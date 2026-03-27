"""Tests for LiveTradingEngine event builder methods.

Covers _build_state_snapshot() and _build_bar_update_event() after
the refactor that extracted shared state-building logic.
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
        assert STATE_KEYS == set(state.keys())

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
# _build_bar_update_event regression tests
# ---------------------------------------------------------------------------


class TestBuildBarUpdateEvent:
    def test_returns_dict_with_event_key(self, engine: LiveTradingEngine):
        event = engine._build_bar_update_event()
        assert isinstance(event, dict)
        assert event["event"] == "bar_update"

    def test_event_level_fields_present(self, engine: LiveTradingEngine):
        event = engine._build_bar_update_event()
        assert "run_id" in event
        assert "bar_count" in event
        assert "new_fills" in event
        assert "new_trades" in event
        assert "new_logs" in event

    def test_state_fields_at_top_level(self, engine: LiveTradingEngine):
        """State fields must be at the top level — not nested under a 'state' key."""
        event = engine._build_bar_update_event()
        for key in STATE_KEYS:
            assert key in event, f"'{key}' must be at top level of bar_update event"
        assert "state" not in event, "'state' key must NOT exist — fields are flattened"

    def test_run_id_is_string(self, engine: LiveTradingEngine):
        event = engine._build_bar_update_event()
        assert isinstance(event["run_id"], str)

    def test_initial_empty_new_fills(self, engine: LiveTradingEngine):
        event = engine._build_bar_update_event()
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

        event1 = engine._build_bar_update_event()
        assert len(event1["new_fills"]) == 1

        event2 = engine._build_bar_update_event()
        assert len(event2["new_fills"]) == 0

    def test_cash_is_decimal_string(self, engine: LiveTradingEngine):
        event = engine._build_bar_update_event()
        cash_val = event["cash"]
        assert isinstance(cash_val, str)
        Decimal(cash_val)  # must parse cleanly
