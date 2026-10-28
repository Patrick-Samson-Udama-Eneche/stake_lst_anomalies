"""
Daily LST Analysis Utilities — Notebook 04
============================================

Implements the EXCELLENT / GOOD / FAIR persistent heat-event detection and
selection protocol for the daily temporal analysis of MODIS and ERA5-Land
Urban-Core LST data.

Public API
----------
detect_hot_days(series, percentile=90)
find_persistent_events(hot_series, dates, min_consecutive=2)
assign_tier(era5_event, modis_persistent_events, modis_hot_dates)
select_seviri_event(era5_events_with_tiers)
build_event_json(era5_events, selected_event, city, period)
compute_correlation_metrics(modis_series, era5_series)
build_cluster_daily_series(city_records, cluster_lookup)
aggregate_cluster_events(city_event_records, cluster_lookup)
load_daily_csv(path, period)
compute_suhii_from_seviri(uc_series, bra_series)
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Constants — kept in sync with config.DAILY_LST_CONFIG
# ---------------------------------------------------------------------------
_DEFAULT_PERCENTILE   = 90
_DEFAULT_PERSISTENT   = 2          # minimum consecutive hot days / nights
_TIER_EXCELLENT       = 'EXCELLENT'
_TIER_GOOD            = 'GOOD'
_TIER_FAIR            = 'FAIR'

# Column name helpers  (MODIS daily CSVs produced by gee_utils.extract_modis_daily_lst)
_MODIS_DAY_COL   = 'day_lst_median'
_MODIS_NIGHT_COL = 'night_lst_median'
_ERA5_DAY_COL    = 'day_lst_median'    # ERA5 CSVs use same column names
_ERA5_NIGHT_COL  = 'night_lst_median'
_DATE_COL        = 'date'


# =============================================================================
# §1 — Hot-day detection (within-year P90, day and night independently)
# =============================================================================

def detect_hot_days(
    series: pd.Series,
    percentile: int = _DEFAULT_PERCENTILE,
) -> Tuple[pd.Series, float]:
    """
    Identify hot days/nights using the within-year P-*percentile* threshold.

    The threshold is computed from the *valid* (non-NaN) values of *series*
    for the single year being analysed.  Days with NaN LST are flagged as
    ``False`` (not hot) regardless of the threshold.

    Parameters
    ----------
    series : pd.Series
        Numeric LST values for one period (day or night) across a single year.
        Index may be anything; NaN values are allowed and treated as missing.
    percentile : int
        Percentile for the hot-day threshold (default 90 → P90).

    Returns
    -------
    hot_mask : pd.Series[bool]
        Boolean mask aligned with *series*.  True = hot day/night.
    threshold : float
        Computed threshold value (°C).
    """
    valid = series.dropna()
    if valid.empty:
        return pd.Series(False, index=series.index), float('nan')

    threshold = float(np.percentile(valid, percentile))
    hot_mask  = series >= threshold          # NaN comparisons → False
    return hot_mask.fillna(False), threshold


# =============================================================================
# §2 — Persistent event detection (run-length encoding)
# =============================================================================

def find_persistent_events(
    hot_mask: pd.Series,
    dates: pd.Series,
    min_consecutive: int = _DEFAULT_PERSISTENT,
) -> List[Dict]:
    """
    Identify runs of consecutive hot days / nights meeting the persistence
    threshold.

    Parameters
    ----------
    hot_mask : pd.Series[bool]
        Boolean series output from :func:`detect_hot_days`.  Must be
        chronologically ordered and have the same index as *dates*.
    dates : pd.Series
        Corresponding date values (datetime or string).  Same index as
        *hot_mask*.
    min_consecutive : int
        Minimum run length to count as a persistent event (default 2).

    Returns
    -------
    list of dict
        Each dict has keys:
        ``start_date``, ``end_date``, ``duration`` (int, days),
        ``date_list`` (list of date strings in 'YYYY-MM-DD' format).
    """
    events: List[Dict] = []
    mask   = hot_mask.values
    dvals  = pd.to_datetime(dates.values)

    i = 0
    n = len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j < n and mask[j]:
                j += 1
            run_len = j - i
            if run_len >= min_consecutive:
                run_dates = dvals[i:j]
                events.append({
                    'start_date': run_dates[0].strftime('%Y-%m-%d'),
                    'end_date':   run_dates[-1].strftime('%Y-%m-%d'),
                    'duration':   run_len,
                    'date_list':  [d.strftime('%Y-%m-%d') for d in run_dates],
                })
            i = j
        else:
            i += 1

    # Sort longest → shortest for the iteration protocol in §3
    events.sort(key=lambda e: e['duration'], reverse=True)
    return events


# =============================================================================
# §3 — EXCELLENT / GOOD / FAIR tier assignment
# =============================================================================

def _dates_overlap(dates_a: List[str], dates_b: List[str]) -> bool:
    """Return True if any date in *dates_a* appears in *dates_b*."""
    return bool(set(dates_a) & set(dates_b))


def assign_tier(
    era5_event: Dict,
    modis_persistent_events: List[Dict],
    modis_hot_dates: List[str],
) -> str:
    """
    Assign an EXCELLENT / GOOD / FAIR tier to an ERA5 persistent event.

    Protocol
    --------
    EXCELLENT : the ERA5 event's date window overlaps with at least one MODIS
                *persistent* event (≥ ``PERSISTENT_THRESHOLD`` consecutive hot
                days).
    GOOD      : the ERA5 event's date window contains at least one single MODIS
                hot day (above P90) but no MODIS persistent overlap.
    FAIR      : no MODIS overlap at all.

    Parameters
    ----------
    era5_event : dict
        Single ERA5 persistent event dict from :func:`find_persistent_events`.
    modis_persistent_events : list of dict
        All MODIS persistent events from :func:`find_persistent_events` for the
        same period (day or night).
    modis_hot_dates : list of str
        All individual MODIS hot dates for the same period (any single day
        above P90), as 'YYYY-MM-DD' strings.

    Returns
    -------
    str
        'EXCELLENT', 'GOOD', or 'FAIR'.
    """
    era5_dates = era5_event['date_list']

    # Check EXCELLENT — overlap with a MODIS persistent event
    for m_evt in modis_persistent_events:
        if _dates_overlap(era5_dates, m_evt['date_list']):
            return _TIER_EXCELLENT

    # Check GOOD — overlap with any MODIS single hot day
    if _dates_overlap(era5_dates, modis_hot_dates):
        return _TIER_GOOD

    return _TIER_FAIR


# =============================================================================
# §4 — Event selection (best tier → longest duration → earliest start)
# =============================================================================

_TIER_ORDER = {_TIER_EXCELLENT: 0, _TIER_GOOD: 1, _TIER_FAIR: 2}


def select_seviri_event(
    era5_events_with_tiers: List[Dict],
) -> Tuple[Optional[Dict], str]:
    """
    Select the single best ERA5 event for SEVIRI download.

    Selection order
    ---------------
    1. Best tier (EXCELLENT > GOOD > FAIR)
    2. Longest duration within the tier
    3. Earliest start date within ties

    Parameters
    ----------
    era5_events_with_tiers : list of dict
        ERA5 persistent events, each augmented with a ``'tier'`` key
        (output of :func:`assign_tier`).

    Returns
    -------
    selected : dict or None
        The winning event dict, or ``None`` if the list is empty.
    reason : str
        Human-readable explanation of the selection.
    """
    if not era5_events_with_tiers:
        return None, 'No ERA5 persistent events detected.'

    # Sort: tier asc (EXCELLENT=0 wins), then duration desc, then start asc
    ranked = sorted(
        era5_events_with_tiers,
        key=lambda e: (
            _TIER_ORDER.get(e.get('tier', _TIER_FAIR), 2),
            -e['duration'],
            e['start_date'],
        ),
    )
    selected = ranked[0]
    tier     = selected.get('tier', _TIER_FAIR)
    dur      = selected['duration']
    start    = selected['start_date']
    end      = selected['end_date']

    # Count how many events share the winning tier
    same_tier = [e for e in ranked if e.get('tier') == tier]
    if len(same_tier) == 1:
        reason = (
            f"Selected sole {tier} event "
            f"({start} – {end}, {dur} day{'s' if dur != 1 else ''})."
        )
    else:
        reason = (
            f"Selected longest {tier} event among {len(same_tier)} "
            f"({start} – {end}, {dur} day{'s' if dur != 1 else ''})."
        )

    return selected, reason


# =============================================================================
# §5 — JSON audit trail
# =============================================================================

def build_event_json(
    era5_events: List[Dict],
    selected_event: Optional[Dict],
    city: str,
    period: str,
    modis_persistent_events: Optional[List[Dict]] = None,
    modis_hot_dates: Optional[List[str]] = None,
    selection_reason: str = '',
    era5_threshold: float = float('nan'),
    modis_threshold: float = float('nan'),
) -> Dict:
    """
    Build a JSON-serialisable audit record for one city × period.

    Parameters
    ----------
    era5_events : list of dict
        All ERA5 persistent events (with 'tier' key added).
    selected_event : dict or None
        The event chosen for SEVIRI download.
    city : str
        City name.
    period : str
        'day' or 'night'.
    modis_persistent_events : list of dict, optional
        All MODIS persistent events for reference.
    modis_hot_dates : list of str, optional
        All individual MODIS hot dates.
    selection_reason : str
        Output of :func:`select_seviri_event`.
    era5_threshold : float
        P90 threshold used for ERA5 hot-day detection (°C).
    modis_threshold : float
        P90 threshold used for MODIS hot-day detection (°C).

    Returns
    -------
    dict
        Audit dict ready for ``json.dump``.
    """
    return {
        'city':   city,
        'period': period,
        'thresholds': {
            'era5_p90_celsius':   round(era5_threshold,  2) if np.isfinite(era5_threshold)  else None,
            'modis_p90_celsius':  round(modis_threshold, 2) if np.isfinite(modis_threshold) else None,
        },
        'era5_persistent_events': [
            {
                'start_date': e['start_date'],
                'end_date':   e['end_date'],
                'duration':   e['duration'],
                'tier':       e.get('tier', _TIER_FAIR),
            }
            for e in era5_events
        ],
        'modis_persistent_events': [
            {
                'start_date': e['start_date'],
                'end_date':   e['end_date'],
                'duration':   e['duration'],
            }
            for e in (modis_persistent_events or [])
        ],
        'n_modis_hot_dates': len(modis_hot_dates or []),
        'selected_event': {
            'start_date':      selected_event['start_date'],
            'end_date':        selected_event['end_date'],
            'duration':        selected_event['duration'],
            'tier':            selected_event.get('tier', _TIER_FAIR),
            'selection_reason': selection_reason,
        } if selected_event else None,
    }


# =============================================================================
# §6 — ERA5 vs MODIS correlation metrics (full-year, MODIS-valid days only)
# =============================================================================

def compute_correlation_metrics(
    modis_series: pd.Series,
    era5_series: pd.Series,
) -> Dict:
    """
    Compute pairwise comparison metrics between MODIS and ERA5 LST for the
    days on which MODIS has a valid (non-NaN) observation.

    Metrics returned
    ----------------
    n       : int   — number of valid paired observations
    r       : float — Pearson correlation coefficient
    r2      : float — coefficient of determination
    bias    : float — mean(ERA5 − MODIS)  [positive → ERA5 warmer]
    rmse    : float — root mean squared error
    mae     : float — mean absolute error

    Parameters
    ----------
    modis_series, era5_series : pd.Series
        Numeric daily LST series with a shared datetime-compatible index.
        Only days where MODIS is non-NaN are used.

    Returns
    -------
    dict
        Keys: 'n', 'r', 'r2', 'bias', 'rmse', 'mae'.
        All float/int values; NaN if insufficient data (n < 2).
    """
    df = pd.DataFrame({'modis': modis_series, 'era5': era5_series}).dropna(subset=['modis'])
    df = df.dropna()            # drop rows where ERA5 is also missing

    n = len(df)
    nan_result = {'n': n, 'r': float('nan'), 'r2': float('nan'),
                  'bias': float('nan'), 'rmse': float('nan'), 'mae': float('nan')}

    if n < 2:
        return nan_result

    diff  = df['era5'] - df['modis']
    bias  = float(diff.mean())
    rmse  = float(np.sqrt((diff ** 2).mean()))
    mae   = float(diff.abs().mean())

    corr  = df[['modis', 'era5']].corr().iloc[0, 1]
    r     = float(corr)
    r2    = float(corr ** 2)

    return {'n': n, 'r': round(r, 4), 'r2': round(r2, 4),
            'bias': round(bias, 3), 'rmse': round(rmse, 3), 'mae': round(mae, 3)}


# =============================================================================
# §7 — SUHII from SEVIRI zone extracts
# =============================================================================

def compute_suhii_from_seviri(
    uc_series: pd.Series,
    bra_series: pd.Series,
) -> pd.Series:
    """
    Compute SEVIRI-based Surface Urban Heat Island Intensity (SUHII).

    SUHII = UC_LST − BRA_LST

    Parameters
    ----------
    uc_series, bra_series : pd.Series
        Daily (or sub-daily) median LST for Urban Core and Background
        Rural Area respectively.  Must share a compatible index.

    Returns
    -------
    pd.Series
        SUHII values in °C.  NaN where either zone is missing.
    """
    return uc_series - bra_series


# =============================================================================
# §8 — Cluster-level daily series builder
# =============================================================================

def build_cluster_daily_series(
    city_records: Dict[str, pd.DataFrame],
    cluster_lookup: Dict[str, int],
) -> Dict[int, pd.DataFrame]:
    """
    Aggregate city-level daily LST DataFrames into cluster-level composite
    DataFrames by taking the mean across available cities within each cluster.

    Parameters
    ----------
    city_records : dict
        ``{city_name: dataframe}`` where each DataFrame has a ``'date'`` column
        and numeric LST columns (e.g. ``day_lst_median``, ``night_lst_median``).
    cluster_lookup : dict
        ``{city_name: cluster_int}`` mapping from the Cluster25 lookup table.

    Returns
    -------
    dict
        ``{cluster_int: dataframe}`` with the same columns as the input
        DataFrames plus ``'n_cities'`` (number of valid cities on each date).
    """
    # Group city names by cluster
    cluster_cities: Dict[int, List[str]] = {}
    for city, cnum in cluster_lookup.items():
        if city in city_records:
            cluster_cities.setdefault(int(cnum), []).append(city)

    result: Dict[int, pd.DataFrame] = {}

    for cnum, cities in cluster_cities.items():
        frames = [city_records[c].set_index('date') for c in cities if 'date' in city_records[c].columns]
        if not frames:
            continue

        combined = pd.concat(frames, axis=0, keys=cities)
        # mean across cities for each date, ignoring NaN
        agg = combined.groupby(level=1).mean(numeric_only=True)
        # count of non-NaN cities per date (use the first numeric column as proxy)
        first_col = [c for c in agg.columns if c != 'date'][0] if agg.shape[1] else None
        if first_col:
            counts = combined[first_col].groupby(level=1).count()
            agg['n_cities'] = counts

        agg = agg.reset_index().rename(columns={'date': 'date'})
        result[cnum] = agg

    return result


# =============================================================================
# §9 — Cluster-level event aggregation
# =============================================================================

def aggregate_cluster_events(
    city_event_records: Dict[str, Dict],
    cluster_lookup: Dict[str, int],
) -> pd.DataFrame:
    """
    Aggregate city-level event statistics into cluster-level summary rows.

    For each cluster the function collects:
    - cities in the cluster with valid selected events
    - modal (most common) tier among selected events
    - median duration of selected events
    - date range of selected event window across all cities

    Parameters
    ----------
    city_event_records : dict
        ``{city_name: audit_dict}`` where each audit dict was produced by
        :func:`build_event_json`.  Both 'day' and 'night' can be nested
        under the city key (the caller decides the structure).
    cluster_lookup : dict
        ``{city_name: cluster_int}``.

    Returns
    -------
    pd.DataFrame
        One row per cluster, columns:
        ``cluster_num``, ``n_cities_total``, ``n_cities_with_event``,
        ``modal_tier``, ``median_duration_days``,
        ``earliest_event_start``, ``latest_event_end``.
    """
    rows = []

    # Group cities by cluster
    cluster_cities: Dict[int, List[str]] = {}
    for city, cnum in cluster_lookup.items():
        cluster_cities.setdefault(int(cnum), []).append(city)

    for cnum in sorted(cluster_cities):
        cities = cluster_cities[cnum]
        n_total = len(cities)

        tiers, durations, starts, ends = [], [], [], []
        for city in cities:
            rec = city_event_records.get(city)
            if rec is None:
                continue
            sel = rec.get('selected_event')
            if sel is None:
                continue
            tiers.append(sel.get('tier', _TIER_FAIR))
            durations.append(sel.get('duration', 0))
            starts.append(sel.get('start_date', ''))
            ends.append(sel.get('end_date', ''))

        n_with = len(tiers)
        # Modal tier (best if tied → EXCELLENT > GOOD > FAIR)
        if tiers:
            from collections import Counter
            tier_counts = Counter(tiers)
            modal_tier = min(
                tier_counts.keys(),
                key=lambda t: (_TIER_ORDER.get(t, 2), -tier_counts[t]),
            )
        else:
            modal_tier = None

        rows.append({
            'cluster_num':             cnum,
            'n_cities_total':          n_total,
            'n_cities_with_event':     n_with,
            'modal_tier':              modal_tier,
            'median_duration_days':    round(float(np.median(durations)), 1) if durations else None,
            'earliest_event_start':    min(starts) if starts else None,
            'latest_event_end':        max(ends)   if ends   else None,
        })

    return pd.DataFrame(rows)


# =============================================================================
# §10 — CSV loader (MODIS and ERA5 daily outputs from gee_utils)
# =============================================================================

def load_daily_csv(path: str | Path, period: str) -> Optional[pd.DataFrame]:
    """
    Load a MODIS or ERA5 daily LST CSV and return a tidy DataFrame.

    Parameters
    ----------
    path : str or Path
        Full path to the CSV file.
    period : str
        'day' or 'night' — selects the appropriate median column.

    Returns
    -------
    pd.DataFrame or None
        Columns: ``date`` (datetime64), ``lst_median`` (float), plus whatever
        other columns are present in the file.  Returns None if the file does
        not exist or is empty.
    """
    path = Path(path)
    if not path.exists():
        warnings.warn(f"daily_csv: file not found — {path}")
        return None

    try:
        df = pd.read_csv(path)
    except Exception as exc:
        warnings.warn(f"daily_csv: could not read {path} — {exc}")
        return None

    if df.empty:
        return None

    # Parse date column
    if 'date' not in df.columns:
        warnings.warn(f"daily_csv: no 'date' column in {path}")
        return None

    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.dropna(subset=['date']).sort_values('date').reset_index(drop=True)

    # Resolve LST median column
    col_map = {'day': _MODIS_DAY_COL, 'night': _MODIS_NIGHT_COL}
    lst_col  = col_map.get(period)
    if lst_col and lst_col in df.columns:
        df['lst_median'] = pd.to_numeric(df[lst_col], errors='coerce')
    elif 'lst_median' not in df.columns:
        warnings.warn(
            f"daily_csv: expected column '{lst_col}' not found in {path}. "
            "Available columns: " + ', '.join(df.columns)
        )
        df['lst_median'] = float('nan')

    return df


# =============================================================================
# §11 — Hot-date list builder (helper for audit trails)
# =============================================================================

def get_hot_dates(
    df: pd.DataFrame,
    period: str,
    percentile: int = _DEFAULT_PERCENTILE,
    lst_col: str = 'lst_median',
) -> Tuple[List[str], float]:
    """
    Return the list of all hot-day dates and the P-*percentile* threshold.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with a ``'date'`` column and an LST column.
    period : str
        'day' or 'night' — used only for messages.
    percentile : int
        Threshold percentile (default 90).
    lst_col : str
        Name of the LST column to threshold (default 'lst_median').

    Returns
    -------
    hot_dates : list of str
        Dates (ISO format) on which LST ≥ threshold.
    threshold : float
        Computed P90 value.
    """
    hot_mask, threshold = detect_hot_days(df[lst_col], percentile)
    hot_dates = df.loc[hot_mask, 'date'].dt.strftime('%Y-%m-%d').tolist()
    return hot_dates, threshold


# =============================================================================
# §12 — Full per-city pipeline (convenience wrapper for NB04 cells)
# =============================================================================

def run_city_event_pipeline(
    modis_df: Optional[pd.DataFrame],
    era5_df: Optional[pd.DataFrame],
    city: str,
    period: str,
    percentile: int = _DEFAULT_PERCENTILE,
    min_consecutive: int = _DEFAULT_PERSISTENT,
    lst_col: str = 'lst_median',
) -> Dict:
    """
    Run the full EXCELLENT / GOOD / FAIR event detection pipeline for one city
    and one period (day or night).

    Steps
    -----
    1. Detect MODIS hot days → persistent events + hot-date list.
    2. Detect ERA5 hot days  → persistent events, iterate longest → shortest.
    3. Assign tier to every ERA5 persistent event.
    4. Select the single best event for SEVIRI download.
    5. Build and return the JSON audit record.

    Parameters
    ----------
    modis_df, era5_df : pd.DataFrame or None
        Output of :func:`load_daily_csv` for the given period.
    city : str
        City name.
    period : str
        'day' or 'night'.
    percentile : int
        Hot-day detection percentile (default 90).
    min_consecutive : int
        Minimum run length for persistence (default 2).
    lst_col : str
        LST column name in the DataFrames.

    Returns
    -------
    dict
        JSON audit dict from :func:`build_event_json`, also containing
        convenience keys:
        ``'selected_event'``, ``'era5_persistent_events'``,
        ``'modis_persistent_events'``, ``'correlation_metrics'``.
    """
    # ── MODIS ────────────────────────────────────────────────────────────────
    modis_persistent: List[Dict] = []
    modis_hot_dates:  List[str]  = []
    modis_threshold:  float      = float('nan')

    if modis_df is not None and lst_col in modis_df.columns:
        hot_mask_m, modis_threshold = detect_hot_days(modis_df[lst_col], percentile)
        modis_hot_dates   = modis_df.loc[hot_mask_m, 'date'].dt.strftime('%Y-%m-%d').tolist()
        modis_persistent  = find_persistent_events(hot_mask_m, modis_df['date'], min_consecutive)

    # ── ERA5 ─────────────────────────────────────────────────────────────────
    era5_persistent:  List[Dict] = []
    era5_threshold:   float      = float('nan')

    if era5_df is not None and lst_col in era5_df.columns:
        hot_mask_e, era5_threshold = detect_hot_days(era5_df[lst_col], percentile)
        raw_events = find_persistent_events(hot_mask_e, era5_df['date'], min_consecutive)

        # Assign tiers (longest → shortest order preserved by find_persistent_events)
        for evt in raw_events:
            evt['tier'] = assign_tier(evt, modis_persistent, modis_hot_dates)
        era5_persistent = raw_events

    # ── Select event ─────────────────────────────────────────────────────────
    selected, reason = select_seviri_event(era5_persistent)

    # ── Correlation (full-year, MODIS-valid days only) ────────────────────────
    corr_metrics: Dict = {}
    if modis_df is not None and era5_df is not None:
        merged = pd.merge(
            modis_df[['date', lst_col]].rename(columns={lst_col: 'modis'}),
            era5_df[['date', lst_col]].rename(columns={lst_col: 'era5'}),
            on='date', how='inner',
        )
        corr_metrics = compute_correlation_metrics(merged['modis'], merged['era5'])

    # ── Audit JSON ────────────────────────────────────────────────────────────
    audit = build_event_json(
        era5_events             = era5_persistent,
        selected_event          = selected,
        city                    = city,
        period                  = period,
        modis_persistent_events = modis_persistent,
        modis_hot_dates         = modis_hot_dates,
        selection_reason        = reason,
        era5_threshold          = era5_threshold,
        modis_threshold         = modis_threshold,
    )
    audit['correlation_metrics'] = corr_metrics

    return audit


# =============================================================================
# §13 — Utility: print concise event summary to stdout
# =============================================================================

def print_event_summary(audit: Dict) -> None:
    """
    Print a one-paragraph summary of the selected event for a city × period.

    Parameters
    ----------
    audit : dict
        Output of :func:`run_city_event_pipeline` or :func:`build_event_json`.
    """
    city   = audit.get('city', '?')
    period = audit.get('period', '?')
    sel    = audit.get('selected_event')
    era5_n = len(audit.get('era5_persistent_events', []))
    mod_n  = len(audit.get('modis_persistent_events', []))

    header = f"  {city} [{period}]"
    print(header)
    thr = audit.get('thresholds', {})
    e_thr = thr.get('era5_p90_celsius')
    m_thr = thr.get('modis_p90_celsius')
    print(f"    ERA5 P90={e_thr}°C  MODIS P90={m_thr}°C")
    print(f"    ERA5 persistent events: {era5_n}   MODIS persistent events: {mod_n}")

    if sel:
        print(
            f"    Selected [{sel['tier']}]: "
            f"{sel['start_date']} – {sel['end_date']} "
            f"({sel['duration']} day{'s' if sel['duration'] != 1 else ''})"
        )
        print(f"    Reason: {sel.get('selection_reason', '')}")
    else:
        print("    No ERA5 persistent event found — SEVIRI download skipped.")

    corr = audit.get('correlation_metrics', {})
    if corr:
        print(
            f"    Full-year ERA5 vs MODIS: "
            f"r={corr.get('r', 'N/A')}, bias={corr.get('bias', 'N/A')}°C, "
            f"RMSE={corr.get('rmse', 'N/A')}°C, n={corr.get('n', 'N/A')}"
        )
    print()
