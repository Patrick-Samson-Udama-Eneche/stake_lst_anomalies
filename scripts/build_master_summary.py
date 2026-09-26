#!/usr/bin/env python
"""
Build the master summary dataset for the 56-city diurnal surface thermal anomaly study.

Reads only outputs that already exist under Results/ and writes only into
Results/05_hotspot_analysis/master_summary/. Re-runnable and deterministic: the
only value that changes between runs is the build date in `dataset_info`.

Usage
-----
    python scripts/build_master_summary.py
    python scripts/build_master_summary.py --out /tmp/reproduce_check

Excluded by design: association analysis, cluster/national aggregates, and the
raw questionnaire. See the generated README.md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
from shapely.geometry import Polygon

try:
    import h3
except ImportError:  # pragma: no cover
    h3 = None

# ── constants ───────────────────────────────────────────────────────────────
VERSION = "1.0.0"
DATASET_DIR  = "surface_thermal_anomaly_stakeholder_composite"   # published dataset root
DATASET_STEM = "surface_thermal_anomaly_stakeholder_composite"   # the single data file
# Names are protocol-generic: the instance (region, city set, study years, selection
# rule) is recorded in the dataset_info and scenario_config layers, not in the names.
CRS_ANALYSIS = "ESRI:102022"          # Africa Albers Equal Area Conic
CRS_WGS84 = "EPSG:4326"
STUDY_YEAR = int(__import__("os").environ.get("LST_STUDY_YEAR", "2024"))  # event-scale year;
                                       # overridden by --study-year / discovered from sources
TREND_FIRST, TREND_LAST = 2006, 2025
H3_RES = 8

ROOT = Path(__file__).resolve().parents[1]
R01 = ROOT / "Results" / "01_aoi_delineation"
R02 = ROOT / "Results" / "02_stakeholder_analysis"
R03 = ROOT / "Results" / "03_temporal_analysis"
R04 = ROOT / "Results" / "04_temporal_analysis_daily"
R05 = ROOT / "Results" / "05_hotspot_analysis"
MASTER_GPKG = R05 / "master_thermal_spots.gpkg"

ZONE_MAP = {"urban_core": "uc", "bra": "bra", "city_region": "cr", "delta_uc_bra": "suhii"}
ZONE_ORDER = ["uc", "bra", "cr", "suhii"]
PERIODS = ["day", "night"]
SPOT_TYPES = ["hot", "cold"]

LOG: list[str] = []
DEVIATIONS: list[str] = []
CHECKS: list[str] = []


def log(msg: str) -> None:
    print(msg)
    LOG.append(msg)


def slugify(city) -> str:
    return str(city).replace(" ", "_")


def clean_city(name) -> str:
    """Strip BH-FDR decoration such as 'Abonnema [★D-Hot]'."""
    return str(name).split(" [")[0].strip()


def nullify(df: pd.DataFrame, cols, sentinel=0) -> pd.DataFrame:
    """Turn a not-applicable sentinel into a real null for the given columns."""
    for c in cols:
        if c in df.columns:
            df[c] = df[c].replace(sentinel, np.nan)
    return df


# ── shared reference tables ─────────────────────────────────────────────────
def load_reference():
    lookup = pd.read_csv(R01 / "city_cluster25_lookup.csv")
    lookup = lookup.rename(columns={"city_name": "city", "Cluster25": "cluster25"})
    areas = pd.read_csv(R01 / "zone_area_summary_with_pop.csv")
    ce = pd.read_csv(R04 / "city_heat_event_summary.csv")
    cities = sorted(ce["city"].astype(str).unique())
    ref = pd.DataFrame({"city": cities})
    ref["city_slug"] = ref["city"].map(slugify)
    ref = ref.merge(lookup[["city", "cluster25", "land_code25", "Climate_Class",
                            "Landcover_Class", "Elevation_Class", "Geology_Class"]],
                    on="city", how="left")
    ref = ref.rename(columns={"Climate_Class": "climate_class",
                              "Landcover_Class": "landcover_class",
                              "Elevation_Class": "elevation_class",
                              "Geology_Class": "geology_class"})
    ref = ref.merge(areas.drop(columns=[c for c in ("Cluster25", "Climate_Class",
                                                    "Geology_Class", "Elevation_Class")
                                        if c in areas.columns]),
                    on="city", how="left")
    # percent of the urban core occupied by the assigned Cluster25
    ucd = pd.read_csv(R01 / "cluster25_uc_distribution.csv").rename(columns={"City Region": "city"})
    pct = []
    for _, r in ref.iterrows():
        row = ucd[ucd["city"] == r["city"]]
        col = f"C{int(r['cluster25'])}" if pd.notna(r["cluster25"]) else None
        pct.append(float(row.iloc[0][col]) if len(row) and col in ucd.columns else np.nan)
    ref["pct_dominant_class"] = pct
    return ref.sort_values("city_slug").reset_index(drop=True)



# ── scenario: the config that makes one complete run distinct ───────────────
# Every layer carries `scenario_id`, an 8-character digest of these parameters, so
# runs made under different settings (city-selection rule, thresholds, study year)
# coexist in one package and can be filtered apart.
def capture_scenario():
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "src"))
    import config as cfg
    try:
        from daily_analysis_utils import _DEFAULT_PERCENTILE, _DEFAULT_PERSISTENT
    except Exception:
        _DEFAULT_PERCENTILE, _DEFAULT_PERSISTENT = 90, 2
    mode = getattr(cfg, "CITY_SELECTION_MODE", "[UNKNOWN]")
    n_cand = {"ABOVE_1M": len(getattr(cfg, "CITIES_ABOVE_1M", [])),
              "ABOVE_500K": len(getattr(cfg, "CITIES_ABOVE_500K", [])),
              "ABOVE_300K": len(getattr(cfg, "CITIES_ABOVE_300K", []))}.get(mode)
    params = [
        ("city_selection_mode", mode, "config.py CITY_SELECTION_MODE"),
        ("city_selection_rule", {"ABOVE_1M": "UN WUP 2024 population >= 1,000,000",
                                 "ABOVE_500K": "UN WUP 2024 population >= 500,000",
                                 "ABOVE_300K": "UN WUP 2024 population >= 300,000",
                                 "ALL": "all UN WUP 2025 Nigerian cities",
                                 }.get(mode, "[CHECK] custom selection"), "config.py"),
        ("n_candidate_cities", n_cand, "config.py CITIES_* list length"),
        ("study_year", getattr(cfg, "PROJECT_STUDY_YEAR", None), "config.py PROJECT_STUDY_YEAR"),
        ("analysis_crs", getattr(cfg, "ANALYSIS_CRS", None), "config.py ANALYSIS_CRS"),
        ("smod_uc_classes", str(getattr(cfg, "SMOD_UC_CLASSES", "")), "config.py SMOD_UC_CLASSES"),
        ("smod_builtup_classes", str(getattr(cfg, "SMOD_BUILTUP_CLASSES", "")), "config.py"),
        ("smod_merge_radius_m", getattr(cfg, "SMOD_MERGE_RADIUS_M", None), "config.py"),
        ("bra_buffer_m", getattr(cfg, "BRA_BUFFER_M", None), "config.py BRA_BUFFER_M"),
        ("bra_tolerance", getattr(cfg, "BRA_TOLERANCE", None), "config.py BRA_TOLERANCE"),
        ("bra_max_dist_m", getattr(cfg, "BRA_MAX_DIST_M", None), "config.py"),
        ("bra_min_ring_m", getattr(cfg, "BRA_MIN_RING_M", None), "config.py"),
        ("jrc_occurrence_threshold_pct", getattr(cfg, "JRC_OCCURRENCE_THRESHOLD", None), "config.py"),
        ("jrc_min_water_area_m2", getattr(cfg, "JRC_MIN_WATER_AREA_M2", None), "config.py"),
        ("era5_min_pixels", getattr(cfg, "ERA5_MIN_PIXELS", None), "config.py ERA5_MIN_PIXELS"),
        ("event_percentile", _DEFAULT_PERCENTILE, "src/daily_analysis_utils.py _DEFAULT_PERCENTILE"),
        ("event_min_consecutive_days", _DEFAULT_PERSISTENT, "src/daily_analysis_utils.py _DEFAULT_PERSISTENT"),
        ("gistar_z_hot", 1.96, "NB05 GISTAR_Z_HOT"),
        ("gistar_z_cold", -1.96, "NB05 GISTAR_Z_COLD"),
        ("bh_fdr_alpha", getattr(cfg, "HOTSPOT_FDR_ALPHA", 0.05), "NB05 FDR_ALPHA"),
        ("kde_contour_levels", str(getattr(cfg, "KDE_CONTOUR_LEVELS", [0.50, 0.75, 0.90])), "NB05 KDE_CONTOURS"),
        ("random_state", getattr(cfg, "RANDOM_STATE", None), "config.py RANDOM_STATE"),
    ]
    canon = json.dumps({k: str(v) for k, v, _ in params}, sort_keys=True, separators=(",", ":"))
    sid = hashlib.sha1(canon.encode("utf-8")).hexdigest()[:8]
    df = pd.DataFrame([{"scenario_id": sid, "parameter": k, "value": ("" if v is None else str(v)),
                        "source": src} for k, v, src in params])
    return sid, df


# ── accumulation: never overwrite an earlier scenario or study year ─────────
# Event-scale layers are replaced only for the (scenario_id, study_year) being built;
# scenario-scoped layers only for the scenario_id. Everything else is carried forward.
YEAR_KEYED = {"city_year_summary", "heat_event_catalogue", "spot_occurrence", "spots",
              "spot_contours", "hitrate_sensitivity", "city_exposure_by_contour"}


def merge_with_existing(layers, gpkg: Path, scenario_id: str, study_years: set):
    if not gpkg.exists():
        return layers
    try:
        existing = {n for n, _ in pyogrio.list_layers(gpkg)}
    except Exception:
        return layers
    merged = {}
    for name, new in layers.items():
        if new is None:
            continue
        if name not in existing:
            merged[name] = new
            continue
        spatial = isinstance(new, gpd.GeoDataFrame) and new.geometry.notna().any()
        old = (gpd.read_file(gpkg, layer=name) if spatial
               else pyogrio.read_dataframe(gpkg, layer=name, read_geometry=False))
        if "scenario_id" not in old.columns:
            merged[name] = new
            continue
        keep = old["scenario_id"].astype(str) != str(scenario_id)
        if name in YEAR_KEYED and "study_year" in old.columns:
            keep = keep | (~old["study_year"].isin(study_years))
        old = old[keep]
        if len(old):
            out = pd.concat([old, new], ignore_index=True)
            merged[name] = gpd.GeoDataFrame(out, geometry="geometry", crs=new.crs) if spatial else out
            log(f"    accumulated {name}: kept {len(old)} earlier rows + {len(new)} new")
        else:
            merged[name] = new
    return merged


# ── layer 1: city_zones ─────────────────────────────────────────────────────
def build_city_zones(ref):
    rows = []
    for _, r in ref.iterrows():
        s = r["city_slug"]
        for src_zone, zone in (("urban_core", "uc"), ("bra", "bra"), ("city_region", "cr")):
            f = R01 / s / f"{s}_{src_zone}_102022_v5.geojson"
            if not f.exists():
                continue
            g = gpd.read_file(f)
            geom = g.geometry.union_all()
            area_col = {"uc": "uc_area_km2", "bra": "bra_area_km2", "cr": "cr_area_km2"}[zone]
            rows.append({"city_slug": s, "city": r["city"], "cluster25": r["cluster25"],
                         "zone": zone, "area_km2": r.get(area_col, np.nan), "geometry": geom})
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=CRS_ANALYSIS)
    gdf["zone"] = pd.Categorical(gdf["zone"], ZONE_ORDER[:3], ordered=True)
    gdf = gdf.sort_values(["city_slug", "zone"]).reset_index(drop=True)
    gdf["zone"] = gdf["zone"].astype(str)
    return gdf


# ── layers 2a/2b: city_profile (stable) + city_year_summary (per study year) ──
# Split so that re-running the protocol for another year appends a city_year_summary
# row instead of overwriting the city's stable attributes.
def build_city_profile(ref, zones):
    """Year-independent city attributes: PLT classes, zone geometry-derived areas, population."""
    df = ref.copy()
    pts = gpd.read_file(R02 / "Data" / "Cities_Stakeholder_Points_2024.geojson")
    if "total_attendees" in pts.columns:
        df["n_participants"] = df["city"].map(
            pts.set_index("city")["total_attendees"]).fillna(0).astype(int)
    uc = zones[zones.zone == "uc"].set_index("city_slug").geometry
    geom = df["city_slug"].map(lambda s: uc[s].centroid if s in uc.index else None)
    gdf = gpd.GeoDataFrame(df, geometry=gpd.GeoSeries(geom.values, crs=CRS_ANALYSIS),
                           crs=CRS_ANALYSIS)
    return gdf.sort_values("city_slug").reset_index(drop=True)


def build_city_year_summary(ref, spots, study_year=STUDY_YEAR):
    """Per-year city record: ERA5-Land persistence, selected events, sensor comparison, spot counts."""
    ce = pd.read_csv(R04 / "city_heat_event_summary.csv")
    df = ref[["city_slug", "city", "cluster25"]].copy()
    df["study_year"] = study_year

    # ERA5-Land persistence only (issue A); MODIS hot-day frequency is dropped
    for p_ in PERIODS:
        for src, dst in (("n_persistent_events", f"era5_{p_}_n_persistent_events"),
                         ("longest_event_days", f"era5_{p_}_longest_event_days"),
                         ("total_persistent_days", f"era5_{p_}_total_persistent_days"),
                         ("n_hot_days", f"era5_{p_}_n_hot_days")):
            col = f"era5_{p_}_{src}"
            df[dst] = df["city"].map(ce.set_index("city")[col]) if col in ce.columns else np.nan
    for p_ in PERIODS:
        for src, dst in ((f"{p_}_sel_start", f"{p_}_selected_event_start"),
                         (f"{p_}_sel_end", f"{p_}_selected_event_end"),
                         (f"{p_}_sel_duration_days", f"{p_}_selected_event_duration_days"),
                         (f"{p_}_sel_tier", f"{p_}_selected_event_tier"),
                         (f"{p_}_corr_n", f"{p_}_modis_era5land_n"),
                         (f"{p_}_corr_r", f"{p_}_modis_era5land_r"),
                         (f"{p_}_corr_r2", f"{p_}_modis_era5land_r2"),
                         (f"{p_}_corr_bias", f"{p_}_modis_era5land_bias_c"),
                         (f"{p_}_corr_rmse", f"{p_}_modis_era5land_rmse_c"),
                         (f"{p_}_corr_mae", f"{p_}_modis_era5land_mae_c")):
            df[dst] = df["city"].map(ce.set_index("city")[src]) if src in ce.columns else np.nan

    sy = spots[spots["study_year"] == study_year] if "study_year" in spots.columns else spots
    cnt = sy.groupby(["city_slug", "period", "spot_type"]).size().rename("n").reset_index()
    bh = (sy[sy["bh_significant"].astype(str).str.lower().isin(["true", "1"])]
          .groupby(["city_slug", "period", "spot_type"]).size().rename("n").reset_index())
    for p_ in PERIODS:
        for t in SPOT_TYPES:
            a = cnt[(cnt.period == p_) & (cnt.spot_type == t)].set_index("city_slug")["n"]
            df[f"n_{t}_{p_}_spots"] = df["city_slug"].map(a).fillna(0).astype(int)
            b = bh[(bh.period == p_) & (bh.spot_type == t)].set_index("city_slug")["n"]
            df[f"n_{t}_{p_}_bh_significant"] = df["city_slug"].map(b).fillna(0).astype(int)

    mcc = pd.read_csv(R05 / "master_city_composite.csv")
    for c in ("validation_tier", "bh_any"):
        if c in mcc.columns:
            df[c] = df["city"].map(mcc.set_index("city")[c])
    return df.sort_values(["city_slug", "study_year"]).reset_index(drop=True)


# ── layers 3-6: trends, annual series, monthly series, climatology ──────────
TREND_COLS = ["n", "mk_z", "mk_p", "mk_trend", "autocorr_corrected", "lag1_autocorr",
              "ljungbox_pvalue", "sen_slope_per_year", "sen_slope_per_decade", "intercept",
              "ols_slope", "ols_r_squared", "ols_p_value", "highest_year", "highest_year_lst",
              "lowest_year", "lowest_year_lst"]
SERIES_EXTRA = ["mean_lst", "min_lst", "max_lst", "std_lst", "p05_lst", "p95_lst",
                "mean_spatial_std", "n_images_total", "n_obs_total", "n_strict_total",
                "n_moderate_total", "pct_strict", "pct_valid_obs", "n_valid_months",
                "pct_valid_months", "low_coverage", "hottest_month", "coolest_month"]


def _load_annual():
    ta = pd.read_csv(R03 / "all_cities_temporal_annual.csv")
    ta["zone"] = ta["zone"].map(ZONE_MAP)
    da = pd.read_csv(R03 / "all_cities_delta_annual.csv")
    da["zone"] = da["zone"].map(ZONE_MAP).fillna("suhii")
    da = da.rename(columns={"delta_lst": "value_c"})
    ta = ta.rename(columns={"median_lst": "value_c"})
    return ta, da


def build_trend_statistics(ref):
    ta, da = _load_annual()
    keep = ["city", "zone", "period"] + [c for c in TREND_COLS if c in ta.columns]
    a = ta[keep].drop_duplicates(["city", "zone", "period"])
    keepd = ["city", "zone", "period"] + [c for c in TREND_COLS if c in da.columns]
    d = da[keepd].drop_duplicates(["city", "zone", "period"])
    t = pd.concat([a, d], ignore_index=True)
    # hottest month from the annual table (mode across years), amplitude from climatology
    t = t.rename(columns={"n": "n_years", "mk_p": "mk_p_value",
                          "sen_slope_per_decade": "sen_slope_c_per_decade",
                          "sen_slope_per_year": "sen_slope_c_per_year",
                          "highest_year_lst": "highest_year_value_c",
                          "lowest_year_lst": "lowest_year_value_c",
                          "ljungbox_pvalue": "ljungbox_p_value"})
    t["mk_method"] = np.where(t["autocorr_corrected"].astype(str).str.lower().isin(["true", "1"]),
                              "Hamed-Rao variance correction", "original Mann-Kendall")
    t["city_slug"] = t["city"].map(slugify)
    t["cluster25"] = t["city"].map(ref.set_index("city")["cluster25"])
    t["zone"] = pd.Categorical(t["zone"], ZONE_ORDER, ordered=True)
    cols = ["city_slug", "city", "cluster25", "zone", "period", "n_years", "mk_method",
            "mk_z", "mk_p_value", "mk_trend", "autocorr_corrected", "lag1_autocorr",
            "ljungbox_p_value", "sen_slope_c_per_year", "sen_slope_c_per_decade", "intercept",
            "ols_slope", "ols_r_squared", "ols_p_value", "highest_year", "highest_year_value_c",
            "lowest_year", "lowest_year_value_c"]
    t = t[[c for c in cols if c in t.columns]]
    t = t.sort_values(["city_slug", "zone", "period"]).reset_index(drop=True)
    t["zone"] = t["zone"].astype(str)
    return t


def build_annual_series(ref):
    ta, da = _load_annual()
    keep = ["city", "zone", "period", "year", "value_c"] + [c for c in SERIES_EXTRA if c in ta.columns]
    a = ta[keep].copy()
    d = da[["city", "zone", "period", "year", "value_c"]].copy()
    s = pd.concat([a, d], ignore_index=True)
    s["city_slug"] = s["city"].map(slugify)
    s["cluster25"] = s["city"].map(ref.set_index("city")["cluster25"])
    s["zone"] = pd.Categorical(s["zone"], ZONE_ORDER, ordered=True)
    front = ["city_slug", "city", "cluster25", "zone", "period", "year", "value_c"]
    s = s[front + [c for c in s.columns if c not in front + ["city"]]]
    s = s.sort_values(["city_slug", "zone", "period", "year"]).reset_index(drop=True)
    s["zone"] = s["zone"].astype(str)
    return s


def build_monthly(ref):
    tm = pd.read_csv(R03 / "all_cities_temporal_monthly.csv")
    tm["zone"] = tm["zone"].map(ZONE_MAP)
    tm = tm.rename(columns={"median_lst": "value_c"})
    dm = pd.read_csv(R03 / "all_cities_delta_monthly.csv")
    dm["zone"] = dm["zone"].map(ZONE_MAP).fillna("suhii")
    dm = dm.rename(columns={"delta_lst": "value_c"})
    base = ["city", "zone", "period", "year", "month", "value_c"]
    extra = [c for c in ("mean_lst", "min_lst", "max_lst", "std_lst", "n_images", "n_obs",
                         "n_strict") if c in tm.columns]
    a = tm[base + extra].copy()
    d = dm[[c for c in base if c in dm.columns]].copy()
    s = pd.concat([a, d], ignore_index=True)
    s["city_slug"] = s["city"].map(slugify)
    s["cluster25"] = s["city"].map(ref.set_index("city")["cluster25"])
    s["zone"] = pd.Categorical(s["zone"], ZONE_ORDER, ordered=True)
    front = ["city_slug", "city", "cluster25", "zone", "period", "year", "month", "value_c"]
    s = s[front + [c for c in s.columns if c not in front + ["city"]]]
    s = s.sort_values(["city_slug", "zone", "period", "year", "month"]).reset_index(drop=True)
    s["zone"] = s["zone"].astype(str)

    clim = (s.groupby(["city_slug", "city", "cluster25", "zone", "period", "month"],
                      observed=True)["value_c"]
            .agg(mean_value_c="mean", std_value_c="std", n_years_used="count")
            .reset_index())
    clim["zone"] = pd.Categorical(clim["zone"], ZONE_ORDER, ordered=True)
    clim = clim.sort_values(["city_slug", "zone", "period", "month"]).reset_index(drop=True)
    clim["zone"] = clim["zone"].astype(str)
    return s, clim


# ── layer 7: heat_event_catalogue ───────────────────────────────────────────
def build_heat_events(ref):
    rows = []
    sev_root = R04 / "seviri"
    for _, r in ref.iterrows():
        city, s = r["city"], r["city_slug"]
        f = R04 / "events" / f"{city}_event_audit.json"
        if not f.exists():
            continue
        audit = json.loads(f.read_text(encoding="utf-8"))
        for p in PERIODS:
            blk = audit.get(p) or {}
            thr = (blk.get("thresholds") or {}).get("era5_p90_celsius", np.nan)
            sel = blk.get("selected_event") or {}
            for ev in blk.get("era5_persistent_events", []) or []:
                st, en = ev.get("start_date"), ev.get("end_date")
                is_sel = bool(sel) and sel.get("start_date") == st and sel.get("end_date") == en
                sev = np.nan
                if is_sel and st and en:
                    tag = f"{city}_SEVIRI_{p}_{st.replace('-', '')}_{en.replace('-', '')}_"
                    sev = any((sev_root / city).glob(tag + "*")) if (sev_root / city).exists() else False
                rows.append({
                    "event_id": f"{s}_{p}_{st}", "city_slug": s, "city": city,
                    "cluster25": r["cluster25"], "period": p, "study_year": STUDY_YEAR,
                    "start_date": st, "end_date": en,
                    "duration_days": ev.get("duration"), "tier": ev.get("tier"),
                    "is_selected": is_sel,
                    "selection_reason": sel.get("selection_reason") if is_sel else None,
                    "era5_p90_threshold_c": thr,
                    "seviri_scene_available": sev if is_sel else np.nan,
                })
    df = pd.DataFrame(rows)
    return df.sort_values(["city_slug", "period", "start_date"]).reset_index(drop=True)


# ── layer 8: spot_occurrence ────────────────────────────────────────────────
def build_spot_occurrence(ref, spots):
    sc = pd.read_csv(R05 / "spot_comprehensive_summary.csv")
    sc["city"] = sc["City"].map(clean_city)
    sc["period"] = sc["Period"].str.lower()
    sc["spot_type"] = sc["Type"].str.lower()
    grid = pd.MultiIndex.from_product(
        [ref["city_slug"], PERIODS, SPOT_TYPES],
        names=["city_slug", "period", "spot_type"]).to_frame(index=False)
    grid = grid.merge(ref[["city_slug", "city", "cluster25"]], on="city_slug", how="left")
    sc["city_slug"] = sc["city"].map(slugify)
    keep = {"n_px_z": "n_gistar_pixels", "n_px_bh": "n_bh_fdr_pixels", "T1": "n_tier1",
            "T2": "n_tier2", "area_50_km2": "area_l50_km2", "area_75_km2": "area_l75_km2",
            "area_90_km2": "area_l90_km2", "area_75_pct": "area_l75_pct",
            "area_90_pct": "area_l90_pct", "L75_compl": "l75_completeness",
            "L90_compl": "l90_completeness"}
    m = grid.merge(sc[["city_slug", "period", "spot_type"] + list(keep)]
                   .rename(columns=keep), on=["city_slug", "period", "spot_type"], how="left")
    cnt = spots.groupby(["city_slug", "period", "spot_type"]).size().rename("n_spots").reset_index()
    m = m.merge(cnt, on=["city_slug", "period", "spot_type"], how="left")
    m["n_spots"] = m["n_spots"].fillna(0).astype(int)
    bh = (spots[spots["bh_significant"].astype(str).str.lower().isin(["true", "1"])]
          .groupby(["city_slug", "period", "spot_type"]).size().rename("n_bh_significant").reset_index())
    m = m.merge(bh, on=["city_slug", "period", "spot_type"], how="left")
    m["n_bh_significant"] = m["n_bh_significant"].fillna(0).astype(int)
    for c in ("n_tier1", "n_tier2", "n_gistar_pixels", "n_bh_fdr_pixels"):
        m[c] = m[c].fillna(0).astype(int)
    for c in ("area_l50_km2", "area_l75_km2", "area_l90_km2"):
        m[c] = m[c].fillna(0.0)
    m["study_year"] = STUDY_YEAR
    front = ["city_slug", "city", "cluster25", "period", "spot_type", "study_year",
             "n_spots", "n_tier1", "n_tier2", "n_bh_significant",
             "n_gistar_pixels", "n_bh_fdr_pixels"]
    m = m[front + [c for c in m.columns if c not in front]]
    return m.sort_values(["city_slug", "period", "spot_type"]).reset_index(drop=True)


# ── layer 9: spots ──────────────────────────────────────────────────────────
DROP_FROM_SPOTS = ["climate_class", "landcover_class", "elevation_class", "geology_class",
                   "pct_dominant_class", "city_area_km2", "uc_area_km2", "bra_area_km2",
                   "sen_slope_C_per_decade", "mk_p_value", "mk_trend",
                   "n_modis_hot_days", "n_persistent_events", "longest_event_days",
                   "h3_cells_json", "h3_cell_count",
                   # L75/L90 outlines are real geometries in spot_contours; the WKT
                   # strings average ~1.9 kB and would make the CSV unusable.
                   "geom_75_wkt", "geom_90_wkt"]


def build_spots(ref):
    g = gpd.read_file(R05 / "all_cities_spots.geojson")
    g = g.drop(columns=[c for c in DROP_FROM_SPOTS if c in g.columns])
    g["city"] = g["city"].map(clean_city)
    g["city_slug"] = g["city"].map(slugify)
    g = g.rename(columns={"suhii": "suhii_event_c", "core_mean_lst": "core_mean_lst_c",
                          "core_max_lst": "core_max_lst_c", "mean_lst": "mean_lst_c",
                          "std_lst": "std_lst_c", "max_lst": "max_lst_c", "min_lst": "min_lst_c",
                          "population": "population_persons", "pop_75": "pop_l75_persons",
                          "pop_90": "pop_l90_persons", "area_km2_50": "area_l50_km2",
                          "area_km2_75": "area_l75_km2", "area_km2_90": "area_l90_km2",
                          "n_pixels_75": "n_pixels_l75", "n_pixels_90": "n_pixels_l90",
                          "zone": "spot_zone"})
    if "study_year" not in g.columns:
        g["study_year"] = STUDY_YEAR
    g["spot_uid"] = g["study_year"].astype(int).astype(str) + "_" + g["spot_id"].astype(str)
    front = ["spot_uid", "spot_id", "city_slug", "city", "cluster25", "period", "spot_type",
             "study_year", "spot_zone", "tier", "bh_significant"]
    g = g[[c for c in front if c in g.columns] + [c for c in g.columns if c not in front + ["geometry"]] + ["geometry"]]
    g = g.to_crs(CRS_ANALYSIS)
    return g.sort_values(["city_slug", "period", "spot_type", "spot_id"]).reset_index(drop=True)


# ── layer 10: hotspot_contours ──────────────────────────────────────────────
def build_contours(ref):
    """One row per contour. `area_km2` is already the contour's own area; population and
    pixel count are collapsed to the matching level so nothing is replicated. Spot-level
    attributes (LST statistics, tier, dense_core_pct ...) stay in `spots` and join on spot_id."""
    g = gpd.read_file(MASTER_GPKG, layer="hotspot_contours")
    g["city"] = g["city"].map(clean_city)
    g["city_slug"] = g["city"].map(slugify)
    lvl = g["contour_level"].astype(str)
    pop_src = {"L50": "population", "L75": "pop_75", "L90": "pop_90"}
    px_src = {"L50": "n_pixels", "L75": "n_pixels_75", "L90": "n_pixels_90"}
    g["population_persons"] = [g.at[i, pop_src[l]] if pop_src.get(l) in g.columns else np.nan
                               for i, l in lvl.items()]
    g["n_pixels_level"] = [g.at[i, px_src[l]] if px_src.get(l) in g.columns else np.nan
                           for i, l in lvl.items()]
    if "study_year" not in g.columns:
        g["study_year"] = STUDY_YEAR
    g["spot_uid"] = g["study_year"].astype(int).astype(str) + "_" + g["spot_id"].astype(str)
    g["contour_uid"] = g["spot_uid"] + "_" + g["contour_level"].astype(str)
    keep = ["contour_uid", "contour_id", "spot_uid", "spot_id", "city_slug", "city", "cluster25",
            "period", "spot_type", "contour_level", "study_year", "area_km2",
            "population_persons", "n_pixels_level", "geometry"]
    g = g[[c for c in keep if c in g.columns]].to_crs(CRS_ANALYSIS)
    DEVIATIONS.append(
        "spot_contours: per-contour population and pixel count collapsed to the matching "
        "level (population/pop_75/pop_90 -> population_persons). Spot-level LST statistics, "
        "tier and dense_core_pct were not duplicated onto the 441 contour rows; they remain in "
        "`spots` and join on spot_id.")
    return g.sort_values(["city_slug", "spot_id", "contour_level"]).reset_index(drop=True)


# ── layer 11: h3_grid (generated) ───────────────────────────────────────────
def build_h3_grid(spots):
    if h3 is None:
        DEVIATIONS.append("h3 library unavailable — layer 11 h3_grid omitted.")
        return None
    g4 = spots.to_crs(CRS_WGS84)
    rows = []
    for r in g4.itertuples():
        geom = r.geometry
        if geom is None or geom.is_empty:
            continue
        try:
            cells = list(h3.geo_to_cells(geom.__geo_interface__, H3_RES))
        except Exception:
            cells = []
        # a spot smaller than one res-8 cell (0.737 km2) contains no cell centroid, so
        # fall back to the cell holding its own centroid rather than losing the spot
        source = "polygon_fill"
        if not cells:
            c = geom.centroid
            cells = [h3.latlng_to_cell(c.y, c.x, H3_RES)]
            source = "centroid_fallback"
        for c in cells:
            rows.append({"h3_index": c, "h3_resolution": H3_RES, "cell_source": source,
                         "spot_uid": getattr(r, "spot_uid", None), "spot_id": r.spot_id,
                         "city_slug": r.city_slug, "city": r.city, "cluster25": r.cluster25,
                         "period": r.period, "spot_type": r.spot_type,
                         "study_year": getattr(r, "study_year", STUDY_YEAR)})
    if not rows:
        DEVIATIONS.append("h3 generation produced no cells — layer 11 omitted.")
        return None
    df = pd.DataFrame(rows).drop_duplicates(["h3_index", "spot_uid"])
    geoms = [Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(c)]) for c in df["h3_index"]]
    gdf = gpd.GeoDataFrame(df, geometry=geoms, crs=CRS_WGS84).to_crs(CRS_ANALYSIS)
    return gdf.sort_values(["city_slug", "spot_id", "h3_index"]).reset_index(drop=True)


# ── layers 12-13: stakeholder (pseudonymised) ───────────────────────────────
ALLOWED_PERCEPTION = {"61_temp_increase_10yrs": "perceived_warming_10yr",
                      "60_diurnal_severity_heat": "perceived_diurnal_severity",
                      "58_temp_peak_city": "perceived_peak_period",
                      "56_recency_with_city": "years_associated_with_city"}


def build_participant_key(ref):
    pp = pd.read_csv(R02 / "Data" / "Stakeholder_Perception_Data_2024.csv")
    k = pp[["pid", "city"]].drop_duplicates("pid").copy()
    k["city"] = k["city"].map(clean_city)
    k = k.sort_values(["city", "pid"], kind="mergesort").reset_index(drop=True)
    k["participant_code"] = [f"P{i:03d}" for i in range(1, len(k) + 1)]
    k["city_slug"] = k["city"].map(slugify)
    return k


def build_perception(ref, key):
    pp = pd.read_csv(R02 / "Data" / "Stakeholder_Perception_Data_2024.csv")
    wa = pd.read_csv(R02 / "Data" / "workshop_attendees_clean.csv")
    df = pp.merge(wa, on="pid", how="left", suffixes=("", "_wa"))
    df = df.rename(columns={"warming": "perceived_warming_10yr",
                            "diurnal": "perceived_diurnal_severity"})
    for src, dst in ALLOWED_PERCEPTION.items():
        if src in df.columns and dst not in df.columns:
            df[dst] = df[src]
    df = df.merge(key[["pid", "participant_code", "city_slug"]], on="pid", how="left")
    df["city"] = df["city"].map(clean_city)
    df["cluster25"] = df["city"].map(ref.set_index("city")["cluster25"])
    out = df[["participant_code", "city_slug", "city", "cluster25",
              "perceived_warming_10yr", "perceived_diurnal_severity",
              "perceived_peak_period", "years_associated_with_city"]]
    return out.sort_values("participant_code").reset_index(drop=True)


def build_gps(ref, key):
    codes = key.set_index("pid")["participant_code"]
    frames = []
    for layer, t in (("stakeholder_hotspot_gps", "hot"), ("stakeholder_coldspot_gps", "cold")):
        g = gpd.read_file(MASTER_GPKG, layer=layer)
        g = g[["pid", "matched_city_y", "geometry"]].copy()
        g["spot_type"] = t
        frames.append(g)
    g = pd.concat(frames, ignore_index=True)
    before = len(g)
    g = g[g["pid"].isin(codes.index)].copy()      # drops cal235 (no registration/attendance city)
    dropped = before - len(g)
    if dropped:
        DEVIATIONS.append(
            f"stakeholder_spots_gps: dropped {dropped} point(s) from participant(s) absent from "
            "the 105 (cal235 — no registration city, city match sourced from '55_other_cities'). "
            f"Result {len(g)} points, not the 97 in the uncorrected source.")
    g["participant_code"] = g["pid"].map(codes)
    g["city"] = g["matched_city_y"].map(clean_city)
    g["city_slug"] = g["city"].map(slugify)
    g["cluster25"] = g["city"].map(ref.set_index("city")["cluster25"])
    g["study_year"] = STUDY_YEAR
    out = gpd.GeoDataFrame(
        g[["participant_code", "city_slug", "city", "cluster25", "spot_type", "study_year",
           "geometry"]], geometry="geometry", crs=CRS_WGS84).to_crs(CRS_ANALYSIS)
    return out.sort_values(["participant_code", "spot_type"]).reset_index(drop=True)


# ── layers 14-15 ────────────────────────────────────────────────────────────
def build_hitrate(ref):
    d = pd.read_csv(R05 / "stakeholder_hitrate_sensitivity.csv")
    d = d.rename(columns={"matched_city_y": "city"})
    d["city"] = d["city"].map(clean_city)
    d["city_slug"] = d["city"].map(slugify)
    d["study_year"] = STUDY_YEAR
    out = d[["city_slug", "city", "cluster25", "period", "spot_type", "study_year",
             "buffer_m", "n_hit", "n_total", "hit_rate"]]
    return out.sort_values(["city_slug", "spot_type", "period", "buffer_m"]).reset_index(drop=True)


def build_halfdonut(ref):
    d = pd.read_csv(R05 / "halfdonut_city_summary.csv")
    d["city"] = d["city"].map(clean_city)
    d["city_slug"] = d["city"].map(slugify)
    d["cluster25"] = d["city"].map(ref.set_index("city")["cluster25"])
    d["study_year"] = STUDY_YEAR
    d = d.rename(columns={"area_km2_50": "area_l50_km2", "area_km2_75": "area_l75_km2",
                          "area_km2_90": "area_l90_km2", "pop_50": "pop_l50_persons",
                          "pop_75": "pop_l75_persons", "pop_90": "pop_l90_persons"})
    out = d[["city_slug", "city", "cluster25", "spot_type", "period", "study_year",
             "area_l50_km2", "area_l75_km2", "area_l90_km2",
             "pop_l50_persons", "pop_l75_persons", "pop_l90_persons"]]
    return out.sort_values(["city_slug", "spot_type", "period"]).reset_index(drop=True)


# ── layer 16: dataset_info ──────────────────────────────────────────────────
def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:
        return "[UNKNOWN]"


def build_dataset_info(layers, n_cities, n_clusters, study_years, scenario_id, scen_df):
    rows = [
        ("title", "Dataset and protocol associated with the analysis of the diurnal surface "
                  "thermal anomalies across 56 Nigerian cities situated in 16 physiographic "
                  "landscape typologies"),
        ("version", VERSION),
        ("build_date", date.today().isoformat()),
        ("crs_geopackage", CRS_ANALYSIS),
        ("crs_geojson", CRS_WGS84),
        ("spatial_coverage", "Nigeria, approximately 4-14 N and 2-15 E"),
        ("temporal_coverage_modis", f"{TREND_FIRST}-{TREND_LAST} (MODIS Aqua MYD11A1)"),
        ("temporal_coverage_era5", f"{STUDY_YEAR} (ERA5-Land)"),
        ("temporal_coverage_seviri", f"{STUDY_YEAR} selected persistent heat events (MSG-SEVIRI)"),
        ("region", "Nigeria"),
        ("scenario_id", scenario_id),
        ("city_selection_mode", scen_df.set_index("parameter").loc["city_selection_mode", "value"]),
        ("city_selection_rule", scen_df.set_index("parameter").loc["city_selection_rule", "value"]),
        ("n_candidate_cities", scen_df.set_index("parameter").loc["n_candidate_cities", "value"]),
        ("n_cities", str(n_cities)),
        ("n_plt_clusters", str(n_clusters)),
        ("study_years", ", ".join(str(y) for y in study_years)),
        ("licence", "CC BY 4.0"),
        ("build_script", "scripts/build_master_summary.py"),
        ("git_commit", git_commit()),
        ("dataset_doi", "[PENDING-DOI]"),
        ("code_repository_doi", "[PENDING-DOI]"),
    ]
    rows += [("scenario_ids_in_package", "see the scenario_config layer")]
    rows += [(f"rows_{n}", str(len(d))) for n, d in layers.items() if d is not None]
    return pd.DataFrame(rows, columns=["key", "value"])


# ── data dictionary ─────────────────────────────────────────────────────────
DESCR = {
    "city_slug": ("Stable city key, as used in the AoI file names.", "", "derived", "keying", "NB01 AoI file names"),
    "city": ("City display name.", "", "derived", "keying", "NB01 study_cities_final.csv"),
    "cluster25": ("Physiographic landscape typology (PLT) cluster identifier.", "", "derived", "PLT typology overlay", "NB01 city_cluster25_lookup.csv"),
    "zone": ("Spatial zone: uc urban core, bra built-up rural area ring, cr city region, suhii the urban-core minus BRA difference.", "", "derived", "three-zone delineation", "NB01 AoI v5"),
    "period": ("Overpass period: day or night.", "", "derived", "", "all notebooks"),
    "spot_type": ("Thermal anomaly type: hot or cold.", "", "derived", "Gi* sign", "NB05"),
    "contour_level": ("KDE contour level: L50 outer extent, L75 inner zone, L90 dense core.", "", "derived", "Gaussian KDE", "NB05 section 6"),
    "study_year": ("Event-scale study year.", "year", "derived", "", "NB04/NB05"),
    "area_km2": ("Polygon area.", "km2", "derived", "area in ESRI:102022", "NB01/NB05"),
    "geometry": ("Feature geometry.", "", "derived", "", "NB01/NB05"),
    "climate_class": ("Predominant climate class of the PLT cluster.", "", "derived", "PLT typology", "NB01 city_cluster25_lookup.csv"),
    "landcover_class": ("Predominant land-cover class of the PLT cluster.", "", "derived", "PLT typology", "NB01 city_cluster25_lookup.csv"),
    "elevation_class": ("Elevation belt of the PLT cluster.", "", "derived", "PLT typology", "NB01 city_cluster25_lookup.csv"),
    "geology_class": ("Geological substrate of the PLT cluster.", "", "derived", "PLT typology", "NB01 city_cluster25_lookup.csv"),
    "pct_dominant_class": ("Percentage of the urban core occupied by the assigned Cluster25 class.", "%", "derived", "zonal composition", "NB01 cluster25_uc_distribution.csv"),
    "n_years": ("Number of years in the trend test.", "years", "MODIS", "Mann-Kendall", "NB03"),
    "mk_method": ("Mann-Kendall variant applied.", "", "MODIS", "original Mann-Kendall or Hamed-Rao variance correction", "NB03"),
    "mk_z": ("Mann-Kendall Z statistic.", "", "MODIS", "Mann-Kendall", "NB03"),
    "mk_p_value": ("Mann-Kendall two-sided p-value.", "", "MODIS", "Mann-Kendall", "NB03"),
    "mk_trend": ("Trend label: increasing, decreasing or no trend.", "", "MODIS", "Mann-Kendall", "NB03"),
    "autocorr_corrected": ("True when the Hamed-Rao correction was applied.", "", "MODIS", "Ljung-Box then Hamed-Rao", "NB03"),
    "lag1_autocorr": ("Lag-1 autocorrelation of the annual series.", "", "MODIS", "autocorrelation", "NB03"),
    "ljungbox_p_value": ("Ljung-Box test p-value for serial correlation.", "", "MODIS", "Ljung-Box", "NB03"),
    "sen_slope_c_per_year": ("Theil-Sen slope per year.", "C/yr", "MODIS", "Theil-Sen", "NB03"),
    "sen_slope_c_per_decade": ("Theil-Sen slope per decade.", "C/decade", "MODIS", "Theil-Sen", "NB03"),
    "intercept": ("Theil-Sen intercept.", "C", "MODIS", "Theil-Sen", "NB03"),
    "ols_slope": ("Ordinary least squares slope per year.", "C/yr", "MODIS", "OLS", "NB03"),
    "ols_r_squared": ("OLS coefficient of determination.", "", "MODIS", "OLS", "NB03"),
    "ols_p_value": ("OLS slope p-value.", "", "MODIS", "OLS", "NB03"),
    "value_c": ("Zone value: annual or monthly median LST for zones uc, bra and cr; the urban-core minus BRA difference for zone suhii.", "C", "MODIS", "zonal statistics", "NB03"),
    "event_id": ("Event key: city_slug, period and start date.", "", "derived", "keying", "NB04 event audit"),
    "start_date": ("First day of the persistent heat event.", "date", "ERA5-Land", "P90 threshold, >= 2 consecutive days", "NB04 event audit"),
    "end_date": ("Last day of the persistent heat event.", "date", "ERA5-Land", "P90 threshold, >= 2 consecutive days", "NB04 event audit"),
    "duration_days": ("Event length.", "days", "ERA5-Land", "P90 threshold, >= 2 consecutive days", "NB04 event audit"),
    "tier": ("Event quality tier assigned during selection.", "", "ERA5-Land", "event selection", "NB04 event audit"),
    "is_selected": ("True for the event chosen for SEVIRI compositing.", "", "ERA5-Land", "event selection", "NB04 event audit"),
    "era5_p90_threshold_c": ("City and period specific 90th percentile of the ERA5-Land daily LST series.", "C", "ERA5-Land", "P90 threshold", "NB04 event audit"),
    "n_spots": ("Number of delineated spots.", "count", "SEVIRI", "Gi* |Z| >= 1.96 then KDE delineation", "NB05"),
    "n_tier1": ("Tier-1 spots delineated by KDE (>= 10 validated pixels).", "count", "SEVIRI", "KDE delineation", "NB05 section 6"),
    "n_tier2": ("Tier-2 spots represented by a 1 km buffer (1-9 pixels).", "count", "SEVIRI", "tier-2 buffering", "NB05 section 6"),
    "n_bh_significant": ("Spots surviving the BH-FDR control.", "count", "SEVIRI", "BH-FDR q = 0.05", "NB05"),
    "n_gistar_pixels": ("Pixels passing the Gi* significance test.", "count", "SEVIRI", "Gi* |Z| >= 1.96, Queen contiguity", "NB05 spot_comprehensive_summary.csv"),
    "n_bh_fdr_pixels": ("Pixels surviving BH-FDR control.", "count", "SEVIRI", "BH-FDR q = 0.05", "NB05 spot_comprehensive_summary.csv"),
    "bh_significant": ("True when the spot survives BH-FDR control.", "", "SEVIRI", "BH-FDR q = 0.05", "NB05"),
    "population_persons": ("Resident population within the L50 footprint.", "persons", "GHS-POP", "zonal sum", "NB05"),
    "pop_l75_persons": ("Resident population within the L75 zone.", "persons", "GHS-POP", "zonal sum", "NB05"),
    "pop_l90_persons": ("Resident population within the L90 dense core.", "persons", "GHS-POP", "zonal sum", "NB05"),
    "suhii_event_c": ("Event-scale surface urban heat island intensity, urban core minus BRA.", "C", "SEVIRI", "zonal mean difference", "NB05"),
    "h3_index": ("H3 cell index.", "", "derived", f"H3 res {H3_RES} indexing of the L50 footprint", "generated by this script"),
    "h3_resolution": ("H3 resolution.", "", "derived", "H3 indexing", "generated by this script"),
    "cell_source": ("How the cell was obtained: polygon_fill for normal coverage, centroid_fallback for spots smaller than one resolution-8 cell (0.737 km2).", "", "derived", f"H3 res {H3_RES} indexing", "generated by this script"),
    "participant_code": ("Pseudonymous participant code, P001 to P105.", "", "stakeholder", "pseudonymisation", "NB02, remapped here"),
    "perceived_warming_10yr": ("Perceived temperature increase over the last ten years.", "", "stakeholder", "questionnaire item 61", "NB02"),
    "perceived_diurnal_severity": ("Period in which heat is felt most severely.", "", "stakeholder", "questionnaire item 60", "NB02"),
    "perceived_peak_period": ("Months perceived as the city's temperature peak.", "", "stakeholder", "questionnaire item 58", "NB02"),
    "years_associated_with_city": ("How long the participant has been associated with the city.", "", "stakeholder", "questionnaire item 56", "NB02"),
    "buffer_m": ("Buffer radius applied around stakeholder-marked points.", "m", "derived", "buffer sensitivity", "NB05"),
    "n_hit": ("Stakeholder points falling inside a delineated spot at this buffer.", "count", "derived", "buffer sensitivity", "NB05"),
    "n_total": ("Stakeholder points tested at this buffer.", "count", "derived", "buffer sensitivity", "NB05"),
    "hit_rate": ("n_hit divided by n_total.", "fraction", "derived", "buffer sensitivity", "NB05"),
    "n_participants": ("Workshop attendees recorded for the city.", "count", "stakeholder", "attendance", "NB02"),
}
DESCR.update({
    # time keys and observation counts (NB03 zonal statistics)
    "year": ("Calendar year.", "year", "MODIS", "zonal statistics", "NB03"),
    "month": ("Calendar month, 1 to 12.", "month", "MODIS", "zonal statistics", "NB03"),
    "mean_lst": ("Zonal mean LST.", "C", "MODIS", "zonal statistics", "NB03"),
    "min_lst": ("Zonal minimum LST.", "C", "MODIS", "zonal statistics", "NB03"),
    "max_lst": ("Zonal maximum LST.", "C", "MODIS", "zonal statistics", "NB03"),
    "std_lst": ("Standard deviation of zonal LST.", "C", "MODIS", "zonal statistics", "NB03"),
    "p05_lst": ("5th percentile of zonal LST.", "C", "MODIS", "zonal statistics", "NB03"),
    "p95_lst": ("95th percentile of zonal LST.", "C", "MODIS", "zonal statistics", "NB03"),
    "mean_spatial_std": ("Mean within-scene spatial standard deviation of LST.", "C", "MODIS", "zonal statistics", "NB03"),
    "n_images_total": ("MODIS scenes contributing to the period.", "count", "MODIS", "QA screening", "NB03"),
    "n_obs_total": ("Valid pixel observations contributing to the period.", "count", "MODIS", "QA screening", "NB03"),
    "n_strict_total": ("Observations passing the strict QA gate (LST error <= 1 K).", "count", "MODIS", "QA screening", "NB03"),
    "n_moderate_total": ("Observations passing only the moderate QA gate.", "count", "MODIS", "QA screening", "NB03"),
    "pct_strict": ("Share of observations passing the strict QA gate.", "%", "MODIS", "QA screening", "NB03"),
    "pct_valid_obs": ("Share of possible observations that were valid.", "%", "MODIS", "QA screening", "NB03"),
    "n_valid_months": ("Months with at least one valid observation.", "count", "MODIS", "QA screening", "NB03"),
    "pct_valid_months": ("Share of months with a valid observation.", "%", "MODIS", "QA screening", "NB03"),
    "low_coverage": ("True when the year falls below the coverage threshold and is treated as weakly observed.", "", "MODIS", "QA screening", "NB03"),
    "hottest_month": ("Calendar month with the highest zonal LST in that year.", "month", "MODIS", "zonal statistics", "NB03"),
    "coolest_month": ("Calendar month with the lowest zonal LST in that year.", "month", "MODIS", "zonal statistics", "NB03"),
    "n_images": ("MODIS scenes contributing to the month.", "count", "MODIS", "QA screening", "NB03"),
    "n_obs": ("Valid pixel observations in the month.", "count", "MODIS", "QA screening", "NB03"),
    "n_strict": ("Observations in the month passing the strict QA gate.", "count", "MODIS", "QA screening", "NB03"),
    # climatology (derived here)
    "mean_value_c": ("Mean of the monthly zone values across all study years for that calendar month.", "C", "MODIS", "calendar-month mean over the monthly series", "derived by this script from monthly_series"),
    "std_value_c": ("Standard deviation across years for that calendar month.", "C", "MODIS", "calendar-month mean over the monthly series", "derived by this script from monthly_series"),
    "n_years_used": ("Years contributing to the calendar-month mean.", "count", "MODIS", "calendar-month mean", "derived by this script from monthly_series"),
    # trend extremes
    "highest_year": ("Year with the highest zone value in the series.", "year", "MODIS", "series extremes", "NB03"),
    "highest_year_value_c": ("Zone value in the highest year.", "C", "MODIS", "series extremes", "NB03"),
    "lowest_year": ("Year with the lowest zone value in the series.", "year", "MODIS", "series extremes", "NB03"),
    "lowest_year_value_c": ("Zone value in the lowest year.", "C", "MODIS", "series extremes", "NB03"),
    # zone geometry / delineation (NB01)
    "uc_area_km2": ("Urban-core area.", "km2", "GHS-SMOD", "three-zone delineation", "NB01"),
    "bra_area_km2": ("Built-up rural area ring area.", "km2", "GHS-SMOD", "three-zone delineation", "NB01"),
    "cr_area_km2": ("City-region area.", "km2", "GHS-SMOD", "three-zone delineation", "NB01"),
    "bra_uc_ratio": ("Ratio of BRA ring area to urban-core area.", "ratio", "derived", "three-zone delineation", "NB01"),
    "bra_dist_km": ("Radial distance from the urban core at which the BRA ring was fixed.", "km", "derived", "three-zone delineation", "NB01"),
    "bra_converged": ("True when the BRA ring search met its convergence criterion.", "", "derived", "three-zone delineation", "NB01"),
    "bra_coastal": ("True when the BRA ring is truncated by coastline or water.", "", "JRC Global Surface Water", "three-zone delineation", "NB01"),
    "bra_water_frac": ("Fraction of the BRA ring covered by permanent water.", "fraction", "JRC Global Surface Water", "water masking", "NB01"),
    "bra_smod_builtup_frac": ("Fraction of the BRA ring classed as built-up.", "fraction", "GHS-SMOD", "three-zone delineation", "NB01"),
    "bra_effective_area_km2": ("BRA ring area after water and built-up exclusion.", "km2", "derived", "three-zone delineation", "NB01"),
    "smod_epoch_year": ("GHS-SMOD epoch used to delineate the zones.", "year", "GHS-SMOD", "three-zone delineation", "NB01"),
    "uc_flags": ("Delineation flags raised for the urban core.", "", "derived", "three-zone delineation", "NB01"),
    "population_wup_k": ("City population from UN World Urbanization Prospects.", "thousand persons", "UN WUP", "lookup", "NB01"),
    "is_absorbed": ("True when a neighbouring settlement was absorbed into this AoI.", "", "derived", "AoI absorption", "NB01"),
    "absorbed_by": ("Parent AoI when this settlement was absorbed.", "", "derived", "AoI absorption", "NB01"),
    "land_code25": ("PLT typology code, climate-geology-elevation.", "", "derived", "PLT typology", "NB01"),
    # spot / contour attributes (NB05)
    "spot_id": ("Spot key as issued by NB05, unique within a study year.", "", "derived", "keying", "NB05"),
    "spot_uid": ("Year-qualified spot key, study_year and spot_id, unique across study years.", "", "derived", "keying", "this script"),
    "contour_uid": ("Year-qualified contour key, spot_uid and contour level.", "", "derived", "keying", "this script"),
    "city_selection_criterion": ("Rule used to select the city set for this run.", "", "derived", "study design", "recorded at build time"),
    "region": ("Country or region covered by this run.", "", "derived", "study design", "recorded at build time"),
    "scenario_id": ("Eight-character digest of the configuration that produced these rows. Filter on it to isolate one complete run.", "", "derived", "scenario hashing", "config.py via this script"),
    "parameter": ("Configuration parameter name.", "", "derived", "scenario capture", "config.py / src / NB05"),
    "source": ("Where the parameter value was read from.", "", "derived", "scenario capture", "this script"),
    "study_years": ("Study years present in the event-scale layers.", "", "derived", "packaging", "this script"),
    "contour_id": ("Contour key, spot_id and contour level.", "", "derived", "keying", "NB05"),
    "spot_zone": ("Zone the spot falls in: urban_core, bra or both.", "", "derived", "zone intersection", "NB05"),
    "tier": ("Delineation tier: 1 for KDE-delineated spots (>= 10 pixels), 2 for buffered isolated pixels.", "", "SEVIRI", "tier assignment", "NB05 section 6"),
    "n_pixels": ("Validated Gi* pixels in the spot.", "count", "SEVIRI", "Gi* |Z| >= 1.96, Queen contiguity", "NB05"),
    "n_pixels_l75": ("Pixels inside the L75 zone.", "count", "SEVIRI", "Gaussian KDE", "NB05"),
    "n_pixels_l90": ("Pixels inside the L90 dense core.", "count", "SEVIRI", "Gaussian KDE", "NB05"),
    "n_pixels_level": ("Pixels inside this contour level.", "count", "SEVIRI", "Gaussian KDE", "NB05"),
    "area_l50_km2": ("Area of the L50 outer extent.", "km2", "SEVIRI", "Gaussian KDE, Scott's bandwidth", "NB05"),
    "area_l75_km2": ("Area of the L75 inner zone.", "km2", "SEVIRI", "Gaussian KDE, Scott's bandwidth", "NB05"),
    "area_l90_km2": ("Area of the L90 dense core.", "km2", "SEVIRI", "Gaussian KDE, Scott's bandwidth", "NB05"),
    "area_l75_pct": ("L75 area as a share of L50.", "%", "SEVIRI", "Gaussian KDE", "NB05"),
    "area_l90_pct": ("L90 area as a share of L50.", "%", "SEVIRI", "Gaussian KDE", "NB05"),
    "l75_completeness": ("Whether an L75 contour could be delineated for every spot in the group.", "", "SEVIRI", "Gaussian KDE", "NB05"),
    "l90_completeness": ("Whether an L90 contour could be delineated for every spot in the group.", "", "SEVIRI", "Gaussian KDE", "NB05"),
    "dense_core_pct": ("L90 dense core as a share of the L50 footprint.", "%", "SEVIRI", "Gaussian KDE", "NB05"),
    "is_merged_t2": ("True when tier-2 pixels were absorbed into this tier-1 polygon.", "", "SEVIRI", "tier-2 absorption within 2 km", "NB05 section 6d"),
    "n_absorbed_t2": ("Number of tier-2 spots absorbed into this polygon.", "count", "SEVIRI", "tier-2 absorption within 2 km", "NB05 section 6d"),
    "core_mean_lst_c": ("Mean LST inside the L90 dense core.", "C", "SEVIRI", "zonal statistics", "NB05"),
    "core_max_lst_c": ("Maximum LST inside the L90 dense core.", "C", "SEVIRI", "zonal statistics", "NB05"),
    "mean_lst_c": ("Mean LST within the spot footprint.", "C", "SEVIRI", "zonal statistics", "NB05"),
    "std_lst_c": ("Standard deviation of LST within the spot footprint.", "C", "SEVIRI", "zonal statistics", "NB05"),
    "max_lst_c": ("Maximum LST within the spot footprint.", "C", "SEVIRI", "zonal statistics", "NB05"),
    "min_lst_c": ("Minimum LST within the spot footprint.", "C", "SEVIRI", "zonal statistics", "NB05"),
    "pop_l50_persons": ("Resident population within the L50 outer extent.", "persons", "GHS-POP", "zonal sum", "NB05"),
    "nb04_val_tier": ("Quality tier of the NB04 event window underlying the SEVIRI composite.", "", "ERA5-Land", "event selection", "NB04 via NB05"),
    "persistent_dn": ("True when the city shows a persistent day and night anomaly.", "", "SEVIRI", "day-night persistence check", "NB05"),
    # events
    "selection_reason": ("Why this event was chosen for SEVIRI compositing.", "", "ERA5-Land", "event selection", "NB04 event audit"),
    "seviri_scene_available": ("True when a clipped SEVIRI composite exists for the selected window.", "", "MSG-SEVIRI", "scene inventory", "NB04 seviri folder"),
    # city roll-ups
    "validation_tier": ("City-level validation tier rolled up from the selected events.", "", "ERA5-Land", "event selection", "NB05 master_city_composite.csv"),
    "bh_any": ("True when any spot in the city survives BH-FDR control.", "", "SEVIRI", "BH-FDR q = 0.05", "NB05 master_city_composite.csv"),
    # dataset_info
    "key": ("Metadata key.", "", "derived", "packaging", "this script"),
    "value": ("Metadata value.", "", "derived", "packaging", "this script"),
})

# templated field families, resolved by pattern
import re as _re
_PATTERNS = [
    (_re.compile(r"^era5_(day|night)_n_persistent_events$"),
     ("Persistent heat events detected for the {0} period.", "count", "ERA5-Land",
      "P90 threshold, >= 2 consecutive days", "NB04 city_heat_event_summary.csv")),
    (_re.compile(r"^era5_(day|night)_longest_event_days$"),
     ("Longest persistent heat event for the {0} period.", "days", "ERA5-Land",
      "P90 threshold, >= 2 consecutive days", "NB04 city_heat_event_summary.csv")),
    (_re.compile(r"^era5_(day|night)_total_persistent_days$"),
     ("Total days inside persistent heat events for the {0} period.", "days", "ERA5-Land",
      "P90 threshold, >= 2 consecutive days", "NB04 city_heat_event_summary.csv")),
    (_re.compile(r"^era5_(day|night)_n_hot_days$"),
     ("Days above the {0} P90 threshold, whether or not persistent.", "days", "ERA5-Land",
      "P90 threshold", "NB04 city_heat_event_summary.csv")),
    (_re.compile(r"^(day|night)_selected_event_start$"),
     ("Start of the {0} event selected for SEVIRI compositing.", "date", "ERA5-Land",
      "event selection", "NB04 city_heat_event_summary.csv")),
    (_re.compile(r"^(day|night)_selected_event_end$"),
     ("End of the {0} selected event.", "date", "ERA5-Land", "event selection",
      "NB04 city_heat_event_summary.csv")),
    (_re.compile(r"^(day|night)_selected_event_duration_days$"),
     ("Length of the {0} selected event.", "days", "ERA5-Land", "event selection",
      "NB04 city_heat_event_summary.csv")),
    (_re.compile(r"^(day|night)_selected_event_tier$"),
     ("Quality tier of the {0} selected event.", "", "ERA5-Land", "event selection",
      "NB04 city_heat_event_summary.csv")),
    (_re.compile(r"^(day|night)_modis_era5land_n$"),
     ("Paired MODIS and ERA5-Land {0} observations compared.", "count", "MODIS; ERA5-Land",
      "paired comparison on MODIS-valid days", "NB04 city_heat_event_summary.csv")),
    (_re.compile(r"^(day|night)_modis_era5land_r$"),
     ("Pearson r between MODIS and ERA5-Land {0} LST.", "", "MODIS; ERA5-Land",
      "paired comparison", "NB04 city_heat_event_summary.csv")),
    (_re.compile(r"^(day|night)_modis_era5land_r2$"),
     ("Coefficient of determination, MODIS against ERA5-Land, {0}.", "", "MODIS; ERA5-Land",
      "paired comparison", "NB04 city_heat_event_summary.csv")),
    (_re.compile(r"^(day|night)_modis_era5land_bias_c$"),
     ("Mean ERA5-Land minus MODIS {0} difference; positive means ERA5-Land warmer.", "C",
      "MODIS; ERA5-Land", "paired comparison", "NB04 city_heat_event_summary.csv")),
    (_re.compile(r"^(day|night)_modis_era5land_rmse_c$"),
     ("Root mean squared error between MODIS and ERA5-Land {0} LST.", "C", "MODIS; ERA5-Land",
      "paired comparison", "NB04 city_heat_event_summary.csv")),
    (_re.compile(r"^(day|night)_modis_era5land_mae_c$"),
     ("Mean absolute error between MODIS and ERA5-Land {0} LST.", "C", "MODIS; ERA5-Land",
      "paired comparison", "NB04 city_heat_event_summary.csv")),
    (_re.compile(r"^n_(hot|cold)_(day|night)_spots$"),
     ("{0} spots delineated in the {1} period; 0 means none detected.", "count", "SEVIRI",
      "Gi* then KDE delineation", "derived from the spots layer")),
    (_re.compile(r"^n_(hot|cold)_(day|night)_bh_significant$"),
     ("{0} {1} spots surviving BH-FDR control; 0 means none.", "count", "SEVIRI",
      "BH-FDR q = 0.05", "derived from the spots layer")),
]


def describe(field: str):
    if field in DESCR:
        return DESCR[field]
    for pat, (d, unit, sensor, method, prov) in _PATTERNS:
        m = pat.match(field)
        if m:
            return (d.format(*m.groups()), unit, sensor, method, prov)
    return (f"[CHECK] description not yet written for '{field}'.", "", "[CHECK]", "[CHECK]", "[CHECK]")


NULL_MEANING = {
    "area_l75_km2": "L75 not defined for tier-2 spots.",
    "area_l90_km2": "L90 not defined for tier-2 spots.",
    "pop_l75_persons": "L75 not defined for tier-2 spots.",
    "pop_l90_persons": "L90 not defined for tier-2 spots.",
    "selection_reason": "Only populated on the selected event.",
    "seviri_scene_available": "Only evaluated for the selected event.",
    "value_c": "Zone or year with no valid observation.",
    "mk_trend": "Trend not computed (insufficient valid years).",
}


def build_dictionary(layers):
    rows = []
    for lname, df in layers.items():
        if df is None:
            continue
        for f in df.columns:
            s = df[f]
            d, unit, sensor, method, prov = describe(f)
            if d.startswith("[CHECK]"):
                CHECKS.append(f"{lname}.{f}")
            if f == "geometry":
                rng = str(df.geom_type.dropna().unique().tolist()) if hasattr(df, "geom_type") else ""
            elif pd.api.types.is_numeric_dtype(s):
                v = pd.to_numeric(s, errors="coerce").dropna()
                rng = f"{v.min():g} to {v.max():g}" if len(v) else "all null"
            else:
                u = pd.Series(s.dropna().astype(str).unique())
                rng = "; ".join(sorted(u)[:12]) + (" ..." if len(u) > 12 else "") if len(u) else "all null"
            rows.append({"layer": lname, "field": f, "dtype": str(s.dtype), "unit": unit,
                         "description": d, "allowed_values_or_range": rng[:300],
                         "null_meaning": NULL_MEANING.get(f, "Value not available."),
                         "sensor_or_source": sensor, "method_step": method, "provenance": prov})
    return pd.DataFrame(rows)


def dictionary_md(dd: pd.DataFrame) -> str:
    out = ["# Data dictionary", "",
           f"Version {VERSION}. One table per layer. Generated from `data_dictionary.csv`.", ""]
    for lname, g in dd.groupby("layer", sort=False):
        out += [f"## {lname}", "",
                "| field | dtype | unit | description | values / range | null means | source | method | provenance |",
                "|---|---|---|---|---|---|---|---|---|"]
        for _, r in g.iterrows():
            out.append("| `{field}` | {dtype} | {unit} | {description} | {allowed_values_or_range} | "
                       "{null_meaning} | {sensor_or_source} | {method_step} | {provenance} |".format(
                           **{k: str(v).replace("|", "\\|") for k, v in r.items()}))
        out.append("")
    return "\n".join(out)


# ── writing ─────────────────────────────────────────────────────────────────
def write_package(layers, out_dir: Path, with_csv=False, with_geojson=False):
    """One GeoPackage holds every layer, spatial and aspatial alike. CSV and GeoJSON
    copies are opt-in so the published folder stays lean."""
    gpkg = out_dir / f"{DATASET_STEM}.gpkg"
    if gpkg.exists():
        gpkg.unlink()
    csv_dir, gj_dir = out_dir / "csv", out_dir / "geojson"
    for d, want in ((csv_dir, with_csv), (gj_dir, with_geojson)):
        if want:
            d.mkdir(parents=True, exist_ok=True)
    for name, df in layers.items():
        if df is None:
            continue
        spatial = isinstance(df, gpd.GeoDataFrame) and df.geometry.notna().any()
        if spatial:
            pyogrio.write_dataframe(df, gpkg, layer=name, append=gpkg.exists())
            if with_geojson:
                df.to_crs(CRS_WGS84).to_file(gj_dir / f"{name}.geojson", driver="GeoJSON")
        else:
            plain = df.drop(columns="geometry") if "geometry" in getattr(df, "columns", []) else df
            pyogrio.write_dataframe(pd.DataFrame(plain), gpkg, layer=name, append=gpkg.exists())
        if with_csv:
            plain = df.drop(columns="geometry") if "geometry" in getattr(df, "columns", []) else df
            plain.to_csv(csv_dir / f"{name}.csv", index=False, encoding="utf-8",
                         date_format="%Y-%m-%d")
        log(f"  {name:26} {len(df):>7} rows  {len(df.columns):>3} fields{'  [geom]' if spatial else ''}")
    return gpkg


def md5(p: Path) -> str:
    h = hashlib.md5()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


LAYER_ONE_LINER = {
    "city_zones": "Urban-core, BRA ring and city-region polygons for every city.",
    "city_profile": "One record per city, year-independent: PLT classes, zone areas, population, participants.",
    "city_year_summary": "One record per city and study year: ERA5-Land persistence, selected events, sensor comparison, spot counts.",
    "trend_statistics": "Long-term LST trend tests per city, zone and period.",
    "annual_series": "Annual zone values, 2006-2025.",
    "monthly_series": "Monthly zone values, 2006-2025.",
    "monthly_climatology": "Calendar-month means across the study period.",
    "heat_event_catalogue": "Every ERA5-Land persistent heat event, with the selected one flagged.",
    "spot_occurrence": "Spot counts and Gi*/BH-FDR pixel counts on the full city x period x type grid, zeros included.",
    "spots": "One polygon per delineated hot or cold spot (L50 footprint).",
    "spot_contours": "One polygon per KDE contour level (L50, L75, L90), hot and cold spots alike.",
    "stakeholder_spots_gps": "Stakeholder-marked hot and cold spot locations, pseudonymised.",
    "stakeholder_perception": "Perception responses, one row per participant, pseudonymised.",
    "hitrate_sensitivity": "Stakeholder-satellite agreement across buffer distances.",
    "city_exposure_by_contour": "Population exposure by contour level per city, period and spot type.",
    "dataset_info": "Dataset metadata as key/value pairs.",
    "scenario_config": "The configuration behind each scenario_id: city-selection rule, thresholds and method parameters.",
}


def write_readme(layers, out_dir: Path, gpkg: Path):
    def size(p):
        n = p.stat().st_size
        return f"{n/1e6:.1f} MB" if n >= 1e6 else f"{n/1e3:.0f} kB"

    rows = "\n".join(
        f"| `{n}` | {len(d):,} | {LAYER_ONE_LINER.get(n, '')} |"
        for n, d in layers.items() if d is not None)
    files = "\n".join(
        f"| `{p.relative_to(out_dir).as_posix()}` | {size(p)} |"
        for p in sorted(out_dir.rglob("*"))
        if p.is_file() and "_build" not in p.relative_to(out_dir).parts)
    txt = f"""# Dataset and protocol associated with the analysis of the diurnal surface thermal anomalies across 56 Nigerian cities situated in 16 physiographic landscape typologies

