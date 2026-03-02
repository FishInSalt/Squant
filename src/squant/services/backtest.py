"""Backtest service for managing and executing backtests.

Provides high-level operations for:
- Creating and running backtests
- Managing backtest records
- Retrieving results and equity curves
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from squant.engine.backtest.runner import (
    BacktestCancelledError,
    BacktestError,
    BacktestRunner,
)
from squant.engine.backtest.types import BacktestResult
from squant.infra.repository import BaseRepository
from squant.models.enums import RunMode, RunStatus
from squant.models.metrics import EquityCurve
from squant.models.strategy import StrategyRun
from squant.services.data_loader import DataLoader

logger = logging.getLogger(__name__)


# Minimum initial capital for backtest (TRD-003#4)
# Very small amounts may produce unreliable results due to commission and rounding
MIN_INITIAL_CAPITAL = Decimal("1.0")


class BacktestNotFoundError(Exception):
    """Backtest run not found."""

    def __init__(self, run_id: str | UUID):
        self.run_id = str(run_id)
        super().__init__(f"Backtest run not found: {run_id}")


class InvalidInitialCapitalError(Exception):
    """Initial capital is invalid for backtest (TRD-003#4)."""

    def __init__(self, capital: Decimal, min_capital: Decimal):
        self.capital = capital
        self.min_capital = min_capital
        super().__init__(
            f"Initial capital {capital} is below minimum required ({min_capital}). "
            f"Very small amounts may produce unreliable backtest results due to "
            f"commission and rounding effects."
        )


class InsufficientDataError(Exception):
    """Insufficient historical data for backtest."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class IncompleteDataError(Exception):
    """Historical data doesn't cover the full requested range.

    This is different from InsufficientDataError - we have some data,
    but it doesn't span the entire requested period.
    """

    def __init__(
        self,
        message: str,
        *,
        first_bar: str | None = None,
        last_bar: str | None = None,
        requested_start: str | None = None,
        requested_end: str | None = None,
    ):
        self.message = message
        self.first_bar = first_bar
        self.last_bar = last_bar
        self.requested_start = requested_start
        self.requested_end = requested_end
        super().__init__(message)


class StrategyRunRepository(BaseRepository[StrategyRun]):
    """Repository for StrategyRun model."""

    def __init__(self, session: AsyncSession):
        super().__init__(StrategyRun, session)

    async def list_by_strategy(
        self,
        strategy_id: str,
        *,
        mode: RunMode | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> list[StrategyRun]:
        """List runs for a strategy."""
        stmt = select(StrategyRun).where(StrategyRun.strategy_id == strategy_id)

        if mode:
            stmt = stmt.where(StrategyRun.mode == mode)

        stmt = stmt.order_by(StrategyRun.created_at.desc()).offset(offset).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_strategy(
        self,
        strategy_id: str,
        mode: RunMode | None = None,
    ) -> int:
        """Count runs for a strategy."""
        filters = {"strategy_id": strategy_id}
        if mode:
            filters["mode"] = mode
        return await self.count(**filters)

    async def list_runs(
        self,
        *,
        strategy_id: str | None = None,
        mode: RunMode | None = None,
        status: RunStatus | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> list[StrategyRun]:
        """List runs with optional filters."""
        stmt = select(StrategyRun)

        if strategy_id:
            stmt = stmt.where(StrategyRun.strategy_id == strategy_id)
        if mode:
            stmt = stmt.where(StrategyRun.mode == mode)
        if status:
            stmt = stmt.where(StrategyRun.status == status)

        stmt = stmt.order_by(StrategyRun.created_at.desc()).offset(offset).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_runs(
        self,
        *,
        strategy_id: str | None = None,
        mode: RunMode | None = None,
        status: RunStatus | None = None,
    ) -> int:
        """Count runs with optional filters."""
        stmt = select(func.count(StrategyRun.id))

        if strategy_id:
            stmt = stmt.where(StrategyRun.strategy_id == strategy_id)
        if mode:
            stmt = stmt.where(StrategyRun.mode == mode)
        if status:
            stmt = stmt.where(StrategyRun.status == status)

        result = await self.session.execute(stmt)
        return result.scalar() or 0


class EquityCurveRepository:
    """Repository for EquityCurve records."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def bulk_create(self, records: list[dict[str, Any]]) -> None:
        """Bulk insert equity curve records."""
        if not records:
            return

        instances = [EquityCurve(**record) for record in records]
        self.session.add_all(instances)
        await self.session.flush()

    async def get_by_run(self, run_id: str) -> list[EquityCurve]:
        """Get equity curve for a run."""
        stmt = (
            select(EquityCurve).where(EquityCurve.run_id == run_id).order_by(EquityCurve.time.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_by_run(self, run_id: str) -> None:
        """Delete equity curve records for a run."""
        await self.session.execute(delete(EquityCurve).where(EquityCurve.run_id == run_id))


class BacktestService:
    """Service for backtest operations."""

    # Class-level tracking of running backtests (TRD-008#3)
    _running_backtests: dict[str, BacktestRunner] = {}
    # Background task references for async execution
    _backtest_tasks: dict[str, asyncio.Task] = {}  # type: ignore[type-arg]
    # Real-time progress tracking (0.0 - 100.0)
    _backtest_progress: dict[str, float] = {}

    def __init__(self, session: AsyncSession):
        self.session = session
        self.run_repo = StrategyRunRepository(session)
        self.equity_repo = EquityCurveRepository(session)
        self.data_loader = DataLoader(session)

    async def create_and_run(
        self,
        strategy_id: UUID,
        symbol: str,
        exchange: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        initial_capital: Decimal,
        commission_rate: Decimal = Decimal("0.001"),
        slippage: Decimal = Decimal("0"),
        params: dict[str, Any] | None = None,
        *,
        allow_partial_data: bool = False,
    ) -> StrategyRun:
        """Create and execute a backtest.

        Args:
            strategy_id: Strategy ID.
            symbol: Trading symbol.
            exchange: Exchange name.
            timeframe: Candle timeframe.
            start_date: Backtest start date.
            end_date: Backtest end date.
            initial_capital: Starting capital.
            commission_rate: Commission rate.
            slippage: Slippage rate.
            params: Strategy parameters.
            allow_partial_data: If True, allow running backtest with incomplete
                data coverage. A warning will be logged but no error raised.
                Default is False (strict validation).

        Returns:
            StrategyRun with backtest results.

        Raises:
            StrategyNotFoundError: If strategy not found.
            InsufficientDataError: If no historical data available.
            IncompleteDataError: If data doesn't cover full range
                (unless allow_partial_data=True).
            BacktestError: If backtest execution fails.
        """
        # Create the run record
        run = await self.create(
            strategy_id=strategy_id,
            symbol=symbol,
            exchange=exchange,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            commission_rate=commission_rate,
            slippage=slippage,
            params=params,
        )

        # Execute the backtest
        # Note: run() handles status transitions (RUNNING→COMPLETED/CANCELLED/ERROR)
        # internally, so we don't set ERROR status here to avoid double-writes.
        run = await self.run(UUID(run.id), allow_partial_data=allow_partial_data)

        return run

    async def create(
        self,
        strategy_id: UUID,
        symbol: str,
        exchange: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        initial_capital: Decimal,
        commission_rate: Decimal = Decimal("0.001"),
        slippage: Decimal = Decimal("0"),
        params: dict[str, Any] | None = None,
    ) -> StrategyRun:
        """Create a backtest run record (without executing).

        Args:
            strategy_id: Strategy ID.
            symbol: Trading symbol.
            exchange: Exchange name.
            timeframe: Candle timeframe.
            start_date: Backtest start date.
            end_date: Backtest end date.
            initial_capital: Starting capital.
            commission_rate: Commission rate.
            slippage: Slippage rate.
            params: Strategy parameters.

        Returns:
            Created StrategyRun.

        Raises:
            StrategyNotFoundError: If strategy not found.
            InvalidInitialCapitalError: If initial capital is below minimum.
        """
        # Validate initial capital (TRD-003#4)
        if initial_capital < MIN_INITIAL_CAPITAL:
            raise InvalidInitialCapitalError(initial_capital, MIN_INITIAL_CAPITAL)

        # Log warning for very small capital (but above minimum)
        if initial_capital < Decimal("100"):
            logger.warning(
                f"Very small initial capital ({initial_capital}) may produce "
                f"unreliable backtest results due to commission and rounding effects."
            )

        # Verify strategy exists
        from squant.services.strategy import StrategyNotFoundError, StrategyRepository

        strategy_repo = StrategyRepository(self.session)
        strategy = await strategy_repo.get(strategy_id)
        if not strategy:
            raise StrategyNotFoundError(strategy_id)

        # Validate strategy code before creating DB record to avoid orphan PENDING records
        from squant.engine.sandbox import validate_strategy_code

        validation = validate_strategy_code(strategy.code)
        if not validation.valid:
            errors = "; ".join(validation.errors)
            raise ValueError(f"Invalid strategy code: {errors}")

        # Create run record
        run = await self.run_repo.create(
            strategy_id=str(strategy_id),
            mode=RunMode.BACKTEST,
            symbol=symbol,
            exchange=exchange,
            timeframe=timeframe,
            backtest_start=start_date,
            backtest_end=end_date,
            initial_capital=initial_capital,
            commission_rate=commission_rate,
            slippage=slippage,
            params=params or {},
            status=RunStatus.PENDING,
        )

        await self.session.commit()
        return run

    async def run(
        self,
        run_id: UUID,
        *,
        allow_partial_data: bool = False,
    ) -> StrategyRun:
        """Execute a pending backtest.

        Args:
            run_id: StrategyRun ID.
            allow_partial_data: If True, allow running backtest with incomplete
                data coverage. A warning will be logged but no error raised.
                Default is False (strict validation).

        Returns:
            Updated StrategyRun with results.

        Raises:
            BacktestNotFoundError: If run not found.
            StrategyNotFoundError: If strategy not found.
            InsufficientDataError: If no historical data available.
            IncompleteDataError: If data doesn't cover full range
                (unless allow_partial_data=True).
            BacktestError: If backtest execution fails.
        """
        # Get run record
        run = await self.run_repo.get(run_id)
        if not run:
            raise BacktestNotFoundError(run_id)

        # Load strategy
        from squant.services.strategy import StrategyNotFoundError, StrategyRepository

        strategy_repo = StrategyRepository(self.session)
        strategy = await strategy_repo.get(run.strategy_id)
        if not strategy:
            raise StrategyNotFoundError(run.strategy_id)

        # Check data availability
        availability = await self.data_loader.check_data_availability(
            exchange=run.exchange,
            symbol=run.symbol,
            timeframe=run.timeframe,
            start=run.backtest_start,
            end=run.backtest_end,
        )

        if not availability.has_data:
            raise InsufficientDataError(
                f"No data available for {run.exchange}:{run.symbol}:{run.timeframe} "
                f"between {run.backtest_start} and {run.backtest_end}"
            )

        # Check if data covers the full requested range (Issue 029)
        if not availability.is_complete:
            first_bar_str = availability.first_bar.isoformat() if availability.first_bar else "N/A"
            last_bar_str = availability.last_bar.isoformat() if availability.last_bar else "N/A"
            message = (
                f"Data doesn't cover the full requested range for "
                f"{run.exchange}:{run.symbol}:{run.timeframe}. "
                f"Requested: {run.backtest_start.isoformat()} to {run.backtest_end.isoformat()}, "
                f"Available: {first_bar_str} to {last_bar_str} "
                f"({availability.total_bars} bars). "
                f"Running backtest on partial data may produce misleading results."
            )
            if allow_partial_data:
                logger.warning(f"Proceeding with partial data (allow_partial_data=True): {message}")
            else:
                raise IncompleteDataError(
                    message,
                    first_bar=first_bar_str,
                    last_bar=last_bar_str,
                    requested_start=run.backtest_start.isoformat(),
                    requested_end=run.backtest_end.isoformat(),
                )

        # Update status to running
        await self.run_repo.update(
            run.id,
            status=RunStatus.RUNNING,
            started_at=datetime.now(UTC),
        )
        await self.session.commit()

        # Create runner
        runner = BacktestRunner(
            strategy_code=strategy.code,
            strategy_name=strategy.name,
            symbol=run.symbol,
            timeframe=run.timeframe,
            initial_capital=run.initial_capital,
            commission_rate=run.commission_rate,
            slippage=run.slippage or Decimal("0"),
            params=run.params,
        )
        runner.set_run_id(run.id)

        # Register runner for cancellation support (TRD-008#3)
        BacktestService._running_backtests[run.id] = runner

        try:
            bars = self.data_loader.load_bars(
                exchange=run.exchange,
                symbol=run.symbol,
                timeframe=run.timeframe,
                start=run.backtest_start,
                end=run.backtest_end,
            )

            # Progress callback updates class-level tracking
            def on_progress(current: int, total: int) -> None:
                if total > 0:
                    BacktestService._backtest_progress[run.id] = min(
                        99.0, (current / total) * 100
                    )

            result = await runner.run(
                bars,
                progress_callback=on_progress,
                total_bars=availability.total_bars,
            )

            # Save results
            await self._save_results(run.id, result)

            # Update run status with metrics + trades
            result_data = dict(result.metrics)
            result_data["trades"] = [
                {
                    "symbol": t.symbol,
                    "side": t.side.value,
                    "entry_time": t.entry_time.isoformat(),
                    "entry_price": str(t.entry_price),
                    "exit_time": t.exit_time.isoformat() if t.exit_time else None,
                    "exit_price": str(t.exit_price) if t.exit_price else None,
                    "amount": str(t.amount),
                    "pnl": str(t.pnl),
                    "pnl_pct": str(t.pnl_pct),
                    "fees": str(t.fees),
                }
                for t in result.trades
                if t.is_closed
            ]
            result_data["fills"] = [
                {
                    "order_id": f.order_id,
                    "symbol": f.symbol,
                    "side": f.side.value,
                    "price": str(f.price),
                    "amount": str(f.amount),
                    "fee": str(f.fee),
                    "timestamp": f.timestamp.isoformat(),
                }
                for f in result.fills
            ]
            run = await self.run_repo.update(
                run.id,
                status=RunStatus.COMPLETED,
                result=result_data,
                stopped_at=datetime.now(UTC),
            )
            await self.session.commit()

            return run

        except BacktestCancelledError:
            # Handle cancellation (TRD-008#3)
            run = await self.run_repo.update(
                run.id,
                status=RunStatus.CANCELLED,
                error_message="Backtest cancelled by user",
                stopped_at=datetime.now(UTC),
            )
            await self.session.commit()
            raise

        except Exception as e:
            await self.run_repo.update(
                run.id,
                status=RunStatus.ERROR,
                error_message=str(e),
                stopped_at=datetime.now(UTC),
            )
            await self.session.commit()
            raise BacktestError(f"Backtest execution failed: {e}") from e

        finally:
            # Always unregister runner (TRD-008#3)
            BacktestService._running_backtests.pop(run.id, None)

    async def _save_results(self, run_id: str, result: BacktestResult) -> None:
        """Save backtest results to database.

        Args:
            run_id: Run ID.
            result: Backtest result.
        """
        # Save equity curve
        equity_records = [
            {
                "time": snapshot.time,
                "run_id": run_id,
                "equity": snapshot.equity,
                "cash": snapshot.cash,
                "position_value": snapshot.position_value,
                "unrealized_pnl": snapshot.unrealized_pnl,
                "benchmark_equity": snapshot.benchmark_equity,
            }
            for snapshot in result.equity_curve
        ]
        await self.equity_repo.bulk_create(equity_records)

    async def cancel(self, run_id: UUID) -> StrategyRun:
        """Cancel a running backtest (TRD-008#3).

        Args:
            run_id: Backtest run ID.

        Returns:
            Updated StrategyRun with cancelled status.

        Raises:
            BacktestNotFoundError: If run not found.
            BacktestError: If run is not in a cancellable state.
        """
        # Verify run exists
        run = await self.run_repo.get(run_id)
        if not run:
            raise BacktestNotFoundError(run_id)

        # Check if run is in a cancellable state
        if run.status != RunStatus.RUNNING:
            status_val = run.status.value if hasattr(run.status, "value") else run.status
            raise BacktestError(
                f"Cannot cancel backtest with status '{status_val}'. "
                f"Only running backtests can be cancelled."
            )

        # Find and cancel the runner
        runner = BacktestService._running_backtests.get(str(run_id))
        if runner:
            runner.cancel()
            logger.info(f"Backtest {run_id} cancellation requested")
        else:
            # Runner not found - may have just finished
            logger.warning(f"No active runner found for backtest {run_id}")

        # Return current run state (actual cancellation happens asynchronously)
        return run

    @classmethod
    def is_running(cls, run_id: str) -> bool:
        """Check if a backtest is currently running.

        Args:
            run_id: Backtest run ID.

        Returns:
            True if backtest is running.
        """
        return run_id in cls._running_backtests

    @classmethod
    def run_in_background(cls, run_id: str) -> None:
        """Start a backtest execution as a background asyncio.Task.

        The task creates its own DB session via get_session_context()
        so it is independent of the HTTP request lifecycle.

        Args:
            run_id: StrategyRun ID to execute.
        """
        task = asyncio.create_task(cls._background_worker(run_id))
        cls._backtest_tasks[run_id] = task

    @classmethod
    async def _background_worker(cls, run_id: str) -> None:
        """Background worker that executes a backtest with an independent DB session."""
        from squant.infra.database import get_session_context

        try:
            async with get_session_context() as session:
                service = BacktestService(session)
                await service.run(UUID(run_id))
        except BacktestCancelledError:
            logger.info("Background backtest %s was cancelled", run_id)
        except Exception:
            logger.exception("Background backtest %s failed", run_id)
        finally:
            cls._backtest_tasks.pop(run_id, None)
            cls._backtest_progress.pop(run_id, None)

    @classmethod
    def get_progress(cls, run_id: str) -> float:
        """Get real-time progress for a running backtest.

        Args:
            run_id: StrategyRun ID.

        Returns:
            Progress percentage (0.0 - 100.0), 0.0 if not tracked.
        """
        return cls._backtest_progress.get(run_id, 0.0)

    async def get(self, run_id: UUID) -> StrategyRun:
        """Get a backtest run by ID.

        Args:
            run_id: Run ID.

        Returns:
            StrategyRun.

        Raises:
            BacktestNotFoundError: If not found.
        """
        run = await self.run_repo.get(run_id)
        if not run:
            raise BacktestNotFoundError(run_id)
        return run

    async def list_by_strategy(
        self,
        strategy_id: UUID,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[StrategyRun], int]:
        """List backtest runs for a strategy.

        Args:
            strategy_id: Strategy ID.
            page: Page number (1-indexed).
            page_size: Items per page.

        Returns:
            Tuple of (runs, total_count).
        """
        offset = (page - 1) * page_size
        runs = await self.run_repo.list_by_strategy(
            str(strategy_id),
            mode=RunMode.BACKTEST,
            offset=offset,
            limit=page_size,
        )
        total = await self.run_repo.count_by_strategy(str(strategy_id), RunMode.BACKTEST)
        return runs, total

    async def list_runs(
        self,
        *,
        strategy_id: UUID | None = None,
        status: RunStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[StrategyRun], int]:
        """List backtest runs with optional filters.

        Args:
            strategy_id: Optional strategy ID filter.
            status: Optional status filter.
            page: Page number (1-indexed).
            page_size: Items per page.

        Returns:
            Tuple of (runs, total_count).
        """
        offset = (page - 1) * page_size
        runs = await self.run_repo.list_runs(
            strategy_id=str(strategy_id) if strategy_id else None,
            mode=RunMode.BACKTEST,
            status=status,
            offset=offset,
            limit=page_size,
        )
        total = await self.run_repo.count_runs(
            strategy_id=str(strategy_id) if strategy_id else None,
            mode=RunMode.BACKTEST,
            status=status,
        )
        return runs, total

    async def get_equity_curve(self, run_id: UUID) -> list[EquityCurve]:
        """Get equity curve for a backtest.

        Args:
            run_id: Run ID.

        Returns:
            List of EquityCurve records.

        Raises:
            BacktestNotFoundError: If run not found.
        """
        # Verify run exists
        run = await self.run_repo.get(run_id)
        if not run:
            raise BacktestNotFoundError(run_id)

        return await self.equity_repo.get_by_run(str(run_id))

    async def delete(self, run_id: UUID) -> None:
        """Delete a backtest run and associated data.

        Args:
            run_id: Run ID.

        Raises:
            BacktestNotFoundError: If not found.
        """
        run = await self.run_repo.get(run_id)
        if not run:
            raise BacktestNotFoundError(run_id)

        # Delete equity curve records first (foreign key constraint)
        await self.equity_repo.delete_by_run(str(run_id))

        # Delete run record
        await self.run_repo.delete(run_id)

        await self.session.commit()

    async def check_data_availability(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> dict[str, Any]:
        """Check historical data availability.

        Args:
            exchange: Exchange name.
            symbol: Trading symbol.
            timeframe: Candle timeframe.
            start: Start datetime.
            end: End datetime.

        Returns:
            Data availability info as dict.
        """
        availability = await self.data_loader.check_data_availability(
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
        )
        return availability.to_dict()

    async def export_report(
        self,
        run_id: UUID,
        format: str = "json",
    ) -> dict[str, Any]:
        """Export backtest report (TRD-009#4).

        Args:
            run_id: Backtest run ID.
            format: Export format ('json' or 'csv').

        Returns:
            Report data as dictionary.

        Raises:
            BacktestNotFoundError: If run not found.
            ValueError: If run is not completed or format is invalid.
        """
        # Validate format
        if format not in ("json", "csv"):
            raise ValueError(f"Invalid export format: {format}. Supported: json, csv")

        # Get run data
        run = await self.run_repo.get(run_id)
        if not run:
            raise BacktestNotFoundError(run_id)

        # Check run status
        if run.status != RunStatus.COMPLETED:
            raise ValueError(
                f"Cannot export report for backtest with status '{run.status.value}'. "
                f"Only completed backtests can be exported."
            )

        # Get strategy name
        from squant.services.strategy import StrategyRepository

        strategy_repo = StrategyRepository(self.session)
        strategy = await strategy_repo.get(run.strategy_id)
        strategy_name = strategy.name if strategy else None

        # Get equity curve
        equity_curve = await self.equity_repo.get_by_run(str(run_id))

        # Build report data
        report = {
            "run_id": str(run.id),
            "strategy_id": str(run.strategy_id),
            "strategy_name": strategy_name,
            "symbol": run.symbol,
            "exchange": run.exchange,
            "timeframe": run.timeframe,
            "start_date": run.backtest_start.isoformat() if run.backtest_start else None,
            "end_date": run.backtest_end.isoformat() if run.backtest_end else None,
            "initial_capital": str(run.initial_capital),
            "final_equity": str(run.result.get("final_equity", run.initial_capital))
            if run.result
            else str(run.initial_capital),
            "commission_rate": str(run.commission_rate),
            "slippage": str(run.slippage or Decimal("0")),
            "metrics": run.result or {},
            "equity_curve": [
                {
                    "time": ec.time.isoformat(),
                    "equity": str(ec.equity),
                    "cash": str(ec.cash),
                    "position_value": str(ec.position_value),
                    "unrealized_pnl": str(ec.unrealized_pnl),
                }
                for ec in equity_curve
            ],
            "trades": run.result.get("trades", []) if run.result else [],
            "exported_at": datetime.now(UTC).isoformat(),
            "export_format": format,
        }

        return report

    def generate_csv_report(self, report: dict[str, Any]) -> str:
        """Generate CSV format report (TRD-009#4).

        Args:
            report: Report data from export_report().

        Returns:
            CSV formatted string.
        """
        import csv
        import io

        output = io.StringIO()

        # Section 1: Summary
        output.write("# Backtest Report Summary\n")
        output.write("Field,Value\n")
        writer = csv.writer(output)
        writer.writerow(["run_id", report["run_id"]])
        writer.writerow(["strategy_id", report["strategy_id"]])
        writer.writerow(["strategy_name", report["strategy_name"] or ""])
        writer.writerow(["symbol", report["symbol"]])
        writer.writerow(["exchange", report["exchange"]])
        writer.writerow(["timeframe", report["timeframe"]])
        writer.writerow(["start_date", report["start_date"] or ""])
        writer.writerow(["end_date", report["end_date"] or ""])
        writer.writerow(["initial_capital", report["initial_capital"]])
        writer.writerow(["final_equity", report["final_equity"]])
        writer.writerow(["commission_rate", report["commission_rate"]])
        writer.writerow(["slippage", report["slippage"]])
        writer.writerow(["exported_at", report["exported_at"]])

        # Section 2: Metrics
        output.write("\n# Performance Metrics\n")
        output.write("Metric,Value\n")
        for key, value in report["metrics"].items():
            if not isinstance(value, (list, dict)):
                writer.writerow([key, str(value)])

        # Section 3: Equity Curve
        output.write("\n# Equity Curve\n")
        if report["equity_curve"]:
            output.write("time,equity,cash,position_value,unrealized_pnl\n")
            for point in report["equity_curve"]:
                writer.writerow(
                    [
                        point["time"],
                        point["equity"],
                        point["cash"],
                        point["position_value"],
                        point["unrealized_pnl"],
                    ]
                )

        # Section 4: Trades
        output.write("\n# Trades\n")
        if report["trades"]:
            # Get trade fields from first trade
            if report["trades"]:
                first_trade = report["trades"][0]
                if isinstance(first_trade, dict):
                    headers = list(first_trade.keys())
                    output.write(",".join(headers) + "\n")
                    for trade in report["trades"]:
                        writer.writerow([str(trade.get(h, "")) for h in headers])

        return output.getvalue()
