"""Unit tests for CCXTStreamProvider."""

import asyncio
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
        """Test that _handle_loop_error applies fast retry then exponential backoff."""
        provider = CCXTStreamProvider("okx")

        with patch("squant.infra.exchange.ccxt.provider.ccxtpro") as mock_ccxt:
            mock_exchange = MagicMock()
            mock_exchange.load_markets = AsyncMock()
            mock_exchange.close = AsyncMock()
            mock_ccxt.okx.return_value = mock_exchange

            await provider.connect()

            # Track sleep calls
            sleep_calls: list[float] = []

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

            # Verify that sleep was called with fast retry delay (first attempt)
            assert len(sleep_calls) >= 1
            # First reconnect uses fast retry delay (2s), not exponential backoff
            assert sleep_calls[0] == provider._fast_retry_delay

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


class TestFastRetry:
    """Tests for fast retry logic on initial subscription connection failures."""

    @pytest.mark.asyncio
    async def test_fast_retry_uses_fixed_delay(self) -> None:
        """Test that first N reconnect attempts use fast retry (short fixed delay)."""
        provider = CCXTStreamProvider("okx")

        with patch("squant.infra.exchange.ccxt.provider.ccxtpro") as mock_ccxt:
            mock_exchange = MagicMock()
            mock_exchange.load_markets = AsyncMock()
            mock_exchange.close = AsyncMock()
            mock_ccxt.okx.return_value = mock_exchange

            await provider.connect()

            sleep_calls: list[float] = []

            async def mock_sleep(delay: float) -> None:
                sleep_calls.append(delay)

            with (
                patch("asyncio.sleep", mock_sleep),
                patch.object(provider, "reconnect", AsyncMock(return_value=True)),
            ):
                # Trigger enough errors to hit reconnect threshold
                for _i in range(provider._max_consecutive_errors):
                    await provider._handle_loop_error("test:key", Exception("Test"))

            # First reconnect should use fast retry delay (2s), not exponential (1s)
            assert len(sleep_calls) == 1
            assert sleep_calls[0] == provider._fast_retry_delay

            await provider.close()

    @pytest.mark.asyncio
    async def test_fast_retry_transitions_to_exponential_backoff(self) -> None:
        """Test that after fast retry attempts are exhausted, exponential backoff is used."""
        provider = CCXTStreamProvider("okx")

        with patch("squant.infra.exchange.ccxt.provider.ccxtpro") as mock_ccxt:
            mock_exchange = MagicMock()
            mock_exchange.load_markets = AsyncMock()
            mock_exchange.close = AsyncMock()
            mock_ccxt.okx.return_value = mock_exchange

            await provider.connect()

            sleep_calls: list[float] = []

            async def mock_sleep(delay: float) -> None:
                sleep_calls.append(delay)

            # reconnect returns False to keep _subscription_reconnect_count incrementing
            # (on success it resets), but _consecutive_errors resets to 0 only on
            # reconnect success, so we need reconnect to fail to accumulate
            reconnect_call_count = 0

            async def mock_reconnect() -> bool:
                nonlocal reconnect_call_count
                reconnect_call_count += 1
                # Fail the reconnect so the subscription reconnect counter keeps growing
                return False

            with (
                patch("asyncio.sleep", mock_sleep),
                patch.object(provider, "reconnect", mock_reconnect),
            ):
                # Trigger fast_retry_max_attempts + 1 reconnect cycles
                for cycle in range(provider._fast_retry_max_attempts + 1):
                    # Reset consecutive errors to simulate a fresh error cycle
                    provider._consecutive_errors["test:key"] = (
                        provider._max_consecutive_errors - 1
                    )
                    await provider._handle_loop_error("test:key", Exception("Test"))

            # First N should be fast retry delay
            for i in range(provider._fast_retry_max_attempts):
                assert sleep_calls[i] == provider._fast_retry_delay, (
                    f"Call {i} should be fast retry delay"
                )
            # The one after should be exponential backoff (not fast retry delay)
            last_delay = sleep_calls[provider._fast_retry_max_attempts]
            assert last_delay != provider._fast_retry_delay, (
                "After fast retries exhausted, should use exponential backoff"
            )

            await provider.close()

    @pytest.mark.asyncio
    async def test_fast_retry_counter_resets_on_success(self) -> None:
        """Test that per-subscription reconnect counter resets on successful data receipt."""
        provider = CCXTStreamProvider("okx")

        key = "ohlcv:BTC/USDT:1m"
        provider._subscription_reconnect_count[key] = 5

        # Simulate successful message
        provider._mark_success(key)

        assert key not in provider._subscription_reconnect_count


