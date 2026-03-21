from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import update

from app.database import get_background_session_factory
from app.models.market import UnifiedMarket

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
            logger.error("deactivate_expired_markets_failed", error=str(exc), exc_info=True)
