"""Unit tests for paper trading service."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from squant.models.enums import RunMode, RunStatus
from squant.services.paper_trading import (
    EquityCurveRepository,
    PaperTradingError,
    PaperTradingService,
    SessionAlreadyRunningError,
    SessionNotFoundError,
    SessionNotResumableError,
    StrategyInstantiationError,
    StrategyRunRepository,
)


@pytest.fixture
def mock_session():
    """Create a mock database session."""
    session = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    session.add_all = MagicMock()
    return session


@pytest.fixture
def mock_strategy():
    """Create a mock strategy object."""
    strategy = MagicMock()
    strategy.id = str(uuid4())
    strategy.name = "Test Strategy"
    strategy.code = """
class TestStrategy(Strategy):
    def on_bar(self, bar):
        pass
"""
    return strategy


@pytest.fixture
def mock_run():
    """Create a mock strategy run object."""
    run = MagicMock()
    run.id = str(uuid4())
    run.strategy_id = str(uuid4())
    run.strategy_name = "Test Strategy"
    run.mode = RunMode.PAPER
    run.symbol = "BTC/USDT"
    run.exchange = "okx"
    run.timeframe = "1m"
    run.status = RunStatus.RUNNING
    run.initial_capital = Decimal("10000")
    run.commission_rate = Decimal("0.001")
    run.slippage = Decimal("0")
    run.params = {}
    run.error_message = None
    run.result = None
    run.started_at = datetime.now(UTC)
    run.stopped_at = None
    run.created_at = datetime.now(UTC)
    run.updated_at = datetime.now(UTC)
    return run


@pytest.fixture
def mock_equity_curve():
    """Create a mock equity curve record."""
    curve = MagicMock()
    curve.id = str(uuid4())
    curve.run_id = str(uuid4())
    curve.time = datetime.now(UTC)
    curve.equity = Decimal("10500")
    curve.cash = Decimal("9000")
    curve.position_value = Decimal("1500")
    curve.unrealized_pnl = Decimal("500")
    return curve


@pytest.fixture
def mock_engine():
    """Create a mock paper trading engine."""
    engine = MagicMock()
    engine.run_id = uuid4()
    engine.symbol = "BTC/USDT"
    engine.timeframe = "1m"
    engine.error_message = None
    engine.start = AsyncMock()
    engine.stop = AsyncMock()
    engine.get_pending_snapshots = MagicMock(return_value=[])
    # Result data for DB persistence (used by stop() and health check)
    result_data = {
        "cash": "9000",
        "equity": "10500",
        "total_fees": "15.5",
        "bar_count": 100,
        "realized_pnl": "500",
        "unrealized_pnl": "200",
        "positions": {"BTC/USDT": {"amount": "0.1", "avg_entry_price": "50000"}},
        "trades": [
            {
                "symbol": "BTC/USDT",
                "side": "buy",
                "entry_price": "50000",
                "exit_price": "51000",
                "amount": "0.1",
                "pnl": "100",
            }
        ],
        "open_trade": {
            "symbol": "BTC/USDT",
            "side": "buy",
            "entry_time": "2024-06-01T10:00:00+00:00",
            "entry_price": "50000",
            "amount": "0.1",
            "fees": "5.0",
            "partial_exit_pnl": "0",
        },
        "completed_orders_count": 5,
        "trades_count": 3,
        "logs": ["Log entry 1", "Log entry 2"],
    }
    engine.build_result_for_persistence = MagicMock(return_value=result_data)
    # API response snapshot (superset of result_data with extra fields)
    engine.get_state_snapshot = MagicMock(
        return_value={
            "run_id": str(engine.run_id),
            "symbol": "BTC/USDT",
            "timeframe": "1m",
            "is_running": True,
            "initial_capital": "10000",
            **result_data,
        }
    )
    return engine


class TestStrategyRunRepository:
    """Tests for StrategyRunRepository."""

    @pytest.mark.asyncio
    async def test_list_by_mode(self, mock_session, mock_run):
        """Test listing runs by mode."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_run]
        mock_session.execute.return_value = mock_result

        repo = StrategyRunRepository(mock_session)
        runs = await repo.list_by_mode(RunMode.PAPER)

        assert len(runs) == 1
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_by_mode_with_status(self, mock_session, mock_run):
        """Test listing runs by mode with status filter."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_run]
        mock_session.execute.return_value = mock_result

        repo = StrategyRunRepository(mock_session)
        runs = await repo.list_by_mode(RunMode.PAPER, status=RunStatus.RUNNING)

        assert len(runs) == 1
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_mark_orphaned_sessions(self, mock_session):
        """Test marking orphaned sessions as error."""
        mock_result = MagicMock()
        mock_result.rowcount = 2
        mock_session.execute.return_value = mock_result

        repo = StrategyRunRepository(mock_session)
        count = await repo.mark_orphaned_sessions()

        assert count == 2
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()


class TestEquityCurveRepository:
    """Tests for EquityCurveRepository."""

    @pytest.mark.asyncio
    async def test_bulk_create(self, mock_session):
        """Test bulk creating equity curve records."""
        records = [
            {
                "time": datetime.now(UTC),
                "run_id": str(uuid4()),
                "equity": Decimal("10500"),
                "cash": Decimal("9000"),
                "position_value": Decimal("1500"),
                "unrealized_pnl": Decimal("500"),
            }
        ]

        repo = EquityCurveRepository(mock_session)
        await repo.bulk_create(records)

        mock_session.add_all.assert_called_once()
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_bulk_create_empty(self, mock_session):
        """Test bulk create with empty list does nothing."""
        repo = EquityCurveRepository(mock_session)
        await repo.bulk_create([])

        mock_session.add_all.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_by_run(self, mock_session, mock_equity_curve):
        """Test getting equity curve by run ID."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_equity_curve]
        mock_session.execute.return_value = mock_result

        repo = EquityCurveRepository(mock_session)
        curves = await repo.get_by_run(mock_equity_curve.run_id)

        assert len(curves) == 1
        mock_session.execute.assert_called_once()


