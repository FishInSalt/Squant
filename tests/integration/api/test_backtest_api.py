"""
Integration tests for Backtest API endpoints.

Tests validate acceptance criteria from dev-docs/requirements/acceptance-criteria/03-trading.md:
- TRD-001: Select strategy and trading pair
- TRD-002: Set backtest time range
- TRD-003: Set initial capital
- TRD-004: Set commission rate
- TRD-006: Configure strategy parameters
- TRD-007: Start backtest task
- TRD-009: Generate backtest report
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select

from squant.models.enums import RunStatus
from squant.models.strategy import Strategy, StrategyRun


@pytest.fixture
async def sample_strategy(db_session):
    """Create a sample strategy for testing."""
    strategy = Strategy(
        id=uuid4(),
        name="Test Backtest Strategy",
        code="class MyStrategy(Strategy):\n    def on_bar(self, bar):\n        pass",
        version="1.0.0",
        description="Strategy for backtest testing",
    )
    db_session.add(strategy)
    await db_session.commit()
    await db_session.refresh(strategy)
    return strategy


@pytest.fixture
def sample_backtest_config(sample_strategy):
    """Create sample backtest configuration."""
    return {
        "strategy_id": str(sample_strategy.id),
        "symbol": "BTC/USDT",
        "exchange": "okx",
        "timeframe": "1h",
        "start_date": (datetime.now(UTC) - timedelta(days=30)).isoformat(),
        "end_date": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        "initial_capital": "10000",
        "commission_rate": "0.001",
        "slippage": "0.0005",
    }


class TestSelectStrategyAndTradingPair:
    """
    Tests for TRD-001: Select strategy and trading pair

    Acceptance criteria:
    - Display available strategies from strategy library
    - Display supported trading pairs
    - Selected results shown on page
    """

    @pytest.mark.asyncio
    async def test_get_available_symbols(self, client):
        """Test TRD-001-2: Get supported trading pairs."""
        # Mock DataLoader to return available symbols
        mock_symbols = [
            {
                "exchange": "okx",
                "symbol": "BTC/USDT",
                "timeframe": "1h",
                "bar_count": 1000,
                "first_bar": datetime.now(UTC) - timedelta(days=30),
                "last_bar": datetime.now(UTC),
            },
            {
                "exchange": "okx",
                "symbol": "ETH/USDT",
                "timeframe": "1h",
                "bar_count": 1000,
                "first_bar": datetime.now(UTC) - timedelta(days=30),
                "last_bar": datetime.now(UTC),
            },
        ]

        with patch(
            "squant.services.data_loader.DataLoader.get_available_symbols",
            new_callable=AsyncMock,
            return_value=mock_symbols,
        ):
            response = await client.get("/api/v1/backtest/data/symbols")

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert isinstance(result, list)
        assert len(result) >= 2
        assert result[0]["symbol"] in ["BTC/USDT", "ETH/USDT"]

    @pytest.mark.asyncio
    async def test_filter_symbols_by_exchange(self, client):
        """Test filtering symbols by exchange."""
        mock_symbols = [
            {
                "exchange": "okx",
                "symbol": "BTC/USDT",
                "timeframe": "1h",
                "bar_count": 1000,
                "first_bar": datetime.now(UTC) - timedelta(days=30),
                "last_bar": datetime.now(UTC),
            }
        ]

        with patch(
            "squant.services.data_loader.DataLoader.get_available_symbols",
            new_callable=AsyncMock,
            return_value=mock_symbols,
        ):
            response = await client.get("/api/v1/backtest/data/symbols", params={"exchange": "okx"})

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert all(symbol["exchange"] == "okx" for symbol in result)


class TestSetBacktestTimeRange:
    """
    Tests for TRD-002: Set backtest time range

    Acceptance criteria:
    - Record start and end date selection
    - Error if start date is after end date
    - Error if date range has no historical data
    """

    @pytest.mark.asyncio
    async def test_validate_date_range_order(self, client, sample_backtest_config):
        """Test TRD-002-2: Error if start date is after end date."""
        # Swap dates to make start after end
        invalid_config = sample_backtest_config.copy()
        invalid_config["start_date"] = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        invalid_config["end_date"] = (datetime.now(UTC) - timedelta(days=30)).isoformat()

        response = await client.post("/api/v1/backtest", json=invalid_config)

        # Should return validation error (422 uses FastAPI's default format)
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_check_data_availability_no_data(self, client):
        """Test TRD-002-3: Error if date range has no historical data."""
        check_request = {
            "exchange": "okx",
            "symbol": "BTC/USDT",
            "timeframe": "1h",
            "start_date": (datetime.now(UTC) - timedelta(days=365)).isoformat(),
            "end_date": (datetime.now(UTC) - timedelta(days=360)).isoformat(),
        }

        # Mock service to return no data available
        mock_result = {
            "exchange": "okx",
            "symbol": "BTC/USDT",
            "timeframe": "1h",
            "first_bar": None,
            "last_bar": None,
            "total_bars": 0,
            "requested_start": datetime.now(UTC) - timedelta(days=365),
            "requested_end": datetime.now(UTC) - timedelta(days=360),
            "has_data": False,
            "is_complete": False,
        }

        with patch(
            "squant.services.backtest.BacktestService.check_data_availability",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            response = await client.post("/api/v1/backtest/data/check", json=check_request)

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["has_data"] is False
        assert result["total_bars"] == 0

    @pytest.mark.asyncio
    async def test_check_data_availability_with_data(self, client):
        """Test checking data availability with available data."""
        check_request = {
            "exchange": "okx",
            "symbol": "BTC/USDT",
            "timeframe": "1h",
            "start_date": (datetime.now(UTC) - timedelta(days=30)).isoformat(),
            "end_date": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        }

        # Mock service to return data available
        mock_result = {
            "exchange": "okx",
            "symbol": "BTC/USDT",
            "timeframe": "1h",
            "first_bar": datetime.now(UTC) - timedelta(days=30),
            "last_bar": datetime.now(UTC) - timedelta(days=1),
            "total_bars": 696,  # 29 days * 24 hours
            "requested_start": datetime.now(UTC) - timedelta(days=30),
            "requested_end": datetime.now(UTC) - timedelta(days=1),
            "has_data": True,
            "is_complete": True,
        }

        with patch(
            "squant.services.backtest.BacktestService.check_data_availability",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            response = await client.post("/api/v1/backtest/data/check", json=check_request)

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["has_data"] is True
        assert result["total_bars"] == 696
        assert result["is_complete"] is True


class TestSetInitialCapital:
    """
    Tests for TRD-003: Set initial capital

    Acceptance criteria:
    - Record initial capital value
    - Error if initial capital is negative or zero
    - Error if initial capital is too small
    """

    @pytest.mark.asyncio
    async def test_reject_zero_initial_capital(self, client, sample_backtest_config):
        """Test TRD-003-2: Error if initial capital is zero."""
        invalid_config = sample_backtest_config.copy()
        invalid_config["initial_capital"] = "0"

        response = await client.post("/api/v1/backtest", json=invalid_config)

        # Should return validation error (422)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_reject_negative_initial_capital(self, client, sample_backtest_config):
        """Test TRD-003-2: Error if initial capital is negative."""
        invalid_config = sample_backtest_config.copy()
        invalid_config["initial_capital"] = "-1000"

        response = await client.post("/api/v1/backtest", json=invalid_config)

        # Should return validation error (422)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_accept_valid_initial_capital(self, client, sample_backtest_config):
        """Test TRD-003-1: Record valid initial capital."""
        # Mock the service to avoid actual backtest execution
        mock_run = MagicMock()
        mock_run.id = uuid4()
        mock_run.strategy_id = uuid4()
        mock_run.mode = "backtest"
        mock_run.symbol = "BTC/USDT"
        mock_run.exchange = "okx"
        mock_run.timeframe = "1h"
        mock_run.status = RunStatus.COMPLETED
        mock_run.backtest_start = datetime.now(UTC) - timedelta(days=30)
        mock_run.backtest_end = datetime.now(UTC) - timedelta(days=1)
        mock_run.initial_capital = Decimal("10000")
        mock_run.commission_rate = Decimal("0.001")
        mock_run.slippage = Decimal("0.0005")
        mock_run.params = {}
        mock_run.result = {"total_return": 0.15}
        mock_run.error_message = None
        mock_run.started_at = datetime.now(UTC)
        mock_run.stopped_at = datetime.now(UTC)
        mock_run.created_at = datetime.now(UTC)
        mock_run.updated_at = datetime.now(UTC)
        mock_run.strategy_name = None
        mock_run.progress = 0.0

        with (
            patch(
                "squant.services.backtest.BacktestService.create",
                new_callable=AsyncMock,
                return_value=mock_run,
            ),
            patch("squant.services.backtest.BacktestService.run_in_background"),
        ):
            response = await client.post("/api/v1/backtest", json=sample_backtest_config)

        assert response.status_code == 201
        data = response.json()

        result = data["data"]
        assert float(result["initial_capital"]) == 10000


class TestSetCommissionRate:
    """
    Tests for TRD-004: Set commission rate

    Acceptance criteria:
    - Record commission rate value
    - Default commission rate exists
    - Error if commission rate exceeds 100%
    """

    @pytest.mark.asyncio
    async def test_default_commission_rate(self, client, sample_backtest_config):
        """Test TRD-004-2: Default commission rate exists."""
        # Remove commission_rate to test default
        config = sample_backtest_config.copy()
        del config["commission_rate"]

        mock_run = MagicMock()
        mock_run.id = uuid4()
        mock_run.strategy_id = uuid4()
        mock_run.mode = "backtest"
        mock_run.symbol = "BTC/USDT"
        mock_run.exchange = "okx"
        mock_run.timeframe = "1h"
        mock_run.status = RunStatus.COMPLETED
        mock_run.backtest_start = datetime.now(UTC) - timedelta(days=30)
        mock_run.backtest_end = datetime.now(UTC) - timedelta(days=1)
        mock_run.initial_capital = Decimal("10000")
        mock_run.commission_rate = Decimal("0.001")  # Default 0.1%
        mock_run.slippage = Decimal("0")
        mock_run.params = {}
        mock_run.result = None
        mock_run.error_message = None
        mock_run.started_at = None
        mock_run.stopped_at = None
        mock_run.created_at = datetime.now(UTC)
        mock_run.updated_at = datetime.now(UTC)
        mock_run.strategy_name = None
        mock_run.progress = 0.0

        with (
            patch(
                "squant.services.backtest.BacktestService.create",
                new_callable=AsyncMock,
                return_value=mock_run,
            ),
            patch("squant.services.backtest.BacktestService.run_in_background"),
        ):
            response = await client.post("/api/v1/backtest", json=config)

        assert response.status_code == 201
        data = response.json()

        result = data["data"]
        # Default should be 0.001 (0.1%)
        assert float(result["commission_rate"]) == 0.001

    @pytest.mark.asyncio
    async def test_reject_excessive_commission_rate(self, client, sample_backtest_config):
        """Test TRD-004-3: Error if commission rate exceeds 100%."""
        invalid_config = sample_backtest_config.copy()
        invalid_config["commission_rate"] = "1.5"  # 150%

        response = await client.post("/api/v1/backtest", json=invalid_config)

        # Should return validation error (422)
        assert response.status_code == 422


class TestConfigureStrategyParameters:
    """
    Tests for TRD-006: Configure strategy parameters

    Acceptance criteria:
    - Display all configurable parameters for selected strategy
    - New parameter values recorded for backtest
    - Parameters show default values
    """

    @pytest.mark.asyncio
    async def test_set_strategy_parameters(self, client, sample_backtest_config):
        """Test TRD-006-2: Parameter values recorded for backtest."""
        config = sample_backtest_config.copy()
        config["params"] = {
            "fast_period": 10,
            "slow_period": 20,
            "signal_threshold": 0.02,
        }

        mock_run = MagicMock()
        mock_run.id = uuid4()
        mock_run.strategy_id = uuid4()
        mock_run.mode = "backtest"
        mock_run.symbol = "BTC/USDT"
        mock_run.exchange = "okx"
        mock_run.timeframe = "1h"
        mock_run.status = RunStatus.COMPLETED
        mock_run.backtest_start = datetime.now(UTC) - timedelta(days=30)
        mock_run.backtest_end = datetime.now(UTC) - timedelta(days=1)
        mock_run.initial_capital = Decimal("10000")
        mock_run.commission_rate = Decimal("0.001")
        mock_run.slippage = Decimal("0.0005")
        mock_run.params = config["params"]
        mock_run.result = None
        mock_run.error_message = None
        mock_run.started_at = None
        mock_run.stopped_at = None
        mock_run.created_at = datetime.now(UTC)
        mock_run.updated_at = datetime.now(UTC)
        mock_run.strategy_name = None
        mock_run.progress = 0.0

        with (
            patch(
                "squant.services.backtest.BacktestService.create",
                new_callable=AsyncMock,
                return_value=mock_run,
            ),
            patch("squant.services.backtest.BacktestService.run_in_background"),
        ):
            response = await client.post("/api/v1/backtest", json=config)

        assert response.status_code == 201
        data = response.json()

        result = data["data"]
        assert result["params"]["fast_period"] == 10
        assert result["params"]["slow_period"] == 20
        assert result["params"]["signal_threshold"] == 0.02


class TestStartBacktestTask:
    """
    Tests for TRD-007: Start backtest task

    Acceptance criteria:
    - Backtest task starts when all required config complete
    - Error if required configuration missing
    - Page navigates to progress/results after start
    """

    @pytest.mark.asyncio
    async def test_start_backtest_with_complete_config(self, client, sample_backtest_config):
        """Test TRD-007-1: Start backtest with all required config."""
        mock_run = MagicMock()
        mock_run.id = uuid4()
        mock_run.strategy_id = uuid4()
        mock_run.mode = "backtest"
        mock_run.symbol = "BTC/USDT"
        mock_run.exchange = "okx"
        mock_run.timeframe = "1h"
        mock_run.status = RunStatus.PENDING
        mock_run.backtest_start = datetime.now(UTC) - timedelta(days=30)
        mock_run.backtest_end = datetime.now(UTC) - timedelta(days=1)
        mock_run.initial_capital = Decimal("10000")
        mock_run.commission_rate = Decimal("0.001")
        mock_run.slippage = Decimal("0.0005")
        mock_run.params = {}
        mock_run.result = None
        mock_run.error_message = None
        mock_run.started_at = None
        mock_run.stopped_at = None
        mock_run.created_at = datetime.now(UTC)
        mock_run.updated_at = datetime.now(UTC)
        mock_run.strategy_name = None
        mock_run.progress = 0.0

        with (
            patch(
                "squant.services.backtest.BacktestService.create",
                new_callable=AsyncMock,
                return_value=mock_run,
            ),
            patch("squant.services.backtest.BacktestService.run_in_background"),
        ):
            response = await client.post("/api/v1/backtest", json=sample_backtest_config)

        assert response.status_code == 201
        data = response.json()

        result = data["data"]
        assert "id" in result
        # Backtest is now async: returns pending, executes in background
        assert result["status"] == "pending"

    @pytest.mark.asyncio
    async def test_reject_missing_required_fields(self, client):
        """Test TRD-007-2: Error if required configuration missing."""
        incomplete_config = {
            "symbol": "BTC/USDT",
            # Missing strategy_id, exchange, timeframe, dates, initial_capital
        }

        response = await client.post("/api/v1/backtest", json=incomplete_config)

        # Should return validation error (422)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_strategy_not_found_error(self, client, sample_backtest_config):
        """Test error when strategy doesn't exist."""
        config = sample_backtest_config.copy()
        config["strategy_id"] = str(uuid4())  # Non-existent strategy

        from squant.services.strategy import StrategyNotFoundError

        with patch(
            "squant.services.backtest.BacktestService.create",
            new_callable=AsyncMock,
            side_effect=StrategyNotFoundError("Strategy not found"),
        ):
            response = await client.post("/api/v1/backtest", json=config)

        assert response.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.skip(
        reason="InsufficientDataError is now raised during async background execution, "
        "not at create time — cannot be tested via the synchronous POST endpoint"
    )
    async def test_insufficient_data_error(self, client, sample_backtest_config):
        """Test error when insufficient historical data."""
        pass


