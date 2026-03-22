"""Background task for grouping markets and computing group analytics.

Phase 1: Seed groups from platform-native clusters (event_ticker).
Phase 2: Merge cross-platform groups via TF-IDF similarity + end_date gate.
Phase 3: Compute group analytics (consensus, disagreement, best-odds).

Two entry points:
- run_mini_grouping(): processes only ungrouped markets (every 10 min)
- run_full_grouping(): exhaustive cross-platform merge (every 2 hours)
"""
import structlog
from sqlalchemy import delete, desc, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import settings
from app.database import get_background_session_factory
from app.matching.scorer import _end_date_gate, score_pair
from app.matching.text import build_tfidf_matrix, get_candidates, preprocess
from app.models.market import UnifiedMarket
from app.models.market_group import MarketGroup, MarketGroupMember
from app.models.price_history import latest_snapshot_subquery

logger = structlog.get_logger()


async def _get_ungrouped_market_ids(db) -> set[int]:
    """Return IDs of active markets that have no group membership."""
    result = await db.execute(
        select(UnifiedMarket.id)
        .outerjoin(MarketGroupMember, MarketGroupMember.market_id == UnifiedMarket.id)
        .where(UnifiedMarket.is_active.is_(True))
        .where(MarketGroupMember.id.is_(None))
    )
    return {row[0] for row in result.all()}


async def _load_group_representatives(db, group_ids: list[int]) -> dict[int, dict]:
    """Load representative end_date and description for each group.

    rep_end_date: MIN(end_date) of all members (conservative).
    rep_description: description from the highest-liquidity member.
    """
    if not group_ids:
        return {}

    # Batch to avoid param limit
    reps: dict[int, dict] = {}
    batch_size = 5000
    for i in range(0, len(group_ids), batch_size):
        batch_ids = group_ids[i:i + batch_size]

        # Get min end_date per group
        end_date_result = await db.execute(
            select(
                MarketGroupMember.group_id,
                func.min(UnifiedMarket.end_date),
            )
            .join(UnifiedMarket, UnifiedMarket.id == MarketGroupMember.market_id)
            .where(MarketGroupMember.group_id.in_(batch_ids))
            .group_by(MarketGroupMember.group_id)
        )
        for gid, end_date in end_date_result.all():
            reps.setdefault(gid, {})["end_date"] = end_date

        # Get description from highest-liquidity member per group
        # Use DISTINCT ON (group_id) ordered by snapshot liquidity DESC
        snap = latest_snapshot_subquery("rep_snap")
        desc_result = await db.execute(
            select(
                MarketGroupMember.group_id,
                UnifiedMarket.description,
            )
            .join(UnifiedMarket, UnifiedMarket.id == MarketGroupMember.market_id)
            .outerjoin(snap, snap.c.market_id == UnifiedMarket.id)
            .where(MarketGroupMember.group_id.in_(batch_ids))
            .order_by(
                MarketGroupMember.group_id,
                desc(snap.c.liquidity).nulls_last(),
            )
            .distinct(MarketGroupMember.group_id)
        )
        for gid, description in desc_result.all():
            reps.setdefault(gid, {})["description"] = description

    return reps


async def _phase1_seed_groups(db, market_ids: set[int] | None = None) -> int:
    """Seed groups from markets with event_ticker.

    Markets sharing the same event_ticker belong to the same group.
    Uses bulk operations to avoid O(n) individual queries.

    When market_ids is provided, only those markets are considered.
    """
    # 1. Load existing groups into a lookup
    existing_result = await db.execute(
        select(MarketGroup.id, MarketGroup.source_event_ticker)
        .where(MarketGroup.source_event_ticker.isnot(None))
    )
    existing_groups: dict[str, int] = {
        row[1]: row[0] for row in existing_result.all()
    }

    # 2. Get markets with event_tickers
    query = (
        select(UnifiedMarket.id, UnifiedMarket.event_ticker, UnifiedMarket.question, UnifiedMarket.category)
        .where(UnifiedMarket.is_active.is_(True))
        .where(UnifiedMarket.event_ticker.isnot(None))
        .where(UnifiedMarket.event_ticker != "")
    )
    if market_ids is not None:
        query = query.where(UnifiedMarket.id.in_(market_ids))

    result = await db.execute(query)
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


