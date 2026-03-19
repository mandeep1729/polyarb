from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import RedisCache, get_cache
from app.database import async_session_factory


async def get_db() -> AsyncGenerator[AsyncSession]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_redis_cache() -> RedisCache:
    return get_cache()
