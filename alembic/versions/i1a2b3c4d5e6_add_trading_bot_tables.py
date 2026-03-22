"""Add trading bot tables (bots, orders, trades) and outcome_mapping column.

Revision ID: i1a2b3c4d5e6
Revises: h9e7f3a5b6c8
Create Date: 2026-03-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "i1a2b3c4d5e6"
down_revision: Union[str, None] = "h9e7f3a5b6c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add outcome_mapping to matched_market_pairs
    op.add_column(
        "matched_market_pairs",
        sa.Column("outcome_mapping", JSONB, nullable=True),
    )

    # Create bots table
    op.create_table(
        "bots",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("pair_id", sa.Integer, sa.ForeignKey("matched_market_pairs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("strategy_name", sa.String(50), nullable=False),
        sa.Column("config", JSONB, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(20), nullable=False, server_default="created"),
        sa.Column("pause_reason", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_bots_pair_id", "bots", ["pair_id"])
    op.create_index("ix_bots_status", "bots", ["status"])

    # Create orders table
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("bot_id", sa.Integer, sa.ForeignKey("bots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("market_id", sa.Integer, sa.ForeignKey("unified_markets.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("platform_order_id", sa.String(255), nullable=True),
        sa.Column("side", sa.String(10), nullable=False),
        sa.Column("outcome", sa.String(100), nullable=False),
        sa.Column("price", sa.Float, nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("filled_quantity", sa.Integer, nullable=False, server_default="0"),
        sa.Column("avg_fill_price", sa.Float, nullable=True),
        sa.Column("fee", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_orders_bot_id", "orders", ["bot_id"])
    op.create_index("ix_orders_status", "orders", ["status"])

    # Create trades table
    op.create_table(
        "trades",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("bot_id", sa.Integer, sa.ForeignKey("bots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("leg_a_order_id", sa.Integer, sa.ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("leg_b_order_id", sa.Integer, sa.ForeignKey("orders.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("spread_at_entry", sa.Float, nullable=False),
        sa.Column("expected_profit", sa.Float, nullable=False),
        sa.Column("actual_profit", sa.Float, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_trades_bot_id", "trades", ["bot_id"])
    op.create_index("ix_trades_status", "trades", ["status"])


def downgrade() -> None:
    op.drop_table("trades")
    op.drop_table("orders")
    op.drop_table("bots")
    op.drop_column("matched_market_pairs", "outcome_mapping")
