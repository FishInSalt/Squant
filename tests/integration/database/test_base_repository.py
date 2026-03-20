"""Integration tests for BaseRepository against a real PostgreSQL database.

Tests every public method of BaseRepository with real SQL execution:
- get, get_by, list, count, create, update, delete, exists, bulk_create
- Pagination, ordering, filtering (including None-skip behavior)
- Setting fields to NULL via update()
- Edge cases: non-existent IDs, empty filters, duplicate keys

Uses the Strategy model as the concrete model under test.
"""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from squant.infra.repository import BaseRepository
from squant.models.enums import StrategyStatus
from squant.models.strategy import Strategy

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_strategy(**overrides) -> dict:
    """Build a minimal Strategy creation dict."""
    defaults = {
        "name": f"strategy-{uuid4().hex[:8]}",
        "code": "class MyStrategy(Strategy):\n    def on_bar(self, bar): pass",
        "version": "1.0.0",
        "status": StrategyStatus.ACTIVE,
    }
    defaults.update(overrides)
    return defaults


class _StrategyRepo(BaseRepository[Strategy]):
    """Concrete repository binding for tests."""

    def __init__(self, session: AsyncSession):
        super().__init__(Strategy, session)


# ===========================================================================
# create
# ===========================================================================


class TestCreate:
    async def test_create_returns_instance_with_id(self, db_session):
        repo = _StrategyRepo(db_session)
        s = await repo.create(**_make_strategy(name="create-test"))
        assert s.id is not None
        assert s.name == "create-test"
        assert s.created_at is not None

    async def test_create_persists_to_database(self, db_session):
        repo = _StrategyRepo(db_session)
        s = await repo.create(**_make_strategy(name="persist-test"))
        found = await repo.get(s.id)
        assert found is not None
        assert found.name == "persist-test"

    async def test_create_with_optional_fields(self, db_session):
        repo = _StrategyRepo(db_session)
        s = await repo.create(
            **_make_strategy(
                name="with-desc",
                description="A detailed description",
            )
        )
        assert s.description == "A detailed description"

    async def test_create_without_optional_fields(self, db_session):
        repo = _StrategyRepo(db_session)
        s = await repo.create(**_make_strategy(name="no-desc"))
        assert s.description is None


# ===========================================================================
# get
# ===========================================================================


class TestGet:
    async def test_get_existing(self, db_session):
        repo = _StrategyRepo(db_session)
        s = await repo.create(**_make_strategy(name="get-existing"))
        result = await repo.get(s.id)
        assert result is not None
        assert result.id == s.id

    async def test_get_nonexistent_returns_none(self, db_session):
        repo = _StrategyRepo(db_session)
        result = await repo.get(str(uuid4()))
        assert result is None

    async def test_get_with_uuid_object(self, db_session):
        repo = _StrategyRepo(db_session)
        s = await repo.create(**_make_strategy(name="get-uuid"))
        # Pass UUID object instead of string
        from uuid import UUID

        result = await repo.get(UUID(s.id))
        assert result is not None
        assert result.id == s.id


# ===========================================================================
# get_by
# ===========================================================================


class TestGetBy:
    async def test_get_by_single_field(self, db_session):
        repo = _StrategyRepo(db_session)
        name = f"getby-{uuid4().hex[:8]}"
        await repo.create(**_make_strategy(name=name))
        result = await repo.get_by(name=name)
        assert result is not None
        assert result.name == name

    async def test_get_by_multiple_fields(self, db_session):
        repo = _StrategyRepo(db_session)
        name = f"getby-multi-{uuid4().hex[:8]}"
        await repo.create(
            **_make_strategy(
                name=name,
                version="2.0.0",
                status=StrategyStatus.ARCHIVED,
            )
        )
        result = await repo.get_by(name=name, version="2.0.0")
        assert result is not None
        assert result.name == name
        assert result.version == "2.0.0"

    async def test_get_by_no_match_returns_none(self, db_session):
        repo = _StrategyRepo(db_session)
        result = await repo.get_by(name="nonexistent-name-12345")
        assert result is None

    async def test_get_by_nullable_field(self, db_session):
        """get_by passes None directly as == None (IS NULL in SQL)."""
        repo = _StrategyRepo(db_session)
        name = f"getby-null-{uuid4().hex[:8]}"
        await repo.create(**_make_strategy(name=name, description=None))
        # This generates WHERE description IS NULL
        result = await repo.get_by(name=name, description=None)
        assert result is not None
        assert result.description is None


