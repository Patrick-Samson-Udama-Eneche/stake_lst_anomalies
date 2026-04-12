"""
Modelling Utilities for Hotspot Analysis (Notebook 06)
======================================================

Reusable functions for:
- Building city-level binary datasets for Gi* occurrence analysis
- Hierarchical binomial GLMs with logit link for occurrence analysis
- Hierarchical logistic regression with variance partitioning (legacy)
- Hierarchical OLS with city-clustered standard errors (Analyses 2–3)
- Wild Cluster Bootstrap p-values (Cameron, Gelbach & Miller, 2008)
- Coefficient tables and visualisation helpers (panel Day|Night charts)

Author: LST Modelling Project
Date: 2026
"""

import json
from pathlib import Path
from typing import List, Dict, Tuple, Optional

import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt

import statsmodels.api as sm
from statsmodels.discrete.discrete_model import Logit
from scipy import stats as scipy_stats

from src.data_io import export_figure_set


def _export_figure_all_formats(fig: plt.Figure, output_path: Path, dpi: int = 300) -> None:
    """Export a figure through the centralized data_io exporter."""
    output_path = Path(output_path)
    export_figure_set(
        fig,
        output_path,
        dpi=dpi,
        include_svg=True,
        include_pdf=True,
        bbox_inches='tight',
    )


# =========================================================================
# SHARED COLOUR PALETTES  (one per hierarchy block; used by donut & Sankey)
# =========================================================================
BLOCK_PALETTES: List[List[str]] = [
    ['#4e79a7', '#59a14f', '#f28e2b', '#e15759', '#76b7b2', '#edc949'],   # Climate
    ['#af7aa1', '#ff9da7', '#9c755f', '#bab0ab', '#d4a6c8', '#c9d4e0'],   # Geology
    ['#86bcb6', '#f1ce63', '#a0cbe8', '#d37295', '#b07aa1', '#8cd17d'],   # Elevation
    ['#499894', '#e49444', '#b6992d', '#d4a6c8', '#f1ce63', '#86bcb6', '#a0cbe8', '#d37295'],  # Landcover
]


def _category_color_map(
    series: pd.Series,
    palette: List[str],
) -> Dict[str, str]:
    """Return {category_label: hex_colour} keyed by **alphabetical** order.

    Both the donut and Sankey call this so the same category always
    receives the same colour regardless of how nodes are sorted.
    """
    cats_alpha = sorted(series.dropna().unique())
    return {cat: palette[i % len(palette)] for i, cat in enumerate(cats_alpha)}


# =========================================================================
# DATASET CONSTRUCTION
# =========================================================================

def load_aoi_boundaries(aoi_base_dir: Path, cities: List[str]) -> gpd.GeoDataFrame:
    """
    Load AOI boundary GeoJSONs for all cities and combine into one GeoDataFrame.

    Parameters
    ----------
    aoi_base_dir : Path
        Path to ``data/outputs/01_aoi_delineation/``.
    cities : list[str]
        City names to load.

    Returns
    -------
    gpd.GeoDataFrame
        One row per city with columns ``city``, ``aoi_area_km2``, ``geometry``.
    """
    records = []
    for city in cities:
        aoi_file = aoi_base_dir / f"City_{city}" / "Features" / f"{city}_AOI_Boundary.geojson"
        if not aoi_file.exists():
            print(f"  ⚠ AOI not found for {city}: {aoi_file}")
            continue
        gdf = gpd.read_file(aoi_file)
        area_col = 'aoi_area_km2' if 'aoi_area_km2' in gdf.columns else None
        records.append({
            'city': city,
            'aoi_area_km2': float(gdf[area_col].iloc[0]) if area_col else None,
            'geometry': gdf.geometry.iloc[0],
        })
    result = gpd.GeoDataFrame(records, crs="EPSG:4326")
    print(f"✓ Loaded {len(result)} / {len(cities)} AOI boundaries")
    return result


def extract_dominant_landscape(
    aoi_gdf: gpd.GeoDataFrame,
    landscape_gdf: gpd.GeoDataFrame,
    class_columns: List[str],
) -> pd.DataFrame:
    """
    For each AOI, find the dominant (mode) landscape class by overlay area.

    Parameters
    ----------
    aoi_gdf : gpd.GeoDataFrame
        City AOI polygons (must have ``city`` column).
    landscape_gdf : gpd.GeoDataFrame
        Landscape character polygons with class attribute columns.
    class_columns : list[str]
        Column names to extract (e.g. ``['Climate_Class', 'Geology_Class', ...]``).

    Returns
    -------
    pd.DataFrame
        One row per city with dominant class per attribute.
    """
    # Ensure same CRS
    if aoi_gdf.crs != landscape_gdf.crs:
        landscape_gdf = landscape_gdf.to_crs(aoi_gdf.crs)

    results = []
    for _, aoi_row in aoi_gdf.iterrows():
        city = aoi_row['city']
        aoi_geom = aoi_row.geometry

        # Clip landscape to this AOI
        clipped = landscape_gdf[landscape_gdf.intersects(aoi_geom)].copy()
        if len(clipped) == 0:
            row_data = {'city': city}
            for col in class_columns:
                row_data[col] = None
            results.append(row_data)
            continue

        # Compute intersection areas
        clipped = clipped.copy()
        clipped['_intersect_geom'] = clipped.geometry.intersection(aoi_geom)
        # Use projected CRS for area calculation
        clipped_proj = clipped.set_geometry('_intersect_geom').to_crs("EPSG:3857")
        clipped['_area'] = clipped_proj.geometry.area

        row_data = {'city': city}
        for col in class_columns:
            if col in clipped.columns:
                # Dominant class = class with largest total intersection area
                area_by_class = clipped.groupby(col)['_area'].sum()
                row_data[col] = area_by_class.idxmax()
            else:
                row_data[col] = None
        results.append(row_data)

    return pd.DataFrame(results)


def build_binary_hotspot_dataset(
    aoi_gdf: gpd.GeoDataFrame,
    hotspot_gdf: gpd.GeoDataFrame,
    landscape_classes: pd.DataFrame,
    method: str,
    periods: List[str] = None,
) -> pd.DataFrame:
    """
    Build a city-level binary dataset: does a hotspot intersect the AOI

    Parameters
    ----------
    aoi_gdf : gpd.GeoDataFrame
        City AOI polygons with ``city`` column.
    hotspot_gdf : gpd.GeoDataFrame
        Enriched hotspot polygons from NB05.
    landscape_classes : pd.DataFrame
        Output of ``extract_dominant_landscape()`` with ``city`` + class columns.
    method : str
        Detection method to filter (e.g. ``'GI_STAR'``).
    periods : list[str], optional
        Periods to create binary columns for (default: ``['Day', 'Night']``).

    Returns
    -------
    pd.DataFrame
        One row per city.  Columns include landscape classes and
        ``Hotspot_Day``, ``Hotspot_Night`` (0/1).
    """
    if periods is None:
        periods = ['Day', 'Night']

    method_gdf = hotspot_gdf[hotspot_gdf['method'] == method].copy()

    # Merge landscape classes into AOI
    df = aoi_gdf[['city', 'aoi_area_km2']].merge(landscape_classes, on='city', how='left')

    for period in periods:
        period_gdf = method_gdf[method_gdf['period'] == period]
        flags = []
        for _, aoi_row in aoi_gdf.iterrows():
            city = aoi_row['city']
            aoi_geom = aoi_row.geometry
            city_hotspots = period_gdf[period_gdf['city'] == city]
            if len(city_hotspots) > 0 and city_hotspots.unary_union.intersects(aoi_geom):
                flags.append(1)
            else:
                flags.append(0)
        df[f'Hotspot_{period}'] = flags

    return df


