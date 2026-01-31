"""Backtest service for managing and executing backtests.

Provides high-level operations for:
- Creating and running backtests
- Managing backtest records
- Retrieving results and equity curves
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from squant.engine.backtest.runner import BacktestError, BacktestRunner
from squant.engine.backtest.types import BacktestResult
from squant.infra.repository import BaseRepository
from squant.models.enums import RunMode, RunStatus
from squant.models.metrics import EquityCurve
from squant.models.strategy import StrategyRun
from squant.services.data_loader import DataLoader


class BacktestNotFoundError(Exception):
    """Backtest run not found."""

    def __init__(self, run_id: str | UUID):
        self.run_id = str(run_id)
        super().__init__(f"Backtest run not found: {run_id}")


class InsufficientDataError(Exception):
    """Insufficient historical data for backtest."""

    def __init__(self, message: str):
        self.message = message
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

        Returns:
            StrategyRun with backtest results.

        Raises:
            StrategyNotFoundError: If strategy not found.
            InsufficientDataError: If not enough historical data.
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
        try:
            run = await self.run(UUID(run.id))
        except Exception as e:
            # Update run status to error
            await self.run_repo.update(
                run.id,
                status=RunStatus.ERROR,
                error_message=str(e),
                stopped_at=datetime.now(UTC),
            )
            await self.session.commit()
            raise

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
        """
        # Verify strategy exists
        from squant.services.strategy import StrategyNotFoundError, StrategyRepository

        strategy_repo = StrategyRepository(self.session)
        strategy = await strategy_repo.get(strategy_id)
        if not strategy:
            raise StrategyNotFoundError(strategy_id)

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

    async def run(self, run_id: UUID) -> StrategyRun:
        """Execute a pending backtest.

        Args:
            run_id: StrategyRun ID.

        Returns:
            Updated StrategyRun with results.

        Raises:
            BacktestNotFoundError: If run not found.
            InsufficientDataError: If not enough historical data.
            BacktestError: If backtest execution fails.
        """
        # Get run record
        run = await self.run_repo.get(run_id)
        if not run:
            raise BacktestNotFoundError(run_id)

        # Load strategy
        from squant.services.strategy import StrategyRepository

        strategy_repo = StrategyRepository(self.session)
        strategy = await strategy_repo.get(run.strategy_id)

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

        # Update status to running
        await self.run_repo.update(
            run.id,
            status=RunStatus.RUNNING,
            started_at=datetime.now(UTC),
        )
        await self.session.commit()

        try:
            # Create and run backtest
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

            bars = self.data_loader.load_bars(
                exchange=run.exchange,
                symbol=run.symbol,
                timeframe=run.timeframe,
                start=run.backtest_start,
                end=run.backtest_end,
            )

            result = await runner.run(bars, total_bars=availability.total_bars)

            # Save results
            await self._save_results(run.id, result)

            # Update run status
            run = await self.run_repo.update(
                run.id,
                status=RunStatus.COMPLETED,
                result=result.metrics,
                stopped_at=datetime.now(UTC),
            )
            await self.session.commit()

            return run

        except Exception as e:
            await self.run_repo.update(
                run.id,
                status=RunStatus.ERROR,
                error_message=str(e),
                stopped_at=datetime.now(UTC),
            )
            await self.session.commit()
            raise BacktestError(f"Backtest execution failed: {e}") from e

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
            }
            for snapshot in result.equity_curve
        ]
        await self.equity_repo.bulk_create(equity_records)

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
