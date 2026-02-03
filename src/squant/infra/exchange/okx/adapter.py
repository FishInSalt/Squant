"""OKX exchange adapter implementation."""

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from squant.infra.exchange.base import ExchangeAdapter
from squant.infra.exchange.exceptions import (
    ExchangeAPIError,
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

from .client import OKXClient


class OKXAdapter(ExchangeAdapter):
    """OKX exchange adapter.

    Implements the ExchangeAdapter interface for OKX exchange,
    handling symbol format conversion, API calls, and response mapping.
    """

    # Symbol format conversion (BTC/USDT <-> BTC-USDT)
    @staticmethod
    def _to_okx_symbol(symbol: str) -> str:
        """Convert standard symbol to OKX format."""
        return symbol.replace("/", "-")

    @staticmethod
    def _from_okx_symbol(symbol: str) -> str:
        """Convert OKX symbol to standard format."""
        return symbol.replace("-", "/")

    # Timeframe mapping
    TIMEFRAME_MAP = {
        TimeFrame.M1: "1m",
        TimeFrame.M5: "5m",
        TimeFrame.M15: "15m",
        TimeFrame.M30: "30m",
        TimeFrame.H1: "1H",
        TimeFrame.H4: "4H",
        TimeFrame.D1: "1D",
        TimeFrame.W1: "1W",
    }

    # Order status mapping (OKX -> standard)
    ORDER_STATUS_MAP = {
        "live": OrderStatus.SUBMITTED,
        "partially_filled": OrderStatus.PARTIAL,
        "filled": OrderStatus.FILLED,
        "canceled": OrderStatus.CANCELLED,
        "mmp_canceled": OrderStatus.CANCELLED,
    }

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        passphrase: str,
        testnet: bool = False,
    ) -> None:
        """Initialize OKX adapter.

        Args:
            api_key: OKX API key.
            api_secret: OKX API secret.
            passphrase: OKX API passphrase.
            testnet: Whether to use testnet (simulated trading).
        """
        self._testnet = testnet
        self._client = OKXClient(
            api_key=api_key,
            api_secret=api_secret,
            passphrase=passphrase,
            testnet=testnet,
        )

    @property
    def name(self) -> str:
        """Exchange name."""
        return "okx"

    @property
    def is_testnet(self) -> bool:
        """Whether connected to testnet."""
        return self._testnet

    async def connect(self) -> None:
        """Establish connection to OKX."""
        await self._client.connect()

    async def close(self) -> None:
        """Close connection."""
        await self._client.close()

    # Account methods

    async def get_balance(self) -> AccountBalance:
        """Get account balance for all currencies."""
        response = await self._client.get("/api/v5/account/balance")
        data = response.get("data", [])

        balances: list[Balance] = []
        if data:
            details = data[0].get("details", [])
            for item in details:
                # Only include currencies with non-zero balance
                available = Decimal(item.get("availBal", "0"))
                frozen = Decimal(item.get("frozenBal", "0"))
                if available > 0 or frozen > 0:
                    balances.append(
                        Balance(
                            currency=item.get("ccy", ""),
                            available=available,
                            frozen=frozen,
                        )
                    )

        return AccountBalance(
            exchange=self.name,
            balances=balances,
            timestamp=datetime.now(UTC),
        )

    # Market data methods

    async def get_ticker(self, symbol: str) -> Ticker:
        """Get ticker for a trading pair."""
        okx_symbol = self._to_okx_symbol(symbol)
        response = await self._client.get(
            "/api/v5/market/ticker",
            params={"instId": okx_symbol},
            authenticated=False,
        )

        data = response.get("data", [])
        if not data:
            raise ExchangeAPIError(
                message=f"No ticker data for {symbol}",
                exchange="okx",
            )

        return self._parse_ticker(data[0])

    async def get_tickers(self, symbols: Sequence[str] | None = None) -> list[Ticker]:
        """Get tickers for multiple trading pairs."""
        # OKX requires instType parameter for batch ticker
        response = await self._client.get(
            "/api/v5/market/tickers",
            params={"instType": "SPOT"},
            authenticated=False,
        )

        data = response.get("data", [])
        tickers = [self._parse_ticker(item) for item in data]

        # Filter by symbols if provided
        if symbols:
            symbol_set = {self._to_okx_symbol(s) for s in symbols}
            tickers = [t for t in tickers if self._to_okx_symbol(t.symbol) in symbol_set]

        return tickers

    def _parse_ticker(self, data: dict[str, Any]) -> Ticker:
        """Parse ticker data from OKX response."""
        symbol = self._from_okx_symbol(data.get("instId", ""))
        last = Decimal(data.get("last", "0"))

        # Parse optional fields with defaults
        def parse_decimal(value: str | None) -> Decimal | None:
            if value and value != "":
                return Decimal(value)
            return None

        # Calculate price change and percentage
        open_24h = parse_decimal(data.get("open24h"))
        change_24h = None
        change_pct_24h = None
        if open_24h and open_24h != 0:
            change_24h = last - open_24h
            change_pct_24h = (change_24h / open_24h) * 100

        return Ticker(
            symbol=symbol,
            last=last,
            bid=parse_decimal(data.get("bidPx")),
            ask=parse_decimal(data.get("askPx")),
            high_24h=parse_decimal(data.get("high24h")),
            low_24h=parse_decimal(data.get("low24h")),
            volume_24h=parse_decimal(data.get("vol24h")),
            volume_quote_24h=parse_decimal(data.get("volCcy24h")),
            change_24h=change_24h,
            change_pct_24h=change_pct_24h,
            timestamp=datetime.now(UTC),
        )

    async def get_candlesticks(
        self,
        symbol: str,
        timeframe: TimeFrame,
        limit: int = 100,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[Candlestick]:
        """Get OHLCV candlestick data."""
        okx_symbol = self._to_okx_symbol(symbol)
        okx_timeframe = self.TIMEFRAME_MAP.get(timeframe)

        if not okx_timeframe:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

        params: dict[str, Any] = {
            "instId": okx_symbol,
            "bar": okx_timeframe,
            "limit": str(min(limit, 300)),  # OKX max is 300
        }

        if end_time:
            params["after"] = str(end_time)
        if start_time:
            params["before"] = str(start_time)

        response = await self._client.get(
            "/api/v5/market/candles",
            params=params,
            authenticated=False,
        )

        data = response.get("data", [])
        candlesticks = []

        for item in data:
            # OKX format: [timestamp, open, high, low, close, vol, volCcy, ...]
            if len(item) >= 6:
                candlesticks.append(
                    Candlestick(
                        timestamp=datetime.fromtimestamp(int(item[0]) / 1000, tz=UTC),
                        open=Decimal(item[1]),
                        high=Decimal(item[2]),
                        low=Decimal(item[3]),
                        close=Decimal(item[4]),
                        volume=Decimal(item[5]),
                        volume_quote=Decimal(item[6]) if len(item) > 6 else None,
                    )
                )

        # Sort by timestamp ascending (OKX returns descending)
        candlesticks.sort(key=lambda c: c.timestamp)
        return candlesticks

    # Order methods

    async def place_order(self, request: OrderRequest) -> OrderResponse:
        """Place a new order."""
        okx_symbol = self._to_okx_symbol(request.symbol)

        body: dict[str, Any] = {
            "instId": okx_symbol,
            "tdMode": "cash",  # Spot trading
            "side": request.side.value,
            "ordType": request.type.value,
            "sz": str(request.amount),
        }

        if request.type == OrderType.LIMIT:
            if request.price is None:
                raise InvalidOrderError(
                    message="Limit order requires price",
                    exchange="okx",
                    field="price",
                )
            body["px"] = str(request.price)

        if request.client_order_id:
            body["clOrdId"] = request.client_order_id

        response = await self._client.post("/api/v5/trade/order", body=body)

        data = response.get("data", [])
        if not data:
            raise ExchangeAPIError(
                message="No data in order response",
                exchange="okx",
            )

        order_data = data[0]

        # Check for order-level error
        if order_data.get("sCode") != "0":
            raise InvalidOrderError(
                message=order_data.get("sMsg", "Order placement failed"),
                exchange="okx",
            )

        # Return basic response; full details require get_order
        return OrderResponse(
            order_id=order_data.get("ordId", ""),
            client_order_id=order_data.get("clOrdId"),
            symbol=request.symbol,
            side=request.side,
            type=request.type,
            status=OrderStatus.SUBMITTED,
            price=request.price,
            amount=request.amount,
            filled=Decimal("0"),
            created_at=datetime.now(UTC),
        )

    async def cancel_order(self, request: CancelOrderRequest) -> OrderResponse:
        """Cancel an existing order."""
        # Validate that at least one identifier is provided (Issue 026)
        if not request.order_id and not request.client_order_id:
            raise InvalidOrderError(
                message="Either order_id or client_order_id is required to cancel an order",
                exchange="okx",
                field="order_id",
            )

        okx_symbol = self._to_okx_symbol(request.symbol)

        body: dict[str, Any] = {
            "instId": okx_symbol,
        }

        if request.order_id:
            body["ordId"] = request.order_id
        elif request.client_order_id:
            body["clOrdId"] = request.client_order_id

        response = await self._client.post("/api/v5/trade/cancel-order", body=body)

        data = response.get("data", [])
        if not data:
            raise ExchangeAPIError(
                message="No data in cancel response",
                exchange="okx",
            )

        order_data = data[0]

        # Check for order-level error
        if order_data.get("sCode") != "0":
            error_code = order_data.get("sCode", "")
            error_msg = order_data.get("sMsg", "Cancel failed")

            if error_code == "51400":  # Order doesn't exist
                raise OrderNotFoundError(
                    message=error_msg,
                    exchange="okx",
                    order_id=request.order_id or request.client_order_id,
                )

            raise ExchangeAPIError(
                message=error_msg,
                exchange="okx",
                code=error_code,
            )

        # Get full order details using the order_id from response or request
        order_id = order_data.get("ordId") or request.order_id
        if not order_id:
            # This shouldn't happen if validation passed, but handle it gracefully
            raise ExchangeAPIError(
                message="No order_id in cancel response and none provided in request",
                exchange="okx",
            )
        return await self.get_order(request.symbol, order_id)

    async def get_order(self, symbol: str, order_id: str) -> OrderResponse:
        """Get order details by ID."""
        okx_symbol = self._to_okx_symbol(symbol)

        response = await self._client.get(
            "/api/v5/trade/order",
            params={
                "instId": okx_symbol,
                "ordId": order_id,
            },
        )

        data = response.get("data", [])
        if not data:
            raise OrderNotFoundError(
                message=f"Order {order_id} not found",
                exchange="okx",
                order_id=order_id,
            )

        return self._parse_order(data[0])

    async def get_open_orders(self, symbol: str | None = None) -> list[OrderResponse]:
        """Get all open orders."""
        params: dict[str, Any] = {"instType": "SPOT"}
        if symbol:
            params["instId"] = self._to_okx_symbol(symbol)

        response = await self._client.get("/api/v5/trade/orders-pending", params=params)

        data = response.get("data", [])
        return [self._parse_order(item) for item in data]

    def _parse_order(self, data: dict[str, Any]) -> OrderResponse:
        """Parse order data from OKX response."""
        symbol = self._from_okx_symbol(data.get("instId", ""))

        # Parse side
        side_str = data.get("side", "buy")
        side = OrderSide.BUY if side_str == "buy" else OrderSide.SELL

        # Parse type
        type_str = data.get("ordType", "limit")
        order_type = OrderType.MARKET if type_str == "market" else OrderType.LIMIT

        # Parse status
        state = data.get("state", "")
        status = self.ORDER_STATUS_MAP.get(state, OrderStatus.PENDING)

        # Parse decimals
        def parse_decimal(value: str | None) -> Decimal | None:
            if value and value != "" and value != "0":
                return Decimal(value)
            return None

        def parse_decimal_default(value: str | None, default: str = "0") -> Decimal:
            if value and value != "":
                return Decimal(value)
            return Decimal(default)

        # Parse timestamps
        created_ts = data.get("cTime")
        updated_ts = data.get("uTime")

        created_at = None
        updated_at = None
        if created_ts:
            created_at = datetime.fromtimestamp(int(created_ts) / 1000, tz=UTC)
        if updated_ts:
            updated_at = datetime.fromtimestamp(int(updated_ts) / 1000, tz=UTC)

        return OrderResponse(
            order_id=data.get("ordId", ""),
            client_order_id=data.get("clOrdId") or None,
            symbol=symbol,
            side=side,
            type=order_type,
            status=status,
            price=parse_decimal(data.get("px")),
            amount=parse_decimal_default(data.get("sz")),
            filled=parse_decimal_default(data.get("accFillSz")),
            avg_price=parse_decimal(data.get("avgPx")),
            fee=parse_decimal(data.get("fee")),
            fee_currency=data.get("feeCcy") or None,
            created_at=created_at,
            updated_at=updated_at,
        )
