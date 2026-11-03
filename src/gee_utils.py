"""
Google Earth Engine Utilities
==============================

Functions for initializing and interacting with Google Earth Engine API,
including LST data extraction with quality filtering.

MATCHES ORIGINAL NOTEBOOK 04 PROTOCOL EXACTLY
"""

import os
import json
import ee
import pandas as pd
from pathlib import Path
from datetime import datetime
from google.oauth2 import service_account

import config

# A request whose answer is lost (a laptop going to sleep, a dropped network) would otherwise wait
# forever. Earth Engine stops an interactive computation after about five minutes anyway.
REQUEST_DEADLINE_MS = 6 * 60 * 1000
_TRANSIENT = ('timed out', 'timeout', 'deadline', 'too many requests', '429', '500', '502', '503',
              '504', 'internal error', 'connection', 'reset', 'unavailable', 'broken pipe')


def get_info_retrying(ee_object, attempts=3, pause_s=10):
    """ee_object.getInfo(), retried when the failure looks transient (timeout, dropped connection,
    rate limit, server error). Any other error is raised at once, as before."""
    import time as _t
    for attempt in range(attempts):
        try:
            return ee_object.getInfo()
        except Exception as e:
            transient = isinstance(e, TimeoutError) or any(s in str(e).lower() for s in _TRANSIENT)
            if not transient or attempt == attempts - 1:
                raise
            _t.sleep(pause_s * (attempt + 1))


def _save_extraction_metadata(output_path, dataset_type, extra_info=None):
    """
    Save extraction metadata alongside a CSV so the skip logic can detect
    methodology changes (reducer, scale, QA filtering, etc.).

    Parameters
    ----------
    output_path : str or Path
        Path to the CSV that was just saved.
    dataset_type : str
        'modis' or 'era5' – key into ``config.EXTRACTION_METHODS``.
    extra_info : dict, optional
        Additional key/value pairs to store.
    """
    meta_path = Path(output_path).with_suffix('.meta.json')
    metadata = {
        'extraction_date': datetime.now().isoformat(),
        'method': config.EXTRACTION_METHODS[dataset_type],
    }
    if extra_info:
        metadata.update(extra_info)
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2)


def validate_extraction_metadata(output_path, dataset_type):
    """
    Check whether a cached CSV was produced with the current extraction method.

    Parameters
    ----------
    output_path : str or Path
        Path to the CSV file (the ``.meta.json`` sidecar is derived from it).
    dataset_type : str
        'modis' or 'era5' – key into ``config.EXTRACTION_METHODS``.

    Returns
    -------
    (bool, str)
        ``(True, reason)`` if metadata matches the current method,
        ``(False, reason)`` otherwise.
    """
    meta_path = Path(output_path).with_suffix('.meta.json')

    if not meta_path.exists():
        return False, "No metadata file (pre-versioning extraction)"

    with open(meta_path, encoding='utf-8') as f:
        stored = json.load(f)

    current = config.EXTRACTION_METHODS[dataset_type]
    stored_method = stored.get('method', {})

    if stored_method.get('version') != current['version']:
        return False, (
            f"Version mismatch: cached={stored_method.get('version')}, "
            f"current={current['version']}"
        )
    if stored_method.get('spatial_reducer') != current['spatial_reducer']:
        return False, (
            f"Reducer changed: cached={stored_method.get('spatial_reducer')}, "
            f"current={current['spatial_reducer']}"
        )
    return True, "Metadata matches current method"


def initialize_gee(service_account_key=None, project_id=None):
    """
    Initialize Google Earth Engine with service account credentials.

    When called with no arguments, falls back to ``config.GEE_CONFIG``
    (the standard invocation in all NB0x notebooks).

    Parameters:
    -----------
    service_account_key : str | None
        Path to the service account JSON file.
        Defaults to ``config.GEE_CONFIG['service_json']``.
    project_id : str | None
        Google Cloud Project ID.
        Defaults to ``config.GEE_CONFIG['project_id']``.

    Returns:
    --------
    bool
        True if initialization successful, False otherwise
    """
    try:
        import config as _cfg
        if service_account_key is None:
            service_account_key = _cfg.GEE_CONFIG.get('service_json', '')
        if project_id is None:
            project_id = _cfg.GEE_CONFIG.get('project_id', '')

        # Earth Engine's start-up requests carry no timeout of their own; without a default, a lost
        # answer would hang here. Connections that set their own timeout keep it.
        import socket
        if socket.getdefaulttimeout() is None:
            socket.setdefaulttimeout(REQUEST_DEADLINE_MS / 1000)

        if service_account_key and os.path.exists(service_account_key):
            print(f"🔑 Found service account key: {Path(service_account_key).name}")
            credentials = service_account.Credentials.from_service_account_file(
                service_account_key,
                scopes=['https://www.googleapis.com/auth/earthengine']
            )
            ee.Initialize(credentials=credentials, project=project_id)
        else:
            # Fall back to application-default credentials (gcloud auth login)
            ee.Initialize(project=project_id)

        # Test the connection
        ee.Number(1).getInfo()
        ee.data.setDeadline(REQUEST_DEADLINE_MS)

        print("✅ Google Earth Engine initialized successfully")
        return True

    except Exception as e:
        print(f"❌ GEE Initialization error: {e}")
        return False


# =============================================================================
# AOI BOUNDARY LOADING
# =============================================================================

def load_aoi_boundaries(aoi_results_dir: str) -> dict:
    """
    Load AOI boundaries from Notebook 01 outputs.
    
    Scans ``aoi_results_dir`` for ``City_*/Features/*_AOI_Boundary.geojson``
    files, reads each one and extracts the bounding box.
    
    Only cities listed in ``config.get_cities_to_process()`` are loaded.
    
    Parameters
    ----------
    aoi_results_dir : str
        Path to the Notebook 01 output directory
        (e.g. ``data/outputs/01_aoi_delineation``).
    
    Returns
    -------
    dict
        ``{city_name: {'bounds': [west, south, east, north], 'city_dir': Path}}``
    
    Raises
    ------
    FileNotFoundError
        If no city directories or AOI boundary files are found.
    """
    import geopandas as gpd
    import sys
    
    aoi_dir = Path(aoi_results_dir)
    if not aoi_dir.exists():
        raise FileNotFoundError(f"AOI results directory not found: {aoi_dir}")
    
    # Get the cities we should process from config
    # Import config at function level to avoid circular imports
    project_root = Path(__file__).parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    import config
    cities_to_process = config.get_cities_to_process()
    
    aoi_data = {}
    
    # Scan for City_* directories
    city_dirs = sorted([d for d in aoi_dir.iterdir() if d.is_dir() and d.name.startswith("City_")])
    
    if not city_dirs:
        raise FileNotFoundError(f"No City_* directories found in {aoi_dir}")
    
    for city_dir in city_dirs:
        city_name = city_dir.name.replace("City_", "")
        
        # Only load cities that are in the current selection
        if city_name not in cities_to_process:
            continue
        
        # Look for AOI boundary GeoJSON
        features_dir = city_dir / "Features"
        boundary_file = features_dir / f"{city_name}_AOI_Boundary.geojson"
        
        if not boundary_file.exists():
            print(f"  ⚠️  No AOI boundary file for {city_name}, skipping")
            continue
        
        try:
            gdf = gpd.read_file(boundary_file)
            bounds = gdf.total_bounds.tolist()  # [minx, miny, maxx, maxy] = [west, south, east, north]
            
            aoi_data[city_name] = {
                'bounds': bounds,
                'city_dir': str(city_dir),
            }
        except Exception as e:
            print(f"  ⚠️  Error reading AOI for {city_name}: {e}")
            continue
    
    if not aoi_data:
        raise FileNotFoundError(
            f"No valid AOI boundaries found in {aoi_dir} for cities: {cities_to_process}"
        )
    
    return aoi_data


