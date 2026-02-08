"""Unit tests for backtest service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from squant.models.enums import RunMode, RunStatus
from squant.services.backtest import (
    MIN_INITIAL_CAPITAL,
    BacktestNotFoundError,
    BacktestService,
    EquityCurveRepository,
    IncompleteDataError,
    InsufficientDataError,
    InvalidInitialCapitalError,
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
    strategy.code = """from squant.engine.sandbox import Strategy

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
    run.mode = RunMode.BACKTEST
    run.symbol = "BTC/USDT"
    run.exchange = "okx"
    run.timeframe = "1h"
    run.status = RunStatus.PENDING
    run.progress = 0.0
    run.initial_capital = Decimal("10000")
    run.commission_rate = Decimal("0.001")
    run.slippage = Decimal("0")
    run.backtest_start = datetime.now(UTC) - timedelta(days=30)
    run.backtest_end = datetime.now(UTC)
    run.params = {}
    run.result = None
    run.error_message = None
    run.started_at = None
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
def mock_data_availability():
    """Create a mock data availability object with complete data."""
    now = datetime.now(UTC)
    start = now - timedelta(days=30)
    availability = MagicMock()
    availability.has_data = True
    availability.is_complete = True  # Data covers full range
    availability.total_bars = 720
    availability.first_bar = start
    availability.last_bar = now
    availability.requested_start = start
    availability.requested_end = now
    availability.to_dict = MagicMock(
        return_value={
            "has_data": True,
            "is_complete": True,
            "total_bars": 720,
            "first_bar": start.isoformat(),
            "last_bar": now.isoformat(),
        }
    )
    return availability


@pytest.fixture
def mock_incomplete_data_availability():
    """Create a mock data availability object with incomplete data coverage."""
    now = datetime.now(UTC)
    requested_start = now - timedelta(days=30)
    requested_end = now
    # Data only covers 15 days instead of 30
    actual_start = now - timedelta(days=15)
    actual_end = now
    availability = MagicMock()
    availability.has_data = True
    availability.is_complete = False  # Data doesn't cover full range
    availability.total_bars = 360
    availability.first_bar = actual_start
    availability.last_bar = actual_end
    availability.requested_start = requested_start
    availability.requested_end = requested_end
    availability.to_dict = MagicMock(
        return_value={
            "has_data": True,
            "is_complete": False,
            "total_bars": 360,
            "first_bar": actual_start.isoformat(),
            "last_bar": actual_end.isoformat(),
        }
    )
    return availability


class TestStrategyRunRepository:
    """Tests for StrategyRunRepository."""

    @pytest.mark.asyncio
    async def test_list_by_strategy(self, mock_session, mock_run):
        """Test listing runs by strategy."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_run]
        mock_session.execute.return_value = mock_result

        repo = StrategyRunRepository(mock_session)
        runs = await repo.list_by_strategy(mock_run.strategy_id)

        assert len(runs) == 1
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_by_strategy_with_mode(self, mock_session, mock_run):
        """Test listing runs by strategy with mode filter."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_run]
        mock_session.execute.return_value = mock_result

        repo = StrategyRunRepository(mock_session)
        runs = await repo.list_by_strategy(mock_run.strategy_id, mode=RunMode.BACKTEST)

        assert len(runs) == 1
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_runs_with_filters(self, mock_session, mock_run):
        """Test listing runs with multiple filters."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_run]
        mock_session.execute.return_value = mock_result

        repo = StrategyRunRepository(mock_session)
        runs = await repo.list_runs(
            strategy_id=mock_run.strategy_id,
            mode=RunMode.BACKTEST,
            status=RunStatus.COMPLETED,
        )

        assert len(runs) == 1
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_count_runs(self, mock_session):
        """Test counting runs with filters."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 5
        mock_session.execute.return_value = mock_result

        repo = StrategyRunRepository(mock_session)
        count = await repo.count_runs(mode=RunMode.BACKTEST)

        assert count == 5
        mock_session.execute.assert_called_once()


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

    @pytest.mark.asyncio
    async def test_delete_by_run(self, mock_session):
        """Test deleting equity curve by run ID."""
        repo = EquityCurveRepository(mock_session)
        await repo.delete_by_run(str(uuid4()))

        mock_session.execute.assert_called_once()


