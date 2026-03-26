"""Tests for per-currency fee tracking."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from squant.engine.backtest.context import BacktestContext
from squant.engine.backtest.types import Bar, Fill, OrderSide


@pytest.fixture
def ctx():
    return BacktestContext(initial_capital=Decimal("100000"))


class TestFeesByCurrency:
    def test_initial_fees_by_currency_empty(self, ctx):
        assert ctx._fees_by_currency == {}

    def test_quote_currency_fee(self, ctx):
        ctx._process_fill(Fill(
            order_id="o1", symbol="BTC/USDT", side=OrderSide.BUY,
            price=Decimal("50000"), amount=Decimal("0.1"),
            fee=Decimal("5"), timestamp=datetime.now(UTC),
            fee_currency=None,
        ))
        assert ctx._fees_by_currency == {"USDT": Decimal("5")}

    def test_base_currency_fee(self, ctx):
        ctx._process_fill(Fill(
            order_id="o2", symbol="BTC/USDT", side=OrderSide.BUY,
            price=Decimal("50000"), amount=Decimal("0.1"),
            fee=Decimal("0.0001"), timestamp=datetime.now(UTC),
            fee_currency="BTC",
        ))
        assert "BTC" in ctx._fees_by_currency
        assert ctx._fees_by_currency["BTC"] == Decimal("0.0001")

    def test_mixed_currencies_accumulate(self, ctx):
        ctx._process_fill(Fill(
            order_id="o1", symbol="BTC/USDT", side=OrderSide.BUY,
            price=Decimal("50000"), amount=Decimal("0.1"),
            fee=Decimal("5"), timestamp=datetime.now(UTC),
            fee_currency="USDT",
        ))
        ctx._process_fill(Fill(
            order_id="o2", symbol="BTC/USDT", side=OrderSide.BUY,
            price=Decimal("50000"), amount=Decimal("0.1"),
            fee=Decimal("0.0001"), timestamp=datetime.now(UTC),
            fee_currency="BTC",
        ))
        assert ctx._fees_by_currency["USDT"] == Decimal("5")
        assert ctx._fees_by_currency["BTC"] == Decimal("0.0001")
        assert ctx._total_fees == Decimal("5.0001")

    def test_snapshot_includes_fees_by_currency(self, ctx):
        ctx._process_fill(Fill(
            order_id="o1", symbol="BTC/USDT", side=OrderSide.BUY,
            price=Decimal("50000"), amount=Decimal("0.1"),
            fee=Decimal("5"), timestamp=datetime.now(UTC),
            fee_currency="USDT",
        ))
        snapshot = ctx.build_result_snapshot()
        assert "fees_by_currency" in snapshot
        assert snapshot["fees_by_currency"]["USDT"] == "5"

    def test_restore_state_fees_by_currency(self, ctx):
        state = {
            "cash": "100000",
            "total_fees": "5.0001",
            "fees_by_currency": {"USDT": "5", "BTC": "0.0001"},
        }
        ctx.restore_state(state)
        assert ctx._fees_by_currency["USDT"] == Decimal("5")
        assert ctx._fees_by_currency["BTC"] == Decimal("0.0001")

    def test_restore_state_without_fees_by_currency(self, ctx):
        state = {"cash": "100000", "total_fees": "5"}
        ctx.restore_state(state)
        assert ctx._fees_by_currency == {}


class TestFeesUsdtEquivalent:
    def test_usdt_equivalent_empty(self, ctx):
        assert ctx.get_fees_usdt_equivalent() == Decimal("0")

    def test_usdt_equivalent_single_currency(self, ctx):
        ctx._fees_by_currency = {"USDT": Decimal("10")}
        assert ctx.get_fees_usdt_equivalent() == Decimal("10")

    def test_usdt_equivalent_with_base_currency(self, ctx):
        ctx._fees_by_currency = {"USDT": Decimal("5"), "BTC": Decimal("0.0001")}
        bar = Bar(
            symbol="BTC/USDT", time=datetime.now(UTC),
            open=Decimal("50000"), high=Decimal("50000"),
            low=Decimal("50000"), close=Decimal("50000"),
            volume=Decimal("100"),
        )
        ctx._set_current_bar(bar)
        equiv = ctx.get_fees_usdt_equivalent()
        assert equiv == Decimal("10")  # 5 + 0.0001 * 50000

    def test_usdt_equivalent_no_price_returns_none(self, ctx):
        ctx._fees_by_currency = {"BTC": Decimal("0.0001")}
        assert ctx.get_fees_usdt_equivalent() is None
