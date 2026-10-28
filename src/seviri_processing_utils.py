"""
SEVIRI LST Processing Module

Complete protocol: Download → Median → Reproject to WGS84 @ 1km → Clip to AOI

This module provides functions for processing MSG SEVIRI LST data with:
- EUMETSAT Data Store access via eumdac
- DASK-based parallel processing
- Native MSG projection handling
- Reprojection to WGS84 @ 1km resolution
- AOI clipping for city-specific analysis

Workflow:
1. Load decision tree event selections
2. Determine temporal resolution strategy (15min/1hr/daily)
3. Download SEVIRI data for selected periods
4. Extract and compute median LST in native MSG projection
5. Reproject to WGS84 @ 1km to match AOI CRS
6. Clip to city AOI boundaries

Author: Heat Stress Analysis Team
Date: 2024
"""

import os
import json
import geopandas as gpd
import numpy as np
from datetime import datetime, timedelta
import pandas as pd
from dask import delayed, compute
from dask.distributed import Client
import eumdac
import zipfile
import rasterio
from rasterio.mask import mask
from rasterio.warp import reproject, calculate_default_transform, Resampling
from rasterio.transform import from_bounds
from rasterio.crs import CRS
import warnings
warnings.filterwarnings('ignore')


def _resolve_city_aoi(city_name: str, aoi_dir: str, temp_dir: str = None) -> str | None:
    """
    Return a path to the city-region GeoJSON for SEVIRI clipping/reprojection.

    Priority:
    1. {aoi_dir}/{city_slug}/{city_slug}_city_region_102022_v5.geojson  ← preferred (ANALYSIS_CRS)
    2. {aoi_dir}/{city_slug}/{city_slug}_city_region_4326_v5.geojson
    3. GEE Asset fallback — downloads the CityRegion geometry to a temp file.

    Returns the file path, or None if both fail.
    """
    city_slug = city_name.replace(' ', '_')
    # Prefer the ESRI:102022 (analysis CRS) version — avoids degree-to-metre approximation
    for suffix in ('_city_region_102022_v5.geojson', '_city_region_4326_v5.geojson'):
        p = os.path.join(aoi_dir, city_slug, f'{city_slug}{suffix}')
        if os.path.exists(p):
            return p

    # GEE Asset fallback
    try:
        import ee, config, json as _json, tempfile
        try:
            ee.Number(1).getInfo()
        except Exception:
            config.initialize_gee()

        project_id      = config.GEE_CONFIG['project_id']
        collection_base = config.GEE_CONFIG.get('collection_name', 'AOI_Nigeria_Cities')
        asset_id        = f"projects/{project_id}/assets/{collection_base}/{city_slug}"

        fc = ee.FeatureCollection(asset_id).filter(ee.Filter.eq('zone', 'CityRegion'))
        geojson = fc.getInfo()

        if not geojson or not geojson.get('features'):
            print(f"        GEE asset has no CityRegion feature for {city_name}")
            return None

        # Save to a temp file so existing rasterio/geopandas callers work unchanged
        out_dir = temp_dir if temp_dir else os.path.join(os.path.dirname(aoi_dir), 'tmp')
        os.makedirs(out_dir, exist_ok=True)
        tmp_path = os.path.join(out_dir, f'{city_slug}_city_region_gee.geojson')
        with open(tmp_path, 'w') as _f:
            _json.dump(geojson, _f)
        print(f"        AOI loaded from GEE asset → {tmp_path}")
        return tmp_path

    except Exception as _exc:
        print(f"        GEE AOI fallback failed for {city_name}: {_exc}")
        return None


# ====================================================================
# CRS HELPER FUNCTIONS
# ====================================================================

def create_wgs84_crs():
    """
    Create WGS84 CRS without relying on EPSG database
    
    Returns:
    --------
    rasterio.crs.CRS
        WGS84 coordinate reference system
    """
    try:
        return CRS.from_epsg(4326)
    except:
        wgs84_wkt = '''GEOGCS["WGS 84",
            DATUM["WGS_1984",
                SPHEROID["WGS 84",6378137,298.257223563,
                    AUTHORITY["EPSG","7030"]],
                AUTHORITY["EPSG","6326"]],
            PRIMEM["Greenwich",0,
                AUTHORITY["EPSG","8901"]],
            UNIT["degree",0.0174532925199433,
                AUTHORITY["EPSG","9122"]],
            AUTHORITY["EPSG","4326"]]'''
        return CRS.from_wkt(wgs84_wkt)


def create_msg_crs():
    """
    Create MSG geostationary CRS for SEVIRI data
    
    Returns:
    --------
    rasterio.crs.CRS
        MSG geostationary coordinate reference system
    """
    try:
        return CRS.from_proj4("+proj=geos +lon_0=0 +h=35785831 +x_0=0 +y_0=0 +ellps=WGS84 +units=m +no_defs")
    except:
        msg_wkt = '''PROJCS["Geostationary_Satellite",
            GEOGCS["WGS 84",
                DATUM["WGS_1984",
                    SPHEROID["WGS 84",6378137,298.257223563]],
                PRIMEM["Greenwich",0],
                UNIT["degree",0.0174532925199433]],
            PROJECTION["Geostationary_Satellite"],
            PARAMETER["central_meridian",0],
            PARAMETER["satellite_height",35785831],
            PARAMETER["false_easting",0],
            PARAMETER["false_northing",0],
            UNIT["metre",1]]'''
        return CRS.from_wkt(msg_wkt)


# ====================================================================
# HELPER FUNCTIONS
# ====================================================================

def get_temporal_resolution_strategy(duration_days):
    """
    Determine temporal resolution based on event duration.

    Protocol:
    ---------
    ≤ 4 days  →  15-min  (13 timestamps/day × 3-h window — max cloud sampling)
    5–7 days  →  30-min  (7 timestamps/day — balance coverage vs download volume)
    > 7 days  →  1-hr    (4 timestamps/day — long events; median still robust)

    Parameters:
    -----------
    duration_days : int
        Duration of the selected event in days.

    Returns:
    --------
    tuple : (strategy_str, interval_minutes)
    """
    if duration_days <= 4:
        return "15min", 15
    elif duration_days <= 7:
        return "30min", 30
    else:
        return "1hr", 60


