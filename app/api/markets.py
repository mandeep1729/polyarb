from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.categories import resolve_category
from app.models.market import UnifiedMarket
from app.models.platform import Platform
from app.schemas.common import MarketStatus, SortField
from app.schemas.market import (
    MarketListResponse,
    MarketResponse,
    PriceSnapshotResponse,
    TrendingMarketResponse,
)
from app.services.group_service import extract_word_counts
from app.services.market_service import MarketService
from app.services.search_utils import build_tsquery

logger = structlog.get_logger()

router = APIRouter(prefix="/markets", tags=["markets"])


@router.get("", response_model=MarketListResponse)
async def list_markets(
    platform: str | None = Query(None, description="Filter by platform slug"),
    category: str | None = Query(None, description="Filter by category"),
    status: MarketStatus | None = Query(None, description="Filter by market status"),
    sort_by: SortField = Query(SortField.volume_24h, description="Sort field"),
    end_date_min: datetime | None = Query(None, description="Markets expiring on or after this date"),
    end_date_max: datetime | None = Query(None, description="Markets expiring on or before this date"),
    exclude_expired: bool = Query(True, description="Hide markets whose end_date has passed"),
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
        exclude_expired=exclude_expired,
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


@router.get("/tags")
async def market_tags(
    q: str | None = Query(None, min_length=2, max_length=200, description="Search query"),
    category: str | None = Query(None, description="Filter by category"),
    platform: str | None = Query(None, description="Filter by platform slug"),
    exclude_expired: bool = Query(True, description="Hide expired markets"),
    end_date_min: datetime | None = Query(None, description="Markets expiring on or after"),
    end_date_max: datetime | None = Query(None, description="Markets expiring on or before"),
    limit: int = Query(100, ge=1, le=200, description="Max tags to return"),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Return tag frequency counts computed from markets matching the given filters."""
    has_filters = any([q, category, platform, end_date_min, end_date_max, not exclude_expired])

    if not has_filters:
        # No filters — use the admin tag cache for speed
        from app.api.admin import _get_all_tags
        all_tags, _ = await _get_all_tags(db)
        return [t for t in all_tags if t["total"] > 1][:limit]

    # Build filtered query for market questions
    stmt = select(UnifiedMarket.question).join(
        Platform, Platform.id == UnifiedMarket.platform_id
    )

    filters = []
    if q:
        or_query = build_tsquery(q)
        ts_query = func.to_tsquery("english", or_query)
        ts_vector = func.to_tsvector(
            "english",
            UnifiedMarket.question + " " + func.coalesce(UnifiedMarket.description, ""),
        )
        filters.append(ts_vector.bool_op("@@")(ts_query))
    if category:
        db_cat = resolve_category(category)
        filters.append(UnifiedMarket.category == (db_cat or category))
    if platform:
        filters.append(Platform.slug == platform)
    if exclude_expired:
        now = datetime.now(timezone.utc)
        filters.append(
            (UnifiedMarket.end_date >= now) | (UnifiedMarket.end_date.is_(None))
        )
    if end_date_min is not None:
        filters.append(UnifiedMarket.end_date >= end_date_min)
    if end_date_max is not None:
        filters.append(UnifiedMarket.end_date <= end_date_max)

    if filters:
        stmt = stmt.where(and_(*filters))

    result = await db.execute(stmt)
    questions = result.scalars().all()

    counter = extract_word_counts(questions)
    return [
        {"term": term, "count": count}
        for term, count in counter.most_common(limit)
        if count > 1
    ]


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
