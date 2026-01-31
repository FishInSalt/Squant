"""Paper trading service for managing real-time simulated trading sessions.

Provides high-level operations for:
- Starting and stopping paper trading sessions
- Managing session lifecycle
- Persisting equity curves
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from squant.engine.backtest.strategy_base import Strategy
from squant.engine.backtest.types import EquitySnapshot
from squant.engine.paper.engine import PaperTradingEngine
from squant.engine.paper.manager import get_session_manager
from squant.engine.sandbox import compile_strategy
from squant.infra.repository import BaseRepository
from squant.models.enums import RunMode, RunStatus
from squant.models.metrics import EquityCurve
from squant.models.strategy import StrategyRun
from squant.websocket.manager import get_stream_manager

logger = logging.getLogger(__name__)


class PaperTradingError(Exception):
    """Base error for paper trading operations."""

    pass


class SessionNotFoundError(PaperTradingError):
    """Paper trading session not found."""

    def __init__(self, run_id: str | UUID):
        self.run_id = str(run_id)
        super().__init__(f"Paper trading session not found: {run_id}")


class SessionAlreadyRunningError(PaperTradingError):
    """Paper trading session already running."""

    def __init__(self, run_id: str | UUID):
        self.run_id = str(run_id)
        super().__init__(f"Paper trading session already running: {run_id}")


class StrategyInstantiationError(PaperTradingError):
    """Error instantiating strategy from code."""

    pass


class StrategyRunRepository(BaseRepository[StrategyRun]):
    """Repository for StrategyRun model."""

    def __init__(self, session: AsyncSession):
        super().__init__(StrategyRun, session)

    async def list_by_mode(
        self,
        mode: RunMode,
        status: RunStatus | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> list[StrategyRun]:
        """List runs by mode."""
        stmt = select(StrategyRun).where(StrategyRun.mode == mode)

        if status:
            stmt = stmt.where(StrategyRun.status == status)

        stmt = stmt.order_by(StrategyRun.created_at.desc()).offset(offset).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_mode(
        self,
        mode: RunMode,
        status: RunStatus | None = None,
    ) -> int:
        """Count runs by mode."""
        filters: dict[str, Any] = {"mode": mode}
        if status:
            filters["status"] = status
        return await self.count(**filters)

    async def mark_orphaned_sessions(self) -> int:
        """Mark all RUNNING paper trading sessions as ERROR.

        Called on startup to recover from unexpected shutdowns.
        Sessions that were RUNNING when the application crashed are
        orphaned and need to be marked as ERROR.

        Returns:
            Number of sessions marked as ERROR.
        """
        stmt = (
            update(StrategyRun)
            .where(
                StrategyRun.mode == RunMode.PAPER,
                StrategyRun.status == RunStatus.RUNNING,
            )
            .values(
                status=RunStatus.ERROR,
                error_message="Session terminated due to application restart",
                stopped_at=datetime.now(UTC),
            )
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount


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


class PaperTradingService:
    """Service for paper trading operations."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.run_repo = StrategyRunRepository(session)
        self.equity_repo = EquityCurveRepository(session)

    async def start(
        self,
        strategy_id: UUID,
        symbol: str,
        exchange: str,
        timeframe: str,
        initial_capital: Decimal,
        commission_rate: Decimal = Decimal("0.001"),
        slippage: Decimal = Decimal("0"),
        params: dict[str, Any] | None = None,
    ) -> StrategyRun:
        """Start a paper trading session.

        Args:
            strategy_id: Strategy ID to run.
            symbol: Trading symbol.
            exchange: Exchange name.
            timeframe: Candle timeframe.
            initial_capital: Starting capital.
            commission_rate: Commission rate.
            slippage: Slippage rate.
            params: Strategy parameters.

        Returns:
            Created StrategyRun.

        Raises:
            StrategyNotFoundError: If strategy not found.
            StrategyInstantiationError: If strategy cannot be instantiated.
        """
        from squant.services.strategy import StrategyNotFoundError, StrategyRepository

        # Verify strategy exists
        strategy_repo = StrategyRepository(self.session)
        strategy = await strategy_repo.get(strategy_id)
        if not strategy:
            raise StrategyNotFoundError(strategy_id)

        # Create run record
        run = await self.run_repo.create(
            strategy_id=str(strategy_id),
            mode=RunMode.PAPER,
            symbol=symbol,
            exchange=exchange,
            timeframe=timeframe,
            initial_capital=initial_capital,
            commission_rate=commission_rate,
            slippage=slippage,
            params=params or {},
            status=RunStatus.RUNNING,
            started_at=datetime.now(UTC),
        )
        await self.session.commit()

        engine = None
        subscribed = False
        session_manager = get_session_manager()

        try:
            # Instantiate strategy
            strategy_instance = self._instantiate_strategy(strategy.code)

            # Create engine
            engine = PaperTradingEngine(
                run_id=UUID(run.id),
                strategy=strategy_instance,
                symbol=symbol,
                timeframe=timeframe,
                initial_capital=initial_capital,
                commission_rate=commission_rate,
                slippage=slippage,
                params=params,
            )

            # Register with session manager
            await session_manager.register(engine)

            # Subscribe to WebSocket candles
            stream_manager = get_stream_manager()
            await stream_manager.subscribe_candles(symbol, timeframe)
            subscribed = True

            # Start engine
            await engine.start()

            logger.info(f"Started paper trading session {run.id} for strategy {strategy_id}")

            return run

        except Exception as e:
            # Cleanup: unregister engine if it was registered
            if engine is not None:
                try:
                    await session_manager.unregister(engine.run_id)
                except Exception as cleanup_error:
                    logger.warning(
                        f"Failed to cleanup engine during error handling: {cleanup_error}"
                    )

            # Cleanup: unsubscribe from WebSocket if subscribed
            if subscribed:
                try:
                    await self._check_unsubscribe(symbol, timeframe)
                except Exception as cleanup_error:
                    logger.warning(
                        f"Failed to cleanup WebSocket subscription during error handling: {cleanup_error}"
                    )

            # Update run status to error
            await self.run_repo.update(
                run.id,
                status=RunStatus.ERROR,
                error_message=str(e),
                stopped_at=datetime.now(UTC),
            )
            await self.session.commit()
            raise

    def _instantiate_strategy(self, code: str) -> Strategy:
        """Compile strategy code and instantiate the strategy class.

        Args:
            code: Strategy source code.

        Returns:
            Strategy instance.

        Raises:
            StrategyInstantiationError: If strategy cannot be instantiated.
        """
        try:
            # Compile with RestrictedPython
            compiled = compile_strategy(code)

            # Inject Strategy base class into globals
            from squant.engine.backtest.strategy_base import Strategy as StrategyBase
            from squant.engine.backtest.types import Bar, OrderSide, OrderType, Position

            compiled.restricted_globals["Strategy"] = StrategyBase
            compiled.restricted_globals["Bar"] = Bar
            compiled.restricted_globals["Position"] = Position
            compiled.restricted_globals["OrderSide"] = OrderSide
            compiled.restricted_globals["OrderType"] = OrderType

            # Execute the code to define the class
            local_namespace: dict[str, Any] = {}
            exec(compiled.code_object, compiled.restricted_globals, local_namespace)

            # Find the strategy class (subclass of Strategy)
            strategy_class = None
            for _name, obj in local_namespace.items():
                if (
                    isinstance(obj, type)
                    and issubclass(obj, StrategyBase)
                    and obj is not StrategyBase
                ):
                    strategy_class = obj
                    break

            if strategy_class is None:
                raise StrategyInstantiationError("No Strategy subclass found in strategy code")

            # Instantiate
            return strategy_class()

        except ValueError as e:
            raise StrategyInstantiationError(f"Strategy compilation failed: {e}") from e
        except Exception as e:
            raise StrategyInstantiationError(f"Strategy instantiation failed: {e}") from e

    async def stop(self, run_id: UUID) -> StrategyRun:
        """Stop a paper trading session.

        Args:
            run_id: Run ID.

        Returns:
            Updated StrategyRun.

        Raises:
            SessionNotFoundError: If session not found.
        """
        # Get run record
        run = await self.run_repo.get(run_id)
        if not run:
            raise SessionNotFoundError(run_id)

        # Get engine from session manager
        session_manager = get_session_manager()
        engine = session_manager.get(run_id)

        if engine:
            # Persist any pending snapshots
            await self._persist_snapshots(str(run_id), engine.get_pending_snapshots())

            # Stop engine
            await engine.stop()

            # Unregister from session manager
            await session_manager.unregister(run_id)

            # Check if we should unsubscribe from candles
            await self._check_unsubscribe(engine.symbol, engine.timeframe)

        # Update run status
        run = await self.run_repo.update(
            run.id,
            status=RunStatus.STOPPED,
            stopped_at=datetime.now(UTC),
            error_message=engine.error_message if engine else None,
        )
        await self.session.commit()

        logger.info(f"Stopped paper trading session {run_id}")
        return run

    async def _check_unsubscribe(self, symbol: str, timeframe: str) -> None:
        """Check if we should unsubscribe from candles.

        Only unsubscribes if no other sessions need this symbol/timeframe.

        Args:
            symbol: Trading symbol.
            timeframe: Candle timeframe.
        """
        session_manager = get_session_manager()
        subscribed_symbols = session_manager.get_subscribed_symbols()

        if (symbol, timeframe) not in subscribed_symbols:
            stream_manager = get_stream_manager()
            await stream_manager.unsubscribe_candles(symbol, timeframe)
            logger.info(f"Unsubscribed from candles: {symbol}:{timeframe}")

    async def get_status(self, run_id: UUID) -> dict[str, Any]:
        """Get real-time status of a paper trading session.

        Args:
            run_id: Run ID.

        Returns:
            Status dictionary.

        Raises:
            SessionNotFoundError: If session not found.
        """
        # Get run record
        run = await self.run_repo.get(run_id)
        if not run:
            raise SessionNotFoundError(run_id)

        # Get engine from session manager
        session_manager = get_session_manager()
        engine = session_manager.get(run_id)

        if engine:
            # Return live status from engine
            status = engine.get_state_snapshot()
            status["strategy_id"] = run.strategy_id
            return status

        # Session not active, return from database
        return {
            "run_id": str(run_id),
            "strategy_id": run.strategy_id,
            "symbol": run.symbol,
            "timeframe": run.timeframe,
            "is_running": False,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "stopped_at": run.stopped_at.isoformat() if run.stopped_at else None,
            "error_message": run.error_message,
            "bar_count": 0,
            "cash": str(run.initial_capital) if run.initial_capital else "0",
            "equity": str(run.initial_capital) if run.initial_capital else "0",
            "initial_capital": str(run.initial_capital) if run.initial_capital else "0",
            "total_fees": "0",
            "positions": {},
            "pending_orders": [],
            "completed_orders_count": 0,
            "trades_count": 0,
        }

    def list_active(self) -> list[dict[str, Any]]:
        """List all active paper trading sessions.

        Returns:
            List of session state snapshots.
        """
        session_manager = get_session_manager()
        sessions = session_manager.list_sessions()

        # Enrich with strategy_id from sessions
        # Note: This is synchronous, so we can't query the database here
        # The strategy_id will need to be added by the API layer if needed
        return sessions

    async def list_runs(
        self,
        page: int = 1,
        page_size: int = 20,
        status: RunStatus | None = None,
    ) -> tuple[list[StrategyRun], int]:
        """List paper trading runs.

        Args:
            page: Page number (1-indexed).
            page_size: Items per page.
            status: Optional status filter.

        Returns:
            Tuple of (runs, total_count).
        """
        offset = (page - 1) * page_size
        runs = await self.run_repo.list_by_mode(
            RunMode.PAPER,
            status=status,
            offset=offset,
            limit=page_size,
        )
        total = await self.run_repo.count_by_mode(RunMode.PAPER, status)
        return runs, total

    async def get_run(self, run_id: UUID) -> StrategyRun:
        """Get a paper trading run by ID.

        Args:
            run_id: Run ID.

        Returns:
            StrategyRun.

        Raises:
            SessionNotFoundError: If not found.
        """
        run = await self.run_repo.get(run_id)
        if not run:
            raise SessionNotFoundError(run_id)
        return run

    async def get_equity_curve(self, run_id: UUID) -> list[EquityCurve]:
        """Get equity curve for a paper trading run.

        Args:
            run_id: Run ID.

        Returns:
            List of EquityCurve records.

        Raises:
            SessionNotFoundError: If run not found.
        """
        # Verify run exists
        run = await self.run_repo.get(run_id)
        if not run:
            raise SessionNotFoundError(run_id)

        return await self.equity_repo.get_by_run(str(run_id))

    async def persist_snapshots(self, run_id: UUID) -> int:
        """Persist pending equity snapshots for a session.

        Called periodically or on demand to save equity curve data.

        Args:
            run_id: Run ID.

        Returns:
            Number of snapshots persisted.
        """
        session_manager = get_session_manager()
        engine = session_manager.get(run_id)

        if not engine:
            return 0

        snapshots = engine.get_pending_snapshots()
        if not snapshots:
            return 0

        await self._persist_snapshots(str(run_id), snapshots)
        await self.session.commit()

        return len(snapshots)

    async def _persist_snapshots(self, run_id: str, snapshots: list[EquitySnapshot]) -> None:
        """Persist equity snapshots to database.

        Args:
            run_id: Run ID.
            snapshots: List of equity snapshots.
        """
        if not snapshots:
            return

        records = [
            {
                "time": snapshot.time,
                "run_id": run_id,
                "equity": snapshot.equity,
                "cash": snapshot.cash,
                "position_value": snapshot.position_value,
                "unrealized_pnl": snapshot.unrealized_pnl,
            }
            for snapshot in snapshots
        ]
        await self.equity_repo.bulk_create(records)
