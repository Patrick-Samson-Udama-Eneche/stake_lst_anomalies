"""
Reusable annual / monthly LST-trend *panel* rendering for the publication notebook.

The NB03 chart ``create_temporal_chart`` draws a combined annual (left) + monthly
(right) figure per entity.  For the manuscript we need those two panels **separated**
(Figure 7 = annual, Figure 8 = monthly) and arranged into grids across the study
levels (cluster / city / national).  This module exposes:

    draw_temporal_panel(ax, ax2, kind, df, ddf, stats, dstats)
        Draw one annual OR monthly panel into a supplied axes pair.

    load_cluster(cluster_id, stats_dir)   -> dict of the panel inputs
    load_city(slug, city_dir)             -> dict of the panel inputs
    load_national(city_dirs)              -> dict of the panel inputs

Colours mirror ``visualization._NB03_COLOURS`` (day = orange/gold/red,
night = black/grey/purple).  Trend statistics reuse
``temporal_analysis.run_trend_analysis`` so the printed Sen slopes and MK
significance match NB03 exactly.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Day = warm tones, Night = near-black/grey (never blue), matching NB03.
NB03_COLOURS = {
    'uc_day': '#E07B00', 'bra_day': '#B8860B', 'delta_day': '#B22222', 'cr_day_fill': '#FFDAB9',
    'uc_night': '#1C1C1C', 'bra_night': '#6B6B6B', 'delta_night': '#9932CC', 'cr_night_fill': '#A8A8A8',
}
MON_ABBR = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
_STAT_COLS = ['mk_trend', 'mk_p', 'sen_slope_per_year', 'sen_slope_per_decade',
              'intercept', 'autocorr_corrected']


# ─────────────────────────── drawing ────────────────────────────────────────
def _smooth(x, y, kind):
    try:
        from scipy.ndimage import gaussian_filter1d as gf
        from scipy.interpolate import make_interp_spline as mis
    except ImportError:
        return np.asarray(y, float)
    y = np.asarray(y, float)
    if len(y) < 4:
        return y
    if kind == 'monthly':
        try:
            spl = mis(np.asarray(x, float), y, k=3)
            return np.array([float(spl(np.array([xi]))[0]) for xi in x])
        except Exception:
            return y
    return gf(y, sigma=0.8)


def _trend_line(idx, slope, intercept):
    x = np.asarray(idx, float)
    return intercept + slope * (x - x[0])


def _row(sdf, zone, period):
    if sdf is None or getattr(sdf, 'empty', True):
        return None
    sub = (sdf[(sdf['zone'] == zone) & (sdf['period'] == period)]
           if 'zone' in sdf.columns else sdf[sdf['period'] == period])
    return sub.iloc[0] if not sub.empty else None


def _stats_box(ax, rows, header, y, va):
    lines = [f'─ {header} ─']
    any_d = False
    for label, r in rows:
        if r is None:
            continue
        any_d = True
        sym = {'increasing': '↑', 'decreasing': '↓'}.get(str(r.get('mk_trend', '')), '—')
        try:
            pf = float(r.get('mk_p', np.nan))
            sig = '***' if pf < .001 else ('**' if pf < .01 else ('*' if pf < .05 else 'ns'))
        except (TypeError, ValueError):
            sig = ''
        hr = '[H&R]' if r.get('autocorr_corrected', False) else ''
        try:
            dec = f"{float(r.get('sen_slope_per_decade', np.nan)):+.2f}°C/dec"
        except (TypeError, ValueError):
            dec = ''
        lines.append(f'  {label}: {" ".join(p for p in [sym, sig, dec, hr] if p)}')
    if any_d:
        ax.text(0.02, y, '\n'.join(lines), transform=ax.transAxes, fontsize=6.5,
                va=va, ha='left', zorder=12, linespacing=1.25,
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8,
                          lw=0.4, edgecolor='#bbb'))


def _peak_trough(ax, x, y_raw, col, is_monthly):
    y = np.asarray(y_raw, float)
    if len(y) < 3:
        return
    for idx, dy in [(int(np.argmax(y)), 8), (int(np.argmin(y)), -12)]:
        xi, yi = x[idx], y[idx]
        ax.plot(xi, yi, marker='o', mfc='none', mec=col, ms=5, mew=1.0, zorder=6)
        tag = f"{MON_ABBR[int(xi) - 1]} {yi:.1f}°C" if is_monthly else f"{int(xi)}: {yi:.1f}°C"
        ax.annotate(tag, xy=(xi, yi), xytext=(0, dy), textcoords='offset points',
                    fontsize=6.5, color=col, ha='center', zorder=7,
                    bbox=dict(boxstyle='round,pad=0.15', facecolor='white',
                              edgecolor=col, alpha=0.85, lw=0.4))


def _suhii_ylim(dd):
    if dd is None or dd.empty:
        return None
    v = dd['delta_lst'].dropna().values
    if not len(v):
        return None
    c = (v.max() + v.min()) / 2
    h = max(v.max() - v.min(), 0.3) / 2
    return (c - h * 3.5, c + h * 3.5)


def draw_temporal_panel(ax, ax2, kind, df, ddf, stats, dstats,
                        colours=None, ylim_lst=(10, 50), stat_boxes=True, suhii_ylabel=True):
    """Draw one annual|monthly LST-trend panel (day+night, UC/BRA/SUHII) into ax/ax2."""
    C = colours or NB03_COLOURS
    ax.set_ylim(*ylim_lst)
    for period in ['day', 'night']:
        uc, bra = C[f'uc_{period}'], C[f'bra_{period}']
        dcol, crf = C[f'delta_{period}'], C[f'cr_{period}_fill']
        for zone, col in [('urban_core', uc), ('bra', bra)]:
            sub = df[(df['zone'] == zone) & (df['period'] == period)]
            if sub.empty:
                continue
            if kind == 'annual':
                sub = sub.sort_values('year'); x, yr = sub['year'].values, sub['median_lst'].values
            else:
                cl = sub.groupby('month')['median_lst'].mean().reset_index()
                x, yr = cl['month'].values, cl['median_lst'].values
            ax.plot(x, _smooth(x, yr, kind), color=col, lw=1.4, zorder=4)
            sr = _row(stats, zone, period)
            if sr is not None and pd.notna(sr.get('sen_slope_per_year', np.nan)):
                ax.plot(x, _trend_line(x, sr['sen_slope_per_year'], sr['intercept']),
                        color=col, lw=0.8, ls='--', zorder=3)
            if zone == 'urban_core':
                _peak_trough(ax, list(x), list(yr), col, kind == 'monthly')
        cr = df[(df['zone'] == 'city_region') & (df['period'] == period)]
        if not cr.empty and 'p05_lst' in cr.columns:
            if kind == 'annual':
                cs = cr.sort_values('year')
                ax.fill_between(cs['year'], cs['p05_lst'], cs['p95_lst'], color=crf, alpha=0.4, zorder=1)
            else:
                cc = cr.groupby('month').agg(p05=('p05_lst', 'mean'), p95=('p95_lst', 'mean')).reset_index()
                ax.fill_between(cc['month'], cc['p05'], cc['p95'], color=crf, alpha=0.4, zorder=1)
        dd = ddf[ddf['period'] == period] if ddf is not None and not ddf.empty else pd.DataFrame()
        if not dd.empty:
            if kind == 'annual':
                dd = dd.sort_values('year'); xd, ydr = dd['year'].values, dd['delta_lst'].values
            else:
                dc = dd.groupby('month')['delta_lst'].mean().reset_index()
                xd, ydr = dc['month'].values, dc['delta_lst'].values
            yd = _smooth(xd, ydr, kind)
            ax2.plot(xd, yd, color=dcol, lw=6, alpha=0.15, zorder=6, solid_capstyle='round')
            ax2.plot(xd, yd, color=dcol, lw=1.8, zorder=8)
            dr = _row(dstats, 'delta_uc_bra', period)
            if dr is not None and pd.notna(dr.get('sen_slope_per_year', np.nan)):
                ax2.plot(xd, _trend_line(xd, dr['sen_slope_per_year'], dr['intercept']),
                         color=dcol, lw=1.0, ls='--', zorder=7)
    lim = _suhii_ylim(ddf)
    if lim:
        ax2.set_ylim(*lim)
    ax2.axhline(0, color='#888', lw=0.6, ls=':', alpha=0.7, zorder=2)
    if kind == 'monthly':
        ax.axvspan(5.5, 10.5, color='#AADDFF', alpha=0.12, zorder=0)
        ax.set_xticks(range(1, 13)); ax.set_xticklabels(MON_ABBR, fontsize=6.5, rotation=90)
        ax.set_xlabel('Month', fontsize=6.5)
    else:
        yrs = sorted({int(y) for y in df['year'].unique()})
        tks = [y for y in yrs if (y - yrs[0]) % 4 == 0]
        ax.set_xticks(tks); ax.set_xticklabels([str(y) for y in tks], fontsize=6.5, rotation=45, ha='right')
        ax.set_xlabel('Year', fontsize=6.5)
    ax.tick_params(labelsize=5.5); ax2.tick_params(labelsize=5.5, colors='#555')
    ax.set_ylabel(('Annual' if kind == 'annual' else 'Monthly') + ' median LST (°C)', fontsize=6.5)
    if suhii_ylabel:
        ax2.set_ylabel('SUHII — UC−BRA (°C)', fontsize=6.5, color='#555')
    if stat_boxes:
        _stats_box(ax, [('UC', _row(stats, 'urban_core', 'day')), ('BRA', _row(stats, 'bra', 'day')),
                        ('SUHII', _row(dstats, 'delta_uc_bra', 'day'))], 'Day (- - Sen)', 0.985, 'top')
        _stats_box(ax, [('UC', _row(stats, 'urban_core', 'night')), ('BRA', _row(stats, 'bra', 'night')),
                        ('SUHII', _row(dstats, 'delta_uc_bra', 'night'))], 'Night (- - Sen)', 0.015, 'bottom')


# ─────────────────────────── data loaders ───────────────────────────────────
def _delta_from_lst(lst_df, keys):
    """SUHII (UC-BRA) delta series from a zoned LST table.  keys = ['year'] or ['year','month']."""
    uc = lst_df[lst_df['zone'] == 'urban_core'].set_index(keys + ['period'])['median_lst']
    br = lst_df[lst_df['zone'] == 'bra'].set_index(keys + ['period'])['median_lst']
    d = (uc - br).rename('delta_lst').reset_index()
    d['zone'] = 'delta_uc_bra'
    return d


def _trend_stats(series, kind, zone, period):
    from temporal_analysis import run_trend_analysis
    st = run_trend_analysis(series.dropna(), mode=kind)
    st.update(zone=zone, period=period)
    return st


def _delta_stats(delta_df, kind):
    rows = []
    for period in ['day', 'night']:
        d = delta_df[delta_df['period'] == period]
        if d.empty:
            continue
        if kind == 'annual':
            s = pd.Series(d.sort_values('year')['delta_lst'].values,
                          index=d.sort_values('year')['year'].values)
        else:
            d = d.sort_values(['year', 'month'])
            idx = pd.PeriodIndex.from_fields(year=d['year'], month=d['month'], freq='M').to_timestamp()
            s = pd.Series(d['delta_lst'].values, index=idx)
        rows.append(_trend_stats(s, kind, 'delta_uc_bra', period))
    return pd.DataFrame(rows)


def load_cluster(cluster_id: int, stats_dir):
    """cluster_id like 13 -> panel inputs from the cached Cluster25_Composites/stats folder."""
    from pathlib import Path
    stats_dir = Path(stats_dir)
    clid = f"Cluster25_{cluster_id:02d}"
    g = lambda f: pd.read_csv(stats_dir / f)
    ann = g('Cluster25_LST_Annual.csv'); mon = g('Cluster25_LST_Monthly.csv')
    sa = g('Cluster25_SUHII_Annual.csv'); sm = g('Cluster25_SUHII_Monthly.csv')
    asx = g('Cluster25_Annual_Stats.csv'); msx = g('Cluster25_Monthly_Stats.csv')
    ss = g('Cluster25_SUHII_Stats.csv')
    f = lambda d: d[d['city'] == clid]
    suh_mon = f(sm)
    return dict(ann=f(ann), mon=f(mon), suh_ann=f(sa), suh_mon=suh_mon,
                ann_stats=f(asx), mon_stats=f(msx),
                suh_ann_stats=f(ss), suh_mon_stats=_delta_stats(suh_mon, 'monthly'))


def _city_stats(lst_df):
    """Extract embedded per-zone/period trend stats (constant per zone/period rows)."""
    return lst_df[['zone', 'period'] + _STAT_COLS].drop_duplicates(['zone', 'period']).reset_index(drop=True)


def load_city(slug: str, city_dir):
    from pathlib import Path
    city_dir = Path(city_dir)
    ann = pd.read_csv(city_dir / f'{slug}_annual_lst.csv')
    mon = pd.read_csv(city_dir / f'{slug}_monthly_lst.csv')
    suh_ann = _delta_from_lst(ann, ['year'])
    suh_mon = _delta_from_lst(mon, ['year', 'month'])
    return dict(ann=ann, mon=mon, suh_ann=suh_ann, suh_mon=suh_mon,
                ann_stats=_city_stats(ann), mon_stats=_city_stats(mon),
                suh_ann_stats=_delta_stats(suh_ann, 'annual'),
                suh_mon_stats=_delta_stats(suh_mon, 'monthly'))


def load_national(city_slug_dirs):
    """Pool all cities into an unweighted national composite (mean LST per zone/period)."""
    ann_all, mon_all = [], []
    for slug, cdir in city_slug_dirs:
        from pathlib import Path
        cdir = Path(cdir)
        ann_all.append(pd.read_csv(cdir / f'{slug}_annual_lst.csv')[
            ['zone', 'period', 'year', 'median_lst', 'p05_lst', 'p95_lst']])
        mon_all.append(pd.read_csv(cdir / f'{slug}_monthly_lst.csv')[
            ['zone', 'period', 'year', 'month', 'median_lst', 'p05_lst', 'p95_lst']])
    A = pd.concat(ann_all); M = pd.concat(mon_all)
    ann = A.groupby(['zone', 'period', 'year'], as_index=False).mean(numeric_only=True)
    mon = M.groupby(['zone', 'period', 'year', 'month'], as_index=False).mean(numeric_only=True)
    suh_ann = _delta_from_lst(ann, ['year'])
    suh_mon = _delta_from_lst(mon, ['year', 'month'])

    def zone_stats(lst_df, kind):
        rows = []
        for zone in ['urban_core', 'bra', 'city_region']:
            for period in ['day', 'night']:
                d = lst_df[(lst_df['zone'] == zone) & (lst_df['period'] == period)]
                if d.empty:
                    continue
                if kind == 'annual':
                    s = pd.Series(d.sort_values('year')['median_lst'].values,
                                  index=d.sort_values('year')['year'].values)
                else:
                    d = d.sort_values(['year', 'month'])
                    idx = pd.PeriodIndex.from_fields(year=d['year'], month=d['month'], freq='M').to_timestamp()
                    s = pd.Series(d['median_lst'].values, index=idx)
                rows.append(_trend_stats(s, kind, zone, period))
        return pd.DataFrame(rows)

    return dict(ann=ann, mon=mon, suh_ann=suh_ann, suh_mon=suh_mon,
                ann_stats=zone_stats(ann, 'annual'), mon_stats=zone_stats(mon, 'monthly'),
                suh_ann_stats=_delta_stats(suh_ann, 'annual'),
                suh_mon_stats=_delta_stats(suh_mon, 'monthly'))


def panel_inputs(entity, kind):
    """Pick (df, ddf, stats, dstats) for a given kind from a loader dict."""
    if kind == 'annual':
        return entity['ann'], entity['suh_ann'], entity['ann_stats'], entity['suh_ann_stats']
    return entity['mon'], entity['suh_mon'], entity['mon_stats'], entity['suh_mon_stats']
