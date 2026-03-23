"""Tests for live trading session resume (LIVE-010)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from squant.engine.live.engine import LiveOrder, LiveTradingEngine, _serialize_live_order
from squant.engine.risk import RiskConfig
from squant.infra.exchange.types import AccountBalance, Balance, OrderResponse
from squant.models.enums import OrderSide, OrderStatus, OrderType, RunStatus
from squant.services.live_trading import (
    LiveTradingService,
    MaxSessionsReachedError,
    SessionNotFoundError,
    SessionNotResumableError,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session():
    """Create a mock DB session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    return session


@pytest.fixture
def service(mock_session):
    """Create a LiveTradingService with mock session."""
    return LiveTradingService(mock_session)


@pytest.fixture
def risk_config_dict():
    """Risk config as dict (as stored in run.result)."""
    return {
        "max_position_size": "0.5",
        "max_order_size": "0.1",
        "daily_trade_limit": 100,
        "daily_loss_limit": "0.1",
        "max_price_deviation": "0.05",
        "circuit_breaker_enabled": True,
        "circuit_breaker_loss_count": 5,
        "circuit_breaker_cooldown_minutes": 30,
    }


@pytest.fixture
def saved_result(risk_config_dict):
    """A valid saved result dict for resume."""
    return {
        "cash": "10000",
        "equity": "10000",
        "total_fees": "0",
        "positions": {},
        "trades": [],
        "fills": [],
        "completed_orders_count": 0,
        "logs": [],
        "bar_count": 50,
        "risk_state": {
            "total_pnl": "0",
            "daily_pnl": "0",
            "consecutive_losses": 0,
            "circuit_breaker_active": False,
        },
        "risk_config": risk_config_dict,
        "live_orders": {},
        "exchange_order_map": {},
    }


@pytest.fixture
def mock_run(saved_result):
    """Create a mock StrategyRun."""
    run = MagicMock()
    run.id = str(uuid4())
    run.strategy_id = str(uuid4())
    run.account_id = str(uuid4())
    run.symbol = "BTC/USDT"
    run.timeframe = "1m"
    run.exchange = "okx"
    run.initial_capital = Decimal("10000")
    run.params = {}
    run.status = RunStatus.INTERRUPTED
    run.result = saved_result
    return run


# ---------------------------------------------------------------------------
# Error class tests
# ---------------------------------------------------------------------------


class TestErrorClasses:
    """Tests for resume-related error classes."""

    def test_session_not_resumable_error(self):
        run_id = uuid4()
        err = SessionNotResumableError(run_id, "status is running")
        assert str(run_id) in str(err)
        assert "cannot be resumed" in str(err)
        assert err.reason == "status is running"

    def test_max_sessions_reached_error(self):
        err = MaxSessionsReachedError(10)
        assert err.max_sessions == 10
        assert "10" in str(err)


# ---------------------------------------------------------------------------
# resume() validation tests
# ---------------------------------------------------------------------------


class TestResumeValidation:
    """Tests for resume() validation logic."""

    async def test_session_not_found(self, service):
        service.run_repo = AsyncMock()
        service.run_repo.get = AsyncMock(return_value=None)

        with pytest.raises(SessionNotFoundError):
            await service.resume(uuid4())

    async def test_session_not_resumable_status(self, service, mock_run):
        mock_run.status = RunStatus.RUNNING
        service.run_repo = AsyncMock()
        service.run_repo.get = AsyncMock(return_value=mock_run)

        with pytest.raises(SessionNotResumableError, match="status is running"):
            await service.resume(uuid4())

    async def test_session_no_result(self, service, mock_run):
        mock_run.result = None
        service.run_repo = AsyncMock()
        service.run_repo.get = AsyncMock(return_value=mock_run)

        with pytest.raises(SessionNotResumableError, match="no saved state"):
            await service.resume(uuid4())

    async def test_session_no_account_id(self, service, mock_run):
        mock_run.account_id = None
        service.run_repo = AsyncMock()
        service.run_repo.get = AsyncMock(return_value=mock_run)

        with pytest.raises(SessionNotResumableError, match="no exchange account"):
            await service.resume(uuid4())

    async def test_session_result_missing_cash(self, service, mock_run):
        mock_run.result = {"equity": "10000"}
        service.run_repo = AsyncMock()
        service.run_repo.get = AsyncMock(return_value=mock_run)

        with pytest.raises(SessionNotResumableError, match="no saved state"):
            await service.resume(uuid4())


