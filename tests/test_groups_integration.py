"""Integration tests for the groups feature.

Tests run against the live backend API (localhost:8001).
Requires the backend container to be running with data populated.
"""
import httpx
import pytest

API_URL = "http://localhost:8001/api/v1"


@pytest.fixture
def api():
    """HTTP client for the live API."""
    return httpx.Client(base_url=API_URL, timeout=30.0)


class TestGroupsListEndpoint:
    """GET /api/v1/groups"""

    def test_returns_paginated_response(self, api):
        resp = api.get("/groups", params={"limit": 5})
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "next_cursor" in data
        assert isinstance(data["items"], list)
        assert len(data["items"]) <= 5

    def test_groups_have_required_fields(self, api):
        resp = api.get("/groups", params={"limit": 1})
        data = resp.json()
        if not data["items"]:
            pytest.skip("No groups available")
        group = data["items"][0]
        assert "id" in group
        assert "canonical_question" in group
        assert "consensus_yes" in group
        assert "consensus_no" in group
        assert "disagreement_score" in group
        assert "member_count" in group
        assert "total_volume" in group
        assert "total_liquidity" in group
        assert "best_yes_market_id" in group
        assert "best_no_market_id" in group
        assert "created_at" in group
        assert "updated_at" in group

    def test_sort_by_disagreement(self, api):
        resp = api.get("/groups", params={"limit": 10, "sort_by": "disagreement"})
        data = resp.json()
        items = data["items"]
        if len(items) < 2:
            pytest.skip("Not enough groups")
        scores = [g["disagreement_score"] for g in items if g["disagreement_score"] is not None]
        assert scores == sorted(scores, reverse=True)

    def test_sort_by_volume(self, api):
        resp = api.get("/groups", params={"limit": 10, "sort_by": "volume"})
        data = resp.json()
        items = data["items"]
        if len(items) < 2:
            pytest.skip("Not enough groups")
        volumes = [g["total_volume"] for g in items if g["total_volume"] is not None]
        assert volumes == sorted(volumes, reverse=True)

    def test_filter_by_category(self, api):
        resp = api.get("/groups", params={"limit": 10, "category": "sports"})
        data = resp.json()
        for group in data["items"]:
            assert group["category"] == "sports"

    def test_pagination_cursor(self, api):
        page1 = api.get("/groups", params={"limit": 3}).json()
        if page1["next_cursor"] is None:
            pytest.skip("Not enough groups for pagination")
        page2 = api.get("/groups", params={"limit": 3, "cursor": page1["next_cursor"]}).json()
        page1_ids = {g["id"] for g in page1["items"]}
        page2_ids = {g["id"] for g in page2["items"]}
        assert page1_ids.isdisjoint(page2_ids), "Pages should not overlap"

    def test_invalid_sort_returns_422(self, api):
        resp = api.get("/groups", params={"sort_by": "invalid"})
        assert resp.status_code == 422

    def test_empty_category_returns_empty(self, api):
        resp = api.get("/groups", params={"category": "nonexistent_category_xyz"})
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0


class TestGroupDetailEndpoint:
    """GET /api/v1/groups/{group_id}"""

    def _get_first_group_id(self, api) -> int:
        resp = api.get("/groups", params={"limit": 1})
        items = resp.json()["items"]
        if not items:
            pytest.skip("No groups available")
        return items[0]["id"]

    def test_returns_group_with_members(self, api):
        gid = self._get_first_group_id(api)
        resp = api.get(f"/groups/{gid}")
        assert resp.status_code == 200
        data = resp.json()
        assert "group" in data
        assert "members" in data
        assert isinstance(data["members"], list)
        assert data["group"]["id"] == gid

    def test_members_have_platform_info(self, api):
        gid = self._get_first_group_id(api)
        data = api.get(f"/groups/{gid}").json()
        if not data["members"]:
            pytest.skip("Group has no members")
        member = data["members"][0]
        assert "platform_name" in member
        assert "platform_slug" in member
        assert "question" in member
        assert "outcome_prices" in member

    def test_best_odds_markets_included(self, api):
        gid = self._get_first_group_id(api)
        data = api.get(f"/groups/{gid}").json()
        # best_yes_market and best_no_market may be null if no prices
        assert "best_yes_market" in data
        assert "best_no_market" in data

    def test_nonexistent_group_returns_404(self, api):
        resp = api.get("/groups/999999999")
        assert resp.status_code == 404

    def test_member_count_matches_members_list(self, api):
        gid = self._get_first_group_id(api)
        data = api.get(f"/groups/{gid}").json()
        assert data["group"]["member_count"] == len(data["members"])


class TestGroupHistoryEndpoint:
    """GET /api/v1/groups/{group_id}/history"""

    def _get_first_group_id(self, api) -> int:
        resp = api.get("/groups", params={"limit": 1})
        items = resp.json()["items"]
        if not items:
            pytest.skip("No groups available")
        return items[0]["id"]

    def test_returns_list_of_snapshots(self, api):
        gid = self._get_first_group_id(api)
        resp = api.get(f"/groups/{gid}/history", params={"days": 7})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_snapshots_have_required_fields(self, api):
        gid = self._get_first_group_id(api)
        data = api.get(f"/groups/{gid}/history", params={"days": 30}).json()
        if not data:
            pytest.skip("No history snapshots yet")
        snap = data[0]
        assert "consensus_yes" in snap
        assert "consensus_no" in snap
        assert "disagreement_score" in snap
        assert "total_volume" in snap
        assert "timestamp" in snap

    def test_days_param_capped_at_90(self, api):
        gid = self._get_first_group_id(api)
        resp = api.get(f"/groups/{gid}/history", params={"days": 91})
        assert resp.status_code == 422

    def test_snapshots_ordered_by_timestamp(self, api):
        gid = self._get_first_group_id(api)
        data = api.get(f"/groups/{gid}/history", params={"days": 30}).json()
        if len(data) < 2:
            pytest.skip("Not enough snapshots")
        timestamps = [s["timestamp"] for s in data]
        assert timestamps == sorted(timestamps)


class TestGroupConsensusComputation:
    """Verify consensus analytics are computed correctly."""

    def test_consensus_values_are_probabilities(self, api):
        resp = api.get("/groups", params={"limit": 50, "sort_by": "volume"})
        for group in resp.json()["items"]:
            if group["consensus_yes"] is not None:
                assert 0 <= group["consensus_yes"] <= 1, f"consensus_yes out of range: {group['consensus_yes']}"
            if group["consensus_no"] is not None:
                assert 0 <= group["consensus_no"] <= 1, f"consensus_no out of range: {group['consensus_no']}"

    def test_disagreement_is_nonnegative(self, api):
        resp = api.get("/groups", params={"limit": 50})
        for group in resp.json()["items"]:
            if group["disagreement_score"] is not None:
                assert group["disagreement_score"] >= 0

    def test_member_count_is_positive(self, api):
        resp = api.get("/groups", params={"limit": 50})
        for group in resp.json()["items"]:
            assert group["member_count"] >= 0


class TestPolymarketSlugCapture:
    """Verify Polymarket markets now have event_ticker populated."""

    def test_polymarket_markets_have_event_ticker(self, api):
        resp = api.get("/markets", params={"platform": "polymarket", "limit": 10})
        data = resp.json()
        if not data["items"]:
            pytest.skip("No Polymarket markets")
        has_ticker = sum(1 for m in data["items"] if m.get("event_ticker"))
        assert has_ticker > 0, "At least some Polymarket markets should have event_ticker (slug)"
