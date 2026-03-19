"""Background task for grouping markets and computing group analytics.

Phase 1: Seed groups from platform-native clusters (event_ticker).
Phase 2: Merge cross-platform groups via TF-IDF similarity.
Phase 3: Compute group analytics (consensus, disagreement, best-odds).
"""
from datetime import datetime, timezone

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import settings
from app.database import get_background_session_factory
from app.matching.text import build_tfidf_matrix, get_candidates, preprocess
from app.models.group_snapshot import GroupPriceSnapshot
from app.models.market import UnifiedMarket
from app.models.market_group import MarketGroup, MarketGroupMember
from app.models.platform import Platform

logger = structlog.get_logger()


async def _phase1_seed_groups(db) -> int:
    """Seed groups from markets with event_ticker.

    Markets sharing the same event_ticker belong to the same group.
    Uses bulk operations to avoid O(n) individual queries.
    """
    # 1. Load existing groups into a lookup
    existing_result = await db.execute(
        select(MarketGroup.id, MarketGroup.source_event_ticker)
        .where(MarketGroup.source_event_ticker.isnot(None))
    )
    existing_groups: dict[str, int] = {
        row[1]: row[0] for row in existing_result.all()
    }

    # 2. Get all markets with event_tickers
    result = await db.execute(
        select(UnifiedMarket.id, UnifiedMarket.event_ticker, UnifiedMarket.question, UnifiedMarket.category)
        .where(UnifiedMarket.is_active.is_(True))
        .where(UnifiedMarket.event_ticker.isnot(None))
        .where(UnifiedMarket.event_ticker != "")
    )
    markets = result.all()

    # 3. Group markets by event_ticker
    ticker_markets: dict[str, list[tuple]] = {}
    for mid, et, question, category in markets:
        ticker_markets.setdefault(et, []).append((mid, question, category))

    # 4. Create missing groups in bulk
    groups_created = 0
    for et, members in ticker_markets.items():
        if et not in existing_groups:
            question = members[0][1] or ""
            category = members[0][2]
            group = MarketGroup(
                canonical_question=question,
                category=category,
                source_event_ticker=et,
            )
            db.add(group)
            groups_created += 1

    if groups_created > 0:
        await db.flush()
        # Reload to get new IDs
        new_result = await db.execute(
            select(MarketGroup.id, MarketGroup.source_event_ticker)
            .where(MarketGroup.source_event_ticker.isnot(None))
        )
        existing_groups = {row[1]: row[0] for row in new_result.all()}

    # 5. Bulk insert members
    member_values = []
    for et, members in ticker_markets.items():
        group_id = existing_groups.get(et)
        if group_id is None:
            continue
        for mid, _, _ in members:
            member_values.append({"group_id": group_id, "market_id": mid})

    if member_values:
        # Batch in chunks of 1000
        for i in range(0, len(member_values), 1000):
            chunk = member_values[i:i + 1000]
            stmt = pg_insert(MarketGroupMember).values(chunk).on_conflict_do_nothing(
                constraint="uq_group_market"
            )
            await db.execute(stmt)

    return groups_created


async def _phase2_merge_cross_platform(db) -> int:
    """Merge groups across platforms using TF-IDF similarity on canonical questions.

    Only compares groups from different platforms. Uses bulk platform lookup
    instead of per-group queries.
    """
    threshold = settings.GROUP_MERGE_THRESHOLD

    # Bulk load group→platform mapping via a single query
    result = await db.execute(
        select(
            MarketGroupMember.group_id,
            UnifiedMarket.platform_id,
        )
        .join(UnifiedMarket, UnifiedMarket.id == MarketGroupMember.market_id)
        .distinct(MarketGroupMember.group_id)
    )
    group_platform: dict[int, int] = {row[0]: row[1] for row in result.all()}

    # Separate groups by platform
    platform_groups: dict[int, list] = {}
    all_groups_result = await db.execute(
        select(MarketGroup.id, MarketGroup.canonical_question)
        .where(MarketGroup.is_active.is_(True))
    )
    all_groups = all_groups_result.all()

    for g in all_groups:
        pid = group_platform.get(g.id)
        if pid is not None:
            platform_groups.setdefault(pid, []).append(g)

    pids = sorted(platform_groups.keys())
    if len(pids) < 2:
        return 0

    merges = 0
    merged_ids: set[int] = set()

    # Compare each pair of platforms
    for pi in range(len(pids)):
        for pj in range(pi + 1, len(pids)):
            groups_a = platform_groups[pids[pi]]
            groups_b = platform_groups[pids[pj]]

            if not groups_a or not groups_b:
                continue

            # Build TF-IDF only for these two platforms' groups
            all_questions = [g.canonical_question for g in groups_a] + [g.canonical_question for g in groups_b]
            preprocessed = [preprocess(q) for q in all_questions]
            tfidf_matrix, _ = build_tfidf_matrix(preprocessed)

            len_a = len(groups_a)

            for i, g_a in enumerate(groups_a):
                if g_a.id in merged_ids:
                    continue

                candidates = get_candidates(tfidf_matrix[i], tfidf_matrix, threshold=threshold)

                best_match: tuple[int, float] | None = None
                for j, score in candidates:
                    if j < len_a:
                        continue  # Same platform
                    g_b = groups_b[j - len_a]
                    if g_b.id in merged_ids:
                        continue
                    if best_match is None or score > best_match[1]:
                        best_match = (j - len_a, score)

                if best_match is None:
                    continue

                idx_b, score = best_match
                g_b = groups_b[idx_b]

                # Merge: move members from g_b into g_a
                members_b = await db.execute(
                    select(MarketGroupMember.market_id).where(
                        MarketGroupMember.group_id == g_b.id
                    )
                )
                member_ids = [r[0] for r in members_b.all()]
                if member_ids:
                    vals = [{"group_id": g_a.id, "market_id": mid} for mid in member_ids]
                    await db.execute(
                        pg_insert(MarketGroupMember).values(vals).on_conflict_do_nothing(
                            constraint="uq_group_market"
                        )
                    )

                await db.execute(
                    delete(MarketGroupMember).where(MarketGroupMember.group_id == g_b.id)
                )
                merged_group = await db.get(MarketGroup, g_b.id)
                if merged_group:
                    merged_group.is_active = False

                merged_ids.add(g_b.id)
                merges += 1

            logger.info(
                "group_phase2_platform_pair",
                platform_a=pids[pi],
                platform_b=pids[pj],
                groups_a=len(groups_a),
                groups_b=len(groups_b),
                merges_so_far=merges,
            )

    return merges


