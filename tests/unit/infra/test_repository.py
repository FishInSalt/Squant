"""Unit tests for base repository."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from squant.infra.repository import BaseRepository


# Create a mock model class for testing
class MockModel:
    """Mock model for repository tests."""

    id = MagicMock()
    name = MagicMock()
    status = MagicMock()

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


@pytest.fixture
def mock_session():
    """Create a mock async session."""
    session = MagicMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.add_all = MagicMock()
    return session


@pytest.fixture
def repository(mock_session):
    """Create a repository instance with mock session."""
    return BaseRepository(MockModel, mock_session)


@pytest.fixture
def mock_model_instance():
    """Create a mock model instance."""
    instance = MagicMock(spec=MockModel)
    instance.id = str(uuid4())
    instance.name = "Test Item"
    instance.status = "active"
    return instance


class TestBaseRepositoryInit:
    """Tests for BaseRepository initialization."""

    def test_init_stores_model_and_session(self, mock_session):
        """Test repository stores model and session."""
        repo = BaseRepository(MockModel, mock_session)

        assert repo.model is MockModel
        assert repo.session is mock_session


class TestBaseRepositoryGet:
    """Tests for BaseRepository.get method."""

    @pytest.mark.asyncio
    @patch("squant.infra.repository.select")
    async def test_get_returns_model(
        self, mock_select, repository, mock_session, mock_model_instance
    ):
        """Test get returns model when found."""
        mock_stmt = MagicMock()
        mock_stmt.where.return_value = mock_stmt
        mock_select.return_value = mock_stmt

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_model_instance
        mock_session.execute.return_value = mock_result

        result = await repository.get(mock_model_instance.id)

        assert result == mock_model_instance
        mock_session.execute.assert_called_once()
        mock_select.assert_called_once_with(MockModel)

    @pytest.mark.asyncio
    @patch("squant.infra.repository.select")
    async def test_get_returns_none_when_not_found(
        self, mock_select, repository, mock_session
    ):
        """Test get returns None when not found."""
        mock_stmt = MagicMock()
        mock_stmt.where.return_value = mock_stmt
        mock_select.return_value = mock_stmt

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get(str(uuid4()))

        assert result is None

    @pytest.mark.asyncio
    @patch("squant.infra.repository.select")
    async def test_get_accepts_uuid(
        self, mock_select, repository, mock_session, mock_model_instance
    ):
        """Test get accepts UUID object."""
        mock_stmt = MagicMock()
        mock_stmt.where.return_value = mock_stmt
        mock_select.return_value = mock_stmt

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_model_instance
        mock_session.execute.return_value = mock_result

        result = await repository.get(uuid4())

        assert result is not None
        mock_session.execute.assert_called_once()


class TestBaseRepositoryGetBy:
    """Tests for BaseRepository.get_by method."""

    @pytest.mark.asyncio
    @patch("squant.infra.repository.select")
    async def test_get_by_single_filter(
        self, mock_select, repository, mock_session, mock_model_instance
    ):
        """Test get_by with single filter."""
        mock_stmt = MagicMock()
        mock_stmt.where.return_value = mock_stmt
        mock_select.return_value = mock_stmt

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_model_instance
        mock_session.execute.return_value = mock_result

        result = await repository.get_by(name="Test Item")

        assert result == mock_model_instance
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    @patch("squant.infra.repository.select")
    async def test_get_by_multiple_filters(
        self, mock_select, repository, mock_session, mock_model_instance
    ):
        """Test get_by with multiple filters."""
        mock_stmt = MagicMock()
        mock_stmt.where.return_value = mock_stmt
        mock_select.return_value = mock_stmt

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_model_instance
        mock_session.execute.return_value = mock_result

        result = await repository.get_by(name="Test Item", status="active")

        assert result == mock_model_instance
        # where() called twice for two filters
        assert mock_stmt.where.call_count == 2

    @pytest.mark.asyncio
    @patch("squant.infra.repository.select")
    async def test_get_by_returns_none_when_not_found(
        self, mock_select, repository, mock_session
    ):
        """Test get_by returns None when not found."""
        mock_stmt = MagicMock()
        mock_stmt.where.return_value = mock_stmt
        mock_select.return_value = mock_stmt

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_by(name="Nonexistent")

        assert result is None


class TestBaseRepositoryList:
    """Tests for BaseRepository.list method."""

    @pytest.mark.asyncio
    @patch("squant.infra.repository.select")
    async def test_list_returns_all(
        self, mock_select, repository, mock_session, mock_model_instance
    ):
        """Test list returns all records."""
        mock_stmt = MagicMock()
        mock_stmt.where.return_value = mock_stmt
        mock_stmt.order_by.return_value = mock_stmt
        mock_stmt.offset.return_value = mock_stmt
        mock_stmt.limit.return_value = mock_stmt
        mock_select.return_value = mock_stmt

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_model_instance]
        mock_session.execute.return_value = mock_result

        result = await repository.list()

        assert len(result) == 1
        assert result[0] == mock_model_instance

    @pytest.mark.asyncio
    @patch("squant.infra.repository.select")
    async def test_list_with_pagination(
        self, mock_select, repository, mock_session, mock_model_instance
    ):
        """Test list with offset and limit."""
        mock_stmt = MagicMock()
        mock_stmt.where.return_value = mock_stmt
        mock_stmt.order_by.return_value = mock_stmt
        mock_stmt.offset.return_value = mock_stmt
        mock_stmt.limit.return_value = mock_stmt
        mock_select.return_value = mock_stmt

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_model_instance]
        mock_session.execute.return_value = mock_result

        result = await repository.list(offset=10, limit=5)

        assert len(result) == 1
        mock_stmt.offset.assert_called_once_with(10)
        mock_stmt.limit.assert_called_once_with(5)

    @pytest.mark.asyncio
    @patch("squant.infra.repository.select")
    async def test_list_with_filters(
        self, mock_select, repository, mock_session, mock_model_instance
    ):
        """Test list with filters."""
        mock_stmt = MagicMock()
        mock_stmt.where.return_value = mock_stmt
        mock_stmt.order_by.return_value = mock_stmt
        mock_stmt.offset.return_value = mock_stmt
        mock_stmt.limit.return_value = mock_stmt
        mock_select.return_value = mock_stmt

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_model_instance]
        mock_session.execute.return_value = mock_result

        result = await repository.list(status="active")

        assert len(result) == 1
        mock_stmt.where.assert_called_once()

    @pytest.mark.asyncio
    @patch("squant.infra.repository.select")
    async def test_list_with_none_filter_ignored(
        self, mock_select, repository, mock_session, mock_model_instance
    ):
        """Test list ignores None filter values."""
        mock_stmt = MagicMock()
        mock_stmt.where.return_value = mock_stmt
        mock_stmt.order_by.return_value = mock_stmt
        mock_stmt.offset.return_value = mock_stmt
        mock_stmt.limit.return_value = mock_stmt
        mock_select.return_value = mock_stmt

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_model_instance]
        mock_session.execute.return_value = mock_result

        result = await repository.list(status=None)

        assert len(result) == 1
        # where() should not be called for None filters
        mock_stmt.where.assert_not_called()

    @pytest.mark.asyncio
    @patch("squant.infra.repository.select")
    async def test_list_with_ordering(
        self, mock_select, repository, mock_session, mock_model_instance
    ):
        """Test list with ordering."""
        mock_stmt = MagicMock()
        mock_stmt.where.return_value = mock_stmt
        mock_stmt.order_by.return_value = mock_stmt
        mock_stmt.offset.return_value = mock_stmt
        mock_stmt.limit.return_value = mock_stmt
        mock_select.return_value = mock_stmt

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_model_instance]
        mock_session.execute.return_value = mock_result

        result = await repository.list(order_by="name")

        assert len(result) == 1
        mock_stmt.order_by.assert_called_once()

    @pytest.mark.asyncio
    @patch("squant.infra.repository.select")
    async def test_list_with_desc_ordering(
        self, mock_select, repository, mock_session, mock_model_instance
    ):
        """Test list with descending order."""
        mock_stmt = MagicMock()
        mock_stmt.where.return_value = mock_stmt
        mock_stmt.order_by.return_value = mock_stmt
        mock_stmt.offset.return_value = mock_stmt
        mock_stmt.limit.return_value = mock_stmt
        mock_select.return_value = mock_stmt

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_model_instance]
        mock_session.execute.return_value = mock_result

        result = await repository.list(order_by="name", desc=True)

        assert len(result) == 1
        mock_stmt.order_by.assert_called_once()

    @pytest.mark.asyncio
    @patch("squant.infra.repository.select")
    async def test_list_empty_result(self, mock_select, repository, mock_session):
        """Test list returns empty list when no records."""
        mock_stmt = MagicMock()
        mock_stmt.where.return_value = mock_stmt
        mock_stmt.order_by.return_value = mock_stmt
        mock_stmt.offset.return_value = mock_stmt
        mock_stmt.limit.return_value = mock_stmt
        mock_select.return_value = mock_stmt

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await repository.list()

        assert result == []


class TestBaseRepositoryCount:
    """Tests for BaseRepository.count method."""

    @pytest.mark.asyncio
    @patch("squant.infra.repository.func")
    @patch("squant.infra.repository.select")
    async def test_count_all(
        self, mock_select, mock_func, repository, mock_session
    ):
        """Test count all records."""
        mock_stmt = MagicMock()
        mock_stmt.select_from.return_value = mock_stmt
        mock_stmt.where.return_value = mock_stmt
        mock_select.return_value = mock_stmt

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 10
        mock_session.execute.return_value = mock_result

        result = await repository.count()

        assert result == 10
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    @patch("squant.infra.repository.func")
    @patch("squant.infra.repository.select")
    async def test_count_with_filters(
        self, mock_select, mock_func, repository, mock_session
    ):
        """Test count with filters."""
        mock_stmt = MagicMock()
        mock_stmt.select_from.return_value = mock_stmt
        mock_stmt.where.return_value = mock_stmt
        mock_select.return_value = mock_stmt

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 5
        mock_session.execute.return_value = mock_result

        result = await repository.count(status="active")

        assert result == 5
        mock_stmt.where.assert_called_once()

    @pytest.mark.asyncio
    @patch("squant.infra.repository.func")
    @patch("squant.infra.repository.select")
    async def test_count_with_none_filter_ignored(
        self, mock_select, mock_func, repository, mock_session
    ):
        """Test count ignores None filter values."""
        mock_stmt = MagicMock()
        mock_stmt.select_from.return_value = mock_stmt
        mock_stmt.where.return_value = mock_stmt
        mock_select.return_value = mock_stmt

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 10
        mock_session.execute.return_value = mock_result

        result = await repository.count(status=None)

        assert result == 10
        # where() should not be called for None filters
        mock_stmt.where.assert_not_called()


class TestBaseRepositoryCreate:
    """Tests for BaseRepository.create method."""

    @pytest.mark.asyncio
    async def test_create_returns_instance(self, repository, mock_session):
        """Test create returns new instance."""
        result = await repository.create(name="New Item", status="active")

        assert result is not None
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()
        mock_session.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_adds_to_session(self, repository, mock_session):
        """Test create adds instance to session."""
        await repository.create(name="New Item")

        mock_session.add.assert_called_once()
        # Verify it's a MockModel instance
        added_instance = mock_session.add.call_args[0][0]
        assert isinstance(added_instance, MockModel)
        assert added_instance.name == "New Item"


class TestBaseRepositoryUpdate:
    """Tests for BaseRepository.update method."""

    @pytest.mark.asyncio
    @patch("squant.infra.repository.select")
    @patch("squant.infra.repository.update")
    async def test_update_returns_updated_instance(
        self, mock_update, mock_select, repository, mock_session, mock_model_instance
    ):
        """Test update returns updated instance."""
        # Mock update statement
        mock_update_stmt = MagicMock()
        mock_update_stmt.where.return_value = mock_update_stmt
        mock_update_stmt.values.return_value = mock_update_stmt
        mock_update.return_value = mock_update_stmt

        # Mock select for get() after update
        mock_select_stmt = MagicMock()
        mock_select_stmt.where.return_value = mock_select_stmt
        mock_select.return_value = mock_select_stmt

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_model_instance
        mock_session.execute.return_value = mock_result

        result = await repository.update(mock_model_instance.id, name="Updated Name")

        assert result is not None
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    @patch("squant.infra.repository.select")
    async def test_update_with_empty_data_returns_existing(
        self, mock_select, repository, mock_session, mock_model_instance
    ):
        """Test update with no data returns existing record."""
        mock_stmt = MagicMock()
        mock_stmt.where.return_value = mock_stmt
        mock_select.return_value = mock_stmt

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_model_instance
        mock_session.execute.return_value = mock_result

        result = await repository.update(mock_model_instance.id)

        assert result == mock_model_instance
        # Only one call for get, no update
        assert mock_session.execute.call_count == 1

    @pytest.mark.asyncio
    @patch("squant.infra.repository.select")
    @patch("squant.infra.repository.update")
    async def test_update_filters_none_values(
        self, mock_update, mock_select, repository, mock_session, mock_model_instance
    ):
        """Test update filters out None values."""
        mock_update_stmt = MagicMock()
        mock_update_stmt.where.return_value = mock_update_stmt
        mock_update_stmt.values.return_value = mock_update_stmt
        mock_update.return_value = mock_update_stmt

        mock_select_stmt = MagicMock()
        mock_select_stmt.where.return_value = mock_select_stmt
        mock_select.return_value = mock_select_stmt

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_model_instance
        mock_session.execute.return_value = mock_result

        result = await repository.update(
            mock_model_instance.id, name="Updated", status=None
        )

        assert result is not None
        # values() should only receive non-None values
        mock_update_stmt.values.assert_called_once_with(name="Updated")


class TestBaseRepositoryDelete:
    """Tests for BaseRepository.delete method."""

    @pytest.mark.asyncio
    @patch("squant.infra.repository.delete")
    async def test_delete_returns_true_when_deleted(
        self, mock_delete, repository, mock_session
    ):
        """Test delete returns True when record deleted."""
        mock_stmt = MagicMock()
        mock_stmt.where.return_value = mock_stmt
        mock_delete.return_value = mock_stmt

        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result

        result = await repository.delete(str(uuid4()))

        assert result is True
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    @patch("squant.infra.repository.delete")
    async def test_delete_returns_false_when_not_found(
        self, mock_delete, repository, mock_session
    ):
        """Test delete returns False when record not found."""
        mock_stmt = MagicMock()
        mock_stmt.where.return_value = mock_stmt
        mock_delete.return_value = mock_stmt

        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute.return_value = mock_result

        result = await repository.delete(str(uuid4()))

        assert result is False


class TestBaseRepositoryExists:
    """Tests for BaseRepository.exists method."""

    @pytest.mark.asyncio
    @patch("squant.infra.repository.func")
    @patch("squant.infra.repository.select")
    async def test_exists_returns_true_when_exists(
        self, mock_select, mock_func, repository, mock_session
    ):
        """Test exists returns True when record exists."""
        mock_stmt = MagicMock()
        mock_stmt.select_from.return_value = mock_stmt
        mock_stmt.where.return_value = mock_stmt
        mock_select.return_value = mock_stmt

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 1
        mock_session.execute.return_value = mock_result

        result = await repository.exists(str(uuid4()))

        assert result is True

    @pytest.mark.asyncio
    @patch("squant.infra.repository.func")
    @patch("squant.infra.repository.select")
    async def test_exists_returns_false_when_not_exists(
        self, mock_select, mock_func, repository, mock_session
    ):
        """Test exists returns False when record doesn't exist."""
        mock_stmt = MagicMock()
        mock_stmt.select_from.return_value = mock_stmt
        mock_stmt.where.return_value = mock_stmt
        mock_select.return_value = mock_stmt

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 0
        mock_session.execute.return_value = mock_result

        result = await repository.exists(str(uuid4()))

        assert result is False


class TestBaseRepositoryBulkCreate:
    """Tests for BaseRepository.bulk_create method."""

    @pytest.mark.asyncio
    async def test_bulk_create_returns_instances(self, repository, mock_session):
        """Test bulk_create returns created instances."""
        items = [
            {"name": "Item 1", "status": "active"},
            {"name": "Item 2", "status": "inactive"},
        ]

        result = await repository.bulk_create(items)

        assert len(result) == 2
        mock_session.add_all.assert_called_once()
        mock_session.flush.assert_called_once()
        # Refresh called for each instance
        assert mock_session.refresh.call_count == 2

    @pytest.mark.asyncio
    async def test_bulk_create_empty_list(self, repository, mock_session):
        """Test bulk_create with empty list."""
        result = await repository.bulk_create([])

        assert result == []
        mock_session.add_all.assert_called_once_with([])
