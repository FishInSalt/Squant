"""Unit tests for live trading engine."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from squant.engine.backtest.strategy_base import Strategy
from squant.engine.backtest.types import Bar
from squant.engine.live.engine import LiveOrder, LiveTradingEngine
from squant.engine.risk import RiskConfig
from squant.infra.exchange.okx.ws_types import WSCandle, WSOrderUpdate
from squant.infra.exchange.types import (
    AccountBalance,
    Balance,
    OrderResponse,
)
from squant.models.enums import OrderSide, OrderStatus, OrderType


class SimpleStrategy(Strategy):
    """Simple test strategy that buys when price is below threshold."""

    def on_init(self) -> None:
        self.threshold = self.ctx.params.get("threshold", Decimal("50000"))
        self.buy_executed = False

    def on_bar(self, bar: Bar) -> None:
        if bar.close < self.threshold and not self.ctx.has_position(bar.symbol):
            self.ctx.buy(bar.symbol, Decimal("0.01"))
            self.buy_executed = True

    def on_stop(self) -> None:
        pass


class AlwaysBuyStrategy(Strategy):
    """Strategy that always tries to buy (for risk testing)."""

    def on_init(self) -> None:
        self.buy_count = 0

    def on_bar(self, bar: Bar) -> None:
        self.ctx.buy(bar.symbol, Decimal("0.01"))
        self.buy_count += 1

    def on_stop(self) -> None:
        pass


@pytest.fixture
def run_id():
    """Generate a unique run ID."""
    return uuid4()


@pytest.fixture
def strategy():
    """Create a simple test strategy."""
    return SimpleStrategy()


@pytest.fixture
def risk_config():
    """Create a risk config for testing."""
    return RiskConfig(
        max_position_size=Decimal("0.5"),  # 50% of equity
        max_order_size=Decimal("0.1"),  # 10% of equity
        daily_trade_limit=100,
        daily_loss_limit=Decimal("0.1"),  # 10%
        max_price_deviation=Decimal("0.05"),  # 5%
        circuit_breaker_enabled=True,
        circuit_breaker_loss_count=5,
        circuit_breaker_cooldown_minutes=30,
    )


@pytest.fixture
def mock_adapter():
    """Create a mock exchange adapter."""
    adapter = AsyncMock()

    # Mock connect to succeed
    adapter.connect = AsyncMock()

    # Mock get_balance to return test balance
    adapter.get_balance = AsyncMock(
        return_value=AccountBalance(
            exchange="okx",
            balances=[
                Balance(currency="USDT", available=Decimal("10000"), frozen=Decimal("0")),
                Balance(currency="BTC", available=Decimal("0"), frozen=Decimal("0")),
            ],
        )
    )

    # Mock place_order to succeed
    adapter.place_order = AsyncMock(
        return_value=OrderResponse(
            order_id="exchange-123",
            client_order_id=None,
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            status=OrderStatus.SUBMITTED,
            price=None,
            amount=Decimal("0.01"),
            filled=Decimal("0"),
        )
    )

    # Mock get_order
    adapter.get_order = AsyncMock(
        return_value=OrderResponse(
            order_id="exchange-123",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            status=OrderStatus.SUBMITTED,
            price=None,
            amount=Decimal("0.01"),
            filled=Decimal("0"),
        )
    )

    # Mock cancel_order
    adapter.cancel_order = AsyncMock()

    return adapter


@pytest.fixture
def engine(run_id, strategy, risk_config, mock_adapter):
    """Create a live trading engine for testing."""
    with patch("squant.config.get_settings") as mock_settings:
        settings = MagicMock()
        settings.paper_max_equity_curve_size = 10000
        settings.paper_max_completed_orders = 1000
        settings.paper_max_fills = 1000
        settings.paper_max_trades = 1000
        settings.paper_max_logs = 1000
        mock_settings.return_value = settings

        return LiveTradingEngine(
            run_id=run_id,
            strategy=strategy,
            symbol="BTC/USDT",
            timeframe="1m",
            adapter=mock_adapter,
            risk_config=risk_config,
            initial_equity=Decimal("10000"),
            params={"threshold": Decimal("50000")},
        )


class TestLiveOrderClass:
    """Tests for LiveOrder class."""

    def test_live_order_creation(self):
        """Test LiveOrder is created with correct attributes."""
        order = LiveOrder(
            internal_id="order-1",
            exchange_order_id="exchange-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="market",
            amount=Decimal("0.1"),
            price=None,
        )

        assert order.internal_id == "order-1"
        assert order.exchange_order_id == "exchange-1"
        assert order.symbol == "BTC/USDT"
        assert order.side == OrderSide.BUY
        assert order.amount == Decimal("0.1")
        assert order.filled_amount == Decimal("0")
        assert order.status == OrderStatus.PENDING

    def test_remaining_amount(self):
        """Test remaining_amount property."""
        order = LiveOrder(
            internal_id="order-1",
            exchange_order_id="exchange-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="market",
            amount=Decimal("1.0"),
            price=None,
        )
        order.filled_amount = Decimal("0.3")

        assert order.remaining_amount == Decimal("0.7")

    def test_is_complete_for_terminal_states(self):
        """Test is_complete for terminal states."""
        order = LiveOrder(
            internal_id="order-1",
            exchange_order_id="exchange-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="market",
            amount=Decimal("0.1"),
            price=None,
        )

        # Not complete for pending
        order.status = OrderStatus.PENDING
        assert order.is_complete is False

        # Not complete for submitted
        order.status = OrderStatus.SUBMITTED
        assert order.is_complete is False

        # Complete for filled
        order.status = OrderStatus.FILLED
        assert order.is_complete is True

        # Complete for cancelled
        order.status = OrderStatus.CANCELLED
        assert order.is_complete is True

        # Complete for rejected
        order.status = OrderStatus.REJECTED
        assert order.is_complete is True


class TestLiveTradingEngineInit:
    """Tests for engine initialization."""

    def test_engine_creation(self, engine, run_id):
        """Test engine is created with correct attributes."""
        assert engine.run_id == run_id
        assert engine.symbol == "BTC/USDT"
        assert engine.timeframe == "1m"
        assert engine.is_running is False
        assert engine.bar_count == 0

    def test_context_initialized(self, engine):
        """Test that context is properly initialized."""
        assert engine.context.cash == Decimal("10000")
        assert engine.context.initial_capital == Decimal("10000")
        assert engine.context.params.get("threshold") == Decimal("50000")

    def test_strategy_has_context(self, engine, strategy):
        """Test that strategy has context injected."""
        assert strategy.ctx is engine.context

    def test_risk_manager_initialized(self, engine):
        """Test that risk manager is properly initialized."""
        assert engine.risk_manager is not None
        state = engine.risk_manager.get_state_summary()
        assert state["initial_equity"] == Decimal("10000")


class TestLiveTradingEngineLifecycle:
    """Tests for engine lifecycle."""

    @pytest.mark.asyncio
    async def test_start_engine(self, engine, strategy, mock_adapter):
        """Test starting the engine."""
        await engine.start()

        assert engine.is_running is True
        assert engine.started_at is not None
        # Strategy on_init was called
        assert hasattr(strategy, "threshold")
        # Adapter connect was called
        mock_adapter.connect.assert_called_once()
        # Balance was synced
        mock_adapter.get_balance.assert_called()

    @pytest.mark.asyncio
    async def test_stop_engine(self, engine):
        """Test stopping the engine."""
        await engine.start()
        await engine.stop()

        assert engine.is_running is False
        assert engine.stopped_at is not None

    @pytest.mark.asyncio
    async def test_stop_with_error(self, engine):
        """Test stopping the engine with an error message."""
        await engine.start()
        await engine.stop(error="Test error")

        assert engine.is_running is False
        assert engine.error_message == "Test error"

    @pytest.mark.asyncio
    async def test_double_start_warns(self, engine):
        """Test that starting twice doesn't cause issues."""
        await engine.start()
        await engine.start()  # Should log warning but not fail

        assert engine.is_running is True

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self, engine):
        """Test that stopping when not running doesn't cause issues."""
        await engine.stop()  # Should log warning but not fail

        assert engine.is_running is False

    @pytest.mark.asyncio
    async def test_start_failure_propagates(self, engine, mock_adapter):
        """Test that start failure is properly handled."""
        mock_adapter.connect.side_effect = Exception("Connection failed")

        with pytest.raises(Exception, match="Connection failed"):
            await engine.start()

        assert engine.is_running is False
        assert "Startup failed" in engine.error_message


