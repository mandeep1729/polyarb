"""Service for querying market groups and their analytics."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import Select, and_, desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.categories import resolve_category
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
        sort_by: str = "liquidity",
        limit: int = 20,
        cursor: str | None = None,
    ) -> PaginatedResponse[GroupResponse]:
        """Return paginated list of active groups."""
        base = select(MarketGroup).where(
            MarketGroup.is_active.is_(True),
            MarketGroup.member_count > 1,
        )

        filters = []
        if category:
            db_cat = resolve_category(category)
            if db_cat:
                filters.append(MarketGroup.category == db_cat)
            else:
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

    async def search_groups(
        self,
        query: str,
        category: str | None = None,
        sort_by: str = "liquidity",
        limit: int = 20,
    ) -> PaginatedResponse[GroupResponse]:
        """Full-text search on group canonical_question with ILIKE fallback."""
        ts_query = func.plainto_tsquery("english", query)
        ts_vector = func.to_tsvector("english", MarketGroup.canonical_question)
        rank = func.ts_rank(ts_vector, ts_query)

        stmt = (
            select(MarketGroup, rank.label("rank"))
            .where(
                MarketGroup.is_active.is_(True),
                MarketGroup.member_count > 1,
                ts_vector.bool_op("@@")(ts_query),
            )
        )

        if category:
            db_cat = resolve_category(category)
            if db_cat:
                stmt = stmt.where(MarketGroup.category == db_cat)

        sort_col = SORT_COLUMNS.get(sort_by, MarketGroup.disagreement_score)
        stmt = stmt.order_by(desc("rank"), desc(sort_col).nulls_last()).limit(limit)

        result = await self._db.execute(stmt)
        rows = result.all()

        # ILIKE fallback when FTS returns fewer than limit
        if len(rows) < limit:
            like_pattern = f"%{query.lower()}%"
            existing_ids = {row[0].id for row in rows}

            fallback = select(MarketGroup).where(
                MarketGroup.is_active.is_(True),
                MarketGroup.member_count > 1,
                func.lower(MarketGroup.canonical_question).like(like_pattern),
            )
            if existing_ids:
                fallback = fallback.where(MarketGroup.id.not_in(existing_ids))
            if category:
                db_cat = resolve_category(category)
                if db_cat:
                    fallback = fallback.where(MarketGroup.category == db_cat)

            fallback = fallback.order_by(
                desc(sort_col).nulls_last()
            ).limit(limit - len(rows))

            fb_result = await self._db.execute(fallback)
            fb_groups = fb_result.scalars().all()
            all_groups = [row[0] for row in rows] + list(fb_groups)
        else:
            all_groups = [row[0] for row in rows]

        items = [GroupResponse.model_validate(g) for g in all_groups]
        return PaginatedResponse(items=items, next_cursor=None, total=len(items))

    async def get_category_counts(self) -> list[dict]:
        """Return category counts for active groups with >1 member."""
        result = await self._db.execute(
            select(MarketGroup.category, func.count())
            .where(
                MarketGroup.is_active.is_(True),
                MarketGroup.member_count > 1,
                MarketGroup.category.isnot(None),
            )
            .group_by(MarketGroup.category)
        )
        from app.categories import DISPLAY_NAMES
        return [
            {"category": row[0], "display_name": DISPLAY_NAMES.get(row[0], row[0].title()), "count": row[1]}
            for row in result.all()
        ]

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
