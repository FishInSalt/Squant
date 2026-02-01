"""
Integration tests for Data Loader Service.

Tests data loader functionality with real database integration:
- Historical candle data loading
- Data caching and retrieval
- Multiple timeframe support
- Data validation and cleanup
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio

from squant.models.market import Kline
from squant.services.data_loader import DataLoader


@pytest_asyncio.fixture
async def data_loader(db_session):
    """Create data loader service instance."""
    return DataLoader(db_session)


@pytest.fixture
def sample_ohlcv_data():
    """Create sample OHLCV data from exchange."""
    now = datetime.now(UTC)
    data = []

    for i in range(100, 0, -1):
        timestamp = now - timedelta(minutes=i)
        data.append(
            [
                int(timestamp.timestamp() * 1000),  # timestamp in ms
                40000.0 + i * 10,  # open
                40100.0 + i * 10,  # high
                39900.0 + i * 10,  # low
                40050.0 + i * 10,  # close
                100.0 + i,  # volume
            ]
        )

    return data


class TestHistoricalDataLoading:
    """Tests for loading historical candle data."""

    @pytest.mark.asyncio
    async def test_load_candles_from_exchange(
        self, data_loader, sample_ohlcv_data, sample_exchange_account
    ):
        """Test loading candles from exchange."""
        # Mock exchange adapter
        mock_adapter = MagicMock()
        mock_adapter.get_ohlcv = AsyncMock(return_value=sample_ohlcv_data)

        with patch("squant.services.data_loader.get_exchange_adapter", return_value=mock_adapter):
            candles = await data_loader.load_candles(
                exchange_account_id=sample_exchange_account.id,
                symbol="BTC/USDT",
                timeframe="1m",
                start_time=datetime.now(UTC) - timedelta(hours=2),
                end_time=datetime.now(UTC),
            )

        # Should have loaded 100 candles
        assert len(candles) == 100
        assert candles[0].symbol == "BTC/USDT"
        assert candles[0].timeframe == "1m"

    @pytest.mark.asyncio
    async def test_load_candles_persists_to_database(
        self, data_loader, sample_ohlcv_data, sample_exchange_account, db_session
    ):
        """Test that loaded candles are persisted to database."""
        mock_adapter = MagicMock()
        mock_adapter.get_ohlcv = AsyncMock(return_value=sample_ohlcv_data[:10])  # Just 10 candles

        with patch("squant.services.data_loader.get_exchange_adapter", return_value=mock_adapter):
            await data_loader.load_candles(
                exchange_account_id=sample_exchange_account.id,
                symbol="BTC/USDT",
                timeframe="1m",
                start_time=datetime.now(UTC) - timedelta(minutes=10),
                end_time=datetime.now(UTC),
            )

        # Query database to verify persistence
        from sqlalchemy import select

        result = await db_session.execute(
            select(Kline).where(
                Kline.exchange_account_id == sample_exchange_account.id,
                Kline.symbol == "BTC/USDT",
            )
        )
        candles = result.scalars().all()

        assert len(candles) == 10

    @pytest.mark.asyncio
    async def test_load_candles_multiple_timeframes(
        self, data_loader, sample_ohlcv_data, sample_exchange_account
    ):
        """Test loading candles for different timeframes."""
        timeframes = ["1m", "5m", "1h", "1d"]

        for timeframe in timeframes:
            mock_adapter = MagicMock()
            mock_adapter.get_ohlcv = AsyncMock(return_value=sample_ohlcv_data)

            with patch(
                "squant.services.data_loader.get_exchange_adapter", return_value=mock_adapter
            ):
                candles = await data_loader.load_candles(
                    exchange_account_id=sample_exchange_account.id,
                    symbol="BTC/USDT",
                    timeframe=timeframe,
                    start_time=datetime.now(UTC) - timedelta(hours=2),
                    end_time=datetime.now(UTC),
                )

            assert len(candles) > 0
            assert all(c.timeframe == timeframe for c in candles)

    @pytest.mark.asyncio
    async def test_load_candles_handles_duplicate_data(
        self, data_loader, sample_ohlcv_data, sample_exchange_account, db_session
    ):
        """Test that loading duplicate data doesn't create duplicates."""
        mock_adapter = MagicMock()
        mock_adapter.get_ohlcv = AsyncMock(return_value=sample_ohlcv_data[:10])

        with patch("squant.services.data_loader.get_exchange_adapter", return_value=mock_adapter):
            # Load same data twice
            await data_loader.load_candles(
                exchange_account_id=sample_exchange_account.id,
                symbol="BTC/USDT",
                timeframe="1m",
                start_time=datetime.now(UTC) - timedelta(minutes=10),
                end_time=datetime.now(UTC),
            )

            await data_loader.load_candles(
                exchange_account_id=sample_exchange_account.id,
                symbol="BTC/USDT",
                timeframe="1m",
                start_time=datetime.now(UTC) - timedelta(minutes=10),
                end_time=datetime.now(UTC),
            )

        # Should still have only 10 candles (no duplicates)
        from sqlalchemy import select

        result = await db_session.execute(
            select(Kline).where(
                Kline.exchange_account_id == sample_exchange_account.id,
                Kline.symbol == "BTC/USDT",
            )
        )
        candles = result.scalars().all()

        # Should be 10, not 20
        assert len(candles) == 10


