"""add_group_question_trgm_index

Revision ID: e6b4c8d2f3a7
Revises: d5a3e7f9b1c2
Create Date: 2026-03-19

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e6b4c8d2f3a7"
down_revision: Union[str, None] = "d5a3e7f9b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pg_trgm extension (idempotent)
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    # GIN trigram index for fast ILIKE / similarity search on group questions
    op.execute(
        "CREATE INDEX ix_market_groups_question_trgm "
        "ON market_groups USING gin (canonical_question gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_market_groups_question_trgm")
