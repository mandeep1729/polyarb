from datetime import datetime, timezone

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings
from app.tasks.cleanup import cleanup_old_snapshots
from app.tasks.fetch_markets import fetch_all_markets
from app.tasks.fetch_prices import fetch_active_prices
from app.tasks.group_markets import run_grouping
from app.tasks.match_markets import run_matching

logger = structlog.get_logger()


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(
        job_defaults={
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": 60,
        }
    )

    from datetime import timedelta

    now = datetime.now(timezone.utc)

    # Stagger jobs so they don't all compete for API/DB at startup
    scheduler.add_job(
        fetch_all_markets,
        "interval",
        seconds=settings.FETCH_MARKETS_INTERVAL_SECONDS,
        id="fetch_markets",
        name="Fetch markets from all platforms",
        next_run_time=now,
    )

    # Price fetch starts after markets have had time to sync
    scheduler.add_job(
        fetch_active_prices,
        "interval",
        seconds=settings.FETCH_PRICES_INTERVAL_SECONDS,
        id="fetch_prices",
        name="Fetch prices for active markets",
        next_run_time=now + timedelta(minutes=5),
    )

    # Matching starts after initial market fetch
    scheduler.add_job(
        run_matching,
        "interval",
        seconds=settings.MATCH_MARKETS_INTERVAL_SECONDS,
        id="match_markets",
        name="Match markets across platforms",
        next_run_time=now + timedelta(minutes=6),
    )

    # Grouping runs after markets are fetched
    scheduler.add_job(
        run_grouping,
        "interval",
        seconds=settings.GROUP_MARKETS_INTERVAL_SECONDS,
        id="group_markets",
        name="Group markets and compute analytics",
        next_run_time=now + timedelta(minutes=7),
    )

    scheduler.add_job(
        cleanup_old_snapshots,
        "interval",
        seconds=settings.CLEANUP_INTERVAL_SECONDS,
        id="cleanup_snapshots",
        name="Clean up old price snapshots",
    )

    logger.info(
        "scheduler_configured",
        fetch_markets_interval=settings.FETCH_MARKETS_INTERVAL_SECONDS,
        fetch_prices_interval=settings.FETCH_PRICES_INTERVAL_SECONDS,
        match_markets_interval=settings.MATCH_MARKETS_INTERVAL_SECONDS,
        cleanup_interval=settings.CLEANUP_INTERVAL_SECONDS,
    )

    return scheduler
