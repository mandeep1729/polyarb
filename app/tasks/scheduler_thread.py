import asyncio
import threading
from collections.abc import Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler

_loop: asyncio.AbstractEventLoop | None = None
_thread: threading.Thread | None = None


def start_scheduler_thread(create_fn: Callable[[], AsyncIOScheduler]) -> None:
    global _loop, _thread
    ready = threading.Event()

    def _run() -> None:
        global _loop
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)

        scheduler = create_fn()

        # Schedule start inside the running loop so get_running_loop() works
        async def _start_scheduler() -> None:
            scheduler.start()
            ready.set()

        _loop.create_task(_start_scheduler())
        _loop.run_forever()
        scheduler.shutdown(wait=False)

    _thread = threading.Thread(target=_run, daemon=True, name="scheduler")
    _thread.start()
    ready.wait(timeout=10)


def stop_scheduler_thread() -> None:
    if _loop is not None:
        _loop.call_soon_threadsafe(_loop.stop)
