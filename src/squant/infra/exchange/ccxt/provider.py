"""CCXT Stream Provider for multi-exchange real-time data."""

import asyncio
import contextlib
import logging
import random
import re
import time
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
from squant.infra.exchange.ws_types import (
    WSAccountUpdate,
    WSCandle,
    WSOrderBook,
    WSOrderUpdate,
    WSTicker,
    WSTrade,
    WSTradeExecution,
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
                f"Unsupported exchange: {exchange_id}. Supported: {', '.join(SUPPORTED_EXCHANGES)}"
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

        # Reconnect handlers — invoked after successful WebSocket reconnection
        self._reconnect_handlers: list[Callable[..., Any]] = []

        # Transformer for data conversion
        self._transformer = CCXTDataTransformer()

        # Connection health tracking
        self._consecutive_errors: dict[str, int] = {}
        self._max_consecutive_errors = 5
        self._reconnect_lock = asyncio.Lock()
        self._last_successful_message: float = 0

        # Exponential backoff configuration for reconnection
        self._reconnect_base_delay = 1.0  # Base delay in seconds
        self._reconnect_max_delay = 60.0  # Maximum delay in seconds
        self._reconnect_attempt: int = 0  # Current reconnect attempt counter

        # Fast retry: use short fixed delay for the first N reconnect attempts
        # per subscription to give WebSocket connections a chance to establish
        # without long exponential backoff delays on startup.
        self._fast_retry_max_attempts = 3  # Number of reconnects that use fast retry
        self._fast_retry_delay = 2.0  # Fixed delay in seconds for fast retries
        self._subscription_reconnect_count: dict[str, int] = {}  # per-subscription counter

        # Candle close detection: track last timestamp to detect when a new candle starts
        # (meaning the previous one closed). CCXT doesn't provide is_closed natively.
        self._last_candle_ts: dict[str, int] = {}  # "symbol:timeframe" -> timestamp_ms
        self._last_candle_data: dict[str, list[Any]] = {}  # "symbol:timeframe" -> OHLCV array

        # Batch ticker watching - more efficient than individual watch_ticker calls
        self._watched_ticker_symbols: set[str] = set()
        self._tickers_task: asyncio.Task[None] | None = None
        self._tickers_lock = asyncio.Lock()

    @property
    def exchange_id(self) -> str:
        """Get the exchange identifier."""
        return self._exchange_id

    def _get_reconnect_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay for reconnection.

        Uses the formula: min(base * 2^(attempt-1), max_delay) with ±10% jitter.

        Args:
            attempt: Current reconnection attempt number (1-based).

        Returns:
            Delay in seconds before next reconnection attempt.
            Sequence: 1s → 2s → 4s → 8s → 16s → 32s → 60s (capped)
        """
        if attempt <= 0:
            attempt = 1

        # Calculate base exponential delay
        delay = min(
            self._reconnect_base_delay * (2 ** (attempt - 1)),
            self._reconnect_max_delay,
        )

        # Add ±10% jitter to avoid thundering herd problem
        jitter = delay * 0.1 * (random.random() * 2 - 1)
        return float(delay + jitter)

    def _fire_reconnect_exhausted_alert(self, subscription_key: str) -> None:
        """Fire a critical notification when reconnect attempts are exhausted (LIVE-CN-002).

        This prevents silent failure — the system alerts operators that a
        WebSocket subscription has permanently stopped.
        """
        try:
            from squant.services.notification import emit_notification

            loop = asyncio.get_running_loop()
            loop.create_task(
                emit_notification(
                    level="critical",
                    event_type="ws_reconnect_exhausted",
                    title="WebSocket connection permanently lost",
                    message=(
                        f"Subscription '{subscription_key}' on {self._exchange_id} stopped "
                        f"after {self._reconnect_attempt} reconnect attempts. "
                        f"Live trading engines may not receive market data."
                    ),
                    details={
                        "exchange": self._exchange_id,
                        "subscription_key": subscription_key,
                        "reconnect_attempts": self._reconnect_attempt,
                    },
                )
            )
        except Exception:
            logger.warning("Failed to fire reconnect exhausted alert", exc_info=True)

    @property
    def is_connected(self) -> bool:
        """Check if connected to exchange.

        Note: This is a basic check. For true health status, use is_healthy().
        """
        return self._connected and self._exchange is not None

    def is_healthy(self) -> bool:
        """Check if the connection is actually healthy.

        Returns True only if:
        1. We have an exchange instance
        2. We received a message within the last 60 seconds (if we have active subscriptions)
        """
        if not self._connected or self._exchange is None:
            return False

        # If we have active subscriptions but haven't received data recently, unhealthy
        # Allow 60 seconds of no messages before marking unhealthy
        if (
            self._subscription_tasks
            and self._last_successful_message > 0
            and (time_since_last := time.time() - self._last_successful_message) > 60
        ):
            logger.warning(
                f"No messages received in {time_since_last:.0f}s, connection may be dead"
            )
            return False

        return True

    def _build_exchange_config(self) -> dict[str, Any]:
        """Build exchange configuration dictionary.

        Returns:
            Configuration dictionary for CCXT exchange instance.
        """
        config: dict[str, Any] = {
            "enableRateLimit": True,
            # Only load spot markets to avoid timeout on OPTION/FUTURES APIs
            "options": {
                "defaultType": "spot",
                # Limit which market types to fetch (OKX-specific)
                "fetchMarkets": ["spot"],
            },
        }

        # Add credentials if provided
        if self._credentials:
            config["apiKey"] = self._credentials.api_key
            config["secret"] = self._credentials.api_secret
            if self._credentials.passphrase:
                config["password"] = self._credentials.passphrase
            if self._credentials.sandbox:
                config["sandbox"] = True

        return config

    async def _create_exchange_instance(self) -> None:
        """Create and initialize CCXT exchange instance.

        Creates the exchange instance and loads markets with timeout.

        Raises:
            ExchangeConnectionError: If exchange creation or market loading fails.
        """
        config = self._build_exchange_config()

        # Create exchange instance
        exchange_class = getattr(ccxtpro, self._exchange_id, None)
        if exchange_class is None:
            raise ExchangeConnectionError(
                message=f"Exchange {self._exchange_id} not found in ccxt.pro",
                exchange=self._exchange_id,
            )

        self._exchange = exchange_class(config)

        # Load markets (required before using watch_* methods)
        # Use timeout to prevent hanging on network issues
        logger.info(f"Loading markets for {self._exchange_id}...")
        try:
            await asyncio.wait_for(
                self._exchange.load_markets(),
                timeout=30.0,  # 30 second timeout
            )
        except TimeoutError:
            raise ExchangeConnectionError(
                message=f"Timeout loading markets for {self._exchange_id}",
                exchange=self._exchange_id,
            ) from None
        logger.info(f"Markets loaded for {self._exchange_id}")

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

            await self._create_exchange_instance()

            self._connected = True
            self._running = True
            self._last_successful_message = time.time()

            logger.info(f"Connected to {self._exchange_id} via CCXT")

        except ExchangeConnectionError:
            raise
        except Exception as e:
            raise ExchangeConnectionError(
                message=f"Failed to connect to {self._exchange_id}: {e}",
                exchange=self._exchange_id,
            ) from e

    async def reconnect(self) -> bool:
        """Attempt to reconnect to the exchange.

        This method is called when the connection appears to be dead.
        It closes the existing connection and creates a new one.

        Returns:
            True if reconnection was successful, False otherwise.
        """
        async with self._reconnect_lock:
            # Double-check we need to reconnect (another task may have done it)
            if self.is_healthy():
                return True

            logger.warning(f"Attempting to reconnect to {self._exchange_id}...")

            try:
                # Close existing connection
                if self._exchange:
                    try:
                        await self._exchange.close()
                    except Exception as e:
                        logger.debug(f"Error closing old connection: {e}")
                    self._exchange = None
                    self._connected = False

                await self._create_exchange_instance()

                self._connected = True
                self._last_successful_message = time.time()
                self._consecutive_errors.clear()
                self._reconnect_attempt = 0  # Reset reconnect attempt counter on success

                # Restart batch tickers loop if we had watched symbols
                if self._watched_ticker_symbols and (
                    self._tickers_task is None or self._tickers_task.done()
                ):
                    self._tickers_task = asyncio.create_task(self._batch_tickers_loop())
                    logger.info("Restarted batch tickers loop after reconnect")

                logger.info(f"Successfully reconnected to {self._exchange_id}")

                # Notify reconnect handlers
                for handler in self._reconnect_handlers:
                    try:
                        await handler()
                    except Exception as e:
                        logger.error(f"Reconnect handler error: {e}")

                return True

            except ExchangeConnectionError as e:
                logger.error(f"Failed to reconnect to {self._exchange_id}: {e}")
                self._connected = False
                return False
            except Exception as e:
                logger.exception(f"Failed to reconnect to {self._exchange_id}: {e}")
                self._connected = False
                return False

    async def _handle_loop_error(self, key: str, error: Exception) -> bool:
        """Handle an error in a watch loop with exponential backoff.

        Tracks consecutive errors and triggers reconnection with exponential
        backoff delays when threshold is reached. For the first few reconnect
        attempts per subscription, uses a short fixed delay ("fast retry") to
        give the WebSocket connection a chance to establish without long delays
        on startup.

        Args:
            key: Subscription key (e.g., "ticker:BTC/USDT").
            error: The exception that occurred.

        Returns:
            True if we should continue retrying, False if we should stop.
        """
        self._consecutive_errors[key] = self._consecutive_errors.get(key, 0) + 1
        error_count = self._consecutive_errors[key]

        logger.warning(
            f"Error in {key} (attempt {error_count}/{self._max_consecutive_errors}): {error}"
        )

        if error_count >= self._max_consecutive_errors:
            self._reconnect_attempt += 1

            # Track per-subscription reconnect count for fast retry logic
            sub_reconnects = self._subscription_reconnect_count.get(key, 0) + 1
            self._subscription_reconnect_count[key] = sub_reconnects

            # Use fast retry (short fixed delay) for the first N reconnect
            # attempts per subscription — gives WebSocket connections a chance
            # to establish without long exponential backoff delays on startup.
            if sub_reconnects <= self._fast_retry_max_attempts:
                delay = self._fast_retry_delay
                logger.info(
                    f"Fast retry {sub_reconnects}/{self._fast_retry_max_attempts} for {key}, "
                    f"reconnecting in {delay:.1f}s"
                )
            else:
                delay = self._get_reconnect_delay(self._reconnect_attempt)
                logger.warning(
                    f"Too many consecutive errors for {key}, "
                    f"reconnecting in {delay:.1f}s (attempt {self._reconnect_attempt})"
                )

            # Wait before reconnecting
            await asyncio.sleep(delay)

            # Try to reconnect
            if await self.reconnect():
                self._consecutive_errors[key] = 0
                self._reconnect_attempt = 0  # Reset attempt counter on success
                return True
            else:
                # Check if we've exceeded max reconnect attempts
                if self._reconnect_attempt >= 10:
                    logger.error(
                        f"Max reconnection attempts ({self._reconnect_attempt}) reached, stopping {key}"
                    )
                    # Fire critical alert so the issue is not silent (LIVE-CN-002)
                    self._fire_reconnect_exhausted_alert(key)
                    return False
                # Otherwise keep trying with backoff
                return True

        return True

    async def _wait_until_ready(self, key: str, timeout: float = 30.0) -> bool:
        """Wait for the provider to become ready (_running=True).

        Returns True if ready, False if timed out.
        """
        if self._running:
            return True
        logger.info(f"Waiting for provider to become ready before starting {key}")
        elapsed = 0.0
        while not self._running and elapsed < timeout:
            await asyncio.sleep(0.5)
            elapsed += 0.5
        if not self._running:
            logger.warning(f"Provider not ready after {timeout}s, giving up on {key}")
        return self._running

    def _mark_success(self, key: str) -> None:
        """Mark a successful message receipt for a subscription.

        Args:
            key: Subscription key.
        """
        self._last_successful_message = time.time()
        self._consecutive_errors[key] = 0
        # Reset per-subscription reconnect counter on success so that
        # future disconnections get fast retry again.
        self._subscription_reconnect_count.pop(key, None)

    async def close(self) -> None:
        """Close connection and cleanup resources."""
        logger.info(f"Closing {self._exchange_id} connection...")
        self._running = False

        # Cancel batch tickers task
        if self._tickers_task and not self._tickers_task.done():
            self._tickers_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._tickers_task
            self._tickers_task = None

        # Clear watched symbols
        self._watched_ticker_symbols.clear()

        # Cancel all subscription tasks
        for key, task in list(self._subscription_tasks.items()):
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            self._subscription_tasks.pop(key, None)

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

    def add_reconnect_handler(self, handler: Callable[..., Any]) -> None:
        """Register a callback invoked after successful WS reconnection."""
        if handler not in self._reconnect_handlers:
            self._reconnect_handlers.append(handler)

    def remove_reconnect_handler(self, handler: Callable[..., Any]) -> None:
        """Remove a reconnect callback."""
        if handler in self._reconnect_handlers:
            self._reconnect_handlers.remove(handler)

    # ==================== Public Channel Subscriptions ====================

    async def watch_ticker(self, symbol: str) -> None:
        """Subscribe to ticker updates for a symbol.

        Uses batch watch_tickers for efficiency. Multiple symbols share
        a single WebSocket connection.

        Args:
            symbol: Trading pair (e.g., "BTC/USDT").
        """
        # Validate symbol exists on the exchange before adding
        if (
            self._exchange
            and hasattr(self._exchange, "markets")
            and symbol not in self._exchange.markets
        ):
            logger.warning(
                f"Symbol {symbol} not found on {self._exchange_id}, skipping ticker subscription"
            )
            return

        async with self._tickers_lock:
            if symbol in self._watched_ticker_symbols:
                logger.debug(f"Already watching ticker: {symbol}")
                return

            self._watched_ticker_symbols.add(symbol)
            logger.info(
                f"Added ticker to watch list: {symbol} (total: {len(self._watched_ticker_symbols)})"
            )

            # Start or restart the batch tickers loop if not running
            if self._tickers_task is None or self._tickers_task.done():
                self._tickers_task = asyncio.create_task(self._batch_tickers_loop())
                logger.info("Started batch tickers loop")

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
            if not self._subscription_tasks[key].done():
                logger.debug(f"Already watching OHLCV: {symbol} {timeframe}")
                return
            logger.warning(f"Restarting dead OHLCV task for {symbol} {timeframe}")
            del self._subscription_tasks[key]

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
            if not self._subscription_tasks[key].done():
                logger.debug(f"Already watching trades: {symbol}")
                return
            logger.warning(f"Restarting dead trades task for {symbol}")
            del self._subscription_tasks[key]

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
            if not self._subscription_tasks[key].done():
                logger.debug(f"Already watching order book: {symbol}")
                return
            logger.warning(f"Restarting dead order book task for {symbol}")
            del self._subscription_tasks[key]

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
            if not self._subscription_tasks[key].done():
                logger.debug(f"Already watching orders: {symbol or 'all'}")
                return
            logger.warning(f"Restarting dead orders task for {symbol or 'all'}")
            del self._subscription_tasks[key]

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
            if not self._subscription_tasks[key].done():
                logger.debug("Already watching balance")
                return
            logger.warning("Restarting dead balance task")
            del self._subscription_tasks[key]

        task = asyncio.create_task(self._balance_loop())
        self._subscription_tasks[key] = task
        logger.info("Started watching balance")

    async def watch_my_trades(self, symbol: str) -> None:
        """Subscribe to user trade execution feed (private channel).

        Args:
            symbol: Trading symbol (required -- Binance/Bybit require it;
                    OKX supports None but we use symbol for consistency).
        """
        if not self._credentials:
            raise ExchangeAuthenticationError(
                message="Credentials required for private channels",
                exchange=self._exchange_id,
            )
        key = f"my_trades:{symbol}"
        if key in self._subscription_tasks:
            if not self._subscription_tasks[key].done():
                logger.debug(f"Already watching my trades: {symbol}")
                return
            logger.warning(f"Restarting dead my_trades task for {symbol}")
            del self._subscription_tasks[key]
        task = asyncio.create_task(self._my_trades_loop(symbol))
        self._subscription_tasks[key] = task
        logger.info(f"Started watching my trades: {symbol}")

    # ==================== Unsubscribe ====================

    async def unwatch(self, subscription_key: str) -> None:
        """Unsubscribe from a channel.

        Args:
            subscription_key: Subscription key (e.g., "ticker:BTC/USDT").
        """
        # Handle batch ticker unsubscription
        if subscription_key.startswith("ticker:"):
            symbol = subscription_key[7:]  # Remove "ticker:" prefix
            await self.unwatch_ticker(symbol)
            return

        # Handle individual subscription tasks
        if subscription_key in self._subscription_tasks:
            task = self._subscription_tasks.pop(subscription_key)
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            # Clean up candle tracking state for ohlcv subscriptions
            if subscription_key.startswith("ohlcv:"):
                candle_key = subscription_key[6:]  # "ohlcv:BTC/USDT:1h" -> "BTC/USDT:1h"
                self._last_candle_ts.pop(candle_key, None)
                self._last_candle_data.pop(candle_key, None)
            logger.info(f"Unwatched: {subscription_key}")

    async def unwatch_ticker(self, symbol: str) -> None:
        """Unsubscribe from ticker updates for a symbol.

        Removes the symbol from the batch watch list. The batch tickers loop
        will automatically stop watching it on the next iteration.

        Args:
            symbol: Trading pair (e.g., "BTC/USDT").
        """
        async with self._tickers_lock:
            if symbol in self._watched_ticker_symbols:
                self._watched_ticker_symbols.discard(symbol)
                logger.info(
                    f"Removed ticker from watch list: {symbol} "
                    f"(remaining: {len(self._watched_ticker_symbols)})"
                )

                # If no more symbols to watch, stop the batch loop
                if (
                    not self._watched_ticker_symbols
                    and self._tickers_task
                    and not self._tickers_task.done()
                ):
                    self._tickers_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await self._tickers_task
                    self._tickers_task = None
                    logger.info("Stopped batch tickers loop (no symbols to watch)")

    # ==================== Watch Loops ====================

    async def _batch_tickers_loop(self) -> None:
        """Background loop for watching multiple tickers efficiently.

        Uses watch_tickers (plural) to batch multiple symbols into a single
        WebSocket connection, which is much more efficient than individual
        watch_ticker calls.

        Error handling delegates to _handle_loop_error() for consistent
        reconnection behavior with other loops (same threshold, shared
        error counters, exponential backoff).
        """
        key = "batch_tickers"
        logger.info("Batch tickers loop started")

        while self._running:
            try:
                if not self._exchange:
                    await asyncio.sleep(1)
                    continue

                # Get current list of symbols to watch
                async with self._tickers_lock:
                    symbols = list(self._watched_ticker_symbols)

                if not symbols:
                    await asyncio.sleep(1)
                    continue

                # Use watch_tickers (plural) for efficiency
                # This watches all symbols in a single call
                tickers = await self._exchange.watch_tickers(symbols)

                # Reset error count on success
                self._mark_success(key)

                # Process all received tickers
                for symbol, ticker in tickers.items():
                    try:
                        ws_ticker = self._transformer.ticker_to_ws_ticker(ticker)
                        await self._dispatch("ticker", ws_ticker)
                    except Exception as e:
                        logger.warning(f"Error transforming ticker for {symbol}: {e}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                error_msg = str(e)

                # Check if this is an invalid symbol error
                # CCXT raises "exchange does not have market symbol XXX" for invalid symbols
                if "does not have market symbol" in error_msg:
                    # Extract the invalid symbol from error message
                    invalid_symbol = self._extract_invalid_symbol(error_msg)
                    if invalid_symbol:
                        async with self._tickers_lock:
                            if invalid_symbol in self._watched_ticker_symbols:
                                self._watched_ticker_symbols.discard(invalid_symbol)
                                logger.warning(
                                    f"Removed invalid symbol from watch list: {invalid_symbol} "
                                    f"(remaining: {len(self._watched_ticker_symbols)})"
                                )
                        # Don't count this as a consecutive error, just continue
                        continue

                if not await self._handle_loop_error(key, e):
                    break
                await asyncio.sleep(1)

        logger.info("Batch tickers loop stopped")

    def _extract_invalid_symbol(self, error_msg: str) -> str | None:
        """Extract invalid symbol from CCXT error message.

        Args:
            error_msg: Error message like "okx does not have market symbol ZEC/USDT"

        Returns:
            The invalid symbol (e.g., "ZEC/USDT") or None if not found.
        """
        # Pattern: "exchange does not have market symbol SYMBOL"
        match = re.search(r"does not have market symbol (\S+)", error_msg)
        if match:
            return match.group(1)
        return None

    async def _ticker_loop(self, symbol: str) -> None:
        """Background loop for single ticker updates (legacy, used for individual subscriptions)."""
        key = f"ticker:{symbol}"
        try:
            if not await self._wait_until_ready(key):
                return
            while self._running:
                try:
                    if not self._exchange:
                        await asyncio.sleep(1)
                        continue

                    ticker = await self._exchange.watch_ticker(symbol)
                    self._mark_success(key)
                    ws_ticker = self._transformer.ticker_to_ws_ticker(ticker)
                    await self._dispatch("ticker", ws_ticker)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    if not await self._handle_loop_error(key, e):
                        break
                    await asyncio.sleep(1)
        finally:
            self._subscription_tasks.pop(key, None)
            logger.info(f"Ticker loop exited for {symbol}")

    async def _ohlcv_loop(self, symbol: str, ccxt_timeframe: str, timeframe: str) -> None:
        """Background loop for OHLCV/candle updates."""
        key = f"ohlcv:{symbol}:{timeframe}"
        logger.info(f"OHLCV loop started for {symbol} {timeframe}")
        try:
            if not await self._wait_until_ready(key):
                return
            while self._running:
                try:
                    if not self._exchange:
                        await asyncio.sleep(1)
                        continue

                    logger.debug(f"Calling watch_ohlcv for {symbol} {ccxt_timeframe}")
                    ohlcv_list = await self._exchange.watch_ohlcv(symbol, ccxt_timeframe)
                    self._mark_success(key)
                    logger.debug(
                        f"Received {len(ohlcv_list)} OHLCV candles for {symbol} {timeframe}"
                    )

                    # Process the latest candle with close detection
                    for ohlcv in ohlcv_list[-1:]:  # Only process the latest
                        candle_key = f"{symbol}:{timeframe}"
                        candle_ts = int(ohlcv[0])

                        # Detect candle close: when timestamp changes, previous candle closed
                        if candle_key in self._last_candle_ts:
                            if candle_ts != self._last_candle_ts[candle_key]:
                                # Previous candle has closed - dispatch with is_closed=True
                                closed_candle = self._transformer.ohlcv_to_ws_candle(
                                    self._last_candle_data[candle_key],
                                    symbol,
                                    timeframe,
                                    is_closed=True,
                                )
                                await self._dispatch("candle", closed_candle)

                        # Track current candle state
                        self._last_candle_ts[candle_key] = candle_ts
                        self._last_candle_data[candle_key] = ohlcv

                        # Dispatch current (open) candle for real-time UI updates
                        ws_candle = self._transformer.ohlcv_to_ws_candle(
                            ohlcv, symbol, timeframe, is_closed=False
                        )
                        await self._dispatch("candle", ws_candle)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    if not await self._handle_loop_error(key, e):
                        break
                    await asyncio.sleep(1)
        finally:
            self._subscription_tasks.pop(key, None)
            logger.info(f"OHLCV loop exited for {symbol} {timeframe}")

    async def _trades_loop(self, symbol: str) -> None:
        """Background loop for trade updates."""
        key = f"trades:{symbol}"
        try:
            if not await self._wait_until_ready(key):
                return
            while self._running:
                try:
                    if not self._exchange:
                        await asyncio.sleep(1)
                        continue

                    trades = await self._exchange.watch_trades(symbol)
                    self._mark_success(key)

                    for trade in trades:
                        ws_trade = self._transformer.trade_to_ws_trade(trade)
                        await self._dispatch("trade", ws_trade)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    if not await self._handle_loop_error(key, e):
                        break
                    await asyncio.sleep(1)
        finally:
            self._subscription_tasks.pop(key, None)
            logger.info(f"Trades loop exited for {symbol}")

    async def _orderbook_loop(self, symbol: str, limit: int) -> None:
        """Background loop for order book updates."""
        key = f"orderbook:{symbol}"
        try:
            if not await self._wait_until_ready(key):
                return
            while self._running:
                try:
                    if not self._exchange:
                        await asyncio.sleep(1)
                        continue

                    orderbook = await self._exchange.watch_order_book(symbol, limit)
                    self._mark_success(key)
                    ws_orderbook = self._transformer.orderbook_to_ws_orderbook(
                        orderbook, symbol, limit
                    )
                    await self._dispatch("orderbook", ws_orderbook)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    if not await self._handle_loop_error(key, e):
                        break
                    await asyncio.sleep(1)
        finally:
            self._subscription_tasks.pop(key, None)
            logger.info(f"Order book loop exited for {symbol}")

    async def _orders_loop(self, symbol: str | None) -> None:
        """Background loop for order updates."""
        key = f"orders:{symbol or 'all'}"
        try:
            if not await self._wait_until_ready(key):
                return
            while self._running:
                try:
                    if not self._exchange:
                        await asyncio.sleep(1)
                        continue

                    orders = await self._exchange.watch_orders(symbol)
                    self._mark_success(key)

                    for order in orders:
                        ws_order = self._transformer.order_to_ws_order_update(order)
                        await self._dispatch("order", ws_order)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    if not await self._handle_loop_error(key, e):
                        break
                    await asyncio.sleep(1)
        finally:
            self._subscription_tasks.pop(key, None)
            logger.info(f"Orders loop exited for {symbol or 'all'}")

    async def _balance_loop(self) -> None:
        """Background loop for balance updates."""
        key = "balance"
        try:
            if not await self._wait_until_ready(key):
                return
            while self._running:
                try:
                    if not self._exchange:
                        await asyncio.sleep(1)
                        continue

                    balance = await self._exchange.watch_balance()
                    self._mark_success(key)
                    ws_balance = self._transformer.balance_to_ws_account_update(balance)
                    await self._dispatch("account", ws_balance)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    if not await self._handle_loop_error(key, e):
                        break
                    await asyncio.sleep(1)
        finally:
            self._subscription_tasks.pop(key, None)
            logger.info("Balance loop exited")

    async def _my_trades_loop(self, symbol: str) -> None:
        """Background loop for user trade execution updates."""
        key = f"my_trades:{symbol}"
        try:
            if not await self._wait_until_ready(key):
                return
            while self._running:
                try:
                    if not self._exchange:
                        await asyncio.sleep(1)
                        continue
                    trades = await self._exchange.watch_my_trades(symbol)
                    self._mark_success(key)
                    for trade in trades:
                        ws_trade = self._transformer.trade_to_ws_trade_execution(trade)
                        await self._dispatch("trade_execution", ws_trade)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    if not await self._handle_loop_error(key, e):
                        break
                    await asyncio.sleep(1)
        finally:
            self._subscription_tasks.pop(key, None)
            logger.info(f"My trades loop exited for {symbol}")

    # ==================== Dispatch ====================

    async def _dispatch(
        self,
        data_type: str,
        data: WSTicker | WSCandle | WSTrade | WSOrderBook | WSOrderUpdate | WSAccountUpdate | WSTradeExecution,
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
