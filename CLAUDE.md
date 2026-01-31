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
├── config.py            # Nested Pydantic Settings (loaded from .env)
├── api/                 # REST API routes (presentation layer)
│   ├── deps.py          # Dependency injection (sessions, exchange clients)
│   └── v1/              # Versioned endpoints
│       ├── market.py, strategies.py, backtest.py
│       ├── paper_trading.py, live_trading.py
│       ├── orders.py, account.py, risk.py
│       └── circuit_breaker.py, exchange_accounts.py
├── websocket/           # WebSocket handlers for real-time data
│   ├── manager.py       # Stream manager with auto-reconnect
│   └── handlers.py      # Message routing
├── services/            # Business logic layer
│   ├── backtest.py, paper_trading.py, live_trading.py
│   ├── order.py, account.py, risk.py
│   ├── circuit_breaker.py  # Trading halt on risk events
│   ├── background.py    # Background task manager
│   └── data_loader.py   # Historical data loading
├── engine/              # Trading engines
│   ├── backtest/        # Backtesting with order matching simulation
│   ├── paper/           # Real-time paper trading (in-memory)
│   ├── live/            # Live trading with real orders
│   ├── risk/            # Risk management engine
│   └── sandbox.py       # RestrictedPython strategy sandbox
├── models/              # SQLAlchemy ORM models
├── schemas/             # Pydantic request/response schemas
└── infra/               # Infrastructure layer
    ├── database.py      # AsyncPG + SQLAlchemy async session
    ├── redis.py         # Redis client with pub/sub
    ├── repository.py    # Generic repository pattern
    └── exchange/        # Exchange adapters
        ├── base.py      # Abstract adapter interface
        ├── types.py     # Shared types (Ticker, Order, etc.)
        ├── ccxt/        # CCXT multi-exchange (REST + WebSocket)
        ├── okx/         # Native OKX implementation
        └── binance/     # Native Binance implementation
```

### Key Patterns

- **Async-first**: All I/O operations use `async`/`await` with asyncpg and aioredis
- **Dependency injection**: FastAPI `Depends()` for database sessions and exchange clients
- **Repository pattern**: Generic CRUD operations in `infra/repository.py`
- **Process isolation**: Strategy execution runs in separate processes via `multiprocessing`
- **Strategy sandbox**: RestrictedPython for safe user strategy execution
- **Circuit breaker**: Automatic trading halt on risk events (max loss, position limits)
- **Background tasks**: Periodic persistence, health checks, session cleanup

### Trading Engines

1. **Backtest Engine** (`engine/backtest/`): Simulates historical trading with realistic order matching
2. **Paper Trading Engine** (`engine/paper/`): Real-time simulation with in-memory order book
3. **Live Trading Engine** (`engine/live/`): Executes real orders through exchange APIs

### Exchange Abstraction

Two adapter implementations available:

1. **CCXT Provider** (`infra/exchange/ccxt/`): Multi-exchange support via CCXT library
   - REST adapter for trading operations
   - WebSocket streaming for real-time data (tickers, orderbook, trades)
   - Supports OKX, Binance, Bybit with unified interface

2. **Native Adapters** (`infra/exchange/okx/`, `binance/`): Direct API implementations
   - Lower latency, exchange-specific optimizations
   - Full WebSocket support with auto-reconnect

Configurable via `DEFAULT_EXCHANGE` (okx/binance/bybit) and `USE_CCXT_PROVIDER` (true/false) settings.

### Data Flow

- Real-time market data: WebSocket → Redis pub/sub → Frontend WebSocket
- Order execution: Frontend → REST API → Service → Exchange Adapter → Exchange
- Strategy signals: Strategy Process → Redis → Order Service

## Configuration

Environment variables are loaded from `.env` via Pydantic Settings with nested configuration classes:

```python
settings = get_settings()
settings.database.url      # DatabaseSettings
settings.redis.url         # RedisSettings
settings.security.secret_key  # SecuritySettings
settings.exchange.default_exchange  # ExchangeSettings
# ... plus LoggingSettings, StrategySettings, RiskSettings, etc.
```

Key environment variables:

- `DATABASE_URL`: PostgreSQL connection string (must include `+asyncpg`)
- `REDIS_URL`: Redis connection string
- `SECRET_KEY`: Application secret (min 32 chars)
- `ENCRYPTION_KEY`: For encrypting stored API keys
- `DEFAULT_EXCHANGE`: okx, binance, or bybit
- `USE_CCXT_PROVIDER`: true (CCXT) or false (native adapter)
- `*_API_KEY`, `*_API_SECRET`, `*_PASSPHRASE`: Exchange credentials

## Testing

Squant has comprehensive test coverage across unit, integration, and E2E layers.

**Test Statistics** (as of 2026-01-31):
- **Total tests**: 1,537
- **Overall coverage**: 77%
- **All tests passing**: ✅

### Test Structure

```
tests/
├── unit/              # Fast, isolated tests with mocks
│   ├── api/           # API endpoint tests
│   ├── engine/        # Trading engine tests
│   ├── infra/         # Infrastructure tests
│   ├── models/        # Model tests
│   ├── schemas/       # Schema validation tests
│   └── services/      # Business logic tests
├── integration/       # Tests with real DB/Redis
│   ├── api/           # API integration tests
│   ├── conftest.py    # Shared fixtures
│   └── services/      # Service integration tests
├── e2e/               # End-to-end workflow tests
│   ├── conftest.py    # E2E fixtures
│   └── seed_data.py   # Test data seeding
└── templates/         # Test templates for new tests

