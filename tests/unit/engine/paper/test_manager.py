"""Unit tests for paper trading session manager."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from squant.engine.paper.manager import SessionManager, get_session_manager
from squant.infra.exchange.okx.ws_types import WSCandle


@pytest.fixture
def session_manager():
    """Create a fresh session manager for testing."""
    return SessionManager()


@pytest.fixture
def mock_engine():
    """Create a mock paper trading engine."""
    engine = MagicMock()
    engine.run_id = uuid4()
    engine.symbol = "BTC/USDT"
    engine.timeframe = "1m"
    engine.is_running = True
    engine.process_candle = AsyncMock()
    engine.stop = AsyncMock()
    engine.get_state_snapshot = MagicMock(return_value={
        "run_id": str(engine.run_id),
        "symbol": "BTC/USDT",
        "timeframe": "1m",
        "is_running": True,
        "bar_count": 0,
        "cash": "10000",
        "equity": "10000",
    })
    return engine


class TestSessionRegistration:
    """Tests for session registration and unregistration."""

    @pytest.mark.asyncio
    async def test_register_session(self, session_manager, mock_engine):
        """Test registering a session."""
        await session_manager.register(mock_engine)

        assert session_manager.session_count == 1
        assert session_manager.get(mock_engine.run_id) == mock_engine

    @pytest.mark.asyncio
    async def test_register_duplicate_warns(self, session_manager, mock_engine):
        """Test that registering duplicate session logs warning."""
        await session_manager.register(mock_engine)
        await session_manager.register(mock_engine)  # Should warn

        assert session_manager.session_count == 1

    @pytest.mark.asyncio
    async def test_unregister_session(self, session_manager, mock_engine):
        """Test unregistering a session."""
        await session_manager.register(mock_engine)
        await session_manager.unregister(mock_engine.run_id)

        assert session_manager.session_count == 0
        assert session_manager.get(mock_engine.run_id) is None

    @pytest.mark.asyncio
    async def test_unregister_nonexistent(self, session_manager):
        """Test unregistering non-existent session logs warning."""
        await session_manager.unregister(uuid4())  # Should warn but not fail

    def test_get_nonexistent_session(self, session_manager):
        """Test getting non-existent session returns None."""
        assert session_manager.get(uuid4()) is None


class TestSubscriptionTracking:
    """Tests for subscription tracking."""

    @pytest.mark.asyncio
    async def test_subscription_created(self, session_manager, mock_engine):
        """Test that subscription is tracked on registration."""
        await session_manager.register(mock_engine)

        subscribed = session_manager.get_subscribed_symbols()
        assert ("BTC/USDT", "1m") in subscribed

    @pytest.mark.asyncio
    async def test_subscription_removed(self, session_manager, mock_engine):
        """Test that subscription is removed on unregistration."""
        await session_manager.register(mock_engine)
        await session_manager.unregister(mock_engine.run_id)

        subscribed = session_manager.get_subscribed_symbols()
        assert ("BTC/USDT", "1m") not in subscribed

    @pytest.mark.asyncio
    async def test_multiple_sessions_same_symbol(self, session_manager):
        """Test multiple sessions for the same symbol."""
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

        assert session_manager.session_count == 2

        # Unregister one, subscription should remain
        await session_manager.unregister(engine1.run_id)
        subscribed = session_manager.get_subscribed_symbols()
        assert ("BTC/USDT", "1m") in subscribed

        # Unregister the other, subscription should be removed
        await session_manager.unregister(engine2.run_id)
        subscribed = session_manager.get_subscribed_symbols()
        assert ("BTC/USDT", "1m") not in subscribed


class TestCandleDispatch:
    """Tests for candle dispatch functionality."""

    @pytest.fixture
    def sample_candle(self):
        """Create a sample candle."""
        return WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            open=Decimal("45000"),
            high=Decimal("46000"),
            low=Decimal("44000"),
            close=Decimal("45500"),
            volume=Decimal("100"),
            is_closed=True,
        )

    @pytest.mark.asyncio
    async def test_dispatch_to_subscribed_engine(
        self, session_manager, mock_engine, sample_candle
    ):
        """Test that candles are dispatched to subscribed engines."""
        await session_manager.register(mock_engine)
        await session_manager.dispatch_candle(sample_candle)

        mock_engine.process_candle.assert_called_once_with(sample_candle)

    @pytest.mark.asyncio
    async def test_no_dispatch_to_unsubscribed(
        self, session_manager, mock_engine, sample_candle
    ):
        """Test that candles are not dispatched to unsubscribed symbols."""
        mock_engine.symbol = "ETH/USDT"
        await session_manager.register(mock_engine)

        sample_candle.symbol = "BTC/USDT"  # Different symbol
        await session_manager.dispatch_candle(sample_candle)

        mock_engine.process_candle.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_to_multiple_engines(self, session_manager, sample_candle):
        """Test dispatching to multiple engines with same subscription."""
        engine1 = MagicMock()
        engine1.run_id = uuid4()
        engine1.symbol = "BTC/USDT"
        engine1.timeframe = "1m"
        engine1.is_running = True
        engine1.process_candle = AsyncMock()

        engine2 = MagicMock()
        engine2.run_id = uuid4()
        engine2.symbol = "BTC/USDT"
        engine2.timeframe = "1m"
        engine2.is_running = True
        engine2.process_candle = AsyncMock()

        await session_manager.register(engine1)
        await session_manager.register(engine2)
        await session_manager.dispatch_candle(sample_candle)

        engine1.process_candle.assert_called_once_with(sample_candle)
        engine2.process_candle.assert_called_once_with(sample_candle)

    @pytest.mark.asyncio
    async def test_no_dispatch_to_stopped_engine(
        self, session_manager, mock_engine, sample_candle
    ):
        """Test that candles are not dispatched to stopped engines."""
        mock_engine.is_running = False
        await session_manager.register(mock_engine)
        await session_manager.dispatch_candle(sample_candle)

        mock_engine.process_candle.assert_not_called()


class TestStopAll:
    """Tests for stop_all functionality."""

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
            call_args = engine.stop.call_args
            assert "test shutdown" in call_args.kwargs.get("error", "")


class TestListSessions:
    """Tests for listing sessions."""

    @pytest.mark.asyncio
    async def test_list_sessions(self, session_manager):
        """Test listing all sessions."""
        engine1 = MagicMock()
        engine1.run_id = uuid4()
        engine1.symbol = "BTC/USDT"
        engine1.timeframe = "1m"
        engine1.get_state_snapshot = MagicMock(return_value={
            "run_id": str(engine1.run_id),
            "symbol": "BTC/USDT",
        })

        engine2 = MagicMock()
        engine2.run_id = uuid4()
        engine2.symbol = "ETH/USDT"
        engine2.timeframe = "1m"
        engine2.get_state_snapshot = MagicMock(return_value={
            "run_id": str(engine2.run_id),
            "symbol": "ETH/USDT",
        })

        await session_manager.register(engine1)
        await session_manager.register(engine2)

        sessions = session_manager.list_sessions()

        assert len(sessions) == 2
        symbols = [s["symbol"] for s in sessions]
        assert "BTC/USDT" in symbols
        assert "ETH/USDT" in symbols


class TestSingleton:
    """Tests for singleton behavior."""

    def test_get_session_manager_singleton(self):
        """Test that get_session_manager returns the same instance."""
        manager1 = get_session_manager()
        manager2 = get_session_manager()

        assert manager1 is manager2
