"""
Dual-Zone AOI Utilities
=======================
Helper functions for the revised NB01 methodology (MODIFICATION_SPEC §2.1).

Provides:
  - build_urban_core_smod() — UC from GHS-SMOD raster (classes 30+23, connected component)
  - build_city_region()     — BRA bounding box (full, unmasked — extraction domain)
  - compute_geometry_hash() — stable hash for smart-cache invalidation
  - zone_cache_valid()      — check whether saved zone files are still current
  - save_zone_geojsons()    — write all 6 zone GeoJSONs + metadata JSON
  - build_zone_metadata()   — assemble the per-city metadata dict

Legacy (retained for reference, not used in NB01_v4_SMOD):
  - build_urban_core()      — L50 polygon union (v1–v3 protocol)

CRS convention
--------------
All geometric operations are performed in ESRI:102022 (Africa Albers Equal
Area Conic).  The functions accept and return Shapely geometries already in
that CRS.  Storage to GeoJSON in EPSG:4326 is handled by save_zone_geojsons().
"""

from __future__ import annotations

import hashlib
import json
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import geopandas as gpd
import numpy as np
from shapely.geometry import mapping, shape, Point
from shapely.ops import unary_union

warnings.filterwarnings("ignore")


# =============================================================================
# Urban Core — GHS-SMOD (NB01_v4_SMOD)
# =============================================================================

