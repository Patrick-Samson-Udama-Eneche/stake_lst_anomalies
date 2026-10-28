#!/usr/bin/env python
"""Build the SCS main figures and tables from the v1.0.1 package.

Every quantity that exists in the published GeoPackage is read from it. Two items are the
declared exception: Fig. 10 and Table 4 come from the NB06 association caches, because the
association analysis is deliberately not part of the dataset (README section 7).

    python scripts/build_scs_main.py [--only fig01,table03] [--list]

Each builder asserts the numbers it is supposed to reproduce and fails loudly on a mismatch,
so a figure cannot quietly disagree with the package.
"""
from __future__ import annotations
import argparse
import shutil
import sys
import warnings
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyogrio
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import scs_style as S                                                    # noqa: E402

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
R01 = ROOT / "Results" / "01_aoi_delineation"
R03 = ROOT / "Results" / "03_temporal_analysis"
R06 = ROOT / "Results" / "06_hotspot_modelling"
GEO = ROOT / "data" / "inputs" / "geospatial_features"
SUPERSEDED = S.OUT / "_superseded_v3.0"

SELECTED_CLUSTERS = [4, 7, 9, 13, 19, 25]
FIG6_CITIES = ["Lagos", "Port Harcourt", "Ibadan", "Akure", "Kano", "Abuja"]
ANALYSIS_CRS = "ESRI:102022"

_CACHE: dict[str, pd.DataFrame] = {}
NOTES: list[str] = []


def L(name: str, geom: bool = False) -> pd.DataFrame:
    """Read a package layer once."""
    key = name + ("_g" if geom else "")
    if key not in _CACHE:
        _CACHE[key] = (gpd.read_file(S.GPKG, layer=name) if geom
                       else pyogrio.read_dataframe(S.GPKG, layer=name, read_geometry=False))
    return _CACHE[key].copy()


def note(s: str) -> None:
    NOTES.append(s)
    print("    " + s)


def _xlsx(df: pd.DataFrame, path: Path, sheet: str) -> None:
    """Table workbooks share one look: bold dark header, bordered cells, frozen top row."""
    import xlsxwriter
    wb = xlsxwriter.Workbook(str(path))
    ws = wb.add_worksheet(sheet[:31])
    hdr = wb.add_format({"bold": True, "bg_color": "#404040", "font_color": "white",
                         "border": 1, "align": "center", "valign": "vcenter",
                         "text_wrap": True})
    cell = wb.add_format({"border": 1, "valign": "vcenter", "font_size": 9})
    for j, c in enumerate(df.columns):
        ws.write(0, j, str(c), hdr)
        ws.set_column(j, j, max(10, min(42, int(df[c].astype(str).str.len().max() or 10) + 2)))
    for i, (_, r) in enumerate(df.iterrows(), start=1):
        for j, c in enumerate(df.columns):
            v = r[c]
            ws.write(i, j, "" if pd.isna(v) else (float(v) if isinstance(v, (int, float, np.number))
                                                  else str(v)), cell)
    ws.freeze_panes(1, 0)
    wb.close()


def write_table(df: pd.DataFrame, num: int, name: str, sheet: str) -> str:
    stem = S.TABLES / ("Table_%02d_%s" % (num, name))
    stem.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(stem.with_suffix(".csv"), index=False, encoding="utf-8")
    _xlsx(df, stem.with_suffix(".xlsx"), sheet)
    print("  Table %02d: %d rows x %d cols -> %s.{csv,xlsx}" % (num, len(df), len(df.columns),
                                                                stem.name))
    return stem.name


# ═══════════════════════════════════════════════════════════════════════════
# Fig. 1 — study area
# ═══════════════════════════════════════════════════════════════════════════
def fig01() -> None:
    prof = L("city_profile", geom=True).to_crs(ANALYSIS_CRS)
    boundary = gpd.read_file(GEO / "boundary_Nigeria.geojson").to_crs(ANALYSIS_CRS)

    # The 11 absorbed candidates are not in the package (only their names, on the city that
    # absorbed them), so their own coordinates and populations come from the two caches. The
    # assertion below ties both back to the package.
    final = pd.read_csv(R01 / "study_cities_final.csv")
    wup = pd.read_csv(GEO / "Major_cities_population_Nigeria_WUP_2025.csv")
    wup["pop_k"] = pd.to_numeric(wup["2024"].astype(str).str.replace(",", ""), errors="coerce")
    absorbed = final[final.status == "absorbed"].merge(
        wup[["City_Name", "PWCent_Longitude", "PWCent_Latitude", "pop_k"]],
        left_on="city_name", right_on="City_Name", how="left")
    names_pkg = sorted({n.strip() for s in prof.absorbed_cities.dropna()
                        for n in str(s).split(";")})
    assert sorted(absorbed.city_name) == names_pkg, (sorted(absorbed.city_name), names_pkg)
    assert len(prof) == 56 and len(absorbed) == 11, (len(prof), len(absorbed))
    note("Fig. 1: 56 study cities + 11 absorbed candidates = 67; absorbed names match "
         "city_profile.absorbed_cities exactly")
    abs_g = gpd.GeoDataFrame(
        absorbed, geometry=gpd.points_from_xy(absorbed.PWCent_Longitude,
                                              absorbed.PWCent_Latitude),
        crs="EPSG:4326").to_crs(ANALYSIS_CRS)

    fig, (ax, lax) = plt.subplots(1, 2, figsize=(9.6, 5.6),
                                  gridspec_kw={"width_ratios": [1.75, 1.25]})
    ax.set_axis_off()
    lax.set_axis_off()
    boundary.boundary.plot(ax=ax, color=S.GREY, linewidth=0.7)
    boundary.plot(ax=ax, color="#F7F7F5", zorder=0)

    # Population legend starts at 300,000, the selection threshold.
    bins = [300, 500, 1000, 3000, 20000]
    sizes = [16, 38, 78, 150]
    bands = ["300,000–500,000", "500,000–1 million", "1–3 million",
             "> 3 million"]
    prof["_pop"] = prof.population_wup_merged_k
    prof["_sz"] = pd.cut(prof._pop, bins=bins, labels=sizes, right=False).astype(float)
    assert prof._pop.min() >= 300, prof._pop.min()
    assert prof._sz.notna().all(), "a city fell outside the population bands"

    for cl, g in prof.groupby("cluster25"):
        ax.scatter(g.geometry.x, g.geometry.y, s=g._sz, facecolor=_cluster_color(cl),
                   edgecolor="black", linewidth=0.35, zorder=3)
    ax.scatter(abs_g.geometry.x, abs_g.geometry.y, s=20, marker="x", color=S.GREY,
               linewidth=0.9, zorder=4)

    ax.set_title("Study area: 56 Nigerian cities of at least 300,000 residents", loc="left")
    _scalebar(ax, 200_000, "200 km")

    # Typology legend: climate, geology and elevation, because those are the typology axes.
    lab = S.labels()
    present = sorted(prof.cluster25.unique(), key=lambda c: int(str(c).lstrip("C")))
    handles = [Line2D([], [], marker="o", linestyle="none", markersize=5,
                      markerfacecolor=_cluster_color(c), markeredgecolor="black",
                      markeredgewidth=0.35,
                      label="%s  %s" % (lab.loc[_num(c)].cluster25, lab.loc[_num(c)].label_short))
               for c in present]
    l1 = lax.legend(handles=handles, loc="upper left", bbox_to_anchor=(-0.02, 1.0),
                    title="Physiographic landscape typology\n(climate · geology · elevation)",
                    handletextpad=0.5, labelspacing=0.42, borderaxespad=0,
                    fontsize=6.8)
    l1.get_title().set_fontweight("bold")
    l1.get_title().set_fontsize(7.5)
    lax.add_artist(l1)

    ph = [Line2D([], [], marker="o", linestyle="none", markersize=np.sqrt(s),
                 markerfacecolor="white", markeredgecolor="black", markeredgewidth=0.4,
                 label=b) for s, b in zip(sizes, bands)]
    ph.append(Line2D([], [], marker="x", linestyle="none", markersize=4.5, color=S.GREY,
                     label="absorbed candidate (11)"))
    l2 = lax.legend(handles=ph, loc="lower left", bbox_to_anchor=(-0.02, 0.0),
                    title="City population, 2024 (UN WUP)", handletextpad=0.7,
                    labelspacing=0.75, borderaxespad=0, fontsize=6.8)
    l2.get_title().set_fontweight("bold")
    l2.get_title().set_fontsize(7.5)

    print("  Fig. 01:", S.savefig(fig, S.MAIN_FIG / "Fig_01_study_area"))


