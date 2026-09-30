#!/usr/bin/env python
"""Sum GHS-POP inside each study polygon, on the dataset's own 100 m grid.

Two independent extractions, deliberately kept apart:

  contours/  one row per KDE contour  ({spot_id}_L50 / _L75 / _L90)  -- the science
  zones/     one row per city zone    ({city_slug}_{urban_core|bra|city_region})

The contour path is the one the results depend on, so it is kept as plain as possible:
one polygon, one sum, no geometry repair, no fallback that touches a polygon. Every KDE
contour is a valid geometry and all of them reduce first time, so there is nothing for
repair code to do -- and if that ever stops being true the run fails loudly rather than
quietly adjusting a published polygon.

The zone path is separate because zone geometries are not clean: 68 of 168 are invalid
(52 BRA, 16 city-region), inherited from NB01's zone construction. One of them,
onitsha_bra, is refused by GEE outright. Only there is a repaired COPY used, and only if
the repair leaves the area within AREA_TOL. Nothing on disk is ever modified.

Why not the 1 km raster: it was resampled from 100 m without an additive reducer, so each
1 km cell carried one 100 m cell value rather than the sum of the ~100 beneath it. That
understated population by ~100x (Jos city region: 15,970 against 1,550,542). Fixing the
aggregation still left the 1 km pixel-centre rule putting only 3 of 10 Jos polygons within
5% of truth, so the raster is not used for population at all.

Why not reduceRegions: it counts a pixel once per PART of a multi-part geometry, so parts
sharing an edge are double counted. 203 of the 609 polygons are multi-part. Measured on
Benin City's BRA: 79,067.89 against 77,488.47, 2.0% high. reduceRegion is mapped over each
city's features instead -- same semantics as a single-polygon call, one request per city.

Nothing is downloaded. No raster, no city region: only the summed values come back.

City scope follows the active run, not whatever happens to be on disk. See active_cities().

Usage:
    python scripts/extract_population_100m.py                 # both, resume from cache
    python scripts/extract_population_100m.py --kind contours # one path only
    python scripts/extract_population_100m.py --city Jos --force
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

R01 = ROOT / "Results" / "01_aoi_delineation"
R05 = ROOT / "Results" / "05_hotspot_analysis"
MASTER_GPKG = R05 / "master_thermal_spots.gpkg"
OUT_DIR = R05 / "population_100m"
SECRETS = ROOT / "secrets" / "gee_service_account.json"

GHS_COLLECTION = "JRC/GHSL/P2023A/GHS_POP"
EXTRACTION_LABEL = "mapped reduceRegion sum, native 100 m grid, fractional overlap"

TILE_SCALES = [1, 4, 8, 16]   # GEE default first; tileScale subdivides and costs real time
WAITS = [5, 20, 60, 60]
AREA_TOL = 1e-6               # a repair may not move a polygon's area by more than this

# GEE reports a malformed geometry as a bare "internal error". No tileScale can fix that,
# so escalating is wasted time; capacity problems announce themselves differently.
GEOMETRY_ERROR = re.compile(r"internal error", re.I)
CAPACITY_ERROR = re.compile(r"timed? ?out|memory|too many|user memory|computation timed", re.I)


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_")


# -- scope -------------------------------------------------------------------
def active_cities():
    """Cities in the CURRENT run, not whatever is left on disk from an earlier one.

    NB01 writes study_cities_final.csv from config.CITY_SELECTION_MODE, marking each city
    'included' or 'absorbed'. That file is the same source data_io.load_stakeholder_datasets
    uses, so changing the mode in config.py and re-running NB01 narrows this automatically.

    This matters because master_thermal_spots.gpkg and the cache below both persist between
    runs. Without this filter, shrinking the selection would leave the extraction working on
    retired cities, and NB05 reading stale cached values back in.
    """
    f = R01 / "study_cities_final.csv"
    if not f.exists():
        raise SystemExit(str(f) + " not found: run NB01 before extracting population")
    df = pd.read_csv(f)
    return set(df.loc[df["status"] == "included", "city_name"].astype(str))


def _scoped(gdf, what):
    active = active_cities()
    present = set(gdf["city"].astype(str))
    stale, missing = sorted(present - active), sorted(active - present)
    if stale:
        tail = " ..." if len(stale) > 6 else ""
        print("  " + what + ": ignoring " + str(len(stale))
              + " city(ies) not in the current selection: " + str(stale[:6]) + tail)
    if missing:
        tail = " ..." if len(missing) > 6 else ""
        print("  " + what + ": [WARN] " + str(len(missing))
              + " selected city(ies) absent from " + MASTER_GPKG.name + ": "
              + str(missing[:6]) + tail)
    return gdf[gdf["city"].astype(str).isin(active)].reset_index(drop=True)


# -- polygons ----------------------------------------------------------------
def load_contours():
    """One row per KDE contour. Geometries are used exactly as stored.

    Spot footprints are not loaded separately: each is geometrically identical to its own
    L50 contour (symmetric difference / area < 3e-13), so a spot's three values are read
    back from its contours.
    """
    g = gpd.read_file(MASTER_GPKG, layer="hotspot_contours")
    g = g[["contour_id", "spot_id", "city", "period", "spot_type",
           "contour_level", "geometry"]].copy()
    g = g.rename(columns={"contour_id": "key"})
    return _finish(_scoped(g, "contours"))


def load_zones():
    """One row per city zone. Denominator for exposure shares; the README says why CR."""
    g = gpd.read_file(MASTER_GPKG, layer="city_zones")[["city", "zone", "geometry"]].copy()
    g["key"] = g["city"].map(slugify) + "_" + g["zone"].astype(str)
    return _finish(_scoped(g, "zones"))


def _finish(g):
    g["city_slug"] = g["city"].map(slugify)
    g["area_km2"] = g.geometry.to_crs("ESRI:102022").area / 1e6
    return g


# -- reduction ---------------------------------------------------------------
def ee_init():
    import ee
    info = json.loads(SECRETS.read_text())
    ee.Initialize(credentials=ee.ServiceAccountCredentials(info["client_email"], str(SECRETS)),
                  project=info["project_id"])
    return ee


def ghs_epoch():
    """The project rule: the available GHSL epoch closest to the study year (2024 -> 2025)."""
    import config
    return int(config.get_closest_ghsl_year(config.PROJECT_STUDY_YEAR, verbose=False))


def _sum_over(ee, img, geom, tile_scale=1):
    """Sum GHS-POP inside one polygon, on the image's own 100 m grid."""
    stats = img.reduceRegion(reducer=ee.Reducer.sum(),
                             geometry=ee.Geometry(mapping(geom), proj="EPSG:4326",
                                                  geodesic=False),
                             scale=100, crs=img.projection(), maxPixels=int(1e10),
                             tileScale=tile_scale, bestEffort=False)
    return float(stats.values().get(0).getInfo() or 0.0)


