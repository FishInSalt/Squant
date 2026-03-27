"""Tests for LiveTradingEngine event builder methods.

Covers _build_state_snapshot(), _build_bar_close_event(), and
_build_state_update_event() after the refactor that extracted shared
state-building logic.
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from squant.engine.backtest.strategy_base import Strategy
from squant.engine.backtest.types import Bar, Fill
from squant.engine.live.engine import EngineEvent, EngineEventType, LiveTradingEngine
from squant.engine.risk import RiskConfig
from squant.infra.exchange.types import AccountBalance, Balance, OrderResponse
from squant.models.enums import OrderSide, OrderStatus, OrderType

# ---------------------------------------------------------------------------
# Minimal strategy fixture
# ---------------------------------------------------------------------------


class NoOpStrategy(Strategy):
    """Strategy that does nothing — used only to construct an engine."""

    def on_init(self) -> None:
        pass

    def on_bar(self, bar: Bar) -> None:
        pass

    def on_stop(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def run_id():
    return uuid4()


@pytest.fixture
def risk_config():
    return RiskConfig(
        max_position_size=Decimal("0.5"),
        max_order_size=Decimal("0.1"),
        daily_trade_limit=100,
        daily_loss_limit=Decimal("0.1"),
        max_price_deviation=Decimal("0.05"),
        circuit_breaker_enabled=False,
        circuit_breaker_loss_count=5,
        circuit_breaker_cooldown_minutes=30,
    )


@pytest.fixture
def mock_adapter():
    adapter = AsyncMock()
    adapter.connect = AsyncMock()
    adapter.get_balance = AsyncMock(
        return_value=AccountBalance(
            exchange="okx",
            balances=[
                Balance(currency="USDT", available=Decimal("10000"), frozen=Decimal("0")),
            ],
        )
    )
    adapter.place_order = AsyncMock(
        return_value=OrderResponse(
            order_id="exchange-123",
            client_order_id=None,
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            status=OrderStatus.SUBMITTED,
            price=None,
            amount=Decimal("0.01"),
            filled=Decimal("0"),
        )
    )
    return adapter


@pytest.fixture
def engine(run_id, risk_config, mock_adapter):
    """Create a LiveTradingEngine with minimal configuration."""
    with patch("squant.config.get_settings") as mock_settings:
        settings = MagicMock()
        settings.paper_max_equity_curve_size = 10000
        settings.paper_max_completed_orders = 1000
        settings.paper_max_fills = 1000
        settings.paper_max_trades = 1000
        settings.paper_max_logs = 1000
        settings.strategy.max_bar_history = 1000
        mock_settings.return_value = settings

        return LiveTradingEngine(
            run_id=run_id,
            strategy=NoOpStrategy(),
            symbol="BTC/USDT",
            timeframe="1m",
            adapter=mock_adapter,
            risk_config=risk_config,
            initial_equity=Decimal("10000"),
            params={},
        )


# ---------------------------------------------------------------------------
# EngineEventType and EngineEvent tests
# ---------------------------------------------------------------------------


class TestEngineEventModel:
    def test_event_type_values(self):
        assert EngineEventType.WS_FILL == "ws_fill"
        assert EngineEventType.WS_ORDER == "ws_order"
        assert EngineEventType.BAR_CLOSE == "bar_close"

    def test_engine_event_is_frozen(self):
        """EngineEvent is a frozen dataclass — mutation must raise."""
        event = EngineEvent(
            type=EngineEventType.WS_FILL,
            data={"dummy": True},
            received_at=datetime.now(UTC),
        )
        with pytest.raises((AttributeError, TypeError)):
            event.type = EngineEventType.WS_ORDER  # type: ignore[misc]

    def test_engine_event_fields(self):
        now = datetime.now(UTC)
        payload = {"symbol": "BTC/USDT"}
        event = EngineEvent(type=EngineEventType.BAR_CLOSE, data=payload, received_at=now)
        assert event.type == EngineEventType.BAR_CLOSE
        assert event.data is payload
        assert event.received_at is now

    def test_engine_event_type_is_str_enum(self):
        """EngineEventType inherits from str — values compare equal to plain strings."""
        assert EngineEventType.WS_FILL == "ws_fill"
        assert isinstance(EngineEventType.WS_FILL, str)


# ---------------------------------------------------------------------------
# _build_state_snapshot tests
# ---------------------------------------------------------------------------


STATE_KEYS = {
    "cash",
    "equity",
    "unrealized_pnl",
    "realized_pnl",
    "total_fees",
    "fees_by_currency",
    "fees_usdt_equivalent",
    "completed_orders_count",
    "trades_count",
    "positions",
    "pending_orders",
    "open_trade",
    "risk_state",
}


class TestBuildStateSnapshot:
    def test_returns_4_tuple(self, engine: LiveTradingEngine):
        result = engine._build_state_snapshot()
        assert isinstance(result, tuple)
        assert len(result) == 4

    def test_state_dict_has_all_required_keys(self, engine: LiveTradingEngine):
        state, _, _, _ = engine._build_state_snapshot()
        assert set(state.keys()) == STATE_KEYS

    def test_numeric_values_are_strings(self, engine: LiveTradingEngine):
        state, _, _, _ = engine._build_state_snapshot()
        for key in ("cash", "equity", "unrealized_pnl", "realized_pnl", "total_fees"):
            assert isinstance(state[key], str), f"{key} should be a string"
            # Confirm it's a valid Decimal string
            Decimal(state[key])

    def test_initial_state_no_new_fills(self, engine: LiveTradingEngine):
        """Fresh engine should report no incremental fills/trades/logs."""
        _, new_fills, new_trades, new_logs = engine._build_state_snapshot()
        assert new_fills == []
        assert new_trades == []
        assert new_logs == []

    def test_delta_counter_updates_on_fill(self, engine: LiveTradingEngine):
        """After a fill is added to context, snapshot should report it once."""
        ctx = engine._context
        # Directly append a fill to simulate a fill being processed
        fill = Fill(
            order_id="test-order-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            price=Decimal("50000"),
            amount=Decimal("0.01"),
            fee=Decimal("0.5"),
            timestamp=datetime.now(UTC),
        )
        ctx._fills.append(fill)
        ctx._total_fills_added += 1

        # First snapshot call — should see exactly 1 new fill
        _, new_fills, _, _ = engine._build_state_snapshot()
        assert len(new_fills) == 1

        # Second snapshot call — counters were advanced, so delta should be 0
        _, new_fills2, _, _ = engine._build_state_snapshot()
        assert new_fills2 == []

    def test_delta_counter_updates_on_log(self, engine: LiveTradingEngine):
        """After a log entry is added, snapshot reports it once then resets."""
        ctx = engine._context
        ctx._logs.append("strategy: bought BTC/USDT")
        ctx._total_logs_added += 1

        _, _, _, new_logs = engine._build_state_snapshot()
        assert len(new_logs) == 1

        _, _, _, new_logs2 = engine._build_state_snapshot()
        assert new_logs2 == []

    def test_multiple_fills_accumulate(self, engine: LiveTradingEngine):
        """Two fills added between snapshots appear together in a single call."""
        ctx = engine._context
        for i in range(2):
            fill = Fill(
                order_id=f"order-{i}",
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                price=Decimal("50000"),
                amount=Decimal("0.01"),
                fee=Decimal("0.5"),
                timestamp=datetime.now(UTC),
            )
            ctx._fills.append(fill)
            ctx._total_fills_added += 1

        _, new_fills, _, _ = engine._build_state_snapshot()
        assert len(new_fills) == 2


# ---------------------------------------------------------------------------
# Helper: create a sample Bar for bar_close event tests
# ---------------------------------------------------------------------------


def _make_bar(
    time: datetime | None = None,
    close: Decimal = Decimal("50000"),
) -> Bar:
    """Create a minimal Bar for testing."""
    t = time or datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
    return Bar(
        time=t,
        symbol="BTC/USDT",
        open=Decimal("49900"),
        high=Decimal("50100"),
        low=Decimal("49800"),
        close=close,
        volume=Decimal("123.45"),
    )


# ---------------------------------------------------------------------------
# _build_bar_close_event regression tests
# ---------------------------------------------------------------------------


class TestBuildBarCloseEvent:
    def test_returns_dict_with_event_key(self, engine: LiveTradingEngine):
        bar = _make_bar()
        event = engine._build_bar_close_event(bar)
        assert isinstance(event, dict)
        assert event["event"] == "bar_close"

    def test_event_level_fields_present(self, engine: LiveTradingEngine):
        bar = _make_bar()
        event = engine._build_bar_close_event(bar)
        assert "run_id" in event
        assert "bar_count" in event
        assert "bar" in event
        assert "equity_point" in event
        assert "state" in event
        assert "new_fills" in event
        assert "new_trades" in event
        assert "new_logs" in event

    def test_state_nested_under_state_key(self, engine: LiveTradingEngine):
        """State fields must be nested under 'state' key (new format)."""
        bar = _make_bar()
        event = engine._build_bar_close_event(bar)
        assert "state" in event
        for key in STATE_KEYS:
            assert key in event["state"], f"'{key}' must be in event['state']"

    def test_bar_dict_has_ohlcv(self, engine: LiveTradingEngine):
        bar = _make_bar()
        event = engine._build_bar_close_event(bar)
        bar_dict = event["bar"]
        for field in ("time", "open", "high", "low", "close", "volume"):
            assert field in bar_dict, f"bar dict missing '{field}'"

    def test_equity_point_has_required_fields(self, engine: LiveTradingEngine):
        bar = _make_bar()
        event = engine._build_bar_close_event(bar)
        ep = event["equity_point"]
        for field in ("time", "equity", "cash", "position_value", "unrealized_pnl"):
            assert field in ep, f"equity_point missing '{field}'"

    def test_run_id_is_string(self, engine: LiveTradingEngine):
        bar = _make_bar()
        event = engine._build_bar_close_event(bar)
        assert isinstance(event["run_id"], str)

    def test_initial_empty_new_fills(self, engine: LiveTradingEngine):
        bar = _make_bar()
        event = engine._build_bar_close_event(bar)
        assert event["new_fills"] == []
        assert event["new_trades"] == []
        assert event["new_logs"] == []

    def test_fill_appears_in_event_then_gone(self, engine: LiveTradingEngine):
        """Fill shows up in the first event and not in the next (delta tracking)."""
        ctx = engine._context
        fill = Fill(
            order_id="order-bar",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            price=Decimal("50000"),
            amount=Decimal("0.01"),
            fee=Decimal("0.5"),
            timestamp=datetime.now(UTC),
        )
        ctx._fills.append(fill)
        ctx._total_fills_added += 1

        bar = _make_bar()
        event1 = engine._build_bar_close_event(bar)
        assert len(event1["new_fills"]) == 1

        event2 = engine._build_bar_close_event(bar)
        assert len(event2["new_fills"]) == 0

    def test_cash_is_decimal_string(self, engine: LiveTradingEngine):
        bar = _make_bar()
        event = engine._build_bar_close_event(bar)
        cash_val = event["state"]["cash"]
        assert isinstance(cash_val, str)
        Decimal(cash_val)  # must parse cleanly


# ---------------------------------------------------------------------------
# _build_state_update_event tests
# ---------------------------------------------------------------------------


class TestBuildStateUpdateEvent:
    def test_fill_trigger_detail(self, engine: LiveTradingEngine):
        """Fill trigger should populate trigger_detail with fill fields."""
        from squant.infra.exchange.ws_types import WSTradeExecution

        exec_data = WSTradeExecution(
            trade_id="t1",
            order_id="ex-1",
            symbol="BTC/USDT",
            side="buy",
            price=Decimal("50000"),
            amount=Decimal("0.01"),
            fee=Decimal("0.5"),
            fee_currency="USDT",
            timestamp=datetime.now(UTC),
        )
        event = engine._build_state_update_event("fill", exec_data)
        assert event["event"] == "state_update"
        assert event["trigger"] == "fill"
        detail = event["trigger_detail"]
        assert detail["order_id"] == "ex-1"
        assert detail["price"] == "50000"
        assert detail["amount"] == "0.01"
        assert detail["fee"] == "0.5"
        assert detail["fee_currency"] == "USDT"

    def test_order_update_trigger_detail_with_known_order(self, engine: LiveTradingEngine):
        """Order update trigger should resolve live_order for side/amount."""
        from squant.engine.live.engine import LiveOrder
        from squant.infra.exchange.ws_types import WSOrderUpdate

        # Set up a tracked order
        live_order = LiveOrder(
            internal_id="int-1",
            exchange_order_id="ex-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="market",
            amount=Decimal("0.05"),
            price=None,
        )
        engine._live_orders["int-1"] = live_order
        engine._exchange_order_map["ex-1"] = "int-1"

        update = WSOrderUpdate(
            order_id="ex-1",
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            status="filled",
            size=Decimal("0.05"),
            filled_size=Decimal("0.05"),
            avg_price=Decimal("50000"),
        )
        event = engine._build_state_update_event("order_update", update)
        detail = event["trigger_detail"]
        assert detail["order_id"] == "ex-1"
        assert detail["status"] == "filled"
        assert detail["side"] == "buy"
        assert detail["amount"] == "0.05"
        assert detail["filled_amount"] == "0.05"

    def test_order_update_trigger_detail_unknown_order(self, engine: LiveTradingEngine):
        """Order update for unknown exchange ID should still build event."""
        from squant.infra.exchange.ws_types import WSOrderUpdate

        update = WSOrderUpdate(
            order_id="unknown-ex-id",
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            status="filled",
            size=Decimal("0.01"),
            filled_size=Decimal("0.01"),
        )
        event = engine._build_state_update_event("order_update", update)
        detail = event["trigger_detail"]
        assert detail["side"] == ""
        assert detail["amount"] == "0"

    def test_unknown_trigger_has_empty_detail(self, engine: LiveTradingEngine):
        """Trigger types other than fill/order_update produce empty detail."""
        event = engine._build_state_update_event("something_else", {})
        assert event["trigger_detail"] == {}

    def test_state_key_present(self, engine: LiveTradingEngine):
        """state_update event has 'state' dict with all required keys."""
        event = engine._build_state_update_event("fill", MagicMock(price=Decimal("1")))
        assert "state" in event
        for key in STATE_KEYS:
            assert key in event["state"], f"state missing '{key}'"


# ---------------------------------------------------------------------------
# Delta tracking across event builders
# ---------------------------------------------------------------------------


class TestDeltaTrackingAcrossEvents:
    def test_fills_emitted_once_across_state_update_calls(self, engine: LiveTradingEngine):
        """Process 3 fills via _build_state_update_event, each sees exactly 1 new fill."""
        from squant.infra.exchange.ws_types import WSTradeExecution

        ctx = engine._context
        results = []
        for i in range(3):
            fill = Fill(
                order_id=f"order-{i}",
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                price=Decimal("50000"),
                amount=Decimal("0.01"),
                fee=Decimal("0.5"),
                timestamp=datetime.now(UTC),
            )
            ctx._fills.append(fill)
            ctx._total_fills_added += 1

            exec_data = WSTradeExecution(
                trade_id=f"t{i}",
                order_id=f"ex-{i}",
                symbol="BTC/USDT",
                price=Decimal("50000"),
                amount=Decimal("0.01"),
                fee=Decimal("0.5"),
                fee_currency="USDT",
                timestamp=datetime.now(UTC),
            )
            event = engine._build_state_update_event("fill", exec_data)
            results.append(len(event["new_fills"]))

        # Each call should see exactly 1 new fill (not cumulative)
        assert results == [1, 1, 1]

        # bar_close after all fills emitted should see 0 new fills
        bar = _make_bar()
        bar_event = engine._build_bar_close_event(bar)
        assert len(bar_event["new_fills"]) == 0


class TestFallbackFillFromOrderUpdate:
    def test_ws_order_fills_when_no_prior_ws_fill(self, engine: LiveTradingEngine):
        """_process_single_ws_update should record a fill when order reports filled
        and no prior WS_FILL was processed (fallback path)."""
        from squant.engine.live.engine import LiveOrder
        from squant.infra.exchange.ws_types import WSOrderUpdate

        # Set up a tracked order with no fills yet
        live_order = LiveOrder(
            internal_id="int-1",
            exchange_order_id="ex-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="market",
            amount=Decimal("0.01"),
            price=None,
            status=OrderStatus.SUBMITTED,
        )
        engine._live_orders["int-1"] = live_order
        engine._exchange_order_map["ex-1"] = "int-1"

        # Simulate WS_ORDER arriving with filled status (no prior WS_FILL)
        update = WSOrderUpdate(
            order_id="ex-1",
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            status="filled",
            size=Decimal("0.01"),
            filled_size=Decimal("0.01"),
            avg_price=Decimal("50000"),
            fee=Decimal("0.5"),
            fee_currency="USDT",
        )

        fills_before = engine._context._total_fills_added
        engine._process_single_ws_update(update)
        fills_after = engine._context._total_fills_added

        # The fallback fill path should have recorded a fill
        assert fills_after == fills_before + 1
        # The fill should be in context._fills
        assert len(engine._context._fills) == 1
        assert engine._context._fills[0].order_id == "int-1"
        assert engine._context._fills[0].price == Decimal("50000")
