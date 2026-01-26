"""Stream manager for WebSocket data distribution via Redis pub/sub."""

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from redis.asyncio import Redis

from squant.config import get_settings
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

    def __init__(self) -> None:
        """Initialize stream manager."""
        self._public_client: OKXWebSocketClient | None = None
        self._private_client: OKXWebSocketClient | None = None
        self._redis: Redis | None = None
        self._running = False
        self._settings = get_settings()

        # Track active subscriptions
        self._ticker_subscriptions: set[str] = set()
        self._candle_subscriptions: set[tuple[str, str]] = set()  # (symbol, timeframe)
        self._trade_subscriptions: set[str] = set()
        self._orderbook_subscriptions: set[str] = set()

    @property
    def is_running(self) -> bool:
        """Check if stream manager is running."""
        return self._running

    async def start(self) -> None:
        """Start the public WebSocket connection."""
        if self._running:
            logger.debug("Stream manager already running")
            return

        logger.info("Starting stream manager...")

        # Get Redis client (initialized at app startup)
        self._redis = get_redis_client()

        # Initialize public WebSocket client
        self._public_client = OKXWebSocketClient(
            testnet=self._settings.okx_testnet,
            private=False,
        )
        self._public_client.add_handler(self._handle_public_message)

        await self._public_client.connect()
        self._running = True
        logger.info("Stream manager started (public channels)")

    async def start_private(self) -> None:
        """Start the private WebSocket connection (requires credentials)."""
        if not all([
            self._settings.okx_api_key,
            self._settings.okx_api_secret,
            self._settings.okx_passphrase,
        ]):
            logger.warning("OKX credentials not configured, private channels unavailable")
            return

        logger.info("Starting private WebSocket connection...")

        # Get Redis client if not already set
        if self._redis is None:
            self._redis = get_redis_client()

        # Initialize private WebSocket client
        self._private_client = OKXWebSocketClient(
            api_key=self._settings.okx_api_key.get_secret_value() if self._settings.okx_api_key else None,
            api_secret=self._settings.okx_api_secret.get_secret_value() if self._settings.okx_api_secret else None,
            passphrase=self._settings.okx_passphrase.get_secret_value() if self._settings.okx_passphrase else None,
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

        if self._public_client:
            await self._public_client.close()
            self._public_client = None

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
        okx_symbol = self._to_okx_symbol(symbol)

        if okx_symbol in self._ticker_subscriptions:
            logger.debug(f"Already subscribed to ticker: {okx_symbol}")
            return

        if not self._public_client:
            raise RuntimeError("Public client not started. Call start() first.")

        await self._public_client.subscribe([
            {"channel": OKXChannel.TICKERS.value, "instId": okx_symbol}
        ])
        self._ticker_subscriptions.add(okx_symbol)
        logger.info(f"Subscribed to ticker: {okx_symbol}")

    async def unsubscribe_ticker(self, symbol: str) -> None:
        """Unsubscribe from ticker updates."""
        okx_symbol = self._to_okx_symbol(symbol)

        if okx_symbol not in self._ticker_subscriptions:
            return

        if self._public_client:
            await self._public_client.unsubscribe([
                {"channel": OKXChannel.TICKERS.value, "instId": okx_symbol}
            ])
        self._ticker_subscriptions.discard(okx_symbol)

    async def subscribe_candles(self, symbol: str, timeframe: str = "1m") -> None:
        """Subscribe to candlestick updates.

        Args:
            symbol: Trading pair.
            timeframe: Candle timeframe (1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w).
        """
        okx_symbol = self._to_okx_symbol(symbol)
        key = (okx_symbol, timeframe)

        if key in self._candle_subscriptions:
            logger.debug(f"Already subscribed to candles: {okx_symbol} {timeframe}")
            return

        if not self._public_client:
            raise RuntimeError("Public client not started. Call start() first.")

        channel = CANDLE_CHANNELS.get(timeframe.lower())
        if not channel:
            raise ValueError(f"Invalid timeframe: {timeframe}")

        await self._public_client.subscribe([
            {"channel": channel.value, "instId": okx_symbol}
        ])
        self._candle_subscriptions.add(key)
        logger.info(f"Subscribed to candles: {okx_symbol} {timeframe}")

    async def unsubscribe_candles(self, symbol: str, timeframe: str = "1m") -> None:
        """Unsubscribe from candlestick updates."""
        okx_symbol = self._to_okx_symbol(symbol)
        key = (okx_symbol, timeframe)

        if key not in self._candle_subscriptions:
            return

        if self._public_client:
            channel = CANDLE_CHANNELS.get(timeframe.lower())
            if channel:
                await self._public_client.unsubscribe([
                    {"channel": channel.value, "instId": okx_symbol}
                ])
        self._candle_subscriptions.discard(key)

    async def subscribe_trades(self, symbol: str) -> None:
        """Subscribe to trade updates for a symbol."""
        okx_symbol = self._to_okx_symbol(symbol)

        if okx_symbol in self._trade_subscriptions:
            return

        if not self._public_client:
            raise RuntimeError("Public client not started. Call start() first.")

        await self._public_client.subscribe([
            {"channel": OKXChannel.TRADES.value, "instId": okx_symbol}
        ])
        self._trade_subscriptions.add(okx_symbol)
        logger.info(f"Subscribed to trades: {okx_symbol}")

    async def unsubscribe_trades(self, symbol: str) -> None:
        """Unsubscribe from trade updates."""
        okx_symbol = self._to_okx_symbol(symbol)

        if okx_symbol not in self._trade_subscriptions:
            return

        if self._public_client:
            await self._public_client.unsubscribe([
                {"channel": OKXChannel.TRADES.value, "instId": okx_symbol}
            ])
        self._trade_subscriptions.discard(okx_symbol)

    async def subscribe_orderbook(self, symbol: str) -> None:
        """Subscribe to order book updates (5-level depth)."""
        okx_symbol = self._to_okx_symbol(symbol)

        if okx_symbol in self._orderbook_subscriptions:
            return

        if not self._public_client:
            raise RuntimeError("Public client not started. Call start() first.")

        await self._public_client.subscribe([
            {"channel": OKXChannel.BOOKS5.value, "instId": okx_symbol}
        ])
        self._orderbook_subscriptions.add(okx_symbol)
        logger.info(f"Subscribed to orderbook: {okx_symbol}")

    async def unsubscribe_orderbook(self, symbol: str) -> None:
        """Unsubscribe from order book updates."""
        okx_symbol = self._to_okx_symbol(symbol)

        if okx_symbol not in self._orderbook_subscriptions:
            return

        if self._public_client:
            await self._public_client.unsubscribe([
                {"channel": OKXChannel.BOOKS5.value, "instId": okx_symbol}
            ])
        self._orderbook_subscriptions.discard(okx_symbol)

    # ==================== Private Channel Subscriptions ====================

    async def subscribe_orders(self, inst_type: str = "SPOT") -> None:
        """Subscribe to order updates (private channel).

        Args:
            inst_type: Instrument type (SPOT, MARGIN, SWAP, FUTURES, OPTION).
        """
        if not self._private_client:
            await self.start_private()

        if not self._private_client:
            raise RuntimeError("Private client not available (credentials missing)")

        await self._private_client.subscribe([
            {"channel": OKXChannel.ORDERS.value, "instType": inst_type}
        ])
        logger.info(f"Subscribed to orders: {inst_type}")

    async def subscribe_account(self) -> None:
        """Subscribe to account balance updates (private channel)."""
        if not self._private_client:
            await self.start_private()

        if not self._private_client:
            raise RuntimeError("Private client not available (credentials missing)")

        await self._private_client.subscribe([
            {"channel": OKXChannel.ACCOUNT.value}
        ])
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
                balances.append(WSBalanceUpdate(
                    currency=detail.get("ccy", ""),
                    available=Decimal(detail.get("availBal", "0")),
                    frozen=Decimal(detail.get("frozenBal", "0")),
                ))

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

    async def _publish(self, msg_type: WSMessageType, channel: str, data: dict) -> None:
        """Publish message to Redis pub/sub channel.

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
        await self._redis.publish(redis_channel, message.model_dump_json())

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
