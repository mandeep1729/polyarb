from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import and_, delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import get_background_session_factory
from app.models.market import UnifiedMarket
from app.models.price_history import PriceSnapshot

logger = structlog.get_logger()


async def cleanup_old_snapshots() -> None:
    logger.info("cleanup_old_snapshots_started")

    async with get_background_session_factory()() as db:
        try:
            now = datetime.now(timezone.utc)

            # >7d snapshots -> downsample to hourly
            seven_days_ago = now - timedelta(days=7)
            thirty_days_ago = now - timedelta(days=30)
            ninety_days_ago = now - timedelta(days=90)

            week_deleted = await _downsample_range(
                db,
                start=thirty_days_ago,
                end=seven_days_ago,
                bucket_seconds=3600,  # 1 hour
            )

            # >30d -> downsample to daily
            month_deleted = await _downsample_range(
                db,
                start=ninety_days_ago,
                end=thirty_days_ago,
                bucket_seconds=86400,  # 1 day
            )

            # >90d resolved markets -> delete all snapshots
            resolved_result = await db.execute(
                select(UnifiedMarket.id)
                .where(UnifiedMarket.status == "resolved")
                .where(UnifiedMarket.updated_at < ninety_days_ago)
            )
            resolved_ids = [row[0] for row in resolved_result.all()]

            resolved_deleted = 0
            if resolved_ids:
                del_result = await db.execute(
                    delete(PriceSnapshot).where(
                        PriceSnapshot.market_id.in_(resolved_ids)
                    )
                )
                resolved_deleted = del_result.rowcount or 0

            await db.commit()
            logger.info(
                "cleanup_old_snapshots_complete",
                week_deleted=week_deleted,
                month_deleted=month_deleted,
                resolved_deleted=resolved_deleted,
            )
        except Exception as exc:
            await db.rollback()
            logger.error("cleanup_old_snapshots_failed", error=str(exc))


async def _downsample_range(
    db,
    start: datetime,
    end: datetime,
    bucket_seconds: int,
) -> int:
    result = await db.execute(
        select(PriceSnapshot)
        .where(
            and_(
                PriceSnapshot.timestamp >= start,
                PriceSnapshot.timestamp < end,
            )
        )
        .order_by(PriceSnapshot.market_id, PriceSnapshot.timestamp)
    )
    snapshots = result.scalars().all()

    if not snapshots:
        return 0

    keep_ids: set[int] = set()
    seen_buckets: dict[tuple[int, int], int] = {}

    for snap in snapshots:
        ts = int(snap.timestamp.timestamp())
        bucket_key = (snap.market_id, ts - (ts % bucket_seconds))

        if bucket_key not in seen_buckets:
            seen_buckets[bucket_key] = snap.id
            keep_ids.add(snap.id)

    all_ids = {s.id for s in snapshots}
    delete_ids = all_ids - keep_ids

    if not delete_ids:
        return 0

    batch_size = 500
    delete_list = list(delete_ids)
    total_deleted = 0

    for i in range(0, len(delete_list), batch_size):
        batch = delete_list[i : i + batch_size]
        del_result = await db.execute(
            delete(PriceSnapshot).where(PriceSnapshot.id.in_(batch))
        )
        total_deleted += del_result.rowcount or 0

    return total_deleted
