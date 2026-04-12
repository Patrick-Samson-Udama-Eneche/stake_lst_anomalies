"""
Temporal Analysis Utilities
============================

Functions for LST temporal analysis including trend calculations,
statistical aggregations, and warming rate computations.
"""

import numpy as np
import pandas as pd
from scipy import stats


def calculate_warming_rates(years, temperatures):
    """
    Calculate warming/cooling rates using linear regression.
    
    Parameters:
    -----------
    years : array-like
        Years for the analysis
    temperatures : array-like
        Temperature values
        
    Returns:
    --------
    dict
        Dictionary containing slope, intercept, r_value, p_value, std_err,
        rate_per_decade, rate_total
    """
    # Perform linear regression
    slope, intercept, r_value, p_value, std_err = stats.linregress(years, temperatures)
    
    # Calculate rates
    rate_per_decade = slope * 10
    rate_total = slope * (years[-1] - years[0])
    
    return {
        'slope': slope,
        'intercept': intercept,
        'r_value': r_value,
        'r_squared': r_value ** 2,
        'p_value': p_value,
        'std_err': std_err,
        'rate_per_decade': rate_per_decade,
        'rate_total': rate_total,
        'is_significant': p_value < 0.05
    }


def compute_monthly_climatology(df, temp_column='LST', month_column='month'):
    """
    Compute monthly climatology from daily/sub-monthly data.
    
    Parameters:
    -----------
    df : pd.DataFrame
        DataFrame with temperature data
    temp_column : str
        Name of temperature column
    month_column : str
        Name of month column
        
    Returns:
    --------
    pd.DataFrame
        Monthly climatology statistics
    """
    monthly_stats = df.groupby(month_column)[temp_column].agg([
        ('median', 'median'),
        ('mean', 'mean'),
        ('min', 'min'),
        ('max', 'max'),
        ('std', 'std'),
        ('count', 'count')
    ]).reset_index()
    
    return monthly_stats


def compute_yearly_aggregates(df, temp_column='LST', year_column='year'):
    """
    Compute yearly aggregate statistics.
    
    Parameters:
    -----------
    df : pd.DataFrame
        DataFrame with temperature data
    temp_column : str
        Name of temperature column
    year_column : str
        Name of year column
        
    Returns:
    --------
    pd.DataFrame
        Yearly statistics
    """
    yearly_stats = df.groupby(year_column)[temp_column].agg([
        ('median', 'median'),
        ('mean', 'mean'),
        ('min', 'min'),
        ('max', 'max'),
        ('std', 'std'),
        ('count', 'count')
    ]).reset_index()
    
    return yearly_stats


def create_heatmap_data(city_data_dict, time_dim='year', stat='median'):
    """
    Create a matrix for heatmap visualization across cities and time.
    
    Parameters:
    -----------
    city_data_dict : dict
        Dictionary with city names as keys and dataframes as values
    time_dim : str
        Time dimension: 'year' or 'month'
    stat : str
        Statistic to use: 'median', 'mean', 'min', 'max'
        
    Returns:
    --------
    pd.DataFrame
        Matrix with cities as rows and time periods as columns
    """
    heatmap_data = {}
    
    for city_name, df in city_data_dict.items():
        if time_dim in df.columns and stat in df.columns:
            # Pivot to get time as index
            city_series = df.set_index(time_dim)[stat]
            heatmap_data[city_name] = city_series
    
    # Combine into DataFrame
    heatmap_df = pd.DataFrame(heatmap_data).T
    
    return heatmap_df


