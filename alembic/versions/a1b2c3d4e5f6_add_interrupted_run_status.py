"""add interrupted run status

Revision ID: a1b2c3d4e5f6
Revises: f7bb3cc13521
Create Date: 2026-02-24 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "f7bb3cc13521"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # status column is VARCHAR(16), no schema change needed.
    # Backfill existing infrastructure-caused errors to 'interrupted'.
    op.execute(
        "UPDATE strategy_runs SET status = 'interrupted' "
        "WHERE status = 'error' "
        "AND (error_message LIKE '%application restart%' "
        "     OR error_message LIKE '%Session timeout%')"
    )


def downgrade() -> None:
    # Only revert rows that were changed by upgrade(), not new application-written rows
    op.execute(
        "UPDATE strategy_runs SET status = 'error' "
        "WHERE status = 'interrupted' "
        "AND (error_message LIKE '%application restart%' "
        "     OR error_message LIKE '%Session timeout%')"
    )