class TestBacktestService:
    """Tests for BacktestService."""

    @pytest.mark.asyncio
    async def test_get_success(self, mock_session, mock_run):
        """Test getting a backtest run by ID."""
        with patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_run

            service = BacktestService(mock_session)
            result = await service.get(uuid4())

            assert result == mock_run
            mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_not_found(self, mock_session):
        """Test getting non-existent backtest raises error."""
        with patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            service = BacktestService(mock_session)

            with pytest.raises(BacktestNotFoundError):
                await service.get(uuid4())

    @pytest.mark.asyncio
    async def test_create_success(self, mock_session, mock_strategy, mock_run):
        """Test creating a backtest run record."""
        strategy_id = uuid4()

        with (
            patch("squant.services.strategy.StrategyRepository") as mock_strategy_repo_class,
            patch.object(StrategyRunRepository, "create", new_callable=AsyncMock) as mock_create,
        ):
            mock_strategy_repo = MagicMock()
            mock_strategy_repo.get = AsyncMock(return_value=mock_strategy)
            mock_strategy_repo_class.return_value = mock_strategy_repo
            mock_create.return_value = mock_run

            service = BacktestService(mock_session)
            result = await service.create(
                strategy_id=strategy_id,
                symbol="BTC/USDT",
                exchange="okx",
                timeframe="1h",
                start_date=datetime.now(UTC) - timedelta(days=30),
                end_date=datetime.now(UTC),
                initial_capital=Decimal("10000"),
            )

            assert result == mock_run
            mock_create.assert_called_once()
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_strategy_not_found(self, mock_session):
        """Test creating backtest with non-existent strategy."""
        with patch("squant.services.strategy.StrategyRepository") as mock_strategy_repo_class:
            from squant.services.strategy import StrategyNotFoundError

            mock_strategy_repo = MagicMock()
            mock_strategy_repo.get = AsyncMock(return_value=None)
            mock_strategy_repo_class.return_value = mock_strategy_repo

            service = BacktestService(mock_session)

            with pytest.raises(StrategyNotFoundError):
                await service.create(
                    strategy_id=uuid4(),
                    symbol="BTC/USDT",
                    exchange="okx",
                    timeframe="1h",
                    start_date=datetime.now(UTC) - timedelta(days=30),
                    end_date=datetime.now(UTC),
                    initial_capital=Decimal("10000"),
                )

    @pytest.mark.asyncio
    async def test_list_by_strategy(self, mock_session, mock_run):
        """Test listing backtest runs by strategy."""
        with (
            patch.object(
                StrategyRunRepository, "list_by_strategy", new_callable=AsyncMock
            ) as mock_list,
            patch.object(
                StrategyRunRepository, "count_by_strategy", new_callable=AsyncMock
            ) as mock_count,
        ):
            mock_list.return_value = [mock_run]
            mock_count.return_value = 1

            service = BacktestService(mock_session)
            runs, total = await service.list_by_strategy(uuid4())

            assert len(runs) == 1
            assert total == 1
            mock_list.assert_called_once()
            mock_count.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_runs(self, mock_session, mock_run):
        """Test listing backtest runs with filters."""
        with (
            patch.object(StrategyRunRepository, "list_runs", new_callable=AsyncMock) as mock_list,
            patch.object(StrategyRunRepository, "count_runs", new_callable=AsyncMock) as mock_count,
        ):
            mock_list.return_value = [mock_run]
            mock_count.return_value = 1

            service = BacktestService(mock_session)
            runs, total = await service.list_runs(status=RunStatus.COMPLETED)

            assert len(runs) == 1
            assert total == 1
            mock_list.assert_called_once()
            mock_count.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_equity_curve_success(self, mock_session, mock_run, mock_equity_curve):
        """Test getting equity curve for a backtest."""
        with (
            patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get,
            patch.object(
                EquityCurveRepository, "get_by_run", new_callable=AsyncMock
            ) as mock_get_curve,
        ):
            mock_get.return_value = mock_run
            mock_get_curve.return_value = [mock_equity_curve]

            service = BacktestService(mock_session)
            curves = await service.get_equity_curve(uuid4())

            assert len(curves) == 1
            mock_get.assert_called_once()
            mock_get_curve.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_equity_curve_not_found(self, mock_session):
        """Test getting equity curve for non-existent run."""
        with patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            service = BacktestService(mock_session)

            with pytest.raises(BacktestNotFoundError):
                await service.get_equity_curve(uuid4())

    @pytest.mark.asyncio
    async def test_delete_success(self, mock_session, mock_run):
        """Test deleting a backtest run."""
        with (
            patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get,
            patch.object(
                EquityCurveRepository, "delete_by_run", new_callable=AsyncMock
            ) as mock_delete_curve,
            patch.object(StrategyRunRepository, "delete", new_callable=AsyncMock) as mock_delete,
        ):
            mock_get.return_value = mock_run

            service = BacktestService(mock_session)
            await service.delete(uuid4())

            mock_delete_curve.assert_called_once()
            mock_delete.assert_called_once()
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_not_found(self, mock_session):
        """Test deleting non-existent backtest raises error."""
        with patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            service = BacktestService(mock_session)

            with pytest.raises(BacktestNotFoundError):
                await service.delete(uuid4())

    @pytest.mark.asyncio
    async def test_check_data_availability(self, mock_session, mock_data_availability):
        """Test checking data availability."""
        with patch.object(BacktestService, "__init__", lambda x, y: None):
            service = BacktestService.__new__(BacktestService)
            service.session = mock_session
            service.data_loader = MagicMock()
            service.data_loader.check_data_availability = AsyncMock(
                return_value=mock_data_availability
            )

            result = await service.check_data_availability(
                exchange="okx",
                symbol="BTC/USDT",
                timeframe="1h",
                start=datetime.now(UTC) - timedelta(days=30),
                end=datetime.now(UTC),
            )

            assert result["has_data"] is True
            assert result["total_bars"] == 720

    @pytest.mark.asyncio
    async def test_run_insufficient_data(self, mock_session, mock_run, mock_strategy):
        """Test running backtest with insufficient data."""
        run_id = uuid4()
        mock_run.id = str(run_id)

        with (
            patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get,
            patch("squant.services.strategy.StrategyRepository") as mock_strategy_repo_class,
            patch.object(BacktestService, "__init__", lambda x, y: None),
        ):
            mock_get.return_value = mock_run

            mock_strategy_repo = MagicMock()
            mock_strategy_repo.get = AsyncMock(return_value=mock_strategy)
            mock_strategy_repo_class.return_value = mock_strategy_repo

            service = BacktestService.__new__(BacktestService)
            service.session = mock_session
            service.run_repo = StrategyRunRepository(mock_session)
            service.run_repo.get = mock_get
            service.data_loader = MagicMock()

            # Mock no data available
            mock_availability = MagicMock()
            mock_availability.has_data = False
            service.data_loader.check_data_availability = AsyncMock(return_value=mock_availability)

            with pytest.raises(InsufficientDataError):
                await service.run(run_id)


