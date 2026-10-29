#!/usr/bin/env python
"""
Build the master summary dataset for the 56-city diurnal surface thermal anomaly study.

Reads only outputs that already exist under Results/. This module is the one place the build
logic lives; it has two entry points, the command line below and the last section of NB05,
and both call build_dataset().

Every build goes into a staging folder first (Results/05_hotspot_analysis/_build_staging/)
and is then compared with the deposit by its content fingerprint:

    same fingerprint      -> "reproduced": nothing is touched, staging cleared
    different content     -> QA runs on the staging build. If it passes, the deposit is kept in
                             _superseded_build_<date>/ and replaced by the staging build with all
                             its files; if QA fails, the deposit is not touched.

No version is named here: versions are named on Zenodo only. A deposit is identified by its
content fingerprint, and its CHANGELOG entry is headed by date and fingerprint.

Usage
-----
    python scripts/build_master_summary.py                          # build, compare, update
    python scripts/build_master_summary.py --compare-only           # build and compare only
    python scripts/build_master_summary.py --out <folder>           # another deposit folder
    python scripts/build_master_summary.py --normalise-line-endings # LF text files in --out

Excluded by design: association analysis, cluster/national aggregates, and the
raw questionnaire. See the generated README.md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
from shapely.geometry import Polygon

# ── constants ───────────────────────────────────────────────────────────────
# A deposit is identified by its content fingerprint. The code never names a version: versions
# are named on Zenodo only. build_dataset() rebinds BUILD_DATE for every build.
BUILD_DATE = date.today().isoformat()
# The first public release, as published on Zenodo (record 23050560) and restored, verified
# against its manifest, in Results/05_hotspot_analysis/_archive_v1.0.0/.
V100_LABEL = "1.0.0"
V100_DATE = "2026-09-30"
V100_DOI = "10.5281/zenodo.23050560"  # the version DOI of v1.0.0, not the concept DOI
V100_FINGERPRINT = "9d2f24fb8baf147d59bd3d10e9305cf8710d002917108f74919d9ffd4daf3390"      # content_fingerprint() of that archive (checked by QA)
DATASET_DIR  = "surface_thermal_anomaly_stakeholder_composite"   # published dataset root
DATASET_STEM = "surface_thermal_anomaly_stakeholder_composite"
# The Zenodo record title. Deliberately free of counts and years so it stays stable across
# versions; the scope of each version belongs in the README body and the version notes.
DATASET_TITLE = ("Dataset associated with the analysis of surface thermal anomalies, "
                 "population exposure and stakeholder insights across Nigerian cities")
# Zenodo concept DOI: it resolves to the latest version and lists every version. Checked
# against the Zenodo API on 2026-10-29: record 23050560 (v1.0.0) has conceptrecid 23050559.
# Zenodo assigns each version its own DOI at upload, so no version DOI is stored.
CONCEPT_DOI = "10.5281/zenodo.23050559"
# Build records live OUTSIDE the deposit folder. Everything inside the deposit folder is
# published to Zenodo, so nothing internal may sit there.
BUILD_DIR_NAME = "dataset_build"
# Names are protocol-generic: the instance (region, city set, study years, selection
# rule) is recorded in the dataset_info and scenario_config layers, not in the names.
CRS_ANALYSIS = "ESRI:102022"          # Africa Albers Equal Area Conic
CRS_WGS84 = "EPSG:4326"
GPS_DECIMALS = 3   # ~110 m; see build_gps()
STUDY_YEAR = int(__import__("os").environ.get("LST_STUDY_YEAR", "2024"))  # event-scale year;
                                       # overridden by --study-year / discovered from sources
TREND_FIRST, TREND_LAST = 2006, 2025

ROOT = Path(__file__).resolve().parents[1]
R01 = ROOT / "Results" / "01_aoi_delineation"
R02 = ROOT / "Results" / "02_stakeholder_analysis"
R03 = ROOT / "Results" / "03_temporal_analysis"
R04 = ROOT / "Results" / "04_temporal_analysis_daily"
R05 = ROOT / "Results" / "05_hotspot_analysis"
MASTER_GPKG = R05 / "master_thermal_spots.gpkg"
# the UN WUP 2024 table NB01 used for city selection (config.AOI_DATA_PATHS['cities_csv'])
WUP_CSV = ROOT / "data" / "inputs" / "geospatial_features" / "Major_cities_population_Nigeria_WUP_2025.csv"
# Hand-authored reference input, not a notebook output, so it lives on a TRACKED path:
# it used to sit under docs/, which .gitignore excludes, and a fresh clone could not build.
ABBREV_CSV = ROOT / "data" / "reference" / "abbreviations.csv"
# The published deposit, and the folder every build is written to before any comparison.
DEPOSIT_DIR = R05 / DATASET_DIR
STAGING_DIR = R05 / "_build_staging"
STAGING_MARKER = "_BUILD_STAGING"      # only a folder holding this file is ever cleared
# Content fingerprint: dataset_info rows that describe the build, not the data. `version` was
# carried by builds up to the local build of 2026-10-28 and is excluded so those still compare.
FP_VOLATILE_KEYS = {"build_date", "git_commit", "content_fingerprint", "previous_fingerprint",
                    "version"}
# Written last, after the data has been fingerprinted, always in this order.
IDENTITY_KEYS = ["build_date", "content_fingerprint", "previous_fingerprint"]
FP_FLOAT = ".12g"                      # 12 significant digits, far below any stored precision

ZONE_MAP = {"urban_core": "uc", "bra": "bra", "city_region": "cr", "delta_uc_bra": "suhii"}
ZONE_ORDER = ["uc", "bra", "cr", "suhii"]
PERIODS = ["day", "night"]
SPOT_TYPES = ["hot", "cold"]

LOG: list[str] = []
DEVIATIONS: list[str] = []

# The QA script replaces whatever sits between these two markers in the build report.
QA_BEGIN = "<!-- QA:BEGIN — written by scripts/qa_master_summary.py, do not edit by hand -->"
QA_END = "<!-- QA:END -->"
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


# ── merged (post-absorption) city population ────────────────────────────────
# Step 3 of the zonation protocol absorbs a city whose urban core falls entirely
# inside a larger neighbour and reassigns its population to the parent. population_wup_k
# holds only the parent's OWN figure, so the two fields added here carry the reassigned
# total and the names behind it. Both are read from files; no population is typed in.
def add_merged_population(ref: pd.DataFrame) -> pd.DataFrame:
    wup = (pd.read_csv(WUP_CSV, thousands=",")
           .set_index("City_Name")["2024"].astype(float))          # UN WUP 2024, thousands
    ab = pd.read_csv(R01 / "absorbed_cities.csv")                  # NB01 deduplication step
    missing = sorted(set(ab["absorbed_city"]) - set(wup.index))
    if missing:
        raise SystemExit(f"absorbed cities absent from the UN WUP table: {missing}")

    ab["pop"] = ab["absorbed_city"].map(wup)
    added = ab.groupby("parent_aoi")["pop"].sum()
    names = ab.groupby("parent_aoi")["absorbed_city"].apply(lambda s: "; ".join(sorted(s)))

    ref = ref.copy()
    ref["population_wup_merged_k"] = ref["population_wup_k"] + ref["city"].map(added).fillna(0.0)
    ref["absorbed_cities"] = ref["city"].map(names)                # NaN where nothing was absorbed

    # place both immediately after population_wup_k
    cols = [c for c in ref.columns if c not in ("population_wup_merged_k", "absorbed_cities")]
    i = cols.index("population_wup_k") + 1
    return ref[cols[:i] + ["population_wup_merged_k", "absorbed_cities"] + cols[i:]]


def add_zone_population(ref: pd.DataFrame) -> pd.DataFrame:
    """GHS-POP totals for the three zones, from the native 100 m extraction.

    `population_cr_persons` is the denominator to use for exposure shares. Spots are
    detected across the whole city region and do not respect the urban-core boundary: of
    the 185 L50 footprints only 16 lie wholly inside the UC, 75 wholly inside the BRA, 36
    straddle the two and 8 sit mostly in neither. Mean composition is 20.9% UC, 69.2% BRA,
    9.9% elsewhere in the CR, so UC understates the base and only CR covers every spot.
    """
    zdir = R05 / "population_100m" / "zones"
    files = sorted(zdir.glob("*.csv"))
    if not files:
        CHECKS.append("city_profile.population_{uc,bra,cr}_persons (zone cache absent)")
        for c in ("population_uc_persons", "population_bra_persons", "population_cr_persons"):
            ref[c] = np.nan
        return ref
    z = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    z = z[z["city"].astype(str).isin(set(ref["city"].astype(str)))]
    wide = z.pivot_table(index="city", columns="zone", values="population_100m", aggfunc="first")
    ref = ref.copy()
    for col, zone in (("population_uc_persons", "urban_core"),
                      ("population_bra_persons", "bra"),
                      ("population_cr_persons", "city_region")):
        ref[col] = ref["city"].map(wide[zone]) if zone in wide.columns else np.nan
    cols = [c for c in ref.columns if not c.startswith("population_uc_")
            and not c.startswith("population_bra_") and not c.startswith("population_cr_")]
    i = cols.index("population_wup_merged_k") + 1
    return ref[cols[:i] + ["population_uc_persons", "population_bra_persons",
                           "population_cr_persons"] + cols[i:]]


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
    # bra_dist_km / bra_converged / bra_coastal are fossils of the retired equal-area ring
    # search: all-zero and all-null in the source. is_absorbed / absorbed_by record whether THIS
    # city was absorbed into another, which is False and null for all 56 survivors by
    # construction; the absorption is published in the active direction by absorbed_cities.
    # All five are dropped rather than published empty.
    _drop = ("Cluster25", "Climate_Class", "Geology_Class", "Elevation_Class",
             "bra_dist_km", "bra_converged", "bra_coastal",
             "is_absorbed", "absorbed_by")
    ref = ref.merge(areas.drop(columns=[c for c in _drop if c in areas.columns]),
                    on="city", how="left")
    ref = add_merged_population(ref)
    ref = add_zone_population(ref)
    # percent of the urban core occupied by the assigned Cluster25
    ucd = pd.read_csv(R01 / "cluster25_uc_distribution.csv").rename(columns={"City Region": "city"})
    pct = []
    for _, r in ref.iterrows():
        row = ucd[ucd["city"] == r["city"]]
        col = f"C{int(r['cluster25'])}" if pd.notna(r["cluster25"]) else None
        pct.append(float(row.iloc[0][col]) if len(row) and col in ucd.columns else np.nan)
    ref["pct_dominant_class"] = pct

    # A6: the same share measured on the CITY REGION, which is the zone the cluster was
    # assigned on. pct_dominant_class measures that cluster inside the urban core instead,
    # so the two differ and neither alone describes the assignment.
    crd = R01 / "cluster25_cr_distribution.csv"
    if crd.exists():
        crdf = pd.read_csv(crd).rename(columns={"City Region": "city"})
        pct_cr = []
        for _, r in ref.iterrows():
            row = crdf[crdf["city"] == r["city"]]
            col = f"C{int(r['cluster25'])}" if pd.notna(r["cluster25"]) else None
            pct_cr.append(float(row.iloc[0][col]) if len(row) and col in crdf.columns else np.nan)
        ref["pct_assigned_class_cr"] = pct_cr
    else:
        CHECKS.append("city_profile.pct_assigned_class_cr (CR distribution CSV absent)")
        ref["pct_assigned_class_cr"] = np.nan
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
        ("jrc_occurrence_threshold_pct", getattr(cfg, "JRC_OCCURRENCE_THRESHOLD", None), "config.py"),
        ("jrc_min_water_area_m2", getattr(cfg, "JRC_MIN_WATER_AREA_M2", None), "config.py"),
        ("event_percentile", _DEFAULT_PERCENTILE, "src/daily_analysis_utils.py _DEFAULT_PERCENTILE"),
        ("event_min_consecutive_days", _DEFAULT_PERSISTENT, "src/daily_analysis_utils.py _DEFAULT_PERSISTENT"),
        ("gistar_z_hot", 1.96, "NB05 GISTAR_Z_HOT"),
        ("gistar_z_cold", -1.96, "NB05 GISTAR_Z_COLD"),
        ("bh_fdr_alpha", getattr(cfg, "HOTSPOT_FDR_ALPHA", 0.05), "NB05 FDR_ALPHA"),
        ("kde_contour_levels", str(getattr(cfg, "KDE_CONTOUR_LEVELS", [0.50, 0.75, 0.90])), "NB05 KDE_CONTOURS"),
        # NB: the method is a MAPPED reduceRegion, not reduceRegions. reduceRegions counts
        # a pixel once per part of a multi-part geometry and came out 2.0% high on a test
        # zone, so the label states what actually runs.
        ("ghs_pop_extraction", "mapped reduceRegion sum, native 100 m grid, fractional overlap",
         "scripts/extract_population_100m.py"),
        ("ghs_pop_display_raster", "1 km, mean x pixelArea/1e4",
         "src/data_io.py download_ghsl_population_raster (display only)"),
        ("gps_coordinate_decimals", GPS_DECIMALS, "this script (privacy coarsening)"),
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
                         (f"{p_}_corr_bias", f"{p_}_era5land_minus_modis_bias_c"),
                         (f"{p_}_corr_rmse", f"{p_}_modis_era5land_rmse_c"),
                         (f"{p_}_corr_mae", f"{p_}_modis_era5land_mae_c")):
            df[dst] = df["city"].map(ce.set_index("city")[src]) if src in ce.columns else np.nan

    # A3: the MSG-SEVIRI three-zone event composite, copied from NB04 without recomputation.
    # These are the values the event-scale SUHII in `spots` is built on, so publishing them
    # lets a reader reproduce that column and Supplementary Figure S7.2 from the package.
    sev3 = R04 / "seviri" / "City_SEVIRI_3zone_SUHII.csv"
    if sev3.exists():
        s3 = pd.read_csv(sev3)
        for p_ in ("day", "night"):
            sub = s3[s3["period"] == p_].set_index("city")
            for src, dst in (("uc_lst_mean", f"{p_}_seviri_uc_mean_c"),
                             ("bra_lst_mean", f"{p_}_seviri_bra_mean_c"),
                             ("cr_lst_mean", f"{p_}_seviri_cr_mean_c"),
                             ("suhii", f"{p_}_seviri_suhii_c")):
                df[dst] = df["city"].map(sub[src]) if src in sub.columns else np.nan
    else:
        CHECKS.append("city_year_summary.*_seviri_{uc,bra,cr}_mean_c (3-zone CSV absent)")
        for p_ in ("day", "night"):
            for suf in ("uc_mean_c", "bra_mean_c", "cr_mean_c", "suhii_c"):
                df[f"{p_}_seviri_{suf}"] = np.nan

    # A3: the ERA5-Land event mean -- the mean of the daily urban-core medians across the
    # days of the selected event. This is the quantity *_seviri_minus_era5land_bias_c is
    # measured against, so publishing it makes that bias reproducible from the package.
    _ev = _selected_event_windows()
    for p_ in ("day", "night"):
        df[f"{p_}_era5land_event_mean_c"] = df["city"].map(
            lambda c, _p=p_: _era5land_event_mean(c, _p, _ev))

    # MSG-SEVIRI against ERA5-Land over the selected event window, read as computed by NB04
    # §11a; nothing is recomputed here. Bias is SEVIRI urban-core mean minus the mean of the
    # ERA5-Land daily urban-core medians across the event days, so positive means SEVIRI warmer.
    sev_csv = R04 / "correlation" / "SEVIRI_vs_ERA5_target_metrics.csv"
    if sev_csv.exists():
        sev = pd.read_csv(sev_csv).set_index("city")
        for p_ in ("day", "night"):
            for src, dst in ((f"{p_}_n_obs", f"{p_}_seviri_era5land_n"),
                             (f"{p_}_bias", f"{p_}_seviri_minus_era5land_bias_c"),
                             (f"{p_}_rmse", f"{p_}_seviri_era5land_rmse_c"),
                             (f"{p_}_mae", f"{p_}_seviri_era5land_mae_c")):
                df[dst] = df["city"].map(sev[src]) if src in sev.columns else np.nan
    else:
        CHECKS.append("city_year_summary.*_seviri_era5land_* (source CSV absent)")
        for p_ in ("day", "night"):
            for suf in ("n", "rmse_c", "mae_c"):
                df[f"{p_}_seviri_era5land_{suf}"] = np.nan
            df[f"{p_}_seviri_minus_era5land_bias_c"] = np.nan

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

    # validation_tier and bh_any are derived here. They used to be read from NB05's
    # master_city_composite.csv, which no notebook cell writes any more; both rules were
    # checked against that file for the 55 cities it holds, with zero differences
    # (docs/scs_rebuild/WORKLOG.md, 2026-10-29). The file has no row for Ikare, the city with
    # no spots, so Ikare's values come from the same rules here as everyone else's.
    # validation_tier: the day and night selected-event tiers joined day-first, e.g.
    # 'EXCELLENT/GOOD'. A pair, not a ranked grade.
    def _tier_pair(a, b):
        a = str(a).strip() if isinstance(a, str) and str(a).strip() else None
        b = str(b).strip() if isinstance(b, str) and str(b).strip() else None
        return f"{a}/{b}" if a and b else np.nan
    df["validation_tier"] = [_tier_pair(r.day_selected_event_tier, r.night_selected_event_tier)
                             for r in df.itertuples()]
    # bh_any: 1 when any spot group of the city (city x period x spot type) survives BH-FDR
    # control, 0 when none does. spots.bh_significant is that group-level flag, repeated on
    # each spot. A city with no spots has no group to test and stays null, as published.
    _bh_any = (sy.assign(_b=sy["bh_significant"].astype(str).str.lower().isin(["true", "1"]))
               .groupby("city_slug")["_b"].any())
    df["bh_any"] = df["city_slug"].map(_bh_any).map({True: 1.0, False: 0.0}).astype(float)
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


# ── A3 helpers: the ERA5-Land mean over the selected event window ───────────
# NB04 section 11a computes the SEVIRI-minus-ERA5-Land bias as
#   seviri_uc_mean - mean(ERA5-Land daily urban-core medians within [start, end])
# The second term was never published, so the bias could not be reproduced from the
# package. These helpers recreate that term from the same daily CSVs and event windows.
_ERA5_COL = {"day": "day_lst_median", "night": "night_lst_median"}


def _selected_event_windows() -> dict:
    """{(city, period): (start, end)} for the event chosen for SEVIRI compositing."""
    ce = pd.read_csv(R04 / "city_heat_event_summary.csv")
    out = {}
    for r in ce.itertuples():
        for p in ("day", "night"):
            st, en = getattr(r, f"{p}_sel_start", None), getattr(r, f"{p}_sel_end", None)
            if pd.notna(st) and pd.notna(en):
                out[(str(r.city), p)] = (pd.to_datetime(st), pd.to_datetime(en))
    return out


def _era5land_event_mean(city: str, period: str, windows: dict) -> float:
    """Mean ERA5-Land daily urban-core median across the selected event days."""
    win = windows.get((str(city), period))
    if win is None:
        return np.nan
    # NB04 names these files with the city's display name, spaces and all, whereas it names
    # the event audit JSONs with underscores. Accept both rather than assume either: the
    # underscore assumption silently lost Ado Ekiti, Benin City and Port Harcourt.
    base = R04 / "raw_extractions"
    f = next((p for p in (base / f"{city}_ERA5_UC_daily_{STUDY_YEAR}.csv",
                          base / f"{str(city).replace(' ', '_')}_ERA5_UC_daily_{STUDY_YEAR}.csv")
              if p.exists()), None)
    if f is None:
        CHECKS.append(f"era5land_event_mean: no daily ERA5 file for {city}")
        return np.nan
    d = pd.read_csv(f, parse_dates=["date"])
    col = _ERA5_COL[period]
    if col not in d.columns:
        return np.nan
    v = d[(d["date"] >= win[0]) & (d["date"] <= win[1])][col]
    v = pd.to_numeric(v, errors="coerce").dropna()
    return float(v.mean()) if len(v) else np.nan


def build_composite_trends(annual: pd.DataFrame) -> pd.DataFrame:
    """Cluster and national composites of the annual series (DiB eq. 17).

    Each composite is the UNWEIGHTED mean of its member cities for a given year, zone and
    period; the same four-layer protocol as trend_statistics is then run on that series.
    Verified in two stages before use: temporal_analysis.run_trend_analysis reproduces all
    448 rows of the released trend_statistics exactly, and these composites reproduce the
    128 rows of NB03's Cluster25_Annual_Stats.csv and Cluster25_SUHII_Stats.csv to 1e-5.
    """
    sys.path.insert(0, str(ROOT / "src"))
    from temporal_analysis import run_trend_analysis

    rows = []
    for (cl, z, p), g in annual.groupby(["cluster25", "zone", "period"]):
        srs = g.groupby("year")["value_c"].mean().sort_index()
        rows.append({"composite_type": "cluster", "composite_key": f"C{int(cl)}",
                     "cluster25": int(cl), "zone": z, "period": p,
                     "n_cities": int(g["city"].nunique()), **run_trend_analysis(srs, mode="annual")})
    for (z, p), g in annual.groupby(["zone", "period"]):
        srs = g.groupby("year")["value_c"].mean().sort_index()
        rows.append({"composite_type": "national", "composite_key": "national",
                     "cluster25": np.nan, "zone": z, "period": p,
                     "n_cities": int(g["city"].nunique()), **run_trend_analysis(srs, mode="annual")})

    t = pd.DataFrame(rows).rename(columns={
        "n": "n_years", "mk_p": "mk_p_value",
        "sen_slope_per_decade": "sen_slope_c_per_decade",
        "sen_slope_per_year": "sen_slope_c_per_year",
        "ljungbox_pvalue": "ljungbox_p_value"})
    t["mk_method"] = np.where(t["autocorr_corrected"].astype(str).str.lower().isin(["true", "1"]),
                              "Hamed-Rao variance correction", "original Mann-Kendall")
    t["zone"] = pd.Categorical(t["zone"], ZONE_ORDER, ordered=True)
    cols = ["composite_type", "composite_key", "cluster25", "zone", "period", "n_cities",
            "n_years", "mk_method", "mk_z", "mk_p_value", "mk_trend", "autocorr_corrected",
            "lag1_autocorr", "ljungbox_p_value", "sen_slope_c_per_year",
            "sen_slope_c_per_decade", "intercept", "ols_slope", "ols_r_squared", "ols_p_value"]
    t = t[[c for c in cols if c in t.columns]]
    t = t.sort_values(["composite_type", "composite_key", "zone", "period"]).reset_index(drop=True)
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
        # NB04 writes these as city.replace(' ', '_') + '_event_audit.json'. Matching on the
        # display name silently lost the three cities whose names contain a space -- Ado Ekiti,
        # Benin City and Port Harcourt -- even though all three have events. 37 events were
        # missing from the catalogue as a result.
        f = R04 / "events" / f"{city.replace(' ', '_')}_event_audit.json"
        if not f.exists():
            CHECKS.append(f"heat_event_catalogue: no audit file for {city}")
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
                   "pct_dominant_class", "pct_assigned_class_cr", "city_area_km2", "uc_area_km2", "bra_area_km2",
                   "sen_slope_C_per_decade", "mk_p_value", "mk_trend",
                   "n_modis_hot_days", "n_persistent_events", "longest_event_days",
                   "h3_cells_json", "h3_cell_count",   # legacy columns, never populated
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


# ── layers 12-13: stakeholder (pseudonymised) ───────────────────────────────
ALLOWED_PERCEPTION = {"61_temp_increase_10yrs": "perceived_warming_10yr",
                      "60_diurnal_severity_heat": "perceived_diurnal_severity",
                      "58_temp_peak_city": "perceived_peak_period",
                      "56_recency_with_city": "recency_of_contact_with_city"}


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
    # The warming and diurnal items already carry "I'd rather not say" as a stored
    # answer option, so a blank peak-period answer is harmonised to the same value
    # rather than left null. The three perception items then share one vocabulary.
    _n_blank = int(df["perceived_peak_period"].isna().sum())
    if _n_blank:
        df["perceived_peak_period"] = df["perceived_peak_period"].fillna(
            "I'd rather not say")
        DEVIATIONS.append(
            f"stakeholder_perception.perceived_peak_period: {_n_blank} blank answer(s) "
            "stored as \"I'd rather not say\", the same value the other two perception "
            "items use for a blank, so the three share one vocabulary.")
    # The recency item is harmonised the same way, so no perception item carries a null.
    _n_blank = int(df["recency_of_contact_with_city"].isna().sum())
    if _n_blank:
        df["recency_of_contact_with_city"] = df["recency_of_contact_with_city"].fillna(
            "I'd rather not say")
        DEVIATIONS.append(
            f"stakeholder_perception.recency_of_contact_with_city: {_n_blank} blank answer(s) "
            "stored as \"I'd rather not say\", as for the other three perception items.")
    out = df[["participant_code", "city_slug", "city", "cluster25",
              "perceived_warming_10yr", "perceived_diurnal_severity",
              "perceived_peak_period", "recency_of_contact_with_city"]]
    return out.sort_values("participant_code").reset_index(drop=True)


def _gps_frame(src) -> gpd.GeoDataFrame:
    """A stakeholder GPS table as NB05 §10 writes it: points from long_spot/lat_spot, EPSG:4326."""
    if isinstance(src, gpd.GeoDataFrame) and src.geometry.notna().any():
        return src
    return gpd.GeoDataFrame(src.copy(), crs=CRS_WGS84,
                            geometry=gpd.points_from_xy(src["long_spot"], src["lat_spot"]))


def build_gps(ref, key, zones=None, sources=None):
    """The published stakeholder points. `sources` = {"hot": df, "cold": df} supplies NB05's
    in-memory tables (the ones §10 writes to the working GeoPackage); by default the build
    reads them back from that GeoPackage."""
    codes = key.set_index("pid")["participant_code"]
    frames = []
    for layer, t in (("stakeholder_hotspot_gps", "hot"), ("stakeholder_coldspot_gps", "cold")):
        g = (_gps_frame(sources[t]) if sources is not None
             else gpd.read_file(MASTER_GPKG, layer=layer))
        g = g[["pid", "matched_city_y", "geometry"]].copy()
        g["spot_type"] = t
        frames.append(g)
    g = pd.concat(frames, ignore_index=True)
    before = len(g)
    # Keep only the analysed cohort. Registration is the auditable record of participation,
    # so a respondent with attendance data but no registration entry is excluded as
    # unverifiable — see "Participant cohort" in the build report.
    g = g[g["pid"].isin(codes.index)].copy()
    dropped = before - len(g)
    if dropped:
        DEVIATIONS.append(
            f"stakeholder_spots_gps: dropped {dropped} point(s) belonging to respondent(s) outside "
            f"the analysed cohort of {len(codes)} (no registration record, so participation could "
            f"not be verified). Result {len(g)} points, not the 97 in the unfiltered source.")
    g["participant_code"] = g["pid"].map(codes)
    g["city"] = g["matched_city_y"].map(clean_city)
    g["city_slug"] = g["city"].map(slugify)
    g["cluster25"] = g["city"].map(ref.set_index("city")["cluster25"])
    g["study_year"] = STUDY_YEAR
    # Coarsen to 3 decimal degrees (~110 m) to lower re-identification risk. Measured
    # displacement is mean 43 m / max 79 m, and it flips no hit/miss outcome at the
    # smallest published buffer (500 m), so the corroboration analysis is unaffected.
    g = gpd.GeoDataFrame(g, geometry="geometry", crs=CRS_WGS84)
    g["geometry"] = gpd.points_from_xy(g.geometry.x.round(GPS_DECIMALS),
                                       g.geometry.y.round(GPS_DECIMALS), crs=CRS_WGS84)
    out = gpd.GeoDataFrame(
        g[["participant_code", "city_slug", "city", "cluster25", "spot_type", "study_year",
           "geometry"]], geometry="geometry", crs=CRS_WGS84).to_crs(CRS_ANALYSIS)

    # A4: where does the point actually fall? `city` is the study city the participant
    # ANSWERED for, which need not be the city whose region contains the mark. City regions
    # are bounding boxes and can overlap, so the participant's own city takes precedence;
    # that resolves every overlap here (3 points lie in two regions, and in all three one of
    # them is the participant's own city), leaving the assignment deterministic.
    out["in_city_region"] = False
    out["containing_city"] = ""
    if zones is not None:
        cr = zones[zones["zone"] == "cr"].to_crs(CRS_ANALYSIS)
        by_city = {r.city: r.geometry for r in cr.itertuples()}
        inside, holder = [], []
        for r in out.itertuples():
            own = by_city.get(r.city)
            if own is not None and own.covers(r.geometry):
                inside.append(True); holder.append(r.city); continue
            others = sorted(c for c, geom in by_city.items() if geom.covers(r.geometry))
            inside.append(False); holder.append(others[0] if others else "")
        out["in_city_region"] = inside
        out["containing_city"] = holder
    else:
        CHECKS.append("stakeholder_spots_gps.in_city_region / containing_city (zones not supplied)")
    return out.sort_values(["participant_code", "spot_type"]).reset_index(drop=True)


# ── layers 14-15 ────────────────────────────────────────────────────────────
def build_hitrate(ref, spots, gps):
    """Derive the hit rates from the two layers this package publishes.

    Not read from a notebook CSV. The points are the RELEASED coordinates, rounded to
    GPS_DECIMALS before they reach this function, so the published hit rates can be
    reproduced from the dataset alone. Previously the layer was copied from a CSV that
    NB05 wrote from unrounded points, which made the published value depend on something
    the dataset does not contain.
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from compute_hitrate import hit_rate_table, ANALYSIS_CRS

    pts = gps.to_crs(ANALYSIS_CRS) if gps.crs else gps
    sp = spots.to_crs(ANALYSIS_CRS) if spots.crs else spots
    d = hit_rate_table(pts, sp)
    d["city_slug"] = d["city"].map(slugify)
    d["cluster25"] = d["city"].map(ref.set_index("city")["cluster25"])
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
        ("title", DATASET_TITLE),
        ("build_date", BUILD_DATE),
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
        ("concept_doi", CONCEPT_DOI),
        ("content_fingerprint", ""),     # filled once the data is written and read back
        ("previous_fingerprint", ""),
    ]
    # Package-level totals, so a reader can check a download is complete without opening
    # every layer. The GeoPackage holds the data layers plus this table, so n_layers and
    # n_fields_total count dataset_info as well (its own two fields, key and value), which
    # makes them agree with the table list and with the data dictionary. n_records_total
    # counts the data layers only: this table cannot count its own rows.
    _live = {n: d for n, d in layers.items() if d is not None and n != "dataset_info"}
    rows += [("n_layers", str(len(_live) + 1)),
             ("n_data_layers", str(len(_live))),
             ("n_records_total", str(sum(len(d) for d in _live.values()))),
             ("n_fields_total", str(sum(len(d.columns) for d in _live.values()) + 2)),
             ("n_geometry_layers", str(sum(1 for d in _live.values()
                                          if getattr(d, "geometry", None) is not None)))]
    rows += [("scenario_ids_in_package", "see the scenario_config layer")]
    rows += [(f"rows_{n}", str(len(d))) for n, d in layers.items() if d is not None]
    return pd.DataFrame(rows, columns=["key", "value"])


