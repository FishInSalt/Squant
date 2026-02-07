"""Unit tests for squant.main — exception handlers and app configuration.

Tests cover:
- Exchange exception handlers (connection, auth, rate limit, API errors)
- Global HTTPException handler with uniform response shape
- create_app() configuration (docs URLs, CORS, router prefix)
- _configure_logging() is called during app creation
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from squant.infra.exchange.exceptions import (
    ExchangeAPIError,
    ExchangeAuthenticationError,
    ExchangeConnectionError,
    ExchangeRateLimitError,
)
from squant.main import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def test_app():
    """Create a fresh FastAPI app with test routes that raise specific exceptions.

    Uses create_app() to get the real app with all exception handlers registered,
    then injects test-only routes. The lifespan is NOT invoked during these tests
    because we never send ASGI startup events through the transport.
    """
    app = create_app()

    # -- Test routes that raise exchange exceptions --

    async def raise_connection_error():
        raise ExchangeConnectionError(message="Connection refused", exchange="okx")

    async def raise_auth_error():
        raise ExchangeAuthenticationError(message="Invalid API key", exchange="binance")

    async def raise_rate_limit_error():
        raise ExchangeRateLimitError(
            message="Too many requests", exchange="okx", retry_after=30.0
        )

    async def raise_rate_limit_error_no_retry():
        raise ExchangeRateLimitError(
            message="Rate limited", exchange="bybit", retry_after=None
        )

    async def raise_api_error():
        raise ExchangeAPIError(
            message="Order rejected", exchange="okx", code="51000"
        )

    # -- Test routes that raise HTTPException variants --

    from fastapi import HTTPException

    async def raise_http_404():
        raise HTTPException(status_code=404, detail="Resource not found")

    async def raise_http_403():
        raise HTTPException(status_code=403, detail="Forbidden")

    async def raise_http_dict_detail():
        raise HTTPException(
            status_code=500,
            detail={"message": "Internal server error", "extra": "info"},
        )

    async def raise_http_non_string_detail():
        raise HTTPException(status_code=422, detail=["validation", "errors"])

    async def successful_route():
        return {"status": "ok"}

    app.add_api_route("/test/connection-error", raise_connection_error)
    app.add_api_route("/test/auth-error", raise_auth_error)
    app.add_api_route("/test/rate-limit-error", raise_rate_limit_error)
    app.add_api_route("/test/rate-limit-no-retry", raise_rate_limit_error_no_retry)
    app.add_api_route("/test/api-error", raise_api_error)
    app.add_api_route("/test/http-404", raise_http_404)
    app.add_api_route("/test/http-403", raise_http_403)
    app.add_api_route("/test/http-dict-detail", raise_http_dict_detail)
    app.add_api_route("/test/http-non-string-detail", raise_http_non_string_detail)
    app.add_api_route("/test/success", successful_route)

    return app


@pytest_asyncio.fixture
async def client(test_app):
    """Async HTTP client bound to the test app."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as ac:
        yield ac


# ===========================================================================
# Exception Handler Tests
# ===========================================================================


class TestExchangeConnectionErrorHandler:
    """ExchangeConnectionError -> 503 Service Unavailable."""

    async def test_returns_503_status(self, client: AsyncClient):
        resp = await client.get("/test/connection-error")
        assert resp.status_code == 503

    async def test_response_body_format(self, client: AsyncClient):
        resp = await client.get("/test/connection-error")
        body = resp.json()
        assert body["code"] == 503
        assert "Connection refused" in body["message"]
        assert body["data"] is None

    async def test_response_has_three_keys(self, client: AsyncClient):
        resp = await client.get("/test/connection-error")
        body = resp.json()
        assert set(body.keys()) == {"code", "message", "data"}


class TestExchangeAuthenticationErrorHandler:
    """ExchangeAuthenticationError -> 401 Unauthorized."""

    async def test_returns_401_status(self, client: AsyncClient):
        resp = await client.get("/test/auth-error")
        assert resp.status_code == 401

    async def test_response_body_format(self, client: AsyncClient):
        resp = await client.get("/test/auth-error")
        body = resp.json()
        assert body["code"] == 401
        assert "Invalid API key" in body["message"]
        assert body["data"] is None

    async def test_response_has_three_keys(self, client: AsyncClient):
        resp = await client.get("/test/auth-error")
        body = resp.json()
        assert set(body.keys()) == {"code", "message", "data"}


class TestExchangeRateLimitErrorHandler:
    """ExchangeRateLimitError -> 429 Too Many Requests with Retry-After header."""

    async def test_returns_429_status(self, client: AsyncClient):
        resp = await client.get("/test/rate-limit-error")
        assert resp.status_code == 429

    async def test_response_body_format(self, client: AsyncClient):
        resp = await client.get("/test/rate-limit-error")
        body = resp.json()
        assert body["code"] == 429
        assert "Too many requests" in body["message"]
        assert body["data"] is None

    async def test_retry_after_header_present(self, client: AsyncClient):
        resp = await client.get("/test/rate-limit-error")
        assert "retry-after" in resp.headers
        assert resp.headers["retry-after"] == "30"

    async def test_retry_after_defaults_to_1_when_none(self, client: AsyncClient):
        resp = await client.get("/test/rate-limit-no-retry")
        assert resp.status_code == 429
        assert resp.headers["retry-after"] == "1"

    async def test_response_has_three_keys(self, client: AsyncClient):
        resp = await client.get("/test/rate-limit-error")
        body = resp.json()
        assert set(body.keys()) == {"code", "message", "data"}


