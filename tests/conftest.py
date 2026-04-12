"""
Shared test fixtures for the LST Modelling project.

Provides sample DataFrames, GeoDataFrames, and config objects that
mirror the real data structures used across notebooks and src modules.
"""

import sys
from pathlib import Path
from datetime import date

import numpy as np
import pandas as pd
import pytest

# Make project root importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Sample city data (mimics WUP 2025 CSV schema,
# columns renamed to legacy names by load_aoi_datasets)
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_cities_df():
    """DataFrame with 3 cities and population columns from 1975 to 2050."""
    return pd.DataFrame({
        'Urban Agglomeration': ['CityA', 'CityB', 'CityC'],
        'Latitude': [9.06, 6.45, 12.00],
        'Longitude': [7.49, 3.40, 8.52],
        '1975': [100_000, 300_000, 50_000],
        '2024': [3_000_000, 15_000_000, 1_200_000],
        '2050': [5_000_000, 22_000_000, 2_000_000],
    })


# ---------------------------------------------------------------------------
# Sample heat events for decision-tree tests
# ---------------------------------------------------------------------------

@pytest.fixture
def overlapping_events():
    """Two events that overlap by 2 days."""
    return {
        'event1_start': date(2024, 6, 1),
        'event1_end': date(2024, 6, 10),
        'event2_start': date(2024, 6, 9),
        'event2_end': date(2024, 6, 15),
    }


@pytest.fixture
def non_overlapping_events():
    """Two events that do NOT overlap."""
    return {
        'event1_start': date(2024, 3, 1),
        'event1_end': date(2024, 3, 5),
        'event2_start': date(2024, 3, 10),
        'event2_end': date(2024, 3, 15),
    }


# ---------------------------------------------------------------------------
# Combined results dict for find_longest_persistent_period
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_combined_results():
    """Mimics the dict structure returned by calculate_comprehensive_heat_statistics_dual."""
    return {
        'modis': {
            'heat_events': {
                'persistent_events': {
                    'persistent_hot_days': [
                        {'start': '2024-05-10', 'end': '2024-05-14',
                         'duration': 5, 'max_temp': 42.1},
                        {'start': '2024-07-01', 'end': '2024-07-03',
                         'duration': 3, 'max_temp': 40.5},
                    ],
                    'persistent_hot_nights': [
                        {'start': '2024-05-11', 'end': '2024-05-13',
                         'duration': 3, 'max_temp': 28.3},
                    ],
                }
            }
        },
        'era5_land': {
            'heat_events': {
                'persistent_events': {
                    'persistent_hot_days': [
                        {'start': '2024-05-09', 'end': '2024-05-15',
                         'duration': 7, 'max_temp': 41.8},
                    ],
                    'persistent_hot_nights': [],
                }
            }
        },
    }