```

### Running Tests

```bash
# Unit tests (fast, no external dependencies)
uv run pytest tests/unit -v

# Integration tests (requires Docker)
docker compose -f docker-compose.test.yml up -d postgres redis
uv run pytest tests/integration -v

# E2E tests (full stack)
docker compose -f docker-compose.test.yml --profile e2e up -d
uv run pytest tests/e2e -v

# All tests
uv run pytest -v

# With coverage
uv run pytest --cov=src/squant --cov-report=html
```

### Test Markers

- `@pytest.mark.unit`: Unit tests (default)
- `@pytest.mark.integration`: Integration tests requiring databases
- `@pytest.mark.e2e`: End-to-end tests requiring full stack
- `@pytest.mark.okx_private`: Tests requiring OKX credentials
- `@pytest.mark.asyncio`: Async tests (pytest-asyncio mode = "auto")

### Important Testing Notes

**Async Testing with FastAPI**:
- Use `httpx.AsyncClient` (not `TestClient`) for async endpoint tests
- Override async generator dependencies correctly:
  ```python
  async def override_dep() -> AsyncGenerator[Mock, None]:
      yield mock_object
  app.dependency_overrides[get_dep] = override_dep
  ```
- All test methods must be `async def` with `@pytest.mark.asyncio`

**Dangerous Operations to Avoid**:
1. ❌ Never mock `asyncio.sleep()` in code with `while` loops
2. ❌ Don't test methods with infinite `while running` loops
3. ❌ Don't call WebSocket `run()` methods in unit tests
4. ❌ Don't start background async tasks in unit tests

See `dev-docs/technical/testing/TROUBLESHOOTING.md` for details on system crashes caused by these operations.

### Test Documentation

Comprehensive testing guides available in `dev-docs/technical/testing/`:
- **TESTING_GUIDE.md** - General testing guide and best practices
- **INTEGRATION_TESTING.md** - Integration testing with Docker
- **E2E_TESTING.md** - End-to-end testing guide
- **TROUBLESHOOTING.md** - Common issues and solutions
- **CI_SETUP.md** - CI/CD workflow configuration

## Database

- PostgreSQL 16 with TimescaleDB extension for time-series data (candles, equity curves)
- Alembic for migrations in `alembic/` directory
- Models use SQLAlchemy 2.0 async patterns

## Documentation

Detailed technical documentation is available in `dev-docs/`:

- `dev-docs/requirements/` - PRD, user stories, acceptance criteria
- `dev-docs/technical/architecture/` - System architecture, module design, data flows
- `dev-docs/technical/strategy-engine/` - Strategy lifecycle, sandbox, indicators
- `dev-docs/technical/api/` - REST and WebSocket API specifications
- `dev-docs/technical/testing/` - Comprehensive testing guides (unit, integration, E2E, CI/CD)
- `dev-docs/technical/deployment/` - Docker, environment, monitoring
