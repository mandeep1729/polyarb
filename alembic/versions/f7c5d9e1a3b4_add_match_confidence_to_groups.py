"""add match_confidence to market_groups

Revision ID: f7c5d9e1a3b4
Revises: e6b4c8d2f3a7
Create Date: 2026-03-20

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "f7c5d9e1a3b4"
down_revision: Union[str, None] = "e6b4c8d2f3a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "market_groups",
        sa.Column("match_confidence", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("market_groups", "match_confidence")
