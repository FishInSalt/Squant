"""Unit tests for watchlist API endpoints."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from squant.api.v1.watchlist import router
from squant.models.market import Watchlist
from squant.services.watchlist import (
    WatchlistItemExistsError,
    WatchlistItemNotFoundError,
)


@pytest.fixture
def app() -> FastAPI:
    """Create a test FastAPI app."""
    app = FastAPI()
    app.include_router(router, prefix="/watchlist")
    return app


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Create async test client."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_watchlist_item() -> MagicMock:
    """Create a mock watchlist item."""
    item = MagicMock(spec=Watchlist)
    item.id = uuid4()
    item.exchange = "okx"
    item.symbol = "BTC/USDT"
    item.sort_order = 0
    item.created_at = datetime.now(UTC)
    return item


class TestAddToWatchlist:
    """Tests for POST /watchlist."""

    @pytest.mark.asyncio
    async def test_add_to_watchlist_success(
        self, client: AsyncClient, mock_watchlist_item: MagicMock
    ) -> None:
        """Test successful addition to watchlist."""
        with patch("squant.api.v1.watchlist.get_session"):
            with patch("squant.api.v1.watchlist.WatchlistService") as MockService:
                service = MockService.return_value
                service.add = AsyncMock(return_value=mock_watchlist_item)

                response = await client.post(
                    "/watchlist",
                    json={
                        "exchange": "okx",
                        "symbol": "BTC/USDT",
                    },
                )

                assert response.status_code == 201
                data = response.json()
                assert data["code"] == 0
                assert data["data"]["symbol"] == "BTC/USDT"
                assert data["data"]["exchange"] == "okx"

    @pytest.mark.asyncio
    async def test_add_to_watchlist_duplicate_returns_409(self, client: AsyncClient) -> None:
        """Test adding duplicate item returns 409."""
        with patch("squant.api.v1.watchlist.get_session"):
            with patch("squant.api.v1.watchlist.WatchlistService") as MockService:
                service = MockService.return_value
                service.add = AsyncMock(side_effect=WatchlistItemExistsError("okx", "BTC/USDT"))

                response = await client.post(
                    "/watchlist",
                    json={
                        "exchange": "okx",
                        "symbol": "BTC/USDT",
                    },
                )

                assert response.status_code == 409
                assert "already in watchlist" in response.json()["detail"].lower()


class TestListWatchlist:
    """Tests for GET /watchlist."""

    @pytest.mark.asyncio
    async def test_list_watchlist_success(
        self, client: AsyncClient, mock_watchlist_item: MagicMock
    ) -> None:
        """Test listing watchlist items."""
        with patch("squant.api.v1.watchlist.get_session"):
            with patch("squant.api.v1.watchlist.WatchlistService") as MockService:
                service = MockService.return_value
                service.list = AsyncMock(return_value=[mock_watchlist_item])

                response = await client.get("/watchlist")

                assert response.status_code == 200
                data = response.json()
                assert data["code"] == 0
                assert len(data["data"]) == 1
                assert data["data"][0]["symbol"] == "BTC/USDT"

    @pytest.mark.asyncio
    async def test_list_watchlist_empty(self, client: AsyncClient) -> None:
        """Test listing empty watchlist."""
        with patch("squant.api.v1.watchlist.get_session"):
            with patch("squant.api.v1.watchlist.WatchlistService") as MockService:
                service = MockService.return_value
                service.list = AsyncMock(return_value=[])

                response = await client.get("/watchlist")

                assert response.status_code == 200
                data = response.json()
                assert data["code"] == 0
                assert len(data["data"]) == 0


class TestRemoveFromWatchlist:
    """Tests for DELETE /watchlist/{item_id}."""

    @pytest.mark.asyncio
    async def test_remove_from_watchlist_success(
        self, client: AsyncClient, mock_watchlist_item: MagicMock
    ) -> None:
        """Test successful removal from watchlist."""
        with patch("squant.api.v1.watchlist.get_session"):
            with patch("squant.api.v1.watchlist.WatchlistService") as MockService:
                service = MockService.return_value
                service.remove = AsyncMock()

                response = await client.delete(f"/watchlist/{mock_watchlist_item.id}")

                assert response.status_code == 200
                data = response.json()
                assert data["message"] == "Item removed from watchlist"

    @pytest.mark.asyncio
    async def test_remove_from_watchlist_not_found_returns_404(self, client: AsyncClient) -> None:
        """Test removing non-existent item returns 404."""
        item_id = uuid4()

        with patch("squant.api.v1.watchlist.get_session"):
            with patch("squant.api.v1.watchlist.WatchlistService") as MockService:
                service = MockService.return_value
                service.remove = AsyncMock(side_effect=WatchlistItemNotFoundError(item_id))

                response = await client.delete(f"/watchlist/{item_id}")

                assert response.status_code == 404
                assert "not found" in response.json()["detail"].lower()


class TestCheckWatchlist:
    """Tests for GET /watchlist/check."""

    @pytest.mark.asyncio
    async def test_check_in_watchlist_true(
        self, client: AsyncClient, mock_watchlist_item: MagicMock
    ) -> None:
        """Test checking item that is in watchlist."""
        with patch("squant.api.v1.watchlist.get_session"):
            with patch("squant.api.v1.watchlist.WatchlistService") as MockService:
                service = MockService.return_value
                service.check = AsyncMock(return_value=(True, mock_watchlist_item.id))

                response = await client.get(
                    "/watchlist/check",
                    params={"exchange": "okx", "symbol": "BTC/USDT"},
                )

                assert response.status_code == 200
                data = response.json()
                assert data["code"] == 0
                assert data["data"]["in_watchlist"] is True
                assert data["data"]["item_id"] is not None

    @pytest.mark.asyncio
    async def test_check_in_watchlist_false(self, client: AsyncClient) -> None:
        """Test checking item that is not in watchlist."""
        with patch("squant.api.v1.watchlist.get_session"):
            with patch("squant.api.v1.watchlist.WatchlistService") as MockService:
                service = MockService.return_value
                service.check = AsyncMock(return_value=(False, None))

                response = await client.get(
                    "/watchlist/check",
                    params={"exchange": "okx", "symbol": "ETH/USDT"},
                )

                assert response.status_code == 200
                data = response.json()
                assert data["code"] == 0
                assert data["data"]["in_watchlist"] is False
                assert data["data"]["item_id"] is None


class TestReorderWatchlist:
    """Tests for PUT /watchlist/reorder."""

    @pytest.mark.asyncio
    async def test_reorder_watchlist_success(
        self, client: AsyncClient, mock_watchlist_item: MagicMock
    ) -> None:
        """Test successful reordering of watchlist."""
        # Create second mock item
        item2 = MagicMock(spec=Watchlist)
        item2.id = uuid4()
        item2.exchange = "okx"
        item2.symbol = "ETH/USDT"
        item2.sort_order = 1
        item2.created_at = datetime.now(UTC)

        mock_watchlist_item.sort_order = 0

        with patch("squant.api.v1.watchlist.get_session"):
            with patch("squant.api.v1.watchlist.WatchlistService") as MockService:
                service = MockService.return_value
                # After reorder, item2 comes first
                item2.sort_order = 0
                mock_watchlist_item.sort_order = 1
                service.reorder = AsyncMock(return_value=[item2, mock_watchlist_item])

                response = await client.put(
                    "/watchlist/reorder",
                    json={
                        "items": [
                            {"id": str(item2.id), "sort_order": 0},
                            {"id": str(mock_watchlist_item.id), "sort_order": 1},
                        ]
                    },
                )

                assert response.status_code == 200
                data = response.json()
                assert data["code"] == 0
                assert len(data["data"]) == 2
                assert data["data"][0]["symbol"] == "ETH/USDT"
                assert data["data"][1]["symbol"] == "BTC/USDT"
