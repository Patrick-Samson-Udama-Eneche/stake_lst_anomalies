"""
Central configuration for LST Modeling Project - Updated for AOI Processing
"""
import os
from pathlib import Path
from typing import Optional, List
from datetime import datetime

# Base paths
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
INPUT_DIR = DATA_DIR / "inputs"
OUTPUT_DIR = DATA_DIR / "outputs"
DOCS_DIR = PROJECT_ROOT / "docs"
SRC_DIR = PROJECT_ROOT / "src"
SECRETS_DIR = PROJECT_ROOT / "secrets"  # Secure credentials storage

# Environment variables with defaults
INPUT_DATA_PATH = os.getenv("INPUT_DATA_PATH", str(INPUT_DIR))
OUTPUT_DATA_PATH = os.getenv("OUTPUT_DATA_PATH", str(OUTPUT_DIR))

# Project parameters
PROJECT_STUDY_YEAR = 2024  # Reference year for analysis

# Processing parameters
RANDOM_STATE = int(os.getenv("RANDOM_STATE", "42"))
N_JOBS = int(os.getenv("N_JOBS", "-1"))

# Model parameters
TEST_SIZE = float(os.getenv("TEST_SIZE", "0.2"))
CV_FOLDS = int(os.getenv("CV_FOLDS", "5"))

# Visualization
FIGURE_DPI = int(os.getenv("FIGURE_DPI", "300"))
PLOT_STYLE = os.getenv("PLOT_STYLE", "default")

# CRS settings (common projections)
WGS84 = "EPSG:4326"
WEB_MERCATOR = "EPSG:3857"
UTM_ZONE_32N = "EPSG:32632"  # For Nigeria (approximate)

# =============================================================================
# VALID CITY NAMES (from Major_cities_population_Nigeria.csv)
# =============================================================================
# These are the 50 cities recognized by the pipeline.  City names passed via
# CLI (--cities) or selected in Notebook 01 are validated against this list.
# Spelling and capitalisation must match exactly.  Use validate_city_names()
# to check user input and get suggestions for typos.
VALID_CITIES: List[str] = [
    "Aba", "Abakaliki", "Abeokuta", "Abuja", "Ado-Ekiti",
    "Akure", "Bauchi", "Benin City", "Birnin Kebbi", "Calabar",
    "Effon Alaiye", "Enugu", "Gboko", "Gombe", "Gwagwalada",
    "Ibadan", "Ife", "Igbidu", "Ijebu-Ode", "Ikorodu",
    "Ikot Ekpene", "Ilesha", "Ilorin", "Jos", "Kaduna",
    "Kano", "Katsina", "Lafia", "Lagos", "Lokoja",
    "Maiduguri", "Makurdi", "Minna", "Nnewi", "Ogbomosho",
    "Okene", "Okpogho", "Ondo", "Onitsha", "Oshogbo",
    "Owerri", "Oyo", "Port Harcourt", "Potiskum", "Saki",
    "Sokoto", "Umuahia", "Uyo", "Warri", "Zaria",
]


def validate_city_names(names: List[str], *, strict: bool = False) -> List[str]:
    """
    Validate a list of city names against VALID_CITIES.

    For each unrecognised name the function prints a warning and suggests
    the closest valid name (simple case-insensitive + substring matching).

    Parameters
    ----------
    names : list[str]
        City names supplied by the user.
    strict : bool
        If True, raise ValueError on the first invalid name instead of
        printing a warning and continuing.

    Returns
    -------
    list[str]
        Only the names that matched a valid city (original casing from
        VALID_CITIES is used so downstream code always gets the canonical form).
    """
    valid_lower = {c.lower(): c for c in VALID_CITIES}
    accepted: List[str] = []

    for name in names:
        key = name.strip().lower()
        if key in valid_lower:
            accepted.append(valid_lower[key])
        else:
            # Find close matches
            from difflib import get_close_matches
            suggestions = get_close_matches(name, VALID_CITIES, n=3, cutoff=0.5)
            hint = f"  Did you mean: {', '.join(suggestions)}" if suggestions else ""
            msg = f"[ERROR] '{name}' is not a valid city name.{hint}"
            if strict:
                raise ValueError(msg)
            print(msg)
            print(f"         Run with --list-cities to see all {len(VALID_CITIES)} valid names.")

    return accepted


# =============================================================================
# CITIES ABOVE 1 MILLION POPULATION (2024 estimates)
# =============================================================================
# These 16 cities have population >= 1 million based on 2024 data.
# Population figures are in thousands (e.g., 16536 = ~16.5 million).
CITIES_ABOVE_1M: List[str] = [
    "Lagos",         # 16,536k
    "Kano",          # 4,491k
    "Abuja",         # 4,026k
    "Ibadan",        # 4,004k
    "Port Harcourt", # 3,637k
    "Benin City",    # 1,973k
    "Onitsha",       # 1,695k
    "Uyo",           # 1,393k
    "Nnewi",         # 1,301k
    "Aba",           # 1,230k
    "Kaduna",        # 1,221k
    "Ikorodu",       # 1,145k
    "Ilorin",        # 1,064k
    "Warri",         # 1,031k
    "Owerri",        # 1,023k
    "Jos",           # 1,001k
]

# Test cities for quick development/debugging runs
TEST_CITIES: List[str] = [
    "Lagos",
    "Abuja",
    "Kano",
    "Jos",
    "Port Harcourt",
]

# =============================================================================
# CITY SELECTION CONFIGURATION
# =============================================================================
# Control which cities to process in notebooks.
# 
# CITY_SELECTION_MODE options:
#   - "ALL"      : Process all 50 cities in the CSV file
#   - "ABOVE_1M" : Process 16 cities with population >= 1 million (default)
#   - "TEST"     : Process 5 test cities (Lagos, Abuja, Kano, Jos, Port Harcourt)
#   - "SPECIFIC" : Process only the cities listed in SELECTED_CITIES
#
# SELECTED_CITIES:
#   - Only used when CITY_SELECTION_MODE = "SPECIFIC"
#   - Can be any cities from VALID_CITIES (all 50 Nigerian cities)
#   - Example: ["Lagos", "Abuja", "Enugu", "Maiduguri"]


