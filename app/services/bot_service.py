import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bot import Bot, Order, Trade
from app.models.matched_market import MatchedMarketPair

logger = structlog.get_logger()


class BotService:
    """CRUD and state management for trading bots."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create_bot(
        self,
        pair_id: int,
        strategy_name: str = "simple_arb",
        config: dict | None = None,
    ) -> Bot:
        """Create a new bot for a matched market pair.

        Enforces one active bot per pair (created, running, or paused).
        """
        # Verify pair exists
        pair = await self._db.get(MatchedMarketPair, pair_id)
        if pair is None:
            raise ValueError(f"Pair {pair_id} not found")

        # Check for existing active bot on this pair
        existing = await self._db.execute(
            select(Bot).where(
                and_(
                    Bot.pair_id == pair_id,
                    Bot.status.in_(["created", "running", "paused"]),
                )
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise ValueError(f"An active bot already exists for pair {pair_id}")

        bot = Bot(
            pair_id=pair_id,
            strategy_name=strategy_name,
            config=config or {},
        )
        self._db.add(bot)
        await self._db.flush()
        logger.info("bot_created", bot_id=bot.id, pair_id=pair_id, strategy=strategy_name)
        return bot

    async def get_bot(self, bot_id: int) -> Bot | None:
        return await self._db.get(Bot, bot_id)

    async def list_bots(self, status: str | None = None) -> list[Bot]:
        stmt = select(Bot).order_by(Bot.created_at.desc())
        if status:
            stmt = stmt.where(Bot.status == status)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def start_bot(self, bot_id: int) -> Bot:
        """Transition bot to running state."""
        bot = await self._db.get(Bot, bot_id)
        if bot is None:
            raise ValueError(f"Bot {bot_id} not found")
        bot.transition_to("running")
        await self._db.flush()
        logger.info("bot_started", bot_id=bot.id)
        return bot

    async def stop_bot(self, bot_id: int) -> Bot:
        """Transition bot to stopped state."""
        bot = await self._db.get(Bot, bot_id)
        if bot is None:
            raise ValueError(f"Bot {bot_id} not found")
        bot.transition_to("stopped")
        await self._db.flush()
        logger.info("bot_stopped", bot_id=bot.id)
        return bot

    async def resume_bot(self, bot_id: int) -> Bot:
        """Resume a paused bot."""
        bot = await self._db.get(Bot, bot_id)
        if bot is None:
            raise ValueError(f"Bot {bot_id} not found")
        bot.transition_to("running")
        await self._db.flush()
        logger.info("bot_resumed", bot_id=bot.id)
        return bot

    async def get_bot_trades(self, bot_id: int) -> list[Trade]:
        result = await self._db.execute(
            select(Trade).where(Trade.bot_id == bot_id).order_by(Trade.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_all_trades(self, limit: int = 50) -> list[Trade]:
        result = await self._db.execute(
            select(Trade).order_by(Trade.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())
