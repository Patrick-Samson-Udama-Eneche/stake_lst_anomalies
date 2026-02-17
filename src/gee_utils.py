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


def initialize_gee(service_account_key, project_id):
    """
    Initialize Google Earth Engine with service account credentials.
    
    Parameters:
    -----------
    service_account_key : str
        Path to the service account JSON file
    project_id : str
        Google Cloud Project ID
        
    Returns:
    --------
    bool
        True if initialization successful, False otherwise
    """
    try:
        if not os.path.exists(service_account_key):
            print(f"❌ Service account key not found: {service_account_key}")
            return False
            
        print(f"🔑 Found service account key: {service_account_key}")
        
        credentials = service_account.Credentials.from_service_account_file(
            service_account_key,
            scopes=['https://www.googleapis.com/auth/earthengine']
        )
        
        ee.Initialize(credentials=credentials, project=project_id)
        
        # Test the connection
        ee.Number(1).getInfo()
        
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
            
            # Process collection
            processed = collection.map(process_image)
            image_list = processed.toList(processed.size())
            collection_size = processed.size().getInfo()
            
            print(f"        📊 Processing {collection_size} images...")
            
            # Comprehensive statistics reducer: min, median, mean, max (ORIGINAL PROTOCOL)
            stats_reducer = ee.Reducer.min().combine(
                reducer2=ee.Reducer.median(), sharedInputs=True
            ).combine(
                reducer2=ee.Reducer.mean(), sharedInputs=True
            ).combine(
                reducer2=ee.Reducer.max(), sharedInputs=True
            )
            
            # Extract statistics for each image
            for j in range(collection_size):
                try:
                    image = ee.Image(image_list.get(j))
                    date_str = image.get('date').getInfo()
                    
                    # Extract LST statistics for both day and night
                    stats = image.select(['LST_Day', 'LST_Night', 'QA_Day_Source', 'QA_Night_Source']).reduceRegion(
                        reducer=stats_reducer,
                        geometry=geometry,
                        scale=1000,
                        maxPixels=1e9,
                        bestEffort=True
                    ).getInfo()
                    
                    # Calculate QA percentages (original protocol)
                    qa_day = image.select('QA_Day_Source').reduceRegion(
                        reducer=ee.Reducer.frequencyHistogram(),
                        geometry=geometry,
                        scale=1000,
                        maxPixels=1e9,
                        bestEffort=True
                    ).getInfo().get('QA_Day_Source', {})
                    
                    qa_night = image.select('QA_Night_Source').reduceRegion(
                        reducer=ee.Reducer.frequencyHistogram(),
                        geometry=geometry,
                        scale=1000,
                        maxPixels=1e9,
                        bestEffort=True
                    ).getInfo().get('QA_Night_Source', {})
                    
                    def calculate_qa_percentages(qa_hist):
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
                    
                    day_strict_pct, day_moderate_pct, day_qa_level = calculate_qa_percentages(qa_day)
                    night_strict_pct, night_moderate_pct, night_qa_level = calculate_qa_percentages(qa_night)
                    
                    # Compile comprehensive results with all statistics
                    all_results.append({
                        'date': date_str,
                        # Day LST - All Statistics (min, median, mean, max)
                        'day_lst_min': stats.get('LST_Day_min'),
                        'day_lst_median': stats.get('LST_Day_median'),
                        'day_lst_mean': stats.get('LST_Day_mean'),
                        'day_lst_max': stats.get('LST_Day_max'),
                        # Night LST - All Statistics (min, median, mean, max)
                        'night_lst_min': stats.get('LST_Night_min'),
                        'night_lst_median': stats.get('LST_Night_median'),
                        'night_lst_mean': stats.get('LST_Night_mean'),
                        'night_lst_max': stats.get('LST_Night_max'),
                        # QA Information for data quality tracking
                        'day_qa_strict_pct': round(day_strict_pct, 1),
                        'day_qa_moderate_pct': round(day_moderate_pct, 1),
                        'night_qa_strict_pct': round(night_strict_pct, 1),
                        'night_qa_moderate_pct': round(night_moderate_pct, 1),
                        'day_qa_level': day_qa_level,
                        'night_qa_level': night_qa_level
                    })
                    
                except Exception as e:
                    print(f"        ⚠️ Error processing image {j}: {e}")
        
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
