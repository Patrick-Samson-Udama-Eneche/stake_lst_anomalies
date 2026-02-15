"""
Decision Tree Event Selection Module

Hierarchical approach prioritizing MODIS validation with ERA5-Land gap-filling.
This module implements a 5-step decision tree for selecting optimal heat events
for high-resolution SEVIRI LST analysis.

Decision Tree Steps:
1. Direct MODIS-ERA5 overlap (longest duration)
2. Extended MODIS search (±1 day)
3. Hottest single day/night overlap
4. Extended hottest day search (±1 day)
5. ERA5-only fallback

Author: Heat Stress Analysis Team
Date: 2024
"""

from datetime import datetime, timedelta
import pandas as pd
import json
import os
import glob


def check_event_overlap(event1_start, event1_end, event2_start, event2_end):
    """
    Check if two events overlap and return overlap details
    
    Parameters:
    -----------
    event1_start : str or datetime.date
        Start date of first event
    event1_end : str or datetime.date
        End date of first event
    event2_start : str or datetime.date
        Start date of second event
    event2_end : str or datetime.date
        End date of second event
    
    Returns:
    --------
    tuple : (overlap_exists, overlap_days, union_start, union_end)
        - overlap_exists: Boolean indicating if events overlap
        - overlap_days: Number of overlapping days
        - union_start: Start of combined period
        - union_end: End of combined period
    """
    # Convert to datetime objects if strings
    if isinstance(event1_start, str):
        event1_start = pd.to_datetime(event1_start).date()
    if isinstance(event1_end, str):
        event1_end = pd.to_datetime(event1_end).date()
    if isinstance(event2_start, str):
        event2_start = pd.to_datetime(event2_start).date()
    if isinstance(event2_end, str):
        event2_end = pd.to_datetime(event2_end).date()
    
    # Check for overlap
    latest_start = max(event1_start, event2_start)
    earliest_end = min(event1_end, event2_end)
    
    overlap_exists = latest_start <= earliest_end
    overlap_days = (earliest_end - latest_start).days + 1 if overlap_exists else 0
    
    # Union period
    union_start = min(event1_start, event2_start)
    union_end = max(event1_end, event2_end)
    
    return overlap_exists, overlap_days, union_start, union_end


def extend_event_period(start_date, end_date, extension_days=1):
    """
    Extend an event period by specified days before and after
    
    Parameters:
    -----------
    start_date : str or datetime.date
        Start date of event
    end_date : str or datetime.date
        End date of event
    extension_days : int, default=1
        Number of days to extend before and after the event
    
    Returns:
    --------
    tuple : (extended_start, extended_end)
        Extended event period dates
    """
    if isinstance(start_date, str):
        start_date = pd.to_datetime(start_date).date()
    if isinstance(end_date, str):
        end_date = pd.to_datetime(end_date).date()
    
    extended_start = start_date - timedelta(days=extension_days)
    extended_end = end_date + timedelta(days=extension_days)
    
    return extended_start, extended_end


