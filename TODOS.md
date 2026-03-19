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