# ── data dictionary ─────────────────────────────────────────────────────────
DESCR = {
    "city_slug": ("Stable city key, as used in the AoI file names.", "", "derived", "keying", "NB01 AoI file names"),
    "city": ("City display name.", "", "derived", "keying", "NB01 study_cities_final.csv"),
    "cluster25": ("Physiographic landscape typology (PLT) cluster identifier.", "", "derived", "PLT typology overlay", "NB01 city_cluster25_lookup.csv"),
    "zone": ("Spatial zone: uc urban core, bra background reference area, cr city region, suhii the urban-core minus BRA difference.", "", "derived", "three-zone delineation", "NB01 AoI v5"),
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
    "pct_dominant_class": ("Share of the URBAN CORE occupied by the cluster assigned to this city. The cluster itself is assigned on the CITY REGION, by largest intersection area, so this is a cross-tabulation of two zones and can be small: Abeokuta is 8.5%, where its assigned C9 is not among the top three clusters of its urban core. See pct_assigned_class_cr for the share in the zone the assignment was made on.", "%", "derived", "zonal composition", "NB01 cluster25_uc_distribution.csv"),
    "pct_assigned_class_cr": ("Share of the CITY REGION occupied by the cluster assigned to this city. This is the zone the assignment is made on, so it is the figure that justifies the assignment.", "%", "derived", "zonal composition", "NB01 cluster25_cr_distribution.csv"),
    "composite_type": ("Whether the composite is a Cluster25 group or the national set of all study cities.", "", "derived", "composite trend", "derived from the annual_series layer"),
    "composite_key": ("Identifier of the composite: C<n> for a Cluster25 group, or `national`.", "", "derived", "composite trend", "derived from the annual_series layer"),
    "n_cities": ("Cities averaged into this composite for the given zone and period.", "count", "derived", "composite trend", "derived from the annual_series layer"),
    "n_years": ("Number of years in the trend test.", "years", "MODIS", "Mann-Kendall", "NB03"),
    "mk_method": ("Mann-Kendall variant applied.", "", "MODIS", "original Mann-Kendall or Hamed-Rao variance correction", "NB03"),
    "mk_z": ("Mann-Kendall Z statistic.", "", "MODIS", "Mann-Kendall", "NB03"),
    "mk_p_value": ("Mann-Kendall two-sided p-value.", "", "MODIS", "Mann-Kendall", "NB03"),
    "mk_trend": ("Trend label: increasing, decreasing or no trend.", "", "MODIS", "Mann-Kendall", "NB03"),
    "autocorr_corrected": ("True when the Hamed-Rao correction was applied.", "", "MODIS", "Ljung-Box then Hamed-Rao", "NB03"),
    "lag1_autocorr": ("Lag-1 Pearson correlation of the series with itself shifted by one year. The Ljung-Box test reported alongside uses the sample autocorrelation function, whose lag-1 value is slightly smaller, so the two do not agree exactly.", "", "MODIS", "autocorrelation", "NB03"),
    "ljungbox_p_value": ("Ljung-Box test p-value for serial correlation.", "", "MODIS", "Ljung-Box", "NB03"),
    "sen_slope_c_per_year": ("Theil-Sen slope per year.", "C/yr", "MODIS", "Theil-Sen", "NB03"),
    "sen_slope_c_per_decade": ("Theil-Sen slope per decade.", "C/decade", "MODIS", "Theil-Sen", "NB03"),
    "intercept": ("Theil-Sen intercept.", "C", "MODIS", "Theil-Sen", "NB03"),
    "ols_slope": ("Ordinary least squares slope per year.", "C/yr", "MODIS", "OLS", "NB03"),
    "ols_r_squared": ("OLS coefficient of determination.", "", "MODIS", "OLS", "NB03"),
    "ols_p_value": ("OLS slope p-value.", "", "MODIS", "OLS", "NB03"),
    "value_c": ("Monthly value for this city, zone and period: the spatial median across the zone of the per-pixel monthly median. For the annual series this is the annual value.", "C", "MODIS", "zonal statistics", "NB03"),
    "event_id": ("Event key: city_slug, period and start date.", "", "derived", "keying", "NB04 event audit"),
    "start_date": ("First day of the persistent heat event.", "date", "ERA5-Land", "P90 threshold, >= 2 consecutive days", "NB04 event audit"),
    "end_date": ("Last day of the persistent heat event.", "date", "ERA5-Land", "P90 threshold, >= 2 consecutive days", "NB04 event audit"),
    "duration_days": ("Event length.", "days", "ERA5-Land", "P90 threshold, >= 2 consecutive days", "NB04 event audit"),
    # NB: "tier" means the event quality tier here and the delineation tier in `spots`, so both
    # live in LAYER_DESCR / DESCR respectively — see LAYER_DESCR above.
    "is_selected": ("True for the event chosen for SEVIRI compositing.", "", "ERA5-Land", "event selection", "NB04 event audit"),
    "era5_p90_threshold_c": ("City and period specific 90th percentile of the ERA5-Land daily LST series.", "C", "ERA5-Land", "P90 threshold", "NB04 event audit"),
    "n_spots": ("Number of delineated spots.", "count", "SEVIRI", "Gi* |Z| >= 1.96 then KDE delineation", "NB05"),
    "n_tier1": ("Tier-1 spots delineated by KDE (>= 10 validated pixels).", "count", "SEVIRI", "KDE delineation", "NB05 section 6"),
    "n_tier2": ("Tier-2 spots, those with 1 to 9 validated pixels, which are too few for a KDE surface. Each is represented by a 500 m buffer around every one of its pixels, simplified at a 50 m tolerance, which makes a near-octagon of about 0.71 km2 per isolated pixel.", "count", "SEVIRI", "tier-2 buffering", "NB05 section 6"),
    "n_bh_significant": ("Spots surviving the BH-FDR control.", "count", "SEVIRI", "BH-FDR q = 0.05", "NB05"),
    "n_gistar_pixels": ("Pixels passing the Gi* significance test.", "count", "SEVIRI", "Gi* |Z| >= 1.96, Queen contiguity", "NB05 spot_comprehensive_summary.csv"),
    "n_bh_fdr_pixels": ("Pixels surviving BH-FDR control.", "count", "SEVIRI", "BH-FDR q = 0.05", "NB05 spot_comprehensive_summary.csv"),
    "bh_significant": ("Whether the GROUP this spot belongs to (city x period x spot type) survived Benjamini-Hochberg FDR control, repeated on every spot of that group.", "", "SEVIRI", "BH-FDR q = 0.05", "NB05"),
    "population_persons": ("Resident population within the L50 footprint, GHS-POP summed on its native 100 m grid with fractional overlap. Express as a share of population_cr_persons in city_profile; see that field for why the city region is the right denominator.", "persons", "GHS-POP", "zonal sum at 100 m", "GHS-POP P2023A epoch 2025"),
    "pop_l75_persons": ("Resident population within the L75 zone, GHS-POP summed on its native 100 m grid with fractional overlap.", "persons", "GHS-POP", "zonal sum at 100 m", "GHS-POP P2023A epoch 2025"),
    "pop_l90_persons": ("Resident population within the L90 dense core, GHS-POP summed on its native 100 m grid with fractional overlap.", "persons", "GHS-POP", "zonal sum at 100 m", "GHS-POP P2023A epoch 2025"),
    "suhii_event_c": ("Event-scale surface urban heat island intensity, urban core minus BRA.", "C", "SEVIRI", "zonal mean difference", "NB05"),
    "participant_code": ("Pseudonymous participant code, P001 to P105.", "", "stakeholder", "pseudonymisation", "NB02, remapped here"),
    "perceived_warming_10yr": ("Perceived temperature increase over the last ten years.", "", "stakeholder", "questionnaire item 61", "NB02"),
    "perceived_diurnal_severity": ("Period in which heat is felt most severely.", "", "stakeholder", "questionnaire item 60", "NB02"),
    "perceived_peak_period": ("Months perceived as the city's temperature peak.", "", "stakeholder", "questionnaire item 58", "NB02"),
    "in_city_region": ("True when the marked point falls inside the city region of the city the participant answered for. False when it falls elsewhere, which is not an error: participants were asked about a city, not about where they were standing.", "", "derived", "point-in-polygon", "city_zones (cr) in this package"),
    "containing_city": ("The study city whose city region contains the point, or empty when no study city's does. Equals `city` when in_city_region is true. PRECEDENCE RULE: city regions are bounding boxes and can overlap, so a point can fall in more than one. Where it does, the participant's own city wins; only if the own city is not among them is the single containing city used. Three of the 94 points lie in two city regions - one Abuja point also inside Madalla, and two Port Harcourt points also inside Abonnema - and the own city is one of the two in all three, so the rule resolves every overlap in this release and never has to choose between two foreign cities.", "", "derived", "point-in-polygon", "city_zones (cr) in this package"),
    "recency_of_contact_with_city": ("How recently the participant was in touch with the city. A participant who did not answer is recorded as \"I'd rather not say\", as for the other three perception items.", "", "stakeholder", "questionnaire item 56", "NB02"),
    "buffer_m": ("Buffer radius applied around stakeholder-marked points.", "m", "derived", "buffer sensitivity", "NB05"),
    "n_hit": ("Rows of the point-to-footprint join that fall inside a spot at this buffer, for the 105-participant cohort. A point inside several footprints contributes several rows.", "count", "derived", "buffer sensitivity", "scripts/compute_hitrate.py"),
    "n_total": ("Rows of the point-to-footprint join at this buffer, for the 105-participant cohort (94 points, 55 hot / 39 cold). A point inside no footprint contributes one row, so n_total is a row count and grows with buffer distance.", "count", "derived", "buffer sensitivity", "scripts/compute_hitrate.py"),
    "hit_rate": ("n_hit divided by n_total, on the cohort basis. Computed from the released point coordinates in stakeholder_spots_gps, which are rounded to three decimal degrees, so these values are reproducible from this dataset alone.", "fraction", "derived", "buffer sensitivity", "scripts/compute_hitrate.py"),
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
    "n_obs": ("Images contributing to this month, counted as images with at least one valid pixel in the CITY REGION. It is not a count of pixel observations, and it is not zone-specific, so a zone can carry a value where n_obs is 0: six zone-months do, in Gboko, Ogbomosho and Warri.", "count", "MODIS", "QA screening", "NB03"),
    "n_strict": ("Images whose pixels passed the strict quality tier, counted the same way as n_obs: images with at least one valid pixel in the city region, not pixel observations.", "count", "MODIS", "QA screening", "NB03"),
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
    "bra_area_km2": ("Area of the background reference area (BRA).", "km2", "GHS-SMOD", "three-zone delineation", "NB01"),
    "cr_area_km2": ("City-region area.", "km2", "GHS-SMOD", "three-zone delineation", "NB01"),
    "bra_uc_ratio": ("Ratio of BRA area to urban-core area.", "ratio", "derived", "three-zone delineation", "NB01"),
    "bra_water_frac": ("Fraction of the BRA BOUNDING BOX covered by permanent water. Measured on the bbox, before the urban core is subtracted.", "fraction", "JRC Global Surface Water", "water masking", "NB01"),
    "bra_smod_builtup_frac": ("Fraction of the BRA BOUNDING BOX classed as peri-urban (SMOD 21). Measured on the bbox, before the urban core is subtracted.", "fraction", "GHS-SMOD", "three-zone delineation", "NB01"),
    "bra_effective_area_km2": ("BRA BOUNDING BOX area after water and peri-urban exclusion. Measured on the bbox and therefore LARGER than bra_area_km2, which also excludes the urban core.", "km2", "derived", "three-zone delineation", "NB01"),
    "smod_epoch_year": ("GHS-SMOD epoch used to delineate the zones.", "year", "GHS-SMOD", "three-zone delineation", "NB01"),
    "uc_flags": ("Delineation flags raised for the urban core.", "", "derived", "three-zone delineation", "NB01"),
    "population_wup_k": ("City population from UN World Urbanization Prospects, 2024 estimate. The parent city's own figure; it excludes any city absorbed into it.", "thousand persons", "UN WUP", "lookup", "NB01"),
    "population_wup_merged_k": ("City population after spatial deduplication: the city's own UN WUP 2024 population plus that of every city absorbed into it. Equals population_wup_k where nothing was absorbed. This is the total used for city- and cluster-level population reporting.", "thousand persons", "UN WUP", "spatial deduplication", "NB01 absorbed_cities.csv + UN WUP 2024 table"),
    "population_uc_persons": ("Resident population inside the urban core, GHS-POP summed on its native 100 m grid.", "persons", "GHS-POP", "zonal sum at 100 m", "scripts/extract_population_100m.py"),
    "population_bra_persons": ("Resident population inside the background reference area, GHS-POP summed on its native 100 m grid.", "persons", "GHS-POP", "zonal sum at 100 m", "scripts/extract_population_100m.py"),
    "population_cr_persons": ("Resident population inside the city region, GHS-POP summed on its native 100 m grid. USE THIS as the denominator for exposure shares: spots are detected across the whole city region and do not respect the urban-core boundary. Of the 185 L50 footprints only 16 lie wholly inside the UC, 75 wholly inside the BRA, 36 straddle the two and 8 sit mostly in neither, so UC understates the base and only CR covers every spot.", "persons", "GHS-POP", "zonal sum at 100 m", "scripts/extract_population_100m.py"),
    "absorbed_cities": ("Names of the cities absorbed into this one, semicolon-separated, in UN WUP spelling. A city is absorbed when its urban core falls entirely within a larger adjacent city.", "", "derived", "spatial deduplication", "NB01 absorbed_cities.csv"),
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
    "spot_zone": ("Zone containing the spot's L50 centroid: urban_core, bra, or both, where both means the centroid falls in neither of the two.", "", "derived", "zone intersection", "NB05"),
    "tier": ("Delineation tier: 1 for KDE-delineated spots (10 or more validated pixels), 2 for spots of 1 to 9 pixels, each pixel represented by a 500 m buffer simplified at a 50 m tolerance, about 0.71 km2 per isolated pixel.", "", "SEVIRI", "tier assignment", "NB05 section 6"),
    "n_pixels": ("Validated pixels for the GROUP this spot belongs to (city x period x spot type), repeated on every spot of that group. It is not the pixel count of this spot alone.", "count", "SEVIRI", "Gi* |Z| >= 1.96, Queen contiguity", "NB05"),
    "n_pixels_l75": ("Pixels inside the L75 zone.", "count", "SEVIRI", "Gaussian KDE", "NB05"),
    "n_pixels_l90": ("Pixels inside the L90 dense core.", "count", "SEVIRI", "Gaussian KDE", "NB05"),
    "n_pixels_level": ("Validated pixels within this contour level. At L50 this is the group total for the city, period and spot type, as in spots.n_pixels.", "count", "SEVIRI", "Gaussian KDE", "NB05"),
    "area_l50_km2": ("Area of the L50 outer extent.", "km2", "SEVIRI", "Gaussian KDE, Scott's bandwidth", "NB05"),
    "area_l75_km2": ("Area of the L75 inner zone.", "km2", "SEVIRI", "Gaussian KDE, Scott's bandwidth", "NB05"),
    "area_l90_km2": ("Area of the L90 dense core.", "km2", "SEVIRI", "Gaussian KDE, Scott's bandwidth", "NB05"),
    "area_l75_pct": ("L75 area as a share of L50.", "%", "SEVIRI", "Gaussian KDE", "NB05"),
    "area_l90_pct": ("L90 area as a share of L50.", "%", "SEVIRI", "Gaussian KDE", "NB05"),
    "l75_completeness": ("Whether an L75 contour could be delineated for every spot in the group.", "", "SEVIRI", "Gaussian KDE", "NB05"),
    "l90_completeness": ("Whether an L90 contour could be delineated for every spot in the group.", "", "SEVIRI", "Gaussian KDE", "NB05"),
    "dense_core_pct": ("L90 dense core as a share of the L50 footprint.", "%", "SEVIRI", "Gaussian KDE", "NB05"),
    "is_merged_t2": ("True when tier-2 pixels were absorbed into this tier-1 polygon. No spot in this release triggered it.", "", "SEVIRI", "tier-2 absorption within 2 km", "NB05 section 6d"),
    "n_absorbed_t2": ("Number of tier-2 spots absorbed into this polygon. Zero for every spot in this release.", "count", "SEVIRI", "tier-2 absorption within 2 km", "NB05 section 6d"),
    "core_mean_lst_c": ("Mean LST inside the L90 dense core.", "C", "SEVIRI", "zonal statistics", "NB05"),
    "core_max_lst_c": ("Maximum LST inside the L90 dense core.", "C", "SEVIRI", "zonal statistics", "NB05"),
    "mean_lst_c": ("Mean LST within the spot footprint.", "C", "SEVIRI", "zonal statistics", "NB05"),
    "std_lst_c": ("Standard deviation of LST within the spot footprint.", "C", "SEVIRI", "zonal statistics", "NB05"),
    "max_lst_c": ("Maximum LST within the spot footprint.", "C", "SEVIRI", "zonal statistics", "NB05"),
    "min_lst_c": ("Minimum LST within the spot footprint.", "C", "SEVIRI", "zonal statistics", "NB05"),
    "pop_l50_persons": ("Resident population within the L50 outer extent, GHS-POP summed on its native 100 m grid with fractional overlap. Express as a share of population_cr_persons in city_profile.", "persons", "GHS-POP", "zonal sum at 100 m", "GHS-POP P2023A epoch 2025"),
    "nb04_val_tier": ("Quality tier of the NB04 event window underlying the SEVIRI composite.", "", "ERA5-Land", "event selection", "NB04 via NB05"),
    "persistent_dn": ("True when the city has at least one hot spot by day and at least one by night.", "", "SEVIRI", "day-night persistence check", "NB05"),
    # events
    "selection_reason": ("Why this event was chosen for SEVIRI compositing.", "", "ERA5-Land", "event selection", "NB04 event audit"),
    "seviri_scene_available": ("True when a clipped SEVIRI composite exists for the selected window.", "", "MSG-SEVIRI", "scene inventory", "NB04 seviri folder"),
    # city roll-ups
    "validation_tier": ("Quality tiers of the city's two selected heat events, joined day-first as '<day>/<night>', each one of FAIR, GOOD or EXCELLENT: 'EXCELLENT/GOOD' means the day event was EXCELLENT and the night event GOOD. It is a pair, not a single ranked grade, so do not order these values. Six combinations occur in this release.", "", "ERA5-Land", "event selection", "derived in the build from day_selected_event_tier and night_selected_event_tier"),
    "bh_any": ("1 when any spot group of the city (city x period x spot type) survives BH-FDR control, 0 when none does.", "", "SEVIRI", "BH-FDR q = 0.05", "derived in the build from spots.bh_significant"),
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
    (_re.compile(r"^(day|night)_era5land_minus_modis_bias_c$"),
     ("Mean ERA5-Land minus MODIS {0} difference; positive means ERA5-Land warmer.", "C",
      "MODIS; ERA5-Land", "paired comparison", "NB04 city_heat_event_summary.csv")),
    (_re.compile(r"^(day|night)_modis_era5land_rmse_c$"),
     ("Root mean squared error between MODIS and ERA5-Land {0} LST.", "C", "MODIS; ERA5-Land",
      "paired comparison", "NB04 city_heat_event_summary.csv")),
    (_re.compile(r"^(day|night)_modis_era5land_mae_c$"),
     ("Mean absolute error between MODIS and ERA5-Land {0} LST.", "C", "MODIS; ERA5-Land",
      "paired comparison", "NB04 city_heat_event_summary.csv")),
    (_re.compile(r"^(day|night)_seviri_(uc|bra|cr)_mean_c$"),
     ("MSG-SEVIRI {0} composite mean land-surface temperature over the {1} zone, across the "
      "selected persistent heat event. Copied from the event composite without recomputation.",
      "C", "MSG-SEVIRI", "event compositing", "NB04 seviri/City_SEVIRI_3zone_SUHII.csv")),
    (_re.compile(r"^(day|night)_seviri_suhii_c$"),
     ("Event-scale surface urban heat island intensity for the {0} period: the MSG-SEVIRI "
      "urban-core composite minus the background reference area composite. Equals "
      "spots.suhii_event_c for every spot of this city and period.",
      "C", "MSG-SEVIRI", "event compositing", "NB04 seviri/City_SEVIRI_3zone_SUHII.csv")),
    (_re.compile(r"^(day|night)_era5land_event_mean_c$"),
     ("Mean of the ERA5-Land daily urban-core median temperatures across the days of the "
      "selected {0} event. This is the quantity the matching "
      "{0}_seviri_minus_era5land_bias_c is measured against, so that bias is reproducible "
      "from this dataset: bias = {0}_seviri_uc_mean_c minus this field.",
      "C", "ERA5-Land", "event-window mean",
      "NB04 raw_extractions daily ERA5-Land series over the selected event window")),
    (_re.compile(r"^(day|night)_seviri_era5land_n$"),
     ("Number of event days in the selected {0} window over which the MSG-SEVIRI composite was "
      "compared with ERA5-Land daily values.", "count", "ERA5-Land",
      "event-window comparison", "NB04 SEVIRI_vs_ERA5_target_metrics.csv")),
    (_re.compile(r"^(day|night)_seviri_minus_era5land_bias_c$"),
     ("MSG-SEVIRI urban-core {0} composite minus the mean of the ERA5-Land daily urban-core "
      "medians across the selected event days; positive means SEVIRI warmer.", "C",
      "MSG-SEVIRI; ERA5-Land", "event-window comparison",
      "NB04 SEVIRI_vs_ERA5_target_metrics.csv")),
    (_re.compile(r"^(day|night)_seviri_era5land_rmse_c$"),
     ("Root mean squared difference between the single MSG-SEVIRI urban-core {0} composite and "
      "each ERA5-Land daily value across the selected event days.", "C",
      "MSG-SEVIRI; ERA5-Land", "event-window comparison",
      "NB04 SEVIRI_vs_ERA5_target_metrics.csv")),
    (_re.compile(r"^(day|night)_seviri_era5land_mae_c$"),
     ("Mean absolute difference between the single MSG-SEVIRI urban-core {0} composite and each "
      "ERA5-Land daily value across the selected event days.", "C",
      "MSG-SEVIRI; ERA5-Land", "event-window comparison",
      "NB04 SEVIRI_vs_ERA5_target_metrics.csv")),
    (_re.compile(r"^n_(hot|cold)_(day|night)_spots$"),
     ("{0} spots delineated in the {1} period; 0 means none detected.", "count", "SEVIRI",
      "Gi* then KDE delineation", "derived from the spots layer")),
    (_re.compile(r"^n_(hot|cold)_(day|night)_bh_significant$"),
     ("{0} {1} spots surviving BH-FDR control; 0 means none.", "count", "SEVIRI",
      "BH-FDR q = 0.05", "derived from the spots layer")),
]


