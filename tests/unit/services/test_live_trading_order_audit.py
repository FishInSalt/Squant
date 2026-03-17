"""Tests for LIVE-013: order/trade audit persistence."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from squant.engine.backtest.strategy_base import Strategy
from squant.engine.backtest.types import Bar
from squant.engine.live.engine import LiveOrder, LiveTradingEngine
from squant.engine.risk import RiskConfig
from squant.infra.exchange.ws_types import WSCandle
from squant.infra.exchange.types import (
    AccountBalance,
    Balance,
    OrderResponse,
)
from squant.models.enums import OrderSide, OrderStatus, OrderType

# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------

class NoOpStrategy(Strategy):
    """Strategy that does nothing — used when we don't need on_bar logic."""

    def on_init(self) -> None:
        pass

    def on_bar(self, bar: Bar) -> None:
        pass

    def on_stop(self) -> None:
        pass


class BuyOnceStrategy(Strategy):
    """Strategy that buys once."""

    def on_init(self) -> None:
        self._bought = False

    def on_bar(self, bar: Bar) -> None:
        if not self._bought:
            self.ctx.buy(bar.symbol, Decimal("0.01"))
            self._bought = True

    def on_stop(self) -> None:
        pass


@pytest.fixture
def risk_config():
    return RiskConfig(
        max_position_size=Decimal("0.5"),
        max_order_size=Decimal("0.1"),
        daily_trade_limit=100,
        daily_loss_limit=Decimal("0.1"),
        max_price_deviation=Decimal("0.05"),
        circuit_breaker_enabled=True,
        circuit_breaker_loss_count=5,
        circuit_breaker_cooldown_minutes=30,
    )


@pytest.fixture
def mock_adapter():
    adapter = AsyncMock()
    adapter.connect = AsyncMock()
    adapter.get_balance = AsyncMock(
        return_value=AccountBalance(
            exchange="okx",
            balances=[
                Balance(currency="USDT", available=Decimal("10000"), frozen=Decimal("0")),
                Balance(currency="BTC", available=Decimal("0"), frozen=Decimal("0")),
            ],
        )
    )
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
    adapter.cancel_order = AsyncMock(
        return_value=OrderResponse(
            order_id="exchange-123",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            status=OrderStatus.CANCELLED,
            price=None,
            amount=Decimal("0.01"),
            filled=Decimal("0"),
        )
    )
    return adapter


def _make_engine(
    strategy=None,
    risk_config=None,
    adapter=None,
    on_order_persist=None,
):
    return LiveTradingEngine(
        run_id=uuid4(),
        strategy=strategy or NoOpStrategy(),
        symbol="BTC/USDT",
        timeframe="1m",
        adapter=adapter or AsyncMock(),
        risk_config=risk_config
        or RiskConfig(
            max_position_size=Decimal("0.5"),
            max_order_size=Decimal("0.1"),
            daily_trade_limit=100,
            daily_loss_limit=Decimal("0.1"),
        ),
        initial_equity=Decimal("10000"),
        on_order_persist=on_order_persist,
    )


def _make_live_order(**kwargs) -> LiveOrder:
    defaults = {
        "internal_id": "order-1",
        "exchange_order_id": "exchange-123",
        "symbol": "BTC/USDT",
        "side": OrderSide.BUY,
        "order_type": "market",
        "amount": Decimal("0.01"),
        "price": None,
        "status": OrderStatus.SUBMITTED,
    }
    defaults.update(kwargs)
    lo = LiveOrder(**defaults)
    lo.created_at = datetime.now(UTC)
    return lo


# ===========================================================================
# Engine-level event buffering tests
# ===========================================================================


