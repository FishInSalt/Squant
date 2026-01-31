"""Unit tests for order synchronization utilities."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from squant.engine.live.order_sync import (
    OrderReconciler,
    OrderStateChange,
    OrderStateTracker,
    parse_ws_order_update,
)
from squant.infra.exchange.types import OrderResponse
from squant.models.enums import OrderSide, OrderStatus, OrderType


class TestOrderStateChange:
    """Tests for OrderStateChange dataclass."""

    def test_has_new_fill_positive(self):
        """Test has_new_fill returns True when there's a fill delta."""
        change = OrderStateChange(
            order_id="order-1",
            old_status=OrderStatus.SUBMITTED,
            new_status=OrderStatus.PARTIAL,
            old_filled=Decimal("0"),
            new_filled=Decimal("0.5"),
            fill_delta=Decimal("0.5"),
            timestamp=datetime.now(UTC),
        )

        assert change.has_new_fill is True

    def test_has_new_fill_zero(self):
        """Test has_new_fill returns False when no fill delta."""
        change = OrderStateChange(
            order_id="order-1",
            old_status=OrderStatus.SUBMITTED,
            new_status=OrderStatus.CANCELLED,
            old_filled=Decimal("0"),
            new_filled=Decimal("0"),
            fill_delta=Decimal("0"),
            timestamp=datetime.now(UTC),
        )

        assert change.has_new_fill is False

    def test_is_status_change_true(self):
        """Test is_status_change returns True when status changed."""
        change = OrderStateChange(
            order_id="order-1",
            old_status=OrderStatus.SUBMITTED,
            new_status=OrderStatus.FILLED,
            old_filled=Decimal("0"),
            new_filled=Decimal("1.0"),
            fill_delta=Decimal("1.0"),
            timestamp=datetime.now(UTC),
        )

        assert change.is_status_change is True

    def test_is_status_change_false(self):
        """Test is_status_change returns False when status unchanged."""
        change = OrderStateChange(
            order_id="order-1",
            old_status=OrderStatus.PARTIAL,
            new_status=OrderStatus.PARTIAL,
            old_filled=Decimal("0.3"),
            new_filled=Decimal("0.5"),
            fill_delta=Decimal("0.2"),
            timestamp=datetime.now(UTC),
        )

        assert change.is_status_change is False


class TestOrderStateTracker:
    """Tests for OrderStateTracker class."""

    @pytest.fixture
    def tracker(self):
        """Create a fresh tracker."""
        return OrderStateTracker()

    @pytest.fixture
    def order_response(self):
        """Create a test order response."""
        return OrderResponse(
            order_id="exchange-1",
            client_order_id="internal-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            status=OrderStatus.SUBMITTED,
            price=None,
            amount=Decimal("1.0"),
            filled=Decimal("0"),
            avg_price=None,
            fee=None,
        )

    def test_first_update_returns_none(self, tracker, order_response):
        """Test that first update returns None (no change to compare)."""
        result = tracker.update_state("order-1", order_response)

        assert result is None

    def test_no_change_returns_none(self, tracker, order_response):
        """Test that identical state returns None."""
        tracker.update_state("order-1", order_response)
        result = tracker.update_state("order-1", order_response)

        assert result is None

    def test_status_change_detected(self, tracker, order_response):
        """Test that status change is detected."""
        tracker.update_state("order-1", order_response)

        order_response.status = OrderStatus.FILLED
        order_response.filled = Decimal("1.0")
        result = tracker.update_state("order-1", order_response)

        assert result is not None
        assert result.old_status == OrderStatus.SUBMITTED
        assert result.new_status == OrderStatus.FILLED

    def test_fill_change_detected(self, tracker, order_response):
        """Test that fill change is detected."""
        tracker.update_state("order-1", order_response)

        order_response.status = OrderStatus.PARTIAL
        order_response.filled = Decimal("0.5")
        result = tracker.update_state("order-1", order_response)

        assert result is not None
        assert result.fill_delta == Decimal("0.5")

    def test_remove_order(self, tracker, order_response):
        """Test removing an order from tracking."""
        tracker.update_state("order-1", order_response)
        tracker.remove_order("order-1")

        assert "order-1" not in tracker.get_tracked_orders()

    def test_get_tracked_orders(self, tracker, order_response):
        """Test getting list of tracked orders."""
        tracker.update_state("order-1", order_response)
        order_response.order_id = "exchange-2"
        tracker.update_state("order-2", order_response)

        tracked = tracker.get_tracked_orders()

        assert "order-1" in tracked
        assert "order-2" in tracked

    def test_clear_tracker(self, tracker, order_response):
        """Test clearing all tracked state."""
        tracker.update_state("order-1", order_response)
        tracker.update_state("order-2", order_response)
        tracker.clear()

        assert tracker.get_tracked_orders() == []


