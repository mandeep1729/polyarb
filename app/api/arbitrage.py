import asyncio
import json

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_redis_cache
from app.cache import RedisCache
from app.schemas.arbitrage import ArbitrageListResponse
from app.services.arbitrage_service import ArbitrageService

logger = structlog.get_logger()

router = APIRouter(prefix="/arbitrage", tags=["arbitrage"])


@router.get("", response_model=ArbitrageListResponse)
async def list_opportunities(
    min_delta: float = Query(0.0, ge=0.0, description="Minimum odds delta"),
    sort_by: str = Query("odds_delta", description="Sort field: odds_delta, similarity_score"),
    category: str | None = Query(None, description="Filter by category"),
    hide_onesided: bool = Query(True, description="Hide pairs where either leg trades above 97c"),
    limit: int = Query(20, ge=1, le=100, description="Page size"),
    cursor: str | None = Query(None, description="Pagination cursor"),
    db: AsyncSession = Depends(get_db),
) -> ArbitrageListResponse:
    service = ArbitrageService(db)
    return await service.get_opportunities(
        min_delta=min_delta,
        sort_by=sort_by,
        category=category,
        hide_onesided=hide_onesided,
        limit=limit,
        cursor=cursor,
    )


class ManualPairInput(BaseModel):
    """Request body for manually pairing two markets."""

    market_a_id: int
    market_b_id: int


class LLMVerifiedPair(BaseModel):
    """A single verified pair from LLM review."""

    market_a_id: int
    market_b_id: int
    confidence: float
    outcome_mapping: dict[str, str] | None = None
    explanation: str | None = None


class ImportVerifiedInput(BaseModel):
    """Batch of LLM-verified pairs to import."""

    pairs: list[LLMVerifiedPair]


@router.post("/pair", status_code=201)
async def create_manual_pair(
    body: ManualPairInput,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Manually pair two markets for arbitrage tracking."""
    if body.market_a_id == body.market_b_id:
        raise HTTPException(status_code=400, detail="Markets must be different")
    service = ArbitrageService(db)
    try:
        pair = await service.create_manual_pair(body.market_a_id, body.market_b_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "id": pair.id,
        "market_a_id": pair.market_a_id,
        "market_b_id": pair.market_b_id,
        "odds_delta": pair.odds_delta,
        "match_method": pair.match_method,
    }


@router.post("/import-verified", status_code=201)
async def import_verified_pairs(
    body: ImportVerifiedInput,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Import a batch of LLM-verified market pairs."""
    service = ArbitrageService(db)
    imported = 0
    skipped = 0
    errors: list[str] = []

    for p in body.pairs:
        try:
            await service.create_verified_pair(
                market_a_id=p.market_a_id,
                market_b_id=p.market_b_id,
                confidence=p.confidence,
                outcome_mapping=p.outcome_mapping,
                explanation=p.explanation,
            )
            imported += 1
        except ValueError as exc:
            skipped += 1
            errors.append(f"{p.market_a_id}-{p.market_b_id}: {exc}")

    logger.info(
        "import_verified_pairs",
        imported=imported,
        skipped=skipped,
    )
    return {"imported": imported, "skipped": skipped, "errors": errors}


CANDIDATES_CACHE_KEY = "embedding_candidates"
CANDIDATES_TTL = 86400  # 24 hours
_generating = False


@router.post("/candidates/generate")
async def generate_candidates(
    threshold: float = Query(0.85, ge=0.5, le=1.0),
    db: AsyncSession = Depends(get_db),
    cache: RedisCache = Depends(get_redis_cache),
) -> dict:
    """Trigger embedding candidate generation in the background."""
    global _generating
    if _generating:
        raise HTTPException(status_code=409, detail="Generation already in progress")

    async def _run() -> None:
        global _generating
        try:
            from app.database import get_background_session_factory
            from app.tasks.embed_candidates import find_embedding_candidates

            async with get_background_session_factory()() as bg_db:
                candidates = await find_embedding_candidates(bg_db, threshold=threshold)
            await cache.set(CANDIDATES_CACHE_KEY, json.dumps(candidates), ttl=CANDIDATES_TTL)
            logger.info("candidates_generated", count=len(candidates), threshold=threshold)
        except Exception as exc:
            logger.error("candidates_generation_failed", error=str(exc), exc_info=True)
        finally:
            _generating = False

    _generating = True
    asyncio.create_task(_run())
    return {"status": "started", "threshold": threshold}


@router.get("/candidates")
async def list_candidates(
    cache: RedisCache = Depends(get_redis_cache),
) -> dict:
    """Return cached embedding candidates."""
    raw = await cache.get(CANDIDATES_CACHE_KEY)
    if raw is None:
        return {"candidates": [], "stale": True}
    candidates = json.loads(raw)
    return {"candidates": candidates, "stale": False}


class ApproveCandidateInput(BaseModel):
    """Approve a specific candidate by market IDs."""

    market_a_id: int
    market_b_id: int
    confidence: float = 1.0


@router.post("/candidates/approve", status_code=201)
async def approve_candidate(
    body: ApproveCandidateInput,
    db: AsyncSession = Depends(get_db),
    cache: RedisCache = Depends(get_redis_cache),
) -> dict:
    """Approve an embedding candidate — creates a verified pair and removes from cache."""
    service = ArbitrageService(db)
    try:
        pair = await service.create_verified_pair(
            market_a_id=body.market_a_id,
            market_b_id=body.market_b_id,
            confidence=body.confidence,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Remove approved candidate from cache
    raw = await cache.get(CANDIDATES_CACHE_KEY)
    if raw:
        candidates = json.loads(raw)
        candidates = [
            c for c in candidates
            if not (
                {c["market_a_id"], c["market_b_id"]}
                == {body.market_a_id, body.market_b_id}
            )
        ]
        await cache.set(CANDIDATES_CACHE_KEY, json.dumps(candidates), ttl=CANDIDATES_TTL)

    return {
        "id": pair.id,
        "market_a_id": pair.market_a_id,
        "market_b_id": pair.market_b_id,
        "odds_delta": pair.odds_delta,
    }


@router.post("/candidates/dismiss")
async def dismiss_candidate(
    body: ApproveCandidateInput,
    cache: RedisCache = Depends(get_redis_cache),
) -> dict:
    """Dismiss a candidate — removes from cache without creating a pair."""
    raw = await cache.get(CANDIDATES_CACHE_KEY)
    if raw:
        candidates = json.loads(raw)
        before = len(candidates)
        candidates = [
            c for c in candidates
            if not (
                {c["market_a_id"], c["market_b_id"]}
                == {body.market_a_id, body.market_b_id}
            )
        ]
        await cache.set(CANDIDATES_CACHE_KEY, json.dumps(candidates), ttl=CANDIDATES_TTL)
        return {"removed": before - len(candidates)}
    return {"removed": 0}
