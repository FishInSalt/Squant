"""
端到端测试配置和fixtures

E2E测试需要完整的应用栈运行：Backend API + Database + Redis

运行E2E测试前，请先启动完整应用栈:
    docker compose -f docker-compose.test.yml --profile e2e up -d

运行E2E测试:
    uv run pytest tests/e2e -v

停止测试环境:
    docker compose -f docker-compose.test.yml --profile e2e down -v
"""

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient

# ============================================================================
# 测试环境配置
# ============================================================================


@pytest.fixture(scope="session")
def api_base_url():
    """
    API基础URL

    E2E测试通过HTTP调用API，不直接访问数据库。
    统一使用 localhost:8000 端口（DevContainer 和 CI 环境相同）
    """
    return "http://localhost:8000"


# ============================================================================
# HTTP Client Fixtures
# ============================================================================


@pytest_asyncio.fixture
async def api_client(api_base_url) -> AsyncGenerator[AsyncClient, None]:
    """
    HTTP客户端，用于调用API端点

    这是E2E测试的核心fixture，通过HTTP调用真实的API。
    """
    async with AsyncClient(base_url=api_base_url, timeout=30.0) as client:
        # 验证API服务是否可用
        try:
            response = await client.get("/api/v1/health")
            assert response.status_code == 200, "API server not ready"
        except Exception as e:
            pytest.skip(f"API server not available: {e}")

        yield client


# ============================================================================
# 测试数据 Fixtures
# ============================================================================


@pytest_asyncio.fixture
async def test_strategy_data():
    """测试策略数据 - 每次调用生成唯一名称"""
    import uuid

    unique_id = str(uuid.uuid4())[:8]

    return {
        "name": f"E2E Test Strategy {unique_id}",
        "code": """
# Strategy base class is injected by sandbox - no imports needed

class SimpleStrategy(Strategy):
    \"\"\"Minimal test strategy for E2E testing\"\"\"

    def on_bar(self, bar):
        # Simple buy and hold strategy
        # Just for testing - doesn't generate actual orders
        pass
""",
        "description": "Minimal test strategy for E2E testing",
    }


@pytest_asyncio.fixture
async def test_backtest_config(api_client):
    """测试回测配置 — 基于实际可用数据动态构建。

    通过 /api/v1/backtest/data/check 查询 DB 中实际已有的 K 线数据范围，
    然后从 last_bar 向前取 3 天作为测试窗口。这样无论交易所数据延迟多久，
    只要 DB 中有数据，测试就能稳定通过。
    """
    from datetime import UTC, datetime, timedelta

    exchange = "okx"
    symbol = "BTC/USDT"
    timeframe = "1h"

    # 用一个足够大的窗口查询 DB 中实际可用数据
    now = datetime.now(UTC)
    probe_start = (now - timedelta(days=90)).isoformat()
    probe_end = now.isoformat()

    response = await api_client.post(
        "/api/v1/backtest/data/check",
        json={
            "exchange": exchange,
            "symbol": symbol,
            "timeframe": timeframe,
            "start_date": probe_start,
            "end_date": probe_end,
        },
    )

    if response.status_code != 200:
        pytest.skip(f"Data check API failed: {response.status_code} {response.text}")

    data = response.json().get("data", {})
    if not data.get("has_data") or not data.get("last_bar"):
        pytest.skip("No historical data available in DB for BTC/USDT 1h")

    # 从实际最后一根 K 线向前取 3 天窗口
    last_bar = datetime.fromisoformat(data["last_bar"])
    first_bar = datetime.fromisoformat(data["first_bar"])
    end_date = last_bar
    start_date = end_date - timedelta(days=3)

    # 确保 start_date 不早于实际数据起点
    if start_date < first_bar:
        start_date = first_bar

    # 至少需要 24 根 1h K 线（1 天）才有意义
    hours_available = (end_date - start_date).total_seconds() / 3600
    if hours_available < 24:
        pytest.skip(
            f"Insufficient data: only {hours_available:.0f}h available "
            f"(need >=24h). first_bar={first_bar}, last_bar={last_bar}"
        )

    return {
        "exchange": exchange,
        "symbol": symbol,
        "timeframe": timeframe,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "initial_capital": 10000.0,
        "commission_rate": 0.001,
    }


@pytest_asyncio.fixture
async def cleanup_strategies(api_client):
    """测试结束后清理创建的策略"""
    created_strategy_ids = []

    def register(strategy_id: str):
        created_strategy_ids.append(strategy_id)

    yield register

    # 清理创建的策略
    for strategy_id in created_strategy_ids:
        try:
            await api_client.delete(f"/api/v1/strategies/{strategy_id}")
        except Exception:
            pass  # 忽略删除失败


# ============================================================================
# 辅助函数
# ============================================================================


@pytest.fixture
def wait_for_backtest():
    """等待回测完成的辅助函数"""
    import asyncio

    async def _wait(api_client: AsyncClient, run_id: str, timeout: float = 60.0):
        """
        轮询等待回测完成

        Args:
            api_client: HTTP客户端
            run_id: 回测运行ID
            timeout: 超时时间（秒）

        Returns:
            最终的回测运行状态
        """
        start_time = asyncio.get_event_loop().time()

        while True:
            response = await api_client.get(f"/api/v1/backtest/{run_id}")
            assert response.status_code == 200

            response_data = response.json()
            assert "data" in response_data, f"Response missing 'data' field: {response_data}"

            run_data = response_data["data"]
            status = run_data["status"]

            # 完成状态
            if status in ["completed", "failed", "cancelled", "error"]:
                return run_data

            # 超时检查
            if asyncio.get_event_loop().time() - start_time > timeout:
                pytest.fail(f"Backtest did not complete within {timeout}s")

            # 等待后重试
            await asyncio.sleep(1.0)

    return _wait


@pytest.fixture
def assert_backtest_metrics():
    """验证回测指标的辅助函数"""
    from decimal import Decimal

    def _assert(metrics: dict):
        """验证回测指标是否合理"""
        assert "total_return" in metrics
        assert "sharpe_ratio" in metrics
        assert "max_drawdown" in metrics
        assert "total_trades" in metrics

        # 基本合理性检查 - metrics may be Decimal, float, int, or string
        total_return = metrics["total_return"]
        if isinstance(total_return, str):
            total_return = float(Decimal(total_return))
        elif isinstance(total_return, Decimal):
            total_return = float(total_return)
        assert isinstance(total_return, (int, float))

        assert isinstance(metrics["total_trades"], int)
        assert metrics["total_trades"] >= 0

        max_dd = metrics["max_drawdown"]
        if isinstance(max_dd, str):
            max_dd = float(Decimal(max_dd))
        elif isinstance(max_dd, Decimal):
            max_dd = float(max_dd)
        assert -1.0 <= max_dd <= 0.0  # 最大回撤应该是负数

    return _assert


# ============================================================================
# 标记配置
# ============================================================================


def pytest_configure(config):
    """注册自定义标记"""
    config.addinivalue_line("markers", "e2e: End-to-end tests requiring full application stack")
    config.addinivalue_line("markers", "slow: Slow running E2E tests")


def pytest_collection_modifyitems(config, items):
    """自动为e2e目录下的测试添加e2e标记"""
    for item in items:
        if "e2e" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)
