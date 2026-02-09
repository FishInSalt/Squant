"""add circuit_breaker_events table

Revision ID: 7b07702de1bf
Revises: 41a7a4f3b3e6
Create Date: 2026-01-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "7b07702de1bf"
down_revision: str | None = "41a7a4f3b3e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "circuit_breaker_events",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trigger_type", sa.String(16), nullable=False),
        sa.Column("trigger_source", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(256), nullable=False),
        sa.Column("details", JSONB, nullable=False, server_default="{}"),
        sa.Column("sessions_stopped", sa.Integer, nullable=False, server_default="0"),
        sa.Column("positions_closed", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index(
        "idx_circuit_breaker_events_time",
        "circuit_breaker_events",
        ["time"],
    )


def downgrade() -> None:
    op.drop_index("idx_circuit_breaker_events_time", table_name="circuit_breaker_events")
    op.drop_table("circuit_breaker_events")
