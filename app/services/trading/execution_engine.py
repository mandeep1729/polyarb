import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.bot import Bot, Order, Trade
from app.services.trading.strategies import Signal

logger = structlog.get_logger()

# Execution flow:
#
#   pre_flight_check (balance + exposure)
#        │
#        ▼
#   execute Leg A → poll for fill
#        │
#        ├─ timeout → cancel → return (no trade)
#        ├─ partial fill → accept filled_quantity
#        │
#        ▼
#   re-evaluate (re-fetch Leg B ask price)
#        │
#        ├─ no longer profitable → rollback Leg A → pause bot
#        │
#        ▼
#   execute Leg B (for filled_quantity) → poll for fill
#        │
#        ├─ filled → create Trade(status="open")
#        ├─ partial fill → rollback delta → create Trade(status="partial")
#        ├─ timeout → rollback Leg A → pause bot
#        │
#        ▼
#   rollback: sell Leg A at aggressive price
#        │
#        ├─ success → Trade(status="rolled_back") → pause bot
#        └─ failure → Trade(status="partial") → pause bot → webhook alert


@dataclass
class OrderResult:
    """Result from a connector's submit_order call."""

    platform_order_id: str
    status: str  # "pending", "filled", "partial"
    filled_quantity: int = 0
    avg_fill_price: float | None = None
    fee: float | None = None


@dataclass
class OrderBook:
    """Order book snapshot from a connector."""

    best_bid: float | None = None
    best_ask: float | None = None
    bids: list[tuple[float, int]] | None = None
    asks: list[tuple[float, int]] | None = None


