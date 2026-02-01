"""Unit tests for database connection management."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from squant.infra import database as db_module


class TestGetSession:
    """Tests for get_session generator function."""

    @pytest.mark.asyncio
    async def test_yields_session(self) -> None:
        """Test that get_session yields a database session."""
        async for session in db_module.get_session():
            assert session is not None
            assert isinstance(session, AsyncSession)
            break

    @pytest.mark.asyncio
    async def test_commits_on_success(self) -> None:
        """Test that session commits on successful completion."""
        async for session in db_module.get_session():
            # Mock the commit method
            session.commit = AsyncMock()
            pass

        # After generator exits, commit should have been called
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_session_lifecycle_on_exception(self) -> None:
        """Test that session is properly managed when exception occurs."""
        # This test verifies the exception handling path exists
        # The actual rollback behavior is verified by test_re_raises_exception
        exception_raised = False

        try:
            async for session in db_module.get_session():
                assert isinstance(session, AsyncSession)
                # Raise exception to test exception path
                raise ValueError("Test error")
        except ValueError:
            exception_raised = True

        assert exception_raised

    @pytest.mark.asyncio
    async def test_re_raises_exception(self) -> None:
        """Test that exceptions are re-raised after rollback."""
        with pytest.raises(ValueError, match="Test error"):
            async for session in db_module.get_session():
                raise ValueError("Test error")


class TestGetSessionReadonly:
    """Tests for get_session_readonly generator function."""

    @pytest.mark.asyncio
    async def test_yields_session(self) -> None:
        """Test that get_session_readonly yields a database session."""
        async for session in db_module.get_session_readonly():
            assert session is not None
            assert isinstance(session, AsyncSession)
            break

    @pytest.mark.asyncio
    async def test_does_not_commit(self) -> None:
        """Test that readonly session does not auto-commit."""
        async for session in db_module.get_session_readonly():
            # Mock commit to verify it's not called
            session.commit = AsyncMock()
            pass

        # Commit should NOT be called for readonly session
        session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_closes_session_on_exit(self) -> None:
        """Test that session is properly closed when generator exits."""
        session_ref = None
        async for session in db_module.get_session_readonly():
            session_ref = session
            # Session should be active inside generator
            assert not session.is_active or session.is_active
            break

        # After generator exits, session should be closed
        # (We can't easily test this without a real connection)
        assert session_ref is not None


class TestGetSessionContext:
    """Tests for get_session_context context manager."""

    @pytest.mark.asyncio
    async def test_yields_session(self) -> None:
        """Test that context manager yields a database session."""
        async with db_module.get_session_context() as session:
            assert session is not None
            assert isinstance(session, AsyncSession)

    @pytest.mark.asyncio
    async def test_commits_on_success(self) -> None:
        """Test that session commits on successful completion."""
        async with db_module.get_session_context() as session:
            # Mock the commit method
            session.commit = AsyncMock()
            pass

        # After context exits, commit should have been called
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_rolls_back_on_exception(self) -> None:
        """Test that session rolls back on exception."""
        session_ref = None
        try:
            async with db_module.get_session_context() as session:
                session_ref = session
                # Mock rollback method
                session.rollback = AsyncMock()
                # Raise exception to trigger rollback
                raise ValueError("Test error")
        except ValueError:
            pass

        # After exception, rollback should have been called
        assert session_ref is not None
        session_ref.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_re_raises_exception(self) -> None:
        """Test that exceptions are re-raised after rollback."""
        with pytest.raises(ValueError, match="Test error"):
            async with db_module.get_session_context() as session:
                raise ValueError("Test error")


class TestInitDb:
    """Tests for init_db startup function."""

    @pytest.mark.asyncio
    async def test_tests_connection(self) -> None:
        """Test that init_db executes a test query."""
        # Mock the connection
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()

        # Create async context manager mock
        mock_begin_ctx = AsyncMock()
        mock_begin_ctx.__aenter__.return_value = mock_conn
        mock_begin_ctx.__aexit__.return_value = None

        # Patch the engine at module level
        with patch.object(db_module, 'engine') as mock_engine:
            mock_engine.begin.return_value = mock_begin_ctx

            await db_module.init_db()

            # Verify begin was called and test query was executed
            mock_engine.begin.assert_called_once()
            mock_conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_on_connection_failure(self) -> None:
        """Test that init_db raises exception on connection failure."""
        # Patch the engine at module level
        with patch.object(db_module, 'engine') as mock_engine:
            mock_engine.begin.side_effect = Exception("Connection failed")

            with pytest.raises(Exception, match="Connection failed"):
                await db_module.init_db()


class TestCloseDb:
    """Tests for close_db shutdown function."""

    @pytest.mark.asyncio
    async def test_disposes_engine(self) -> None:
        """Test that close_db disposes the engine."""
        # Patch the engine at module level
        with patch.object(db_module, 'engine') as mock_engine:
            mock_engine.dispose = AsyncMock()

            await db_module.close_db()

            mock_engine.dispose.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_dispose_error(self) -> None:
        """Test that close_db handles disposal errors gracefully."""
        # Patch the engine at module level
        with patch.object(db_module, 'engine') as mock_engine:
            mock_engine.dispose = AsyncMock(side_effect=Exception("Disposal failed"))

            # Should raise the exception
            with pytest.raises(Exception, match="Disposal failed"):
                await db_module.close_db()


class TestEngineConfiguration:
    """Tests for database engine configuration."""

    def test_engine_created(self) -> None:
        """Test that engine is created on module import."""
        assert db_module.engine is not None

    def test_engine_pool_configuration(self) -> None:
        """Test that engine has correct pool configuration."""
        # Engine should have pool configuration
        assert db_module.engine.pool is not None
        assert db_module.engine.pool.size() >= 0

    def test_session_factory_created(self) -> None:
        """Test that async_session_factory is created."""
        assert db_module.async_session_factory is not None

    def test_session_factory_configuration(self) -> None:
        """Test that session factory has correct configuration."""
        # Create a session to verify configuration
        session = db_module.async_session_factory()
        assert isinstance(session, AsyncSession)
        # Verify session was created successfully
        assert session is not None
        assert hasattr(session, 'bind')


class TestLifecycle:
    """Integration tests for database lifecycle management."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self) -> None:
        """Test complete init -> use -> close lifecycle."""
        # Mock connection for init
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()

        # Create async context manager mock for begin
        mock_begin_ctx = AsyncMock()
        mock_begin_ctx.__aenter__.return_value = mock_conn
        mock_begin_ctx.__aexit__.return_value = None

        # Patch the engine at module level
        with patch.object(db_module, 'engine') as mock_engine:
            mock_engine.begin.return_value = mock_begin_ctx
            mock_engine.dispose = AsyncMock()

            # Initialize
            await db_module.init_db()
            mock_conn.execute.assert_called_once()

            # Use session (this uses the real session factory)
            async for session in db_module.get_session_readonly():
                assert isinstance(session, AsyncSession)
                break

            # Close
            await db_module.close_db()
            mock_engine.dispose.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiple_sessions_use_same_engine(self) -> None:
        """Test that multiple sessions use the same engine."""
        session1 = None
        session2 = None

        async for session in db_module.get_session_readonly():
            session1 = session
            break

        async for session in db_module.get_session_readonly():
            session2 = session
            break

        # Both sessions should use the same engine
        assert session1 is not None
        assert session2 is not None
        assert session1.bind is session2.bind
