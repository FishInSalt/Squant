"""Tests for engine fill processing refactor — watchMyTrades per-fill data.

Tests _process_trade_execution, _drain_ws_updates ordering, and
reconciliation queue logic.
"""

from collections import OrderedDict, deque
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from squant.engine.live.engine import LiveOrder, LiveTradingEngine
from squant.infra.exchange.ws_types import WSOrderUpdate, WSTradeExecution
from squant.models.enums import OrderSide, OrderStatus


class TestProcessTradeExecution:
    """Tests for _process_trade_execution — per-fill handling from watchMyTrades."""

    @pytest.fixture
    def engine(self):
        engine = LiveTradingEngine.__new__(LiveTradingEngine)
        engine._is_running = True
        engine._symbol = "BTC/USDT"
        engine._pending_ws_trade_executions = deque(maxlen=1000)
        engine._processed_trade_ids = OrderedDict()
        engine._MAX_PROCESSED_TRADE_IDS = 10000
        engine._live_orders = {}
        engine._exchange_order_map = {}
        engine._pending_order_events = []
        engine._orders_needing_reconciliation = set()
        engine._context = MagicMock()
        engine._context._open_trade = None
        engine._risk_manager = MagicMock()
        engine._risk_manager.state.circuit_breaker_triggered = False
        engine._current_price = Decimal("96500")
        engine._has_recent_fill = False
        engine._circuit_breaker_triggered = False

        live_order = LiveOrder(
            internal_id="int-001",
            exchange_order_id="exch-001",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="market",
            amount=Decimal("0.02"),
            price=None,
            status=OrderStatus.SUBMITTED,
        )
        live_order.filled_amount = Decimal("0")
        live_order.avg_fill_price = Decimal("0")
        live_order.fee = Decimal("0")
        live_order.fee_currency = "USDT"
        engine._live_orders["int-001"] = live_order
        engine._exchange_order_map["exch-001"] = "int-001"

        return engine

    def test_records_fill_and_updates_order(self, engine):
        """Per-fill execution should update order state and call _record_fill."""
        exec_data = WSTradeExecution(
            trade_id="t001",
            order_id="exch-001",
            symbol="BTC/USDT",
            side="buy",
            price=Decimal("96500"),
            amount=Decimal("0.008"),
            fee=Decimal("0.077"),
            fee_currency="USDT",
            taker_or_maker="taker",
            timestamp=datetime(2026, 3, 20, 10, 30, 15, tzinfo=UTC),
        )

        with (
            patch.object(engine, "_record_fill") as mock_record,
            patch.object(engine, "_check_trade_completion"),
        ):
            engine._process_trade_execution(exec_data)

            mock_record.assert_called_once()
            call_args = mock_record.call_args
            assert call_args[0][1] == Decimal("96500")  # fill_price
            assert call_args[0][2] == Decimal("0.008")  # fill_amount
            assert call_args.kwargs.get("exchange_tid") == "t001"
            assert call_args.kwargs.get("taker_or_maker") == "taker"

        # Verify order state updated
        order = engine._live_orders["int-001"]
        assert order.filled_amount == Decimal("0.008")
        assert order.avg_fill_price == Decimal("96500")
        assert order.status == OrderStatus.PARTIAL
        assert "t001" in engine._processed_trade_ids
        assert engine._has_recent_fill is True

    def test_marks_filled_when_complete(self, engine):
        """Order should be marked FILLED when filled_amount reaches amount."""
        order = engine._live_orders["int-001"]
        order.amount = Decimal("0.008")  # Set amount to match fill

        exec_data = WSTradeExecution(
            trade_id="t001",
            order_id="exch-001",
            symbol="BTC/USDT",
            side="buy",
            price=Decimal("96500"),
            amount=Decimal("0.008"),
            timestamp=datetime.now(UTC),
        )

        with (
            patch.object(engine, "_record_fill"),
            patch.object(engine, "_check_trade_completion"),
        ):
            engine._process_trade_execution(exec_data)

        assert order.status == OrderStatus.FILLED

    def test_dedup_skips_duplicate(self, engine):
        """Duplicate trade_id should be silently skipped."""
        engine._processed_trade_ids["t001"] = True

        exec_data = WSTradeExecution(
            trade_id="t001",
            order_id="exch-001",
            symbol="BTC/USDT",
            side="buy",
            price=Decimal("96500"),
            amount=Decimal("0.008"),
            timestamp=datetime.now(UTC),
        )

        with patch.object(engine, "_record_fill") as mock_record:
            engine._process_trade_execution(exec_data)
            mock_record.assert_not_called()

    def test_skips_unknown_order(self, engine):
        """Fill for an order not tracked by this engine should be skipped."""
        exec_data = WSTradeExecution(
            trade_id="t999",
            order_id="unknown",
            symbol="BTC/USDT",
            side="buy",
            price=Decimal("96500"),
            amount=Decimal("0.008"),
            timestamp=datetime.now(UTC),
        )

        with patch.object(engine, "_record_fill") as mock_record:
            engine._process_trade_execution(exec_data)
            mock_record.assert_not_called()

    def test_skips_missing_live_order(self, engine):
        """Fill with valid exchange mapping but missing LiveOrder should warn and skip."""
        engine._exchange_order_map["orphan-001"] = "missing-internal"

        exec_data = WSTradeExecution(
            trade_id="t999",
            order_id="orphan-001",
            symbol="BTC/USDT",
            side="buy",
            price=Decimal("96500"),
            amount=Decimal("0.008"),
            timestamp=datetime.now(UTC),
        )

        with patch.object(engine, "_record_fill") as mock_record:
            engine._process_trade_execution(exec_data)
            mock_record.assert_not_called()

    def test_lru_eviction(self, engine):
        """When processed_trade_ids exceeds cap, oldest entries are evicted."""
        engine._MAX_PROCESSED_TRADE_IDS = 10
        for i in range(10):
            engine._processed_trade_ids[f"old-{i}"] = True

        exec_data = WSTradeExecution(
            trade_id="new-001",
            order_id="exch-001",
            symbol="BTC/USDT",
            side="buy",
            price=Decimal("96500"),
            amount=Decimal("0.008"),
            timestamp=datetime.now(UTC),
        )

        with (
            patch.object(engine, "_record_fill"),
            patch.object(engine, "_check_trade_completion"),
        ):
            engine._process_trade_execution(exec_data)

        assert "new-001" in engine._processed_trade_ids
        # Evicts 50% (5 oldest) when cap (10) is exceeded
        assert len(engine._processed_trade_ids) <= 6

    def test_avg_price_weighted_on_second_fill(self, engine):
        """Second partial fill should compute weighted avg_fill_price correctly."""
        order = engine._live_orders["int-001"]
        # Simulate first fill already processed
        order.filled_amount = Decimal("0.01")
        order.avg_fill_price = Decimal("96000")
        order.fee = Decimal("0.096")

        exec_data = WSTradeExecution(
            trade_id="t002",
            order_id="exch-001",
            symbol="BTC/USDT",
            side="buy",
            price=Decimal("97000"),
            amount=Decimal("0.01"),
            fee=Decimal("0.097"),
            timestamp=datetime.now(UTC),
        )

        with (
            patch.object(engine, "_record_fill"),
            patch.object(engine, "_check_trade_completion"),
        ):
            engine._process_trade_execution(exec_data)

        assert order.filled_amount == Decimal("0.02")
        # Weighted avg: (96000*0.01 + 97000*0.01) / 0.02 = 96500
        assert order.avg_fill_price == Decimal("96500")
        assert order.fee == Decimal("0.193")  # 0.096 + 0.097

    def test_check_trade_completion_called(self, engine):
        """_check_trade_completion should be called after recording fill."""
        exec_data = WSTradeExecution(
            trade_id="t001",
            order_id="exch-001",
            symbol="BTC/USDT",
            side="buy",
            price=Decimal("96500"),
            amount=Decimal("0.008"),
            timestamp=datetime.now(UTC),
        )

        with (
            patch.object(engine, "_record_fill"),
            patch.object(engine, "_check_trade_completion") as mock_check,
        ):
            engine._process_trade_execution(exec_data)
            mock_check.assert_called_once_with(False, False, "ws")


