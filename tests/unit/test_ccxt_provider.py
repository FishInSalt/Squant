"""Unit tests for CCXTStreamProvider."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from squant.infra.exchange.ccxt.provider import CCXTStreamProvider
from squant.infra.exchange.ccxt.types import SUPPORTED_EXCHANGES, ExchangeCredentials
from squant.infra.exchange.exceptions import (
    ExchangeAuthenticationError,
    ExchangeConnectionError,
)


class TestCCXTStreamProviderInit:
    """Tests for CCXTStreamProvider initialization."""

    def test_init_supported_exchange(self) -> None:
        """Test initializing with a supported exchange."""
        for exchange_id in SUPPORTED_EXCHANGES:
            provider = CCXTStreamProvider(exchange_id)
            assert provider.exchange_id == exchange_id
            assert provider.is_connected is False

    def test_init_unsupported_exchange(self) -> None:
        """Test that unsupported exchanges raise ValueError."""
        with pytest.raises(ValueError, match="Unsupported exchange"):
            CCXTStreamProvider("kraken")

    def test_init_case_insensitive(self) -> None:
        """Test that exchange ID is case-insensitive."""
        provider = CCXTStreamProvider("OKX")
        assert provider.exchange_id == "okx"

        provider = CCXTStreamProvider("BINANCE")
        assert provider.exchange_id == "binance"

    def test_init_with_credentials(self) -> None:
        """Test initializing with credentials."""
        credentials = ExchangeCredentials(
            api_key="test-key",
            api_secret="test-secret",
            passphrase="test-pass",
            sandbox=True,
        )
        provider = CCXTStreamProvider("okx", credentials)
        assert provider._credentials == credentials


class TestCCXTStreamProviderConnect:
    """Tests for CCXTStreamProvider connection."""

    @pytest.mark.asyncio
    async def test_connect_creates_exchange_instance(self) -> None:
        """Test that connect creates the exchange instance."""
        provider = CCXTStreamProvider("okx")

        with patch("squant.infra.exchange.ccxt.provider.ccxtpro") as mock_ccxt:
            mock_exchange = MagicMock()
            mock_exchange.load_markets = AsyncMock()
            mock_ccxt.okx.return_value = mock_exchange

            await provider.connect()

            assert provider.is_connected is True
            mock_ccxt.okx.assert_called_once()
            mock_exchange.load_markets.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_with_credentials(self) -> None:
        """Test that credentials are passed to exchange."""
        credentials = ExchangeCredentials(
            api_key="test-key",
            api_secret="test-secret",
            passphrase="test-pass",
            sandbox=True,
        )
        provider = CCXTStreamProvider("okx", credentials)

        with patch("squant.infra.exchange.ccxt.provider.ccxtpro") as mock_ccxt:
            mock_exchange = MagicMock()
            mock_exchange.load_markets = AsyncMock()
            mock_ccxt.okx.return_value = mock_exchange

            await provider.connect()

            call_args = mock_ccxt.okx.call_args[0][0]
            assert call_args["apiKey"] == "test-key"
            assert call_args["secret"] == "test-secret"
            assert call_args["password"] == "test-pass"
            assert call_args["sandbox"] is True

    @pytest.mark.asyncio
    async def test_connect_already_connected(self) -> None:
        """Test that connect is idempotent."""
        provider = CCXTStreamProvider("okx")

        with patch("squant.infra.exchange.ccxt.provider.ccxtpro") as mock_ccxt:
            mock_exchange = MagicMock()
            mock_exchange.load_markets = AsyncMock()
            mock_ccxt.okx.return_value = mock_exchange

            await provider.connect()
            await provider.connect()  # Second call should be no-op

            # Should only be called once
            assert mock_ccxt.okx.call_count == 1

    @pytest.mark.asyncio
    async def test_connect_failure_raises_exception(self) -> None:
        """Test that connection failure raises ExchangeConnectionError."""
        provider = CCXTStreamProvider("okx")

        with patch("squant.infra.exchange.ccxt.provider.ccxtpro") as mock_ccxt:
            mock_ccxt.okx.side_effect = Exception("Connection failed")

            with pytest.raises(ExchangeConnectionError):
                await provider.connect()


class TestCCXTStreamProviderClose:
    """Tests for CCXTStreamProvider close."""

    @pytest.mark.asyncio
    async def test_close_disconnects(self) -> None:
        """Test that close properly disconnects."""
        provider = CCXTStreamProvider("okx")

        with patch("squant.infra.exchange.ccxt.provider.ccxtpro") as mock_ccxt:
            mock_exchange = MagicMock()
            mock_exchange.load_markets = AsyncMock()
            mock_exchange.close = AsyncMock()
            mock_ccxt.okx.return_value = mock_exchange

            await provider.connect()
            assert provider.is_connected is True

            await provider.close()
            assert provider.is_connected is False
            mock_exchange.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_cancels_tasks(self) -> None:
        """Test that close cancels subscription tasks and clears watched symbols."""
        provider = CCXTStreamProvider("okx")

        with patch("squant.infra.exchange.ccxt.provider.ccxtpro") as mock_ccxt:
            mock_exchange = MagicMock()
            mock_exchange.load_markets = AsyncMock()
            mock_exchange.close = AsyncMock()
            mock_exchange.watch_tickers = AsyncMock(side_effect=Exception("Cancelled"))
            mock_exchange.markets = {"BTC/USDT": {"symbol": "BTC/USDT"}}
            mock_ccxt.okx.return_value = mock_exchange

            await provider.connect()

            # Start a ticker subscription (uses batch watching)
            await provider.watch_ticker("BTC/USDT")
            assert "BTC/USDT" in provider._watched_ticker_symbols
            assert provider._tickers_task is not None

            # Close should cancel the task and clear symbols
            await provider.close()
            assert len(provider._watched_ticker_symbols) == 0
            assert provider._tickers_task is None


class TestCCXTStreamProviderHandlers:
    """Tests for message handler management."""

    def test_add_handler(self) -> None:
        """Test adding a message handler."""
        provider = CCXTStreamProvider("okx")

        async def handler(msg: dict) -> None:
            pass

        provider.add_handler(handler)
        assert handler in provider._handlers

    def test_add_handler_no_duplicates(self) -> None:
        """Test that handlers are not duplicated."""
        provider = CCXTStreamProvider("okx")

        async def handler(msg: dict) -> None:
            pass

        provider.add_handler(handler)
        provider.add_handler(handler)
        assert len(provider._handlers) == 1

    def test_remove_handler(self) -> None:
        """Test removing a message handler."""
        provider = CCXTStreamProvider("okx")

        async def handler(msg: dict) -> None:
            pass

        provider.add_handler(handler)
        provider.remove_handler(handler)
        assert handler not in provider._handlers


class TestCCXTStreamProviderSubscriptions:
    """Tests for subscription methods."""

    @pytest.mark.asyncio
    async def test_watch_ticker_creates_task(self) -> None:
        """Test that watch_ticker adds symbol to batch watch list."""
        provider = CCXTStreamProvider("okx")

        with patch("squant.infra.exchange.ccxt.provider.ccxtpro") as mock_ccxt:
            mock_exchange = MagicMock()
            mock_exchange.load_markets = AsyncMock()
            mock_exchange.watch_tickers = AsyncMock(
                return_value={"BTC/USDT": {"symbol": "BTC/USDT"}}
            )
            mock_exchange.close = AsyncMock()
            mock_exchange.markets = {"BTC/USDT": {"symbol": "BTC/USDT"}}
            mock_ccxt.okx.return_value = mock_exchange

            await provider.connect()
            await provider.watch_ticker("BTC/USDT")

            # With batch ticker watching, symbol is added to _watched_ticker_symbols
            assert "BTC/USDT" in provider._watched_ticker_symbols
            # And a batch tickers task is created
            assert provider._tickers_task is not None

            await provider.close()

    @pytest.mark.asyncio
    async def test_watch_ohlcv_validates_timeframe(self) -> None:
        """Test that watch_ohlcv validates timeframe."""
        provider = CCXTStreamProvider("okx")

        with patch("squant.infra.exchange.ccxt.provider.ccxtpro") as mock_ccxt:
            mock_exchange = MagicMock()
            mock_exchange.load_markets = AsyncMock()
            mock_exchange.close = AsyncMock()
            mock_ccxt.okx.return_value = mock_exchange

            await provider.connect()

            with pytest.raises(ValueError, match="Invalid timeframe"):
                await provider.watch_ohlcv("BTC/USDT", "invalid")

            await provider.close()

    @pytest.mark.asyncio
    async def test_watch_orders_requires_credentials(self) -> None:
        """Test that private channels require credentials."""
        provider = CCXTStreamProvider("okx")  # No credentials

        with patch("squant.infra.exchange.ccxt.provider.ccxtpro") as mock_ccxt:
            mock_exchange = MagicMock()
            mock_exchange.load_markets = AsyncMock()
            mock_exchange.close = AsyncMock()
            mock_ccxt.okx.return_value = mock_exchange

            await provider.connect()

            with pytest.raises(ExchangeAuthenticationError):
                await provider.watch_orders()

            await provider.close()

    @pytest.mark.asyncio
    async def test_watch_balance_requires_credentials(self) -> None:
        """Test that balance watching requires credentials."""
        provider = CCXTStreamProvider("okx")  # No credentials

        with patch("squant.infra.exchange.ccxt.provider.ccxtpro") as mock_ccxt:
            mock_exchange = MagicMock()
            mock_exchange.load_markets = AsyncMock()
            mock_exchange.close = AsyncMock()
            mock_ccxt.okx.return_value = mock_exchange

            await provider.connect()

            with pytest.raises(ExchangeAuthenticationError):
                await provider.watch_balance()

            await provider.close()

    @pytest.mark.asyncio
    async def test_unwatch_cancels_subscription(self) -> None:
        """Test that unwatch removes symbol from batch watch list."""
        provider = CCXTStreamProvider("okx")

        with patch("squant.infra.exchange.ccxt.provider.ccxtpro") as mock_ccxt:
            mock_exchange = MagicMock()
            mock_exchange.load_markets = AsyncMock()
            mock_exchange.watch_tickers = AsyncMock(
                return_value={"BTC/USDT": {"symbol": "BTC/USDT"}}
            )
            mock_exchange.close = AsyncMock()
            mock_exchange.markets = {"BTC/USDT": {"symbol": "BTC/USDT"}}
            mock_ccxt.okx.return_value = mock_exchange

            await provider.connect()
            await provider.watch_ticker("BTC/USDT")

            assert "BTC/USDT" in provider._watched_ticker_symbols

            await provider.unwatch("ticker:BTC/USDT")

            assert "BTC/USDT" not in provider._watched_ticker_symbols

            await provider.close()


class TestCCXTStreamProviderContextManager:
    """Tests for async context manager support."""

    @pytest.mark.asyncio
    async def test_context_manager(self) -> None:
        """Test using provider as async context manager."""
        with patch("squant.infra.exchange.ccxt.provider.ccxtpro") as mock_ccxt:
            mock_exchange = MagicMock()
            mock_exchange.load_markets = AsyncMock()
            mock_exchange.close = AsyncMock()
            mock_ccxt.okx.return_value = mock_exchange

            async with CCXTStreamProvider("okx") as provider:
                assert provider.is_connected is True

            assert provider.is_connected is False
            mock_exchange.close.assert_called_once()


class TestExchangeCredentials:
    """Tests for ExchangeCredentials dataclass."""

    def test_credentials_defaults(self) -> None:
        """Test default values for credentials."""
        credentials = ExchangeCredentials(
            api_key="key",
            api_secret="secret",
        )

        assert credentials.api_key == "key"
        assert credentials.api_secret == "secret"
        assert credentials.passphrase is None
        assert credentials.sandbox is False

    def test_credentials_with_all_fields(self) -> None:
        """Test credentials with all fields set."""
        credentials = ExchangeCredentials(
            api_key="key",
            api_secret="secret",
            passphrase="pass",
            sandbox=True,
        )

        assert credentials.api_key == "key"
        assert credentials.api_secret == "secret"
        assert credentials.passphrase == "pass"
        assert credentials.sandbox is True


class TestCCXTStreamProviderReconnectBackoff:
    """Tests for exponential backoff reconnection logic."""

    def test_backoff_delay_progression(self) -> None:
        """Test exponential backoff delay calculation follows 2^n pattern."""
        provider = CCXTStreamProvider("okx")

        # Calculate delays for attempts 1-7
        delays = [provider._get_reconnect_delay(i) for i in range(1, 8)]

        # Verify exponential progression (allowing for ±10% jitter)
        # Expected: 1s, 2s, 4s, 8s, 16s, 32s, 60s (capped)
        assert 0.9 <= delays[0] <= 1.1  # ~1s
        assert 1.8 <= delays[1] <= 2.2  # ~2s
        assert 3.6 <= delays[2] <= 4.4  # ~4s
        assert 7.2 <= delays[3] <= 8.8  # ~8s
        assert 14.4 <= delays[4] <= 17.6  # ~16s
        assert 28.8 <= delays[5] <= 35.2  # ~32s
        assert 54.0 <= delays[6] <= 66.0  # ~60s (capped)

    def test_backoff_max_delay_cap(self) -> None:
        """Test that delay is capped at max value."""
        provider = CCXTStreamProvider("okx")

        # Very high attempt number should still be capped
        delay = provider._get_reconnect_delay(100)

        # Allow for ±10% jitter on max delay
        assert delay <= provider._reconnect_max_delay * 1.1

    def test_backoff_attempt_zero_treated_as_one(self) -> None:
        """Test that attempt 0 is treated as attempt 1."""
        provider = CCXTStreamProvider("okx")

        delay_zero = provider._get_reconnect_delay(0)
        delay_one = provider._get_reconnect_delay(1)

        # Both should give approximately 1 second (with jitter variance)
        assert 0.9 <= delay_zero <= 1.1
        assert 0.9 <= delay_one <= 1.1

    def test_backoff_jitter_adds_variance(self) -> None:
        """Test that jitter adds variance to delays."""
        provider = CCXTStreamProvider("okx")

        # Generate multiple delays for the same attempt
        delays = [provider._get_reconnect_delay(3) for _ in range(10)]

        # With jitter, not all delays should be identical
        # (There's a very small chance they could all be the same,
        # but with 10 samples that's extremely unlikely)
        unique_delays = set(delays)
        assert len(unique_delays) > 1

    @pytest.mark.asyncio
    async def test_reconnect_resets_attempt_counter(self) -> None:
        """Test that successful reconnect resets the attempt counter."""
        provider = CCXTStreamProvider("okx")

        with patch("squant.infra.exchange.ccxt.provider.ccxtpro") as mock_ccxt:
            mock_exchange = MagicMock()
            mock_exchange.load_markets = AsyncMock()
            mock_exchange.close = AsyncMock()
            mock_ccxt.okx.return_value = mock_exchange

            await provider.connect()

            # Simulate some reconnect attempts
            provider._reconnect_attempt = 5

            # To trigger actual reconnection, we need to make is_healthy() return False
            # is_healthy checks: connected, exchange, and (if subscriptions) message timing
            # Add a fake subscription task so the timing check kicks in
            fake_task = MagicMock()
            provider._subscription_tasks["test"] = fake_task
            provider._last_successful_message = 1  # Very old timestamp (1970)

            # Successful reconnect should reset counter
            result = await provider.reconnect()

            assert result is True
            assert provider._reconnect_attempt == 0

            await provider.close()

    @pytest.mark.asyncio
    async def test_handle_loop_error_uses_backoff(self) -> None:
        """Test that _handle_loop_error applies exponential backoff."""
        provider = CCXTStreamProvider("okx")

        with patch("squant.infra.exchange.ccxt.provider.ccxtpro") as mock_ccxt:
            mock_exchange = MagicMock()
            mock_exchange.load_markets = AsyncMock()
            mock_exchange.close = AsyncMock()
            mock_ccxt.okx.return_value = mock_exchange

            await provider.connect()

            # Track sleep calls
            sleep_calls = []

            async def mock_sleep(delay: float) -> None:
                sleep_calls.append(delay)

            # Mock asyncio.sleep and reconnect
            with (
                patch("asyncio.sleep", mock_sleep),
                patch.object(provider, "reconnect", AsyncMock(return_value=True)),
            ):
                # Simulate enough errors to trigger reconnection
                for i in range(provider._max_consecutive_errors):
                    await provider._handle_loop_error("test:key", Exception("Test error"))

            # Verify that sleep was called with backoff delay before reconnect
            assert len(sleep_calls) >= 1
            # First backoff delay should be approximately 1 second
            assert 0.9 <= sleep_calls[0] <= 1.1

            await provider.close()

    @pytest.mark.asyncio
    async def test_handle_loop_error_resets_on_success(self) -> None:
        """Test that error counter resets after successful reconnect."""
        provider = CCXTStreamProvider("okx")

        with patch("squant.infra.exchange.ccxt.provider.ccxtpro") as mock_ccxt:
            mock_exchange = MagicMock()
            mock_exchange.load_markets = AsyncMock()
            mock_exchange.close = AsyncMock()
            mock_ccxt.okx.return_value = mock_exchange

            await provider.connect()

            # Set up consecutive errors
            key = "test:key"
            provider._consecutive_errors[key] = provider._max_consecutive_errors - 1
            provider._reconnect_attempt = 3

            with (
                patch("asyncio.sleep", AsyncMock()),
                patch.object(provider, "reconnect", AsyncMock(return_value=True)),
            ):
                # This error should trigger reconnect
                await provider._handle_loop_error(key, Exception("Test error"))

            # Verify counters were reset
            assert provider._consecutive_errors[key] == 0
            assert provider._reconnect_attempt == 0

            await provider.close()
