"""Market group models for clustering similar markets across platforms.

Groups are seeded from platform-native clusters (Kalshi event_ticker,
Polymarket slug) and merged cross-platform via TF-IDF similarity.

    market_groups (1) ──── (*) market_group_members (*) ──── (1) unified_markets
"""
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MarketGroup(Base):
    """A cluster of related markets across one or more platforms."""

    __tablename__ = "market_groups"

    id: Mapped[int] = mapped_column(init=False, primary_key=True, autoincrement=True)
    canonical_question: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(100), default=None)
    source_event_ticker: Mapped[str | None] = mapped_column(String(255), default=None)
    consensus_yes: Mapped[float | None] = mapped_column(Float, default=None)
    consensus_no: Mapped[float | None] = mapped_column(Float, default=None)
    disagreement_score: Mapped[float | None] = mapped_column(Float, default=None)
    best_yes_market_id: Mapped[int | None] = mapped_column(
        ForeignKey("unified_markets.id", ondelete="SET NULL"), default=None
    )
    best_no_market_id: Mapped[int | None] = mapped_column(
        ForeignKey("unified_markets.id", ondelete="SET NULL"), default=None
    )
    member_count: Mapped[int] = mapped_column(Integer, default=0)
    total_volume: Mapped[float | None] = mapped_column(Float, default=None)
    total_liquidity: Mapped[float | None] = mapped_column(Float, default=None)
    match_confidence: Mapped[float | None] = mapped_column(Float, default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), init=False
    )

    __table_args__ = (
        Index("ix_market_groups_category", "category"),
        Index("ix_market_groups_disagreement", "disagreement_score"),
        Index("ix_market_groups_source_event", "source_event_ticker"),
        Index("ix_market_groups_is_active", "is_active"),
        Index(
            "ix_market_groups_question_trgm",
            "canonical_question",
            postgresql_using="gin",
            postgresql_ops={"canonical_question": "gin_trgm_ops"},
        ),
    )


class MarketGroupMember(Base):
    """Join table linking markets to groups (many-to-many)."""

    __tablename__ = "market_group_members"

    id: Mapped[int] = mapped_column(init=False, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("market_groups.id", ondelete="CASCADE")
    )
    market_id: Mapped[int] = mapped_column(
        ForeignKey("unified_markets.id", ondelete="CASCADE")
    )

    __table_args__ = (
        UniqueConstraint("group_id", "market_id", name="uq_group_market"),
        Index("ix_group_members_group_id", "group_id"),
        Index("ix_group_members_market_id", "market_id"),
    )
