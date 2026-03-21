"""API endpoints for managing synonym equivalence groups."""

import fcntl
import json

import structlog
import app.matching.synonyms as synonyms_mod
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

logger = structlog.get_logger()

router = APIRouter(prefix="/synonyms", tags=["synonyms"])


class SynonymGroupInput(BaseModel):
    """A group of equivalent words (minimum 2)."""

    words: list[str]

    @field_validator("words", mode="before")
    @classmethod
    def normalize_words(cls, v: list[str]) -> list[str]:
        normalized = [w.strip().lower() for w in v if w.strip()]
        if len(normalized) < 2:
            raise ValueError("Each synonym group must have at least 2 words")
        return normalized


def _read_groups() -> list[list[str]]:
    return synonyms_mod.load_synonym_groups()


def _write_groups(groups: list[list[str]]) -> None:
    path = synonyms_mod.SYNONYMS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            json.dump(groups, f, indent=2)
            f.write("\n")
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


@router.get("")
async def list_synonyms() -> dict:
    """Return all synonym groups."""
    return {"groups": _read_groups()}


@router.post("", status_code=201)
async def add_synonym_group(body: SynonymGroupInput) -> dict:
    """Add a new synonym equivalence group."""
    groups = _read_groups()
    groups.append(body.words)
    _write_groups(groups)
    logger.info("synonym_group_added", words=body.words)
    return {"groups": groups}


@router.put("/{index}")
async def update_synonym_group(index: int, body: SynonymGroupInput) -> dict:
    """Update a synonym group at the given index."""
    groups = _read_groups()
    if index < 0 or index >= len(groups):
        raise HTTPException(status_code=404, detail="Synonym group not found")
    groups[index] = body.words
    _write_groups(groups)
    logger.info("synonym_group_updated", index=index, words=body.words)
    return {"groups": groups}


@router.delete("/{index}")
async def delete_synonym_group(index: int) -> dict:
    """Delete a synonym group at the given index."""
    groups = _read_groups()
    if index < 0 or index >= len(groups):
        raise HTTPException(status_code=404, detail="Synonym group not found")
    groups.pop(index)
    _write_groups(groups)
    logger.info("synonym_group_deleted", index=index)
    return {"groups": groups}
