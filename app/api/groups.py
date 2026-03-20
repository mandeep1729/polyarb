"""API endpoints for market groups."""
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.matching.scorer import _end_date_gate, score_pair
from app.matching.text import build_tfidf_matrix, get_candidates, preprocess
from app.models.market import UnifiedMarket
from app.models.market_group import MarketGroup, MarketGroupMember
from app.schemas.group import (
    GroupDetailResponse,
    GroupListResponse,
    GroupSnapshotResponse,
    TagResponse,
)
from app.services.group_service import GroupService
from app.tasks.group_markets import _load_group_representatives, run_full_grouping

router = APIRouter(prefix="/groups", tags=["groups"])


@router.get("", response_model=GroupListResponse)
async def list_groups(
    category: str | None = None,
    sort_by: str = Query(default="liquidity", pattern="^(disagreement|volume|liquidity|consensus|created_at)$"),
    end_date_min: str | None = Query(None, description="Groups with members expiring on or after this date (YYYY-MM-DD)"),
    end_date_max: str | None = Query(None, description="Groups with members expiring on or before this date (YYYY-MM-DD)"),
    exclude_expired: bool = Query(True, description="Hide groups whose members have all expired"),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    db: AsyncSession = Depends(get_session),
) -> GroupListResponse:
    """List active market groups with pagination."""
    service = GroupService(db)
    return await service.get_groups(
        category=category, sort_by=sort_by, end_date_min=end_date_min, end_date_max=end_date_max,
        exclude_expired=exclude_expired, limit=limit, cursor=cursor,
    )


@router.get("/search", response_model=GroupListResponse)
async def search_groups(
    q: str = Query(..., min_length=2, max_length=200),
    category: str | None = None,
    sort_by: str = Query(default="liquidity", pattern="^(disagreement|volume|liquidity|consensus|created_at)$"),
    end_date_min: str | None = Query(None, description="Groups with members expiring on or after this date (YYYY-MM-DD)"),
    end_date_max: str | None = Query(None, description="Groups with members expiring on or before this date (YYYY-MM-DD)"),
    exclude_expired: bool = Query(True, description="Hide groups whose members have all expired"),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_session),
) -> GroupListResponse:
    """Search groups by canonical question text."""
    service = GroupService(db)
    return await service.search_groups(
        query=q, category=category, sort_by=sort_by, end_date_min=end_date_min, end_date_max=end_date_max,
        exclude_expired=exclude_expired, limit=limit,
    )


