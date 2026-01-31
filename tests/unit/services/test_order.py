"""Unit tests for order service."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from squant.infra.exchange.exceptions import OrderNotFoundError as ExchangeOrderNotFound
from squant.infra.exchange.types import OrderResponse as ExchangeOrderResponse
from squant.models.enums import OrderSide, OrderStatus, OrderType
from squant.models.order import Order, Trade
from squant.services.order import (
    OrderNotFoundError,
    OrderRepository,
    OrderService,
    OrderValidationError,
    TradeRepository,
)


class TestOrderNotFoundError:
    """Tests for OrderNotFoundError exception."""

    def test_error_message(self):
        """Test error message contains order ID."""
        order_id = uuid4()
        error = OrderNotFoundError(order_id)

        assert str(order_id) in str(error)
        assert error.order_id == str(order_id)

    def test_string_id(self):
        """Test works with string ID."""
        error = OrderNotFoundError("test-order-id")

        assert "test-order-id" in str(error)


class TestOrderValidationError:
    """Tests for OrderValidationError exception."""

    def test_error_message(self):
        """Test error message."""
        error = OrderValidationError("Invalid amount")

        assert "Invalid amount" in str(error)


class TestOrderRepository:
    """Tests for OrderRepository."""

    @pytest.fixture
    def mock_session(self):
        """Create mock async session."""
        session = MagicMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.fixture
    def repository(self, mock_session):
        """Create repository with mock session."""
        return OrderRepository(mock_session)

    @pytest.fixture
    def sample_order(self):
        """Create sample order model."""
        order = MagicMock(spec=Order)
        order.id = uuid4()
        order.account_id = str(uuid4())
        order.exchange = "okx"
        order.exchange_oid = "exc-123"
        order.symbol = "BTC/USDT"
        order.side = OrderSide.BUY
        order.type = OrderType.LIMIT
        order.amount = Decimal("0.1")
        order.price = Decimal("50000")
        order.status = OrderStatus.PENDING
        order.created_at = datetime.now(UTC)
        return order

    @pytest.mark.asyncio
    async def test_get_by_exchange_oid_found(self, repository, mock_session, sample_order):
        """Test getting order by exchange order ID."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_order
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_exchange_oid("okx", "exc-123")

        assert result == sample_order

    @pytest.mark.asyncio
    async def test_get_by_exchange_oid_not_found(self, repository, mock_session):
        """Test getting nonexistent order by exchange order ID."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_exchange_oid("okx", "nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_list_by_account(self, repository, mock_session, sample_order):
        """Test listing orders by account."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_order]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.list_by_account(sample_order.account_id)

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_by_account_with_filters(self, repository, mock_session, sample_order):
        """Test listing orders with all filters."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_order]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        now = datetime.now(UTC)
        result = await repository.list_by_account(
            sample_order.account_id,
            status=OrderStatus.PENDING,
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            start_time=now,
            end_time=now,
            offset=0,
            limit=10,
        )

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_by_account_with_status_list(self, repository, mock_session, sample_order):
        """Test listing orders with status list filter."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_order]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.list_by_account(
            sample_order.account_id,
            status=[OrderStatus.PENDING, OrderStatus.SUBMITTED],
        )

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_open_orders(self, repository, mock_session, sample_order):
        """Test listing open orders."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_order]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.list_open_orders(sample_order.account_id)

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_count_by_account(self, repository, mock_session):
        """Test counting orders by account."""
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 5
        mock_session.execute.return_value = mock_result

        result = await repository.count_by_account(uuid4())

        assert result == 5

    @pytest.mark.asyncio
    async def test_count_by_account_with_status(self, repository, mock_session):
        """Test counting orders with status filter."""
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 3
        mock_session.execute.return_value = mock_result

        result = await repository.count_by_account(uuid4(), status=OrderStatus.FILLED)

        assert result == 3

    @pytest.mark.asyncio
    async def test_get_stats_by_status(self, repository, mock_session):
        """Test getting order stats by status."""
        mock_result = MagicMock()
        mock_result.all.return_value = [
            (OrderStatus.FILLED, 10),
            (OrderStatus.PENDING, 5),
        ]
        mock_session.execute.return_value = mock_result

        result = await repository.get_stats_by_status(uuid4())

        assert result[OrderStatus.FILLED] == 10
        assert result[OrderStatus.PENDING] == 5


class TestTradeRepository:
    """Tests for TradeRepository."""

    @pytest.fixture
    def mock_session(self):
        """Create mock async session."""
        session = MagicMock()
        session.execute = AsyncMock()
        return session

    @pytest.fixture
    def repository(self, mock_session):
        """Create repository with mock session."""
        return TradeRepository(mock_session)

    @pytest.fixture
    def sample_trade(self):
        """Create sample trade model."""
        trade = MagicMock(spec=Trade)
        trade.id = uuid4()
        trade.order_id = str(uuid4())
        trade.price = Decimal("50000")
        trade.amount = Decimal("0.1")
        trade.timestamp = datetime.now(UTC)
        return trade

    @pytest.mark.asyncio
    async def test_list_by_order(self, repository, mock_session, sample_trade):
        """Test listing trades by order."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_trade]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.list_by_order(sample_trade.order_id)

        assert len(result) == 1
        assert result[0] == sample_trade


