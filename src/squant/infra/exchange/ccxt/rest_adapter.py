"""CCXT-based REST adapter for multi-exchange support."""

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import ccxt.async_support as ccxt

from squant.infra.exchange.base import ExchangeAdapter
from squant.infra.exchange.ccxt.types import (
    SUPPORTED_EXCHANGES,
    TIMEFRAME_MAP,
    ExchangeCredentials,
)
from squant.infra.exchange.exceptions import (
    ExchangeAPIError,
    ExchangeAuthenticationError,
    ExchangeConnectionError,
    ExchangeRateLimitError,
    InvalidOrderError,
    OrderNotFoundError,
)
from squant.infra.exchange.retry import RetryConfig, with_retry
from squant.infra.exchange.types import (
    AccountBalance,
    Balance,
    CancelOrderRequest,
    Candlestick,
    OrderRequest,
    OrderResponse,
    Ticker,
    TimeFrame,
    TradeInfo,
)
from squant.models.enums import OrderSide, OrderStatus, OrderType

logger = logging.getLogger(__name__)

# Retry config for read-only and idempotent operations (LIVE-007)
_READ_RETRY = RetryConfig(max_retries=3, base_delay=0.5, max_delay=10.0)

# Retry config for order placement — safe when client_order_id is set
# (exchanges treat duplicate client_order_id as idempotent). Single retry
# to avoid extended delays while protecting against transient network errors.
_PLACE_ORDER_RETRY = RetryConfig(max_retries=1, base_delay=0.5, max_delay=5.0)


