"""Hourly price fetcher for all active markets.

Processes markets in batches of BATCH_SIZE, committing after each batch
so progress is saved incrementally and memory stays bounded.
"""

from datetime import datetime, timezone

import structlog
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import settings
from app.connectors.kalshi import KalshiConnector
from app.connectors.polymarket import PolymarketConnector
from app.database import get_background_session_factory
from app.models.market import UnifiedMarket
from app.models.market_group import MarketGroup, MarketGroupMember
from app.models.platform import Platform
from app.models.price_history import PriceSnapshot
from app.utils import first_float as _first_float

logger = structlog.get_logger()

BATCH_SIZE = 500
SNAPSHOT_CHUNK = 1000


def _hour_now() -> datetime:
    """Return current UTC time rounded down to the hour boundary."""
    now = datetime.now(timezone.utc)
    return now.replace(minute=0, second=0, microsecond=0)


async def _upsert_snapshots(db, rows: list[dict]) -> int:
    """Bulk upsert price snapshots, updating if the hour slot already exists."""
    total = 0
    for i in range(0, len(rows), SNAPSHOT_CHUNK):
        chunk = rows[i : i + SNAPSHOT_CHUNK]
        stmt = (
            pg_insert(PriceSnapshot.__table__)
            .values(chunk)
            .on_conflict_do_update(
                constraint="uq_price_snapshots_market_ts",
                set_={
                    "outcome_prices": pg_insert(PriceSnapshot.__table__).excluded.outcome_prices,
                    "volume": pg_insert(PriceSnapshot.__table__).excluded.volume,
                },
            )
        )
        result = await db.execute(stmt)
        total += result.rowcount or 0
    return total


async def _get_top_group_market_ids(db) -> set[int] | None:
    """Return market IDs belonging to the top N groups by volume, or None if no groups exist."""
    top_n = settings.PRICE_SYNC_TOP_N_GROUPS

    # Check if any groups exist
    group_count = (await db.execute(
        select(func.count()).select_from(MarketGroup).where(MarketGroup.is_active.is_(True))
    )).scalar_one()
    if group_count == 0:
        return None  # No groups yet — fall back to all markets

    top_group_ids = (await db.execute(
        select(MarketGroup.id)
        .where(MarketGroup.is_active.is_(True))
        .order_by(MarketGroup.total_volume.desc().nulls_last())
        .limit(top_n)
    )).scalars().all()

    if not top_group_ids:
        return None

    market_ids = (await db.execute(
        select(MarketGroupMember.market_id)
        .where(MarketGroupMember.group_id.in_(top_group_ids))
    )).scalars().all()

    return set(market_ids)


async def _count_active(db, platform_id: int, market_ids: set[int] | None = None) -> int:
    """Count active markets for a platform, optionally filtered to specific IDs."""
    stmt = (
        select(func.count())
        .select_from(UnifiedMarket)
        .where(
            UnifiedMarket.platform_id == platform_id,
            UnifiedMarket.is_active.is_(True),
            UnifiedMarket.status == "active",
        )
    )
    if market_ids is not None:
        stmt = stmt.where(UnifiedMarket.id.in_(market_ids))
    return (await db.execute(stmt)).scalar_one()


async def _load_batch(
    db, platform_id: int, offset: int, limit: int, market_ids: set[int] | None = None
) -> list:
    """Load a batch of active markets ordered by liquidity."""
    stmt = (
        select(UnifiedMarket)
        .where(
            UnifiedMarket.platform_id == platform_id,
            UnifiedMarket.is_active.is_(True),
            UnifiedMarket.status == "active",
        )
    )
    if market_ids is not None:
        stmt = stmt.where(UnifiedMarket.id.in_(market_ids))
    stmt = stmt.order_by(UnifiedMarket.liquidity.desc().nulls_last()).offset(offset).limit(limit)
    return (await db.execute(stmt)).scalars().all()