# ===========================================================================
# list
# ===========================================================================


class TestList:
    async def _seed(self, repo: _StrategyRepo, n: int = 5) -> list[Strategy]:
        """Create n strategies with predictable names."""
        prefix = uuid4().hex[:6]
        items = []
        for i in range(n):
            s = await repo.create(
                **_make_strategy(
                    name=f"{prefix}-{i:03d}",
                    status=StrategyStatus.ACTIVE if i % 2 == 0 else StrategyStatus.ARCHIVED,
                )
            )
            items.append(s)
        return items

    async def test_list_returns_all(self, db_session):
        repo = _StrategyRepo(db_session)
        created = await self._seed(repo, 3)
        results = await repo.list(limit=100)
        created_ids = {s.id for s in created}
        result_ids = {s.id for s in results}
        assert created_ids.issubset(result_ids)

    async def test_list_with_limit(self, db_session):
        repo = _StrategyRepo(db_session)
        await self._seed(repo, 5)
        results = await repo.list(limit=2)
        assert len(results) == 2

    async def test_list_with_offset(self, db_session):
        repo = _StrategyRepo(db_session)
        await self._seed(repo, 5)
        all_results = await repo.list(limit=100, order_by="name")
        offset_results = await repo.list(offset=2, limit=100, order_by="name")
        assert len(offset_results) == len(all_results) - 2
        assert offset_results[0].id == all_results[2].id

    async def test_list_with_order_by_asc(self, db_session):
        repo = _StrategyRepo(db_session)
        await self._seed(repo, 3)
        results = await repo.list(order_by="name", desc=False, limit=100)
        names = [s.name for s in results]
        assert names == sorted(names)

    async def test_list_with_order_by_desc(self, db_session):
        repo = _StrategyRepo(db_session)
        await self._seed(repo, 3)
        results = await repo.list(order_by="name", desc=True, limit=100)
        names = [s.name for s in results]
        assert names == sorted(names, reverse=True)

    async def test_list_with_filter(self, db_session):
        repo = _StrategyRepo(db_session)
        created = await self._seed(repo, 6)
        active_ids = {s.id for s in created if s.status == StrategyStatus.ACTIVE}
        results = await repo.list(status=StrategyStatus.ACTIVE, limit=100)
        result_ids = {s.id for s in results}
        assert active_ids.issubset(result_ids)
        for s in results:
            assert s.status == StrategyStatus.ACTIVE

    async def test_list_none_filter_is_skipped(self, db_session):
        """Passing None as a filter value should skip that filter (not IS NULL)."""
        repo = _StrategyRepo(db_session)
        created = await self._seed(repo, 3)
        # status=None should be ignored, returning all
        results = await repo.list(status=None, limit=100)
        created_ids = {s.id for s in created}
        result_ids = {s.id for s in results}
        assert created_ids.issubset(result_ids)

    async def test_list_empty_result(self, db_session):
        repo = _StrategyRepo(db_session)
        results = await repo.list(status="nonexistent_status", limit=100)
        assert results == []

    async def test_list_pagination(self, db_session):
        """Verify offset + limit gives correct pages."""
        repo = _StrategyRepo(db_session)
        await self._seed(repo, 6)

        page1 = await repo.list(order_by="name", offset=0, limit=3)
        page2 = await repo.list(order_by="name", offset=3, limit=3)

        page1_ids = [s.id for s in page1]
        page2_ids = [s.id for s in page2]
        # No overlap
        assert set(page1_ids).isdisjoint(set(page2_ids))


