"""Unit tests for the event equivalence scorer."""
from datetime import datetime, timezone

import pytest

from app.matching.scorer import (
    _description_similarity,
    _end_date_gate,
    _temporal_proximity,
    score_pair,
)


class TestEndDateGate:
    """Tests for _end_date_gate() hard gate logic."""

    def test_both_none_passes(self):
        assert _end_date_gate(None, None) is True

    def test_first_none_second_present_fails(self):
        dt = datetime(2026, 3, 20, tzinfo=timezone.utc)
        assert _end_date_gate(None, dt) is False

    def test_first_present_second_none_fails(self):
        dt = datetime(2026, 3, 20, tzinfo=timezone.utc)
        assert _end_date_gate(dt, None) is False

    def test_same_datetime_passes(self):
        dt = datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc)
        assert _end_date_gate(dt, dt) is True

    def test_12_hours_apart_passes(self):
        dt1 = datetime(2026, 3, 20, 0, 0, tzinfo=timezone.utc)
        dt2 = datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc)
        assert _end_date_gate(dt1, dt2) is True

    def test_exactly_1_day_passes(self):
        dt1 = datetime(2026, 3, 20, 0, 0, tzinfo=timezone.utc)
        dt2 = datetime(2026, 3, 21, 0, 0, tzinfo=timezone.utc)
        assert _end_date_gate(dt1, dt2) is True

    def test_25_hours_apart_fails(self):
        dt1 = datetime(2026, 3, 20, 0, 0, tzinfo=timezone.utc)
        dt2 = datetime(2026, 3, 21, 1, 0, tzinfo=timezone.utc)
        assert _end_date_gate(dt1, dt2) is False

    def test_2_days_apart_fails(self):
        dt1 = datetime(2026, 3, 20, tzinfo=timezone.utc)
        dt2 = datetime(2026, 3, 22, tzinfo=timezone.utc)
        assert _end_date_gate(dt1, dt2) is False

    def test_order_does_not_matter(self):
        dt1 = datetime(2026, 3, 20, 0, 0, tzinfo=timezone.utc)
        dt2 = datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc)
        assert _end_date_gate(dt1, dt2) == _end_date_gate(dt2, dt1)


class TestTemporalProximity:
    """Tests for _temporal_proximity() fine-grained scoring."""

    def test_both_none_returns_neutral(self):
        assert _temporal_proximity(None, None) == 0.5

    def test_one_none_returns_neutral(self):
        dt = datetime(2026, 3, 20, tzinfo=timezone.utc)
        assert _temporal_proximity(dt, None) == 0.5
        assert _temporal_proximity(None, dt) == 0.5

    def test_same_moment_returns_1(self):
        dt = datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc)
        assert _temporal_proximity(dt, dt) == 1.0

    def test_12_hours_returns_half(self):
        dt1 = datetime(2026, 3, 20, 0, 0, tzinfo=timezone.utc)
        dt2 = datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc)
        assert _temporal_proximity(dt1, dt2) == pytest.approx(0.5)

    def test_1_day_apart_returns_0(self):
        dt1 = datetime(2026, 3, 20, 0, 0, tzinfo=timezone.utc)
        dt2 = datetime(2026, 3, 21, 0, 0, tzinfo=timezone.utc)
        assert _temporal_proximity(dt1, dt2) == 0.0


class TestDescriptionSimilarity:
    """Tests for _description_similarity()."""

    def test_both_none_returns_neutral(self):
        assert _description_similarity(None, None) == 0.5

    def test_one_none_returns_neutral(self):
        assert _description_similarity("some desc", None) == 0.5
        assert _description_similarity(None, "some desc") == 0.5

    def test_both_empty_returns_neutral(self):
        assert _description_similarity("", "") == 0.5

    def test_identical_descriptions_high_score(self):
        desc = "Will Bitcoin reach $100,000 by end of June 2026?"
        score = _description_similarity(desc, desc)
        assert score > 0.9

    def test_different_descriptions_low_score(self):
        d1 = "The Federal Reserve will cut interest rates at the March meeting."
        d2 = "LeBron James wins NBA MVP for the 2025-2026 season."
        score = _description_similarity(d1, d2)
        assert score < 0.4


