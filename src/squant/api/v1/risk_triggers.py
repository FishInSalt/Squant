"""Risk triggers API endpoints (RSK-008).

Provides access to risk trigger audit records.
"""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from squant.api.utils import ApiResponse, PaginatedData
from squant.infra.database import get_session
from squant.schemas.circuit_breaker import RiskTriggerListItem
from squant.services.risk import RiskTriggerService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=ApiResponse[PaginatedData[RiskTriggerListItem]])
async def list_risk_triggers(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
    start_time: datetime | None = Query(None, description="Filter by start time"),
    end_time: datetime | None = Query(None, description="Filter by end time"),
    rule_id: UUID | None = Query(None, description="Filter by rule ID"),
    run_id: UUID | None = Query(None, description="Filter by run ID"),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[PaginatedData[RiskTriggerListItem]]:
    """List risk trigger records with pagination and filters (RSK-008).

    Returns historical records of when risk rules were triggered,
    useful for auditing and monitoring risk events.

    Args:
        page: Page number (1-indexed).
        page_size: Items per page (max 100).
        start_time: Filter triggers after this time.
        end_time: Filter triggers before this time.
        rule_id: Filter by specific risk rule.
        run_id: Filter by specific strategy run.
        session: Database session.

    Returns:
        Paginated list of risk trigger records.
    """
    service = RiskTriggerService(session)

    triggers, total = await service.list_triggers(
        page=page,
        page_size=page_size,
        start_time=start_time,
        end_time=end_time,
        rule_id=rule_id,
        run_id=run_id,
    )

    items = [
        RiskTriggerListItem(
            id=t.id,
            time=t.time,
            rule_id=t.rule_id,
            run_id=t.run_id,
            trigger_type=t.trigger_type,
            details=t.details,
            rule_name=t.rule.name if t.rule else None,
            rule_type=t.rule.type if t.rule else t.details.get("rule_type"),
            strategy_name=t.run.strategy.name if t.run and t.run.strategy else None,
            symbol=t.run.symbol if t.run else t.details.get("order_symbol"),
            message=t.details.get("reason"),
        )
        for t in triggers
    ]

    return ApiResponse(
        data=PaginatedData(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )
    )
