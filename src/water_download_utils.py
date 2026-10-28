"""
JRC Water Download Utilities
=============================

Robust helpers for downloading JRC Global Surface Water data from Google Earth Engine
with tiling, geometry simplification, and retry logic to handle the "5000 elements" error.

Functions:
  - download_jrc_water_robust()  — Main entry point with tiling and retry logic
"""

import time
import ee
import pandas as pd
import geopandas as gpd
from shapely.geometry import box
from shapely.ops import unary_union
import warnings

warnings.filterwarnings("ignore")


def _simplify_geometry(geom, tolerance_m=1000):
    """
    Simplify a Shapely geometry to reduce vertex count before GEE upload.
    
    Parameters
    ----------
    geom : Shapely geometry
        Geometry to simplify
    tolerance_m : int
        Simplification tolerance in metres
        
    Returns
    -------
    Shapely geometry
        Simplified geometry
    """
    # geometry is in ESRI:102022 (metres), so tolerance is in metres directly
    return geom.simplify(tolerance_m)


def _create_grid_tiles(bounds, tile_size_m=50000):
    """
    Create a grid of non-overlapping tiles covering the given bounds.
    
    Parameters
    ----------
    bounds : tuple
        (minx, miny, maxx, maxy) in metres (for projected CRS like ESRI:102022)
    tile_size_m : int
        Tile edge length in metres (default 50 km)
        
    Yields
    ------
    box
        Shapely box geometry for each tile
    """
    minx, miny, maxx, maxy = bounds
    x = minx
    while x < maxx:
        y = miny
        while y < maxy:
            x_end = min(x + tile_size_m, maxx)
            y_end = min(y + tile_size_m, maxy)
            yield box(x, y, x_end, y_end)
            y = y_end
        x = x_end


def download_jrc_water_robust(
    search_geom,
    search_crs="ESRI:102022",
    occurrence_threshold=50,
    tile_size_m=50000,
    max_retries=3,
    retry_delay=2,
    min_area_m2=900,
    verbose=True
):
    """
    Download JRC Global Surface Water data with robust error handling.
    
    Implements:
      1. **Geometry simplification** — reduce vertex count before GEE upload
      2. **Tiling** — split large areas into manageable chunks
      3. **Retry logic** — handle transient GEE errors with exponential backoff
    
    Parameters
    ----------
    search_geom : Shapely geometry
        Search area in the specified CRS (typically ESRI:102022)
    search_crs : str
        CRS of the search geometry (default: "ESRI:102022")
    occurrence_threshold : int
        JRC occurrence percentage threshold (0-100, default 50)
    tile_size_m : int
        Tile size in metres (default 50 km; smaller = more robust but slower)
    max_retries : int
        Number of retry attempts per tile (default 3)
    retry_delay : int
        Initial delay between retries in seconds (default 2, with exponential backoff)
    min_area_m2 : int
        Minimum polygon area in m² to retain (default 900 = 1 Landsat pixel)
    verbose : bool
        Print status messages (default True)
        
    Returns
    -------
    geopandas.GeoDataFrame or None
        Water polygons in EPSG:4326, or None if all tiles failed
    """
    
    if verbose:
        print(f"    🌊 Water download (robust tiling mode, tile_size={tile_size_m/1000:.0f} km)")
    
    # Step 1: Simplify search geometry to reduce GEE complexity
    search_geom_simp = _simplify_geometry(search_geom, tolerance_m=1000)
    
    if verbose:
        ratio = search_geom_simp.area / search_geom.area if search_geom.area > 0 else 1.0
        print(f"      Simplified geometry (complexity: {ratio:.1%} of original)")
    
    # Step 2: Load JRC Global Surface Water
    try:
        jrc = ee.Image('JRC/GSW1_4/GlobalSurfaceWater')
        water_mask = jrc.select('occurrence').gte(occurrence_threshold)
    except Exception as e:
        if verbose:
            print(f"    ❌ Failed to load JRC dataset: {e}")
        return None
    
    # Step 3: Create tiles from geometry bounds
    bounds = search_geom_simp.bounds  # (minx, miny, maxx, maxy)
    tiles = list(_create_grid_tiles(bounds, tile_size_m=tile_size_m))
    
    if verbose:
        print(f"      Created {len(tiles)} tiles from search area")
    
    # Step 4: Download water for each tile with retry logic
    all_water_gdf = None
    failed_tiles = []
    
    for tile_idx, tile_geom in enumerate(tiles, 1):
        
        # Convert tile to 4326 for GEE
        tile_gdf = gpd.GeoDataFrame(
            [{'geom': tile_geom}],
            geometry='geom',
            crs=search_crs
        ).to_crs("EPSG:4326")
        tile_4326 = tile_gdf.geometry.iloc[0]
        
        # Attempt download with retries
        retry_count = 0
        water_gdf_tile = None
        
        while retry_count < max_retries:
            try:
                # Convert to GEE geometry
                search_ee_geom = ee.Geometry(tile_4326.__geo_interface__)
                
                # Vectorize water mask
                water_vectors = water_mask.updateMask(water_mask).reduceToVectors(
                    geometry=search_ee_geom,
                    scale=30,
                    geometryType='polygon',
                    eightConnected=False,
                    maxPixels=1e9,
                )
                
                # Retrieve features
                feats = water_vectors.getInfo()
                
                if feats and feats.get('features'):
                    # Convert to GeoDataFrame
                    water_gdf_tile = gpd.GeoDataFrame.from_features(
                        feats['features'],
                        crs="EPSG:4326"
                    )
                    
                    # Clip to tile bounds
                    water_gdf_tile = gpd.clip(water_gdf_tile, tile_gdf)
                    
                    # Filter by minimum area (convert to m²)
                    if not water_gdf_tile.empty:
                        water_gdf_tile_m = water_gdf_tile.to_crs(search_crs)
                        water_gdf_tile_m = water_gdf_tile_m[
                            water_gdf_tile_m.geometry.area >= min_area_m2
                        ]
                        water_gdf_tile = water_gdf_tile_m.to_crs("EPSG:4326")
                
                if verbose:
                    n_features = len(water_gdf_tile) if water_gdf_tile is not None and not water_gdf_tile.empty else 0
                    print(f"      Tile {tile_idx}/{len(tiles)}: {n_features} water polygons ✓")
                
                break  # Success, exit retry loop
                
            except Exception as e:
                retry_count += 1
                error_msg = str(e)
                
                if "accumulated over 5000 elements" in error_msg:
                    # Too complex for this tile - reduce tile size won't help, add to failed
                    if verbose:
                        print(f"      Tile {tile_idx}/{len(tiles)}: Too complex (5000+ elements) ⚠️")
                    failed_tiles.append(tile_idx)
                    break
                
                if retry_count < max_retries:
                    delay = retry_delay * (2 ** (retry_count - 1))  # Exponential backoff
                    if verbose:
                        print(f"      Tile {tile_idx}/{len(tiles)}: Retry {retry_count}/{max_retries} "
                              f"(waiting {delay}s)...")
                    time.sleep(delay)
                else:
                    if verbose:
                        print(f"      Tile {tile_idx}/{len(tiles)}: Failed after {max_retries} retries ✗")
                    failed_tiles.append(tile_idx)
        
        # Append tile results to master GeoDataFrame
        if water_gdf_tile is not None and not water_gdf_tile.empty:
            if all_water_gdf is None:
                all_water_gdf = water_gdf_tile.copy()
            else:
                all_water_gdf = gpd.GeoDataFrame(
                    pd.concat([all_water_gdf, water_gdf_tile], ignore_index=True),
                    crs="EPSG:4326"
                )
    
    # Summarize results
    if all_water_gdf is not None and not all_water_gdf.empty:
        all_water_gdf = all_water_gdf.drop_duplicates(subset=['geometry']).reset_index(drop=True)
        if verbose:
            print(f"      ✅ Total: {len(all_water_gdf)} unique water polygons across all tiles")
        return all_water_gdf
    elif failed_tiles:
        if verbose:
            print(f"      ⚠️  Some tiles too complex: {failed_tiles}. "
                  f"Proceeding without water mask for those regions.")
        return None
    else:
        if verbose:
            print(f"      ℹ️  No water bodies found")
        return None


