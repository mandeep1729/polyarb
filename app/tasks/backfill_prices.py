import asyncio
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.connectors.kalshi import KalshiConnector
from app.connectors.polymarket import PolymarketConnector
from app.database import get_background_session_factory
from app.models.market import UnifiedMarket
from app.models.platform import Platform
from app.models.price_history import PriceSnapshot

logger = structlog.get_logger()

CHUNK_SIZE = 1000


def _round_to_hour(ts: int) -> datetime:
    """Round a unix timestamp down to the nearest hour boundary."""
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.replace(minute=0, second=0, microsecond=0)


async def backfill_all_prices() -> None:
    """Backfill historical prices for all active markets from platform APIs.

    Idempotent: uses ON CONFLICT DO NOTHING on (market_id, timestamp).
    Safe to re-run — skips already-inserted timestamps.
    """
    logger.info("backfill_all_prices_started")

    async with get_background_session_factory()() as db:
        try:
            result = await db.execute(
                select(Platform).where(Platform.is_active.is_(True))
            )
            platforms = {p.slug: p.id for p in result.scalars().all()}

            poly_total = 0
            kalshi_total = 0

            if "polymarket" in platforms:
                poly_total = await _backfill_polymarket(db, platforms["polymarket"])
            if "kalshi" in platforms:
                kalshi_total = await _backfill_kalshi(db, platforms["kalshi"])

            logger.info(
                "backfill_all_prices_complete",
                polymarket_inserted=poly_total,
                kalshi_inserted=kalshi_total,
            )
        except Exception as exc:
            logger.error("backfill_all_prices_failed", error=str(exc))


async def _backfill_polymarket(db, platform_id: int) -> int:
    result = await db.execute(
        select(UnifiedMarket)
        .where(UnifiedMarket.platform_id == platform_id)
        .where(UnifiedMarket.is_active.is_(True))
        .where(UnifiedMarket.status == "active")
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
                    if not token_id:
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
                        "volume": None,
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
                logger.warning(
                    "backfill_polymarket_market_error",
                    market_id=market.id,
                    error=str(exc),
                )
    finally:
        await connector.close()

    return total_inserted


async def _backfill_kalshi(db, platform_id: int) -> int:
    result = await db.execute(
        select(UnifiedMarket)
        .where(UnifiedMarket.platform_id == platform_id)
        .where(UnifiedMarket.is_active.is_(True))
        .where(UnifiedMarket.status == "active")
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
                ts = candle.get("end_period_ts") or candle.get("start_period_ts")
                if ts is None:
                    continue

                # Use close prices; Kalshi reports yes/no as cents (0-100)
                close_yes = candle.get("yes_close") or candle.get("close")
                close_no = candle.get("no_close")

                prices: dict[str, float] = {}
                if close_yes is not None:
                    try:
                        yval = float(close_yes)
                        # Normalize cents to dollars if > 1
                        prices["Yes"] = round(yval / 100, 4) if yval > 1 else round(yval, 4)
                    except (ValueError, TypeError):
                        pass
                if close_no is not None:
                    try:
                        nval = float(close_no)
                        prices["No"] = round(nval / 100, 4) if nval > 1 else round(nval, 4)
                    except (ValueError, TypeError):
                        pass

                # Infer No from Yes if missing
                if "Yes" in prices and "No" not in prices:
                    prices["No"] = round(1.0 - prices["Yes"], 4)
                elif "No" in prices and "Yes" not in prices:
                    prices["Yes"] = round(1.0 - prices["No"], 4)

                if not prices:
                    continue

                rows.append({
                    "market_id": market.id,
                    "outcome_prices": prices,
                    "volume": None,
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
            logger.warning(
                "backfill_kalshi_market_error",
                market_id=market.id,
                error=str(exc),
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
