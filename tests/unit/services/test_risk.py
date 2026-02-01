"""Unit tests for risk service."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from squant.models.enums import RiskRuleType
from squant.models.risk import RiskRule, RiskTrigger
from squant.schemas.risk import CreateRiskRuleRequest, UpdateRiskRuleRequest
from squant.services.risk import (
    RiskRuleNotFoundError,
    RiskRuleRepository,
    RiskRuleService,
    RiskTriggerRepository,
    RiskTriggerService,
)


class TestRiskRuleNotFoundError:
    """Tests for RiskRuleNotFoundError exception."""

    def test_error_message(self):
        """Test error message contains rule ID."""
        rule_id = uuid4()
        error = RiskRuleNotFoundError(rule_id)

        assert str(rule_id) in str(error)
        assert error.rule_id == str(rule_id)

    def test_string_id(self):
        """Test works with string ID."""
        error = RiskRuleNotFoundError("test-rule-id")

        assert "test-rule-id" in str(error)


class TestRiskRuleRepository:
    """Tests for RiskRuleRepository."""

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
        return RiskRuleRepository(mock_session)

    @pytest.fixture
    def sample_rule(self):
        """Create sample risk rule model."""
        rule = MagicMock(spec=RiskRule)
        rule.id = uuid4()
        rule.name = "Max Position"
        rule.type = RiskRuleType.POSITION_LIMIT
        rule.params = {"max_position": 10.0}
        rule.enabled = True
        rule.created_at = datetime.now(UTC)
        return rule

    @pytest.mark.asyncio
    async def test_list_enabled(self, repository, mock_session, sample_rule):
        """Test listing enabled rules."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_rule]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.list_enabled()

        assert len(result) == 1
        assert result[0] == sample_rule

    @pytest.mark.asyncio
    async def test_list_with_pagination(self, repository, mock_session, sample_rule):
        """Test listing with pagination."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_rule]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.list_with_pagination(offset=0, limit=10)

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_with_pagination_enabled_filter(self, repository, mock_session, sample_rule):
        """Test listing with enabled filter."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_rule]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.list_with_pagination(offset=0, limit=10, enabled=True)

        assert len(result) == 1

    @pytest.mark.asyncio
    @patch.object(RiskRuleRepository, "count")
    async def test_count_by_enabled_with_filter(self, mock_count, repository):
        """Test counting with enabled filter."""
        mock_count.return_value = 3

        result = await repository.count_by_enabled(enabled=True)

        assert result == 3
        mock_count.assert_called_once_with(enabled=True)

    @pytest.mark.asyncio
    @patch.object(RiskRuleRepository, "count")
    async def test_count_by_enabled_no_filter(self, mock_count, repository):
        """Test counting without filter."""
        mock_count.return_value = 10

        result = await repository.count_by_enabled(None)

        assert result == 10
        mock_count.assert_called_once_with()