CITY_SELECTION_MODE: str = "ALL"  # Options: "ALL", "ABOVE_1M", "TEST", or "SPECIFIC"


SELECTED_CITIES: List[str] = [
    # Add cities here when using CITY_SELECTION_MODE = "SPECIFIC"
    # Can select from any of the 50 cities in VALID_CITIES
    # "Lagos",
    # "Enugu",
    # "Maiduguri",
]


def get_cities_to_process() -> List[str]:
    """
    Get the list of cities to process based on CITY_SELECTION_MODE.
    
    Returns
    -------
    list[str]
        List of city names to process.
        
    Raises
    ------
    ValueError
        If CITY_SELECTION_MODE is invalid or SELECTED_CITIES contains
        invalid city names.
    """
    if CITY_SELECTION_MODE == "ALL":
        return VALID_CITIES.copy()
    elif CITY_SELECTION_MODE == "ABOVE_1M":
        return CITIES_ABOVE_1M.copy()
    elif CITY_SELECTION_MODE == "TEST":
        return TEST_CITIES.copy()
    elif CITY_SELECTION_MODE == "SPECIFIC":
        if not SELECTED_CITIES:
            raise ValueError(
                "CITY_SELECTION_MODE is 'SPECIFIC' but SELECTED_CITIES is empty. "
                "Please add cities to SELECTED_CITIES in config.py."
            )
        # Validate selected cities against all valid cities
        invalid = [c for c in SELECTED_CITIES if c not in VALID_CITIES]
        if invalid:
            from difflib import get_close_matches
            suggestions = {c: get_close_matches(c, VALID_CITIES, n=2, cutoff=0.5) for c in invalid}
            hint = "\n".join(f"  - '{c}': did you mean {s}?" for c, s in suggestions.items() if s)
            raise ValueError(
                f"Invalid cities in SELECTED_CITIES: {invalid}.\n"
                f"Valid cities are: {VALID_CITIES}\n"
                f"{hint if hint else ''}"
            )
        return SELECTED_CITIES.copy()
    else:
        raise ValueError(
            f"Invalid CITY_SELECTION_MODE: '{CITY_SELECTION_MODE}'. "
            "Must be 'ALL', 'ABOVE_1M', 'TEST', or 'SPECIFIC'."
        )


# =============================================================================
# AOI PROCESSING CONFIGURATION (Notebook 01)
# =============================================================================
# Defines how city Areas of Interest are constructed from urban polygons.
# If adapting to a new country, update all three file paths below.

# Paths to your geospatial input files (relative to project root):
AOI_DATA_PATHS = {
    'cities_csv': 'data/inputs/geospatial_features/Major_cities_population_Nigeria.csv',        # ← CHANGE THIS  (CSV with 'Urban Agglomeration' column)
    'urban_geojson': 'data/inputs/geospatial_features/urban_landscape_typology_Nigeria.geojson', # ← CHANGE THIS  (urban area polygons)
    'boundary_geojson': 'data/inputs/geospatial_features/boundary_Nigeria.geojson'               # ← CHANGE THIS  (country boundary for clipping)
}

# Buffer distances around city polygons (in metres):
ADJACENT_POLYGON_BUFFER = int(os.getenv("ADJACENT_POLYGON_BUFFER", "1000"))  # ← CHANGE THIS  (search radius for nearby urban polygons, default 1 km)
AOI_BUFFER_DISTANCE = int(os.getenv("AOI_BUFFER_DISTANCE", "10000"))          # ← CHANGE THIS  (AOI buffer around merged polygons, default 10 km)

# CRS for AOI processing (usually no change needed):
INPUT_CRS = WGS84
PROCESSING_CRS = WEB_MERCATOR  # Used for metric distance calculations
OUTPUT_CRS = WGS84

# Visualization parameters for AOI maps
AOI_VIS_CONFIG = {
    'map_figsize': (8, 5),
    'population_plot_figsize': (6, 4),
    'dashboard_figsize': (10, 6),
    'interactive_zoom': 11,
    
    # Color schemes
    'colors': {
        'aoi_boundary': 'purple',
        'buffer_zone': 'lightblue', 
        'main_polygon': 'red',
        'adjacent_polygon': 'orange',
        'city_marker': 'green',
        'target_city': 'red'
    },
    
    # Map styling
    'buffer_alpha': 0.3,
    'polygon_alpha': 0.7,
    'city_marker_size': 80,
    'target_city_size': 120
}

# Population analysis configuration
POPULATION_CONFIG = {
    'years_range': list(range(1950, 2036, 5)),  # Every 5 years
    'growth_periods': {
        'pre_2024': (1950, 2024),
        'post_2024': (2024, 2035), 
        'overall': (1950, 2035)
    },
    'trend_analysis_step': 2  # For 10-year growth rates
}

# =============================================================================
# GOOGLE EARTH ENGINE CREDENTIALS  (auto-resolved — see secrets/README.md)
# =============================================================================
# Place your GEE service account JSON in secrets/gee_service_account.json.
# See secrets/gee_service_account.json.example for the expected format.
# The code tries /secrets/ first, then falls back to /data/inputs/ (legacy).
_GEE_KEY_NEW = SECRETS_DIR / "gee_service_account.json"
_GEE_KEY_OLD = INPUT_DIR / "gee_service_account.json"

if _GEE_KEY_NEW.exists():
    _GEE_SERVICE_JSON = _GEE_KEY_NEW
elif _GEE_KEY_OLD.exists():
    _GEE_SERVICE_JSON = _GEE_KEY_OLD
    import warnings
    warnings.warn(
        "GEE credentials found in legacy location. Please move to /secrets/ directory.",
        DeprecationWarning,
        stacklevel=2
    )
else:
    _GEE_SERVICE_JSON = None

