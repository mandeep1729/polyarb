import asyncio
from datetime import datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.kalshi import KalshiConnector
from app.connectors.polymarket import PolymarketConnector
from app.models.market import UnifiedMarket
from app.models.platform import Platform
from app.schemas.market import MarketResponse
from app.services.market_service import MarketService
from app.services.search_service import SearchService

logger = structlog.get_logger()

UPSTREAM_TIMEOUT = 12.0


class LiveSearchService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._market_service = MarketService(db)
        self._search_service = SearchService(db)

    async def search(
        self,
        query: str,
        category: str | None = None,
        platform: str | None = None,
        exclude_expired: bool = True,
        end_date_min: "datetime | None" = None,
        end_date_max: "datetime | None" = None,
        exclude_q: str | None = None,
        limit: int = 20,
    ) -> list[MarketResponse]:
        # Fire local + upstream searches in parallel
        local_task = self._search_service.search(
            query=query, category=category, platform=platform,
            exclude_expired=exclude_expired, end_date_min=end_date_min,
            end_date_max=end_date_max, exclude_q=exclude_q, limit=limit,
        )

        # Skip upstream searches when there's no positive query (exclusion-only)
        if not query:
            local_results = await local_task
            return local_results[:limit]

        poly_task = asyncio.wait_for(
            self._search_polymarket(query, limit), timeout=UPSTREAM_TIMEOUT
        )
        kalshi_task = asyncio.wait_for(
            self._search_kalshi(query, limit), timeout=UPSTREAM_TIMEOUT
        )

        results = await asyncio.gather(
            local_task, poly_task, kalshi_task, return_exceptions=True
        )

        # Extract local results
        local_results: list[MarketResponse] = []
        if isinstance(results[0], list):
            local_results = results[0]
        elif isinstance(results[0], Exception):
            logger.error("local_search_error", error=str(results[0]), exc_info=results[0])

        # Build seen set from local results for dedup
        seen: set[tuple[int, str]] = {
            (r.platform_id, r.platform_market_id) for r in local_results
        }

        # Process upstream results
        upstream_raw: list[tuple[dict, str]] = []  # (normalized_dict, platform_slug)

        if isinstance(results[1], list):
            poly_connector = PolymarketConnector()
            for raw in results[1]:
                normalized = poly_connector.normalize(raw)
                upstream_raw.append((normalized, "polymarket"))
            await poly_connector.close()
        elif isinstance(results[1], Exception):
            logger.error("polymarket_upstream_error", error=str(results[1]), exc_info=results[1])

        if isinstance(results[2], list):
            kalshi_connector = KalshiConnector()
            for raw in results[2]:
                normalized = kalshi_connector.normalize(raw)
                upstream_raw.append((normalized, "kalshi"))
            await kalshi_connector.close()
        elif isinstance(results[2], Exception):
            logger.error("kalshi_upstream_error", error=str(results[2]), exc_info=results[2])

        if not upstream_raw:
            return local_results[:limit]

        # Resolve platform IDs
        platform_map = await self._get_platform_map()

        # Filter to new markets only, apply platform filter if set
        new_markets: list[tuple[dict, int]] = []  # (normalized, platform_id)
        for normalized, slug in upstream_raw:
            pid = platform_map.get(slug)
            if pid is None:
                continue
            if platform and slug != platform:
                continue
            key = (pid, normalized["platform_market_id"])
            if key in seen:
                continue
            if not normalized.get("platform_market_id") or not normalized.get("question"):
                continue
            # Apply expiry filters to upstream results
            end_date = normalized.get("end_date")
            if exclude_expired and end_date and end_date < datetime.now(end_date.tzinfo):
                continue
            if end_date_min and (not end_date or end_date < end_date_min):
                continue
            if end_date_max and (not end_date or end_date > end_date_max):
                continue
            seen.add(key)
            new_markets.append((normalized, pid))

        # Upsert new markets and build responses
        new_responses: list[MarketResponse] = []
        if new_markets:
            for normalized, pid in new_markets:
                market_data = {
                    "platform_id": pid,
                    **normalized,
                }
                try:
                    await self._market_service.upsert_market(market_data)
                except Exception as exc:
                    logger.error(
                        "upsert_new_market_error",
                        platform_market_id=normalized["platform_market_id"],
                        error=str(exc),
                        exc_info=True,
                    )
                    continue

            await self._db.commit()

            # Fetch the upserted markets back to get DB IDs
            for normalized, pid in new_markets:
                result = await self._db.execute(
                    select(UnifiedMarket, Platform.name, Platform.slug)
                    .join(Platform, Platform.id == UnifiedMarket.platform_id)
                    .where(UnifiedMarket.platform_id == pid)
                    .where(
                        UnifiedMarket.platform_market_id
                        == normalized["platform_market_id"]
                    )
                )
                row = result.one_or_none()
                if row:
                    new_responses.append(
                        MarketService._to_response(row[0], row[1], row[2])
                    )

        combined = local_results + new_responses
        logger.info(
            "live_search_complete",
            query=query,
            local_count=len(local_results),
            new_upstream_count=len(new_responses),
            total=len(combined),
        )
        return combined[:limit]

    async def _search_polymarket(self, query: str, limit: int) -> list[dict]:
        connector = PolymarketConnector()
        try:
            return await connector.search_markets(query, limit)
        finally:
            await connector.close()

    async def _search_kalshi(self, query: str, limit: int) -> list[dict]:
        connector = KalshiConnector()
        try:
            return await connector.search_markets(query, limit)
        finally:
            await connector.close()

    async def _get_platform_map(self) -> dict[str, int]:
        """Return {slug: id} for all platforms."""
        result = await self._db.execute(select(Platform.slug, Platform.id))
        return {row[0]: row[1] for row in result.all()}

    async def _get_platform_names(self) -> dict[int, str]:
        """Return {id: name} for all platforms."""
        result = await self._db.execute(select(Platform.id, Platform.name))
        return {row[0]: row[1] for row in result.all()}