class TestInitialCapitalValidation:
    """Tests for initial capital validation (TRD-003#4)."""

    @pytest.mark.asyncio
    async def test_tiny_capital_rejected(self, mock_session, mock_strategy):
        """Test very small capital below minimum is rejected."""
        strategy_id = uuid4()

        with patch("squant.services.strategy.StrategyRepository") as mock_strategy_repo_class:
            mock_strategy_repo = MagicMock()
            mock_strategy_repo.get = AsyncMock(return_value=mock_strategy)
            mock_strategy_repo_class.return_value = mock_strategy_repo

            service = BacktestService(mock_session)

            with pytest.raises(InvalidInitialCapitalError) as exc_info:
                await service.create(
                    strategy_id=strategy_id,
                    symbol="BTC/USDT",
                    exchange="okx",
                    timeframe="1h",
                    start_date=datetime.now(UTC) - timedelta(days=30),
                    end_date=datetime.now(UTC),
                    initial_capital=Decimal("0.01"),  # Tiny amount
                )

            error = exc_info.value
            assert error.capital == Decimal("0.01")
            assert error.min_capital == MIN_INITIAL_CAPITAL
            assert "below minimum" in str(error).lower()
            assert "unreliable" in str(error).lower()

    @pytest.mark.asyncio
    async def test_zero_capital_rejected(self, mock_session, mock_strategy):
        """Test zero capital is rejected."""
        strategy_id = uuid4()

        with patch("squant.services.strategy.StrategyRepository") as mock_strategy_repo_class:
            mock_strategy_repo = MagicMock()
            mock_strategy_repo.get = AsyncMock(return_value=mock_strategy)
            mock_strategy_repo_class.return_value = mock_strategy_repo

            service = BacktestService(mock_session)

            with pytest.raises(InvalidInitialCapitalError):
                await service.create(
                    strategy_id=strategy_id,
                    symbol="BTC/USDT",
                    exchange="okx",
                    timeframe="1h",
                    start_date=datetime.now(UTC) - timedelta(days=30),
                    end_date=datetime.now(UTC),
                    initial_capital=Decimal("0"),
                )

    @pytest.mark.asyncio
    async def test_negative_capital_rejected(self, mock_session, mock_strategy):
        """Test negative capital is rejected."""
        strategy_id = uuid4()

        with patch("squant.services.strategy.StrategyRepository") as mock_strategy_repo_class:
            mock_strategy_repo = MagicMock()
            mock_strategy_repo.get = AsyncMock(return_value=mock_strategy)
            mock_strategy_repo_class.return_value = mock_strategy_repo

            service = BacktestService(mock_session)

            with pytest.raises(InvalidInitialCapitalError):
                await service.create(
                    strategy_id=strategy_id,
                    symbol="BTC/USDT",
                    exchange="okx",
                    timeframe="1h",
                    start_date=datetime.now(UTC) - timedelta(days=30),
                    end_date=datetime.now(UTC),
                    initial_capital=Decimal("-100"),
                )

    @pytest.mark.asyncio
    async def test_minimum_capital_passes(self, mock_session, mock_strategy, mock_run):
        """Test minimum valid capital is accepted."""
        strategy_id = uuid4()

        with (
            patch("squant.services.strategy.StrategyRepository") as mock_strategy_repo_class,
            patch.object(StrategyRunRepository, "create", new_callable=AsyncMock) as mock_create,
        ):
            mock_strategy_repo = MagicMock()
            mock_strategy_repo.get = AsyncMock(return_value=mock_strategy)
            mock_strategy_repo_class.return_value = mock_strategy_repo
            mock_create.return_value = mock_run

            service = BacktestService(mock_session)

            # Should not raise - exactly at minimum
            result = await service.create(
                strategy_id=strategy_id,
                symbol="BTC/USDT",
                exchange="okx",
                timeframe="1h",
                start_date=datetime.now(UTC) - timedelta(days=30),
                end_date=datetime.now(UTC),
                initial_capital=MIN_INITIAL_CAPITAL,
            )

            assert result == mock_run

    @pytest.mark.asyncio
    async def test_normal_capital_passes(self, mock_session, mock_strategy, mock_run):
        """Test normal capital is accepted without issues."""
        strategy_id = uuid4()

        with (
            patch("squant.services.strategy.StrategyRepository") as mock_strategy_repo_class,
            patch.object(StrategyRunRepository, "create", new_callable=AsyncMock) as mock_create,
        ):
            mock_strategy_repo = MagicMock()
            mock_strategy_repo.get = AsyncMock(return_value=mock_strategy)
            mock_strategy_repo_class.return_value = mock_strategy_repo
            mock_create.return_value = mock_run

            service = BacktestService(mock_session)

            result = await service.create(
                strategy_id=strategy_id,
                symbol="BTC/USDT",
                exchange="okx",
                timeframe="1h",
                start_date=datetime.now(UTC) - timedelta(days=30),
                end_date=datetime.now(UTC),
                initial_capital=Decimal("10000"),
            )

            assert result == mock_run

    @pytest.mark.asyncio
    async def test_small_capital_logs_warning(self, mock_session, mock_strategy, mock_run):
        """Test that small capital (above minimum but below $100) logs a warning."""
        strategy_id = uuid4()

        with (
            patch("squant.services.strategy.StrategyRepository") as mock_strategy_repo_class,
            patch.object(StrategyRunRepository, "create", new_callable=AsyncMock) as mock_create,
            patch("squant.services.backtest.logger") as mock_logger,
        ):
            mock_strategy_repo = MagicMock()
            mock_strategy_repo.get = AsyncMock(return_value=mock_strategy)
            mock_strategy_repo_class.return_value = mock_strategy_repo
            mock_create.return_value = mock_run

            service = BacktestService(mock_session)

            # Small but valid capital
            await service.create(
                strategy_id=strategy_id,
                symbol="BTC/USDT",
                exchange="okx",
                timeframe="1h",
                start_date=datetime.now(UTC) - timedelta(days=30),
                end_date=datetime.now(UTC),
                initial_capital=Decimal("50"),  # Small but above minimum
            )

            # Should have logged a warning
            mock_logger.warning.assert_called_once()
            warning_msg = mock_logger.warning.call_args[0][0]
            assert "50" in warning_msg
            assert "unreliable" in warning_msg.lower()