def prepare_occurrence_dataset(
    occurrence_df: pd.DataFrame,
    block_columns: List[str],
    min_count: int = 5,
) -> pd.DataFrame:
    """
    Collapse sparse categorical levels before city-level occurrence modelling.

    The Gi* occurrence analysis operates on only 58 cities. Rare categories can
    create quasi-separation and unstable maximum-likelihood estimates, so levels
    occurring fewer than ``min_count`` times are grouped into an ``Other`` class.

    Parameters
    ----------
    occurrence_df : pd.DataFrame
        Output of ``build_binary_hotspot_dataset()``.
    block_columns : list[str]
        Ordered predictor columns to check.
    min_count : int
        Minimum frequency required to retain a category as-is.

    Returns
    -------
    pd.DataFrame
        Copy of ``occurrence_df`` with sparse levels collapsed.
    """
    prepared = occurrence_df.copy()
    for col in block_columns:
        counts = prepared[col].value_counts(dropna=False)
        rare_levels = counts[counts < min_count].index.tolist()
        if len(rare_levels) == 0:
            continue
        other_label = f'{col}_Other'
        prepared[col] = prepared[col].where(~prepared[col].isin(rare_levels), other=other_label)
    return prepared


def summarize_binary_separation_risk(
    df: pd.DataFrame,
    dv_column: str,
    block_columns: List[str],
) -> pd.DataFrame:
    """
    Summarize zero-cell risks for binary occurrence models.

    A categorical level with only successes or only failures can induce
    (quasi-)separation in a logit-type model. This helper reports the binary
    outcome counts for every level in every predictor block so Notebook 06 can
    surface the risk explicitly before coefficient-level interpretation.

    Parameters
    ----------
    df : pd.DataFrame
        City-level occurrence dataset.
    dv_column : str
        Binary dependent variable column.
    block_columns : list[str]
        Predictor block columns to inspect.

    Returns
    -------
    pd.DataFrame
        Columns include ``Block``, ``Level``, counts of 0/1 outcomes, and a
        boolean ``Zero-cell risk`` flag.
    """
    rows = []
    for block in block_columns:
        counts = pd.crosstab(df[block], df[dv_column]).reindex(columns=[0, 1], fill_value=0)
        for level, row in counts.iterrows():
            n_zero = int(row.get(0, 0))
            n_one = int(row.get(1, 0))
            rows.append({
                'Block': block,
                'Level': level,
                'No hotspot (0)': n_zero,
                'Hotspot (1)': n_one,
                'Zero-cell risk': (n_zero == 0 or n_one == 0),
            })
    return pd.DataFrame(rows)


def fit_hierarchical_binomial_glm(
    df: pd.DataFrame,
    dv_column: str,
    block_columns: List[str],
    alpha: float = 0.05,
    verbose: bool = True,
) -> Dict:
    """
    Fit cumulative binomial GLMs with the canonical logit link.

    This is the primary occurrence-analysis engine for Notebook 06. It replaces
    the older direct ``Logit`` fit because GLM(Binomial, logit) is numerically
    more stable for the sparse city-level Gi* presence/absence dataset while
    preserving the same substantive model family.

    Parameters
    ----------
    df : pd.DataFrame
        City-level dataset with binary dependent variable and categorical blocks.
    dv_column : str
        Name of the binary outcome column.
    block_columns : list[str]
        Ordered list of categorical predictor columns added cumulatively.
    alpha : float
        Significance level.
    verbose : bool
        Print progress.

    Returns
    -------
    dict
        Keys: ``'models'``, ``'comparison'``, ``'block_tests'``, ``'model_results'``.
    """
    y = df[dv_column].astype(float)

    models = []
    model_results = []
    prev_result = None

    for i, _ in enumerate(block_columns):
        current_blocks = block_columns[:i + 1]
        block_label = ' + '.join(current_blocks)

        X_parts = []
        for col in current_blocks:
            dummies = pd.get_dummies(df[col], prefix=col, drop_first=True, dtype=float)
            X_parts.append(dummies)
        X = pd.concat(X_parts, axis=1)
        X = sm.add_constant(X, has_constant='add')

        if verbose:
            print(f"\n  Block {i+1}: {block_label}")
            print(f"    Predictors: {X.shape[1] - 1} dummies + intercept")

        model = sm.GLM(y, X, family=sm.families.Binomial())
        result = model.fit(maxiter=200, disp=0)
        converged = bool(getattr(result, 'converged', True))
        pseudo_r2 = np.nan
        if result.null_deviance not in (0, np.nan):
            pseudo_r2 = 1 - (result.deviance / result.null_deviance)

        lr_test = None
        if prev_result is not None:
            lr_stat = 2 * (result.llf - prev_result.llf)
            df_diff = int(result.df_model - prev_result.df_model)
            if df_diff > 0:
                lr_pvalue = scipy_stats.chi2.sf(lr_stat, df_diff)
                lr_test = {
                    'block_added': block_columns[i],
                    'lr_statistic': lr_stat,
                    'df': df_diff,
                    'p_value': lr_pvalue,
                    'significant': lr_pvalue < alpha,
                }
                if verbose:
                    sig_str = '***' if lr_pvalue < 0.001 else '**' if lr_pvalue < 0.01 else '*' if lr_pvalue < alpha else 'ns'
                    print(f"    LR test vs Block {i}: χ²={lr_stat:.3f}, df={df_diff}, p={lr_pvalue:.4f} {sig_str}")

        model_info = {
            'block': i + 1,
            'block_label': block_label,
            'n_predictors': X.shape[1] - 1,
            'log_likelihood': result.llf,
            'pseudo_r2': pseudo_r2,
            'aic': result.aic,
            'bic': result.bic_llf,
            'converged': converged,
            'lr_test': lr_test,
        }
        model_results.append(model_info)
        models.append(result)
        prev_result = result

        if verbose:
            print(f"    McFadden-style R² = {pseudo_r2:.4f}, AIC = {result.aic:.1f}, LL = {result.llf:.2f}")

    comparison_df = pd.DataFrame([{
        'Block': r['block'],
        'Variables': r['block_label'],
        'K': r['n_predictors'],
        'Log-Lik': r['log_likelihood'],
        'McFadden R²': r['pseudo_r2'],
        'AIC': r['aic'],
        'BIC': r['bic'],
        'Converged': r.get('converged', False),
    } for r in model_results])
    comparison_df['ΔR²'] = comparison_df['McFadden R²'].diff().fillna(comparison_df['McFadden R²'])

    block_tests = [r.get('lr_test') for r in model_results if r.get('lr_test') is not None]

    return {
        'models': models,
        'comparison': comparison_df,
        'block_tests': block_tests,
        'model_results': model_results,
    }



# =========================================================================
# WILD CLUSTER BOOTSTRAP  (Cameron, Gelbach & Miller, 2008)
# =========================================================================

