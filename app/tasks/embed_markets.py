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

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_background_session_factory
from app.models.market import UnifiedMarket
from app.models.matched_market import MatchedMarketPair
from app.models.platform import Platform
from app.services.embedding_service import (
    find_all_cross_platform_candidates,
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

    # Embed in batches to show progress
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
    """Find cross-platform candidates via embedding similarity, enriched with DB data."""
    # Get platform IDs
    plat_result = await db.execute(select(Platform.id, Platform.name, Platform.slug))
    platforms = plat_result.all()
    platform_ids = [p.id for p in platforms]
    platform_names = {p.id: p.name for p in platforms}

    # Get existing pairs to exclude
    existing_result = await db.execute(
        select(MatchedMarketPair.market_a_id, MatchedMarketPair.market_b_id)
    )
    existing_pairs: set[tuple[int, int]] = {
        (row[0], row[1]) for row in existing_result.all()
    }

    # Find candidates via embedding similarity
    raw_candidates = find_all_cross_platform_candidates(
        platform_ids=platform_ids,
        threshold=threshold,
    )

    # Filter out existing pairs and enrich with full market data
    market_ids = set()
    for c in raw_candidates:
        market_ids.add(c["market_a_id"])
        market_ids.add(c["market_b_id"])

    # Batch-load market details
    market_data: dict[int, UnifiedMarket] = {}
    if market_ids:
        for i in range(0, len(market_ids), 500):
            batch_ids = list(market_ids)[i : i + 500]
            result = await db.execute(
                select(UnifiedMarket).where(UnifiedMarket.id.in_(batch_ids))
            )
            for m in result.scalars().all():
                market_data[m.id] = m

    candidates = []
    for c in raw_candidates:
        pair_key = (c["market_a_id"], c["market_b_id"])
        if pair_key in existing_pairs:
            continue

        m_a = market_data.get(c["market_a_id"])
        m_b = market_data.get(c["market_b_id"])
        if not m_a or not m_b:
            continue

        candidates.append({
            "market_a_id": m_a.id,
            "market_a_question": m_a.question,
            "market_a_platform": platform_names.get(m_a.platform_id, "unknown"),
            "market_a_outcomes": m_a.outcomes or {},
            "market_a_outcome_prices": m_a.outcome_prices or {},
            "market_a_end_date": m_a.end_date.isoformat() if m_a.end_date else None,
            "market_a_category": m_a.category,
            "market_b_id": m_b.id,
            "market_b_question": m_b.question,
            "market_b_platform": platform_names.get(m_b.platform_id, "unknown"),
            "market_b_outcomes": m_b.outcomes or {},
            "market_b_outcome_prices": m_b.outcome_prices or {},
            "market_b_end_date": m_b.end_date.isoformat() if m_b.end_date else None,
            "market_b_category": m_b.category,
            "tfidf_score": c["embedding_score"],  # reuse field name for prompt compat
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
