from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Bot state machine:
#
#   created ──start──→ running ──stop──→ stopped
#                         │
#                     rollback / error
#                         │
#                         ▼
#                      paused ──resume──→ running
#                         │
#                       stop
#                         │
#                         ▼
#                      stopped

_VALID_TRANSITIONS: dict[str, set[str]] = {
    "created": {"running", "stopped"},
    "running": {"paused", "stopped"},
    "paused": {"running", "stopped"},
    "stopped": {"running"},
}


class Bot(Base):
    __tablename__ = "bots"

    id: Mapped[int] = mapped_column(init=False, primary_key=True, autoincrement=True)
    pair_id: Mapped[int] = mapped_column(ForeignKey("matched_market_pairs.id", ondelete="CASCADE"))
    strategy_name: Mapped[str] = mapped_column(String(50))
    config: Mapped[dict] = mapped_column(JSONB, default_factory=dict)
    status: Mapped[str] = mapped_column(String(20), default="created")
    pause_reason: Mapped[str | None] = mapped_column(String(200), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), init=False,
    )

    __table_args__ = (
        Index("ix_bots_pair_id", "pair_id"),
        Index("ix_bots_status", "status"),
    )

    def transition_to(self, new_status: str, pause_reason: str | None = None) -> None:
        """Transition bot to a new status, raising ValueError on invalid transitions."""
        valid = _VALID_TRANSITIONS.get(self.status, set())
        if new_status not in valid:
            raise ValueError(
                f"Invalid transition: {self.status} → {new_status}. "
                f"Valid targets: {valid}"
            )
        self.status = new_status
        if new_status == "paused":
            self.pause_reason = pause_reason
        elif new_status == "running":
            self.pause_reason = None


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(init=False, primary_key=True, autoincrement=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"))
    market_id: Mapped[int] = mapped_column(ForeignKey("unified_markets.id", ondelete="RESTRICT"))
    platform: Mapped[str] = mapped_column(String(50))
    side: Mapped[str] = mapped_column(String(10))
    outcome: Mapped[str] = mapped_column(String(100))
    price: Mapped[float] = mapped_column(Float)
    quantity: Mapped[int] = mapped_column(Integer)
    # Fields with defaults must come after required fields (dataclass rule)
    platform_order_id: Mapped[str | None] = mapped_column(String(255), default=None)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    filled_quantity: Mapped[int] = mapped_column(Integer, default=0)
    avg_fill_price: Mapped[float | None] = mapped_column(Float, default=None)
    fee: Mapped[float | None] = mapped_column(Float, default=None)
    filled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False,
    )

    __table_args__ = (
        Index("ix_orders_bot_id", "bot_id"),
        Index("ix_orders_status", "status"),
    )


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(init=False, primary_key=True, autoincrement=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"))
    leg_a_order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"))
    spread_at_entry: Mapped[float] = mapped_column(Float)
    expected_profit: Mapped[float] = mapped_column(Float)
    # Fields with defaults after required fields
    leg_b_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"), default=None,
    )
    actual_profit: Mapped[float | None] = mapped_column(Float, default=None)
    status: Mapped[str] = mapped_column(String(20), default="open")
    settled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False,
    )

    __table_args__ = (
        Index("ix_trades_bot_id", "bot_id"),
        Index("ix_trades_status", "status"),
    )
