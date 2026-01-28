"""CCXT Stream Provider for multi-exchange real-time data."""

import asyncio
import contextlib
import logging
from collections.abc import Callable, Coroutine
from typing import Any

import ccxt.pro as ccxtpro

from squant.infra.exchange.ccxt.transformer import CCXTDataTransformer
from squant.infra.exchange.ccxt.types import (
    SUPPORTED_EXCHANGES,
    TIMEFRAME_MAP,
    ExchangeCredentials,
)
from squant.infra.exchange.exceptions import (
    ExchangeAuthenticationError,
    ExchangeConnectionError,
)
from squant.infra.exchange.okx.ws_types import (
    WSAccountUpdate,
    WSCandle,
    WSOrderBook,
    WSOrderUpdate,
    WSTicker,
    WSTrade,
)

logger = logging.getLogger(__name__)

# Type alias for message handlers
MessageHandler = Callable[[Any], Coroutine[Any, Any, None]]


class CCXTStreamProvider:
    """CCXT-based stream provider for multi-exchange support.

    This provider wraps ccxt.pro's watch_* methods to provide real-time
    data streams from supported exchanges. Data is transformed to internal
    types (WSTicker, WSCandle, etc.) for compatibility with the rest of the system.

    Supported exchanges:
    - OKX
    - Binance
    - Bybit

    Example:
        provider = CCXTStreamProvider("okx", credentials)
        await provider.connect()
        provider.add_handler(my_handler)
        await provider.watch_ticker("BTC/USDT")
    """

    def __init__(
        self,
        exchange_id: str,
        credentials: ExchangeCredentials | None = None,
    ) -> None:
        """Initialize CCXT stream provider.

        Args:
            exchange_id: Exchange identifier (okx, binance, bybit).
            credentials: Optional API credentials for private channels.

        Raises:
            ValueError: If exchange is not supported.
        """
        if exchange_id.lower() not in SUPPORTED_EXCHANGES:
            raise ValueError(
                f"Unsupported exchange: {exchange_id}. "
                f"Supported: {', '.join(SUPPORTED_EXCHANGES)}"
            )

        self._exchange_id = exchange_id.lower()
        self._credentials = credentials
        self._exchange: Any = None
        self._connected = False
        self._running = False

        # Message handlers
        self._handlers: list[MessageHandler] = []

        # Active subscription tasks
        self._subscription_tasks: dict[str, asyncio.Task[None]] = {}

        # Transformer for data conversion
        self._transformer = CCXTDataTransformer()

    @property
    def exchange_id(self) -> str:
        """Get the exchange identifier."""
        return self._exchange_id

    @property
    def is_connected(self) -> bool:
        """Check if connected to exchange."""
        return self._connected and self._exchange is not None

    async def connect(self) -> None:
        """Establish connection to the exchange.

        This initializes the CCXT exchange instance. Actual WebSocket connections
        are established lazily when subscribing to channels.
        """
        if self._connected:
            logger.debug(f"Already connected to {self._exchange_id}")
            return

        try:
            logger.info(f"Connecting to {self._exchange_id} via CCXT...")

            # Build exchange configuration
            config: dict[str, Any] = {
                "enableRateLimit": True,
            }

            # Add credentials if provided
            if self._credentials:
                config["apiKey"] = self._credentials.api_key
                config["secret"] = self._credentials.api_secret
                if self._credentials.passphrase:
                    config["password"] = self._credentials.passphrase
                if self._credentials.sandbox:
                    config["sandbox"] = True

            # Create exchange instance
            exchange_class = getattr(ccxtpro, self._exchange_id, None)
            if exchange_class is None:
                raise ExchangeConnectionError(
                    message=f"Exchange {self._exchange_id} not found in ccxt.pro",
                    exchange=self._exchange_id,
                )

            self._exchange = exchange_class(config)

            # Load markets (required before using watch_* methods)
            logger.info(f"Loading markets for {self._exchange_id}...")
            await self._exchange.load_markets()
            logger.info(f"Markets loaded for {self._exchange_id}")

            self._connected = True
            self._running = True

            logger.info(f"Connected to {self._exchange_id} via CCXT")

        except Exception as e:
            raise ExchangeConnectionError(
                message=f"Failed to connect to {self._exchange_id}: {e}",
                exchange=self._exchange_id,
            ) from e

    async def close(self) -> None:
        """Close connection and cleanup resources."""
        logger.info(f"Closing {self._exchange_id} connection...")
        self._running = False

        # Cancel all subscription tasks
        for key, task in list(self._subscription_tasks.items()):
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            del self._subscription_tasks[key]

        # Close exchange connection
        if self._exchange:
            try:
                await self._exchange.close()
            except Exception as e:
                logger.warning(f"Error closing exchange: {e}")
            self._exchange = None

        self._connected = False
        logger.info(f"Closed {self._exchange_id} connection")

    def add_handler(self, handler: MessageHandler) -> None:
        """Add a message handler.

        Args:
            handler: Async function to handle incoming data.
        """
        if handler not in self._handlers:
            self._handlers.append(handler)

    def remove_handler(self, handler: MessageHandler) -> None:
        """Remove a message handler.

        Args:
            handler: Handler to remove.
        """
        if handler in self._handlers:
            self._handlers.remove(handler)

    # ==================== Public Channel Subscriptions ====================

    async def watch_ticker(self, symbol: str) -> None:
        """Subscribe to ticker updates for a symbol.

        Args:
            symbol: Trading pair (e.g., "BTC/USDT").
        """
        key = f"ticker:{symbol}"
        if key in self._subscription_tasks:
            logger.debug(f"Already watching ticker: {symbol}")
            return

        task = asyncio.create_task(self._ticker_loop(symbol))
        self._subscription_tasks[key] = task
        logger.info(f"Started watching ticker: {symbol}")

    async def watch_ohlcv(self, symbol: str, timeframe: str = "1m") -> None:
        """Subscribe to OHLCV/candlestick updates.

        Args:
            symbol: Trading pair (e.g., "BTC/USDT").
            timeframe: Candle timeframe (1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w).
        """
        ccxt_timeframe = TIMEFRAME_MAP.get(timeframe.lower())
        if not ccxt_timeframe:
            raise ValueError(f"Invalid timeframe: {timeframe}")

        key = f"ohlcv:{symbol}:{timeframe}"
        if key in self._subscription_tasks:
            logger.debug(f"Already watching OHLCV: {symbol} {timeframe}")
            return

        task = asyncio.create_task(self._ohlcv_loop(symbol, ccxt_timeframe, timeframe))
        self._subscription_tasks[key] = task
        logger.info(f"Started watching OHLCV: {symbol} {timeframe}")

    async def watch_trades(self, symbol: str) -> None:
        """Subscribe to trade updates for a symbol.

        Args:
            symbol: Trading pair (e.g., "BTC/USDT").
        """
        key = f"trades:{symbol}"
        if key in self._subscription_tasks:
            logger.debug(f"Already watching trades: {symbol}")
            return

        task = asyncio.create_task(self._trades_loop(symbol))
        self._subscription_tasks[key] = task
        logger.info(f"Started watching trades: {symbol}")

    async def watch_order_book(self, symbol: str, limit: int = 5) -> None:
        """Subscribe to order book updates.

        Args:
            symbol: Trading pair (e.g., "BTC/USDT").
            limit: Number of order book levels.
        """
        key = f"orderbook:{symbol}"
        if key in self._subscription_tasks:
            logger.debug(f"Already watching order book: {symbol}")
            return

        task = asyncio.create_task(self._orderbook_loop(symbol, limit))
        self._subscription_tasks[key] = task
        logger.info(f"Started watching order book: {symbol}")

    # ==================== Private Channel Subscriptions ====================

    async def watch_orders(self, symbol: str | None = None) -> None:
        """Subscribe to order updates (private channel).

        Args:
            symbol: Optional symbol filter. None for all orders.
        """
        if not self._credentials:
            raise ExchangeAuthenticationError(
                message="Credentials required for private channels",
                exchange=self._exchange_id,
            )

        key = f"orders:{symbol or 'all'}"
        if key in self._subscription_tasks:
            logger.debug(f"Already watching orders: {symbol or 'all'}")
            return

        task = asyncio.create_task(self._orders_loop(symbol))
        self._subscription_tasks[key] = task
        logger.info(f"Started watching orders: {symbol or 'all'}")

    async def watch_balance(self) -> None:
        """Subscribe to balance updates (private channel)."""
        if not self._credentials:
            raise ExchangeAuthenticationError(
                message="Credentials required for private channels",
                exchange=self._exchange_id,
            )

        key = "balance"
        if key in self._subscription_tasks:
            logger.debug("Already watching balance")
            return

        task = asyncio.create_task(self._balance_loop())
        self._subscription_tasks[key] = task
        logger.info("Started watching balance")

    # ==================== Unsubscribe ====================

    async def unwatch(self, subscription_key: str) -> None:
        """Unsubscribe from a channel.

        Args:
            subscription_key: Subscription key (e.g., "ticker:BTC/USDT").
        """
        if subscription_key in self._subscription_tasks:
            task = self._subscription_tasks.pop(subscription_key)
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            logger.info(f"Unwatched: {subscription_key}")

    # ==================== Watch Loops ====================

    async def _ticker_loop(self, symbol: str) -> None:
        """Background loop for ticker updates."""
        while self._running:
            try:
                if not self._exchange:
                    await asyncio.sleep(1)
                    continue

                ticker = await self._exchange.watch_ticker(symbol)
                ws_ticker = self._transformer.ticker_to_ws_ticker(ticker)
                await self._dispatch("ticker", ws_ticker)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Error in ticker loop for {symbol}: {e}")
                await asyncio.sleep(1)

    async def _ohlcv_loop(self, symbol: str, ccxt_timeframe: str, timeframe: str) -> None:
        """Background loop for OHLCV/candle updates."""
        logger.info(f"OHLCV loop started for {symbol} {timeframe}")
        while self._running:
            try:
                if not self._exchange:
                    await asyncio.sleep(1)
                    continue

                logger.debug(f"Calling watch_ohlcv for {symbol} {ccxt_timeframe}")
                ohlcv_list = await self._exchange.watch_ohlcv(symbol, ccxt_timeframe)
                logger.info(f"Received {len(ohlcv_list)} OHLCV candles for {symbol} {timeframe}")

                # Process each candle (usually just the latest)
                for ohlcv in ohlcv_list[-1:]:  # Only process the latest
                    # Determine if candle is closed based on timestamp
                    # This is a heuristic - CCXT doesn't always provide is_closed
                    ws_candle = self._transformer.ohlcv_to_ws_candle(
                        ohlcv, symbol, timeframe, is_closed=False
                    )
                    await self._dispatch("candle", ws_candle)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Error in OHLCV loop for {symbol}: {e}")
                await asyncio.sleep(1)

    async def _trades_loop(self, symbol: str) -> None:
        """Background loop for trade updates."""
        while self._running:
            try:
                if not self._exchange:
                    await asyncio.sleep(1)
                    continue

                trades = await self._exchange.watch_trades(symbol)

                for trade in trades:
                    ws_trade = self._transformer.trade_to_ws_trade(trade)
                    await self._dispatch("trade", ws_trade)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Error in trades loop for {symbol}: {e}")
                await asyncio.sleep(1)

    async def _orderbook_loop(self, symbol: str, limit: int) -> None:
        """Background loop for order book updates."""
        while self._running:
            try:
                if not self._exchange:
                    await asyncio.sleep(1)
                    continue

                orderbook = await self._exchange.watch_order_book(symbol, limit)
                ws_orderbook = self._transformer.orderbook_to_ws_orderbook(
                    orderbook, symbol, limit
                )
                await self._dispatch("orderbook", ws_orderbook)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Error in orderbook loop for {symbol}: {e}")
                await asyncio.sleep(1)

    async def _orders_loop(self, symbol: str | None) -> None:
        """Background loop for order updates."""
        while self._running:
            try:
                if not self._exchange:
                    await asyncio.sleep(1)
                    continue

                orders = await self._exchange.watch_orders(symbol)

                for order in orders:
                    ws_order = self._transformer.order_to_ws_order_update(order)
                    await self._dispatch("order", ws_order)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Error in orders loop: {e}")
                await asyncio.sleep(1)

    async def _balance_loop(self) -> None:
        """Background loop for balance updates."""
        while self._running:
            try:
                if not self._exchange:
                    await asyncio.sleep(1)
                    continue

                balance = await self._exchange.watch_balance()
                ws_balance = self._transformer.balance_to_ws_account_update(balance)
                await self._dispatch("account", ws_balance)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Error in balance loop: {e}")
                await asyncio.sleep(1)

    # ==================== Dispatch ====================

    async def _dispatch(
        self,
        data_type: str,
        data: WSTicker | WSCandle | WSTrade | WSOrderBook | WSOrderUpdate | WSAccountUpdate,
    ) -> None:
        """Dispatch data to all registered handlers.

        Args:
            data_type: Type of data (ticker, candle, trade, orderbook, order, account).
            data: The data object.
        """
        message = {"type": data_type, "data": data}

        for handler in self._handlers:
            try:
                await handler(message)
            except Exception as e:
                logger.exception(f"Error in handler for {data_type}: {e}")

    async def __aenter__(self) -> "CCXTStreamProvider":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()