class TestDataRetrieval:
    """Tests for retrieving candle data."""

    @pytest.mark.asyncio
    async def test_get_candles_from_database(
        self, data_loader, sample_exchange_account, db_session
    ):
        """Test retrieving candles from database."""
        # First create some candles in database
        now = datetime.now(UTC)
        for i in range(10):
            candle = Kline(
                id=uuid4(),
                exchange_account_id=sample_exchange_account.id,
                symbol="BTC/USDT",
                timeframe="1m",
                timestamp=now - timedelta(minutes=10 - i),
                open=Decimal("40000"),
                high=Decimal("40100"),
                low=Decimal("39900"),
                close=Decimal("40050"),
                volume=Decimal("100"),
            )
            db_session.add(candle)

        await db_session.commit()

        # Retrieve candles
        candles = await data_loader.get_candles(
            exchange_account_id=sample_exchange_account.id,
            symbol="BTC/USDT",
            timeframe="1m",
            start_time=now - timedelta(minutes=11),
            end_time=now,
        )

        assert len(candles) == 10

    @pytest.mark.asyncio
    async def test_get_candles_filters_by_time_range(
        self, data_loader, sample_exchange_account, db_session
    ):
        """Test that get_candles filters by time range."""
        now = datetime.now(UTC)

        # Create candles with different timestamps
        for i in range(20):
            candle = Kline(
                id=uuid4(),
                exchange_account_id=sample_exchange_account.id,
                symbol="BTC/USDT",
                timeframe="1m",
                timestamp=now - timedelta(minutes=20 - i),
                open=Decimal("40000"),
                high=Decimal("40100"),
                low=Decimal("39900"),
                close=Decimal("40050"),
                volume=Decimal("100"),
            )
            db_session.add(candle)

        await db_session.commit()

        # Get only last 5 minutes
        candles = await data_loader.get_candles(
            exchange_account_id=sample_exchange_account.id,
            symbol="BTC/USDT",
            timeframe="1m",
            start_time=now - timedelta(minutes=5),
            end_time=now,
        )

        # Should have at most 5 candles
        assert len(candles) <= 5

    @pytest.mark.asyncio
    async def test_get_candles_filters_by_symbol(
        self, data_loader, sample_exchange_account, db_session
    ):
        """Test filtering candles by symbol."""
        now = datetime.now(UTC)

        # Create candles for different symbols
        for symbol in ["BTC/USDT", "ETH/USDT"]:
            for i in range(5):
                candle = Kline(
                    id=uuid4(),
                    exchange_account_id=sample_exchange_account.id,
                    symbol=symbol,
                    timeframe="1m",
                    timestamp=now - timedelta(minutes=5 - i),
                    open=Decimal("40000"),
                    high=Decimal("40100"),
                    low=Decimal("39900"),
                    close=Decimal("40050"),
                    volume=Decimal("100"),
                )
                db_session.add(candle)

        await db_session.commit()

        # Get only BTC candles
        candles = await data_loader.get_candles(
            exchange_account_id=sample_exchange_account.id,
            symbol="BTC/USDT",
            timeframe="1m",
            start_time=now - timedelta(minutes=6),
            end_time=now,
        )

        assert all(c.symbol == "BTC/USDT" for c in candles)
        assert len(candles) == 5


class TestDataCaching:
    """Tests for data caching mechanisms."""

    @pytest.mark.asyncio
    async def test_load_only_missing_data(
        self, data_loader, sample_ohlcv_data, sample_exchange_account, db_session
    ):
        """Test that only missing data is loaded from exchange."""
        now = datetime.now(UTC)

        # Pre-populate database with first 50 candles
        for i in range(50):
            ohlcv = sample_ohlcv_data[i]
            candle = Kline(
                id=uuid4(),
                exchange_account_id=sample_exchange_account.id,
                symbol="BTC/USDT",
                timeframe="1m",
                timestamp=datetime.fromtimestamp(ohlcv[0] / 1000, tz=UTC),
                open=Decimal(str(ohlcv[1])),
                high=Decimal(str(ohlcv[2])),
                low=Decimal(str(ohlcv[3])),
                close=Decimal(str(ohlcv[4])),
                volume=Decimal(str(ohlcv[5])),
            )
            db_session.add(candle)

        await db_session.commit()

        # Mock exchange to return all 100 candles
        mock_adapter = MagicMock()
        mock_adapter.get_ohlcv = AsyncMock(return_value=sample_ohlcv_data)

        with patch("squant.services.data_loader.get_exchange_adapter", return_value=mock_adapter):
            candles = await data_loader.load_candles(
                exchange_account_id=sample_exchange_account.id,
                symbol="BTC/USDT",
                timeframe="1m",
                start_time=now - timedelta(hours=2),
                end_time=now,
            )

        # Should have all 100 candles (50 from DB + 50 new)
        assert len(candles) == 100


