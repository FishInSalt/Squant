"""Watchlist service for managing user's favorite trading pairs."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from squant.infra.repository import BaseRepository
from squant.models.market import Watchlist
from squant.schemas.watchlist import AddToWatchlistRequest, ReorderWatchlistItem

logger = logging.getLogger(__name__)


class WatchlistItemExistsError(Exception):
    """Watchlist item already exists."""

    def __init__(self, exchange: str, symbol: str):
        self.exchange = exchange
        self.symbol = symbol
        super().__init__(f"'{symbol}' on '{exchange}' is already in watchlist")


class WatchlistItemNotFoundError(Exception):
    """Watchlist item not found."""

    def __init__(self, item_id: str | UUID):
        self.item_id = str(item_id)
        super().__init__(f"Watchlist item not found: {item_id}")


class WatchlistRepository(BaseRepository[Watchlist]):
    """Repository for Watchlist model with specialized queries."""

    def __init__(self, session: AsyncSession):
        super().__init__(Watchlist, session)

    async def get_by_exchange_and_symbol(self, exchange: str, symbol: str) -> Watchlist | None:
        """Get watchlist item by exchange and symbol combination.

        Args:
            exchange: Exchange identifier (e.g., 'okx', 'binance').
            symbol: Trading pair symbol (e.g., 'BTC/USDT').

        Returns:
            Watchlist item if found, None otherwise.
        """
        stmt = select(Watchlist).where(
            and_(Watchlist.exchange == exchange, Watchlist.symbol == symbol)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all_ordered(self) -> list[Watchlist]:
        """List all watchlist items ordered by sort_order.

        Returns:
            List of watchlist items sorted by sort_order ascending.
        """
        stmt = select(Watchlist).order_by(Watchlist.sort_order.asc(), Watchlist.created_at.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_max_sort_order(self) -> int:
        """Get the maximum sort_order value.

        Returns:
            Maximum sort_order value, or -1 if no items exist.
        """
        stmt = select(func.max(Watchlist.sort_order))
        result = await self.session.execute(stmt)
        max_order = result.scalar()
        return max_order if max_order is not None else -1


class WatchlistService:
    """Service for watchlist business logic."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = WatchlistRepository(session)

    async def add(self, request: AddToWatchlistRequest) -> Watchlist:
        """Add a symbol to the watchlist.

        Args:
            request: Add to watchlist request.

        Returns:
            Created watchlist item.

        Raises:
            WatchlistItemExistsError: If the symbol already exists in watchlist.
        """
        # Check if already exists
        existing = await self.repository.get_by_exchange_and_symbol(
            request.exchange, request.symbol
        )
        if existing:
            raise WatchlistItemExistsError(request.exchange, request.symbol)

        # Get max sort_order and add 1
        max_order = await self.repository.get_max_sort_order()
        new_order = max_order + 1

        # Create watchlist item
        item = await self.repository.create(
            exchange=request.exchange,
            symbol=request.symbol,
            sort_order=new_order,
        )

        try:
            await self.session.commit()
        except IntegrityError as e:
            await self.session.rollback()
            # Handle unique constraint violation (race condition)
            if "uq_watchlist_exchange_symbol" in str(e).lower():
                raise WatchlistItemExistsError(request.exchange, request.symbol) from e
            raise

        return item

    async def remove(self, item_id: UUID) -> None:
        """Remove an item from the watchlist.

        Args:
            item_id: Watchlist item ID.

        Raises:
            WatchlistItemNotFoundError: If item not found.
        """
        exists = await self.repository.exists(item_id)
        if not exists:
            raise WatchlistItemNotFoundError(item_id)

        await self.repository.delete(item_id)
        await self.session.commit()

    async def list(self) -> list[Watchlist]:
        """List all watchlist items ordered by sort_order.

        Returns:
            List of watchlist items.
        """
        return await self.repository.list_all_ordered()

    async def check(self, exchange: str, symbol: str) -> tuple[bool, UUID | None]:
        """Check if a symbol is in the watchlist.

        Args:
            exchange: Exchange identifier.
            symbol: Trading pair symbol.

        Returns:
            Tuple of (in_watchlist, item_id or None).
        """
        item = await self.repository.get_by_exchange_and_symbol(exchange, symbol)
        if item:
            return True, item.id
        return False, None

    async def reorder(self, items: list[ReorderWatchlistItem]) -> list[Watchlist]:
        """Reorder watchlist items.

        Args:
            items: List of items with new sort_order values.

        Returns:
            Updated list of watchlist items.
        """
        for item in items:
            await self.repository.update(item.id, sort_order=item.sort_order)

        await self.session.commit()
        return await self.repository.list_all_ordered()
