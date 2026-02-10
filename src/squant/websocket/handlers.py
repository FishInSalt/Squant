"""FastAPI WebSocket endpoints for real-time data streaming."""

import asyncio
import contextlib
import json
import logging
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from squant.infra.redis import get_redis_context
from squant.websocket.manager import StreamManager, get_stream_manager

logger = logging.getLogger(__name__)

router = APIRouter()


# ==================== Unified WebSocket Gateway ====================


class WebSocketGateway:
    """Unified WebSocket gateway supporting multiple channel subscriptions.

    This gateway allows clients to:
    1. Connect once to /ws
    2. Subscribe/unsubscribe to multiple channels via JSON messages
    3. Receive real-time updates from all subscribed channels

    Message Protocol:
    - Subscribe: {"type": "subscribe", "channel": "ticker:BTC/USDT"}
    - Unsubscribe: {"type": "unsubscribe", "channel": "ticker:BTC/USDT"}
    - Ping: "ping" or {"type": "ping"}
    - Pong response: {"type": "pong"}

    Channel formats:
    - ticker:{symbol} - e.g., ticker:BTC/USDT
    - candle:{symbol}:{timeframe} - e.g., candle:BTC/USDT:1m
    - trade:{symbol} - e.g., trade:BTC/USDT
    - orderbook:{symbol} - e.g., orderbook:BTC/USDT
    - orders - private order updates
    - account - private account updates
    """

    REDIS_CHANNEL_PREFIX = "squant:ws:"

    def __init__(self, websocket: WebSocket, stream_manager: StreamManager) -> None:
        """Initialize gateway connection.

        Args:
            websocket: FastAPI WebSocket connection.
            stream_manager: Stream manager for OKX subscriptions.
        """
        self.websocket = websocket
        self.stream_manager = stream_manager
        self._running = False
        self._subscribed_channels: set[str] = set()
        self._pubsub: Any = None
        self._redis: Any = None

    async def run(self) -> None:
        """Run the gateway, handling client messages and forwarding data."""
        await self.websocket.accept()
        self._running = True
        logger.info("WebSocket gateway client connected")

        try:
            async with get_redis_context() as redis:
                self._redis = redis
                self._pubsub = redis.pubsub()

                # Auto-subscribe to system channel for broadcast messages
                # (e.g., exchange_switching notifications)
                system_channel = f"{self.REDIS_CHANNEL_PREFIX}system"
                await self._pubsub.subscribe(system_channel)
                self._subscribed_channels.add("system")
                logger.info("Auto-subscribed to system channel")

                # Create tasks for receiving from Redis, handling client messages,
                # and keeping the Redis connection alive
                receive_task = asyncio.create_task(self._receive_from_redis(), name="redis_receive")
                client_task = asyncio.create_task(
                    self._handle_client_messages(), name="client_messages"
                )
                heartbeat_task = asyncio.create_task(
                    self._redis_heartbeat(), name="redis_heartbeat"
                )

                # Wait for any task to complete (heartbeat should never complete normally)
                done, pending = await asyncio.wait(
                    [receive_task, client_task, heartbeat_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                # Log which task completed and why
                for task in done:
                    task_name = task.get_name()
                    try:
                        # Check if task raised an exception
                        exc = task.exception()
                        if exc:
                            logger.warning(f"Gateway task '{task_name}' failed with: {exc}")
                        else:
                            logger.debug(f"Gateway task '{task_name}' completed normally")
                    except asyncio.CancelledError:
                        logger.debug(f"Gateway task '{task_name}' was cancelled")

                # Cancel pending tasks
                for task in pending:
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task

        except WebSocketDisconnect:
            logger.info("WebSocket gateway client disconnected")
        except Exception as e:
            logger.exception(f"WebSocket gateway error: {e}")
        finally:
            self._running = False
            # Cleanup subscriptions
            if self._pubsub and self._subscribed_channels:
                for channel in list(self._subscribed_channels):
                    await self._unsubscribe_redis(channel)
            logger.info("WebSocket gateway connection closed")

    async def _redis_heartbeat(self) -> None:
        """Periodically ping Redis to keep the pubsub connection alive.

        This prevents idle connections from being closed by firewalls,
        load balancers, or the Redis server itself.

        Note: We ping via the pubsub connection specifically, as it's a separate
        connection from the regular Redis client and is the one most likely to
        become stale during long periods without messages.
        """
        heartbeat_interval = 30  # seconds
        consecutive_failures = 0
        max_failures = 3

        try:
            while self._running:
                await asyncio.sleep(heartbeat_interval)

                if not self._running:
                    break

                try:
                    # Ping via pubsub connection to keep it alive
                    # This sends a PING through the dedicated pubsub connection
                    if self._pubsub:
                        await self._pubsub.ping()
                        consecutive_failures = 0
                        logger.debug("Redis pubsub heartbeat OK")
                except Exception as e:
                    consecutive_failures += 1
                    logger.warning(
                        f"Redis pubsub heartbeat failed (attempt {consecutive_failures}/{max_failures}): {e}"
                    )
                    if consecutive_failures >= max_failures:
                        logger.error(
                            "Redis pubsub heartbeat failed too many times, stopping gateway"
                        )
                        self._running = False
                        break

        except asyncio.CancelledError:
            pass

    async def _handle_client_messages(self) -> None:
        """Handle incoming messages from the WebSocket client."""
        try:
            while self._running:
                raw_message = await self.websocket.receive_text()

                # Handle simple ping
                if raw_message == "ping":
                    await self.websocket.send_json({"type": "pong"})
                    continue

                # Parse JSON message
                try:
                    message = json.loads(raw_message)
                except json.JSONDecodeError:
                    await self._send_error("Invalid JSON format")
                    continue

                msg_type = message.get("type")

                if msg_type == "ping":
                    await self.websocket.send_json({"type": "pong"})

                elif msg_type == "subscribe":
                    channel = message.get("channel")
                    if channel:
                        await self._subscribe(channel)
                    else:
                        await self._send_error("Missing 'channel' field")

                elif msg_type == "unsubscribe":
                    channel = message.get("channel")
                    if channel:
                        await self._unsubscribe(channel)
                    else:
                        await self._send_error("Missing 'channel' field")

                else:
                    await self._send_error(f"Unknown message type: {msg_type}")

        except WebSocketDisconnect:
            self._running = False
        except asyncio.CancelledError:
            pass
        except Exception as e:
            # Catch any unexpected exceptions to prevent task from dying
            logger.exception(f"Unexpected error in client message handler: {e}")
            self._running = False

    # Valid channel prefixes for subscription (R3-017)
    VALID_CHANNEL_PREFIXES = ("ticker:", "candle:", "orderbook:", "trade:")
    VALID_EXACT_CHANNELS = ("orders", "account")
    MAX_CHANNEL_LENGTH = 64
    # Frontend max pageSize is 200 tickers + system channel + headroom for other channel types
    MAX_SUBSCRIPTIONS = 250

    async def _subscribe(self, channel: str) -> None:
        """Subscribe to a channel.

        Args:
            channel: Channel name (e.g., "ticker:BTC/USDT").
        """
        # Validate channel format (R3-017)
        if not isinstance(channel, str) or len(channel) > self.MAX_CHANNEL_LENGTH:
            await self._send_error(f"Invalid channel: too long (max {self.MAX_CHANNEL_LENGTH})")
            return

        if not channel.startswith(self.VALID_CHANNEL_PREFIXES) and (
            channel not in self.VALID_EXACT_CHANNELS
        ):
            await self._send_error(
                f"Invalid channel. Valid prefixes: {', '.join(self.VALID_CHANNEL_PREFIXES)}; "
                f"or exact: {', '.join(self.VALID_EXACT_CHANNELS)}"
            )
            return

        # Validate that prefixed channels have a non-empty value after the colon
        if ":" in channel and not channel.split(":", 1)[1]:
            await self._send_error("Invalid channel: missing value after prefix")
            return

        if len(self._subscribed_channels) >= self.MAX_SUBSCRIPTIONS:
            await self._send_error(f"Max subscriptions reached ({self.MAX_SUBSCRIPTIONS})")
            return

        if channel in self._subscribed_channels:
            await self.websocket.send_json(
                {
                    "type": "subscribed",
                    "channel": channel,
                    "message": "Already subscribed",
                }
            )
            return

        try:
            # Subscribe to Redis channel
            redis_channel = f"{self.REDIS_CHANNEL_PREFIX}{channel}"
            await self._pubsub.subscribe(redis_channel)
            self._subscribed_channels.add(channel)

            # Subscribe to OKX stream if needed
            await self._subscribe_okx(channel)

            await self.websocket.send_json(
                {
                    "type": "subscribed",
                    "channel": channel,
                }
            )
        except Exception as e:
            logger.warning(f"Failed to subscribe to {channel}: {e}")
            await self._send_error(f"Failed to subscribe to {channel}")

    async def _unsubscribe(self, channel: str) -> None:
        """Unsubscribe from a channel.

        Args:
            channel: Channel name.

        TODO: Implement reference counting for OKX subscriptions.
        Currently, OKX subscriptions are not cancelled when clients unsubscribe.
        This causes minimal resource waste (data flows to Redis but no consumer).
        A proper solution would track subscriber count per channel and call
        stream_manager.unsubscribe_* when count reaches zero.
        """
        if channel not in self._subscribed_channels:
            await self.websocket.send_json(
                {
                    "type": "unsubscribed",
                    "channel": channel,
                    "message": "Not subscribed",
                }
            )
            return

        await self._unsubscribe_redis(channel)

        await self.websocket.send_json(
            {
                "type": "unsubscribed",
                "channel": channel,
            }
        )

    async def _unsubscribe_redis(self, channel: str) -> None:
        """Unsubscribe from Redis channel."""
        redis_channel = f"{self.REDIS_CHANNEL_PREFIX}{channel}"
        await self._pubsub.unsubscribe(redis_channel)
        self._subscribed_channels.discard(channel)

    async def _subscribe_okx(self, channel: str) -> None:
        """Subscribe to OKX stream based on channel type.

        Args:
            channel: Channel name (e.g., "ticker:BTC/USDT").
        """
        parts = channel.split(":")
        channel_type = parts[0]

        try:
            if channel_type == "ticker" and len(parts) >= 2:
                symbol = parts[1]
                if not symbol:
                    logger.warning(f"Empty symbol in channel: {channel}")
                    return
                await self.stream_manager.subscribe_ticker(symbol)

            elif channel_type == "candle" and len(parts) >= 3:
                symbol = parts[1]
                timeframe = parts[2]
                if not symbol or not timeframe:
                    logger.warning(f"Empty symbol or timeframe in channel: {channel}")
                    return
                logger.info(f"Subscribing to candle: symbol={symbol}, timeframe={timeframe}")
                await self.stream_manager.subscribe_candles(symbol, timeframe)

            elif channel_type == "trade" and len(parts) >= 2:
                symbol = parts[1]
                if not symbol:
                    logger.warning(f"Empty symbol in channel: {channel}")
                    return
                await self.stream_manager.subscribe_trades(symbol)

            elif channel_type == "orderbook" and len(parts) >= 2:
                symbol = parts[1]
                if not symbol:
                    logger.warning(f"Empty symbol in channel: {channel}")
                    return
                await self.stream_manager.subscribe_orderbook(symbol)

            elif channel_type == "orders":
                await self.stream_manager.subscribe_orders()

            elif channel_type == "account":
                await self.stream_manager.subscribe_account()

            else:
                logger.warning(f"Unknown or malformed channel: {channel}")

        except Exception as e:
            logger.warning(f"Failed to subscribe OKX stream for {channel}: {e}")

    async def _receive_from_redis(self) -> None:
        """Receive messages from Redis and forward to WebSocket client."""
        consecutive_errors = 0
        max_consecutive_errors = 10  # After 10 consecutive errors, give up

        try:
            # Keep running while connection is active
            while self._running:
                # Wait for at least one subscription before calling get_message()
                # Redis pubsub requires at least one subscription to initialize the connection
                if not self._subscribed_channels:
                    await asyncio.sleep(0.1)
                    continue

                try:
                    # Use get_message with a timeout instead of listen()
                    # This prevents the issue where listen() exits immediately with no subscriptions
                    message = await self._pubsub.get_message(
                        ignore_subscribe_messages=True, timeout=1.0
                    )

                    # Reset error counter on successful operation
                    consecutive_errors = 0

                    if message is None:
                        # No message yet, continue waiting
                        continue

                    if message["type"] == "message":
                        data = message["data"]
                        if isinstance(data, bytes):
                            data = data.decode("utf-8")

                        # Intercept service_ready on system channel to re-subscribe OKX
                        redis_channel = message.get("channel", b"")
                        if isinstance(redis_channel, bytes):
                            redis_channel = redis_channel.decode("utf-8")
                        if redis_channel == f"{self.REDIS_CHANNEL_PREFIX}system":
                            try:
                                parsed = json.loads(data)
                                if parsed.get("type") == "service_ready":
                                    logger.info(
                                        "Received service_ready, re-subscribing OKX channels"
                                    )
                                    await self._resubscribe_okx_channels()
                            except (json.JSONDecodeError, KeyError):
                                pass

                        await self.websocket.send_text(data)

                except asyncio.CancelledError:
                    raise  # Re-raise cancellation
                except RuntimeError as e:
                    # Handle "pubsub connection not set" error if subscriptions were cleared
                    if "pubsub connection not set" in str(e):
                        await asyncio.sleep(0.1)
                        continue
                    # For other RuntimeErrors, log and retry
                    consecutive_errors += 1
                    logger.warning(f"Redis pubsub RuntimeError (attempt {consecutive_errors}): {e}")
                    if consecutive_errors >= max_consecutive_errors:
                        logger.error("Too many consecutive Redis errors, giving up")
                        break
                    await asyncio.sleep(0.5)
                except (ConnectionError, TimeoutError, OSError) as e:
                    # Handle connection-related errors (common after long idle periods)
                    consecutive_errors += 1
                    logger.warning(f"Redis connection error (attempt {consecutive_errors}): {e}")
                    if consecutive_errors >= max_consecutive_errors:
                        logger.error("Too many consecutive Redis connection errors, giving up")
                        break
                    # Wait longer for connection errors
                    await asyncio.sleep(1.0)
                except Exception as e:
                    # Catch all other exceptions to prevent task from dying
                    consecutive_errors += 1
                    logger.warning(
                        f"Unexpected error in Redis receive loop (attempt {consecutive_errors}): {e}"
                    )
                    if consecutive_errors >= max_consecutive_errors:
                        logger.error("Too many consecutive errors in Redis receive loop, giving up")
                        break
                    await asyncio.sleep(0.5)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(f"Fatal error in Redis receive loop: {e}")

    async def _resubscribe_okx_channels(self) -> None:
        """Re-subscribe all current channels to OKX after stream manager recovery."""
        for channel in list(self._subscribed_channels):
            if channel == "system":
                continue
            try:
                await self._subscribe_okx(channel)
            except Exception as e:
                logger.warning(f"Failed to re-subscribe OKX channel {channel}: {e}")

    async def _send_error(self, message: str) -> None:
        """Send error message to client."""
        await self.websocket.send_json(
            {
                "type": "error",
                "message": message,
            }
        )


@router.websocket("")
async def websocket_gateway(websocket: WebSocket) -> None:
    """Unified WebSocket gateway endpoint.

    This endpoint supports subscribing to multiple channels through a single connection.

    Example usage:
    ```javascript
    const ws = new WebSocket('ws://localhost:8000/api/v1/ws')

    ws.onopen = () => {
        // Subscribe to channels
        ws.send(JSON.stringify({ type: 'subscribe', channel: 'ticker:BTC/USDT' }))
        ws.send(JSON.stringify({ type: 'subscribe', channel: 'ticker:ETH/USDT' }))
        ws.send(JSON.stringify({ type: 'subscribe', channel: 'candle:BTC/USDT:1m' }))
    }

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data)
        console.log('Received:', data.type, data.channel, data.data)
    }
    ```

    Supported channels:
    - ticker:{symbol} - Real-time ticker updates
    - candle:{symbol}:{timeframe} - Candlestick updates (1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w)
    - trade:{symbol} - Trade updates
    - orderbook:{symbol} - Order book updates (5-level depth)
    - orders - Private order updates (requires API credentials)
    - account - Private account balance updates (requires API credentials)
    """
    stream_manager = get_stream_manager()

    # Never call try_start() here — it blocks the WebSocket handshake while
    # connecting to the exchange (can hang for minutes). The background task in
    # main.py handles stream manager initialization. When it finishes, it
    # publishes a service_ready event; the Gateway intercepts it and
    # re-subscribes OKX channels at that point.
    if not stream_manager.is_running:
        logger.info(
            "Stream manager not running, accepting WebSocket anyway. "
            "OKX data will flow after service_ready event."
        )

    gateway = WebSocketGateway(websocket, stream_manager)
    await gateway.run()


# ==================== Legacy Single-Channel Endpoints ====================


class WebSocketConnection:
    """Manages a single WebSocket client connection.

    Handles Redis subscription and message forwarding to the client.
    """

    def __init__(
        self,
        websocket: WebSocket,
        redis_channel: str,
        stream_manager: StreamManager,
    ) -> None:
        """Initialize WebSocket connection.

        Args:
            websocket: FastAPI WebSocket connection.
            redis_channel: Redis pub/sub channel to subscribe to.
            stream_manager: Stream manager instance.
        """
        self.websocket = websocket
        self.redis_channel = redis_channel
        self.stream_manager = stream_manager
        self._running = False

    async def run(self) -> None:
        """Run the WebSocket connection, forwarding messages from Redis."""
        await self.websocket.accept()
        self._running = True

        try:
            async with get_redis_context() as redis:
                pubsub = redis.pubsub()
                await pubsub.subscribe(self.redis_channel)
                logger.info(f"Client subscribed to {self.redis_channel}")

                # Create tasks for receiving from Redis and handling client messages
                receive_task = asyncio.create_task(self._receive_from_redis(pubsub))
                client_task = asyncio.create_task(self._handle_client_messages())

                # Wait for either task to complete (usually due to disconnect)
                _, pending = await asyncio.wait(
                    [receive_task, client_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                # Cancel pending tasks
                for task in pending:
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task

                # Unsubscribe
                await pubsub.unsubscribe(self.redis_channel)

        except WebSocketDisconnect:
            logger.info(f"Client disconnected from {self.redis_channel}")
        except Exception as e:
            logger.exception(f"WebSocket error: {e}")
        finally:
            self._running = False

    async def _receive_from_redis(self, pubsub: Any) -> None:
        """Receive messages from Redis and forward to WebSocket client."""
        try:
            async for message in pubsub.listen():
                if not self._running:
                    break

                if message["type"] == "message":
                    data = message["data"]
                    # Redis returns bytes or string depending on decode_responses setting
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    await self.websocket.send_text(data)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(f"Error receiving from Redis: {e}")

    async def _handle_client_messages(self) -> None:
        """Handle messages from the WebSocket client (e.g., ping/pong)."""
        try:
            while self._running:
                # This will raise WebSocketDisconnect when client disconnects
                message = await self.websocket.receive_text()

                # Handle ping
                if message == "ping":
                    await self.websocket.send_text("pong")

        except WebSocketDisconnect:
            self._running = False
        except asyncio.CancelledError:
            pass


# ==================== Public Channel Endpoints ====================


@router.websocket("/ticker/{symbol}")
async def websocket_ticker(
    websocket: WebSocket,
    symbol: str,
) -> None:
    """WebSocket endpoint for real-time ticker data.

    Args:
        websocket: WebSocket connection.
        symbol: Trading pair (e.g., "BTC-USDT" or "BTC/USDT").

    Message format (JSON):
    ```json
    {
        "type": "ticker",
        "channel": "ticker:BTC/USDT",
        "data": {
            "symbol": "BTC/USDT",
            "last": "42000.50",
            "bid": "42000.00",
            "ask": "42001.00",
            "volume_24h": "1234.56",
            "timestamp": "2024-01-26T12:00:00Z"
        },
        "timestamp": "2024-01-26T12:00:00Z"
    }
    ```
    """
    stream_manager = get_stream_manager()
    normalized_symbol = symbol.replace("-", "/")
    redis_channel = f"{stream_manager.REDIS_CHANNEL_PREFIX}ticker:{normalized_symbol}"

    # Subscribe to ticker feed
    await stream_manager.subscribe_ticker(symbol)

    try:
        connection = WebSocketConnection(websocket, redis_channel, stream_manager)
        await connection.run()
    finally:
        # Optionally unsubscribe when no clients remain
        # For now, keep subscription active for other potential clients
        pass


@router.websocket("/candles/{symbol}")
async def websocket_candles(
    websocket: WebSocket,
    symbol: str,
    timeframe: str = Query(
        default="1m", description="Candle timeframe (1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w)"
    ),
) -> None:
    """WebSocket endpoint for real-time candlestick data.

    Args:
        websocket: WebSocket connection.
        symbol: Trading pair (e.g., "BTC-USDT").
        timeframe: Candle timeframe.

    Message format (JSON):
    ```json
    {
        "type": "candle",
        "channel": "candle:BTC/USDT:1m",
        "data": {
            "symbol": "BTC/USDT",
            "timeframe": "1m",
            "timestamp": "2024-01-26T12:00:00Z",
            "open": "42000.00",
            "high": "42100.00",
            "low": "41900.00",
            "close": "42050.00",
            "volume": "123.45",
            "is_closed": false
        },
        "timestamp": "2024-01-26T12:00:00Z"
    }
    ```
    """
    stream_manager = get_stream_manager()
    normalized_symbol = symbol.replace("-", "/")
    redis_channel = f"{stream_manager.REDIS_CHANNEL_PREFIX}candle:{normalized_symbol}:{timeframe}"

    # Subscribe to candle feed
    await stream_manager.subscribe_candles(symbol, timeframe)

    try:
        connection = WebSocketConnection(websocket, redis_channel, stream_manager)
        await connection.run()
    finally:
        pass


@router.websocket("/trades/{symbol}")
async def websocket_trades(
    websocket: WebSocket,
    symbol: str,
) -> None:
    """WebSocket endpoint for real-time trade data.

    Args:
        websocket: WebSocket connection.
        symbol: Trading pair (e.g., "BTC-USDT").

    Message format (JSON):
    ```json
    {
        "type": "trade",
        "channel": "trade:BTC/USDT",
        "data": {
            "symbol": "BTC/USDT",
            "trade_id": "123456789",
            "price": "42000.50",
            "size": "0.5",
            "side": "buy",
            "timestamp": "2024-01-26T12:00:00Z"
        },
        "timestamp": "2024-01-26T12:00:00Z"
    }
    ```
    """
    stream_manager = get_stream_manager()
    normalized_symbol = symbol.replace("-", "/")
    redis_channel = f"{stream_manager.REDIS_CHANNEL_PREFIX}trade:{normalized_symbol}"

    # Subscribe to trade feed
    await stream_manager.subscribe_trades(symbol)

    try:
        connection = WebSocketConnection(websocket, redis_channel, stream_manager)
        await connection.run()
    finally:
        pass


@router.websocket("/orderbook/{symbol}")
async def websocket_orderbook(
    websocket: WebSocket,
    symbol: str,
) -> None:
    """WebSocket endpoint for real-time order book data (5-level depth).

    Args:
        websocket: WebSocket connection.
        symbol: Trading pair (e.g., "BTC-USDT").

    Message format (JSON):
    ```json
    {
        "type": "orderbook",
        "channel": "orderbook:BTC/USDT",
        "data": {
            "symbol": "BTC/USDT",
            "bids": [
                {"price": "42000.00", "size": "1.5", "num_orders": 3},
                {"price": "41999.00", "size": "2.0", "num_orders": 5}
            ],
            "asks": [
                {"price": "42001.00", "size": "1.0", "num_orders": 2},
                {"price": "42002.00", "size": "0.8", "num_orders": 1}
            ],
            "timestamp": "2024-01-26T12:00:00Z"
        },
        "timestamp": "2024-01-26T12:00:00Z"
    }
    ```
    """
    stream_manager = get_stream_manager()
    normalized_symbol = symbol.replace("-", "/")
    redis_channel = f"{stream_manager.REDIS_CHANNEL_PREFIX}orderbook:{normalized_symbol}"

    # Subscribe to orderbook feed
    await stream_manager.subscribe_orderbook(symbol)

    try:
        connection = WebSocketConnection(websocket, redis_channel, stream_manager)
        await connection.run()
    finally:
        pass


# ==================== Private Channel Endpoints ====================


@router.websocket("/orders")
async def websocket_orders(
    websocket: WebSocket,
    inst_type: str = Query(
        default="SPOT", description="Instrument type (SPOT, MARGIN, SWAP, FUTURES, OPTION)"
    ),
) -> None:
    """WebSocket endpoint for real-time order updates (private channel).

    Requires OKX API credentials to be configured.

    Args:
        websocket: WebSocket connection.
        inst_type: Instrument type to filter orders.

    Message format (JSON):
    ```json
    {
        "type": "order_update",
        "channel": "orders",
        "data": {
            "order_id": "12345678",
            "client_order_id": "my-order-1",
            "symbol": "BTC/USDT",
            "side": "buy",
            "order_type": "limit",
            "status": "filled",
            "price": "42000.00",
            "size": "0.5",
            "filled_size": "0.5",
            "avg_price": "42000.00",
            "fee": "0.00021",
            "fee_currency": "BTC",
            "timestamp": "2024-01-26T12:00:00Z"
        },
        "timestamp": "2024-01-26T12:00:00Z"
    }
    ```
    """
    stream_manager = get_stream_manager()
    redis_channel = f"{stream_manager.REDIS_CHANNEL_PREFIX}orders"

    try:
        # Subscribe to orders feed (will start private client if needed)
        await stream_manager.subscribe_orders(inst_type)
    except RuntimeError as e:
        await websocket.accept()
        await websocket.send_json(
            {
                "error": str(e),
                "message": "OKX API credentials not configured",
            }
        )
        await websocket.close(code=4001)
        return

    try:
        connection = WebSocketConnection(websocket, redis_channel, stream_manager)
        await connection.run()
    finally:
        pass


@router.websocket("/account")
async def websocket_account(
    websocket: WebSocket,
) -> None:
    """WebSocket endpoint for real-time account balance updates (private channel).

    Requires OKX API credentials to be configured.

    Args:
        websocket: WebSocket connection.

    Message format (JSON):
    ```json
    {
        "type": "account_update",
        "channel": "account",
        "data": {
            "balances": [
                {
                    "currency": "USDT",
                    "available": "10000.00",
                    "frozen": "500.00"
                },
                {
                    "currency": "BTC",
                    "available": "1.5",
                    "frozen": "0.1"
                }
            ],
            "timestamp": "2024-01-26T12:00:00Z"
        },
        "timestamp": "2024-01-26T12:00:00Z"
    }
    ```
    """
    stream_manager = get_stream_manager()
    redis_channel = f"{stream_manager.REDIS_CHANNEL_PREFIX}account"

    try:
        # Subscribe to account feed (will start private client if needed)
        await stream_manager.subscribe_account()
    except RuntimeError as e:
        await websocket.accept()
        await websocket.send_json(
            {
                "error": str(e),
                "message": "OKX API credentials not configured",
            }
        )
        await websocket.close(code=4001)
        return

    try:
        connection = WebSocketConnection(websocket, redis_channel, stream_manager)
        await connection.run()
    finally:
        pass
