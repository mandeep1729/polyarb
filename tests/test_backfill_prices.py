"""Tests for the price backfill system.

Tests the model changes, cleanup simplification, bulk insert logic,
helper functions, and backfill task against a real PostgreSQL database.
"""
import os
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database import Base
from app.models.market import UnifiedMarket
from app.models.platform import Platform
from app.models.price_history import PriceSnapshot
from app.tasks.backfill_prices import _bulk_insert, _round_to_hour

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://polyarb:polyarb@postgres:5432/polyarb_test",
)
ADMIN_DATABASE_URL = os.environ.get(
    "ADMIN_DATABASE_URL",
    "postgresql+asyncpg://polyarb:polyarb@postgres:5432/polyarb",
)

_db_initialized = False


async def _ensure_test_db():
    """Create the test database and tables if they don't exist yet."""
    global _db_initialized
    if _db_initialized:
        return
    admin_engine = create_async_engine(ADMIN_DATABASE_URL, isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as conn:
        result = await conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = 'polyarb_test'")
        )
        if not result.scalar():
            await conn.execute(text("CREATE DATABASE polyarb_test"))
    await admin_engine.dispose()

    eng = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with eng.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await eng.dispose()
    _db_initialized = True


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    """Provide a fresh session with clean tables for each test."""
    await _ensure_test_db()
    eng = create_async_engine(TEST_DATABASE_URL, echo=False)
    factory = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        await session.execute(delete(PriceSnapshot))
        await session.execute(delete(UnifiedMarket))
        await session.execute(delete(Platform))
        await session.commit()
        yield session
    await eng.dispose()


@pytest_asyncio.fixture
async def platform(db: AsyncSession) -> Platform:
    """Create a test platform."""
    p = Platform(
        name="TestPlatform",
        slug="testplatform",
        base_url="http://test",
        api_url="http://test/api",
    )
    db.add(p)
    await db.flush()
    return p


@pytest_asyncio.fixture
async def market(db: AsyncSession, platform: Platform) -> UnifiedMarket:
    """Create a test market."""
    m = UnifiedMarket(
        platform_id=platform.id,
        platform_market_id="TEST-MARKET-001",
        question="Will it rain tomorrow?",
        outcomes={"Yes": "token_yes", "No": "token_no"},
    )
    db.add(m)
    await db.flush()
    return m


class TestRoundToHour:
    """Test the _round_to_hour helper function."""

    def test_exact_hour(self):
        ts = int(datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc).timestamp())
        result = _round_to_hour(ts)
        assert result == datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

    def test_mid_hour(self):
        ts = int(datetime(2026, 1, 15, 10, 37, 42, tzinfo=timezone.utc).timestamp())
        result = _round_to_hour(ts)
        assert result == datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

    def test_just_before_next_hour(self):
        ts = int(datetime(2026, 1, 15, 10, 59, 59, tzinfo=timezone.utc).timestamp())
        result = _round_to_hour(ts)
        assert result == datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

    def test_midnight(self):
        ts = int(datetime(2026, 1, 15, 0, 30, 0, tzinfo=timezone.utc).timestamp())
        result = _round_to_hour(ts)
        assert result == datetime(2026, 1, 15, 0, 0, 0, tzinfo=timezone.utc)

    def test_returns_utc(self):
        ts = int(datetime(2026, 6, 15, 14, 22, 0, tzinfo=timezone.utc).timestamp())
        result = _round_to_hour(ts)
        assert result.tzinfo == timezone.utc


