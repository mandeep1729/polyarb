"""Service for querying market groups and their analytics."""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import structlog
from sqlalchemy import Float, Select, and_, case, cast, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.categories import resolve_category
from app.services.search_utils import build_tsquery
from app.models.market import UnifiedMarket
from app.models.market_group import MarketGroup, MarketGroupMember
from app.models.price_history import PriceSnapshot
from app.models.platform import Platform
from app.schemas.common import PaginatedResponse
from app.schemas.group import (
    GroupDetailResponse,
    GroupResponse,
    GroupSnapshotResponse,
)
from app.schemas.market import MarketResponse

logger = structlog.get_logger()

SORT_COLUMNS = {
    "disagreement": MarketGroup.disagreement_score,
    "volume": MarketGroup.total_volume,
    "liquidity": MarketGroup.total_liquidity,
    "consensus": MarketGroup.consensus_yes,
    "created_at": MarketGroup.created_at,
}

_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"
_TAG_NOISE: frozenset[str] = frozenset(json.loads((_CONFIG_DIR / "tag_noise.json").read_text()))

# Build verb set: base forms + inflected forms (3rd person, past, gerund)
_VERB_ROOTS: list[str] = json.loads((_CONFIG_DIR / "tag_verbs.json").read_text())


def _build_verb_set(roots: list[str]) -> frozenset[str]:
    forms: set[str] = set()
    for v in roots:
        forms.add(v)
        # -s / -es / -ies
        if v.endswith(("s", "x", "z", "ch", "sh")):
            forms.add(v + "es")
        elif v.endswith("y") and len(v) > 1 and v[-2] not in "aeiou":
            forms.add(v[:-1] + "ies")
        else:
            forms.add(v + "s")
        # -ed / -ied / -d
        if v.endswith("e"):
            forms.add(v + "d")
        elif v.endswith("y") and len(v) > 1 and v[-2] not in "aeiou":
            forms.add(v[:-1] + "ied")
        else:
            forms.add(v + "ed")
        # -ing
        if v.endswith("e") and not v.endswith("ee"):
            forms.add(v[:-1] + "ing")
        else:
            forms.add(v + "ing")
    return frozenset(forms)


_TAG_VERBS = _build_verb_set(_VERB_ROOTS)

_YEAR_RE = re.compile(r"^(19|20)\d{2}$")
_TIME_RE = re.compile(r"^\d{1,2}[ap]m$")
_ORDINAL_RE = re.compile(r"^\d+(?:st|nd|rd|th)$")
_MONEY_SIZE_RE = re.compile(r"^\d+[bkmt]{1,2}$")
_BASIS_POINTS_RE = re.compile(r"^\d+bps?$")
_TEMPERATURE_RE = re.compile(r"^\d+[°ºcf]+$")

_NUMERIC_NOISE_PATTERNS = (_TIME_RE, _ORDINAL_RE, _MONEY_SIZE_RE, _BASIS_POINTS_RE, _TEMPERATURE_RE)


def extract_word_counts(questions: list[str]) -> Counter[str]:
    """Extract word frequency counts from a list of market question texts."""
    from app.matching.text import STOP_WORDS, _PUNCTUATION_RE

    counter: Counter[str] = Counter()
    for q in questions:
        if not q:
            continue
        text = _PUNCTUATION_RE.sub(" ", q.lower())
        for word in text.split():
            if (
                len(word) > 2
                and word not in STOP_WORDS
                and word not in _TAG_NOISE
                and word not in _TAG_VERBS
                and not word.isdigit()
                and not _YEAR_RE.match(word)
                and not any(p.match(word) for p in _NUMERIC_NOISE_PATTERNS)
            ):
                counter[word] += 1
    return counter


