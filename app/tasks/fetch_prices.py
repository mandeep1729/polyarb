from datetime import datetime, timezone

import structlog
from sqlalchemy import select

from app.config import settings
from app.connectors.kalshi import KalshiConnector
from app.connectors.polymarket import PolymarketConnector
from app.database import get_background_session_factory
from app.models.market import UnifiedMarket
from app.models.platform import Platform
from app.models.price_history import PriceSnapshot
from app.utils import first_float as _first_float

logger = structlog.get_logger()


def _top_markets_query(platform_id: int, limit: int):
    """Query top active markets by liquidity, capped at limit."""
    return (
        select(UnifiedMarket)
        .where(UnifiedMarket.platform_id == platform_id)
        .where(UnifiedMarket.is_active.is_(True))
        .where(UnifiedMarket.status == "active")
        .order_by(UnifiedMarket.liquidity.desc().nulls_last())
        .limit(limit)
    )


async def _update_polymarket_prices(db, platform_id: int) -> int:
    """Fetch prices for top Polymarket markets using CLOB POST /midpoints.

    Collects token_ids from market.outcomes, fetches midpoint prices in
    batch, then merges Yes/No prices back by market.
    """
    result = await db.execute(
        _top_markets_query(platform_id, settings.FETCH_PRICES_MAX_MARKETS)
    )
    markets = result.scalars().all()

    if not markets:
        return 0

    # Build token_id -> (market, outcome_name) lookup
    token_to_market: dict[str, tuple[UnifiedMarket, str]] = {}
    all_token_ids: list[str] = []
    for market in markets:
        outcomes = market.outcomes or {}
        for outcome_name, token_id in outcomes.items():
            if token_id:
                token_to_market[token_id] = (market, outcome_name)
                all_token_ids.append(token_id)

    if not all_token_ids:
        return 0

    connector = PolymarketConnector()
    try:
        midpoints = await connector.fetch_prices(all_token_ids)
    finally:
        await connector.close()

    # Merge midpoints back into per-market outcome_prices dicts
    market_prices: dict[int, dict[str, float]] = {}
    for token_id, price_str in midpoints.items():
        entry = token_to_market.get(token_id)
        if entry is None:
            continue
        market, outcome_name = entry
        try:
            price_val = float(price_str)
        except (ValueError, TypeError):
            continue
        if market.id not in market_prices:
            market_prices[market.id] = {}
        market_prices[market.id][outcome_name] = round(price_val, 4)

    updated = 0
    market_by_id = {m.id: m for m in markets}
    for market_id, prices in market_prices.items():
        market = market_by_id[market_id]

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

    logger.info(
        "polymarket_prices_fetched",
        markets_queried=len(markets),
        tokens_sent=len(all_token_ids),
        midpoints_received=len(midpoints),
        markets_updated=updated,
    )
    return updated


async def _update_kalshi_prices(db, platform_id: int) -> int:
    """Fetch prices for top Kalshi markets using batch /markets endpoint."""
    result = await db.execute(
        _top_markets_query(platform_id, settings.FETCH_PRICES_MAX_MARKETS)
    )
    markets = result.scalars().all()

    if not markets:
        return 0

    connector = KalshiConnector()
    market_ids = [m.platform_market_id for m in markets]
    price_data = await connector.fetch_prices(market_ids)

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

    logger.info(
        "kalshi_prices_fetched",
        markets_queried=len(markets),
        api_results=len(price_data),
        markets_updated=updated,
    )
    return updated


async def fetch_active_prices() -> None:
    """Fetch prices for top active markets on each platform."""
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
