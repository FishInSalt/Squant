"""
Unit test fixtures for Squant.

This module provides shared fixtures for all unit tests. These fixtures are
automatically discovered by pytest and available to all tests under tests/unit/.

Fixture Categories:
    - Database: Mock database sessions and related utilities
    - Exchange: Mock exchange adapters with common async methods
    - Redis: Mock Redis clients with pub/sub support
    - Settings: Mock configuration settings
    - Data: Common test data objects (tickers, candles, orders, etc.)

Usage:
    Fixtures defined here are automatically available to all unit tests.
    Import additional fixtures from sub-modules as needed:

        # In tests/unit/api/conftest.py
        from tests.unit.conftest import mock_session, mock_exchange

        # In test files, just use the fixture name directly
        def test_example(mock_session, mock_exchange):
            ...

Notes:
    - All fixtures use MagicMock/AsyncMock to avoid real I/O
    - Original fixtures in individual test files are preserved for backward compatibility
    - New tests should prefer using these shared fixtures
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from squant.infra.exchange.types import Candlestick, Ticker


# ============================================================================
# Database Fixtures
# ============================================================================


@pytest.fixture
def mock_db_session():
    """
    Create a mock async database session.

    Provides a MagicMock with common SQLAlchemy async session methods:
        - execute: AsyncMock for query execution
        - commit: AsyncMock for transaction commit
        - rollback: AsyncMock for transaction rollback
        - refresh: AsyncMock for refreshing object state
        - add: MagicMock for adding objects to session
        - delete: AsyncMock for deleting objects
        - get: AsyncMock for getting objects by primary key
        - scalars: MagicMock for returning ScalarResult

    Returns:
        MagicMock: Mock database session

    Example:
        def test_create_record(mock_db_session):
            mock_db_session.execute.return_value = ...
            # Test code using session
    """
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.delete = AsyncMock()
    session.get = AsyncMock()
    session.scalars = MagicMock()
    session.scalar = AsyncMock()

    # Configure scalars to return a mock with common methods
    scalar_result = MagicMock()
    scalar_result.first = MagicMock(return_value=None)
    scalar_result.all = MagicMock(return_value=[])
    scalar_result.one_or_none = MagicMock(return_value=None)
    session.scalars.return_value = scalar_result

    return session


# ============================================================================
# Exchange Fixtures
# ============================================================================


@pytest.fixture
def mock_exchange_adapter():
    """
    Create a mock exchange adapter with common async methods.

    Provides a MagicMock with all standard exchange adapter methods:
        Market Data:
            - get_ticker: Get single ticker
            - get_tickers: Get multiple tickers
            - get_candlesticks: Get OHLCV data
            - get_orderbook: Get order book

        Trading:
            - create_order: Place order
            - cancel_order: Cancel order
            - get_order: Get order details
            - get_open_orders: Get all open orders

        Account:
            - get_balance: Get account balance
            - get_balance_currency: Get single currency balance
            - get_positions: Get open positions

        Connection:
            - test_connection: Test API connectivity
            - close: Close connection

    Returns:
        MagicMock: Mock exchange adapter

    Example:
        def test_get_ticker(mock_exchange_adapter):
            mock_exchange_adapter.get_ticker.return_value = mock_ticker
            # Test code using exchange
    """
    exchange = MagicMock()

    # Market data methods
    exchange.get_ticker = AsyncMock()
    exchange.get_tickers = AsyncMock()
    exchange.get_candlesticks = AsyncMock()
    exchange.get_orderbook = AsyncMock()

    # Trading methods
    exchange.create_order = AsyncMock()
    exchange.cancel_order = AsyncMock()
    exchange.get_order = AsyncMock()
    exchange.get_open_orders = AsyncMock()
    exchange.get_order_history = AsyncMock()

    # Account methods
    exchange.get_balance = AsyncMock()
    exchange.get_balance_currency = AsyncMock()
    exchange.get_positions = AsyncMock()

    # Connection methods
    exchange.test_connection = AsyncMock(return_value=True)
    exchange.close = AsyncMock()

    return exchange


# ============================================================================
# Redis Fixtures
# ============================================================================


@pytest.fixture
def mock_redis_client():
    """
    Create a mock Redis client with common async methods.

    Provides a MagicMock with:
        Basic Operations:
            - get/set/delete: Key-value operations
            - exists: Check key existence
            - expire: Set key expiration

        Pub/Sub:
            - publish: Publish message to channel
            - pubsub: Get pub/sub instance
            - subscribe/unsubscribe: Channel subscription

        Pipeline:
            - pipeline: Get pipeline for batched operations

    Returns:
        MagicMock: Mock Redis client

    Example:
        async def test_publish(mock_redis_client):
            await mock_redis_client.publish("channel", "message")
            mock_redis_client.publish.assert_called_once()
    """
    redis = AsyncMock()

    # Basic operations
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=1)
    redis.exists = AsyncMock(return_value=0)
    redis.expire = AsyncMock(return_value=True)
    redis.keys = AsyncMock(return_value=[])

    # Pub/sub
    redis.publish = AsyncMock(return_value=1)

    # Create mock pubsub
    pubsub = AsyncMock()
    pubsub.subscribe = AsyncMock()
    pubsub.unsubscribe = AsyncMock()
    pubsub.ping = AsyncMock()
    pubsub.get_message = AsyncMock(return_value=None)
    redis.pubsub = MagicMock(return_value=pubsub)

    # Pipeline
    pipeline = AsyncMock()
    pipeline.publish = MagicMock(return_value=pipeline)
    pipeline.execute = AsyncMock(return_value=[1, 1, 1])
    redis.pipeline = MagicMock(return_value=pipeline)

    return redis


@pytest.fixture
def mock_redis_pubsub(mock_redis_client):
    """
    Get the mock pub/sub instance from mock_redis_client.

    This is a convenience fixture that extracts the pubsub from the
    mock_redis_client fixture.

    Returns:
        AsyncMock: Mock pub/sub instance
    """
    return mock_redis_client.pubsub()


# ============================================================================
# Settings Fixtures
# ============================================================================


@pytest.fixture
def mock_settings():
    """
    Create mock application settings.

    Provides a MagicMock with common settings attributes:
        - use_ccxt_provider: True (default to CCXT)
        - default_exchange: "okx"
        - Exchange credentials (as SecretStr mocks)
        - Testnet flags

    Returns:
        MagicMock: Mock settings object

    Example:
        def test_with_binance(mock_settings):
            mock_settings.default_exchange = "binance"
            # Test code
    """
    settings = MagicMock()
    settings.use_ccxt_provider = True
    settings.default_exchange = "okx"

    # OKX credentials
    settings.okx_api_key = MagicMock()
    settings.okx_api_key.get_secret_value.return_value = "test-okx-key"
    settings.okx_api_secret = MagicMock()
    settings.okx_api_secret.get_secret_value.return_value = "test-okx-secret"
    settings.okx_passphrase = MagicMock()
    settings.okx_passphrase.get_secret_value.return_value = "test-okx-passphrase"
    settings.okx_testnet = True

    # Binance credentials (not configured by default)
    settings.binance_api_key = None
    settings.binance_api_secret = None
    settings.binance_testnet = False

    # Bybit credentials (not configured by default)
    settings.bybit_api_key = None
    settings.bybit_api_secret = None
    settings.bybit_testnet = False

    return settings


# ============================================================================
# Market Data Fixtures
# ============================================================================


@pytest.fixture
def sample_ticker():
    """
    Create a sample Ticker object for testing.

    Returns a Ticker with realistic BTC/USDT market data:
        - symbol: "BTC/USDT"
        - last: 42000.5
        - bid/ask spread: 42000.0 / 42001.0
        - 24h range: 41000.0 - 43000.0
        - 24h volume: 1000.0 BTC

    Returns:
        Ticker: Sample ticker data
    """
    from squant.infra.exchange.types import Ticker

    return Ticker(
        symbol="BTC/USDT",
        last=42000.5,
        bid=42000.0,
        ask=42001.0,
        high_24h=43000.0,
        low_24h=41000.0,
        volume_24h=1000.0,
        volume_quote_24h=42000000.0,
        change_24h=500.0,
        change_pct_24h=1.2,
        timestamp=datetime.now(UTC),
    )


@pytest.fixture
def sample_candles():
    """
    Create a list of sample Candlestick objects for testing.

    Returns a list of 2 candlesticks with realistic OHLCV data:
        - Bullish candle: 42000 -> 42050
        - Continuation: 42050 -> 42100

    Returns:
        list[Candlestick]: List of sample candlesticks
    """
    from squant.infra.exchange.types import Candlestick

    now = datetime.now(UTC)
    return [
        Candlestick(
            timestamp=now,
            open=42000.0,
            high=42100.0,
            low=41900.0,
            close=42050.0,
            volume=100.0,
        ),
        Candlestick(
            timestamp=now,
            open=42050.0,
            high=42150.0,
            low=42000.0,
            close=42100.0,
            volume=150.0,
        ),
    ]


@pytest.fixture
def sample_eth_ticker():
    """
    Create a sample ETH/USDT Ticker for testing multiple symbols.

    Returns:
        Ticker: Sample ETH ticker data
    """
    from squant.infra.exchange.types import Ticker

    return Ticker(
        symbol="ETH/USDT",
        last=2500.0,
        bid=2499.0,
        ask=2501.0,
        high_24h=2600.0,
        low_24h=2400.0,
        volume_24h=5000.0,
        volume_quote_24h=12500000.0,
        change_24h=50.0,
        change_pct_24h=2.0,
        timestamp=datetime.now(UTC),
    )


# ============================================================================
# Order Fixtures
# ============================================================================


@pytest.fixture
def sample_order():
    """
    Create a sample Order mock object for testing.

    Returns a MagicMock configured as a filled BTC/USDT limit buy order:
        - symbol: "BTC/USDT"
        - side: BUY
        - type: LIMIT
        - status: FILLED
        - price: 50000
        - amount: 0.1

    Returns:
        MagicMock: Mock order object
    """
    from squant.models.enums import OrderSide, OrderStatus, OrderType

    order = MagicMock()
    order.id = str(uuid4())
    order.account_id = str(uuid4())
    order.run_id = None
    order.exchange = "okx"
    order.exchange_oid = "EXC123456"
    order.symbol = "BTC/USDT"
    order.side = OrderSide.BUY
    order.type = OrderType.LIMIT
    order.status = OrderStatus.FILLED
    order.price = Decimal("50000")
    order.amount = Decimal("0.1")
    order.filled = Decimal("0.1")
    order.avg_price = Decimal("50000")
    order.reject_reason = None
    order.created_at = datetime.now(UTC)
    order.updated_at = datetime.now(UTC)
    order.trades = []
    return order


@pytest.fixture
def sample_trade():
    """
    Create a sample Trade mock object for testing.

    Returns a MagicMock configured as a trade execution:
        - price: 50000
        - amount: 0.1
        - fee: 0.5 USDT

    Returns:
        MagicMock: Mock trade object
    """
    trade = MagicMock()
    trade.id = str(uuid4())
    trade.order_id = str(uuid4())
    trade.exchange_tid = "TRD123456"
    trade.price = Decimal("50000")
    trade.amount = Decimal("0.1")
    trade.fee = Decimal("0.5")
    trade.fee_currency = "USDT"
    trade.timestamp = datetime.now(UTC)
    return trade


@pytest.fixture
def valid_order_request():
    """
    Create a valid order creation request dict for API testing.

    Returns:
        dict: Valid order request payload
    """
    return {
        "symbol": "BTC/USDT",
        "side": "buy",
        "type": "limit",
        "amount": "0.1",
        "price": "50000",
    }


# ============================================================================
# Strategy and Backtest Fixtures
# ============================================================================


@pytest.fixture
def sample_strategy():
    """
    Create a sample Strategy mock object for testing.

    Returns:
        MagicMock: Mock strategy object
    """
    from squant.models.enums import StrategyStatus

    strategy = MagicMock()
    strategy.id = uuid4()
    strategy.name = "Test MA Strategy"
    strategy.code = """
