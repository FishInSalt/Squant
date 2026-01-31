# CI/CD测试集成指南

本文档介绍如何在持续集成/持续部署（CI/CD）流程中集成Squant项目的测试套件。

## 目录

- [测试策略](#测试策略)
- [GitHub Actions配置](#github-actions配置)
- [测试环境配置](#测试环境配置)
- [覆盖率报告](#覆盖率报告)
- [测试分级执行](#测试分级执行)
- [性能优化](#性能优化)
- [故障排查](#故障排查)

---

## 测试策略

### 测试金字塔

Squant采用分层测试策略：

```
         /\
        /  \       E2E Tests (少量，关键流程)
       /____\      ~5% of tests
      /      \
     / Integ. \    Integration Tests (中等数量)
    /__________\   ~25% of tests
   /            \
  /  Unit Tests  \ Unit Tests (大量，快速)
 /________________\ ~70% of tests
```

### CI中的测试分类

1. **快速反馈测试**（每次push）：
   - 单元测试
   - Linting和类型检查
   - 快速集成测试
   - 时间: ~2-3分钟

2. **完整测试**（PR合并前）：
   - 所有单元测试
   - 完整集成测试
   - 覆盖率检查
   - 时间: ~5-10分钟

3. **夜间测试**（定时任务）：
   - E2E测试
   - 性能测试
   - 交易所集成测试（需要真实API）
   - 时间: ~20-30分钟

---

## GitHub Actions配置

### 基础工作流配置

创建 `.github/workflows/test.yml`:

```yaml
name: Tests

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main, develop ]

jobs:
  lint:
    name: Lint & Type Check
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4
        with:
          version: "0.5.11"

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: uv sync

      - name: Run ruff (linting)
        run: uv run ruff check .

      - name: Run ruff (formatting)
        run: uv run ruff format --check .

      - name: Run mypy (type check)
        run: uv run mypy src/squant

  unit-tests:
    name: Unit Tests
    runs-on: ubuntu-latest

    services:
      postgres:
        image: timescale/timescaledb:latest-pg16
        env:
          POSTGRES_USER: squant
          POSTGRES_PASSWORD: squant
          POSTGRES_DB: squant_test
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4
        with:
          version: "0.5.11"

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: uv sync

      - name: Run database migrations
        env:
          DATABASE_URL: postgresql+asyncpg://squant:squant@localhost:5432/squant_test
          REDIS_URL: redis://localhost:6379/0
        run: uv run alembic upgrade head

      - name: Run unit tests
        env:
          DATABASE_URL: postgresql+asyncpg://squant:squant@localhost:5432/squant_test
          REDIS_URL: redis://localhost:6379/0
          SECRET_KEY: test-secret-key-min-32-chars-long-for-testing
          ENCRYPTION_KEY: test-encryption-key-32-chars!!
        run: |
          uv run pytest tests/unit \
            -v \
            --cov=src/squant \
            --cov-report=xml \
            --cov-report=term-missing \
            --junit-xml=test-results.xml

      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v4
        with:
          file: ./coverage.xml
          flags: unittests
          name: codecov-umbrella

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: test-results
          path: test-results.xml

  integration-tests:
    name: Integration Tests
    runs-on: ubuntu-latest
    if: github.event_name == 'pull_request' || github.ref == 'refs/heads/main'

    services:
      postgres:
        image: timescale/timescaledb:latest-pg16
        env:
          POSTGRES_USER: squant
          POSTGRES_PASSWORD: squant
          POSTGRES_DB: squant_test
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4
        with:
          version: "0.5.11"

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: uv sync

      - name: Run database migrations
        env:
          DATABASE_URL: postgresql+asyncpg://squant:squant@localhost:5432/squant_test
          REDIS_URL: redis://localhost:6379/0
        run: uv run alembic upgrade head

      - name: Run integration tests
        env:
          DATABASE_URL: postgresql+asyncpg://squant:squant@localhost:5432/squant_test
          REDIS_URL: redis://localhost:6379/0
          SECRET_KEY: test-secret-key-min-32-chars-long-for-testing
          ENCRYPTION_KEY: test-encryption-key-32-chars!!
        run: |
          uv run pytest tests/integration \
            -v \
            --cov=src/squant \
            --cov-report=xml \
            --junit-xml=integration-results.xml

      - name: Upload integration test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: integration-results
          path: integration-results.xml
```

### 矩阵测试（多版本Python）

```yaml
  test-matrix:
    name: Test (Python ${{ matrix.python-version }})
    runs-on: ubuntu-latest

    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.11", "3.12", "3.13"]

    services:
      postgres:
        image: timescale/timescaledb:latest-pg16
        # ... (同上)

      redis:
        image: redis:7-alpine
        # ... (同上)

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: uv sync

      - name: Run tests
        env:
          DATABASE_URL: postgresql+asyncpg://squant:squant@localhost:5432/squant_test
          REDIS_URL: redis://localhost:6379/0
        run: uv run pytest tests/unit -v
```

### 夜间完整测试

创建 `.github/workflows/nightly.yml`:

```yaml
name: Nightly Tests

on:
  schedule:
    # 每天UTC时间2:00 (北京时间10:00)
    - cron: '0 2 * * *'
  workflow_dispatch:  # 允许手动触发

jobs:
  e2e-tests:
    name: End-to-End Tests
    runs-on: ubuntu-latest
    timeout-minutes: 60

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Start services with Docker Compose
        run: |
          docker compose -f docker-compose.dev.yml up -d
          sleep 10  # 等待服务启动

      - name: Run database migrations
        run: |
          uv run alembic upgrade head

      - name: Run E2E tests
        env:
          OKX_API_KEY: ${{ secrets.OKX_TESTNET_API_KEY }}
          OKX_API_SECRET: ${{ secrets.OKX_TESTNET_API_SECRET }}
          OKX_PASSPHRASE: ${{ secrets.OKX_TESTNET_PASSPHRASE }}
        run: |
          uv run pytest tests/e2e \
            -v \
            --junit-xml=e2e-results.xml

      - name: Stop services
        if: always()
        run: docker compose -f docker-compose.dev.yml down

      - name: Upload E2E test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: e2e-results
          path: e2e-results.xml

      - name: Notify on failure
        if: failure()
        uses: 8398a7/action-slack@v3
        with:
          status: ${{ job.status }}
          text: 'Nightly E2E tests failed!'
          webhook_url: ${{ secrets.SLACK_WEBHOOK }}
```

---

## 测试环境配置

### 环境变量

在GitHub仓库设置中配置Secrets:

**必需的Secrets**:
- `DATABASE_URL` (自动通过service提供)
- `REDIS_URL` (自动通过service提供)
- `SECRET_KEY` (测试用)
- `ENCRYPTION_KEY` (测试用)

**可选的Secrets（用于E2E测试）**:
- `OKX_TESTNET_API_KEY`
- `OKX_TESTNET_API_SECRET`
- `OKX_TESTNET_PASSPHRASE`
- `BINANCE_TESTNET_API_KEY`
- `BINANCE_TESTNET_API_SECRET`

### pytest配置

确保 `pytest.ini` 正确配置：

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*

# 异步测试配置
asyncio_mode = auto
asyncio_default_fixture_loop_scope = function

# 标记
markers =
    unit: Unit tests (fast, no external dependencies)
    integration: Integration tests (require database/redis)
    e2e: End-to-end tests (full system test)
    slow: Slow running tests
    okx_private: Tests requiring OKX API credentials
    binance_private: Tests requiring Binance API credentials

# 覆盖率配置
addopts =
    --strict-markers
    --strict-config
    --showlocals
    -ra

# 超时配置（防止测试卡住）
timeout = 300
timeout_method = thread
```

### .coveragerc配置

```ini
[run]
source = src/squant
omit =
    */tests/*
    */migrations/*
    */__pycache__/*
    */venv/*
    */.venv/*

[report]
precision = 2
exclude_lines =
    pragma: no cover
    def __repr__
    def __str__
    raise AssertionError
    raise NotImplementedError
    if __name__ == .__main__.:
    if TYPE_CHECKING:
    @abstractmethod
    @abc.abstractmethod

[html]
directory = htmlcov
```

---

## 覆盖率报告

### Codecov集成

1. **注册Codecov**: 在 [codecov.io](https://codecov.io) 注册并关联GitHub仓库

2. **配置codecov.yml**:

```yaml
# .codecov.yml
coverage:
  status:
    project:
      default:
        target: 40%         # 最低覆盖率要求
        threshold: 1%       # 允许下降1%
    patch:
      default:
        target: 60%         # 新代码要求更高覆盖率

comment:
  layout: "header, diff, files"
  behavior: default

ignore:
  - "tests/"
  - "alembic/"
  - "scripts/"
```

3. **在PR中查看覆盖率**:
   - Codecov会自动评论PR
   - 显示新增代码的覆盖率
   - 高亮未覆盖的行

### 本地覆盖率报告

```bash
# 生成HTML报告
uv run pytest --cov=src/squant --cov-report=html

# 在浏览器中查看
open htmlcov/index.html

# 终端查看
uv run pytest --cov=src/squant --cov-report=term-missing

# 生成JSON报告（供工具使用）
uv run pytest --cov=src/squant --cov-report=json
```

---

## 测试分级执行

### 使用pytest标记

```python
# tests/unit/services/test_order.py
import pytest

@pytest.mark.unit
def test_fast_unit_test():
    """快速单元测试"""
    pass

@pytest.mark.integration
async def test_database_integration():
    """需要数据库的集成测试"""
    pass

@pytest.mark.e2e
@pytest.mark.slow
async def test_full_backtest_workflow():
    """完整的回测流程（慢）"""
    pass

@pytest.mark.okx_private
async def test_okx_real_api():
    """需要OKX API凭证的测试"""
    pass
```

### CI中的选择性执行

```yaml
# 快速测试（每次push）
- name: Run fast tests
  run: |
    uv run pytest -m "unit and not slow" -v

# 集成测试（PR）
- name: Run integration tests
  run: |
    uv run pytest -m "integration" -v

# 完整测试（合并到main）
- name: Run all tests
  run: |
    uv run pytest -v

# 跳过需要API凭证的测试
- name: Run tests (skip private)
  run: |
    uv run pytest -m "not okx_private and not binance_private" -v
```

---

## 性能优化

### 并行测试执行

```yaml
- name: Run tests in parallel
  run: |
    uv run pytest -n auto --dist loadgroup -v
```

需要安装 `pytest-xdist`:
```bash
uv add --dev pytest-xdist
```

### 测试缓存

```yaml
- name: Cache pytest cache
  uses: actions/cache@v4
  with:
    path: .pytest_cache
    key: pytest-cache-${{ runner.os }}-${{ hashFiles('**/pyproject.toml') }}

- name: Run tests (use cache)
  run: |
    # 只运行上次失败的测试
    uv run pytest --lf -v

    # 如果没有失败，运行所有测试
    uv run pytest --ff -v
```

### Docker层缓存

```yaml
- name: Set up Docker Buildx
  uses: docker/setup-buildx-action@v3

- name: Cache Docker layers
  uses: actions/cache@v4
  with:
    path: /tmp/.buildx-cache
    key: ${{ runner.os }}-buildx-${{ github.sha }}
    restore-keys: |
      ${{ runner.os }}-buildx-
```

---

## 故障排查

### 常见CI测试失败

#### 1. 数据库连接失败

**错误**: `psycopg.OperationalError: could not connect to server`

**解决**:
```yaml
services:
  postgres:
    # 添加健康检查
    options: >-
      --health-cmd pg_isready
      --health-interval 10s
      --health-timeout 5s
      --health-retries 5

steps:
  # 等待服务准备就绪
  - name: Wait for services
    run: |
      timeout 30 bash -c 'until pg_isready -h localhost -p 5432; do sleep 1; done'
```

#### 2. 测试超时

**错误**: `FAILED tests/test_example.py::test_long_running - Timeout`

**解决**:
```yaml
jobs:
  test:
    timeout-minutes: 30  # 设置作业超时

steps:
  - name: Run tests
    run: |
      # 单个测试超时
      uv run pytest --timeout=300 -v
```

或在测试中:
```python
@pytest.mark.timeout(60)  # 60秒超时
async def test_long_running():
    ...
```

#### 3. 依赖安装失败

**错误**: `error: Failed to download distributions`

**解决**:
```yaml
- name: Install dependencies with retry
  uses: nick-invision/retry@v2
  with:
    timeout_minutes: 10
    max_attempts: 3
    command: uv sync
```

#### 4. 内存不足

**错误**: `Killed` 或 `MemoryError`

**解决**:
```yaml
- name: Run tests (limit workers)
  run: |
    # 限制并行worker数量
    uv run pytest -n 2 -v  # 只用2个worker

    # 或者不使用并行
    uv run pytest -v
```

### 查看详细日志

```yaml
- name: Run tests with verbose output
  run: |
    uv run pytest -vv -s --log-cli-level=DEBUG

- name: Upload logs on failure
  if: failure()
  uses: actions/upload-artifact@v4
  with:
    name: test-logs
    path: |
      logs/
      *.log
```

---

## 本地CI模拟

使用 [act](https://github.com/nektos/act) 在本地运行GitHub Actions:

```bash
# 安装act (macOS)
brew install act

# 运行工作流
act push

# 运行特定job
act -j unit-tests

# 使用secrets
act -s GITHUB_TOKEN=your_token
```

---

## 持续改进

### 测试性能监控

创建 `.github/workflows/test-benchmark.yml`:

```yaml
name: Test Performance

on:
  push:
    branches: [ main ]

jobs:
  benchmark:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run tests and measure time
        run: |
          start=$(date +%s)
          uv run pytest tests/unit -v
          end=$(date +%s)
          duration=$((end - start))
          echo "Test duration: ${duration}s"
          echo "test_duration=${duration}" >> $GITHUB_OUTPUT
        id: test

      - name: Save benchmark
        run: |
          echo "${{ steps.test.outputs.test_duration }}" > benchmark.txt
          git config user.name "GitHub Actions"
          git config user.email "actions@github.com"
          git add benchmark.txt
          git commit -m "Update test benchmark"
          git push
```

### 覆盖率趋势

使用Codecov的图表功能查看覆盖率趋势：
- 整体覆盖率变化
- 各模块覆盖率变化
- PR对覆盖率的影响

---

## 相关资源

- [GitHub Actions文档](https://docs.github.com/en/actions)
- [pytest文档](https://docs.pytest.org/)
- [Codecov文档](https://docs.codecov.com/)
- [act - 本地CI工具](https://github.com/nektos/act)

---

**最后更新**: 2026-01-30
**维护者**: Development Team