class TestCandleProcessing:
    """Tests for candle processing."""

    @pytest.fixture
    def closed_candle(self):
        """Create a closed candle for testing."""
        return WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            open=Decimal("45000"),
            high=Decimal("46000"),
            low=Decimal("44000"),
            close=Decimal("45500"),
            volume=Decimal("100"),
            is_closed=True,
        )

    @pytest.fixture
    def unclosed_candle(self):
        """Create an unclosed candle for testing."""
        return WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            open=Decimal("45000"),
            high=Decimal("46000"),
            low=Decimal("44000"),
            close=Decimal("45500"),
            volume=Decimal("100"),
            is_closed=False,
        )

    @pytest.mark.asyncio
    async def test_process_closed_candle(self, engine, strategy, closed_candle):
        """Test that closed candles are processed."""
        await engine.start()
        await engine.process_candle(closed_candle)

        assert engine.bar_count == 1
        assert engine.context.current_bar is not None
        assert engine.context.current_bar.close == Decimal("45500")
        # Strategy should have executed buy (price 45500 < threshold 50000)
        assert strategy.buy_executed is True

    @pytest.mark.asyncio
    async def test_skip_unclosed_candle(self, engine, unclosed_candle):
        """Test that unclosed candles are skipped."""
        await engine.start()
        await engine.process_candle(unclosed_candle)

        assert engine.bar_count == 0

    @pytest.mark.asyncio
    async def test_skip_when_not_running(self, engine, closed_candle):
        """Test that candles are skipped when engine is not running."""
        # Don't start the engine
        await engine.process_candle(closed_candle)

        assert engine.bar_count == 0

    @pytest.mark.asyncio
    async def test_skip_wrong_symbol(self, engine, closed_candle):
        """Test that candles for wrong symbol are skipped."""
        await engine.start()
        closed_candle.symbol = "ETH/USDT"
        await engine.process_candle(closed_candle)

        assert engine.bar_count == 0

    @pytest.mark.asyncio
    async def test_current_price_updated(self, engine, closed_candle):
        """Test that current price is updated from candle."""
        await engine.start()
        await engine.process_candle(closed_candle)

        assert engine._current_price == Decimal("45500")