def _sum_city(ee, img, sub, tile_scale):
    """The same reduction mapped over one city's polygons, so a city costs one request."""
    proj = img.projection()
    feats = [ee.Feature(ee.Geometry(mapping(g), proj="EPSG:4326", geodesic=False), {"key": k})
             for k, g in zip(sub["key"], sub.geometry)]

    def per_feature(f):
        stats = img.reduceRegion(reducer=ee.Reducer.sum(), geometry=f.geometry(),
                                 scale=100, crs=proj, maxPixels=int(1e10),
                                 tileScale=tile_scale, bestEffort=False)
        return f.set("sum", stats.values().get(0))

    res = ee.FeatureCollection(feats).map(per_feature).getInfo()
    return {f["properties"]["key"]: float(f["properties"].get("sum") or 0.0)
            for f in res["features"]}


def _repair(geom):
    """buffer(0) on a throwaway copy, refused if it would move the area (zones only)."""
    a0 = gpd.GeoSeries([geom], crs="EPSG:4326").to_crs("ESRI:102022").area.iloc[0]
    fixed = geom.buffer(0)
    a1 = gpd.GeoSeries([fixed], crs="EPSG:4326").to_crs("ESRI:102022").area.iloc[0]
    rel = abs(a1 - a0) / a0 if a0 else float("inf")
    if rel > AREA_TOL:
        raise RuntimeError("repair would change the area by " + format(rel, ".2e") + "; refused")
    return fixed, rel


