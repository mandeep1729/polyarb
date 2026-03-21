import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.arbitrage import ArbitrageListResponse
from app.services.arbitrage_service import ArbitrageService

logger = structlog.get_logger()

router = APIRouter(prefix="/arbitrage", tags=["arbitrage"])


@router.get("", response_model=ArbitrageListResponse)
async def list_opportunities(
    min_delta: float = Query(0.0, ge=0.0, description="Minimum odds delta"),
    sort_by: str = Query("odds_delta", description="Sort field: odds_delta, similarity_score"),
    category: str | None = Query(None, description="Filter by category"),
    limit: int = Query(20, ge=1, le=100, description="Page size"),
    cursor: str | None = Query(None, description="Pagination cursor"),
    db: AsyncSession = Depends(get_db),
) -> ArbitrageListResponse:
    service = ArbitrageService(db)
    return await service.get_opportunities(
        min_delta=min_delta,
        sort_by=sort_by,
        category=category,
        limit=limit,
        cursor=cursor,
    )


class ManualPairInput(BaseModel):
    """Request body for manually pairing two markets."""

    market_a_id: int
    market_b_id: int


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
