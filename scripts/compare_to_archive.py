#!/usr/bin/env python
"""Compare the v1.0.1 build against the published v1.0.0 deposit, field by field, and name
every difference.

The alignment rule for this release is that nothing moves except the changes that were asked
for. The intended changes are listed below as an allow-list, and anything outside it is a
failure, so no value can drift unnoticed. Neither package is written to.

v1.0.0 reference: Zenodo record 23050560 (DOI 10.5281/zenodo.23050560), restored into
Results/05_hotspot_analysis/_archive_v1.0.0/ and verified against its published manifest.

    python scripts/compare_to_archive.py [--new <deposit folder>] [--archive <folder>]

Exit code 0 when every difference is an intended one.
"""
from __future__ import annotations
import argparse
import sys
import warnings
from pathlib import Path

import pandas as pd
import pyogrio

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
STEM = "surface_thermal_anomaly_stakeholder_composite"
DEFAULT_NEW = ROOT / "Results" / "05_hotspot_analysis" / STEM
DEFAULT_ARC = ROOT / "Results" / "05_hotspot_analysis" / "_archive_v1.0.0"

# Join keys per layer, so rows are matched by identity rather than by position.
KEYS = {
    "city_zones": ["city_slug", "zone"],
    "city_profile": ["city_slug"],
    "city_year_summary": ["city_slug", "study_year"],
    "trend_statistics": ["city_slug", "zone", "period"],
    "annual_series": ["city_slug", "zone", "period", "year"],
    "monthly_series": ["city_slug", "zone", "period", "year", "month"],
    "monthly_climatology": ["city_slug", "zone", "period", "month"],
    "heat_event_catalogue": ["event_id", "start_date"],
    "spot_occurrence": ["city_slug", "period", "spot_type"],
    "spots": ["spot_uid"],
    "spot_contours": ["contour_id"],
    "stakeholder_spots_gps": ["participant_code", "spot_type"],
    "stakeholder_perception": ["participant_code"],
    "hitrate_sensitivity": ["city_slug", "period", "spot_type", "buffer_m"],
    "city_exposure_by_contour": ["city_slug", "period", "spot_type"],
    "scenario_config": ["parameter"],
    "dataset_info": ["key"],
}

# ── the intended changes, and nothing else ──────────────────────────────────
NEW_LAYERS = {"composite_trend_statistics"}                     # A2
NEW_FIELDS = {                                                   # A3, A4, A6
    "city_year_summary": {
        "day_era5land_event_mean_c", "night_era5land_event_mean_c",
        "day_seviri_uc_mean_c", "day_seviri_bra_mean_c", "day_seviri_cr_mean_c",
        "day_seviri_suhii_c", "night_seviri_uc_mean_c", "night_seviri_bra_mean_c",
        "night_seviri_cr_mean_c", "night_seviri_suhii_c",
    },
    "stakeholder_spots_gps": {"in_city_region", "containing_city"},
    "city_profile": {"pct_assigned_class_cr"},
}
RENAMED = {"stakeholder_perception":                             # A7: same values, new name
           {"years_associated_with_city": "recency_of_contact_with_city"}}
CHANGED_FIELDS = {                                               # A1, A5, harmonisation
    "hitrate_sensitivity": {"n_hit", "n_total", "hit_rate"},
    "city_year_summary": {"validation_tier"},
    # the one blank peak-period answer is now stored as "I'd rather not say"
    "stakeholder_perception": {"perceived_peak_period"},
}
# No layer is expected to change row count in v1.0.1. The heat-event catalogue fix (770 ->
# 807 rows) was made BEFORE v1.0.0 was deposited, so the archive already holds all 807.
ROW_COUNT_CHANGES: dict[str, str] = {}
# A provenance table restates the build, so it is expected to change wholesale.
PROVENANCE_LAYERS = {"dataset_info"}

AREA_POP = ("area", "pop", "population")      # the alignment rule allows 0.5% on these
TOL = 1e-6
TOL_PCT = 0.005


def read(gpkg: Path, layer: str) -> pd.DataFrame:
    return pyogrio.read_dataframe(gpkg, layer=layer, read_geometry=False)


