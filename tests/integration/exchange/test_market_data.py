"""Layer 2 market data flow integration tests.

These tests verify that CCXTStreamProvider can connect to a live exchange
WebSocket, receive real-time OHLCV candle data, and correctly detect candle
close events.

Requirements:
    - Network access to OKX public WebSocket API (no credentials needed)

Run:
    uv run pytest tests/integration/exchange/test_market_data.py -v

NOTE: test_candle_reception_and_close_detection waits ~130 seconds to
observe at least one 1m candle close.  Total module runtime is ~2.5 minutes.

All tests are automatically marked ``@pytest.mark.integration`` by the
integration conftest.  They do NOT require exchange credentials — public
market data is used.
"""

import asyncio
from decimal import Decimal

import pytest

from squant.infra.exchange.ccxt.provider import CCXTStreamProvider
from squant.infra.exchange.ws_types import WSCandle

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXCHANGE_ID = "okx"
TEST_SYMBOL = "BTC/USDT"
TIMEFRAME = "1m"

# All tests in this module are integration tests (no credentials needed)
pytestmark = [pytest.mark.integration]


# ===========================================================================
# Connection health
# ===========================================================================


class TestWebSocketConnection:
    """Verify that CCXTStreamProvider can connect and report healthy status."""

    async def test_websocket_connection(self) -> None:
        """Provider can connect to OKX, load markets, and report healthy."""
        provider = CCXTStreamProvider(EXCHANGE_ID)

        try:
            await provider.connect()

            # Basic connection assertions
            assert provider.is_connected, "Provider should be connected after connect()"
            assert provider.is_healthy(), "Provider should be healthy right after connect()"
            assert provider.exchange_id == EXCHANGE_ID
        finally:
            await provider.close()

        # After close, connection state should be cleared
        assert not provider.is_connected, "Provider should not be connected after close()"


# ===========================================================================
# Candle reception and close detection
# ===========================================================================


class TestCandleReceptionAndCloseDetection:
    """Verify real-time candle data arrives and close detection works.

    NOTE: This test subscribes to BTC/USDT 1m candles and waits up to
    ~130 seconds to observe at least one closed candle.  A 1m candle
    closes every minute on the minute boundary, so 130s guarantees we
    cross at least one boundary.
    """

    async def test_candle_reception_and_close_detection(self) -> None:
        """Subscribe to 1m OHLCV, receive candle updates, detect at least 1 close.

        Expected duration: ~130 seconds (waiting for a 1m candle boundary).
        """
        received_candles: list[WSCandle] = []
        closed_candles: list[WSCandle] = []
        close_event = asyncio.Event()

        async def handler(message: dict) -> None:
            """Collect candle messages dispatched by the provider."""
            if message.get("type") != "candle":
                return

            candle = message["data"]
            assert isinstance(candle, WSCandle), f"Expected WSCandle, got {type(candle)}"

            received_candles.append(candle)

            if candle.is_closed:
                closed_candles.append(candle)
                close_event.set()

        provider = CCXTStreamProvider(EXCHANGE_ID)

        try:
            await provider.connect()

            # Register handler *before* subscribing
            provider.add_handler(handler)

            # Subscribe to 1m OHLCV — this starts a background _ohlcv_loop task
            await provider.watch_ohlcv(TEST_SYMBOL, TIMEFRAME)

            # Wait for at least one closed candle.
            # 1m candles close on the minute boundary; 130s guarantees we
            # cross at least one boundary regardless of when we start.
            try:
                await asyncio.wait_for(close_event.wait(), timeout=150.0)
            except TimeoutError:
                # Provide diagnostics if we timed out
                pytest.fail(
                    f"Timed out after 150s waiting for a closed candle. "
                    f"Received {len(received_candles)} open candles, "
                    f"{len(closed_candles)} closed candles."
                )

            # ----- Validate received open (in-progress) candles -----
            assert len(received_candles) > 0, "Should have received at least one candle update"

            sample = received_candles[0]
            assert sample.symbol == TEST_SYMBOL
            assert sample.timeframe == TIMEFRAME
            assert sample.timestamp is not None

            # OHLCV fields should be positive for BTC/USDT
            assert sample.open > Decimal("0"), f"open should be > 0, got {sample.open}"
            assert sample.high > Decimal("0"), f"high should be > 0, got {sample.high}"
            assert sample.low > Decimal("0"), f"low should be > 0, got {sample.low}"
            assert sample.close > Decimal("0"), f"close should be > 0, got {sample.close}"
            assert sample.volume >= Decimal("0"), f"volume should be >= 0, got {sample.volume}"

            # Sanity: high >= low
            assert sample.high >= sample.low, "high must be >= low"

            # ----- Validate closed candle -----
            assert len(closed_candles) >= 1, "Should have at least one closed candle"

            closed = closed_candles[0]
            assert closed.is_closed is True
            assert closed.symbol == TEST_SYMBOL
            assert closed.timeframe == TIMEFRAME
            assert closed.open > Decimal("0")
            assert closed.high > Decimal("0")
            assert closed.low > Decimal("0")
            assert closed.close > Decimal("0")
            assert closed.high >= closed.low

        finally:
            await provider.close()
