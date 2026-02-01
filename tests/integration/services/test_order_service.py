"""
Integration tests for Order Service.

Tests order service functionality with real database integration:
- Order creation and submission to exchange
- Order cancellation
- Order status synchronization
- Order querying and filtering
- Order statistics
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio

from squant.infra.exchange.types import OrderResponse as ExchangeOrderResponse
from squant.models.enums import OrderSide, OrderStatus, OrderType
from squant.models.order import Order
from squant.services.order import (
    OrderNotFoundError,
    OrderService,
    OrderValidationError,
)


@pytest_asyncio.fixture
async def order_service(db_session, mock_exchange_adapter, sample_exchange_account):
    """Create order service instance."""
    return OrderService(
        session=db_session,
        exchange=mock_exchange_adapter,
        account=sample_exchange_account,
    )


class TestOrderCreation:
    """Tests for order creation and submission."""

    @pytest.mark.asyncio
    async def test_create_market_order(self, order_service, mock_exchange_adapter):
        """Test creating and submitting a market order."""
        # Mock exchange response
        exchange_response = ExchangeOrderResponse(
            order_id="EXCH_123",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.01"),
            filled=Decimal("0.01"),
            price=None,
            avg_price=Decimal("40000"),
            status=OrderStatus.FILLED,
            created_at=datetime.now(UTC),
            fee=Decimal("0.4"),
            fee_currency="USDT",
        )
        mock_exchange_adapter.place_order = AsyncMock(return_value=exchange_response)

        # Create order
        order = await order_service.create_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            amount=Decimal("0.01"),
        )

        # Verify order was created and updated with exchange response
        assert order.symbol == "BTC/USDT"
        assert order.side == OrderSide.BUY
        assert order.type == OrderType.MARKET
        assert order.amount == Decimal("0.01")
        assert order.exchange_oid == "EXCH_123"
        assert order.status == OrderStatus.FILLED
        assert order.filled == Decimal("0.01")
        assert order.avg_price == Decimal("40000")

        # Verify exchange adapter was called
        mock_exchange_adapter.place_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_limit_order(self, order_service, mock_exchange_adapter):
        """Test creating a limit order."""
        exchange_response = ExchangeOrderResponse(
            order_id="EXCH_456",
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            type=OrderType.LIMIT,
            amount=Decimal("0.02"),
            filled=Decimal("0"),
            price=Decimal("45000"),
            avg_price=None,
            status=OrderStatus.SUBMITTED,
            created_at=datetime.now(UTC),
            fee=Decimal("0"),
            fee_currency="USDT",
        )
        mock_exchange_adapter.place_order = AsyncMock(return_value=exchange_response)

        order = await order_service.create_order(
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            amount=Decimal("0.02"),
            price=Decimal("45000"),
        )

        assert order.type == OrderType.LIMIT
        assert order.price == Decimal("45000")
        assert order.status == OrderStatus.SUBMITTED
        assert order.filled == Decimal("0")

    @pytest.mark.skip(
        reason="Requires creating StrategyRun with foreign key to Strategy - complex setup"
    )
    @pytest.mark.asyncio
    async def test_create_order_with_run_id(self, order_service, mock_exchange_adapter, sample_strategy):
        """Test creating order associated with a strategy run."""
        # Requires creating a StrategyRun first, which requires a Strategy
        # Foreign key constraint will fail without proper setup
        pass

    @pytest.mark.asyncio
    async def test_create_limit_order_without_price_raises_error(self, order_service):
        """Test that creating limit order without price raises validation error."""
        with pytest.raises(OrderValidationError, match="Limit orders require a price"):
            await order_service.create_order(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                amount=Decimal("0.01"),
                # Missing price
            )

    @pytest.mark.asyncio
    async def test_create_order_with_zero_amount_raises_error(self, order_service):
        """Test that creating order with zero amount raises validation error."""
        with pytest.raises(OrderValidationError, match="Amount must be positive"):
            await order_service.create_order(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                amount=Decimal("0"),
            )

    @pytest.mark.asyncio
    async def test_create_order_marks_rejected_on_exchange_error(
        self, order_service, mock_exchange_adapter, db_session
    ):
        """Test that order is marked as rejected if exchange rejects it."""
        # Mock exchange to raise error
        mock_exchange_adapter.place_order = AsyncMock(side_effect=Exception("Insufficient balance"))

        with pytest.raises(Exception, match="Insufficient balance"):
            await order_service.create_order(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                amount=Decimal("100"),  # Too large
            )

        # Verify order was marked as rejected
        from sqlalchemy import select

        result = await db_session.execute(select(Order))
        orders = result.scalars().all()

        assert len(orders) == 1
        assert orders[0].status == OrderStatus.REJECTED
        assert "Insufficient balance" in orders[0].reject_reason


class TestOrderCancellation:
    """Tests for order cancellation."""

    @pytest.mark.asyncio
    async def test_cancel_order(self, order_service, mock_exchange_adapter, db_session):
        """Test cancelling an order."""
        # First create an order
        exchange_response = ExchangeOrderResponse(
            order_id="EXCH_CANCEL_1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=Decimal("0.01"),
            filled=Decimal("0"),
            price=Decimal("40000"),
            avg_price=None,
            status=OrderStatus.SUBMITTED,
            created_at=datetime.now(UTC),
            fee=Decimal("0"),
            fee_currency="USDT",
        )
        mock_exchange_adapter.place_order = AsyncMock(return_value=exchange_response)

        order = await order_service.create_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            amount=Decimal("0.01"),
            price=Decimal("40000"),
        )

        # Mock cancel response
        cancel_response = ExchangeOrderResponse(
            order_id="EXCH_CANCEL_1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=Decimal("0.01"),
            filled=Decimal("0"),
            price=Decimal("40000"),
            avg_price=None,
            status=OrderStatus.CANCELLED,
            created_at=datetime.now(UTC),
            fee=Decimal("0"),
            fee_currency="USDT",
        )
        mock_exchange_adapter.cancel_order = AsyncMock(return_value=cancel_response)

        # Cancel the order
        cancelled_order = await order_service.cancel_order(order.id)

        assert cancelled_order.status == OrderStatus.CANCELLED
        mock_exchange_adapter.cancel_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_order_raises_error(self, order_service):
        """Test that cancelling nonexistent order raises error."""
        with pytest.raises(OrderNotFoundError):
            await order_service.cancel_order(uuid4())

    @pytest.mark.asyncio
    async def test_cancel_filled_order_raises_error(self, order_service, mock_exchange_adapter):
        """Test that cancelling filled order raises validation error."""
        # Create a filled order
        exchange_response = ExchangeOrderResponse(
            order_id="EXCH_FILLED",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.01"),
            filled=Decimal("0.01"),
            price=None,
            avg_price=Decimal("40000"),
            status=OrderStatus.FILLED,
            created_at=datetime.now(UTC),
            fee=Decimal("0.4"),
            fee_currency="USDT",
        )
        mock_exchange_adapter.place_order = AsyncMock(return_value=exchange_response)

        order = await order_service.create_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            amount=Decimal("0.01"),
        )

        # Try to cancel it
        with pytest.raises(OrderValidationError, match="Cannot cancel order with status"):
            await order_service.cancel_order(order.id)


class TestOrderRetrieval:
    """Tests for retrieving orders."""

    @pytest.mark.asyncio
    async def test_get_order_by_id(self, order_service, mock_exchange_adapter):
        """Test retrieving order by ID."""
        # Create order first
        exchange_response = ExchangeOrderResponse(
            order_id="EXCH_GET_1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.01"),
            filled=Decimal("0.01"),
            price=None,
            avg_price=Decimal("40000"),
            status=OrderStatus.FILLED,
            created_at=datetime.now(UTC),
            fee=Decimal("0.4"),
            fee_currency="USDT",
        )
        mock_exchange_adapter.place_order = AsyncMock(return_value=exchange_response)

        created_order = await order_service.create_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            amount=Decimal("0.01"),
        )

        # Get order by ID
        retrieved_order = await order_service.get_order(created_order.id)

        assert retrieved_order.id == created_order.id
        assert retrieved_order.symbol == "BTC/USDT"

    @pytest.mark.asyncio
    async def test_get_nonexistent_order_raises_error(self, order_service):
        """Test that getting nonexistent order raises error."""
        with pytest.raises(OrderNotFoundError):
            await order_service.get_order(uuid4())

    @pytest.mark.asyncio
    async def test_get_order_by_exchange_oid(self, order_service, mock_exchange_adapter):
        """Test retrieving order by exchange order ID."""
        exchange_response = ExchangeOrderResponse(
            order_id="EXCH_UNIQUE_123",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.01"),
            filled=Decimal("0.01"),
            price=None,
            avg_price=Decimal("40000"),
            status=OrderStatus.FILLED,
            created_at=datetime.now(UTC),
            fee=Decimal("0.4"),
            fee_currency="USDT",
        )
        mock_exchange_adapter.place_order = AsyncMock(return_value=exchange_response)

        await order_service.create_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            amount=Decimal("0.01"),
        )

        # Get by exchange order ID
        order = await order_service.get_order_by_exchange_oid("EXCH_UNIQUE_123")

        assert order.exchange_oid == "EXCH_UNIQUE_123"

    @pytest.mark.asyncio
    async def test_list_orders(self, order_service, mock_exchange_adapter):
        """Test listing orders."""
        # Create multiple orders
        for i in range(3):
            exchange_response = ExchangeOrderResponse(
                order_id=f"EXCH_LIST_{i}",
                symbol="BTC/USDT",
                side=OrderSide.BUY if i % 2 == 0 else OrderSide.SELL,
                type=OrderType.MARKET,
                amount=Decimal("0.01"),
                filled=Decimal("0.01"),
                price=None,
                avg_price=Decimal("40000"),
                status=OrderStatus.FILLED,
                created_at=datetime.now(UTC),
                fee=Decimal("0.4"),
                fee_currency="USDT",
            )
            mock_exchange_adapter.place_order = AsyncMock(return_value=exchange_response)

            await order_service.create_order(
                symbol="BTC/USDT",
                side=OrderSide.BUY if i % 2 == 0 else OrderSide.SELL,
                order_type=OrderType.MARKET,
                amount=Decimal("0.01"),
            )

        # List all orders
        orders = await order_service.list_orders()

        assert len(orders) == 3

    @pytest.mark.asyncio
    async def test_list_orders_filter_by_status(self, order_service, mock_exchange_adapter):
        """Test filtering orders by status."""
        # Create orders with different statuses
        statuses = [OrderStatus.SUBMITTED, OrderStatus.FILLED, OrderStatus.CANCELLED]

        for i, status in enumerate(statuses):
            exchange_response = ExchangeOrderResponse(
                order_id=f"EXCH_STATUS_{i}",
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                type=OrderType.LIMIT,
                amount=Decimal("0.01"),
                filled=Decimal("0.01") if status == OrderStatus.FILLED else Decimal("0"),
                price=Decimal("40000"),
                avg_price=Decimal("40000") if status == OrderStatus.FILLED else None,
                status=status,
                created_at=datetime.now(UTC),
                fee=Decimal("0.4") if status == OrderStatus.FILLED else Decimal("0"),
                fee_currency="USDT",
            )
            mock_exchange_adapter.place_order = AsyncMock(return_value=exchange_response)

            await order_service.create_order(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                amount=Decimal("0.01"),
                price=Decimal("40000"),
            )

        # Filter by FILLED status
        filled_orders = await order_service.list_orders(status=OrderStatus.FILLED)

        assert len(filled_orders) == 1
        assert all(o.status == OrderStatus.FILLED for o in filled_orders)

    @pytest.mark.asyncio
    async def test_list_orders_filter_by_symbol(self, order_service, mock_exchange_adapter):
        """Test filtering orders by symbol."""
        # Create orders for different symbols
        symbols = ["BTC/USDT", "ETH/USDT", "BTC/USDT"]

        for i, symbol in enumerate(symbols):
            exchange_response = ExchangeOrderResponse(
                order_id=f"EXCH_SYMBOL_{i}",
                symbol=symbol,
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                amount=Decimal("0.01"),
                filled=Decimal("0.01"),
                price=None,
                avg_price=Decimal("40000"),
                status=OrderStatus.FILLED,
                created_at=datetime.now(UTC),
                fee=Decimal("0.4"),
                fee_currency="USDT",
            )
            mock_exchange_adapter.place_order = AsyncMock(return_value=exchange_response)

            await order_service.create_order(
                symbol=symbol,
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                amount=Decimal("0.01"),
            )

        # Filter by BTC/USDT
        btc_orders = await order_service.list_orders(symbol="BTC/USDT")

        assert len(btc_orders) == 2
        assert all(o.symbol == "BTC/USDT" for o in btc_orders)

    @pytest.mark.asyncio
    async def test_get_open_orders(self, order_service, mock_exchange_adapter):
        """Test getting open orders."""
        # Create mix of open and closed orders
        statuses = [OrderStatus.SUBMITTED, OrderStatus.PARTIAL, OrderStatus.FILLED]

        for i, status in enumerate(statuses):
            exchange_response = ExchangeOrderResponse(
                order_id=f"EXCH_OPEN_{i}",
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                type=OrderType.LIMIT,
                amount=Decimal("0.01"),
                filled=Decimal("0.01") if status == OrderStatus.FILLED else Decimal("0.005") if status == OrderStatus.PARTIAL else Decimal("0"),
                price=Decimal("40000"),
                avg_price=Decimal("40000") if status == OrderStatus.FILLED else None,
                status=status,
                created_at=datetime.now(UTC),
                fee=Decimal("0"),
                fee_currency="USDT",
            )
            mock_exchange_adapter.place_order = AsyncMock(return_value=exchange_response)

            await order_service.create_order(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                amount=Decimal("0.01"),
                price=Decimal("40000"),
            )

        # Get open orders (should only get SUBMITTED and PARTIAL)
        open_orders = await order_service.get_open_orders()

        assert len(open_orders) == 2
        assert all(o.status in [OrderStatus.SUBMITTED, OrderStatus.PARTIAL] for o in open_orders)


class TestOrderStatistics:
    """Tests for order statistics."""

    @pytest.mark.asyncio
    async def test_count_orders(self, order_service, mock_exchange_adapter):
        """Test counting orders."""
        # Create 3 orders
        for i in range(3):
            exchange_response = ExchangeOrderResponse(
                order_id=f"EXCH_COUNT_{i}",
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                amount=Decimal("0.01"),
                filled=Decimal("0.01"),
                price=None,
                avg_price=Decimal("40000"),
                status=OrderStatus.FILLED,
                created_at=datetime.now(UTC),
                fee=Decimal("0.4"),
                fee_currency="USDT",
            )
            mock_exchange_adapter.place_order = AsyncMock(return_value=exchange_response)

            await order_service.create_order(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                amount=Decimal("0.01"),
            )

        count = await order_service.count_orders()
        assert count == 3

    @pytest.mark.asyncio
    async def test_count_orders_by_status(self, order_service, mock_exchange_adapter):
        """Test counting orders filtered by status."""
        # Create orders with different statuses
        statuses = [OrderStatus.SUBMITTED, OrderStatus.FILLED, OrderStatus.FILLED]

        for i, status in enumerate(statuses):
            exchange_response = ExchangeOrderResponse(
                order_id=f"EXCH_COUNT_STATUS_{i}",
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                type=OrderType.LIMIT,
                amount=Decimal("0.01"),
                filled=Decimal("0.01") if status == OrderStatus.FILLED else Decimal("0"),
                price=Decimal("40000"),
                avg_price=Decimal("40000") if status == OrderStatus.FILLED else None,
                status=status,
                created_at=datetime.now(UTC),
                fee=Decimal("0"),
                fee_currency="USDT",
            )
            mock_exchange_adapter.place_order = AsyncMock(return_value=exchange_response)

            await order_service.create_order(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                amount=Decimal("0.01"),
                price=Decimal("40000"),
            )

        filled_count = await order_service.count_orders(status=OrderStatus.FILLED)
        assert filled_count == 2

    @pytest.mark.asyncio
    async def test_get_order_stats(self, order_service, mock_exchange_adapter):
        """Test getting order statistics by status."""
        # Create orders with various statuses
        statuses = [
            OrderStatus.PENDING,
            OrderStatus.SUBMITTED,
            OrderStatus.SUBMITTED,
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
        ]

        for i, status in enumerate(statuses):
            exchange_response = ExchangeOrderResponse(
                order_id=f"EXCH_STATS_{i}",
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                type=OrderType.LIMIT,
                amount=Decimal("0.01"),
                filled=Decimal("0.01") if status == OrderStatus.FILLED else Decimal("0"),
                price=Decimal("40000"),
                avg_price=Decimal("40000") if status == OrderStatus.FILLED else None,
                status=status,
                created_at=datetime.now(UTC),
                fee=Decimal("0"),
                fee_currency="USDT",
            )
            mock_exchange_adapter.place_order = AsyncMock(return_value=exchange_response)

            await order_service.create_order(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                amount=Decimal("0.01"),
                price=Decimal("40000"),
            )

        stats = await order_service.get_order_stats()

        assert stats["total"] == 5
        assert stats["pending"] == 1
        assert stats["submitted"] == 2
        assert stats["filled"] == 1
        assert stats["cancelled"] == 1
        assert stats["rejected"] == 0


class TestOrderSynchronization:
    """Tests for order synchronization with exchange."""

    @pytest.mark.asyncio
    async def test_sync_order(self, order_service, mock_exchange_adapter):
        """Test syncing order status from exchange."""
        # Create order with SUBMITTED status
        exchange_response = ExchangeOrderResponse(
            order_id="EXCH_SYNC_1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=Decimal("0.01"),
            filled=Decimal("0"),
            price=Decimal("40000"),
            avg_price=None,
            status=OrderStatus.SUBMITTED,
            created_at=datetime.now(UTC),
            fee=Decimal("0"),
            fee_currency="USDT",
        )
        mock_exchange_adapter.place_order = AsyncMock(return_value=exchange_response)

        order = await order_service.create_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            amount=Decimal("0.01"),
            price=Decimal("40000"),
        )

        # Mock exchange get_order to return FILLED status
        filled_response = ExchangeOrderResponse(
            order_id="EXCH_SYNC_1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=Decimal("0.01"),
            filled=Decimal("0.01"),
            price=Decimal("40000"),
            avg_price=Decimal("40000"),
            status=OrderStatus.FILLED,
            created_at=datetime.now(UTC),
            fee=Decimal("0.4"),
            fee_currency="USDT",
        )
        mock_exchange_adapter.get_order = AsyncMock(return_value=filled_response)

        # Sync order
        synced_order = await order_service.sync_order(order.id)

        assert synced_order.status == OrderStatus.FILLED
        assert synced_order.filled == Decimal("0.01")
        assert synced_order.avg_price == Decimal("40000")

    @pytest.mark.skip(reason="sync_open_orders requires complex mock setup with multiple orders")
    @pytest.mark.asyncio
    async def test_sync_open_orders(self, order_service):
        """Test syncing all open orders from exchange."""
        # This test requires complex setup of multiple orders
        # and mocking the exchange's get_open_orders method
        pass