def initialize(context):
    context.ma_period = 20

def handle_data(context, data):
    pass
"""
    strategy.description = "Simple moving average strategy for testing"
    strategy.status = StrategyStatus.ACTIVE
    strategy.created_at = datetime.now(UTC)
    strategy.updated_at = datetime.now(UTC)
    return strategy


@pytest.fixture
def sample_backtest_run(sample_strategy):
    """
    Create a sample BacktestRun mock object for testing.

    Args:
        sample_strategy: Strategy fixture for linking

    Returns:
        MagicMock: Mock backtest run object
    """
    from squant.models.enums import RunStatus

    run = MagicMock()
    run.id = uuid4()
    run.strategy_id = sample_strategy.id
    run.mode = "backtest"
    run.symbol = "BTC/USDT"
    run.exchange = "okx"
    run.timeframe = "1h"
    run.backtest_start = datetime(2024, 1, 1, tzinfo=UTC)
    run.backtest_end = datetime(2024, 6, 1, tzinfo=UTC)
    run.initial_capital = 10000.0
    run.commission_rate = 0.001
    run.slippage = 0.0005
    run.params = {}
    run.status = RunStatus.COMPLETED.value
    run.result = {"total_return": 0.2, "max_drawdown": 0.1}
    run.error_message = None
    run.started_at = datetime.now(UTC)
    run.stopped_at = datetime.now(UTC)
    run.created_at = datetime.now(UTC)
    run.updated_at = datetime.now(UTC)
    return run


@pytest.fixture
def valid_backtest_request():
    """
    Create a valid backtest run request dict for API testing.

    Returns:
        dict: Valid backtest request payload
    """
    return {
        "strategy_id": str(uuid4()),
        "symbol": "BTC/USDT",
        "exchange": "okx",
        "timeframe": "1h",
        "start_date": "2024-01-01T00:00:00Z",
        "end_date": "2024-06-01T00:00:00Z",
        "initial_capital": 10000.0,
        "commission_rate": 0.001,
        "slippage": 0.0005,
    }


# ============================================================================
# Account Fixtures
# ============================================================================


@pytest.fixture
def sample_account_balance():
    """
    Create a sample AccountBalance object for testing.

    Returns:
        AccountBalance: Sample account balance with BTC, ETH, USDT
    """
    from squant.infra.exchange.types import AccountBalance, Balance

    return AccountBalance(
        exchange="okx",
        balances=[
            Balance(currency="BTC", available=1.5, frozen=0.5),
            Balance(currency="USDT", available=10000.0, frozen=500.0),
            Balance(currency="ETH", available=5.0, frozen=0.0),
        ],
        timestamp=datetime.now(UTC),
    )


@pytest.fixture
def sample_balance():
    """
    Create a sample single Balance object for testing.

    Returns:
        Balance: Sample BTC balance
    """
    from squant.infra.exchange.types import Balance

    return Balance(currency="BTC", available=1.5, frozen=0.5)


# ============================================================================
# Exchange Account Fixtures
# ============================================================================


@pytest.fixture
def sample_exchange_account():
    """
    Create a sample ExchangeAccount mock object for testing.

    Returns:
        MagicMock: Mock exchange account object
    """
    account = MagicMock()
    account.id = uuid4()
    account.exchange = "okx"
    account.name = "Test Account"
    account.api_key_enc = b"encrypted_key"
    account.api_secret_enc = b"encrypted_secret"
    account.passphrase_enc = b"encrypted_passphrase"
    account.nonce = b"random_nonce"
    account.testnet = True
    account.is_active = True
    account.created_at = datetime.now(UTC)
    account.updated_at = datetime.now(UTC)
    return account