class TestInvalidInitialCapitalError:
    """Tests for InvalidInitialCapitalError."""

    def test_error_message(self):
        """Test error message formatting."""
        error = InvalidInitialCapitalError(Decimal("0.5"), Decimal("1.0"))

        assert "0.5" in str(error)
        assert "1.0" in str(error)
        assert "below minimum" in str(error).lower()
        assert error.capital == Decimal("0.5")
        assert error.min_capital == Decimal("1.0")


class TestBacktestNotFoundError:
    """Tests for BacktestNotFoundError."""

    def test_error_message(self):
        """Test error message formatting."""
        run_id = uuid4()
        error = BacktestNotFoundError(run_id)

        assert str(run_id) in str(error)
        assert error.run_id == str(run_id)


class TestInsufficientDataError:
    """Tests for InsufficientDataError."""

    def test_error_message(self):
        """Test error message formatting."""
        message = "No data available for BTC/USDT"
        error = InsufficientDataError(message)

        assert message in str(error)
        assert error.message == message


class TestIncompleteDataError:
    """Tests for IncompleteDataError (Issue 029)."""

    def test_error_message(self):
        """Test error message formatting."""
        message = "Data doesn't cover the full range"
        error = IncompleteDataError(
            message,
            first_bar="2024-01-15T00:00:00+00:00",
            last_bar="2024-01-31T00:00:00+00:00",
            requested_start="2024-01-01T00:00:00+00:00",
            requested_end="2024-01-31T00:00:00+00:00",
        )

        assert message in str(error)
        assert error.message == message
        assert error.first_bar == "2024-01-15T00:00:00+00:00"
        assert error.last_bar == "2024-01-31T00:00:00+00:00"
        assert error.requested_start == "2024-01-01T00:00:00+00:00"
        assert error.requested_end == "2024-01-31T00:00:00+00:00"