def wild_cluster_bootstrap(
    model_result,
    X: pd.DataFrame,
    y: pd.Series,
    cluster_var: pd.Series,
    n_bootstrap: int = 999,
    random_state: int = 42,
) -> pd.DataFrame:
    """
    Compute Wild Cluster Bootstrap p-values for OLS coefficients.

    Implements the restricted residual bootstrap (WCR) of Cameron, Gelbach
    and Miller (2008, *Review of Economics and Statistics*, 90(3), 414–427)
    using Rademacher weights (+1/−1 with equal probability) for cluster-level
    perturbation.

    Algorithm
    ---------
    1. Fit restricted model (null: β_k = 0) for each coefficient k.
    2. Obtain restricted residuals ê_r.
    3. For b = 1, …, B bootstrap iterations:
       a. Draw one Rademacher weight v_g ∈ {−1, +1} per cluster g.
       b. Construct bootstrap DV: y*_i = X_i β̂_r + v_{g(i)} · ê_{r,i}
       c. Fit unrestricted OLS on (X, y*), compute t-statistic for β_k.
    4. Bootstrap p-value = (1 + #{|t*_b| ≥ |t_obs|}) / (1 + B).

    Parameters
    ----------
    model_result : statsmodels OLS RegressionResultsWrapper
        Fitted OLS model (unrestricted).
    X : pd.DataFrame
        Design matrix (with constant if used).
    y : pd.Series
        Dependent variable.
    cluster_var : pd.Series
        Cluster assignment (aligned with X/y index).
    n_bootstrap : int
        Number of bootstrap replications (default: 999).
    random_state : int
        Random seed for reproducibility.

    Returns
    -------
    pd.DataFrame
        Columns: ``Variable``, ``t_obs``, ``Boot_p``.
    """
    rng = np.random.RandomState(random_state)
    clusters = cluster_var.values
    unique_clusters = np.unique(clusters)
    n_clusters = len(unique_clusters)
    params = model_result.params
    resid = model_result.resid
    n_vars = len(params)

    # Observed t-statistics (from cluster-robust SEs)
    try:
        cov_cl = model_result.get_robustcov_results(
            cov_type='cluster', groups=clusters
        )
        t_obs = cov_cl.tvalues
    except Exception:
        # Fallback: use HC1 if clustering fails
        t_obs = model_result.tvalues

    X_arr = np.asarray(X, dtype=float)

    boot_t = np.zeros((n_bootstrap, n_vars))

    for b in range(n_bootstrap):
        # Rademacher weights: one per cluster
        weights = rng.choice([-1.0, 1.0], size=n_clusters)
        weight_map = dict(zip(unique_clusters, weights))
        v = np.array([weight_map[c] for c in clusters])

        # Construct bootstrap DV
        y_star = X_arr @ params + v * resid

        # Fit OLS on bootstrap sample
        try:
            mod_b = sm.OLS(y_star, X_arr).fit()
            # Cluster-robust t-stats
            try:
                cov_b = mod_b.get_robustcov_results(
                    cov_type='cluster', groups=clusters
                )
                boot_t[b, :] = cov_b.tvalues
            except Exception:
                boot_t[b, :] = mod_b.tvalues
        except Exception:
            boot_t[b, :] = np.nan

    # Compute two-sided bootstrap p-values
    # p = (1 + #{|t*| >= |t_obs|}) / (1 + B)
    boot_p = np.zeros(n_vars)
    for k in range(n_vars):
        valid_mask = ~np.isnan(boot_t[:, k])
        if valid_mask.sum() == 0:
            boot_p[k] = np.nan
        else:
            count_extreme = np.sum(
                np.abs(boot_t[valid_mask, k]) >= np.abs(t_obs[k])
            )
            boot_p[k] = (1 + count_extreme) / (1 + valid_mask.sum())

    var_names = list(X.columns) if hasattr(X, 'columns') else [f'x{i}' for i in range(n_vars)]
    result_df = pd.DataFrame({
        'Variable': var_names,
        't_obs': t_obs,
        'Boot_p': boot_p,
    })
    return result_df


# =========================================================================
# HIERARCHICAL LOGISTIC REGRESSION
# =========================================================================

def fit_hierarchical_logit(
    df: pd.DataFrame,
    dv_column: str,
    block_columns: List[str],
    alpha: float = 0.05,
    verbose: bool = True,
) -> Dict:
    """
    Fit a sequence of cumulative logistic regression models.

    Parameters
    ----------
    df : pd.DataFrame
        Dataset with dependent variable and categorical predictors.
    dv_column : str
        Name of the binary (0/1) dependent variable column.
    block_columns : list[str]
        Ordered list of categorical predictor columns (added cumulatively).
    alpha : float
        Significance level.
    verbose : bool
        Print progress.

    Returns
    -------
    dict
        Keys: ``'models'`` (list of fitted results), ``'comparison'`` (DataFrame),
        ``'block_tests'`` (list of LR-test dicts), ``'full_model_summary'`` (dict).
    """
    y = df[dv_column].values.astype(float)

    models = []
    model_results = []
    prev_result = None

    for i, _ in enumerate(block_columns):
        current_blocks = block_columns[:i + 1]
        block_label = " + ".join(current_blocks)

        # Create dummy variables
        X_parts = []
        for col in current_blocks:
            dummies = pd.get_dummies(df[col], prefix=col, drop_first=True, dtype=float)
            X_parts.append(dummies)
        X = pd.concat(X_parts, axis=1)
        X = sm.add_constant(X, has_constant='add')

        if verbose:
            print(f"\n  Block {i+1}: {block_label}")
            print(f"    Predictors: {X.shape[1] - 1} dummies + intercept")

        # Fit logit
        try:
            model = Logit(y, X)
            result = model.fit(disp=0, maxiter=100, method='newton')
            converged = result.mle_retvals.get('converged', True)
        except Exception:
            # Fallback: try bfgs if newton fails
            try:
                model = Logit(y, X)
                result = model.fit(disp=0, maxiter=300, method='bfgs')
                converged = result.mle_retvals.get('converged', True)
            except Exception as e:
                if verbose:
                    print(f"    ⚠ Model failed to converge: {e}")
                models.append(None)
                model_results.append({
                    'block': i + 1,
                    'block_label': block_label,
                    'n_predictors': X.shape[1] - 1,
                    'log_likelihood': None,
                    'pseudo_r2': None,
                    'aic': None,
                    'bic': None,
                    'converged': False,
                })
                continue

        if verbose and not converged:
            print("    ⚠ Convergence warning")

        pseudo_r2 = result.prsquared  # McFadden pseudo-R²

        # Likelihood ratio test vs previous block
        lr_test = None
        if prev_result is not None:
            lr_stat = 2 * (result.llf - prev_result.llf)
            df_diff = result.df_model - prev_result.df_model
            if df_diff > 0:
                lr_pvalue = scipy_stats.chi2.sf(lr_stat, df_diff)
                lr_test = {
                    'block_added': block_columns[i],
                    'lr_statistic': lr_stat,
                    'df': df_diff,
                    'p_value': lr_pvalue,
                    'significant': lr_pvalue < alpha,
                }
                if verbose:
                    sig_str = "***" if lr_pvalue < 0.001 else "**" if lr_pvalue < 0.01 else "*" if lr_pvalue < alpha else "ns"
                    print(f"    LR test vs Block {i}: χ²={lr_stat:.3f}, df={df_diff}, p={lr_pvalue:.4f} {sig_str}")

        model_info = {
            'block': i + 1,
            'block_label': block_label,
            'n_predictors': int(result.df_model),
            'log_likelihood': result.llf,
            'pseudo_r2': pseudo_r2,
            'aic': result.aic,
            'bic': result.bic,
            'converged': converged,
            'lr_test': lr_test,
        }
        model_results.append(model_info)
        models.append(result)
        prev_result = result

        if verbose:
            print(f"    Pseudo-R² = {pseudo_r2:.4f}, AIC = {result.aic:.1f}, LL = {result.llf:.2f}")

    # Comparison table
    comparison_df = pd.DataFrame([{
        'Block': r['block'],
        'Variables': r['block_label'],
        'K': r['n_predictors'],
        'Log-Lik': r['log_likelihood'],
        'McFadden R²': r['pseudo_r2'],
        'AIC': r['aic'],
        'BIC': r['bic'],
        'Converged': r.get('converged', False),
    } for r in model_results])

    # Variance partitioning (incremental pseudo-R²)
    comparison_df['ΔR²'] = comparison_df['McFadden R²'].diff().fillna(
        comparison_df['McFadden R²']
    )

    # Collect block-level LR tests
    block_tests = [r.get('lr_test') for r in model_results if r.get('lr_test') is not None]

    return {
        'models': models,
        'comparison': comparison_df,
        'block_tests': block_tests,
        'model_results': model_results,
    }


# =========================================================================
# HIERARCHICAL OLS WITH CLUSTERED SEs
# =========================================================================

