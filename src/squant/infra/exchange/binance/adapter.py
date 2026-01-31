"""Binance exchange adapter implementation."""

import json
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

from .client import BinanceClient


def _ensure_dict(response: dict[str, Any] | list[Any], context: str) -> dict[str, Any]:
    """Ensure response is a dict, raising error if it's a list."""
    if isinstance(response, list):
        raise ExchangeAPIError(
            message=f"Unexpected list response for {context}",
            exchange="binance",
        )
    return response


class BinanceAdapter(ExchangeAdapter):
    """Binance exchange adapter.

    Implements the ExchangeAdapter interface for Binance exchange,
    handling symbol format conversion, API calls, and response mapping.
    """

    # Symbol format conversion (BTC/USDT <-> BTCUSDT)
    @staticmethod
    def _to_binance_symbol(symbol: str) -> str:
        """Convert standard symbol to Binance format."""
        return symbol.replace("/", "")

    @staticmethod
    def _from_binance_symbol(symbol: str) -> str:
        """Convert Binance symbol to standard format.

        Binance symbols don't have separators, so we need to infer the split point.
        Common quote currencies: USDT, USDC, BUSD, BTC, ETH, BNB
        """
        # Try common quote currencies (longest first to avoid false matches)
        quote_currencies = ["USDT", "USDC", "BUSD", "FDUSD", "TUSD", "BTC", "ETH", "BNB"]
        for quote in quote_currencies:
            if symbol.endswith(quote):
                base = symbol[: -len(quote)]
                if base:  # Ensure we have a base currency
                    return f"{base}/{quote}"
        # Fallback: assume last 4 chars are quote (USDT)
        if len(symbol) > 4:
            return f"{symbol[:-4]}/{symbol[-4:]}"
        return symbol

    # Timeframe mapping
    TIMEFRAME_MAP = {
        TimeFrame.M1: "1m",
        TimeFrame.M5: "5m",
        TimeFrame.M15: "15m",
        TimeFrame.M30: "30m",
        TimeFrame.H1: "1h",
        TimeFrame.H4: "4h",
        TimeFrame.D1: "1d",
        TimeFrame.W1: "1w",
    }

    # Order status mapping (Binance -> standard)
    ORDER_STATUS_MAP = {
        "NEW": OrderStatus.SUBMITTED,
        "PARTIALLY_FILLED": OrderStatus.PARTIAL,
        "FILLED": OrderStatus.FILLED,
        "CANCELED": OrderStatus.CANCELLED,
        "PENDING_CANCEL": OrderStatus.SUBMITTED,  # Still active
        "REJECTED": OrderStatus.REJECTED,
        "EXPIRED": OrderStatus.CANCELLED,
        "EXPIRED_IN_MATCH": OrderStatus.CANCELLED,
    }

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        testnet: bool = False,
    ) -> None:
        """Initialize Binance adapter.

        Args:
            api_key: Binance API key.
            api_secret: Binance API secret.
            testnet: Whether to use testnet.
        """
        self._testnet = testnet
        self._client = BinanceClient(
            api_key=api_key,
            api_secret=api_secret,
            testnet=testnet,
        )

    @property
    def name(self) -> str:
        """Exchange name."""
        return "binance"

    @property
    def is_testnet(self) -> bool:
        """Whether connected to testnet."""
        return self._testnet

    async def connect(self) -> None:
        """Establish connection to Binance."""
        await self._client.connect()

    async def close(self) -> None:
        """Close connection."""
        await self._client.close()

    # Account methods

    async def get_balance(self) -> AccountBalance:
        """Get account balance for all currencies."""
        response = _ensure_dict(await self._client.get("/api/v3/account"), "get_balance")

        balances: list[Balance] = []
        for item in response.get("balances", []):
            available = Decimal(item.get("free", "0"))
            frozen = Decimal(item.get("locked", "0"))
            # Only include currencies with non-zero balance
            if available > 0 or frozen > 0:
                balances.append(
                    Balance(
                        currency=item.get("asset", ""),
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
        binance_symbol = self._to_binance_symbol(symbol)
        response = _ensure_dict(
            await self._client.get(
                "/api/v3/ticker/24hr",
                params={"symbol": binance_symbol},
                authenticated=False,
            ),
            "get_ticker",
        )

        if not response:
            raise ExchangeAPIError(
                message=f"No ticker data for {symbol}",
                exchange="binance",
            )

        return self._parse_ticker(response)

    async def get_tickers(self, symbols: Sequence[str] | None = None) -> list[Ticker]:
        """Get tickers for multiple trading pairs."""
        params: dict[str, Any] = {}

        if symbols:
            # Binance accepts a JSON array of symbols
            binance_symbols = [self._to_binance_symbol(s) for s in symbols]
            params["symbols"] = json.dumps(binance_symbols)

        response = await self._client.get(
            "/api/v3/ticker/24hr",
            params=params if params else None,
            authenticated=False,
        )

        # Response is an array when no symbol specified or multiple symbols
        data = response if isinstance(response, list) else response.get("data", [response])

        return [self._parse_ticker(item) for item in data]

    def _parse_ticker(self, data: dict[str, Any]) -> Ticker:
        """Parse ticker data from Binance response."""
        symbol = self._from_binance_symbol(data.get("symbol", ""))

        def parse_decimal(value: str | None) -> Decimal | None:
            if value and value != "":
                try:
                    return Decimal(value)
                except Exception:
                    return None
            return None

        last = parse_decimal(data.get("lastPrice")) or Decimal("0")
        price_change = parse_decimal(data.get("priceChange"))
        price_change_pct = parse_decimal(data.get("priceChangePercent"))

        return Ticker(
            symbol=symbol,
            last=last,
            bid=parse_decimal(data.get("bidPrice")),
            ask=parse_decimal(data.get("askPrice")),
            high_24h=parse_decimal(data.get("highPrice")),
            low_24h=parse_decimal(data.get("lowPrice")),
            volume_24h=parse_decimal(data.get("volume")),
            volume_quote_24h=parse_decimal(data.get("quoteVolume")),
            change_24h=price_change,
            change_pct_24h=price_change_pct,
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
        binance_symbol = self._to_binance_symbol(symbol)
        binance_interval = self.TIMEFRAME_MAP.get(timeframe)

        if not binance_interval:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

        params: dict[str, Any] = {
            "symbol": binance_symbol,
            "interval": binance_interval,
            "limit": min(limit, 1000),  # Binance max is 1000
        }

        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time

        response = await self._client.get(
            "/api/v3/klines",
            params=params,
            authenticated=False,
        )

        # Response might be wrapped in "data" key
        data = response if isinstance(response, list) else response.get("data", [])
        candlesticks = []

        for item in data:
            # Binance format: [openTime, open, high, low, close, volume, closeTime, quoteVolume, ...]
            if len(item) >= 7:
                candlesticks.append(
                    Candlestick(
                        timestamp=datetime.fromtimestamp(int(item[0]) / 1000, tz=UTC),
                        open=Decimal(item[1]),
                        high=Decimal(item[2]),
                        low=Decimal(item[3]),
                        close=Decimal(item[4]),
                        volume=Decimal(item[5]),
                        volume_quote=Decimal(item[7]) if len(item) > 7 else None,
                    )
                )

        # Already sorted by timestamp ascending from Binance
        return candlesticks

    # Order methods

    async def place_order(self, request: OrderRequest) -> OrderResponse:
        """Place a new order."""
        binance_symbol = self._to_binance_symbol(request.symbol)

        params: dict[str, Any] = {
            "symbol": binance_symbol,
            "side": request.side.value.upper(),
            "type": request.type.value.upper(),
            "quantity": str(request.amount),
        }

        if request.type == OrderType.LIMIT:
            if request.price is None:
                raise InvalidOrderError(
                    message="Limit order requires price",
                    exchange="binance",
                    field="price",
                )
            params["price"] = str(request.price)
            params["timeInForce"] = "GTC"  # Good Till Cancelled

        if request.client_order_id:
            params["newClientOrderId"] = request.client_order_id

        response = _ensure_dict(
            await self._client.post("/api/v3/order", params=params), "place_order"
        )

        return OrderResponse(
            order_id=str(response.get("orderId", "")),
            client_order_id=response.get("clientOrderId"),
            symbol=request.symbol,
            side=request.side,
            type=request.type,
            status=self.ORDER_STATUS_MAP.get(response.get("status", "NEW"), OrderStatus.SUBMITTED),
            price=request.price,
            amount=request.amount,
            filled=Decimal(response.get("executedQty", "0")),
            created_at=datetime.now(UTC),
        )

    async def cancel_order(self, request: CancelOrderRequest) -> OrderResponse:
        """Cancel an existing order."""
        binance_symbol = self._to_binance_symbol(request.symbol)

        params: dict[str, Any] = {
            "symbol": binance_symbol,
        }

        if request.order_id:
            params["orderId"] = request.order_id
        elif request.client_order_id:
            params["origClientOrderId"] = request.client_order_id
        else:
            raise InvalidOrderError(
                message="Either order_id or client_order_id is required",
                exchange="binance",
                field="order_id",
            )

        response = _ensure_dict(
            await self._client.delete("/api/v3/order", params=params), "cancel_order"
        )

        return self._parse_order(response)

    async def get_order(self, symbol: str, order_id: str) -> OrderResponse:
        """Get order details by ID."""
        binance_symbol = self._to_binance_symbol(symbol)

        response = _ensure_dict(
            await self._client.get(
                "/api/v3/order",
                params={
                    "symbol": binance_symbol,
                    "orderId": order_id,
                },
            ),
            "get_order",
        )

        if not response:
            raise OrderNotFoundError(
                message=f"Order {order_id} not found",
                exchange="binance",
                order_id=order_id,
            )

        return self._parse_order(response)

    async def get_open_orders(self, symbol: str | None = None) -> list[OrderResponse]:
        """Get all open orders."""
        params: dict[str, Any] = {}
        if symbol:
            params["symbol"] = self._to_binance_symbol(symbol)

        response = await self._client.get("/api/v3/openOrders", params=params if params else None)

        # Response might be wrapped in "data" key
        data = response if isinstance(response, list) else response.get("data", [])

        return [self._parse_order(item) for item in data]

    def _parse_order(self, data: dict[str, Any]) -> OrderResponse:
        """Parse order data from Binance response."""
        symbol = self._from_binance_symbol(data.get("symbol", ""))

        # Parse side
        side_str = data.get("side", "BUY").upper()
        side = OrderSide.BUY if side_str == "BUY" else OrderSide.SELL

        # Parse type
        type_str = data.get("type", "LIMIT").upper()
        order_type = OrderType.MARKET if type_str == "MARKET" else OrderType.LIMIT

        # Parse status
        status_str = data.get("status", "NEW")
        status = self.ORDER_STATUS_MAP.get(status_str, OrderStatus.PENDING)

        # Parse decimals
        def parse_decimal(value: str | None) -> Decimal | None:
            if value and value != "" and value != "0":
                try:
                    return Decimal(value)
                except Exception:
                    return None
            return None

        def parse_decimal_default(value: str | None, default: str = "0") -> Decimal:
            if value and value != "":
                try:
                    return Decimal(value)
                except Exception:
                    return Decimal(default)
            return Decimal(default)

        # Parse timestamps
        created_ts = data.get("time") or data.get("transactTime")
        updated_ts = data.get("updateTime")

        created_at = None
        updated_at = None
        if created_ts:
            created_at = datetime.fromtimestamp(int(created_ts) / 1000, tz=UTC)
        if updated_ts:
            updated_at = datetime.fromtimestamp(int(updated_ts) / 1000, tz=UTC)

        # Calculate average price if filled
        filled_qty = parse_decimal_default(data.get("executedQty"))
        cummulative_quote = parse_decimal(data.get("cummulativeQuoteQty"))
        avg_price = None
        if cummulative_quote and filled_qty > 0:
            avg_price = cummulative_quote / filled_qty

        return OrderResponse(
            order_id=str(data.get("orderId", "")),
            client_order_id=data.get("clientOrderId") or None,
            symbol=symbol,
            side=side,
            type=order_type,
            status=status,
            price=parse_decimal(data.get("price")),
            amount=parse_decimal_default(data.get("origQty")),
            filled=filled_qty,
            avg_price=avg_price,
            fee=None,  # Binance doesn't return fee in order response
            fee_currency=None,
            created_at=created_at,
            updated_at=updated_at,
        )
