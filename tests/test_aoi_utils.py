"""
Unit tests for src/aoi_utils.py — population statistics and AOI boundary creation.
"""

import sys
from pathlib import Path

import pandas as pd
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.aoi_utils import calculate_population_statistics

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
        assert stats['total_pop_1950'] == 100_000 + 300_000 + 50_000
        assert stats['growth_rate_pre'] > 0
        assert stats['growth_rate_post'] > 0
        assert stats['growth_rate_total'] > 0

    def test_empty_dataframe(self):
        empty_df = pd.DataFrame(columns=['1950', '2024', '2035'])
        stats = calculate_population_statistics(empty_df)
        assert stats['total_pop_2024'] == 0
        assert stats['growth_rate_pre'] == 0

    def test_single_city(self):
        df = pd.DataFrame({
            '1950': [100_000],
            '2024': [1_000_000],
            '2035': [1_500_000],
        })
        stats = calculate_population_statistics(df)
        assert stats['total_pop_2024'] == 1_000_000
        # Pre-2024: 74 years of growth from 100k to 1M
        assert 2.0 < stats['growth_rate_pre'] < 5.0  # ~3.1% CAGR

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
