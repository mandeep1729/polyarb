import re
import string

from scipy.sparse import spmatrix
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.matching.synonyms import expand_synonyms

_PUNCTUATION_RE = re.compile(f"[{re.escape(string.punctuation)}]")

STOP_WORDS = frozenset({
    "will", "the", "be", "to", "of", "in", "a", "an", "is", "are",
    "was", "were", "by", "for", "on", "at", "or", "and", "that",
    "this", "it", "from", "as", "with", "has", "have", "had", "do",
    "does", "did", "but", "not", "what", "which", "who", "whom",
    "when", "where", "how", "than", "before", "after", "above",
    "below", "between", "during", "through",
})


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
    vectorizer = TfidfVectorizer(
        max_features=10000,
        ngram_range=(1, 2),
        sublinear_tf=True,
        min_df=1,
    )
    matrix = vectorizer.fit_transform(documents)
    return matrix, vectorizer


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
