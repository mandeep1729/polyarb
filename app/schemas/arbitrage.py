from pydantic import BaseModel

from app.schemas.common import PaginatedResponse
from app.schemas.market import MarketResponse


class ArbitrageOpportunity(BaseModel):
    id: int
    market_a: MarketResponse
    market_b: MarketResponse
    similarity_score: float
    odds_delta: float | None = None
    match_method: str

    model_config = {"from_attributes": True}


ArbitrageListResponse = PaginatedResponse[ArbitrageOpportunity]
