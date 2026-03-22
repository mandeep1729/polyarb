import pickle
import re
import string
from pathlib import Path

import structlog
from scipy.sparse import spmatrix, vstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.matching.synonyms import expand_synonyms

logger = structlog.get_logger()

_PUNCTUATION_RE = re.compile(f"[{re.escape(string.punctuation)}]")

STOP_WORDS = frozenset({
    "will", "the", "be", "to", "of", "in", "a", "an", "is", "are",
    "was", "were", "by", "for", "on", "at", "or", "and", "that",
    "this", "it", "from", "as", "with", "has", "have", "had", "do",
    "does", "did", "but", "not", "what", "which", "who", "whom",
    "when", "where", "how", "than", "before", "after", "above",
    "below", "between", "during", "through",
})

_TFIDF_CACHE_PATH = Path("data/tfidf_cache.pkl")
_REFIT_THRESHOLD = 0.10  # refit when >10% of corpus is new


def preprocess(text: str, category: str | None = None) -> str:
    text = text.lower()
    text = _PUNCTUATION_RE.sub(" ", text)
    if category and category.lower() == "politics":
        text = text.replace("shut down", "shutdown")
    text = expand_synonyms(text)
    tokens = text.split()
    tokens = [t for t in tokens if t not in STOP_WORDS and len(t) > 1]
    return " ".join(tokens)


def build_tfidf_matrix(
    documents: list[str],
) -> tuple[spmatrix, TfidfVectorizer]:
    """Build TF-IDF matrix from scratch (full fit_transform)."""
    vectorizer = TfidfVectorizer(
        max_features=10000,
        ngram_range=(1, 2),
        sublinear_tf=True,
        min_df=1,
    )
    matrix = vectorizer.fit_transform(documents)
    return matrix, vectorizer


def build_tfidf_matrix_incremental(
    documents: list[str],
    market_ids: list[int],
) -> tuple[spmatrix, TfidfVectorizer, list[int], set[int]]:
    """Build TF-IDF matrix with caching. Returns (matrix, vectorizer, ordered_ids, new_ids).

    On first run or when >10% of markets are new: full fit_transform + cache.
    On subsequent runs: load cached vectorizer, transform only new markets,
    append to cached matrix. IDF weights from the original fit are reused
    (acceptable drift for a few hundred new docs in a 55k corpus).
    """
    cache = _load_tfidf_cache()

    if cache is not None:
        cached_vectorizer, cached_matrix, cached_ids = cache
        cached_id_set = set(cached_ids)
        current_id_set = set(market_ids)

        # Find new markets not in cache
        new_indices = [i for i, mid in enumerate(market_ids) if mid not in cached_id_set]
        # Find cached markets that are still active (preserve their order)
        surviving_cached_indices = [i for i, mid in enumerate(cached_ids) if mid in current_id_set]

        new_ratio = len(new_indices) / max(len(market_ids), 1)

        if new_ratio > _REFIT_THRESHOLD or not surviving_cached_indices:
            # Too much drift — full refit
            logger.info(
                "tfidf_full_refit",
                new_ratio=round(new_ratio, 3),
                total=len(market_ids),
                new=len(new_indices),
            )
            matrix, vectorizer = build_tfidf_matrix(documents)
            _save_tfidf_cache(vectorizer, matrix, market_ids)
            return matrix, vectorizer, market_ids, set(market_ids)

        if not new_indices:
            # No new markets — rebuild matrix from cache for surviving markets only
            logger.info("tfidf_cache_hit", cached=len(surviving_cached_indices), new=0)
            # Reindex: build matrix rows for current market_ids from cache
            # Map cached_id -> cached row index
            cached_id_to_row = {mid: i for i, mid in enumerate(cached_ids)}
            row_indices = [cached_id_to_row[mid] for mid in market_ids if mid in cached_id_to_row]
            matrix = cached_matrix[row_indices]
            ordered_ids = [mid for mid in market_ids if mid in cached_id_to_row]
            return matrix, cached_vectorizer, ordered_ids, set()

        # Incremental: transform new markets, combine with cached
        logger.info(
            "tfidf_incremental",
            cached=len(surviving_cached_indices),
            new=len(new_indices),
        )
        new_docs = [documents[i] for i in new_indices]
        new_market_ids = [market_ids[i] for i in new_indices]
        new_matrix = cached_vectorizer.transform(new_docs)

        # Rebuild: cached surviving rows + new rows
        cached_id_to_row = {mid: i for i, mid in enumerate(cached_ids)}
        surviving_rows = cached_matrix[[cached_id_to_row[mid] for mid in market_ids if mid in cached_id_to_row]]
        surviving_ids = [mid for mid in market_ids if mid in cached_id_to_row]

        combined_matrix = vstack([surviving_rows, new_matrix])
        combined_ids = surviving_ids + new_market_ids

        _save_tfidf_cache(cached_vectorizer, combined_matrix, combined_ids)
        return combined_matrix, cached_vectorizer, combined_ids, set(new_market_ids)

    # No cache — full fit
    logger.info("tfidf_cold_start", total=len(market_ids))
    matrix, vectorizer = build_tfidf_matrix(documents)
    _save_tfidf_cache(vectorizer, matrix, market_ids)
    return matrix, vectorizer, market_ids, set(market_ids)


def _load_tfidf_cache() -> tuple[TfidfVectorizer, spmatrix, list[int]] | None:
    if not _TFIDF_CACHE_PATH.exists():
        return None
    try:
        with open(_TFIDF_CACHE_PATH, "rb") as f:
            data = pickle.load(f)
        return data["vectorizer"], data["matrix"], data["market_ids"]
    except Exception as exc:
        logger.warning("tfidf_cache_load_failed", error=str(exc))
        return None


def _save_tfidf_cache(vectorizer: TfidfVectorizer, matrix: spmatrix, market_ids: list[int]) -> None:
    _TFIDF_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(_TFIDF_CACHE_PATH, "wb") as f:
            pickle.dump({"vectorizer": vectorizer, "matrix": matrix, "market_ids": market_ids}, f)
        logger.info("tfidf_cache_saved", markets=len(market_ids))
    except Exception as exc:
        logger.warning("tfidf_cache_save_failed", error=str(exc))


def get_candidates(
    query_vec: spmatrix,
    corpus_matrix: spmatrix,
    threshold: float = 0.3,
) -> list[tuple[int, float]]:
    similarities = cosine_similarity(query_vec, corpus_matrix).flatten()

    candidates = []
    for idx, score in enumerate(similarities):
        if score >= threshold:
            candidates.append((idx, float(score)))

    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates
