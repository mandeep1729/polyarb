"""Tests for custom synonym loading, merging, and API endpoints."""
import json
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.matching.synonyms import (
    SYNONYMS,
    _groups_to_dict,
    expand_synonyms,
    get_all_synonyms,
    get_builtin_synonym_groups,
    load_custom_synonyms,
)


# ---------------------------------------------------------------------------
# Unit tests for synonym helpers
# ---------------------------------------------------------------------------


class TestLoadCustomSynonyms:
    def test_missing_file(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(
            "app.matching.synonyms.CUSTOM_SYNONYMS_PATH",
            tmp_path / "nonexistent.json",
        )
        assert load_custom_synonyms() == []

    def test_empty_file(self, tmp_path: Path, monkeypatch):
        f = tmp_path / "empty.json"
        f.write_text("")
        monkeypatch.setattr("app.matching.synonyms.CUSTOM_SYNONYMS_PATH", f)
        assert load_custom_synonyms() == []

    def test_valid_file(self, tmp_path: Path, monkeypatch):
        f = tmp_path / "syns.json"
        groups = [["crude", "wti"], ["oil", "petroleum"]]
        f.write_text(json.dumps(groups))
        monkeypatch.setattr("app.matching.synonyms.CUSTOM_SYNONYMS_PATH", f)
        assert load_custom_synonyms() == groups


class TestGroupsToDict:
    def test_simple_group(self):
        result = _groups_to_dict([["a", "b", "c"]])
        assert set(result["a"]) == {"b", "c"}
        assert set(result["b"]) == {"a", "c"}
        assert set(result["c"]) == {"a", "b"}

    def test_multiple_groups(self):
        result = _groups_to_dict([["x", "y"], ["p", "q"]])
        assert result["x"] == ["y"]
        assert result["p"] == ["q"]

    def test_empty_groups(self):
        assert _groups_to_dict([]) == {}


class TestGetAllSynonyms:
    def test_merges_custom_and_builtin(self, tmp_path: Path, monkeypatch):
        f = tmp_path / "syns.json"
        f.write_text(json.dumps([["crude", "wti"]]))
        monkeypatch.setattr("app.matching.synonyms.CUSTOM_SYNONYMS_PATH", f)
        merged = get_all_synonyms()
        # Custom synonyms present
        assert "wti" in merged["crude"]
        assert "crude" in merged["wti"]
        # Built-in synonyms still present
        assert "bitcoin" in merged["btc"]

    def test_custom_extends_builtin(self, tmp_path: Path, monkeypatch):
        # Add a new synonym for an existing builtin key
        f = tmp_path / "syns.json"
        f.write_text(json.dumps([["btc", "xbt"]]))
        monkeypatch.setattr("app.matching.synonyms.CUSTOM_SYNONYMS_PATH", f)
        merged = get_all_synonyms()
        assert "xbt" in merged["btc"]
        assert "bitcoin" in merged["btc"]  # original still there

    def test_no_custom_file(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(
            "app.matching.synonyms.CUSTOM_SYNONYMS_PATH",
            tmp_path / "missing.json",
        )
        merged = get_all_synonyms()
        assert merged == SYNONYMS


class TestExpandSynonymsWithCustom:
    def test_custom_expansion(self, tmp_path: Path, monkeypatch):
        f = tmp_path / "syns.json"
        f.write_text(json.dumps([["crude", "wti"]]))
        monkeypatch.setattr("app.matching.synonyms.CUSTOM_SYNONYMS_PATH", f)
        result = expand_synonyms("crude oil prices")
        assert "wti" in result

    def test_builtin_still_works(self, tmp_path: Path, monkeypatch):
        f = tmp_path / "syns.json"
        f.write_text("[]")
        monkeypatch.setattr("app.matching.synonyms.CUSTOM_SYNONYMS_PATH", f)
        result = expand_synonyms("btc price")
        assert "bitcoin" in result


class TestGetBuiltinSynonymGroups:
    def test_returns_groups(self):
        groups = get_builtin_synonym_groups()
        assert len(groups) > 0
        # Each group should have at least 2 members
        for group in groups:
            assert len(group) >= 2

    def test_covers_all_builtin_words(self):
        groups = get_builtin_synonym_groups()
        all_words = {w for group in groups for w in group}
        for word in SYNONYMS:
            assert word in all_words


# ---------------------------------------------------------------------------
# API integration tests
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def api_client(tmp_path: Path, monkeypatch):
    """AsyncClient hitting the real app, with custom synonyms in a temp file."""
    syn_file = tmp_path / "custom_synonyms.json"
    syn_file.write_text("[]")
    monkeypatch.setattr("app.matching.synonyms.CUSTOM_SYNONYMS_PATH", syn_file)

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestSynonymsCRUD:
    @pytest.mark.asyncio
    async def test_list_empty(self, api_client: AsyncClient):
        resp = await api_client.get("/api/v1/synonyms")
        assert resp.status_code == 200
        data = resp.json()
        assert data["custom"] == []
        assert len(data["builtin"]) > 0

    @pytest.mark.asyncio
    async def test_add_group(self, api_client: AsyncClient):
        resp = await api_client.post(
            "/api/v1/synonyms",
            json={"words": ["crude", "wti", "west texas intermediate"]},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["custom"]) == 1
        assert data["custom"][0] == ["crude", "wti", "west texas intermediate"]

    @pytest.mark.asyncio
    async def test_add_rejects_single_word(self, api_client: AsyncClient):
        resp = await api_client.post(
            "/api/v1/synonyms", json={"words": ["lonely"]}
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_full_crud_cycle(self, api_client: AsyncClient):
        # Add
        resp = await api_client.post(
            "/api/v1/synonyms", json={"words": ["oil", "petroleum"]}
        )
        assert resp.status_code == 201

        # List
        resp = await api_client.get("/api/v1/synonyms")
        assert len(resp.json()["custom"]) == 1

        # Update
        resp = await api_client.put(
            "/api/v1/synonyms/0",
            json={"words": ["oil", "petroleum", "crude oil"]},
        )
        assert resp.status_code == 200
        assert resp.json()["custom"][0] == ["oil", "petroleum", "crude oil"]

        # Delete
        resp = await api_client.delete("/api/v1/synonyms/0")
        assert resp.status_code == 200
        assert resp.json()["custom"] == []

    @pytest.mark.asyncio
    async def test_update_invalid_index(self, api_client: AsyncClient):
        resp = await api_client.put(
            "/api/v1/synonyms/99", json={"words": ["a", "b"]}
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_invalid_index(self, api_client: AsyncClient):
        resp = await api_client.delete("/api/v1/synonyms/99")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_words_are_lowercased_and_stripped(self, api_client: AsyncClient):
        resp = await api_client.post(
            "/api/v1/synonyms", json={"words": [" Crude ", " WTI "]}
        )
        assert resp.status_code == 201
        assert resp.json()["custom"][0] == ["crude", "wti"]