GEE_CONFIG = {
    'service_json': os.getenv("GEE_SERVICE_JSON", str(_GEE_SERVICE_JSON) if _GEE_SERVICE_JSON else ""),
    'project_id': os.getenv("GEE_PROJECT_ID", "your-gee-project-id"),    # ← CHANGE THIS  (your GEE Cloud project ID)
    'collection_name': os.getenv("GEE_COLLECTION", "AOI_Nigeria_Cities"),  # ← CHANGE THIS  (GEE asset collection name)
    
    # LST visualization parameters (colour ramp for map exports)
    'lst_vis_params': {
        'min': 24,
        'max': 38,
        'palette': ['blue', 'cyan', 'yellow', 'orange', 'red']
    },
    
    # MODIS collection
    'modis_collection': 'MODIS/061/MOD11A1',
    'lst_band': 'LST_Day_1km',
    'scale': 1000,
    'max_pixels': 1e9
}

# =============================================================================
# EUMETSAT CONFIGURATION (MSG SEVIRI LST Data)
# =============================================================================
# Place your EUMETSAT credentials in secrets/eumetsat_credentials.json.
# See secrets/eumetsat_credentials.json.example for the expected format.
# Register at https://eoportal.eumetsat.int/ to obtain API keys.

_EUMETSAT_CREDS = SECRETS_DIR / "eumetsat_credentials.json"

EUMETSAT_CONFIG = {
    'credentials_file': str(_EUMETSAT_CREDS) if _EUMETSAT_CREDS.exists() else None,
    'data_store_url': 'https://api.eumetsat.int/data/search-products/os',
    'collection_id': 'EO:EUM:DAT:MSG:LST',      # MSG SEVIRI LST product ID
    
    # Time windows (UTC) — aligned with MODIS Aqua overpass times.
    # Adjust if using a different satellite for cross-validation.
    'night_hours': [1, 2, 3],                     # 01:00–03:00 UTC (AQUA ~01:30)
    'day_hours': [13, 14, 15],                     # 13:00–15:00 UTC (AQUA ~13:30)
    
    # Processing parameters
    'temporal_resolution': 15,                     # SEVIRI repeat cycle (minutes)
    'aggregation_method': 'median',                # How 15-min slots are combined: 'median' or 'mean'
    'quality_filter': True,                        # Apply SEVIRI quality flags
}

# =============================================================================
# LST TEMPORAL ANALYSIS CONFIGURATION (Notebooks 03–04)
# =============================================================================
# MODIS collection IDs, band names, and QA settings for LST extraction.
# The scale factor (0.02) and offset (-273.15) convert raw DN to Celsius.
LST_CONFIG = {
    'collections': {
        'terra_daily': {
            'id': 'MODIS/061/MOD11A1',
            'day_band': 'LST_Day_1km',
            'night_band': 'LST_Night_1km',
            'day_qa_band': 'QC_Day',
            'night_qa_band': 'QC_Night',
            'scale_factor': 0.02,
            'offset': -273.15,
            'description': 'Terra Daily LST'
        },
        'aqua_daily': {
            'id': 'MODIS/061/MYD11A1',
            'day_band': 'LST_Day_1km',
            'night_band': 'LST_Night_1km',
            'day_qa_band': 'QC_Day',
            'night_qa_band': 'QC_Night',
            'scale_factor': 0.02,
            'offset': -273.15,
            'description': 'Aqua Daily LST'
        }
    },
    'primary_collection': 'aqua_daily',                 # ← CHANGE THIS  ('terra_daily' or 'aqua_daily')
    'scale': 1000,                                       # MODIS native resolution (metres)
    'max_cloud_cover': 20,                               # ← CHANGE THIS  (max cloud cover %, 0–100)
    
    # Which LST period to analyse: 'day', 'night', or 'both'
    'lst_time': 'both',                                  # ← CHANGE THIS
    
    # Quality hierarchy settings
    'quality_hierarchy': {
        'strict': {
            'description': 'Highest quality - LST error <= 1K',
            'qa_bits': 0,
            'color': '#1a9850',
            'priority': 1
        },
        'moderate': {
            'description': 'Medium quality - LST error <= 2K',
            'qa_bits': 1,
            'color': '#ffd966',
            'priority': 2
        },
        'loose': {
            'description': 'Lower quality - LST error <= 3K',
            'qa_bits': 2,
            'color': '#d73027',
            'priority': 3
        }
    },
    'qa_levels_to_use': ['strict', 'moderate']           # ← CHANGE THIS  (which QA levels to include in analysis)
}

# Helper function to determine dynamic end date and years
def _get_dynamic_temporal_range():
    """
    Dynamically calculate end date and years based on current date.
    
    Logic:
    - Only includes complete years (years that have finished)
    - Current year is excluded since it's incomplete
    - Always uses (current_year - 1) as the last year with complete data
    
    Examples:
    - Running in January 2026 → includes up to 2025
    - Running in December 2026 → includes up to 2025
    - Running in January 2027 → includes up to 2026
    
    Returns:
        tuple: (end_date_string, list_of_years)
    """
    now = datetime.now()
    current_year = now.year
    
    # Use previous year as end year (only complete years)
    end_year = current_year - 1
    
    # Create end date string
    end_date = f"{end_year}-12-31"
    
    # Create years list (2006 to end_year inclusive)
    start_year = 2006
    years = list(range(start_year, end_year + 1))
    
    return end_date, years

# Get dynamic temporal range
_DYNAMIC_END_DATE, _DYNAMIC_YEARS = _get_dynamic_temporal_range()

# Temporal aggregation: defines the time range for trend analysis.
# end_date and years are auto-calculated to include only complete years.
TEMPORAL_CONFIG = {
    'start_date': '2006-01-01',                          # ← CHANGE THIS  (first year of your study period)
    'end_date': _DYNAMIC_END_DATE,                       # Auto-calculated (last complete year)
    'aggregation_methods': ['median', 'mean', 'min', 'max'],
    'primary_method': 'median',                          # ← CHANGE THIS  ('median' recommended for LST)
    'temporal_units': ['monthly', 'yearly'],
    'months': list(range(1, 13)),
    'years': _DYNAMIC_YEARS                              # Auto-calculated from start_date to last complete year
}

