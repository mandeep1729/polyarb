"""Generate LLM verification candidates from TF-IDF matching.

Lowers the TF-IDF threshold to catch more potential matches, then outputs
candidate pairs as structured JSON for LLM review. The output prompt can
be pasted into a Claude session or sent to the API.

Usage (CLI):
    python -m app.tasks.llm_candidates > /tmp/candidates.json
    python -m app.tasks.llm_candidates --prompt  # outputs the full LLM prompt
"""

import asyncio
import json
import sys

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_background_session_factory
from app.matching.scorer import _end_date_gate
from app.matching.text import build_tfidf_matrix, get_candidates, preprocess
from app.models.market import UnifiedMarket
from app.models.matched_market import MatchedMarketPair
from app.models.platform import Platform
from app.models.price_history import load_snap_map

logger = structlog.get_logger()

# Lower threshold to catch candidates the current system misses
CANDIDATE_TFIDF_THRESHOLD = 0.15
MAX_CANDIDATES = 500


async def generate_candidates(db: AsyncSession) -> list[dict]:
    """Find cross-platform candidate pairs using a lowered TF-IDF threshold.

    Returns candidates that:
    - Pass the end_date gate (same expiry window)
    - Have TF-IDF cosine similarity >= 0.15 (vs 0.30 in production)
    - Are NOT already paired in matched_market_pairs
    - Are on different platforms
    """
    # Load active markets with platform info
    result = await db.execute(
        select(UnifiedMarket, Platform.name, Platform.slug)
        .join(Platform, Platform.id == UnifiedMarket.platform_id)
        .where(UnifiedMarket.is_active.is_(True))
        .where(UnifiedMarket.status == "active")
    )
    rows = result.all()
    markets = [r[0] for r in rows]
    platform_names = {r[0].id: r[1] for r in rows}

    if len(markets) < 2:
        return []

    # Only keep markets with end_date (matching requires temporal gate)
    markets = [m for m in markets if m.end_date is not None]
    logger.info("llm_candidates_filtered", with_end_date=len(markets))

    # Group by platform
    platform_groups: dict[int, list[UnifiedMarket]] = {}
    for m in markets:
        platform_groups.setdefault(m.platform_id, []).append(m)

    if len(platform_groups) < 2:
        return []

    # Bulk-load latest snapshot prices for all markets
    snap_map = await load_snap_map(db, [m.id for m in markets])

    # Load existing pairs to exclude
    existing_result = await db.execute(
        select(MatchedMarketPair.market_a_id, MatchedMarketPair.market_b_id)
    )
    existing_pairs: set[tuple[int, int]] = {
        (row[0], row[1]) for row in existing_result.all()
    }

    # Build TF-IDF matrix with index lookup
    questions = [m.question for m in markets]
    preprocessed = [preprocess(q) for q in questions]
    tfidf_matrix, _ = build_tfidf_matrix(preprocessed)
    id_to_idx = {m.id: i for i, m in enumerate(markets)}

    candidates: list[dict] = []
    platform_ids = sorted(platform_groups.keys())

    for i in range(len(platform_ids)):
        for j in range(i + 1, len(platform_ids)):
            pid_a = platform_ids[i]
            pid_b = platform_ids[j]
            markets_a = platform_groups[pid_a]
            markets_b = platform_groups[pid_b]

            indices_a = [id_to_idx[m.id] for m in markets_a]
            indices_b = set(id_to_idx[m.id] for m in markets_b)

            for idx_a in indices_a:
                query_vec = tfidf_matrix[idx_a]
                matches = get_candidates(
                    query_vec, tfidf_matrix, threshold=CANDIDATE_TFIDF_THRESHOLD
                )

                for idx_b, tfidf_score in matches:
                    if idx_b not in indices_b:
                        continue

                    m_a = markets[idx_a]
                    m_b = markets[idx_b]

                    pair_key = (min(m_a.id, m_b.id), max(m_a.id, m_b.id))
                    if pair_key in existing_pairs:
                        continue

                    # Apply end_date gate
                    if not _end_date_gate(m_a.end_date, m_b.end_date):
                        continue

                    candidates.append({
                        "market_a_id": m_a.id,
                        "market_a_question": m_a.question,
                        "market_a_platform": platform_names.get(m_a.id, "unknown"),
                        "market_a_outcomes": m_a.outcomes or {},
                        "market_a_outcome_prices": snap_map.get(m_a.id, {}).get("outcome_prices", {}),
                        "market_a_end_date": m_a.end_date.isoformat() if m_a.end_date else None,
                        "market_a_category": m_a.category,
                        "market_b_id": m_b.id,
                        "market_b_question": m_b.question,
                        "market_b_platform": platform_names.get(m_b.id, "unknown"),
                        "market_b_outcomes": m_b.outcomes or {},
                        "market_b_outcome_prices": snap_map.get(m_b.id, {}).get("outcome_prices", {}),
                        "market_b_end_date": m_b.end_date.isoformat() if m_b.end_date else None,
                        "market_b_category": m_b.category,
                        "tfidf_score": round(tfidf_score, 4),
                    })

                    if len(candidates) >= MAX_CANDIDATES:
                        break
                if len(candidates) >= MAX_CANDIDATES:
                    break
            if len(candidates) >= MAX_CANDIDATES:
                break
        if len(candidates) >= MAX_CANDIDATES:
            break

    # Sort by tfidf_score descending
    candidates.sort(key=lambda c: c["tfidf_score"], reverse=True)
    logger.info("llm_candidates_generated", count=len(candidates))
    return candidates


