from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1 import accounts, market

app = FastAPI(
    title=settings.app_name,
    description="Quantitative Trading System API",
    version="0.1.0",
    debug=settings.debug
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(accounts.router, prefix=f"{settings.api_v1_prefix}/accounts", tags=["accounts"])
app.include_router(market.router, prefix=f"{settings.api_v1_prefix}/market", tags=["market"])


@app.get("/")
async def root():
    return {"message": "Squant API", "version": "0.1.0"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
