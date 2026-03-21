"""Admin dashboard stats endpoint — single endpoint returning all metrics."""
import time
from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.market import UnifiedMarket
from app.models.market_group import MarketGroup, MarketGroupMember
from app.models.matched_market import MatchedMarketPair
from app.models.platform import Platform
from app.models.price_history import PriceSnapshot
from app.services.group_service import extract_word_counts
from app.tasks.task_tracker import get_all_status

router = APIRouter(prefix="/admin", tags=["admin"])

# --- Cached tag data (recomputed at most every 5 minutes) ---
_tag_cache: dict = {"tags": [], "platform_slugs": [], "ts": 0.0}
_TAG_CACHE_TTL = 3600  # seconds


@router.get("/stats")
async def admin_stats(db: AsyncSession = Depends(get_db)) -> dict:
    """Return all admin dashboard metrics in a single payload."""
    now = datetime.now(timezone.utc)

    # --- Platform stats: market counts split by expired/non-expired ---
    platform_rows = (await db.execute(
        select(
            Platform.slug,
            Platform.name,
            func.count(UnifiedMarket.id).label("total"),
            func.count(case(
                (UnifiedMarket.end_date < now, UnifiedMarket.id),
            )).label("expired"),
        )
        .join(UnifiedMarket, UnifiedMarket.platform_id == Platform.id, isouter=True)
        .group_by(Platform.id)
    )).all()

    platform_stats = [
        {
            "slug": row.slug,
            "name": row.name,
            "total": row.total,
            "expired": row.expired,
            "active": row.total - row.expired,
        }
        for row in platform_rows
    ]

    # --- Last sync per platform ---
    sync_rows = (await db.execute(
        select(
            Platform.slug,
            func.max(UnifiedMarket.last_synced_at).label("last_sync"),
        )
        .join(UnifiedMarket, UnifiedMarket.platform_id == Platform.id, isouter=True)
        .group_by(Platform.id)
    )).all()

    sync_health = {
        row.slug: row.last_sync.isoformat() if row.last_sync else None
        for row in sync_rows
    }

    # --- Market freshness: synced within 1h / 6h / 24h / older ---
    freshness_rows = (await db.execute(
        select(
            func.count(case((UnifiedMarket.last_synced_at >= now - timedelta(hours=1), UnifiedMarket.id))).label("h1"),
            func.count(case((UnifiedMarket.last_synced_at >= now - timedelta(hours=6), UnifiedMarket.id))).label("h6"),
            func.count(case((UnifiedMarket.last_synced_at >= now - timedelta(hours=24), UnifiedMarket.id))).label("h24"),
            func.count(UnifiedMarket.id).label("total"),
        )
    )).one()

    freshness = {
        "last_1h": freshness_rows.h1,
        "last_6h": freshness_rows.h6,
        "last_24h": freshness_rows.h24,
        "older": freshness_rows.total - freshness_rows.h24,
    }

    # --- Data quality: % with end_date, % with price history, % categorized ---
    total_markets = freshness_rows.total or 1  # avoid division by zero

    quality_rows = (await db.execute(
        select(
            func.count(case((UnifiedMarket.end_date.isnot(None), UnifiedMarket.id))).label("has_end_date"),
            func.count(case((UnifiedMarket.category.isnot(None), UnifiedMarket.id))).label("has_category"),
        )
    )).one()

    has_history_count = (await db.execute(
        select(func.count(distinct(PriceSnapshot.market_id)))
    )).scalar_one()

    data_quality = {
        "pct_end_date": round(quality_rows.has_end_date / total_markets * 100, 1),
        "pct_categorized": round(quality_rows.has_category / total_markets * 100, 1),
        "pct_price_history": round(has_history_count / total_markets * 100, 1),
    }

    # --- Price history coverage distribution ---
    snapshot_counts_subq = (
        select(
            PriceSnapshot.market_id,
            func.count(PriceSnapshot.id).label("cnt"),
        )
        .group_by(PriceSnapshot.market_id)
        .subquery()
    )

    dist_rows = (await db.execute(
        select(
            func.count(case((snapshot_counts_subq.c.cnt.between(1, 10), 1))).label("b1_10"),
            func.count(case((snapshot_counts_subq.c.cnt.between(11, 100), 1))).label("b11_100"),
            func.count(case((snapshot_counts_subq.c.cnt > 100, 1))).label("b100_plus"),
        )
        .select_from(snapshot_counts_subq)
    )).one()

    price_coverage = {
        "zero": total_markets - has_history_count,
        "1_to_10": dist_rows.b1_10,
        "11_to_100": dist_rows.b11_100,
        "100_plus": dist_rows.b100_plus,
    }

    # --- Top 10 markets by snapshot count ---
    top_markets_rows = (await db.execute(
        select(
            UnifiedMarket.id,
            UnifiedMarket.question,
            Platform.slug.label("platform"),
            func.count(PriceSnapshot.id).label("snapshot_count"),
            func.min(PriceSnapshot.timestamp).label("earliest"),
            func.max(PriceSnapshot.timestamp).label("latest"),
        )
        .join(PriceSnapshot, PriceSnapshot.market_id == UnifiedMarket.id)
        .join(Platform, Platform.id == UnifiedMarket.platform_id)
        .group_by(UnifiedMarket.id, Platform.slug)
        .order_by(func.count(PriceSnapshot.id).desc())
        .limit(10)
    )).all()

    top_markets = [
        {
            "id": row.id,
            "question": row.question,
            "platform": row.platform,
            "snapshot_count": row.snapshot_count,
            "earliest": row.earliest.isoformat() if row.earliest else None,
            "latest": row.latest.isoformat() if row.latest else None,
        }
        for row in top_markets_rows
    ]

    # --- Background task status ---
    task_status = get_all_status()

    # --- Arbitrage health ---
    arb_rows = (await db.execute(
        select(
            func.count(MatchedMarketPair.id).label("total_pairs"),
            func.count(case((MatchedMarketPair.odds_delta > 0.01, MatchedMarketPair.id))).label("arb_pairs"),
            func.avg(case((MatchedMarketPair.odds_delta > 0.01, MatchedMarketPair.odds_delta))).label("avg_spread"),
            func.max(MatchedMarketPair.odds_delta).label("best_spread"),
        )
    )).one()

    arbitrage = {
        "total_pairs": arb_rows.total_pairs,
        "arb_pairs": arb_rows.arb_pairs,
        "avg_spread": round(float(arb_rows.avg_spread or 0), 4),
        "best_spread": round(float(arb_rows.best_spread or 0), 4),
    }

    # --- Grouping health ---
    group_total = (await db.execute(
        select(func.count()).select_from(
            select(MarketGroup.id).where(MarketGroup.is_active.is_(True)).subquery()
        )
    )).scalar_one()

    cross_platform_subq = (
        select(MarketGroupMember.group_id)
        .join(UnifiedMarket, UnifiedMarket.id == MarketGroupMember.market_id)
        .join(MarketGroup, MarketGroup.id == MarketGroupMember.group_id)
        .where(MarketGroup.is_active.is_(True))
        .group_by(MarketGroupMember.group_id)
        .having(func.count(distinct(UnifiedMarket.platform_id)) > 1)
        .subquery()
    )
    cross_platform_count = (await db.execute(
        select(func.count()).select_from(cross_platform_subq)
    )).scalar_one()

    avg_members = (await db.execute(
        select(func.avg(MarketGroup.member_count))
        .where(MarketGroup.is_active.is_(True))
    )).scalar_one()

    high_disagreement = (await db.execute(
        select(func.count()).select_from(
            select(MarketGroup.id)
            .where(MarketGroup.is_active.is_(True), MarketGroup.disagreement_score > 0.05)
            .subquery()
        )
    )).scalar_one()

    grouping = {
        "total_active": group_total,
        "cross_platform": cross_platform_count,
        "cross_platform_pct": round(cross_platform_count / max(group_total, 1) * 100, 1),
        "avg_members": round(float(avg_members or 0), 1),
        "high_disagreement": high_disagreement,
    }

    # --- Tags by platform (cached, all tags) ---
    all_tags, platform_slugs = await _get_all_tags(db)

    return {
        "timestamp": now.isoformat(),
        "platform_stats": platform_stats,
        "sync_health": sync_health,
        "freshness": freshness,
        "data_quality": data_quality,
        "price_coverage": price_coverage,
        "top_markets": top_markets,
        "task_status": task_status,
        "arbitrage": arbitrage,
        "grouping": grouping,
        "tags": all_tags,
        "platform_slugs": platform_slugs,
    }


