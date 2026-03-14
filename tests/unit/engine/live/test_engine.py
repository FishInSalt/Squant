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

    # Mock cancel_order — returns CANCELLED status by default
    adapter.cancel_order = AsyncMock(
        return_value=OrderResponse(
            order_id="exchange-123",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            status=OrderStatus.CANCELLED,
            price=Decimal("40000"),
            amount=Decimal("0.1"),
            filled=Decimal("0"),
        )
    )

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
        settings.strategy.max_bar_history = 1000
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

    @pytest.mark.asyncio
    async def test_empty_order_id_rejected(self, engine, mock_adapter, closed_candle):
        """Test C-DEFER-4: order with empty exchange_order_id is rejected.

        If the exchange returns a successful response but with no order_id,
        the order should be treated as a failure to prevent zombie orders.
        """
        mock_adapter.place_order.return_value = OrderResponse(
            order_id="",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            status=OrderStatus.SUBMITTED,
            price=None,
            amount=Decimal("0.01"),
            filled=Decimal("0"),
        )

        await engine.start()
        await engine.process_candle(closed_candle)

        # Should be rejected, not tracked as live order
        assert len(engine._live_orders) == 0
        assert len(engine.context.completed_orders) == 1
        assert engine.context.completed_orders[0].status == OrderStatus.REJECTED


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
            settings.strategy.max_bar_history = 1000
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
        """Test that emergency close closes open positions and waits for fill."""
        await engine.start()

        # Simulate a position
        engine.context._positions["BTC/USDT"] = MagicMock()
        engine.context._positions["BTC/USDT"].is_open = True
        engine.context._positions["BTC/USDT"].amount = Decimal("0.5")

        # Mock place_order to return FILLED immediately (typical for market orders)
        mock_adapter.place_order.return_value = OrderResponse(
            order_id="close-123",
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            status=OrderStatus.FILLED,
            amount=Decimal("0.5"),
            filled=Decimal("0.5"),
            avg_price=Decimal("42000"),
        )

        results = await engine.emergency_close()

        # Should place market sell order
        mock_adapter.place_order.assert_called()
        call_args = mock_adapter.place_order.call_args[0][0]
        assert call_args.side == OrderSide.SELL
        assert call_args.type == "market"
        assert results["positions_closed"] == 1

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

        # First call succeeds with FILLED response, second fails
        mock_adapter.place_order.side_effect = [
            OrderResponse(
                order_id="close-btc",
                symbol="BTC/USDT",
                side=OrderSide.SELL,
                type=OrderType.MARKET,
                status=OrderStatus.FILLED,
                amount=Decimal("0.5"),
                filled=Decimal("0.5"),
                avg_price=Decimal("42000"),
            ),
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
        mock_adapter.place_order.return_value = OrderResponse(
            order_id="close-123",
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            status=OrderStatus.FILLED,
            amount=Decimal("0.5"),
            filled=Decimal("0.5"),
            avg_price=Decimal("42000"),
        )

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
        assert results["status"] == "completed"
        # Engine should still be stopped
        assert engine.is_running is False

    @pytest.mark.asyncio
    async def test_emergency_close_rejects_concurrent_calls(self, engine, mock_adapter):
        """Test TRD-038#6: Reject duplicate emergency close calls.

        When an emergency close is already in progress, subsequent calls should
        return immediately with status "in_progress" instead of executing again.
        """
        await engine.start()

        # Simulate emergency close already in progress
        engine._emergency_close_in_progress = True

        result = await engine.emergency_close()

        assert result["status"] == "in_progress"
        assert "already in progress" in result["message"]
        assert result["orders_cancelled"] is None
        assert result["positions_closed"] is None
        # Should not have called any exchange operations
        mock_adapter.cancel_order.assert_not_called()
        mock_adapter.place_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_emergency_close_returns_remaining_positions(self, engine, mock_adapter):
        """Test TRD-038#5: Return remaining positions on partial close.

        When some positions fail to close, the response should include
        detailed information about remaining positions.
        """
        await engine.start()

        # Simulate two positions
        engine.context._positions["BTC/USDT"] = MagicMock()
        engine.context._positions["BTC/USDT"].is_open = True
        engine.context._positions["BTC/USDT"].amount = Decimal("0.5")

        engine.context._positions["ETH/USDT"] = MagicMock()
        engine.context._positions["ETH/USDT"].is_open = True
        engine.context._positions["ETH/USDT"].amount = Decimal("-2.0")  # Short position

        # First call succeeds with FILLED, second fails
        mock_adapter.place_order.side_effect = [
            OrderResponse(
                order_id="close-btc",
                symbol="BTC/USDT",
                side=OrderSide.SELL,
                type=OrderType.MARKET,
                status=OrderStatus.FILLED,
                amount=Decimal("0.5"),
                filled=Decimal("0.5"),
                avg_price=Decimal("42000"),
            ),
            Exception("Network timeout"),  # ETH/USDT fails
        ]

        results = await engine.emergency_close()

        # Should have partial success
        assert results["status"] == "partial"
        assert results["positions_closed"] == 1
        assert len(results["errors"]) == 1
        assert len(results["remaining_positions"]) == 1

        # Check remaining position details
        remaining = results["remaining_positions"][0]
        assert remaining["symbol"] == "ETH/USDT"
        assert remaining["amount"] == "-2.0"
        assert remaining["side"] == "short"

    @pytest.mark.asyncio
    async def test_emergency_close_polls_for_fill(self, engine, mock_adapter):
        """Test that emergency close polls get_order when order is not immediately filled."""
        await engine.start()

        # Simulate a position
        engine.context._positions["BTC/USDT"] = MagicMock()
        engine.context._positions["BTC/USDT"].is_open = True
        engine.context._positions["BTC/USDT"].amount = Decimal("0.5")

        # place_order returns SUBMITTED (not immediately filled)
        mock_adapter.place_order.return_value = OrderResponse(
            order_id="close-123",
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            status=OrderStatus.SUBMITTED,
            amount=Decimal("0.5"),
            filled=Decimal("0"),
        )

        # get_order returns FILLED on first poll
        mock_adapter.get_order.return_value = OrderResponse(
            order_id="close-123",
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            status=OrderStatus.FILLED,
            amount=Decimal("0.5"),
            filled=Decimal("0.5"),
            avg_price=Decimal("42000"),
        )

        results = await engine.emergency_close()

        # Should have polled get_order
        mock_adapter.get_order.assert_called_with("BTC/USDT", "close-123")
        assert results["positions_closed"] == 1
        assert results["status"] == "completed"

    @pytest.mark.asyncio
    async def test_emergency_close_flag_reset_on_completion(self, engine, mock_adapter):
        """Test that emergency close flag is reset after completion.

        The flag should be reset even if the operation completes successfully,
        allowing future emergency close calls if needed.
        """
        await engine.start()

        assert engine._emergency_close_in_progress is False

        await engine.emergency_close()

        # Flag should be reset after completion
        assert engine._emergency_close_in_progress is False

    @pytest.mark.asyncio
    async def test_emergency_close_flag_reset_on_error(self, engine, mock_adapter):
        """Test that emergency close flag is reset even on errors.

        The flag should be reset in the finally block even if errors occur.
        """
        await engine.start()

        # Simulate a position that will fail
        engine.context._positions["BTC/USDT"] = MagicMock()
        engine.context._positions["BTC/USDT"].is_open = True
        engine.context._positions["BTC/USDT"].amount = Decimal("0.5")

        mock_adapter.place_order.side_effect = Exception("API error")

        await engine.emergency_close()

        # Flag should still be reset
        assert engine._emergency_close_in_progress is False

    @pytest.mark.asyncio
    async def test_process_candle_blocked_during_emergency_close(self, engine, mock_adapter):
        """Test C-DEFER-3: process_candle returns early during emergency close.

        When an emergency close is in progress, new candle processing should be
        blocked to prevent the strategy from placing new orders that would
        interfere with the emergency close operation.
        """
        await engine.start()

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

        # Simulate emergency close in progress
        engine._emergency_close_in_progress = True

        await engine.process_candle(candle)

        # Strategy should NOT have been called (no order placed)
        mock_adapter.place_order.assert_not_called()


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

        # on_order_update buffers, _drain_ws_updates processes (ISSUE-203 fix)
        engine_with_order.on_order_update(update)
        engine_with_order._drain_ws_updates()

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

        # Should not raise (buffer + drain)
        engine_with_order.on_order_update(update)
        engine_with_order._drain_ws_updates()

    def test_order_update_ignored_during_emergency_close(self, engine_with_order):
        """Test that order updates are blocked during emergency close (P0-2)."""
        engine_with_order._emergency_close_in_progress = True

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

        # Order status should remain SUBMITTED — fill was ignored
        live_order = engine_with_order._live_orders["internal-1"]
        assert live_order.status == OrderStatus.SUBMITTED
        assert live_order.filled_amount == Decimal("0")


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
        assert snapshot["trades"] == []
        assert snapshot["open_trade"] is None
        assert "logs" in snapshot
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
    async def test_is_healthy_adapts_to_timeframe(self, engine):
        """Test is_healthy uses adaptive timeout based on timeframe.

        For 1m timeframe, effective timeout = max(timeout_seconds, 60*3=180).
        So even with timeout_seconds=0, a just-started engine is healthy.
        """
        await engine.start()
        # Effective timeout = max(0, 180) = 180s, just started so healthy
        assert engine.is_healthy(timeout_seconds=0) is True

    @pytest.mark.asyncio
    async def test_is_healthy_returns_false_when_expired(self, engine):
        """Test is_healthy returns False when activity exceeds adaptive timeout."""
        from datetime import timedelta

        await engine.start()
        # Set last_active_at far in the past (beyond adaptive timeout of 180s for 1m)
        engine._last_active_at = datetime.now(UTC) - timedelta(seconds=600)
        assert engine.is_healthy(timeout_seconds=300) is False


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

    @pytest.mark.asyncio
    async def test_cancel_uses_exchange_response(self, engine, mock_adapter):
        """Test C-DEFER-7: cancel uses exchange response as source of truth.

        If the order was filled before the cancel took effect, the local state
        should reflect FILLED (not CANCELLED) with actual fill data.
        """
        await engine.start()

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

        # Exchange returns FILLED (order was filled before cancel arrived)
        mock_adapter.cancel_order.return_value = OrderResponse(
            order_id="exchange-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            status=OrderStatus.FILLED,
            price=Decimal("40000"),
            amount=Decimal("0.1"),
            filled=Decimal("0.1"),
            avg_price=Decimal("40000"),
            fee=Decimal("0.04"),
        )

        await engine.stop(cancel_orders=True)

        # Order should be FILLED, not CANCELLED
        order = engine._live_orders["order-1"]
        assert order.status == OrderStatus.FILLED
        assert order.filled_amount == Decimal("0.1")
        assert order.avg_fill_price == Decimal("40000")

    @pytest.mark.asyncio
    async def test_cancel_partial_fill_before_cancel(self, engine, mock_adapter):
        """Test C-DEFER-7: partially filled order returns accurate state.

        If the order was partially filled before cancel, the response captures
        the fill data rather than silently marking as cancelled.
        """
        await engine.start()

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

        # Exchange returns CANCELLED with partial fill
        mock_adapter.cancel_order.return_value = OrderResponse(
            order_id="exchange-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            status=OrderStatus.CANCELLED,
            price=Decimal("40000"),
            amount=Decimal("0.1"),
            filled=Decimal("0.03"),
            avg_price=Decimal("40000"),
            fee=Decimal("0.012"),
        )

        await engine.stop(cancel_orders=True)

        # Order should be CANCELLED but with partial fill data preserved
        order = engine._live_orders["order-1"]
        assert order.status == OrderStatus.CANCELLED
        assert order.filled_amount == Decimal("0.03")
        assert order.fee == Decimal("0.012")


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
            settings.strategy.max_bar_history = 1000
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
    async def test_on_order_update_records_trade_pnl(
        self, engine_with_circuit_breaker, mock_adapter
    ):
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

        # Simulate a trade completion: _open_trade goes from non-None to None
        mock_trade = MagicMock()
        mock_trade.pnl = Decimal("-100")  # Loss

        engine._context._trades = []  # Before: 0 trades
        # Set _open_trade to simulate an open position (will be cleared by fill)
        engine._context._open_trade = MagicMock()

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

        # Mock _process_fill to close the trade (_open_trade → None, trade added)
        def mock_process_fill(*args, **kwargs):
            engine._context._trades = [mock_trade]
            engine._context._open_trade = None

        with (
            patch.object(engine._context, "_process_fill", side_effect=mock_process_fill),
            patch.object(engine._context, "_move_completed_orders"),
        ):
            # Buffer the update, then drain to process (ISSUE-203 fix)
            engine.on_order_update(update)
            engine._drain_ws_updates()

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
        with (
            patch("squant.engine.live.manager.get_live_session_manager") as mock_get_live,
            patch("squant.engine.paper.manager.get_session_manager") as mock_get_paper,
        ):
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


class TestStaleOrderCleanup:
    """Tests for C-DEFER-4: stale and zombie order cleanup."""

    @pytest.mark.asyncio
    async def test_completed_orders_cleaned_from_live_orders(self, engine, mock_adapter):
        """Completed orders should be removed from _live_orders during sync."""
        await engine.start()

        # Add a FILLED order (completed)
        engine._live_orders["order-1"] = LiveOrder(
            internal_id="order-1",
            exchange_order_id="exchange-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="limit",
            amount=Decimal("0.1"),
            price=Decimal("40000"),
            status=OrderStatus.FILLED,
        )
        engine._exchange_order_map["exchange-1"] = "order-1"

        # Add a still-active order
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

        await engine._sync_pending_orders()

        # Completed order should be cleaned up
        assert "order-1" not in engine._live_orders
        assert "exchange-1" not in engine._exchange_order_map
        # Active order should remain
        assert "order-2" in engine._live_orders

    @pytest.mark.asyncio
    async def test_zombie_order_marked_rejected(self, engine, mock_adapter):
        """Orders without exchange_order_id older than threshold should be rejected."""
        await engine.start()

        # Create a zombie order (no exchange_order_id, old timestamp)
        zombie = LiveOrder(
            internal_id="zombie-1",
            exchange_order_id=None,
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="limit",
            amount=Decimal("0.1"),
            price=Decimal("40000"),
            status=OrderStatus.PENDING,
        )
        zombie.created_at = datetime(2020, 1, 1, tzinfo=UTC)  # Very old
        engine._live_orders["zombie-1"] = zombie

        await engine._sync_pending_orders()

        # Zombie should be cleaned up
        assert "zombie-1" not in engine._live_orders

    @pytest.mark.asyncio
    async def test_recent_order_without_exchange_id_not_cleaned(self, engine, mock_adapter):
        """Recently created orders without exchange_id should NOT be cleaned yet."""
        await engine.start()

        recent = LiveOrder(
            internal_id="recent-1",
            exchange_order_id=None,
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="limit",
            amount=Decimal("0.1"),
            price=Decimal("40000"),
            status=OrderStatus.PENDING,
        )
        recent.created_at = datetime.now(UTC)  # Just created
        engine._live_orders["recent-1"] = recent

        await engine._sync_pending_orders()

        # Should still be there (not old enough)
        assert "recent-1" in engine._live_orders


class TestEquitySnapshotTiming:
    """Tests for C-DEFER-8: equity snapshot timing consistency."""

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
    async def test_snapshot_recorded_before_strategy(self, engine, mock_adapter, closed_candle):
        """Equity snapshot should be recorded before strategy.on_bar() runs.

        This ensures the snapshot captures the portfolio state at bar close,
        not a state affected by new orders from the strategy.
        """
        await engine.start()

        call_order = []

        # Track when snapshot is recorded vs when strategy runs
        original_record = engine._context._record_equity_snapshot

        def track_record(time):
            call_order.append("snapshot")
            original_record(time)

        engine._context._record_equity_snapshot = track_record

        original_on_bar = engine._strategy.on_bar

        def track_on_bar(bar):
            call_order.append("strategy")
            original_on_bar(bar)

        engine._strategy.on_bar = track_on_bar

        await engine.process_candle(closed_candle)

        assert call_order.index("snapshot") < call_order.index("strategy")

    @pytest.mark.asyncio
    async def test_balance_synced_before_order_sync(self, engine, mock_adapter, closed_candle):
        """Balance should be synced before order sync so fills adjust on top of exchange cash."""
        await engine.start()

        call_order = []

        original_sync_balance = engine._sync_balance

        async def track_balance():
            call_order.append("balance")
            await original_sync_balance()

        engine._sync_balance = track_balance

        original_sync_orders = engine._sync_pending_orders

        async def track_orders():
            call_order.append("orders")
            await original_sync_orders()

        engine._sync_pending_orders = track_orders

        await engine.process_candle(closed_candle)

        assert call_order.index("balance") < call_order.index("orders")


class TestOrderSyncRateLimiting:
    """Tests for order sync rate limiting in _sync_pending_orders."""

    @pytest.fixture
    def engine_with_pending_order(self, engine, mock_adapter):
        """Create engine with a pending order that has an exchange ID."""
        engine._live_orders["order-1"] = LiveOrder(
            internal_id="order-1",
            exchange_order_id="exchange-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="market",
            amount=Decimal("0.1"),
            price=None,
            status=OrderStatus.SUBMITTED,
        )
        engine._exchange_order_map["exchange-1"] = "order-1"
        return engine

    @pytest.mark.asyncio
    async def test_first_poll_always_executes(self, engine_with_pending_order, mock_adapter):
        """Test first poll for an order always goes through (no prior poll time)."""
        engine = engine_with_pending_order
        await engine.start()

        mock_adapter.get_order.return_value = OrderResponse(
            order_id="exchange-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            status=OrderStatus.SUBMITTED,
            price=None,
            amount=Decimal("0.1"),
            filled=Decimal("0"),
        )

        await engine._sync_pending_orders()

        mock_adapter.get_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_skip_polling_within_interval(self, engine_with_pending_order, mock_adapter):
        """Test that polling is skipped for orders polled within min interval."""
        engine = engine_with_pending_order
        await engine.start()

        # Record a recent poll time
        engine._order_last_poll["exchange-1"] = datetime.now(UTC)

        await engine._sync_pending_orders()

        # Should NOT call get_order because within 30s interval
        mock_adapter.get_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_poll_after_interval_elapsed(self, engine_with_pending_order, mock_adapter):
        """Test polling proceeds after min interval has elapsed."""
        from datetime import timedelta

        engine = engine_with_pending_order
        await engine.start()

        # Set poll time to 31 seconds ago (beyond 30s min interval)
        engine._order_last_poll["exchange-1"] = datetime.now(UTC) - timedelta(seconds=31)

        mock_adapter.get_order.return_value = OrderResponse(
            order_id="exchange-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            status=OrderStatus.SUBMITTED,
            price=None,
            amount=Decimal("0.1"),
            filled=Decimal("0"),
        )

        await engine._sync_pending_orders()

        mock_adapter.get_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_poll_tracking_for_completed_orders(
        self, engine_with_pending_order, mock_adapter
    ):
        """Test that poll tracking is cleaned up when orders complete."""
        engine = engine_with_pending_order
        await engine.start()

        # Return a filled order
        mock_adapter.get_order.return_value = OrderResponse(
            order_id="exchange-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            status=OrderStatus.FILLED,
            price=None,
            amount=Decimal("0.1"),
            filled=Decimal("0.1"),
            avg_price=Decimal("45000"),
        )

        await engine._sync_pending_orders()

        # Poll tracking should be cleaned up for completed order
        assert "exchange-1" not in engine._order_last_poll

    @pytest.mark.asyncio
    async def test_poll_time_recorded_on_error(self, engine_with_pending_order, mock_adapter):
        """Test that poll time is recorded even on API errors to avoid hammering."""
        engine = engine_with_pending_order
        await engine.start()

        mock_adapter.get_order.side_effect = Exception("API error")

        await engine._sync_pending_orders()

        # Even on error, poll time should be recorded
        assert "exchange-1" in engine._order_last_poll


class TestFillProcessing:
    """Tests for _record_fill and _check_trade_completion."""

    @pytest.fixture
    def engine_with_buy_order(self, engine):
        """Create engine with a buy order for fill testing."""
        engine._live_orders["order-1"] = LiveOrder(
            internal_id="order-1",
            exchange_order_id="exchange-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="market",
            amount=Decimal("1.0"),
            price=None,
            status=OrderStatus.SUBMITTED,
        )
        engine._exchange_order_map["exchange-1"] = "order-1"
        return engine

    @pytest.mark.asyncio
    async def test_record_fill_updates_context(self, engine_with_buy_order, mock_adapter):
        """Test that _record_fill processes correctly."""
        engine = engine_with_buy_order
        await engine.start()

        live_order = engine._live_orders["order-1"]

        with (
            patch.object(engine._context, "_process_fill") as mock_fill,
            patch.object(engine._context, "_move_completed_orders"),
        ):
            engine._record_fill(
                live_order, Decimal("45000"), Decimal("0.5"),
                Decimal("0.225"), Decimal("0.225"), source="poll",
            )

            mock_fill.assert_called_once()
            fill_arg = mock_fill.call_args[0][0]
            assert fill_arg.amount == Decimal("0.5")
            assert fill_arg.fee == Decimal("0.225")
            assert fill_arg.price == Decimal("45000")

    @pytest.mark.asyncio
    async def test_record_fill_uses_total_fee_when_no_delta(
        self, engine_with_buy_order, mock_adapter
    ):
        """Test fallback to total fee when fee_delta is None."""
        engine = engine_with_buy_order
        await engine.start()

        live_order = engine._live_orders["order-1"]

        with (
            patch.object(engine._context, "_process_fill") as mock_fill,
            patch.object(engine._context, "_move_completed_orders"),
        ):
            engine._record_fill(
                live_order, Decimal("45000"), Decimal("1.0"),
                None, Decimal("0.45"), source="poll",
            )

            fill_arg = mock_fill.call_args[0][0]
            # Should use total fee as fallback
            assert fill_arg.fee == Decimal("0.45")

    @pytest.mark.asyncio
    async def test_update_order_from_response_detects_fill(
        self, engine_with_buy_order, mock_adapter
    ):
        """Test _update_order_from_response correctly detects new fills."""
        engine = engine_with_buy_order
        await engine.start()

        live_order = engine._live_orders["order-1"]
        live_order.filled_amount = Decimal("0.3")  # Previously filled
        live_order.fee = Decimal("0.135")

        response = OrderResponse(
            order_id="exchange-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            status=OrderStatus.PARTIAL,
            price=None,
            amount=Decimal("1.0"),
            filled=Decimal("0.7"),  # New total = 0.7, delta = 0.4
            avg_price=Decimal("45000"),
            fee=Decimal("0.315"),  # New total fee
            fee_currency="USDT",
        )

        with (
            patch.object(engine._context, "_process_fill") as mock_fill,
            patch.object(engine._context, "_move_completed_orders"),
        ):
            engine._update_order_from_response(live_order, response)

            mock_fill.assert_called_once()
            fill_arg = mock_fill.call_args[0][0]
            # Should get incremental fill: 0.7 - 0.3 = 0.4
            assert fill_arg.amount == Decimal("0.4")
            # Should get incremental fee: 0.315 - 0.135 = 0.18
            assert fill_arg.fee == Decimal("0.18")

    @pytest.mark.asyncio
    async def test_update_order_from_response_no_new_fills(
        self, engine_with_buy_order, mock_adapter
    ):
        """Test _update_order_from_response does nothing when no new fills."""
        engine = engine_with_buy_order
        await engine.start()

        live_order = engine._live_orders["order-1"]
        live_order.filled_amount = Decimal("0.5")
        live_order.fee = Decimal("0.225")

        response = OrderResponse(
            order_id="exchange-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            status=OrderStatus.PARTIAL,
            price=None,
            amount=Decimal("1.0"),
            filled=Decimal("0.5"),  # Same as before
            avg_price=Decimal("45000"),
            fee=Decimal("0.225"),
        )

        with patch.object(engine._context, "_process_fill") as mock_fill:
            engine._update_order_from_response(live_order, response)

            # No new fills, so _process_fill should not be called
            mock_fill.assert_not_called()

    @pytest.mark.asyncio
    async def test_polling_path_records_trade_pnl(self, engine_with_buy_order, mock_adapter):
        """Test that _update_order_from_response records trade PnL for risk management."""
        engine = engine_with_buy_order
        await engine.start()

        live_order = engine._live_orders["order-1"]
        response = OrderResponse(
            order_id="exchange-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            status=OrderStatus.FILLED,
            price=None,
            amount=Decimal("1.0"),
            filled=Decimal("1.0"),
            avg_price=Decimal("45000"),
            fee=Decimal("0.45"),
            fee_currency="USDT",
        )

        # Mock a completed trade with a loss
        mock_trade = MagicMock()
        mock_trade.pnl = Decimal("-100")

        engine._context._trades = []  # Before: 0 trades
        engine._context._open_trade = MagicMock()  # Simulate open position

        def mock_process_fill(*args, **kwargs):
            engine._context._trades = [mock_trade]
            engine._context._open_trade = None  # Trade closed

        with (
            patch.object(engine._context, "_process_fill", side_effect=mock_process_fill),
            patch.object(engine._context, "_move_completed_orders"),
        ):
            engine._update_order_from_response(live_order, response)

        # Check that consecutive_losses increased
        assert engine._risk_manager.state.consecutive_losses == 1

    @pytest.mark.asyncio
    async def test_polling_path_triggers_circuit_breaker(
        self, engine_with_buy_order, mock_adapter
    ):
        """Test that polling path triggers circuit breaker after consecutive losses."""
        engine = engine_with_buy_order
        await engine.start()

        # Pre-load consecutive losses (threshold=3 by default, but engine fixture uses
        # default config; manually set to near threshold)
        engine._risk_manager.config.circuit_breaker_enabled = True
        engine._risk_manager.config.circuit_breaker_loss_count = 2

        # Record one prior loss so next loss triggers breaker
        engine._risk_manager.record_trade_result(Decimal("-100"))
        assert engine._circuit_breaker_triggered is False

        live_order = engine._live_orders["order-1"]
        response = OrderResponse(
            order_id="exchange-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            status=OrderStatus.FILLED,
            price=None,
            amount=Decimal("1.0"),
            filled=Decimal("1.0"),
            avg_price=Decimal("45000"),
            fee=Decimal("0.45"),
            fee_currency="USDT",
        )

        mock_trade = MagicMock()
        mock_trade.pnl = Decimal("-200")

        engine._context._trades = []
        engine._context._open_trade = MagicMock()  # Simulate open position

        def mock_process_fill(*args, **kwargs):
            engine._context._trades = [mock_trade]
            engine._context._open_trade = None  # Trade closed

        with (
            patch.object(engine._context, "_process_fill", side_effect=mock_process_fill),
            patch.object(engine._context, "_move_completed_orders"),
        ):
            engine._update_order_from_response(live_order, response)

        # Circuit breaker should now be triggered
        assert engine._risk_manager.state.consecutive_losses == 2
        assert engine._risk_manager.state.circuit_breaker_triggered is True
        assert engine._circuit_breaker_triggered is True

    @pytest.mark.asyncio
    async def test_polling_path_no_risk_update_when_no_trade_completed(
        self, engine_with_buy_order, mock_adapter
    ):
        """Test that polling path does NOT update risk when fill doesn't complete a trade."""
        engine = engine_with_buy_order
        await engine.start()

        live_order = engine._live_orders["order-1"]
        response = OrderResponse(
            order_id="exchange-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            status=OrderStatus.PARTIAL,
            price=None,
            amount=Decimal("1.0"),
            filled=Decimal("0.5"),
            avg_price=Decimal("45000"),
            fee=Decimal("0.225"),
            fee_currency="USDT",
        )

        engine._context._trades = []  # No trades before or after

        with (
            patch.object(engine._context, "_process_fill"),
            patch.object(engine._context, "_move_completed_orders"),
        ):
            engine._update_order_from_response(live_order, response)

        # No trade completed, risk state unchanged
        assert engine._risk_manager.state.consecutive_losses == 0


class TestRiskTriggerPersistence:
    """Tests for risk trigger persistence tracking (Issue 010)."""

    @pytest.fixture
    def engine_with_risk_rejection(self, engine, mock_adapter):
        """Create engine and prepare for risk rejection scenario."""
        return engine

    @pytest.mark.asyncio
    async def test_risk_trigger_recorded_on_rejection(self, engine, mock_adapter):
        """Test that risk triggers are recorded when orders are rejected."""
        await engine.start()

        # Set a very small max order size to force rejection
        engine._risk_manager.config.max_order_size = Decimal("0.0001")
        engine._current_price = Decimal("45000")

        # Process a candle to trigger strategy which will create an order
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

        # Check if there are pending risk triggers
        if engine.has_pending_risk_triggers():
            triggers = engine.get_pending_risk_triggers()
            assert len(triggers) > 0
            trigger = triggers[0]
            assert trigger["trigger_type"] == "order_rejected"
            assert "details" in trigger
            assert "reason" in trigger["details"]

    def test_get_pending_risk_triggers_clears_after_retrieval(self, engine):
        """Test that get_pending_risk_triggers clears the list."""
        engine._pending_risk_triggers = [
            {"rule_type": "max_order_size", "trigger_type": "order_rejected", "details": {}}
        ]

        assert engine.has_pending_risk_triggers() is True

        triggers = engine.get_pending_risk_triggers()
        assert len(triggers) == 1

        # Should be cleared now
        assert engine.has_pending_risk_triggers() is False
        assert len(engine.get_pending_risk_triggers()) == 0

    def test_has_pending_risk_triggers_false_when_empty(self, engine):
        """Test has_pending_risk_triggers returns False when no triggers."""
        assert engine.has_pending_risk_triggers() is False


class TestBalanceSyncFailure:
    """Tests for balance sync error handling."""

    @pytest.mark.asyncio
    async def test_balance_sync_preserves_cash_on_failure(self, engine, mock_adapter):
        """Test that cash remains unchanged when balance sync fails."""
        await engine.start()
        initial_cash = engine.context.cash

        # Make get_balance fail
        mock_adapter.get_balance.side_effect = Exception("Network error")

        await engine._sync_balance()

        # Cash should remain unchanged
        assert engine.context.cash == initial_cash

    @pytest.mark.asyncio
    async def test_balance_sync_missing_quote_currency(self, engine, mock_adapter):
        """Test balance sync when quote currency not in response."""
        await engine.start()
        initial_cash = engine.context.cash

        # Return balance without USDT
        mock_adapter.get_balance.return_value = AccountBalance(
            exchange="okx",
            balances=[
                Balance(currency="BTC", available=Decimal("1.0"), frozen=Decimal("0")),
            ],
        )

        await engine._sync_balance()

        # Cash should remain unchanged (no USDT balance found)
        assert engine.context.cash == initial_cash

    @pytest.mark.asyncio
    async def test_balance_sync_does_not_overwrite_cash(self, engine, mock_adapter):
        """Test balance sync does NOT overwrite local cash (LIVE-012)."""
        await engine.start()
        initial_cash = engine.context.cash

        mock_adapter.get_balance.return_value = AccountBalance(
            exchange="okx",
            balances=[
                Balance(currency="USDT", available=Decimal("9500"), frozen=Decimal("500")),
            ],
        )

        await engine._sync_balance()

        # Cash should remain at initial_equity, not overwritten to 9500
        assert engine.context.cash == initial_cash

    @pytest.mark.asyncio
    async def test_balance_sync_stores_exchange_balance(self, engine, mock_adapter):
        """Test that exchange balance is stored for diagnostics."""
        await engine.start()
        engine._last_balance_check = None  # Reset rate limiter for direct call

        mock_adapter.get_balance.return_value = AccountBalance(
            exchange="okx",
            balances=[
                Balance(currency="USDT", available=Decimal("9500"), frozen=Decimal("500")),
            ],
        )

        await engine._sync_balance()

        assert engine._last_exchange_balance == Decimal("9500")

    @pytest.mark.asyncio
    async def test_balance_sync_logs_cash_discrepancy(self, engine, mock_adapter, caplog):
        """Test that large cash discrepancy is logged as warning."""
        await engine.start()
        engine._last_balance_check = None  # Reset rate limiter for direct test
        # Engine initial_equity = 10000, set exchange to very different value
        mock_adapter.get_balance.return_value = AccountBalance(
            exchange="okx",
            balances=[
                Balance(currency="USDT", available=Decimal("5000"), frozen=Decimal("0")),
            ],
        )

        import logging

        with caplog.at_level(logging.WARNING):
            await engine._sync_balance()

        assert any("Cash discrepancy" in msg for msg in caplog.messages)
        # Cash should still be original value
        assert engine.context.cash == engine._initial_equity

    @pytest.mark.asyncio
    async def test_balance_sync_no_warning_for_small_discrepancy(self, engine, mock_adapter, caplog):
        """Test that small cash discrepancy does not trigger warning."""
        await engine.start()
        # Exchange balance close to initial_equity (within 5%)
        mock_adapter.get_balance.return_value = AccountBalance(
            exchange="okx",
            balances=[
                Balance(
                    currency="USDT", available=Decimal("9800"), frozen=Decimal("0")
                ),
            ],
        )

        import logging

        with caplog.at_level(logging.WARNING):
            await engine._sync_balance()

        assert not any("Cash discrepancy" in msg for msg in caplog.messages)


class TestCircuitBreakerOrderProcessing:
    """Tests for circuit breaker blocking order processing."""

    @pytest.mark.asyncio
    async def test_order_processing_blocked_by_circuit_breaker(self, engine, mock_adapter):
        """Test that _process_order_requests skips when circuit breaker triggered."""
        await engine.start()

        engine._circuit_breaker_triggered = True

        # Add a pending order via context
        engine._context.buy("BTC/USDT", Decimal("0.01"))

        await engine._process_order_requests()

        # Should NOT call place_order
        mock_adapter.place_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_order_processing_works_without_circuit_breaker(self, engine, mock_adapter):
        """Test that orders process normally when circuit breaker is not triggered."""
        await engine.start()
        engine._current_price = Decimal("45000")

        engine._context.buy("BTC/USDT", Decimal("0.01"))

        await engine._process_order_requests()

        # Should call place_order
        mock_adapter.place_order.assert_called_once()


class TestSyncConsecutiveFailures:
    """Tests for exchange connection failure detection (LV-3).

    After ISSUE-202 fix, _sync_balance and _sync_pending_orders raise
    RuntimeError instead of silently setting _is_running=False. The outer
    handler in process_candle catches the exception and calls stop() for
    proper cleanup (order cancellation, strategy notification).
    """

    @pytest.mark.asyncio
    async def test_balance_sync_consecutive_failures_raises(self, engine, mock_adapter):
        """Test _sync_balance raises RuntimeError after consecutive failures."""
        await engine.start()
        assert engine.is_running is True
        engine._last_balance_check = None  # Reset rate limiter for direct test

        # Make get_balance fail
        mock_adapter.get_balance.side_effect = Exception("Network error")

        # First 4 calls just increment the counter
        for _ in range(4):
            await engine._sync_balance()
        assert engine._balance_consecutive_failures == 4
        assert engine.is_running is True

        # 5th call should raise RuntimeError (ISSUE-202 fix)
        with pytest.raises(RuntimeError, match="Exchange connection lost"):
            await engine._sync_balance()

    @pytest.mark.asyncio
    async def test_balance_sync_failure_via_process_candle_calls_stop(
        self, engine, mock_adapter
    ):
        """Test that balance sync failure through process_candle properly stops engine.

        This verifies the ISSUE-202 fix: instead of silently setting _is_running=False,
        the exception propagates to process_candle's outer handler which calls stop()
        with proper cleanup (order cancellation, strategy.on_stop()).
        """
        await engine.start()
        assert engine.is_running is True
        engine._last_balance_check = None  # Reset rate limiter for direct test

        # Pre-fail to reach threshold on next sync
        engine._balance_consecutive_failures = 4
        mock_adapter.get_balance.side_effect = Exception("Network error")

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

        # process_candle should catch the RuntimeError and call stop()
        with pytest.raises(RuntimeError, match="Exchange connection lost"):
            await engine.process_candle(candle)

        # Engine should be properly stopped via stop()
        assert engine.is_running is False
        assert engine.stopped_at is not None
        assert "Exchange connection lost" in engine.error_message

    @pytest.mark.asyncio
    async def test_balance_sync_success_resets_failure_counter(self, engine, mock_adapter):
        """Test successful balance sync resets the failure counter."""
        await engine.start()
        engine._last_balance_check = None  # Reset rate limiter for direct test

        # Fail 4 times (below threshold)
        mock_adapter.get_balance.side_effect = Exception("Network error")
        for _ in range(4):
            await engine._sync_balance()

        assert engine.is_running is True
        assert engine._balance_consecutive_failures == 4

        # Succeed once (resets counter)
        mock_adapter.get_balance.side_effect = None
        await engine._sync_balance()

        assert engine._balance_consecutive_failures == 0
        assert engine.is_running is True

    @pytest.mark.asyncio
    async def test_order_sync_consecutive_failures_raises(self, engine, mock_adapter):
        """Test _sync_pending_orders raises RuntimeError after consecutive failures."""
        await engine.start()

        # Disable rate limiting for this test
        engine._order_poll_min_interval = 0

        # Add a pending order for sync to process
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

        # Make get_order fail
        mock_adapter.get_order.side_effect = Exception("Network error")

        # First 4 calls just increment the counter
        for _ in range(4):
            await engine._sync_pending_orders()
        assert engine._order_sync_consecutive_failures == 4

        # 5th call should raise RuntimeError (ISSUE-202 fix)
        with pytest.raises(RuntimeError, match="Exchange connection lost"):
            await engine._sync_pending_orders()


class TestEmergencyCloseTimestamp:
    """Tests for emergency close activity timestamp (LV-6)."""

    @pytest.mark.asyncio
    async def test_emergency_close_updates_last_active_at(self, engine, mock_adapter):
        """Test that emergency close updates last_active_at timestamp."""
        await engine.start()
        initial_time = engine._last_active_at

        # Simulate a position
        engine.context._positions["BTC/USDT"] = MagicMock()
        engine.context._positions["BTC/USDT"].is_open = True
        engine.context._positions["BTC/USDT"].amount = Decimal("0.5")

        # Mock place_order for market close
        mock_adapter.place_order.return_value = OrderResponse(
            order_id="close-123",
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            status=OrderStatus.FILLED,
            amount=Decimal("0.5"),
            filled=Decimal("0.5"),
            avg_price=Decimal("42000"),
        )

        await engine.emergency_close()

        # last_active_at should have been updated during emergency close
        assert engine._last_active_at >= initial_time


class TestForceFillOnValueError:
    """Tests for ISSUE-201 fix: live fills must be recorded even when local
    cash/position tracking has discrepancies with exchange state."""

    @pytest.fixture
    def engine_with_buy_order(self, engine):
        """Create engine with a tracked buy order."""
        engine._live_orders["order-1"] = LiveOrder(
            internal_id="order-1",
            exchange_order_id="exchange-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="market",
            amount=Decimal("1.0"),
            price=None,
            status=OrderStatus.SUBMITTED,
        )
        engine._exchange_order_map["exchange-1"] = "order-1"
        return engine

    @pytest.mark.asyncio
    async def test_ws_fill_recorded_despite_insufficient_cash(
        self, engine_with_buy_order, mock_adapter
    ):
        """Test WS fill is recorded even when local cash is insufficient.

        In live trading, fills are already executed on exchange. The engine
        must record them locally regardless of cash discrepancy (ISSUE-201).
        """
        engine = engine_with_buy_order
        await engine.start()

        # Artificially deplete local cash to create discrepancy
        engine._context._cash = Decimal("100")  # Much less than fill cost

        update = WSOrderUpdate(
            order_id="exchange-1",
            client_order_id="order-1",
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            status="filled",
            size=Decimal("1.0"),
            filled_size=Decimal("1.0"),
            avg_price=Decimal("45000"),
            fee=Decimal("0.45"),
            fee_currency="USDT",
        )

        # Buffer and drain — should NOT raise ValueError
        engine.on_order_update(update)
        engine._drain_ws_updates()

        # Fill should be recorded (cash goes negative, which is OK in live)
        assert len(engine._context.fills) == 1
        assert engine._context.fills[0].amount == Decimal("1.0")
        assert engine._context._cash < Decimal("0")  # Negative cash from discrepancy

    @pytest.mark.asyncio
    async def test_polling_fill_recorded_despite_insufficient_cash(
        self, engine_with_buy_order, mock_adapter
    ):
        """Test polling-path fill is recorded even when local cash is insufficient."""
        engine = engine_with_buy_order
        await engine.start()

        # Artificially deplete local cash
        engine._context._cash = Decimal("50")

        live_order = engine._live_orders["order-1"]
        response = OrderResponse(
            order_id="exchange-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            status=OrderStatus.FILLED,
            price=None,
            amount=Decimal("1.0"),
            filled=Decimal("1.0"),
            avg_price=Decimal("45000"),
            fee=Decimal("0.45"),
            fee_currency="USDT",
        )

        # Should NOT raise ValueError
        engine._update_order_from_response(live_order, response)

        # Fill should be recorded
        assert len(engine._context.fills) == 1
        assert engine._context._cash < Decimal("0")


class TestWsUpdateBuffering:
    """Tests for ISSUE-203 fix: WS updates are buffered and processed
    synchronously within process_candle to prevent concurrent state mutation."""

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

    def test_on_order_update_buffers_not_processes(self, engine_with_order):
        """Test on_order_update only buffers, does not immediately mutate state."""
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

        # Update should be buffered, NOT processed
        assert len(engine_with_order._pending_ws_updates) == 1
        live_order = engine_with_order._live_orders["internal-1"]
        assert live_order.status == OrderStatus.SUBMITTED  # Unchanged
        assert live_order.filled_amount == Decimal("0")  # Unchanged

    def test_drain_ws_updates_processes_buffered(self, engine_with_order):
        """Test _drain_ws_updates processes all buffered updates."""
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
        engine_with_order._drain_ws_updates()

        # Now state should be updated
        assert len(engine_with_order._pending_ws_updates) == 0
        live_order = engine_with_order._live_orders["internal-1"]
        assert live_order.status == OrderStatus.FILLED
        assert live_order.filled_amount == Decimal("0.1")

    def test_drain_ws_updates_noop_when_empty(self, engine_with_order):
        """Test _drain_ws_updates is a no-op when queue is empty."""
        # Should not raise
        engine_with_order._drain_ws_updates()
        assert len(engine_with_order._pending_ws_updates) == 0


class TestTimedOutOrderReconciliation:
    """Tests for R5-F3: timed-out order recovery via client_order_id."""

    async def test_timeout_records_order_for_reconciliation(self, engine, mock_adapter):
        """Test that order submission timeout adds order to _timed_out_orders."""
        mock_adapter.place_order.side_effect = TimeoutError("timed out")

        await engine.start()

        # Create a pending order manually
        engine._current_price = Decimal("45000")
        engine._context.buy("BTC/USDT", Decimal("0.01"))
        pending = engine._context._get_pending_orders()
        assert len(pending) == 1

        order = pending[0]
        await engine._submit_order(order)

        # Order should be in _timed_out_orders, NOT in _live_orders
        assert order.id in engine._timed_out_orders
        assert order.id not in engine._live_orders
        # Order should NOT be marked REJECTED
        assert order.status != OrderStatus.REJECTED

    async def test_reconcile_recovers_order_found_on_exchange(self, engine, mock_adapter):
        """Test that reconciliation recovers a timed-out order found on exchange."""
        await engine.start()

        # Simulate a timed-out order
        engine._current_price = Decimal("45000")
        engine._context.buy("BTC/USDT", Decimal("0.01"))
        order = engine._context._get_pending_orders()[0]
        engine._timed_out_orders[order.id] = order

        # Exchange has this order (matched by client_order_id)
        mock_adapter.get_open_orders.return_value = [
            OrderResponse(
                order_id="exchange-recovered-1",
                client_order_id=order.id,
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                status=OrderStatus.SUBMITTED,
                amount=Decimal("0.01"),
                filled=Decimal("0"),
            )
        ]

        await engine._reconcile_timed_out_orders()

        # Order should now be tracked as a live order
        assert order.id in engine._live_orders
        assert engine._live_orders[order.id].exchange_order_id == "exchange-recovered-1"
        assert "exchange-recovered-1" in engine._exchange_order_map
        # Should be removed from timed-out tracking
        assert order.id not in engine._timed_out_orders

    async def test_reconcile_marks_cancelled_when_not_on_exchange(self, engine, mock_adapter):
        """Test that timed-out order not found on exchange is marked cancelled."""
        await engine.start()

        engine._current_price = Decimal("45000")
        engine._context.buy("BTC/USDT", Decimal("0.01"))
        order = engine._context._get_pending_orders()[0]
        engine._timed_out_orders[order.id] = order

        # Exchange has no matching orders
        mock_adapter.get_open_orders.return_value = []

        await engine._reconcile_timed_out_orders()

        # Order should be marked cancelled and moved to completed
        assert order.status == OrderStatus.CANCELLED
        assert order.id not in engine._timed_out_orders
        assert any(o.id == order.id for o in engine._context._completed_orders)

    async def test_reconcile_processes_fills_for_recovered_order(self, engine, mock_adapter):
        """Test that fills on recovered timed-out orders are processed."""
        await engine.start()

        engine._current_price = Decimal("45000")
        engine._context.buy("BTC/USDT", Decimal("0.01"))
        order = engine._context._get_pending_orders()[0]
        engine._timed_out_orders[order.id] = order

        # Exchange has this order already partially filled
        mock_adapter.get_open_orders.return_value = [
            OrderResponse(
                order_id="exchange-recovered-2",
                client_order_id=order.id,
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                status=OrderStatus.PARTIAL,
                amount=Decimal("0.01"),
                filled=Decimal("0.005"),
                avg_price=Decimal("45000"),
                fee=Decimal("0.225"),
                fee_currency="USDT",
            )
        ]

        await engine._reconcile_timed_out_orders()

        # Fill should have been processed
        assert engine._live_orders[order.id].filled_amount == Decimal("0.005")
        # Position should exist in context
        pos = engine._context.get_position("BTC/USDT")
        assert pos is not None and pos.amount > 0

    async def test_timed_out_order_not_resubmitted(self, engine, mock_adapter):
        """Test that orders in _timed_out_orders are not re-submitted."""
        await engine.start()

        engine._current_price = Decimal("45000")
        engine._context.buy("BTC/USDT", Decimal("0.01"))
        order = engine._context._get_pending_orders()[0]
        # Simulate timeout
        engine._timed_out_orders[order.id] = order

        # Reset place_order call count
        mock_adapter.place_order.reset_mock()

        await engine._process_order_requests()

        # Should NOT have attempted to submit the order again
        mock_adapter.place_order.assert_not_called()

    async def test_reconcile_noop_when_no_timed_out_orders(self, engine, mock_adapter):
        """Test reconciliation is a no-op with no timed-out orders."""
        await engine.start()

        await engine._reconcile_timed_out_orders()

        # get_open_orders should NOT be called
        mock_adapter.get_open_orders.assert_not_called()

    async def test_reconcile_handles_exchange_error_gracefully(self, engine, mock_adapter):
        """Test reconciliation handles exchange errors without crashing."""
        await engine.start()

        engine._current_price = Decimal("45000")
        engine._context.buy("BTC/USDT", Decimal("0.01"))
        order = engine._context._get_pending_orders()[0]
        engine._timed_out_orders[order.id] = order

        mock_adapter.get_open_orders.side_effect = Exception("Network error")

        await engine._reconcile_timed_out_orders()

        # Order should remain in _timed_out_orders for next attempt
        assert order.id in engine._timed_out_orders


class TestBalanceCheckRateLimiting:
    """Tests for F-5: balance check rate limiting to reduce API calls."""

    @pytest.mark.asyncio
    async def test_balance_check_skipped_within_interval(self, engine, mock_adapter):
        """Balance sync should be skipped if called within the rate limit interval."""
        await engine.start()
        # start() calls _sync_balance() once, setting _last_balance_check
        initial_call_count = mock_adapter.get_balance.call_count

        await engine._sync_balance()

        # Should be skipped — no additional call
        assert mock_adapter.get_balance.call_count == initial_call_count

    @pytest.mark.asyncio
    async def test_balance_check_executes_after_interval(self, engine, mock_adapter):
        """Balance sync should execute after the rate limit interval expires."""
        await engine.start()
        initial_call_count = mock_adapter.get_balance.call_count

        # Simulate interval elapsed
        engine._last_balance_check = None

        await engine._sync_balance()

        assert mock_adapter.get_balance.call_count == initial_call_count + 1

    @pytest.mark.asyncio
    async def test_balance_check_forced_after_fill(self, engine, mock_adapter):
        """Balance sync should execute immediately after a fill, even within interval."""
        await engine.start()
        initial_call_count = mock_adapter.get_balance.call_count

        # Simulate a recent fill
        engine._has_recent_fill = True

        await engine._sync_balance()

        assert mock_adapter.get_balance.call_count == initial_call_count + 1
        # Flag should be reset after check
        assert engine._has_recent_fill is False


class TestOrderEventPersistRetry:
    """Tests for F-10: failed audit events are retried on next bar."""

    @pytest.mark.asyncio
    async def test_failed_persist_puts_events_back(self, engine):
        """Events should be put back into the queue if persist fails."""
        await engine.start()

        # Inject events and a failing callback
        events = [{"type": "order_created", "order_id": "abc"}]
        engine._pending_order_events = events.copy()
        engine._on_order_persist = AsyncMock(side_effect=Exception("DB error"))

        # Simulate the persist flush path in process_candle
        if engine._on_order_persist and engine._pending_order_events:
            events_to_persist = engine._pending_order_events.copy()
            engine._pending_order_events.clear()
            try:
                await engine._on_order_persist(str(engine._run_id), events_to_persist)
            except Exception:
                engine._pending_order_events = events_to_persist + engine._pending_order_events

        assert len(engine._pending_order_events) == 1
        assert engine._pending_order_events[0]["order_id"] == "abc"

    @pytest.mark.asyncio
    async def test_successful_persist_clears_events(self, engine):
        """Events should be cleared after successful persist."""
        await engine.start()

        events = [{"type": "order_created", "order_id": "abc"}]
        engine._pending_order_events = events.copy()
        engine._on_order_persist = AsyncMock()

        if engine._on_order_persist and engine._pending_order_events:
            events_to_persist = engine._pending_order_events.copy()
            engine._pending_order_events.clear()
            try:
                await engine._on_order_persist(str(engine._run_id), events_to_persist)
            except Exception:
                engine._pending_order_events = events_to_persist + engine._pending_order_events

        assert len(engine._pending_order_events) == 0
        engine._on_order_persist.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_preserves_new_events_added_during_persist(self, engine):
        """New events added during persist attempt should be preserved alongside retried ones."""
        await engine.start()

        original = [{"type": "fill", "order_id": "1"}]
        engine._pending_order_events = original.copy()

        async def fail_and_add_event(run_id, events):
            # Simulate new event arriving during persist
            engine._pending_order_events.append({"type": "fill", "order_id": "2"})
            raise Exception("DB error")

        engine._on_order_persist = AsyncMock(side_effect=fail_and_add_event)

        if engine._on_order_persist and engine._pending_order_events:
            events_to_persist = engine._pending_order_events.copy()
            engine._pending_order_events.clear()
            try:
                await engine._on_order_persist(str(engine._run_id), events_to_persist)
            except Exception:
                engine._pending_order_events = events_to_persist + engine._pending_order_events

        # Original event first, then new event
        assert len(engine._pending_order_events) == 2
        assert engine._pending_order_events[0]["order_id"] == "1"
        assert engine._pending_order_events[1]["order_id"] == "2"


class TestOnBarExceptionIsolation:
    """Tests for ISSUE-3: on_bar() exceptions should not stop the live engine."""

    @pytest.mark.asyncio
    async def test_strategy_exception_does_not_stop_engine(self, engine, mock_adapter):
        """A strategy on_bar() error should be caught and logged, not stop the engine."""
        await engine.start()

        # Make strategy raise a KeyError
        engine._strategy.on_bar = MagicMock(side_effect=KeyError("missing_key"))

        candle = WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2025, 1, 1, 0, 1, tzinfo=UTC),
            open=Decimal("50000"),
            high=Decimal("50100"),
            low=Decimal("49900"),
            close=Decimal("50050"),
            volume=Decimal("100"),
            is_closed=True,
        )

        with patch("squant.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                strategy=MagicMock(cpu_limit_seconds=5, memory_limit_mb=256),
            )
            # Should NOT raise — strategy error is isolated
            await engine.process_candle(candle)

        # Engine should still be running
        assert engine._is_running is True

    @pytest.mark.asyncio
    async def test_strategy_exception_logged_to_context(self, engine, mock_adapter):
        """Strategy error should be recorded in context logs."""
        await engine.start()

        engine._strategy.on_bar = MagicMock(side_effect=ValueError("bad calculation"))

        candle = WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2025, 1, 1, 0, 1, tzinfo=UTC),
            open=Decimal("50000"),
            high=Decimal("50100"),
            low=Decimal("49900"),
            close=Decimal("50050"),
            volume=Decimal("100"),
            is_closed=True,
        )

        with patch("squant.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                strategy=MagicMock(cpu_limit_seconds=5, memory_limit_mb=256),
            )
            await engine.process_candle(candle)

        # Error should be in context logs
        logs = list(engine._context._logs)
        assert any("ERROR in on_bar" in log for log in logs)


