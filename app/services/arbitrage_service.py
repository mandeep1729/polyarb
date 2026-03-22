import structlog
from sqlalchemy import Float, and_, cast, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.market import UnifiedMarket
from app.models.matched_market import MatchedMarketPair
from app.models.platform import Platform
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

        stmt = (
            select(
                MatchedMarketPair,
                MarketA,
                MarketB,
                PlatformA.name.label("platform_a_name"),
                PlatformA.slug.label("platform_a_slug"),
                PlatformB.name.label("platform_b_name"),
                PlatformB.slug.label("platform_b_slug"),
            )
            .join(MarketA, MarketA.id == MatchedMarketPair.market_a_id)
            .join(MarketB, MarketB.id == MatchedMarketPair.market_b_id)
            .join(PlatformA, PlatformA.id == MarketA.platform_id)
            .join(PlatformB, PlatformB.id == MarketB.platform_id)
        )

        filters = []
        if min_delta > 0:
            filters.append(func.abs(func.coalesce(MatchedMarketPair.odds_delta, 0)) >= min_delta)
        if category:
            filters.append(MatchedMarketPair.category == category)
        if hide_onesided:
            jt_a = func.jsonb_each_text(MarketA.outcome_prices).table_valued("key", "value")
            max_price_a = (
                select(func.coalesce(func.max(cast(jt_a.c.value, Float)), 0.0))
                .correlate(MarketA)
                .scalar_subquery()
            )
            jt_b = func.jsonb_each_text(MarketB.outcome_prices).table_valued("key", "value")
            max_price_b = (
                select(func.coalesce(func.max(cast(jt_b.c.value, Float)), 0.0))
                .correlate(MarketB)
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

            market_a_resp = self._row_to_market_response(ma, pa_name, pa_slug)
            market_b_resp = self._row_to_market_response(mb, pb_name, pb_slug)

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

        delta = self._compute_odds_delta(
            market_a.outcome_prices or {},
            market_b.outcome_prices or {},
        )

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

        prices_a = market_a.outcome_prices or {}
        prices_b = market_b.outcome_prices or {}

        # Use outcome mapping for correct delta if provided
        if outcome_mapping:
            # Determine which market's IDs were used as keys in the mapping
            # mapping is {market_a_outcome: market_b_outcome}
            # Need to figure out if lo == market_a_id from the original input
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

        updated_count = 0
        for pair in pairs:
            market_a_result = await self._db.execute(
                select(UnifiedMarket).where(UnifiedMarket.id == pair.market_a_id)
            )
            market_a = market_a_result.scalar_one_or_none()

            market_b_result = await self._db.execute(
                select(UnifiedMarket).where(UnifiedMarket.id == pair.market_b_id)
            )
            market_b = market_b_result.scalar_one_or_none()

            if market_a is None or market_b is None:
                logger.warning(
                    "arbitrage_missing_market",
                    pair_id=pair.id,
                    market_a_id=pair.market_a_id,
                    market_b_id=pair.market_b_id,
                    market_a_missing=market_a is None,
                    market_b_missing=market_b is None,
                )
                continue

            delta = self._compute_odds_delta(
                market_a.outcome_prices, market_b.outcome_prices
            )
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
    def _row_to_market_response(market: UnifiedMarket, platform_name: str, platform_slug: str) -> MarketResponse:
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
            outcome_prices=market.outcome_prices or {},
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
