"""Unit tests for StreamManager."""

import asyncio
import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from squant.websocket.manager import StreamManager


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    settings = MagicMock()
    settings.default_exchange = "okx"
    settings.okx_api_key = MagicMock()
    settings.okx_api_key.get_secret_value.return_value = "test-key"
    settings.okx_api_secret = MagicMock()
    settings.okx_api_secret.get_secret_value.return_value = "test-secret"
    settings.okx_passphrase = MagicMock()
    settings.okx_passphrase.get_secret_value.return_value = "test-passphrase"
    settings.binance_api_key = None
    settings.binance_api_secret = None
    settings.bybit_api_key = None
    settings.bybit_api_secret = None
    return settings


@pytest.fixture
def mock_redis():
    """Create mock Redis client."""
    redis = AsyncMock()
    redis.publish = AsyncMock(return_value=1)
    redis.pipeline = MagicMock()
    pipeline = AsyncMock()
    pipeline.publish = MagicMock(return_value=pipeline)
    pipeline.execute = AsyncMock(return_value=[1, 1, 1])
    redis.pipeline.return_value = pipeline
    return redis


@pytest.fixture
def mock_ccxt_provider():
    """Create mock CCXT stream provider."""
    provider = AsyncMock()
    provider.exchange_id = "okx"
    provider.is_connected = True
    provider.is_healthy = MagicMock(return_value=True)
    provider.connect = AsyncMock()
    provider.close = AsyncMock()
    provider.watch_ticker = AsyncMock()
    provider.watch_ohlcv = AsyncMock()
    provider.watch_trades = AsyncMock()
    provider.watch_order_book = AsyncMock()
    provider.unwatch = AsyncMock()
    provider.add_handler = MagicMock()
    return provider


class TestStreamManagerInit:
    """Test StreamManager initialization."""

    def test_init_defaults(self):
        """Test default initialization values."""
        with patch("squant.websocket.manager.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MagicMock(
                default_exchange="okx",
            )
            manager = StreamManager()

            assert manager._running is False
            assert manager._ccxt_provider is None
            assert len(manager._ticker_subscriptions) == 0
            assert len(manager._candle_subscriptions) == 0
            assert len(manager._trade_subscriptions) == 0
            assert len(manager._orderbook_subscriptions) == 0

    def test_is_running_property(self):
        """Test is_running property."""
        with patch("squant.websocket.manager.get_settings") as mock_get_settings:
            mock_get_settings.return_value = MagicMock(default_exchange="okx")
            manager = StreamManager()

            assert manager.is_running is False
            manager._running = True
            assert manager.is_running is True


class TestStreamManagerHealth:
    """Test StreamManager health check functionality."""

    def test_is_healthy_when_not_running(self, mock_settings):
        """Test is_healthy returns False when not running."""
        with patch("squant.websocket.manager.get_settings", return_value=mock_settings):
            manager = StreamManager()
            assert manager.is_healthy is False

    def test_is_healthy_with_ccxt_provider(self, mock_settings, mock_ccxt_provider):
        """Test is_healthy with CCXT provider."""
        with patch("squant.websocket.manager.get_settings", return_value=mock_settings):
            manager = StreamManager()
            manager._running = True
            manager._ccxt_provider = mock_ccxt_provider

            assert manager.is_healthy is True

            # Test when provider reports unhealthy
            mock_ccxt_provider.is_healthy.return_value = False
            assert manager.is_healthy is False



