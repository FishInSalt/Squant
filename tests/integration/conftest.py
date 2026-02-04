"""
集成测试配置和fixtures

集成测试需要真实的数据库和Redis连接。

运行方式（两种环境使用不同的配置文件）:

1. 在 DevContainer 内部:
    - 自动加载 .env.test.local（Docker 服务名: postgres:5432, redis:6379）
    - 运行: uv run pytest tests/integration -v
    - 首次运行前需创建: cp .env.test.local.example .env.test.local

2. 在 CI/GitHub Actions:
    - 自动加载 .env.test.ci（localhost:5433, localhost:6380）
    - 无需额外配置，CI 会自动使用正确的配置

配置文件说明:
    - .env.test.ci: CI 环境专用，使用 localhost 端口映射（已提交到仓库）
    - .env.test.local: 本地测试专用，使用 Docker 服务名（不提交，含敏感凭证）
    - .env.test.local.example: 本地配置模板（已提交到仓库）
"""

import asyncio
import os
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ==========================================================================
# 加载测试环境变量 (必须在导入 squant 模块之前)
# ==========================================================================

# 检测是否在 CI 环境中运行
_IS_CI = os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true"


def _load_env_file(env_file: Path) -> None:
    """从 .env 文件加载环境变量

    Args:
        env_file: .env 文件路径
    """
    if not env_file.exists():
        return

    with open(env_file) as f:
        for line in f:
            line = line.strip()
            # 跳过空行和注释
            if not line or line.startswith("#"):
                continue
            # 解析 KEY=VALUE
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                # 设置环境变量（覆盖已存在的值，确保使用正确的测试配置）
                if key:
                    os.environ[key] = value


def _setup_test_environment() -> None:
    """设置测试环境变量（严格模式）

    加载策略：
    - CI 环境: 加载 .env.test.ci (使用 localhost 端口映射)
    - DevContainer: 加载 .env.test.local (使用 Docker 服务名)

    严格模式：缺少配置文件直接报错，避免静默使用错误配置。
    """
    project_root = Path(__file__).parent.parent.parent

    if _IS_CI:
        # CI 环境：加载 .env.test.ci
        env_test_ci = project_root / ".env.test.ci"
        if not env_test_ci.exists():
            raise FileNotFoundError(
                f".env.test.ci not found at {env_test_ci}. "
                "This file is required for CI integration tests."
            )
        _load_env_file(env_test_ci)
        print("[CI] Loaded configuration from .env.test.ci")
        print(f"[CI] DATABASE_URL = {os.environ.get('DATABASE_URL')}")
        print(f"[CI] REDIS_URL = {os.environ.get('REDIS_URL')}")
    else:
        # DevContainer/本地环境：加载 .env.test.local（必须存在）
        env_test_local = project_root / ".env.test.local"

        if not env_test_local.exists():
            raise FileNotFoundError(
                f".env.test.local not found at {env_test_local}. "
                "Please create it from template: cp .env.test.local.example .env.test.local"
            )

        # 先加载 .env（获取敏感凭证如交易所 API keys）
        env_path = project_root / ".env"
        if env_path.exists():
            _load_env_file(env_path)

        # 再加载 .env.test.local（测试特定配置，会覆盖 .env 中的值）
        _load_env_file(env_test_local)
        print("[Local] Loaded configuration from .env.test.local")
        print(f"[Local] DATABASE_URL = {os.environ.get('DATABASE_URL')}")
        print(f"[Local] REDIS_URL = {os.environ.get('REDIS_URL')}")

    # 清除 get_settings 缓存以使用新的环境变量
    try:
        from squant.config import get_settings

        get_settings.cache_clear()
    except ImportError:
        pass  # squant.config 尚未导入


# 立即设置环境变量（conftest.py 在测试模块之前被导入）
_setup_test_environment()

from squant.config import get_settings  # noqa: E402
from squant.models.base import Base  # noqa: E402

# ============================================================================
# 测试环境配置
# ============================================================================