Version {VERSION}. Built {date.today().isoformat()}.

Authors: P. S. U. Eneche (ORCID [PENDING]), Y. Zeng (ORCID [PENDING]), F. Atun (ORCID [PENDING]), K. Pfeffer (ORCID [PENDING]).
Contact: P. S. U. Eneche.

## 1. What this dataset contains

**One GeoPackage, {sum(1 for d in layers.values() if d is not None)} layers.** Spatial and attribute-only layers live side by side in the same
file, so there is a single data artefact to cite, download and checksum. CSV and GeoJSON copies
are not shipped; regenerate them at any time with
`python scripts/build_master_summary.py --with-csv --with-geojson`.

| layer | rows | contents |
|---|---|---|
{rows}

## 2. Files

| file | size |
|---|---|
{files}

## 3. Keys and joining

- `city_slug` is the stable city key; `city` is the display name; `cluster25` is the PLT cluster.
- `zone` is one of `uc`, `bra`, `cr`, `suhii`; `period` is `day` or `night`; `spot_type` is `hot` or `cold`; `contour_level` is `L50`, `L75` or `L90`.
- `spot_uid` (study year + spot id) is the key that joins `spots` and `spot_contours`, and stays unique if the protocol is re-run for another year. `spot_id` is kept as issued by NB05 and is unique only within a year.
- `city_slug` joins `city_profile` (year-independent) to `city_year_summary` and every event-scale layer; add `study_year` when more than one year is present.
- `participant_code` joins the two stakeholder layers.