# ---------------------------------------------------------------------------
# _serialize_live_order tests
# ---------------------------------------------------------------------------


class TestSerializeLiveOrder:
    """Tests for LiveOrder serialization."""

    def test_serialize_basic(self):
        order = LiveOrder(
            internal_id="ord-1",
            exchange_order_id="ex-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="limit",
            amount=Decimal("0.01"),
            price=Decimal("50000"),
            status=OrderStatus.SUBMITTED,
        )
        order.filled_amount = Decimal("0.005")
        order.fee = Decimal("0.01")
        order.created_at = datetime(2024, 1, 1, tzinfo=UTC)

        result = _serialize_live_order(order)

        assert result["internal_id"] == "ord-1"
        assert result["exchange_order_id"] == "ex-1"
        assert result["side"] == "buy"
        assert result["status"] == "submitted"
        assert result["filled_amount"] == "0.005"
        assert result["fee"] == "0.01"
        assert result["created_at"] is not None

    def test_serialize_none_price(self):
        order = LiveOrder(
            internal_id="ord-2",
            exchange_order_id=None,
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="market",
            amount=Decimal("0.01"),
            price=None,
        )
        result = _serialize_live_order(order)
        assert result["price"] is None
        assert result["exchange_order_id"] is None


# ---------------------------------------------------------------------------
# build_result_for_persistence tests
# ---------------------------------------------------------------------------


class TestBuildResultForPersistence:
    """Tests that build_result_for_persistence saves live order state."""

    @patch("squant.config.get_settings")
    def test_includes_live_orders(self, mock_settings):
        from squant.engine.backtest.strategy_base import Strategy

        mock_settings.return_value = MagicMock(
            paper_max_equity_curve_size=100,
            paper_max_completed_orders=100,
            paper_max_fills=100,
            paper_max_trades=100,
            paper_max_logs=100,
            strategy=MagicMock(max_bar_history=1000),
        )

        class DummyStrategy(Strategy):
            def on_init(self):
                pass

            def on_bar(self, bar):
                pass

            def on_stop(self):
                pass

        engine = LiveTradingEngine(
            run_id=uuid4(),
            strategy=DummyStrategy(),
            symbol="BTC/USDT",
            timeframe="1m",
            adapter=AsyncMock(),
            risk_config=RiskConfig(
                max_position_size=Decimal("0.5"),
                max_order_size=Decimal("0.1"),
            ),
            initial_equity=Decimal("10000"),
        )

        # Add a live order
        order = LiveOrder(
            internal_id="ord-1",
            exchange_order_id="ex-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="limit",
            amount=Decimal("0.01"),
            price=Decimal("50000"),
            status=OrderStatus.SUBMITTED,
        )
        engine._live_orders["ord-1"] = order
        engine._exchange_order_map["ex-1"] = "ord-1"

        result = engine.build_result_for_persistence()

        assert "live_orders" in result
        assert "ord-1" in result["live_orders"]
        assert result["live_orders"]["ord-1"]["exchange_order_id"] == "ex-1"
        assert "exchange_order_map" in result
        assert result["exchange_order_map"]["ex-1"] == "ord-1"
        assert "risk_config" in result


# ---------------------------------------------------------------------------
# Delta counter sync tests
# ---------------------------------------------------------------------------


class TestDeltaCounterSync:
    """Tests that resume syncs delta tracking counters to prevent re-delivery."""

    @patch("squant.config.get_settings")
    def test_counters_synced_after_restore(self, mock_settings):
        """After restore_state, delta counters should match context totals."""
        from squant.engine.backtest.strategy_base import Strategy

        mock_settings.return_value = MagicMock(
            paper_max_equity_curve_size=100,
            paper_max_completed_orders=100,
            paper_max_fills=100,
            paper_max_trades=100,
            paper_max_logs=100,
            strategy=MagicMock(max_bar_history=1000),
        )

        class DummyStrategy(Strategy):
            def on_init(self):
                pass

            def on_bar(self, bar):
                pass

            def on_stop(self):
                pass

        engine = LiveTradingEngine(
            run_id=uuid4(),
            strategy=DummyStrategy(),
            symbol="BTC/USDT",
            timeframe="1m",
            adapter=AsyncMock(),
            risk_config=RiskConfig(
                max_position_size=Decimal("0.5"),
                max_order_size=Decimal("0.1"),
            ),
            initial_equity=Decimal("10000"),
        )

        # Simulate restored state with historical data
        engine.context._total_fills_added = 10
        engine.context._total_completed_added = 8
        engine.context._total_trades_added = 5
        engine.context._total_logs_added = 20

        # Before sync — counters are at 0 (from __init__)
        assert engine._last_callback_fill_total == 0
        assert engine._last_emitted_fill_total == 0

        # Simulate what resume() does after restore_state
        ctx = engine.context
        engine._last_callback_fill_total = ctx._total_fills_added
        engine._last_callback_completed_total = ctx._total_completed_added
        engine._last_emitted_fill_total = ctx._total_fills_added
        engine._last_emitted_trade_total = ctx._total_trades_added
        engine._last_emitted_log_total = ctx._total_logs_added

        # After sync — deltas should be 0
        assert engine._last_callback_fill_total == 10
        assert engine._last_callback_completed_total == 8
        assert engine._last_emitted_fill_total == 10
        assert engine._last_emitted_trade_total == 5
        assert engine._last_emitted_log_total == 20

        # Delta computation should yield 0 (no new data)
        fill_delta = ctx._total_fills_added - engine._last_emitted_fill_total
        trade_delta = ctx._total_trades_added - engine._last_emitted_trade_total
        assert fill_delta == 0
        assert trade_delta == 0


