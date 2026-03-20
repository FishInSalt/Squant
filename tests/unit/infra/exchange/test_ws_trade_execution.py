from datetime import UTC, datetime
from decimal import Decimal

from squant.infra.exchange.ccxt.transformer import CCXTDataTransformer
from squant.infra.exchange.ws_types import WSTradeExecution


class TestWSTradeExecution:
    def test_create_from_fields(self):
        trade = WSTradeExecution(
            trade_id="t123456",
            order_id="o789",
            client_order_id="cli001",
            symbol="BTC/USDT",
            side="buy",
            price=Decimal("96500.00"),
            amount=Decimal("0.008"),
            fee=Decimal("0.077"),
            fee_currency="USDT",
            taker_or_maker="taker",
            timestamp=datetime(2026, 3, 20, 10, 30, 15, tzinfo=UTC),
        )
        assert trade.trade_id == "t123456"
        assert trade.order_id == "o789"
        assert trade.price == Decimal("96500.00")
        assert trade.amount == Decimal("0.008")
        assert trade.taker_or_maker == "taker"

    def test_defaults(self):
        trade = WSTradeExecution(
            trade_id="t1",
            order_id="o1",
            symbol="ETH/USDT",
            side="sell",
            price=Decimal("3000"),
            amount=Decimal("1"),
            timestamp=datetime.now(UTC),
        )
        assert trade.client_order_id is None
        assert trade.fee == Decimal("0")
        assert trade.fee_currency == ""
        assert trade.taker_or_maker is None


class TestTradeToWSTradeExecution:
    def test_transforms_ccxt_trade(self):
        ccxt_trade = {
            "id": "t001",
            "order": "o123",
            "clientOrderId": "cli001",
            "symbol": "BTC/USDT",
            "side": "buy",
            "price": 96500.0,
            "amount": 0.008,
            "fee": {"cost": 0.077, "currency": "USDT"},
            "takerOrMaker": "taker",
            "timestamp": 1711000215000,
        }
        result = CCXTDataTransformer.trade_to_ws_trade_execution(ccxt_trade)
        assert isinstance(result, WSTradeExecution)
        assert result.trade_id == "t001"
        assert result.order_id == "o123"
        assert result.client_order_id == "cli001"
        assert result.price == Decimal("96500.0")
        assert result.amount == Decimal("0.008")
        assert result.fee == Decimal("0.077")
        assert result.fee_currency == "USDT"
        assert result.taker_or_maker == "taker"

    def test_handles_missing_fields(self):
        ccxt_trade = {
            "id": "t002",
            "order": "o456",
            "symbol": "ETH/USDT",
            "side": "sell",
            "price": 3000.0,
            "amount": 1.0,
            "fee": None,
            "takerOrMaker": None,
            "timestamp": None,
        }
        result = CCXTDataTransformer.trade_to_ws_trade_execution(ccxt_trade)
        assert result.client_order_id is None
        assert result.fee == Decimal("0")
        assert result.fee_currency == ""
        assert result.taker_or_maker is None
        assert result.timestamp is not None  # falls back to utcnow
