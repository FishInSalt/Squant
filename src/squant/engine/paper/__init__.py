"""Paper trading engine module.

Provides real-time simulated trading using WebSocket market data.
"""

from squant.engine.paper.engine import PaperTradingEngine
from squant.engine.paper.manager import (
    SessionManager,
    get_session_manager,
)

__all__ = [
    "PaperTradingEngine",
    "SessionManager",
    "get_session_manager",
]
