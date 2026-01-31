"""Unit tests for WebSocket handlers."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import WebSocket, WebSocketDisconnect

from squant.websocket.handlers import WebSocketConnection, WebSocketGateway


@pytest.fixture
def mock_websocket():
    """Create mock WebSocket."""
    ws = AsyncMock(spec=WebSocket)
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.send_text = AsyncMock()
    ws.receive_text = AsyncMock()
    ws.close = AsyncMock()
    return ws


@pytest.fixture
def mock_stream_manager():
    """Create mock StreamManager."""
    manager = MagicMock()
    manager.REDIS_CHANNEL_PREFIX = "squant:ws:"
    manager.is_running = True
    manager.is_healthy = True
    manager.subscribe_ticker = AsyncMock()
    manager.subscribe_candles = AsyncMock()
    manager.subscribe_trades = AsyncMock()
    manager.subscribe_orderbook = AsyncMock()
    manager.subscribe_orders = AsyncMock()
    manager.subscribe_account = AsyncMock()
    manager.unsubscribe_ticker = AsyncMock()
    return manager


@pytest.fixture
def mock_redis():
    """Create mock Redis client."""
    redis = AsyncMock()
    pubsub = AsyncMock()
    pubsub.subscribe = AsyncMock()
    pubsub.unsubscribe = AsyncMock()
    pubsub.ping = AsyncMock()
    pubsub.get_message = AsyncMock(return_value=None)
    redis.pubsub = MagicMock(return_value=pubsub)
    return redis, pubsub


class TestWebSocketGatewayInit:
    """Test WebSocketGateway initialization."""

    def test_init(self, mock_websocket, mock_stream_manager):
        """Test gateway initialization."""
        gateway = WebSocketGateway(mock_websocket, mock_stream_manager)

        assert gateway.websocket is mock_websocket
        assert gateway.stream_manager is mock_stream_manager
        assert gateway._running is False
        assert len(gateway._subscribed_channels) == 0
        assert gateway._pubsub is None
        assert gateway._redis is None


class TestWebSocketGatewayClientMessages:
    """Test WebSocketGateway client message handling."""

    @pytest.mark.asyncio
    async def test_handle_ping_simple(self, mock_websocket, mock_stream_manager):
        """Test handling simple ping message."""
        gateway = WebSocketGateway(mock_websocket, mock_stream_manager)
        gateway._running = True

        # Simulate receiving "ping" then disconnect
        call_count = 0

        async def receive_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "ping"
            raise WebSocketDisconnect()

        mock_websocket.receive_text = AsyncMock(side_effect=receive_side_effect)

        await gateway._handle_client_messages()

        mock_websocket.send_json.assert_called_once_with({"type": "pong"})

    @pytest.mark.asyncio
    async def test_handle_ping_json(self, mock_websocket, mock_stream_manager):
        """Test handling JSON ping message."""
        gateway = WebSocketGateway(mock_websocket, mock_stream_manager)
        gateway._running = True

        call_count = 0

        async def receive_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return json.dumps({"type": "ping"})
            raise WebSocketDisconnect()

        mock_websocket.receive_text = AsyncMock(side_effect=receive_side_effect)

        await gateway._handle_client_messages()

        mock_websocket.send_json.assert_called_once_with({"type": "pong"})

    @pytest.mark.asyncio
    async def test_handle_invalid_json(self, mock_websocket, mock_stream_manager):
        """Test handling invalid JSON message."""
        gateway = WebSocketGateway(mock_websocket, mock_stream_manager)
        gateway._running = True

        call_count = 0

        async def receive_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "not valid json"
            raise WebSocketDisconnect()

        mock_websocket.receive_text = AsyncMock(side_effect=receive_side_effect)

        await gateway._handle_client_messages()

        mock_websocket.send_json.assert_called_once_with(
            {
                "type": "error",
                "message": "Invalid JSON format",
            }
        )

    @pytest.mark.asyncio
    async def test_handle_unknown_message_type(self, mock_websocket, mock_stream_manager):
        """Test handling unknown message type."""
        gateway = WebSocketGateway(mock_websocket, mock_stream_manager)
        gateway._running = True

        call_count = 0

        async def receive_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return json.dumps({"type": "unknown"})
            raise WebSocketDisconnect()

        mock_websocket.receive_text = AsyncMock(side_effect=receive_side_effect)

        await gateway._handle_client_messages()

        mock_websocket.send_json.assert_called_once_with(
            {
                "type": "error",
                "message": "Unknown message type: unknown",
            }
        )


class TestWebSocketGatewaySubscriptions:
    """Test WebSocketGateway subscription handling."""

    @pytest.mark.asyncio
    async def test_subscribe_ticker(self, mock_websocket, mock_stream_manager):
        """Test subscribing to ticker channel."""
        gateway = WebSocketGateway(mock_websocket, mock_stream_manager)
        gateway._running = True

        # Setup mock pubsub
        pubsub = AsyncMock()
        pubsub.subscribe = AsyncMock()
        gateway._pubsub = pubsub

        await gateway._subscribe("ticker:BTC/USDT")

        # Verify Redis subscription
        pubsub.subscribe.assert_called_once_with("squant:ws:ticker:BTC/USDT")

        # Verify OKX subscription
        mock_stream_manager.subscribe_ticker.assert_called_once_with("BTC/USDT")

        # Verify response sent
        mock_websocket.send_json.assert_called_once_with(
            {
                "type": "subscribed",
                "channel": "ticker:BTC/USDT",
            }
        )

        # Verify channel tracked
        assert "ticker:BTC/USDT" in gateway._subscribed_channels

    @pytest.mark.asyncio
    async def test_subscribe_already_subscribed(self, mock_websocket, mock_stream_manager):
        """Test subscribing to already subscribed channel."""
        gateway = WebSocketGateway(mock_websocket, mock_stream_manager)
        gateway._running = True
        gateway._subscribed_channels.add("ticker:BTC/USDT")

        await gateway._subscribe("ticker:BTC/USDT")

        # Verify "already subscribed" message
        mock_websocket.send_json.assert_called_once_with(
            {
                "type": "subscribed",
                "channel": "ticker:BTC/USDT",
                "message": "Already subscribed",
            }
        )

    @pytest.mark.asyncio
    async def test_subscribe_candles(self, mock_websocket, mock_stream_manager):
        """Test subscribing to candle channel."""
        gateway = WebSocketGateway(mock_websocket, mock_stream_manager)
        gateway._running = True

        pubsub = AsyncMock()
        pubsub.subscribe = AsyncMock()
        gateway._pubsub = pubsub

        await gateway._subscribe("candle:BTC/USDT:1h")

        mock_stream_manager.subscribe_candles.assert_called_once_with("BTC/USDT", "1h")

    @pytest.mark.asyncio
    async def test_subscribe_trades(self, mock_websocket, mock_stream_manager):
        """Test subscribing to trade channel."""
        gateway = WebSocketGateway(mock_websocket, mock_stream_manager)
        gateway._running = True

        pubsub = AsyncMock()
        pubsub.subscribe = AsyncMock()
        gateway._pubsub = pubsub

        await gateway._subscribe("trade:ETH/USDT")

        mock_stream_manager.subscribe_trades.assert_called_once_with("ETH/USDT")

    @pytest.mark.asyncio
    async def test_subscribe_orderbook(self, mock_websocket, mock_stream_manager):
        """Test subscribing to orderbook channel."""
        gateway = WebSocketGateway(mock_websocket, mock_stream_manager)
        gateway._running = True

        pubsub = AsyncMock()
        pubsub.subscribe = AsyncMock()
        gateway._pubsub = pubsub

        await gateway._subscribe("orderbook:BTC/USDT")

        mock_stream_manager.subscribe_orderbook.assert_called_once_with("BTC/USDT")

    @pytest.mark.asyncio
    async def test_subscribe_orders(self, mock_websocket, mock_stream_manager):
        """Test subscribing to orders channel."""
        gateway = WebSocketGateway(mock_websocket, mock_stream_manager)
        gateway._running = True

        pubsub = AsyncMock()
        pubsub.subscribe = AsyncMock()
        gateway._pubsub = pubsub

        await gateway._subscribe("orders")

        mock_stream_manager.subscribe_orders.assert_called_once()

    @pytest.mark.asyncio
    async def test_subscribe_account(self, mock_websocket, mock_stream_manager):
        """Test subscribing to account channel."""
        gateway = WebSocketGateway(mock_websocket, mock_stream_manager)
        gateway._running = True

        pubsub = AsyncMock()
        pubsub.subscribe = AsyncMock()
        gateway._pubsub = pubsub

        await gateway._subscribe("account")

        mock_stream_manager.subscribe_account.assert_called_once()

    @pytest.mark.asyncio
    async def test_unsubscribe(self, mock_websocket, mock_stream_manager):
        """Test unsubscribing from channel."""
        gateway = WebSocketGateway(mock_websocket, mock_stream_manager)
        gateway._running = True
        gateway._subscribed_channels.add("ticker:BTC/USDT")

        pubsub = AsyncMock()
        pubsub.unsubscribe = AsyncMock()
        gateway._pubsub = pubsub

        await gateway._unsubscribe("ticker:BTC/USDT")

        # Verify unsubscribe
        pubsub.unsubscribe.assert_called_once_with("squant:ws:ticker:BTC/USDT")

        # Verify response
        mock_websocket.send_json.assert_called_once_with(
            {
                "type": "unsubscribed",
                "channel": "ticker:BTC/USDT",
            }
        )

        # Verify channel removed
        assert "ticker:BTC/USDT" not in gateway._subscribed_channels

    @pytest.mark.asyncio
    async def test_unsubscribe_not_subscribed(self, mock_websocket, mock_stream_manager):
        """Test unsubscribing from channel not subscribed to."""
        gateway = WebSocketGateway(mock_websocket, mock_stream_manager)
        gateway._running = True

        await gateway._unsubscribe("ticker:BTC/USDT")

        mock_websocket.send_json.assert_called_once_with(
            {
                "type": "unsubscribed",
                "channel": "ticker:BTC/USDT",
                "message": "Not subscribed",
            }
        )


class TestWebSocketGatewayRedisHeartbeat:
    """Test WebSocketGateway Redis heartbeat functionality."""

    @pytest.mark.asyncio
    async def test_heartbeat_success(self, mock_websocket, mock_stream_manager):
        """Test successful Redis heartbeat."""
        gateway = WebSocketGateway(mock_websocket, mock_stream_manager)
        gateway._running = True

        pubsub = AsyncMock()
        pubsub.ping = AsyncMock()
        gateway._pubsub = pubsub

        call_count = 0

        async def mock_sleep_side_effect(duration):
            nonlocal call_count
            call_count += 1
            # Stop after 2 iterations
            if call_count >= 2:
                gateway._running = False

        with patch("squant.websocket.handlers.asyncio.sleep", side_effect=mock_sleep_side_effect):
            await gateway._redis_heartbeat()

        # Should have pinged at least once
        assert pubsub.ping.call_count >= 1

    @pytest.mark.asyncio
    async def test_heartbeat_failure_recovery(self, mock_websocket, mock_stream_manager):
        """Test heartbeat handles failures gracefully."""
        gateway = WebSocketGateway(mock_websocket, mock_stream_manager)
        gateway._running = True

        pubsub = AsyncMock()
        call_count = 0

        async def ping_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Connection lost")
            # Second call succeeds

        pubsub.ping = AsyncMock(side_effect=ping_side_effect)
        gateway._pubsub = pubsub

        sleep_count = 0

        async def mock_sleep_side_effect(duration):
            nonlocal sleep_count
            sleep_count += 1
            # Stop after 3 sleep calls
            if sleep_count >= 3:
                gateway._running = False

        with patch("squant.websocket.handlers.asyncio.sleep", side_effect=mock_sleep_side_effect):
            await gateway._redis_heartbeat()

        # Should have attempted ping multiple times
        assert pubsub.ping.call_count >= 1


class TestWebSocketGatewayReceiveFromRedis:
    """Test WebSocketGateway Redis message receiving."""

    @pytest.mark.asyncio
    async def test_receive_and_forward_message(self, mock_websocket, mock_stream_manager):
        """Test receiving and forwarding Redis messages."""
        gateway = WebSocketGateway(mock_websocket, mock_stream_manager)
        gateway._running = True
        gateway._subscribed_channels.add("ticker:BTC/USDT")

        pubsub = AsyncMock()

        call_count = 0

        async def get_message_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "type": "message",
                    "data": b'{"type":"ticker","data":{"last":"42000"}}',
                }
            # Stop after first message
            gateway._running = False
            return None

        pubsub.get_message = AsyncMock(side_effect=get_message_side_effect)
        gateway._pubsub = pubsub

        await gateway._receive_from_redis()

        mock_websocket.send_text.assert_called_once_with(
            '{"type":"ticker","data":{"last":"42000"}}'
        )

    @pytest.mark.asyncio
    async def test_receive_skips_non_message_types(self, mock_websocket, mock_stream_manager):
        """Test that non-message types are skipped."""
        gateway = WebSocketGateway(mock_websocket, mock_stream_manager)
        gateway._running = True
        gateway._subscribed_channels.add("ticker:BTC/USDT")

        pubsub = AsyncMock()

        call_count = 0

        async def get_message_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Subscribe confirmation message (not a data message)
                return {"type": "subscribe", "channel": b"squant:ws:ticker:BTC/USDT"}
            gateway._running = False
            return None

        pubsub.get_message = AsyncMock(side_effect=get_message_side_effect)
        gateway._pubsub = pubsub

        await gateway._receive_from_redis()

        # Should not forward subscribe confirmation
        mock_websocket.send_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_receive_waits_for_subscriptions(self, mock_websocket, mock_stream_manager):
        """Test that receive loop waits for subscriptions before reading."""
        gateway = WebSocketGateway(mock_websocket, mock_stream_manager)
        gateway._running = True
        # No subscriptions initially

        pubsub = AsyncMock()
        gateway._pubsub = pubsub

        call_count = 0

        async def sleep_side_effect(duration):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                gateway._running = False

        with patch("squant.websocket.handlers.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_sleep.side_effect = sleep_side_effect

            await gateway._receive_from_redis()

            # Should have waited (slept) because no subscriptions
            assert mock_sleep.call_count >= 1


class TestWebSocketConnection:
    """Test legacy WebSocketConnection class."""

    @pytest.mark.asyncio
    async def test_init(self, mock_websocket, mock_stream_manager):
        """Test WebSocketConnection initialization."""
        connection = WebSocketConnection(
            mock_websocket,
            "squant:ws:ticker:BTC/USDT",
            mock_stream_manager,
        )

        assert connection.websocket is mock_websocket
        assert connection.redis_channel == "squant:ws:ticker:BTC/USDT"
        assert connection.stream_manager is mock_stream_manager
        assert connection._running is False

    @pytest.mark.asyncio
    async def test_handle_ping(self, mock_websocket, mock_stream_manager):
        """Test ping handling in client messages."""
        connection = WebSocketConnection(
            mock_websocket,
            "squant:ws:ticker:BTC/USDT",
            mock_stream_manager,
        )
        connection._running = True

        call_count = 0

        async def receive_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "ping"
            raise WebSocketDisconnect()

        mock_websocket.receive_text = AsyncMock(side_effect=receive_side_effect)

        await connection._handle_client_messages()

        mock_websocket.send_text.assert_called_once_with("pong")


class TestWebSocketGatewaySendError:
    """Test WebSocketGateway error sending."""

    @pytest.mark.asyncio
    async def test_send_error(self, mock_websocket, mock_stream_manager):
        """Test sending error message."""
        gateway = WebSocketGateway(mock_websocket, mock_stream_manager)

        await gateway._send_error("Test error message")

        mock_websocket.send_json.assert_called_once_with(
            {
                "type": "error",
                "message": "Test error message",
            }
        )


class TestWebSocketGatewaySubscribeOKX:
    """Test WebSocketGateway _subscribe_okx method."""

    @pytest.mark.asyncio
    async def test_subscribe_okx_ticker(self, mock_websocket, mock_stream_manager):
        """Test _subscribe_okx for ticker."""
        gateway = WebSocketGateway(mock_websocket, mock_stream_manager)

        await gateway._subscribe_okx("ticker:BTC/USDT")

        mock_stream_manager.subscribe_ticker.assert_called_once_with("BTC/USDT")

    @pytest.mark.asyncio
    async def test_subscribe_okx_candle(self, mock_websocket, mock_stream_manager):
        """Test _subscribe_okx for candle."""
        gateway = WebSocketGateway(mock_websocket, mock_stream_manager)

        await gateway._subscribe_okx("candle:ETH/USDT:4h")

        mock_stream_manager.subscribe_candles.assert_called_once_with("ETH/USDT", "4h")

    @pytest.mark.asyncio
    async def test_subscribe_okx_trade(self, mock_websocket, mock_stream_manager):
        """Test _subscribe_okx for trade."""
        gateway = WebSocketGateway(mock_websocket, mock_stream_manager)

        await gateway._subscribe_okx("trade:SOL/USDT")

        mock_stream_manager.subscribe_trades.assert_called_once_with("SOL/USDT")

    @pytest.mark.asyncio
    async def test_subscribe_okx_orderbook(self, mock_websocket, mock_stream_manager):
        """Test _subscribe_okx for orderbook."""
        gateway = WebSocketGateway(mock_websocket, mock_stream_manager)

        await gateway._subscribe_okx("orderbook:DOGE/USDT")

        mock_stream_manager.subscribe_orderbook.assert_called_once_with("DOGE/USDT")

    @pytest.mark.asyncio
    async def test_subscribe_okx_orders(self, mock_websocket, mock_stream_manager):
        """Test _subscribe_okx for private orders."""
        gateway = WebSocketGateway(mock_websocket, mock_stream_manager)

        await gateway._subscribe_okx("orders")

        mock_stream_manager.subscribe_orders.assert_called_once()

    @pytest.mark.asyncio
    async def test_subscribe_okx_account(self, mock_websocket, mock_stream_manager):
        """Test _subscribe_okx for private account."""
        gateway = WebSocketGateway(mock_websocket, mock_stream_manager)

        await gateway._subscribe_okx("account")

        mock_stream_manager.subscribe_account.assert_called_once()

    @pytest.mark.asyncio
    async def test_subscribe_okx_handles_error(self, mock_websocket, mock_stream_manager):
        """Test _subscribe_okx handles errors gracefully."""
        gateway = WebSocketGateway(mock_websocket, mock_stream_manager)
        mock_stream_manager.subscribe_ticker = AsyncMock(side_effect=Exception("Connection failed"))

        # Should not raise
        await gateway._subscribe_okx("ticker:BTC/USDT")

    @pytest.mark.asyncio
    async def test_subscribe_okx_invalid_channel(self, mock_websocket, mock_stream_manager):
        """Test _subscribe_okx with invalid channel format."""
        gateway = WebSocketGateway(mock_websocket, mock_stream_manager)

        # Invalid channel type - should not call any subscription
        await gateway._subscribe_okx("invalid")

        mock_stream_manager.subscribe_ticker.assert_not_called()
        mock_stream_manager.subscribe_candles.assert_not_called()

    @pytest.mark.asyncio
    async def test_subscribe_okx_ticker_missing_symbol(self, mock_websocket, mock_stream_manager):
        """Test _subscribe_okx with ticker but no symbol."""
        gateway = WebSocketGateway(mock_websocket, mock_stream_manager)

        # ticker without symbol - should not call subscribe
        await gateway._subscribe_okx("ticker")

        mock_stream_manager.subscribe_ticker.assert_not_called()


class TestWebSocketGatewayErrorHandling:
    """Test WebSocketGateway error handling."""

    @pytest.mark.asyncio
    async def test_handle_subscribe_missing_channel(self, mock_websocket, mock_stream_manager):
        """Test subscribing with missing channel field."""
        gateway = WebSocketGateway(mock_websocket, mock_stream_manager)
        gateway._running = True

        call_count = 0

        async def receive_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return json.dumps({"type": "subscribe"})  # Missing 'channel'
            raise WebSocketDisconnect()

        mock_websocket.receive_text = AsyncMock(side_effect=receive_side_effect)

        await gateway._handle_client_messages()

        mock_websocket.send_json.assert_called_once_with(
            {
                "type": "error",
                "message": "Missing 'channel' field",
            }
        )

    @pytest.mark.asyncio
    async def test_handle_unsubscribe_missing_channel(self, mock_websocket, mock_stream_manager):
        """Test unsubscribing with missing channel field."""
        gateway = WebSocketGateway(mock_websocket, mock_stream_manager)
        gateway._running = True

        call_count = 0

        async def receive_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return json.dumps({"type": "unsubscribe"})  # Missing 'channel'
            raise WebSocketDisconnect()

        mock_websocket.receive_text = AsyncMock(side_effect=receive_side_effect)

        await gateway._handle_client_messages()

        mock_websocket.send_json.assert_called_once_with(
            {
                "type": "error",
                "message": "Missing 'channel' field",
            }
        )

    @pytest.mark.asyncio
    async def test_handle_unexpected_exception(self, mock_websocket, mock_stream_manager):
        """Test handling of unexpected exceptions in client messages."""
        gateway = WebSocketGateway(mock_websocket, mock_stream_manager)
        gateway._running = True

        mock_websocket.receive_text = AsyncMock(side_effect=RuntimeError("Unexpected error"))

        await gateway._handle_client_messages()

        # Gateway should stop running after unexpected exception
        assert gateway._running is False

    @pytest.mark.asyncio
    async def test_subscribe_failure_sends_error(self, mock_websocket, mock_stream_manager):
        """Test that subscription failure sends error to client."""
        gateway = WebSocketGateway(mock_websocket, mock_stream_manager)
        gateway._running = True

        # Setup mock pubsub that fails
        mock_pubsub = AsyncMock()
        mock_pubsub.subscribe = AsyncMock(side_effect=Exception("Redis error"))
        gateway._pubsub = mock_pubsub

        await gateway._subscribe("ticker:BTC/USDT")

        # Should send error message
        mock_websocket.send_json.assert_called_with(
            {
                "type": "error",
                "message": "Failed to subscribe to ticker:BTC/USDT",
            }
        )
