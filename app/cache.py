import redis.asyncio as redis
import structlog

from app.config import settings

logger = structlog.get_logger()


class RedisCache:
    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._client: redis.Redis | None = None

    async def connect(self) -> None:
        self._client = redis.from_url(
            self._redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        logger.info("redis_connected", url=self._redis_url)

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            logger.info("redis_disconnected")

    async def get(self, key: str) -> str | None:
        if self._client is None:
            return None
        try:
            return await self._client.get(key)
        except redis.RedisError as exc:
            logger.warning("redis_get_error", key=key, error=str(exc))
            return None

    async def set(self, key: str, value: str, ttl: int = 60) -> None:
        if self._client is None:
            return
        try:
            await self._client.set(key, value, ex=ttl)
        except redis.RedisError as exc:
            logger.warning("redis_set_error", key=key, error=str(exc))

    async def delete(self, key: str) -> None:
        if self._client is None:
            return
        try:
            await self._client.delete(key)
        except redis.RedisError as exc:
            logger.warning("redis_delete_error", key=key, error=str(exc))


_cache_instance: RedisCache | None = None


def get_cache() -> RedisCache:
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = RedisCache(settings.REDIS_URL)
    return _cache_instance
