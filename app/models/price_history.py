from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, UniqueConstraint, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"

    id: Mapped[int] = mapped_column(init=False, primary_key=True, autoincrement=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("unified_markets.id", ondelete="RESTRICT"))
    outcome_prices: Mapped[dict] = mapped_column(JSONB, default_factory=dict)
    volume_24h: Mapped[float | None] = mapped_column(Float, default=None)
    volume_total: Mapped[float | None] = mapped_column(Float, default=None)
    liquidity: Mapped[float | None] = mapped_column(Float, default=None)
    yes_ask: Mapped[float | None] = mapped_column(Float, default=None)
    no_ask: Mapped[float | None] = mapped_column(Float, default=None)
    price_change_24h: Mapped[float | None] = mapped_column(Float, default=None)
    timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=None,
    )

    __table_args__ = (
        UniqueConstraint("market_id", "timestamp", name="uq_price_snapshots_market_ts"),
        # ix_price_snapshots_market_ts_desc (market_id, timestamp DESC) created in migration
        # for efficient DISTINCT ON latest-snapshot lookups
    )


def latest_snapshot_subquery(name="latest_snap"):
    """Subquery returning one row per market: its most recent price snapshot.

    Uses PostgreSQL DISTINCT ON — with the (market_id, timestamp DESC)
    index, this is an index scan, not a sort.
    """
    return (
        select(PriceSnapshot)
        .distinct(PriceSnapshot.market_id)
        .order_by(PriceSnapshot.market_id, PriceSnapshot.timestamp.desc())
    ).subquery(name=name)


def snap_select_columns(snap, prefix="snap"):
    """Return labeled snapshot columns for use in select()."""
    return [
        snap.c.outcome_prices.label(f"{prefix}_outcome_prices"),
        snap.c.volume_24h.label(f"{prefix}_volume_24h"),
        snap.c.volume_total.label(f"{prefix}_volume_total"),
        snap.c.liquidity.label(f"{prefix}_liquidity"),
        snap.c.yes_ask.label(f"{prefix}_yes_ask"),
        snap.c.no_ask.label(f"{prefix}_no_ask"),
        snap.c.price_change_24h.label(f"{prefix}_price_change_24h"),
        snap.c.timestamp.label(f"{prefix}_timestamp"),
    ]


def snap_to_dict(row, prefix="snap"):
    """Extract snapshot pricing data from a query result row into a dict."""
    return {
        "outcome_prices": getattr(row, f"{prefix}_outcome_prices", None) or {},
        "volume_24h": getattr(row, f"{prefix}_volume_24h", None),
        "volume_total": getattr(row, f"{prefix}_volume_total", None),
        "liquidity": getattr(row, f"{prefix}_liquidity", None),
        "yes_ask": getattr(row, f"{prefix}_yes_ask", None),
        "no_ask": getattr(row, f"{prefix}_no_ask", None),
        "price_change_24h": getattr(row, f"{prefix}_price_change_24h", None),
        "last_synced_at": getattr(row, f"{prefix}_timestamp", None),
    }


async def load_snap_map(db, market_ids: list[int]) -> dict[int, dict]:
    """Bulk-load latest snapshot data for a list of market IDs.

    Returns a dict mapping market_id to a snapshot pricing dict.
    """
    if not market_ids:
        return {}
    snap = latest_snapshot_subquery()
    result = await db.execute(
        select(snap.c.market_id, *snap_select_columns(snap))
        .where(snap.c.market_id.in_(market_ids))
    )
    return {row[0]: snap_to_dict(row) for row in result.all()}
