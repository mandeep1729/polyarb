import asyncio
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import settings
from app.connectors.kalshi import KalshiConnector
from app.connectors.polymarket import PolymarketConnector
from app.database import get_background_session_factory
from app.models.market import UnifiedMarket
from app.models.platform import Platform
from app.models.price_history import PriceSnapshot, latest_snapshot_subquery

logger = structlog.get_logger()

CHUNK_SIZE = 1000


def _top_markets_query(platform_id: int, limit: int):
    """Query top active markets by snapshot liquidity for backfill prioritization."""
    snap = latest_snapshot_subquery("backfill_snap")
    return (
        select(UnifiedMarket)
        .outerjoin(snap, snap.c.market_id == UnifiedMarket.id)
        .where(UnifiedMarket.platform_id == platform_id)
        .where(UnifiedMarket.is_active.is_(True))
        .where(UnifiedMarket.status == "active")
        .order_by(snap.c.liquidity.desc().nulls_last())
        .limit(limit)
    )


def _kalshi_close_dollars(candle: dict, *keys: str) -> float | None:
    """Extract close_dollars from nested Kalshi candlestick objects.

    Tries each key in order (e.g. "price", "yes_bid"), returning the
    first non-None close_dollars value as a float.
    """
    for key in keys:
        obj = candle.get(key)
        if not isinstance(obj, dict):
            continue
        val = obj.get("close_dollars")
        if val is not None:
            try:
                return float(val)
            except (ValueError, TypeError):
                continue
    return None


def _round_to_hour(ts: int) -> datetime:
    """Round a unix timestamp down to the nearest hour boundary."""
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.replace(minute=0, second=0, microsecond=0)


async def _run_backfill(session_factory) -> tuple[int, int]:
    """Core backfill logic using the provided session factory."""
    poly_total = 0
    kalshi_total = 0

    try:
        async with session_factory() as db:
            result = await db.execute(
                select(Platform).where(Platform.is_active.is_(True))
            )
            platforms = {p.slug: p.id for p in result.scalars().all()}
    except Exception as exc:
        logger.error("backfill_load_platforms_failed", error=str(exc), exc_info=True)
        return 0, 0

    if "polymarket" in platforms:
        try:
            async with session_factory() as db:
                poly_total = await _backfill_polymarket(db, platforms["polymarket"])
        except Exception as exc:
            logger.error("backfill_polymarket_failed", error=str(exc), exc_info=True)

    if "kalshi" in platforms:
        try:
            async with session_factory() as db:
                kalshi_total = await _backfill_kalshi(db, platforms["kalshi"])
        except Exception as exc:
            logger.error("backfill_kalshi_failed", error=str(exc), exc_info=True)

    return poly_total, kalshi_total


async def backfill_all_prices() -> None:
    """Backfill historical prices (called from scheduler thread)."""
    logger.info("backfill_all_prices_started")
    poly_total, kalshi_total = await _run_backfill(get_background_session_factory())
    logger.info(
        "backfill_all_prices_complete",
        polymarket_inserted=poly_total,
        kalshi_inserted=kalshi_total,
    )


async def run_backfill_inline() -> None:
    """Backfill historical prices (called from uvicorn event loop via admin endpoint)."""
    from app.database import async_session_factory
    logger.info("backfill_inline_started")
    poly_total, kalshi_total = await _run_backfill(async_session_factory)
    logger.info(
        "backfill_inline_complete",
        polymarket_inserted=poly_total,
        kalshi_inserted=kalshi_total,
    )


