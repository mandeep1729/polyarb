"""Tests for KalshiConnector.normalize() outcome labeling."""

from app.connectors.kalshi import KalshiConnector


def _make_connector() -> KalshiConnector:
    """Create a KalshiConnector without hitting real APIs.

    normalize() is a pure transformation method that doesn't use any
    instance attributes, so we bypass __init__ entirely.
    """
    connector = object.__new__(KalshiConnector)
    return connector


class TestNormalizeOutcomes:
    def setup_method(self):
        self.connector = _make_connector()

    def test_plain_binary_market_uses_yes_no(self):
        """Markets without yes_sub_title should use 'Yes'/'No' labels."""
        raw = {
            "ticker": "PLAIN-BINARY",
            "title": "Will it rain tomorrow?",
            "yes_bid": 0.65,
            "no_bid": 0.35,
            "status": "open",
        }
        result = self.connector.normalize(raw)

        assert result["outcomes"] == {"Yes": "yes", "No": "no"}
        assert result["outcome_prices"] == {"Yes": 0.65, "No": 0.35}

    def test_multi_outcome_market_uses_sub_titles(self):
        """Markets with yes_sub_title should use candidate names as labels."""
        raw = {
            "ticker": "POPE-PAROLIN",
            "title": "Who will be the next Pope?",
            "event_ticker": "POPE",
            "yes_sub_title": "Pietro Parolin",
            "no_sub_title": "Not Pietro Parolin",
            "yes_bid": 0.11,
            "no_bid": 0.89,
            "status": "open",
        }
        result = self.connector.normalize(raw)

        assert result["outcomes"] == {"Pietro Parolin": "yes", "Not Pietro Parolin": "no"}
        assert result["outcome_prices"] == {"Pietro Parolin": 0.11, "Not Pietro Parolin": 0.89}

    def test_sub_title_yes_only_infers_no_price(self):
        """When only yes_bid is present, no price should be inferred."""
        raw = {
            "ticker": "MVP-JOKIC",
            "title": "NBA MVP 2025-26",
            "yes_sub_title": "Nikola Jokic",
            "no_sub_title": "Not Nikola Jokic",
            "yes_bid": 0.30,
            "status": "open",
        }
        result = self.connector.normalize(raw)

        assert result["outcome_prices"]["Nikola Jokic"] == 0.30
        assert result["outcome_prices"]["Not Nikola Jokic"] == 0.70

    def test_plain_binary_infers_missing_no_price(self):
        """Plain binary market should still infer missing No price."""
        raw = {
            "ticker": "RAIN-2025",
            "title": "Will it rain?",
            "yes_bid": 0.40,
            "status": "open",
        }
        result = self.connector.normalize(raw)

        assert result["outcomes"] == {"Yes": "yes", "No": "no"}
        assert result["outcome_prices"] == {"Yes": 0.40, "No": 0.60}

    def test_yes_sub_title_only_defaults_no_label(self):
        """If yes_sub_title is set but no_sub_title is absent, no_label falls back to 'No'."""
        raw = {
            "ticker": "TEST-123",
            "title": "Test market",
            "yes_sub_title": "Candidate A",
            "yes_bid": 0.50,
            "no_bid": 0.50,
            "status": "open",
        }
        result = self.connector.normalize(raw)

        assert result["outcomes"] == {"Candidate A": "yes", "No": "no"}
        assert result["outcome_prices"] == {"Candidate A": 0.50, "No": 0.50}
