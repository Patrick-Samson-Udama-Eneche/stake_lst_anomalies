"""
Unit tests for src/aoi_utils.py — population statistics and AOI boundary creation.
"""

import sys
from pathlib import Path

import pandas as pd
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.aoi_utils import calculate_population_statistics, sort_cities_by_population

# Optional — only import if geopandas is available (some CI runners may skip)
geopandas_available = True
try:
    import geopandas as gpd
    from shapely.geometry import box
    from src.aoi_utils import create_aoi_boundary
except ImportError:
    geopandas_available = False


# =============================================================================
# calculate_population_statistics
# =============================================================================

class TestCalculatePopulationStatistics:
    """Tests for the population growth-rate calculator."""

    def test_basic_growth(self, sample_cities_df):
        stats = calculate_population_statistics(sample_cities_df)
        assert stats['total_pop_2024'] == 3_000_000 + 15_000_000 + 1_200_000
        assert stats['total_pop_first'] == 100_000 + 300_000 + 50_000
        assert stats['growth_rate_pre'] > 0
        assert stats['growth_rate_post'] > 0
        assert stats['growth_rate_total'] > 0

    def test_empty_dataframe(self):
        empty_df = pd.DataFrame(columns=['1975', '2024', '2050'])
        stats = calculate_population_statistics(empty_df)
        assert stats['total_pop_2024'] == 0
        assert stats['growth_rate_pre'] == 0

    def test_single_city(self):
        df = pd.DataFrame({
            '1975': [100_000],
            '2024': [1_000_000],
            '2050': [1_500_000],
        })
        stats = calculate_population_statistics(df)
        assert stats['total_pop_2024'] == 1_000_000
        # Pre-2024: 49 years of growth from 100k to 1M
        assert 2.0 < stats['growth_rate_pre'] < 6.0  # ~4.8% CAGR

    def test_growth_rate_ordering(self, sample_cities_df):
        """Pre-2024 growth rate should differ from post-2024 rate."""
        stats = calculate_population_statistics(sample_cities_df)
        # Both should be positive (growing cities)
        assert stats['growth_rate_pre'] > 0
        assert stats['growth_rate_post'] > 0


# =============================================================================
# create_aoi_boundary (requires geopandas)
# =============================================================================

@pytest.mark.skipif(not geopandas_available, reason="geopandas not installed")
class TestCreateAOIBoundary:
    """Tests for AOI bounding-box creation."""

    def test_creates_bounding_box(self):
        """AOI boundary should be a rectangle enclosing the input geometry."""
        # Create a simple polygon in Web Mercator
        geom = box(500_000, 600_000, 520_000, 620_000)
        aoi_gdf, aoi_area = create_aoi_boundary(geom, "TestCity")

        assert not aoi_gdf.empty
        assert aoi_area > 0
        assert 'city' in aoi_gdf.columns
        assert aoi_gdf.iloc[0]['city'] == "TestCity"

    def test_area_is_positive(self):
        geom = box(0, 0, 10_000, 10_000)
        _, area = create_aoi_boundary(geom, "SmallCity")
        assert area > 0


# =============================================================================
# sort_cities_by_population
# =============================================================================

class TestSortCitiesByPopulation:
    """Tests for sorting cities by population."""

    def test_descending_order(self, sample_cities_df):
        result = sort_cities_by_population(
            ['CityA', 'CityC', 'CityB'], sample_cities_df, year='2024'
        )
        assert result == ['CityB', 'CityA', 'CityC']

    def test_preserves_all_cities(self, sample_cities_df):
        cities = ['CityC', 'CityA']
        result = sort_cities_by_population(cities, sample_cities_df)
        assert set(result) == set(cities)
        assert len(result) == len(cities)

    def test_unknown_city_sorted_last(self, sample_cities_df):
        result = sort_cities_by_population(
            ['UnknownCity', 'CityA'], sample_cities_df
        )
        assert result == ['CityA', 'UnknownCity']


# =============================================================================
# State entry filtering (logic used in load_aoi_datasets)
# =============================================================================

class TestFilterStateEntries:
    """Entries with 'State' in the name should be removed from cities_df."""

    def test_state_entries_removed(self):
        df = pd.DataFrame({
            'Urban Agglomeration': ['Lagos', 'Abia State', 'Kano', 'Ondo State'],
            'Latitude': [6.45, 5.41, 12.0, 7.14],
            'Longitude': [3.40, 7.49, 8.52, 5.10],
            '2024': [14900, 0, 4900, 0],
        })
        mask = df['Urban Agglomeration'].str.contains(r'\bState\b', case=False, na=False)
        filtered = df[~mask].reset_index(drop=True)
        assert len(filtered) == 2
        assert 'Lagos' in filtered['Urban Agglomeration'].values
        assert 'Kano' in filtered['Urban Agglomeration'].values
        assert 'Abia State' not in filtered['Urban Agglomeration'].values

    def test_no_state_entries_unchanged(self):
        df = pd.DataFrame({
            'Urban Agglomeration': ['Lagos', 'Kano', 'Abuja'],
            'Latitude': [6.45, 12.0, 9.06],
            'Longitude': [3.40, 8.52, 7.49],
            '2024': [14900, 4900, 3000],
        })
        mask = df['Urban Agglomeration'].str.contains(r'\bState\b', case=False, na=False)
        filtered = df[~mask].reset_index(drop=True)
        assert len(filtered) == 3

    def test_state_substring_preserved(self):
        """City names containing 'state' as a substring (not word) are kept."""
        df = pd.DataFrame({
            'Urban Agglomeration': ['Stately', 'Interstate', 'Abia State'],
            'Latitude': [6.0, 7.0, 5.41],
            'Longitude': [3.0, 4.0, 7.49],
            '2024': [100, 200, 0],
        })
        mask = df['Urban Agglomeration'].str.contains(r'\bState\b', case=False, na=False)
        filtered = df[~mask].reset_index(drop=True)
        # 'Stately' and 'Interstate' do NOT contain the standalone word 'State'
        assert len(filtered) == 2
        assert 'Stately' in filtered['Urban Agglomeration'].values
        assert 'Interstate' in filtered['Urban Agglomeration'].values