def build_urban_core_smod(
    city_point,
    smod_array: np.ndarray,
    smod_transform,
    smod_crs: str,
    analysis_crs: str = "ESRI:102022",
    uc_classes: List[int] = None,
    fallback_radius_m: float = 1_000.0,
    merge_radius_m: float = 1_000.0,
) -> Tuple[Any, List[str]]:
    """
    Construct the Urban Core from a GHS-SMOD raster array.

    Algorithm
    ---------
    1. Mask the raster to UC classes (default: 30 = Urban Centre, 23 = Dense
       Urban Cluster).
    2. Label connected components (8-connectivity).
    3. Find the component whose pixels contain ``city_point``.
    4. Fallback: if the centroid misses all UC pixels, search within
       ``fallback_radius_m`` for the nearest UC pixel and use its component.
    5. Vectorise the selected component with ``rasterio.features.shapes``.
    6. Reproject the resulting polygon to ``analysis_crs``.
    7. Merge: absorb any other UC components whose boundary lies within
       ``merge_radius_m`` of the primary component (default 1 km). These are
       treated as part of the same urban block, separated only by gaps such as
       roads or narrow water bodies.

    Parameters
    ----------
    city_point : Shapely Point
        City centroid in ``analysis_crs`` (ESRI:102022).
    smod_array : np.ndarray
        2-D integer array of SMOD class codes (downloaded from GEE).
    smod_transform : affine.Affine
        Affine transform of ``smod_array`` (from rasterio / GEE pixel grid).
    smod_crs : str
        CRS string of the downloaded raster (e.g. "EPSG:4326" or native GEE CRS).
    analysis_crs : str
        Target CRS for returned geometry (default ESRI:102022).
    uc_classes : list[int]
        SMOD class codes that define the Urban Core.
        Default: [30, 23]  (Urban Centre + Dense Urban Cluster).
    fallback_radius_m : float
        Search radius in metres if centroid misses all UC pixels (default 1 km).
    merge_radius_m : float
        Distance in metres within which neighbouring UC components are merged
        into the primary component (default 1 km).  Set to 0 to disable.

    Returns
    -------
    uc_geom : Shapely geometry
        Urban Core polygon in ``analysis_crs``.
    flags : list[str]
        Diagnostic flags:
          'fallback_nearest'      — centroid missed UC pixels; nearest pixel used
          'fallback_buffer'       — no UC pixels within fallback radius; 5 km circle used
          'no_uc_pixels'          — raster has no UC-class pixels at all
          'merged_N_components'   — N additional nearby components merged in
    """
    import rasterio.features
    import rasterio.transform
    import scipy.ndimage as ndimage

    if uc_classes is None:
        uc_classes = [30, 23]

    flags: List[str] = []

    # ── Step 1: binary UC mask ────────────────────────────────────────────────
    uc_mask = np.isin(smod_array, uc_classes).astype(np.uint8)

    if uc_mask.sum() == 0:
        flags.append("no_uc_pixels")
        return city_point.buffer(5_000), flags

    # ── Step 2: connected components (8-connectivity) ─────────────────────────
    struct = ndimage.generate_binary_structure(2, 2)  # 8-connected
    labeled, n_components = ndimage.label(uc_mask, structure=struct)

    # ── Step 3: find component containing city_point ──────────────────────────
    # Convert city_point (analysis_crs) to raster pixel coordinates
    city_pt_gdf = gpd.GeoDataFrame(
        [1], geometry=[city_point], crs=analysis_crs
    ).to_crs(smod_crs)
    cx, cy = city_pt_gdf.geometry.iloc[0].x, city_pt_gdf.geometry.iloc[0].y

    # rasterio row/col from geographic coords
    row, col = rasterio.transform.rowcol(smod_transform, cx, cy)
    target_label = None

    if 0 <= row < labeled.shape[0] and 0 <= col < labeled.shape[1]:
        target_label = int(labeled[row, col])
        if target_label == 0:  # background pixel
            target_label = None

    # ── Step 4: fallback — nearest UC pixel within fallback_radius_m ──────────
    if target_label is None:
        flags.append("fallback_nearest")
        # pixel size in metres — handle geographic (degrees) vs projected (metres) CRS
        try:
            import pyproj
            _crs = pyproj.CRS(smod_crs)
            if _crs.is_geographic:
                px_size_m = abs(smod_transform.a) * 111_000  # degrees → metres (approx)
            else:
                px_size_m = abs(smod_transform.a)
        except Exception:
            px_size_m = abs(smod_transform.a) * 111_000  # safe fallback
        radius_px = int(np.ceil(fallback_radius_m / px_size_m))

        # Search window around centroid pixel
        r0 = max(0, row - radius_px)
        r1 = min(labeled.shape[0], row + radius_px + 1)
        c0 = max(0, col - radius_px)
        c1 = min(labeled.shape[1], col + radius_px + 1)

        window = uc_mask[r0:r1, c0:c1]
        if window.sum() > 0:
            uc_rows, uc_cols = np.where(window)
            dists = (uc_rows - (row - r0)) ** 2 + (uc_cols - (col - c0)) ** 2
            nearest_r = uc_rows[np.argmin(dists)] + r0
            nearest_c = uc_cols[np.argmin(dists)] + c0
            target_label = int(labeled[nearest_r, nearest_c])
        else:
            flags.append("fallback_buffer")
            return city_point.buffer(5_000), flags

    # ── Step 5: vectorise selected component ──────────────────────────────────
    component_mask = (labeled == target_label).astype(np.uint8)
    shapes = list(rasterio.features.shapes(component_mask, transform=smod_transform))
    polys = [shape(geom) for geom, val in shapes if val == 1]

    if not polys:
        flags.append("fallback_buffer")
        return city_point.buffer(5_000), flags

    uc_geom_smod_crs = unary_union(polys)

    # ── Step 6: reproject primary component to analysis_crs ──────────────────
    uc_gdf = gpd.GeoDataFrame(
        [1], geometry=[uc_geom_smod_crs], crs=smod_crs
    ).to_crs(analysis_crs)
    uc_geom = uc_gdf.geometry.iloc[0]

    # ── Step 7: merge nearby UC components within merge_radius_m ─────────────
    # Any other connected UC component within merge_radius_m of the primary is
    # treated as part of the same urban block (gap may be road, narrow water,
    # or simply a sub-1km classification gap).
    if merge_radius_m > 0 and n_components > 1:
        other_polys_smod = []
        for lbl in range(1, n_components + 1):
            if lbl == target_label:
                continue
            other_mask   = (labeled == lbl).astype(np.uint8)
            other_shapes = list(rasterio.features.shapes(other_mask, transform=smod_transform))
            comp_polys   = [shape(geom) for geom, val in other_shapes if val == 1]
            if comp_polys:
                other_polys_smod.append(unary_union(comp_polys))

        if other_polys_smod:
            others_gdf = gpd.GeoDataFrame(
                range(len(other_polys_smod)),
                geometry=other_polys_smod,
                crs=smod_crs,
            ).to_crs(analysis_crs)

            search_area = uc_geom.buffer(merge_radius_m)
            nearby = others_gdf[others_gdf.geometry.intersects(search_area)]

            if not nearby.empty:
                uc_geom = unary_union([uc_geom] + list(nearby.geometry))
                flags.append(f"merged_{len(nearby)}_components")

    return uc_geom, flags


