"""Tests for the category mapping and inference module."""

from app.categories import (
    CATEGORY_KEYWORDS,
    CATEGORY_MAP,
    DISPLAY_NAMES,
    VALID_DB_CATEGORIES,
    infer_category,
    resolve_category,
    resolve_tag,
)


class TestCategoryMap:
    """Verify CATEGORY_MAP structure and consistency."""

    def test_all_values_are_valid_db_categories(self):
        for frontend_key, db_val in CATEGORY_MAP.items():
            assert db_val in VALID_DB_CATEGORIES, f"{frontend_key} -> {db_val} not in VALID_DB_CATEGORIES"

    def test_display_names_roundtrip(self):
        """Every DB category should have a display name, and it should be title-case."""
        for db_cat in VALID_DB_CATEGORIES:
            assert db_cat in DISPLAY_NAMES, f"Missing display name for {db_cat}"
            assert DISPLAY_NAMES[db_cat][0].isupper(), f"Display name not title-case: {DISPLAY_NAMES[db_cat]}"

    def test_display_names_correct_mapping(self):
        assert DISPLAY_NAMES["economics"] == "Finance"
        assert DISPLAY_NAMES["technology"] == "Science"
        assert DISPLAY_NAMES["climate"] == "Weather"
        assert DISPLAY_NAMES["politics"] == "Politics"

    def test_keyword_categories_match_valid_categories(self):
        """Every keyword category must be a valid DB category."""
        for cat in CATEGORY_KEYWORDS:
            assert cat in VALID_DB_CATEGORIES, f"Keyword category {cat} not in VALID_DB_CATEGORIES"

    def test_all_db_categories_have_keywords(self):
        """Every DB category should have at least one keyword."""
        for cat in VALID_DB_CATEGORIES:
            assert cat in CATEGORY_KEYWORDS, f"No keywords for DB category {cat}"
            assert len(CATEGORY_KEYWORDS[cat]) > 0


class TestResolveCategory:
    """Test resolve_category() frontend → DB mapping."""

    def test_none_input(self):
        assert resolve_category(None) is None

    def test_empty_string(self):
        assert resolve_category("") is None

    def test_exact_lowercase(self):
        assert resolve_category("politics") == "politics"
        assert resolve_category("crypto") == "crypto"
        assert resolve_category("sports") == "sports"
        assert resolve_category("finance") == "economics"
        assert resolve_category("entertainment") == "entertainment"
        assert resolve_category("science") == "technology"
        assert resolve_category("weather") == "climate"

    def test_title_case(self):
        """Frontend sends title-case values."""
        assert resolve_category("Politics") == "politics"
        assert resolve_category("Finance") == "economics"
        assert resolve_category("Science") == "technology"
        assert resolve_category("Weather") == "climate"

    def test_uppercase(self):
        assert resolve_category("POLITICS") == "politics"
        assert resolve_category("FINANCE") == "economics"

    def test_unknown_category(self):
        assert resolve_category("unknown") is None
        assert resolve_category("food") is None


