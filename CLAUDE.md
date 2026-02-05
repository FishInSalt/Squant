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

# Start backend server with hot reload (foreground)
./scripts/dev.sh backend          # runs uvicorn on port 8000

# Background service management
./scripts/backend.sh start|stop|restart|status|logs

# Run all tests (pytest addopts already includes --cov)
uv run pytest -v

# Run specific tests
uv run pytest tests/unit -v
uv run pytest tests/unit/test_example.py -v
uv run pytest -k "test_name_pattern" -v

# Run tests without coverage (faster for iterating)
uv run pytest tests/unit -v --no-cov

# Integration tests (requires Docker services on ports 5433/6380)
docker compose -f docker-compose.dev.yml up -d postgres redis
uv run pytest tests/integration -v

# E2E tests (full stack)
docker compose -f docker-compose.test.yml --profile e2e up -d
uv run pytest tests/e2e -v

# Lint (ruff check + ruff format --check + mypy)
./scripts/dev.sh lint

# Format (ruff format + ruff check --fix)
./scripts/dev.sh format
```

### Frontend (Vue 3 + TypeScript)

```bash
cd frontend
pnpm install
pnpm dev          # Development server at http://localhost:5173
pnpm build        # Production build (vue-tsc + vite build)
pnpm lint         # ESLint with --fix
```

Frontend stack: Vue 3, Vue Router, Pinia, Element Plus, ECharts/vue-echarts, KlineCharts, Axios. Views organized by domain: `views/{market,trading,strategy,risk,account,order,system}/`.

### Docker Development

```bash
docker compose -f docker-compose.dev.yml up -d postgres redis   # databases only
docker compose -f docker-compose.dev.yml --profile full up -d    # full stack
```

**Dev ports**: PostgreSQL on 5433, Redis on 6380 (non-standard to avoid conflicts).

### VS Code Dev Container

项目支持通过 VS Code Dev Container 进行开发（配置在 `.devcontainer/`）。容器启动后 `post-create.sh` 自动完成 `uv sync`、`pnpm install`、DB 迁移和 `.env` 生成，环境开箱即用。

与本地开发的关键差异：

- **数据库/Redis 已自动启动** — postgres 和 redis 作为 sibling 容器运行并有 health check，无需手动 `./scripts/dev.sh start`
- **连接地址使用容器服务名** — `postgres:5432` / `redis:6379`，而非宿主机的 `localhost:5433` / `localhost:6380`
- **`.venv` 和 `frontend/node_modules` 在 named volume 上** — 不在宿主机文件系统中，容器重建后 volume 会保留
- **Python 解释器路径** — `/workspaces/Squant/.venv/bin/python`

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
  - `Exchange` — CCXT adapter (cached, auto-connected with `load_markets()`)
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

Settings loaded from `.env` via nested Pydantic Settings classes. Each sub-settings class has its own `env_prefix`:

| Setting group | Prefix | Access |
|---|---|---|
| `DatabaseSettings` | `DATABASE_` | `settings.database.url` |
| `RedisSettings` | `REDIS_` | `settings.redis.url` |
| `LoggingSettings` | `LOG_` | `settings.logging.level` |
| `SecuritySettings` | *(none)* | `settings.security.secret_key` |
| `OKXSettings` | `OKX_` | `settings.okx.api_key` |
| `BinanceSettings` | `BINANCE_` | `settings.binance.api_key` |
| `BybitSettings` | `BYBIT_` | `settings.bybit.api_key` |
| `ExchangeStreamSettings` | *(none)* | `settings.exchange.default_exchange` |
| `StrategySettings` | `STRATEGY_` | `settings.strategy.max_processes` |
| `RiskSettings` | `RISK_` | `settings.risk.max_position_ratio` |
| `PaperTradingSettings` | `PAPER_` | `settings.paper.max_equity_curve_size` |
| `CircuitBreakerSettings` | `CIRCUIT_BREAKER_` | `settings.circuit_breaker.cooldown_minutes` |

`get_settings()` is `@lru_cache`d. Flat aliases exist for backward compatibility (e.g., `settings.okx_api_key` → `settings.okx.api_key`). Nested settings use `@cached_property` to avoid re-reading `.env` on each access.

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

- `@pytest.mark.integration`: requires Docker databases
- `@pytest.mark.e2e`: requires full stack
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

### CI Pipeline

CI runs on pushes to `main`, `develop`, `cc/*` and PRs to `main`/`develop`. Pipeline: lint → unit tests → integration tests → e2e tests → docker build check. Note: mypy and ruff format checks are `continue-on-error` in CI (non-blocking).

## Documentation

Detailed docs in `dev-docs/`:
- `requirements/` — PRD, user stories, acceptance criteria
- `technical/architecture/` — system architecture, module design, data flows
- `technical/strategy-engine/` — strategy lifecycle, sandbox, indicators
- `technical/api/` — REST and WebSocket API specs
- `technical/testing/` — testing guides (unit, integration, E2E, CI/CD, troubleshooting)
- `technical/deployment/` — Docker, environment, monitoring
