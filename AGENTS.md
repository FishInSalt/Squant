# AGENTS.md

This file contains guidelines for agentic coding agents working in this repository.

## Project Overview

Squant is a quantitative trading system with:
- **Backend**: Python 3.12+ with FastAPI, SQLAlchemy 2.0+ (async), PostgreSQL, Redis
- **Frontend**: Vue 3 + TypeScript + Vite + Element UI + Pinia
- **Infrastructure**: Docker Compose (PostgreSQL, Redis)
- **Database Migrations**: Alembic

---

## Build Commands

### Backend (Python)

```bash
cd src/backend

# Run tests
pytest                          # Run all tests
pytest tests/                   # Run all tests
pytest tests/test_specific.py   # Run specific test file
pytest -k "test_name"           # Run tests matching pattern
pytest tests/test_file.py::test_function  # Run single test

# Run with coverage
pytest --cov=app --cov-report=html

# Lint and type check
ruff check .                    # Lint with ruff
ruff check . --fix              # Auto-fix linting issues
mypy .                          # Type check with mypy
black .                         # Format code with black

# Run server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Database migrations
alembic revision --autogenerate -m "description"
alembic upgrade head
alembic downgrade -1
```

### Frontend (Vue 3 + TypeScript)

```bash
cd src/frontend

# Development server
npm run dev

# Build for production
npm run build

# Type check
npx vue-tsc --noEmit

# Lint (run in project root)
npm run lint  # if available in package.json

# Format with prettier
npx prettier --write "src/**/*.{ts,tsx,vue}"
```

### Infrastructure

```bash
cd /home/li416/Squant_oc

# Start services
docker compose up -d postgres redis

# Stop services
docker compose down

# View logs
docker compose logs -f postgres redis
```

---

## Code Style Guidelines

### Python Backend

#### Imports
- Order: standard library → third-party → local imports
- Separate groups with blank line
- Use absolute imports from `app` package (e.g., `from app.core.config import settings`)
- No wildcard imports (`from x import *`)

#### Formatting
- Use **Black** for formatting (79 char line length default)
- Use **Ruff** for linting with `--extend-select=I` for import sorting
- Use **Mypy** for type checking with `--ignore-missing-imports`

#### Naming Conventions
- **Classes**: `PascalCase` (e.g., `StrategyStatus`, `User`)
- **Functions/Variables**: `snake_case` (e.g., `get_db`, `database_url`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `MAX_DAILY_TRADES`)
- **Private**: `_single_underscore` for internal use

#### Database & SQLAlchemy
- Use async API: `create_async_engine`, `AsyncSession`, `async_sessionmaker`
- Models inherit from `Base` (declarative_base)
- Use `Column` types with explicit constraints (e.g., `nullable=False`)
- Timestamps: `server_default=func.now()` for created, `onupdate=func.now()` for updated
- Use dependency injection for DB sessions: `async def get_db() -> AsyncSession:`

#### Async Patterns
- All DB operations must be async
- Use `async with` for session management
- Route functions use `async def`
- Use `httpx` or `aiohttp` for async HTTP requests

#### Configuration
- Use `pydantic-settings.BaseSettings` for config
- Environment variables via `.env` file
- Single settings instance: `from app.core.config import settings`

#### Error Handling
- Use FastAPI exception handlers
- Return proper HTTP status codes
- Log errors appropriately (not implemented yet)

---

### Vue 3 Frontend

#### TypeScript
- **Strict mode enabled**: `strict: true` in tsconfig
- No unused locals or parameters
- No fallthrough cases in switch
- Use type annotations explicitly

#### Vue Components
- Use **Composition API** with `<script setup lang="ts">`
- Use `defineProps<{ msg: string }>()` for typed props
- Use `ref` and `reactive` from 'vue' for reactivity
- Components in `src/components/` directory

#### Imports
- Use named imports: `import { ref } from 'vue'`
- Use absolute imports where appropriate
- Order: Vue/external → internal → types

#### Styling
- Use `<style scoped>` for component-specific styles
- SCSS available via sass package
- Element UI components for UI library

#### File Naming
- Components: `PascalCase.vue` (e.g., `HelloWorld.vue`)
- Utilities/composables: `kebab-case.ts` or `camelCase.ts`

---

### Database Migrations (Alembic)
- Always use descriptive migration messages
- Generate migrations with `--autogenerate` after model changes
- Review generated migrations before committing
- Run `alembic upgrade head` after applying migrations

---

## Project Structure

```
src/
├── backend/
│   ├── app/
│   │   ├── api/          # API route handlers (currently empty)
│   │   ├── auth/         # Authentication logic (currently empty)
│   │   ├── core/         # Config, settings
│   │   ├── db/           # Database session, engine
│   │   ├── market/       # Market data module (currently empty)
│   │   ├── models/       # SQLAlchemy models
│   │   ├── monitoring/   # Monitoring (currently empty)
│   │   ├── runtime/      # Runtime module (currently empty)
│   │   ├── schemas/      # Pydantic schemas (currently empty)
│   │   ├── strategy/     # Strategy module (currently empty)
│   │   ├── trading/      # Trading module (currently empty)
│   │   └── utils/        # Utilities (currently empty)
│   ├── tests/            # Test files (pytest)
│   ├── alembic/          # Database migrations
│   ├── requirements.txt  # Python dependencies
│   └── main.py           # FastAPI app entry point
└── frontend/
    ├── src/
    │   ├── components/   # Vue components
    │   ├── assets/       # Static assets
    │   ├── App.vue       # Root component
    │   └── main.ts       # Entry point
    ├── package.json      # Node dependencies
    └── vite.config.ts    # Vite configuration
```

---

## Environment Setup

1. Activate conda env: `conda activate squant`
2. Start services: `docker compose up -d postgres redis`
3. Initialize DB: `cd src/backend && alembic upgrade head`
4. Backend: `cd src/backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
5. Frontend: `cd src/frontend && npm run dev`

---

## Before Submitting Work

- **Backend**: Run `ruff check .`, `mypy .`, and `pytest`
- **Frontend**: Run `npx vue-tsc --noEmit`, build passes
- **Both**: No linting errors, all tests passing
- Test database migrations applied if model changes made

---

## Additional Notes

- CORS enabled for `http://localhost:5173` and `http://localhost:3000`
- API docs available at `http://localhost:8000/docs` (Swagger UI)
- Health check endpoint: `GET /health`
- All endpoints should be under `/api/v1` prefix (define in settings)
