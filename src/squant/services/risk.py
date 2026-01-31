"""Risk rule service for risk management."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from squant.infra.repository import BaseRepository
from squant.models.risk import RiskRule, RiskTrigger
from squant.schemas.risk import CreateRiskRuleRequest, UpdateRiskRuleRequest


class RiskRuleNotFoundError(Exception):
    """Risk rule not found in database."""

    def __init__(self, rule_id: str | UUID):
        self.rule_id = str(rule_id)
        super().__init__(f"Risk rule not found: {rule_id}")


class RiskRuleRepository(BaseRepository[RiskRule]):
    """Repository for RiskRule model with specialized queries."""

    def __init__(self, session: AsyncSession):
        super().__init__(RiskRule, session)

    async def list_enabled(self) -> list[RiskRule]:
        """List all enabled risk rules."""
        stmt = (
            select(RiskRule)
            .where(RiskRule.enabled == True)  # noqa: E712
            .order_by(RiskRule.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_with_pagination(
        self,
        *,
        offset: int = 0,
        limit: int = 20,
        enabled: bool | None = None,
    ) -> list[RiskRule]:
        """List risk rules with pagination and optional enabled filter."""
        stmt = select(RiskRule)

        if enabled is not None:
            stmt = stmt.where(RiskRule.enabled == enabled)

        stmt = stmt.order_by(RiskRule.created_at.desc()).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_enabled(self, enabled: bool | None = None) -> int:
        """Count risk rules by enabled status."""
        if enabled is not None:
            return await self.count(enabled=enabled)
        return await self.count()


class RiskRuleService:
    """Service for risk rule business logic."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = RiskRuleRepository(session)

    async def create(self, request: CreateRiskRuleRequest) -> RiskRule:
        """Create a new risk rule.

        Args:
            request: Risk rule creation request.

        Returns:
            Created risk rule.
        """
        rule = await self.repository.create(
            name=request.name,
            type=request.type,
            params=request.params,
            enabled=request.enabled,
        )

        await self.session.commit()
        return rule

    async def update(self, rule_id: UUID, request: UpdateRiskRuleRequest) -> RiskRule:
        """Update an existing risk rule.

        Args:
            rule_id: Risk rule ID.
            request: Update request.

        Returns:
            Updated risk rule.

        Raises:
            RiskRuleNotFoundError: If rule not found.
        """
        rule = await self.repository.get(rule_id)
        if not rule:
            raise RiskRuleNotFoundError(rule_id)

        # Build update data
        update_data = {}
        if request.name is not None:
            update_data["name"] = request.name
        if request.type is not None:
            update_data["type"] = request.type
        if request.params is not None:
            update_data["params"] = request.params
        if request.enabled is not None:
            update_data["enabled"] = request.enabled

        if update_data:
            rule = await self.repository.update(rule_id, **update_data)

        await self.session.commit()
        return rule

    async def delete(self, rule_id: UUID) -> None:
        """Delete a risk rule.

        Args:
            rule_id: Risk rule ID.

        Raises:
            RiskRuleNotFoundError: If rule not found.
        """
        exists = await self.repository.exists(rule_id)
        if not exists:
            raise RiskRuleNotFoundError(rule_id)

        await self.repository.delete(rule_id)
        await self.session.commit()

    async def get(self, rule_id: UUID) -> RiskRule:
        """Get a risk rule by ID.

        Args:
            rule_id: Risk rule ID.

        Returns:
            Risk rule.

        Raises:
            RiskRuleNotFoundError: If not found.
        """
        rule = await self.repository.get(rule_id)
        if not rule:
            raise RiskRuleNotFoundError(rule_id)
        return rule

    async def list(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        enabled: bool | None = None,
    ) -> tuple[list[RiskRule], int]:
        """List risk rules with pagination.

        Args:
            page: Page number (1-indexed).
            page_size: Items per page.
            enabled: Optional enabled filter.

        Returns:
            Tuple of (rules, total_count).
        """
        offset = (page - 1) * page_size
        rules = await self.repository.list_with_pagination(
            offset=offset,
            limit=page_size,
            enabled=enabled,
        )
        total = await self.repository.count_by_enabled(enabled)
        return rules, total

    async def toggle(self, rule_id: UUID, enabled: bool) -> RiskRule:
        """Toggle a risk rule's enabled status.

        Args:
            rule_id: Risk rule ID.
            enabled: New enabled status.

        Returns:
            Updated risk rule.

        Raises:
            RiskRuleNotFoundError: If not found.
        """
        rule = await self.repository.get(rule_id)
        if not rule:
            raise RiskRuleNotFoundError(rule_id)

        rule = await self.repository.update(rule_id, enabled=enabled)
        await self.session.commit()
        return rule

    async def list_enabled(self) -> list[RiskRule]:
        """List all enabled risk rules.

        Returns:
            List of enabled risk rules.
        """
        return await self.repository.list_enabled()


