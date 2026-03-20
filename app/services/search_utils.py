"""Shared full-text search utilities."""

from app.matching.synonyms import expand_synonyms


def build_or_tsquery(query: str) -> str:
    """Build a tsquery string that ORs the original terms with synonyms."""
    expanded = expand_synonyms(query.lower())
    terms = expanded.split()
    if not terms:
        return query
    return " | ".join(terms)
