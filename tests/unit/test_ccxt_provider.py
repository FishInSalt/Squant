"""Unit tests for CCXTStreamProvider."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from squant.infra.exchange.ccxt.provider import CCXTStreamProvider
from squant.infra.exchange.ccxt.types import SUPPORTED_EXCHANGES, ExchangeCredentials
from squant.infra.exchange.exceptions import (
    ExchangeAuthenticationError,
    ExchangeConnectionError,
)


class TestCCXTStreamProviderInit:
    """Tests for CCXTStreamProvider initialization."""

    def test_init_supported_exchange(self) -> None:
        """Test initializing with a supported exchange."""
        for exchange_id in SUPPORTED_EXCHANGES:
            provider = CCXTStreamProvider(exchange_id)
            assert provider.exchange_id == exchange_id
            assert provider.is_connected is False

    def test_init_unsupported_exchange(self) -> None:
        """Test that unsupported exchanges raise ValueError."""
        with pytest.raises(ValueError, match="Unsupported exchange"):
            CCXTStreamProvider("kraken")

    def test_init_case_insensitive(self) -> None:
        """Test that exchange ID is case-insensitive."""
        provider = CCXTStreamProvider("OKX")
        assert provider.exchange_id == "okx"

        provider = CCXTStreamProvider("BINANCE")
        assert provider.exchange_id == "binance"

    def test_init_with_credentials(self) -> None:
        """Test initializing with credentials."""
        credentials = ExchangeCredentials(
            api_key="test-key",
            api_secret="test-secret",
            passphrase="test-pass",
            sandbox=True,
        )
        provider = CCXTStreamProvider("okx", credentials)
        assert provider._credentials == credentials


class TestCCXTStreamProviderConnect:
    """Tests for CCXTStreamProvider connection."""

    @pytest.mark.asyncio
    async def test_connect_creates_exchange_instance(self) -> None:
        """Test that connect creates the exchange instance."""
        provider = CCXTStreamProvider("okx")

        with patch("squant.infra.exchange.ccxt.provider.ccxtpro") as mock_ccxt:
            mock_exchange = MagicMock()
            mock_exchange.load_markets = AsyncMock()
            mock_ccxt.okx.return_value = mock_exchange

            await provider.connect()

            assert provider.is_connected is True
            mock_ccxt.okx.assert_called_once()
            mock_exchange.load_markets.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_with_credentials(self) -> None:
        """Test that credentials are passed to exchange."""
        credentials = ExchangeCredentials(
            api_key="test-key",
            api_secret="test-secret",
            passphrase="test-pass",
            sandbox=True,
        )
        provider = CCXTStreamProvider("okx", credentials)

        with patch("squant.infra.exchange.ccxt.provider.ccxtpro") as mock_ccxt:
            mock_exchange = MagicMock()
            mock_exchange.load_markets = AsyncMock()
            mock_ccxt.okx.return_value = mock_exchange

            await provider.connect()

            call_args = mock_ccxt.okx.call_args[0][0]
            assert call_args["apiKey"] == "test-key"
            assert call_args["secret"] == "test-secret"
            assert call_args["password"] == "test-pass"
            assert call_args["sandbox"] is True

    @pytest.mark.asyncio
    async def test_connect_already_connected(self) -> None:
        """Test that connect is idempotent."""
        provider = CCXTStreamProvider("okx")

        with patch("squant.infra.exchange.ccxt.provider.ccxtpro") as mock_ccxt:
            mock_exchange = MagicMock()
            mock_exchange.load_markets = AsyncMock()
            mock_ccxt.okx.return_value = mock_exchange

            await provider.connect()
            await provider.connect()  # Second call should be no-op

            # Should only be called once
            assert mock_ccxt.okx.call_count == 1

    @pytest.mark.asyncio
    async def test_connect_failure_raises_exception(self) -> None:
        """Test that connection failure raises ExchangeConnectionError."""
        provider = CCXTStreamProvider("okx")

        with patch("squant.infra.exchange.ccxt.provider.ccxtpro") as mock_ccxt:
            mock_ccxt.okx.side_effect = Exception("Connection failed")

            with pytest.raises(ExchangeConnectionError):
                await provider.connect()


class TestCCXTStreamProviderClose:
    """Tests for CCXTStreamProvider close."""

    @pytest.mark.asyncio
    async def test_close_disconnects(self) -> None:
        """Test that close properly disconnects."""
        provider = CCXTStreamProvider("okx")

        with patch("squant.infra.exchange.ccxt.provider.ccxtpro") as mock_ccxt:
            mock_exchange = MagicMock()
            mock_exchange.load_markets = AsyncMock()
            mock_exchange.close = AsyncMock()
            mock_ccxt.okx.return_value = mock_exchange

            await provider.connect()
            assert provider.is_connected is True

            await provider.close()
            assert provider.is_connected is False
            mock_exchange.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_cancels_tasks(self) -> None:
        """Test that close cancels subscription tasks and clears watched symbols."""
        provider = CCXTStreamProvider("okx")

        with patch("squant.infra.exchange.ccxt.provider.ccxtpro") as mock_ccxt:
            mock_exchange = MagicMock()
            mock_exchange.load_markets = AsyncMock()
            mock_exchange.close = AsyncMock()
            mock_exchange.watch_tickers = AsyncMock(side_effect=Exception("Cancelled"))
            mock_exchange.markets = {"BTC/USDT": {"symbol": "BTC/USDT"}}
            mock_ccxt.okx.return_value = mock_exchange

            await provider.connect()

            # Start a ticker subscription (uses batch watching)
            await provider.watch_ticker("BTC/USDT")
            assert "BTC/USDT" in provider._watched_ticker_symbols
            assert provider._tickers_task is not None

            # Close should cancel the task and clear symbols
            await provider.close()
            assert len(provider._watched_ticker_symbols) == 0
            assert provider._tickers_task is None


class TestCCXTStreamProviderHandlers:
    """Tests for message handler management."""

    def test_add_handler(self) -> None:
        """Test adding a message handler."""
        provider = CCXTStreamProvider("okx")

        async def handler(msg: dict) -> None:
            pass

        provider.add_handler(handler)
        assert handler in provider._handlers

    def test_add_handler_no_duplicates(self) -> None:
        """Test that handlers are not duplicated."""
        provider = CCXTStreamProvider("okx")

        async def handler(msg: dict) -> None:
            pass

        provider.add_handler(handler)
        provider.add_handler(handler)
        assert len(provider._handlers) == 1

    def test_remove_handler(self) -> None:
        """Test removing a message handler."""
        provider = CCXTStreamProvider("okx")

        async def handler(msg: dict) -> None:
            pass

        provider.add_handler(handler)
        provider.remove_handler(handler)
        assert handler not in provider._handlers


class TestCCXTStreamProviderSubscriptions:
    """Tests for subscription methods."""

    @pytest.mark.asyncio
    async def test_watch_ticker_creates_task(self) -> None:
        """Test that watch_ticker adds symbol to batch watch list."""
        provider = CCXTStreamProvider("okx")

        with patch("squant.infra.exchange.ccxt.provider.ccxtpro") as mock_ccxt:
            mock_exchange = MagicMock()
            mock_exchange.load_markets = AsyncMock()
            mock_exchange.watch_tickers = AsyncMock(
                return_value={"BTC/USDT": {"symbol": "BTC/USDT"}}
            )
            mock_exchange.close = AsyncMock()
            mock_exchange.markets = {"BTC/USDT": {"symbol": "BTC/USDT"}}
            mock_ccxt.okx.return_value = mock_exchange

            await provider.connect()
            await provider.watch_ticker("BTC/USDT")

            # With batch ticker watching, symbol is added to _watched_ticker_symbols
            assert "BTC/USDT" in provider._watched_ticker_symbols
            # And a batch tickers task is created
            assert provider._tickers_task is not None

            await provider.close()

    @pytest.mark.asyncio
    async def test_watch_ohlcv_validates_timeframe(self) -> None:
        """Test that watch_ohlcv validates timeframe."""
        provider = CCXTStreamProvider("okx")

        with patch("squant.infra.exchange.ccxt.provider.ccxtpro") as mock_ccxt:
            mock_exchange = MagicMock()
            mock_exchange.load_markets = AsyncMock()
            mock_exchange.close = AsyncMock()
            mock_ccxt.okx.return_value = mock_exchange

            await provider.connect()

            with pytest.raises(ValueError, match="Invalid timeframe"):
                await provider.watch_ohlcv("BTC/USDT", "invalid")

            await provider.close()

    @pytest.mark.asyncio
    async def test_watch_orders_requires_credentials(self) -> None:
        """Test that private channels require credentials."""
        provider = CCXTStreamProvider("okx")  # No credentials

        with patch("squant.infra.exchange.ccxt.provider.ccxtpro") as mock_ccxt:
            mock_exchange = MagicMock()
            mock_exchange.load_markets = AsyncMock()
            mock_exchange.close = AsyncMock()
            mock_ccxt.okx.return_value = mock_exchange

            await provider.connect()

            with pytest.raises(ExchangeAuthenticationError):
                await provider.watch_orders()

            await provider.close()

    @pytest.mark.asyncio
    async def test_watch_balance_requires_credentials(self) -> None:
        """Test that balance watching requires credentials."""
        provider = CCXTStreamProvider("okx")  # No credentials

        with patch("squant.infra.exchange.ccxt.provider.ccxtpro") as mock_ccxt:
            mock_exchange = MagicMock()
            mock_exchange.load_markets = AsyncMock()
            mock_exchange.close = AsyncMock()
            mock_ccxt.okx.return_value = mock_exchange

            await provider.connect()

            with pytest.raises(ExchangeAuthenticationError):
                await provider.watch_balance()

            await provider.close()

    @pytest.mark.asyncio
    async def test_unwatch_cancels_subscription(self) -> None:
        """Test that unwatch removes symbol from batch watch list."""
        provider = CCXTStreamProvider("okx")

        with patch("squant.infra.exchange.ccxt.provider.ccxtpro") as mock_ccxt:
            mock_exchange = MagicMock()
            mock_exchange.load_markets = AsyncMock()
            mock_exchange.watch_tickers = AsyncMock(
                return_value={"BTC/USDT": {"symbol": "BTC/USDT"}}
            )
            mock_exchange.close = AsyncMock()
            mock_exchange.markets = {"BTC/USDT": {"symbol": "BTC/USDT"}}
            mock_ccxt.okx.return_value = mock_exchange

            await provider.connect()
            await provider.watch_ticker("BTC/USDT")

            assert "BTC/USDT" in provider._watched_ticker_symbols

            await provider.unwatch("ticker:BTC/USDT")

            assert "BTC/USDT" not in provider._watched_ticker_symbols

            await provider.close()


class TestCCXTStreamProviderContextManager:
    """Tests for async context manager support."""

    @pytest.mark.asyncio
    async def test_context_manager(self) -> None:
        """Test using provider as async context manager."""
        with patch("squant.infra.exchange.ccxt.provider.ccxtpro") as mock_ccxt:
            mock_exchange = MagicMock()
            mock_exchange.load_markets = AsyncMock()
            mock_exchange.close = AsyncMock()
            mock_ccxt.okx.return_value = mock_exchange

            async with CCXTStreamProvider("okx") as provider:
                assert provider.is_connected is True

            assert provider.is_connected is False
            mock_exchange.close.assert_called_once()


class TestExchangeCredentials:
    """Tests for ExchangeCredentials dataclass."""

    def test_credentials_defaults(self) -> None:
        """Test default values for credentials."""
        credentials = ExchangeCredentials(
            api_key="key",
            api_secret="secret",
        )

        assert credentials.api_key == "key"
        assert credentials.api_secret == "secret"
        assert credentials.passphrase is None
        assert credentials.sandbox is False

    def test_credentials_with_all_fields(self) -> None:
        """Test credentials with all fields set."""
        credentials = ExchangeCredentials(
            api_key="key",
            api_secret="secret",
            passphrase="pass",
            sandbox=True,
        )

        assert credentials.api_key == "key"
        assert credentials.api_secret == "secret"
        assert credentials.passphrase == "pass"
        assert credentials.sandbox is True
