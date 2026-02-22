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
    Determine temporal resolution based on event duration
    
    Parameters:
    -----------
    duration_days : int
        Duration of the event in days
    
    Returns:
    --------
    tuple : (strategy, interval_minutes)
        Strategy name and temporal interval in minutes
    """
    if duration_days <= 3:
        return "15min", 15
    elif duration_days <= 7:
        return "1hr", 60
    else:
        return "daily", 1440


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
    results_file = os.path.join(output_dir, '04_trend_analysis_daily',
                               f'decision_tree_selections_{study_year}.json')
    
    if not os.path.exists(results_file):
        raise FileNotFoundError(f"Decision tree results not found: {results_file}")
    
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
        if city_result['selected_events'][period_type]:
            event = city_result['selected_events'][period_type]
            period_info = event['period_used']
            
            events[period_type] = {
                'start_date': pd.to_datetime(period_info['start_date']).date(),
                'end_date': pd.to_datetime(period_info['end_date']).date(),
                'duration': period_info['duration'],
                'source': event['source'],
                'quality_flag': city_result['decision_log'][period_type]['quality_flag']
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


def compute_median_lst_native_msg(lst_arrays, output_path, transform=None, city_name=None):
    """
    Compute median LST in native MSG projection with optional water masking
    
    Parameters:
    -----------
    lst_arrays : list
        List of LST numpy arrays
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
        if not lst_arrays:
            print("        No valid LST arrays to process")
            return None
        
        lst_stack = np.stack(lst_arrays, axis=0)
        median_lst = np.nanmedian(lst_stack, axis=0)
        valid_count = np.sum(~np.isnan(lst_stack), axis=0)
        
        height, width = median_lst.shape
        print(f"        Computing median: {width} x {height} pixels from {len(lst_arrays)} arrays")
        
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
        
        # Apply water masking if city name is provided
        if city_name is not None:
            try:
                from data_io import load_osm_water_mask
                
                # Create temporary transform for water mask loading
                try:
                    msg_crs = create_msg_crs()
                except:
                    msg_crs = "+proj=geos +lon_0=0 +h=35785831 +x_0=0 +y_0=0 +ellps=WGS84 +units=m +no_defs"
                
                if transform is None:
                    # MSG SEVIRI full disk extent
                    west_bound = -5568742.4
                    east_bound = 5568742.4
                    south_bound = -5568742.4
                    north_bound = 5568742.4
                    pixel_size_x = (east_bound - west_bound) / width
                    pixel_size_y = (north_bound - south_bound) / height
                    temp_transform = from_bounds(west_bound, south_bound, east_bound, north_bound, width, height)
                else:
                    temp_transform = transform
                
                print(f"        Applying water body masking for {city_name}...")
                water_mask = load_osm_water_mask(city_name, median_lst.shape, temp_transform, msg_crs)
                
                if np.any(water_mask):
                    # Mask water pixels
                    median_lst = np.where(water_mask, np.nan, median_lst)
                    
                    # Update coverage statistics
                    valid_after_masking = np.sum(~np.isnan(median_lst))
                    coverage_after_masking = 100 * valid_after_masking / total_pixels
                    masked_count = valid_after - valid_after_masking
                    print(f"        Coverage after water masking:  {coverage_after_masking:.1f}% ({valid_after_masking:,}/{total_pixels:,} pixels)")
                    
            except ImportError as e:
                print(f"        Warning: Could not load water masking function: {e}")
            except Exception as e:
                print(f"        Warning: Water masking failed: {e}")

        
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