async def _phase2_assign_to_existing_groups(db, market_ids: set[int]) -> int:
    """Mini merge: try to slot newly-seeded groups into existing cross-platform groups.

    Only compares groups containing the given market_ids against all other groups.
    This is O(new x existing) instead of O(all^2).
    """
    threshold = settings.GROUP_MERGE_THRESHOLD

    # Find group IDs that contain any of the new market_ids
    new_group_result = await db.execute(
        select(MarketGroupMember.group_id)
        .where(MarketGroupMember.market_id.in_(market_ids))
        .distinct()
    )
    new_group_ids = {row[0] for row in new_group_result.all()}
    if not new_group_ids:
        return 0

    # Load all active groups
    all_groups_result = await db.execute(
        select(MarketGroup.id, MarketGroup.canonical_question, MarketGroup.category)
        .where(MarketGroup.is_active.is_(True))
    )
    all_groups = all_groups_result.all()

    new_groups = [g for g in all_groups if g.id in new_group_ids]
    existing_groups = [g for g in all_groups if g.id not in new_group_ids]

    if not new_groups or not existing_groups:
        return 0

    # Load representative end_date and description for all groups
    all_group_ids = [g.id for g in new_groups] + [g.id for g in existing_groups]
    reps = await _load_group_representatives(db, all_group_ids)

    # Bulk load group->platform mapping
    platform_result = await db.execute(
        select(
            MarketGroupMember.group_id,
            UnifiedMarket.platform_id,
        )
        .join(UnifiedMarket, UnifiedMarket.id == MarketGroupMember.market_id)
        .where(MarketGroupMember.group_id.in_(all_group_ids))
        .distinct(MarketGroupMember.group_id)
    )
    group_platform: dict[int, int] = {row[0]: row[1] for row in platform_result.all()}

    # Build TF-IDF: new groups first, then existing groups
    all_questions = (
        [g.canonical_question for g in new_groups]
        + [g.canonical_question for g in existing_groups]
    )
    preprocessed = [preprocess(q) for q in all_questions]
    tfidf_matrix, _ = build_tfidf_matrix(preprocessed)

    # Build description TF-IDF matrix
    all_descs = []
    for g in list(new_groups) + list(existing_groups):
        rep = reps.get(g.id, {})
        desc_text = rep.get("description") or ""
        all_descs.append(preprocess(desc_text) if desc_text else "")

    has_descs = any(d for d in all_descs)
    desc_tfidf_matrix = None
    if has_descs:
        desc_tfidf_matrix, _ = build_tfidf_matrix(all_descs)

    len_new = len(new_groups)
    merges = 0
    merged_ids: set[int] = set()

    for i, g_new in enumerate(new_groups):
        if g_new.id in merged_ids:
            continue

        new_pid = group_platform.get(g_new.id)
        new_rep = reps.get(g_new.id, {})
        new_end = new_rep.get("end_date")
        new_desc = new_rep.get("description")

        # Use low threshold for TF-IDF candidates, final score_pair does real filtering
        candidates = get_candidates(tfidf_matrix[i], tfidf_matrix, threshold=0.30)

        best_match: tuple[int, float, float] | None = None  # (idx, composite, tfidf)
        for j, tfidf_score in candidates:
            if j < len_new:
                continue  # Skip other new groups
            g_existing = existing_groups[j - len_new]
            if g_existing.id in merged_ids:
                continue
            existing_pid = group_platform.get(g_existing.id)
            if new_pid is not None and existing_pid is not None and new_pid == existing_pid:
                continue  # Same platform, skip

            ex_rep = reps.get(g_existing.id, {})
            ex_end = ex_rep.get("end_date")

            # Apply hard gate before expensive scoring
            if not _end_date_gate(new_end, ex_end):
                continue

            ex_desc = ex_rep.get("description")

            # Compute description TF-IDF score if available
            desc_tfidf_score = None
            if desc_tfidf_matrix is not None:
                from sklearn.metrics.pairwise import cosine_similarity
                desc_sim = cosine_similarity(
                    desc_tfidf_matrix[i], desc_tfidf_matrix[j]
                ).flatten()[0]
                desc_tfidf_score = float(desc_sim)

            composite = score_pair(
                q1=g_new.canonical_question,
                q2=g_existing.canonical_question,
                cat1=g_new.category,
                cat2=g_existing.category,
                end1=new_end,
                end2=ex_end,
                desc1=new_desc,
                desc2=ex_desc,
                tfidf_score=tfidf_score,
                desc_tfidf_score=desc_tfidf_score,
            )

            if composite >= threshold:
                if best_match is None or composite > best_match[1]:
                    best_match = (j - len_new, composite, tfidf_score)

        if best_match is None:
            continue

        idx_existing, composite, _ = best_match
        g_existing = existing_groups[idx_existing]

        # Merge: move members from new group -> existing group
        members_new = await db.execute(
            select(MarketGroupMember.market_id).where(
                MarketGroupMember.group_id == g_new.id
            )
        )
        member_ids = [r[0] for r in members_new.all()]
        if member_ids:
            vals = [{"group_id": g_existing.id, "market_id": mid} for mid in member_ids]
            await db.execute(
                pg_insert(MarketGroupMember).values(vals).on_conflict_do_nothing(
                    constraint="uq_group_market"
                )
            )

        await db.execute(
            delete(MarketGroupMember).where(MarketGroupMember.group_id == g_new.id)
        )
        merged_group = await db.get(MarketGroup, g_new.id)
        if merged_group:
            merged_group.is_active = False

        # Persist match_confidence on the target group
        target_group = await db.get(MarketGroup, g_existing.id)
        if target_group:
            target_group.match_confidence = round(composite, 4)

        merged_ids.add(g_new.id)
        merges += 1

        logger.info(
            "mini_merge_matched",
            new_group_id=g_new.id,
            existing_group_id=g_existing.id,
            score=round(composite, 4),
        )

    return merges


