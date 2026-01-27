"""fix exchange_type enum to use uppercase values

Revision ID: f9bf8cb0ef08
Revises: 82bc6c0b93cc
Create Date: 2026-01-24 17:54:51.331799+00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f9bf8cb0ef08"
down_revision: Union[str, Sequence[str], None] = "82bc6c0b93cc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 删除旧的 enum 类型和列
    op.execute("ALTER TYPE exchangetype RENAME TO exchangetype_old")

    # 创建新的 enum 类型（使用大写值）
    exchangetype_enum = sa.Enum("BINANCE", "OKX", "HUOBI", name="exchangetype")
    exchangetype_enum.create(op.get_bind())

    # 更新列以使用新的 enum 类型
    op.execute(
        "ALTER TABLE exchange_accounts ALTER COLUMN exchange TYPE exchangetype USING exchange::text::exchangetype"
    )

    # 删除旧的 enum 类型
    op.execute("DROP TYPE exchangetype_old")


def downgrade() -> None:
    """Downgrade schema."""
    pass
