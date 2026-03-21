"""In-memory task status tracker for background scheduler tasks.

Provides a decorator that wraps scheduled tasks to record their last
run time, status, and duration. Data is lost on restart — acceptable
for an admin dashboard that shows "unknown" until the first run.
"""
import functools
import time
from datetime import datetime, timezone

_task_status: dict[str, dict] = {}


def track_task(task_id: str, interval_seconds: int):
    """Decorator that records last_run, status, and duration for a scheduled task."""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.monotonic()
            try:
                result = await func(*args, **kwargs)
                _task_status[task_id] = {
                    "last_run": datetime.now(timezone.utc).isoformat(),
                    "status": "success",
                    "duration_seconds": round(time.monotonic() - start, 1),
                    "interval_seconds": interval_seconds,
                    "error": None,
                }
                return result
            except Exception as exc:
                _task_status[task_id] = {
                    "last_run": datetime.now(timezone.utc).isoformat(),
                    "status": "error",
                    "duration_seconds": round(time.monotonic() - start, 1),
                    "interval_seconds": interval_seconds,
                    "error": str(exc)[:200],
                }
                raise

        return wrapper
    return decorator


def get_all_status() -> dict[str, dict]:
    """Return a copy of all tracked task statuses."""
    return dict(_task_status)
