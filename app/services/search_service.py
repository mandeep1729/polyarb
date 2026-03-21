from datetime import datetime, timezone

import structlog
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.categories import resolve_category
from app.models.market import UnifiedMarket
from app.models.platform import Platform
from app.schemas.market import MarketResponse
from app.services.market_service import MarketService
from app.services.search_utils import build_exclude_tsquery, build_tsquery

logger = structlog.get_logger()


class SearchService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def search(
        self,
        query: str,
        category: str | None = None,
        platform: str | None = None,
        exclude_expired: bool = True,
        end_date_min: datetime | None = None,
        end_date_max: datetime | None = None,
        exclude_q: str | None = None,
        limit: int = 20,
    ) -> list[MarketResponse]:
        ts_vector = func.to_tsvector("english", UnifiedMarket.question)

        # Exclusion-only mode: no positive query, just exclude
        if not query:
            return await self._exclude_only_search(
                ts_vector, category, platform, exclude_expired,
                end_date_min, end_date_max, exclude_q, limit,
            )

        or_query = build_tsquery(query)
        ts_query = func.to_tsquery("english", or_query)
        rank = func.ts_rank(ts_vector, ts_query)

        stmt = (
            select(UnifiedMarket, Platform.name, Platform.slug, rank.label("rank"))
            .join(Platform, Platform.id == UnifiedMarket.platform_id)
            .where(ts_vector.bool_op("@@")(ts_query))
        )

        filters = self._build_filters(category, platform, exclude_expired, end_date_min, end_date_max)
        if exclude_q:
            filters.append(self._build_exclude_filter(ts_vector, exclude_q))
        if filters:
            stmt = stmt.where(and_(*filters))

        stmt = stmt.order_by(desc("rank")).limit(limit)

        result = await self._db.execute(stmt)
        rows = result.all()

        if len(rows) < limit:
            like_pattern = f"%{query.lower()}%"
            existing_ids = {row[0].id for row in rows}

            fallback_stmt = (
                select(UnifiedMarket, Platform.name, Platform.slug)
                .join(Platform, Platform.id == UnifiedMarket.platform_id)
                .where(func.lower(UnifiedMarket.question).like(like_pattern))
            )

            if existing_ids:
                fallback_stmt = fallback_stmt.where(
                    UnifiedMarket.id.not_in(existing_ids)
                )

            fb_filters = self._build_filters(category, platform, exclude_expired, end_date_min, end_date_max)
            if exclude_q:
                fb_filters.extend(self._build_exclude_ilike_filters(exclude_q))
            if fb_filters:
                fallback_stmt = fallback_stmt.where(and_(*fb_filters))

            fallback_stmt = fallback_stmt.limit(limit - len(rows))
            fallback_result = await self._db.execute(fallback_stmt)
            fallback_rows = fallback_result.all()

            combined_rows = list(rows) + [
                (*fb_row, 0.0) for fb_row in fallback_rows
            ]
        else:
            combined_rows = list(rows)

        results = [
            MarketService._to_response(row[0], row[1], row[2])
            for row in combined_rows
        ]

        logger.info(
            "search_service_search",
            query=query,
            fts_results=len(rows),
            fallback_results=len(combined_rows) - len(rows),
            total=len(results),
        )

        return results

    async def _exclude_only_search(
        self,
        ts_vector,
        category: str | None,
        platform: str | None,
        exclude_expired: bool,
        end_date_min: datetime | None,
        end_date_max: datetime | None,
        exclude_q: str | None,
        limit: int,
    ) -> list[MarketResponse]:
        """Browse markets with exclusion filter only (no positive search query)."""
        stmt = (
            select(UnifiedMarket, Platform.name, Platform.slug)
            .join(Platform, Platform.id == UnifiedMarket.platform_id)
        )

        filters = self._build_filters(category, platform, exclude_expired, end_date_min, end_date_max)
        if exclude_q:
            filters.append(self._build_exclude_filter(ts_vector, exclude_q))
        if filters:
            stmt = stmt.where(and_(*filters))

        stmt = stmt.order_by(desc(UnifiedMarket.volume_24h)).limit(limit)

        result = await self._db.execute(stmt)
        return [
            MarketService._to_response(row[0], row[1], row[2])
            for row in result.all()
        ]

    def _build_filters(
        self,
        category: str | None,
        platform: str | None,
        exclude_expired: bool,
        end_date_min: datetime | None,
        end_date_max: datetime | None,
    ) -> list:
        """Build common WHERE filters for category, platform, expiry, date range."""
        filters = []
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
        return filters

    @staticmethod
    def _build_exclude_filter(ts_vector, exclude_q: str):
        """Build NOT FTS filter for exclusion terms."""
        excl_tsquery = build_exclude_tsquery(exclude_q)
        return ~ts_vector.bool_op("@@")(func.to_tsquery("english", excl_tsquery))

    @staticmethod
    def _build_exclude_ilike_filters(exclude_q: str) -> list:
        """Build NOT ILIKE filters for each excluded term (fallback path)."""
        filters = []
        for term in exclude_q.lower().split():
            filters.append(~func.lower(UnifiedMarket.question).like(f"%{term}%"))
        return filters
