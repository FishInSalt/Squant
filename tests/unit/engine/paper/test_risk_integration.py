"""Tests for RiskManager integration with PaperTradingEngine."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

from squant.engine.backtest.strategy_base import Strategy
from squant.engine.paper.engine import PaperTradingEngine
from squant.engine.risk.models import RiskConfig
from squant.infra.exchange.okx.ws_types import WSCandle


class DummyStrategy(Strategy):
    """Minimal strategy for testing."""

    def on_init(self) -> None:
        pass

    def on_bar(self, bar) -> None:
        pass

    def on_stop(self) -> None:
        pass


def _make_candle(
    close: str,
    is_closed: bool = True,
    high: str | None = None,
    low: str | None = None,
    ts: datetime | None = None,
) -> WSCandle:
    close_d = Decimal(close)
    return WSCandle(
        symbol="BTC/USDT",
        timeframe="1m",
        timestamp=ts or datetime(2024, 1, 1, 0, 1, tzinfo=UTC),
        open=close_d,
        high=Decimal(high) if high else close_d + Decimal("100"),
        low=Decimal(low) if low else close_d - Decimal("100"),
        close=close_d,
        volume=Decimal("10"),
        is_closed=is_closed,
    )


def _create_engine(
    risk_config: RiskConfig | None = None,
    initial_capital: Decimal = Decimal("100000"),
) -> PaperTradingEngine:
    with patch("squant.config.get_settings") as mock_settings:
        settings = MagicMock()
        settings.paper_max_equity_curve_size = 10000
        settings.paper_max_completed_orders = 1000
        settings.paper_max_fills = 5000
        settings.paper_max_trades = 1000
        settings.paper_max_logs = 500
        mock_settings.return_value = settings

        return PaperTradingEngine(
            run_id=uuid4(),
            strategy=DummyStrategy(),
            symbol="BTC/USDT",
            timeframe="1m",
            initial_capital=initial_capital,
            commission_rate=Decimal("0.001"),
            slippage=Decimal("0"),
            risk_config=risk_config,
        )


class TestRiskManagerIntegration:
    """Tests for risk management in paper trading."""

    async def test_no_risk_manager_allows_all(self):
        """Without risk_config, all orders pass without validation."""
        engine = _create_engine(risk_config=None)
        await engine.start()

        # Place a market order
        engine.context.buy("BTC/USDT", Decimal("0.1"))

        # Process a candle — order should fill without risk check
        candle = _make_candle("50000")
        with patch("squant.config.get_settings") as mock_s:
            settings = MagicMock()
            settings.strategy.cpu_limit_seconds = 5
            settings.strategy.memory_limit_mb = 256
            mock_s.return_value = settings
            await engine.process_candle(candle)

        # Order should have been filled
        assert engine.context.cash < Decimal("100000")
        assert len(engine.context.pending_orders) == 0

    async def test_risk_manager_allows_valid_order(self):
        """Orders within risk limits are filled normally."""
        config = RiskConfig(
            max_position_size=Decimal("0.5"),  # 50% of equity
            max_order_size=Decimal("0.3"),  # 30% of equity
        )
        engine = _create_engine(risk_config=config)
        await engine.start()

        # Place a small order: 0.1 BTC * 50000 = 5000 = 5% of 100k equity → OK
        engine.context.buy("BTC/USDT", Decimal("0.1"))

        candle = _make_candle("50000")
        with patch("squant.config.get_settings") as mock_s:
            settings = MagicMock()
            settings.strategy.cpu_limit_seconds = 5
            settings.strategy.memory_limit_mb = 256
            mock_s.return_value = settings
            await engine.process_candle(candle)

        assert engine.context.cash < Decimal("100000")

    async def test_risk_manager_rejects_oversized_order(self):
        """Orders exceeding max_order_size are rejected."""
        config = RiskConfig(
            max_position_size=Decimal("0.5"),
            max_order_size=Decimal("0.01"),  # 1% of equity = 1000 USDT max
        )
        engine = _create_engine(risk_config=config)
        await engine.start()

        # Place oversized order: 0.1 BTC * 50000 = 5000 = 5% > 1% limit
        engine.context.buy("BTC/USDT", Decimal("0.1"))

        candle = _make_candle("50000")
        with patch("squant.config.get_settings") as mock_s:
            settings = MagicMock()
            settings.strategy.cpu_limit_seconds = 5
            settings.strategy.memory_limit_mb = 256
            mock_s.return_value = settings
            await engine.process_candle(candle)

        # Order should NOT have been filled — cash unchanged
        assert engine.context.cash == Decimal("100000")
        # Order should be cancelled
        assert len(engine.context.pending_orders) == 0

    async def test_risk_state_in_snapshot(self):
        """get_state_snapshot() includes risk_state when risk manager is present."""
        config = RiskConfig()
        engine = _create_engine(risk_config=config)
        await engine.start()

        snapshot = engine.get_state_snapshot()
        assert "risk_state" in snapshot
        assert snapshot["risk_state"] is not None
        assert "daily_trade_count" in snapshot["risk_state"]
        assert "circuit_breaker_triggered" in snapshot["risk_state"]

    async def test_no_risk_state_without_config(self):
        """get_state_snapshot() has risk_state=None without risk config."""
        engine = _create_engine(risk_config=None)
        await engine.start()

        snapshot = engine.get_state_snapshot()
        assert snapshot["risk_state"] is None

    async def test_risk_state_in_persistence(self):
        """build_result_for_persistence() includes risk_state."""
        config = RiskConfig()
        engine = _create_engine(risk_config=config)
        await engine.start()

        result = engine.build_result_for_persistence()
        assert "risk_state" in result
        assert result["risk_state"]["initial_equity"] == 100000.0

    async def test_risk_manager_tracks_equity_updates(self):
        """Risk manager equity is updated after each closed candle."""
        config = RiskConfig(
            max_position_size=Decimal("0.9"),
            max_order_size=Decimal("0.9"),
        )
        engine = _create_engine(risk_config=config)
        await engine.start()

        # Place and fill an order
        engine.context.buy("BTC/USDT", Decimal("0.1"))

        candle = _make_candle("50000")
        with patch("squant.config.get_settings") as mock_s:
            settings = MagicMock()
            settings.strategy.cpu_limit_seconds = 5
            settings.strategy.memory_limit_mb = 256
            mock_s.return_value = settings
            await engine.process_candle(candle)

        # Risk manager should have updated equity
        risk_state = engine._risk_manager.get_state_summary()
        assert risk_state["current_equity"] > 0

    async def test_risk_manager_rejects_position_limit(self):
        """Orders exceeding position size limit are rejected."""
        config = RiskConfig(
            max_position_size=Decimal("0.04"),  # 4% of equity
            max_order_size=Decimal("0.9"),  # allow large orders
        )
        engine = _create_engine(risk_config=config)
        await engine.start()

        # 0.1 BTC * 50000 = 5000 = 5% > 4% position limit
        engine.context.buy("BTC/USDT", Decimal("0.1"))

        candle = _make_candle("50000")
        with patch("squant.config.get_settings") as mock_s:
            settings = MagicMock()
            settings.strategy.cpu_limit_seconds = 5
            settings.strategy.memory_limit_mb = 256
            mock_s.return_value = settings
            await engine.process_candle(candle)

        # Should be rejected
        assert engine.context.cash == Decimal("100000")

    async def test_partial_fill_risk_uses_remaining(self):
        """Risk check after partial fill uses order.remaining, not full amount.

        Scenario: order for 0.1 BTC gets partially filled (0.05 BTC) due to
        volume participation limits. On the next candle, the risk check should
        use remaining=0.05, not amount=0.1, so position check calculates
        position + 0.05 (correct) instead of position + 0.1 (double-count).
        """
        config = RiskConfig(
            max_position_size=Decimal("0.08"),  # 8% of equity = 8000 USDT
            max_order_size=Decimal("0.9"),
        )
        engine = _create_engine(risk_config=config, initial_capital=Decimal("100000"))
        await engine.start()

        # Place market order for 0.1 BTC at $50000 = $5000 (5% < 8% → allowed)
        engine.context.buy("BTC/USDT", Decimal("0.1"))

        # First candle: low volume → partial fill via volume participation
        # With volume=1 and participation=0.1 → max 0.1 BTC fill
        # But engine uses default matching engine without volume participation.
        # Instead, directly test by simulating partial fill state:
        # Manually set up a partially filled order scenario
        from squant.engine.backtest.types import (
            OrderSide,
            OrderStatus,
            OrderType,
            SimulatedOrder,
        )

        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            amount=Decimal("0.1"),
        )
        order.filled = Decimal("0.05")  # 50% filled
        order.status = OrderStatus.PARTIAL

        # Verify order.remaining is 0.05
        assert order.remaining == Decimal("0.05")

        # Risk check should use remaining (0.05), not amount (0.1)
        # With position=0.05 BTC from partial fill:
        # If risk uses order.amount: new_pos = 0.05 + 0.1 = 0.15 * 50000 = 7500 → 7.5% < 8% → pass
        # If risk uses order.remaining: new_pos = 0.05 + 0.05 = 0.1 * 50000 = 5000 → 5% < 8% → pass
        # Both pass for this case, so let's test a tighter scenario:

        # Position = 0.12 BTC already, order.amount=0.1, order.remaining=0.05
        # If uses amount: 0.12+0.1=0.22 * 50000 = 11000 → 11% > 8% → REJECTED (wrong!)
        # If uses remaining: 0.12+0.05=0.17 * 50000 = 8500 → 8.5% > 8% → still rejected
        # Use 6% limit:
        config2 = RiskConfig(
            max_position_size=Decimal("0.09"),  # 9% of equity = 9000
            max_order_size=Decimal("0.9"),
        )
        engine2 = _create_engine(risk_config=config2, initial_capital=Decimal("100000"))
        await engine2.start()

        # Simulate position of 0.12 BTC
        from squant.engine.backtest.types import Position

        engine2._context._positions["BTC/USDT"] = Position(
            symbol="BTC/USDT",
            amount=Decimal("0.12"),
            avg_entry_price=Decimal("50000"),
        )

        # Partially filled order: amount=0.1, filled=0.05, remaining=0.05
        order2 = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            amount=Decimal("0.1"),
        )
        order2.filled = Decimal("0.05")
        order2.status = OrderStatus.PARTIAL

        # With remaining: pos = 0.12+0.05 = 0.17 * 50000 = 8500 → 8.5% < 9% → PASS
        # With amount:    pos = 0.12+0.10 = 0.22 * 50000 = 11000 → 11% > 9% → REJECT
        result = engine2._validate_order_risk(order2, Decimal("50000"))
        assert result is True, "Partial fill should use remaining, not full amount"


class TestVolumeBudgetIntegration:
    """Tests for volume budget correctness at the engine level."""

    async def test_risk_rejected_limit_preserves_budget(self):
        """When a limit fill is risk-rejected, its budget is preserved for other orders.

        Without fix: matching engine deducts budget for ALL generated fills,
        then engine rejects some fills, permanently losing that budget.
        With fix: engine processes limits one-at-a-time, only deducting after
        risk check passes.
        """
        from squant.engine.backtest.types import Position

        config = RiskConfig(
            max_position_size=Decimal("0.04"),  # 4% of equity = $4000
            max_order_size=Decimal("0.9"),
        )
        engine = _create_engine(risk_config=config, initial_capital=Decimal("100000"))
        engine._matching_engine.max_volume_participation = Decimal("0.1")
        await engine.start()

        # Place two limit buy orders:
        # Order 1: 0.05 BTC @ $50000 → $2500 → but with existing position
        #          it will exceed 4% limit → REJECTED by risk
        # Order 2: 0.05 BTC @ $49000 → should still fill if budget is preserved

        # Set up existing position that makes order1 exceed limit
        engine._context._positions["BTC/USDT"] = Position(
            symbol="BTC/USDT",
            amount=Decimal("0.04"),
            avg_entry_price=Decimal("50000"),
        )
        # Current position: 0.04 * $50000 = $2000 = 2%
        # After order1: 0.04+0.05 = 0.09 * $50000 = $4500 = 4.5% > 4% → REJECTED
        # After order2 alone: 0.04+0.05 = 0.09 * $49000 = $4410 = 4.41% > 4% → also rejected
        # Adjust: make order2 small enough to pass
        engine.context.buy("BTC/USDT", Decimal("0.05"), price=Decimal("50000"))
        engine.context.buy("BTC/USDT", Decimal("0.03"), price=Decimal("49000"))
        # After order2: 0.04+0.03 = 0.07 * $49000 = $3430 = 3.43% < 4% → PASS

        # Candle: low=$48000 triggers both limits, volume=100, budget=10 BTC
        candle = WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 0, 1, tzinfo=UTC),
            open=Decimal("50500"),
            high=Decimal("51000"),
            low=Decimal("48000"),
            close=Decimal("50000"),
            volume=Decimal("100"),
            is_closed=True,
        )

        with patch("squant.config.get_settings") as mock_s:
            settings = MagicMock()
            settings.strategy.cpu_limit_seconds = 5
            settings.strategy.memory_limit_mb = 256
            mock_s.return_value = settings
            await engine.process_candle(candle)

        # Order1 (0.05 @ $50000) should be rejected (4.5% > 4%)
        # Order2 (0.03 @ $49000) should be filled (3.43% < 4%) — budget was preserved
        pos = engine._context._positions.get("BTC/USDT")
        assert pos is not None
        # Original position 0.04 + order2's 0.03 = 0.07
        assert pos.amount == Decimal("0.07"), (
            f"Expected 0.07 (order2 filled after order1 risk-rejected), got {pos.amount}"
        )

    async def test_cross_update_volume_cap(self):
        """Cumulative fills across unclosed candle updates must not exceed bar budget.

        Without fix: each unclosed update computes a fresh budget from cumulative
        volume, allowing total fills to exceed final_volume * participation_rate.
        With fix: engine tracks bar-level consumption and subtracts it.
        """
        config = RiskConfig(
            max_position_size=Decimal("0.9"),
            max_order_size=Decimal("0.9"),
        )
        engine = _create_engine(risk_config=config, initial_capital=Decimal("10000000"))
        engine._matching_engine.max_volume_participation = Decimal("0.10")
        await engine.start()

        # Place a large limit order: 50 BTC @ $49000
        engine.context.buy("BTC/USDT", Decimal("50"), price=Decimal("49000"))

        bar_ts = datetime(2024, 1, 1, 0, 1, tzinfo=UTC)

        # Unclosed update 1: volume=100, budget=10, minus consumed=0 → fill 10
        candle1 = WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=bar_ts,
            open=Decimal("49500"),
            high=Decimal("50000"),
            low=Decimal("48000"),
            close=Decimal("49000"),
            volume=Decimal("100"),
            is_closed=False,
        )
        with patch("squant.config.get_settings") as mock_s:
            settings = MagicMock()
            settings.strategy.cpu_limit_seconds = 5
            settings.strategy.memory_limit_mb = 256
            mock_s.return_value = settings
            await engine.process_candle(candle1)

        pos1 = engine._context._positions.get("BTC/USDT")
        fill_after_1 = pos1.amount if pos1 else Decimal("0")
        assert fill_after_1 == Decimal("10"), f"First update should fill 10, got {fill_after_1}"

        # Unclosed update 2: volume=200, budget=20, minus consumed=10 → fill 10 more
        candle2 = WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=bar_ts,
            open=Decimal("49500"),
            high=Decimal("50000"),
            low=Decimal("48000"),
            close=Decimal("49000"),
            volume=Decimal("200"),
            is_closed=False,
        )
        with patch("squant.config.get_settings") as mock_s:
            settings = MagicMock()
            settings.strategy.cpu_limit_seconds = 5
            settings.strategy.memory_limit_mb = 256
            mock_s.return_value = settings
            await engine.process_candle(candle2)

        pos2 = engine._context._positions.get("BTC/USDT")
        fill_after_2 = pos2.amount if pos2 else Decimal("0")
        assert fill_after_2 == Decimal("20"), f"After 2 updates should fill 20, got {fill_after_2}"

        # Closed candle: volume=250, budget=25, minus consumed=20 → fill 5 more
        candle3 = WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=bar_ts,
            open=Decimal("49500"),
            high=Decimal("50000"),
            low=Decimal("48000"),
            close=Decimal("49000"),
            volume=Decimal("250"),
            is_closed=True,
        )
        with patch("squant.config.get_settings") as mock_s:
            settings = MagicMock()
            settings.strategy.cpu_limit_seconds = 5
            settings.strategy.memory_limit_mb = 256
            mock_s.return_value = settings
            await engine.process_candle(candle3)

        pos3 = engine._context._positions.get("BTC/USDT")
        fill_after_3 = pos3.amount if pos3 else Decimal("0")
        # Total should be exactly 250 * 0.10 = 25 BTC, not more
        assert fill_after_3 == Decimal("25"), (
            f"Total fills across 3 updates should be 25 (= 250 * 0.10), got {fill_after_3}"
        )


class TestTradeCompletionDetection:
    """Tests that trade completion is detected even when _trades deque is full."""

    async def test_trade_completion_detected_when_deque_full(self):
        """Risk manager records trade PnL even after _trades deque reaches maxlen.

        Regression test for R7-001: the old len(_trades) > before pattern fails
        when deque is at capacity because append doesn't increase len.
        """
        config = RiskConfig(daily_loss_limit_absolute=Decimal("999999"))
        # Create engine with small max_trades to trigger the deque-full condition
        with patch("squant.config.get_settings") as mock_settings:
            settings = MagicMock()
            settings.paper_max_equity_curve_size = 10000
            settings.paper_max_completed_orders = 1000
            settings.paper_max_fills = 5000
            settings.paper_max_trades = 3  # Very small to trigger maxlen quickly
            settings.paper_max_logs = 500
            mock_settings.return_value = settings

            engine = PaperTradingEngine(
                run_id=uuid4(),
                strategy=DummyStrategy(),
                symbol="BTC/USDT",
                timeframe="1m",
                initial_capital=Decimal("1000000"),
                commission_rate=Decimal("0"),
                slippage=Decimal("0"),
                risk_config=config,
            )
        await engine.start()

        base_time = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
        record_calls = []
        original_record = engine._risk_manager.record_trade_result

        def tracking_record(pnl):
            record_calls.append(pnl)
            return original_record(pnl)

        engine._risk_manager.record_trade_result = tracking_record

        # Execute 5 round-trip trades (buy then sell), deque maxlen=3 overflows at trade 4
        for i in range(5):
            buy_price = Decimal("50000")
            sell_price = Decimal("50100")  # Small profit each trade
            buy_ts = base_time.replace(minute=i * 2)
            sell_ts = base_time.replace(minute=i * 2 + 1)

            # Buy
            engine.context.buy("BTC/USDT", Decimal("0.1"))
            candle_buy = WSCandle(
                symbol="BTC/USDT",
                timeframe="1m",
                timestamp=buy_ts,
                open=buy_price,
                high=buy_price + Decimal("50"),
                low=buy_price - Decimal("50"),
                close=buy_price,
                volume=Decimal("100"),
                is_closed=True,
            )
            with patch("squant.config.get_settings") as mock_s:
                s = MagicMock()
                s.strategy.cpu_limit_seconds = 5
                s.strategy.memory_limit_mb = 256
                mock_s.return_value = s
                await engine.process_candle(candle_buy)

            # Sell (closes position)
            engine.context.sell("BTC/USDT", Decimal("0.1"))
            candle_sell = WSCandle(
                symbol="BTC/USDT",
                timeframe="1m",
                timestamp=sell_ts,
                open=sell_price,
                high=sell_price + Decimal("50"),
                low=sell_price - Decimal("50"),
                close=sell_price,
                volume=Decimal("100"),
                is_closed=True,
            )
            with patch("squant.config.get_settings") as mock_s:
                s = MagicMock()
                s.strategy.cpu_limit_seconds = 5
                s.strategy.memory_limit_mb = 256
                mock_s.return_value = s
                await engine.process_candle(candle_sell)

        # All 5 trades should have been recorded, including trades 4 and 5
        # which overflow the deque (maxlen=3)
        assert len(record_calls) == 5, (
            f"Expected 5 record_trade_result calls, got {len(record_calls)}. "
            f"Trades 4+ may have been missed due to deque maxlen."
        )
        # Each trade should have positive PnL
        for i, pnl in enumerate(record_calls):
            assert pnl > 0, f"Trade {i + 1} PnL should be positive, got {pnl}"
