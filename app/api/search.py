from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.market import MarketResponse
from app.services.live_search_service import LiveSearchService

logger = structlog.get_logger()

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=list[MarketResponse])
async def search_markets(
    q: str | None = Query(None, min_length=2, max_length=200, description="Search query"),
    category: str | None = Query(None, description="Filter by category"),
    platform: str | None = Query(None, description="Filter by platform slug"),
    exclude_expired: bool = Query(True, description="Hide expired markets"),
    end_date_min: datetime | None = Query(None, description="Markets expiring on or after"),
    end_date_max: datetime | None = Query(None, description="Markets expiring on or before"),
    exclude_q: str | None = Query(None, max_length=200, description="Exclude markets matching these terms"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    db: AsyncSession = Depends(get_db),
) -> list[MarketResponse]:
    if not q and not exclude_q:
        return []
    service = LiveSearchService(db)
    return await service.search(
        query=q or "",
        category=category,
        platform=platform,
        exclude_expired=exclude_expired,
        end_date_min=end_date_min,
        end_date_max=end_date_max,
        exclude_q=exclude_q,
        limit=limit,
    )