class TestOrderEventBuffering:
    """Test that engine buffers placed/fill events correctly."""

    def test_submit_order_buffers_placed_event(self, risk_config, mock_adapter):
        """After _submit_order, buffer should contain a 'placed' event."""
        engine = _make_engine(
            strategy=BuyOnceStrategy(),
            risk_config=risk_config,
            adapter=mock_adapter,
        )
        assert engine._pending_order_events == []

    async def test_submit_order_creates_placed_event(self, risk_config, mock_adapter):
        """_submit_order should buffer a 'placed' event."""
        engine = _make_engine(
            strategy=BuyOnceStrategy(),
            risk_config=risk_config,
            adapter=mock_adapter,
        )
        await engine.start()

        # Simulate a strategy order
        order = MagicMock()
        order.id = "test-order-1"
        order.symbol = "BTC/USDT"
        order.side = OrderSide.BUY
        order.type = OrderType.MARKET
        order.amount = Decimal("0.01")
        order.price = None
        order.stop_price = None

        await engine._submit_order(order)

        # Should have exactly one "placed" event
        assert len(engine._pending_order_events) == 1
        evt = engine._pending_order_events[0]
        assert evt["type"] == "placed"
        assert evt["internal_id"] == "test-order-1"
        assert evt["exchange_order_id"] == "exchange-123"
        assert evt["symbol"] == "BTC/USDT"
        assert evt["side"] == "buy"
        assert evt["order_type"] == "market"
        assert evt["amount"] == "0.01"

    def test_record_fill_buffers_ws_event(self):
        """_record_fill (WS path) should buffer a 'fill' event."""
        engine = _make_engine()
        live_order = _make_live_order()
        engine._live_orders[live_order.internal_id] = live_order

        engine._record_fill(
            live_order, Decimal("50000"), Decimal("0.01"),
            Decimal("0.005"), Decimal("0.005"), source="ws",
        )

        assert len(engine._pending_order_events) == 1
        evt = engine._pending_order_events[0]
        assert evt["type"] == "fill"
        assert evt["internal_id"] == "order-1"
        assert evt["fill_price"] == "50000"
        assert evt["fill_amount"] == "0.01"
        assert evt["fee"] == "0.005"
        assert evt["fill_source"] == "ws"

    def test_record_fill_buffers_poll_event(self):
        """_record_fill (polling path) should buffer a 'fill' event."""
        engine = _make_engine()
        live_order = _make_live_order()

        engine._record_fill(
            live_order, Decimal("49500"), Decimal("0.01"),
            Decimal("0.004"), Decimal("0.004"), source="poll",
        )

        assert len(engine._pending_order_events) == 1
        evt = engine._pending_order_events[0]
        assert evt["type"] == "fill"
        assert evt["fill_price"] == "49500"
        assert evt["fill_amount"] == "0.01"
        assert evt["fee"] == "0.004"
        assert evt["fill_source"] == "poll"

    async def test_process_candle_flushes_events(self, risk_config, mock_adapter):
        """process_candle should flush pending events via on_order_persist."""
        persist_cb = AsyncMock()
        engine = _make_engine(
            risk_config=risk_config,
            adapter=mock_adapter,
            on_order_persist=persist_cb,
        )
        await engine.start()

        # Manually buffer some events
        engine._pending_order_events.append({"type": "placed", "internal_id": "o1"})
        engine._pending_order_events.append({"type": "fill", "internal_id": "o1"})

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

        # Callback should have been called with the 2 events
        persist_cb.assert_called_once()
        call_args = persist_cb.call_args
        assert call_args[0][0] == str(engine.run_id)  # run_id
        assert len(call_args[0][1]) == 2  # 2 events

        # Buffer should be cleared
        assert engine._pending_order_events == []

    async def test_process_candle_retries_events_on_callback_failure(
        self, risk_config, mock_adapter
    ):
        """Buffer should be restored for retry if persist callback raises."""
        persist_cb = AsyncMock(side_effect=Exception("DB error"))
        engine = _make_engine(
            risk_config=risk_config,
            adapter=mock_adapter,
            on_order_persist=persist_cb,
        )
        await engine.start()

        engine._pending_order_events.append({"type": "placed", "internal_id": "o1"})

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

        # Events restored for retry on next bar (F-10 fix)
        assert len(engine._pending_order_events) == 1
        assert engine._pending_order_events[0]["internal_id"] == "o1"

    async def test_no_flush_without_callback(self, risk_config, mock_adapter):
        """Without on_order_persist, pending events remain (no crash)."""
        engine = _make_engine(
            risk_config=risk_config,
            adapter=mock_adapter,
            on_order_persist=None,
        )
        await engine.start()

        engine._pending_order_events.append({"type": "placed", "internal_id": "o1"})

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

        # Events stay in buffer (not cleared) since there's no callback
        assert len(engine._pending_order_events) == 1


# ===========================================================================
# Service-level callback tests
# ===========================================================================


