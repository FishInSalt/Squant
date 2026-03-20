from datetime import UTC, datetime
from decimal import Decimal

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
