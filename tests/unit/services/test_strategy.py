"""Unit tests for strategy service."""

from __future__ import annotations

from datetime import UTC, datetime
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


class TestStrategyNotFoundError:
    """Tests for StrategyNotFoundError exception."""

    def test_error_message(self):
        """Test error message contains strategy ID."""
        strategy_id = uuid4()
        error = StrategyNotFoundError(strategy_id)

        assert str(strategy_id) in str(error)
        assert error.strategy_id == str(strategy_id)

    def test_string_id(self):
        """Test works with string ID."""
        error = StrategyNotFoundError("test-id")

        assert "test-id" in str(error)
        assert error.strategy_id == "test-id"


class TestStrategyNameExistsError:
    """Tests for StrategyNameExistsError exception."""

    def test_error_message(self):
        """Test error message contains name."""
        error = StrategyNameExistsError("My Strategy")

        assert "My Strategy" in str(error)
        assert error.name == "My Strategy"


class TestStrategyValidationError:
    """Tests for StrategyValidationError exception."""

    def test_single_error(self):
        """Test error with single validation error."""
        error = StrategyValidationError(["Missing init method"])

        assert "Missing init method" in str(error)
        assert len(error.errors) == 1

    def test_multiple_errors(self):
        """Test error with multiple validation errors."""
        errors = ["Missing init method", "Invalid import"]
        error = StrategyValidationError(errors)

        assert "Missing init method" in str(error)
        assert "Invalid import" in str(error)
        assert len(error.errors) == 2