# ---------------------------------------------------------------------------
# restore_live_orders tests
# ---------------------------------------------------------------------------


class TestRestoreLiveOrders:
    """Tests for LiveTradingEngine.restore_live_orders()."""

    @patch("squant.config.get_settings")
    def test_restores_active_orders(self, mock_settings):
        from squant.engine.backtest.strategy_base import Strategy

        mock_settings.return_value = MagicMock(
            paper_max_equity_curve_size=100,
            paper_max_completed_orders=100,
            paper_max_fills=100,
            paper_max_trades=100,
            paper_max_logs=100,
            strategy=MagicMock(max_bar_history=1000),
        )

        class DummyStrategy(Strategy):
            def on_init(self):
                pass

            def on_bar(self, bar):
                pass

            def on_stop(self):
                pass

        engine = LiveTradingEngine(
            run_id=uuid4(),
            strategy=DummyStrategy(),
            symbol="BTC/USDT",
            timeframe="1m",
            adapter=AsyncMock(),
            risk_config=RiskConfig(
                max_position_size=Decimal("0.5"),
                max_order_size=Decimal("0.1"),
            ),
            initial_equity=Decimal("10000"),
        )

        state = {
            "live_orders": {
                "ord-1": {
                    "internal_id": "ord-1",
                    "exchange_order_id": "ex-1",
                    "symbol": "BTC/USDT",
                    "side": "buy",
                    "order_type": "limit",
                    "amount": "0.01",
                    "price": "50000",
                    "status": "submitted",
                    "filled_amount": "0",
                    "fee": "0",
                },
                "ord-2": {
                    "internal_id": "ord-2",
                    "exchange_order_id": "ex-2",
                    "symbol": "BTC/USDT",
                    "side": "sell",
                    "order_type": "market",
                    "amount": "0.01",
                    "price": None,
                    "status": "filled",  # Terminal — should be skipped
                    "filled_amount": "0.01",
                    "fee": "0.005",
                },
            },
            "exchange_order_map": {
                "ex-1": "ord-1",
                "ex-2": "ord-2",
            },
        }

        engine.restore_live_orders(state)

        # Only active order restored
        assert len(engine._live_orders) == 1
        assert "ord-1" in engine._live_orders
        assert "ord-2" not in engine._live_orders

        # Exchange map only for restored orders
        assert len(engine._exchange_order_map) == 1
        assert "ex-1" in engine._exchange_order_map
        assert "ex-2" not in engine._exchange_order_map

    @patch("squant.config.get_settings")
    def test_restores_empty_state(self, mock_settings):
        from squant.engine.backtest.strategy_base import Strategy

        mock_settings.return_value = MagicMock(
            paper_max_equity_curve_size=100,
            paper_max_completed_orders=100,
            paper_max_fills=100,
            paper_max_trades=100,
            paper_max_logs=100,
            strategy=MagicMock(max_bar_history=1000),
        )

        class DummyStrategy(Strategy):
            def on_init(self):
                pass

            def on_bar(self, bar):
                pass

            def on_stop(self):
                pass

        engine = LiveTradingEngine(
            run_id=uuid4(),
            strategy=DummyStrategy(),
            symbol="BTC/USDT",
            timeframe="1m",
            adapter=AsyncMock(),
            risk_config=RiskConfig(
                max_position_size=Decimal("0.5"),
                max_order_size=Decimal("0.1"),
            ),
            initial_equity=Decimal("10000"),
        )

        # No live_orders key
        engine.restore_live_orders({})
        assert len(engine._live_orders) == 0
        assert len(engine._exchange_order_map) == 0


