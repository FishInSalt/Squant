"""Tests for base currency fee handling in _process_fill.

When an exchange charges fees in the base currency (e.g., BTC for BTC/USDT),
the fee should reduce the position instead of affecting cash. This prevents
the engine from tracking more position than actually held, which would cause
sell orders to be rejected by the exchange ("oversell").
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from squant.engine.backtest.context import BacktestContext
from squant.engine.backtest.types import Fill
from squant.models.enums import OrderSide


@pytest.fixture
def ctx():
    """Create a BacktestContext with 10000 USDT cash."""
    return BacktestContext(
        initial_capital=Decimal("10000"),
        commission_rate=Decimal("0"),
        slippage=Decimal("0"),
    )


class TestBaseCurrencyFee:
    """Tests for _process_fill with fee_currency in base currency."""

    def test_buy_fee_in_base_currency_reduces_position(self, ctx):
        """BUY with base currency fee: position should be amount - fee."""
        fill = Fill(
            order_id="o1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            price=Decimal("50000"),
            amount=Decimal("0.1"),
            fee=Decimal("0.0001"),
            timestamp=datetime.now(UTC),
            fee_currency="BTC",
        )
        ctx._process_fill(fill)

        position = ctx._positions["BTC/USDT"]
        # Position should be 0.1 - 0.0001 = 0.0999
        assert position.amount == Decimal("0.0999")

    def test_buy_fee_in_base_currency_cash_not_charged_fee(self, ctx):
        """BUY with base currency fee: cash should only be price * amount (no fee)."""
        fill = Fill(
            order_id="o1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            price=Decimal("50000"),
            amount=Decimal("0.1"),
            fee=Decimal("0.0001"),
            timestamp=datetime.now(UTC),
            fee_currency="BTC",
        )
        ctx._process_fill(fill)

        # Cash: 10000 - (50000 * 0.1) = 5000 (fee NOT added to cost)
        assert ctx._cash == Decimal("5000")

    def test_buy_fee_in_quote_currency_default_behavior(self, ctx):
        """BUY with quote currency fee: cash includes fee (existing behavior)."""
        fill = Fill(
            order_id="o1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            price=Decimal("50000"),
            amount=Decimal("0.1"),
            fee=Decimal("5"),
            timestamp=datetime.now(UTC),
            fee_currency="USDT",
        )
        ctx._process_fill(fill)

        position = ctx._positions["BTC/USDT"]
        # Position: full 0.1 (fee in quote doesn't affect position)
        assert position.amount == Decimal("0.1")
        # Cash: 10000 - (50000 * 0.1 + 5) = 4995
        assert ctx._cash == Decimal("4995")

    def test_buy_fee_currency_none_default_behavior(self, ctx):
        """BUY with fee_currency=None: fee treated as quote currency (backward compat)."""
        fill = Fill(
            order_id="o1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            price=Decimal("50000"),
            amount=Decimal("0.1"),
            fee=Decimal("5"),
            timestamp=datetime.now(UTC),
            fee_currency=None,
        )
        ctx._process_fill(fill)

        position = ctx._positions["BTC/USDT"]
        assert position.amount == Decimal("0.1")
        assert ctx._cash == Decimal("4995")

    def test_sell_fee_in_base_currency_reduces_proceeds(self, ctx):
        """SELL with base currency fee: fee reduces effective sold amount, position goes to 0."""
        # Setup: buy first
        buy_fill = Fill(
            order_id="o1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            price=Decimal("50000"),
            amount=Decimal("0.1"),
            fee=Decimal("0"),
            timestamp=datetime.now(UTC),
        )
        ctx._process_fill(buy_fill)
        assert ctx._cash == Decimal("5000")

        # Sell with base currency fee
        sell_fill = Fill(
            order_id="o2",
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            price=Decimal("50000"),
            amount=Decimal("0.1"),
            fee=Decimal("0.0001"),
            timestamp=datetime.now(UTC),
            fee_currency="BTC",
        )
        ctx._process_fill(sell_fill)

        # Cash: 5000 + 50000 * (0.1 - 0.0001) = 5000 + 4995 = 9995
        # (fee deducted from sold amount, not from proceeds directly)
        assert ctx._cash == Decimal("9995")
        # Position: 0.1 - 0.1 = 0 (no fee deduction from position for SELL)
        position = ctx._positions["BTC/USDT"]
        assert position.amount == Decimal("0")

    def test_sell_fee_in_quote_currency_default_behavior(self, ctx):
        """SELL with quote currency fee: fee deducted from proceeds (existing behavior)."""
        # Setup: buy first
        buy_fill = Fill(
            order_id="o1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            price=Decimal("50000"),
            amount=Decimal("0.1"),
            fee=Decimal("0"),
            timestamp=datetime.now(UTC),
        )
        ctx._process_fill(buy_fill)

        sell_fill = Fill(
            order_id="o2",
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            price=Decimal("50000"),
            amount=Decimal("0.1"),
            fee=Decimal("5"),
            timestamp=datetime.now(UTC),
            fee_currency="USDT",
        )
        ctx._process_fill(sell_fill)

        # Cash: 5000 + (50000 * 0.1 - 5) = 9995
        assert ctx._cash == Decimal("9995")
        assert ctx._positions["BTC/USDT"].amount == Decimal("0")

    def test_force_buy_with_base_fee_insufficient_cash(self, ctx):
        """Force buy with base currency fee should work even with insufficient cash."""
        ctx._cash = Decimal("4000")  # Not enough for 50000 * 0.1 = 5000
        fill = Fill(
            order_id="o1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            price=Decimal("50000"),
            amount=Decimal("0.1"),
            fee=Decimal("0.0001"),
            timestamp=datetime.now(UTC),
            fee_currency="BTC",
        )
        ctx._process_fill(fill, force=True)

        position = ctx._positions["BTC/USDT"]
        assert position.amount == Decimal("0.0999")
        assert ctx._cash == Decimal("-1000")

    def test_total_fees_tracked_regardless_of_currency(self, ctx):
        """Total fees should accumulate regardless of fee currency."""
        fill = Fill(
            order_id="o1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            price=Decimal("50000"),
            amount=Decimal("0.1"),
            fee=Decimal("0.0001"),
            timestamp=datetime.now(UTC),
            fee_currency="BTC",
        )
        ctx._process_fill(fill)

        assert ctx._total_fees == Decimal("0.0001")