def _num(c) -> int:
    return int(str(c).lstrip("C"))


_CFG = None


def _cluster_color(c) -> str:
    """Cluster colours come from config.CLUSTER25_COLORS, so maps match the rest of the project."""
    global _CFG
    if _CFG is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("_scs_config", ROOT / "config.py")
        _CFG = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_CFG)
    return _CFG.CLUSTER25_COLORS.get(_num(c), "#999999")


def _scalebar(ax, length_m: float, label: str, pad: float = 0.055) -> None:
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    x = x0 + (x1 - x0) * pad
    y = y0 + (y1 - y0) * pad
    ax.add_patch(Rectangle((x, y), length_m, (y1 - y0) * 0.008, facecolor="black",
                           edgecolor="black", zorder=6))
    ax.text(x + length_m / 2, y + (y1 - y0) * 0.022, label, ha="center", va="bottom",
            fontsize=6.5, zorder=6)


# ═══════════════════════════════════════════════════════════════════════════
# Fig. 3 — delineation excerpt, re-exported unchanged
# ═══════════════════════════════════════════════════════════════════════════
def fig03() -> None:
    src = SUPERSEDED / "main_figures"
    got = []
    for ext in ("pdf", "svg"):
        s = src / ("Figure_4_city_aoi_grid." + ext)
        if not s.exists():
            raise FileNotFoundError(s)
        d = S.MAIN_FIG / ("Fig_03_delineation_excerpt." + ext)
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(s, d)
        got.append(d.name)
    note("Fig. 3: re-exported byte-for-byte from v3.0 Figure_4_city_aoi_grid; not redrawn")
    print("  Fig. 03:", got)


# ═══════════════════════════════════════════════════════════════════════════
# Fig. 4 — long-term trends, one A4 page
# ═══════════════════════════════════════════════════════════════════════════
def fig04() -> None:
    ann = L("annual_series")
    clim = L("monthly_climatology")
    comp = L("composite_trend_statistics")
    comp = comp[comp.composite_type == "cluster"]

    fig, axes = plt.subplots(len(SELECTED_CLUSTERS), 2, figsize=(8.27, 11.69),
                             sharex="col")
    for i, cl in enumerate(SELECTED_CLUSTERS):
        a_ax, m_ax = axes[i, 0], axes[i, 1]
        key = "C%d" % cl
        sub_a = ann[ann.cluster25 == cl]
        sub_m = clim[clim.cluster25 == cl]
        ncit = sub_a.city_slug.nunique()

        for zone in ("uc", "bra", "cr", "suhii"):
            for period, ls in (("day", "-"), ("night", "--")):
                g = (sub_a[(sub_a.zone == zone) & (sub_a.period == period)]
                     .groupby("year")["value_c"].mean())
                if len(g):
                    a_ax.plot(g.index, g.values, ls, color=S.ZONE_COLOR[zone],
                              linewidth=0.9, alpha=0.95)
                h = (sub_m[(sub_m.zone == zone) & (sub_m.period == period)]
                     .groupby("month")["mean_value_c"].mean())
                if len(h):
                    m_ax.plot(h.index, h.values, ls, color=S.ZONE_COLOR[zone], linewidth=0.9)

        # Trend annotation: the cluster composite SUHII slope, day and night.
        bits = []
        for period in ("day", "night"):
            r = comp[(comp.composite_key == key) & (comp.zone == "suhii")
                     & (comp.period == period)]
            if len(r):
                r = r.iloc[0]
                star = "***" if r.mk_p_value < 0.001 else ("**" if r.mk_p_value < 0.01 else
                                                           ("*" if r.mk_p_value < 0.05 else "n.s."))
                bits.append("%s SUHII %+.2f °C/decade (%s)"
                            % (S.PERIOD_LABEL[period], r.sen_slope_c_per_decade, star))
        a_ax.text(0.015, 0.03, "\n".join(bits), transform=a_ax.transAxes, fontsize=6,
                  va="bottom", ha="left", linespacing=1.4,
                  bbox=dict(boxstyle="round,pad=0.25", facecolor="white", alpha=0.85,
                            edgecolor=S.LIGHT, linewidth=0.4))

        a_ax.set_title(S.panel_header(cl, ncit), loc="left", fontsize=7.5)
        m_ax.set_title("Monthly climatology, 2006–2025", loc="left", fontsize=7.5)
        a_ax.set_ylabel("LST (°C)")
        m_ax.set_xticks(range(1, 13))
        m_ax.set_xticklabels(list("JFMAMJJASOND"), fontsize=6)
    from matplotlib.ticker import MaxNLocator
    for a_ax in axes[:, 0]:
        a_ax.xaxis.set_major_locator(MaxNLocator(integer=True, nbins=6))
    axes[-1, 0].set_xlabel("Year")
    axes[-1, 1].set_xlabel("Month")

    zh = [Line2D([], [], color=S.ZONE_COLOR[z], linewidth=1.3, label=S.ZONE_LABEL[z])
          for z in ("uc", "bra", "cr", "suhii")]
    ph = [Line2D([], [], color="black", linestyle=ls, linewidth=1.1,
                 label=S.PERIOD_LABEL[p]) for p, ls in (("day", "-"), ("night", "--"))]
    fig.legend(handles=zh + ph, loc="upper center", ncol=6, bbox_to_anchor=(0.5, 0.995),
               fontsize=7)
    fig.suptitle("Long-term land surface temperature by physiographic landscape typology, "
                 "2006–2025", y=1.012, fontsize=9, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.975))
    note("Fig. 4: %d selected clusters; trend annotations are cluster SUHII composites from "
         "composite_trend_statistics" % len(SELECTED_CLUSTERS))
    print("  Fig. 04:", S.savefig(fig, S.MAIN_FIG / "Fig_04_longterm_trends"))


# ═══════════════════════════════════════════════════════════════════════════
# Fig. 5 — event-scale anomalies
# ═══════════════════════════════════════════════════════════════════════════
TIER_COLOR = {"EXCELLENT": "#1B7837", "GOOD": "#E08214", "FAIR": "#B2182B"}


