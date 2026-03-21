"""Synonym expansion for market matching and search.

All synonyms are loaded from config/custom_synonyms.json.
"""

import json
from pathlib import Path

SYNONYMS_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "custom_synonyms.json"


def load_synonym_groups() -> list[list[str]]:
    """Load synonym equivalence groups from JSON config.

    Returns list of equivalence groups, e.g. [["crude", "wti", "west texas intermediate"]].
    Returns empty list if file is missing or empty.
    """
    if not SYNONYMS_PATH.exists():
        return []
    text = SYNONYMS_PATH.read_text().strip()
    if not text:
        return []
    return json.loads(text)


def _groups_to_dict(groups: list[list[str]]) -> dict[str, list[str]]:
    """Convert list-of-lists equivalence groups to bidirectional synonym dict."""
    result: dict[str, list[str]] = {}
    for group in groups:
        for word in group:
            others = [w for w in group if w != word]
            if word in result:
                for o in others:
                    if o not in result[word]:
                        result[word].append(o)
            else:
                result[word] = others
    return result


def get_all_synonyms() -> dict[str, list[str]]:
    """Load all synonyms from config as a bidirectional lookup dict."""
    return _groups_to_dict(load_synonym_groups())


def expand_synonyms(text: str) -> str:
    """Expand text with synonym equivalences (unigram, bigram, trigram)."""
    all_syns = get_all_synonyms()
    words = text.lower().split()
    expanded_words = list(words)

    for word in words:
        syns = all_syns.get(word, [])
        for syn in syns:
            if syn not in expanded_words:
                expanded_words.append(syn)

    for i in range(len(words) - 1):
        bigram = f"{words[i]} {words[i + 1]}"
        syns = all_syns.get(bigram, [])
        for syn in syns:
            if syn not in expanded_words:
                expanded_words.append(syn)

    for i in range(len(words) - 2):
        trigram = f"{words[i]} {words[i + 1]} {words[i + 2]}"
        syns = all_syns.get(trigram, [])
        for syn in syns:
            if syn not in expanded_words:
                expanded_words.append(syn)

    return " ".join(expanded_words)