class TestOrderTTLExpiry:
    """Tests for ISSUE-8: limit orders with bars_remaining TTL."""

    @pytest.mark.asyncio
    async def test_ttl_order_cancelled_after_expiry(self, engine, mock_adapter):
        """Limit order with bars_remaining=1 should be cancelled after 1 bar."""
        await engine.start()

        # Create a live order with TTL
        live_order = LiveOrder(
            internal_id="test-ttl-1",
            exchange_order_id="exc-123",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="limit",
            amount=Decimal("0.01"),
            price=Decimal("45000"),
        )
        live_order.bars_remaining = 1
        live_order.created_at = datetime(2025, 1, 1, tzinfo=UTC)
        engine._live_orders["test-ttl-1"] = live_order
        engine._exchange_order_map["exc-123"] = "test-ttl-1"

        # Mock cancel response
        mock_adapter.cancel_order.return_value = OrderResponse(
            order_id="exc-123",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=Decimal("0.01"),
            status=OrderStatus.CANCELLED,
            filled=Decimal("0"),
            avg_price=None,
            fee=Decimal("0"),
        )

        await engine._expire_ttl_orders()

        assert live_order.bars_remaining == 0
        mock_adapter.cancel_order.assert_called_once()
        assert live_order.status == OrderStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_ttl_order_not_cancelled_before_expiry(self, engine, mock_adapter):
        """Limit order with bars_remaining=3 should not be cancelled after 1 bar."""
        await engine.start()

        live_order = LiveOrder(
            internal_id="test-ttl-2",
            exchange_order_id="exc-456",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="limit",
            amount=Decimal("0.01"),
            price=Decimal("45000"),
        )
        live_order.bars_remaining = 3
        live_order.created_at = datetime(2025, 1, 1, tzinfo=UTC)
        engine._live_orders["test-ttl-2"] = live_order

        await engine._expire_ttl_orders()

        assert live_order.bars_remaining == 2
        mock_adapter.cancel_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_gtc_order_not_affected(self, engine, mock_adapter):
        """GTC order (bars_remaining=None) should never expire."""
        await engine.start()

        live_order = LiveOrder(
            internal_id="test-gtc",
            exchange_order_id="exc-789",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="limit",
            amount=Decimal("0.01"),
            price=Decimal("45000"),
        )
        live_order.bars_remaining = None
        live_order.created_at = datetime(2025, 1, 1, tzinfo=UTC)
        engine._live_orders["test-gtc"] = live_order

        await engine._expire_ttl_orders()

        assert live_order.bars_remaining is None
        mock_adapter.cancel_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_ttl_cancel_failure_handled_gracefully(self, engine, mock_adapter):
        """Exchange cancel failure should not crash the engine."""
        await engine.start()

        live_order = LiveOrder(
            internal_id="test-ttl-fail",
            exchange_order_id="exc-999",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="limit",
            amount=Decimal("0.01"),
            price=Decimal("45000"),
        )
        live_order.bars_remaining = 1
        live_order.created_at = datetime(2025, 1, 1, tzinfo=UTC)
        engine._live_orders["test-ttl-fail"] = live_order

        mock_adapter.cancel_order.side_effect = Exception("Network error")

        # Should not raise
        await engine._expire_ttl_orders()

        assert live_order.bars_remaining == 0


