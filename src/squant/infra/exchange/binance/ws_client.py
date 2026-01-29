"""Binance WebSocket client with heartbeat and auto-reconnect."""

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection
from websockets.exceptions import ConnectionClosed, ConnectionClosedError

from squant.infra.exchange.exceptions import (
    ExchangeAuthenticationError,
    ExchangeConnectionError,
)

from .client import BinanceClient
from .ws_types import (
    KLINE_INTERVALS,
    BinanceAccountUpdate,
    BinanceBalanceUpdate,
    BinanceCandle,
    BinanceOrderBook,
    BinanceOrderBookLevel,
    BinanceOrderUpdate,
    BinanceTicker,
    BinanceTrade,
)

logger = logging.getLogger(__name__)

# Type alias for message handlers
MessageHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


def _to_binance_symbol(symbol: str) -> str:
    """Convert standard symbol to Binance lowercase format for WebSocket streams.

    Note: This differs from BinanceAdapter._to_binance_symbol() which returns
    UPPERCASE for REST API calls. Binance WebSocket streams require lowercase
    symbols (e.g., 'btcusdt@ticker'), while REST API uses uppercase ('BTCUSDT').
    """
    return symbol.replace("/", "").lower()


def _from_binance_symbol(symbol: str) -> str:
    """Convert Binance WebSocket symbol to standard format.

    Binance stream symbols are lowercase without separator. This function
    normalizes to uppercase before parsing.

    Note: Similar logic exists in BinanceAdapter._from_binance_symbol() for
    REST API responses. Both implementations share the same parsing logic
    for consistency, but are kept separate to maintain clear boundaries
    between WebSocket and REST API code.
    """
    symbol = symbol.upper()
    quote_currencies = ["USDT", "USDC", "BUSD", "FDUSD", "TUSD", "BTC", "ETH", "BNB"]
    for quote in quote_currencies:
        if symbol.endswith(quote):
            base = symbol[: -len(quote)]
            if base:
                return f"{base}/{quote}"
    if len(symbol) > 4:
        return f"{symbol[:-4]}/{symbol[-4:]}"
    return symbol


