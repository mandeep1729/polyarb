from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class OddsFormat(str, Enum):
    percentage = "percentage"
    decimal = "decimal"
    fractional = "fractional"


class MarketStatus(str, Enum):
    active = "active"
    closed = "closed"
    resolved = "resolved"


class SortField(str, Enum):
    volume_24h = "volume_24h"
    end_date = "end_date"
    created_at = "created_at"
    price_change_24h = "price_change_24h"


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = None
    total: int