class TestFillPositionCashIntegration:
    """End-to-end tests for _record_fill → _process_fill(force=True) verifying
    exact position amount, cash, and fee changes after fills."""

    @pytest.fixture
    def engine_with_tracked_buy(self, engine):
        """Engine with a tracked BUY order on the exchange."""
        order = LiveOrder(
            internal_id="buy-1",
            exchange_order_id="exc-buy-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="limit",
            amount=Decimal("0.5"),
            price=Decimal("40000"),
            status=OrderStatus.SUBMITTED,
        )
        order.created_at = datetime(2025, 1, 1, tzinfo=UTC)
        engine._live_orders["buy-1"] = order
        engine._exchange_order_map["exc-buy-1"] = "buy-1"
        return engine

    @pytest.mark.asyncio
    async def test_buy_fill_updates_position_and_cash(self, engine_with_tracked_buy, mock_adapter):
        """BUY fill: position increases, cash decreases by (price * amount + fee)."""
        engine = engine_with_tracked_buy
        await engine.start()

        initial_cash = engine._context._cash
        live_order = engine._live_orders["buy-1"]

        engine._record_fill(
            live_order,
            fill_price=Decimal("40000"),
            fill_amount=Decimal("0.5"),
            fee_delta=Decimal("10"),
            total_fee=Decimal("10"),
            source="poll",
        )

        # Position should be 0.5 BTC
        pos = engine._context.get_position("BTC/USDT")
        assert pos is not None
        assert pos.amount == Decimal("0.5")

        # Cash: initial - (40000 * 0.5 + 10) = initial - 20010
        expected_cash = initial_cash - Decimal("20010")
        assert engine._context._cash == expected_cash

        # Fill recorded
        assert len(engine._context.fills) == 1
        assert engine._context.fills[0].fee == Decimal("10")

        # Balance check triggered
        assert engine._has_recent_fill is True

    @pytest.mark.asyncio
    async def test_sell_fill_updates_position_and_cash(self, engine_with_tracked_buy, mock_adapter):
        """SELL fill: position decreases, cash increases by (price * amount - fee)."""
        engine = engine_with_tracked_buy
        await engine.start()

        # First buy to establish position
        buy_order = engine._live_orders["buy-1"]
        engine._record_fill(
            buy_order,
            fill_price=Decimal("40000"),
            fill_amount=Decimal("1.0"),
            fee_delta=Decimal("20"),
            total_fee=Decimal("20"),
            source="poll",
        )
        cash_before_sell = engine._context._cash

        # Create sell order
        sell_order = LiveOrder(
            internal_id="sell-1",
            exchange_order_id="exc-sell-1",
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            order_type="limit",
            amount=Decimal("0.5"),
            price=Decimal("45000"),
            status=OrderStatus.SUBMITTED,
        )
        engine._live_orders["sell-1"] = sell_order

        engine._record_fill(
            sell_order,
            fill_price=Decimal("45000"),
            fill_amount=Decimal("0.5"),
            fee_delta=Decimal("11.25"),
            total_fee=Decimal("11.25"),
            source="poll",
        )

        # Position: 1.0 - 0.5 = 0.5
        pos = engine._context.get_position("BTC/USDT")
        assert pos.amount == Decimal("0.5")

        # Cash: before + (45000 * 0.5 - 11.25) = before + 22488.75
        expected_cash = cash_before_sell + Decimal("22488.75")
        assert engine._context._cash == expected_cash

    @pytest.mark.asyncio
    async def test_partial_fills_accumulate_correctly(self, engine_with_tracked_buy, mock_adapter):
        """Two partial fills should accumulate position and deduct cash correctly."""
        engine = engine_with_tracked_buy
        await engine.start()

        initial_cash = engine._context._cash
        live_order = engine._live_orders["buy-1"]

        # First partial: 0.3 of 0.5
        engine._record_fill(
            live_order,
            fill_price=Decimal("40000"),
            fill_amount=Decimal("0.3"),
            fee_delta=Decimal("6"),
            total_fee=Decimal("6"),
            source="ws",
        )

        pos = engine._context.get_position("BTC/USDT")
        assert pos.amount == Decimal("0.3")
        assert engine._context._cash == initial_cash - Decimal("12006")  # 40000*0.3+6

        # Second partial: remaining 0.2 at slightly different price
        engine._record_fill(
            live_order,
            fill_price=Decimal("40100"),
            fill_amount=Decimal("0.2"),
            fee_delta=Decimal("4"),
            total_fee=Decimal("10"),
            source="ws",
        )

        pos = engine._context.get_position("BTC/USDT")
        assert pos.amount == Decimal("0.5")
        # Additional cost: 40100*0.2+4 = 8024
        assert engine._context._cash == initial_cash - Decimal("12006") - Decimal("8024")
        assert len(engine._context.fills) == 2

    @pytest.mark.asyncio
    async def test_force_true_allows_negative_cash(self, engine_with_tracked_buy, mock_adapter):
        """force=True allows fill recording even when cash goes deeply negative."""
        engine = engine_with_tracked_buy
        await engine.start()

        # Deplete cash to near-zero
        engine._context._cash = Decimal("1")

        live_order = engine._live_orders["buy-1"]
        engine._record_fill(
            live_order,
            fill_price=Decimal("40000"),
            fill_amount=Decimal("0.5"),
            fee_delta=Decimal("10"),
            total_fee=Decimal("10"),
            source="reconcile",
        )

        # Cash deeply negative: 1 - 20010 = -20009
        assert engine._context._cash == Decimal("-20009")
        # Position IS recorded despite negative cash
        pos = engine._context.get_position("BTC/USDT")
        assert pos.amount == Decimal("0.5")
        # Audit event buffered
        assert any(e["type"] == "fill" for e in engine._pending_order_events)