# =============================================================================
# Urban Core — L50 legacy (v1–v3, retained for reference)
# =============================================================================

def build_urban_core(
    city_point,
    l50_gdf: gpd.GeoDataFrame,
    adjacent_buffer_m: int = 1000,
) -> Tuple[Any, List[str]]:
    """
    Construct the Urban Core geometry for a single city.

    Algorithm
    ---------
    1. Find the L50 polygon that contains `city_point`.
    2. Find all additional L50 polygons whose boundary intersects a
       `adjacent_buffer_m`-wide buffer around the main polygon.
    3. Return the unary union of all found polygons.

    If no L50 polygon contains the city point, fall back to a 5 km buffer
    around the point and flag it.

    Parameters
    ----------
    city_point : Shapely Point
        City centroid in ESRI:102022.
    l50_gdf : GeoDataFrame
        L50 (built-up) landscape typology polygons, already in ESRI:102022.
    adjacent_buffer_m : int
        Search radius (metres) for adjacent L50 polygons (default 1 000 m).

    Returns
    -------
    uc_geom : Shapely geometry
        Urban Core geometry in ESRI:102022.
    flags : list[str]
        Diagnostic flags (e.g. 'fallback_buffer', 'no_adjacent').
    """
    flags: List[str] = []

    # ── Step 1: find main polygon ──────────────────────────────────────────────
    main_polygon = None
    for _, row in l50_gdf.iterrows():
        if row.geometry.contains(city_point):
            main_polygon = row.geometry
            break

    if main_polygon is None:
        # Try intersects (point may lie on boundary)
        for _, row in l50_gdf.iterrows():
            if row.geometry.intersects(city_point):
                main_polygon = row.geometry
                break

    if main_polygon is None:
        flags.append("fallback_buffer")
        main_polygon = city_point.buffer(5_000)  # 5 km fallback

    # ── Step 2: find adjacent L50 polygons ────────────────────────────────────
    search_area = main_polygon.buffer(adjacent_buffer_m)
    adjacent = []
    main_id = id(main_polygon)

    for _, row in l50_gdf.iterrows():
        if id(row.geometry) == main_id:
            continue
        if row.geometry is main_polygon:
            continue
        if row.geometry.intersects(search_area) and not row.geometry.equals(main_polygon):
            adjacent.append(row.geometry)

    if not adjacent:
        flags.append("no_adjacent")

    # ── Step 3: union ──────────────────────────────────────────────────────────
    all_polys = [main_polygon] + adjacent
    uc_geom = unary_union(all_polys)

    return uc_geom, flags


# =============================================================================
# BRA extent
# =============================================================================
# The BRA bounding box is built in NB01 as envelope(UC_raw.buffer(config.BRA_BUFFER_M)):
# a fixed radius, deterministic, no search. The Dynamic Equal-Area ring search of
# Yang et al. (2024) that previously lived here (compute_bra_dea) was never called by
# NB01_v5_SMOD and was removed on 2026-09-28. Every published geometry was produced by
# the fixed buffer; see "bra_method": "fixed_buffer" in each city's zone metadata.


