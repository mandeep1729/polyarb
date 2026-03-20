"""API endpoints for market groups."""
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.market_group import MarketGroup, MarketGroupMember
from app.schemas.group import (
    GroupDetailResponse,
    GroupListResponse,
    GroupSnapshotResponse,
)
from app.services.group_service import GroupService
from app.tasks.group_markets import run_full_grouping

router = APIRouter(prefix="/groups", tags=["groups"])


@router.get("", response_model=GroupListResponse)
async def list_groups(
    category: str | None = None,
    sort_by: str = Query(default="liquidity", pattern="^(disagreement|volume|liquidity|consensus|created_at)$"),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    db: AsyncSession = Depends(get_session),
) -> GroupListResponse:
    """List active market groups with pagination."""
    service = GroupService(db)
    return await service.get_groups(
        category=category, sort_by=sort_by, limit=limit, cursor=cursor
    )


@router.get("/search", response_model=GroupListResponse)
async def search_groups(
    q: str = Query(..., min_length=2, max_length=200),
    category: str | None = None,
    sort_by: str = Query(default="liquidity", pattern="^(disagreement|volume|liquidity|consensus|created_at)$"),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_session),
) -> GroupListResponse:
    """Search groups by canonical question text."""
    service = GroupService(db)
    return await service.search_groups(
        query=q, category=category, sort_by=sort_by, limit=limit
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