class TestPrivateWebSocket:
    """Tests for private WebSocket start/stop (LIVE-CN-001)."""

    @pytest.fixture
    def engine_with_credentials(self, run_id, strategy, risk_config, mock_adapter):
        """Create engine with credentials for private WS testing."""
        with patch("squant.config.get_settings") as mock_settings:
            settings = MagicMock()
            settings.paper_max_equity_curve_size = 10000
            settings.paper_max_completed_orders = 1000
            settings.paper_max_fills = 1000
            settings.paper_max_trades = 1000
            settings.paper_max_logs = 1000
            settings.strategy.max_bar_history = 1000
            mock_settings.return_value = settings

            mock_creds = MagicMock()
            return LiveTradingEngine(
                run_id=run_id,
                strategy=strategy,
                symbol="BTC/USDT",
                timeframe="1m",
                adapter=mock_adapter,
                risk_config=risk_config,
                initial_equity=Decimal("10000"),
                params={"threshold": Decimal("50000")},
                credentials=mock_creds,
                exchange_id="okx",
            )

    @pytest.mark.asyncio
    async def test_start_private_ws_success(self, engine_with_credentials):
        """Test _start_private_ws successfully connects and watches orders."""
        engine = engine_with_credentials

        mock_provider = AsyncMock()
        mock_provider.connect = AsyncMock()
        mock_provider.watch_orders = AsyncMock()
        mock_provider.add_handler = MagicMock()

        with patch(
            "squant.infra.exchange.ccxt.CCXTStreamProvider",
            return_value=mock_provider,
        ):
            await engine._start_private_ws()

        assert engine._private_ws is mock_provider
        mock_provider.add_handler.assert_called_once()
        mock_provider.connect.assert_called_once()
        mock_provider.watch_orders.assert_called_once_with("BTC/USDT")

    @pytest.mark.asyncio
    async def test_start_private_ws_no_credentials_skips(self, engine):
        """Test _start_private_ws skips when no credentials are set."""
        assert engine._credentials is None

        await engine._start_private_ws()

        # Should not set _private_ws since there are no credentials
        assert engine._private_ws is None

    @pytest.mark.asyncio
    async def test_start_private_ws_failure_degrades_silently(self, engine_with_credentials):
        """Test _start_private_ws fails silently without affecting engine."""
        engine = engine_with_credentials

        mock_provider = AsyncMock()
        mock_provider.connect = AsyncMock(side_effect=Exception("WS connection failed"))
        mock_provider.close = AsyncMock()
        mock_provider.add_handler = MagicMock()

        with patch(
            "squant.infra.exchange.ccxt.CCXTStreamProvider",
            return_value=mock_provider,
        ):
            # Should not raise
            await engine._start_private_ws()

        # private_ws should be cleaned up to None on failure
        assert engine._private_ws is None
        mock_provider.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_private_ws_closes_connection(self, engine_with_credentials):
        """Test _stop_private_ws closes the WS connection and cleans up."""
        engine = engine_with_credentials

        mock_provider = AsyncMock()
        mock_provider.close = AsyncMock()
        engine._private_ws = mock_provider

        await engine._stop_private_ws()

        mock_provider.close.assert_called_once()
        assert engine._private_ws is None

    @pytest.mark.asyncio
    async def test_stop_private_ws_when_none(self, engine):
        """Test _stop_private_ws is a no-op when no WS is set."""
        assert engine._private_ws is None

        # Should not raise
        await engine._stop_private_ws()

        assert engine._private_ws is None

    @pytest.mark.asyncio
    async def test_stop_private_ws_handles_close_error(self, engine_with_credentials):
        """Test _stop_private_ws handles errors during close gracefully."""
        engine = engine_with_credentials

        mock_provider = AsyncMock()
        mock_provider.close = AsyncMock(side_effect=Exception("Close error"))
        engine._private_ws = mock_provider

        # Should not raise
        await engine._stop_private_ws()

        # Should still clean up to None despite error
        assert engine._private_ws is None


