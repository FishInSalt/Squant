"""Unit tests for live trading schema symbol/timeframe validation (bug m-1)."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from squant.schemas.live_trading import RiskConfigRequest, StartLiveTradingRequest


def _make_risk_config() -> RiskConfigRequest:
    """Helper to create a valid risk config for request tests."""
    return RiskConfigRequest(
        max_position_size=Decimal("0.5"),
        max_order_size=Decimal("0.1"),
        daily_trade_limit=100,
        daily_loss_limit=Decimal("0.05"),
    )


class TestSymbolFormatValidation:
    """Test symbol field requires BASE/QUOTE format (e.g., BTC/USDT).

    Bug m-1: symbol only had min_length/max_length but no format check.
    Service layer calls symbol.split("/")[1] which raises IndexError
    if no "/" is present.
    """

    @pytest.mark.parametrize(
        "symbol",
        [
            "BTC/USDT",
            "ETH/USDT",
            "SOL/BTC",
            "DOGE/USDT",
            "BNB/ETH",
            "XRP/USDT",
            "AVAX/USDT",
            "SHIB/USDT",
            "1INCH/USDT",
            "100X/BTC",
        ],
    )
    def test_valid_symbol_accepted(self, symbol: str):
        """Valid BASE/QUOTE symbols should be accepted."""
        request = StartLiveTradingRequest(
            strategy_id=uuid4(),
            symbol=symbol,
            exchange_account_id=uuid4(),
            timeframe="1m",
            risk_config=_make_risk_config(),
        )
        assert request.symbol == symbol

    @pytest.mark.parametrize(
        "symbol",
        [
            "BTCUSDT",  # missing slash
            "BTC-USDT",  # dash instead of slash
            "BTC_USDT",  # underscore instead of slash
            "btc/usdt",  # lowercase
            "BTC/",  # trailing slash, no quote
            "/USDT",  # leading slash, no base
            "BTC",  # single token
            "BTC/USDT/EXTRA",  # too many parts
            "BTC / USDT",  # spaces
            "btc/USDT",  # mixed case
            "BTC/usdt",  # mixed case
        ],
    )
    def test_invalid_symbol_rejected(self, symbol: str):
        """Symbols without proper BASE/QUOTE format should be rejected."""
        with pytest.raises(ValidationError):
            StartLiveTradingRequest(
                strategy_id=uuid4(),
                symbol=symbol,
                exchange_account_id=uuid4(),
                timeframe="1m",
                risk_config=_make_risk_config(),
            )


class TestTimeframeValidation:
    """Test timeframe field only accepts valid values.

    Bug m-1: timeframe only had min_length/max_length but no value validation.
    Valid timeframes: 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d, 1w, 1M.
    """

    @pytest.mark.parametrize(
        "timeframe",
        ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w", "1M"],
    )
    def test_valid_timeframe_accepted(self, timeframe: str):
        """All standard timeframes should be accepted."""
        request = StartLiveTradingRequest(
            strategy_id=uuid4(),
            symbol="BTC/USDT",
            exchange_account_id=uuid4(),
            timeframe=timeframe,
            risk_config=_make_risk_config(),
        )
        assert request.timeframe == timeframe

    @pytest.mark.parametrize(
        "timeframe",
        [
            "invalid",
            "2m",  # not a standard timeframe
            "10m",
            "1s",  # seconds not supported
            "1y",  # years not supported
            "60m",
            "1H",  # uppercase H (use 1h)
            "1D",  # uppercase D (use 1d)
            "1W",  # uppercase W (use 1w)
        ],
    )
    def test_invalid_timeframe_rejected(self, timeframe: str):
        """Invalid timeframes should be rejected."""
        with pytest.raises(ValidationError):
            StartLiveTradingRequest(
                strategy_id=uuid4(),
                symbol="BTC/USDT",
                exchange_account_id=uuid4(),
                timeframe=timeframe,
                risk_config=_make_risk_config(),
            )