# RSK-008: Risk Trigger Repository and Service


class RiskTriggerRepository(BaseRepository[RiskTrigger]):
    """Repository for RiskTrigger model with specialized queries."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(RiskTrigger, session)

    async def list_with_filters(
        self,
        *,
        offset: int = 0,
        limit: int = 20,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        rule_id: UUID | None = None,
        run_id: UUID | None = None,
    ) -> list[RiskTrigger]:
        """List risk triggers with filters.

        Args:
            offset: Number of records to skip.
            limit: Maximum records to return.
            start_time: Filter by minimum time.
            end_time: Filter by maximum time.
            rule_id: Filter by rule ID.
            run_id: Filter by run ID.

        Returns:
            List of risk triggers.
        """
        stmt = select(RiskTrigger)

        if start_time is not None:
            stmt = stmt.where(RiskTrigger.time >= start_time)
        if end_time is not None:
            stmt = stmt.where(RiskTrigger.time <= end_time)
        if rule_id is not None:
            stmt = stmt.where(RiskTrigger.rule_id == str(rule_id))
        if run_id is not None:
            stmt = stmt.where(RiskTrigger.run_id == str(run_id))

        stmt = stmt.order_by(RiskTrigger.time.desc()).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_with_filters(
        self,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        rule_id: UUID | None = None,
        run_id: UUID | None = None,
    ) -> int:
        """Count risk triggers with filters.

        Args:
            start_time: Filter by minimum time.
            end_time: Filter by maximum time.
            rule_id: Filter by rule ID.
            run_id: Filter by run ID.

        Returns:
            Count of matching triggers.
        """
        stmt = select(func.count()).select_from(RiskTrigger)

        if start_time is not None:
            stmt = stmt.where(RiskTrigger.time >= start_time)
        if end_time is not None:
            stmt = stmt.where(RiskTrigger.time <= end_time)
        if rule_id is not None:
            stmt = stmt.where(RiskTrigger.rule_id == str(rule_id))
        if run_id is not None:
            stmt = stmt.where(RiskTrigger.run_id == str(run_id))

        result = await self.session.execute(stmt)
        return result.scalar_one()


class RiskTriggerService:
    """Service for risk trigger queries (RSK-008).

    Provides read-only access to risk trigger records for audit
    and monitoring purposes.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = RiskTriggerRepository(session)

    async def list_triggers(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        rule_id: UUID | None = None,
        run_id: UUID | None = None,
    ) -> tuple[list[RiskTrigger], int]:
        """List risk triggers with pagination and filters.

        Args:
            page: Page number (1-indexed).
            page_size: Items per page.
            start_time: Filter by minimum time.
            end_time: Filter by maximum time.
            rule_id: Filter by rule ID.
            run_id: Filter by run ID.

        Returns:
            Tuple of (triggers, total_count).
        """
        offset = (page - 1) * page_size
        triggers = await self.repository.list_with_filters(
            offset=offset,
            limit=page_size,
            start_time=start_time,
            end_time=end_time,
            rule_id=rule_id,
            run_id=run_id,
        )
        total = await self.repository.count_with_filters(
            start_time=start_time,
            end_time=end_time,
            rule_id=rule_id,
            run_id=run_id,
        )
        return triggers, total

    async def get_trigger(self, trigger_id: UUID) -> RiskTrigger | None:
        """Get a risk trigger by ID.

        Args:
            trigger_id: Trigger ID.

        Returns:
            Risk trigger or None if not found.
        """
        return await self.repository.get(trigger_id)
