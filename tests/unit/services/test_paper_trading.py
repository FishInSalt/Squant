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
    engine.get_state_snapshot = MagicMock(
        return_value={
            "run_id": str(engine.run_id),
            "symbol": "BTC/USDT",
            "timeframe": "1m",
            "is_running": True,
            "bar_count": 100,
            "equity": "10500",
            "cash": "9000",
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
            mock_manager.get_subscribed_symbols.return_value = set()
            mock_manager.unregister = AsyncMock()
            mock_get_manager.return_value = mock_manager

            mock_stream = MagicMock()
            mock_stream.unsubscribe_candles = AsyncMock()
            mock_get_stream.return_value = mock_stream

            service = PaperTradingService(mock_session)
            await service.stop(run_id)

            mock_engine.stop.assert_called_once()
            mock_manager.unregister.assert_called_once()

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
