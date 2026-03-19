import asyncio

import structlog
from sqlalchemy import select

from app.connectors.kalshi import KalshiConnector
from app.connectors.polymarket import PolymarketConnector
from app.database import get_background_session_factory
from app.models.platform import Platform
from app.services.market_service import MarketService

logger = structlog.get_logger()

PLATFORM_CONFIGS = {
    "polymarket": {
        "name": "Polymarket",
        "slug": "polymarket",
        "base_url": "https://polymarket.com",
        "api_url": "https://gamma-api.polymarket.com",
    },
    "kalshi": {
        "name": "Kalshi",
        "slug": "kalshi",
        "base_url": "https://kalshi.com",
        "api_url": "https://api.elections.kalshi.com/trade-api/v2",
    },
}


async def _ensure_platform(db, slug: str) -> int:
    config = PLATFORM_CONFIGS[slug]
    result = await db.execute(
        select(Platform).where(Platform.slug == slug)
    )
    platform = result.scalar_one_or_none()

    if platform is None:
        platform = Platform(
            name=config["name"],
            slug=config["slug"],
            base_url=config["base_url"],
            api_url=config["api_url"],
        )
        db.add(platform)
        await db.flush()

    return platform.id


async def _fetch_polymarket(platform_id: int) -> int:
    connector = PolymarketConnector()
    try:
        raw_markets = await connector.fetch_markets()
        logger.info("polymarket_fetch_done", raw_count=len(raw_markets))

        async with get_background_session_factory()() as db:
            service = MarketService(db)
            count = 0
            for raw in raw_markets:
                normalized = connector.normalize(raw)
                normalized["platform_id"] = platform_id
                await service.upsert_market(normalized)
                count += 1
                if count % 1000 == 0:
                    await db.commit()
                    logger.info("polymarket_upsert_progress", count=count)

            await db.commit()

        logger.info("polymarket_markets_upserted", count=count)
        return count
    except Exception as exc:
        logger.error("polymarket_fetch_failed", error=str(exc), exc_info=True)
        return 0
    finally:
        await connector.close()


async def _fetch_kalshi(platform_id: int) -> int:
    connector = KalshiConnector()
    try:
        raw_markets = await connector.fetch_markets()
        logger.info("kalshi_fetch_done", raw_count=len(raw_markets))

        async with get_background_session_factory()() as db:
            service = MarketService(db)
            count = 0
            for raw in raw_markets:
                normalized = connector.normalize(raw)
                normalized["platform_id"] = platform_id
                await service.upsert_market(normalized)
                count += 1
                if count % 1000 == 0:
                    await db.commit()
                    logger.info("kalshi_upsert_progress", count=count)

            await db.commit()

        logger.info("kalshi_markets_upserted", count=count)
        return count
    except Exception as exc:
        logger.error("kalshi_fetch_failed", error=str(exc), exc_info=True)
        return 0
    finally:
        await connector.close()


async def fetch_all_markets() -> None:
    logger.info("fetch_all_markets_started")

    async with get_background_session_factory()() as db:
        polymarket_id = await _ensure_platform(db, "polymarket")
        kalshi_id = await _ensure_platform(db, "kalshi")
        await db.commit()

    # Run sequentially to avoid API rate limit contention
    poly_count = await _fetch_polymarket(polymarket_id)
    kalshi_count = await _fetch_kalshi(kalshi_id)

    logger.info(
        "fetch_all_markets_complete",
        polymarket=poly_count,
        kalshi=kalshi_count,
    )
