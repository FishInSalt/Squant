"""CCXT data transformer for converting exchange data to internal types."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from squant.infra.exchange.ws_types import (
    WSAccountUpdate,
    WSBalanceUpdate,
    WSCandle,
    WSOrderBook,
    WSOrderBookLevel,
    WSOrderUpdate,
    WSTicker,
    WSTrade,
    WSTradeExecution,
)


class CCXTDataTransformer:
    """Transform CCXT unified data formats to internal Pydantic models.

    CCXT provides unified data structures across all exchanges. This transformer
    converts those structures to our existing internal types (WSTicker, WSCandle, etc.)
    ensuring compatibility with the rest of the system.
    """

    @staticmethod
    def ticker_to_ws_ticker(ticker: dict[str, Any]) -> WSTicker:
        """Convert CCXT ticker to WSTicker.

        Args:
            ticker: CCXT unified ticker structure.
                {
                    'symbol': 'BTC/USDT',
                    'timestamp': 1234567890123,
                    'datetime': '2024-01-01T00:00:00.123Z',
                    'high': 50000.0,
                    'low': 49000.0,
                    'bid': 49500.0,
                    'bidVolume': 1.5,
                    'ask': 49501.0,
                    'askVolume': 2.0,
                    'open': 49200.0,
                    'close': 49500.0,
                    'last': 49500.0,
                    'baseVolume': 1000.0,
                    'quoteVolume': 49500000.0,
                    ...
                }

        Returns:
            WSTicker instance.
        """
        return WSTicker(
            symbol=ticker.get("symbol", ""),
            last=Decimal(str(ticker.get("last", 0)))
            if ticker.get("last") is not None
            else Decimal("0"),
            bid=Decimal(str(ticker["bid"])) if ticker.get("bid") is not None else None,
            ask=Decimal(str(ticker["ask"])) if ticker.get("ask") is not None else None,
            bid_size=Decimal(str(ticker["bidVolume"]))
            if ticker.get("bidVolume") is not None
            else None,
            ask_size=Decimal(str(ticker["askVolume"]))
            if ticker.get("askVolume") is not None
            else None,
            high_24h=Decimal(str(ticker["high"])) if ticker.get("high") is not None else None,
            low_24h=Decimal(str(ticker["low"])) if ticker.get("low") is not None else None,
            volume_24h=Decimal(str(ticker["baseVolume"]))
            if ticker.get("baseVolume") is not None
            else None,
            volume_quote_24h=Decimal(str(ticker["quoteVolume"]))
            if ticker.get("quoteVolume") is not None
            else None,
            open_24h=Decimal(str(ticker["open"])) if ticker.get("open") is not None else None,
            timestamp=CCXTDataTransformer._parse_timestamp(ticker.get("timestamp")),
        )

    @staticmethod
    def ohlcv_to_ws_candle(
        ohlcv: list[Any],
        symbol: str,
        timeframe: str,
        is_closed: bool = False,
    ) -> WSCandle:
        """Convert CCXT OHLCV to WSCandle.

        Args:
            ohlcv: CCXT OHLCV array [timestamp, open, high, low, close, volume].
            symbol: Trading pair symbol.
            timeframe: Candle timeframe.
            is_closed: Whether the candle is closed.

        Returns:
            WSCandle instance.

        Raises:
            ValueError: If OHLCV array length is less than 6.
        """
        if len(ohlcv) < 6:
            raise ValueError(f"Invalid OHLCV array length: {len(ohlcv)}, expected >= 6")

        return WSCandle(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=CCXTDataTransformer._parse_timestamp(ohlcv[0]),
            open=Decimal(str(ohlcv[1])),
            high=Decimal(str(ohlcv[2])),
            low=Decimal(str(ohlcv[3])),
            close=Decimal(str(ohlcv[4])),
            volume=Decimal(str(ohlcv[5])) if ohlcv[5] is not None else Decimal("0"),
            volume_quote=None,  # CCXT OHLCV doesn't include quote volume
            is_closed=is_closed,
        )

    @staticmethod
    def trade_to_ws_trade(trade: dict[str, Any]) -> WSTrade:
        """Convert CCXT trade to WSTrade.

        Args:
            trade: CCXT unified trade structure.
                {
                    'id': '12345',
                    'timestamp': 1234567890123,
                    'datetime': '2024-01-01T00:00:00.123Z',
                    'symbol': 'BTC/USDT',
                    'side': 'buy',
                    'price': 49500.0,
                    'amount': 0.1,
                    ...
                }

        Returns:
            WSTrade instance.
        """
        return WSTrade(
            symbol=trade.get("symbol", ""),
            trade_id=str(trade.get("id", "")),
            price=Decimal(str(trade.get("price", 0))),
            size=Decimal(str(trade.get("amount", 0))),
            side=trade.get("side", "").lower(),
            timestamp=CCXTDataTransformer._parse_timestamp(trade.get("timestamp")),
        )

    @staticmethod
    def orderbook_to_ws_orderbook(
        orderbook: dict[str, Any],
        symbol: str,
        limit: int = 5,
    ) -> WSOrderBook:
        """Convert CCXT order book to WSOrderBook.

        Args:
            orderbook: CCXT unified orderbook structure.
                {
                    'timestamp': 1234567890123,
                    'datetime': '2024-01-01T00:00:00.123Z',
                    'nonce': 12345,
                    'bids': [[price, amount], ...],
                    'asks': [[price, amount], ...],
                }
            symbol: Trading pair symbol.
            limit: Number of levels to include.

        Returns:
            WSOrderBook instance.
        """
        bids = [
            WSOrderBookLevel(
                price=Decimal(str(bid[0])),
                size=Decimal(str(bid[1])),
                num_orders=None,
            )
            for bid in orderbook.get("bids", [])[:limit]
        ]

        asks = [
            WSOrderBookLevel(
                price=Decimal(str(ask[0])),
                size=Decimal(str(ask[1])),
                num_orders=None,
            )
            for ask in orderbook.get("asks", [])[:limit]
        ]

        return WSOrderBook(
            symbol=symbol,
            bids=bids,
            asks=asks,
            timestamp=CCXTDataTransformer._parse_timestamp(orderbook.get("timestamp")),
            checksum=orderbook.get("nonce"),
        )

    @staticmethod
    def order_to_ws_order_update(order: dict[str, Any]) -> WSOrderUpdate:
        """Convert CCXT order to WSOrderUpdate.

        Args:
            order: CCXT unified order structure.
                {
                    'id': '12345',
                    'clientOrderId': 'my-order-1',
                    'timestamp': 1234567890123,
                    'datetime': '2024-01-01T00:00:00.123Z',
                    'lastTradeTimestamp': 1234567890456,
                    'symbol': 'BTC/USDT',
                    'type': 'limit',
                    'side': 'buy',
                    'price': 49500.0,
                    'amount': 0.1,
                    'filled': 0.05,
                    'remaining': 0.05,
                    'status': 'open',
                    'fee': {'cost': 0.01, 'currency': 'USDT'},
                    'average': 49500.0,
                    ...
                }

        Returns:
            WSOrderUpdate instance.
        """
        fee_info = order.get("fee") or {}

        # Map status, then detect partial fills (CCXT reports "open" for both
        # unfilled and partially filled orders — ISSUE-506 fix)
        status = CCXTDataTransformer._map_order_status(order.get("status", ""))
        filled = Decimal(str(order.get("filled", 0)))
        amount = Decimal(str(order.get("amount", 0)))
        if status == "submitted" and filled > 0 and amount > 0 and filled < amount:
            status = "partial"

        return WSOrderUpdate(
            order_id=str(order.get("id", "")),
            client_order_id=order.get("clientOrderId"),
            symbol=order.get("symbol", ""),
            side=order.get("side", "").lower(),
            order_type=order.get("type", "").lower(),
            status=status,
            price=Decimal(str(order["price"])) if order.get("price") is not None else None,
            size=Decimal(str(order.get("amount", 0))),
            filled_size=filled,
            avg_price=Decimal(str(order["average"])) if order.get("average") is not None else None,
            fee=Decimal(str(fee_info["cost"])) if fee_info.get("cost") is not None else None,
            fee_currency=fee_info.get("currency"),
            created_at=CCXTDataTransformer._parse_timestamp(order.get("timestamp")),
            updated_at=CCXTDataTransformer._parse_timestamp(order.get("lastTradeTimestamp")),
        )

    @staticmethod
    def balance_to_ws_account_update(balance: dict[str, Any]) -> WSAccountUpdate:
        """Convert CCXT balance to WSAccountUpdate.

        Args:
            balance: CCXT unified balance structure.
                {
                    'info': {...},
                    'timestamp': 1234567890123,
                    'datetime': '2024-01-01T00:00:00.123Z',
                    'free': {'BTC': 1.0, 'USDT': 10000.0},
                    'used': {'BTC': 0.5, 'USDT': 5000.0},
                    'total': {'BTC': 1.5, 'USDT': 15000.0},
                    'BTC': {'free': 1.0, 'used': 0.5, 'total': 1.5},
                    'USDT': {'free': 10000.0, 'used': 5000.0, 'total': 15000.0},
                    ...
                }

        Returns:
            WSAccountUpdate instance.
        """
        balances: list[WSBalanceUpdate] = []

        # Extract per-currency balances
        free_balances = balance.get("free", {})
        used_balances = balance.get("used", {})

        # Combine all currencies from both free and used balances
        all_currencies = set(free_balances.keys()) | set(used_balances.keys())

        for currency in all_currencies:
            free = free_balances.get(currency, 0)
            used = used_balances.get(currency, 0)

            # Skip zero balances
            if free == 0 and used == 0:
                continue

            balances.append(
                WSBalanceUpdate(
                    currency=currency,
                    available=Decimal(str(free)) if free is not None else Decimal("0"),
                    frozen=Decimal(str(used)) if used is not None else Decimal("0"),
                )
            )

        return WSAccountUpdate(
            balances=balances,
            timestamp=CCXTDataTransformer._parse_timestamp(balance.get("timestamp")),
        )

    @staticmethod
    def trade_to_ws_trade_execution(trade: dict[str, Any]) -> WSTradeExecution:
        """Convert a CCXT trade dict (from watchMyTrades) to WSTradeExecution.

        Args:
            trade: CCXT unified trade structure.

        Returns:
            WSTradeExecution with per-fill data.
        """
        fee_info = trade.get("fee") or {}
        ts = trade.get("timestamp")
        timestamp = (
            datetime.fromtimestamp(ts / 1000, tz=UTC)
            if ts is not None
            else datetime.now(UTC)
        )
        return WSTradeExecution(
            trade_id=str(trade.get("id", "")),
            order_id=str(trade.get("order", "")),
            client_order_id=trade.get("clientOrderId"),
            symbol=trade.get("symbol", ""),
            side=trade.get("side", ""),
            price=Decimal(str(trade.get("price") or 0)),
            amount=Decimal(str(trade.get("amount") or 0)),
            fee=Decimal(str(fee_info.get("cost") or 0)),
            fee_currency=fee_info.get("currency") or "",
            taker_or_maker=trade.get("takerOrMaker"),
            timestamp=timestamp,
        )

    @staticmethod
    def _parse_timestamp(ts: int | None) -> datetime:
        """Parse CCXT timestamp (milliseconds) to datetime.

        Falls back to current time when the exchange omits the timestamp,
        since WS message types require non-None datetime fields.

        Args:
            ts: Timestamp in milliseconds.

        Returns:
            Datetime object in UTC.
        """
        if ts is None:
            return datetime.now(UTC)
        return datetime.fromtimestamp(ts / 1000, tz=UTC)

    @staticmethod
    def _map_order_status(status: str) -> str:
        """Map CCXT order status to internal status.

        CCXT unified order statuses:
        - 'open': Order is open and active
        - 'closed': Order is fully filled
        - 'canceled': Order is canceled
        - 'expired': Order has expired
        - 'rejected': Order was rejected

        Args:
            status: CCXT order status.

        Returns:
            Internal order status.
        """
        status_map = {
            "open": "submitted",
            "closed": "filled",
            "canceled": "cancelled",
            "expired": "cancelled",
            "rejected": "rejected",
        }
        return status_map.get(status.lower(), status.lower())
