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
from squant.engine.resource_limits import resource_limiter
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

    def __init__(self, run_id: str | UUID | None = None, *, message: str | None = None):
        self.run_id = str(run_id) if run_id else None
        if message:
            super().__init__(message)
        else:
            super().__init__(f"Paper trading session already running: {run_id}")


class MaxSessionsReachedError(PaperTradingError):
    """Maximum number of concurrent paper trading sessions reached."""

    def __init__(self, max_sessions: int):
        super().__init__(f"Maximum concurrent paper trading sessions reached: {max_sessions}")


class StrategyInstantiationError(PaperTradingError):
    """Error instantiating strategy from code."""

    pass


class SessionNotResumableError(PaperTradingError):
    """Session cannot be resumed (wrong status or no saved state)."""

    def __init__(self, run_id: str | UUID, reason: str):
        self.run_id = str(run_id)
        super().__init__(f"Cannot resume session {run_id}: {reason}")


class CircuitBreakerActiveError(PaperTradingError):
    """Cannot start trading when circuit breaker is active."""

    def __init__(self, reason: str | None = None):
        message = "Cannot start trading: circuit breaker is active"
        if reason:
            message += f" (reason: {reason})"
        super().__init__(message)


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

    async def has_running_session(
        self,
        strategy_id: str,
        symbol: str,
        mode: RunMode,
    ) -> bool:
        """Check if a running session exists for the given strategy/symbol/mode.

        Args:
            strategy_id: Strategy ID.
            symbol: Trading symbol.
            mode: Run mode (PAPER, LIVE).

        Returns:
            True if a running session exists.
        """
        stmt = (
            select(StrategyRun)
            .where(
                StrategyRun.strategy_id == strategy_id,
                StrategyRun.symbol == symbol,
                StrategyRun.mode == mode,
                StrategyRun.status == RunStatus.RUNNING,
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def get_orphaned_sessions(self) -> list[StrategyRun]:
        """Get recoverable paper trading sessions after restart.

        Finds sessions that were either:
        - RUNNING (force-killed, no graceful shutdown)
        - INTERRUPTED (gracefully stopped during application shutdown)

        Returns:
            List of recoverable StrategyRun records.
        """
        stmt = select(StrategyRun).where(
            StrategyRun.mode == RunMode.PAPER,
            StrategyRun.status.in_([RunStatus.RUNNING, RunStatus.INTERRUPTED]),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def mark_orphaned_sessions(self) -> int:
        """Mark all RUNNING paper trading sessions as INTERRUPTED.

        Called on startup to recover from unexpected shutdowns.
        Sessions that were RUNNING when the application crashed are
        orphaned and need to be marked as INTERRUPTED.

        Returns:
            Number of sessions marked as INTERRUPTED.
        """
        stmt = (
            update(StrategyRun)
            .where(
                StrategyRun.mode == RunMode.PAPER,
                StrategyRun.status == RunStatus.RUNNING,
            )
            .values(
                status=RunStatus.INTERRUPTED,
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

    async def get_by_run(self, run_id: str, since: datetime | None = None) -> list[EquityCurve]:
        """Get equity curve for a run.

        Args:
            run_id: Run ID.
            since: If provided, only return records with time > since.
        """
        stmt = select(EquityCurve).where(EquityCurve.run_id == run_id)
        if since is not None:
            stmt = stmt.where(EquityCurve.time > since)
        stmt = stmt.order_by(EquityCurve.time.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_last_by_run(self, run_id: str) -> EquityCurve | None:
        """Get the last equity curve record for a run.

        Args:
            run_id: Run ID.

        Returns:
            Last EquityCurve record or None if no records exist.
        """
        stmt = (
            select(EquityCurve)
            .where(EquityCurve.run_id == run_id)
            .order_by(EquityCurve.time.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


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
        slippage: Decimal = Decimal("0.0005"),
        params: dict[str, Any] | None = None,
        redis: Any | None = None,
        risk_config: Any | None = None,
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
            redis: Redis client for circuit breaker check (optional).
            risk_config: Optional RiskConfigRequest for risk management.

        Returns:
            Created StrategyRun.

        Raises:
            StrategyNotFoundError: If strategy not found.
            StrategyInstantiationError: If strategy cannot be instantiated.
            CircuitBreakerActiveError: If circuit breaker is active.
        """
        from squant.config import get_settings
        from squant.services.strategy import StrategyNotFoundError, StrategyRepository

        # Check circuit breaker state before starting
        if redis is not None:
            await self._check_circuit_breaker(redis)

        # Check for duplicate running session (PP-C03)
        has_running = await self.run_repo.has_running_session(
            strategy_id=str(strategy_id),
            symbol=symbol,
            mode=RunMode.PAPER,
        )
        if has_running:
            raise SessionAlreadyRunningError(
                message=f"A paper trading session for strategy {strategy_id} "
                f"on {symbol} is already running"
            )

        # Check max concurrent sessions limit (PP-H01)
        settings = get_settings()
        session_manager = get_session_manager()
        if session_manager.session_count >= settings.paper.max_sessions:
            raise MaxSessionsReachedError(settings.paper.max_sessions)

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

            # Convert risk config request to RiskConfig model (if provided)
            engine_risk_config = None
            if risk_config:
                from squant.engine.risk.models import RiskConfig

                engine_risk_config = RiskConfig(
                    max_position_size=risk_config.max_position_size,
                    max_order_size=risk_config.max_order_size,
                    daily_trade_limit=risk_config.daily_trade_limit,
                    daily_loss_limit=risk_config.daily_loss_limit,
                    max_price_deviation=risk_config.price_deviation_limit,
                    circuit_breaker_loss_count=risk_config.circuit_breaker_threshold,
                )

            # Create engine with synchronous persistence callbacks
            engine = PaperTradingEngine(
                run_id=UUID(run.id),
                strategy=strategy_instance,
                symbol=symbol,
                timeframe=timeframe,
                initial_capital=initial_capital,
                commission_rate=commission_rate,
                slippage=slippage,
                params=params,
                on_snapshot=self._create_snapshot_callback(),
                on_result=self._create_result_callback(),
                risk_config=engine_risk_config,
            )

            # Register with session manager
            await session_manager.register(engine)

            # Subscribe to WebSocket candles and tickers (for spread simulation)
            stream_manager = get_stream_manager()
            await stream_manager.subscribe_candles(symbol, timeframe)
            subscribed = True
            await stream_manager.subscribe_ticker(symbol)

            # Start engine
            await engine.start()

            logger.info(f"Started paper trading session {run.id} for strategy {strategy_id}")

            return run

        except Exception as e:
            # Cleanup: stop engine if it was started (Issue 020 fix)
            if engine is not None and engine.is_running:
                try:
                    await engine.stop(error=f"Startup failed: {e}")
                except Exception as cleanup_error:
                    logger.warning(f"Failed to stop engine during error handling: {cleanup_error}")

            # Cleanup: unregister engine and check unsubscribe atomically (Issue 019 fix)
            if engine is not None:
                try:
                    key_to_unsubscribe = await session_manager.unregister_and_check_subscription(
                        engine.run_id
                    )
                    if subscribed:
                        stream_manager = get_stream_manager()
                        await stream_manager.unsubscribe_ticker(symbol)
                        if key_to_unsubscribe:
                            await stream_manager.unsubscribe_candles(*key_to_unsubscribe)
                        logger.info(f"Unsubscribed from ticker+candles: {symbol}")
                except Exception as cleanup_error:
                    logger.warning(
                        f"Failed to cleanup engine during error handling: {cleanup_error}"
                    )
            elif subscribed:
                # Engine was not created but we subscribed - unsubscribe directly
                try:
                    stream_manager = get_stream_manager()
                    await stream_manager.unsubscribe_candles(symbol, timeframe)
                    await stream_manager.unsubscribe_ticker(symbol)
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

    async def _check_circuit_breaker(self, redis: Any) -> None:
        """Check if circuit breaker is active and raise error if so.

        Args:
            redis: Redis client.

        Raises:
            CircuitBreakerActiveError: If circuit breaker is active.
        """
        import json

        try:
            state_data = await redis.get("squant:circuit_breaker:state")
            if state_data:
                state = json.loads(state_data)
                if state.get("is_active", False):
                    raise CircuitBreakerActiveError(state.get("trigger_reason"))
        except json.JSONDecodeError:
            pass  # Invalid state, allow trading

    @staticmethod
    def _create_snapshot_callback() -> Any:
        """Create a callback for synchronous snapshot persistence.

        Returns a closure that opens its own DB session to persist a single
        equity snapshot. This keeps the engine DB-agnostic.
        """

        async def _persist_single(run_id: str, snapshot: EquitySnapshot) -> None:
            from squant.infra.database import get_session_context

            async with get_session_context() as db_session:
                repo = EquityCurveRepository(db_session)
                await repo.bulk_create(
                    [
                        {
                            "time": snapshot.time,
                            "run_id": run_id,
                            "equity": snapshot.equity,
                            "cash": snapshot.cash,
                            "position_value": snapshot.position_value,
                            "unrealized_pnl": snapshot.unrealized_pnl,
                            "benchmark_equity": snapshot.benchmark_equity,
                        }
                    ]
                )

        return _persist_single

    @staticmethod
    def _create_result_callback() -> Any:
        """Create a callback for synchronous result state persistence.

        Returns a closure that opens its own DB session to update the
        StrategyRun.result JSONB with the latest trading state.
        This ensures crash recovery always has recent state.
        """

        async def _persist_result(run_id: str, result: dict[str, Any]) -> None:
            from squant.infra.database import get_session_context

            async with get_session_context() as db_session:
                repo = StrategyRunRepository(db_session)
                await repo.update(run_id, result=result)

        return _persist_result

    async def stop(self, run_id: UUID, *, for_shutdown: bool = False) -> StrategyRun:
        """Stop a paper trading session.

        Args:
            run_id: Run ID.
            for_shutdown: If True, marks session as INTERRUPTED (application
                shutdown) instead of STOPPED, and skips candle unsubscription.

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

        key_to_unsubscribe = None
        symbol = None
        error_message = None
        result_data = None

        if engine:
            symbol = engine.symbol

            # Stop engine FIRST — acquires _processing_lock, waits for any
            # in-progress candle to finish.  This prevents a race where an
            # awaited persist_snapshots yields the event loop and a new candle
            # is processed between result capture and engine stop.
            await engine.stop()
            error_message = engine.error_message

            # NOW capture result and snapshots (engine state is stable)
            result_data = engine.build_result_for_persistence()
            await self._persist_snapshots(str(run_id), engine.get_pending_snapshots())

            # Unregister and atomically check subscription (Issue 019 fix)
            key_to_unsubscribe = await session_manager.unregister_and_check_subscription(run_id)

        # Determine status based on stop reason
        if for_shutdown:
            status = RunStatus.INTERRUPTED
            # Preserve engine's original error message (e.g. risk limit triggered)
            error_message = error_message or "Session interrupted by application shutdown"
        else:
            status = RunStatus.STOPPED

        # Update run status and commit BEFORE unsubscribing (Issue 021 fix)
        # This ensures database state is consistent even if unsubscribe fails
        run = await self.run_repo.update(
            run.id,
            status=status,
            result=result_data,
            stopped_at=datetime.now(UTC),
            error_message=error_message,
        )
        await self.session.commit()

        # Skip unsubscription during shutdown (stream manager is about to close)
        if not for_shutdown:
            try:
                stream_manager = get_stream_manager()
                # Always unsubscribe ticker (ref-counted independently from candles)
                if symbol:
                    await stream_manager.unsubscribe_ticker(symbol)
                if key_to_unsubscribe:
                    await stream_manager.unsubscribe_candles(*key_to_unsubscribe)
                    logger.info(f"Unsubscribed from candles+ticker: {key_to_unsubscribe}")
            except Exception as e:
                # Log but don't fail - database is already updated
                logger.warning(f"Failed to unsubscribe from candles/ticker: {e}")

        logger.info(f"{'Shutdown' if for_shutdown else 'Stopped'} paper trading session {run_id}")
        return run

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
        base_status = {
            "run_id": str(run_id),
            "strategy_id": run.strategy_id,
            "symbol": run.symbol,
            "timeframe": run.timeframe,
            "is_running": False,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "stopped_at": run.stopped_at.isoformat() if run.stopped_at else None,
            "error_message": run.error_message,
            "initial_capital": str(run.initial_capital) if run.initial_capital else "0",
        }

        if run.result:
            # Restore from saved result snapshot
            initial_capital = str(run.initial_capital) if run.initial_capital else "0"
            base_status.update(
                {
                    "bar_count": run.result.get("bar_count", 0),
                    "cash": run.result.get("cash", initial_capital),
                    "equity": run.result.get("equity", initial_capital),
                    "total_fees": run.result.get("total_fees", "0"),
                    "unrealized_pnl": run.result.get("unrealized_pnl", "0"),
                    "realized_pnl": run.result.get("realized_pnl", "0"),
                    "positions": run.result.get("positions", {}),
                    "pending_orders": [],
                    "completed_orders_count": run.result.get("completed_orders_count", 0),
                    "trades_count": run.result.get("trades_count", 0),
                    "trades": run.result.get("trades", []),
                    "open_trade": run.result.get("open_trade"),
                    "logs": run.result.get("logs", []),
                }
            )
        else:
            # No result saved — fallback to zero values
            base_status.update(
                {
                    "bar_count": 0,
                    "cash": str(run.initial_capital) if run.initial_capital else "0",
                    "equity": str(run.initial_capital) if run.initial_capital else "0",
                    "total_fees": "0",
                    "unrealized_pnl": "0",
                    "realized_pnl": "0",
                    "positions": {},
                    "pending_orders": [],
                    "completed_orders_count": 0,
                    "trades_count": 0,
                    "trades": [],
                    "logs": [],
                }
            )

        return base_status

    async def mark_session_interrupted(
        self,
        run_id: UUID,
        error_message: str,
        result: dict[str, Any] | None = None,
    ) -> None:
        """Mark a session as interrupted in the database.

        Used by background health checks when a session is cleaned up
        due to timeout or stale state (infrastructure interruption,
        not a strategy error).

        Args:
            run_id: Run ID of the session to mark.
            error_message: Interruption description.
            result: Optional engine state snapshot to save as final result.
        """
        run = await self.run_repo.get(run_id)
        if run and run.status in (RunStatus.RUNNING, RunStatus.INTERRUPTED):
            await self.run_repo.update(
                run.id,
                status=RunStatus.INTERRUPTED,
                error_message=error_message,
                result=result,
                stopped_at=datetime.now(UTC),
            )
            await self.session.commit()
            logger.info(f"Marked session {run_id} as interrupted: {error_message}")

    async def mark_session_error(
        self,
        run_id: UUID,
        error_message: str,
        result: dict[str, Any] | None = None,
    ) -> None:
        """Mark a session as errored in the database.

        Used when auto-stop triggers due to repeated dispatch failures
        (strategy bugs). Unlike mark_session_interrupted, ERROR status
        prevents auto-recovery on restart to avoid infinite retry loops.

        Args:
            run_id: Run ID of the session to mark.
            error_message: Error description.
            result: Optional engine state snapshot to save as final result.
        """
        run = await self.run_repo.get(run_id)
        if run and run.status in (RunStatus.RUNNING, RunStatus.INTERRUPTED):
            await self.run_repo.update(
                run.id,
                status=RunStatus.ERROR,
                error_message=error_message,
                result=result,
                stopped_at=datetime.now(UTC),
            )
            await self.session.commit()
            logger.info(f"Marked session {run_id} as error: {error_message}")

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

    async def stop_all(self, *, for_shutdown: bool = False) -> int:
        """Stop all active paper trading sessions.

        Args:
            for_shutdown: If True, marks sessions as INTERRUPTED instead of
                STOPPED, enabling auto-recovery on next startup.

        Returns:
            Number of sessions stopped.
        """
        session_manager = get_session_manager()
        active = session_manager.list_sessions()
        stopped = 0

        for sess in active:
            run_id = UUID(sess["run_id"])
            try:
                await self.stop(run_id, for_shutdown=for_shutdown)
                stopped += 1
            except Exception as e:
                logger.warning(f"Failed to stop session {run_id}: {e}")

        logger.info(f"Stopped {stopped}/{len(active)} paper trading sessions")
        return stopped

    async def resume(
        self,
        run_id: UUID,
        warmup_bars: int = 200,
        redis: Any | None = None,
    ) -> StrategyRun:
        """Resume a stopped or errored paper trading session.

        Recreates the engine with saved state, replays historical bars
        for strategy warmup, and re-subscribes to market data.

        Args:
            run_id: Run ID of the session to resume.
            warmup_bars: Number of historical bars to replay for strategy warmup.
            redis: Redis client for circuit breaker check (optional).

        Returns:
            Updated StrategyRun.

        Raises:
            SessionNotFoundError: If session not found.
            SessionNotResumableError: If session cannot be resumed.
            SessionAlreadyRunningError: If a duplicate session is running.
        """
        from squant.config import get_settings
        from squant.services.strategy import StrategyRepository

        # Check circuit breaker state before resuming
        if redis is not None:
            await self._check_circuit_breaker(redis)

        # Load run from DB
        run = await self.run_repo.get(run_id)
        if not run:
            raise SessionNotFoundError(run_id)

        # Validate status is resumable
        if run.status not in (RunStatus.ERROR, RunStatus.STOPPED, RunStatus.INTERRUPTED):
            raise SessionNotResumableError(
                run_id,
                f"status is {run.status.value}, must be error, stopped, or interrupted",
            )

        # Check max concurrent sessions limit
        settings = get_settings()
        session_manager = get_session_manager()
        if session_manager.session_count >= settings.paper.max_sessions:
            raise MaxSessionsReachedError(settings.paper.max_sessions)

        # Check for duplicate running session
        has_running = await self.run_repo.has_running_session(
            strategy_id=run.strategy_id,
            symbol=run.symbol,
            mode=RunMode.PAPER,
        )
        if has_running:
            raise SessionAlreadyRunningError(
                message=f"A paper trading session for strategy {run.strategy_id} "
                f"on {run.symbol} is already running"
            )

        # Load and instantiate strategy
        strategy_repo = StrategyRepository(self.session)
        strategy_model = await strategy_repo.get(UUID(run.strategy_id))
        if not strategy_model:
            raise SessionNotResumableError(run_id, "strategy no longer exists")

        strategy_instance = self._instantiate_strategy(strategy_model.code)

        # Restore risk config from persisted result (if available)
        engine_risk_config = None
        if run.result and run.result.get("risk_config"):
            from squant.engine.risk.models import RiskConfig

            engine_risk_config = RiskConfig(**run.result["risk_config"])

        # Create engine with same parameters
        engine = PaperTradingEngine(
            run_id=UUID(run.id),
            strategy=strategy_instance,
            symbol=run.symbol,
            timeframe=run.timeframe,
            initial_capital=run.initial_capital,
            commission_rate=run.commission_rate,
            slippage=run.slippage or Decimal("0"),
            params=run.params,
            on_snapshot=self._create_snapshot_callback(),
            on_result=self._create_result_callback(),
            risk_config=engine_risk_config,
        )

        # Restore trading state from result JSONB
        if run.result:
            engine.context.restore_state(run.result)
            engine._bar_count = run.result.get("bar_count", 0)
            # Restore risk manager state (cumulative PnL, circuit breaker, etc.)
            if engine._risk_manager and run.result.get("risk_state"):
                engine._risk_manager.restore_state(run.result["risk_state"])

        # Register with session manager
        await session_manager.register(engine)

        subscribed = False
        try:
            # Subscribe to WebSocket candles and tickers (for spread simulation)
            stream_manager = get_stream_manager()
            await stream_manager.subscribe_candles(run.symbol, run.timeframe)
            subscribed = True
            await stream_manager.subscribe_ticker(run.symbol)

            # Start engine (calls strategy.on_init())
            await engine.start()

            # Warmup: replay historical bars through strategy to rebuild internal state
            if warmup_bars > 0:
                await self._warmup_strategy(engine, run, warmup_bars)

            # Update DB status to RUNNING
            run = await self.run_repo.update(
                run.id,
                status=RunStatus.RUNNING,
                error_message=None,
                stopped_at=None,
            )
            await self.session.commit()

            logger.info(f"Resumed paper trading session {run.id} (warmup={warmup_bars} bars)")
            return run

        except Exception as e:
            # Cleanup on failure
            if engine.is_running:
                try:
                    await engine.stop(error=f"Resume failed: {e}")
                except Exception:
                    pass

            key_to_unsub = await session_manager.unregister_and_check_subscription(engine.run_id)
            if subscribed:
                try:
                    stream_manager = get_stream_manager()
                    await stream_manager.unsubscribe_ticker(run.symbol)
                    if key_to_unsub:
                        await stream_manager.unsubscribe_candles(*key_to_unsub)
                except Exception:
                    pass

            raise

    async def _warmup_strategy(
        self,
        engine: PaperTradingEngine,
        run: StrategyRun,
        warmup_bars: int,
    ) -> None:
        """Replay historical bars through strategy to rebuild internal state.

        During warmup, bars are fed to strategy.on_bar() but no orders
        are processed, no equity snapshots are recorded, and nothing is
        persisted. This purely rebuilds strategy self.* attributes.

        Args:
            engine: The paper trading engine.
            run: The strategy run record.
            warmup_bars: Number of bars to replay.
        """
        from datetime import timedelta

        from squant.config import get_settings
        from squant.services.data_loader import DataLoader

        settings = get_settings()

        tf_durations = {
            "1m": 60,
            "5m": 300,
            "15m": 900,
            "30m": 1800,
            "1h": 3600,
            "4h": 14400,
            "1d": 86400,
            "1w": 604800,
        }
        tf_seconds = tf_durations.get(run.timeframe, 60)
        end_time = datetime.now(UTC)
        start_time = end_time - timedelta(seconds=tf_seconds * warmup_bars * 1.2)

        loader = DataLoader(self.session)
        bar_count = 0

        # Save a snapshot of logs before warmup so we can restore them afterward.
        # Using a snapshot instead of count-based pop() avoids deque overflow issues
        # when the log deque is near maxlen (warmup entries evict restored entries).
        logs_snapshot = list(engine.context._logs)

        async for bar in loader.load_bars(
            exchange=run.exchange,
            symbol=run.symbol,
            timeframe=run.timeframe,
            start=start_time,
            end=end_time,
        ):
            # Only update bar history and call strategy — no order processing
            engine.context._set_current_bar(bar)
            engine.context._add_bar_to_history(bar)
            try:
                with resource_limiter(
                    cpu_seconds=settings.strategy.cpu_limit_seconds,
                    memory_mb=settings.strategy.memory_limit_mb,
                ):
                    engine._strategy.on_bar(bar)
            except Exception as e:
                logger.debug(f"Warmup bar error (ignored): {e}")
            bar_count += 1
            if bar_count >= warmup_bars:
                break

        # F1: Clear pending orders generated by strategy during warmup.
        # Without this, warmup orders would be matched against the first
        # real candle and produce phantom trades.
        engine.context._pending_orders.clear()

        # F2: Restore pre-warmup logs (warmup generates trade logs from
        # ctx.buy/sell that would pollute the restored log list).
        engine.context._logs.clear()
        for entry in logs_snapshot:
            engine.context._logs.append(entry)

        logger.info(
            f"Warmup completed for session {engine.run_id}: {bar_count}/{warmup_bars} bars replayed"
        )

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

    async def get_equity_curve(self, run_id: UUID, since: datetime | None = None) -> list:
        """Get equity curve for a paper trading run.

        Merges persisted snapshots from DB with pending (not-yet-persisted)
        snapshots from engine memory for real-time data.

        Args:
            run_id: Run ID.
            since: If provided, only return records with time > since.

        Returns:
            List of equity curve records (EquityCurve + EquitySnapshot).

        Raises:
            SessionNotFoundError: If run not found.
        """
        # Verify run exists
        run = await self.run_repo.get(run_id)
        if not run:
            raise SessionNotFoundError(run_id)

        persisted = await self.equity_repo.get_by_run(str(run_id), since=since)

        # Append pending snapshots from engine memory for real-time updates
        session_manager = get_session_manager()
        engine = session_manager.get(run_id)
        if engine:
            pending = engine.peek_pending_snapshots()
            if since is not None:
                pending = [s for s in pending if s.time > since]
            if pending:
                return list(persisted) + pending

        return persisted

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

    async def mark_orphaned_sessions(self) -> int:
        """Mark orphaned RUNNING sessions as INTERRUPTED with equity recovery.

        Called on startup to recover from unexpected shutdowns.
        For each orphaned session, attempts to recover basic metrics
        from the last equity curve record and saves them to the result field.

        Returns:
            Number of sessions marked as INTERRUPTED.
        """
        orphaned = await self.run_repo.get_orphaned_sessions()
        if not orphaned:
            return 0

        for run in orphaned:
            # Preserve existing result (saved by on_result callback per candle).
            # Only fall back to equity curve when no result exists.
            result_data = run.result
            if not result_data:
                last_point = await self.equity_repo.get_last_by_run(str(run.id))
                if last_point:
                    result_data = {
                        "equity": str(last_point.equity),
                        "cash": str(last_point.cash),
                        "unrealized_pnl": str(last_point.unrealized_pnl),
                    }

            await self.run_repo.update(
                run.id,
                status=RunStatus.INTERRUPTED,
                result=result_data,
                error_message="Session terminated due to application restart",
                stopped_at=datetime.now(UTC),
            )

        await self.session.commit()
        return len(orphaned)

    async def recover_orphaned_sessions(self) -> tuple[int, int]:
        """Attempt to recover orphaned RUNNING sessions, falling back to INTERRUPTED.

        Called on startup after stream manager is ready. For each orphaned
        session that has a saved result with sufficient state, attempts to
        resume the session. Sessions that fail to resume are marked INTERRUPTED
        with equity curve recovery as fallback.

        Returns:
            Tuple of (recovered_count, failed_count).
        """
        from squant.config import get_settings

        settings = get_settings()
        if not settings.paper.auto_recovery:
            # Auto-recovery disabled, fall back to marking as INTERRUPTED
            count = await self.mark_orphaned_sessions()
            return 0, count

        orphaned = await self.run_repo.get_orphaned_sessions()
        if not orphaned:
            return 0, 0

        recovered = 0
        failed = 0

        for run in orphaned:
            # Try to resume if result has enough state
            if run.result and run.result.get("cash"):
                try:
                    # Mark as INTERRUPTED so resume() accepts it
                    await self.run_repo.update(
                        run.id,
                        status=RunStatus.INTERRUPTED,
                        error_message="Session interrupted by application restart, recovering...",
                    )
                    await self.session.commit()

                    await self.resume(
                        UUID(run.id),
                        warmup_bars=settings.paper.warmup_bars,
                    )
                    recovered += 1
                    logger.info(f"Auto-recovered orphaned session {run.id}")
                    continue
                except Exception as e:
                    logger.warning(f"Auto-recovery failed for session {run.id}: {e}")
                    # Mark as ERROR to prevent infinite retry on next restart
                    await self.run_repo.update(
                        run.id,
                        status=RunStatus.ERROR,
                        error_message=f"Auto-recovery failed: {e}",
                        stopped_at=datetime.now(UTC),
                    )
                    await self.session.commit()
                    failed += 1
                    continue

            # No saved state — mark as INTERRUPTED
            result_data = run.result
            if not result_data:
                last_point = await self.equity_repo.get_last_by_run(str(run.id))
                if last_point:
                    result_data = {
                        "equity": str(last_point.equity),
                        "cash": str(last_point.cash),
                        "unrealized_pnl": str(last_point.unrealized_pnl),
                    }

            await self.run_repo.update(
                run.id,
                status=RunStatus.INTERRUPTED,
                result=result_data,
                error_message="Session terminated due to application restart",
                stopped_at=datetime.now(UTC),
            )
            await self.session.commit()
            failed += 1

        return recovered, failed

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
                "benchmark_equity": snapshot.benchmark_equity,
            }
            for snapshot in snapshots
        ]
        await self.equity_repo.bulk_create(records)
