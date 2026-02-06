# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Squant is a personal quantitative trading system for cryptocurrency. It supports backtesting, paper trading, and live trading with multiple exchanges (OKX, Binance, Bybit) through the CCXT library.

## Development Commands

### Backend (Python 3.12+ with uv)

```bash
# Start dev dependencies (PostgreSQL + TimescaleDB, Redis)
./scripts/dev.sh start

# Run database migrations
./scripts/dev.sh migrate          # or: uv run alembic upgrade head

# Create a new Alembic migration
uv run alembic revision --autogenerate -m "description of changes"

# Start backend server with hot reload (foreground)
./scripts/dev.sh backend          # runs uvicorn on port 8000

# Background service management
./scripts/backend.sh start|stop|restart|status|logs
./scripts/frontend.sh start|stop|restart|status|logs|build

# Run all tests (pytest addopts already includes --cov)
uv run pytest -v

# Run specific tests
uv run pytest tests/unit -v
uv run pytest tests/unit/test_example.py -v
uv run pytest -k "test_name_pattern" -v

# Run tests without coverage (faster for iterating)
uv run pytest tests/unit -v --no-cov

# Run tests in parallel (pytest-xdist)
uv run pytest tests/unit -v --no-cov -n auto

# Integration tests (requires Docker services on ports 5433/6380)
docker compose -f docker-compose.dev.yml up -d postgres redis
uv run pytest tests/integration -v

# E2E tests (full stack)
docker compose -f docker-compose.test.yml --profile e2e up -d
uv run pytest tests/e2e -v

# Test environment management (integration/e2e)
./scripts/test-env.sh start|stop|status|reset-db|clear-redis|psql|redis-cli

# Lint (ruff check + ruff format --check + mypy)
./scripts/dev.sh lint

# Format (ruff format + ruff check --fix)
./scripts/dev.sh format
```

### Frontend (Vue 3 + TypeScript)

```bash
cd frontend
pnpm install
pnpm dev          # Development server at http://localhost:5175
pnpm build        # Production build (vue-tsc + vite build)
pnpm lint         # ESLint with --fix
```

Frontend stack: Vue 3, Vue Router, Pinia, Element Plus, ECharts/vue-echarts, KlineCharts, Axios. Uses `unplugin-auto-import` (Vue/Router/Pinia) and `unplugin-vue-components` (Element Plus auto-resolve) so most imports are auto-generated. Views organized by domain: `views/{market,trading,strategy,risk,account,order,system}/`.

### Docker Development

```bash
docker compose -f docker-compose.dev.yml up -d postgres redis   # databases only
docker compose -f docker-compose.dev.yml --profile full up -d    # full stack
```

**Dev ports**: PostgreSQL on 5433, Redis on 6380 (non-standard to avoid conflicts).

**Environment setup**: Copy `.env.example` to `.env` and fill in values. In DevContainer, `post-create.sh` generates `.env` automatically.

### VS Code Dev Container

The project supports development via VS Code Dev Container (config in `.devcontainer/`). On container start, `post-create.sh` auto-runs `uv sync`, `pnpm install`, DB migrations, and `.env` generation — ready to use out of the box.

Key differences from local development:

- **DB/Redis already running** — postgres and redis run as sibling containers with health checks, no need for `./scripts/dev.sh start`
- **Connection addresses use container service names** — `postgres:5432` / `redis:6379`, not `localhost:5433` / `localhost:6380`
- **`.venv` and `frontend/node_modules` on named volumes** — not on host filesystem, volumes persist across container rebuilds
- **Python interpreter path** — `/workspaces/Squant/.venv/bin/python`

## Architecture

### Backend Layer Structure

```
src/squant/
├── main.py              # FastAPI entry point with lifespan (init DB, Redis, WebSocket, background tasks)
├── config.py            # Nested Pydantic Settings (loaded from .env)
├── api/                 # REST API routes (presentation layer)
│   ├── deps.py          # DI: DbSession, DbSessionReadonly, RedisClient, Exchange
│   ├── middleware.py     # Rate limiting middleware
│   └── v1/              # Versioned endpoints
├── websocket/           # WebSocket handlers + stream manager for real-time market data
├── services/            # Business logic layer (one service per domain)
├── engine/              # Trading engines
│   ├── sandbox.py       # RestrictedPython strategy sandbox
│   ├── resource_limits.py
│   ├── paper/           # Paper trading: manager.py (session lifecycle) + engine.py (execution)
│   └── live/            # Live trading: manager.py + engine.py + order_sync.py
├── models/              # SQLAlchemy ORM models (inherit Base, UUIDMixin, TimestampMixin)
├── schemas/             # Pydantic request/response schemas
└── infra/               # Infrastructure layer
    ├── database.py      # AsyncPG + SQLAlchemy async session
    ├── redis.py         # Redis client with pub/sub
    ├── repository.py    # Generic CRUD: BaseRepository[ModelT: Base] (Python 3.12 generics)
    └── exchange/        # Exchange adapters
        ├── base.py      # Abstract base + types + exceptions + retry
        └── ccxt/        # CCXT unified adapter: rest_adapter.py, provider.py, transformer.py
```

### Key Patterns

- **Async-first**: All I/O uses `async`/`await` with asyncpg and aioredis
- **Dependency injection**: FastAPI `Depends()` with type aliases in `api/deps.py`:
  - `DbSession`, `DbSessionReadonly` — async SQLAlchemy sessions
  - `RedisClient` — Redis connection
  - `Exchange` — CCXT adapter (cached in `_exchange_cache` with `asyncio.Lock`, auto-connected with `load_markets()`)
  - `OKXExchange` — legacy OKX-specific adapter (async generator with `yield`)