@router.get("/categories")
async def group_category_counts(
    db: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Return category counts for active groups."""
    service = GroupService(db)
    return await service.get_category_counts()


_regroup_running = False


@router.post("/regroup")
async def trigger_regroup() -> dict:
    """Trigger a full regrouping in the background."""
    global _regroup_running
    if _regroup_running:
        raise HTTPException(status_code=409, detail="Regrouping already in progress")

    async def _run() -> None:
        global _regroup_running
        try:
            await run_full_grouping()
        finally:
            _regroup_running = False

    _regroup_running = True
    asyncio.create_task(_run())
    return {"status": "started"}


@router.get("/status")
async def grouping_status(
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Return grouping statistics: last run time, active group count, total markets grouped."""
    result = await db.execute(
        select(
            func.count(MarketGroup.id),
            func.max(MarketGroup.updated_at),
        ).where(MarketGroup.is_active.is_(True))
    )
    row = result.one()
    group_count = row[0]
    last_updated = row[1]

    member_result = await db.execute(
        select(func.count(MarketGroupMember.id))
        .join(MarketGroup, MarketGroup.id == MarketGroupMember.group_id)
        .where(MarketGroup.is_active.is_(True))
    )
    member_count = member_result.scalar() or 0

    return {
        "active_groups": group_count,
        "total_markets_grouped": member_count,
        "last_run": last_updated.isoformat() if last_updated else None,
    }


@router.get("/audit-equivalence")
async def audit_equivalence(
    limit: int = Query(default=50, ge=1, le=500, description="Max groups per platform pair to analyze for would_merge"),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Dry-run: preview what the current equivalence rules would change.

    Returns:
        would_split: existing multi-platform groups where members fail the end_date gate.
        would_merge: pairs of currently-separate groups that would pass gate + threshold.
    """
    threshold = settings.GROUP_MERGE_THRESHOLD

    # --- would_split: check existing groups for members that fail end_date gate ---
    would_split: list[dict] = []
    active_result = await db.execute(
        select(MarketGroup.id, MarketGroup.canonical_question)
        .where(MarketGroup.is_active.is_(True))
    )
    active_groups = active_result.all()

    # Load member end_dates for each group
    group_ids = [g.id for g in active_groups]
    if group_ids:
        member_dates: dict[int, list] = {}
        for i in range(0, len(group_ids), 5000):
            batch = group_ids[i:i + 5000]
            result = await db.execute(
                select(
                    MarketGroupMember.group_id,
                    UnifiedMarket.id,
                    UnifiedMarket.end_date,
                    UnifiedMarket.platform_id,
                )
                .join(UnifiedMarket, UnifiedMarket.id == MarketGroupMember.market_id)
                .where(MarketGroupMember.group_id.in_(batch))
            )
            for gid, mid, end_date, pid in result.all():
                member_dates.setdefault(gid, []).append({
                    "market_id": mid,
                    "end_date": end_date.isoformat() if end_date else None,
                    "platform_id": pid,
                })

        for g in active_groups:
            members = member_dates.get(g.id, [])
            if len(members) < 2:
                continue
            # Check if any pair of members fails the gate
            platforms = {m["platform_id"] for m in members}
            if len(platforms) < 2:
                continue  # Single-platform group, skip
            failing_pairs = []
            for a_idx in range(len(members)):
                for b_idx in range(a_idx + 1, len(members)):
                    a = members[a_idx]
                    b = members[b_idx]
                    if a["platform_id"] == b["platform_id"]:
                        continue
                    from datetime import datetime
                    a_end = datetime.fromisoformat(a["end_date"]) if a["end_date"] else None
                    b_end = datetime.fromisoformat(b["end_date"]) if b["end_date"] else None
                    if not _end_date_gate(a_end, b_end):
                        failing_pairs.append({
                            "market_a": a["market_id"],
                            "market_b": b["market_id"],
                            "end_date_a": a["end_date"],
                            "end_date_b": b["end_date"],
                        })
            if failing_pairs:
                would_split.append({
                    "group_id": g.id,
                    "canonical_question": g.canonical_question,
                    "failing_pairs": failing_pairs,
                })

    # --- would_merge: check separate groups that would now pass ---
    would_merge: list[dict] = []

    # Load group→platform mapping
    platform_result = await db.execute(
        select(
            MarketGroupMember.group_id,
            UnifiedMarket.platform_id,
        )
        .join(UnifiedMarket, UnifiedMarket.id == MarketGroupMember.market_id)
        .distinct(MarketGroupMember.group_id)
    )
    group_platform: dict[int, int] = {row[0]: row[1] for row in platform_result.all()}

    # Separate by platform
    platform_groups: dict[int, list] = {}
    for g in active_groups:
        pid = group_platform.get(g.id)
        if pid is not None:
            platform_groups.setdefault(pid, []).append(g)

    pids = sorted(platform_groups.keys())
    if len(pids) >= 2:
        reps = await _load_group_representatives(db, group_ids)

        for pi in range(len(pids)):
            for pj in range(pi + 1, len(pids)):
                groups_a = platform_groups[pids[pi]][:limit]
                groups_b = platform_groups[pids[pj]][:limit]
                if not groups_a or not groups_b:
                    continue

                all_questions = [g.canonical_question for g in groups_a] + [g.canonical_question for g in groups_b]
                preprocessed_qs = [preprocess(q) for q in all_questions]
                tfidf_matrix, _ = build_tfidf_matrix(preprocessed_qs)
                len_a = len(groups_a)

                for i, g_a in enumerate(groups_a):
                    a_rep = reps.get(g_a.id, {})
                    candidates = get_candidates(tfidf_matrix[i], tfidf_matrix, threshold=0.30)
                    for j, tfidf_score in candidates:
                        if j < len_a:
                            continue
                        g_b = groups_b[j - len_a]
                        b_rep = reps.get(g_b.id, {})

                        a_end = a_rep.get("end_date")
                        b_end = b_rep.get("end_date")
                        if not _end_date_gate(a_end, b_end):
                            continue

                        composite = score_pair(
                            q1=g_a.canonical_question,
                            q2=g_b.canonical_question,
                            cat1=g_a.category if hasattr(g_a, "category") else None,
                            cat2=g_b.category if hasattr(g_b, "category") else None,
                            end1=a_end,
                            end2=b_end,
                            desc1=a_rep.get("description"),
                            desc2=b_rep.get("description"),
                            tfidf_score=tfidf_score,
                        )

                        if composite >= threshold:
                            would_merge.append({
                                "group_a_id": g_a.id,
                                "group_a_question": g_a.canonical_question,
                                "group_b_id": g_b.id,
                                "group_b_question": g_b.canonical_question,
                                "composite_score": round(composite, 4),
                            })

    return {"would_split": would_split, "would_merge": would_merge}


@router.get("/tags", response_model=list[TagResponse])
async def group_tags(
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_session),
) -> list[TagResponse]:
    """Return most frequent terms from active market questions."""
    service = GroupService(db)
    rows = await service.get_tags(limit=limit)
    return [TagResponse(**r) for r in rows]


@router.get("/{group_id}", response_model=GroupDetailResponse)
async def get_group(
    group_id: int,
    db: AsyncSession = Depends(get_session),
) -> GroupDetailResponse:
    """Get group detail with all member markets and best-odds routing."""
    service = GroupService(db)
    detail = await service.get_group_detail(group_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Group not found")
    return detail


@router.get("/{group_id}/history", response_model=list[GroupSnapshotResponse])
async def get_group_history(
    group_id: int,
    days: int = Query(default=30, ge=1, le=90),
    db: AsyncSession = Depends(get_session),
) -> list[GroupSnapshotResponse]:
    """Get historical consensus data for a group."""
    service = GroupService(db)
    return await service.get_group_history(group_id, days=days)