# =============================================================================
# MODIS LST EXTRACTION (ORIGINAL NOTEBOOK 04 PROTOCOL)
# =============================================================================

def extract_modis_daily_lst(geometry, city_name, year, output_path):
    """
    Extract comprehensive daily MODIS LST data matching ORIGINAL notebook protocol.
    
    Uses quarterly batch processing with hierarchical QA filtering (strict + moderate blend).
    Extracts BOTH day and night LST in a single combined CSV file.
    
    Server-side batch extraction: maps ``reduceRegion`` over all images on the
    GEE server and retrieves results in a single ``getInfo()`` call per quarter,
    reducing API round-trips by ~180× compared to per-image iteration.
    
    Parameters
    ----------
    geometry : ee.Geometry
        Area of interest
    city_name : str
        City name for display
    year : int
        Year to extract
    output_path : str or Path
        Full path to output CSV file
        
    Returns
    -------
    bool
        True if successful, False otherwise
    """
    
    print(f"    📡 Extracting MODIS LST data for {city_name}...")
    
    # Define quarterly date ranges for batch processing (ORIGINAL PROTOCOL)
    quarters = [
        (f'{year}-01-01', f'{year}-04-01'),
        (f'{year}-04-01', f'{year}-07-01'),
        (f'{year}-07-01', f'{year}-10-01'),
        (f'{year}-10-01', f'{year+1}-01-01')
    ]
    
    all_results = []
    
    for q_idx, (start, end) in enumerate(quarters):
        try:
            print(f"        Processing quarter {q_idx + 1}/4: {start} to {end}")
            
            # Load quarterly collection
            collection = ee.ImageCollection('MODIS/061/MYD11A1') \
                          .filterDate(start, end) \
                          .filterBounds(geometry)
            
            def process_image(image):
                """Process individual MODIS image with hierarchical QA filtering (ORIGINAL PROTOCOL)"""
                # Extract LST and QA bands
                day_lst = image.select('LST_Day_1km')
                night_lst = image.select('LST_Night_1km')
                day_qa = image.select('QC_Day')
                night_qa = image.select('QC_Night')
                
                # Convert to Celsius using MODIS scaling factors
                day_celsius = day_lst.multiply(0.02).subtract(273.15)
                night_celsius = night_lst.multiply(0.02).subtract(273.15)
                
                # Create QA masks using bit operations
                # Strict quality: QC bits 0-1 = 00 (good quality)
                strict_day_mask = day_qa.bitwiseAnd(3).eq(0)
                moderate_day_mask = day_qa.bitwiseAnd(3).eq(1)
                strict_night_mask = night_qa.bitwiseAnd(3).eq(0)
                moderate_night_mask = night_qa.bitwiseAnd(3).eq(1)
                
                # Apply reasonable temperature bounds for LST
                temp_bounds_day = day_celsius.gt(5).And(day_celsius.lt(70))
                temp_bounds_night = night_celsius.gt(5).And(night_celsius.lt(70))
                
                # Combine QA and temperature filters
                strict_day_final = strict_day_mask.And(temp_bounds_day)
                moderate_day_final = moderate_day_mask.And(temp_bounds_day)
                strict_night_final = strict_night_mask.And(temp_bounds_night)
                moderate_night_final = moderate_night_mask.And(temp_bounds_night)
                
                # Apply hierarchical masking: strict quality first, then moderate to fill gaps (BLEND!)
                day_hierarchical = day_celsius.updateMask(strict_day_final).blend(
                    day_celsius.updateMask(moderate_day_final)
                )
                night_hierarchical = night_celsius.updateMask(strict_night_final).blend(
                    night_celsius.updateMask(moderate_night_final)
                )
                
                # QA source tracking (1=strict, 2=moderate, 0=no_data)
                day_qa_source = ee.Image(0).where(strict_day_final, 1).where(moderate_day_final, 2)
                night_qa_source = ee.Image(0).where(strict_night_final, 1).where(moderate_night_final, 2)
                
                # Add date information for tracking
                date_band = image.date().format('YYYY-MM-dd')
                
                return image.select([]).addBands([
                    day_hierarchical.rename('LST_Day'),
                    night_hierarchical.rename('LST_Night'),
                    day_qa_source.rename('QA_Day_Source'),
                    night_qa_source.rename('QA_Night_Source')
                ]).set('date', date_band)
            
            # Process collection with hierarchical QA filtering
            processed = collection.map(process_image)
            collection_size = processed.size().getInfo()
            
            if collection_size == 0:
                print(f"        ⚠️ No images in quarter {q_idx + 1}")
                continue
            
            print(f"        📊 Extracting {collection_size} images (server-side batch)...")
            
            # Comprehensive statistics reducer: min, median, mean, max (ORIGINAL PROTOCOL)
            stats_reducer = ee.Reducer.min().combine(
                reducer2=ee.Reducer.median(), sharedInputs=True
            ).combine(
                reducer2=ee.Reducer.mean(), sharedInputs=True
            ).combine(
                reducer2=ee.Reducer.max(), sharedInputs=True
            )
            
            # --- SERVER-SIDE BATCH EXTRACTION ---
            # Maps reduceRegion over all images on the GEE server so only ONE
            # getInfo() call is needed per quarter (instead of ~90 per-image
            # round-trips). Reduces GEE API calls by ~180× per city.
            def _extract_daily_feature(image):
                """Server-side: extract spatial statistics as an ee.Feature."""
                date_val = image.get('date')
                
                # LST spatial statistics (min, median, mean, max)
                lst_stats = image.select(['LST_Day', 'LST_Night']).reduceRegion(
                    reducer=stats_reducer,
                    geometry=geometry,
                    scale=1000,
                    maxPixels=1e9,
                    bestEffort=True
                )
                
                # QA frequency histograms
                qa_day_hist = image.select('QA_Day_Source').reduceRegion(
                    reducer=ee.Reducer.frequencyHistogram(),
                    geometry=geometry,
                    scale=1000,
                    maxPixels=1e9,
                    bestEffort=True
                ).get('QA_Day_Source')
                
                qa_night_hist = image.select('QA_Night_Source').reduceRegion(
                    reducer=ee.Reducer.frequencyHistogram(),
                    geometry=geometry,
                    scale=1000,
                    maxPixels=1e9,
                    bestEffort=True
                ).get('QA_Night_Source')
                
                return ee.Feature(None, lst_stats.combine(ee.Dictionary({
                    'date': date_val,
                    'qa_day_hist': qa_day_hist,
                    'qa_night_hist': qa_night_hist
                })))
            
            features_fc = processed.map(_extract_daily_feature)
            
            # Single getInfo() retrieves all results for the quarter
            result_fc = features_fc.getInfo()
            
            def _qa_percentages(qa_hist):
                """Parse QA frequency histogram into percentages."""
                if not qa_hist:
                    return 0, 0, 'none'
                total = sum(float(v) for v in qa_hist.values())
                if total == 0:
                    return 0, 0, 'none'
                strict_count = float(qa_hist.get('1', 0))
                moderate_count = float(qa_hist.get('2', 0))
                strict_pct = (strict_count / total) * 100
                moderate_pct = (moderate_count / total) * 100
                dominant = 'strict' if strict_pct >= moderate_pct else 'moderate' if moderate_pct > 0 else 'none'
                return strict_pct, moderate_pct, dominant
            
            q_count = 0
            for feature in result_fc['features']:
                props = feature['properties']
                date_str = props.get('date')
                if not date_str:
                    continue
                
                day_s, day_m, day_l = _qa_percentages(props.get('qa_day_hist'))
                night_s, night_m, night_l = _qa_percentages(props.get('qa_night_hist'))
                
                # Compile comprehensive results (identical output format)
                all_results.append({
                    'date': date_str,
                    # Day LST - All Statistics (min, median, mean, max)
                    'day_lst_min': props.get('LST_Day_min'),
                    'day_lst_median': props.get('LST_Day_median'),
                    'day_lst_mean': props.get('LST_Day_mean'),
                    'day_lst_max': props.get('LST_Day_max'),
                    # Night LST - All Statistics (min, median, mean, max)
                    'night_lst_min': props.get('LST_Night_min'),
                    'night_lst_median': props.get('LST_Night_median'),
                    'night_lst_mean': props.get('LST_Night_mean'),
                    'night_lst_max': props.get('LST_Night_max'),
                    # QA Information for data quality tracking
                    'day_qa_strict_pct': round(day_s, 1),
                    'day_qa_moderate_pct': round(day_m, 1),
                    'night_qa_strict_pct': round(night_s, 1),
                    'night_qa_moderate_pct': round(night_m, 1),
                    'day_qa_level': day_l,
                    'night_qa_level': night_l
                })
                q_count += 1
            
            print(f"        ✅ Quarter {q_idx + 1}: {q_count} daily records extracted")
        
        except Exception as e:
            print(f"        ❌ Error processing quarter {q_idx + 1}: {e}")
    
    if not all_results:
        print(f"        ❌ No results for {city_name}")
        return False
    
    # Convert to DataFrame and save
    df = pd.DataFrame(all_results)
    df = df[df['date'].notna()].copy()
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    df = df.drop_duplicates(subset=['date']).reset_index(drop=True)
    
    # Validate data quality - check that at least some values are non-NaN
    lst_cols = [c for c in df.columns if 'lst_' in c]
    valid_count = df[lst_cols].notna().any(axis=1).sum()
    if valid_count == 0:
        print(f"        ❌ All LST values are NaN for {city_name} - extraction failed silently")
        print(f"        ⚠️  File NOT saved. Will retry on next run.")
        return False
    
    valid_pct = valid_count / len(df) * 100
    print(f"        📊 Data quality: {valid_count}/{len(df)} days with valid data ({valid_pct:.1f}%)")
    
    # Save raw data
    df.to_csv(output_path, index=False)
    _save_extraction_metadata(output_path, 'modis')
    
    print(f"        ✅ Saved {len(df)} records to {output_path}")
    return True


