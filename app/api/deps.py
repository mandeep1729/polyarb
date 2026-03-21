from collections.abc import AsyncGenerator

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import RedisCache, get_cache
from app.database import async_session_factory

logger = structlog.get_logger()


async def get_db() -> AsyncGenerator[AsyncSession]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception as exc:
            logger.error("api_session_rollback", error=str(exc), exc_info=True)
            await session.rollback()
            raise


def get_redis_cache() -> RedisCache:
    return get_cache()
