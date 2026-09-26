"""
Data Input/Output Utilities
===========================

Functions for exporting AOI processing results in various formats.
Maintains city-specific folder structure for organized outputs.
"""

import os
import json
import numpy as np
import pandas as pd
import geopandas as gpd
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.backends.backend_pdf import FigureCanvasPdf

try:
    import config
except ImportError:
    # Fallback configuration
    class Config:
        OUTPUT_DIR = Path("data/outputs")
        WGS84 = "EPSG:4326"
    config = Config()

try:
    import rasterio
    from rasterio.features import rasterize
    RASTERIO_AVAILABLE = True
except ImportError:
    RASTERIO_AVAILABLE = False


def install_backend_safe_savefig(svg_mirror_pdf: bool = False) -> None:
    """Install backend-safe PNG/PDF savefig behavior.

    This avoids inline-backend redirection of PNG/PDF when notebooks run in VS Code.
    Optionally mirrors SVG saves into sibling PDF files.
    """
    # Store/reuse original savefig through dynamic attrs to avoid static member warnings.
    original_figure_savefig = getattr(Figure, '_data_io_original_savefig', Figure.savefig)
    setattr(Figure, '_data_io_original_savefig', original_figure_savefig)

    def _safe_figure_savefig(self, fname, *args, **kwargs):
        target = Path(str(fname))
        suffix = target.suffix.lower().lstrip('.')
        fmt = str(kwargs.get('format', suffix)).lower()

        if fmt == 'png':
            export_kwargs = dict(kwargs)
            export_kwargs['format'] = 'png'
            FigureCanvasAgg(self).print_figure(str(target), **export_kwargs)
            return

        if fmt == 'pdf':
            export_kwargs = dict(kwargs)
            export_kwargs['format'] = 'pdf'
            FigureCanvasPdf(self).print_figure(str(target), **export_kwargs)
            return

        if fmt == 'svg':
            original_figure_savefig(self, str(target), *args, **kwargs)
            if svg_mirror_pdf:
                pdf_target = target.with_suffix('.pdf')
                export_kwargs = dict(kwargs)
                export_kwargs.pop('format', None)
                export_kwargs['format'] = 'pdf'
                FigureCanvasPdf(self).print_figure(str(pdf_target), **export_kwargs)
            return

        return original_figure_savefig(self, str(target), *args, **kwargs)

    def _safe_pyplot_savefig(fname, *args, **kwargs):
        return plt.gcf().savefig(fname, *args, **kwargs)

    Figure.savefig = _safe_figure_savefig
    plt.savefig = _safe_pyplot_savefig
    setattr(Figure, '_data_io_safe_savefig', True)
    setattr(Figure, '_data_io_svg_mirror_pdf', bool(svg_mirror_pdf))


def export_figure_set(
    fig: Figure,
    output_stem: Path,
    dpi: int = 300,
    include_png: bool = True,
    include_svg: bool = True,
    include_pdf: bool = True,
    bbox_inches: str = 'tight',
    facecolor: Optional[str] = None,
    edgecolor: Optional[str] = None,
    **legacy_kwargs,
) -> Dict[str, Path]:
    """Export a figure to PNG (+ optional SVG/PDF) using backend-safe writers."""
    # Backward compatibility for older call sites that use save_* argument names.
    if 'save_png' in legacy_kwargs:
        include_png = bool(legacy_kwargs.pop('save_png'))
    if 'save_svg' in legacy_kwargs:
        include_svg = bool(legacy_kwargs.pop('save_svg'))
    if 'save_pdf' in legacy_kwargs:
        include_pdf = bool(legacy_kwargs.pop('save_pdf'))

    if legacy_kwargs:
        unknown = ', '.join(sorted(legacy_kwargs.keys()))
        raise TypeError(f"Unexpected keyword argument(s): {unknown}")

    output_stem = Path(output_stem)
    if output_stem.suffix:
        output_stem = output_stem.with_suffix('')

    paths = {}
    if include_png:
        paths['png'] = output_stem.with_suffix('.png')
    if include_svg:
        paths['svg'] = output_stem.with_suffix('.svg')
    if include_pdf:
        paths['pdf'] = output_stem.with_suffix('.pdf')

    common_kwargs = {'bbox_inches': bbox_inches}
    if facecolor is not None:
        common_kwargs['facecolor'] = facecolor
    if edgecolor is not None:
        common_kwargs['edgecolor'] = edgecolor

    if include_png:
        FigureCanvasAgg(fig).print_figure(str(paths['png']), dpi=dpi, format='png', **common_kwargs)
    if include_svg:
        fig.savefig(paths['svg'], format='svg', **common_kwargs)
    if include_pdf:
        FigureCanvasPdf(fig).print_figure(str(paths['pdf']), format='pdf', **common_kwargs)

    return paths


def create_city_output_structure(city_name: str, notebook_name: str = "01_aoi_delineation", 
                               base_output_dir: str = None) -> Dict[str, Path]:
    """
    Create standardized output directory structure for a city within a notebook folder.
    """
    if base_output_dir is None:
        # Use absolute path to the project's outputs directory
        project_root = Path.cwd().parent  # Go up from notebooks to project root
        base_output_dir = project_root / "data" / "outputs"
    
    # Create the correct path: stake_lst_modelling/data/outputs/01_aoi_delineation/City_Lagos/
    notebook_dir = Path(base_output_dir) / notebook_name
    city_dir = notebook_dir / f"City_{city_name}"  
    features_dir = city_dir / "Features"
    figures_dir = city_dir / "Figures"
    
    # Create directories if they don't exist
    features_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Created directories:")
    print(f"  Features: {features_dir}")
    print(f"  Figures: {figures_dir}")
    
    return {
        'notebook_dir': notebook_dir,
        'city_dir': city_dir,
        'features_dir': features_dir,
        'figures_dir': figures_dir
    }


def export_spatial_data(aoi_results: Dict[str, Any], city_name: str, 
                       notebook_name: str = "01_aoi_delineation",
                       base_output_dir: str = None) -> Dict[str, str]:
    """
    Export all spatial data as GeoJSON files.
    
    Args:
        aoi_results: Results from process_city_aoi function
        city_name: Name of the city
        notebook_name: Name of the notebook
        base_output_dir: Base output directory (optional)
        
    Returns:
        Dictionary with paths of exported files
    """
    print("Exporting spatial data as GeoJSON...")
    
    # Create output directories
    dirs = create_city_output_structure(city_name, notebook_name, base_output_dir)
    features_dir = dirs['features_dir']
    
    exported_files = {}
    
    # Convert all spatial data to EPSG:4326 for standard GeoJSON
    spatial_data = {
        'Main_Polygon': aoi_results['main_polygon_gdf'],
        'Buffer_Zone': aoi_results['buffer_gdf'],
        'AOI_Boundary': aoi_results['aoi_gdf'],
        'Cities_in_AOI': aoi_results['cities_in_aoi_gdf']
    }
    
    # Add adjacent polygons if they exist
    if not aoi_results['adjacent_gdf'].empty:
        spatial_data['Adjacent_Polygons'] = aoi_results['adjacent_gdf']
    
    # Export each spatial dataset
    for name, gdf in spatial_data.items():
        if not gdf.empty:
            # Convert to WGS84
            if gdf.crs != config.WGS84:
                gdf_export = gdf.to_crs(config.WGS84)
            else:
                gdf_export = gdf.copy()
            
            # Add comprehensive stats to AOI boundary
            if name == 'AOI_Boundary':
                for key, value in aoi_results['comprehensive_stats'].items():
                    gdf_export[key] = value
            
            # Export to GeoJSON in Features folder
            output_path = features_dir / f"{city_name}_{name}.geojson"
            gdf_export.to_file(output_path, driver='GeoJSON')
            exported_files[name] = str(output_path)
            print(f"  Exported {name}: {output_path.name}")
    
    return exported_files


def export_tabular_data(aoi_results: Dict[str, Any], city_name: str,
                       notebook_name: str = "01_aoi_delineation",
                       base_output_dir: str = None) -> Dict[str, str]:
    """
    Export tabular data as CSV and JSON files.
    
    Args:
        aoi_results: Results from process_city_aoi function
        city_name: Name of the city
        notebook_name: Name of the notebook
        base_output_dir: Base output directory (optional)
        
    Returns:
        Dictionary with paths of exported files
    """
    print("Exporting tabular data as CSV and JSON...")
    
    # Create output directories
    dirs = create_city_output_structure(city_name, notebook_name, base_output_dir)
    features_dir = dirs['features_dir']
    
    exported_files = {}
    
    # Export cities statistics if available
    if not aoi_results['cities_in_aoi_df'].empty:
        cities_csv_path = features_dir / f"{city_name}_Cities_Statistics.csv"
        aoi_results['cities_in_aoi_df'].to_csv(cities_csv_path, index=False)
        exported_files['cities_csv'] = str(cities_csv_path)
        print(f"  Exported cities statistics: {cities_csv_path.name}")
    
    # Export comprehensive AOI statistics as CSV
    stats_csv_path = features_dir / f"{city_name}_AOI_Statistics.csv"
    pd.DataFrame([aoi_results['comprehensive_stats']]).to_csv(stats_csv_path, index=False)
    exported_files['stats_csv'] = str(stats_csv_path)
    print(f"  Exported AOI statistics CSV: {stats_csv_path.name}")
    
    # Export comprehensive AOI statistics as JSON
    stats_json_path = features_dir / f"{city_name}_AOI_Statistics.json"
    with open(stats_json_path, 'w') as f:
        json.dump(aoi_results['comprehensive_stats'], f, indent=2, default=str)
    exported_files['stats_json'] = str(stats_json_path)
    print(f"  Exported AOI statistics JSON: {stats_json_path.name}")
    
    return exported_files


def export_processing_summary(aoi_results: Dict[str, Any], city_name: str,
                            export_paths: Dict[str, Any], 
                            notebook_name: str = "01_aoi_delineation",
                            base_output_dir: str = None) -> str:
    """
    Create and export a processing summary report.
    
    Args:
        aoi_results: Results from process_city_aoi function
        city_name: Name of the city
        export_paths: Dictionary with all export paths
        notebook_name: Name of the notebook
        base_output_dir: Base output directory (optional)
        
    Returns:
        Path to the summary report file
    """
    # Create output directories
    dirs = create_city_output_structure(city_name, notebook_name, base_output_dir)
    features_dir = dirs['features_dir']
    
    # Build summary report
    stats = aoi_results['comprehensive_stats']
    metrics = aoi_results['metrics']
    
    summary_content = f"""# AOI Processing Summary Report

## City: {city_name}
**Processing Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Area Statistics
- **AOI Area:** {metrics['aoi_area_km2']:.2f} km²
- **Buffer Area:** {metrics['buffer_area_km2']:.2f} km²
- **Main Urban Polygon:** {metrics['main_area_km2']:.2f} km²
- **Adjacent Polygons:** {metrics['adjacent_area_km2']:.2f} km²
- **Coverage Efficiency:** {metrics['coverage_efficiency']:.1f}%

## Urban Analysis
- **Cities in AOI:** {stats['cities_in_aoi_count']}
- **Adjacent Polygons Count:** {stats['adjacent_polygons_count']}
- **Major Cities:** {stats['AOI_Major_Cities']}

## Population Analysis
- **Total Population 2024:** {stats['total_population_2024']:,.0f}k
- **Population Density:** {stats['population_density_per_km2']:,.0f} people/km²
- **Growth Rate (Pre-2024):** {stats['growth_rate_pre_2024_percent']:.2f}%/year
- **Growth Rate (Post-2024):** {stats['growth_rate_post_2024_percent']:.2f}%/year
- **Overall Growth Rate:** {stats['growth_rate_overall_percent']:.2f}%/year

## Processing Method
- **Method:** {stats['method']}
- **Buffer Distance:** {stats['buffer_distance_km']} km

## Exported Files
"""
    
    # Add exported files to summary
    for category, files in export_paths.items():
        if isinstance(files, dict):
            summary_content += f"\n### {category.replace('_', ' ').title()}\n"
            for name, path in files.items():
                filename = Path(path).name
                summary_content += f"- **{name.replace('_', ' ')}:** {filename}\n"
        elif isinstance(files, str):
            filename = Path(files).name
            summary_content += f"- **{category.replace('_', ' ').title()}:** {filename}\n"
    
    # Save summary report in Features folder
    summary_path = features_dir / f"{city_name}_Processing_Summary.md"
    with open(summary_path, 'w') as f:
        f.write(summary_content)
    
    print(f"  Exported processing summary: {summary_path.name}")
    return str(summary_path)


