"""One visual vocabulary for every SCS figure.

Day/night and hot/cold are the two axes that recur in nearly every figure, so they are defined
once here and nowhere else. A figure that invents its own colour for "night" is a bug.

Cluster labels come from Results/manuscript_outputs/cluster_labels.csv, the file the author
approved; nothing in the figure code spells a cluster name out by hand.
"""
from __future__ import annotations
from pathlib import Path

import matplotlib as mpl
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PKG_DIR = (ROOT / "Results" / "05_hotspot_analysis"
           / "surface_thermal_anomaly_stakeholder_composite")
GPKG = PKG_DIR / "surface_thermal_anomaly_stakeholder_composite.gpkg"
OUT = ROOT / "Results" / "manuscript_outputs"
MAIN_FIG = OUT / "main_figures"
TABLES = OUT / "tables"
SUP_FIG = OUT / "supplementary_figures"
LABELS_CSV = OUT / "cluster_labels.csv"

# ── the two recurring axes ──────────────────────────────────────────────────
# Period: warm amber for day, deep indigo for night. Readable in greyscale, and
# distinguishable under the common forms of colour-vision deficiency.
DAY = "#E08214"
NIGHT = "#3B4CA8"
PERIOD_COLOR = {"day": DAY, "night": NIGHT}
PERIOD_LABEL = {"day": "Day", "night": "Night"}

# Spot type: red for hot, blue for cold.
HOT = "#C0392B"
COLD = "#2471A3"
SPOT_COLOR = {"hot": HOT, "cold": COLD}
SPOT_LABEL = {"hot": "Hot spot", "cold": "Cold spot"}

# The four combinations, where a figure needs all of them at once. Each keeps its spot-type
# hue and separates day from night by lightness, so the two axes stay readable together.
COMBO_COLOR = {
    ("hot", "day"): "#E8694A",
    ("hot", "night"): "#8E1E1E",
    ("cold", "day"): "#5BA3D0",
    ("cold", "night"): "#17446B",
}

ZONE_LABEL = {"uc": "Urban core", "bra": "Background reference area",
              "cr": "City region", "suhii": "SUHII (urban core − BRA)"}
ZONE_COLOR = {"uc": "#B2182B", "bra": "#2166AC", "cr": "#4D4D4D", "suhii": "#762A83"}

GREY = "#595959"
LIGHT = "#D9D9D9"


def apply_style() -> None:
    """Typeface and weights for every figure. Called once per build."""
    mpl.rcParams.update({
        "figure.dpi": 150,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
        "font.size": 8,
        "axes.titlesize": 9,
        "axes.labelsize": 8,
        "axes.titleweight": "bold",
        "axes.edgecolor": GREY,
        "axes.linewidth": 0.6,
        "axes.grid": True,
        "grid.color": LIGHT,
        "grid.linewidth": 0.4,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "legend.fontsize": 7,
        "legend.frameon": False,
        "pdf.fonttype": 42,          # editable text, not outlines
        "svg.fonttype": "none",
    })


_LABELS: pd.DataFrame | None = None


def labels() -> pd.DataFrame:
    """The approved cluster labels, indexed by integer cluster number."""
    global _LABELS
    if _LABELS is None:
        d = pd.read_csv(LABELS_CSV)
        d["n"] = d.cluster25.str.extract(r"(\d+)").astype(int)
        _LABELS = d.set_index("n")
    return _LABELS


def short(cl: int, with_code: bool = True) -> str:
    """Short cluster label. Figures always show the code alongside, as agreed."""
    r = labels().loc[int(cl)]
    return "%s (%s)" % (r.label_short, r.cluster25) if with_code else r.label_short


def long(cl: int) -> str:
    return labels().loc[int(cl)].label_long


def n_cities(cl: int) -> int:
    return int(labels().loc[int(cl)].n_cities)


def panel_header(cl: int, n: int | None = None) -> str:
    """Panel header: the cluster in words, its code, and how many cities it holds."""
    k = n_cities(cl) if n is None else n
    return "%s (%s) — %d %s" % (labels().loc[int(cl)].label_short,
                                     labels().loc[int(cl)].cluster25,
                                     k, "city" if k == 1 else "cities")


def savefig(fig, stem: Path, close: bool = True) -> list[str]:
    """Write the PDF and SVG pair every item ships as."""
    stem.parent.mkdir(parents=True, exist_ok=True)
    out = []
    for ext in ("pdf", "svg"):
        p = stem.with_suffix("." + ext)
        # format is passed explicitly: relying on the extension alone once wrote SVG content
        # into a .pdf, which no reader would have caught until submission.
        fig.savefig(p, format=ext)
        head = p.open("rb").read(5)
        want = b"%PDF-" if ext == "pdf" else b"<?xml"
        if head != want:
            raise RuntimeError("%s was written as %r, not %s" % (p.name, head, ext))
        out.append(p.name)
    if close:
        import matplotlib.pyplot as plt
        plt.close(fig)
    return out