```python
import geopandas as gpd
gpkg = "{DATASET_STEM}.gpkg"
spots  = gpd.read_file(gpkg, layer="spots")                      # polygons
trends = gpd.read_file(gpkg, layer="trend_statistics")           # attribute-only layer
joined = spots.merge(trends.query("zone == 'suhii'"), on=["city_slug", "period"], how="left")
```

## 4. Coordinate reference system and coverage

- GeoPackage: {CRS_ANALYSIS} (Africa Albers Equal Area Conic), the analysis CRS. All areas were computed in it.
- GeoJSON copies: {CRS_WGS84}, per RFC 7946.
- Spatial coverage: Nigeria, about 4-14 N and 2-15 E.
- Temporal coverage: MODIS Aqua MYD11A1 {TREND_FIRST}-{TREND_LAST}; ERA5-Land {STUDY_YEAR}; MSG-SEVIRI composites over the selected {STUDY_YEAR} heat events.

## 5. Input data sources

| source | use | identifier |
|---|---|---|
| MODIS Aqua MYD11A1 | long-term day and night LST | [PENDING-DOI] |
| ERA5-Land | daily LST for persistent heat events | [PENDING-DOI] |
| LSA-SAF MSG-SEVIRI LST | event-scale composites for spot detection | [PENDING-DOI] |
| GHS-SMOD | settlement model for the three-zone delineation | [PENDING-DOI] |
| GHS-POP | population grid for exposure | [PENDING-DOI] |
| JRC Global Surface Water | water masking | [PENDING-DOI] |
| UN World Urbanization Prospects | city population | [PENDING-DOI] |
| PLT typology (Eneche et al., 4TU.ResearchData) | physiographic landscape typology | [PENDING-DOI] |

