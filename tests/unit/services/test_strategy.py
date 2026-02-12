"""Unit tests for strategy service."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from squant.models.enums import RunStatus, StrategyStatus
from squant.models.strategy import Strategy, StrategyRun
from squant.schemas.strategy import CreateStrategyRequest, UpdateStrategyRequest
from squant.services.strategy import (
    StrategyInUseError,
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


class TestStrategyInUseError:
    """Tests for StrategyInUseError exception (STR-024)."""

    def test_error_message(self):
        """Test error message contains strategy ID and running count."""
        strategy_id = uuid4()
        error = StrategyInUseError(strategy_id, running_count=2)

        assert str(strategy_id) in str(error)
        assert "2" in str(error)
        assert "running" in str(error).lower()
        assert error.strategy_id == str(strategy_id)
        assert error.running_count == 2

    def test_default_running_count(self):
        """Test default running count is 1."""
        error = StrategyInUseError("test-id")

        assert error.running_count == 1
        assert "1" in str(error)


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
    async def test_update_with_params_and_status(self, service, sample_strategy):
        """Test updating params_schema, default_params, and status."""
        service.repository.get = AsyncMock(return_value=sample_strategy)
        service.repository.update = AsyncMock(return_value=sample_strategy)

        params_schema = {"type": "object", "properties": {"period": {"type": "integer"}}}
        default_params = {"period": 14}

        request = UpdateStrategyRequest(
            params_schema=params_schema,
            default_params=default_params,
            status=StrategyStatus.ARCHIVED,
        )

        await service.update(sample_strategy.id, request)

        # Check that all fields were passed to update
        call_args = service.repository.update.call_args
        assert call_args[1]["params_schema"] == params_schema
        assert call_args[1]["default_params"] == default_params
        assert call_args[1]["status"] == StrategyStatus.ARCHIVED

    @pytest.mark.asyncio
    async def test_delete_success(self, service, mock_session, sample_strategy):
        """Test successful strategy soft-delete (archive) when no running sessions."""
        service.repository.get = AsyncMock(return_value=sample_strategy)
        service.repository.update = AsyncMock(return_value=sample_strategy)

        # Mock no running sessions
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        await service.delete(sample_strategy.id)

        call_args = service.repository.update.call_args
        assert call_args[0][0] == sample_strategy.id
        assert call_args[1]["status"] == StrategyStatus.ARCHIVED
        assert call_args[1]["name"].startswith("Test Strategy_archived_")
        service.session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_not_found(self, service):
        """Test delete fails when strategy not found."""
        service.repository.get = AsyncMock(return_value=None)

        with pytest.raises(StrategyNotFoundError):
            await service.delete(uuid4())

    @pytest.mark.asyncio
    async def test_delete_running_strategy_fails(self, service, mock_session, sample_strategy):
        """Test delete fails when strategy has running sessions (STR-024)."""
        service.repository.get = AsyncMock(return_value=sample_strategy)

        # Mock one running session
        running_session = MagicMock(spec=StrategyRun)
        running_session.status = RunStatus.RUNNING
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [running_session]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        with pytest.raises(StrategyInUseError) as exc_info:
            await service.delete(sample_strategy.id)

        assert exc_info.value.running_count == 1
        assert str(sample_strategy.id) in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_delete_multiple_running_sessions_fails(self, service, mock_session, sample_strategy):
        """Test delete fails with correct count when multiple sessions running."""
        service.repository.get = AsyncMock(return_value=sample_strategy)

        # Mock multiple running sessions
        running_sessions = [
            MagicMock(spec=StrategyRun, status=RunStatus.RUNNING),
            MagicMock(spec=StrategyRun, status=RunStatus.RUNNING),
            MagicMock(spec=StrategyRun, status=RunStatus.RUNNING),
        ]
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = running_sessions
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        with pytest.raises(StrategyInUseError) as exc_info:
            await service.delete(sample_strategy.id)

        assert exc_info.value.running_count == 3

    @pytest.mark.asyncio
    async def test_delete_with_completed_runs_archives(self, service, mock_session, sample_strategy):
        """Test delete archives strategy even when it has completed runs.

        Soft delete preserves strategy_runs history (backtest results, etc.)
        while hiding the strategy from active listings.
        """
        service.repository.get = AsyncMock(return_value=sample_strategy)
        service.repository.update = AsyncMock(return_value=sample_strategy)

        # Mock no running sessions
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        await service.delete(sample_strategy.id)

        # Should archive, not hard delete
        call_args = service.repository.update.call_args
        assert call_args[0][0] == sample_strategy.id
        assert call_args[1]["status"] == StrategyStatus.ARCHIVED
        assert "_archived_" in call_args[1]["name"]

    @pytest.mark.asyncio
    @patch("squant.services.strategy.validate_strategy_code")
    async def test_archive_frees_name_for_reuse(self, mock_validate, service, mock_session, sample_strategy):
        """Test that archiving a strategy frees up its name for a new strategy."""
        # Step 1: Archive the strategy
        service.repository.get = AsyncMock(return_value=sample_strategy)
        service.repository.update = AsyncMock(return_value=sample_strategy)

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        await service.delete(sample_strategy.id)

        # Verify name was changed to include _archived_
        archive_call = service.repository.update.call_args
        archived_name = archive_call[1]["name"]
        assert archived_name != sample_strategy.name
        assert sample_strategy.name in archived_name

        # Step 2: Create new strategy with original name should not conflict
        mock_validate.return_value = MagicMock(valid=True, errors=[])
        # get_by_name returns None because the archived one has a different name now
        service.repository.get_by_name = AsyncMock(return_value=None)
        new_strategy = MagicMock(spec=Strategy)
        new_strategy.name = sample_strategy.name
        service.repository.create = AsyncMock(return_value=new_strategy)

        request = CreateStrategyRequest(
            name=sample_strategy.name,
            code="class T(Strategy):\n    def on_bar(self, bar): pass\n",
        )
        result = await service.create(request)
        assert result.name == sample_strategy.name

    @pytest.mark.asyncio
    async def test_delete_already_archived_is_noop(self, service, mock_session, sample_strategy):
        """Test deleting an already-archived strategy is a no-op (F2)."""
        sample_strategy.status = StrategyStatus.ARCHIVED
        service.repository.get = AsyncMock(return_value=sample_strategy)
        service.repository.update = AsyncMock()

        await service.delete(sample_strategy.id)

        service.repository.update.assert_not_called()
        service.session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_truncates_long_name(self, service, mock_session, sample_strategy):
        """Test archived name is truncated to fit 128-char DB limit (F1)."""
        sample_strategy.name = "A" * 128  # Max length name
        service.repository.get = AsyncMock(return_value=sample_strategy)
        service.repository.update = AsyncMock(return_value=sample_strategy)

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        await service.delete(sample_strategy.id)

        call_args = service.repository.update.call_args
        archived_name = call_args[1]["name"]
        assert len(archived_name) <= 128
        assert "_archived_" in archived_name

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
