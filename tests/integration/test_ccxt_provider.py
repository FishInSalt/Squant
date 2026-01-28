"""Integration tests for CCXTStreamProvider.

These tests verify the CCXT provider works with actual exchange connections.
They use sandbox/demo mode where possible.

Note: These tests require network access and may be slow.
Mark with pytest.mark.integration to skip in quick test runs.
"""

import asyncio

import pytest

from squant.infra.exchange.ccxt import CCXTStreamProvider


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

            # Wait for some data (with timeout)
            for _ in range(50):  # 5 seconds max
                await asyncio.sleep(0.1)
                if received_data:
                    break

            # Verify we received ticker data
            assert len(received_data) > 0
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

            # Wait for some data (with timeout)
            for _ in range(100):  # 10 seconds max
                await asyncio.sleep(0.1)
                if received_data:
                    break

            # Verify we received candle data
            assert len(received_data) > 0
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

            # Wait for some data (with timeout)
            for _ in range(50):  # 5 seconds max
                await asyncio.sleep(0.1)
                if received_data:
                    break

            # Verify we received orderbook data
            assert len(received_data) > 0
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

            # Wait for data from both symbols
            for _ in range(100):  # 10 seconds max
                await asyncio.sleep(0.1)
                if len(received_symbols) >= 2:
                    break

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

            # Wait for data from both types
            for _ in range(100):  # 10 seconds max
                await asyncio.sleep(0.1)
                if len(received_types) >= 2:
                    break

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

            # Wait for some data
            for _ in range(30):
                await asyncio.sleep(0.1)
                if received_count_before > 0:
                    break

            assert received_count_before > 0

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
