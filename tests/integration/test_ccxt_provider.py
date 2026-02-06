"""Integration tests for CCXTStreamProvider.

These tests verify the CCXT provider works with actual exchange connections.
They use sandbox/demo mode where possible.

Note: These tests require network access and may be slow.
Mark with pytest.mark.integration to skip in quick test runs.
"""

import asyncio
from collections.abc import Callable

import pytest

from squant.infra.exchange.ccxt import CCXTStreamProvider

# Default timeout for waiting on WebSocket data (seconds).
# Exchange WebSocket connections can be slow to establish, especially
# under load or in CI environments with shared network resources.
WS_DATA_TIMEOUT = 15


async def wait_for_data(
    check: Callable[[], bool],
    timeout: float = WS_DATA_TIMEOUT,
    poll_interval: float = 0.1,
    description: str = "WebSocket data",
) -> None:
    """Wait until check() returns True, or raise on timeout.

    Replaces hand-written polling loops across all WebSocket tests with
    a single, configurable utility that gives clear timeout messages.

    Args:
        check: Callable that returns True when desired data has arrived.
        timeout: Maximum wait time in seconds.
        poll_interval: Sleep interval between checks.
        description: Human-readable label for timeout error message.
    """
    elapsed = 0.0
    while elapsed < timeout:
        if check():
            return
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval
    pytest.fail(f"Timed out after {timeout}s waiting for {description}")


@pytest.mark.integration
class TestCCXTProviderConnection:
    """Integration tests for CCXT provider connection."""

    @pytest.mark.asyncio
    async def test_connect_okx(self) -> None:
        """Test connecting to OKX (public channels only)."""
        provider = CCXTStreamProvider("okx")

        try:
            await provider.connect()
            assert provider.is_connected is True
        finally:
            await provider.close()
            assert provider.is_connected is False

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Binance blocks access from many cloud providers and regions")
    async def test_connect_binance(self) -> None:
        """Test connecting to Binance (public channels only)."""
        provider = CCXTStreamProvider("binance")

        try:
            await provider.connect()
            assert provider.is_connected is True
        finally:
            await provider.close()
            assert provider.is_connected is False

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Bybit blocks access from many cloud providers and regions")
    async def test_connect_bybit(self) -> None:
        """Test connecting to Bybit (public channels only)."""
        provider = CCXTStreamProvider("bybit")

        try:
            await provider.connect()
            assert provider.is_connected is True
        finally:
            await provider.close()
            assert provider.is_connected is False


@pytest.mark.integration
class TestCCXTProviderPublicChannels:
    """Integration tests for CCXT provider public channels."""

    @pytest.mark.asyncio
    async def test_watch_ticker_okx(self) -> None:
        """Test watching ticker on OKX."""
        received_data = []

        async def handler(msg: dict) -> None:
            received_data.append(msg)

        provider = CCXTStreamProvider("okx")
        provider.add_handler(handler)

        try:
            await provider.connect()
            await provider.watch_ticker("BTC/USDT")

            await wait_for_data(
                lambda: len(received_data) > 0,
                description="OKX ticker data for BTC/USDT",
            )

            assert received_data[0]["type"] == "ticker"
            assert received_data[0]["data"].symbol == "BTC/USDT"

        finally:
            await provider.close()

    @pytest.mark.asyncio
    async def test_watch_ohlcv_okx(self) -> None:
        """Test watching OHLCV/candles on OKX."""
        received_data = []

        async def handler(msg: dict) -> None:
            received_data.append(msg)

        provider = CCXTStreamProvider("okx")
        provider.add_handler(handler)

        try:
            await provider.connect()
            await provider.watch_ohlcv("BTC/USDT", "1m")

            await wait_for_data(
                lambda: len(received_data) > 0,
                description="OKX OHLCV data for BTC/USDT 1m",
            )

            assert received_data[0]["type"] == "candle"
            assert received_data[0]["data"].symbol == "BTC/USDT"
            assert received_data[0]["data"].timeframe == "1m"

        finally:
            await provider.close()

    @pytest.mark.asyncio
    async def test_watch_orderbook_okx(self) -> None:
        """Test watching order book on OKX."""
        received_data = []

        async def handler(msg: dict) -> None:
            received_data.append(msg)

        provider = CCXTStreamProvider("okx")
        provider.add_handler(handler)

        try:
            await provider.connect()
            await provider.watch_order_book("BTC/USDT", limit=5)

            await wait_for_data(
                lambda: len(received_data) > 0,
                description="OKX orderbook data for BTC/USDT",
            )

            assert received_data[0]["type"] == "orderbook"
            assert received_data[0]["data"].symbol == "BTC/USDT"
            assert len(received_data[0]["data"].bids) <= 5
            assert len(received_data[0]["data"].asks) <= 5

        finally:
            await provider.close()


@pytest.mark.integration
class TestCCXTProviderMultipleSubscriptions:
    """Integration tests for multiple concurrent subscriptions."""

    @pytest.mark.asyncio
    async def test_multiple_symbols(self) -> None:
        """Test watching multiple symbols simultaneously."""
        received_symbols = set()

        async def handler(msg: dict) -> None:
            if msg["type"] == "ticker":
                received_symbols.add(msg["data"].symbol)

        provider = CCXTStreamProvider("okx")
        provider.add_handler(handler)

        try:
            await provider.connect()
            await provider.watch_ticker("BTC/USDT")
            await provider.watch_ticker("ETH/USDT")

            await wait_for_data(
                lambda: len(received_symbols) >= 2,
                description="ticker data for both BTC/USDT and ETH/USDT",
            )

            assert "BTC/USDT" in received_symbols
            assert "ETH/USDT" in received_symbols

        finally:
            await provider.close()

    @pytest.mark.asyncio
    async def test_multiple_data_types(self) -> None:
        """Test watching different data types simultaneously."""
        received_types = set()

        async def handler(msg: dict) -> None:
            received_types.add(msg["type"])

        provider = CCXTStreamProvider("okx")
        provider.add_handler(handler)

        try:
            await provider.connect()
            await provider.watch_ticker("BTC/USDT")
            await provider.watch_order_book("BTC/USDT")

            await wait_for_data(
                lambda: len(received_types) >= 2,
                description="both ticker and orderbook data types",
            )

            assert "ticker" in received_types
            assert "orderbook" in received_types

        finally:
            await provider.close()


@pytest.mark.integration
class TestCCXTProviderUnsubscribe:
    """Integration tests for unsubscribing from channels."""

    @pytest.mark.asyncio
    async def test_unwatch_stops_data(self) -> None:
        """Test that unwatching stops receiving data."""
        received_count_before = 0
        received_count_after = 0
        stop_counting = False

        async def handler(msg: dict) -> None:
            nonlocal received_count_before, received_count_after, stop_counting
            if stop_counting:
                received_count_after += 1
            else:
                received_count_before += 1

        provider = CCXTStreamProvider("okx")
        provider.add_handler(handler)

        try:
            await provider.connect()
            await provider.watch_ticker("BTC/USDT")

            await wait_for_data(
                lambda: received_count_before > 0,
                description="initial OKX ticker data before unwatch",
            )

            # Unwatch and set flag
            await provider.unwatch("ticker:BTC/USDT")
            stop_counting = True

            # Wait a bit and verify no more data
            await asyncio.sleep(1)

            # After unwatching, we should not receive significant new data
            # (there may be a few messages in flight)
            assert received_count_after < 5

        finally:
            await provider.close()
