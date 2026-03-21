"""Fast embedding candidate search using local cosine similarity.

Pulls all vectors from Qdrant into memory, groups by platform, and computes
cross-platform cosine similarity using numpy. Much faster than per-market
Qdrant queries for large collections.

Usage:
    python -m app.tasks.embed_candidates                # JSON candidates at default threshold
    python -m app.tasks.embed_candidates --threshold 0.8
    python -m app.tasks.embed_candidates --prompt        # LLM prompt for top 50
"""

import asyncio
import json
import logging
import sys
import numpy as np
import structlog
from qdrant_client.models import FieldCondition, Filter, MatchValue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_background_session_factory
from app.matching.scorer import _end_date_gate
from app.models.market import UnifiedMarket
from app.models.matched_market import MatchedMarketPair
from app.models.platform import Platform
from app.services.embedding_service import get_qdrant
from app.tasks.llm_candidates import build_llm_prompt

logger = structlog.get_logger()


def _pull_platform_vectors(platform_id: int) -> tuple[list[int], np.ndarray]:
    """Pull all vectors for a platform from Qdrant into numpy arrays."""
    client = get_qdrant()
    ids: list[int] = []
    vectors: list[list[float]] = []
    offset = None

    while True:
        points, next_offset = client.scroll(
            collection_name=settings.QDRANT_COLLECTION,
            scroll_filter=Filter(
                must=[FieldCondition(key="platform_id", match=MatchValue(value=platform_id))]
            ),
            limit=1000,
            offset=offset,
            with_vectors=True,
            with_payload=False,
        )
        for p in points:
            ids.append(p.id)
            vectors.append(p.vector)

        if next_offset is None:
            break
        offset = next_offset

    logger.info("pulled_vectors", platform_id=platform_id, count=len(ids))
    return ids, np.array(vectors, dtype=np.float32) if vectors else np.empty((0, 0))


def _cross_platform_cosine(
    ids_a: list[int],
    vecs_a: np.ndarray,
    ids_b: list[int],
    vecs_b: np.ndarray,
    threshold: float,
    top_k: int = 5,
) -> list[tuple[int, int, float]]:
    """Compute cross-platform cosine similarities above threshold.

    Returns list of (id_a, id_b, score) tuples.
    Vectors are assumed to be L2-normalized (as BGE embeddings are).
    """
    if vecs_a.size == 0 or vecs_b.size == 0:
        return []

    # Normalize just in case
    norms_a = np.linalg.norm(vecs_a, axis=1, keepdims=True)
    norms_b = np.linalg.norm(vecs_b, axis=1, keepdims=True)
    norms_a[norms_a == 0] = 1
    norms_b[norms_b == 0] = 1
    vecs_a = vecs_a / norms_a
    vecs_b = vecs_b / norms_b

    # Compute cosine similarity matrix in chunks to avoid OOM
    results: list[tuple[int, int, float]] = []
    chunk_size = 500

    for i in range(0, len(ids_a), chunk_size):
        chunk_a = vecs_a[i : i + chunk_size]
        chunk_ids_a = ids_a[i : i + chunk_size]

        # (chunk_size, dim) @ (dim, len_b) = (chunk_size, len_b)
        sim_matrix = chunk_a @ vecs_b.T

        for row_idx in range(len(chunk_ids_a)):
            scores = sim_matrix[row_idx]
            # Get top_k above threshold
            above = np.where(scores >= threshold)[0]
            if len(above) == 0:
                continue
            top_indices = above[np.argsort(-scores[above])[:top_k]]
            for col_idx in top_indices:
                results.append((
                    chunk_ids_a[row_idx],
                    ids_b[col_idx],
                    float(scores[col_idx]),
                ))

        if (i + chunk_size) % 5000 < chunk_size:
            logger.info("cosine_progress", processed=min(i + chunk_size, len(ids_a)), total=len(ids_a), matches=len(results))

    return results


async def find_embedding_candidates(
    db: AsyncSession,
    threshold: float = 0.80,
) -> list[dict]:
    """Find cross-platform candidates using local cosine similarity on Qdrant vectors."""
    # Load platforms
    plat_result = await db.execute(select(Platform.id, Platform.name))
    platforms = plat_result.all()
    platform_names = {p.id: p.name for p in platforms}
    platform_ids = [p.id for p in platforms]

    # Load end_dates for gate check
    result = await db.execute(
        select(UnifiedMarket.id, UnifiedMarket.end_date)
        .where(UnifiedMarket.is_active.is_(True))
        .where(UnifiedMarket.end_date.isnot(None))
    )
    end_dates = {r.id: r.end_date for r in result.all()}

    # Load existing pairs
    existing_result = await db.execute(
        select(MatchedMarketPair.market_a_id, MatchedMarketPair.market_b_id)
    )
    existing_pairs: set[tuple[int, int]] = {
        (row[0], row[1]) for row in existing_result.all()
    }

    # Pull vectors from Qdrant per platform
    platform_data: dict[int, tuple[list[int], np.ndarray]] = {}
    for pid in platform_ids:
        platform_data[pid] = _pull_platform_vectors(pid)

    # Cross-platform cosine similarity
    raw_matches: list[tuple[int, int, float]] = []
    for i, pid_a in enumerate(platform_ids):
        for pid_b in platform_ids[i + 1 :]:
            ids_a, vecs_a = platform_data[pid_a]
            ids_b, vecs_b = platform_data[pid_b]
            logger.info(
                "cross_platform_search",
                platform_a=platform_names[pid_a],
                count_a=len(ids_a),
                platform_b=platform_names[pid_b],
                count_b=len(ids_b),
            )
            matches = _cross_platform_cosine(ids_a, vecs_a, ids_b, vecs_b, threshold)
            raw_matches.extend(matches)

    # Deduplicate, filter existing, apply end_date gate
    seen: set[tuple[int, int]] = set()
    filtered: list[dict] = []
    for id_a, id_b, score in raw_matches:
        pair_key = (min(id_a, id_b), max(id_a, id_b))
        if pair_key in seen or pair_key in existing_pairs:
            continue
        seen.add(pair_key)

        end_a = end_dates.get(id_a)
        end_b = end_dates.get(id_b)
        if not _end_date_gate(end_a, end_b):
            continue

        filtered.append({
            "market_a_id": pair_key[0],
            "market_b_id": pair_key[1],
            "embedding_score": round(score, 4),
        })

    logger.info("embedding_filtered", raw=len(raw_matches), after_gate=len(filtered))

    # Enrich top candidates with market details
    filtered.sort(key=lambda c: c["embedding_score"], reverse=True)
    top = filtered[:500]  # Cap at 500

    market_ids_needed = set()
    for c in top:
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

    candidates = []
    for c in top:
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
            "tfidf_score": c["embedding_score"],  # reuse field for prompt compat
        })

    return candidates


async def main() -> None:
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    threshold = 0.80
    show_prompt = False
    for arg in sys.argv[1:]:
        if arg == "--prompt":
            show_prompt = True
        elif arg.startswith("--threshold"):
            pass
        else:
            try:
                threshold = float(arg)
            except ValueError:
                pass
    if "--threshold" in sys.argv:
        idx = sys.argv.index("--threshold")
        if idx + 1 < len(sys.argv):
            threshold = float(sys.argv[idx + 1])

    async with get_background_session_factory()() as db:
        candidates = await find_embedding_candidates(db, threshold=threshold)

    if show_prompt:
        print(build_llm_prompt(candidates[:50]))
    else:
        print(json.dumps(candidates, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