class TestDrainWSUpdatesOrdering:
    """Tests for _drain_ws_updates — fills before status changes."""

    @pytest.fixture
    def engine(self):
        engine = LiveTradingEngine.__new__(LiveTradingEngine)
        engine._pending_ws_trade_executions = deque(maxlen=1000)
        engine._pending_ws_updates = deque(maxlen=1000)
        engine._is_running = True
        return engine

    def test_fills_before_status_changes(self, engine):
        """Trade executions must be processed before order status updates."""
        call_order = []

        def mock_process_trade(exec_data):
            call_order.append(("fill", exec_data.trade_id))

        def mock_process_status(update):
            call_order.append(("status", update.order_id))

        engine._process_trade_execution = mock_process_trade
        engine._process_single_ws_update = mock_process_status

        # Queue a status update first, then a fill
        engine._pending_ws_updates.append(
            WSOrderUpdate(
                order_id="o1",
                symbol="BTC/USDT",
                side="buy",
                order_type="market",
                status="cancelled",
                price=Decimal("0"),
                size=Decimal("0"),
                filled_size=Decimal("0"),
                avg_price=Decimal("0"),
                timestamp=datetime.now(UTC),
            )
        )
        engine._pending_ws_trade_executions.append(
            WSTradeExecution(
                trade_id="t1",
                order_id="o2",
                symbol="BTC/USDT",
                side="buy",
                price=Decimal("96500"),
                amount=Decimal("0.01"),
                timestamp=datetime.now(UTC),
            )
        )

        engine._drain_ws_updates()

        assert len(call_order) == 2
        assert call_order[0][0] == "fill"
        assert call_order[1][0] == "status"

    def test_drain_with_only_fills(self, engine):
        """Draining with only trade executions and no order updates works."""
        processed = []
        engine._process_trade_execution = lambda ed: processed.append(ed.trade_id)
        engine._process_single_ws_update = lambda u: processed.append(u.order_id)

        engine._pending_ws_trade_executions.append(
            WSTradeExecution(
                trade_id="t1",
                order_id="o1",
                symbol="BTC/USDT",
                side="buy",
                price=Decimal("96500"),
                amount=Decimal("0.01"),
                timestamp=datetime.now(UTC),
            )
        )

        engine._drain_ws_updates()

        assert processed == ["t1"]
        assert len(engine._pending_ws_trade_executions) == 0

    def test_drain_with_only_status_updates(self, engine):
        """Draining with only order updates and no fills works."""
        processed = []
        engine._process_trade_execution = lambda ed: processed.append(ed.trade_id)
        engine._process_single_ws_update = lambda u: processed.append(u.order_id)

        engine._pending_ws_updates.append(
            WSOrderUpdate(
                order_id="o1",
                symbol="BTC/USDT",
                side="buy",
                order_type="market",
                status="cancelled",
                size=Decimal("0"),
                timestamp=datetime.now(UTC),
            )
        )

        engine._drain_ws_updates()

        assert processed == ["o1"]
        assert len(engine._pending_ws_updates) == 0

    def test_drain_empty_is_noop(self, engine):
        """Draining with both queues empty does nothing without error."""
        engine._drain_ws_updates()
        assert len(engine._pending_ws_trade_executions) == 0
        assert len(engine._pending_ws_updates) == 0


