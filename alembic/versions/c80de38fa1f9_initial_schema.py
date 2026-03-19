"""initial_schema

Revision ID: c80de38fa1f9
Revises:
Create Date: 2026-03-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c80de38fa1f9"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # --- platforms ---
    op.create_table(
        "platforms",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=50), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=False),
        sa.Column("api_url", sa.String(length=500), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("slug"),
    )

    # --- unified_markets ---
    op.create_table(
        "unified_markets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("platform_id", sa.Integer(), nullable=False),
        sa.Column("platform_market_id", sa.String(length=255), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("outcomes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("outcome_prices", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("volume_total", sa.Float(), nullable=True),
        sa.Column("volume_24h", sa.Float(), nullable=True),
        sa.Column("liquidity", sa.Float(), nullable=True),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("resolution", sa.String(length=50), nullable=True),
        sa.Column("deep_link_url", sa.String(length=1000), nullable=True),
        sa.Column("image_url", sa.String(length=1000), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("price_change_24h", sa.Float(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["platform_id"], ["platforms.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_unified_markets_platform_market",
        "unified_markets",
        ["platform_id", "platform_market_id"],
        unique=True,
    )
    op.create_index("ix_unified_markets_category", "unified_markets", ["category"])
    op.create_index("ix_unified_markets_status", "unified_markets", ["status"])
    op.create_index("ix_unified_markets_end_date", "unified_markets", ["end_date"])
    op.create_index("ix_unified_markets_volume_24h", "unified_markets", ["volume_24h"])
    op.execute(
        "CREATE INDEX ix_unified_markets_question_trgm ON unified_markets "
        "USING gin (question gin_trgm_ops)"
    )

    # --- price_snapshots ---
    op.create_table(
        "price_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("outcome_prices", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("volume", sa.Float(), nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["market_id"], ["unified_markets.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_price_snapshots_market_timestamp",
        "price_snapshots",
        ["market_id", "timestamp"],
    )

    # --- matched_market_pairs ---
    op.create_table(
        "matched_market_pairs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("market_a_id", sa.Integer(), nullable=False),
        sa.Column("market_b_id", sa.Integer(), nullable=False),
        sa.Column("similarity_score", sa.Float(), nullable=False),
        sa.Column("odds_delta", sa.Float(), nullable=True),
        sa.Column("match_method", sa.String(length=50), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["market_a_id"], ["unified_markets.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["market_b_id"], ["unified_markets.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("market_a_id", "market_b_id", name="uq_matched_pair"),
        sa.CheckConstraint("market_a_id < market_b_id", name="ck_market_a_lt_b"),
    )


def downgrade() -> None:
    op.drop_table("matched_market_pairs")
    op.drop_table("price_snapshots")
    op.drop_index("ix_unified_markets_question_trgm", table_name="unified_markets")
    op.drop_index("ix_unified_markets_volume_24h", table_name="unified_markets")
    op.drop_index("ix_unified_markets_end_date", table_name="unified_markets")
    op.drop_index("ix_unified_markets_status", table_name="unified_markets")
    op.drop_index("ix_unified_markets_category", table_name="unified_markets")
    op.drop_index(
        "ix_unified_markets_platform_market", table_name="unified_markets"
    )
    op.drop_table("unified_markets")
    op.drop_table("platforms")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
