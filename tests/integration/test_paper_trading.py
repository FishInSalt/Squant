"""Integration tests for paper trading.

These tests verify the complete flow from API to engine execution.
Note: Some tests require a running database and may be skipped in CI.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from squant.engine.paper.engine import PaperTradingEngine
from squant.engine.paper.manager import SessionManager
from squant.infra.exchange.okx.ws_types import WSCandle

# Test strategy code for integration tests
TEST_STRATEGY_CODE = '''
class TestStrategy(Strategy):
    """Simple test strategy for integration testing."""

    def on_init(self):
        self.buy_price = self.ctx.params.get("buy_price", Decimal("45000"))
        self.initialized = True

    def on_bar(self, bar):
        if bar.close < self.buy_price and not self.ctx.has_position(bar.symbol):
            self.ctx.buy(bar.symbol, Decimal("0.1"))
        elif bar.close > self.buy_price and self.ctx.has_position(bar.symbol):
            pos = self.ctx.get_position(bar.symbol)
            self.ctx.sell(bar.symbol, pos.amount)

    def on_stop(self):
        self.stopped = True
'''


class TestPaperTradingIntegration:
    """Integration tests for paper trading flow."""

    @pytest.fixture
    def session_manager(self):
        """Create a fresh session manager."""
        return SessionManager()

    @pytest.fixture
    def strategy_instance(self):
        """Create a strategy instance from test code."""
        from squant.engine.backtest.strategy_base import Strategy as StrategyBase
        from squant.engine.backtest.types import Bar, OrderSide, OrderType, Position
        from squant.engine.sandbox import compile_strategy

        compiled = compile_strategy(TEST_STRATEGY_CODE)
        compiled.restricted_globals["Strategy"] = StrategyBase
        compiled.restricted_globals["Bar"] = Bar
        compiled.restricted_globals["Position"] = Position
        compiled.restricted_globals["OrderSide"] = OrderSide
        compiled.restricted_globals["OrderType"] = OrderType

        local_namespace = {}
        exec(compiled.code_object, compiled.restricted_globals, local_namespace)

        strategy_class = None
        for _name, obj in local_namespace.items():
            if isinstance(obj, type) and issubclass(obj, StrategyBase) and obj is not StrategyBase:
                strategy_class = obj
                break

        return strategy_class()

    @pytest.fixture
    def engine(self, strategy_instance):
        """Create a paper trading engine with the test strategy."""
        return PaperTradingEngine(
            run_id=uuid4(),
            strategy=strategy_instance,
            symbol="BTC/USDT",
            timeframe="1m",
            initial_capital=Decimal("10000"),
            commission_rate=Decimal("0.001"),
            slippage=Decimal("0"),
            params={"buy_price": Decimal("45000")},
        )

    @pytest.mark.asyncio
    async def test_full_trading_cycle(self, session_manager, engine):
        """Test a complete trading cycle: start, trade, stop."""
        # Register and start
        await session_manager.register(engine)
        await engine.start()

        assert engine.is_running
        assert engine.context.params.get("buy_price") == Decimal("45000")

        # First candle: price below threshold, should place buy order
        candle1 = WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            open=Decimal("44000"),
            high=Decimal("44500"),
            low=Decimal("43500"),
            close=Decimal("44200"),
            volume=Decimal("100"),
            is_closed=True,
        )
        await session_manager.dispatch_candle(candle1)

        assert engine.bar_count == 1
        assert len(engine.context.pending_orders) == 1

        # Second candle: order gets filled
        candle2 = WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 1, 0, tzinfo=UTC),
            open=Decimal("44300"),
            high=Decimal("44800"),
            low=Decimal("44100"),
            close=Decimal("44500"),
            volume=Decimal("100"),
            is_closed=True,
        )
        await session_manager.dispatch_candle(candle2)

        assert engine.bar_count == 2
        assert len(engine.context.pending_orders) == 0
        assert engine.context.has_position("BTC/USDT")

        # Third candle: price above threshold, should place sell order
        candle3 = WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 2, 0, tzinfo=UTC),
            open=Decimal("45500"),
            high=Decimal("46000"),
            low=Decimal("45000"),
            close=Decimal("45800"),
            volume=Decimal("100"),
            is_closed=True,
        )
        await session_manager.dispatch_candle(candle3)

        assert len(engine.context.pending_orders) == 1

        # Fourth candle: sell order gets filled
        candle4 = WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 3, 0, tzinfo=UTC),
            open=Decimal("45900"),
            high=Decimal("46500"),
            low=Decimal("45700"),
            close=Decimal("46200"),
            volume=Decimal("100"),
            is_closed=True,
        )
        await session_manager.dispatch_candle(candle4)

        assert not engine.context.has_position("BTC/USDT")
        assert len(engine.context.trades) == 1

        # Stop engine
        await engine.stop()
        await session_manager.unregister(engine.run_id)

        assert not engine.is_running
        assert session_manager.session_count == 0

    @pytest.mark.asyncio
    async def test_equity_tracking(self, session_manager, engine):
        """Test that equity is properly tracked during trading."""
        await session_manager.register(engine)
        await engine.start()

        initial_equity = engine.context.equity

        # Process a candle
        candle = WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            open=Decimal("44000"),
            high=Decimal("44500"),
            low=Decimal("43500"),
            close=Decimal("44200"),
            volume=Decimal("100"),
            is_closed=True,
        )
        await session_manager.dispatch_candle(candle)

        # Equity curve should have a snapshot
        assert len(engine.context.equity_curve) == 1

        # Equity should still be initial (no position yet)
        assert engine.context.equity == initial_equity

        await engine.stop()

    @pytest.mark.asyncio
    async def test_multiple_sessions_isolation(self, session_manager, strategy_instance):
        """Test that multiple sessions are properly isolated."""
        # Create two engines for different symbols
        engine1 = PaperTradingEngine(
            run_id=uuid4(),
            strategy=strategy_instance,
            symbol="BTC/USDT",
            timeframe="1m",
            initial_capital=Decimal("10000"),
        )

        # Need a fresh strategy instance for second engine
        from squant.engine.backtest.strategy_base import Strategy as StrategyBase
        from squant.engine.backtest.types import Bar, OrderSide, OrderType, Position
        from squant.engine.sandbox import compile_strategy

        compiled = compile_strategy(TEST_STRATEGY_CODE)
        compiled.restricted_globals["Strategy"] = StrategyBase
        compiled.restricted_globals["Bar"] = Bar
        compiled.restricted_globals["Position"] = Position
        compiled.restricted_globals["OrderSide"] = OrderSide
        compiled.restricted_globals["OrderType"] = OrderType

        local_namespace = {}
        exec(compiled.code_object, compiled.restricted_globals, local_namespace)
        strategy_class = None
        for _name, obj in local_namespace.items():
            if isinstance(obj, type) and issubclass(obj, StrategyBase) and obj is not StrategyBase:
                strategy_class = obj
                break
        strategy2 = strategy_class()

        engine2 = PaperTradingEngine(
            run_id=uuid4(),
            strategy=strategy2,
            symbol="ETH/USDT",
            timeframe="1m",
            initial_capital=Decimal("5000"),
        )

        await session_manager.register(engine1)
        await session_manager.register(engine2)
        await engine1.start()
        await engine2.start()

        # BTC candle should only affect engine1
        btc_candle = WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            open=Decimal("44000"),
            high=Decimal("44500"),
            low=Decimal("43500"),
            close=Decimal("44200"),
            volume=Decimal("100"),
            is_closed=True,
        )
        await session_manager.dispatch_candle(btc_candle)

        assert engine1.bar_count == 1
        assert engine2.bar_count == 0

        # ETH candle should only affect engine2
        eth_candle = WSCandle(
            symbol="ETH/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            open=Decimal("2200"),
            high=Decimal("2250"),
            low=Decimal("2150"),
            close=Decimal("2220"),
            volume=Decimal("500"),
            is_closed=True,
        )
        await session_manager.dispatch_candle(eth_candle)

        assert engine1.bar_count == 1
        assert engine2.bar_count == 1

        await engine1.stop()
        await engine2.stop()

    @pytest.mark.asyncio
    async def test_state_snapshot_accuracy(self, session_manager, engine):
        """Test that state snapshots accurately reflect engine state."""
        await session_manager.register(engine)
        await engine.start()

        # Initial state
        snapshot = engine.get_state_snapshot()
        assert snapshot["is_running"] is True
        assert Decimal(snapshot["cash"]) == Decimal("10000")
        assert Decimal(snapshot["equity"]) == Decimal("10000")
        assert snapshot["positions"] == {}

        # Process candles to get a position
        candle1 = WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            open=Decimal("44000"),
            high=Decimal("44500"),
            low=Decimal("43500"),
            close=Decimal("44200"),
            volume=Decimal("100"),
            is_closed=True,
        )
        await session_manager.dispatch_candle(candle1)

        candle2 = WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 1, 0, tzinfo=UTC),
            open=Decimal("44300"),
            high=Decimal("44800"),
            low=Decimal("44100"),
            close=Decimal("44500"),
            volume=Decimal("100"),
            is_closed=True,
        )
        await session_manager.dispatch_candle(candle2)

        # Check state after position
        snapshot = engine.get_state_snapshot()
        assert snapshot["bar_count"] == 2
        assert "BTC/USDT" in snapshot["positions"]
        assert Decimal(snapshot["positions"]["BTC/USDT"]["amount"]) == Decimal("0.1")
        assert Decimal(snapshot["cash"]) < Decimal("10000")  # Cash reduced after buy

        await engine.stop()

    @pytest.mark.asyncio
    async def test_graceful_shutdown(self, session_manager):
        """Test graceful shutdown of all sessions."""
        # Create multiple engines
        engines = []
        for i in range(3):
            from squant.engine.backtest.strategy_base import Strategy as StrategyBase
            from squant.engine.backtest.types import Bar, OrderSide, OrderType, Position
            from squant.engine.sandbox import compile_strategy

            compiled = compile_strategy(TEST_STRATEGY_CODE)
            compiled.restricted_globals["Strategy"] = StrategyBase
            compiled.restricted_globals["Bar"] = Bar
            compiled.restricted_globals["Position"] = Position
            compiled.restricted_globals["OrderSide"] = OrderSide
            compiled.restricted_globals["OrderType"] = OrderType

            local_namespace = {}
            exec(compiled.code_object, compiled.restricted_globals, local_namespace)
            strategy_class = None
            for _name, obj in local_namespace.items():
                if (
                    isinstance(obj, type)
                    and issubclass(obj, StrategyBase)
                    and obj is not StrategyBase
                ):
                    strategy_class = obj
                    break

            engine = PaperTradingEngine(
                run_id=uuid4(),
                strategy=strategy_class(),
                symbol="BTC/USDT",
                timeframe="1m",
                initial_capital=Decimal("10000"),
            )
            engines.append(engine)
            await session_manager.register(engine)
            await engine.start()

        assert session_manager.session_count == 3

        # Graceful shutdown
        await session_manager.stop_all(reason="test shutdown")

        # All engines should be stopped
        for engine in engines:
            assert not engine.is_running
            assert engine.error_message is not None
            assert "test shutdown" in engine.error_message


class TestErrorHandling:
    """Tests for error handling scenarios."""

    @pytest.mark.asyncio
    async def test_strategy_error_in_on_bar(self):
        """Test handling of strategy errors during on_bar."""
        # Strategy that raises an error
        error_strategy_code = """
