"""
Unit tests for src/decision_tree_utils.py — event overlap and extension logic.
"""

import sys
from pathlib import Path
from datetime import date, timedelta

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.decision_tree_utils import check_event_overlap, extend_event_period


# =============================================================================
# check_event_overlap
# =============================================================================

class TestCheckEventOverlap:
    """Tests for the event overlap detection function."""

    def test_overlapping_events(self, overlapping_events):
        overlap, days, union_s, union_e = check_event_overlap(
            overlapping_events['event1_start'],
            overlapping_events['event1_end'],
            overlapping_events['event2_start'],
            overlapping_events['event2_end'],
        )
        assert overlap is True
        assert days == 2  # June 9 and June 10
        assert union_s == date(2024, 6, 1)
        assert union_e == date(2024, 6, 15)

    def test_non_overlapping_events(self, non_overlapping_events):
        overlap, days, union_s, union_e = check_event_overlap(
            non_overlapping_events['event1_start'],
            non_overlapping_events['event1_end'],
            non_overlapping_events['event2_start'],
            non_overlapping_events['event2_end'],
        )
        assert overlap is False
        assert days == 0

    def test_identical_events(self):
        overlap, days, union_s, union_e = check_event_overlap(
            date(2024, 7, 1), date(2024, 7, 5),
            date(2024, 7, 1), date(2024, 7, 5),
        )
        assert overlap is True
        assert days == 5  # 1,2,3,4,5
        assert union_s == date(2024, 7, 1)
        assert union_e == date(2024, 7, 5)

    def test_adjacent_events_no_gap(self):
        """Events that share exactly one boundary day should overlap."""
        overlap, days, _, _ = check_event_overlap(
            date(2024, 1, 1), date(2024, 1, 5),
            date(2024, 1, 5), date(2024, 1, 10),
        )
        assert overlap is True
        assert days == 1

    def test_one_day_gap(self):
        overlap, days, _, _ = check_event_overlap(
            date(2024, 1, 1), date(2024, 1, 5),
            date(2024, 1, 7), date(2024, 1, 10),
        )
        assert overlap is False
        assert days == 0

    def test_string_inputs(self):
        """Function should accept ISO date strings."""
        overlap, days, union_s, union_e = check_event_overlap(
            '2024-06-01', '2024-06-10',
            '2024-06-09', '2024-06-15',
        )
        assert overlap is True
        assert days == 2

    def test_single_day_event(self):
        overlap, days, _, _ = check_event_overlap(
            date(2024, 4, 5), date(2024, 4, 5),
            date(2024, 4, 5), date(2024, 4, 5),
        )
        assert overlap is True
        assert days == 1

    def test_contained_event(self):
        """One event fully inside another."""
        overlap, days, union_s, union_e = check_event_overlap(
            date(2024, 3, 1), date(2024, 3, 31),
            date(2024, 3, 10), date(2024, 3, 15),
        )
        assert overlap is True
        assert days == 6  # 10,11,12,13,14,15
        assert union_s == date(2024, 3, 1)
        assert union_e == date(2024, 3, 31)


# =============================================================================
# extend_event_period
# =============================================================================

class TestExtendEventPeriod:
    """Tests for the event extension function."""

    def test_default_extension(self):
        ext_s, ext_e = extend_event_period(date(2024, 6, 5), date(2024, 6, 10))
        assert ext_s == date(2024, 6, 4)
        assert ext_e == date(2024, 6, 11)

    def test_custom_extension(self):
        ext_s, ext_e = extend_event_period(date(2024, 6, 5), date(2024, 6, 10), extension_days=3)
        assert ext_s == date(2024, 6, 2)
        assert ext_e == date(2024, 6, 13)

    def test_zero_extension(self):
        ext_s, ext_e = extend_event_period(date(2024, 6, 5), date(2024, 6, 10), extension_days=0)
        assert ext_s == date(2024, 6, 5)
        assert ext_e == date(2024, 6, 10)

    def test_string_inputs(self):
        ext_s, ext_e = extend_event_period('2024-01-10', '2024-01-15', extension_days=2)
        assert ext_s == date(2024, 1, 8)
        assert ext_e == date(2024, 1, 17)

    def test_crosses_month_boundary(self):
        ext_s, ext_e = extend_event_period(date(2024, 3, 1), date(2024, 3, 31), extension_days=5)
        assert ext_s == date(2024, 2, 25)
        assert ext_e == date(2024, 4, 5)
