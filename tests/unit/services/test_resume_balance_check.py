"""Tests for _check_resume_balance in LiveTradingService (B1+).

Validates that resume checks account balance sufficiency before
proceeding, raises ValueError when insufficient, and logs warnings
(but does not raise) when the balance check itself fails.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from squant.schemas.live_trading import AccountBalanceResponse
from squant.services.live_trading import LiveTradingService


@pytest.fixture
def mock_session():
    """Create a mock DB session."""
    return AsyncMock()


@pytest.fixture
def service(mock_session):
    """Create a LiveTradingService with mock session."""
    return LiveTradingService(mock_session)


class TestCheckResumeBalance:
    """Tests for _check_resume_balance method."""

    async def test_sufficient_balance_passes(self, service):
        """When available balance >= session equity, no exception is raised."""
        service.get_account_available_balance = AsyncMock(
            return_value=AccountBalanceResponse(
                account_total_value=Decimal("15000"),
                quote_currency="USDT",
                available=Decimal("12000"),
            )
        )

        # Should not raise
        await service._check_resume_balance(
            account_id="acc-123",
            session_equity=Decimal("10000"),
            quote_currency="USDT",
        )

        service.get_account_available_balance.assert_awaited_once_with("acc-123", "USDT")

    async def test_equal_balance_passes(self, service):
        """When available balance == session equity, no exception is raised."""
        service.get_account_available_balance = AsyncMock(
            return_value=AccountBalanceResponse(
                account_total_value=Decimal("10000"),
                quote_currency="USDT",
                available=Decimal("10000"),
            )
        )

        # Should not raise — exact match is OK
        await service._check_resume_balance(
            account_id="acc-123",
            session_equity=Decimal("10000"),
            quote_currency="USDT",
        )

    async def test_insufficient_balance_raises(self, service):
        """When session equity > available balance, ValueError is raised."""
        service.get_account_available_balance = AsyncMock(
            return_value=AccountBalanceResponse(
                account_total_value=Decimal("8000"),
                quote_currency="USDT",
                available=Decimal("5000"),
            )
        )

        with pytest.raises(ValueError, match="Insufficient balance to resume session"):
            await service._check_resume_balance(
                account_id="acc-123",
                session_equity=Decimal("10000"),
                quote_currency="USDT",
            )

    async def test_insufficient_balance_message_includes_amounts(self, service):
        """ValueError message should include both session equity and available balance."""
        service.get_account_available_balance = AsyncMock(
            return_value=AccountBalanceResponse(
                account_total_value=Decimal("8000"),
                quote_currency="USDT",
                available=Decimal("5000"),
            )
        )

        with pytest.raises(ValueError) as exc_info:
            await service._check_resume_balance(
                account_id="acc-123",
                session_equity=Decimal("10000"),
                quote_currency="USDT",
            )

        msg = str(exc_info.value)
        assert "10000" in msg
        assert "5000" in msg
        assert "USDT" in msg

    async def test_balance_check_failure_logs_warning(self, service, caplog):
        """When get_account_available_balance raises a non-ValueError exception,
        log a warning and do not raise."""
        service.get_account_available_balance = AsyncMock(
            side_effect=RuntimeError("Exchange connection failed")
        )

        with caplog.at_level(logging.WARNING, logger="squant.services.live_trading"):
            # Should NOT raise
            await service._check_resume_balance(
                account_id="acc-123",
                session_equity=Decimal("10000"),
                quote_currency="USDT",
            )

        assert "Balance check failed" in caplog.text
        assert "acc-123" in caplog.text
        assert "proceeding with resume" in caplog.text
