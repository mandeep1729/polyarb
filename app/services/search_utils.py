"""Shared full-text search utilities."""

from app.matching.synonyms import get_all_synonyms


def build_tsquery(query: str) -> str:
    """Build a tsquery string: AND between terms, OR with each term's synonyms.

    "Crude Oil"  → "(crude | oil | wti | brent) & (oil | crude | wti | brent)"
    "bitcoin price" → "(bitcoin | btc) & price"
    "fed rate"   → "(fed | federal | reserve | fomc) & rate"
    """
    words = query.lower().split()
    if not words:
        return query

    all_synonyms = get_all_synonyms()
    groups = []
    for word in words:
        synonyms = all_synonyms.get(word, [])
        # Flatten multi-word synonyms into individual tsquery terms
        all_terms = [word]
        for syn in synonyms:
            all_terms.extend(syn.split())
        # Deduplicate while preserving order
        seen = set()
        unique = []
        for t in all_terms:
            if t not in seen:
                seen.add(t)
                unique.append(t)
        if len(unique) == 1:
            groups.append(unique[0])
        else:
            groups.append("(" + " | ".join(unique) + ")")

    return " & ".join(groups)


def build_exclude_tsquery(query: str) -> str:
    """Build OR tsquery for exclusion: 'trump biden' -> '(trump) | (biden)'.

    Used with NOT: WHERE NOT ts_vector @@ to_tsquery('english', result)
    """
    words = query.lower().split()
    if not words:
        return ""

    all_synonyms = get_all_synonyms()
    groups = []
    for word in words:
        synonyms = all_synonyms.get(word, [])
        all_terms = [word]
        for syn in synonyms:
            all_terms.extend(syn.split())
        seen: set[str] = set()
        unique: list[str] = []
        for t in all_terms:
            if t not in seen:
                seen.add(t)
                unique.append(t)
        groups.append("(" + " | ".join(unique) + ")")

    return " | ".join(groups)
