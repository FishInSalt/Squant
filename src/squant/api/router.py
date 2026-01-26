"""API router aggregation."""

from fastapi import APIRouter

from squant.api.v1 import account, health, market, orders
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

# WebSocket endpoints for real-time data
api_router.include_router(ws_router, prefix="/ws", tags=["WebSocket"])
