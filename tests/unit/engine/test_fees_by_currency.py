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


class TestPnlFeeConversion:
    """Verify that PnL calculation converts base currency fees to quote currency."""

    def test_base_fee_converted_in_pnl(self, ctx):
        """BTC fee should be converted to USDT in trade PnL calculation."""
        # Buy 0.01 BTC @ 50000, fee = 0.00001 BTC
        ctx._process_fill(Fill(
            order_id="o1", symbol="BTC/USDT", side=OrderSide.BUY,
            price=Decimal("50000"), amount=Decimal("0.01"),
            fee=Decimal("0.00001"), timestamp=datetime.now(UTC),
            fee_currency="BTC",
        ))
        assert ctx._open_trade is not None
        # Fee should be stored as USDT equivalent: 0.00001 * 50000 = 0.5
        assert ctx._open_trade.fees == Decimal("0.5")

        # Sell 0.00999 BTC @ 51000, fee = 0.5 USDT
        ctx._process_fill(Fill(
            order_id="o2", symbol="BTC/USDT", side=OrderSide.SELL,
            price=Decimal("51000"), amount=Decimal("0.00999"),
            fee=Decimal("0.5"), timestamp=datetime.now(UTC),
            fee_currency="USDT",
        ))
        # Trade should be closed
        assert ctx._open_trade is None
        assert len(ctx._trades) == 1

        trade = ctx._trades[0]
        # Total fees in USDT: 0.5 (converted BTC fee) + 0.5 (USDT fee) = 1.0
        assert trade.fees == Decimal("1.0")
        # PnL = (51000 - 50000) * 0.00999 - 1.0 = 9.99 - 1.0 = 8.99
        expected_pnl = Decimal("51000") * Decimal("0.00999") - Decimal("50000") * Decimal("0.00999") - Decimal("1.0")
        assert trade.pnl == expected_pnl

    def test_quote_fee_unchanged_in_pnl(self, ctx):
        """USDT fee should be used as-is in trade PnL calculation."""
        ctx._process_fill(Fill(
            order_id="o1", symbol="BTC/USDT", side=OrderSide.BUY,
            price=Decimal("50000"), amount=Decimal("0.01"),
            fee=Decimal("5"), timestamp=datetime.now(UTC),
            fee_currency="USDT",
        ))
        assert ctx._open_trade.fees == Decimal("5")

        ctx._process_fill(Fill(
            order_id="o2", symbol="BTC/USDT", side=OrderSide.SELL,
            price=Decimal("50000"), amount=Decimal("0.01"),
            fee=Decimal("5"), timestamp=datetime.now(UTC),
            fee_currency="USDT",
        ))
        trade = ctx._trades[0]
        assert trade.fees == Decimal("10")
        # Price didn't change, so PnL = 0 - 10 fees = -10
        assert trade.pnl == Decimal("-10")
