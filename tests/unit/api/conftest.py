"""
API unit test fixtures for Squant.

This module provides shared fixtures specific to API endpoint testing.
These fixtures extend the base fixtures from tests/unit/conftest.py with
API-specific utilities like FastAPI TestClient and dependency overrides.

Fixture Categories:
    - TestClient: FastAPI test client with dependency injection
    - Dependency Overrides: Common patterns for overriding FastAPI dependencies
    - Mock Services: Pre-configured service mocks for API testing

Usage:
    These fixtures are automatically available to all tests under tests/unit/api/.

    Example:
        def test_endpoint(api_client, mock_exchange_adapter):
            mock_exchange_adapter.get_ticker.return_value = sample_ticker
            response = api_client.get("/api/v1/market/ticker/BTC/USDT")
            assert response.status_code == 200

Notes:
    - The api_client fixture automatically clears dependency overrides after tests
    - Original fixtures in individual test files are preserved for backward compatibility
    - For complex dependency scenarios, use the override helper functions
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from squant.api.deps import get_exchange, get_okx_exchange, get_session
from squant.main import app

if TYPE_CHECKING:
    pass


# ============================================================================
# FastAPI TestClient Fixtures
# ============================================================================


@pytest.fixture
def api_client() -> TestClient:
    """
    Create a FastAPI TestClient without dependency overrides.

    This is a basic test client for endpoints that don't require
    mocked dependencies. For endpoints requiring mocks, use
    api_client_with_exchange or api_client_with_session.

    Returns:
        TestClient: FastAPI test client

    Example:
        def test_health_endpoint(api_client):
            response = api_client.get("/health")
            assert response.status_code == 200
    """
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def api_client_with_exchange(mock_exchange_adapter) -> TestClient:
    """
    Create a FastAPI TestClient with mocked exchange dependency.

    This fixture overrides the get_exchange dependency with a mock
    exchange adapter. Use this for testing market data endpoints.

    Args:
        mock_exchange_adapter: Mock exchange adapter from unit conftest

    Returns:
        TestClient: FastAPI test client with exchange override

    Example:
        def test_get_ticker(api_client_with_exchange, mock_exchange_adapter):
            mock_exchange_adapter.get_ticker.return_value = ...
            response = api_client_with_exchange.get("/api/v1/market/ticker/BTC/USDT")
    """
    app.dependency_overrides[get_exchange] = lambda: mock_exchange_adapter
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def api_client_with_okx(mock_exchange_adapter) -> TestClient:
    """
    Create a FastAPI TestClient with mocked OKX exchange dependency.

    This fixture overrides the get_okx_exchange dependency with a mock
    adapter. Use this for testing account and order endpoints.

    Args:
        mock_exchange_adapter: Mock exchange adapter from unit conftest

    Returns:
        TestClient: FastAPI test client with OKX exchange override

    Example:
        def test_get_balance(api_client_with_okx, mock_exchange_adapter):
            mock_exchange_adapter.get_balance.return_value = ...
            response = api_client_with_okx.get("/api/v1/account/balance")
    """

    async def override_get_okx_exchange():
        yield mock_exchange_adapter

    app.dependency_overrides[get_okx_exchange] = override_get_okx_exchange
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def api_client_with_session(mock_db_session) -> TestClient:
    """
    Create a FastAPI TestClient with mocked database session dependency.

    This fixture overrides the get_session dependency with a mock session.
    Use this for testing endpoints that interact with the database.

    Args:
        mock_db_session: Mock database session from unit conftest

    Returns:
        TestClient: FastAPI test client with session override

    Example:
        def test_create_strategy(api_client_with_session, mock_db_session):
            response = api_client_with_session.post("/api/v1/strategies", json={...})
    """

    async def override_get_session():
        yield mock_db_session

    app.dependency_overrides[get_session] = override_get_session
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def api_client_with_all_deps(mock_db_session, mock_exchange_adapter) -> TestClient:
    """
    Create a FastAPI TestClient with all common dependencies mocked.

    This fixture overrides both session and exchange dependencies.
    Use this for testing endpoints that require both database and exchange.

    Args:
        mock_db_session: Mock database session from unit conftest
        mock_exchange_adapter: Mock exchange adapter from unit conftest

    Returns:
        TestClient: FastAPI test client with all dependencies overridden

    Example:
        def test_create_order(api_client_with_all_deps):
            response = api_client_with_all_deps.post("/api/v1/orders", json={...})
    """

    async def override_get_session():
        yield mock_db_session

    async def override_get_okx_exchange():
        yield mock_exchange_adapter

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_exchange] = lambda: mock_exchange_adapter
    app.dependency_overrides[get_okx_exchange] = override_get_okx_exchange
    yield TestClient(app)
    app.dependency_overrides.clear()


# ============================================================================
# Dependency Override Helpers
# ============================================================================


@pytest.fixture
def override_dependency():
    """
    Factory fixture for overriding FastAPI dependencies.

    Returns a function that can be used to override any dependency
    with a custom value or factory.

    Returns:
        Callable: Function to override dependencies

    Example:
        def test_custom_dep(override_dependency):
            custom_service = MagicMock()
            override_dependency(SomeService, custom_service)
            # Test with custom service
    """

    def _override(dependency: Callable, value: Any) -> None:
        """
        Override a FastAPI dependency.

        Args:
            dependency: The dependency to override
            value: The value or factory to use instead
        """
        if callable(value) and not isinstance(value, MagicMock):
            app.dependency_overrides[dependency] = value
        else:
            app.dependency_overrides[dependency] = lambda: value

    yield _override
    app.dependency_overrides.clear()


@pytest.fixture
def override_async_generator_dependency():
    """
    Factory fixture for overriding async generator dependencies.

    Use this for dependencies that are async generators (like get_session).

    Returns:
        Callable: Function to override async generator dependencies

    Example:
        def test_custom_session(override_async_generator_dependency, mock_db_session):
            override_async_generator_dependency(get_session, mock_db_session)
            # Test with custom session
    """

    def _override(dependency: Callable, value: Any) -> None:
        """
        Override an async generator dependency.

        Args:
            dependency: The dependency to override
            value: The value to yield from the generator
        """

        async def override() -> AsyncGenerator[Any, None]:
            yield value

        app.dependency_overrides[dependency] = override

    yield _override
    app.dependency_overrides.clear()


# ============================================================================
# Mock Service Fixtures
# ============================================================================


@pytest.fixture
def mock_order_service():
    """
    Create a mock OrderService for API testing.

    Returns a MagicMock with all OrderService methods as AsyncMocks.

    Returns:
        MagicMock: Mock order service

    Example:
        def test_create_order(mock_order_service):
            mock_order_service.create_order.return_value = order
            # Patch and test
    """
    service = MagicMock()
    service.create_order = AsyncMock()
    service.cancel_order = AsyncMock()
    service.get_order = AsyncMock()
    service.list_orders = AsyncMock()
    service.count_orders = AsyncMock()
    service.get_open_orders = AsyncMock()
    service.get_order_stats = AsyncMock()
    service.sync_order = AsyncMock()
    service.sync_open_orders = AsyncMock()
    return service


@pytest.fixture
def mock_backtest_service():
    """
    Create a mock BacktestService for API testing.

    Returns a MagicMock with all BacktestService methods as AsyncMocks.

    Returns:
        MagicMock: Mock backtest service
    """
    service = MagicMock()
    service.create = AsyncMock()
    service.run = AsyncMock()
    service.create_and_run = AsyncMock()
    service.get = AsyncMock()
    service.list_runs = AsyncMock()
    service.delete = AsyncMock()
    service.get_equity_curve = AsyncMock()
    service.check_data_availability = AsyncMock()
    return service


@pytest.fixture
def mock_strategy_service():
    """
    Create a mock StrategyService for API testing.

    Returns a MagicMock with all StrategyService methods as AsyncMocks.

    Returns:
        MagicMock: Mock strategy service
    """
    service = MagicMock()
    service.create = AsyncMock()
    service.get = AsyncMock()
    service.list = AsyncMock()
    service.update = AsyncMock()
    service.delete = AsyncMock()
    service.validate_code = AsyncMock()
    return service


@pytest.fixture
def mock_account_service():
    """
    Create a mock AccountService for API testing.

    Returns a MagicMock with all AccountService methods as AsyncMocks.

    Returns:
        MagicMock: Mock account service
    """
    service = MagicMock()
    service.create = AsyncMock()
    service.get = AsyncMock()
    service.list = AsyncMock()
    service.update = AsyncMock()
    service.delete = AsyncMock()
    service.test_connection = AsyncMock()
    service.get_balance = AsyncMock()
    return service


@pytest.fixture
def mock_risk_service():
    """
    Create a mock RiskService for API testing.

    Returns a MagicMock with all RiskService methods as AsyncMocks.

    Returns:
        MagicMock: Mock risk service
    """
    service = MagicMock()
    service.get_risk_status = AsyncMock()
    service.get_risk_metrics = AsyncMock()
    service.update_limits = AsyncMock()
    service.check_order_risk = AsyncMock()
    return service


@pytest.fixture
def mock_stream_manager():
    """
    Create a mock StreamManager for API testing.

    Returns a MagicMock with StreamManager properties and methods.

    Returns:
        MagicMock: Mock stream manager
    """
    manager = MagicMock()
    manager.REDIS_CHANNEL_PREFIX = "squant:ws:"
    manager.is_running = True
    manager.is_healthy = True
    manager.subscribe_ticker = AsyncMock()
    manager.subscribe_candles = AsyncMock()
    manager.subscribe_trades = AsyncMock()
    manager.subscribe_orderbook = AsyncMock()
    manager.subscribe_orders = AsyncMock()
    manager.subscribe_account = AsyncMock()
    manager.unsubscribe_ticker = AsyncMock()
    manager.unsubscribe_candles = AsyncMock()
    manager.unsubscribe_trades = AsyncMock()
    manager.switch_exchange = AsyncMock()
    manager.start = AsyncMock()
    manager.stop = AsyncMock()
    return manager


# ============================================================================
# Response Assertion Helpers
# ============================================================================


@pytest.fixture
def assert_api_success():
    """
    Factory fixture for asserting successful API responses.

    Returns a function that validates the standard API response format.

    Returns:
        Callable: Function to assert API success

    Example:
        def test_endpoint(api_client, assert_api_success):
            response = api_client.get("/api/v1/endpoint")
            data = assert_api_success(response)
            assert data["key"] == "value"
    """

    def _assert(response, expected_status: int = 200) -> dict:
        """
        Assert API response is successful.

        Args:
            response: Response object from TestClient
            expected_status: Expected HTTP status code

        Returns:
            dict: The 'data' field from the response

        Raises:
            AssertionError: If response format is invalid
        """
        assert response.status_code == expected_status, (
            f"Expected {expected_status}, got {response.status_code}: {response.text}"
        )
        json_data = response.json()
        assert json_data.get("code") == 0, f"Expected code 0, got {json_data.get('code')}"
        return json_data.get("data")

    return _assert


@pytest.fixture
def assert_api_error():
    """
    Factory fixture for asserting error API responses.

    Returns a function that validates API error responses.

    Returns:
        Callable: Function to assert API error

    Example:
        def test_not_found(api_client, assert_api_error):
            response = api_client.get("/api/v1/nonexistent")
            assert_api_error(response, 404, "Not found")
    """

    def _assert(response, expected_status: int, message_contains: str | None = None) -> dict:
        """
        Assert API response is an error.

        Args:
            response: Response object from TestClient
            expected_status: Expected HTTP status code
            message_contains: Optional substring to check in error detail

        Returns:
            dict: The full response JSON

        Raises:
            AssertionError: If response doesn't match expectations
        """
        assert response.status_code == expected_status, (
            f"Expected {expected_status}, got {response.status_code}"
        )
        json_data = response.json()
        if message_contains:
            detail = json_data.get("detail", "")
            assert message_contains in detail, f"Expected '{message_contains}' in '{detail}'"
        return json_data

    return _assert
