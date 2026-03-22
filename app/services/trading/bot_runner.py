import asyncio

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.models.bot import Bot
from app.models.market import UnifiedMarket
from app.models.matched_market import MatchedMarketPair
from app.models.platform import Platform
from app.services.trading.execution_engine import ExecutionEngine
from app.services.trading.strategies import SimpleArbStrategy, estimate_fee

logger = structlog.get_logger()

# Bot runner lifecycle:
#
#   startup → load running bots → reconcile positions → start loops
#        │
#   each bot loop:
#        │
#        ├─ fetch_order_book(market_a) + fetch_order_book(market_b)
#        ├─ extract ask prices
#        ├─ estimate fees
#        ├─ strategy.evaluate() → Signal or None
#        ├─ if Signal: execution_engine.execute()
#        └─ sleep(poll_interval)
#        │
#   shutdown → cancel all tasks

_STRATEGIES = {
    "simple_arb": SimpleArbStrategy(),
}

_MAX_CONSECUTIVE_ERRORS = 3
_MAX_EMPTY_BOOK_CYCLES = 10


class BotRunner:
    """Manages bot lifecycle: start, stop, resume, and async poll loops."""

    def __init__(
        self,
        connectors: dict,
        db_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._connectors = connectors
        self._db_factory = db_factory
        self._engine = ExecutionEngine(connectors, db_factory)
        self._tasks: dict[int, asyncio.Task] = {}
        # Cached pair data per bot: {bot_id: (pair, market_a, market_b, platform_a, platform_b)}
        self._bot_context: dict[int, tuple] = {}

    async def startup(self) -> None:
        """Load all running bots and start their loops."""
        async with self._db_factory() as db:
            result = await db.execute(
                select(Bot).where(Bot.status == "running")
            )
            bots = result.scalars().all()

        logger.info("bot_runner_startup", running_bots=len(bots))
        for bot in bots:
            await self.start_bot(bot.id)

    async def shutdown(self) -> None:
        """Cancel all running bot tasks."""
        for bot_id, task in list(self._tasks.items()):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()
        self._bot_context.clear()
        logger.info("bot_runner_shutdown")

    async def start_bot(self, bot_id: int) -> None:
        """Start a bot's polling loop."""
        if bot_id in self._tasks and not self._tasks[bot_id].done():
            return  # Already running

        # Load and cache pair context
        context = await self._load_bot_context(bot_id)
        if context is None:
            logger.error("bot_start_failed_no_context", bot_id=bot_id)
            return
        self._bot_context[bot_id] = context

        # Position reconciliation before starting
        pair, market_a, market_b, platform_a, platform_b = context
        try:
            await self._reconcile_positions(bot_id, market_a, market_b, platform_a, platform_b)
        except Exception as exc:
            logger.error("bot_reconciliation_failed", bot_id=bot_id, error=str(exc))
            async with self._db_factory() as db:
                bot_r = await db.execute(select(Bot).where(Bot.id == bot_id))
                bot = bot_r.scalar_one_or_none()
                if bot and bot.status == "running":
                    bot.transition_to("paused", pause_reason="reconciliation_failed")
                    await db.commit()
            return

        task = asyncio.create_task(self._run_bot_loop(bot_id), name=f"bot-{bot_id}")
        self._tasks[bot_id] = task
        logger.info("bot_started", bot_id=bot_id)

    async def stop_bot(self, bot_id: int) -> None:
        """Stop a bot's polling loop."""
        task = self._tasks.pop(bot_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._bot_context.pop(bot_id, None)
        logger.info("bot_stopped", bot_id=bot_id)

    async def _load_bot_context(self, bot_id: int) -> tuple | None:
        """Load pair + market data for a bot (cached on start, reloaded on resume).

        Returns detached copies of the data needed for the bot loop, so they
        don't depend on an open database session.
        """
        async with self._db_factory() as db:
            bot_result = await db.execute(
                select(Bot).where(Bot.id == bot_id)
            )
            bot = bot_result.scalar_one_or_none()
            if not bot:
                return None

            pair_result = await db.execute(
                select(MatchedMarketPair).where(MatchedMarketPair.id == bot.pair_id)
            )
            pair = pair_result.scalar_one_or_none()
            if not pair:
                return None

            # Load both markets with their platforms
            ma_result = await db.execute(
                select(UnifiedMarket, Platform.slug)
                .join(Platform, Platform.id == UnifiedMarket.platform_id)
                .where(UnifiedMarket.id == pair.market_a_id)
            )
            row_a = ma_result.one_or_none()

            mb_result = await db.execute(
                select(UnifiedMarket, Platform.slug)
                .join(Platform, Platform.id == UnifiedMarket.platform_id)
                .where(UnifiedMarket.id == pair.market_b_id)
            )
            row_b = mb_result.one_or_none()

            if not row_a or not row_b:
                return None

            market_a, platform_a = row_a
            market_b, platform_b = row_b

            # Eagerly access all attributes before session closes
            # (MappedAsDataclass objects are detached-safe since expire_on_commit=False)
            _ = pair.outcome_mapping
            _ = market_a.outcomes
            _ = market_a.platform_market_id
            _ = market_b.outcomes
            _ = market_b.platform_market_id

            # Expunge so objects can be used outside the session
            db.expunge(pair)
            db.expunge(market_a)
            db.expunge(market_b)

            return (pair, market_a, market_b, platform_a, platform_b)

    async def _reconcile_positions(
        self,
        bot_id: int,
        market_a: UnifiedMarket,
        market_b: UnifiedMarket,
        platform_a: str,
        platform_b: str,
    ) -> None:
        """Check platform positions before starting. Raise on mismatch."""
        conn_a = self._connectors.get(platform_a)
        conn_b = self._connectors.get(platform_b)
        if not conn_a or not conn_b:
            return

        try:
            positions_a = await conn_a.get_positions()
            positions_b = await conn_b.get_positions()
        except Exception:
            # If we can't check positions, log and continue
            logger.warning("bot_reconciliation_skipped", bot_id=bot_id)
            return

        # Check for positions on the bot's markets
        has_position_a = any(
            p.get("market_id") == market_a.platform_market_id for p in positions_a
        )
        has_position_b = any(
            p.get("market_id") == market_b.platform_market_id for p in positions_b
        )

        if has_position_a != has_position_b:
            raise ValueError(
                f"Position mismatch: platform_a={has_position_a}, platform_b={has_position_b}"
            )

    async def _run_bot_loop(self, bot_id: int) -> None:
        """Main polling loop for a single bot."""
        consecutive_errors = 0
        consecutive_empty_books = 0

        while True:
            try:
                async with self._db_factory() as db:
                    bot_r = await db.execute(select(Bot).where(Bot.id == bot_id))
                    bot = bot_r.scalar_one_or_none()
                    if not bot or bot.status != "running":
                        logger.info("bot_loop_exit", bot_id=bot_id, reason="not_running")
                        return
                    db.expunge(bot)

                context = self._bot_context.get(bot_id)
                if not context:
                    logger.error("bot_loop_no_context", bot_id=bot_id)
                    return

                pair, market_a, market_b, platform_a, platform_b = context
                conn_a = self._connectors.get(platform_a)
                conn_b = self._connectors.get(platform_b)
                if not conn_a or not conn_b:
                    logger.error("bot_loop_no_connector", bot_id=bot_id)
                    return

                # Fetch order books for each outcome
                try:
                    books_a = await self._fetch_books_for_market(conn_a, market_a, platform_a)
                    books_b = await self._fetch_books_for_market(conn_b, market_b, platform_b)
                except Exception as exc:
                    if "auth" in str(exc).lower() or "401" in str(exc) or "403" in str(exc):
                        logger.error("bot_loop_auth_error", bot_id=bot_id, error=str(exc))
                        await self._pause_bot(bot_id, "auth_failure")
                        return
                    raise

                # Check for empty order books
                if not books_a or not books_b:
                    consecutive_empty_books += 1
                    logger.debug(
                        "bot_loop_empty_book",
                        bot_id=bot_id, count=consecutive_empty_books,
                    )
                    if consecutive_empty_books >= _MAX_EMPTY_BOOK_CYCLES:
                        logger.warning("bot_loop_empty_book_limit", bot_id=bot_id)
                        await self._pause_bot(bot_id, "empty_order_book")
                        return
                    poll_interval = bot.config.get(
                        "poll_interval_seconds",
                        settings.BOT_DEFAULT_POLL_INTERVAL_SECONDS,
                    )
                    await asyncio.sleep(poll_interval)
                    continue

                consecutive_empty_books = 0

                # Build ask prices dicts from order books
                prices_a = self._extract_ask_prices(market_a, books_a)
                prices_b = self._extract_ask_prices(market_b, books_b)

                # Compute fees
                max_pos = bot.config.get("max_position_size", settings.BOT_DEFAULT_MAX_POSITION_SIZE)
                avg_price_a = sum(prices_a.values()) / len(prices_a) if prices_a else 0.5
                avg_price_b = sum(prices_b.values()) / len(prices_b) if prices_b else 0.5
                fees_a = estimate_fee(platform_a, avg_price_a, max_pos, bot.config)
                fees_b = estimate_fee(platform_b, avg_price_b, max_pos, bot.config)

                # Evaluate strategy
                strategy = _STRATEGIES.get(bot.strategy_name)
                if not strategy:
                    logger.error("bot_loop_unknown_strategy", bot_id=bot_id, strategy=bot.strategy_name)
                    return

                signal = strategy.evaluate(
                    prices_a, prices_b, fees_a, fees_b,
                    bot.config, pair.outcome_mapping,
                )

                if signal:
                    logger.info(
                        "bot_heartbeat",
                        bot_id=bot_id,
                        spread=signal.expected_spread,
                        profit=signal.expected_profit,
                        action="trade",
                    )

                    # Determine leg ordering
                    first_platform = bot.config.get("first_leg_platform", "kalshi")
                    if platform_a == first_platform:
                        await self._engine.execute(
                            signal, bot,
                            market_a.id, market_b.id,
                            platform_a, platform_b,
                            market_a.platform_market_id,
                            market_b.platform_market_id,
                        )
                    else:
                        # Swap legs
                        swapped = type(signal)(
                            side_a=signal.side_b, outcome_a=signal.outcome_b,
                            price_a=signal.price_b,
                            side_b=signal.side_a, outcome_b=signal.outcome_a,
                            price_b=signal.price_a,
                            quantity=signal.quantity,
                            expected_spread=signal.expected_spread,
                            expected_profit=signal.expected_profit,
                        )
                        await self._engine.execute(
                            swapped, bot,
                            market_b.id, market_a.id,
                            platform_b, platform_a,
                            market_b.platform_market_id,
                            market_a.platform_market_id,
                        )
                else:
                    best_spread = self._compute_best_spread(prices_a, prices_b)
                    logger.info(
                        "bot_heartbeat",
                        bot_id=bot_id,
                        spread=best_spread,
                        threshold=bot.config.get("min_profit", settings.BOT_DEFAULT_MIN_PROFIT),
                        action="skip",
                    )

                consecutive_errors = 0

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                consecutive_errors += 1
                logger.error(
                    "bot_loop_error",
                    bot_id=bot_id,
                    error=str(exc),
                    consecutive=consecutive_errors,
                    exc_info=True,
                )
                if consecutive_errors >= _MAX_CONSECUTIVE_ERRORS:
                    await self._pause_bot(bot_id, f"consecutive_errors_{consecutive_errors}")
                    return
                await asyncio.sleep(30)
                continue

            poll_interval = bot.config.get(
                "poll_interval_seconds",
                settings.BOT_DEFAULT_POLL_INTERVAL_SECONDS,
            )
            await asyncio.sleep(poll_interval)

    def _extract_ask_prices(self, market: UnifiedMarket, books: dict) -> dict[str, float]:
        """Extract outcome ask prices from order books.

        books is {outcome_name: OrderBook}. For each outcome, use best_ask.
        """
        prices = {}
        for outcome_name, book in books.items():
            if book.best_ask is not None:
                prices[outcome_name] = book.best_ask
        return prices

    async def _fetch_books_for_market(self, connector, market: UnifiedMarket, platform: str) -> dict:
        """Fetch order books for each outcome of a market.

        For Polymarket, outcomes map to token_ids and each needs its own order book.
        For Kalshi, the single ticker gives yes/no prices.
        Returns {outcome_name: OrderBook}.
        """
        from app.services.trading.execution_engine import OrderBook

        outcomes = market.outcomes or {}
        if not outcomes:
            return {}

        if platform == "polymarket":
            # Each outcome has a token_id; fetch order book per token
            books = {}
            for outcome_name, token_id in outcomes.items():
                book = await connector.fetch_order_book(token_id)
                books[outcome_name] = book
            return books
        else:
            # Kalshi: single ticker, yes/no derived from one order book
            book = await connector.fetch_order_book(market.platform_market_id)
            result = {}
            outcome_names = list(outcomes.keys())
            if len(outcome_names) >= 1 and book.best_ask is not None:
                result[outcome_names[0]] = book
            if len(outcome_names) >= 2 and book.best_ask is not None:
                # No ask = 1 - Yes ask for binary Kalshi markets
                no_book = OrderBook(
                    best_bid=round(1.0 - book.best_ask, 4) if book.best_ask else None,
                    best_ask=round(1.0 - (book.best_bid or 0), 4) if book.best_bid else None,
                )
                result[outcome_names[1]] = no_book
            return result

    def _compute_best_spread(
        self, prices_a: dict[str, float], prices_b: dict[str, float],
    ) -> float:
        """Compute the best cross-outcome spread for logging."""
        best = 0.0
        for outcome_a in prices_a:
            for outcome_b in prices_b:
                if outcome_a != outcome_b:
                    total = prices_a[outcome_a] + prices_b[outcome_b]
                    spread = 1.0 - total
                    best = max(best, spread)
        return round(best, 4)

    async def _pause_bot(self, bot_id: int, reason: str) -> None:
        """Pause a bot and remove its task."""
        async with self._db_factory() as db:
            r = await db.execute(select(Bot).where(Bot.id == bot_id))
            bot = r.scalar_one_or_none()
            if bot and bot.status == "running":
                bot.transition_to("paused", pause_reason=reason)
                await db.commit()
        self._tasks.pop(bot_id, None)
        self._bot_context.pop(bot_id, None)
        logger.warning("bot_paused", bot_id=bot_id, reason=reason)