def fig05() -> None:
    cy = L("city_year_summary")
    lab = S.labels()
    clusters = sorted(cy.cluster25.unique(), key=_num)
    xs = np.arange(len(clusters))
    names = [lab.loc[_num(c)].cluster25 for c in clusters]

    fig = plt.figure(figsize=(7.5, 8.4))
    gs = fig.add_gridspec(3, 1, height_ratios=[1, 1, 1.25], hspace=0.55)
    ax1, ax2, ax3 = (fig.add_subplot(gs[i]) for i in range(3))

    # (a) persistent heat events per cluster
    for k, period in enumerate(("day", "night")):
        v = [cy[cy.cluster25 == c]["era5_%s_n_persistent_events" % period].sum()
             for c in clusters]
        ax1.bar(xs + (k - 0.5) * 0.4, v, 0.4, color=S.PERIOD_COLOR[period],
                edgecolor="white", linewidth=0.4, label=S.PERIOD_LABEL[period])
    ax1.set_ylabel("Persistent heat events (count)")
    ax1.set_title("(a) Persistent heat events in 2024, by typology and period", loc="left")
    ax1.legend(ncol=2)

    # (b) longest event, with the selected event's tier as the outline colour
    for k, period in enumerate(("day", "night")):
        col = "era5_%s_longest_event_days" % period
        for j, c in enumerate(clusters):
            sub = cy[cy.cluster25 == c]
            if not len(sub) or sub[col].isna().all():
                continue
            top = sub.loc[sub[col].idxmax()]
            tier = str(top["%s_selected_event_tier" % period]).strip().upper()
            ax2.bar(j + (k - 0.5) * 0.4, top[col], 0.4, color=S.PERIOD_COLOR[period],
                    edgecolor=TIER_COLOR.get(tier, S.GREY), linewidth=1.5)
    ax2.set_ylabel("Longest event (days)")
    ax2.set_title("(b) Longest persistent heat event per typology, outline = event tier "
                  "of that event", loc="left")
    ax2.legend(handles=[Patch(facecolor="white", edgecolor=v, linewidth=1.5, label=k.title())
                        for k, v in TIER_COLOR.items()], ncol=3, title="Event tier")

    # (c) event-scale SUHII per city, grouped by cluster
    pos, ticks = 0.0, []
    for c in clusters:
        sub = cy[cy.cluster25 == c].sort_values("city")
        start = pos
        for _, r in sub.iterrows():
            for k, period in enumerate(("day", "night")):
                val = r["%s_seviri_suhii_c" % period]
                if pd.notna(val):
                    ax3.scatter(pos + k * 0.3, val, s=11, color=S.PERIOD_COLOR[period],
                                edgecolor="white", linewidth=0.25, zorder=3)
            pos += 1.0
        ticks.append((start + max(pos - 1.0, start)) / 2)
        pos += 1.0
        ax3.axvline(pos - 1.0, color=S.LIGHT, linewidth=0.5, zorder=0)
    ax3.axhline(0, color=S.GREY, linewidth=0.6)
    ax3.set_ylabel("Event-scale SUHII (°C)")
    ax3.set_title("(c) Event-scale surface urban heat island intensity per city, from the "
                  "MSG-SEVIRI composites", loc="left")
    ax3.set_xticks(ticks)
    ax3.set_xticklabels(names, fontsize=6.5, rotation=90)
    ax3.legend(handles=[Line2D([], [], marker="o", linestyle="none", markersize=4,
                               color=S.PERIOD_COLOR[p], label=S.PERIOD_LABEL[p])
                        for p in ("day", "night")], ncol=2)

    for ax in (ax1, ax2):
        ax.set_xticks(xs)
        ax.set_xticklabels(names, fontsize=6.5)

    d = cy.day_seviri_suhii_c.mean()
    n = cy.night_seviri_suhii_c.mean()
    assert abs(d - 0.735) < 0.001 and abs(n - 0.496) < 0.001, (d, n)
    note("Fig. 5: national mean event SUHII day %.3f / night %.3f °C, matching the "
         "package" % (d, n))
    print("  Fig. 05:", S.savefig(fig, S.MAIN_FIG / "Fig_05_event_scale_anomalies"))


# ═══════════════════════════════════════════════════════════════════════════
# Fig. 6 — hot and cold spots, six cities
# ═══════════════════════════════════════════════════════════════════════════
def fig06() -> None:
    spots = L("spots", geom=True).to_crs(ANALYSIS_CRS)
    cont = L("spot_contours", geom=True).to_crs(ANALYSIS_CRS)
    zones = L("city_zones", geom=True).to_crs(ANALYSIS_CRS)
    prof = L("city_profile")
    slug = prof.set_index("city").city_slug

    fig, axes = plt.subplots(3, 4, figsize=(8.0, 7.6))
    for i, city in enumerate(FIG6_CITIES):
        s = slug[city]
        cr = zones[(zones.city_slug == s) & (zones.zone == "cr")]
        uc = zones[(zones.city_slug == s) & (zones.zone == "uc")]
        for j, period in enumerate(("day", "night")):
            ax = axes[i // 2, (i % 2) * 2 + j]
            ax.set_axis_off()
            cr.boundary.plot(ax=ax, color=S.GREY, linewidth=0.5)
            uc.boundary.plot(ax=ax, color="black", linewidth=0.6, linestyle=":")
            sp = spots[(spots.city_slug == s) & (spots.period == period)]
            for st in ("cold", "hot"):
                ss = sp[sp.spot_type == st]
                if not len(ss):
                    continue
                ids = set(ss.spot_uid)
                for lvl, alpha, lw in (("L50", 0.18, 0.4), ("L75", 0.30, 0.5),
                                       ("L90", 0.55, 0.6)):
                    cc = cont[(cont.spot_uid.isin(ids)) & (cont.contour_level == lvl)]
                    if len(cc):
                        cc.plot(ax=ax, facecolor=S.SPOT_COLOR[st], alpha=alpha,
                                edgecolor=S.SPOT_COLOR[st], linewidth=lw)
                t2 = ss[ss.tier == 2]
                if len(t2):
                    t2.boundary.plot(ax=ax, color=S.SPOT_COLOR[st], linewidth=0.7,
                                     linestyle="--")
            ax.set_title("%s — %s" % (city, S.PERIOD_LABEL[period]), fontsize=7.5,
                         loc="left")
            _scalebar(ax, 10_000, "10 km")

    handles = [Patch(facecolor=S.SPOT_COLOR[t], alpha=0.5, edgecolor=S.SPOT_COLOR[t],
                     label=S.SPOT_LABEL[t]) for t in ("hot", "cold")]
    handles += [Patch(facecolor="#777777", alpha=a, edgecolor="#777777",
                      label="%s kernel density contour" % lvl)
                for lvl, a in (("L50", 0.18), ("L75", 0.30), ("L90", 0.55))]
    handles += [Line2D([], [], color="#777777", linestyle="--", linewidth=0.9,
                       label="Tier-2 buffer (1–9 pixels)"),
                Line2D([], [], color="black", linestyle=":", linewidth=0.9,
                       label="Urban core"),
                Line2D([], [], color=S.GREY, linewidth=0.7, label="City region")]
    fig.legend(handles=handles, loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.035),
               fontsize=7)
    fig.suptitle("Surface hot and cold spots in six cities, day and night", fontsize=9,
                 fontweight="bold", y=1.0)
    fig.tight_layout()
    note("Fig. 6: six cities, %d spots and %d contours drawn from the package"
         % (len(spots[spots.city_slug.isin(slug[FIG6_CITIES])]),
            len(cont[cont.city_slug.isin(slug[FIG6_CITIES])])))
    print("  Fig. 06:", S.savefig(fig, S.MAIN_FIG / "Fig_06_spot_maps_six_cities"))