class TestStreamManagerStart:
    """Test StreamManager start functionality."""

    @pytest.mark.asyncio
    async def test_start_ccxt_provider(self, mock_settings, mock_redis, mock_ccxt_provider):
        """Test starting with CCXT provider."""
        with (
            patch("squant.websocket.manager.get_settings", return_value=mock_settings),
            patch("squant.websocket.manager.get_redis_client", return_value=mock_redis),
            patch(
                "squant.websocket.manager.CCXTStreamProvider",
                return_value=mock_ccxt_provider,
            ),
        ):
            manager = StreamManager()

            await manager.start()

            assert manager._running is True
            assert manager._ccxt_provider is not None
            mock_ccxt_provider.connect.assert_called_once()
            mock_ccxt_provider.add_handler.assert_called_once()

            # Cleanup
            await manager.stop()

    @pytest.mark.asyncio
    async def test_start_already_running(self, mock_settings, mock_redis, mock_ccxt_provider):
        """Test start when already running does nothing."""
        with (
            patch("squant.websocket.manager.get_settings", return_value=mock_settings),
            patch("squant.websocket.manager.get_redis_client", return_value=mock_redis),
            patch(
                "squant.websocket.manager.CCXTStreamProvider",
                return_value=mock_ccxt_provider,
            ),
        ):
            manager = StreamManager()
            manager._running = True

            await manager.start()

            # Should not create a new provider
            mock_ccxt_provider.connect.assert_not_called()

    @pytest.mark.asyncio
    async def test_try_start_success(self, mock_settings, mock_redis, mock_ccxt_provider):
        """Test try_start returns True on success."""
        with (
            patch("squant.websocket.manager.get_settings", return_value=mock_settings),
            patch("squant.websocket.manager.get_redis_client", return_value=mock_redis),
            patch(
                "squant.websocket.manager.CCXTStreamProvider",
                return_value=mock_ccxt_provider,
            ),
        ):
            manager = StreamManager()

            result = await manager.try_start()

            assert result is True
            assert manager._running is True

            # Cleanup
            await manager.stop()

    @pytest.mark.asyncio
    async def test_try_start_failure(self, mock_settings, mock_redis):
        """Test try_start returns False on failure."""
        mock_provider = AsyncMock()
        mock_provider.connect = AsyncMock(side_effect=Exception("Connection failed"))

        with (
            patch("squant.websocket.manager.get_settings", return_value=mock_settings),
            patch("squant.websocket.manager.get_redis_client", return_value=mock_redis),
            patch(
                "squant.websocket.manager.CCXTStreamProvider",
                return_value=mock_provider,
            ),
        ):
            manager = StreamManager()

            result = await manager.try_start()

            assert result is False
            assert manager._running is False


class TestStreamManagerStop:
    """Test StreamManager stop functionality."""

    @pytest.mark.asyncio
    async def test_stop_cleans_up_resources(self, mock_settings, mock_redis, mock_ccxt_provider):
        """Test stop properly cleans up all resources."""
        with (
            patch("squant.websocket.manager.get_settings", return_value=mock_settings),
            patch("squant.websocket.manager.get_redis_client", return_value=mock_redis),
            patch(
                "squant.websocket.manager.CCXTStreamProvider",
                return_value=mock_ccxt_provider,
            ),
        ):
            manager = StreamManager()
            await manager.start()

            await manager.stop()

            assert manager._running is False
            assert manager._ccxt_provider is None
            mock_ccxt_provider.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self, mock_settings):
        """Test stop when not running does nothing."""
        with patch("squant.websocket.manager.get_settings", return_value=mock_settings):
            manager = StreamManager()

            # Should not raise
            await manager.stop()

            assert manager._running is False