class TestOrderService:
    """Tests for OrderService."""

    @pytest.fixture
    def mock_session(self):
        """Create mock async session."""
        session = MagicMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.fixture
    def mock_exchange(self):
        """Create mock exchange adapter."""
        exchange = MagicMock()
        exchange.place_order = AsyncMock()
        exchange.cancel_order = AsyncMock()
        exchange.get_order = AsyncMock()
        exchange.get_open_orders = AsyncMock()
        return exchange

    @pytest.fixture
    def mock_account(self):
        """Create mock exchange account."""
        account = MagicMock()
        account.id = uuid4()
        account.exchange = "okx"
        return account

    @pytest.fixture
    def service(self, mock_session, mock_exchange, mock_account):
        """Create service with mocks."""
        return OrderService(mock_session, mock_exchange, mock_account)

    @pytest.fixture
    def sample_order(self, mock_account):
        """Create sample order model."""
        order = MagicMock(spec=Order)
        order.id = uuid4()
        order.account_id = str(mock_account.id)
        order.exchange = "okx"
        order.exchange_oid = "exc-123"
        order.symbol = "BTC/USDT"
        order.side = OrderSide.BUY
        order.type = OrderType.LIMIT
        order.amount = Decimal("0.1")
        order.price = Decimal("50000")
        order.status = OrderStatus.PENDING
        order.created_at = datetime.now(UTC)
        return order

    @pytest.fixture
    def exchange_response(self):
        """Create exchange order response."""
        return ExchangeOrderResponse(
            order_id="exc-123",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            status=OrderStatus.SUBMITTED,
            price=Decimal("50000"),
            amount=Decimal("0.1"),
            filled=Decimal("0"),
        )

    @pytest.mark.asyncio
    async def test_create_order_success(self, service, sample_order, exchange_response):
        """Test successful order creation."""
        service.order_repo.create = AsyncMock(return_value=sample_order)
        service.order_repo.update = AsyncMock(return_value=sample_order)
        service.exchange.place_order.return_value = exchange_response

        result = await service.create_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            amount=Decimal("0.1"),
            price=Decimal("50000"),
        )

        assert result == sample_order
        service.order_repo.create.assert_called_once()
        service.exchange.place_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_order_limit_requires_price(self, service):
        """Test limit order requires price."""
        with pytest.raises(OrderValidationError, match="price"):
            await service.create_order(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                amount=Decimal("0.1"),
                price=None,
            )

    @pytest.mark.asyncio
    async def test_create_order_amount_positive(self, service):
        """Test amount must be positive."""
        with pytest.raises(OrderValidationError, match="positive"):
            await service.create_order(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                amount=Decimal("0"),
            )

    @pytest.mark.asyncio
    async def test_create_order_negative_amount(self, service):
        """Test negative amount fails."""
        with pytest.raises(OrderValidationError, match="positive"):
            await service.create_order(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                amount=Decimal("-1"),
            )

    @pytest.mark.asyncio
    async def test_create_order_exchange_error(self, service, sample_order):
        """Test order is rejected on exchange error."""
        service.order_repo.create = AsyncMock(return_value=sample_order)
        service.order_repo.update = AsyncMock(return_value=sample_order)
        service.exchange.place_order.side_effect = Exception("Exchange error")

        with pytest.raises(Exception, match="Exchange error"):
            await service.create_order(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                amount=Decimal("0.1"),
            )

        # Order should be marked as rejected
        service.order_repo.update.assert_called()
        call_kwargs = service.order_repo.update.call_args[1]
        assert call_kwargs["status"] == OrderStatus.REJECTED

    @pytest.mark.asyncio
    async def test_cancel_order_success(self, service, sample_order, exchange_response):
        """Test successful order cancellation."""
        exchange_response.status = OrderStatus.CANCELLED
        service.order_repo.get = AsyncMock(return_value=sample_order)
        service.order_repo.update = AsyncMock(return_value=sample_order)
        service.exchange.cancel_order.return_value = exchange_response

        result = await service.cancel_order(sample_order.id)

        assert result == sample_order
        service.exchange.cancel_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_order_not_found(self, service):
        """Test cancel fails when order not found."""
        service.order_repo.get = AsyncMock(return_value=None)

        with pytest.raises(OrderNotFoundError):
            await service.cancel_order(uuid4())

    @pytest.mark.asyncio
    async def test_cancel_order_already_filled(self, service, sample_order):
        """Test cannot cancel filled order."""
        sample_order.status = OrderStatus.FILLED
        service.order_repo.get = AsyncMock(return_value=sample_order)

        with pytest.raises(OrderValidationError, match="Cannot cancel"):
            await service.cancel_order(sample_order.id)

    @pytest.mark.asyncio
    async def test_cancel_order_no_exchange_oid(self, service, sample_order):
        """Test cancelling order without exchange ID."""
        sample_order.exchange_oid = None
        service.order_repo.get = AsyncMock(return_value=sample_order)
        service.order_repo.update = AsyncMock(return_value=sample_order)

        await service.cancel_order(sample_order.id)

        # Should just mark as cancelled without calling exchange
        service.exchange.cancel_order.assert_not_called()
        service.order_repo.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_order_success(self, service, sample_order):
        """Test getting order by ID."""
        service.order_repo.get = AsyncMock(return_value=sample_order)

        result = await service.get_order(sample_order.id)

        assert result == sample_order

    @pytest.mark.asyncio
    async def test_get_order_not_found(self, service):
        """Test get fails when order not found."""
        service.order_repo.get = AsyncMock(return_value=None)

        with pytest.raises(OrderNotFoundError):
            await service.get_order(uuid4())

    @pytest.mark.asyncio
    async def test_get_order_by_exchange_oid(self, service, sample_order):
        """Test getting order by exchange order ID."""
        service.order_repo.get_by_exchange_oid = AsyncMock(return_value=sample_order)

        result = await service.get_order_by_exchange_oid("exc-123")

        assert result == sample_order

    @pytest.mark.asyncio
    async def test_get_order_by_exchange_oid_not_found(self, service):
        """Test get by exchange oid fails when not found."""
        service.order_repo.get_by_exchange_oid = AsyncMock(return_value=None)

        with pytest.raises(OrderNotFoundError):
            await service.get_order_by_exchange_oid("nonexistent")

    @pytest.mark.asyncio
    async def test_sync_order_success(self, service, sample_order, exchange_response):
        """Test syncing order from exchange."""
        service.order_repo.get = AsyncMock(return_value=sample_order)
        service.order_repo.update = AsyncMock(return_value=sample_order)
        service.exchange.get_order.return_value = exchange_response

        result = await service.sync_order(sample_order.id)

        assert result == sample_order
        service.exchange.get_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_order_not_found_in_db(self, service):
        """Test sync fails when order not found in database."""
        service.order_repo.get = AsyncMock(return_value=None)

        with pytest.raises(OrderNotFoundError):
            await service.sync_order(uuid4())

    @pytest.mark.asyncio
    async def test_sync_order_no_exchange_oid(self, service, sample_order):
        """Test sync returns order when no exchange ID."""
        sample_order.exchange_oid = None
        service.order_repo.get = AsyncMock(return_value=sample_order)

        result = await service.sync_order(sample_order.id)

        assert result == sample_order
        service.exchange.get_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_order_not_found_on_exchange(self, service, sample_order):
        """Test sync handles order not found on exchange."""
        service.order_repo.get = AsyncMock(return_value=sample_order)
        service.order_repo.update = AsyncMock(return_value=sample_order)
        service.exchange.get_order.side_effect = ExchangeOrderNotFound("exc-123")

        await service.sync_order(sample_order.id)

        # Should mark as rejected
        service.order_repo.update.assert_called_once()
        call_kwargs = service.order_repo.update.call_args[1]
        assert call_kwargs["status"] == OrderStatus.REJECTED

    @pytest.mark.asyncio
    async def test_list_orders(self, service, sample_order):
        """Test listing orders."""
        service.order_repo.list_by_account = AsyncMock(return_value=[sample_order])

        result = await service.list_orders(symbol="BTC/USDT")

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_open_orders(self, service, sample_order):
        """Test getting open orders."""
        service.order_repo.list_open_orders = AsyncMock(return_value=[sample_order])

        result = await service.get_open_orders()

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_count_orders(self, service):
        """Test counting orders."""
        service.order_repo.count_by_account = AsyncMock(return_value=10)

        result = await service.count_orders()

        assert result == 10

    @pytest.mark.asyncio
    async def test_get_order_stats(self, service):
        """Test getting order stats."""
        service.order_repo.get_stats_by_status = AsyncMock(
            return_value={
                OrderStatus.FILLED: 10,
                OrderStatus.PENDING: 5,
                OrderStatus.CANCELLED: 3,
            }
        )

        result = await service.get_order_stats()

        assert result["total"] == 18
        assert result["filled"] == 10
        assert result["pending"] == 5
        assert result["cancelled"] == 3
        assert result["submitted"] == 0

    @pytest.mark.asyncio
    async def test_sync_open_orders(self, service, sample_order, exchange_response):
        """Test syncing open orders from exchange."""
        service.exchange.get_open_orders.return_value = [exchange_response]
        service.order_repo.list_open_orders = AsyncMock(return_value=[sample_order])
        service.order_repo.update = AsyncMock(return_value=sample_order)

        result = await service.sync_open_orders()

        assert len(result) == 1
