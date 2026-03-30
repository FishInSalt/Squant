"""make risk_triggers rule_id nullable

Revision ID: b3f1a2c4d5e7
Revises: e62be619bcc6
Create Date: 2026-03-18 00:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b3f1a2c4d5e7"
down_revision: str | None = "e62be619bcc6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The model defines rule_id as nullable (to support in-memory risk checks
    # without DB rules), but the initial migration created it as NOT NULL.
    # This caused NotNullViolationError when persisting engine-level risk
    # triggers (e.g., order rejections) that aren't linked to a specific rule.
    op.alter_column(
        "risk_triggers",
        "rule_id",
        existing_type=postgresql.UUID(as_uuid=False),
        nullable=True,
    )


def downgrade() -> None:
    # Note: downgrade will fail if any rows have NULL rule_id
    op.alter_column(
        "risk_triggers",
        "rule_id",
        existing_type=postgresql.UUID(as_uuid=False),
        nullable=False,
    )