# =============================================================================
# ERA5-LAND LST EXTRACTION (ORIGINAL NOTEBOOK 04 PROTOCOL)
# =============================================================================

def extract_era5_daily_lst(geometry, city_name, year, output_path):
    """
    Extract comprehensive ERA5-Land LST data matching ORIGINAL notebook protocol.
    Extracts BOTH day and night LST in a single combined CSV file.
    
    Parameters
    ----------
    geometry : ee.Geometry
        Area of interest
    city_name : str
        City name for display
    year : int
        Year to extract
    output_path : str or Path
        Full path to output CSV file
        
    Returns
    -------
    bool
        True if successful, False otherwise
    """
    print(f"    🌍 Extracting ERA5-Land LST data for {city_name}...")
    
    # Time windows matching original protocol
    day_hours = [13, 14, 15]    # Afternoon hours (UTC)
    night_hours = [1, 2, 3]     # Early morning hours (UTC)
    
    try:
        # Load ERA5-Land collection
        era5_collection = ee.ImageCollection('ECMWF/ERA5_LAND/HOURLY') \
                            .filterDate(f'{year}-01-01', f'{year+1}-01-01') \
                            .filterBounds(geometry) \
                            .select('skin_temperature')
        
        collection_size = era5_collection.size().getInfo()
        print(f"        📊 Found {collection_size} hourly ERA5-Land images")
        
        if collection_size == 0:
            print(f"        ❌ No ERA5-Land data found")
            return False
        
        # Function to process daily ERA5-Land data (ORIGINAL PROTOCOL)
        def process_era5_daily(date):
            """Process ERA5-Land data for a specific date"""
            date_str = ee.Date(date).format('YYYY-MM-dd')
            
            # Filter images for this date
            day_images = era5_collection.filterDate(date, ee.Date(date).advance(1, 'day'))
            
            # Day statistics (afternoon hours)
            day_filtered = day_images.filter(ee.Filter.inList('hour', day_hours))
            day_stats = day_filtered.select('skin_temperature').reduce(
                ee.Reducer.min().combine(
                    reducer2=ee.Reducer.median(), sharedInputs=True
                ).combine(
                    reducer2=ee.Reducer.mean(), sharedInputs=True
                ).combine(
                    reducer2=ee.Reducer.max(), sharedInputs=True
                )
            ).subtract(273.15)  # Convert Kelvin to Celsius
            
            # Night statistics (early morning hours)
            night_filtered = day_images.filter(ee.Filter.inList('hour', night_hours))
            night_stats = night_filtered.select('skin_temperature').reduce(
                ee.Reducer.min().combine(
                    reducer2=ee.Reducer.median(), sharedInputs=True
                ).combine(
                    reducer2=ee.Reducer.mean(), sharedInputs=True
                ).combine(
                    reducer2=ee.Reducer.max(), sharedInputs=True
                )
            ).subtract(273.15)  # Convert Kelvin to Celsius
            
            # Rename bands to match format
            combined = day_stats.select(
                ['skin_temperature_min', 'skin_temperature_median', 'skin_temperature_mean', 'skin_temperature_max'],
                ['day_lst_min', 'day_lst_median', 'day_lst_mean', 'day_lst_max']
            ).addBands(
                night_stats.select(
                    ['skin_temperature_min', 'skin_temperature_median', 'skin_temperature_mean', 'skin_temperature_max'],
                    ['night_lst_min', 'night_lst_median', 'night_lst_mean', 'night_lst_max']
                )
            )
            
            return combined.set('date', date_str).set('system:time_start', ee.Date(date).millis())
        
        # Generate date list for the year
        start_date = ee.Date(f'{year}-01-01')
        end_date = ee.Date(f'{year+1}-01-01')
        
        # Create daily composites
        date_list = ee.List.sequence(0, end_date.difference(start_date, 'day').subtract(1), 1)
        daily_images = date_list.map(lambda day_offset: 
            process_era5_daily(start_date.advance(ee.Number(day_offset), 'day'))
        )
        
        # Convert to ImageCollection
        era5_daily_collection = ee.ImageCollection.fromImages(daily_images)
        
        print(f"        📅 Created {era5_daily_collection.size().getInfo()} daily composites")
        
        # Extract statistics for each day
        def extract_daily_stats(image):
            """Extract comprehensive statistics for each daily composite"""
            date = image.get('date')
            
            # Spatially aggregate all valid (land) pixels in the AOI.
            # Using median() for robustness: at ERA5-Land's ~9 km resolution,
            # only ~4-9 pixels fall within the AOI, so a single outlier/edge
            # pixel can skew the mean. Median is more representative of
            # typical conditions across the AOI.
            stats = image.reduceRegion(
                reducer=ee.Reducer.median(),
                geometry=geometry,
                scale=11132,  # ERA5-Land native resolution (~0.1 degree)
                maxPixels=1e9,
                bestEffort=True
            )
            
            # Return feature with date and statistics
            return ee.Feature(None, {
                'date': date,
                'day_lst_min': stats.get('day_lst_min'),
                'day_lst_median': stats.get('day_lst_median'),
                'day_lst_mean': stats.get('day_lst_mean'),
                'day_lst_max': stats.get('day_lst_max'),
                'night_lst_min': stats.get('night_lst_min'),
                'night_lst_median': stats.get('night_lst_median'),
                'night_lst_mean': stats.get('night_lst_mean'),
                'night_lst_max': stats.get('night_lst_max')
            })
        
        # Process all daily images
        era5_features = era5_daily_collection.map(extract_daily_stats)
        
        # Convert to list and get info
        era5_data = era5_features.getInfo()
        
        # Process results into DataFrame
        results = []
        for feature in era5_data['features']:
            props = feature['properties']
            if props['date']:  # Only include valid dates
                results.append({
                    'date': props['date'],
                    'day_lst_min': props.get('day_lst_min'),
                    'day_lst_median': props.get('day_lst_median'),
                    'day_lst_mean': props.get('day_lst_mean'),
                    'day_lst_max': props.get('day_lst_max'),
                    'night_lst_min': props.get('night_lst_min'),
                    'night_lst_median': props.get('night_lst_median'),
                    'night_lst_mean': props.get('night_lst_mean'),
                    'night_lst_max': props.get('night_lst_max')
                })
        
        if not results:
            print(f"        ❌ No results for {city_name}")
            return False
        
        # Convert to DataFrame
        df = pd.DataFrame(results)
        df = df[df['date'].notna()].copy()
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)
        df = df.drop_duplicates(subset=['date']).reset_index(drop=True)
        
        # Validate data quality - check that at least some values are non-NaN
        lst_cols = [c for c in df.columns if 'lst_' in c]
        valid_count = df[lst_cols].notna().any(axis=1).sum()
        if valid_count == 0:
            print(f"        ❌ All LST values are NaN for {city_name} - extraction failed silently")
            print(f"        ⚠️  File NOT saved. Will retry on next run.")
            return False
        
        valid_pct = valid_count / len(df) * 100
        print(f"        📊 Data quality: {valid_count}/{len(df)} days with valid data ({valid_pct:.1f}%)")
        
        # Save to CSV
        df.to_csv(output_path, index=False)
        _save_extraction_metadata(output_path, 'era5')
        
        print(f"        ✅ Saved {len(df)} records to {output_path}")
        return True
        
    except Exception as e:
        print(f"        ❌ ERA5-Land extraction error: {e}")
        return False


