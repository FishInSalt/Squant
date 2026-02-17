"""add benchmark_equity to equity_curves

Revision ID: f7bb3cc13521
Revises: 99cce873d552
Create Date: 2026-02-17 07:05:54.642686

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7bb3cc13521'
down_revision: Union[str, None] = '99cce873d552'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('equity_curves', sa.Column('benchmark_equity', sa.Numeric(precision=20, scale=8), nullable=True))


def downgrade() -> None:
    op.drop_column('equity_curves', 'benchmark_equity')
