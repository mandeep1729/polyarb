from datetime import datetime, timezone

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings
from app.tasks.backfill_prices import backfill_all_prices
from app.tasks.cleanup import deactivate_expired_markets
from app.tasks.fetch_markets import fetch_all_markets
from app.tasks.fetch_prices import fetch_active_prices
from app.tasks.group_markets import run_full_grouping, run_mini_grouping
from app.tasks.match_markets import run_matching

logger = structlog.get_logger()


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(
        job_defaults={
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": 600,
        }
    )

    from datetime import timedelta

    now = datetime.now(timezone.utc)

    # Market metadata sync: every 15 min (takes ~5 min to run)
    scheduler.add_job(
        fetch_all_markets,
        "interval",
        seconds=settings.FETCH_MARKETS_INTERVAL_SECONDS,
        id="fetch_markets",
        name="Fetch markets from all platforms",
        next_run_time=now,
    )

    # Hourly price fetch for all active markets (batched, ~5-10 min)
    scheduler.add_job(
        fetch_active_prices,
        "interval",
        seconds=settings.FETCH_PRICES_INTERVAL_SECONDS,
        id="fetch_prices",
        name="Fetch prices for active markets",
        next_run_time=now + timedelta(minutes=6),
    )

    scheduler.add_job(
        run_matching,
        "interval",
        seconds=settings.MATCH_MARKETS_INTERVAL_SECONDS,
        id="match_markets",
        name="Match markets across platforms",
        next_run_time=now + timedelta(minutes=12),
    )

    scheduler.add_job(
        run_mini_grouping,
        "interval",
        seconds=settings.GROUP_MARKETS_INTERVAL_SECONDS,
        id="group_markets_mini",
        name="Mini-group new markets",
        next_run_time=now + timedelta(minutes=13),
    )

    scheduler.add_job(
        run_full_grouping,
        "interval",
        seconds=settings.GROUP_FULL_REGROUP_INTERVAL_SECONDS,
        id="group_markets_full",
        name="Full regroup all markets",
        next_run_time=now + timedelta(minutes=14),
    )

    scheduler.add_job(
        deactivate_expired_markets,
        "interval",
        seconds=settings.CLEANUP_INTERVAL_SECONDS,
        id="deactivate_expired",
        name="Deactivate markets past expiry",
        next_run_time=now + timedelta(minutes=2),
    )

    # Backfill top 1000 markets with full history — daily, idempotent
    # Starts 30 min after boot to avoid competing with initial market sync + price fetch
    scheduler.add_job(
        backfill_all_prices,
        "interval",
        seconds=settings.BACKFILL_PRICES_INTERVAL_SECONDS,
        id="backfill_prices",
        name="Backfill historical prices",
        next_run_time=now + timedelta(minutes=30),
    )

    logger.info(
        "scheduler_configured",
        fetch_markets_interval=settings.FETCH_MARKETS_INTERVAL_SECONDS,
        fetch_prices_interval=settings.FETCH_PRICES_INTERVAL_SECONDS,
        match_markets_interval=settings.MATCH_MARKETS_INTERVAL_SECONDS,
        cleanup_interval=settings.CLEANUP_INTERVAL_SECONDS,
    )

    return scheduler
