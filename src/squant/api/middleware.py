"""API middleware components.

This module provides middleware for the FastAPI application including:
- Rate limiting (simple in-memory implementation)

For production environments with multiple instances, consider:
- slowapi with Redis backend
- Nginx or API gateway level rate limiting
"""

import logging
import time
from collections import defaultdict
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiting middleware.

    Uses a sliding window algorithm to track request counts per client IP.
    This is suitable for single-instance deployments. For distributed
    deployments, use Redis-backed rate limiting (e.g., slowapi).

    Attributes:
        requests_per_minute: Maximum requests allowed per minute.
        burst_limit: Maximum burst requests allowed in short period.
    """

    def __init__(
        self,
        app: ASGIApp,
        requests_per_minute: int = 60,
        burst_limit: int = 10,
    ):
        """Initialize rate limiter.

        Args:
            app: The ASGI application.
            requests_per_minute: Max requests per minute per client.
            burst_limit: Max burst requests allowed.
        """
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.burst_limit = burst_limit
        self.window_size = 60  # 1 minute window

        # Client request tracking: {client_ip: [(timestamp, count), ...]}
        self._request_counts: dict[str, list[tuple[float, int]]] = defaultdict(list)
        self._cleanup_interval = 60  # Cleanup old entries every 60 seconds
        self._last_cleanup = time.time()

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request.

        Handles X-Forwarded-For header for reverse proxy setups.

        Args:
            request: The incoming request.

        Returns:
            Client IP address string.
        """
        # Check for X-Forwarded-For header (when behind reverse proxy)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP in the chain (original client)
            return forwarded_for.split(",")[0].strip()

        # Fall back to direct client IP
        if request.client:
            return request.client.host

        return "unknown"

    def _cleanup_old_entries(self) -> None:
        """Remove expired request tracking entries."""
        current_time = time.time()
        if current_time - self._last_cleanup < self._cleanup_interval:
            return

        cutoff = current_time - self.window_size
        for client_ip in list(self._request_counts.keys()):
            self._request_counts[client_ip] = [
                (ts, count)
                for ts, count in self._request_counts[client_ip]
                if ts > cutoff
            ]
            # Remove empty entries
            if not self._request_counts[client_ip]:
                del self._request_counts[client_ip]

        self._last_cleanup = current_time

    def _get_request_count(self, client_ip: str) -> int:
        """Get total request count in current window.

        Args:
            client_ip: Client IP address.

        Returns:
            Total requests in the current window.
        """
        current_time = time.time()
        cutoff = current_time - self.window_size

        # Filter and sum requests within window
        valid_entries = [
            (ts, count)
            for ts, count in self._request_counts[client_ip]
            if ts > cutoff
        ]
        self._request_counts[client_ip] = valid_entries

        return sum(count for _, count in valid_entries)

    def _record_request(self, client_ip: str) -> None:
        """Record a new request for the client.

        Args:
            client_ip: Client IP address.
        """
        current_time = time.time()
        self._request_counts[client_ip].append((current_time, 1))

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Response]
    ) -> Response:
        """Process request with rate limiting.

        Args:
            request: The incoming request.
            call_next: The next middleware/handler.

        Returns:
            Response from handler or 429 Too Many Requests.
        """
        # Skip rate limiting for health check endpoints
        if request.url.path in ["/health", "/api/v1/health"]:
            return await call_next(request)

        # Periodic cleanup
        self._cleanup_old_entries()

        client_ip = self._get_client_ip(request)
        current_count = self._get_request_count(client_ip)

        # Check rate limit
        if current_count >= self.requests_per_minute:
            logger.warning(
                f"Rate limit exceeded for {client_ip}: "
                f"{current_count}/{self.requests_per_minute} requests"
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Please slow down.",
                    "retry_after": self.window_size,
                },
                headers={
                    "Retry-After": str(self.window_size),
                    "X-RateLimit-Limit": str(self.requests_per_minute),
                    "X-RateLimit-Remaining": "0",
                },
            )

        # Record request and proceed
        self._record_request(client_ip)

        response = await call_next(request)

        # Add rate limit headers to response
        remaining = max(0, self.requests_per_minute - current_count - 1)
        response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(remaining)

        return response
