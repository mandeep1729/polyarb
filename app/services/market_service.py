from datetime import datetime, timezone

import structlog
from sqlalchemy import and_, desc, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.categories import resolve_category
from app.models.market import UnifiedMarket
from app.models.platform import Platform
from app.models.price_history import (
    PriceSnapshot,
    latest_snapshot_subquery,
    load_snap_map,
    snap_select_columns,
    snap_to_dict,
)
from app.schemas.common import PaginatedResponse
from app.schemas.market import (
    MarketResponse,
    PriceSnapshotResponse,
    TrendingMarketResponse,
)

logger = structlog.get_logger()

PRICING_KEYS = {
    "outcome_prices", "volume_total", "volume_24h", "liquidity",
    "yes_ask", "no_ask", "price_change_24h", "last_synced_at",
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
        end_date_min: datetime | None = None,
        end_date_max: datetime | None = None,
        exclude_expired: bool = True,
        hide_zero_liquidity: bool = True,
        limit: int = 20,
        cursor: str | None = None,
    ) -> PaginatedResponse[MarketResponse]:
        snap = latest_snapshot_subquery()

        base_query = (
            select(UnifiedMarket, Platform.name, Platform.slug, *snap_select_columns(snap))
            .join(Platform, Platform.id == UnifiedMarket.platform_id)
            .outerjoin(snap, snap.c.market_id == UnifiedMarket.id)
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
        if exclude_expired:
            now = datetime.now(timezone.utc)
            filters.append(
                (UnifiedMarket.end_date >= now) | (UnifiedMarket.end_date.is_(None))
            )
        if end_date_min is not None:
            filters.append(UnifiedMarket.end_date >= end_date_min)
        if end_date_max is not None:
            filters.append(UnifiedMarket.end_date <= end_date_max)
        if hide_zero_liquidity:
            filters.append(snap.c.liquidity > 0)
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

        sort_columns = {
            "volume_24h": snap.c.volume_24h,
            "end_date": UnifiedMarket.end_date,
            "created_at": UnifiedMarket.created_at,
            "price_change_24h": snap.c.price_change_24h,
        }
        sort_col = sort_columns.get(sort_by, snap.c.volume_24h)
        base_query = base_query.order_by(
            desc(snap.c.liquidity).nulls_last(),
            desc(sort_col).nulls_last(),
            UnifiedMarket.id,
        )
        base_query = base_query.limit(limit)

        result = await self._db.execute(base_query)
        rows = result.all()

        items = [
            self._to_response(row[0], row[1], row[2], snap=snap_to_dict(row))
            for row in rows
        ]

        next_cursor = str(rows[-1][0].id) if len(rows) == limit else None

        logger.info(
            "market_service_get_markets",
            total=total,
            returned=len(items),
            platform=platform,
            category=category,
            status=status,
        )

        return PaginatedResponse(
            items=items,
            next_cursor=next_cursor,
            total=total,
        )

    async def get_market_by_id(self, market_id: int) -> MarketResponse | None:
        snap = latest_snapshot_subquery()
        result = await self._db.execute(
            select(UnifiedMarket, Platform.name, Platform.slug, *snap_select_columns(snap))
            .join(Platform, Platform.id == UnifiedMarket.platform_id)
            .outerjoin(snap, snap.c.market_id == UnifiedMarket.id)
            .where(UnifiedMarket.id == market_id)
        )
        row = result.one_or_none()
        if row is None:
            logger.info("market_service_get_market_not_found", market_id=market_id)
            return None
        return self._to_response(row[0], row[1], row[2], snap=snap_to_dict(row))

    async def get_price_history(
        self,
        market_id: int,
        interval: str = "1h",
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[PriceSnapshotResponse]:
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
            return [self._snap_response(s) for s in snapshots]

        # Downsample: group by time bucket

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
            self._snap_response(s)
            for s in sorted(buckets.values(), key=lambda x: x.timestamp)
        ]

    async def get_trending(self, limit: int = 10, platform: str | None = None) -> list[TrendingMarketResponse]:
        snap = latest_snapshot_subquery()
        query = (
            select(UnifiedMarket, Platform.name, Platform.slug, *snap_select_columns(snap))
            .join(Platform, Platform.id == UnifiedMarket.platform_id)
            .outerjoin(snap, snap.c.market_id == UnifiedMarket.id)
            .where(UnifiedMarket.is_active.is_(True))
            .where(UnifiedMarket.status == "active")
        )
        if platform:
            query = query.where(Platform.slug == platform)
        query = query.order_by(
            desc(
                func.coalesce(snap.c.volume_24h, 0) * 0.5
                + func.abs(func.coalesce(snap.c.price_change_24h, 0)) * 100 * 0.3
                + func.coalesce(snap.c.liquidity, 0) * 0.0001 * 0.2
            )
        ).limit(limit)
        result = await self._db.execute(query)
        rows = result.all()

        trending = []
        for row in rows:
            market = row[0]
            s = snap_to_dict(row)
            vol = s.get("volume_24h") or 0.0
            price_chg = abs(s.get("price_change_24h") or 0.0)
            liq = s.get("liquidity") or 0.0
            score = vol * 0.5 + price_chg * 100 * 0.3 + liq * 0.0001 * 0.2

            trending.append(
                TrendingMarketResponse(
                    market=self._to_response(market, row[1], row[2], snap=s),
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

    async def upsert_market(self, market_data: dict) -> int:
        """Upsert a market and create an initial price snapshot.

        Splits pricing keys out of market_data before upserting the market.
        Returns the market ID.
        """
        # Split out pricing data
        pricing = {k: market_data.pop(k) for k in list(market_data) if k in PRICING_KEYS}

        update_cols = {
            k: v
            for k, v in market_data.items()
            if k not in ("platform_id", "platform_market_id")
        }

        stmt = pg_insert(UnifiedMarket).values(**market_data)
        stmt = stmt.on_conflict_do_update(
            index_elements=["platform_id", "platform_market_id"],
            set_=update_cols,
        ).returning(UnifiedMarket.__table__.c.id)
        result = await self._db.execute(stmt)
        market_id = result.scalar_one()

        # Create initial price snapshot so the market has prices immediately
        if pricing.get("outcome_prices"):
            now = datetime.now(timezone.utc)
            snap_ts = now.replace(minute=0, second=0, microsecond=0)
            snap_data = {
                "market_id": market_id,
                "outcome_prices": pricing.get("outcome_prices", {}),
                "volume_24h": pricing.get("volume_24h"),
                "volume_total": pricing.get("volume_total"),
                "liquidity": pricing.get("liquidity"),
                "yes_ask": pricing.get("yes_ask"),
                "no_ask": pricing.get("no_ask"),
                "price_change_24h": pricing.get("price_change_24h"),
                "timestamp": snap_ts,
            }
            excluded = pg_insert(PriceSnapshot.__table__).excluded
            snap_stmt = (
                pg_insert(PriceSnapshot.__table__)
                .values(snap_data)
                .on_conflict_do_update(
                    constraint="uq_price_snapshots_market_ts",
                    set_={
                        "outcome_prices": excluded.outcome_prices,
                        "volume_24h": excluded.volume_24h,
                        "volume_total": excluded.volume_total,
                        "liquidity": excluded.liquidity,
                        "yes_ask": excluded.yes_ask,
                        "no_ask": excluded.no_ask,
                        "price_change_24h": excluded.price_change_24h,
                    },
                )
            )
            await self._db.execute(snap_stmt)

        return market_id

    @staticmethod
    def _to_response(
        market: UnifiedMarket,
        platform_name: str,
        platform_slug: str,
        snap: dict | None = None,
    ) -> MarketResponse:
        s = snap or {}
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
            outcomes=market.outcomes,
            start_date=market.start_date,
            end_date=market.end_date,
            status=market.status,
            resolution=market.resolution,
            deep_link_url=market.deep_link_url,
            image_url=market.image_url,
            created_at=market.created_at,
            updated_at=market.updated_at,
            # Pricing from snapshot
            outcome_prices=s.get("outcome_prices", {}),
            volume_total=s.get("volume_total"),
            volume_24h=s.get("volume_24h"),
            liquidity=s.get("liquidity"),
            yes_ask=s.get("yes_ask"),
            no_ask=s.get("no_ask"),
            price_change_24h=s.get("price_change_24h"),
            last_synced_at=s.get("last_synced_at"),
        )

    @staticmethod
    def _snap_response(s: PriceSnapshot) -> PriceSnapshotResponse:
        return PriceSnapshotResponse(
            outcome_prices=s.outcome_prices,
            volume_24h=s.volume_24h,
            volume_total=s.volume_total,
            liquidity=s.liquidity,
            yes_ask=s.yes_ask,
            no_ask=s.no_ask,
            price_change_24h=s.price_change_24h,
            timestamp=s.timestamp,
        )