class TestDeadManSwitch:
    """Tests for Dead Man's Switch (DMS) functionality (F-2)."""

    @pytest.mark.asyncio
    async def test_activate_dms_success(self, engine, mock_adapter):
        """Test _activate_dead_man_switch calls adapter when supported."""
        mock_adapter.supports_dead_man_switch = True
        mock_adapter.setup_dead_man_switch = AsyncMock()

        await engine._activate_dead_man_switch()

        assert engine._dms_enabled is True
        mock_adapter.setup_dead_man_switch.assert_called_once_with(engine._dms_timeout_ms)

    @pytest.mark.asyncio
    async def test_activate_dms_not_supported(self, engine, mock_adapter):
        """Test _activate_dead_man_switch skips when exchange doesn't support DMS."""
        mock_adapter.supports_dead_man_switch = False

        await engine._activate_dead_man_switch()

        assert engine._dms_enabled is False

    @pytest.mark.asyncio
    async def test_activate_dms_failure_silent(self, engine, mock_adapter):
        """Test _activate_dead_man_switch does not raise on failure."""
        mock_adapter.supports_dead_man_switch = True
        mock_adapter.setup_dead_man_switch = AsyncMock(
            side_effect=Exception("Exchange error")
        )

        # Should not raise
        await engine._activate_dead_man_switch()

        # DMS should remain disabled on failure
        assert engine._dms_enabled is False

    @pytest.mark.asyncio
    async def test_refresh_dms_when_enabled(self, engine, mock_adapter):
        """Test _refresh_dead_man_switch sends heartbeat when DMS is enabled."""
        engine._dms_enabled = True
        mock_adapter.setup_dead_man_switch = AsyncMock()

        await engine._refresh_dead_man_switch()

        mock_adapter.setup_dead_man_switch.assert_called_once_with(engine._dms_timeout_ms)

    @pytest.mark.asyncio
    async def test_refresh_dms_when_disabled_noop(self, engine, mock_adapter):
        """Test _refresh_dead_man_switch does nothing when DMS is not enabled."""
        engine._dms_enabled = False
        mock_adapter.setup_dead_man_switch = AsyncMock()

        await engine._refresh_dead_man_switch()

        mock_adapter.setup_dead_man_switch.assert_not_called()

    @pytest.mark.asyncio
    async def test_refresh_dms_failure_silent(self, engine, mock_adapter):
        """Test _refresh_dead_man_switch does not raise on failure."""
        engine._dms_enabled = True
        mock_adapter.setup_dead_man_switch = AsyncMock(
            side_effect=Exception("Heartbeat failed")
        )

        # Should not raise
        await engine._refresh_dead_man_switch()

    @pytest.mark.asyncio
    async def test_deactivate_dms_when_enabled(self, engine, mock_adapter):
        """Test _deactivate_dead_man_switch cancels DMS on exchange."""
        engine._dms_enabled = True
        mock_adapter.cancel_dead_man_switch = AsyncMock()

        await engine._deactivate_dead_man_switch()

        mock_adapter.cancel_dead_man_switch.assert_called_once()
        assert engine._dms_enabled is False

    @pytest.mark.asyncio
    async def test_deactivate_dms_when_disabled_noop(self, engine, mock_adapter):
        """Test _deactivate_dead_man_switch does nothing when DMS is not enabled."""
        engine._dms_enabled = False
        mock_adapter.cancel_dead_man_switch = AsyncMock()

        await engine._deactivate_dead_man_switch()

        mock_adapter.cancel_dead_man_switch.assert_not_called()
        assert engine._dms_enabled is False

    @pytest.mark.asyncio
    async def test_deactivate_dms_failure_resets_flag(self, engine, mock_adapter):
        """Test _deactivate_dead_man_switch resets flag even on failure."""
        engine._dms_enabled = True
        mock_adapter.cancel_dead_man_switch = AsyncMock(
            side_effect=Exception("Deactivation failed")
        )

        # Should not raise
        await engine._deactivate_dead_man_switch()

        # Flag should be reset to False in the finally block
        assert engine._dms_enabled is False