async def _get_all_tags(db: AsyncSession) -> tuple[list[dict], list[str]]:
    """Return all tags with per-platform counts. Cached for 5 minutes."""
    global _tag_cache
    if time.monotonic() - _tag_cache["ts"] < _TAG_CACHE_TTL and _tag_cache["tags"]:
        return _tag_cache["tags"], _tag_cache["platform_slugs"]

    tag_rows = (await db.execute(
        select(Platform.slug, UnifiedMarket.question)
        .join(UnifiedMarket, UnifiedMarket.platform_id == Platform.id)
        .where(UnifiedMarket.is_active.is_(True))
    )).all()

    platform_counters: dict[str, Counter[str]] = {}
    all_questions: list[str] = []
    for slug, question in tag_rows:
        if question:
            all_questions.append(question)
            platform_counters.setdefault(slug, Counter())

    total_counter = extract_word_counts(all_questions)

    for slug in platform_counters:
        platform_qs = [q for s, q in tag_rows if s == slug and q]
        platform_counters[slug] = extract_word_counts(platform_qs)

    platform_slugs = sorted(platform_counters.keys())
    all_tags = [
        {
            "term": term,
            "total": count,
            **{slug: platform_counters.get(slug, Counter()).get(term, 0) for slug in platform_slugs},
        }
        for term, count in total_counter.most_common()
        if count > 10
    ]

    _tag_cache["tags"] = all_tags
    _tag_cache["platform_slugs"] = platform_slugs
    _tag_cache["ts"] = time.monotonic()
    return all_tags, platform_slugs


@router.get("/tags/search")
async def search_tags(
    q: str = Query(..., min_length=3, max_length=100, description="Search term (min 3 chars)"),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Search all tags by substring match. Returns matching tags with per-platform counts."""
    all_tags, _ = await _get_all_tags(db)
    query = q.lower()
    return [t for t in all_tags if query in str(t["term"]).lower()][:limit]
