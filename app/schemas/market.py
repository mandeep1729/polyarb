from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import PaginatedResponse


class MarketResponse(BaseModel):
    id: int
    platform_id: int
    platform_name: str
    platform_slug: str
    platform_market_id: str
    question: str
    description: str | None = None
    category: str | None = None
    outcomes: dict
    outcome_prices: dict
    event_ticker: str | None = None
    series_ticker: str | None = None
    yes_ask: float | None = None
    no_ask: float | None = None
    volume_total: float | None = None
    volume_24h: float | None = None
    liquidity: float | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    status: str
    resolution: str | None = None
    deep_link_url: str | None = None
    image_url: str | None = None
    price_change_24h: float | None = None
    last_synced_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


MarketListResponse = PaginatedResponse[MarketResponse]


class PriceSnapshotResponse(BaseModel):
    outcome_prices: dict
    volume: float | None = None
    timestamp: datetime

    model_config = {"from_attributes": True}


class TrendingMarketResponse(BaseModel):
    market: MarketResponse
    trending_score: float
