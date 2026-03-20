import asyncio
import json
import re
import urllib.request
from datetime import datetime, timezone

import structlog
from kalshi_python_sync import Configuration, KalshiClient, EventsApi, MarketApi

from app.config import settings
from app.utils import first_float

logger = structlog.get_logger()


class KalshiConnector:
    """Kalshi connector using the official SDK for request handling,
    with raw JSON parsing to work around strict model validation."""

    def __init__(self) -> None:
        config = Configuration()
        config.host = settings.KALSHI_API_URL
        client = KalshiClient(configuration=config)
        self._events_api = EventsApi(client)
        self._markets_api = MarketApi(client)
        self._series_slug_cache: dict[str, str] = {}

    async def close(self) -> None:
        """No-op — SDK manages its own connections."""

    def _get_events_raw(self, **kwargs) -> dict:
        resp = self._events_api.get_events_without_preload_content(**kwargs)
        return json.loads(resp.data)

    def _get_event_raw(self, event_ticker: str, **kwargs) -> dict:
        resp = self._events_api.get_event_without_preload_content(
            event_ticker=event_ticker, **kwargs
        )
        return json.loads(resp.data)

    def _get_markets_raw(self, **kwargs) -> dict:
        resp = self._markets_api.get_markets_without_preload_content(**kwargs)
        return json.loads(resp.data)

    def _fetch_series_title(self, series_ticker: str) -> str | None:
        """Fetch the series title from the /series endpoint with retry."""
        url = f"{settings.KALSHI_API_URL}/series/{series_ticker}"
        for attempt in range(3):
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            try:
                resp = urllib.request.urlopen(req, timeout=10)
                data = json.loads(resp.read())
                return data.get("series", {}).get("title")
            except urllib.error.HTTPError as exc:
                if exc.code == 429 and attempt < 2:
                    import time
                    time.sleep(1.0 * (attempt + 1))
                    continue
                return None
            except Exception:
                return None
        return None

    @staticmethod
    def _slugify(text: str) -> str:
        text = text.lower().strip()
        text = re.sub(r"[^a-z0-9\s-]", "", text)
        text = re.sub(r"[\s]+", "-", text)
        text = re.sub(r"-+", "-", text).strip("-")
        return text

    def _get_series_slug(self, series_ticker: str) -> str | None:
        """Return cached series URL slug, fetching if needed."""
        if series_ticker in self._series_slug_cache:
            return self._series_slug_cache[series_ticker]
        title = self._fetch_series_title(series_ticker)
        slug = self._slugify(title) if title else None
        self._series_slug_cache[series_ticker] = slug
        return slug

    def _build_deep_link(self, series_ticker: str, event_ticker: str) -> str | None:
        if not event_ticker:
            return None
        slug = self._series_slug_cache.get(series_ticker) if series_ticker else None
        if series_ticker and slug:
            return (
                f"https://kalshi.com/markets/"
                f"{series_ticker.lower()}/{slug}/{event_ticker.lower()}"
            )
        # Fallback if slug unavailable
        return f"https://kalshi.com/markets/{event_ticker.lower()}"

    async def fetch_markets(self) -> list[dict]:
        """Fetch markets via events-first strategy.

        Paginates get_events(with_nested_markets=True) to collect real
        markets instead of 400k+ MVE combos from the flat /markets endpoint.
        """
        all_markets: list[dict] = []
        seen_tickers: set[str] = set()
        cursor: str | None = None
        event_count = 0

        while True:
            kwargs: dict = {"limit": 200, "with_nested_markets": True, "status": "open"}
            if cursor:
                kwargs["cursor"] = cursor

            try:
                data = await asyncio.to_thread(self._get_events_raw, **kwargs)
            except Exception as exc:
                logger.warning("kalshi_events_fetch_error", error=str(exc))
                break

            events = data.get("events") or []
            if not events:
                break

            for event in events:
                event_count += 1
                et = event.get("event_ticker", "")
                st = event.get("series_ticker", "")
                nested = event.get("markets") or []

                for market in nested:
                    ticker = market.get("ticker", "")
                    if not ticker or ticker in seen_tickers:
                        continue
                    seen_tickers.add(ticker)
                    market["event_ticker"] = et
                    market["series_ticker"] = st
                    # deep_link_url is set after series slugs are resolved
                    all_markets.append(market)

            logger.info(
                "kalshi_fetch_page",
                events_on_page=len(events),
                total_events=event_count,
                total_markets=len(all_markets),
            )

            cursor = data.get("cursor")
            if not cursor or len(events) < 200:
                break

        # Resolve series slugs for deep link URLs (parallel, batched)
        unique_series = list({m.get("series_ticker", "") for m in all_markets} - {""})
        logger.info("kalshi_resolving_series_slugs", count=len(unique_series))
        batch_size = 5
        for i in range(0, len(unique_series), batch_size):
            batch = unique_series[i : i + batch_size]
            await asyncio.gather(
                *(asyncio.to_thread(self._get_series_slug, st) for st in batch)
            )
            if (i + batch_size) % 200 == 0:
                logger.info("kalshi_series_progress", resolved=min(i + batch_size, len(unique_series)))

        resolved_count = sum(1 for v in self._series_slug_cache.values() if v is not None)
        failed_count = sum(1 for v in self._series_slug_cache.values() if v is None)
        logger.info(
            "kalshi_series_slugs_done",
            resolved=resolved_count,
            failed=failed_count,
        )

        # Pre-compute deep link URLs now that slugs are resolved
        for m in all_markets:
            m["_deep_link_url"] = self._build_deep_link(
                m.get("series_ticker", ""), m.get("event_ticker", "")
            )

        logger.info(
            "kalshi_fetch_complete",
            total_events=event_count,
            total_markets=len(all_markets),
            series_resolved=len(self._series_slug_cache),
            sample_url=all_markets[0].get("_deep_link_url") if all_markets else None,
        )
        return all_markets

    async def fetch_prices(self, market_ids: list[str]) -> list[dict]:
        """Batch-fetch prices using tickers param (100 per request)."""
        if not market_ids:
            return []

        results: list[dict] = []
        chunk_size = 100

        for i in range(0, len(market_ids), chunk_size):
            chunk = market_ids[i : i + chunk_size]
            tickers_str = ",".join(chunk)

            try:
                data = await asyncio.to_thread(
                    self._get_markets_raw, tickers=tickers_str
                )
                markets = data.get("markets") or []
                results.extend(markets)
            except Exception as exc:
                logger.warning(
                    "kalshi_batch_price_error",
                    chunk_start=i,
                    error=str(exc),
                )

        return results

    async def fetch_price_history(
        self, ticker: str, start_ts: int, end_ts: int
    ) -> list[dict]:
        """Fetch hourly candlestick data for a single market.

        Returns list of candlestick dicts with yes/no prices.
        """
        url = f"{settings.KALSHI_API_URL}/markets/{ticker}/candlesticks"

        def _fetch():
            req = urllib.request.Request(
                f"{url}?start_ts={start_ts}&end_ts={end_ts}&period_interval=60",
                headers={"Accept": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=30)
            return json.loads(resp.read())

        data = await asyncio.to_thread(_fetch)
        return data.get("candlesticks", [])

    async def search_markets(self, query: str, limit: int = 20) -> list[dict]:
        """Search by scanning event titles, then fetching nested markets."""
        query_lower = query.lower().strip()
        if not query_lower:
            return []

        try:
            matching_markets: list[dict] = []
            cursor: str | None = None
            max_pages = 20

            for _ in range(max_pages):
                kwargs: dict = {"limit": 200}
                if cursor:
                    kwargs["cursor"] = cursor

                data = await asyncio.to_thread(self._get_events_raw, **kwargs)
                events = data.get("events") or []
                if not events:
                    break

                matching_event_tickers: list[tuple[str, str]] = []
                for event in events:
                    title = (event.get("title") or "").lower()
                    et = event.get("event_ticker", "")
                    st = event.get("series_ticker", "")
                    if query_lower in title or query_lower in st.lower():
                        matching_event_tickers.append((et, st))

                for et, st in matching_event_tickers:
                    if len(matching_markets) >= limit:
                        break
                    # Resolve series slug if not cached
                    if st and st not in self._series_slug_cache:
                        await asyncio.to_thread(self._get_series_slug, st)
                    try:
                        event_data = await asyncio.to_thread(
                            self._get_event_raw, et, with_nested_markets=True
                        )
                        nested = (event_data.get("event") or {}).get("markets") or []
                        for market in nested:
                            market["event_ticker"] = et
                            market["series_ticker"] = st
                            matching_markets.append(market)
                    except Exception as exc:
                        logger.warning(
                            "kalshi_search_event_error",
                            event_ticker=et,
                            error=str(exc),
                        )

                cursor = data.get("cursor")
                if not cursor or len(events) < 200 or len(matching_markets) >= limit:
                    break

            # Pre-compute deep link URLs
            for m in matching_markets:
                m["_deep_link_url"] = self._build_deep_link(
                    m.get("series_ticker", ""), m.get("event_ticker", "")
                )

            logger.info(
                "kalshi_search_found",
                query=query,
                markets=len(matching_markets),
            )
            return matching_markets[:limit]

        except Exception as exc:
            logger.warning("kalshi_search_error", query=query, error=str(exc))
            return []

    def normalize(self, raw: dict) -> dict:
        # SDK numeric fields or dollar-string variants from nested events
        yes_bid = first_float(raw, "yes_bid", "yes_bid_dollars")
        no_bid = first_float(raw, "no_bid", "no_bid_dollars")
        yes_ask = first_float(raw, "yes_ask", "yes_ask_dollars")
        no_ask = first_float(raw, "no_ask", "no_ask_dollars")

        yes_label = raw.get("yes_sub_title") or "Yes"
        no_label = raw.get("no_sub_title") or "No"

        outcome_prices: dict[str, float] = {}
        if yes_bid is not None:
            outcome_prices[yes_label] = round(yes_bid, 4)
        if no_bid is not None:
            outcome_prices[no_label] = round(no_bid, 4)

        if yes_label in outcome_prices and no_label not in outcome_prices:
            outcome_prices[no_label] = round(1.0 - outcome_prices[yes_label], 4)
        elif no_label in outcome_prices and yes_label not in outcome_prices:
            outcome_prices[yes_label] = round(1.0 - outcome_prices[no_label], 4)

        outcomes = {yes_label: "yes", no_label: "no"}

        end_date = None
        close_time = raw.get("close_time") or raw.get("expected_expiration_time")
        if close_time:
            try:
                end_date = datetime.fromisoformat(
                    str(close_time).replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass

        start_date = None
        open_time = raw.get("open_time")
        if open_time:
            try:
                start_date = datetime.fromisoformat(
                    str(open_time).replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass

        volume_total = first_float(raw, "volume", "volume_fp") or 0.0
        volume_24h = first_float(raw, "volume_24h", "volume_24h_fp") or 0.0
        liquidity = first_float(raw, "open_interest", "open_interest_fp", "liquidity", "liquidity_dollars") or 0.0

        ticker = raw.get("ticker", "")
        deep_link = raw.get("_deep_link_url") or self._build_deep_link(
            raw.get("series_ticker", "") or "",
            raw.get("event_ticker", "") or "",
        )

        category = raw.get("category")
        if not category:
            sub_title = raw.get("subtitle", "") or ""
            event_ticker = raw.get("event_ticker", "") or ""
            category = self._infer_category(event_ticker, sub_title)

        status_map = {
            "open": "active",
            "active": "active",
            "closed": "closed",
            "determined": "resolved",
            "settled": "resolved",
            "finalized": "resolved",
        }
        raw_status = raw.get("status", "active")
        status = status_map.get(raw_status, "active")

        return {
            "platform_market_id": ticker,
            "question": raw.get("title", ""),
            "description": raw.get("subtitle"),
            "category": category,
            "outcomes": outcomes,
            "outcome_prices": outcome_prices,
            "volume_total": volume_total,
            "volume_24h": volume_24h,
            "liquidity": liquidity,
            "start_date": start_date,
            "end_date": end_date,
            "status": status,
            "resolution": raw.get("result"),
            "deep_link_url": deep_link,
            "image_url": raw.get("image_url"),
            "event_ticker": raw.get("event_ticker"),
            "series_ticker": raw.get("series_ticker"),
            "yes_ask": yes_ask,
            "no_ask": no_ask,
        }

    @staticmethod
    def _infer_category(event_ticker: str, subtitle: str) -> str | None:
        event_lower = event_ticker.lower()
        sub_lower = subtitle.lower()
        combined = f"{event_lower} {sub_lower}"

        category_keywords = {
            "politics": ["election", "president", "congress", "senate", "governor", "potus", "vote"],
            "crypto": ["bitcoin", "btc", "ethereum", "eth", "crypto", "defi"],
            "economics": ["fed", "inflation", "gdp", "unemployment", "interest rate", "cpi"],
            "sports": ["nfl", "nba", "mlb", "nhl", "super bowl", "world series", "championship"],
            "technology": ["ai", "tech", "apple", "google", "microsoft", "spacex"],
            "entertainment": ["oscar", "emmy", "grammy", "box office", "movie"],
            "climate": ["temperature", "hurricane", "weather", "climate"],
        }

        for cat, keywords in category_keywords.items():
            for kw in keywords:
                if kw in combined:
                    return cat

        return None