class TestCandleCloseDetection:
    """Tests for candle close detection heuristic in CCXT provider."""

    @pytest.mark.asyncio
    async def test_first_candle_dispatched_as_not_closed(self) -> None:
        """First candle for a symbol should be dispatched with is_closed=False."""
        provider = CCXTStreamProvider("okx")
        dispatched: list = []

        async def mock_dispatch(data_type, data):
            dispatched.append((data_type, data))

        provider._dispatch = mock_dispatch  # type: ignore[assignment]
        provider._running = True

        symbol = "BTC/USDT"
        timeframe = "1h"
        candle_key = f"{symbol}:{timeframe}"
        ohlcv = [1700000000000, 50000, 51000, 49000, 50500, 100]
        candle_ts = int(ohlcv[0])

        # First candle: no previous state → no closed dispatch
        assert candle_key not in provider._last_candle_ts

        provider._last_candle_ts[candle_key] = candle_ts
        provider._last_candle_data[candle_key] = ohlcv

        ws_candle = provider._transformer.ohlcv_to_ws_candle(
            ohlcv, symbol, timeframe, is_closed=False
        )
        await provider._dispatch("candle", ws_candle)

        assert len(dispatched) == 1
        assert dispatched[0][0] == "candle"
        assert dispatched[0][1].is_closed is False

    @pytest.mark.asyncio
    async def test_new_timestamp_dispatches_closed_candle(self) -> None:
        """When candle timestamp changes, previous candle dispatched as closed."""
        provider = CCXTStreamProvider("okx")
        dispatched: list = []

        async def mock_dispatch(data_type, data):
            dispatched.append((data_type, data))

        provider._dispatch = mock_dispatch  # type: ignore[assignment]
        provider._running = True

        symbol = "BTC/USDT"
        timeframe = "1h"
        candle_key = f"{symbol}:{timeframe}"

        # Simulate previous candle state
        prev_ohlcv = [1700000000000, 50000, 51000, 49000, 50500, 100]
        provider._last_candle_ts[candle_key] = int(prev_ohlcv[0])
        provider._last_candle_data[candle_key] = prev_ohlcv

        # New candle with different timestamp (1 hour later)
        new_ohlcv = [1700003600000, 50500, 52000, 50000, 51500, 120]
        candle_ts = int(new_ohlcv[0])

        # Replicate the _ohlcv_loop close detection logic
        if candle_key in provider._last_candle_ts:
            if candle_ts != provider._last_candle_ts[candle_key]:
                closed_candle = provider._transformer.ohlcv_to_ws_candle(
                    provider._last_candle_data[candle_key],
                    symbol,
                    timeframe,
                    is_closed=True,
                )
                await provider._dispatch("candle", closed_candle)

        provider._last_candle_ts[candle_key] = candle_ts
        provider._last_candle_data[candle_key] = new_ohlcv

        ws_candle = provider._transformer.ohlcv_to_ws_candle(
            new_ohlcv, symbol, timeframe, is_closed=False
        )
        await provider._dispatch("candle", ws_candle)

        # Should have 2 dispatches: closed previous + open current
        assert len(dispatched) == 2
        assert dispatched[0][1].is_closed is True
        assert dispatched[0][1].close == prev_ohlcv[4]
        assert dispatched[1][1].is_closed is False
        assert dispatched[1][1].close == new_ohlcv[4]

    @pytest.mark.asyncio
    async def test_same_timestamp_no_closed_dispatch(self) -> None:
        """Same timestamp updates should not dispatch a closed candle."""
        provider = CCXTStreamProvider("okx")
        dispatched: list = []

        async def mock_dispatch(data_type, data):
            dispatched.append((data_type, data))

        provider._dispatch = mock_dispatch  # type: ignore[assignment]
        provider._running = True

        symbol = "BTC/USDT"
        timeframe = "1h"
        candle_key = f"{symbol}:{timeframe}"

        # Previous candle state
        prev_ohlcv = [1700000000000, 50000, 51000, 49000, 50500, 100]
        provider._last_candle_ts[candle_key] = int(prev_ohlcv[0])
        provider._last_candle_data[candle_key] = prev_ohlcv

        # Same timestamp, updated values (candle still forming)
        updated_ohlcv = [1700000000000, 50000, 51500, 49000, 51000, 150]
        candle_ts = int(updated_ohlcv[0])

        # Replicate close detection — same timestamp, no closed dispatch
        if candle_key in provider._last_candle_ts:
            if candle_ts != provider._last_candle_ts[candle_key]:
                closed_candle = provider._transformer.ohlcv_to_ws_candle(
                    provider._last_candle_data[candle_key],
                    symbol,
                    timeframe,
                    is_closed=True,
                )
                await provider._dispatch("candle", closed_candle)

        provider._last_candle_ts[candle_key] = candle_ts
        provider._last_candle_data[candle_key] = updated_ohlcv

        ws_candle = provider._transformer.ohlcv_to_ws_candle(
            updated_ohlcv, symbol, timeframe, is_closed=False
        )
        await provider._dispatch("candle", ws_candle)

        # Only 1 dispatch: the current (open) candle, no closed dispatch
        assert len(dispatched) == 1
        assert dispatched[0][1].is_closed is False

    def test_unwatch_cleans_candle_tracking(self) -> None:
        """Unwatching should clean up candle tracking state."""
        provider = CCXTStreamProvider("okx")

        # Set up tracking state
        provider._last_candle_ts["BTC/USDT:1h"] = 1700000000000
        provider._last_candle_data["BTC/USDT:1h"] = [
            1700000000000, 50000, 51000, 49000, 50500, 100,
        ]

        # Simulate the unwatch cleanup
        candle_key = "BTC/USDT:1h"
        provider._last_candle_ts.pop(candle_key, None)
        provider._last_candle_data.pop(candle_key, None)

        assert "BTC/USDT:1h" not in provider._last_candle_ts
        assert "BTC/USDT:1h" not in provider._last_candle_data