class TestOrderSubmission:
    """Tests for order submission to exchange."""

    @pytest.fixture
    def closed_candle(self):
        """Create a closed candle that triggers buy."""
        return WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            open=Decimal("45000"),
            high=Decimal("46000"),
            low=Decimal("44000"),
            close=Decimal("45500"),
            volume=Decimal("100"),
            is_closed=True,
        )

    @pytest.mark.asyncio
    async def test_order_submitted_to_exchange(self, engine, mock_adapter, closed_candle):
        """Test that orders from strategy are submitted to exchange."""
        await engine.start()
        await engine.process_candle(closed_candle)

        # Order should be submitted to exchange
        mock_adapter.place_order.assert_called_once()
        call_args = mock_adapter.place_order.call_args[0][0]
        assert call_args.symbol == "BTC/USDT"
        assert call_args.side == OrderSide.BUY
        assert call_args.amount == Decimal("0.01")

    @pytest.mark.asyncio
    async def test_live_order_tracked(self, engine, closed_candle):
        """Test that submitted orders are tracked as live orders."""
        await engine.start()
        await engine.process_candle(closed_candle)

        assert len(engine._live_orders) == 1
        live_order = list(engine._live_orders.values())[0]
        assert live_order.exchange_order_id == "exchange-123"
        assert live_order.symbol == "BTC/USDT"

    @pytest.mark.asyncio
    async def test_exchange_order_map_updated(self, engine, closed_candle):
        """Test that exchange order map is updated."""
        await engine.start()
        await engine.process_candle(closed_candle)

        assert "exchange-123" in engine._exchange_order_map

    @pytest.mark.asyncio
    async def test_order_failure_marks_rejected(self, engine, mock_adapter, closed_candle):
        """Test that failed order submission marks order as rejected."""
        mock_adapter.place_order.side_effect = Exception("Exchange error")

        await engine.start()
        await engine.process_candle(closed_candle)

        # Order should be marked rejected
        assert len(engine.context.completed_orders) == 1
        rejected = engine.context.completed_orders[0]
        assert rejected.status == OrderStatus.REJECTED