# Visualization configuration for LST analysis
VISUALIZATION_CONFIG = {
    'day': {
        'min_temp': 20,
        'max_temp': 50,
        'highlight_temp': 30,
        'colors': ['#FFFFCC', '#FFEDA0', '#FED976', '#FEB24C', '#FD8D3C', '#FC4E2A', '#E31A1C', '#BD0026', '#800026'],
        'colormap_name': 'LST_day_cmap'
    },
    'night': {
        'min_temp': 10,
        'max_temp': 30,
        'highlight_temp': 20,
        'colors': ['#FFFFCC', '#FFEDA0', '#FED976', '#FEB24C', '#FD8D3C', '#FC4E2A', '#E31A1C', '#BD0026', '#800026'],
        'colormap_name': 'LST_night_cmap'
    },
    'qa_hierarchy': {
        'colors': ['#1a9850', '#ffd966', '#d73027'],
        'labels': ['Strict', 'Moderate', 'Loose'],
        'colormap_name': 'QA_hierarchy_cmap'
    }
}

# Processing options for LST analysis
PROCESSING_OPTIONS = {
    'export_primary_only': True,                          # Export only the primary collection
    'include_trend_analysis': True,                       # Run Mann-Kendall trend tests
    'create_individual_city_maps': True,                  # Generate per-city map figures
    'max_cities_for_individual_maps': 5,                  # ← CHANGE THIS  (cap for individual maps)
    'qa_filtering': 'hierarchical',                       # 'hierarchical' (strict→moderate) or 'simple'
    'save_qa_source_maps': True,                          # Save QA provenance maps
    'dask_chunksize': 2                                   # ← CHANGE THIS  (cities processed in parallel; lower = less RAM)
}

# Project-wide settings shared across multiple notebooks
PROJECT_SETTINGS = {
    'study_year': 2024,                                   # ← CHANGE THIS  (must match PROJECT_STUDY_YEAR above)
    'aoi_pattern': 'City_*/Features/*_AOI_Boundary.geojson',  # Glob pattern for AOI files
    'daily_stats_subdir': 'daily_stats',
    'hot_pct': 0.90,                                      # ← CHANGE THIS  (percentile for hot pixel detection: 0.90=P90, 0.95=P95)
}

# =============================================================================
# DAILY LST ANALYSIS CONFIGURATION (Notebook 04)
# =============================================================================
# Controls hot-event detection thresholds and SEVIRI processing.

DAILY_LST_CONFIG = {
    'hot_percentile': 90,                                 # ← CHANGE THIS  (percentile for hot day/night detection)
    'persistent_threshold': 2,                            # ← CHANGE THIS  (min consecutive days to count as persistent)
    'skip_existing': True,                                # Skip GEE extraction if output files already exist
    'study_year': 2024,                                   # ← CHANGE THIS  (must match PROJECT_STUDY_YEAR)
}

# ERA5-Land parameters (cross-validation data source for daily analysis)
ERA5_LAND_CONFIG = {
    'night_hours': [1, 2, 3],                             # UTC hours for night window
    'day_hours': [13, 14, 15],                             # UTC hours for day window
    'aggregation': 'median',                               # 'median' or 'mean' within window
    'temp_conversion': True,                               # Convert Kelvin → Celsius
}

# ---------------------------------------------------------------------------
# Extraction method versioning
# ---------------------------------------------------------------------------
# Bump the version string whenever the extraction methodology changes
# (e.g. spatial reducer, QA filtering, scale).  The skip logic in Notebook 04
# compares cached metadata against these values and re-extracts on mismatch.
EXTRACTION_METHODS = {
    'modis': {
        'version': 'v1.0',
        'spatial_reducer': 'stats',                        # min/median/mean/max combined
        'scale': 1000,
        'qa_filtering': 'hierarchical',
    },
    'era5': {
        'version': 'v1.2',                                # v1.0=first, v1.1=mean, v1.2=median
        'spatial_reducer': 'median',
        'scale': 11132,
        'temporal_aggregation': 'min_median_mean_max',
    },
}

# MODIS QA filtering thresholds
MODIS_QA_CONFIG = {
    'strict_quality_bits': [0, 1],                         # QC bits 0-1 = 00 (highest quality)
    'moderate_quality_bits': [0, 1],                       # QC bits 0-1 = 01 (acceptable quality)
    'temp_min': 5,                                         # ← CHANGE THIS  (min valid LST in °C — filters sensor errors)
    'temp_max': 70,                                        # ← CHANGE THIS  (max valid LST in °C)
    'use_hierarchical_qa': True,                           # If True, use strict first, fill gaps with moderate
}

# Dask parallelisation — tune to your machine's resources
DASK_CONFIG = {
    'n_workers': 4,                                        # ← CHANGE THIS  (number of parallel workers)
    'threads_per_worker': 2,                               # ← CHANGE THIS  (threads per worker)
    'memory_limit': '2GB',                                 # ← CHANGE THIS  (RAM per worker)
}

# Master database configuration
MASTER_DB_CONFIG = {
    'wgs84_path': 'data/outputs/Master_AOI_Database_WGS84.geojson',
    'web_mercator_path': 'data/outputs/Master_AOI_Database_WebMercator.geojson',
    'stats_csv_path': 'data/outputs/Master_AOI_Statistics.csv',
    'search_pattern': '**/*/AOI_Boundary.geojson'
}

# Export configuration
EXPORT_CONFIG = {
    'formats': ['geojson', 'csv', 'json'],
    'include_gee': True,
    'create_figures': True,
    'figure_formats': ['png', 'pdf']
}

# Dashboard configuration
DASHBOARD_CONFIG = {
    'scalebar_length_km': 100,
    'north_arrow_size': 0.05,
    'legend_location': 'upper left',
    'table_header_color': '#4472C4',
    'body_font_size': 8,
    'title_font_size': 10
}

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_output_dir(notebook_name: str) -> Path:
    """Get output directory for specific notebook"""
    output_path = Path(OUTPUT_DATA_PATH) / notebook_name
    output_path.mkdir(parents=True, exist_ok=True)
    return output_path

def get_input_path(filename: str, subfolder: Optional[str] = None) -> Path:
    """Get input file path"""
    input_path = Path(INPUT_DATA_PATH)
    if subfolder:
        input_path = input_path / subfolder
    return input_path / filename

def get_aoi_data_path(data_type: str) -> Path:
    """Get AOI data file path"""
    if data_type not in AOI_DATA_PATHS:
        raise ValueError(f"Unknown data type: {data_type}. Available: {list(AOI_DATA_PATHS.keys())}")
    return PROJECT_ROOT / AOI_DATA_PATHS[data_type]