def export_all_city_data(aoi_results: Dict[str, Any], city_name: str,
                        notebook_name: str = "01_aoi_delineation",
                        base_output_dir: str = None) -> Dict[str, Any]:
    """
    Export all data for a city (spatial, tabular, and summary).
    
    Args:
        aoi_results: Results from process_city_aoi function
        city_name: Name of the city
        notebook_name: Name of the notebook
        base_output_dir: Base output directory (optional)
        
    Returns:
        Dictionary with all export paths and summary
    """
    print(f"Exporting all data for {city_name}...")
    
    # Export spatial data
    spatial_paths = export_spatial_data(aoi_results, city_name, notebook_name, base_output_dir)
    
    # Export tabular data
    tabular_paths = export_tabular_data(aoi_results, city_name, notebook_name, base_output_dir)
    
    # Combine export paths
    all_export_paths = {
        'spatial_data': spatial_paths,
        'tabular_data': tabular_paths
    }
    
    # Export processing summary
    summary_path = export_processing_summary(aoi_results, city_name, all_export_paths, notebook_name, base_output_dir)
    all_export_paths['summary_report'] = summary_path
    
    # Get output directory info
    dirs = create_city_output_structure(city_name, notebook_name, base_output_dir)
    
    print(f"All data exported successfully!")
    print(f"Output directory: {dirs['city_dir']}")
    print(f"Features directory: {dirs['features_dir']}")
    print(f"Figures directory: {dirs['figures_dir']}")
    print(f"Total files exported: {len(spatial_paths) + len(tabular_paths) + 1}")
    
    return {
        'export_paths': all_export_paths,
        'output_directory': str(dirs['city_dir']),
        'features_directory': str(dirs['features_dir']),
        'figures_directory': str(dirs['figures_dir']),
        'total_files': len(spatial_paths) + len(tabular_paths) + 1
    }