def fit_hierarchical_ols_clustered(
    df: pd.DataFrame,
    dv_column: str,
    block_columns: List[str],
    cluster_column: str,
    alpha: float = 0.05,
    verbose: bool = True,
    run_bootstrap: bool = False,
    n_bootstrap: int = 999,
    bootstrap_seed: int = 42,
) -> Dict:
    """
    Fit a sequence of cumulative OLS models with city-clustered standard errors.

    Parameters
    ----------
    df : pd.DataFrame
        Dataset with DV, categorical predictors, and cluster column.
    dv_column : str
        Dependent variable column (e.g. ``'log_area_km2'``).
    block_columns : list[str]
        Ordered categorical predictor columns (added cumulatively).
    cluster_column : str
        Column to cluster SEs on (e.g. ``'city'``).
    alpha : float
        Significance level.
    verbose : bool
        Print progress.
    run_bootstrap : bool
        If True, compute Wild Cluster Bootstrap p-values for the **final**
        (full) model using ``wild_cluster_bootstrap()``.
    n_bootstrap : int
        Number of bootstrap replications (default 999).
    bootstrap_seed : int
        Random seed for bootstrap reproducibility.

    Returns
    -------
    dict
        Keys: ``'models'``, ``'comparison'``, ``'block_tests'``,
        ``'bootstrap'`` (DataFrame of bootstrap p-values, if requested).
    """
    y = df[dv_column].values.astype(float)
    clusters = df[cluster_column].values

    models = []
    model_results = []
    prev_ssr = None
    prev_k = 0

    for i, _ in enumerate(block_columns):
        current_blocks = block_columns[:i + 1]
        block_label = " + ".join(current_blocks)

        # Create dummy variables
        X_parts = []
        for col in current_blocks:
            dummies = pd.get_dummies(df[col], prefix=col, drop_first=True, dtype=float)
            X_parts.append(dummies)
        X = pd.concat(X_parts, axis=1)
        X = sm.add_constant(X, has_constant='add')

        if verbose:
            print(f"\n  Block {i+1}: {block_label}")
            print(f"    Predictors: {X.shape[1] - 1} dummies + intercept")

        # Fit OLS with clustered SEs
        model = sm.OLS(y, X)
        result = model.fit(
            cov_type='cluster',
            cov_kwds={'groups': clusters},
        )

        r2 = result.rsquared
        adj_r2 = result.rsquared_adj

        # Partial F-test vs previous block
        f_test = None
        if prev_ssr is not None:
            k_new = X.shape[1] - 1  # number of predictors (excl. constant)
            k_added = k_new - prev_k
            if k_added > 0:
                ssr_restricted = prev_ssr
                ssr_full = result.ssr
                n = len(y)
                f_stat = ((ssr_restricted - ssr_full) / k_added) / (ssr_full / (n - k_new - 1))
                f_pvalue = scipy_stats.f.sf(f_stat, k_added, n - k_new - 1)
                f_test = {
                    'block_added': block_columns[i],
                    'f_statistic': f_stat,
                    'df_num': k_added,
                    'df_denom': n - k_new - 1,
                    'p_value': f_pvalue,
                    'significant': f_pvalue < alpha,
                }
                if verbose:
                    sig_str = "***" if f_pvalue < 0.001 else "**" if f_pvalue < 0.01 else "*" if f_pvalue < alpha else "ns"
                    print(f"    F-test vs Block {i}: F={f_stat:.3f}, df=({k_added},{n-k_new-1}), p={f_pvalue:.4f} {sig_str}")

        model_info = {
            'block': i + 1,
            'block_label': block_label,
            'n_predictors': X.shape[1] - 1,
            'r2': r2,
            'adj_r2': adj_r2,
            'aic': result.aic,
            'bic': result.bic,
            'f_test': f_test,
        }
        model_results.append(model_info)
        models.append(result)

        prev_ssr = result.ssr
        prev_df_resid = result.df_resid
        prev_k = X.shape[1] - 1

        if verbose:
            print(f"    R² = {r2:.4f}, Adj-R² = {adj_r2:.4f}, AIC = {result.aic:.1f}")

    # Comparison table
    comparison_df = pd.DataFrame([{
        'Block': r['block'],
        'Variables': r['block_label'],
        'K': r['n_predictors'],
        'R²': r['r2'],
        'Adj-R²': r['adj_r2'],
        'AIC': r['aic'],
        'BIC': r['bic'],
    } for r in model_results])

    comparison_df['ΔR²'] = comparison_df['R²'].diff().fillna(comparison_df['R²'])

    block_tests = [r.get('f_test') for r in model_results if r.get('f_test') is not None]

    # Wild Cluster Bootstrap on the FULL model (last block)
    bootstrap_result = None
    if run_bootstrap and len(models) > 0:
        final_model = models[-1]
        # Reconstruct X for the full model
        X_parts = []
        for col in block_columns:
            dummies = pd.get_dummies(df[col], prefix=col, drop_first=True, dtype=float)
            X_parts.append(dummies)
        X_full = pd.concat(X_parts, axis=1)
        X_full = sm.add_constant(X_full, has_constant='add')
        y_full = pd.Series(y, index=df.index)
        cluster_series = pd.Series(clusters, index=df.index)

        if verbose:
            print(f"\n  Running Wild Cluster Bootstrap (B={n_bootstrap}, Rademacher weights)...")
        bootstrap_result = wild_cluster_bootstrap(
            model_result=final_model,
            X=X_full,
            y=y_full,
            cluster_var=cluster_series,
            n_bootstrap=n_bootstrap,
            random_state=bootstrap_seed,
        )
        if verbose:
            sig_boot = (bootstrap_result['Boot_p'] < alpha).sum()
            print(f"    ✓ Bootstrap complete: {sig_boot}/{len(bootstrap_result)} coefficients significant at α={alpha}")

    return {
        'models': models,
        'comparison': comparison_df,
        'block_tests': block_tests,
        'model_results': model_results,
        'bootstrap': bootstrap_result,
    }


def format_ols_coefficients(
    result, alpha: float = 0.05, log_transformed: bool = True,
    bootstrap_df: pd.DataFrame = None,
) -> pd.DataFrame:
    """
    Extract OLS coefficients with clustered SEs, CIs, and optional % change.

    Parameters
    ----------
    result : statsmodels RegressionResults
        Fitted OLS result (with clustered SEs).
    alpha : float
        Significance level for CIs.
    log_transformed : bool
        If True, add a '% Change' column (exp(β) - 1) * 100.
    bootstrap_df : pd.DataFrame, optional
        Output of ``wild_cluster_bootstrap()`` — adds ``Boot_p`` and
        ``Boot_Sig`` columns.

    Returns
    -------
    pd.DataFrame
    """
    params = result.params
    conf = result.conf_int(alpha=alpha)
    pvalues = result.pvalues
    bse = result.bse

    rows = []
    for var in params.index:
        coef = params[var]
        ci_low = conf.loc[var, 0]
        ci_high = conf.loc[var, 1]
        p = pvalues[var]
        t = result.tvalues[var]

        sig = ''
        if p < 0.001:
            sig = '***'
        elif p < 0.01:
            sig = '**'
        elif p < alpha:
            sig = '*'

        row = {
            'Variable': var,
            'Coef (β)': round(coef, 4),
            'Clustered SE': round(bse[var], 4),
            't': round(t, 3),
            'p-value': round(p, 4),
            f'CI {(1-alpha)*100:.0f}% Lower': round(ci_low, 4),
            f'CI {(1-alpha)*100:.0f}% Upper': round(ci_high, 4),
            'Sig': sig,
        }

        # Add Wild Cluster Bootstrap p-value if available
        if bootstrap_df is not None:
            boot_row = bootstrap_df[bootstrap_df['Variable'] == var]
            if len(boot_row) > 0:
                boot_p = boot_row['Boot_p'].values[0]
                row['Boot_p'] = round(boot_p, 4)
                boot_sig = ''
                if boot_p < 0.001:
                    boot_sig = '***'
                elif boot_p < 0.01:
                    boot_sig = '**'
                elif boot_p < alpha:
                    boot_sig = '*'
                row['Boot_Sig'] = boot_sig
            else:
                row['Boot_p'] = np.nan
                row['Boot_Sig'] = ''

        if log_transformed and var != 'const':
            pct_change = (np.exp(coef) - 1) * 100
            row['% Change'] = round(pct_change, 2)

        rows.append(row)

    return pd.DataFrame(rows)


