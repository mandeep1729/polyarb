# Polyarb — Prediction Market Aggregator & Arbitrage Detector

## Overview
Polyarb aggregates prediction markets from Polymarket, Kalshi, and other platforms into a unified interface. It normalizes odds, matches same events across platforms, and detects arbitrage opportunities.

## Tech Stack
- Backend: Python + FastAPI + SQLAlchemy (async) + PostgreSQL + Redis
- Frontend: Next.js 14+ (App Router) + React + TanStack Query + Tailwind CSS
- Background tasks: APScheduler (in-process)
- Matching: scikit-learn (TF-IDF) + rapidfuzz (fuzzy matching)
- Deployment: Docker Compose

## Key Features
1. Market aggregation from multiple platforms
2. Arbitrage detection via cross-platform matching
3. Smart search with synonym expansion
4. Real-time odds polling (30s intervals)
5. Trending bets by volume/price movement
6. Deep linking to source platforms
7. Odds format toggle (percentage, decimal, fractional)
8. Expiry countdown timers
9. Volume & liquidity indicators
10. Rate limiting middleware

## Architecture
See codebase for full implementation details.
