"""Unit tests for data loader service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from squant.services.data_loader import DataAvailability, DataLoader


@pytest.fixture
def mock_session():
    """Create a mock database session."""
    session = MagicMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def mock_kline():
    """Create a mock kline record."""
    kline = MagicMock()
    kline.time = datetime.now(UTC)
    kline.exchange = "okx"
    kline.symbol = "BTC/USDT"
    kline.timeframe = "1h"
    kline.open = Decimal("50000")
    kline.high = Decimal("51000")
    kline.low = Decimal("49000")
    kline.close = Decimal("50500")
    kline.volume = Decimal("100")
    return kline


class TestDataAvailability:
    """Tests for DataAvailability class."""

    def test_has_data_true(self):
        """Test has_data property when data exists."""
        availability = DataAvailability(
            exchange="okx",
            symbol="BTC/USDT",
            timeframe="1h",
            first_bar=datetime.now(UTC) - timedelta(days=30),
            last_bar=datetime.now(UTC),
            total_bars=720,
            requested_start=datetime.now(UTC) - timedelta(days=30),
            requested_end=datetime.now(UTC),
        )

        assert availability.has_data is True

    def test_has_data_false(self):
        """Test has_data property when no data exists."""
        availability = DataAvailability(
            exchange="okx",
            symbol="BTC/USDT",
            timeframe="1h",
            first_bar=None,
            last_bar=None,
            total_bars=0,
            requested_start=datetime.now(UTC) - timedelta(days=30),
            requested_end=datetime.now(UTC),
        )

        assert availability.has_data is False

    def test_is_complete_true(self):
        """Test is_complete property when data covers full range."""
        requested_start = datetime.now(UTC) - timedelta(days=30)
        requested_end = datetime.now(UTC)

        availability = DataAvailability(
            exchange="okx",
            symbol="BTC/USDT",
            timeframe="1h",
            first_bar=requested_start - timedelta(hours=1),  # Before requested start
            last_bar=requested_end + timedelta(hours=1),  # After requested end
            total_bars=720,
            requested_start=requested_start,
            requested_end=requested_end,
        )

        assert availability.is_complete is True

    def test_is_complete_false_no_data(self):
        """Test is_complete property when no data exists."""
        availability = DataAvailability(
            exchange="okx",
            symbol="BTC/USDT",
            timeframe="1h",
            first_bar=None,
            last_bar=None,
            total_bars=0,
            requested_start=datetime.now(UTC) - timedelta(days=30),
            requested_end=datetime.now(UTC),
        )

        assert availability.is_complete is False

    def test_is_complete_false_partial_data(self):
        """Test is_complete property when data is partial."""
        requested_start = datetime.now(UTC) - timedelta(days=30)
        requested_end = datetime.now(UTC)

        availability = DataAvailability(
            exchange="okx",
            symbol="BTC/USDT",
            timeframe="1h",
            first_bar=requested_start + timedelta(days=5),  # Starts after requested
            last_bar=requested_end,
            total_bars=600,
            requested_start=requested_start,
            requested_end=requested_end,
        )

        assert availability.is_complete is False

    def test_to_dict(self):
        """Test to_dict method."""
        first_bar = datetime.now(UTC) - timedelta(days=30)
        last_bar = datetime.now(UTC)
        requested_start = first_bar
        requested_end = last_bar

        availability = DataAvailability(
            exchange="okx",
            symbol="BTC/USDT",
            timeframe="1h",
            first_bar=first_bar,
            last_bar=last_bar,
            total_bars=720,
            requested_start=requested_start,
            requested_end=requested_end,
        )

        result = availability.to_dict()

        assert result["exchange"] == "okx"
        assert result["symbol"] == "BTC/USDT"
        assert result["timeframe"] == "1h"
        assert result["total_bars"] == 720
        assert result["has_data"] is True
        assert result["is_complete"] is True
        assert result["first_bar"] == first_bar.isoformat()
        assert result["last_bar"] == last_bar.isoformat()

    def test_to_dict_no_data(self):
        """Test to_dict method with no data."""
        requested_start = datetime.now(UTC) - timedelta(days=30)
        requested_end = datetime.now(UTC)

        availability = DataAvailability(
            exchange="okx",
            symbol="BTC/USDT",
            timeframe="1h",
            first_bar=None,
            last_bar=None,
            total_bars=0,
            requested_start=requested_start,
            requested_end=requested_end,
        )

        result = availability.to_dict()

        assert result["first_bar"] is None
        assert result["last_bar"] is None
        assert result["has_data"] is False


class TestDataLoader:
    """Tests for DataLoader class."""

    @pytest.mark.asyncio
    async def test_count_bars(self, mock_session):
        """Test counting bars in a time range."""
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 720
        mock_session.execute.return_value = mock_result

        loader = DataLoader(mock_session)
        count = await loader.count_bars(
            exchange="okx",
            symbol="BTC/USDT",
            timeframe="1h",
            start=datetime.now(UTC) - timedelta(days=30),
            end=datetime.now(UTC),
        )

        assert count == 720
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_data_availability_with_data(self, mock_session):
        """Test checking data availability when data exists."""
        first_bar = datetime.now(UTC) - timedelta(days=30)
        last_bar = datetime.now(UTC)

        # Mock count query
        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 720

        # Mock first bar query
        mock_first_result = MagicMock()
        mock_first_result.scalar_one_or_none.return_value = first_bar

        # Mock last bar query
        mock_last_result = MagicMock()
        mock_last_result.scalar_one_or_none.return_value = last_bar

        mock_session.execute.side_effect = [
            mock_count_result,
            mock_first_result,
            mock_last_result,
        ]

        loader = DataLoader(mock_session)
        availability = await loader.check_data_availability(
            exchange="okx",
            symbol="BTC/USDT",
            timeframe="1h",
            start=first_bar,
            end=last_bar,
        )

        assert availability.has_data is True
        assert availability.total_bars == 720
        assert availability.first_bar == first_bar
        assert availability.last_bar == last_bar

    @pytest.mark.asyncio
    async def test_check_data_availability_no_data(self, mock_session):
        """Test checking data availability when no data exists."""
        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 0
        mock_session.execute.return_value = mock_count_result

        loader = DataLoader(mock_session)
        availability = await loader.check_data_availability(
            exchange="okx",
            symbol="BTC/USDT",
            timeframe="1h",
            start=datetime.now(UTC) - timedelta(days=30),
            end=datetime.now(UTC),
        )

        assert availability.has_data is False
        assert availability.total_bars == 0
        assert availability.first_bar is None
        assert availability.last_bar is None

    @pytest.mark.asyncio
    async def test_load_bars_empty(self, mock_session):
        """Test loading bars when none exist."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        loader = DataLoader(mock_session)
        bars = []
        async for bar in loader.load_bars(
            exchange="okx",
            symbol="BTC/USDT",
            timeframe="1h",
            start=datetime.now(UTC) - timedelta(days=30),
            end=datetime.now(UTC),
        ):
            bars.append(bar)

        assert len(bars) == 0

    @pytest.mark.asyncio
    async def test_load_bars_single_batch(self, mock_session, mock_kline):
        """Test loading bars in a single batch."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_kline]
        mock_session.execute.return_value = mock_result

        loader = DataLoader(mock_session)
        bars = []
        async for bar in loader.load_bars(
            exchange="okx",
            symbol="BTC/USDT",
            timeframe="1h",
            start=datetime.now(UTC) - timedelta(days=30),
            end=datetime.now(UTC),
            batch_size=1000,
        ):
            bars.append(bar)

        assert len(bars) == 1
        assert bars[0].symbol == "BTC/USDT"
        assert bars[0].open == Decimal("50000")

    @pytest.mark.asyncio
    async def test_load_bars_multiple_batches(self, mock_session, mock_kline):
        """Test loading bars across multiple batches."""
        # Create two klines
        mock_kline2 = MagicMock()
        mock_kline2.time = datetime.now(UTC) + timedelta(hours=1)
        mock_kline2.symbol = "BTC/USDT"
        mock_kline2.open = Decimal("50500")
        mock_kline2.high = Decimal("51500")
        mock_kline2.low = Decimal("50000")
        mock_kline2.close = Decimal("51000")
        mock_kline2.volume = Decimal("150")

        # First batch returns 1 kline (batch_size=1), second returns 1, third returns empty
        mock_result1 = MagicMock()
        mock_result1.scalars.return_value.all.return_value = [mock_kline]
        mock_result2 = MagicMock()
        mock_result2.scalars.return_value.all.return_value = [mock_kline2]
        mock_result3 = MagicMock()
        mock_result3.scalars.return_value.all.return_value = []

        mock_session.execute.side_effect = [mock_result1, mock_result2, mock_result3]

        loader = DataLoader(mock_session)
        bars = []
        async for bar in loader.load_bars(
            exchange="okx",
            symbol="BTC/USDT",
            timeframe="1h",
            start=datetime.now(UTC) - timedelta(days=30),
            end=datetime.now(UTC),
            batch_size=1,
        ):
            bars.append(bar)

        assert len(bars) == 2

    @pytest.mark.asyncio
    async def test_get_available_symbols(self, mock_session):
        """Test getting available symbols."""
        mock_row = MagicMock()
        mock_row.exchange = "okx"
        mock_row.symbol = "BTC/USDT"
        mock_row.timeframe = "1h"
        mock_row.bar_count = 720
        mock_row.first_bar = datetime.now(UTC) - timedelta(days=30)
        mock_row.last_bar = datetime.now(UTC)

        mock_result = MagicMock()
        mock_result.all.return_value = [mock_row]
        mock_session.execute.return_value = mock_result

        loader = DataLoader(mock_session)
        symbols = await loader.get_available_symbols()

        assert len(symbols) == 1
        assert symbols[0]["exchange"] == "okx"
        assert symbols[0]["symbol"] == "BTC/USDT"
        assert symbols[0]["bar_count"] == 720

    @pytest.mark.asyncio
    async def test_get_available_symbols_with_filters(self, mock_session):
        """Test getting available symbols with filters."""
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute.return_value = mock_result

        loader = DataLoader(mock_session)
        symbols = await loader.get_available_symbols(exchange="okx", timeframe="1h")

        assert len(symbols) == 0
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_available_symbols_empty(self, mock_session):
        """Test getting available symbols when none exist."""
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute.return_value = mock_result

        loader = DataLoader(mock_session)
        symbols = await loader.get_available_symbols()

        assert len(symbols) == 0
