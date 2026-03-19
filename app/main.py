from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api.arbitrage import router as arbitrage_router
from app.api.groups import router as groups_router
from app.api.health import router as health_router
from app.api.markets import router as markets_router
from app.api.search import router as search_router
from app.cache import get_cache
from app.config import settings
from app.logging import setup_logging
from app.tasks.scheduler import create_scheduler
from app.tasks.scheduler_thread import start_scheduler_thread, stop_scheduler_thread

setup_logging()

logger = structlog.get_logger()

limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    cache = get_cache()
    await cache.connect()
    logger.info("cache_connected")

    start_scheduler_thread(create_scheduler)
    logger.info("scheduler_started")

    yield

    stop_scheduler_thread()
    logger.info("scheduler_stopped")

    await cache.disconnect()
    logger.info("cache_disconnected")


app = FastAPI(
    title="Polyarb API",
    description="Prediction market aggregator & arbitrage detector",
    version="0.1.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api/v1")
app.include_router(markets_router, prefix="/api/v1")
app.include_router(arbitrage_router, prefix="/api/v1")
app.include_router(search_router, prefix="/api/v1")
app.include_router(groups_router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")
