from sqlalchemy import and_, desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.matching.synonyms import expand_synonyms
from app.models.market import UnifiedMarket
from app.models.platform import Platform
from app.schemas.market import MarketResponse
from app.services.market_service import MarketService


def _build_or_tsquery(query: str) -> str:
    """Build a tsquery string that ORs the original terms with synonyms."""
    expanded = expand_synonyms(query.lower())
    terms = expanded.split()
    if not terms:
        return query
    return " | ".join(terms)


class SearchService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def search(
        self,
        query: str,
        category: str | None = None,
        platform: str | None = None,
        limit: int = 20,
    ) -> list[MarketResponse]:
        or_query = _build_or_tsquery(query)

        ts_query = func.to_tsquery("english", or_query)
        ts_vector = func.to_tsvector("english", UnifiedMarket.question)
        rank = func.ts_rank(ts_vector, ts_query)

        stmt = (
            select(UnifiedMarket, Platform.name, Platform.slug, rank.label("rank"))
            .join(Platform, Platform.id == UnifiedMarket.platform_id)
            .where(ts_vector.bool_op("@@")(ts_query))
        )

        filters = []
        if category:
            filters.append(UnifiedMarket.category == category)
        if platform:
            filters.append(Platform.slug == platform)
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

            fb_filters = []
            if category:
                fb_filters.append(UnifiedMarket.category == category)
            if platform:
                fb_filters.append(Platform.slug == platform)
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

        return [
            MarketService._to_response(row[0], row[1], row[2])
            for row in combined_rows
        ]
