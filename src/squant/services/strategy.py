"""Strategy service for strategy management."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from squant.engine.sandbox import ValidationResult, validate_strategy_code
from squant.infra.repository import BaseRepository
from squant.models.enums import RunStatus, StrategyStatus
from squant.models.strategy import Strategy, StrategyRun
from squant.schemas.strategy import CreateStrategyRequest, UpdateStrategyRequest


class StrategyNotFoundError(Exception):
    """Strategy not found in database."""

    def __init__(self, strategy_id: str | UUID):
        self.strategy_id = str(strategy_id)
        super().__init__(f"Strategy not found: {strategy_id}")


class StrategyNameExistsError(Exception):
    """Strategy name already exists."""

    def __init__(self, name: str):
        self.name = name
        super().__init__(f"Strategy name already exists: {name}")


class StrategyValidationError(Exception):
    """Strategy code validation failed."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"Strategy validation failed: {'; '.join(errors)}")


class StrategyInUseError(Exception):
    """Strategy is currently in use and cannot be deleted."""

    def __init__(self, strategy_id: str | UUID, running_count: int = 1):
        self.strategy_id = str(strategy_id)
        self.running_count = running_count
        super().__init__(
            f"Strategy {strategy_id} is currently running "
            f"({running_count} active session(s)). Stop all sessions before deleting."
        )


