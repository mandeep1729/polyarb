from datetime import datetime

from rapidfuzz import fuzz

from app.config import settings
from app.matching.text import preprocess

WEIGHT_TFIDF = 0.30
WEIGHT_DESC_TFIDF = 0.15
WEIGHT_FUZZY = 0.25
WEIGHT_CATEGORY = 0.10
WEIGHT_TEMPORAL = 0.20

MAX_TEMPORAL_DAYS = 1.0


def _end_date_gate(dt1: datetime | None, dt2: datetime | None) -> bool:
    """Hard gate: both dates must match temporal equivalence.

    Returns True if both are None, or both are present and within
    GROUP_END_DATE_GATE_DAYS of each other. Returns False if one is
    None and the other isn't, or if they differ by more than the gate.
    """
    if dt1 is None and dt2 is None:
        return True
    if dt1 is None or dt2 is None:
        return False
    diff_days = abs((dt1 - dt2).total_seconds()) / 86400.0
    return diff_days <= settings.GROUP_END_DATE_GATE_DAYS


def score_pair(
    q1: str,
    q2: str,
    cat1: str | None,
    cat2: str | None,
    end1: datetime | None,
    end2: datetime | None,
    desc1: str | None = None,
    desc2: str | None = None,
    tfidf_score: float | None = None,
    desc_tfidf_score: float | None = None,
) -> float:
    """Compute composite similarity score for a pair of markets/groups.

    Returns 0.0 immediately if the end_date hard gate fails.
    Otherwise computes a weighted composite of question TF-IDF,
    description TF-IDF, fuzzy match, category, and temporal signals.
    """
    if not _end_date_gate(end1, end2):
        return 0.0

    if tfidf_score is None:
        tfidf_score = 0.0

    if desc_tfidf_score is None:
        desc_tfidf_score = _description_similarity(desc1, desc2)

    preprocessed_q1 = preprocess(q1, category=cat1)
    preprocessed_q2 = preprocess(q2, category=cat2)
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
        + WEIGHT_DESC_TFIDF * desc_tfidf_score
        + WEIGHT_FUZZY * fuzzy_score
        + WEIGHT_CATEGORY * category_score
        + WEIGHT_TEMPORAL * temporal_score
    )

    return min(composite, 1.0)


def _description_similarity(desc1: str | None, desc2: str | None) -> float:
    """Compute similarity between two descriptions.

    Returns 0.5 (neutral) if either description is missing or empty.
    Otherwise uses fuzzy token sort ratio as a lightweight proxy.
    """
    if not desc1 or not desc2:
        return 0.5
    d1 = preprocess(desc1)
    d2 = preprocess(desc2)
    if not d1 or not d2:
        return 0.5
    return fuzz.token_sort_ratio(d1, d2) / 100.0


def _temporal_proximity(dt1: datetime | None, dt2: datetime | None) -> float:
    """Fine-grained temporal proximity within the gate window.

    Since _end_date_gate already ensures dates are within MAX_TEMPORAL_DAYS,
    this gives a fine-grained score: 1.0 for same moment, 0.0 at the gate boundary.
    """
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
