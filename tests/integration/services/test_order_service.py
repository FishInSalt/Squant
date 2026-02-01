"""
Integration tests for Order Service.

Tests order service functionality with real database integration:
- Order creation and persistence
- Order synchronization from exchange
- Order status updates
- Order filtering and counting
- Fee calculation and tracking
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio

from squant.infra.exchange.types import OrderResponse as ExchangeOrder
from squant.models.enums import OrderSide, OrderStatus, OrderType
from squant.models.order import Order
from squant.schemas.order import CreateOrderRequest
from squant.services.order import OrderService


@pytest_asyncio.fixture
async def order_service(db_session, mock_exchange_adapter, sample_exchange_account):
    """Create order service instance."""
    return OrderService(
        session=db_session,
        exchange=mock_exchange_adapter,
        account=sample_exchange_account,
    )


@pytest_asyncio.fixture
async def sample_orders(db_session, sample_exchange_account):
    """Create sample orders for testing."""
    orders = []

    # Create 5 orders with different statuses
    statuses = [
        OrderStatus.SUBMITTED,
        OrderStatus.SUBMITTED,
        OrderStatus.FILLED,
        OrderStatus.CANCELLED,
        OrderStatus.FAILED,
    ]

    for i, status in enumerate(statuses):
        order = Order(
            id=uuid4(),
            exchange_account_id=sample_exchange_account.id,
            exchange_order_id=f"ORDER_{i}",
            symbol="BTC/USDT",
            side=OrderSide.BUY if i % 2 == 0 else OrderSide.SELL,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.01"),
            price=Decimal(f"{40000 + i * 100}"),
            status=status,
            created_at=datetime.now(UTC) - timedelta(minutes=10 - i),
        )

        # Add filled quantity and fees for filled orders
        if status == OrderStatus.FILLED:
            order.filled_quantity = Decimal("0.01")
            order.avg_price = Decimal(f"{40000 + i * 100}")
            order.fee = Decimal("0.4")

        orders.append(order)
        db_session.add(order)

    await db_session.commit()

    # Refresh all orders
    for order in orders:
        await db_session.refresh(order)

    return orders


class TestOrderCreation:
    """Tests for order creation and persistence."""

    @pytest.mark.asyncio
    async def test_create_order_with_strategy(
        self, order_service, sample_exchange_account, sample_strategy
    ):
        """Test creating order associated with a strategy."""
        request = CreateOrderRequest(
            exchange_account_id=sample_exchange_account.id,
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.01"),
            price=Decimal("40000"),
            strategy_id=sample_strategy.id,
        )

        # Mock exchange adapter
        mock_adapter = MagicMock()
        mock_exchange_order = ExchangeOrder(
            order_id="EXCHANGE_123",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=Decimal("0.01"),
            price=Decimal("40000.0"),
            status=OrderStatus.SUBMITTED,
            created_at=datetime.now(UTC),
        )
        mock_adapter.create_order = AsyncMock(return_value=mock_exchange_order)

        with patch("squant.services.order.get_exchange_adapter", return_value=mock_adapter):
            order = await order_service.create(request)

        assert order.strategy_id == sample_strategy.id
        assert order.symbol == "BTC/USDT"
        assert order.exchange_order_id == "EXCHANGE_123"
        assert order.status == OrderStatus.SUBMITTED

    @pytest.mark.asyncio
    async def test_create_order_persists_to_database(
        self, order_service, sample_exchange_account, db_session
    ):
        """Test that created order is persisted to database."""
        request = CreateOrderRequest(
            exchange_account_id=sample_exchange_account.id,
            symbol="ETH/USDT",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.1"),
        )

        # Mock exchange adapter
        mock_adapter = MagicMock()
        mock_exchange_order = ExchangeOrder(
            order_id="MARKET_ORDER",
            symbol="ETH/USDT",
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            amount=Decimal("0.1"),
            status=OrderStatus.SUBMITTED,
            created_at=datetime.now(UTC),
        )
        mock_adapter.create_order = AsyncMock(return_value=mock_exchange_order)

        with patch("squant.services.order.get_exchange_adapter", return_value=mock_adapter):
            order = await order_service.create(request)

        # Verify order exists in database
        await db_session.refresh(order)
        assert order.exchange_order_id == "MARKET_ORDER"
        assert order.side == OrderSide.SELL
        assert order.order_type == OrderType.MARKET


class TestOrderSynchronization:
    """Tests for syncing orders from exchange."""

    @pytest.mark.asyncio
    async def test_sync_order_updates_status(
        self, order_service, sample_orders, sample_exchange_account
    ):
        """Test syncing order updates status from exchange."""
        submitted_order = [o for o in sample_orders if o.status == OrderStatus.SUBMITTED][0]

        # Mock exchange to return filled order
        mock_exchange_order = ExchangeOrder(
            order_id=submitted_order.exchange_order_id,
            symbol=submitted_order.symbol,
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=submitted_order.quantity,
            price=submitted_order.price,
            filled=submitted_order.quantity,  # Fully filled
            avg_price=submitted_order.price,
            status=OrderStatus.FILLED,
            created_at=submitted_order.created_at,
            fee=Decimal("0.4"),
            fee_currency="USDT",
        )

        mock_adapter = MagicMock()
        mock_adapter.get_order = AsyncMock(return_value=mock_exchange_order)

        with patch("squant.services.order.get_exchange_adapter", return_value=mock_adapter):
            updated_order = await order_service.sync_order(
                submitted_order.id, sample_exchange_account.id
            )

        # Verify status was updated
        assert updated_order.status == OrderStatus.FILLED
        assert updated_order.filled_quantity == Decimal("0.01")
        assert updated_order.fee == Decimal("0.4")

    @pytest.mark.asyncio
    async def test_sync_open_orders_from_exchange(
        self, order_service, sample_exchange_account
    ):
        """Test syncing all open orders from exchange."""
        # Mock exchange to return 2 open orders
        mock_exchange_orders = [
            ExchangeOrder(
                order_id="NEW_ORDER_1",
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                type=OrderType.LIMIT,
                amount=Decimal("0.01"),
                price=Decimal("41000.0"),
                status=OrderStatus.SUBMITTED,
                created_at=datetime.now(UTC),
            ),
            ExchangeOrder(
                order_id="NEW_ORDER_2",
                symbol="ETH/USDT",
                side=OrderSide.SELL,
                type=OrderType.LIMIT,
                amount=Decimal("0.1"),
                price=Decimal("2500.0"),
                status=OrderStatus.SUBMITTED,
                created_at=datetime.now(UTC),
            ),
        ]

        mock_adapter = MagicMock()
        mock_adapter.get_open_orders = AsyncMock(return_value=mock_exchange_orders)

        with patch("squant.services.order.get_exchange_adapter", return_value=mock_adapter):
            synced_orders = await order_service.sync_open_orders(sample_exchange_account.id)

        # Should have synced 2 orders
        assert len(synced_orders) == 2
        assert synced_orders[0].exchange_order_id == "NEW_ORDER_1"
        assert synced_orders[1].exchange_order_id == "NEW_ORDER_2"

    @pytest.mark.asyncio
    async def test_sync_partially_filled_order(
        self, order_service, sample_orders, sample_exchange_account
    ):
        """Test syncing partially filled order."""
        submitted_order = [o for o in sample_orders if o.status == OrderStatus.SUBMITTED][0]

        # Mock exchange to return partially filled order
        mock_exchange_order = ExchangeOrder(
            order_id=submitted_order.exchange_order_id,
            symbol=submitted_order.symbol,
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=submitted_order.quantity,
            price=submitted_order.price,
            filled=submitted_order.quantity * Decimal("0.5"),  # 50% filled
            avg_price=submitted_order.price,
            status=OrderStatus.PARTIAL_FILLED,
            created_at=submitted_order.created_at,
            fee=Decimal("0.2"),
            fee_currency="USDT",
        )

        mock_adapter = MagicMock()
        mock_adapter.get_order = AsyncMock(return_value=mock_exchange_order)

        with patch("squant.services.order.get_exchange_adapter", return_value=mock_adapter):
            updated_order = await order_service.sync_order(
                submitted_order.id, sample_exchange_account.id
            )

        # Verify partial fill
        assert updated_order.status == OrderStatus.PARTIAL_FILLED
        assert updated_order.filled_quantity == Decimal("0.005")
        assert updated_order.fee == Decimal("0.2")


class TestOrderCancellation:
    """Tests for order cancellation."""

    @pytest.mark.asyncio
    async def test_cancel_order_success(
        self, order_service, sample_orders, sample_exchange_account
    ):
        """Test successfully canceling an order."""
        submitted_order = [o for o in sample_orders if o.status == OrderStatus.SUBMITTED][0]

        # Mock exchange adapter
        mock_adapter = MagicMock()
        mock_adapter.cancel_order = AsyncMock(return_value=True)

        with patch("squant.services.order.get_exchange_adapter", return_value=mock_adapter):
            canceled_order = await order_service.cancel(
                submitted_order.id, sample_exchange_account.id
            )

        assert canceled_order.status == OrderStatus.CANCELED
        mock_adapter.cancel_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_filled_order_raises_error(
        self, order_service, sample_orders, sample_exchange_account
    ):
        """Test that canceling a filled order raises an error."""
        filled_order = [o for o in sample_orders if o.status == OrderStatus.FILLED][0]

        from squant.services.order import OrderNotCancelableError

        with pytest.raises(OrderNotCancelableError):
            await order_service.cancel(filled_order.id, sample_exchange_account.id)

    @pytest.mark.asyncio
    async def test_cancel_already_canceled_order_raises_error(
        self, order_service, sample_orders, sample_exchange_account
    ):
        """Test that canceling an already canceled order raises an error."""
        canceled_order = [o for o in sample_orders if o.status == OrderStatus.CANCELED][0]

        from squant.services.order import OrderNotCancelableError

        with pytest.raises(OrderNotCancelableError):
            await order_service.cancel(canceled_order.id, sample_exchange_account.id)


class TestOrderQueryAndFiltering:
    """Tests for order querying and filtering."""

    @pytest.mark.asyncio
    async def test_list_orders_by_account(
        self, order_service, sample_orders, sample_exchange_account
    ):
        """Test listing all orders for an account."""
        orders, total = await order_service.list(
            exchange_account_id=sample_exchange_account.id,
            page=1,
            page_size=20,
        )

        # Should return all 5 sample orders
        assert total == 5
        assert len(orders) == 5

    @pytest.mark.asyncio
    async def test_list_orders_filter_by_status(
        self, order_service, sample_orders, sample_exchange_account
    ):
        """Test filtering orders by status."""
        orders, total = await order_service.list(
            exchange_account_id=sample_exchange_account.id,
            status=OrderStatus.SUBMITTED,
            page=1,
            page_size=20,
        )

        # Should return only SUBMITTED orders (2 total)
        assert total == 2
        assert all(order.status == OrderStatus.SUBMITTED for order in orders)

    @pytest.mark.asyncio
    async def test_list_orders_filter_by_symbol(
        self, order_service, sample_exchange_account, db_session
    ):
        """Test filtering orders by symbol."""
        # Create order with different symbol
        order = Order(
            id=uuid4(),
            exchange_account_id=sample_exchange_account.id,
            exchange_order_id="ETH_ORDER",
            symbol="ETH/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.1"),
            price=Decimal("2500"),
            status=OrderStatus.SUBMITTED,
        )
        db_session.add(order)
        await db_session.commit()

        orders, total = await order_service.list(
            exchange_account_id=sample_exchange_account.id,
            symbol="ETH/USDT",
            page=1,
            page_size=20,
        )

        # Should return only ETH/USDT order
        assert total == 1
        assert orders[0].symbol == "ETH/USDT"

    @pytest.mark.asyncio
    async def test_list_orders_pagination(
        self, order_service, sample_orders, sample_exchange_account
    ):
        """Test order list pagination."""
        # Get first page with 2 items
        orders_page1, total = await order_service.list(
            exchange_account_id=sample_exchange_account.id,
            page=1,
            page_size=2,
        )

        assert total == 5
        assert len(orders_page1) == 2

        # Get second page
        orders_page2, _ = await order_service.list(
            exchange_account_id=sample_exchange_account.id,
            page=2,
            page_size=2,
        )

        assert len(orders_page2) == 2

        # Verify different orders on different pages
        assert orders_page1[0].id != orders_page2[0].id

    @pytest.mark.asyncio
    async def test_count_orders_by_status(
        self, order_service, sample_orders, sample_exchange_account
    ):
        """Test counting orders by status."""
        submitted_count = await order_service.repository.count_by_account(
            sample_exchange_account.id,
            status=OrderStatus.SUBMITTED,
        )

        filled_count = await order_service.repository.count_by_account(
            sample_exchange_account.id,
            status=OrderStatus.FILLED,
        )

        assert submitted_count == 2
        assert filled_count == 1


class TestOrderFeeCalculation:
    """Tests for order fee calculation and tracking."""

    @pytest.mark.asyncio
    async def test_fee_tracking_on_fill(
        self, order_service, sample_exchange_account, db_session
    ):
        """Test that fees are tracked when order is filled."""
        # Create pending order
        order = Order(
            id=uuid4(),
            exchange_account_id=sample_exchange_account.id,
            exchange_order_id="FEE_ORDER",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.01"),
            price=Decimal("40000"),
            status=OrderStatus.SUBMITTED,
        )
        db_session.add(order)
        await db_session.commit()
        await db_session.refresh(order)

        # Sync with exchange (filled with fee)
        mock_exchange_order = ExchangeOrder(
            order_id="FEE_ORDER",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=Decimal("0.01"),
            price=Decimal("40000.0"),
            filled=Decimal("0.01"),
            avg_price=Decimal("40000.0"),
            status=OrderStatus.FILLED,
            created_at=datetime.now(UTC),
            fee=Decimal("0.4"),
            fee_currency="USDT",
        )

        mock_adapter = MagicMock()
        mock_adapter.get_order = AsyncMock(return_value=mock_exchange_order)

        with patch("squant.services.order.get_exchange_adapter", return_value=mock_adapter):
            updated_order = await order_service.sync_order(order.id, sample_exchange_account.id)

        # Verify fee was recorded
        assert updated_order.fee == Decimal("0.4")
        assert updated_order.fee_currency == "USDT"

    @pytest.mark.asyncio
    async def test_cumulative_fee_on_partial_fills(
        self, order_service, sample_exchange_account, db_session
    ):
        """Test that fees accumulate on partial fills."""
        # Create pending order
        order = Order(
            id=uuid4(),
            exchange_account_id=sample_exchange_account.id,
            exchange_order_id="PARTIAL_FEE_ORDER",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.02"),
            price=Decimal("40000"),
            status=OrderStatus.SUBMITTED,
        )
        db_session.add(order)
        await db_session.commit()
        await db_session.refresh(order)

        # First partial fill (50%)
        mock_exchange_order_1 = ExchangeOrder(
            order_id="PARTIAL_FEE_ORDER",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=Decimal("0.02"),
            price=Decimal("40000.0"),
            filled=Decimal("0.01"),
            avg_price=Decimal("40000.0"),
            status=OrderStatus.PARTIAL_FILLED,
            created_at=datetime.now(UTC),
            fee=Decimal("0.2"),
            fee_currency="USDT",
        )

        mock_adapter = MagicMock()
        mock_adapter.get_order = AsyncMock(return_value=mock_exchange_order_1)

        with patch("squant.services.order.get_exchange_adapter", return_value=mock_adapter):
            await order_service.sync_order(order.id, sample_exchange_account.id)

        # Refresh order
        await db_session.refresh(order)
        assert order.fee == Decimal("0.2")

        # Second partial fill (remaining 50%)
        mock_exchange_order_2 = ExchangeOrder(
            order_id="PARTIAL_FEE_ORDER",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=Decimal("0.02"),
            price=Decimal("40000.0"),
            filled=Decimal("0.02"),
            avg_price=Decimal("40000.0"),
            status=OrderStatus.FILLED,
            created_at=datetime.now(UTC),
            fee=Decimal("0.4"),  # Total fee
            fee_currency="USDT",
        )

        mock_adapter.get_order = AsyncMock(return_value=mock_exchange_order_2)

        with patch("squant.services.order.get_exchange_adapter", return_value=mock_adapter):
            await order_service.sync_order(order.id, sample_exchange_account.id)

        # Refresh order and verify total fee
        await db_session.refresh(order)
        assert order.fee == Decimal("0.4")
        assert order.status == OrderStatus.FILLED
