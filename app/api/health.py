from datetime import datetime

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.market import UnifiedMarket
from app.models.price_history import PriceSnapshot

logger = structlog.get_logger()

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)) -> dict:
    total_markets = 0
    last_sync: datetime | None = None

    try:
        count_result = await db.execute(
            select(func.count()).select_from(UnifiedMarket)
        )
        total_markets = count_result.scalar_one()

        sync_result = await db.execute(
            select(func.max(PriceSnapshot.timestamp))
        )
        last_sync = sync_result.scalar_one()
    except Exception as exc:
        logger.error("health_check_db_error", error=str(exc), exc_info=True)

    return {
        "status": "healthy",
        "total_markets": total_markets,
        "last_sync_at": last_sync.isoformat() if last_sync else None,
        "timestamp": datetime.now().isoformat(),
    }