def build_llm_prompt(candidates: list[dict]) -> str:
    """Build a structured prompt for LLM verification of candidate pairs."""
    lines = [
        "You are reviewing candidate prediction market pairs to determine if they",
        "track the SAME real-world event. For each pair, determine:",
        "",
        "1. **match**: true/false — do both markets resolve based on the same event?",
        "2. **confidence**: 0.0-1.0 — how confident are you?",
        "3. **outcome_mapping**: which outcomes in market A correspond to which in market B",
        "   (e.g. {\"Yes\": \"Yes\", \"No\": \"No\"} or {\"Yes\": \"Above\", \"No\": \"Below\"})",
        "4. **explanation**: one sentence explaining why they match or don't",
        "",
        "Rules:",
        "- Same event = same underlying real-world outcome being measured",
        "- Different phrasing of the same question IS a match",
        "- Same topic but different thresholds/dates is NOT a match",
        "- If outcomes map differently (Yes/No vs Above/Below), still a match if same event",
        "",
        f"Review these {len(candidates)} candidate pairs and return a JSON array:",
        "",
        "```json",
        "[",
        '  {"pair_index": 0, "match": true, "confidence": 0.95, "outcome_mapping": {"Yes": "Yes", "No": "No"}, "explanation": "Both ask if X happens by Y date"},',
        '  {"pair_index": 1, "match": false, "confidence": 0.9, "outcome_mapping": null, "explanation": "Same topic but different thresholds"}',
        "]",
        "```",
        "",
        "CANDIDATES:",
        "",
    ]

    for i, c in enumerate(candidates):
        lines.append(f"--- Pair {i} ---")
        lines.append(f"Market A [{c['market_a_platform']}] (id={c['market_a_id']}):")
        lines.append(f"  Question: {c['market_a_question']}")
        lines.append(f"  Outcomes: {json.dumps(c['market_a_outcomes'])}")
        lines.append(f"  Prices:   {json.dumps(c['market_a_outcome_prices'])}")
        lines.append(f"  Expires:  {c['market_a_end_date']}")
        lines.append(f"Market B [{c['market_b_platform']}] (id={c['market_b_id']}):")
        lines.append(f"  Question: {c['market_b_question']}")
        lines.append(f"  Outcomes: {json.dumps(c['market_b_outcomes'])}")
        lines.append(f"  Prices:   {json.dumps(c['market_b_outcome_prices'])}")
        lines.append(f"  Expires:  {c['market_b_end_date']}")
        lines.append(f"  TF-IDF:   {c['tfidf_score']}")
        lines.append("")

    return "\n".join(lines)


async def main() -> None:
    """CLI entrypoint: generate candidates and output JSON or prompt."""
    show_prompt = "--prompt" in sys.argv

    async with get_background_session_factory()() as db:
        candidates = await generate_candidates(db)

    if show_prompt:
        print(build_llm_prompt(candidates))
    else:
        print(json.dumps(candidates, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
