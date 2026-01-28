"""OKX WebSocket client with authentication, heartbeat, and auto-reconnect."""

import asyncio
import base64
import contextlib
import hashlib
import hmac
import json
import logging
import time
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection
from websockets.exceptions import ConnectionClosed, ConnectionClosedError

from squant.infra.exchange.exceptions import (
    ExchangeAuthenticationError,
    ExchangeConnectionError,
)

logger = logging.getLogger(__name__)

# Type alias for message handlers
MessageHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


class OKXWebSocketClient:
    """WebSocket client for OKX exchange.

    Handles connection management, authentication, heartbeat,
    and automatic reconnection with exponential backoff.
    """

    # Public WebSocket endpoints
    PUBLIC_WS_URL = "wss://ws.okx.com:8443/ws/v5/public"
    PRIVATE_WS_URL = "wss://ws.okx.com:8443/ws/v5/private"
    BUSINESS_WS_URL = "wss://ws.okx.com:8443/ws/v5/business"

    # Demo/Testnet endpoints
    DEMO_PUBLIC_WS_URL = "wss://wspap.okx.com:8443/ws/v5/public?brokerId=9999"
    DEMO_PRIVATE_WS_URL = "wss://wspap.okx.com:8443/ws/v5/private?brokerId=9999"
    DEMO_BUSINESS_WS_URL = "wss://wspap.okx.com:8443/ws/v5/business?brokerId=9999"

    # Connection settings
    HEARTBEAT_INTERVAL = 25.0  # OKX requires ping within 30 seconds
    RECONNECT_MAX_ATTEMPTS = 10
    RECONNECT_BASE_DELAY = 1.0  # seconds
    RECONNECT_MAX_DELAY = 60.0  # seconds
    CONNECTION_TIMEOUT = 30.0
    INACTIVITY_TIMEOUT = 30.0  # Reconnect if no data for 30 seconds

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        passphrase: str | None = None,
        testnet: bool = False,
        private: bool = False,
        business: bool = False,
    ) -> None:
        """Initialize OKX WebSocket client.

        Args:
            api_key: OKX API key (required for private channels).
            api_secret: OKX API secret (required for private channels).
            passphrase: OKX API passphrase (required for private channels).
            testnet: Whether to use testnet/demo trading.
            private: Whether this is for private channels.
            business: Whether this is for business channels (candles, etc.).
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.testnet = testnet
        self.private = private
        self.business = business

        # Connection state
        self._ws: ClientConnection | None = None
        self._connected = False
        self._authenticated = False
        self._running = False
        self._reconnect_count = 0

        # Subscriptions management
        self._subscriptions: list[dict[str, str]] = []

        # Message handlers
        self._handlers: list[MessageHandler] = []

        # Background tasks
        self._receive_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None

        # Inactivity tracking
        self._last_message_time: float = 0

        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

    @property
    def ws_url(self) -> str:
        """Get WebSocket URL based on configuration."""
        if self.private:
            return self.DEMO_PRIVATE_WS_URL if self.testnet else self.PRIVATE_WS_URL
        if self.business:
            return self.DEMO_BUSINESS_WS_URL if self.testnet else self.BUSINESS_WS_URL
        return self.DEMO_PUBLIC_WS_URL if self.testnet else self.PUBLIC_WS_URL

    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self._connected and self._ws is not None

    @property
    def is_authenticated(self) -> bool:
        """Check if authenticated (for private channels)."""
        return self._authenticated

    def _generate_signature(self, timestamp: str) -> str:
        """Generate HMAC-SHA256 signature for WebSocket authentication.

        Args:
            timestamp: Unix timestamp as string.

        Returns:
            Base64-encoded signature.
        """
        if not self.api_secret:
            raise ExchangeAuthenticationError(
                message="API secret required for authentication",
                exchange="okx",
            )

        # OKX WebSocket auth: sign(timestamp + 'GET' + '/users/self/verify')
        message = f"{timestamp}GET/users/self/verify"
        mac = hmac.new(
            self.api_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        )
        return base64.b64encode(mac.digest()).decode("utf-8")

    async def connect(self) -> None:
        """Establish WebSocket connection."""
        if self._connected:
            logger.debug("Already connected")
            return

        async with self._lock:
            try:
                logger.info(f"Connecting to OKX WebSocket: {self.ws_url}")
                self._ws = await asyncio.wait_for(
                    websockets.connect(
                        self.ws_url,
                        ping_interval=None,  # We handle our own heartbeat
                        ping_timeout=None,
                        close_timeout=10,
                    ),
                    timeout=self.CONNECTION_TIMEOUT,
                )
                self._connected = True
                self._reconnect_count = 0
                self._last_message_time = time.monotonic()
                logger.info("WebSocket connection established")

                # Authenticate if private channel
                if self.private:
                    await self._authenticate()

                # Start background tasks
                self._running = True
                self._receive_task = asyncio.create_task(self._receive_loop())
                self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

                # Re-subscribe to previous channels
                if self._subscriptions:
                    await self._resubscribe()

            except TimeoutError as e:
                raise ExchangeConnectionError(
                    message=f"Connection timeout: {e}",
                    exchange="okx",
                ) from e
            except Exception as e:
                raise ExchangeConnectionError(
                    message=f"Failed to connect: {e}",
                    exchange="okx",
                ) from e

    async def _authenticate(self) -> None:
        """Authenticate for private channels."""
        if not all([self.api_key, self.api_secret, self.passphrase]):
            raise ExchangeAuthenticationError(
                message="API credentials required for private channels",
                exchange="okx",
            )

        timestamp = str(int(datetime.now(UTC).timestamp()))
        signature = self._generate_signature(timestamp)

        login_msg = {
            "op": "login",
            "args": [
                {
                    "apiKey": self.api_key,
                    "passphrase": self.passphrase,
                    "timestamp": timestamp,
                    "sign": signature,
                }
            ],
        }

        await self._send(login_msg)

        # Wait for login response
        try:
            response = await asyncio.wait_for(
                self._wait_for_response("login"),
                timeout=10.0,
            )
            if response.get("code") == "0":
                self._authenticated = True
                logger.info("WebSocket authentication successful")
            else:
                raise ExchangeAuthenticationError(
                    message=f"Authentication failed: {response.get('msg', 'Unknown error')}",
                    exchange="okx",
                )
        except TimeoutError as e:
            raise ExchangeAuthenticationError(
                message="Authentication timeout",
                exchange="okx",
            ) from e

    async def _wait_for_response(self, event: str) -> dict[str, Any]:
        """Wait for a specific response event.

        Args:
            event: Event type to wait for (e.g., 'login', 'subscribe').

        Returns:
            Response message.
        """
        if not self._ws:
            raise ExchangeConnectionError(
                message="Not connected",
                exchange="okx",
            )

        while True:
            try:
                raw_msg = await self._ws.recv()
                if raw_msg == "pong":
                    continue

                msg = json.loads(raw_msg)
                self._last_message_time = time.monotonic()

                if msg.get("event") == event:
                    return msg

                # Also handle error responses
                if msg.get("event") == "error":
                    return msg

            except json.JSONDecodeError:
                continue

    async def close(self) -> None:
        """Close WebSocket connection and cleanup."""
        logger.info("Closing WebSocket connection")
        self._running = False

        # Cancel background tasks
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._receive_task
            self._receive_task = None

        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat_task
            self._heartbeat_task = None

        # Close WebSocket
        if self._ws:
            try:
                await self._ws.close()
            except Exception as e:
                logger.warning(f"Error closing WebSocket: {e}")
            self._ws = None

        self._connected = False
        self._authenticated = False
        logger.info("WebSocket connection closed")

    async def _send(self, message: dict[str, Any]) -> None:
        """Send a message through WebSocket.

        Args:
            message: Message to send.
        """
        if not self._ws or not self._connected:
            raise ExchangeConnectionError(
                message="Not connected",
                exchange="okx",
            )

        try:
            await self._ws.send(json.dumps(message))
        except ConnectionClosed as e:
            self._connected = False
            raise ExchangeConnectionError(
                message=f"Connection closed: {e}",
                exchange="okx",
            ) from e

    async def subscribe(self, channels: list[dict[str, str]]) -> None:
        """Subscribe to channels.

        Args:
            channels: List of channel subscriptions.
                Example: [{"channel": "tickers", "instId": "BTC-USDT"}]
        """
        if not channels:
            return

        # Add to subscriptions list for re-subscription on reconnect
        for channel in channels:
            if channel not in self._subscriptions:
                self._subscriptions.append(channel)

        subscribe_msg = {
            "op": "subscribe",
            "args": channels,
        }

        await self._send(subscribe_msg)
        logger.info(f"Subscribed to channels: {channels}")

    async def unsubscribe(self, channels: list[dict[str, str]]) -> None:
        """Unsubscribe from channels.

        Args:
            channels: List of channel subscriptions to remove.
        """
        if not channels:
            return

        # Remove from subscriptions list
        for channel in channels:
            if channel in self._subscriptions:
                self._subscriptions.remove(channel)

        unsubscribe_msg = {
            "op": "unsubscribe",
            "args": channels,
        }

        await self._send(unsubscribe_msg)
        logger.info(f"Unsubscribed from channels: {channels}")

    async def _resubscribe(self) -> None:
        """Re-subscribe to all previously subscribed channels."""
        if not self._subscriptions:
            return

        logger.info(f"Re-subscribing to {len(self._subscriptions)} channels")
        subscribe_msg = {
            "op": "subscribe",
            "args": self._subscriptions,
        }
        await self._send(subscribe_msg)

    def add_handler(self, handler: MessageHandler) -> None:
        """Add a message handler.

        Args:
            handler: Async function to handle incoming messages.
        """
        if handler not in self._handlers:
            self._handlers.append(handler)

    def remove_handler(self, handler: MessageHandler) -> None:
        """Remove a message handler.

        Args:
            handler: Handler to remove.
        """
        if handler in self._handlers:
            self._handlers.remove(handler)

    async def _receive_loop(self) -> None:
        """Background task to receive and process messages."""
        while self._running:
            try:
                if not self._ws:
                    await asyncio.sleep(0.1)
                    continue

                try:
                    raw_msg = await asyncio.wait_for(
                        self._ws.recv(),
                        timeout=self.INACTIVITY_TIMEOUT,
                    )
                except TimeoutError:
                    # No data received, check connection
                    logger.warning("No data received, checking connection...")
                    await self._handle_disconnect()
                    continue

                self._last_message_time = time.monotonic()

                # Handle pong response
                if raw_msg == "pong":
                    logger.debug("Received pong")
                    continue

                # Parse JSON message
                try:
                    msg = json.loads(raw_msg)
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse message: {e}")
                    continue

                # Handle different message types
                if "event" in msg:
                    await self._handle_event(msg)
                elif "data" in msg:
                    await self._handle_data(msg)

            except ConnectionClosedError as e:
                logger.warning(f"Connection closed: {e}")
                await self._handle_disconnect()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Error in receive loop: {e}")
                await asyncio.sleep(1)

    async def _handle_event(self, msg: dict[str, Any]) -> None:
        """Handle event messages (subscribe confirmations, errors, etc.)."""
        event = msg.get("event")

        if event == "subscribe":
            logger.debug(f"Subscription confirmed: {msg.get('arg')}")
        elif event == "unsubscribe":
            logger.debug(f"Unsubscription confirmed: {msg.get('arg')}")
        elif event == "error":
            logger.error(f"WebSocket error: {msg.get('msg')} (code: {msg.get('code')})")
        elif event == "login":
            if msg.get("code") == "0":
                logger.info("Login successful")
            else:
                logger.error(f"Login failed: {msg.get('msg')}")

    async def _handle_data(self, msg: dict[str, Any]) -> None:
        """Handle data messages and dispatch to handlers."""
        # Dispatch to all handlers
        for handler in self._handlers:
            try:
                await handler(msg)
            except Exception as e:
                logger.exception(f"Error in message handler: {e}")

    async def _heartbeat_loop(self) -> None:
        """Background task to send periodic heartbeat."""
        while self._running:
            try:
                await asyncio.sleep(self.HEARTBEAT_INTERVAL)

                if self._ws and self._connected:
                    try:
                        await self._ws.send("ping")
                        logger.debug("Sent ping")
                    except ConnectionClosed:
                        await self._handle_disconnect()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Error in heartbeat loop: {e}")

    async def _handle_disconnect(self) -> None:
        """Handle disconnection and trigger reconnection."""
        self._connected = False
        self._authenticated = False

        if not self._running:
            return

        logger.warning("Disconnected, attempting reconnection...")
        await self._reconnect()

    async def _reconnect(self) -> None:
        """Attempt to reconnect with exponential backoff."""
        while self._running and self._reconnect_count < self.RECONNECT_MAX_ATTEMPTS:
            self._reconnect_count += 1

            # Calculate delay with exponential backoff
            delay = min(
                self.RECONNECT_BASE_DELAY * (2 ** (self._reconnect_count - 1)),
                self.RECONNECT_MAX_DELAY,
            )

            logger.info(
                f"Reconnection attempt {self._reconnect_count}/{self.RECONNECT_MAX_ATTEMPTS} "
                f"in {delay:.1f}s"
            )
            await asyncio.sleep(delay)

            try:
                # Close existing connection
                if self._ws:
                    with contextlib.suppress(Exception):
                        await self._ws.close()
                    self._ws = None

                # Reconnect
                self._ws = await asyncio.wait_for(
                    websockets.connect(
                        self.ws_url,
                        ping_interval=None,
                        ping_timeout=None,
                        close_timeout=10,
                    ),
                    timeout=self.CONNECTION_TIMEOUT,
                )
                self._connected = True
                self._last_message_time = time.monotonic()
                logger.info("Reconnection successful")

                # Re-authenticate if needed
                if self.private:
                    await self._authenticate()

                # Re-subscribe
                if self._subscriptions:
                    await self._resubscribe()

                self._reconnect_count = 0
                return

            except Exception as e:
                logger.warning(f"Reconnection failed: {e}")

        if self._reconnect_count >= self.RECONNECT_MAX_ATTEMPTS:
            logger.error("Max reconnection attempts reached")
            self._running = False

    async def __aenter__(self) -> "OKXWebSocketClient":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()