class TestInferCategory:
    """Test infer_category() keyword matching."""

    def test_none_inputs(self):
        assert infer_category("", None, None) is None

    def test_politics_from_question(self):
        assert infer_category("Will Trump win the 2024 election?") == "politics"
        assert infer_category("Who will be the next president?") == "politics"
        assert infer_category("Will congress pass the bill?") == "politics"

    def test_crypto_from_question(self):
        assert infer_category("Will Bitcoin reach $100k?") == "crypto"
        assert infer_category("Ethereum price above $5000?") == "crypto"
        assert infer_category("Will Solana outperform ETH?") == "crypto"

    def test_sports_from_question(self):
        assert infer_category("Who will win the Super Bowl?") == "sports"
        assert infer_category("NBA MVP 2025-26") == "sports"
        assert infer_category("Will the UFC have a surprise upset?") == "sports"

    def test_economics_from_question(self):
        assert infer_category("Will inflation drop below 3%?") == "economics"
        assert infer_category("Fed interest rate decision") == "economics"
        assert infer_category("Will GDP growth exceed 2%?") == "economics"
        assert infer_category("Will the S&P 500 hit 6000?") == "economics"

    def test_technology_from_question(self):
        assert infer_category("Will OpenAI release GPT-5?") == "technology"
        assert infer_category("SpaceX Starship launch") == "technology"
        assert infer_category("Will Apple announce new AI features?") == "technology"

    def test_entertainment_from_question(self):
        assert infer_category("Who will win the Oscar for best picture?") == "entertainment"
        assert infer_category("Netflix subscriber count") == "entertainment"

    def test_climate_from_question(self):
        assert infer_category("Will there be a hurricane this season?") == "climate"
        assert infer_category("Average temperature in July") == "climate"
        assert infer_category("Will a wildfire affect California?") == "climate"

    def test_no_match(self):
        assert infer_category("Something completely random") is None
        assert infer_category("How many fish in the sea?") is None

    def test_description_fallback(self):
        """When question doesn't match, description should be checked."""
        assert infer_category("Market XYZ", description="bitcoin price forecast") == "crypto"

    def test_event_ticker_fallback(self):
        """Event ticker should also be checked."""
        assert infer_category("Market XYZ", event_ticker="ELECTION-2024") == "politics"

    def test_combined_text_checked(self):
        """All text fields are combined — first category in iteration order wins."""
        result = infer_category("Will Bitcoin crash?", description="election related")
        # politics comes before crypto in CATEGORY_KEYWORDS iteration order
        assert result == "politics"

    def test_case_insensitive(self):
        assert infer_category("BITCOIN PRICE") == "crypto"
        assert infer_category("SUPER BOWL winner") == "sports"

    def test_word_boundary_no_substring_match(self):
        """Keywords should not match as substrings of other words."""
        # "inflation" contains "nfl" but should not match sports
        assert infer_category("Will inflation drop below 3%?") == "economics"
        # "main" contains "ai" but should not match technology
        assert infer_category("What is the main question?") is None
        # "said" contains "ai" but should not match technology
        assert infer_category("He said something") is None

    def test_word_boundary_standalone_match(self):
        """Short keywords should match when standalone."""
        assert infer_category("Will the NFL expand?") == "sports"
        assert infer_category("AI is the future") == "technology"
        assert infer_category("CPI data released") == "economics"
        assert infer_category("F1 racing season") == "sports"

    def test_new_economics_keywords(self):
        assert infer_category("Economy growth forecast") == "economics"
        assert infer_category("Finance sector outlook") == "economics"
        assert infer_category("Crude oil prices surge") == "economics"


class TestResolveTag:
    """Test resolve_tag() for mapping raw platform tags to canonical categories."""

    def test_none_input(self):
        assert resolve_tag(None) is None

    def test_empty_string(self):
        assert resolve_tag("") is None

    def test_canonical_values_pass_through(self):
        assert resolve_tag("economics") == "economics"
        assert resolve_tag("politics") == "politics"
        assert resolve_tag("crypto") == "crypto"

    def test_frontend_names_resolve(self):
        assert resolve_tag("Finance") == "economics"
        assert resolve_tag("Sports") == "sports"
        assert resolve_tag("Weather") == "climate"
        assert resolve_tag("Science") == "technology"

    def test_tag_aliases(self):
        assert resolve_tag("Economy") == "economics"
        assert resolve_tag("Equities") == "economics"
        assert resolve_tag("Commodities") == "economics"
        assert resolve_tag("Derivatives") == "economics"
        assert resolve_tag("Up or Down") == "economics"
        assert resolve_tag("Crypto Prices") == "crypto"
        assert resolve_tag("NBA") == "sports"
        assert resolve_tag("Elections") == "politics"
        assert resolve_tag("Culture") == "entertainment"
        assert resolve_tag("Esports") == "sports"

    def test_case_insensitive(self):
        assert resolve_tag("ECONOMY") == "economics"
        assert resolve_tag("finance") == "economics"
        assert resolve_tag("UP OR DOWN") == "economics"

    def test_unknown_tag(self):
        assert resolve_tag("SomeRandomTag") is None
        assert resolve_tag("custom_tag") is None