class TestIncompleteDataValidation:
    """Tests for incomplete data validation in backtest run (Issue 029)."""

    @pytest.mark.asyncio
    async def test_run_incomplete_data_raises_error(
        self, mock_session, mock_run, mock_strategy, mock_incomplete_data_availability
    ):
        """Test running backtest with incomplete data raises IncompleteDataError."""
        run_id = uuid4()
        mock_run.id = str(run_id)

        with (
            patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get,
            patch("squant.services.strategy.StrategyRepository") as mock_strategy_repo_class,
            patch.object(BacktestService, "__init__", lambda x, y: None),
        ):
            mock_get.return_value = mock_run

            mock_strategy_repo = MagicMock()
            mock_strategy_repo.get = AsyncMock(return_value=mock_strategy)
            mock_strategy_repo_class.return_value = mock_strategy_repo

            service = BacktestService.__new__(BacktestService)
            service.session = mock_session
            service.run_repo = StrategyRunRepository(mock_session)
            service.run_repo.get = mock_get
            service.data_loader = MagicMock()
            service.data_loader.check_data_availability = AsyncMock(
                return_value=mock_incomplete_data_availability
            )

            with pytest.raises(IncompleteDataError) as exc_info:
                await service.run(run_id)

            # Verify error contains useful information
            error = exc_info.value
            assert "doesn't cover the full requested range" in str(error)
            assert error.first_bar is not None
            assert error.last_bar is not None

    @pytest.mark.asyncio
    async def test_run_incomplete_data_with_allow_partial_succeeds(
        self, mock_session, mock_run, mock_strategy, mock_incomplete_data_availability
    ):
        """Test running backtest with allow_partial_data=True logs warning but continues."""
        run_id = uuid4()
        mock_run.id = str(run_id)

        with (
            patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get,
            patch.object(StrategyRunRepository, "update", new_callable=AsyncMock) as mock_update,
            patch("squant.services.strategy.StrategyRepository") as mock_strategy_repo_class,
            # Patch at import location in the service module
            patch("squant.services.backtest.BacktestRunner") as mock_runner_class,
            patch.object(BacktestService, "__init__", lambda x, y: None),
            patch("squant.services.backtest.logger") as mock_logger,
        ):
            mock_get.return_value = mock_run
            mock_update.return_value = mock_run

            mock_strategy_repo = MagicMock()
            mock_strategy_repo.get = AsyncMock(return_value=mock_strategy)
            mock_strategy_repo_class.return_value = mock_strategy_repo

            # Mock backtest runner
            mock_runner = MagicMock()
            mock_result = MagicMock()
            mock_result.metrics = {"total_return": 0.1}
            mock_result.equity_curve = []
            mock_runner.run = AsyncMock(return_value=mock_result)
            mock_runner_class.return_value = mock_runner

            service = BacktestService.__new__(BacktestService)
            service.session = mock_session
            service.run_repo = StrategyRunRepository(mock_session)
            service.run_repo.get = mock_get
            service.run_repo.update = mock_update
            service.equity_repo = EquityCurveRepository(mock_session)
            service.data_loader = MagicMock()
            service.data_loader.check_data_availability = AsyncMock(
                return_value=mock_incomplete_data_availability
            )

            # Mock load_bars as an async generator
            async def mock_load_bars(*args, **kwargs):
                return
                yield  # Make it an async generator

            service.data_loader.load_bars = mock_load_bars

            # Should not raise with allow_partial_data=True
            await service.run(run_id, allow_partial_data=True)

            # Verify warning was logged
            mock_logger.warning.assert_called_once()
            warning_msg = mock_logger.warning.call_args[0][0]
            assert "Proceeding with partial data" in warning_msg
            assert "allow_partial_data=True" in warning_msg

    @pytest.mark.asyncio
    async def test_run_complete_data_succeeds(
        self, mock_session, mock_run, mock_strategy, mock_data_availability
    ):
        """Test running backtest with complete data coverage succeeds."""
        run_id = uuid4()
        mock_run.id = str(run_id)

        with (
            patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get,
            patch.object(StrategyRunRepository, "update", new_callable=AsyncMock) as mock_update,
            patch("squant.services.strategy.StrategyRepository") as mock_strategy_repo_class,
            # Patch at import location in the service module
            patch("squant.services.backtest.BacktestRunner") as mock_runner_class,
            patch.object(BacktestService, "__init__", lambda x, y: None),
        ):
            mock_get.return_value = mock_run
            mock_update.return_value = mock_run

            mock_strategy_repo = MagicMock()
            mock_strategy_repo.get = AsyncMock(return_value=mock_strategy)
            mock_strategy_repo_class.return_value = mock_strategy_repo

            # Mock backtest runner
            mock_runner = MagicMock()
            mock_result = MagicMock()
            mock_result.metrics = {"total_return": 0.1}
            mock_result.equity_curve = []
            mock_runner.run = AsyncMock(return_value=mock_result)
            mock_runner_class.return_value = mock_runner

            service = BacktestService.__new__(BacktestService)
            service.session = mock_session
            service.run_repo = StrategyRunRepository(mock_session)
            service.run_repo.get = mock_get
            service.run_repo.update = mock_update
            service.equity_repo = EquityCurveRepository(mock_session)
            service.data_loader = MagicMock()
            service.data_loader.check_data_availability = AsyncMock(
                return_value=mock_data_availability
            )

            # Mock load_bars as an async generator
            async def mock_load_bars(*args, **kwargs):
                return
                yield  # Make it an async generator

            service.data_loader.load_bars = mock_load_bars

            # Should succeed with complete data
            result = await service.run(run_id)

            assert result == mock_run


