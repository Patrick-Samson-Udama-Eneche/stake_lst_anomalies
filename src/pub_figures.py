"""Drawing code of the SCS main figures, and the rules of Table 3.

NB07 reads and checks the data. Each function here takes that data and returns the figure or the
table, which NB07 then saves.
"""
from __future__ import annotations

import matplotlib.colors as mcolors
import matplotlib.patheffects as patheffects
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch, Patch, Wedge

import config
import temporal_panels as tp
from pub_hotspot_tables import _star


# ── Figs 5 and 6: the cluster trend grid ─────────────────────────────────────
_ZONE_PKG = {"urban_core": "uc", "bra": "bra", "delta_uc_bra": "suhii"}


def _temporal_legend(fig, y):
    Cc = tp.NB03_COLOURS
    fig.legend(handles=[
        Line2D([0],[0], color=Cc['uc_day'],    lw=1.4, label='UC — day'),
        Line2D([0],[0], color=Cc['uc_night'],  lw=1.4, label='UC — night'),
        Line2D([0],[0], color=Cc['bra_day'],   lw=1.4, label='BRA — day'),
        Line2D([0],[0], color=Cc['bra_night'], lw=1.4, label='BRA — night'),
        Line2D([0],[0], color=Cc['delta_day'], lw=1.8, label='SUHII — day'),
        Line2D([0],[0], color=Cc['delta_night'],lw=1.8, label='SUHII — night'),
        Patch(facecolor=Cc['cr_day_fill'],   alpha=.55, label='CR range — day'),
        Patch(facecolor=Cc['cr_night_fill'], alpha=.55, label='CR range — night'),
        Line2D([0],[0], color='#777', lw=.9, ls='--', label="Sen's slope"),
    ], loc='center', ncol=5, fontsize=7, framealpha=.9, bbox_to_anchor=(0.5, y))


def _trend_cell(stats, dstats, zone, period):
    src = dstats if zone == "delta_uc_bra" else stats
    if src is None or src.empty:
        return "—"
    r = src[(src["zone"] == zone) & (src["period"] == period)]
    if r.empty:
        return "—"
    r = r.iloc[0]
    sym = {"increasing": "↑", "decreasing": "↓"}.get(str(r.get("mk_trend", "")), "—")
    try:
        pf = float(r.get("mk_p")); sig = "***" if pf < .001 else ("**" if pf < .01 else ("*" if pf < .05 else "ns"))
    except (TypeError, ValueError):
        sig = ""
    try:
        dec = f"{float(r.get('sen_slope_per_decade')):+.2f}"
    except (TypeError, ValueError):
        dec = ""
    hr = "ᴴ" if r.get("autocorr_corrected", False) else ""
    return f"{sym}{sig} {dec}{hr}".strip()


def package_trend(comp, cid, zone, period):
    """One row of the published cluster composite, by temporal_panels zone name."""
    r = comp[(comp.composite_key == f"C{int(cid)}")
             & (comp.zone == _ZONE_PKG[zone]) & (comp.period == period)]
    return None if r.empty else r.iloc[0]


def trend_cell_package(comp, cid, zone, period):
    """Same cell format as _trend_cell, but sourced from the package."""
    r = package_trend(comp, cid, zone, period)
    if r is None:
        return "—"
    sym = {"increasing": "↑", "decreasing": "↓"}.get(str(r.mk_trend), "—")
    p = float(r.mk_p_value)
    sig = "***" if p < .001 else ("**" if p < .01 else ("*" if p < .05 else "ns"))
    hr = "ᴴ" if bool(r.autocorr_corrected) else ""
    return f"{sym}{sig} {float(r.sen_slope_c_per_decade):+.2f}{hr}".strip()


