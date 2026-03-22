import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services.bot_service import BotService

logger = structlog.get_logger()

router = APIRouter(prefix="/bots", tags=["bots"])


class CreateBotInput(BaseModel):
    pair_id: int
    strategy: str = "simple_arb"
    config: dict | None = None


class BotResponse(BaseModel):
    id: int
    pair_id: int
    strategy_name: str
    config: dict
    status: str
    pause_reason: str | None = None

    model_config = {"from_attributes": True}


class TradeResponse(BaseModel):
    id: int
    bot_id: int
    leg_a_order_id: int
    leg_b_order_id: int | None = None
    spread_at_entry: float
    expected_profit: float
    actual_profit: float | None = None
    status: str

    model_config = {"from_attributes": True}


@router.post("", status_code=201, response_model=BotResponse)
async def create_bot(
    body: CreateBotInput,
    db: AsyncSession = Depends(get_db),
) -> BotResponse:
    """Create a new trading bot for a matched market pair."""
    service = BotService(db)
    try:
        bot = await service.create_bot(body.pair_id, body.strategy, body.config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return BotResponse.model_validate(bot)


@router.get("", response_model=list[BotResponse])
async def list_bots(
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[BotResponse]:
    """List all bots, optionally filtered by status."""
    service = BotService(db)
    bots = await service.list_bots(status)
    return [BotResponse.model_validate(b) for b in bots]


@router.get("/{bot_id}", response_model=BotResponse)
async def get_bot(
    bot_id: int,
    db: AsyncSession = Depends(get_db),
) -> BotResponse:
    service = BotService(db)
    bot = await service.get_bot(bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    return BotResponse.model_validate(bot)


@router.post("/{bot_id}/start", response_model=BotResponse)
async def start_bot(
    bot_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> BotResponse:
    """Start a bot (transitions from created/stopped to running)."""
    service = BotService(db)
    try:
        bot = await service.start_bot(bot_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Start the bot's polling loop via the BotRunner
    runner = request.app.state.bot_runner
    if runner:
        await runner.start_bot(bot_id)

    return BotResponse.model_validate(bot)


@router.post("/{bot_id}/stop", response_model=BotResponse)
async def stop_bot(
    bot_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> BotResponse:
    """Stop a bot (transitions from running/paused to stopped)."""
    service = BotService(db)
    try:
        bot = await service.stop_bot(bot_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Stop the bot's polling loop
    runner = request.app.state.bot_runner
    if runner:
        await runner.stop_bot(bot_id)

    return BotResponse.model_validate(bot)


@router.post("/{bot_id}/resume", response_model=BotResponse)
async def resume_bot(
    bot_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> BotResponse:
    """Resume a paused bot after manual review."""
    service = BotService(db)
    try:
        bot = await service.resume_bot(bot_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Restart the bot's polling loop (reloads context)
    runner = request.app.state.bot_runner
    if runner:
        await runner.start_bot(bot_id)

    return BotResponse.model_validate(bot)


@router.get("/{bot_id}/trades", response_model=list[TradeResponse])
async def get_bot_trades(
    bot_id: int,
    db: AsyncSession = Depends(get_db),
) -> list[TradeResponse]:
    """Get trade history for a specific bot."""
    service = BotService(db)
    trades = await service.get_bot_trades(bot_id)
    return [TradeResponse.model_validate(t) for t in trades]


@router.get("/trades/all", response_model=list[TradeResponse])
async def get_all_trades(
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[TradeResponse]:
    """Get all trades across all bots."""
    service = BotService(db)
    trades = await service.get_all_trades(limit)
    return [TradeResponse.model_validate(t) for t in trades]