- **Repository pattern**: `BaseRepository[ModelT: Base]` uses Python 3.12 generic syntax; provides `get`, `get_by`, `list`, `create`, `update`, `delete`, `count`
- **Model mixins**: `UUIDMixin` (UUID string PK), `TimestampMixin` (created_at/updated_at with timezone)
- **Manager + Engine pattern**: Both paper and live trading use a `manager.py` (session lifecycle, singleton via `get_*_session_manager()`) and `engine.py` (execution logic)
- **Process isolation**: Strategy execution in separate processes via `multiprocessing`
- **Strategy sandbox**: RestrictedPython blocks os/sys/subprocess/network/pickle/threading modules
- **Circuit breaker**: Automatic trading halt on risk events (max loss, position limits)
- **Exchange abstraction**: CCXT unified adapter (default) or native OKX adapter; configured via `DEFAULT_EXCHANGE` + `USE_CCXT_PROVIDER`

### Data Flow

- Real-time market data: WebSocket → Redis pub/sub → Frontend WebSocket
- Order execution: Frontend → REST API → Service → Exchange Adapter → Exchange
- Strategy signals: Strategy Process → Redis → Order Service

### Application Lifespan

`main.py` lifespan manages startup/shutdown order:
1. **Startup**: init DB → init Redis → init stream manager (with retry fallback) → recover orphaned trading sessions → start background tasks (persist + health check)
2. **Shutdown**: stop background tasks → stop paper sessions → stop live sessions → close stream manager → clear exchange cache → close Redis → close DB

### Configuration

Settings loaded from `.env` via nested Pydantic Settings classes in `config.py`. Each sub-settings class has its own `env_prefix` (e.g., `DATABASE_`, `REDIS_`, `OKX_`, `STRATEGY_`, `RISK_`, `PAPER_`, `CIRCUIT_BREAKER_`). Access via `get_settings()` which is `@lru_cache`d. See `.env.example` for all available settings.

Nested access: `settings.database.url`, `settings.okx.api_key`, `settings.risk.max_position_ratio`, etc. Flat aliases exist for backward compatibility (e.g., `settings.okx_api_key` → `settings.okx.api_key`). Sensitive fields (`url`, `api_key`, `secret_key`, etc.) use `SecretStr` — call `.get_secret_value()` to access the actual value.

### Database

- PostgreSQL 16 + TimescaleDB for time-series data (candles, equity curves)
- Alembic migrations in `alembic/` — run `uv run alembic upgrade head`
- SQLAlchemy 2.0 async patterns; connection string must include `+asyncpg`

### API Response Convention

Exchange-related exception handlers return a uniform shape: `{"code": <http_status>, "message": <str>, "data": null}`. Exchange errors map to: connection → 503, auth → 401, rate limit → 429 (with `Retry-After` header), other API errors → 502.

## Code Style

- **Ruff**: line-length 100, target Python 3.12. Rules: E, W, F, I, B, C4, UP, SIM
- **Ruff ignored**: E501, B008 (FastAPI default args), B904, SIM117, SIM102, SIM105, B027, B007, B017
- **Ruff exclude**: `tests/templates/` is excluded from linting
- **mypy**: strict mode with pydantic plugin; `RestrictedPython` and `ccxt` have `ignore_missing_imports`
- **isort**: first-party = `squant`

## Testing

### Test Markers

- `@pytest.mark.integration`: requires Docker databases (ports 5433/6380 or container names)
- `@pytest.mark.e2e`: requires full stack (registered in `tests/e2e/conftest.py`)
- `@pytest.mark.okx_private`: requires OKX API credentials
- `asyncio_mode = "auto"`: no need for explicit `@pytest.mark.asyncio` on every test

### Test Structure

Tests mirror the source layout: `tests/unit/{api/v1, services, engine/{backtest,paper,live,risk}, infra/exchange, models, schemas, websocket, utils}`, `tests/integration/{api, database, services, websocket}`, `tests/e2e/`. Each subdirectory can have its own `conftest.py` for scoped fixtures.

### Important Testing Rules

**Async Testing with FastAPI**:
- Use `httpx.AsyncClient` (not `TestClient`) for async endpoint tests
- Override async generator dependencies correctly:
  ```python
  async def override_dep() -> AsyncGenerator[Mock, None]:
      yield mock_object
  app.dependency_overrides[get_dep] = override_dep
  ```

**Dangerous Operations — Will Crash Tests**:
1. Never mock `asyncio.sleep()` in code with `while` loops — causes infinite CPU loops and OOM
2. Don't test methods with infinite `while running` loops directly
3. Don't call WebSocket `run()` methods in unit tests
4. Don't start background async tasks in unit tests

See `dev-docs/technical/testing/TROUBLESHOOTING.md` for detailed examples and solutions.

**Test Environment Configuration**:
- `.env.test.ci` — CI environment (localhost:5433/6380)
- `.env.test.local` — DevContainer (container service names: postgres:5432, redis:6379)
- Root `tests/conftest.py` auto-detects integration tests and selectively overrides `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, `ENCRYPTION_KEY`, `APP_ENV` from `.env.test`
- Integration conftest provides two session fixtures: `db_session` (auto-rollback per test) and `clean_db_session` (real commits, clears tables after test)

### CI Pipeline

CI runs on pushes to `main`, `develop`, `cc/*` and PRs to `main`/`develop`. Pipeline: lint → unit tests → integration tests → e2e tests → docker build check. Note: mypy and ruff format checks are `continue-on-error` in CI (non-blocking).

## Documentation

Detailed docs in `dev-docs/`: requirements (PRD, user stories, acceptance criteria) and technical docs (architecture, strategy engine, API specs, testing guides, deployment). See `dev-docs/technical/testing/TROUBLESHOOTING.md` for common test failure patterns.