async def _backfill_polymarket(db, platform_id: int) -> int:
    result = await db.execute(
        _top_markets_query(platform_id, settings.BACKFILL_TOP_N_MARKETS)
    )
    markets = result.scalars().all()

    if not markets:
        logger.info("backfill_polymarket_no_markets")
        return 0

    connector = PolymarketConnector()
    total_inserted = 0
    now_ts = int(datetime.now(timezone.utc).timestamp())
    one_year_ago_ts = int((datetime.now(timezone.utc) - timedelta(days=365)).timestamp())

    try:
        for i, market in enumerate(markets):
            try:
                outcomes = market.outcomes or {}
                if not outcomes:
                    continue

                start_ts = one_year_ago_ts
                if market.start_date:
                    start_ts = max(int(market.start_date.timestamp()), one_year_ago_ts)

                # Fetch price history for each token (Yes/No)
                token_histories: dict[str, list[dict]] = {}
                for outcome_name, token_id in outcomes.items():
                    if not token_id or len(token_id) < 10:
                        continue
                    history = await connector.fetch_price_history(
                        token_id, start_ts, now_ts
                    )
                    token_histories[outcome_name] = history

                if not token_histories:
                    continue

                # Merge histories by timestamp into outcome_prices dicts
                merged: dict[int, dict[str, float]] = {}
                for outcome_name, history in token_histories.items():
                    for point in history:
                        t = point.get("t")
                        p = point.get("p")
                        if t is None or p is None:
                            continue
                        ts_key = int(t)
                        if ts_key not in merged:
                            merged[ts_key] = {}
                        try:
                            merged[ts_key][outcome_name] = float(p)
                        except (ValueError, TypeError):
                            continue

                if not merged:
                    continue

                # Build snapshot rows
                rows = []
                for ts_key, prices in merged.items():
                    rows.append({
                        "market_id": market.id,
                        "outcome_prices": prices,
                        "volume_24h": None,
                        "timestamp": _round_to_hour(ts_key),
                    })

                inserted = await _bulk_insert(db, rows)
                await db.commit()
                total_inserted += inserted

                logger.info(
                    "backfill_polymarket_market_done",
                    market_id=market.id,
                    snapshots_inserted=inserted,
                    progress=f"{i + 1}/{len(markets)}",
                )
            except Exception as exc:
                await db.rollback()
                logger.error(
                    "backfill_polymarket_market_error",
                    market_id=market.id,
                    error=str(exc),
                    exc_info=True,
                )
    finally:
        await connector.close()

    return total_inserted


async def _backfill_kalshi(db, platform_id: int) -> int:
    result = await db.execute(
        _top_markets_query(platform_id, settings.BACKFILL_TOP_N_MARKETS)
    )
    markets = result.scalars().all()

    if not markets:
        logger.info("backfill_kalshi_no_markets")
        return 0

    connector = KalshiConnector()
    total_inserted = 0
    now_ts = int(datetime.now(timezone.utc).timestamp())
    one_year_ago_ts = int((datetime.now(timezone.utc) - timedelta(days=365)).timestamp())

    for i, market in enumerate(markets):
        try:
            ticker = market.platform_market_id
            if not ticker:
                continue

            start_ts = one_year_ago_ts
            if market.start_date:
                start_ts = max(int(market.start_date.timestamp()), one_year_ago_ts)

            candlesticks = await connector.fetch_price_history(
                ticker, start_ts, now_ts
            )

            if not candlesticks:
                continue

            rows = []
            for candle in candlesticks:
                ts = candle.get("end_period_ts")
                if ts is None:
                    continue

                # Extract Yes price: prefer trade price, fall back to yes_bid
                yes_price = _kalshi_close_dollars(candle, "price", "yes_bid")

                prices: dict[str, float] = {}
                if yes_price is not None:
                    prices["Yes"] = round(yes_price, 4)
                    prices["No"] = round(1.0 - yes_price, 4)

                if not prices:
                    continue

                rows.append({
                    "market_id": market.id,
                    "outcome_prices": prices,
                    "volume_24h": None,
                    "timestamp": _round_to_hour(int(ts)),
                })

            if not rows:
                continue

            inserted = await _bulk_insert(db, rows)
            await db.commit()
            total_inserted += inserted

            logger.info(
                "backfill_kalshi_market_done",
                market_id=market.id,
                ticker=ticker,
                snapshots_inserted=inserted,
                progress=f"{i + 1}/{len(markets)}",
            )

            # Rate limit between markets
            await asyncio.sleep(0.5)
        except Exception as exc:
            await db.rollback()
            logger.error(
                "backfill_kalshi_market_error",
                market_id=market.id,
                error=str(exc),
                exc_info=True,
            )

    return total_inserted


async def _bulk_insert(db, rows: list[dict]) -> int:
    """Insert rows in chunks using ON CONFLICT DO NOTHING. Returns count inserted."""
    total = 0
    for i in range(0, len(rows), CHUNK_SIZE):
        chunk = rows[i : i + CHUNK_SIZE]
        stmt = (
            pg_insert(PriceSnapshot.__table__)
            .values(chunk)
            .on_conflict_do_nothing(constraint="uq_price_snapshots_market_ts")
        )
        result = await db.execute(stmt)
        total += result.rowcount or 0
    return total
