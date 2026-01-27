"""Live trading service for managing real-time trading sessions with exchange execution.

Provides high-level operations for:
- Starting and stopping live trading sessions
- Managing session lifecycle with risk controls
- Emergency close functionality
- Persisting equity curves
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from squant.engine.backtest.strategy_base import Strategy
from squant.engine.backtest.types import EquitySnapshot
from squant.engine.live.engine import LiveTradingEngine
from squant.engine.live.manager import get_live_session_manager
from squant.engine.risk import RiskConfig
from squant.engine.sandbox import compile_strategy
from squant.infra.exchange.okx.adapter import OKXAdapter
from squant.infra.repository import BaseRepository
from squant.models.enums import RunMode, RunStatus
from squant.models.metrics import EquityCurve
from squant.models.strategy import Strategy as StrategyModel
from squant.models.strategy import StrategyRun

if TYPE_CHECKING:
    from squant.infra.exchange.base import ExchangeAdapter

logger = logging.getLogger(__name__)


class LiveTradingError(Exception):
    """Base error for live trading operations."""

    pass


class SessionNotFoundError(LiveTradingError):
    """Live trading session not found."""

    def __init__(self, run_id: str | UUID):
        self.run_id = str(run_id)
        super().__init__(f"Live trading session not found: {run_id}")


class SessionAlreadyRunningError(LiveTradingError):
    """Live trading session already running."""

    def __init__(self, run_id: str | UUID):
        self.run_id = str(run_id)
        super().__init__(f"Live trading session already running: {run_id}")


class RiskConfigurationError(LiveTradingError):
    """Risk configuration is missing or invalid."""

    pass


class StrategyInstantiationError(LiveTradingError):
    """Error instantiating strategy from code."""

    pass


class ExchangeConnectionError(LiveTradingError):
    """Error connecting to exchange."""

    pass


class LiveStrategyRunRepository(BaseRepository[StrategyRun]):
    """Repository for live trading StrategyRun model."""

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
        """Mark all RUNNING live trading sessions as ERROR.

        Called on startup to recover from unexpected shutdowns.
        Sessions that were RUNNING when the application crashed are
        orphaned and need to be marked as ERROR.

        Returns:
            Number of sessions marked as ERROR.
        """
        stmt = (
            update(StrategyRun)
            .where(
                StrategyRun.mode == RunMode.LIVE,
                StrategyRun.status == RunStatus.RUNNING,
            )
            .values(
                status=RunStatus.ERROR,
                error_message="Session terminated due to application restart",
                stopped_at=datetime.now(timezone.utc),
            )
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount


class LiveEquityCurveRepository:
    """Repository for live trading EquityCurve records."""

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
            select(EquityCurve)
            .where(EquityCurve.run_id == run_id)
            .order_by(EquityCurve.time.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class LiveTradingService:
    """Service for live trading operations.

    Manages live trading sessions with real exchange execution.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.run_repo = LiveStrategyRunRepository(session)
        self.equity_repo = LiveEquityCurveRepository(session)

    async def start(
        self,
        strategy_id: UUID,
        symbol: str,
        exchange: str,
        timeframe: str,
        risk_config: RiskConfig,
        initial_equity: Decimal | None = None,
        params: dict[str, Any] | None = None,
    ) -> StrategyRun:
        """Start a live trading session.

        Args:
            strategy_id: Strategy ID to run.
            symbol: Trading symbol.
            exchange: Exchange name.
            timeframe: Candle timeframe.
            risk_config: Risk management configuration.
            initial_equity: Initial equity for risk calculations (fetched from exchange if None).
            params: Strategy parameters.

        Returns:
            Created StrategyRun.

        Raises:
            StrategyNotFoundError: If strategy not found.
            StrategyInstantiationError: If strategy cannot be instantiated.
            RiskConfigurationError: If risk config is invalid.
            ExchangeConnectionError: If exchange connection fails.
        """
        from squant.services.strategy import StrategyNotFoundError, StrategyRepository

        # Validate risk configuration
        self._validate_risk_config(risk_config)

        # Verify strategy exists
        strategy_repo = StrategyRepository(self.session)
        strategy = await strategy_repo.get(strategy_id)
        if not strategy:
            raise StrategyNotFoundError(strategy_id)

        # Create exchange adapter
        adapter = self._create_adapter(exchange)

        # Connect to exchange and get initial equity if not provided
        try:
            await adapter.connect()
            if initial_equity is None:
                balance = await adapter.get_balance()
                quote_currency = symbol.split("/")[1]  # e.g., "USDT"
                quote_balance = balance.get_balance(quote_currency)
                if quote_balance:
                    initial_equity = quote_balance.available
                else:
                    initial_equity = Decimal("0")
                logger.info(f"Fetched initial equity from exchange: {initial_equity}")
        except Exception as e:
            raise ExchangeConnectionError(f"Failed to connect to exchange: {e}") from e

        # Create run record
        run = await self.run_repo.create(
            strategy_id=str(strategy_id),
            mode=RunMode.LIVE,
            symbol=symbol,
            exchange=exchange,
            timeframe=timeframe,
            initial_capital=initial_equity,
            commission_rate=Decimal("0"),  # Real fees from exchange
            slippage=Decimal("0"),
            params=params or {},
            status=RunStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
        )
        await self.session.commit()

        engine = None
        subscribed = False
        session_manager = get_live_session_manager()

        try:
            # Instantiate strategy
            strategy_instance = self._instantiate_strategy(strategy.code)

            # Create engine
            engine = LiveTradingEngine(
                run_id=UUID(run.id),
                strategy=strategy_instance,
                symbol=symbol,
                timeframe=timeframe,
                adapter=adapter,
                risk_config=risk_config,
                initial_equity=initial_equity,
                params=params,
            )

            # Register with session manager
            await session_manager.register(engine)

            # Subscribe to WebSocket candles
            from squant.websocket.manager import get_stream_manager

            stream_manager = get_stream_manager()
            await stream_manager.subscribe_candles(symbol, timeframe)
            subscribed = True

            # Start engine
            await engine.start()

            logger.info(
                f"Started live trading session {run.id} for strategy {strategy_id}"
            )

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
                stopped_at=datetime.now(timezone.utc),
            )
            await self.session.commit()
            raise

    def _validate_risk_config(self, config: RiskConfig) -> None:
        """Validate risk configuration.

        Args:
            config: Risk configuration to validate.

        Raises:
            RiskConfigurationError: If config is invalid.
        """
        if config.max_position_size <= 0:
            raise RiskConfigurationError("max_position_size must be positive")
        if config.max_order_size <= 0:
            raise RiskConfigurationError("max_order_size must be positive")
        if config.daily_trade_limit <= 0:
            raise RiskConfigurationError("daily_trade_limit must be positive")
        if config.daily_loss_limit <= 0:
            raise RiskConfigurationError("daily_loss_limit must be positive")

    def _create_adapter(self, exchange: str) -> ExchangeAdapter:
        """Create exchange adapter.

        Args:
            exchange: Exchange name.

        Returns:
            Exchange adapter instance.

        Raises:
            ValueError: If exchange not supported.
        """
        if exchange.lower() == "okx":
            return OKXAdapter()
        raise ValueError(f"Unsupported exchange: {exchange}")

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
            for name, obj in local_namespace.items():
                if (
                    isinstance(obj, type)
                    and issubclass(obj, StrategyBase)
                    and obj is not StrategyBase
                ):
                    strategy_class = obj
                    break

            if strategy_class is None:
                raise StrategyInstantiationError(
                    "No Strategy subclass found in strategy code"
                )

            # Instantiate
            return strategy_class()

        except ValueError as e:
            raise StrategyInstantiationError(f"Strategy compilation failed: {e}") from e
        except Exception as e:
            raise StrategyInstantiationError(
                f"Strategy instantiation failed: {e}"
            ) from e

    async def stop(self, run_id: UUID, cancel_orders: bool = True) -> StrategyRun:
        """Stop a live trading session.

        Args:
            run_id: Run ID.
            cancel_orders: Whether to cancel open orders on stop.

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
        session_manager = get_live_session_manager()
        engine = session_manager.get(run_id)

        if engine:
            # Persist any pending snapshots
            await self._persist_snapshots(str(run_id), engine.get_pending_snapshots())

            # Stop engine
            await engine.stop(cancel_orders=cancel_orders)

            # Unregister from session manager
            await session_manager.unregister(run_id)

            # Check if we should unsubscribe from candles
            await self._check_unsubscribe(engine.symbol, engine.timeframe)

        # Update run status
        run = await self.run_repo.update(
            run.id,
            status=RunStatus.STOPPED,
            stopped_at=datetime.now(timezone.utc),
            error_message=engine.error_message if engine else None,
        )
        await self.session.commit()

        logger.info(f"Stopped live trading session {run_id}")
        return run

    async def emergency_close(self, run_id: UUID) -> dict[str, Any]:
        """Emergency close all positions and stop the session.

        Args:
            run_id: Run ID.

        Returns:
            Results of the emergency close operation.

        Raises:
            SessionNotFoundError: If session not found.
        """
        # Get run record
        run = await self.run_repo.get(run_id)
        if not run:
            raise SessionNotFoundError(run_id)

        # Get engine from session manager
        session_manager = get_live_session_manager()
        engine = session_manager.get(run_id)

        if not engine:
            # Session not active
            return {
                "run_id": str(run_id),
                "status": "not_active",
                "message": "Session is not currently running",
            }

        # Execute emergency close
        results = await engine.emergency_close()

        # Unregister from session manager
        await session_manager.unregister(run_id)

        # Check if we should unsubscribe from candles
        await self._check_unsubscribe(engine.symbol, engine.timeframe)

        # Update run status
        await self.run_repo.update(
            run.id,
            status=RunStatus.STOPPED,
            stopped_at=datetime.now(timezone.utc),
            error_message="Emergency close executed",
        )
        await self.session.commit()

        logger.warning(f"Emergency close executed for live session {run_id}")

        return {
            "run_id": str(run_id),
            "status": "closed",
            **results,
        }

    async def _check_unsubscribe(self, symbol: str, timeframe: str) -> None:
        """Check if we should unsubscribe from candles.

        Only unsubscribes if no other sessions need this symbol/timeframe.

        Args:
            symbol: Trading symbol.
            timeframe: Candle timeframe.
        """
        session_manager = get_live_session_manager()
        subscribed_symbols = session_manager.get_subscribed_symbols()

        if (symbol, timeframe) not in subscribed_symbols:
            from squant.websocket.manager import get_stream_manager

            stream_manager = get_stream_manager()
            await stream_manager.unsubscribe_candles(symbol, timeframe)
            logger.info(f"Unsubscribed from candles: {symbol}:{timeframe}")

    async def get_status(self, run_id: UUID) -> dict[str, Any]:
        """Get real-time status of a live trading session.

        Args:
            run_id: Run ID.

        Returns:
            Status dictionary with live order tracking and risk state.

        Raises:
            SessionNotFoundError: If session not found.
        """
        # Get run record
        run = await self.run_repo.get(run_id)
        if not run:
            raise SessionNotFoundError(run_id)

        # Get engine from session manager
        session_manager = get_live_session_manager()
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
            "live_orders": [],
            "completed_orders_count": 0,
            "trades_count": 0,
            "risk_state": None,
        }

    def list_active(self) -> list[dict[str, Any]]:
        """List all active live trading sessions.

        Returns:
            List of session state snapshots.
        """
        session_manager = get_live_session_manager()
        return session_manager.list_sessions()

    async def list_runs(
        self,
        page: int = 1,
        page_size: int = 20,
        status: RunStatus | None = None,
    ) -> tuple[list[StrategyRun], int]:
        """List live trading runs.

        Args:
            page: Page number (1-indexed).
            page_size: Items per page.
            status: Optional status filter.

        Returns:
            Tuple of (runs, total_count).
        """
        offset = (page - 1) * page_size
        runs = await self.run_repo.list_by_mode(
            RunMode.LIVE,
            status=status,
            offset=offset,
            limit=page_size,
        )
        total = await self.run_repo.count_by_mode(RunMode.LIVE, status)
        return runs, total

    async def get_run(self, run_id: UUID) -> StrategyRun:
        """Get a live trading run by ID.

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
        """Get equity curve for a live trading run.

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
        session_manager = get_live_session_manager()
        engine = session_manager.get(run_id)

        if not engine:
            return 0

        snapshots = engine.get_pending_snapshots()
        if not snapshots:
            return 0

        await self._persist_snapshots(str(run_id), snapshots)
        await self.session.commit()

        return len(snapshots)

    async def _persist_snapshots(
        self, run_id: str, snapshots: list[EquitySnapshot]
    ) -> None:
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

    async def mark_orphaned_sessions(self) -> int:
        """Mark orphaned RUNNING sessions as ERROR.

        Should be called on application startup.

        Returns:
            Number of sessions marked as ERROR.
        """
        return await self.run_repo.mark_orphaned_sessions()
