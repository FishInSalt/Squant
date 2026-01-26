"""FastAPI WebSocket endpoints for real-time data streaming."""

import asyncio
import contextlib
import logging
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from squant.infra.redis import get_redis_context
from squant.websocket.manager import StreamManager, get_stream_manager

logger = logging.getLogger(__name__)

router = APIRouter()


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
                done, pending = await asyncio.wait(
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
    timeframe: str = Query(default="1m", description="Candle timeframe (1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w)"),
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
    inst_type: str = Query(default="SPOT", description="Instrument type (SPOT, MARGIN, SWAP, FUTURES, OPTION)"),
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
        await websocket.send_json({
            "error": str(e),
            "message": "OKX API credentials not configured",
        })
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
        await websocket.send_json({
            "error": str(e),
            "message": "OKX API credentials not configured",
        })
        await websocket.close(code=4001)
        return

    try:
        connection = WebSocketConnection(websocket, redis_channel, stream_manager)
        await connection.run()
    finally:
        pass