async def _phase2_merge_cross_platform(db) -> int:
    """Merge groups across platforms using TF-IDF similarity + end_date gate.

    Only compares groups from different platforms. Uses bulk platform lookup
    instead of per-group queries.
    """
    threshold = settings.GROUP_MERGE_THRESHOLD

    # Bulk load group->platform mapping via a single query
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
        select(MarketGroup.id, MarketGroup.canonical_question, MarketGroup.category)
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

    # Load representative end_date and description for all groups
    all_group_ids = [g.id for g in all_groups]
    reps = await _load_group_representatives(db, all_group_ids)

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

            # Build description TF-IDF matrix
            combined_groups = list(groups_a) + list(groups_b)
            all_descs = []
            for g in combined_groups:
                rep = reps.get(g.id, {})
                desc_text = rep.get("description") or ""
                all_descs.append(preprocess(desc_text) if desc_text else "")

            has_descs = any(d for d in all_descs)
            desc_tfidf_matrix = None
            if has_descs:
                desc_tfidf_matrix, _ = build_tfidf_matrix(all_descs)

            len_a = len(groups_a)

            for i, g_a in enumerate(groups_a):
                if g_a.id in merged_ids:
                    continue

                a_rep = reps.get(g_a.id, {})
                a_end = a_rep.get("end_date")
                a_desc = a_rep.get("description")

                candidates = get_candidates(tfidf_matrix[i], tfidf_matrix, threshold=0.30)

                best_match: tuple[int, float] | None = None
                for j, tfidf_score in candidates:
                    if j < len_a:
                        continue  # Same platform
                    g_b = groups_b[j - len_a]
                    if g_b.id in merged_ids:
                        continue

                    b_rep = reps.get(g_b.id, {})
                    b_end = b_rep.get("end_date")

                    # Apply hard gate before scoring
                    if not _end_date_gate(a_end, b_end):
                        continue

                    b_desc = b_rep.get("description")

                    # Compute description TF-IDF score if available
                    desc_tfidf_score = None
                    if desc_tfidf_matrix is not None:
                        from sklearn.metrics.pairwise import cosine_similarity
                        desc_sim = cosine_similarity(
                            desc_tfidf_matrix[i], desc_tfidf_matrix[j]
                        ).flatten()[0]
                        desc_tfidf_score = float(desc_sim)

                    composite = score_pair(
                        q1=g_a.canonical_question,
                        q2=g_b.canonical_question,
                        cat1=g_a.category,
                        cat2=g_b.category,
                        end1=a_end,
                        end2=b_end,
                        desc1=a_desc,
                        desc2=b_desc,
                        tfidf_score=tfidf_score,
                        desc_tfidf_score=desc_tfidf_score,
                    )

                    if composite >= threshold:
                        if best_match is None or composite > best_match[1]:
                            best_match = (j - len_a, composite)

                if best_match is None:
                    continue

                idx_b, composite = best_match
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

                # Persist match_confidence on the target group
                target_group = await db.get(MarketGroup, g_a.id)
                if target_group:
                    target_group.match_confidence = round(composite, 4)

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

    # Bulk load all members with their market data + latest snapshot
    group_ids = [g.id for g in groups]
    group_members: dict[int, list[tuple]] = {}  # gid -> [(market, snap_data), ...]
    batch_size = 5000

    snap = latest_snapshot_subquery("analytics_snap")

    for i in range(0, len(group_ids), batch_size):
        batch_ids = group_ids[i:i + batch_size]
        batch_result = await db.execute(
            select(
                MarketGroupMember.group_id,
                UnifiedMarket,
                snap.c.outcome_prices.label("snap_outcome_prices"),
                snap.c.liquidity.label("snap_liquidity"),
                snap.c.volume_24h.label("snap_volume_24h"),
                snap.c.yes_ask.label("snap_yes_ask"),
                snap.c.no_ask.label("snap_no_ask"),
            )
            .join(UnifiedMarket, UnifiedMarket.id == MarketGroupMember.market_id)
            .outerjoin(snap, snap.c.market_id == UnifiedMarket.id)
            .where(MarketGroupMember.group_id.in_(batch_ids))
        )
        for row in batch_result.all():
            gid = row[0]
            market = row[1]
            snap_data = {
                "outcome_prices": row.snap_outcome_prices or {},
                "liquidity": row.snap_liquidity,
                "volume_24h": row.snap_volume_24h,
                "yes_ask": row.snap_yes_ask,
                "no_ask": row.snap_no_ask,
            }
            group_members.setdefault(gid, []).append((market, snap_data))

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

        for m, snap_data in members:
            prices = snap_data.get("outcome_prices", {})
            liq = snap_data.get("liquidity") or 0.0
            total_vol += snap_data.get("volume_24h") or 0.0
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
            yes_ask = snap_data.get("yes_ask")
            if yes_ask is None:
                yes_ask = float(yes_p) if yes_p is not None else None
            if yes_ask is not None and yes_ask < best_yes_price:
                best_yes_price = yes_ask
                best_yes_id = m.id

            no_ask = snap_data.get("no_ask")
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

        # Propagate majority member category to groups with NULL category
        if not group.category:
            member_cats = [m.category for m, _ in members if m.category]
            if member_cats:
                from collections import Counter
                group.category = Counter(member_cats).most_common(1)[0][0]

        db.add(group)
        updated += 1

    return updated


