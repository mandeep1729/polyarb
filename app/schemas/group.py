"""Schemas for market group API responses."""
from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import PaginatedResponse
from app.schemas.market import MarketResponse


class GroupResponse(BaseModel):
    """Summary view of a market group (used in list/feed)."""

    id: int
    canonical_question: str
    category: str | None = None
    consensus_yes: float | None = None
    consensus_no: float | None = None
    disagreement_score: float | None = None
    member_count: int = 0
    total_volume: float | None = None
    total_liquidity: float | None = None
    best_yes_market_id: int | None = None
    best_no_market_id: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GroupDetailResponse(BaseModel):
    """Detailed view of a market group with member markets."""

    group: GroupResponse
    members: list[MarketResponse]
    best_yes_market: MarketResponse | None = None
    best_no_market: MarketResponse | None = None


class GroupSnapshotResponse(BaseModel):
    """A single point in the group consensus history."""

    consensus_yes: float | None = None
    consensus_no: float | None = None
    disagreement_score: float | None = None
    total_volume: float | None = None
    timestamp: datetime

    model_config = {"from_attributes": True}


GroupListResponse = PaginatedResponse[GroupResponse]
