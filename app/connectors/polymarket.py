import asyncio
import json
from datetime import datetime, timezone

import httpx
import structlog
import websockets

from app.config import settings
from app.connectors.base import BaseConnector

logger = structlog.get_logger()


class PolymarketConnector(BaseConnector):
    def __init__(self) -> None:
        super().__init__(
            max_concurrent=25,
            max_requests_per_window=300,
            window_seconds=10.0,
        )
        self._gamma_url = settings.POLYMARKET_API_URL
        self._clob_url = settings.POLYMARKET_CLOB_URL
        self._ws_url = settings.POLYMARKET_WS_URL

    async def fetch_markets(self) -> list[dict]:
        all_markets: list[dict] = []
        offset = 0
        page_size = 100

        while True:
            client = await self._get_client()

            response = await self._retry(
                lambda o=offset: client.get(
                    f"{self._gamma_url}/markets",
                    params={
                        "limit": page_size,
                        "offset": o,
                        "active": "true",
                        "closed": "false",
                    },
                )
            )

            data = response.json()

            if not data:
                break

            all_markets.extend(data)
            logger.info(
                "polymarket_fetch_page",
                offset=offset,
                count=len(data),
                total_so_far=len(all_markets),
            )

            if len(data) < page_size:
                break

            offset += page_size

        logger.info("polymarket_fetch_complete", total=len(all_markets))
        return all_markets

    async def fetch_prices(self, market_ids: list[str]) -> list[dict]:
        if not market_ids:
            return []

        results: list[dict] = []
        client = await self._get_client()

        batch_size = 50
        for i in range(0, len(market_ids), batch_size):
            batch = market_ids[i : i + batch_size]

            tasks = []
            for condition_id in batch:
                tasks.append(self._fetch_single_price(client, condition_id))

            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            for cid, res in zip(batch, batch_results):
                if isinstance(res, Exception):
                    logger.warning("polymarket_price_error", condition_id=cid, error=str(res))
                    continue
                results.append(res)

        return results

    async def _fetch_single_price(self, client: httpx.AsyncClient, condition_id: str) -> dict:
        response = await self._retry(
            lambda: client.get(
                f"{self._clob_url}/prices",
                params={"token_id": condition_id},
            )
        )
        response.raise_for_status()
        data = response.json()
        return {"condition_id": condition_id, "prices": data}

    async def stream_prices(self, market_ids: list[str], callback) -> None:
        if not market_ids:
            return

        while True:
            try:
                async with websockets.connect(self._ws_url) as ws:
                    subscribe_msg = {
                        "type": "market",
                        "assets_ids": market_ids,
                    }
                    await ws.send(json.dumps(subscribe_msg))
                    logger.info("polymarket_ws_connected", markets=len(market_ids))

                    async for message in ws:
                        try:
                            data = json.loads(message)
                            await callback(data)
                        except json.JSONDecodeError:
                            logger.warning("polymarket_ws_invalid_json")
                        except Exception as exc:
                            logger.error("polymarket_ws_callback_error", error=str(exc))

            except websockets.ConnectionClosed as exc:
                logger.warning("polymarket_ws_disconnected", code=exc.code)
                await asyncio.sleep(5)
            except Exception as exc:
                logger.error("polymarket_ws_error", error=str(exc))
                await asyncio.sleep(10)

    async def fetch_price_history(
        self, token_id: str, start_ts: int, end_ts: int
    ) -> list[dict]:
        """Fetch hourly price history for a single token.

        Returns list of {"t": unix_timestamp, "p": price_float}.
        """
        client = await self._get_client()
        response = await self._retry(
            lambda: client.get(
                f"{self._clob_url}/prices-history",
                params={
                    "market": token_id,
                    "interval": "1h",
                    "startTs": start_ts,
                    "endTs": end_ts,
                    "fidelity": 60,
                },
            )
        )
        data = response.json()
        if not isinstance(data, dict):
            return []
        return data.get("history", [])

    async def search_markets(self, query: str, limit: int = 20) -> list[dict]:
        """Search Polymarket events API using _q parameter, return flattened markets."""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=3.0)) as client:
                response = await client.get(
                    f"{self._gamma_url}/events",
                    params={
                        "_q": query,
                        "limit": limit,
                        "active": "true",
                        "closed": "false",
                    },
                )
                response.raise_for_status()
            events = response.json()
            if not isinstance(events, list):
                return []

            markets: list[dict] = []
            for event in events:
                nested = event.get("markets", [])
                if isinstance(nested, list):
                    markets.extend(nested)
                if len(markets) >= limit:
                    break

            return markets[:limit]
        except Exception as exc:
            logger.warning("polymarket_search_error", query=query, error=str(exc))
            return []

    def normalize(self, raw: dict) -> dict:
        outcomes = {}
        outcome_prices = {}

        tokens = raw.get("tokens", [])
        if tokens:
            for token in tokens:
                outcome_name = token.get("outcome", "Unknown")
                outcomes[outcome_name] = token.get("token_id", "")
                price = token.get("price")
                if price is not None:
                    outcome_prices[outcome_name] = float(price)
        else:
            outcomes_list = raw.get("outcomes", [])
            prices_list = raw.get("outcomePrices", [])
            if isinstance(outcomes_list, str):
                try:
                    outcomes_list = json.loads(outcomes_list)
                except (json.JSONDecodeError, TypeError):
                    outcomes_list = []
            if isinstance(prices_list, str):
                try:
                    prices_list = json.loads(prices_list)
                except (json.JSONDecodeError, TypeError):
                    prices_list = []

            for i, outcome_name in enumerate(outcomes_list):
                outcomes[outcome_name] = outcome_name
                if i < len(prices_list):
                    try:
                        outcome_prices[outcome_name] = float(prices_list[i])
                    except (ValueError, TypeError):
                        pass

        end_date = None
        end_str = raw.get("endDate") or raw.get("end_date_iso")
        if end_str:
            try:
                end_date = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        start_date = None
        start_str = raw.get("startDate") or raw.get("start_date_iso")
        if start_str:
            try:
                start_date = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        volume_str = raw.get("volume", "0")
        try:
            volume_total = float(volume_str)
        except (ValueError, TypeError):
            volume_total = 0.0

        volume_24h_str = raw.get("volume24hr", "0")
        try:
            volume_24h = float(volume_24h_str)
        except (ValueError, TypeError):
            volume_24h = 0.0

        liquidity_str = raw.get("liquidity", "0")
        try:
            liquidity = float(liquidity_str)
        except (ValueError, TypeError):
            liquidity = 0.0

        condition_id = raw.get("condition_id") or raw.get("conditionId") or ""
        slug = raw.get("slug", "")
        deep_link = f"https://polymarket.com/event/{slug}" if slug else None

        category = raw.get("category")
        if not category:
            tags = raw.get("tags", [])
            if tags and isinstance(tags, list):
                category = tags[0].get("label") if isinstance(tags[0], dict) else str(tags[0])

        return {
            "platform_market_id": condition_id or str(raw.get("id", "")),
            "question": raw.get("question", ""),
            "description": raw.get("description"),
            "category": category,
            "outcomes": outcomes,
            "outcome_prices": outcome_prices,
            "volume_total": volume_total,
            "volume_24h": volume_24h,
            "liquidity": liquidity,
            "start_date": start_date,
            "end_date": end_date,
            "status": "active" if raw.get("active") else "closed",
            "deep_link_url": deep_link,
            "image_url": raw.get("image"),
            "event_ticker": slug or None,
        }