def numeric_diff(new: pd.Series, old: pd.Series, field: str) -> tuple[int, float]:
    """Count differing values under the alignment rule, and report the worst one."""
    a = pd.to_numeric(new, errors="coerce")
    b = pd.to_numeric(old, errors="coerce")
    nan_mismatch = int((a.isna() != b.isna()).sum())
    both = ~a.isna() & ~b.isna()
    if any(k in field.lower() for k in AREA_POP):
        scale = b.abs().where(b.abs() > 0, 1.0)
        measure = ((a - b).abs() / scale)[both]
        bad = int((measure > TOL_PCT).sum())
    else:
        measure = (a - b).abs()[both]
        bad = int((measure > TOL).sum())
    worst = float(measure.max()) if len(measure) else 0.0
    return bad + nan_mismatch, worst


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--new", type=Path, default=DEFAULT_NEW,
                    help="the v1.0.1 deposit folder")
    ap.add_argument("--archive", type=Path, default=DEFAULT_ARC,
                    help="the restored v1.0.0 deposit folder")
    args = ap.parse_args(argv)

    new_gpkg = args.new / (STEM + ".gpkg")
    arc_gpkg = args.archive / (STEM + ".gpkg")
    for p in (new_gpkg, arc_gpkg):
        if not p.exists():
            print("missing: " + str(p))
            return 2

    print("v1.0.1 : " + str(new_gpkg))
    print("v1.0.0 : " + str(arc_gpkg) + "\n")
    oldl = {n for n, _ in pyogrio.list_layers(arc_gpkg)}
    newl = {n for n, _ in pyogrio.list_layers(new_gpkg)}

    problems: list[str] = []
    intended: list[str] = []

    added, removed = newl - oldl, oldl - newl
    if added - NEW_LAYERS:
        problems.append("unexpected new layer(s): " + str(sorted(added - NEW_LAYERS)))
    for n in sorted(added & NEW_LAYERS):
        intended.append("new layer `%s` (%s rows)" % (n, format(len(read(new_gpkg, n)), ",")))
    if removed:
        problems.append("layer(s) dropped: " + str(sorted(removed)))

    print("%-28s %18s  %11s  %s" % ("layer", "rows 1.0.0 -> 1.0.1", "fields", "verdict"))
    print("-" * 92)
    for layer in sorted(oldl & newl):
        old = read(arc_gpkg, layer).rename(columns=RENAMED.get(layer, {}))
        new = read(new_gpkg, layer)
        of, nf = set(old.columns), set(new.columns)
        gained, lost = nf - of, of - nf
        exp_new = NEW_FIELDS.get(layer, set())
        notes = []

        if gained - exp_new:
            problems.append("%s: unexpected new field(s) %s" % (layer, sorted(gained - exp_new)))
        if gained & exp_new:
            notes.append("+%d field(s)" % len(gained & exp_new))
            intended.append("`%s`: %d new field(s) %s"
                            % (layer, len(gained & exp_new), sorted(gained & exp_new)))
        if lost:
            problems.append("%s: field(s) removed %s" % (layer, sorted(lost)))
        for old_name, new_name in RENAMED.get(layer, {}).items():
            intended.append("`%s`: `%s` renamed `%s`" % (layer, old_name, new_name))

        if layer in PROVENANCE_LAYERS:
            print("%-28s %7s -> %-7s  %4d -> %-3d  %s"
                  % (layer, format(len(old), ","), format(len(new), ","), len(of), len(nf),
                     "provenance table, not compared"))
            intended.append("`%s`: provenance table, expected to change wholesale" % layer)
            continue

        rowdelta = len(new) - len(old)
        if rowdelta:
            if layer in ROW_COUNT_CHANGES:
                notes.append("%s -> %s rows" % (format(len(old), ","), format(len(new), ",")))
                intended.append("`%s`: %s -> %s rows, %s"
                                % (layer, format(len(old), ","), format(len(new), ","),
                                   ROW_COUNT_CHANGES[layer]))
            else:
                problems.append("%s: row count %s -> %s"
                                % (layer, format(len(old), ","), format(len(new), ",")))


        key = [c for c in KEYS.get(layer, []) if c in of and c in nf]
        shared = sorted((of & nf) - set(key) - {"scenario_id"})
        allowed = CHANGED_FIELDS.get(layer, set())
        diffs: list[tuple[str, int]] = []
        worst_by_field: dict[str, float] = {}

        if key and not rowdelta:
            om = old.sort_values(key).set_index(key)
            nm = new.sort_values(key).set_index(key)
            if not om.index.equals(nm.index):
                problems.append("%s: key sets differ" % layer)
            else:
                for c in shared:
                    x, y = nm[c], om[c]
                    numeric = (pd.api.types.is_numeric_dtype(x)
                               and pd.api.types.is_numeric_dtype(y)
                               and not pd.api.types.is_bool_dtype(x)
                               and not pd.api.types.is_bool_dtype(y))
                    if numeric:
                        nd, worst = numeric_diff(x, y, c)
                    else:
                        nd = int((x.astype(str).fillna("") != y.astype(str).fillna("")).sum())
                        worst = float(nd)
                    if nd:
                        diffs.append((c, nd))
                        worst_by_field[c] = worst
        elif rowdelta:
            notes.append("rows differ, values not aligned")

        for c, k in diffs:
            if c in allowed:
                intended.append("`%s.%s`: %s value(s) changed" % (layer, c, format(k, ",")))
            else:
                problems.append("%s.%s: %s value(s) differ (worst %.3g)"
                                % (layer, c, format(k, ","), worst_by_field.get(c, 0.0)))

        unexpected = [c for c, _ in diffs if c not in allowed]
        if not diffs and not gained and not rowdelta:
            verdict = "IDENTICAL"
        else:
            parts = list(notes)
            if diffs:
                parts.append("%d field(s) changed" % len(diffs))
            verdict = ", ".join(parts) or "identical"
        if unexpected:
            verdict = "** " + verdict
        print("%-28s %7s -> %-7s  %4d -> %-3d  %s"
              % (layer, format(len(old), ","), format(len(new), ","), len(of), len(nf), verdict))

    print("\n" + "=" * 92)
    print("Intended changes (%d):" % len(intended))
    for s in intended:
        print("  - " + s)
    print("\nUnexpected differences (%d):" % len(problems))
    for s in problems:
        print("  ! " + s)
    print("=" * 92)
    print("ALIGNED - every difference is an intended one." if not problems
          else "NOT ALIGNED - %d unexpected difference(s)." % len(problems))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
