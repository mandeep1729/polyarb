import asyncio
import time
from abc import ABC, abstractmethod
from collections import deque

import httpx
import structlog

logger = structlog.get_logger()


class BaseConnector(ABC):
    def __init__(
        self,
        max_concurrent: int = 10,
        max_requests_per_window: int = 100,
        window_seconds: float = 10.0,
    ) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max_requests_per_window = max_requests_per_window
        self._window_seconds = window_seconds
        self._request_timestamps: deque[float] = deque()
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=10.0),
                limits=httpx.Limits(
                    max_connections=50,
                    max_keepalive_connections=20,
                ),
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _rate_limit(self) -> None:
        now = time.monotonic()
        while (
            self._request_timestamps
            and now - self._request_timestamps[0] > self._window_seconds
        ):
            self._request_timestamps.popleft()

        if len(self._request_timestamps) >= self._max_requests_per_window:
            oldest = self._request_timestamps[0]
            sleep_time = self._window_seconds - (now - oldest) + 0.01
            if sleep_time > 0:
                logger.debug("rate_limit_wait", sleep_seconds=round(sleep_time, 2))
                await asyncio.sleep(sleep_time)

        self._request_timestamps.append(time.monotonic())

    async def _retry(
        self,
        coro_factory,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                async with self._semaphore:
                    await self._rate_limit()
                    response = await coro_factory()
                    response.raise_for_status()
                    return response
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    delay = base_delay * (2 ** attempt)
                    retry_after = exc.response.headers.get("Retry-After")
                    if retry_after:
                        try:
                            delay = float(retry_after)
                        except ValueError:
                            pass
                    logger.warning(
                        "rate_limited",
                        attempt=attempt,
                        delay=delay,
                        status=exc.response.status_code,
                    )
                    await asyncio.sleep(delay)
                    last_exc = exc
                elif exc.response.status_code >= 500:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        "server_error_retry",
                        attempt=attempt,
                        delay=delay,
                        status=exc.response.status_code,
                    )
                    await asyncio.sleep(delay)
                    last_exc = exc
                else:
                    raise
            except (httpx.ConnectError, httpx.ReadTimeout) as exc:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    "connection_error_retry",
                    attempt=attempt,
                    delay=delay,
                    error=str(exc),
                )
                await asyncio.sleep(delay)
                last_exc = exc

        raise last_exc  # type: ignore[misc]

    @abstractmethod
    async def fetch_markets(self) -> list[dict]:
        ...

    async def search_markets(self, query: str, limit: int = 20) -> list[dict]:
        """Search upstream API for markets matching query. Override in subclasses."""
        return []

    @abstractmethod
    async def fetch_prices(self, market_ids: list[str]) -> list[dict]:
        ...

    @abstractmethod
    def normalize(self, raw: dict) -> dict:
        ...
