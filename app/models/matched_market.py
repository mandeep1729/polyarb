from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MatchedMarketPair(Base):
    __tablename__ = "matched_market_pairs"

    id: Mapped[int] = mapped_column(init=False, primary_key=True, autoincrement=True)
    market_a_id: Mapped[int] = mapped_column(ForeignKey("unified_markets.id", ondelete="CASCADE"))
    market_b_id: Mapped[int] = mapped_column(ForeignKey("unified_markets.id", ondelete="CASCADE"))
    similarity_score: Mapped[float] = mapped_column(Float)
    odds_delta: Mapped[float | None] = mapped_column(Float, default=None)
    match_method: Mapped[str] = mapped_column(String(50), default="tfidf_fuzzy")
    category: Mapped[str | None] = mapped_column(String(100), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        init=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        init=False,
    )

    __table_args__ = (
        UniqueConstraint("market_a_id", "market_b_id", name="uq_matched_pair"),
        CheckConstraint("market_a_id < market_b_id", name="ck_market_a_lt_b"),
    )
