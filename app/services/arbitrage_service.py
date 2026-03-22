import structlog
from sqlalchemy import Float, and_, cast, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.market import UnifiedMarket
from app.models.matched_market import MatchedMarketPair
from app.models.platform import Platform
from app.models.price_history import (
    PriceSnapshot,
    latest_snapshot_subquery,
    load_snap_map,
    snap_select_columns,
    snap_to_dict,
)
from app.schemas.arbitrage import ArbitrageListResponse, ArbitrageOpportunity
from app.schemas.market import MarketResponse

logger = structlog.get_logger()


class ArbitrageService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    ONE_SIDED_THRESHOLD = 0.97

    async def get_opportunities(
        self,
        min_delta: float = 0.0,
        sort_by: str = "odds_delta",
        category: str | None = None,
        hide_onesided: bool = True,
        limit: int = 20,
        cursor: str | None = None,
    ) -> ArbitrageListResponse:
        MarketA = aliased(UnifiedMarket, flat=True)
        MarketB = aliased(UnifiedMarket, flat=True)
        PlatformA = aliased(Platform, flat=True)
        PlatformB = aliased(Platform, flat=True)

        snap_a = latest_snapshot_subquery("snap_a")
        snap_b = latest_snapshot_subquery("snap_b")

        stmt = (
            select(
                MatchedMarketPair,
                MarketA,
                MarketB,
                PlatformA.name.label("platform_a_name"),
                PlatformA.slug.label("platform_a_slug"),
                PlatformB.name.label("platform_b_name"),
                PlatformB.slug.label("platform_b_slug"),
                *snap_select_columns(snap_a, "sa"),
                *snap_select_columns(snap_b, "sb"),
            )
            .join(MarketA, MarketA.id == MatchedMarketPair.market_a_id)
            .join(MarketB, MarketB.id == MatchedMarketPair.market_b_id)
            .join(PlatformA, PlatformA.id == MarketA.platform_id)
            .join(PlatformB, PlatformB.id == MarketB.platform_id)
            .outerjoin(snap_a, snap_a.c.market_id == MarketA.id)
            .outerjoin(snap_b, snap_b.c.market_id == MarketB.id)
        )

        filters = []
        if min_delta > 0:
            filters.append(func.abs(func.coalesce(MatchedMarketPair.odds_delta, 0)) >= min_delta)
        if category:
            filters.append(MatchedMarketPair.category == category)
        if hide_onesided:
            jt_a = func.jsonb_each_text(snap_a.c.outcome_prices).table_valued("key", "value")
            max_price_a = (
                select(func.coalesce(func.max(cast(jt_a.c.value, Float)), 0.0))
                .correlate(snap_a)
                .scalar_subquery()
            )
            jt_b = func.jsonb_each_text(snap_b.c.outcome_prices).table_valued("key", "value")
            max_price_b = (
                select(func.coalesce(func.max(cast(jt_b.c.value, Float)), 0.0))
                .correlate(snap_b)
                .scalar_subquery()
            )
            filters.append(max_price_a <= self.ONE_SIDED_THRESHOLD)
            filters.append(max_price_b <= self.ONE_SIDED_THRESHOLD)
        if cursor:
            filters.append(MatchedMarketPair.id > int(cursor))
        if filters:
            stmt = stmt.where(and_(*filters))

        count_stmt = select(func.count()).select_from(
            stmt.with_only_columns(MatchedMarketPair.id).subquery()
        )
        total_result = await self._db.execute(count_stmt)
        total = total_result.scalar_one()

        if sort_by == "odds_delta":
            stmt = stmt.order_by(
                desc(func.abs(func.coalesce(MatchedMarketPair.odds_delta, 0))),
                MatchedMarketPair.id,
            )
        else:
            stmt = stmt.order_by(
                desc(MatchedMarketPair.similarity_score),
                MatchedMarketPair.id,
            )

        stmt = stmt.limit(limit)
        result = await self._db.execute(stmt)
        rows = result.all()

        items = []
        for row in rows:
            pair = row[0]
            ma = row[1]
            mb = row[2]
            pa_name = row[3]
            pa_slug = row[4]
            pb_name = row[5]
            pb_slug = row[6]

            snap_a_data = snap_to_dict(row, "sa")
            snap_b_data = snap_to_dict(row, "sb")

            market_a_resp = self._row_to_market_response(ma, pa_name, pa_slug, snap=snap_a_data)
            market_b_resp = self._row_to_market_response(mb, pb_name, pb_slug, snap=snap_b_data)

            items.append(
                ArbitrageOpportunity(
                    id=pair.id,
                    market_a=market_a_resp,
                    market_b=market_b_resp,
                    similarity_score=pair.similarity_score,
                    odds_delta=pair.odds_delta,
                    match_method=pair.match_method,
                )
            )

        next_cursor = str(rows[-1][0].id) if len(rows) == limit else None

        logger.info(
            "arbitrage_get_opportunities",
            total=total,
            returned=len(items),
            min_delta=min_delta,
            category=category,
        )

        return ArbitrageListResponse(
            items=items,
            next_cursor=next_cursor,
            total=total,
        )

    async def create_manual_pair(
        self, market_a_id: int, market_b_id: int,
    ) -> MatchedMarketPair:
        """Create a manual arbitrage pair from two market IDs.

        Validates both markets exist and are on different platforms.
        Computes odds_delta immediately. Enforces market_a_id < market_b_id.
        """
        # Normalize ordering for the check constraint
        lo, hi = sorted([market_a_id, market_b_id])

        # Check for existing pair
        existing = await self._db.execute(
            select(MatchedMarketPair).where(
                MatchedMarketPair.market_a_id == lo,
                MatchedMarketPair.market_b_id == hi,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise ValueError("This pair already exists")

        # Fetch both markets
        result_a = await self._db.execute(
            select(UnifiedMarket).where(UnifiedMarket.id == lo)
        )
        market_a = result_a.scalar_one_or_none()
        result_b = await self._db.execute(
            select(UnifiedMarket).where(UnifiedMarket.id == hi)
        )
        market_b = result_b.scalar_one_or_none()

        if market_a is None or market_b is None:
            raise ValueError("One or both markets not found")
        if market_a.platform_id == market_b.platform_id:
            raise ValueError("Markets must be on different platforms")

        # Get latest prices from snapshots
        snap_prices = await load_snap_map(self._db, [lo, hi])
        prices_a = snap_prices.get(lo, {}).get("outcome_prices", {})
        prices_b = snap_prices.get(hi, {}).get("outcome_prices", {})

        delta = self._compute_odds_delta(prices_a, prices_b)

        pair = MatchedMarketPair(
            market_a_id=lo,
            market_b_id=hi,
            similarity_score=1.0,
            odds_delta=delta,
            match_method="manual",
            category=market_a.category or market_b.category,
        )
        self._db.add(pair)
        await self._db.flush()

        logger.info(
            "manual_pair_created",
            pair_id=pair.id,
            market_a_id=lo,
            market_b_id=hi,
            odds_delta=delta,
        )
        return pair

    async def create_verified_pair(
        self,
        market_a_id: int,
        market_b_id: int,
        confidence: float,
        outcome_mapping: dict[str, str] | None = None,
        explanation: str | None = None,
    ) -> MatchedMarketPair:
        """Create an LLM-verified arbitrage pair.

        Uses outcome_mapping for correct delta calculation when outcome
        labels differ across platforms (e.g. Yes/No vs Above/Below).
        """
        lo, hi = sorted([market_a_id, market_b_id])

        existing = await self._db.execute(
            select(MatchedMarketPair).where(
                MatchedMarketPair.market_a_id == lo,
                MatchedMarketPair.market_b_id == hi,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise ValueError("This pair already exists")

        result_a = await self._db.execute(
            select(UnifiedMarket).where(UnifiedMarket.id == lo)
        )
        market_a = result_a.scalar_one_or_none()
        result_b = await self._db.execute(
            select(UnifiedMarket).where(UnifiedMarket.id == hi)
        )
        market_b = result_b.scalar_one_or_none()

        if market_a is None or market_b is None:
            raise ValueError("One or both markets not found")
        if market_a.platform_id == market_b.platform_id:
            raise ValueError("Markets must be on different platforms")

        # Get latest prices from snapshots
        snap_prices = await load_snap_map(self._db, [lo, hi])
        prices_a = snap_prices.get(lo, {}).get("outcome_prices", {})
        prices_b = snap_prices.get(hi, {}).get("outcome_prices", {})

        # Use outcome mapping for correct delta if provided
        if outcome_mapping:
            if market_a_id <= market_b_id:
                mapped_a, mapped_b = prices_a, prices_b
                mapping = outcome_mapping
            else:
                mapped_a, mapped_b = prices_b, prices_a
                mapping = {v: k for k, v in outcome_mapping.items()}
            delta = self._compute_mapped_delta(mapped_a, mapped_b, mapping)
        else:
            delta = self._compute_odds_delta(prices_a, prices_b)

        pair = MatchedMarketPair(
            market_a_id=lo,
            market_b_id=hi,
            similarity_score=confidence,
            odds_delta=delta,
            match_method="llm_verified",
            category=market_a.category or market_b.category,
        )
        self._db.add(pair)
        await self._db.flush()

        logger.info(
            "llm_verified_pair_created",
            pair_id=pair.id,
            market_a_id=lo,
            market_b_id=hi,
            confidence=confidence,
            odds_delta=delta,
            outcome_mapping=outcome_mapping,
            explanation=explanation,
        )
        return pair

    @staticmethod
    def _compute_mapped_delta(
        prices_a: dict, prices_b: dict, mapping: dict[str, str],
    ) -> float:
        """Compute odds delta using explicit outcome mapping."""
        max_delta = 0.0
        for outcome_a, outcome_b in mapping.items():
            try:
                price_a = float(prices_a.get(outcome_a, 0))
                price_b = float(prices_b.get(outcome_b, 0))
                max_delta = max(max_delta, abs(price_a - price_b))
            except (ValueError, TypeError):
                continue
        return max_delta

    async def update_deltas(self) -> int:
        result = await self._db.execute(
            select(MatchedMarketPair)
        )
        pairs = result.scalars().all()
        logger.info("arbitrage_update_deltas_started", total_pairs=len(pairs))

        # Bulk load all latest prices
        market_ids: set[int] = set()
        for pair in pairs:
            market_ids.add(pair.market_a_id)
            market_ids.add(pair.market_b_id)

        snap_prices = await load_snap_map(self._db, list(market_ids))

        updated_count = 0
        for pair in pairs:
            prices_a = snap_prices.get(pair.market_a_id, {}).get("outcome_prices", {})
            prices_b = snap_prices.get(pair.market_b_id, {}).get("outcome_prices", {})

            if not prices_a and not prices_b:
                logger.warning(
                    "arbitrage_missing_prices",
                    pair_id=pair.id,
                    market_a_id=pair.market_a_id,
                    market_b_id=pair.market_b_id,
                )
                continue

            delta = self._compute_odds_delta(prices_a, prices_b)
            pair.odds_delta = delta
            self._db.add(pair)
            updated_count += 1

        return updated_count

    @staticmethod
    def _compute_odds_delta(prices_a: dict, prices_b: dict) -> float:
        if not prices_a or not prices_b:
            return 0.0

        common_outcomes = set(prices_a.keys()) & set(prices_b.keys())
        if not common_outcomes:
            yes_keys_a = [k for k in prices_a if k.lower() in ("yes", "true", "1")]
            yes_keys_b = [k for k in prices_b if k.lower() in ("yes", "true", "1")]

            if yes_keys_a and yes_keys_b:
                price_a = float(prices_a[yes_keys_a[0]])
                price_b = float(prices_b[yes_keys_b[0]])
                return abs(price_a - price_b)
            return 0.0

        max_delta = 0.0
        for outcome in common_outcomes:
            try:
                price_a = float(prices_a[outcome])
                price_b = float(prices_b[outcome])
                delta = abs(price_a - price_b)
                max_delta = max(max_delta, delta)
            except (ValueError, TypeError):
                continue

        return max_delta

    @staticmethod
    def _row_to_market_response(
        market: UnifiedMarket, platform_name: str, platform_slug: str,
        snap: dict | None = None,
    ) -> MarketResponse:
        s = snap or {}
        return MarketResponse(
            id=market.id,
            platform_id=market.platform_id,
            platform_name=platform_name,
            platform_slug=platform_slug,
            platform_market_id=market.platform_market_id,
            question=market.question,
            description=market.description,
            category=market.category,
            outcomes=market.outcomes or {},
            start_date=market.start_date,
            end_date=market.end_date,
            status=market.status,
            resolution=market.resolution,
            deep_link_url=market.deep_link_url,
            image_url=market.image_url,
            created_at=market.created_at,
            updated_at=market.updated_at,
            # Pricing from snapshot
            outcome_prices=s.get("outcome_prices", {}),
            volume_total=s.get("volume_total"),
            volume_24h=s.get("volume_24h"),
            liquidity=s.get("liquidity"),
            yes_ask=s.get("yes_ask"),
            no_ask=s.get("no_ask"),
            price_change_24h=s.get("price_change_24h"),
            last_synced_at=s.get("last_synced_at"),
        )
