"""Single source of truth for category mapping and inference.

Frontend sends title-case names (e.g. "Finance"), but the DB stores
lowercase domain names (e.g. "economics"). This module bridges that gap
and provides keyword-based category inference for markets without one.
"""

import re

# Frontend display name (lowered) → DB category value
CATEGORY_MAP: dict[str, str] = {
    "politics": "politics",
    "crypto": "crypto",
    "sports": "sports",
    "finance": "economics",
    "entertainment": "entertainment",
    "science": "technology",
    "weather": "climate",
}

# DB category value → frontend display name
DISPLAY_NAMES: dict[str, str] = {v: k.title() for k, v in CATEGORY_MAP.items()}

# All valid DB category values
VALID_DB_CATEGORIES = set(CATEGORY_MAP.values())

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "politics": [
        "election", "president", "congress", "senate", "governor", "vote",
        "trump", "biden", "democrat", "republican", "parliament", "cabinet",
        "impeach", "poll", "party", "legislation", "white house", "potus",
        "vp", "vice president", "primary", "electoral", "ballot",
    ],
    "crypto": [
        "bitcoin", "btc", "ethereum", "eth", "crypto", "defi", "solana",
        "token", "blockchain", "nft", "coinbase", "binance", "dogecoin",
        "ripple", "xrp", "cardano", "polygon", "matic", "stablecoin",
    ],
    "sports": [
        "nfl", "nba", "mlb", "nhl", "super bowl", "world series",
        "championship", "playoffs", "world cup", "olympics", "ufc",
        "boxing", "tennis", "f1", "premier league", "mvp", "march madness",
        "formula 1", "grand prix", "la liga", "bundesliga", "serie a",
        "champions league", "copa america", "euro 2026",
    ],
    "economics": [
        "fed", "inflation", "gdp", "unemployment", "interest rate", "cpi",
        "recession", "stock", "s&p", "nasdaq", "dow", "treasury", "tariff",
        "trade war", "oil price", "gas price", "housing", "jobs report",
        "federal reserve", "fomc", "rate cut", "rate hike", "ipo",
    ],
    "technology": [
        "ai", "tech", "apple", "google", "microsoft", "spacex", "openai",
        "chatgpt", "nvidia", "semiconductor", "chip", "robot", "quantum",
        "tiktok", "meta", "amazon", "tesla", "self-driving", "starship",
    ],
    "entertainment": [
        "oscar", "emmy", "grammy", "box office", "movie", "netflix",
        "spotify", "album", "tv show", "celebrity", "reality tv",
        "disney", "hulu", "streaming", "billboard", "concert",
    ],
    "climate": [
        "temperature", "hurricane", "weather", "climate", "drought", "flood",
        "wildfire", "tornado", "earthquake", "storm", "el nino",
        "la nina", "sea level", "carbon", "emissions", "heatwave",
    ],
}


def resolve_category(frontend_value: str | None) -> str | None:
    """Map a frontend category name to its DB value. Case-insensitive.

    Returns None if the value doesn't map to a known category.
    """
    if not frontend_value:
        return None
    return CATEGORY_MAP.get(frontend_value.lower())


# Pre-compile regex patterns for each category (word-boundary matching)
_CATEGORY_PATTERNS: dict[str, re.Pattern] = {
    cat: re.compile(
        r"\b(?:" + "|".join(re.escape(kw) for kw in keywords) + r")\b",
        re.IGNORECASE,
    )
    for cat, keywords in CATEGORY_KEYWORDS.items()
}


def infer_category(
    question: str,
    description: str | None = None,
    event_ticker: str | None = None,
) -> str | None:
    """Infer a category from free-text fields using keyword matching.

    Uses word-boundary regex to avoid false positives (e.g. "inflation" matching "nfl").
    Checks question, description, and event_ticker against the keyword lists.
    Returns the first matching DB category, or None.
    """
    parts = [
        question or "",
        description or "",
        event_ticker or "",
    ]
    combined = " ".join(parts)

    for cat, pattern in _CATEGORY_PATTERNS.items():
        if pattern.search(combined):
            return cat

    return None