class GroupService:
    """Query market groups, their members, and historical consensus data."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    @staticmethod
    def _end_date_subquery(
        end_date_min: str | None, end_date_max: str | None,
    ) -> Select | None:
        """Build a subquery filtering groups by member end_date range."""
        if end_date_min is None and end_date_max is None:
            return None
        conditions = []
        if end_date_min is not None:
            conditions.append(UnifiedMarket.end_date >= end_date_min)
        if end_date_max is not None:
            conditions.append(UnifiedMarket.end_date <= end_date_max)
        return (
            select(MarketGroupMember.group_id)
            .join(UnifiedMarket, UnifiedMarket.id == MarketGroupMember.market_id)
            .where(*conditions)
        )

    async def get_groups(
        self,
        category: str | None = None,
        sort_by: str = "liquidity",
        end_date_min: str | None = None,
        end_date_max: str | None = None,
        exclude_expired: bool = True,
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
        if exclude_expired:
            now = datetime.now(timezone.utc)
            active_subq = (
                select(MarketGroupMember.group_id)
                .join(UnifiedMarket, UnifiedMarket.id == MarketGroupMember.market_id)
                .where(
                    (UnifiedMarket.end_date >= now) | (UnifiedMarket.end_date.is_(None))
                )
            )
            filters.append(MarketGroup.id.in_(active_subq))
        member_subq = self._end_date_subquery(end_date_min, end_date_max)
        if member_subq is not None:
            filters.append(MarketGroup.id.in_(member_subq))
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

        logger.info("group_service_get_groups", total=total, returned=len(items), category=category, sort_by=sort_by)

        return PaginatedResponse(items=items, next_cursor=next_cursor, total=total)

    async def search_groups(
        self,
        query: str,
        category: str | None = None,
        sort_by: str = "liquidity",
        end_date_min: str | None = None,
        end_date_max: str | None = None,
        exclude_expired: bool = True,
        limit: int = 20,
    ) -> PaginatedResponse[GroupResponse]:
        """Full-text search on group canonical_question with ILIKE fallback."""
        db_cat = resolve_category(category) if category else None

        or_query = build_tsquery(query)
        ts_query = func.to_tsquery("english", or_query)
        ts_vector = func.to_tsvector("english", MarketGroup.canonical_question)
        rank = func.ts_rank(ts_vector, ts_query)

        stmt = (
            select(MarketGroup, rank.label("rank"))
            .where(
                MarketGroup.is_active.is_(True),
                ts_vector.bool_op("@@")(ts_query),
            )
        )

        if db_cat:
            stmt = stmt.where(MarketGroup.category == db_cat)
        if exclude_expired:
            now = datetime.now(timezone.utc)
            active_subq = (
                select(MarketGroupMember.group_id)
                .join(UnifiedMarket, UnifiedMarket.id == MarketGroupMember.market_id)
                .where(
                    (UnifiedMarket.end_date >= now) | (UnifiedMarket.end_date.is_(None))
                )
            )
            stmt = stmt.where(MarketGroup.id.in_(active_subq))
        member_subq = self._end_date_subquery(end_date_min, end_date_max)
        if member_subq is not None:
            stmt = stmt.where(MarketGroup.id.in_(member_subq))

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
                func.lower(MarketGroup.canonical_question).like(like_pattern),
            )
            if existing_ids:
                fallback = fallback.where(MarketGroup.id.not_in(existing_ids))
            if db_cat:
                fallback = fallback.where(MarketGroup.category == db_cat)
            if member_subq is not None:
                fallback = fallback.where(MarketGroup.id.in_(member_subq))

            fallback = fallback.order_by(
                desc(sort_col).nulls_last()
            ).limit(limit - len(rows))

            fb_result = await self._db.execute(fallback)
            fb_groups = fb_result.scalars().all()
            all_groups = [row[0] for row in rows] + list(fb_groups)
        else:
            all_groups = [row[0] for row in rows]

        items = [GroupResponse.model_validate(g) for g in all_groups]

        logger.info("group_service_search_groups", query=query, total=len(items), category=category)

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

    async def get_tags(self, limit: int = 50) -> list[dict]:
        """Return most frequent terms from active market questions."""
        result = await self._db.execute(
            select(UnifiedMarket.question).where(
                UnifiedMarket.is_active.is_(True),
            )
        )
        questions = result.scalars().all()
        counter = extract_word_counts(questions)
        return [
            {"term": term, "count": count}
            for term, count in counter.most_common(limit)
        ]

    async def get_group_detail(self, group_id: int) -> GroupDetailResponse | None:
        """Return group with all member markets and best-odds markets."""
        result = await self._db.execute(
            select(MarketGroup).where(MarketGroup.id == group_id)
        )
        group = result.scalar_one_or_none()
        if group is None:
            logger.info("group_service_group_not_found", group_id=group_id)
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
        """Derive consensus history from member market price snapshots."""
        max_days = min(days, 90)
        since = datetime.now(timezone.utc) - timedelta(days=max_days)

        yes_price = cast(PriceSnapshot.outcome_prices["Yes"].as_string(), Float)
        no_price = cast(PriceSnapshot.outcome_prices["No"].as_string(), Float)

        stmt = (
            select(
                PriceSnapshot.timestamp,
                func.avg(yes_price).label("consensus_yes"),
                func.avg(no_price).label("consensus_no"),
                case(
                    (
                        func.count(yes_price) >= 2,
                        func.max(yes_price) - func.min(yes_price),
                    ),
                    else_=None,
                ).label("disagreement_score"),
                func.sum(PriceSnapshot.volume).label("total_volume"),
            )
            .join(
                MarketGroupMember,
                MarketGroupMember.market_id == PriceSnapshot.market_id,
            )
            .where(
                MarketGroupMember.group_id == group_id,
                PriceSnapshot.timestamp >= since,
            )
            .group_by(PriceSnapshot.timestamp)
            .order_by(PriceSnapshot.timestamp)
        )

        result = await self._db.execute(stmt)
        rows = result.all()

        return [
            GroupSnapshotResponse(
                timestamp=row.timestamp,
                consensus_yes=round(row.consensus_yes, 4) if row.consensus_yes is not None else None,
                consensus_no=round(row.consensus_no, 4) if row.consensus_no is not None else None,
                disagreement_score=round(row.disagreement_score, 4) if row.disagreement_score is not None else None,
                total_volume=round(row.total_volume, 2) if row.total_volume is not None else None,
            )
            for row in rows
        ]

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
