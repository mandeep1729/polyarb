"""Tests for manual market pairing endpoint POST /arbitrage/pair."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.services.arbitrage_service import ArbitrageService


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
