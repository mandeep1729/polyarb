from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UnifiedMarket(Base):
    __tablename__ = "unified_markets"

    id: Mapped[int] = mapped_column(init=False, primary_key=True, autoincrement=True)
    platform_id: Mapped[int] = mapped_column(ForeignKey("platforms.id"))
    platform_market_id: Mapped[str] = mapped_column(String(255))
    question: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    category: Mapped[str | None] = mapped_column(String(100), default=None)
    outcomes: Mapped[dict] = mapped_column(JSONB, default_factory=dict)
    start_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    end_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    status: Mapped[str] = mapped_column(String(20), default="active")
    resolution: Mapped[str | None] = mapped_column(String(50), default=None)
    deep_link_url: Mapped[str | None] = mapped_column(String(1000), default=None)
    image_url: Mapped[str | None] = mapped_column(String(1000), default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    event_ticker: Mapped[str | None] = mapped_column(String(255), default=None)
    series_ticker: Mapped[str | None] = mapped_column(String(255), default=None)
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
        Index("ix_unified_markets_platform_market", "platform_id", "platform_market_id", unique=True),
        Index("ix_unified_markets_category", "category"),
        Index("ix_unified_markets_status", "status"),
        Index("ix_unified_markets_end_date", "end_date"),
        Index("ix_unified_markets_question_trgm", "question", postgresql_using="gin",
              postgresql_ops={"question": "gin_trgm_ops"}),
    )