def summarize_lst_statistics(yearly_data, monthly_data, city_name, lst_time):
    """
    Create a comprehensive summary of LST statistics.
    
    Parameters:
    -----------
    yearly_data : pd.DataFrame
        Yearly aggregated data
    monthly_data : pd.DataFrame
        Monthly climatology data
    city_name : str
        Name of the city
    lst_time : str
        'day' or 'night'
        
    Returns:
    --------
    dict
        Summary statistics
    """
    summary = {
        'city': city_name,
        'lst_time': lst_time,
        'years_analyzed': len(yearly_data),
        'months_analyzed': len(monthly_data)
    }
    
    # Yearly statistics
    if not yearly_data.empty:
        summary['yearly_median_mean'] = yearly_data['median'].mean()
        summary['yearly_median_min'] = yearly_data['median'].min()
        summary['yearly_median_max'] = yearly_data['median'].max()
        summary['yearly_temp_range'] = summary['yearly_median_max'] - summary['yearly_median_min']
        
        # Warming rates
        warming_stats = calculate_warming_rates(
            yearly_data['year'].values,
            yearly_data['median'].values
        )
        summary.update({f'yearly_{k}': v for k, v in warming_stats.items()})
    
    # Monthly statistics
    if not monthly_data.empty:
        summary['monthly_median_mean'] = monthly_data['median'].mean()
        summary['monthly_median_min'] = monthly_data['median'].min()
        summary['monthly_median_max'] = monthly_data['median'].max()
        summary['monthly_amplitude'] = summary['monthly_median_max'] - summary['monthly_median_min']
        summary['monthly_std_mean'] = monthly_data['std'].mean()
    
    return summary


# =============================================================================
# DAILY HEAT EVENT ANALYSIS (Notebook 04)
# =============================================================================

def detect_hot_events(
    df,
    temp_column='lst_mean',
    hot_percentile=90
):
    """
    Detect hot events based on percentile threshold.
    
    Hot events are days where LST exceeds the specified percentile.
    
    Mathematical Formulation:
    -------------------------
    Let T = {T₁, T₂, ..., Tₙ} be the time series of daily LST values
    Let P₉₀ = percentile(T, 90) be the 90th percentile threshold
    
    Hot event on day i: Hᵢ = 1 if Tᵢ ≥ P₉₀, else 0
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with date and temperature columns
    temp_column : str, default='lst_mean'
        Name of temperature column
    hot_percentile : float, default=90
        Percentile threshold (0-100)
        
    Returns
    -------
    df_events : pd.DataFrame
        Original DataFrame with added 'is_hot' boolean column
    threshold : float
        Temperature threshold value (°C)
        
    Example
    -------
    >>> df = pd.read_csv('modis_day_2024.csv')
    >>> df_events, threshold = detect_hot_events(df, hot_percentile=90)
    >>> print(f"Hot days: {df_events['is_hot'].sum()}, Threshold: {threshold:.2f}°C")
    """
    df_copy = df.copy()
    df_copy['date'] = pd.to_datetime(df_copy['date'])
    df_copy = df_copy.sort_values('date').reset_index(drop=True)
    
    # Calculate threshold
    threshold = np.percentile(df_copy[temp_column].dropna(), hot_percentile)
    
    # Identify hot events
    df_copy['is_hot'] = df_copy[temp_column] >= threshold
    
    return df_copy, threshold


