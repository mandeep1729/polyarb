"""add_unique_price_snapshots

Revision ID: d5a3e7f9b1c2
Revises: b4e2f7a8c9d1
Create Date: 2026-03-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5a3e7f9b1c2"
down_revision: Union[str, None] = "b4e2f7a8c9d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Deduplicate existing rows: keep the latest id for each (market_id, timestamp)
    op.execute(
        """
        DELETE FROM price_snapshots a
        USING price_snapshots b
        WHERE a.market_id = b.market_id
          AND a.timestamp = b.timestamp
          AND a.id < b.id
        """
    )

    # Drop the existing non-unique index
    op.drop_index("ix_price_snapshots_market_timestamp", table_name="price_snapshots")

    # Add unique constraint (implicitly creates an index)
    op.create_unique_constraint(
        "uq_price_snapshots_market_ts",
        "price_snapshots",
        ["market_id", "timestamp"],
    )

    # Re-create the index explicitly for query performance
    op.create_index(
        "ix_price_snapshots_market_timestamp",
        "price_snapshots",
        ["market_id", "timestamp"],
    )

    # Allow NULL default on timestamp column (server_default still applies)
    op.alter_column(
        "price_snapshots",
        "timestamp",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
        existing_server_default=sa.text("now()"),
    )


def downgrade() -> None:
    op.alter_column(
        "price_snapshots",
        "timestamp",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.drop_index("ix_price_snapshots_market_timestamp", table_name="price_snapshots")
    op.drop_constraint("uq_price_snapshots_market_ts", "price_snapshots", type_="unique")
    op.create_index(
        "ix_price_snapshots_market_timestamp",
        "price_snapshots",
        ["market_id", "timestamp"],
    )
