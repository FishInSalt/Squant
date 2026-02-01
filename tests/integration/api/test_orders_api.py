"""
Integration tests for Order API endpoints.

Tests validate acceptance criteria from dev-docs/requirements/acceptance-criteria/04-order.md:
- ORD-001: Current open orders list
- ORD-002: Historical orders list
- ORD-003: Order details view
- ORD-004: Manual order cancellation
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from squant.main import app
from squant.models.enums import OrderSide, OrderStatus, OrderType
from squant.models.order import Order
from squant.services.order import OrderService


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
async def sample_orders(db_session, sample_exchange_account):
    """Create sample orders for testing."""
    orders = []

    # Create 3 open orders (SUBMITTED)
    for i in range(3):
        order = Order(
            id=uuid4(),
            exchange_account_id=sample_exchange_account.id,
            exchange_order_id=f"ORDER_{i}",
            symbol=f"BTC/USDT" if i < 2 else "ETH/USDT",
            side=OrderSide.BUY if i % 2 == 0 else OrderSide.SELL,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.01"),
            price=Decimal(f"{40000 + i * 100}"),
            status=OrderStatus.SUBMITTED,
            created_at=datetime.now(UTC) - timedelta(minutes=10 - i),
        )
        orders.append(order)
        db_session.add(order)

    # Create 2 filled orders
    for i in range(2):
        order = Order(
            id=uuid4(),
            exchange_account_id=sample_exchange_account.id,
            exchange_order_id=f"FILLED_{i}",
            symbol="BTC/USDT",
            side=OrderSide.BUY if i == 0 else OrderSide.SELL,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.01"),
            price=Decimal("40000"),
            filled_quantity=Decimal("0.01"),
            avg_price=Decimal("40000"),
            fee=Decimal("0.4"),
            status=OrderStatus.FILLED,
            created_at=datetime.now(UTC) - timedelta(hours=i + 1),
            updated_at=datetime.now(UTC) - timedelta(minutes=30),
        )
        orders.append(order)
        db_session.add(order)

    # Create 1 canceled order
    order = Order(
        id=uuid4(),
        exchange_account_id=sample_exchange_account.id,
        exchange_order_id="CANCELED_1",
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.01"),
        price=Decimal("40000"),
        status=OrderStatus.CANCELED,
        created_at=datetime.now(UTC) - timedelta(hours=3),
    )
    orders.append(order)
    db_session.add(order)

    await db_session.commit()

    # Refresh all orders to get database state
    for order in orders:
        await db_session.refresh(order)

    return orders


class TestCurrentOpenOrdersList:
    """
    Tests for ORD-001: Current open orders list

    Acceptance criteria:
    - Display all unfilled orders
    - Show symbol, direction, price, quantity, status, time for each order
    - Show "No orders" when empty
    """

    @pytest.mark.asyncio
    async def test_list_open_orders_with_data(
        self, client, db_session, sample_orders, sample_exchange_account
    ):
        """Test ORD-001-1: Display all unfilled orders."""
        with patch("squant.api.deps.get_db_session", return_value=db_session):
            response = client.get(
                f"/api/v1/orders?account_id={sample_exchange_account.id}&status=SUBMITTED"
            )

        assert response.status_code == 200
        data = response.json()

        # Should have 3 open orders
        assert data["total"] == 3
        assert len(data["items"]) == 3

    @pytest.mark.asyncio
    async def test_order_display_fields(
        self, client, db_session, sample_orders, sample_exchange_account
    ):
        """Test ORD-001-2: Each order displays required fields."""
        with patch("squant.api.deps.get_db_session", return_value=db_session):
            response = client.get(
                f"/api/v1/orders?account_id={sample_exchange_account.id}&status=SUBMITTED"
            )

        assert response.status_code == 200
        data = response.json()

        # Check first order has all required fields
        order = data["items"][0]
        assert "symbol" in order
        assert "side" in order  # direction
        assert "price" in order
        assert "quantity" in order
        assert "status" in order
        assert "created_at" in order  # time

    @pytest.mark.asyncio
    async def test_no_open_orders_empty_state(self, client, db_session, sample_exchange_account):
        """Test ORD-001-3: Show empty state when no open orders."""
        with patch("squant.api.deps.get_db_session", return_value=db_session):
            response = client.get(
                f"/api/v1/orders?account_id={sample_exchange_account.id}&status=PENDING_CANCEL"
            )

        assert response.status_code == 200
        data = response.json()

        # Should have no orders
        assert data["total"] == 0
        assert len(data["items"]) == 0


class TestHistoricalOrdersList:
    """
    Tests for ORD-002: Historical orders list

    Acceptance criteria:
    - Display completed/canceled orders
    - Support pagination
    - Auto-load more on scroll (frontend behavior, API supports pagination)
    """

    @pytest.mark.asyncio
    async def test_list_historical_orders(
        self, client, db_session, sample_orders, sample_exchange_account
    ):
        """Test ORD-002-1: Display completed/canceled orders."""
        with patch("squant.api.deps.get_db_session", return_value=db_session):
            response = client.get(
                f"/api/v1/orders?account_id={sample_exchange_account.id}"
            )

        assert response.status_code == 200
        data = response.json()

        # Should have all 6 orders (3 submitted + 2 filled + 1 canceled)
        assert data["total"] == 6

    @pytest.mark.asyncio
    async def test_filter_completed_orders(
        self, client, db_session, sample_orders, sample_exchange_account
    ):
        """Test filtering for completed orders only."""
        with patch("squant.api.deps.get_db_session", return_value=db_session):
            response = client.get(
                f"/api/v1/orders?account_id={sample_exchange_account.id}&status=FILLED"
            )

        assert response.status_code == 200
        data = response.json()

        # Should have 2 filled orders
        assert data["total"] == 2
        assert all(order["status"] == "FILLED" for order in data["items"])

    @pytest.mark.asyncio
    async def test_pagination_support(
        self, client, db_session, sample_orders, sample_exchange_account
    ):
        """Test ORD-002-2: Support pagination."""
        with patch("squant.api.deps.get_db_session", return_value=db_session):
            # Get first page with 2 items
            response = client.get(
                f"/api/v1/orders?account_id={sample_exchange_account.id}&page=1&page_size=2"
            )

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 6
        assert len(data["items"]) == 2
        assert data["page"] == 1
        assert data["page_size"] == 2

    @pytest.mark.asyncio
    async def test_pagination_second_page(
        self, client, db_session, sample_orders, sample_exchange_account
    ):
        """Test ORD-002-3: Auto-load more (second page)."""
        with patch("squant.api.deps.get_db_session", return_value=db_session):
            # Get second page with 2 items
            response = client.get(
                f"/api/v1/orders?account_id={sample_exchange_account.id}&page=2&page_size=2"
            )

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 6
        assert len(data["items"]) == 2
        assert data["page"] == 2


class TestOrderDetailsView:
    """
    Tests for ORD-003: Order details view

    Acceptance criteria:
    - Click order to show details
    - Display complete info: trade records, fees, associated strategy
    """

    @pytest.mark.asyncio
    async def test_get_order_details(
        self, client, db_session, sample_orders, sample_exchange_account
    ):
        """Test ORD-003-1: Get order details."""
        filled_order = [o for o in sample_orders if o.status == OrderStatus.FILLED][0]

        with patch("squant.api.deps.get_db_session", return_value=db_session):
            response = client.get(f"/api/v1/orders/{filled_order.id}")

        assert response.status_code == 200
        data = response.json()

        assert data["id"] == str(filled_order.id)
        assert data["symbol"] == filled_order.symbol
        assert data["status"] == "FILLED"

    @pytest.mark.asyncio
    async def test_order_details_includes_fee(
        self, client, db_session, sample_orders
    ):
        """Test ORD-003-2: Order details include fees."""
        filled_order = [o for o in sample_orders if o.status == OrderStatus.FILLED][0]

        with patch("squant.api.deps.get_db_session", return_value=db_session):
            response = client.get(f"/api/v1/orders/{filled_order.id}")

        assert response.status_code == 200
        data = response.json()

        # Check fee is included
        assert "fee" in data
        assert float(data["fee"]) == 0.4

    @pytest.mark.asyncio
    async def test_order_details_includes_strategy(
        self, client, db_session, sample_exchange_account, sample_strategy
    ):
        """Test ORD-003-2: Order details include associated strategy."""
        # Create order with strategy_id
        order = Order(
            id=uuid4(),
            exchange_account_id=sample_exchange_account.id,
            exchange_order_id="STRATEGY_ORDER",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.01"),
            price=Decimal("40000"),
            status=OrderStatus.SUBMITTED,
            strategy_id=sample_strategy.id,
        )
        db_session.add(order)
        await db_session.commit()
        await db_session.refresh(order)

        with patch("squant.api.deps.get_db_session", return_value=db_session):
            response = client.get(f"/api/v1/orders/{order.id}")

        assert response.status_code == 200
        data = response.json()

        # Check strategy is included
        assert "strategy_id" in data
        assert data["strategy_id"] == str(sample_strategy.id)


class TestManualOrderCancellation:
    """
    Tests for ORD-004: Manual order cancellation

    Acceptance criteria:
    - Cancel pending orders
    - Update status to "Canceled" on exchange confirmation
    - Show error "Order already filled, cannot cancel" if already filled
    """

    @pytest.mark.asyncio
    async def test_cancel_pending_order_success(
        self, client, db_session, sample_orders
    ):
        """Test ORD-004-1: Cancel pending order successfully."""
        pending_order = [o for o in sample_orders if o.status == OrderStatus.SUBMITTED][0]

        # Mock exchange adapter to return success
        mock_adapter = MagicMock()
        mock_adapter.cancel_order = AsyncMock(return_value=True)

        with (
            patch("squant.api.deps.get_db_session", return_value=db_session),
            patch("squant.api.v1.orders.get_exchange_adapter", return_value=mock_adapter),
        ):
            response = client.post(f"/api/v1/orders/{pending_order.id}/cancel")

        assert response.status_code == 200
        data = response.json()

        # Verify order was canceled
        assert data["status"] == "CANCELED"
        mock_adapter.cancel_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_order_updates_status(
        self, client, db_session, sample_orders
    ):
        """Test ORD-004-2: Order status updates to CANCELED on confirmation."""
        pending_order = [o for o in sample_orders if o.status == OrderStatus.SUBMITTED][0]

        # Mock exchange adapter
        mock_adapter = MagicMock()
        mock_adapter.cancel_order = AsyncMock(return_value=True)

        with (
            patch("squant.api.deps.get_db_session", return_value=db_session),
            patch("squant.api.v1.orders.get_exchange_adapter", return_value=mock_adapter),
        ):
            response = client.post(f"/api/v1/orders/{pending_order.id}/cancel")

        assert response.status_code == 200

        # Refresh order from database
        await db_session.refresh(pending_order)

        # Verify status was updated in database
        assert pending_order.status == OrderStatus.CANCELED

    @pytest.mark.asyncio
    async def test_cancel_filled_order_error(
        self, client, db_session, sample_orders
    ):
        """Test ORD-004-3: Cannot cancel already filled order."""
        filled_order = [o for o in sample_orders if o.status == OrderStatus.FILLED][0]

        with patch("squant.api.deps.get_db_session", return_value=db_session):
            response = client.post(f"/api/v1/orders/{filled_order.id}/cancel")

        assert response.status_code == 400
        data = response.json()

        # Should contain error message about order already filled
        assert "已成交" in data["detail"] or "filled" in data["detail"].lower()