# Field names whose meaning depends on the layer they sit in. Checked before DESCR, which is
# keyed on the field name alone and so can only hold one meaning per name.
LAYER_DESCR = {
    ("heat_event_catalogue", "tier"): (
        "Quality tier of the event window, assigned during event selection.", "",
        "ERA5-Land", "event selection", "NB04 event audit"),
    ("city_profile", "geometry"): (
        "Point geometry: the centroid of the city's urban-core polygon. It is a label point for "
        "the record, not a surveyed or gazetteer city location; it sits a median 1.1 km from the "
        "UN WUP city coordinate (39.3 km at most, where an absorbed city was remapped).", "",
        "derived", "urban-core centroid", "NB01 urban-core polygon"),
    ("city_exposure_by_contour", "area_l50_km2"): (
        "Total L50 outer extent area for this city, period and spot type: the sum over every spot of that type in the city, not the area of a single polygon. Contours of one city, period and type never overlap in this release, so the sum does not double count. Zero where no spot of that type was delineated.", "km2",
        "SEVIRI", "sum of per-spot KDE contour areas", "NB05 halfdonut_city_summary.csv"),
    ("city_exposure_by_contour", "area_l75_km2"): (
        "Total L75 inner zone area for this city, period and spot type: the sum over every spot of that type in the city, not the area of a single polygon. Contours of one city, period and type never overlap in this release, so the sum does not double count. Zero where no spot of that type was delineated.", "km2",
        "SEVIRI", "sum of per-spot KDE contour areas", "NB05 halfdonut_city_summary.csv"),
    ("city_exposure_by_contour", "area_l90_km2"): (
        "Total L90 dense core area for this city, period and spot type: the sum over every spot of that type in the city, not the area of a single polygon. Contours of one city, period and type never overlap in this release, so the sum does not double count. Zero where no spot of that type was delineated.", "km2",
        "SEVIRI", "sum of per-spot KDE contour areas", "NB05 halfdonut_city_summary.csv"),
    ("city_exposure_by_contour", "pop_l50_persons"): (
        "Resident population of the L50 outer extent summed over every spot of this type in the city, not the population of a single polygon. It is the sum of the per-spot values, which do not overlap, so no resident is counted twice. Express as a share of city_profile.population_cr_persons.", "persons",
        "GHS-POP", "sum of per-spot zonal sums at 100 m", "GHS-POP P2023A epoch 2025"),
    ("city_exposure_by_contour", "pop_l75_persons"): (
        "Resident population of the L75 inner zone summed over every spot of this type in the city, not the population of a single polygon. It is the sum of the per-spot values, which do not overlap, so no resident is counted twice. Express as a share of city_profile.population_cr_persons.", "persons",
        "GHS-POP", "sum of per-spot zonal sums at 100 m", "GHS-POP P2023A epoch 2025"),
    ("city_exposure_by_contour", "pop_l90_persons"): (
        "Resident population of the L90 dense core summed over every spot of this type in the city, not the population of a single polygon. It is the sum of the per-spot values, which do not overlap, so no resident is counted twice. Express as a share of city_profile.population_cr_persons.", "persons",
        "GHS-POP", "sum of per-spot zonal sums at 100 m", "GHS-POP P2023A epoch 2025"),
    ("stakeholder_spots_gps", "spot_type"): (
        "Whether the participant marked this location as a hot or a cold place. It is the participant's own label, not a Gi* classification, so it is not expected to coincide with the spots layer; hitrate_sensitivity measures how often the two agree.", "",
        "stakeholder", "participatory mapping", "NB02 workshop mapping exercise"),
    ("stakeholder_spots_gps", "city"): (
        "The study city named on the questionnaire row that carries this point (items 54 and 55, "
        "the cities the participant answered for). It is not the registration city (item 8). It "
        "equals the participant's city in stakeholder_perception except where the participant "
        "named several study cities and marked points for a city other than the one kept there "
        "(3 points of one participant in this release). It is not necessarily the city containing "
        "the point; see in_city_region and containing_city.", "",
        "stakeholder", "questionnaire items 54-55", "NB02, NB05"),
    ("stakeholder_perception", "city"): (
        "The study city the participant answered the questionnaire for: the city named in items 54 and 55 (the target and other cities the participant named), restricted to the study cities. It is not the registration city (item 8), which decides only membership of the cohort. Where a participant named several study cities, NB02 keeps one city per participant, the first in its cleaned workshop table; this is not a choice by frequency (the three participants concerned named each of their cities equally often).", "",
        "stakeholder", "questionnaire items 54-55", "NB02"),
    ("stakeholder_spots_gps", "study_year"): (
        "Year of the workshop series in which the point was marked. Every participant is recorded under 2024, the year of the series; the final workshop itself took place on 22 January 2025.", "year",
        "stakeholder", "workshop series", "NB02"),
    ("stakeholder_perception", "perceived_peak_period"): (
        "Months the participant perceives as the city's temperature peak. A participant who did not answer is recorded as \"I'd rather not say\", the same value the other perception items use, so the four items share one vocabulary and none carries a null.", "",
        "stakeholder", "questionnaire item 58", "NB02"),
}