# =============================================================================
# NOTEBOOK 03 — MODIS MONTHLY/ANNUAL LST WITH HIERARCHICAL QA
# =============================================================================

def load_modis_collection_with_hierarchical_qa(city_name, geometry, lst_time,
                                               lst_config, temporal_config,
                                               project_config):
    """
    Load and prepare a MODIS LST ImageCollection with hierarchical QA filtering.

    Implements the strict → moderate fallback strategy:
      1. Strict QA (error ≤ 1 K) applied first.
      2. Where strict pixels are absent, moderate QA (error ≤ 2 K) fills gaps.
      3. A 'QA_Source' band records which tier was used (1 = strict, 2 = moderate).

    Parameters
    ----------
    city_name : str
    geometry : ee.Geometry
    lst_time : str
        'day' or 'night'
    lst_config : dict
        config.LST_CONFIG
    temporal_config : dict
        config.TEMPORAL_CONFIG
    project_config : dict
        Local PROJECT_CONFIG dict from the notebook (needs 'start_date', 'end_date').

    Returns
    -------
    tuple
        (processed_collection, image_count, monthly_counts, yearly_counts,
         monthly_yearly_counts)
        Any element can be None on failure.
    """
    import time as _time
    import traceback as _tb
    import datetime as _dt

    start_time = _time.time()
    try:
        collection_config = lst_config['collections'][lst_config['primary_collection']]
        selected_band    = collection_config[lst_time + '_band']
        selected_qa_band = collection_config[lst_time + '_qa_band']
        qa_levels_to_use = lst_config['qa_levels_to_use']

        print(f"  🛰️  Loading {collection_config['description']} {lst_time.title()}-time for {city_name}")

        collection = (ee.ImageCollection(collection_config['id'])
                      .filterDate(project_config['start_date'], project_config['end_date'])
                      .filterBounds(geometry))

        total_images = collection.size().getInfo()
        print(f"    📊 Total images in collection: {total_images}")

        def apply_hierarchical_qa(image):
            lst   = image.select(selected_band)
            qa    = image.select(selected_qa_band)
            lst_c = lst.multiply(collection_config['scale_factor']).add(collection_config['offset'])
            qa_hierarchy = lst_config['quality_hierarchy']

            quality_masks = {}
            quality_lst   = {}
            for tier in qa_hierarchy:
                if tier in qa_levels_to_use:
                    quality_masks[tier] = qa.bitwiseAnd(3).eq(qa_hierarchy[tier]['qa_bits'])
                    quality_lst[tier]   = lst_c.updateMask(quality_masks[tier])

            qa_source    = ee.Image(0).rename('QA_Source')
            sorted_tiers = sorted([t for t in qa_levels_to_use],
                                  key=lambda t: qa_hierarchy[t]['priority'])
            for tier in sorted_tiers:
                qa_source = qa_source.where(quality_masks[tier],
                                            qa_hierarchy[tier]['priority'])

            lst_hierarchical = None
            for i, tier in enumerate(sorted_tiers):
                if i == 0:
                    lst_hierarchical = quality_lst[tier]
                else:
                    lst_hierarchical = lst_hierarchical.blend(quality_lst[tier])

            if lst_hierarchical is None:
                return ee.Image([]).copyProperties(image, ['system:time_start'])

            lst_hierarchical = lst_hierarchical.rename('LST')
            valid_temp       = lst_hierarchical.gt(5).And(lst_hierarchical.lt(70))
            lst_hierarchical = lst_hierarchical.updateMask(valid_temp)
            qa_source        = qa_source.updateMask(valid_temp)

            return (ee.Image([lst_hierarchical, qa_source])
                    .copyProperties(image, ['system:time_start']))

        processed_collection = collection.map(apply_hierarchical_qa)
        image_count          = processed_collection.size().getInfo()
        print(f"    📊 Processed images after filtering: {image_count}")

        try:
            dates_millis = processed_collection.aggregate_array('system:time_start').getInfo()
            dates        = [_dt.datetime.fromtimestamp(d / 1000) for d in dates_millis]

            monthly_counts = {m: sum(1 for d in dates if d.month == m) for m in range(1, 13)}
            yearly_counts  = {y: sum(1 for d in dates if d.year  == y)
                              for y in temporal_config['years']}
            monthly_yearly_counts = {}
            for y in temporal_config['years']:
                monthly_yearly_counts[y] = {
                    m: sum(1 for d in dates if d.year == y and d.month == m)
                    for m in range(1, 13)}

            duration = _time.time() - start_time
            print(f"    ⏱️ Collection loaded in {duration:.2f}s")
            return processed_collection, image_count, monthly_counts, \
                   yearly_counts, monthly_yearly_counts

        except Exception as e:
            print(f"    ⚠️ Could not compute image frequency statistics: {e}")
            return processed_collection, image_count, None, None, None

    except Exception as e:
        print(f"    ❌ Error loading collection for {city_name}: {e}")
        print(f"    📋 {_tb.format_exc()}")
        return None, 0, None, None, None


