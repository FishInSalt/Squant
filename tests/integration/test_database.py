"""Integration tests for database layer."""

import pytest
from sqlalchemy import text

from squant.infra.database import get_session_context


@pytest.mark.asyncio
async def test_database_connection():
    """Test database connection works."""
    async with get_session_context() as session:
        result = await session.execute(text("SELECT 1"))
        assert result.scalar() == 1
