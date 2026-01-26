"""Market data API endpoints."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query

from squant.api.deps import OKXExchange
from squant.api.utils import ApiResponse, handle_exchange_error
from squant.infra.exchange import TimeFrame
from squant.schemas.exchange import (
    CandlestickItem,
    CandlestickResponse,
    TickerResponse,
)

router = APIRouter()


@router.get("/ticker/{symbol:path}", response_model=ApiResponse[TickerResponse])
async def get_ticker(
    exchange: OKXExchange,
    symbol: Annotated[str, Path(description="Trading pair (e.g., BTC/USDT)")],
) -> ApiResponse[TickerResponse]:
    """Get ticker data for a trading pair.

    Returns the latest price and 24h statistics.
    """
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
            timestamp=ticker.timestamp,
        )
        return ApiResponse(data=data)
    except Exception as e:
        handle_exchange_error(e)


@router.get("/tickers", response_model=ApiResponse[list[TickerResponse]])
async def get_tickers(
    exchange: OKXExchange,
    symbols: Annotated[
        str | None,
        Query(description="Comma-separated trading pairs (e.g., BTC/USDT,ETH/USDT)"),
    ] = None,
) -> ApiResponse[list[TickerResponse]]:
    """Get ticker data for multiple trading pairs.

    If no symbols specified, returns all available tickers.
    """
    try:
        # Filter empty strings from split result
        symbol_list = (
            [s.strip() for s in symbols.split(",") if s.strip()] if symbols else None
        )
        tickers = await exchange.get_tickers(symbol_list)
        data = [
            TickerResponse(
                symbol=t.symbol,
                last=t.last,
                bid=t.bid,
                ask=t.ask,
                high_24h=t.high_24h,
                low_24h=t.low_24h,
                volume_24h=t.volume_24h,
                timestamp=t.timestamp,
            )
            for t in tickers
        ]
        return ApiResponse(data=data)
    except Exception as e:
        handle_exchange_error(e)


@router.get("/candles/{symbol:path}", response_model=ApiResponse[CandlestickResponse])
async def get_candles(
    exchange: OKXExchange,
    symbol: Annotated[str, Path(description="Trading pair (e.g., BTC/USDT)")],
    timeframe: Annotated[
        str,
        Query(description="Time frame: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w"),
    ] = "1h",
    limit: Annotated[int, Query(ge=1, le=300, description="Number of candles")] = 100,
) -> ApiResponse[CandlestickResponse]:
    """Get candlestick (OHLCV) data for a trading pair.

    Returns historical price data in candlestick format.
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
        candles = await exchange.get_candlesticks(symbol, tf, limit=limit)
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
