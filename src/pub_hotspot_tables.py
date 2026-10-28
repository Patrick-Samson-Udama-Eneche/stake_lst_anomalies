"""
Publication-assembly table builders for manuscript §3.3–§3.4 (hot/cold-spot &
PLT-attribution results). Reshapes cached NB05/NB06 CSVs into the manuscript's
table layouts and writes both a plain ``.csv`` and a styled ``.xlsx`` for each.

Deliverables
------------
Table 5        cluster-level significant-spot occurrence (Day/Night × Hot/Cool)
Supp Table 6   per-city zone footprints  (n, L50, L75, L90, BH)
Supp Table 7   stakeholder buffer-sensitivity hit-rate (%) by buffer distance
Table 6        PLT–thermal-anomaly association (long: Occurrence / SUHII / Area)
Table 7        excerpt of best single-element attribution (composite vs element)
Supp Table 8   full single-element attribution (all 12 outcomes)

All numbers come straight from the cached result CSVs — nothing is recomputed.
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

# ── palette (mirrors the manuscript table styling) ──────────────────────────
_HDR_BG   = '#2f5496'   # dark-blue header band
_SUB_BG   = '#4472c4'   # lighter-blue sub-header
_GRP_BG   = '#e2efda'   # green cluster/group row
_HDR_FG   = '#ffffff'
_CITY_FG  = '#1f4e79'   # blue-ish body text for city values


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return np.nan


def _star(cell: str) -> str:
    s = str(cell)
    for m in ('***', '**', '*'):
        if m in s:
            return m
    return ''


# ═══════════════════════════════════════════════════════════════════════════
# Table 5 — cluster-level significant-spot occurrence
# ═══════════════════════════════════════════════════════════════════════════
_T5_GROUPS = [('day', 'hot', 'Day · Sig. Hotspots'),
              ('day', 'cold', 'Day · Sig. Cool spots'),
              ('night', 'hot', 'Night · Sig. Hotspots'),
              ('night', 'cold', 'Night · Sig. Cool spots')]
_T5_METRICS = ['No. of spots', 'No. of cities', 'Area (sq.km)']


def build_table5(results_05: Path) -> pd.DataFrame:
    ch = pd.read_csv(results_05 / 'cluster_hotspot_summary.csv')
    nat = pd.read_csv(results_05 / 'national_hotspot_summary.csv')

    def cell(df, cl, period, spot):
        r = df[(df['cluster25'] == cl) & (df['period'] == period) & (df['spot_type'] == spot)]
        if r.empty:
            return (0, 0, 0.0)
        r = r.iloc[0]
        return (int(r['n_spots']), int(r['n_cities']), round(float(r['total_area_50_km2']), 2))

    rows = []
    for cl in sorted(ch['cluster25'].unique()):
        d = {'Cluster': f'Cl-{cl}'}
        for period, spot, grp in _T5_GROUPS:
            ns, nc, ar = cell(ch, cl, period, spot)
            d[f'{grp}|No. of spots'] = ns
            d[f'{grp}|No. of cities'] = nc
            d[f'{grp}|Area (sq.km)'] = ar
        rows.append(d)
    dtot = {'Cluster': 'Total'}
    for period, spot, grp in _T5_GROUPS:
        r = nat[(nat['period'] == period) & (nat['spot_type'] == spot)].iloc[0]
        dtot[f'{grp}|No. of spots'] = int(r['n_spots'])
        dtot[f'{grp}|No. of cities'] = int(r['n_cities'])
        dtot[f'{grp}|Area (sq.km)'] = round(float(r['total_area_50_km2']), 2)
    rows.append(dtot)
    return pd.DataFrame(rows)


# ═══════════════════════════════════════════════════════════════════════════
# Supp Table 6 — per-city zone footprints
# ═══════════════════════════════════════════════════════════════════════════
_S6_COMBOS = [('hot', 'day', 'Hot · Day'), ('hot', 'night', 'Hot · Night'),
              ('cold', 'day', 'Cold · Day'), ('cold', 'night', 'Cold · Night')]
_S6_SUB = ['n', 'L50', 'L75', 'L90', 'BH']


def build_supp6(results_05: Path) -> pd.DataFrame:
    sc = pd.read_csv(results_05 / 'spot_comprehensive_summary.csv')

    def blank():
        return {s: '' for s in _S6_SUB}

    def one(r):
        n = int(r['T1']) if pd.notna(r['T1']) else 0
        l50, l75, l90 = _num(r['area_50_km2']), _num(r['area_75_km2']), _num(r['area_90_km2'])
        return {'n': (n or ''),
                'L50': round(l50, 2) if pd.notna(l50) and l50 else '',
                'L75': round(l75, 2) if pd.notna(l75) and l75 else '',
                'L90': round(l90, 2) if pd.notna(l90) and l90 else '',
                'BH': 'Yes' if _num(r['n_px_bh']) > 0 else ''}

    def row(entity, sub, is_group=False):
        d = {'Cluster/Entity': entity, '_group': is_group}
        for spot, period, grp in _S6_COMBOS:
            r = sub[(sub['Type'] == spot) & (sub['Period'] == period)]
            vals = blank() if r.empty else one(r.iloc[0])
            for s in _S6_SUB:
                d[f'{grp}|{s}'] = vals[s]
        return d

    def group_row(cl, csub, cities):
        d = {'Cluster/Entity': f'Cluster {cl} (n={len(cities)})', '_group': True}
        for spot, period, grp in _S6_COMBOS:
            r = csub[(csub['Type'] == spot) & (csub['Period'] == period)]
            nsum = int(r['T1'].fillna(0).sum())
            l50 = r['area_50_km2'].apply(_num).sum()
            l75 = r['area_75_km2'].apply(_num).sum()
            l90 = r['area_90_km2'].apply(_num).sum()
            bh = 'Yes' if (r['n_px_bh'].apply(_num) > 0).any() else ''
            d[f'{grp}|n'] = nsum or ''
            d[f'{grp}|L50'] = round(l50, 2) if l50 else ''
            d[f'{grp}|L75'] = round(l75, 2) if l75 else ''
            d[f'{grp}|L90'] = round(l90, 2) if l90 else ''
            d[f'{grp}|BH'] = bh
        return d

    rows = []
    for cl in sorted(sc['Cluster'].unique()):
        csub = sc[sc['Cluster'] == cl]
        cities = sorted(csub['City'].unique())
        rows.append(group_row(cl, csub, cities))
        for city in cities:
            rows.append(row(city, csub[csub['City'] == city]))
    return pd.DataFrame(rows)


# ═══════════════════════════════════════════════════════════════════════════
# Supp Table 7 — stakeholder buffer-sensitivity hit-rate (%)
# ═══════════════════════════════════════════════════════════════════════════
def _bkm(m):
    return f'{m/1000:g}km'


def build_supp7(results_05: Path):
    hs = pd.read_csv(results_05 / 'stakeholder_hitrate_sensitivity.csv')
    buffers = sorted(hs['buffer_m'].unique())

    def spot_rows(sub, entity, is_group=False):
        out = []
        for spot in ('hot', 'cold'):
            for period in ('day', 'night'):
                g = sub[(sub['spot_type'] == spot) & (sub['period'] == period)]
                if g.empty:
                    continue
                npts = int(g.groupby('buffer_m')['n_total'].first().iloc[0])
                d = {'Cluster/Entity': entity, '_group': is_group,
                     'Spot': spot.capitalize(), 'Period': period.capitalize(),
                     'No. of points': npts}
                for m in buffers:
                    gm = g[g['buffer_m'] == m]
                    d[_bkm(m)] = (round(100.0 * gm['n_hit'].sum() / max(gm['n_total'].sum(), 1), 1)
                                  if not gm.empty else '')
                out.append(d)
        return out

    rows = []
    for cl in sorted(hs['cluster25'].unique()):
        csub = hs[hs['cluster25'] == cl]
        rows += spot_rows(csub, f'C{cl}', is_group=True)
        for city in sorted(csub['matched_city_y'].unique()):
            rows += spot_rows(csub[csub['matched_city_y'] == city], city)
    return pd.DataFrame(rows), [_bkm(m) for m in buffers]


# ═══════════════════════════════════════════════════════════════════════════
# Table 6 — PLT–thermal-anomaly association (long format)
# ═══════════════════════════════════════════════════════════════════════════
def build_table6(results_06: Path) -> pd.DataFrame:
    pa = pd.read_csv(results_06 / 'partA_synthesis_cluster25.csv')

    def pstar(p, st):
        return f'{float(p):.3f}{st}'

    rows = []
    for _, r in pa.iterrows():
        rows.append({'Spot': r['Spot Type'], 'Period': r['Period'], 'Outcome': 'Occurrence',
                     'Test': 'MC χ²', 'Effect size': f"V = {float(r['V (occ)']):.3f}",
                     'p': pstar(r['p (occ)'], _star(r['χ² (occ)']))})
        rows.append({'Spot': '', 'Period': '', 'Outcome': 'SUHII', 'Test': 'KW',
                     'Effect size': f"η² = {float(r['η² (suhii)']):.3f}",
                     'p': pstar(r['p (suhii)'], _star(r['H (suhii)']))})
        rows.append({'Spot': '', 'Period': '', 'Outcome': 'Area (L50)', 'Test': 'KW',
                     'Effect size': f"η² = {float(r['η² (area)']):.3f}",
                     'p': pstar(r['p (area)'], _star(r['H (area)']))})
    return pd.DataFrame(rows)


# ═══════════════════════════════════════════════════════════════════════════
# Table 7 / Supp Table 8 — best single-element attribution (composite vs element)
# Source: master_synthesis.csv (the full "one major table"; matches the manuscript
# exactly, incl. the Occurrence rows absent from synthesis_S2_comparative_power).
# ═══════════════════════════════════════════════════════════════════════════
# manuscript Table-7 excerpt = these six notable outcomes
_T7_EXCERPT = [('Hot', 'Day', 'SUHII'), ('Hot', 'Night', 'Occurrence'),
               ('Hot', 'Night', 'SUHII'), ('Hot', 'Night', 'Area (L50)'),
               ('Cold', 'Day', 'SUHII'), ('Cold', 'Night', 'SUHII')]


def build_supp8_and_table7(results_06: Path):
    ms = pd.read_csv(results_06 / 'master_synthesis.csv')

    def eff(r, which):
        """Composite (A) or best-element (B) effect string: V= for occurrence, η² otherwise."""
        occ = str(r['Outcome']).strip().lower().startswith('occ')
        if which == 'A':
            return f"V = {float(r['A: V (Cramér)']):.3f}" if occ else f"η² = {float(r['A: η²']):.3f}"
        return f"V = {float(r['B: V (Cramér)']):.3f}" if occ else f"η² = {float(r['B: η²']):.3f}"

    def build(df):
        out = []
        for _, r in df.iterrows():
            out.append({
                'Spot': r['Spot Type'], 'Period': r['Period'], 'Outcome': r['Outcome'],
                'Composite PLT': eff(r, 'A'),
                'Best element': f"{r['B: Best element']} ({str(r['B: sig']).strip()})",
                'Best element effect': eff(r, 'B'),
                'Δ (PLT − element)': f"{float(r['Δ effect size']):+.3f}",
            })
        return pd.DataFrame(out)

    supp8 = build(ms)
    order = {k: i for i, k in enumerate(_T7_EXCERPT)}
    keys = ms.apply(lambda r: (r['Spot Type'], r['Period'], r['Outcome']), axis=1)
    exc = ms[keys.isin(order)].copy()
    exc = exc.assign(_o=keys[keys.isin(order)].map(order)).sort_values('_o').drop(columns='_o')
    table7 = build(exc)
    return supp8, table7, ms


# ═══════════════════════════════════════════════════════════════════════════
# XLSX writers (styled, manuscript-like)
# ═══════════════════════════════════════════════════════════════════════════
def _grouped_xlsx(df, path, id_cols, groups, subs, title, footnote='',
                  group_mask_col='_group', pct=False):
    """Two-row banded header (merged group over its sub-columns) + optional group shading."""
    import xlsxwriter
    show = df.drop(columns=[group_mask_col], errors='ignore')
    gmask = df[group_mask_col].tolist() if group_mask_col in df.columns else [False] * len(df)

    wb = xlsxwriter.Workbook(str(path), {'nan_inf_to_errors': True})
    ws = wb.add_worksheet('Sheet1')
    f_title = wb.add_format({'bold': True, 'italic': True, 'font_size': 11})
    f_grp = wb.add_format({'bold': True, 'bg_color': _HDR_BG, 'font_color': _HDR_FG,
                           'align': 'center', 'valign': 'vcenter', 'border': 1})
    f_sub = wb.add_format({'bold': True, 'bg_color': _SUB_BG, 'font_color': _HDR_FG,
                           'align': 'center', 'valign': 'vcenter', 'border': 1, 'font_size': 9})
    f_idh = wb.add_format({'bold': True, 'bg_color': _HDR_BG, 'font_color': _HDR_FG,
                           'align': 'left', 'valign': 'vcenter', 'border': 1})
    f_grow = wb.add_format({'bold': True, 'bg_color': _GRP_BG, 'border': 1})
    f_grow_c = wb.add_format({'bold': True, 'bg_color': _GRP_BG, 'border': 1, 'align': 'center'})
    f_id = wb.add_format({'border': 1})
    f_val = wb.add_format({'border': 1, 'align': 'center', 'font_color': _CITY_FG})
    f_foot = wb.add_format({'italic': True, 'font_size': 8, 'font_color': '#555555'})

    ncol = len(id_cols) + len(groups) * len(subs)
    ws.merge_range(0, 0, 0, ncol - 1, title, f_title)
    r0 = 2                                   # header rows at 2 (group) & 3 (sub)
    for i, c in enumerate(id_cols):
        ws.merge_range(r0, i, r0 + 1, i, c, f_idh)
    c = len(id_cols)
    for g in groups:
        ws.merge_range(r0, c, r0, c + len(subs) - 1, g, f_grp)
        for j, s in enumerate(subs):
            ws.write(r0 + 1, c + j, s, f_sub)
        c += len(subs)
    # body
    cols = list(show.columns)
    for ridx, (_, row) in enumerate(show.iterrows()):
        rr = r0 + 2 + ridx
        is_g = gmask[ridx]
        for cidx, col in enumerate(cols):
            v = row[col]
            if cidx < len(id_cols):
                ws.write(rr, cidx, v, f_grow if is_g else f_id)
            else:
                ws.write(rr, cidx, v, f_grow_c if is_g else f_val)
    ws.set_column(0, 0, 22)
    ws.set_column(1, ncol - 1, 7.5)
    if footnote:
        ws.write(r0 + 2 + len(show) + 1, 0, footnote, f_foot)
    ws.freeze_panes(r0 + 2, len(id_cols))
    wb.close()


def _simple_xlsx(df, path, title, footnote='', bold_sig_cols=None, caption_italic=True):
    """Plain academic table: bold header, optional bold-on-significance, footnote."""
    import xlsxwriter
    bold_sig_cols = bold_sig_cols or []
    wb = xlsxwriter.Workbook(str(path), {'nan_inf_to_errors': True})
    ws = wb.add_worksheet('Sheet1')
    f_title = wb.add_format({'bold': True, 'italic': caption_italic, 'font_size': 11})
    f_hdr = wb.add_format({'bold': True, 'bg_color': _HDR_BG, 'font_color': _HDR_FG,
                           'border': 1, 'align': 'center', 'valign': 'vcenter'})
    f_cell = wb.add_format({'border': 1})
    f_cell_c = wb.add_format({'border': 1, 'align': 'center'})
    f_bold = wb.add_format({'border': 1, 'align': 'center', 'bold': True})
    f_foot = wb.add_format({'italic': True, 'font_size': 8, 'font_color': '#555555'})
    cols = list(df.columns)
    ws.merge_range(0, 0, 0, len(cols) - 1, title, f_title)
    for j, c in enumerate(cols):
        ws.write(2, j, c, f_hdr)
    for i, (_, row) in enumerate(df.iterrows()):
        for j, c in enumerate(cols):
            v = row[c]
            sig = c in bold_sig_cols and isinstance(v, str) and ('*' in v)
            fmt = f_bold if sig else (f_cell_c if j > 0 else f_cell)
            ws.write(3 + i, j, v, fmt)
    for j, c in enumerate(cols):
        w = max(10, min(30, int(df[c].astype(str).map(len).max() if len(df) else 10) + 3))
        ws.set_column(j, j, w)
    if footnote:
        ws.write(3 + len(df) + 1, 0, footnote, f_foot)
    wb.close()


# ═══════════════════════════════════════════════════════════════════════════
# top-level driver
# ═══════════════════════════════════════════════════════════════════════════
def build_hotspot_tables(results_05: Path, results_06: Path, out_dir: Path) -> dict:
    """Build every §3.3–§3.4 table; write .csv + styled .xlsx; return the DataFrames."""
    results_05, results_06, out_dir = Path(results_05), Path(results_06), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    made = {}

    # ── Table 5 ──
    t5 = build_table5(results_05)
    t5.columns = [c.split('|')[-1] if '|' in c else c for c in t5.columns]  # flat for csv
    t5.to_csv(out_dir / 'Table_5_cluster_spot_occurrence.csv', index=False)
    t5g = build_table5(results_05)
    t5g['_group'] = t5g['Cluster'].eq('Total')
    _grouped_xlsx(t5g, out_dir / 'Table_5_cluster_spot_occurrence.xlsx',
                  id_cols=['Cluster'], groups=[g for _, _, g in _T5_GROUPS], subs=_T5_METRICS,
                  title='Table 5: Summary of significant spots occurrence across PLT clusters (56 cities)',
                  footnote='Area = total L50 footprint (sq.km). Total row = national aggregate.')
    made['Table_5'] = t5

    # ── Supp Table 6 ──
    s6 = build_supp6(results_05)
    s6.drop(columns=['_group']).to_csv(out_dir / 'Supp_Table_6_city_zone_footprints.csv', index=False)
    _grouped_xlsx(s6, out_dir / 'Supp_Table_6_city_zone_footprints.xlsx',
                  id_cols=['Cluster/Entity'], groups=[g for _, _, g in _S6_COMBOS], subs=_S6_SUB,
                  title='Supplementary Table 6: City-level significant-spot zone footprints (L50/L75/L90, km²)',
                  footnote='n = significant spots; L50/L75/L90 = zone areas (km²); BH = survives BH-FDR. '
                           'Green rows = cluster aggregates.')
    made['Supp_Table_6'] = s6

    # ── Supp Table 7 ──
    s7, bufcols = build_supp7(results_05)
    s7.drop(columns=['_group']).to_csv(out_dir / 'Supp_Table_7_buffer_sensitivity.csv', index=False)
    _grouped_xlsx(s7, out_dir / 'Supp_Table_7_buffer_sensitivity.xlsx',
                  id_cols=['Cluster/Entity', 'Spot', 'Period', 'No. of points'],
                  groups=['Hit-rate Buffer Sensitivity (%)'], subs=bufcols,
                  title='Supplementary Table 7: Stakeholder–satellite spot corroboration — buffer sensitivity',
                  footnote='Values = hit-rate (%) at each buffer radius. Green rows = cluster aggregates.')
    made['Supp_Table_7'] = s7

    # ── Table 6 ──
    t6 = build_table6(results_06)
    t6.to_csv(out_dir / 'Table_6_plt_thermal_association.csv', index=False)
    _simple_xlsx(t6, out_dir / 'Table_6_plt_thermal_association.xlsx',
                 title='Table 6: PLT — Thermal anomaly association result',
                 footnote='* p < 0.05; ** p < 0.01. V: large ≥ 0.50; η²: large ≥ 0.14. '
                          'MC χ² = Monte-Carlo permutation χ²; KW = Kruskal–Wallis.',
                 bold_sig_cols=['p'])
    made['Table_6'] = t6

    # ── Table 7 + Supp Table 8 ──
    supp8, table7, _ = build_supp8_and_table7(results_06)
    table7.to_csv(out_dir / 'Table_7_best_element_attribution_excerpt.csv', index=False)
    supp8.to_csv(out_dir / 'Supp_Table_8_best_element_attribution_full.csv', index=False)
    _simple_xlsx(table7, out_dir / 'Table_7_best_element_attribution_excerpt.xlsx',
                 title='Table 7: Excerpt — best PLT single-element attribution to thermal anomalies',
                 footnote='Composite PLT vs best contributing element. (***/**/* /ns) = element significance. '
                          'Δ = composite − element effect size (η² for SUHII/Area; V for Occurrence).')
    _simple_xlsx(supp8, out_dir / 'Supp_Table_8_best_element_attribution_full.xlsx',
                 title='Supplementary Table 8: Full best PLT single-element attribution (all outcomes)',
                 footnote='Composite PLT vs best contributing element across all 12 outcomes. '
                          'Δ = composite − element effect size.')
    made['Table_7'] = table7
    made['Supp_Table_8'] = supp8
    return made