def load_city_event_periods(city_name, output_dir, study_year):
    """
    Load selected event periods from decision tree results
    
    Parameters:
    -----------
    city_name : str
        Name of city
    output_dir : str or Path
        Base output directory
    study_year : int
        Study year
    
    Returns:
    --------
    dict : Event periods for day and night
    """
    # Try both subfolder naming conventions (old: 04_trend, new: 04_temporal)
    _nb04_subfolders = ['04_trend_analysis_daily', '04_temporal_analysis_daily']
    results_file = next(
        (os.path.join(output_dir, sub, f'decision_tree_selections_{study_year}.json')
         for sub in _nb04_subfolders
         if os.path.exists(os.path.join(output_dir, sub, f'decision_tree_selections_{study_year}.json'))),
        os.path.join(output_dir, '04_trend_analysis_daily', f'decision_tree_selections_{study_year}.json')
    )

    if not os.path.exists(results_file):
        # Fallback: try per-city event audit JSON written by the NB04 pipeline.
        # Try slug name (standard) then canonical name (legacy, spaces in filename).
        _city_slug = city_name.replace(' ', '_')
        _audit_candidates = [
            os.path.join(output_dir, sub, 'events', f'{name}_event_audit.json')
            for sub in _nb04_subfolders
            for name in (_city_slug, city_name)
        ]
        audit_file = next((p for p in _audit_candidates if os.path.exists(p)), None)
        if audit_file is None:
            raise FileNotFoundError(
                f"Decision tree results not found: {results_file}\n"
                f"Fallback audit also not found for '{city_name}' in any known subfolder."
            )
        with open(audit_file, 'r') as _f:
            _audit = json.load(_f)
        # Convert our audit format to the expected format
        city_result = {
            'city': city_name,
            'selected_events': {
                'day':   (_audit.get('day')   or {}).get('selected_event'),
                'night': (_audit.get('night') or {}).get('selected_event'),
            },
        }
        # Wrap flat event dicts into period_used subdict if needed
        for _period in ('day', 'night'):
            _sel = city_result['selected_events'][_period]
            if _sel and 'period_used' not in _sel:
                city_result['selected_events'][_period] = {
                    'period_used': {
                        'start_date': _sel.get('start_date'),
                        'end_date':   _sel.get('end_date'),
                        'duration':   _sel.get('duration', 0),
                    },
                    'source': 'era5_persistent',
                    'tier':   _sel.get('tier', 'FAIR'),
                }
    else:
        with open(results_file, 'r') as f:
            all_results = json.load(f)
        city_result = None
        for result in all_results:
            if result['city'].lower() == city_name.lower():
                city_result = result
                break
        if not city_result:
            raise ValueError(f"No decision tree results found for {city_name}")
    
    events = {}
    for period_type in ['day', 'night']:
        _raw = city_result['selected_events'][period_type]
        if _raw:
            # Support both period_used-wrapped and flat selected_event formats
            if 'period_used' in _raw:
                period_info = _raw['period_used']
                _source = _raw.get('source', 'era5_persistent')
            else:
                period_info = _raw
                _source = _raw.get('source', 'era5_persistent')
            _qflag = (city_result.get('decision_log') or {}).get(period_type, {}).get('quality_flag', 'FAIR')
            events[period_type] = {
                'start_date': pd.to_datetime(period_info['start_date']).date(),
                'end_date': pd.to_datetime(period_info['end_date']).date(),
                'duration': period_info.get('duration', 0),
                'source': _source,
                'quality_flag': _qflag,
            }
    
    if not events:
        # Collect rationale from decision log for informative messaging
        reasons = []
        for pt in ['day', 'night']:
            log = city_result.get('decision_log', {}).get(pt, {})
            rationale = log.get('rationale', 'unknown reason')
            reasons.append(f"{pt}: {rationale}")
        raise ValueError(
            f"No heat events selected for {city_name} — "
            + "; ".join(reasons)
        )
    
    return events


def setup_eumetsat_connection(credentials):
    """
    Initialize EUMETSAT Data Store connection
    
    Parameters:
    -----------
    credentials : dict
        EUMETSAT credentials with 'consumer_key' and 'consumer_secret'
    
    Returns:
    --------
    tuple : (datastore, lst_collection) or (None, None) if failed
    """
    try:
        print("    Connecting to EUMETSAT Data Store...")
        creds_tuple = (credentials['consumer_key'], credentials['consumer_secret'])
        token = eumdac.AccessToken(creds_tuple)
        datastore = eumdac.DataStore(token)
        
        collections = datastore.collections
        lst_collection = None
        
        for c in collections:
            if "Land Surface Temperature with Directional Effects - MSG" in c.title:
                lst_collection = c
                break
        
        if not lst_collection:
            raise RuntimeError("SEVIRI LST collection not found")
        
        print(f"        Connected to: {lst_collection.title}")
        return datastore, lst_collection
        
    except Exception as e:
        print(f"    Error connecting to EUMETSAT: {e}")
        return None, None