async def run_mini_grouping() -> None:
    """Mini-grouping: process only ungrouped markets, then refresh analytics."""
    logger.info("run_mini_grouping_started")

    async with get_background_session_factory()() as db:
        try:
            ungrouped = await _get_ungrouped_market_ids(db)

            if not ungrouped:
                logger.info("run_mini_grouping_no_ungrouped")
                updated = await _phase3_compute_analytics(db)
                await db.commit()
                logger.info("run_mini_grouping_complete", ungrouped=0, created=0, merged=0, analytics_updated=updated)
                return

            logger.info("run_mini_grouping_found_ungrouped", count=len(ungrouped))

            created = await _phase1_seed_groups(db, market_ids=ungrouped)
            await db.commit()
            logger.info("mini_group_phase1_complete", groups_created=created)

            merged = await _phase2_assign_to_existing_groups(db, ungrouped)
            await db.commit()
            logger.info("mini_group_phase2_complete", merges=merged)

            updated = await _phase3_compute_analytics(db)
            await db.commit()

            logger.info(
                "run_mini_grouping_complete",
                ungrouped=len(ungrouped),
                created=created,
                merged=merged,
                analytics_updated=updated,
            )
        except Exception as exc:
            await db.rollback()
            logger.error("run_mini_grouping_failed", error=str(exc), exc_info=True)


async def run_full_grouping() -> None:
    """Full regrouping: exhaustive cross-platform merge across all groups."""
    logger.info("run_full_grouping_started")

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
                "run_full_grouping_complete",
                created=created,
                merged=merged,
                analytics_updated=updated,
            )
        except Exception as exc:
            await db.rollback()
            logger.error("run_full_grouping_failed", error=str(exc), exc_info=True)
