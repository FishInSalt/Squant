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
    """Re-raise exchange exceptions for unified handling by main.py exception handlers.

    Known exchange exceptions are re-raised directly so main.py's registered
    exception handlers format them with the standard {"code", "message", "data"} shape.
    Unknown exceptions are raised as HTTPException with the same format.

    Args:
        e: The exception to handle.

    Raises:
        ExchangeError subclasses: Re-raised for main.py exception handlers.
        HTTPException: For unknown errors or exchange errors without a registered handler.
    """
    from squant.infra.exchange.exceptions import ExchangeError

    if isinstance(e, (ExchangeConnectionError, ExchangeAuthenticationError, ExchangeAPIError)):
        # These have registered handlers in main.py — re-raise directly
        raise e
    if isinstance(e, ExchangeRateLimitError):
        raise e
    if isinstance(e, ExchangeOrderNotFound):
        raise HTTPException(
            status_code=404,
            detail={"code": 404, "message": str(e), "data": None},
        )
    if isinstance(e, InvalidOrderError):
        raise HTTPException(
            status_code=400,
            detail={"code": 400, "message": str(e), "data": None},
        )
    if isinstance(e, ExchangeError):
        # Other ExchangeError subclasses without a registered handler
        raise HTTPException(
            status_code=502,
            detail={"code": 502, "message": str(e), "data": None},
        )
    # Log internal errors but don't expose details to client
    logger.exception("Unexpected error in API handler")
    raise HTTPException(
        status_code=500,
        detail={"code": 500, "message": "Internal server error", "data": None},
    )


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