def describe(field: str, layer: str | None = None):
    if (layer, field) in LAYER_DESCR:
        return LAYER_DESCR[(layer, field)]
    if field in DESCR:
        return DESCR[field]
    for pat, (d, unit, sensor, method, prov) in _PATTERNS:
        m = pat.match(field)
        if m:
            return (d.format(*m.groups()), unit, sensor, method, prov)
    return (f"[CHECK] description not yet written for '{field}'.", "", "[CHECK]", "[CHECK]", "[CHECK]")


NULL_MEANING = {
    "recency_of_contact_with_city": "none",
    "containing_city": "The point falls in no study city's city region.",
    "bh_any": "The city has no spots, so there is no spot group to test.",
    "absorbed_cities": "No city was absorbed into this one.",
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
            d, unit, sensor, method, prov = describe(f, lname)
            if d.startswith("[CHECK]"):
                CHECKS.append(f"{lname}.{f}")
            if lname == "dataset_info" and f == "value":
                # values restate the build (dates, fingerprints, labels); listing them
                # would make the dictionary differ from one build to the next
                rng = "free text, one value per key"
            elif f == "geometry":
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
           f"Built {BUILD_DATE}. One table per layer. Generated from `data_dictionary.csv`.", ""]
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
    "city_zones": "Urban-core, background reference area and city-region polygons for every city.",
    "city_profile": "One record per city, year-independent: PLT classes, zone areas, population, participants.",
    "city_year_summary": "One record per city and study year: ERA5-Land persistence, selected events, sensor comparison, spot counts.",
    "trend_statistics": "Long-term LST trend tests per city, zone and period.",
    "composite_trend_statistics": "Cluster and national composites of the annual series: unweighted means of member cities, same trend protocol as trend_statistics.",
    "annual_series": "Annual zone values, 2006-2025.",
    "monthly_series": "Monthly zone values, 2006-2025.",
    "monthly_climatology": "Calendar-month means across the study period.",
    "heat_event_catalogue": "Every ERA5-Land persistent heat event, with the selected one flagged.",
    "spot_occurrence": "Spot counts and Gi*/BH-FDR pixel counts on the full city x period x type grid, zeros included.",
    "spots": "One polygon per delineated hot or cold spot (L50 footprint).",
    "spot_contours": "One polygon per KDE contour level (L50, L75, L90), hot and cold spots alike.",
    "stakeholder_spots_gps": "Stakeholder-marked hot and cold spot locations, pseudonymised and coarsened to ~110 m.",
    "stakeholder_perception": "Perception responses, one row per participant, pseudonymised.",
    "hitrate_sensitivity": "Stakeholder-satellite agreement across buffer distances, computed from the released (3-decimal-degree) point coordinates.",
    "city_exposure_by_contour": "Population exposure by contour level per city, period and spot type.",
    "dataset_info": "Dataset metadata as key/value pairs.",
    "scenario_config": "The configuration behind each scenario_id: city-selection rule, thresholds and method parameters.",
}


def write_readme(layers, out_dir: Path, gpkg: Path, fp: str = ""):
    def size(p):
        n = p.stat().st_size
        return f"{n/1e6:.1f} MB" if n >= 1e6 else f"{n/1e3:.0f} kB"

    rows = "\n".join(
        f"| `{n}` | {len(d):,} | {LAYER_ONE_LINER.get(n, '')} |"
        for n, d in layers.items() if d is not None)
    # A fixed manifest with a Contents column, not a glob over the folder. Globbing listed
    # only what existed when the README was written, so a fresh build omitted four of the
    # seven files. Sizes are deliberately not shown: no entry can then refer to itself or go
    # stale. Zenodo and the Data in Brief article carry the sizes.
    _manifest = [
        (DATASET_STEM + ".gpkg", "All " + str(sum(1 for d in layers.values() if d is not None))
                                 + " layers (" + CRS_ANALYSIS + ")"),
        ("data_dictionary.csv", "Field-level data dictionary (machine-readable)"),
        ("data_dictionary.md", "The same dictionary, for reading"),
        ("CHANGELOG.md", "Changes by version"),
        ("LICENSE.txt", "CC BY 4.0 licence"),
        ("README.md", "This file"),
        ("checksums_md5.txt", "MD5 checksums of all other files, written last"),
    ]
    files = ("\n").join("| `" + _nm + "` | " + _what + " |"
                                for _nm, _what in _manifest)

    n_part = len(layers["stakeholder_perception"])
    _data = {n: d for n, d in layers.items() if d is not None and n != "dataset_info"}
    _n_all = len(_data) + 1
    _n_fields = sum(len(d.columns) for d in _data.values()) + 2
    _n_rec = sum(len(d) for d in _data.values())

    # Geometry-bearing layers are counted, not stated, so the split cannot go stale when a
    # layer is added. GeoDataFrame is the test: an attribute-only layer is a plain frame.
    _geom_layers = [n for n, d in layers.items()
                    if d is not None and getattr(d, "geometry", None) is not None]
    _n_live = sum(1 for d in layers.values() if d is not None)
    _n_geom = len(_geom_layers)
    _n_attr = _n_live - _n_geom
    _w = {5: "Five", 12: "twelve", 13: "thirteen", 14: "fourteen", 6: "Six"}
    _n_geom = _w.get(_n_geom, _n_geom)
    _n_attr = _w.get(_n_attr, _n_attr)

    # The abbreviation list is read from the Data in Brief source of truth rather than
    # restated here, so the two can never disagree. Missing file fails the build.
    _ab_src = ABBREV_CSV
    if not _ab_src.exists():
        raise FileNotFoundError(f"abbreviation list not found: {_ab_src}")
    _ab = pd.read_csv(_ab_src)
    _abbrev = ("\n").join("| " + str(r.abbreviation) + " | " + str(r.meaning) + " |"
                          for r in _ab.itertuples())

    txt = f"""# {DATASET_TITLE}

Built {BUILD_DATE}. Content fingerprint `sha256:{fp}`: it identifies the data (see CHANGELOG.md).
Versions are named on Zenodo; the concept DOI in section 9 resolves to all of them.

This version covers the 56 Nigerian cities that remain after spatial deduplication of the 67
UN World Urbanization Prospects 2024 candidates with a population of at least 300,000. The
land-surface temperature record runs 2006-2025; persistent heat events, surface hot and cold
spots, population exposure and stakeholder evidence are for 2024.

## 1. What this dataset contains

**One GeoPackage, {_n_all} layers: {_n_all - 1} data layers plus `dataset_info`.** Spatial and attribute-only
layers live side by side in the same file, so there is a single data artefact to cite, download
and checksum. The data layers hold {_n_rec:,} records. The data dictionary describes {_n_fields} fields:
{_n_fields - 2} in the data layers and the two (`key`, `value`) of `dataset_info`. Any layer can be
read with GDAL/OGR, geopandas, QGIS, R (sf) or any GeoPackage-aware tool.

| layer | rows | contents |
|---|---|---|
{rows}

## 2. Files

| File | Contents |
|---|---|
{files}

## 3. Keys and joining

- `city_slug` is the stable city key; `city` is the display name; `cluster25` is the PLT cluster.
- `zone` is one of `uc`, `bra`, `cr`, `suhii`; `period` is `day` or `night`; `spot_type` is `hot` or `cold`; `contour_level` is `L50`, `L75` or `L90`.
- `spot_uid` (study year + spot id) is the key that joins `spots` and `spot_contours`, and stays unique if the protocol is re-run for another year. `spot_id` is the identifier used within a single year and is not unique across years.
- `city_slug` joins `city_profile` (year-independent) to `city_year_summary` and every event-scale layer; add `study_year` when more than one year is present.
- `participant_code` joins the two stakeholder layers.
- `composite_trend_statistics` is keyed by `composite_type`, `composite_key`, `zone` and `period`, not by `city_slug`: each row is a group of cities, so it joins to `city_profile` through `cluster25` (`composite_key`), not city by city.

```python
import geopandas as gpd
gpkg = "{DATASET_STEM}.gpkg"
spots  = gpd.read_file(gpkg, layer="spots")                      # polygons
trends = gpd.read_file(gpkg, layer="trend_statistics")           # attribute-only layer
joined = spots.merge(trends.query("zone == 'suhii'"), on=["city_slug", "period"], how="left")
```

## 4. Coordinate reference system and coverage

- Every layer is in {CRS_ANALYSIS} (Africa Albers Equal Area Conic), the analysis CRS; all areas
  and distances were computed in it. {_n_geom} layers carry geometry (`city_zones`,
  `city_profile`, `spots`, `spot_contours`, `stakeholder_spots_gps`); the other {_n_attr}
  are attribute-only tables stored in the same file.
- Spatial coverage: Nigeria, about 4-14 N and 2-15 E.
- Temporal coverage: MODIS Aqua MYD11A1 {TREND_FIRST}-{TREND_LAST}; ERA5-Land {STUDY_YEAR}; MSG-SEVIRI composites over the selected {STUDY_YEAR} heat events.

## 5. Input data sources

| source | use |
|---|---|
| MODIS Aqua MYD11A1 Collection 6.1 (NASA LP DAAC) | long-term day and night land-surface temperature |
| ERA5-Land hourly, skin temperature (ECMWF Copernicus Climate Change Service) | daily values for persistent heat events |
| MSG LST with Directional Effects, MLST_DIR [LSA-004] (EUMETSAT LSA SAF) | event-scale composites for spot detection |
| GHS-SMOD R2023A (European Commission JRC) | settlement model for the three-zone delineation |
| GHS-POP R2023A, epoch 2025 (European Commission JRC) | resident population; summed on the native 100 m grid per polygon, with fractional overlap |
| Global Surface Water v1.4 (European Commission JRC) | permanent-water masking in the three-zone delineation, and the MSG-SEVIRI water mask (water bodies >= 3 km2) |
| World Urbanization Prospects, 2025 revision (UN DESA) | city population and city selection |
| Physiographic landscape typology (Eneche et al., 4TU.ResearchData, 2025) | landscape character class per city |

Full citations for every source are given in the associated Data in Brief article.

## 6. Bias conventions

Two sensor comparisons are published, and each field name states the direction of the subtraction
so the sign cannot be misread. `day_era5land_minus_modis_bias_c` and its night counterpart are the
mean of ERA5-Land minus MODIS across the days when both have a valid urban-core value, so a
positive value means ERA5-Land is the warmer of the two. `day_seviri_minus_era5land_bias_c` and its
night counterpart are the MSG-SEVIRI urban-core composite minus the mean of the ERA5-Land daily
urban-core medians across the selected event days, so a positive value means SEVIRI is warmer. The
accompanying `*_n`, `*_r`, `*_r2`, `*_rmse_c` and `*_mae_c` fields are sign-free.

## 7. What is deliberately not included

- **Association analysis.** Kruskal-Wallis, Dunn post-hoc, chi-square, effect sizes, forest-plot data and the synthesis association tables belong to the research article.
- **Cluster-level and national aggregates.** They are findings of the article and can be rebuilt from the city-level records with a group-by on `cluster25`.
- **The raw questionnaire.** No free text, names, emails, phone numbers, device identifiers or timestamps. Only the perception items listed in the data dictionary are present.
- **Rasters and per-city intermediates.** The source imagery is available from the providers listed above, and the derived rasters are reproducible from the code record.

## 8. Participant cohort and inclusion rule

The {n_part} participants in `stakeholder_perception` are the respondents whose **registered** city is
one of the study cities. Registration is the auditable record of participation, so a respondent
recorded as attending a workshop but holding no registration entry is excluded: participation
cannot be verified independently, as no per-person attendance register exists. One respondent falls
in that category and is excluded from every layer, along with the spots they marked. The rule is
deliberate and conservative — it omits an unverifiable record rather than admitting one.

Registration decides who is in the cohort; it does not decide a participant's `city`. That is the
study city the participant answered the questionnaire for (items 54 and 55). The data dictionary
gives the rule for participants who named several cities.

## 9. Licence and citation

Licence: **CC BY 4.0**.

- Dataset, all versions (concept DOI): https://doi.org/{CONCEPT_DOI}. Each version also has its
  own DOI, assigned by Zenodo and shown on the record page.

Related publications and the code record are listed on the Zenodo record page.

The full licence text accompanies this dataset in `LICENSE.txt`.

## 10. Abbreviations

| abbreviation | meaning |
|---|---|
{_abbrev}

## 11. Map disclaimer

Map lines delineate study areas and do not necessarily depict accepted national boundaries. The boundaries are only for academic and research purposes.
"""
    (out_dir / "README.md").write_text(txt, encoding="utf-8", newline="\n")