# ═══════════════════════════════════════════════════════════════════════════
# Fig. 7 — spot area by cluster
# ═══════════════════════════════════════════════════════════════════════════
def fig07() -> None:
    sp = L("spots")
    lab = S.labels()
    clusters = sorted(sp.cluster25.unique(), key=_num)
    fig, axes = plt.subplots(2, 2, figsize=(7.8, 7.4), sharex=True)
    for (st, period), ax in zip([("hot", "day"), ("hot", "night"),
                                 ("cold", "day"), ("cold", "night")], axes.ravel()):
        data, names, counts = [], [], []
        for c in clusters:
            v = sp[(sp.cluster25 == c) & (sp.spot_type == st)
                   & (sp.period == period)].area_l50_km2.dropna()
            data.append(v.values if len(v) else np.array([np.nan]))
            names.append(lab.loc[_num(c)].cluster25)
            counts.append(len(v))
        bp = ax.boxplot(data, vert=True, widths=0.6, patch_artist=True,
                        medianprops=dict(color="black", linewidth=0.8),
                        flierprops=dict(marker="o", markersize=2, alpha=0.55,
                                        markerfacecolor=S.COMBO_COLOR[(st, period)],
                                        markeredgewidth=0))
        for b in bp["boxes"]:
            b.set(facecolor=S.COMBO_COLOR[(st, period)], alpha=0.55, linewidth=0.5,
                  edgecolor=S.GREY)
        ax.set_yscale("log")
        ax.set_ylabel("L50 spot area (km$^2$, log scale)")
        ax.set_title("%s, %s" % (S.SPOT_LABEL[st], S.PERIOD_LABEL[period].lower()),
                     loc="left", pad=14)
        ax.set_xticks(range(1, len(names) + 1))
        ax.set_xticklabels(names, rotation=90, fontsize=6)
        for j, k in enumerate(counts, start=1):
            ax.text(j, 1.012, str(k), transform=ax.get_xaxis_transform(),
                    ha="center", va="bottom", fontsize=5.2, color=S.GREY)
        ax.text(0.0, 1.012, "n =", transform=ax.transAxes, ha="right", va="bottom",
                fontsize=5.2, color=S.GREY)
    fig.suptitle("Spot footprint area by physiographic landscape typology",
                 fontsize=9, fontweight="bold", y=1.0)
    fig.tight_layout()
    note("Fig. 7: %d spots across %d clusters; n per box is the spot count"
         % (len(sp), len(clusters)))
    print("  Fig. 07:", S.savefig(fig, S.MAIN_FIG / "Fig_07_spot_area_by_cluster"))


