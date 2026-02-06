"""Historical data loader for backtesting.

Loads OHLCV data from the Kline TimescaleDB hypertable and converts
to Bar objects for the backtest engine.
"""

from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from squant.engine.backtest.types import Bar
from squant.models.market import Kline

# Mapping from timeframe string to its duration.
# Bar timestamps represent the START of the period, so the bar at time T
# covers the interval [T, T + duration).
_TIMEFRAME_DURATIONS: dict[str, timedelta] = {
    "1m": timedelta(minutes=1),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "30m": timedelta(minutes=30),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
    "1w": timedelta(weeks=1),
}


class DataAvailability:
    """Information about data availability for a symbol/timeframe."""

    def __init__(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        first_bar: datetime | None,
        last_bar: datetime | None,
        total_bars: int,
        requested_start: datetime,
        requested_end: datetime,
    ):
        self.exchange = exchange
        self.symbol = symbol
        self.timeframe = timeframe
        self.first_bar = first_bar
        self.last_bar = last_bar
        self.total_bars = total_bars
        self.requested_start = requested_start
        self.requested_end = requested_end

    @property
    def has_data(self) -> bool:
        """Check if any data is available."""
        return self.total_bars > 0

    @property
    def is_complete(self) -> bool:
        """Check if data covers the full requested range.

        Bar timestamps represent the START of the period.  A bar at time T
        with timeframe duration D covers the interval [T, T+D).  Therefore,
        data is complete when ``last_bar + duration >= requested_end``, not
        simply ``last_bar >= requested_end``.
        """
        if not self.has_data:
            return False
        if self.first_bar is None or self.last_bar is None:
            return False
        duration = _TIMEFRAME_DURATIONS.get(self.timeframe, timedelta(0))
        return (
            self.first_bar <= self.requested_start
            and self.last_bar + duration >= self.requested_end
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "exchange": self.exchange,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "first_bar": self.first_bar.isoformat() if self.first_bar else None,
            "last_bar": self.last_bar.isoformat() if self.last_bar else None,
            "total_bars": self.total_bars,
            "requested_start": self.requested_start.isoformat(),
            "requested_end": self.requested_end.isoformat(),
            "has_data": self.has_data,
            "is_complete": self.is_complete,
        }


class DataLoader:
    """Loads historical bar data from the database.

    Provides methods to:
    - Stream bars as an async iterator
    - Count available bars
    - Check data availability
    """

    def __init__(self, session: AsyncSession):
        """Initialize data loader.

        Args:
            session: Database session.
        """
        self.session = session

    async def load_bars(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        batch_size: int = 1000,
    ) -> AsyncIterator[Bar]:
        """Load bars as an async iterator.

        Streams bars from the database in batches to avoid loading
        all data into memory at once.

        Args:
            exchange: Exchange name.
            symbol: Trading symbol.
            timeframe: Candle timeframe.
            start: Start datetime (inclusive).
            end: End datetime (inclusive).
            batch_size: Number of bars to fetch per batch.

        Yields:
            Bar objects in chronological order.
        """
        offset = 0

        while True:
            # Build query for this batch
            stmt = (
                select(Kline)
                .where(
                    and_(
                        Kline.exchange == exchange,
                        Kline.symbol == symbol,
                        Kline.timeframe == timeframe,
                        Kline.time >= start,
                        Kline.time <= end,
                    )
                )
                .order_by(Kline.time.asc())
                .offset(offset)
                .limit(batch_size)
            )

            result = await self.session.execute(stmt)
            klines = result.scalars().all()

            if not klines:
                break

            for kline in klines:
                yield Bar(
                    time=kline.time,
                    symbol=kline.symbol,
                    open=kline.open,
                    high=kline.high,
                    low=kline.low,
                    close=kline.close,
                    volume=kline.volume,
                )

            # Check if we got a full batch (more data available)
            if len(klines) < batch_size:
                break

            offset += batch_size

    async def count_bars(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> int:
        """Count available bars in a time range.

        Args:
            exchange: Exchange name.
            symbol: Trading symbol.
            timeframe: Candle timeframe.
            start: Start datetime.
            end: End datetime.

        Returns:
            Number of available bars.
        """
        stmt = (
            select(func.count())
            .select_from(Kline)
            .where(
                and_(
                    Kline.exchange == exchange,
                    Kline.symbol == symbol,
                    Kline.timeframe == timeframe,
                    Kline.time >= start,
                    Kline.time <= end,
                )
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def check_data_availability(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> DataAvailability:
        """Check data availability for a backtest.

        Args:
            exchange: Exchange name.
            symbol: Trading symbol.
            timeframe: Candle timeframe.
            start: Requested start datetime.
            end: Requested end datetime.

        Returns:
            DataAvailability with information about available data.
        """
        # Get total count
        count = await self.count_bars(exchange, symbol, timeframe, start, end)

        # Get first and last bar times for this symbol/timeframe in database
        # NOTE: We query the ACTUAL data range without filtering by requested range,
        # because is_complete needs to check if data covers the requested range.
        first_bar = None
        last_bar = None

        if count > 0:
            # First bar in database for this symbol (not filtered by requested range)
            stmt = (
                select(Kline.time)
                .where(
                    and_(
                        Kline.exchange == exchange,
                        Kline.symbol == symbol,
                        Kline.timeframe == timeframe,
                    )
                )
                .order_by(Kline.time.asc())
                .limit(1)
            )
            result = await self.session.execute(stmt)
            first_bar = result.scalar_one_or_none()

            # Last bar in database for this symbol (not filtered by requested range)
            stmt = (
                select(Kline.time)
                .where(
                    and_(
                        Kline.exchange == exchange,
                        Kline.symbol == symbol,
                        Kline.timeframe == timeframe,
                    )
                )
                .order_by(Kline.time.desc())
                .limit(1)
            )
            result = await self.session.execute(stmt)
            last_bar = result.scalar_one_or_none()

        return DataAvailability(
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe,
            first_bar=first_bar,
            last_bar=last_bar,
            total_bars=count,
            requested_start=start,
            requested_end=end,
        )

    async def get_available_symbols(
        self,
        exchange: str | None = None,
        timeframe: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get list of available symbols with data.

        Args:
            exchange: Optional exchange filter.
            timeframe: Optional timeframe filter.

        Returns:
            List of dicts with exchange, symbol, timeframe, and bar count.
        """
        # Build query to get distinct combinations with counts
        stmt = select(
            Kline.exchange,
            Kline.symbol,
            Kline.timeframe,
            func.count().label("bar_count"),
            func.min(Kline.time).label("first_bar"),
            func.max(Kline.time).label("last_bar"),
        ).group_by(Kline.exchange, Kline.symbol, Kline.timeframe)

        if exchange:
            stmt = stmt.where(Kline.exchange == exchange)
        if timeframe:
            stmt = stmt.where(Kline.timeframe == timeframe)

        stmt = stmt.order_by(Kline.exchange, Kline.symbol)

        result = await self.session.execute(stmt)
        rows = result.all()

        return [
            {
                "exchange": row.exchange,
                "symbol": row.symbol,
                "timeframe": row.timeframe,
                "bar_count": row.bar_count,
                "first_bar": row.first_bar.isoformat() if row.first_bar else None,
                "last_bar": row.last_bar.isoformat() if row.last_bar else None,
            }
            for row in rows
        ]
