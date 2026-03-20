"""Tests for PolymarketConnector.normalize() category inference."""

from app.connectors.polymarket import PolymarketConnector


def _make_connector() -> PolymarketConnector:
    """Create a PolymarketConnector without hitting real APIs."""
    connector = object.__new__(PolymarketConnector)
    return connector


class TestNormalizeCategoryInference:
    def setup_method(self):
        self.connector = _make_connector()

    def test_explicit_category_preserved(self):
        raw = {
            "condition_id": "abc",
            "question": "Will it rain?",
            "category": "weather_custom",
            "outcomes": '["Yes","No"]',
            "outcomePrices": '["0.5","0.5"]',
            "clobTokenIds": '["t1","t2"]',
        }
        result = self.connector.normalize(raw)
        assert result["category"] == "weather_custom"

    def test_tags_used_when_no_category(self):
        raw = {
            "condition_id": "abc",
            "question": "Something random",
            "tags": [{"label": "custom_tag"}],
            "outcomes": '["Yes","No"]',
            "outcomePrices": '["0.5","0.5"]',
            "clobTokenIds": '["t1","t2"]',
        }
        result = self.connector.normalize(raw)
        assert result["category"] == "custom_tag"

    def test_infer_fallback_when_no_category_or_tags(self):
        raw = {
            "condition_id": "abc",
            "question": "Will Bitcoin hit $200k?",
            "outcomes": '["Yes","No"]',
            "outcomePrices": '["0.3","0.7"]',
            "clobTokenIds": '["t1","t2"]',
        }
        result = self.connector.normalize(raw)
        assert result["category"] == "crypto"

    def test_no_category_when_no_match(self):
        raw = {
            "condition_id": "abc",
            "question": "Something totally random",
            "outcomes": '["Yes","No"]',
            "outcomePrices": '["0.5","0.5"]',
            "clobTokenIds": '["t1","t2"]',
        }
        result = self.connector.normalize(raw)
        assert result["category"] is None

    def test_infer_from_description(self):
        raw = {
            "condition_id": "abc",
            "question": "Market XYZ",
            "description": "This is about the upcoming NBA season",
            "outcomes": '["Yes","No"]',
            "outcomePrices": '["0.5","0.5"]',
            "clobTokenIds": '["t1","t2"]',
        }
        result = self.connector.normalize(raw)
        assert result["category"] == "sports"