def format_binomial_coefficients(
    result,
    alpha: float = 0.05,
) -> pd.DataFrame:
    """
    Extract binomial GLM coefficients with standard errors, CIs, and odds ratios.

    Parameters
    ----------
    result : statsmodels GLMResults
        Fitted binomial GLM result.
    alpha : float
        Significance level for confidence intervals.

    Returns
    -------
    pd.DataFrame
    """
    params = result.params
    conf = result.conf_int(alpha=alpha)
    pvalues = result.pvalues
    bse = result.bse
    zvalues = result.tvalues

    rows = []
    for var in params.index:
        coef = params[var]
        ci_low = conf.loc[var, 0]
        ci_high = conf.loc[var, 1]
        p = pvalues[var]
        z = zvalues[var]

        sig = ''
        if p < 0.001:
            sig = '***'
        elif p < 0.01:
            sig = '**'
        elif p < alpha:
            sig = '*'

        row = {
            'Variable': var,
            'Coef (β)': round(coef, 4),
            'SE': round(bse[var], 4),
            'z': round(z, 3),
            'p-value': round(p, 4),
            f'CI {(1-alpha)*100:.0f}% Lower': round(ci_low, 4),
            f'CI {(1-alpha)*100:.0f}% Upper': round(ci_high, 4),
            'Odds Ratio': round(np.exp(coef), 4),
            'Sig': sig,
        }
        rows.append(row)

    return pd.DataFrame(rows)


# =========================================================================
# VARIANCE PARTITIONING PLOTS  (Day | Night panel)
# =========================================================================

def plot_variance_partitioning_panel(
    comparison_day: pd.DataFrame,
    comparison_night: pd.DataFrame,
    r2_col: str,
    delta_col: str,
    title: str,
    ylabel: str,
    block_columns: List[str],
    output_path: Optional[Path] = None,
    figsize: Tuple[float, float] = (14, 5),
    dpi: int = 300,
    show: bool = True,
) -> plt.Figure:
    """
    Create a Day | Night panel of stacked bar charts showing incremental
    and cumulative R² / pseudo-R².

    Parameters
    ----------
    comparison_day : pd.DataFrame
        Comparison table for Day model.
    comparison_night : pd.DataFrame
        Comparison table for Night model.
    r2_col : str
        Column name for cumulative R² (e.g. ``'McFadden R²'`` or ``'R²'``).
    delta_col : str
        Column name for incremental R² (e.g. ``'ΔR²'``).
    title : str
        Overall figure title.
    ylabel : str
        Y-axis label.
    block_columns : list[str]
        Block names for x-axis labels.
    output_path : Path, optional
        Save figure to this path (PNG). PDF auto-generated alongside.
    figsize : tuple
        Figure size.
    dpi : int
        Resolution.
    show : bool
        Whether to display the figure.

    Returns
    -------
    plt.Figure
    """
    fig, (ax_day, ax_night) = plt.subplots(1, 2, figsize=figsize)

    colors = ['#4e79a7', '#f28e2b', '#59a14f', '#e15759', '#76b7b2']

    for ax, comp_df, period_label in [(ax_day, comparison_day, 'Day'),
                                       (ax_night, comparison_night, 'Night')]:
        blocks = comp_df['Block'].values
        cumulative = comp_df[r2_col].values
        incremental = comp_df[delta_col].values
        labels = [block_columns[i] for i in range(len(blocks))]

        # Stacked bars (bottom-up)
        bottoms = np.zeros(len(blocks))
        for i in range(len(blocks)):
            ax.bar(i, incremental[i], bottom=bottoms[i],
                   color=colors[i % len(colors)],
                   edgecolor='white', linewidth=1.5,
                   label=labels[i] if period_label == 'Day' else None,
                   zorder=3)
            # Annotation inside bar
            mid = bottoms[i] + incremental[i] / 2
            if incremental[i] > 0.005:
                ax.text(i, mid, f'{incremental[i]:.4f}', ha='center', va='center',
                        fontsize=9, fontweight='bold', color='white')
            if i < len(blocks) - 1:
                bottoms[i + 1] = cumulative[i]

        # Cumulative line
        ax.plot(range(len(blocks)), cumulative, 'k-o', linewidth=2, markersize=8,
                zorder=5, label='Cumulative' if period_label == 'Day' else None)
        for i, val in enumerate(cumulative):
            ax.annotate(f'{val:.4f}', (i, val), textcoords="offset points",
                        xytext=(0, 12), ha='center', fontsize=9, fontweight='bold')

        ax.set_xticks(range(len(blocks)))
        ax.set_xticklabels([f'Block {b}\n+{labels[b-1]}' for b in blocks], fontsize=9)
        ax.set_title(period_label, fontsize=12, fontweight='bold')

        # Per-panel y-limit: leave 35 % headroom for annotations
        max_cum = max(cumulative) if len(cumulative) > 0 else 0.1
        ax.set_ylim(0, max_cum * 1.35)
        ax.grid(axis='y', alpha=0.3)

    ax_day.set_ylabel(ylabel, fontsize=11)
    ax_night.set_ylabel(ylabel, fontsize=11)

    # Single legend from Day panel
    handles, labels_leg = ax_day.get_legend_handles_labels()
    fig.legend(handles, labels_leg, loc='upper center', ncol=len(block_columns) + 1,
               fontsize=9, bbox_to_anchor=(0.5, 0.02), frameon=False)

    fig.suptitle(title, fontsize=13, fontweight='bold')
    plt.tight_layout(rect=[0, 0.06, 1, 0.95])

    if output_path:
        output_path = Path(output_path)
        _export_figure_all_formats(fig, output_path, dpi=dpi)
        print(f"    ✓ Saved: {output_path.name} + .svg + .pdf")

    if not show:
        plt.close(fig)

    return fig


# =========================================================================
# DATA COMPOSITION DONUT CHART  (Day | Night panel)
# =========================================================================