class TestPaperTradingService:
    """Tests for PaperTradingService."""

    @pytest.mark.asyncio
    async def test_get_run_success(self, mock_session, mock_run):
        """Test getting a paper trading run by ID."""
        with patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_run

            service = PaperTradingService(mock_session)
            result = await service.get_run(uuid4())

            assert result == mock_run
            mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_run_not_found(self, mock_session):
        """Test getting non-existent run raises error."""
        with patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            service = PaperTradingService(mock_session)

            with pytest.raises(SessionNotFoundError):
                await service.get_run(uuid4())

    @pytest.mark.asyncio
    async def test_list_runs(self, mock_session, mock_run):
        """Test listing paper trading runs."""
        with (
            patch.object(
                StrategyRunRepository, "list_by_mode", new_callable=AsyncMock
            ) as mock_list,
            patch.object(
                StrategyRunRepository, "count_by_mode", new_callable=AsyncMock
            ) as mock_count,
        ):
            mock_list.return_value = [mock_run]
            mock_count.return_value = 1

            service = PaperTradingService(mock_session)
            runs, total = await service.list_runs()

            assert len(runs) == 1
            assert total == 1
            mock_list.assert_called_once()
            mock_count.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_runs_with_status(self, mock_session, mock_run):
        """Test listing runs with status filter."""
        with (
            patch.object(
                StrategyRunRepository, "list_by_mode", new_callable=AsyncMock
            ) as mock_list,
            patch.object(
                StrategyRunRepository, "count_by_mode", new_callable=AsyncMock
            ) as mock_count,
        ):
            mock_list.return_value = [mock_run]
            mock_count.return_value = 1

            service = PaperTradingService(mock_session)
            runs, total = await service.list_runs(status=RunStatus.RUNNING)

            assert len(runs) == 1
            mock_list.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_active(self, mock_session):
        """Test listing active paper trading sessions."""
        with patch("squant.services.paper_trading.get_session_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.list_sessions.return_value = [
                {"run_id": str(uuid4()), "symbol": "BTC/USDT", "is_running": True}
            ]
            mock_get_manager.return_value = mock_manager

            service = PaperTradingService(mock_session)
            sessions = service.list_active()

            assert len(sessions) == 1
            assert sessions[0]["is_running"] is True

    @pytest.mark.asyncio
    async def test_get_status_active_session(self, mock_session, mock_run, mock_engine):
        """Test getting status of active session."""
        run_id = uuid4()

        with (
            patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get,
            patch("squant.services.paper_trading.get_session_manager") as mock_get_manager,
        ):
            mock_get.return_value = mock_run
            mock_manager = MagicMock()
            mock_manager.get.return_value = mock_engine
            mock_get_manager.return_value = mock_manager

            service = PaperTradingService(mock_session)
            status = await service.get_status(run_id)

            assert status["is_running"] is True
            assert "bar_count" in status

    @pytest.mark.asyncio
    async def test_get_status_inactive_session(self, mock_session, mock_run):
        """Test getting status of inactive session."""
        run_id = uuid4()
        mock_run.started_at = datetime.now(UTC)
        mock_run.stopped_at = datetime.now(UTC)

        with (
            patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get,
            patch("squant.services.paper_trading.get_session_manager") as mock_get_manager,
        ):
            mock_get.return_value = mock_run
            mock_manager = MagicMock()
            mock_manager.get.return_value = None  # No active engine
            mock_get_manager.return_value = mock_manager

            service = PaperTradingService(mock_session)
            status = await service.get_status(run_id)

            assert status["is_running"] is False

    @pytest.mark.asyncio
    async def test_get_status_not_found(self, mock_session):
        """Test getting status of non-existent session."""
        with patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            service = PaperTradingService(mock_session)

            with pytest.raises(SessionNotFoundError):
                await service.get_status(uuid4())

    @pytest.mark.asyncio
    async def test_get_equity_curve_success(self, mock_session, mock_run, mock_equity_curve):
        """Test getting equity curve for a run."""
        with (
            patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get,
            patch.object(
                EquityCurveRepository, "get_by_run", new_callable=AsyncMock
            ) as mock_get_curve,
        ):
            mock_get.return_value = mock_run
            mock_get_curve.return_value = [mock_equity_curve]

            service = PaperTradingService(mock_session)
            curves = await service.get_equity_curve(uuid4())

            assert len(curves) == 1
            mock_get.assert_called_once()
            mock_get_curve.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_equity_curve_not_found(self, mock_session):
        """Test getting equity curve for non-existent run."""
        with patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            service = PaperTradingService(mock_session)

            with pytest.raises(SessionNotFoundError):
                await service.get_equity_curve(uuid4())

    @pytest.mark.asyncio
    async def test_stop_session_success(self, mock_session, mock_run, mock_engine):
        """Test stopping a paper trading session."""
        run_id = uuid4()
        mock_run.id = str(run_id)

        with (
            patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get,
            patch.object(StrategyRunRepository, "update", new_callable=AsyncMock) as mock_update,
            patch("squant.services.paper_trading.get_session_manager") as mock_get_manager,
            patch("squant.services.paper_trading.get_stream_manager") as mock_get_stream,
        ):
            mock_get.return_value = mock_run
            mock_update.return_value = mock_run

            mock_manager = MagicMock()
            mock_manager.get.return_value = mock_engine
            # Return None means no unsubscribe needed (other sessions still using it)
            mock_manager.unregister_and_check_subscription = AsyncMock(return_value=None)
            mock_get_manager.return_value = mock_manager

            mock_stream = MagicMock()
            mock_stream.unsubscribe_candles = AsyncMock()
            mock_get_stream.return_value = mock_stream

            service = PaperTradingService(mock_session)
            await service.stop(run_id)

            mock_engine.stop.assert_called_once()
            mock_manager.unregister_and_check_subscription.assert_called_once_with(run_id)

    @pytest.mark.asyncio
    async def test_stop_session_with_unsubscribe(self, mock_session, mock_run, mock_engine):
        """Test stop session triggers unsubscribe when last session (Issue 021)."""
        run_id = uuid4()
        mock_run.id = str(run_id)
        mock_engine.symbol = "BTC/USDT"
        mock_engine.timeframe = "1m"

        with (
            patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get,
            patch.object(StrategyRunRepository, "update", new_callable=AsyncMock) as mock_update,
            patch("squant.services.paper_trading.get_session_manager") as mock_get_manager,
            patch("squant.services.paper_trading.get_stream_manager") as mock_get_stream,
        ):
            mock_get.return_value = mock_run
            mock_update.return_value = mock_run

            mock_manager = MagicMock()
            mock_manager.get.return_value = mock_engine
            # Return key means unsubscribe needed (last session)
            mock_manager.unregister_and_check_subscription = AsyncMock(
                return_value=("BTC/USDT", "1m")
            )
            mock_get_manager.return_value = mock_manager

            mock_stream = MagicMock()
            mock_stream.unsubscribe_candles = AsyncMock()
            mock_get_stream.return_value = mock_stream

            service = PaperTradingService(mock_session)
            await service.stop(run_id)

            # DB should be committed before unsubscribe (Issue 021 fix)
            mock_session.commit.assert_called_once()
            mock_stream.unsubscribe_candles.assert_called_once_with("BTC/USDT", "1m")

    @pytest.mark.asyncio
    async def test_stop_session_unsubscribe_failure_doesnt_fail(
        self, mock_session, mock_run, mock_engine
    ):
        """Test stop succeeds even if unsubscribe fails (Issue 021)."""
        run_id = uuid4()
        mock_run.id = str(run_id)
        mock_engine.symbol = "BTC/USDT"
        mock_engine.timeframe = "1m"

        with (
            patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get,
            patch.object(StrategyRunRepository, "update", new_callable=AsyncMock) as mock_update,
            patch("squant.services.paper_trading.get_session_manager") as mock_get_manager,
            patch("squant.services.paper_trading.get_stream_manager") as mock_get_stream,
        ):
            mock_get.return_value = mock_run
            mock_update.return_value = mock_run

            mock_manager = MagicMock()
            mock_manager.get.return_value = mock_engine
            mock_manager.unregister_and_check_subscription = AsyncMock(
                return_value=("BTC/USDT", "1m")
            )
            mock_get_manager.return_value = mock_manager

            mock_stream = MagicMock()
            # Simulate unsubscribe failure
            mock_stream.unsubscribe_candles = AsyncMock(side_effect=Exception("WS error"))
            mock_get_stream.return_value = mock_stream

            service = PaperTradingService(mock_session)
            # Should not raise despite unsubscribe failure
            result = await service.stop(run_id)

            # DB was still committed successfully
            mock_session.commit.assert_called_once()
            assert result is not None

    @pytest.mark.asyncio
    async def test_stop_session_not_found(self, mock_session):
        """Test stopping non-existent session."""
        with patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            service = PaperTradingService(mock_session)

            with pytest.raises(SessionNotFoundError):
                await service.stop(uuid4())

    @pytest.mark.asyncio
    async def test_persist_snapshots_no_engine(self, mock_session):
        """Test persisting snapshots when no engine exists."""
        with patch("squant.services.paper_trading.get_session_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get.return_value = None
            mock_get_manager.return_value = mock_manager

            service = PaperTradingService(mock_session)
            count = await service.persist_snapshots(uuid4())

            assert count == 0

    @pytest.mark.asyncio
    async def test_persist_snapshots_no_pending(self, mock_session, mock_engine):
        """Test persisting snapshots when none are pending."""
        mock_engine.get_pending_snapshots.return_value = []

        with patch("squant.services.paper_trading.get_session_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get.return_value = mock_engine
            mock_get_manager.return_value = mock_manager

            service = PaperTradingService(mock_session)
            count = await service.persist_snapshots(uuid4())

            assert count == 0

    @pytest.mark.asyncio
    async def test_persist_snapshots_success(self, mock_session, mock_engine):
        """Test persisting snapshots successfully."""
        mock_snapshot = MagicMock()
        mock_snapshot.time = datetime.now(UTC)
        mock_snapshot.equity = Decimal("10500")
        mock_snapshot.cash = Decimal("9000")
        mock_snapshot.position_value = Decimal("1500")
        mock_snapshot.unrealized_pnl = Decimal("500")
        mock_engine.get_pending_snapshots.return_value = [mock_snapshot]

        with patch("squant.services.paper_trading.get_session_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get.return_value = mock_engine
            mock_get_manager.return_value = mock_manager

            service = PaperTradingService(mock_session)
            count = await service.persist_snapshots(uuid4())

            assert count == 1
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_all_success(self, mock_session, mock_run, mock_engine):
        """Test stopping all active paper trading sessions."""
        run_id_1 = uuid4()
        run_id_2 = uuid4()

        with (
            patch("squant.services.paper_trading.get_session_manager") as mock_get_manager,
            patch.object(PaperTradingService, "stop", new_callable=AsyncMock) as mock_stop,
        ):
            mock_manager = MagicMock()
            mock_manager.list_sessions.return_value = [
                {"run_id": str(run_id_1), "symbol": "BTC/USDT", "is_running": True},
                {"run_id": str(run_id_2), "symbol": "ETH/USDT", "is_running": True},
            ]
            mock_get_manager.return_value = mock_manager
            mock_stop.return_value = mock_run

            service = PaperTradingService(mock_session)
            count = await service.stop_all()

            assert count == 2
            assert mock_stop.call_count == 2
            # Default: for_shutdown=False
            for call in mock_stop.call_args_list:
                assert call.kwargs.get("for_shutdown") is not True

    @pytest.mark.asyncio
    async def test_stop_all_for_shutdown(self, mock_session, mock_run):
        """Test stop_all passes for_shutdown flag to stop()."""
        run_id = uuid4()

        with (
            patch("squant.services.paper_trading.get_session_manager") as mock_get_manager,
            patch.object(PaperTradingService, "stop", new_callable=AsyncMock) as mock_stop,
        ):
            mock_manager = MagicMock()
            mock_manager.list_sessions.return_value = [
                {"run_id": str(run_id), "symbol": "BTC/USDT", "is_running": True},
            ]
            mock_get_manager.return_value = mock_manager
            mock_stop.return_value = mock_run

            service = PaperTradingService(mock_session)
            count = await service.stop_all(for_shutdown=True)

            assert count == 1
            mock_stop.assert_called_once_with(run_id, for_shutdown=True)

    @pytest.mark.asyncio
    async def test_stop_all_empty(self, mock_session):
        """Test stop_all when no sessions are active."""
        with patch("squant.services.paper_trading.get_session_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.list_sessions.return_value = []
            mock_get_manager.return_value = mock_manager

            service = PaperTradingService(mock_session)
            count = await service.stop_all()

            assert count == 0

    @pytest.mark.asyncio
    async def test_stop_all_partial_failure(self, mock_session, mock_run):
        """Test stop_all continues when one session fails to stop."""
        run_id_1 = uuid4()
        run_id_2 = uuid4()

        with (
            patch("squant.services.paper_trading.get_session_manager") as mock_get_manager,
            patch.object(PaperTradingService, "stop", new_callable=AsyncMock) as mock_stop,
        ):
            mock_manager = MagicMock()
            mock_manager.list_sessions.return_value = [
                {"run_id": str(run_id_1), "symbol": "BTC/USDT", "is_running": True},
                {"run_id": str(run_id_2), "symbol": "ETH/USDT", "is_running": True},
            ]
            mock_get_manager.return_value = mock_manager
            # First call fails, second succeeds
            mock_stop.side_effect = [Exception("Failed"), mock_run]

            service = PaperTradingService(mock_session)
            count = await service.stop_all()

            # Only 1 succeeded
            assert count == 1
            assert mock_stop.call_count == 2

    @pytest.mark.asyncio
    async def test_stop_saves_result_to_db(self, mock_session, mock_run, mock_engine):
        """Test that stop() captures engine state and saves to result JSONB field."""
        run_id = uuid4()
        mock_run.id = str(run_id)

        with (
            patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get,
            patch.object(StrategyRunRepository, "update", new_callable=AsyncMock) as mock_update,
            patch("squant.services.paper_trading.get_session_manager") as mock_get_manager,
            patch("squant.services.paper_trading.get_stream_manager") as mock_get_stream,
        ):
            mock_get.return_value = mock_run
            mock_update.return_value = mock_run

            mock_manager = MagicMock()
            mock_manager.get.return_value = mock_engine
            mock_manager.unregister_and_check_subscription = AsyncMock(return_value=None)
            mock_get_manager.return_value = mock_manager

            mock_stream = MagicMock()
            mock_stream.unsubscribe_candles = AsyncMock()
            mock_get_stream.return_value = mock_stream

            service = PaperTradingService(mock_session)
            await service.stop(run_id)

            # Verify update was called with result data
            update_call = mock_update.call_args
            assert update_call is not None
            kwargs = update_call.kwargs if update_call.kwargs else {}
            # Check positional + keyword args
            if not kwargs:
                # Args are positional: (run_id, status=..., result=..., ...)
                kwargs = {
                    k: v
                    for k, v in zip(
                        ["status", "result", "stopped_at", "error_message"],
                        update_call.args[1:] if len(update_call.args) > 1 else [],
                    )
                }
                kwargs.update(update_call.kwargs or {})

            assert "result" in kwargs
            result_data = kwargs["result"]
            assert result_data is not None
            assert result_data["cash"] == "9000"
            assert result_data["equity"] == "10500"
            assert result_data["trades_count"] == 3
            assert result_data["completed_orders_count"] == 5
            assert len(result_data["trades"]) == 1
            assert len(result_data["logs"]) == 2
            # Verify open_trade is preserved in result snapshot
            assert result_data["open_trade"] is not None
            assert result_data["open_trade"]["entry_time"] == "2024-06-01T10:00:00+00:00"
            assert result_data["open_trade"]["entry_price"] == "50000"

    @pytest.mark.asyncio
    async def test_stop_calls_engine_stop_before_capturing_result(
        self, mock_session, mock_run, mock_engine
    ):
        """Engine must be stopped before result is captured to prevent race conditions.

        If build_result_for_persistence() runs before engine.stop(), an awaited
        persist_snapshots could yield the event loop, allowing a candle to be
        processed between result capture and engine halt.
        """
        run_id = uuid4()
        mock_run.id = str(run_id)

        call_order: list[str] = []
        mock_engine.stop = AsyncMock(side_effect=lambda **kw: call_order.append("stop"))
        mock_engine.build_result_for_persistence = MagicMock(
            side_effect=lambda: (
                call_order.append("build_result"),
                {
                    "cash": "9000",
                    "equity": "10500",
                    "trades_count": 0,
                    "completed_orders_count": 0,
                    "trades": [],
                    "logs": [],
                    "open_trade": None,
                    "total_fees": "0",
                    "bar_count": 0,
                },
            )[1]
        )

        with (
            patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get,
            patch.object(StrategyRunRepository, "update", new_callable=AsyncMock) as mock_update,
            patch("squant.services.paper_trading.get_session_manager") as mock_get_manager,
        ):
            mock_get.return_value = mock_run
            mock_update.return_value = mock_run

            mock_manager = MagicMock()
            mock_manager.get.return_value = mock_engine
            mock_manager.unregister_and_check_subscription = AsyncMock(return_value=None)
            mock_get_manager.return_value = mock_manager

            service = PaperTradingService(mock_session)
            await service.stop(run_id)

            assert call_order == ["stop", "build_result"], (
                f"engine.stop() must be called BEFORE build_result_for_persistence(), "
                f"got: {call_order}"
            )

    @pytest.mark.asyncio
    async def test_stop_for_shutdown_marks_interrupted(self, mock_session, mock_run, mock_engine):
        """Test that stop(for_shutdown=True) marks session as INTERRUPTED."""
        run_id = uuid4()
        mock_run.id = str(run_id)

        with (
            patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get,
            patch.object(StrategyRunRepository, "update", new_callable=AsyncMock) as mock_update,
            patch("squant.services.paper_trading.get_session_manager") as mock_get_manager,
        ):
            mock_get.return_value = mock_run
            mock_update.return_value = mock_run

            mock_manager = MagicMock()
            mock_manager.get.return_value = mock_engine
            mock_manager.unregister_and_check_subscription = AsyncMock(return_value=None)
            mock_get_manager.return_value = mock_manager

            service = PaperTradingService(mock_session)
            await service.stop(run_id, for_shutdown=True)

            update_kwargs = mock_update.call_args.kwargs
            assert update_kwargs["status"] == RunStatus.INTERRUPTED
            assert "shutdown" in update_kwargs["error_message"]

    @pytest.mark.asyncio
    async def test_get_status_restores_from_result(self, mock_session, mock_run):
        """Test get_status() restores data from result JSONB when engine not in memory."""
        run_id = uuid4()
        mock_run.started_at = datetime.now(UTC)
        mock_run.stopped_at = datetime.now(UTC)
        mock_run.result = {
            "bar_count": 50,
            "cash": "8500",
            "equity": "10200",
            "total_fees": "12.5",
            "unrealized_pnl": "150",
            "realized_pnl": "350",
            "positions": {"BTC/USDT": {"amount": "0.05"}},
            "completed_orders_count": 4,
            "trades_count": 2,
            "trades": [{"symbol": "BTC/USDT", "pnl": "350"}],
            "logs": ["trade executed"],
        }

        with (
            patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get,
            patch("squant.services.paper_trading.get_session_manager") as mock_get_manager,
        ):
            mock_get.return_value = mock_run
            mock_manager = MagicMock()
            mock_manager.get.return_value = None  # No active engine
            mock_get_manager.return_value = mock_manager

            service = PaperTradingService(mock_session)
            status = await service.get_status(run_id)

            assert status["is_running"] is False
            assert status["bar_count"] == 50
            assert status["cash"] == "8500"
            assert status["equity"] == "10200"
            assert status["total_fees"] == "12.5"
            assert status["realized_pnl"] == "350"
            assert status["unrealized_pnl"] == "150"
            assert status["trades_count"] == 2
            assert status["completed_orders_count"] == 4
            assert len(status["trades"]) == 1
            assert len(status["logs"]) == 1

    @pytest.mark.asyncio
    async def test_get_status_fallback_without_result(self, mock_session, mock_run):
        """Test get_status() falls back to zero values when no result saved."""
        run_id = uuid4()
        mock_run.started_at = datetime.now(UTC)
        mock_run.stopped_at = datetime.now(UTC)
        mock_run.result = None

        with (
            patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get,
            patch("squant.services.paper_trading.get_session_manager") as mock_get_manager,
        ):
            mock_get.return_value = mock_run
            mock_manager = MagicMock()
            mock_manager.get.return_value = None
            mock_get_manager.return_value = mock_manager

            service = PaperTradingService(mock_session)
            status = await service.get_status(run_id)

            assert status["is_running"] is False
            assert status["bar_count"] == 0
            assert status["cash"] == str(mock_run.initial_capital)
            assert status["equity"] == str(mock_run.initial_capital)
            assert status["positions"] == {}

    @pytest.mark.asyncio
    async def test_mark_orphaned_sessions_preserves_existing_result(self, mock_session):
        """Test mark_orphaned_sessions preserves existing result from on_result callback."""
        run_id = str(uuid4())
        mock_run = MagicMock()
        mock_run.id = run_id
        # Simulate a complete result saved by the on_result callback
        mock_run.result = {
            "cash": "9000",
            "equity": "10500",
            "total_fees": "50",
            "unrealized_pnl": "200",
            "realized_pnl": "300",
            "positions": {"BTC/USDT": {"amount": "0.1", "avg_entry_price": "50000"}},
            "trades": [{"symbol": "BTC/USDT", "pnl": "300"}],
            "logs": ["[10:00] Buy BTC"],
        }

        with (
            patch.object(
                StrategyRunRepository, "get_orphaned_sessions", new_callable=AsyncMock
            ) as mock_get_orphaned,
            patch.object(
                EquityCurveRepository, "get_last_by_run", new_callable=AsyncMock
            ) as mock_get_last,
            patch.object(StrategyRunRepository, "update", new_callable=AsyncMock) as mock_update,
        ):
            mock_get_orphaned.return_value = [mock_run]
            mock_update.return_value = mock_run

            service = PaperTradingService(mock_session)
            count = await service.mark_orphaned_sessions()

            assert count == 1
            # Should NOT query equity curve since result already exists
            mock_get_last.assert_not_called()
            # Verify the complete result was preserved, not overwritten
            update_kwargs = mock_update.call_args.kwargs
            assert update_kwargs["result"]["realized_pnl"] == "300"
            assert update_kwargs["result"]["trades"] == [{"symbol": "BTC/USDT", "pnl": "300"}]
            assert update_kwargs["result"]["logs"] == ["[10:00] Buy BTC"]
            assert update_kwargs["status"] == RunStatus.INTERRUPTED

    @pytest.mark.asyncio
    async def test_mark_orphaned_sessions_falls_back_to_equity_curve(self, mock_session):
        """Test mark_orphaned_sessions falls back to equity curve when no result exists."""
        run_id = str(uuid4())
        mock_run = MagicMock()
        mock_run.id = run_id
        mock_run.result = None  # No result saved

        mock_equity = MagicMock()
        mock_equity.equity = Decimal("10500")
        mock_equity.cash = Decimal("9000")
        mock_equity.unrealized_pnl = Decimal("200")

        with (
            patch.object(
                StrategyRunRepository, "get_orphaned_sessions", new_callable=AsyncMock
            ) as mock_get_orphaned,
            patch.object(
                EquityCurveRepository, "get_last_by_run", new_callable=AsyncMock
            ) as mock_get_last,
            patch.object(StrategyRunRepository, "update", new_callable=AsyncMock) as mock_update,
        ):
            mock_get_orphaned.return_value = [mock_run]
            mock_get_last.return_value = mock_equity
            mock_update.return_value = mock_run

            service = PaperTradingService(mock_session)
            count = await service.mark_orphaned_sessions()

            assert count == 1
            mock_session.commit.assert_called_once()

            # Verify fallback result data from equity curve
            update_kwargs = mock_update.call_args.kwargs
            assert update_kwargs["result"] is not None
            assert update_kwargs["result"]["equity"] == "10500"
            assert update_kwargs["result"]["cash"] == "9000"
            assert update_kwargs["result"]["unrealized_pnl"] == "200"
            assert update_kwargs["status"] == RunStatus.INTERRUPTED

    @pytest.mark.asyncio
    async def test_mark_orphaned_sessions_without_equity_curve(self, mock_session):
        """Test mark_orphaned_sessions when no equity curve data and no result."""
        run_id = str(uuid4())
        mock_run = MagicMock()
        mock_run.id = run_id
        mock_run.result = None

        with (
            patch.object(
                StrategyRunRepository, "get_orphaned_sessions", new_callable=AsyncMock
            ) as mock_get_orphaned,
            patch.object(
                EquityCurveRepository, "get_last_by_run", new_callable=AsyncMock
            ) as mock_get_last,
            patch.object(StrategyRunRepository, "update", new_callable=AsyncMock) as mock_update,
        ):
            mock_get_orphaned.return_value = [mock_run]
            mock_get_last.return_value = None  # No equity curve data
            mock_update.return_value = mock_run

            service = PaperTradingService(mock_session)
            count = await service.mark_orphaned_sessions()

            assert count == 1
            update_kwargs = mock_update.call_args.kwargs
            assert update_kwargs["result"] is None

    @pytest.mark.asyncio
    async def test_mark_orphaned_sessions_no_orphans(self, mock_session):
        """Test mark_orphaned_sessions when no orphaned sessions exist."""
        with patch.object(
            StrategyRunRepository, "get_orphaned_sessions", new_callable=AsyncMock
        ) as mock_get_orphaned:
            mock_get_orphaned.return_value = []

            service = PaperTradingService(mock_session)
            count = await service.mark_orphaned_sessions()

            assert count == 0
            mock_session.commit.assert_not_called()


class TestSessionNotFoundError:
    """Tests for SessionNotFoundError."""

    def test_error_message(self):
        """Test error message formatting."""
        run_id = uuid4()
        error = SessionNotFoundError(run_id)

        assert str(run_id) in str(error)
        assert error.run_id == str(run_id)


class TestSessionAlreadyRunningError:
    """Tests for SessionAlreadyRunningError."""

    def test_error_message(self):
        """Test error message formatting."""
        run_id = uuid4()
        error = SessionAlreadyRunningError(run_id)

        assert str(run_id) in str(error)
        assert error.run_id == str(run_id)


class TestStrategyInstantiationError:
    """Tests for StrategyInstantiationError."""

    def test_error_message(self):
        """Test error message formatting."""
        error = StrategyInstantiationError("Failed to compile strategy")

        assert "Failed to compile strategy" in str(error)


class TestPaperTradingError:
    """Tests for PaperTradingError base class."""

    def test_error_message(self):
        """Test error message formatting."""
        error = PaperTradingError("Something went wrong")

        assert "Something went wrong" in str(error)


class TestSessionNotResumableError:
    """Tests for SessionNotResumableError."""

    def test_error_message(self):
        """Test error message formatting."""
        run_id = uuid4()
        error = SessionNotResumableError(run_id, "status is running")

        assert str(run_id) in str(error)
        assert "status is running" in str(error)
        assert error.run_id == str(run_id)


class TestMarkSessionInterrupted:
    """Tests for mark_session_interrupted with optional result parameter."""

    @pytest.mark.asyncio
    async def test_mark_interrupted_with_result(self, mock_session, mock_run):
        """Test that result data is saved when marking session as interrupted."""
        result_data = {"cash": "10000", "equity": "10500"}

        with (
            patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get,
            patch.object(StrategyRunRepository, "update", new_callable=AsyncMock) as mock_update,
        ):
            mock_get.return_value = mock_run
            mock_run.status = RunStatus.RUNNING

            service = PaperTradingService(mock_session)
            await service.mark_session_interrupted(uuid4(), "timeout", result=result_data)

            mock_update.assert_called_once()
            call_kwargs = mock_update.call_args.kwargs
            assert call_kwargs["result"] == result_data
            assert call_kwargs["status"] == RunStatus.INTERRUPTED

    @pytest.mark.asyncio
    async def test_mark_interrupted_without_result(self, mock_session, mock_run):
        """Test that result is None when not provided."""
        with (
            patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get,
            patch.object(StrategyRunRepository, "update", new_callable=AsyncMock) as mock_update,
        ):
            mock_get.return_value = mock_run
            mock_run.status = RunStatus.RUNNING

            service = PaperTradingService(mock_session)
            await service.mark_session_interrupted(uuid4(), "timeout")

            call_kwargs = mock_update.call_args.kwargs
            assert call_kwargs["result"] is None


class TestResumeSession:
    """Tests for PaperTradingService.resume() (Phase 3)."""

    @pytest.fixture
    def resumable_run(self, mock_run):
        """Create a run that is resumable (STOPPED with result)."""
        mock_run.status = RunStatus.STOPPED
        mock_run.result = {
            "cash": "9500",
            "total_fees": "50",
            "positions": {},
            "trades": [],
        }
        return mock_run

    @pytest.mark.asyncio
    async def test_resume_rejects_running_status(self, mock_session, mock_run):
        """Test that resume rejects sessions with RUNNING status."""
        mock_run.status = RunStatus.RUNNING

        with patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_run

            service = PaperTradingService(mock_session)
            with pytest.raises(SessionNotResumableError):
                await service.resume(uuid4())

    @pytest.mark.asyncio
    async def test_resume_rejects_completed_status(self, mock_session, mock_run):
        """Test that resume rejects sessions with COMPLETED status."""
        mock_run.status = RunStatus.COMPLETED

        with patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_run

            service = PaperTradingService(mock_session)
            with pytest.raises(SessionNotResumableError):
                await service.resume(uuid4())

    @pytest.mark.asyncio
    async def test_resume_accepts_error_status(self, mock_session, resumable_run, mock_strategy):
        """Test that resume accepts ERROR status sessions."""
        resumable_run.status = RunStatus.ERROR

        mock_settings = MagicMock()
        mock_settings.paper.max_sessions = 10
        mock_settings.paper.warmup_bars = 0

        mock_manager = MagicMock()
        mock_manager.session_count = 0
        mock_manager.register = AsyncMock()
        mock_manager.unregister_and_check_subscription = AsyncMock(return_value=None)

        mock_stream = MagicMock()
        mock_stream.subscribe_candles = AsyncMock()

        mock_engine = MagicMock()
        mock_engine.start = AsyncMock()
        mock_engine.is_running = False
        mock_engine.context = MagicMock()
        mock_engine.run_id = uuid4()

        with (
            patch.object(
                StrategyRunRepository, "get", new_callable=AsyncMock, return_value=resumable_run
            ),
            patch.object(
                StrategyRunRepository,
                "has_running_session",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch.object(
                StrategyRunRepository, "update", new_callable=AsyncMock, return_value=resumable_run
            ),
            patch("squant.config.get_settings", return_value=mock_settings),
            patch("squant.services.paper_trading.get_session_manager", return_value=mock_manager),
            patch("squant.services.paper_trading.get_stream_manager", return_value=mock_stream),
            patch("squant.services.paper_trading.PaperTradingEngine", return_value=mock_engine),
            patch("squant.services.strategy.StrategyRepository") as mock_strategy_repo_class,
        ):
            mock_strategy_repo = MagicMock()
            mock_strategy_repo.get = AsyncMock(return_value=mock_strategy)
            mock_strategy_repo_class.return_value = mock_strategy_repo

            service = PaperTradingService(mock_session)
            service._instantiate_strategy = MagicMock(return_value=MagicMock())

            result = await service.resume(uuid4(), warmup_bars=0)
            assert result is not None

    @pytest.mark.asyncio
    async def test_resume_accepts_interrupted_status(
        self, mock_session, resumable_run, mock_strategy
    ):
        """Test that resume accepts INTERRUPTED status sessions."""
        resumable_run.status = RunStatus.INTERRUPTED

        mock_settings = MagicMock()
        mock_settings.paper.max_sessions = 10
        mock_settings.paper.warmup_bars = 0

        mock_manager = MagicMock()
        mock_manager.session_count = 0
        mock_manager.register = AsyncMock()
        mock_manager.unregister_and_check_subscription = AsyncMock(return_value=None)

        mock_stream = MagicMock()
        mock_stream.subscribe_candles = AsyncMock()

        mock_engine = MagicMock()
        mock_engine.start = AsyncMock()
        mock_engine.is_running = False
        mock_engine.context = MagicMock()
        mock_engine.run_id = uuid4()

        with (
            patch.object(
                StrategyRunRepository, "get", new_callable=AsyncMock, return_value=resumable_run
            ),
            patch.object(
                StrategyRunRepository,
                "has_running_session",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch.object(
                StrategyRunRepository, "update", new_callable=AsyncMock, return_value=resumable_run
            ),
            patch("squant.config.get_settings", return_value=mock_settings),
            patch("squant.services.paper_trading.get_session_manager", return_value=mock_manager),
            patch("squant.services.paper_trading.get_stream_manager", return_value=mock_stream),
            patch("squant.services.paper_trading.PaperTradingEngine", return_value=mock_engine),
            patch("squant.services.strategy.StrategyRepository") as mock_strategy_repo_class,
        ):
            mock_strategy_repo = MagicMock()
            mock_strategy_repo.get = AsyncMock(return_value=mock_strategy)
            mock_strategy_repo_class.return_value = mock_strategy_repo

            service = PaperTradingService(mock_session)
            service._instantiate_strategy = MagicMock(return_value=MagicMock())

            result = await service.resume(uuid4(), warmup_bars=0)
            assert result is not None

    @pytest.mark.asyncio
    async def test_resume_not_found(self, mock_session):
        """Test that resume raises SessionNotFoundError for missing session."""
        with patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            service = PaperTradingService(mock_session)
            with pytest.raises(SessionNotFoundError):
                await service.resume(uuid4())

    @pytest.mark.asyncio
    async def test_resume_accepts_stopped_status(self, mock_session, resumable_run, mock_strategy):
        """Test that resume accepts STOPPED status sessions."""
        resumable_run.status = RunStatus.STOPPED

        mock_settings = MagicMock()
        mock_settings.paper.max_sessions = 10
        mock_settings.paper.warmup_bars = 0

        mock_manager = MagicMock()
        mock_manager.session_count = 0
        mock_manager.register = AsyncMock()
        mock_manager.unregister_and_check_subscription = AsyncMock(return_value=None)

        mock_stream = MagicMock()
        mock_stream.subscribe_candles = AsyncMock()

        mock_engine = MagicMock()
        mock_engine.start = AsyncMock()
        mock_engine.is_running = False
        mock_engine.context = MagicMock()
        mock_engine.run_id = uuid4()

        with (
            patch.object(
                StrategyRunRepository, "get", new_callable=AsyncMock, return_value=resumable_run
            ),
            patch.object(
                StrategyRunRepository,
                "has_running_session",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch.object(
                StrategyRunRepository, "update", new_callable=AsyncMock, return_value=resumable_run
            ),
            patch("squant.config.get_settings", return_value=mock_settings),
            patch("squant.services.paper_trading.get_session_manager", return_value=mock_manager),
            patch("squant.services.paper_trading.get_stream_manager", return_value=mock_stream),
            patch("squant.services.paper_trading.PaperTradingEngine", return_value=mock_engine),
            patch("squant.services.strategy.StrategyRepository") as mock_strategy_repo_class,
        ):
            mock_strategy_repo = MagicMock()
            mock_strategy_repo.get = AsyncMock(return_value=mock_strategy)
            mock_strategy_repo_class.return_value = mock_strategy_repo

            service = PaperTradingService(mock_session)
            service._instantiate_strategy = MagicMock(return_value=MagicMock())

            result = await service.resume(uuid4(), warmup_bars=0)
            assert result is not None

    @pytest.mark.asyncio
    async def test_resume_restores_state(self, mock_session, resumable_run, mock_strategy):
        """Test that resume calls restore_state and bar_count when result exists."""
        resumable_run.status = RunStatus.STOPPED
        resumable_run.result = {"cash": "5000", "positions": {}, "bar_count": 42}

        mock_settings = MagicMock()
        mock_settings.paper.max_sessions = 10

        mock_manager = MagicMock()
        mock_manager.session_count = 0
        mock_manager.register = AsyncMock()

        mock_stream = MagicMock()
        mock_stream.subscribe_candles = AsyncMock()

        mock_context = MagicMock()
        mock_engine = MagicMock()
        mock_engine.start = AsyncMock()
        mock_engine.is_running = False
        mock_engine.context = mock_context
        mock_engine.run_id = uuid4()

        with (
            patch.object(
                StrategyRunRepository, "get", new_callable=AsyncMock, return_value=resumable_run
            ),
            patch.object(
                StrategyRunRepository,
                "has_running_session",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch.object(
                StrategyRunRepository, "update", new_callable=AsyncMock, return_value=resumable_run
            ),
            patch("squant.config.get_settings", return_value=mock_settings),
            patch("squant.services.paper_trading.get_session_manager", return_value=mock_manager),
            patch("squant.services.paper_trading.get_stream_manager", return_value=mock_stream),
            patch("squant.services.paper_trading.PaperTradingEngine", return_value=mock_engine),
            patch("squant.services.strategy.StrategyRepository") as mock_strategy_repo_class,
        ):
            mock_strategy_repo = MagicMock()
            mock_strategy_repo.get = AsyncMock(return_value=mock_strategy)
            mock_strategy_repo_class.return_value = mock_strategy_repo

            service = PaperTradingService(mock_session)
            service._instantiate_strategy = MagicMock(return_value=MagicMock())

            await service.resume(uuid4(), warmup_bars=0)

            # Verify restore_state was called with the result data
            mock_context.restore_state.assert_called_once_with(resumable_run.result)

            # Verify bar_count is restored from persisted result
            assert mock_engine._bar_count == 42


class TestRecoverOrphanedSessions:
    """Tests for recover_orphaned_sessions (Phase 4)."""

    @pytest.mark.asyncio
    async def test_recovery_disabled_falls_back(self, mock_session):
        """Test that auto-recovery falls back to mark-as-error when disabled."""
        mock_settings = MagicMock()
        mock_settings.paper.auto_recovery = False

        with (
            patch("squant.config.get_settings", return_value=mock_settings),
            patch.object(
                PaperTradingService,
                "mark_orphaned_sessions",
                new_callable=AsyncMock,
                return_value=3,
            ) as mock_mark,
        ):
            service = PaperTradingService(mock_session)
            recovered, failed = await service.recover_orphaned_sessions()

            assert recovered == 0
            assert failed == 3
            mock_mark.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_orphaned_sessions(self, mock_session):
        """Test recovery with no orphaned sessions returns (0, 0)."""
        mock_settings = MagicMock()
        mock_settings.paper.auto_recovery = True

        with (
            patch("squant.config.get_settings", return_value=mock_settings),
            patch.object(
                StrategyRunRepository,
                "get_orphaned_sessions",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            service = PaperTradingService(mock_session)
            recovered, failed = await service.recover_orphaned_sessions()

            assert recovered == 0
            assert failed == 0

    @pytest.mark.asyncio
    async def test_recovery_with_no_result_marks_interrupted(self, mock_session, mock_run):
        """Test that orphaned session without result is marked as INTERRUPTED."""
        mock_run.status = RunStatus.RUNNING
        mock_run.result = None  # No saved state

        mock_settings = MagicMock()
        mock_settings.paper.auto_recovery = True
        mock_settings.paper.warmup_bars = 200

        with (
            patch("squant.config.get_settings", return_value=mock_settings),
            patch.object(
                StrategyRunRepository,
                "get_orphaned_sessions",
                new_callable=AsyncMock,
                return_value=[mock_run],
            ),
            patch.object(
                StrategyRunRepository,
                "update",
                new_callable=AsyncMock,
            ),
            patch.object(
                EquityCurveRepository,
                "get_last_by_run",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            service = PaperTradingService(mock_session)
            recovered, failed = await service.recover_orphaned_sessions()

            assert recovered == 0
            assert failed == 1

    @pytest.mark.asyncio
    async def test_recovery_resume_failure_marks_error(self, mock_session, mock_run):
        """Test that failed resume marks session as ERROR to prevent infinite retry."""
        mock_run.status = RunStatus.RUNNING
        mock_run.result = {"cash": "10000"}

        mock_settings = MagicMock()
        mock_settings.paper.auto_recovery = True
        mock_settings.paper.warmup_bars = 200

        mock_update = AsyncMock()

        with (
            patch("squant.config.get_settings", return_value=mock_settings),
            patch.object(
                StrategyRunRepository,
                "get_orphaned_sessions",
                new_callable=AsyncMock,
                return_value=[mock_run],
            ),
            patch.object(
                StrategyRunRepository,
                "update",
                new=mock_update,
            ),
            patch.object(
                PaperTradingService,
                "resume",
                new_callable=AsyncMock,
                side_effect=Exception("resume failed"),
            ),
            patch.object(
                EquityCurveRepository,
                "get_last_by_run",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            service = PaperTradingService(mock_session)
            recovered, failed = await service.recover_orphaned_sessions()

            assert recovered == 0
            assert failed == 1
            # Verify the second update call (after resume failure) sets ERROR status
            error_call = mock_update.call_args_list[-1]
            assert error_call.kwargs.get("status") == RunStatus.ERROR
            assert "resume failed" in error_call.kwargs.get("error_message", "")
