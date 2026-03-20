from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import delete, select, update

from app.database import get_background_session_factory
from app.models.market import UnifiedMarket
from app.models.price_history import PriceSnapshot

logger = structlog.get_logger()

EXPIRY_GRACE_DAYS = 7


async def deactivate_expired_markets() -> None:
    """Mark markets as inactive when their end_date is more than 7 days in the past."""
    async with get_background_session_factory()() as db:
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=EXPIRY_GRACE_DAYS)

            result = await db.execute(
                update(UnifiedMarket)
                .where(
                    UnifiedMarket.is_active.is_(True),
                    UnifiedMarket.end_date.isnot(None),
                    UnifiedMarket.end_date < cutoff,
                )
                .values(is_active=False)
            )
            deactivated = result.rowcount or 0

            await db.commit()
            logger.info(
                "deactivate_expired_markets_complete",
                deactivated=deactivated,
                cutoff=cutoff.isoformat(),
            )
        except Exception as exc:
            await db.rollback()
            logger.error("deactivate_expired_markets_failed", error=str(exc))


async def cleanup_old_snapshots() -> None:
    """Delete price snapshots for long-resolved markets to prevent unbounded growth."""
    async with get_background_session_factory()() as db:
        try:
            ninety_days_ago = datetime.now(timezone.utc) - timedelta(days=90)

            resolved_result = await db.execute(
                select(UnifiedMarket.id)
                .where(UnifiedMarket.status == "resolved")
                .where(UnifiedMarket.updated_at < ninety_days_ago)
            )
            resolved_ids = [row[0] for row in resolved_result.all()]

            deleted = 0
            if resolved_ids:
                del_result = await db.execute(
                    delete(PriceSnapshot).where(
                        PriceSnapshot.market_id.in_(resolved_ids)
                    )
                )
                deleted = del_result.rowcount or 0

            await db.commit()
            logger.info("cleanup_old_snapshots_complete", resolved_deleted=deleted)
        except Exception as exc:
            await db.rollback()
            logger.error("cleanup_old_snapshots_failed", error=str(exc))
