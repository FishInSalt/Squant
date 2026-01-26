"""API router aggregation."""

from fastapi import APIRouter

from squant.api.v1 import (
    account,
    backtest,
    health,
    market,
    orders,
    paper_trading,
    risk,
    strategies,
)
from squant.websocket.handlers import router as ws_router

api_router = APIRouter()

# Health check endpoints
api_router.include_router(health.router, tags=["Health"])

# Market data endpoints (ticker, candles)
api_router.include_router(market.router, prefix="/market", tags=["Market"])

# Account endpoints (balance)
api_router.include_router(account.router, prefix="/account", tags=["Account"])

# Order management endpoints (with persistence)
api_router.include_router(orders.router, prefix="/orders", tags=["Orders"])

# Strategy management endpoints
api_router.include_router(strategies.router, prefix="/strategies", tags=["Strategies"])

# Backtest endpoints
api_router.include_router(backtest.router, prefix="/backtest", tags=["Backtest"])

# Paper trading endpoints
api_router.include_router(paper_trading.router, prefix="/paper", tags=["Paper Trading"])

# Risk rule management endpoints
api_router.include_router(risk.router, prefix="/risk-rules", tags=["Risk"])

# WebSocket endpoints for real-time data
api_router.include_router(ws_router, prefix="/ws", tags=["WebSocket"])