@pytest.fixture(scope="session")
def test_settings():
    """获取测试环境配置"""
    settings = get_settings()

    # Debug output for settings values
    db_url = (
        settings.database.url.get_secret_value()
        if hasattr(settings.database.url, "get_secret_value")
        else str(settings.database.url)
    )
    redis_url = (
        settings.redis.url.get_secret_value()
        if hasattr(settings.redis.url, "get_secret_value")
        else str(settings.redis.url)
    )
    print(f"[test_settings] database.url = {db_url}")
    print(f"[test_settings] redis.url = {redis_url}")

    # 确保使用测试数据库
    assert "test" in db_url, "Must use test database for integration tests"
    return settings


# ============================================================================
# 数据库Fixtures
# ============================================================================

# Note: Changed from session to function scope to avoid event loop conflicts


@pytest_asyncio.fixture
async def engine(test_settings):
    """创建测试数据库引擎"""
    db_url = (
        test_settings.database.url.get_secret_value()
        if hasattr(test_settings.database.url, "get_secret_value")
        else str(test_settings.database.url)
    )
    engine = create_async_engine(
        db_url,
        echo=False,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )

    # 创建所有表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # 测试结束后清理
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    """
    为每个测试提供独立的数据库session

    每个测试在独立的事务中运行，测试结束后自动回滚，确保测试隔离。
    注意：不使用session.begin()，允许测试内部调用commit()。
    """
    # 创建session maker
    async_session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_maker() as session:
        # 不使用session.begin() - 让测试自己管理事务
        yield session
        # 测试结束后回滚任何未提交的更改
        if session.in_transaction():
            await session.rollback()


@pytest_asyncio.fixture(scope="function")
async def clean_db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    """
    提供clean session（不自动回滚）

    用于需要真实提交数据的测试场景。
    测试结束后会清空所有表。
    """
    async_session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_maker() as session:
        yield session

    # 测试结束后清空所有表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


# ============================================================================
# Redis Fixtures
# ============================================================================


@pytest_asyncio.fixture
async def redis_client(test_settings) -> AsyncGenerator[Redis, None]:
    """创建Redis客户端"""
    redis_url = (
        test_settings.redis.url.get_secret_value()
        if hasattr(test_settings.redis.url, "get_secret_value")
        else str(test_settings.redis.url)
    )
    client = Redis.from_url(
        redis_url,
        encoding="utf-8",
        decode_responses=True,
    )

    # 验证连接
    await client.ping()

    yield client

    # 清理并关闭连接
    await client.flushdb()
    await client.aclose()


@pytest_asyncio.fixture(scope="function")
async def redis(redis_client) -> AsyncGenerator[Redis, None]:
    """
    为每个测试提供独立的Redis客户端

    测试结束后自动清理数据
    """
    yield redis_client

    # 测试结束后清空数据
    await redis_client.flushdb()


# ============================================================================
# 交易所客户端Fixtures（需要测试网凭证）
# ============================================================================


@pytest.fixture(scope="session")
def skip_if_no_exchange_credentials():
    """如果没有配置交易所凭证，跳过测试"""
    import os

    okx_key = os.getenv("OKX_API_KEY")
    if not okx_key:
        pytest.skip("OKX_API_KEY not set, skipping exchange integration tests")


@pytest_asyncio.fixture
async def okx_exchange(skip_if_no_exchange_credentials):
    """
    创建OKX测试网交易所客户端

    需要环境变量:
        - OKX_API_KEY
        - OKX_API_SECRET
        - OKX_PASSPHRASE
    """
    from squant.infra.exchange.ccxt.rest_adapter import CCXTRestAdapter

    adapter = CCXTRestAdapter(
        exchange_id="okx",
        config={
            "apiKey": os.getenv("OKX_API_KEY"),
            "secret": os.getenv("OKX_API_SECRET"),
            "password": os.getenv("OKX_PASSPHRASE"),
            "options": {
                "defaultType": "spot",
            },
        },
    )

    yield adapter

    # 关闭连接
    await adapter.close()


# ============================================================================
# 测试数据Fixtures
# ============================================================================


@pytest_asyncio.fixture
async def sample_strategy(db_session):
    """创建示例策略"""
    from uuid import uuid4

    from squant.models.strategy import Strategy

    strategy = Strategy(
        id=uuid4(),
        name="Test MA Strategy",
        code="""
def initialize(context):
    context.ma_period = 20

def handle_data(context, data):
    close_prices = data.history('close', context.ma_period)
    ma = close_prices.mean()
    current_price = data.current('close')

    if current_price > ma:
        context.order('BTC/USDT', 0.01)
    elif current_price < ma:
        context.order('BTC/USDT', -0.01)
""",
        description="Simple moving average strategy",
    )

    db_session.add(strategy)
    await db_session.commit()
    await db_session.refresh(strategy)

    return strategy


