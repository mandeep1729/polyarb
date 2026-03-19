from datetime import datetime, timezone

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings
from app.tasks.backfill_prices import backfill_all_prices
from app.tasks.cleanup import cleanup_old_snapshots
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

    # Mini-grouping: every 10 minutes (new/ungrouped markets only)
    scheduler.add_job(
        run_mini_grouping,
        "interval",
        seconds=settings.GROUP_MARKETS_INTERVAL_SECONDS,
        id="group_markets_mini",
        name="Mini-group new markets",
        next_run_time=now + timedelta(minutes=7),
    )

    # Full regrouping: every 2 hours (exhaustive cross-platform merge)
    scheduler.add_job(
        run_full_grouping,
        "interval",
        seconds=settings.GROUP_FULL_REGROUP_INTERVAL_SECONDS,
        id="group_markets_full",
        name="Full regroup all markets",
        next_run_time=now + timedelta(minutes=10),
    )

    scheduler.add_job(
        cleanup_old_snapshots,
        "interval",
        seconds=settings.CLEANUP_INTERVAL_SECONDS,
        id="cleanup_snapshots",
        name="Clean up old price snapshots",
    )

    # Backfill historical prices — runs daily, idempotent (ON CONFLICT DO NOTHING)
    scheduler.add_job(
        backfill_all_prices,
        "interval",
        seconds=settings.BACKFILL_PRICES_INTERVAL_SECONDS,
        id="backfill_prices",
        name="Backfill historical prices",
        next_run_time=now + timedelta(minutes=15),
    )

    logger.info(
        "scheduler_configured",
        fetch_markets_interval=settings.FETCH_MARKETS_INTERVAL_SECONDS,
        fetch_prices_interval=settings.FETCH_PRICES_INTERVAL_SECONDS,
        match_markets_interval=settings.MATCH_MARKETS_INTERVAL_SECONDS,
        cleanup_interval=settings.CLEANUP_INTERVAL_SECONDS,
    )

    return scheduler
