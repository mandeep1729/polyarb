from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import delete, select

from app.database import get_background_session_factory
from app.models.market import UnifiedMarket
from app.models.price_history import PriceSnapshot

logger = structlog.get_logger()


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
