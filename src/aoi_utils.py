"""
AOI (Area of Interest) Processing Utilities
===========================================

Core functions for AOI delineation and urban polygon analysis.
Extracted from 01_AOI_delineation.ipynb for reusability and testing.
"""

import pandas as pd
import geopandas as gpd
import numpy as np
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union
from pathlib import Path
from typing import Tuple, Optional, Dict, Any, List
import warnings
import glob
import os
from datetime import datetime

# Import project configuration
try:
    import config
except ImportError:
    # Fallback if config not available
    class Config:
        WGS84 = "EPSG:4326"
        WEB_MERCATOR = "EPSG:3857"
        AOI_BUFFER_DISTANCE = 2000
        ADJACENT_POLYGON_BUFFER = 1000
    config = Config()

warnings.filterwarnings('ignore')


def load_aoi_datasets(cities_csv_path: str, urban_geojson_path: str, 
                     boundary_geojson_path: str) -> Tuple[pd.DataFrame, gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """
    Load all required datasets for AOI processing.
    
    Supports both the legacy CSV (Major_cities_population_Nigeria.csv) and
    the WUP 2025 CSV (Major_cities_population_Nigeria_WUP_2025.csv).
    Column names are normalised so downstream code always sees:
      - 'Urban Agglomeration'  (city name)
      - 'Latitude' / 'Longitude'
      - Year columns as strings, e.g. '1975' … '2050'
    
    Args:
        cities_csv_path: Path to cities population file (CSV or XLSX)
        urban_geojson_path: Path to urban landscape typology GeoJSON
        boundary_geojson_path: Path to country boundary GeoJSON
        
    Returns:
        Tuple of (cities_df, urban_gdf, boundary_gdf)
        
    Raises:
        FileNotFoundError: If any required file is missing
        ValueError: If data has unexpected structure
    """
    print("Loading AOI datasets...")
    
    # Load cities data — detect format by extension
    cities_path = Path(cities_csv_path)
    if not cities_path.exists():
        raise FileNotFoundError(f"Cities file not found: {cities_csv_path}")
    
    if cities_path.suffix.lower() in ('.xlsx', '.xls'):
        cities_df = pd.read_excel(cities_csv_path, sheet_name='Data')
    else:
        cities_df = pd.read_csv(cities_csv_path, thousands=',')
    
    # Rename WUP 2025 columns to legacy schema if present
    if 'City_Name' in cities_df.columns:
        rename_map = {
            'City_Name': 'Urban Agglomeration',
            'PWCent_Latitude': 'Latitude',
            'PWCent_Longitude': 'Longitude',
        }
        cities_df = cities_df.rename(columns=rename_map)
        cities_df['Urban Agglomeration'] = cities_df['Urban Agglomeration'].str.strip()
    
    # Ensure year columns are strings
    cities_df.columns = [
        str(c) if isinstance(c, (int, float)) else c
        for c in cities_df.columns
    ]
    
    # Remove non-city entries (e.g., state-level entries like "Abia State")
    state_mask = cities_df['Urban Agglomeration'].str.contains(r'\bState\b', case=False, na=False)
    if state_mask.any():
        removed = cities_df.loc[state_mask, 'Urban Agglomeration'].tolist()
        cities_df = cities_df[~state_mask].reset_index(drop=True)
        print(f"🗑️ Removed {len(removed)} non-city entries: {', '.join(removed)}")

    print(f"✅ Loaded {len(cities_df)} cities from {cities_path.name}")
    
    # Validate cities data structure
    required_columns = ['Urban Agglomeration', 'Latitude', 'Longitude', '2024']
    missing_cols = [col for col in required_columns if col not in cities_df.columns]
    if missing_cols:
        raise ValueError(f"Cities CSV missing required columns: {missing_cols}")
    
    # Load urban polygons
    if not Path(urban_geojson_path).exists():
        raise FileNotFoundError(f"Urban GeoJSON not found: {urban_geojson_path}")
    
    urban_gdf = gpd.read_file(urban_geojson_path)
    print(f"✅ Loaded {len(urban_gdf)} urban polygons (CRS: {urban_gdf.crs})")
    
    # Load boundary
    if not Path(boundary_geojson_path).exists():
        raise FileNotFoundError(f"Boundary GeoJSON not found: {boundary_geojson_path}")
    
    boundary_gdf = gpd.read_file(boundary_geojson_path)
    print(f"✅ Loaded boundary (CRS: {boundary_gdf.crs})")
    
    # Ensure consistent CRS
    if boundary_gdf.crs != urban_gdf.crs:
        boundary_gdf = boundary_gdf.to_crs(urban_gdf.crs)
        print(f"🔄 Reprojected boundary to {urban_gdf.crs}")
    
    return cities_df, urban_gdf, boundary_gdf


def create_city_point(city_info: pd.Series, target_crs: str) -> gpd.GeoDataFrame:
    """
    Create point geometry from city coordinates.
    
    Args:
        city_info: Series containing city data with Latitude/Longitude
        target_crs: Target CRS for the output
        
    Returns:
        GeoDataFrame with city point geometry
    """
    city_point = Point(city_info['Longitude'], city_info['Latitude'])
    city_gdf = gpd.GeoDataFrame([city_info], geometry=[city_point], crs=config.WGS84)
    
    if target_crs != config.WGS84:
        city_gdf = city_gdf.to_crs(target_crs)
    
    return city_gdf


def find_main_urban_polygon(city_gdf: gpd.GeoDataFrame, 
                           urban_gdf: gpd.GeoDataFrame) -> Tuple[gpd.GeoDataFrame, float]:
    """
    Find the main urban polygon containing the city point.
    
    Args:
        city_gdf: GeoDataFrame with city point
        urban_gdf: GeoDataFrame with urban polygons
        
    Returns:
        Tuple of (main_polygon_gdf, area_km2)
    """
    city_point = city_gdf.geometry.iloc[0]
    
    # Find polygon containing the city point
    for idx, polygon in urban_gdf.iterrows():
        if polygon.geometry.contains(city_point):
            main_polygon_gdf = gpd.GeoDataFrame([polygon], crs=urban_gdf.crs)
            area_km2 = polygon.geometry.area / 1_000_000
            print(f"✅ Found main urban polygon (Area: {area_km2:.2f} km²)")
            return main_polygon_gdf, area_km2
    
    # Fallback: create buffer around city point
    print("⚠️ No urban polygon found containing city point, creating 5km buffer")
    buffer_geom = city_point.buffer(5000)  # 5km buffer
    main_polygon_gdf = gpd.GeoDataFrame([{'OBJECTID': 0}], 
                                       geometry=[buffer_geom], crs=urban_gdf.crs)
    area_km2 = buffer_geom.area / 1_000_000
    return main_polygon_gdf, area_km2


def find_adjacent_polygons(main_polygon_gdf: gpd.GeoDataFrame, 
                          urban_gdf: gpd.GeoDataFrame,
                          buffer_distance: int = None) -> Tuple[gpd.GeoDataFrame, float]:
    """
    Find adjacent urban polygons within buffer distance of main polygon.
    
    Args:
        main_polygon_gdf: GeoDataFrame with main urban polygon
        urban_gdf: GeoDataFrame with all urban polygons
        buffer_distance: Buffer distance in meters (default from config)
        
    Returns:
        Tuple of (adjacent_gdf, total_adjacent_area_km2)
    """
    if buffer_distance is None:
        buffer_distance = config.ADJACENT_POLYGON_BUFFER
    
    main_buffer = main_polygon_gdf.geometry.iloc[0].buffer(buffer_distance)
    adjacent_polygons = []
    main_polygon_id = main_polygon_gdf.index[0]
    
    for idx, polygon in urban_gdf.iterrows():
        if idx != main_polygon_id and polygon.geometry.intersects(main_buffer):
            adjacent_polygons.append(polygon)
    
    print(f"📍 Found {len(adjacent_polygons)} adjacent polygons within {buffer_distance/1000}km")
    
    if adjacent_polygons:
        adjacent_gdf = gpd.GeoDataFrame(adjacent_polygons, crs=urban_gdf.crs)
        total_adjacent_area = adjacent_gdf.geometry.area.sum() / 1_000_000
        return adjacent_gdf, total_adjacent_area
    else:
        return gpd.GeoDataFrame(columns=urban_gdf.columns, crs=urban_gdf.crs), 0


def create_aoi_buffer(combined_polygons_gdf: gpd.GeoDataFrame,
                     buffer_distance: int = None) -> Tuple[gpd.GeoDataFrame, float]:
    """
    Create buffer around combined urban polygons.
    
    Args:
        combined_polygons_gdf: GeoDataFrame with all urban polygons
        buffer_distance: Buffer distance in meters (default from config)
        
    Returns:
        Tuple of (buffer_gdf, buffer_area_km2)
    """
    if buffer_distance is None:
        buffer_distance = config.AOI_BUFFER_DISTANCE
    
    # Combine all polygon geometries
    combined_geometry = unary_union(combined_polygons_gdf.geometry)
    
    # Create buffer
    buffer_geometry = combined_geometry.buffer(buffer_distance)
    buffer_gdf = gpd.GeoDataFrame([{'buffer_distance': buffer_distance}],
                                 geometry=[buffer_geometry],
                                 crs=combined_polygons_gdf.crs)
    
    buffer_area_km2 = buffer_geometry.area / 1_000_000
    print(f"✅ Created {buffer_distance/1000}km buffer (Area: {buffer_area_km2:.2f} km²)")
    
    return buffer_gdf, buffer_area_km2


def create_aoi_boundary(buffer_geometry, city_name: str) -> Tuple[gpd.GeoDataFrame, float]:
    """
    Create AOI boundary (bounding box) from buffer geometry.
    
    Args:
        buffer_geometry: Shapely geometry of buffer zone
        city_name: Name of the city
        
    Returns:
        Tuple of (aoi_gdf, aoi_area_km2)
    """
    bounds = buffer_geometry.bounds
    aoi_boundary = box(bounds[0], bounds[1], bounds[2], bounds[3])
    
    aoi_gdf = gpd.GeoDataFrame([{
        'city': city_name,
        'method': 'buffer_bbox',
        'bounds_minx': bounds[0],
        'bounds_miny': bounds[1], 
        'bounds_maxx': bounds[2],
        'bounds_maxy': bounds[3]
    }], geometry=[aoi_boundary], crs=buffer_geometry.crs if hasattr(buffer_geometry, 'crs') else config.WEB_MERCATOR)
    
    aoi_area_km2 = aoi_boundary.area / 1_000_000
    
    # Calculate dimensions
    width_km = (bounds[2] - bounds[0]) / 1000
    height_km = (bounds[3] - bounds[1]) / 1000
    
    print(f"✅ Created AOI boundary (Area: {aoi_area_km2:.2f} km²)")
    print(f"📏 AOI dimensions: {width_km:.2f} km × {height_km:.2f} km")
    
    return aoi_gdf, aoi_area_km2


def clip_aoi_to_land(aoi_gdf: gpd.GeoDataFrame, boundary_gdf: gpd.GeoDataFrame,
                     city_name: str) -> Tuple[gpd.GeoDataFrame, float]:
    """
    Clip AOI geometry to country boundary to remove ocean/water areas.
    
    This is essential for coastal cities (e.g., Lagos) where the bounding box
    extends over the ocean. ERA5-Land and other land-only datasets have masked
    pixels over water, causing all-NaN extractions if the geometry includes
    significant ocean coverage.
    
    Args:
        aoi_gdf: GeoDataFrame with AOI boundary (bounding box)
        boundary_gdf: GeoDataFrame with country boundary polygon
        city_name: Name of the city (for logging)
        
    Returns:
        Tuple of (clipped_gdf, clipped_area_km2)
    """
    try:
        aoi_geom = aoi_gdf.geometry.iloc[0]
        land_geom = boundary_gdf.geometry.unary_union
        
        # Ensure same CRS
        if aoi_gdf.crs != boundary_gdf.crs:
            boundary_reproj = boundary_gdf.to_crs(aoi_gdf.crs)
            land_geom = boundary_reproj.geometry.unary_union
        
        clipped_geom = aoi_geom.intersection(land_geom)
        
        if clipped_geom.is_empty:
            print(f"  ⚠️ Warning: Clipping resulted in empty geometry for {city_name}, keeping original AOI")
            original_area = aoi_geom.area / 1_000_000
            return aoi_gdf, original_area
        
        # Calculate area change
        original_area = aoi_geom.area / 1_000_000
        clipped_area = clipped_geom.area / 1_000_000
        reduction = original_area - clipped_area
        
        if reduction > 0.01:  # Meaningful reduction threshold (0.01 km²)
            # Replace geometry in the GeoDataFrame (preserve all columns)
            clipped_gdf = aoi_gdf.copy()
            clipped_gdf.geometry = gpd.GeoSeries([clipped_geom], crs=aoi_gdf.crs)
            
            pct = (reduction / original_area) * 100
            print(f"  ✂️ Clipped AOI to land boundary: {original_area:.2f} km² → {clipped_area:.2f} km² "
                  f"(removed {reduction:.2f} km² ocean/water, {pct:.1f}%)")
            
            return clipped_gdf, clipped_area
        else:
            print(f"  ✅ AOI is fully within land boundary (no clipping needed)")
            return aoi_gdf, original_area
        
    except Exception as e:
        print(f"  ⚠️ Warning: AOI clipping failed for {city_name}: {e}")
        original_area = aoi_gdf.geometry.area.sum() / 1_000_000
        return aoi_gdf, original_area


def find_cities_in_aoi(cities_df: pd.DataFrame, aoi_boundary,
                      target_crs: str,
                      filter_year: str = None) -> Tuple[pd.DataFrame, gpd.GeoDataFrame]:
    """
    Find all cities within the AOI boundary.
    
    Args:
        cities_df: DataFrame with all cities data
        aoi_boundary: Shapely geometry of AOI boundary
        target_crs: CRS of the AOI boundary
        filter_year: If provided, drop cities with NaN population for this year column
        
    Returns:
        Tuple of (cities_in_aoi_df, cities_in_aoi_gdf)
    """
    cities_in_aoi = []
    
    for idx, city_row in cities_df.iterrows():
        city_point = Point(city_row['Longitude'], city_row['Latitude'])
        city_gdf_temp = gpd.GeoDataFrame([city_row], geometry=[city_point], crs=config.WGS84)
        city_gdf_temp = city_gdf_temp.to_crs(target_crs)
        
        if aoi_boundary.contains(city_gdf_temp.geometry.iloc[0]):
            cities_in_aoi.append(city_row)
    
    print(f"🏙️ Found {len(cities_in_aoi)} cities within AOI")
    
    if cities_in_aoi:
        cities_in_aoi_df = pd.DataFrame(cities_in_aoi)
        
        # Filter out cities with no population for the study year
        if filter_year and filter_year in cities_in_aoi_df.columns:
            before_count = len(cities_in_aoi_df)
            cities_in_aoi_df = cities_in_aoi_df.dropna(subset=[filter_year]).reset_index(drop=True)
            dropped = before_count - len(cities_in_aoi_df)
            if dropped:
                print(f"  🔍 Filtered {dropped} cities with no {filter_year} population data")
        
        # Create GeoDataFrame
        geometries = [Point(row['Longitude'], row['Latitude']) for _, row in cities_in_aoi_df.iterrows()]
        cities_in_aoi_gdf = gpd.GeoDataFrame(cities_in_aoi_df, geometry=geometries, crs=config.WGS84)
        cities_in_aoi_gdf = cities_in_aoi_gdf.to_crs(target_crs)
        
        return cities_in_aoi_df, cities_in_aoi_gdf
    else:
        return pd.DataFrame(), gpd.GeoDataFrame(columns=cities_df.columns, crs=target_crs)


def calculate_population_statistics(cities_in_aoi_df: pd.DataFrame) -> Dict[str, Any]:
    """
    Calculate population statistics and growth rates for cities in AOI.
    
    Dynamically determines the earliest and latest available year columns
    so the function works with both the legacy 1950–2035 CSV and the new
    1975–2050 WUP 2025 CSV dataset.
    
    Args:
        cities_in_aoi_df: DataFrame with cities population data
        
    Returns:
        Dictionary with population statistics
    """
    if cities_in_aoi_df.empty:
        return {
            'total_pop_2024': 0,
            'growth_rate_pre': 0,
            'growth_rate_post': 0,
            'growth_rate_total': 0
        }
    
    # Determine available year columns
    year_cols = sorted([c for c in cities_in_aoi_df.columns if c.isdigit()])
    first_year = int(year_cols[0]) if year_cols else 1975
    last_year = int(year_cols[-1]) if year_cols else 2050
    
    pop_first = cities_in_aoi_df[str(first_year)].sum() if str(first_year) in cities_in_aoi_df.columns else 0
    pop_2024 = cities_in_aoi_df['2024'].sum() if '2024' in cities_in_aoi_df.columns else 0
    pop_last = cities_in_aoi_df[str(last_year)].sum() if str(last_year) in cities_in_aoi_df.columns else 0
    
    # Pre-2024 growth rate
    years_pre = 2024 - first_year
    growth_rate_pre = ((pop_2024 / pop_first) ** (1/years_pre) - 1) * 100 if pop_first > 0 and years_pre > 0 else 0
    
    # Post-2024 growth rate
    years_post = last_year - 2024
    growth_rate_post = ((pop_last / pop_2024) ** (1/years_post) - 1) * 100 if pop_2024 > 0 and years_post > 0 else 0
    
    # Overall growth rate
    years_total = last_year - first_year
    growth_rate_total = ((pop_last / pop_first) ** (1/years_total) - 1) * 100 if pop_first > 0 and years_total > 0 else 0
    
    return {
        'total_pop_2024': pop_2024,
        'total_pop_first': pop_first,
        'total_pop_last': pop_last,
        'first_year': first_year,
        'last_year': last_year,
        # Legacy keys for backward compatibility
        'total_pop_1950': pop_first,
        'total_pop_2035': pop_last,
        'growth_rate_pre': growth_rate_pre,
        'growth_rate_post': growth_rate_post,
        'growth_rate_total': growth_rate_total
    }


def build_comprehensive_aoi_stats(selected_city: str, cities_in_aoi_df: pd.DataFrame,
                                 aoi_area_km2: float, buffer_area_km2: float,
                                 main_polygon_area_km2: float, adjacent_area_km2: float,
                                 adjacent_count: int, coverage_efficiency: float,
                                 buffer_distance_km: float) -> Dict[str, Any]:
    """
    Build comprehensive AOI statistics database.
    
    Args:
        selected_city: Name of the target city
        cities_in_aoi_df: DataFrame with cities in AOI
        aoi_area_km2: AOI area in square kilometers
        buffer_area_km2: Buffer area in square kilometers
        main_polygon_area_km2: Main polygon area in square kilometers
        adjacent_area_km2: Adjacent polygons area in square kilometers
        adjacent_count: Number of adjacent polygons
        coverage_efficiency: Coverage efficiency percentage
        buffer_distance_km: Buffer distance in kilometers
        
    Returns:
        Dictionary with comprehensive AOI statistics
    """
    # Get population statistics
    pop_stats = calculate_population_statistics(cities_in_aoi_df)
    
    # Build major cities list
    aoi_major_cities = cities_in_aoi_df['Urban Agglomeration'].tolist() if not cities_in_aoi_df.empty else []
    
    # Calculate population density
    pop_density = (pop_stats['total_pop_2024'] * 1000 / aoi_area_km2) if aoi_area_km2 > 0 else 0
    
    # Base statistics
    stats = {
        # Basic AOI Information
        'AOI': selected_city,
        'AOI_Major_Cities': ', '.join(aoi_major_cities),
        'processing_date': datetime.now().isoformat(),
        'method': f'buffer_bbox_{int(buffer_distance_km)}km',
        
        # Area Statistics
        'aoi_area_km2': aoi_area_km2,
        'buffer_area_km2': buffer_area_km2,
        'main_polygon_area_km2': main_polygon_area_km2,
        'adjacent_polygons_area_km2': adjacent_area_km2,
        'total_urban_polygons_area_km2': main_polygon_area_km2 + adjacent_area_km2,
        
        # Count Statistics
        'adjacent_polygons_count': adjacent_count,
        'cities_in_aoi_count': len(cities_in_aoi_df),
        
        # Population Statistics
        'total_population_2024': pop_stats['total_pop_2024'],
        'population_density_per_km2': pop_density,
        
        # Growth Rate Statistics
        'growth_rate_pre_2024_percent': pop_stats['growth_rate_pre'],
        'growth_rate_post_2024_percent': pop_stats['growth_rate_post'],
        'growth_rate_overall_percent': pop_stats['growth_rate_total'],
        
        # Efficiency Metrics
        'coverage_efficiency_percent': coverage_efficiency,
        'buffer_distance_km': buffer_distance_km
    }
    
    # Add population time series data
    if not cities_in_aoi_df.empty:
        year_cols = sorted([c for c in cities_in_aoi_df.columns if c.isdigit()])
        for year in year_cols:
            stats[f'total_population_{year}'] = cities_in_aoi_df[year].sum()
    
    # Add individual city data
    if not cities_in_aoi_df.empty:
        for i, (_, city) in enumerate(cities_in_aoi_df.iterrows()):
            city_name = city['Urban Agglomeration'].replace(' ', '_').replace('-', '_')
            stats[f'{city_name}_lat'] = city['Latitude']
            stats[f'{city_name}_lon'] = city['Longitude']
            stats[f'{city_name}_pop_2024'] = city['2024']
    
    return stats


def update_master_database(output_base_dir: str, 
                          master_db_paths: Dict[str, str]) -> Dict[str, Any]:
    """
    Update master AOI database by scanning for new AOI boundary files.
    
    Args:
        output_base_dir: Base output directory to scan
        master_db_paths: Dictionary with paths for different database formats
        
    Returns:
        Dictionary with update summary statistics
    """
    print("🔍 Scanning for AOI Boundary files to update master database...")
    
    # Find all AOI Boundary files
    search_pattern = os.path.join(output_base_dir, '**', '*_AOI_Boundary.geojson')
    aoi_files = glob.glob(search_pattern, recursive=True)
    
    if not aoi_files:
        # Alternative search method
        aoi_files = []
        for root, dirs, files in os.walk(output_base_dir):
            for file in files:
                if file.endswith('_AOI_Boundary.geojson'):
                    aoi_files.append(os.path.join(root, file))
    
    print(f"📁 Found {len(aoi_files)} AOI Boundary files")
    
    if not aoi_files:
        return {'status': 'no_files', 'message': 'No AOI files found'}
    
    # Load existing master database
    existing_cities = set()
    master_gdf = None
    
    wgs84_path = master_db_paths.get('wgs84_path')
    if wgs84_path and os.path.exists(wgs84_path):
        try:
            master_gdf = gpd.read_file(wgs84_path)
            if 'AOI' in master_gdf.columns:
                existing_cities = set(master_gdf['AOI'].tolist())
                print(f"📊 Existing database: {len(existing_cities)} cities")
        except Exception as e:
            print(f"⚠️ Error reading existing database: {e}")
            master_gdf = None
    
    # Process new files
    new_gdfs = []
    new_cities = []
    skipped_cities = []
    
    for file_path in aoi_files:
        try:
            filename = os.path.basename(file_path)
            city_name = filename.replace('_AOI_Boundary.geojson', '')
            
            if city_name in existing_cities:
                skipped_cities.append(city_name)
                continue
            
            gdf = gpd.read_file(file_path)
            if gdf.empty:
                continue
            
            # Ensure consistent structure
            if 'AOI' not in gdf.columns:
                gdf['AOI'] = city_name
            
            gdf['source_file'] = filename
            gdf['date_added'] = pd.Timestamp.now().strftime('%Y-%m-%d')
            gdf['last_updated'] = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Ensure WGS84
            if not gdf.crs or gdf.crs.to_string() != config.WGS84:
                gdf = gdf.to_crs(config.WGS84)
            
            # Calculate area if missing
            if 'aoi_area_km2' not in gdf.columns:
                gdf_3857 = gdf.to_crs(config.WEB_MERCATOR)
                gdf['aoi_area_km2'] = gdf_3857.area / 1e6
            
            new_gdfs.append(gdf)
            new_cities.append(city_name)
            print(f"   ✅ Added {city_name}")
            
        except Exception as e:
            print(f"   ❌ Failed to load {os.path.basename(file_path)}: {e}")
    
    # Combine and save
    if new_gdfs or master_gdf is not None:
        all_gdfs = []
        if master_gdf is not None:
            all_gdfs.append(master_gdf)
        all_gdfs.extend(new_gdfs)
        
        if all_gdfs:
            combined_gdf = pd.concat(all_gdfs, ignore_index=True, sort=False)
            combined_gdf = combined_gdf.drop_duplicates(subset=['AOI'], keep='last')
            
            # Save databases
            combined_gdf.to_file(master_db_paths['wgs84_path'], driver='GeoJSON')
            
            if 'web_mercator_path' in master_db_paths:
                combined_gdf_3857 = combined_gdf.to_crs(config.WEB_MERCATOR)
                combined_gdf_3857.to_file(master_db_paths['web_mercator_path'], driver='GeoJSON')
            
            if 'stats_csv_path' in master_db_paths:
                stats_columns = [col for col in combined_gdf.columns if col != 'geometry']
                combined_gdf[stats_columns].to_csv(master_db_paths['stats_csv_path'], index=False)
            
            return {
                'status': 'success',
                'total_cities': len(combined_gdf),
                'new_cities': new_cities,
                'skipped_cities': skipped_cities,
                'total_area_km2': combined_gdf['aoi_area_km2'].sum() if 'aoi_area_km2' in combined_gdf.columns else 0
            }
    
    return {'status': 'no_changes', 'message': 'No updates needed'}


def sort_cities_by_population(cities_to_process: List[str],
                              cities_df: pd.DataFrame,
                              year: str = '2024') -> List[str]:
    """
    Sort a list of city names by their population in descending order.

    Args:
        cities_to_process: City names to sort.
        cities_df: DataFrame with 'Urban Agglomeration' and year columns.
        year: Year column to use for sorting (default '2024').

    Returns:
        List of city names sorted by population (largest first).
    """
    pop_lookup = dict(zip(
        cities_df['Urban Agglomeration'],
        pd.to_numeric(cities_df[year], errors='coerce').fillna(0)
    ))
    return sorted(
        cities_to_process,
        key=lambda c: pop_lookup.get(c, 0),
        reverse=True
    )


def process_city_aoi(selected_city: str, cities_df: pd.DataFrame, 
                    urban_gdf: gpd.GeoDataFrame, boundary_gdf: gpd.GeoDataFrame,
                    buffer_distance: int = None) -> Dict[str, Any]:
    """
    Complete AOI processing pipeline for a single city.
    
    Args:
        selected_city: Name of the city to process
        cities_df: DataFrame with all cities data
        urban_gdf: GeoDataFrame with urban polygons
        boundary_gdf: GeoDataFrame with country boundary
        buffer_distance: Buffer distance in meters (optional)
        
    Returns:
        Dictionary containing all processed AOI data and statistics
    """
    print(f"🏙️ Processing AOI for: {selected_city}")
    
    # Get city information
    city_info = cities_df[cities_df['Urban Agglomeration'] == selected_city].iloc[0]
    print(f"📍 Coordinates: {city_info['Latitude']:.4f}, {city_info['Longitude']:.4f}")
    
    # Create city point
    city_gdf = create_city_point(city_info, urban_gdf.crs)
    
    # Find main urban polygon
    main_polygon_gdf, main_area_km2 = find_main_urban_polygon(city_gdf, urban_gdf)
    
    # Find adjacent polygons
    adjacent_gdf, adjacent_area_km2 = find_adjacent_polygons(main_polygon_gdf, urban_gdf, buffer_distance)
    
    # Combine polygons
    all_polygons = [main_polygon_gdf]
    if not adjacent_gdf.empty:
        all_polygons.append(adjacent_gdf)
    combined_polygons_gdf = pd.concat(all_polygons, ignore_index=True)
    
    # Create buffer
    buffer_gdf, buffer_area_km2 = create_aoi_buffer(combined_polygons_gdf, buffer_distance)
    
    # Create AOI boundary
    aoi_gdf, aoi_area_km2 = create_aoi_boundary(buffer_gdf.geometry.iloc[0], selected_city)
    
    # Clip AOI to country boundary (removes ocean areas for coastal cities)
    if boundary_gdf is not None and not boundary_gdf.empty:
        aoi_gdf, aoi_area_km2 = clip_aoi_to_land(aoi_gdf, boundary_gdf, selected_city)
    
    # Find cities in AOI
    cities_in_aoi_df, cities_in_aoi_gdf = find_cities_in_aoi(
        cities_df, aoi_gdf.geometry.iloc[0], urban_gdf.crs,
        filter_year=str(config.PROJECT_STUDY_YEAR))
    
    # Calculate statistics
    coverage_efficiency = (buffer_area_km2 / aoi_area_km2) * 100 if aoi_area_km2 > 0 else 0
    buffer_distance_used = buffer_distance or config.AOI_BUFFER_DISTANCE
    
    comprehensive_stats = build_comprehensive_aoi_stats(
        selected_city, cities_in_aoi_df, aoi_area_km2, buffer_area_km2,
        main_area_km2, adjacent_area_km2, len(adjacent_gdf),
        coverage_efficiency, buffer_distance_used / 1000
    )
    
    print(f"✅ AOI processing complete for {selected_city}")
    print(f"📏 AOI Area: {aoi_area_km2:.2f} km²")
    print(f"🏙️ Cities in AOI: {len(cities_in_aoi_df)}")
    print(f"📊 Coverage Efficiency: {coverage_efficiency:.1f}%")
    
    return {
        'city_info': city_info,
        'city_gdf': city_gdf,
        'main_polygon_gdf': main_polygon_gdf,
        'adjacent_gdf': adjacent_gdf,
        'combined_polygons_gdf': combined_polygons_gdf,
        'buffer_gdf': buffer_gdf,
        'aoi_gdf': aoi_gdf,
        'cities_in_aoi_df': cities_in_aoi_df,
        'cities_in_aoi_gdf': cities_in_aoi_gdf,
        'comprehensive_stats': comprehensive_stats,
        'metrics': {
            'main_area_km2': main_area_km2,
            'adjacent_area_km2': adjacent_area_km2,
            'buffer_area_km2': buffer_area_km2,
            'aoi_area_km2': aoi_area_km2,
            'coverage_efficiency': coverage_efficiency
        }
    }