def extract_city(ee, img, sub, city, allow_repair):
    """Returns (values, n_retries, repaired_keys). allow_repair is False for contours."""
    last = None
    for attempt, ts in enumerate(TILE_SCALES):
        try:
            return _sum_city(ee, img, sub, ts), attempt, set()
        except Exception as exc:
            last = exc
            print("      attempt " + str(attempt + 1) + " (tileScale=" + str(ts)
                  + ") failed: " + str(exc)[:100])
            if GEOMETRY_ERROR.search(str(exc)) and not CAPACITY_ERROR.search(str(exc)):
                print("      -> geometry error, not capacity: skipping the tileScale ladder")
                break
            if attempt < len(TILE_SCALES) - 1:
                time.sleep(WAITS[attempt])

    print("      falling back to one polygon at a time")
    values, repaired, failed = {}, [], []
    for r in sub.itertuples():
        for ts in (1, 8):
            try:
                values[r.key] = _sum_over(ee, img, r.geometry, ts)
                break
            except Exception:
                continue
        else:
            if not allow_repair:
                failed.append(r.key)          # never adjust a KDE contour to make it work
                continue
            try:
                fixed, rel = _repair(r.geometry)
                values[r.key] = _sum_over(ee, img, fixed)
                repaired.append((r.key, rel))
            except Exception as exc:
                last = exc
                failed.append(r.key)
    for k, rel in repaired:
        print("      repaired " + k + " for the reduction only (area moved "
              + format(rel, ".1e") + "); the stored geometry is untouched")
    if failed:
        raise RuntimeError(city + ": " + str(len(failed)) + " polygon(s) failed: "
                           + str(failed) + " (" + str(last) + ")")
    return values, len(TILE_SCALES), set(k for k, _ in repaired)


# -- driver ------------------------------------------------------------------
def run(kind, polys, only_city, force):
    out_dir = OUT_DIR / kind
    out_dir.mkdir(parents=True, exist_ok=True)
    allow_repair = (kind == "zones")
    if only_city:
        polys = polys[polys["city"] == only_city]
        if polys.empty:
            print("  no " + kind + " for " + repr(only_city) + " in the current selection")
            return 0

    ee = ee_init()
    epoch = ghs_epoch()
    img = ee.Image(GHS_COLLECTION + "/" + str(epoch))
    cities = sorted(polys["city"].unique())
    print("\n" + kind + ": " + str(len(polys)) + " polygons across " + str(len(cities))
          + " cities (GHS-POP " + str(epoch) + ", native 100 m, repair "
          + ("permitted" if allow_repair else "DISABLED") + ")")

    done, skipped, failed = 0, 0, []
    t_all = time.time()
    for n, city in enumerate(cities, 1):
        sub = polys[polys["city"] == city].reset_index(drop=True)
        cache = out_dir / (slugify(city) + ".csv")
        if cache.exists() and not force:
            # The cache carries no year in its name, so a cached file from a different
            # GHS epoch would otherwise be reused silently after PROJECT_STUDY_YEAR
            # changes. Check the epoch recorded in the file and re-extract if it moved.
            try:
                cached_epoch = int(pd.read_csv(cache, nrows=1)["ghs_epoch"].iloc[0])
            except Exception:
                cached_epoch = None
            if cached_epoch == epoch:
                skipped += 1
                continue
            print("  " + city + ": cached epoch " + str(cached_epoch)
                  + " != current " + str(epoch) + " -- re-extracting")
        print("  [" + str(n) + "/" + str(len(cities)) + "] " + city + " - "
              + str(len(sub)) + " polygons", flush=True)
        t0 = time.time()
        try:
            values, retries, repaired = extract_city(ee, img, sub, city, allow_repair)
        except Exception as exc:
            print("      FAILED: " + str(exc)[:200])
            failed.append(city)
            continue
        rec = sub.drop(columns="geometry").copy()
        rec["population_100m"] = rec["key"].map(values)
        rec["ghs_epoch"] = epoch
        rec["extraction"] = EXTRACTION_LABEL
        if allow_repair:
            rec["geometry_repaired"] = rec["key"].isin(repaired)
        rec.to_csv(cache, index=False)
        print("      " + str(len(rec)) + " values, " + format(time.time() - t0, ".1f")
              + "s, " + str(retries) + " retries", flush=True)
        done += 1

    print("  " + kind + ": extracted " + str(done) + ", skipped " + str(skipped)
          + " cached, failed " + str(len(failed)) + " in "
          + format(time.time() - t_all, ".0f") + "s")
    if failed:
        print("  failed: " + str(failed))
    return 1 if failed else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=["contours", "zones", "both"], default="both")
    ap.add_argument("--city", help="restrict to one city (display name)")
    ap.add_argument("--force", action="store_true", help="re-extract even if cached")
    args = ap.parse_args()

    print("active city selection: " + str(len(active_cities())) + " cities "
          "(Results/01_aoi_delineation/study_cities_final.csv, status == 'included')")
    rc = 0
    if args.kind in ("contours", "both"):
        rc |= run("contours", load_contours(), args.city, args.force)
    if args.kind in ("zones", "both"):
        rc |= run("zones", load_zones(), args.city, args.force)
    return rc


if __name__ == "__main__":
    sys.exit(main())