# ============================================================================
# Integration helper for notebook
# ============================================================================

def download_water_for_aoi(
    uc_geom,
    city_slug,
    city_dir,
    analysis_crs="ESRI:102022",
    storage_crs="EPSG:4326",
    use_tiling=True,
):
    """
    Convenience function to download and save JRC water for a city's Urban Core.
    
    Parameters
    ----------
    uc_geom : Shapely geometry
        Urban Core geometry in analysis_crs
    city_slug : str
        City name for file naming
    city_dir : Path
        Output directory for city
    analysis_crs : str
        CRS of input geometry (default ESRI:102022)
    storage_crs : str
        CRS for saving files (default EPSG:4326)
    use_tiling : bool
        Enable tiling for large areas (default True)
        
    Returns
    -------
    tuple
        (water_geom, success_flag)
    """
    import pandas as pd
    from pathlib import Path
    
    water_file = city_dir / f"{city_slug}_water_bodies_4326.geojson"
    
    # Check cache first
    if water_file.exists():
        try:
            water_gdf_cached = gpd.read_file(water_file)
            if not water_gdf_cached.empty:
                water_geom = water_gdf_cached.to_crs(analysis_crs).geometry.unary_union
                return water_geom, True
        except:
            pass
    
    # Download using robust method
    if use_tiling:
        water_gdf = download_jrc_water_robust(
            uc_geom,
            search_crs=analysis_crs,
            tile_size_m=50000,
            verbose=True
        )
    else:
        # Fallback to direct download without tiling
        try:
            search_gdf_4326 = gpd.GeoDataFrame(
                [{'geom': uc_geom}],
                geometry='geom',
                crs=analysis_crs
            ).to_crs(storage_crs)
            search_ee_geom = ee.Geometry(search_gdf_4326.geometry.iloc[0].__geo_interface__)
            
            jrc = ee.Image('JRC/GSW1_4/GlobalSurfaceWater')
            water_mask = jrc.select('occurrence').gte(50)
            water_vectors = water_mask.updateMask(water_mask).reduceToVectors(
                geometry=search_ee_geom,
                scale=30,
                geometryType='polygon',
                eightConnected=False,
                maxPixels=1e9,
            )
            feats = water_vectors.getInfo()
            if feats.get('features'):
                water_gdf = gpd.GeoDataFrame.from_features(
                    feats['features'],
                    crs=storage_crs
                )
            else:
                water_gdf = None
        except Exception as e:
            print(f"    ⚠️  Direct download failed: {e}")
            water_gdf = None
    
    # Save results
    if water_gdf is not None and not water_gdf.empty:
        water_gdf.to_crs(storage_crs).to_file(water_file, driver='GeoJSON')
        water_geom = water_gdf.to_crs(analysis_crs).geometry.unary_union
        return water_geom, True
    else:
        print(f"    Water: GEE download failed; proceeding without water mask")
        return None, False
