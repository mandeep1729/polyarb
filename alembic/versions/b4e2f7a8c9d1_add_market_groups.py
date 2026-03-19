"""add market groups

Revision ID: b4e2f7a8c9d1
Revises: a3f1b2c4d5e6
Create Date: 2026-03-18

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "b4e2f7a8c9d1"
down_revision: Union[str, None] = "a3f1b2c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- market_groups ---
    op.create_table(
        "market_groups",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("canonical_question", sa.Text(), nullable=False),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("source_event_ticker", sa.String(255), nullable=True),
        sa.Column("consensus_yes", sa.Float(), nullable=True),
        sa.Column("consensus_no", sa.Float(), nullable=True),
        sa.Column("disagreement_score", sa.Float(), nullable=True),
        sa.Column("best_yes_market_id", sa.Integer(), nullable=True),
        sa.Column("best_no_market_id", sa.Integer(), nullable=True),
        sa.Column("member_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_volume", sa.Float(), nullable=True),
        sa.Column("total_liquidity", sa.Float(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["best_yes_market_id"], ["unified_markets.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["best_no_market_id"], ["unified_markets.id"], ondelete="SET NULL"
        ),
    )
    op.create_index("ix_market_groups_category", "market_groups", ["category"])
    op.create_index("ix_market_groups_disagreement", "market_groups", ["disagreement_score"])
    op.create_index("ix_market_groups_source_event", "market_groups", ["source_event_ticker"])
    op.create_index("ix_market_groups_is_active", "market_groups", ["is_active"])

    # --- market_group_members ---
    op.create_table(
        "market_group_members",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["group_id"], ["market_groups.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["market_id"], ["unified_markets.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("group_id", "market_id", name="uq_group_market"),
    )
    op.create_index("ix_group_members_group_id", "market_group_members", ["group_id"])
    op.create_index("ix_group_members_market_id", "market_group_members", ["market_id"])

    # --- group_price_snapshots ---
    op.create_table(
        "group_price_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("consensus_yes", sa.Float(), nullable=True),
        sa.Column("consensus_no", sa.Float(), nullable=True),
        sa.Column("disagreement_score", sa.Float(), nullable=True),
        sa.Column("total_volume", sa.Float(), nullable=True),
        sa.Column(
            "timestamp", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["group_id"], ["market_groups.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_group_snapshots_group_timestamp",
        "group_price_snapshots",
        ["group_id", "timestamp"],
    )


def downgrade() -> None:
    op.drop_table("group_price_snapshots")
    op.drop_index("ix_group_members_market_id", table_name="market_group_members")
    op.drop_index("ix_group_members_group_id", table_name="market_group_members")
    op.drop_table("market_group_members")
    op.drop_index("ix_market_groups_is_active", table_name="market_groups")
    op.drop_index("ix_market_groups_source_event", table_name="market_groups")
    op.drop_index("ix_market_groups_disagreement", table_name="market_groups")
    op.drop_index("ix_market_groups_category", table_name="market_groups")
    op.drop_table("market_groups")
