"""Unit tests for backtest schemas."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from squant.schemas.backtest import (
    AvailableSymbolResponse,
    BacktestDetailResponse,
    BacktestListItem,
    BacktestMetrics,
    BacktestRunResponse,
    CheckDataRequest,
    CreateBacktestRequest,
    DataAvailabilityResponse,
    EquityCurvePoint,
    RunBacktestRequest,
    TradeRecordResponse,
)


class TestRunBacktestRequest:
    """Tests for RunBacktestRequest schema."""

    def test_valid_minimal_request(self):
        """Test creating request with required fields."""
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 6, 1, tzinfo=UTC)

        request = RunBacktestRequest(
            strategy_id=uuid4(),
            symbol="BTC/USDT",
            exchange="okx",
            timeframe="1h",
            start_date=start,
            end_date=end,
            initial_capital=Decimal("10000"),
        )

        assert request.symbol == "BTC/USDT"
        assert request.exchange == "okx"
        assert request.initial_capital == Decimal("10000")
        assert request.commission_rate == Decimal("0.001")
        assert request.slippage == Decimal("0")

    def test_full_request(self):
        """Test creating request with all fields."""
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 6, 1, tzinfo=UTC)

        request = RunBacktestRequest(
            strategy_id=uuid4(),
            symbol="ETH/USDT",
            exchange="binance",
            timeframe="4h",
            start_date=start,
            end_date=end,
            initial_capital=Decimal("50000"),
            commission_rate=Decimal("0.0005"),
            slippage=Decimal("0.001"),
            params={"fast_period": 10, "slow_period": 20},
        )

        assert request.commission_rate == Decimal("0.0005")
        assert request.slippage == Decimal("0.001")
        assert request.params == {"fast_period": 10, "slow_period": 20}

    def test_initial_capital_must_be_positive(self):
        """Test initial capital must be greater than 0."""
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 6, 1, tzinfo=UTC)

        with pytest.raises(ValidationError):
            RunBacktestRequest(
                strategy_id=uuid4(),
                symbol="BTC/USDT",
                exchange="okx",
                timeframe="1h",
                start_date=start,
                end_date=end,
                initial_capital=Decimal("0"),
            )

    def test_commission_rate_range(self):
        """Test commission rate must be between 0 and 1."""
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 6, 1, tzinfo=UTC)

        # Negative should fail
        with pytest.raises(ValidationError):
            RunBacktestRequest(
                strategy_id=uuid4(),
                symbol="BTC/USDT",
                exchange="okx",
                timeframe="1h",
                start_date=start,
                end_date=end,
                initial_capital=Decimal("10000"),
                commission_rate=Decimal("-0.001"),
            )

        # > 1 should fail
        with pytest.raises(ValidationError):
            RunBacktestRequest(
                strategy_id=uuid4(),
                symbol="BTC/USDT",
                exchange="okx",
                timeframe="1h",
                start_date=start,
                end_date=end,
                initial_capital=Decimal("10000"),
                commission_rate=Decimal("1.5"),
            )

    def test_symbol_validation(self):
        """Test symbol field validation."""
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 6, 1, tzinfo=UTC)

        with pytest.raises(ValidationError):
            RunBacktestRequest(
                strategy_id=uuid4(),
                symbol="",  # Empty string
                exchange="okx",
                timeframe="1h",
                start_date=start,
                end_date=end,
                initial_capital=Decimal("10000"),
            )

    def test_date_range_validation(self):
        """Test end_date must be after start_date."""
        start = datetime(2024, 6, 1, tzinfo=UTC)
        end = datetime(2024, 1, 1, tzinfo=UTC)  # Before start

        with pytest.raises(ValidationError, match="end_date must be after start_date"):
            RunBacktestRequest(
                strategy_id=uuid4(),
                symbol="BTC/USDT",
                exchange="okx",
                timeframe="1h",
                start_date=start,
                end_date=end,
                initial_capital=Decimal("10000"),
            )


class TestCreateBacktestRequest:
    """Tests for CreateBacktestRequest schema."""

    def test_valid_request(self):
        """Test creating valid request."""
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 6, 1, tzinfo=UTC)

        request = CreateBacktestRequest(
            strategy_id=uuid4(),
            symbol="BTC/USDT",
            exchange="okx",
            timeframe="1h",
            start_date=start,
            end_date=end,
            initial_capital=Decimal("10000"),
        )

        assert request.symbol == "BTC/USDT"
        assert request.commission_rate == Decimal("0.001")

    def test_same_validation_as_run_request(self):
        """Test has same validation as RunBacktestRequest."""
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 6, 1, tzinfo=UTC)

        with pytest.raises(ValidationError):
            CreateBacktestRequest(
                strategy_id=uuid4(),
                symbol="BTC/USDT",
                exchange="okx",
                timeframe="1h",
                start_date=start,
                end_date=end,
                initial_capital=Decimal("0"),  # Invalid
            )

    def test_date_range_validation(self):
        """Test end_date must be after start_date."""
        start = datetime(2024, 6, 1, tzinfo=UTC)
        end = datetime(2024, 1, 1, tzinfo=UTC)  # Before start

        with pytest.raises(ValidationError, match="end_date must be after start_date"):
            CreateBacktestRequest(
                strategy_id=uuid4(),
                symbol="BTC/USDT",
                exchange="okx",
                timeframe="1h",
                start_date=start,
                end_date=end,
                initial_capital=Decimal("10000"),
            )


class TestCheckDataRequest:
    """Tests for CheckDataRequest schema."""

    def test_valid_request(self):
        """Test creating valid request."""
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 6, 1, tzinfo=UTC)

        request = CheckDataRequest(
            exchange="okx",
            symbol="BTC/USDT",
            timeframe="1h",
            start_date=start,
            end_date=end,
        )

        assert request.exchange == "okx"
        assert request.symbol == "BTC/USDT"

    def test_required_fields(self):
        """Test all fields are required."""
        with pytest.raises(ValidationError):
            CheckDataRequest(exchange="okx", symbol="BTC/USDT")

    def test_date_range_validation(self):
        """Test end_date must be after start_date."""
        start = datetime(2024, 6, 1, tzinfo=UTC)
        end = datetime(2024, 1, 1, tzinfo=UTC)  # Before start

        with pytest.raises(ValidationError, match="end_date must be after start_date"):
            CheckDataRequest(
                exchange="okx",
                symbol="BTC/USDT",
                timeframe="1h",
                start_date=start,
                end_date=end,
            )


class TestBacktestRunResponse:
    """Tests for BacktestRunResponse schema."""

    def test_full_response(self):
        """Test creating full response."""
        now = datetime.now(UTC)
        response = BacktestRunResponse(
            id=uuid4(),
            strategy_id=uuid4(),
            mode="backtest",
            symbol="BTC/USDT",
            exchange="okx",
            timeframe="1h",
            status="completed",
            backtest_start=now,
            backtest_end=now,
            initial_capital=Decimal("10000"),
            commission_rate=Decimal("0.001"),
            slippage=Decimal("0"),
            params={},
            result={"total_return": 0.15, "sharpe_ratio": 1.5},
            error_message=None,
            started_at=now,
            stopped_at=now,
            created_at=now,
            updated_at=now,
        )

        assert response.status == "completed"
        assert response.result is not None

    def test_pending_response(self):
        """Test response for pending backtest."""
        now = datetime.now(UTC)
        response = BacktestRunResponse(
            id=uuid4(),
            strategy_id=uuid4(),
            mode="backtest",
            symbol="BTC/USDT",
            exchange="okx",
            timeframe="1h",
            status="pending",
            backtest_start=None,
            backtest_end=None,
            initial_capital=None,
            commission_rate=Decimal("0.001"),
            slippage=None,
            params={},
            result=None,
            error_message=None,
            started_at=None,
            stopped_at=None,
            created_at=now,
            updated_at=now,
        )

        assert response.status == "pending"
        assert response.result is None

    def test_from_attributes_config(self):
        """Test model has from_attributes config."""
        assert BacktestRunResponse.model_config.get("from_attributes") is True


class TestBacktestListItem:
    """Tests for BacktestListItem schema."""

    def test_list_item(self):
        """Test creating list item."""
        now = datetime.now(UTC)
        item = BacktestListItem(
            id=uuid4(),
            strategy_id=uuid4(),
            symbol="BTC/USDT",
            exchange="okx",
            timeframe="1h",
            status="completed",
            backtest_start=now,
            backtest_end=now,
            initial_capital=Decimal("10000"),
            result={"total_return": 0.15},
            created_at=now,
        )

        assert item.symbol == "BTC/USDT"
        assert item.status == "completed"


class TestEquityCurvePoint:
    """Tests for EquityCurvePoint schema."""

    def test_equity_point(self):
        """Test creating equity curve point."""
        now = datetime.now(UTC)
        point = EquityCurvePoint(
            time=now,
            equity=Decimal("10500"),
            cash=Decimal("5000"),
            position_value=Decimal("5500"),
            unrealized_pnl=Decimal("500"),
        )

        assert point.equity == Decimal("10500")
        assert point.cash == Decimal("5000")
        assert point.position_value == Decimal("5500")

    def test_from_attributes_config(self):
        """Test model has from_attributes config."""
        assert EquityCurvePoint.model_config.get("from_attributes") is True


class TestTradeRecordResponse:
    """Tests for TradeRecordResponse schema."""

    def test_closed_trade(self):
        """Test creating closed trade record."""
        entry_time = datetime(2024, 1, 1, 10, 0, tzinfo=UTC)
        exit_time = datetime(2024, 1, 1, 14, 0, tzinfo=UTC)

        trade = TradeRecordResponse(
            symbol="BTC/USDT",
            side="buy",
            entry_time=entry_time,
            entry_price=Decimal("40000"),
            exit_time=exit_time,
            exit_price=Decimal("41000"),
            amount=Decimal("0.1"),
            pnl=Decimal("100"),
            pnl_pct=Decimal("2.5"),
            fees=Decimal("2"),
        )

        assert trade.pnl == Decimal("100")
        assert trade.exit_time is not None

    def test_open_trade(self):
        """Test creating open trade record (no exit)."""
        entry_time = datetime(2024, 1, 1, 10, 0, tzinfo=UTC)

        trade = TradeRecordResponse(
            symbol="BTC/USDT",
            side="buy",
            entry_time=entry_time,
            entry_price=Decimal("40000"),
            exit_time=None,
            exit_price=None,
            amount=Decimal("0.1"),
            pnl=Decimal("50"),  # Unrealized
            pnl_pct=Decimal("1.25"),
            fees=Decimal("1"),
        )

        assert trade.exit_time is None
        assert trade.exit_price is None


class TestBacktestDetailResponse:
    """Tests for BacktestDetailResponse schema."""

    def test_detail_response(self):
        """Test creating detail response."""
        now = datetime.now(UTC)
        run = BacktestRunResponse(
            id=uuid4(),
            strategy_id=uuid4(),
            mode="backtest",
            symbol="BTC/USDT",
            exchange="okx",
            timeframe="1h",
            status="completed",
            backtest_start=now,
            backtest_end=now,
            initial_capital=Decimal("10000"),
            commission_rate=Decimal("0.001"),
            slippage=Decimal("0"),
            params={},
            result={"total_return": 0.15},
            error_message=None,
            started_at=now,
            stopped_at=now,
            created_at=now,
            updated_at=now,
        )

        equity_curve = [
            EquityCurvePoint(
                time=now,
                equity=Decimal("10500"),
                cash=Decimal("5000"),
                position_value=Decimal("5500"),
                unrealized_pnl=Decimal("500"),
            )
        ]

        response = BacktestDetailResponse(
            run=run,
            equity_curve=equity_curve,
            total_bars=1000,
        )

        assert response.run.status == "completed"
        assert len(response.equity_curve) == 1
        assert response.total_bars == 1000

    def test_total_bars_optional(self):
        """Test total_bars is optional."""
        now = datetime.now(UTC)
        run = BacktestRunResponse(
            id=uuid4(),
            strategy_id=uuid4(),
            mode="backtest",
            symbol="BTC/USDT",
            exchange="okx",
            timeframe="1h",
            status="completed",
            backtest_start=now,
            backtest_end=now,
            initial_capital=Decimal("10000"),
            commission_rate=Decimal("0.001"),
            slippage=Decimal("0"),
            params={},
            result=None,
            error_message=None,
            started_at=now,
            stopped_at=now,
            created_at=now,
            updated_at=now,
        )

        response = BacktestDetailResponse(run=run, equity_curve=[])

        assert response.total_bars is None


class TestBacktestMetrics:
    """Tests for BacktestMetrics schema (BT-004)."""

    def test_all_defaults_are_zero(self):
        """Test all fields default to zero values."""
        metrics = BacktestMetrics()
        assert metrics.total_return == 0.0
        assert metrics.sharpe_ratio == 0.0
        assert metrics.total_trades == 0
        assert metrics.win_rate == 0.0
        assert metrics.max_drawdown_duration_hours == 0
        assert metrics.total_fees == 0.0

    def test_from_complete_dict(self):
        """Test parsing from a complete PerformanceMetrics.to_dict() output."""
        raw = {
            "total_return": "1500.50",
            "total_return_pct": "15.005",
            "annualized_return": "30.01",
            "max_drawdown": "500.25",
            "max_drawdown_pct": "5.0025",
            "max_drawdown_duration_hours": 72,
            "sharpe_ratio": "1.85",
            "sortino_ratio": "2.10",
            "calmar_ratio": "3.0",
            "volatility": "0.15",
            "total_trades": 42,
            "winning_trades": 28,
            "losing_trades": 14,
            "win_rate": "0.6667",
            "profit_factor": "2.5",
            "avg_trade_return": "35.73",
            "avg_win": "80.0",
            "avg_loss": "-32.0",
            "largest_win": "500.0",
            "largest_loss": "-200.0",
            "max_consecutive_losses": 3,
            "avg_trade_duration_hours": "4.5",
            "total_duration_days": 180,
            "total_fees": "42.0",
        }
        metrics = BacktestMetrics(**raw)
        assert metrics.total_return == 1500.50
        assert metrics.total_trades == 42
        assert metrics.win_rate == pytest.approx(0.6667)
        assert metrics.max_consecutive_losses == 3

    def test_string_to_float_coercion(self):
        """Test string values from to_dict() are coerced to float."""
        metrics = BacktestMetrics(total_return="1000", sharpe_ratio="1.5")
        assert isinstance(metrics.total_return, float)
        assert isinstance(metrics.sharpe_ratio, float)
        assert metrics.total_return == 1000.0
        assert metrics.sharpe_ratio == 1.5

    def test_string_to_int_coercion(self):
        """Test string int values are coerced properly."""
        metrics = BacktestMetrics(total_trades="10", winning_trades="7")
        assert isinstance(metrics.total_trades, int)
        assert metrics.total_trades == 10
        assert metrics.winning_trades == 7

    def test_ignores_unknown_fields(self):
        """Test extra fields from result dict are silently ignored."""
        raw = {"total_return": 100.0, "trades": [], "unknown_field": "value"}
        # Filter to known fields (as done in the API route)
        filtered = {k: v for k, v in raw.items() if k in BacktestMetrics.model_fields}
        metrics = BacktestMetrics(**filtered)
        assert metrics.total_return == 100.0

    def test_partial_dict(self):
        """Test parsing from dict with only some fields — rest use defaults."""
        metrics = BacktestMetrics(total_return=500.0, total_trades=10)
        assert metrics.total_return == 500.0
        assert metrics.total_trades == 10
        assert metrics.sharpe_ratio == 0.0
        assert metrics.volatility == 0.0


class TestDataAvailabilityResponse:
    """Tests for DataAvailabilityResponse schema."""

    def test_data_available(self):
        """Test response when data is available."""
        now = datetime.now(UTC)
        response = DataAvailabilityResponse(
            exchange="okx",
            symbol="BTC/USDT",
            timeframe="1h",
            first_bar=now,
            last_bar=now,
            total_bars=10000,
            requested_start=now,
            requested_end=now,
            has_data=True,
            is_complete=True,
        )

        assert response.has_data is True
        assert response.is_complete is True
        assert response.total_bars == 10000

    def test_no_data(self):
        """Test response when no data available."""
        now = datetime.now(UTC)
        response = DataAvailabilityResponse(
            exchange="okx",
            symbol="NEW/USDT",
            timeframe="1h",
            first_bar=None,
            last_bar=None,
            total_bars=0,
            requested_start=now,
            requested_end=now,
            has_data=False,
            is_complete=False,
        )

        assert response.has_data is False
        assert response.total_bars == 0


class TestAvailableSymbolResponse:
    """Tests for AvailableSymbolResponse schema."""

    def test_available_symbol(self):
        """Test available symbol response."""
        now = datetime.now(UTC)
        response = AvailableSymbolResponse(
            exchange="okx",
            symbol="BTC/USDT",
            timeframe="1h",
            bar_count=50000,
            first_bar=now,
            last_bar=now,
        )

        assert response.symbol == "BTC/USDT"
        assert response.bar_count == 50000

    def test_optional_bar_times(self):
        """Test bar times are optional."""
        response = AvailableSymbolResponse(
            exchange="okx",
            symbol="BTC/USDT",
            timeframe="1h",
            bar_count=0,
            first_bar=None,
            last_bar=None,
        )

        assert response.first_bar is None
        assert response.last_bar is None