def generate_timestamp_list(start_date, end_date, period_type, strategy):
    """
    Generate list of timestamps to download
    
    Parameters:
    -----------
    start_date : datetime.date
        Event start date
    end_date : datetime.date
        Event end date
    period_type : str
        'day' or 'night'
    strategy : str
        '15min', '1hr', or 'daily'
    
    Returns:
    --------
    list : Sorted list of datetime timestamps
    """
    timestamps = []
    current_date = start_date
    
    while current_date <= end_date:
        if strategy == "15min":
            if period_type == 'day':
                # DAY: 12:00 to 15:00 (inclusive)
                for hour in range(12, 16):  # 12, 13, 14, 15
                    for minute in [0, 15, 30, 45]:
                        timestamp = datetime.combine(current_date, datetime.min.time()) + \
                                  timedelta(hours=hour, minutes=minute)
                        # Only include up to 15:00, not 15:15, 15:30, 15:45
                        if not (hour == 15 and minute > 0):
                            timestamps.append(timestamp)
            else:
                # NIGHT: 00:00 to 03:00 (inclusive)
                for hour in range(0, 4):  # 0, 1, 2, 3
                    for minute in [0, 15, 30, 45]:
                        timestamp = datetime.combine(current_date, datetime.min.time()) + \
                                  timedelta(hours=hour, minutes=minute)
                        # Only include up to 03:00, not 03:15, 03:30, 03:45
                        if not (hour == 3 and minute > 0):
                            timestamps.append(timestamp)
        
        elif strategy == "30min":
            if period_type == 'day':
                for hour in range(12, 16):
                    for minute in [0, 30]:
                        if not (hour == 15 and minute > 0):
                            timestamps.append(
                                datetime.combine(current_date, datetime.min.time())
                                + timedelta(hours=hour, minutes=minute)
                            )
            else:
                for hour in range(0, 4):
                    for minute in [0, 30]:
                        if not (hour == 3 and minute > 0):
                            timestamps.append(
                                datetime.combine(current_date, datetime.min.time())
                                + timedelta(hours=hour, minutes=minute)
                            )

        elif strategy == "1hr":
            if period_type == 'day':
                # DAY: 12:00 to 15:00 (inclusive)
                for hour in range(12, 16):  # 12, 13, 14, 15
                    timestamp = datetime.combine(current_date, datetime.min.time()) + \
                              timedelta(hours=hour)
                    timestamps.append(timestamp)
            else:
                # NIGHT: 00:00 to 03:00 (inclusive)
                for hour in range(0, 4):  # 0, 1, 2, 3
                    timestamp = datetime.combine(current_date, datetime.min.time()) + \
                              timedelta(hours=hour)
                    timestamps.append(timestamp)
        
        else:  # daily
            if period_type == 'day':
                # DAY: Single timestamp at 13:30 (middle of 12:00-15:00 window)
                timestamp = datetime.combine(current_date, datetime.min.time()) + \
                          timedelta(hours=13, minutes=30)
            else:
                # NIGHT: Single timestamp at 01:30 (middle of 00:00-03:00 window)
                timestamp = datetime.combine(current_date, datetime.min.time()) + \
                          timedelta(hours=1, minutes=30)
            timestamps.append(timestamp)
        
        current_date += timedelta(days=1)
    
    return sorted(timestamps)


# ====================================================================
# SEVIRI DATA PROCESSING FUNCTIONS
# ====================================================================

@delayed
def download_seviri_timestamp(collection, timestamp, temp_dir, city_name, period_type):
    """
    Download single SEVIRI timestamp (DASK delayed function)
    
    Parameters:
    -----------
    collection : eumdac.Collection
        EUMETSAT collection object
    timestamp : datetime
        Timestamp to download
    temp_dir : str
        Temporary directory for downloads
    city_name : str
        City name
    period_type : str
        'day' or 'night'
    
    Returns:
    --------
    str or None : Path to downloaded file or None if failed
    """
    try:
        start_time = timestamp
        end_time = timestamp + timedelta(minutes=30)
        
        products = list(collection.search(dtstart=start_time, dtend=end_time))
        
        if not products:
            return None
        
        product = products[0]
        filename = f"{city_name}_{period_type}_{timestamp.strftime('%Y%m%d_%H%M')}.zip"
        output_path = os.path.join(temp_dir, filename)
        
        with product.open() as src:
            blob = src.read()
        
        with open(output_path, 'wb') as f:
            f.write(blob)
        
        return output_path
        
    except Exception as e:
        print(f"        Error downloading {timestamp}: {e}")
        return None


def extract_and_subset_seviri_native(zip_path, target_resolution=3000):
    """
    Extract SEVIRI data preserving NATIVE MSG projection
    
    Parameters:
    -----------
    zip_path : str
        Path to downloaded ZIP file
    target_resolution : int, default=3000
        Target resolution in meters
    
    Returns:
    --------
    tuple or None : (lst_data, transform) or None if failed
    """
    try:
        print(f"        Extracting: {os.path.basename(zip_path)}")
        
        extract_dir = zip_path.replace('.zip', '_extracted')
        os.makedirs(extract_dir, exist_ok=True)
        
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(extract_dir)
        
        h5_candidates = []
        for root, dirs, files in os.walk(extract_dir):
            for file in files:
                file_path = os.path.join(root, file)
                if (('lst' in file.lower() or 'LST' in file) and 
                    not file.endswith(('.xml', '.txt', '.json', '.md')) and
                    os.path.getsize(file_path) > 1000000):
                    h5_candidates.append(file_path)
        
        if not h5_candidates:
            return None
        
        h5_path = max(h5_candidates, key=os.path.getsize)
        
        gpath = h5_path.replace("\\", "/")
        sds_path = f'HDF5:"{gpath}"://LST'
        
        try:
            with rasterio.open(sds_path) as src:
                data = src.read(1).astype(np.float32)
                native_transform = src.transform
                
                data[data == -8000] = np.nan
                data = data / 100.0
                data[(data < -50) | (data > 70)] = np.nan
                
        except Exception as read_error:
            print(f"        HDF5 read failed: {read_error}")
            return None
        
        import shutil
        shutil.rmtree(extract_dir, ignore_errors=True)
        
        return data, native_transform
        
    except Exception as e:
        print(f"        Error in extraction: {e}")
        return None