@pytest_asyncio.fixture
async def sample_exchange_account(db_session):
    """创建示例交易所账户"""
    import os
    from uuid import uuid4

    from squant.models.exchange import ExchangeAccount
    from squant.utils.crypto import get_crypto_manager

    # Generate a base nonce for derived nonce encryption
    crypto = get_crypto_manager()
    nonce = os.urandom(crypto.NONCE_SIZE)

    # Encrypt credentials using derived nonces (matches account service pattern)
    # Index: 0=api_key, 1=api_secret, 2=passphrase
    api_key_enc = crypto.encrypt_with_derived_nonce("test_api_key", nonce, index=0)
    api_secret_enc = crypto.encrypt_with_derived_nonce("test_api_secret", nonce, index=1)
    passphrase_enc = crypto.encrypt_with_derived_nonce("test_passphrase", nonce, index=2)

    account = ExchangeAccount(
        id=uuid4(),
        exchange="okx",
        name="Test Account",
        api_key_enc=api_key_enc,
        api_secret_enc=api_secret_enc,
        passphrase_enc=passphrase_enc,
        nonce=nonce,
        testnet=True,
    )

    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)

    return account


@pytest.fixture
def mock_exchange_adapter():
    """Create a mock exchange adapter for testing."""
    from unittest.mock import AsyncMock, MagicMock

    adapter = MagicMock()
    # Add async methods commonly used in tests
    adapter.get_balance = AsyncMock(return_value={"USDT": 10000.0})
    adapter.get_ticker = AsyncMock()
    adapter.get_tickers = AsyncMock()
    adapter.get_ohlcv = AsyncMock()
    adapter.create_order = AsyncMock()
    adapter.cancel_order = AsyncMock()
    adapter.get_order = AsyncMock()
    adapter.get_open_orders = AsyncMock()
    adapter.test_connection = AsyncMock(return_value=True)
    adapter.close = AsyncMock()

    return adapter


@pytest_asyncio.fixture
async def sample_backtest_run(db_session, sample_strategy):
    """创建示例回测运行"""
    from datetime import datetime, timedelta
    from uuid import uuid4

    from squant.models.backtest import BacktestRun
    from squant.models.enums import RunStatus

    run = BacktestRun(
        id=uuid4(),
        strategy_id=sample_strategy.id,
        exchange="okx",
        symbol="BTC/USDT",
        start_time=datetime.now() - timedelta(days=30),
        end_time=datetime.now(),
        initial_capital=10000.0,
        status=RunStatus.PENDING,
    )

    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    return run


# ============================================================================
# WebSocket Fixtures
# ============================================================================


@pytest_asyncio.fixture
async def websocket_manager(redis):
    """创建WebSocket管理器实例"""
    from squant.websocket.manager import StreamManager

    manager = StreamManager(redis_client=redis)

    yield manager

    # 清理
    await manager.cleanup()


# ============================================================================
# 测试工具函数
# ============================================================================


@pytest.fixture
def assert_no_db_leaks():
    """验证没有数据库连接泄漏"""

    async def _assert():
        # TODO: 实现连接池检查
        pass

    return _assert


@pytest.fixture
def wait_for_async_task():
    """等待异步任务完成的辅助函数"""

    async def _wait(task, timeout: float = 5.0):
        try:
            return await asyncio.wait_for(task, timeout=timeout)
        except TimeoutError:
            pytest.fail(f"Task did not complete within {timeout}s")

    return _wait


# ============================================================================
# 标记配置
# ============================================================================


def pytest_configure(config):
    """注册自定义标记"""
    config.addinivalue_line(
        "markers", "integration: Integration tests requiring database and Redis"
    )
    config.addinivalue_line("markers", "exchange: Tests requiring real exchange API credentials")
    config.addinivalue_line("markers", "slow: Slow running integration tests")


def pytest_collection_modifyitems(config, items):
    """自动为integration目录下的测试添加integration标记"""
    for item in items:
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
