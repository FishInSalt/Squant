"""Shared fixtures for exchange integration tests.

These tests require OKX demo trading credentials configured via environment
variables (OKX_API_KEY, OKX_API_SECRET, OKX_PASSPHRASE).  When credentials
are missing the entire module is skipped gracefully.
"""

import os

import pytest
import pytest_asyncio

from squant.infra.exchange.ccxt import CCXTRestAdapter, ExchangeCredentials

# ---------------------------------------------------------------------------
# Credential helpers
# ---------------------------------------------------------------------------


def _has_okx_credentials() -> bool:
    """Return True when all required OKX demo credentials are set."""
    return bool(os.getenv("OKX_API_KEY"))


requires_okx_credentials = pytest.mark.skipif(
    not _has_okx_credentials(),
    reason="OKX demo credentials not configured (OKX_API_KEY missing)",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def okx_credentials() -> ExchangeCredentials:
    """Load OKX demo-trading credentials from environment variables."""
    return ExchangeCredentials(
        api_key=os.environ["OKX_API_KEY"],
        api_secret=os.environ["OKX_API_SECRET"],
        passphrase=os.environ.get("OKX_PASSPHRASE"),
        sandbox=True,
    )


@pytest_asyncio.fixture
async def okx_adapter(okx_credentials: ExchangeCredentials) -> CCXTRestAdapter:
    """Create a connected CCXTRestAdapter for OKX demo trading.

    The adapter is connected before yielding and closed after the test.
    """
    adapter = CCXTRestAdapter(exchange_id="okx", credentials=okx_credentials)
    await adapter.connect()
    yield adapter  # type: ignore[misc]
    await adapter.close()
