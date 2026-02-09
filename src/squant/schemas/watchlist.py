"""Pydantic schemas for watchlist API requests and responses."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AddToWatchlistRequest(BaseModel):
    """Request to add a symbol to the watchlist."""

    symbol: str = Field(..., min_length=1, max_length=32, description="Trading pair symbol")
    exchange: str = Field(..., min_length=1, max_length=32, description="Exchange identifier")


class ReorderWatchlistItem(BaseModel):
    """Item for reordering the watchlist."""

    id: UUID = Field(..., description="Watchlist item ID")
    sort_order: int = Field(..., ge=0, description="New sort order")


class ReorderWatchlistRequest(BaseModel):
    """Request to reorder the watchlist."""

    items: list[ReorderWatchlistItem] = Field(
        ..., description="Reordered items with new sort_order"
    )


class WatchlistItemResponse(BaseModel):
    """Watchlist item response."""

    id: UUID
    symbol: str
    exchange: str
    sort_order: int
    created_at: datetime

    model_config = {"from_attributes": True}


class WatchlistCheckResponse(BaseModel):
    """Response for checking if a symbol is in the watchlist."""

    in_watchlist: bool = Field(..., description="Whether the symbol is in the watchlist")
    item_id: UUID | None = Field(None, description="Watchlist item ID if exists")
