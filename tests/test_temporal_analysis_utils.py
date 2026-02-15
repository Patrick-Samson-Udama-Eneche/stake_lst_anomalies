"""
Unit tests for src/temporal_analysis_utils.py — JSON serialization and
persistent-event selection.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.temporal_analysis_utils import (
    fix_json_serialization,
    find_longest_persistent_period,
)


# =============================================================================
# fix_json_serialization
# =============================================================================

class TestFixJsonSerialization:
    """Tests for numpy→Python type conversion."""

    def test_int64(self):
        assert fix_json_serialization(np.int64(42)) == 42
        assert isinstance(fix_json_serialization(np.int64(42)), int)

    def test_float64(self):
        val = fix_json_serialization(np.float64(3.14))
        assert abs(val - 3.14) < 1e-6
        assert isinstance(val, float)

    def test_ndarray(self):
        result = fix_json_serialization(np.array([1, 2, 3]))
        assert result == [1, 2, 3]
        assert isinstance(result, list)

    def test_nested_dict(self):
        data = {
            'a': np.int64(10),
            'b': {'c': np.float32(2.5), 'd': [np.int32(1), np.int32(2)]},
        }
        result = fix_json_serialization(data)
        assert result == {'a': 10, 'b': {'c': 2.5, 'd': [1, 2]}}

    def test_nan_becomes_none(self):
        assert fix_json_serialization(float('nan')) is None
        assert fix_json_serialization(np.nan) is None

    def test_plain_types_pass_through(self):
        assert fix_json_serialization("hello") == "hello"
        assert fix_json_serialization(42) == 42
        assert fix_json_serialization(None) is None


# =============================================================================
# find_longest_persistent_period
# =============================================================================

class TestFindLongestPersistentPeriod:
    """Tests for selecting the longest heat event across datasets."""

    def test_returns_longest_event(self, sample_combined_results):
        result = find_longest_persistent_period(sample_combined_results)
        assert result is not None
        assert result['longest_event']['duration'] == 7  # ERA5 day: 7 days
        assert result['selection_criteria'] == 'longest_duration'

    def test_total_count(self, sample_combined_results):
        result = find_longest_persistent_period(sample_combined_results)
        # 2 MODIS days + 1 MODIS night + 1 ERA5 day = 4
        assert result['total_persistent_events'] == 4

    def test_empty_returns_none(self):
        empty = {
            'modis': {
                'heat_events': {
                    'persistent_events': {
                        'persistent_hot_days': [],
                        'persistent_hot_nights': [],
                    }
                }
            }
        }
        assert find_longest_persistent_period(empty) is None

    def test_single_event(self):
        single = {
            'modis': {
                'heat_events': {
                    'persistent_events': {
                        'persistent_hot_days': [
                            {'start': '2024-08-01', 'end': '2024-08-04',
                             'duration': 4, 'max_temp': 39.0},
                        ],
                        'persistent_hot_nights': [],
                    }
                }
            }
        }
        result = find_longest_persistent_period(single)
        assert result['longest_event']['duration'] == 4
        assert result['total_persistent_events'] == 1