class TestBacktestCancellation:
    """Tests for backtest cancellation (TRD-008#3)."""

    @pytest.mark.asyncio
    async def test_cancel_running_backtest(self, mock_session, mock_run):
        """Test cancelling a running backtest."""
        from squant.engine.backtest.runner import BacktestRunner

        run_id = uuid4()
        mock_run.id = str(run_id)
        mock_run.status = RunStatus.RUNNING

        with patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_run

            service = BacktestService(mock_session)

            # Manually register a mock runner
            mock_runner = MagicMock(spec=BacktestRunner)
            BacktestService._running_backtests[str(run_id)] = mock_runner

            try:
                result = await service.cancel(run_id)

                assert result == mock_run
                mock_runner.cancel.assert_called_once()
            finally:
                # Clean up
                BacktestService._running_backtests.pop(str(run_id), None)

    @pytest.mark.asyncio
    async def test_cancel_pending_backtest_fails(self, mock_session, mock_run):
        """Test cancelling a pending backtest raises error."""
        from squant.engine.backtest.runner import BacktestError

        run_id = uuid4()
        mock_run.id = str(run_id)
        mock_run.status = RunStatus.PENDING

        with patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_run

            service = BacktestService(mock_session)

            with pytest.raises(BacktestError) as exc_info:
                await service.cancel(run_id)

            assert "pending" in str(exc_info.value).lower()
            assert "only running" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_cancel_completed_backtest_fails(self, mock_session, mock_run):
        """Test cancelling a completed backtest raises error."""
        from squant.engine.backtest.runner import BacktestError

        run_id = uuid4()
        mock_run.id = str(run_id)
        mock_run.status = RunStatus.COMPLETED

        with patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_run

            service = BacktestService(mock_session)

            with pytest.raises(BacktestError) as exc_info:
                await service.cancel(run_id)

            assert "completed" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_cancel_not_found(self, mock_session):
        """Test cancelling non-existent backtest raises error."""
        with patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            service = BacktestService(mock_session)

            with pytest.raises(BacktestNotFoundError):
                await service.cancel(uuid4())

    @pytest.mark.asyncio
    async def test_cancel_no_runner_found(self, mock_session, mock_run):
        """Test cancelling when runner already finished logs warning."""
        run_id = uuid4()
        mock_run.id = str(run_id)
        mock_run.status = RunStatus.RUNNING

        with (
            patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get,
            patch("squant.services.backtest.logger") as mock_logger,
        ):
            mock_get.return_value = mock_run

            service = BacktestService(mock_session)

            # No runner registered
            result = await service.cancel(run_id)

            assert result == mock_run
            mock_logger.warning.assert_called_once()
            assert "No active runner" in mock_logger.warning.call_args[0][0]

    def test_is_running(self, mock_run):
        """Test is_running class method."""
        from squant.engine.backtest.runner import BacktestRunner

        run_id = str(uuid4())

        # Not running initially
        assert BacktestService.is_running(run_id) is False

        # Register a runner
        mock_runner = MagicMock(spec=BacktestRunner)
        BacktestService._running_backtests[run_id] = mock_runner

        try:
            assert BacktestService.is_running(run_id) is True
        finally:
            BacktestService._running_backtests.pop(run_id, None)

        # No longer running after cleanup
        assert BacktestService.is_running(run_id) is False

    @pytest.mark.asyncio
    async def test_create_and_run_cancelled_preserves_status(self, mock_session, mock_run):
        """Test that create_and_run does not overwrite CANCELLED status with ERROR.

        When run() raises BacktestCancelledError, it already sets the status to
        CANCELLED. create_and_run() must not catch it in the generic Exception
        handler and overwrite with ERROR.
        """
        from squant.engine.backtest.runner import BacktestCancelledError

        strategy_id = uuid4()
        run_id = str(uuid4())
        mock_run.id = run_id

        with (
            patch.object(BacktestService, "create", new_callable=AsyncMock) as mock_create,
            patch.object(BacktestService, "run", new_callable=AsyncMock) as mock_run_method,
            patch.object(StrategyRunRepository, "update", new_callable=AsyncMock) as mock_update,
        ):
            mock_create.return_value = mock_run
            mock_run_method.side_effect = BacktestCancelledError(run_id)

            service = BacktestService(mock_session)

            with pytest.raises(BacktestCancelledError):
                await service.create_and_run(
                    strategy_id=strategy_id,
                    symbol="BTC/USDT",
                    exchange="okx",
                    timeframe="1h",
                    start_date=datetime.now(UTC) - timedelta(days=30),
                    end_date=datetime.now(UTC),
                    initial_capital=Decimal("10000"),
                )

            # The generic Exception handler should NOT have been called
            # (which would set status to ERROR)
            mock_update.assert_not_called()


