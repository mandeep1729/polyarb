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


class TestNormalizeEventMetadata:
    """Tests for normalize() with injected event metadata from event-first fetch."""

    def setup_method(self):
        self.connector = _make_connector()

    def test_event_slug_used_for_deep_link(self):
        raw = {
            "condition_id": "cond1",
            "question": "Will X happen?",
            "slug": "will-x-happen",
            "_event_slug": "x-event",
            "outcomes": '["Yes","No"]',
            "outcomePrices": '["0.6","0.4"]',
            "clobTokenIds": '["t1","t2"]',
            "active": True,
        }
        result = self.connector.normalize(raw)
        assert result["deep_link_url"] == "https://polymarket.com/event/x-event"
        assert result["event_ticker"] == "x-event"

    def test_event_tags_used_for_category(self):
        raw = {
            "condition_id": "cond2",
            "question": "Something random",
            "_event_tags": [{"label": "Politics"}],
            "outcomes": '["Yes","No"]',
            "outcomePrices": '["0.5","0.5"]',
            "clobTokenIds": '["t1","t2"]',
        }
        result = self.connector.normalize(raw)
        assert result["category"] == "Politics"

    def test_event_tags_string_labels(self):
        raw = {
            "condition_id": "cond3",
            "question": "Something random",
            "_event_tags": ["Sports"],
            "outcomes": '["Yes","No"]',
            "outcomePrices": '["0.5","0.5"]',
            "clobTokenIds": '["t1","t2"]',
        }
        result = self.connector.normalize(raw)
        assert result["category"] == "Sports"

    def test_event_image_used(self):
        raw = {
            "condition_id": "cond4",
            "question": "Will Y happen?",
            "_event_image": "https://example.com/event.png",
            "image": "https://example.com/market.png",
            "outcomes": '["Yes","No"]',
            "outcomePrices": '["0.5","0.5"]',
            "clobTokenIds": '["t1","t2"]',
        }
        result = self.connector.normalize(raw)
        assert result["image_url"] == "https://example.com/event.png"

    def test_fallback_to_market_image_when_no_event_image(self):
        raw = {
            "condition_id": "cond5",
            "question": "Will Z happen?",
            "image": "https://example.com/market.png",
            "outcomes": '["Yes","No"]',
            "outcomePrices": '["0.5","0.5"]',
            "clobTokenIds": '["t1","t2"]',
        }
        result = self.connector.normalize(raw)
        assert result["image_url"] == "https://example.com/market.png"

    def test_fallback_to_legacy_events_array(self):
        """When no _event_slug injected, fall back to events[0].slug."""
        raw = {
            "condition_id": "cond6",
            "question": "Legacy market?",
            "events": [{"slug": "legacy-event"}],
            "outcomes": '["Yes","No"]',
            "outcomePrices": '["0.5","0.5"]',
            "clobTokenIds": '["t1","t2"]',
            "active": True,
        }
        result = self.connector.normalize(raw)
        assert result["deep_link_url"] == "https://polymarket.com/event/legacy-event"
        assert result["event_ticker"] == "legacy-event"

    def test_fallback_to_slug_when_no_event_data(self):
        """When no _event_slug and no events array, fall back to market slug."""
        raw = {
            "condition_id": "cond7",
            "question": "Bare market?",
            "slug": "bare-market-slug",
            "outcomes": '["Yes","No"]',
            "outcomePrices": '["0.5","0.5"]',
            "clobTokenIds": '["t1","t2"]',
            "active": True,
        }
        result = self.connector.normalize(raw)
        assert result["deep_link_url"] == "https://polymarket.com/event/bare-market-slug"
        assert result["event_ticker"] == "bare-market-slug"

    def test_event_tags_override_market_tags(self):
        """_event_tags should be preferred over raw tags."""
        raw = {
            "condition_id": "cond8",
            "question": "Tag priority test",
            "_event_tags": [{"label": "EventTag"}],
            "tags": [{"label": "MarketTag"}],
            "outcomes": '["Yes","No"]',
            "outcomePrices": '["0.5","0.5"]',
            "clobTokenIds": '["t1","t2"]',
        }
        result = self.connector.normalize(raw)
        assert result["category"] == "EventTag"

    def test_explicit_category_overrides_event_tags(self):
        """Explicit category field still wins over _event_tags."""
        raw = {
            "condition_id": "cond9",
            "question": "Category priority test",
            "category": "explicit_cat",
            "_event_tags": [{"label": "EventTag"}],
            "outcomes": '["Yes","No"]',
            "outcomePrices": '["0.5","0.5"]',
            "clobTokenIds": '["t1","t2"]',
        }
        result = self.connector.normalize(raw)
        assert result["category"] == "explicit_cat"