def compute_and_export_lst_geotiff_with_qa(collection, geometry, city_name,
                                           city_dir, period_type, period_value,
                                           lst_time, lst_config, project_config):
    """
    Compute a median LST composite and export both the LST and QA GeoTIFFs.

    Parameters
    ----------
    collection : ee.ImageCollection
        QA-filtered collection returned by load_modis_collection_with_hierarchical_qa.
    geometry : ee.Geometry
    city_name, city_dir : str
    period_type : str
        'yearly' or 'monthly_climatology'
    period_value : int
        Year (e.g. 2020) or month number (1-12).
    lst_time : str
        'day' or 'night'
    lst_config : dict   (config.LST_CONFIG)
    project_config : dict
        Needs 'lst_output_dir'.

    Returns
    -------
    dict or None
        Keys: 'file_name', 'period', 'image_count', 'status', optionally
        'lst_path', 'qa_path', 'processing_time'.
    """
    import time as _time
    import traceback as _tb
    import requests as _req

    start = _time.time()
    try:
        if period_type == 'yearly':
            start_date  = f"{period_value}-01-01"
            end_date    = f"{period_value}-12-31"
            period_name = str(period_value)
            file_name   = f"{city_name}_LST_{lst_time.title()}_Yearly_{period_value}"
            qa_name     = f"{city_name}_QA_Source_{lst_time.title()}_Yearly_{period_value}"
            period_coll = collection.filterDate(start_date, end_date)

        elif period_type == 'monthly_climatology':
            month          = period_value
            month_filter   = ee.Filter.calendarRange(month, month, 'month')
            period_name    = f"Month_{month:02d}_AllYears"
            file_name      = f"{city_name}_LST_{lst_time.title()}_MonthlyClimatology_{month:02d}"
            qa_name        = f"{city_name}_QA_Source_{lst_time.title()}_MonthlyClimatology_{month:02d}"
            period_coll    = collection.filter(month_filter)
        else:
            return None

        period_count = period_coll.size().getInfo()
        if period_count == 0:
            return None

        lst_composite = period_coll.select('LST').median().rename('LST')
        qa_composite  = period_coll.select('QA_Source').mode().rename('QA_Source')

        # Check valid pixels
        valid_pixels = (ee.Number(lst_composite.reduceRegion(
            reducer=ee.Reducer.count(), geometry=geometry,
            scale=lst_config['scale'], maxPixels=1e9).get('LST'))
            .getInfo())
        if valid_pixels == 0:
            return {'file_name': file_name, 'period': period_name,
                    'image_count': period_count, 'status': 'no_valid_pixels'}

        # Build output paths
        lst_subfolder  = 'Day' if lst_time == 'day' else 'Night'
        geotiff_dir    = os.path.join(project_config['lst_output_dir'], f"City_{city_name}",
                                      'LST_Temporal_Analysis', lst_subfolder, 'geotiff')
        os.makedirs(geotiff_dir, exist_ok=True)
        dl_path        = os.path.join(geotiff_dir, f"{file_name}.tif")
        qa_path        = os.path.join(geotiff_dir, f"{qa_name}.tif")

        def _download(image, bands, path, label):
            params = {'scale': lst_config['scale'], 'crs': 'EPSG:4326',
                      'region': geometry, 'format': 'GEO_TIFF',
                      'bands': bands}
            url  = image.getDownloadURL(params)
            for attempt in range(3):
                try:
                    r = _req.get(url, stream=True, timeout=60)
                    if r.status_code == 200:
                        with open(path, 'wb') as f:
                            for chunk in r.iter_content(8192):
                                if chunk:
                                    f.write(chunk)
                        return True
                    print(f"      ⚠️ HTTP {r.status_code} on attempt {attempt+1} for {label}")
                except Exception as e:
                    print(f"      ⚠️ Download error on attempt {attempt+1}: {e}")
                _time.sleep(2)
            return False

        lst_ok = _download(lst_composite, ['LST'],       dl_path, 'LST')
        qa_ok  = _download(qa_composite,  ['QA_Source'], qa_path, 'QA')

        duration = _time.time() - start
        status   = 'downloaded' if (lst_ok and qa_ok) else ('partial' if lst_ok else 'failed')
        result   = {'file_name': file_name, 'period': period_name,
                    'image_count': period_count, 'status': status,
                    'processing_time': duration}
        if lst_ok:
            result['lst_path'] = dl_path
        if qa_ok:
            result['qa_path']  = qa_path
        return result

    except Exception as e:
        print(f"      ❌ Error: {e}")
        print(f"      📋 {_tb.format_exc()}")
        return None


# ---------------------------------------------------------------------------
# Dask worker helpers for parallel GEE processing  (Notebook 03, Cell 13)
# ---------------------------------------------------------------------------

def init_ee_in_worker():
    """Initialize Earth Engine inside a Dask worker process.

    Safe to call repeatedly — skips if EE is already initialised.
    """
    import sys
    import os as _os
    from pathlib import Path
    import ee as _ee

    try:
        _ee.Number(1).getInfo()          # already initialised
    except Exception:
        project_root = (Path(_os.getcwd()).parent
                        if Path(_os.getcwd()).name.lower() in ('notebooks', 'notebook')
                        else Path(_os.getcwd()))
        sys.path.insert(0, str(project_root))
        import config as _cfg
        from google.oauth2 import service_account as _sa

        credentials = _sa.Credentials.from_service_account_file(
            _cfg.GEE_CONFIG['service_json'],
            scopes=['https://www.googleapis.com/auth/earthengine'],
        )
        _ee.Initialize(credentials=credentials,
                       project=_cfg.GEE_CONFIG['project_id'])


