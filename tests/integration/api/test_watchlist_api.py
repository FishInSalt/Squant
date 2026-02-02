"""
Integration tests for Watchlist API endpoints.

Tests the complete watchlist CRUD operations with a real database.
"""

from uuid import uuid4

import pytest


class TestWatchlistCRUD:
    """Tests for watchlist CRUD operations."""

    @pytest.mark.asyncio
    async def test_add_to_watchlist(self, client, db_session):
        """Test adding a symbol to watchlist."""
        response = await client.post(
            "/api/v1/watchlist",
            json={"exchange": "okx", "symbol": "BTC/USDT"},
        )

        assert response.status_code == 201
        data = response.json()

        assert data["code"] == 0
        assert data["data"]["exchange"] == "okx"
        assert data["data"]["symbol"] == "BTC/USDT"
        assert data["data"]["sort_order"] == 0
        assert "id" in data["data"]

    @pytest.mark.asyncio
    async def test_add_duplicate_returns_409(self, client, db_session):
        """Test adding duplicate symbol returns 409."""
        # Add first time
        await client.post(
            "/api/v1/watchlist",
            json={"exchange": "okx", "symbol": "ETH/USDT"},
        )

        # Add duplicate
        response = await client.post(
            "/api/v1/watchlist",
            json={"exchange": "okx", "symbol": "ETH/USDT"},
        )

        assert response.status_code == 409
        assert "already in watchlist" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_list_watchlist(self, client, db_session):
        """Test listing all watchlist items."""
        # Add multiple items
        await client.post(
            "/api/v1/watchlist",
            json={"exchange": "okx", "symbol": "BTC/USDT"},
        )
        await client.post(
            "/api/v1/watchlist",
            json={"exchange": "okx", "symbol": "ETH/USDT"},
        )

        # List
        response = await client.get("/api/v1/watchlist")

        assert response.status_code == 200
        data = response.json()

        assert data["code"] == 0
        assert len(data["data"]) == 2

        # Should be ordered by sort_order
        assert data["data"][0]["symbol"] == "BTC/USDT"
        assert data["data"][0]["sort_order"] == 0
        assert data["data"][1]["symbol"] == "ETH/USDT"
        assert data["data"][1]["sort_order"] == 1

    @pytest.mark.asyncio
    async def test_check_in_watchlist(self, client, db_session):
        """Test checking if symbol is in watchlist."""
        # Add item
        add_response = await client.post(
            "/api/v1/watchlist",
            json={"exchange": "okx", "symbol": "BTC/USDT"},
        )
        item_id = add_response.json()["data"]["id"]

        # Check existing
        response = await client.get(
            "/api/v1/watchlist/check",
            params={"exchange": "okx", "symbol": "BTC/USDT"},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["data"]["in_watchlist"] is True
        assert data["data"]["item_id"] == item_id

    @pytest.mark.asyncio
    async def test_check_not_in_watchlist(self, client, db_session):
        """Test checking symbol not in watchlist."""
        response = await client.get(
            "/api/v1/watchlist/check",
            params={"exchange": "okx", "symbol": "NONEXISTENT/USDT"},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["data"]["in_watchlist"] is False
        assert data["data"]["item_id"] is None

    @pytest.mark.asyncio
    async def test_remove_from_watchlist(self, client, db_session):
        """Test removing item from watchlist."""
        # Add item
        add_response = await client.post(
            "/api/v1/watchlist",
            json={"exchange": "okx", "symbol": "BTC/USDT"},
        )
        item_id = add_response.json()["data"]["id"]

        # Remove
        response = await client.delete(f"/api/v1/watchlist/{item_id}")

        assert response.status_code == 200
        assert response.json()["message"] == "Item removed from watchlist"

        # Verify removed
        check_response = await client.get(
            "/api/v1/watchlist/check",
            params={"exchange": "okx", "symbol": "BTC/USDT"},
        )
        assert check_response.json()["data"]["in_watchlist"] is False

    @pytest.mark.asyncio
    async def test_remove_nonexistent_returns_404(self, client, db_session):
        """Test removing nonexistent item returns 404."""
        fake_id = str(uuid4())

        response = await client.delete(f"/api/v1/watchlist/{fake_id}")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestWatchlistReorder:
    """Tests for watchlist reorder operations."""

    @pytest.mark.asyncio
    async def test_reorder_watchlist(self, client, db_session):
        """Test reordering watchlist items."""
        # Add items
        r1 = await client.post(
            "/api/v1/watchlist",
            json={"exchange": "okx", "symbol": "BTC/USDT"},
        )
        r2 = await client.post(
            "/api/v1/watchlist",
            json={"exchange": "okx", "symbol": "ETH/USDT"},
        )
        r3 = await client.post(
            "/api/v1/watchlist",
            json={"exchange": "okx", "symbol": "SOL/USDT"},
        )

        id1 = r1.json()["data"]["id"]
        id2 = r2.json()["data"]["id"]
        id3 = r3.json()["data"]["id"]

        # Reorder: SOL -> BTC -> ETH
        response = await client.put(
            "/api/v1/watchlist/reorder",
            json={
                "items": [
                    {"id": id3, "sort_order": 0},
                    {"id": id1, "sort_order": 1},
                    {"id": id2, "sort_order": 2},
                ]
            },
        )

        assert response.status_code == 200
        data = response.json()

        # Verify new order
        assert data["data"][0]["symbol"] == "SOL/USDT"
        assert data["data"][0]["sort_order"] == 0
        assert data["data"][1]["symbol"] == "BTC/USDT"
        assert data["data"][1]["sort_order"] == 1
        assert data["data"][2]["symbol"] == "ETH/USDT"
        assert data["data"][2]["sort_order"] == 2

    @pytest.mark.asyncio
    async def test_reorder_persists_after_list(self, client, db_session):
        """Test that reorder is persisted to database."""
        # Add items
        r1 = await client.post(
            "/api/v1/watchlist",
            json={"exchange": "okx", "symbol": "BTC/USDT"},
        )
        r2 = await client.post(
            "/api/v1/watchlist",
            json={"exchange": "okx", "symbol": "ETH/USDT"},
        )

        id1 = r1.json()["data"]["id"]
        id2 = r2.json()["data"]["id"]

        # Reorder: ETH -> BTC
        await client.put(
            "/api/v1/watchlist/reorder",
            json={
                "items": [
                    {"id": id2, "sort_order": 0},
                    {"id": id1, "sort_order": 1},
                ]
            },
        )

        # List again and verify order persists
        response = await client.get("/api/v1/watchlist")
        data = response.json()

        assert data["data"][0]["symbol"] == "ETH/USDT"
        assert data["data"][1]["symbol"] == "BTC/USDT"


class TestWatchlistMultiExchange:
    """Tests for watchlist with multiple exchanges."""

    @pytest.mark.asyncio
    async def test_same_symbol_different_exchanges(self, client, db_session):
        """Test adding same symbol on different exchanges."""
        # Add BTC/USDT on OKX
        r1 = await client.post(
            "/api/v1/watchlist",
            json={"exchange": "okx", "symbol": "BTC/USDT"},
        )
        assert r1.status_code == 201

        # Add BTC/USDT on Binance (should succeed)
        r2 = await client.post(
            "/api/v1/watchlist",
            json={"exchange": "binance", "symbol": "BTC/USDT"},
        )
        assert r2.status_code == 201

        # List should show both
        response = await client.get("/api/v1/watchlist")
        data = response.json()

        assert len(data["data"]) == 2
        exchanges = [item["exchange"] for item in data["data"]]
        assert "okx" in exchanges
        assert "binance" in exchanges

    @pytest.mark.asyncio
    async def test_check_by_exchange(self, client, db_session):
        """Test checking watchlist by specific exchange."""
        # Add BTC/USDT on OKX only
        await client.post(
            "/api/v1/watchlist",
            json={"exchange": "okx", "symbol": "BTC/USDT"},
        )

        # Check OKX - should be in watchlist
        r1 = await client.get(
            "/api/v1/watchlist/check",
            params={"exchange": "okx", "symbol": "BTC/USDT"},
        )
        assert r1.json()["data"]["in_watchlist"] is True

        # Check Binance - should NOT be in watchlist
        r2 = await client.get(
            "/api/v1/watchlist/check",
            params={"exchange": "binance", "symbol": "BTC/USDT"},
        )
        assert r2.json()["data"]["in_watchlist"] is False
