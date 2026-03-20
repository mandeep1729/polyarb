import json
import re
from pathlib import Path

CUSTOM_SYNONYMS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "custom_synonyms.json"

SYNONYMS: dict[str, list[str]] = {
    # Crypto
    "btc": ["bitcoin"],
    "bitcoin": ["btc"],
    "eth": ["ethereum"],
    "ethereum": ["eth"],
    "sol": ["solana"],
    "solana": ["sol"],
    "xrp": ["ripple"],
    "ripple": ["xrp"],
    "doge": ["dogecoin"],
    "dogecoin": ["doge"],
    "ada": ["cardano"],
    "cardano": ["ada"],
    "bnb": ["binance coin"],
    "defi": ["decentralized finance"],
    "nft": ["non-fungible token"],
    "cbdc": ["central bank digital currency"],
    # Politics - US
    "potus": ["president", "president of the united states"],
    "president": ["potus"],
    "gop": ["republican", "republicans"],
    "republican": ["gop"],
    "dem": ["democrat", "democratic"],
    "democrat": ["dem", "democratic"],
    "scotus": ["supreme court"],
    "supreme court": ["scotus"],
    "vp": ["vice president"],
    "vice president": ["vp"],
    "house": ["house of representatives"],
    "senate": ["upper chamber"],
    # Economics / Fed
    "fed": ["federal reserve", "fomc"],
    "federal reserve": ["fed", "fomc"],
    "fomc": ["fed", "federal reserve"],
    "cpi": ["consumer price index", "inflation"],
    "inflation": ["cpi"],
    "gdp": ["gross domestic product"],
    "nonfarm": ["nfp", "non-farm payrolls"],
    "unemployment": ["jobless"],
    "rate cut": ["interest rate decrease"],
    "rate hike": ["interest rate increase"],
    # Sports
    "nfl": ["football", "national football league"],
    "nba": ["basketball", "national basketball association"],
    "mlb": ["baseball", "major league baseball"],
    "nhl": ["hockey", "national hockey league"],
    "epl": ["premier league", "english premier league"],
    "ucl": ["champions league"],
    "world cup": ["fifa world cup"],
    "super bowl": ["sb"],
    # Tech
    "ai": ["artificial intelligence"],
    "artificial intelligence": ["ai"],
    "agi": ["artificial general intelligence"],
    "llm": ["large language model"],
    "spacex": ["space exploration technologies"],
    "tsla": ["tesla"],
    "tesla": ["tsla"],
    # Geopolitics
    "uk": ["united kingdom", "britain"],
    "us": ["united states", "america", "usa"],
    "eu": ["european union"],
    "nato": ["north atlantic treaty organization"],
    "un": ["united nations"],
}

_WORD_BOUNDARY = re.compile(r"\b(\w+)\b")


def load_custom_synonyms() -> list[list[str]]:
    """Load custom synonym groups from JSON file.

    Returns list of equivalence groups, e.g. [["crude", "wti", "west texas intermediate"]].
    Returns empty list if file is missing or empty.
    """
    if not CUSTOM_SYNONYMS_PATH.exists():
        return []
    text = CUSTOM_SYNONYMS_PATH.read_text().strip()
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


def get_builtin_synonym_groups() -> list[list[str]]:
    """Convert the hardcoded SYNONYMS dict to list-of-lists format for display."""
    visited: set[str] = set()
    groups: list[list[str]] = []
    for word, syns in SYNONYMS.items():
        if word in visited:
            continue
        group = {word}
        group.update(syns)
        visited.update(group)
        groups.append(sorted(group))
    return groups


def get_all_synonyms() -> dict[str, list[str]]:
    """Merge hardcoded SYNONYMS with custom synonyms from JSON file."""
    merged = dict(SYNONYMS)
    custom_groups = load_custom_synonyms()
    custom_dict = _groups_to_dict(custom_groups)
    for word, syns in custom_dict.items():
        if word in merged:
            for s in syns:
                if s not in merged[word]:
                    merged[word].append(s)
        else:
            merged[word] = list(syns)
    return merged


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