def identify_persistent_events(
    df,
    hot_column='is_hot',
    persistent_threshold=2
):
    """
    Identify persistent hot events using run-length encoding.
    
    Persistent events are sequences of consecutive hot days meeting
    the minimum duration threshold.
    
    Mathematical Formulation:
    -------------------------
    Let H = {H₁, H₂, ..., Hₙ} be binary hot event indicator (1=hot, 0=not hot)
    
    Run-length encoding identifies consecutive sequences:
    For sequence starting at index i with duration d:
        Persistent event: d ≥ D_min (minimum duration threshold)
    
    Event ID assignment:
        event_idᵢ = k if day i is part of k-th persistent event
        event_idᵢ = 0 if day i is not part of any persistent event
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with 'is_hot' boolean column (from detect_hot_events)
    hot_column : str, default='is_hot'
        Name of boolean hot event column
    persistent_threshold : int, default=2
        Minimum consecutive days for persistent classification
        
    Returns
    -------
    df_persistent : pd.DataFrame
        Original DataFrame with added columns:
        - 'event_id': Unique identifier for persistent events (0 = non-event)
        - 'event_duration': Duration of persistent event (0 = non-event)
        - 'event_start_date': Start date of event (NaT for non-events)
        - 'event_end_date': End date of event (NaT for non-events)
    stats : dict
        Summary statistics:
        - 'total_hot_days': Total count of hot days
        - 'persistent_events': Count of persistent events
        - 'longest_event': Maximum event duration (days)
        - 'total_persistent_days': Total days in persistent events
        
    Example
    -------
    >>> df_events, threshold = detect_hot_events(df, hot_percentile=90)
    >>> df_persistent, stats = identify_persistent_events(df_events, persistent_threshold=2)
    >>> print(f"Persistent events: {stats['persistent_events']}, Longest: {stats['longest_event']} days")
    """
    df_copy = df.copy()
    df_copy = df_copy.sort_values('date').reset_index(drop=True)
    
    # Initialize tracking columns
    hot_array = df_copy[hot_column].values
    event_ids = []
    event_durations = []
    event_starts = []
    event_ends = []
    
    event_id = 0
    i = 0
    
    while i < len(hot_array):
        if hot_array[i]:
            # Count consecutive hot days
            start_idx = i
            duration = 1
            
            while i + duration < len(hot_array) and hot_array[i + duration]:
                duration += 1
            
            end_idx = i + duration - 1
            
            # Assign event ID if meets threshold
            if duration >= persistent_threshold:
                event_id += 1
                start_date = df_copy.loc[start_idx, 'date']
                end_date = df_copy.loc[end_idx, 'date']
                
                for j in range(duration):
                    event_ids.append(event_id)
                    event_durations.append(duration)
                    event_starts.append(start_date)
                    event_ends.append(end_date)
            else:
                # Not persistent - mark as non-event
                for j in range(duration):
                    event_ids.append(0)
                    event_durations.append(0)
                    event_starts.append(pd.NaT)
                    event_ends.append(pd.NaT)
            
            i += duration
        else:
            # Not a hot day
            event_ids.append(0)
            event_durations.append(0)
            event_starts.append(pd.NaT)
            event_ends.append(pd.NaT)
            i += 1
    
    # Add columns to DataFrame
    df_copy['event_id'] = event_ids
    df_copy['event_duration'] = event_durations
    df_copy['event_start_date'] = event_starts
    df_copy['event_end_date'] = event_ends
    
    # Calculate summary statistics
    stats = {
        'total_hot_days': df_copy[hot_column].sum(),
        'persistent_events': df_copy['event_id'].max() if df_copy['event_id'].max() > 0 else 0,
        'longest_event': df_copy['event_duration'].max(),
        'total_persistent_days': (df_copy['event_id'] > 0).sum()
    }
    
    return df_copy, stats


