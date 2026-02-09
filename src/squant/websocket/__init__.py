"""WebSocket module for real-time data streaming."""

from squant.websocket.handlers import router as ws_router
from squant.websocket.manager import (
    StreamManager,
    close_stream_manager,
    get_stream_manager,
    init_stream_manager,
)

__all__ = [
    "StreamManager",
    "get_stream_manager",
    "init_stream_manager",
    "close_stream_manager",
    "ws_router",
]
