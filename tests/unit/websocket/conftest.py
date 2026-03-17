"""
WebSocket unit test fixtures for Squant.

This module provides shared fixtures specific to WebSocket testing.
These fixtures extend the base fixtures from tests/unit/conftest.py with
WebSocket-specific utilities like mock WebSocket connections and stream providers.

Fixture Categories:
    - WebSocket: Mock FastAPI WebSocket instances
    - StreamManager: Mock stream manager with subscription methods
    - CCXT Provider: Mock CCXT stream provider for WebSocket data
    - Redis Pub/Sub: Mock Redis pub/sub for message routing

Usage:
    These fixtures are automatically available to all tests under tests/unit/websocket/.

    Example:
        @pytest.mark.asyncio
        async def test_websocket_subscribe(mock_websocket, mock_stream_manager):
            gateway = WebSocketGateway(mock_websocket, mock_stream_manager)
            await gateway._subscribe("ticker:BTC/USDT")
            mock_stream_manager.subscribe_ticker.assert_called_once()

Notes:
    - All WebSocket fixtures use AsyncMock for async operations
    - Original fixtures in individual test files are preserved for backward compatibility
    - Test classes should use @pytest.mark.asyncio for async test methods

Important Testing Warnings:
    - Never mock asyncio.sleep() in code with infinite while loops
    - Never test methods with `while running:` loops directly
    - Never call WebSocket run() methods in unit tests
    - See CLAUDE.md "Dangerous Operations" section for details
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import WebSocket

if TYPE_CHECKING:
    pass


# ============================================================================
# WebSocket Connection Fixtures
# ============================================================================


@pytest.fixture
def mock_websocket():
    """
    Create a mock FastAPI WebSocket instance.

    Provides an AsyncMock with all WebSocket methods:
        - accept: Accept WebSocket connection
        - send_json: Send JSON data
        - send_text: Send text data
        - receive_text: Receive text data
        - receive_json: Receive JSON data
        - close: Close connection

    Returns:
        AsyncMock: Mock WebSocket instance

    Example:
        @pytest.mark.asyncio
        async def test_send_message(mock_websocket):
            await mock_websocket.send_json({"type": "ping"})
            mock_websocket.send_json.assert_called_once()
    """
    ws = AsyncMock(spec=WebSocket)
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.send_text = AsyncMock()
    ws.receive_text = AsyncMock()
    ws.receive_json = AsyncMock()
    ws.close = AsyncMock()

    # Add client info for logging
    ws.client = MagicMock()
    ws.client.host = "127.0.0.1"
    ws.client.port = 12345

    return ws


@pytest.fixture
def mock_websocket_disconnect():
    """
    Create a factory for simulating WebSocket disconnect scenarios.

    Returns a function that configures mock_websocket to raise
    WebSocketDisconnect after N messages.

    Returns:
        Callable: Factory function for disconnect scenarios

    Example:
        @pytest.mark.asyncio
        async def test_disconnect(mock_websocket, mock_websocket_disconnect):
            mock_websocket_disconnect(mock_websocket, after_messages=2)
            # First 2 calls succeed, 3rd raises WebSocketDisconnect
    """
    from fastapi import WebSocketDisconnect

    def _configure(ws: AsyncMock, after_messages: int = 1, messages: list | None = None):
        """
        Configure WebSocket to disconnect after N messages.

        Args:
            ws: The mock WebSocket to configure
            after_messages: Number of messages before disconnect
            messages: Optional list of messages to return before disconnect
        """
        call_count = 0
        messages = messages or ["ping"]

        async def receive_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count <= len(messages):
                return messages[call_count - 1]
            raise WebSocketDisconnect()

        ws.receive_text = AsyncMock(side_effect=receive_side_effect)

    return _configure


# ============================================================================
# Stream Manager Fixtures
# ============================================================================


@pytest.fixture
def mock_stream_manager():
    """
    Create a mock StreamManager for WebSocket testing.

    Provides a MagicMock with all StreamManager properties and methods:
        Properties:
            - REDIS_CHANNEL_PREFIX: Channel prefix for Redis pub/sub
            - is_running: Whether manager is running
            - is_healthy: Whether manager is healthy

        Subscription Methods:
            - subscribe_ticker: Subscribe to ticker updates
            - subscribe_candles: Subscribe to candlestick updates
            - subscribe_trades: Subscribe to trade updates
            - subscribe_orderbook: Subscribe to order book updates
            - subscribe_orders: Subscribe to private order updates
            - subscribe_account: Subscribe to private account updates

        Unsubscription Methods:
            - unsubscribe_ticker: Unsubscribe from ticker
            - unsubscribe_candles: Unsubscribe from candles
            - unsubscribe_trades: Unsubscribe from trades

        Control Methods:
            - switch_exchange: Switch to different exchange
            - start: Start the manager
            - stop: Stop the manager

    Returns:
        MagicMock: Mock stream manager

    Example:
        @pytest.mark.asyncio
        async def test_subscribe(mock_stream_manager):
            await mock_stream_manager.subscribe_ticker("BTC/USDT")
            mock_stream_manager.subscribe_ticker.assert_called_once()
    """
    manager = MagicMock()

    # Properties
    manager.REDIS_CHANNEL_PREFIX = "squant:ws:"
    manager.is_running = True
    manager.is_healthy = True

    # Subscription methods
    manager.subscribe_ticker = AsyncMock()
    manager.subscribe_candles = AsyncMock()
    manager.subscribe_trades = AsyncMock()
    manager.subscribe_orderbook = AsyncMock()
    manager.subscribe_orders = AsyncMock()
    manager.subscribe_account = AsyncMock()

    # Unsubscription methods
    manager.unsubscribe_ticker = AsyncMock()
    manager.unsubscribe_candles = AsyncMock()
    manager.unsubscribe_trades = AsyncMock()
    manager.unsubscribe_orderbook = AsyncMock()

    # Control methods
    manager.switch_exchange = AsyncMock()
    manager.start = AsyncMock()
    manager.stop = AsyncMock()
    manager.try_start = AsyncMock(return_value=True)

    return manager


@pytest.fixture
def mock_stream_manager_not_running(mock_stream_manager):
    """
    Create a mock StreamManager that is not running.

    This is useful for testing error cases when the manager
    hasn't been started.

    Args:
        mock_stream_manager: Base stream manager fixture

    Returns:
        MagicMock: Mock stream manager with is_running=False
    """
    mock_stream_manager.is_running = False
    mock_stream_manager.is_healthy = False
    return mock_stream_manager


# ============================================================================
# CCXT Provider Fixtures
# ============================================================================


@pytest.fixture
def mock_ccxt_provider():
    """
    Create a mock CCXT stream provider for WebSocket testing.

    Provides an AsyncMock with all CCXTStreamProvider methods:
        Properties:
            - exchange_id: Current exchange ID
            - is_connected: Connection status

        Connection Methods:
            - connect: Establish connection
            - close: Close connection
            - is_healthy: Check health status

        Watch Methods:
            - watch_ticker: Watch ticker updates
            - watch_ohlcv: Watch candlestick updates
            - watch_trades: Watch trade updates
            - watch_order_book: Watch order book updates

        Handler Methods:
            - add_handler: Add message handler
            - unwatch: Unwatch a channel

    Returns:
        AsyncMock: Mock CCXT stream provider

    Example:
        @pytest.mark.asyncio
        async def test_provider(mock_ccxt_provider):
            await mock_ccxt_provider.connect()
            mock_ccxt_provider.connect.assert_called_once()
    """
    provider = AsyncMock()

    # Properties
    provider.exchange_id = "okx"
    provider.is_connected = True

    # Connection methods
    provider.connect = AsyncMock()
    provider.close = AsyncMock()
    provider.is_healthy = MagicMock(return_value=True)

    # Watch methods
    provider.watch_ticker = AsyncMock()
    provider.watch_ohlcv = AsyncMock()
    provider.watch_trades = AsyncMock()
    provider.watch_order_book = AsyncMock()

    # Handler methods
    provider.add_handler = MagicMock()
    provider.unwatch = AsyncMock()

    return provider


@pytest.fixture
def mock_ccxt_provider_factory(mock_ccxt_provider):
    """
    Create a factory that returns mock CCXT providers.

    This is useful for testing exchange switching where multiple
    providers are created.

    Returns:
        Callable: Factory function that returns mock providers

    Example:
        def test_switch(mock_ccxt_provider_factory):
            with patch("CCXTStreamProvider", side_effect=mock_ccxt_provider_factory):
                # Each call creates a new provider
                pass
    """
    call_count = 0

    def _factory(*args, **kwargs):
        nonlocal call_count
        call_count += 1

        provider = AsyncMock()
        provider.exchange_id = kwargs.get("exchange_id", "okx")
        provider.is_connected = True
        provider.connect = AsyncMock()
        provider.close = AsyncMock()
        provider.is_healthy = MagicMock(return_value=True)
        provider.watch_ticker = AsyncMock()
        provider.watch_ohlcv = AsyncMock()
        provider.watch_trades = AsyncMock()
        provider.watch_order_book = AsyncMock()
        provider.add_handler = MagicMock()
        provider.unwatch = AsyncMock()

        return provider

    return _factory


# ============================================================================
# Redis Pub/Sub Fixtures for WebSocket
# ============================================================================


@pytest.fixture
def mock_ws_redis():
    """
    Create a mock Redis client configured for WebSocket pub/sub.

    This extends the base mock_redis_client with WebSocket-specific
    configurations.

    Returns:
        tuple[AsyncMock, AsyncMock]: Tuple of (redis_client, pubsub)

    Example:
        @pytest.mark.asyncio
        async def test_pubsub(mock_ws_redis):
            redis, pubsub = mock_ws_redis
            await pubsub.subscribe("squant:ws:ticker:BTC/USDT")
    """
    redis = AsyncMock()
    pubsub = AsyncMock()

    # Pub/sub methods
    pubsub.subscribe = AsyncMock()
    pubsub.unsubscribe = AsyncMock()
    pubsub.ping = AsyncMock()
    pubsub.get_message = AsyncMock(return_value=None)

    # Configure redis.pubsub() to return pubsub
    redis.pubsub = MagicMock(return_value=pubsub)

    # Publish method
    redis.publish = AsyncMock(return_value=1)

    return redis, pubsub


@pytest.fixture
def mock_redis_message_factory():
    """
    Create a factory for generating mock Redis pub/sub messages.

    Returns:
        Callable: Factory function for creating messages

    Example:
        def test_receive(mock_redis_message_factory, mock_ws_redis):
            redis, pubsub = mock_ws_redis
            message = mock_redis_message_factory("ticker", {"last": "42000"})
            pubsub.get_message.return_value = message
    """

    def _create(
        msg_type: str = "message",
        data: dict | str | None = None,
        channel: str = "squant:ws:ticker:BTC/USDT",
    ) -> dict:
        """
        Create a mock Redis pub/sub message.

        Args:
            msg_type: Message type ("message", "subscribe", etc.)
            data: Message data (will be JSON encoded if dict)
            channel: Channel name

        Returns:
            dict: Mock Redis message
        """
        import json

        if data is None:
            data = {"type": "ticker", "data": {"last": "42000"}}

        if isinstance(data, dict):
            data = json.dumps(data).encode()
        elif isinstance(data, str):
            data = data.encode()

        return {
            "type": msg_type,
            "data": data,
            "channel": channel.encode() if isinstance(channel, str) else channel,
        }

    return _create


# ============================================================================
# WebSocket Gateway Fixtures
# ============================================================================


@pytest.fixture
def websocket_gateway(mock_websocket, mock_stream_manager):
    """
    Create a WebSocketGateway instance with mocked dependencies.

    Returns a configured gateway ready for testing.

    Args:
        mock_websocket: Mock WebSocket connection
        mock_stream_manager: Mock stream manager

    Returns:
        WebSocketGateway: Gateway instance for testing

    Example:
        @pytest.mark.asyncio
        async def test_gateway(websocket_gateway):
            gateway = websocket_gateway
            await gateway._subscribe("ticker:BTC/USDT")
    """
    from squant.websocket.handlers import WebSocketGateway

    gateway = WebSocketGateway(mock_websocket, mock_stream_manager)
    return gateway


@pytest.fixture
def websocket_gateway_with_pubsub(websocket_gateway, mock_ws_redis):
    """
    Create a WebSocketGateway with Redis pub/sub configured.

    Args:
        websocket_gateway: Base gateway fixture
        mock_ws_redis: Mock Redis with pub/sub

    Returns:
        WebSocketGateway: Gateway with pub/sub configured
    """
    redis, pubsub = mock_ws_redis
    websocket_gateway._redis = redis
    websocket_gateway._pubsub = pubsub
    return websocket_gateway


# ============================================================================
# Settings Fixtures for WebSocket
# ============================================================================


@pytest.fixture
def mock_ws_settings():
    """
    Create mock settings optimized for WebSocket testing.

    Extends the base mock_settings with WebSocket-specific configuration.

    Returns:
        MagicMock: Mock settings for WebSocket tests
    """
    settings = MagicMock()

    # Provider settings
    settings.default_exchange = "okx"

    # OKX credentials
    settings.okx_api_key = MagicMock()
    settings.okx_api_key.get_secret_value.return_value = "test-key"
    settings.okx_api_secret = MagicMock()
    settings.okx_api_secret.get_secret_value.return_value = "test-secret"
    settings.okx_passphrase = MagicMock()
    settings.okx_passphrase.get_secret_value.return_value = "test-passphrase"

    # Binance credentials (not configured)
    settings.binance_api_key = None
    settings.binance_api_secret = None

    # Bybit credentials (not configured)
    settings.bybit_api_key = None
    settings.bybit_api_secret = None

    return settings


# ============================================================================
# Async Test Helpers
# ============================================================================


@pytest.fixture
def create_receive_sequence():
    """
    Create a factory for simulating sequences of WebSocket messages.

    Returns a function that configures a mock WebSocket to return
    a sequence of messages then disconnect.

    Returns:
        Callable: Factory for creating receive sequences

    Example:
        @pytest.mark.asyncio
        async def test_messages(mock_websocket, create_receive_sequence):
            create_receive_sequence(mock_websocket, [
                '{"type": "subscribe", "channel": "ticker:BTC/USDT"}',
                '{"type": "ping"}',
            ])
            # Test message handling
    """
    from fastapi import WebSocketDisconnect

    def _configure(ws: AsyncMock, messages: list[str]):
        """
        Configure WebSocket to return messages in sequence.

        Args:
            ws: Mock WebSocket to configure
            messages: List of messages to return
        """
        call_count = 0

        async def receive_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count <= len(messages):
                return messages[call_count - 1]
            raise WebSocketDisconnect()

        ws.receive_text = AsyncMock(side_effect=receive_side_effect)

    return _configure


@pytest.fixture
def create_pubsub_sequence():
    """
    Create a factory for simulating sequences of Redis pub/sub messages.

    Returns a function that configures mock pubsub to return
    a sequence of messages.

    Returns:
        Callable: Factory for creating pub/sub sequences

    Example:
        @pytest.mark.asyncio
        async def test_redis_messages(mock_ws_redis, create_pubsub_sequence):
            redis, pubsub = mock_ws_redis
            create_pubsub_sequence(pubsub, [
                {"type": "message", "data": b'{"price": 42000}'},
            ])
    """

    def _configure(pubsub: AsyncMock, messages: list[dict | None]):
        """
        Configure pubsub to return messages in sequence.

        Args:
            pubsub: Mock pubsub to configure
            messages: List of messages to return (None for no message)
        """
        call_count = 0

        async def get_message_side_effect(**kwargs):
            nonlocal call_count
            if call_count < len(messages):
                msg = messages[call_count]
                call_count += 1
                return msg
            return None

        pubsub.get_message = AsyncMock(side_effect=get_message_side_effect)

    return _configure