class ErrorStrategy(Strategy):
    def on_init(self):
        pass

    def on_bar(self, bar):
        if bar.close > Decimal("44000"):
            raise ValueError("Test error in on_bar")

    def on_stop(self):
        pass
"""
        from squant.engine.backtest.strategy_base import Strategy as StrategyBase
        from squant.engine.backtest.types import Bar, OrderSide, OrderType, Position
        from squant.engine.sandbox import compile_strategy

        compiled = compile_strategy(error_strategy_code)
        compiled.restricted_globals["Strategy"] = StrategyBase
        compiled.restricted_globals["Bar"] = Bar
        compiled.restricted_globals["Position"] = Position
        compiled.restricted_globals["OrderSide"] = OrderSide
        compiled.restricted_globals["OrderType"] = OrderType

        local_namespace = {}
        exec(compiled.code_object, compiled.restricted_globals, local_namespace)
        strategy_class = None
        for _name, obj in local_namespace.items():
            if isinstance(obj, type) and issubclass(obj, StrategyBase) and obj is not StrategyBase:
                strategy_class = obj
                break

        engine = PaperTradingEngine(
            run_id=uuid4(),
            strategy=strategy_class(),
            symbol="BTC/USDT",
            timeframe="1m",
            initial_capital=Decimal("10000"),
        )

        await engine.start()

        # This candle should trigger the error
        candle = WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            open=Decimal("44000"),
            high=Decimal("45000"),
            low=Decimal("43500"),
            close=Decimal("44500"),
            volume=Decimal("100"),
            is_closed=True,
        )

        with pytest.raises(ValueError):
            await engine.process_candle(candle)

        assert not engine.is_running
        assert "Test error in on_bar" in engine.error_message