def compare_datasets(
    df1,
    df2,
    temp_column1='lst_mean',
    temp_column2='lst_mean',
    dataset1_name='Dataset 1',
    dataset2_name='Dataset 2'
):
    """
    Compare two LST datasets using statistical metrics.
    
    Mathematical Formulation:
    -------------------------
    Let T₁ = {T₁₁, T₁₂, ..., T₁ₙ} and T₂ = {T₂₁, T₂₂, ..., T₂ₙ} be two LST time series
    
    Pearson Correlation:
        r = Σ[(T₁ᵢ - μ₁)(T₂ᵢ - μ₂)] / √[Σ(T₁ᵢ - μ₁)² Σ(T₂ᵢ - μ₂)²]
    
    Bias:
        Bias = (1/n) Σ(T₁ᵢ - T₂ᵢ)
    
    Root Mean Square Error:
        RMSE = √[(1/n) Σ(T₁ᵢ - T₂ᵢ)²]
    
    Mean Absolute Error:
        MAE = (1/n) Σ|T₁ᵢ - T₂ᵢ|
    
    Parameters
    ----------
    df1 : pd.DataFrame
        First dataset with 'date' and temperature columns
    df2 : pd.DataFrame
        Second dataset with 'date' and temperature columns
    temp_column1 : str, default='lst_mean'
        Temperature column name in df1
    temp_column2 : str, default='lst_mean'
        Temperature column name in df2
    dataset1_name : str
        Name of first dataset (for labeling)
    dataset2_name : str
        Name of second dataset (for labeling)
        
    Returns
    -------
    dict
        Comparison results:
        - 'merged_data': pd.DataFrame with both datasets merged by date
        - 'correlation': Pearson correlation coefficient
        - 'bias': Mean bias (dataset1 - dataset2)
        - 'rmse': Root mean square error
        - 'mae': Mean absolute error
        - 'n_samples': Number of overlapping observations
        - 'dataset1_name': Name of dataset 1
        - 'dataset2_name': Name of dataset 2
        
    Example
    -------
    >>> df_modis = pd.read_csv('modis_day_2024.csv')
    >>> df_era5 = pd.read_csv('era5_day_2024.csv')
    >>> comparison = compare_datasets(df_modis, df_era5, 
    ...                                dataset1_name='MODIS', dataset2_name='ERA5')
    >>> print(f"Correlation: {comparison['correlation']:.3f}, Bias: {comparison['bias']:.2f}°C")
    """
    # Ensure date columns are datetime
    df1_copy = df1.copy()
    df2_copy = df2.copy()
    df1_copy['date'] = pd.to_datetime(df1_copy['date'])
    df2_copy['date'] = pd.to_datetime(df2_copy['date'])
    
    # Merge datasets on date
    merged = pd.merge(
        df1_copy[['date', temp_column1]],
        df2_copy[['date', temp_column2]],
        on='date',
        suffixes=(f'_{dataset1_name}', f'_{dataset2_name}')
    )
    
    # Remove NaNs
    merged = merged.dropna()
    
    if len(merged) == 0:
        return {
            'merged_data': merged,
            'correlation': None,
            'bias': None,
            'rmse': None,
            'mae': None,
            'n_samples': 0,
            'dataset1_name': dataset1_name,
            'dataset2_name': dataset2_name
        }
    
    # Extract temperature arrays
    t1 = merged[f'{temp_column1}_{dataset1_name}'].values
    t2 = merged[f'{temp_column2}_{dataset2_name}'].values
    
    # Calculate statistics
    correlation = np.corrcoef(t1, t2)[0, 1]
    bias = np.mean(t1 - t2)
    rmse = np.sqrt(np.mean((t1 - t2) ** 2))
    mae = np.mean(np.abs(t1 - t2))
    
    return {
        'merged_data': merged,
        'correlation': correlation,
        'bias': bias,
        'rmse': rmse,
        'mae': mae,
        'n_samples': len(merged),
        'dataset1_name': dataset1_name,
        'dataset2_name': dataset2_name
    }


