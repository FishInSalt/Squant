# tests/unit/infra/exchange/test_account_total_value.py
"""Tests for CCXTRestAdapter.get_account_total_value()."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from squant.infra.exchange.ccxt.rest_adapter import CCXTRestAdapter
from squant.infra.exchange.exceptions import ExchangeAuthenticationError


class TestGetAccountTotalValue:
    """Tests for the get_account_total_value adapter method."""

    @pytest.fixture
    def adapter(self):
        """Create a connected adapter with mocked exchange."""
        adapter = CCXTRestAdapter.__new__(CCXTRestAdapter)
        adapter._exchange = MagicMock()
        adapter._exchange.fetch_balance = AsyncMock()
        adapter._exchange.fetch_ticker = AsyncMock()
        adapter._exchange_id = "okx"
        adapter._credentials = MagicMock()
        adapter._connected = True
        return adapter

    async def test_single_quote_currency(self, adapter):
        """Only USDT balance -- no ticker lookups needed."""
        adapter._exchange.fetch_balance.return_value = {
            "free": {"USDT": 1500.0},
            "used": {"USDT": 500.0},
            "info": {"data": [{}]},
        }

        total, balances = await adapter.get_account_total_value("USDT")

        assert total == Decimal("2000")
        assert len(balances) == 1
        assert balances[0].currency == "USDT"
        assert balances[0].available == Decimal("1500")
        assert balances[0].frozen == Decimal("500")
        # No ticker calls should have been made
        adapter._exchange.fetch_ticker.assert_not_called()

    async def test_multi_currency_with_ticker_conversion(self, adapter):
        """USDT + BTC balance -- BTC converted via ticker lookup."""
        adapter._exchange.fetch_balance.return_value = {
            "free": {"USDT": 1000.0, "BTC": 0.5},
            "used": {"USDT": 0, "BTC": 0.1},
            "info": {"data": [{}]},
        }
        adapter._exchange.fetch_ticker.return_value = {
            "last": 60000.0,
        }

        total, balances = await adapter.get_account_total_value("USDT")

        # USDT: 1000 + 0 = 1000
        # BTC: (0.5 + 0.1) * 60000 = 36000
        # Total: 37000
        assert total == Decimal("37000")
        assert len(balances) == 2
        adapter._exchange.fetch_ticker.assert_called_once_with("BTC/USDT")

    async def test_okx_total_eq_priority(self, adapter):
        """OKX returns totalEq in raw info -- use it directly instead of manual calc."""
        adapter._exchange_id = "okx"
        adapter._exchange.fetch_balance.return_value = {
            "free": {"USDT": 1000.0, "BTC": 0.5},
            "used": {"USDT": 0, "BTC": 0},
            "info": {"data": [{"totalEq": "42000.55"}]},
        }

        total, balances = await adapter.get_account_total_value("USDT")

        # Should use totalEq directly
        assert total == Decimal("42000.55")
        assert len(balances) == 2
        # Should NOT have called fetch_ticker since we used totalEq
        adapter._exchange.fetch_ticker.assert_not_called()

    async def test_ticker_failure_skips_currency(self, adapter):
        """When ticker fetch fails for a currency, skip it with warning log."""
        adapter._exchange.fetch_balance.return_value = {
            "free": {"USDT": 1000.0, "OBSCURE": 100.0},
            "used": {"USDT": 0, "OBSCURE": 0},
            "info": {"data": [{}]},
        }
        adapter._exchange.fetch_ticker.side_effect = Exception("No market for OBSCURE/USDT")

        with patch("squant.infra.exchange.ccxt.rest_adapter.logger") as mock_logger:
            total, balances = await adapter.get_account_total_value("USDT")

        # Only USDT counted; OBSCURE skipped due to ticker failure
        assert total == Decimal("1000")
        # Both balances still returned in the list
        assert len(balances) == 2
        mock_logger.warning.assert_called_once()

    async def test_zero_balances_excluded(self, adapter):
        """Zero balances should not appear in the returned balance list."""
        adapter._exchange.fetch_balance.return_value = {
            "free": {"USDT": 1000.0, "ETH": 0, "BTC": 0},
            "used": {"USDT": 0, "ETH": 0, "BTC": 0},
            "info": {"data": [{}]},
        }

        total, balances = await adapter.get_account_total_value("USDT")

        assert total == Decimal("1000")
        assert len(balances) == 1
        assert balances[0].currency == "USDT"

    async def test_no_credentials_raises(self, adapter):
        """Should raise ExchangeAuthenticationError when no credentials."""
        adapter._credentials = None

        with pytest.raises(ExchangeAuthenticationError):
            await adapter.get_account_total_value("USDT")

    async def test_no_exchange_raises(self, adapter):
        """Should raise when exchange is not connected."""
        from squant.infra.exchange.exceptions import ExchangeConnectionError

        adapter._exchange = None

        with pytest.raises(ExchangeConnectionError):
            await adapter.get_account_total_value("USDT")

    async def test_okx_total_eq_missing_falls_back_to_manual(self, adapter):
        """When OKX info is present but totalEq is missing, fall back to manual calc."""
        adapter._exchange_id = "okx"
        adapter._exchange.fetch_balance.return_value = {
            "free": {"USDT": 500.0, "ETH": 2.0},
            "used": {"USDT": 0, "ETH": 0},
            "info": {"data": [{}]},  # no totalEq key
        }
        adapter._exchange.fetch_ticker.return_value = {
            "last": 3000.0,
        }

        total, balances = await adapter.get_account_total_value("USDT")

        # USDT: 500, ETH: 2 * 3000 = 6000, total = 6500
        assert total == Decimal("6500")
        adapter._exchange.fetch_ticker.assert_called_once_with("ETH/USDT")

    async def test_multiple_non_quote_currencies(self, adapter):
        """Multiple non-quote currencies each get their own ticker lookup."""
        adapter._exchange.fetch_balance.return_value = {
            "free": {"USDT": 100.0, "BTC": 1.0, "ETH": 10.0},
            "used": {"USDT": 0, "BTC": 0, "ETH": 0},
            "info": {"data": [{}]},
        }

        async def mock_fetch_ticker(symbol):
            tickers = {
                "BTC/USDT": {"last": 50000.0},
                "ETH/USDT": {"last": 3000.0},
            }
            return tickers[symbol]

        adapter._exchange.fetch_ticker = AsyncMock(side_effect=mock_fetch_ticker)

        total, balances = await adapter.get_account_total_value("USDT")

        # USDT: 100, BTC: 1*50000 = 50000, ETH: 10*3000 = 30000 → 80100
        assert total == Decimal("80100")
        assert adapter._exchange.fetch_ticker.call_count == 2
