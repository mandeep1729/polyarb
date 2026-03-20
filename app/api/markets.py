from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.common import MarketStatus, SortField
from app.schemas.market import (
    MarketListResponse,
    MarketResponse,
    PriceSnapshotResponse,
    TrendingMarketResponse,
)
from app.services.market_service import MarketService

router = APIRouter(prefix="/markets", tags=["markets"])


@router.get("", response_model=MarketListResponse)
async def list_markets(
    platform: str | None = Query(None, description="Filter by platform slug"),
    category: str | None = Query(None, description="Filter by category"),
    status: MarketStatus | None = Query(None, description="Filter by market status"),
    sort_by: SortField = Query(SortField.volume_24h, description="Sort field"),
    end_date_min: datetime | None = Query(None, description="Markets expiring on or after this date"),
    end_date_max: datetime | None = Query(None, description="Markets expiring on or before this date"),
    limit: int = Query(20, ge=1, le=100, description="Page size"),
    cursor: str | None = Query(None, description="Pagination cursor"),
    db: AsyncSession = Depends(get_db),
) -> MarketListResponse:
    service = MarketService(db)
    return await service.get_markets(
        platform=platform,
        category=category,
        status=status.value if status else None,
        sort_by=sort_by.value,
        end_date_min=end_date_min,
        end_date_max=end_date_max,
        limit=limit,
        cursor=cursor,
    )


@router.get("/category-counts")
async def market_category_counts(
    platform: str | None = Query(None, description="Filter by platform slug"),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Return category counts for markets."""
    service = MarketService(db)
    return await service.get_category_counts(platform=platform)


@router.get("/trending", response_model=list[TrendingMarketResponse])
async def trending_markets(
    limit: int = Query(10, ge=1, le=50),
    platform: str | None = Query(None, description="Filter by platform slug"),
    db: AsyncSession = Depends(get_db),
) -> list[TrendingMarketResponse]:
    service = MarketService(db)
    return await service.get_trending(limit=limit, platform=platform)


@router.get("/{market_id}", response_model=MarketResponse)
async def get_market(
    market_id: int,
    db: AsyncSession = Depends(get_db),
) -> MarketResponse:
    service = MarketService(db)
    market = await service.get_market_by_id(market_id)
    if market is None:
        raise HTTPException(status_code=404, detail="Market not found")
    return market


@router.get("/{market_id}/price-history", response_model=list[PriceSnapshotResponse])
async def get_price_history(
    market_id: int,
    interval: str = Query("1h", description="Interval: 1m, 5m, 1h, 1d"),
    start: datetime | None = Query(None, description="Start timestamp"),
    end: datetime | None = Query(None, description="End timestamp"),
    db: AsyncSession = Depends(get_db),
) -> list[PriceSnapshotResponse]:
    service = MarketService(db)
    return await service.get_price_history(
        market_id=market_id,
        interval=interval,
        start=start,
        end=end,
    )