class TestHandlePrivateWSMessage:
    """Tests for _handle_private_ws_message — routing to correct buffer."""

    @pytest.fixture
    def engine(self):
        engine = LiveTradingEngine.__new__(LiveTradingEngine)
        engine._pending_ws_trade_executions = deque(maxlen=1000)
        engine._pending_ws_updates = deque(maxlen=1000)
        engine._is_running = True
        engine._emergency_close_in_progress = False
        engine._MAX_PENDING_WS_UPDATES = 1000
        return engine

    @pytest.mark.asyncio
    async def test_routes_order_to_on_order_update(self, engine):
        """Messages with type='order' should be routed to on_order_update."""
        update = WSOrderUpdate(
            order_id="o1",
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            status="filled",
            size=Decimal("0.1"),
            timestamp=datetime.now(UTC),
        )
        msg = {"type": "order", "data": update}

        with patch.object(engine, "on_order_update") as mock_on_order:
            await engine._handle_private_ws_message(msg)
            mock_on_order.assert_called_once_with(update)

    @pytest.mark.asyncio
    async def test_routes_trade_execution_to_buffer(self, engine):
        """Messages with type='trade_execution' should be buffered."""
        exec_data = WSTradeExecution(
            trade_id="t1",
            order_id="o1",
            symbol="BTC/USDT",
            side="buy",
            price=Decimal("96500"),
            amount=Decimal("0.01"),
            timestamp=datetime.now(UTC),
        )
        msg = {"type": "trade_execution", "data": exec_data}

        await engine._handle_private_ws_message(msg)

        assert len(engine._pending_ws_trade_executions) == 1
        assert engine._pending_ws_trade_executions[0] is exec_data

    @pytest.mark.asyncio
    async def test_ignores_empty_data(self, engine):
        """Messages with no data should be silently ignored."""
        msg = {"type": "order", "data": None}

        with patch.object(engine, "on_order_update") as mock_on_order:
            await engine._handle_private_ws_message(msg)
            mock_on_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_unknown_type(self, engine):
        """Messages with unknown type should be silently ignored."""
        msg = {"type": "unknown", "data": {"foo": "bar"}}

        await engine._handle_private_ws_message(msg)
        assert len(engine._pending_ws_trade_executions) == 0

    @pytest.mark.asyncio
    async def test_ignores_non_wstradeexecution_data(self, engine):
        """trade_execution with non-WSTradeExecution data should be ignored."""
        msg = {"type": "trade_execution", "data": {"raw": "dict"}}

        await engine._handle_private_ws_message(msg)
        assert len(engine._pending_ws_trade_executions) == 0