class TestOrderReconciler:
    """Tests for OrderReconciler class."""

    @pytest.fixture
    def reconciler(self):
        """Create a fresh reconciler."""
        return OrderReconciler()

    def test_reconcile_matching_orders(self, reconciler):
        """Test reconciliation with matching orders."""
        local_orders = {
            "internal-1": {
                "status": OrderStatus.SUBMITTED,
                "filled": Decimal("0"),
            }
        }
        exchange_orders = [
            OrderResponse(
                order_id="exchange-1",
                client_order_id="internal-1",
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                status=OrderStatus.SUBMITTED,
                amount=Decimal("1.0"),
                filled=Decimal("0"),
            )
        ]

        discrepancies = reconciler.reconcile(local_orders, exchange_orders)

        assert discrepancies == []

    def test_reconcile_status_mismatch(self, reconciler):
        """Test reconciliation detects status mismatch."""
        local_orders = {
            "internal-1": {
                "status": OrderStatus.PARTIAL,
                "filled": Decimal("0.5"),
            }
        }
        exchange_orders = [
            OrderResponse(
                order_id="exchange-1",
                client_order_id="internal-1",
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                status=OrderStatus.FILLED,
                amount=Decimal("1.0"),
                filled=Decimal("1.0"),
            )
        ]

        discrepancies = reconciler.reconcile(local_orders, exchange_orders)

        assert len(discrepancies) == 1
        assert discrepancies[0]["type"] == "state_mismatch"

    def test_reconcile_missing_on_exchange(self, reconciler):
        """Test reconciliation detects orders missing on exchange."""
        local_orders = {
            "internal-1": {
                "status": OrderStatus.SUBMITTED,
                "filled": Decimal("0"),
            }
        }
        exchange_orders = []  # Order not on exchange

        discrepancies = reconciler.reconcile(local_orders, exchange_orders)

        assert len(discrepancies) == 1
        assert discrepancies[0]["type"] == "missing_on_exchange"

    def test_reconcile_terminal_status_not_missing(self, reconciler):
        """Test that terminal status orders are not flagged as missing."""
        local_orders = {
            "internal-1": {
                "status": OrderStatus.FILLED,
                "filled": Decimal("1.0"),
            }
        }
        exchange_orders = []  # Filled order not in open orders is expected

        discrepancies = reconciler.reconcile(local_orders, exchange_orders)

        assert discrepancies == []

    def test_reconcile_untracked_exchange_order(self, reconciler):
        """Test reconciliation detects untracked exchange orders."""
        local_orders = {}
        exchange_orders = [
            OrderResponse(
                order_id="exchange-1",
                client_order_id="unknown-internal",
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                status=OrderStatus.SUBMITTED,
                amount=Decimal("1.0"),
                filled=Decimal("0"),
            )
        ]

        discrepancies = reconciler.reconcile(local_orders, exchange_orders)

        assert len(discrepancies) == 1
        assert discrepancies[0]["type"] == "untracked_exchange_order"

    def test_reconcile_filled_amount_mismatch(self, reconciler):
        """Test reconciliation detects filled amount mismatch."""
        local_orders = {
            "internal-1": {
                "status": OrderStatus.PARTIAL,
                "filled": Decimal("0.3"),
            }
        }
        exchange_orders = [
            OrderResponse(
                order_id="exchange-1",
                client_order_id="internal-1",
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                status=OrderStatus.PARTIAL,
                amount=Decimal("1.0"),
                filled=Decimal("0.5"),  # Different fill
            )
        ]

        discrepancies = reconciler.reconcile(local_orders, exchange_orders)

        assert len(discrepancies) == 1
        assert discrepancies[0]["type"] == "state_mismatch"

    def test_reconcile_allows_submitted_to_filled_lag(self, reconciler):
        """Test reconciliation allows submitted -> filled transition lag."""
        local_orders = {
            "internal-1": {
                "status": OrderStatus.SUBMITTED,
                "filled": Decimal("0"),
            }
        }
        exchange_orders = [
            OrderResponse(
                order_id="exchange-1",
                client_order_id="internal-1",
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                status=OrderStatus.FILLED,  # Exchange shows filled
                amount=Decimal("1.0"),
                filled=Decimal("1.0"),
            )
        ]

        discrepancies = reconciler.reconcile(local_orders, exchange_orders)

        # Still flagged because filled amount differs
        assert len(discrepancies) == 1

    def test_reconciliation_log(self, reconciler):
        """Test reconciliation log is maintained."""
        local_orders = {
            "internal-1": {
                "status": OrderStatus.SUBMITTED,
                "filled": Decimal("0"),
            }
        }
        exchange_orders = []

        reconciler.reconcile(local_orders, exchange_orders)

        log = reconciler.get_reconciliation_log()
        assert len(log) == 1
        assert "timestamp" in log[0]
        assert "discrepancies" in log[0]


