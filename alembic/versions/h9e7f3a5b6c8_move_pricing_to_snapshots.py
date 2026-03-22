"""Move pricing data from unified_markets to price_snapshots.

1. Add pricing columns to price_snapshots
2. Rename volume -> volume_24h
3. Add DESC index for DISTINCT ON lookups
4. Backfill latest snapshot per market from unified_markets values
5. Drop pricing columns from unified_markets

Revision ID: h9e7f3a5b6c8
Revises: g8d6e2f4a5b7
Create Date: 2026-03-21

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "h9e7f3a5b6c8"
down_revision: Union[str, None] = "g8d6e2f4a5b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add new columns to price_snapshots
    op.add_column("price_snapshots", sa.Column("volume_total", sa.Float, nullable=True))
    op.add_column("price_snapshots", sa.Column("liquidity", sa.Float, nullable=True))
    op.add_column("price_snapshots", sa.Column("yes_ask", sa.Float, nullable=True))
    op.add_column("price_snapshots", sa.Column("no_ask", sa.Float, nullable=True))
    op.add_column("price_snapshots", sa.Column("price_change_24h", sa.Float, nullable=True))

    # 2. Rename volume -> volume_24h
    op.alter_column("price_snapshots", "volume", new_column_name="volume_24h")

    # 3. Add DESC index for efficient DISTINCT ON, drop old forward index
    op.execute(
        "CREATE INDEX ix_price_snapshots_market_ts_desc "
        "ON price_snapshots (market_id, timestamp DESC)"
    )
    op.drop_index("ix_price_snapshots_market_timestamp", table_name="price_snapshots")

    # 4. Backfill: update latest snapshot per market with pricing from unified_markets
    op.execute("""
        UPDATE price_snapshots ps
        SET
            volume_total = um.volume_total,
            volume_24h = COALESCE(ps.volume_24h, um.volume_24h),
            liquidity = um.liquidity,
            yes_ask = um.yes_ask,
            no_ask = um.no_ask,
            price_change_24h = um.price_change_24h
        FROM (
            SELECT DISTINCT ON (market_id) id, market_id
            FROM price_snapshots
            ORDER BY market_id, timestamp DESC
        ) latest
        JOIN unified_markets um ON um.id = latest.market_id
        WHERE ps.id = latest.id
    """)

    # 4b. Insert snapshots for markets that have no existing snapshot
    op.execute("""
        INSERT INTO price_snapshots (
            market_id, outcome_prices, volume_24h, volume_total,
            liquidity, yes_ask, no_ask, price_change_24h, timestamp
        )
        SELECT
            um.id,
            um.outcome_prices,
            um.volume_24h,
            um.volume_total,
            um.liquidity,
            um.yes_ask,
            um.no_ask,
            um.price_change_24h,
            COALESCE(um.last_synced_at, um.updated_at, NOW())
        FROM unified_markets um
        LEFT JOIN price_snapshots ps ON ps.market_id = um.id
        WHERE ps.id IS NULL
        AND um.outcome_prices IS NOT NULL
        AND um.outcome_prices != '{}'::jsonb
    """)

    # 5. Drop pricing columns from unified_markets
    op.drop_index("ix_unified_markets_volume_24h", table_name="unified_markets")
    op.drop_column("unified_markets", "outcome_prices")
    op.drop_column("unified_markets", "volume_total")
    op.drop_column("unified_markets", "volume_24h")
    op.drop_column("unified_markets", "liquidity")
    op.drop_column("unified_markets", "yes_ask")
    op.drop_column("unified_markets", "no_ask")
    op.drop_column("unified_markets", "price_change_24h")
    op.drop_column("unified_markets", "last_synced_at")


def downgrade() -> None:
    # Re-add columns to unified_markets
    op.add_column("unified_markets", sa.Column("outcome_prices", JSONB, server_default=sa.text("'{}'::jsonb")))
    op.add_column("unified_markets", sa.Column("volume_total", sa.Float, nullable=True))
    op.add_column("unified_markets", sa.Column("volume_24h", sa.Float, nullable=True))
    op.add_column("unified_markets", sa.Column("liquidity", sa.Float, nullable=True))
    op.add_column("unified_markets", sa.Column("yes_ask", sa.Float, nullable=True))
    op.add_column("unified_markets", sa.Column("no_ask", sa.Float, nullable=True))
    op.add_column("unified_markets", sa.Column("price_change_24h", sa.Float, nullable=True))
    op.add_column("unified_markets", sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_unified_markets_volume_24h", "unified_markets", ["volume_24h"])

    # Restore pricing from latest snapshots
    op.execute("""
        UPDATE unified_markets um
        SET
            outcome_prices = snap.outcome_prices,
            volume_total = snap.volume_total,
            volume_24h = snap.volume_24h,
            liquidity = snap.liquidity,
            yes_ask = snap.yes_ask,
            no_ask = snap.no_ask,
            price_change_24h = snap.price_change_24h,
            last_synced_at = snap.timestamp
        FROM (
            SELECT DISTINCT ON (market_id) *
            FROM price_snapshots
            ORDER BY market_id, timestamp DESC
        ) snap
        WHERE um.id = snap.market_id
    """)

    # Restore old index, drop DESC index
    op.create_index("ix_price_snapshots_market_timestamp", "price_snapshots", ["market_id", "timestamp"])
    op.execute("DROP INDEX ix_price_snapshots_market_ts_desc")

    # Rename volume_24h back to volume
    op.alter_column("price_snapshots", "volume_24h", new_column_name="volume")

    # Drop new columns from price_snapshots
    op.drop_column("price_snapshots", "volume_total")
    op.drop_column("price_snapshots", "liquidity")
    op.drop_column("price_snapshots", "yes_ask")
    op.drop_column("price_snapshots", "no_ask")
    op.drop_column("price_snapshots", "price_change_24h")