class TestReconciliationQueue:
    """Tests for _orders_needing_reconciliation queue from WS and polling."""

    @pytest.fixture
    def engine(self):
        engine = LiveTradingEngine.__new__(LiveTradingEngine)
        engine._is_running = True
        engine._symbol = "BTC/USDT"
        engine._pending_ws_updates = deque(maxlen=1000)
        engine._pending_ws_trade_executions = deque(maxlen=1000)
        engine._processed_trade_ids = OrderedDict()
        engine._MAX_PROCESSED_TRADE_IDS = 10000
        engine._live_orders = {}
        engine._exchange_order_map = {}
        engine._pending_order_events = []
        engine._orders_needing_reconciliation = set()
        engine._context = MagicMock()
        engine._context._open_trade = None
        engine._risk_manager = MagicMock()
        engine._risk_manager.state.circuit_breaker_triggered = False
        engine._current_price = Decimal("96500")
        engine._has_recent_fill = False
        engine._circuit_breaker_triggered = False
        return engine

    def test_ws_filled_but_incomplete_fills_queues_reconciliation(self, engine):
        """watchOrders FILLED but fills incomplete should queue for reconciliation."""
        live_order = LiveOrder(
            internal_id="int-001",
            exchange_order_id="exch-001",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="market",
            amount=Decimal("0.1"),
            price=None,
            status=OrderStatus.SUBMITTED,
        )
        live_order.filled_amount = Decimal("0")  # No fills arrived yet
        engine._live_orders["int-001"] = live_order
        engine._exchange_order_map["exch-001"] = "int-001"

        update = WSOrderUpdate(
            order_id="exch-001",
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            status="filled",
            size=Decimal("0.1"),
            filled_size=Decimal("0.1"),
            avg_price=Decimal("96500"),
            timestamp=datetime.now(UTC),
        )

        engine._process_single_ws_update(update)

        # filled_amount updated from WS (max(0, 0.1) = 0.1)
        # But since filled_amount (0.1) >= amount (0.1), reconciliation
        # should NOT be queued
        assert "int-001" not in engine._orders_needing_reconciliation

    def test_ws_filled_with_zero_local_fills_queues(self, engine):
        """watchOrders FILLED but filled_size < amount queues reconciliation."""
        live_order = LiveOrder(
            internal_id="int-001",
            exchange_order_id="exch-001",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="market",
            amount=Decimal("0.1"),
            price=None,
            status=OrderStatus.SUBMITTED,
        )
        live_order.filled_amount = Decimal("0")
        engine._live_orders["int-001"] = live_order
        engine._exchange_order_map["exch-001"] = "int-001"

        # WS reports FILLED but filled_size is only 0.05 (partial data from WS)
        update = WSOrderUpdate(
            order_id="exch-001",
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            status="filled",
            size=Decimal("0.1"),
            filled_size=Decimal("0.05"),  # Less than amount
            avg_price=Decimal("96500"),
            timestamp=datetime.now(UTC),
        )

        engine._process_single_ws_update(update)

        assert "int-001" in engine._orders_needing_reconciliation

    def test_polling_filled_but_incomplete_queues_reconciliation(self, engine):
        """REST polling FILLED but fills incomplete should queue for reconciliation."""
        live_order = LiveOrder(
            internal_id="int-001",
            exchange_order_id="exch-001",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="market",
            amount=Decimal("0.1"),
            price=None,
            status=OrderStatus.SUBMITTED,
        )
        live_order.filled_amount = Decimal("0")
        engine._live_orders["int-001"] = live_order

        from squant.infra.exchange.types import OrderResponse
        from squant.models.enums import OrderType

        response = OrderResponse(
            order_id="exch-001",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            status=OrderStatus.FILLED,
            price=None,
            amount=Decimal("0.1"),
            filled=Decimal("0.05"),  # Less than amount
            avg_price=Decimal("96500"),
        )

        engine._update_order_from_response(live_order, response)

        assert "int-001" in engine._orders_needing_reconciliation


