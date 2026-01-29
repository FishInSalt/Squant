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
    InvalidOrderError,
    OrderNotFoundError,
)
from squant.infra.exchange.types import (
    AccountBalance,
    Balance,
    CancelOrderRequest,
    Candlestick,
    OrderRequest,
    OrderResponse,
    Ticker,
    TimeFrame,
)
from squant.models.enums import OrderSide, OrderStatus, OrderType

logger = logging.getLogger(__name__)


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
                f"Unsupported exchange: {exchange_id}. "
                f"Supported: {', '.join(SUPPORTED_EXCHANGES)}"
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
            raise RuntimeError("Exchange not connected. Call connect() first.")

        try:
            ticker = await self._exchange.fetch_ticker(symbol)
            return self._transform_ticker(ticker)
        except ccxt.BadSymbol as e:
            raise ExchangeAPIError(
                message=f"Invalid symbol: {symbol}",
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
            raise RuntimeError("Exchange not connected. Call connect() first.")

        try:
            # Fetch all tickers if no symbols specified
            if symbols is None:
                tickers = await self._exchange.fetch_tickers()
            else:
                # Some exchanges support batch fetch, others need individual calls
                if self._exchange.has.get("fetchTickers"):
                    tickers = await self._exchange.fetch_tickers(list(symbols))
                else:
                    tickers = {}
                    for symbol in symbols:
                        try:
                            ticker = await self._exchange.fetch_ticker(symbol)
                            tickers[symbol] = ticker
                        except Exception as e:
                            logger.warning(f"Failed to fetch ticker for {symbol}: {e}")

            return [self._transform_ticker(t) for t in tickers.values()]
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
            raise RuntimeError("Exchange not connected. Call connect() first.")

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
        except Exception as e:
            raise ExchangeAPIError(
                message=f"Failed to fetch candlesticks for {symbol}: {e}",
                exchange=self._exchange_id,
            ) from e

    # ==================== Account Methods ====================

    async def get_balance(self) -> AccountBalance:
        """Get account balance for all currencies."""
        if not self._exchange:
            raise RuntimeError("Exchange not connected. Call connect() first.")

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
        except Exception as e:
            raise ExchangeAPIError(
                message=f"Failed to fetch balance: {e}",
                exchange=self._exchange_id,
            ) from e

    # ==================== Order Methods ====================

    async def place_order(self, request: OrderRequest) -> OrderResponse:
        """Place a new order."""
        if not self._exchange:
            raise RuntimeError("Exchange not connected. Call connect() first.")

        if not self._credentials:
            raise ExchangeAuthenticationError(
                message="Credentials required for placing orders",
                exchange=self._exchange_id,
            )

        try:
            order_type = request.type.value.lower()
            side = request.side.value.lower()

            order = await self._exchange.create_order(
                symbol=request.symbol,
                type=order_type,
                side=side,
                amount=float(request.amount),
                price=float(request.price) if request.price else None,
            )

            return self._transform_order(order)
        except ccxt.InvalidOrder as e:
            raise InvalidOrderError(
                message=f"Invalid order: {e}",
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
        if not self._exchange:
            raise RuntimeError("Exchange not connected. Call connect() first.")

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
        if not self._exchange:
            raise RuntimeError("Exchange not connected. Call connect() first.")

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
        """Get all open (unfilled) orders."""
        if not self._exchange:
            raise RuntimeError("Exchange not connected. Call connect() first.")

        if not self._credentials:
            raise ExchangeAuthenticationError(
                message="Credentials required for order query",
                exchange=self._exchange_id,
            )

        try:
            orders = await self._exchange.fetch_open_orders(symbol)
            return [self._transform_order(order) for order in orders]
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
            volume_24h=Decimal(str(ticker["baseVolume"])) if ticker.get("baseVolume") is not None else None,
            volume_quote_24h=Decimal(str(ticker["quoteVolume"])) if ticker.get("quoteVolume") is not None else None,
            change_24h=Decimal(str(change_24h)) if change_24h is not None else None,
            change_pct_24h=Decimal(str(change_pct_24h)) if change_pct_24h is not None else None,
            timestamp=self._parse_timestamp(ticker.get("timestamp")),
        )

    def _transform_order(self, order: dict[str, Any]) -> OrderResponse:
        """Transform CCXT order to internal OrderResponse type."""
        fee_info = order.get("fee") or {}

        return OrderResponse(
            order_id=str(order.get("id", "")),
            client_order_id=order.get("clientOrderId"),
            symbol=order.get("symbol", ""),
            side=OrderSide(order.get("side", "buy").upper()),
            type=OrderType(order.get("type", "market").upper()),
            status=self._map_order_status(order.get("status", "")),
            price=Decimal(str(order["price"])) if order.get("price") is not None else None,
            amount=Decimal(str(order.get("amount", 0))),
            filled=Decimal(str(order.get("filled", 0))),
            avg_price=Decimal(str(order["average"])) if order.get("average") is not None else None,
            fee=Decimal(str(fee_info["cost"])) if fee_info.get("cost") is not None else None,
            fee_currency=fee_info.get("currency"),
            created_at=self._parse_timestamp(order.get("timestamp")),
            updated_at=self._parse_timestamp(order.get("lastTradeTimestamp")),
        )

    def _map_order_status(self, status: str) -> OrderStatus:
        """Map CCXT order status to internal OrderStatus enum."""
        status_map = {
            "open": OrderStatus.SUBMITTED,
            "closed": OrderStatus.FILLED,
            "canceled": OrderStatus.CANCELLED,
            "expired": OrderStatus.CANCELLED,
            "rejected": OrderStatus.REJECTED,
        }
        return status_map.get(status.lower(), OrderStatus.SUBMITTED)

    def _parse_timestamp(self, ts: int | None) -> datetime:
        """Parse CCXT timestamp (milliseconds) to datetime."""
        if ts is None:
            return datetime.now(UTC)
        return datetime.fromtimestamp(ts / 1000, tz=UTC)