async def _update_polymarket_batch(db, markets: list, connector: PolymarketConnector) -> int:
    """Fetch and store prices for a batch of Polymarket markets."""
    token_to_market: dict[str, tuple[UnifiedMarket, str]] = {}
    all_token_ids: list[str] = []
    for market in markets:
        for outcome_name, token_id in (market.outcomes or {}).items():
            if token_id:
                token_to_market[token_id] = (market, outcome_name)
                all_token_ids.append(token_id)

    if not all_token_ids:
        return 0

    midpoints = await connector.fetch_prices(all_token_ids)

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
        market_prices.setdefault(market.id, {})[outcome_name] = round(price_val, 4)

    ts = _hour_now()
    snapshot_rows: list[dict] = []
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
                except (ValueError, TypeError) as exc:
                    logger.warning(
                        "price_change_parse_error",
                        market_id=market.id,
                        old=first_old,
                        new=first_new,
                        error=str(exc),
                    )

        snapshot_rows.append({
            "market_id": market.id,
            "outcome_prices": prices,
            "volume": market.volume_24h,
            "timestamp": ts,
        })
        db.add(market)

    return await _upsert_snapshots(db, snapshot_rows)


async def _update_kalshi_batch(db, markets: list, connector: KalshiConnector) -> int:
    """Fetch and store prices for a batch of Kalshi markets."""
    market_ids = [m.platform_market_id for m in markets]
    price_data = await connector.fetch_prices(market_ids)

    price_map: dict[str, dict] = {}
    for pd_item in price_data:
        ticker = pd_item.get("ticker", "")
        if ticker:
            price_map[ticker] = pd_item

    ts = _hour_now()
    snapshot_rows: list[dict] = []

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

        snapshot_rows.append({
            "market_id": market.id,
            "outcome_prices": prices,
            "volume": market.volume_24h,
            "timestamp": ts,
        })
        db.add(market)

    return await _upsert_snapshots(db, snapshot_rows)


async def _update_platform_prices(
    db, platform_id: int, slug: str, market_ids: set[int] | None = None
) -> int:
    """Fetch prices for active markets on a platform, optionally filtered to group members."""
    total_count = await _count_active(db, platform_id, market_ids)
    if total_count == 0:
        return 0

    connector: PolymarketConnector | KalshiConnector
    if slug == "polymarket":
        connector = PolymarketConnector()
    else:
        connector = KalshiConnector()

    updated = 0
    try:
        for offset in range(0, total_count, BATCH_SIZE):
            markets = await _load_batch(db, platform_id, offset, BATCH_SIZE, market_ids)
            if not markets:
                break

            if slug == "polymarket":
                batch_count = await _update_polymarket_batch(db, markets, connector)
            else:
                batch_count = await _update_kalshi_batch(db, markets, connector)

            await db.commit()
            updated += batch_count

            logger.info(
                "price_batch_complete",
                platform=slug,
                batch_offset=offset,
                batch_updated=batch_count,
                total_so_far=updated,
                total_markets=total_count,
            )
    finally:
        if slug == "polymarket":
            await connector.close()

    return updated


async def fetch_active_prices() -> None:
    """Fetch hourly prices for markets in the top groups by volume.

    Limited to markets belonging to the top PRICE_SYNC_TOP_N_GROUPS groups.
    Falls back to all active markets if no groups exist yet.
    """
    logger.info("fetch_active_prices_started")

    async with get_background_session_factory()() as db:
        try:
            market_ids = await _get_top_group_market_ids(db)
            if market_ids is not None:
                logger.info(
                    "price_sync_scope",
                    top_n_groups=settings.PRICE_SYNC_TOP_N_GROUPS,
                    market_count=len(market_ids),
                )
            else:
                logger.info("price_sync_scope", mode="all_markets (no groups yet)")

            result = await db.execute(
                select(Platform).where(Platform.is_active.is_(True))
            )
            platforms = {p.slug: p.id for p in result.scalars().all()}

            poly_count = 0
            kalshi_count = 0

            if "polymarket" in platforms:
                poly_count = await _update_platform_prices(
                    db, platforms["polymarket"], "polymarket", market_ids
                )
            if "kalshi" in platforms:
                kalshi_count = await _update_platform_prices(
                    db, platforms["kalshi"], "kalshi", market_ids
                )

            logger.info(
                "fetch_active_prices_complete",
                polymarket=poly_count,
                kalshi=kalshi_count,
            )
        except Exception as exc:
            await db.rollback()
            logger.error("fetch_active_prices_failed", error=str(exc), exc_info=True)
