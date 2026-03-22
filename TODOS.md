# TODOs

## P1 — Group-Level Price Alerts

**What:** Background task that monitors group consensus changes and new cross-platform spreads, triggers notifications.

**Why:** Highest-value follow-up to market grouping. Users want to know when consensus shifts (e.g., "Tesla deliveries consensus dropped 8 points") or when a new arbitrage opportunity appears (e.g., "9-point spread opened between Kalshi and Polymarket on X").

**Pros:** Transforms polyarb from "check when you remember" to "we tell you when something happens." Highest user-retention feature.

**Cons:** Needs notification channel decision (email? webhook? browser push?). Adds alert rules model, alert history, background check task (~3-4 new files).

**Context:** Requires `market_groups` + `group_price_snapshots` tables to exist. The `update_group_analytics` task already computes consensus and disagreement — alerts would check deltas between runs. Build after groups ship and are validated in production.

**Effort:** M (human: ~3 days / CC: ~30 min)
**Depends on:** Market grouping feature
**Added:** 2026-03-18 (eng review of market grouping plan)

## P1 — Trade Settlement Tracking

**What:** Scheduled task that polls platform APIs for market resolution status and computes actual P&L on settled trades.

**Why:** Without this, trades sit as "open" forever. You won't know if you actually made money until you manually check each platform. This is the "did it work?" question for the trading bot.

**Pros:** Automatic P&L computation, portfolio performance visibility, closed-loop feedback on strategy effectiveness.

**Cons:** Need to handle edge cases (voided markets, disputed outcomes, partial resolutions). Adds ~2 files (task + service method).

**Context:** Both Polymarket and Kalshi expose market resolution status via their existing APIs — the connector's `fetch_markets()` already reads `status` and `resolution` fields. A scheduled task would query all open trades, check their markets' resolution status, compute actual P&L (fill price × quantity vs outcome × quantity), and update the Trade record with `actual_profit` and `status = "settled"`.

**Effort:** S (human: ~2 days / CC: ~15 min)
**Priority:** P1
**Depends on:** Trading bot v1
**Added:** 2026-03-21 (CEO review of trading bot plan)

## P2 — WebSocket Price Feeds for Trading Bots

**What:** Replace 30s polling with real-time Polymarket WebSocket feeds + faster Kalshi polling (5s) for bot pairs.

**Why:** Polling every 30s means you miss spreads that open and close within that window. The existing PolymarketConnector has `POLYMARKET_WS_URL` in config and a `stream_prices` method signature already stubbed.

**Pros:** Faster spread detection, lower latency to execution, catch more opportunities.

**Cons:** More complex bot loop (event-driven vs poll-based), WebSocket reconnection logic, Kalshi doesn't have a public WebSocket so it stays as faster polling.

**Context:** The bot runner's poll-based loop would need to support an event-driven mode where the WebSocket pushes price updates and the strategy evaluates on each update rather than on a fixed timer. The Strategy protocol doesn't change — just the data source.

**Effort:** M (human: ~1 week / CC: ~20 min)
**Priority:** P2
**Depends on:** Trading bot v1
**Added:** 2026-03-21 (CEO review of trading bot plan)
