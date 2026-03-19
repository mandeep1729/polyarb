from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"

    id: Mapped[int] = mapped_column(init=False, primary_key=True, autoincrement=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("unified_markets.id", ondelete="CASCADE"))
    outcome_prices: Mapped[dict] = mapped_column(JSONB, default_factory=dict)
    volume: Mapped[float | None] = mapped_column(Float, default=None)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        init=False,
    )

    __table_args__ = (
        Index("ix_price_snapshots_market_timestamp", "market_id", "timestamp"),
    )