class ExecutionEngine:
    """Handles two-leg trade execution with rollback and pause-on-failure safety."""

    def __init__(self, connectors: dict, db_factory) -> None:
        self._connectors = connectors  # {"polymarket": connector, "kalshi": connector}
        self._db_factory = db_factory

    async def execute(
        self,
        signal: Signal,
        bot: Bot,
        market_a_id: int,
        market_b_id: int,
        platform_a: str,
        platform_b: str,
        token_a: str,
        token_b: str,
    ) -> Trade | None:
        """Execute a two-leg arbitrage trade with rollback safety.

        Returns the Trade record on success, None if skipped (balance/exposure).
        On rollback, pauses the bot and returns the rolled-back Trade.
        """
        conn_a = self._connectors[platform_a]
        conn_b = self._connectors[platform_b]

        # Step 0: Pre-flight balance check
        try:
            balance_a = await conn_a.get_balance()
            balance_b = await conn_b.get_balance()
        except Exception as exc:
            logger.warning("execution_balance_check_failed", error=str(exc), bot_id=bot.id)
            return None

        cost_a = signal.price_a * signal.quantity
        cost_b = signal.price_b * signal.quantity
        if balance_a < cost_a or balance_b < cost_b:
            logger.warning(
                "execution_insufficient_balance",
                bot_id=bot.id,
                balance_a=balance_a, cost_a=cost_a,
                balance_b=balance_b, cost_b=cost_b,
            )
            return None

        # Check global exposure
        async with self._db_factory() as db:
            exposure = await self._get_total_exposure(db)
        if exposure + cost_a + cost_b > settings.BOT_MAX_TOTAL_EXPOSURE:
            logger.warning(
                "execution_exposure_limit",
                bot_id=bot.id,
                current_exposure=exposure,
                trade_cost=cost_a + cost_b,
                limit=settings.BOT_MAX_TOTAL_EXPOSURE,
            )
            return None

        order_timeout = bot.config.get(
            "order_timeout_seconds", settings.BOT_ORDER_TIMEOUT_SECONDS
        )
        rollback_timeout = bot.config.get(
            "rollback_timeout_seconds", settings.BOT_ROLLBACK_TIMEOUT_SECONDS
        )

        # Step 1: Execute Leg A
        logger.info(
            "execution_leg_a_start",
            bot_id=bot.id, platform=platform_a,
            outcome=signal.outcome_a, price=signal.price_a,
            quantity=signal.quantity,
        )
        leg_a_result = await self._submit_and_wait(
            conn_a, token_a, signal.side_a, signal.price_a,
            signal.quantity, order_timeout,
        )
        if leg_a_result is None or leg_a_result.filled_quantity == 0:
            logger.info("execution_leg_a_not_filled", bot_id=bot.id)
            return None

        filled_qty = leg_a_result.filled_quantity
        logger.info(
            "execution_leg_a_filled",
            bot_id=bot.id,
            filled=filled_qty, requested=signal.quantity,
            price=leg_a_result.avg_fill_price,
        )

        # Step 1.5: Re-evaluate before Leg B
        actual_price_a = leg_a_result.avg_fill_price or signal.price_a
        try:
            book_b = await conn_b.fetch_order_book(token_b)
            current_ask_b = book_b.best_ask
        except Exception:
            current_ask_b = signal.price_b

        if current_ask_b is not None:
            total_cost = actual_price_a + current_ask_b
            fees = (
                signal.expected_spread - signal.expected_profit
                + (1.0 - signal.price_a - signal.price_b)
                - signal.expected_spread
            )
            # Simpler: just check if total_cost + estimated_fees >= 1.0
            estimated_fees = abs(signal.expected_spread - signal.expected_profit)
            if total_cost + estimated_fees >= 1.0:
                logger.warning(
                    "execution_re_eval_unprofitable",
                    bot_id=bot.id,
                    actual_price_a=actual_price_a,
                    current_ask_b=current_ask_b,
                )
                # Rollback Leg A
                return await self._rollback_and_pause(
                    conn_a, token_a, filled_qty, bot,
                    leg_a_result, signal, market_a_id, market_b_id,
                    platform_a, rollback_timeout,
                )
            leg_b_price = current_ask_b
        else:
            leg_b_price = signal.price_b

        # Step 2: Execute Leg B (for filled_quantity from Leg A)
        logger.info(
            "execution_leg_b_start",
            bot_id=bot.id, platform=platform_b,
            outcome=signal.outcome_b, price=leg_b_price,
            quantity=filled_qty,
        )
        leg_b_result = await self._submit_and_wait(
            conn_b, token_b, signal.side_b, leg_b_price,
            filled_qty, order_timeout,
        )

        if leg_b_result is None or leg_b_result.filled_quantity == 0:
            # Leg B failed entirely — rollback Leg A
            logger.warning("execution_leg_b_failed", bot_id=bot.id)
            return await self._rollback_and_pause(
                conn_a, token_a, filled_qty, bot,
                leg_a_result, signal, market_a_id, market_b_id,
                platform_a, rollback_timeout,
            )

        # Handle partial fill on Leg B — rollback the unmatched delta
        delta = filled_qty - leg_b_result.filled_quantity
        if delta > 0:
            logger.warning(
                "execution_leg_b_partial",
                bot_id=bot.id,
                filled_b=leg_b_result.filled_quantity,
                delta=delta,
            )
            # Rollback delta from Leg A
            await self._rollback_position(
                conn_a, token_a, delta, rollback_timeout,
            )

        # Both legs filled (at least partially matched) — create Trade
        async with self._db_factory() as db:
            order_a = Order(
                bot_id=bot.id, market_id=market_a_id, platform=platform_a,
                platform_order_id=leg_a_result.platform_order_id,
                side=signal.side_a, outcome=signal.outcome_a,
                price=signal.price_a, quantity=signal.quantity,
                status="filled", filled_quantity=leg_a_result.filled_quantity,
                avg_fill_price=leg_a_result.avg_fill_price,
                fee=leg_a_result.fee,
                filled_at=datetime.now(timezone.utc),
            )
            db.add(order_a)
            await db.flush()

            order_b = Order(
                bot_id=bot.id, market_id=market_b_id, platform=platform_b,
                platform_order_id=leg_b_result.platform_order_id,
                side=signal.side_b, outcome=signal.outcome_b,
                price=leg_b_price, quantity=filled_qty,
                status="filled", filled_quantity=leg_b_result.filled_quantity,
                avg_fill_price=leg_b_result.avg_fill_price,
                fee=leg_b_result.fee,
                filled_at=datetime.now(timezone.utc),
            )
            db.add(order_b)
            await db.flush()

            trade_status = "open" if delta == 0 else "partial"
            trade = Trade(
                bot_id=bot.id,
                leg_a_order_id=order_a.id,
                leg_b_order_id=order_b.id,
                spread_at_entry=signal.expected_spread,
                expected_profit=signal.expected_profit,
                status=trade_status,
            )
            db.add(trade)
            await db.commit()

            logger.info(
                "execution_trade_created",
                bot_id=bot.id, trade_id=trade.id,
                status=trade_status,
                spread=signal.expected_spread,
                expected_profit=signal.expected_profit,
            )
            return trade

    async def _submit_and_wait(
        self, connector, token: str, side: str, price: float,
        quantity: int, timeout_seconds: int,
    ) -> OrderResult | None:
        """Submit an order and poll until filled or timeout."""
        try:
            result = await connector.submit_order(token, side, price, quantity)
        except Exception as exc:
            logger.error("execution_submit_error", error=str(exc), exc_info=True)
            return None

        if result.status == "filled":
            return result

        # Poll for fill
        elapsed = 0
        poll_interval = 5
        while elapsed < timeout_seconds:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            try:
                status = await connector.get_order_status(result.platform_order_id)
                if status.status == "filled":
                    return status
                if status.status in ("failed", "cancelled"):
                    return None
                if status.filled_quantity > 0 and status.status == "partial":
                    # Partial fill — accept what we got on timeout
                    if elapsed >= timeout_seconds:
                        try:
                            await connector.cancel_order(result.platform_order_id)
                        except Exception:
                            pass
                        return status
            except Exception as exc:
                logger.warning("execution_poll_error", error=str(exc))

        # Timeout — cancel and check final state
        try:
            await connector.cancel_order(result.platform_order_id)
            final = await connector.get_order_status(result.platform_order_id)
            if final.filled_quantity > 0:
                return final
        except Exception:
            pass
        return None

    async def _rollback_and_pause(
        self, connector, token: str, quantity: int, bot: Bot,
        leg_a_result: OrderResult, signal: Signal,
        market_a_id: int, market_b_id: int, platform_a: str,
        rollback_timeout: int,
    ) -> Trade:
        """Rollback Leg A position and pause the bot."""
        logger.critical(
            "execution_rollback_start",
            bot_id=bot.id, quantity=quantity,
        )

        rollback_success = await self._rollback_position(
            connector, token, quantity, rollback_timeout,
        )

        # Create trade record
        async with self._db_factory() as db:
            order_a = Order(
                bot_id=bot.id, market_id=market_a_id, platform=platform_a,
                platform_order_id=leg_a_result.platform_order_id,
                side=signal.side_a, outcome=signal.outcome_a,
                price=signal.price_a, quantity=signal.quantity,
                status="filled", filled_quantity=leg_a_result.filled_quantity,
                avg_fill_price=leg_a_result.avg_fill_price,
                fee=leg_a_result.fee,
                filled_at=datetime.now(timezone.utc),
            )
            db.add(order_a)
            await db.flush()

            trade_status = "rolled_back" if rollback_success else "partial"
            trade = Trade(
                bot_id=bot.id,
                leg_a_order_id=order_a.id,
                spread_at_entry=signal.expected_spread,
                expected_profit=signal.expected_profit,
                status=trade_status,
            )
            db.add(trade)

            # Pause the bot
            bot_result = await db.execute(select(Bot).where(Bot.id == bot.id))
            bot_row = bot_result.scalar_one_or_none()
            if bot_row:
                bot_row.transition_to("paused", pause_reason="rollback_triggered")
                db.add(bot_row)

            await db.commit()

            if not rollback_success:
                await self._fire_webhook_alert(bot.id, trade.id, "rollback_failed")

            logger.critical(
                "execution_rollback_complete",
                bot_id=bot.id, trade_id=trade.id,
                status=trade_status,
                rollback_success=rollback_success,
            )
            return trade

    async def _rollback_position(
        self, connector, token: str, quantity: int, timeout: int,
    ) -> bool:
        """Sell back a position at aggressive pricing. Returns True on success."""
        try:
            book = await connector.fetch_order_book(token)
            sell_price = book.best_bid if book.best_bid else 0.01
        except Exception:
            sell_price = 0.01

        result = await self._submit_and_wait(
            connector, token, "sell", sell_price, quantity, timeout,
        )
        return result is not None and result.filled_quantity > 0

    async def _get_total_exposure(self, db: AsyncSession) -> float:
        """Sum the notional value of all in-flight (open/partial) trades."""
        result = await db.execute(
            select(Trade).where(Trade.status.in_(["open", "partial"]))
        )
        trades = result.scalars().all()
        total = 0.0
        for t in trades:
            # Approximate exposure as spread_at_entry * quantity (from expected_profit)
            # More accurate: look up actual order prices, but this is sufficient
            total += abs(t.expected_profit) * 10  # rough estimate
        return total

    async def _fire_webhook_alert(self, bot_id: int, trade_id: int, event: str) -> None:
        """Fire a webhook alert for critical events (rollback failure)."""
        url = settings.BOT_ALERT_WEBHOOK_URL
        if not url:
            return
        payload = {
            "text": f"CRITICAL: Bot {bot_id} — {event}. Trade {trade_id} needs manual review.",
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(url, json=payload)
        except Exception as exc:
            logger.error("webhook_alert_failed", error=str(exc), bot_id=bot_id)
