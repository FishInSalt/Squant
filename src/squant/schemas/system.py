"""Pydantic schemas for system API requests and responses."""

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class DownloadDataRequest(BaseModel):
    """Request to start a historical data download."""

    exchange: str = Field(
        ...,
        min_length=1,
        max_length=32,
        description="Exchange ID (okx, binance, bybit)",
    )
    symbol: str = Field(
        ...,
        min_length=1,
        max_length=32,
        description="Trading pair (e.g., BTC/USDT)",
    )
    timeframe: str = Field(
        ...,
        min_length=1,
        max_length=8,
        description="Candle timeframe (1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w)",
    )
    start_date: datetime = Field(..., description="Download start date")
    end_date: datetime = Field(..., description="Download end date")

    @model_validator(mode="after")
    def validate_date_range(self) -> "DownloadDataRequest":
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        return self


class DownloadTaskResponse(BaseModel):
    """Download task status response.

    Matches frontend DataDownloadTask type in types/common.ts.
    """

    id: str
    exchange: str
    symbol: str
    timeframe: str
    start_date: str
    end_date: str
    status: str
    progress: float
    total_candles: int | None = None
    downloaded_candles: int | None = None
    error: str | None = None
    created_at: str
    completed_at: str | None = None


class HistoricalDataItem(BaseModel):
    """Historical data summary item.

    Maps from DataLoader.get_available_symbols() output.
    """

    id: str
    exchange: str
    symbol: str
    timeframe: str
    start_date: str | None = None
    end_date: str | None = None
    candle_count: int
    file_size: int = 0
    created_at: str = ""
