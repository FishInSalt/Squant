"""Unit tests for order schemas."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from squant.models.enums import OrderSide, OrderStatus, OrderType
from squant.schemas.order import (
    CreateOrderRequest,
    ListOrdersRequest,
    OrderDetail,
    OrderListData,
    OrderStatsResponse,
    OrderWithTrades,
    SyncOrdersResponse,
    TradeDetail,
)


class TestCreateOrderRequest:
    """Tests for CreateOrderRequest schema."""

    def test_valid_market_order(self):
        """Test creating a valid market order request."""
        request = CreateOrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.1"),
        )

        assert request.symbol == "BTC/USDT"
        assert request.side == OrderSide.BUY
        assert request.type == OrderType.MARKET
        assert request.amount == Decimal("0.1")
        assert request.price is None

    def test_valid_limit_order(self):
        """Test creating a valid limit order request."""
        request = CreateOrderRequest(
            symbol="ETH/USDT",
            side=OrderSide.SELL,
            type=OrderType.LIMIT,
            amount=Decimal("1.5"),
            price=Decimal("2500.00"),
        )

        assert request.type == OrderType.LIMIT
        assert request.price == Decimal("2500.00")

    def test_with_client_order_id(self):
        """Test creating order with client order ID."""
        request = CreateOrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.1"),
            client_order_id="my-order-123",
        )

        assert request.client_order_id == "my-order-123"

    def test_with_run_id(self):
        """Test creating order with strategy run ID."""
        run_id = uuid4()
        request = CreateOrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.1"),
            run_id=run_id,
        )

        assert request.run_id == run_id

    def test_amount_must_be_positive(self):
        """Test amount must be greater than 0."""
        with pytest.raises(ValidationError) as exc_info:
            CreateOrderRequest(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                amount=Decimal("0"),
            )

        assert "amount" in str(exc_info.value)

    def test_negative_amount_fails(self):
        """Test negative amount fails validation."""
        with pytest.raises(ValidationError):
            CreateOrderRequest(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                amount=Decimal("-0.1"),
            )

    def test_symbol_required(self):
        """Test symbol is required."""
        with pytest.raises(ValidationError):
            CreateOrderRequest(
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                amount=Decimal("0.1"),
            )

    def test_client_order_id_max_length(self):
        """Test client order ID max length."""
        with pytest.raises(ValidationError):
            CreateOrderRequest(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                amount=Decimal("0.1"),
                client_order_id="x" * 33,
            )


class TestOrderDetail:
    """Tests for OrderDetail schema."""

    def test_full_order_detail(self):
        """Test creating full order detail."""
        now = datetime.now(UTC)
        detail = OrderDetail(
            id=uuid4(),
            account_id=uuid4(),
            run_id=uuid4(),
            exchange="okx",
            exchange_oid="12345",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            status=OrderStatus.FILLED,
            price=Decimal("50000"),
            amount=Decimal("0.1"),
            filled=Decimal("0.1"),
            avg_price=Decimal("50010"),
            reject_reason=None,
            created_at=now,
            updated_at=now,
        )

        assert detail.symbol == "BTC/USDT"
        assert detail.status == OrderStatus.FILLED
        assert detail.filled == Decimal("0.1")

    def test_optional_fields(self):
        """Test optional fields can be None."""
        now = datetime.now(UTC)
        detail = OrderDetail(
            id=uuid4(),
            account_id=uuid4(),
            run_id=None,
            exchange="okx",
            exchange_oid=None,
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            status=OrderStatus.PENDING,
            price=None,
            amount=Decimal("0.1"),
            filled=Decimal("0"),
            avg_price=None,
            reject_reason=None,
            created_at=now,
            updated_at=now,
        )

        assert detail.run_id is None
        assert detail.exchange_oid is None
        assert detail.price is None

    def test_from_attributes_config(self):
        """Test model has from_attributes config."""
        assert OrderDetail.model_config.get("from_attributes") is True


class TestTradeDetail:
    """Tests for TradeDetail schema."""

    def test_full_trade_detail(self):
        """Test creating full trade detail."""
        now = datetime.now(UTC)
        trade = TradeDetail(
            id=uuid4(),
            order_id=uuid4(),
            exchange_tid="trade-123",
            price=Decimal("50000"),
            amount=Decimal("0.1"),
            fee=Decimal("0.0001"),
            fee_currency="BTC",
            timestamp=now,
        )

        assert trade.price == Decimal("50000")
        assert trade.fee == Decimal("0.0001")
        assert trade.fee_currency == "BTC"

    def test_optional_fields(self):
        """Test optional fields."""
        now = datetime.now(UTC)
        trade = TradeDetail(
            id=uuid4(),
            order_id=uuid4(),
            exchange_tid=None,
            price=Decimal("50000"),
            amount=Decimal("0.1"),
            fee=Decimal("0.0001"),
            fee_currency=None,
            timestamp=now,
        )

        assert trade.exchange_tid is None
        assert trade.fee_currency is None


class TestOrderWithTrades:
    """Tests for OrderWithTrades schema."""

    def test_order_with_trades(self):
        """Test order with trades list."""
        now = datetime.now(UTC)
        order = OrderWithTrades(
            id=uuid4(),
            account_id=uuid4(),
            run_id=None,
            exchange="okx",
            exchange_oid="12345",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            status=OrderStatus.FILLED,
            price=None,
            amount=Decimal("0.1"),
            filled=Decimal("0.1"),
            avg_price=Decimal("50000"),
            reject_reason=None,
            created_at=now,
            updated_at=now,
            trades=[
                TradeDetail(
                    id=uuid4(),
                    order_id=uuid4(),
                    exchange_tid="t1",
                    price=Decimal("50000"),
                    amount=Decimal("0.05"),
                    fee=Decimal("0.00005"),
                    fee_currency="BTC",
                    timestamp=now,
                ),
                TradeDetail(
                    id=uuid4(),
                    order_id=uuid4(),
                    exchange_tid="t2",
                    price=Decimal("50000"),
                    amount=Decimal("0.05"),
                    fee=Decimal("0.00005"),
                    fee_currency="BTC",
                    timestamp=now,
                ),
            ],
        )

        assert len(order.trades) == 2

    def test_default_empty_trades(self):
        """Test default empty trades list."""
        now = datetime.now(UTC)
        order = OrderWithTrades(
            id=uuid4(),
            account_id=uuid4(),
            run_id=None,
            exchange="okx",
            exchange_oid="12345",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            status=OrderStatus.PENDING,
            price=None,
            amount=Decimal("0.1"),
            filled=Decimal("0"),
            avg_price=None,
            reject_reason=None,
            created_at=now,
            updated_at=now,
        )

        assert order.trades == []


class TestListOrdersRequest:
    """Tests for ListOrdersRequest schema."""

    def test_default_values(self):
        """Test default pagination values."""
        request = ListOrdersRequest()

        assert request.status is None
        assert request.symbol is None
        assert request.side is None
        assert request.start_time is None
        assert request.end_time is None
        assert request.page == 1
        assert request.page_size == 20

    def test_with_filters(self):
        """Test request with filters."""
        now = datetime.now(UTC)
        request = ListOrdersRequest(
            status=[OrderStatus.FILLED, OrderStatus.PARTIAL],
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            start_time=now,
            end_time=now,
            page=2,
            page_size=50,
        )

        assert len(request.status) == 2
        assert request.symbol == "BTC/USDT"
        assert request.page == 2
        assert request.page_size == 50

    def test_page_min_value(self):
        """Test page minimum value."""
        with pytest.raises(ValidationError):
            ListOrdersRequest(page=0)

    def test_page_size_max_value(self):
        """Test page size maximum value."""
        with pytest.raises(ValidationError):
            ListOrdersRequest(page_size=101)

    def test_page_size_min_value(self):
        """Test page size minimum value."""
        with pytest.raises(ValidationError):
            ListOrdersRequest(page_size=0)


class TestOrderListData:
    """Tests for OrderListData schema."""

    def test_empty_list(self):
        """Test empty order list."""
        data = OrderListData(items=[], total=0, page=1, page_size=20)

        assert len(data.items) == 0
        assert data.total == 0

    def test_with_orders(self):
        """Test list with orders."""
        now = datetime.now(UTC)
        order = OrderDetail(
            id=uuid4(),
            account_id=uuid4(),
            run_id=None,
            exchange="okx",
            exchange_oid="12345",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            status=OrderStatus.FILLED,
            price=None,
            amount=Decimal("0.1"),
            filled=Decimal("0.1"),
            avg_price=Decimal("50000"),
            reject_reason=None,
            created_at=now,
            updated_at=now,
        )

        data = OrderListData(items=[order], total=100, page=1, page_size=20)

        assert len(data.items) == 1
        assert data.total == 100


class TestSyncOrdersResponse:
    """Tests for SyncOrdersResponse schema."""

    def test_sync_response(self):
        """Test sync orders response."""
        now = datetime.now(UTC)
        order = OrderDetail(
            id=uuid4(),
            account_id=uuid4(),
            run_id=None,
            exchange="okx",
            exchange_oid="12345",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            status=OrderStatus.FILLED,
            price=None,
            amount=Decimal("0.1"),
            filled=Decimal("0.1"),
            avg_price=Decimal("50000"),
            reject_reason=None,
            created_at=now,
            updated_at=now,
        )

        response = SyncOrdersResponse(synced_count=5, orders=[order])

        assert response.synced_count == 5
        assert len(response.orders) == 1


class TestOrderStatsResponse:
    """Tests for OrderStatsResponse schema."""

    def test_stats_response(self):
        """Test order stats response."""
        stats = OrderStatsResponse(
            total=100,
            pending=5,
            submitted=10,
            partial=3,
            filled=70,
            cancelled=10,
            rejected=2,
        )

        assert stats.total == 100
        assert stats.filled == 70
        assert (
            stats.pending
            + stats.submitted
            + stats.partial
            + stats.filled
            + stats.cancelled
            + stats.rejected
            <= stats.total
        )

    def test_all_fields_required(self):
        """Test all fields are required."""
        with pytest.raises(ValidationError):
            OrderStatsResponse(total=100)
