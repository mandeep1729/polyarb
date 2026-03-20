"""Protect price history from cascade deletes

Change price_snapshots FK from CASCADE to RESTRICT so that
deleting a market row is blocked while it has price history.

Revision ID: g8d6e2f4a5b7
Revises: f7c5d9e1a3b4
Create Date: 2026-03-20

"""
from typing import Sequence, Union

from alembic import op

revision: str = "g8d6e2f4a5b7"
down_revision: Union[str, None] = "f7c5d9e1a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "price_snapshots_market_id_fkey", "price_snapshots", type_="foreignkey"
    )
    op.create_foreign_key(
        "price_snapshots_market_id_fkey",
        "price_snapshots",
        "unified_markets",
        ["market_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "price_snapshots_market_id_fkey", "price_snapshots", type_="foreignkey"
    )
    op.create_foreign_key(
        "price_snapshots_market_id_fkey",
        "price_snapshots",
        "unified_markets",
        ["market_id"],
        ["id"],
        ondelete="CASCADE",
    )