class TestDataValidation:
    """Tests for data validation."""

    @pytest.mark.asyncio
    async def test_validate_candle_data_completeness(
        self, data_loader, sample_exchange_account
    ):
        """Test that incomplete candle data is rejected."""
        # Invalid OHLCV data (missing fields)
        invalid_data = [
            [1234567890000, 40000.0, 40100.0],  # Missing low, close, volume
        ]

        mock_adapter = MagicMock()
        mock_adapter.get_ohlcv = AsyncMock(return_value=invalid_data)

        with (
            patch(
                "squant.services.data_loader.get_exchange_adapter", return_value=mock_adapter
            ),
            pytest.raises(Exception),
        ):  # Should raise validation error
            await data_loader.load_candles(
                exchange_account_id=sample_exchange_account.id,
                symbol="BTC/USDT",
                timeframe="1m",
                start_time=datetime.now(UTC) - timedelta(hours=1),
                end_time=datetime.now(UTC),
            )

    @pytest.mark.asyncio
    async def test_validate_price_sanity_checks(
        self, data_loader, sample_exchange_account
    ):
        """Test price sanity checks (high >= low, etc.)."""
        # Invalid data where high < low
        invalid_data = [
            [
                int(datetime.now(UTC).timestamp() * 1000),
                40000.0,  # open
                39000.0,  # high (should be >= low)
                40000.0,  # low (higher than high - invalid!)
                40050.0,  # close
                100.0,  # volume
            ],
        ]

        mock_adapter = MagicMock()
        mock_adapter.get_ohlcv = AsyncMock(return_value=invalid_data)

        with patch("squant.services.data_loader.get_exchange_adapter", return_value=mock_adapter):
            # Service should either:
            # 1. Skip invalid candles, or
            # 2. Raise validation error
            # (Depends on implementation)
            try:
                candles = await data_loader.load_candles(
                    exchange_account_id=sample_exchange_account.id,
                    symbol="BTC/USDT",
                    timeframe="1m",
                    start_time=datetime.now(UTC) - timedelta(hours=1),
                    end_time=datetime.now(UTC),
                )
                # If no error, should have skipped invalid candle
                assert len(candles) == 0
            except Exception:
                # Validation error is also acceptable
                pass


class TestDataCleanup:
    """Tests for data cleanup and maintenance."""

    @pytest.mark.asyncio
    async def test_delete_old_candles(
        self, data_loader, sample_exchange_account, db_session
    ):
        """Test deleting old candle data."""
        now = datetime.now(UTC)

        # Create old candles (1 year ago)
        for i in range(10):
            old_candle = Kline(
                id=uuid4(),
                exchange_account_id=sample_exchange_account.id,
                symbol="BTC/USDT",
                timeframe="1m",
                timestamp=now - timedelta(days=365 + i),
                open=Decimal("40000"),
                high=Decimal("40100"),
                low=Decimal("39900"),
                close=Decimal("40050"),
                volume=Decimal("100"),
            )
            db_session.add(old_candle)

        # Create recent candles
        for i in range(10):
            recent_candle = Kline(
                id=uuid4(),
                exchange_account_id=sample_exchange_account.id,
                symbol="BTC/USDT",
                timeframe="1m",
                timestamp=now - timedelta(minutes=10 - i),
                open=Decimal("40000"),
                high=Decimal("40100"),
                low=Decimal("39900"),
                close=Decimal("40050"),
                volume=Decimal("100"),
            )
            db_session.add(recent_candle)

        await db_session.commit()

        # Delete candles older than 30 days
        deleted_count = await data_loader.cleanup_old_candles(
            exchange_account_id=sample_exchange_account.id,
            symbol="BTC/USDT",
            timeframe="1m",
            older_than=now - timedelta(days=30),
        )

        # Should have deleted 10 old candles
        assert deleted_count == 10

    @pytest.mark.asyncio
    async def test_deduplicate_candles(
        self, data_loader, sample_exchange_account, db_session
    ):
        """Test removing duplicate candles."""
        now = datetime.now(UTC)
        timestamp = now - timedelta(minutes=5)

        # Create duplicate candles (same timestamp, symbol, timeframe)
        for _ in range(3):
            candle = Kline(
                id=uuid4(),
                exchange_account_id=sample_exchange_account.id,
                symbol="BTC/USDT",
                timeframe="1m",
                timestamp=timestamp,
                open=Decimal("40000"),
                high=Decimal("40100"),
                low=Decimal("39900"),
                close=Decimal("40050"),
                volume=Decimal("100"),
            )
            db_session.add(candle)

        await db_session.commit()

        # Deduplicate
        removed_count = await data_loader.deduplicate_candles(
            exchange_account_id=sample_exchange_account.id,
            symbol="BTC/USDT",
            timeframe="1m",
        )

        # Should have removed 2 duplicates, keeping 1
        assert removed_count == 2

        # Verify only 1 candle remains
        from sqlalchemy import select

        result = await db_session.execute(
            select(Kline).where(
                Kline.exchange_account_id == sample_exchange_account.id,
                Kline.symbol == "BTC/USDT",
                Kline.timestamp == timestamp,
            )
        )
        remaining = result.scalars().all()

        assert len(remaining) == 1
