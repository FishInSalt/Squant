"""Strategy API endpoints."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from squant.api.utils import ApiResponse, PaginatedData
from squant.infra.database import get_session
from squant.models.enums import StrategyStatus
from squant.schemas.strategy import (
    CreateStrategyRequest,
    StrategyListItem,
    StrategyResponse,
    UpdateStrategyRequest,
    ValidateCodeRequest,
    ValidationResultResponse,
)
from squant.services.strategy import (
    StrategyInUseError,
    StrategyNameExistsError,
    StrategyNotFoundError,
    StrategyService,
    StrategyValidationError,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/validate", response_model=ApiResponse[ValidationResultResponse])
async def validate_strategy_code(
    request: ValidateCodeRequest,
) -> ApiResponse[ValidationResultResponse]:
    """Validate strategy code without saving.

    This endpoint checks:
    - Syntax validity
    - Forbidden imports
    - Required strategy structure (Strategy class with on_bar method)
    - RestrictedPython compatibility

    Args:
        request: Validation request.

    Returns:
        Validation result with any errors or warnings.
    """
    from squant.engine.sandbox import validate_strategy_code as validate

    result = validate(request.code)

    return ApiResponse(
        data=ValidationResultResponse(
            valid=result.valid,
            errors=result.errors,
            warnings=result.warnings,
        )
    )


@router.post("", response_model=ApiResponse[StrategyResponse])
async def create_strategy(
    request: CreateStrategyRequest,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[StrategyResponse]:
    """Create a new strategy.

    The strategy code will be validated before saving.

    Args:
        request: Strategy creation request.
        session: Database session.

    Returns:
        Created strategy.

    Raises:
        HTTPException: 400 if validation fails, 409 if name exists.
    """
    service = StrategyService(session)

    try:
        strategy = await service.create(request)
        return ApiResponse(data=StrategyResponse.model_validate(strategy))
    except StrategyNameExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except StrategyValidationError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "code": 400,
                "message": f"Strategy validation failed: {'; '.join(e.errors)}",
                "data": None,
            },
        )


@router.get("", response_model=ApiResponse[PaginatedData[StrategyListItem]])
async def list_strategies(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
    status: StrategyStatus | None = Query(None, description="Filter by status"),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[PaginatedData[StrategyListItem]]:
    """List strategies with pagination.

    Args:
        page: Page number (1-indexed).
        page_size: Items per page.
        status: Optional status filter.
        session: Database session.

    Returns:
        Paginated list of strategies.
    """
    service = StrategyService(session)

    strategies, total = await service.list(
        page=page,
        page_size=page_size,
        status=status,
    )

    items = [StrategyListItem.model_validate(s) for s in strategies]

    return ApiResponse(
        data=PaginatedData(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/{strategy_id}", response_model=ApiResponse[StrategyResponse])
async def get_strategy(
    strategy_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[StrategyResponse]:
    """Get a strategy by ID.

    Args:
        strategy_id: Strategy ID.
        session: Database session.

    Returns:
        Strategy details.

    Raises:
        HTTPException: 404 if not found.
    """
    service = StrategyService(session)

    try:
        strategy = await service.get(strategy_id)
        return ApiResponse(data=StrategyResponse.model_validate(strategy))
    except StrategyNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{strategy_id}", response_model=ApiResponse[StrategyResponse])
async def update_strategy(
    strategy_id: UUID,
    request: UpdateStrategyRequest,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[StrategyResponse]:
    """Update a strategy.

    Args:
        strategy_id: Strategy ID.
        request: Update request.
        session: Database session.

    Returns:
        Updated strategy.

    Raises:
        HTTPException: 400 if validation fails, 404 if not found, 409 if name exists.
    """
    service = StrategyService(session)

    try:
        strategy = await service.update(strategy_id, request)
        return ApiResponse(data=StrategyResponse.model_validate(strategy))
    except StrategyNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except StrategyNameExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except StrategyValidationError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "code": 400,
                "message": f"Strategy validation failed: {'; '.join(e.errors)}",
                "data": None,
            },
        )


@router.delete("/{strategy_id}", response_model=ApiResponse[None])
async def delete_strategy(
    strategy_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[None]:
    """Delete a strategy.

    Args:
        strategy_id: Strategy ID.
        session: Database session.

    Returns:
        Success response.

    Raises:
        HTTPException: 404 if not found, 409 if strategy is running.
    """
    service = StrategyService(session)

    try:
        await service.delete(strategy_id)
        return ApiResponse(data=None, message="Strategy deleted")
    except StrategyNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except StrategyInUseError as e:
        raise HTTPException(status_code=409, detail=str(e))
