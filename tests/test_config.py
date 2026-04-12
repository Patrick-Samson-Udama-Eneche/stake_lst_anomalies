"""
Unit tests for config.py — path helpers, dynamic temporal range, GHSL year selection.
"""

import sys
from pathlib import Path
from datetime import datetime

import pytest

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config


# =============================================================================
# _get_dynamic_temporal_range
# =============================================================================

class TestDynamicTemporalRange:
    """Tests for the auto-calculated time range."""

    def test_returns_tuple(self):
        end_date, years = config._get_dynamic_temporal_range()
        assert isinstance(end_date, str)
        assert isinstance(years, list)

    def test_end_date_format(self):
        end_date, _ = config._get_dynamic_temporal_range()
        # Must be YYYY-12-31
        assert end_date.endswith("-12-31")
        year = int(end_date[:4])
        assert 2005 < year < 2100

    def test_excludes_current_year(self):
        _, years = config._get_dynamic_temporal_range()
        current_year = datetime.now().year
        assert current_year not in years
        assert (current_year - 1) in years

    def test_starts_at_2006(self):
        _, years = config._get_dynamic_temporal_range()
        assert years[0] == 2006

    def test_years_are_contiguous(self):
        _, years = config._get_dynamic_temporal_range()
        for i in range(1, len(years)):
            assert years[i] == years[i - 1] + 1


# =============================================================================
# get_closest_ghsl_year
# =============================================================================

class TestGetClosestGHSLYear:
    """Tests for GHSL year selection logic."""

    def test_exact_match(self):
        assert config.get_closest_ghsl_year(2020, verbose=False) == 2020

    def test_rounds_to_nearest(self):
        # 2024 → should pick 2025 (1 year away vs 4 years from 2020)
        assert config.get_closest_ghsl_year(2024, verbose=False) == 2025

    def test_before_all_years(self):
        assert config.get_closest_ghsl_year(1960, verbose=False) == 1975

    def test_after_all_years(self):
        assert config.get_closest_ghsl_year(2050, verbose=False) == 2030

    def test_midpoint_tie(self):
        # 2022 is equidistant (2 years) from 2020 and 2025
        # min() returns the first minimum → 2020
        result = config.get_closest_ghsl_year(2022, verbose=False)
        assert result in (2020, 2025)

    def test_verbose_does_not_crash(self, capsys):
        result = config.get_closest_ghsl_year(2024, verbose=True)
        captured = capsys.readouterr()
        assert "Selected" in captured.out
        assert result == 2025


# =============================================================================
# Path helper functions
# =============================================================================

class TestPathHelpers:
    """Tests for get_output_dir, get_input_path, get_aoi_data_path."""

    def test_get_output_dir_creates_directory(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, 'OUTPUT_DATA_PATH', str(tmp_path))
        output = config.get_output_dir("test_notebook")
        assert output.exists()
        assert output.name == "test_notebook"
        # Cleanup
        output.rmdir()

    def test_get_input_path_no_subfolder(self):
        result = config.get_input_path("test.csv")
        assert result.name == "test.csv"
        assert result.parent == Path(config.INPUT_DATA_PATH)

    def test_get_input_path_with_subfolder(self):
        result = config.get_input_path("test.csv", subfolder="mydir")
        assert result.name == "test.csv"
        assert result.parent.name == "mydir"

    def test_get_aoi_data_path_valid_key(self):
        path = config.get_aoi_data_path('cities_csv')
        assert str(path).endswith('.csv')

    def test_get_aoi_data_path_legacy_alias(self):
        """'cities_xlsx' should resolve to the same path as 'cities_csv'."""
        path_legacy = config.get_aoi_data_path('cities_xlsx')
        path_new = config.get_aoi_data_path('cities_csv')
        assert path_legacy == path_new

    def test_get_aoi_data_path_invalid_key_raises(self):
        with pytest.raises(ValueError, match="Unknown data type"):
            config.get_aoi_data_path('nonexistent_key')


# =============================================================================
# Configuration constants sanity checks
# =============================================================================

class TestConfigConstants:
    """Sanity checks on configuration values."""

    def test_study_year_is_int(self):
        assert isinstance(config.PROJECT_STUDY_YEAR, int)
        assert 2000 <= config.PROJECT_STUDY_YEAR <= 2050

    def test_crs_strings(self):
        assert config.WGS84 == "EPSG:4326"
        assert config.WEB_MERCATOR == "EPSG:3857"

    def test_hotspot_percentiles_valid(self):
        assert 50 <= config.HOTSPOT_CONFIG['percentile_hot'] <= 99
        assert config.HOTSPOT_CONFIG['percentile_extreme'] > config.HOTSPOT_CONFIG['percentile_hot']

    def test_kde_contour_levels_sorted(self):
        levels = config.KDE_CONFIG['contour_levels']
        assert levels == sorted(levels)
        assert all(0 < lev <= 1 for lev in levels)

    def test_model_output_dir_exists_as_path(self):
        assert hasattr(config, 'MODEL_OUTPUT_DIR')
        assert str(config.MODEL_OUTPUT_DIR).endswith('06_hotspot_modelling')

    def test_test_size_fraction(self):
        assert 0 < config.TEST_SIZE < 1

    def test_cv_folds_positive(self):
        assert config.CV_FOLDS >= 2
