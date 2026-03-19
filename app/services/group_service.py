"""Service for querying market groups and their analytics."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import Select, and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.group_snapshot import GroupPriceSnapshot
from app.models.market import UnifiedMarket
from app.models.market_group import MarketGroup, MarketGroupMember
from app.models.platform import Platform
from app.schemas.common import PaginatedResponse
from app.schemas.group import (
    GroupDetailResponse,
    GroupResponse,
    GroupSnapshotResponse,
)
from app.schemas.market import MarketResponse

SORT_COLUMNS = {
    "disagreement": MarketGroup.disagreement_score,
    "volume": MarketGroup.total_volume,
    "liquidity": MarketGroup.total_liquidity,
    "consensus": MarketGroup.consensus_yes,
    "created_at": MarketGroup.created_at,
}


class GroupService:
    """Query market groups, their members, and historical consensus data."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_groups(
        self,
        category: str | None = None,
        sort_by: str = "disagreement",
        limit: int = 20,
        cursor: str | None = None,
    ) -> PaginatedResponse[GroupResponse]:
        """Return paginated list of active groups."""
        base = select(MarketGroup).where(MarketGroup.is_active.is_(True))

        filters = []
        if category:
            filters.append(MarketGroup.category == category)
        if cursor:
            filters.append(MarketGroup.id > int(cursor))
        if filters:
            base = base.where(and_(*filters))

        # Count
        count_q = select(func.count()).select_from(
            base.with_only_columns(MarketGroup.id).subquery()
        )
        total = (await self._db.execute(count_q)).scalar_one()

        # Sort + limit
        sort_col = SORT_COLUMNS.get(sort_by, MarketGroup.disagreement_score)
        base = base.order_by(desc(sort_col).nulls_last(), MarketGroup.id).limit(limit)

        result = await self._db.execute(base)
        groups = result.scalars().all()

        items = [GroupResponse.model_validate(g) for g in groups]
        next_cursor = str(groups[-1].id) if len(groups) == limit else None

        return PaginatedResponse(items=items, next_cursor=next_cursor, total=total)

    async def get_group_detail(self, group_id: int) -> GroupDetailResponse | None:
        """Return group with all member markets and best-odds markets."""
        result = await self._db.execute(
            select(MarketGroup).where(MarketGroup.id == group_id)
        )
        group = result.scalar_one_or_none()
        if group is None:
            return None

        # Get members with platform info
        members_result = await self._db.execute(
            select(UnifiedMarket, Platform.name, Platform.slug)
            .join(MarketGroupMember, MarketGroupMember.market_id == UnifiedMarket.id)
            .join(Platform, Platform.id == UnifiedMarket.platform_id)
            .where(MarketGroupMember.group_id == group_id)
            .order_by(desc(UnifiedMarket.liquidity).nulls_last())
        )
        member_rows = members_result.all()

        members = [
            self._to_market_response(row[0], row[1], row[2])
            for row in member_rows
        ]

        # Find best-odds markets
        best_yes = None
        best_no = None
        if group.best_yes_market_id:
            best_yes = await self._get_market_response(group.best_yes_market_id)
        if group.best_no_market_id:
            best_no = await self._get_market_response(group.best_no_market_id)

        return GroupDetailResponse(
            group=GroupResponse.model_validate(group),
            members=members,
            best_yes_market=best_yes,
            best_no_market=best_no,
        )

    async def get_group_history(
        self,
        group_id: int,
        days: int = 30,
    ) -> list[GroupSnapshotResponse]:
        """Return materialized consensus history for a group."""
        max_days = min(days, 90)
        since = datetime.now(timezone.utc) - timedelta(days=max_days)

        result = await self._db.execute(
            select(GroupPriceSnapshot)
            .where(GroupPriceSnapshot.group_id == group_id)
            .where(GroupPriceSnapshot.timestamp >= since)
            .order_by(GroupPriceSnapshot.timestamp)
        )
        snapshots = result.scalars().all()

        return [GroupSnapshotResponse.model_validate(s) for s in snapshots]

    async def _get_market_response(self, market_id: int) -> MarketResponse | None:
        """Fetch a single market with platform info as MarketResponse."""
        result = await self._db.execute(
            select(UnifiedMarket, Platform.name, Platform.slug)
            .join(Platform, Platform.id == UnifiedMarket.platform_id)
            .where(UnifiedMarket.id == market_id)
        )
        row = result.one_or_none()
        if row is None:
            return None
        return self._to_market_response(row[0], row[1], row[2])

    @staticmethod
    def _to_market_response(
        market: UnifiedMarket, platform_name: str, platform_slug: str
    ) -> MarketResponse:
        """Convert a UnifiedMarket + platform info to MarketResponse."""
        return MarketResponse(
            id=market.id,
            platform_id=market.platform_id,
            platform_name=platform_name,
            platform_slug=platform_slug,
            platform_market_id=market.platform_market_id,
            question=market.question,
            description=market.description,
            category=market.category,
            event_ticker=market.event_ticker,
            series_ticker=market.series_ticker,
            yes_ask=market.yes_ask,
            no_ask=market.no_ask,
            outcomes=market.outcomes,
            outcome_prices=market.outcome_prices,
            volume_total=market.volume_total,
            volume_24h=market.volume_24h,
            liquidity=market.liquidity,
            start_date=market.start_date,
            end_date=market.end_date,
            status=market.status,
            resolution=market.resolution,
            deep_link_url=market.deep_link_url,
            image_url=market.image_url,
            price_change_24h=market.price_change_24h,
            last_synced_at=market.last_synced_at,
            created_at=market.created_at,
            updated_at=market.updated_at,
        )