class TestRiskValidation:
    """Tests for risk validation integration."""

    @pytest.fixture
    def large_order_strategy(self):
        """Strategy that places orders too large relative to max_order_size limit."""

        class LargeOrderStrategy(Strategy):
            def on_init(self) -> None:
                pass

            def on_bar(self, bar: Bar) -> None:
                # Try to buy 0.03 BTC at 45500 = 1365 USDT (13.65% of equity)
                # This exceeds 10% max_order_size but is within available cash
                self.ctx.buy(bar.symbol, Decimal("0.03"))

            def on_stop(self) -> None:
                pass

        return LargeOrderStrategy()

    @pytest.fixture
    def closed_candle(self):
        """Create a closed candle."""
        return WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            open=Decimal("45000"),
            high=Decimal("46000"),
            low=Decimal("44000"),
            close=Decimal("45500"),
            volume=Decimal("100"),
            is_closed=True,
        )

    @pytest.mark.asyncio
    async def test_order_exceeding_limit_rejected(
        self, run_id, large_order_strategy, risk_config, mock_adapter, closed_candle
    ):
        """Test that orders exceeding risk limits are rejected."""
        with patch("squant.config.get_settings") as mock_settings:
            settings = MagicMock()
            settings.paper_max_equity_curve_size = 10000
            settings.paper_max_completed_orders = 1000
            settings.paper_max_fills = 1000
            settings.paper_max_trades = 1000
            settings.paper_max_logs = 1000
            mock_settings.return_value = settings

            engine = LiveTradingEngine(
                run_id=run_id,
                strategy=large_order_strategy,
                symbol="BTC/USDT",
                timeframe="1m",
                adapter=mock_adapter,
                risk_config=risk_config,
                initial_equity=Decimal("10000"),
                params={},
            )

        await engine.start()
        await engine.process_candle(closed_candle)

        # Order should be rejected, not submitted to exchange
        mock_adapter.place_order.assert_not_called()
        # Order should be marked rejected in context
        assert len(engine.context.completed_orders) == 1
        assert engine.context.completed_orders[0].status == OrderStatus.REJECTED


class TestEmergencyClose:
    """Tests for emergency close functionality."""

    @pytest.mark.asyncio
    async def test_emergency_close_cancels_orders(self, engine, mock_adapter):
        """Test that emergency close cancels open orders."""
        await engine.start()

        # Simulate an open order
        engine._live_orders["order-1"] = LiveOrder(
            internal_id="order-1",
            exchange_order_id="exchange-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="limit",
            amount=Decimal("0.1"),
            price=Decimal("40000"),
            status=OrderStatus.SUBMITTED,
        )

        results = await engine.emergency_close()

        mock_adapter.cancel_order.assert_called_once()
        assert results["orders_cancelled"] == 1

    @pytest.mark.asyncio
    async def test_emergency_close_closes_positions(self, engine, mock_adapter):
        """Test that emergency close closes open positions."""
        await engine.start()

        # Simulate a position
        engine.context._positions["BTC/USDT"] = MagicMock()
        engine.context._positions["BTC/USDT"].is_open = True
        engine.context._positions["BTC/USDT"].amount = Decimal("0.5")

        await engine.emergency_close()

        # Should place market sell order
        mock_adapter.place_order.assert_called()
        call_args = mock_adapter.place_order.call_args[0][0]
        assert call_args.side == OrderSide.SELL
        assert call_args.type == "market"

    @pytest.mark.asyncio
    async def test_emergency_close_stops_engine(self, engine):
        """Test that emergency close stops the engine."""
        await engine.start()

        await engine.emergency_close()

        assert engine.is_running is False
        assert "Emergency close" in engine.error_message

    @pytest.mark.asyncio
    async def test_emergency_close_with_exchange_error(self, engine, mock_adapter):
        """Test emergency close when exchange API fails (TRD-038).

        When the exchange API is unavailable, the error should be recorded
        and reported in the results.
        """
        await engine.start()

        # Simulate a position
        engine.context._positions["BTC/USDT"] = MagicMock()
        engine.context._positions["BTC/USDT"].is_open = True
        engine.context._positions["BTC/USDT"].amount = Decimal("0.5")

        # Mock exchange failure
        mock_adapter.place_order.side_effect = Exception("Exchange API unavailable")

        results = await engine.emergency_close()

        # Should record the error
        assert len(results["errors"]) == 1
        assert "BTC/USDT" in results["errors"][0]["symbol"]
        assert "Exchange API unavailable" in results["errors"][0]["error"]
        assert results["positions_closed"] == 0

    @pytest.mark.asyncio
    async def test_emergency_close_partial_success(self, engine, mock_adapter):
        """Test emergency close with partial success (TRD-038).

        When some positions fail to close but others succeed, results should
        reflect both successes and failures.
        """
        await engine.start()

        # Simulate two positions
        engine.context._positions["BTC/USDT"] = MagicMock()
        engine.context._positions["BTC/USDT"].is_open = True
        engine.context._positions["BTC/USDT"].amount = Decimal("0.5")

        engine.context._positions["ETH/USDT"] = MagicMock()
        engine.context._positions["ETH/USDT"].is_open = True
        engine.context._positions["ETH/USDT"].amount = Decimal("2.0")

        # First call succeeds, second fails
        mock_adapter.place_order.side_effect = [
            MagicMock(),  # BTC/USDT succeeds
            Exception("Network timeout"),  # ETH/USDT fails
        ]

        results = await engine.emergency_close()

        # Should have partial success
        assert results["positions_closed"] == 1
        assert len(results["errors"]) == 1

    @pytest.mark.asyncio
    async def test_emergency_close_cancel_order_failure(self, engine, mock_adapter):
        """Test emergency close when order cancellation fails.

        Order cancellation failures should be logged but not prevent
        position closing attempts.
        """
        await engine.start()

        # Simulate an open order
        engine._live_orders["order-1"] = LiveOrder(
            internal_id="order-1",
            exchange_order_id="exchange-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="limit",
            amount=Decimal("0.1"),
            price=Decimal("40000"),
            status=OrderStatus.SUBMITTED,
        )

        # Simulate a position
        engine.context._positions["BTC/USDT"] = MagicMock()
        engine.context._positions["BTC/USDT"].is_open = True
        engine.context._positions["BTC/USDT"].amount = Decimal("0.5")

        # Cancel fails but place_order should still be called
        mock_adapter.cancel_order.side_effect = Exception("Cannot cancel")

        await engine.emergency_close()

        # Cancel attempt made but failed
        mock_adapter.cancel_order.assert_called_once()
        # Position close should still be attempted
        mock_adapter.place_order.assert_called()

    @pytest.mark.asyncio
    async def test_emergency_close_no_positions(self, engine, mock_adapter):
        """Test emergency close when there are no positions to close."""
        await engine.start()

        # No positions set up

        results = await engine.emergency_close()

        assert results["positions_closed"] == 0
        assert results["orders_cancelled"] == 0
        assert results["errors"] == []
        # Engine should still be stopped
        assert engine.is_running is False


