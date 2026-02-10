"""Stream manager for WebSocket data distribution via Redis pub/sub."""

import asyncio
import contextlib
import logging
from collections import deque
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from redis.asyncio import Redis

from squant.config import get_settings
from squant.infra.exchange.ccxt import CCXTStreamProvider, ExchangeCredentials
from squant.infra.exchange.okx.ws_client import OKXWebSocketClient
from squant.infra.exchange.okx.ws_types import (
    CANDLE_CHANNELS,
    OKXChannel,
    WSAccountUpdate,
    WSBalanceUpdate,
    WSCandle,
    WSMessage,
    WSMessageType,
    WSOrderBook,
    WSOrderBookLevel,
    WSOrderUpdate,
    WSTicker,
    WSTrade,
)
from squant.infra.redis import get_redis_client

logger = logging.getLogger(__name__)


class StreamManager:
    """Manages WebSocket connections and distributes data via Redis pub/sub.

    This manager:
    1. Maintains OKX WebSocket connections (public and private)
    2. Converts OKX message format to internal types
    3. Publishes data to Redis channels for FastAPI WebSocket endpoints
    """

    REDIS_CHANNEL_PREFIX = "squant:ws:"

    # Batch publishing configuration
    FLUSH_INTERVAL = 0.05  # 50ms - flush buffer every 50ms
    MAX_BUFFER_SIZE = 500  # Force flush when buffer reaches this size

    def __init__(self) -> None:
        """Initialize stream manager."""
        # Native OKX clients (kept as backup)
        self._public_client: OKXWebSocketClient | None = None
        self._business_client: OKXWebSocketClient | None = None  # For candles
        self._private_client: OKXWebSocketClient | None = None

        # CCXT provider (primary when use_ccxt_provider=True)
        self._ccxt_provider: CCXTStreamProvider | None = None

        self._redis: Redis | None = None
        self._running = False
        self._settings = get_settings()

        # Track active subscriptions
        self._ticker_subscriptions: set[str] = set()
        self._candle_subscriptions: set[tuple[str, str]] = set()  # (symbol, timeframe)
        self._trade_subscriptions: set[str] = set()
        self._orderbook_subscriptions: set[str] = set()

        # Batch publishing buffer
        self._publish_buffer: deque[tuple[str, str]] = deque()  # (channel, message_json)
        self._flush_task: asyncio.Task | None = None
        self._buffer_lock = asyncio.Lock()

        # Throughput stats (for periodic logging)
        self._stats_messages_published = 0
        self._stats_flushes = 0
        self._stats_task: asyncio.Task | None = None
        self._stats_interval = 60.0  # Log throughput every 60 seconds

        # Health check task
        self._health_check_task: asyncio.Task | None = None
        self._health_check_interval = 30.0  # Check every 30 seconds

        # Connection retry configuration
        self._start_attempted = False  # Has start() been called at least once?
        self._retry_task: asyncio.Task | None = None
        self._retry_interval = 30.0  # Retry every 30 seconds
        self._max_startup_retries = 10  # Max retries for initial connection

    @property
    def is_running(self) -> bool:
        """Check if stream manager is running."""
        return self._running

    @property
    def is_healthy(self) -> bool:
        """Check if stream manager is running and connections are healthy.

        This is a more thorough check than is_running - it verifies that
        the underlying connections (CCXT provider or native clients) are
        actually connected and operational.
        """
        if not self._running:
            return False

        if self._settings.use_ccxt_provider:
            # Check if CCXT provider is connected and healthy
            if self._ccxt_provider is None:
                return False
            # Use the detailed health check if available
            if hasattr(self._ccxt_provider, "is_healthy"):
                return self._ccxt_provider.is_healthy()
            return self._ccxt_provider.is_connected
        else:
            # Check if native OKX clients are connected
            public_ok = self._public_client is not None and self._public_client.is_connected
            business_ok = self._business_client is not None and self._business_client.is_connected
            return public_ok and business_ok

    async def start(self) -> None:
        """Start the public WebSocket connection."""
        if self._running:
            logger.debug("Stream manager already running")
            return

        self._start_attempted = True
        logger.info("Starting stream manager...")

        # Get Redis client (initialized at app startup)
        self._redis = get_redis_client()

        if self._settings.use_ccxt_provider:
            await self._start_ccxt_provider()
        else:
            await self._start_native_okx()

        self._running = True

        # Start the batch publishing flush task
        self._flush_task = asyncio.create_task(self._flush_loop())

        # Start throughput stats logging task
        self._stats_task = asyncio.create_task(self._stats_loop())

        # Start the health check task
        self._health_check_task = asyncio.create_task(self._health_check_loop())

        logger.info("Stream manager started")

        # Notify connected WebSocket clients that the service is ready
        await self._publish_service_ready()

    async def try_start(self) -> bool:
        """Attempt to start the stream manager without raising exceptions.

        Returns:
            True if the stream manager is now running, False otherwise.
        """
        if self._running:
            return True

        try:
            await self.start()
            return True
        except Exception as e:
            logger.warning(f"Failed to start stream manager: {e}")
            return False

    def start_retry_loop(self) -> None:
        """Start a background task that periodically retries connection.

        Call this after a failed start() to enable automatic retry.
        The retry loop will stop once connection succeeds.
        """
        if self._retry_task and not self._retry_task.done():
            logger.debug("Retry loop already running")
            return

        logger.info("Starting connection retry loop...")
        self._retry_task = asyncio.create_task(self._retry_loop())

    async def _retry_loop(self) -> None:
        """Background task that periodically retries the connection."""
        retry_count = 0

        while not self._running and retry_count < self._max_startup_retries:
            await asyncio.sleep(self._retry_interval)

            if self._running:
                break

            retry_count += 1
            logger.info(
                f"Retrying stream manager connection (attempt {retry_count}/{self._max_startup_retries})..."
            )

            try:
                await self.start()
                logger.info("Stream manager connected successfully after retry")
                break
            except Exception as e:
                logger.warning(f"Retry {retry_count} failed: {e}")

        if not self._running:
            logger.error(
                f"Stream manager failed to connect after {retry_count} retries. "
                "WebSocket will remain unavailable until next restart."
            )

    async def _start_ccxt_provider(self) -> None:
        """Start CCXT-based stream provider."""
        exchange_id = self._settings.default_exchange.lower()
        logger.info(f"Starting CCXT provider for {exchange_id}...")

        # Build credentials based on exchange
        credentials = self._get_exchange_credentials(exchange_id)

        # Create and connect CCXT provider
        self._ccxt_provider = CCXTStreamProvider(exchange_id, credentials)
        self._ccxt_provider.add_handler(self._handle_ccxt_message)
        await self._ccxt_provider.connect()

        logger.info(f"CCXT provider started for {exchange_id}")

    async def _start_native_okx(self) -> None:
        """Start native OKX WebSocket clients (backup mode)."""
        logger.info("Starting native OKX WebSocket clients...")

        # Initialize public WebSocket client (for tickers, trades, orderbook)
        self._public_client = OKXWebSocketClient(
            testnet=self._settings.okx_testnet,
            private=False,
        )
        self._public_client.add_handler(self._handle_public_message)

        # Initialize business WebSocket client (for candles)
        # OKX requires candle subscriptions on the /business endpoint since June 2023
        self._business_client = OKXWebSocketClient(
            testnet=self._settings.okx_testnet,
            private=False,
            business=True,
        )
        self._business_client.add_handler(self._handle_public_message)

        await self._public_client.connect()
        await self._business_client.connect()

        logger.info("Native OKX WebSocket clients started")

    async def switch_exchange(self, exchange_id: str) -> None:
        """Switch to a new exchange data source.

        This method closes the current CCXT provider and creates a new one
        for the specified exchange, then resubscribes to all active channels.

        Args:
            exchange_id: New exchange identifier (okx, binance, bybit).

        Note:
            This only works in CCXT provider mode. Native OKX mode does not
            support exchange switching.
        """
        if not self._settings.use_ccxt_provider:
            logger.warning("Exchange switching only supported in CCXT provider mode")
            return

        if not self._running:
            logger.warning("Stream manager not running, cannot switch exchange")
            return

        current_exchange = self._ccxt_provider.exchange_id if self._ccxt_provider else "none"
        if current_exchange == exchange_id:
            logger.debug(f"Already connected to {exchange_id}, no switch needed")
            return

        logger.info(f"Switching exchange from {current_exchange} to {exchange_id}")

        # Notify clients that exchange is switching
        await self._publish_exchange_switching(current_exchange, exchange_id, "switching")

        # Store current subscriptions before closing
        ticker_subs = set(self._ticker_subscriptions)
        candle_subs = set(self._candle_subscriptions)
        trade_subs = set(self._trade_subscriptions)
        orderbook_subs = set(self._orderbook_subscriptions)

        # Close current CCXT provider
        if self._ccxt_provider:
            await self._ccxt_provider.close()
            self._ccxt_provider = None

        # Clear subscription tracking (will be rebuilt)
        self._ticker_subscriptions.clear()
        self._candle_subscriptions.clear()
        self._trade_subscriptions.clear()
        self._orderbook_subscriptions.clear()

        # Create new CCXT provider for the new exchange
        credentials = self._get_exchange_credentials(exchange_id)
        self._ccxt_provider = CCXTStreamProvider(exchange_id, credentials)
        self._ccxt_provider.add_handler(self._handle_ccxt_message)
        await self._ccxt_provider.connect()

        logger.info(
            f"Connected to {exchange_id}, resubscribing to {len(ticker_subs)} tickers, {len(candle_subs)} candles"
        )

        # Resubscribe to all previous channels on new exchange
        failed_subs: list[str] = []

        for symbol in ticker_subs:
            try:
                await self.subscribe_ticker(symbol)
            except Exception as e:
                logger.error(f"Failed to resubscribe ticker {symbol}: {e}")
                failed_subs.append(f"ticker:{symbol}")

        for symbol, timeframe in candle_subs:
            try:
                await self.subscribe_candles(symbol, timeframe)
            except Exception as e:
                logger.error(f"Failed to resubscribe candle {symbol} {timeframe}: {e}")
                failed_subs.append(f"candle:{symbol}:{timeframe}")

        for symbol in trade_subs:
            try:
                await self.subscribe_trades(symbol)
            except Exception as e:
                logger.error(f"Failed to resubscribe trades {symbol}: {e}")
                failed_subs.append(f"trade:{symbol}")

        for symbol in orderbook_subs:
            try:
                await self.subscribe_orderbook(symbol)
            except Exception as e:
                logger.error(f"Failed to resubscribe orderbook {symbol}: {e}")
                failed_subs.append(f"orderbook:{symbol}")

        if failed_subs:
            logger.error(
                f"Exchange switch to {exchange_id}: {len(failed_subs)} subscriptions failed: "
                f"{', '.join(failed_subs)}"
            )
        logger.info(f"Switched to {exchange_id} ({len(failed_subs)} failures)")

        # Notify clients that exchange switch is complete
        await self._publish_exchange_switching(current_exchange, exchange_id, "completed")

    def _get_exchange_credentials(self, exchange_id: str) -> ExchangeCredentials | None:
        """Get credentials for the specified exchange.

        Args:
            exchange_id: Exchange identifier (okx, binance, bybit).

        Returns:
            ExchangeCredentials or None if not configured.
        """
        if exchange_id == "okx":
            if self._settings.okx_api_key and self._settings.okx_api_secret:
                return ExchangeCredentials(
                    api_key=self._settings.okx_api_key.get_secret_value(),
                    api_secret=self._settings.okx_api_secret.get_secret_value(),
                    passphrase=self._settings.okx_passphrase.get_secret_value()
                    if self._settings.okx_passphrase
                    else None,
                    sandbox=self._settings.okx_testnet,
                )
        elif exchange_id == "binance":
            if self._settings.binance_api_key and self._settings.binance_api_secret:
                return ExchangeCredentials(
                    api_key=self._settings.binance_api_key.get_secret_value(),
                    api_secret=self._settings.binance_api_secret.get_secret_value(),
                    sandbox=self._settings.binance_testnet,
                )
        elif exchange_id == "bybit":
            if self._settings.bybit_api_key and self._settings.bybit_api_secret:
                return ExchangeCredentials(
                    api_key=self._settings.bybit_api_key.get_secret_value(),
                    api_secret=self._settings.bybit_api_secret.get_secret_value(),
                    sandbox=self._settings.bybit_testnet,
                )
        return None

    async def start_private(self) -> None:
        """Start the private WebSocket connection (requires credentials).

        For CCXT provider mode, private channels are handled by the same provider.
        For native OKX mode, a separate private client is used.
        """
        if self._settings.use_ccxt_provider and self._ccxt_provider:
            # CCXT provider already handles private channels if credentials are provided
            logger.info("CCXT provider already supports private channels")
            return

        # Native OKX mode
        if not all(
            [
                self._settings.okx_api_key,
                self._settings.okx_api_secret,
                self._settings.okx_passphrase,
            ]
        ):
            logger.warning("OKX credentials not configured, private channels unavailable")
            return

        logger.info("Starting private WebSocket connection...")

        # Get Redis client if not already set
        if self._redis is None:
            self._redis = get_redis_client()

        # Initialize private WebSocket client
        self._private_client = OKXWebSocketClient(
            api_key=self._settings.okx_api_key.get_secret_value()
            if self._settings.okx_api_key
            else None,
            api_secret=self._settings.okx_api_secret.get_secret_value()
            if self._settings.okx_api_secret
            else None,
            passphrase=self._settings.okx_passphrase.get_secret_value()
            if self._settings.okx_passphrase
            else None,
            testnet=self._settings.okx_testnet,
            private=True,
        )
        self._private_client.add_handler(self._handle_private_message)

        await self._private_client.connect()
        logger.info("Stream manager private connection established")

    async def stop(self) -> None:
        """Stop all WebSocket connections."""
        logger.info("Stopping stream manager...")
        self._running = False

        # Stop retry task if running
        if self._retry_task and not self._retry_task.done():
            self._retry_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._retry_task
            self._retry_task = None

        # Stop health check task
        if self._health_check_task:
            self._health_check_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._health_check_task
            self._health_check_task = None

        # Stop stats task
        if self._stats_task:
            self._stats_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._stats_task
            self._stats_task = None

        # Stop flush task
        if self._flush_task:
            self._flush_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._flush_task
            self._flush_task = None

        # Flush any remaining messages
        await self._flush_buffer()

        # Close CCXT provider
        if self._ccxt_provider:
            await self._ccxt_provider.close()
            self._ccxt_provider = None

        # Close native OKX clients
        if self._public_client:
            await self._public_client.close()
            self._public_client = None

        if self._business_client:
            await self._business_client.close()
            self._business_client = None

        if self._private_client:
            await self._private_client.close()
            self._private_client = None

        self._redis = None
        logger.info("Stream manager stopped")

    # ==================== Public Channel Subscriptions ====================

    async def subscribe_ticker(self, symbol: str) -> None:
        """Subscribe to ticker updates for a symbol.

        Args:
            symbol: Trading pair (e.g., "BTC/USDT" or "BTC-USDT").
        """
        # Normalize symbol format (use "/" for internal tracking, CCXT uses "/")
        normalized_symbol = self._normalize_symbol(symbol)

        if normalized_symbol in self._ticker_subscriptions:
            return

        if self._settings.use_ccxt_provider:
            if not self._ccxt_provider:
                raise RuntimeError("CCXT provider not started. Call start() first.")
            await self._ccxt_provider.watch_ticker(normalized_symbol)
        else:
            if not self._public_client:
                raise RuntimeError("Public client not started. Call start() first.")
            okx_symbol = self._to_okx_symbol(symbol)
            await self._public_client.subscribe(
                [{"channel": OKXChannel.TICKERS.value, "instId": okx_symbol}]
            )

        self._ticker_subscriptions.add(normalized_symbol)
        logger.info(f"Subscribed to ticker: {normalized_symbol}")

    async def unsubscribe_ticker(self, symbol: str) -> None:
        """Unsubscribe from ticker updates."""
        normalized_symbol = self._normalize_symbol(symbol)

        if normalized_symbol not in self._ticker_subscriptions:
            return

        if self._settings.use_ccxt_provider:
            if self._ccxt_provider:
                await self._ccxt_provider.unwatch(f"ticker:{normalized_symbol}")
        else:
            if self._public_client:
                okx_symbol = self._to_okx_symbol(symbol)
                await self._public_client.unsubscribe(
                    [{"channel": OKXChannel.TICKERS.value, "instId": okx_symbol}]
                )

        self._ticker_subscriptions.discard(normalized_symbol)

    async def subscribe_candles(self, symbol: str, timeframe: str = "1m") -> None:
        """Subscribe to candlestick updates.

        Args:
            symbol: Trading pair.
            timeframe: Candle timeframe (1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w).
        """
        normalized_symbol = self._normalize_symbol(symbol)
        key = (normalized_symbol, timeframe)

        if key in self._candle_subscriptions:
            return

        if self._settings.use_ccxt_provider:
            if not self._ccxt_provider:
                logger.error("CCXT provider not started!")
                raise RuntimeError("CCXT provider not started. Call start() first.")

            logger.info(
                f"Subscribing to candles via CCXT: symbol={normalized_symbol}, timeframe={timeframe}"
            )
            await self._ccxt_provider.watch_ohlcv(normalized_symbol, timeframe)
        else:
            # Native OKX mode
            if not self._business_client:
                logger.error("Business client not started!")
                raise RuntimeError("Business client not started. Call start() first.")

            channel = CANDLE_CHANNELS.get(timeframe.lower())
            if not channel:
                logger.error(f"Invalid timeframe: {timeframe}")
                raise ValueError(f"Invalid timeframe: {timeframe}")

            okx_symbol = self._to_okx_symbol(symbol)
            logger.info(
                f"Sending candle subscription to OKX business endpoint: channel={channel.value}, instId={okx_symbol}"
            )
            await self._business_client.subscribe(
                [{"channel": channel.value, "instId": okx_symbol}]
            )

        self._candle_subscriptions.add(key)
        logger.info(f"Subscribed to candles: {normalized_symbol} {timeframe}")

    async def unsubscribe_candles(self, symbol: str, timeframe: str = "1m") -> None:
        """Unsubscribe from candlestick updates."""
        normalized_symbol = self._normalize_symbol(symbol)
        key = (normalized_symbol, timeframe)

        if key not in self._candle_subscriptions:
            return

        if self._settings.use_ccxt_provider:
            if self._ccxt_provider:
                await self._ccxt_provider.unwatch(f"ohlcv:{normalized_symbol}:{timeframe}")
        else:
            if self._business_client:
                channel = CANDLE_CHANNELS.get(timeframe.lower())
                if channel:
                    okx_symbol = self._to_okx_symbol(symbol)
                    await self._business_client.unsubscribe(
                        [{"channel": channel.value, "instId": okx_symbol}]
                    )

        self._candle_subscriptions.discard(key)

    async def subscribe_trades(self, symbol: str) -> None:
        """Subscribe to trade updates for a symbol."""
        normalized_symbol = self._normalize_symbol(symbol)

        if normalized_symbol in self._trade_subscriptions:
            return

        if self._settings.use_ccxt_provider:
            if not self._ccxt_provider:
                raise RuntimeError("CCXT provider not started. Call start() first.")
            await self._ccxt_provider.watch_trades(normalized_symbol)
        else:
            if not self._public_client:
                raise RuntimeError("Public client not started. Call start() first.")
            okx_symbol = self._to_okx_symbol(symbol)
            await self._public_client.subscribe(
                [{"channel": OKXChannel.TRADES.value, "instId": okx_symbol}]
            )

        self._trade_subscriptions.add(normalized_symbol)
        logger.info(f"Subscribed to trades: {normalized_symbol}")

    async def unsubscribe_trades(self, symbol: str) -> None:
        """Unsubscribe from trade updates."""
        normalized_symbol = self._normalize_symbol(symbol)

        if normalized_symbol not in self._trade_subscriptions:
            return

        if self._settings.use_ccxt_provider:
            if self._ccxt_provider:
                await self._ccxt_provider.unwatch(f"trades:{normalized_symbol}")
        else:
            if self._public_client:
                okx_symbol = self._to_okx_symbol(symbol)
                await self._public_client.unsubscribe(
                    [{"channel": OKXChannel.TRADES.value, "instId": okx_symbol}]
                )

        self._trade_subscriptions.discard(normalized_symbol)

    async def subscribe_orderbook(self, symbol: str) -> None:
        """Subscribe to order book updates (5-level depth)."""
        normalized_symbol = self._normalize_symbol(symbol)

        if normalized_symbol in self._orderbook_subscriptions:
            return

        if self._settings.use_ccxt_provider:
            if not self._ccxt_provider:
                raise RuntimeError("CCXT provider not started. Call start() first.")
            await self._ccxt_provider.watch_order_book(normalized_symbol, limit=5)
        else:
            if not self._public_client:
                raise RuntimeError("Public client not started. Call start() first.")
            okx_symbol = self._to_okx_symbol(symbol)
            await self._public_client.subscribe(
                [{"channel": OKXChannel.BOOKS5.value, "instId": okx_symbol}]
            )

        self._orderbook_subscriptions.add(normalized_symbol)
        logger.info(f"Subscribed to orderbook: {normalized_symbol}")

    async def unsubscribe_orderbook(self, symbol: str) -> None:
        """Unsubscribe from order book updates."""
        normalized_symbol = self._normalize_symbol(symbol)

        if normalized_symbol not in self._orderbook_subscriptions:
            return

        if self._settings.use_ccxt_provider:
            if self._ccxt_provider:
                await self._ccxt_provider.unwatch(f"orderbook:{normalized_symbol}")
        else:
            if self._public_client:
                okx_symbol = self._to_okx_symbol(symbol)
                await self._public_client.unsubscribe(
                    [{"channel": OKXChannel.BOOKS5.value, "instId": okx_symbol}]
                )

        self._orderbook_subscriptions.discard(normalized_symbol)

    # ==================== Private Channel Subscriptions ====================

    async def subscribe_orders(self, inst_type: str = "SPOT") -> None:
        """Subscribe to order updates (private channel).

        Args:
            inst_type: Instrument type (SPOT, MARGIN, SWAP, FUTURES, OPTION).
        """
        if self._settings.use_ccxt_provider:
            if not self._ccxt_provider:
                raise RuntimeError("CCXT provider not started. Call start() first.")
            # CCXT watches all orders by default
            await self._ccxt_provider.watch_orders()
            logger.info("Subscribed to orders via CCXT")
        else:
            if not self._private_client:
                await self.start_private()

            if not self._private_client:
                raise RuntimeError("Private client not available (credentials missing)")

            await self._private_client.subscribe(
                [{"channel": OKXChannel.ORDERS.value, "instType": inst_type}]
            )
            logger.info(f"Subscribed to orders: {inst_type}")

    async def subscribe_account(self) -> None:
        """Subscribe to account balance updates (private channel)."""
        if self._settings.use_ccxt_provider:
            if not self._ccxt_provider:
                raise RuntimeError("CCXT provider not started. Call start() first.")
            await self._ccxt_provider.watch_balance()
            logger.info("Subscribed to account updates via CCXT")
        else:
            if not self._private_client:
                await self.start_private()

            if not self._private_client:
                raise RuntimeError("Private client not available (credentials missing)")

            await self._private_client.subscribe([{"channel": OKXChannel.ACCOUNT.value}])
            logger.info("Subscribed to account updates")

    # ==================== Message Handlers ====================

    async def _handle_public_message(self, msg: dict[str, Any]) -> None:
        """Handle messages from public WebSocket."""
        try:
            arg = msg.get("arg", {})
            channel = arg.get("channel", "")
            data = msg.get("data", [])

            if not data:
                return

            if channel == OKXChannel.TICKERS.value:
                await self._process_ticker(arg, data)
            elif channel.startswith("candle"):
                await self._process_candle(arg, data, channel)
            elif channel == OKXChannel.TRADES.value:
                await self._process_trades(arg, data)
            elif channel == OKXChannel.BOOKS5.value:
                await self._process_orderbook(arg, data)

        except Exception as e:
            logger.exception(f"Error processing public message: {e}")

    async def _handle_private_message(self, msg: dict[str, Any]) -> None:
        """Handle messages from private WebSocket."""
        try:
            arg = msg.get("arg", {})
            channel = arg.get("channel", "")
            data = msg.get("data", [])

            if not data:
                return

            if channel == OKXChannel.ORDERS.value:
                await self._process_orders(data)
            elif channel == OKXChannel.ACCOUNT.value:
                await self._process_account(data)

        except Exception as e:
            logger.exception(f"Error processing private message: {e}")

    async def _handle_ccxt_message(self, msg: dict[str, Any]) -> None:
        """Handle messages from CCXT provider.

        CCXT provider sends messages in the format:
        {"type": "ticker|candle|trade|orderbook|order|account", "data": <WS* model>}
        """
        try:
            data_type = msg.get("type", "")
            data = msg.get("data")

            if not data:
                logger.warning(f"_handle_ccxt_message: no data for type={data_type}")
                return

            if data_type == "ticker":
                ticker: WSTicker = data
                await self._publish(
                    WSMessageType.TICKER,
                    f"ticker:{ticker.symbol}",
                    ticker.model_dump(mode="json"),
                )

            elif data_type == "candle":
                candle: WSCandle = data
                # Publish to Redis for WebSocket clients
                channel = f"candle:{candle.symbol}:{candle.timeframe}"
                await self._publish(
                    WSMessageType.CANDLE,
                    channel,
                    candle.model_dump(mode="json"),
                )

                # Dispatch to paper trading sessions
                from squant.engine.paper.manager import get_session_manager

                session_manager = get_session_manager()
                await session_manager.dispatch_candle(candle)

            elif data_type == "trade":
                trade: WSTrade = data
                await self._publish(
                    WSMessageType.TRADE,
                    f"trade:{trade.symbol}",
                    trade.model_dump(mode="json"),
                )

            elif data_type == "orderbook":
                orderbook: WSOrderBook = data
                await self._publish(
                    WSMessageType.ORDERBOOK,
                    f"orderbook:{orderbook.symbol}",
                    orderbook.model_dump(mode="json"),
                )

            elif data_type == "order":
                order: WSOrderUpdate = data
                await self._publish(
                    WSMessageType.ORDER_UPDATE,
                    "orders",
                    order.model_dump(mode="json"),
                )

            elif data_type == "account":
                account: WSAccountUpdate = data
                await self._publish(
                    WSMessageType.ACCOUNT_UPDATE,
                    "account",
                    account.model_dump(mode="json"),
                )

        except Exception as e:
            logger.exception(f"Error processing CCXT message: {e}")

    async def _process_ticker(self, arg: dict, data: list) -> None:
        """Process ticker data and publish to Redis."""
        for item in data:
            symbol = self._from_okx_symbol(item.get("instId", ""))

            ticker = WSTicker(
                symbol=symbol,
                last=Decimal(item.get("last", "0")),
                bid=Decimal(item["bidPx"]) if item.get("bidPx") else None,
                ask=Decimal(item["askPx"]) if item.get("askPx") else None,
                bid_size=Decimal(item["bidSz"]) if item.get("bidSz") else None,
                ask_size=Decimal(item["askSz"]) if item.get("askSz") else None,
                high_24h=Decimal(item["high24h"]) if item.get("high24h") else None,
                low_24h=Decimal(item["low24h"]) if item.get("low24h") else None,
                volume_24h=Decimal(item["vol24h"]) if item.get("vol24h") else None,
                volume_quote_24h=Decimal(item["volCcy24h"]) if item.get("volCcy24h") else None,
                open_24h=Decimal(item["open24h"]) if item.get("open24h") else None,
                timestamp=self._parse_timestamp(item.get("ts")),
            )

            await self._publish(
                WSMessageType.TICKER,
                f"ticker:{symbol}",
                ticker.model_dump(mode="json"),
            )

    async def _process_candle(self, arg: dict, data: list, channel: str) -> None:
        """Process candlestick data and publish to Redis."""
        symbol = self._from_okx_symbol(arg.get("instId", ""))

        # Extract timeframe from channel (e.g., "candle1m" -> "1m")
        timeframe = channel.replace("candle", "").lower()
        logger.debug(
            f"Processing candle data: symbol={symbol}, timeframe={timeframe}, count={len(data)}"
        )

        for item in data:
            # OKX candle format: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
            if len(item) >= 9:
                candle = WSCandle(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=self._parse_timestamp(item[0]),
                    open=Decimal(item[1]),
                    high=Decimal(item[2]),
                    low=Decimal(item[3]),
                    close=Decimal(item[4]),
                    volume=Decimal(item[5]),
                    volume_quote=Decimal(item[7]) if item[7] else None,
                    is_closed=item[8] == "1",
                )

                # Publish to Redis for WebSocket clients
                await self._publish(
                    WSMessageType.CANDLE,
                    f"candle:{symbol}:{timeframe}",
                    candle.model_dump(mode="json"),
                )

                # Dispatch to paper trading sessions
                from squant.engine.paper.manager import get_session_manager

                session_manager = get_session_manager()
                await session_manager.dispatch_candle(candle)

    async def _process_trades(self, arg: dict, data: list) -> None:
        """Process trade data and publish to Redis."""
        symbol = self._from_okx_symbol(arg.get("instId", ""))

        for item in data:
            trade = WSTrade(
                symbol=symbol,
                trade_id=item.get("tradeId", ""),
                price=Decimal(item.get("px", "0")),
                size=Decimal(item.get("sz", "0")),
                side=item.get("side", "").lower(),
                timestamp=self._parse_timestamp(item.get("ts")),
            )

            await self._publish(
                WSMessageType.TRADE,
                f"trade:{symbol}",
                trade.model_dump(mode="json"),
            )

    async def _process_orderbook(self, arg: dict, data: list) -> None:
        """Process order book data and publish to Redis."""
        symbol = self._from_okx_symbol(arg.get("instId", ""))

        for item in data:
            bids = [
                WSOrderBookLevel(
                    price=Decimal(b[0]),
                    size=Decimal(b[1]),
                    num_orders=int(b[3]) if len(b) > 3 else None,
                )
                for b in item.get("bids", [])
            ]

            asks = [
                WSOrderBookLevel(
                    price=Decimal(a[0]),
                    size=Decimal(a[1]),
                    num_orders=int(a[3]) if len(a) > 3 else None,
                )
                for a in item.get("asks", [])
            ]

            orderbook = WSOrderBook(
                symbol=symbol,
                bids=bids,
                asks=asks,
                timestamp=self._parse_timestamp(item.get("ts")),
                checksum=int(item["checksum"]) if item.get("checksum") else None,
            )

            await self._publish(
                WSMessageType.ORDERBOOK,
                f"orderbook:{symbol}",
                orderbook.model_dump(mode="json"),
            )

    async def _process_orders(self, data: list) -> None:
        """Process order updates and publish to Redis."""
        for item in data:
            symbol = self._from_okx_symbol(item.get("instId", ""))

            order = WSOrderUpdate(
                order_id=item.get("ordId", ""),
                client_order_id=item.get("clOrdId") or None,
                symbol=symbol,
                side=item.get("side", "").lower(),
                order_type=item.get("ordType", "").lower(),
                status=self._map_order_status(item.get("state", "")),
                price=Decimal(item["px"]) if item.get("px") else None,
                size=Decimal(item.get("sz", "0")),
                filled_size=Decimal(item.get("fillSz", "0")),
                avg_price=Decimal(item["avgPx"]) if item.get("avgPx") else None,
                fee=Decimal(item["fee"]) if item.get("fee") else None,
                fee_currency=item.get("feeCcy") or None,
                created_at=self._parse_timestamp(item.get("cTime")),
                updated_at=self._parse_timestamp(item.get("uTime")),
            )

            await self._publish(
                WSMessageType.ORDER_UPDATE,
                "orders",
                order.model_dump(mode="json"),
            )

    async def _process_account(self, data: list) -> None:
        """Process account balance updates and publish to Redis."""
        for item in data:
            balances = []
            for detail in item.get("details", []):
                balances.append(
                    WSBalanceUpdate(
                        currency=detail.get("ccy", ""),
                        available=Decimal(detail.get("availBal", "0")),
                        frozen=Decimal(detail.get("frozenBal", "0")),
                    )
                )

            account = WSAccountUpdate(
                balances=balances,
                timestamp=self._parse_timestamp(item.get("uTime")),
            )

            await self._publish(
                WSMessageType.ACCOUNT_UPDATE,
                "account",
                account.model_dump(mode="json"),
            )

    # ==================== Helper Methods ====================

    async def _publish_service_ready(self) -> None:
        """Publish service_ready event to notify clients that the stream manager is ready.

        Clients receiving this can re-subscribe to OKX channels that may have
        failed during stream manager downtime.
        """
        await self._publish(
            WSMessageType.SERVICE_READY,
            "system",
            {"status": "ready"},
        )

    async def _publish_exchange_switching(
        self, from_exchange: str, to_exchange: str, status: str
    ) -> None:
        """Publish exchange switching status to clients.

        Args:
            from_exchange: Previous exchange ID.
            to_exchange: New exchange ID.
            status: Switch status ('switching' or 'completed').
        """
        await self._publish(
            WSMessageType.EXCHANGE_SWITCHING,
            "system",
            {
                "from": from_exchange,
                "to": to_exchange,
                "status": status,
            },
        )

    async def _publish(self, msg_type: WSMessageType, channel: str, data: dict) -> None:
        """Queue message for batch publishing to Redis.

        Args:
            msg_type: Message type.
            channel: Channel name (without prefix).
            data: Message data.
        """
        if not self._redis:
            logger.warning("Redis not available, message dropped")
            return

        message = WSMessage(
            type=msg_type,
            channel=channel,
            data=data,
        )

        redis_channel = f"{self.REDIS_CHANNEL_PREFIX}{channel}"
        message_json = message.model_dump_json()

        # Add to buffer
        async with self._buffer_lock:
            self._publish_buffer.append((redis_channel, message_json))

            # Force flush if buffer is too large
            if len(self._publish_buffer) >= self.MAX_BUFFER_SIZE:
                await self._flush_buffer_unsafe()

    async def _flush_loop(self) -> None:
        """Background task that periodically flushes the message buffer."""
        while self._running:
            try:
                await asyncio.sleep(self.FLUSH_INTERVAL)
                await self._flush_buffer()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Error in flush loop: {e}")

    async def _stats_loop(self) -> None:
        """Background task that periodically logs throughput statistics."""
        while self._running:
            try:
                await asyncio.sleep(self._stats_interval)
                # Safe without lock: asyncio single-threaded event loop,
                # no await between read and reset so no interleaving possible.
                msgs = self._stats_messages_published
                flushes = self._stats_flushes
                self._stats_messages_published = 0
                self._stats_flushes = 0
                if msgs > 0:
                    logger.info(
                        f"Stream throughput: {msgs} msgs in {flushes} flushes "
                        f"({msgs / self._stats_interval:.1f} msgs/s), "
                        f"subscriptions: {len(self._ticker_subscriptions)} tickers, "
                        f"{len(self._candle_subscriptions)} candles"
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Error in stats loop: {e}")

    async def _flush_buffer(self) -> None:
        """Flush the message buffer using Redis pipeline."""
        async with self._buffer_lock:
            await self._flush_buffer_unsafe()

    async def _flush_buffer_unsafe(self) -> None:
        """Flush buffer without acquiring lock (caller must hold lock).

        Note: If Redis publish fails, messages are dropped intentionally.
        For real-time market data, this is the correct behavior because:
        1. Stale market data is worse than no data
        2. New data arrives within milliseconds
        3. Buffering failed messages could cause memory issues if Redis is down
        """
        if not self._publish_buffer or not self._redis:
            return

        # Collect all messages from buffer
        messages = []
        while self._publish_buffer:
            messages.append(self._publish_buffer.popleft())

        if not messages:
            return

        # Use pipeline to batch publish all messages
        try:
            async with self._redis.pipeline(transaction=False) as pipe:
                for channel, message_json in messages:
                    pipe.publish(channel, message_json)
                await pipe.execute()
            self._stats_messages_published += len(messages)
            self._stats_flushes += 1
        except Exception as e:
            # Log dropped messages for monitoring, but don't retry
            # (stale market data is worse than no data)
            logger.warning(f"Dropped {len(messages)} messages due to Redis error: {e}")

    async def _health_check_loop(self) -> None:
        """Background task that periodically checks connection health.

        If the connection is unhealthy, attempts to recover by triggering
        reconnection in the CCXT provider.
        """
        consecutive_unhealthy = 0
        max_unhealthy_before_action = 2  # Allow 2 unhealthy checks before action

        while self._running:
            try:
                await asyncio.sleep(self._health_check_interval)

                if not self._running:
                    break

                if self.is_healthy:
                    consecutive_unhealthy = 0
                    logger.debug("Stream manager health check: OK")
                else:
                    consecutive_unhealthy += 1
                    logger.warning(
                        f"Stream manager health check: UNHEALTHY "
                        f"(consecutive: {consecutive_unhealthy})"
                    )

                    if consecutive_unhealthy >= max_unhealthy_before_action:
                        logger.error(
                            "Stream manager unhealthy for too long, attempting recovery..."
                        )
                        recovered = await self._attempt_recovery()
                        if recovered:
                            consecutive_unhealthy = 0
                        else:
                            # Keep counting so next check triggers another attempt immediately
                            logger.warning("Recovery failed, will retry on next health check")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Error in health check loop: {e}")

    async def _attempt_recovery(self) -> bool:
        """Attempt to recover from an unhealthy state.

        For CCXT provider mode, triggers a reconnection attempt.
        For native OKX mode, attempts to reconnect the clients.

        Returns:
            True if recovery was successful, False otherwise.
        """
        if self._settings.use_ccxt_provider:
            if self._ccxt_provider and hasattr(self._ccxt_provider, "reconnect"):
                logger.info("Triggering CCXT provider reconnection...")
                success = await self._ccxt_provider.reconnect()
                if success:
                    logger.info("CCXT provider reconnection successful")
                    await self._publish_service_ready()
                    return True
                else:
                    logger.error("CCXT provider reconnection failed")
                    return False
            return False
        else:
            # Native OKX mode - try to reconnect clients
            logger.info("Attempting to reconnect native OKX clients...")
            try:
                if self._public_client and not self._public_client.is_connected:
                    await self._public_client.connect()
                if self._business_client and not self._business_client.is_connected:
                    await self._business_client.connect()
                logger.info("Native OKX clients reconnection attempted")
                await self._publish_service_ready()
                return True
            except Exception as e:
                logger.exception(f"Failed to reconnect native OKX clients: {e}")
                return False

    def _to_okx_symbol(self, symbol: str) -> str:
        """Convert standard symbol to OKX format.

        Args:
            symbol: Standard format (e.g., "BTC/USDT").

        Returns:
            OKX format (e.g., "BTC-USDT").
        """
        return symbol.replace("/", "-")

    def _from_okx_symbol(self, symbol: str) -> str:
        """Convert OKX symbol to standard format.

        Args:
            symbol: OKX format (e.g., "BTC-USDT").

        Returns:
            Standard format (e.g., "BTC/USDT").
        """
        return symbol.replace("-", "/")

    def _normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol to standard format (using '/').

        CCXT uses '/' separator, OKX uses '-'. This method normalizes
        both formats to the standard '/' format used internally.

        Args:
            symbol: Symbol in either format (e.g., "BTC/USDT" or "BTC-USDT").

        Returns:
            Standard format (e.g., "BTC/USDT").
        """
        return symbol.replace("-", "/")

    def _parse_timestamp(self, ts: str | None) -> datetime:
        """Parse OKX timestamp (milliseconds) to datetime.

        Args:
            ts: Timestamp in milliseconds as string.

        Returns:
            Datetime object.
        """
        if not ts:
            return datetime.now(UTC)
        return datetime.fromtimestamp(int(ts) / 1000, tz=UTC)

    def _map_order_status(self, status: str) -> str:
        """Map OKX order status to internal status.

        Args:
            status: OKX order status.

        Returns:
            Internal order status.
        """
        status_map = {
            "live": "submitted",
            "partially_filled": "partial",
            "filled": "filled",
            "canceled": "cancelled",
            "mmp_canceled": "cancelled",
        }
        return status_map.get(status.lower(), status.lower())


# Global stream manager instance
_stream_manager: StreamManager | None = None


def get_stream_manager() -> StreamManager:
    """Get global stream manager instance."""
    global _stream_manager
    if _stream_manager is None:
        _stream_manager = StreamManager()
    return _stream_manager


async def init_stream_manager() -> None:
    """Initialize and start stream manager (for startup)."""
    manager = get_stream_manager()
    await manager.start()


async def close_stream_manager() -> None:
    """Stop and cleanup stream manager (for shutdown)."""
    global _stream_manager
    if _stream_manager is not None:
        await _stream_manager.stop()
        _stream_manager = None