class StrategyRepository(BaseRepository[Strategy]):
    """Repository for Strategy model with specialized queries."""

    def __init__(self, session: AsyncSession):
        super().__init__(Strategy, session)

    async def get_by_name(self, name: str) -> Strategy | None:
        """Get strategy by name."""
        stmt = select(Strategy).where(Strategy.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_active(self) -> list[Strategy]:
        """List all active strategies."""
        stmt = (
            select(Strategy)
            .where(Strategy.status == StrategyStatus.ACTIVE)
            .order_by(Strategy.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_with_pagination(
        self,
        *,
        offset: int = 0,
        limit: int = 20,
        status: StrategyStatus | None = None,
    ) -> list[Strategy]:
        """List strategies with pagination and optional status filter."""
        stmt = select(Strategy)

        if status is not None:
            stmt = stmt.where(Strategy.status == status)

        stmt = stmt.order_by(Strategy.created_at.desc()).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_status(self, status: StrategyStatus | None = None) -> int:
        """Count strategies by status."""
        if status is not None:
            return await self.count(status=status)
        return await self.count()


class StrategyService:
    """Service for strategy business logic."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = StrategyRepository(session)

    async def create(self, request: CreateStrategyRequest) -> Strategy:
        """Create a new strategy.

        Args:
            request: Strategy creation request.

        Returns:
            Created strategy.

        Raises:
            StrategyNameExistsError: If name already exists.
            StrategyValidationError: If code validation fails.
        """
        # Check name uniqueness
        existing = await self.repository.get_by_name(request.name)
        if existing:
            raise StrategyNameExistsError(request.name)

        # Validate code
        validation = validate_strategy_code(request.code)
        if not validation.valid:
            raise StrategyValidationError(validation.errors)

        # Create strategy (handle TOCTOU race on name uniqueness)
        try:
            strategy = await self.repository.create(
                name=request.name,
                code=request.code,
                description=request.description,
                params_schema=request.params_schema or {},
                default_params=request.default_params or {},
            )

            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise StrategyNameExistsError(request.name)
        return strategy

    async def update(self, strategy_id: UUID, request: UpdateStrategyRequest) -> Strategy:
        """Update an existing strategy.

        Args:
            strategy_id: Strategy ID.
            request: Update request.

        Returns:
            Updated strategy.

        Raises:
            StrategyNotFoundError: If strategy not found.
            StrategyNameExistsError: If new name already exists.
            StrategyValidationError: If code validation fails.
        """
        strategy = await self.repository.get(strategy_id)
        if not strategy:
            raise StrategyNotFoundError(strategy_id)

        # Check name uniqueness if name is being changed
        if request.name and request.name != strategy.name:
            existing = await self.repository.get_by_name(request.name)
            if existing:
                raise StrategyNameExistsError(request.name)

        # Validate code if being updated
        if request.code:
            validation = validate_strategy_code(request.code)
            if not validation.valid:
                raise StrategyValidationError(validation.errors)

        # Build update data
        update_data = {}
        if request.name is not None:
            update_data["name"] = request.name
        if request.code is not None:
            update_data["code"] = request.code
            # Increment version when code changes
            version_parts = strategy.version.split(".")
            version_parts[-1] = str(int(version_parts[-1]) + 1)
            update_data["version"] = ".".join(version_parts)
        if request.description is not None:
            update_data["description"] = request.description
        if request.params_schema is not None:
            update_data["params_schema"] = request.params_schema
        if request.default_params is not None:
            update_data["default_params"] = request.default_params
        if request.status is not None:
            update_data["status"] = request.status

        if update_data:
            updated = await self.repository.update(strategy_id, **update_data)
            if not updated:
                raise StrategyNotFoundError(strategy_id)
            strategy = updated

        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            if request.name and request.name != strategy.name:
                raise StrategyNameExistsError(request.name)
            raise
        return strategy

    async def delete(self, strategy_id: UUID) -> None:
        """Soft-delete a strategy by archiving it.

        Preserves associated strategy runs (backtest results, trading history)
        for historical analysis. The strategy is marked as archived rather than
        physically removed from the database.

        Args:
            strategy_id: Strategy ID.

        Raises:
            StrategyNotFoundError: If strategy not found.
            StrategyInUseError: If strategy has running sessions.
        """
        strategy = await self.repository.get(strategy_id)
        if not strategy:
            raise StrategyNotFoundError(strategy_id)

        # Guard against re-archiving an already archived strategy
        if strategy.status == StrategyStatus.ARCHIVED:
            return

        # Check for running sessions (STR-024: cannot delete running strategy)
        running_stmt = (
            select(StrategyRun)
            .where(StrategyRun.strategy_id == str(strategy_id))
            .where(StrategyRun.status == RunStatus.RUNNING)
        )
        result = await self.session.execute(running_stmt)
        running_sessions = list(result.scalars().all())

        if running_sessions:
            raise StrategyInUseError(strategy_id, len(running_sessions))

        # Soft delete: archive and rename to free up the name for reuse.
        # Suffix is "_archived_<id[:8]>" (18 chars). Truncate name to fit 128-char DB limit.
        suffix = f"_archived_{str(strategy_id)[:8]}"
        max_name_len = 128 - len(suffix)
        truncated_name = strategy.name[:max_name_len]
        archived_name = f"{truncated_name}{suffix}"
        await self.repository.update(
            strategy_id,
            name=archived_name,
            status=StrategyStatus.ARCHIVED,
        )
        await self.session.commit()

    async def get(self, strategy_id: UUID) -> Strategy:
        """Get a strategy by ID.

        Args:
            strategy_id: Strategy ID.

        Returns:
            Strategy.

        Raises:
            StrategyNotFoundError: If not found.
        """
        strategy = await self.repository.get(strategy_id)
        if not strategy:
            raise StrategyNotFoundError(strategy_id)
        return strategy

    async def list(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        status: StrategyStatus | None = None,
    ) -> tuple[list[Strategy], int]:
        """List strategies with pagination.

        Args:
            page: Page number (1-indexed).
            page_size: Items per page.
            status: Optional status filter.

        Returns:
            Tuple of (strategies, total_count).
        """
        offset = (page - 1) * page_size
        strategies = await self.repository.list_with_pagination(
            offset=offset,
            limit=page_size,
            status=status,
        )
        total = await self.repository.count_by_status(status)
        return strategies, total

    def validate_code(self, code: str) -> ValidationResult:
        """Validate strategy code without saving.

        Args:
            code: Strategy code to validate.

        Returns:
            ValidationResult.
        """
        return validate_strategy_code(code)