def plot_data_composition_donut(
    df: pd.DataFrame,
    block_columns: List[str],
    periods: List[str] = None,
    title: str = 'Data Composition: P90 Hotspot Polygons by Landscape Class',
    output_path: Optional[Path] = None,
    figsize: Tuple[float, float] = (16, 7),
    dpi: int = 300,
    show: bool = True,
) -> plt.Figure:
    """
    Nested donut chart showing the hierarchical composition of the
    hotspot polygon dataset by landscape class, as Day | Night panels.

    Rings (inside → outside): Block 1 → Block 2 → Block 3.
    Centre annotation: total polygon count.

    Parameters
    ----------
    df : pd.DataFrame or GeoDataFrame
        P90 hotspot polygons with ``'period'`` and landscape class columns.
    block_columns : list[str]
        Landscape class column names in hierarchy order (inner → outer ring).
    periods : list[str], optional
        ``['Day', 'Night']`` by default.
    title : str
        Overall figure title.
    output_path : Path, optional
        Save path (SVG output).
    figsize : tuple
        Figure size.
    dpi : int
        Resolution.
    show : bool
        Display figure.

    Returns
    -------
    plt.Figure
    """
    if periods is None:
        periods = ['Day', 'Night']

    palettes = BLOCK_PALETTES   # shared module-level constant

    fig, axes = plt.subplots(1, len(periods), figsize=figsize)
    if len(periods) == 1:
        axes = [axes]

    # Ring geometry (inner → outer) — dynamically spaced for any number of blocks
    n_rings = len(block_columns)
    ring_width = 0.22
    ring_gap = 0.06
    radii = [0.50 + i * (ring_width + ring_gap) for i in range(n_rings)]
    widths = [ring_width] * n_rings

    # Collect legend handles to build one unified legend
    legend_handles_all = []
    legend_built = False

    for _ax_idx, (ax, period) in enumerate(zip(axes, periods)):
        subset = df[df['period'] == period]
        total = len(subset)

        for ring_idx, col in enumerate(block_columns):
            counts = subset[col].value_counts().sort_index()
            labels = counts.index.tolist()
            sizes = counts.values.tolist()
            cmap = _category_color_map(subset[col], palettes[ring_idx % len(palettes)])
            ring_colors = [cmap[l] for l in labels]

            wedges, _texts, autotexts = ax.pie(
                sizes,
                labels=None,
                autopct=lambda pct, _s=sizes, _t=sum(sizes):
                    f'{int(round(pct * _t / 100))}' if pct > 6 else '',
                pctdistance=1 - widths[ring_idx] / (2 * radii[ring_idx]),
                radius=radii[ring_idx],
                colors=ring_colors,
                wedgeprops=dict(
                    width=widths[ring_idx], edgecolor='white', linewidth=2,
                ),
                startangle=90,
                textprops={'fontsize': 8, 'fontweight': 'bold', 'color': '#333'},
            )
            for at in autotexts:
                at.set_fontsize(8)

            # Build legend handles from first panel only
            if not legend_built:
                short_name = col.replace('_Class', '')
                for w_idx, _w in enumerate(wedges):
                    legend_handles_all.append(
                        plt.matplotlib.patches.Patch(
                            facecolor=ring_colors[w_idx],
                            edgecolor='white',
                            label=f'{short_name}: {labels[w_idx]}',
                        )
                    )

        legend_built = True

        # Centre text
        ax.text(0, 0, f'n = {total}', ha='center', va='center',
                fontsize=15, fontweight='bold', color='#333333')
        ax.set_title(period, fontsize=13, fontweight='bold', pad=10)
        ax.set_aspect('equal')

    # Ring-name annotations (placed once, on the left panel)
    ring_labels_short = [c.replace('_Class', '') for c in block_columns]
    for ring_idx, rl in enumerate(ring_labels_short):
        mid_r = radii[ring_idx] - widths[ring_idx] / 2
        axes[0].annotate(
            rl, xy=(0, -mid_r), fontsize=8, fontstyle='italic',
            ha='center', va='center', color='#666666',
        )

    # Unified legend below figure
    fig.legend(
        handles=legend_handles_all,
        loc='lower center',
        ncol=min(5, len(legend_handles_all)),
        fontsize=8,
        frameon=False,
        bbox_to_anchor=(0.5, -0.02),
    )

    fig.suptitle(title, fontsize=14, fontweight='bold')
    plt.tight_layout(rect=[0, 0.10, 1, 0.95])

    if output_path:
        output_path = Path(output_path)
        _export_figure_all_formats(fig, output_path, dpi=dpi)
        print(f"    ✓ Saved: {output_path.name} + .svg + .pdf")

    if not show:
        plt.close(fig)

    return fig


# =========================================================================
# DATA COMPOSITION SANKEY  (Day / Night stacked)
# =========================================================================

def plot_data_composition_sankey(
    df: pd.DataFrame,
    block_columns: List[str],
    periods: List[str] = None,
    title: str = 'Data Composition: Sankey — Climate → Geology → Elevation',
    output_path: Optional[Path] = None,
    figsize: Tuple[float, float] = (16, 14),
    dpi: int = 300,
    show: bool = True,
) -> plt.Figure:
    """
    Three-column Sankey (alluvial) diagram showing polygon flows through
    the three landscape hierarchies.  Separate subplot for each period.

    Columns (left → right): Climate Zone · Geology · Elevation.
    Band colour follows the source (left-side) node.

    Parameters
    ----------
    df : pd.DataFrame or GeoDataFrame
        P90 hotspot polygons with ``'period'`` and landscape class columns.
    block_columns : list[str]
        Landscape class column names in hierarchy order (length ≥ 2).
    periods : list[str], optional
        ``['Day', 'Night']`` by default.
    title : str
        Overall figure title.
    output_path : Path, optional
        Save path (SVG output).
    figsize : tuple
        Figure size.
    dpi : int
        Resolution.
    show : bool
        Display figure.

    Returns
    -------
    plt.Figure
    """
    if periods is None:
        periods = ['Day', 'Night']

    from matplotlib.patches import PathPatch
    from matplotlib.path import Path as MplPath

    col_palettes = BLOCK_PALETTES   # shared module-level constant

    fig, axes = plt.subplots(len(periods), 1, figsize=figsize)
    if len(periods) == 1:
        axes = [axes]

    # Layout constants — dynamically spaced for any number of blocks
    n_cols = len(block_columns)
    node_w = 0.04                  # node width
    gap = 0.03                     # vertical gap between nodes
    min_node_h = 0.04              # minimum node height for label legibility
    x_start = 0.22
    x_end = 0.74
    if n_cols > 1:
        x_spacing = (x_end - x_start) / (n_cols - 1)
    else:
        x_spacing = 0
    x_left = [x_start + i * x_spacing for i in range(n_cols)]

    for ax, period in zip(axes, periods):
        subset = df[df['period'] == period]
        total = len(subset)

        # ── 1. Build node stacks (sorted largest-first) ─────────
        nodes = {}       # col_idx → dict{ label: (y0, y1, count) }
        cat_cmaps = {}   # col_idx → {label: hex_colour} (alphabetical)
        for ci, col_name in enumerate(block_columns):
            counts = subset[col_name].value_counts().sort_values(ascending=False)
            cat_cmaps[ci] = _category_color_map(
                subset[col_name], col_palettes[ci % len(col_palettes)]
            )
            n_cats = len(counts)
            total_gap = gap * max(n_cats - 1, 0)
            scale = (1.0 - total_gap) / total if total > 0 else 1.0
            # First pass: compute raw heights, enforce minimum
            raw_heights = {lbl: max(cnt * scale, min_node_h) for lbl, cnt in counts.items()}
            # Rescale so total fits in [0, 1] with gaps
            sum_h = sum(raw_heights.values()) + total_gap
            rescale = (1.0) / sum_h if sum_h > 0 else 1.0
            y = 0.0
            nd = {}
            for lbl, cnt in counts.items():
                h = raw_heights[lbl] * rescale
                nd[lbl] = (y, y + h, cnt)
                y += h + gap * rescale
            nodes[ci] = nd

        # ── 2. Draw flow bands between adjacent columns ─────────
        for li in range(len(block_columns) - 1):
            src_col = block_columns[li]
            tgt_col = block_columns[li + 1]
            cross = pd.crosstab(subset[src_col], subset[tgt_col])
            src_nd = nodes[li]
            tgt_nd = nodes[li + 1]
            palette = col_palettes[li % len(col_palettes)]

            # Scale factors per column
            n_src = len(src_nd)
            src_scale = (1.0 - gap * max(n_src - 1, 0)) / total if total else 1
            n_tgt = len(tgt_nd)
            tgt_scale = (1.0 - gap * max(n_tgt - 1, 0)) / total if total else 1

            src_cursors = {lbl: y0 for lbl, (y0, _, _) in src_nd.items()}
            tgt_cursors = {lbl: y0 for lbl, (y0, _, _) in tgt_nd.items()}

            src_x_r = x_left[li] + node_w
            tgt_x_l = x_left[li + 1]
            mid_x = (src_x_r + tgt_x_l) / 2

            src_cmap = cat_cmaps[li]
            for src_label in cross.index:
                color = src_cmap.get(src_label, palette[0])
                for tgt_label in cross.columns:
                    flow = cross.loc[src_label, tgt_label]
                    if flow == 0:
                        continue
                    s_bot = src_cursors[src_label]
                    s_top = s_bot + flow * src_scale
                    src_cursors[src_label] = s_top
                    t_bot = tgt_cursors[tgt_label]
                    t_top = t_bot + flow * tgt_scale
                    tgt_cursors[tgt_label] = t_top

                    verts = [
                        (src_x_r, s_bot),
                        (mid_x, s_bot), (mid_x, t_bot), (tgt_x_l, t_bot),
                        (tgt_x_l, t_top),
                        (mid_x, t_top), (mid_x, s_top), (src_x_r, s_top),
                        (src_x_r, s_bot),
                    ]
                    codes = [
                        MplPath.MOVETO,
                        MplPath.CURVE4, MplPath.CURVE4, MplPath.CURVE4,
                        MplPath.LINETO,
                        MplPath.CURVE4, MplPath.CURVE4, MplPath.CURVE4,
                        MplPath.CLOSEPOLY,
                    ]
                    patch = PathPatch(
                        MplPath(verts, codes),
                        facecolor=color, alpha=0.35,
                        edgecolor='none', zorder=2,
                    )
                    ax.add_patch(patch)

        # ── 3. Draw node rectangles + labels ────────────────────
        for ci, col_name in enumerate(block_columns):
            cmap = cat_cmaps[ci]
            nd = nodes[ci]
            x = x_left[ci]
            for cat_i, (label, (y0, y1, count)) in enumerate(nd.items()):
                color = cmap[label]
                rect = plt.Rectangle(
                    (x, y0), node_w, y1 - y0,
                    facecolor=color, edgecolor='white', linewidth=1.5, zorder=4,
                )
                ax.add_patch(rect)

                y_mid = (y0 + y1) / 2
                if ci == 0:
                    ax.text(x - 0.01, y_mid, f'{label}\n({count})',
                            ha='right', va='center', fontsize=9,
                            fontweight='bold', zorder=10)
                elif ci == len(block_columns) - 1:
                    ax.text(x + node_w + 0.01, y_mid, f'{label}\n({count})',
                            ha='left', va='center', fontsize=9,
                            fontweight='bold', zorder=10)
                else:
                    ax.text(x + node_w + 0.01, y_mid, f'{label}\n({count})',
                            ha='left', va='center', fontsize=9,
                            fontweight='bold', zorder=10)

        # ── 4. Column headers ──────────────────────────────────
        headers = [c.replace('_Class', '') for c in block_columns]
        for ci, hdr in enumerate(headers):
            ax.text(x_left[ci] + node_w / 2, -0.07, hdr,
                    ha='center', va='top', fontsize=11,
                    fontweight='bold', fontstyle='italic')

        # ── 5. Total polygon count ─────────────────────────────
        mid_x_pos = (x_left[0] + x_left[-1] + node_w) / 2
        ax.text(mid_x_pos, 1.06, f'n = {total} polygons',
                ha='center', va='bottom', fontsize=13,
                fontweight='bold', color='#333333')

        ax.set_title(period, fontsize=14, fontweight='bold', pad=20)
        ax.set_xlim(-0.12, x_left[-1] + node_w + 0.30)
        ax.set_ylim(-0.12, 1.15)
        ax.axis('off')

    fig.suptitle(title, fontsize=14, fontweight='bold', y=0.99)
    plt.tight_layout(rect=[0, 0, 1, 0.97])

    if output_path:
        output_path = Path(output_path)
        _export_figure_all_formats(fig, output_path, dpi=dpi)
        print(f"    ✓ Saved: {output_path.name} + .svg + .pdf")

    if not show:
        plt.close(fig)

    return fig


