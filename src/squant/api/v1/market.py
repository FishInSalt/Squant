"""Market data API endpoints."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query

from squant.api.deps import Exchange
from squant.api.utils import ApiResponse, handle_exchange_error
from squant.config import get_settings
from squant.infra.exchange import TimeFrame
from squant.infra.exchange.ccxt.types import SUPPORTED_EXCHANGES
from squant.schemas.exchange import (
    CandlestickItem,
    CandlestickResponse,
    TickerResponse,
)
from squant.websocket.manager import get_stream_manager

logger = logging.getLogger(__name__)

router = APIRouter()

# Timeframe durations in milliseconds (local copy to avoid cross-layer dependency)
TIMEFRAME_MS: dict[str, int] = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
    "1w": 604_800_000,
}

# Runtime storage for current exchange (single-user system)
_current_exchange: str = get_settings().default_exchange


class MarketDataCache:
    """TTL cache for market data to reduce exchange API calls.

    Caches ticker and market data with configurable time-to-live.
    Expected to reduce exchange API calls by 80-90% for frequently
    requested symbols during active trading hours.
    """

    def __init__(self, ttl_seconds: int = 1) -> None:
        """Initialize cache with TTL in seconds."""
        self._cache: dict[str, tuple[Any, datetime]] = {}
        self._ttl = timedelta(seconds=ttl_seconds)

    def get(self, key: str) -> Any | None:
        """Get cached value if not expired."""
        if key in self._cache:
            value, timestamp = self._cache[key]
            if datetime.now(UTC) - timestamp < self._ttl:
                return value
            # Expired, remove from cache
            del self._cache[key]
        return None

    def set(self, key: str, value: Any) -> None:
        """Cache value with current timestamp."""
        self._cache[key] = (value, datetime.now(UTC))

    def clear(self) -> None:
        """Clear all cached values."""
        self._cache.clear()


# Global cache instance with 1 second TTL
_market_cache = MarketDataCache(ttl_seconds=1)


def get_current_exchange() -> str:
    """Get the current exchange ID."""
    return _current_exchange


@router.get("/exchange")
async def get_exchange_config() -> ApiResponse[dict]:
    """Get current data source exchange configuration.

    Returns the currently active exchange and list of supported exchanges.
    """
    return ApiResponse(
        data={
            "current": _current_exchange,
            "supported": list(SUPPORTED_EXCHANGES),
        }
    )


@router.put("/exchange/{exchange_id}")
async def set_exchange(
    exchange_id: Annotated[str, Path(description="Exchange ID (okx, binance, bybit)")],
) -> ApiResponse[dict]:
    """Switch data source exchange.

    For single-user system, this dynamically switches the exchange for
    both REST API and WebSocket data sources.
    """
    global _current_exchange

    exchange_id = exchange_id.lower()
    if exchange_id not in SUPPORTED_EXCHANGES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported exchange: {exchange_id}. Supported: {', '.join(SUPPORTED_EXCHANGES)}",
        )

    old_exchange = _current_exchange
    _current_exchange = exchange_id

    logger.info(f"Switching exchange from {old_exchange} to {exchange_id}")

    # Clear market data cache when switching exchanges
    _market_cache.clear()
    logger.debug("Cleared market data cache after exchange switch")

    # Notify WebSocket manager to switch exchange
    try:
        stream_manager = get_stream_manager()
        await stream_manager.switch_exchange(exchange_id)
    except Exception as e:
        logger.warning(f"Failed to switch WebSocket exchange: {e}")
        # Don't fail the request, REST API will still work

    return ApiResponse(
        data={
            "current": exchange_id,
            "previous": old_exchange,
        }
    )


@router.get("/ticker/{symbol:path}", response_model=ApiResponse[TickerResponse])
async def get_ticker(
    exchange: Exchange,
    symbol: Annotated[str, Path(description="Trading pair (e.g., BTC/USDT)")],
) -> ApiResponse[TickerResponse]:
    """Get ticker data for a trading pair.

    Returns the latest price and 24h statistics.
    Cached for 1 second to reduce exchange API calls.
    """
    # Check cache first
    cache_key = f"ticker:{_current_exchange}:{symbol}"
    cached = _market_cache.get(cache_key)
    if cached:
        return ApiResponse(data=cached)

    try:
        ticker = await exchange.get_ticker(symbol)
        data = TickerResponse(
            symbol=ticker.symbol,
            last=ticker.last,
            bid=ticker.bid,
            ask=ticker.ask,
            high_24h=ticker.high_24h,
            low_24h=ticker.low_24h,
            volume_24h=ticker.volume_24h,
            volume_quote_24h=ticker.volume_quote_24h,
            change_24h=ticker.change_24h,
            change_pct_24h=ticker.change_pct_24h,
            timestamp=ticker.timestamp,
        )
        # Cache the result
        _market_cache.set(cache_key, data)
        return ApiResponse(data=data)
    except Exception as e:
        handle_exchange_error(e)


@router.get("/tickers", response_model=ApiResponse[list[TickerResponse]])
async def get_tickers(
    exchange: Exchange,
    symbols: Annotated[
        str | None,
        Query(description="Comma-separated trading pairs (e.g., BTC/USDT,ETH/USDT)"),
    ] = None,
    sort_by: Annotated[
        str | None,
        Query(description="Sort field: volume_quote_24h, volume_24h, change_pct_24h, last"),
    ] = None,
    order: Annotated[
        str,
        Query(description="Sort order: desc (default) or asc"),
    ] = "desc",
    limit: Annotated[
        int | None,
        Query(ge=1, le=500, description="Maximum number of tickers to return"),
    ] = None,
) -> ApiResponse[list[TickerResponse]]:
    """Get ticker data for multiple trading pairs.

    If no symbols specified, returns all available tickers.
    Use sort_by=volume_quote_24h to get hot/popular trading pairs by USDT trading volume.
    Cached for 1 second to reduce exchange API calls.
    """
    # Filter empty strings from split result
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()] if symbols else None

    # Check cache first
    cache_key = f"tickers:{_current_exchange}:{symbols or 'all'}:{sort_by}:{order}:{limit}"
    cached = _market_cache.get(cache_key)
    if cached:
        return ApiResponse(data=cached)

    try:
        tickers = await exchange.get_tickers(symbol_list)

        # Sort tickers if sort_by is specified
        if sort_by:
            sort_fields = {
                "volume_quote_24h": lambda t: t.volume_quote_24h or 0,
                "volume_24h": lambda t: t.volume_24h or 0,
                "change_pct_24h": lambda t: t.change_pct_24h or 0,
                "last": lambda t: t.last or 0,
            }
            if sort_by in sort_fields:
                reverse = order.lower() != "asc"
                tickers = sorted(tickers, key=sort_fields[sort_by], reverse=reverse)

        # Limit results if specified
        if limit:
            tickers = tickers[:limit]

        data = [
            TickerResponse(
                symbol=t.symbol,
                last=t.last,
                bid=t.bid,
                ask=t.ask,
                high_24h=t.high_24h,
                low_24h=t.low_24h,
                volume_24h=t.volume_24h,
                volume_quote_24h=t.volume_quote_24h,
                change_24h=t.change_24h,
                change_pct_24h=t.change_pct_24h,
                timestamp=t.timestamp,
            )
            for t in tickers
        ]
        # Cache the result
        _market_cache.set(cache_key, data)
        return ApiResponse(data=data)
    except Exception as e:
        handle_exchange_error(e)


@router.get("/candles/{symbol:path}", response_model=ApiResponse[CandlestickResponse])
async def get_candles(
    exchange: Exchange,
    symbol: Annotated[str, Path(description="Trading pair (e.g., BTC/USDT)")],
    timeframe: Annotated[
        str,
        Query(description="Time frame: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w"),
    ] = "1h",
    limit: Annotated[int, Query(ge=1, le=300, description="Number of candles")] = 100,
    end_time: Annotated[
        int | None,
        Query(
            ge=0,
            le=32503680000000,
            description="End timestamp in milliseconds. "
            "When provided, fetches candles before this time.",
        ),
    ] = None,
) -> ApiResponse[CandlestickResponse]:
    """Get candlestick (OHLCV) data for a trading pair.

    Returns historical price data in candlestick format.
    When end_time is provided, returns candles before that timestamp
    (useful for scroll-loading historical data).
    """
    # Map string to TimeFrame enum
    tf_map = {
        "1m": TimeFrame.M1,
        "5m": TimeFrame.M5,
        "15m": TimeFrame.M15,
        "30m": TimeFrame.M30,
        "1h": TimeFrame.H1,
        "4h": TimeFrame.H4,
        "1d": TimeFrame.D1,
        "1w": TimeFrame.W1,
    }
    tf = tf_map.get(timeframe)
    if tf is None:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid timeframe: {timeframe}. Valid values: {', '.join(tf_map.keys())}",
        )

    try:
        # When end_time is provided, calculate start_time to fetch historical candles
        start_time: int | None = None
        if end_time is not None:
            tf_ms = TIMEFRAME_MS[timeframe]
            start_time = end_time - limit * tf_ms

        candles = await exchange.get_candlesticks(
            symbol, tf, limit=limit, start_time=start_time
        )

        # Filter out candles at or after end_time
        if end_time is not None:
            end_dt = datetime.fromtimestamp(end_time / 1000, tz=UTC)
            candles = [c for c in candles if c.timestamp < end_dt]

        data = CandlestickResponse(
            symbol=symbol,
            timeframe=timeframe,
            candles=[
                CandlestickItem(
                    timestamp=c.timestamp,
                    open=c.open,
                    high=c.high,
                    low=c.low,
                    close=c.close,
                    volume=c.volume,
                )
                for c in candles
            ],
        )
        return ApiResponse(data=data)
    except Exception as e:
        handle_exchange_error(e)
