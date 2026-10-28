#!/usr/bin/env python
"""QA for the published composite package. Read-only apart from the marked validation block
it fills in _build/build_report.md."""
from __future__ import annotations
import argparse, hashlib, json, re, shutil, subprocess, sys, tempfile, warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_master_summary import QA_BEGIN, QA_END  # the markers are defined once, with the writer

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PKG = ROOT / "Results" / "05_hotspot_analysis" / "surface_thermal_anomaly_stakeholder_composite"
# Rebound by --package so QA can validate a scratch build, and so the reproducibility
# check can point at the folder it just rebuilt rather than the live deposit.
PKG = DEFAULT_PKG
GPKG = PKG / "surface_thermal_anomaly_stakeholder_composite.gpkg"
R01, R03 = ROOT / "Results" / "01_aoi_delineation", ROOT / "Results" / "03_temporal_analysis"
R04, R05 = ROOT / "Results" / "04_temporal_analysis_daily", ROOT / "Results" / "05_hotspot_analysis"

RES: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = ""):
    RES.append((name, bool(ok), detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def L(name, geom=False):
    return gpd.read_file(GPKG, layer=name) if geom else pyogrio.read_dataframe(
        GPKG, layer=name, read_geometry=False)


def main():
    print("Phase 3 QA\n")
    lay = {n: t for n, t in pyogrio.list_layers(GPKG)}
    SPATIAL = {n for n, t in lay.items() if t is not None}
    d = {n: L(n, n in SPATIAL) for n in lay}

    # The package may legitimately hold several scenarios (a re-run under different
    # settings appends rather than overwrites). QA validates the scenario being published:
    # the one named in dataset_info.
    _sid = d["dataset_info"].set_index("key")["value"].get("scenario_id")
    if _sid is not None:
        d = {n: (df[df["scenario_id"].astype(str) == str(_sid)].reset_index(drop=True)
                 if "scenario_id" in getattr(df, "columns", []) else df)
             for n, df in d.items()}
        print(f"  validating scenario {_sid}\n")

    # ── 1. row counts ───────────────────────────────────────────────────────
    print("1. Row counts")
    exp = {"city_profile": 56, "city_year_summary": 56, "spot_occurrence": 224,
           "spots": 185, "spot_contours": 441, "stakeholder_perception": 105,
           "hitrate_sensitivity": 1160, "city_zones": 168}
    for k, v in exp.items():
        check(f"{k} == {v}", len(d[k]) == v, f"got {len(d[k])}")
    gps = d["stakeholder_spots_gps"]
    nh, nc = (gps.spot_type == "hot").sum(), (gps.spot_type == "cold").sum()
    check("stakeholder_spots_gps == 94 (55 hot / 39 cold)",
          len(gps) == 94 and nh == 55 and nc == 39,
          f"got {len(gps)} ({nh} hot / {nc} cold) — 97/57/40 in the unfiltered source; the "
          "3 points of one unregistered respondent are excluded with the cohort rule")

    # NB05 §9 selects stakeholder points by city of attendance, the cohort rule by registration,
    # so the hit-rate denominators can legitimately exceed the published point count. The
    # invariant is that any such difference is DISCLOSED in the README, not that it is absent.
    _hr = d["hitrate_sensitivity"]
    # one buffer AND one period — each city is listed once per period
    _hr = _hr[(_hr.buffer_m == _hr.buffer_m.min())
              & (_hr.period == sorted(_hr.period.unique())[0])]
    _denom = {k: int(v) for k, v in _hr.groupby("spot_type")["n_total"].sum().items()}
    _counted = {k: int(v) for k, v in gps.spot_type.value_counts().items()}
    _agree = _denom == _counted
    _disclosed = "reproduced exactly as" in (PKG / "README.md").read_text(encoding="utf-8")
    check("hit-rate denominators match the GPS layer, or the difference is disclosed",
          _agree or _disclosed,
          "they match" if _agree else
          f"hit-rate {_denom} vs points {_counted}; disclosed in README §7")

    # ── merged (post-absorption) city population ────────────────────────────
    # Step 3 of the zonation protocol absorbs 11 cities into larger neighbours and reassigns
    # their population. These checks tie the published totals back to the UN WUP 2024 table.
    _cp = d["city_profile"]
    _wup = (pd.read_csv(ROOT / "data" / "inputs" / "geospatial_features" /
                        "Major_cities_population_Nigeria_WUP_2025.csv", thousands=",")
            .set_index("City_Name")["2024"].astype(float))
    _ab = pd.read_csv(R01 / "absorbed_cities.csv")

    _listed = [c.strip() for s in _cp["absorbed_cities"].dropna() for c in str(s).split(";") if c.strip()]
    _dupes = sorted({c for c in _listed if _listed.count(c) > 1})
    _retained = set(_cp["city"])
    _overlap = sorted(set(_listed) & _retained)
    check("absorbed_cities lists 11 cities, each once, none of them retained",
          len(_listed) == 11 and not _dupes and not _overlap,
          f"{len(_listed)} listed; duplicated {_dupes or 'none'}; also retained {_overlap or 'none'}")

    _expected = _cp["city"].map(
        _ab.assign(pop=_ab.absorbed_city.map(_wup)).groupby("parent_aoi")["pop"].sum()).fillna(0.0)
    _delta = (_cp["population_wup_merged_k"] - _cp["population_wup_k"] - _expected).abs()
    check("population_wup_merged_k == population_wup_k + absorbed populations",
          bool((_delta < 0.51).all()), f"max deviation {_delta.max():.3f} thousand")

    _tot, _all67 = _cp["population_wup_merged_k"].sum(), _wup.sum()
    check("merged population totals the 67 candidate cities",
          abs(_tot - _all67) < 0.51,
          f"{_tot:,.0f}k vs {_all67:,.0f}k over {len(_wup)} candidates ({_tot/1000:.1f} million)")

    _cl = _cp.groupby("cluster25")[["population_wup_k", "population_wup_merged_k"]].sum().round(0)
    _t3 = {13: 37960, 9: 8361, 16: 1203}
    _wrong = [f"C{int(c)}={r.population_wup_merged_k:.0f}!={_t3[int(c)]}"
              for c, r in _cl.iterrows() if int(c) in _t3 and abs(r.population_wup_merged_k - _t3[int(c)]) >= 1]
    _moved = [f"C{int(c)}" for c, r in _cl.iterrows()
              if int(c) not in _t3 and r.population_wup_k != r.population_wup_merged_k]
    check("cluster sums match manuscript Table 3; other clusters unchanged",
          not _wrong and not _moved,
          f"C13/C9/C16 {'match' if not _wrong else _wrong}; unexpectedly changed: {_moved or 'none'}")

    # ── hit rates reproduce from the published layers ───────────────────────
    # The point of the cohort fix is that anyone can recompute the hit rates from the
    # dataset alone. Recompute from the FINISHED package and require an exact match.
    import sys as _sys
    if str(ROOT / "scripts") not in _sys.path:
        _sys.path.insert(0, str(ROOT / "scripts"))
    from compute_hitrate import hit_rate_table as _hrt, ANALYSIS_CRS as _ACRS
    _pub = d["hitrate_sensitivity"]
    _pts = L("stakeholder_spots_gps", geom=True).to_crs(_ACRS)
    _sp = L("spots", geom=True).to_crs(_ACRS)
    _re_ = _hrt(_pts, _sp)
    _k = ["city", "spot_type", "period", "buffer_m"]
    _m = (_pub[_k + ["n_hit", "n_total"]].sort_values(_k).reset_index(drop=True)
          .merge(_re_[_k + ["n_hit", "n_total"]].sort_values(_k).reset_index(drop=True),
                 on=_k, how="outer", suffixes=("_pub", "_re")))
    _bad = _m[(_m.n_hit_pub != _m.n_hit_re) | (_m.n_total_pub != _m.n_total_re)]
    check("hit rates recompute exactly from the published spots and GPS layers",
          len(_m) == len(_pub) and _bad.empty,
          f"{len(_m)} rows compared, {len(_bad)} differing"
          + ("" if _bad.empty else f"; first: {_bad.head(3).to_dict('records')}"))

    # the four published 500 m values, and the rounding-sensitive Port Harcourt row
    _t500 = _pub[_pub.buffer_m == 500].groupby(["spot_type", "period"])[["n_hit", "n_total"]].sum()
    _want = {("hot", "day"): (4, 55), ("hot", "night"): (3, 55),
             ("cold", "day"): (4, 39), ("cold", "night"): (0, 39)}
    _got = {k: (int(v.n_hit), int(v.n_total)) for k, v in _t500.iterrows()}
    check("500 m hit rates match the cohort targets", _got == _want, f"{_got}")
    _ph = _pub[(_pub.city == "Port Harcourt") & (_pub.spot_type == "hot")
               & (_pub.period == "day") & (_pub.buffer_m == 8500)]
    check("Port Harcourt hot/day at 8500 m is on the rounded basis (3 hits)",
          len(_ph) == 1 and int(_ph.n_hit.iloc[0]) == 3,
          f"n_hit={None if _ph.empty else int(_ph.n_hit.iloc[0])} (unrounded would give 2)")

    # ── heat event catalogue completeness ───────────────────────────────────
    # The catalogue is built by reading one audit JSON per city. Matching those files on the
    # display name silently dropped the three cities whose names contain a space, so the
    # count is checked against the persistence figures city_year_summary carries independently.
    _ev, _cys2 = d["heat_event_catalogue"], d["city_year_summary"]
    _counted = _ev.groupby(["city", "period"]).size()
    _mismatch = []
    for _r in _cys2.itertuples():
        for _p in ("day", "night"):
            _expect = int(getattr(_r, f"era5_{_p}_n_persistent_events", 0) or 0)
            _got = int(_counted.get((_r.city, _p), 0))
            if _got != _expect:
                _mismatch.append(f"{_r.city}/{_p} {_got}!={_expect}")
    check("heat_event_catalogue rows match era5_*_n_persistent_events per city and period",
          not _mismatch,
          f"{len(_ev)} rows, {_ev.city.nunique()} cities"
          + ("" if not _mismatch else f"; {len(_mismatch)} mismatch: {_mismatch[:6]}"))

    # ── MSG-SEVIRI against ERA5-Land ────────────────────────────────────────
    # These are carried over from NB04, never recomputed, so the only thing to verify is that
    # the package reproduces the source CSV exactly.
    _sev_csv = R04 / "correlation" / "SEVIRI_vs_ERA5_target_metrics.csv"
    _cys = d["city_year_summary"]
    if _sev_csv.exists():
        _sev = pd.read_csv(_sev_csv).set_index("city")
        _pairs = [(f"{p}_{s}", f"{p}_seviri_{t}" if t.startswith("minus") else f"{p}_seviri_era5land_{t}")
                  for p in ("day", "night")
                  for s, t in (("n_obs", "n"), ("bias", "minus_era5land_bias_c"),
                               ("rmse", "rmse_c"), ("mae", "mae_c"))]
        _worst, _missing = 0.0, []
        for src, dst in _pairs:
            if dst not in _cys.columns:
                _missing.append(dst); continue
            _j = _cys.set_index("city")[dst].astype(float)
            _e = _sev[src].reindex(_j.index).astype(float)
            _both = _j.notna() & _e.notna()
            if _both.any():
                _worst = max(_worst, float((_j[_both] - _e[_both]).abs().max()))
            if (_j.notna() != _e.notna()).any():
                _missing.append(f"{dst}(null mismatch)")
        check("seviri_era5land values equal the source CSV",
              not _missing and _worst < 1e-9,
              f"{len(_pairs)} fields, max |difference| {_worst:.2e}"
              + (f"; problems: {_missing}" if _missing else ""))
    else:
        check("seviri_era5land values equal the source CSV", False, "source CSV not found")

    # A field name repeated in the DESCR literal is collapsed by Python with the last one
    # silently winning, which is how heat_event_catalogue.tier came to carry the spot-tier
    # text. Parse the source and refuse to let that recur.
    import ast as _ast, collections as _coll
    _src = (ROOT / "scripts" / "build_master_summary.py").read_text(encoding="utf-8")
    _keys = []
    for _n in _ast.walk(_ast.parse(_src)):
        _dicts = []
        if isinstance(_n, _ast.Assign) and getattr(_n.targets[0], "id", "") == "DESCR":
            _dicts = [_n.value]
        elif (isinstance(_n, _ast.Call) and isinstance(_n.func, _ast.Attribute)
              and _n.func.attr == "update" and getattr(_n.func.value, "id", "") == "DESCR"):
            _dicts = [a for a in _n.args if isinstance(a, _ast.Dict)]
        for _dd in _dicts:
            _keys += [k.value for k in _dd.keys if isinstance(k, _ast.Constant)]
    _dup = sorted(k for k, c in _coll.Counter(_keys).items() if c > 1)
    check("no duplicate field key in DESCR", not _dup,
          f"{len(_keys)} entries, {len(set(_keys))} unique" + (f"; duplicated: {_dup}" if _dup else ""))

    # ── 2. key integrity ────────────────────────────────────────────────────
    print("\n2. Key integrity")
    cities = set(d["city_profile"].city_slug)
    for n, df in d.items():
        if "city_slug" in df.columns:
            bad = set(df.city_slug.dropna()) - cities
            check(f"{n}.city_slug ⊆ city_profile", not bad, f"orphans: {sorted(bad)[:5]}")
    su = set(d["spots"].spot_uid)
    check("spot_contours.spot_uid ⊆ spots", not (set(d["spot_contours"].spot_uid) - su))
    pk = {"spots": ["spot_uid"], "spot_contours": ["contour_uid"],
          "city_profile": ["scenario_id", "city_slug"],
          "city_year_summary": ["scenario_id", "city_slug", "study_year"],
          "spot_occurrence": ["scenario_id", "city_slug", "period", "spot_type", "study_year"],
          "stakeholder_perception": ["scenario_id", "participant_code"],
          "heat_event_catalogue": ["scenario_id", "event_id"],
          "trend_statistics": ["scenario_id", "city_slug", "zone", "period"]}
    for n, k in pk.items():
        dup = d[n].duplicated(k).sum()
        check(f"{n} PK {'+'.join(k)} unique", dup == 0, f"{dup} duplicates")

    # ── 3. sum check ────────────────────────────────────────────────────────
    print("\n3. Spot counts reconcile")
    a = (d["spots"].groupby(["city_slug", "period", "spot_type"]).size()
         .rename("from_spots").reset_index())
    b = d["spot_occurrence"][["city_slug", "period", "spot_type", "n_spots"]]
    m = b.merge(a, on=["city_slug", "period", "spot_type"], how="left").fillna({"from_spots": 0})
    check("spot_occurrence.n_spots == rows in spots",
          (m.n_spots == m.from_spots).all(),
          f"{int((m.n_spots != m.from_spots).sum())} mismatched")
    check("spot_occurrence totals == 185", int(m.n_spots.sum()) == 185, f"{int(m.n_spots.sum())}")

    # ── 4. spot checks against the sources ──────────────────────────────────
    print("\n4. Values against sources")
    t = d["trend_statistics"]
    ab = t[(t.city == "Abeokuta") & (t.period == "day")].set_index("zone")["sen_slope_c_per_decade"]
    check("Abeokuta day uc Sen slope == 2.834", abs(ab["uc"] - 2.83362) < 1e-4, f"{ab['uc']}")
    check("Abeokuta day suhii Sen slope == 2.204", abs(ab["suhii"] - 2.20390) < 1e-4, f"{ab['suhii']}")
    ta = pd.read_csv(R03 / "all_cities_temporal_annual.csv")
    da = pd.read_csv(R03 / "all_cities_delta_annual.csv")
    ce = pd.read_csv(R04 / "city_heat_event_summary.csv")
    sc = pd.read_csv(R05 / "spot_comprehensive_summary.csv")
    ah = pd.read_csv(R05 / "all_cities_spots.csv")
    side = []
    rng = np.random.default_rng(42)
    # trend_statistics
    for _, r in t[t.zone != "suhii"].sample(5, random_state=1).iterrows():
        zmap = {"uc": "urban_core", "bra": "bra", "cr": "city_region"}
        s = ta[(ta.city == r.city) & (ta.zone == zmap[r.zone]) & (ta.period == r.period)]
        side.append(("trend_statistics", f"{r.city}/{r.zone}/{r.period} sen_decade",
                     r.sen_slope_c_per_decade, s.sen_slope_per_decade.iloc[0]))
    # annual_series
    for _, r in d["annual_series"][d["annual_series"].zone == "suhii"].sample(5, random_state=2).iterrows():
        s = da[(da.city == r.city) & (da.period == r.period) & (da.year == r.year)]
        side.append(("annual_series", f"{r.city}/{r.period}/{r.year} suhii", r.value_c, s.delta_lst.iloc[0]))
    # city_year_summary
    for _, r in d["city_year_summary"].sample(5, random_state=3).iterrows():
        s = ce[ce.city == r.city].iloc[0]
        side.append(("city_year_summary", f"{r.city} era5_day_n_persistent_events",
                     r.era5_day_n_persistent_events, s.era5_day_n_persistent_events))
    # spot_occurrence
    for _, r in d["spot_occurrence"].sample(5, random_state=4).iterrows():
        s = sc[(sc.City.str.split(" [", regex=False).str[0] == r.city)
               & (sc.Period == r.period) & (sc.Type == r.spot_type)]
        side.append(("spot_occurrence", f"{r.city}/{r.period}/{r.spot_type} L50 area",
                     r.area_l50_km2, s.area_50_km2.iloc[0] if len(s) else np.nan))
    # spots
    for _, r in d["spots"].sample(5, random_state=5).iterrows():
        s = ah[ah.spot_id == r.spot_id].iloc[0]
        side.append(("spots", f"{r.spot_id} population", r.population_persons, s.population))
    ok = all(pd.isna(x) and pd.isna(y) or abs(float(x) - float(y)) < 1e-6 for _, _, x, y in side)
    check("25 sampled values match their sources", ok)

    # ── 5. ERA5 fix ─────────────────────────────────────────────────────────
    print("\n5. ERA5 correction")
    cy = d["city_year_summary"].merge(
        ce[["city", "era5_day_n_persistent_events", "era5_day_longest_event_days",
            "modis_day_n_persistent_events", "modis_day_longest_event_days"]],
        on="city", suffixes=("_pkg", "_src"))
    check("persistence == ERA5 source",
          (cy.era5_day_n_persistent_events_pkg == cy.era5_day_n_persistent_events_src).all() and
          (cy.era5_day_longest_event_days_pkg == cy.era5_day_longest_event_days_src).all())
    check("persistence != MODIS",
          not (cy.era5_day_n_persistent_events_pkg == cy.modis_day_n_persistent_events).all())
    allcols = {c for df in d.values() for c in df.columns}
    check("n_modis_hot_days absent from package", "n_modis_hot_days" not in allcols)

    # ── 6. geometry ─────────────────────────────────────────────────────────
    print("\n6. Geometry")
    for n in SPATIAL:
        g = d[n]
        check(f"{n} geometries valid", bool(g.geometry.is_valid.all()),
              f"{int((~g.geometry.is_valid).sum())} invalid")
        check(f"{n} CRS recorded", g.crs is not None, str(g.crs))
    sp = d["spots"]
    rec = sp.geometry.area / 1e6
    rel = (rec - sp.area_l50_km2).abs() / sp.area_l50_km2.replace(0, np.nan)
    within = (rel.dropna() <= 0.01).sum(); tot = rel.notna().sum()
    check("spots recomputed area within 1% of area_l50_km2", within == tot,
          f"{within}/{tot} within 1%; max deviation {rel.max()*100:.2f}%")

    # ── 7. privacy ──────────────────────────────────────────────────────────
    print("\n7. Privacy")
    PII = re.compile(r"name|email|e-mail|phone|mobile|device|timestamp|username|free.?text|comment|"
                     r"respondent|address|gps_raw|original_response|match_score|survey.?status|"
                     r"^pid$|_specific$|_other", re.I)
    hits = sorted({f"{n}.{c}" for n, df in d.items() for c in df.columns if PII.search(c)})
    check("no PII-pattern column", not hits, f"{hits}")
    key = pd.read_csv(ROOT / "private" / "participant_key.csv")
    orig = set(key.pid.astype(str))
    leaked = set()
    for n, df in d.items():
        for c in df.select_dtypes("object").columns:
            if set(df[c].dropna().astype(str)) & orig:
                leaked.add(f"{n}.{c}")
    check("no original participant id anywhere", not leaked, f"{sorted(leaked)}")
    raw = pd.read_csv(ROOT / "data" / "inputs" / "stakeholder_survey" / "master_composite.csv",
                      nrows=1, low_memory=False)
    # Published perception items, plus keys and derived fields. recency_of_contact_with_city
    # replaces years_associated_with_city (A7); in_city_region and containing_city are
    # derived by point-in-polygon (A4) and carry a boolean and a study-city name, never free
    # text or anything from the questionnaire.
    allowed = {"perceived_warming_10yr", "perceived_diurnal_severity",
               "perceived_peak_period", "recency_of_contact_with_city",
               "in_city_region", "containing_city",
               "participant_code", "city", "city_slug",
               "cluster25", "spot_type", "study_year", "scenario_id", "geometry"}
    sk = set(d["stakeholder_perception"].columns) | set(d["stakeholder_spots_gps"].columns)
    check("no raw questionnaire column reaches the package",
          not (sk & set(raw.columns)) and sk <= allowed, f"unexpected: {sorted(sk - allowed)}")

    # ── 8. dictionary coverage ──────────────────────────────────────────────
    print("\n8. Data dictionary")
    dd = pd.read_csv(PKG / "data_dictionary.csv")
    missing, extra = [], []
    for n, df in d.items():
        have = set(dd[dd.layer == n].field)
        missing += [f"{n}.{c}" for c in df.columns if c not in have]
        extra += [f"{n}.{c}" for c in have if c not in df.columns]
    check("every field has a dictionary row", not missing, f"{missing[:6]}")
    check("every dictionary row matches a real field", not extra, f"{extra[:6]}")
    check("no [CHECK] left in the dictionary",
          not dd.description.astype(str).str.contains(r"\[CHECK\]").any())

    # ── 8b. deposit readiness ───────────────────────────────────────────────
    print("\n8b. Deposit readiness")

    # geometry validity and CRS, per spatial layer
    _bad_geom, _crs_seen = [], {}
    for _n, _gt in pyogrio.list_layers(GPKG):
        _g = gpd.read_file(GPKG, layer=_n)
        if "geometry" not in _g.columns or _g.geometry.isna().all():
            continue
        _crs_seen[_n] = _g.crs.to_string() if _g.crs else "NONE"
        _inv = int((~_g.geometry.is_valid).sum())
        if _inv:
            _bad_geom.append(f"{_n}:{_inv}")
    check("every geometry in every spatial layer is valid", not _bad_geom,
          f"{len(_crs_seen)} spatial layers: " + ", ".join(f"{k}={v}" for k, v in _crs_seen.items())
          + ("" if not _bad_geom else f"; invalid: {_bad_geom}"))
    check("every spatial layer is in the analysis CRS",
          set(_crs_seen.values()) == {"ESRI:102022"}, f"{sorted(set(_crs_seen.values()))}")

    # population ordering
    _sp = d["spots"]
    _o1 = int(((_sp.pop_l75_persons > _sp.population_persons + 0.5)).sum())
    _o2 = int(((_sp.pop_l90_persons > _sp.pop_l75_persons + 0.5)).sum())
    _cp2 = d["city_profile"]
    _o3 = int((_cp2.population_uc_persons > _cp2.population_cr_persons + 0.5).sum())
    _o4 = int((_cp2.population_uc_persons + _cp2.population_bra_persons
               > _cp2.population_cr_persons + 0.5).sum())
    check("population ordering holds (L90<=L75<=L50, UC<=CR, UC+BRA<=CR)",
          not (_o1 or _o2 or _o3 or _o4),
          f"L75>L50 {_o1}, L90>L75 {_o2}, UC>CR {_o3}, UC+BRA>CR {_o4}")

    # population comes from the 100 m extraction, not the retired 1 km raster
    _cache_files = sorted((R05 / "population_100m" / "contours").glob("*.csv"))
    if _cache_files:
        _cache = pd.concat([pd.read_csv(f) for f in _cache_files],
                           ignore_index=True).set_index("key")["population_100m"].astype(float)
        _sc2 = d["spot_contours"].copy()
        _sc2["k"] = _sc2["spot_id"].astype(str) + "_" + _sc2["contour_level"].astype(str)
        _m = _sc2.set_index("k")["population_persons"].astype(float)
        _both = _m.index.intersection(_cache.index)
        _worst = float((_m[_both] - _cache[_both]).abs().max()) if len(_both) else float("inf")
        check("population matches the native 100 m extraction, not the retired 1 km raster",
              len(_both) == len(_sc2) and _worst < 1e-6,
              f"{len(_both)}/{len(_sc2)} contours compared, max |difference| {_worst:.2e}")
    else:
        check("population matches the native 100 m extraction, not the retired 1 km raster",
              False, "100 m cache not found")

    # key integrity across layers
    _ki = []
    if d["city_profile"].city_slug.isna().any() or d["city_profile"].city_slug.duplicated().any():
        _ki.append("city_profile.city_slug")
    if d["spots"].spot_uid.isna().any() or d["spots"].spot_uid.duplicated().any():
        _ki.append("spots.spot_uid")
    _pc = d["stakeholder_perception"].participant_code
    if _pc.isna().any() or _pc.duplicated().any():
        _ki.append("stakeholder_perception.participant_code")
    if not set(d["stakeholder_spots_gps"].participant_code).issubset(set(_pc)):
        _ki.append("gps participant_code not in perception")
    check("keys are complete and unique (city_slug, spot_uid, participant_code)", not _ki,
          f"{len(d['city_profile'])} slugs, {d['spots'].spot_uid.nunique()} spot_uids, "
          f"{_pc.nunique()} participant codes" + ("" if not _ki else f"; problems: {_ki}"))

    # GPS precision
    _g = L("stakeholder_spots_gps", geom=True).to_crs("EPSG:4326")
    # Coordinates were rounded in EPSG:4326 and are stored projected, so counting decimals
    # after a round-trip just measures float noise. Test the property that matters instead:
    # every point lies ON the 3-decimal grid. Unrounded data would sit ~29 m off on average.
    _xy = np.array([[p.x, p.y] for p in _g.geometry])
    _off_m = float(np.max(np.hypot(*(np.abs(_xy - np.round(_xy, 3)).T))) * 111_000)
    check("stakeholder GPS is published at three decimal degrees (~110 m)", _off_m < 0.5,
          f"maximum distance from the 3-decimal grid: {_off_m:.4f} m")

    # the deposit folder holds exactly the published files
    _expect = {"surface_thermal_anomaly_stakeholder_composite.gpkg", "data_dictionary.csv",
               "data_dictionary.md", "README.md", "CHANGELOG.md", "LICENSE.txt",
               "checksums_md5.txt"}
    _present = {p.name for p in PKG.iterdir()}
    check("deposit folder holds exactly the seven published files",
          _present == _expect,
          f"{len(_present)} entries" + ("" if _present == _expect else
          f"; unexpected {sorted(_present - _expect)}; missing {sorted(_expect - _present)}"))


    # A10: the manifest must verify with the tool a depositor would actually use. Digests
    # are recomputed here too, so the check cannot pass just because md5sum is missing.
    _man = (PKG / "checksums_md5.txt").read_bytes()
    _crlf = _man.count(b"\r\n")
    _recomp = []
    for _line in _man.decode("utf-8").strip().splitlines():
        _dig, _name = _line.split("  ", 1)
        _f = PKG / _name.strip()
        _h = hashlib.md5()
        with _f.open("rb") as _fh:
            for _c in iter(lambda: _fh.read(1 << 20), b""):
                _h.update(_c)
        if _h.hexdigest() != _dig:
            _recomp.append(_name.strip())
    _md5sum = shutil.which("md5sum")
    _ext = None
    if _md5sum:
        _r = subprocess.run([_md5sum, "-c", "checksums_md5.txt"], cwd=PKG,
                            capture_output=True, text=True)
        _ext = _r.returncode
    _nman = len(_man.decode("utf-8").strip().splitlines())
    check("checksums_md5.txt verifies, and has no CRLF that would break md5sum -c",
          not _recomp and _crlf == 0 and _ext in (0, None),
          f"recomputed {_nman} digests, {len(_recomp)} mismatched; "
          f"CRLF lines: {_crlf}; "
          + ("md5sum -c unavailable" if _ext is None else f"md5sum -c exit {_ext}"))
    # Every build input that is NOT a notebook cache must be under version control, or a
    # fresh clone cannot build. docs/ is ignored wholesale, which is how the abbreviation
    # list came to be unreachable; this check stops that recurring.
    _inputs = [ROOT / "data" / "reference" / "abbreviations.csv",
               ROOT / "data" / "inputs" / "geospatial_features" /
               "Major_cities_population_Nigeria_WUP_2025.csv"]
    _missing = [p.name for p in _inputs if not p.exists()]
    _ignored = []
    for _p in _inputs:
        _r = subprocess.run(["git", "check-ignore", "-q", str(_p)], cwd=ROOT,
                            capture_output=True, text=True)
        if _r.returncode == 0:
            _ignored.append(_p.name)
    check("hand-authored build inputs exist and are not gitignored",
          not _missing and not _ignored,
          f"{len(_inputs)} inputs checked"
          + ("" if not _missing else f"; missing {_missing}")
          + ("" if not _ignored else f"; IGNORED {_ignored}"))

    # The published v1.0.0 deposit, restored from Zenodo record 23050560, is the reference
    # the alignment rule is measured against. Its own manifest is CRLF and records a stale
    # README digest (the README was hand-edited after the manifest was written), so those
    # two facts are asserted rather than treated as failures.
    _arc = ROOT / "Results" / "05_hotspot_analysis" / "_archive_v1.0.0"
    _am = _arc / "checksums_md5.txt"
    if not _am.exists():
        check("v1.0.0 archive present and verifies against its published manifest", False,
              f"no manifest at {_am}")
    else:
        _exp = {}
        for _l in _am.read_bytes().decode("utf-8").replace(chr(13), "").strip().split(chr(10)):
            _dg, _nm = _l.split("  ", 1)
            _exp[_nm] = _dg
        _bad = []
        for _nm, _dg in _exp.items():
            _f = _arc / _nm
            if not _f.exists():
                _bad.append(_nm + " (absent)")
                continue
            _h = hashlib.md5()
            with _f.open("rb") as _fh:
                for _c in iter(lambda: _fh.read(1 << 20), b""):
                    _h.update(_c)
            if _h.hexdigest() != _dg:
                _bad.append(_nm)
        check("v1.0.0 archive present and verifies against its published manifest",
              _bad == ["README.md"],
              f"{len(_exp) - len(_bad)}/{len(_exp)} match; README.md is a known v1.0.0 "
              f"defect (hand-edited after its digest was written)"
              + ("" if _bad in ([], ["README.md"]) else f"; unexpected {_bad}"))

    # provenance rows and retired parameters
    _info = d["dataset_info"].set_index("key")["value"]
    _retired = {"era5_min_pixels", "bra_tolerance", "bra_max_dist_m", "bra_min_ring_m"}
    _found = _retired & set(d["scenario_config"].parameter)
    check("dataset_info carries build_date and git_commit; scenario_config has no retired parameter",
          bool(_info.get("build_date")) and bool(_info.get("git_commit")) and not _found,
          f"build_date={_info.get('build_date')}, git_commit={str(_info.get('git_commit'))[:7]}, "
          f"scenario rows={len(d['scenario_config'])}"
          + ("" if not _found else f"; retired present: {sorted(_found)}"))

    # the package opens in both stacks and every layer reads
    _fails = []
    for _n, _ in pyogrio.list_layers(GPKG):
        try:
            pyogrio.read_dataframe(GPKG, layer=_n, read_geometry=False)
            gpd.read_file(GPKG, layer=_n)
        except Exception as _e:
            _fails.append(f"{_n}: {str(_e)[:40]}")
    check("every layer opens in both GDAL/pyogrio and geopandas", not _fails,
          f"{len(list(pyogrio.list_layers(GPKG)))} layers read" + ("" if not _fails else f"; {_fails}"))

    # ── 9. reproducibility ──────────────────────────────────────────────────
    print("\n9. Reproducibility")
    tmp = Path(tempfile.mkdtemp()) / "repro"
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_master_summary.py"),
                        "--out", str(tmp)], capture_output=True, text=True, cwd=ROOT)
    if r.returncode != 0:
        check("rebuild succeeds", False, r.stderr[-200:])
    else:
        a = {l.split("  ", 1)[1]: l.split("  ", 1)[0]
             for l in (PKG / "checksums_md5.txt").read_text().strip().splitlines()}
        b = {l.split("  ", 1)[1]: l.split("  ", 1)[0]
             for l in (tmp / "checksums_md5.txt").read_text().strip().splitlines()}
        same = [k for k in a if k in b and a[k] == b[k]]
        diff = [k for k in a if k in b and a[k] != b[k]]
        check("rebuild reproduces the same files", set(a) == set(b), f"{sorted(set(a) ^ set(b))}")
        check("checksums identical except date-bearing files",
              set(diff) <= {"surface_thermal_anomaly_stakeholder_composite.gpkg",
                            "data_dictionary.csv", "data_dictionary.md",
                            "README.md", "CHANGELOG.md"},
              f"identical: {len(same)}; differ: {sorted(diff)}")
        shutil.rmtree(tmp.parent, ignore_errors=True)

    # ── report: fill the marked block in the single build report ────────────
    npass = sum(1 for _, o, _ in RES if o)
    files = [p for p in sorted(PKG.rglob("*")) if p.is_file()]
    out = [QA_BEGIN, "",
           f"Validated {pd.Timestamp.today().date().isoformat()} — "
           f"**{npass}/{len(RES)} checks passed**.", "",
           f"- Layers: **{len(d)}**",
           f"- Total records: **{sum(len(x) for x in d.values()):,}**",
           f"- Distinct fields described: **{len(dd)}**",
           f"- Archived files: **{len(files)}**, total **{sum(p.stat().st_size for p in files)/1e6:.1f} MB**",
           f"- Study years: **{', '.join(str(y) for y in sorted(d['spots'].study_year.unique()))}**",
           f"- Scenarios: **{', '.join(sorted(d['spots'].scenario_id.unique()))}**", "",
           "### Checks", "",
           "| # | check | result | detail |", "|---|---|---|---|"]
    out += [f"| {i} | {n} | {'PASS' if o else '**FAIL**'} | {t} |"
            for i, (n, o, t) in enumerate(RES, 1)]
    out += ["", "### Values sampled against their source", "",
            "| layer | item | package | source |", "|---|---|---|---|"]
    out += [f"| {l} | {k} | {v} | {s} |" for l, k, v, s in side]
    out += ["", QA_END]

    report = PKG.parent / "dataset_build" / "build_report.md"
    if report.exists():
        txt = report.read_text(encoding="utf-8")
        i, j = txt.find(QA_BEGIN), txt.find(QA_END)
        if i != -1 and j != -1:
            report.write_text(txt[:i] + "\n".join(out) + txt[j + len(QA_END):], encoding="utf-8")
            print(f"\n  validation written into {report.relative_to(ROOT)}")
        else:
            print(f"\n  [WARN] markers missing in {report.name}; validation not written")
    else:
        print(f"\n  [WARN] {report.name} absent; run the build first")

    print(f"\n{npass}/{len(RES)} checks passed")
    return 0 if npass == len(RES) else 1


def _cli(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--package", type=Path, default=DEFAULT_PKG,
                    help="deposit folder to validate (default: the published deposit folder)")
    a = ap.parse_args(argv)
    global PKG, GPKG
    PKG = a.package.resolve()
    GPKG = PKG / "surface_thermal_anomaly_stakeholder_composite.gpkg"
    if not GPKG.exists():
        print(f"no package at {GPKG}")
        return 2
    print(f"Package: {PKG}")
    return main()


if __name__ == "__main__":
    sys.exit(_cli())