# ===========================================================================
# count
# ===========================================================================


class TestCount:
    async def test_count_all(self, db_session):
        repo = _StrategyRepo(db_session)
        prefix = uuid4().hex[:6]
        for i in range(3):
            await repo.create(**_make_strategy(name=f"{prefix}-count-{i}"))
        total = await repo.count()
        assert total >= 3

    async def test_count_with_filter(self, db_session):
        repo = _StrategyRepo(db_session)
        prefix = uuid4().hex[:6]
        for i in range(4):
            status = StrategyStatus.ACTIVE if i < 2 else StrategyStatus.ARCHIVED
            await repo.create(**_make_strategy(name=f"{prefix}-cf-{i}", status=status))
        archived = await repo.count(status=StrategyStatus.ARCHIVED)
        assert archived >= 2

    async def test_count_none_filter_is_skipped(self, db_session):
        repo = _StrategyRepo(db_session)
        prefix = uuid4().hex[:6]
        for i in range(2):
            await repo.create(**_make_strategy(name=f"{prefix}-cn-{i}"))
        total = await repo.count()
        filtered = await repo.count(status=None)
        assert total == filtered

    async def test_count_no_matches(self, db_session):
        repo = _StrategyRepo(db_session)
        c = await repo.count(name="absolutely-nonexistent-name-xyz")
        assert c == 0


# ===========================================================================
# update
# ===========================================================================


class TestUpdate:
    async def test_update_single_field(self, db_session):
        repo = _StrategyRepo(db_session)
        s = await repo.create(**_make_strategy(name="update-single"))
        updated = await repo.update(s.id, name="updated-name")
        assert updated is not None
        assert updated.name == "updated-name"

    async def test_update_multiple_fields(self, db_session):
        repo = _StrategyRepo(db_session)
        s = await repo.create(**_make_strategy(name="update-multi"))
        updated = await repo.update(
            s.id,
            name="new-name",
            version="2.0.0",
            description="new desc",
        )
        assert updated is not None
        assert updated.name == "new-name"
        assert updated.version == "2.0.0"
        assert updated.description == "new desc"

    async def test_update_set_field_to_null(self, db_session):
        """update() should allow setting a nullable field to NULL."""
        repo = _StrategyRepo(db_session)
        s = await repo.create(
            **_make_strategy(
                name="update-null",
                description="has a description",
            )
        )
        assert s.description == "has a description"
        updated = await repo.update(s.id, description=None)
        assert updated is not None
        assert updated.description is None

    async def test_update_nonexistent_returns_none(self, db_session):
        repo = _StrategyRepo(db_session)
        result = await repo.update(str(uuid4()), name="ghost")
        assert result is None

    async def test_update_empty_data_returns_unchanged(self, db_session):
        repo = _StrategyRepo(db_session)
        s = await repo.create(**_make_strategy(name="update-empty"))
        result = await repo.update(s.id)
        assert result is not None
        assert result.name == "update-empty"

    async def test_update_persists(self, db_session):
        """Verify update is visible via a fresh get()."""
        repo = _StrategyRepo(db_session)
        s = await repo.create(**_make_strategy(name="update-persist"))
        await repo.update(s.id, name="persisted-name")
        fresh = await repo.get(s.id)
        assert fresh is not None
        assert fresh.name == "persisted-name"


# ===========================================================================
# delete
# ===========================================================================


class TestDelete:
    async def test_delete_existing(self, db_session):
        repo = _StrategyRepo(db_session)
        s = await repo.create(**_make_strategy(name="delete-me"))
        deleted = await repo.delete(s.id)
        assert deleted is True
        assert await repo.get(s.id) is None

    async def test_delete_nonexistent_returns_false(self, db_session):
        repo = _StrategyRepo(db_session)
        deleted = await repo.delete(str(uuid4()))
        assert deleted is False

    async def test_delete_is_permanent(self, db_session):
        repo = _StrategyRepo(db_session)
        s = await repo.create(**_make_strategy(name="delete-perm"))
        await repo.delete(s.id)
        assert await repo.exists(s.id) is False


