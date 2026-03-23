"""Unit tests for API dependencies."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from squant.api.deps import (
    _exchange_cache,
    _get_current_exchange_id,
    _get_exchange_credentials,
    _get_or_create_exchange_adapter,
    clear_exchange_cache,
    get_exchange,
)


class TestGetOrCreateExchangeAdapter:
    """Tests for _get_or_create_exchange_adapter function."""

    @pytest.fixture(autouse=True)
    def clear_cache(self):
        """Clear exchange cache before and after each test."""
        _exchange_cache.clear()
        yield
        _exchange_cache.clear()

    @pytest.mark.asyncio
    @patch("squant.api.deps.CCXTRestAdapter")
    async def test_creates_new_adapter(self, mock_adapter_class):
        """Test creating a new adapter when cache is empty."""
        mock_adapter = MagicMock()
        mock_adapter._connected = True
        mock_adapter.connect = AsyncMock()
        mock_adapter_class.return_value = mock_adapter

        result = await _get_or_create_exchange_adapter("okx")

        mock_adapter_class.assert_called_once_with("okx", None)
        mock_adapter.connect.assert_called_once()
        assert result == mock_adapter
        assert "okx" in _exchange_cache

    @pytest.mark.asyncio
    @patch("squant.api.deps.CCXTRestAdapter")
    async def test_reuses_cached_adapter(self, mock_adapter_class):
        """Test reusing a cached connected adapter."""
        mock_adapter = MagicMock()
        mock_adapter._connected = True
        _exchange_cache["okx"] = mock_adapter

        result = await _get_or_create_exchange_adapter("okx")

        # Should not create a new adapter
        mock_adapter_class.assert_not_called()
        assert result == mock_adapter

    @pytest.mark.asyncio
    @patch("squant.api.deps.CCXTRestAdapter")
    async def test_replaces_disconnected_adapter(self, mock_adapter_class):
        """Test replacing a disconnected adapter."""
        # Old disconnected adapter
        old_adapter = MagicMock()
        old_adapter._connected = False
        _exchange_cache["okx"] = old_adapter

        # New adapter
        new_adapter = MagicMock()
        new_adapter._connected = True
        new_adapter.connect = AsyncMock()
        mock_adapter_class.return_value = new_adapter

        result = await _get_or_create_exchange_adapter("okx")

        mock_adapter_class.assert_called_once()
        assert result == new_adapter
        assert _exchange_cache["okx"] == new_adapter

    @pytest.mark.asyncio
    @patch("squant.api.deps.CCXTRestAdapter")
    async def test_different_exchanges(self, mock_adapter_class):
        """Test caching different exchanges separately."""
        mock_adapter_okx = MagicMock()
        mock_adapter_okx._connected = True
        mock_adapter_okx.connect = AsyncMock()

        mock_adapter_binance = MagicMock()
        mock_adapter_binance._connected = True
        mock_adapter_binance.connect = AsyncMock()

        mock_adapter_class.side_effect = [mock_adapter_okx, mock_adapter_binance]

        result_okx = await _get_or_create_exchange_adapter("okx")
        result_binance = await _get_or_create_exchange_adapter("binance")

        assert result_okx == mock_adapter_okx
        assert result_binance == mock_adapter_binance
        assert "okx" in _exchange_cache
        assert "binance" in _exchange_cache


class TestGetCurrentExchangeId:
    """Tests for _get_current_exchange_id function."""

    @patch("squant.api.v1.market.get_current_exchange")
    def test_returns_current_exchange(self, mock_get_current_exchange):
        """Test returns the current exchange ID."""
        mock_get_current_exchange.return_value = "binance"

        result = _get_current_exchange_id()

        assert result == "binance"
        mock_get_current_exchange.assert_called_once()


class TestClearExchangeCache:
    """Tests for clear_exchange_cache function."""

    @pytest.fixture(autouse=True)
    def clear_cache(self):
        """Clear exchange cache before and after each test."""
        _exchange_cache.clear()
        yield
        _exchange_cache.clear()

    @pytest.mark.asyncio
    async def test_clear_specific_exchange(self):
        """Test clearing a specific exchange from cache."""
        mock_adapter = MagicMock()
        mock_adapter.close = AsyncMock()
        _exchange_cache["okx"] = mock_adapter
        _exchange_cache["binance"] = MagicMock()

        await clear_exchange_cache("okx")

        assert "okx" not in _exchange_cache
        assert "binance" in _exchange_cache
        mock_adapter.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_all_exchanges(self):
        """Test clearing all exchanges from cache."""
        mock_adapter1 = MagicMock()
        mock_adapter1.close = AsyncMock()
        mock_adapter2 = MagicMock()
        mock_adapter2.close = AsyncMock()

        _exchange_cache["okx"] = mock_adapter1
        _exchange_cache["binance"] = mock_adapter2

        await clear_exchange_cache()

        assert len(_exchange_cache) == 0
        mock_adapter1.close.assert_called_once()
        mock_adapter2.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_nonexistent_exchange(self):
        """Test clearing nonexistent exchange doesn't error."""
        await clear_exchange_cache("nonexistent")
        # Should not raise


