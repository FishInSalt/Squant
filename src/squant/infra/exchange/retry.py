"""Retry utilities for exchange API calls with exponential backoff."""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import ParamSpec, TypeVar

from squant.infra.exchange.exceptions import (
    ExchangeAuthenticationError,
    ExchangeConnectionError,
    ExchangeRateLimitError,
)

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


@dataclass
class RetryConfig:
    """Configuration for retry behavior.

    Attributes:
        max_retries: Maximum number of retry attempts (0 = no retries).
        base_delay: Initial delay in seconds before first retry.
        max_delay: Maximum delay between retries.
        exponential_base: Multiplier for exponential backoff (default 2.0).
        jitter: Random jitter factor (0.0 - 1.0) to avoid thundering herd.
    """

    max_retries: int = 3
    base_delay: float = 0.5
    max_delay: float = 30.0
    exponential_base: float = 2.0
    jitter: float = 0.25
    retryable_exceptions: tuple[type[Exception], ...] = field(
        default_factory=lambda: (
            ExchangeConnectionError,
            ExchangeRateLimitError,
        )
    )

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for a given attempt number.

        Args:
            attempt: Current attempt number (0-indexed).

        Returns:
            Delay in seconds with jitter applied.
        """
        # Exponential backoff: base_delay * (exponential_base ^ attempt)
        delay = self.base_delay * (self.exponential_base**attempt)

        # Cap at max_delay
        delay = min(delay, self.max_delay)

        # Add random jitter
        if self.jitter > 0:
            jitter_range = delay * self.jitter
            delay += random.uniform(-jitter_range, jitter_range)

        return max(0, delay)


# Default retry configuration
DEFAULT_RETRY_CONFIG = RetryConfig()


async def with_retry(
    func: Callable[P, Awaitable[T]],
    *args: P.args,
    config: RetryConfig | None = None,
    operation_name: str = "API call",
    **kwargs: P.kwargs,
) -> T:
    """Execute an async function with retry logic.

    Args:
        func: Async function to execute.
        *args: Positional arguments for the function.
        config: Retry configuration (uses default if None).
        operation_name: Name of operation for logging.
        **kwargs: Keyword arguments for the function.

    Returns:
        Result of the function.

    Raises:
        The last exception if all retries are exhausted.
        ExchangeAuthenticationError: Immediately (not retried).
    """
    config = config or DEFAULT_RETRY_CONFIG
    last_exception: Exception | None = None

    for attempt in range(config.max_retries + 1):
        try:
            return await func(*args, **kwargs)

        except ExchangeAuthenticationError:
            # Authentication errors should not be retried
            raise

        except config.retryable_exceptions as e:
            last_exception = e

            if attempt >= config.max_retries:
                logger.warning(
                    f"{operation_name} failed after {config.max_retries + 1} attempts: {e}"
                )
                raise

            delay = config.calculate_delay(attempt)

            # Special handling for rate limit errors
            if isinstance(e, ExchangeRateLimitError) and e.retry_after:
                delay = max(delay, e.retry_after)

            logger.info(
                f"{operation_name} failed (attempt {attempt + 1}/{config.max_retries + 1}): "
                f"{e}. Retrying in {delay:.2f}s..."
            )

            await asyncio.sleep(delay)

    # This should not be reached, but just in case
    if last_exception:
        raise last_exception
    raise RuntimeError("Retry logic error: no exception captured")


def retryable(
    config: RetryConfig | None = None,
    operation_name: str | None = None,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Decorator to add retry logic to an async function.

    Args:
        config: Retry configuration (uses default if None).
        operation_name: Name of operation for logging (uses function name if None).

    Returns:
        Decorated function with retry logic.

    Example:
        @retryable(config=RetryConfig(max_retries=5))
        async def fetch_data():
            ...
    """

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            name = operation_name or func.__name__
            return await with_retry(func, *args, config=config, operation_name=name, **kwargs)

        # Preserve function metadata
        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper

    return decorator