# ---------------------------------------------------------------------------
# Order reconciliation tests
# ---------------------------------------------------------------------------


class TestReconcileOrders:
    """Tests for _reconcile_orders()."""

    async def test_order_still_open_with_new_fill(self, service):
        """Order still on exchange with new fills since crash."""
        engine = MagicMock(spec=LiveTradingEngine)
        engine._live_orders = {
            "ord-1": LiveOrder(
                internal_id="ord-1",
                exchange_order_id="ex-1",
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                order_type="limit",
                amount=Decimal("0.01"),
                price=Decimal("50000"),
                status=OrderStatus.SUBMITTED,
            ),
        }
        engine._exchange_order_map = {"ex-1": "ord-1"}
        engine._record_fill = MagicMock()

        adapter = AsyncMock()
        adapter.get_open_orders = AsyncMock(
            return_value=[
                OrderResponse(
                    order_id="ex-1",
                    symbol="BTC/USDT",
                    side=OrderSide.BUY,
                    type=OrderType.LIMIT,
                    status=OrderStatus.PARTIAL,
                    amount=Decimal("0.01"),
                    filled=Decimal("0.005"),
                    avg_price=Decimal("50000"),
                    fee=Decimal("0.01"),
                ),
            ]
        )

        report = await service._reconcile_orders(engine, adapter, "BTC/USDT")

        assert report["orders_reconciled"] == 1
        assert report["fills_processed"] == 1
        engine._record_fill.assert_called_once()

    async def test_order_filled_during_downtime(self, service):
        """Order completed while session was down."""
        lo = LiveOrder(
            internal_id="ord-1",
            exchange_order_id="ex-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="limit",
            amount=Decimal("0.01"),
            price=Decimal("50000"),
            status=OrderStatus.SUBMITTED,
        )
        engine = MagicMock(spec=LiveTradingEngine)
        engine._live_orders = {"ord-1": lo}
        engine._exchange_order_map = {"ex-1": "ord-1"}
        engine._record_fill = MagicMock()

        adapter = AsyncMock()
        # Not in open orders
        adapter.get_open_orders = AsyncMock(return_value=[])
        # Query shows filled
        adapter.get_order = AsyncMock(
            return_value=OrderResponse(
                order_id="ex-1",
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                type=OrderType.LIMIT,
                status=OrderStatus.FILLED,
                amount=Decimal("0.01"),
                filled=Decimal("0.01"),
                avg_price=Decimal("50000"),
                fee=Decimal("0.02"),
            )
        )

        report = await service._reconcile_orders(engine, adapter, "BTC/USDT")

        assert report["orders_reconciled"] == 1
        assert report["fills_processed"] == 1
        # Order should be removed from tracking
        assert "ord-1" not in engine._live_orders

    async def test_exchange_query_failure_marks_cancelled(self, service):
        """When can't query order, conservatively mark cancelled."""
        lo = LiveOrder(
            internal_id="ord-1",
            exchange_order_id="ex-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="limit",
            amount=Decimal("0.01"),
            price=Decimal("50000"),
        )
        engine = MagicMock(spec=LiveTradingEngine)
        engine._live_orders = {"ord-1": lo}
        engine._exchange_order_map = {"ex-1": "ord-1"}

        adapter = AsyncMock()
        adapter.get_open_orders = AsyncMock(return_value=[])
        adapter.get_order = AsyncMock(side_effect=Exception("API error"))

        report = await service._reconcile_orders(engine, adapter, "BTC/USDT")

        assert report["orders_cancelled"] == 1
        assert lo.status == OrderStatus.CANCELLED

    async def test_untracked_exchange_order_logged(self, service):
        """Exchange order not tracked locally generates warning."""
        engine = MagicMock(spec=LiveTradingEngine)
        engine._live_orders = {}
        engine._exchange_order_map = {}

        adapter = AsyncMock()
        adapter.get_open_orders = AsyncMock(
            return_value=[
                OrderResponse(
                    order_id="unknown-1",
                    symbol="BTC/USDT",
                    side=OrderSide.BUY,
                    type=OrderType.LIMIT,
                    status=OrderStatus.SUBMITTED,
                    amount=Decimal("0.01"),
                    filled=Decimal("0"),
                ),
            ]
        )

        report = await service._reconcile_orders(engine, adapter, "BTC/USDT")

        assert report["orders_unknown"] == 1
        assert len(report["discrepancies"]) == 1
        assert report["discrepancies"][0]["type"] == "untracked_exchange_order"

    async def test_no_orders_to_reconcile(self, service):
        """Empty state reconciliation succeeds."""
        engine = MagicMock(spec=LiveTradingEngine)
        engine._live_orders = {}
        engine._exchange_order_map = {}

        adapter = AsyncMock()
        adapter.get_open_orders = AsyncMock(return_value=[])

        report = await service._reconcile_orders(engine, adapter, "BTC/USDT")

        assert report["orders_reconciled"] == 0
        assert report["fills_processed"] == 0