class TestExchangeAPIErrorHandler:
    """ExchangeAPIError -> 502 Bad Gateway."""

    async def test_returns_502_status(self, client: AsyncClient):
        resp = await client.get("/test/api-error")
        assert resp.status_code == 502

    async def test_response_body_format(self, client: AsyncClient):
        resp = await client.get("/test/api-error")
        body = resp.json()
        assert body["code"] == 502
        assert "Order rejected" in body["message"]
        assert body["data"] is None

    async def test_response_has_three_keys(self, client: AsyncClient):
        resp = await client.get("/test/api-error")
        body = resp.json()
        assert set(body.keys()) == {"code", "message", "data"}


class TestHTTPExceptionHandler:
    """Global HTTPException handler -> uniform {code, message, data} shape."""

    async def test_404_string_detail(self, client: AsyncClient):
        resp = await client.get("/test/http-404")
        assert resp.status_code == 404
        body = resp.json()
        assert body["code"] == 404
        assert body["message"] == "Resource not found"
        assert body["data"] is None

    async def test_403_string_detail(self, client: AsyncClient):
        resp = await client.get("/test/http-403")
        assert resp.status_code == 403
        body = resp.json()
        assert body["code"] == 403
        assert body["message"] == "Forbidden"
        assert body["data"] is None

    async def test_dict_detail_extracts_message(self, client: AsyncClient):
        """When detail is a dict with 'message' key, that value is used."""
        resp = await client.get("/test/http-dict-detail")
        assert resp.status_code == 500
        body = resp.json()
        assert body["code"] == 500
        assert body["message"] == "Internal server error"
        assert body["data"] is None

    async def test_non_string_detail_converted_to_str(self, client: AsyncClient):
        """When detail is neither str nor dict-with-message, it is str()'d."""
        resp = await client.get("/test/http-non-string-detail")
        assert resp.status_code == 422
        body = resp.json()
        assert body["code"] == 422
        # The list ["validation", "errors"] should be stringified
        assert "validation" in body["message"]
        assert body["data"] is None

    async def test_response_always_has_three_keys(self, client: AsyncClient):
        resp = await client.get("/test/http-404")
        body = resp.json()
        assert set(body.keys()) == {"code", "message", "data"}

    async def test_nonexistent_route_returns_404(self, client: AsyncClient):
        """Routes not found should return 404. Note: Starlette's default
        route-not-found handler produces {"detail": "Not Found"} and does not
        pass through the custom HTTPException handler, so the response shape
        may differ from the uniform format."""
        resp = await client.get("/this/route/does/not/exist")
        assert resp.status_code == 404


# ===========================================================================
# App Configuration Tests
# ===========================================================================


class TestCreateApp:
    """Verify create_app() produces a correctly configured FastAPI instance."""

    def test_returns_fastapi_instance(self):
        from fastapi import FastAPI

        app = create_app()
        assert isinstance(app, FastAPI)

    def test_docs_url_under_api_prefix(self):
        app = create_app()
        # Default api_prefix is "/api/v1"
        assert app.docs_url == "/api/v1/docs"

    def test_redoc_url_under_api_prefix(self):
        app = create_app()
        assert app.redoc_url == "/api/v1/redoc"

    def test_openapi_url_under_api_prefix(self):
        app = create_app()
        assert app.openapi_url == "/api/v1/openapi.json"

    def test_app_title(self):
        app = create_app()
        assert app.title == "Squant"

    def test_app_version(self):
        app = create_app()
        assert app.version == "0.1.0"

    def test_cors_middleware_is_added(self):
        app = create_app()
        middleware_classes = [type(m).__name__ for m in app.user_middleware]
        # CORSMiddleware is added via app.add_middleware, which stores it
        # in user_middleware as Middleware objects wrapping the class.
        has_cors = any("CORS" in str(m) for m in app.user_middleware)
        assert has_cors, f"CORS middleware not found in {middleware_classes}"

    def test_api_router_included(self):
        """The api_router should be included — verify by checking that
        known route paths exist on the app."""
        app = create_app()
        route_paths = [route.path for route in app.routes]
        # Health endpoint is at /api/v1/health/* per the router configuration
        assert any("/api/v1" in path for path in route_paths), (
            f"No routes with /api/v1 prefix found. Routes: {route_paths}"
        )


class TestConfigureLogging:
    """Verify _configure_logging() is called during create_app()."""

    def test_configure_logging_called_in_create_app(self):
        with patch("squant.main._configure_logging") as mock_logging:
            create_app()
            mock_logging.assert_called_once()


# ===========================================================================
# Successful Route Test (baseline sanity check)
# ===========================================================================


class TestSuccessfulRoute:
    """Ensure the test infrastructure works — a non-raising route returns 200."""

    async def test_success_returns_200(self, client: AsyncClient):
        resp = await client.get("/test/success")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