class TestParseWSOrderUpdate:
    """Tests for parse_ws_order_update function."""

    def test_parse_basic_order(self):
        """Test parsing a basic order update."""
        data = {
            "ordId": "exchange-123",
            "clOrdId": "internal-123",
            "instId": "BTC-USDT",
            "side": "buy",
            "ordType": "market",
            "state": "filled",
            "sz": "0.1",
            "accFillSz": "0.1",
            "px": "",
            "avgPx": "45000.5",
            "fee": "-0.45",
            "feeCcy": "USDT",
        }

        result = parse_ws_order_update(data)

        assert result["order_id"] == "exchange-123"
        assert result["client_order_id"] == "internal-123"
        assert result["symbol"] == "BTC/USDT"
        assert result["side"] == OrderSide.BUY
        assert result["type"] == OrderType.MARKET
        assert result["status"] == OrderStatus.FILLED
        assert result["amount"] == Decimal("0.1")
        assert result["filled"] == Decimal("0.1")
        assert result["avg_price"] == Decimal("45000.5")
        assert result["fee"] == Decimal("-0.45")
        assert result["fee_currency"] == "USDT"

    def test_parse_sell_limit_order(self):
        """Test parsing a sell limit order."""
        data = {
            "ordId": "exchange-456",
            "clOrdId": "internal-456",
            "instId": "ETH-USDT",
            "side": "sell",
            "ordType": "limit",
            "state": "partially_filled",
            "sz": "1.0",
            "accFillSz": "0.5",
            "px": "3000.00",
            "avgPx": "3000.50",
            "fee": "-1.50",
            "feeCcy": "USDT",
        }

        result = parse_ws_order_update(data)

        assert result["side"] == OrderSide.SELL
        assert result["type"] == OrderType.LIMIT
        assert result["status"] == OrderStatus.PARTIAL
        assert result["price"] == Decimal("3000.00")

    def test_parse_cancelled_order(self):
        """Test parsing a cancelled order."""
        data = {
            "ordId": "exchange-789",
            "clOrdId": "internal-789",
            "instId": "BTC-USDT",
            "side": "buy",
            "ordType": "limit",
            "state": "canceled",
            "sz": "0.5",
            "accFillSz": "0",
            "px": "40000.00",
            "avgPx": "",
            "fee": "0",
            "feeCcy": "USDT",
        }

        result = parse_ws_order_update(data)

        assert result["status"] == OrderStatus.CANCELLED
        assert result["filled"] == Decimal("0")
        assert result["avg_price"] is None

    def test_parse_live_order(self):
        """Test parsing a live (submitted) order."""
        data = {
            "ordId": "exchange-abc",
            "clOrdId": "internal-abc",
            "instId": "BTC-USDT",
            "side": "buy",
            "ordType": "limit",
            "state": "live",
            "sz": "0.1",
            "accFillSz": "0",
            "px": "44000.00",
            "avgPx": "",
            "fee": "0",
            "feeCcy": "",
        }

        result = parse_ws_order_update(data)

        assert result["status"] == OrderStatus.SUBMITTED

    def test_parse_mmp_cancelled(self):
        """Test parsing MMP cancelled order."""
        data = {
            "ordId": "exchange-mmp",
            "clOrdId": "internal-mmp",
            "instId": "BTC-USDT",
            "side": "buy",
            "ordType": "limit",
            "state": "mmp_canceled",
            "sz": "0.1",
            "accFillSz": "0",
            "px": "44000.00",
            "avgPx": "",
        }

        result = parse_ws_order_update(data)

        assert result["status"] == OrderStatus.CANCELLED

    def test_parse_unknown_state_defaults_to_pending(self):
        """Test that unknown state defaults to PENDING."""
        data = {
            "ordId": "exchange-unknown",
            "clOrdId": "internal-unknown",
            "instId": "BTC-USDT",
            "side": "buy",
            "ordType": "market",
            "state": "unknown_state",
            "sz": "0.1",
            "accFillSz": "0",
        }

        result = parse_ws_order_update(data)

        assert result["status"] == OrderStatus.PENDING

    def test_parse_missing_optional_fields(self):
        """Test parsing with missing optional fields."""
        data = {
            "ordId": "exchange-min",
            "instId": "BTC-USDT",
            "side": "buy",
            "ordType": "market",
            "state": "filled",
            "sz": "0.1",
            "accFillSz": "0.1",
        }

        result = parse_ws_order_update(data)

        assert result["client_order_id"] is None
        assert result["price"] is None
        assert result["avg_price"] is None
        assert result["fee"] == Decimal("0")
        assert result["fee_currency"] is None