def summarize_daily_lst_analysis(
    df_day,
    df_night,
    hot_percentile=90,
    persistent_threshold=2
):
    """
    Comprehensive summary of daily LST analysis for day and night.
    
    Parameters
    ----------
    df_day : pd.DataFrame
        Daytime LST data with 'date' and 'lst_mean' columns
    df_night : pd.DataFrame
        Nighttime LST data with 'date' and 'lst_mean' columns
    hot_percentile : float, default=90
        Percentile threshold for hot event detection
    persistent_threshold : int, default=2
        Minimum consecutive days for persistent events
        
    Returns
    -------
    dict
        Comprehensive summary with keys:
        - 'day_stats': Daytime analysis summary
        - 'night_stats': Nighttime analysis summary
        - 'day_events': Daytime persistent events DataFrame
        - 'night_events': Nighttime persistent events DataFrame
        
    Example
    -------
    >>> df_day = pd.read_csv('modis_day_2024.csv')
    >>> df_night = pd.read_csv('modis_night_2024.csv')
    >>> summary = summarize_daily_lst_analysis(df_day, df_night)
    >>> print(summary['day_stats'])
    """
    summary = {}
    
    # Daytime analysis
    df_day_events, day_threshold = detect_hot_events(
        df_day, temp_column='lst_mean', hot_percentile=hot_percentile
    )
    df_day_persistent, day_event_stats = identify_persistent_events(
        df_day_events, persistent_threshold=persistent_threshold
    )
    
    summary['day_stats'] = {
        'threshold': day_threshold,
        'mean_lst': df_day['lst_mean'].mean(),
        'std_lst': df_day['lst_mean'].std(),
        'min_lst': df_day['lst_mean'].min(),
        'max_lst': df_day['lst_mean'].max(),
        **day_event_stats
    }
    summary['day_events'] = df_day_persistent
    
    # Nighttime analysis
    df_night_events, night_threshold = detect_hot_events(
        df_night, temp_column='lst_mean', hot_percentile=hot_percentile
    )
    df_night_persistent, night_event_stats = identify_persistent_events(
        df_night_events, persistent_threshold=persistent_threshold
    )
    
    summary['night_stats'] = {
        'threshold': night_threshold,
        'mean_lst': df_night['lst_mean'].mean(),
        'std_lst': df_night['lst_mean'].std(),
        'min_lst': df_night['lst_mean'].min(),
        'max_lst': df_night['lst_mean'].max(),
        **night_event_stats
    }
    summary['night_events'] = df_night_persistent
    
    # Diurnal range
    merged = pd.merge(
        df_day[['date', 'lst_mean']],
        df_night[['date', 'lst_mean']],
        on='date',
        suffixes=('_day', '_night')
    ).dropna()
    
    if len(merged) > 0:
        merged['diurnal_range'] = merged['lst_mean_day'] - merged['lst_mean_night']
        summary['diurnal_stats'] = {
            'mean_range': merged['diurnal_range'].mean(),
            'std_range': merged['diurnal_range'].std(),
            'min_range': merged['diurnal_range'].min(),
            'max_range': merged['diurnal_range'].max()
        }
    
    return summary

# =============================================================================
# NOTEBOOK 03 — MONTHLY/ANNUAL STATISTICS & TREND CATEGORISATION
# =============================================================================

def compute_lst_statistics_from_files(aoi_data, lst_output_dir,
                                      temporal_config, lst_config):
    """
    Walk every city's GeoTIFF directory and compute per-city, per-year, and
    per-month statistics from already-downloaded LST GeoTIFF files.

    Returns a list of record dicts suitable for ``pd.DataFrame(records)``.
    Each record contains: city, day_night, time_period_type, is_climatology,
    time_period, lst_median, lst_mean, lst_min, lst_max, lst_std, lst_count.

    Parameters
    ----------
    aoi_data : dict
        {city_name: {'city_dir': ...}}
    lst_output_dir : str
        Root output dir for notebook 03
        (e.g. config.get_output_dir('03_trend_analysis_monthly_annual')).
    temporal_config : dict   (config.TEMPORAL_CONFIG)
    lst_config : dict        (config.LST_CONFIG)

    Returns
    -------
    list[dict]
    """
    import glob as _glob
    import re as _re
    import numpy as _np
    try:
        import rasterio as _rio
    except ImportError:
        raise ImportError("rasterio is required for compute_lst_statistics_from_files()")

    records = []

    lst_times = (['day', 'night'] if lst_config['lst_time'] == 'both'
                 else [lst_config['lst_time']])

    for city_name, aoi_info in aoi_data.items():
        city_dir = aoi_info['city_dir']

        for lst_time in lst_times:
            subdir      = 'Day' if lst_time == 'day' else 'Night'
            geotiff_dir = os.path.join(lst_output_dir, city_dir,
                                       'LST_Temporal_Analysis', subdir, 'geotiff')
            if not os.path.isdir(geotiff_dir):
                continue

            # ── Yearly files ─────────────────────────────────────────────
            for fp in sorted(_glob.glob(
                    os.path.join(geotiff_dir,
                                 f"{city_name}_LST_{lst_time.title()}_Yearly_*.tif"))):
                m = _re.search(r'Yearly_(\d{4})', os.path.basename(fp))
                if not m:
                    continue
                year = int(m.group(1))
                try:
                    with _rio.open(fp) as src:
                        data = src.read(1).astype(float)
                        if src.nodata is not None:
                            data[data == src.nodata] = _np.nan
                        data[data < -50] = _np.nan
                        data[data > 70]  = _np.nan
                        valid = data[~_np.isnan(data)]
                        if len(valid) == 0:
                            continue
                        records.append({
                            'city': city_name,
                            'day_night': lst_time,
                            'time_period_type': 'yearly',
                            'is_climatology': False,
                            'time_period': year,
                            'lst_median': float(_np.median(valid)),
                            'lst_mean':   float(_np.mean(valid)),
                            'lst_min':    float(_np.min(valid)),
                            'lst_max':    float(_np.max(valid)),
                            'lst_std':    float(_np.std(valid)),
                            'lst_count':  int(len(valid)),
                        })
                except Exception:
                    continue

            # ── Monthly climatology files ─────────────────────────────────
            for fp in sorted(_glob.glob(
                    os.path.join(geotiff_dir,
                                 f"{city_name}_LST_{lst_time.title()}_MonthlyClimatology_*.tif"))):
                m = _re.search(r'MonthlyClimatology_(\d+)', os.path.basename(fp))
                if not m:
                    continue
                month = int(m.group(1))
                try:
                    with _rio.open(fp) as src:
                        data = src.read(1).astype(float)
                        if src.nodata is not None:
                            data[data == src.nodata] = _np.nan
                        data[data < -50] = _np.nan
                        data[data > 70]  = _np.nan
                        valid = data[~_np.isnan(data)]
                        if len(valid) == 0:
                            continue
                        records.append({
                            'city': city_name,
                            'day_night': lst_time,
                            'time_period_type': 'monthly',
                            'is_climatology': True,
                            'time_period': month,
                            'lst_median': float(_np.median(valid)),
                            'lst_mean':   float(_np.mean(valid)),
                            'lst_min':    float(_np.min(valid)),
                            'lst_max':    float(_np.max(valid)),
                            'lst_std':    float(_np.std(valid)),
                            'lst_count':  int(len(valid)),
                        })
                except Exception:
                    continue

    return records


