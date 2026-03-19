from datetime import datetime

from rapidfuzz import fuzz

from app.matching.text import preprocess

WEIGHT_TFIDF = 0.50
WEIGHT_FUZZY = 0.25
WEIGHT_CATEGORY = 0.15
WEIGHT_TEMPORAL = 0.10

MAX_TEMPORAL_DAYS = 30.0


def score_pair(
    q1: str,
    q2: str,
    cat1: str | None,
    cat2: str | None,
    end1: datetime | None,
    end2: datetime | None,
    tfidf_score: float | None = None,
) -> float:
    if tfidf_score is None:
        tfidf_score = 0.0

    preprocessed_q1 = preprocess(q1)
    preprocessed_q2 = preprocess(q2)
    fuzzy_score = fuzz.token_sort_ratio(preprocessed_q1, preprocessed_q2) / 100.0

    category_score = 0.0
    if cat1 and cat2:
        if cat1.lower() == cat2.lower():
            category_score = 1.0
        elif _categories_related(cat1, cat2):
            category_score = 0.5

    temporal_score = _temporal_proximity(end1, end2)

    composite = (
        WEIGHT_TFIDF * tfidf_score
        + WEIGHT_FUZZY * fuzzy_score
        + WEIGHT_CATEGORY * category_score
        + WEIGHT_TEMPORAL * temporal_score
    )

    return min(composite, 1.0)


def _temporal_proximity(dt1: datetime | None, dt2: datetime | None) -> float:
    if dt1 is None or dt2 is None:
        return 0.5

    diff_days = abs((dt1 - dt2).total_seconds()) / 86400.0

    if diff_days == 0:
        return 1.0
    if diff_days >= MAX_TEMPORAL_DAYS:
        return 0.0

    return 1.0 - (diff_days / MAX_TEMPORAL_DAYS)


_RELATED_CATEGORIES: list[set[str]] = [
    {"politics", "elections", "government", "policy"},
    {"crypto", "cryptocurrency", "defi", "blockchain", "web3"},
    {"economics", "finance", "markets", "stocks", "fed"},
    {"sports", "football", "basketball", "baseball", "hockey", "soccer"},
    {"technology", "tech", "ai", "software"},
    {"entertainment", "media", "movies", "music"},
    {"climate", "weather", "environment"},
]


def _categories_related(cat1: str, cat2: str) -> bool:
    c1 = cat1.lower()
    c2 = cat2.lower()
    for group in _RELATED_CATEGORIES:
        if c1 in group and c2 in group:
            return True
    return False
