# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Squant is a personal quantitative trading system for cryptocurrency. It supports backtesting, paper trading, and live trading with multiple exchanges (OKX, Binance, Bybit) through the CCXT library.

## Development Commands

### Backend (Python with uv)

```bash
# Start dev dependencies (PostgreSQL + TimescaleDB, Redis)
./scripts/dev.sh start

# Run database migrations
./scripts/dev.sh migrate

# Start backend server with hot reload (foreground)
./scripts/dev.sh backend

# Or run as background service with management commands
./scripts/backend.sh start     # Start in background
./scripts/backend.sh stop      # Stop server
./scripts/backend.sh restart   # Restart server
./scripts/backend.sh status    # Check if running
./scripts/backend.sh logs      # Tail log file

# Run tests
uv run pytest -v

# Run a single test file
uv run pytest tests/unit/test_example.py -v

# Run tests matching a pattern
uv run pytest -k "test_name_pattern" -v

# Lint and type check
./scripts/dev.sh lint

# Format code
./scripts/dev.sh format
```

### Frontend (Vue 3 + TypeScript)

```bash
cd frontend
pnpm install
pnpm dev          # Development server at http://localhost:5173
pnpm build        # Production build
pnpm lint         # ESLint
```

### Docker Development

```bash
# Start only databases
docker compose -f docker-compose.dev.yml up -d postgres redis

# Full stack (includes backend and frontend)
docker compose -f docker-compose.dev.yml --profile full up -d
```

**Port mapping in dev**: PostgreSQL on 5433, Redis on 6380 (non-standard to avoid conflicts).

## Architecture

### Backend Layer Structure

```
src/squant/
├── main.py              # FastAPI entry point with lifespan management
├── config.py            # Pydantic Settings (loaded from .env)
├── api/                 # REST API routes (presentation layer)
│   └── v1/              # Versioned endpoints
├── websocket/           # WebSocket handlers for real-time data
├── services/            # Business logic layer
├── engine/              # Trading engines
│   ├── backtest/        # Backtesting engine with matching simulation
│   ├── paper/           # Paper trading engine (in-memory)
│   ├── live/            # Live trading engine (real orders)
│   └── risk/            # Risk management and circuit breaker
├── models/              # SQLAlchemy ORM models
├── schemas/             # Pydantic request/response schemas
└── infra/               # Infrastructure layer
    ├── database.py      # AsyncPG + SQLAlchemy async session
    ├── redis.py         # Redis client
    ├── repository.py    # Generic repository pattern
    └── exchange/        # Exchange adapters
        ├── ccxt/        # CCXT-based multi-exchange adapter
        └── okx/         # Native OKX implementation (legacy)
```

### Key Patterns

- **Async-first**: All I/O operations use `async`/`await` with asyncpg and aioredis
- **Dependency injection**: FastAPI `Depends()` for database sessions and exchange clients
- **Repository pattern**: Generic CRUD operations in `infra/repository.py`
- **Process isolation**: Strategy execution runs in separate processes via `multiprocessing`
- **Strategy sandbox**: RestrictedPython for safe user strategy execution

### Trading Engines

1. **Backtest Engine** (`engine/backtest/`): Simulates historical trading with realistic order matching
2. **Paper Trading Engine** (`engine/paper/`): Real-time simulation with in-memory order book
3. **Live Trading Engine** (`engine/live/`): Executes real orders through exchange APIs

### Exchange Abstraction

CCXT provider (`infra/exchange/ccxt/`) wraps multiple exchanges with unified interface:
- REST adapter for trading operations
- WebSocket streaming for real-time data (tickers, orderbook, trades)
- Configurable via `DEFAULT_EXCHANGE` and `USE_CCXT_PROVIDER` settings

### Data Flow

- Real-time market data: WebSocket → Redis pub/sub → Frontend WebSocket
- Order execution: Frontend → REST API → Service → Exchange Adapter → Exchange
- Strategy signals: Strategy Process → Redis → Order Service

## Configuration

Environment variables are loaded from `.env` via Pydantic Settings. Key variables:

- `DATABASE_URL`: PostgreSQL connection string (must include `+asyncpg`)
- `REDIS_URL`: Redis connection string
- `SECRET_KEY`: Application secret (min 32 chars)
- `ENCRYPTION_KEY`: For encrypting stored API keys
- `DEFAULT_EXCHANGE`: okx, binance, or bybit
- `*_API_KEY`, `*_API_SECRET`: Exchange credentials

## Testing

- Integration tests may require running databases (marked with `@pytest.mark.integration`)
- OKX-specific tests requiring credentials are marked with `@pytest.mark.okx_private`
- pytest-asyncio is configured with `asyncio_mode = "auto"`

## Database

- PostgreSQL 16 with TimescaleDB extension for time-series data (candles, equity curves)
- Alembic for migrations in `alembic/` directory
- Models use SQLAlchemy 2.0 async patterns
