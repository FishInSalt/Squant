"""API router aggregation."""

from fastapi import APIRouter

from squant.api.v1 import exchange, health

api_router = APIRouter()

# Health check endpoints
api_router.include_router(health.router, tags=["Health"])

# Exchange endpoints
api_router.include_router(exchange.router, prefix="/exchange", tags=["Exchange"])

# TODO: Include other routers
# api_router.include_router(strategy.router, prefix="/strategies", tags=["Strategy"])
# api_router.include_router(risk.router, prefix="/risk", tags=["Risk"])
# api_router.include_router(system.router, prefix="/system", tags=["System"])
