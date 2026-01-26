"""Unit tests for strategy service."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from squant.models.enums import StrategyStatus
from squant.models.strategy import Strategy
from squant.schemas.strategy import CreateStrategyRequest, UpdateStrategyRequest
from squant.services.strategy import (
    StrategyNameExistsError,
    StrategyNotFoundError,
    StrategyRepository,
    StrategyService,
    StrategyValidationError,
)


# Valid strategy code for tests
VALID_STRATEGY_CODE = '''
class TestStrategy(Strategy):
    """A test strategy."""

    def on_bar(self, bar):
        pass
'''

# Invalid strategy code (missing on_bar)
INVALID_STRATEGY_CODE = '''
class TestStrategy(Strategy):
    def do_something(self):
        pass
'''

# Malicious strategy code
MALICIOUS_CODE = '''
import os

class TestStrategy(Strategy):
    def on_bar(self, bar):
        os.system("rm -rf /")
'''


class TestStrategyRepository:
    """Tests for StrategyRepository."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create a mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        return session

    @pytest.fixture
    def repository(self, mock_session: AsyncMock) -> StrategyRepository:
        """Create a repository with mock session."""
        return StrategyRepository(mock_session)

    @pytest.mark.asyncio
    async def test_get_by_name_found(
        self, repository: StrategyRepository, mock_session: AsyncMock
    ) -> None:
        """Test getting a strategy by name when it exists."""
        mock_strategy = MagicMock(spec=Strategy)
        mock_strategy.name = "TestStrategy"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_strategy
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_name("TestStrategy")
        assert result == mock_strategy

    @pytest.mark.asyncio
    async def test_get_by_name_not_found(
        self, repository: StrategyRepository, mock_session: AsyncMock
    ) -> None:
        """Test getting a strategy by name when it doesn't exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_name("NonExistent")
        assert result is None


class TestStrategyService:
    """Tests for StrategyService."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create a mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.fixture
    def service(self, mock_session: AsyncMock) -> StrategyService:
        """Create a service with mock session."""
        return StrategyService(mock_session)

    @pytest.mark.asyncio
    async def test_create_success(
        self, service: StrategyService, mock_session: AsyncMock
    ) -> None:
        """Test successful strategy creation."""
        request = CreateStrategyRequest(
            name="TestStrategy",
            code=VALID_STRATEGY_CODE,
            description="A test strategy",
        )

        mock_strategy = MagicMock(spec=Strategy)
        mock_strategy.id = str(uuid4())
        mock_strategy.name = request.name

        # Mock get_by_name to return None (name doesn't exist)
        with patch.object(
            service.repository, "get_by_name", new_callable=AsyncMock
        ) as mock_get_by_name:
            mock_get_by_name.return_value = None

            with patch.object(
                service.repository, "create", new_callable=AsyncMock
            ) as mock_create:
                mock_create.return_value = mock_strategy

                result = await service.create(request)
                assert result == mock_strategy
                mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_name_exists(
        self, service: StrategyService
    ) -> None:
        """Test that duplicate name raises error."""
        request = CreateStrategyRequest(
            name="ExistingStrategy",
            code=VALID_STRATEGY_CODE,
        )

        with patch.object(
            service.repository, "get_by_name", new_callable=AsyncMock
        ) as mock_get_by_name:
            mock_get_by_name.return_value = MagicMock(spec=Strategy)

            with pytest.raises(StrategyNameExistsError):
                await service.create(request)

    @pytest.mark.asyncio
    async def test_create_validation_error(
        self, service: StrategyService
    ) -> None:
        """Test that invalid code raises validation error."""
        request = CreateStrategyRequest(
            name="BadStrategy",
            code=MALICIOUS_CODE,
        )

        with patch.object(
            service.repository, "get_by_name", new_callable=AsyncMock
        ) as mock_get_by_name:
            mock_get_by_name.return_value = None

            with pytest.raises(StrategyValidationError) as exc_info:
                await service.create(request)

            assert len(exc_info.value.errors) > 0

    @pytest.mark.asyncio
    async def test_get_found(self, service: StrategyService) -> None:
        """Test getting a strategy that exists."""
        strategy_id = uuid4()
        mock_strategy = MagicMock(spec=Strategy)
        mock_strategy.id = str(strategy_id)

        with patch.object(
            service.repository, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = mock_strategy

            result = await service.get(strategy_id)
            assert result == mock_strategy

    @pytest.mark.asyncio
    async def test_get_not_found(self, service: StrategyService) -> None:
        """Test getting a strategy that doesn't exist."""
        strategy_id = uuid4()

        with patch.object(
            service.repository, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = None

            with pytest.raises(StrategyNotFoundError):
                await service.get(strategy_id)

    @pytest.mark.asyncio
    async def test_delete_success(
        self, service: StrategyService, mock_session: AsyncMock
    ) -> None:
        """Test successful strategy deletion."""
        strategy_id = uuid4()

        with patch.object(
            service.repository, "exists", new_callable=AsyncMock
        ) as mock_exists:
            mock_exists.return_value = True

            with patch.object(
                service.repository, "delete", new_callable=AsyncMock
            ) as mock_delete:
                mock_delete.return_value = True

                await service.delete(strategy_id)
                mock_delete.assert_called_once_with(strategy_id)
                mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_not_found(self, service: StrategyService) -> None:
        """Test deleting a strategy that doesn't exist."""
        strategy_id = uuid4()

        with patch.object(
            service.repository, "exists", new_callable=AsyncMock
        ) as mock_exists:
            mock_exists.return_value = False

            with pytest.raises(StrategyNotFoundError):
                await service.delete(strategy_id)

    @pytest.mark.asyncio
    async def test_update_success(
        self, service: StrategyService, mock_session: AsyncMock
    ) -> None:
        """Test successful strategy update."""
        strategy_id = uuid4()
        mock_strategy = MagicMock(spec=Strategy)
        mock_strategy.id = str(strategy_id)
        mock_strategy.name = "OldName"
        mock_strategy.version = "1.0.0"

        request = UpdateStrategyRequest(name="NewName")

        with patch.object(
            service.repository, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = mock_strategy

            with patch.object(
                service.repository, "get_by_name", new_callable=AsyncMock
            ) as mock_get_by_name:
                mock_get_by_name.return_value = None

                with patch.object(
                    service.repository, "update", new_callable=AsyncMock
                ) as mock_update:
                    mock_update.return_value = mock_strategy

                    result = await service.update(strategy_id, request)
                    assert result == mock_strategy

    @pytest.mark.asyncio
    async def test_update_code_increments_version(
        self, service: StrategyService, mock_session: AsyncMock
    ) -> None:
        """Test that updating code increments version."""
        strategy_id = uuid4()
        mock_strategy = MagicMock(spec=Strategy)
        mock_strategy.id = str(strategy_id)
        mock_strategy.name = "TestStrategy"
        mock_strategy.version = "1.0.0"

        request = UpdateStrategyRequest(code=VALID_STRATEGY_CODE)

        with patch.object(
            service.repository, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = mock_strategy

            with patch.object(
                service.repository, "update", new_callable=AsyncMock
            ) as mock_update:
                mock_update.return_value = mock_strategy

                await service.update(strategy_id, request)

                # Check that version was incremented in update call
                call_kwargs = mock_update.call_args[1]
                assert call_kwargs["version"] == "1.0.1"

    def test_validate_code(self, service: StrategyService) -> None:
        """Test code validation without saving."""
        # Valid code
        result = service.validate_code(VALID_STRATEGY_CODE)
        assert result.valid is True

        # Invalid code
        result = service.validate_code(MALICIOUS_CODE)
        assert result.valid is False


class TestStrategyErrors:
    """Tests for strategy error classes."""

    def test_strategy_not_found_error(self) -> None:
        """Test StrategyNotFoundError message."""
        error = StrategyNotFoundError("test-id")
        assert "test-id" in str(error)
        assert error.strategy_id == "test-id"

    def test_strategy_name_exists_error(self) -> None:
        """Test StrategyNameExistsError message."""
        error = StrategyNameExistsError("TestStrategy")
        assert "TestStrategy" in str(error)
        assert error.name == "TestStrategy"

    def test_strategy_validation_error(self) -> None:
        """Test StrategyValidationError message."""
        errors = ["Error 1", "Error 2"]
        error = StrategyValidationError(errors)
        assert "Error 1" in str(error)
        assert "Error 2" in str(error)
        assert error.errors == errors