class TestOrderUpdates:
    """Tests for WebSocket order updates."""

    @pytest.fixture
    def engine_with_order(self, engine):
        """Create an engine with a tracked order."""
        engine._live_orders["internal-1"] = LiveOrder(
            internal_id="internal-1",
            exchange_order_id="exchange-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="market",
            amount=Decimal("0.1"),
            price=None,
            status=OrderStatus.SUBMITTED,
        )
        engine._exchange_order_map["exchange-1"] = "internal-1"
        return engine

    def test_order_update_updates_status(self, engine_with_order):
        """Test that order updates change order status."""
        # Note: WSOrderUpdate.status is a string, not an enum
        update = WSOrderUpdate(
            order_id="exchange-1",
            client_order_id="internal-1",
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            status="filled",
            size=Decimal("0.1"),
            filled_size=Decimal("0.1"),
            avg_price=Decimal("45000"),
            fee=Decimal("0.45"),
            fee_currency="USDT",
        )

        engine_with_order.on_order_update(update)

        live_order = engine_with_order._live_orders["internal-1"]
        assert live_order.status == OrderStatus.FILLED
        assert live_order.filled_amount == Decimal("0.1")
        assert live_order.avg_fill_price == Decimal("45000")
        assert live_order.fee == Decimal("0.45")

    def test_unknown_order_update_ignored(self, engine_with_order):
        """Test that updates for unknown orders are ignored."""
        update = WSOrderUpdate(
            order_id="unknown-exchange-id",
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            status=OrderStatus.FILLED,
            size=Decimal("0.1"),
        )

        # Should not raise
        engine_with_order.on_order_update(update)


class TestStateSnapshot:
    """Tests for state snapshot functionality."""

    @pytest.mark.asyncio
    async def test_state_snapshot(self, engine):
        """Test that state snapshot contains correct data."""
        await engine.start()

        snapshot = engine.get_state_snapshot()

        assert snapshot["run_id"] == str(engine.run_id)
        assert snapshot["symbol"] == "BTC/USDT"
        assert snapshot["timeframe"] == "1m"
        assert snapshot["is_running"] is True
        assert snapshot["bar_count"] == 0
        assert Decimal(snapshot["cash"]) == Decimal("10000")
        assert Decimal(snapshot["equity"]) == Decimal("10000")
        assert snapshot["positions"] == {}
        assert snapshot["pending_orders"] == []
        assert "risk_state" in snapshot

    @pytest.mark.asyncio
    async def test_state_snapshot_includes_live_orders(self, engine):
        """Test that state snapshot includes live orders."""
        await engine.start()

        # Add a live order
        engine._live_orders["order-1"] = LiveOrder(
            internal_id="order-1",
            exchange_order_id="exchange-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="limit",
            amount=Decimal("0.1"),
            price=Decimal("40000"),
            status=OrderStatus.SUBMITTED,
        )

        snapshot = engine.get_state_snapshot()

        assert len(snapshot["live_orders"]) == 1
        assert snapshot["live_orders"][0]["internal_id"] == "order-1"
        assert snapshot["live_orders"][0]["exchange_id"] == "exchange-1"