def write_licence(out_dir: Path):
    """CC BY 4.0 notice. The deposit carries its licence with it."""
    text = f"""{DATASET_TITLE}

Copyright (c) 2026 P. S. U. Eneche, Y. Zeng, F. Atun, K. Pfeffer
University of Twente, Faculty of Geo-Information Science and Earth Observation (ITC)

This work is licensed under the Creative Commons Attribution 4.0 International License
(CC BY 4.0).

You are free to:
  Share  - copy and redistribute the material in any medium or format
  Adapt  - remix, transform, and build upon the material for any purpose, even
           commercially

Under the following terms:
  Attribution - You must give appropriate credit, provide a link to the licence, and
                indicate if changes were made. You may do so in any reasonable manner,
                but not in any way that suggests the licensor endorses you or your use.

No additional restrictions - You may not apply legal terms or technological measures that
legally restrict others from doing anything the licence permits.

Full licence text:       https://creativecommons.org/licenses/by/4.0/legalcode
Human-readable summary:  https://creativecommons.org/licenses/by/4.0/

Map disclaimer: map lines delineate study areas and do not necessarily depict accepted
national boundaries.
"""
    (out_dir / "LICENSE.txt").write_text(text, encoding="utf-8", newline="\n")


# ── CHANGELOG ────────────────────────────────────────────────────────────────
# Assembled, not written whole: the header, the entry for this deposit, then every earlier entry
# carried forward from the deposit it replaces. Entries carry no version name: versions are named
# on Zenodo only. Each is headed by its date and the content fingerprint of the data it describes,
# and says which earlier deposit it is compared with. Prose only: the field-by-field detail of a
# build is in dataset_build/CHANGES_REPORT_<date>.md.
CHANGELOG_HEADER = """# Changelog

All notable changes to this dataset are recorded here, newest first, in the sections of Keep a
Changelog (https://keepachangelog.com/en/1.1.0/). Entries carry no version name: versions are named
on Zenodo. Each entry is headed by its date and the content fingerprint of the data it describes, a
SHA-256 over every layer, the scenario configuration and the data dictionary that excludes the build
date, commit and checksums, so it identifies the data rather than the build.
"""

# The entry for the first deposit after v1.0.0: what changed between v1.0.0 and this build.
NOTES_SINCE_1_0_0 = """### Changed values

Three published values change: the hit rates, and the one blank peak-period answer and the one
blank recency answer, both now stored as "I'd rather not say". Nothing was re-observed and no
geometry changed: every polygon, contour and coordinate is identical to v1.0.0.

- **`hitrate_sensitivity` now rests on the participant cohort.** In v1.0.0 this layer selected
  stakeholder points by the city of workshop ATTENDANCE, so it was computed on 57 hot and 40 cold
  points, while `stakeholder_spots_gps` carried 55 and 39 under the registration rule documented
  in the README. The two no longer disagree: the layer is now derived from the released `spots`
  and `stakeholder_spots_gps` layers, using the published coordinates as they are stored, so the
  hit rates can be recomputed from this dataset alone. At a 500 m buffer: hot day 4/55 and hot
  night 3/55 (were 4/57 and 3/57), cold day 4/39 (was 5/40), cold night 0/39 (was 0/40). Every
  changed count traces to the three points marked by the one respondent the cohort rule excludes.
  The counting rule itself is unchanged.
- **`stakeholder_perception.perceived_peak_period`**: the one blank answer is stored as "I'd rather
  not say", the value the warming and diurnal items already use for a blank.
- **`stakeholder_perception.recency_of_contact_with_city`**: likewise, its one blank answer is
  stored as "I'd rather not say", so none of the four perception items carries a null.

### Added

- **`composite_trend_statistics`** ({n_comp} rows): Cluster25 and national composites of the annual
  series, by zone and period. Each row is the unweighted mean of its member cities per year,
  then the same Mann-Kendall and Sen protocol used for `trend_statistics`. Publishing them fixes
  the aggregation and the trend test to one definition.
- **Event-scale sensor fields in `city_year_summary`**: per-city ERA5-Land event means for the
  selected event window, and the MSG-SEVIRI three-zone event composites, so the
  SEVIRI-against-ERA5-Land comparison can be reproduced from the package.
- **`stakeholder_spots_gps.in_city_region` and `.containing_city`**: whether a marked point falls
  inside the city region of the city the participant answered for, and which study city's
  region does contain it. Points outside are not errors: participants were asked about a city,
  not about where they were standing.
- **`city_profile.pct_assigned_class_cr`**: the share of the CITY REGION held by the cluster
  assigned to the city. The assignment is made on the city region, so this is the figure that
  justifies it; the existing `pct_dominant_class` measures the urban core and can be much smaller.
- **Identity in `dataset_info`**: `content_fingerprint` (the fingerprint heading this entry),
  `previous_fingerprint` (the deposit this entry is compared with) and `concept_doi`, the DOI
  that resolves to every version.
- **Package totals in `dataset_info`**: `n_layers` (all 18 tables: 17 data layers plus
  `dataset_info`), `n_data_layers`, `n_records_total` (records in the data layers),
  `n_fields_total` (327, every field the data dictionary describes, including the two of
  `dataset_info`), `n_geometry_layers` and one `rows_<layer>` per data layer.
- **Abbreviations**: the README now carries the full abbreviation list.

### Fixed

- **`city_year_summary.validation_tier` no longer null for a city with no spots.** Ikare produced
  no spots, so it had no row in the source roll-up and the field was empty. It now carries
  `EXCELLENT/GOOD`, built by the same rule as the other 55 cities: the day and night
  selected-event tiers joined day-first. The field is a PAIR of tiers, not a single ranked
  grade, so its values should not be ordered.
- **`recency_of_contact_with_city`** replaces a field published as `years_associated_with_city`.
  The questionnaire item records how recently the participant was in touch with the city, not a
  duration in years.
- **`dataset_info.dataset_doi` held the v1.0.0 version DOI.** It is replaced by `concept_doi`;
  each version's own DOI is assigned by Zenodo. The generated `version` field is removed:
  versions are named on Zenodo, and a deposit is identified by its `content_fingerprint`.
- **The v1.0.0 `checksums_md5.txt` recorded the digest of a generated README that was replaced
  before upload,** so the README failed verification in v1.0.0. Every file is now generated by
  the build, and the manifest verifies all files.
- **Every text file uses LF line endings.** The v1.0.0 manifest used CRLF, so `md5sum -c` failed
  on Linux and macOS.
- **Water masking is attributed correctly.** v1.0.0 listed OpenStreetMap water features as a
  source. No OpenStreetMap data is used anywhere: the MSG-SEVIRI water mask is built from JRC
  Global Surface Water bodies of at least 3 km2, the same source already credited for the zone
  delineation.

### Documentation

- Tier-2 spot geometry is described correctly: a 500 m buffer around each of the spot's pixels,
  simplified at a 50 m tolerance, about 0.71 km2 per isolated pixel. v1.0.0 called it a 1 km
  buffer.
- `n_obs` and `n_strict` are documented as counts of IMAGES with at least one valid pixel in the
  city region, not counts of pixel observations, which is why six zone-months carry a value where
  `n_obs` is 0.
- `spots.n_pixels`, `bh_significant` and `spot_contours.n_pixels_level` at L50 are documented as
  values for the whole city-period-type group, repeated on each spot, not per-spot values.
- `city_exposure_by_contour` areas and populations are documented as sums over all of the city's
  spots of that type and period; the contours do not overlap, so nothing is counted twice.
- `stakeholder_spots_gps.spot_type` is documented as the participant's own hot/cold label, not a
  Gi* classification, and `study_year` as the year of the workshop series.
- `city` in both stakeholder layers is documented as the study city the participant answered the
  questionnaire for (items 54 and 55), not the city they registered under, with the rule used
  where a participant named several cities.
- `city_year_summary.validation_tier` and `bh_any` are documented as derived from this dataset's
  own fields (the selected-event tiers, and `spots.bh_significant`); `bh_any` is null only for a
  city with no spots, which has no spot group to test.
"""

# v1.0.0's own entry, prose exactly as published.
ENTRY_1_0_0 = ("## [1.0.0] - " + V100_DATE + "\n\nfingerprint: sha256:" + V100_FINGERPRINT
               + " · first public release (version DOI " + V100_DOI + ")\n\n"
               + """First public release.

### Contents

One GeoPackage of 17 layers covering 56 Nigerian cities, grouped as:

- **Zonation** - urban core, background reference area and city region for every city, plus a
  year-independent city profile carrying the physiographic typology, zone areas and populations.
- **Long-term temperature** - annual and monthly land-surface temperature series per city, zone
  and period for 2006-2025, their calendar-month climatology, and Mann-Kendall / Sen trend
  statistics.
- **Persistent heat events** - the full ERA5-Land event catalogue for 2024, with the event
  selected for event-scale analysis flagged.
- **Surface hot and cold spots** - spot polygons and their 50/75/90% kernel-density contours,
  detected from MSG-SEVIRI composites over the selected events, with Getis-Ord Gi* and
  Benjamini-Hochberg FDR counts on the complete city x period x spot-type grid.
- **Population exposure** - resident population inside each spot and contour, and by city,
  period, spot type and contour level.
- **Stakeholder evidence** - pseudonymised perception responses, pseudonymised marked locations,
  and stakeholder-satellite agreement across buffer distances.

### Notes for this version

- Coverage is the 56 cities that remain after spatial deduplication of the 67 UN WUP 2024
  candidates with a population of at least 300,000.
- The long-term record runs 2006-2025; events, spots, population exposure and stakeholder
  evidence are for 2024.
- Population is summed from GHS-POP on its native 100 m grid, per polygon, with fractional
  overlap weighting.
- Every layer carries a `scenario_id` recording the configuration behind the run, so results
  produced under different settings or for another study year can coexist in one file and be
  told apart from the data alone.
""")


V100_RELATIVE = ("Changes relative to the deposit published on Zenodo as v1.0.0 (fingerprint "
                 "sha256:" + V100_FINGERPRINT + ").")
# An entry heading this module writes, or the v1.0.0 entry: "## 2026-10-29 · fingerprint
# sha256:<64 hex>" or "## [1.0.0] - 2026-09-30". Headings of the old local format ("## v1.0.1
# - 2026-10-28", never published) are not carried forward.
_ENTRY_HEAD = re.compile(r"^## (\[1\.0\.0\]|\d{4}-\d{2}-\d{2} · fingerprint sha256:[0-9a-f]{64})")


def changelog_history(deposit_dir: Path) -> list[str]:
    """Entries carried forward from the deposit, newest first; v1.0.0's when it has none."""
    cl = Path(deposit_dir) / "CHANGELOG.md"
    if cl.exists():
        txt = cl.read_text(encoding="utf-8").replace("\r\n", "\n")
        got = [p.rstrip("\n") + "\n" for p in re.split(r"(?m)^(?=## )", txt)
               if _ENTRY_HEAD.match(p)]
        if got:
            return got
    return [ENTRY_1_0_0]


def previous_entry(history: list[str]) -> dict:
    """What a new entry is compared with: the newest entry carried forward."""
    first = history[0]
    fp = re.search(r"sha256:([0-9a-f]{64})", first).group(1)
    if fp == V100_FINGERPRINT:
        return {"fingerprint": fp, "line": V100_RELATIVE}
    day = re.search(r"\d{4}-\d{2}-\d{2}", first.split("\n", 1)[0]).group(0)
    return {"fingerprint": fp,
            "line": f"Changes relative to the previous deposit, of {day} (fingerprint sha256:{fp})."}


def draft_from_changes(table: pd.DataFrame) -> str:
    """Prose sections from the changes report, for an entry after the v1.0.1 one."""
    meta = {"dataset_info", "data_dictionary.csv"}
    t = table.fillna("") if len(table) else pd.DataFrame(columns=["layer"])
    data = t[~t["layer"].isin(meta)] if len(t) else t
    changed, added, docs = [], [], []
    for r in data.itertuples():
        if getattr(r, "rows_deposit", 1) == 0:
            added.append(f"- New layer `{r.layer}`.")
            continue
        if getattr(r, "fields_changed", ""):
            changed.append(f"- Values change in `{r.layer}`: "
                           + ", ".join(f"`{f.strip()}`" for f in str(r.fields_changed).split(","))
                           + ".")
        if getattr(r, "rows_added", 0) or getattr(r, "rows_removed", 0):
            changed.append(f"- `{r.layer}` gains {int(r.rows_added or 0)} and loses "
                           f"{int(r.rows_removed or 0)} records.")
        if getattr(r, "fields_added", ""):
            added.append(f"- New fields in `{r.layer}`: {r.fields_added}.")
        if getattr(r, "fields_removed", ""):
            changed.append(f"- Fields removed from `{r.layer}`: {r.fields_removed}.")
    for r in (t[t["layer"].isin(meta)].itertuples() if len(t) else []):
        docs.append(f"- `{r.layer}` changes ({r.fields_changed or 'rows added or removed'}).")
    sec = lambda h, xs: [f"### {h}", ""] + (xs or ["- None."]) + [""]
    return "\n".join(sec("Changed values", changed) + sec("Added", added)
                     + sec("Fixed", []) + sec("Documentation", docs))


def assemble_changelog(entry_date: str, fp: str, prev: dict, body: str,
                       history: list[str]) -> str:
    parts = [CHANGELOG_HEADER, f"## {entry_date} · fingerprint sha256:{fp}", "",
             prev["line"], "", body.strip("\n"), ""]
    parts += [t.rstrip("\n") + "\n" for t in history]
    return "\n".join(parts).rstrip("\n") + "\n"


# Decisions taken during the build that a reader of the code cannot infer from it.
# Kept here, in the script, so the record is version-controlled and reproduced on every run.
DECISIONS = [
    ("Participant cohort — 105, not 106",
     "Inclusion is decided by the REGISTERED city (`matched_city_x`), not the city of workshop "
     "attendance (`matched_city_y`). One respondent (`cal235`) is recorded as attending in Abuja, "
     "a study city, with an exact city match and three marked spots (2 hot, 1 cold), but has no "
     "registration entry — one of only 4 of 332 respondents in that state. No per-person "
     "attendance register exists anywhere in the project, so attendance cannot be corroborated "
     "independently. The record is therefore excluded as unverifiable and the cohort is 105. "
     "Note that the earlier rationale given for this exclusion — that the city match came from "
     "`55_other_cities` — was wrong: 59 of the 105 included participants are matched through that "
     "same column, so it was never the disqualifier. The exclusion stands on verifiability alone."),
    ("Hit rates moved to the cohort basis (v1.0.1)",
     "v1.0.0 selected stakeholder points by city of ATTENDANCE, so `hitrate_sensitivity` rested "
     "on 57 hot and 40 cold points while `stakeholder_spots_gps` carried 55 and 39 under the "
     "cohort rule, and the two disagreed. The layer is now DERIVED during the build by "
     "scripts/compute_hitrate.py from the two released layers, `spots` and "
     "`stakeholder_spots_gps`, using the released coordinates rounded to three decimal degrees, "
     "so the published hit rates are reproducible from the dataset alone. At 500 m: hot day "
     "4/55 and hot night 3/55 (from 4/57 and 3/57), cold day 4/39 (from 5/40), cold night 0/39 "
     "(from 0/40). Every changed value traces to one respondent's three Abuja points. The "
     "counting rule is unchanged, and the README disclosure of the old mismatch is removed."),
    ("GPS coordinates coarsened to 3 decimal degrees",
     "About 110 m. Measured displacement is 43 m on average and 79 m at most, and it flips no "
     "hit-or-miss outcome at any published buffer radius (500 m, 1 km, 2 km), so the corroboration "
     "results are unaffected. Recorded in the scenario log as `gps_coordinate_decimals`."),
    ("ERA5-Land, not MODIS, for event persistence",
     "NB05 §7 originally read `modis_*_n_persistent_events` into the persistence fields. Those are "
     "0 for cities that do have ERA5 events (Aba day: MODIS 0/0 against ERA5 7/13). The package "
     "reads the ERA5-Land fields, and `n_modis_hot_days` was dropped as misleading."),
    ("Trend statistics carry an explicit zone",
     "The single trend value on each spot row in NB05 is the urban-core trend, not the SUHII trend "
     "(Abeokuta day: 2.83362 against 2.20390). Trends are published in `trend_statistics` keyed by "
     "city, zone and period so the zone can never be mistaken."),
    ("The equal-area ring search was never used and is now retired",
     "The zones were built with a FIXED buffer: BRA bbox = envelope(UC_raw.buffer(10 km)), "
     "CR = bbox - water, BRA = bbox - UC_raw - water - SMOD 21. The Dynamic Equal-Area ring "
     "search (Yang et al. 2024) existed as compute_bra_dea(), was imported by NB01 and never "
     "called. Three independent proofs: every city's zone metadata records "
     "bra_method = 'fixed_buffer'; envelope(UC.buffer(10 km)) reproduces the CR envelope to "
     "within 1% for 54 of 56 cities; and the BRA:UC area ratio is 2.4-49.5 (mean 10.8) where the "
     "ring search targets 1:1 within 5%, so 0 of 56 cities are consistent with it. The function, "
     "its config parameters (BRA_TOLERANCE, BRA_MAX_DIST_M, BRA_MIN_RING_M, BRA_MIN_ITER) and the "
     "scenario entries that advertised them have been removed, and the fossil fields bra_dist_km, "
     "bra_converged and bra_coastal are no longer published. No geometry changed; scenario_id "
     "changed from 4c24e467 because the scenario log now describes only what actually runs."),
    ("bra_water_frac, bra_smod_builtup_frac and bra_effective_area_km2 measure the bounding box",
     "NB01 computes the BRA fraction fields with _zone_fracs(bra_bbox_geom, ...), so they are "
     "measured on the BRA bounding box rather than on the BRA itself. bra_effective_area_km2 is "
     "consequently LARGER than bra_area_km2 for all 56 cities (Abuja: 2946.70 against 2508.15 "
     "km2), because the bbox excludes water and peri-urban but not the urban core. The values are "
     "published unchanged and the descriptions now say which geometry they refer to."),
    ("Population recomputed at native 100 m",
     "Population had been summed from a 1 km raster resampled from GHS-POP's 100 m grid without "
     "an additive reducer, so each 1 km cell held one 100 m value instead of the sum of the ~100 "
     "beneath it. Zonal sums understated population by about 100x: the Jos city region read "
     "15,970 against a true 1,550,542, and Lagos's urban core was 102x short of its UN WUP "
     "population. Every polygon is now summed server-side on the native 100 m grid, per polygon, "
     "with fractional overlap. A corrected 1 km raster was tested and rejected: the pixel-centre "
     "rule left only 3 of 10 Jos polygons within 5% of truth. Contour population rose 243,841 to "
     "24,521,914 with every KDE geometry byte-identical."),
    ("Event catalogue completed",
     "The catalogue read one audit file per city using the display name, but NB04 writes those "
     "files with spaces replaced by underscores. The three cities whose names contain a space -- "
     "Ado Ekiti, Benin City and Port Harcourt -- were never found, so 37 of their events were "
     "missing even though city_year_summary recorded them. 770 -> 807 rows, 53 -> 56 cities. A "
     "QA check now compares catalogue rows against era5_<period>_n_persistent_events."),
    ("Bias fields renamed to carry their direction",
     "day_/night_modis_era5land_bias_c became day_/night_era5land_minus_modis_bias_c, and "
     "day_/night_seviri_era5land_bias_c became day_/night_seviri_minus_era5land_bias_c. The old "
     "names did not say which sensor was subtracted from which, and the stored value is "
     "ERA5-Land minus MODIS and SEVIRI minus ERA5-Land respectively. No value changed."),
    ("ERA5_MIN_PIXELS retired",
     "Declared in config.py with a comment describing a City-Region proxy for zones with fewer "
     "than 4 ERA5 pixels, and never read by any code; the only other reference was the scenario "
     "log. Removed from config.py and from scenario_config."),
    ("The public changelog describes the release, not the repairs",
     "v1.0.0 is the first public version, so a reader has no earlier version to compare against. "
     "The correction history that used to sit in CHANGELOG.md is here instead, and this report is "
     "not part of the deposit."),
    ("Redundant exports retired, hot-biased names corrected",
     "12 files were withdrawn after a dependency scan showed they had no readers: "
     "`all_cities_dashboard.gpkg` duplicated this package exactly, and the GeoJSON, Shapefile and "
     "columns-CSV side exports of the spot layers were regenerable. They are staged in "
     "`Results/_to_delete/`, not erased. Two renames followed, because both layers hold cold spots "
     "as well as hot: `master_hotspot_gdf.*` to `master_thermal_spots.*`, and `all_cities_hotspots` "
     "to `all_cities_spots`. Approved and carried out in commit 25f1427."),
    ("One build report, not a folder of them",
     "The phase reports written while this package was assembled (inventory, participant-count "
     "decision, proposed NB05 diff, QA report, deletion manifest, package summary) are superseded "
     "by this single report; their substance is in sections 2 and 5 and in `results_inventory.csv`, "
     "`nb_outputs.csv` and `duplicates.json` beside it. The originals are staged in "
     "`Results/_to_delete/`."),
    ("Zero rows are explicit in `spot_occurrence`",
     "One city (Ikare) produced no spots at all and was absent from the source, giving 55 of 56 "
     "cities. The layer is built on the complete city x period x type grid with explicit zeros, "
     "so absence of a spot is distinguishable from absence of a record."),
]


