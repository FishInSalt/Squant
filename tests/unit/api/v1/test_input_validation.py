"""Unit tests for API-level input validation.

Tests that Pydantic schema validation at the API boundary correctly rejects
invalid inputs with 422 status codes. These tests exercise real FastAPI
validation through the app, not schema-level unit tests.

Endpoints covered:
- POST /api/v1/backtest (RunBacktestRequest)
- POST /api/v1/paper (StartPaperTradingRequest)
- POST /api/v1/orders (CreateOrderRequest)
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from squant.api.deps import get_okx_exchange
from squant.infra.database import get_session
from squant.infra.redis import get_redis
from squant.main import app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Create async test client with dependency overrides.

    Overrides database session, Redis, and OKX exchange dependencies so that
    requests reach the Pydantic validation layer without requiring real
    infrastructure. Since we only test 422 responses, the mocked dependencies
    are never actually invoked by any endpoint handler.
    """
    mock_session = MagicMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()
    mock_session.add = MagicMock()

    # The orders endpoint also needs an exchange account lookup to succeed
    # before reaching the handler body. Configure a mock account so the
    # OrderService dependency does not raise first.
    mock_account = MagicMock()
    mock_account.id = uuid4()
    mock_account.exchange = "okx"
    mock_account.is_active = True
    mock_account.nonce = b"valid_nonce_12"

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_account
    mock_session.execute = AsyncMock(return_value=mock_result)

    async def override_get_session():
        yield mock_session

    async def override_get_redis():
        yield MagicMock()

    async def override_get_okx_exchange():
        yield MagicMock()

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_redis] = override_get_redis
    app.dependency_overrides[get_okx_exchange] = override_get_okx_exchange

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_redis, None)
    app.dependency_overrides.pop(get_okx_exchange, None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_backtest_payload() -> dict:
    """Return a minimal valid backtest request payload."""
    return {
        "strategy_id": str(uuid4()),
        "symbol": "BTC/USDT",
        "exchange": "okx",
        "timeframe": "1h",
        "start_date": "2024-01-01T00:00:00Z",
        "end_date": "2024-06-01T00:00:00Z",
        "initial_capital": 10000,
    }


def _valid_paper_payload() -> dict:
    """Return a minimal valid paper trading request payload."""
    return {
        "strategy_id": str(uuid4()),
        "symbol": "BTC/USDT",
        "exchange": "okx",
        "timeframe": "1m",
        "initial_capital": 10000,
    }


def _valid_order_payload() -> dict:
    """Return a minimal valid order request payload."""
    return {
        "symbol": "BTC/USDT",
        "side": "buy",
        "type": "market",
        "amount": 0.1,
    }


# ===========================================================================
# POST /api/v1/backtest — RunBacktestRequest validation
# ===========================================================================


class TestBacktestValidation:
    """Input validation tests for the backtest endpoint."""

    URL = "/api/v1/backtest"

    async def test_empty_body_returns_422(self, client: AsyncClient):
        response = await client.post(self.URL, json={})
        assert response.status_code == 422

    async def test_missing_strategy_id(self, client: AsyncClient):
        payload = _valid_backtest_payload()
        del payload["strategy_id"]
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_missing_symbol(self, client: AsyncClient):
        payload = _valid_backtest_payload()
        del payload["symbol"]
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_missing_exchange(self, client: AsyncClient):
        payload = _valid_backtest_payload()
        del payload["exchange"]
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_missing_timeframe(self, client: AsyncClient):
        payload = _valid_backtest_payload()
        del payload["timeframe"]
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_missing_start_date(self, client: AsyncClient):
        payload = _valid_backtest_payload()
        del payload["start_date"]
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_missing_end_date(self, client: AsyncClient):
        payload = _valid_backtest_payload()
        del payload["end_date"]
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_missing_initial_capital(self, client: AsyncClient):
        payload = _valid_backtest_payload()
        del payload["initial_capital"]
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_invalid_uuid_format(self, client: AsyncClient):
        payload = _valid_backtest_payload()
        payload["strategy_id"] = "not-a-uuid"
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_start_date_equals_end_date(self, client: AsyncClient):
        """model_validator rejects start_date == end_date."""
        payload = _valid_backtest_payload()
        same_date = "2024-03-15T00:00:00Z"
        payload["start_date"] = same_date
        payload["end_date"] = same_date
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_start_date_after_end_date(self, client: AsyncClient):
        """model_validator rejects start_date > end_date."""
        payload = _valid_backtest_payload()
        payload["start_date"] = "2024-06-01T00:00:00Z"
        payload["end_date"] = "2024-01-01T00:00:00Z"
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_zero_initial_capital(self, client: AsyncClient):
        """Field(gt=0) rejects zero."""
        payload = _valid_backtest_payload()
        payload["initial_capital"] = 0
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_negative_initial_capital(self, client: AsyncClient):
        """Field(gt=0) rejects negative values."""
        payload = _valid_backtest_payload()
        payload["initial_capital"] = -1000
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_commission_rate_negative(self, client: AsyncClient):
        """Field(ge=0) rejects negative commission_rate."""
        payload = _valid_backtest_payload()
        payload["commission_rate"] = -0.01
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_commission_rate_above_one(self, client: AsyncClient):
        """Field(le=1) rejects commission_rate > 1."""
        payload = _valid_backtest_payload()
        payload["commission_rate"] = 1.5
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_slippage_negative(self, client: AsyncClient):
        """Field(ge=0) rejects negative slippage."""
        payload = _valid_backtest_payload()
        payload["slippage"] = -0.001
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_slippage_above_one(self, client: AsyncClient):
        """Field(le=1) rejects slippage > 1."""
        payload = _valid_backtest_payload()
        payload["slippage"] = 2.0
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_empty_symbol_string(self, client: AsyncClient):
        """Field(min_length=1) rejects empty symbol."""
        payload = _valid_backtest_payload()
        payload["symbol"] = ""
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_symbol_too_long(self, client: AsyncClient):
        """Field(max_length=32) rejects overly long symbol."""
        payload = _valid_backtest_payload()
        payload["symbol"] = "A" * 33
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_exchange_too_long(self, client: AsyncClient):
        """Field(max_length=32) rejects overly long exchange."""
        payload = _valid_backtest_payload()
        payload["exchange"] = "x" * 33
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_timeframe_too_long(self, client: AsyncClient):
        """Field(max_length=8) rejects overly long timeframe."""
        payload = _valid_backtest_payload()
        payload["timeframe"] = "123456789"  # 9 chars > 8
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_invalid_date_format(self, client: AsyncClient):
        """Non-datetime strings are rejected."""
        payload = _valid_backtest_payload()
        payload["start_date"] = "not-a-date"
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_extra_fields_accepted(self, client: AsyncClient):
        """Pydantic default 'ignore' allows extra fields without error.

        We patch the service layer so the request passes validation and
        reaches the handler. A StrategyNotFoundError (404) confirms the
        extra field did not trigger a 422 validation error.
        """
        from squant.services.strategy import StrategyNotFoundError

        payload = _valid_backtest_payload()
        payload["unknown_field"] = "should be ignored"
        with patch("squant.api.v1.backtest.BacktestService") as mock_cls:
            mock_service = mock_cls.return_value
            mock_service.create = AsyncMock(side_effect=StrategyNotFoundError("not found"))
            response = await client.post(self.URL, json=payload)
        assert response.status_code == 404

    async def test_non_json_content_type(self, client: AsyncClient):
        """Sending non-JSON content returns 422."""
        response = await client.post(
            self.URL,
            content="this is not json",
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 422


# ===========================================================================
# POST /api/v1/paper — StartPaperTradingRequest validation
# ===========================================================================


class TestPaperTradingValidation:
    """Input validation tests for the paper trading endpoint."""

    URL = "/api/v1/paper"

    async def test_empty_body_returns_422(self, client: AsyncClient):
        response = await client.post(self.URL, json={})
        assert response.status_code == 422

    async def test_missing_strategy_id(self, client: AsyncClient):
        payload = _valid_paper_payload()
        del payload["strategy_id"]
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_missing_symbol(self, client: AsyncClient):
        payload = _valid_paper_payload()
        del payload["symbol"]
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_missing_exchange(self, client: AsyncClient):
        payload = _valid_paper_payload()
        del payload["exchange"]
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_missing_timeframe(self, client: AsyncClient):
        payload = _valid_paper_payload()
        del payload["timeframe"]
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_invalid_uuid_format(self, client: AsyncClient):
        payload = _valid_paper_payload()
        payload["strategy_id"] = "bad-uuid"
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_zero_initial_capital(self, client: AsyncClient):
        """Field(gt=0) rejects zero."""
        payload = _valid_paper_payload()
        payload["initial_capital"] = 0
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_negative_initial_capital(self, client: AsyncClient):
        payload = _valid_paper_payload()
        payload["initial_capital"] = -5000
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_commission_rate_negative(self, client: AsyncClient):
        payload = _valid_paper_payload()
        payload["commission_rate"] = -0.01
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_commission_rate_above_one(self, client: AsyncClient):
        payload = _valid_paper_payload()
        payload["commission_rate"] = 1.1
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_slippage_negative(self, client: AsyncClient):
        payload = _valid_paper_payload()
        payload["slippage"] = -0.5
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_slippage_above_one(self, client: AsyncClient):
        payload = _valid_paper_payload()
        payload["slippage"] = 1.5
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_empty_symbol_string(self, client: AsyncClient):
        payload = _valid_paper_payload()
        payload["symbol"] = ""
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_symbol_too_long(self, client: AsyncClient):
        payload = _valid_paper_payload()
        payload["symbol"] = "X" * 33
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_exchange_too_long(self, client: AsyncClient):
        payload = _valid_paper_payload()
        payload["exchange"] = "e" * 33
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_timeframe_too_long(self, client: AsyncClient):
        payload = _valid_paper_payload()
        payload["timeframe"] = "t" * 9
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_extra_fields_accepted(self, client: AsyncClient):
        """Extra fields should not cause a 422."""
        from squant.services.strategy import StrategyNotFoundError

        payload = _valid_paper_payload()
        payload["extra"] = True
        with patch("squant.api.v1.paper_trading.PaperTradingService") as mock_cls:
            mock_service = mock_cls.return_value
            mock_service.start = AsyncMock(side_effect=StrategyNotFoundError("not found"))
            response = await client.post(self.URL, json=payload)
        assert response.status_code == 404


# ===========================================================================
# POST /api/v1/orders — CreateOrderRequest validation
# ===========================================================================


class TestOrderValidation:
    """Input validation tests for the orders endpoint."""

    URL = "/api/v1/orders"

    async def test_empty_body_returns_422(self, client: AsyncClient):
        response = await client.post(self.URL, json={})
        assert response.status_code == 422

    async def test_missing_symbol(self, client: AsyncClient):
        payload = _valid_order_payload()
        del payload["symbol"]
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_missing_side(self, client: AsyncClient):
        payload = _valid_order_payload()
        del payload["side"]
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_missing_type(self, client: AsyncClient):
        payload = _valid_order_payload()
        del payload["type"]
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_missing_amount(self, client: AsyncClient):
        payload = _valid_order_payload()
        del payload["amount"]
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_invalid_side_value(self, client: AsyncClient):
        """OrderSide enum only allows 'buy' or 'sell'."""
        payload = _valid_order_payload()
        payload["side"] = "hold"
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_invalid_order_type_value(self, client: AsyncClient):
        """OrderType enum only allows 'market' or 'limit'."""
        payload = _valid_order_payload()
        payload["type"] = "stop_loss"
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_zero_amount(self, client: AsyncClient):
        """Field(gt=0) rejects zero amount."""
        payload = _valid_order_payload()
        payload["amount"] = 0
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_negative_amount(self, client: AsyncClient):
        """Field(gt=0) rejects negative amount."""
        payload = _valid_order_payload()
        payload["amount"] = -1.5
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_invalid_client_order_id_too_long(self, client: AsyncClient):
        """Field(max_length=32) rejects overly long client_order_id."""
        payload = _valid_order_payload()
        payload["client_order_id"] = "x" * 33
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_invalid_run_id_format(self, client: AsyncClient):
        """run_id must be a valid UUID if provided."""
        payload = _valid_order_payload()
        payload["run_id"] = "not-a-uuid"
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422

    async def test_extra_fields_accepted(self, client: AsyncClient):
        """Extra fields should not cause a 422."""
        from squant.api.v1.orders import get_order_service
        from squant.services.order import OrderValidationError

        mock_service = AsyncMock()
        mock_service.create_order = AsyncMock(side_effect=OrderValidationError("patched"))

        async def override_get_order_service():
            return mock_service

        app.dependency_overrides[get_order_service] = override_get_order_service
        try:
            payload = _valid_order_payload()
            payload["unknown"] = "data"
            response = await client.post(self.URL, json=payload)
            assert response.status_code == 400
        finally:
            app.dependency_overrides.pop(get_order_service, None)

    async def test_amount_non_numeric(self, client: AsyncClient):
        """Non-numeric amount is rejected."""
        payload = _valid_order_payload()
        payload["amount"] = "abc"
        response = await client.post(self.URL, json=payload)
        assert response.status_code == 422


# ===========================================================================
# Cross-cutting validation concerns
# ===========================================================================


class TestCrossCuttingValidation:
    """Tests for validation behavior shared across endpoints."""

    @pytest.mark.parametrize(
        "url",
        [
            "/api/v1/backtest",
            "/api/v1/paper",
            "/api/v1/orders",
        ],
    )
    async def test_null_body_returns_422(self, client: AsyncClient, url: str):
        """Sending null as the request body returns 422."""
        response = await client.post(
            url,
            content="null",
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 422

    @pytest.mark.parametrize(
        "url",
        [
            "/api/v1/backtest",
            "/api/v1/paper",
            "/api/v1/orders",
        ],
    )
    async def test_array_body_returns_422(self, client: AsyncClient, url: str):
        """Sending a JSON array instead of an object returns 422."""
        response = await client.post(url, json=[])
        assert response.status_code == 422

    @pytest.mark.parametrize(
        "url",
        [
            "/api/v1/backtest",
            "/api/v1/paper",
            "/api/v1/orders",
        ],
    )
    async def test_422_response_has_detail(self, client: AsyncClient, url: str):
        """FastAPI's default validation error response includes a 'detail' key."""
        response = await client.post(url, json={})
        assert response.status_code == 422
        body = response.json()
        assert "detail" in body

    @pytest.mark.parametrize(
        "url,payload_fn",
        [
            ("/api/v1/backtest", _valid_backtest_payload),
            ("/api/v1/paper", _valid_paper_payload),
            ("/api/v1/orders", _valid_order_payload),
        ],
    )
    async def test_string_value_for_numeric_field(self, client: AsyncClient, url: str, payload_fn):
        """Non-numeric string for a numeric field is rejected.

        Pydantic will attempt coercion for some types (like Decimal from a
        numeric string), but a clearly non-numeric string should fail.
        """
        payload = payload_fn()
        # Pick the first numeric field available
        if "initial_capital" in payload:
            payload["initial_capital"] = "not-a-number"
        else:
            payload["amount"] = "not-a-number"
        response = await client.post(url, json=payload)
        assert response.status_code == 422
