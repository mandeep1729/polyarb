"""Sync market embeddings to Qdrant and find cross-platform candidates.

Usage (CLI):
    python -m app.tasks.embed_markets sync       # Embed all active markets into Qdrant
    python -m app.tasks.embed_markets candidates  # Find cross-platform candidates via embedding similarity
    python -m app.tasks.embed_markets prompt      # Generate LLM verification prompt from embedding candidates
"""

import asyncio
import json
import logging
import sys
from collections import defaultdict

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_background_session_factory
from app.matching.scorer import _end_date_gate
from app.models.market import UnifiedMarket
from app.models.matched_market import MatchedMarketPair
from app.models.platform import Platform
from app.models.price_history import load_snap_map
from app.services.embedding_service import (
    find_cross_platform_matches,
    upsert_markets,
)
from app.tasks.llm_candidates import build_llm_prompt

logger = structlog.get_logger()


async def sync_embeddings(db: AsyncSession) -> int:
    """Load all active markets from DB and upsert their embeddings into Qdrant."""
    result = await db.execute(
        select(
            UnifiedMarket.id,
            UnifiedMarket.question,
            UnifiedMarket.platform_id,
            UnifiedMarket.category,
            UnifiedMarket.end_date,
        )
        .where(UnifiedMarket.is_active.is_(True))
        .where(UnifiedMarket.status == "active")
        .where(UnifiedMarket.end_date.isnot(None))
    )
    rows = result.all()
    logger.info("embed_markets_loaded", count=len(rows))

    markets = [
        {
            "id": r.id,
            "question": r.question,
            "platform_id": r.platform_id,
            "category": r.category,
            "end_date": r.end_date.isoformat() if r.end_date else None,
        }
        for r in rows
    ]

    batch_size = 500
    total = 0
    for i in range(0, len(markets), batch_size):
        batch = markets[i : i + batch_size]
        count = upsert_markets(batch)
        total += count
        logger.info("embed_batch_complete", batch=i // batch_size + 1, upserted=count, total=total)

    return total


async def generate_embedding_candidates(
    db: AsyncSession,
    threshold: float | None = None,
) -> list[dict]:
    """Find cross-platform candidates by searching Qdrant for each smaller-platform market.

    Strategy: group markets by platform, iterate through the smaller platform's
    markets, and search Qdrant for matches on other platforms. This avoids
    searching all 125k markets — only the smaller set triggers queries.
    """
    if threshold is None:
        threshold = 0.80

    # Load platforms
    plat_result = await db.execute(select(Platform.id, Platform.name))
    platforms = plat_result.all()
    platform_names = {p.id: p.name for p in platforms}

    # Load markets grouped by platform (only id, platform_id, end_date for speed)
    result = await db.execute(
        select(UnifiedMarket.id, UnifiedMarket.platform_id, UnifiedMarket.end_date)
        .where(UnifiedMarket.is_active.is_(True))
        .where(UnifiedMarket.status == "active")
        .where(UnifiedMarket.end_date.isnot(None))
    )
    all_markets = result.all()
    end_dates = {r.id: r.end_date for r in all_markets}

    by_platform: dict[int, list[int]] = defaultdict(list)
    for r in all_markets:
        by_platform[r.platform_id].append(r.id)

    # Pick the smaller platform to iterate (fewer Qdrant queries)
    platform_ids = sorted(by_platform.keys(), key=lambda pid: len(by_platform[pid]))
    smaller_pid = platform_ids[0]
    smaller_ids = by_platform[smaller_pid]

    logger.info(
        "embedding_candidate_search",
        smaller_platform=platform_names.get(smaller_pid),
        smaller_count=len(smaller_ids),
        total_markets=len(all_markets),
        threshold=threshold,
    )

    # Load existing pairs to exclude
    existing_result = await db.execute(
        select(MatchedMarketPair.market_a_id, MatchedMarketPair.market_b_id)
    )
    existing_pairs: set[tuple[int, int]] = {
        (row[0], row[1]) for row in existing_result.all()
    }

    # Search for each market in the smaller platform
    raw_candidates: list[dict] = []
    seen_pairs: set[tuple[int, int]] = set()

    for i, market_id in enumerate(smaller_ids):
        matches = find_cross_platform_matches(
            market_id=market_id,
            platform_id=smaller_pid,
            threshold=threshold,
            limit=5,
        )
        for m in matches:
            pair_key = (min(market_id, m["id"]), max(market_id, m["id"]))
            if pair_key in seen_pairs or pair_key in existing_pairs:
                continue

            # Apply end_date gate
            end_a = end_dates.get(market_id)
            end_b = end_dates.get(m["id"])
            if not _end_date_gate(end_a, end_b):
                continue

            seen_pairs.add(pair_key)
            raw_candidates.append({
                "market_a_id": pair_key[0],
                "market_b_id": pair_key[1],
                "embedding_score": m["score"],
                "source_id": market_id,
                "match_id": m["id"],
            })

        if (i + 1) % 500 == 0:
            logger.info("embedding_search_progress", searched=i + 1, candidates=len(raw_candidates))

    logger.info("embedding_raw_candidates", count=len(raw_candidates))

    # Enrich with full market data
    market_ids_needed = set()
    for c in raw_candidates:
        market_ids_needed.add(c["market_a_id"])
        market_ids_needed.add(c["market_b_id"])

    market_data: dict[int, UnifiedMarket] = {}
    for i in range(0, len(market_ids_needed), 500):
        batch_ids = list(market_ids_needed)[i : i + 500]
        res = await db.execute(
            select(UnifiedMarket).where(UnifiedMarket.id.in_(batch_ids))
        )
        for m in res.scalars().all():
            market_data[m.id] = m

    # Bulk-load latest snapshot prices
    snap_map = await load_snap_map(db, list(market_ids_needed))

    candidates = []
    for c in raw_candidates:
        m_a = market_data.get(c["market_a_id"])
        m_b = market_data.get(c["market_b_id"])
        if not m_a or not m_b:
            continue

        candidates.append({
            "market_a_id": m_a.id,
            "market_a_question": m_a.question,
            "market_a_platform": platform_names.get(m_a.platform_id, "unknown"),
            "market_a_outcomes": m_a.outcomes or {},
            "market_a_outcome_prices": snap_map.get(m_a.id, {}).get("outcome_prices", {}),
            "market_a_end_date": m_a.end_date.isoformat() if m_a.end_date else None,
            "market_a_category": m_a.category,
            "market_b_id": m_b.id,
            "market_b_question": m_b.question,
            "market_b_platform": platform_names.get(m_b.platform_id, "unknown"),
            "market_b_outcomes": m_b.outcomes or {},
            "market_b_outcome_prices": snap_map.get(m_b.id, {}).get("outcome_prices", {}),
            "market_b_end_date": m_b.end_date.isoformat() if m_b.end_date else None,
            "market_b_category": m_b.category,
            "tfidf_score": c["embedding_score"],  # reuse field for prompt compat
        })

    candidates.sort(key=lambda c: c["tfidf_score"], reverse=True)
    logger.info("embedding_candidates_enriched", total=len(candidates))
    return candidates


async def main() -> None:
    """CLI entrypoint."""
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    if len(sys.argv) < 2:
        print("Usage: python -m app.tasks.embed_markets [sync|candidates|prompt]")
        sys.exit(1)

    command = sys.argv[1]

    async with get_background_session_factory()() as db:
        if command == "sync":
            count = await sync_embeddings(db)
            print(f"Synced {count} market embeddings to Qdrant")

        elif command == "candidates":
            threshold = float(sys.argv[2]) if len(sys.argv) > 2 else None
            candidates = await generate_embedding_candidates(db, threshold=threshold)
            print(json.dumps(candidates, indent=2))

        elif command == "prompt":
            threshold = float(sys.argv[2]) if len(sys.argv) > 2 else None
            candidates = await generate_embedding_candidates(db, threshold=threshold)
            print(build_llm_prompt(candidates[:50]))

        else:
            print(f"Unknown command: {command}")
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
