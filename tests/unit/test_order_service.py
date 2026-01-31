"""Unit tests for order service."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from squant.infra.exchange.exceptions import (
    ExchangeAPIError,
)
from squant.infra.exchange.exceptions import (
    OrderNotFoundError as ExchangeOrderNotFound,
)
from squant.infra.exchange.types import OrderResponse as ExchangeOrderResponse
from squant.models.enums import OrderSide, OrderStatus, OrderType
from squant.models.order import Order
from squant.services.order import (
    OrderNotFoundError,
    OrderRepository,
    OrderService,
    OrderValidationError,
)


class TestOrderRepository:
    """Tests for OrderRepository."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.add = MagicMock()
        return session

    @pytest.fixture
    def repo(self, mock_session: AsyncMock) -> OrderRepository:
        """Create repository with mock session."""
        return OrderRepository(mock_session)

    @pytest.mark.asyncio
    async def test_get_by_exchange_oid(
        self, repo: OrderRepository, mock_session: AsyncMock
    ) -> None:
        """Test finding order by exchange order ID."""
        mock_order = MagicMock(spec=Order)
        mock_order.id = str(uuid4())
        mock_order.exchange = "okx"
        mock_order.exchange_oid = "12345"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_order
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_exchange_oid("okx", "12345")

        assert result is mock_order
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_exchange_oid_not_found(
        self, repo: OrderRepository, mock_session: AsyncMock
    ) -> None:
        """Test finding non-existent order by exchange order ID."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_exchange_oid("okx", "nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_list_by_account(self, repo: OrderRepository, mock_session: AsyncMock) -> None:
        """Test listing orders by account."""
        mock_orders = [MagicMock(spec=Order) for _ in range(3)]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_orders
        mock_session.execute.return_value = mock_result

        account_id = str(uuid4())
        result = await repo.list_by_account(account_id, limit=10)

        assert len(result) == 3
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_by_account_with_status_filter(
        self, repo: OrderRepository, mock_session: AsyncMock
    ) -> None:
        """Test listing orders by account with status filter."""
        mock_orders = [MagicMock(spec=Order)]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_orders
        mock_session.execute.return_value = mock_result

        account_id = str(uuid4())
        result = await repo.list_by_account(account_id, status=OrderStatus.FILLED)

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_open_orders(self, repo: OrderRepository, mock_session: AsyncMock) -> None:
        """Test listing open orders."""
        mock_orders = [MagicMock(spec=Order) for _ in range(2)]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_orders
        mock_session.execute.return_value = mock_result

        account_id = str(uuid4())
        result = await repo.list_open_orders(account_id)

        assert len(result) == 2


class TestOrderService:
    """Tests for OrderService."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.add = MagicMock()
        return session

    @pytest.fixture
    def mock_exchange(self) -> AsyncMock:
        """Create mock exchange adapter."""
        exchange = AsyncMock()
        exchange.name = "okx"
        return exchange

    @pytest.fixture
    def mock_account(self) -> MagicMock:
        """Create mock exchange account."""
        account = MagicMock()
        account.id = str(uuid4())
        account.exchange = "okx"
        return account

    @pytest.fixture
    def service(
        self,
        mock_session: AsyncMock,
        mock_exchange: AsyncMock,
        mock_account: MagicMock,
    ) -> OrderService:
        """Create order service with mocks."""
        return OrderService(mock_session, mock_exchange, mock_account)

    @pytest.mark.asyncio
    async def test_create_order_success(
        self,
        service: OrderService,
        mock_exchange: AsyncMock,
    ) -> None:
        """Test successful order creation."""
        order_id = str(uuid4())

        # Mock repository create
        mock_order = MagicMock(spec=Order)
        mock_order.id = order_id
        mock_order.exchange_oid = None
        mock_order.price = None

        with patch.object(service.order_repo, "create", new_callable=AsyncMock) as mock_create:
            with patch.object(service.order_repo, "update", new_callable=AsyncMock) as mock_update:
                mock_create.return_value = mock_order

                # Mock exchange response
                mock_exchange.place_order.return_value = ExchangeOrderResponse(
                    order_id="exchange-123",
                    symbol="BTC/USDT",
                    side=OrderSide.BUY,
                    type=OrderType.LIMIT,
                    status=OrderStatus.SUBMITTED,
                    price=Decimal("42000"),
                    amount=Decimal("0.1"),
                    filled=Decimal("0"),
                )

                updated_order = MagicMock(spec=Order)
                updated_order.id = order_id
                updated_order.exchange_oid = "exchange-123"
                updated_order.status = OrderStatus.SUBMITTED
                mock_update.return_value = updated_order

                result = await service.create_order(
                    symbol="BTC/USDT",
                    side=OrderSide.BUY,
                    order_type=OrderType.LIMIT,
                    amount=Decimal("0.1"),
                    price=Decimal("42000"),
                )

                assert result.exchange_oid == "exchange-123"
                mock_create.assert_called_once()
                mock_exchange.place_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_order_exchange_failure(
        self,
        service: OrderService,
        mock_exchange: AsyncMock,
    ) -> None:
        """Test order creation when exchange fails."""
        order_id = str(uuid4())

        mock_order = MagicMock(spec=Order)
        mock_order.id = order_id
        mock_order.status = OrderStatus.PENDING

        with patch.object(service.order_repo, "create", new_callable=AsyncMock) as mock_create:
            with patch.object(service.order_repo, "update", new_callable=AsyncMock) as mock_update:
                mock_create.return_value = mock_order

                # Mock exchange failure
                mock_exchange.place_order.side_effect = ExchangeAPIError(
                    code="51000",
                    message="Parameter error",
                    exchange="okx",
                )

                rejected_order = MagicMock(spec=Order)
                rejected_order.id = order_id
                rejected_order.status = OrderStatus.REJECTED
                rejected_order.reject_reason = "Parameter error"
                mock_update.return_value = rejected_order

                with pytest.raises(ExchangeAPIError):
                    await service.create_order(
                        symbol="BTC/USDT",
                        side=OrderSide.BUY,
                        order_type=OrderType.MARKET,
                        amount=Decimal("0.1"),
                    )

                # Order should be marked as rejected
                mock_update.assert_called_once()
                update_kwargs = mock_update.call_args[1]
                assert update_kwargs["status"] == OrderStatus.REJECTED

    @pytest.mark.asyncio
    async def test_create_order_validation_error(
        self,
        service: OrderService,
    ) -> None:
        """Test order creation with invalid parameters."""
        with pytest.raises(OrderValidationError, match="Limit orders require a price"):
            await service.create_order(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                amount=Decimal("0.1"),
                price=None,  # Missing price for limit order
            )

    @pytest.mark.asyncio
    async def test_create_order_negative_amount(
        self,
        service: OrderService,
    ) -> None:
        """Test order creation with negative amount."""
        with pytest.raises(OrderValidationError, match="Amount must be positive"):
            await service.create_order(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                amount=Decimal("-0.1"),
            )

    @pytest.mark.asyncio
    async def test_cancel_order_success(
        self,
        service: OrderService,
        mock_exchange: AsyncMock,
    ) -> None:
        """Test successful order cancellation."""
        order_id = str(uuid4())

        mock_order = MagicMock(spec=Order)
        mock_order.id = order_id
        mock_order.symbol = "BTC/USDT"
        mock_order.exchange_oid = "exchange-123"
        mock_order.status = OrderStatus.SUBMITTED

        with patch.object(service.order_repo, "get", new_callable=AsyncMock) as mock_get:
            with patch.object(service.order_repo, "update", new_callable=AsyncMock) as mock_update:
                mock_get.return_value = mock_order

                mock_exchange.cancel_order.return_value = ExchangeOrderResponse(
                    order_id="exchange-123",
                    symbol="BTC/USDT",
                    side=OrderSide.BUY,
                    type=OrderType.LIMIT,
                    status=OrderStatus.CANCELLED,
                    amount=Decimal("0.1"),
                    filled=Decimal("0"),
                )

                cancelled_order = MagicMock(spec=Order)
                cancelled_order.id = order_id
                cancelled_order.status = OrderStatus.CANCELLED
                mock_update.return_value = cancelled_order

                result = await service.cancel_order(order_id)

                assert result.status == OrderStatus.CANCELLED
                mock_exchange.cancel_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_order_not_found(
        self,
        service: OrderService,
    ) -> None:
        """Test cancelling non-existent order."""
        order_id = str(uuid4())

        with patch.object(service.order_repo, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            with pytest.raises(OrderNotFoundError):
                await service.cancel_order(order_id)

    @pytest.mark.asyncio
    async def test_cancel_order_already_filled(
        self,
        service: OrderService,
    ) -> None:
        """Test cancelling already filled order."""
        order_id = str(uuid4())

        mock_order = MagicMock(spec=Order)
        mock_order.id = order_id
        mock_order.status = OrderStatus.FILLED

        with patch.object(service.order_repo, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_order

            with pytest.raises(OrderValidationError, match="Cannot cancel order with status"):
                await service.cancel_order(order_id)

    @pytest.mark.asyncio
    async def test_cancel_pending_order_without_exchange_oid(
        self,
        service: OrderService,
    ) -> None:
        """Test cancelling order that was never submitted to exchange."""
        order_id = str(uuid4())

        mock_order = MagicMock(spec=Order)
        mock_order.id = order_id
        mock_order.exchange_oid = None
        mock_order.status = OrderStatus.PENDING

        with patch.object(service.order_repo, "get", new_callable=AsyncMock) as mock_get:
            with patch.object(service.order_repo, "update", new_callable=AsyncMock) as mock_update:
                mock_get.return_value = mock_order

                cancelled_order = MagicMock(spec=Order)
                cancelled_order.id = order_id
                cancelled_order.status = OrderStatus.CANCELLED
                mock_update.return_value = cancelled_order

                result = await service.cancel_order(order_id)

                assert result.status == OrderStatus.CANCELLED
                # Should not call exchange
                service.exchange.cancel_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_order_success(
        self,
        service: OrderService,
    ) -> None:
        """Test getting order by ID."""
        order_id = str(uuid4())

        mock_order = MagicMock(spec=Order)
        mock_order.id = order_id

        with patch.object(service.order_repo, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_order

            result = await service.get_order(order_id)

            assert result.id == order_id

    @pytest.mark.asyncio
    async def test_get_order_not_found(
        self,
        service: OrderService,
    ) -> None:
        """Test getting non-existent order."""
        order_id = str(uuid4())

        with patch.object(service.order_repo, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            with pytest.raises(OrderNotFoundError):
                await service.get_order(order_id)

    @pytest.mark.asyncio
    async def test_sync_order_success(
        self,
        service: OrderService,
        mock_exchange: AsyncMock,
    ) -> None:
        """Test syncing order status from exchange."""
        order_id = str(uuid4())

        mock_order = MagicMock(spec=Order)
        mock_order.id = order_id
        mock_order.symbol = "BTC/USDT"
        mock_order.exchange_oid = "exchange-123"
        mock_order.status = OrderStatus.SUBMITTED
        mock_order.price = Decimal("42000")

        with patch.object(service.order_repo, "get", new_callable=AsyncMock) as mock_get:
            with patch.object(service.order_repo, "update", new_callable=AsyncMock) as mock_update:
                mock_get.return_value = mock_order

                mock_exchange.get_order.return_value = ExchangeOrderResponse(
                    order_id="exchange-123",
                    symbol="BTC/USDT",
                    side=OrderSide.BUY,
                    type=OrderType.LIMIT,
                    status=OrderStatus.FILLED,
                    price=Decimal("42000"),
                    amount=Decimal("0.1"),
                    filled=Decimal("0.1"),
                    avg_price=Decimal("41998.5"),
                )

                filled_order = MagicMock(spec=Order)
                filled_order.id = order_id
                filled_order.status = OrderStatus.FILLED
                filled_order.filled = Decimal("0.1")
                filled_order.avg_price = Decimal("41998.5")
                mock_update.return_value = filled_order

                result = await service.sync_order(order_id)

                assert result.status == OrderStatus.FILLED
                assert result.filled == Decimal("0.1")
                mock_exchange.get_order.assert_called_once_with("BTC/USDT", "exchange-123")

    @pytest.mark.asyncio
    async def test_sync_order_not_found_on_exchange(
        self,
        service: OrderService,
        mock_exchange: AsyncMock,
    ) -> None:
        """Test syncing order that doesn't exist on exchange."""
        order_id = str(uuid4())

        mock_order = MagicMock(spec=Order)
        mock_order.id = order_id
        mock_order.symbol = "BTC/USDT"
        mock_order.exchange_oid = "exchange-123"
        mock_order.status = OrderStatus.PENDING

        with patch.object(service.order_repo, "get", new_callable=AsyncMock) as mock_get:
            with patch.object(service.order_repo, "update", new_callable=AsyncMock) as mock_update:
                mock_get.return_value = mock_order

                mock_exchange.get_order.side_effect = ExchangeOrderNotFound(
                    message="Order does not exist",
                    exchange="okx",
                    order_id="exchange-123",
                )

                rejected_order = MagicMock(spec=Order)
                rejected_order.id = order_id
                rejected_order.status = OrderStatus.REJECTED
                mock_update.return_value = rejected_order

                await service.sync_order(order_id)

                # Should mark as rejected
                mock_update.assert_called_once()
                update_kwargs = mock_update.call_args[1]
                assert update_kwargs["status"] == OrderStatus.REJECTED

    @pytest.mark.asyncio
    async def test_list_orders(
        self,
        service: OrderService,
        mock_account: MagicMock,
    ) -> None:
        """Test listing orders with filters."""
        mock_orders = [MagicMock(spec=Order) for _ in range(5)]

        with patch.object(
            service.order_repo, "list_by_account", new_callable=AsyncMock
        ) as mock_list:
            mock_list.return_value = mock_orders

            result = await service.list_orders(
                status=OrderStatus.FILLED,
                symbol="BTC/USDT",
                limit=10,
            )

            assert len(result) == 5
            mock_list.assert_called_once_with(
                mock_account.id,
                status=OrderStatus.FILLED,
                symbol="BTC/USDT",
                side=None,
                start_time=None,
                end_time=None,
                offset=0,
                limit=10,
            )

    @pytest.mark.asyncio
    async def test_get_open_orders(
        self,
        service: OrderService,
        mock_account: MagicMock,
    ) -> None:
        """Test getting open orders."""
        mock_orders = [MagicMock(spec=Order) for _ in range(2)]

        with patch.object(
            service.order_repo, "list_open_orders", new_callable=AsyncMock
        ) as mock_list:
            mock_list.return_value = mock_orders

            result = await service.get_open_orders(symbol="ETH/USDT")

            assert len(result) == 2
            mock_list.assert_called_once_with(mock_account.id, symbol="ETH/USDT")

    @pytest.mark.asyncio
    async def test_count_orders(
        self,
        service: OrderService,
        mock_account: MagicMock,
    ) -> None:
        """Test counting orders."""
        with patch.object(
            service.order_repo, "count_by_account", new_callable=AsyncMock
        ) as mock_count:
            mock_count.return_value = 42

            result = await service.count_orders(status=OrderStatus.FILLED)

            assert result == 42
            mock_count.assert_called_once_with(mock_account.id, status=OrderStatus.FILLED)

    @pytest.mark.asyncio
    async def test_get_order_stats(
        self,
        service: OrderService,
        mock_account: MagicMock,
    ) -> None:
        """Test getting order stats with single aggregated query."""
        with patch.object(
            service.order_repo, "get_stats_by_status", new_callable=AsyncMock
        ) as mock_stats:
            mock_stats.return_value = {
                OrderStatus.PENDING: 5,
                OrderStatus.SUBMITTED: 3,
                OrderStatus.PARTIAL: 2,
                OrderStatus.FILLED: 10,
                OrderStatus.CANCELLED: 4,
                OrderStatus.REJECTED: 1,
            }

            result = await service.get_order_stats()

            assert result["total"] == 25
            assert result["pending"] == 5
            assert result["submitted"] == 3
            assert result["partial"] == 2
            assert result["filled"] == 10
            assert result["cancelled"] == 4
            assert result["rejected"] == 1
            mock_stats.assert_called_once_with(mock_account.id)


class TestOrderValidation:
    """Tests for order validation."""

    def test_order_not_found_error_message(self) -> None:
        """Test OrderNotFoundError message."""
        order_id = str(uuid4())
        error = OrderNotFoundError(order_id)

        assert order_id in str(error)
        assert error.order_id == order_id

    def test_order_validation_error(self) -> None:
        """Test OrderValidationError."""
        error = OrderValidationError("Invalid order")

        assert "Invalid order" in str(error)