def get_city_output_dir(city_name: str) -> Path:
    """Get output directory for specific city"""
    output_path = Path(OUTPUT_DATA_PATH) / f"City_{city_name}"
    output_path.mkdir(parents=True, exist_ok=True)
    return output_path

def get_figure_dir(city_name: str) -> Path:
    """Get figure directory for specific city"""
    figure_path = get_city_output_dir(city_name) / "Figures"
    figure_path.mkdir(parents=True, exist_ok=True)
    return figure_path

def validate_config() -> bool:
    """Validate configuration settings"""
    try:
        # Check if required data files exist
        for data_type, path in AOI_DATA_PATHS.items():
            full_path = PROJECT_ROOT / path
            if not full_path.exists():
                print(f"Warning: {data_type} file not found: {full_path}")
                return False
        
        # Check if output directories can be created
        test_output = get_output_dir("test")
        test_output.rmdir()  # Clean up
        
        print("Configuration validation passed")
        return True
        
    except Exception as e:
        print(f"Configuration validation failed: {e}")
        return False

# Default city for single-city testing / previews
DEFAULT_CITY = "Lagos"                                             # ← CHANGE THIS

# Available cities — auto-populated by load_available_cities() at runtime
AVAILABLE_CITIES = []

# =============================================================================
# HOTSPOT ANALYSIS CONFIGURATION (Notebook 05)
# =============================================================================
# Defines percentile thresholds, spatial statistics, KDE bandwidth, and
# polygon delineation parameters for UHI hotspot detection.

# Study year (derived from PROJECT_SETTINGS to keep a single source of truth)
STUDY_YEAR = PROJECT_SETTINGS['study_year']

# Cities — auto-populated at runtime by load_cities_from_daily_analysis()
CITIES = []

# GHSL Population years available
GHSL_AVAILABLE_YEARS = [1975, 1980, 1985, 1990, 1995, 2000, 2005, 2010, 2015, 2020, 2025, 2030]

def get_closest_ghsl_year(study_year: int, verbose: bool = True) -> int:
    """
    Automatically select closest GHSL year to study year with informative output.
    
    GHSL R2023A Population Grid provides data for specific epochs:
    - Historical: 1975, 1980, 1985, 1990, 1995, 2000
    - Recent: 2005, 2010, 2015, 2020
    - Projected: 2025, 2030
    
    Data Source: JRC/GHSL/P2023A/GHS_POP (Google Earth Engine)
    Resolution: 100m global grid
    
    Parameters:
    -----------
    study_year : int
        Year of LST study (e.g., 2024)
    verbose : bool, optional
        Print selection details (default: True)
    
    Returns:
    --------
    int : Closest available GHSL year
    
    Examples:
    ---------
    >>> get_closest_ghsl_year(2024)
    Selecting GHSL Population year for LST study year: 2024
    Available GHSL years: [1975, 1980, ..., 2020, 2025, 2030]
    Years around study year: 2020 (4 years before), 2025 (1 year after)
    ✓ Selected: 2025 (closest match, +1 year from study year)
    2025
    
    >>> get_closest_ghsl_year(2019, verbose=False)
    2020
    """
    closest_year = min(GHSL_AVAILABLE_YEARS, key=lambda x: abs(x - study_year))
    
    if verbose:
        # Find years immediately before and after study year
        years_before = [y for y in GHSL_AVAILABLE_YEARS if y <= study_year]
        years_after = [y for y in GHSL_AVAILABLE_YEARS if y > study_year]
        
        year_before = max(years_before) if years_before else None
        year_after = min(years_after) if years_after else None
        
        print(f"\nSelecting GHSL Population year for LST study year: {study_year}")
        print(f"Available GHSL years: {GHSL_AVAILABLE_YEARS}")
        
        if year_before and year_after:
            diff_before = study_year - year_before
            diff_after = year_after - study_year
            print(f"Years around study year: {year_before} ({diff_before} years before), {year_after} ({diff_after} years after)")
        elif year_before:
            print(f"Year before study year: {year_before} ({study_year - year_before} years before)")
        elif year_after:
            print(f"Year after study year: {year_after} ({year_after - study_year} years after)")
        
        diff = closest_year - study_year
        direction = f"+{diff}" if diff > 0 else str(diff)
        print(f"✓ Selected: {closest_year} (closest match, {direction} years from study year)\n")
    
    return closest_year

# Landscape assessment configuration
LANDSCAPE_ASSESSMENT = {
    'physiographic_geojson': 'data/inputs/geospatial_features/landscape_character_nigeria.geojson',
    'categories': [
        'elevation_range_m',
        'slope_category',
        'drainage_density',
        'land_cover_type',
        'soil_type',
        'climate_zone'
    ]
}

# =============================================================================
# GEE DATA VERIFICATION FUNCTIONS
# =============================================================================