def render_cluster_grid(cids, kind, stats_dir, cl_meta, trend_cell=None):
    """2-col × 3-row cluster grid (no in-panel stat boxes) + a summary table below the legend.

    cl_meta maps a cluster to (climate, number of cities). trend_cell(cid, zone, period), when
    given, fills the table instead of the NB03 stats."""
    fig = plt.figure(figsize=(8.27, 11.69))
    gs = fig.add_gridspec(3, 2, top=0.965, bottom=0.345, left=0.10, right=0.90,
                          hspace=0.55, wspace=0.50)
    trows = []
    for k, cid in enumerate(cids):
        ax = fig.add_subplot(gs[k // 2, k % 2]); ax2 = ax.twinx()
        df, ddf, st, ds = tp.panel_inputs(tp.load_cluster(cid, stats_dir), kind)
        tp.draw_temporal_panel(ax, ax2, kind, df, ddf, st, ds, stat_boxes=False)
        clim, n = cl_meta.get(cid, ("", 0))
        ax.set_title(f"C{cid} — {clim} ({n} cities)", fontsize=8, fontweight="bold", pad=3)
        cell = ((lambda z, p: trend_cell(cid, z, p)) if trend_cell
                else (lambda z, p: _trend_cell(st, ds, z, p)))
        trows.append([f"C{cid}",
                      cell("urban_core", "day"),  cell("bra", "day"),  cell("delta_uc_bra", "day"),
                      cell("urban_core", "night"), cell("bra", "night"), cell("delta_uc_bra", "night")])
    _temporal_legend(fig, y=0.30)
    tax = fig.add_axes([0.05, 0.035, 0.90, 0.215]); tax.axis("off")
    cols = ["Cluster", "UC · Day", "BRA · Day", "SUHII · Day", "UC · Night", "BRA · Night", "SUHII · Night"]
    tbl = tax.table(cellText=trows, colLabels=cols, loc="center", cellLoc="center")
    tbl.auto_set_font_size(False); tbl.set_fontsize(6.4); tbl.scale(1, 1.55)
    for (rr, cc), cl in tbl.get_celld().items():
        cl.set_edgecolor("#cccccc")
        if rr == 0:
            cl.set_facecolor("#404040"); cl.set_text_props(color="white", fontweight="bold")
        elif cc == 0:
            cl.set_text_props(fontweight="bold")
    tax.set_title("Trend summary — ↑/↓ Mann-Kendall direction · */**/*** = p<.05/.01/.001 · "
                  "value = Sen slope (°C/decade) · ᴴ = Hamed–Rao corrected",
                  fontsize=6.5, pad=4)
    return fig


# ── Fig. 12: population within spots ─────────────────────────────────────────
_HOT, _COLD = "#E07B00", "#2B6CB0"
_DAYF, _NIGHTF = 0.18, 0.48          # day/night shades shared by maps + half-donut Ring2
_halo = [patheffects.withStroke(linewidth=1.6, foreground="white")]
POPULATION_KEY = {"hot": [(100_000, "100,000"), (500_000, "500,000"), (1_000_000, "1 million"), (2_000_000, "2 million")],
                  "cold": [(10_000, "10,000"), (50_000, "50,000"), (100_000, "100,000"), (200_000, "200,000")]}


def _fmt(v): return f"{v/1000:.1f}k" if v >= 1000 else f"{v:.0f}"


def _blend(h, f):
    r, g, b = mcolors.to_rgb(h); return (r + (1 - r) * f, g + (1 - g) * f, b + (1 - b) * f)


def _draw_map(ax, nigeria, hd, coords, spot_type, base, key):
    nigeria.plot(ax=ax, facecolor="#f2f1ee", edgecolor="#333", lw=0.9, zorder=1)
    nigeria.boundary.plot(ax=ax, edgecolor="#222", lw=1.1, zorder=6)
    _dc, _nc = _blend(base, _DAYF), _blend(base, _NIGHTF)
    _sub = hd[hd.spot_type == spot_type]; _rows = {}
    for _city, (_lon, _lat) in coords.items():
        _s = _sub[_sub.city == _city]
        _da = float(_s[_s.period == "day"]["area_km2_50"].sum()); _na = float(_s[_s.period == "night"]["area_km2_50"].sum())
        _dp = float(_s[_s.period == "day"]["pop_50"].sum()); _np = float(_s[_s.period == "night"]["pop_50"].sum())
        _rows[_city] = dict(lon=_lon, lat=_lat, da=_da, na=_na, dp=_dp, npp=_np, ta=_da + _na, tp=_dp + _np)
    _maxp = max((r["tp"] for r in _rows.values() if r["tp"] > 0), default=1); _SC = 0.62
    for _city, r in _rows.items():
        if r["ta"] <= 0 or r["tp"] <= 0:
            ax.plot(r["lon"], r["lat"], "o", color="#c9c9c9", ms=2.5, zorder=5, alpha=0.7); continue
        r["rad"] = _SC * (max(r["tp"], 1) / _maxp) ** 0.5; _df = r["da"] / r["ta"]
        if r["da"] > 0: ax.add_patch(Wedge((r["lon"], r["lat"]), r["rad"], 90, 90 + _df * 360, facecolor=_dc, edgecolor="white", lw=0.6, zorder=6))
        if r["na"] > 0: ax.add_patch(Wedge((r["lon"], r["lat"]), r["rad"], 90 + _df * 360, 450, facecolor=_nc, edgecolor="white", lw=0.6, zorder=6))
        ax.plot(r["lon"], r["lat"], "ko", ms=1.6, zorder=7)
    _placed = []
    for _city, r in sorted(_rows.items(), key=lambda kv: -kv[1]["tp"]):
        if r["tp"] < 500 or "rad" not in r or len(_placed) >= 13: continue
        _px, _py = r["lon"], r["lat"] - r["rad"] - 0.05
        if any((_px - qx) ** 2 + (_py - qy) ** 2 < 0.85 ** 2 for qx, qy in _placed): continue
        ax.text(_px, _py, f"{_city}\n☀{_fmt(r['dp'])} ☾{_fmt(r['npp'])}", ha="center", va="top",
                fontsize=4.6, color="#1a1a1a", zorder=8, linespacing=0.95, path_effects=_halo)
        _placed.append((_px, _py))
    _b = nigeria.total_bounds
    ax.set_xlim(_b[0] - 0.4, _b[2] + 0.4); ax.set_ylim(_b[1] - 0.8, _b[3] + 0.6); ax.set_aspect("equal"); ax.axis("off")
    _ml = (_b[1] + _b[3]) / 2; _dx = 200 / (111.32 * np.cos(np.radians(_ml))); _x0 = _b[0] + 0.2; _y0 = _b[1] - 0.55
    ax.plot([_x0, _x0 + _dx], [_y0, _y0], color="#111", lw=2.2, zorder=9, solid_capstyle="butt")
    ax.text(_x0 + _dx / 2, _y0 + 0.12, "200 km", ha="center", va="bottom", fontsize=5.5, zorder=9)
    ax.annotate("", xy=(_b[2] + 0.05, _b[3] + 0.35), xytext=(_b[2] + 0.05, _b[3] - 0.25), arrowprops=dict(arrowstyle="->", lw=1.1, color="#111"), zorder=9)
    ax.text(_b[2] + 0.05, _b[3] + 0.42, "N", ha="center", va="bottom", fontsize=6.5, fontweight="bold", zorder=9)
    # population key: nested circles drawn with the map's own radius rule, labelled on the left;
    # labels kept at least a line apart, each led to the top of its circle
    _kx, _ky = _b[2] - 0.55, _b[1] - 0.55
    _rk = {v: _SC * (v / _maxp) ** 0.5 for v, _ in key}
    _lx, _ly = _kx - max(_rk.values()) - 0.35, None
    for _v, _lab in sorted(key, reverse=True):
        _top = _ky + 2 * _rk[_v]
        _ly = _top if _ly is None else min(_top, _ly - 0.3)
        ax.add_patch(plt.Circle((_kx, _ky + _rk[_v]), _rk[_v], facecolor="none", edgecolor="#555", lw=0.7, zorder=9))
        ax.plot([_lx, _lx + 0.2, _kx], [_ly, _top, _top], color="#888", lw=0.4, zorder=9)
        ax.text(_lx - 0.05, _ly, _lab, ha="right", va="center", fontsize=5.5, zorder=9)
    ax.text(_kx, _ky + 2 * max(_rk.values()) + 0.15, "Population within spots\n(day + night)", ha="center",
            va="bottom", fontsize=6, fontweight="bold", zorder=9)
    return _maxp


def _compact_halfdonut(ax, df, title=None, fs=7.0):
    r_i, r_w = [0.32, 0.60, 0.92], [0.25, 0.28, 0.28]
    def pop(st, per, col="pop_50"):
        s = df[(df.spot_type == st) & (df.period == per)]; return float(s[col].sum()) if len(s) else 0.0
    th = pop("hot", "day") + pop("hot", "night"); tc = pop("cold", "day") + pop("cold", "night"); tot = (th + tc) or 1
    hs, cs = 180 * th / tot, 180 * tc / tot
    def put(ang, r, t, size):
        a = np.radians(ang); ax.text(r * np.cos(a), r * np.sin(a), t, ha="center", va="center", fontsize=size, color="#1a1a1a", fontweight="bold", zorder=20, path_effects=_halo)
    for st, ba, span, base in (("hot", 180 - hs, hs, _HOT), ("cold", 0, cs, _COLD)):
        stt = th if st == "hot" else tc
        if span < 0.5: continue
        ax.add_patch(Wedge((0, 0), r_i[0] + r_w[0], ba, ba + span, width=r_w[0], facecolor=_blend(base, 0.0), edgecolor="white", lw=1.2))
        if span >= 34: put(ba + span / 2, r_i[0] + r_w[0] / 2, _fmt(stt), fs + 0.5)
        ang2, s2 = ba, stt or 1
        for per, fade in (("day", _DAYF), ("night", _NIGHTF)):
            pp = pop(st, per); sw2 = span * (pp / s2)
            if pp <= 0 or sw2 <= 0.5:
                ang2 += sw2; continue
            ax.add_patch(Wedge((0, 0), r_i[1] + r_w[1], ang2, ang2 + sw2, width=r_w[1], facecolor=_blend(base, fade), edgecolor="white", lw=1.0))
            if sw2 >= 24: put(ang2 + sw2 / 2, r_i[1] + r_w[1] / 2, _fmt(pp), fs - 0.5)
            p90 = min(pop(st, per, "pop_90"), pp); p75 = min(pop(st, per, "pop_75"), pp); ang3 = ang2
            for seg, f3 in ((p90, 0.62), (max(0, p75 - p90), 0.74), (max(0, pp - p75), 0.85)):
                sw3 = sw2 * (seg / pp) if pp > 0 else 0
                if seg > 0 and sw3 > 0.3:
                    ax.add_patch(Wedge((0, 0), r_i[2] + r_w[2], ang3, ang3 + sw3, width=r_w[2], facecolor=_blend(base, f3), edgecolor="white", lw=0.6))
                    if sw3 >= 30: put(ang3 + sw3 / 2, r_i[2] + r_w[2] / 2, _fmt(seg), fs - 1.3)
                    ang3 += sw3
            ang2 += sw2
    ax.text(0, 0.13, _fmt(tot), ha="center", va="center", fontsize=fs + 3, fontweight="bold", color="#333")
    ax.text(0, -0.03, "pop", ha="center", va="center", fontsize=fs - 1.5, color="#777")
    if title: ax.text(0, 1.58, title, ha="center", va="center", fontsize=fs + 2, fontweight="bold")
    ax.set_xlim(-1.32, 1.32); ax.set_ylim(-0.22, 1.82); ax.axis("off"); ax.set_aspect("equal")


def _agg(sub): return sub.groupby(["spot_type", "period"])[["pop_50", "pop_75", "pop_90"]].sum().reset_index()


def population_within_spots(hd, nigeria, coords, n_cities):
    """The two maps and five half-donuts. Returns the figure and each map's largest circle.

    hd holds pop_50/75/90, area_km2_50 and cluster per city; coords maps a city to its (lon, lat);
    n_cities maps a cluster to its number of study cities."""
    fig = plt.figure(figsize=(8.27, 11.0))
    largest = {"hot": _draw_map(fig.add_axes([0.015, 0.70, 0.475, 0.29]), nigeria, hd, coords, "hot", _HOT,
                                POPULATION_KEY["hot"]),
               "cold": _draw_map(fig.add_axes([0.51, 0.70, 0.475, 0.29]), nigeria, hd, coords, "cold", _COLD,
                                 POPULATION_KEY["cold"])}
    _POS = {"C25": [0.02, 0.50, 0.36, 0.155], "C4": [0.62, 0.50, 0.36, 0.155], "NAT": [0.32, 0.34, 0.36, 0.16],
            "C9": [0.02, 0.175, 0.36, 0.155], "C13": [0.62, 0.175, 0.36, 0.155]}
    _CID = {"C25": 25, "C4": 4, "C13": 13, "C9": 9}
    for _k, _rect in _POS.items():
        _ax = fig.add_axes(_rect)
        if _k == "NAT":
            _compact_halfdonut(_ax, _agg(hd), title="(c) National", fs=7.6)
        else:
            _compact_halfdonut(_ax, _agg(hd[hd.cluster == _CID[_k]]),
                               title=f"C{_CID[_k]} ({n_cities.get(_CID[_k], 0)} cities)", fs=6.3)
    _axl = fig.add_axes([0.0, 0.0, 1.0, 0.14]); _axl.axis("off")
    _h1 = [Patch(fc=_blend(_HOT, _DAYF), label="Hot · Day"), Patch(fc=_blend(_HOT, _NIGHTF), label="Hot · Night"),
           Patch(fc=_blend(_COLD, _DAYF), label="Cold · Day"), Patch(fc=_blend(_COLD, _NIGHTF), label="Cold · Night")]
    _lg1 = _axl.legend(handles=_h1, loc="center left", bbox_to_anchor=(0.02, 0.62), ncol=2, fontsize=7.5,
                       title="Spot type × period  (darker = Day · lighter = Night)", title_fontsize=8, framealpha=0.9)
    _lg1.get_title().set_fontweight("bold"); _axl.add_artist(_lg1)
    _h2 = [Patch(fc=_blend("#888", 0.62), label="L90 dense core"), Patch(fc=_blend("#888", 0.74), label="L75 inner zone"),
           Patch(fc=_blend("#888", 0.85), label="L50 outer extent"),
           Line2D([0], [0], marker="o", mfc="none", mec="#555", ls="none", ms=10, label="circle ∝ pop (maps)")]
    _lg2 = _axl.legend(handles=_h2, loc="center right", bbox_to_anchor=(0.98, 0.62), ncol=2, fontsize=7.5,
                       title="Half-donut contour rings  ·  map symbols", title_fontsize=8, framealpha=0.9)
    _lg2.get_title().set_fontweight("bold")
    _axl.text(0.5, 0.06, "Maps: city wedge split = Day/Night spot area, circle size ∝ population within spots  ·  "
              "Half-donuts: rings = Type → Day/Night → Contour; ☀ = day  ☾ = night",
              ha="center", va="bottom", fontsize=6.8, color="#444", transform=_axl.transAxes)
    return fig, largest


# ── Table 3: stakeholder accounts against the satellite record ───────────────
_MONTHS = dict(enumerate(["January", "February", "March", "April", "May", "June", "July",
                          "August", "September", "October", "November", "December"], start=1))
_SEASONS = {"March – May": ["March", "April", "May"], "June – August": ["June", "July", "August"],
            "September – November": ["September", "October", "November"],
            "December – February": ["December", "January", "February"]}
_DIURNAL = {"During the day": "Day", "At night": "Night", "Both": "Both"}


def uc_increase(trends, city, per):
    """True when the city's urban-core trend is a significant increase."""
    r = trends[(trends.city == city) & (trends.zone == "uc") & (trends.period == per)].iloc[0]
    return r.mk_trend == "increasing" and r.mk_p_value < 0.05


def trend_label(trends, city, per):
    return "Significant increase" if uc_increase(trends, city, per) else "No significant trend"


def trend_count(trends, cities, per):
    return f"{sum(uc_increase(trends, c, per) for c in cities)}/{len(cities)} increasing"


def _hottest(sub):
    """Hottest month of a monthly climatology (month -> mean)."""
    return _MONTHS[int(sub.idxmax())]


def _diurnal(s):
    """Day, Night or Both, the most frequent among those who answered; a tie is Both."""
    vc = s.map(_DIURNAL).dropna().value_counts()
    if vc.empty:
        return "—"
    top = vc[vc == vc.iloc[0]].index
    return top[0] if len(top) == 1 else "Both"


def _season(s):
    """The season named most often; two named equally often are both given, in calendar order."""
    vc = s[s.isin(list(_SEASONS))].value_counts()
    if vc.empty:
        return "—"
    return " or ".join(q for q in _SEASONS if q in vc[vc == vc.iloc[0]].index)


def _consensus(a, m, city):
    if a > 70 and m > 70:
        return "High"
    if city and a > 50 and m > 50 and (a + m) / 2 > 60:
        return "Medium"
    return "Medium" if (a + m) / 2 >= 60 else "Low"


def stakeholder_table(perception, trends, climatology, series):
    """Table 3's rows, with the participants' agreement flags and the single-stakeholder cities.

    Warming agreement: "Yes" where the city's day urban-core trend is a significant increase, else
    anything but "Yes". Peak-month agreement: the season named contains the city's hottest month,
    by day or by night."""
    d = perception.assign(cluster25=perception.cluster25.astype(int))
    cities = sorted(d.city.unique())
    hotd = {c: _hottest(climatology[(climatology.city == c) & (climatology.zone == "uc") & (climatology.period == "day")]
                        .set_index("month").mean_value_c) for c in cities}
    hotn = {c: _hottest(climatology[(climatology.city == c) & (climatology.zone == "uc") & (climatology.period == "night")]
                        .set_index("month").mean_value_c) for c in cities}
    d["q61"] = [(w == "Yes") if uc_increase(trends, c, "day") else (w != "Yes")
                for c, w in zip(d.city, d.perceived_warming_10yr)]
    d["q58"] = [(hotd[c] in _SEASONS.get(p, [])) or (hotn[c] in _SEASONS.get(p, []))
                for c, p in zip(d.city, d.perceived_peak_period)]
    singles = sorted(d.groupby("city").size().loc[lambda s: s == 1].index)

    def row(level, unit, cl, g, day, night, hot_day, hot_night, cons):
        a, m = round(100 * g.q61.mean(), 1), round(100 * g.q58.mean(), 1)
        return {"Level": level, "Unit": unit, "Cluster": cl, "N": len(g),
                "Pct_of_Total": round(100 * len(g) / len(d), 1),
                "Q61_Warming_Input": f"{int((g.perceived_warming_10yr == 'Yes').sum())}/{len(g)}",
                "Q61_Annual_Agreement_%": a, "LST_Day_Trend": day, "LST_Night_Trend": night,
                "Q60_Diurnal_Majority": _diurnal(g.perceived_diurnal_severity),
                "Q58_Peak_Response": _season(g.perceived_peak_period), "Q58_Monthly_Agreement_%": m,
                "LST_Day_Hottest_Month": hot_day, "LST_Night_Hottest_Month": hot_night,
                "Consensus_Level": cons(a, m)}

    rows = []
    for (cl, city), g in d.groupby(["cluster25", "city"]):
        rows.append(row("City", city + (" †" if city in singles else ""), f"C{cl}", g,
                        trend_label(trends, city, "day"), trend_label(trends, city, "night"), hotd[city], hotn[city],
                        lambda a, m: _consensus(a, m, True)))
    for cl, g in d.groupby("cluster25"):
        cc = sorted(g.city.unique())
        clim = {per: (series[(series.cluster25 == cl) & (series.zone == "uc") & (series.period == per)]
                      .groupby(["year", "month"]).value_c.mean().groupby("month").mean())
                for per in ("day", "night")}
        rows.append(row("Cluster", f"C{cl}", f"C{cl}", g, trend_count(trends, cc, "day"), trend_count(trends, cc, "night"),
                        _hottest(clim["day"]), _hottest(clim["night"]), lambda a, m: _consensus(a, m, False)))
    rows.append(row("National", "National (all cities)", "All", d,
                    trend_count(trends, cities, "day"), trend_count(trends, cities, "night"),
                    pd.Series(hotd).mode().iloc[0], pd.Series(hotn).mode().iloc[0],
                    lambda a, m: "aggregate"))
    return pd.DataFrame(rows), d, singles


# ── Fig. 14: hit rate against buffer distance ────────────────────────────────
_DAY_FILL, _NIGHT_FILL, _FILL_A = "#F2C14E", "#9BA3AE", 0.25


def hitrate_buffer(sens_df, chart_type="national"):
    """chart_type='cluster': one line per Cluster25 group; 'national': one aggregate line."""
    buffer_m = getattr(config, "STAKEHOLDER_VALIDATION_BUFFER_M", 1000)
    fig_s, (ax_hot, ax_cold) = plt.subplots(1, 2, figsize=(14, 6.5), sharey=False)
    fig_s.subplots_adjust(bottom=0.22, wspace=0.35, top=0.80)
    for _st, _ax in (('hot', ax_hot), ('cold', ax_cold)):
        _sub = sens_df[sens_df.spot_type == _st]
        _clr_spot = '#CC2222' if _st == 'hot' else '#1155AA'
        _ax.set_xlabel('Buffer distance (km)', fontsize=10)
        _ax.set_ylabel('Hit-rate (%)', fontsize=10)
        _ax.set_title(f'{"(a)  Hot" if _st == "hot" else "(b)  Cold"} Spots',
                      fontsize=12, fontweight='bold', color=_clr_spot)
        _ax.grid(True, alpha=0.2, ls='--')
        _ax.tick_params(labelsize=9)
        _ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x:.0f}%'))
        _ax.set_ylim(-3, 108)
        _ax.axvline(buffer_m / 1000, color='#777', lw=0.9, ls=':', zorder=1)
        _ax2 = _ax.twinx()
        _ax2.set_ylabel('Total hit count', fontsize=9, color='#333')
        _ax2.tick_params(axis='y', labelsize=8, labelcolor='#333')
        for _per, _fill_clr in (('day', _DAY_FILL), ('night', _NIGHT_FILL)):
            _psub = _sub[_sub.period == _per]
            if not len(_psub):
                continue
            _tot = (_psub.groupby('buffer_m')[['n_hit', 'n_total']].sum()
                    .reset_index().sort_values('buffer_m'))
            _ax2.fill_between(_tot['buffer_m'] / 1000, 0, _tot['n_hit'],
                              alpha=_FILL_A, color=_fill_clr, zorder=1)
            _ax2.plot(_tot['buffer_m'] / 1000, _tot['n_hit'], color=_fill_clr, lw=0.7,
                      alpha=0.6, zorder=1)
        if not len(_sub):
            _ax.text(0.5, 0.5, 'No data', ha='center', va='center',
                     transform=_ax.transAxes, color='#aaa', fontsize=11)
            continue
        if chart_type == 'cluster':
            _cl_agg = (_sub.dropna(subset=['cluster25'])
                       .groupby(['buffer_m', 'cluster25', 'period'])[['n_hit', 'n_total']]
                       .sum().reset_index())
            _cl_agg['hit_rate_cl'] = _cl_agg['n_hit'] / _cl_agg['n_total']
            for _cl in sorted(_cl_agg.groupby('cluster25')['n_hit'].sum()
                              .loc[lambda s: s > 0].index.tolist()):
                _clr_cl = config.CLUSTER25_COLORS.get(int(_cl), '#888')
                for _per, _ls in (('day', '-'), ('night', '--')):
                    _cs = (_cl_agg[(_cl_agg.cluster25 == _cl) & (_cl_agg.period == _per)]
                           .sort_values('buffer_m'))
                    if len(_cs):
                        _ax.plot(_cs['buffer_m'] / 1000, _cs['hit_rate_cl'] * 100,
                                 color=_clr_cl, lw=1.5, ls=_ls, zorder=3)
        else:
            for _per, _ls, _lw in (('day', '-', 2.5), ('night', '--', 2.0)):
                _ns = (_sub[_sub.period == _per].groupby('buffer_m')[['n_hit', 'n_total']]
                       .sum().reset_index().sort_values('buffer_m'))
                if len(_ns):
                    _ax.plot(_ns['buffer_m'] / 1000, _ns['n_hit'] / _ns['n_total'] * 100,
                             color=_clr_spot, lw=_lw, ls=_ls, zorder=4)
    _leg = [plt.Line2D([0], [0], ls='-', color='#555', lw=1.3, label='Daytime'),
            plt.Line2D([0], [0], ls='--', color='#555', lw=1.3, label='Nighttime'),
            plt.Rectangle((0, 0), 1, 1, fc=_DAY_FILL, alpha=_FILL_A + 0.1,
                          label='Daytime total hits'),
            plt.Rectangle((0, 0), 1, 1, fc=_NIGHT_FILL, alpha=_FILL_A + 0.1,
                          label='Nighttime total hits')]
    if chart_type == 'cluster':
        _leg = [plt.Line2D([0], [0], color=config.CLUSTER25_COLORS.get(int(_cl), '#888'), lw=1.5,
                           label=f'C{int(_cl)}')
                for _cl in sorted(sens_df.dropna(subset=['cluster25'])
                                  .groupby('cluster25')['n_hit'].sum()
                                  .loc[lambda s: s > 0].index.tolist())] + _leg
    fig_s.legend(handles=_leg, loc='lower center', ncol=min(len(_leg), 8), fontsize=8.5,
                 framealpha=0.92, edgecolor='#bbb', bbox_to_anchor=(0.5, 0.01))
    return fig_s


# ── Fig. 15: association effect sizes ────────────────────────────────────────
SPOTS, PERIODS = ['hot', 'cold'], ['day', 'night']
_ELEMS = ['climate_class', 'geology_class', 'elevation_class']
_ELEM_NAME = {'climate_class': 'Climate Zone', 'geology_class': 'Geology', 'elevation_class': 'Elevation Belt'}
ELEMENT_KEY = {v: k for k, v in _ELEM_NAME.items()}
OUTCOME_LABEL = {'occurrence': 'Occurrence', 'suhii': 'SUHII', 'area': 'Area (L50)'}


def association_results(part_a, part_b):
    """NB06's results as the figure reads them: composite effects with stars, element effects, element stars.

    part_b maps (spot type, period) to that combination's table."""
    comp = {'occurrence': {}, 'suhii': {}, 'area': {}}
    for _, _r in part_a.iterrows():
        _st, _pe = str(_r['Spot Type']).lower(), str(_r['Period']).lower()
        comp['occurrence'][(_st, _pe)] = {'cramers_v': float(_r['V (occ)']), 'st': _star(_r['χ² (occ)'])}
        comp['suhii'][(_st, _pe)] = {'eta2': float(_r['η² (suhii)']), 'st': _star(_r['H (suhii)'])}
        comp['area'][(_st, _pe)] = {'eta2': float(_r['η² (area)']), 'st': _star(_r['H (area)'])}
    elem, stars = {}, {}
    for _st in SPOTS:
        for _pe in PERIODS:
            for _, _r in part_b[(_st, _pe)].iterrows():
                _e = ELEMENT_KEY.get(str(_r['Element']).strip())
                if _e is None: continue
                elem[(_st, _pe, _e, 'occurrence')] = {'cramers_v': float(_r['V'])}
                elem[(_st, _pe, _e, 'suhii')] = {'eta2': float(_r['η²_suhii'])}
                elem[(_st, _pe, _e, 'area')] = {'eta2': float(_r['η²_area'])}
                stars[(_st, _pe, _e, 'occurrence')] = _star(_r['sig_occ'])
                stars[(_st, _pe, _e, 'suhii')] = _star(_r['sig_suhii'])
                stars[(_st, _pe, _e, 'area')] = _star(_r['sig_area'])
    return comp, elem, stars


def association_effect_sizes(comp, elem, stars):
    """Forest plot of the composite typology and the three elements, for each outcome."""
    _TH = {'occurrence': {'s': .10, 'm': .30, 'l': .50, 'fl': .60, 'lbl': "Cramér's V"},
           'suhii': {'s': .01, 'm': .06, 'l': .14, 'fl': .22, 'lbl': 'η²'},
           'area': {'s': .01, 'm': .06, 'l': .14, 'fl': .22, 'lbl': 'η² (L50)'}}
    _ZC = {'negligible': '#FFAAAA', 'small': '#FFCC99', 'medium': '#FFEE99', 'large': '#AADDAA'}; _ZA = 0.42
    _CFILL = '#A8D8A8'
    _EFILL = {'climate_class': '#F4A8A8', 'geology_class': '#A8A8F4', 'elevation_class': '#F4CCA8'}
    _EMARK = {'climate_class': 'D', 'geology_class': 's', 'elevation_class': '^'}
    _ECS, _ECN, _LWS, _LWN = '#CC1100', '#111111', 2.0, 0.9
    _FB, _FT = 10, 11

    def _effs(out):
        v = []
        for st in SPOTS:
            for pe in PERIODS:
                a = comp[out].get((st, pe))
                if a: v.append(a['cramers_v'] if out == 'occurrence' else a['eta2'])
                for e in _ELEMS:
                    b = elem.get((st, pe, e, out))
                    if b: v.append(b['cramers_v'] if out == 'occurrence' else b['eta2'])
        return v

    fig, _axes = plt.subplots(1, 3, figsize=(11.69, 7.6), gridspec_kw={'wspace': 0.46})
    for _ax, _out, _let in zip(_axes, ['occurrence', 'suhii', 'area'], ['(a)', '(b)', '(c)']):
        _t = _TH[_out]; _s, _m, _l = _t['s'], _t['m'], _t['l']
        _al = _effs(_out); _xl = max(_t['fl'], max(_al) * 1.15) if _al else _t['fl']
        _ax.set_title(f'{_let}  {OUTCOME_LABEL[_out]}', fontsize=_FT, fontweight='bold', pad=8)
        _ax.set_xlabel(_t['lbl'], fontsize=_FB); _ax.set_xlim(-0.01, _xl)
        _ax.axvspan(-0.01, _s, color=_ZC['negligible'], alpha=_ZA, zorder=0)
        _ax.axvspan(_s, _m, color=_ZC['small'], alpha=_ZA, zorder=0)
        _ax.axvspan(_m, _l, color=_ZC['medium'], alpha=_ZA, zorder=0)
        _ax.axvspan(_l, _xl, color=_ZC['large'], alpha=_ZA, zorder=0)
        for _rf, _ls in ((_s, '--'), (_m, ':'), (_l, '-.')):
            _ax.axvline(_rf, color='#888888', lw=0.7, ls=_ls, zorder=1)
        _ax.axvline(0, color='#CCCCCC', lw=0.7, zorder=1)
        _yl, _yp, _yc = [], [], 0
        for st in SPOTS:
            for pe in PERIODS:
                _yl.append(f'{st.capitalize()} / {pe.capitalize()}'); _yp.append(_yc)
                a = comp[_out].get((st, pe))
                if a:
                    _eA = a['cramers_v'] if _out == 'occurrence' else a['eta2']; _sA = bool(a['st'])
                    _ax.scatter(_eA, _yc, color=_CFILL, s=110, marker='o', zorder=5,
                                edgecolors=_ECS if _sA else _ECN, linewidths=_LWS if _sA else _LWN)
                    if _sA:
                        _ax.text(_eA + _xl * 0.015, _yc + 0.20, a['st'], fontsize=8,
                                 color=_ECS, va='bottom', fontweight='bold')
                _off = {'climate_class': -0.22, 'geology_class': 0.0, 'elevation_class': 0.22}
                for e in _ELEMS:
                    b = elem.get((st, pe, e, _out))
                    if b:
                        _eB = b['cramers_v'] if _out == 'occurrence' else b['eta2']
                        _sB = bool(stars.get((st, pe, e, _out), ''))
                        _ax.scatter(_eB, _yc + _off[e], color=_EFILL[e], s=60, marker=_EMARK[e], zorder=4,
                                    edgecolors=_ECS if _sB else _ECN, linewidths=_LWS if _sB else _LWN)
                _yc += 1
        _ax.set_yticks(_yp); _ax.set_yticklabels(_yl, fontsize=_FB); _ax.invert_yaxis()
        _ax.grid(True, axis='x', alpha=0.18, ls='--', zorder=2); _ax.tick_params(axis='x', labelsize=_FB - 1)
        _ax.spines['top'].set_visible(False); _ax.spines['right'].set_visible(False)

    fig.subplots_adjust(top=0.91, bottom=0.205, left=0.08, right=0.98)
    _BT, _BH = 0.020, 0.130
    fig.add_artist(FancyBboxPatch((0.01, _BT), 0.97, _BH, boxstyle='square,pad=0', facecolor='#fafafa',
                                  edgecolor='#aaaaaa', linewidth=1.2, transform=fig.transFigure, zorder=0, clip_on=False))
    for _sx in (0.34, 0.67):
        fig.add_artist(Line2D([_sx, _sx], [_BT + 0.006, _BT + _BH - 0.006], transform=fig.transFigure,
                              color='#cccccc', lw=1.0, zorder=1, clip_on=False))
    _lkw = dict(fontsize=_FB - 0.5, frameon=False, handlelength=1.2, handletextpad=0.5, borderpad=0.0,
                columnspacing=0.9, bbox_transform=fig.transFigure)
    _ay = _BT + 0.018
    _zh = [Patch(facecolor=_ZC[k], alpha=_ZA + 0.2, edgecolor='#888', lw=0.6, label=v)
           for k, v in [('negligible', 'Negligible'), ('small', 'Small'), ('medium', 'Medium'), ('large', 'Large')]]
    _lg1 = fig.legend(handles=_zh, title='Effect Size Zone', title_fontsize=_FB, loc='lower left',
                      bbox_to_anchor=(0.03, _ay), ncol=2, **_lkw); _lg1.get_title().set_fontweight('bold')
    _nt = '#666666'
    _ph = [Line2D([0], [0], marker='o', ls='none', color=_CFILL, markeredgecolor=_nt, markeredgewidth=1.0, markersize=9, label='Composite typology'),
           Line2D([0], [0], marker='D', ls='none', color=_EFILL['climate_class'], markeredgecolor=_nt, markeredgewidth=1.0, markersize=7, label='Climate Zone'),
           Line2D([0], [0], marker='s', ls='none', color=_EFILL['geology_class'], markeredgecolor=_nt, markeredgewidth=1.0, markersize=7, label='Geology'),
           Line2D([0], [0], marker='^', ls='none', color=_EFILL['elevation_class'], markeredgecolor=_nt, markeredgewidth=1.0, markersize=8, label='Elevation Belt')]
    _lg2 = fig.legend(handles=_ph, title='Predictor', title_fontsize=_FB, loc='lower left',
                      bbox_to_anchor=(0.36, _ay), ncol=2, **_lkw); _lg2.get_title().set_fontweight('bold')
    _sh = [Line2D([0], [0], marker='o', ls='none', color='#AAAAAA', markeredgecolor=_ECS, markeredgewidth=_LWS, markersize=10, label='Significant'),
           Line2D([0], [0], marker='o', ls='none', color='#AAAAAA', markeredgecolor=_ECN, markeredgewidth=_LWN, markersize=10, label='Not significant')]
    _lg3 = fig.legend(handles=_sh, title='Significance (p < 0.05)', title_fontsize=_FB, loc='lower left',
                      bbox_to_anchor=(0.69, _ay), ncol=1, **_lkw); _lg3.get_title().set_fontweight('bold')
    return fig


# ── S3: profession colours ───────────────────────────────────────────────────
def profession_colours(professions):
    """NB02's colours for the professions; the unlisted ones take the fallback list in sorted order."""
    colours = {"Academic": "#1f77b4", "Practitioner (Public/private)": "#ff7f0e", "GIS expert": "#2ca02c",
               "Academic|Practitioner (Public/private)": "#d62728",
               "GIS expert|Practitioner (Public/private)": "#9467bd", "Academic|GIS expert": "#8c564b",
               "Academic|GIS expert|Practitioner (Public/private)": "#e377c2"}
    fallback = ["#7f7f7f", "#bcbd22", "#17becf", "#aec7e8", "#ffbb78", "#98df8a"]
    for i, p in enumerate(p for p in sorted(pd.unique(professions)) if p not in colours and pd.notna(p)):
        colours[p] = fallback[i % len(fallback)]
    return colours