def write_build_report(layers, dd, out_dir: Path, sources: dict):
    """Single build report. The QA script fills the marked block; nothing else writes here."""
    lines = [f"# Build report — {DATASET_STEM}, built {BUILD_DATE}", "",
             f"Built {date.today().isoformat()} by `scripts/build_master_summary.py`. "
             f"Validated by `scripts/qa_master_summary.py`.", "",
             "This folder is a build record and is **not** part of the published dataset. The "
             "archived files sit at the top level of the dataset folder.", "",
             "## 1. Layers, sources and row counts", "",
             "| layer | rows | fields | built from |", "|---|---|---|---|"]
    for n, d in layers.items():
        if d is None:
            continue
        lines.append(f"| `{n}` | {len(d):,} | {len(d.columns)} | {sources.get(n, '')} |")
    lines += ["", "## 2. Decisions on record", ""]
    for title, body in DECISIONS:
        lines += [f"**{title}.** {body}", ""]
    lines += ["## 3. Deviations from the target schema", ""]
    lines += [f"- {d}" for d in DEVIATIONS] or ["- none"]
    checks = sorted(set(CHECKS))
    lines += ["", f"## 4. `[CHECK]` items ({len(checks)})", "",
              "Fields whose provenance is worth re-reading before release.", ""]
    lines += [f"- `{c}`" for c in checks] or ["- none"]
    lines += ["", "## 5. Validation", "", QA_BEGIN,
              "_Not yet run for this build. Run `python scripts/qa_master_summary.py`._", QA_END, ""]
    _bd = out_dir.parent / BUILD_DIR_NAME
    _bd.mkdir(parents=True, exist_ok=True)
    (_bd / "build_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8",
                                         newline="\n")


def write_checksums(out_dir: Path):
    lines = []
    for p in sorted(out_dir.rglob("*")):
        rel = p.relative_to(out_dir)
        # never checksum the manifest itself: it exists on a rebuild but not on a
        # first build, which would otherwise make the listing non-deterministic
        if p.is_file() and rel.name != "checksums_md5.txt":
            lines.append(f"{md5(p)}  {rel.as_posix()}")
    # LF endings, explicitly. Path.write_text translates to CRLF on Windows, and md5sum -c
    # then reads every filename with a trailing carriage return and fails to open it, so the
    # manifest a depositor would verify with was unusable on any platform.
    (out_dir / "checksums_md5.txt").write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return len(lines)


# ── pre-flight: every input exists before anything is built ─────────────────
_NB01 = "NB01 (Notebook/01_AOI_delineation.ipynb)"
_NB02 = "NB02 (Notebook/02_stakeholder_analysis.ipynb)"
_NB03 = "NB03 (Notebook/03_temporal_analysis_months_annual.ipynb)"
_NB04 = "NB04 (Notebook/04_temporal_analysis_daily.ipynb)"
_NB05 = "NB05 (Notebook/05_hotspot_analysis.ipynb)"
_POP = "scripts/extract_population_100m.py"


def required_inputs() -> list[tuple[Path, str]]:
    """Every file the build reads that does not depend on the city list, with its producer."""
    return [
        (WUP_CSV, "the UN WUP input table (config.AOI_DATA_PATHS['cities_csv'])"),
        (ABBREV_CSV, "hand-authored reference input (tracked in git)"),
        (R01 / "city_cluster25_lookup.csv", _NB01),
        (R01 / "zone_area_summary_with_pop.csv", _NB01),
        (R01 / "absorbed_cities.csv", _NB01),
        (R01 / "cluster25_uc_distribution.csv", _NB01),
        (R01 / "cluster25_cr_distribution.csv", _NB01),
        (R02 / "Data" / "Cities_Stakeholder_Points_2024.geojson", _NB02),
        (R02 / "Data" / "Stakeholder_Perception_Data_2024.csv", _NB02),
        (R02 / "Data" / "workshop_attendees_clean.csv", _NB02),
        (R03 / "all_cities_temporal_annual.csv", _NB03),
        (R03 / "all_cities_delta_annual.csv", _NB03),
        (R03 / "all_cities_temporal_monthly.csv", _NB03),
        (R03 / "all_cities_delta_monthly.csv", _NB03),
        (R04 / "city_heat_event_summary.csv", _NB04),
        (R04 / "seviri" / "City_SEVIRI_3zone_SUHII.csv", _NB04),
        (R04 / "correlation" / "SEVIRI_vs_ERA5_target_metrics.csv", _NB04),
        (R05 / "spot_comprehensive_summary.csv", _NB05),
        (R05 / "all_cities_spots.geojson", _NB05),
        (R05 / "halfdonut_city_summary.csv", _NB05),
        (MASTER_GPKG, _NB05),
        (R05 / "population_100m" / "zones", _POP),
    ]


def preflight() -> list[str]:
    """Names every missing input and what produces it. An empty list means the build may run.

    A partial dataset is never built: several builders fall back to nulls when a source is
    absent, which would publish a hole as if it were data.
    """
    missing = [f"{p.relative_to(ROOT).as_posix()}  <- run {who}"
               for p, who in required_inputs() if not p.exists()]
    if MASTER_GPKG.exists():
        have = {n for n, _ in pyogrio.list_layers(MASTER_GPKG)}
        for lyr in ("hotspot_contours", "stakeholder_hotspot_gps", "stakeholder_coldspot_gps"):
            if lyr not in have:
                missing.append(f"{MASTER_GPKG.relative_to(ROOT).as_posix()}::{lyr}  <- run {_NB05}")
    ce = R04 / "city_heat_event_summary.csv"
    if not ce.exists():
        return missing
    cities = sorted(pd.read_csv(ce)["city"].astype(str).unique())
    for c in cities:
        s = slugify(c)
        for z in ("urban_core", "bra", "city_region"):
            f = R01 / s / f"{s}_{z}_102022_v5.geojson"
            if not f.exists():
                missing.append(f"{f.relative_to(ROOT).as_posix()}  <- run {_NB01}")
        f = R04 / "events" / f"{s}_event_audit.json"
        if not f.exists():
            missing.append(f"{f.relative_to(ROOT).as_posix()}  <- run {_NB04}")
        raw = R04 / "raw_extractions"
        if not any((raw / f"{n}_ERA5_UC_daily_{STUDY_YEAR}.csv").exists() for n in (c, s)):
            missing.append(f"{(raw / f'{s}_ERA5_UC_daily_{STUDY_YEAR}.csv').relative_to(ROOT).as_posix()}"
                           f"  <- run {_NB04}")
    zdir = R05 / "population_100m" / "zones"
    if zdir.exists():
        files = sorted(zdir.glob("*.csv"))
        have = (set(pd.concat([pd.read_csv(f, usecols=["city"]) for f in files])["city"].astype(str))
                if files else set())
        for c in sorted(set(cities) - have):
            missing.append(f"population_100m/zones: no zone totals for {c}  <- run {_POP}")
    return missing


# ── content fingerprint: what "the same version" means ──────────────────────
# A GeoPackage can differ byte-wise while holding identical data (SQLite page layout,
# timestamps, R-tree order), so MD5s verify a download and the fingerprint decides whether
# two builds hold the same dataset. It is computed from the written files, never from the
# frames in memory, so both sides of a comparison pass through the same reader.
def _canon(v) -> str:
    """One value as text: the same datum always serialises the same way."""
    if v is None or v is pd.NA or v is pd.NaT:
        return ""
    if isinstance(v, (bool, np.bool_)):
        return "true" if v else "false"
    if isinstance(v, (float, np.floating)):
        return "" if np.isnan(v) else format(float(v), FP_FLOAT)
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    if isinstance(v, (bytes, bytearray)):
        return bytes(v).hex()
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


def _canon_column(s: pd.Series) -> list[str]:
    if isinstance(s, gpd.GeoSeries) or str(getattr(s, "dtype", "")) == "geometry":
        import shapely
        arr = np.array(list(s), dtype=object)
        wkb = shapely.to_wkb(arr, hex=True, output_dimension=2, byte_order=1)
        return ["" if w is None else w for w in wkb]
    return [_canon(v) for v in s.tolist()]


def _canon_rows(df: pd.DataFrame) -> list[str]:
    """Rows in canonical form, sorted, so row order never changes the digest."""
    cols = list(df.columns)
    if not cols or not len(df):
        return []
    rows = ["\x1f".join(t) for t in zip(*[_canon_column(df[c]) for c in cols])]
    rows.sort()
    return rows


def _read_layer(gpkg: Path, name: str, spatial: bool) -> pd.DataFrame:
    return (pyogrio.read_dataframe(gpkg, layer=name) if spatial
            else pyogrio.read_dataframe(gpkg, layer=name, read_geometry=False))


def _layers_of(gpkg: Path) -> dict[str, str | None]:
    return {str(n): (None if t is None else str(t)) for n, t in pyogrio.list_layers(gpkg)}


def _stable_info(df: pd.DataFrame) -> pd.DataFrame:
    return df[~df["key"].astype(str).isin(FP_VOLATILE_KEYS)].reset_index(drop=True)


def _canon_dictionary(path: Path) -> pd.DataFrame:
    """The data dictionary as published, minus the one cell that restates dataset_info.

    The dataset_info value range lists build-specific values (version, DOI, commit), so it
    is blanked; every other description, unit, range and provenance cell counts.
    """
    dd = pd.read_csv(path, dtype=str, keep_default_na=False)
    dd.loc[dd["layer"] == "dataset_info", "allowed_values_or_range"] = ""
    return dd