def verify_ghsl_availability() -> dict:
    """
    Verify GHSL Population data availability in Google Earth Engine.
    Tests connection and checks for available years in the collection.
    
    Returns:
    --------
    dict : {
        'gee_available': bool,
        'ghsl_collection_exists': bool,
        'available_years': list,
        'missing_years': list,
        'status_message': str
    }
    
    Usage:
    ------
    >>> status = verify_ghsl_availability()
    >>> if status['gee_available']:
    >>>     print(f"GHSL years available: {status['available_years']}")
    """
    result = {
        'gee_available': False,
        'ghsl_collection_exists': False,
        'available_years': [],
        'missing_years': [],
        'status_message': ''
    }
    
    try:
        import ee
        
        # Try to initialize GEE with service account
        try:
            # Use service account credentials if available
            if GEE_CONFIG['service_json'] and Path(GEE_CONFIG['service_json']).exists():
                credentials = ee.ServiceAccountCredentials(
                    email=None,  # Will be read from JSON
                    key_file=GEE_CONFIG['service_json']
                )
                ee.Initialize(credentials=credentials, project=GEE_CONFIG['project_id'])
            else:
                # Fallback to default authentication
                ee.Initialize(project=GEE_CONFIG['project_id'])
            
            result['gee_available'] = True
            print(f"✓ Google Earth Engine connection established (project: {GEE_CONFIG['project_id']})")
        except Exception as init_error:
            result['status_message'] = f"GEE initialization failed: {init_error}"
            print(f"✗ {result['status_message']}")
            return result
        
        # Check GHSL collection
        ghsl_collection_id = "JRC/GHSL/P2023A/GHS_POP"
        try:
            ghsl_collection = ee.ImageCollection(ghsl_collection_id)
            result['ghsl_collection_exists'] = True
            print(f"✓ GHSL collection found: {ghsl_collection_id}")
            
            # Get all images in collection and check their years
            # GHSL images are individual, not filtered by year property
            try:
                collection_info = ghsl_collection.getInfo()
                collection_features = collection_info.get('features', [])
                
                # Extract years from image IDs (format: JRC/GHSL/P2023A/GHS_POP/2020)
                found_years = set()
                for feature in collection_features:
                    img_id = feature.get('id', '')
                    # Extract year from the end of ID
                    year_str = img_id.split('/')[-1]
                    if year_str.isdigit():
                        found_years.add(int(year_str))
                
                # Check which expected years are available
                available_years = []
                for year in GHSL_AVAILABLE_YEARS:
                    if year in found_years:
                        available_years.append(year)
                        print(f"  ✓ GHSL {year} available")
                    else:
                        result['missing_years'].append(year)
                        # Don't print missing years - too verbose
                
                result['available_years'] = available_years
                
                if len(available_years) == len(GHSL_AVAILABLE_YEARS):
                    result['status_message'] = f"All {len(available_years)} GHSL years verified in GEE"
                    print(f"\n✓ {result['status_message']}")
                elif len(available_years) > 0:
                    result['status_message'] = f"{len(available_years)}/{len(GHSL_AVAILABLE_YEARS)} GHSL years available"
                    print(f"\n✓ {result['status_message']}")
                    if result['missing_years']:
                        print(f"  Note: Years {min(result['missing_years'])}-{max(result['missing_years'])} may be outside dataset range")
                else:
                    result['status_message'] = "No GHSL years found in collection"
                    print(f"\n⚠ {result['status_message']}")
                    
            except Exception as year_check_error:
                # Fallback: assume all years available if we can't verify
                result['available_years'] = GHSL_AVAILABLE_YEARS
                result['status_message'] = f"GHSL collection accessible (year verification skipped: {year_check_error})"
                print(f"\n⚠ {result['status_message']}")
            
        except Exception as collection_error:
            result['status_message'] = f"GHSL collection access failed: {collection_error}"
            print(f"✗ {result['status_message']}")
    
    except ImportError:
        result['status_message'] = "Earth Engine Python API not installed (pip install earthengine-api)"
        print(f"✗ {result['status_message']}")
    except Exception as e:
        result['status_message'] = f"Verification failed: {e}"
        print(f"✗ {result['status_message']}")
    
    return result

def load_available_cities() -> List[str]:
    """Load available cities from CSV"""
    try:
        import pandas as pd
        cities_path = get_aoi_data_path('cities_csv')
        df = pd.read_csv(cities_path)
        cities = df['Urban Agglomeration'].dropna().tolist()
        global AVAILABLE_CITIES
        AVAILABLE_CITIES = cities
        return cities
    except Exception as e:
        print(f"Failed to load cities: {e}")
        return []

def load_cities_from_daily_analysis(study_year: int = None) -> List[str]:
    """
    Load cities that have SEVIRI persistent heat rasters from Notebook 04.
    Scans for SEVIRI_LST directory with day and night median rasters.
    
    **What Notebook 05 needs from Notebook 04:**
    - SEVIRI day persistent heat raster (median LST during longest event)
    - SEVIRI night persistent heat raster (median LST during longest event)
    - Metadata JSON with event dates and duration
    
    Parameters:
    -----------
    study_year : int, optional
        Year to check for (default: PROJECT_SETTINGS['study_year'])
    
    Returns:
    --------
    List[str] : City names with available SEVIRI persistent heat rasters
    """
    if study_year is None:
        study_year = PROJECT_SETTINGS['study_year']
    
    try:
        seviri_dir = OUTPUT_DIR / "04_trend_analysis_daily" / "SEVIRI_LST"
        if not seviri_dir.exists():
            print(f"⚠ Warning: SEVIRI output directory not found: {seviri_dir}")
            print(f"  Please run Notebook 04 SEVIRI processing first.")
            return []
        
        cities = []
        print(f"\nScanning for cities with SEVIRI persistent heat rasters...")
        print("-" * 70)
        
        for item in seviri_dir.iterdir():
            if item.is_dir() and item.name.startswith("City_"):
                city_name = item.name.replace("City_", "").replace("_", " ")
                
                # Check for clipped day and night rasters (WGS84 1km)
                # Use actual directory name (not city_name) for glob pattern to handle spaces correctly
                dir_city_name = item.name.replace("City_", "")
                day_files = list(item.glob(f"{dir_city_name}_SEVIRI_day_*_median_WGS84_1km_clipped.tif"))
                night_files = list(item.glob(f"{dir_city_name}_SEVIRI_night_*_median_WGS84_1km_clipped.tif"))
                
                if not day_files:
                    print(f"  ✗ {city_name}: Missing day raster")
                    continue
                
                if not night_files:
                    print(f"  ✗ {city_name}: Missing night raster")
                    continue
                
                # Check for metadata
                metadata_pattern = f"{dir_city_name}_SEVIRI_day_*_median_MSG3km_metadata.json"
                metadata_files = list(item.glob(metadata_pattern))
                
                if metadata_files:
                    cities.append(city_name)
                    print(f"  ✓ {city_name}: Day + Night rasters with metadata")
                else:
                    cities.append(city_name)
                    print(f"  ⚠ {city_name}: Day + Night rasters (no metadata)")
        
        # Update global CITIES variable
        global CITIES
        CITIES = sorted(cities)
        
        print("-" * 70)
        if not CITIES:
            print(f"\n⚠ No cities with SEVIRI persistent heat rasters found.")
            print(f"\nTo use Notebook 05, please:")
            print(f"  1. Run Notebook 04 (SEVIRI processing section) first")
            print(f"  2. Ensure it completes for at least one city")
            print(f"  3. Check output directory: {seviri_dir}")
        else:
            print(f"\n✓ Found {len(CITIES)} cities with SEVIRI persistent heat rasters")
        
        return CITIES
    except Exception as e:
        print(f"✗ Failed to load cities from SEVIRI outputs: {e}")
        import traceback
        traceback.print_exc()
        return []