class TestStreamManagerSubscriptions:
    """Test StreamManager subscription functionality."""

    @pytest.mark.asyncio
    async def test_subscribe_ticker(self, mock_settings, mock_redis, mock_ccxt_provider):
        """Test subscribing to ticker updates."""
        with (
            patch("squant.websocket.manager.get_settings", return_value=mock_settings),
            patch("squant.websocket.manager.get_redis_client", return_value=mock_redis),
            patch(
                "squant.websocket.manager.CCXTStreamProvider",
                return_value=mock_ccxt_provider,
            ),
        ):
            manager = StreamManager()
            await manager.start()

            await manager.subscribe_ticker("BTC/USDT")

            mock_ccxt_provider.watch_ticker.assert_called_once_with("BTC/USDT")
            assert "BTC/USDT" in manager._ticker_subscriptions

            # Cleanup
            await manager.stop()

    @pytest.mark.asyncio
    async def test_subscribe_ticker_already_subscribed(
        self, mock_settings, mock_redis, mock_ccxt_provider
    ):
        """Test subscribing to already subscribed ticker does nothing."""
        with (
            patch("squant.websocket.manager.get_settings", return_value=mock_settings),
            patch("squant.websocket.manager.get_redis_client", return_value=mock_redis),
            patch(
                "squant.websocket.manager.CCXTStreamProvider",
                return_value=mock_ccxt_provider,
            ),
        ):
            manager = StreamManager()
            await manager.start()

            await manager.subscribe_ticker("BTC/USDT")
            await manager.subscribe_ticker("BTC/USDT")  # Second call

            # Should only be called once
            assert mock_ccxt_provider.watch_ticker.call_count == 1

            # Cleanup
            await manager.stop()

    @pytest.mark.asyncio
    async def test_subscribe_ticker_not_started(self, mock_settings):
        """Test subscribing without starting raises error."""
        with patch("squant.websocket.manager.get_settings", return_value=mock_settings):
            manager = StreamManager()

            with pytest.raises(RuntimeError, match="not started"):
                await manager.subscribe_ticker("BTC/USDT")

    @pytest.mark.asyncio
    async def test_unsubscribe_ticker(self, mock_settings, mock_redis, mock_ccxt_provider):
        """Test unsubscribing from ticker updates."""
        with (
            patch("squant.websocket.manager.get_settings", return_value=mock_settings),
            patch("squant.websocket.manager.get_redis_client", return_value=mock_redis),
            patch(
                "squant.websocket.manager.CCXTStreamProvider",
                return_value=mock_ccxt_provider,
            ),
        ):
            manager = StreamManager()
            await manager.start()

            await manager.subscribe_ticker("BTC/USDT")
            await manager.unsubscribe_ticker("BTC/USDT")

            mock_ccxt_provider.unwatch.assert_called_once_with("ticker:BTC/USDT")
            assert "BTC/USDT" not in manager._ticker_subscriptions

            # Cleanup
            await manager.stop()

    @pytest.mark.asyncio
    async def test_subscribe_candles(self, mock_settings, mock_redis, mock_ccxt_provider):
        """Test subscribing to candlestick updates."""
        with (
            patch("squant.websocket.manager.get_settings", return_value=mock_settings),
            patch("squant.websocket.manager.get_redis_client", return_value=mock_redis),
            patch(
                "squant.websocket.manager.CCXTStreamProvider",
                return_value=mock_ccxt_provider,
            ),
        ):
            manager = StreamManager()
            await manager.start()

            await manager.subscribe_candles("BTC/USDT", "1h")

            mock_ccxt_provider.watch_ohlcv.assert_called_once_with("BTC/USDT", "1h")
            assert ("BTC/USDT", "1h") in manager._candle_subscriptions

            # Cleanup
            await manager.stop()

    @pytest.mark.asyncio
    async def test_subscribe_candles_already_subscribed(
        self, mock_settings, mock_redis, mock_ccxt_provider
    ):
        """Test subscribing to already subscribed candles does nothing."""
        with (
            patch("squant.websocket.manager.get_settings", return_value=mock_settings),
            patch("squant.websocket.manager.get_redis_client", return_value=mock_redis),
            patch(
                "squant.websocket.manager.CCXTStreamProvider",
                return_value=mock_ccxt_provider,
            ),
        ):
            manager = StreamManager()
            await manager.start()

            await manager.subscribe_candles("BTC/USDT", "1h")
            await manager.subscribe_candles("BTC/USDT", "1h")  # Second call

            # Should only be called once
            assert mock_ccxt_provider.watch_ohlcv.call_count == 1

            # Cleanup
            await manager.stop()

    @pytest.mark.asyncio
    async def test_unsubscribe_candles(self, mock_settings, mock_redis, mock_ccxt_provider):
        """Test unsubscribing from candlestick updates."""
        with (
            patch("squant.websocket.manager.get_settings", return_value=mock_settings),
            patch("squant.websocket.manager.get_redis_client", return_value=mock_redis),
            patch(
                "squant.websocket.manager.CCXTStreamProvider",
                return_value=mock_ccxt_provider,
            ),
        ):
            manager = StreamManager()
            await manager.start()

            await manager.subscribe_candles("BTC/USDT", "1h")
            await manager.unsubscribe_candles("BTC/USDT", "1h")

            mock_ccxt_provider.unwatch.assert_called_once_with("ohlcv:BTC/USDT:1h")
            assert ("BTC/USDT", "1h") not in manager._candle_subscriptions

            # Cleanup
            await manager.stop()

    @pytest.mark.asyncio
    async def test_subscribe_trades(self, mock_settings, mock_redis, mock_ccxt_provider):
        """Test subscribing to trade updates."""
        with (
            patch("squant.websocket.manager.get_settings", return_value=mock_settings),
            patch("squant.websocket.manager.get_redis_client", return_value=mock_redis),
            patch(
                "squant.websocket.manager.CCXTStreamProvider",
                return_value=mock_ccxt_provider,
            ),
        ):
            manager = StreamManager()
            await manager.start()

            await manager.subscribe_trades("BTC/USDT")

            mock_ccxt_provider.watch_trades.assert_called_once_with("BTC/USDT")
            assert "BTC/USDT" in manager._trade_subscriptions

            # Cleanup
            await manager.stop()

    @pytest.mark.asyncio
    async def test_unsubscribe_trades(self, mock_settings, mock_redis, mock_ccxt_provider):
        """Test unsubscribing from trade updates."""
        with (
            patch("squant.websocket.manager.get_settings", return_value=mock_settings),
            patch("squant.websocket.manager.get_redis_client", return_value=mock_redis),
            patch(
                "squant.websocket.manager.CCXTStreamProvider",
                return_value=mock_ccxt_provider,
            ),
        ):
            manager = StreamManager()
            await manager.start()

            await manager.subscribe_trades("BTC/USDT")
            await manager.unsubscribe_trades("BTC/USDT")

            mock_ccxt_provider.unwatch.assert_called_once_with("trades:BTC/USDT")
            assert "BTC/USDT" not in manager._trade_subscriptions

            # Cleanup
            await manager.stop()

    @pytest.mark.asyncio
    async def test_subscribe_orderbook(self, mock_settings, mock_redis, mock_ccxt_provider):
        """Test subscribing to orderbook updates."""
        with (
            patch("squant.websocket.manager.get_settings", return_value=mock_settings),
            patch("squant.websocket.manager.get_redis_client", return_value=mock_redis),
            patch(
                "squant.websocket.manager.CCXTStreamProvider",
                return_value=mock_ccxt_provider,
            ),
        ):
            manager = StreamManager()
            await manager.start()

            await manager.subscribe_orderbook("BTC/USDT")

            mock_ccxt_provider.watch_order_book.assert_called_once_with("BTC/USDT", limit=5)
            assert "BTC/USDT" in manager._orderbook_subscriptions

            # Cleanup
            await manager.stop()


