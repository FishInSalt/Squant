"""Tests for _check_balance_sufficiency in LiveTradingService (B1+).

Validates that resume checks account balance sufficiency before
proceeding, raises ValueError when insufficient, and logs warnings
(but does not raise) when the balance check itself fails.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from squant.services.live_trading import LiveTradingError, LiveTradingService


@pytest.fixture
def mock_session():
    """Create a mock DB session."""
    return AsyncMock()


@pytest.fixture
def service(mock_session):
    """Create a LiveTradingService with mock session."""
    svc = LiveTradingService(mock_session)
    svc.run_repo = AsyncMock()
    return svc


@pytest.fixture
def mock_adapter():
    """Create a mock adapter with get_account_total_value."""
    adapter = AsyncMock()
    return adapter


class TestCheckResumeBalance:
    """Tests for _check_balance_sufficiency method."""

    async def test_sufficient_balance_passes(self, service, mock_adapter):
        """When available balance >= session equity, no exception is raised."""
        mock_adapter.get_account_total_value.return_value = (Decimal("15000"), [])
        service.run_repo.list_running_by_account = AsyncMock(return_value=[])

        with patch("squant.services.live_trading.get_live_session_manager"):
            await service._check_balance_sufficiency(
                adapter=mock_adapter,
                account_id="acc-123",
                required_equity=Decimal("10000"),
                quote_currency="USDT",
            )

    async def test_equal_balance_passes(self, service, mock_adapter):
        """When available balance == session equity, no exception is raised."""
        mock_adapter.get_account_total_value.return_value = (Decimal("10000"), [])
        service.run_repo.list_running_by_account = AsyncMock(return_value=[])

        with patch("squant.services.live_trading.get_live_session_manager"):
            await service._check_balance_sufficiency(
                adapter=mock_adapter,
                account_id="acc-123",
                required_equity=Decimal("10000"),
                quote_currency="USDT",
            )

    async def test_insufficient_balance_raises(self, service, mock_adapter):
        """When session equity > available balance, ValueError is raised."""
        mock_adapter.get_account_total_value.return_value = (Decimal("8000"), [])
        service.run_repo.list_running_by_account = AsyncMock(return_value=[])

        with patch("squant.services.live_trading.get_live_session_manager"):
            with pytest.raises(LiveTradingError, match="账户可用余额不足"):
                await service._check_balance_sufficiency(
                    adapter=mock_adapter,
                    account_id="acc-123",
                    required_equity=Decimal("10000"),
                    quote_currency="USDT",
                )

    async def test_deducts_running_sessions_equity(self, service, mock_adapter):
        """Available balance should exclude other running sessions' equity."""
        mock_adapter.get_account_total_value.return_value = (Decimal("15000"), [])

        # Another session using 8000
        other_run = MagicMock()
        other_run.id = str(uuid4())
        other_run.result = {"equity": 8000}
        service.run_repo.list_running_by_account = AsyncMock(return_value=[other_run])

        mock_manager = MagicMock()
        mock_manager.get.return_value = None  # Not in memory, use DB snapshot

        with patch(
            "squant.services.live_trading.get_live_session_manager", return_value=mock_manager
        ):
            # available = 15000 - 8000 = 7000, session_equity = 10000 > 7000
            with pytest.raises(LiveTradingError, match="账户可用余额不足"):
                await service._check_balance_sufficiency(
                    adapter=mock_adapter,
                    account_id="acc-123",
                    required_equity=Decimal("10000"),
                    quote_currency="USDT",
                )

    async def test_balance_check_failure_logs_warning(self, service, mock_adapter, caplog):
        """When adapter raises, log a warning and do not raise."""
        mock_adapter.get_account_total_value.side_effect = RuntimeError(
            "Exchange connection failed"
        )

        with caplog.at_level(logging.WARNING, logger="squant.services.live_trading"):
            await service._check_balance_sufficiency(
                adapter=mock_adapter,
                account_id="acc-123",
                required_equity=Decimal("10000"),
                quote_currency="USDT",
            )

        assert "Balance check failed" in caplog.text
        assert "acc-123" in caplog.text