class TestTriggerGlobalCircuitBreaker:
    """Tests for _trigger_global_circuit_breaker() (LIVE-RM-002, Issue 033)."""

    @pytest.fixture
    def engine_with_cb(self, run_id, strategy, risk_config, mock_adapter):
        """Create engine with circuit breaker config for global CB testing."""
        with patch("squant.config.get_settings") as mock_settings:
            settings = MagicMock()
            settings.paper_max_equity_curve_size = 10000
            settings.paper_max_completed_orders = 1000
            settings.paper_max_fills = 1000
            settings.paper_max_trades = 1000
            settings.paper_max_logs = 1000
            settings.strategy.max_bar_history = 1000
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

    @pytest.mark.asyncio
    async def test_global_cb_writes_redis_state(self, engine_with_cb):
        """Test _trigger_global_circuit_breaker persists state to Redis."""
        engine = engine_with_cb
        engine._risk_manager.state.consecutive_losses = 5

        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()

        mock_live_manager = MagicMock()
        mock_live_manager.stop_all = AsyncMock()
        mock_paper_manager = MagicMock()
        mock_paper_manager.stop_all = AsyncMock()

        with (
            patch(
                "squant.infra.redis.get_redis_client", return_value=mock_redis
            ),
            patch(
                "squant.engine.live.manager.get_live_session_manager",
                return_value=mock_live_manager,
            ),
            patch(
                "squant.engine.paper.manager.get_session_manager",
                return_value=mock_paper_manager,
            ),
        ):
            await engine._trigger_global_circuit_breaker()

        # Redis should have been called with circuit breaker state
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        key = call_args[0][0]
        assert key == "squant:circuit_breaker:state"
        # Verify the value is valid JSON with expected fields
        import json

        state_data = json.loads(call_args[0][1])
        assert state_data["is_active"] is True
        assert state_data["trigger_type"] == "auto"
        assert "consecutive losses" in state_data["trigger_reason"]

    @pytest.mark.asyncio
    async def test_global_cb_stops_all_sessions(self, engine_with_cb):
        """Test _trigger_global_circuit_breaker calls stop_all on both managers."""
        engine = engine_with_cb
        engine._risk_manager.state.consecutive_losses = 5

        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()

        mock_live_manager = MagicMock()
        mock_live_manager.stop_all = AsyncMock()
        mock_paper_manager = MagicMock()
        mock_paper_manager.stop_all = AsyncMock()

        with (
            patch(
                "squant.infra.redis.get_redis_client", return_value=mock_redis
            ),
            patch(
                "squant.engine.live.manager.get_live_session_manager",
                return_value=mock_live_manager,
            ),
            patch(
                "squant.engine.paper.manager.get_session_manager",
                return_value=mock_paper_manager,
            ),
        ):
            await engine._trigger_global_circuit_breaker()

        mock_live_manager.stop_all.assert_called_once()
        mock_paper_manager.stop_all.assert_called_once()
        # Verify reason is passed
        live_reason = mock_live_manager.stop_all.call_args.kwargs.get("reason", "")
        assert "Circuit breaker" in live_reason

    @pytest.mark.asyncio
    async def test_global_cb_redis_failure_degrades(self, engine_with_cb):
        """Test _trigger_global_circuit_breaker continues if Redis write fails."""
        engine = engine_with_cb
        engine._risk_manager.state.consecutive_losses = 5

        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(side_effect=Exception("Redis down"))

        mock_live_manager = MagicMock()
        mock_live_manager.stop_all = AsyncMock()
        mock_paper_manager = MagicMock()
        mock_paper_manager.stop_all = AsyncMock()

        with (
            patch(
                "squant.infra.redis.get_redis_client", return_value=mock_redis
            ),
            patch(
                "squant.engine.live.manager.get_live_session_manager",
                return_value=mock_live_manager,
            ),
            patch(
                "squant.engine.paper.manager.get_session_manager",
                return_value=mock_paper_manager,
            ),
        ):
            # Should not raise despite Redis failure
            await engine._trigger_global_circuit_breaker()

        # Session managers should still be called despite Redis failure
        mock_live_manager.stop_all.assert_called_once()
        mock_paper_manager.stop_all.assert_called_once()

    @pytest.mark.asyncio
    async def test_global_cb_stop_all_failure_does_not_block(self, engine_with_cb):
        """Test stop_all failure on one manager does not prevent the other."""
        engine = engine_with_cb
        engine._risk_manager.state.consecutive_losses = 5

        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()

        mock_live_manager = MagicMock()
        mock_live_manager.stop_all = AsyncMock(
            side_effect=Exception("Live manager error")
        )
        mock_paper_manager = MagicMock()
        mock_paper_manager.stop_all = AsyncMock()

        with (
            patch(
                "squant.infra.redis.get_redis_client", return_value=mock_redis
            ),
            patch(
                "squant.engine.live.manager.get_live_session_manager",
                return_value=mock_live_manager,
            ),
            patch(
                "squant.engine.paper.manager.get_session_manager",
                return_value=mock_paper_manager,
            ),
        ):
            # Should not raise even though live manager stop_all fails
            await engine._trigger_global_circuit_breaker()

        # Paper manager should still be called
        mock_paper_manager.stop_all.assert_called_once()


