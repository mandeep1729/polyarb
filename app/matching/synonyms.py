import re

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


def expand_synonyms(text: str) -> str:
    words = text.lower().split()
    expanded_words = list(words)

    for word in words:
        syns = SYNONYMS.get(word, [])
        for syn in syns:
            if syn not in expanded_words:
                expanded_words.append(syn)

    for i in range(len(words) - 1):
        bigram = f"{words[i]} {words[i + 1]}"
        syns = SYNONYMS.get(bigram, [])
        for syn in syns:
            if syn not in expanded_words:
                expanded_words.append(syn)

    for i in range(len(words) - 2):
        trigram = f"{words[i]} {words[i + 1]} {words[i + 2]}"
        syns = SYNONYMS.get(trigram, [])
        for syn in syns:
            if syn not in expanded_words:
                expanded_words.append(syn)

    return " ".join(expanded_words)