# =========================================================================
# COEFFICIENT FOREST PLOT  (Day | Night panel)
# =========================================================================

def plot_coefficient_forest_panel(
    coef_day: pd.DataFrame,
    coef_night: pd.DataFrame,
    title: str,
    output_path: Optional[Path] = None,
    figsize: Optional[Tuple[float, float]] = None,
    max_abs_display: Optional[float] = None,
    dpi: int = 300,
    show: bool = True,
) -> plt.Figure:
    """
    Create a Day | Night panel of horizontal forest plots of OLS coefficients.

    Parameters
    ----------
    coef_day : pd.DataFrame
        Output of ``format_ols_coefficients()`` for Day.
    coef_night : pd.DataFrame
        Output of ``format_ols_coefficients()`` for Night.
    title : str
        Overall figure title.
    output_path : Path, optional
        Save path.
    figsize : tuple, optional
        Auto-sized if None.
    max_abs_display : float, optional
        If provided, clip the displayed coefficient axis to ``±max_abs_display``.
        This is useful when a few unstable coefficients produce enormous
        confidence intervals that would otherwise hide the interpretable range.
    dpi : int
        Resolution.
    show : bool
        Display figure.

    Returns
    -------
    plt.Figure
    """
    # Exclude intercept
    plot_day = coef_day[coef_day['Variable'] != 'const'].copy().reset_index(drop=True)
    plot_night = coef_night[coef_night['Variable'] != 'const'].copy().reset_index(drop=True)
    if len(plot_day) == 0:
        return None

    n_max = max(len(plot_day), len(plot_night))
    if figsize is None:
        figsize = (14, max(4, n_max * 0.45))

    fig, (ax_day, ax_night) = plt.subplots(1, 2, figsize=figsize, sharey=False)

    ci_lower_col = [c for c in plot_day.columns if 'Lower' in c][0]
    ci_upper_col = [c for c in plot_day.columns if 'Upper' in c][0]

    for ax, plot_df, period_label in [(ax_day, plot_day, 'Day'),
                                       (ax_night, plot_night, 'Night')]:
        n_panel = len(plot_df)
        y_pos = np.arange(n_panel)
        coefs = plot_df['Coef (β)'].values
        ci_lower = plot_df[ci_lower_col].values
        ci_upper = plot_df[ci_upper_col].values

        if max_abs_display is not None:
            clipped_coefs = np.clip(coefs, -max_abs_display, max_abs_display)
            clipped_lower = np.clip(ci_lower, -max_abs_display, max_abs_display)
            clipped_upper = np.clip(ci_upper, -max_abs_display, max_abs_display)
            left_truncated = ci_lower < -max_abs_display
            right_truncated = ci_upper > max_abs_display
            errors = np.array([clipped_coefs - clipped_lower, clipped_upper - clipped_coefs])
        else:
            clipped_coefs = coefs
            left_truncated = np.zeros_like(coefs, dtype=bool)
            right_truncated = np.zeros_like(coefs, dtype=bool)
            errors = np.array([coefs - ci_lower, ci_upper - coefs])

        # Colour by significance
        colors = []
        for _, row in plot_df.iterrows():
            if row['Sig'] in ('***', '**', '*'):
                colors.append('#d73027' if row['Coef (β)'] > 0 else '#4575b4')
            else:
                colors.append('#999999')

        ax.errorbar(clipped_coefs, y_pos, xerr=errors, fmt='o', color='black',
                    ecolor='grey', elinewidth=1.5, capsize=3, markersize=0, zorder=3)
        ax.scatter(clipped_coefs, y_pos, c=colors, s=80, zorder=5, edgecolors='black', linewidths=0.5)
        ax.axvline(x=0, color='black', linestyle='--', linewidth=0.8, alpha=0.5)

        if max_abs_display is not None:
            if left_truncated.any():
                ax.scatter(np.full(left_truncated.sum(), -max_abs_display),
                           y_pos[left_truncated], marker='<', c='grey', s=40, zorder=6)
            if right_truncated.any():
                ax.scatter(np.full(right_truncated.sum(), max_abs_display),
                           y_pos[right_truncated], marker='>', c='grey', s=40, zorder=6)
            n_truncated = int(left_truncated.sum() + right_truncated.sum())
            if n_truncated > 0:
                ax.text(0.02, 0.96,
                        f'{n_truncated} CI bound(s) truncated at ±{max_abs_display:g}',
                        transform=ax.transAxes, ha='left', va='top',
                        fontsize=8, color='#555555',
                        bbox={'facecolor': 'white', 'edgecolor': 'none', 'alpha': 0.8, 'pad': 1.5})
            ax.set_xlim(-max_abs_display, max_abs_display)

        # Labels
        labels = plot_df['Variable'].apply(
            lambda v: v.replace('Climate_Class_', 'Climate: ')
                       .replace('Geology_Class_', 'Geology: ')
                       .replace('Elevation_Class_', 'Elevation: ')
                       .replace('Landcover_Class_', 'Landcover: ')
        ).values
        ax.set_yticks(range(n_panel))
        ax.set_yticklabels(labels, fontsize=9)
        ax.set_xlabel('Coefficient (β)', fontsize=11)
        ax.set_title(period_label, fontsize=12, fontweight='bold')
        ax.grid(axis='x', alpha=0.3)
        ax.invert_yaxis()

    # ── Legend for colour coding ──
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker='o', color='w', markerfacecolor='#d73027',
               markeredgecolor='black', markersize=8, label='Significant positive (β > 0)'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='#4575b4',
               markeredgecolor='black', markersize=8, label='Significant negative (β < 0)'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='#999999',
               markeredgecolor='black', markersize=8, label='Not significant'),
    ]
    fig.legend(handles=legend_elements, loc='lower center', ncol=3,
              fontsize=9, frameon=True, fancybox=True, shadow=False,
              bbox_to_anchor=(0.5, -0.02))

    fig.suptitle(title, fontsize=13, fontweight='bold')
    plt.tight_layout(rect=[0, 0.06, 1, 0.95])

    if output_path:
        output_path = Path(output_path)
        _export_figure_all_formats(fig, output_path, dpi=dpi)
        print(f"    ✓ Saved: {output_path.name} + .svg + .pdf")

    if not show:
        plt.close(fig)

    return fig


