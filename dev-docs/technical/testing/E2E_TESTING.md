# End-to-End (E2E) Testing Guide

This guide covers end-to-end testing in the Squant project, which validates complete user workflows from frontend to backend with real dependencies.

## Table of Contents

- [Overview](#overview)
- [E2E vs Integration vs Unit Tests](#e2e-vs-integration-vs-unit-tests)
- [E2E Test Environment](#e2e-test-environment)
- [Running E2E Tests](#running-e2e-tests)
- [Writing E2E Tests](#writing-e2e-tests)
- [Test Data Management](#test-data-management)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)

## Overview

End-to-end tests validate complete user workflows by testing the entire system stack:

- **Frontend** (optional): Vue.js application
- **Backend API**: FastAPI endpoints
- **WebSocket**: Real-time data streaming
- **Database**: PostgreSQL + TimescaleDB
- **Cache**: Redis
- **External Services**: Exchange APIs (using testnets)

E2E tests ensure that all components work together correctly in a production-like environment.

## E2E vs Integration vs Unit Tests

| Aspect | Unit Tests | Integration Tests | E2E Tests |
|--------|-----------|-------------------|-----------|
| **Scope** | Single function/class | Multiple components | Full system |
| **Dependencies** | All mocked | Real databases | Everything real |
| **Speed** | Fast (<1s) | Medium (1-5s) | Slow (5-30s) |
| **Isolation** | Complete | Partial | None |
| **Environment** | In-memory | Docker services | Full stack |
| **Coverage** | Logic/edge cases | Component integration | User workflows |

**When to use each**:

- **Unit tests**: Business logic, data transformations, error handling
- **Integration tests**: Database operations, API endpoints, service interactions
- **E2E tests**: Complete workflows (backtest → analysis → strategy execution)

## E2E Test Environment

### Docker Compose Stack

E2E tests use `docker-compose.test.yml` with the `e2e` profile:

```bash
docker compose -f docker-compose.test.yml --profile e2e up -d
```

This starts:

1. **PostgreSQL + TimescaleDB** (port 5433)
   - Test database with migrations applied
   - TimescaleDB extension for time-series data

2. **Redis** (port 6380)
   - Cache and pub/sub for real-time data

3. **Backend API** (port 8001)
   - Full FastAPI application
   - Connected to test database and Redis
   - WebSocket endpoints enabled

4. **Frontend** (optional, port 5174)
   - Vue.js development server
   - Connected to backend API

### Environment Variables

E2E tests use dedicated test environment variables:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://squant_test:squant_test@localhost:5433/squant_test

# Redis
REDIS_URL=redis://localhost:6380

# Security
SECRET_KEY=test-secret-key-for-integration-testing-min-32-chars
ENCRYPTION_KEY=test-encryption-key-32-chars-long

# Exchange APIs (testnet credentials)
OKX_API_KEY=<testnet-key>
OKX_API_SECRET=<testnet-secret>
OKX_PASSPHRASE=<testnet-passphrase>
OKX_TESTNET=true
```

## Running E2E Tests

### Quick Start

```bash
# 1. Start E2E environment
docker compose -f docker-compose.test.yml --profile e2e up -d

# 2. Wait for services to be ready (check API health)
max_attempts=30
attempt=0
until curl -f http://localhost:8001/api/v1/health || [ $attempt -eq $max_attempts ]; do
  echo "Waiting for API... (attempt $((attempt+1))/$max_attempts)"
  sleep 2
  attempt=$((attempt+1))
done

# 3. Seed test data (generates 7 days of BTC/USDT 1h klines)
DATABASE_URL=postgresql+asyncpg://squant_test:squant_test@localhost:5433/squant_test \
REDIS_URL=redis://localhost:6380 \
uv run python tests/e2e/seed_data.py

# 4. Run E2E tests
uv run pytest tests/e2e -v

# 5. Stop environment (optional, use -v to remove volumes)
docker compose -f docker-compose.test.yml --profile e2e down
```

**Expected Results**:
- 16 tests passed
- 1 test skipped (test_cancel_running_backtest)
- Overall code coverage: ~37%

### Using pytest-asyncio

E2E tests are async and use pytest-asyncio:

```bash
# Run all E2E tests
uv run pytest tests/e2e -v

# Run specific test file
uv run pytest tests/e2e/test_backtest_workflow.py -v

# Run specific test
uv run pytest tests/e2e/test_backtest_workflow.py::test_complete_backtest_workflow -v

# With coverage
uv run pytest tests/e2e -v --cov=src/squant --cov-report=html
```

### Health Check

Before running tests, verify services are healthy:

```bash
# Check API health
curl http://localhost:8001/api/v1/health

# Expected response:
# {"code":0,"message":"success","data":{"status":"healthy",...}}
```

## Writing E2E Tests

### Test Structure

E2E tests follow this structure:

```python
"""E2E tests for <workflow-name>.

These tests validate complete user workflows with real dependencies.
"""

import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
@pytest.mark.e2e
async def test_<workflow_name>(
    e2e_client: AsyncClient,
    test_user: dict,
) -> None:
    """Test <workflow description>.

    Workflow:
    1. Step 1 description
    2. Step 2 description
    3. Step 3 description
    ...
    """
    # 1. Setup - Prepare test data
    # ...

    # 2. Execute - Perform workflow steps
    # ...

    # 3. Verify - Assert expected results
    # ...

    # 4. Cleanup (optional) - Remove test data
    # ...
```

### Example: Backtest Workflow

```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
@pytest.mark.e2e
async def test_complete_backtest_workflow(
    e2e_client: AsyncClient,
) -> None:
    """Test complete backtest workflow from creation to results analysis.

    Workflow:
    1. Create a strategy
    2. Configure backtest parameters
    3. Start backtest
    4. Monitor progress
    5. Retrieve results
    6. Analyze performance metrics
    """
    # 1. Create strategy
    strategy_data = {
        "name": "Test MA Cross Strategy",
        "description": "E2E test strategy",
        "code": """
class MACrossStrategy(Strategy):
    def on_bar(self, bar):
        # Simple MA crossover logic
        if self.sma_fast[-1] > self.sma_slow[-1]:
            self.buy(size=1.0)
        elif self.sma_fast[-1] < self.sma_slow[-1]:
            self.sell(size=1.0)
""",
        "version": "1.0.0",
    }

    response = await e2e_client.post("/api/v1/strategies", json=strategy_data)
    assert response.status_code == 200
    strategy_id = response.json()["data"]["id"]

    # 2. Configure backtest
    backtest_config = {
        "strategy_id": strategy_id,
        "exchange": "okx",
        "symbol": "BTC/USDT",
        "start_time": "2024-01-01T00:00:00Z",
        "end_time": "2024-01-31T23:59:59Z",
        "initial_capital": 10000.0,
        "timeframe": "1h",
    }

    response = await e2e_client.post("/api/v1/backtest", json=backtest_config)
    assert response.status_code == 200
    backtest_id = response.json()["data"]["id"]

    # 3. Start backtest
    response = await e2e_client.post(f"/api/v1/backtest/{backtest_id}/start")
    assert response.status_code == 200

    # 4. Monitor progress (poll until complete)
    import asyncio
    max_attempts = 60
    for attempt in range(max_attempts):
        response = await e2e_client.get(f"/api/v1/backtest/{backtest_id}")
        assert response.status_code == 200

        status = response.json()["data"]["status"]
        if status == "completed":
            break
        elif status == "failed":
            pytest.fail(f"Backtest failed: {response.json()['data'].get('error')}")

        await asyncio.sleep(1)
    else:
        pytest.fail("Backtest did not complete within 60 seconds")

    # 5. Retrieve results
    response = await e2e_client.get(f"/api/v1/backtest/{backtest_id}/results")
    assert response.status_code == 200
    results = response.json()["data"]

    # 6. Verify results structure and metrics
    assert "performance" in results
    assert "trades" in results
    assert results["performance"]["total_trades"] > 0
    assert results["performance"]["final_capital"] > 0
```

### Fixtures for E2E Tests

E2E tests use special fixtures defined in `tests/e2e/conftest.py`:

```python
@pytest.fixture
async def e2e_client() -> AsyncGenerator[AsyncClient, None]:
    """Create async HTTP client for E2E tests.

    Points to the running E2E backend service (port 8001).
    """
    async with AsyncClient(base_url="http://localhost:8001") as client:
        yield client

@pytest.fixture
async def test_user(e2e_client: AsyncClient) -> dict:
    """Create a test user for E2E tests."""
    response = await e2e_client.post("/api/v1/auth/register", json={
        "username": "testuser",
        "email": "test@example.com",
        "password": "testpass123",
    })
    assert response.status_code == 200
    return response.json()["data"]

@pytest.fixture
async def authenticated_client(
    e2e_client: AsyncClient,
    test_user: dict,
) -> AsyncClient:
    """Create authenticated HTTP client."""
    # Login
    response = await e2e_client.post("/api/v1/auth/login", json={
        "username": test_user["username"],
        "password": "testpass123",
    })
    assert response.status_code == 200
    token = response.json()["data"]["access_token"]

    # Set authorization header
    e2e_client.headers["Authorization"] = f"Bearer {token}"
    return e2e_client
```

## Test Data Management

### Seeding Data

Before running E2E tests, seed the database with historical market data:

```python
# tests/e2e/seed_data.py
import asyncio
from decimal import Decimal
from datetime import UTC, datetime, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

async def generate_klines(
    exchange: str, symbol: str, timeframe: str,
    start_date: datetime, end_date: datetime,
    base_price: Decimal = Decimal("50000.0"),
) -> list[Kline]:
    """Generate test kline data with random walk price simulation."""
    # Generates realistic OHLCV data for backtesting
    # Price follows random walk with mean reversion
    ...

async def seed_test_data(session: AsyncSession):
    """Insert E2E test data - 7 days of BTC/USDT 1h klines."""
    end_date = datetime.now(UTC)
    start_date = end_date - timedelta(days=7)

    klines = await generate_klines(
        exchange="okx", symbol="BTC/USDT", timeframe="1h",
        start_date=start_date, end_date=end_date,
    )

    session.add_all(klines)
    await session.commit()
    print(f"✅ Successfully inserted {len(klines)} klines")

if __name__ == "__main__":
    asyncio.run(main())
```

Run before E2E tests with correct environment variables:

```bash
DATABASE_URL=postgresql+asyncpg://squant_test:squant_test@localhost:5433/squant_test \
REDIS_URL=redis://localhost:6380 \
uv run python tests/e2e/seed_data.py
```

**Output**:
```
生成测试K线数据: okx:BTC/USDT:1h
时间范围: 2026-01-24 to 2026-01-31
生成了 168 条K线数据
✅ 成功插入 168 条K线数据
```

### Cleanup Between Tests

Use fixtures to ensure cleanup:

```python
@pytest.fixture
async def clean_database(e2e_client: AsyncClient):
    """Clean up database after each test."""
    yield
    # Cleanup logic
    await e2e_client.delete("/api/v1/test/cleanup")
```

## Best Practices

### 1. Test Complete Workflows

E2E tests should validate entire user journeys:

```python
# ✅ Good: Complete workflow
@pytest.mark.e2e
async def test_backtest_workflow(e2e_client):
    # Create strategy → Configure backtest → Run → Analyze results
    ...

# ❌ Bad: Testing single endpoint (use integration test instead)
@pytest.mark.e2e
async def test_get_strategy(e2e_client):
    response = await e2e_client.get("/api/v1/strategies/1")
    assert response.status_code == 200
```

### 2. Keep Tests Independent

Each test should be independent and repeatable:

```python
# ✅ Good: Creates own data
@pytest.mark.e2e
async def test_workflow(e2e_client):
    # Create test strategy
    strategy = await create_test_strategy(e2e_client)
    # Use strategy in test
    ...

# ❌ Bad: Depends on other tests
@pytest.mark.e2e
async def test_workflow(e2e_client):
    # Assumes strategy with ID 1 exists
    response = await e2e_client.get("/api/v1/strategies/1")
    ...
```

### 3. Use Realistic Data

Use production-like data and scenarios:

```python
# ✅ Good: Realistic parameters
backtest_config = {
    "initial_capital": 10000.0,  # Realistic amount
    "start_time": "2024-01-01T00:00:00Z",  # Recent date
    "timeframe": "1h",  # Common timeframe
}

# ❌ Bad: Unrealistic data
backtest_config = {
    "initial_capital": 1.0,  # Too small
    "start_time": "2000-01-01T00:00:00Z",  # Too old
    "timeframe": "1s",  # Uncommon
}
```

### 4. Add Reasonable Timeouts

E2E tests may take time; use appropriate timeouts:

```python
# ✅ Good: Polling with timeout
max_attempts = 60
for attempt in range(max_attempts):
    status = await check_status()
    if status == "completed":
        break
    await asyncio.sleep(1)
else:
    pytest.fail("Timeout waiting for completion")

# ❌ Bad: No timeout
while True:  # May hang forever
    status = await check_status()
    if status == "completed":
        break
    await asyncio.sleep(1)
```

### 5. Clean Up Resources

Always clean up test resources:

```python
@pytest.mark.e2e
async def test_workflow(e2e_client):
    strategy_id = None
    backtest_id = None

    try:
        # Create resources
        strategy_id = await create_strategy()
        backtest_id = await create_backtest(strategy_id)

        # Run test
        ...

    finally:
        # Clean up
        if backtest_id:
            await e2e_client.delete(f"/api/v1/backtest/{backtest_id}")
        if strategy_id:
            await e2e_client.delete(f"/api/v1/strategies/{strategy_id}")
```

## Troubleshooting

### Services Not Ready

**Symptom**: Tests fail with connection errors

**Solution**: Add health check before running tests

```bash
# Wait for API to be ready
max_attempts=30
attempt=0
until curl -f http://localhost:8001/api/v1/health || [ $attempt -eq $max_attempts ]; do
  echo "Waiting for API... (attempt $((attempt+1))/$max_attempts)"
  sleep 2
  attempt=$((attempt+1))
done
```

### Database Migrations Not Applied

**Symptom**: Relation does not exist errors (e.g., "relation 'strategies' does not exist")

**Root Cause**: Alembic version table exists but actual migrations weren't applied (database state inconsistency)

**Solution 1** - Reset alembic version and re-apply migrations:

```bash
# Connect to E2E test database
docker exec -it squant-postgres-test psql -U squant_test -d squant_test

# Delete stale alembic version
DELETE FROM alembic_version;

# Exit psql
\q

# Re-apply migrations from container
docker exec squant-app-test alembic upgrade head

# Verify tables created
docker exec -it squant-postgres-test psql -U squant_test -d squant_test -c "\dt"
# Should show 14 tables: strategies, backtest_runs, orders, klines, etc.
```

**Solution 2** - Ensure migrations run on container startup:

The `docker-entrypoint.sh` script automatically runs migrations:

```bash
#!/bin/bash
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Starting Squant application..."
exec uvicorn squant.main:app --host 0.0.0.0 --port 8000
```

If migrations still don't apply, check container logs:

```bash
docker logs squant-app-test
```

### Test Data Conflicts

**Symptom**: Unique constraint violations

**Solution**: Use unique names or clean up between tests

```python
import uuid

@pytest.mark.e2e
async def test_workflow(e2e_client):
    # Generate unique name
    unique_id = uuid.uuid4().hex[:8]
    strategy_name = f"test-strategy-{unique_id}"

    strategy = await create_strategy(name=strategy_name)
    ...
```

### Slow Tests

**Symptom**: E2E tests take too long

**Solutions**:

1. Run fewer E2E tests, more integration tests
2. Parallelize E2E tests (carefully)
3. Use faster polling intervals
4. Optimize test data size

```python
# Faster polling
await asyncio.sleep(0.5)  # Instead of 1 second

# Smaller date ranges
"start_time": "2024-01-01T00:00:00Z",
"end_time": "2024-01-02T00:00:00Z",  # 1 day instead of 1 month
```

### WebSocket Connection Failures

**Symptom**: WebSocket tests fail to connect

**Solution**: Ensure WebSocket endpoint is enabled

```python
from httpx_ws import aconnect_ws

@pytest.mark.e2e
async def test_websocket_stream(e2e_client):
    async with aconnect_ws("ws://localhost:8001/ws/market") as ws:
        # Subscribe to market data
        await ws.send_json({"action": "subscribe", "channel": "ticker.BTC/USDT"})

        # Receive data
        message = await ws.receive_json()
        assert message["channel"] == "ticker.BTC/USDT"
```

## Related Documentation

- [TESTING_GUIDE.md](./TESTING_GUIDE.md) - General testing guide
- [INTEGRATION_TESTING.md](./INTEGRATION_TESTING.md) - Integration testing
- [CI_SETUP.md](./CI_SETUP.md) - CI/CD configuration
- [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) - Common issues

---

**Maintainer**: Development Team
**Last Updated**: 2026-01-31
**Project**: Squant - Quantitative Trading System