class CCXTRestAdapter(ExchangeAdapter):
    """CCXT-based REST adapter supporting multiple exchanges.

    This adapter provides a unified interface for REST API calls to any
    supported exchange (OKX, Binance, Bybit) using the CCXT library.

    Example:
        adapter = CCXTRestAdapter("okx", credentials)
        async with adapter:
            tickers = await adapter.get_tickers()
    """

    def __init__(
        self,
        exchange_id: str,
        credentials: ExchangeCredentials | None = None,
    ) -> None:
        """Initialize CCXT REST adapter.

        Args:
            exchange_id: Exchange identifier (okx, binance, bybit).
            credentials: Optional API credentials for authenticated endpoints.

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

    @property
    def name(self) -> str:
        """Exchange name."""
        return self._exchange_id

    @property
    def is_testnet(self) -> bool:
        """Whether connected to testnet/sandbox."""
        return self._credentials.sandbox if self._credentials else False

    def get_symbols(self) -> list[str]:
        """Return sorted list of available trading symbols.

        Must be called after connect() / load_markets().
        """
        if self._exchange and self._exchange.markets:
            return sorted(self._exchange.markets.keys())
        return []

    async def connect(self) -> None:
        """Establish connection to the exchange."""
        if self._connected:
            logger.debug(f"Already connected to {self._exchange_id}")
            return

        try:
            logger.info(f"Connecting to {self._exchange_id} via CCXT REST...")

            # Build exchange configuration
            config: dict[str, Any] = {
                "enableRateLimit": True,
                # Only load spot markets to avoid timeout on OPTION/FUTURES APIs
                "options": {
                    "defaultType": "spot",
                    # Limit which market types to fetch (reduces API calls)
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

            # Create exchange instance
            exchange_class = getattr(ccxt, self._exchange_id, None)
            if exchange_class is None:
                raise ExchangeConnectionError(
                    message=f"Exchange {self._exchange_id} not found in ccxt",
                    exchange=self._exchange_id,
                )

            self._exchange = exchange_class(config)

            # Load markets
            logger.info(f"Loading markets for {self._exchange_id}...")
            await self._exchange.load_markets()
            logger.info(f"Markets loaded for {self._exchange_id}")

            self._connected = True
            logger.info(f"Connected to {self._exchange_id} via CCXT REST")

        except ccxt.ExchangeNotAvailable as e:
            raise ExchangeConnectionError(
                message=f"Exchange {self._exchange_id} is not available (possibly geo-restricted): {e}",
                exchange=self._exchange_id,
            ) from e
        except ccxt.NetworkError as e:
            raise ExchangeConnectionError(
                message=f"Network error connecting to {self._exchange_id}: {e}",
                exchange=self._exchange_id,
            ) from e
        except Exception as e:
            raise ExchangeConnectionError(
                message=f"Failed to connect to {self._exchange_id}: {e}",
                exchange=self._exchange_id,
            ) from e

    async def close(self) -> None:
        """Close connection and cleanup resources."""
        logger.info(f"Closing {self._exchange_id} REST connection...")

        if self._exchange:
            try:
                await self._exchange.close()
            except Exception as e:
                logger.warning(f"Error closing exchange: {e}")
            self._exchange = None

        self._connected = False
        logger.info(f"Closed {self._exchange_id} REST connection")

    # ==================== Market Data Methods ====================

    async def get_ticker(self, symbol: str) -> Ticker:
        """Get ticker for a trading pair."""
        if not self._exchange:
            raise ExchangeConnectionError(
                message="Exchange not connected. Call connect() first.",
                exchange=self._exchange_id,
            )

        try:
            ticker = await self._exchange.fetch_ticker(symbol)
            return self._transform_ticker(ticker)
        except ccxt.BadSymbol as e:
            raise ExchangeAPIError(
                message=f"Invalid symbol: {symbol}",
                exchange=self._exchange_id,
            ) from e
        except ccxt.RateLimitExceeded as e:
            raise ExchangeRateLimitError(
                message=f"Rate limit exceeded: {e}",
                exchange=self._exchange_id,
            ) from e
        except Exception as e:
            raise ExchangeAPIError(
                message=f"Failed to fetch ticker for {symbol}: {e}",
                exchange=self._exchange_id,
            ) from e

    async def get_tickers(self, symbols: Sequence[str] | None = None) -> list[Ticker]:
        """Get tickers for multiple trading pairs."""
        if not self._exchange:
            raise ExchangeConnectionError(
                message="Exchange not connected. Call connect() first.",
                exchange=self._exchange_id,
            )

        try:
            # Fetch all tickers if no symbols specified
            if symbols is None:
                tickers = await self._exchange.fetch_tickers()
            else:
                # Filter out symbols not available on this exchange
                markets = self._exchange.markets or {}
                valid_symbols = [s for s in symbols if s in markets]
                skipped = set(symbols) - set(valid_symbols)
                if skipped:
                    logger.warning(
                        f"Skipping symbols not found on {self._exchange_id}: "
                        f"{', '.join(sorted(skipped))}"
                    )

                if not valid_symbols:
                    return []

                # Some exchanges support batch fetch, others need individual calls
                if self._exchange.has.get("fetchTickers"):
                    tickers = await self._exchange.fetch_tickers(valid_symbols)
                else:
                    tickers = {}
                    for symbol in valid_symbols:
                        try:
                            ticker = await self._exchange.fetch_ticker(symbol)
                            tickers[symbol] = ticker
                        except Exception as e:
                            logger.warning(f"Failed to fetch ticker for {symbol}: {e}")

            return [self._transform_ticker(t) for t in tickers.values()]
        except ccxt.RateLimitExceeded as e:
            raise ExchangeRateLimitError(
                message=f"Rate limit exceeded: {e}",
                exchange=self._exchange_id,
            ) from e
        except Exception as e:
            raise ExchangeAPIError(
                message=f"Failed to fetch tickers: {e}",
                exchange=self._exchange_id,
            ) from e

    async def get_candlesticks(
        self,
        symbol: str,
        timeframe: TimeFrame,
        limit: int = 100,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[Candlestick]:
        """Get OHLCV candlestick data."""
        if not self._exchange:
            raise ExchangeConnectionError(
                message="Exchange not connected. Call connect() first.",
                exchange=self._exchange_id,
            )

        # Convert TimeFrame enum to CCXT timeframe string
        ccxt_timeframe = TIMEFRAME_MAP.get(timeframe.value)
        if not ccxt_timeframe:
            raise ValueError(f"Invalid timeframe: {timeframe}")

        try:
            ohlcv = await self._exchange.fetch_ohlcv(
                symbol,
                timeframe=ccxt_timeframe,
                since=start_time,
                limit=limit,
            )

            candles = []
            for item in ohlcv:
                if len(item) >= 6:
                    # Filter by end_time if specified (CCXT doesn't support it natively)
                    if end_time is not None and item[0] > end_time:
                        continue
                    candles.append(
                        Candlestick(
                            timestamp=datetime.fromtimestamp(item[0] / 1000, tz=UTC),
                            open=Decimal(str(item[1])),
                            high=Decimal(str(item[2])),
                            low=Decimal(str(item[3])),
                            close=Decimal(str(item[4])),
                            volume=Decimal(str(item[5])) if item[5] else Decimal("0"),
                        )
                    )

            return candles
        except ccxt.BadSymbol as e:
            raise ExchangeAPIError(
                message=f"Invalid symbol: {symbol}",
                exchange=self._exchange_id,
            ) from e
        except ccxt.RateLimitExceeded as e:
            raise ExchangeRateLimitError(
                message=f"Rate limit exceeded: {e}",
                exchange=self._exchange_id,
            ) from e
        except Exception as e:
            raise ExchangeAPIError(
                message=f"Failed to fetch candlesticks for {symbol}: {e}",
                exchange=self._exchange_id,
            ) from e

    # ==================== Account Methods ====================

    async def get_balance(self) -> AccountBalance:
        """Get account balance for all currencies."""
        return await with_retry(
            self._get_balance_impl, config=_READ_RETRY, operation_name="get_balance"
        )

    async def _get_balance_impl(self) -> AccountBalance:
        """Internal get_balance implementation (retryable)."""
        if not self._exchange:
            raise ExchangeConnectionError(
                message="Exchange not connected. Call connect() first.",
                exchange=self._exchange_id,
            )

        if not self._credentials:
            raise ExchangeAuthenticationError(
                message="Credentials required for balance query",
                exchange=self._exchange_id,
            )

        try:
            balance = await self._exchange.fetch_balance()

            balances = []
            free_balances = balance.get("free", {})
            used_balances = balance.get("used", {})

            all_currencies = set(free_balances.keys()) | set(used_balances.keys())

            for currency in all_currencies:
                free = free_balances.get(currency, 0)
                used = used_balances.get(currency, 0)

                if free == 0 and used == 0:
                    continue

                balances.append(
                    Balance(
                        currency=currency,
                        available=Decimal(str(free)) if free else Decimal("0"),
                        frozen=Decimal(str(used)) if used else Decimal("0"),
                    )
                )

            return AccountBalance(
                exchange=self._exchange_id,
                balances=balances,
                timestamp=datetime.now(UTC),
            )
        except ccxt.AuthenticationError as e:
            raise ExchangeAuthenticationError(
                message=f"Authentication failed: {e}",
                exchange=self._exchange_id,
            ) from e
        except ccxt.RateLimitExceeded as e:
            raise ExchangeRateLimitError(
                message=f"Rate limit exceeded: {e}",
                exchange=self._exchange_id,
            ) from e
        except Exception as e:
            raise ExchangeAPIError(
                message=f"Failed to fetch balance: {e}",
                exchange=self._exchange_id,
            ) from e

    # ==================== Order Methods ====================

    async def place_order(self, request: OrderRequest) -> OrderResponse:
        """Place a new order with retry for transient errors (LIVE-EX-001).

        Uses client_order_id for idempotency — safe to retry on network errors.
        """
        if not self._exchange:
            raise ExchangeConnectionError(
                message="Exchange not connected. Call connect() first.",
                exchange=self._exchange_id,
            )

        if not self._credentials:
            raise ExchangeAuthenticationError(
                message="Credentials required for placing orders",
                exchange=self._exchange_id,
            )

        return await with_retry(
            self._place_order_impl,
            request,
            config=_PLACE_ORDER_RETRY,
            operation_name="place_order",
        )

    async def _place_order_impl(self, request: OrderRequest) -> OrderResponse:
        """Internal place_order implementation."""
        try:
            order_type = request.type.value.lower()
            side = request.side.value.lower()

            kwargs: dict[str, Any] = {
                "symbol": request.symbol,
                "type": order_type,
                "side": side,
                "amount": str(request.amount),
                "price": str(request.price) if request.price else None,
            }
            params: dict[str, Any] = {}
            if request.client_order_id:
                params["clientOrderId"] = request.client_order_id
            # LIVE-EX-002: pass trigger price for STOP/STOP_LIMIT orders
            # CCXT unified API uses "triggerPrice" across all exchanges
            if request.stop_price is not None:
                params["triggerPrice"] = str(request.stop_price)
            if params:
                kwargs["params"] = params

            order = await self._exchange.create_order(**kwargs)

            return self._transform_order(order)
        except ccxt.InsufficientFunds as e:
            raise InvalidOrderError(
                message=f"Insufficient funds: {e}",
                exchange=self._exchange_id,
                field="amount",
            ) from e
        except ccxt.InvalidOrder as e:
            raise InvalidOrderError(
                message=f"Invalid order: {e}",
                exchange=self._exchange_id,
            ) from e
        except ccxt.RateLimitExceeded as e:
            raise ExchangeRateLimitError(
                message=f"Rate limit exceeded: {e}",
                exchange=self._exchange_id,
            ) from e
        except ccxt.AuthenticationError as e:
            raise ExchangeAuthenticationError(
                message=f"Authentication failed: {e}",
                exchange=self._exchange_id,
            ) from e
        except Exception as e:
            raise ExchangeAPIError(
                message=f"Failed to place order: {e}",
                exchange=self._exchange_id,
            ) from e

    async def cancel_order(self, request: CancelOrderRequest) -> OrderResponse:
        """Cancel an existing order."""
        return await with_retry(
            self._cancel_order_impl,
            request,
            config=_READ_RETRY,
            operation_name="cancel_order",
        )

    async def _cancel_order_impl(self, request: CancelOrderRequest) -> OrderResponse:
        """Internal cancel_order implementation (retryable)."""
        if not self._exchange:
            raise ExchangeConnectionError(
                message="Exchange not connected. Call connect() first.",
                exchange=self._exchange_id,
            )

        if not self._credentials:
            raise ExchangeAuthenticationError(
                message="Credentials required for canceling orders",
                exchange=self._exchange_id,
            )

        try:
            order_id = request.order_id or request.client_order_id
            order = await self._exchange.cancel_order(
                id=order_id,
                symbol=request.symbol,
            )

            return self._transform_order(order)
        except ccxt.OrderNotFound as e:
            raise OrderNotFoundError(
                message=f"Order not found: {order_id}",
                exchange=self._exchange_id,
            ) from e
        except ccxt.RateLimitExceeded as e:
            raise ExchangeRateLimitError(
                message=f"Rate limit exceeded: {e}",
                exchange=self._exchange_id,
            ) from e
        except ccxt.AuthenticationError as e:
            raise ExchangeAuthenticationError(
                message=f"Authentication failed: {e}",
                exchange=self._exchange_id,
            ) from e
        except Exception as e:
            raise ExchangeAPIError(
                message=f"Failed to cancel order: {e}",
                exchange=self._exchange_id,
            ) from e

    async def get_order(self, symbol: str, order_id: str) -> OrderResponse:
        """Get order details by ID."""
        return await with_retry(
            self._get_order_impl,
            symbol,
            order_id,
            config=_READ_RETRY,
            operation_name="get_order",
        )

    async def _get_order_impl(self, symbol: str, order_id: str) -> OrderResponse:
        """Internal get_order implementation (retryable)."""
        if not self._exchange:
            raise ExchangeConnectionError(
                message="Exchange not connected. Call connect() first.",
                exchange=self._exchange_id,
            )

        if not self._credentials:
            raise ExchangeAuthenticationError(
                message="Credentials required for order query",
                exchange=self._exchange_id,
            )

        try:
            order = await self._exchange.fetch_order(order_id, symbol)
            return self._transform_order(order)
        except ccxt.OrderNotFound as e:
            raise OrderNotFoundError(
                message=f"Order not found: {order_id}",
                exchange=self._exchange_id,
            ) from e
        except ccxt.RateLimitExceeded as e:
            raise ExchangeRateLimitError(
                message=f"Rate limit exceeded: {e}",
                exchange=self._exchange_id,
            ) from e
        except ccxt.AuthenticationError as e:
            raise ExchangeAuthenticationError(
                message=f"Authentication failed: {e}",
                exchange=self._exchange_id,
            ) from e
        except Exception as e:
            raise ExchangeAPIError(
                message=f"Failed to fetch order: {e}",
                exchange=self._exchange_id,
            ) from e

    async def get_open_orders(self, symbol: str | None = None) -> list[OrderResponse]:
        """Get all open (unfilled) orders with retry (LIVE-CN-004)."""
        if not self._exchange:
            raise ExchangeConnectionError(
                message="Exchange not connected. Call connect() first.",
                exchange=self._exchange_id,
            )

        if not self._credentials:
            raise ExchangeAuthenticationError(
                message="Credentials required for order query",
                exchange=self._exchange_id,
            )

        return await with_retry(
            self._get_open_orders_impl,
            symbol,
            config=_READ_RETRY,
            operation_name="get_open_orders",
        )

    async def _get_open_orders_impl(self, symbol: str | None = None) -> list[OrderResponse]:
        """Internal get_open_orders implementation."""
        try:
            orders = await self._exchange.fetch_open_orders(symbol)
            return [self._transform_order(order) for order in orders]
        except ccxt.RateLimitExceeded as e:
            raise ExchangeRateLimitError(
                message=f"Rate limit exceeded: {e}",
                exchange=self._exchange_id,
            ) from e
        except ccxt.AuthenticationError as e:
            raise ExchangeAuthenticationError(
                message=f"Authentication failed: {e}",
                exchange=self._exchange_id,
            ) from e
        except Exception as e:
            raise ExchangeAPIError(
                message=f"Failed to fetch open orders: {e}",
                exchange=self._exchange_id,
            ) from e

    async def get_order_trades(self, symbol: str, order_id: str) -> list[TradeInfo]:
        """Get all individual fills for a specific order via CCXT fetchOrderTrades."""
        return await with_retry(
            lambda: self._get_order_trades_impl(symbol, order_id),
            config=_READ_RETRY,
            operation_name="get_order_trades",
        )

    async def _get_order_trades_impl(self, symbol: str, order_id: str) -> list[TradeInfo]:
        """Internal implementation (retryable)."""
        if not self._exchange:
            raise ExchangeConnectionError(
                message="Exchange not connected. Call connect() first.",
                exchange=self._exchange_id,
            )
        raw_trades = await self._exchange.fetch_order_trades(order_id, symbol)
        result = []
        for t in raw_trades:
            fee_info = t.get("fee") or {}
            ts = t.get("timestamp")
            timestamp = (
                datetime.fromtimestamp(ts / 1000, tz=UTC) if ts is not None else datetime.now(UTC)
            )
            result.append(
                TradeInfo(
                    trade_id=str(t.get("id", "")),
                    order_id=str(t.get("order", "")),
                    symbol=t.get("symbol", symbol),
                    side=t.get("side", ""),
                    price=Decimal(str(t.get("price") or 0)),
                    amount=Decimal(str(t.get("amount") or 0)),
                    fee=Decimal(str(fee_info.get("cost") or 0)),
                    fee_currency=fee_info.get("currency") or "",
                    taker_or_maker=t.get("takerOrMaker"),
                    timestamp=timestamp,
                )
            )
        result.sort(key=lambda x: x.timestamp)
        return result

    # ==================== Dead Man's Switch (F-2) ====================

    @property
    def supports_dead_man_switch(self) -> bool:
        """Whether the exchange supports cancel-all-after."""
        if not self._exchange:
            return False
        return bool(self._exchange.has.get("cancelAllOrdersAfter"))

    async def setup_dead_man_switch(self, timeout_ms: int) -> None:
        """Activate or refresh dead man's switch timer.

        Args:
            timeout_ms: Countdown in milliseconds. 0 cancels the timer.
        """
        if not self._exchange:
            raise ExchangeConnectionError(
                message="Exchange not connected. Call connect() first.",
                exchange=self._exchange_id,
            )

        if not self._exchange.has.get("cancelAllOrdersAfter"):
            return

        try:
            params: dict[str, Any] = {}
            # Bybit requires explicit product type for spot
            if self._exchange_id == "bybit":
                params["product"] = "SPOT"

            await self._exchange.cancel_all_orders_after(timeout_ms, params)
        except ccxt.AuthenticationError as e:
            raise ExchangeAuthenticationError(
                message=f"Authentication failed for dead man's switch: {e}",
                exchange=self._exchange_id,
            ) from e
        except Exception as e:
            # Non-fatal: log and continue — DMS is a safety net, not critical path
            logger.warning(f"Failed to set dead man's switch on {self._exchange_id}: {e}")

    # ==================== Transformation Helpers ====================

    def _transform_ticker(self, ticker: dict[str, Any]) -> Ticker:
        """Transform CCXT ticker to internal Ticker type."""
        last = ticker.get("last")
        open_price = ticker.get("open")

        # Calculate change values
        change_24h = None
        change_pct_24h = None
        if last is not None and open_price is not None and open_price != 0:
            change_24h = last - open_price
            change_pct_24h = (change_24h / open_price) * 100

        return Ticker(
            symbol=ticker.get("symbol", ""),
            last=Decimal(str(last)) if last is not None else Decimal("0"),
            bid=Decimal(str(ticker["bid"])) if ticker.get("bid") is not None else None,
            ask=Decimal(str(ticker["ask"])) if ticker.get("ask") is not None else None,
            high_24h=Decimal(str(ticker["high"])) if ticker.get("high") is not None else None,
            low_24h=Decimal(str(ticker["low"])) if ticker.get("low") is not None else None,
            volume_24h=Decimal(str(ticker["baseVolume"]))
            if ticker.get("baseVolume") is not None
            else None,
            volume_quote_24h=Decimal(str(ticker["quoteVolume"]))
            if ticker.get("quoteVolume") is not None
            else None,
            change_24h=Decimal(str(change_24h)) if change_24h is not None else None,
            change_pct_24h=Decimal(str(change_pct_24h)) if change_pct_24h is not None else None,
            timestamp=self._parse_timestamp(ticker.get("timestamp")) or datetime.now(UTC),
        )

    def _transform_order(self, order: dict[str, Any]) -> OrderResponse:
        """Transform CCXT order to internal OrderResponse type."""
        fee_info = order.get("fee") or {}
        amount = Decimal(str(order.get("amount") or 0))
        filled = Decimal(str(order.get("filled") or 0))

        try:
            side = OrderSide(order.get("side", "buy"))
        except ValueError as e:
            raise ExchangeAPIError(
                f"Unknown order side '{order.get('side')}' for order {order.get('id')} — "
                f"cannot safely default in live trading"
            ) from e

        try:
            order_type = OrderType(order.get("type", "market"))
        except ValueError as e:
            raise ExchangeAPIError(
                f"Unknown order type '{order.get('type')}' for order {order.get('id')} — "
                f"cannot safely default in live trading"
            ) from e

        return OrderResponse(
            order_id=str(order.get("id", "")),
            client_order_id=order.get("clientOrderId"),
            symbol=order.get("symbol", ""),
            side=side,
            type=order_type,
            status=self._map_order_status(order.get("status") or "", filled, amount),
            price=Decimal(str(order["price"])) if order.get("price") is not None else None,
            amount=amount,
            filled=filled,
            avg_price=Decimal(str(order["average"])) if order.get("average") is not None else None,
            fee=Decimal(str(fee_info["cost"])) if fee_info.get("cost") is not None else None,
            fee_currency=fee_info.get("currency"),
            created_at=self._parse_timestamp(order.get("timestamp")),
            updated_at=self._parse_timestamp(order.get("lastTradeTimestamp")),
        )

    def _map_order_status(
        self, status: str, filled: Decimal = Decimal("0"), amount: Decimal = Decimal("0")
    ) -> OrderStatus:
        """Map CCXT order status to internal OrderStatus enum.

        CCXT uses "open" for both new and partially filled orders.
        We distinguish them by checking if filled > 0.
        """
        lower_status = status.lower()
        # Detect partially filled orders: CCXT reports "open" with filled > 0
        if lower_status == "open" and filled > 0 and amount > 0 and filled < amount:
            return OrderStatus.PARTIAL
        status_map = {
            "open": OrderStatus.SUBMITTED,
            "closed": OrderStatus.FILLED,
            "canceled": OrderStatus.CANCELLED,
            "expired": OrderStatus.CANCELLED,
            "rejected": OrderStatus.REJECTED,
        }
        return status_map.get(lower_status, OrderStatus.SUBMITTED)

    def _parse_timestamp(self, ts: int | None) -> datetime | None:
        """Parse CCXT timestamp (milliseconds) to datetime.

        Returns None when the exchange omits the timestamp instead of
        silently substituting the current wall-clock time (LIVE-CN-006).
        """
        if ts is None:
            return None
        return datetime.fromtimestamp(ts / 1000, tz=UTC)