# ===========================================================================
# exists
# ===========================================================================


class TestExists:
    async def test_exists_true(self, db_session):
        repo = _StrategyRepo(db_session)
        s = await repo.create(**_make_strategy(name="exists-true"))
        assert await repo.exists(s.id) is True

    async def test_exists_false(self, db_session):
        repo = _StrategyRepo(db_session)
        assert await repo.exists(str(uuid4())) is False

    async def test_exists_after_delete(self, db_session):
        repo = _StrategyRepo(db_session)
        s = await repo.create(**_make_strategy(name="exists-del"))
        await repo.delete(s.id)
        assert await repo.exists(s.id) is False


# ===========================================================================
# bulk_create
# ===========================================================================


class TestBulkCreate:
    async def test_bulk_create_multiple(self, db_session):
        repo = _StrategyRepo(db_session)
        prefix = uuid4().hex[:6]
        items = [_make_strategy(name=f"{prefix}-bulk-{i}") for i in range(5)]
        created = await repo.bulk_create(items)
        assert len(created) == 5
        for s in created:
            assert s.id is not None
            assert s.created_at is not None

    async def test_bulk_create_persists(self, db_session):
        repo = _StrategyRepo(db_session)
        prefix = uuid4().hex[:6]
        items = [_make_strategy(name=f"{prefix}-bp-{i}") for i in range(3)]
        created = await repo.bulk_create(items)
        for s in created:
            found = await repo.get(s.id)
            assert found is not None

    async def test_bulk_create_empty_list(self, db_session):
        repo = _StrategyRepo(db_session)
        created = await repo.bulk_create([])
        assert created == []

    async def test_bulk_create_single_item(self, db_session):
        repo = _StrategyRepo(db_session)
        items = [_make_strategy(name=f"bulk-single-{uuid4().hex[:8]}")]
        created = await repo.bulk_create(items)
        assert len(created) == 1


# ===========================================================================
# Cross-method scenarios
# ===========================================================================


class TestCrossMethodScenarios:
    async def test_create_then_list_then_delete(self, db_session):
        """Full CRUD lifecycle."""
        repo = _StrategyRepo(db_session)
        s = await repo.create(**_make_strategy(name=f"lifecycle-{uuid4().hex[:8]}"))
        assert await repo.exists(s.id)

        results = await repo.list(limit=100)
        assert any(r.id == s.id for r in results)

        await repo.update(s.id, description="updated")
        refreshed = await repo.get(s.id)
        assert refreshed.description == "updated"

        await repo.delete(s.id)
        assert not await repo.exists(s.id)

    async def test_count_matches_list_length(self, db_session):
        """count() and len(list()) should agree for the same filter."""
        repo = _StrategyRepo(db_session)
        prefix = uuid4().hex[:6]
        for i in range(4):
            await repo.create(
                **_make_strategy(
                    name=f"{prefix}-match-{i}",
                    status=StrategyStatus.ARCHIVED,
                )
            )
        count = await repo.count(status=StrategyStatus.ARCHIVED)
        items = await repo.list(status=StrategyStatus.ARCHIVED, limit=1000)
        assert count == len(items)

    async def test_update_does_not_affect_other_records(self, db_session):
        repo = _StrategyRepo(db_session)
        s1 = await repo.create(**_make_strategy(name=f"iso-1-{uuid4().hex[:8]}"))
        s2 = await repo.create(**_make_strategy(name=f"iso-2-{uuid4().hex[:8]}"))
        original_s2_name = s2.name

        await repo.update(s1.id, name="changed")
        s2_fresh = await repo.get(s2.id)
        assert s2_fresh.name == original_s2_name