# =============================================================================
# City-Region
# =============================================================================

def build_city_region(bra_bbox_geom, water_geom=None) -> Any:
    """
    City-Region = BRA bounding box minus JRC water bodies.

    All land cover types are retained (including SMOD urban classes within the
    bbox); only open water is removed.  CR is the full raster extraction domain
    for MODIS, SEVIRI, and ERA5 — both UC and BRA are spatial sub-zones of CR.

    Parameters
    ----------
    bra_bbox_geom : Shapely Polygon
        BRA bounding box in ESRI:102022, i.e. envelope(UC_raw.buffer(BRA_BUFFER_M)).
    water_geom : Shapely geometry or None
        Union of JRC water bodies in ESRI:102022.  Pass None to skip.

    Returns
    -------
    Shapely Polygon
        City-Region polygon in ESRI:102022 (water bodies excluded).
    """
    cr = bra_bbox_geom
    if water_geom is not None and not water_geom.is_empty:
        cr = cr.difference(water_geom).buffer(0)
    return cr


# =============================================================================
# Smart-cache helpers
# =============================================================================

def compute_geometry_hash(geom, source_version: str = "") -> str:
    """
    Return a short SHA-256 hash of a geometry + source version string.

    Used to invalidate the smart cache when the input geometry or
    algorithm version changes.
    """
    geom_wkt = geom.wkt if hasattr(geom, "wkt") else str(geom)
    raw = f"{geom_wkt}|{source_version}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def zone_cache_valid(
    uc_4326_path: Path,
    meta_path: Path,
    source_version: str,
    city_point,
) -> bool:
    """
    Return True if cached zone files exist and the geometry hash matches.

    Cache is considered valid when:
    - `uc_4326_path` and `meta_path` exist on disk
    - The `source_version` in the saved metadata equals `source_version`
    - The `geometry_hash` in the saved metadata matches the current city_point hash

    Parameters
    ----------
    uc_4326_path : Path
        Path to the saved Urban Core GeoJSON (4326).
    meta_path : Path
        Path to the saved zone_metadata.json.
    source_version : str
        Current algorithm version tag (e.g. 'NB01_v2_DEA').
    city_point : Shapely Point
        City centroid in ESRI:102022.
    """
    if not uc_4326_path.exists() or not meta_path.exists():
        return False
    try:
        meta = json.loads(meta_path.read_text())
        if meta.get("source_version") != source_version:
            return False
        expected_hash = compute_geometry_hash(city_point, source_version)
        if meta.get("geometry_hash") != expected_hash:
            return False
        return True
    except Exception:
        return False


# =============================================================================
# Output helpers
# =============================================================================

def _to_polygon(geom):
    """
    Normalise a Shapely geometry for saving.

    Order of operations:
      1. buffer(0)            — repairs self-intersections / invalid rings
      2. GeometryCollection   — extract Polygon/MultiPolygon parts, unary_union
      3. MultiPolygon         — kept as-is (UC may legitimately span multiple
                                merged blocks; BRA/CR are bbox-derived and will
                                almost always remain a single Polygon)
      4. Anything else        — convex_hull as last resort
    """
    geom = geom.buffer(0)
    gtype = geom.geom_type

    if gtype == "Polygon":
        return geom

    if gtype == "GeometryCollection":
        polys = [g for g in geom.geoms if g.geom_type in ("Polygon", "MultiPolygon")]
        if not polys:
            return geom.convex_hull
        geom = unary_union(polys)
        gtype = geom.geom_type

    if gtype == "MultiPolygon":
        return geom   # preserve all parts — do NOT discard smaller blocks

    return geom.convex_hull