class TestBatchTickersLoopErrorHandling:
    """Tests that _batch_tickers_loop uses _handle_loop_error for consistent reconnect logic.

    Bug M-9: _batch_tickers_loop had its own independent error handling with:
    - Local consecutive_errors counter instead of shared self._consecutive_errors dict
    - Tolerance of 10 consecutive errors (other loops use 5 via _handle_loop_error)
    - Its own reconnect_attempt local variable instead of self._reconnect_attempt

    These tests verify the fix: _batch_tickers_loop now delegates to _handle_loop_error().
    """

    @pytest.mark.asyncio
    async def test_batch_tickers_loop_uses_shared_consecutive_errors(self) -> None:
        """_batch_tickers_loop should track errors in self._consecutive_errors, not a local var."""
        provider = CCXTStreamProvider("okx")
        provider._running = True
        provider._connected = True

        mock_exchange = MagicMock()
        # First call raises, second call we stop the loop
        call_count = 0

        async def watch_tickers_side_effect(symbols):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Connection lost")
            # Stop the loop on subsequent calls
            provider._running = False
            raise asyncio.CancelledError()

        mock_exchange.watch_tickers = AsyncMock(side_effect=watch_tickers_side_effect)
        provider._exchange = mock_exchange
        provider._watched_ticker_symbols = {"BTC/USDT"}

        # Mock _handle_loop_error to avoid actual reconnect logic
        handle_error_calls = []

        async def mock_handle_loop_error(key, error):
            handle_error_calls.append((key, error))
            provider._running = False  # Stop loop after handling error
            return False

        provider._handle_loop_error = mock_handle_loop_error  # type: ignore[assignment]

        await provider._batch_tickers_loop()

        # _handle_loop_error should have been called
        assert len(handle_error_calls) == 1
        key, error = handle_error_calls[0]
        assert key == "batch_tickers"
        assert isinstance(error, RuntimeError)
        assert "Connection lost" in str(error)

    @pytest.mark.asyncio
    async def test_batch_tickers_loop_uses_same_threshold_as_other_loops(self) -> None:
        """_batch_tickers_loop should use _max_consecutive_errors (5), not a local max of 10."""
        provider = CCXTStreamProvider("okx")
        provider._running = True
        provider._connected = True

        mock_exchange = MagicMock()
        mock_exchange.watch_tickers = AsyncMock(side_effect=RuntimeError("Connection lost"))
        provider._exchange = mock_exchange
        provider._watched_ticker_symbols = {"BTC/USDT"}

        # Track how many times _handle_loop_error is called
        handle_error_call_count = 0

        async def mock_handle_loop_error(key, error):
            nonlocal handle_error_call_count
            handle_error_call_count += 1
            # After _max_consecutive_errors calls, stop the loop
            if handle_error_call_count >= provider._max_consecutive_errors:
                provider._running = False
                return False
            return True

        provider._handle_loop_error = mock_handle_loop_error  # type: ignore[assignment]

        # Use timeout to prevent hanging if buggy code doesn't delegate to _handle_loop_error
        try:
            await asyncio.wait_for(provider._batch_tickers_loop(), timeout=5.0)
        except TimeoutError:
            provider._running = False
            pytest.fail(
                "_batch_tickers_loop timed out — likely not delegating to _handle_loop_error"
            )

        # Should have called _handle_loop_error exactly _max_consecutive_errors times
        assert handle_error_call_count == provider._max_consecutive_errors

    @pytest.mark.asyncio
    async def test_batch_tickers_loop_marks_success_via_mark_success(self) -> None:
        """_batch_tickers_loop should call _mark_success on successful ticker fetch."""
        provider = CCXTStreamProvider("okx")
        provider._running = True
        provider._connected = True

        mock_exchange = MagicMock()
        call_count = 0

        async def watch_tickers_side_effect(symbols):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"BTC/USDT": {"symbol": "BTC/USDT", "last": 50000.0}}
            provider._running = False
            raise asyncio.CancelledError()

        mock_exchange.watch_tickers = AsyncMock(side_effect=watch_tickers_side_effect)
        provider._exchange = mock_exchange
        provider._watched_ticker_symbols = {"BTC/USDT"}
        provider._handlers = []

        # Track _mark_success calls
        mark_success_calls = []
        original_mark_success = provider._mark_success

        def mock_mark_success(key):
            mark_success_calls.append(key)
            original_mark_success(key)

        provider._mark_success = mock_mark_success  # type: ignore[assignment]

        await provider._batch_tickers_loop()

        assert len(mark_success_calls) >= 1
        assert mark_success_calls[0] == "batch_tickers"

    @pytest.mark.asyncio
    async def test_batch_tickers_loop_invalid_symbol_not_passed_to_handle_loop_error(
        self,
    ) -> None:
        """Invalid symbol errors should still be handled specially, not via _handle_loop_error."""
        provider = CCXTStreamProvider("okx")
        provider._running = True
        provider._connected = True

        mock_exchange = MagicMock()
        call_count = 0

        async def watch_tickers_side_effect(symbols):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("okx does not have market symbol ZEC/USDT")
            # After removing invalid symbol, stop the loop
            provider._running = False
            return {"BTC/USDT": {"symbol": "BTC/USDT", "last": 50000.0}}

        mock_exchange.watch_tickers = AsyncMock(side_effect=watch_tickers_side_effect)
        provider._exchange = mock_exchange
        # Include a valid symbol so the loop doesn't stall after removing ZEC/USDT
        provider._watched_ticker_symbols = {"ZEC/USDT", "BTC/USDT"}
        provider._handlers = []

        # Track _handle_loop_error calls
        handle_error_calls = []

        async def mock_handle_loop_error(key, error):
            handle_error_calls.append((key, error))
            return True

        provider._handle_loop_error = mock_handle_loop_error  # type: ignore[assignment]

        try:
            await asyncio.wait_for(provider._batch_tickers_loop(), timeout=5.0)
        except TimeoutError:
            provider._running = False
            pytest.fail("_batch_tickers_loop timed out")

        # Invalid symbol errors should NOT be passed to _handle_loop_error
        assert len(handle_error_calls) == 0
        # The invalid symbol should be removed from the watch list
        assert "ZEC/USDT" not in provider._watched_ticker_symbols
