import json
from datetime import datetime, timezone
from pathlib import Path

import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.matching.scorer import score_pair
from app.matching.text import build_tfidf_matrix, get_candidates, preprocess
from app.models.market import UnifiedMarket
from app.models.matched_market import MatchedMarketPair
from app.models.price_history import latest_snapshot_subquery

logger = structlog.get_logger()

MATCH_THRESHOLD = 0.55
_LAST_RUN_PATH = Path("data/matching_last_run.json")


def _load_last_run_start() -> datetime | None:
    """Load the start time of the previous matching run."""
    if not _LAST_RUN_PATH.exists():
        return None
    try:
        data = json.loads(_LAST_RUN_PATH.read_text())
        return datetime.fromisoformat(data["last_run_start"])
    except (json.JSONDecodeError, KeyError, ValueError, OSError):
        return None


def _save_last_run_start(ts: datetime) -> None:
    """Persist the start time of the current matching run."""
    _LAST_RUN_PATH.parent.mkdir(parents=True, exist_ok=True)
    _LAST_RUN_PATH.write_text(json.dumps({"last_run_start": ts.isoformat()}))


class MatchingService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def run_matching(self) -> int:
        now = datetime.now(timezone.utc)
        last_run_start = _load_last_run_start()
        _save_last_run_start(now)
        snap = latest_snapshot_subquery()
        result = await self._db.execute(
            select(UnifiedMarket)
            .join(snap, snap.c.market_id == UnifiedMarket.id)
            .where(UnifiedMarket.is_active.is_(True))
            .where(UnifiedMarket.status == "active")
            .where(or_(UnifiedMarket.end_date.is_(None), UnifiedMarket.end_date >= now))
            .where(snap.c.liquidity >= 100)
        )
        markets = result.scalars().all()

        if len(markets) < 2:
            logger.info("matching_skipped", reason="insufficient_markets", count=len(markets))
            return 0

        platform_groups: dict[int, list[UnifiedMarket]] = {}
        for m in markets:
            platform_groups.setdefault(m.platform_id, []).append(m)

        if len(platform_groups) < 2:
            logger.info("matching_skipped", reason="single_platform")
            return 0

        existing_result = await self._db.execute(
            select(MatchedMarketPair.market_a_id, MatchedMarketPair.market_b_id)
        )
        existing_pairs: set[tuple[int, int]] = {
            (row[0], row[1]) for row in existing_result.all()
        }

        questions = [m.question for m in markets]
        preprocessed = [preprocess(q, category=m.category) for q, m in zip(questions, markets)]
        tfidf_matrix, vectorizer = build_tfidf_matrix(preprocessed)

        new_pairs = 0
        platform_ids = sorted(platform_groups.keys())

        for i in range(len(platform_ids)):
            for j in range(i + 1, len(platform_ids)):
                pid_a = platform_ids[i]
                pid_b = platform_ids[j]
                markets_a = platform_groups[pid_a]
                markets_b = platform_groups[pid_b]

                indices_a = [markets.index(m) for m in markets_a]
                indices_b = [markets.index(m) for m in markets_b]

                for idx_a in indices_a:
                    query_vec = tfidf_matrix[idx_a]
                    candidates = get_candidates(
                        query_vec, tfidf_matrix, threshold=0.3
                    )

                    for idx_b, tfidf_score in candidates:
                        if idx_b not in indices_b:
                            continue

                        m_a = markets[idx_a]
                        m_b = markets[idx_b]

                        pair_key = (min(m_a.id, m_b.id), max(m_a.id, m_b.id))
                        if pair_key in existing_pairs:
                            continue

                        if (
                            last_run_start
                            and m_a.created_at < last_run_start
                            and m_b.created_at < last_run_start
                        ):
                            continue

                        composite = score_pair(
                            q1=m_a.question,
                            q2=m_b.question,
                            cat1=m_a.category,
                            cat2=m_b.category,
                            end1=m_a.end_date,
                            end2=m_b.end_date,
                            tfidf_score=tfidf_score,
                        )

                        if composite >= MATCH_THRESHOLD:
                            matched = MatchedMarketPair(
                                market_a_id=pair_key[0],
                                market_b_id=pair_key[1],
                                similarity_score=round(composite, 4),
                                match_method="tfidf_fuzzy",
                                category=m_a.category or m_b.category,
                            )
                            self._db.add(matched)
                            existing_pairs.add(pair_key)
                            new_pairs += 1

        logger.info("matching_complete", new_pairs=new_pairs, total_markets=len(markets))
        return new_pairs