async def _phase3_compute_analytics(db) -> int:
    """Compute consensus, disagreement, and best-odds for all active groups."""
    result = await db.execute(
        select(MarketGroup).where(MarketGroup.is_active.is_(True))
    )
    groups = result.scalars().all()

    # Bulk load all members with their market data (batched to avoid param limit)
    group_ids = [g.id for g in groups]
    group_members: dict[int, list] = {}
    batch_size = 5000
    for i in range(0, len(group_ids), batch_size):
        batch_ids = group_ids[i:i + batch_size]
        batch_result = await db.execute(
            select(MarketGroupMember.group_id, UnifiedMarket)
            .join(UnifiedMarket, UnifiedMarket.id == MarketGroupMember.market_id)
            .where(MarketGroupMember.group_id.in_(batch_ids))
        )
        for gid, market in batch_result.all():
            group_members.setdefault(gid, []).append(market)

    updated = 0
    for group in groups:
        members = group_members.get(group.id, [])

        group.member_count = len(members)
        if not members:
            continue

        # Consensus: liquidity-weighted average, exclude zero-liquidity
        total_weight = 0.0
        weighted_yes = 0.0
        weighted_no = 0.0
        yes_prices: list[tuple[float, int]] = []  # (price, market_id)
        no_prices: list[tuple[float, int]] = []
        total_vol = 0.0
        total_liq = 0.0

        best_yes_price = float("inf")
        best_yes_id: int | None = None
        best_no_price = float("inf")
        best_no_id: int | None = None

        for m in members:
            prices = m.outcome_prices or {}
            liq = m.liquidity or 0.0
            total_vol += m.volume_24h or 0.0
            total_liq += liq

            yes_p = prices.get("Yes")
            no_p = prices.get("No")

            if yes_p is not None and liq > 0:
                weighted_yes += float(yes_p) * liq
                total_weight += liq
                yes_prices.append((float(yes_p), m.id))

            if no_p is not None and liq > 0:
                weighted_no += float(no_p) * liq
                no_prices.append((float(no_p), m.id))

            # Best odds: lowest ask prices
            yes_ask = m.yes_ask
            if yes_ask is None:
                yes_ask = float(yes_p) if yes_p is not None else None
            if yes_ask is not None and yes_ask < best_yes_price:
                best_yes_price = yes_ask
                best_yes_id = m.id

            no_ask = m.no_ask
            if no_ask is None:
                no_ask = float(no_p) if no_p is not None else None
            if no_ask is not None and no_ask < best_no_price:
                best_no_price = no_ask
                best_no_id = m.id

        # Set consensus
        if total_weight > 0:
            group.consensus_yes = round(weighted_yes / total_weight, 4)
            group.consensus_no = round(weighted_no / total_weight, 4)
        else:
            group.consensus_yes = None
            group.consensus_no = None

        # Disagreement: max spread among Yes prices
        if len(yes_prices) >= 2:
            prices_only = [p for p, _ in yes_prices]
            group.disagreement_score = round(max(prices_only) - min(prices_only), 4)
        else:
            group.disagreement_score = None

        group.best_yes_market_id = best_yes_id
        group.best_no_market_id = best_no_id
        group.total_volume = round(total_vol, 2)
        group.total_liquidity = round(total_liq, 2)

        # Create materialized snapshot
        snapshot = GroupPriceSnapshot(
            group_id=group.id,
            consensus_yes=group.consensus_yes,
            consensus_no=group.consensus_no,
            disagreement_score=group.disagreement_score,
            total_volume=group.total_volume,
        )
        db.add(snapshot)

        db.add(group)
        updated += 1

    return updated


async def run_grouping() -> None:
    """Main entry point for the grouping background task."""
    logger.info("run_grouping_started")

    async with get_background_session_factory()() as db:
        try:
            created = await _phase1_seed_groups(db)
            await db.commit()
            logger.info("group_phase1_complete", groups_created=created)

            merged = await _phase2_merge_cross_platform(db)
            await db.commit()
            logger.info("group_phase2_complete", merges=merged)

            updated = await _phase3_compute_analytics(db)
            await db.commit()
            logger.info("group_phase3_complete", groups_updated=updated)

            logger.info(
                "run_grouping_complete",
                created=created,
                merged=merged,
                analytics_updated=updated,
            )
        except Exception as exc:
            await db.rollback()
            logger.error("run_grouping_failed", error=str(exc), exc_info=True)