def apply_decision_steps(period_type, modis_events, era5_events, modis_hottest, city_name):
    """
    Apply duration-priority decision logic for event selection
    
    STRATEGY: Duration Paramount (Option 1)
    1. Select longest ERA5-Land event (ALWAYS - continuous coverage, no cloud gaps)
    2. Check MODIS validation level (for documentation/transparency):
       - Full: MODIS persistent event overlaps → Quality: EXCELLENT
       - Partial: MODIS hot day/night overlaps → Quality: GOOD
       - None: No MODIS data available → Quality: FAIR
    3. Use longest ERA5 event regardless of validation level
    4. Document validation in metadata for scientific transparency
    
    Rationale:
    - Heat stress is cumulative (longer duration = greater health impact)
    - ERA5-Land is reliable and continuous (assimilated multi-source data)
    - MODIS cloud gaps common in tropical cities (shouldn't penalize selection)
    - Longer events = more SEVIRI timestamps = better cloud gap filling
    
    Parameters:
    -----------
    period_type : str
        'day' or 'night'
    modis_events : list
        List of MODIS persistent events
    era5_events : list
        List of ERA5-Land persistent events
    modis_hottest : dict or None
        MODIS hottest single day/night event
    city_name : str
        Name of city being processed
    
    Returns:
    --------
    dict : {
        'selected_event': Event details dict or None,
        'decision_log': Decision tree tracking information
    }
    """
    
    decision_log = {
        'strategy': 'duration_priority',
        'steps_attempted': [],
        'alternatives_considered': [],
        'final_decision_stage': None,
        'quality_flag': None,
        'rationale': None
    }
    
    selected_event = None
    
    # CORE LOGIC: Duration Paramount (Option 1)
    print(f"    {period_type.upper()} - Duration Priority: Selecting longest ERA5-Land event...")
    decision_log['steps_attempted'].append('Duration_Priority_Selection')
    
    if not era5_events:
        decision_log['final_decision_stage'] = 'No_ERA5_Events'
        decision_log['quality_flag'] = 'N/A'
        decision_log['rationale'] = f"No ERA5-Land persistent {period_type} events found for {city_name}"
        print(f"        ❌ No ERA5-Land events available")
        return {'selected_event': None, 'decision_log': decision_log}
    
    # Step 1: Select LONGEST ERA5-Land event (ALWAYS)
    longest_era5 = max(era5_events, key=lambda x: x['duration'])
    print(f"        ✅ Longest ERA5-Land event: {longest_era5['duration']} days ({longest_era5['start_date']} to {longest_era5['end_date']})")
    
    # Step 2: Check MODIS validation level (for documentation only - doesn't affect selection)
    validation_level = 'none'
    validation_event = None
    validation_details = None
    
    # Check 1: Direct MODIS persistent event overlap (EXCELLENT validation)
    if modis_events:
        print(f"        Checking MODIS persistent events for validation...")
        for modis_event in modis_events:
            overlap_exists, overlap_days, union_start, union_end = check_event_overlap(
                modis_event['start_date'], modis_event['end_date'],
                longest_era5['start_date'], longest_era5['end_date']
            )
            
            if overlap_exists:
                validation_level = 'excellent'
                validation_event = modis_event
                validation_details = {
                    'overlap_days': overlap_days,
                    'modis_duration': modis_event['duration'],
                    'validation_type': 'direct_persistent_overlap'
                }
                print(f"           ✓ Excellent validation: MODIS persistent event overlaps ({modis_event['duration']} days, {overlap_days} days overlap)")
                break
    
    # Check 2: MODIS hottest single day/night overlap (GOOD validation)
    if validation_level == 'none' and modis_hottest:
        print(f"        Checking MODIS hottest {period_type} for validation...")
        overlap_exists, overlap_days, union_start, union_end = check_event_overlap(
            modis_hottest['start_date'], modis_hottest['end_date'],
            longest_era5['start_date'], longest_era5['end_date']
        )
        
        if overlap_exists:
            validation_level = 'good'
            validation_event = modis_hottest
            validation_details = {
                'overlap_days': overlap_days,
                'validation_type': 'hottest_single_overlap'
            }
            print(f"           ✓ Good validation: MODIS hottest {period_type} overlaps")
    
    if validation_level == 'none':
        print(f"           ○ Fair validation: No MODIS validation available (cloud gaps or data limitations)")
    
    # Step 3: Assign quality flag based on validation level
    quality_map = {
        'excellent': 'Excellent',
        'good': 'Good',
        'none': 'Fair'
    }
    quality_flag = quality_map[validation_level]
    
    # Step 4: Create selected event (ALWAYS longest ERA5, regardless of validation)
    selected_event = {
        'source': 'ERA5_duration_priority',
        'primary_event': longest_era5,
        'validation_event': validation_event,
        'validation_level': validation_level,
        'overlap_details': validation_details,
        'period_used': {
            'start_date': longest_era5['start_date'],
            'end_date': longest_era5['end_date'],
            'duration': longest_era5['duration']
        }
    }
    
    decision_log['final_decision_stage'] = 'Duration_Priority_Selection'
    decision_log['quality_flag'] = quality_flag
    decision_log['validation_level'] = validation_level
    
    # Construct rationale
    if validation_level == 'excellent':
        decision_log['rationale'] = f"Longest ERA5-Land event ({longest_era5['duration']} days) selected. Quality: {quality_flag} - MODIS persistent event validation confirmed"
    elif validation_level == 'good':
        decision_log['rationale'] = f"Longest ERA5-Land event ({longest_era5['duration']} days) selected. Quality: {quality_flag} - MODIS hottest {period_type} validation available"
    else:
        decision_log['rationale'] = f"Longest ERA5-Land event ({longest_era5['duration']} days) selected. Quality: {quality_flag} - No MODIS validation available (cloud gaps or data limitations)"
    
    # Document alternatives considered (other ERA5 events not selected)
    decision_log['alternatives_considered'] = [e for e in era5_events if e != longest_era5]
    
    print(f"        ✅ Selected: {longest_era5['duration']} days | Quality: {quality_flag}")
    return {'selected_event': selected_event, 'decision_log': decision_log}