def reproject_to_wgs84_1km(input_path, output_dir, city_name, period_type, aoi_path, date_str):
    """
    Reproject MSG native to match AOI CRS and resample to 1km
    
    Parameters:
    -----------
    input_path : str
        Input GeoTIFF in MSG projection
    output_dir : str
        Output directory
    city_name : str
        City name
    period_type : str
        'day' or 'night'
    aoi_path : str
        Path to AOI GeoJSON
    date_str : str
        Date string for filename
    
    Returns:
    --------
    str or None : Path to reprojected GeoTIFF or None if failed
    """
    try:
        print(f"    Reprojecting to match AOI CRS @ 1km...")
        
        aoi_gdf = gpd.read_file(aoi_path)
        target_crs = aoi_gdf.crs
        
        aoi_bounds = aoi_gdf.total_bounds
        buffer_deg = 50000 / 111320  # 50km buffer
        
        target_bounds = (
            aoi_bounds[0] - buffer_deg,
            aoi_bounds[1] - buffer_deg,
            aoi_bounds[2] + buffer_deg,
            aoi_bounds[3] + buffer_deg
        )
        
        print(f"        AOI CRS: {target_crs}")
        
        with rasterio.open(input_path) as src:
            target_res_deg = 1000 / 111320
            
            width = int((target_bounds[2] - target_bounds[0]) / target_res_deg)
            height = int((target_bounds[3] - target_bounds[1]) / target_res_deg)
            
            dst_transform = from_bounds(
                target_bounds[0], target_bounds[1], 
                target_bounds[2], target_bounds[3],
                width, height
            )
            
            dst_data = np.empty((height, width), dtype=np.float32)
            dst_data.fill(np.nan)
            
            reproject(
                source=rasterio.band(src, 1),
                destination=dst_data,
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=dst_transform,
                dst_crs=target_crs,
                resampling=Resampling.bilinear,
                src_nodata=np.nan,
                dst_nodata=np.nan,
                num_threads=2
            )
            
            valid_pixels = np.sum(~np.isnan(dst_data))
            
            if valid_pixels == 0:
                print(f"        WARNING: No valid data after reprojection!")
                return None
            
            output_filename = f"{city_name}_SEVIRI_{period_type}_{date_str}_median_WGS84_1km.tif"
            output_path = os.path.join(output_dir, output_filename)
            
            profile = {
                'driver': 'GTiff',
                'dtype': 'float32',
                'nodata': np.nan,
                'width': width,
                'height': height,
                'count': 1,
                'crs': target_crs,
                'transform': dst_transform,
                'compress': 'deflate',
                'tiled': True,
                'blockxsize': 256,
                'blockysize': 256
            }
            
            with rasterio.open(output_path, 'w', **profile) as dst:
                dst.write(dst_data, 1)
                dst.update_tags(
                    PRODUCT='SEVIRI_LST_Median_Reprojected',
                    UNITS='Degrees_Celsius',
                    SPATIAL_RESOLUTION='1km',
                    ORIGINAL_RESOLUTION='3km_MSG',
                    TARGET_CRS=str(target_crs),
                    RESAMPLING='bilinear',
                    AOI_FILE=os.path.basename(aoi_path)
                )
            
            print(f"        Reprojection complete: {valid_pixels:,} valid pixels")
            
            # RE-APPLY water masking after reprojection (critical fix)
            # Reprojection can interpolate across water pixels, so re-mask them
            if city_name is not None:
                try:
                    from data_io import load_osm_water_mask
                    
                    print(f"        Re-applying water body masking after reprojection...")
                    
                    # Load the reprojected file
                    with rasterio.open(output_path, 'r+') as src:
                        data = src.read(1)
                        
                        # Create water mask in WGS84 projection
                        water_mask = load_osm_water_mask(
                            city_name, data.shape, src.transform, src.crs
                        )
                        
                        if np.any(water_mask):
                            # Mask water pixels
                            data_masked = np.where(water_mask, np.nan, data)
                            
                            # Write back
                            src.write(data_masked, 1)
                            
                            # Update statistics
                            valid_before = np.sum(~np.isnan(data))
                            valid_after = np.sum(~np.isnan(data_masked))
                            masked_count = valid_before - valid_after
                            
                            print(f"        Re-masked {masked_count:,} water pixels")
                            print(f"        Final valid pixels: {valid_after:,}")
                            
                except Exception as e:
                    print(f"        Warning: Post-reprojection water masking failed: {e}")
            
            return output_path
            
    except Exception as e:
        print(f"        Error in reprojection: {e}")
        import traceback
        traceback.print_exc()
        return None


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
        
        city_aoi_path = os.path.join(aoi_dir, f'City_{city_name}', 'Features',
                                     f'{city_name}_AOI_Boundary.geojson')
        
        if not os.path.exists(city_aoi_path):
            print(f"        AOI file not found")
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
            
            clipped_filename = f"{city_name}_SEVIRI_{period_type}_{date_str}_median_WGS84_1km_clipped.tif"
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
        reprojected_filename = f"{city_name}_SEVIRI_{period_type}_{date_str}_median_WGS84_1km.tif"
        clipped_filename = f"{city_name}_SEVIRI_{period_type}_{date_str}_median_WGS84_1km_clipped.tif"
        
        native_path = os.path.join(output_dir, native_filename)
        reprojected_path_expected = os.path.join(output_dir, reprojected_filename)
        clipped_path_expected = os.path.join(output_dir, clipped_filename)
        
        # SKIP LOGIC: Check if final file exists
        if os.path.exists(clipped_path_expected):
            print(f"        SKIP: Clipped file already exists")
            metadata_path = native_path.replace('.tif', '_metadata.json')
            if os.path.exists(metadata_path):
                with open(metadata_path, 'r') as f:
                    metadata = json.load(f)
                return {
                    'status': 'skipped',
                    'native_path': native_path,
                    'reprojected_path': reprojected_path_expected,
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
            lst_arrays = []
            
            for zip_file in valid_files:
                lst_result = extract_and_subset_seviri_native(zip_file)
                if lst_result is not None:
                    lst_data, file_transform = lst_result
                    lst_arrays.append(lst_data)
            
            print(f"        Valid LST arrays: {len(lst_arrays)}")
            
            if not lst_arrays:
                return None
            
            # Create transform
            height, width = lst_arrays[0].shape
            correct_transform = from_bounds(
                -5568742.4, -5568742.4, 5568742.4, 5568742.4,
                width, height
            )
            
            result_path = compute_median_lst_native_msg(lst_arrays, native_path, correct_transform, city_name)
            
            if not result_path:
                return None
        
        # Get AOI path
        aoi_path = os.path.join(aoi_dir, f'City_{city_name}', 'Features',
                               f'{city_name}_AOI_Boundary.geojson')
        
        if not os.path.exists(aoi_path):
            print(f"        WARNING: AOI not found")
            return {'status': 'partial', 'native_path': result_path}
        
        # SKIP LOGIC: Check if reprojected file exists
        if os.path.exists(reprojected_path_expected):
            print(f"        SKIP: Using existing reprojected file")
            reprojected_path = reprojected_path_expected
        else:
            reprojected_path = reproject_to_wgs84_1km(result_path, output_dir, 
                                                      city_name, period_type, 
                                                      aoi_path, date_str)
            if not reprojected_path:
                return None
        
        # Clip to AOI
        clipped_path = clip_seviri_to_city_aoi(reprojected_path, city_name, 
                                               output_dir, date_str, period_type, aoi_dir)
        
        # Metadata
        metadata = {
            'city': city_name,
            'period_type': period_type,
            'event_start_date': str(start_date),
            'event_end_date': str(end_date),
            'event_duration_days': event_info['duration'],
            'processing_date': datetime.now().isoformat(),
            'native_file': native_filename,
            'reprojected_file': reprojected_filename,
            'clipped_file': clipped_filename
        }
        
        metadata_path = native_path.replace('.tif', '_metadata.json')
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2, default=str)
        
        return {
            'status': 'success',
            'native_path': result_path,
            'reprojected_path': reprojected_path,
            'clipped_path': clipped_path,
            'metadata': metadata
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
        
        city_output_dir = os.path.join(output_dir, '04_trend_analysis_daily', 
                                      'SEVIRI_LST', f'City_{city_name}')
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
                              aoi_dir, city_list=None, n_workers=2):
    """
    Process SEVIRI LST for all cities with DASK parallelization
    
    Parameters:
    -----------
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
    city_list : list, optional
        List of cities to process (default: auto-detect from decision tree)
    n_workers : int, default=2
        Number of DASK workers
    
    Returns:
    --------
    dict : Complete processing summary for all cities
    """
    print("\n" + "=" * 60)
    print("MULTI-CITY SEVIRI LST PROCESSING")
    print("=" * 60)
    
    if city_list is None:
        results_file = os.path.join(output_dir, '04_trend_analysis_daily',
                                   f'decision_tree_selections_{study_year}.json')
        
        if not os.path.exists(results_file):
            print(f"ERROR: Decision tree results not found")
            return None
        
        with open(results_file, 'r') as f:
            all_results = json.load(f)
        
        city_list = [r['city'] for r in all_results]
        print(f"Auto-detected {len(city_list)} cities")
    
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
    
    # Save summary
    seviri_output_dir = os.path.join(output_dir, '04_trend_analysis_daily', 'SEVIRI_LST')
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