class TestStrategyRepository:
    """Tests for StrategyRepository."""

    @pytest.fixture
    def mock_session(self):
        """Create mock async session."""
        session = MagicMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.fixture
    def repository(self, mock_session):
        """Create repository with mock session."""
        return StrategyRepository(mock_session)

    @pytest.fixture
    def sample_strategy(self):
        """Create sample strategy model."""
        strategy = MagicMock(spec=Strategy)
        strategy.id = uuid4()
        strategy.name = "Test Strategy"
        strategy.code = "class Strategy: pass"
        strategy.status = StrategyStatus.ACTIVE
        strategy.created_at = datetime.now(UTC)
        return strategy

    @pytest.mark.asyncio
    async def test_get_by_name_found(self, repository, mock_session, sample_strategy):
        """Test get_by_name when strategy exists."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_strategy
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_name("Test Strategy")

        assert result == sample_strategy
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_name_not_found(self, repository, mock_session):
        """Test get_by_name when strategy doesn't exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_name("Nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_list_active(self, repository, mock_session, sample_strategy):
        """Test listing active strategies."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_strategy]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.list_active()

        assert len(result) == 1
        assert result[0] == sample_strategy

    @pytest.mark.asyncio
    async def test_list_with_pagination(self, repository, mock_session, sample_strategy):
        """Test listing with pagination."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_strategy]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.list_with_pagination(offset=0, limit=10)

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_with_pagination_and_status_filter(
        self, repository, mock_session, sample_strategy
    ):
        """Test listing with status filter."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_strategy]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.list_with_pagination(
            offset=0, limit=10, status=StrategyStatus.ACTIVE
        )

        assert len(result) == 1

    @pytest.mark.asyncio
    @patch.object(StrategyRepository, "count")
    async def test_count_by_status_with_status(self, mock_count, repository):
        """Test counting with status filter."""
        mock_count.return_value = 5

        result = await repository.count_by_status(StrategyStatus.ACTIVE)

        assert result == 5
        mock_count.assert_called_once_with(status=StrategyStatus.ACTIVE)

    @pytest.mark.asyncio
    @patch.object(StrategyRepository, "count")
    async def test_count_by_status_no_filter(self, mock_count, repository):
        """Test counting without filter."""
        mock_count.return_value = 10

        result = await repository.count_by_status(None)

        assert result == 10
        mock_count.assert_called_once_with()


class TestStrategyService:
    """Tests for StrategyService."""

    @pytest.fixture
    def mock_session(self):
        """Create mock async session."""
        session = MagicMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.fixture
    def service(self, mock_session):
        """Create service with mock session."""
        return StrategyService(mock_session)

    @pytest.fixture
    def sample_strategy(self):
        """Create sample strategy model."""
        strategy = MagicMock(spec=Strategy)
        strategy.id = uuid4()
        strategy.name = "Test Strategy"
        strategy.code = "class Strategy:\n    def init(self): pass\n    def next(self): pass"
        strategy.version = "1.0.0"
        strategy.status = StrategyStatus.ACTIVE
        strategy.created_at = datetime.now(UTC)
        return strategy

    @pytest.mark.asyncio
    @patch("squant.services.strategy.validate_strategy_code")
    async def test_create_success(self, mock_validate, service, sample_strategy):
        """Test successful strategy creation."""
        mock_validate.return_value = MagicMock(valid=True, errors=[])
        service.repository.get_by_name = AsyncMock(return_value=None)
        service.repository.create = AsyncMock(return_value=sample_strategy)

        request = CreateStrategyRequest(
            name="Test Strategy",
            code="class Strategy:\n    def init(self): pass\n    def next(self): pass",
        )

        result = await service.create(request)

        assert result == sample_strategy
        service.repository.create.assert_called_once()
        service.session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_name_exists(self, service, sample_strategy):
        """Test create fails when name exists."""
        service.repository.get_by_name = AsyncMock(return_value=sample_strategy)

        request = CreateStrategyRequest(
            name="Test Strategy",
            code="class Strategy: pass",
        )

        with pytest.raises(StrategyNameExistsError) as exc_info:
            await service.create(request)

        assert exc_info.value.name == "Test Strategy"

    @pytest.mark.asyncio
    @patch("squant.services.strategy.validate_strategy_code")
    async def test_create_validation_fails(self, mock_validate, service):
        """Test create fails on validation error."""
        mock_validate.return_value = MagicMock(valid=False, errors=["Missing init"])
        service.repository.get_by_name = AsyncMock(return_value=None)

        request = CreateStrategyRequest(
            name="Test Strategy",
            code="class Strategy: pass",
        )

        with pytest.raises(StrategyValidationError) as exc_info:
            await service.create(request)

        assert "Missing init" in exc_info.value.errors

    @pytest.mark.asyncio
    @patch("squant.services.strategy.validate_strategy_code")
    async def test_update_success(self, mock_validate, service, sample_strategy):
        """Test successful strategy update."""
        mock_validate.return_value = MagicMock(valid=True, errors=[])
        service.repository.get = AsyncMock(return_value=sample_strategy)
        service.repository.get_by_name = AsyncMock(return_value=None)
        service.repository.update = AsyncMock(return_value=sample_strategy)

        request = UpdateStrategyRequest(
            name="Updated Strategy",
            description="Updated description",
        )

        result = await service.update(sample_strategy.id, request)

        assert result == sample_strategy
        service.session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_not_found(self, service):
        """Test update fails when strategy not found."""
        service.repository.get = AsyncMock(return_value=None)

        request = UpdateStrategyRequest(name="Updated")

        with pytest.raises(StrategyNotFoundError):
            await service.update(uuid4(), request)

    @pytest.mark.asyncio
    async def test_update_name_exists(self, service, sample_strategy):
        """Test update fails when new name exists."""
        other_strategy = MagicMock()
        other_strategy.name = "Other Strategy"

        service.repository.get = AsyncMock(return_value=sample_strategy)
        service.repository.get_by_name = AsyncMock(return_value=other_strategy)

        request = UpdateStrategyRequest(name="Other Strategy")

        with pytest.raises(StrategyNameExistsError):
            await service.update(sample_strategy.id, request)

    @pytest.mark.asyncio
    @patch("squant.services.strategy.validate_strategy_code")
    async def test_update_code_validates(self, mock_validate, service, sample_strategy):
        """Test update validates code when code is changed."""
        mock_validate.return_value = MagicMock(valid=False, errors=["Invalid"])
        service.repository.get = AsyncMock(return_value=sample_strategy)

        request = UpdateStrategyRequest(code="invalid code")

        with pytest.raises(StrategyValidationError):
            await service.update(sample_strategy.id, request)

    @pytest.mark.asyncio
    @patch("squant.services.strategy.validate_strategy_code")
    async def test_update_increments_version(self, mock_validate, service, sample_strategy):
        """Test version increments when code changes."""
        mock_validate.return_value = MagicMock(valid=True, errors=[])
        sample_strategy.version = "1.0.5"
        service.repository.get = AsyncMock(return_value=sample_strategy)
        service.repository.update = AsyncMock(return_value=sample_strategy)

        request = UpdateStrategyRequest(code="new valid code")

        await service.update(sample_strategy.id, request)

        # Check that version was incremented
        call_args = service.repository.update.call_args
        assert call_args[1]["version"] == "1.0.6"

    @pytest.mark.asyncio
    async def test_delete_success(self, service):
        """Test successful strategy deletion."""
        service.repository.exists = AsyncMock(return_value=True)
        service.repository.delete = AsyncMock()

        await service.delete(uuid4())

        service.repository.delete.assert_called_once()
        service.session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_not_found(self, service):
        """Test delete fails when strategy not found."""
        service.repository.exists = AsyncMock(return_value=False)

        with pytest.raises(StrategyNotFoundError):
            await service.delete(uuid4())

    @pytest.mark.asyncio
    async def test_get_success(self, service, sample_strategy):
        """Test successful strategy retrieval."""
        service.repository.get = AsyncMock(return_value=sample_strategy)

        result = await service.get(sample_strategy.id)

        assert result == sample_strategy

    @pytest.mark.asyncio
    async def test_get_not_found(self, service):
        """Test get fails when strategy not found."""
        service.repository.get = AsyncMock(return_value=None)

        with pytest.raises(StrategyNotFoundError):
            await service.get(uuid4())

    @pytest.mark.asyncio
    async def test_list_pagination(self, service, sample_strategy):
        """Test listing with pagination."""
        service.repository.list_with_pagination = AsyncMock(return_value=[sample_strategy])
        service.repository.count_by_status = AsyncMock(return_value=1)

        strategies, total = await service.list(page=1, page_size=20)

        assert len(strategies) == 1
        assert total == 1
        service.repository.list_with_pagination.assert_called_once_with(
            offset=0, limit=20, status=None
        )

    @pytest.mark.asyncio
    async def test_list_with_status_filter(self, service, sample_strategy):
        """Test listing with status filter."""
        service.repository.list_with_pagination = AsyncMock(return_value=[sample_strategy])
        service.repository.count_by_status = AsyncMock(return_value=1)

        strategies, total = await service.list(page=2, page_size=10, status=StrategyStatus.ACTIVE)

        service.repository.list_with_pagination.assert_called_once_with(
            offset=10, limit=10, status=StrategyStatus.ACTIVE
        )

    @patch("squant.services.strategy.validate_strategy_code")
    def test_validate_code(self, mock_validate, service):
        """Test code validation method."""
        mock_result = MagicMock(valid=True, errors=[])
        mock_validate.return_value = mock_result

        result = service.validate_code("class Strategy: pass")

        assert result == mock_result
        mock_validate.assert_called_once_with("class Strategy: pass")
