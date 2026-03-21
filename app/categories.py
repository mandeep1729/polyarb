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

# Broader tag aliases → canonical DB category (used by resolve_tag)
_TAG_ALIASES: dict[str, str] = {
    # economics
    "economy": "economics",
    "equities": "economics",
    "commodities": "economics",
    "derivatives": "economics",
    "earnings": "economics",
    "macro indicators": "economics",
    "global rates": "economics",
    "up or down": "economics",
    "indicies": "economics",
    "interest rate": "economics",
    "interest rates": "economics",
    "fed rates": "economics",
    "global gdp": "economics",
    "housing": "economics",
    "business": "economics",
    "s&p 500": "economics",
    "volatility": "economics",
    "foreign exchange": "economics",
    # crypto
    "crypto prices": "crypto",
    "stablecoins": "crypto",
    "bitcoin": "crypto",
    "ethereum": "crypto",
    "solana": "crypto",
    "xrp": "crypto",
    "dogecoin": "crypto",
    "bnb": "crypto",
    # sports
    "nba": "sports",
    "nfl": "sports",
    "nhl": "sports",
    "mlb": "sports",
    "mls": "sports",
    "ufc": "sports",
    "soccer": "sports",
    "tennis": "sports",
    "hockey": "sports",
    "basketball": "sports",
    "baseball": "sports",
    "cricket": "sports",
    "formula 1": "sports",
    "premier league": "sports",
    "la liga": "sports",
    "serie a": "sports",
    "serie b": "sports",
    "ligue 1": "sports",
    "champions league": "sports",
    "esports": "sports",
    "efl cup": "sports",
    "wta": "sports",
    # politics
    "elections": "politics",
    "world elections": "politics",
    "global elections": "politics",
    "geopolitics": "politics",
    "congress": "politics",
    "senate": "politics",
    # entertainment
    "culture": "entertainment",
    "movies": "entertainment",
    "music": "entertainment",
    "games": "entertainment",
    "netflix": "entertainment",
    # climate
    "weather & science": "climate",
    "precipitation": "climate",
    "daily temperature": "climate",
    # technology
    "ai": "technology",
    "space": "technology",
}

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
        "economy", "finance", "equities", "commodities", "derivatives",
        "earnings", "nonfarm payroll", "crude oil",
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


def resolve_tag(tag_label: str) -> str | None:
    """Map a raw platform tag to a canonical DB category. Case-insensitive.

    Checks CATEGORY_MAP first (handles "Finance" → "economics"), then
    _TAG_ALIASES for broader tag synonyms (handles "Economy" → "economics").
    Returns None if the tag doesn't map to any known category.
    """
    if not tag_label:
        return None
    key = tag_label.lower().strip()
    # Already a canonical DB category?
    if key in VALID_DB_CATEGORIES:
        return key
    return CATEGORY_MAP.get(key) or _TAG_ALIASES.get(key)


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
