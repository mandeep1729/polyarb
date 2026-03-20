"""Tests for KalshiConnector.normalize() category inference using shared module."""

from app.connectors.kalshi import KalshiConnector


def _make_connector() -> KalshiConnector:
    """Create a KalshiConnector without hitting real APIs."""
    connector = object.__new__(KalshiConnector)
    return connector


class TestNormalizeCategoryInference:
    def setup_method(self):
        self.connector = _make_connector()

    def test_explicit_category_preserved(self):
        """When raw data has a category, it should be used as-is."""
        raw = {
            "ticker": "TEST",
            "title": "Test market",
            "category": "custom_category",
            "status": "open",
        }
        result = self.connector.normalize(raw)
        assert result["category"] == "custom_category"

    def test_infers_politics_from_title(self):
        """Category inferred from title when not provided."""
        raw = {
            "ticker": "ELECTION-2026",
            "title": "Will the election result be contested?",
            "event_ticker": "ELECTION-2026",
            "status": "open",
        }
        result = self.connector.normalize(raw)
        assert result["category"] == "politics"

    def test_infers_crypto_from_title(self):
        raw = {
            "ticker": "BTC-100K",
            "title": "Will Bitcoin exceed $100k?",
            "event_ticker": "BTC-100K",
            "status": "open",
        }
        result = self.connector.normalize(raw)
        assert result["category"] == "crypto"

    def test_infers_from_subtitle(self):
        """Subtitle (description) should also contribute to inference."""
        raw = {
            "ticker": "TEST-123",
            "title": "Market about something",
            "subtitle": "Related to the NBA season",
            "event_ticker": "TEST-123",
            "status": "open",
        }
        result = self.connector.normalize(raw)
        assert result["category"] == "sports"

    def test_infers_from_event_ticker(self):
        """Event ticker should contribute to inference."""
        raw = {
            "ticker": "FED-RATE",
            "title": "Some market question",
            "event_ticker": "FED-RATE-DECISION",
            "status": "open",
        }
        result = self.connector.normalize(raw)
        assert result["category"] == "economics"

    def test_no_category_when_no_match(self):
        raw = {
            "ticker": "RANDOM",
            "title": "Something completely unrelated",
            "status": "open",
        }
        result = self.connector.normalize(raw)
        assert result["category"] is None

    def test_inflation_not_matched_as_nfl(self):
        """Word boundary: 'inflation' should not trigger 'nfl' sports match."""
        raw = {
            "ticker": "INFLATION",
            "title": "Will inflation exceed 4%?",
            "event_ticker": "INFLATION",
            "status": "open",
        }
        result = self.connector.normalize(raw)
        assert result["category"] == "economics"
