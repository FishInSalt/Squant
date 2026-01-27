"""add is_demo field to exchange_accounts for demo trading support

Revision ID: 29fed7137c97
Revises: f9bf8cb0ef08
Create Date: 2026-01-26 08:39:05.955687+00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "29fed7137c97"
down_revision: Union[str, Sequence[str], None] = "f9bf8cb0ef08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 添加 is_demo 字段到 exchange_accounts 表
    op.add_column(
        "exchange_accounts",
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    # 删除 is_demo 字段
    op.drop_column("exchange_accounts", "is_demo")