def get_city_export_status(city_name: str, base_output_dir: str = None) -> Dict[str, Any]:
    """
    Check the export status for a city.
    
    Args:
        city_name: Name of the city
        base_output_dir: Base output directory (optional)
        
    Returns:
        Dictionary with export status information
    """
    if base_output_dir is None:
        base_output_dir = config.OUTPUT_DIR
    
    city_dir = Path(base_output_dir) / f"City_{city_name}"
    figures_dir = city_dir / "Figures"
    
    status = {
        'city_name': city_name,
        'city_dir_exists': city_dir.exists(),
        'figures_dir_exists': figures_dir.exists(),
        'files': []
    }
    
    if city_dir.exists():
        # List all files in city directory
        for file_path in city_dir.iterdir():
            if file_path.is_file():
                status['files'].append({
                    'name': file_path.name,
                    'size_mb': file_path.stat().st_size / (1024 * 1024),
                    'modified': datetime.fromtimestamp(file_path.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                })
    
    status['total_files'] = len(status['files'])
    
    return status


# ============================================================================
# Stakeholder Analysis Data Functions
# ============================================================================

def load_stakeholder_datasets(config):
    """
    Load all required datasets for stakeholder analysis.

    The target city list is read from NB01's study_cities_final.csv (status ==
    'included'), so the filter automatically reflects whatever selection mode
    (ABOVE_300K, ABOVE_500K, ALL, SPECIFIC …) was active when NB01 was run.
    To change the target set, update config.CITY_SELECTION_MODE and re-run NB01.

    Returns
    -------
    tuple : (boundary_gdf, cities_df, survey_df)
        survey_df is already filtered to target cities and carries a Cluster25
        column (keyed on matched_city_x, the stakeholder's registered city).
    """
    import geopandas as gpd
    import pandas as pd

    # ── Nigeria boundary ────────────────────────────────────────────────────────
    boundary_path = config.get_aoi_data_path('boundary_geojson')
    boundary_gdf = gpd.read_file(boundary_path)
    print(f"✅ Nigeria boundary loaded (CRS: {boundary_gdf.crs})")

    # ── WUP cities population data ──────────────────────────────────────────────
    cities_path = config.get_aoi_data_path('cities_csv')
    if cities_path.suffix.lower() in ('.xlsx', '.xls'):
        cities_df = pd.read_excel(cities_path, sheet_name='Data')
    else:
        cities_df = pd.read_csv(cities_path, thousands=',')
    if 'City_Name' in cities_df.columns:
        cities_df = cities_df.rename(columns={
            'City_Name': 'Urban Agglomeration',
            'PWCent_Latitude': 'Latitude',
            'PWCent_Longitude': 'Longitude',
        })
        cities_df['Urban Agglomeration'] = cities_df['Urban Agglomeration'].str.strip()
    print(f"✅ Cities population data loaded: {len(cities_df)} cities")
    print(f"   Population column: {config.PROJECT_STUDY_YEAR}")

    # ── Target city list from NB01 ──────────────────────────────────────────────
    nb01_dir = config.RESULTS_DIR / '01_aoi_delineation'
    study_cities_path = nb01_dir / 'study_cities_final.csv'
    if not study_cities_path.exists():
        raise FileNotFoundError(
            f"study_cities_final.csv not found at {study_cities_path}. "
            "Run NB01 first to generate the target city list."
        )
    study_cities = pd.read_csv(study_cities_path)
    target_cities = set(
        study_cities.loc[study_cities['status'] == 'included', 'city_name']
    )
    # Absorbed city → parent city remap (e.g. Owerri → Onitsha)
    absorbed_map = dict(zip(
        study_cities.loc[study_cities['status'] == 'absorbed', 'city_name'],
        study_cities.loc[study_cities['status'] == 'absorbed', 'absorbed_by']
    ))
    # Known survey spelling variants → canonical names in study_cities_final.csv
    name_norm_map = {
        'Osogbo': 'Oshogbo',
    }
    # Combined remap: normalise first, then absorb
    full_remap = {**name_norm_map, **absorbed_map}

    print(f"\n📋 Target cities loaded from NB01: {len(target_cities)} cities (status='included')")
    print(f"   Absorbed cities with parent remap: {len(absorbed_map)}")
    print(f"   Survey spelling fixes: {list(name_norm_map.items())}")
    print(f"   ℹ  To change the target set, edit config.CITY_SELECTION_MODE and re-run NB01.")

    # ── Cluster25 lookup (city_name → Cluster25) ────────────────────────────────
    cluster_path = nb01_dir / 'city_cluster25_lookup.csv'
    cluster_lookup = pd.read_csv(cluster_path)[['city_name', 'Cluster25']]

    # ── Raw survey data ─────────────────────────────────────────────────────────
    survey_path = config.INPUT_DIR / 'stakeholder_survey' / 'master_composite.csv'
    survey_raw = pd.read_csv(survey_path)
    n_raw = len(survey_raw)

    # ── Normalise city names and remap absorbed → parent before filtering ────────
    # Handles: spelling variants (Osogbo→Oshogbo) and absorbed cities (Owerri→Onitsha).
    n_remapped_x = survey_raw['matched_city_x'].isin(full_remap).sum()
    n_remapped_y = survey_raw['matched_city_y'].isin(full_remap).sum()
    survey_raw = survey_raw.copy()
    survey_raw['matched_city_x'] = survey_raw['matched_city_x'].replace(full_remap)
    survey_raw['matched_city_y'] = survey_raw['matched_city_y'].replace(full_remap)

    # ── Filter to target cities (based on stakeholder's registered city) ─────────
    # Cohort rule: matched_city_x (REGISTERED city) defines inclusion, not matched_city_y
    # (city of workshop attendance).  Registration is the auditable record of participation;
    # attendance alone cannot be verified for someone who never registered, and there is no
    # per-person attendance register in the project.  One respondent (cal235) marked spots in
    # a study city but has no registration entry, so they are excluded as unverifiable.  This
    # is deliberate and conservative, and fixes the analysed cohort at 105 participants.
    survey_df = survey_raw[survey_raw['matched_city_x'].isin(target_cities)].copy()
    n_kept    = len(survey_df)
    n_dropped = n_raw - n_kept

    # ── Add Cluster25 (registered-city cluster) ─────────────────────────────────
    survey_df = survey_df.merge(
        cluster_lookup.rename(columns={'city_name': 'matched_city_x'}),
        on='matched_city_x', how='left'
    )

    # ── Deduplicate workshop attendance: canonical city = most frequent TARGET city ──
    # Some PIDs attended workshops in multiple cities.  Only target-city appearances
    # count toward the canonical assignment so the canonical is always a study city.
    # PIDs whose workshop records point ONLY to non-target cities are left unchanged
    # and will be excluded naturally when workshop_df is filtered downstream.
    ws_mask = (survey_df['survey status'] == 'Yes') & survey_df['matched_city_y'].notna()
    ws_sub  = survey_df.loc[ws_mask, ['pid', 'matched_city_y']].copy()
    if len(ws_sub) > 0:
        # Restrict frequency table to target-city workshop rows
        ws_tgt = ws_sub[ws_sub['matched_city_y'].isin(target_cities)]
        if len(ws_tgt) > 0:
            freq = (ws_tgt.groupby(['pid', 'matched_city_y'])
                    .size().reset_index(name='cnt'))
            canonical_ws = (freq.sort_values('cnt', ascending=False)
                            .drop_duplicates('pid')
                            .set_index('pid')['matched_city_y'])
            multi_pids = freq.groupby('pid').size()
            multi_pids = multi_pids[multi_pids > 1].index.tolist()
            if multi_pids:
                print(f"\n  Multi-city workshop attendance resolved ({len(multi_pids)} PID(s)):")
                for pid in sorted(multi_pids):
                    cities_cnt = (freq[freq['pid'] == pid]
                                  .set_index('matched_city_y')['cnt'].to_dict())
                    print(f"    {pid}: {cities_cnt} → '{canonical_ws[pid]}'")
            # Update matched_city_y ONLY for PIDs that have at least one target-city workshop;
            # PIDs not in canonical_ws (off-target only) keep their original matched_city_y.
            _new = survey_df.loc[ws_mask, 'pid'].map(canonical_ws)
            _has = _new.notna()
            # Use index labels directly — avoids shape mismatch from boolean-mask alignment
            survey_df.loc[_new[_has].index, 'matched_city_y'] = _new[_has].values
        # Report PIDs whose workshop was only in off-target cities
        _offtgt_ws_pids = set(ws_sub['pid']) - set(ws_tgt['pid']) if len(ws_tgt) > 0 \
                          else set(ws_sub['pid'])
        if _offtgt_ws_pids:
            print(f"\n  PID(s) with workshop ONLY in off-target cities ({len(_offtgt_ws_pids)}):")
            for _p in sorted(_offtgt_ws_pids):
                _cities = sorted(ws_sub.loc[ws_sub['pid'] == _p, 'matched_city_y'].unique())
                print(f"    {_p}: {_cities}  — excluded from workshop analysis")

    # ── Filter report ────────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("STAKEHOLDER DATA FILTER REPORT")
    print(f"{'='*70}")
    print(f"  Raw survey records  : {n_raw}")
    if n_remapped_x > 0 or n_remapped_y > 0:
        print(f"  City name remaps    : {n_remapped_x} matched_city_x  |  "
              f"{n_remapped_y} matched_city_y records")
        _orig = pd.read_csv(survey_path)
        for orig_name, new_name in sorted(full_remap.items()):
            orig_x = (_orig['matched_city_x'] == orig_name).sum()
            if orig_x > 0:
                label = 'spelling' if orig_name in name_norm_map else 'absorbed'
                print(f"    [{label}] {orig_name:<25} → {new_name}  ({orig_x} reg. records)")
    print(f"  Records kept        : {n_kept}  ({n_kept / n_raw * 100:.1f}%)")
    print(f"  Records dropped     : {n_dropped}  (off-target cities)")
    if n_dropped > 0:
        dropped = (survey_raw[~survey_raw['matched_city_x'].isin(target_cities)]
                   .groupby('matched_city_x').size()
                   .sort_values(ascending=False))
        print(f"\n  Off-target cities removed (present in survey but outside current target set):")
        for city, cnt in dropped.items():
            print(f"    {city:<30} {cnt:>4} record(s)")
        print(f"  ℹ  These cities are excluded from all analysis and visualisations.")
        print(f"  ℹ  To include them, change config.CITY_SELECTION_MODE and re-run NB01.")
    print(f"\n  Unique PIDs in filtered data : {survey_df['pid'].nunique()}")
    print(f"  Cities represented           : {survey_df['matched_city_x'].nunique()}")
    print(f"{'='*70}")
    print(f"✅ Stakeholder survey ready: {n_kept} records")

    return boundary_gdf, cities_df, survey_df


def export_stakeholder_outputs(stakeholder_map, cities_gdf, workshop_prof, 
                               output_dir, study_year, figure_dpi=300, donut_fig=None):
    """
    Export stakeholder analysis outputs (maps and data tables).
    
    Parameters:
    -----------
    stakeholder_map : matplotlib.figure.Figure
        The stakeholder distribution map figure
    cities_gdf : GeoDataFrame
        Cities with stakeholder data
    workshop_prof : DataFrame
        Workshop profession breakdown data
    output_dir : Path
        Output directory path
    study_year : int
        Study year for file naming
    figure_dpi : int, optional
        Figure DPI for export (default: 300)
    donut_fig : matplotlib.figure.Figure, optional
        The city classification donut chart figure
        
    Returns:
    --------
    dict : Paths to all exported files
    
    Example:
    --------
    >>> export_paths = export_stakeholder_outputs(
    ...     stakeholder_map, cities_gdf, workshop_prof, 
    ...     output_dir, 2024, figure_dpi=300, donut_fig=donut_fig
    ... )
    """
    from pathlib import Path

    # Use explicit backends to bypass Jupyter inline backend on PNG/PDF saves
    from matplotlib.backends.backend_agg import FigureCanvasAgg as _FCAgg
    from matplotlib.backends.backend_pdf import FigureCanvasPdf as _FCPdf

    def _save_png(fig, path, dpi):
        _FCAgg(fig).print_figure(str(path), dpi=dpi, bbox_inches='tight', format='png')

    def _save_pdf(fig, path):
        _FCPdf(fig).print_figure(str(path), bbox_inches='tight', format='pdf')
    
    # Create subdirectories
    figures_dir = output_dir / 'Figures'
    data_dir = output_dir / 'Data'
    
    figures_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Output directories created:")
    print(f"  Figures: {figures_dir}")
    print(f"  Data: {data_dir}")
    
    # Export map as PNG + SVG + PDF
    print("\nExporting stakeholder distribution map...")
    
    png_path = figures_dir / f'Stakeholder_Distribution_Map_{study_year}.png'
    svg_path = figures_dir / f'Stakeholder_Distribution_Map_{study_year}.svg'
    pdf_path = figures_dir / f'Stakeholder_Distribution_Map_{study_year}.pdf'
    
    _save_png(stakeholder_map, png_path, figure_dpi)
    print(f"  ✅ PNG saved: {png_path.name}")
    
    stakeholder_map.savefig(svg_path, format='svg', bbox_inches='tight')
    print(f"  ✅ SVG saved: {svg_path.name}")
    
    _save_pdf(stakeholder_map, pdf_path)
    print(f"  ✅ PDF saved: {pdf_path.name}")
    
    # Export donut chart if provided
    if donut_fig is not None:
        donut_png = figures_dir / f'City_Classification_Donut_{study_year}.png'
        donut_svg = figures_dir / f'City_Classification_Donut_{study_year}.svg'
        donut_pdf = figures_dir / f'City_Classification_Donut_{study_year}.pdf'
        
        _save_png(donut_fig, donut_png, figure_dpi)
        print(f"  ✅ PNG saved: {donut_png.name}")
        
        donut_fig.savefig(donut_svg, format='svg', bbox_inches='tight')
        print(f"  ✅ SVG saved: {donut_svg.name}")
        
        _save_pdf(donut_fig, donut_pdf)
        print(f"  ✅ PDF saved: {donut_pdf.name}")
    
    # Export data tables
    print("\nExporting data tables...")
    
    # Export cities with stakeholder data
    cities_export = cities_gdf.drop(columns=['geometry']).copy()
    cities_export_path = data_dir / f'Cities_Stakeholder_Summary_{study_year}.csv'
    cities_export.to_csv(cities_export_path, index=False)
    print(f"  ✅ Cities summary: {cities_export_path.name}")
    
    # Export profession breakdown
    profession_export_path = data_dir / f'Workshop_Profession_Breakdown_{study_year}.csv'
    workshop_prof.to_csv(profession_export_path, index=False)
    print(f"  ✅ Profession breakdown: {profession_export_path.name}")
    
    # Export GeoJSON
    cities_geojson_path = data_dir / f'Cities_Stakeholder_Points_{study_year}.geojson'
    cities_gdf.to_file(cities_geojson_path, driver='GeoJSON')
    print(f"  ✅ GeoJSON: {cities_geojson_path.name}")
    
    # Print summary
    print("\n" + "="*80)
    print("EXPORT SUMMARY")
    print("="*80)
    print(f"Output Directory: {output_dir}")
    print(f"\nFigures Exported:")
    print(f"  - {png_path.name}")
    print(f"  - {svg_path.name}")
    print(f"  - {pdf_path.name}")
    if donut_fig is not None:
        print(f"  - {donut_png.name}")
        print(f"  - {donut_svg.name}")
        print(f"  - {donut_pdf.name}")
    print(f"\nData Files Exported:")
    print(f"  - {cities_export_path.name}")
    print(f"  - {profession_export_path.name}")
    print(f"  - {cities_geojson_path.name}")
    print("\n✅ All exports completed successfully!")
    
    # Return paths for reference
    result = {
        'png': png_path,
        'svg': svg_path,
        'pdf': pdf_path,
        'cities_csv': cities_export_path,
        'profession_csv': profession_export_path,
        'cities_geojson': cities_geojson_path
    }
    
    if donut_fig is not None:
        result['donut_png'] = donut_png
        result['donut_svg'] = donut_svg
        result['donut_pdf'] = donut_pdf
    
    return result


def export_perception_charts(
    perception_fig,
    donuts_fig,
    unique_resp,
    output_dir,
    study_year,
    figure_dpi=300
):
    """
    Export stakeholder perception charts and data.
    
    Parameters:
    -----------
    perception_fig : matplotlib.figure.Figure
        Main perception chart with embedded donuts
    donuts_fig : matplotlib.figure.Figure
        Separate standalone donut charts
    unique_resp : DataFrame
        Unique participant responses data
    output_dir : Path
        Output directory path
    study_year : int
        Study year for file naming
    figure_dpi : int
        Figure DPI for export (default: 300)
        
    Returns:
    --------
    dict : Paths to all exported files
    """
    from pathlib import Path

    # Use explicit backends to bypass Jupyter inline backend on PNG/PDF saves
    from matplotlib.backends.backend_agg import FigureCanvasAgg as _FCAgg
    from matplotlib.backends.backend_pdf import FigureCanvasPdf as _FCPdf

    def _save_png(fig, path, dpi):
        _FCAgg(fig).print_figure(str(path), dpi=dpi, bbox_inches='tight', format='png')

    def _save_pdf(fig, path):
        _FCPdf(fig).print_figure(str(path), bbox_inches='tight', format='pdf')

    # Create subdirectories
    figures_dir = Path(output_dir) / 'Figures'
    data_dir = Path(output_dir) / 'Data'
    
    figures_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    
    print("\nExporting perception charts...")
    
    # Export main perception chart (PNG + SVG + PDF)
    perception_png = figures_dir / f'Stakeholder_Perception_By_City_{study_year}.png'
    perception_svg = figures_dir / f'Stakeholder_Perception_By_City_{study_year}.svg'
    perception_pdf = figures_dir / f'Stakeholder_Perception_By_City_{study_year}.pdf'
    
    _save_png(perception_fig, perception_png, figure_dpi)
    print(f"  ✅ PNG saved: {perception_png.name}")
    
    perception_fig.savefig(perception_svg, format='svg', bbox_inches='tight', 
                           facecolor='white', edgecolor='none')
    print(f"  ✅ SVG saved: {perception_svg.name}")
    
    _save_pdf(perception_fig, perception_pdf)
    print(f"  ✅ PDF saved: {perception_pdf.name}")
    
    # Export standalone donuts chart (PNG + SVG + PDF)
    donuts_png = figures_dir / f'Stakeholder_Perception_Overall_{study_year}.png'
    donuts_svg = figures_dir / f'Stakeholder_Perception_Overall_{study_year}.svg'
    donuts_pdf = figures_dir / f'Stakeholder_Perception_Overall_{study_year}.pdf'
    
    _save_png(donuts_fig, donuts_png, figure_dpi)
    print(f"  ✅ PNG saved: {donuts_png.name}")
    
    donuts_fig.savefig(donuts_svg, format='svg', bbox_inches='tight', 
                       facecolor='white', edgecolor='none')
    print(f"  ✅ SVG saved: {donuts_svg.name}")
    
    _save_pdf(donuts_fig, donuts_pdf)
    print(f"  ✅ PDF saved: {donuts_pdf.name}")
    
    # Export perception data
    perception_data_path = data_dir / f'Stakeholder_Perception_Data_{study_year}.csv'
    unique_resp.to_csv(perception_data_path, index=False)
    print(f"  ✅ Data saved: {perception_data_path.name}")
    
    print("\n✅ All perception exports completed!")
    
    return {
        'perception_png': perception_png,
        'perception_svg': perception_svg,
        'perception_pdf': perception_pdf,
        'donuts_png': donuts_png,
        'donuts_svg': donuts_svg,
        'donuts_pdf': donuts_pdf,
        'perception_data': perception_data_path
    }


# =============================================================================
# DAILY LST EXPORT FUNCTIONS (Notebook 04)
# =============================================================================

def export_daily_lst_data(
    city_name: str,
    dataset_name: str,
    day_night: str,
    df: pd.DataFrame,
    base_output_dir: str = None
) -> Path:
    """
    Export daily LST data to CSV with standardized naming.
    
    Example:
    >>> df_modis_day = extract_modis_daily_lst(...)
    >>> path = export_daily_lst_data('Lagos', 'modis', 'day', df_modis_day)
    """
    import numpy as np
    
    if base_output_dir is None:
        base_output_dir = config.OUTPUT_DIR if hasattr(config, 'OUTPUT_DIR') else Path("data/outputs")
    
    city_dir = Path(base_output_dir) / "04_trend_analysis_daily" / f"City_{city_name}"
    data_dir = city_dir / "Data"
    data_dir.mkdir(parents=True, exist_ok=True)
    
    filename = f"{dataset_name}_{day_night}_2024.csv"
    output_path = data_dir / filename
    df.to_csv(output_path, index=False)
    
    print(f"Exported {dataset_name.upper()} {day_night} LST data: {output_path}")
    
    return output_path


def export_daily_lst_events(
    city_name: str,
    dataset_name: str,
    day_night: str,
    df_events: pd.DataFrame,
    base_output_dir: str = None
) -> Path:
    """
    Export hot event detection results to CSV.
    
    Args:
        city_name: City name
        dataset_name: Dataset name (modis, era5, seviri)
        day_night: 'day' or 'night'
        df_events: DataFrame with is_hot column and hot event threshold
        base_output_dir: Base output directory (default: config.OUTPUT_DIR)
    
    Returns:
        Path to exported file
    """
    if base_output_dir is None:
        base_output_dir = config.OUTPUT_DIR if hasattr(config, 'OUTPUT_DIR') else Path("data/outputs")
    
    city_dir = Path(base_output_dir) / "04_trend_analysis_daily" / f"City_{city_name}"
    data_dir = city_dir / "Data"
    data_dir.mkdir(parents=True, exist_ok=True)
    
    filename = f"{dataset_name}_{day_night}_events_2024.csv"
    output_path = data_dir / filename
    df_events.to_csv(output_path, index=False)
    
    print(f"Exported {dataset_name.upper()} {day_night} hot events: {output_path}")
    
    return output_path


def export_dataset_comparison(
    city_name: str,
    dataset1_name: str,
    dataset2_name: str,
    day_night: str,
    df_comparison: pd.DataFrame,
    stats: dict,
    base_output_dir: str = None
) -> tuple[Path, Path]:
    """
    Export dataset comparison results (merged data + statistics).
    
    Args:
        city_name: City name
        dataset1_name: First dataset name (e.g., 'modis')
        dataset2_name: Second dataset name (e.g., 'era5')
        day_night: 'day' or 'night'
        df_comparison: Merged DataFrame with both datasets
        stats: Dictionary with correlation, bias, RMSE, MAE
        base_output_dir: Base output directory
    
    Returns:
        Tuple of (data_path, stats_path)
    """
    if base_output_dir is None:
        base_output_dir = config.OUTPUT_DIR if hasattr(config, 'OUTPUT_DIR') else Path("data/outputs")
    
    city_dir = Path(base_output_dir) / "04_trend_analysis_daily" / f"City_{city_name}"
    data_dir = city_dir / "Data"
    data_dir.mkdir(parents=True, exist_ok=True)
    
    # Export merged data
    data_filename = f"comparison_{dataset1_name}_vs_{dataset2_name}_{day_night}_2024.csv"
    data_path = data_dir / data_filename
    df_comparison.to_csv(data_path, index=False)
    
    # Export statistics
    stats_filename = f"comparison_{dataset1_name}_vs_{dataset2_name}_{day_night}_stats_2024.json"
    stats_path = data_dir / stats_filename
    with open(stats_path, 'w') as f:
        json.dump(stats, f, indent=2)
    
    print(f"Exported {dataset1_name.upper()} vs {dataset2_name.upper()} comparison:")
    print(f"  Data:  {data_path}")
    print(f"  Stats: {stats_path}")
    
    return data_path, stats_path


def export_comprehensive_daily_summary(
    city_name: str,
    summary_dict: dict,
    base_output_dir: str = None
) -> Path:
    """
    Export comprehensive daily LST analysis summary to JSON.
    
    Args:
        city_name: City name
        summary_dict: Comprehensive summary dictionary with all analysis results
        base_output_dir: Base output directory
    
    Returns:
        Path to exported JSON file
    """
    if base_output_dir is None:
        base_output_dir = config.OUTPUT_DIR if hasattr(config, 'OUTPUT_DIR') else Path("data/outputs")
    
    city_dir = Path(base_output_dir) / "04_trend_analysis_daily" / f"City_{city_name}"
    data_dir = city_dir / "Data"
    data_dir.mkdir(parents=True, exist_ok=True)
    
    filename = "comprehensive_summary_2024.json"
    output_path = data_dir / filename
    
    with open(output_path, 'w') as f:
        json.dump(summary_dict, f, indent=2)
    
    print(f"Exported comprehensive daily summary: {output_path}")
    
    return output_path


# ====================================================================
# SEVIRI LST DATA LOADING & SUMMARY
# ====================================================================

def load_seviri_cities_lst(base_dir, study_year):
    """
    Load SEVIRI LST data for all processed cities
    
    Parameters:
    -----------
    base_dir : str or Path
        Base SEVIRI output directory
    study_year : int
        Study year
    
    Returns:
    --------
    dict : Dictionary with structure:
        {city_name: {'day': raster_array, 'night': raster_array, 
                     'day_event': date_range, 'night_event': date_range,
                     'day_duration': int, 'night_duration': int}}
    """
    import numpy as np
    import rasterio
    import json
    
    cities_data = {}
    summary_file = Path(base_dir) / f'processing_summary_{study_year}.json'
    
    if not summary_file.exists():
        print(f"❌ Processing summary not found: {summary_file}")
        return cities_data
    
    with open(summary_file, 'r') as f:
        summary = json.load(f)
    
    # Extract city results (skip metadata keys like total_cities, successful, etc.)
    city_results = summary.get('results', summary)
    
    for city_name, city_info in city_results.items():
        # Skip non-dictionary items (metadata keys)
        if not isinstance(city_info, dict):
            continue
            
        city_data = {}
        
        for period_type in ['day', 'night']:
            if (period_type in city_info
                    and city_info[period_type] is not None
                    and isinstance(city_info[period_type], dict)
                    and city_info[period_type].get('status') in ['completed', 'skipped', 'success']):
                clipped_path = city_info[period_type]['clipped_path']
                
                if os.path.exists(clipped_path):
                    try:
                        with rasterio.open(clipped_path) as src:
                            data = src.read(1)
                            data[data == src.nodata] = np.nan
                            city_data[period_type] = data
                            city_data[f'{period_type}_file'] = clipped_path  # Store file path
                        
                        metadata = city_info[period_type]['metadata']
                        city_data[f'{period_type}_event'] = (
                            f"{metadata['event_start_date']} to {metadata['event_end_date']}"
                        )
                        city_data[f'{period_type}_duration'] = metadata['event_duration_days']
                    except Exception as e:
                        print(f"⚠️  Error loading {city_name} {period_type}: {e}")
        
        if city_data:
            cities_data[city_name] = city_data
    
    return cities_data


def create_seviri_temperature_summary(cities_data, base_dir=None, study_year=2024):
    """
    Create comprehensive SEVIRI temperature statistics summary table
    
    Parameters:
    -----------
    cities_data : dict
        Dictionary from load_seviri_cities_lst()
    base_dir : str or Path, optional
        Base output directory for CSV export
    study_year : int
        Study year
    
    Returns:
    --------
    pd.DataFrame : Summary statistics table
    """
    import numpy as np
    
    summary_rows = []
    
    for city_name in sorted(cities_data.keys()):
        city_data = cities_data[city_name]
        row = {'City': city_name}
        
        for period in ['day', 'night']:
            if period in city_data:
                lst_data = city_data[period]
                
                # Calculate statistics
                stats = {
                    f'{period.capitalize()}_Event_Period': city_data.get(f'{period}_event', 'N/A'),
                    f'{period.capitalize()}_Duration_Days': city_data.get(f'{period}_duration', 'N/A'),
                    f'{period.capitalize()}_Mean_°C': f"{np.nanmean(lst_data):.1f}",
                    f'{period.capitalize()}_Min_°C': f"{np.nanmin(lst_data):.1f}",
                    f'{period.capitalize()}_Max_°C': f"{np.nanmax(lst_data):.1f}",
                    f'{period.capitalize()}_Std_°C': f"{np.nanstd(lst_data):.1f}"
                }
                row.update(stats)
            else:
                # Fill with N/A for missing period
                for stat in ['Event_Period', 'Duration_Days', 'Mean_°C', 'Min_°C', 'Max_°C', 'Std_°C']:
                    row[f'{period.capitalize()}_{stat}'] = 'N/A'
        
        summary_rows.append(row)
    
    # Create DataFrame
    df = pd.DataFrame(summary_rows)
    
    # Reorder columns for better readability
    col_order = ['City']
    for period in ['Day', 'Night']:
        col_order.extend([
            f'{period}_Event_Period', f'{period}_Duration_Days',
            f'{period}_Mean_°C', f'{period}_Min_°C', 
            f'{period}_Max_°C', f'{period}_Std_°C'
        ])
    df = df[col_order]
    
    # Display table
    print("\n" + "=" * 120)
    print(f"TEMPERATURE STATISTICS SUMMARY - SEVIRI LST {study_year}")
    print("=" * 120)
    print(df.to_string(index=False))
    
    # Save CSV if base_dir is provided
    if base_dir is not None:
        csv_file = Path(base_dir) / f'SEVIRI_LST_{study_year}_statistics_summary.csv'
        df.to_csv(csv_file, index=False)
        print(f"\nSummary saved to: {csv_file}")
    print("=" * 120)
    return df


def load_osm_water_mask(city_name: str, lst_shape: tuple, lst_transform, lst_crs: str,
                        aoi_dir: Path = None, area_threshold_km2: float = 3.0) -> np.ndarray:
    """
    Load JRC Global Surface Water polygons for a city and rasterize to match LST grid.
    
    Filters water bodies by area threshold to mask only significant water features.
    
    Note: Uses JRC water bodies extracted via Google Earth Engine (not OSM).
    Function name kept for backward compatibility.
    
    Parameters
    ----------
    city_name : str
        Name of the city (e.g., 'Lagos', 'Abuja')
    lst_shape : tuple
        Shape of the LST raster (height, width)
    lst_transform : affine.Affine
        Affine transform of the LST raster
    lst_crs : str
        CRS of the LST raster (e.g., MSG GEOS projection)
    aoi_dir : Path, optional
        Base directory for AOI outputs. Defaults to data/outputs/01_aoi_delineation/
    area_threshold_km2 : float, optional
        Minimum water body area in sq km to include in mask (default: 3.0)
    
    Returns
    -------
    np.ndarray
        Boolean mask array where True indicates water pixels (same shape as LST)
        Returns array of False if no water bodies found
    
    Examples
    --------
    >>> water_mask = load_osm_water_mask('Lagos', (500, 500), transform, msg_crs)
    >>> lst_masked = np.where(water_mask, np.nan, median_lst)
    """
    if not RASTERIO_AVAILABLE:
        print("        Warning: rasterio not available, skipping water masking")
        return np.zeros(lst_shape, dtype=bool)
    
    if aoi_dir is None:
        # Default to project structure
        project_root = Path.cwd()
        if project_root.name.lower() in ('notebooks', 'notebook'):
            project_root = project_root.parent
        aoi_dir = project_root / 'data' / 'outputs' / '01_aoi_delineation'
    
    # Path to geospatial features (JRC water bodies from GEE)
    # Try multiple path conventions in priority order.
    # Prefer _102022 (ANALYSIS_CRS) version when the LST raster is in a projected CRS;
    # fall back to _4326 which can be reprojected on-the-fly by rasterio.
    city_slug = city_name.replace(' ', '_')
    _water_candidates = [
        # ANALYSIS_CRS version (preferred for projected/metric grids e.g. SEVIRI 102022)
        aoi_dir / city_slug / f'{city_slug}_water_bodies_102022.geojson',
        # WGS84 fallback (always reprojected to match LST CRS below)
        aoi_dir / city_slug / f'{city_slug}_water_bodies_4326.geojson',
        aoi_dir / city_name / f'{city_name}_water_bodies_4326.geojson',
        # Legacy structure
        aoi_dir / f'City_{city_name}' / 'Features' / 'OSM' / f'{city_name}_water_bodies.geojson',
        aoi_dir / f'City_{city_slug}' / 'Features' / 'OSM' / f'{city_slug}_water_bodies.geojson',
    ]
    water_file = next((p for p in _water_candidates if p.exists()), None)

    if water_file is None:
        print(f"        No water bodies file found for {city_name}")
        print(f"        Tried: {_water_candidates[0]}")
        return np.zeros(lst_shape, dtype=bool)
    
    try:
        # Load water polygons
        water_gdf = gpd.read_file(water_file)
        
        if water_gdf.empty:
            print(f"        No water bodies found in {water_file.name}")
            return np.zeros(lst_shape, dtype=bool)
        
        # Reproject to LST CRS
        water_reprojected = water_gdf.to_crs(lst_crs)
        
        # Get only polygon geometries
        water_polygons = water_reprojected[
            water_reprojected.geometry.type.isin(['Polygon', 'MultiPolygon'])
        ]
        
        if water_polygons.empty:
            print(f"        No polygon water bodies to mask")
            return np.zeros(lst_shape, dtype=bool)
        
        # Calculate area in sq km and filter by threshold
        water_polygons_copy = water_polygons.copy()
        
        # Use a metric CRS for accurate area calculation
        # UTM Zone 32N (EPSG:32632) is suitable for Nigeria
        water_metric = water_polygons_copy.to_crs('EPSG:32632')
        water_polygons_copy['area_km2'] = water_metric.geometry.area / 1e6
        
        # Filter by area threshold
        water_filtered = water_polygons_copy[water_polygons_copy['area_km2'] >= area_threshold_km2]
        
        n_total = len(water_polygons)
        n_filtered = len(water_filtered)
        
        if water_filtered.empty:
            print(f"        No water bodies ≥{area_threshold_km2} km² ({n_total} bodies < threshold)")
            return np.zeros(lst_shape, dtype=bool)
        
        # Report filtering statistics
        total_area_all = water_polygons_copy['area_km2'].sum()
        total_area_filtered = water_filtered['area_km2'].sum()
        print(f"        Filtered water bodies: {n_filtered}/{n_total} (≥{area_threshold_km2} km²)")
        print(f"        Total area: {total_area_filtered:.2f} km² of {total_area_all:.2f} km² ({100*total_area_filtered/total_area_all:.1f}%)")
        
        # Get geometries back in LST CRS for rasterization
        water_for_mask = water_filtered.to_crs(lst_crs)
        
        # Rasterize water polygons to match LST grid
        water_mask = rasterize(
            shapes=[(geom, 1) for geom in water_for_mask.geometry],
            out_shape=lst_shape,
            transform=lst_transform,
            fill=0,
            dtype='uint8'
        ).astype(bool)
        
        water_pixel_count = np.sum(water_mask)
        total_pixels = lst_shape[0] * lst_shape[1]
        water_pct = 100 * water_pixel_count / total_pixels
        
        print(f"        Water mask applied: {water_pixel_count:,} pixels ({water_pct:.2f}% of AOI)")
        
        # Show water body names if available
        if 'name' in water_filtered.columns:
            named_water = water_filtered[water_filtered['name'].notna()]['name'].unique()
            if len(named_water) > 0:
                print(f"        Water bodies: {', '.join(named_water[:3])}" + 
                      (f" (+{len(named_water)-3} more)" if len(named_water) > 3 else ""))
        
        return water_mask
        
    except Exception as e:
        print(f"        Error loading water mask: {e}")
        return np.zeros(lst_shape, dtype=bool)


# ====================================================================
# OSM/JRC GEOSPATIAL FEATURES EXTRACTION & TRACKING
# ====================================================================

def get_aoi_tracking_file(base_output_dir: Path = None) -> Path:
    """
    Get path to the AOI tracking JSON file.
    
    Parameters
    ----------
    base_output_dir : Path, optional
        Base output directory. Defaults to data/outputs/01_aoi_delineation/
    
    Returns
    -------
    Path
        Path to aoi_features_tracking.json
    """
    if base_output_dir is None:
        try:
            base_output_dir = config.OUTPUT_DIR / '01_aoi_delineation'
        except:
            base_output_dir = Path('data/outputs/01_aoi_delineation')
    
    return Path(base_output_dir) / 'aoi_features_tracking.json'


def load_aoi_tracking(base_output_dir: Path = None) -> dict:
    """
    Load AOI features tracking data from JSON.
    
    The tracking file stores area_km2 for each city's Main_Polygon.
    If the area changes, features should be re-extracted.
    
    Parameters
    ----------
    base_output_dir : Path, optional
        Base output directory
    
    Returns
    -------
    dict
        Dictionary with structure: {city_name: {'area_km2': float, 'last_updated': str}}
    """
    tracking_file = get_aoi_tracking_file(base_output_dir)
    
    if tracking_file.exists():
        with open(tracking_file, 'r') as f:
            return json.load(f)
    
    return {}


def save_aoi_tracking(tracking_data: dict, base_output_dir: Path = None) -> Path:
    """
    Save AOI features tracking data to JSON.
    
    Parameters
    ----------
    tracking_data : dict
        Tracking data dictionary
    base_output_dir : Path, optional
        Base output directory
    
    Returns
    -------
    Path
        Path to saved tracking file
    """
    tracking_file = get_aoi_tracking_file(base_output_dir)
    tracking_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(tracking_file, 'w') as f:
        json.dump(tracking_data, f, indent=2)
    
    return tracking_file


def get_main_polygon_area(city_name: str, base_output_dir: Path = None) -> float:
    """
    Get the area of a city's Main_Polygon from GeoJSON file.
    
    Parameters
    ----------
    city_name : str
        Name of the city
    base_output_dir : Path, optional
        Base output directory for AOI delineation outputs
    
    Returns
    -------
    float
        Area in km², or 0.0 if file not found
    """
    if base_output_dir is None:
        try:
            base_output_dir = config.OUTPUT_DIR / '01_aoi_delineation'
        except:
            base_output_dir = Path('data/outputs/01_aoi_delineation')
    
    main_polygon_file = Path(base_output_dir) / f'City_{city_name}' / 'Features' / f'{city_name}_Main_Polygon.geojson'
    
    if not main_polygon_file.exists():
        return 0.0
    
    try:
        gdf = gpd.read_file(main_polygon_file)
        # Calculate area in km² (convert to metric CRS for area calculation)
        area_km2 = gdf.to_crs('EPSG:32632').area.sum() / 1e6
        return float(area_km2)
    except Exception as e:
        print(f"Warning: Could not calculate area for {city_name}: {e}")
        return 0.0


def check_features_need_update(city_name: str, base_output_dir: Path = None, 
                               tolerance_pct: float = 1.0) -> tuple:
    """
    Check if city features need to be re-extracted based on AOI area change.
    
    Parameters
    ----------
    city_name : str
        Name of the city
    base_output_dir : Path, optional
        Base output directory
    tolerance_pct : float
        Percentage tolerance for area change (default 1%)
    
    Returns
    -------
    tuple
        (needs_update: bool, reason: str, current_area: float, tracked_area: float)
    """
    tracking_data = load_aoi_tracking(base_output_dir)
    current_area = get_main_polygon_area(city_name, base_output_dir)
    
    if current_area == 0.0:
        return True, "Main_Polygon not found", 0.0, 0.0
    
    if city_name not in tracking_data:
        return True, "City not in tracking file", current_area, 0.0
    
    tracked_area = tracking_data[city_name].get('area_km2', 0.0)
    
    if tracked_area == 0.0:
        return True, "No tracked area", current_area, 0.0
    
    # Calculate percentage change
    pct_change = abs(current_area - tracked_area) / tracked_area * 100
    
    if pct_change > tolerance_pct:
        return True, f"Area changed by {pct_change:.2f}%", current_area, tracked_area
    
    return False, "Area unchanged", current_area, tracked_area


def update_aoi_tracking(city_name: str, area_km2: float, base_output_dir: Path = None) -> None:
    """
    Update tracking data for a city after feature extraction.
    
    Parameters
    ----------
    city_name : str
        Name of the city
    area_km2 : float
        Current area in km²
    base_output_dir : Path, optional
        Base output directory
    """
    tracking_data = load_aoi_tracking(base_output_dir)
    
    tracking_data[city_name] = {
        'area_km2': round(area_km2, 4),
        'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    save_aoi_tracking(tracking_data, base_output_dir)


def check_osm_feature_exists(city_name: str, feature_type: str, 
                             base_output_dir: Path = None) -> tuple:
    """
    Check if an OSM/JRC feature file exists and has valid data.
    
    Parameters
    ----------
    city_name : str
        Name of the city
    feature_type : str
        Type of feature: 'water', 'roads', or 'places'
    base_output_dir : Path, optional
        Base output directory
    
    Returns
    -------
    tuple
        (exists: bool, file_path: Path, feature_count: int)
    """
    if base_output_dir is None:
        try:
            base_output_dir = config.OUTPUT_DIR / '01_aoi_delineation'
        except:
            base_output_dir = Path('data/outputs/01_aoi_delineation')
    
    feature_files = {
        'water': f'{city_name}_water_bodies.geojson',
        'roads': f'{city_name}_roads.geojson',
        'places': f'{city_name}_places.geojson'
    }
    
    if feature_type not in feature_files:
        return False, None, 0
    
    feature_file = Path(base_output_dir) / f'City_{city_name}' / 'Features' / 'OSM' / feature_files[feature_type]
    
    if not feature_file.exists():
        return False, feature_file, 0
    
    try:
        # Use fiona to count features without loading full GeoDataFrame
        # (much faster for large files; avoids OGR type warnings from gpd.read_file)
        import fiona
        with fiona.Env(GDAL_CACHEMAX=64), fiona.open(str(feature_file)) as src:
            count = len(src)
        return True, feature_file, count
    except Exception:
        # Fallback: try full read with OGR warnings suppressed
        try:
            os.environ['CPL_LOG'] = 'NUL' if os.name == 'nt' else '/dev/null'
            gdf = gpd.read_file(feature_file)
            os.environ.pop('CPL_LOG', None)
            return True, feature_file, len(gdf)
        except Exception:
            os.environ.pop('CPL_LOG', None)
            return False, feature_file, 0


def load_city_osm_features(city_name: str, base_output_dir: Path = None) -> dict:
    """
    Load all OSM/JRC features for a city.
    
    Parameters
    ----------
    city_name : str
        Name of the city
    base_output_dir : Path, optional
        Base output directory
    
    Returns
    -------
    dict
        Dictionary with keys: 'water', 'roads', 'places'
        Each value is either a GeoDataFrame or None
    """
    features = {}
    
    for feature_type in ['water', 'roads', 'places']:
        exists, file_path, count = check_osm_feature_exists(city_name, feature_type, base_output_dir)
        
        if exists and count > 0:
            # Suppress OGR "Skipping field" warnings (C-level stderr)
            _old_stderr = os.dup(2)
            _devnull = os.open(os.devnull, os.O_RDWR)
            os.dup2(_devnull, 2)
            try:
                features[feature_type] = gpd.read_file(file_path)
            except Exception:
                features[feature_type] = None
            finally:
                os.dup2(_old_stderr, 2)
                os.close(_old_stderr)
                os.close(_devnull)
        else:
            features[feature_type] = None
    
    return features


def load_city_polygon_features(city_name: str, base_output_dir: Path = None) -> dict:
    """
    Load main and adjacent polygon features for a city.
    
    Parameters
    ----------
    city_name : str
        Name of the city
    base_output_dir : Path, optional
        Base output directory
    
    Returns
    -------
    dict
        Dictionary with keys: 'main_polygon', 'adjacent_polygons'
        Each value is either a GeoDataFrame or None
    """
    polygons = {}
    
    if base_output_dir is None:
        base_output_dir = Path('../../data/outputs/01_aoi_delineation')
    
    city_features_dir = base_output_dir / f'City_{city_name}' / 'Features'
    
    # Load main polygon
    main_polygon_file = city_features_dir / f'{city_name}_Main_Polygon.geojson'
    if main_polygon_file.exists():
        polygons['main_polygon'] = gpd.read_file(main_polygon_file)
    else:
        polygons['main_polygon'] = None
    
    # Load adjacent polygons
    adjacent_polygons_file = city_features_dir / f'{city_name}_Adjacent_Polygons.geojson'
    if adjacent_polygons_file.exists():
        polygons['adjacent_polygons'] = gpd.read_file(adjacent_polygons_file)
    else:
        polygons['adjacent_polygons'] = None
    
    return polygons


def get_osm_extraction_status(city_name: str, base_output_dir: Path = None) -> dict:
    """
    Get comprehensive status of OSM feature extraction for a city.
    
    Parameters
    ----------
    city_name : str
        Name of the city
    base_output_dir : Path, optional
        Base output directory
    
    Returns
    -------
    dict
        Status dictionary with extraction state, feature counts, and update needs
    """
    needs_update, reason, current_area, tracked_area = check_features_need_update(
        city_name, base_output_dir
    )
    
    status = {
        'city_name': city_name,
        'needs_update': needs_update,
        'update_reason': reason,
        'current_area_km2': current_area,
        'tracked_area_km2': tracked_area,
        'features': {}
    }
    
    for feature_type in ['water', 'roads', 'places']:
        exists, file_path, count = check_osm_feature_exists(city_name, feature_type, base_output_dir)
        status['features'][feature_type] = {
            'exists': exists,
            'count': count,
            'file': str(file_path) if file_path else None
        }
    
    return status


def filter_places_for_display(places_gdf: gpd.GeoDataFrame, 
                               place_types: list = None) -> gpd.GeoDataFrame:
    """
    Filter places GeoDataFrame for map display (towns and suburbs only by default).
    
    Parameters
    ----------
    places_gdf : gpd.GeoDataFrame
        Full places GeoDataFrame
    place_types : list, optional
        List of place types to include. Default: ['town', 'suburb']
    
    Returns
    -------
    gpd.GeoDataFrame
        Filtered places
    """
    if places_gdf is None or places_gdf.empty:
        return gpd.GeoDataFrame()
    
    if place_types is None:
        place_types = ['town', 'suburb']
    
    if 'place' not in places_gdf.columns:
        return places_gdf
    
    filtered = places_gdf[places_gdf['place'].isin(place_types)].copy()
    
    return filtered


def get_osm_features_summary(cities: list, base_output_dir: Path = None) -> pd.DataFrame:
    """
    Get summary DataFrame of OSM features for all cities.
    
    Parameters
    ----------
    cities : list
        List of city names
    base_output_dir : Path, optional
        Base output directory
    
    Returns
    -------
    pd.DataFrame
        Summary table with feature counts and file sizes
    """
    rows = []
    
    for city_name in cities:
        row = {'city': city_name}
        
        for feature_type in ['water', 'roads', 'places']:
            exists, file_path, count = check_osm_feature_exists(city_name, feature_type, base_output_dir)
            row[f'{feature_type}_count'] = count
            
            if exists and file_path.exists():
                row[f'{feature_type}_size_mb'] = file_path.stat().st_size / (1024 * 1024)
            else:
                row[f'{feature_type}_size_mb'] = 0.0
        
        rows.append(row)
    
    return pd.DataFrame(rows)


def load_city_polygons(city_name: str, base_output_dir: Path = None) -> dict:
    """
    Load Main_Polygon and Adjacent_Polygons for a city.
    
    Parameters
    ----------
    city_name : str
        Name of the city
    base_output_dir : Path, optional
        Base output directory for AOI delineation outputs
    
    Returns
    -------
    dict
        Dictionary with keys 'main_polygon' and 'adjacent_polygons',
        each containing a GeoDataFrame or None if file not found
    
    Example
    -------
    >>> polygons = load_city_polygons('Lagos', aoi_base_dir)
    >>> main_gdf = polygons['main_polygon']
    >>> adj_gdf = polygons['adjacent_polygons']
    """
    if base_output_dir is None:
        try:
            base_output_dir = config.OUTPUT_DIR / '01_aoi_delineation'
        except:
            base_output_dir = Path('data/outputs/01_aoi_delineation')
    
    features_dir = Path(base_output_dir) / f'City_{city_name}' / 'Features'
    
    result = {
        'main_polygon': None,
        'adjacent_polygons': None
    }
    
    # Load Main Polygon
    main_file = features_dir / f'{city_name}_Main_Polygon.geojson'
    if main_file.exists():
        try:
            result['main_polygon'] = gpd.read_file(main_file)
        except Exception as e:
            print(f"Warning: Could not load Main Polygon for {city_name}: {e}")
    
    # Load Adjacent Polygons
    adj_file = features_dir / f'{city_name}_Adjacent_Polygons.geojson'
    if adj_file.exists():
        try:
            result['adjacent_polygons'] = gpd.read_file(adj_file)
        except Exception as e:
            print(f"Warning: Could not load Adjacent Polygons for {city_name}: {e}")
    
    return result


# =============================================================================
# HOTSPOT ANALYSIS I/O FUNCTIONS (Notebook 05)
# =============================================================================

def load_landscape_data(landscape_path: Path = None, target_crs: str = "EPSG:4326") -> gpd.GeoDataFrame:
    """
    Load landscape classification GeoJSON and reproject to target CRS.
    
    Parameters
    ----------
    landscape_path : Path, optional
        Path to landscape GeoJSON file. If None, uses config.LANDSCAPE_DATA_PATH
    target_crs : str, optional
        Target CRS for reprojection (default: EPSG:4326)
    
    Returns
    -------
    gpd.GeoDataFrame
        Landscape features reprojected to target CRS
    
    Raises
    ------
    FileNotFoundError
        If landscape file does not exist
    """
    if landscape_path is None:
        try:
            landscape_path = config.LANDSCAPE_DATA_PATH
        except AttributeError:
            # Fallback for legacy config
            project_root = Path.cwd().parent if Path.cwd().name.lower() in ('notebooks', 'notebook') else Path.cwd()
            landscape_path = project_root / "data" / "inputs" / "geospatial_features" / "landscape_ch_polygons_with_class_metrics.geojson"
    
    if not landscape_path.exists():
        raise FileNotFoundError(f"Landscape file not found: {landscape_path}")
    
    landscape_gdf = gpd.read_file(landscape_path)
    
    # Reproject if needed
    if str(landscape_gdf.crs) != target_crs:
        landscape_gdf = landscape_gdf.to_crs(target_crs)
    
    return landscape_gdf


def extract_landscape_attributes(polygon_gdf: gpd.GeoDataFrame, 
                                landscape_gdf: gpd.GeoDataFrame, 
                                class_cols: list) -> dict:
    """
    Extract dominant landscape attributes for a polygon via spatial overlay.
    
    Calculates area-weighted mode (dominant class) and coverage percentage
    for each landscape classification attribute.
    
    Parameters
    ----------
    polygon_gdf : gpd.GeoDataFrame
        Single-row GeoDataFrame with polygon geometry
    landscape_gdf : gpd.GeoDataFrame
        Landscape classification features
    class_cols : list
        List of classification column names (e.g., 'Elevation_Class', 'Climate_Class')
        
    Returns
    -------
    dict
        Landscape attributes with keys '{col}_mode' and '{col}_pct' for each class,
        plus 'Cluster25_mode' and 'Cluster25_pct'
    """
    # Spatial overlay
    overlay_result = gpd.overlay(polygon_gdf, landscape_gdf, how='intersection')
    
    if len(overlay_result) == 0:
        # No intersection - return null values
        result = {}
        for col in class_cols:
            result[f"{col}_mode"] = None
            result[f"{col}_pct"] = 0.0
        result['Cluster25_mode'] = None
        result['Cluster25_pct'] = 0.0
        return result
    
    # Calculate overlap areas
    overlay_result['overlap_area'] = overlay_result.geometry.area
    total_overlap_area = overlay_result['overlap_area'].sum()
    
    result = {}
    
    # Process each class attribute
    for col in class_cols:
        class_areas = overlay_result.groupby(col)['overlap_area'].sum().sort_values(ascending=False)
        if len(class_areas) > 0:
            dominant_class = class_areas.index[0]
            dominant_area = class_areas.iloc[0]
            dominant_pct = (dominant_area / total_overlap_area) * 100 if total_overlap_area > 0 else 0
            
            result[f"{col}_mode"] = dominant_class
            result[f"{col}_pct"] = round(dominant_pct, 2)
        else:
            result[f"{col}_mode"] = None
            result[f"{col}_pct"] = 0.0
    
    # Process Cluster25
    if 'Cluster25' in overlay_result.columns:
        cluster_areas = overlay_result.groupby('Cluster25')['overlap_area'].sum().sort_values(ascending=False)
        if len(cluster_areas) > 0:
            dominant_cluster = cluster_areas.index[0]
            dominant_cluster_area = cluster_areas.iloc[0]
            dominant_cluster_pct = (dominant_cluster_area / total_overlap_area) * 100 if total_overlap_area > 0 else 0
            
            result['Cluster25_mode'] = int(dominant_cluster)
            result['Cluster25_pct'] = round(dominant_cluster_pct, 2)
        else:
            result['Cluster25_mode'] = None
            result['Cluster25_pct'] = 0.0
    else:
        result['Cluster25_mode'] = None
        result['Cluster25_pct'] = 0.0
    
    return result


def get_lst_raster_files(city_name: str, seviri_base_path: Path) -> tuple:
    """
    Find day and night LST raster files for a city.
    
    Parameters
    ----------
    city_name : str
        City name
    seviri_base_path : Path
        Base path to SEVIRI LST data (e.g., 'data/outputs/04_trend_analysis_daily/SEVIRI_LST')
        
    Returns
    -------
    tuple
        (day_file, night_file) as Path objects, or (None, None) if not found
    """
    city_lst_dir = seviri_base_path / f"City_{city_name}"
    
    if not city_lst_dir.exists():
        return None, None
    
    # Try to find day/night rasters
    day_pattern = f"{city_name}_SEVIRI_day_*_median_WGS84_1km_clipped.tif"
    night_pattern = f"{city_name}_SEVIRI_night_*_median_WGS84_1km_clipped.tif"
    
    day_files = list(city_lst_dir.glob(day_pattern))
    night_files = list(city_lst_dir.glob(night_pattern))
    
    day_file = day_files[0] if day_files else None
    night_file = night_files[0] if night_files else None
    
    return day_file, night_file


def extract_lst_statistics(polygon_gdf: gpd.GeoDataFrame, 
                          lst_raster_path: Path,
                          valid_range: tuple = (0, 100)) -> dict:
    """
    Extract LST statistics from raster for a polygon via masking.
    
    Parameters
    ----------
    polygon_gdf : gpd.GeoDataFrame
        Single-row GeoDataFrame with polygon geometry
    lst_raster_path : Path
        Path to LST raster file
    valid_range : tuple, optional
        Valid LST range (min, max) for filtering (default: 0-100°C)
        
    Returns
    -------
    dict
        LST statistics (min, mean, max, std, median, n_pixels) or None if extraction fails
    """
    if not RASTERIO_AVAILABLE:
        print("⚠️ rasterio not available - LST extraction skipped")
        return None
    
    if not lst_raster_path.exists():
        return None
    
    try:
        from rasterio.mask import mask as rasterio_mask
        
        with rasterio.open(lst_raster_path) as src:
            # Reproject polygon to raster CRS if needed
            poly_geom = polygon_gdf.to_crs(src.crs).geometry.iloc[0]
            
            # Mask raster by polygon
            masked_data, masked_transform = rasterio_mask(src, [poly_geom], crop=True)
            lst_values = masked_data[0]
            
            # Filter valid LST range
            lst_valid = lst_values[(lst_values > valid_range[0]) & (lst_values < valid_range[1])]
            
            if len(lst_valid) == 0:
                return None
            
            # Calculate statistics
            return {
                'min': float(np.min(lst_valid)),
                'mean': float(np.mean(lst_valid)),
                'max': float(np.max(lst_valid)),
                'std': float(np.std(lst_valid)),
                'median': float(np.median(lst_valid)),
                'n_pixels': int(len(lst_valid))
            }
    except Exception as e:
        print(f"    ⚠️ LST extraction failed: {e}")
        return None


def export_hotspot_polygons(gdf: gpd.GeoDataFrame, 
                           output_dir: Path,
                           primary_crs: str = "EPSG:4326",
                           web_crs: str = "EPSG:3857") -> dict:
    """
    Export hotspot polygons to multiple CRS formats.
    
    Parameters
    ----------
    gdf : gpd.GeoDataFrame
        Hotspot polygons with all attributes
    output_dir : Path
        Output directory for GeoJSON files
    primary_crs : str, optional
        Primary CRS (default: EPSG:4326 - WGS84)
    web_crs : str, optional
        Web mapping CRS (default: EPSG:3857 - Web Mercator)
        
    Returns
    -------
    dict
        Dictionary with keys 'primary' and 'web', each containing:
        - 'path': Path to exported file
        - 'size_mb': File size in MB
        - 'crs': CRS string
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True, parents=True)
    
    results = {}
    
    # Export 1: Primary CRS (WGS84)
    if str(gdf.crs) != primary_crs:
        gdf_primary = gdf.to_crs(primary_crs)
    else:
        gdf_primary = gdf
    
    primary_path = output_dir / f"hotspot_polygons_{primary_crs.replace(':', '')}.geojson"
    gdf_primary.to_file(primary_path, driver='GeoJSON')
    
    results['primary'] = {
        'path': primary_path,
        'size_mb': primary_path.stat().st_size / 1024 / 1024,
        'crs': primary_crs
    }
    
    # Export 2: Web CRS (Web Mercator)
    if str(gdf.crs) != web_crs:
        gdf_web = gdf.to_crs(web_crs)
    else:
        gdf_web = gdf
    
    web_path = output_dir / f"hotspot_polygons_{web_crs.replace(':', '')}.geojson"
    gdf_web.to_file(web_path, driver='GeoJSON')
    
    results['web'] = {
        'path': web_path,
        'size_mb': web_path.stat().st_size / 1024 / 1024,
        'crs': web_crs
    }
    
    return results


# =============================================================================
# GHSL POPULATION ENRICHMENT FUNCTIONS (Section 4.4)
# =============================================================================

def download_ghsl_population_raster(
    ghsl_year: int,
    ghsl_pop_config: dict,
    gee_config: dict,
    force: bool = False,
) -> Path:
    """
    Download the national Nigeria GHSL population raster from GEE at 1 km.

    The raster is saved permanently to ``data/inputs/geospatial_features/``
    and reused on subsequent runs (skip-if-exists logic).

    Parameters
    ----------
    ghsl_year : int
        GHSL epoch year (e.g. 2025).
    ghsl_pop_config : dict
        ``config.GHSL_POP_CONFIG`` dictionary with keys
        ``gee_asset``, ``scale``, ``crs``, ``output_dir``,
        ``filename_template``, ``nigeria_bounds``, ``boundary_geojson``.
    gee_config : dict
        ``config.GEE_CONFIG`` dictionary (for project_id and service_json).
    force : bool, optional
        Re-download even when the file already exists (default False).

    Returns
    -------
    pathlib.Path
        Absolute path to the local GeoTIFF file.
    """
    import ee
    import requests
    import zipfile
    import io

    output_dir = Path(ghsl_pop_config['output_dir'])
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = ghsl_pop_config['filename_template'].format(year=ghsl_year)
    output_path = output_dir / filename

    # ---- skip logic ----
    if output_path.exists() and not force:
        size_mb = output_path.stat().st_size / 1024 / 1024
        print(f"✓ GHSL raster already exists: {output_path.name} ({size_mb:.2f} MB) — skipping download")
        return output_path

    print(f"Downloading GHSL POP {ghsl_year} for Nigeria at {ghsl_pop_config['scale']}m ...")

    # Initialise GEE (may already be initialised — safe to call again)
    try:
        ee.Initialize(project=gee_config['project_id'])
    except Exception:
        service_json = gee_config.get('service_json', '')
        if service_json and Path(service_json).exists():
            credentials = ee.ServiceAccountCredentials(
                email=None, key_file=service_json
            )
            ee.Initialize(credentials=credentials, project=gee_config['project_id'])
        else:
            ee.Initialize(project=gee_config['project_id'])

    # Load GHSL image for the requested year
    asset_id = f"{ghsl_pop_config['gee_asset']}/{ghsl_year}"
    image = ee.Image(asset_id).select('population_count')

    # Define Nigeria region from boundary GeoJSON if available, else fallback to bbox
    boundary_path = Path(ghsl_pop_config['boundary_geojson'])
    if boundary_path.exists():
        nigeria_gdf = gpd.read_file(boundary_path)
        nigeria_geom = nigeria_gdf.geometry.unary_union
        # Simplify boundary for GEE (complex polygons cause 400 errors)
        nigeria_geom_simple = nigeria_geom.simplify(0.01, preserve_topology=True)
        import shapely.geometry as sg
        nigeria_ee = ee.Geometry(sg.mapping(nigeria_geom_simple))
        # Use bounding box for download region (clip handles the shape)
        bounds = nigeria_geom.bounds  # (minx, miny, maxx, maxy)
        download_region = ee.Geometry.Rectangle([bounds[0], bounds[1], bounds[2], bounds[3]])
        print(f"  Using Nigeria boundary from {boundary_path.name} (simplified for GEE)")
    else:
        w, s, e, n = ghsl_pop_config['nigeria_bounds']
        nigeria_ee = ee.Geometry.Rectangle([w, s, e, n])
        download_region = nigeria_ee
        print(f"  Using bounding box fallback: {ghsl_pop_config['nigeria_bounds']}")

    # Aggregate 100 m → 1 km using sum (population is additive)
    # Download at native resolution and let the scale parameter handle resampling.
    # For population data, we use reduceResolution server-side to get proper sums.
    scale = ghsl_pop_config['scale']
    crs = ghsl_pop_config['crs']

    # Clip to Nigeria first (reduces data volume)
    image_clipped = image.clip(nigeria_ee)

    # Download via getDownloadURL
    # scale=1000 requests 1 km pixels. Without reduceResolution, GEE uses
    # default (nearest-neighbour) resampling, which is imperfect for
    # population counts but acceptable at national overview level.
    # The per-polygon zonal sums are extracted later at this resolution.
    try:
        url = image_clipped.getDownloadURL({
            'scale': scale,
            'crs': crs,
            'region': download_region,
            'format': 'GEO_TIFF',
            'filePerBand': False,
        })
    except Exception as e:
        print(f"  ⚠ getDownloadURL failed ({e}), trying with bbox fallback ...")
        w, s, e_lon, n = ghsl_pop_config['nigeria_bounds']
        download_region = ee.Geometry.Rectangle([w, s, e_lon, n])
        image_clipped = image.clip(download_region)
        url = image_clipped.getDownloadURL({
            'scale': scale,
            'crs': crs,
            'region': download_region,
            'format': 'GEO_TIFF',
            'filePerBand': False,
        })

    print(f"  Fetching from GEE ...")
    response = requests.get(url, timeout=600)
    response.raise_for_status()

    # GEE may return a zip or raw tiff depending on size
    content_type = response.headers.get('Content-Type', '')
    if 'zip' in content_type or response.content[:4] == b'PK\x03\x04':
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            tif_names = [n for n in zf.namelist() if n.endswith('.tif')]
            if not tif_names:
                raise RuntimeError("No .tif found inside GEE zip response")
            with open(output_path, 'wb') as f:
                f.write(zf.read(tif_names[0]))
    else:
        with open(output_path, 'wb') as f:
            f.write(response.content)

    size_mb = output_path.stat().st_size / 1024 / 1024
    print(f"  ✓ Saved: {output_path.name} ({size_mb:.2f} MB)")
    return output_path


def extract_population_statistics(
    polygon_gdf: gpd.GeoDataFrame,
    ghsl_raster_path: Path,
) -> pd.DataFrame:
    """
    Extract GHSL population statistics for every polygon in a GeoDataFrame.

    Uses the same ``rasterio.mask`` pattern as ``extract_lst_statistics()``
    for consistency.

    Parameters
    ----------
    polygon_gdf : gpd.GeoDataFrame
        GeoDataFrame with polygon geometries (any CRS — will be reprojected).
    ghsl_raster_path : Path
        Path to the national GHSL GeoTIFF (1 km resolution).

    Returns
    -------
    pd.DataFrame
        One row per polygon with columns:
        ``pop_total`` (float), ``pop_density_km2`` (float).
    """
    if not RASTERIO_AVAILABLE:
        print("⚠️ rasterio not available — population extraction skipped")
        return pd.DataFrame({
            'pop_total': [None] * len(polygon_gdf),
            'pop_density_km2': [None] * len(polygon_gdf),
        })

    from rasterio.mask import mask as rasterio_mask

    results = []

    with rasterio.open(ghsl_raster_path) as src:
        raster_crs = src.crs
        # Reproject all polygons to raster CRS once
        gdf_reproj = polygon_gdf.to_crs(raster_crs)

        for idx, row in gdf_reproj.iterrows():
            try:
                geom = row.geometry
                masked_data, _ = rasterio_mask(src, [geom], crop=True, nodata=np.nan)
                values = masked_data[0]

                # Filter out nodata / negative values
                valid = values[(~np.isnan(values)) & (values >= 0)]

                if len(valid) == 0:
                    results.append({'pop_total': 0.0, 'pop_density_km2': 0.0})
                    continue

                pop_total = float(np.nansum(valid))

                # Area in km² (from original CRS row in polygon_gdf)
                orig_row = polygon_gdf.loc[idx]
                area_km2 = orig_row.get('area_km2', None)
                if area_km2 is None or area_km2 == 0:
                    # Compute from geometry in a projected CRS
                    geom_proj = gpd.GeoSeries([orig_row.geometry], crs=polygon_gdf.crs).to_crs('EPSG:3857')
                    area_km2 = geom_proj.area.iloc[0] / 1e6

                pop_density = pop_total / area_km2 if area_km2 > 0 else 0.0

                results.append({
                    'pop_total': round(pop_total, 1),
                    'pop_density_km2': round(pop_density, 1),
                })
            except Exception as e:
                print(f"    ⚠️ Population extraction failed for polygon {idx}: {e}")
                results.append({'pop_total': None, 'pop_density_km2': None})

    return pd.DataFrame(results, index=polygon_gdf.index)


# =============================================================================
# SURVEY VALIDATION FUNCTIONS (Section 5)
# =============================================================================

def load_survey_data(survey_path=None, cities=None):
    """
    Load and preprocess stakeholder survey data with identified hotspot/coolspot locations.
    
    Parameters
    ----------
    survey_path : Path, optional
        Path to survey CSV file (defaults to config.SURVEY_DATA_PATH)
    cities : list, optional
        List of cities to filter (if None, includes all)
        
    Returns
    -------
    gpd.GeoDataFrame
        Survey responses with geometry where respondents identified specific hotspots/coolspots
        
    Notes
    -----
    - Uses `lat_spot`, `long_spot` coordinates (where respondents marked locations)
    - Uses `feature_spot` column to classify: 'hotspot1', 'hotspot2', 'coolspot1', 'coolspot2'
    - Only includes responses where respondents actively identified a spot
    """
    from config import SURVEY_DATA_PATH
    import pandas as pd
    import geopandas as gpd
    from shapely.geometry import Point
    
    if survey_path is None:
        survey_path = SURVEY_DATA_PATH
    
    # Load survey data
    df = pd.read_csv(survey_path)
    
    # Filter for cities if specified (use matched_city_y = workshop city, not matched_city_x = registered cities)
    if cities is not None:
        df = df[df['matched_city_y'].isin(cities)].copy()
    
    # Extract relevant columns (use matched_city_y for actual workshop location)
    survey_clean = df[[
        'pid', 'matched_city_y', 'lat_spot', 'long_spot',
        'feature_spot', '62_knowledge_hotspots', '60_diurnal_severity_heat'
    ]].copy()
    
    # Rename columns for clarity
    survey_clean.columns = [
        'pid', 'city', 'spot_latitude', 'spot_longitude',
        'feature_type', 'knows_hotspots', 'heat_severity'
    ]
    
    # Filter out rows with missing coordinates or missing feature type
    survey_clean = survey_clean.dropna(subset=['spot_latitude', 'spot_longitude', 'feature_type'])
    
    # Create spot classification (hotspot vs coolspot)
    def classify_spot(feature):
        feature_lower = str(feature).lower()
        if 'hotspot' in feature_lower:
            return 'Hotspot'
        elif 'coolspot' in feature_lower:
            return 'Coolspot'
        else:
            return None  # Exclude other features (veg_specie, etc.)
    
    survey_clean['spot_type'] = survey_clean['feature_type'].apply(classify_spot)
    
    # Filter to only hotspots and coolspots (exclude vegetation species and other features)
    # Keep both types for validation and visualization
    survey_clean = survey_clean[survey_clean['spot_type'].notna()].copy()
    
    # Deduplicate: Each stakeholder (pid) can identify multiple spots (hotspot1, hotspot2, coolspot1, etc.)
    # Remove duplicate rows where the same pid identified the same feature_type at the same coordinates
    survey_clean = survey_clean.drop_duplicates(subset=['pid', 'feature_type', 'spot_latitude', 'spot_longitude'])
    
    # Create geometry
    geometry = [Point(xy) for xy in zip(survey_clean['spot_longitude'], survey_clean['spot_latitude'])]
    
    # Create GeoDataFrame
    survey_gdf = gpd.GeoDataFrame(
        survey_clean,
        geometry=geometry,
        crs='EPSG:4326'
    )
    
    return survey_gdf
    survey_gdf = gpd.GeoDataFrame(survey_clean, geometry=geometry, crs='EPSG:4326')
    
    return survey_gdf


def compute_spatial_intersection(hotspot_gdf, survey_gdf, buffer_km=0.5):
    """
    Compute spatial intersection between hotspot polygons and survey points.
    
    Parameters
    ----------
    hotspot_gdf : gpd.GeoDataFrame
        Hotspot polygons
    survey_gdf : gpd.GeoDataFrame
        Survey points with spot type (each row = one identified spot by a stakeholder)
        Note: Same stakeholder (pid) can identify multiple spots (hotspot1, hotspot2, etc.)
    buffer_km : float
        Buffer distance in kilometers
        
    Returns
    -------
    list of dict
        Intersection statistics for each city/method/period combination
        Includes counts of spots AND unique stakeholders
    """
    import geopandas as gpd
    
    # Ensure both are in same CRS (use projected CRS for buffering)
    hotspot_proj = hotspot_gdf.to_crs('EPSG:3857')  # Web Mercator (meters)
    survey_proj = survey_gdf.to_crs('EPSG:3857')
    
    buffer_m = buffer_km * 1000  # Convert km to meters
    
    results = []
    
    # Group by city, method, period
    for (city, method, period), group in hotspot_proj.groupby(['city', 'method', 'period']):
        # Buffer hotspot polygons
        hotspots_buffered = group.copy()
        hotspots_buffered['geometry'] = hotspots_buffered.buffer(buffer_m)
        
        # Get survey points for this city
        city_survey = survey_proj[survey_proj['city'] == city]
        
        if len(city_survey) == 0:
            continue
        
        # Spatial join to find points inside buffered hotspots
        points_in_hotspots = gpd.sjoin(
            city_survey, 
            hotspots_buffered[['geometry']], 
            how='inner', 
            predicate='within'
        )
        
        # Count survey points
        total_survey_points = len(city_survey)
        points_inside = len(points_in_hotspots)
        points_outside = total_survey_points - points_inside
        
        # Count identified hotspot locations (ground truth)
        hotspot_points_total = len(city_survey[city_survey['spot_type'] == 'Hotspot'])
        hotspot_points_inside = len(points_in_hotspots[points_in_hotspots['spot_type'] == 'Hotspot'])
        hotspot_points_outside = hotspot_points_total - hotspot_points_inside
        
        # Count unique stakeholders
        unique_stakeholders_total = city_survey['pid'].nunique()
        unique_stakeholders_inside = points_in_hotspots['pid'].nunique() if len(points_in_hotspots) > 0 else 0
        
        results.append({
            'city': city,
            'method': method,
            'period': period,
            'survey_points_total': total_survey_points,
            'survey_points_inside': points_inside,
            'survey_points_outside': points_outside,
            'hotspot_points_total': hotspot_points_total,
            'hotspot_points_inside': hotspot_points_inside,
            'hotspot_points_outside': hotspot_points_outside,
            'unique_stakeholders_total': unique_stakeholders_total,
            'unique_stakeholders_inside': unique_stakeholders_inside
        })
    
    return results


def calculate_validation_metrics(intersection_results):
    """
    Calculate validation metrics (TP, FP, FN, Precision, Recall, F1) from intersection results.
    
    Parameters
    ----------
    intersection_results : list of dict
        Results from compute_spatial_intersection()
        
    Returns
    -------
    list of dict
        Validation metrics for each configuration
    """
    metrics = []
    
    for result in intersection_results:
        # True Positives: Stakeholder-identified hotspot points inside detected hotspots
        TP = result['hotspot_points_inside']
        
        # False Positives: Coolspot points inside detected hotspots (should be cool, but detected as hot)
        FP = result['survey_points_inside'] - result['hotspot_points_inside']
        
        # False Negatives: Stakeholder-identified hotspot points outside detected hotspots
        FN = result['hotspot_points_outside']
        
        # True Negatives: Non-heat complaint points outside hotspots
        # TN = result['survey_points_outside'] - result['heat_points_outside']
        
        # Calculate metrics
        precision = TP / (TP + FP) if (TP + FP) > 0 else 0
        recall = TP / (TP + FN) if (TP + FN) > 0 else 0
        f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
        
        metrics.append({
            'city': result['city'],
            'method': result['method'],
            'period': result['period'],
            'TP': TP,
            'FP': FP,
            'FN': FN,
            'precision': precision,
            'recall': recall,
            'f1_score': f1_score,
            'total_survey_points': result['survey_points_total'],
            'hotspot_points_total': result['hotspot_points_total']
        })
    
    return metrics