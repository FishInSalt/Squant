"""Unit tests for watchlist service."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from squant.models.market import Watchlist
from squant.schemas.watchlist import AddToWatchlistRequest, ReorderWatchlistItem
from squant.services.watchlist import (
    WatchlistItemExistsError,
    WatchlistItemNotFoundError,
    WatchlistRepository,
    WatchlistService,
)


class TestWatchlistRepository:
    """Tests for WatchlistRepository."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create a mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        return session

    @pytest.fixture
    def repository(self, mock_session: AsyncMock) -> WatchlistRepository:
        """Create a repository with mock session."""
        return WatchlistRepository(mock_session)

    @pytest.mark.asyncio
    async def test_get_by_exchange_and_symbol_found(
        self, repository: WatchlistRepository, mock_session: AsyncMock
    ) -> None:
        """Test getting a watchlist item when it exists."""
        mock_item = MagicMock(spec=Watchlist)
        mock_item.exchange = "okx"
        mock_item.symbol = "BTC/USDT"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_item
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_exchange_and_symbol("okx", "BTC/USDT")
        assert result == mock_item

    @pytest.mark.asyncio
    async def test_get_by_exchange_and_symbol_not_found(
        self, repository: WatchlistRepository, mock_session: AsyncMock
    ) -> None:
        """Test getting a watchlist item when it doesn't exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_exchange_and_symbol("okx", "NON/EXIST")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_all_ordered(
        self, repository: WatchlistRepository, mock_session: AsyncMock
    ) -> None:
        """Test listing all watchlist items ordered by sort_order."""
        mock_items = [MagicMock(spec=Watchlist), MagicMock(spec=Watchlist)]
        mock_items[0].sort_order = 0
        mock_items[1].sort_order = 1

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_items
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.list_all_ordered()
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_max_sort_order_with_items(
        self, repository: WatchlistRepository, mock_session: AsyncMock
    ) -> None:
        """Test getting max sort_order when items exist."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 5
        mock_session.execute.return_value = mock_result

        result = await repository.get_max_sort_order()
        assert result == 5

    @pytest.mark.asyncio
    async def test_get_max_sort_order_empty(
        self, repository: WatchlistRepository, mock_session: AsyncMock
    ) -> None:
        """Test getting max sort_order when no items exist."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_max_sort_order()
        assert result == -1


class TestWatchlistService:
    """Tests for WatchlistService."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create a mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        return session

    @pytest.fixture
    def service(self, mock_session: AsyncMock) -> WatchlistService:
        """Create a service with mock session."""
        return WatchlistService(mock_session)

    @pytest.mark.asyncio
    async def test_add_success(
        self, service: WatchlistService, mock_session: AsyncMock
    ) -> None:
        """Test successful addition to watchlist."""
        request = AddToWatchlistRequest(exchange="okx", symbol="BTC/USDT")

        mock_item = MagicMock(spec=Watchlist)
        mock_item.id = uuid4()
        mock_item.exchange = "okx"
        mock_item.symbol = "BTC/USDT"
        mock_item.sort_order = 0

        with patch.object(
            service.repository, "get_by_exchange_and_symbol", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = None

            with patch.object(
                service.repository, "get_max_sort_order", new_callable=AsyncMock
            ) as mock_max:
                mock_max.return_value = -1

                with patch.object(
                    service.repository, "create", new_callable=AsyncMock
                ) as mock_create:
                    mock_create.return_value = mock_item

                    result = await service.add(request)
                    assert result == mock_item
                    mock_session.commit.assert_called_once()
                    mock_create.assert_called_once_with(
                        exchange="okx",
                        symbol="BTC/USDT",
                        sort_order=0,
                    )

    @pytest.mark.asyncio
    async def test_add_duplicate_raises_error(
        self, service: WatchlistService
    ) -> None:
        """Test that adding duplicate item raises error."""
        request = AddToWatchlistRequest(exchange="okx", symbol="BTC/USDT")

        with patch.object(
            service.repository, "get_by_exchange_and_symbol", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = MagicMock(spec=Watchlist)

            with pytest.raises(WatchlistItemExistsError) as exc_info:
                await service.add(request)

            assert "BTC/USDT" in str(exc_info.value)
            assert "okx" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_remove_success(
        self, service: WatchlistService, mock_session: AsyncMock
    ) -> None:
        """Test successful removal from watchlist."""
        item_id = uuid4()

        with patch.object(
            service.repository, "exists", new_callable=AsyncMock
        ) as mock_exists:
            mock_exists.return_value = True

            with patch.object(
                service.repository, "delete", new_callable=AsyncMock
            ) as mock_delete:
                mock_delete.return_value = True

                await service.remove(item_id)
                mock_delete.assert_called_once_with(item_id)
                mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_remove_not_found_raises_error(
        self, service: WatchlistService
    ) -> None:
        """Test that removing non-existent item raises error."""
        item_id = uuid4()

        with patch.object(
            service.repository, "exists", new_callable=AsyncMock
        ) as mock_exists:
            mock_exists.return_value = False

            with pytest.raises(WatchlistItemNotFoundError) as exc_info:
                await service.remove(item_id)

            assert str(item_id) in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_list_all(self, service: WatchlistService) -> None:
        """Test listing all watchlist items."""
        mock_items = [
            MagicMock(spec=Watchlist),
            MagicMock(spec=Watchlist),
        ]

        with patch.object(
            service.repository, "list_all_ordered", new_callable=AsyncMock
        ) as mock_list:
            mock_list.return_value = mock_items

            result = await service.list()
            assert result == mock_items
            mock_list.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_exists(self, service: WatchlistService) -> None:
        """Test checking when item exists in watchlist."""
        mock_item = MagicMock(spec=Watchlist)
        mock_item.id = uuid4()

        with patch.object(
            service.repository, "get_by_exchange_and_symbol", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = mock_item

            in_watchlist, item_id = await service.check("okx", "BTC/USDT")
            assert in_watchlist is True
            assert item_id == mock_item.id

    @pytest.mark.asyncio
    async def test_check_not_exists(self, service: WatchlistService) -> None:
        """Test checking when item does not exist in watchlist."""
        with patch.object(
            service.repository, "get_by_exchange_and_symbol", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = None

            in_watchlist, item_id = await service.check("okx", "ETH/USDT")
            assert in_watchlist is False
            assert item_id is None

    @pytest.mark.asyncio
    async def test_reorder(
        self, service: WatchlistService, mock_session: AsyncMock
    ) -> None:
        """Test reordering watchlist items."""
        id1 = uuid4()
        id2 = uuid4()

        items = [
            ReorderWatchlistItem(id=id1, sort_order=1),
            ReorderWatchlistItem(id=id2, sort_order=0),
        ]

        mock_items = [MagicMock(spec=Watchlist), MagicMock(spec=Watchlist)]

        with patch.object(
            service.repository, "update", new_callable=AsyncMock
        ) as mock_update:
            with patch.object(
                service.repository, "list_all_ordered", new_callable=AsyncMock
            ) as mock_list:
                mock_list.return_value = mock_items

                result = await service.reorder(items)
                assert result == mock_items
                assert mock_update.call_count == 2
                mock_session.commit.assert_called_once()


class TestWatchlistErrors:
    """Tests for watchlist error classes."""

    def test_watchlist_item_exists_error(self) -> None:
        """Test WatchlistItemExistsError message."""
        error = WatchlistItemExistsError("okx", "BTC/USDT")
        assert "BTC/USDT" in str(error)
        assert "okx" in str(error)
        assert "already in watchlist" in str(error).lower()
        assert error.exchange == "okx"
        assert error.symbol == "BTC/USDT"

    def test_watchlist_item_not_found_error(self) -> None:
        """Test WatchlistItemNotFoundError message."""
        item_id = uuid4()
        error = WatchlistItemNotFoundError(item_id)
        assert str(item_id) in str(error)
        assert "not found" in str(error).lower()
        assert error.item_id == str(item_id)