# ═══════════════════════════════════════════════════════════════════════════
# Fig. 8 — population within spots
# ═══════════════════════════════════════════════════════════════════════════
def fig08() -> None:
    ex = L("city_exposure_by_contour")
    prof = L("city_profile", geom=True).to_crs(ANALYSIS_CRS)
    boundary = gpd.read_file(GEO / "boundary_Nigeria.geojson").to_crs(ANALYSIS_CRS)
    lab = S.labels()

    tot = ex.groupby(["spot_type", "period"])[["pop_l50_persons"]].sum()
    hn = float(tot.loc[("hot", "night"), "pop_l50_persons"])
    assert round(hn) == 9_184_401, round(hn)
    note("Fig. 8: hot/night L50 population = %s, matching the required total" % f"{round(hn):,}")

    fig = plt.figure(figsize=(7.5, 9.4))
    gs = fig.add_gridspec(3, 2, height_ratios=[1.75, 1, 1], hspace=0.42, wspace=0.25)

    ax = fig.add_subplot(gs[0, :])
    ax.set_axis_off()
    ax.set_anchor("C")
    boundary.plot(ax=ax, color="#F7F7F5", zorder=0)
    boundary.boundary.plot(ax=ax, color=S.GREY, linewidth=0.7)
    hot_night = (ex[(ex.spot_type == "hot") & (ex.period == "night")]
                 .set_index("city_slug").pop_l50_persons)
    p = prof.copy()
    p["_v"] = p.city_slug.map(hot_night).fillna(0.0)
    p = p.sort_values("_v")
    sc = ax.scatter(p.geometry.x, p.geometry.y, s=np.clip(p._v / 9000.0, 6, 320),
                    c=p._v / 1e6, cmap="YlOrRd", edgecolor="black", linewidth=0.35,
                    zorder=3, vmin=0)
    # Horizontal, under the map: a vertical colorbar takes width from a row that an
    # equal-aspect map of Nigeria already cannot fill, pushing the map off centre.
    cb = fig.colorbar(sc, ax=ax, orientation="horizontal", fraction=0.035, pad=0.01,
                      shrink=0.45, anchor=(0.5, 1.0))
    cb.set_label("Residents in night-time hot spots (millions)", fontsize=7)
    cb.ax.tick_params(labelsize=6)
    ax.set_title("(a) Residents within night-time hot spot footprints (L50), by city",
                 loc="left")
    _scalebar(ax, 200_000, "200 km")

    clusters = sorted(ex.cluster25.unique(), key=_num)
    names = [lab.loc[_num(c)].cluster25 for c in clusters]
    xs = np.arange(len(clusters))
    for k, (st, period) in enumerate([("hot", "day"), ("hot", "night"),
                                      ("cold", "day"), ("cold", "night")]):
        ax = fig.add_subplot(gs[1 + k // 2, k % 2])
        sub = ex[(ex.spot_type == st) & (ex.period == period)]
        bottom = np.zeros(len(clusters))
        for lvl, alpha in (("l50", 0.45), ("l75", 0.7), ("l90", 1.0)):
            v = np.array([sub[sub.cluster25 == c]["pop_%s_persons" % lvl].sum() / 1e6
                          for c in clusters])
            inc = v if lvl == "l50" else v           # nested, so plot as overlapping bars
            ax.bar(xs, inc, 0.72, color=S.COMBO_COLOR[(st, period)], alpha=alpha,
                   edgecolor="white", linewidth=0.3, zorder=3 if lvl == "l50" else 4,
                   label=lvl.upper())
        ax.set_title("(%s) %s, %s" % ("bcde"[k], S.SPOT_LABEL[st],
                                      S.PERIOD_LABEL[period].lower()), loc="left")
        ax.set_ylabel("Residents (millions)")
        ax.set_xticks(xs)
        ax.set_xticklabels(names, rotation=90, fontsize=6)
        if k == 0:
            ax.legend(title="Contour level", ncol=3, fontsize=6.5, title_fontsize=6.5)
    fig.suptitle("Population within surface hot and cold spots", fontsize=9,
                 fontweight="bold", y=0.995)
    print("  Fig. 08:", S.savefig(fig, S.MAIN_FIG / "Fig_08_population_within_spots"))


# ═══════════════════════════════════════════════════════════════════════════
# Fig. 9 — stakeholder accounts
# ═══════════════════════════════════════════════════════════════════════════
WARM_ORDER = ["Yes", "No", "I'm not sure", "I'd rather not say"]
DIUR_ORDER = ["During the day", "At night", "Both", "I'd rather not say"]
PEAK_ORDER = ["December – February", "March – May", "June – August",
              "September – November", "I am not sure", "No answer"]
CAT_COLORS = ["#1B7837", "#B2182B", "#E08214", "#9E9E9E", "#5BA3D0", "#C9C9C9"]


def fig09() -> None:
    pc = L("stakeholder_perception")
    hs = L("hitrate_sensitivity")
    lab = S.labels()

    assert len(pc) == 105 and pc.city.nunique() == 21 and pc.cluster25.nunique() == 10, \
        (len(pc), pc.city.nunique(), pc.cluster25.nunique())

    # The one blank peak-period answer is shown as "No answer", exactly as stored. NB03's
    # fillna("I'd rather not say") is deliberately NOT applied: it invented a response.
    pc = pc.copy()
    n_blank = int(pc.perceived_peak_period.isna().sum())
    pc["peak"] = pc.perceived_peak_period.fillna("No answer")
    assert n_blank == 1, n_blank
    note("Fig. 9a-c: 105 participants, 21 cities, 10 clusters; the 1 blank peak-period "
         "answer is shown as 'No answer', not imputed")

    clusters = sorted(pc.cluster25.unique(), key=_num)
    fig = plt.figure(figsize=(9.2, 8.6))
    gs = fig.add_gridspec(4, 1, height_ratios=[1, 1, 1, 1.2], hspace=0.42)

    for k, (col, order, title) in enumerate([
            ("perceived_warming_10yr", WARM_ORDER,
             "(a) Perceived temperature increase over the last ten years"),
            ("perceived_diurnal_severity", DIUR_ORDER,
             "(b) Period in which heat is felt most severely"),
            ("peak", PEAK_ORDER, "(c) Months perceived as the city's temperature peak")]):
        ax = fig.add_subplot(gs[k])
        ct = pd.crosstab(pc.cluster25, pc[col])
        for c in order:
            if c not in ct.columns:
                ct[c] = 0
        ct = ct[order].reindex(clusters)
        pct = ct.div(ct.sum(axis=1), axis=0) * 100.0
        left = np.zeros(len(ct))
        ys = np.arange(len(ct))
        for j, c in enumerate(order):
            ax.barh(ys, pct[c].values, 0.68, left=left, color=CAT_COLORS[j],
                    edgecolor="white", linewidth=0.4, label=c)
            left += pct[c].values
        ax.set_yticks(ys)
        ax.set_yticklabels(["%s  (n=%d)" % (lab.loc[_num(c)].cluster25, int(ct.loc[c].sum()))
                            for c in clusters], fontsize=6.5)
        ax.invert_yaxis()
        ax.set_xlim(0, 100)
        ax.set_xlabel("Share of participants (%)")
        ax.set_title(title, loc="left")
        ax.legend(ncol=1, fontsize=6.4, loc="center left", bbox_to_anchor=(1.01, 0.5),
                  handlelength=1.1, handletextpad=0.5)
        ax.grid(axis="y", visible=False)

    # (d) hit-rate sensitivity, on the cohort points
    ax = fig.add_subplot(gs[3])
    for st in ("hot", "cold"):
        for period in ("day", "night"):
            g = (hs[(hs.spot_type == st) & (hs.period == period)]
                 .groupby("buffer_m")[["n_hit", "n_total"]].sum())
            ax.plot(g.index / 1000.0, 100.0 * g.n_hit / g.n_total, "-o", markersize=2.4,
                    linewidth=1.1, color=S.COMBO_COLOR[(st, period)],
                    label="%s, %s" % (S.SPOT_LABEL[st], S.PERIOD_LABEL[period].lower()))
    a = hs[hs.buffer_m == 500].groupby(["spot_type", "period"])[["n_hit", "n_total"]].sum()
    for (st, period), target in ((("hot", "day"), (4, 55)), (("hot", "night"), (3, 55)),
                                 (("cold", "day"), (4, 39)), (("cold", "night"), (0, 39))):
        got = (int(a.loc[(st, period), "n_hit"]), int(a.loc[(st, period), "n_total"]))
        assert got == target, (st, period, got, target)
    note("Fig. 9d: 500 m hit rates reproduce 4/55, 3/55, 4/39, 0/39 on the cohort points")
    ax.set_xlabel("Buffer radius around the marked point (km)")
    ax.set_ylabel("Hit rate (% of joined rows)")
    ax.set_title("(d) Agreement between stakeholder-marked locations and detected spots",
                 loc="left")
    ax.legend(ncol=2)

    fig.suptitle("Stakeholder accounts of urban heat and their agreement with the "
                 "satellite record", fontsize=9, fontweight="bold", y=0.998)
    print("  Fig. 09:", S.savefig(fig, S.MAIN_FIG / "Fig_09_stakeholder_accounts"))


# ═══════════════════════════════════════════════════════════════════════════
# Fig. 10 — association effect sizes (NB06 caches: the declared exception)
# ═══════════════════════════════════════════════════════════════════════════
ELEMENT_WORDS = {"Climate Zone": "Climate zone", "Geology": "Geological substrate",
                 "Elevation Belt": "Elevation belt"}
OUTCOME_WORDS = {"Occurrence": "Spot occurrence", "SUHII": "Spot SUHII",
                 "Area (L50)": "Spot area (L50)"}


def fig10() -> None:
    ms = pd.read_csv(R06 / "tables" / "master_synthesis.csv")
    assert len(ms) == 12, len(ms)
    ms["eff"] = ms["A: V (Cramér)"].fillna(ms["A: η²"])
    ms["eff_b"] = ms["B: V (Cramér)"].fillna(ms["B: η²"])
    ms["lab"] = [("%s, %s — %s" % (S.SPOT_LABEL[r["Spot Type"].lower()],
                                        r["Period"].lower(),
                                        OUTCOME_WORDS.get(r["Outcome"], r["Outcome"])))
                 for _, r in ms.iterrows()]
    fig, ax = plt.subplots(figsize=(7.5, 5.2))
    ys = np.arange(len(ms))[::-1]
    for y, (_, r) in zip(ys, ms.iterrows()):
        st = r["Spot Type"].lower()
        per = r["Period"].lower()
        ax.plot([r.eff_b, r.eff], [y, y], color=S.LIGHT, linewidth=1.2, zorder=1)
        ax.scatter(r.eff, y, s=42, color=S.COMBO_COLOR[(st, per)], edgecolor="black",
                   linewidth=0.4, zorder=3)
        ax.scatter(r.eff_b, y, s=30, facecolor="white",
                   edgecolor=S.COMBO_COLOR[(st, per)], linewidth=1.1, marker="D", zorder=3)
        ax.text(1.005, y, "%s   %s" % (str(r["A: sig"]),
                                       ELEMENT_WORDS.get(r["B: Best element"],
                                                         r["B: Best element"])),
                transform=ax.get_yaxis_transform(), fontsize=6.3, va="center")
    ax.set_yticks(ys)
    ax.set_yticklabels(ms.lab, fontsize=6.8)
    ax.set_xlabel("Effect size (Cramér's V for occurrence, η² for SUHII and area)")
    ax.set_xlim(-0.02, 0.78)
    ax.axvline(0, color=S.GREY, linewidth=0.6)
    ax.set_title("Association of the physiographic landscape typology with the thermal "
                 "anomalies, against its strongest single element", loc="left")
    ax.legend(handles=[
        Line2D([], [], marker="o", linestyle="none", markersize=6, color="#777777",
               markeredgecolor="black", label="Full typology (Cluster25)"),
        Line2D([], [], marker="D", linestyle="none", markersize=5, markerfacecolor="white",
               markeredgecolor="#777777", label="Best single element")], ncol=2,
        loc="lower right")
    nsig = int((pd.to_numeric(ms["A: p"], errors="coerce") < 0.05).sum())
    note("Fig. 10 / Table 4: %d of 12 typology tests reach p < 0.05 (the v3.0 text said "
         "4 of 12; the tables show %d)" % (nsig, nsig))
    fig.tight_layout()
    print("  Fig. 10:", S.savefig(fig, S.MAIN_FIG / "Fig_10_association_effect_sizes"))


# ═══════════════════════════════════════════════════════════════════════════
# Tables
# ═══════════════════════════════════════════════════════════════════════════
def table01() -> None:
    prof = L("city_profile")
    lab = S.labels()
    rows = []
    for c in sorted(prof.cluster25.unique(), key=_num):
        g = prof[prof.cluster25 == c]
        r = lab.loc[_num(c)]
        rows.append({
            "Cluster": r.cluster25, "Code": r.code, "Typology": r.label_long,
            "Cities (n)": len(g),
            "Population 2024 (thousands)": round(g.population_wup_merged_k.sum(), 1),
            "City region area (km2)": round(g.cr_area_km2.sum(), 1),
            "Urban core area (km2)": round(g.uc_area_km2.sum(), 1),
            "Cities": ", ".join(sorted(g.city)),
        })
    t = pd.DataFrame(rows)
    assert t["Cities (n)"].sum() == 56, t["Cities (n)"].sum()
    for col, src in (("Population 2024 (thousands)", prof.population_wup_merged_k),
                     ("City region area (km2)", prof.cr_area_km2),
                     ("Urban core area (km2)", prof.uc_area_km2)):
        assert abs(t[col].sum() - src.sum()) < 0.5, (col, t[col].sum(), src.sum())
    total = pd.DataFrame([{"Cluster": "All", "Code": "", "Typology": "All 16 typologies",
                           "Cities (n)": 56,
                           "Population 2024 (thousands)": round(prof.population_wup_merged_k.sum(), 1),
                           "City region area (km2)": round(prof.cr_area_km2.sum(), 1),
                           "Urban core area (km2)": round(prof.uc_area_km2.sum(), 1),
                           "Cities": ""}])
    t = pd.concat([t, total], ignore_index=True)
    note("Table 1: 56 cities; cluster sums reconcile with city_profile "
         "(population %.1f thousand, CR %.1f km2, UC %.1f km2)"
         % (prof.population_wup_merged_k.sum(), prof.cr_area_km2.sum(), prof.uc_area_km2.sum()))
    write_table(t, 1, "typology_composition", "Table 1")


def table02() -> None:
    sp = L("spots")
    lab = S.labels()
    rows = []
    for c in sorted(sp.cluster25.unique(), key=_num):
        for st in ("hot", "cold"):
            for period in ("day", "night"):
                g = sp[(sp.cluster25 == c) & (sp.spot_type == st) & (sp.period == period)]
                if not len(g):
                    continue
                bh = g[g.bh_significant.astype(str).str.lower().isin(["true", "1"])]
                rows.append({
                    "Cluster": lab.loc[_num(c)].cluster25,
                    "Typology": lab.loc[_num(c)].label_short,
                    "Spot type": S.SPOT_LABEL[st], "Period": S.PERIOD_LABEL[period],
                    "Spots (n)": len(g), "Cities (n)": g.city_slug.nunique(),
                    "L50 area (km2)": round(g.area_l50_km2.sum(), 2),
                    "Median spot area (km2)": round(g.area_l50_km2.median(), 2),
                    "Spots in BH-FDR groups (n)": len(bh),
                })
    t = pd.DataFrame(rows)
    assert t["Spots (n)"].sum() == len(sp), (t["Spots (n)"].sum(), len(sp))
    note("Table 2: %d rows covering all %d spots" % (len(t), len(sp)))
    write_table(t, 2, "significant_spots_by_cluster", "Table 2")


def table03() -> None:
    pc = L("stakeholder_perception")
    comp = L("composite_trend_statistics")
    comp = comp[(comp.composite_type == "cluster") & (comp.zone == "uc")]
    val = pd.read_csv(R03 / "Stakeholder_Validation_Comprehensive.csv")
    lab = S.labels()

    per_city = pc.groupby("city").size()
    singles = sorted(per_city[per_city == 1].index)
    assert len(singles) == 7, singles

    rows = []
    for c in sorted(pc.cluster25.unique(), key=_num):
        g = pc[pc.cluster25 == c]
        key = "C%d" % _num(c)
        v = val[(val.Level == "Cluster") & (val.Cluster25.astype(str).str.lstrip("C0")
                                            .str.lstrip("C") == str(_num(c)))]
        vr = v.iloc[0] if len(v) else None
        tr = {}
        for period in ("day", "night"):
            r = comp[(comp.composite_key == key) & (comp.period == period)]
            tr[period] = (("%s (%+.2f °C/decade, p=%.3f)"
                           % (r.iloc[0].mk_trend, r.iloc[0].sen_slope_c_per_decade,
                              r.iloc[0].mk_p_value)) if len(r) else "")
        sc = sorted(set(g.city) & set(singles))
        rows.append({
            "Cluster": lab.loc[_num(c)].cluster25,
            "Typology": lab.loc[_num(c)].label_long,
            "Stakeholders (n)": len(g), "Cities (n)": g.city.nunique(),
            "Single-stakeholder cities": ", ".join(sc) if sc else "—",
            "Urban-core trend, day (Mann-Kendall)": tr["day"],
            "Urban-core trend, night (Mann-Kendall)": tr["night"],
            "Perceived warming, agreement (%)": (round(float(vr["Q61_Annual_Agreement_%"]), 1)
                                                 if vr is not None else np.nan),
            "Perceived peak period": vr["Q58_Peak_Response"] if vr is not None else "",
            "Peak-month agreement (%)": (round(float(vr["Q58_Monthly_Agreement_%"]), 1)
                                         if vr is not None else np.nan),
            "Consensus": vr["Consensus_Level"] if vr is not None else "",
        })
    t = pd.DataFrame(rows)
    assert t["Stakeholders (n)"].sum() == 105, t["Stakeholders (n)"].sum()

    nat = val[val.Level == "National"].iloc[0]
    n_peak = int(round(float(nat["Q58_Monthly_Agreement_%"]) / 100.0 * 105))
    assert n_peak == 70, n_peak
    t = pd.concat([t, pd.DataFrame([{
        "Cluster": "All", "Typology": "All typologies with stakeholders",
        "Stakeholders (n)": 105, "Cities (n)": 21, "Single-stakeholder cities": "7 cities",
        "Urban-core trend, day (Mann-Kendall)": str(nat["LST_Day_Trend"]),
        "Urban-core trend, night (Mann-Kendall)": str(nat["LST_Night_Trend"]),
        "Perceived warming, agreement (%)": round(float(nat["Q61_Annual_Agreement_%"]), 1),
        "Perceived peak period": nat["Q58_Peak_Response"],
        "Peak-month agreement (%)": round(float(nat["Q58_Monthly_Agreement_%"]), 1),
        "Consensus": "70 of 105 participants",
    }])], ignore_index=True)
    note("Table 3: 10 clusters, 105 stakeholders, 21 cities; 7 single-stakeholder cities "
         "flagged (%s); peak month 70 of 105" % ", ".join(singles))
    write_table(t, 3, "stakeholder_vs_satellite_cluster", "Table 3")


def table04() -> None:
    ms = pd.read_csv(R06 / "tables" / "master_synthesis.csv")
    assert len(ms) == 12, len(ms)
    t = pd.DataFrame({
        "Spot type": [S.SPOT_LABEL[s.lower()] for s in ms["Spot Type"]],
        "Period": [S.PERIOD_LABEL[p.lower()] for p in ms["Period"]],
        "Outcome": [OUTCOME_WORDS.get(o, o) for o in ms["Outcome"]],
        "Test": ms["A: Method"],
        "Typology effect size": [
            ("V = %.3f" % r["A: V (Cramér)"]) if pd.notna(r["A: V (Cramér)"])
            else ("η² = %.3f" % r["A: η²"]) for _, r in ms.iterrows()],
        "Typology p": ms["A: p"],
        "Typology significance": ms["A: sig"],
        "Best single element": [ELEMENT_WORDS.get(e, e) for e in ms["B: Best element"]],
        "Element effect size": [
            ("V = %.3f" % r["B: V (Cramér)"]) if pd.notna(r["B: V (Cramér)"])
            else ("η² = %.3f" % r["B: η²"]) for _, r in ms.iterrows()],
        "Element p (Holm)": ms["B: p(Holm)"],
        "Element significance": ms["B: sig"],
        "Difference in effect size": ms["Δ effect size"].round(3),
    })
    nsig = int((pd.to_numeric(ms["A: p"], errors="coerce") < 0.05).sum())
    note("Table 4: %d of 12 typology tests at p < 0.05 — resolves the v3.0 "
         "discrepancy in favour of %d, not 4" % (nsig, nsig))
    write_table(t, 4, "typology_association", "Table 4")


# ═══════════════════════════════════════════════════════════════════════════
# thumbnail sheet
# ═══════════════════════════════════════════════════════════════════════════
def thumbnails() -> None:
    try:
        import fitz                                                      # PyMuPDF
    except ImportError:
        print("  thumbnails: PyMuPDF not installed; skipped")
        NOTES.append("thumbnail sheet skipped: PyMuPDF (fitz) not installed")
        return
    pdfs = sorted(S.MAIN_FIG.glob("Fig_*.pdf"))
    if not pdfs:
        print("  thumbnails: no figures yet")
        return
    cols, rows = 3, int(np.ceil(len(pdfs) / 3))
    fig, axes = plt.subplots(rows, cols, figsize=(8.27, 11.69))
    axes = np.atleast_1d(axes).ravel()
    for ax in axes:
        ax.set_axis_off()
    for ax, p in zip(axes, pdfs):
        doc = fitz.open(p)
        pm = doc[0].get_pixmap(dpi=96)
        img = np.frombuffer(pm.samples, dtype=np.uint8).reshape(pm.height, pm.width, pm.n)
        ax.imshow(img[:, :, :3])
        ax.set_title(p.stem.replace("_", " "), fontsize=7)
        doc.close()
    fig.suptitle("SCS main figures — contact sheet (%d items, %s)"
                 % (len(pdfs), pd.Timestamp.today().date().isoformat()),
                 fontsize=10, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    out = S.MAIN_FIG / "_thumbnails_main_figures.pdf"
    fig.savefig(out)
    plt.close(fig)
    print("  thumbnails: %d figures -> %s" % (len(pdfs), out.name))



# ═══════════════════════════════════════════════════════════════════════════
# captions.md
# ═══════════════════════════════════════════════════════════════════════════
# Two denominators run through the stakeholder items and must never be mixed.
PERCEPTION_BASE = ("105 participants in 21 cities and 10 physiographic landscape typology "
                   "(PLT) clusters")
POINT_BASE = "94 marked points (55 hot, 39 cold) from 17 cities and 8 PLT clusters"
ROW_RULE = ("Hit rates are row-based: a point lying within several spot footprints counts "
            "once per footprint, so the denominator grows with the buffer radius.")
NB06_NOTE = ("Source: the NB06 association caches, not the published GeoPackage. The "
             "association analysis is deliberately excluded from the dataset (README "
             "section 7), so this is the one item whose values cannot be traced to the "
             "package.")


def captions() -> None:
    pc = L("stakeholder_perception")
    sp = L("spots")
    ex = L("city_exposure_by_contour")
    prof = L("city_profile")
    per_city = pc.groupby("city").size()
    singles = sorted(per_city[per_city == 1].index)
    multi = sorted(per_city[per_city >= 2].index)
    dropped = sorted(set(pc.city) - set(multi))
    hot_night = ex[(ex.spot_type == "hot") & (ex.period == "night")].pop_l50_persons.sum()

    items = [
        ("Fig. 1", "Fig_01_study_area",
         "Study area: the %d Nigerian cities analysed, and the 11 candidate cities absorbed "
         "into them." % len(prof),
         "The %d cities are those of the 67 UN World Urbanization Prospects (WUP) 2024 "
         "candidates with at least 300,000 residents that survive spatial deduplication; "
         "the 11 absorbed candidates are marked with a cross and their populations merged "
         "into the absorbing city. Symbol colour gives the physiographic landscape typology "
         "(PLT) cluster, named by its three axes - climate, geology and elevation - and "
         "symbol size gives 2024 city population, the smallest class beginning at the "
         "300,000 selection threshold." % len(prof),
         "`city_profile` (geometry, city, cluster25, population_wup_merged_k, "
         "absorbed_cities); `city_zones`. The absorbed candidates own coordinates and "
         "populations come from `study_cities_final.csv` and the WUP table, because the "
         "package records only their names; those names are asserted against "
         "`city_profile.absorbed_cities`."),

        ("Fig. 3", "Fig_03_delineation_excerpt",
         "Three-zone delineation for five cities: Kano, Abuja, Jos, Lagos and Port Harcourt.",
         "Urban core, background reference area (BRA) and city region for each city. "
         "Re-exported unchanged from version 3.0; no value was recomputed.",
         "None: re-exported artwork."),

        ("Fig. 4", "Fig_04_longterm_trends",
         "Long-term land surface temperature (LST) by physiographic landscape typology, "
         "2006-2025.",
         "For each of six selected PLT clusters, the annual series (left) and the monthly "
         "climatology (right) for the urban core, the background reference area, the city "
         "region and the surface urban heat island intensity (SUHII, urban core minus BRA), "
         "by day (solid) and night (dashed). Each line is the unweighted mean of the member "
         "cities. The inset gives the cluster SUHII trend as a Theil-Sen slope per decade "
         "with its Mann-Kendall significance (*** p < 0.001, ** p < 0.01, * p < 0.05, n.s. "
         "not significant). Panel headers name the cluster in words, with its code and the "
         "number of cities it holds.",
         "`annual_series` (zone, period, year, value_c); `monthly_climatology` (month, "
         "mean_value_c); `composite_trend_statistics` (composite_key, zone, period, "
         "sen_slope_c_per_decade, mk_p_value, mk_trend)."),

        ("Fig. 5", "Fig_05_event_scale_anomalies",
         "Persistent heat events of 2024 and the event-scale heat island, by physiographic "
         "landscape typology.",
         "(a) Number of ERA5-Land persistent heat events (PHEs) per cluster, by day and "
         "night. (b) The longest single event in each cluster; the bar outline gives the "
         "event tier of that event (EXCELLENT, GOOD or FAIR), a single grade because an "
         "event is either a day or a night event. (c) Event-scale SUHII for every city, "
         "grouped by cluster, from the MSG-SEVIRI composites over the selected event window.",
         "`city_year_summary` (era5_{day,night}_n_persistent_events, "
         "era5_{day,night}_longest_event_days, {day,night}_selected_event_tier, "
         "{day,night}_seviri_suhii_c); `heat_event_catalogue` (duration_days, tier, "
         "is_selected)."),

        ("Fig. 6", "Fig_06_spot_maps_six_cities",
         "Surface hot and cold spots in six cities, day and night.",
         "Lagos, Port Harcourt, Ibadan, Akure, Kano and Abuja. Shaded areas are kernel "
         "density contours at the 50, 75 and 90 per cent levels (L50, L75, L90), darker "
         "towards the dense core; dashed outlines are tier-2 spots, which hold 1 to 9 "
         "validated pixels and are represented by a 500 m buffer around each pixel rather "
         "than a density surface. The dotted line is the urban core, the thin line the city "
         "region. Each panel carries its own scale bar. All %d cities appear in "
         "Supplementary Figure S9." % len(prof),
         "`spots` (geometry, period, spot_type, tier, spot_uid); `spot_contours` (geometry, "
         "contour_level, spot_uid); `city_zones` (uc, cr geometry)."),

        ("Fig. 7", "Fig_07_spot_area_by_cluster",
         "Spot footprint area by physiographic landscape typology.",
         "Distribution of L50 footprint area for each cluster, split by spot type and "
         "period. Boxes give the median and interquartile range, whiskers 1.5 times that "
         "range, and points the values beyond. The area axis is logarithmic. The number "
         "above each box is the count of spots in that cluster for that panel, which "
         "differs between panels. The four panels together cover all %d spots." % len(sp),
         "`spots` (cluster25, spot_type, period, area_l50_km2)."),

        ("Fig. 8", "Fig_08_population_within_spots",
         "Resident population within surface hot and cold spots.",
         "(a) Residents inside night-time hot spot footprints (L50) for each city, by symbol "
         "size and colour. (b-e) Residents by cluster and contour level for each combination "
         "of spot type and period; the three levels are nested, so L90 lies within L75 "
         "within L50. Population is summed from GHS-POP on its native 100 m grid, per "
         "polygon, with fractional overlap. Nationally, %s residents fall within night-time "
         "hot spot footprints at L50." % format(int(round(hot_night)), ","),
         "`city_exposure_by_contour` (cluster25, spot_type, period, "
         "pop_l50/l75/l90_persons); `city_profile` (geometry)."),

        ("Fig. 9", "Fig_09_stakeholder_accounts",
         "Stakeholder accounts of urban heat and their agreement with the satellite record.",
         "(a-c) Perception responses by cluster, as a share of participants: perceived "
         "temperature increase over the last ten years, the period in which heat is felt "
         "most severely, and the months perceived as the temperature peak. Based on %s. One "
         "participant left the peak-period item blank and is shown as No answer. (d) "
         "Agreement between stakeholder-marked locations and detected spots across buffer "
         "radii from 0.5 to 10 km, based on %s. %s Coordinates are the published ones, "
         "rounded to three decimal degrees, so the curves can be reproduced from the dataset "
         "alone." % (PERCEPTION_BASE, POINT_BASE, ROW_RULE),
         "`stakeholder_perception` (cluster25, perceived_warming_10yr, "
         "perceived_diurnal_severity, perceived_peak_period); `hitrate_sensitivity` "
         "(spot_type, period, buffer_m, n_hit, n_total)."),

        ("Fig. 10", "Fig_10_association_effect_sizes",
         "Association of the physiographic landscape typology with the thermal anomalies, "
         "against its strongest single element.",
         "For each combination of spot type, period and outcome, the effect size of the full "
         "typology (filled circle) and of its strongest single element - climate zone, "
         "geological substrate or elevation belt (open diamond). Occurrence is tested with a "
         "Monte Carlo permutation chi-square and reported as Cramer V; SUHII and area are "
         "tested with Kruskal-Wallis and reported as eta squared. Significance markers on "
         "the right refer to the typology test, and the element named is the strongest for "
         "that row. %s" % NB06_NOTE,
         "None from the package. "
         "`Results/06_hotspot_modelling/tables/master_synthesis.csv`."),
    ]

    tables = [
        ("Table 1", "Table_01_typology_composition",
         "Physiographic cluster composition of the %d study cities." % len(prof),
         "One row per PLT cluster, with its code, full name, number of cities, summed 2024 "
         "population after absorption, and summed city-region and urban-core area. Areas are "
         "computed in ESRI:102022. The final row totals all 16 clusters.",
         "`city_profile` (cluster25, population_wup_merged_k, cr_area_km2, uc_area_km2)."),

        ("Table 2", "Table_02_significant_spots_by_cluster",
         "Spots by physiographic landscape typology, spot type and period.",
         "Number of spots, number of cities contributing them, and total and median L50 "
         "area. The last column counts spots belonging to a city-period-type group that "
         "survived Benjamini-Hochberg false discovery rate control; `bh_significant` is a "
         "group property repeated on every spot of the group, not a per-spot test.",
         "`spots` (cluster25, spot_type, period, area_l50_km2, bh_significant, city_slug)."),

        ("Table 3", "Table_03_stakeholder_vs_satellite_cluster",
         "Stakeholder accounts against the satellite record, by physiographic landscape "
         "typology.",
         "One row per cluster, based on %s. Columns give the number of stakeholders and "
         "cities, any city represented by a single stakeholder, the urban-core Mann-Kendall "
         "trend by day and night from the cluster composite, the share of participants whose "
         "perceived warming agrees with that trend, the perceived peak period and its "
         "agreement with the observed hottest month, and the consensus level. Seven cities "
         "are represented by one stakeholder each (%s) and are flagged, because a single "
         "account cannot express agreement within a city. Nationally, 70 of 105 participants "
         "named a window containing the observed hottest month. City rows are in "
         "Supplementary Table S6." % (PERCEPTION_BASE, ", ".join(singles)),
         "`stakeholder_perception`; `composite_trend_statistics` (composite_key, zone = uc, "
         "period, mk_trend, sen_slope_c_per_decade, mk_p_value); the agreement columns from "
         "`Stakeholder_Validation_Comprehensive.csv`."),

        ("Table 4", "Table_04_typology_association",
         "Association of the typology and its elements with the thermal anomalies.",
         "Twelve rows: spot type by period by outcome. For each, the test applied, the "
         "typology effect size and p-value, the strongest single element with its effect "
         "size and Holm-adjusted p-value, and the difference in effect size. Five of the "
         "twelve typology tests reach p < 0.05. %s" % NB06_NOTE,
         "None from the package. "
         "`Results/06_hotspot_modelling/tables/master_synthesis.csv`."),
    ]

    nl = chr(10)
    out = ["# Captions - SCS main figures and tables", "",
           "Draft captions for every main item, generated by `scripts/build_scs_main.py` so "
           "the counts stay tied to the package.", "",
           "Cluster names follow `Results/manuscript_outputs/cluster_labels.csv`. One colour "
           "scheme runs through every figure: amber for day and indigo for night, red for "
           "hot spots and blue for cold.", "",
           "**Two stakeholder denominators, never mixed.** Perception items rest on "
           + PERCEPTION_BASE + ". Point-based items rest on " + POINT_BASE + ", because four "
           "cohort cities answered the perception items but marked no locations.", "",
           "**Event tier.** `validation_tier` and the selected-event tiers are a day/night "
           "pair, written as event tier (day / night), for example EXCELLENT/GOOD. A single "
           "event carries one grade, written as event tier with the period of that event.",
           "", "---", ""]
    for num, stem, title, body, src in items:
        out += ["## %s - %s" % (num, title), "",
                "`main_figures/%s.(pdf|svg)`" % stem, "",
                "**%s.** %s %s" % (num, title, body), "",
                "*Reads:* %s" % src, "", "---", ""]
    for num, stem, title, body, src in tables:
        out += ["## %s - %s" % (num, title), "",
                "`tables/%s.(csv|xlsx)`" % stem, "",
                "**%s.** %s %s" % (num, title, body), "",
                "*Reads:* %s" % src, "", "---", ""]
    out += ["## Supplementary items referenced above", "",
            "- Supplementary Figure S9: spot maps for all %d cities." % len(prof),
            "- Supplementary Figure S12: city-level perception for the %d cities with at "
            "least two participants; that threshold omits %d cities (%s)."
            % (len(multi), len(dropped), ", ".join(dropped)),
            "- Supplementary Table S6: stakeholder accounts per city, with the %d "
            "single-stakeholder cities flagged." % len(singles),
            "- Supplementary Table S7: hit rate by city and buffer, on the same %s. %s"
            % (POINT_BASE, ROW_RULE), ""]

    p = S.OUT / "captions.md"
    p.write_text(nl.join(out), encoding="utf-8")
    note("captions.md: %d figures, %d tables; the perception base and the point base are "
         "stated separately on every stakeholder item" % (len(items), len(tables)))
    print("  captions: %s (%d lines)" % (p.name, len(out)))


BUILDERS = {"fig01": fig01, "fig03": fig03, "fig04": fig04, "fig05": fig05, "fig06": fig06,
            "fig07": fig07, "fig08": fig08, "fig09": fig09, "fig10": fig10,
            "table01": table01, "table02": table02, "table03": table03, "table04": table04,
            "captions": captions, "thumbnails": thumbnails}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default="", help="comma-separated builder names")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args(argv)
    if a.list:
        print(" ".join(BUILDERS))
        return 0
    S.apply_style()
    S.MAIN_FIG.mkdir(parents=True, exist_ok=True)
    S.TABLES.mkdir(parents=True, exist_ok=True)
    names = [n.strip() for n in a.only.split(",") if n.strip()] or list(BUILDERS)
    bad = [n for n in names if n not in BUILDERS]
    if bad:
        print("unknown builder(s): %s" % bad)
        return 2
    for n in names:
        print("[%s]" % n)
        BUILDERS[n]()
    if NOTES:
        print("\nAssertions and notes (%d):" % len(NOTES))
        for s in NOTES:
            print("  - " + s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
