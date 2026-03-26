"""Live trading service for managing real-time trading sessions with exchange execution.

Provides high-level operations for:
- Starting and stopping live trading sessions
- Managing session lifecycle with risk controls
- Emergency close functionality
- Persisting equity curves
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from squant.engine.backtest.strategy_base import Strategy
from squant.engine.backtest.types import EquitySnapshot
from squant.engine.live.engine import LiveTradingEngine
from squant.engine.live.manager import get_live_session_manager
from squant.engine.risk import RiskConfig
from squant.engine.sandbox import compile_strategy
from squant.infra.exchange.ccxt import CCXTRestAdapter, ExchangeCredentials
from squant.infra.repository import BaseRepository
from squant.infra.trading_logger import close_trading_logger, create_trading_logger
from squant.models.enums import OrderSide, OrderStatus, OrderType, RunMode, RunStatus
from squant.models.exchange import ExchangeAccount
from squant.models.metrics import EquityCurve
from squant.models.strategy import StrategyRun

if TYPE_CHECKING:
    from squant.infra.exchange.base import ExchangeAdapter
    from squant.schemas.live_trading import AccountBalanceResponse

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

    def __init__(self, run_id: str | UUID | None = None, *, message: str | None = None):
        self.run_id = str(run_id) if run_id else None
        if message:
            super().__init__(message)
        else:
            super().__init__(f"Live trading session already running: {run_id}")


class RiskConfigurationError(LiveTradingError):
    """Risk configuration is missing or invalid."""

    pass


class StrategyInstantiationError(LiveTradingError):
    """Error instantiating strategy from code."""

    pass


class LiveExchangeConnectionError(LiveTradingError):
    """Error connecting to exchange in live trading service layer."""

    pass


# Backward compatibility alias
ExchangeConnectionError = LiveExchangeConnectionError


class ExchangeAccountNotFoundError(LiveTradingError):
    """Exchange account not found or not active."""

    def __init__(self, account_id: str | UUID, reason: str = "not found"):
        self.account_id = str(account_id)
        self.reason = reason
        super().__init__(f"Exchange account {account_id}: {reason}")


class CircuitBreakerActiveError(LiveTradingError):
    """Cannot start trading when circuit breaker is active."""

    def __init__(self, reason: str | None = None):
        message = "Cannot start live trading: circuit breaker is active"
        if reason:
            message += f" (reason: {reason})"
        super().__init__(message)


class SessionNotResumableError(LiveTradingError):
    """Session cannot be resumed."""

    def __init__(self, run_id: str | UUID, reason: str):
        self.run_id = str(run_id)
        self.reason = reason
        super().__init__(f"Session {run_id} cannot be resumed: {reason}")


class MaxSessionsReachedError(LiveTradingError):
    """Maximum number of concurrent sessions reached."""

    def __init__(self, max_sessions: int):
        self.max_sessions = max_sessions
        super().__init__(f"Maximum concurrent live sessions reached: {max_sessions}")


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

        if status is not None:
            stmt = stmt.where(StrategyRun.status == status)

        stmt = stmt.order_by(StrategyRun.created_at.desc()).offset(offset).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_ids(self, ids: list[str | UUID]) -> list[StrategyRun]:
        """Batch-fetch runs by a list of IDs.

        Args:
            ids: List of run IDs.

        Returns:
            List of StrategyRun records found.
        """
        if not ids:
            return []
        str_ids = [str(i) for i in ids]
        stmt = select(StrategyRun).where(StrategyRun.id.in_(str_ids))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

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

    async def count_by_mode(
        self,
        mode: RunMode,
        status: RunStatus | None = None,
    ) -> int:
        """Count runs by mode."""
        filters: dict[str, Any] = {"mode": mode}
        if status is not None:
            filters["status"] = status
        return await self.count(**filters)

    async def list_running_by_account(self, account_id: str) -> list[StrategyRun]:
        """List all RUNNING sessions for a given exchange account."""
        result = await self.session.execute(
            select(StrategyRun).where(
                StrategyRun.account_id == account_id,
                StrategyRun.mode == RunMode.LIVE,
                StrategyRun.status == RunStatus.RUNNING,
            )
        )
        return list(result.scalars().all())

    async def get_orphaned_sessions(self) -> list[StrategyRun]:
        """Get recoverable live trading sessions after restart.

        Finds sessions that were either:
        - RUNNING (force-killed, no graceful shutdown)
        - INTERRUPTED (gracefully stopped during application shutdown)

        Returns:
            List of recoverable StrategyRun records.
        """
        stmt = select(StrategyRun).where(
            StrategyRun.mode == RunMode.LIVE,
            StrategyRun.status.in_([RunStatus.RUNNING, RunStatus.INTERRUPTED]),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def mark_orphaned_sessions(self) -> int:
        """Mark all RUNNING live trading sessions as INTERRUPTED.

        Called on startup to recover from unexpected shutdowns.
        Sessions that were RUNNING when the application crashed are
        orphaned and need to be marked as INTERRUPTED.

        Returns:
            Number of sessions marked as INTERRUPTED.
        """
        stmt = (
            update(StrategyRun)
            .where(
                StrategyRun.mode == RunMode.LIVE,
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
        exchange_account_id: UUID,
        timeframe: str,
        risk_config: RiskConfig,
        initial_equity: Decimal | None = None,
        params: dict[str, Any] | None = None,
    ) -> StrategyRun:
        """Start a live trading session.

        Args:
            strategy_id: Strategy ID to run.
            symbol: Trading symbol.
            exchange_account_id: Exchange account ID with API credentials.
            timeframe: Candle timeframe.
            risk_config: Risk management configuration.
            initial_equity: Initial equity for risk calculations (fetched from exchange if None).
            params: Strategy parameters.

        Returns:
            Created StrategyRun.

        Raises:
            StrategyNotFoundError: If strategy not found.
            ExchangeAccountNotFoundError: If exchange account not found or not active.
            StrategyInstantiationError: If strategy cannot be instantiated.
            RiskConfigurationError: If risk config is invalid.
            ExchangeConnectionError: If exchange connection fails.
            CircuitBreakerActiveError: If circuit breaker is active.
        """
        from squant.services.account import ExchangeAccountRepository
        from squant.services.strategy import StrategyNotFoundError, StrategyRepository

        # Check circuit breaker state before starting (LIVE-OP-001)
        await self._check_circuit_breaker()

        # Check session limits (LIVE-EX-005)
        from squant.config import get_settings as _get_settings

        session_manager = get_live_session_manager()
        _settings = _get_settings()
        if session_manager.session_count >= _settings.live.max_sessions:
            raise MaxSessionsReachedError(_settings.live.max_sessions)

        # Validate risk configuration
        self._validate_risk_config(risk_config)

        # Check for duplicate running session (R3-003, mirrors PP-C03)
        has_running = await self.run_repo.has_running_session(
            strategy_id=str(strategy_id),
            symbol=symbol,
            mode=RunMode.LIVE,
        )
        if has_running:
            raise SessionAlreadyRunningError(
                message=f"A live trading session for strategy {strategy_id} on {symbol} is already running"
            )

        # Verify strategy exists
        strategy_repo = StrategyRepository(self.session)
        strategy = await strategy_repo.get(strategy_id)
        if not strategy:
            raise StrategyNotFoundError(strategy_id)

        # Fetch and validate exchange account
        account_repo = ExchangeAccountRepository(self.session)
        exchange_account = await account_repo.get(exchange_account_id)
        if not exchange_account:
            raise ExchangeAccountNotFoundError(exchange_account_id, "not found")
        if not exchange_account.is_active:
            raise ExchangeAccountNotFoundError(exchange_account_id, "account is not active")

        # Create exchange adapter with credentials
        adapter = self._create_adapter(exchange_account)

        # Build WS credentials for private order push (LIVE-CN-001)
        ws_credentials = self._build_ws_credentials(exchange_account)

        quote_currency = symbol.split("/")[1]  # e.g., "USDT"

        # Connect to exchange and get initial equity if not provided
        try:
            await asyncio.wait_for(adapter.connect(), timeout=30.0)
            if initial_equity is None:
                balance = await adapter.get_balance()
                quote_balance = balance.get_balance(quote_currency)
                initial_equity = quote_balance.total if quote_balance else Decimal("0")
                logger.info(f"Fetched initial equity from exchange: {initial_equity}")
        except Exception as e:
            try:
                await adapter.close()
            except Exception:
                pass
            raise LiveExchangeConnectionError(f"Failed to connect to exchange: {e}") from e

        # Validate initial equity is positive to prevent division-by-zero in risk calculations
        if initial_equity <= Decimal("0"):
            try:
                await adapter.close()
            except Exception:
                pass
            raise LiveTradingError(
                f"Insufficient {quote_currency} balance to start live trading. "
                f"Available balance: {initial_equity}"
            )

        # Validate initial equity does not exceed available balance (B1 check)
        try:
            await self._check_balance_sufficiency(
                adapter=adapter,
                account_id=str(exchange_account_id),
                required_equity=initial_equity,
                quote_currency=quote_currency,
            )
        except LiveTradingError:
            try:
                await adapter.close()
            except Exception:
                pass
            raise

        # Create run record
        run = await self.run_repo.create(
            strategy_id=str(strategy_id),
            account_id=str(exchange_account_id),
            mode=RunMode.LIVE,
            symbol=symbol,
            exchange=exchange_account.exchange,
            timeframe=timeframe,
            initial_capital=initial_equity,
            commission_rate=Decimal("0"),  # Real fees from exchange
            slippage=Decimal("0"),
            params=params or {},
            status=RunStatus.RUNNING,
            started_at=datetime.now(UTC),
        )
        await self.session.commit()

        engine = None
        subscribed = False
        session_manager = get_live_session_manager()

        try:
            # Instantiate strategy
            strategy_instance = self._instantiate_strategy(strategy.code)

            # Create engine with synchronous persistence callbacks
            engine = LiveTradingEngine(
                run_id=UUID(run.id),
                strategy=strategy_instance,
                symbol=symbol,
                timeframe=timeframe,
                adapter=adapter,
                risk_config=risk_config,
                initial_equity=initial_equity,
                params=params,
                on_snapshot=self._create_snapshot_callback(),
                on_result=self._create_result_callback(),
                on_event=self._create_event_callback(UUID(run.id)),
                on_order_persist=self._create_order_persist_callback(
                    account_id=str(exchange_account_id),
                    exchange=exchange_account.exchange,
                ),
                credentials=ws_credentials,
                exchange_id=exchange_account.exchange.lower(),
            )

            # Register with session manager
            await session_manager.register(engine)

            # Subscribe to WebSocket candles (public data via global StreamManager)
            from squant.websocket.manager import get_stream_manager

            stream_manager = get_stream_manager()
            await stream_manager.subscribe_candles(symbol, timeframe)
            subscribed = True
            # Note: private order WS is handled by engine's own CCXTStreamProvider (LIVE-CN-001)

            # Start engine
            await engine.start()

            # Create per-session file logger after successful start
            engine._context._file_logger = create_trading_logger(str(run.id))

            logger.info(f"Started live trading session {run.id} for strategy {strategy_id}")

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

            # Cleanup: close adapter to release aiohttp resources (fix #1)
            try:
                await adapter.close()
            except Exception as cleanup_error:
                logger.warning(f"Failed to close adapter during error handling: {cleanup_error}")

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

    async def _check_circuit_breaker(self) -> None:
        """Check if circuit breaker is active and raise error if so.

        Fetches Redis client internally so callers never accidentally skip the check.
        If the cooldown period has expired, automatically clears the state.

        Raises:
            CircuitBreakerActiveError: If circuit breaker is active and cooldown not expired.
        """
        import json
        from datetime import UTC, datetime

        from squant.infra.redis import get_redis_client
        from squant.services.circuit_breaker import CIRCUIT_BREAKER_STATE_KEY

        try:
            redis = get_redis_client()
            state_data = await redis.get(CIRCUIT_BREAKER_STATE_KEY)
            if state_data:
                state = json.loads(state_data)
                if state.get("is_active", False):
                    # Check if cooldown has expired
                    cooldown_until = state.get("cooldown_until")
                    if cooldown_until:
                        expiry = datetime.fromisoformat(cooldown_until)
                        if expiry.tzinfo is None:
                            expiry = expiry.replace(tzinfo=UTC)
                        if datetime.now(UTC) >= expiry:
                            await redis.delete(CIRCUIT_BREAKER_STATE_KEY)
                            logger.info("Circuit breaker cooldown expired, auto-cleared")
                            return
                    raise CircuitBreakerActiveError(state.get("trigger_reason"))
        except CircuitBreakerActiveError:
            raise
        except Exception:
            logger.warning("Failed to check circuit breaker state in Redis", exc_info=True)

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

    def _create_adapter(self, account: ExchangeAccount) -> ExchangeAdapter:
        """Create exchange adapter with account credentials.

        Args:
            account: Exchange account with encrypted credentials.

        Returns:
            Exchange adapter instance with injected credentials.

        Raises:
            ValueError: If exchange not supported.
            ExchangeConnectionError: If credentials cannot be decrypted.
        """
        from squant.services.account import ExchangeAccountService
        from squant.utils.crypto import DecryptionError

        # Decrypt credentials
        try:
            account_service = ExchangeAccountService(self.session)
            credentials = account_service.get_decrypted_credentials(account)
        except DecryptionError as e:
            raise LiveExchangeConnectionError(f"Failed to decrypt credentials: {e}") from e

        exchange = account.exchange.lower()

        ccxt_credentials = ExchangeCredentials(
            api_key=credentials["api_key"],
            api_secret=credentials["api_secret"],
            passphrase=credentials.get("passphrase"),
            sandbox=account.testnet,
        )
        return CCXTRestAdapter(exchange, ccxt_credentials)

    async def _create_adapter_for_account(self, account_id: str) -> ExchangeAdapter:
        """Create and connect an exchange adapter for the given account."""
        from squant.services.account import ExchangeAccountRepository

        account_repo = ExchangeAccountRepository(self.session)
        account = await account_repo.get(UUID(account_id))
        if not account:
            raise ExchangeAccountNotFoundError(account_id, "not found")
        if not account.is_active:
            raise ExchangeAccountNotFoundError(account_id, "account is not active")

        adapter = self._create_adapter(account)
        try:
            await asyncio.wait_for(adapter.connect(), timeout=30.0)
        except Exception as e:
            try:
                await adapter.close()
            except Exception:
                pass
            raise LiveExchangeConnectionError(f"Failed to connect to exchange: {e}") from e
        return adapter

    def _build_ws_credentials(self, account: ExchangeAccount) -> ExchangeCredentials | None:
        """Build ExchangeCredentials for private WS order push (LIVE-CN-001).

        Returns None if credentials cannot be decrypted (engine falls back to polling).
        """
        from squant.services.account import ExchangeAccountService
        from squant.utils.crypto import DecryptionError

        try:
            account_service = ExchangeAccountService(self.session)
            creds = account_service.get_decrypted_credentials(account)
        except DecryptionError as e:
            logger.warning(f"Cannot build WS credentials: {e}. Order updates via polling only.")
            return None

        try:
            return ExchangeCredentials(
                api_key=creds["api_key"],
                api_secret=creds["api_secret"],
                passphrase=creds.get("passphrase"),
                sandbox=account.testnet,
            )
        except (KeyError, TypeError) as e:
            logger.warning(f"Malformed credentials for WS: {e}. Order updates via polling only.")
            return None

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

            # Inject Strategy base class and types into globals
            from squant.engine.backtest import indicators as ta_module
            from squant.engine.backtest.strategy_base import Strategy as StrategyBase
            from squant.engine.backtest.types import (
                Bar,
                Fill,
                OrderSide,
                OrderStatus,
                OrderType,
                Position,
            )

            compiled.restricted_globals["Strategy"] = StrategyBase
            compiled.restricted_globals["Bar"] = Bar
            compiled.restricted_globals["Position"] = Position
            compiled.restricted_globals["OrderSide"] = OrderSide
            compiled.restricted_globals["OrderType"] = OrderType
            compiled.restricted_globals["Fill"] = Fill
            compiled.restricted_globals["OrderStatus"] = OrderStatus
            compiled.restricted_globals["ta"] = ta_module

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

    @staticmethod
    def _create_snapshot_callback() -> Any:
        """Create a callback for synchronous snapshot persistence.

        Returns a closure that opens its own DB session to persist a single
        equity snapshot. This keeps the engine DB-agnostic.
        """

        async def _persist_single(run_id: str, snapshot: EquitySnapshot) -> None:
            from squant.infra.database import get_session_context

            async with get_session_context() as db_session:
                repo = LiveEquityCurveRepository(db_session)
                await repo.bulk_create(
                    [
                        {
                            "time": snapshot.time,
                            "run_id": run_id,
                            "equity": snapshot.equity,
                            "cash": snapshot.cash,
                            "position_value": snapshot.position_value,
                            "unrealized_pnl": snapshot.unrealized_pnl,
                        }
                    ]
                )

        return _persist_single

    @staticmethod
    def _create_result_callback() -> Any:
        """Create a callback for synchronous result state persistence.

        Returns a closure that opens its own DB session to update the
        StrategyRun.result JSONB with the latest trading state.
        """

        async def _persist_result(run_id: str, result: dict) -> None:
            from squant.infra.database import get_session_context

            async with get_session_context() as db_session:
                repo = LiveStrategyRunRepository(db_session)
                await repo.update(run_id, result=result)

        return _persist_result

    @staticmethod
    def _create_order_persist_callback(
        account_id: str,
        exchange: str,
        seed_map: dict[str, str] | None = None,
    ) -> Any:
        """Create a callback for order/trade audit persistence (LIVE-013).

        Returns a closure that opens its own DB session to persist order
        placement and fill events to the orders/trades audit tables.

        Args:
            account_id: Exchange account ID.
            exchange: Exchange name (e.g. "okx").
            seed_map: Optional pre-populated internal_id → DB order UUID mapping.
                Used on resume to link existing DB orders to restored engine orders.
        """
        # Map engine internal_id → DB order UUID (kept across events)
        order_id_map: dict[str, str] = dict(seed_map) if seed_map else {}

        async def _persist_orders(run_id: str, events: list[dict]) -> None:
            from squant.infra.database import get_session_context
            from squant.services.order import OrderRepository, TradeRepository

            async with get_session_context() as db_session:
                order_repo = OrderRepository(db_session)
                trade_repo = TradeRepository(db_session)

                for event in events:
                    try:
                        if event["type"] == "placed":
                            order = await order_repo.create(
                                run_id=run_id,
                                account_id=account_id,
                                exchange=exchange,
                                exchange_oid=event.get("exchange_order_id"),
                                symbol=event["symbol"],
                                side=OrderSide(event["side"]),
                                type=OrderType(event["order_type"]),
                                amount=Decimal(event["amount"]),
                                price=Decimal(event["price"]) if event.get("price") else None,
                                status=OrderStatus(event["status"]),
                            )
                            order_id_map[event["internal_id"]] = order.id

                        elif event["type"] == "fill":
                            db_order_id = order_id_map.get(event["internal_id"])
                            if not db_order_id:
                                logger.warning(
                                    f"No DB order for internal_id={event['internal_id']}, "
                                    f"skipping fill"
                                )
                                continue

                            await trade_repo.create(
                                order_id=db_order_id,
                                price=Decimal(event["fill_price"]),
                                amount=Decimal(event["fill_amount"]),
                                fee=Decimal(event["fee"]),
                                fee_currency=event.get("fee_currency"),
                                timestamp=datetime.fromisoformat(event["timestamp"]),
                                fill_source=event.get("fill_source"),
                                exchange_tid=event.get("exchange_tid"),
                                taker_or_maker=event.get("taker_or_maker"),
                            )
                            # Update order with cumulative fill info
                            update_kwargs: dict[str, Any] = {
                                "filled": Decimal(event["total_filled"]),
                                "status": OrderStatus(event["status"]),
                            }
                            if event.get("avg_fill_price"):
                                update_kwargs["avg_price"] = Decimal(event["avg_fill_price"])
                            await order_repo.update(db_order_id, **update_kwargs)

                        elif event["type"] == "status_change":
                            db_order_id = order_id_map.get(event["internal_id"])
                            if not db_order_id:
                                logger.warning(
                                    f"No DB order for internal_id={event['internal_id']}, "
                                    f"skipping status_change"
                                )
                                continue
                            update_kwargs: dict[str, Any] = {
                                "status": OrderStatus(event["new_status"]),
                            }
                            if event.get("filled_amount"):
                                update_kwargs["filled"] = Decimal(event["filled_amount"])
                            if event.get("avg_fill_price"):
                                update_kwargs["avg_price"] = Decimal(event["avg_fill_price"])
                            await order_repo.update(db_order_id, **update_kwargs)

                        elif event["type"] == "correction":
                            internal_id = event["internal_id"]
                            db_order_id = order_id_map.get(internal_id)
                            if db_order_id:
                                # Update order fields based on corrections
                                update_data: dict[str, Any] = {}
                                for c in event.get("corrections", []):
                                    field = c["field"]
                                    if field == "filled_amount":
                                        update_data["filled"] = Decimal(c["after"])
                                    elif field == "avg_fill_price":
                                        update_data["avg_price"] = Decimal(c["after"])
                                    elif field == "status":
                                        status_map = {
                                            "submitted": OrderStatus.SUBMITTED,
                                            "partial": OrderStatus.PARTIAL,
                                            "filled": OrderStatus.FILLED,
                                            "cancelled": OrderStatus.CANCELLED,
                                            "rejected": OrderStatus.REJECTED,
                                        }
                                        mapped = status_map.get(c["after"])
                                        if mapped:
                                            update_data["status"] = mapped

                                if update_data:
                                    await order_repo.update(db_order_id, **update_data)

                                # Append correction record to JSONB field
                                order = await order_repo.get(db_order_id)
                                if order:
                                    existing = order.corrections or []
                                    existing.append(
                                        {
                                            "timestamp": event["timestamp"],
                                            "reason": event["reason"],
                                            "changes": event.get("corrections", []),
                                            "missing_trade_ids": event.get("missing_trade_ids", []),
                                        }
                                    )
                                    await order_repo.update(db_order_id, corrections=existing)

                        elif event["type"] == "enrichment":
                            # Async enrichment: update existing Trade records with
                            # per-fill details (exchange_tid, exact prices, taker_or_maker)
                            # fetched from REST get_order_trades after watchOrders fallback.
                            db_order_id = order_id_map.get(event["internal_id"])
                            if not db_order_id:
                                continue
                            for trade_data in event.get("trades", []):
                                # Try to match existing Trade by timestamp+amount
                                # and update with enrichment data
                                from squant.models.order import Trade

                                stmt = (
                                    select(Trade)
                                    .where(Trade.order_id == db_order_id)
                                    .where(Trade.exchange_tid.is_(None))
                                )
                                result = await db_session.execute(stmt)
                                unmatched_trades = result.scalars().all()

                                if unmatched_trades:
                                    # Update first unmatched trade with enrichment data
                                    trade_to_update = unmatched_trades[0]
                                    trade_to_update.exchange_tid = trade_data.get("exchange_tid")
                                    trade_to_update.taker_or_maker = trade_data.get(
                                        "taker_or_maker"
                                    )
                                    if trade_data.get("price"):
                                        trade_to_update.price = Decimal(trade_data["price"])
                                    if trade_data.get("amount"):
                                        trade_to_update.amount = Decimal(trade_data["amount"])
                                    if trade_data.get("fee"):
                                        trade_to_update.fee = abs(Decimal(trade_data["fee"]))
                                    if trade_data.get("fee_currency"):
                                        trade_to_update.fee_currency = trade_data["fee_currency"]

                            await db_session.commit()
                            logger.info(
                                f"Enriched trades for order {event.get('exchange_order_id')}"
                            )

                        else:
                            logger.warning(f"Unknown order event type: {event.get('type')}")

                    except Exception as e:
                        logger.warning(f"Failed to persist order event {event.get('type')}: {e}")

        return _persist_orders

    @staticmethod
    def _create_event_callback(run_id: UUID) -> Any:
        """Create callback that publishes engine events to Redis for WebSocket push."""

        async def _publish(event_data: dict) -> None:
            try:
                import json

                from squant.infra.redis import get_redis_client

                redis = get_redis_client()
                channel = f"squant:ws:trading:{run_id}"
                message = json.dumps(
                    {
                        "type": "trading_status",
                        "channel": f"trading:{run_id}",
                        "data": event_data,
                    }
                )
                await redis.publish(channel, message)
            except Exception as e:
                logger.debug(f"Failed to publish trading event: {e}")

        return _publish

    async def stop(
        self, run_id: UUID, cancel_orders: bool = True, *, for_shutdown: bool = False
    ) -> StrategyRun:
        """Stop a live trading session.

        Args:
            run_id: Run ID.
            cancel_orders: Whether to cancel open orders on stop.
            for_shutdown: If True, marks session as INTERRUPTED (application
                shutdown) instead of STOPPED, and skips candle unsubscription.

        Returns:
            Updated StrategyRun.

        Raises:
            SessionNotFoundError: If session not found.
            LiveTradingError: If session is in a terminal state (not for_shutdown).
        """
        # Get run record
        run = await self.run_repo.get(run_id)
        if not run:
            raise SessionNotFoundError(run_id)

        # Check status guard (skip for shutdown cleanup)
        if not for_shutdown and run.status not in (
            RunStatus.RUNNING,
            RunStatus.PENDING,
            RunStatus.INTERRUPTED,
        ):
            raise LiveTradingError(
                f"Cannot stop session {run_id}: current status is {run.status.value}"
            )

        # Get engine from session manager
        session_manager = get_live_session_manager()
        engine = session_manager.get(run_id)

        result_data = None

        if engine:
            # Persist any pending snapshots
            await self._persist_snapshots(str(run_id), engine.get_pending_snapshots())

            # Persist any pending risk triggers (Issue 010)
            await self.persist_risk_triggers(run_id)

            # Stop engine (may trigger final fills from cancel responses)
            await engine.stop(cancel_orders=cancel_orders)

            # Close file logger
            if engine._context._file_logger:
                close_trading_logger(engine._context._file_logger)

            # Flush any order events generated during stop (M-6: cancel fills)
            # process_candle() no longer runs after stop, so events from
            # _cancel_all_orders() would otherwise be lost.
            if engine._on_order_persist:
                pending_events = engine.get_pending_order_events()
                if pending_events:
                    try:
                        await engine._on_order_persist(str(run_id), pending_events)
                    except Exception as e:
                        logger.warning(f"Failed to persist stop-time order events: {e}")

            # Capture result AFTER stop so final fills from order cancellation
            # are included in the persisted state (crash recovery accuracy)
            result_data = engine.build_result_for_persistence()

            # Unregister from session manager
            await session_manager.unregister(run_id)

        # Determine status based on stop reason
        if for_shutdown:
            status = RunStatus.INTERRUPTED
            error_message = "Session interrupted by application shutdown"
        else:
            status = RunStatus.STOPPED
            error_message = engine.error_message if engine else None

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
        if engine and not for_shutdown:
            try:
                await self._check_unsubscribe(engine.symbol, engine.timeframe)
            except Exception as e:
                # Log but don't fail - database is already updated
                logger.warning(f"Failed to unsubscribe from candles: {e}")

        logger.info(f"{'Shutdown' if for_shutdown else 'Stopped'} live trading session {run_id}")
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

        # Flush any order events generated during emergency close (Issue 2:
        # same reasoning as M-6 in stop() — fill/cancel audit events would be lost)
        if engine._on_order_persist:
            pending_events = engine.get_pending_order_events()
            if pending_events:
                try:
                    await engine._on_order_persist(str(run_id), pending_events)
                except Exception as e:
                    logger.warning(f"Failed to persist emergency-close order events: {e}")

        # Persist engine final state (M-1: same as normal stop path)
        result_data = engine.build_result_for_persistence()

        # Unregister from session manager
        await session_manager.unregister(run_id)

        # Update run status and commit BEFORE unsubscribing (Issue 021 fix)
        # This ensures database state is consistent even if unsubscribe fails
        await self.run_repo.update(
            run.id,
            status=RunStatus.STOPPED,
            result=result_data,
            stopped_at=datetime.now(UTC),
            error_message="Emergency close executed",
        )
        await self.session.commit()

        # Now unsubscribe if needed (after database is consistent)
        try:
            await self._check_unsubscribe(engine.symbol, engine.timeframe)
        except Exception as e:
            # Log but don't fail - database is already updated
            logger.warning(f"Failed to unsubscribe from candles after emergency close: {e}")

        logger.warning(f"Emergency close executed for live session {run_id}")

        return {
            "run_id": str(run_id),
            **results,
        }

    async def _check_unsubscribe(self, symbol: str, timeframe: str) -> None:
        """Check if we should unsubscribe from candles.

        Only unsubscribes if no other sessions (live or paper) need this
        symbol/timeframe (R3-006: cross-manager check).

        Args:
            symbol: Trading symbol.
            timeframe: Candle timeframe.
        """
        from squant.engine.paper.manager import get_session_manager

        live_manager = get_live_session_manager()
        paper_manager = get_session_manager()

        live_subscribed = live_manager.get_subscribed_symbols()
        paper_subscribed = paper_manager.get_subscribed_symbols()

        if (symbol, timeframe) not in live_subscribed and (
            symbol,
            timeframe,
        ) not in paper_subscribed:
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
                    "live_orders": [],
                    "completed_orders_count": run.result.get("completed_orders_count", 0),
                    "trades_count": run.result.get("trades_count", 0),
                    "trades": run.result.get("trades", []),
                    "open_trade": run.result.get("open_trade"),
                    "risk_state": run.result.get("risk_state"),
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
                    "live_orders": [],
                    "completed_orders_count": 0,
                    "trades_count": 0,
                    "risk_state": None,
                }
            )

        return base_status

    def list_active(self) -> list[dict[str, Any]]:
        """List all active live trading sessions.

        Returns:
            List of session state snapshots.
        """
        session_manager = get_live_session_manager()
        return session_manager.list_sessions()

    async def get_runs_by_ids(self, ids: list[UUID]) -> dict[str, StrategyRun]:
        """Batch-fetch runs by IDs and return a lookup dict.

        Args:
            ids: List of run UUIDs.

        Returns:
            Dict mapping run_id (str) -> StrategyRun.
        """
        runs = await self.run_repo.get_by_ids(ids)
        return {str(r.id): r for r in runs if r.mode == RunMode.LIVE}

    async def stop_all(self, *, for_shutdown: bool = False) -> int:
        """Stop all active live trading sessions.

        Args:
            for_shutdown: If True, marks sessions as INTERRUPTED instead of
                STOPPED, enabling auto-recovery on next startup.

        Returns:
            Number of sessions stopped.
        """
        session_manager = get_live_session_manager()
        active = session_manager.list_sessions()
        stopped = 0

        for sess in active:
            run_id = UUID(sess["run_id"])
            try:
                await self.stop(run_id, for_shutdown=for_shutdown)
                stopped += 1
            except Exception as e:
                logger.warning(f"Failed to stop live session {run_id}: {e}")

        logger.info(f"Stopped {stopped}/{len(active)} live trading sessions")
        return stopped

    # -------------------------------------------------------------------------
    # Resume: reconciliation, warmup, and session recovery
    # -------------------------------------------------------------------------

    async def _reconcile_orders(
        self,
        engine: LiveTradingEngine,
        adapter: ExchangeAdapter,
        symbol: str,
    ) -> dict[str, Any]:
        """Reconcile local order state with exchange during resume.

        Queries exchange open orders and compares with saved local state.
        Processes fills that occurred during downtime.

        Tech debt (M-10): This method directly accesses engine private attrs
        (_live_orders, _exchange_order_map, _record_fill). Ideally the
        reconciliation logic should live inside LiveTradingEngine. Deferred
        to a future refactor when the engine undergoes larger changes.

        Args:
            engine: Live trading engine with restored live_orders.
            adapter: Connected exchange adapter.
            symbol: Trading symbol.

        Returns:
            Reconciliation report dict.
        """
        from squant.infra.exchange.types import OrderResponse

        report: dict[str, Any] = {
            "orders_reconciled": 0,
            "fills_processed": 0,
            "orders_cancelled": 0,
            "orders_unknown": 0,
            "discrepancies": [],
        }

        try:
            exchange_orders: list[OrderResponse] = await adapter.get_open_orders(symbol)
        except Exception as e:
            logger.error(f"Failed to query exchange open orders during reconciliation: {e}")
            report["error"] = f"Could not query exchange: {e}"
            return report

        # Build lookup by exchange order ID
        exchange_by_id: dict[str, OrderResponse] = {o.order_id: o for o in exchange_orders}

        orders_to_remove: list[str] = []

        for internal_id, live_order in list(engine._live_orders.items()):
            exchange_oid = live_order.exchange_order_id
            if not exchange_oid:
                live_order.status = OrderStatus.REJECTED
                orders_to_remove.append(internal_id)
                report["orders_cancelled"] += 1
                continue

            if exchange_oid in exchange_by_id:
                # Order still open on exchange — check for new fills
                exchange_order = exchange_by_id[exchange_oid]
                old_filled = live_order.filled_amount

                if exchange_order.filled > old_filled:
                    fill_delta = exchange_order.filled - old_filled
                    fee_delta = (exchange_order.fee or Decimal("0")) - live_order.fee
                    if fee_delta < 0:
                        fee_delta = Decimal("0")
                    # Update fee_currency from exchange before recording fill —
                    # it may be None if the session stopped before any fill arrived.
                    if exchange_order.fee_currency:
                        live_order.fee_currency = exchange_order.fee_currency
                    # Precision trade-off: using exchange avg_price as the fill price
                    # for the incremental fill. The REST API only provides the blended
                    # average price across all fills, not the price of each individual
                    # fill. The trades/fills endpoint would give exact per-fill prices
                    # but ExchangeAdapter does not expose it. This is acceptable for
                    # reconciliation purposes where approximate PnL tracking suffices.
                    logger.warning(
                        f"Reconcile fill for order {internal_id}: using approximate "
                        f"avg_price={exchange_order.avg_price} for delta={fill_delta} "
                        f"(exchange does not provide incremental fill price via REST)"
                    )
                    engine._record_fill(
                        live_order,
                        exchange_order.avg_price,
                        fill_delta,
                        fee_delta,
                        exchange_order.fee or Decimal("0"),
                        source="reconcile",
                        exchange_timestamp=exchange_order.updated_at,
                    )
                    report["fills_processed"] += 1

                live_order.status = exchange_order.status
                live_order.filled_amount = exchange_order.filled
                live_order.avg_fill_price = exchange_order.avg_price
                live_order.fee = exchange_order.fee or Decimal("0")
                live_order.updated_at = datetime.now(UTC)
                report["orders_reconciled"] += 1
            else:
                # Order not in open orders — query final state
                try:
                    final_state = await adapter.get_order(symbol, exchange_oid)
                    old_filled = live_order.filled_amount

                    if final_state.filled > old_filled:
                        fill_delta = final_state.filled - old_filled
                        fee_delta = (final_state.fee or Decimal("0")) - live_order.fee
                        if fee_delta < 0:
                            fee_delta = Decimal("0")
                        # Update fee_currency from exchange before recording fill —
                        # it may be None if the session stopped before any fill arrived.
                        if final_state.fee_currency:
                            live_order.fee_currency = final_state.fee_currency
                        # Precision trade-off: same as open-order path above.
                        # Using final_state.avg_price (blended average) as the fill
                        # price for the incremental amount. The actual per-fill price
                        # would require a get_order_trades() API that ExchangeAdapter
                        # does not currently provide.
                        logger.warning(
                            f"Reconcile fill for order {internal_id}: using approximate "
                            f"avg_price={final_state.avg_price} for delta={fill_delta} "
                            f"(exchange does not provide incremental fill price via REST)"
                        )
                        engine._record_fill(
                            live_order,
                            final_state.avg_price,
                            fill_delta,
                            fee_delta,
                            final_state.fee or Decimal("0"),
                            source="reconcile",
                            exchange_timestamp=final_state.updated_at,
                        )
                        report["fills_processed"] += 1

                    live_order.status = final_state.status
                    live_order.filled_amount = final_state.filled
                    live_order.avg_fill_price = final_state.avg_price
                    live_order.fee = final_state.fee or Decimal("0")
                    orders_to_remove.append(internal_id)
                    report["orders_reconciled"] += 1
                except Exception as e:
                    logger.warning(
                        f"Failed to query order {internal_id} (exchange_id={exchange_oid}): {e}"
                    )
                    live_order.status = OrderStatus.CANCELLED
                    orders_to_remove.append(internal_id)
                    report["orders_cancelled"] += 1

        # Clean up completed orders from tracking and update context count
        for internal_id in orders_to_remove:
            order = engine._live_orders.pop(internal_id, None)
            if order and order.exchange_order_id:
                engine._exchange_order_map.pop(order.exchange_order_id, None)
            # Increment completed count — SimulatedOrders aren't restored on resume,
            # so we bump the base count directly for the UI to reflect the update.
            engine._context._restored_completed_orders_count += 1

        # Check for untracked exchange orders
        tracked_exchange_ids = set(engine._exchange_order_map.keys())
        for order in exchange_orders:
            if order.order_id not in tracked_exchange_ids:
                logger.warning(
                    f"Untracked exchange order during reconciliation: "
                    f"id={order.order_id}, status={order.status.value}"
                )
                report["orders_unknown"] += 1
                report["discrepancies"].append(
                    {
                        "type": "untracked_exchange_order",
                        "exchange_order_id": order.order_id,
                        "status": order.status.value,
                    }
                )

        logger.info(
            f"Order reconciliation: reconciled={report['orders_reconciled']}, "
            f"fills={report['fills_processed']}, cancelled={report['orders_cancelled']}, "
            f"unknown={report['orders_unknown']}"
        )
        return report

    async def _reconcile_stale_db_orders(
        self,
        run_id: UUID,
        adapter: ExchangeAdapter,
        symbol: str,
    ) -> None:
        """Reconcile DB orders that have non-terminal status after crash/restart.

        When the engine crashes, order events may not have been flushed.
        This queries the DB for orders with status 'submitted' or 'partial',
        checks their actual status on the exchange, and updates the DB.
        """
        from squant.models.order import Trade
        from squant.services.order import OrderRepository

        order_repo = OrderRepository(self.session)
        stale_orders = await order_repo.list_by_run(run_id, offset=0, limit=100)
        non_terminal = [
            o
            for o in stale_orders
            if o.status in (OrderStatus.SUBMITTED, OrderStatus.PARTIAL) and o.exchange_oid
        ]

        if not non_terminal:
            return

        logger.info(f"Reconciling {len(non_terminal)} stale DB orders for run {run_id}")

        for order in non_terminal:
            try:
                exchange_state = await adapter.get_order(symbol, order.exchange_oid)
                updates: dict[str, Any] = {}

                if exchange_state.status != order.status:
                    updates["status"] = exchange_state.status
                if exchange_state.filled > (order.filled or Decimal("0")):
                    updates["filled"] = exchange_state.filled
                if exchange_state.avg_price and exchange_state.avg_price != order.avg_price:
                    updates["avg_price"] = exchange_state.avg_price
                # Note: fee is stored on Trade records, not on Order model

                if updates:
                    await order_repo.update(order.id, **updates)
                    logger.info(
                        f"Updated stale order {order.id} "
                        f"(exchange: {order.exchange_oid}): {updates}"
                    )

                    # Also try to fetch and persist individual fills
                    try:
                        trades = await adapter.get_order_trades(symbol, order.exchange_oid)
                        from squant.services.order import TradeRepository

                        trade_repo = TradeRepository(self.session)
                        for t in trades:
                            existing = await self.session.execute(
                                select(Trade).where(Trade.exchange_tid == t.trade_id)
                            )
                            if existing.scalar_one_or_none():
                                continue
                            await trade_repo.create(
                                order_id=str(order.id),
                                exchange_tid=t.trade_id,
                                price=t.price,
                                amount=t.amount,
                                fee=t.fee,
                                fee_currency=t.fee_currency,
                                taker_or_maker=t.taker_or_maker,
                                timestamp=t.timestamp,
                                fill_source="reconcile",
                            )
                        await self.session.commit()
                    except Exception as e:
                        logger.warning(f"Failed to fetch trades for stale order {order.id}: {e}")
            except Exception as e:
                logger.warning(f"Failed to reconcile stale order {order.id}: {e}")

    async def _reconcile_positions(
        self,
        engine: LiveTradingEngine,
        adapter: ExchangeAdapter,
        symbol: str,
    ) -> dict[str, Any]:
        """Reconcile local positions with exchange balance during resume.

        Local cash from restore_state() is the source of truth for the session,
        since the exchange balance reflects the entire account (which may include
        funds from other sessions or manual trades). Cash discrepancies are
        logged as warnings but NOT auto-adjusted — consistent with _sync_balance()
        in the engine (LIVE-012). Position discrepancies are also logged but not
        auto-adjusted (preserves avg_entry_price).

        Args:
            engine: Live trading engine with restored context.
            adapter: Connected exchange adapter.
            symbol: Trading symbol.

        Returns:
            Reconciliation report dict.
        """
        report: dict[str, Any] = {
            "cash_adjusted": False,
            "position_discrepancy": False,
            "discrepancies": [],
        }

        try:
            balance = await adapter.get_balance()
        except Exception as e:
            logger.error(f"Failed to query balance during reconciliation: {e}")
            report["error"] = f"Could not query balance: {e}"
            return report

        # Reconcile quote currency (cash)
        quote_currency = symbol.split("/")[1]
        quote_balance = balance.get_balance(quote_currency)
        if quote_balance:
            exchange_cash = quote_balance.total
            local_cash = engine.context._cash
            diff = abs(exchange_cash - local_cash)
            threshold = max(local_cash * Decimal("0.01"), Decimal("1"))

            if diff > threshold:
                logger.warning(
                    f"Cash discrepancy (warning only, not adjusting): "
                    f"local={local_cash}, exchange={exchange_cash}. "
                    f"Local cash from restored session state is source of truth."
                )
                report["discrepancies"].append(
                    {
                        "type": "cash_mismatch",
                        "local": str(local_cash),
                        "exchange": str(exchange_cash),
                    }
                )

        # Reconcile base currency (position)
        base_currency = symbol.split("/")[0]
        base_balance = balance.get_balance(base_currency)
        exchange_amount = base_balance.total if base_balance else Decimal("0")
        local_pos = engine.context.get_position(symbol)
        local_amount = local_pos.amount if local_pos else Decimal("0")

        if local_amount > 0 or exchange_amount > 0:
            diff = abs(exchange_amount - local_amount)
            threshold = max(abs(local_amount) * Decimal("0.001"), Decimal("0.00001"))

            if diff > threshold:
                logger.warning(
                    f"Position discrepancy for {symbol}: "
                    f"local={local_amount}, exchange={exchange_amount}"
                )
                report["discrepancies"].append(
                    {
                        "type": "position_mismatch",
                        "symbol": symbol,
                        "local": str(local_amount),
                        "exchange": str(exchange_amount),
                    }
                )
                report["position_discrepancy"] = True

        return report

    async def _warmup_strategy(
        self,
        engine: LiveTradingEngine,
        run: StrategyRun,
        warmup_bars: int,
    ) -> None:
        """Replay historical bars through strategy to rebuild internal state.

        During warmup, bars are fed to strategy.on_bar() but no orders
        are processed. Rebuilds strategy indicators and internal state.

        Args:
            engine: The live trading engine.
            run: The strategy run record.
            warmup_bars: Number of bars to replay.
        """
        from datetime import timedelta

        from squant.config import get_settings
        from squant.engine.resource_limits import resource_limiter
        from squant.services.data_loader import DataLoader

        settings = get_settings()

        tf_seconds = LiveTradingEngine._TIMEFRAME_SECONDS.get(run.timeframe, 60)
        end_time = datetime.now(UTC)
        start_time = end_time - timedelta(seconds=int(tf_seconds * warmup_bars * 1.2))

        loader = DataLoader(self.session)
        bar_count = 0

        logs_snapshot = list(engine.context._logs)

        async for bar in loader.load_bars(
            exchange=run.exchange,
            symbol=run.symbol,
            timeframe=run.timeframe,
            start=start_time,
            end=end_time,
        ):
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

        # Clear pending orders generated during warmup
        engine.context._pending_orders.clear()

        # Restore pre-warmup logs
        engine.context._logs.clear()
        for entry in logs_snapshot:
            engine.context._logs.append(entry)
        # Reset log counter to match restored logs — warmup incremented it
        # via ctx.buy()/sell() → ctx.log(), causing a false delta on first emit.
        engine.context._total_logs_added = len(logs_snapshot)

        logger.info(
            f"Warmup completed for live session {engine.run_id}: "
            f"{bar_count}/{warmup_bars} bars replayed"
        )

    async def resume(
        self,
        run_id: UUID,
        warmup_bars: int = 200,
    ) -> tuple[StrategyRun, dict[str, Any]]:
        """Resume a stopped/errored/interrupted live trading session.

        Reconnects to exchange, reconciles orders and positions,
        restores trading state, warms up strategy, and resumes trading.

        Args:
            run_id: Run ID of the session to resume.
            warmup_bars: Number of historical bars for strategy warmup.

        Returns:
            Tuple of (updated StrategyRun, reconciliation_report).

        Raises:
            SessionNotFoundError: If session not found.
            SessionNotResumableError: If session cannot be resumed.
            SessionAlreadyRunningError: If duplicate session running.
            CircuitBreakerActiveError: If circuit breaker active.
            MaxSessionsReachedError: If max sessions reached.
            ExchangeConnectionError: If exchange connection fails.
        """
        from squant.config import get_settings
        from squant.services.account import ExchangeAccountRepository
        from squant.services.strategy import StrategyRepository
        from squant.websocket.manager import get_stream_manager

        # 1. Circuit breaker check (LIVE-OP-001)
        await self._check_circuit_breaker()

        # 2. Load and validate run
        run = await self.run_repo.get(run_id)
        if not run:
            raise SessionNotFoundError(run_id)

        if run.status not in (RunStatus.ERROR, RunStatus.STOPPED, RunStatus.INTERRUPTED):
            raise SessionNotResumableError(
                run_id,
                f"status is {run.status.value}, must be error, stopped, or interrupted",
            )

        if not run.result or "cash" not in run.result:
            raise SessionNotResumableError(run_id, "no saved state; session cannot be resumed")

        if not run.account_id:
            raise SessionNotResumableError(
                run_id, "no exchange account ID; session predates resume support"
            )

        # 3. Check session limits
        settings = get_settings()
        session_manager = get_live_session_manager()
        if session_manager.session_count >= settings.live.max_sessions:
            raise MaxSessionsReachedError(settings.live.max_sessions)

        # 4. Check for duplicate running session
        has_running = await self.run_repo.has_running_session(
            strategy_id=run.strategy_id,
            symbol=run.symbol,
            mode=RunMode.LIVE,
        )
        if has_running:
            raise SessionAlreadyRunningError(
                message=f"A live session for strategy {run.strategy_id} "
                f"on {run.symbol} is already running"
            )

        # 5. Load and instantiate strategy
        strategy_repo = StrategyRepository(self.session)
        strategy_model = await strategy_repo.get(UUID(run.strategy_id))
        if not strategy_model:
            raise SessionNotResumableError(run_id, "strategy no longer exists")

        strategy_instance = self._instantiate_strategy(strategy_model.code)

        # 6. Reconnect to exchange
        account_repo = ExchangeAccountRepository(self.session)
        exchange_account = await account_repo.get(UUID(run.account_id))
        if not exchange_account:
            raise ExchangeAccountNotFoundError(run.account_id, "not found")
        if not exchange_account.is_active:
            raise ExchangeAccountNotFoundError(run.account_id, "account is not active")

        adapter = self._create_adapter(exchange_account)
        ws_credentials = self._build_ws_credentials(exchange_account)
        try:
            await asyncio.wait_for(adapter.connect(), timeout=30.0)
        except Exception as e:
            try:
                await adapter.close()
            except Exception:
                pass
            raise LiveExchangeConnectionError(f"Failed to reconnect to exchange: {e}") from e

        # 7. Restore risk config
        risk_config = None
        if run.result.get("risk_config"):
            risk_config = RiskConfig(**run.result["risk_config"])
        if risk_config is None:
            raise SessionNotResumableError(run_id, "no risk config in saved state")

        # 8. Create engine (on_order_persist wired after step 10 with seed map)
        engine = LiveTradingEngine(
            run_id=UUID(run.id),
            strategy=strategy_instance,
            symbol=run.symbol,
            timeframe=run.timeframe,
            adapter=adapter,
            risk_config=risk_config,
            initial_equity=run.initial_capital or Decimal("0"),
            params=run.params,
            on_snapshot=self._create_snapshot_callback(),
            on_result=self._create_result_callback(),
            on_event=self._create_event_callback(UUID(run.id)),
            credentials=ws_credentials,
            exchange_id=exchange_account.exchange.lower(),
        )

        # 9. Restore trading state
        engine.context.restore_state(run.result)
        engine._bar_count = run.result.get("bar_count", 0)
        if run.result.get("last_bar_time"):
            engine._last_bar_time = datetime.fromisoformat(run.result["last_bar_time"])

        if run.result.get("risk_state"):
            engine._risk_manager.restore_state(run.result["risk_state"])

        # 9b. Sync delta tracking counters to restored totals so that
        # already-persisted fills/trades/logs are not re-delivered as new
        # deltas to strategy callbacks or WebSocket events.
        ctx = engine.context
        engine._last_callback_fill_total = ctx._total_fills_added
        engine._last_callback_completed_total = ctx._total_completed_added
        engine._last_emitted_fill_total = ctx._total_fills_added
        engine._last_emitted_trade_total = ctx._total_trades_added
        engine._last_emitted_log_total = ctx._total_logs_added

        # 10. Restore live order tracking
        engine.restore_live_orders(run.result)

        # 10b. Wire order audit callback with seed map from DB (F-1 fix).
        # After restoring live orders, query existing DB audit records for
        # this run and build internal_id → DB UUID mapping so that fills
        # for orders placed before the crash can be linked correctly.
        seed_map: dict[str, str] = {}
        from squant.services.order import OrderRepository

        order_repo = OrderRepository(self.session)
        existing_orders = await order_repo.list_by_run(run.id, limit=1000)
        # Build reverse lookup: exchange_oid → DB order UUID
        oid_to_db: dict[str, str] = {
            o.exchange_oid: o.id for o in existing_orders if o.exchange_oid
        }
        # Match against restored live orders via exchange_order_id
        for internal_id, live_order in engine._live_orders.items():
            if live_order.exchange_order_id in oid_to_db:
                seed_map[internal_id] = oid_to_db[live_order.exchange_order_id]

        engine._on_order_persist = self._create_order_persist_callback(
            account_id=str(run.account_id),
            exchange=exchange_account.exchange,
            seed_map=seed_map,
        )
        if seed_map:
            logger.info(f"Resume: seeded order audit map with {len(seed_map)} orders")

        # 10c. Balance sufficiency check (B1+)
        # Reuses the adapter from step 6 to avoid extra connect() overhead
        session_equity = Decimal(str(run.result.get("equity", 0)))
        quote_currency = run.symbol.split("/")[1] if "/" in run.symbol else "USDT"
        await self._check_balance_sufficiency(
            adapter=adapter,
            account_id=str(run.account_id),
            required_equity=session_equity,
            quote_currency=quote_currency,
        )

        # 10d. Recovery reconciliation -- find orders on exchange missing from DB (B4)
        last_bar_time = None
        if run.result.get("last_bar_time"):
            last_bar_time = datetime.fromisoformat(run.result["last_bar_time"])
        recovery_since = self._compute_reconciliation_since(
            last_bar_time=last_bar_time,
            timeframe=run.timeframe,
            fallback=run.started_at,
        )
        # Upper bound: stopped_at (session was inactive after that), with small margin
        recovery_until = run.stopped_at if run.stopped_at else None

        recovery_report = await self._reconcile_missing_orders(
            adapter=adapter,
            run_id=run.id,
            account_id=str(run.account_id),
            exchange=exchange_account.exchange,
            symbol=run.symbol,
            db_orders=existing_orders,  # from step 10b
            since=recovery_since,
            until=recovery_until,
        )
        logger.info(f"Recovery reconciliation for {run_id}: {recovery_report}")

        # 11. Order reconciliation (live orders in engine state)
        reconciliation_report = await self._reconcile_orders(engine, adapter, run.symbol)
        logger.info(f"Order reconciliation for {run_id}: {reconciliation_report}")

        # 11a. Discard fill events buffered by step 11 — step 11b will write
        # complete per-fill trade records from get_order_trades() with full
        # exchange_tid/taker_or_maker fields. Keeping step 11's approximate
        # fill events would cause duplicate, incomplete trade records.
        engine._pending_order_events = [
            e for e in engine._pending_order_events if e.get("type") != "fill"
        ]

        # 11b. Reconcile stale DB orders (orders persisted but engine state lost on crash)
        await self._reconcile_stale_db_orders(run.id, adapter, run.symbol)

        # 12. Position/balance reconciliation
        position_report = await self._reconcile_positions(engine, adapter, run.symbol)
        reconciliation_report["position_reconciliation"] = position_report

        # 13. Register with session manager
        await session_manager.register(engine)

        subscribed = False
        try:
            # 14. Subscribe to WebSocket candles (public data via global StreamManager)
            stream_manager = get_stream_manager()
            await stream_manager.subscribe_candles(run.symbol, run.timeframe)
            subscribed = True
            # Note: private order WS is handled by engine's own CCXTStreamProvider (LIVE-CN-001)

            # 15. Start engine
            await engine.start()

            # 16. Warmup strategy
            if warmup_bars > 0:
                engine._warming_up = True
                try:
                    await self._warmup_strategy(engine, run, warmup_bars)
                finally:
                    engine._warming_up = False

            # Create per-session file logger after successful start+warmup
            engine._context._file_logger = create_trading_logger(str(run.id))

            # 17. Update DB status
            run = await self.run_repo.update(
                run.id,
                status=RunStatus.RUNNING,
                error_message=None,
                stopped_at=None,
            )
            await self.session.commit()

            logger.info(
                f"Resumed live session {run.id} "
                f"(warmup={warmup_bars}, "
                f"orders_reconciled={reconciliation_report.get('orders_reconciled', 0)})"
            )
            return run, reconciliation_report

        except Exception as e:
            # Cleanup on failure
            if engine.is_running:
                try:
                    await engine.stop(error=f"Resume failed: {e}")
                except Exception:
                    pass
            else:
                # engine.stop() was not called (engine never started or start failed),
                # so the adapter connection must be closed explicitly (fix: adapter leak)
                try:
                    await adapter.close()
                except Exception:
                    pass

            try:
                await session_manager.unregister(engine.run_id)
            except Exception:
                pass

            if subscribed:
                try:
                    await self._check_unsubscribe(run.symbol, run.timeframe)
                except Exception:
                    pass

            # Update DB status to ERROR so the session is not left in an inconsistent state
            try:
                await self.run_repo.update(
                    run.id,
                    status=RunStatus.ERROR,
                    error_message=f"Resume failed: {e}",
                )
                await self.session.commit()
            except Exception:
                pass

            raise

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
            SessionNotFoundError: If not found or if mode is not LIVE.
        """
        run = await self.run_repo.get(run_id)
        if not run:
            raise SessionNotFoundError(run_id)
        if run.mode != RunMode.LIVE:
            raise SessionNotFoundError(run_id)
        return run

    async def get_equity_curve(self, run_id: UUID, since: datetime | None = None) -> list:
        """Get equity curve for a live trading run.

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
        session_manager = get_live_session_manager()
        engine = session_manager.get(run_id)
        if engine:
            pending = engine.peek_pending_snapshots()
            if since is not None:
                pending = [s for s in pending if s.time > since]
            if pending:
                return list(persisted) + pending

        return persisted

    async def get_account_available_balance(
        self, account_id: str, quote_currency: str
    ) -> AccountBalanceResponse:
        """Calculate available balance for an exchange account.

        Fetches total account value from the exchange, then subtracts
        the equity allocated to running live trading sessions.

        Args:
            account_id: Exchange account ID.
            quote_currency: Quote currency for balance (e.g., "USDT").

        Returns:
            AccountBalanceResponse with total, allocated, and available balance.

        Raises:
            ExchangeAccountNotFoundError: If account not found or inactive.
            LiveExchangeConnectionError: If exchange connection fails.
        """
        from squant.schemas.live_trading import AccountBalanceResponse, RunningSessionEquity
        from squant.services.strategy import StrategyRepository

        adapter = await self._create_adapter_for_account(account_id)
        try:
            total_value, _ = await adapter.get_account_total_value(quote_currency)
        finally:
            await adapter.close()

        running_runs = await self.run_repo.list_running_by_account(account_id)

        session_manager = get_live_session_manager()
        strategy_repo = StrategyRepository(self.session)
        running_sessions: list[RunningSessionEquity] = []
        total_equity = Decimal("0")

        for run in running_runs:
            engine = session_manager.get(UUID(run.id))
            if engine:
                equity = engine.context.equity
            elif run.result and "equity" in run.result:
                equity = Decimal(str(run.result["equity"]))
            else:
                equity = run.initial_capital or Decimal("0")

            strategy = await strategy_repo.get(UUID(run.strategy_id))
            strategy_name = strategy.name if strategy else None

            running_sessions.append(
                RunningSessionEquity(
                    run_id=UUID(run.id),
                    strategy_name=strategy_name,
                    symbol=run.symbol,
                    equity=equity,
                )
            )
            total_equity += equity

        available = total_value - total_equity

        return AccountBalanceResponse(
            account_total_value=total_value,
            quote_currency=quote_currency,
            running_sessions=running_sessions,
            sessions_total_equity=total_equity,
            available=available,
        )

    async def _check_balance_sufficiency(
        self,
        adapter: ExchangeAdapter,
        account_id: str,
        required_equity: Decimal,
        quote_currency: str,
    ) -> None:
        """Check if account has sufficient balance for required equity.

        Reuses an existing adapter connection to avoid extra connect() overhead.
        Raises LiveTradingError if insufficient. Logs warning and continues
        if the balance check itself fails (non-blocking).
        """
        try:
            total_value, _ = await adapter.get_account_total_value(quote_currency)

            # Get running sessions' equity to compute available
            running_runs = await self.run_repo.list_running_by_account(account_id)
            session_manager = get_live_session_manager()
            total_running_equity = Decimal("0")
            for r in running_runs:
                engine = session_manager.get(UUID(r.id))
                if engine:
                    total_running_equity += engine.context.equity
                elif r.result and "equity" in r.result:
                    total_running_equity += Decimal(str(r.result["equity"]))
                else:
                    total_running_equity += r.initial_capital or Decimal("0")

            available = total_value - total_running_equity
            if required_equity > available:
                raise LiveTradingError(
                    f"账户可用余额不足。"
                    f"需要: {required_equity:.2f} {quote_currency}, "
                    f"可用: {available:.2f} {quote_currency}"
                )
        except LiveTradingError:
            raise  # Re-raise insufficient balance
        except Exception as e:
            logger.warning(f"Balance check failed for account {account_id}, proceeding: {e}")

    @staticmethod
    def _compute_reconciliation_since(
        last_bar_time: datetime | None,
        timeframe: str,
        fallback: datetime | None = None,
    ) -> datetime:
        """Compute the 'since' timestamp for recovery reconciliation.

        When resuming after a crash, we need to check the exchange for orders
        that may have been placed but never recorded. This method determines
        how far back to look.

        Args:
            last_bar_time: Timestamp of the last processed bar (from saved state).
            timeframe: Candle timeframe string (e.g. "1h", "5m").
            fallback: Fallback datetime if last_bar_time is not available
                      (typically run.started_at).

        Returns:
            A datetime to use as the 'since' parameter for exchange order queries.
        """
        if not last_bar_time:
            if fallback:
                return fallback
            return datetime.now(UTC) - timedelta(hours=24)

        tf_map = {
            "1m": timedelta(minutes=1),
            "3m": timedelta(minutes=3),
            "5m": timedelta(minutes=5),
            "15m": timedelta(minutes=15),
            "30m": timedelta(minutes=30),
            "1h": timedelta(hours=1),
            "2h": timedelta(hours=2),
            "4h": timedelta(hours=4),
            "6h": timedelta(hours=6),
            "12h": timedelta(hours=12),
            "1d": timedelta(days=1),
            "1w": timedelta(weeks=1),
            "1M": timedelta(days=30),
        }
        interval = tf_map.get(timeframe, timedelta(hours=1))
        return last_bar_time - interval

    async def _reconcile_missing_orders(
        self,
        adapter: ExchangeAdapter,
        run_id: str,
        account_id: str,
        exchange: str,
        symbol: str,
        db_orders: list,
        since: datetime,
        until: datetime | None = None,
    ) -> dict[str, Any]:
        """Find and recover orders on exchange that are missing from DB.

        During a crash, orders may have been placed on the exchange via
        adapter.place_order() but never persisted to our database. This
        method fetches all orders from the exchange since a given time,
        compares against existing DB orders by exchange_order_id, and
        creates Order + Trade records for any missing ones.

        Uses an independent DB session (get_session_context) to isolate
        IntegrityError rollbacks from the main resume transaction.

        Args:
            adapter: Exchange adapter for querying orders/trades.
            run_id: Strategy run ID.
            account_id: Exchange account ID.
            exchange: Exchange name (e.g. "okx").
            symbol: Trading symbol (e.g. "BTC/USDT").
            db_orders: Existing DB order records for this run.
            since: How far back to look for orders on the exchange.
            until: Upper time bound for order query (limits scope for old sessions).

        Returns:
            Dict with keys: missing_orders_found, missing_orders_recovered, errors.
        """
        from squant.infra.database import get_session_context
        from squant.services.order import OrderRepository, TradeRepository

        report: dict[str, Any] = {
            "missing_orders_found": 0,
            "missing_orders_recovered": 0,
            "errors": [],
        }

        try:
            exchange_orders = await adapter.get_orders(symbol, since=since, until=until)
        except Exception as e:
            logger.warning(f"Recovery reconciliation: failed to fetch orders: {e}")
            report["errors"].append(str(e))
            return report

        known_eoids = {o.exchange_oid for o in db_orders if o.exchange_oid}
        missing = [o for o in exchange_orders if o.order_id not in known_eoids]
        report["missing_orders_found"] = len(missing)

        if not missing:
            return report

        logger.info(f"Recovery reconciliation for {run_id}: found {len(missing)} missing orders")

        async with get_session_context() as db_session:
            order_repo = OrderRepository(db_session)
            trade_repo = TradeRepository(db_session)

            for ex_order in missing:
                try:
                    db_order = await order_repo.create(
                        run_id=run_id,
                        account_id=account_id,
                        exchange=exchange,
                        exchange_oid=ex_order.order_id,
                        symbol=ex_order.symbol,
                        side=ex_order.side,
                        type=ex_order.type,
                        amount=ex_order.amount,
                        price=ex_order.price,
                        status=ex_order.status,
                    )
                except IntegrityError:
                    # Order belongs to another session — skip
                    await db_session.rollback()
                    continue
                except Exception as e:
                    logger.warning(f"Failed to recover order {ex_order.order_id}: {e}")
                    report["errors"].append(str(e))
                    try:
                        await db_session.rollback()
                    except Exception:
                        pass
                    continue

                try:
                    fills = await adapter.get_order_trades(symbol, ex_order.order_id)
                    for fill in fills:
                        await trade_repo.create(
                            order_id=db_order.id,
                            price=fill.price,
                            amount=fill.amount,
                            fee=abs(fill.fee) if fill.fee else Decimal("0"),
                            fee_currency=fill.fee_currency,
                            timestamp=fill.timestamp or datetime.now(UTC),
                            fill_source="recovery",
                            exchange_tid=fill.trade_id,
                            taker_or_maker=fill.taker_or_maker,
                        )
                except Exception as e:
                    logger.warning(
                        f"Failed to fetch fills for recovered order {ex_order.order_id}: {e}"
                    )

                if ex_order.filled and ex_order.filled > 0:
                    try:
                        await order_repo.update(
                            db_order.id,
                            filled=ex_order.filled,
                            avg_price=ex_order.avg_price,
                            status=ex_order.status,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to update recovered order {ex_order.order_id}: {e}")

                report["missing_orders_recovered"] += 1

        return report

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

    async def persist_risk_triggers(self, run_id: UUID) -> int:
        """Persist pending risk triggers for a session (Issue 010).

        Called periodically or on demand to save risk trigger events.

        Args:
            run_id: Run ID.

        Returns:
            Number of triggers persisted.
        """
        from squant.services.risk import RiskTriggerService

        session_manager = get_live_session_manager()
        engine = session_manager.get(run_id)

        if not engine:
            return 0

        triggers = engine.get_pending_risk_triggers()
        if not triggers:
            return 0

        trigger_service = RiskTriggerService(self.session)
        for trigger_data in triggers:
            await trigger_service.record_trigger(
                rule_type=trigger_data["rule_type"],
                trigger_type=trigger_data["trigger_type"],
                details=trigger_data["details"],
                run_id=run_id,
            )

        return len(triggers)

    async def mark_session_interrupted(
        self,
        run_id: UUID,
        error_message: str,
        result: dict[str, Any] | None = None,
    ) -> None:
        """Mark a session as interrupted in the database.

        Used by background health checks when a session is cleaned up
        due to timeout or stale state.

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
            logger.info(f"Marked live session {run_id} as interrupted: {error_message}")

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
        """Attempt to recover orphaned live trading sessions.

        For each orphaned session with saved state, attempts resume().
        Sessions that fail are marked ERROR to prevent infinite retry.

        Live auto-recovery is opt-in (LIVE_AUTO_RECOVERY=true) because
        it involves real money and exchange connections.

        Returns:
            Tuple of (recovered_count, failed_count).
        """
        from squant.config import get_settings

        settings = get_settings()
        if not settings.live.auto_recovery:
            count = await self.mark_orphaned_sessions()
            return 0, count

        orphaned = await self.run_repo.get_orphaned_sessions()
        if not orphaned:
            return 0, 0

        recovered = 0
        failed = 0

        for run in orphaned:
            if run.result and run.result.get("cash") and run.account_id:
                try:
                    # Mark INTERRUPTED so resume() accepts it
                    await self.run_repo.update(
                        run.id,
                        status=RunStatus.INTERRUPTED,
                        error_message="Recovering from application restart...",
                    )
                    await self.session.commit()

                    await self.resume(
                        UUID(run.id),
                        warmup_bars=settings.live.warmup_bars,
                    )
                    recovered += 1
                    logger.info(f"Auto-recovered live session {run.id}")
                    continue
                except Exception as e:
                    logger.warning(f"Auto-recovery failed for live session {run.id}: {e}")
                    await self.run_repo.update(
                        run.id,
                        status=RunStatus.ERROR,
                        error_message=f"Auto-recovery failed: {e}",
                        stopped_at=datetime.now(UTC),
                    )
                    await self.session.commit()
                    failed += 1
                    continue

            # No saved state or no account_id — mark INTERRUPTED
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