class TestPendingSnapshots:
    """Tests for pending snapshot management."""

    @pytest.fixture
    def closed_candle(self):
        """Create a closed candle."""
        return WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            open=Decimal("45000"),
            high=Decimal("46000"),
            low=Decimal("44000"),
            close=Decimal("45500"),
            volume=Decimal("100"),
            is_closed=True,
        )

    @pytest.mark.asyncio
    async def test_pending_snapshots_collected(self, engine, closed_candle):
        """Test that pending snapshots are collected."""
        await engine.start()

        # Process multiple candles
        for i in range(5):
            closed_candle.timestamp = datetime(2024, 1, 1, 12, i, 0, tzinfo=UTC)
            await engine.process_candle(closed_candle)

        snapshots = engine.get_pending_snapshots()
        assert len(snapshots) == 5

        # After getting, should be cleared
        assert len(engine.get_pending_snapshots()) == 0

    @pytest.mark.asyncio
    async def test_should_persist_snapshots(self, engine, closed_candle):
        """Test persistence threshold check."""
        await engine.start()

        # Process bars below batch size
        for i in range(5):
            closed_candle.timestamp = datetime(2024, 1, 1, 12, i, 0, tzinfo=UTC)
            await engine.process_candle(closed_candle)

        assert engine.should_persist_snapshots() is False

        # Process more to exceed batch size (default is 10)
        for i in range(5, 10):
            closed_candle.timestamp = datetime(2024, 1, 1, 12, i, 0, tzinfo=UTC)
            await engine.process_candle(closed_candle)

        assert engine.should_persist_snapshots() is True


class TestHealthCheck:
    """Tests for health check functionality."""

    @pytest.mark.asyncio
    async def test_last_active_at_set_on_start(self, engine):
        """Test that last_active_at is set when engine starts."""
        assert engine.last_active_at is None

        await engine.start()

        assert engine.last_active_at is not None

    @pytest.mark.asyncio
    async def test_last_active_at_updated_on_candle(self, engine):
        """Test that last_active_at is updated when processing candles."""
        await engine.start()
        initial_time = engine.last_active_at

        candle = WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            open=Decimal("45000"),
            high=Decimal("46000"),
            low=Decimal("44000"),
            close=Decimal("45500"),
            volume=Decimal("100"),
            is_closed=True,
        )
        await engine.process_candle(candle)

        assert engine.last_active_at >= initial_time

    @pytest.mark.asyncio
    async def test_is_healthy_returns_true_when_active(self, engine):
        """Test is_healthy returns True when recently active."""
        await engine.start()

        assert engine.is_healthy(timeout_seconds=300) is True

    @pytest.mark.asyncio
    async def test_is_healthy_returns_false_when_not_running(self, engine):
        """Test is_healthy returns False when not running."""
        # Engine not started
        assert engine.is_healthy(timeout_seconds=300) is False

    @pytest.mark.asyncio
    async def test_is_healthy_returns_false_when_stopped(self, engine):
        """Test is_healthy returns False after stop."""
        await engine.start()
        await engine.stop()

        assert engine.is_healthy(timeout_seconds=300) is False

    @pytest.mark.asyncio
    async def test_is_healthy_with_zero_timeout(self, engine):
        """Test is_healthy with very short timeout."""
        await engine.start()

        # With 0 second timeout, should be considered unhealthy
        # since any elapsed time > 0
        import asyncio

        await asyncio.sleep(0.01)
        assert engine.is_healthy(timeout_seconds=0) is False


class TestCancelAllOrders:
    """Tests for cancel all orders functionality."""

    @pytest.mark.asyncio
    async def test_cancel_all_orders(self, engine, mock_adapter):
        """Test that all open orders are cancelled."""
        await engine.start()

        # Add multiple orders
        engine._live_orders["order-1"] = LiveOrder(
            internal_id="order-1",
            exchange_order_id="exchange-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="limit",
            amount=Decimal("0.1"),
            price=Decimal("40000"),
            status=OrderStatus.SUBMITTED,
        )
        engine._live_orders["order-2"] = LiveOrder(
            internal_id="order-2",
            exchange_order_id="exchange-2",
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            order_type="limit",
            amount=Decimal("0.1"),
            price=Decimal("50000"),
            status=OrderStatus.SUBMITTED,
        )

        await engine.stop(cancel_orders=True)

        # Both orders should be cancelled
        assert mock_adapter.cancel_order.call_count == 2

    @pytest.mark.asyncio
    async def test_stop_without_cancel(self, engine, mock_adapter):
        """Test stopping without cancelling orders."""
        await engine.start()

        # Add an order
        engine._live_orders["order-1"] = LiveOrder(
            internal_id="order-1",
            exchange_order_id="exchange-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="limit",
            amount=Decimal("0.1"),
            price=Decimal("40000"),
            status=OrderStatus.SUBMITTED,
        )

        await engine.stop(cancel_orders=False)

        # Order should not be cancelled
        mock_adapter.cancel_order.assert_not_called()


