"""Unit tests for OKX WebSocket client."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from squant.infra.exchange.exceptions import (
    ExchangeAuthenticationError,
    ExchangeConnectionError,
)
from squant.infra.exchange.okx.ws_client import OKXWebSocketClient
from squant.infra.exchange.okx.ws_types import (
    CANDLE_CHANNELS,
    OKXChannel,
    WSAccountUpdate,
    WSCandle,
    WSMessage,
    WSMessageType,
    WSOrderBook,
    WSOrderBookLevel,
    WSOrderUpdate,
    WSTicker,
    WSTrade,
)


class TestOKXWebSocketClientInit:
    """Tests for OKX WebSocket client initialization."""

    def test_public_client_urls(self) -> None:
        """Test public client WebSocket URLs."""
        client = OKXWebSocketClient(testnet=False, private=False)
        assert client.ws_url == OKXWebSocketClient.PUBLIC_WS_URL

        client_testnet = OKXWebSocketClient(testnet=True, private=False)
        assert client_testnet.ws_url == OKXWebSocketClient.DEMO_PUBLIC_WS_URL

    def test_private_client_urls(self) -> None:
        """Test private client WebSocket URLs."""
        client = OKXWebSocketClient(
            api_key="key",
            api_secret="secret",
            passphrase="pass",
            testnet=False,
            private=True,
        )
        assert client.ws_url == OKXWebSocketClient.PRIVATE_WS_URL

        client_testnet = OKXWebSocketClient(
            api_key="key",
            api_secret="secret",
            passphrase="pass",
            testnet=True,
            private=True,
        )
        assert client_testnet.ws_url == OKXWebSocketClient.DEMO_PRIVATE_WS_URL

    def test_initial_state(self) -> None:
        """Test initial client state."""
        client = OKXWebSocketClient()
        assert client.is_connected is False
        assert client.is_authenticated is False
        assert client._running is False
        assert client._subscriptions == []


class TestOKXWebSocketClientSignature:
    """Tests for WebSocket authentication signature generation."""

    def test_signature_generation(self) -> None:
        """Test HMAC-SHA256 signature generation for WebSocket auth."""
        client = OKXWebSocketClient(
            api_key="test-key",
            api_secret="test-secret",
            passphrase="test-passphrase",
            private=True,
        )

        timestamp = "1705315800"
        signature = client._generate_signature(timestamp)

        # Signature should be base64 encoded string
        assert isinstance(signature, str)
        assert len(signature) > 0

    def test_signature_requires_secret(self) -> None:
        """Test that signature generation requires API secret."""
        client = OKXWebSocketClient(private=True)

        with pytest.raises(ExchangeAuthenticationError) as exc_info:
            client._generate_signature("1705315800")

        assert "API secret required" in str(exc_info.value)

    def test_signature_consistency(self) -> None:
        """Test that same inputs produce same signature."""
        client = OKXWebSocketClient(
            api_key="key",
            api_secret="secret",
            passphrase="pass",
            private=True,
        )

        timestamp = "1705315800"
        sig1 = client._generate_signature(timestamp)
        sig2 = client._generate_signature(timestamp)

        assert sig1 == sig2


class TestOKXWebSocketClientSubscriptions:
    """Tests for WebSocket subscription management."""

    @pytest.mark.asyncio
    async def test_subscribe_adds_to_list(self) -> None:
        """Test that subscribe adds channels to subscription list."""
        client = OKXWebSocketClient()
        client._connected = True
        client._ws = AsyncMock()

        channels = [{"channel": "tickers", "instId": "BTC-USDT"}]
        await client.subscribe(channels)

        assert channels[0] in client._subscriptions

    @pytest.mark.asyncio
    async def test_subscribe_avoids_duplicates(self) -> None:
        """Test that duplicate subscriptions are not added."""
        client = OKXWebSocketClient()
        client._connected = True
        client._ws = AsyncMock()

        channel = {"channel": "tickers", "instId": "BTC-USDT"}
        await client.subscribe([channel])
        await client.subscribe([channel])

        assert client._subscriptions.count(channel) == 1

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_from_list(self) -> None:
        """Test that unsubscribe removes channels from subscription list."""
        client = OKXWebSocketClient()
        client._connected = True
        client._ws = AsyncMock()

        channel = {"channel": "tickers", "instId": "BTC-USDT"}
        client._subscriptions.append(channel)

        await client.unsubscribe([channel])

        assert channel not in client._subscriptions

    @pytest.mark.asyncio
    async def test_subscribe_sends_message(self) -> None:
        """Test that subscribe sends correct message format."""
        client = OKXWebSocketClient()
        client._connected = True
        mock_ws = AsyncMock()
        client._ws = mock_ws

        channels = [{"channel": "tickers", "instId": "BTC-USDT"}]
        await client.subscribe(channels)

        mock_ws.send.assert_called_once()
        sent_data = json.loads(mock_ws.send.call_args[0][0])
        assert sent_data["op"] == "subscribe"
        assert sent_data["args"] == channels


class TestOKXWebSocketClientHandlers:
    """Tests for message handler management."""

    def test_add_handler(self) -> None:
        """Test adding a message handler."""
        client = OKXWebSocketClient()

        async def handler(msg: dict) -> None:
            pass

        client.add_handler(handler)
        assert handler in client._handlers

    def test_add_handler_avoids_duplicates(self) -> None:
        """Test that duplicate handlers are not added."""
        client = OKXWebSocketClient()

        async def handler(msg: dict) -> None:
            pass

        client.add_handler(handler)
        client.add_handler(handler)

        assert client._handlers.count(handler) == 1

    def test_remove_handler(self) -> None:
        """Test removing a message handler."""
        client = OKXWebSocketClient()

        async def handler(msg: dict) -> None:
            pass

        client.add_handler(handler)
        client.remove_handler(handler)

        assert handler not in client._handlers


class TestWSMessageTypes:
    """Tests for WebSocket message types."""

    def test_ws_ticker_model(self) -> None:
        """Test WSTicker model creation and serialization."""
        ticker = WSTicker(
            symbol="BTC/USDT",
            last=Decimal("42000.50"),
            bid=Decimal("42000.00"),
            ask=Decimal("42001.00"),
            volume_24h=Decimal("1234.56"),
        )

        assert ticker.symbol == "BTC/USDT"
        assert ticker.last == Decimal("42000.50")

        # Test JSON serialization
        data = ticker.model_dump(mode="json")
        assert data["symbol"] == "BTC/USDT"
        assert data["last"] == "42000.50"

    def test_ws_candle_model(self) -> None:
        """Test WSCandle model creation."""
        candle = WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 26, 12, 0, 0, tzinfo=UTC),
            open=Decimal("42000.00"),
            high=Decimal("42100.00"),
            low=Decimal("41900.00"),
            close=Decimal("42050.00"),
            volume=Decimal("123.45"),
            is_closed=False,
        )

        assert candle.symbol == "BTC/USDT"
        assert candle.timeframe == "1m"
        assert candle.is_closed is False

    def test_ws_trade_model(self) -> None:
        """Test WSTrade model creation."""
        trade = WSTrade(
            symbol="BTC/USDT",
            trade_id="123456789",
            price=Decimal("42000.50"),
            size=Decimal("0.5"),
            side="buy",
            timestamp=datetime(2024, 1, 26, 12, 0, 0, tzinfo=UTC),
        )

        assert trade.trade_id == "123456789"
        assert trade.side == "buy"

    def test_ws_orderbook_model(self) -> None:
        """Test WSOrderBook model creation."""
        orderbook = WSOrderBook(
            symbol="BTC/USDT",
            bids=[
                WSOrderBookLevel(price=Decimal("42000.00"), size=Decimal("1.5"), num_orders=3),
                WSOrderBookLevel(price=Decimal("41999.00"), size=Decimal("2.0"), num_orders=5),
            ],
            asks=[
                WSOrderBookLevel(price=Decimal("42001.00"), size=Decimal("1.0"), num_orders=2),
            ],
        )

        assert orderbook.symbol == "BTC/USDT"
        assert len(orderbook.bids) == 2
        assert len(orderbook.asks) == 1
        assert orderbook.bids[0].price == Decimal("42000.00")

    def test_ws_order_update_model(self) -> None:
        """Test WSOrderUpdate model creation."""
        order = WSOrderUpdate(
            order_id="12345678",
            client_order_id="my-order-1",
            symbol="BTC/USDT",
            side="buy",
            order_type="limit",
            status="filled",
            price=Decimal("42000.00"),
            size=Decimal("0.5"),
            filled_size=Decimal("0.5"),
            avg_price=Decimal("42000.00"),
        )

        assert order.order_id == "12345678"
        assert order.status == "filled"
        assert order.filled_size == Decimal("0.5")

    def test_ws_account_update_model(self) -> None:
        """Test WSAccountUpdate model creation."""
        from squant.infra.exchange.okx.ws_types import WSBalanceUpdate

        account = WSAccountUpdate(
            balances=[
                WSBalanceUpdate(
                    currency="USDT", available=Decimal("10000.00"), frozen=Decimal("500.00")
                ),
                WSBalanceUpdate(currency="BTC", available=Decimal("1.5"), frozen=Decimal("0.1")),
            ],
        )

        assert len(account.balances) == 2
        assert account.balances[0].currency == "USDT"
        assert account.balances[0].available == Decimal("10000.00")

    def test_ws_message_wrapper(self) -> None:
        """Test WSMessage wrapper model."""
        message = WSMessage(
            type=WSMessageType.TICKER,
            channel="ticker:BTC/USDT",
            data={"symbol": "BTC/USDT", "last": "42000.50"},
        )

        assert message.type == WSMessageType.TICKER
        assert message.channel == "ticker:BTC/USDT"

        # Test JSON serialization
        json_str = message.model_dump_json()
        assert "ticker" in json_str
        assert "BTC/USDT" in json_str


class TestOKXChannelEnum:
    """Tests for OKX channel enumeration."""

    def test_public_channels(self) -> None:
        """Test public channel values."""
        assert OKXChannel.TICKERS.value == "tickers"
        assert OKXChannel.TRADES.value == "trades"
        assert OKXChannel.BOOKS5.value == "books5"

    def test_candle_channels(self) -> None:
        """Test candle channel values."""
        assert OKXChannel.CANDLE_1M.value == "candle1m"
        assert OKXChannel.CANDLE_1H.value == "candle1H"
        assert OKXChannel.CANDLE_1D.value == "candle1D"

    def test_private_channels(self) -> None:
        """Test private channel values."""
        assert OKXChannel.ACCOUNT.value == "account"
        assert OKXChannel.ORDERS.value == "orders"

    def test_candle_channel_mapping(self) -> None:
        """Test candle timeframe to channel mapping."""
        assert CANDLE_CHANNELS["1m"] == OKXChannel.CANDLE_1M
        assert CANDLE_CHANNELS["5m"] == OKXChannel.CANDLE_5M
        assert CANDLE_CHANNELS["1h"] == OKXChannel.CANDLE_1H
        assert CANDLE_CHANNELS["4h"] == OKXChannel.CANDLE_4H
        assert CANDLE_CHANNELS["1d"] == OKXChannel.CANDLE_1D


class TestOKXWebSocketClientConnection:
    """Tests for WebSocket connection management."""

    @pytest.mark.asyncio
    async def test_connect_not_connected(self) -> None:
        """Test connection error when not connected."""
        client = OKXWebSocketClient()

        with pytest.raises(ExchangeConnectionError) as exc_info:
            await client._send({"test": "data"})

        assert "Not connected" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_close_idempotent(self) -> None:
        """Test that close is safe to call multiple times."""
        client = OKXWebSocketClient()
        client._running = False

        # Should not raise
        await client.close()
        await client.close()

    def test_is_connected_property(self) -> None:
        """Test is_connected property."""
        client = OKXWebSocketClient()
        assert client.is_connected is False

        client._connected = True
        assert client.is_connected is False  # Still False because _ws is None

        client._ws = MagicMock()
        assert client.is_connected is True


class TestOKXWebSocketClientReconnect:
    """Tests for reconnection logic."""

    def test_reconnect_delay_calculation(self) -> None:
        """Test exponential backoff delay calculation."""
        base = OKXWebSocketClient.RECONNECT_BASE_DELAY
        max_delay = OKXWebSocketClient.RECONNECT_MAX_DELAY

        # First attempt: base * 2^0 = 1s
        delay1 = min(base * (2**0), max_delay)
        assert delay1 == 1.0

        # Second attempt: base * 2^1 = 2s
        delay2 = min(base * (2**1), max_delay)
        assert delay2 == 2.0

        # Third attempt: base * 2^2 = 4s
        delay3 = min(base * (2**2), max_delay)
        assert delay3 == 4.0

        # Should cap at max_delay
        delay_max = min(base * (2**10), max_delay)
        assert delay_max == max_delay

    def test_max_reconnect_attempts(self) -> None:
        """Test max reconnection attempts constant."""
        assert OKXWebSocketClient.RECONNECT_MAX_ATTEMPTS == 10


class TestOKXWebSocketClientEventHandling:
    """Tests for event message handling."""

    @pytest.mark.asyncio
    async def test_handle_subscribe_event(self) -> None:
        """Test handling subscribe confirmation."""
        client = OKXWebSocketClient()

        msg = {
            "event": "subscribe",
            "arg": {"channel": "tickers", "instId": "BTC-USDT"},
        }

        # Should not raise
        await client._handle_event(msg)

    @pytest.mark.asyncio
    async def test_handle_error_event(self) -> None:
        """Test handling error event."""
        client = OKXWebSocketClient()

        msg = {
            "event": "error",
            "code": "60001",
            "msg": "Invalid request",
        }

        # Should not raise (logs error)
        await client._handle_event(msg)

    @pytest.mark.asyncio
    async def test_handle_data_dispatches_to_handlers(self) -> None:
        """Test that data messages are dispatched to handlers."""
        client = OKXWebSocketClient()
        received_messages = []

        async def handler(msg: dict) -> None:
            received_messages.append(msg)

        client.add_handler(handler)

        test_msg = {
            "arg": {"channel": "tickers", "instId": "BTC-USDT"},
            "data": [{"last": "42000.50"}],
        }

        await client._handle_data(test_msg)

        assert len(received_messages) == 1
        assert received_messages[0] == test_msg


class TestOKXWebSocketClientContextManager:
    """Tests for async context manager."""

    @pytest.mark.asyncio
    async def test_context_manager_calls_close(self) -> None:
        """Test that context manager calls close on exit."""
        client = OKXWebSocketClient()

        with patch.object(client, "connect", new_callable=AsyncMock) as mock_connect:
            with patch.object(client, "close", new_callable=AsyncMock) as mock_close:
                async with client:
                    mock_connect.assert_called_once()

                mock_close.assert_called_once()