def build_enhanced_city_summary(all_stats_df, temporal_config, lst_times=None):
    """
    Build the 'City_LST_Enhanced_Summary' table from All_Cities_LST_Statistics.

    Each row = one city × one time period (Day / Night).
    Columns include mean annual LST, hottest/coolest month & year, warming rate,
    trend significance (linear regression + Mann-Kendall).

    Parameters
    ----------
    all_stats_df : pd.DataFrame
        Output of compute_lst_statistics_from_files().
    temporal_config : dict   (config.TEMPORAL_CONFIG)
    lst_times : list[str] or None
        e.g. ['day', 'night']. Defaults to both if None.

    Returns
    -------
    pd.DataFrame
    """
    import numpy as _np
    from scipy import stats as _stats
    try:
        import pymannkendall as _mk
    except ImportError:
        _mk = None

    MONTH_MAP = {1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun',
                 7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'}

    if lst_times is None:
        lst_times = ['day', 'night']

    rows = []
    for city_name in sorted(all_stats_df['city'].unique()):
        for lst_time in lst_times:
            city_df = all_stats_df[
                (all_stats_df['city'] == city_name) &
                (all_stats_df['day_night'] == lst_time)]

            if city_df.empty:
                continue

            # ── Yearly stats ──────────────────────────────────────────────
            yearly_df = city_df[
                (city_df['time_period_type'] == 'yearly') &
                (~city_df['is_climatology'])].copy()
            yearly_df = yearly_df.sort_values('time_period')

            # ── Monthly climatology ───────────────────────────────────────
            monthly_df = city_df[
                (city_df['time_period_type'] == 'monthly') &
                city_df['is_climatology']].copy()
            monthly_df = monthly_df.sort_values('time_period')

            row = {'City': city_name, 'Time': lst_time.capitalize()}

            if not yearly_df.empty:
                years = yearly_df['time_period'].values.astype(int)
                meds  = yearly_df['lst_median'].values

                row['Mean Annual LST (°C)'] = round(float(_np.mean(meds)), 2)
                row['Median LST (°C)']      = round(float(_np.median(meds)), 2)
                row['Overall Min-Max (°C)'] = (f"{yearly_df['lst_min'].min():.1f}–"
                                               f"{yearly_df['lst_max'].max():.1f}")
                row['Std Dev (°C)']         = round(float(_np.std(meds)), 2)

                hot_idx   = int(_np.argmax(meds))
                cool_idx  = int(_np.argmin(meds))
                row['Hottest Year']  = int(years[hot_idx])
                row['Coolest Year']  = int(years[cool_idx])

                # Linear regression (warming rate)
                if len(years) >= 3:
                    sl, ic, rv, pv, se = _stats.linregress(years, meds)
                    rate_text = (f"{sl:.3f}°C/year (R²={rv**2:.2f})")
                    if pv < 0.05:
                        sig_text = (f"p={pv:.3f} (significant at p=0.05 level)\n"
                                    f"Linear: {sl:.4f}°C/year")
                    else:
                        sig_text = (f"p={pv:.3f} (not significant at p=0.05 level)\n"
                                    f"Linear: {sl:.4f}°C/year")
                    # Mann-Kendall
                    if _mk is not None:
                        mk_result = _mk.original_test(meds)
                        mk_dir    = mk_result.trend   # 'increasing', 'decreasing', 'no trend'
                        sig_text += f"\nMann-Kendall: {mk_dir} trend (p={mk_result.p:.3f})"
                    row['Warming Rate']        = rate_text
                    row['Trend Significance']  = sig_text
                else:
                    row['Warming Rate']        = 'Insufficient data'
                    row['Trend Significance']  = 'Insufficient data'

            if not monthly_df.empty:
                months = monthly_df['time_period'].values.astype(int)
                meds_m = monthly_df['lst_median'].values
                hot_m  = months[int(_np.argmax(meds_m))]
                cool_m = months[int(_np.argmin(meds_m))]
                amp    = float(meds_m.max() - meds_m.min())
                row['Hottest Month']   = (f"{MONTH_MAP.get(hot_m, str(hot_m))} "
                                          f"({meds_m.max():.1f}°C)")
                row['Coolest Month']   = (f"{MONTH_MAP.get(cool_m, str(cool_m))} "
                                          f"({meds_m.min():.1f}°C)")
                row['Max Temp Month']  = row['Hottest Month']
                row['Monthly Range (°C)']     = round(amp, 2)
                row['Monthly Amplitude (°C)'] = round(amp, 2)
                row['Seasonal Amplitude (°C)']= round(amp, 2)
            rows.append(row)

    return pd.DataFrame(rows)


def categorise_trend(warming_rate_str, trend_significance_str):
    """
    Classify a city×time trend into one of four categories.

    Parameters
    ----------
    warming_rate_str : str
        Free-text value from 'Warming Rate' column, e.g. '0.048°C/year (R²=0.19)'.
    trend_significance_str : str
        Free-text value from 'Trend Significance' column.

    Returns
    -------
    str
        One of:
        'Significant Warming', 'Significant Cooling',
        'Insignificant Warming', 'No Trend / Insig. Cooling'
    """
    import re as _re

    def _slope(val):
        m = _re.search(r'([-+]\d+\.\d*)\s*°C/year', str(val))
        return float(m.group(1)) if m else 0.0

    def _is_sig(val):
        s = str(val).lower()
        if 'not significant' in s:
            return False
        m = _re.search(r'p\s*=\s*([\d.]+)', s)
        if m:
            return float(m.group(1)) < 0.05
        return ('increasing trend' in s or 'decreasing trend' in s)

    slope  = _slope(warming_rate_str)
    is_sig = _is_sig(trend_significance_str)

    if is_sig and slope > 0:
        return 'Significant Warming'
    elif is_sig and slope < 0:
        return 'Significant Cooling'
    elif (not is_sig) and slope > 0:
        return 'Insignificant Warming'
    else:
        return 'No Trend / Insig. Cooling'