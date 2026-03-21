from datetime import datetime, timezone

import structlog
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.categories import resolve_category
from app.models.market import UnifiedMarket
from app.models.platform import Platform
from app.schemas.market import MarketResponse
from app.services.market_service import MarketService
from app.services.search_utils import build_tsquery

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
        limit: int = 20,
    ) -> list[MarketResponse]:
        or_query = build_tsquery(query)

        ts_query = func.to_tsquery("english", or_query)
        ts_vector = func.to_tsvector(
            "english",
            UnifiedMarket.question + " " + func.coalesce(UnifiedMarket.description, ""),
        )
        rank = func.ts_rank(ts_vector, ts_query)

        stmt = (
            select(UnifiedMarket, Platform.name, Platform.slug, rank.label("rank"))
            .join(Platform, Platform.id == UnifiedMarket.platform_id)
            .where(ts_vector.bool_op("@@")(ts_query))
        )

        filters = []
        if category:
            db_cat = resolve_category(category)
            cat_val = db_cat if db_cat else category
            filters.append(UnifiedMarket.category == cat_val)
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

        stmt = stmt.order_by(desc("rank")).limit(limit)

        result = await self._db.execute(stmt)
        rows = result.all()

        if len(rows) < limit:
            like_pattern = f"%{query.lower()}%"
            existing_ids = {row[0].id for row in rows}

            fallback_stmt = (
                select(UnifiedMarket, Platform.name, Platform.slug)
                .join(Platform, Platform.id == UnifiedMarket.platform_id)
                .where(
                    func.lower(
                        UnifiedMarket.question + " " + func.coalesce(UnifiedMarket.description, "")
                    ).like(like_pattern)
                )
            )

            if existing_ids:
                fallback_stmt = fallback_stmt.where(
                    UnifiedMarket.id.not_in(existing_ids)
                )

            fb_filters = []
            if category:
                db_cat = resolve_category(category)
                cat_val = db_cat if db_cat else category
                fb_filters.append(UnifiedMarket.category == cat_val)
            if platform:
                fb_filters.append(Platform.slug == platform)
            if exclude_expired:
                now = datetime.now(timezone.utc)
                fb_filters.append(
                    (UnifiedMarket.end_date >= now) | (UnifiedMarket.end_date.is_(None))
                )
            if end_date_min is not None:
                fb_filters.append(UnifiedMarket.end_date >= end_date_min)
            if end_date_max is not None:
                fb_filters.append(UnifiedMarket.end_date <= end_date_max)
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
