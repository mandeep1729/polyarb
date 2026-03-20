from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"

    id: Mapped[int] = mapped_column(init=False, primary_key=True, autoincrement=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("unified_markets.id", ondelete="RESTRICT"))
    outcome_prices: Mapped[dict] = mapped_column(JSONB, default_factory=dict)
    volume: Mapped[float | None] = mapped_column(Float, default=None)
    timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=None,
    )

    __table_args__ = (
        UniqueConstraint("market_id", "timestamp", name="uq_price_snapshots_market_ts"),
        Index("ix_price_snapshots_market_timestamp", "market_id", "timestamp"),
    )