def apply_decision_tree_logic(city_name, stats):
    """
    Apply the refined decision tree logic to select optimal events
    
    This function implements a hierarchical 5-step decision tree that prioritizes
    MODIS satellite observations (ground truth) for validation while using ERA5-Land
    for gap-filling and extended temporal coverage.
    
    Parameters:
    -----------
    city_name : str
        Name of the city being analyzed
    stats : dict
        Comprehensive LST statistics from temporal analysis containing:
        - 'modis': MODIS Aqua statistics (if available)
        - 'era5_land': ERA5-Land statistics (if available)
        - Each dataset includes heat events and extreme temperatures
    
    Returns:
    --------
    dict : {
        'city': City name,
        'processing_date': Timestamp of analysis,
        'datasets_available': List of available datasets,
        'selected_events': {
            'day': Selected daytime event details,
            'night': Selected nighttime event details
        },
        'decision_log': {
            'day': Decision tree log for day,
            'night': Decision tree log for night
        }
    }
    
    Decision Tree Steps:
    --------------------
    1. Direct MODIS-ERA5 overlap (longest duration) - FULLY VALIDATED
    2. Extended MODIS search (±1 day) - PARTIALLY VALIDATED
    3. Hottest single day/night overlap - PARTIALLY VALIDATED
    4. Extended hottest day search (±1 day) - PARTIALLY VALIDATED
    5. ERA5-only fallback - UNVALIDATED
    """
    
    results = {
        'city': city_name,
        'processing_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'datasets_available': stats.get('datasets_available', []),
        'selected_events': {},
        'decision_log': {}
    }
    
    # Extract events from datasets
    modis_day_events = []
    modis_night_events = []
    era5_day_events = []
    era5_night_events = []
    
    # Get MODIS hottest days for fallback
    modis_hottest_day = None
    modis_hottest_night = None
    
    if 'modis' in stats:
        modis_stats = stats['modis']
        modis_day_events = modis_stats['heat_events']['persistent_events']['persistent_hot_days']
        modis_night_events = modis_stats['heat_events']['persistent_events']['persistent_hot_nights']
        
        # Get hottest single days for fallback
        if modis_stats['extreme_temperatures']['date_highest_day']:
            hottest_date = modis_stats['extreme_temperatures']['date_highest_day']
            modis_hottest_day = {
                'start_date': hottest_date,
                'end_date': hottest_date,
                'duration': 1,
                'max_temperature': modis_stats['extreme_temperatures']['highest_day_median'],
                'event_type': 'hottest_single_day'
            }
        
        if modis_stats['extreme_temperatures']['date_highest_night']:
            hottest_date = modis_stats['extreme_temperatures']['date_highest_night']
            modis_hottest_night = {
                'start_date': hottest_date,
                'end_date': hottest_date,
                'duration': 1,
                'max_temperature': modis_stats['extreme_temperatures']['highest_night_median'],
                'event_type': 'hottest_single_night'
            }
    
    if 'era5_land' in stats:
        era5_stats = stats['era5_land']
        era5_day_events = era5_stats['heat_events']['persistent_events']['persistent_hot_days']
        era5_night_events = era5_stats['heat_events']['persistent_events']['persistent_hot_nights']
    
    # Process day and night separately
    for period_type, modis_events, era5_events, modis_hottest in [
        ('day', modis_day_events, era5_day_events, modis_hottest_day),
        ('night', modis_night_events, era5_night_events, modis_hottest_night)
    ]:
        
        selection_result = apply_decision_steps(
            period_type, modis_events, era5_events, modis_hottest, city_name
        )
        
        results['selected_events'][period_type] = selection_result['selected_event']
        results['decision_log'][period_type] = selection_result['decision_log']
    
    return results