def spatial_interpolate_gaps(data, max_distance=5, method='nearest'):
    """
    Fill gaps in LST data using spatial interpolation
    
    Parameters:
    -----------
    data : np.ndarray
        2D array with NaN gaps
    max_distance : int
        Maximum distance (in pixels) to search for valid values
    method : str
        'nearest' or 'idw' (inverse distance weighting)
    
    Returns:
    --------
    np.ndarray : Interpolated data
    """
    from scipy.ndimage import distance_transform_edt
    from scipy.interpolate import griddata
    
    # Create copy to avoid modifying original
    filled = data.copy()
    
    # Find gap pixels
    gap_mask = np.isnan(filled)
    n_gaps = np.sum(gap_mask)
    
    if n_gaps == 0:
        return filled
    
    # Find valid pixels
    valid_mask = ~gap_mask
    n_valid = np.sum(valid_mask)
    
    if n_valid == 0:
        return filled  # Nothing to interpolate from
    
    # Distance transform: how far is each gap pixel from nearest valid pixel
    distances, _ = distance_transform_edt(gap_mask, return_indices=True)
    
    # Only fill gaps within max_distance
    fillable_mask = gap_mask & (distances <= max_distance)
    n_fillable = np.sum(fillable_mask)
    
    if n_fillable == 0:
        return filled
    
    # Get coordinates of valid and fillable pixels
    rows, cols = np.indices(filled.shape)
    valid_points = np.column_stack([rows[valid_mask], cols[valid_mask]])
    valid_values = filled[valid_mask]
    fillable_points = np.column_stack([rows[fillable_mask], cols[fillable_mask]])
    
    # Interpolate using nearest neighbor or griddata
    if method == 'nearest' or n_valid < 4:
        # Nearest neighbor (fast, works with few points)
        from scipy.spatial import cKDTree
        tree = cKDTree(valid_points)
        _, nearest_idx = tree.query(fillable_points, k=1)
        filled[fillable_mask] = valid_values[nearest_idx]
    else:
        # Inverse distance weighting via griddata (smoother, needs more points)
        try:
            interpolated = griddata(valid_points, valid_values, fillable_points, 
                                   method='linear', fill_value=np.nan)
            # Fill any remaining NaN with nearest
            still_nan = np.isnan(interpolated)
            if np.any(still_nan):
                interpolated[still_nan] = griddata(valid_points, valid_values, 
                                                   fillable_points[still_nan], 
                                                   method='nearest')
            filled[fillable_mask] = interpolated
        except:
            # Fallback to nearest neighbor if griddata fails
            from scipy.spatial import cKDTree
            tree = cKDTree(valid_points)
            _, nearest_idx = tree.query(fillable_points, k=1)
            filled[fillable_mask] = valid_values[nearest_idx]
    
    return filled