def save_zone_geojsons(
    city_dir: Path,
    city_slug: str,
    uc_geom,
    bra_geom,
    cr_geom,
    meta: dict,
    analysis_crs: str = "ESRI:102022",
    storage_crs: str = "EPSG:4326",
    file_version: str = "",
) -> None:
    """
    Write the six zone GeoJSONs (UC / BRA / CR × 2 CRS) and metadata JSON.

    Parameters
    ----------
    file_version : str
        Version suffix appended to all output filenames before the extension,
        e.g. '_v5' → '{city_slug}_urban_core_4326_v5.geojson'.
        Default '' keeps the legacy naming.

    Output files
    ------------
    {city_slug}_urban_core_102022{file_version}.geojson
    {city_slug}_urban_core_4326{file_version}.geojson
    {city_slug}_bra_102022{file_version}.geojson
    {city_slug}_bra_4326{file_version}.geojson
    {city_slug}_city_region_102022{file_version}.geojson
    {city_slug}_city_region_4326{file_version}.geojson
    {city_slug}_zone_metadata{file_version}.json
    """
    city_dir.mkdir(parents=True, exist_ok=True)

    for name, geom in [("urban_core", uc_geom), ("bra", bra_geom), ("city_region", cr_geom)]:
        geom = _to_polygon(geom)
        gdf_anl = gpd.GeoDataFrame(
            [{"zone": name, "city": city_slug}],
            geometry=[geom],
            crs=analysis_crs,
        )
        gdf_str = gdf_anl.to_crs(storage_crs)

        anl_path = city_dir / f"{city_slug}_{name}_102022{file_version}.geojson"
        str_path = city_dir / f"{city_slug}_{name}_4326{file_version}.geojson"
        gdf_anl.to_file(anl_path, driver="GeoJSON")
        gdf_str.to_file(str_path, driver="GeoJSON")

    # Metadata JSON
    meta_path = city_dir / f"{city_slug}_zone_metadata{file_version}.json"
    meta_path.write_text(json.dumps(meta, indent=2, default=str))


def build_zone_metadata(
    city_name: str,
    city_row,
    uc_geom,
    bra_geom,
    cr_geom,
    bra_buffer_m: float,
    uc_flags: List[str],
    absorbed_cities: List[str],
    source_version: str,
    smod_epoch_year: int = 0,
    analysis_crs: str = "ESRI:102022",
) -> Dict[str, Any]:
    """
    Assemble the per-city zone metadata dictionary (NB01_v5_SMOD).

    BRA is defined as envelope(UC_raw.buffer(bra_buffer_m)) — a fixed radius with no
    iteration, recorded as bra_method = "fixed_buffer".

    Returns a JSON-serialisable dict with area stats, BRA diagnostics,
    SMOD epoch, smart-cache hashes, and deduplication info.
    Zone fraction fields (water, SMOD built-up) are added separately via
    dict.update() after this function returns.
    """
    city_point_geom = Point(
        float(city_row.get("Longitude", 0)),
        float(city_row.get("Latitude", 0)),
    )
    geom_hash = compute_geometry_hash(city_point_geom, source_version)

    return {
        # Identity
        "city_name":        city_name,
        "latitude":         float(city_row.get("Latitude", 0)),
        "longitude":        float(city_row.get("Longitude", 0)),
        "population_2024":  float(city_row.get("2024", 0)),

        # Zone areas (km²)
        "uc_area_km2":      round(uc_geom.area / 1e6, 4),
        "bra_area_km2":     round(bra_geom.area / 1e6, 4),
        "cr_area_km2":      round(cr_geom.area / 1e6, 4),
        "bra_uc_ratio":     round(bra_geom.area / uc_geom.area if uc_geom.area > 0 else float("nan"), 4),

        # BRA diagnostics (fixed-buffer approach)
        "bra_buffer_m":     round(bra_buffer_m, 1),
        "bra_method":       "fixed_buffer",

        # Urban Core flags + SMOD epoch
        "uc_flags":         uc_flags,
        "smod_epoch_year":  smod_epoch_year,

        # Deduplication
        "absorbed_cities":  absorbed_cities,

        # Smart-cache
        "source_version":   source_version,
        "geometry_hash":    geom_hash,
        "analysis_crs":     analysis_crs,
        "created_at":       datetime.utcnow().isoformat(),
    }