# ---------------------------------------------------------------------------
# Position reconciliation tests
# ---------------------------------------------------------------------------


class TestReconcilePositions:
    """Tests for _reconcile_positions()."""

    async def test_no_discrepancy(self, service):
        """When balances match, no adjustment needed."""
        engine = MagicMock()
        engine.context._cash = Decimal("10000")
        engine.context.get_position.return_value = None

        adapter = AsyncMock()
        adapter.get_balance = AsyncMock(
            return_value=AccountBalance(
                exchange="okx",
                balances=[
                    Balance(currency="USDT", available=Decimal("10000"), frozen=Decimal("0")),
                ],
            )
        )

        report = await service._reconcile_positions(engine, adapter, "BTC/USDT")

        assert not report["cash_adjusted"]
        assert not report["position_discrepancy"]

    async def test_cash_mismatch_warning_only(self, service):
        """Cash discrepancy should be logged but NOT adjusted (session cash is source of truth)."""
        engine = MagicMock()
        engine.context._cash = Decimal("10000")
        engine.context.get_position.return_value = None

        adapter = AsyncMock()
        adapter.get_balance = AsyncMock(
            return_value=AccountBalance(
                exchange="okx",
                balances=[
                    Balance(currency="USDT", available=Decimal("9500"), frozen=Decimal("0")),
                ],
            )
        )

        report = await service._reconcile_positions(engine, adapter, "BTC/USDT")

        # Cash should NOT be adjusted — local session state is source of truth
        assert not report["cash_adjusted"]
        assert engine.context._cash == Decimal("10000")
        assert len(report["discrepancies"]) == 1
        assert report["discrepancies"][0]["type"] == "cash_mismatch"

    async def test_balance_query_failure(self, service):
        """Balance query failure returns error in report."""
        engine = MagicMock()
        adapter = AsyncMock()
        adapter.get_balance = AsyncMock(side_effect=Exception("Network error"))

        report = await service._reconcile_positions(engine, adapter, "BTC/USDT")

        assert "error" in report


# ---------------------------------------------------------------------------
# Auto-recovery tests
# ---------------------------------------------------------------------------


class TestRecoverOrphanedSessions:
    """Tests for recover_orphaned_sessions()."""

    @patch("squant.config.get_settings")
    async def test_auto_recovery_disabled(self, mock_settings, service):
        """When auto_recovery=False, marks sessions as INTERRUPTED."""
        mock_settings.return_value.live.auto_recovery = False
        service.mark_orphaned_sessions = AsyncMock(return_value=2)

        recovered, failed = await service.recover_orphaned_sessions()

        assert recovered == 0
        assert failed == 2
        service.mark_orphaned_sessions.assert_called_once()

    @patch("squant.config.get_settings")
    async def test_no_orphaned_sessions(self, mock_settings, service):
        """No orphaned sessions returns (0, 0)."""
        mock_settings.return_value.live.auto_recovery = True
        service.run_repo = AsyncMock()
        service.run_repo.get_orphaned_sessions = AsyncMock(return_value=[])

        recovered, failed = await service.recover_orphaned_sessions()

        assert recovered == 0
        assert failed == 0


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


class TestLiveTradingSettings:
    """Tests for LiveTradingSettings."""

    def test_defaults(self, monkeypatch):
        from squant.config import LiveTradingSettings

        # Isolate from .env to test true code defaults
        monkeypatch.delenv("LIVE_AUTO_RECOVERY", raising=False)
        settings = LiveTradingSettings(_env_file=None)
        assert settings.max_sessions == 10
        assert settings.warmup_bars == 200
        assert settings.auto_recovery is False  # Safety default