class TestRiskRuleService:
    """Tests for RiskRuleService."""

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
        return RiskRuleService(mock_session)

    @pytest.fixture
    def sample_rule(self):
        """Create sample risk rule model."""
        rule = MagicMock(spec=RiskRule)
        rule.id = uuid4()
        rule.name = "Max Position"
        rule.type = RiskRuleType.POSITION_LIMIT
        rule.params = {"max_position": 10.0}
        rule.enabled = True
        rule.created_at = datetime.now(UTC)
        return rule

    @pytest.mark.asyncio
    async def test_create_success(self, service, sample_rule):
        """Test successful rule creation."""
        service.repository.create = AsyncMock(return_value=sample_rule)

        request = CreateRiskRuleRequest(
            name="Max Position",
            type=RiskRuleType.POSITION_LIMIT,
            params={"max_position": 10.0},
        )

        result = await service.create(request)

        assert result == sample_rule
        service.repository.create.assert_called_once()
        service.session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_with_disabled(self, service, sample_rule):
        """Test creating disabled rule."""
        sample_rule.enabled = False
        service.repository.create = AsyncMock(return_value=sample_rule)

        request = CreateRiskRuleRequest(
            name="Max Position",
            type=RiskRuleType.POSITION_LIMIT,
            params={"max_position": 10.0},
            enabled=False,
        )

        await service.create(request)

        call_kwargs = service.repository.create.call_args[1]
        assert call_kwargs["enabled"] is False

    @pytest.mark.asyncio
    async def test_update_success(self, service, sample_rule):
        """Test successful rule update."""
        service.repository.get = AsyncMock(return_value=sample_rule)
        service.repository.update = AsyncMock(return_value=sample_rule)

        request = UpdateRiskRuleRequest(name="Updated Name", enabled=False)

        result = await service.update(sample_rule.id, request)

        assert result == sample_rule
        service.repository.update.assert_called_once()
        service.session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_not_found(self, service):
        """Test update fails when rule not found."""
        service.repository.get = AsyncMock(return_value=None)

        request = UpdateRiskRuleRequest(name="Updated")

        with pytest.raises(RiskRuleNotFoundError):
            await service.update(uuid4(), request)

    @pytest.mark.asyncio
    async def test_update_no_changes(self, service, sample_rule):
        """Test update with no changes."""
        service.repository.get = AsyncMock(return_value=sample_rule)
        service.repository.update = AsyncMock()

        request = UpdateRiskRuleRequest()

        result = await service.update(sample_rule.id, request)

        assert result == sample_rule
        service.repository.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_all_fields(self, service, sample_rule):
        """Test update with all fields."""
        service.repository.get = AsyncMock(return_value=sample_rule)
        service.repository.update = AsyncMock(return_value=sample_rule)

        request = UpdateRiskRuleRequest(
            name="New Name",
            type=RiskRuleType.ORDER_LIMIT,
            params={"new_param": "value"},
            enabled=False,
        )

        await service.update(sample_rule.id, request)

        call_kwargs = service.repository.update.call_args[1]
        assert call_kwargs["name"] == "New Name"
        assert call_kwargs["type"] == RiskRuleType.ORDER_LIMIT
        assert call_kwargs["params"] == {"new_param": "value"}
        assert call_kwargs["enabled"] is False

    @pytest.mark.asyncio
    async def test_delete_success(self, service):
        """Test successful rule deletion."""
        service.repository.exists = AsyncMock(return_value=True)
        service.repository.delete = AsyncMock()

        await service.delete(uuid4())

        service.repository.delete.assert_called_once()
        service.session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_not_found(self, service):
        """Test delete fails when rule not found."""
        service.repository.exists = AsyncMock(return_value=False)

        with pytest.raises(RiskRuleNotFoundError):
            await service.delete(uuid4())

    @pytest.mark.asyncio
    async def test_get_success(self, service, sample_rule):
        """Test successful rule retrieval."""
        service.repository.get = AsyncMock(return_value=sample_rule)

        result = await service.get(sample_rule.id)

        assert result == sample_rule

    @pytest.mark.asyncio
    async def test_get_not_found(self, service):
        """Test get fails when rule not found."""
        service.repository.get = AsyncMock(return_value=None)

        with pytest.raises(RiskRuleNotFoundError):
            await service.get(uuid4())

    @pytest.mark.asyncio
    async def test_list_pagination(self, service, sample_rule):
        """Test listing with pagination."""
        service.repository.list_with_pagination = AsyncMock(return_value=[sample_rule])
        service.repository.count_by_enabled = AsyncMock(return_value=1)

        rules, total = await service.list(page=1, page_size=20)

        assert len(rules) == 1
        assert total == 1
        service.repository.list_with_pagination.assert_called_once_with(
            offset=0, limit=20, enabled=None
        )

    @pytest.mark.asyncio
    async def test_list_with_enabled_filter(self, service, sample_rule):
        """Test listing with enabled filter."""
        service.repository.list_with_pagination = AsyncMock(return_value=[sample_rule])
        service.repository.count_by_enabled = AsyncMock(return_value=1)

        rules, total = await service.list(page=2, page_size=10, enabled=True)

        service.repository.list_with_pagination.assert_called_once_with(
            offset=10, limit=10, enabled=True
        )

    @pytest.mark.asyncio
    async def test_toggle_enable(self, service, sample_rule):
        """Test toggling rule to enabled."""
        sample_rule.enabled = False
        service.repository.get = AsyncMock(return_value=sample_rule)
        service.repository.update = AsyncMock(return_value=sample_rule)

        await service.toggle(sample_rule.id, enabled=True)

        service.repository.update.assert_called_once_with(sample_rule.id, enabled=True)
        service.session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_toggle_disable(self, service, sample_rule):
        """Test toggling rule to disabled."""
        service.repository.get = AsyncMock(return_value=sample_rule)
        service.repository.update = AsyncMock(return_value=sample_rule)

        await service.toggle(sample_rule.id, enabled=False)

        service.repository.update.assert_called_once_with(sample_rule.id, enabled=False)

    @pytest.mark.asyncio
    async def test_toggle_not_found(self, service):
        """Test toggle fails when rule not found."""
        service.repository.get = AsyncMock(return_value=None)

        with pytest.raises(RiskRuleNotFoundError):
            await service.toggle(uuid4(), enabled=True)

    @pytest.mark.asyncio
    async def test_list_enabled(self, service, sample_rule):
        """Test listing enabled rules."""
        service.repository.list_enabled = AsyncMock(return_value=[sample_rule])

        result = await service.list_enabled()

        assert len(result) == 1
        assert result[0] == sample_rule


