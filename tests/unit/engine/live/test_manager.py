"""Unit tests for live session manager."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from squant.engine.live.manager import LiveSessionManager, get_live_session_manager
from squant.infra.exchange.okx.ws_types import WSCandle, WSOrderUpdate
from squant.models.enums import OrderStatus


@pytest.fixture
def session_manager():
    """Create a fresh session manager for testing."""
    return LiveSessionManager()


@pytest.fixture
def mock_engine():
    """Create a mock live trading engine."""
    engine = MagicMock()
    engine.run_id = uuid4()
    engine.symbol = "BTC/USDT"
    engine.timeframe = "1m"
    engine.is_running = True
    engine.is_healthy = MagicMock(return_value=True)
    engine.get_state_snapshot = MagicMock(
        return_value={
            "run_id": str(engine.run_id),
            "symbol": "BTC/USDT",
            "timeframe": "1m",
            "is_running": True,
        }
    )
    engine.should_persist_snapshots = MagicMock(return_value=False)
    engine.process_candle = AsyncMock()
    engine.on_order_update = MagicMock()
    engine.stop = AsyncMock()
    return engine


class TestSessionManagerRegistration:
    """Tests for session registration and unregistration."""

    @pytest.mark.asyncio
    async def test_register_engine(self, session_manager, mock_engine):
        """Test registering a live trading engine."""
        await session_manager.register(mock_engine)

        assert session_manager.session_count == 1
        assert session_manager.get(mock_engine.run_id) is mock_engine

    @pytest.mark.asyncio
    async def test_register_multiple_engines(self, session_manager):
        """Test registering multiple engines."""
        engines = []
        for i in range(3):
            engine = MagicMock()
            engine.run_id = uuid4()
            engine.symbol = f"COIN{i}/USDT"
            engine.timeframe = "1m"
            engines.append(engine)
            await session_manager.register(engine)

        assert session_manager.session_count == 3

    @pytest.mark.asyncio
    async def test_register_duplicate_warns(self, session_manager, mock_engine):
        """Test that registering duplicate engine logs warning."""
        await session_manager.register(mock_engine)
        await session_manager.register(mock_engine)  # Should warn

        assert session_manager.session_count == 1

    @pytest.mark.asyncio
    async def test_unregister_engine(self, session_manager, mock_engine):
        """Test unregistering a live trading engine."""
        await session_manager.register(mock_engine)
        await session_manager.unregister(mock_engine.run_id)

        assert session_manager.session_count == 0
        assert session_manager.get(mock_engine.run_id) is None

    @pytest.mark.asyncio
    async def test_unregister_unknown_engine(self, session_manager):
        """Test unregistering an unknown engine."""
        unknown_id = uuid4()
        await session_manager.unregister(unknown_id)  # Should not raise

        assert session_manager.session_count == 0


class TestSubscriptionTracking:
    """Tests for subscription tracking."""

    @pytest.mark.asyncio
    async def test_candle_subscription_tracked(self, session_manager, mock_engine):
        """Test that candle subscriptions are tracked."""
        await session_manager.register(mock_engine)

        subscriptions = session_manager.get_subscribed_symbols()
        assert ("BTC/USDT", "1m") in subscriptions

    @pytest.mark.asyncio
    async def test_order_subscription_tracked(self, session_manager, mock_engine):
        """Test that order subscriptions are tracked."""
        await session_manager.register(mock_engine)

        symbols = session_manager.get_order_subscribed_symbols()
        assert "BTC/USDT" in symbols

    @pytest.mark.asyncio
    async def test_subscriptions_removed_on_unregister(self, session_manager, mock_engine):
        """Test that subscriptions are removed when engine unregisters."""
        await session_manager.register(mock_engine)
        await session_manager.unregister(mock_engine.run_id)

        assert session_manager.get_subscribed_symbols() == []
        assert session_manager.get_order_subscribed_symbols() == []

    @pytest.mark.asyncio
    async def test_multiple_engines_same_subscription(self, session_manager):
        """Test multiple engines on same symbol/timeframe."""
        engine1 = MagicMock()
        engine1.run_id = uuid4()
        engine1.symbol = "BTC/USDT"
        engine1.timeframe = "1m"

        engine2 = MagicMock()
        engine2.run_id = uuid4()
        engine2.symbol = "BTC/USDT"
        engine2.timeframe = "1m"

        await session_manager.register(engine1)
        await session_manager.register(engine2)

        # Only one subscription entry for the same symbol/timeframe
        subscriptions = session_manager.get_subscribed_symbols()
        assert len(subscriptions) == 1

        # Unregister one, subscription should remain
        await session_manager.unregister(engine1.run_id)
        assert len(session_manager.get_subscribed_symbols()) == 1

        # Unregister both, subscription should be removed
        await session_manager.unregister(engine2.run_id)
        assert len(session_manager.get_subscribed_symbols()) == 0


class TestCandleDispatch:
    """Tests for candle dispatch."""

    @pytest.fixture
    def candle(self):
        """Create a test candle."""
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
    async def test_dispatch_candle_to_subscribed_engine(self, session_manager, mock_engine, candle):
        """Test dispatching candle to subscribed engine."""
        await session_manager.register(mock_engine)
        await session_manager.dispatch_candle(candle)

        mock_engine.process_candle.assert_called_once_with(candle)

    @pytest.mark.asyncio
    async def test_dispatch_candle_no_subscribers(self, session_manager, candle):
        """Test dispatching candle with no subscribers."""
        await session_manager.dispatch_candle(candle)
        # Should not raise

    @pytest.mark.asyncio
    async def test_dispatch_candle_wrong_symbol(self, session_manager, mock_engine, candle):
        """Test dispatching candle for non-subscribed symbol."""
        await session_manager.register(mock_engine)

        candle.symbol = "ETH/USDT"
        await session_manager.dispatch_candle(candle)

        mock_engine.process_candle.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_candle_wrong_timeframe(self, session_manager, mock_engine, candle):
        """Test dispatching candle for non-subscribed timeframe."""
        await session_manager.register(mock_engine)

        candle.timeframe = "5m"
        await session_manager.dispatch_candle(candle)

        mock_engine.process_candle.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_candle_to_multiple_engines(self, session_manager, candle):
        """Test dispatching candle to multiple subscribed engines."""
        engines = []
        for _ in range(3):
            engine = MagicMock()
            engine.run_id = uuid4()
            engine.symbol = "BTC/USDT"
            engine.timeframe = "1m"
            engine.is_running = True
            engine.process_candle = AsyncMock()
            engines.append(engine)
            await session_manager.register(engine)

        await session_manager.dispatch_candle(candle)

        for engine in engines:
            engine.process_candle.assert_called_once_with(candle)

    @pytest.mark.asyncio
    async def test_dispatch_candle_skips_stopped_engine(self, session_manager, mock_engine, candle):
        """Test that candles are not dispatched to stopped engines."""
        mock_engine.is_running = False
        await session_manager.register(mock_engine)
        await session_manager.dispatch_candle(candle)

        mock_engine.process_candle.assert_not_called()


class TestOrderUpdateDispatch:
    """Tests for order update dispatch."""

    @pytest.fixture
    def order_update(self):
        """Create a test order update."""
        return WSOrderUpdate(
            order_id="exchange-123",
            client_order_id="internal-123",
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            status=OrderStatus.FILLED,
            size=Decimal("0.1"),
            filled_size=Decimal("0.1"),
            avg_price=Decimal("45000"),
        )

    def test_dispatch_order_update(self, session_manager, mock_engine, order_update):
        """Test dispatching order update to subscribed engine."""
        # Register synchronously (for this test)
        session_manager._sessions[mock_engine.run_id] = mock_engine
        session_manager._order_subscriptions["BTC/USDT"] = {mock_engine.run_id}

        session_manager.dispatch_order_update(order_update)

        mock_engine.on_order_update.assert_called_once_with(order_update)

    def test_dispatch_order_update_no_subscribers(self, session_manager, order_update):
        """Test dispatching order update with no subscribers."""
        session_manager.dispatch_order_update(order_update)
        # Should not raise

    def test_dispatch_order_update_wrong_symbol(self, session_manager, mock_engine, order_update):
        """Test dispatching order update for non-subscribed symbol."""
        session_manager._sessions[mock_engine.run_id] = mock_engine
        session_manager._order_subscriptions["BTC/USDT"] = {mock_engine.run_id}

        order_update.symbol = "ETH/USDT"
        session_manager.dispatch_order_update(order_update)

        mock_engine.on_order_update.assert_not_called()


class TestStopAll:
    """Tests for stop all sessions."""

    @pytest.mark.asyncio
    async def test_stop_all_sessions(self, session_manager):
        """Test stopping all sessions."""
        engines = []
        for _ in range(3):
            engine = MagicMock()
            engine.run_id = uuid4()
            engine.symbol = "BTC/USDT"
            engine.timeframe = "1m"
            engine.is_running = True
            engine.stop = AsyncMock()
            engines.append(engine)
            await session_manager.register(engine)

        await session_manager.stop_all(reason="test shutdown")

        for engine in engines:
            engine.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_all_with_stopped_engines(self, session_manager):
        """Test stop_all skips already stopped engines."""
        engine = MagicMock()
        engine.run_id = uuid4()
        engine.symbol = "BTC/USDT"
        engine.timeframe = "1m"
        engine.is_running = False  # Already stopped
        engine.stop = AsyncMock()
        await session_manager.register(engine)

        await session_manager.stop_all(reason="test")

        engine.stop.assert_not_called()


class TestHealthCheck:
    """Tests for health check functionality."""

    @pytest.mark.asyncio
    async def test_check_health_all_healthy(self, session_manager, mock_engine):
        """Test health check with all healthy sessions."""
        mock_engine.is_healthy.return_value = True
        await session_manager.register(mock_engine)

        unhealthy = await session_manager.check_health(timeout_seconds=300)

        assert unhealthy == []

    @pytest.mark.asyncio
    async def test_check_health_unhealthy_session(self, session_manager, mock_engine):
        """Test health check detects unhealthy sessions."""
        mock_engine.is_healthy.return_value = False
        await session_manager.register(mock_engine)

        unhealthy = await session_manager.check_health(timeout_seconds=300)

        assert mock_engine.run_id in unhealthy

    @pytest.mark.asyncio
    async def test_cleanup_stale_sessions(self, session_manager, mock_engine):
        """Test cleanup of stale sessions."""
        mock_engine.is_healthy.return_value = False
        await session_manager.register(mock_engine)

        cleaned_ids, keys_to_unsub, _ = await session_manager.cleanup_stale_sessions(
            timeout_seconds=300
        )

        assert cleaned_ids == [mock_engine.run_id]
        assert keys_to_unsub == [(mock_engine.symbol, mock_engine.timeframe)]
        mock_engine.stop.assert_called_once()
        assert session_manager.session_count == 0


class TestListSessions:
    """Tests for listing sessions."""

    @pytest.mark.asyncio
    async def test_list_sessions(self, session_manager, mock_engine):
        """Test listing all sessions."""
        await session_manager.register(mock_engine)

        sessions = session_manager.list_sessions()

        assert len(sessions) == 1
        assert sessions[0]["run_id"] == str(mock_engine.run_id)

    @pytest.mark.asyncio
    async def test_list_sessions_empty(self, session_manager):
        """Test listing sessions when empty."""
        sessions = session_manager.list_sessions()

        assert sessions == []


class TestPersistenceTracking:
    """Tests for persistence tracking."""

    @pytest.mark.asyncio
    async def test_get_sessions_needing_persistence(self, session_manager, mock_engine):
        """Test getting sessions that need persistence."""
        mock_engine.should_persist_snapshots.return_value = True
        await session_manager.register(mock_engine)

        needing = session_manager.get_sessions_needing_persistence()

        assert mock_engine.run_id in needing

    @pytest.mark.asyncio
    async def test_get_sessions_no_persistence_needed(self, session_manager, mock_engine):
        """Test when no sessions need persistence."""
        mock_engine.should_persist_snapshots.return_value = False
        await session_manager.register(mock_engine)

        needing = session_manager.get_sessions_needing_persistence()

        assert needing == []


class TestGlobalInstance:
    """Tests for global session manager instance."""

    def test_get_live_session_manager_singleton(self):
        """Test that get_live_session_manager returns singleton."""
        # Reset the global instance for testing
        import squant.engine.live.manager as manager_module

        manager_module._live_session_manager = None

        manager1 = get_live_session_manager()
        manager2 = get_live_session_manager()

        assert manager1 is manager2

        # Clean up
        manager_module._live_session_manager = None
