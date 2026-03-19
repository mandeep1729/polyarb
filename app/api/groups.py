"""API endpoints for market groups."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.group import (
    GroupDetailResponse,
    GroupListResponse,
    GroupSnapshotResponse,
)
from app.services.group_service import GroupService

router = APIRouter(prefix="/groups", tags=["groups"])


@router.get("", response_model=GroupListResponse)
async def list_groups(
    category: str | None = None,
    sort_by: str = Query(default="disagreement", pattern="^(disagreement|volume|liquidity|consensus|created_at)$"),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    db: AsyncSession = Depends(get_session),
) -> GroupListResponse:
    """List active market groups with pagination."""
    service = GroupService(db)
    return await service.get_groups(
        category=category, sort_by=sort_by, limit=limit, cursor=cursor
    )


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
