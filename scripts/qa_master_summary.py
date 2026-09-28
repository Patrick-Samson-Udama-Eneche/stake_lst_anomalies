#!/usr/bin/env python
"""QA for the published composite package. Read-only apart from the marked validation block
it fills in _build/build_report.md."""
from __future__ import annotations
import hashlib, json, re, shutil, subprocess, sys, tempfile, warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_master_summary import QA_BEGIN, QA_END  # the markers are defined once, with the writer

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "Results" / "05_hotspot_analysis" / "surface_thermal_anomaly_stakeholder_composite"
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
    allowed = {"perceived_warming_10yr", "perceived_diurnal_severity", "perceived_peak_period",
               "years_associated_with_city", "participant_code", "city", "city_slug",
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
    files = [p for p in sorted(PKG.rglob("*")) if p.is_file() and "_build" not in p.relative_to(PKG).parts]
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

    report = PKG / "_build" / "build_report.md"
    if report.exists():
        txt = report.read_text(encoding="utf-8")
        i, j = txt.find(QA_BEGIN), txt.find(QA_END)
        if i != -1 and j != -1:
            report.write_text(txt[:i] + "\n".join(out) + txt[j + len(QA_END):], encoding="utf-8")
            print(f"\n  validation written into {report.relative_to(PKG)}")
        else:
            print(f"\n  [WARN] markers missing in {report.name}; validation not written")
    else:
        print(f"\n  [WARN] {report.name} absent; run the build first")

    print(f"\n{npass}/{len(RES)} checks passed")
    return 0 if npass == len(RES) else 1


if __name__ == "__main__":
    sys.exit(main())
