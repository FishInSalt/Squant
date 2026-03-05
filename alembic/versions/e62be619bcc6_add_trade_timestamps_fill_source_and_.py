"""add Trade timestamps, fill_source, and Order exchange_oid unique constraint

Revision ID: e62be619bcc6
Revises: 538fd3eef394
Create Date: 2026-03-05 03:42:59.236003

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e62be619bcc6'
down_revision: Union[str, None] = '538fd3eef394'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # LIVE-AU-002: partial unique index on (exchange, exchange_oid) where exchange_oid IS NOT NULL
    op.create_index(
        'uq_orders_exchange_oid',
        'orders',
        ['exchange', 'exchange_oid'],
        unique=True,
        postgresql_where='exchange_oid IS NOT NULL',
    )

    # LIVE-EX-003: fill source tracking (ws vs poll)
    op.add_column('trades', sa.Column('fill_source', sa.String(length=8), nullable=True))

    # LIVE-AU-001: server-side ingestion timestamps
    op.add_column('trades', sa.Column(
        'created_at', sa.DateTime(timezone=True),
        server_default=sa.text('now()'), nullable=False,
    ))
    op.add_column('trades', sa.Column(
        'updated_at', sa.DateTime(timezone=True),
        server_default=sa.text('now()'), nullable=False,
    ))


def downgrade() -> None:
    op.drop_column('trades', 'updated_at')
    op.drop_column('trades', 'created_at')
    op.drop_column('trades', 'fill_source')
    op.drop_index('uq_orders_exchange_oid', table_name='orders', postgresql_where='exchange_oid IS NOT NULL')