def process_all_cities_with_decision_tree(output_dir, study_year):
    """
    Apply decision tree logic to all cities and generate comprehensive results
    
    Parameters:
    -----------
    output_dir : str
        Path to directory containing city analysis files
    study_year : int or str
        Year of analysis
    
    Returns:
    --------
    tuple : (all_results, results_file)
        - all_results: List of decision tree results for all cities
        - results_file: Path to saved JSON results file
    """
    print("APPLYING REFINED DECISION TREE TO ALL CITIES")
    print("=" * 60)
    
    # Find all analysis files (check both Data and Daily_LST subdirectories)
    pattern1 = os.path.join(output_dir, "City_*", "Data", f"*_comprehensive_LST_statistics_{study_year}.json")
    pattern2 = os.path.join(output_dir, "City_*", "Daily_LST", f"*_comprehensive_LST_statistics_{study_year}.json")
    json_files = glob.glob(pattern1) + glob.glob(pattern2)
    
    if not json_files:
        print(f"No analysis files found!")
        print(f"  Searched pattern 1: {pattern1}")
        print(f"  Searched pattern 2: {pattern2}")
        return None, None
    
    print(f"Processing {len(json_files)} cities...")
    
    all_results = []
    
    for json_file in json_files:
        try:
            city_name = os.path.basename(json_file).split('_comprehensive_LST_statistics_')[0]
            
            print(f"\n--- Processing {city_name} ---")
            
            with open(json_file, 'r') as f:
                stats = json.load(f)
            
            # Apply decision tree logic
            city_result = apply_decision_tree_logic(city_name, stats)
            all_results.append(city_result)
            
            # Print summary for this city
            for period in ['day', 'night']:
                if city_result['selected_events'][period]:
                    event = city_result['selected_events'][period]
                    decision = city_result['decision_log'][period]
                    
                    print(f"  {period.upper()}: {decision['final_decision_stage']} | {decision['quality_flag']}")
                    if event['period_used']:
                        period_info = event['period_used']
                        print(f"    Period: {period_info['start_date']} to {period_info['end_date']} ({period_info['duration']} days)")
                        print(f"    Source: {event['source']}")
                else:
                    print(f"  {period.upper()}: No event selected")
            
        except Exception as e:
            print(f"Error processing {city_name}: {e}")
    
    # Save results
    results_file = os.path.join(output_dir, f'decision_tree_selections_{study_year}.json')
    with open(results_file, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    
    print(f"\nDecision tree results saved to: {results_file}")
    
    # Create summary table
    create_decision_tree_summary_table(all_results, output_dir, study_year)
    
    return all_results, results_file


def create_decision_tree_summary_table(all_results, output_dir, study_year):
    """
    Create summary table showing decision tree outcomes for all cities
    
    Parameters:
    -----------
    all_results : list
        List of decision tree results from process_all_cities_with_decision_tree
    output_dir : str
        Path to directory for saving summary table
    study_year : int or str
        Year of analysis
    
    Returns:
    --------
    str : Path to saved summary CSV file
    """
    summary_data = []
    
    for result in all_results:
        city = result['city']
        
        for period in ['day', 'night']:
            if result['selected_events'][period]:
                event = result['selected_events'][period]
                decision = result['decision_log'][period]
                period_info = event['period_used']
                
                summary_data.append({
                    'city': city,
                    'period': period,
                    'decision_stage': decision['final_decision_stage'],
                    'quality_flag': decision['quality_flag'],
                    'source': event['source'],
                    'start_date': period_info['start_date'],
                    'end_date': period_info['end_date'],
                    'duration_days': period_info['duration'],
                    'rationale': decision['rationale'],
                    'alternatives_count': len(decision.get('alternatives_considered', [])),
                    'datasets_available': ', '.join(result['datasets_available'])
                })
            else:
                summary_data.append({
                    'city': city,
                    'period': period,
                    'decision_stage': 'No_Events_Found',
                    'quality_flag': 'No_Data',
                    'source': 'None',
                    'start_date': None,
                    'end_date': None,
                    'duration_days': 0,
                    'rationale': 'No events found',
                    'alternatives_count': 0,
                    'datasets_available': ', '.join(result['datasets_available'])
                })
    
    # Create DataFrame and save
    summary_df = pd.DataFrame(summary_data)
    summary_df = summary_df.sort_values(['city', 'period'])
    
    summary_path = os.path.join(output_dir, f'decision_tree_summary_{study_year}.csv')
    summary_df.to_csv(summary_path, index=False)
    
    print(f"Summary table saved to: {summary_path}")
    
    # Print statistics
    print(f"\nDECISION TREE STATISTICS:")
    stage_counts = summary_df['decision_stage'].value_counts()
    for stage, count in stage_counts.items():
        print(f"  {stage}: {count} cases")
    
    quality_counts = summary_df['quality_flag'].value_counts()
    print(f"\nQUALITY FLAG DISTRIBUTION:")
    for quality, count in quality_counts.items():
        print(f"  {quality}: {count} cases")
    
    return summary_path
