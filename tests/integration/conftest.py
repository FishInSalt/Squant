"""
集成测试配置和fixtures

集成测试需要真实的数据库和Redis连接，使用docker-compose.test.yml启动测试环境。

运行集成测试前，请先启动测试环境:
    docker compose -f docker-compose.test.yml up -d

运行集成测试:
    uv run pytest tests/integration -v

停止测试环境:
    docker compose -f docker-compose.test.yml down -v
"""

import asyncio
import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from squant.config import get_settings
from squant.models.base import Base

# ============================================================================
# 测试环境配置
# ============================================================================


@pytest.fixture(scope="session")
def test_settings():
    """获取测试环境配置"""
    settings = get_settings()
    # 确保使用测试数据库
    db_url = (
        settings.database.url.get_secret_value()
        if hasattr(settings.database.url, "get_secret_value")
        else str(settings.database.url)
    )
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
