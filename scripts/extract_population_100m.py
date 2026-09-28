#!/usr/bin/env python
"""Extract GHS-POP population at native 100 m for every study polygon.

Replaces the previous approach, which summed a 1 km raster that had been resampled from
100 m without an additive reducer. That raster held a single 100 m cell value per 1 km
cell, so the zonal sums understated population by about 100x (measured 97x for the Jos
city region). See _build/build_report.md.

Here each polygon is reduced server-side against the native 100 m grid, by mapping
reduceRegion over one city's features so the whole city costs a single request:

    reduceRegion(reducer=ee.Reducer.sum(), geometry=<polygon>,
                 scale=100, crs=<GHS-POP native projection>, tileScale=...)

GEE's default fractional-overlap weighting applies, which is the same rule used for the
pilot truth values. No intermediate raster is produced and nothing is resampled.
reduceRegions is deliberately NOT used -- see _reduce for the measured reason.

One request per city, cached to Results/05_hotspot_analysis/population_100m/{slug}.csv.
A rerun skips cities already cached, so a failure never costs completed work.

Failures are handled by kind, because they are not the same problem:
  * a GEOMETRY error (GEE reports a bare "internal error") skips the tileScale ladder --
    raising tileScale cannot fix a malformed geometry -- and drops to one polygon at a time;
  * a CAPACITY error escalates tileScale 1 -> 4 -> 8 -> 16 with increasing waits;
  * a polygon GEE still refuses is reduced from a buffer(0)-repaired COPY, and only if the
    repair leaves the area within AREA_TOL. Stored geometries are never modified.
See the README beside the cache for the measured numbers behind each of these.

Usage:
    python scripts/extract_population_100m.py              # all cities, resume from cache
    python scripts/extract_population_100m.py --city Jos   # one city
    python scripts/extract_population_100m.py --force      # ignore the cache
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

R05 = ROOT / "Results" / "05_hotspot_analysis"
MASTER_GPKG = R05 / "master_thermal_spots.gpkg"
OUT_DIR = R05 / "population_100m"
SECRETS = ROOT / "secrets" / "gee_service_account.json"

GHS_COLLECTION = "JRC/GHSL/P2023A/GHS_POP"
TILE_SCALES = [1, 4, 8, 16]       # GEE default first (fastest); raised on each retry.
                                  # tileScale > 1 subdivides the computation, which costs
                                  # real time: at tileScale=4 a city took ~4 min against
                                  # ~2 s at the default, so it is a fallback, not a default.
WAITS = [5, 20, 60, 60]           # seconds before each retry
EXTRACTION_LABEL = "mapped reduceRegion sum, native 100 m grid, fractional overlap"

# GEE reports a malformed geometry as a bare "internal error". That is not a capacity
# problem, so raising tileScale cannot help and only wastes time: Onitsha burned 4 attempts
# and ~8 minutes before reaching the path that actually worked. Capacity problems announce
# themselves differently, and those are the ones tileScale is for.
GEOMETRY_ERROR = re.compile(r"internal error", re.I)
CAPACITY_ERROR = re.compile(r"timed? ?out|memory|too many|user memory|computation timed", re.I)


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_")


def ee_init():
    import ee
    info = json.loads(SECRETS.read_text())
    ee.Initialize(credentials=ee.ServiceAccountCredentials(info["client_email"], str(SECRETS)),
                  project=info["project_id"])
    return ee


def ghs_epoch() -> int:
    """Follow the project rule: the available GHSL epoch closest to the study year."""
    import config
    return int(config.get_closest_ghsl_year(config.PROJECT_STUDY_YEAR, verbose=False))


def load_polygons() -> gpd.GeoDataFrame:
    """The 609 distinct polygons: 441 spot contours plus 168 city zones.

    The 185 spot footprints are geometrically identical to their own L50 contours
    (symmetric difference / area < 3e-13), so they are not reduced a second time; each
    spot's L50/L75/L90 values are read back from its contours.
    """
    con = gpd.read_file(MASTER_GPKG, layer="hotspot_contours")
    con = con[["contour_id", "spot_id", "city", "period", "spot_type",
               "contour_level", "geometry"]].copy()
    con["kind"] = "contour"
    con["key"] = con["contour_id"]
    con["zone"] = None

    zon = gpd.read_file(MASTER_GPKG, layer="city_zones")[["city", "zone", "geometry"]].copy()
    zon["kind"] = "zone"
    zon["key"] = zon["city"].map(slugify) + "_" + zon["zone"].astype(str)
    for c in ("contour_id", "spot_id", "period", "spot_type", "contour_level"):
        zon[c] = None

    cols = ["key", "kind", "city", "spot_id", "period", "spot_type",
            "contour_level", "zone", "geometry"]
    out = pd.concat([con[cols], zon[cols]], ignore_index=True)
    out = gpd.GeoDataFrame(out, geometry="geometry", crs=con.crs)

    # Geometries are used exactly as stored: no dissolve, no repair. See _reduce for why.
    out["city_slug"] = out["city"].map(slugify)
    out["area_km2"] = out.geometry.to_crs("ESRI:102022").area / 1e6
    return out


def _reduce(ee, img, sub: gpd.GeoDataFrame, tile_scale: int) -> dict:
    """Reduce one city's polygons in a single request. Returns {key: population}.

    reduceRegion is mapped over the features rather than calling reduceRegions, because
    reduceRegions counts a pixel once per PART of a multi-part geometry, so parts sharing
    an edge are double-counted along it. 203 of the 609 polygons are multi-part, some with
    over 200 parts. Measured on Benin City's BRA: reduceRegions 79,067.89 against 77,488.47
    here, a 2.0% overstatement. Dissolving the parts first would fix it but alters 68
    invalid stored geometries -- Ilesa's BRA by 12.8% -- and published areas must not move.
    Mapping reduceRegion keeps the geometry exactly as stored and matches the pilot truth.
    """
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


AREA_TOL = 1e-6          # a repair may not move a polygon's area by more than this


def _one(ee, img, proj, geom, tile_scale=1):
    """Reduce a single polygon. Returns the population."""
    stats = img.reduceRegion(reducer=ee.Reducer.sum(),
                             geometry=ee.Geometry(mapping(geom), proj="EPSG:4326", geodesic=False),
                             scale=100, crs=proj, maxPixels=int(1e10),
                             tileScale=tile_scale, bestEffort=False)
    return float(stats.values().get(0).getInfo() or 0.0)


def _repair(geom):
    """buffer(0) repair, but only if it leaves the area alone.

    A handful of stored zone geometries are invalid (self-touching rings) and GEE rejects
    them outright with an internal error, whatever the tileScale. buffer(0) fixes Onitsha's
    BRA -- 141 parts, 5679.7068 km2 -- with a relative area change of 3.3e-08, whereas
    make_valid moves it by 3.5e-04 and GEE still refuses it. The guard matters: the same
    repair would inflate Ilesa's BRA by 12.8%, and a published area must never move, so a
    repair that large is refused and the city is reported as failed instead.
    """
    import geopandas as _gpd
    a0 = _gpd.GeoSeries([geom], crs="EPSG:4326").to_crs("ESRI:102022").area.iloc[0]
    fixed = geom.buffer(0)
    a1 = _gpd.GeoSeries([fixed], crs="EPSG:4326").to_crs("ESRI:102022").area.iloc[0]
    rel = abs(a1 - a0) / a0 if a0 else float("inf")
    if rel > AREA_TOL:
        raise RuntimeError(f"repair would change the area by {rel:.2e}; refused")
    return fixed, rel


def extract_city(ee, img, sub: gpd.GeoDataFrame, city: str) -> tuple[dict, int, set]:
    """Reduce one city. Returns (values, n_retries, keys whose geometry needed repair)."""
    last = None
    for attempt, ts in enumerate(TILE_SCALES):
        try:
            return _reduce(ee, img, sub, ts), attempt, set()
        except Exception as exc:
            last = exc
            print(f"      attempt {attempt + 1} (tileScale={ts}) failed: {str(exc)[:110]}")
            if GEOMETRY_ERROR.search(str(exc)) and not CAPACITY_ERROR.search(str(exc)):
                print("      -> geometry error, not capacity: skipping the tileScale ladder")
                break
            if attempt < len(TILE_SCALES) - 1:
                time.sleep(WAITS[attempt])

    # One bad polygon fails the whole city, so isolate them: reduce one at a time, and
    # repair only the ones GEE refuses, never the ones that merely take longer.
    print(f"      falling back to one polygon at a time")
    proj = img.projection()
    values, repaired, failed = {}, [], []
    for r in sub.itertuples():
        for ts in (1, 8):
            try:
                values[r.key] = _one(ee, img, proj, r.geometry, ts)
                break
            except Exception:
                continue
        else:
            try:
                fixed, rel = _repair(r.geometry)
                values[r.key] = _one(ee, img, proj, fixed)
                repaired.append((r.key, rel))
            except Exception as exc:
                last = exc
                failed.append(r.key)
    for k, rel in repaired:
        print(f"      repaired {k} for the reduction only (area moved {rel:.1e}); "
              f"the stored geometry is untouched")
    if failed:
        raise RuntimeError(f"{city}: {len(failed)} polygon(s) failed: {failed} ({last})")
    return values, len(TILE_SCALES), {k for k, _ in repaired}


def main() -> int:
    import functools
    global print
    print = functools.partial(__builtins__["print"] if isinstance(__builtins__, dict) else __builtins__.print, flush=True)
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", help="restrict to one city (display name)")
    ap.add_argument("--force", action="store_true", help="re-extract even if cached")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    polys = load_polygons()
    if args.city:
        polys = polys[polys["city"] == args.city]
        if polys.empty:
            print(f"no polygons for {args.city!r}")
            return 1

    ee = ee_init()
    epoch = ghs_epoch()
    img = ee.Image(f"{GHS_COLLECTION}/{epoch}")
    print(f"GHS-POP {GHS_COLLECTION}/{epoch} at "
          f"{img.projection().nominalScale().getInfo():.0f} m native\n")

    cities = sorted(polys["city"].unique())
    done, skipped, failed = 0, 0, []
    t_all = time.time()
    for n, city in enumerate(cities, 1):
        sub = polys[polys["city"] == city].reset_index(drop=True)
        cache = OUT_DIR / f"{slugify(city)}.csv"
        if cache.exists() and not args.force:
            skipped += 1
            continue
        print(f"[{n:>2}/{len(cities)}] {city} — {len(sub)} polygons")
        t0 = time.time()
        try:
            values, retries, repaired_keys = extract_city(ee, img, sub, city)
        except Exception as exc:
            print(f"      FAILED: {str(exc)[:200]}")
            failed.append(city)
            continue
        out = sub.drop(columns="geometry").copy()
        out["population_100m"] = out["key"].map(values)
        out["ghs_epoch"] = epoch
        out["extraction"] = EXTRACTION_LABEL
        out["geometry_repaired"] = out["key"].isin(repaired_keys)
        out.to_csv(cache, index=False)
        dt = time.time() - t0
        print(f"      {len(out)} values, {dt:6.1f}s, {retries} retr{'y' if retries == 1 else 'ies'}"
              f" -> {cache.name}")
        done += 1

    print(f"\nextracted {done}, skipped {skipped} cached, failed {len(failed)} "
          f"in {time.time() - t_all:.0f}s")
    if failed:
        print("failed cities:", failed)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