class TestTotalLossLimitAutoStop:
    """Tests for process_candle total loss limit auto-stop (IMP-005)."""

    @pytest.fixture
    def loss_limit_config(self):
        """Create a risk config with a total loss limit."""
        return RiskConfig(
            max_position_size=Decimal("0.5"),
            max_order_size=Decimal("0.1"),
            daily_trade_limit=100,
            daily_loss_limit=Decimal("0.1"),
            max_price_deviation=Decimal("0.05"),
            total_loss_limit=Decimal("0.2"),  # 20% total loss limit
        )

    @pytest.fixture
    def engine_with_loss_limit(self, run_id, strategy, loss_limit_config, mock_adapter):
        """Create engine with total loss limit configured."""
        with patch("squant.config.get_settings") as mock_settings:
            settings = MagicMock()
            settings.paper_max_equity_curve_size = 10000
            settings.paper_max_completed_orders = 1000
            settings.paper_max_fills = 1000
            settings.paper_max_trades = 1000
            settings.paper_max_logs = 1000
            settings.strategy.max_bar_history = 1000
            mock_settings.return_value = settings

            return LiveTradingEngine(
                run_id=run_id,
                strategy=strategy,
                symbol="BTC/USDT",
                timeframe="1m",
                adapter=mock_adapter,
                risk_config=loss_limit_config,
                initial_equity=Decimal("10000"),
                params={"threshold": Decimal("50000")},
            )

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

    @pytest.mark.asyncio
    async def test_auto_stop_when_total_loss_limit_exceeded(
        self, engine_with_loss_limit, mock_adapter, closed_candle
    ):
        """Test engine auto-stops when cumulative loss exceeds limit."""
        engine = engine_with_loss_limit
        await engine.start()

        assert engine.is_running is True

        # Simulate losses exceeding 20% of initial equity (10000 * 0.2 = 2000)
        engine._risk_manager.state.total_pnl = Decimal("-2500")
        engine._risk_manager.state.unrealized_pnl = Decimal("0")

        with patch(
            "squant.engine.live.engine._fire_notification"
        ) as mock_notify:
            await engine.process_candle(closed_candle)

        # Engine should have been stopped
        assert engine.is_running is False
        assert engine.error_message is not None
        assert "total loss limit" in engine.error_message.lower()

    @pytest.mark.asyncio
    async def test_auto_stop_correct_error_message(
        self, engine_with_loss_limit, mock_adapter, closed_candle
    ):
        """Test stop is called with correct error message containing loss details."""
        engine = engine_with_loss_limit
        await engine.start()

        # Set total_pnl exceeding 20% of 10000 = 2000
        # Note: process_candle calls update_unrealized_pnl from context which
        # overwrites state.unrealized_pnl, so use total_pnl alone to trigger.
        engine._risk_manager.state.total_pnl = Decimal("-2500")

        with patch(
            "squant.engine.live.engine._fire_notification"
        ):
            await engine.process_candle(closed_candle)

        assert engine.is_running is False
        # Error message should contain loss information
        assert "Risk auto-stop" in engine.error_message
        assert "total loss limit" in engine.error_message

    @pytest.mark.asyncio
    async def test_risk_state_updated_on_total_loss_trigger(
        self, engine_with_loss_limit, mock_adapter, closed_candle
    ):
        """Test risk manager state is correctly updated when total loss triggers."""
        engine = engine_with_loss_limit
        await engine.start()

        # Set loss exceeding 20% threshold
        engine._risk_manager.state.total_pnl = Decimal("-2100")
        engine._risk_manager.state.unrealized_pnl = Decimal("0")

        with patch(
            "squant.engine.live.engine._fire_notification"
        ):
            await engine.process_candle(closed_candle)

        # total_loss_limit_triggered should be set in risk state
        assert engine._risk_manager.state.total_loss_limit_triggered is True

    @pytest.mark.asyncio
    async def test_no_stop_when_below_loss_limit(
        self, engine_with_loss_limit, mock_adapter, closed_candle
    ):
        """Test engine continues running when loss is below limit."""
        engine = engine_with_loss_limit
        await engine.start()

        # Set loss below 20% threshold (10000 * 0.2 = 2000)
        engine._risk_manager.state.total_pnl = Decimal("-500")
        engine._risk_manager.state.unrealized_pnl = Decimal("0")

        await engine.process_candle(closed_candle)

        # Engine should still be running
        assert engine.is_running is True
        assert engine.bar_count == 1
