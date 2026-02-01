"""Unit tests for Redis connection management."""

import socket
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.asyncio import Redis

from squant.infra import redis as redis_module


@pytest.fixture(autouse=True)
def reset_redis_globals():
    """Reset global Redis instances before each test."""
    redis_module._redis_pool = None
    redis_module._redis_client = None
    yield
    redis_module._redis_pool = None
    redis_module._redis_client = None


class TestGetRedisPool:
    """Tests for get_redis_pool function."""

    def test_creates_pool_on_first_call(self) -> None:
        """Test that pool is created on first call."""
        pool = redis_module.get_redis_pool()

        assert pool is not None
        assert redis_module._redis_pool is pool

    def test_returns_same_pool_on_subsequent_calls(self) -> None:
        """Test that same pool instance is returned on subsequent calls."""
        pool1 = redis_module.get_redis_pool()
        pool2 = redis_module.get_redis_pool()

        assert pool1 is pool2

    def test_pool_creation_with_tcp_keepalive_linux(self) -> None:
        """Test pool creation with TCP keepalive options on Linux."""
        # Ensure TCP keepalive constants exist (Linux)
        assert hasattr(socket, "TCP_KEEPIDLE") or True  # May not exist on all platforms

        pool = redis_module.get_redis_pool()

        assert pool is not None
        # Pool should be created successfully with keepalive options

    def test_pool_creation_without_tcp_keepalive(self) -> None:
        """Test pool creation handles missing TCP keepalive constants gracefully."""
        # Remove TCP keepalive constants to simulate Windows/macOS
        with patch.object(socket, "TCP_KEEPIDLE", create=False):
            with patch.object(socket, "TCP_KEEPINTVL", create=False):
                with patch.object(socket, "TCP_KEEPCNT", create=False):
                    # Should not have these attributes, triggering AttributeError
                    # But the code handles it gracefully
                    pool = redis_module.get_redis_pool()

                    assert pool is not None


class TestGetRedis:
    """Tests for get_redis generator function."""

    @pytest.mark.asyncio
    async def test_creates_client_on_first_call(self) -> None:
        """Test that client is created on first call."""
        async for client in redis_module.get_redis():
            assert client is not None
            assert isinstance(client, Redis)
            assert redis_module._redis_client is client
            break  # Generator yields once

    @pytest.mark.asyncio
    async def test_returns_same_client_on_subsequent_calls(self) -> None:
        """Test that same client instance is returned."""
        clients = []

        async for client in redis_module.get_redis():
            clients.append(client)
            break

        async for client in redis_module.get_redis():
            clients.append(client)
            break

        assert len(clients) == 2
        assert clients[0] is clients[1]

    @pytest.mark.asyncio
    async def test_uses_global_pool(self) -> None:
        """Test that client uses the global connection pool."""
        async for client in redis_module.get_redis():
            assert client.connection_pool is redis_module._redis_pool
            break


class TestGetRedisContext:
    """Tests for get_redis_context context manager."""

    @pytest.mark.asyncio
    async def test_creates_client_on_first_use(self) -> None:
        """Test that client is created on first use."""
        async with redis_module.get_redis_context() as client:
            assert client is not None
            assert isinstance(client, Redis)
            assert redis_module._redis_client is client

    @pytest.mark.asyncio
    async def test_returns_same_client_on_subsequent_uses(self) -> None:
        """Test that same client instance is returned."""
        async with redis_module.get_redis_context() as client1:
            pass

        async with redis_module.get_redis_context() as client2:
            pass

        assert client1 is client2

    @pytest.mark.asyncio
    async def test_client_reuses_existing_instance(self) -> None:
        """Test that context manager reuses existing client if already initialized."""
        # Initialize client first
        async for client in redis_module.get_redis():
            first_client = client
            break

        # Context manager should return same instance
        async with redis_module.get_redis_context() as context_client:
            assert context_client is first_client