class TestGenerateBacktestReport:
    """
    Tests for TRD-009: Generate backtest report

    Acceptance criteria:
    - Display equity curve chart
    - Display all backtest metrics (return, sharpe, drawdown)
    - Display trade records list
    """

    @pytest.mark.asyncio
    async def test_get_backtest_results(self, client, db_session, sample_strategy):
        """Test TRD-009-2: Display all backtest metrics."""
        # Create a completed backtest run
        run_id = uuid4()
        run = StrategyRun(
            id=run_id,
            strategy_id=sample_strategy.id,
            mode="backtest",
            exchange="okx",
            symbol="BTC/USDT",
            timeframe="1h",
            status=RunStatus.COMPLETED,
            backtest_start=datetime.now(UTC) - timedelta(days=30),
            backtest_end=datetime.now(UTC) - timedelta(days=1),
            initial_capital=Decimal("10000"),
            commission_rate=Decimal("0.001"),
            slippage=Decimal("0.0005"),
            result={
                "total_return": 0.15,
                "annualized_return": 0.45,
                "sharpe_ratio": 1.5,
                "max_drawdown": -0.12,
                "win_rate": 0.65,
                "total_trades": 50,
            },
            started_at=datetime.now(UTC) - timedelta(hours=1),
            stopped_at=datetime.now(UTC),
        )
        db_session.add(run)
        await db_session.commit()

        response = await client.get(f"/api/v1/backtest/{run_id}")

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["id"] == str(run_id)
        assert result["status"] == "completed"
        assert result["result"]["total_return"] == 0.15
        assert result["result"]["sharpe_ratio"] == 1.5
        assert result["result"]["max_drawdown"] == -0.12

    @pytest.mark.asyncio
    async def test_get_equity_curve(self, client, db_session, sample_strategy):
        """Test TRD-009-1: Display equity curve chart."""
        # Create a completed backtest run
        run_id = uuid4()
        run = StrategyRun(
            id=run_id,
            strategy_id=sample_strategy.id,
            mode="backtest",
            exchange="okx",
            symbol="BTC/USDT",
            timeframe="1h",
            status=RunStatus.COMPLETED,
            backtest_start=datetime.now(UTC) - timedelta(days=30),
            backtest_end=datetime.now(UTC) - timedelta(days=1),
            initial_capital=Decimal("10000"),
            commission_rate=Decimal("0.001"),
        )
        db_session.add(run)
        await db_session.commit()

        # Mock equity curve data
        mock_equity_curve = [
            MagicMock(
                time=datetime.now(UTC) - timedelta(days=30 - i),
                equity=Decimal("10000") + Decimal(str(i * 50)),
                cash=Decimal("5000"),
                position_value=Decimal("5000") + Decimal(str(i * 50)),
                unrealized_pnl=Decimal(str(i * 10)),
                benchmark_equity=None,
            )
            for i in range(10)
        ]

        with patch(
            "squant.services.backtest.BacktestService.get_equity_curve",
            new_callable=AsyncMock,
            return_value=mock_equity_curve,
        ):
            response = await client.get(f"/api/v1/backtest/{run_id}/equity-curve")

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert isinstance(result, list)
        assert len(result) == 10
        assert "equity" in result[0]
        assert "time" in result[0]

    @pytest.mark.asyncio
    async def test_get_backtest_detail_with_equity_curve(self, client, db_session, sample_strategy):
        """Test getting detailed backtest including equity curve."""
        # Create a completed backtest run
        run_id = uuid4()
        run = StrategyRun(
            id=run_id,
            strategy_id=sample_strategy.id,
            mode="backtest",
            exchange="okx",
            symbol="BTC/USDT",
            timeframe="1h",
            status=RunStatus.COMPLETED,
            backtest_start=datetime.now(UTC) - timedelta(days=30),
            backtest_end=datetime.now(UTC) - timedelta(days=1),
            initial_capital=Decimal("10000"),
            commission_rate=Decimal("0.001"),
            result={"total_return": 0.15},
        )
        db_session.add(run)
        await db_session.commit()

        # Mock equity curve data
        mock_equity_curve = [
            MagicMock(
                time=datetime.now(UTC) - timedelta(days=30 - i),
                equity=Decimal("10000") + Decimal(str(i * 50)),
                cash=Decimal("5000"),
                position_value=Decimal("5000") + Decimal(str(i * 50)),
                unrealized_pnl=Decimal(str(i * 10)),
                benchmark_equity=None,
            )
            for i in range(10)
        ]

        with patch(
            "squant.services.backtest.BacktestService.get_equity_curve",
            new_callable=AsyncMock,
            return_value=mock_equity_curve,
        ):
            response = await client.get(f"/api/v1/backtest/{run_id}/detail")

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert "run" in result
        assert "equity_curve" in result
        assert "total_bars" in result
        assert len(result["equity_curve"]) == 10