class TestGetExchangeCredentials:
    """Tests for _get_exchange_credentials function."""

    @patch("squant.api.deps.get_settings")
    def test_okx_credentials(self, mock_get_settings):
        """Test getting OKX credentials."""
        mock_settings = MagicMock()
        mock_settings.okx_api_key = MagicMock()
        mock_settings.okx_api_key.get_secret_value.return_value = "test-key"
        mock_settings.okx_api_secret = MagicMock()
        mock_settings.okx_api_secret.get_secret_value.return_value = "test-secret"
        mock_settings.okx_passphrase = MagicMock()
        mock_settings.okx_passphrase.get_secret_value.return_value = "test-passphrase"
        mock_get_settings.return_value = mock_settings

        credentials = _get_exchange_credentials("okx")

        assert credentials is not None
        assert credentials.api_key == "test-key"
        assert credentials.api_secret == "test-secret"
        assert credentials.passphrase == "test-passphrase"
        assert credentials.sandbox is False

    @patch("squant.api.deps.get_settings")
    def test_okx_no_credentials(self, mock_get_settings):
        """Test returns None when OKX credentials not configured."""
        mock_settings = MagicMock()
        mock_settings.okx_api_key = None
        mock_settings.okx_api_secret = None
        mock_get_settings.return_value = mock_settings

        credentials = _get_exchange_credentials("okx")

        assert credentials is None

    @patch("squant.api.deps.get_settings")
    def test_binance_credentials(self, mock_get_settings):
        """Test getting Binance credentials."""
        mock_settings = MagicMock()
        mock_settings.binance_api_key = MagicMock()
        mock_settings.binance_api_key.get_secret_value.return_value = "binance-key"
        mock_settings.binance_api_secret = MagicMock()
        mock_settings.binance_api_secret.get_secret_value.return_value = "binance-secret"
        mock_get_settings.return_value = mock_settings

        credentials = _get_exchange_credentials("binance")

        assert credentials is not None
        assert credentials.api_key == "binance-key"
        assert credentials.api_secret == "binance-secret"
        assert credentials.passphrase is None  # Binance doesn't use passphrase

    @patch("squant.api.deps.get_settings")
    def test_bybit_credentials(self, mock_get_settings):
        """Test getting Bybit credentials."""
        mock_settings = MagicMock()
        mock_settings.bybit_api_key = MagicMock()
        mock_settings.bybit_api_key.get_secret_value.return_value = "bybit-key"
        mock_settings.bybit_api_secret = MagicMock()
        mock_settings.bybit_api_secret.get_secret_value.return_value = "bybit-secret"
        mock_get_settings.return_value = mock_settings

        credentials = _get_exchange_credentials("bybit")

        assert credentials is not None
        assert credentials.api_key == "bybit-key"
        assert credentials.sandbox is False

    @patch("squant.api.deps.get_settings")
    def test_unknown_exchange(self, mock_get_settings):
        """Test returns None for unknown exchange."""
        mock_settings = MagicMock()
        mock_get_settings.return_value = mock_settings

        credentials = _get_exchange_credentials("unknown")

        assert credentials is None

    @patch("squant.api.deps.get_settings")
    def test_okx_partial_credentials_key_only(self, mock_get_settings):
        """Test returns None when only API key is configured (no secret)."""
        mock_settings = MagicMock()
        mock_settings.okx_api_key = MagicMock()
        mock_settings.okx_api_secret = None
        mock_get_settings.return_value = mock_settings

        credentials = _get_exchange_credentials("okx")

        assert credentials is None

    @patch("squant.api.deps.get_settings")
    def test_binance_partial_credentials_secret_only(self, mock_get_settings):
        """Test returns None when only API secret is configured (no key)."""
        mock_settings = MagicMock()
        mock_settings.binance_api_key = None
        mock_settings.binance_api_secret = MagicMock()
        mock_get_settings.return_value = mock_settings

        credentials = _get_exchange_credentials("binance")

        assert credentials is None


class TestClearExchangeCacheErrorHandling:
    """Tests for error handling in clear_exchange_cache."""

    @pytest.fixture(autouse=True)
    def clear_cache(self):
        """Clear exchange cache before and after each test."""
        _exchange_cache.clear()
        yield
        _exchange_cache.clear()

    @pytest.mark.asyncio
    async def test_close_failure_continues_cleanup(self):
        """Test that one adapter.close() failure doesn't prevent clearing others."""
        adapter1 = MagicMock()
        adapter1.close = AsyncMock(side_effect=Exception("Close failed"))
        adapter2 = MagicMock()
        adapter2.close = AsyncMock()

        _exchange_cache["okx"] = adapter1
        _exchange_cache["binance"] = adapter2

        await clear_exchange_cache()

        # Both should have been attempted
        adapter1.close.assert_called_once()
        adapter2.close.assert_called_once()
        # Cache should still be cleared
        assert len(_exchange_cache) == 0


class TestGetExchange:
    """Tests for get_exchange generator function."""

    @pytest.fixture(autouse=True)
    def clear_cache(self):
        """Clear exchange cache before and after each test."""
        _exchange_cache.clear()
        yield
        _exchange_cache.clear()

    @pytest.mark.asyncio
    @patch("squant.api.deps._get_current_exchange_id")
    @patch("squant.api.deps._get_or_create_exchange_adapter")
    async def test_yields_adapter(self, mock_get_adapter, mock_get_exchange_id):
        """Test get_exchange yields the adapter."""
        mock_get_exchange_id.return_value = "okx"
        mock_adapter = MagicMock()
        mock_get_adapter.return_value = mock_adapter

        async for adapter in get_exchange():
            assert adapter == mock_adapter

        mock_get_exchange_id.assert_called_once()
        mock_get_adapter.assert_called_once_with("okx")

    @pytest.mark.asyncio
    @patch("squant.api.deps._get_current_exchange_id")
    @patch("squant.api.deps._get_or_create_exchange_adapter")
    async def test_uses_current_exchange(self, mock_get_adapter, mock_get_exchange_id):
        """Test uses the current configured exchange."""
        mock_get_exchange_id.return_value = "binance"
        mock_adapter = MagicMock()
        mock_get_adapter.return_value = mock_adapter

        async for _ in get_exchange():
            pass

        mock_get_adapter.assert_called_once_with("binance")
