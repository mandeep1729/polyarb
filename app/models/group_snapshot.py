"""Materialized group-level price snapshots for fast historical queries."""
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class GroupPriceSnapshot(Base):
    """Hourly snapshot of group consensus analytics."""

    __tablename__ = "group_price_snapshots"

    id: Mapped[int] = mapped_column(init=False, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("market_groups.id", ondelete="CASCADE")
    )
    consensus_yes: Mapped[float | None] = mapped_column(Float, default=None)
    consensus_no: Mapped[float | None] = mapped_column(Float, default=None)
    disagreement_score: Mapped[float | None] = mapped_column(Float, default=None)
    total_volume: Mapped[float | None] = mapped_column(Float, default=None)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )

    __table_args__ = (
        Index("ix_group_snapshots_group_timestamp", "group_id", "timestamp"),
    )
