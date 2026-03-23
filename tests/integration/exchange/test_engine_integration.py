"""Layer 3 engine integration tests.

Tests verify that:
1. Strategy code loads correctly through the RestrictedPython sandbox
2. The order submission pipeline works end-to-end against OKX demo trading

Requirements:
    - OKX demo trading credentials in environment for order tests
      (OKX_API_KEY, OKX_API_SECRET, OKX_PASSPHRASE)
    - Network access to OKX sandbox API

Run:
    uv run pytest tests/integration/exchange/test_engine_integration.py -v
"""

import asyncio
import pathlib
from decimal import Decimal

import pytest

from squant.engine.backtest.strategy_base import Strategy
from squant.engine.sandbox import (
    CompiledStrategy,
    compile_strategy,
    validate_strategy_code,
)
from squant.infra.exchange.ccxt import CCXTRestAdapter
from squant.infra.exchange.types import OrderRequest, OrderResponse
from squant.models.enums import OrderSide, OrderStatus, OrderType

from .conftest import requires_okx_credentials

# Path to the test strategy templates
TEMPLATES_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "templates"

# All tests in this module are integration tests
pytestmark = [pytest.mark.integration]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEST_SYMBOL = "BTC/USDT"
SMALL_ORDER_AMOUNT = Decimal("0.0001")


def _load_template(name: str) -> str:
    """Read a strategy template file and return its source code."""
    path = TEMPLATES_DIR / name
    return path.read_text(encoding="utf-8")


# ===========================================================================
# Sandbox strategy loading
# ===========================================================================


class TestStrategyLoadsInSandbox:
    """Verify that the first_bar_buy strategy loads through the sandbox."""

    def test_validate_strategy_code_passes(self) -> None:
        """validate_strategy_code() accepts the first_bar_buy template."""
        code = _load_template("first_bar_buy.py")
        result = validate_strategy_code(code)

        # The validation should strip the sandbox-provided imports
        # internally during compile, but validate_strategy_code does
        # NOT strip them — it validates raw code. We need to check
        # that compile_strategy works (which does strip + validate).
        # validate_strategy_code checks structure only, so imports
        # of squant modules are fine at the AST level (they are not
        # in DISALLOWED_MODULES).
        assert result.valid, f"Validation errors: {result.errors}"
        assert result.strategy_info is not None
        assert result.strategy_info["class_name"] == "FirstBarBuyStrategy"
        assert result.strategy_info["has_on_bar"] is True

    def test_compile_strategy_succeeds(self) -> None:
        """compile_strategy() compiles the first_bar_buy template."""
        code = _load_template("first_bar_buy.py")
        compiled = compile_strategy(code)

        assert isinstance(compiled, CompiledStrategy)
        assert compiled.code_object is not None
        assert isinstance(compiled.restricted_globals, dict)
        # Strategy base class should be in globals
        assert "Strategy" in compiled.restricted_globals

    def test_strategy_instantiates_and_on_init_works(self) -> None:
        """Execute compiled code and instantiate the strategy class."""
        code = _load_template("first_bar_buy.py")
        compiled = compile_strategy(code)

        # Execute the code to define the class in a local namespace
        local_namespace: dict = {}
        exec(compiled.code_object, compiled.restricted_globals, local_namespace)

        # Find the strategy subclass
        strategy_class = None
        for _name, obj in local_namespace.items():
            if isinstance(obj, type) and issubclass(obj, Strategy) and obj is not Strategy:
                strategy_class = obj
                break

        assert strategy_class is not None, "No Strategy subclass found after exec"
        assert strategy_class.__name__ == "FirstBarBuyStrategy"

        # Instantiate and call on_init
        instance = strategy_class()
        assert isinstance(instance, Strategy)

        instance.on_init()
        assert instance.bought is False

    def test_bar_count_strategy_also_loads(self) -> None:
        """Verify bar_count.py template also loads through sandbox."""
        code = _load_template("bar_count.py")
        compiled = compile_strategy(code)

        local_namespace: dict = {}
        exec(compiled.code_object, compiled.restricted_globals, local_namespace)

        strategy_class = None
        for _name, obj in local_namespace.items():
            if isinstance(obj, type) and issubclass(obj, Strategy) and obj is not Strategy:
                strategy_class = obj
                break

        assert strategy_class is not None, "No Strategy subclass found for bar_count"
        instance = strategy_class()
        instance.on_init()
        assert instance.bar_count == 0

    def test_invalid_strategy_code_rejected(self) -> None:
        """Verify that code without a Strategy subclass is rejected."""
        bad_code = """
class NotAStrategy:
    def on_bar(self, bar):
        pass
"""
        result = validate_strategy_code(bad_code)
        assert not result.valid
        assert any("Strategy" in err for err in result.errors)


# ===========================================================================
# Order submission to exchange (requires OKX demo credentials)
# ===========================================================================


@requires_okx_credentials
@pytest.mark.okx_private
class TestOrderSubmissionToExchange:
    """Submit a real order to OKX demo, verify fill, and clean up."""

    async def test_market_buy_fill_and_sell_back(self, okx_adapter: CCXTRestAdapter) -> None:
        """Place a small market buy via the adapter, verify fill, sell back.

        This mirrors what the live/paper trading engine does when a strategy
        calls ctx.buy() — ultimately the engine submits an OrderRequest
        through the exchange adapter.
        """
        # -- 1. Place a market buy ------------------------------------------------
        buy_request = OrderRequest(
            symbol=TEST_SYMBOL,
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=SMALL_ORDER_AMOUNT,
        )

        buy_resp = await okx_adapter.place_order(buy_request)
        assert isinstance(buy_resp, OrderResponse)
        assert buy_resp.order_id, "Exchange must assign an order ID"
        assert buy_resp.symbol == TEST_SYMBOL
        assert buy_resp.side == OrderSide.BUY

        # -- 2. Wait for fill and verify ------------------------------------------
        await asyncio.sleep(2)

        buy_detail = await okx_adapter.get_order(TEST_SYMBOL, buy_resp.order_id)
        assert buy_detail.status == OrderStatus.FILLED, f"Expected FILLED, got {buy_detail.status}"
        assert buy_detail.filled > Decimal("0")

        if buy_detail.avg_price is not None:
            assert buy_detail.avg_price > Decimal("0"), "Fill price should be positive"

        # -- 3. Sell back to clean up the position --------------------------------
        sell_request = OrderRequest(
            symbol=TEST_SYMBOL,
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            amount=SMALL_ORDER_AMOUNT,
        )

        sell_resp = await okx_adapter.place_order(sell_request)
        assert isinstance(sell_resp, OrderResponse)
        assert sell_resp.order_id

        await asyncio.sleep(2)

        sell_detail = await okx_adapter.get_order(TEST_SYMBOL, sell_resp.order_id)
        assert sell_detail.status == OrderStatus.FILLED, (
            f"Sell-back expected FILLED, got {sell_detail.status}"
        )
        assert sell_detail.filled > Decimal("0")
