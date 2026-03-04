"""API router aggregation."""

from fastapi import APIRouter

from squant.api.v1 import (
    account,
    backtest,
    circuit_breaker,
    exchange_accounts,
    health,
    live_trading,
    market,
    notifications,
    orders,
    paper_trading,
    risk,
    risk_triggers,
    strategies,
    system,
    watchlist,
)
from squant.websocket.handlers import router as ws_router

api_router = APIRouter()

# Health check endpoints
api_router.include_router(health.router, tags=["Health"])

# Market data endpoints (ticker, candles)
api_router.include_router(market.router, prefix="/market", tags=["Market"])

# Account endpoints (balance)
api_router.include_router(account.router, prefix="/account", tags=["Account"])

# Exchange account configuration endpoints
api_router.include_router(
    exchange_accounts.router, prefix="/exchange-accounts", tags=["Exchange Accounts"]
)

# Order management endpoints (with persistence)
api_router.include_router(orders.router, prefix="/orders", tags=["Orders"])

# Strategy management endpoints
api_router.include_router(strategies.router, prefix="/strategies", tags=["Strategies"])

# Backtest endpoints
api_router.include_router(backtest.router, prefix="/backtest", tags=["Backtest"])

# Paper trading endpoints
api_router.include_router(paper_trading.router, prefix="/paper", tags=["Paper Trading"])

# Live trading endpoints
api_router.include_router(live_trading.router, prefix="/live", tags=["Live Trading"])

# Risk rule management endpoints
api_router.include_router(risk.router, prefix="/risk-rules", tags=["Risk"])

# Risk trigger audit endpoints
api_router.include_router(risk_triggers.router, prefix="/risk-triggers", tags=["Risk Triggers"])

# Circuit breaker endpoints
api_router.include_router(
    circuit_breaker.router, prefix="/circuit-breaker", tags=["Circuit Breaker"]
)

# Notification endpoints
api_router.include_router(
    notifications.router, prefix="/notifications", tags=["Notifications"]
)

# Watchlist endpoints
api_router.include_router(watchlist.router, prefix="/watchlist", tags=["Watchlist"])

# System management endpoints (data download, etc.)
api_router.include_router(system.router, prefix="/system", tags=["System"])

# WebSocket endpoints for real-time data
api_router.include_router(ws_router, prefix="/ws", tags=["WebSocket"])
