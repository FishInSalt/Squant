"""Risk rule API endpoints."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from squant.api.utils import ApiResponse, PaginatedData
from squant.infra.database import get_session
from squant.schemas.risk import (
    CreateRiskRuleRequest,
    RiskRuleListItem,
    RiskRuleResponse,
    ToggleRiskRuleRequest,
    UpdateRiskRuleRequest,
)
from squant.services.risk import RiskRuleNotFoundError, RiskRuleService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("", response_model=ApiResponse[RiskRuleResponse])
async def create_risk_rule(
    request: CreateRiskRuleRequest,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[RiskRuleResponse]:
    """Create a new risk rule.

    Args:
        request: Risk rule creation request.
        session: Database session.

    Returns:
        Created risk rule.
    """
    service = RiskRuleService(session)

    rule = await service.create(request)
    return ApiResponse(data=RiskRuleResponse.model_validate(rule))


@router.get("", response_model=ApiResponse[PaginatedData[RiskRuleListItem]])
async def list_risk_rules(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
    enabled: bool | None = Query(None, description="Filter by enabled status"),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[PaginatedData[RiskRuleListItem]]:
    """List risk rules with pagination.

    Args:
        page: Page number (1-indexed).
        page_size: Items per page.
        enabled: Optional enabled filter.
        session: Database session.

    Returns:
        Paginated list of risk rules.
    """
    service = RiskRuleService(session)

    rules, total = await service.list(
        page=page,
        page_size=page_size,
        enabled=enabled,
    )

    items = [RiskRuleListItem.model_validate(r) for r in rules]

    return ApiResponse(
        data=PaginatedData(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/{rule_id}", response_model=ApiResponse[RiskRuleResponse])
async def get_risk_rule(
    rule_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[RiskRuleResponse]:
    """Get a risk rule by ID.

    Args:
        rule_id: Risk rule ID.
        session: Database session.

    Returns:
        Risk rule details.

    Raises:
        HTTPException: 404 if not found.
    """
    service = RiskRuleService(session)

    try:
        rule = await service.get(rule_id)
        return ApiResponse(data=RiskRuleResponse.model_validate(rule))
    except RiskRuleNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{rule_id}", response_model=ApiResponse[RiskRuleResponse])
async def update_risk_rule(
    rule_id: UUID,
    request: UpdateRiskRuleRequest,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[RiskRuleResponse]:
    """Update a risk rule.

    Args:
        rule_id: Risk rule ID.
        request: Update request.
        session: Database session.

    Returns:
        Updated risk rule.

    Raises:
        HTTPException: 404 if not found.
    """
    service = RiskRuleService(session)

    try:
        rule = await service.update(rule_id, request)
        return ApiResponse(data=RiskRuleResponse.model_validate(rule))
    except RiskRuleNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{rule_id}", response_model=ApiResponse[None])
async def delete_risk_rule(
    rule_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[None]:
    """Delete a risk rule.

    Args:
        rule_id: Risk rule ID.
        session: Database session.

    Returns:
        Success response.

    Raises:
        HTTPException: 404 if not found.
    """
    service = RiskRuleService(session)

    try:
        await service.delete(rule_id)
        return ApiResponse(data=None, message="Risk rule deleted")
    except RiskRuleNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{rule_id}/toggle", response_model=ApiResponse[RiskRuleResponse])
async def toggle_risk_rule(
    rule_id: UUID,
    request: ToggleRiskRuleRequest,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[RiskRuleResponse]:
    """Toggle a risk rule's enabled status.

    Args:
        rule_id: Risk rule ID.
        request: Toggle request.
        session: Database session.

    Returns:
        Updated risk rule.

    Raises:
        HTTPException: 404 if not found.
    """
    service = RiskRuleService(session)

    try:
        rule = await service.toggle(rule_id, request.enabled)
        return ApiResponse(data=RiskRuleResponse.model_validate(rule))
    except RiskRuleNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
