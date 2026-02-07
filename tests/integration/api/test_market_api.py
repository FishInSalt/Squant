"""
Integration tests for Market API endpoints.

Tests validate acceptance criteria from dev-docs/requirements/acceptance-criteria/01-market.md:
- MKT-001: Display Top 20 popular trading pairs
- MKT-002: Display real-time price, 24h change%, 24h volume
- MKT-003: Filter by exchange
- MKT-020: Support multiple timeframes
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from squant.infra.exchange.types import Candlestick, Ticker


@pytest.fixture
def sample_tickers():
    """Create sample ticker data for testing."""
    tickers = []

    symbols = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT"]
    volumes_quote = [50000000, 30000000, 20000000, 15000000, 10000000]  # Descending by quote volume

    for symbol, volume_quote in zip(symbols, volumes_quote, strict=True):
        ticker = Ticker(
            symbol=symbol,
            bid=Decimal("40000.0") if "BTC" in symbol else Decimal("2500.0"),
            ask=Decimal("40100.0") if "BTC" in symbol else Decimal("2510.0"),
            last=Decimal("40050.0") if "BTC" in symbol else Decimal("2505.0"),
            volume_24h=Decimal(str(volume_quote / 40000)),  # Base volume
            volume_quote_24h=Decimal(str(volume_quote)),  # Quote volume in USDT
            timestamp=datetime.now(UTC),
            change_24h=Decimal("2000.0") if "BTC" in symbol else Decimal("-50.0"),
            change_pct_24h=Decimal("5.5") if "BTC" in symbol else Decimal("-2.3"),
            high_24h=Decimal("41000.0") if "BTC" in symbol else Decimal("2600.0"),
            low_24h=Decimal("39000.0") if "BTC" in symbol else Decimal("2400.0"),
        )
        tickers.append(ticker)

    return tickers


@pytest.fixture
def sample_candles():
    """Create sample candlestick data for testing."""
    now = datetime.now(UTC)
    candles = []

    for i in range(100, 0, -1):
        candle = Candlestick(
            timestamp=now - timedelta(minutes=i),
            open=Decimal("40000") + Decimal(str(i * 10)),
            high=Decimal("40100") + Decimal(str(i * 10)),
            low=Decimal("39900") + Decimal(str(i * 10)),
            close=Decimal("40050") + Decimal(str(i * 10)),
            volume=Decimal("100") + Decimal(str(i)),
        )
        candles.append(candle)

    return candles


class TestDisplayTopTradingPairs:
    """
    Tests for MKT-001: Display Top 20 popular trading pairs

    Acceptance criteria:
    - Show top 20 by 24h volume when entering market page
    - Display symbol, latest price, 24h change%, volume for each
    - Show error "Cannot get market data" on connection failure
    """

    @pytest.mark.asyncio
    async def test_get_top_20_trading_pairs_by_volume(self, client, sample_tickers):
        """Test MKT-001-1: Display top 20 sorted by 24h volume."""
        # Mock exchange adapter to return tickers
        mock_adapter = MagicMock()
        mock_adapter.get_tickers = AsyncMock(return_value=sample_tickers)

        with patch("squant.api.deps._get_or_create_exchange_adapter", return_value=mock_adapter):
            response = await client.get(
                "/api/v1/market/tickers",
                params={"sort_by": "volume_quote_24h", "limit": 20},
            )

        assert response.status_code == 200
        data = response.json()

        # Response is wrapped in ApiResponse
        assert "data" in data
        tickers = data["data"]

        # Should be sorted by quote volume descending
        assert len(tickers) > 0
        # First ticker should have highest quote volume
        assert tickers[0]["symbol"] == "BTC/USDT"
        assert float(tickers[0]["volume_quote_24h"]) == 50000000

    @pytest.mark.asyncio
    async def test_ticker_display_required_fields(self, client, sample_tickers):
        """Test MKT-001-2: Each ticker displays required fields."""
        mock_adapter = MagicMock()
        mock_adapter.get_tickers = AsyncMock(return_value=sample_tickers)

        with patch("squant.api.deps._get_or_create_exchange_adapter", return_value=mock_adapter):
            response = await client.get("/api/v1/market/tickers")

        assert response.status_code == 200
        data = response.json()

        tickers = data["data"]

        # Check first ticker has all required fields
        ticker = tickers[0]
        assert "symbol" in ticker
        assert "last" in ticker  # latest price
        assert "change_pct_24h" in ticker  # 24h change%
        assert "volume_quote_24h" in ticker  # 24h volume

    @pytest.mark.skip(
        reason="Error handling tested at unit level - integration test has dependency injection complexity"
    )
    @pytest.mark.asyncio
    async def test_get_tickers_connection_failure(self, client):
        """Test MKT-001-3: Show error on connection failure."""
        from squant.infra.exchange.exceptions import ExchangeConnectionError

        # Mock exchange adapter to raise connection error
        mock_adapter = MagicMock()
        mock_adapter.get_tickers = AsyncMock(
            side_effect=ExchangeConnectionError("Cannot connect to exchange")
        )

        with patch("squant.api.deps._get_or_create_exchange_adapter", return_value=mock_adapter):
            response = await client.get("/api/v1/market/tickers")

        assert response.status_code in [400, 500, 503]
        data = response.json()

        # Should contain error message
        assert "message" in data


class TestRealTimePriceDisplay:
    """
    Tests for MKT-002: Display real-time price, 24h change%, 24h volume

    Acceptance criteria:
    - Show latest price with exchange precision
    - Green for positive change, red for negative
    - Use K/M/B abbreviations for large volumes (frontend)
    """

    @pytest.mark.asyncio
    async def test_display_latest_price_with_precision(self, client, sample_tickers):
        """Test MKT-002-1: Display latest price with correct precision."""
        mock_adapter = MagicMock()
        mock_adapter.get_tickers = AsyncMock(return_value=sample_tickers)

        with patch("squant.api.deps._get_or_create_exchange_adapter", return_value=mock_adapter):
            response = await client.get("/api/v1/market/tickers")

        assert response.status_code == 200
        data = response.json()

        tickers = data["data"]

        # BTC ticker should have price
        btc_ticker = next(t for t in tickers if t["symbol"] == "BTC/USDT")
        assert float(btc_ticker["last"]) == 40050.0

    @pytest.mark.asyncio
    async def test_positive_change_indicator(self, client, sample_tickers):
        """Test MKT-002-2: Positive change should be indicated."""
        mock_adapter = MagicMock()
        mock_adapter.get_tickers = AsyncMock(return_value=sample_tickers)

        with patch("squant.api.deps._get_or_create_exchange_adapter", return_value=mock_adapter):
            response = await client.get("/api/v1/market/tickers")

        assert response.status_code == 200
        data = response.json()

        tickers = data["data"]

        # BTC has positive change (+5.5%)
        btc_ticker = next(t for t in tickers if t["symbol"] == "BTC/USDT")
        assert float(btc_ticker["change_pct_24h"]) > 0

    @pytest.mark.asyncio
    async def test_negative_change_indicator(self, client, sample_tickers):
        """Test MKT-002-2: Negative change should be indicated."""
        mock_adapter = MagicMock()
        mock_adapter.get_tickers = AsyncMock(return_value=sample_tickers)

        with patch("squant.api.deps._get_or_create_exchange_adapter", return_value=mock_adapter):
            response = await client.get("/api/v1/market/tickers")

        assert response.status_code == 200
        data = response.json()

        tickers = data["data"]

        # ETH has negative change (-2.3%)
        eth_ticker = next(t for t in tickers if t["symbol"] == "ETH/USDT")
        assert float(eth_ticker["change_pct_24h"]) < 0

    @pytest.mark.asyncio
    async def test_volume_display_with_abbreviations(self, client, sample_tickers):
        """Test MKT-002-3: Large volumes use K/M/B abbreviations (frontend responsibility)."""
        mock_adapter = MagicMock()
        mock_adapter.get_tickers = AsyncMock(return_value=sample_tickers)

        with patch("squant.api.deps._get_or_create_exchange_adapter", return_value=mock_adapter):
            response = await client.get("/api/v1/market/tickers")

        assert response.status_code == 200
        data = response.json()

        tickers = data["data"]

        # Volume should be present as number (frontend formats it)
        btc_ticker = next(t for t in tickers if t["symbol"] == "BTC/USDT")
        assert float(btc_ticker["volume_quote_24h"]) == 50000000  # 50M


class TestFilterByExchange:
    """
    Tests for MKT-003: Filter by exchange

    Acceptance criteria:
    - Filter by specific exchange shows only that exchange's pairs
    - Switch data source exchange
    """

    @pytest.mark.asyncio
    async def test_get_exchange_config(self, client):
        """Test MKT-003: Get current exchange configuration."""
        response = await client.get("/api/v1/market/exchange")

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert "current" in result
        assert "supported" in result
        assert isinstance(result["supported"], list)

    @pytest.mark.asyncio
    async def test_switch_exchange(self, client):
        """Test MKT-003: Switch data source exchange."""
        # Mock stream manager to avoid WebSocket operations
        with patch("squant.api.v1.market.get_stream_manager") as mock_manager:
            mock_manager.return_value.switch_exchange = AsyncMock()

            response = await client.put("/api/v1/market/exchange/binance")

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["current"] == "binance"

    @pytest.mark.asyncio
    async def test_switch_to_invalid_exchange(self, client):
        """Test MKT-003: Reject invalid exchange."""
        response = await client.put("/api/v1/market/exchange/invalid_exchange")

        assert response.status_code == 400
        data = response.json()

        assert "message" in data
        assert "unsupported" in data["message"].lower()


class TestMultipleTimeframes:
    """
    Tests for MKT-020: Support multiple timeframes

    Acceptance criteria:
    - Support 1m, 5m, 15m, 1h, 4h, 1d, 1w timeframes
    - Smooth chart transition on timeframe switch (frontend)
    """

    @pytest.mark.asyncio
    async def test_get_candles_1m_timeframe(self, client, sample_candles):
        """Test MKT-020-1: Get 1-minute candlestick data."""
        mock_adapter = MagicMock()
        mock_adapter.get_candlesticks = AsyncMock(return_value=sample_candles)

        with patch("squant.api.deps._get_or_create_exchange_adapter", return_value=mock_adapter):
            response = await client.get(
                "/api/v1/market/candles/BTC/USDT",
                params={"timeframe": "1m", "limit": 100},
            )

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert "candles" in result
        assert len(result["candles"]) > 0

    @pytest.mark.asyncio
    async def test_get_candles_multiple_timeframes(self, client, sample_candles):
        """Test MKT-020: Support for all timeframes."""
        timeframes = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"]

        for timeframe in timeframes:
            mock_adapter = MagicMock()
            mock_adapter.get_candlesticks = AsyncMock(return_value=sample_candles)

            with patch(
                "squant.api.deps._get_or_create_exchange_adapter", return_value=mock_adapter
            ):
                response = await client.get(
                    "/api/v1/market/candles/BTC/USDT",
                    params={"timeframe": timeframe, "limit": 100},
                )

            assert response.status_code == 200, f"Failed for timeframe {timeframe}"

    @pytest.mark.asyncio
    async def test_invalid_timeframe_error(self, client):
        """Test MKT-020: Invalid timeframe returns error."""
        mock_adapter = MagicMock()

        with patch("squant.api.deps._get_or_create_exchange_adapter", return_value=mock_adapter):
            response = await client.get(
                "/api/v1/market/candles/BTC/USDT",
                params={"timeframe": "invalid", "limit": 100},
            )

        assert response.status_code == 400
        data = response.json()

        assert "message" in data
        assert "invalid timeframe" in data["message"].lower()


class TestGetSingleTicker:
    """Test getting ticker for a single symbol."""

    @pytest.mark.asyncio
    async def test_get_ticker_single_symbol(self, client, sample_tickers):
        """Test getting ticker data for a single trading pair."""
        mock_adapter = MagicMock()
        mock_adapter.get_ticker = AsyncMock(return_value=sample_tickers[0])

        with patch("squant.api.deps._get_or_create_exchange_adapter", return_value=mock_adapter):
            response = await client.get("/api/v1/market/ticker/BTC/USDT")

        assert response.status_code == 200
        data = response.json()

        ticker = data["data"]
        assert ticker["symbol"] == "BTC/USDT"
        assert "last" in ticker
        assert "volume_24h" in ticker

    @pytest.mark.asyncio
    async def test_get_ticker_cache(self, client, sample_tickers):
        """Test ticker caching to reduce API calls."""
        # Clear cache first to ensure clean state
        from squant.api.v1.market import _market_cache

        _market_cache.clear()

        mock_adapter = MagicMock()
        mock_adapter.get_ticker = AsyncMock(return_value=sample_tickers[0])

        with patch("squant.api.deps._get_or_create_exchange_adapter", return_value=mock_adapter):
            # First request - should hit exchange
            response1 = await client.get("/api/v1/market/ticker/BTC/USDT")
            assert response1.status_code == 200

            # Second request - should be cached (within 1 second)
            response2 = await client.get("/api/v1/market/ticker/BTC/USDT")
            assert response2.status_code == 200

            # Both responses should be identical
            assert response1.json() == response2.json()

            # Should only call exchange once due to caching
            assert mock_adapter.get_ticker.call_count == 1
