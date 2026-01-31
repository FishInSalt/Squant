"""Shared API utilities."""

import logging
from typing import TypeVar

from fastapi import HTTPException
from pydantic import BaseModel

from squant.infra.exchange.exceptions import (
    ExchangeAPIError,
    ExchangeAuthenticationError,
    ExchangeConnectionError,
    ExchangeRateLimitError,
    InvalidOrderError,
)
from squant.infra.exchange.exceptions import (
    OrderNotFoundError as ExchangeOrderNotFound,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ApiResponse[T](BaseModel):
    """Standard API response wrapper.

    All API responses follow this format per dev-docs/technical/api/01-conventions.md.
    """

    code: int = 0
    message: str = "success"
    data: T


class PaginatedData[T](BaseModel):
    """Paginated data container.

    Per dev-docs/technical/api/01-conventions.md:
    - page: starts from 1
    - page_size: default 20, max 100
    """

    items: list[T]
    total: int
    page: int
    page_size: int


def handle_exchange_error(e: Exception) -> None:
    """Convert exchange exceptions to HTTP exceptions.

    This function always raises an HTTPException.

    Args:
        e: The exception to handle.

    Raises:
        HTTPException: Always raised with appropriate status code.
    """
    if isinstance(e, ExchangeAuthenticationError):
        raise HTTPException(status_code=401, detail=str(e))
    if isinstance(e, ExchangeRateLimitError):
        raise HTTPException(
            status_code=429,
            detail=str(e),
            headers={"Retry-After": str(int(e.retry_after or 1))},
        )
    if isinstance(e, ExchangeOrderNotFound):
        raise HTTPException(status_code=404, detail=str(e))
    if isinstance(e, InvalidOrderError):
        raise HTTPException(status_code=400, detail=str(e))
    if isinstance(e, ExchangeConnectionError):
        raise HTTPException(status_code=503, detail=str(e))
    if isinstance(e, ExchangeAPIError):
        raise HTTPException(status_code=502, detail=str(e))
    # Log internal errors but don't expose details to client
    logger.exception("Unexpected error in API handler")
    raise HTTPException(status_code=500, detail="Internal server error")


def paginate_params(page: int, page_size: int) -> tuple[int, int]:
    """Convert page/page_size to offset/limit.

    Args:
        page: Page number (1-indexed).
        page_size: Items per page.

    Returns:
        Tuple of (offset, limit).
    """
    offset = (page - 1) * page_size
    return offset, page_size