class TestPriceSnapshotModel:
    """Test PriceSnapshot model changes."""

    @pytest.mark.asyncio
    async def test_create_with_server_default_timestamp(
        self, db: AsyncSession, market: UnifiedMarket
    ):
        """Existing code path: no timestamp provided, server_default kicks in."""
        snap = PriceSnapshot(
            market_id=market.id,
            outcome_prices={"Yes": 0.65, "No": 0.35},
            volume_24h=100.0,
        )
        db.add(snap)
        await db.flush()
        assert snap.id is not None

    @pytest.mark.asyncio
    async def test_create_with_explicit_timestamp(
        self, db: AsyncSession, market: UnifiedMarket
    ):
        """New code path: caller provides a historical timestamp."""
        historical_ts = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        snap = PriceSnapshot(
            market_id=market.id,
            outcome_prices={"Yes": 0.70, "No": 0.30},
            volume=200.0,
            timestamp=historical_ts,
        )
        db.add(snap)
        await db.flush()
        assert snap.id is not None
        assert snap.timestamp == historical_ts

    @pytest.mark.asyncio
    async def test_create_with_none_timestamp(
        self, db: AsyncSession, market: UnifiedMarket
    ):
        """Passing None explicitly should work (server_default fills it)."""
        snap = PriceSnapshot(
            market_id=market.id,
            outcome_prices={"Yes": 0.55},
            timestamp=None,
        )
        db.add(snap)
        await db.flush()
        assert snap.id is not None


class TestBulkInsert:
    """Test _bulk_insert with ON CONFLICT DO NOTHING."""

    @pytest.mark.asyncio
    async def test_insert_rows(self, db: AsyncSession, market: UnifiedMarket):
        """Basic bulk insert creates rows."""
        ts1 = datetime(2025, 3, 1, 10, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2025, 3, 1, 11, 0, 0, tzinfo=timezone.utc)
        rows = [
            {
                "market_id": market.id,
                "outcome_prices": {"Yes": 0.5},
                "volume_24h": None,
                "timestamp": ts1,
            },
            {
                "market_id": market.id,
                "outcome_prices": {"Yes": 0.6},
                "volume_24h": None,
                "timestamp": ts2,
            },
        ]
        inserted = await _bulk_insert(db, rows)
        assert inserted == 2

    @pytest.mark.asyncio
    async def test_idempotent_insert(self, db: AsyncSession, market: UnifiedMarket):
        """Re-inserting same (market_id, timestamp) is a no-op."""
        ts = datetime(2025, 4, 1, 10, 0, 0, tzinfo=timezone.utc)
        rows = [
            {
                "market_id": market.id,
                "outcome_prices": {"Yes": 0.5},
                "volume_24h": None,
                "timestamp": ts,
            },
        ]
        first = await _bulk_insert(db, rows)
        assert first == 1
        await db.flush()

        second = await _bulk_insert(db, rows)
        assert second == 0

    @pytest.mark.asyncio
    async def test_empty_rows(self, db: AsyncSession):
        """Inserting empty list returns 0."""
        inserted = await _bulk_insert(db, [])
        assert inserted == 0

    @pytest.mark.asyncio
    async def test_chunking_large_batch(self, db: AsyncSession, market: UnifiedMarket):
        """Verify large batches are chunked and all rows inserted."""
        base_ts = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        rows = [
            {
                "market_id": market.id,
                "outcome_prices": {"Yes": round(0.5 + (i % 50) * 0.001, 4)},
                "volume_24h": None,
                "timestamp": base_ts + timedelta(hours=i),
            }
            for i in range(2500)
        ]
        inserted = await _bulk_insert(db, rows)
        assert inserted == 2500

    @pytest.mark.asyncio
    async def test_mixed_new_and_duplicate(self, db: AsyncSession, market: UnifiedMarket):
        """Batch with some duplicates inserts only new rows."""
        ts1 = datetime(2025, 5, 1, 10, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2025, 5, 1, 11, 0, 0, tzinfo=timezone.utc)
        ts3 = datetime(2025, 5, 1, 12, 0, 0, tzinfo=timezone.utc)

        rows1 = [
            {"market_id": market.id, "outcome_prices": {"Yes": 0.5}, "volume_24h": None, "timestamp": ts1},
            {"market_id": market.id, "outcome_prices": {"Yes": 0.6}, "volume_24h": None, "timestamp": ts2},
        ]
        await _bulk_insert(db, rows1)
        await db.flush()

        rows2 = [
            {"market_id": market.id, "outcome_prices": {"Yes": 0.7}, "volume_24h": None, "timestamp": ts2},
            {"market_id": market.id, "outcome_prices": {"Yes": 0.8}, "volume_24h": None, "timestamp": ts3},
        ]
        inserted = await _bulk_insert(db, rows2)
        assert inserted == 1
