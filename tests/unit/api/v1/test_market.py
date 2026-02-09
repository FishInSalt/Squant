"""Unit tests for market API endpoints."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from squant.api.deps import get_exchange
from squant.infra.exchange.types import Candlestick, Ticker
from squant.main import app


@pytest.fixture
def mock_exchange():
    """Create mock exchange adapter."""
    exchange = MagicMock()
    exchange.get_ticker = AsyncMock()
    exchange.get_tickers = AsyncMock()
    exchange.get_candlesticks = AsyncMock()
    return exchange


@pytest_asyncio.fixture
async def client(mock_exchange) -> AsyncGenerator[AsyncClient, None]:
    """Create async test client with mocked exchange dependency."""

    async def override_exchange() -> AsyncGenerator[MagicMock, None]:
        yield mock_exchange

    app.dependency_overrides[get_exchange] = override_exchange
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def mock_ticker() -> Ticker:
    """Create mock ticker data."""
    return Ticker(
        symbol="BTC/USDT",
        last=42000.5,
        bid=42000.0,
        ask=42001.0,
        high_24h=43000.0,
        low_24h=41000.0,
        volume_24h=1000.0,
        volume_quote_24h=42000000.0,
        change_24h=500.0,
        change_pct_24h=1.2,
        timestamp=datetime.now(UTC),
    )


@pytest.fixture
def mock_candles() -> list[Candlestick]:
    """Create mock candlestick data."""
    now = datetime.now(UTC)
    return [
        Candlestick(
            timestamp=now,
            open=42000.0,
            high=42100.0,
            low=41900.0,
            close=42050.0,
            volume=100.0,
        ),
        Candlestick(
            timestamp=now,
            open=42050.0,
            high=42150.0,
            low=42000.0,
            close=42100.0,
            volume=150.0,
        ),
    ]


class TestGetExchangeConfig:
    """Tests for GET /api/v1/market/exchange endpoint."""

    @pytest.mark.asyncio
    async def test_get_exchange_config_success(self, client: AsyncClient) -> None:
        """Test getting exchange configuration."""
        response = await client.get("/api/v1/market/exchange")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "current" in data["data"]
        assert "supported" in data["data"]
        assert isinstance(data["data"]["supported"], list)

    @pytest.mark.asyncio
    async def test_exchange_config_contains_okx(self, client: AsyncClient) -> None:
        """Test that supported exchanges include OKX."""
        response = await client.get("/api/v1/market/exchange")

        data = response.json()
        assert "okx" in data["data"]["supported"]


class TestSetExchange:
    """Tests for PUT /api/v1/market/exchange/{exchange_id} endpoint."""

    @pytest.mark.asyncio
    async def test_set_exchange_success(self, client: AsyncClient) -> None:
        """Test switching to a valid exchange."""
        with patch("squant.api.v1.market.get_stream_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.switch_exchange = AsyncMock()
            mock_get_manager.return_value = mock_manager

            response = await client.put("/api/v1/market/exchange/binance")

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["current"] == "binance"

    @pytest.mark.asyncio
    async def test_set_exchange_invalid(self, client: AsyncClient) -> None:
        """Test switching to an invalid exchange."""
        response = await client.put("/api/v1/market/exchange/invalid_exchange")

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_set_exchange_case_insensitive(self, client: AsyncClient) -> None:
        """Test exchange ID is case insensitive."""
        with patch("squant.api.v1.market.get_stream_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.switch_exchange = AsyncMock()
            mock_get_manager.return_value = mock_manager

            response = await client.put("/api/v1/market/exchange/BINANCE")

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["current"] == "binance"

    @pytest.mark.asyncio
    async def test_set_exchange_stream_manager_error(self, client: AsyncClient) -> None:
        """Test switching exchange continues when stream manager fails."""
        with patch("squant.api.v1.market.get_stream_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.switch_exchange = AsyncMock(side_effect=Exception("WebSocket error"))
            mock_get_manager.return_value = mock_manager

            # Should still succeed - REST API continues even if WebSocket fails
            response = await client.put("/api/v1/market/exchange/okx")

            assert response.status_code == 200


class TestGetTicker:
    """Tests for GET /api/v1/market/ticker/{symbol} endpoint."""

    @pytest.mark.asyncio
    async def test_get_ticker_success(
        self, client: AsyncClient, mock_ticker: Ticker, mock_exchange
    ) -> None:
        """Test getting ticker for a symbol."""
        mock_exchange.get_ticker = AsyncMock(return_value=mock_ticker)

        response = await client.get("/api/v1/market/ticker/BTC/USDT")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["symbol"] == "BTC/USDT"
        # API may return numbers as strings for precision
        assert float(data["data"]["last"]) == 42000.5
        assert float(data["data"]["bid"]) == 42000.0
        assert float(data["data"]["ask"]) == 42001.0

    @pytest.mark.asyncio
    async def test_get_ticker_symbol_with_dash(self, client: AsyncClient, mock_exchange) -> None:
        """Test getting ticker with dash-separated symbol."""
        mock_ticker_eth = Ticker(
            symbol="ETH/USDT",
            last=2500.0,
            bid=2499.0,
            ask=2501.0,
            high_24h=2600.0,
            low_24h=2400.0,
            volume_24h=5000.0,
            volume_quote_24h=12500000.0,
            change_24h=50.0,
            change_pct_24h=2.0,
            timestamp=datetime.now(UTC),
        )
        mock_exchange.get_ticker = AsyncMock(return_value=mock_ticker_eth)

        response = await client.get("/api/v1/market/ticker/ETH/USDT")

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["symbol"] == "ETH/USDT"

    @pytest.mark.asyncio
    async def test_get_ticker_exchange_error(self, client: AsyncClient, mock_exchange) -> None:
        """Test getting ticker when exchange returns error."""
        from squant.infra.exchange.exceptions import ExchangeError

        mock_exchange.get_ticker = AsyncMock(side_effect=ExchangeError("Symbol not found"))

        response = await client.get("/api/v1/market/ticker/INVALID/SYMBOL")

        assert response.status_code == 502


class TestGetTickers:
    """Tests for GET /api/v1/market/tickers endpoint."""

    @pytest.mark.asyncio
    async def test_get_tickers_all(self, client: AsyncClient, mock_exchange) -> None:
        """Test getting all tickers."""
        mock_tickers = [
            Ticker(
                symbol="BTC/USDT",
                last=42000.0,
                bid=41999.0,
                ask=42001.0,
                high_24h=43000.0,
                low_24h=41000.0,
                volume_24h=1000.0,
                volume_quote_24h=42000000.0,
                change_24h=500.0,
                change_pct_24h=1.2,
                timestamp=datetime.now(UTC),
            ),
            Ticker(
                symbol="ETH/USDT",
                last=2500.0,
                bid=2499.0,
                ask=2501.0,
                high_24h=2600.0,
                low_24h=2400.0,
                volume_24h=5000.0,
                volume_quote_24h=12500000.0,
                change_24h=50.0,
                change_pct_24h=2.0,
                timestamp=datetime.now(UTC),
            ),
        ]
        mock_exchange.get_tickers = AsyncMock(return_value=mock_tickers)

        response = await client.get("/api/v1/market/tickers")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert len(data["data"]) == 2

    @pytest.mark.asyncio
    async def test_get_tickers_filtered_by_symbols(
        self, client: AsyncClient, mock_exchange
    ) -> None:
        """Test getting tickers filtered by symbols."""
        mock_ticker = Ticker(
            symbol="BTC/USDT",
            last=42000.0,
            bid=41999.0,
            ask=42001.0,
            high_24h=43000.0,
            low_24h=41000.0,
            volume_24h=1000.0,
            volume_quote_24h=42000000.0,
            change_24h=500.0,
            change_pct_24h=1.2,
            timestamp=datetime.now(UTC),
        )
        mock_exchange.get_tickers = AsyncMock(return_value=[mock_ticker])

        response = await client.get("/api/v1/market/tickers?symbols=BTC/USDT")

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["symbol"] == "BTC/USDT"

    @pytest.mark.asyncio
    async def test_get_tickers_sorted_by_volume(self, client: AsyncClient, mock_exchange) -> None:
        """Test getting tickers sorted by volume."""
        mock_tickers = [
            Ticker(
                symbol="LOW/USDT",
                last=100.0,
                bid=99.0,
                ask=101.0,
                volume_quote_24h=1000.0,
                timestamp=datetime.now(UTC),
            ),
            Ticker(
                symbol="HIGH/USDT",
                last=200.0,
                bid=199.0,
                ask=201.0,
                volume_quote_24h=10000000.0,
                timestamp=datetime.now(UTC),
            ),
        ]
        mock_exchange.get_tickers = AsyncMock(return_value=mock_tickers)

        response = await client.get("/api/v1/market/tickers?sort_by=volume_quote_24h&order=desc")

        assert response.status_code == 200
        data = response.json()
        # High volume should be first with descending order
        assert data["data"][0]["symbol"] == "HIGH/USDT"

    @pytest.mark.asyncio
    async def test_get_tickers_sorted_ascending(self, client: AsyncClient, mock_exchange) -> None:
        """Test getting tickers sorted in ascending order."""
        mock_tickers = [
            Ticker(
                symbol="HIGH/USDT",
                last=200.0,
                bid=199.0,
                ask=201.0,
                volume_quote_24h=10000000.0,
                timestamp=datetime.now(UTC),
            ),
            Ticker(
                symbol="LOW/USDT",
                last=100.0,
                bid=99.0,
                ask=101.0,
                volume_quote_24h=1000.0,
                timestamp=datetime.now(UTC),
            ),
        ]
        mock_exchange.get_tickers = AsyncMock(return_value=mock_tickers)

        response = await client.get("/api/v1/market/tickers?sort_by=volume_quote_24h&order=asc")

        assert response.status_code == 200
        data = response.json()
        # Low volume should be first with ascending order
        assert data["data"][0]["symbol"] == "LOW/USDT"

    @pytest.mark.asyncio
    async def test_get_tickers_with_limit(self, client: AsyncClient, mock_exchange) -> None:
        """Test getting tickers with limit."""
        mock_tickers = [
            Ticker(
                symbol=f"TOKEN{i}/USDT",
                last=100.0 + i,
                bid=99.0 + i,
                ask=101.0 + i,
                timestamp=datetime.now(UTC),
            )
            for i in range(10)
        ]
        mock_exchange.get_tickers = AsyncMock(return_value=mock_tickers)

        response = await client.get("/api/v1/market/tickers?limit=3")

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 3

    @pytest.mark.asyncio
    async def test_get_tickers_invalid_limit(self, client: AsyncClient) -> None:
        """Test getting tickers with invalid limit."""
        response = await client.get("/api/v1/market/tickers?limit=0")
        assert response.status_code == 422

        response = await client.get("/api/v1/market/tickers?limit=501")
        assert response.status_code == 422


class TestGetCandles:
    """Tests for GET /api/v1/market/candles/{symbol} endpoint."""

    @pytest.mark.asyncio
    async def test_get_candles_success(
        self, client: AsyncClient, mock_candles: list[Candlestick], mock_exchange
    ) -> None:
        """Test getting candles for a symbol."""
        mock_exchange.get_candlesticks = AsyncMock(return_value=mock_candles)

        response = await client.get("/api/v1/market/candles/BTC/USDT?timeframe=1h")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["symbol"] == "BTC/USDT"
        assert data["data"]["timeframe"] == "1h"
        assert len(data["data"]["candles"]) == 2

    @pytest.mark.asyncio
    async def test_get_candles_default_timeframe(
        self, client: AsyncClient, mock_candles: list[Candlestick], mock_exchange
    ) -> None:
        """Test getting candles with default timeframe."""
        mock_exchange.get_candlesticks = AsyncMock(return_value=mock_candles)

        response = await client.get("/api/v1/market/candles/BTC/USDT")

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["timeframe"] == "1h"

    @pytest.mark.asyncio
    async def test_get_candles_all_timeframes(
        self, client: AsyncClient, mock_candles: list[Candlestick], mock_exchange
    ) -> None:
        """Test getting candles for all supported timeframes."""
        timeframes = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"]
        mock_exchange.get_candlesticks = AsyncMock(return_value=mock_candles)

        for tf in timeframes:
            response = await client.get(f"/api/v1/market/candles/BTC/USDT?timeframe={tf}")
            assert response.status_code == 200, f"Failed for timeframe {tf}"
            data = response.json()
            assert data["data"]["timeframe"] == tf

    @pytest.mark.asyncio
    async def test_get_candles_invalid_timeframe(self, client: AsyncClient) -> None:
        """Test getting candles with invalid timeframe."""
        response = await client.get("/api/v1/market/candles/BTC/USDT?timeframe=invalid")

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_get_candles_with_limit(
        self, client: AsyncClient, mock_candles: list[Candlestick], mock_exchange
    ) -> None:
        """Test getting candles with custom limit."""
        mock_exchange.get_candlesticks = AsyncMock(return_value=mock_candles)

        response = await client.get("/api/v1/market/candles/BTC/USDT?limit=50")

        assert response.status_code == 200
        # Verify limit was passed to exchange
        mock_exchange.get_candlesticks.assert_called_once()
        call_kwargs = mock_exchange.get_candlesticks.call_args[1]
        assert call_kwargs["limit"] == 50

    @pytest.mark.asyncio
    async def test_get_candles_invalid_limit(self, client: AsyncClient) -> None:
        """Test getting candles with invalid limit."""
        response = await client.get("/api/v1/market/candles/BTC/USDT?limit=0")
        assert response.status_code == 422

        response = await client.get("/api/v1/market/candles/BTC/USDT?limit=301")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_candles_exchange_error(self, client: AsyncClient, mock_exchange) -> None:
        """Test getting candles when exchange returns error."""
        from squant.infra.exchange.exceptions import ExchangeError

        mock_exchange.get_candlesticks = AsyncMock(side_effect=ExchangeError("Rate limit exceeded"))

        response = await client.get("/api/v1/market/candles/BTC/USDT")

        assert response.status_code == 502


class TestCandleDataIntegrity:
    """Tests for candle data structure and values."""

    @pytest.mark.asyncio
    async def test_candle_has_all_fields(
        self, client: AsyncClient, mock_candles: list[Candlestick], mock_exchange
    ) -> None:
        """Test that candle response includes all OHLCV fields."""
        mock_exchange.get_candlesticks = AsyncMock(return_value=mock_candles)

        response = await client.get("/api/v1/market/candles/BTC/USDT")

        assert response.status_code == 200
        data = response.json()
        candle = data["data"]["candles"][0]

        assert "timestamp" in candle
        assert "open" in candle
        assert "high" in candle
        assert "low" in candle
        assert "close" in candle
        assert "volume" in candle


class TestTickerDataIntegrity:
    """Tests for ticker data structure and values."""

    @pytest.mark.asyncio
    async def test_ticker_has_all_fields(
        self, client: AsyncClient, mock_ticker: Ticker, mock_exchange
    ) -> None:
        """Test that ticker response includes all fields."""
        mock_exchange.get_ticker = AsyncMock(return_value=mock_ticker)

        response = await client.get("/api/v1/market/ticker/BTC/USDT")

        assert response.status_code == 200
        data = response.json()
        ticker = data["data"]

        assert "symbol" in ticker
        assert "last" in ticker
        assert "bid" in ticker
        assert "ask" in ticker
        assert "high_24h" in ticker
        assert "low_24h" in ticker
        assert "volume_24h" in ticker
        assert "volume_quote_24h" in ticker
        assert "change_24h" in ticker
        assert "change_pct_24h" in ticker
        assert "timestamp" in ticker
