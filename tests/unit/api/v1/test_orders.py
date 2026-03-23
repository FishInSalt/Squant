"""Unit tests for orders API endpoints."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from squant.api.v1.orders import get_order_service
from squant.infra.database import get_session
from squant.main import app
from squant.models.enums import OrderSide, OrderStatus, OrderType
from squant.services.order import OrderNotFoundError, OrderValidationError


@pytest.fixture
def mock_session():
    """Create a mock database session."""
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def mock_service():
    """Create a mock OrderService."""
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


@pytest_asyncio.fixture
async def client(mock_session, mock_service) -> AsyncGenerator[AsyncClient, None]:
    """Create async test client with mocked dependencies."""

    async def override_get_session():
        yield mock_session

    async def override_get_order_service():
        yield mock_service

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_order_service] = override_get_order_service
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def mock_order():
    """Create a mock order object."""
    order = MagicMock()
    order.id = str(uuid4())
    order.account_id = str(uuid4())
    order.run_id = None
    order.run = None
    mock_account = MagicMock()
    mock_account.configure_mock(name="Test Account")
    order.account = mock_account
    order.exchange = "okx"
    order.exchange_oid = "EXC123456"
    order.symbol = "BTC/USDT"
    order.side = OrderSide.BUY
    order.type = OrderType.LIMIT
    order.status = OrderStatus.FILLED
    order.price = Decimal("50000")
    order.amount = Decimal("0.1")
    order.filled = Decimal("0.1")
    order.avg_price = Decimal("50000")
    order.reject_reason = None
    order.created_at = datetime.now(UTC)
    order.updated_at = datetime.now(UTC)
    order.trades = []
    return order


@pytest.fixture
def mock_trade():
    """Create a mock trade object."""
    trade = MagicMock()
    trade.id = str(uuid4())
    trade.order_id = str(uuid4())
    trade.exchange_tid = "TRD123456"
    trade.price = Decimal("50000")
    trade.amount = Decimal("0.1")
    trade.fee = Decimal("0.5")
    trade.fee_currency = "USDT"
    trade.timestamp = datetime.now(UTC)
    return trade


@pytest.fixture
def mock_order_repo():
    """Create a mock OrderRepository for read-only endpoint tests."""
    repo = MagicMock()
    repo.list_all = AsyncMock()
    repo.count_all = AsyncMock()
    repo.list_all_open = AsyncMock()
    repo.get_all_stats_by_status = AsyncMock()
    return repo


@pytest.fixture
def valid_create_request() -> dict[str, Any]:
    """Create a valid order creation request."""
    return {
        "symbol": "BTC/USDT",
        "side": "buy",
        "type": "limit",
        "amount": "0.1",
        "price": "50000",
    }


class TestCreateOrder:
    """Tests for POST /api/v1/orders endpoint."""

    @pytest.mark.asyncio
    async def test_create_order_success(
        self, client: AsyncClient, mock_service, valid_create_request: dict, mock_order
    ) -> None:
        """Test successful order creation."""
        mock_service.create_order.return_value = mock_order
        response = await client.post("/api/v1/orders", json=valid_create_request)
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_create_order_missing_symbol(self, client: AsyncClient) -> None:
        """Test creating order without symbol."""
        response = await client.post(
            "/api/v1/orders",
            json={
                "side": "buy",
                "type": "limit",
                "amount": "0.1",
                "price": "50000",
            },
        )

        # Pydantic validation should catch missing symbol
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_order_missing_side(self, client: AsyncClient) -> None:
        """Test creating order without side."""
        response = await client.post(
            "/api/v1/orders",
            json={
                "symbol": "BTC/USDT",
                "type": "limit",
                "amount": "0.1",
                "price": "50000",
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_order_missing_amount(self, client: AsyncClient) -> None:
        """Test creating order without amount."""
        response = await client.post(
            "/api/v1/orders",
            json={
                "symbol": "BTC/USDT",
                "side": "buy",
                "type": "limit",
                "price": "50000",
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_order_validation_error(
        self, client: AsyncClient, mock_service, valid_create_request: dict
    ) -> None:
        """Test order creation with validation error."""
        mock_service.create_order.side_effect = OrderValidationError("Invalid order size")
        response = await client.post("/api/v1/orders", json=valid_create_request)
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_create_market_order_no_price(
        self, client: AsyncClient, mock_service, mock_order
    ) -> None:
        """Test creating market order without price."""
        mock_service.create_order.return_value = mock_order
        response = await client.post(
            "/api/v1/orders",
            json={
                "symbol": "BTC/USDT",
                "side": "buy",
                "type": "market",
                "amount": "0.1",
            },
        )
        assert response.status_code == 201


class TestListOrders:
    """Tests for GET /api/v1/orders endpoint."""

    @pytest.mark.asyncio
    async def test_list_orders_success(
        self, client: AsyncClient, mock_order_repo, mock_order
    ) -> None:
        """Test listing orders."""
        mock_order_repo.list_all.return_value = [mock_order]
        mock_order_repo.count_all.return_value = 1

        with patch("squant.api.v1.orders.OrderRepository", return_value=mock_order_repo):
            response = await client.get("/api/v1/orders")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_orders_with_pagination(
        self, client: AsyncClient, mock_order_repo, mock_order
    ) -> None:
        """Test listing orders with pagination."""
        mock_order_repo.list_all.return_value = [mock_order]
        mock_order_repo.count_all.return_value = 50

        with patch("squant.api.v1.orders.OrderRepository", return_value=mock_order_repo):
            response = await client.get("/api/v1/orders?page=2&page_size=10")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_orders_with_account_id(
        self, client: AsyncClient, mock_order_repo, mock_order
    ) -> None:
        """Test listing orders filtered by account_id."""
        account_id = str(uuid4())
        mock_order_repo.list_all.return_value = [mock_order]
        mock_order_repo.count_all.return_value = 1

        with patch("squant.api.v1.orders.OrderRepository", return_value=mock_order_repo):
            response = await client.get(f"/api/v1/orders?account_id={account_id}")
        assert response.status_code == 200
        mock_order_repo.list_all.assert_called_once()
        call_kwargs = mock_order_repo.list_all.call_args[1]
        assert call_kwargs["account_id"] == account_id

    @pytest.mark.asyncio
    async def test_list_orders_with_date_range(
        self, client: AsyncClient, mock_order_repo, mock_order
    ) -> None:
        """Test listing orders filtered by start_time and end_time."""
        mock_order_repo.list_all.return_value = [mock_order]
        mock_order_repo.count_all.return_value = 1

        with patch("squant.api.v1.orders.OrderRepository", return_value=mock_order_repo):
            response = await client.get(
                "/api/v1/orders?start_time=2025-01-01T00:00:00&end_time=2025-12-31T23:59:59"
            )
        assert response.status_code == 200
        list_kwargs = mock_order_repo.list_all.call_args[1]
        assert list_kwargs["start_time"] is not None
        assert list_kwargs["end_time"] is not None
        count_kwargs = mock_order_repo.count_all.call_args[1]
        assert count_kwargs["start_time"] is not None
        assert count_kwargs["end_time"] is not None

    @pytest.mark.asyncio
    async def test_list_orders_with_all_filters(
        self, client: AsyncClient, mock_order_repo, mock_order
    ) -> None:
        """Test listing orders with all filters combined."""
        account_id = str(uuid4())
        mock_order_repo.list_all.return_value = [mock_order]
        mock_order_repo.count_all.return_value = 1

        with patch("squant.api.v1.orders.OrderRepository", return_value=mock_order_repo):
            response = await client.get(
                f"/api/v1/orders?account_id={account_id}"
                "&status=filled&symbol=BTC/USDT&side=buy"
                "&start_time=2025-01-01T00:00:00&end_time=2025-12-31T23:59:59"
                "&page=1&page_size=50"
            )
        assert response.status_code == 200
        list_kwargs = mock_order_repo.list_all.call_args[1]
        assert list_kwargs["account_id"] == account_id
        assert list_kwargs["symbol"] == "BTC/USDT"
        assert list_kwargs["start_time"] is not None
        assert list_kwargs["end_time"] is not None


class TestGetOpenOrders:
    """Tests for GET /api/v1/orders/open endpoint."""

    @pytest.mark.asyncio
    async def test_get_open_orders_success(
        self, client: AsyncClient, mock_order_repo, mock_order
    ) -> None:
        """Test getting open orders."""
        mock_order.status = OrderStatus.SUBMITTED
        mock_order_repo.list_all_open.return_value = [mock_order]

        with patch("squant.api.v1.orders.OrderRepository", return_value=mock_order_repo):
            response = await client.get("/api/v1/orders/open")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_open_orders_with_symbol(
        self, client: AsyncClient, mock_order_repo, mock_order
    ) -> None:
        """Test getting open orders for specific symbol."""
        mock_order.status = OrderStatus.SUBMITTED
        mock_order_repo.list_all_open.return_value = [mock_order]

        with patch("squant.api.v1.orders.OrderRepository", return_value=mock_order_repo):
            response = await client.get("/api/v1/orders/open?symbol=BTC/USDT")
        assert response.status_code == 200


class TestGetOrderStats:
    """Tests for GET /api/v1/orders/stats endpoint."""

    @pytest.mark.asyncio
    async def test_get_order_stats_success(self, client: AsyncClient, mock_order_repo) -> None:
        """Test getting order statistics."""
        mock_order_repo.get_all_stats_by_status.return_value = {
            OrderStatus.PENDING: 5,
            OrderStatus.SUBMITTED: 10,
            OrderStatus.PARTIAL: 3,
            OrderStatus.FILLED: 70,
            OrderStatus.CANCELLED: 10,
            OrderStatus.REJECTED: 2,
        }

        with patch("squant.api.v1.orders.OrderRepository", return_value=mock_order_repo):
            response = await client.get("/api/v1/orders/stats")
        assert response.status_code == 200


class TestGetOrder:
    """Tests for GET /api/v1/orders/{order_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_order_success(
        self, client: AsyncClient, mock_service, mock_order, mock_trade
    ) -> None:
        """Test getting an order by ID."""
        mock_order.trades = [mock_trade]
        mock_service.get_order.return_value = mock_order

        response = await client.get(f"/api/v1/orders/{mock_order.id}")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_order_not_found(self, client: AsyncClient, mock_service) -> None:
        """Test getting non-existent order."""
        order_id = uuid4()
        mock_service.get_order.side_effect = OrderNotFoundError(str(order_id))

        response = await client.get(f"/api/v1/orders/{order_id}")
        assert response.status_code == 404


class TestCancelOrder:
    """Tests for POST /api/v1/orders/{order_id}/cancel endpoint."""

    @pytest.mark.asyncio
    async def test_cancel_order_success(
        self, client: AsyncClient, mock_service, mock_order
    ) -> None:
        """Test cancelling an order."""
        mock_order.status = OrderStatus.CANCELLED
        mock_service.cancel_order.return_value = mock_order

        response = await client.post(f"/api/v1/orders/{mock_order.id}/cancel")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_cancel_order_not_found(self, client: AsyncClient, mock_service) -> None:
        """Test cancelling non-existent order."""
        order_id = uuid4()
        mock_service.cancel_order.side_effect = OrderNotFoundError(str(order_id))

        response = await client.post(f"/api/v1/orders/{order_id}/cancel")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_cancel_order_validation_error(
        self, client: AsyncClient, mock_service, mock_order
    ) -> None:
        """Test cancelling order with validation error."""
        mock_service.cancel_order.side_effect = OrderValidationError("Order already filled")

        response = await client.post(f"/api/v1/orders/{mock_order.id}/cancel")
        assert response.status_code == 400


class TestSyncOrder:
    """Tests for POST /api/v1/orders/{order_id}/sync endpoint."""

    @pytest.mark.asyncio
    async def test_sync_order_success(self, client: AsyncClient, mock_service, mock_order) -> None:
        """Test syncing an order."""
        mock_service.sync_order.return_value = mock_order

        response = await client.post(f"/api/v1/orders/{mock_order.id}/sync")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_sync_order_not_found(self, client: AsyncClient, mock_service) -> None:
        """Test syncing non-existent order."""
        order_id = uuid4()
        mock_service.sync_order.side_effect = OrderNotFoundError(str(order_id))

        response = await client.post(f"/api/v1/orders/{order_id}/sync")
        assert response.status_code == 404


class TestSyncOpenOrders:
    """Tests for POST /api/v1/orders/sync endpoint."""

    @pytest.mark.asyncio
    async def test_sync_open_orders_success(
        self, client: AsyncClient, mock_service, mock_order
    ) -> None:
        """Test syncing all open orders."""
        mock_service.sync_open_orders.return_value = [mock_order]

        response = await client.post("/api/v1/orders/sync")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_sync_open_orders_with_symbol(
        self, client: AsyncClient, mock_service, mock_order
    ) -> None:
        """Test syncing open orders for specific symbol."""
        mock_service.sync_open_orders.return_value = [mock_order]

        response = await client.post("/api/v1/orders/sync?symbol=BTC/USDT")
        assert response.status_code == 200
