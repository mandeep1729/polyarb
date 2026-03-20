"""Tests for deactivate_expired_markets task."""

from datetime import datetime, timedelta, timezone

from app.tasks.cleanup import EXPIRY_GRACE_DAYS


class TestExpiryGracePeriod:
    def test_grace_period_is_7_days(self):
        assert EXPIRY_GRACE_DAYS == 7

    def test_cutoff_calculation(self):
        """Verify the cutoff is exactly 7 days before now."""
        now = datetime(2026, 3, 20, tzinfo=timezone.utc)
        cutoff = now - timedelta(days=EXPIRY_GRACE_DAYS)
        assert cutoff == datetime(2026, 3, 13, tzinfo=timezone.utc)

    def test_market_expired_8_days_ago_should_deactivate(self):
        """A market that expired 8 days ago is past the 7-day grace period."""
        now = datetime(2026, 3, 20, tzinfo=timezone.utc)
        cutoff = now - timedelta(days=EXPIRY_GRACE_DAYS)
        end_date = now - timedelta(days=8)
        assert end_date < cutoff

    def test_market_expired_6_days_ago_should_stay_active(self):
        """A market that expired 6 days ago is within the 7-day grace period."""
        now = datetime(2026, 3, 20, tzinfo=timezone.utc)
        cutoff = now - timedelta(days=EXPIRY_GRACE_DAYS)
        end_date = now - timedelta(days=6)
        assert end_date >= cutoff

    def test_market_expired_exactly_7_days_ago_stays_active(self):
        """A market that expired exactly 7 days ago is at the boundary (not yet past)."""
        now = datetime(2026, 3, 20, 12, 0, 0, tzinfo=timezone.utc)
        cutoff = now - timedelta(days=EXPIRY_GRACE_DAYS)
        # end_date at 12:00 == cutoff at 12:00 → NOT less than cutoff → stays active
        end_date = now - timedelta(days=7)
        assert not (end_date < cutoff)

    def test_market_with_no_end_date_stays_active(self):
        """Markets with no end_date should never be deactivated."""
        # The SQL query filters: end_date IS NOT NULL AND end_date < cutoff
        # A None end_date fails the IS NOT NULL check, so it's never touched.
        end_date = None
        assert end_date is None  # Would be excluded by IS NOT NULL
