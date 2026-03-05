"""
Integration tests for Data Download Service.

Tests upsert functionality with real database:
- Inserting candles into Kline table
- Upsert idempotency (same data written twice)
- Upsert overwrites existing data correctly
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import and_, func, select

from squant.infra.exchange.types import Candlestick
from squant.models.market import Kline
from squant.services.data_download import DataDownloadService


def _make_candle(hour: int, price: Decimal = Decimal("42000")) -> Candlestick:
    """Helper to create a test candle."""
    return Candlestick(
        timestamp=datetime(2024, 1, 1, hour, 0, 0, tzinfo=UTC),
        open=price,
        high=price + Decimal("500"),
        low=price - Decimal("500"),
        close=price + Decimal("200"),
        volume=Decimal("100"),
    )


class TestUpsertCandles:
    """Tests for _upsert_candles with real database."""

    @pytest.mark.asyncio
    async def test_insert_new_candles(self, db_session):
        """Test inserting candles into empty table."""
        candles = [_make_candle(h) for h in range(5)]

        await DataDownloadService._upsert_candles(
            db_session, "binance", "BTC/USDT", "1h", candles
        )
        await db_session.commit()

        # Verify data was written
        result = await db_session.execute(
            select(func.count()).select_from(Kline).where(
                and_(
                    Kline.exchange == "binance",
                    Kline.symbol == "BTC/USDT",
                    Kline.timeframe == "1h",
                )
            )
        )
        count = result.scalar_one()
        assert count == 5

    @pytest.mark.asyncio
    async def test_upsert_idempotency(self, db_session):
        """Test that writing same candles twice doesn't create duplicates."""
        candles = [_make_candle(h) for h in range(3)]

        # Write once
        await DataDownloadService._upsert_candles(
            db_session, "binance", "BTC/USDT", "1h", candles
        )
        await db_session.commit()

        # Write again (same data)
        await DataDownloadService._upsert_candles(
            db_session, "binance", "BTC/USDT", "1h", candles
        )
        await db_session.commit()

        # Should still have 3 rows, not 6
        result = await db_session.execute(
            select(func.count()).select_from(Kline).where(
                and_(
                    Kline.exchange == "binance",
                    Kline.symbol == "BTC/USDT",
                    Kline.timeframe == "1h",
                )
            )
        )
        count = result.scalar_one()
        assert count == 3

    @pytest.mark.asyncio
    async def test_upsert_updates_existing_data(self, db_session):
        """Test that upsert overwrites OHLCV values for existing keys."""
        original = [_make_candle(0, price=Decimal("40000"))]
        updated = [_make_candle(0, price=Decimal("50000"))]

        # Write original
        await DataDownloadService._upsert_candles(
            db_session, "binance", "BTC/USDT", "1h", original
        )
        await db_session.commit()

        # Write updated
        await DataDownloadService._upsert_candles(
            db_session, "binance", "BTC/USDT", "1h", updated
        )
        await db_session.commit()

        # Verify updated values
        result = await db_session.execute(
            select(Kline).where(
                and_(
                    Kline.exchange == "binance",
                    Kline.symbol == "BTC/USDT",
                    Kline.timeframe == "1h",
                    Kline.time == datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
                )
            )
        )
        kline = result.scalar_one()
        assert kline.open == Decimal("50000")

    @pytest.mark.asyncio
    async def test_different_symbols_isolated(self, db_session):
        """Test that different symbols don't interfere."""
        btc_candles = [_make_candle(0, Decimal("42000"))]
        eth_candles = [_make_candle(0, Decimal("2500"))]

        await DataDownloadService._upsert_candles(
            db_session, "binance", "BTC/USDT", "1h", btc_candles
        )
        await DataDownloadService._upsert_candles(
            db_session, "binance", "ETH/USDT", "1h", eth_candles
        )
        await db_session.commit()

        # Verify BTC
        result = await db_session.execute(
            select(Kline).where(
                and_(
                    Kline.exchange == "binance",
                    Kline.symbol == "BTC/USDT",
                )
            )
        )
        btc = result.scalar_one()
        assert btc.open == Decimal("42000")

        # Verify ETH
        result = await db_session.execute(
            select(Kline).where(
                and_(
                    Kline.exchange == "binance",
                    Kline.symbol == "ETH/USDT",
                )
            )
        )
        eth = result.scalar_one()
        assert eth.open == Decimal("2500")

    @pytest.mark.asyncio
    async def test_empty_candles_noop(self, db_session):
        """Test that empty candle list is a no-op."""
        await DataDownloadService._upsert_candles(
            db_session, "binance", "BTC/USDT", "1h", []
        )
        await db_session.commit()

        result = await db_session.execute(
            select(func.count()).select_from(Kline).where(
                Kline.exchange == "binance",
            )
        )
        count = result.scalar_one()
        assert count == 0
