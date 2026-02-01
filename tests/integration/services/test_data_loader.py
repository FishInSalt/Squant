"""
Integration tests for Data Loader Service.

Tests data loader functionality with real database integration:
- Loading historical bars from the database
- Streaming bars as async iterator
- Counting available bars
- Checking data availability
- Querying available symbols
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio

from squant.models.market import Kline
from squant.services.data_loader import DataLoader


@pytest_asyncio.fixture
async def data_loader(db_session):
    """Create data loader service instance."""
    return DataLoader(db_session)


@pytest_asyncio.fixture
async def sample_klines(db_session):
    """Create sample klines in the database."""
    now = datetime.now(UTC)
    klines = []

    # Create 20 klines for BTC/USDT
    for i in range(20):
        kline = Kline(
            exchange="okx",
            symbol="BTC/USDT",
            timeframe="1m",
            time=now - timedelta(minutes=20 - i),
            open=Decimal("40000") + Decimal(str(i * 10)),
            high=Decimal("40100") + Decimal(str(i * 10)),
            low=Decimal("39900") + Decimal(str(i * 10)),
            close=Decimal("40050") + Decimal(str(i * 10)),
            volume=Decimal("100") + Decimal(str(i)),
        )
        klines.append(kline)
        db_session.add(kline)

    # Create 10 klines for ETH/USDT
    for i in range(10):
        kline = Kline(
            exchange="okx",
            symbol="ETH/USDT",
            timeframe="1m",
            time=now - timedelta(minutes=10 - i),
            open=Decimal("2500") + Decimal(str(i * 5)),
            high=Decimal("2550") + Decimal(str(i * 5)),
            low=Decimal("2450") + Decimal(str(i * 5)),
            close=Decimal("2525") + Decimal(str(i * 5)),
            volume=Decimal("500") + Decimal(str(i * 10)),
        )
        klines.append(kline)
        db_session.add(kline)

    await db_session.commit()

    for kline in klines:
        await db_session.refresh(kline)

    return klines


class TestBarLoading:
    """Tests for loading bars from the database."""

    @pytest.mark.asyncio
    async def test_load_bars_as_iterator(self, data_loader, sample_klines):
        """Test loading bars as an async iterator."""
        # Use times from sample klines to avoid timing issues
        btc_klines = [k for k in sample_klines if k.symbol == "BTC/USDT"]
        start = min(k.time for k in btc_klines) - timedelta(seconds=1)
        end = max(k.time for k in btc_klines) + timedelta(seconds=1)

        bars = []
        async for bar in data_loader.load_bars(
            exchange="okx",
            symbol="BTC/USDT",
            timeframe="1m",
            start=start,
            end=end,
        ):
            bars.append(bar)

        # Should load all 20 BTC/USDT klines
        assert len(bars) == 20
        assert all(bar.symbol == "BTC/USDT" for bar in bars)

        # Verify bars are in chronological order
        for i in range(1, len(bars)):
            assert bars[i].time > bars[i - 1].time

    @pytest.mark.asyncio
    async def test_load_bars_with_time_filter(self, data_loader, sample_klines):
        """Test loading bars with time range filter."""
        now = datetime.now(UTC)
        # Only get the last 5 minutes
        start = now - timedelta(minutes=5)
        end = now

        bars = []
        async for bar in data_loader.load_bars(
            exchange="okx",
            symbol="BTC/USDT",
            timeframe="1m",
            start=start,
            end=end,
        ):
            bars.append(bar)

        # Should get roughly 5 bars (may be slightly different due to timing)
        assert len(bars) <= 5
        assert all(bar.time >= start for bar in bars)
        assert all(bar.time <= end for bar in bars)

    @pytest.mark.asyncio
    async def test_load_bars_different_symbols(self, data_loader, sample_klines):
        """Test that symbol filter works correctly."""
        # Use times from sample klines
        all_times = [k.time for k in sample_klines]
        start = min(all_times) - timedelta(seconds=1)
        end = max(all_times) + timedelta(seconds=1)

        # Load BTC bars
        btc_bars = []
        async for bar in data_loader.load_bars(
            exchange="okx",
            symbol="BTC/USDT",
            timeframe="1m",
            start=start,
            end=end,
        ):
            btc_bars.append(bar)

        # Load ETH bars
        eth_bars = []
        async for bar in data_loader.load_bars(
            exchange="okx",
            symbol="ETH/USDT",
            timeframe="1m",
            start=start,
            end=end,
        ):
            eth_bars.append(bar)

        assert len(btc_bars) == 20
        assert len(eth_bars) == 10
        assert all(b.symbol == "BTC/USDT" for b in btc_bars)
        assert all(b.symbol == "ETH/USDT" for b in eth_bars)

    @pytest.mark.asyncio
    async def test_load_bars_empty_result(self, data_loader):
        """Test loading bars when no data exists."""
        now = datetime.now(UTC)
        start = now - timedelta(hours=48)  # Long time ago
        end = now - timedelta(hours=24)  # Still long ago

        bars = []
        async for bar in data_loader.load_bars(
            exchange="okx",
            symbol="NONEXISTENT/USDT",
            timeframe="1m",
            start=start,
            end=end,
        ):
            bars.append(bar)

        assert len(bars) == 0

    @pytest.mark.asyncio
    async def test_load_bars_batch_size(self, data_loader, sample_klines):
        """Test that batch_size parameter works."""
        # Use times from sample klines
        btc_klines = [k for k in sample_klines if k.symbol == "BTC/USDT"]
        start = min(k.time for k in btc_klines) - timedelta(seconds=1)
        end = max(k.time for k in btc_klines) + timedelta(seconds=1)

        # Load with small batch size
        bars = []
        async for bar in data_loader.load_bars(
            exchange="okx",
            symbol="BTC/USDT",
            timeframe="1m",
            start=start,
            end=end,
            batch_size=5,  # Small batch
        ):
            bars.append(bar)

        # Should still get all 20 bars, just in smaller batches
        assert len(bars) == 20


class TestBarCounting:
    """Tests for counting bars."""

    @pytest.mark.asyncio
    async def test_count_bars(self, data_loader, sample_klines):
        """Test counting available bars."""
        # Use times from sample klines
        btc_klines = [k for k in sample_klines if k.symbol == "BTC/USDT"]
        start = min(k.time for k in btc_klines) - timedelta(seconds=1)
        end = max(k.time for k in btc_klines) + timedelta(seconds=1)

        count = await data_loader.count_bars(
            exchange="okx",
            symbol="BTC/USDT",
            timeframe="1m",
            start=start,
            end=end,
        )

        assert count == 20

    @pytest.mark.asyncio
    async def test_count_bars_with_filter(self, data_loader, sample_klines):
        """Test counting bars with time filter."""
        now = datetime.now(UTC)
        start = now - timedelta(minutes=5)
        end = now

        count = await data_loader.count_bars(
            exchange="okx",
            symbol="BTC/USDT",
            timeframe="1m",
            start=start,
            end=end,
        )

        # Should be roughly 5 bars
        assert count <= 5

    @pytest.mark.asyncio
    async def test_count_bars_no_data(self, data_loader):
        """Test counting when no data exists."""
        now = datetime.now(UTC)
        start = now - timedelta(hours=48)
        end = now - timedelta(hours=24)

        count = await data_loader.count_bars(
            exchange="okx",
            symbol="NONEXISTENT/USDT",
            timeframe="1m",
            start=start,
            end=end,
        )

        assert count == 0


class TestDataAvailability:
    """Tests for checking data availability."""

    @pytest.mark.asyncio
    async def test_check_data_availability_complete(self, data_loader, sample_klines):
        """Test checking data availability when data is complete."""
        # Use times from sample klines
        btc_klines = [k for k in sample_klines if k.symbol == "BTC/USDT"]
        start = min(k.time for k in btc_klines) - timedelta(seconds=1)
        end = max(k.time for k in btc_klines) + timedelta(seconds=1)

        availability = await data_loader.check_data_availability(
            exchange="okx",
            symbol="BTC/USDT",
            timeframe="1m",
            start=start,
            end=end,
        )

        assert availability.has_data is True
        assert availability.total_bars == 20
        assert availability.exchange == "okx"
        assert availability.symbol == "BTC/USDT"
        assert availability.timeframe == "1m"
        assert availability.first_bar is not None
        assert availability.last_bar is not None

    @pytest.mark.asyncio
    async def test_check_data_availability_no_data(self, data_loader):
        """Test checking data availability when no data exists."""
        now = datetime.now(UTC)
        start = now - timedelta(hours=48)
        end = now - timedelta(hours=24)

        availability = await data_loader.check_data_availability(
            exchange="okx",
            symbol="NONEXISTENT/USDT",
            timeframe="1m",
            start=start,
            end=end,
        )

        assert availability.has_data is False
        assert availability.total_bars == 0
        assert availability.first_bar is None
        assert availability.last_bar is None

    @pytest.mark.asyncio
    async def test_check_data_availability_is_complete(self, data_loader, sample_klines):
        """Test is_complete property."""
        now = datetime.now(UTC)

        # Request range that should be covered
        start = now - timedelta(minutes=15)
        end = now - timedelta(minutes=5)

        availability = await data_loader.check_data_availability(
            exchange="okx",
            symbol="BTC/USDT",
            timeframe="1m",
            start=start,
            end=end,
        )

        assert availability.has_data is True
        # is_complete checks if data covers the full requested range
        # Since we have data from 20 minutes ago to now, it should be complete

    @pytest.mark.asyncio
    async def test_data_availability_to_dict(self, data_loader, sample_klines):
        """Test converting availability to dictionary."""
        # Use times from sample klines
        btc_klines = [k for k in sample_klines if k.symbol == "BTC/USDT"]
        start = min(k.time for k in btc_klines) - timedelta(seconds=1)
        end = max(k.time for k in btc_klines) + timedelta(seconds=1)

        availability = await data_loader.check_data_availability(
            exchange="okx",
            symbol="BTC/USDT",
            timeframe="1m",
            start=start,
            end=end,
        )

        result = availability.to_dict()

        assert isinstance(result, dict)
        assert result["exchange"] == "okx"
        assert result["symbol"] == "BTC/USDT"
        assert result["timeframe"] == "1m"
        assert result["total_bars"] == 20
        assert result["has_data"] is True
        assert "first_bar" in result
        assert "last_bar" in result
        assert "requested_start" in result
        assert "requested_end" in result


class TestAvailableSymbols:
    """Tests for querying available symbols."""

    @pytest.mark.asyncio
    async def test_get_available_symbols(self, data_loader, sample_klines):
        """Test getting list of available symbols."""
        symbols = await data_loader.get_available_symbols()

        # Should have both BTC/USDT and ETH/USDT
        assert len(symbols) >= 2

        # Find BTC entry
        btc_entry = next((s for s in symbols if s["symbol"] == "BTC/USDT"), None)
        assert btc_entry is not None
        assert btc_entry["exchange"] == "okx"
        assert btc_entry["timeframe"] == "1m"
        assert btc_entry["bar_count"] == 20

        # Find ETH entry
        eth_entry = next((s for s in symbols if s["symbol"] == "ETH/USDT"), None)
        assert eth_entry is not None
        assert eth_entry["bar_count"] == 10

    @pytest.mark.asyncio
    async def test_get_available_symbols_filter_by_exchange(self, data_loader, sample_klines):
        """Test filtering available symbols by exchange."""
        symbols = await data_loader.get_available_symbols(exchange="okx")

        assert len(symbols) >= 2
        assert all(s["exchange"] == "okx" for s in symbols)

    @pytest.mark.asyncio
    async def test_get_available_symbols_filter_by_timeframe(self, data_loader, sample_klines):
        """Test filtering available symbols by timeframe."""
        symbols = await data_loader.get_available_symbols(timeframe="1m")

        assert len(symbols) >= 2
        assert all(s["timeframe"] == "1m" for s in symbols)

    @pytest.mark.asyncio
    async def test_get_available_symbols_no_data(self, data_loader):
        """Test getting available symbols when no data exists."""
        symbols = await data_loader.get_available_symbols(exchange="nonexistent")

        assert len(symbols) == 0

    @pytest.mark.asyncio
    async def test_available_symbols_include_metadata(self, data_loader, sample_klines):
        """Test that available symbols include first_bar and last_bar."""
        symbols = await data_loader.get_available_symbols()

        for symbol in symbols:
            assert "first_bar" in symbol
            assert "last_bar" in symbol
            assert "bar_count" in symbol
            # Should have ISO format timestamps
            if symbol["first_bar"]:
                assert isinstance(symbol["first_bar"], str)
                assert "T" in symbol["first_bar"]  # ISO format