class TestScorePair:
    """Tests for the full score_pair() composite scorer."""

    def test_returns_0_when_end_date_gate_fails_one_null(self):
        dt = datetime(2026, 3, 20, tzinfo=timezone.utc)
        score = score_pair(
            q1="Will BTC hit 100k?",
            q2="Will BTC hit 100k?",
            cat1="crypto", cat2="crypto",
            end1=dt, end2=None,
            tfidf_score=0.95,
        )
        assert score == 0.0

    def test_returns_0_when_end_dates_differ_by_more_than_1_day(self):
        dt1 = datetime(2026, 3, 20, tzinfo=timezone.utc)
        dt2 = datetime(2026, 3, 25, tzinfo=timezone.utc)
        score = score_pair(
            q1="Will BTC hit 100k?",
            q2="Will BTC hit 100k?",
            cat1="crypto", cat2="crypto",
            end1=dt1, end2=dt2,
            tfidf_score=0.95,
        )
        assert score == 0.0

    def test_identical_markets_high_score(self):
        dt = datetime(2026, 6, 30, tzinfo=timezone.utc)
        score = score_pair(
            q1="Will Bitcoin reach $100,000 by June 2026?",
            q2="Will Bitcoin reach $100,000 by June 2026?",
            cat1="crypto", cat2="crypto",
            end1=dt, end2=dt,
            tfidf_score=1.0,
            desc_tfidf_score=1.0,
        )
        assert score >= 0.85

    def test_scores_correctly_without_descriptions(self):
        dt = datetime(2026, 6, 30, tzinfo=timezone.utc)
        score = score_pair(
            q1="Will Bitcoin reach $100,000?",
            q2="Will Bitcoin reach $100,000?",
            cat1="crypto", cat2="crypto",
            end1=dt, end2=dt,
            tfidf_score=0.9,
            desc1=None, desc2=None,
        )
        # desc_tfidf_score should default to 0.5 (neutral)
        assert score > 0.0

    def test_both_end_dates_none_still_scores(self):
        score = score_pair(
            q1="Will the sun rise tomorrow?",
            q2="Will the sun rise tomorrow?",
            cat1=None, cat2=None,
            end1=None, end2=None,
            tfidf_score=1.0,
        )
        assert score > 0.0

    def test_different_categories_reduce_score(self):
        dt = datetime(2026, 6, 30, tzinfo=timezone.utc)
        same_cat = score_pair(
            q1="Will BTC hit 100k?",
            q2="Will BTC hit 100k?",
            cat1="crypto", cat2="crypto",
            end1=dt, end2=dt,
            tfidf_score=0.8,
        )
        diff_cat = score_pair(
            q1="Will BTC hit 100k?",
            q2="Will BTC hit 100k?",
            cat1="crypto", cat2="sports",
            end1=dt, end2=dt,
            tfidf_score=0.8,
        )
        assert same_cat > diff_cat

    def test_score_never_exceeds_1(self):
        dt = datetime(2026, 6, 30, tzinfo=timezone.utc)
        score = score_pair(
            q1="test", q2="test",
            cat1="crypto", cat2="crypto",
            end1=dt, end2=dt,
            tfidf_score=1.0,
            desc_tfidf_score=1.0,
        )
        assert score <= 1.0

    def test_description_signal_affects_score(self):
        dt = datetime(2026, 6, 30, tzinfo=timezone.utc)
        with_desc = score_pair(
            q1="Will BTC hit 100k?",
            q2="Will BTC hit 100k?",
            cat1="crypto", cat2="crypto",
            end1=dt, end2=dt,
            tfidf_score=0.7,
            desc_tfidf_score=0.9,
        )
        without_desc = score_pair(
            q1="Will BTC hit 100k?",
            q2="Will BTC hit 100k?",
            cat1="crypto", cat2="crypto",
            end1=dt, end2=dt,
            tfidf_score=0.7,
            desc_tfidf_score=0.1,
        )
        assert with_desc > without_desc
