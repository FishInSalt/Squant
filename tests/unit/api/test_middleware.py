"""Unit tests for API rate limiting middleware."""

import time
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from squant.api.middleware import RateLimitMiddleware


@pytest.fixture
def app_with_middleware():
    """Create a FastAPI app with rate limiting middleware."""
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, requests_per_minute=5, burst_limit=3)

    @app.get("/test")
    async def test_endpoint():
        return {"status": "ok"}

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    @app.get("/api/v1/health")
    async def api_health():
        return {"status": "healthy"}

    return app


class TestRateLimitMiddleware:
    """Tests for RateLimitMiddleware."""

    @pytest.mark.asyncio
    async def test_allows_requests_under_limit(self, app_with_middleware):
        """Test requests under rate limit are allowed."""
        async with AsyncClient(
            transport=ASGITransport(app=app_with_middleware),
            base_url="http://test",
        ) as client:
            response = await client.get("/test")

            assert response.status_code == 200
            assert "X-RateLimit-Limit" in response.headers
            assert "X-RateLimit-Remaining" in response.headers

    @pytest.mark.asyncio
    async def test_rate_limit_headers(self, app_with_middleware):
        """Test rate limit headers are set correctly."""
        async with AsyncClient(
            transport=ASGITransport(app=app_with_middleware),
            base_url="http://test",
        ) as client:
            response = await client.get("/test")

            assert response.headers["X-RateLimit-Limit"] == "5"
            # First request: 5 - 0 - 1 = 4 remaining
            assert response.headers["X-RateLimit-Remaining"] == "4"

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded(self, app_with_middleware):
        """Test 429 response when rate limit is exceeded."""
        async with AsyncClient(
            transport=ASGITransport(app=app_with_middleware),
            base_url="http://test",
        ) as client:
            # Make requests up to the limit
            for _ in range(5):
                response = await client.get("/test")
                assert response.status_code == 200

            # Next request should be rate limited
            response = await client.get("/test")

            assert response.status_code == 429
            assert "Retry-After" in response.headers
            body = response.json()
            assert "Rate limit exceeded" in body["detail"]

    @pytest.mark.asyncio
    async def test_remaining_decreases(self, app_with_middleware):
        """Test remaining count decreases with each request."""
        async with AsyncClient(
            transport=ASGITransport(app=app_with_middleware),
            base_url="http://test",
        ) as client:
            response1 = await client.get("/test")
            response2 = await client.get("/test")

            remaining1 = int(response1.headers["X-RateLimit-Remaining"])
            remaining2 = int(response2.headers["X-RateLimit-Remaining"])

            assert remaining1 > remaining2

    @pytest.mark.asyncio
    async def test_health_endpoint_bypasses_rate_limit(self, app_with_middleware):
        """Test /health endpoint is not rate limited."""
        async with AsyncClient(
            transport=ASGITransport(app=app_with_middleware),
            base_url="http://test",
        ) as client:
            # Exhaust rate limit
            for _ in range(5):
                await client.get("/test")

            # Health should still work
            response = await client.get("/health")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_api_health_endpoint_bypasses_rate_limit(self, app_with_middleware):
        """Test /api/v1/health endpoint is not rate limited."""
        async with AsyncClient(
            transport=ASGITransport(app=app_with_middleware),
            base_url="http://test",
        ) as client:
            # Exhaust rate limit
            for _ in range(5):
                await client.get("/test")

            # API health should still work
            response = await client.get("/api/v1/health")
            assert response.status_code == 200