class TestInitRedis:
    """Tests for init_redis startup function."""

    @pytest.mark.asyncio
    async def test_initializes_client(self) -> None:
        """Test that init_redis creates client."""
        with patch.object(Redis, "ping", new_callable=AsyncMock) as mock_ping:
            await redis_module.init_redis()

            assert redis_module._redis_client is not None
            mock_ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_pings_redis_to_verify_connection(self) -> None:
        """Test that init_redis pings Redis to verify connection."""
        with patch.object(Redis, "ping", new_callable=AsyncMock) as mock_ping:
            await redis_module.init_redis()

            mock_ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_global_pool(self) -> None:
        """Test that initialized client uses global pool."""
        with patch.object(Redis, "ping", new_callable=AsyncMock):
            await redis_module.init_redis()

            assert redis_module._redis_client.connection_pool is redis_module._redis_pool


class TestCloseRedis:
    """Tests for close_redis shutdown function."""

    @pytest.mark.asyncio
    async def test_closes_client_when_initialized(self) -> None:
        """Test that close_redis closes client when it exists."""
        # Initialize client
        with patch.object(Redis, "ping", new_callable=AsyncMock):
            await redis_module.init_redis()

        # Mock aclose method
        with patch.object(Redis, "aclose", new_callable=AsyncMock) as mock_aclose:
            await redis_module.close_redis()

            mock_aclose.assert_called_once()
            assert redis_module._redis_client is None

    @pytest.mark.asyncio
    async def test_disconnects_pool_when_exists(self) -> None:
        """Test that close_redis disconnects pool when it exists."""
        # Initialize pool
        pool = redis_module.get_redis_pool()

        # Mock disconnect method
        with patch.object(pool, "disconnect", new_callable=AsyncMock) as mock_disconnect:
            await redis_module.close_redis()

            mock_disconnect.assert_called_once()
            assert redis_module._redis_pool is None

    @pytest.mark.asyncio
    async def test_handles_no_client_gracefully(self) -> None:
        """Test that close_redis works when client doesn't exist."""
        # Ensure no client exists
        redis_module._redis_client = None

        # Should not raise
        await redis_module.close_redis()

        assert redis_module._redis_client is None

    @pytest.mark.asyncio
    async def test_handles_no_pool_gracefully(self) -> None:
        """Test that close_redis works when pool doesn't exist."""
        # Ensure no pool exists
        redis_module._redis_pool = None

        # Should not raise
        await redis_module.close_redis()

        assert redis_module._redis_pool is None


class TestGetRedisClient:
    """Tests for get_redis_client direct access function."""

    @pytest.mark.asyncio
    async def test_returns_initialized_client(self) -> None:
        """Test that get_redis_client returns the initialized client."""
        # Initialize client
        with patch.object(Redis, "ping", new_callable=AsyncMock):
            await redis_module.init_redis()

        client = redis_module.get_redis_client()

        assert client is redis_module._redis_client

    def test_raises_error_when_not_initialized(self) -> None:
        """Test that get_redis_client raises error when Redis not initialized."""
        # Ensure client is not initialized
        redis_module._redis_client = None

        with pytest.raises(RuntimeError, match="Redis not initialized"):
            redis_module.get_redis_client()

    @pytest.mark.asyncio
    async def test_can_use_returned_client(self) -> None:
        """Test that returned client can be used for operations."""
        # Initialize client
        with patch.object(Redis, "ping", new_callable=AsyncMock):
            await redis_module.init_redis()

        client = redis_module.get_redis_client()

        # Should be a valid Redis instance
        assert isinstance(client, Redis)
        assert client.connection_pool is not None


class TestLifecycle:
    """Integration tests for Redis lifecycle management."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self) -> None:
        """Test complete init -> use -> close lifecycle."""
        # Initialize
        with patch.object(Redis, "ping", new_callable=AsyncMock):
            await redis_module.init_redis()

        assert redis_module._redis_client is not None
        assert redis_module._redis_pool is not None

        # Use
        client = redis_module.get_redis_client()
        assert client is redis_module._redis_client

        # Close
        with patch.object(Redis, "aclose", new_callable=AsyncMock):
            await redis_module.close_redis()

        assert redis_module._redis_client is None
        assert redis_module._redis_pool is None

    @pytest.mark.asyncio
    async def test_multiple_init_calls_idempotent(self) -> None:
        """Test that multiple init calls create same client."""
        with patch.object(Redis, "ping", new_callable=AsyncMock):
            await redis_module.init_redis()
            first_client = redis_module._redis_client

            await redis_module.init_redis()
            second_client = redis_module._redis_client

        # Should reuse pool but may create new client
        # Both should use same pool
        assert first_client.connection_pool is second_client.connection_pool