No DOI is stated unless it was found in the project; all are marked `[PENDING-DOI]`.

## 6. What is deliberately not included

- **Association analysis.** Kruskal-Wallis, Dunn post-hoc, chi-square, effect sizes, forest-plot data and the synthesis association tables belong to the research article.
- **Cluster-level and national aggregates.** They are findings of the article and can be rebuilt from the city-level records with a group-by on `cluster25`.
- **The raw questionnaire.** No free text, names, emails, phone numbers, device identifiers or timestamps. Only the perception items listed in the data dictionary are present.
- **Rasters and per-city intermediates.** Regenerable from the code repository.

## 7. Anonymisation

Participants are identified only by a pseudonymous code, `P001` to `P105`, assigned by sorting on city then original identifier. The mapping back to the original identifiers is held privately by the authors and is not part of this dataset. No free-text response is included. Stakeholder point coordinates are published at their recorded precision of four decimal degrees.

## 8. Licence and citation

Licence: **CC BY 4.0**.

- Dataset: [PENDING-DOI]
- Data in Brief article: [PENDING]
- Sustainable Cities and Society article: [PENDING]
- Code repository: [PENDING-DOI], MIT licence.

## 9. Map disclaimer

Map lines delineate study areas and do not necessarily depict accepted national boundaries.
"""
    (out_dir / "_build" / "README.md").write_text(txt, encoding="utf-8")


def write_changelog(out_dir: Path):
    (out_dir / "_build" / "CHANGELOG.md").write_text(f"""# Changelog

