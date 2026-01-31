# Performance Optimization Guide

This document covers performance analysis, optimization strategies, and benchmarks for the Squant project.

## Table of Contents

- [Test Suite Performance](#test-suite-performance)
- [Application Performance](#application-performance)
- [Database Optimization](#database-optimization)
- [Caching Strategies](#caching-strategies)
- [Benchmarks](#benchmarks)
- [Optimization Recommendations](#optimization-recommendations)

## Test Suite Performance

### Current State (2026-01-31)

**Unit Tests**:
- Total tests: 1,537
- Total time: 9.91 seconds
- Average: ~6.4ms per test
- Coverage: 77%

**Slowest Tests**:
1. `test_periodic_task_handles_exception`: 2.50s (uses real asyncio.sleep)
2. `test_persist_snapshots_called`: 1.50s (uses real asyncio.sleep)
3. `test_health_check_called`: 1.50s (uses real asyncio.sleep)

**Analysis**: Background service tests use actual sleep delays to test periodic task execution, accounting for 5.5s out of 9.91s total runtime. This is acceptable for testing real-world timing behavior.

### Test Optimization Strategies

#### 1. Parallel Test Execution

Run independent test modules in parallel using pytest-xdist:

```bash
# Install pytest-xdist
uv add --dev pytest-xdist

# Run tests in parallel (auto-detect CPU count)
uv run pytest tests/unit -n auto

# Run tests with specific number of workers
uv run pytest tests/unit -n 4
```

**Current status**: ⚠️ **Blocked** - pytest-xdist is installed but many tests fail in parallel due to:
- Shared fixture state (session/module scoped fixtures)
- WebSocket connection state across workers
- Mock object state conflicts

**Required refactoring before enabling**:
1. Convert shared fixtures to function scope with proper cleanup
2. Ensure WebSocket tests use isolated connections
3. Fix mock object sharing issues in parallel workers

**Expected improvement after refactoring**: 40-60% faster on multi-core systems

#### 2. Test Grouping by Speed

Separate fast and slow tests for efficient CI pipelines:

```python
# pyproject.toml
[tool.pytest.ini_options]
markers = [
    "slow: marks tests as slow (>1s)",
    "fast: marks tests as fast (<100ms)",
]
```

```bash
# Run only fast tests for quick feedback
uv run pytest -m "not slow"

# Run all tests
uv run pytest
```

#### 3. Fixture Optimization

**Current state**: Exchange adapter fixture caching already implemented in `tests/unit/api/test_deps.py`

**Recommendation**: Use session-scoped fixtures for expensive setup:

```python
@pytest.fixture(scope="session")
def expensive_resource():
    """Session-scoped fixture for expensive setup."""
    resource = create_expensive_resource()
    yield resource
    cleanup_resource(resource)
```

#### 4. Database Test Optimization

Use database transactions for test isolation instead of teardown:

```python
@pytest.fixture
async def db_session():
    """Database session with automatic rollback."""
    async with engine.begin() as conn:
        await conn.begin_nested()  # Savepoint
        session = AsyncSession(bind=conn)
        yield session
        await session.rollback()  # Rollback savepoint
```

**Benefit**: Faster than DELETE/TRUNCATE teardown

## Application Performance

### Current Caching Mechanisms

1. **Exchange Adapter Cache** (`src/squant/api/deps.py`):
   - Caches CCXT exchange adapters to avoid repeated `load_markets()` calls
   - Saves ~2-3 seconds per request
   - Thread-safe with async lock

2. **Crypto Manager LRU Cache** (`src/squant/utils/crypto.py`):
   - Caches Fernet cipher instances
   - Prevents repeated key derivation

### Performance Bottlenecks

#### 1. Exchange API Calls

**Issue**: Real-time market data fetching can be slow (100-500ms per call)

**Solution**: Implement response caching with TTL:

```python
from datetime import datetime, timedelta
from typing import Optional

class MarketDataCache:
    """TTL cache for market data."""

    def __init__(self, ttl_seconds: int = 1):
        self._cache: dict[str, tuple[Any, datetime]] = {}
        self._ttl = timedelta(seconds=ttl_seconds)

    def get(self, key: str) -> Optional[Any]:
        """Get cached value if not expired."""
        if key in self._cache:
            value, timestamp = self._cache[key]
            if datetime.now() - timestamp < self._ttl:
                return value
            del self._cache[key]
        return None

    def set(self, key: str, value: Any) -> None:
        """Cache value with current timestamp."""
        self._cache[key] = (value, datetime.now())
```

**Usage**:
```python
# In market.py
_ticker_cache = MarketDataCache(ttl_seconds=1)

@router.get("/ticker/{base}/{quote}")
async def get_ticker(base: str, quote: str, exchange: Exchange):
    symbol = f"{base}/{quote}"

    # Check cache first
    cached = _ticker_cache.get(symbol)
    if cached:
        return ApiResponse(data=cached)

    # Fetch from exchange
    ticker = await exchange.get_ticker(symbol)
    _ticker_cache.set(symbol, ticker)
    return ApiResponse(data=ticker)
```

**Expected improvement**: 80-90% reduction in exchange API calls for frequently requested symbols

#### 2. Database Query Optimization

**Current state**: Generic repository pattern with basic filtering

**Optimization opportunities**:

1. **Add database indexes**:
```python
# In models/strategy.py
class Strategy(Base):
    __tablename__ = "strategies"

    # Add indexes
    __table_args__ = (
        Index("ix_strategies_name", "name"),
        Index("ix_strategies_created_at", "created_at"),
    )
```

2. **Use select_in loading for relationships**:
```python
# Avoid N+1 queries
from sqlalchemy.orm import selectinload

async def get_strategy_with_runs(strategy_id: str):
    stmt = (
        select(Strategy)
        .where(Strategy.id == strategy_id)
        .options(selectinload(Strategy.runs))  # Load in single query
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
```

3. **Bulk operations**:
```python
# Instead of individual inserts
async def bulk_create_candles(candles: list[Candlestick]):
    stmt = insert(Candlestick).values([c.dict() for c in candles])
    await session.execute(stmt)
    await session.commit()
```

**Expected improvement**: 30-50% faster for relationship-heavy queries

#### 3. Response Serialization

**Current state**: Pydantic models serialize on every request

**Optimization**: Use Pydantic's model_dump with caching:

```python
from pydantic import computed_field

class TickerResponse(BaseModel):
    symbol: str
    last: Decimal
    # ... other fields

    @computed_field
    @property
    def json_cache(self) -> str:
        """Cached JSON representation."""
        return self.model_dump_json()
```

#### 4. WebSocket Message Processing

**Current implementation**: Individual message handling

**Optimization**: Batch message processing:

```python
async def _handle_messages_batch(self, messages: list[dict]):
    """Process messages in batches."""
    # Group by channel
    by_channel = defaultdict(list)
    for msg in messages:
        by_channel[msg["channel"]].append(msg)

    # Process each channel's messages in bulk
    for channel, channel_msgs in by_channel.items():
        await self._process_channel_batch(channel, channel_msgs)
```

**Expected improvement**: 40-60% better throughput for high-frequency updates

## Database Optimization

### TimescaleDB Optimization

1. **Hypertables for Time-Series Data**:

```sql
-- Convert candles table to hypertable
SELECT create_hypertable('candles', 'timestamp');

-- Add compression policy (compress data older than 7 days)
ALTER TABLE candles SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol'
);

SELECT add_compression_policy('candles', INTERVAL '7 days');
```

2. **Continuous Aggregates for Analytics**:

```sql
-- Pre-compute daily OHLCV
CREATE MATERIALIZED VIEW candles_daily
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', timestamp) AS day,
    symbol,
    first(open, timestamp) AS open,
    max(high) AS high,
    min(low) AS low,
    last(close, timestamp) AS close,
    sum(volume) AS volume
FROM candles
GROUP BY day, symbol;

-- Refresh policy
SELECT add_continuous_aggregate_policy('candles_daily',
    start_offset => INTERVAL '1 month',
    end_offset => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 day');
```

**Expected improvement**: 10-100x faster for historical data queries

### Connection Pooling

**Current state**: AsyncPG with default pool settings

**Optimization**:

```python
# src/squant/infra/database.py
engine = create_async_engine(
    settings.database_url,
    pool_size=20,              # Default: 5
    max_overflow=10,           # Default: 10
    pool_recycle=3600,         # Recycle connections every hour
    pool_pre_ping=True,        # Verify connections before use
    echo_pool=False,           # Disable pool logging in production
)
```

## Caching Strategies

### Redis Caching Layer

Implement Redis caching for frequently accessed data:

```python
# src/squant/infra/cache.py
from redis.asyncio import Redis
from typing import Optional, Any
import json

class CacheService:
    """Redis-based caching service."""

    def __init__(self, redis: Redis, ttl: int = 60):
        self._redis = redis
        self._ttl = ttl

    async def get(self, key: str) -> Optional[Any]:
        """Get cached value."""
        value = await self._redis.get(key)
        return json.loads(value) if value else None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Cache value with TTL."""
        ttl = ttl or self._ttl
        await self._redis.setex(key, ttl, json.dumps(value))

    async def delete(self, key: str) -> None:
        """Delete cached value."""
        await self._redis.delete(key)

# Usage in services
class StrategyService:
    def __init__(self, cache: CacheService):
        self._cache = cache

    async def get_strategy(self, strategy_id: str):
        # Check cache first
        cache_key = f"strategy:{strategy_id}"
        cached = await self._cache.get(cache_key)
        if cached:
            return Strategy(**cached)

        # Fetch from database
        strategy = await self._repo.get(strategy_id)

        # Cache for 5 minutes
        await self._cache.set(cache_key, strategy.dict(), ttl=300)
        return strategy
```

**Cache Invalidation**:

```python
async def update_strategy(self, strategy_id: str, updates: dict):
    """Update strategy and invalidate cache."""
    strategy = await self._repo.update(strategy_id, updates)

    # Invalidate cache
    await self._cache.delete(f"strategy:{strategy_id}")

    return strategy
```

## Benchmarks

### API Endpoint Benchmarks

Use `pytest-benchmark` for performance regression testing:

```python
# tests/benchmark/test_api_performance.py
import pytest
from httpx import AsyncClient

@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_get_ticker_performance(benchmark, async_client: AsyncClient):
    """Benchmark GET /api/v1/market/ticker/{symbol}."""

    async def get_ticker():
        response = await async_client.get("/api/v1/market/ticker/BTC/USDT")
        assert response.status_code == 200
        return response

    # Run benchmark
    result = await benchmark.pedantic(get_ticker, iterations=100, rounds=10)

    # Assert performance SLA
    assert result.stats.mean < 0.1  # Average < 100ms
```

**Install**:
```bash
uv add --dev pytest-benchmark
```

**Run benchmarks**:
```bash
# Run and save baseline
uv run pytest tests/benchmark -v --benchmark-save=baseline

# Compare against baseline
uv run pytest tests/benchmark -v --benchmark-compare=baseline
```

### Load Testing

Use Locust for load testing:

```python
# tests/load/locustfile.py
from locust import HttpUser, task, between

class SquantUser(HttpUser):
    wait_time = between(1, 3)

    @task(3)
    def get_ticker(self):
        """Get ticker (high frequency)."""
        self.client.get("/api/v1/market/ticker/BTC/USDT")

    @task(1)
    def list_strategies(self):
        """List strategies (low frequency)."""
        self.client.get("/api/v1/strategies")

    def on_start(self):
        """Login once per user."""
        self.client.post("/api/v1/auth/login", json={
            "username": "test",
            "password": "test123"
        })
```

**Run**:
```bash
# Install
uv add --dev locust

# Run load test
locust -f tests/load/locustfile.py --host=http://localhost:8000
```

## Optimization Recommendations

### Priority 1: Quick Wins (High Impact, Low Effort)

1. ✅ **Market data caching with 1s TTL** (IMPLEMENTED):
   - Added `MarketDataCache` class in `src/squant/api/v1/market.py`
   - Caches ticker and tickers endpoints with 1-second TTL
   - Automatic cache clearing on exchange switch
   - Expected: 80-90% reduction in exchange API calls for frequently requested symbols
   - Status: Complete and tested (all 1,537 tests passing)

2. ⚠️ **Enable parallel test execution** (BLOCKED):
   - pytest-xdist installed but cannot be enabled yet
   - Requires test refactoring to fix shared state issues
   - See "Test Optimization Strategies" section for details
   - Expected after fixes: 40-60% faster CI

3. ⏸️ **Database indexes on frequently queried columns** (DEFERRED):
   - Order model already has created_at index
   - Strategy model already has status index
   - Could add created_at indexes to Strategy, StrategyRun, RiskRule
   - Expected: 30-50% faster time-based queries
   - Deferred pending query performance profiling in production

### Priority 2: Medium-Term (High Impact, Medium Effort)

1. **Implement Redis caching layer**:
   - Cache strategy, backtest results
   - 5-minute TTL with cache invalidation
   - Expected: 50-70% faster read operations

2. **TimescaleDB compression and continuous aggregates**:
   - Compress historical candle data
   - Pre-compute daily/hourly aggregates
   - Expected: 10-100x faster historical queries

3. **WebSocket message batching**:
   - Batch process high-frequency updates
   - Expected: 40-60% better throughput

### Priority 3: Long-Term (Medium Impact, High Effort)

1. **Query optimization with selectinload**:
   - Eliminate N+1 queries
   - Expected: 30-50% faster for relationship queries

2. **Load balancing and horizontal scaling**:
   - Multiple API instances behind load balancer
   - Separate read replicas for analytics
   - Expected: Linear scaling with instances

3. **CDN for frontend assets**:
   - Cache static assets
   - Expected: 50-80% faster initial page load

## Monitoring and Profiling

### Application Profiling

Use `py-spy` for production profiling:

```bash
# Install
uv add --dev py-spy

# Profile running application
py-spy top --pid <uvicorn-pid>

# Record flame graph
py-spy record -o profile.svg --pid <uvicorn-pid> --duration 60
```

### Database Query Profiling

Enable query logging in development:

```python
# config.py (development only)
engine = create_async_engine(
    settings.database_url,
    echo=True,  # Log all SQL queries
)
```

Analyze slow queries:

```sql
-- Enable pg_stat_statements extension
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Find slow queries
SELECT
    query,
    calls,
    total_exec_time,
    mean_exec_time,
    max_exec_time
FROM pg_stat_statements
WHERE mean_exec_time > 100  -- Slower than 100ms
ORDER BY total_exec_time DESC
LIMIT 20;
```

### Performance Metrics

Track key metrics in production:

```python
from prometheus_client import Counter, Histogram

# Request duration
http_request_duration = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration',
    ['method', 'endpoint']
)

# Cache hit rate
cache_hits = Counter('cache_hits_total', 'Cache hits')
cache_misses = Counter('cache_misses_total', 'Cache misses')

# Exchange API calls
exchange_api_calls = Counter(
    'exchange_api_calls_total',
    'Exchange API calls',
    ['exchange', 'endpoint']
)
```

## Performance SLAs

### Target Metrics

| Metric | Target | Current |
|--------|--------|---------|
| Unit test suite | < 15s | 9.91s ✅ |
| Integration test suite | < 30s | ~1m30s ❌ |
| E2E test suite | < 60s | ~1m50s ❌ |
| GET /ticker response | < 100ms | ~150ms ❌ |
| GET /strategies list | < 200ms | ~180ms ✅ |
| POST /backtest/start | < 500ms | ~450ms ✅ |
| WebSocket message latency | < 50ms | ~60ms ❌ |

### Performance Testing in CI

Add performance regression tests:

```yaml
# .github/workflows/performance.yml
name: Performance Tests

on:
  pull_request:
    branches: [main, develop]

jobs:
  benchmark:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4
    - uses: astral-sh/setup-uv@v4
    - run: uv sync --all-extras

    - name: Run benchmarks
      run: |
        uv run pytest tests/benchmark -v \
          --benchmark-json=benchmark.json

    - name: Check performance regression
      run: |
        # Fail if mean time increased by >10%
        uv run python scripts/check_perf_regression.py \
          --threshold=1.1 \
          --baseline=baseline.json \
          --current=benchmark.json
```

## Related Documentation

- [TESTING_GUIDE.md](./TESTING_GUIDE.md) - Testing best practices
- [CI_SETUP.md](./CI_SETUP.md) - CI/CD configuration
- [INTEGRATION_TESTING.md](./INTEGRATION_TESTING.md) - Integration testing guide

---

**Maintainer**: Development Team
**Last Updated**: 2026-01-31
**Project**: Squant - Quantitative Trading System
