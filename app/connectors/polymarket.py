import asyncio
import json
from datetime import datetime

import structlog
import websockets
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import BookParams

from app.config import settings
from app.categories import infer_category, resolve_tag
from app.connectors.base import BaseConnector

logger = structlog.get_logger()


def _inject_event_metadata(event: dict, market: dict) -> dict:
    """Inject event-level metadata into a market dict for normalize()."""
    market["_event_slug"] = event.get("slug", "")
    market["_event_title"] = event.get("title", "")
    market["_event_tags"] = event.get("tags", [])
    market["_event_image"] = event.get("image")
    return market


class PolymarketConnector(BaseConnector):
    def __init__(self) -> None:
        super().__init__(
            max_concurrent=5,
            max_requests_per_window=30,
            window_seconds=10.0,
        )
        self._gamma_url = settings.POLYMARKET_API_URL
        self._clob_url = settings.POLYMARKET_CLOB_URL
        self._ws_url = settings.POLYMARKET_WS_URL
        # Read-only client for market data
        self._clob = ClobClient(settings.POLYMARKET_CLOB_URL)
        # Authenticated client for trading (optional — only if credentials are set)
        self._trading_clob: ClobClient | None = None
        if settings.POLYMARKET_PRIVATE_KEY:
            self._trading_clob = ClobClient(
                settings.POLYMARKET_CLOB_URL,
                key=settings.POLYMARKET_PRIVATE_KEY,
                chain_id=settings.POLYMARKET_CHAIN_ID,
                creds={
                    "api_key": settings.POLYMARKET_API_KEY,
                    "api_secret": settings.POLYMARKET_API_SECRET,
                    "api_passphrase": settings.POLYMARKET_PASSPHRASE,
                },
            )
            logger.info("polymarket_trading_enabled")

    async def fetch_markets(self) -> list[dict]:
        """Fetch markets via event-first pagination on Gamma API.

        Paginates GET /events?active=true&closed=false, then flattens
        nested markets with injected event metadata for reliable grouping.
        """
        all_markets: list[dict] = []
        seen_condition_ids: set[str] = set()
        offset = 0
        page_size = 100

        while True:
            client = await self._get_client()

            response = await self._retry(
                lambda o=offset: client.get(
                    f"{self._gamma_url}/events",
                    params={
                        "limit": page_size,
                        "offset": o,
                        "active": "true",
                        "closed": "false",
                    },
                )
            )

            events = response.json()

            if not events or not isinstance(events, list):
                break

            for event in events:
                nested = event.get("markets", [])
                if not isinstance(nested, list):
                    continue
                for market in nested:
                    cid = market.get("condition_id") or market.get("conditionId", "")
                    if not cid or cid in seen_condition_ids:
                        continue
                    seen_condition_ids.add(cid)
                    _inject_event_metadata(event, market)
                    all_markets.append(market)

            logger.info(
                "polymarket_fetch_page",
                offset=offset,
                events_on_page=len(events),
                total_markets=len(all_markets),
            )

            if len(events) < page_size:
                break

            offset += page_size

        logger.info("polymarket_fetch_complete", total=len(all_markets))
        return all_markets

    async def fetch_prices(self, token_ids: list[str]) -> dict[str, str]:
        """Fetch midpoint prices for a batch of token_ids via py-clob-client SDK.

        Args:
            token_ids: List of CLOB token_ids (NOT condition_ids).

        Returns:
            Dict mapping token_id -> midpoint price string (e.g. "0.65").
        """
        if not token_ids:
            return {}

        all_prices: dict[str, str] = {}
        batch_size = 100
        for i in range(0, len(token_ids), batch_size):
            batch = token_ids[i : i + batch_size]
            params = [BookParams(token_id=tid) for tid in batch]
            try:
                result = await asyncio.to_thread(self._clob.get_midpoints, params)
                if isinstance(result, dict):
                    all_prices.update(result)
            except Exception as exc:
                logger.error(
                    "polymarket_midpoints_error",
                    batch_start=i,
                    batch_size=len(batch),
                    error=str(exc),
                    exc_info=True,
                )

            if i + batch_size < len(token_ids):
                await asyncio.sleep(1.0)

        return all_prices

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
                            logger.error("polymarket_ws_callback_error", error=str(exc), exc_info=True)

            except websockets.ConnectionClosed as exc:
                logger.warning("polymarket_ws_disconnected", code=exc.code)
                await asyncio.sleep(5)
            except Exception as exc:
                logger.error("polymarket_ws_error", error=str(exc), exc_info=True)
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
            client = await self._get_client()
            response = await self._retry(
                lambda: client.get(
                    f"{self._gamma_url}/events",
                    params={
                        "_q": query,
                        "limit": limit,
                        "active": "true",
                        "closed": "false",
                    },
                )
            )
            events = response.json()
            if not isinstance(events, list):
                return []

            markets: list[dict] = []
            for event in events:
                nested = event.get("markets", [])
                if not isinstance(nested, list):
                    continue
                for market in nested:
                    _inject_event_metadata(event, market)
                    markets.append(market)
                if len(markets) >= limit:
                    break

            return markets[:limit]
        except Exception as exc:
            logger.error("polymarket_search_error", query=query, error=str(exc), exc_info=True)
            return []

    # --- Trading methods ---

    async def fetch_order_book(self, token_id: str):
        """Fetch order book for a token, returning best bid/ask."""
        from app.services.trading.execution_engine import OrderBook

        try:
            book = await asyncio.to_thread(
                self._clob.get_order_book, token_id
            )
            best_bid = None
            best_ask = None
            if hasattr(book, "bids") and book.bids:
                best_bid = float(book.bids[0].price)
            if hasattr(book, "asks") and book.asks:
                best_ask = float(book.asks[0].price)
            return OrderBook(best_bid=best_bid, best_ask=best_ask)
        except Exception as exc:
            logger.error("polymarket_order_book_error", token_id=token_id, error=str(exc))
            return OrderBook()

    async def submit_order(self, token_id: str, side: str, price: float, quantity: int):
        """Submit a limit order via the authenticated CLOB client."""
        from app.services.trading.execution_engine import OrderResult

        if not self._trading_clob:
            raise RuntimeError("Trading not enabled — POLYMARKET_PRIVATE_KEY not set")

        order = await asyncio.to_thread(
            self._trading_clob.create_and_post_order,
            {
                "token_id": token_id,
                "price": price,
                "size": quantity,
                "side": side.upper(),
            },
        )
        order_id = order.get("id", "") if isinstance(order, dict) else str(order)
        return OrderResult(
            platform_order_id=order_id,
            status="pending",
        )

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""
        if not self._trading_clob:
            raise RuntimeError("Trading not enabled")
        try:
            await asyncio.to_thread(self._trading_clob.cancel, order_id)
            return True
        except Exception as exc:
            logger.error("polymarket_cancel_error", order_id=order_id, error=str(exc))
            return False

    async def get_order_status(self, order_id: str):
        """Poll order status."""
        from app.services.trading.execution_engine import OrderResult

        if not self._trading_clob:
            raise RuntimeError("Trading not enabled")
        order = await asyncio.to_thread(self._trading_clob.get_order, order_id)
        if isinstance(order, dict):
            status = order.get("status", "pending")
            filled = int(order.get("size_matched", 0))
            price = float(order.get("price", 0))
            return OrderResult(
                platform_order_id=order_id,
                status="filled" if status == "matched" else status,
                filled_quantity=filled,
                avg_fill_price=price if filled > 0 else None,
            )
        return OrderResult(platform_order_id=order_id, status="pending")

    async def get_balance(self) -> float:
        """Get account balance (USDC)."""
        if not self._trading_clob:
            raise RuntimeError("Trading not enabled")
        try:
            balance = await asyncio.to_thread(self._trading_clob.get_balance_allowance)
            if isinstance(balance, dict):
                return float(balance.get("balance", 0))
            return 0.0
        except Exception as exc:
            logger.error("polymarket_balance_error", error=str(exc))
            return 0.0

    async def get_positions(self) -> list[dict]:
        """Get current positions."""
        if not self._trading_clob:
            return []
        try:
            positions = await asyncio.to_thread(self._trading_clob.get_positions)
            if isinstance(positions, list):
                return [{"market_id": p.get("asset", {}).get("condition_id", "")} for p in positions]
            return []
        except Exception:
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
            clob_token_ids = raw.get("clobTokenIds", [])
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
            if isinstance(clob_token_ids, str):
                try:
                    clob_token_ids = json.loads(clob_token_ids)
                except (json.JSONDecodeError, TypeError):
                    clob_token_ids = []

            for i, outcome_name in enumerate(outcomes_list):
                token_id = clob_token_ids[i] if i < len(clob_token_ids) else outcome_name
                outcomes[outcome_name] = token_id
                if i < len(prices_list):
                    try:
                        outcome_prices[outcome_name] = float(prices_list[i])
                    except (ValueError, TypeError) as exc:
                        logger.warning("polymarket_normalize_price_error", outcome=outcome_name, value=prices_list[i], error=str(exc))

        end_date = None
        end_str = raw.get("endDate") or raw.get("end_date_iso")
        if end_str:
            try:
                end_date = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
            except (ValueError, TypeError) as exc:
                logger.warning("polymarket_normalize_end_date_error", end_str=end_str, error=str(exc))

        start_date = None
        start_str = raw.get("startDate") or raw.get("start_date_iso")
        if start_str:
            try:
                start_date = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            except (ValueError, TypeError) as exc:
                logger.warning("polymarket_normalize_start_date_error", start_str=start_str, error=str(exc))

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
        # Prefer injected event metadata, fall back to legacy extraction
        event_slug = raw.get("_event_slug") or ""
        if not event_slug:
            events = raw.get("events", [])
            event_slug = events[0].get("slug") if events else raw.get("slug", "")
        deep_link = f"https://polymarket.com/event/{event_slug}" if event_slug else None

        category = raw.get("category")
        if not category:
            tags = raw.get("_event_tags") or raw.get("tags", [])
            if tags and isinstance(tags, list):
                tag_label = tags[0].get("label") if isinstance(tags[0], dict) else str(tags[0])
                # Resolve to canonical DB category; fall back to raw tag
                category = resolve_tag(tag_label) or tag_label
        if not category:
            category = infer_category(
                question=raw.get("question", ""),
                description=raw.get("description"),
            )

        image_url = raw.get("_event_image") or raw.get("image")

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
            "image_url": image_url,
            "event_ticker": event_slug or None,
        }