class TestCircuitBreakerIntegration:
    """Tests for circuit breaker integration with risk manager (RSK-012)."""

    @pytest.fixture
    def circuit_breaker_config(self):
        """Create a risk config with circuit breaker enabled and low threshold."""
        return RiskConfig(
            max_position_size=Decimal("0.5"),
            max_order_size=Decimal("0.1"),
            daily_trade_limit=100,
            daily_loss_limit=Decimal("0.1"),
            max_price_deviation=Decimal("0.05"),
            circuit_breaker_enabled=True,
            circuit_breaker_loss_count=3,  # Trigger after 3 consecutive losses
            circuit_breaker_cooldown_minutes=30,
        )

    @pytest.fixture
    def engine_with_circuit_breaker(self, run_id, strategy, circuit_breaker_config, mock_adapter):
        """Create a live trading engine with circuit breaker config."""
        with patch("squant.config.get_settings") as mock_settings:
            settings = MagicMock()
            settings.paper_max_equity_curve_size = 10000
            settings.paper_max_completed_orders = 1000
            settings.paper_max_fills = 1000
            settings.paper_max_trades = 1000
            settings.paper_max_logs = 1000
            mock_settings.return_value = settings

            return LiveTradingEngine(
                run_id=run_id,
                strategy=strategy,
                symbol="BTC/USDT",
                timeframe="1m",
                adapter=mock_adapter,
                risk_config=circuit_breaker_config,
                initial_equity=Decimal("10000"),
                params={"threshold": Decimal("50000")},
            )

    def test_circuit_breaker_flag_initially_false(self, engine_with_circuit_breaker):
        """Test circuit breaker flag is initially False."""
        assert engine_with_circuit_breaker.circuit_breaker_triggered is False

    def test_circuit_breaker_property(self, engine_with_circuit_breaker):
        """Test circuit_breaker_triggered property accessor."""
        engine = engine_with_circuit_breaker

        # Initially false
        assert engine.circuit_breaker_triggered is False

        # Set internal flag
        engine._circuit_breaker_triggered = True

        # Property should reflect internal state
        assert engine.circuit_breaker_triggered is True

    @pytest.mark.asyncio
    async def test_on_order_update_records_trade_pnl(self, engine_with_circuit_breaker, mock_adapter):
        """Test that on_order_update records trade PnL for risk management."""
        engine = engine_with_circuit_breaker
        await engine.start()

        # Set up an order
        internal_id = "order-1"
        exchange_id = "exchange-123"
        engine._live_orders[internal_id] = LiveOrder(
            internal_id=internal_id,
            exchange_order_id=exchange_id,
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="market",
            amount=Decimal("0.1"),
            price=None,
            status=OrderStatus.SUBMITTED,
        )
        engine._exchange_order_map[exchange_id] = internal_id

        # Mock a completed trade with a loss
        with patch.object(engine._context, "_process_fill"), \
             patch.object(engine._context, "_move_completed_orders"):
            # Simulate trades list growing (indicating new trade completed)
            mock_trade = MagicMock()
            mock_trade.pnl = Decimal("-100")  # Loss

            engine._context._trades = []  # Before: 0 trades

            # Create order update
            update = WSOrderUpdate(
                order_id=exchange_id,
                client_order_id=None,
                status="filled",
                symbol="BTC/USDT",
                side="buy",
                order_type="market",
                price=Decimal("50000"),
                size=Decimal("0.1"),
                filled_size=Decimal("0.1"),
                avg_price=Decimal("50000"),
                fee=Decimal("0.05"),
                fee_currency="USDT",
                timestamp=datetime.now(UTC),
            )

            # Patch trades to return mock trade after processing
            def mock_process_fill(*args, **kwargs):
                engine._context._trades = [mock_trade]

            with patch.object(engine._context, "_process_fill", side_effect=mock_process_fill), \
                 patch.object(engine._context, "_move_completed_orders"):
                engine.on_order_update(update)

            # Check that consecutive_losses increased
            assert engine._risk_manager.state.consecutive_losses == 1

    @pytest.mark.asyncio
    async def test_circuit_breaker_triggered_after_consecutive_losses(
        self, engine_with_circuit_breaker, mock_adapter
    ):
        """Test circuit breaker triggers after configured consecutive losses."""
        engine = engine_with_circuit_breaker
        await engine.start()

        # Simulate consecutive losses by directly calling risk manager
        for i in range(3):  # circuit_breaker_loss_count = 3
            engine._risk_manager.record_trade_result(Decimal("-100"))

        # Circuit breaker should be triggered in risk manager
        assert engine._risk_manager.state.circuit_breaker_triggered is True

    @pytest.mark.asyncio
    async def test_process_candle_stops_when_circuit_breaker_triggered(
        self, engine_with_circuit_breaker, mock_adapter
    ):
        """Test that process_candle stops engine when circuit breaker is triggered."""
        engine = engine_with_circuit_breaker
        await engine.start()

        assert engine.is_running is True

        # Manually set circuit breaker flag (simulating it was set in on_order_update)
        engine._circuit_breaker_triggered = True

        # Create a candle
        candle = WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            open=Decimal("45000"),
            high=Decimal("46000"),
            low=Decimal("44000"),
            close=Decimal("45500"),
            volume=Decimal("100"),
            is_closed=True,
        )

        # Process candle - should stop engine due to circuit breaker
        await engine.process_candle(candle)

        # Engine should be stopped
        assert engine.is_running is False
        assert "Circuit breaker triggered" in engine.error_message

    @pytest.mark.asyncio
    async def test_process_candle_continues_without_circuit_breaker(
        self, engine_with_circuit_breaker, mock_adapter
    ):
        """Test that process_candle continues normally without circuit breaker."""
        engine = engine_with_circuit_breaker
        await engine.start()

        assert engine.is_running is True
        assert engine._circuit_breaker_triggered is False

        # Create a candle
        candle = WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            open=Decimal("45000"),
            high=Decimal("46000"),
            low=Decimal("44000"),
            close=Decimal("45500"),
            volume=Decimal("100"),
            is_closed=True,
        )

        # Process candle - should continue normally
        await engine.process_candle(candle)

        # Engine should still be running
        assert engine.is_running is True
        assert engine.bar_count == 1

    @pytest.mark.asyncio
    async def test_winning_trade_resets_consecutive_losses(
        self, engine_with_circuit_breaker, mock_adapter
    ):
        """Test that a winning trade resets consecutive loss count."""
        engine = engine_with_circuit_breaker
        await engine.start()

        # Record some losses
        engine._risk_manager.record_trade_result(Decimal("-100"))
        engine._risk_manager.record_trade_result(Decimal("-100"))
        assert engine._risk_manager.state.consecutive_losses == 2

        # Record a win
        engine._risk_manager.record_trade_result(Decimal("100"))

        # Consecutive losses should be reset
        assert engine._risk_manager.state.consecutive_losses == 0
        assert engine._risk_manager.state.circuit_breaker_triggered is False

    @pytest.mark.asyncio
    async def test_circuit_breaker_triggers_global_stop(
        self, engine_with_circuit_breaker, mock_adapter
    ):
        """Test that circuit breaker triggers global stop of all sessions (Issue 033)."""
        engine = engine_with_circuit_breaker
        await engine.start()

        # Mock the session managers - patch at the import source
        with patch("squant.engine.live.manager.get_live_session_manager") as mock_get_live, \
             patch("squant.engine.paper.manager.get_session_manager") as mock_get_paper:

            mock_live_manager = MagicMock()
            mock_live_manager.stop_all = AsyncMock()
            mock_get_live.return_value = mock_live_manager

            mock_paper_manager = MagicMock()
            mock_paper_manager.stop_all = AsyncMock()
            mock_get_paper.return_value = mock_paper_manager

            # Set circuit breaker flag
            engine._circuit_breaker_triggered = True

            # Create a candle
            candle = WSCandle(
                symbol="BTC/USDT",
                timeframe="1m",
                timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
                open=Decimal("45000"),
                high=Decimal("46000"),
                low=Decimal("44000"),
                close=Decimal("45500"),
                volume=Decimal("100"),
                is_closed=True,
            )

            # Process candle - should trigger global circuit breaker
            await engine.process_candle(candle)

            # Both managers should have stop_all called
            mock_live_manager.stop_all.assert_called_once()
            mock_paper_manager.stop_all.assert_called_once()

            # Verify reason contains the run_id
            live_call_args = mock_live_manager.stop_all.call_args
            assert str(engine.run_id) in live_call_args.kwargs.get("reason", "")