class TestOrderPersistCallback:
    """Test the _create_order_persist_callback closure."""

    async def test_placed_event_creates_order(self):
        """A 'placed' event should create an Order record."""
        from squant.services.live_trading import LiveTradingService

        mock_order = MagicMock()
        mock_order.id = "db-order-uuid-1"

        mock_order_repo = AsyncMock()
        mock_order_repo.create = AsyncMock(return_value=mock_order)

        mock_trade_repo = AsyncMock()

        callback = LiveTradingService._create_order_persist_callback(
            account_id="acc-123", exchange="okx"
        )

        events = [
            {
                "type": "placed",
                "internal_id": "engine-order-1",
                "exchange_order_id": "exch-456",
                "symbol": "BTC/USDT",
                "side": "buy",
                "order_type": "market",
                "amount": "0.01",
                "price": None,
                "status": "submitted",
                "created_at": "2025-01-01T00:00:00+00:00",
            }
        ]

        with patch("squant.infra.database.get_session_context") as mock_ctx:
            mock_session = AsyncMock()
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            with (
                patch(
                    "squant.services.order.OrderRepository",
                    return_value=mock_order_repo,
                ),
                patch(
                    "squant.services.order.TradeRepository",
                    return_value=mock_trade_repo,
                ),
            ):
                await callback("run-123", events)

        mock_order_repo.create.assert_called_once()
        call_kwargs = mock_order_repo.create.call_args[1]
        assert call_kwargs["run_id"] == "run-123"
        assert call_kwargs["account_id"] == "acc-123"
        assert call_kwargs["exchange"] == "okx"
        assert call_kwargs["symbol"] == "BTC/USDT"
        assert call_kwargs["amount"] == Decimal("0.01")

    async def test_fill_event_creates_trade_and_updates_order(self):
        """A 'fill' event should create a Trade and update the Order."""
        from squant.services.live_trading import LiveTradingService

        mock_order = MagicMock()
        mock_order.id = "db-order-uuid-1"

        mock_order_repo = AsyncMock()
        mock_order_repo.create = AsyncMock(return_value=mock_order)
        mock_order_repo.update = AsyncMock()

        mock_trade_repo = AsyncMock()
        mock_trade_repo.create = AsyncMock()

        callback = LiveTradingService._create_order_persist_callback(
            account_id="acc-123", exchange="okx"
        )

        # First place, then fill
        events = [
            {
                "type": "placed",
                "internal_id": "engine-order-1",
                "exchange_order_id": "exch-456",
                "symbol": "BTC/USDT",
                "side": "buy",
                "order_type": "market",
                "amount": "0.01",
                "price": None,
                "status": "submitted",
                "created_at": "2025-01-01T00:00:00+00:00",
            },
            {
                "type": "fill",
                "internal_id": "engine-order-1",
                "fill_price": "50000",
                "fill_amount": "0.01",
                "fee": "0.005",
                "fee_currency": "USDT",
                "total_filled": "0.01",
                "avg_fill_price": "50000",
                "status": "filled",
                "timestamp": "2025-01-01T00:00:01+00:00",
            },
        ]

        with patch("squant.infra.database.get_session_context") as mock_ctx:
            mock_session = AsyncMock()
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            with (
                patch(
                    "squant.services.order.OrderRepository",
                    return_value=mock_order_repo,
                ),
                patch(
                    "squant.services.order.TradeRepository",
                    return_value=mock_trade_repo,
                ),
            ):
                await callback("run-123", events)

        # Trade created
        mock_trade_repo.create.assert_called_once()
        trade_kwargs = mock_trade_repo.create.call_args[1]
        assert trade_kwargs["order_id"] == "db-order-uuid-1"
        assert trade_kwargs["price"] == Decimal("50000")
        assert trade_kwargs["amount"] == Decimal("0.01")
        assert trade_kwargs["fee"] == Decimal("0.005")

        # Order updated
        mock_order_repo.update.assert_called_once()
        update_args = mock_order_repo.update.call_args
        assert update_args[0][0] == "db-order-uuid-1"
        assert update_args[1]["filled"] == Decimal("0.01")
        assert update_args[1]["status"] == OrderStatus.FILLED

    async def test_fill_without_placed_is_skipped(self):
        """A 'fill' event for unknown internal_id should be skipped (not crash)."""
        from squant.services.live_trading import LiveTradingService

        mock_order_repo = AsyncMock()
        mock_trade_repo = AsyncMock()

        callback = LiveTradingService._create_order_persist_callback(
            account_id="acc-123", exchange="okx"
        )

        events = [
            {
                "type": "fill",
                "internal_id": "unknown-order",
                "fill_price": "50000",
                "fill_amount": "0.01",
                "fee": "0.005",
                "fee_currency": "USDT",
                "total_filled": "0.01",
                "avg_fill_price": "50000",
                "status": "filled",
                "timestamp": "2025-01-01T00:00:01+00:00",
            },
        ]

        with patch("squant.infra.database.get_session_context") as mock_ctx:
            mock_session = AsyncMock()
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            with (
                patch(
                    "squant.services.order.OrderRepository",
                    return_value=mock_order_repo,
                ),
                patch(
                    "squant.services.order.TradeRepository",
                    return_value=mock_trade_repo,
                ),
            ):
                await callback("run-123", events)

        # No trade should be created
        mock_trade_repo.create.assert_not_called()

    async def test_callback_failure_does_not_propagate(self):
        """Individual event failure should not stop processing other events."""
        from squant.services.live_trading import LiveTradingService

        mock_order_1 = MagicMock()
        mock_order_1.id = "db-1"
        mock_order_2 = MagicMock()
        mock_order_2.id = "db-2"

        mock_order_repo = AsyncMock()
        # First create fails, second succeeds
        mock_order_repo.create = AsyncMock(
            side_effect=[Exception("DB error"), mock_order_2]
        )

        mock_trade_repo = AsyncMock()

        callback = LiveTradingService._create_order_persist_callback(
            account_id="acc-123", exchange="okx"
        )

        events = [
            {
                "type": "placed",
                "internal_id": "order-1",
                "exchange_order_id": "exch-1",
                "symbol": "BTC/USDT",
                "side": "buy",
                "order_type": "market",
                "amount": "0.01",
                "price": None,
                "status": "submitted",
                "created_at": "2025-01-01T00:00:00+00:00",
            },
            {
                "type": "placed",
                "internal_id": "order-2",
                "exchange_order_id": "exch-2",
                "symbol": "ETH/USDT",
                "side": "sell",
                "order_type": "limit",
                "amount": "0.1",
                "price": "3000",
                "status": "submitted",
                "created_at": "2025-01-01T00:00:01+00:00",
            },
        ]

        with patch("squant.infra.database.get_session_context") as mock_ctx:
            mock_session = AsyncMock()
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            with (
                patch(
                    "squant.services.order.OrderRepository",
                    return_value=mock_order_repo,
                ),
                patch(
                    "squant.services.order.TradeRepository",
                    return_value=mock_trade_repo,
                ),
            ):
                # Should not raise
                await callback("run-123", events)

        # Both creates attempted
        assert mock_order_repo.create.call_count == 2

    async def test_seed_map_links_fill_to_existing_db_order(self):
        """With seed_map, a fill for a pre-existing order should create a Trade."""
        from squant.services.live_trading import LiveTradingService

        mock_order_repo = AsyncMock()
        mock_order_repo.update = AsyncMock()

        mock_trade_repo = AsyncMock()
        mock_trade_repo.create = AsyncMock()

        # Seed map: engine internal_id → DB UUID (simulating resume scenario)
        seed_map = {"engine-order-1": "db-uuid-from-before-crash"}

        callback = LiveTradingService._create_order_persist_callback(
            account_id="acc-123",
            exchange="okx",
            seed_map=seed_map,
        )

        # Only a fill event — no "placed" event (order was placed before crash)
        events = [
            {
                "type": "fill",
                "internal_id": "engine-order-1",
                "fill_price": "50000",
                "fill_amount": "0.005",
                "fee": "0.003",
                "fee_currency": "USDT",
                "total_filled": "0.005",
                "avg_fill_price": "50000",
                "status": "partial",
                "timestamp": "2025-01-01T00:00:05+00:00",
            },
        ]

        with patch("squant.infra.database.get_session_context") as mock_ctx:
            mock_session = AsyncMock()
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            with (
                patch(
                    "squant.services.order.OrderRepository",
                    return_value=mock_order_repo,
                ),
                patch(
                    "squant.services.order.TradeRepository",
                    return_value=mock_trade_repo,
                ),
            ):
                await callback("run-123", events)

        # Trade should be created using the seeded DB order UUID
        mock_trade_repo.create.assert_called_once()
        trade_kwargs = mock_trade_repo.create.call_args[1]
        assert trade_kwargs["order_id"] == "db-uuid-from-before-crash"
        assert trade_kwargs["price"] == Decimal("50000")

        # Order should be updated
        mock_order_repo.update.assert_called_once()
        assert mock_order_repo.update.call_args[0][0] == "db-uuid-from-before-crash"