# =============================================================================
# HOTSPOT ANALYSIS CONFIGURATION (Notebook 05)
# =============================================================================

# Hotspot detection methods
HOTSPOT_CONFIG = {
    # Percentile thresholds for binary hot/extreme classification
    'percentile_hot': 90,                                 # ← CHANGE THIS  (P90 = top 10% of LST pixels)
    'percentile_extreme': 95,                             # ← CHANGE THIS  (P95 = top  5% of LST pixels)
    
    # DBSCAN spatial clustering of hot pixels
    'dbscan_epsilon_km': 2.0,                             # ← CHANGE THIS  (max distance between cluster members, km)
    'dbscan_min_samples': 3,                              # ← CHANGE THIS  (min pixels per cluster)
    
    # Getis-Ord Gi* spatial statistics
    'spatial_weights': 'queen',                           # ← CHANGE THIS  ('queen' = 8 neighbours, 'rook' = 4)
    'lisa_permutations': 999,                             # Permutations for p-value estimation
    'gi_star_alpha': 0.05,                                # ← CHANGE THIS  (significance threshold)
    
    # Pixel resolution (must match your input raster grid)
    'pixel_area_km2': 1.0,                                # ← CHANGE THIS  if using non-1 km data
}

# KDE (Kernel Density Estimation) — converts hot-pixel clusters into smooth polygons
KDE_CONFIG = {
    # Bandwidth: controls smoothness.  'scott' and 'silverman' are data-driven;
    # or supply a float (e.g. 0.01) for manual bandwidth in degrees.
    'bandwidth_method': 'scott',                          # ← CHANGE THIS  ('scott', 'silverman', or float)
    'grid_resolution_factor': 0.5,                        # Grid cell size as fraction of pixel size
    'max_grid_size': 1000,                                # Cap on grid dimension (prevents OOM)
    
    # Contour levels — each produces a nested polygon ring
    'contour_levels': [0.50, 0.75, 0.90],                 # ← CHANGE THIS  (density fractions to extract)
    
    # Polygon post-processing
    'min_polygon_area_km2': 1.0,                          # ← CHANGE THIS  (drop polygons smaller than this)
    'simplify_tolerance': 0.0001,                         # Douglas-Peucker tolerance (degrees)
    
    # Output CRS
    'output_crs': 'EPSG:4326',
}

# Resampling — downscales binary hot-pixel mask before KDE for speed
RESAMPLE_CONFIG = {
    'resolution_m': 250,                                  # ← CHANGE THIS  (target resolution; 250 m ≈ 16× fewer cells than 1 km)
    'method': 'bilinear',                                 # 'nearest', 'bilinear', or 'cubic'
    'order': 1,                                           # Scipy zoom order (0=nearest, 1=bilinear, 3=cubic)
    'min_pixels_for_kde': 10,                             # Skip KDE if fewer hot pixels than this
}

# Landscape enrichment data (Section 4 of NB05)
# The GeoJSON must contain polygon geometries with the listed attribute columns.
LANDSCAPE_DATA_PATH = INPUT_DIR / "geospatial_features" / "landscape_ch_polygons_with_class_metrics.geojson"  # ← CHANGE THIS
LANDSCAPE_CLASS_ATTRIBUTES = ['Elevation_Class', 'Climate_Class', 'Landcover_Class', 'Geology_Class']       # ← CHANGE THIS  (columns in your landscape GeoJSON)
LANDSCAPE_CLUSTER_ATTRIBUTE = 'Cluster25'                                                                   # ← CHANGE THIS  (cluster ID column)

# GHSL Population raster — downloaded once from GEE and reused.
# Adjust bounds if adapting to a different country.
GHSL_POP_CONFIG = {
    'gee_asset': 'JRC/GHSL/P2023A/GHS_POP',               # GEE collection ID (do not change)
    'scale': 1000,                                         # Download resolution (metres)
    'crs': 'EPSG:4326',
    'output_dir': INPUT_DIR / 'geospatial_features',
    'filename_template': 'GHSL_POP_{year}_Nigeria_1km.tif', # ← CHANGE THIS  (country name in filename)
    'nigeria_bounds': [2.5, 4.0, 15.0, 14.5],              # ← CHANGE THIS  [west, south, east, north] bounding box
    'boundary_geojson': INPUT_DIR / 'geospatial_features' / 'boundary_Nigeria.geojson',  # ← CHANGE THIS
}

# Canonical colour palette for all 25 landscape clusters.
# These hex codes are the definitive reference used across all charts & maps.
CLUSTER25_COLORS = {
    1:  '#e84db2',
    3:  '#f28e2b',
    4:  '#08ff46',
    5:  '#59a14f',
    6:  '#8cd17d',
    7:  '#b6992d',
    8:  '#f1ce63',
    9:  '#499894',
    10: '#86bcb6',
    11: '#e15759',
    12: '#ff9d9a',
    13: '#79706e',
    14: '#bab0ac',
    15: '#d37295',
    16: '#fabfd2',
    17: '#b07aa1',
    18: '#d4a6c8',
    19: '#9d7660',
    20: '#d7b5a6',
    21: '#babcd7',
    22: '#4e79a7',
    23: '#ff55ff',
    24: '#f28e2b',
    25: '#ffbe7d',
}

# LST raster configuration
LST_RASTER_CONFIG = {
    'valid_range': (0, 100),        # Valid LST range in Celsius (data format: Celsius*100)
    'base_path_key': 'seviri_lst',  # Key for SEVIRI LST base path
    'file_patterns': {
        'day': '{city}_SEVIRI_day_*_median_WGS84_1km_clipped.tif',
        'night': '{city}_SEVIRI_night_*_median_WGS84_1km_clipped.tif'
    }
}

