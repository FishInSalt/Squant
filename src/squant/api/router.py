"""API router aggregation."""

from fastapi import APIRouter

from squant.api.v1 import health

api_router = APIRouter()

# Health check endpoints
api_router.include_router(health.router, tags=["Health"])

# TODO: Include other routers
# api_router.include_router(market.router, prefix="/market", tags=["Market"])
# api_router.include_router(strategy.router, prefix="/strategies", tags=["Strategy"])
# api_router.include_router(trading.router, prefix="/trading", tags=["Trading"])
# api_router.include_router(order.router, prefix="/orders", tags=["Order"])
# api_router.include_router(risk.router, prefix="/risk", tags=["Risk"])
# api_router.include_router(account.router, prefix="/accounts", tags=["Account"])
# api_router.include_router(system.router, prefix="/system", tags=["System"])