class TestRiskTriggerRepository:
    """Tests for RiskTriggerRepository."""

    @pytest.fixture
    def mock_session(self):
        """Create mock async session."""
        session = MagicMock()
        session.execute = AsyncMock()
        return session

    @pytest.fixture
    def repository(self, mock_session):
        """Create repository with mock session."""
        return RiskTriggerRepository(mock_session)

    @pytest.fixture
    def sample_trigger(self):
        """Create sample risk trigger model."""
        trigger = MagicMock(spec=RiskTrigger)
        trigger.id = uuid4()
        trigger.time = datetime.now(UTC)
        trigger.rule_id = str(uuid4())
        trigger.run_id = str(uuid4())
        trigger.trigger_type = "auto"
        trigger.details = {"threshold": 0.05, "actual": 0.06}
        return trigger

    @pytest.mark.asyncio
    async def test_list_with_filters_no_filters(self, repository, mock_session, sample_trigger):
        """Test listing without filters."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_trigger]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.list_with_filters(offset=0, limit=10)

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_with_filters_time_range(self, repository, mock_session, sample_trigger):
        """Test listing with time range filter."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_trigger]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        now = datetime.now(UTC)
        result = await repository.list_with_filters(
            offset=0, limit=10, start_time=now, end_time=now
        )

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_with_filters_rule_id(self, repository, mock_session, sample_trigger):
        """Test listing with rule_id filter."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_trigger]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.list_with_filters(offset=0, limit=10, rule_id=uuid4())

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_with_filters_run_id(self, repository, mock_session, sample_trigger):
        """Test listing with run_id filter."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_trigger]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.list_with_filters(offset=0, limit=10, run_id=uuid4())

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_count_with_filters(self, repository, mock_session):
        """Test counting with filters."""
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 5
        mock_session.execute.return_value = mock_result

        result = await repository.count_with_filters(rule_id=uuid4())

        assert result == 5

    @pytest.mark.asyncio
    async def test_count_with_start_time_filter(self, repository, mock_session):
        """Test counting with start_time filter."""
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 4
        mock_session.execute.return_value = mock_result

        start_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        result = await repository.count_with_filters(start_time=start_time)

        assert result == 4

    @pytest.mark.asyncio
    async def test_count_with_end_time_filter(self, repository, mock_session):
        """Test counting with end_time filter."""
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 3
        mock_session.execute.return_value = mock_result

        end_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        result = await repository.count_with_filters(end_time=end_time)

        assert result == 3

    @pytest.mark.asyncio
    async def test_count_with_run_id_filter(self, repository, mock_session):
        """Test counting with run_id filter."""
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 7
        mock_session.execute.return_value = mock_result

        result = await repository.count_with_filters(run_id=uuid4())

        assert result == 7


class TestRiskTriggerService:
    """Tests for RiskTriggerService."""

    @pytest.fixture
    def mock_session(self):
        """Create mock async session."""
        session = MagicMock()
        session.execute = AsyncMock()
        return session

    @pytest.fixture
    def service(self, mock_session):
        """Create service with mock session."""
        return RiskTriggerService(mock_session)

    @pytest.fixture
    def sample_trigger(self):
        """Create sample risk trigger model."""
        trigger = MagicMock(spec=RiskTrigger)
        trigger.id = uuid4()
        trigger.time = datetime.now(UTC)
        trigger.rule_id = str(uuid4())
        trigger.run_id = str(uuid4())
        trigger.trigger_type = "auto"
        trigger.details = {"threshold": 0.05}
        return trigger

    @pytest.mark.asyncio
    async def test_list_triggers_pagination(self, service, sample_trigger):
        """Test listing triggers with pagination."""
        service.repository.list_with_filters = AsyncMock(return_value=[sample_trigger])
        service.repository.count_with_filters = AsyncMock(return_value=1)

        triggers, total = await service.list_triggers(page=1, page_size=20)

        assert len(triggers) == 1
        assert total == 1

    @pytest.mark.asyncio
    async def test_list_triggers_with_filters(self, service, sample_trigger):
        """Test listing triggers with filters."""
        service.repository.list_with_filters = AsyncMock(return_value=[sample_trigger])
        service.repository.count_with_filters = AsyncMock(return_value=1)

        rule_id = uuid4()
        run_id = uuid4()
        now = datetime.now(UTC)

        triggers, total = await service.list_triggers(
            page=2,
            page_size=10,
            start_time=now,
            end_time=now,
            rule_id=rule_id,
            run_id=run_id,
        )

        service.repository.list_with_filters.assert_called_once_with(
            offset=10,
            limit=10,
            start_time=now,
            end_time=now,
            rule_id=rule_id,
            run_id=run_id,
        )

    @pytest.mark.asyncio
    async def test_get_trigger_found(self, service, sample_trigger):
        """Test getting trigger by ID."""
        service.repository.get = AsyncMock(return_value=sample_trigger)

        result = await service.get_trigger(sample_trigger.id)

        assert result == sample_trigger

    @pytest.mark.asyncio
    async def test_get_trigger_not_found(self, service):
        """Test getting nonexistent trigger returns None."""
        service.repository.get = AsyncMock(return_value=None)

        result = await service.get_trigger(uuid4())

        assert result is None