# Hotspot polygon export paths
HOTSPOT_EXPORT_CONFIG = {
    'primary_crs': WGS84,
    'web_crs': WEB_MERCATOR,
    'output_base': OUTPUT_DIR / '05_hotspot_analysis',
    'polygons_subdir': 'hotspot_polygons',
    'filename_template': 'hotspot_polygons_{crs}.geojson'
}

# Survey validation (Section 5 of NB05)
SURVEY_DATA_PATH = INPUT_DIR / "stakeholder_survey" / "master_composite.csv"   # ← CHANGE THIS
VALIDATION_BUFFER_KM = 1.0                                                     # ← CHANGE THIS  (buffer for spatial matching, km)

VALIDATION_CONFIG = {
    'buffer_km': 1.0,                                     # ← CHANGE THIS  (lenient matching radius, km)
    'hotspot_methods': ['P90', 'GI_STAR', 'CONFIRMED'],   # Detection methods to evaluate
    'periods': ['Day', 'Night', 'Persistent'],            # LST periods to validate
    'use_coldspot_validation': False,                     # ← CHANGE THIS  (True = full coldspot delineation)
    'coldspot_temperature_check': True,                   # Quick LST comparison for coldspots
}

# =============================================================================
# LST MODELLING CONFIGURATION (Notebook 06)
# =============================================================================
# Notebook 06 is split into three sub-stages:
#   061 — Feature engineering (extract predictor variables per pixel/zone)
#   062 — Model training (Random Forest / Gradient Boosting regression)
#   063 — Model validation (hold-out test set, spatial cross-validation)
#
# This section configures feature selection, model hyperparameters, and
# validation strategy.  All parameters are also overridable via env vars.

# Output directories for each modelling sub-stage
MODEL_OUTPUT_DIRS = {
    'features':   OUTPUT_DIR / '061_lst_model_variables',   # Predictor variables
    'models':     OUTPUT_DIR / '062_lst_modelling',          # Trained models & predictions
    'validation': OUTPUT_DIR / '063_lst_model_validation',   # Validation reports & plots
}

# Feature engineering (Notebook 061)
# These are candidate predictor variables extracted per pixel or AOI zone.
# Add/remove features as needed for your study area.
MODEL_FEATURES_CONFIG = {
    # Land cover / land use features
    'landcover_features': [
        'NDVI',                     # Normalised Difference Vegetation Index
        'NDBI',                     # Normalised Difference Built-up Index
        'NDWI',                     # Normalised Difference Water Index
        'impervious_fraction',      # Fraction of impervious surface
    ],                                                     # ← CHANGE THIS  (add/remove predictor names)
    
    # Physiographic / landscape features
    'physiographic_features': [
        'elevation_m',              # DEM elevation (metres)
        'slope_degrees',            # Terrain slope
        'aspect',                   # Terrain aspect (0–360°)
        'distance_to_water_m',      # Distance to nearest water body
        'distance_to_road_m',       # Distance to nearest major road
    ],                                                     # ← CHANGE THIS
    
    # Climate / atmospheric features
    'climate_features': [
        'air_temp_2m',              # ERA5-Land 2 m air temperature
        'wind_speed',               # ERA5-Land 10 m wind speed
        'relative_humidity',        # ERA5-Land surface relative humidity
    ],                                                     # ← CHANGE THIS
    
    # Population / urban density
    'population_features': [
        'population_density',       # GHSL population per km²
    ],
    
    # GEE data sources for feature extraction
    'gee_datasets': {
        'dem':       'USGS/SRTMGL1_003',                   # SRTM 30 m DEM
        'landcover': 'ESA/WorldCover/v200',                # ESA WorldCover 10 m
        'ndvi':      'MODIS/061/MOD13A2',                  # MODIS 16-day NDVI
    },
    
    # Spatial resolution for feature rasters (metres)
    'resolution_m': 1000,                                  # ← CHANGE THIS  (should match LST resolution)
}

# Model training (Notebook 062)
MODEL_TRAINING_CONFIG = {
    # Target variable
    'target_variable': 'lst_day_median',                   # ← CHANGE THIS  ('lst_day_median', 'lst_night_median', etc.)
    
    # Models to train (all will be compared)
    'models': {
        'random_forest': {
            'n_estimators': 500,                           # ← CHANGE THIS  (number of trees)
            'max_depth': None,                             # None = no limit; set int to control overfitting
            'min_samples_split': 5,
            'min_samples_leaf': 2,
            'max_features': 'sqrt',                        # 'sqrt', 'log2', or float fraction
            'random_state': RANDOM_STATE,
            'n_jobs': N_JOBS,
        },
        'gradient_boosting': {
            'n_estimators': 300,                           # ← CHANGE THIS
            'learning_rate': 0.05,                         # ← CHANGE THIS  (lower = slower but more robust)
            'max_depth': 6,
            'subsample': 0.8,
            'random_state': RANDOM_STATE,
        },
    },
    
    # Feature importance threshold — drop features below this
    'importance_threshold': 0.01,                          # ← CHANGE THIS  (0 = keep all)
    
    # Test set fraction (also see global TEST_SIZE above)
    'test_size': TEST_SIZE,
    'cv_folds': CV_FOLDS,
    'stratify_by': 'landscape_cluster',                    # ← CHANGE THIS  (column for stratified split; None = random)
}

# Model validation (Notebook 063)
MODEL_VALIDATION_CONFIG = {
    # Metrics to compute
    'metrics': ['r2', 'rmse', 'mae', 'mape'],              # ← CHANGE THIS  (add/remove as needed)
    
    # Spatial cross-validation
    'spatial_cv': {
        'enabled': True,                                   # ← CHANGE THIS  (True = leave-one-city-out CV)
        'method': 'leave_one_city_out',                    # Options: 'leave_one_city_out', 'spatial_kfold'
        'n_splits': 5,                                     # Only used if method = 'spatial_kfold'
    },
    
    # Comparison with stakeholder perceptions
    'stakeholder_comparison': True,                        # Compare model predictions with survey hotspots
    
    # Output formats
    'export_predictions': True,                            # Save predicted LST rasters
    'export_format': 'geotiff',                            # 'geotiff' or 'netcdf'
}