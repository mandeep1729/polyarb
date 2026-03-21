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
from app.tasks.task_tracker import track_task

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

    tracked_fetch_markets = track_task("fetch_markets", settings.FETCH_MARKETS_INTERVAL_SECONDS)(fetch_all_markets)
    tracked_fetch_prices = track_task("fetch_prices", settings.FETCH_PRICES_INTERVAL_SECONDS)(fetch_active_prices)
    tracked_matching = track_task("match_markets", settings.MATCH_MARKETS_INTERVAL_SECONDS)(run_matching)
    tracked_mini_grouping = track_task("group_markets_mini", settings.GROUP_MARKETS_INTERVAL_SECONDS)(run_mini_grouping)
    tracked_full_grouping = track_task("group_markets_full", settings.GROUP_FULL_REGROUP_INTERVAL_SECONDS)(run_full_grouping)
    tracked_deactivate = track_task("deactivate_expired", settings.CLEANUP_INTERVAL_SECONDS)(deactivate_expired_markets)
    tracked_backfill = track_task("backfill_prices", settings.BACKFILL_PRICES_INTERVAL_SECONDS)(backfill_all_prices)

    # Market metadata sync: every 15 min (takes ~5 min to run)
    scheduler.add_job(
        tracked_fetch_markets,
        "interval",
        seconds=settings.FETCH_MARKETS_INTERVAL_SECONDS,
        id="fetch_markets",
        name="Fetch markets from all platforms",
        next_run_time=now,
    )

    # Hourly price fetch for all active markets (batched, ~5-10 min)
    scheduler.add_job(
        tracked_fetch_prices,
        "interval",
        seconds=settings.FETCH_PRICES_INTERVAL_SECONDS,
        id="fetch_prices",
        name="Fetch prices for active markets",
        next_run_time=now + timedelta(minutes=6),
    )

    scheduler.add_job(
        tracked_matching,
        "interval",
        seconds=settings.MATCH_MARKETS_INTERVAL_SECONDS,
        id="match_markets",
        name="Match markets across platforms",
        next_run_time=now + timedelta(minutes=12),
    )

    scheduler.add_job(
        tracked_mini_grouping,
        "interval",
        seconds=settings.GROUP_MARKETS_INTERVAL_SECONDS,
        id="group_markets_mini",
        name="Mini-group new markets",
        next_run_time=now + timedelta(minutes=13),
    )

    scheduler.add_job(
        tracked_full_grouping,
        "interval",
        seconds=settings.GROUP_FULL_REGROUP_INTERVAL_SECONDS,
        id="group_markets_full",
        name="Full regroup all markets",
        next_run_time=now + timedelta(minutes=14),
    )

    scheduler.add_job(
        tracked_deactivate,
        "interval",
        seconds=settings.CLEANUP_INTERVAL_SECONDS,
        id="deactivate_expired",
        name="Deactivate markets past expiry",
        next_run_time=now + timedelta(minutes=2),
    )

    # Backfill top 1000 markets with full history — daily, idempotent
    # Starts 30 min after boot to avoid competing with initial market sync + price fetch
    scheduler.add_job(
        tracked_backfill,
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
