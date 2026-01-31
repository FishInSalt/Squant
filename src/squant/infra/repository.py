"""Base repository for CRUD operations."""

from __future__ import annotations

from typing import Any, TypeVar
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from squant.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository[ModelT: Base]:
    """Generic repository for CRUD operations."""

    def __init__(self, model: type[ModelT], session: AsyncSession):
        self.model = model
        self.session = session

    async def get(self, id: str | UUID) -> ModelT | None:
        """Get a single record by ID."""
        result = await self.session.execute(select(self.model).where(self.model.id == str(id)))
        return result.scalar_one_or_none()

    async def get_by(self, **kwargs: Any) -> ModelT | None:
        """Get a single record by arbitrary filters."""
        stmt = select(self.model)
        for key, value in kwargs.items():
            stmt = stmt.where(getattr(self.model, key) == value)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
        order_by: str | None = None,
        desc: bool = False,
        **filters: Any,
    ) -> list[ModelT]:
        """List records with pagination and filtering."""
        stmt = select(self.model)

        # Apply filters
        for key, value in filters.items():
            if value is not None:
                stmt = stmt.where(getattr(self.model, key) == value)

        # Apply ordering
        if order_by:
            col = getattr(self.model, order_by)
            stmt = stmt.order_by(col.desc() if desc else col)

        # Apply pagination
        stmt = stmt.offset(offset).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, **filters: Any) -> int:
        """Count records with optional filtering."""
        stmt = select(func.count()).select_from(self.model)
        for key, value in filters.items():
            if value is not None:
                stmt = stmt.where(getattr(self.model, key) == value)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def create(self, **data: Any) -> ModelT:
        """Create a new record."""
        instance = self.model(**data)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def update(self, id: str | UUID, **data: Any) -> ModelT | None:
        """Update a record by ID."""
        # Remove None values to avoid overwriting with None
        data = {k: v for k, v in data.items() if v is not None}
        if not data:
            return await self.get(id)

        await self.session.execute(
            update(self.model).where(self.model.id == str(id)).values(**data)
        )
        await self.session.flush()
        return await self.get(id)

    async def delete(self, id: str | UUID) -> bool:
        """Delete a record by ID."""
        result = await self.session.execute(delete(self.model).where(self.model.id == str(id)))
        await self.session.flush()
        return result.rowcount > 0

    async def exists(self, id: str | UUID) -> bool:
        """Check if a record exists."""
        stmt = select(func.count()).select_from(self.model).where(self.model.id == str(id))
        result = await self.session.execute(stmt)
        return result.scalar_one() > 0

    async def bulk_create(self, items: list[dict[str, Any]]) -> list[ModelT]:
        """Create multiple records."""
        instances = [self.model(**item) for item in items]
        self.session.add_all(instances)
        await self.session.flush()
        for instance in instances:
            await self.session.refresh(instance)
        return instances
