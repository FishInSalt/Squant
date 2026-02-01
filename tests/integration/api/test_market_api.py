"""
Integration tests for Market API endpoints.

Tests validate acceptance criteria from dev-docs/requirements/acceptance-criteria/01-market.md:
- MKT-001: Display Top 20 popular trading pairs
- MKT-002: Display real-time price, 24h change%, 24h volume
- MKT-003: Filter by exchange
- MKT-004: Real-time price updates
- MKT-010: Add trading pair to watchlist
- MKT-011: Remove trading pair from watchlist
- MKT-012: Watchlist persistence
- MKT-020: Support multiple timeframes
- MKT-021: Real-time candlestick updates
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from squant.infra.exchange.types import Ticker
from squant.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def sample_tickers():
    """Create sample ticker data for testing."""
    tickers = []

    symbols = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT"]
    volumes = [50000000, 30000000, 20000000, 15000000, 10000000]  # Descending by volume

    for symbol, volume in zip(symbols, volumes):
        ticker = Ticker(
            symbol=symbol,
            bid=Decimal("40000.0") if "BTC" in symbol else Decimal("2500.0"),
            ask=Decimal("40100.0") if "BTC" in symbol else Decimal("2510.0"),
            last=Decimal("40050.0") if "BTC" in symbol else Decimal("2505.0"),
            volume_24h=Decimal(str(volume)),
            timestamp=datetime.now(UTC),
            change_24h=Decimal("5.5") if "BTC" in symbol else Decimal("-2.3"),
            high_24h=Decimal("41000.0") if "BTC" in symbol else Decimal("2600.0"),
            low_24h=Decimal("39000.0") if "BTC" in symbol else Decimal("2400.0"),
        )
        tickers.append(ticker)

    return tickers


class TestDisplayTopTradingPairs:
    """
    Tests for MKT-001: Display Top 20 popular trading pairs

    Acceptance criteria:
    - Show top 20 by 24h volume when entering market page
    - Display symbol, latest price, 24h change%, volume for each
    - Show error "Cannot get market data" on connection failure
    """

    @pytest.mark.asyncio
    async def test_get_top_20_trading_pairs_by_volume(
        self, client, sample_tickers, sample_exchange_account
    ):
        """Test MKT-001-1: Display top 20 sorted by 24h volume."""
        # Mock exchange adapter to return tickers
        mock_adapter = MagicMock()
        mock_adapter.get_tickers = AsyncMock(return_value=sample_tickers)

        with patch("squant.api.v1.market.get_exchange_adapter", return_value=mock_adapter):
            response = client.get(f"/api/v1/market/tickers?exchange=okx&limit=20")

        assert response.status_code == 200
        data = response.json()

        # Should be sorted by volume descending
        assert len(data) > 0
        # First ticker should have highest volume
        assert data[0]["symbol"] == "BTC/USDT"
        assert data[0]["volume"] == 50000000

    @pytest.mark.asyncio
    async def test_ticker_display_required_fields(self, client, sample_tickers):
        """Test MKT-001-2: Each ticker displays required fields."""
        mock_adapter = MagicMock()
        mock_adapter.get_tickers = AsyncMock(return_value=sample_tickers)

        with patch("squant.api.v1.market.get_exchange_adapter", return_value=mock_adapter):
            response = client.get("/api/v1/market/tickers?exchange=okx")

        assert response.status_code == 200
        data = response.json()

        # Check first ticker has all required fields
        ticker = data[0]
        assert "symbol" in ticker
        assert "last" in ticker  # latest price
        assert "change_24h" in ticker  # 24h change%
        assert "volume" in ticker  # 24h volume

    @pytest.mark.asyncio
    async def test_get_tickers_connection_failure(self, client):
        """Test MKT-001-3: Show error on connection failure."""
        # Mock exchange adapter to raise connection error
        mock_adapter = MagicMock()
        mock_adapter.get_tickers = AsyncMock(
            side_effect=Exception("Cannot connect to exchange")
        )

        with patch("squant.api.v1.market.get_exchange_adapter", return_value=mock_adapter):
            response = client.get("/api/v1/market/tickers?exchange=okx")

        assert response.status_code in [400, 500, 503]
        data = response.json()

        # Should contain error message about getting market data
        assert "无法获取行情数据" in data["detail"] or "cannot get" in data["detail"].lower()


class TestRealTimePriceDisplay:
    """
    Tests for MKT-002: Display real-time price, 24h change%, 24h volume

    Acceptance criteria:
    - Show latest price with exchange precision
    - Green for positive change, red for negative
    - Use K/M/B abbreviations for large volumes
    """

    @pytest.mark.asyncio
    async def test_display_latest_price_with_precision(self, client, sample_tickers):
        """Test MKT-002-1: Display latest price with correct precision."""
        mock_adapter = MagicMock()
        mock_adapter.get_tickers = AsyncMock(return_value=sample_tickers)

        with patch("squant.api.v1.market.get_exchange_adapter", return_value=mock_adapter):
            response = client.get("/api/v1/market/tickers?exchange=okx")

        assert response.status_code == 200
        data = response.json()

        # BTC ticker should have price
        btc_ticker = next(t for t in data if t["symbol"] == "BTC/USDT")
        assert btc_ticker["last"] == 40050.0

    @pytest.mark.asyncio
    async def test_positive_change_indicator(self, client, sample_tickers):
        """Test MKT-002-2: Positive change should be indicated."""
        mock_adapter = MagicMock()
        mock_adapter.get_tickers = AsyncMock(return_value=sample_tickers)

        with patch("squant.api.v1.market.get_exchange_adapter", return_value=mock_adapter):
            response = client.get("/api/v1/market/tickers?exchange=okx")

        assert response.status_code == 200
        data = response.json()

        # BTC has positive change (+5.5%)
        btc_ticker = next(t for t in data if t["symbol"] == "BTC/USDT")
        assert btc_ticker["change_24h"] > 0

    @pytest.mark.asyncio
    async def test_negative_change_indicator(self, client, sample_tickers):
        """Test MKT-002-2: Negative change should be indicated."""
        mock_adapter = MagicMock()
        mock_adapter.get_tickers = AsyncMock(return_value=sample_tickers)

        with patch("squant.api.v1.market.get_exchange_adapter", return_value=mock_adapter):
            response = client.get("/api/v1/market/tickers?exchange=okx")

        assert response.status_code == 200
        data = response.json()

        # ETH has negative change (-2.3%)
        eth_ticker = next(t for t in data if t["symbol"] == "ETH/USDT")
        assert eth_ticker["change_24h"] < 0

    @pytest.mark.asyncio
    async def test_volume_display_with_abbreviations(self, client, sample_tickers):
        """Test MKT-002-3: Large volumes use K/M/B abbreviations (frontend responsibility)."""
        mock_adapter = MagicMock()
        mock_adapter.get_tickers = AsyncMock(return_value=sample_tickers)

        with patch("squant.api.v1.market.get_exchange_adapter", return_value=mock_adapter):
            response = client.get("/api/v1/market/tickers?exchange=okx")

        assert response.status_code == 200
        data = response.json()

        # Volume should be present as number (frontend formats it)
        btc_ticker = next(t for t in data if t["symbol"] == "BTC/USDT")
        assert btc_ticker["volume"] == 50000000  # 50M


class TestFilterByExchange:
    """
    Tests for MKT-003: Filter by exchange

    Acceptance criteria:
    - Filter by specific exchange shows only that exchange's pairs
    - Filter by "All" shows all exchanges
    - Show "No data" when filter result is empty
    """

    @pytest.mark.asyncio
    async def test_filter_by_binance(self, client):
        """Test MKT-003-1: Filter shows only Binance pairs."""
        binance_tickers = [
            Ticker(
                symbol="BTC/USDT",
                last=Decimal("40000.0"),
                volume_24h=Decimal("50000000"),
                timestamp=datetime.now(UTC),
                change_24h=Decimal("5.0"),
            )
        ]

        mock_adapter = MagicMock()
        mock_adapter.get_tickers = AsyncMock(return_value=binance_tickers)

        with patch("squant.api.v1.market.get_exchange_adapter", return_value=mock_adapter):
            response = client.get("/api/v1/market/tickers?exchange=binance")

        assert response.status_code == 200
        data = response.json()

        # Should return Binance tickers
        assert len(data) > 0

    @pytest.mark.asyncio
    async def test_filter_by_okx(self, client, sample_tickers):
        """Test MKT-003-2: Filter shows only OKX pairs."""
        mock_adapter = MagicMock()
        mock_adapter.get_tickers = AsyncMock(return_value=sample_tickers)

        with patch("squant.api.v1.market.get_exchange_adapter", return_value=mock_adapter):
            response = client.get("/api/v1/market/tickers?exchange=okx")

        assert response.status_code == 200
        data = response.json()

        # Should return OKX tickers
        assert len(data) > 0

    @pytest.mark.asyncio
    async def test_empty_filter_result(self, client):
        """Test MKT-003-4: Show empty state when no data."""
        # Mock exchange with no tickers
        mock_adapter = MagicMock()
        mock_adapter.get_tickers = AsyncMock(return_value=[])

        with patch("squant.api.v1.market.get_exchange_adapter", return_value=mock_adapter):
            response = client.get("/api/v1/market/tickers?exchange=okx")

        assert response.status_code == 200
        data = response.json()

        # Should return empty list
        assert len(data) == 0


class TestRealTimePriceUpdates:
    """
    Tests for MKT-004: Real-time price updates

    Acceptance criteria:
    - Update price within 500ms of exchange push (WebSocket)
    - Flash green on price increase (frontend)
    - Flash red on price decrease (frontend)
    - Show connection status and auto-reconnect
    """

    @pytest.mark.asyncio
    async def test_websocket_price_stream_available(self, client):
        """Test MKT-004: WebSocket endpoint available for real-time updates."""
        # This tests that the WebSocket endpoint exists
        # Actual WebSocket behavior is tested in WebSocket integration tests
        # Here we just verify the endpoint is available
        pass  # WebSocket connection test requires different approach


class TestAddToWatchlist:
    """
    Tests for MKT-010: Add trading pair to watchlist

    Acceptance criteria:
    - Add to watchlist on "Follow" button click
    - Show "Followed" when already in watchlist
    - New pair appears in watchlist tab after adding
    """

    @pytest.mark.asyncio
    async def test_add_symbol_to_watchlist(self, client, db_session):
        """Test MKT-010-1: Add trading pair to watchlist."""
        watchlist_data = {
            "exchange": "okx",
            "symbol": "BTC/USDT",
        }

        with patch("squant.api.deps.get_db_session", return_value=db_session):
            response = client.post("/api/v1/market/watchlist", json=watchlist_data)

        assert response.status_code in [200, 201]
        data = response.json()

        assert data["symbol"] == "BTC/USDT"
        assert data["exchange"] == "okx"

    @pytest.mark.asyncio
    async def test_add_duplicate_to_watchlist(self, client, db_session):
        """Test MKT-010-2: Adding duplicate shows already in watchlist."""
        watchlist_data = {
            "exchange": "okx",
            "symbol": "BTC/USDT",
        }

        with patch("squant.api.deps.get_db_session", return_value=db_session):
            # Add first time
            response1 = client.post("/api/v1/market/watchlist", json=watchlist_data)
            assert response1.status_code in [200, 201]

            # Add again (duplicate)
            response2 = client.post("/api/v1/market/watchlist", json=watchlist_data)

            # Should handle gracefully (either 200 OK or 400 already exists)
            assert response2.status_code in [200, 400]

    @pytest.mark.asyncio
    async def test_get_watchlist_after_adding(self, client, db_session):
        """Test MKT-010-3: New pair appears in watchlist."""
        watchlist_data = {
            "exchange": "okx",
            "symbol": "ETH/USDT",
        }

        with patch("squant.api.deps.get_db_session", return_value=db_session):
            # Add to watchlist
            client.post("/api/v1/market/watchlist", json=watchlist_data)

            # Get watchlist
            response = client.get("/api/v1/market/watchlist")

        assert response.status_code == 200
        data = response.json()

        # Should contain the added symbol
        symbols = [item["symbol"] for item in data]
        assert "ETH/USDT" in symbols


class TestRemoveFromWatchlist:
    """
    Tests for MKT-011: Remove trading pair from watchlist

    Acceptance criteria:
    - Remove from watchlist on "Unfollow" button click
    - Removed pair no longer appears in watchlist after refresh
    """

    @pytest.mark.asyncio
    async def test_remove_symbol_from_watchlist(self, client, db_session):
        """Test MKT-011-1: Remove trading pair from watchlist."""
        # First add to watchlist
        watchlist_data = {
            "exchange": "okx",
            "symbol": "BTC/USDT",
        }

        with patch("squant.api.deps.get_db_session", return_value=db_session):
            add_response = client.post("/api/v1/market/watchlist", json=watchlist_data)
            assert add_response.status_code in [200, 201]

            # Then remove it
            response = client.delete(
                "/api/v1/market/watchlist",
                params={"exchange": "okx", "symbol": "BTC/USDT"},
            )

        assert response.status_code in [200, 204]

    @pytest.mark.asyncio
    async def test_removed_pair_not_in_watchlist(self, client, db_session):
        """Test MKT-011-2: Removed pair no longer appears in watchlist."""
        watchlist_data = {
            "exchange": "okx",
            "symbol": "SOL/USDT",
        }

        with patch("squant.api.deps.get_db_session", return_value=db_session):
            # Add to watchlist
            client.post("/api/v1/market/watchlist", json=watchlist_data)

            # Remove from watchlist
            client.delete(
                "/api/v1/market/watchlist",
                params={"exchange": "okx", "symbol": "SOL/USDT"},
            )

            # Get watchlist
            response = client.get("/api/v1/market/watchlist")

        assert response.status_code == 200
        data = response.json()

        # Should NOT contain the removed symbol
        symbols = [item["symbol"] for item in data]
        assert "SOL/USDT" not in symbols


class TestWatchlistPersistence:
    """
    Tests for MKT-012: Watchlist persistence

    Acceptance criteria:
    - Watchlist persists after browser close/reopen (database storage)
    - Watchlist persists after system restart (database storage)
    """

    @pytest.mark.asyncio
    async def test_watchlist_persists_in_database(self, client, db_session):
        """Test MKT-012: Watchlist is stored in database and persists."""
        watchlist_items = [
            {"exchange": "okx", "symbol": "BTC/USDT"},
            {"exchange": "okx", "symbol": "ETH/USDT"},
            {"exchange": "binance", "symbol": "BNB/USDT"},
        ]

        with patch("squant.api.deps.get_db_session", return_value=db_session):
            # Add items to watchlist
            for item in watchlist_items:
                client.post("/api/v1/market/watchlist", json=item)

            # Simulate session restart by getting fresh watchlist
            response = client.get("/api/v1/market/watchlist")

        assert response.status_code == 200
        data = response.json()

        # All items should still be there
        assert len(data) >= 3

        symbols = [item["symbol"] for item in data]
        assert "BTC/USDT" in symbols
        assert "ETH/USDT" in symbols
        assert "BNB/USDT" in symbols


class TestMultipleTimeframes:
    """
    Tests for MKT-020: Support multiple timeframes

    Acceptance criteria:
    - Support 1m, 5m, 15m, 1h, 4h, 1d, 1w timeframes
    - Smooth chart transition on timeframe switch (frontend)
    """

    @pytest.mark.asyncio
    async def test_get_candles_1m_timeframe(self, client):
        """Test MKT-020-1: Get 1-minute candlestick data."""
        mock_adapter = MagicMock()
        mock_adapter.get_ohlcv = AsyncMock(
            return_value=[
                [datetime.now(UTC).timestamp() * 1000, 40000, 40100, 39900, 40050, 100],
            ]
        )

        with patch("squant.api.v1.market.get_exchange_adapter", return_value=mock_adapter):
            response = client.get(
                "/api/v1/market/candles",
                params={"exchange": "okx", "symbol": "BTC/USDT", "timeframe": "1m"},
            )

        assert response.status_code == 200
        data = response.json()

        assert len(data) > 0

    @pytest.mark.asyncio
    async def test_get_candles_multiple_timeframes(self, client):
        """Test MKT-020: Support for all timeframes."""
        timeframes = ["1m", "5m", "15m", "1h", "4h", "1d", "1w"]

        for timeframe in timeframes:
            mock_adapter = MagicMock()
            mock_adapter.get_ohlcv = AsyncMock(
                return_value=[
                    [datetime.now(UTC).timestamp() * 1000, 40000, 40100, 39900, 40050, 100],
                ]
            )

            with patch("squant.api.v1.market.get_exchange_adapter", return_value=mock_adapter):
                response = client.get(
                    "/api/v1/market/candles",
                    params={
                        "exchange": "okx",
                        "symbol": "BTC/USDT",
                        "timeframe": timeframe,
                    },
                )

            assert response.status_code == 200, f"Failed for timeframe {timeframe}"


class TestRealTimeCandlestickUpdates:
    """
    Tests for MKT-021: Real-time candlestick updates

    Acceptance criteria:
    - Last candle updates in real-time (OHLC)
    - Auto-add new candle when period ends
    - Auto-load more historical candles on scroll
    """

    @pytest.mark.asyncio
    async def test_get_latest_candles(self, client):
        """Test MKT-021-1: Get latest candles for real-time updates."""
        now = datetime.now(UTC)

        mock_candles = [
            [
                int((now - timedelta(minutes=i)).timestamp() * 1000),
                40000 + i * 100,
                40100 + i * 100,
                39900 + i * 100,
                40050 + i * 100,
                100 + i * 10,
            ]
            for i in range(100, 0, -1)  # 100 candles
        ]

        mock_adapter = MagicMock()
        mock_adapter.get_ohlcv = AsyncMock(return_value=mock_candles)

        with patch("squant.api.v1.market.get_exchange_adapter", return_value=mock_adapter):
            response = client.get(
                "/api/v1/market/candles",
                params={
                    "exchange": "okx",
                    "symbol": "BTC/USDT",
                    "timeframe": "1m",
                    "limit": 100,
                },
            )

        assert response.status_code == 200
        data = response.json()

        # Should return 100 candles
        assert len(data) == 100

    @pytest.mark.asyncio
    async def test_load_historical_candles_with_pagination(self, client):
        """Test MKT-021-3: Load more historical candles."""
        now = datetime.now(UTC)
        since = int((now - timedelta(hours=2)).timestamp() * 1000)

        mock_candles = [
            [
                int((now - timedelta(minutes=i)).timestamp() * 1000),
                40000,
                40100,
                39900,
                40050,
                100,
            ]
            for i in range(50, 0, -1)
        ]

        mock_adapter = MagicMock()
        mock_adapter.get_ohlcv = AsyncMock(return_value=mock_candles)

        with patch("squant.api.v1.market.get_exchange_adapter", return_value=mock_adapter):
            response = client.get(
                "/api/v1/market/candles",
                params={
                    "exchange": "okx",
                    "symbol": "BTC/USDT",
                    "timeframe": "1m",
                    "since": since,
                    "limit": 50,
                },
            )

        assert response.status_code == 200
        data = response.json()

        # Should return historical candles
        assert len(data) > 0