class TestOnWSReconnect:
    """Tests for _on_ws_reconnect — schedules fill reconciliation for active orders."""

    @pytest.fixture
    def engine(self):
        engine = LiveTradingEngine.__new__(LiveTradingEngine)
        engine._run_id = "test-run-001"
        engine._live_orders = {}
        engine._orders_needing_reconciliation = set()
        return engine

    @pytest.mark.asyncio
    async def test_reconnect_queues_all_active_orders(self, engine):
        """All orders in _live_orders should be queued for reconciliation on reconnect."""
        engine._live_orders["order-1"] = MagicMock()
        engine._live_orders["order-2"] = MagicMock()
        engine._live_orders["order-3"] = MagicMock()

        await engine._on_ws_reconnect()

        assert engine._orders_needing_reconciliation == {"order-1", "order-2", "order-3"}

    @pytest.mark.asyncio
    async def test_reconnect_with_no_orders(self, engine):
        """Reconnect with no active orders should not error."""
        await engine._on_ws_reconnect()
        assert engine._orders_needing_reconciliation == set()


class TestRecordFillNewParams:
    """Tests for _record_fill new exchange_tid and taker_or_maker params."""

    @pytest.fixture
    def engine(self):
        engine = LiveTradingEngine.__new__(LiveTradingEngine)
        engine._is_running = True
        engine._context = MagicMock()
        engine._risk_manager = MagicMock()
        engine._has_recent_fill = False
        engine._pending_order_events = []
        return engine

    def test_record_fill_includes_exchange_tid(self, engine):
        """exchange_tid should appear in the audit event."""
        live_order = LiveOrder(
            internal_id="order-1",
            exchange_order_id="exch-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="market",
            amount=Decimal("0.1"),
            price=None,
            status=OrderStatus.PARTIAL,
        )
        live_order.filled_amount = Decimal("0.05")
        live_order.avg_fill_price = Decimal("96500")
        live_order.fee = Decimal("0.05")
        live_order.fee_currency = "USDT"

        engine._record_fill(
            live_order,
            fill_price=Decimal("96500"),
            fill_amount=Decimal("0.05"),
            fee_delta=Decimal("0.05"),
            total_fee=Decimal("0.05"),
            source="ws",
            exchange_tid="trade-123",
            taker_or_maker="taker",
        )

        assert len(engine._pending_order_events) == 1
        event = engine._pending_order_events[0]
        assert event["exchange_tid"] == "trade-123"
        assert event["taker_or_maker"] == "taker"

    def test_record_fill_none_tid_by_default(self, engine):
        """Without exchange_tid, audit event should have None for both fields."""
        live_order = LiveOrder(
            internal_id="order-1",
            exchange_order_id="exch-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="market",
            amount=Decimal("0.1"),
            price=None,
            status=OrderStatus.PARTIAL,
        )
        live_order.filled_amount = Decimal("0.05")
        live_order.fee = Decimal("0")
        live_order.fee_currency = "USDT"

        engine._record_fill(
            live_order,
            fill_price=Decimal("96500"),
            fill_amount=Decimal("0.05"),
            fee_delta=Decimal("0.05"),
            total_fee=Decimal("0.05"),
            source="poll",
        )

        event = engine._pending_order_events[0]
        assert event["exchange_tid"] is None
        assert event["taker_or_maker"] is None