def _digest(name: str, df: pd.DataFrame, extra: str = "") -> str:
    h = hashlib.sha256()
    h.update(f"layer:{name}\n{extra}columns:{json.dumps(list(df.columns))}\n"
             f"rows:{len(df)}\n".encode("utf-8"))
    for r in _canon_rows(df):
        h.update(r.encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def layer_digests(package_dir: Path) -> dict[str, str]:
    """One SHA-256 per layer and one for the data dictionary."""
    package_dir = Path(package_dir)
    gpkg = package_dir / f"{DATASET_STEM}.gpkg"
    out = {}
    for name, gtype in sorted(_layers_of(gpkg).items()):
        df = _read_layer(gpkg, name, gtype is not None)
        if name == "dataset_info":
            df = _stable_info(df)
        crs = pyogrio.read_info(gpkg, layer=name).get("crs") or ""
        out[name] = _digest(name, df, f"crs:{crs}\ngeometry:{gtype}\n")
    dd = package_dir / "data_dictionary.csv"
    if dd.exists():
        out["data_dictionary.csv"] = _digest("data_dictionary.csv", _canon_dictionary(dd))
    return out


def _combine(digests: dict[str, str]) -> str:
    h = hashlib.sha256()
    for k in sorted(digests):
        h.update(f"{k}:{digests[k]}\n".encode("utf-8"))
    return h.hexdigest()


def content_fingerprint(package_dir) -> str:
    """SHA-256 over the canonical data: every layer (rows sorted, columns in schema order,
    floats to 12 significant digits, geometry as little-endian 2-D WKB), scenario_config
    and the data dictionary. Build date, commit, checksums and the fingerprint itself are
    excluded, so the same inputs and settings always give the same value."""
    return _combine(layer_digests(Path(package_dir)))


# ── comparing two packages: the CHANGES_REPORT ──────────────────────────────
_EXTRA_KEYS = {"composite_trend_statistics": ["composite_type", "composite_key", "zone", "period"]}


def _diff_keys() -> dict[str, list[str]]:
    import warnings as _w
    with _w.catch_warnings():               # compare_to_archive silences warnings on import
        sys.path.insert(0, str(ROOT / "scripts"))
        from compare_to_archive import KEYS
    return {**KEYS, **_EXTRA_KEYS}


def _key_for(layer: str, cols: set, keys: dict) -> list[str]:
    k = list(keys.get(layer, []))
    for extra in ("scenario_id", "study_year"):
        if extra in cols and extra not in k:
            k.append(extra)
    return k if k and all(c in cols for c in k) else []


def _plain(k):
    """A key value as it reads in a report: numpy scalars as plain numbers."""
    if isinstance(k, tuple):
        return "(" + ", ".join(str(x.item() if hasattr(x, "item") else x) for x in k) + ")"
    return str(k.item() if hasattr(k, "item") else k)


def _compare_frames(name: str, new: pd.DataFrame, old: pd.DataFrame, key: list[str]):
    """(summary row, detail lines) for one layer present in both packages."""
    nf, of = list(new.columns), list(old.columns)
    gained = [c for c in nf if c not in of]
    lost = [c for c in of if c not in nf]
    row = {"layer": name, "rows_deposit": len(old), "rows_staging": len(new),
           "fields_added": ", ".join(gained), "fields_removed": ", ".join(lost),
           "fields_changed": "", "rows_added": 0, "rows_removed": 0}
    lines = [f"- `{name}`: field added `{c}`" for c in gained]
    lines += [f"- `{name}`: field removed `{c}`" for c in lost]
    shared = [c for c in nf if c in of and c not in key]
    if key and not new.duplicated(key).any() and not old.duplicated(key).any():
        nm, om = new.set_index(key), old.set_index(key)
        add, rem = nm.index.difference(om.index), om.index.difference(nm.index)
        row["rows_added"], row["rows_removed"] = len(add), len(rem)
        if len(add):
            lines.append(f"- `{name}`: {len(add)} row(s) added, e.g. {key} = {_plain(add[0])}")
        if len(rem):
            lines.append(f"- `{name}`: {len(rem)} row(s) removed, e.g. {key} = {_plain(rem[0])}")
        common = nm.index.intersection(om.index)
        nm, om = nm.loc[common], om.loc[common]
        changed = []
        for c in shared:
            a, b = _canon_column(nm[c]), _canon_column(om[c])
            bad = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
            if not bad:
                continue
            changed.append(c)
            i = bad[0]
            if c == "geometry":
                ex = "geometry differs"
            else:
                ex = f"{b[i] or 'null'} -> {a[i] or 'null'}"
            worst = ""
            if c != "geometry" and pd.api.types.is_numeric_dtype(nm[c]) \
                    and pd.api.types.is_numeric_dtype(om[c]) \
                    and not pd.api.types.is_bool_dtype(nm[c]):
                d = (pd.to_numeric(nm[c], errors="coerce")
                     - pd.to_numeric(om[c], errors="coerce")).abs()
                if d.notna().any():
                    worst = f"; worst |difference| {d.max():.6g}"
            lines.append(f"- `{name}.{c}`: {len(bad)} value(s) differ{worst}; "
                         f"e.g. {key} = {_plain(common[i])}: {ex}")
        row["fields_changed"] = ", ".join(changed)
    else:
        a, b = set(_canon_rows(new[shared])), set(_canon_rows(old[shared]))
        row["rows_added"], row["rows_removed"] = len(a - b), len(b - a)
        if a != b:
            lines.append(f"- `{name}`: {len(a - b)} row(s) only in staging, {len(b - a)} only "
                         f"in the deposit (no unique key; compared as whole rows)")
    return row, lines


def diff_packages(new_dir: Path, old_dir: Path) -> tuple[pd.DataFrame, list[str]]:
    """Every layer, field and dictionary entry that differs between two package folders."""
    ng, og = new_dir / f"{DATASET_STEM}.gpkg", old_dir / f"{DATASET_STEM}.gpkg"
    nl, ol = _layers_of(ng), _layers_of(og)
    nd, od = layer_digests(new_dir), layer_digests(old_dir)
    keys = _diff_keys()
    rows, lines = [], []
    for name in sorted(set(nl) | set(ol)):
        if name not in ol:
            n = len(_read_layer(ng, name, nl[name] is not None))
            rows.append({"layer": name, "rows_deposit": 0, "rows_staging": n, "rows_added": n})
            lines.append(f"- `{name}`: new layer ({n:,} rows)")
            continue
        if name not in nl:
            rows.append({"layer": name, "rows_deposit": len(_read_layer(og, name, False)),
                         "rows_staging": 0})
            lines.append(f"- `{name}`: layer removed")
            continue
        if nd.get(name) == od.get(name):
            continue
        new = _read_layer(ng, name, nl[name] is not None)
        old = _read_layer(og, name, ol[name] is not None)
        if name == "dataset_info":
            new, old = _stable_info(new), _stable_info(old)
        r, ls = _compare_frames(name, new, old,
                                _key_for(name, set(new.columns) & set(old.columns), keys))
        rows.append(r)
        lines += ls or [f"- `{name}`: digest differs (CRS or geometry type)"]
    if nd.get("data_dictionary.csv") != od.get("data_dictionary.csv"):
        n_dd = _canon_dictionary(new_dir / "data_dictionary.csv")
        o_dd = _canon_dictionary(old_dir / "data_dictionary.csv")
        r, ls = _compare_frames("data_dictionary.csv", n_dd, o_dd, ["layer", "field"])
        rows.append(r)
        lines += ls
    return pd.DataFrame(rows), lines



META_LAYERS = {"dataset_info", "data_dictionary.csv"}


def write_changes_report(path: Path, table: pd.DataFrame, lines: list[str], header: list[str]):
    """Field-by-field record of a build against the deposit: data layers first, then the
    metadata (dataset_info and the data dictionary), so a value change is never buried."""
    def _tab(t):
        if not len(t):
            return ["None."]
        t = t.fillna("")
        cols = list(t.columns)
        return (["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
                + ["| " + " | ".join(str(v) for v in r) + " |" for r in t.itertuples(index=False)])
    is_meta = table["layer"].isin(META_LAYERS) if len(table) else pd.Series(dtype=bool)
    data_t = table[~is_meta] if len(table) else table
    meta_t = table[is_meta] if len(table) else table
    meta_names = tuple(f"`{m}" for m in META_LAYERS)
    data_l = [l for l in lines if not l[2:].startswith(meta_names)]
    meta_l = [l for l in lines if l[2:].startswith(meta_names)]
    out = list(header)
    out += ["", "## Data layers that differ", ""] + _tab(data_t)
    out += ["", "## Metadata that differs (dataset_info, data dictionary)", ""] + _tab(meta_t)
    out += ["", "## Every difference: data layers", ""] + (data_l or ["None."])
    out += ["", "## Every difference: metadata", ""] + (meta_l or ["None."]) + [""]
    path.write_text("\n".join(out), encoding="utf-8", newline="\n")


# ── deterministic writing helpers ───────────────────────────────────────────
def _gpkg_timestamp(build_date: str) -> str:
    return f"{build_date}T00:00:00.000Z"


def _stamp_gpkg(gpkg: Path, build_date: str) -> None:
    """Pin gpkg_contents.last_change to the version's build date, whatever wrote last."""
    import sqlite3
    con = sqlite3.connect(str(gpkg))
    try:
        con.execute("UPDATE gpkg_contents SET last_change = ?", (_gpkg_timestamp(build_date),))
        con.commit()
    finally:
        con.close()


def _set_info(gpkg: Path, key: str, value: str) -> None:
    import sqlite3
    con = sqlite3.connect(str(gpkg))
    try:
        cur = con.execute('UPDATE "dataset_info" SET "value" = ? WHERE "key" = ?', (value, key))
        if cur.rowcount == 0:
            con.execute('INSERT INTO "dataset_info" ("key", "value") VALUES (?, ?)', (key, value))
        con.commit()
    finally:
        con.close()


def read_info(package_dir: Path) -> dict:
    """dataset_info of a package folder as a dict; empty when there is no package."""
    gpkg = Path(package_dir) / f"{DATASET_STEM}.gpkg"
    if not gpkg.exists():
        return {}
    d = pyogrio.read_dataframe(gpkg, layer="dataset_info", read_geometry=False)
    return dict(zip(d["key"].astype(str), d["value"].astype(str)))


def _md5_listing(folder: Path) -> dict[str, str]:
    if not folder.exists():
        return {}
    return {p.relative_to(folder).as_posix(): md5(p)
            for p in sorted(folder.rglob("*")) if p.is_file()}



def _remove(p: Path, tries: int = 6) -> None:
    """Remove a file, or a folder's contents and then the folder, retrying.

    OneDrive and virus scanners hold fresh files and folders briefly. A file that stays
    locked is an error; an EMPTY folder that stays locked is left in place, because it holds
    nothing (a synced folder can keep a just-emptied directory locked for many seconds).
    """
    if p.is_dir():
        for q in sorted(p.iterdir()):
            _remove(q, tries)
        for i in range(tries):
            try:
                p.rmdir()
                return
            except FileNotFoundError:
                return
            except OSError:
                if i == tries - 1:
                    return                 # empty and still locked: harmless
                time.sleep(0.5 * (i + 1))
        return
    for i in range(tries):
        try:
            p.unlink()
            return
        except FileNotFoundError:
            return
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(0.5 * (i + 1))


def _holds_files(root: Path) -> bool:
    return any(q.is_file() for q in root.rglob("*"))


def _clear_staging(root: Path) -> None:
    """Empty a staging folder this build created (it holds the marker); nothing else."""
    if not (root.exists() and (root / STAGING_MARKER).exists()):
        return
    for p in list(root.iterdir()):
        if p.name != STAGING_MARKER:
            _remove(p)
    _remove(root / STAGING_MARKER)
    try:
        root.rmdir()
    except OSError:
        pass          # a synced folder can keep the empty directory locked; empty is clear


def _prepare_staging(root: Path) -> Path:
    """Fresh staging folder. Only a folder this build created (it holds the marker) is cleared."""
    if root.exists():
        if (root / STAGING_MARKER).exists():
            _clear_staging(root)
        elif _holds_files(root):            # empty folders left by a locked clear are fine
            raise SystemExit(f"{root} holds files this build did not create; "
                             f"move it aside first")
    root.mkdir(parents=True, exist_ok=True)
    (root / STAGING_MARKER).write_text("created by scripts/build_master_summary.py\n",
                                       encoding="utf-8", newline="\n")
    return root


# ── the build itself ────────────────────────────────────────────────────────
def _assemble(deposit_gpkg: Path):
    """Every layer from the caches, merged with any other scenario already in the deposit."""
    scenario_id, scen_df = capture_scenario()
    log(f"  scenario_id {scenario_id}  "
        f"({scen_df.set_index('parameter').loc['city_selection_mode', 'value']}, "
        f"study year {scen_df.set_index('parameter').loc['study_year', 'value']})")
    ref = load_reference()
    log(f"  reference: {len(ref)} cities")

    zones = build_city_zones(ref)
    spots = build_spots(ref)
    key = build_participant_key(ref)
    _gps = build_gps(ref, key, zones)   # released, rounded coordinates; feeds the hit rates

    layers = {
        "city_zones": zones,
        "city_profile": build_city_profile(ref, zones),
        "city_year_summary": build_city_year_summary(ref, spots),
        "trend_statistics": build_trend_statistics(ref),
        "composite_trend_statistics": None,   # needs annual_series; filled below
        "annual_series": build_annual_series(ref),
        "monthly_series": None,
        "monthly_climatology": None,
        "heat_event_catalogue": build_heat_events(ref),
        "spot_occurrence": build_spot_occurrence(ref, spots),
        "spots": spots,
        "spot_contours": build_contours(ref),
        "stakeholder_spots_gps": _gps,
        "stakeholder_perception": build_perception(ref, key),
        "hitrate_sensitivity": build_hitrate(ref, spots, _gps),
        "city_exposure_by_contour": build_halfdonut(ref),
    }
    layers["monthly_series"], layers["monthly_climatology"] = build_monthly(ref)
    layers["composite_trend_statistics"] = build_composite_trends(layers["annual_series"])

    # stamp the scenario on every data layer, then accumulate rather than overwrite: the
    # other scenarios and years come from the DEPOSIT, never from an earlier staging build
    for _n, _d in layers.items():
        if _d is None or "scenario_id" in getattr(_d, "columns", []):
            continue
        _d["scenario_id"] = scenario_id
        layers[_n] = _d[["scenario_id"] + [c for c in _d.columns if c != "scenario_id"]]
    study_years = {int(y) for y in layers["spots"]["study_year"].dropna().unique()}
    layers = merge_with_existing(layers, deposit_gpkg, scenario_id, study_years)
    layers["scenario_config"] = scen_df
    return layers, ref, key, scenario_id, scen_df


SOURCES = {
    "city_zones": "NB01 `{slug}_{zone}_102022_v5.geojson` + `zone_area_summary_with_pop.csv`",
    "city_profile": "NB01 `city_cluster25_lookup.csv`, `zone_area_summary_with_pop.csv`, `cluster25_uc_distribution.csv`; NB04 `city_heat_event_summary.csv`; NB02 `Cities_Stakeholder_Points_2024.geojson`; spot counts from the `spots` layer",
    "city_year_summary": "NB04 `city_heat_event_summary.csv` (ERA5-Land persistence, selected events, MODIS<->ERA5-Land comparison); validation_tier and bh_any derived in-build; spot counts from the `spots` layer",
    "trend_statistics": "NB03 `all_cities_temporal_annual.csv` (uc/bra/cr) + `all_cities_delta_annual.csv` (suhii)",
    "composite_trend_statistics": "derived in-build from the `annual_series` layer by src/temporal_analysis.run_trend_analysis",
    "annual_series": "NB03 `all_cities_temporal_annual.csv` + `all_cities_delta_annual.csv`",
    "monthly_series": "NB03 `all_cities_temporal_monthly.csv` + `all_cities_delta_monthly.csv`",
    "monthly_climatology": "derived from `monthly_series` (calendar-month mean)",
    "heat_event_catalogue": "NB04 `events/{city}_event_audit.json` (56 files)",
    "spot_occurrence": "NB05 `spot_comprehensive_summary.csv` on a full 56x2x2 grid + counts from `spots`",
    "spots": "NB05 `all_cities_spots.geojson`",
    "spot_contours": "NB05 `master_thermal_spots.gpkg::hotspot_contours` (hot and cold)",
    "stakeholder_spots_gps": "NB05 `master_thermal_spots.gpkg::stakeholder_{hot,cold}spot_gps`, keys only",
    "stakeholder_perception": "NB02 `Stakeholder_Perception_Data_2024.csv` + `workshop_attendees_clean.csv`",
    "hitrate_sensitivity": "derived in-build by scripts/compute_hitrate.py from the published `spots` and `stakeholder_spots_gps` layers",
    "city_exposure_by_contour": "NB05 `halfdonut_city_summary.csv`",
    "dataset_info": "generated by this script",
    "scenario_config": "config.py, src/daily_analysis_utils.py and NB05 constants, captured at build time",
}

_FIXED_DEVIATIONS = [
    "`spots`: geom_75_wkt and geom_90_wkt were dropped. They averaged ~1.9 kB per row and "
    "the L75/L90 outlines are real geometries in `spot_contours`.",
    "`pct_dominant_class` is taken from NB01 cluster25_uc_distribution.csv (percent of the "
    "urban core in the assigned Cluster25). The like-named field in master_thermal_spots holds "
    "a different, much smaller quantity and was not carried over.",
    "`heat_event_catalogue` covers every city that recorded at least one ERA5-Land "
    "persistent event, which in this release is all 56. A city with none would not be "
    "given placeholder event rows; its zero state is carried in "
    "city_year_summary.era5_*_n_persistent_events.",
    "Vector sources are stored in EPSG:4326; they are reprojected to " + CRS_ANALYSIS +
    " for the GeoPackage. Recorded area_km2 values are the originals computed in the "
    "analysis CRS and were not recomputed.",
]



def _write_data(layers, ref, scenario_id, scen_df, pkg_dir: Path, with_csv=False,
                with_geojson=False):
    """Data layers, dataset_info (identity rows still empty) and the data dictionary.

    Returns the layers with dataset_info, the dictionary and the content fingerprint, which
    is computed from the files as written. The identity rows are filled afterwards; they are
    excluded from the fingerprint, so filling them cannot change it.
    """
    pkg_dir.mkdir(parents=True, exist_ok=True)
    layers = dict(layers)
    layers["dataset_info"] = build_dataset_info(
        layers, n_cities=len(ref), n_clusters=int(ref["cluster25"].nunique()),
        study_years=sorted({int(y) for y in layers["spots"]["study_year"].dropna().unique()}),
        scenario_id=scenario_id, scen_df=scen_df)
    log("Layers:")
    # a fixed write timestamp; gpkg_contents.last_change is pinned to the build date at the end
    pyogrio.set_gdal_config_options({"OGR_CURRENT_DATE": _gpkg_timestamp("2000-01-01")})
    try:
        write_package(layers, pkg_dir, with_csv=with_csv, with_geojson=with_geojson)
    finally:
        pyogrio.set_gdal_config_options({"OGR_CURRENT_DATE": None})
    dd = build_dictionary(layers)
    dd.to_csv(pkg_dir / "data_dictionary.csv", index=False, encoding="utf-8", lineterminator="\n")
    log(f"  data dictionary: {len(dd)} field rows, {len(set(CHECKS))} [CHECK] items")
    fp = content_fingerprint(pkg_dir)
    log(f"  content fingerprint: sha256:{fp}")
    return layers, dd, fp


def _finish_staging(layers, dd, key, pkg_dir: Path, identity: dict, changelog: str):
    """Identity rows, documents, checksums and the build report, once the case is decided."""
    gpkg = pkg_dir / f"{DATASET_STEM}.gpkg"
    for k in IDENTITY_KEYS:                       # always all five, always in this order
        _set_info(gpkg, k, identity[k])
    _stamp_gpkg(gpkg, identity["build_date"])
    (pkg_dir / "data_dictionary.md").write_text(dictionary_md(dd), encoding="utf-8", newline="\n")

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

    DEVIATIONS.extend(d for d in _FIXED_DEVIATIONS if d not in DEVIATIONS)
    (pkg_dir / "CHANGELOG.md").write_text(changelog, encoding="utf-8", newline="\n")
    write_licence(pkg_dir)
    # README last of the documents, so its layer table sees the final layer set.
    write_readme(layers, pkg_dir, gpkg, fp=identity["content_fingerprint"].replace("sha256:", ""))
    n = write_checksums(pkg_dir)
    log(f"  checksums: {n} files")
    write_build_report(layers, dd, pkg_dir, SOURCES)
    log(f"  deviations: {len(DEVIATIONS)} | [CHECK] items: {len(set(CHECKS))}")


# ── the deposit being replaced is kept; staging becomes the deposit ────────
def _free(path: Path) -> Path:
    n, p = 2, path
    while p.exists():
        p, n = path.with_name(f"{path.name}_{n}"), n + 1
    return p


def _promote(pkg_dir: Path, staging_root: Path, deposit_dir: Path, dep_info: dict) -> str | None:
    """Keep the current deposit whole in _superseded_build_<its build date>/, then make the
    staging build the deposit: GeoPackage, dictionary, README, CHANGELOG, LICENSE, and the
    checksums, written last. Returns the folder the old deposit was moved to."""
    keep = None
    if (deposit_dir / f"{DATASET_STEM}.gpkg").exists():
        keep = _free(deposit_dir.parent / f"_superseded_build_{dep_info.get('build_date', 'undated')}")
        shutil.copytree(deposit_dir, keep)
        log(f"  kept the replaced deposit in {keep}")
        for p in list(deposit_dir.iterdir()):        # copied above, so this is a move
            _remove(p)
        old_rep = deposit_dir.parent / BUILD_DIR_NAME / "build_report.md"
        if old_rep.exists():
            shutil.copy2(old_rep, _free(old_rep.with_name(f"build_report{keep.name}.md")))
    deposit_dir.mkdir(parents=True, exist_ok=True)
    for p in pkg_dir.iterdir():
        if p.name == "checksums_md5.txt":
            continue
        (shutil.copytree(p, deposit_dir / p.name) if p.is_dir()
         else shutil.copy2(p, deposit_dir / p.name))
    write_checksums(deposit_dir)                     # last, LF
    rep = staging_root / BUILD_DIR_NAME / "build_report.md"
    if rep.exists():
        (deposit_dir.parent / BUILD_DIR_NAME).mkdir(parents=True, exist_ok=True)
        shutil.copy2(rep, deposit_dir.parent / BUILD_DIR_NAME / "build_report.md")
    return str(keep) if keep else None


def _manifest_ok(package_dir: Path) -> tuple[int, int]:
    """(files verified, files listed) for checksums_md5.txt, as `md5sum -c` would count them."""
    lines = (package_dir / "checksums_md5.txt").read_text(encoding="utf-8").splitlines()
    ok = sum(1 for l in lines if "  " in l
             and md5(package_dir / l.split("  ", 1)[1]) == l.split("  ", 1)[0])
    return ok, len(lines)


@dataclass
class BuildReport:
    """What one build did. `case`: reproduced, values_changed, new_scenario or no_deposit.
    `deposit_changed` says whether the deposit was updated (only after QA passed)."""
    case: str
    message: str
    build_date: str
    scenario_id: str
    fingerprint: str
    deposit_dir: str
    compared_with: str = ""
    previous_fingerprint: str | None = None
    deposit_fingerprint: str | None = None
    deposit_fingerprint_stored: str | None = None
    staging_dir: str | None = None
    changes_report: str | None = None
    deposit_changed: bool = False
    superseded_to: str | None = None
    qa: dict = field(default_factory=dict)
    manifest: str = ""
    n_layers: int = 0
    n_records: int = 0
    n_fields: int = 0
    data_changes: list = field(default_factory=list)
    metadata_changes: list = field(default_factory=list)
    changes_table: list = field(default_factory=list)
    records_added: dict = field(default_factory=dict)
    md5_before: dict = field(default_factory=dict)
    md5_after: dict = field(default_factory=dict)
    seconds: float = 0.0

    @property
    def changes(self) -> list:
        return self.data_changes + self.metadata_changes

    def summary(self) -> pd.DataFrame:
        rows = [("case", self.case), ("message", self.message),
                ("build date", self.build_date), ("scenario_id", self.scenario_id),
                ("fingerprint (this build)", f"sha256:{self.fingerprint}"),
                ("fingerprint (deposit before the build)",
                 f"sha256:{self.deposit_fingerprint}" if self.deposit_fingerprint else "-"),
                ("CHANGELOG compares with", self.compared_with or "-"),
                ("layers / records / fields",
                 f"{self.n_layers} / {self.n_records:,} / {self.n_fields}"),
                ("QA on the staging build",
                 f"{self.qa['passed']}/{self.qa['total']} passed" if self.qa else "not run"),
                ("deposit updated", "yes" if self.deposit_changed else "no"),
                ("old deposit kept in", self.superseded_to or "-"),
                ("checksums_md5.txt", self.manifest or "-"),
                ("changes in data layers", f"{len(self.data_changes)} line(s)"),
                ("changes in metadata", f"{len(self.metadata_changes)} line(s)"),
                ("changes report", self.changes_report or "-"),
                ("staging", self.staging_dir or "cleared"),
                ("run time", f"{self.seconds:.0f} s")]
        if self.records_added:
            rows.append(("records added (new scenario)",
                         ", ".join(f"{k} {v}" for k, v in self.records_added.items())))
        return pd.DataFrame(rows, columns=["item", "value"])

    def __str__(self) -> str:
        return self.summary().to_string(index=False)


def build_dataset(out_dir=DEPOSIT_DIR, build_date=None, *, staging_dir=None, compare_only=False,
                  keep_staging=False, with_csv=False, with_geojson=False) -> BuildReport:
    """Build the dataset into staging, compare it with the deposit, and act on the result.

    - identical content (same fingerprint): nothing is touched;
    - different content: QA runs on the staging build; if it passes, the deposit is kept in
      _superseded_build_<date>/ and replaced by the staging build with all its files; if QA
      fails, the deposit is not touched and staging is kept for inspection.

    No version is named here: versions are named on Zenodo. `compare_only` builds and compares
    but never runs QA or updates the deposit (QA's own rebuild uses it).
    """
    global BUILD_DATE
    t0 = time.time()
    LOG.clear(); DEVIATIONS.clear(); CHECKS.clear()
    deposit_dir = Path(out_dir).resolve()
    staging_root = Path(staging_dir).resolve() if staging_dir else STAGING_DIR
    pkg_dir = staging_root / DATASET_DIR
    today = date.today().isoformat()

    missing = preflight()
    if missing:
        raise SystemExit("Pre-flight failed: these inputs are missing, so no dataset was built.\n  "
                         + "\n  ".join(missing))
    dep_gpkg = deposit_dir / f"{DATASET_STEM}.gpkg"
    dep_info = read_info(deposit_dir)
    md5_before = _md5_listing(deposit_dir)
    history = changelog_history(deposit_dir)
    prev = previous_entry(history)

    log(f"Building -> staging {pkg_dir}")
    _prepare_staging(staging_root)
    layers, ref, key, scenario_id, scen_df = _assemble(dep_gpkg)
    layers, dd, fp = _write_data(layers, ref, scenario_id, scen_df, pkg_dir,
                                 with_csv, with_geojson)

    have_deposit = dep_gpkg.exists()
    fp_dep = content_fingerprint(deposit_dir) if have_deposit else None
    stored = dep_info.get("content_fingerprint", "")
    dep_sids = (set(pyogrio.read_dataframe(dep_gpkg, layer="scenario_config",
                                           read_geometry=False)["scenario_id"].astype(str))
                if have_deposit else set())
    same = have_deposit and fp == fp_dep
    table, lines = (diff_packages(pkg_dir, deposit_dir) if have_deposit and not same
                    else (pd.DataFrame(), []))

    # ── identity and CHANGELOG, decided now that the content is known ──
    if same:
        case = "reproduced"
        BUILD_DATE = dep_info.get("build_date") or today
        prev_fp = dep_info.get("previous_fingerprint", "")
        changelog = ((deposit_dir / "CHANGELOG.md").read_text(encoding="utf-8")
                     .replace("\r\n", "\n") if (deposit_dir / "CHANGELOG.md").exists() else "")
    else:
        case = ("no_deposit" if not have_deposit
                else "values_changed" if scenario_id in dep_sids else "new_scenario")
        BUILD_DATE = build_date or today
        prev_fp = f"sha256:{prev['fingerprint']}"
        body = (NOTES_SINCE_1_0_0.replace("{n_comp}",
                                          str(len(layers["composite_trend_statistics"])))
                if prev["fingerprint"] == V100_FINGERPRINT else draft_from_changes(table))
        changelog = assemble_changelog(BUILD_DATE, fp, prev, body, history)
    identity = {"build_date": BUILD_DATE, "content_fingerprint": f"sha256:{fp}",
                "previous_fingerprint": prev_fp}
    _finish_staging(layers, dd, key, pkg_dir, identity, changelog)

    info = read_info(pkg_dir)
    meta_names = tuple(f"`{m}" for m in META_LAYERS)
    rep = BuildReport(case=case, message="", build_date=BUILD_DATE, scenario_id=scenario_id,
                      fingerprint=fp, deposit_dir=str(deposit_dir), compared_with=prev["line"],
                      previous_fingerprint=prev_fp or None, deposit_fingerprint=fp_dep,
                      deposit_fingerprint_stored=stored or None, staging_dir=str(staging_root),
                      n_layers=int(info.get("n_layers", 0)),
                      n_records=int(info.get("n_records_total", 0)),
                      n_fields=int(info.get("n_fields_total", 0)), md5_before=md5_before,
                      data_changes=[l for l in lines if not l[2:].startswith(meta_names)],
                      metadata_changes=[l for l in lines if l[2:].startswith(meta_names)],
                      changes_table=table.fillna("").to_dict("records") if len(table) else [])
    if stored and fp_dep and stored.replace("sha256:", "") != fp_dep:
        log(f"  [WARN] the deposit's stored fingerprint {stored} does not match its content "
            f"(sha256:{fp_dep})")
    if case == "new_scenario":
        g = pkg_dir / f"{DATASET_STEM}.gpkg"
        for name in _layers_of(g):
            d = _read_layer(g, name, False)
            if "scenario_id" in d.columns:
                n = int((d["scenario_id"].astype(str) == scenario_id).sum())
                if n:
                    rep.records_added[name] = n
    if len(table):
        write_changes_report(staging_root / "CHANGES_REPORT.md", table, lines, [
            "# Changes report — staging build against the deposit", "",
            f"- deposit: `{deposit_dir}` (built {dep_info.get('build_date', '?')}, sha256:{fp_dep})",
            f"- staging: `{pkg_dir}` (sha256:{fp})",
            f"- scenario_id: staging `{scenario_id}`; deposit {sorted(dep_sids)}",
            f"- case: **{case}**",
            f"- written {today} by `scripts/build_master_summary.py`"])
        rep.changes_report = str(staging_root / "CHANGES_REPORT.md")

    what = {"values_changed": "Values changed under the same settings",
            "new_scenario": f"New scenario_id {scenario_id} (a setting changed; "
                            f"{sum(rep.records_added.values()):,} records added)",
            "no_deposit": f"No deposit at {deposit_dir}"}.get(case, "")
    if same:
        rep.message = "Dataset reproduced (fingerprint identical); the deposit is not touched"
        if not keep_staging:
            _clear_staging(staging_root)
            rep.staging_dir = None
    elif compare_only:
        rep.message = f"{what}; compare only: QA not run and the deposit not touched"
    else:
        sys.path.insert(0, str(ROOT / "scripts"))
        from qa_master_summary import run_qa
        log("QA on the staging build:")
        q = run_qa(pkg_dir, write_report=True)
        rep.qa = {"ok": q["ok"], "passed": q["passed"], "total": q["total"],
                  "failed": [n for n, o, _ in q["checks"] if not o]}
        if not q["ok"]:
            rep.message = (f"{what}; QA FAILED on the staging build ({q['passed']}/{q['total']}): "
                           f"the deposit is not touched; staging kept for inspection")
        else:
            rep.superseded_to = _promote(pkg_dir, staging_root, deposit_dir, dep_info)
            after = content_fingerprint(deposit_dir)
            if after != fp:
                raise SystemExit(f"update check failed: deposit fingerprint {after} != {fp}")
            ok, n = _manifest_ok(deposit_dir)
            rep.manifest = f"{ok}/{n} files verify"
            if ok != n:
                raise SystemExit(f"update check failed: checksums_md5.txt verifies {ok}/{n}")
            if len(table):
                dst = _free(deposit_dir.parent / BUILD_DIR_NAME / f"CHANGES_REPORT_{BUILD_DATE}.md")
                shutil.copy2(staging_root / "CHANGES_REPORT.md", dst)
                rep.changes_report = str(dst)
            rep.deposit_changed = True
            rep.message = (f"{what}; QA passed on the staging build ({q['passed']}/{q['total']}); "
                           f"deposit updated (sha256:{fp})"
                           + (f"; the previous deposit is kept in {Path(rep.superseded_to).name}/"
                              if rep.superseded_to else ""))
            _clear_staging(staging_root)
            rep.staging_dir = None

    rep.md5_after = _md5_listing(deposit_dir)
    if not rep.deposit_changed and rep.md5_after != md5_before:
        raise SystemExit("the deposit changed during a build that did not update it")
    rep.seconds = time.time() - t0
    log(rep.message)
    return rep


# ── the inputs NB05 §9 shares with the build ────────────────────────────────
def prepare_spot_footprints() -> gpd.GeoDataFrame:
    """NB05's L50 spot footprints exactly as the build publishes them (`spots`)."""
    return build_spots(load_reference())


def prepare_cohort_points(sources=None) -> gpd.GeoDataFrame:
    """The cohort points exactly as the build publishes them (`stakeholder_spots_gps`): the
    cohort filter, the city and the rounding to GPS_DECIMALS are this module's own.

    `sources` = {"hot": df, "cold": df} passes NB05's in-memory tables, which §10 later writes
    to the working GeoPackage; without it the points are read from that GeoPackage.
    """
    ref = load_reference()
    return build_gps(ref, build_participant_key(ref), build_city_zones(ref), sources=sources)


# ── a whole-dataset summary, for NB05 §14b ──────────────────────────────────
def summarise_package(package_dir=DEPOSIT_DIR) -> dict:
    """Identity, one row per layer, key counts and the MD5 table of a package folder."""
    package_dir = Path(package_dir)
    gpkg = package_dir / f"{DATASET_STEM}.gpkg"
    info = read_info(package_dir)
    sid = info.get("scenario_id")
    keys = _diff_keys()
    rows, frames = [], {}
    for name, gtype in _layers_of(gpkg).items():
        df = _read_layer(gpkg, name, False)
        sub = (df[df["scenario_id"].astype(str) == str(sid)]
               if sid and "scenario_id" in df.columns else df)
        frames[name] = sub
        cols = set(df.columns) | ({"geometry"} if gtype else set())
        k = _key_for(name, cols, keys)
        rows.append({"layer": name, "rows": len(df),
                     "fields": len(df.columns) + (1 if gtype else 0),
                     "geometry": gtype or "no",
                     "crs": pyogrio.read_info(gpkg, layer=name).get("crs") or "-",
                     "key fields": ", ".join(k) or "-",
                     "cities": sub["city_slug"].nunique() if "city_slug" in sub else "",
                     "periods": sub["period"].nunique() if "period" in sub else "",
                     "spot types": sub["spot_type"].nunique() if "spot_type" in sub else ""})
    prof, gps = frames["city_profile"], frames["stakeholder_spots_gps"]
    absorbed = sorted({n.strip() for s_ in prof["absorbed_cities"].dropna()
                       for n in str(s_).split(";") if n.strip()})
    counts = {"layers": len(rows), "cities": len(prof),
              "clusters": int(prof["cluster25"].nunique()),
              "candidates": int(info.get("n_candidate_cities", 0) or 0),
              "absorbed": len(absorbed), "spots": len(frames["spots"]),
              "contours": len(frames["spot_contours"]),
              "heat_events": len(frames["heat_event_catalogue"]),
              "participants": len(frames["stakeholder_perception"]),
              "points": len(gps), "points_hot": int((gps["spot_type"] == "hot").sum()),
              "points_cold": int((gps["spot_type"] == "cold").sum()),
              "composite_trend_rows": len(frames["composite_trend_statistics"]),
              "hitrate_rows": len(frames["hitrate_sensitivity"])}
    stored = info.get("content_fingerprint", "")
    identity = pd.DataFrame(
        [("content fingerprint", stored or
          f"sha256:{content_fingerprint(package_dir)} (computed; this deposit does not store it)"),
         ("previous fingerprint", info.get("previous_fingerprint") or "-"),
         ("build date", info.get("build_date", "")),
         ("scenario_id", sid or "")], columns=["item", "value"])
    man = {}
    cm = package_dir / "checksums_md5.txt"
    if cm.exists():
        for ln in cm.read_text(encoding="utf-8").splitlines():
            if "  " in ln:
                d_, n_ = ln.split("  ", 1)
                man[n_.strip()] = d_
    md5_t = pd.DataFrame([{"file": f, "md5": h, "matches manifest":
                           ("(the manifest)" if f == "checksums_md5.txt" else man.get(f) == h)}
                          for f, h in _md5_listing(package_dir).items()])
    return {"identity": identity, "layers": pd.DataFrame(rows), "counts": counts,
            "md5": md5_t, "frames": frames, "info": info}


def normalise_text_files(package_dir) -> dict:
    """Rewrite every text file of a package with LF line endings, then the checksums, last.

    The GeoPackage is not touched and the content fingerprint must not move; both are
    checked. Returns the fingerprint and {file: (md5 before, md5 after)}.
    """
    package_dir = Path(package_dir)
    gpkg = package_dir / f"{DATASET_STEM}.gpkg"
    before, fp0, g0 = _md5_listing(package_dir), content_fingerprint(package_dir), md5(gpkg)
    for p in sorted(package_dir.iterdir()):
        if p.is_file() and p.suffix in {".md", ".txt", ".csv"} and p.name != "checksums_md5.txt":
            b = p.read_bytes()
            if b"\r\n" in b:
                p.write_bytes(b.replace(b"\r\n", b"\n"))
    write_checksums(package_dir)
    fp1 = content_fingerprint(package_dir)
    if fp1 != fp0 or md5(gpkg) != g0:
        raise SystemExit("line-ending rewrite changed the data; investigate before publishing")
    after = _md5_listing(package_dir)
    return {"fingerprint": fp1,
            "md5": {f: (before.get(f), after.get(f)) for f in sorted(set(before) | set(after))}}


# ── command line ────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(DEPOSIT_DIR),
                    help="the deposit folder: compared against, and updated when the content "
                         "differs and QA passes")
    ap.add_argument("--compare-only", action="store_true",
                    help="build and compare only: never run QA, never update the deposit")
    ap.add_argument("--with-csv", action="store_true", help="also write csv/ copies")
    ap.add_argument("--with-geojson", action="store_true", help="also write geojson/ copies")
    ap.add_argument("--staging", default=None,
                    help=f"staging folder (default {STAGING_DIR.relative_to(ROOT)})")
    ap.add_argument("--keep-staging", action="store_true",
                    help="keep staging even when the build reproduces the deposit")
    ap.add_argument("--build-date", default=None, help="override the build date (YYYY-MM-DD)")
    ap.add_argument("--report-json", default=None, help="also write the build report as JSON")
    ap.add_argument("--normalise-line-endings", action="store_true",
                    help="only rewrite the text files of --out with LF, then the checksums")
    a = ap.parse_args(argv)
    if a.normalise_line_endings:
        r = normalise_text_files(Path(a.out))
        print(f"fingerprint unchanged: sha256:{r['fingerprint']}")
        for f, (o, n) in r["md5"].items():
            print(f"  {f:55} {o}  ->  {n}{'' if o != n else '  (unchanged)'}")
        return 0
    rep = build_dataset(out_dir=a.out, build_date=a.build_date, staging_dir=a.staging,
                        compare_only=a.compare_only, keep_staging=a.keep_staging,
                        with_csv=a.with_csv, with_geojson=a.with_geojson)
    print("\n" + str(rep))
    if a.report_json:
        Path(a.report_json).write_text(json.dumps(asdict(rep), indent=1, default=str),
                                       encoding="utf-8", newline="\n")
    return 1 if rep.qa and not rep.qa["ok"] else 0


if __name__ == "__main__":
    sys.exit(main())
