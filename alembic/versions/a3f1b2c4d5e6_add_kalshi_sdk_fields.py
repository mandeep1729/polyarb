"""add kalshi sdk fields

Revision ID: a3f1b2c4d5e6
Revises: c80de38fa1f9
Create Date: 2026-03-18

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3f1b2c4d5e6"
down_revision: Union[str, None] = "c80de38fa1f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("unified_markets", sa.Column("event_ticker", sa.String(255), nullable=True))
    op.add_column("unified_markets", sa.Column("series_ticker", sa.String(255), nullable=True))
    op.add_column("unified_markets", sa.Column("yes_ask", sa.Float(), nullable=True))
    op.add_column("unified_markets", sa.Column("no_ask", sa.Float(), nullable=True))

    # Clear stale Kalshi data — will be repopulated by background sync
    op.execute(
        """
        DELETE FROM price_snapshots WHERE market_id IN (
            SELECT id FROM unified_markets WHERE platform_id IN (
                SELECT id FROM platforms WHERE slug = 'kalshi'
            )
        )
        """
    )
    op.execute(
        """
        DELETE FROM unified_markets WHERE platform_id IN (
            SELECT id FROM platforms WHERE slug = 'kalshi'
        )
        """
    )


def downgrade() -> None:
    op.drop_column("unified_markets", "no_ask")
    op.drop_column("unified_markets", "yes_ask")
    op.drop_column("unified_markets", "series_ticker")
    op.drop_column("unified_markets", "event_ticker")