class TestBacktestReportExport:
    """Tests for backtest report export (TRD-009#4)."""

    @pytest.fixture
    def completed_run(self, mock_run):
        """Create a completed run with results."""
        mock_run.status = RunStatus.COMPLETED
        mock_run.result = {
            "total_return": 0.15,
            "max_drawdown": 0.05,
            "sharpe_ratio": 1.5,
            "final_equity": "11500",
            "trades": [
                {
                    "symbol": "BTC/USDT",
                    "side": "buy",
                    "entry_time": "2024-01-01T00:00:00",
                    "entry_price": "50000",
                    "exit_time": "2024-01-02T00:00:00",
                    "exit_price": "51000",
                    "amount": "0.1",
                    "pnl": "100",
                    "pnl_pct": "0.02",
                    "fees": "1",
                }
            ],
        }
        return mock_run

    @pytest.mark.asyncio
    async def test_export_report_json(self, mock_session, completed_run, mock_strategy):
        """Test exporting report as JSON."""
        run_id = uuid4()
        completed_run.id = str(run_id)

        with (
            patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get,
            patch.object(
                EquityCurveRepository, "get_by_run", new_callable=AsyncMock
            ) as mock_get_curve,
            patch("squant.services.strategy.StrategyRepository") as mock_strategy_repo_class,
        ):
            mock_get.return_value = completed_run
            mock_get_curve.return_value = []

            mock_strategy_repo = MagicMock()
            mock_strategy_repo.get = AsyncMock(return_value=mock_strategy)
            mock_strategy_repo_class.return_value = mock_strategy_repo

            service = BacktestService(mock_session)
            report = await service.export_report(run_id, format="json")

            assert report["run_id"] == str(run_id)
            assert report["symbol"] == "BTC/USDT"
            assert report["export_format"] == "json"
            assert "metrics" in report
            assert "equity_curve" in report

    @pytest.mark.asyncio
    async def test_export_report_csv(self, mock_session, completed_run, mock_strategy):
        """Test exporting report and generating CSV."""
        run_id = uuid4()
        completed_run.id = str(run_id)

        with (
            patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get,
            patch.object(
                EquityCurveRepository, "get_by_run", new_callable=AsyncMock
            ) as mock_get_curve,
            patch("squant.services.strategy.StrategyRepository") as mock_strategy_repo_class,
        ):
            mock_get.return_value = completed_run
            mock_get_curve.return_value = []

            mock_strategy_repo = MagicMock()
            mock_strategy_repo.get = AsyncMock(return_value=mock_strategy)
            mock_strategy_repo_class.return_value = mock_strategy_repo

            service = BacktestService(mock_session)
            report = await service.export_report(run_id, format="csv")
            csv_content = service.generate_csv_report(report)

            assert "# Backtest Report Summary" in csv_content
            assert "# Performance Metrics" in csv_content
            assert str(run_id) in csv_content

    @pytest.mark.asyncio
    async def test_export_report_not_completed(self, mock_session, mock_run):
        """Test exporting report for non-completed run raises error."""
        run_id = uuid4()
        mock_run.id = str(run_id)
        mock_run.status = RunStatus.RUNNING

        with patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_run

            service = BacktestService(mock_session)

            with pytest.raises(ValueError) as exc_info:
                await service.export_report(run_id)

            assert "running" in str(exc_info.value).lower()
            assert "completed" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_export_report_not_found(self, mock_session):
        """Test exporting report for non-existent run raises error."""
        with patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            service = BacktestService(mock_session)

            with pytest.raises(BacktestNotFoundError):
                await service.export_report(uuid4())

    @pytest.mark.asyncio
    async def test_export_report_invalid_format(self, mock_session, completed_run):
        """Test exporting report with invalid format raises error."""
        run_id = uuid4()
        completed_run.id = str(run_id)

        with patch.object(StrategyRunRepository, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = completed_run

            service = BacktestService(mock_session)

            with pytest.raises(ValueError) as exc_info:
                await service.export_report(run_id, format="xml")

            assert "invalid" in str(exc_info.value).lower()
            assert "xml" in str(exc_info.value).lower()

    def test_generate_csv_report_with_trades(self, mock_session):
        """Test CSV generation includes trades section."""
        service = BacktestService(mock_session)

        report = {
            "run_id": "test-123",
            "strategy_id": "strategy-456",
            "strategy_name": "Test Strategy",
            "symbol": "BTC/USDT",
            "exchange": "okx",
            "timeframe": "1h",
            "start_date": "2024-01-01T00:00:00",
            "end_date": "2024-01-31T00:00:00",
            "initial_capital": "10000",
            "final_equity": "11500",
            "commission_rate": "0.001",
            "slippage": "0",
            "metrics": {"total_return": 0.15, "sharpe_ratio": 1.5},
            "equity_curve": [
                {
                    "time": "2024-01-01T00:00:00",
                    "equity": "10000",
                    "cash": "10000",
                    "position_value": "0",
                    "unrealized_pnl": "0",
                }
            ],
            "trades": [
                {
                    "symbol": "BTC/USDT",
                    "side": "buy",
                    "amount": "0.1",
                }
            ],
            "exported_at": "2024-02-01T00:00:00",
        }

        csv_content = service.generate_csv_report(report)

        assert "# Trades" in csv_content
        assert "BTC/USDT" in csv_content
        assert "# Equity Curve" in csv_content