class TestBacktestListAndManagement:
    """Tests for backtest list, filtering, and management operations."""

    @pytest.mark.asyncio
    async def test_list_backtests_with_pagination(self, client, db_session, sample_strategy):
        """Test listing backtests with pagination."""
        # Create multiple backtest runs
        for i in range(25):
            run = StrategyRun(
                id=uuid4(),
                strategy_id=sample_strategy.id,
                mode="backtest",
                exchange="okx",
                symbol="BTC/USDT" if i % 2 == 0 else "ETH/USDT",
                timeframe="1h",
                status=RunStatus.COMPLETED if i % 3 == 0 else RunStatus.PENDING,
                backtest_start=datetime.now(UTC) - timedelta(days=30),
                backtest_end=datetime.now(UTC) - timedelta(days=1),
                initial_capital=Decimal("10000"),
            )
            db_session.add(run)
        await db_session.commit()

        response = await client.get("/api/v1/backtest", params={"page": 1, "page_size": 10})

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert "items" in result
        assert "total" in result
        assert len(result["items"]) <= 10
        assert result["page"] == 1
        assert result["page_size"] == 10
        assert result["total"] >= 25

    @pytest.mark.asyncio
    async def test_filter_backtests_by_strategy(self, client, db_session, sample_strategy):
        """Test filtering backtests by strategy ID."""
        # Create backtest runs
        run = StrategyRun(
            id=uuid4(),
            strategy_id=sample_strategy.id,
            mode="backtest",
            exchange="okx",
            symbol="BTC/USDT",
            timeframe="1h",
            status=RunStatus.COMPLETED,
            backtest_start=datetime.now(UTC) - timedelta(days=30),
            backtest_end=datetime.now(UTC) - timedelta(days=1),
            initial_capital=Decimal("10000"),
        )
        db_session.add(run)
        await db_session.commit()

        response = await client.get(
            "/api/v1/backtest", params={"strategy_id": str(sample_strategy.id)}
        )

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert len(result["items"]) >= 1
        for item in result["items"]:
            assert item["strategy_id"] == str(sample_strategy.id)

    @pytest.mark.asyncio
    async def test_filter_backtests_by_status(self, client, db_session, sample_strategy):
        """Test filtering backtests by status."""
        # Create backtest runs with different statuses
        for status in [RunStatus.COMPLETED, RunStatus.PENDING, RunStatus.ERROR]:
            run = StrategyRun(
                id=uuid4(),
                strategy_id=sample_strategy.id,
                mode="backtest",
                exchange="okx",
                symbol="BTC/USDT",
                timeframe="1h",
                status=status,
                backtest_start=datetime.now(UTC) - timedelta(days=30),
                backtest_end=datetime.now(UTC) - timedelta(days=1),
                initial_capital=Decimal("10000"),
            )
            db_session.add(run)
        await db_session.commit()

        response = await client.get("/api/v1/backtest", params={"status": "completed"})

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        for item in result["items"]:
            assert item["status"] == "completed"

    @pytest.mark.asyncio
    async def test_filter_with_invalid_status(self, client):
        """Test filtering with invalid status returns error."""
        response = await client.get("/api/v1/backtest", params={"status": "invalid_status"})

        assert response.status_code == 400
        data = response.json()
        assert "invalid" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_delete_backtest(self, client, db_session, sample_strategy):
        """Test deleting a backtest run."""
        run_id = uuid4()
        run = StrategyRun(
            id=run_id,
            strategy_id=sample_strategy.id,
            mode="backtest",
            exchange="okx",
            symbol="BTC/USDT",
            timeframe="1h",
            status=RunStatus.COMPLETED,
            backtest_start=datetime.now(UTC) - timedelta(days=30),
            backtest_end=datetime.now(UTC) - timedelta(days=1),
            initial_capital=Decimal("10000"),
        )
        db_session.add(run)
        await db_session.commit()

        response = await client.delete(f"/api/v1/backtest/{run_id}")

        assert response.status_code == 200

        # Verify deleted
        db_result = await db_session.execute(select(StrategyRun).where(StrategyRun.id == run_id))
        deleted_run = db_result.scalar_one_or_none()
        assert deleted_run is None

    @pytest.mark.asyncio
    async def test_get_nonexistent_backtest(self, client):
        """Test getting non-existent backtest returns 404."""
        response = await client.get(f"/api/v1/backtest/{uuid4()}")

        assert response.status_code == 404


