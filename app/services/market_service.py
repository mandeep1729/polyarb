from datetime import datetime, timedelta, timezone

from sqlalchemy import Select, and_, desc, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.categories import resolve_category
from app.models.market import UnifiedMarket
from app.models.platform import Platform
from app.models.price_history import PriceSnapshot
from app.schemas.common import PaginatedResponse
from app.schemas.market import (
    MarketResponse,
    PriceSnapshotResponse,
    TrendingMarketResponse,
)

SORT_COLUMNS = {
    "volume_24h": UnifiedMarket.volume_24h,
    "end_date": UnifiedMarket.end_date,
    "created_at": UnifiedMarket.created_at,
    "price_change_24h": UnifiedMarket.price_change_24h,
}


class MarketService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_markets(
        self,
        platform: str | None = None,
        category: str | None = None,
        status: str | None = None,
        sort_by: str = "volume_24h",
        expires_within: int | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> PaginatedResponse[MarketResponse]:
        base_query = (
            select(UnifiedMarket, Platform.name, Platform.slug)
            .join(Platform, Platform.id == UnifiedMarket.platform_id)
        )

        filters = []
        if platform:
            filters.append(Platform.slug == platform)
        if category:
            db_cat = resolve_category(category)
            if db_cat:
                filters.append(UnifiedMarket.category == db_cat)
            else:
                filters.append(UnifiedMarket.category == category)
        if status:
            filters.append(UnifiedMarket.status == status)
        if expires_within is not None:
            now = datetime.now(timezone.utc)
            filters.append(UnifiedMarket.end_date >= now)
            filters.append(UnifiedMarket.end_date <= now + timedelta(days=expires_within))
        if cursor:
            cursor_id = int(cursor)
            filters.append(UnifiedMarket.id > cursor_id)

        if filters:
            base_query = base_query.where(and_(*filters))

        count_query = select(func.count()).select_from(
            base_query.with_only_columns(UnifiedMarket.id).subquery()
        )
        total_result = await self._db.execute(count_query)
        total = total_result.scalar_one()

        sort_col = SORT_COLUMNS.get(sort_by, UnifiedMarket.volume_24h)
        base_query = base_query.order_by(
            desc(UnifiedMarket.liquidity).nulls_last(),
            desc(sort_col).nulls_last(),
            UnifiedMarket.id,
        )
        base_query = base_query.limit(limit)

        result = await self._db.execute(base_query)
        rows = result.all()

        items = [
            self._to_response(row[0], row[1], row[2])
            for row in rows
        ]

        next_cursor = str(rows[-1][0].id) if len(rows) == limit else None

        return PaginatedResponse(
            items=items,
            next_cursor=next_cursor,
            total=total,
        )

    async def get_market_by_id(self, market_id: int) -> MarketResponse | None:
        result = await self._db.execute(
            select(UnifiedMarket, Platform.name, Platform.slug)
            .join(Platform, Platform.id == UnifiedMarket.platform_id)
            .where(UnifiedMarket.id == market_id)
        )
        row = result.one_or_none()
        if row is None:
            return None
        return self._to_response(row[0], row[1], row[2])

    async def get_price_history(
        self,
        market_id: int,
        interval: str = "1h",
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[PriceSnapshotResponse]:
        interval_map = {
            "1m": "1 minute",
            "5m": "5 minutes",
            "1h": "1 hour",
            "1d": "1 day",
        }
        pg_interval = interval_map.get(interval, "1 hour")

        query = (
            select(PriceSnapshot)
            .where(PriceSnapshot.market_id == market_id)
            .order_by(PriceSnapshot.timestamp)
        )

        if start:
            query = query.where(PriceSnapshot.timestamp >= start)
        if end:
            query = query.where(PriceSnapshot.timestamp <= end)

        result = await self._db.execute(query)
        snapshots = result.scalars().all()

        if not snapshots:
            return []

        if interval == "1m":
            return [
                PriceSnapshotResponse(
                    outcome_prices=s.outcome_prices,
                    volume=s.volume,
                    timestamp=s.timestamp,
                )
                for s in snapshots
            ]

        # Downsample: group by time bucket
        from datetime import timedelta

        bucket_seconds = {
            "5m": 300,
            "1h": 3600,
            "1d": 86400,
        }
        bucket_size = bucket_seconds.get(interval, 3600)

        buckets: dict[int, PriceSnapshot] = {}
        for s in snapshots:
            ts = int(s.timestamp.timestamp())
            bucket_key = ts - (ts % bucket_size)
            if bucket_key not in buckets:
                buckets[bucket_key] = s

        return [
            PriceSnapshotResponse(
                outcome_prices=s.outcome_prices,
                volume=s.volume,
                timestamp=s.timestamp,
            )
            for s in sorted(buckets.values(), key=lambda x: x.timestamp)
        ]

    async def get_trending(self, limit: int = 10, platform: str | None = None) -> list[TrendingMarketResponse]:
        query = (
            select(UnifiedMarket, Platform.name, Platform.slug)
            .join(Platform, Platform.id == UnifiedMarket.platform_id)
            .where(UnifiedMarket.is_active.is_(True))
            .where(UnifiedMarket.status == "active")
        )
        if platform:
            query = query.where(Platform.slug == platform)
        query = query.order_by(
            desc(
                func.coalesce(UnifiedMarket.volume_24h, 0) * 0.5
                + func.abs(func.coalesce(UnifiedMarket.price_change_24h, 0)) * 100 * 0.3
                + func.coalesce(UnifiedMarket.liquidity, 0) * 0.0001 * 0.2
            )
        ).limit(limit)
        result = await self._db.execute(query)
        rows = result.all()

        trending = []
        for row in rows:
            market = row[0]
            vol = market.volume_24h or 0.0
            price_chg = abs(market.price_change_24h or 0.0)
            liq = market.liquidity or 0.0
            score = vol * 0.5 + price_chg * 100 * 0.3 + liq * 0.0001 * 0.2

            trending.append(
                TrendingMarketResponse(
                    market=self._to_response(market, row[1], row[2]),
                    trending_score=round(score, 4),
                )
            )

        return trending

    async def get_category_counts(self, platform: str | None = None) -> list[dict]:
        """Return category counts for active markets."""
        from app.categories import DISPLAY_NAMES

        query = (
            select(UnifiedMarket.category, func.count())
            .where(UnifiedMarket.category.isnot(None))
        )
        if platform:
            query = (
                query.join(Platform, Platform.id == UnifiedMarket.platform_id)
                .where(Platform.slug == platform)
            )
        query = query.group_by(UnifiedMarket.category)

        result = await self._db.execute(query)
        return [
            {"category": row[0], "display_name": DISPLAY_NAMES.get(row[0], row[0].title()), "count": row[1]}
            for row in result.all()
        ]

    async def upsert_market(self, market_data: dict) -> None:
        market_data["last_synced_at"] = datetime.now(timezone.utc)

        update_cols = {
            k: v
            for k, v in market_data.items()
            if k not in ("platform_id", "platform_market_id")
        }

        stmt = pg_insert(UnifiedMarket).values(**market_data)
        stmt = stmt.on_conflict_do_update(
            index_elements=["platform_id", "platform_market_id"],
            set_=update_cols,
        )
        await self._db.execute(stmt)

    @staticmethod
    def _to_response(
        market: UnifiedMarket,
        platform_name: str,
        platform_slug: str,
    ) -> MarketResponse:
        return MarketResponse(
            id=market.id,
            platform_id=market.platform_id,
            platform_name=platform_name,
            platform_slug=platform_slug,
            platform_market_id=market.platform_market_id,
            question=market.question,
            description=market.description,
            category=market.category,
            event_ticker=market.event_ticker,
            series_ticker=market.series_ticker,
            yes_ask=market.yes_ask,
            no_ask=market.no_ask,
            outcomes=market.outcomes,
            outcome_prices=market.outcome_prices,
            volume_total=market.volume_total,
            volume_24h=market.volume_24h,
            liquidity=market.liquidity,
            start_date=market.start_date,
            end_date=market.end_date,
            status=market.status,
            resolution=market.resolution,
            deep_link_url=market.deep_link_url,
            image_url=market.image_url,
            price_change_24h=market.price_change_24h,
            last_synced_at=market.last_synced_at,
            created_at=market.created_at,
            updated_at=market.updated_at,
        )