# =========================================================================
# SKEWNESS DIAGNOSTIC PLOT  (Day | Night panel, normal overlay, black bars)
# =========================================================================

def plot_skewness_diagnostic(
    day_series: pd.Series,
    night_series: pd.Series,
    variable_name: str = 'area_km2',
    output_path: Optional[Path] = None,
    figsize: Tuple[float, float] = (14, 10),
    dpi: int = 300,
    show: bool = True,
) -> Tuple[plt.Figure, Dict]:
    """
    Plot raw vs log-transformed distribution for Day and Night (2×2 panel)
    with normal distribution overlay and black bars.

    Parameters
    ----------
    day_series : pd.Series
        Raw DV values for Day period.
    night_series : pd.Series
        Raw DV values for Night period.
    variable_name : str
        Display name for the variable.
    output_path : Path, optional
        Save path.
    figsize : tuple
        Figure size.
    dpi : int
        Resolution.
    show : bool
        Display figure.

    Returns
    -------
    tuple
        (fig, stats_dict)
        stats_dict has keys: 'day_raw_skew', 'day_log_skew',
                              'night_raw_skew', 'night_log_skew'
    """
    fig, axes = plt.subplots(2, 2, figsize=figsize)
    stats = {}

    for row_idx, (series, period) in enumerate([(day_series, 'Day'), (night_series, 'Night')]):
        raw = series.dropna()
        log_vals = np.log(raw[raw > 0])

        raw_skew = raw.skew()
        log_skew = log_vals.skew()
        stats[f'{period.lower()}_raw_skew'] = raw_skew
        stats[f'{period.lower()}_log_skew'] = log_skew

        # ── Left: Raw distribution ──────────────────
        ax1 = axes[row_idx, 0]
        _counts, _bin_edges, _ = ax1.hist(raw, bins=30, color='black',
                                         edgecolor='white', alpha=0.75,
                                         density=True, label='Observed')

        # Normal distribution overlay
        x_range = np.linspace(raw.min(), raw.max(), 200)
        norm_pdf = scipy_stats.norm.pdf(x_range, loc=raw.mean(), scale=raw.std())
        ax1.plot(x_range, norm_pdf, 'r-', linewidth=2, label='Normal distribution')

        ax1.axvline(raw.mean(), color='red', linestyle='--', linewidth=1, alpha=0.7)
        ax1.axvline(raw.median(), color='orange', linestyle='--', linewidth=1, alpha=0.7)
        ax1.set_title(f'{period} — Raw {variable_name}\nSkewness = {raw_skew:.2f}',
                       fontsize=11, fontweight='bold')
        ax1.set_xlabel(variable_name, fontsize=10)
        ax1.set_ylabel('Density', fontsize=10)
        ax1.legend(fontsize=8)
        ax1.grid(axis='y', alpha=0.3)

        # ── Right: Log-transformed ──────────────────
        ax2 = axes[row_idx, 1]
        _counts_log, _bin_edges_log, _ = ax2.hist(log_vals, bins=30, color='black',
                                                  edgecolor='white', alpha=0.75,
                                                  density=True, label='Observed')

        # Normal distribution overlay
        x_range_log = np.linspace(log_vals.min(), log_vals.max(), 200)
        norm_pdf_log = scipy_stats.norm.pdf(x_range_log, loc=log_vals.mean(),
                                              scale=log_vals.std())
        ax2.plot(x_range_log, norm_pdf_log, 'r-', linewidth=2, label='Normal distribution')

        ax2.axvline(log_vals.mean(), color='red', linestyle='--', linewidth=1, alpha=0.7)
        ax2.axvline(log_vals.median(), color='orange', linestyle='--', linewidth=1, alpha=0.7)
        ax2.set_title(f'{period} — log({variable_name})\nSkewness = {log_skew:.2f}',
                       fontsize=11, fontweight='bold')
        ax2.set_xlabel(f'log({variable_name})', fontsize=10)
        ax2.set_ylabel('Density', fontsize=10)
        ax2.legend(fontsize=8)
        ax2.grid(axis='y', alpha=0.3)

    fig.suptitle('Skewness Diagnostic — Justification for Log-Transform (Day | Night)',
                 fontsize=14, fontweight='bold')
    plt.tight_layout(rect=[0, 0, 1, 0.96])

    if output_path:
        output_path = Path(output_path)
        _export_figure_all_formats(fig, output_path, dpi=dpi)
        print(f"    ✓ Saved: {output_path.name} + .svg + .pdf")

    if not show:
        plt.close(fig)

    return fig, stats


# =========================================================================
# EXPORT HELPERS
# =========================================================================

def save_model_metadata(
    output_dir: Path,
    analysis_name: str,
    period: str,
    comparison_df: pd.DataFrame,
    block_tests: List[Dict],
    config_dict: Dict,
) -> Path:
    """
    Save model metadata to JSON.

    Parameters
    ----------
    output_dir : Path
        Output directory.
    analysis_name : str
        e.g. ``'analysis1_logistic'`` or ``'analysis2_ols'``.
    period : str
        ``'Day'`` or ``'Night'``.
    comparison_df : pd.DataFrame
        Model comparison table.
    block_tests : list[dict]
        Block-level significance tests.
    config_dict : dict
        Configuration parameters used.

    Returns
    -------
    Path
        Path to saved JSON file.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        'analysis': analysis_name,
        'period': period,
        'timestamp': pd.Timestamp.now().isoformat(),
        'model_comparison': comparison_df.to_dict(orient='records'),
        'block_tests': block_tests,
        'config': {k: str(v) if isinstance(v, Path) else v for k, v in config_dict.items()},
    }

    filepath = output_dir / f'{analysis_name}_{period.lower()}_metadata.json'
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, default=str)
    print(f"    ✓ Metadata saved: {filepath.name}")
    return filepath