def process_city_period(city_name, bounds_list, city_dir, period_type,
                        period_value, lst_time, lst_config, temporal_config,
                        project_config):
    """Process and download a single LST period for one city.

    All arguments are plain Python objects (no EE objects) so that the
    function can be serialised by Dask.

    Returns
    -------
    dict   with keys *city*, *period_type*, *period_value*, *lst_time*,
           *status* ('downloaded' | 'skipped' | 'no_data' | 'error'),
           and optional *file_path*, *qa_file_path*, *duration*,
           *image_count*, *message*, *traceback*.
    """
    import os as _os
    import time as _time
    import traceback as _tb
    import ee as _ee
    import requests as _requests

    try:
        init_ee_in_worker()
        start = _time.time()

        city_geometry = _ee.Geometry.Rectangle(bounds_list)

        result = {
            'city': city_name,
            'period_type': period_type,
            'period_value': period_value,
            'lst_time': lst_time,
            'status': 'pending',
        }

        # File names
        if period_type == 'yearly':
            file_name = f"{city_name}_LST_{lst_time.title()}_Yearly_{period_value}"
            qa_file_name = f"{city_name}_QA_Source_{lst_time.title()}_Yearly_{period_value}"
        else:
            file_name = f"{city_name}_LST_{lst_time.title()}_MonthlyClimatology_{period_value:02d}"
            qa_file_name = f"{city_name}_QA_Source_{lst_time.title()}_MonthlyClimatology_{period_value:02d}"

        # Directories
        city_lst_dir = _os.path.join(project_config['lst_output_dir'],
                                     f"City_{city_name}",
                                     'LST_Temporal_Analysis')
        lst_subfolder = 'Day' if lst_time == 'day' else 'Night'
        city_geotiff_dir = _os.path.join(city_lst_dir, lst_subfolder, 'geotiff')
        _os.makedirs(city_geotiff_dir, exist_ok=True)

        file_path    = _os.path.join(city_geotiff_dir, f"{file_name}.tif")
        qa_file_path = _os.path.join(city_geotiff_dir, f"{qa_file_name}.tif")

        if _os.path.exists(file_path):
            result['status'] = 'skipped'
            result['message'] = f"File already exists: {file_path}"
            return result

        # Collection setup
        collection_config = lst_config['collections'][lst_config['primary_collection']]
        selected_band    = collection_config[lst_time + '_band']
        selected_qa_band = collection_config[lst_time + '_qa_band']

        collection = (_ee.ImageCollection(collection_config['id'])
                      .filterDate(project_config['start_date'],
                                  project_config['end_date'])
                      .filterBounds(city_geometry))

        # Hierarchical QA filtering
        def _apply_hierarchical_qa(image):
            lst = image.select(selected_band)
            qa  = image.select(selected_qa_band)
            lst_celsius = lst.multiply(collection_config['scale_factor']).add(collection_config['offset'])

            qa_levels     = lst_config['qa_levels_to_use']
            qa_hierarchy  = lst_config['quality_hierarchy']
            quality_masks = {}
            quality_lst   = {}
            for tier in qa_levels:
                quality_masks[tier] = qa.bitwiseAnd(3).eq(qa_hierarchy[tier]['qa_bits'])
                quality_lst[tier]   = lst_celsius.updateMask(quality_masks[tier])

            qa_source = _ee.Image(0).rename('QA_Source')
            sorted_qa = sorted(qa_levels, key=lambda t: qa_hierarchy[t]['priority'])
            for tier in sorted_qa:
                qa_source = qa_source.where(quality_masks[tier],
                                            qa_hierarchy[tier]['priority'])

            lst_hier = None
            for i, tier in enumerate(sorted_qa):
                lst_hier = quality_lst[tier] if i == 0 else lst_hier.blend(quality_lst[tier])
            if lst_hier is None:
                return _ee.Image([]).copyProperties(image, ['system:time_start'])

            lst_hier = lst_hier.rename('LST')
            valid = lst_hier.gt(5).And(lst_hier.lt(70))
            lst_hier  = lst_hier.updateMask(valid)
            qa_source = qa_source.updateMask(valid)
            return _ee.Image([lst_hier, qa_source]).copyProperties(image, ['system:time_start'])

        processed = collection.map(_apply_hierarchical_qa)

        if period_type == 'yearly':
            filtered = processed.filterDate(f"{period_value}-01-01",
                                            f"{period_value}-12-31")
        else:
            filtered = processed.filter(
                _ee.Filter.calendarRange(period_value, period_value, 'month'))

        count = filtered.size().getInfo()
        if count == 0:
            result['status']  = 'no_data'
            result['message'] = (f"No images for {city_name} – "
                                 f"{period_type}={period_value} ({lst_time})")
            return result

        lst_composite = filtered.select('LST').median()
        qa_composite  = filtered.select('QA_Source').mode()

        dl_params = {'scale': lst_config['scale'], 'crs': 'EPSG:4326',
                     'region': city_geometry, 'format': 'GEO_TIFF'}

        lst_url = lst_composite.getDownloadURL(dl_params)
        qa_url  = qa_composite.getDownloadURL(dl_params)

        def _download(url, dest, max_retries=3):
            for attempt in range(max_retries):
                try:
                    resp = _requests.get(url, timeout=60)
                    if resp.status_code == 200:
                        with open(dest, 'wb') as f:
                            f.write(resp.content)
                        return True
                except Exception:
                    if attempt == max_retries - 1:
                        raise
                    _time.sleep(2)
            return False

        _download(lst_url, file_path)
        _download(qa_url, qa_file_path)

        duration = _time.time() - start
        result.update({
            'status': 'downloaded',
            'file_path': file_path,
            'qa_file_path': qa_file_path,
            'duration': duration,
            'image_count': count,
        })
        return result

    except Exception as e:
        return {
            'city': city_name,
            'period_type': period_type,
            'period_value': period_value,
            'lst_time': lst_time,
            'status': 'error',
            'message': str(e),
            'traceback': _tb.format_exc(),
        }