class BinanceWebSocketClient:
    """WebSocket client for Binance exchange.

    Handles connection management, stream subscriptions, heartbeat,
    and automatic reconnection with exponential backoff.

    Binance WebSocket API:
    - Public streams: wss://stream.binance.com:9443/stream?streams=<stream1>/<stream2>
    - User data streams: wss://stream.binance.com:9443/ws/<listenKey>
    - Testnet: wss://testnet.binance.vision/stream?streams=<stream1>/<stream2>
    """

    # WebSocket endpoints
    BASE_WS_URL = "wss://stream.binance.com:9443"
    TESTNET_WS_URL = "wss://testnet.binance.vision"

    # Connection settings
    HEARTBEAT_INTERVAL = 180.0  # 3 minutes - Binance connections timeout after 24h
    RECONNECT_MAX_ATTEMPTS = 10
    RECONNECT_BASE_DELAY = 1.0
    RECONNECT_MAX_DELAY = 60.0
    CONNECTION_TIMEOUT = 30.0
    INACTIVITY_TIMEOUT = 300.0  # 5 minutes - Binance may disconnect after inactivity

    # Listen key refresh interval (every 30 minutes, key expires after 60)
    LISTEN_KEY_REFRESH_INTERVAL = 1800.0

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        testnet: bool = False,
        private: bool = False,
    ) -> None:
        """Initialize Binance WebSocket client.

        Args:
            api_key: Binance API key (required for user data streams).
            api_secret: Binance API secret (required for user data streams).
            testnet: Whether to use testnet.
            private: Whether this is for private/user data streams.
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.private = private

        # REST client for listen key management
        self._rest_client: BinanceClient | None = None

        # Connection state
        self._ws: ClientConnection | None = None
        self._connected = False
        self._running = False
        self._reconnect_count = 0

        # Listen key for user data streams
        self._listen_key: str | None = None

        # Stream subscriptions (e.g., "btcusdt@ticker", "ethusdt@kline_1m")
        self._subscriptions: set[str] = set()

        # Message handlers
        self._handlers: list[MessageHandler] = []

        # Background tasks
        self._receive_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._listen_key_task: asyncio.Task[None] | None = None

        # Inactivity tracking
        self._last_message_time: float = 0

        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

        # Subscription request ID counter
        self._request_id = 0

    @property
    def base_url(self) -> str:
        """Get base WebSocket URL based on testnet setting."""
        return self.TESTNET_WS_URL if self.testnet else self.BASE_WS_URL

    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self._connected and self._ws is not None

    def _build_stream_url(self) -> str:
        """Build WebSocket URL based on subscriptions and mode."""
        if self.private and self._listen_key:
            # User data stream
            return f"{self.base_url}/ws/{self._listen_key}"
        elif self._subscriptions:
            # Combined streams
            streams = "/".join(sorted(self._subscriptions))
            return f"{self.base_url}/stream?streams={streams}"
        else:
            # Base connection (will subscribe later)
            return f"{self.base_url}/ws"

    def _get_next_request_id(self) -> int:
        """Get next request ID for subscription messages."""
        self._request_id += 1
        return self._request_id

    async def _create_listen_key(self) -> str:
        """Create a listen key for user data streams.

        Returns:
            Listen key string.
        """
        if not self._rest_client:
            if not self.api_key or not self.api_secret:
                raise ExchangeAuthenticationError(
                    message="API credentials required for user data streams",
                    exchange="binance",
                )
            self._rest_client = BinanceClient(
                api_key=self.api_key,
                api_secret=self.api_secret,
                testnet=self.testnet,
            )
            await self._rest_client.connect()

        # Create listen key (POST to /api/v3/userDataStream)
        response = await self._rest_client.post(
            "/api/v3/userDataStream",
            params={},
            authenticated=True,
        )

        if isinstance(response, dict) and "listenKey" in response:
            listen_key = response["listenKey"]
            if isinstance(listen_key, str):
                return listen_key

        raise ExchangeAuthenticationError(
            message="Failed to create listen key",
            exchange="binance",
        )

    async def _refresh_listen_key(self) -> None:
        """Refresh/keepalive the listen key."""
        if not self._rest_client or not self._listen_key:
            return

        try:
            await self._rest_client.request(
                "PUT",
                "/api/v3/userDataStream",
                params={"listenKey": self._listen_key},
                authenticated=True,
            )
            logger.debug("Listen key refreshed")
        except Exception as e:
            logger.warning(f"Failed to refresh listen key: {e}")

    async def connect(self) -> None:
        """Establish WebSocket connection."""
        if self._connected:
            logger.debug("Already connected")
            return

        async with self._lock:
            try:
                # For private streams, get listen key first
                if self.private:
                    self._listen_key = await self._create_listen_key()
                    logger.info("Created listen key for user data stream")

                ws_url = self._build_stream_url()
                logger.info(f"Connecting to Binance WebSocket: {ws_url}")

                self._ws = await asyncio.wait_for(
                    websockets.connect(
                        ws_url,
                        ping_interval=20,  # Binance requires ping within 60s
                        ping_timeout=20,
                        close_timeout=10,
                    ),
                    timeout=self.CONNECTION_TIMEOUT,
                )
                self._connected = True
                self._reconnect_count = 0
                self._last_message_time = time.monotonic()
                logger.info("WebSocket connection established")

                # Start background tasks
                self._running = True
                self._receive_task = asyncio.create_task(self._receive_loop())
                self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

                # Start listen key refresh task for private streams
                if self.private:
                    self._listen_key_task = asyncio.create_task(self._listen_key_refresh_loop())

            except TimeoutError as e:
                raise ExchangeConnectionError(
                    message=f"Connection timeout: {e}",
                    exchange="binance",
                ) from e
            except Exception as e:
                raise ExchangeConnectionError(
                    message=f"Failed to connect: {e}",
                    exchange="binance",
                ) from e

    async def close(self) -> None:
        """Close WebSocket connection and cleanup."""
        logger.info("Closing Binance WebSocket connection")
        self._running = False

        # Cancel background tasks
        for task in [self._receive_task, self._heartbeat_task, self._listen_key_task]:
            if task and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

        self._receive_task = None
        self._heartbeat_task = None
        self._listen_key_task = None

        # Close WebSocket
        if self._ws:
            try:
                await self._ws.close()
            except Exception as e:
                logger.warning(f"Error closing WebSocket: {e}")
            self._ws = None

        # Close REST client
        if self._rest_client:
            await self._rest_client.close()
            self._rest_client = None

        self._connected = False
        self._listen_key = None
        logger.info("Binance WebSocket connection closed")

    async def _send(self, message: dict[str, Any]) -> None:
        """Send a message through WebSocket.

        Args:
            message: Message to send.
        """
        if not self._ws or not self._connected:
            raise ExchangeConnectionError(
                message="Not connected",
                exchange="binance",
            )

        try:
            await self._ws.send(json.dumps(message))
        except ConnectionClosed as e:
            self._connected = False
            raise ExchangeConnectionError(
                message=f"Connection closed: {e}",
                exchange="binance",
            ) from e

    async def subscribe(
        self,
        symbols: list[str],
        streams: list[str],
    ) -> None:
        """Subscribe to streams for given symbols.

        Args:
            symbols: List of symbols (e.g., ["BTC/USDT", "ETH/USDT"]).
            streams: List of stream types (e.g., ["ticker", "kline_1m"]).

        Stream types:
            - ticker: 24hr ticker
            - miniTicker: Mini ticker
            - kline_<interval>: Candlesticks (1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w)
            - trade: Trade stream
            - depth5, depth10, depth20: Order book depth
            - bookTicker: Best bid/ask
        """
        new_subscriptions: list[str] = []

        for symbol in symbols:
            binance_symbol = _to_binance_symbol(symbol)
            for stream in streams:
                stream_name = f"{binance_symbol}@{stream}"
                if stream_name not in self._subscriptions:
                    self._subscriptions.add(stream_name)
                    new_subscriptions.append(stream_name)

        if not new_subscriptions:
            return

        # If not connected, subscriptions will be applied on connect
        if not self._connected:
            logger.info(f"Queued subscriptions: {new_subscriptions}")
            return

        # Send subscribe message
        subscribe_msg = {
            "method": "SUBSCRIBE",
            "params": new_subscriptions,
            "id": self._get_next_request_id(),
        }

        await self._send(subscribe_msg)
        logger.info(f"Subscribed to streams: {new_subscriptions}")

    async def unsubscribe(
        self,
        symbols: list[str],
        streams: list[str],
    ) -> None:
        """Unsubscribe from streams for given symbols.

        Args:
            symbols: List of symbols.
            streams: List of stream types.
        """
        remove_subscriptions: list[str] = []

        for symbol in symbols:
            binance_symbol = _to_binance_symbol(symbol)
            for stream in streams:
                stream_name = f"{binance_symbol}@{stream}"
                if stream_name in self._subscriptions:
                    self._subscriptions.discard(stream_name)
                    remove_subscriptions.append(stream_name)

        if not remove_subscriptions or not self._connected:
            return

        # Send unsubscribe message
        unsubscribe_msg = {
            "method": "UNSUBSCRIBE",
            "params": remove_subscriptions,
            "id": self._get_next_request_id(),
        }

        await self._send(unsubscribe_msg)
        logger.info(f"Unsubscribed from streams: {remove_subscriptions}")

    async def subscribe_ticker(self, symbols: list[str]) -> None:
        """Subscribe to ticker streams."""
        await self.subscribe(symbols, ["ticker"])

    async def subscribe_kline(self, symbols: list[str], interval: str = "1m") -> None:
        """Subscribe to kline/candlestick streams."""
        if interval not in KLINE_INTERVALS:
            raise ValueError(f"Invalid kline interval: {interval}")
        await self.subscribe(symbols, [f"kline_{interval}"])

    async def subscribe_trade(self, symbols: list[str]) -> None:
        """Subscribe to trade streams."""
        await self.subscribe(symbols, ["trade"])

    async def subscribe_depth(self, symbols: list[str], levels: int = 10) -> None:
        """Subscribe to order book depth streams."""
        if levels not in [5, 10, 20]:
            raise ValueError(f"Invalid depth levels: {levels}. Use 5, 10, or 20.")
        await self.subscribe(symbols, [f"depth{levels}@100ms"])

    async def subscribe_book_ticker(self, symbols: list[str]) -> None:
        """Subscribe to best bid/ask streams."""
        await self.subscribe(symbols, ["bookTicker"])

    def add_handler(self, handler: MessageHandler) -> None:
        """Add a message handler."""
        if handler not in self._handlers:
            self._handlers.append(handler)

    def remove_handler(self, handler: MessageHandler) -> None:
        """Remove a message handler."""
        if handler in self._handlers:
            self._handlers.remove(handler)

    async def _receive_loop(self) -> None:
        """Background task to receive and process messages."""
        while self._running:
            try:
                if not self._ws:
                    await asyncio.sleep(0.1)
                    continue

                try:
                    raw_msg = await asyncio.wait_for(
                        self._ws.recv(),
                        timeout=self.INACTIVITY_TIMEOUT,
                    )
                except TimeoutError:
                    logger.warning("No data received, checking connection...")
                    await self._handle_disconnect()
                    continue

                self._last_message_time = time.monotonic()

                # Parse JSON message
                try:
                    msg = json.loads(raw_msg)
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse message: {e}")
                    continue

                # Handle different message types
                await self._handle_message(msg)

            except ConnectionClosedError as e:
                logger.warning(f"Connection closed: {e}")
                await self._handle_disconnect()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Error in receive loop: {e}")
                await asyncio.sleep(1)

    async def _handle_message(self, msg: dict[str, Any]) -> None:
        """Handle incoming WebSocket message."""
        # Handle subscription response
        if "result" in msg and "id" in msg:
            if msg["result"] is None:
                logger.debug(f"Subscription confirmed (id={msg['id']})")
            else:
                logger.warning(f"Subscription response: {msg}")
            return

        # Handle error
        if "error" in msg:
            logger.error(f"WebSocket error: {msg['error']}")
            return

        # Handle combined stream format (has 'stream' and 'data' keys)
        if "stream" in msg and "data" in msg:
            stream = msg["stream"]
            data = msg["data"]
            await self._dispatch_stream_data(stream, data)
            return

        # Handle direct stream format (user data streams)
        if "e" in msg:  # Event type
            await self._dispatch_event_data(msg)
            return

        # Dispatch to handlers for other messages
        await self._dispatch_to_handlers(msg)

    async def _dispatch_stream_data(self, stream: str, data: dict[str, Any]) -> None:
        """Dispatch stream data based on stream type."""
        # Parse stream name: btcusdt@ticker, btcusdt@kline_1m, etc.
        parts = stream.split("@")
        if len(parts) < 2:
            return

        symbol_lower = parts[0]
        stream_type = parts[1]
        symbol = _from_binance_symbol(symbol_lower)

        # Convert to internal format and dispatch
        parsed_data: dict[str, Any] = {"stream": stream, "symbol": symbol}

        if stream_type == "ticker":
            parsed_data["type"] = "ticker"
            parsed_data["data"] = self._parse_ticker(data, symbol)
        elif stream_type.startswith("kline_"):
            parsed_data["type"] = "kline"
            interval = stream_type.replace("kline_", "")
            parsed_data["data"] = self._parse_kline(data, symbol, interval)
        elif stream_type == "trade":
            parsed_data["type"] = "trade"
            parsed_data["data"] = self._parse_trade(data, symbol)
        elif stream_type.startswith("depth"):
            parsed_data["type"] = "depth"
            parsed_data["data"] = self._parse_depth(data, symbol)
        elif stream_type == "bookTicker":
            parsed_data["type"] = "bookTicker"
            parsed_data["data"] = self._parse_book_ticker(data, symbol)
        else:
            parsed_data["type"] = stream_type
            parsed_data["data"] = data

        await self._dispatch_to_handlers(parsed_data)

    async def _dispatch_event_data(self, data: dict[str, Any]) -> None:
        """Dispatch user data stream events."""
        event_type = data.get("e", "")

        parsed_data: dict[str, Any] = {"event_type": event_type}

        if event_type == "executionReport":
            parsed_data["type"] = "order_update"
            parsed_data["data"] = self._parse_order_update(data)
        elif event_type == "outboundAccountPosition":
            parsed_data["type"] = "account_update"
            parsed_data["data"] = self._parse_account_update(data)
        elif event_type == "balanceUpdate":
            parsed_data["type"] = "balance_update"
            parsed_data["data"] = data
        else:
            parsed_data["type"] = event_type
            parsed_data["data"] = data

        await self._dispatch_to_handlers(parsed_data)

    async def _dispatch_to_handlers(self, msg: dict[str, Any]) -> None:
        """Dispatch message to all handlers."""
        for handler in self._handlers:
            try:
                await handler(msg)
            except Exception as e:
                logger.exception(f"Error in message handler: {e}")

    def _parse_ticker(self, data: dict[str, Any], symbol: str) -> dict[str, Any]:
        """Parse ticker data from Binance format."""
        return BinanceTicker(
            symbol=symbol,
            last=Decimal(data.get("c", "0")),
            bid=Decimal(data.get("b", "0")) if data.get("b") else None,
            ask=Decimal(data.get("a", "0")) if data.get("a") else None,
            bid_size=Decimal(data.get("B", "0")) if data.get("B") else None,
            ask_size=Decimal(data.get("A", "0")) if data.get("A") else None,
            high_24h=Decimal(data.get("h", "0")) if data.get("h") else None,
            low_24h=Decimal(data.get("l", "0")) if data.get("l") else None,
            volume_24h=Decimal(data.get("v", "0")) if data.get("v") else None,
            volume_quote_24h=Decimal(data.get("q", "0")) if data.get("q") else None,
            open_24h=Decimal(data.get("o", "0")) if data.get("o") else None,
            price_change=Decimal(data.get("p", "0")) if data.get("p") else None,
            price_change_percent=Decimal(data.get("P", "0")) if data.get("P") else None,
            timestamp=datetime.fromtimestamp(data.get("E", 0) / 1000, tz=UTC),
        ).model_dump()

    def _parse_kline(
        self, data: dict[str, Any], symbol: str, interval: str
    ) -> dict[str, Any]:
        """Parse kline/candlestick data from Binance format."""
        k = data.get("k", {})
        return BinanceCandle(
            symbol=symbol,
            timeframe=interval,
            timestamp=datetime.fromtimestamp(k.get("t", 0) / 1000, tz=UTC),
            open=Decimal(k.get("o", "0")),
            high=Decimal(k.get("h", "0")),
            low=Decimal(k.get("l", "0")),
            close=Decimal(k.get("c", "0")),
            volume=Decimal(k.get("v", "0")),
            volume_quote=Decimal(k.get("q", "0")) if k.get("q") else None,
            trades=k.get("n"),
            is_closed=k.get("x", False),
        ).model_dump()

    def _parse_trade(self, data: dict[str, Any], symbol: str) -> dict[str, Any]:
        """Parse trade data from Binance format."""
        return BinanceTrade(
            symbol=symbol,
            trade_id=str(data.get("t", "")),
            price=Decimal(data.get("p", "0")),
            size=Decimal(data.get("q", "0")),
            side="sell" if data.get("m", False) else "buy",
            timestamp=datetime.fromtimestamp(data.get("T", 0) / 1000, tz=UTC),
            buyer_is_maker=data.get("m", False),
        ).model_dump()

    def _parse_depth(self, data: dict[str, Any], symbol: str) -> dict[str, Any]:
        """Parse order book depth data from Binance format."""
        bids = [
            BinanceOrderBookLevel(price=Decimal(b[0]), size=Decimal(b[1]))
            for b in data.get("bids", [])
        ]
        asks = [
            BinanceOrderBookLevel(price=Decimal(a[0]), size=Decimal(a[1]))
            for a in data.get("asks", [])
        ]
        return BinanceOrderBook(
            symbol=symbol,
            bids=bids,
            asks=asks,
            last_update_id=data.get("lastUpdateId"),
        ).model_dump()

    def _parse_book_ticker(self, data: dict[str, Any], symbol: str) -> dict[str, Any]:
        """Parse book ticker (best bid/ask) data from Binance format."""
        return {
            "symbol": symbol,
            "bid": Decimal(data.get("b", "0")),
            "bid_size": Decimal(data.get("B", "0")),
            "ask": Decimal(data.get("a", "0")),
            "ask_size": Decimal(data.get("A", "0")),
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def _parse_order_update(self, data: dict[str, Any]) -> dict[str, Any]:
        """Parse order update from user data stream."""
        symbol = _from_binance_symbol(data.get("s", ""))
        return BinanceOrderUpdate(
            order_id=str(data.get("i", "")),
            client_order_id=data.get("c"),
            symbol=symbol,
            side=data.get("S", ""),
            order_type=data.get("o", ""),
            time_in_force=data.get("f"),
            status=data.get("X", ""),
            price=Decimal(data.get("p", "0")) if data.get("p") else None,
            quantity=Decimal(data.get("q", "0")),
            filled_quantity=Decimal(data.get("z", "0")),
            cumulative_quote_qty=Decimal(data.get("Z", "0")) if data.get("Z") else None,
            last_filled_price=Decimal(data.get("L", "0")) if data.get("L") else None,
            last_filled_qty=Decimal(data.get("l", "0")) if data.get("l") else None,
            commission=Decimal(data.get("n", "0")) if data.get("n") else None,
            commission_asset=data.get("N"),
            trade_id=data.get("t"),
            created_at=datetime.fromtimestamp(data.get("O", 0) / 1000, tz=UTC) if data.get("O") else None,
            updated_at=datetime.fromtimestamp(data.get("T", 0) / 1000, tz=UTC) if data.get("T") else None,
        ).model_dump()

    def _parse_account_update(self, data: dict[str, Any]) -> dict[str, Any]:
        """Parse account update from user data stream."""
        balances = [
            BinanceBalanceUpdate(
                asset=b.get("a", ""),
                free=Decimal(b.get("f", "0")),
                locked=Decimal(b.get("l", "0")),
            )
            for b in data.get("B", [])
        ]
        return BinanceAccountUpdate(
            balances=balances,
            last_update_time=data.get("u"),
        ).model_dump()

    async def _heartbeat_loop(self) -> None:
        """Background task for connection keepalive."""
        while self._running:
            try:
                await asyncio.sleep(self.HEARTBEAT_INTERVAL)

                # Check if we've received data recently
                if self._connected:
                    elapsed = time.monotonic() - self._last_message_time
                    if elapsed > self.INACTIVITY_TIMEOUT:
                        logger.warning(f"No data for {elapsed:.0f}s, reconnecting...")
                        await self._handle_disconnect()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Error in heartbeat loop: {e}")

    async def _listen_key_refresh_loop(self) -> None:
        """Background task to refresh listen key for user data streams."""
        while self._running and self.private:
            try:
                await asyncio.sleep(self.LISTEN_KEY_REFRESH_INTERVAL)
                await self._refresh_listen_key()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Error refreshing listen key: {e}")

    async def _handle_disconnect(self) -> None:
        """Handle disconnection and trigger reconnection."""
        self._connected = False

        if not self._running:
            return

        logger.warning("Disconnected, attempting reconnection...")
        await self._reconnect()

    async def _reconnect(self) -> None:
        """Attempt to reconnect with exponential backoff."""
        while self._running and self._reconnect_count < self.RECONNECT_MAX_ATTEMPTS:
            self._reconnect_count += 1

            delay = min(
                self.RECONNECT_BASE_DELAY * (2 ** (self._reconnect_count - 1)),
                self.RECONNECT_MAX_DELAY,
            )

            logger.info(
                f"Reconnection attempt {self._reconnect_count}/{self.RECONNECT_MAX_ATTEMPTS} "
                f"in {delay:.1f}s"
            )
            await asyncio.sleep(delay)

            try:
                # Close existing connection
                if self._ws:
                    with contextlib.suppress(Exception):
                        await self._ws.close()
                    self._ws = None

                # For private streams, refresh listen key
                if self.private:
                    self._listen_key = await self._create_listen_key()

                # Reconnect
                ws_url = self._build_stream_url()
                self._ws = await asyncio.wait_for(
                    websockets.connect(
                        ws_url,
                        ping_interval=20,
                        ping_timeout=20,
                        close_timeout=10,
                    ),
                    timeout=self.CONNECTION_TIMEOUT,
                )
                self._connected = True
                self._last_message_time = time.monotonic()
                logger.info("Reconnection successful")

                # Re-subscribe to streams (for public streams)
                if not self.private and self._subscriptions:
                    subscribe_msg = {
                        "method": "SUBSCRIBE",
                        "params": list(self._subscriptions),
                        "id": self._get_next_request_id(),
                    }
                    await self._send(subscribe_msg)

                self._reconnect_count = 0
                return

            except Exception as e:
                logger.warning(f"Reconnection failed: {e}")

        if self._reconnect_count >= self.RECONNECT_MAX_ATTEMPTS:
            logger.error("Max reconnection attempts reached")
            self._running = False

    async def __aenter__(self) -> "BinanceWebSocketClient":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()