class TestAsyncBacktestCreation:
    """Tests for async backtest creation (create without immediate execution)."""

    @pytest.mark.asyncio
    async def test_create_backtest_without_execution(self, client, sample_backtest_config):
        """Test creating backtest without immediate execution."""
        mock_run = MagicMock()
        mock_run.id = uuid4()
        mock_run.strategy_id = uuid4()
        mock_run.mode = "backtest"
        mock_run.symbol = "BTC/USDT"
        mock_run.exchange = "okx"
        mock_run.timeframe = "1h"
        mock_run.status = RunStatus.PENDING
        mock_run.backtest_start = datetime.now(UTC) - timedelta(days=30)
        mock_run.backtest_end = datetime.now(UTC) - timedelta(days=1)
        mock_run.initial_capital = Decimal("10000")
        mock_run.commission_rate = Decimal("0.001")
        mock_run.slippage = Decimal("0.0005")
        mock_run.params = {}
        mock_run.result = None
        mock_run.error_message = None
        mock_run.started_at = None
        mock_run.stopped_at = None
        mock_run.created_at = datetime.now(UTC)
        mock_run.updated_at = datetime.now(UTC)
        mock_run.strategy_name = None
        mock_run.progress = 0.0

        with patch(
            "squant.services.backtest.BacktestService.create",
            new_callable=AsyncMock,
            return_value=mock_run,
        ):
            response = await client.post("/api/v1/backtest/async", json=sample_backtest_config)

        assert response.status_code == 201
        data = response.json()

        result = data["data"]
        assert result["status"] == "pending"
        assert result["result"] is None

    @pytest.mark.asyncio
    async def test_execute_pending_backtest(self, client, db_session, sample_strategy):
        """Test executing a previously created pending backtest."""
        # Create a pending backtest
        run_id = uuid4()
        run = StrategyRun(
            id=run_id,
            strategy_id=sample_strategy.id,
            mode="backtest",
            exchange="okx",
            symbol="BTC/USDT",
            timeframe="1h",
            status=RunStatus.PENDING,
            backtest_start=datetime.now(UTC) - timedelta(days=30),
            backtest_end=datetime.now(UTC) - timedelta(days=1),
            initial_capital=Decimal("10000"),
        )
        db_session.add(run)
        await db_session.commit()

        # Endpoint fires background execution and returns current (still pending) run
        with patch("squant.services.backtest.BacktestService.run_in_background"):
            response = await client.post(f"/api/v1/backtest/{run_id}/run")

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        # Run is still pending — execution happens asynchronously in background
        assert result["status"] == "pending"
