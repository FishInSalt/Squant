"""Tests for recovery order reconciliation in LiveTradingService (B4).

When a session resumes after a crash, orders may have been placed on the
exchange but never recorded in our DB (if the crash happened during
adapter.place_order()). These tests verify the reconciliation step that
finds and recovers those missing orders.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from squant.infra.exchange.types import OrderResponse, TradeInfo
from squant.models.enums import OrderSide, OrderStatus, OrderType
from squant.services.live_trading import LiveTradingService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session():
    """Create a mock DB session."""
    return AsyncMock()


@pytest.fixture
def service(mock_session):
    """Create a LiveTradingService with mock session."""
    return LiveTradingService(mock_session)


@pytest.fixture
def mock_adapter():
    """Create a mock exchange adapter."""
    adapter = AsyncMock()
    adapter.get_orders = AsyncMock(return_value=[])
    adapter.get_order_trades = AsyncMock(return_value=[])
    return adapter


def _make_exchange_order(
    order_id: str = "ex-order-1",
    symbol: str = "BTC/USDT",
    side: OrderSide = OrderSide.BUY,
    order_type: OrderType = OrderType.LIMIT,
    status: OrderStatus = OrderStatus.FILLED,
    price: Decimal | None = Decimal("50000"),
    amount: Decimal = Decimal("0.1"),
    filled: Decimal = Decimal("0.1"),
    avg_price: Decimal | None = Decimal("50000"),
) -> OrderResponse:
    """Build an OrderResponse from the exchange."""
    return OrderResponse(
        order_id=order_id,
        symbol=symbol,
        side=side,
        type=order_type,
        status=status,
        price=price,
        amount=amount,
        filled=filled,
        avg_price=avg_price,
    )


def _make_db_order(exchange_oid: str | None = "ex-order-1", order_id: str = "db-uuid-1"):
    """Build a mock DB order object."""
    order = MagicMock()
    order.exchange_oid = exchange_oid
    order.id = order_id
    return order


def _make_trade_info(
    trade_id: str = "fill-1",
    order_id: str = "ex-order-1",
    symbol: str = "BTC/USDT",
    side: str = "buy",
    price: Decimal = Decimal("50000"),
    amount: Decimal = Decimal("0.1"),
    fee: Decimal = Decimal("0.05"),
    fee_currency: str = "USDT",
    taker_or_maker: str | None = "taker",
    timestamp: datetime | None = None,
) -> TradeInfo:
    """Build a TradeInfo fill record."""
    return TradeInfo(
        trade_id=trade_id,
        order_id=order_id,
        symbol=symbol,
        side=side,
        price=price,
        amount=amount,
        fee=fee,
        fee_currency=fee_currency,
        taker_or_maker=taker_or_maker,
        timestamp=timestamp or datetime.now(UTC),
    )


def _make_session_context_mock(mock_order_repo, mock_trade_repo):
    """Create a mock get_session_context that injects our mock repos.

    Patches get_session_context at the source module (squant.infra.database)
    so that the local import inside _reconcile_missing_orders picks it up.
    Also patches OrderRepository and TradeRepository at their source module
    (squant.services.order).
    """
    mock_db_session = AsyncMock()

    @asynccontextmanager
    async def fake_session_context():
        yield mock_db_session

    return (
        patch("squant.infra.database.get_session_context", fake_session_context),
        patch("squant.services.order.OrderRepository", return_value=mock_order_repo),
        patch("squant.services.order.TradeRepository", return_value=mock_trade_repo),
    )


# ---------------------------------------------------------------------------
# _compute_reconciliation_since tests
# ---------------------------------------------------------------------------


class TestComputeReconciliationSince:
    """Tests for _compute_reconciliation_since static method."""

    def test_compute_since_with_last_bar_time(self):
        """When last_bar_time is provided, result is last_bar_time minus one bar interval."""
        last_bar = datetime(2026, 3, 24, 12, 0, 0, tzinfo=UTC)
        result = LiveTradingService._compute_reconciliation_since(
            last_bar_time=last_bar,
            timeframe="1h",
        )
        expected = last_bar - timedelta(hours=1)
        assert result == expected

    def test_compute_since_with_5m_timeframe(self):
        """Verify 5m timeframe maps to 5-minute interval."""
        last_bar = datetime(2026, 3, 24, 12, 30, 0, tzinfo=UTC)
        result = LiveTradingService._compute_reconciliation_since(
            last_bar_time=last_bar,
            timeframe="5m",
        )
        expected = last_bar - timedelta(minutes=5)
        assert result == expected

    def test_compute_since_fallback_to_started_at(self):
        """When no last_bar_time, falls back to the provided fallback datetime."""
        fallback = datetime(2026, 3, 24, 10, 0, 0, tzinfo=UTC)
        result = LiveTradingService._compute_reconciliation_since(
            last_bar_time=None,
            timeframe="1h",
            fallback=fallback,
        )
        assert result == fallback

    def test_compute_since_fallback_to_24h(self):
        """When no last_bar_time and no fallback, defaults to ~24h ago."""
        before = datetime.now(UTC) - timedelta(hours=24, seconds=5)
        result = LiveTradingService._compute_reconciliation_since(
            last_bar_time=None,
            timeframe="1h",
            fallback=None,
        )
        after = datetime.now(UTC) - timedelta(hours=23, minutes=59, seconds=55)
        assert before <= result <= after

    def test_compute_since_unknown_timeframe_defaults_to_1h(self):
        """Unknown timeframe falls back to 1h interval."""
        last_bar = datetime(2026, 3, 24, 12, 0, 0, tzinfo=UTC)
        result = LiveTradingService._compute_reconciliation_since(
            last_bar_time=last_bar,
            timeframe="unknown_tf",
        )
        expected = last_bar - timedelta(hours=1)
        assert result == expected


# ---------------------------------------------------------------------------
# _reconcile_missing_orders tests
# ---------------------------------------------------------------------------


class TestReconcileMissingOrders:
    """Tests for _reconcile_missing_orders method."""

    async def test_no_missing_orders(self, service, mock_adapter):
        """When all exchange orders are already in DB, nothing is recovered."""
        # Exchange returns one order
        ex_order = _make_exchange_order(order_id="ex-order-1")
        mock_adapter.get_orders = AsyncMock(return_value=[ex_order])

        # DB already has that order
        db_orders = [_make_db_order(exchange_oid="ex-order-1")]

        report = await service._reconcile_missing_orders(
            adapter=mock_adapter,
            run_id="run-123",
            account_id="acc-456",
            exchange="okx",
            symbol="BTC/USDT",
            db_orders=db_orders,
            since=datetime.now(UTC) - timedelta(hours=1),

        )

        assert report["missing_orders_found"] == 0
        assert report["missing_orders_recovered"] == 0
        assert report["errors"] == []

    async def test_missing_order_recovered(self, service, mock_adapter):
        """Exchange has an order not in DB -- it should be created."""
        ex_order = _make_exchange_order(
            order_id="ex-missing-1",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            status=OrderStatus.FILLED,
            amount=Decimal("0.5"),
            filled=Decimal("0.5"),
            avg_price=Decimal("60000"),
        )
        mock_adapter.get_orders = AsyncMock(return_value=[ex_order])
        mock_adapter.get_order_trades = AsyncMock(return_value=[])

        # DB has no orders matching
        db_orders = [_make_db_order(exchange_oid="ex-other-order")]

        mock_order_repo = AsyncMock()
        mock_created_order = MagicMock()
        mock_created_order.id = "new-db-uuid"
        mock_order_repo.create = AsyncMock(return_value=mock_created_order)
        mock_order_repo.update = AsyncMock()

        mock_trade_repo = AsyncMock()

        ctx_patch, order_patch, trade_patch = _make_session_context_mock(
            mock_order_repo, mock_trade_repo
        )

        with ctx_patch, order_patch, trade_patch:
            report = await service._reconcile_missing_orders(
                adapter=mock_adapter,
                run_id="run-123",
                account_id="acc-456",
                exchange="okx",
                symbol="BTC/USDT",
                db_orders=db_orders,
                since=datetime.now(UTC) - timedelta(hours=1),
    
            )

        assert report["missing_orders_found"] == 1
        assert report["missing_orders_recovered"] == 1
        assert report["errors"] == []

        # Verify order was created with correct params
        mock_order_repo.create.assert_awaited_once()
        create_kwargs = mock_order_repo.create.call_args.kwargs
        assert create_kwargs["run_id"] == "run-123"
        assert create_kwargs["account_id"] == "acc-456"
        assert create_kwargs["exchange"] == "okx"
        assert create_kwargs["exchange_oid"] == "ex-missing-1"
        assert create_kwargs["symbol"] == "BTC/USDT"
        assert create_kwargs["side"] == OrderSide.BUY
        assert create_kwargs["type"] == OrderType.MARKET
        assert create_kwargs["amount"] == Decimal("0.5")
        assert create_kwargs["status"] == OrderStatus.FILLED

        # Verify filled order was updated
        mock_order_repo.update.assert_awaited_once_with(
            "new-db-uuid",
            filled=Decimal("0.5"),
            avg_price=Decimal("60000"),
            status=OrderStatus.FILLED,
        )

    async def test_exchange_fetch_failure_non_blocking(self, service, mock_adapter):
        """If get_orders fails, returns error in report but does not raise."""
        mock_adapter.get_orders = AsyncMock(
            side_effect=Exception("Exchange timeout")
        )

        report = await service._reconcile_missing_orders(
            adapter=mock_adapter,
            run_id="run-123",
            account_id="acc-456",
            exchange="okx",
            symbol="BTC/USDT",
            db_orders=[],
            since=datetime.now(UTC) - timedelta(hours=1),

        )

        assert report["missing_orders_found"] == 0
        assert report["missing_orders_recovered"] == 0
        assert len(report["errors"]) == 1
        assert "Exchange timeout" in report["errors"][0]

    async def test_fill_recovery(self, service, mock_adapter):
        """Recovered order also gets its fills from get_order_trades."""
        ex_order = _make_exchange_order(
            order_id="ex-filled-1",
            status=OrderStatus.FILLED,
            filled=Decimal("0.1"),
            avg_price=Decimal("50000"),
        )
        fill1 = _make_trade_info(
            trade_id="fill-a",
            order_id="ex-filled-1",
            price=Decimal("49900"),
            amount=Decimal("0.05"),
            fee=Decimal("0.02"),
            fee_currency="USDT",
            taker_or_maker="taker",
        )
        fill2 = _make_trade_info(
            trade_id="fill-b",
            order_id="ex-filled-1",
            price=Decimal("50100"),
            amount=Decimal("0.05"),
            fee=Decimal("0.03"),
            fee_currency="USDT",
            taker_or_maker="maker",
        )
        mock_adapter.get_orders = AsyncMock(return_value=[ex_order])
        mock_adapter.get_order_trades = AsyncMock(return_value=[fill1, fill2])

        db_orders: list = []  # No existing DB orders

        mock_order_repo = AsyncMock()
        mock_created_order = MagicMock()
        mock_created_order.id = "new-db-uuid-2"
        mock_order_repo.create = AsyncMock(return_value=mock_created_order)
        mock_order_repo.update = AsyncMock()

        mock_trade_repo = AsyncMock()

        ctx_patch, order_patch, trade_patch = _make_session_context_mock(
            mock_order_repo, mock_trade_repo
        )

        with ctx_patch, order_patch, trade_patch:
            report = await service._reconcile_missing_orders(
                adapter=mock_adapter,
                run_id="run-123",
                account_id="acc-456",
                exchange="okx",
                symbol="BTC/USDT",
                db_orders=db_orders,
                since=datetime.now(UTC) - timedelta(hours=1),
    
            )

        assert report["missing_orders_found"] == 1
        assert report["missing_orders_recovered"] == 1
        assert report["errors"] == []

        # Verify get_order_trades was called
        mock_adapter.get_order_trades.assert_awaited_once_with("BTC/USDT", "ex-filled-1")

        # Verify two fills were created
        assert mock_trade_repo.create.await_count == 2

        # Check first fill
        first_call = mock_trade_repo.create.call_args_list[0].kwargs
        assert first_call["order_id"] == "new-db-uuid-2"
        assert first_call["price"] == Decimal("49900")
        assert first_call["amount"] == Decimal("0.05")
        assert first_call["fee"] == Decimal("0.02")
        assert first_call["fee_currency"] == "USDT"
        assert first_call["fill_source"] == "recovery"
        assert first_call["exchange_tid"] == "fill-a"
        assert first_call["taker_or_maker"] == "taker"

        # Check second fill
        second_call = mock_trade_repo.create.call_args_list[1].kwargs
        assert second_call["exchange_tid"] == "fill-b"
        assert second_call["taker_or_maker"] == "maker"

    async def test_fill_fetch_failure_still_recovers_order(self, service, mock_adapter):
        """If get_order_trades fails, the order itself is still recovered."""
        ex_order = _make_exchange_order(
            order_id="ex-partial-1",
            status=OrderStatus.FILLED,
            filled=Decimal("0.1"),
            avg_price=Decimal("50000"),
        )
        mock_adapter.get_orders = AsyncMock(return_value=[ex_order])
        mock_adapter.get_order_trades = AsyncMock(
            side_effect=Exception("Trades endpoint unavailable")
        )

        mock_order_repo = AsyncMock()
        mock_created_order = MagicMock()
        mock_created_order.id = "new-db-uuid-3"
        mock_order_repo.create = AsyncMock(return_value=mock_created_order)
        mock_order_repo.update = AsyncMock()

        mock_trade_repo = AsyncMock()

        ctx_patch, order_patch, trade_patch = _make_session_context_mock(
            mock_order_repo, mock_trade_repo
        )

        with ctx_patch, order_patch, trade_patch:
            report = await service._reconcile_missing_orders(
                adapter=mock_adapter,
                run_id="run-123",
                account_id="acc-456",
                exchange="okx",
                symbol="BTC/USDT",
                db_orders=[],
                since=datetime.now(UTC) - timedelta(hours=1),
    
            )

        # Order was recovered despite fill fetch failure
        assert report["missing_orders_recovered"] == 1
        assert report["errors"] == []

        # Order created and updated
        mock_order_repo.create.assert_awaited_once()
        mock_order_repo.update.assert_awaited_once()

        # No fills created
        mock_trade_repo.create.assert_not_awaited()

    async def test_unfilled_order_not_updated(self, service, mock_adapter):
        """An unfilled order (filled=0) should not trigger an update call."""
        ex_order = _make_exchange_order(
            order_id="ex-unfilled-1",
            status=OrderStatus.SUBMITTED,
            filled=Decimal("0"),
            avg_price=None,
            price=Decimal("45000"),
        )
        mock_adapter.get_orders = AsyncMock(return_value=[ex_order])
        mock_adapter.get_order_trades = AsyncMock(return_value=[])

        mock_order_repo = AsyncMock()
        mock_created_order = MagicMock()
        mock_created_order.id = "new-db-uuid-4"
        mock_order_repo.create = AsyncMock(return_value=mock_created_order)
        mock_order_repo.update = AsyncMock()

        mock_trade_repo = AsyncMock()

        ctx_patch, order_patch, trade_patch = _make_session_context_mock(
            mock_order_repo, mock_trade_repo
        )

        with ctx_patch, order_patch, trade_patch:
            report = await service._reconcile_missing_orders(
                adapter=mock_adapter,
                run_id="run-123",
                account_id="acc-456",
                exchange="okx",
                symbol="BTC/USDT",
                db_orders=[],
                since=datetime.now(UTC) - timedelta(hours=1),
    
            )

        assert report["missing_orders_recovered"] == 1
        # update should NOT have been called since filled == 0
        mock_order_repo.update.assert_not_awaited()