class TestStreamManagerExchangeSwitching:
    """Test StreamManager exchange switching functionality."""

    @pytest.mark.asyncio
    async def test_switch_exchange(self, mock_settings, mock_redis, mock_ccxt_provider):
        """Test switching exchanges preserves subscriptions."""
        new_provider = AsyncMock()
        new_provider.exchange_id = "binance"
        new_provider.is_connected = True
        new_provider.connect = AsyncMock()
        new_provider.close = AsyncMock()
        new_provider.watch_ticker = AsyncMock()
        new_provider.add_handler = MagicMock()

        call_count = 0

        def create_provider(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_ccxt_provider
            return new_provider

        with (
            patch("squant.websocket.manager.get_settings", return_value=mock_settings),
            patch("squant.websocket.manager.get_redis_client", return_value=mock_redis),
            patch(
                "squant.websocket.manager.CCXTStreamProvider",
                side_effect=create_provider,
            ),
        ):
            manager = StreamManager()
            await manager.start()

            # Subscribe to a ticker
            await manager.subscribe_ticker("BTC/USDT")

            # Switch exchange
            await manager.switch_exchange("binance")

            # Verify old provider was closed
            mock_ccxt_provider.close.assert_called_once()

            # Verify new provider was connected
            new_provider.connect.assert_called_once()

            # Verify subscriptions were restored
            new_provider.watch_ticker.assert_called_once_with("BTC/USDT")

            # Cleanup
            await manager.stop()

    @pytest.mark.asyncio
    async def test_switch_exchange_same_exchange(
        self, mock_settings, mock_redis, mock_ccxt_provider
    ):
        """Test switching to same exchange does nothing."""
        with (
            patch("squant.websocket.manager.get_settings", return_value=mock_settings),
            patch("squant.websocket.manager.get_redis_client", return_value=mock_redis),
            patch(
                "squant.websocket.manager.CCXTStreamProvider",
                return_value=mock_ccxt_provider,
            ),
        ):
            manager = StreamManager()
            await manager.start()

            # Try to switch to the same exchange
            await manager.switch_exchange("okx")

            # Provider should not be closed/reconnected
            mock_ccxt_provider.close.assert_not_called()

            # Cleanup
            await manager.stop()

    @pytest.mark.asyncio
    async def test_switch_exchange_not_running(self, mock_settings):
        """Test switching exchange when not running does nothing."""
        with patch("squant.websocket.manager.get_settings", return_value=mock_settings):
            manager = StreamManager()

            # Should not raise
            await manager.switch_exchange("binance")


class TestStreamManagerSymbolNormalization:
    """Test StreamManager symbol normalization."""

    def test_normalize_symbol_with_dash(self, mock_settings):
        """Test normalizing symbol with dash separator."""
        with patch("squant.websocket.manager.get_settings", return_value=mock_settings):
            manager = StreamManager()

            result = manager._normalize_symbol("BTC-USDT")
            assert result == "BTC/USDT"

    def test_normalize_symbol_with_slash(self, mock_settings):
        """Test normalizing symbol with slash separator."""
        with patch("squant.websocket.manager.get_settings", return_value=mock_settings):
            manager = StreamManager()

            result = manager._normalize_symbol("BTC/USDT")
            assert result == "BTC/USDT"

    def test_normalize_symbol_lowercase(self, mock_settings):
        """Test normalizing lowercase symbol (keeps case as-is)."""
        with patch("squant.websocket.manager.get_settings", return_value=mock_settings):
            manager = StreamManager()

            # _normalize_symbol only converts "-" to "/", doesn't change case
            result = manager._normalize_symbol("btc/usdt")
            assert result == "btc/usdt"


class TestStreamManagerCredentials:
    """Test StreamManager credentials handling."""

    def test_get_exchange_credentials_okx(self, mock_settings):
        """Test getting OKX credentials."""
        with patch("squant.websocket.manager.get_settings", return_value=mock_settings):
            manager = StreamManager()

            creds = manager._get_exchange_credentials("okx")

            assert creds is not None
            assert creds.api_key == "test-key"
            assert creds.api_secret == "test-secret"
            assert creds.passphrase == "test-passphrase"
            assert creds.sandbox is False

    def test_get_exchange_credentials_binance_no_key(self, mock_settings):
        """Test getting Binance credentials when not configured."""
        with patch("squant.websocket.manager.get_settings", return_value=mock_settings):
            manager = StreamManager()

            creds = manager._get_exchange_credentials("binance")

            assert creds is None

    def test_get_exchange_credentials_unknown(self, mock_settings):
        """Test getting credentials for unknown exchange."""
        with patch("squant.websocket.manager.get_settings", return_value=mock_settings):
            manager = StreamManager()

            creds = manager._get_exchange_credentials("unknown")

            assert creds is None


class TestStreamManagerRetryLoop:
    """Test StreamManager retry loop functionality."""

    @pytest.mark.asyncio
    async def test_start_retry_loop(self, mock_settings):
        """Test starting the retry loop."""
        with patch("squant.websocket.manager.get_settings", return_value=mock_settings):
            manager = StreamManager()
            manager._retry_interval = 0.01  # Speed up test

            manager.start_retry_loop()

            assert manager._retry_task is not None
            assert not manager._retry_task.done()

            # Cancel to cleanup
            manager._retry_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await manager._retry_task

    @pytest.mark.asyncio
    async def test_start_retry_loop_already_running(self, mock_settings):
        """Test starting retry loop when already running does nothing."""
        with patch("squant.websocket.manager.get_settings", return_value=mock_settings):
            manager = StreamManager()

            manager.start_retry_loop()
            first_task = manager._retry_task

            manager.start_retry_loop()

            # Should be the same task
            assert manager._retry_task is first_task

            # Cleanup
            manager._retry_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await manager._retry_task


class TestHealthCheckRecovery:
    """Tests for health check recovery logic."""

    @pytest.mark.asyncio
    async def test_attempt_recovery_ccxt_success(self, mock_settings):
        """Test successful CCXT provider recovery returns True."""
        with patch("squant.websocket.manager.get_settings", return_value=mock_settings):
            manager = StreamManager()
            manager._ccxt_provider = MagicMock()
            manager._ccxt_provider.reconnect = AsyncMock(return_value=True)

            result = await manager._attempt_recovery()

            assert result is True
            manager._ccxt_provider.reconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_attempt_recovery_ccxt_failure(self, mock_settings):
        """Test failed CCXT provider recovery returns False."""
        with patch("squant.websocket.manager.get_settings", return_value=mock_settings):
            manager = StreamManager()
            manager._ccxt_provider = MagicMock()
            manager._ccxt_provider.reconnect = AsyncMock(return_value=False)

            result = await manager._attempt_recovery()

            assert result is False

    @pytest.mark.asyncio
    async def test_attempt_recovery_no_provider(self, mock_settings):
        """Test recovery with no CCXT provider returns False."""
        with patch("squant.websocket.manager.get_settings", return_value=mock_settings):
            manager = StreamManager()
            manager._ccxt_provider = None

            result = await manager._attempt_recovery()

            assert result is False



class TestExchangeSwitchSubscriptionRecovery:
    """Tests for exchange switch subscription state handling."""

    @pytest.mark.asyncio
    async def test_switch_exchange_resubscription_failure_logged(self, mock_settings):
        """Test that failed resubscriptions during switch are logged, not lost silently."""
        with patch("squant.websocket.manager.get_settings", return_value=mock_settings):
            manager = StreamManager()
            manager._running = True

            # Set up initial provider
            old_provider = MagicMock()
            old_provider.exchange_id = "okx"
            old_provider.close = AsyncMock()
            manager._ccxt_provider = old_provider

            # Pre-populate subscriptions (dict with ref counts)
            manager._ticker_subscriptions["BTC/USDT"] = 1
            manager._ticker_subscriptions["ETH/USDT"] = 1

            # Mock new provider creation
            new_provider = MagicMock()
            new_provider.add_handler = MagicMock()
            new_provider.connect = AsyncMock()

            with (
                patch(
                    "squant.websocket.manager.CCXTStreamProvider",
                    return_value=new_provider,
                ),
                patch.object(manager, "_publish_exchange_switching", new_callable=AsyncMock),
                patch.object(manager, "_get_exchange_credentials", return_value=None),
            ):
                # Make subscribe_ticker fail for one symbol
                call_count = 0

                async def failing_subscribe(symbol):
                    nonlocal call_count
                    call_count += 1
                    if symbol == "ETH/USDT":
                        raise Exception("Symbol not found on new exchange")
                    manager._ticker_subscriptions[symbol] = 1

                manager.subscribe_ticker = failing_subscribe

                await manager.switch_exchange("binance")

                # BTC/USDT should be resubscribed, ETH/USDT should have failed
                assert "BTC/USDT" in manager._ticker_subscriptions
                # ETH/USDT was NOT added back (subscription lost)
                assert "ETH/USDT" not in manager._ticker_subscriptions
