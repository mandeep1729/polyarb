from datetime import datetime, timezone

import structlog
from sqlalchemy import select

from app.connectors.kalshi import KalshiConnector
from app.connectors.polymarket import PolymarketConnector
from app.database import get_background_session_factory
from app.models.market import UnifiedMarket
from app.models.platform import Platform
from app.models.price_history import PriceSnapshot

from app.utils import first_float as _first_float

logger = structlog.get_logger()


async def _update_polymarket_prices(db, platform_id: int) -> int:
    result = await db.execute(
        select(UnifiedMarket)
        .where(UnifiedMarket.platform_id == platform_id)
        .where(UnifiedMarket.is_active.is_(True))
        .where(UnifiedMarket.status == "active")
    )
    markets = result.scalars().all()

    if not markets:
        return 0

    connector = PolymarketConnector()
    try:
        market_ids = [m.platform_market_id for m in markets]
        price_data = await connector.fetch_prices(market_ids)

        price_map: dict[str, dict] = {}
        for pd_item in price_data:
            cid = pd_item.get("condition_id", "")
            price_map[cid] = pd_item.get("prices", {})

        updated = 0
        for market in markets:
            prices = price_map.get(market.platform_market_id)
            if prices is None:
                continue

            old_prices = market.outcome_prices or {}
            market.outcome_prices = prices
            market.last_synced_at = datetime.now(timezone.utc)

            if old_prices:
                first_old = next(iter(old_prices.values()), None)
                first_new = next(iter(prices.values()), None)
                if first_old is not None and first_new is not None:
                    try:
                        market.price_change_24h = float(first_new) - float(first_old)
                    except (ValueError, TypeError):
                        pass

            snapshot = PriceSnapshot(
                market_id=market.id,
                outcome_prices=prices,
                volume=market.volume_24h,
            )
            db.add(snapshot)
            db.add(market)
            updated += 1

        return updated
    finally:
        await connector.close()


async def _update_kalshi_prices(db, platform_id: int) -> int:
    result = await db.execute(
        select(UnifiedMarket)
        .where(UnifiedMarket.platform_id == platform_id)
        .where(UnifiedMarket.is_active.is_(True))
        .where(UnifiedMarket.status == "active")
    )
    markets = result.scalars().all()

    if not markets:
        return 0

    connector = KalshiConnector()
    market_ids = [m.platform_market_id for m in markets]
    price_data = await connector.fetch_prices(market_ids)

    # Build lookup: ticker -> raw dict (SDK returns clean floats)
    price_map: dict[str, dict] = {}
    for pd_item in price_data:
        ticker = pd_item.get("ticker", "")
        if ticker:
            price_map[ticker] = pd_item

    updated = 0
    for market in markets:
        raw = price_map.get(market.platform_market_id)
        if raw is None:
            continue

        yes_bid = _first_float(raw, "yes_bid", "yes_bid_dollars")
        no_bid = _first_float(raw, "no_bid", "no_bid_dollars")
        prices: dict[str, float] = {}
        if yes_bid is not None:
            prices["Yes"] = round(yes_bid, 4)
        if no_bid is not None:
            prices["No"] = round(no_bid, 4)

        old_prices = market.outcome_prices or {}
        market.outcome_prices = prices
        market.last_synced_at = datetime.now(timezone.utc)

        # Update ask prices on the market record
        ya = _first_float(raw, "yes_ask", "yes_ask_dollars")
        na = _first_float(raw, "no_ask", "no_ask_dollars")
        if ya is not None:
            market.yes_ask = ya
        if na is not None:
            market.no_ask = na

        if old_prices and prices:
            old_yes = old_prices.get("Yes")
            new_yes = prices.get("Yes")
            if old_yes is not None and new_yes is not None:
                market.price_change_24h = new_yes - old_yes

        vol_24h = _first_float(raw, "volume_24h", "volume_24h_fp")
        if vol_24h is not None:
            market.volume_24h = vol_24h

        snapshot = PriceSnapshot(
            market_id=market.id,
            outcome_prices=prices,
            volume=market.volume_24h,
        )
        db.add(snapshot)
        db.add(market)
        updated += 1

    return updated


async def fetch_active_prices() -> None:
    logger.info("fetch_active_prices_started")

    async with get_background_session_factory()() as db:
        try:
            result = await db.execute(
                select(Platform).where(Platform.is_active.is_(True))
            )
            platforms = {p.slug: p.id for p in result.scalars().all()}

            poly_count = 0
            kalshi_count = 0

            if "polymarket" in platforms:
                poly_count = await _update_polymarket_prices(db, platforms["polymarket"])
            if "kalshi" in platforms:
                kalshi_count = await _update_kalshi_prices(db, platforms["kalshi"])

            await db.commit()
            logger.info(
                "fetch_active_prices_complete",
                polymarket=poly_count,
                kalshi=kalshi_count,
            )
        except Exception as exc:
            await db.rollback()
            logger.error("fetch_active_prices_failed", error=str(exc))
