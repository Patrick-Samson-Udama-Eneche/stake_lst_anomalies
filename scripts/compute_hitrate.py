#!/usr/bin/env python
"""Stakeholder hit rate: do participant-marked points fall inside detected spots?

Single source of truth for the hit rate. NB05 section 9 imports hit_rate_table() from
here so the notebook and the published layer cannot drift apart.

Cohort basis (v1.0.1). Points come from the 94 released coordinates in
stakeholder_spots_gps -- 55 hot, 39 cold, from the 105-participant registration cohort.
v1.0.0 selected points by city of ATTENDANCE instead, giving 57 hot and 40 cold, which
included the three points of a respondent with no registration record. Only the point
SELECTION changed; the counting rule below is unchanged.

Counting rule, as in NB05 section 9:
  * a point is compared against the buffered L50 footprints of the SAME spot type and
    period, from ANY city, not only its own;
  * geometry in ESRI:102022, buffers 500 m to 10 km in 500 m steps;
  * the spatial join is one row per (point, containing footprint), so a point inside
    several footprints contributes several rows, and a point inside none contributes one
    row with hit = False. Rows are then grouped by the point's city. n_total is therefore
    a row count, not a point count, and grows with buffer distance.

Coordinates. The released, rounded-to-3-decimal coordinates are used, so the hit rates
can be reproduced from the published dataset alone.
"""
from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
R05 = ROOT / "Results" / "05_hotspot_analysis"
PKG = R05 / "surface_thermal_anomaly_stakeholder_composite" / \
      "surface_thermal_anomaly_stakeholder_composite.gpkg"

ANALYSIS_CRS = "ESRI:102022"
BUFFERS_M = list(range(500, 10_500, 500))


def load_cohort_points(gpkg: Path = PKG) -> gpd.GeoDataFrame:
    """The 94 released cohort points, in the analysis CRS."""
    g = gpd.read_file(gpkg, layer="stakeholder_spots_gps")
    return g.to_crs(ANALYSIS_CRS)


def load_spots(gpkg: Path = PKG) -> gpd.GeoDataFrame:
    """L50 spot footprints, in the analysis CRS."""
    g = gpd.read_file(gpkg, layer="spots")
    return g.to_crs(ANALYSIS_CRS)


def hit_rate(points: gpd.GeoDataFrame, spots: gpd.GeoDataFrame,
             spot_type: str, period: str, buf_m: int,
             city_col: str = "city") -> pd.DataFrame:
    """One (spot_type, period, buffer) slice. Returns a frame indexed by city."""
    pts = points[points["spot_type"] == spot_type]
    if pts.empty:
        return pd.DataFrame()
    computed = spots[(spots["spot_type"] == spot_type) & (spots["period"] == period)].copy()
    if computed.empty:
        return pd.DataFrame()
    computed["geometry"] = computed.geometry.buffer(buf_m)
    joined = gpd.sjoin(pts, computed[["geometry"]], how="left", predicate="within")
    joined["hit"] = joined["index_right"].notna()
    out = (joined.groupby(city_col)["hit"].agg(["sum", "count"])
           .rename(columns={"sum": "n_hit", "count": "n_total"}))
    out["n_hit"] = out["n_hit"].astype(int)
    out["hit_rate"] = out["n_hit"] / out["n_total"]
    out["buffer_m"] = buf_m
    out["spot_type"] = spot_type
    out["period"] = period
    return out.reset_index().rename(columns={city_col: "city"})


def hit_rate_table(points: gpd.GeoDataFrame | None = None,
                   spots: gpd.GeoDataFrame | None = None,
                   buffers: list[int] | None = None) -> pd.DataFrame:
    """The full sensitivity table across type, period and buffer."""
    points = load_cohort_points() if points is None else points
    spots = load_spots() if spots is None else spots
    buffers = BUFFERS_M if buffers is None else buffers
    frames = [hit_rate(points, spots, st, per, b)
              for b in buffers
              for st in ("hot", "cold")
              for per in ("day", "night")]
    frames = [f for f in frames if len(f)]
    df = pd.concat(frames, ignore_index=True)
    return df.sort_values(["spot_type", "period", "buffer_m", "city"]).reset_index(drop=True)


def main() -> int:
    # Nothing is written. hitrate_sensitivity is produced during the build, from the
    # released layers; a CSV here would be a second copy that could drift from it.
    df = hit_rate_table()
    print(f"recomputed {len(df)} rows from the published layers (nothing written)")
    at500 = df[df.buffer_m == 500].groupby(["spot_type", "period"])[["n_hit", "n_total"]].sum()
    print("\n500 m, summed over cities:")
    for (st, per), r in at500.iterrows():
        print(f"  {st:4} {per:5}  {int(r.n_hit)}/{int(r.n_total)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
