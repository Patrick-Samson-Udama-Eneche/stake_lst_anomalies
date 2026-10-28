#!/usr/bin/env python
"""Write Results/manuscript_outputs/cluster_labels.csv.

Every figure and table that names a physiographic landscape typology (PLT) cluster reads its
label from this one file, so a cluster is named the same way everywhere.

The labels are DERIVED from land_code25, not typed by hand. That code is the cluster's
climate-geology-elevation signature (CxGyEz), and all 16 clusters holding study cities have a
distinct one, so a label built from those three axes is unique by construction.

The wording is the typology's own: the class names used in Table 1 and in the published
typology, not invented synonyms. Land cover is NOT a typology axis and appears in neither
label; it is kept as a separate column for description only.
"""
from __future__ import annotations
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
LOOKUP = ROOT / "Results" / "01_aoi_delineation" / "city_cluster25_lookup.csv"
# The full national typology, all 24 classes. Fig. 1 draws every class, so every class
# needs a label, not only the 16 that happen to hold a study city.
TYPOLOGY = (ROOT / "data" / "inputs" / "geospatial_features"
            / "landscape_ch_polygons_with_class_metrics.geojson")
OUT = ROOT / "Results" / "manuscript_outputs" / "cluster_labels.csv"

EN_DASH = "–"
MID_DOT = "·"

# Climate, written in full.
CLIMATE_SHORT = {
    "Tropical wet": "Tropical wet",
    "Tropical wet and dry": "Wet-and-dry",
    "Tropical guinea savanna": "Guinea savanna",
    "Tropical sudan savanna": "Sudan savanna",
    "Tropical sahel savanna": "Sahel savanna",
    "Tropical montane": "Montane",
}
GEOLOGY_SHORT = {
    "Undifferentiated basement complex": "basement",
    "Sedimentary formation": "sedimentary",
    "Metamorphic formation": "metamorphic",
    "Sedimentary & basement formation": "mixed",
}
# Climate for the long label: the lookup stores these lower-case, but Sudan, Guinea and
# Sahel are place names.
CLIMATE_LONG = {
    "Tropical wet": "Tropical wet",
    "Tropical wet and dry": "Tropical wet and dry",
    "Tropical guinea savanna": "Tropical Guinea savanna",
    "Tropical sudan savanna": "Tropical Sudan savanna",
    "Tropical sahel savanna": "Tropical Sahel savanna",
    "Tropical montane": "Tropical montane",
}
GEOLOGY_LONG = {
    "Undifferentiated basement complex": "undifferentiated basement complex",
    "Sedimentary formation": "sedimentary formation",
    "Metamorphic formation": "metamorphic formation",
    "Sedimentary & basement formation": "sedimentary and basement formation",
}
# Class name for the short label; range in metres for the long one.
ELEVATION_SHORT = {
    "Very Low (0-100m)": "very low",
    "Low (101-500m)": "low",
    "Moderate (501-1000m)": "moderate",
    "High (1001-1500m)": "high",
}
ELEVATION_RANGE = {
    "Very Low (0-100m)": "0" + EN_DASH + "100 m",
    "Low (101-500m)": "101" + EN_DASH + "500 m",
    "Moderate (501-1000m)": "501" + EN_DASH + "1,000 m",
    "High (1001-1500m)": "> 1,000 m",
}


def main() -> int:
    import geopandas as gpd
    cities = pd.read_csv(LOOKUP)
    typ = gpd.read_file(TYPOLOGY)
    classes = (typ.drop_duplicates("Cluster25")
               .sort_values("Cluster25")
               .set_index("Cluster25"))
    n_by_cluster = cities.groupby("Cluster25").size()
    city_names = cities.groupby("Cluster25").city_name.apply(lambda g: ", ".join(sorted(g)))

    rows = []
    for cl, r in classes.iterrows():
        cl = int(cl)
        for name, table in (("Climate_Class", CLIMATE_SHORT), ("Climate_Class", CLIMATE_LONG),
                            ("Geology_Class", GEOLOGY_SHORT), ("Geology_Class", GEOLOGY_LONG),
                            ("Elevation_Class", ELEVATION_SHORT)):
            if r[name] not in table:
                print("unmapped %s: %r (cluster C%d)" % (name, r[name], cl))
                return 2
        sep = " " + MID_DOT + " "
        short = sep.join((CLIMATE_SHORT[r.Climate_Class],
                          GEOLOGY_SHORT[r.Geology_Class],
                          ELEVATION_SHORT[r.Elevation_Class]))
        long = "%s, %s, %s elevation (%s)" % (
            CLIMATE_LONG[r.Climate_Class],
            GEOLOGY_LONG[r.Geology_Class],
            ELEVATION_SHORT[r.Elevation_Class],
            ELEVATION_RANGE[r.Elevation_Class],
        )
        n = int(n_by_cluster.get(cl, 0))
        rows.append({
            "cluster25": "C%d" % cl,
            "code": r.land_code25,
            "label_short": short,
            "label_long": long,
            "n_cities": n,
            "has_study_cities": bool(n > 0),
            "climate": r.Climate_Class,
            "geology": r.Geology_Class,
            "elevation": r.Elevation_Class,
            "elevation_range": ELEVATION_RANGE[r.Elevation_Class],
            "landcover": r.Landcover_Class,   # descriptive only, not a typology axis
            "cities": city_names.get(cl, ""),
        })

    out = pd.DataFrame(rows)
    out["_n"] = out.cluster25.str.extract(r"(\d+)").astype(int)
    out = out.sort_values("_n").drop(columns="_n").reset_index(drop=True)

    # The guarantees this file has to carry.
    assert len(out) == 24, len(out)
    assert int(out.has_study_cities.sum()) == 16, int(out.has_study_cities.sum())
    assert out.label_short.is_unique, "short labels collide"
    assert out.label_long.is_unique, "long labels collide"
    assert out.code.is_unique, "land codes collide"
    assert out.cluster25.is_unique, "cluster ids collide"
    assert out.n_cities.sum() == 56, out.n_cities.sum()
    covers = set(out[out.has_study_cities].cluster25)
    want = {"C%d" % c for c in cities.Cluster25.unique()}
    assert covers == want, sorted(covers ^ want)
    for col in ("label_short", "label_long"):
        assert not out[col].str.contains("|".join(
            sorted(set(typ.Landcover_Class.astype(str).str.lower()))), case=False).any(),             "land cover leaked into " + col

    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False, encoding="utf-8")
    print("wrote %s  (%d classes, %d with study cities, %d cities)"
          % (OUT.relative_to(ROOT), len(out), int(out.has_study_cities.sum()),
             out.n_cities.sum()))
    w = max(len(x) for x in out.label_short)
    print()
    print("%-5s %-8s %-4s %-*s  %s" % ("clus", "code", "n", w, "label_short", "label_long"))
    for r in out.itertuples():
        mark = "*" if r.has_study_cities else " "
        print("%-5s %-8s %-3d%s %-*s  %s" % (r.cluster25, r.code, r.n_cities, mark, w,
                                             r.label_short, r.label_long))
    print()
    print("* holds at least one study city")
    return 0


if __name__ == "__main__":
    sys.exit(main())
