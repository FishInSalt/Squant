"""Tests for watch_my_trades and reconnect handlers in CCXTStreamProvider."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from squant.infra.exchange.ccxt.provider import CCXTStreamProvider
from squant.infra.exchange.exceptions import ExchangeAuthenticationError


class TestWatchMyTrades:
    @pytest.fixture
    def provider(self):
        p = CCXTStreamProvider.__new__(CCXTStreamProvider)
        p._exchange = MagicMock()
        p._exchange_id = "okx"
        p._credentials = MagicMock()
        p._running = True
        p._connected = True
        p._subscription_tasks = {}
        p._handlers = []
        p._reconnect_handlers = []
        p._transformer = MagicMock()
        p._consecutive_errors = {}
        p._subscription_reconnect_count = {}
        p._reconnect_lock = asyncio.Lock()
        return p

    async def test_watch_my_trades_creates_task(self, provider):
        # Override _my_trades_loop to not actually run
        provider._my_trades_loop = AsyncMock()
        await provider.watch_my_trades("BTC/USDT")
        assert "my_trades:BTC/USDT" in provider._subscription_tasks

    async def test_watch_my_trades_requires_credentials(self, provider):
        provider._credentials = None
        with pytest.raises(ExchangeAuthenticationError):
            await provider.watch_my_trades("BTC/USDT")

    async def test_watch_my_trades_skips_duplicate(self, provider):
        mock_task = MagicMock()
        mock_task.done.return_value = False
        provider._subscription_tasks["my_trades:BTC/USDT"] = mock_task
        await provider.watch_my_trades("BTC/USDT")
        assert provider._subscription_tasks["my_trades:BTC/USDT"] is mock_task


class TestReconnectHandlers:
    @pytest.fixture
    def provider(self):
        p = CCXTStreamProvider.__new__(CCXTStreamProvider)
        p._reconnect_handlers = []
        return p

    def test_add_reconnect_handler(self, provider):
        handler = AsyncMock()
        provider.add_reconnect_handler(handler)
        assert handler in provider._reconnect_handlers

    def test_add_reconnect_handler_no_duplicate(self, provider):
        handler = AsyncMock()
        provider.add_reconnect_handler(handler)
        provider.add_reconnect_handler(handler)
        assert len(provider._reconnect_handlers) == 1

    def test_remove_reconnect_handler(self, provider):
        handler = AsyncMock()
        provider.add_reconnect_handler(handler)
        provider.remove_reconnect_handler(handler)
        assert handler not in provider._reconnect_handlers

    def test_remove_nonexistent_handler(self, provider):
        handler = AsyncMock()
        # Should not raise
        provider.remove_reconnect_handler(handler)
