"""
Temporal Analysis Utilities for Daily LST Analysis
===================================================

This module contains utility functions for analyzing daily Land Surface Temperature (LST) data,
including hot event detection, persistent event identification, and cross-dataset comparison.

Functions follow the EXACT protocol from the original notebook 04_temporal_analysis_daily.ipynb
- All calculation formulas preserved exactly as written
- All data structures and JSON formats maintained
- Compatible with visualization and export functions

Author: Modularized from original notebook
Date: 2026-01-29
"""

import os
import json
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path


def fix_json_serialization(obj):
    """
    Convert numpy types to native Python types for JSON serialization
    
    Parameters:
    -----------
    obj : any
        Object to convert (dict, list, numpy types, etc.)
    
    Returns:
    --------
    any
        JSON-serializable object
    """
    if isinstance(obj, dict):
        return {key: fix_json_serialization(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [fix_json_serialization(item) for item in obj]
    elif isinstance(obj, (np.integer, np.int32, np.int64)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float32, np.float64)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif pd.isna(obj):
        return None
    else:
        return obj


def load_dual_datasets(city_name, year, output_dir):
    """
    Load both MODIS and ERA5-Land datasets for a city
    
    Parameters:
    -----------
    city_name : str
        Name of the city
    year : int
        Study year
    output_dir : Path
        Base output directory
    
    Returns:
    --------
    tuple
        (modis_df, era5_df, status)
        - modis_df: pandas DataFrame or None
        - era5_df: pandas DataFrame or None
        - status: str ('both_available', 'modis_only', 'era5_only', 'no_data', 'error')
    """
    try:
        # Define file paths
        city_dir = output_dir / "04_trend_analysis_daily" / f'City_{city_name}' / 'Data'
        modis_file = city_dir / f"{city_name}_raw_daily_MODIS_{year}.csv"
        era5_file = city_dir / f"{city_name}_raw_daily_ERA5_{year}.csv"
        
        modis_df = None
        era5_df = None
        
        # Load MODIS data
        if modis_file.exists():
            modis_df = pd.read_csv(modis_file)
            modis_df['date'] = pd.to_datetime(modis_df['date'])
            modis_df = modis_df.sort_values('date').reset_index(drop=True)
            print(f"        Loaded MODIS: {len(modis_df)} records")
        else:
            print(f"        MODIS file not found: {modis_file}")
        
        # Load ERA5-Land data
        if era5_file.exists():
            era5_df = pd.read_csv(era5_file)
            era5_df['date'] = pd.to_datetime(era5_df['date'])
            era5_df = era5_df.sort_values('date').reset_index(drop=True)
            print(f"        Loaded ERA5-Land: {len(era5_df)} records")
        else:
            print(f"        ERA5-Land file not found: {era5_file}")
        
        # Determine status
        if modis_df is not None and era5_df is not None:
            status = 'both_available'
        elif modis_df is not None:
            status = 'modis_only'
        elif era5_df is not None:
            status = 'era5_only'
        else:
            status = 'no_data'
        
        return modis_df, era5_df, status
        
    except Exception as e:
        print(f"        Error loading datasets: {e}")
        return None, None, 'error'


def calculate_comprehensive_heat_statistics_dual(modis_df, era5_df, city_name, hot_percentile=90, persistent_threshold=2):
    """
    Calculate comprehensive heat statistics for both MODIS and ERA5-Land datasets
    
    Parameters:
    -----------
    modis_df : pandas.DataFrame or None
        MODIS daily LST data
    era5_df : pandas.DataFrame or None
        ERA5-Land daily LST data
    city_name : str
        Name of the city
    hot_percentile : int
        Percentile threshold for hot event detection (default: 90)
    persistent_threshold : int
        Minimum consecutive days for persistent events (default: 2)
    
    Returns:
    --------
    dict
        Comprehensive statistics dictionary containing:
        - datasets_available: list of available datasets
        - modis: MODIS statistics (if available)
        - era5_land: ERA5-Land statistics (if available)
        - longest_persistent_period: cross-dataset longest event
    """
    print(f"    Calculating heat statistics for {city_name} (both datasets)")
    
    results = {
        'city': city_name,
        'analysis_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'datasets_available': []
    }
    
    # Process MODIS data
    if modis_df is not None and len(modis_df) > 0:
        print(f"        Processing MODIS dataset...")
        modis_stats = calculate_single_dataset_statistics(
            modis_df, 'MODIS', hot_percentile, persistent_threshold
        )
        results['modis'] = modis_stats
        results['datasets_available'].append('MODIS')
    
    # Process ERA5-Land data
    if era5_df is not None and len(era5_df) > 0:
        print(f"        Processing ERA5-Land dataset...")
        era5_stats = calculate_single_dataset_statistics(
            era5_df, 'ERA5-Land', hot_percentile, persistent_threshold
        )
        results['era5_land'] = era5_stats
        results['datasets_available'].append('ERA5-Land')
    
    # Find longest persistent period across both datasets
    if len(results['datasets_available']) > 0:
        results['longest_persistent_period'] = find_longest_persistent_period(results)
    
    return results


def calculate_single_dataset_statistics(daily_data, dataset_name, hot_percentile=90, persistent_threshold=2):
    """
    Calculate comprehensive heat statistics for a single dataset
    
    Parameters:
    -----------
    daily_data : pandas.DataFrame
        Daily LST data with columns: date, day_lst_*, night_lst_*
    dataset_name : str
        Name of the dataset ('MODIS' or 'ERA5-Land')
    hot_percentile : int
        Percentile threshold for hot events
    persistent_threshold : int
        Minimum consecutive days for persistent events
    
    Returns:
    --------
    dict
        Comprehensive statistics including:
        - data_coverage
        - temperature_statistics
        - heat_events (thresholds, counts, persistent events)
        - extreme_temperatures
    """
    if len(daily_data) == 0:
        return {}
    
    # Extract valid data for threshold calculations (using median as primary statistic)
    valid_day_data = daily_data['day_lst_median'].dropna()
    valid_night_data = daily_data['night_lst_median'].dropna()
    
    if len(valid_day_data) == 0 and len(valid_night_data) == 0:
        return {}
    
    # Calculate hot temperature thresholds using specified percentile
    day_hot_threshold = valid_day_data.quantile(hot_percentile / 100) if len(valid_day_data) > 0 else np.nan
    night_hot_threshold = valid_night_data.quantile(hot_percentile / 100) if len(valid_night_data) > 0 else np.nan
    
    # Create working copy for event analysis
    daily_data_copy = daily_data.copy()
    daily_data_copy['hot_day'] = daily_data_copy['day_lst_median'] >= day_hot_threshold
    daily_data_copy['hot_night'] = daily_data_copy['night_lst_median'] >= night_hot_threshold
    
    def find_persistent_heat_events(hot_series, data_series, event_type, min_consecutive=persistent_threshold):
        """
        Identify persistent heat events (consecutive days above threshold)
        """
        persistent_events = []
        current_streak = 0
        start_date = None
        max_temp_in_streak = -999
        temperatures_in_streak = []
        
        for i, (date, is_hot, temp) in enumerate(zip(daily_data_copy['date'], hot_series, data_series)):
            if is_hot and not pd.isna(temp):
                if current_streak == 0:
                    start_date = date
                    max_temp_in_streak = temp
                    temperatures_in_streak = [temp]
                else:
                    max_temp_in_streak = max(max_temp_in_streak, temp)
                    temperatures_in_streak.append(temp)
                current_streak += 1
            else:
                if current_streak >= min_consecutive:
                    end_date = daily_data_copy['date'].iloc[i-1]
                    persistent_events.append({
                        'start_date': start_date.strftime('%Y-%m-%d'),
                        'end_date': end_date.strftime('%Y-%m-%d'),
                        'duration': current_streak,
                        'max_temperature': round(max_temp_in_streak, 2),
                        'mean_temperature': round(np.mean(temperatures_in_streak), 2),
                        'event_type': event_type,
                        'dataset': dataset_name
                    })
                current_streak = 0
                temperatures_in_streak = []
        
        # Check for event continuing to end of data series
        if current_streak >= min_consecutive:
            persistent_events.append({
                'start_date': start_date.strftime('%Y-%m-%d'),
                'end_date': daily_data_copy['date'].iloc[-1].strftime('%Y-%m-%d'),
                'duration': current_streak,
                'max_temperature': round(max_temp_in_streak, 2),
                'mean_temperature': round(np.mean(temperatures_in_streak), 2),
                'event_type': event_type,
                'dataset': dataset_name
            })
        
        return persistent_events
    
    # Find persistent heat events for day and night
    persistent_hot_days = find_persistent_heat_events(
        daily_data_copy['hot_day'], daily_data_copy['day_lst_median'], 'hot_day'
    )
    persistent_hot_nights = find_persistent_heat_events(
        daily_data_copy['hot_night'], daily_data_copy['night_lst_median'], 'hot_night'
    )
    
    def calculate_temperature_statistics(data_series):
        """Calculate comprehensive temperature statistics"""
        if data_series.empty:
            return {'min': None, 'max': None, 'mean': None, 'std': None, 'median': None}
        return {
            'min': float(data_series.min()),
            'max': float(data_series.max()),
            'mean': float(data_series.mean()),
            'std': float(data_series.std()),
            'median': float(data_series.median())
        }
    
    # Build comprehensive statistics dictionary
    stats = {
        'dataset': dataset_name,
        'year': daily_data['date'].dt.year.iloc[0] if len(daily_data) > 0 else None,
        'data_coverage': {
            'total_days': len(daily_data),
            'day_coverage_count': valid_day_data.count(),
            'night_coverage_count': valid_night_data.count(),
            'day_coverage_percent': (valid_day_data.count() / len(daily_data)) * 100,
            'night_coverage_percent': (valid_night_data.count() / len(daily_data)) * 100
        },
        'temperature_statistics': {
            'day': {
                'min': calculate_temperature_statistics(daily_data['day_lst_min'].dropna()),
                'median': calculate_temperature_statistics(daily_data['day_lst_median'].dropna()),
                'mean': calculate_temperature_statistics(daily_data['day_lst_mean'].dropna()),
                'max': calculate_temperature_statistics(daily_data['day_lst_max'].dropna())
            },
            'night': {
                'min': calculate_temperature_statistics(daily_data['night_lst_min'].dropna()),
                'median': calculate_temperature_statistics(daily_data['night_lst_median'].dropna()),
                'mean': calculate_temperature_statistics(daily_data['night_lst_mean'].dropna()),
                'max': calculate_temperature_statistics(daily_data['night_lst_max'].dropna())
            }
        },
        'heat_events': {
            'thresholds': {
                'day_hot_threshold': float(day_hot_threshold) if not pd.isna(day_hot_threshold) else None,
                'night_hot_threshold': float(night_hot_threshold) if not pd.isna(night_hot_threshold) else None
            },
            'hot_events_count': {
                'hot_days_count': int((daily_data_copy['hot_day']).sum()),
                'hot_nights_count': int((daily_data_copy['hot_night']).sum())
            },
            'persistent_events': {
                'persistent_hot_days': persistent_hot_days,
                'persistent_hot_nights': persistent_hot_nights,
                'persistent_hot_days_count': len(persistent_hot_days),
                'persistent_hot_nights_count': len(persistent_hot_nights)
            }
        },
        'extreme_temperatures': {
            'highest_day_median': float(daily_data['day_lst_median'].max()) if not daily_data['day_lst_median'].isna().all() else None,
            'highest_night_median': float(daily_data['night_lst_median'].max()) if not daily_data['night_lst_median'].isna().all() else None,
            'date_highest_day': daily_data.loc[daily_data['day_lst_median'].idxmax(), 'date'].strftime('%Y-%m-%d') if not daily_data['day_lst_median'].isna().all() else None,
            'date_highest_night': daily_data.loc[daily_data['night_lst_median'].idxmax(), 'date'].strftime('%Y-%m-%d') if not daily_data['night_lst_median'].isna().all() else None
        }
    }
    
    return stats


def find_longest_persistent_period(combined_results):
    """
    Find the longest persistent hot period across both MODIS and ERA5-Land datasets
    
    Parameters:
    -----------
    combined_results : dict
        Combined results dictionary containing 'modis' and/or 'era5_land' keys
    
    Returns:
    --------
    dict or None
        Dictionary containing:
        - longest_event: dict with event details
        - total_persistent_events: int
        - selection_criteria: str
        Returns None if no persistent events found
    """
    all_persistent_events = []
    
    # Collect all persistent events from both datasets
    for dataset_key in ['modis', 'era5_land']:
        if dataset_key in combined_results:
            dataset_stats = combined_results[dataset_key]
            
            # Add day events
            for event in dataset_stats['heat_events']['persistent_events']['persistent_hot_days']:
                event_copy = event.copy()
                event_copy['period_type'] = 'day'
                all_persistent_events.append(event_copy)
            
            # Add night events  
            for event in dataset_stats['heat_events']['persistent_events']['persistent_hot_nights']:
                event_copy = event.copy()
                event_copy['period_type'] = 'night'
                all_persistent_events.append(event_copy)
    
    if not all_persistent_events:
        return None
    
    # Find the longest duration event
    longest_event = max(all_persistent_events, key=lambda x: x['duration'])
    
    return {
        'longest_event': longest_event,
        'total_persistent_events': len(all_persistent_events),
        'selection_criteria': 'longest_duration'
    }


def save_comprehensive_statistics_json(stats, output_path):
    """
    Save comprehensive statistics to JSON file with proper serialization
    
    Parameters:
    -----------
    stats : dict
        Statistics dictionary from calculate_comprehensive_heat_statistics_dual()
    output_path : Path or str
        Path to save JSON file
    
    Returns:
    --------
    Path
        Path to saved JSON file
    """
    # Fix JSON serialization
    stats_serializable = fix_json_serialization(stats)
    
    # Save to file
    with open(output_path, 'w') as f:
        json.dump(stats_serializable, f, indent=2)
    
    return Path(output_path)
