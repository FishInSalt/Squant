"""add description column to risk_rules

Revision ID: 99cce873d552
Revises: 7b07702de1bf
Create Date: 2026-02-08 12:38:18.940812

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '99cce873d552'
down_revision: Union[str, None] = '7b07702de1bf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('risk_rules', sa.Column('description', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('risk_rules', 'description')
