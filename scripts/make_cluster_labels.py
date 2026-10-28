#!/usr/bin/env python
"""Write Results/manuscript_outputs/cluster_labels.csv.

Every figure and table that names a physiographic landscape typology (PLT) cluster reads its
label from this one file, so a cluster is named the same way everywhere.

The labels are DERIVED from land_code25, not typed by hand. That code is the cluster's
climate-geology-elevation signature (CxGyEz), and all 16 clusters holding study cities have a
distinct one, so a label built from those three axes is guaranteed unique. Land cover is not in
the code, so it is carried in the long label as a description rather than used to identify.
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
LOOKUP = ROOT / "Results" / "01_aoi_delineation" / "city_cluster25_lookup.csv"
OUT = ROOT / "Results" / "manuscript_outputs" / "cluster_labels.csv"

# Short forms for the three typology axes. The long form is taken from the lookup itself.
CLIMATE_SHORT = {
    "Tropical wet": "Wet",
    "Tropical wet and dry": "Wet–dry",
    "Tropical guinea savanna": "Guinea sav.",
    "Tropical sudan savanna": "Sudan sav.",
    "Tropical sahel savanna": "Sahel sav.",
    "Tropical montane": "Montane",
}
GEOLOGY_SHORT = {
    "Metamorphic formation": "metamorphic",
    "Sedimentary formation": "sedimentary",
    "Undifferentiated basement complex": "basement",
    "Sedimentary & basement formation": "mixed geology",
}
# Four clearly distinct words, so no two short labels differ only by a suffix.
ELEVATION_SHORT = {
    "Very Low (0-100m)": "lowland",
    "Low (101-500m)": "midland",
    "Moderate (501-1000m)": "upland",
    "High (1001-1500m)": "highland",
}
ELEVATION_BAND = {
    "Very Low (0-100m)": "0–100 m",
    "Low (101-500m)": "101–500 m",
    "Moderate (501-1000m)": "501–1000 m",
    "High (1001-1500m)": "1001–1500 m",
}
GEOLOGY_LONG = {
    "Metamorphic formation": "metamorphic formation",
    "Sedimentary formation": "sedimentary formation",
    "Undifferentiated basement complex": "undifferentiated basement complex",
    "Sedimentary & basement formation": "sedimentary and basement formation",
}


def main() -> int:
    d = pd.read_csv(LOOKUP)
    rows = []
    for cl, g in d.groupby("Cluster25"):
        r = g.iloc[0]
        for name, table in (("Climate_Class", CLIMATE_SHORT), ("Geology_Class", GEOLOGY_SHORT),
                            ("Elevation_Class", ELEVATION_SHORT)):
            if r[name] not in table:
                print(f"unmapped {name}: {r[name]!r} (cluster C{cl})")
                return 2
        short = "%s %s %s" % (CLIMATE_SHORT[r.Climate_Class],
                              GEOLOGY_SHORT[r.Geology_Class],
                              ELEVATION_SHORT[r.Elevation_Class])
        long = "%s on %s at %s elevation (%s), predominantly %s" % (
            r.Climate_Class,
            GEOLOGY_LONG[r.Geology_Class],
            r.Elevation_Class.split(" (")[0].lower(),
            ELEVATION_BAND[r.Elevation_Class],
            str(r.Landcover_Class).lower(),
        )
        rows.append({
            "cluster25": "C%d" % cl,
            "code": r.land_code25,
            "label_short": short,
            "label_long": long,
            "n_cities": len(g),
            "climate": r.Climate_Class,
            "geology": r.Geology_Class,
            "elevation": r.Elevation_Class,
            "landcover": r.Landcover_Class,
            "cities": ", ".join(sorted(g.city_name)),
        })

    out = pd.DataFrame(rows)
    out["_n"] = out.cluster25.str.extract(r"(\d+)").astype(int)
    out = out.sort_values("_n").drop(columns="_n").reset_index(drop=True)

    # The three guarantees this file has to carry.
    assert len(out) == 16, len(out)
    assert out.label_short.is_unique, "short labels collide"
    assert out.code.is_unique, "land codes collide"
    assert out.n_cities.sum() == 56, out.n_cities.sum()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False, encoding="utf-8")
    print("wrote %s  (%d clusters, %d cities)" % (OUT.relative_to(ROOT), len(out),
                                                  out.n_cities.sum()))
    w = max(len(s) for s in out.label_short)
    print()
    print("%-5s %-8s %-3s %-*s  %s" % ("clus", "code", "n", w, "label_short", "label_long"))
    for r in out.itertuples():
        print("%-5s %-8s %-3d %-*s  %s" % (r.cluster25, r.code, r.n_cities, w,
                                           r.label_short, r.label_long))
    return 0


if __name__ == "__main__":
    sys.exit(main())