## v{VERSION} — {date.today().isoformat()}

First published version.

### Corrected

- **Persistence fields now come from ERA5-Land.** In the previous aggregation
  (`master_thermal_spots`) the fields `n_persistent_events` and `longest_event_days` carried the
  **MODIS** values on every row, and `n_modis_hot_days` was present. The locked methodological
  decision is that persistence is derived from ERA5-Land only. This dataset reads
  `era5_<period>_n_persistent_events` and `era5_<period>_longest_event_days`, and
  `n_modis_hot_days` has been removed, because the P90 definition fixes the number of hot days
  per year and the MODIS count carries no extra information.
- **Trend statistics restructured.** `sen_slope_C_per_decade`, `mk_p_value` and `mk_trend` were
  attached to each spot record but were the **urban-core** series, not SUHII, which was
  ambiguous. They now live in `trend_statistics` with an explicit `zone` field covering
  `uc`, `bra`, `cr` and `suhii`, and have been removed from the spot records.

### Added

- `heat_event_catalogue`: the ERA5-Land persistent heat events, previously not published.
- Explicit zero rows so that every city, period and spot type appears even where no spot was
  detected.
- `h3_grid`: H3 resolution-8 cells, generated from the L50 footprints.
- `monthly_series` and `monthly_climatology`.
- `city_exposure_halfdonut`: population exposure by contour level.
""", encoding="utf-8")


def write_build_log(layers, dd, out_dir: Path, sources: dict):
    lines = [f"# Phase 2 build log — v{VERSION}", "",
             f"Built {date.today().isoformat()} by `scripts/build_master_summary.py`.", "",
             "## Layers, sources and row counts", "",
             "| layer | rows | fields | built from |", "|---|---|---|---|"]
    for n, d in layers.items():
        if d is None:
            continue
        lines.append(f"| `{n}` | {len(d):,} | {len(d.columns)} | {sources.get(n, '')} |")
    lines += ["", "## Deviations from the target schema", ""]
    lines += [f"- {d}" for d in DEVIATIONS] or ["- none"]
    checks = sorted(set(CHECKS))
    lines += ["", f"## `[CHECK]` items ({len(checks)})", ""]
    lines += [f"- `{c}`" for c in checks] or ["- none"]
    (out_dir / "_build" / "02_build_log.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_checksums(out_dir: Path):
    lines = []
    for p in sorted(out_dir.rglob("*")):
        rel = p.relative_to(out_dir)
        # never checksum the manifest itself: it exists on a rebuild but not on a
        # first build, which would otherwise make the listing non-deterministic
        if p.is_file() and "_build" not in rel.parts:
            lines.append(f"{md5(p)}  {rel.as_posix()}")
    (out_dir / "_build" / "checksums_md5.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(lines)


# ── main ────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(R05 / DATASET_DIR))
    ap.add_argument("--with-csv", action="store_true", help="also write csv/ copies")
    ap.add_argument("--with-geojson", action="store_true", help="also write geojson/ copies")
    args = ap.parse_args()
    out_dir = Path(args.out)
    (out_dir / "_build").mkdir(parents=True, exist_ok=True)

    log(f"Building master summary v{VERSION} -> {out_dir}")
    scenario_id, scen_df = capture_scenario()
    log(f"  scenario_id {scenario_id}  "
        f"({scen_df.set_index('parameter').loc['city_selection_mode', 'value']}, "
        f"study year {scen_df.set_index('parameter').loc['study_year', 'value']})")
    ref = load_reference()
    log(f"  reference: {len(ref)} cities")

    zones = build_city_zones(ref)
    spots = build_spots(ref)
    key = build_participant_key(ref)

    layers = {
        "city_zones": zones,
        "city_profile": build_city_profile(ref, zones),
        "city_year_summary": build_city_year_summary(ref, spots),
        "trend_statistics": build_trend_statistics(ref),
        "annual_series": build_annual_series(ref),
        "monthly_series": None,
        "monthly_climatology": None,
        "heat_event_catalogue": build_heat_events(ref),
        "spot_occurrence": build_spot_occurrence(ref, spots),
        "spots": spots,
        "spot_contours": build_contours(ref),
        "stakeholder_spots_gps": build_gps(ref, key),
        "stakeholder_perception": build_perception(ref, key),
        "hitrate_sensitivity": build_hitrate(ref),
        "city_exposure_by_contour": build_halfdonut(ref),
    }
    layers["monthly_series"], layers["monthly_climatology"] = build_monthly(ref)

    # stamp the scenario on every data layer, then accumulate rather than overwrite
    for _n, _d in layers.items():
        if _d is None or "scenario_id" in getattr(_d, "columns", []):
            continue
        _d["scenario_id"] = scenario_id
        layers[_n] = _d[["scenario_id"] + [c for c in _d.columns if c != "scenario_id"]]
    study_years = {int(y) for y in layers["spots"]["study_year"].dropna().unique()}
    _gpkg_path = out_dir / f"{DATASET_STEM}.gpkg"
    layers = merge_with_existing(layers, _gpkg_path, scenario_id, study_years)
    layers["scenario_config"] = scen_df
    layers["dataset_info"] = build_dataset_info(
        layers, n_cities=len(ref), n_clusters=int(ref["cluster25"].nunique()),
        study_years=sorted({int(y) for y in layers["spots"]["study_year"].dropna().unique()}),
        scenario_id=scenario_id, scen_df=scen_df)

    log("Layers:")
    gpkg = write_package(layers, out_dir, with_csv=args.with_csv,
                         with_geojson=args.with_geojson)

    dd = build_dictionary(layers)
    dd.to_csv(out_dir / "data_dictionary.csv", index=False, encoding="utf-8")
    (out_dir / "data_dictionary.md").write_text(dictionary_md(dd), encoding="utf-8")
    log(f"  data dictionary: {len(dd)} field rows, {len(set(CHECKS))} [CHECK] items")

    # private key, outside the package
    PRIV = ROOT / "private"
    PRIV.mkdir(exist_ok=True)
    key[["participant_code", "pid", "city", "city_slug"]].to_csv(
        PRIV / "participant_key.csv", index=False, encoding="utf-8")
    gi = ROOT / ".gitignore"
    txt = gi.read_text(encoding="utf-8") if gi.exists() else ""
    if "private/" not in txt:
        gi.write_text(txt.rstrip("\n") + "\n\n# participant re-identification key (never commit)\nprivate/\n",
                      encoding="utf-8")
        log("  added 'private/' to .gitignore")

    SOURCES = {
        "city_zones": "NB01 `{slug}_{zone}_102022_v5.geojson` + `zone_area_summary_with_pop.csv`",
        "city_profile": "NB01 `city_cluster25_lookup.csv`, `zone_area_summary_with_pop.csv`, `cluster25_uc_distribution.csv`; NB04 `city_heat_event_summary.csv`; NB05 `master_city_composite.csv`; NB02 `Cities_Stakeholder_Points_2024.geojson`; spot counts from the `spots` layer",
        "trend_statistics": "NB03 `all_cities_temporal_annual.csv` (uc/bra/cr) + `all_cities_delta_annual.csv` (suhii)",
        "annual_series": "NB03 `all_cities_temporal_annual.csv` + `all_cities_delta_annual.csv`",
        "monthly_series": "NB03 `all_cities_temporal_monthly.csv` + `all_cities_delta_monthly.csv`",
        "monthly_climatology": "derived from `monthly_series` (calendar-month mean)",
        "heat_event_catalogue": "NB04 `events/{city}_event_audit.json` (56 files)",
        "spot_occurrence": "NB05 `spot_comprehensive_summary.csv` on a full 56x2x2 grid + counts from `spots`",
        "spots": "NB05 `all_cities_spots.geojson`",
        "spot_contours": "NB05 `master_thermal_spots.gpkg::hotspot_contours` (hot and cold)",
        "stakeholder_spots_gps": "NB05 `master_thermal_spots.gpkg::stakeholder_{hot,cold}spot_gps`, keys only",
        "stakeholder_perception": "NB02 `Stakeholder_Perception_Data_2024.csv` + `workshop_attendees_clean.csv`",
        "hitrate_sensitivity": "NB05 `stakeholder_hitrate_sensitivity.csv`",
        "city_exposure_by_contour": "NB05 `halfdonut_city_summary.csv`",
        "dataset_info": "generated by this script",
        "scenario_config": "config.py, src/daily_analysis_utils.py and NB05 constants, captured at build time",
    }
    DEVIATIONS.extend([
        "Layer count is 16, not the 14 in the target schema. `monthly_series` was added "
        "alongside `monthly_climatology` (both were requested), and `city_exposure_halfdonut` "
        "was added from halfdonut_city_summary.csv.",
        "`spots`: geom_75_wkt and geom_90_wkt were dropped. They averaged ~1.9 kB per row and "
        "the L75/L90 outlines are real geometries in `spot_contours`.",
        "`pct_dominant_class` is taken from NB01 cluster25_uc_distribution.csv (percent of the "
        "urban core in the assigned Cluster25). The like-named field in master_thermal_spots holds "
        "a different, much smaller quantity and was not carried over.",
        "`heat_event_catalogue` covers the 53 cities that recorded at least one ERA5-Land "
        "persistent event. The three cities with none are not given placeholder event rows; "
        "their zero state is carried in city_summary.era5_*_n_persistent_events.",
        "Vector sources are stored in EPSG:4326; they are reprojected to " + CRS_ANALYSIS +
        " for the GeoPackage. Recorded area_km2 values are the originals computed in the "
        "analysis CRS and were not recomputed.",
    ])
    write_readme(layers, out_dir, gpkg)
    write_changelog(out_dir)
    n = write_checksums(out_dir)
    log(f"  checksums: {n} files")
    write_build_log(layers, dd, out_dir, SOURCES)
    log(f"  deviations: {len(DEVIATIONS)} | [CHECK] items: {len(set(CHECKS))}")
    return layers, dd, out_dir


if __name__ == "__main__":
    main()