class TestGetClientIP:
    """Tests for client IP extraction."""

    def test_direct_client_ip(self):
        """Test extracting IP from direct connection."""
        middleware = RateLimitMiddleware(MagicMock())

        request = MagicMock(spec=Request)
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "192.168.1.100"

        ip = middleware._get_client_ip(request)

        assert ip == "192.168.1.100"

    def test_x_forwarded_for_trusted_proxy(self):
        """Test extracting IP from X-Forwarded-For when proxy is trusted."""
        middleware = RateLimitMiddleware(MagicMock(), trusted_proxies={"127.0.0.1"})

        request = MagicMock(spec=Request)
        request.headers = {"X-Forwarded-For": "10.0.0.1"}
        request.client = MagicMock()
        request.client.host = "127.0.0.1"

        ip = middleware._get_client_ip(request)

        assert ip == "10.0.0.1"

    def test_x_forwarded_for_multiple_ips(self):
        """Test extracting first IP from X-Forwarded-For chain."""
        middleware = RateLimitMiddleware(MagicMock(), trusted_proxies={"172.17.0.1"})

        request = MagicMock(spec=Request)
        request.headers = {"X-Forwarded-For": "10.0.0.1, 172.16.0.1, 192.168.1.1"}
        request.client = MagicMock()
        request.client.host = "172.17.0.1"

        ip = middleware._get_client_ip(request)

        assert ip == "10.0.0.1"

    def test_x_forwarded_for_with_spaces(self):
        """Test X-Forwarded-For header value is stripped."""
        middleware = RateLimitMiddleware(MagicMock(), trusted_proxies={"172.17.0.1"})

        request = MagicMock(spec=Request)
        request.headers = {"X-Forwarded-For": "  10.0.0.1  , 172.16.0.1"}
        request.client = MagicMock()
        request.client.host = "172.17.0.1"

        ip = middleware._get_client_ip(request)

        assert ip == "10.0.0.1"

    def test_x_forwarded_for_ignored_without_trusted_proxy(self):
        """Test X-Forwarded-For is ignored when proxy is not trusted."""
        middleware = RateLimitMiddleware(MagicMock())

        request = MagicMock(spec=Request)
        request.headers = {"X-Forwarded-For": "10.0.0.1"}
        request.client = MagicMock()
        request.client.host = "192.168.1.100"

        ip = middleware._get_client_ip(request)

        assert ip == "192.168.1.100"

    def test_no_client_info(self):
        """Test fallback to 'unknown' when no client info."""
        middleware = RateLimitMiddleware(MagicMock())

        request = MagicMock(spec=Request)
        request.headers = {}
        request.client = None

        ip = middleware._get_client_ip(request)

        assert ip == "unknown"


class TestCleanupOldEntries:
    """Tests for old entry cleanup."""

    def test_cleanup_removes_expired_entries(self):
        """Test cleanup removes entries older than window."""
        middleware = RateLimitMiddleware(MagicMock())

        # Add expired entries
        old_time = time.time() - 120  # 2 minutes ago
        middleware._request_counts["192.168.1.1"] = [(old_time, 1), (old_time + 1, 1)]

        # Force cleanup by setting last cleanup to far past
        middleware._last_cleanup = time.time() - 120

        middleware._cleanup_old_entries()

        # Expired entries should be removed
        assert "192.168.1.1" not in middleware._request_counts

    def test_cleanup_keeps_valid_entries(self):
        """Test cleanup keeps entries within window."""
        middleware = RateLimitMiddleware(MagicMock())

        # Add recent entry
        current_time = time.time()
        middleware._request_counts["192.168.1.1"] = [(current_time, 1)]

        # Force cleanup
        middleware._last_cleanup = time.time() - 120

        middleware._cleanup_old_entries()

        # Recent entry should be kept
        assert "192.168.1.1" in middleware._request_counts
        assert len(middleware._request_counts["192.168.1.1"]) == 1

    def test_cleanup_skips_if_too_recent(self):
        """Test cleanup skips if last cleanup was recent."""
        middleware = RateLimitMiddleware(MagicMock())

        old_time = time.time() - 120
        middleware._request_counts["192.168.1.1"] = [(old_time, 1)]
        middleware._last_cleanup = time.time()  # Just cleaned up

        middleware._cleanup_old_entries()

        # Should NOT have cleaned up (too recent)
        assert "192.168.1.1" in middleware._request_counts


class TestRequestCounting:
    """Tests for request counting logic."""

    def test_get_request_count_empty(self):
        """Test count is 0 for new client."""
        middleware = RateLimitMiddleware(MagicMock())

        count = middleware._get_request_count("192.168.1.1")

        assert count == 0

    def test_get_request_count_with_entries(self):
        """Test count sums entries in window."""
        middleware = RateLimitMiddleware(MagicMock())

        current = time.time()
        middleware._request_counts["192.168.1.1"] = [
            (current - 10, 1),
            (current - 5, 1),
            (current, 1),
        ]

        count = middleware._get_request_count("192.168.1.1")

        assert count == 3

    def test_get_request_count_excludes_expired(self):
        """Test count excludes entries outside window."""
        middleware = RateLimitMiddleware(MagicMock())

        current = time.time()
        middleware._request_counts["192.168.1.1"] = [
            (current - 120, 1),  # Expired (> 60s window)
            (current - 10, 1),  # Valid
        ]

        count = middleware._get_request_count("192.168.1.1")

        assert count == 1

    def test_record_request(self):
        """Test recording a request adds entry."""
        middleware = RateLimitMiddleware(MagicMock())

        middleware._record_request("192.168.1.1")

        assert len(middleware._request_counts["192.168.1.1"]) == 1
        ts, count = middleware._request_counts["192.168.1.1"][0]
        assert count == 1
        assert ts <= time.time()
