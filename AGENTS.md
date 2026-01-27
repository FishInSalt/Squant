# AGENTS.md

Guidelines for agentic coding agents working in this repository.

## Project Overview

Squant is a quantitative trading system:
- **Backend**: Python 3.12+ with FastAPI, SQLAlchemy 2.0+ (async), PostgreSQL, Redis
- **Frontend**: Vue 3 + TypeScript + Vite + Element Plus + Pinia
- **Infrastructure**: Docker Compose (PostgreSQL, Redis)
- **Database Migrations**: Alembic

---

## Build Commands

### Backend (Python)

```bash
cd src/backend

# Run tests
pytest                          # Run all tests
pytest tests/test_file.py       # Run specific test file
pytest -k "test_name"           # Run tests matching pattern
pytest tests/test.py::test_func # Run single test
pytest --cov=app --cov-report=html  # Coverage report

# Lint and format
ruff check .                    # Lint
ruff check . --fix              # Auto-fix
mypy .                          # Type check
black .                         # Format

# Run server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Migrations
alembic revision --autogenerate -m "description"
alembic upgrade head
alembic downgrade -1
```

### Frontend (Vue 3)

```bash
cd src/frontend

# Development & build
npm run dev                     # Dev server
npm run build                   # Production build (includes type check)

# Type checking
npx vue-tsc --noEmit            # Type check only

# Format (prettier available)
npx prettier --write "src/**/*.{ts,vue}"
```

### Infrastructure

```bash
docker compose up -d postgres redis  # Start services
docker compose down                  # Stop
docker compose logs -f postgres redis
```

---

## Code Style Guidelines

### Python Backend

**Imports**: Standard library → third-party → local imports. Separate groups with blank line. Use absolute imports from `app` package. No wildcard imports.

**Formatting**: Black (79 char line), Ruff (lint + import sorting), Mypy (type check with --ignore-missing-imports).

**Naming**: Classes: `PascalCase` (e.g., `ExchangeAccount`), Functions/Variables: `snake_case` (e.g., `get_db`), Constants: `UPPER_SNAKE_CASE`, Private: `_leading_underscore`.

**Database**: Use async API (`create_async_engine`, `AsyncSession`). Models inherit from `Base`. Use explicit `nullable=False`. Timestamps: `server_default=func.now()` for created, `onupdate=func.now()` for updated. Use DI: `async def get_db() -> AsyncSession:`

**Async**: All DB operations async, use `async with` for sessions, route functions `async def`, use `httpx` for async HTTP.

**Config**: Use `pydantic-settings.BaseSettings`, env vars via `.env`, single instance: `from app.core.config import settings`.

**Error Handling**: Use FastAPI exception handlers, return proper HTTP status codes, log with `logger = logging.getLogger(__name__)`.

### Vue 3 Frontend

**TypeScript**: Strict mode enabled. No unused locals/params. Use type annotations explicitly.

**Components**: Use Composition API with `<script setup lang="ts">`. Use `defineProps<Props>()` with interface, `defineEmits<{ event: [] }>()` for type-safe emits. Use `ref` and `computed` from 'vue'.

**Imports**: Named imports: `import { ref } from 'vue'`. Use absolute imports with `@/` alias. Order: Vue/external → internal.

**Styling**: Use `<style scoped lang="scss">`. Element Plus for UI components.

**Naming**: Components: `PascalCase.vue` (e.g., `TickerCard.vue`), Utilities: `kebab-case.ts` or `camelCase.ts`.

### Database Migrations (Alembic)

Use descriptive messages. Generate with `--autogenerate` after model changes. Review migrations before committing. Run `alembic upgrade head` after applying.

---

## Environment Setup

1. `conda activate squant`
2. `docker compose up -d postgres redis`
3. `cd src/backend && alembic upgrade head`
4. Backend: `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
5. Frontend: `npm run dev`

---

## Before Submitting Work

**Backend**: Run `ruff check .`, `mypy .`, and `pytest`. No linting errors, all tests passing.
**Frontend**: Run `npx vue-tsc --noEmit`, ensure build passes.
**Database**: Apply migrations if model changes made.

---

## Notes

- CORS enabled for `http://localhost:5173` and `http://localhost:3000`
- API docs: `http://localhost:8000/docs` (Swagger UI)
- Health check: `GET /health`
- All endpoints under `/api/v1` prefix