def compute_median_lst_native_msg(lst_inputs, output_path, transform=None, city_name=None):
    """
    Compute median LST in native MSG projection with optional water masking
    
    Parameters:
    -----------
    lst_inputs : list
        List of LST numpy arrays  **or**  list of str paths to .npy files
        on disk (memory-mapped mode — avoids holding all arrays in RAM).
    output_path : str
        Output GeoTIFF path
    transform : affine.Affine, optional
        Affine transform for georeferencing
    city_name : str, optional
        City name for water masking (e.g., 'Lagos', 'Abuja')
        If provided, will apply OSM water body masking after interpolation
    
    Returns:
    --------
    str or None : Path to saved GeoTIFF or None if failed
    """
    try:
        if not lst_inputs:
            print("        No valid LST arrays to process")
            return None
        
        # Detect mode: in-memory arrays  vs  disk-backed .npy paths
        disk_mode = isinstance(lst_inputs[0], (str, os.PathLike))
        
        if disk_mode:
            ref = np.load(lst_inputs[0], mmap_mode='r')
            height, width = ref.shape
            del ref
        else:
            height, width = lst_inputs[0].shape
        
        n_arrays = len(lst_inputs)
        mode_label = 'disk-backed' if disk_mode else 'in-memory'
        print(f"        Computing median ({mode_label}): "
              f"{width} x {height} pixels from {n_arrays} arrays")
        
        # Chunked row processing to avoid OOM on full-disk stacks.
        # np.nanmedian internally copies + partitions, so peak ≈ 3× chunk.
        # Target ~200 MiB per raw chunk → ~600 MiB peak with nanmedian.
        TARGET_CHUNK_BYTES = 200 * 1024 * 1024          # 200 MiB
        bytes_per_row = n_arrays * width * 4             # float32
        chunk_rows = max(8, min(256, TARGET_CHUNK_BYTES // max(bytes_per_row, 1)))
        
        median_lst = np.full((height, width), np.nan, dtype=np.float32)
        valid_count = np.zeros((height, width), dtype=np.float32)
        
        n_chunks = -(-height // chunk_rows)              # ceil division
        print(f"        Processing in {n_chunks} chunks of {chunk_rows} rows "
              f"(~{bytes_per_row * chunk_rows / 1024**2:.0f} MiB/chunk)")
        
        for r0 in range(0, height, chunk_rows):
            r1 = min(r0 + chunk_rows, height)
            if disk_mode:
                # Load only the needed row slice from each file (mmap)
                slices = [np.load(p, mmap_mode='r')[r0:r1, :].astype(np.float32)
                          for p in lst_inputs]
            else:
                slices = [a[r0:r1, :] for a in lst_inputs]
            chunk = np.stack(slices, axis=0)
            del slices
            median_lst[r0:r1, :] = np.nanmedian(chunk, axis=0).astype(np.float32)
            valid_count[r0:r1, :] = np.sum(~np.isnan(chunk), axis=0).astype(np.float32)
            del chunk
        
        # Calculate coverage before interpolation
        total_pixels = median_lst.size
        valid_before = np.sum(~np.isnan(median_lst))
        gap_before = total_pixels - valid_before
        coverage_before = 100 * valid_before / total_pixels
        print(f"        Coverage before interpolation: {coverage_before:.1f}% ({valid_before:,}/{total_pixels:,} pixels)")
        
        # Apply spatial interpolation to fill gaps
        if gap_before > 0:
            print(f"        Applying spatial interpolation (max distance: 5 pixels)...")
            median_lst = spatial_interpolate_gaps(median_lst, max_distance=5, method='nearest')
            valid_after = np.sum(~np.isnan(median_lst))
            coverage_after = 100 * valid_after / total_pixels
            filled_count = valid_after - valid_before
            print(f"        Coverage after interpolation:  {coverage_after:.1f}% ({valid_after:,}/{total_pixels:,} pixels)")
            print(f"        Filled {filled_count:,} gap pixels ({100*filled_count/gap_before:.1f}% of gaps)")
        
        # NOTE: water masking is intentionally NOT applied here.
        # The native MSG step covers the full disk at 3 km geostationary projection;
        # rasterizing WGS84 water polygons onto that grid is geometrically incorrect.
        # Water masking is applied correctly in reproject_to_analysis_crs() after the
        # MSG→WGS84 reprojection, when the grid is city-area-specific at 1 km resolution.

        
        try:
            msg_crs = create_msg_crs()
        except Exception as e:
            msg_crs = "+proj=geos +lon_0=0 +h=35785831 +x_0=0 +y_0=0 +ellps=WGS84 +units=m +no_defs"
        
        if transform is None:
            # MSG SEVIRI full disk extent
            west_bound = -5568742.4
            east_bound = 5568742.4
            south_bound = -5568742.4
            north_bound = 5568742.4
            
            transform = from_bounds(
                west_bound, south_bound, east_bound, north_bound,
                width, height
            )
        
        profile = {
            'driver': 'GTiff',
            'dtype': 'float32',
            'nodata': np.nan,
            'width': width,
            'height': height,
            'count': 2,
            'crs': msg_crs,
            'transform': transform,
            'compress': 'deflate',
            'predictor': 2,
            'tiled': True,
            'blockxsize': 512,
            'blockysize': 512
        }
        
        with rasterio.open(output_path, 'w', **profile) as dst:
            dst.write(median_lst.astype(np.float32), 1)
            dst.write(valid_count.astype(np.float32), 2)
            
            dst.update_tags(
                PRODUCT='SEVIRI_LST_Median_Native',
                UNITS='Degrees_Celsius',
                SPATIAL_RESOLUTION='3km_native',
                SATELLITE='MSG_SEVIRI',
                PROJECTION='MSG_Geostationary_Native'
            )
        
        print(f"        Saved native GeoTIFF: {os.path.basename(output_path)}")
        
        # Calculate coverage statistics
        total_pixels = median_lst.size
        valid_before = np.sum(~np.isnan(median_lst))
        gap_before = total_pixels - valid_before
        coverage_before = 100 * valid_before / total_pixels
        print(f"        Coverage before interpolation: {coverage_before:.1f}% ({valid_before:,}/{total_pixels:,} pixels)")
        
        return output_path
        
    except Exception as e:
        print(f"        Error in median computation: {e}")
        return None


def reproject_to_analysis_crs(input_path, output_dir, city_name, period_type, aoi_path, date_str,
                              target_res_m: int = 1000, aoi_dir=None):
    """
    Reproject MSG native GeoTIFF to ESRI:102022 (Africa Albers Equal Area Conic) at 1 km.

    ESRI:102022 is the project ANALYSIS_CRS (config.py §2.3): equal-area, metric units,
    appropriate for all spatial operations across Nigeria.  The final SEVIRI raster
    must be in this CRS so that zonal statistics (UC / BRA / CR), area calculations,
    and hotspot analysis are geometrically correct.

    Parameters:
    -----------
    input_path : str
        Native MSG GeoTIFF (geostationary projection).
    output_dir : str
        Output directory for the reprojected file.
    city_name : str
        City name (used for water masking and filename).
    period_type : str
        'day' or 'night'.
    aoi_path : str
        Path to city-region GeoJSON (preferably _102022_v5 version).
    date_str : str
        Event date string for filename (e.g. '20240615_20240620').
    target_res_m : int
        Target pixel size in metres (default 1000 m = 1 km).

    Returns:
    --------
    str or None : Path to reprojected GeoTIFF, or None if failed.
    """
    ANALYSIS_CRS = "ESRI:102022"
    BUFFER_M     = 50_000   # 50 km margin around city region

    try:
        print(f"    Reprojecting MSG → {ANALYSIS_CRS} @ {target_res_m} m ...")

        aoi_gdf = gpd.read_file(aoi_path)
        # Ensure AOI is in the analysis CRS for metric bounding box
        aoi_102022 = aoi_gdf.to_crs(ANALYSIS_CRS) if str(aoi_gdf.crs) != ANALYSIS_CRS else aoi_gdf
        xmin, ymin, xmax, ymax = aoi_102022.total_bounds

        # Add 50 km buffer in metric units
        xmin -= BUFFER_M;  ymin -= BUFFER_M
        xmax += BUFFER_M;  ymax += BUFFER_M

        width  = max(1, int(round((xmax - xmin) / target_res_m)))
        height = max(1, int(round((ymax - ymin) / target_res_m)))

        dst_transform = from_bounds(xmin, ymin, xmax, ymax, width, height)
        dst_crs = CRS.from_user_input(ANALYSIS_CRS)

        print(f"        AOI extent ({ANALYSIS_CRS}): "
              f"{xmin/1e3:.1f}–{xmax/1e3:.1f} km E, {ymin/1e3:.1f}–{ymax/1e3:.1f} km N")
        print(f"        Output grid: {width} × {height} px @ {target_res_m} m")

        dst_data = np.full((height, width), np.nan, dtype=np.float32)

        with rasterio.open(input_path) as src:
            reproject(
                source=rasterio.band(src, 1),
                destination=dst_data,
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=dst_transform,
                dst_crs=dst_crs,
                resampling=Resampling.bilinear,
                src_nodata=np.nan,
                dst_nodata=np.nan,
                num_threads=2,
            )

        valid_pixels = int(np.sum(~np.isnan(dst_data)))
        if valid_pixels == 0:
            print("        WARNING: No valid data after reprojection!")
            return None

        # Post-reprojection gap fill — MSG→Albers introduces geometric NaN
        # at the full-disk boundary (~10-17 % of pixels in city window).
        # Fill with nearest-neighbour up to 20 pixels (= 20 km at 1 km res).
        total_pixels = dst_data.size
        pre_pct = 100 * valid_pixels / total_pixels
        dst_data = spatial_interpolate_gaps(dst_data, max_distance=20, method='nearest')
        post_valid = int(np.sum(~np.isnan(dst_data)))
        post_pct   = 100 * post_valid / total_pixels
        print(f"        Gap fill: {pre_pct:.1f}% → {post_pct:.1f}%  "
              f"(+{post_valid - valid_pixels:,} px)")

        output_filename = (f"{city_name}_SEVIRI_{period_type}_{date_str}"
                           f"_median_102022_1km.tif")
        output_path = os.path.join(output_dir, output_filename)

        profile = {
            'driver': 'GTiff', 'dtype': 'float32', 'nodata': np.nan,
            'width': width, 'height': height, 'count': 1,
            'crs': dst_crs, 'transform': dst_transform,
            'compress': 'deflate', 'tiled': True,
            'blockxsize': 256, 'blockysize': 256,
        }
        with rasterio.open(output_path, 'w', **profile) as dst:
            dst.write(dst_data, 1)
            dst.update_tags(
                PRODUCT='SEVIRI_LST_Median_Reprojected',
                UNITS='Degrees_Celsius',
                SPATIAL_RESOLUTION=f'{target_res_m}m',
                ORIGINAL_RESOLUTION='3km_MSG',
                TARGET_CRS=ANALYSIS_CRS,
                RESAMPLING='bilinear',
                GAP_FILL='nearest_20km',
                AOI_FILE=os.path.basename(aoi_path),
            )

        print(f"        Reprojection complete: {post_valid:,} valid pixels")

        # Apply water masking in 102022 — reprojection can interpolate across
        # water pixels so we must re-mask AFTER reprojection.
        try:
            import sys as _sys
            _src_dir = os.path.dirname(os.path.abspath(__file__))
            if _src_dir not in _sys.path:
                _sys.path.insert(0, _src_dir)
            from data_io import load_osm_water_mask
            print(f"        Applying water masking (102022) for {city_name}...")
            with rasterio.open(output_path, 'r+') as f:
                data = f.read(1)
                from pathlib import Path as _Path
                water_mask = load_osm_water_mask(
                    city_name, data.shape, f.transform, str(f.crs),
                    aoi_dir=_Path(aoi_dir) if aoi_dir else None
                )
                if np.any(water_mask):
                    masked = np.where(water_mask, np.nan, data)
                    f.write(masked, 1)
                    print(f"        Masked {int(np.sum(water_mask)):,} water pixels → "
                          f"{int(np.sum(~np.isnan(masked))):,} valid remain")
        except Exception as _we:
            print(f"        Warning: water masking failed: {_we}")

        return output_path

    except Exception as e:
        print(f"        Error in reprojection: {e}")
        import traceback
        traceback.print_exc()
        return None


# Backward-compat alias (old name used in skip-logic checks)
reproject_to_wgs84_1km = reproject_to_analysis_crs


def clip_seviri_to_city_aoi(seviri_geotiff_path, city_name, output_dir, date_str, period_type, aoi_dir):
    """
    Clip the WGS84 1km GeoTIFF to city AOI
    
    Parameters:
    -----------
    seviri_geotiff_path : str
        Path to reprojected SEVIRI GeoTIFF
    city_name : str
        City name
    output_dir : str
        Output directory
    date_str : str
        Date string for filename
    period_type : str
        'day' or 'night'
    aoi_dir : str
        Base AOI directory
    
    Returns:
    --------
    str or None : Path to clipped GeoTIFF or None if failed
    """
    try:
        print(f"    Clipping to {city_name} AOI...")
        
        city_aoi_path = _resolve_city_aoi(city_name, aoi_dir)
        if city_aoi_path is None:
            print(f"        AOI file not found for {city_name}")
            return None
        
        aoi_gdf = gpd.read_file(city_aoi_path)
        
        with rasterio.open(seviri_geotiff_path) as src:
            if aoi_gdf.crs != src.crs:
                aoi_gdf = aoi_gdf.to_crs(src.crs)
            
            clipped_data, clipped_transform = mask(src, aoi_gdf.geometry, 
                                                  crop=True, nodata=np.nan)
            
            clipped_profile = src.profile.copy()
            clipped_profile.update({
                'height': clipped_data.shape[1],
                'width': clipped_data.shape[2],
                'transform': clipped_transform
            })
            
            clipped_filename = f"{city_name}_SEVIRI_{period_type}_{date_str}_median_102022_1km_clipped.tif"
            clipped_path = os.path.join(output_dir, clipped_filename)
            
            with rasterio.open(clipped_path, 'w', **clipped_profile) as dst:
                dst.write(clipped_data)
                dst.update_tags(
                    CLIPPED_TO=city_name,
                    AOI_FILE=os.path.basename(city_aoi_path)
                )
            
            valid_pixels = np.sum(~np.isnan(clipped_data))
            print(f"        Clipping successful: {valid_pixels:,} valid pixels")
            
            return clipped_path
            
    except Exception as e:
        print(f"        Error clipping: {e}")
        return None


# ====================================================================
# MAIN PROCESSING WORKFLOW
# ====================================================================

def process_single_event(city_name, period_type, timestamps, lst_collection, 
                        temp_dir, output_dir, event_info, aoi_dir):
    """
    Process single event with complete workflow and skip logic
    
    Parameters:
    -----------
    city_name : str
        City name
    period_type : str
        'day' or 'night'
    timestamps : list
        List of timestamps to process
    lst_collection : eumdac.Collection
        EUMETSAT collection
    temp_dir : str
        Temporary directory
    output_dir : str
        Output directory
    event_info : dict
        Event information from decision tree
    aoi_dir : str
        Base AOI directory
    
    Returns:
    --------
    dict : Processing results with status and file paths
    """
    try:
        start_date = event_info['start_date']
        end_date = event_info['end_date']
        date_str = f"{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}"
        
        native_filename = f"{city_name}_SEVIRI_{period_type}_{date_str}_median_MSG3km.tif"
        reprojected_filename = f"{city_name}_SEVIRI_{period_type}_{date_str}_median_102022_1km.tif"
        clipped_filename = f"{city_name}_SEVIRI_{period_type}_{date_str}_median_102022_1km_clipped.tif"
        
        native_path = os.path.join(output_dir, native_filename)
        reprojected_path_expected = os.path.join(output_dir, reprojected_filename)
        clipped_path_expected = os.path.join(output_dir, clipped_filename)
        
        # SKIP LOGIC: clipped file is the final deliverable — if it exists, nothing to do
        if os.path.exists(clipped_path_expected):
            print(f"        SKIP: {clipped_filename} already exists")
            metadata_path = clipped_path_expected.replace('.tif', '_metadata.json')
            metadata = {}
            if os.path.exists(metadata_path):
                with open(metadata_path, 'r') as f:
                    metadata = json.load(f)
            return {
                'status': 'skipped',
                'clipped_path': clipped_path_expected,
                'metadata': metadata
            }
        
        print(f"        Processing {len(timestamps)} timestamps...")
        
        # SKIP LOGIC: Check if native file exists
        if os.path.exists(native_path):
            print(f"        SKIP: Using existing native file")
            result_path = native_path
        else:
            # Download and process
            download_tasks = []
            for timestamp in timestamps:
                task = download_seviri_timestamp(
                    lst_collection, timestamp, temp_dir, city_name, period_type
                )
                download_tasks.append(task)
            
            print(f"        Downloading...")
            downloaded_files = compute(*download_tasks)
            valid_files = [f for f in downloaded_files if f is not None]
            print(f"        Downloaded: {len(valid_files)}/{len(timestamps)}")
            
            if not valid_files:
                return None
            
            print(f"        Extracting LST...")
            lst_npy_paths = []   # save to disk instead of accumulating in RAM
            ref_shape = None
            
            for zip_file in valid_files:
                lst_result = extract_and_subset_seviri_native(zip_file)
                if lst_result is not None:
                    lst_data, file_transform = lst_result
                    if ref_shape is None:
                        ref_shape = lst_data.shape
                    # Persist to a temp .npy file and free the array immediately
                    npy_path = zip_file.replace('.zip', '.npy')
                    np.save(npy_path, lst_data.astype(np.float32))
                    lst_npy_paths.append(npy_path)
                    del lst_data
                # Delete the downloaded zip — no longer needed after extraction
                try:
                    os.remove(zip_file)
                except OSError:
                    pass

            print(f"        Valid LST arrays: {len(lst_npy_paths)}")

            if not lst_npy_paths:
                return None

            # Create transform
            height, width = ref_shape
            correct_transform = from_bounds(
                -5568742.4, -5568742.4, 5568742.4, 5568742.4,
                width, height
            )

            result_path = compute_median_lst_native_msg(
                lst_npy_paths, native_path, correct_transform, city_name
            )

            # Clean up temp .npy files — median is now in native_path
            for p in lst_npy_paths:
                try:
                    os.remove(p)
                except OSError:
                    pass

            if not result_path:
                return None

        # Resolve AOI path (local Results/ first, then GEE asset fallback)
        aoi_path = _resolve_city_aoi(city_name, aoi_dir, temp_dir)
        if aoi_path is None:
            print(f"        WARNING: AOI not found for {city_name} — cannot reproject/clip")
            return {'status': 'partial', 'native_path': result_path}
        
        # SKIP LOGIC: Check if reprojected file exists
        if os.path.exists(reprojected_path_expected):
            print(f"        SKIP: Using existing reprojected file")
            reprojected_path = reprojected_path_expected
        else:
            reprojected_path = reproject_to_analysis_crs(result_path, output_dir,
                                                      city_name, period_type,
                                                      aoi_path, date_str,
                                                      aoi_dir=aoi_dir)
            if not reprojected_path:
                return None
        
        # Clip to AOI — this is the final deliverable
        clipped_path = clip_seviri_to_city_aoi(reprojected_path, city_name,
                                               output_dir, date_str, period_type, aoi_dir)

        # Delete intermediates once the clipped file exists (old protocol: keep only final)
        if clipped_path and os.path.exists(clipped_path):
            for _tmp in [result_path, reprojected_path]:
                if _tmp and _tmp != clipped_path and os.path.exists(_tmp):
                    try:
                        os.remove(_tmp)
                        print(f"        Deleted intermediate: {os.path.basename(_tmp)}")
                    except OSError:
                        pass

        # Metadata — record what was produced
        metadata = {
            'city': city_name,
            'period_type': period_type,
            'event_start_date': str(start_date),
            'event_end_date': str(end_date),
            'event_duration_days': event_info['duration'],
            'processing_date': datetime.now().isoformat(),
            'clipped_file': clipped_filename,
            'intermediates_deleted': True,
        }

        metadata_path = clipped_path.replace('.tif', '_metadata.json') if clipped_path \
            else os.path.join(output_dir, clipped_filename.replace('.tif', '_metadata.json'))
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2, default=str)

        return {
            'status': 'success',
            'clipped_path': clipped_path,
            'metadata': metadata,
        }
        
    except Exception as e:
        print(f"        Error: {e}")
        import traceback
        traceback.print_exc()
        return {'status': 'error', 'error': str(e)}


def process_city_seviri_events(city_name, eumetsat_creds, output_dir, study_year, 
                               temp_dir, aoi_dir):
    """
    Process SEVIRI LST for all events in a city
    
    Parameters:
    -----------
    city_name : str
        City name
    eumetsat_creds : dict
        EUMETSAT credentials
    output_dir : str
        Base output directory
    study_year : int
        Study year
    temp_dir : str
        Temporary directory
    aoi_dir : str
        Base AOI directory
    
    Returns:
    --------
    dict : Results for day and night events
    """
    print(f"\nProcessing {city_name}")
    print("-" * 40)
    
    try:
        events = load_city_event_periods(city_name, output_dir, study_year)
    except ValueError as ve:
        # No events selected — this is expected for some cities (e.g. Lagos)
        print(f"    SKIP: {ve}")
        return {'_status': 'no_events', '_reason': str(ve)}
    
    try:
        datastore, lst_collection = setup_eumetsat_connection(eumetsat_creds)
        if not datastore:
            raise RuntimeError("Failed to connect to EUMETSAT")
        
        # Try new Results/ structure first, fall back to old data/outputs/ structure
        _nb04_subfolders = ['04_temporal_analysis_daily', '04_trend_analysis_daily']
        _nb04_sub = next(
            (s for s in _nb04_subfolders if os.path.isdir(os.path.join(output_dir, s))),
            '04_temporal_analysis_daily'
        )
        # Output folder uses canonical city name (spaces preserved) — consistent with
        # how city names appear in DataFrames, CSVs and audit JSONs.
        # AOI reading still uses city_slug internally via _resolve_city_aoi().
        city_output_dir = os.path.join(output_dir, _nb04_sub, 'seviri', city_name)
        os.makedirs(city_output_dir, exist_ok=True)
        
        results = {}
        
        for period_type, event_info in events.items():
            print(f"\n    Processing {period_type.upper()}:")
            print(f"        Period: {event_info['start_date']} to {event_info['end_date']}")
            
            strategy, _ = get_temporal_resolution_strategy(event_info['duration'])
            
            timestamps = generate_timestamp_list(
                event_info['start_date'], 
                event_info['end_date'], 
                period_type, 
                strategy
            )
            
            event_temp_dir = os.path.join(temp_dir, f"{city_name}_{period_type}")
            os.makedirs(event_temp_dir, exist_ok=True)
            
            result = process_single_event(
                city_name, period_type, timestamps, lst_collection, 
                event_temp_dir, city_output_dir, event_info, aoi_dir
            )
            
            results[period_type] = result
            
            # Clean up temporary files (mandatory)
            import shutil
            shutil.rmtree(event_temp_dir, ignore_errors=True)
        
        return results
        
    except Exception as e:
        print(f"    Error: {e}")
        return None


def process_all_cities_seviri(eumetsat_creds, output_dir, study_year, temp_dir,
                              aoi_dir, city_list=None, n_workers=2,
                              test_mode=False, test_cities=None):
    """
    Process SEVIRI LST for all cities with DASK parallelization.

    Parameters:
    -----------
    eumetsat_creds : dict
        EUMETSAT credentials
    output_dir : str
        Base output directory (parent of 04_temporal_analysis_daily/)
    study_year : int
        Study year
    temp_dir : str
        Temporary directory (cleared per city after processing)
    aoi_dir : str
        Base AOI directory (Results/01_aoi_delineation/)
    city_list : list, optional
        Cities to process. If None, auto-detected from decision tree JSON.
    n_workers : int, default=2
        Number of DASK workers.
    test_mode : bool, default=False
        If True, run only `test_cities` (or the first city in city_list when
        test_cities is also None). Use this to verify the end-to-end pipeline
        before committing to a full run.
    test_cities : list or None
        Explicit city subset for test mode. Ignored when test_mode=False.

    Returns:
    --------
    dict : {city_name: city_results_dict}
    """
    print("\n" + "=" * 60)
    if test_mode:
        print("SEVIRI LST PROCESSING — TEST MODE")
    else:
        print("MULTI-CITY SEVIRI LST PROCESSING")
    print("=" * 60)
    
    if city_list is None:
        _dt_subfolders = ['04_temporal_analysis_daily', '04_trend_analysis_daily']
        results_file = next(
            (os.path.join(output_dir, s, f'decision_tree_selections_{study_year}.json')
             for s in _dt_subfolders
             if os.path.exists(os.path.join(output_dir, s, f'decision_tree_selections_{study_year}.json'))),
            os.path.join(output_dir, '04_temporal_analysis_daily',
                         f'decision_tree_selections_{study_year}.json')
        )

        if not os.path.exists(results_file):
            print(f"ERROR: Decision tree results not found")
            return None
        
        with open(results_file, 'r') as f:
            all_results = json.load(f)
        
        city_list = [r['city'] for r in all_results]
        print(f"Auto-detected {len(city_list)} cities")

    # ── Test-mode: restrict to a small subset ─────────────────────────────────
    if test_mode:
        if test_cities:
            city_list = [c for c in test_cities if c in city_list] or test_cities[:1]
        else:
            city_list = city_list[:1]   # default: first city only
        print(f"TEST MODE — processing {len(city_list)} city/ies: {city_list}")
    # ──────────────────────────────────────────────────────────────────────────

    print(f"Cities: {', '.join(city_list)}")
    
    # Initialize DASK
    dask_client = None
    try:
        dask_client = Client(n_workers=n_workers, threads_per_worker=2, memory_limit='2GB')
        print(f"DASK client initialized: {n_workers} workers")
    except:
        print("Using DASK synchronous scheduler")
    
    # Process each city
    all_city_results = {}
    successful_cities = []
    failed_cities = []
    skipped_cities = []
    
    for i, city_name in enumerate(city_list, 1):
        print(f"\n{'='*60}")
        print(f"[{i}/{len(city_list)}] Processing: {city_name}")
        print(f"{'='*60}")
        
        try:
            city_results = process_city_seviri_events(
                city_name, eumetsat_creds, output_dir, study_year, 
                temp_dir, aoi_dir
            )
            
            if city_results:
                all_city_results[city_name] = city_results
                
                # Handle cities with no heat events (expected, not a failure)
                if city_results.get('_status') == 'no_events':
                    skipped_cities.append(city_name)
                    print(f"⊘ {city_name}: Skipped — no heat events selected by decision tree")
                    continue
                
                city_status = []
                for period_type, result in city_results.items():
                    if period_type.startswith('_'):
                        continue  # skip internal keys like _status, _reason
                    if isinstance(result, dict) and result:
                        city_status.append(result.get('status', 'unknown'))
                
                if 'skipped' in city_status:
                    skipped_cities.append(city_name)
                    print(f"✓ {city_name}: Some files skipped (already exist)")
                elif 'success' in city_status:
                    successful_cities.append(city_name)
                    print(f"✓ {city_name}: Successfully processed")
                else:
                    failed_cities.append(city_name)
                    print(f"✗ {city_name}: Processing issues")
            else:
                failed_cities.append(city_name)
                print(f"✗ {city_name}: Failed")
                
        except Exception as e:
            print(f"✗ {city_name}: Exception - {e}")
            failed_cities.append(city_name)
            all_city_results[city_name] = {'status': 'error', 'error': str(e)}
            continue
    
    # Close DASK
    if dask_client:
        dask_client.close()
    
    # Summary
    print("\n" + "=" * 60)
    print("PROCESSING SUMMARY")
    print("=" * 60)
    print(f"Total cities: {len(city_list)}")
    print(f"Successful: {len(successful_cities)}")
    print(f"Skipped (already processed): {len(skipped_cities)}")
    print(f"Failed: {len(failed_cities)}")
    
    if successful_cities:
        print(f"\n✓ Successful cities:")
        for city in successful_cities:
            print(f"  - {city}")
    
    if skipped_cities:
        print(f"\n⊘ Skipped cities (files exist):")
        for city in skipped_cities:
            print(f"  - {city}")
    
    if failed_cities:
        print(f"\n✗ Failed cities:")
        for city in failed_cities:
            print(f"  - {city}")
    
    # Save summary — resolve subfolder the same way process_city_seviri_events() does
    _sum_subfolders = ['04_temporal_analysis_daily', '04_trend_analysis_daily']
    _sum_nb04 = next(
        (s for s in _sum_subfolders if os.path.isdir(os.path.join(output_dir, s))),
        '04_temporal_analysis_daily'
    )
    seviri_output_dir = os.path.join(output_dir, _sum_nb04, 'seviri')
    os.makedirs(seviri_output_dir, exist_ok=True)
    summary_path = os.path.join(seviri_output_dir, f'processing_summary_{study_year}.json')
    summary = {
        'processing_date': datetime.now().isoformat(),
        'total_cities': len(city_list),
        'successful': successful_cities,
        'skipped': skipped_cities,
        'failed': failed_cities,
        'results': all_city_results
    }
    
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    
    print(f"\nProcessing summary saved: {os.path.basename(summary_path)}")
    
    return summary
