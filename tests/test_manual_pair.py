"""Tests for manual/LLM-verified market pairing and arbitrage endpoints."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.services.arbitrage_service import ArbitrageService
from app.tasks.llm_candidates import build_llm_prompt


@pytest_asyncio.fixture
async def api_client():
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestManualPairEndpoint:
    @pytest.mark.asyncio
    async def test_same_market_id_rejected(self, api_client: AsyncClient):
        resp = await api_client.post(
            "/api/v1/arbitrage/pair",
            json={"market_a_id": 1, "market_b_id": 1},
        )
        assert resp.status_code == 400
        assert "different" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_nonexistent_market_rejected(self, api_client: AsyncClient):
        resp = await api_client.post(
            "/api/v1/arbitrage/pair",
            json={"market_a_id": 999999, "market_b_id": 999998},
        )
        assert resp.status_code == 400
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_missing_fields_rejected(self, api_client: AsyncClient):
        resp = await api_client.post(
            "/api/v1/arbitrage/pair",
            json={"market_a_id": 1},
        )
        assert resp.status_code == 422


class TestComputeOddsDelta:
    """Unit tests for the static delta computation."""

    def test_common_outcomes(self):
        prices_a = {"Yes": "0.65", "No": "0.35"}
        prices_b = {"Yes": "0.55", "No": "0.45"}
        delta = ArbitrageService._compute_odds_delta(prices_a, prices_b)
        assert abs(delta - 0.1) < 1e-6

    def test_no_common_outcomes_with_yes_keys(self):
        prices_a = {"Yes": "0.70"}
        prices_b = {"True": "0.60"}
        delta = ArbitrageService._compute_odds_delta(prices_a, prices_b)
        assert abs(delta - 0.1) < 1e-6

    def test_no_common_outcomes_no_yes_keys(self):
        prices_a = {"Option A": "0.50"}
        prices_b = {"Option X": "0.40"}
        delta = ArbitrageService._compute_odds_delta(prices_a, prices_b)
        assert delta == 0.0

    def test_empty_prices(self):
        assert ArbitrageService._compute_odds_delta({}, {"Yes": "0.5"}) == 0.0
        assert ArbitrageService._compute_odds_delta({"Yes": "0.5"}, {}) == 0.0
        assert ArbitrageService._compute_odds_delta({}, {}) == 0.0

    def test_max_delta_across_outcomes(self):
        prices_a = {"Yes": "0.80", "No": "0.20"}
        prices_b = {"Yes": "0.50", "No": "0.50"}
        delta = ArbitrageService._compute_odds_delta(prices_a, prices_b)
        assert abs(delta - 0.3) < 1e-6

    def test_invalid_price_values_skipped(self):
        prices_a = {"Yes": "invalid", "No": "0.50"}
        prices_b = {"Yes": "0.60", "No": "0.40"}
        delta = ArbitrageService._compute_odds_delta(prices_a, prices_b)
        assert abs(delta - 0.1) < 1e-6


class TestComputeMappedDelta:
    """Unit tests for outcome-mapped delta calculation."""

    def test_simple_mapping(self):
        prices_a = {"Yes": "0.70", "No": "0.30"}
        prices_b = {"Above": "0.60", "Below": "0.40"}
        mapping = {"Yes": "Above", "No": "Below"}
        delta = ArbitrageService._compute_mapped_delta(prices_a, prices_b, mapping)
        assert abs(delta - 0.1) < 1e-6

    def test_inverted_mapping(self):
        prices_a = {"Yes": "0.80", "No": "0.20"}
        prices_b = {"No": "0.70", "Yes": "0.30"}
        mapping = {"Yes": "Yes", "No": "No"}
        delta = ArbitrageService._compute_mapped_delta(prices_a, prices_b, mapping)
        assert abs(delta - 0.5) < 1e-6

    def test_partial_mapping(self):
        prices_a = {"Yes": "0.60"}
        prices_b = {"True": "0.50"}
        mapping = {"Yes": "True"}
        delta = ArbitrageService._compute_mapped_delta(prices_a, prices_b, mapping)
        assert abs(delta - 0.1) < 1e-6

    def test_empty_mapping(self):
        prices_a = {"Yes": "0.60"}
        prices_b = {"Yes": "0.50"}
        delta = ArbitrageService._compute_mapped_delta(prices_a, prices_b, {})
        assert delta == 0.0

    def test_missing_outcome_in_prices(self):
        prices_a = {"Yes": "0.60"}
        prices_b = {}
        mapping = {"Yes": "Yes"}
        delta = ArbitrageService._compute_mapped_delta(prices_a, prices_b, mapping)
        # prices_b has no "Yes", defaults to 0
        assert abs(delta - 0.6) < 1e-6


class TestBuildLLMPrompt:
    """Tests for the LLM prompt generation."""

    def test_empty_candidates(self):
        prompt = build_llm_prompt([])
        assert "0 candidate pairs" in prompt
        assert "CANDIDATES:" in prompt

    def test_prompt_includes_pair_data(self):
        candidates = [{
            "market_a_id": 1,
            "market_a_question": "Will BTC hit 100k?",
            "market_a_platform": "Polymarket",
            "market_a_outcomes": {"Yes": "Yes", "No": "No"},
            "market_a_outcome_prices": {"Yes": 0.65, "No": 0.35},
            "market_a_end_date": "2026-06-30T00:00:00",
            "market_a_category": "crypto",
            "market_b_id": 2,
            "market_b_question": "Bitcoin above $100,000?",
            "market_b_platform": "Kalshi",
            "market_b_outcomes": {"Yes": "Yes", "No": "No"},
            "market_b_outcome_prices": {"Yes": 0.60, "No": 0.40},
            "market_b_end_date": "2026-06-30T00:00:00",
            "market_b_category": "crypto",
            "tfidf_score": 0.42,
        }]
        prompt = build_llm_prompt(candidates)
        assert "Will BTC hit 100k?" in prompt
        assert "Bitcoin above $100,000?" in prompt
        assert "Polymarket" in prompt
        assert "Kalshi" in prompt
        assert "Pair 0" in prompt
        assert "outcome_mapping" in prompt


class TestImportVerifiedEndpoint:
    @pytest.mark.asyncio
    async def test_empty_import(self, api_client: AsyncClient):
        resp = await api_client.post(
            "/api/v1/arbitrage/import-verified",
            json={"pairs": []},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["imported"] == 0
        assert data["skipped"] == 0

    @pytest.mark.asyncio
    async def test_import_missing_confidence(self, api_client: AsyncClient):
        resp = await api_client.post(
            "/api/v1/arbitrage/import-verified",
            json={"pairs": [{"market_a_id": 1, "market_b_id": 2}]},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_import_missing_pairs_field(self, api_client: AsyncClient):
        resp = await api_client.post(
            "/api/v1/arbitrage/import-verified",
            json={},
        )
        assert resp.status_code == 422