def extract_three_zone_lst(city_name, zones, years, output_dir,
                            source_version='NB01_v5_SMOD',
                            col_id=None):
    """
    Extract monthly MODIS MYD11A1 LST composites for UC, BRA, and City-Region.

    Strategy
    --------
    For each year, 12 month-composite features are built server-side in a
    single ee.FeatureCollection and retrieved with one getInfo() call per year
    (19 round-trips per city instead of 76 quarterly calls with per-image
    mapping).

    QA filtering
    -----------
    Combined mask: QC bits 0-1 in {00, 01} — strict and moderate accepted in
    one pass, no server-side branching.  Temperature bounds 5–70 °C applied
    before compositing.

    Output schema
    -------------
    year, month,
    uc_day_median,  uc_day_n,  uc_night_median,  uc_night_n,
    bra_day_median, bra_day_n, bra_night_median, bra_night_n,
    cr_day_p05, cr_day_median, cr_day_p95, cr_day_n,
    cr_night_p05, cr_night_median, cr_night_p95, cr_night_n,
    n_images

    Parameters
    ----------
    city_name : str
    zones : dict
        {'uc_ee': ee.Geometry, 'bra_ee': ee.Geometry, 'cr_ee': ee.Geometry,
         'city_slug': str, 'cache_hash': str}
    years : list[int]
    output_dir : Path
    source_version : str
    col_id : str | None
        MODIS collection ID; defaults to config.LST_CONFIG primary collection.

    Returns
    -------
    pd.DataFrame | None
    """
    import json as _json
    import traceback as _tb
    from pathlib import Path as _Path
    from datetime import datetime as _dt
    import numpy as _np
    import pandas as _pd

    city_slug  = zones['city_slug']
    cache_hash = zones['cache_hash']
    out_dir    = _Path(output_dir) / city_slug
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path   = out_dir / f'{city_slug}_monthly_lst_threezone.csv'
    meta_path  = csv_path.with_suffix('.meta.json')

    # Cache check
    if csv_path.exists() and meta_path.exists():
        try:
            meta = _json.loads(meta_path.read_text())
            if (meta.get('source_version') == source_version and
                    meta.get('cache_hash') == cache_hash):
                df = _pd.read_csv(csv_path)
                print(f'  [CACHE] {city_name}')
                return df
        except Exception:
            pass

    try:
        import ee as _ee
        import config as _cfg
    except ImportError:
        print(f'  [SKIP ] {city_name} - ee or config not available')
        return None

    uc_ee  = zones.get('uc_ee')
    bra_ee = zones.get('bra_ee')
    cr_ee  = zones.get('cr_ee')
    if uc_ee is None or bra_ee is None or cr_ee is None:
        print(f'  [SKIP ] {city_name} - GEE geometries not available')
        return None

    if col_id is None:
        col_id = _cfg.LST_CONFIG['collections'][
            _cfg.LST_CONFIG['primary_collection']]['id']

    def _month_feature(year, month):
        """Build one ee.Feature for a single year-month composite."""
        start = _ee.Date.fromYMD(year, month, 1)
        end   = start.advance(1, 'month')

        col = (_ee.ImageCollection(col_id)
               .filterDate(start, end)
               .filterBounds(cr_ee))

        def _mask_img(img):
            day_lst   = img.select('LST_Day_1km').multiply(0.02).subtract(273.15)
            night_lst = img.select('LST_Night_1km').multiply(0.02).subtract(273.15)
            day_qa    = img.select('QC_Day')
            night_qa  = img.select('QC_Night')
            # Combined strict+moderate mask — no server-side branching
            day_mask   = day_qa.bitwiseAnd(3).lte(1).And(day_lst.gt(5)).And(day_lst.lt(70))
            night_mask = night_qa.bitwiseAnd(3).lte(1).And(night_lst.gt(5)).And(night_lst.lt(70))
            return (day_lst.updateMask(day_mask).rename('day')
                           .addBands(night_lst.updateMask(night_mask).rename('night')))

        def _qa_count(img):
            """Tag each image with strict / moderate pixel counts inside CR.

            Uses lightweight Reducer.sum() on boolean masks — much cheaper than
            the full LST statistics reducers.  Properties set on each image:
              d_s  — strict-quality day pixels in CR   (QC bits 0-1 = 00)
              d_m  — moderate-quality day pixels in CR (QC bits 0-1 = 01)
              n_s  — strict-quality night pixels in CR
              n_m  — moderate-quality night pixels in CR
            """
            day_lst   = img.select('LST_Day_1km').multiply(0.02).subtract(273.15)
            night_lst = img.select('LST_Night_1km').multiply(0.02).subtract(273.15)
            day_qa    = img.select('QC_Day')
            night_qa  = img.select('QC_Night')
            t_day   = day_lst.gt(5).And(day_lst.lt(70))
            t_night = night_lst.gt(5).And(night_lst.lt(70))
            strict_d   = day_qa.bitwiseAnd(3).eq(0).And(t_day)
            moderate_d = day_qa.bitwiseAnd(3).eq(1).And(t_day)
            strict_n   = night_qa.bitwiseAnd(3).eq(0).And(t_night)
            moderate_n = night_qa.bitwiseAnd(3).eq(1).And(t_night)
            _r = _ee.Reducer.sum()
            _kw = dict(geometry=cr_ee, scale=1000, maxPixels=1e6, bestEffort=True)
            return img.set({
                'd_s': strict_d.rename('v').reduceRegion(_r, **_kw).get('v'),
                'd_m': moderate_d.rename('v').reduceRegion(_r, **_kw).get('v'),
                'n_s': strict_n.rename('v').reduceRegion(_r, **_kw).get('v'),
                'n_m': moderate_n.rename('v').reduceRegion(_r, **_kw).get('v'),
            })

        masked = col.map(_mask_img)
        tagged = col.map(_qa_count)   # lightweight pixel-count pass on raw collection

        # Image-level QA counts (strict = preferred, moderate = supplement)
        _gt0   = _ee.Filter.greaterThan
        _lte0  = _ee.Filter.lessThanOrEquals
        n_day_strict    = tagged.filter(_gt0('d_s', 0)).size()
        n_day_moderate  = tagged.filter(
            _ee.Filter.And(_lte0('d_s', 0), _gt0('d_m', 0))).size()
        n_night_strict  = tagged.filter(_gt0('n_s', 0)).size()
        n_night_moderate = tagged.filter(
            _ee.Filter.And(_lte0('n_s', 0), _gt0('n_m', 0))).size()

        # Monthly pixel-wise composite: median + count across valid days
        comp = masked.reduce(
            _ee.Reducer.median().combine(_ee.Reducer.count(), sharedInputs=True))
        # Band names after reduce: 'day_median', 'day_count', 'night_median', 'night_count'

        # Spatial statistics reducer: mean, median, min, max, std across zone pixels
        # Applied to the monthly median composite — each pixel value is its temporal
        # median for the month, so these are *spatial* descriptors of the zone.
        _stats_r = (
            _ee.Reducer.mean()
            .combine(_ee.Reducer.median(), sharedInputs=True)
            .combine(_ee.Reducer.min(),    sharedInputs=True)
            .combine(_ee.Reducer.max(),    sharedInputs=True)
            .combine(_ee.Reducer.stdDev(), sharedInputs=True)
        )
        # Keys produced: '{band}_mean', '{band}_median', '{band}_min',
        #                '{band}_max', '{band}_stdDev'
        # where band = 'day_median' or 'night_median'

        lst_comp = comp.select(['day_median', 'night_median'])
        cnt_comp = comp.select(['day_count',  'night_count'])

        uc_s  = lst_comp.reduceRegion(_stats_r,          uc_ee,  1000, maxPixels=1e9, bestEffort=True)
        uc_n  = cnt_comp.reduceRegion(_ee.Reducer.mean(), uc_ee,  1000, maxPixels=1e9, bestEffort=True)
        bra_s = lst_comp.reduceRegion(_stats_r,          bra_ee, 1000, maxPixels=1e9, bestEffort=True)
        bra_n = cnt_comp.reduceRegion(_ee.Reducer.mean(), bra_ee, 1000, maxPixels=1e9, bestEffort=True)

        # CR: full spatial stats + P5/P95 envelope
        _cr_r = (
            _ee.Reducer.percentile([5, 50, 95])
            .combine(_ee.Reducer.mean(),   sharedInputs=True)
            .combine(_ee.Reducer.min(),    sharedInputs=True)
            .combine(_ee.Reducer.max(),    sharedInputs=True)
            .combine(_ee.Reducer.stdDev(), sharedInputs=True)
        )
        cr_s = lst_comp.reduceRegion(_cr_r,              cr_ee, 1000, maxPixels=1e9, bestEffort=True)
        cr_n = cnt_comp.reduceRegion(_ee.Reducer.mean(),  cr_ee, 1000, maxPixels=1e9, bestEffort=True)

        return _ee.Feature(None, {
            'year'  : year,
            'month' : month,
            # UC — spatial stats over urban core pixels
            'uc_day_mean'     : uc_s.get('day_median_mean'),
            'uc_day_median'   : uc_s.get('day_median_median'),
            'uc_day_min'      : uc_s.get('day_median_min'),
            'uc_day_max'      : uc_s.get('day_median_max'),
            'uc_day_std'      : uc_s.get('day_median_stdDev'),
            'uc_day_n'        : uc_n.get('day_count'),
            'uc_night_mean'   : uc_s.get('night_median_mean'),
            'uc_night_median' : uc_s.get('night_median_median'),
            'uc_night_min'    : uc_s.get('night_median_min'),
            'uc_night_max'    : uc_s.get('night_median_max'),
            'uc_night_std'    : uc_s.get('night_median_stdDev'),
            'uc_night_n'      : uc_n.get('night_count'),
            # BRA — spatial stats over background reference area pixels
            'bra_day_mean'    : bra_s.get('day_median_mean'),
            'bra_day_median'  : bra_s.get('day_median_median'),
            'bra_day_min'     : bra_s.get('day_median_min'),
            'bra_day_max'     : bra_s.get('day_median_max'),
            'bra_day_std'     : bra_s.get('day_median_stdDev'),
            'bra_day_n'       : bra_n.get('day_count'),
            'bra_night_mean'  : bra_s.get('night_median_mean'),
            'bra_night_median': bra_s.get('night_median_median'),
            'bra_night_min'   : bra_s.get('night_median_min'),
            'bra_night_max'   : bra_s.get('night_median_max'),
            'bra_night_std'   : bra_s.get('night_median_stdDev'),
            'bra_night_n'     : bra_n.get('night_count'),
            # CR — spatial stats + P5/P95 envelope
            'cr_day_p05'      : cr_s.get('day_median_p5'),
            'cr_day_median'   : cr_s.get('day_median_p50'),
            'cr_day_p95'      : cr_s.get('day_median_p95'),
            'cr_day_mean'     : cr_s.get('day_median_mean'),
            'cr_day_min'      : cr_s.get('day_median_min'),
            'cr_day_max'      : cr_s.get('day_median_max'),
            'cr_day_std'      : cr_s.get('day_median_stdDev'),
            'cr_day_n'        : cr_n.get('day_count'),
            'cr_night_p05'    : cr_s.get('night_median_p5'),
            'cr_night_median' : cr_s.get('night_median_p50'),
            'cr_night_p95'    : cr_s.get('night_median_p95'),
            'cr_night_mean'   : cr_s.get('night_median_mean'),
            'cr_night_min'    : cr_s.get('night_median_min'),
            'cr_night_max'    : cr_s.get('night_median_max'),
            'cr_night_std'    : cr_s.get('night_median_stdDev'),
            'cr_night_n'      : cr_n.get('night_count'),
            # Image-level counts: total, strict-quality, moderate-only supplement
            # n_images        — all MODIS granules in the month (before QA)
            # n_days          — total usable day images  (strict + moderate)
            # n_nights        — total usable night images (strict + moderate)
            # n_day_strict    — images with ≥1 strict-quality day pixel in CR
            # n_day_moderate  — images with ≥1 moderate day pixel but 0 strict (supplements)
            # n_night_strict  / n_night_moderate — same for night
            'n_images'        : col.size(),
            'n_days'          : n_day_strict.add(n_day_moderate),
            'n_nights'        : n_night_strict.add(n_night_moderate),
            'n_day_strict'    : n_day_strict,
            'n_day_moderate'  : n_day_moderate,
            'n_night_strict'  : n_night_strict,
            'n_night_moderate': n_night_moderate,
        })

    all_rows = []
    for year in years:
        for month in range(1, 13):
            try:
                # One getInfo() per month keeps the computation graph small enough
                # for large-geometry cities (e.g. Port Harcourt) that exceed GEE's
                # interactive memory limit when all 12 months are bundled together.
                feat  = get_info_retrying(_month_feature(year, month))
                feats = [feat]
            except Exception as e:
                print(f'    WARNING {city_name} {year}-{month:02d}: {e}')
                feats = []
            for f in feats:
                p = f.get('properties', {})
                if p.get('year') is None:
                    continue
                all_rows.append({
                    'year'  : int(p['year']),
                    'month' : int(p['month']),
                    # UC
                    'uc_day_mean'     : p.get('uc_day_mean'),
                    'uc_day_median'   : p.get('uc_day_median'),
                    'uc_day_min'      : p.get('uc_day_min'),
                    'uc_day_max'      : p.get('uc_day_max'),
                    'uc_day_std'      : p.get('uc_day_std'),
                    'uc_day_n'        : p.get('uc_day_n'),
                    'uc_night_mean'   : p.get('uc_night_mean'),
                    'uc_night_median' : p.get('uc_night_median'),
                    'uc_night_min'    : p.get('uc_night_min'),
                    'uc_night_max'    : p.get('uc_night_max'),
                    'uc_night_std'    : p.get('uc_night_std'),
                    'uc_night_n'      : p.get('uc_night_n'),
                    # BRA
                    'bra_day_mean'    : p.get('bra_day_mean'),
                    'bra_day_median'  : p.get('bra_day_median'),
                    'bra_day_min'     : p.get('bra_day_min'),
                    'bra_day_max'     : p.get('bra_day_max'),
                    'bra_day_std'     : p.get('bra_day_std'),
                    'bra_day_n'       : p.get('bra_day_n'),
                    'bra_night_mean'  : p.get('bra_night_mean'),
                    'bra_night_median': p.get('bra_night_median'),
                    'bra_night_min'   : p.get('bra_night_min'),
                    'bra_night_max'   : p.get('bra_night_max'),
                    'bra_night_std'   : p.get('bra_night_std'),
                    'bra_night_n'     : p.get('bra_night_n'),
                    # CR
                    'cr_day_p05'      : p.get('cr_day_p05'),
                    'cr_day_median'   : p.get('cr_day_median'),
                    'cr_day_p95'      : p.get('cr_day_p95'),
                    'cr_day_mean'     : p.get('cr_day_mean'),
                    'cr_day_min'      : p.get('cr_day_min'),
                    'cr_day_max'      : p.get('cr_day_max'),
                    'cr_day_std'      : p.get('cr_day_std'),
                    'cr_day_n'        : p.get('cr_day_n'),
                    'cr_night_p05'    : p.get('cr_night_p05'),
                    'cr_night_median' : p.get('cr_night_median'),
                    'cr_night_p95'    : p.get('cr_night_p95'),
                    'cr_night_mean'   : p.get('cr_night_mean'),
                    'cr_night_min'    : p.get('cr_night_min'),
                    'cr_night_max'    : p.get('cr_night_max'),
                    'cr_night_std'    : p.get('cr_night_std'),
                    'cr_night_n'      : p.get('cr_night_n'),
                    'n_images'        : p.get('n_images',         0),
                    'n_days'          : p.get('n_days',           0),
                    'n_nights'        : p.get('n_nights',         0),
                    'n_day_strict'    : p.get('n_day_strict',     0),
                    'n_day_moderate'  : p.get('n_day_moderate',   0),
                    'n_night_strict'  : p.get('n_night_strict',   0),
                    'n_night_moderate': p.get('n_night_moderate', 0),
                })

    if not all_rows:
        return None

    df = (_pd.DataFrame(all_rows)
            .sort_values(['year', 'month'])
            .reset_index(drop=True))
    df.to_csv(csv_path, index=False)
    meta_path.write_text(_json.dumps({
        'source_version': source_version,
        'cache_hash'    : cache_hash,
        'city'          : city_name,
        'granularity'   : 'monthly',
        'extracted_date': _dt.utcnow().isoformat(),
        'n_records'     : len(df),
    }, indent=2), encoding='utf-8')
    print(f'  [DONE ] {city_name} - {len(df)} monthly records')
    return df

