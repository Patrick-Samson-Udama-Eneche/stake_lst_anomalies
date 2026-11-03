"""
Visualization Utilities
=======================

Functions for creating AOI maps, population plots, and interactive visualizations.
Maintains exact styling and layout from original notebook.
"""

import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.gridspec import GridSpec
from matplotlib.colors import LinearSegmentedColormap
import numpy as np
import pandas as pd
import geopandas as gpd
import folium
from folium import plugins
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import warnings

from src.data_io import export_figure_set

try:
    import config
except ImportError:
    class Config:
        FIGURE_DPI = 300
        WGS84 = "EPSG:4326"
    config = Config()

warnings.filterwarnings('ignore')


def create_aoi_map(aoi_results: Dict[str, Any], current_city: str, 
                   save_path: Optional[str] = None, 
                   figsize: Tuple[float, float] = (8, 5)) -> plt.Figure:
    """
    Create comprehensive AOI visualization with cartographic elements.
    
    Args:
        aoi_results: Results from process_city_aoi function
        current_city: Name of the current city
        save_path: Optional path to save the figure
        figsize: Figure size (width, height)
        
    Returns:
        Matplotlib figure object
    """
    # Extract data from results
    city_gdf = aoi_results['city_gdf']
    main_polygon_gdf = aoi_results['main_polygon_gdf']
    adjacent_gdf = aoi_results['adjacent_gdf']
    buffer_gdf = aoi_results['buffer_gdf']
    aoi_gdf = aoi_results['aoi_gdf']
    cities_in_aoi_gdf = aoi_results['cities_in_aoi_gdf']
    comprehensive_stats = aoi_results['comprehensive_stats']
    metrics = aoi_results['metrics']
    
    # Convert to lat/lon for plotting
    city_gdf_plot = city_gdf.to_crs(config.WGS84)
    main_polygon_gdf_plot = main_polygon_gdf.to_crs(config.WGS84)
    buffer_gdf_plot = buffer_gdf.to_crs(config.WGS84)
    aoi_gdf_plot = aoi_gdf.to_crs(config.WGS84)
    
    if not adjacent_gdf.empty:
        adjacent_gdf_plot = adjacent_gdf.to_crs(config.WGS84)
    
    if not cities_in_aoi_gdf.empty:
        cities_in_aoi_gdf_plot = cities_in_aoi_gdf.to_crs(config.WGS84)
    
    # Create figure
    fig, ax = plt.subplots(1, 1, figsize=figsize)
    
    # Plot layers
    aoi_gdf_plot.plot(ax=ax, color='none', edgecolor='purple', linewidth=3, label='AOI Boundary')
    buffer_gdf_plot.plot(ax=ax, color='lightblue', alpha=0.3, edgecolor='blue', linewidth=1, label='2km Buffer Zone')
    main_polygon_gdf_plot.plot(ax=ax, color='red', alpha=0.7, edgecolor='darkred', linewidth=2, label='Main Urban Polygon')
    
    if not adjacent_gdf.empty:
        adjacent_gdf_plot.plot(ax=ax, color='orange', alpha=0.5, edgecolor='darkorange', linewidth=1, label='Adjacent Polygons')
    
    # Plot cities with names
    if not cities_in_aoi_gdf.empty:
        cities_in_aoi_gdf_plot.plot(ax=ax, color='green', markersize=80, marker='o',
                                   edgecolor='darkgreen', linewidth=1, alpha=0.8, label='Cities in AOI')
        
        # Add city names
        for idx, city in cities_in_aoi_gdf_plot.iterrows():
            city_name = city['Urban Agglomeration']
            if city_name == current_city:
                # Highlight target city
                ax.scatter(city.geometry.x, city.geometry.y, color='red', s=120, marker='*',
                          edgecolors='white', linewidth=2, zorder=10, label='Target City')
                ax.annotate(city_name, (city.geometry.x, city.geometry.y),
                           xytext=(5, 5), textcoords='offset points', fontsize=10, fontweight='bold',
                           bbox=dict(boxstyle='round,pad=0.3', facecolor='red', alpha=0.7, edgecolor='white'))
            else:
                ax.annotate(city_name, (city.geometry.x, city.geometry.y),
                           xytext=(5, 5), textcoords='offset points', fontsize=9,
                           bbox=dict(boxstyle='round,pad=0.3', facecolor='lightgreen', alpha=0.7))
    
    # Add title and labels
    total_pop = comprehensive_stats['total_population_2024']
    cities_count = comprehensive_stats['cities_in_aoi_count']
    
    ax.set_title(f'AOI Delineation for {current_city} Metropolis\n'
                f'Area: {metrics["aoi_area_km2"]:.2f} km² | Major Urban Clusters Found: {cities_count}\n'
                f'Population: {total_pop:,.0f},000',
                fontsize=12, fontweight='bold', pad=20)
    ax.set_xlabel('Longitude (°E)', fontsize=9)
    ax.set_ylabel('Latitude (°N)', fontsize=9)
    
    # Add grid
    ax.grid(True, alpha=0.3, linestyle='--')
    
    # Add legend
    legend = ax.legend(loc='upper left', bbox_to_anchor=(0.01, 1), fontsize=8)
    legend.set_frame_on(True)
    legend.get_frame().set_facecolor('white')
    legend.get_frame().set_alpha(0.9)
    
    # Add north arrow using arrowprops only (robust across SVG/PDF encodings)
    ax.annotate('N', xy=(0.9, 0.9), xycoords='axes fraction', fontsize=16, fontweight='bold',
               ha='center', va='center',
               bbox=dict(boxstyle='circle', facecolor='white', edgecolor='black'))
    ax.annotate('', xy=(0.9, 0.88), xytext=(0.9, 0.83), xycoords='axes fraction',
               arrowprops=dict(arrowstyle='->', lw=1.8, color='black'))
    
    plt.tight_layout()
    
    # Save if path provided
    if save_path:
        save_path = Path(save_path)
        export_figure_set(
            fig,
            save_path,
            dpi=config.FIGURE_DPI,
            include_svg=True,
            include_pdf=True,
            bbox_inches='tight',
        )
        pdf_path = save_path.with_suffix('.pdf')
        svg_path = save_path.with_suffix('.svg')
        print(f"AOI map saved: {save_path.name} + {svg_path.name} + {pdf_path.name}")
    
    return fig


def create_interactive_map(aoi_results: Dict[str, Any], current_city: str) -> folium.Map:
    """
    Create interactive Folium map of the target AOI.
    
    Args:
        aoi_results: Results from process_city_aoi function
        current_city: Name of the current city
        
    Returns:
        Folium map object
    """
    # Extract and convert data
    main_polygon_gdf = aoi_results['main_polygon_gdf'].to_crs(config.WGS84)
    adjacent_gdf = aoi_results['adjacent_gdf']
    buffer_gdf = aoi_results['buffer_gdf'].to_crs(config.WGS84)
    aoi_gdf = aoi_results['aoi_gdf'].to_crs(config.WGS84)
    cities_in_aoi_gdf = aoi_results['cities_in_aoi_gdf']
    
    if not adjacent_gdf.empty:
        adjacent_gdf = adjacent_gdf.to_crs(config.WGS84)
    
    if not cities_in_aoi_gdf.empty:
        cities_in_aoi_gdf = cities_in_aoi_gdf.to_crs(config.WGS84)
    
    # Calculate center point
    aoi_bounds = aoi_gdf.total_bounds
    center_lat = (aoi_bounds[1] + aoi_bounds[3]) / 2
    center_lon = (aoi_bounds[0] + aoi_bounds[2]) / 2
    
    # Create map
    m = folium.Map(location=[center_lat, center_lon], zoom_start=11, tiles='OpenStreetMap')
    
    # Add AOI boundary
    folium.GeoJson(
        aoi_gdf.iloc[0].geometry,
        style_function=lambda x: {
            'fillColor': 'none',
            'color': 'purple',
            'weight': 3,
            'fillOpacity': 0
        },
        popup=f'AOI Boundary - {current_city}'
    ).add_to(m)
    
    # Add buffer zone
    folium.GeoJson(
        buffer_gdf.iloc[0].geometry,
        style_function=lambda x: {
            'fillColor': 'lightblue',
            'color': 'blue',
            'weight': 2,
            'fillOpacity': 0.3
        },
        popup='2km Buffer Zone'
    ).add_to(m)
    
    # Add main polygon
    folium.GeoJson(
        main_polygon_gdf.iloc[0].geometry,
        style_function=lambda x: {
            'fillColor': 'red',
            'color': 'darkred',
            'weight': 2,
            'fillOpacity': 0.7
        },
        popup='Main Urban Polygon'
    ).add_to(m)
    
    # Add adjacent polygons
    if not adjacent_gdf.empty:
        for idx, polygon in adjacent_gdf.iterrows():
            folium.GeoJson(
                polygon.geometry,
                style_function=lambda x: {
                    'fillColor': 'orange',
                    'color': 'darkorange',
                    'weight': 1,
                    'fillOpacity': 0.5
                },
                popup='Adjacent Urban Polygon'
            ).add_to(m)
    
    # Add cities
    if not cities_in_aoi_gdf.empty:
        for idx, city in cities_in_aoi_gdf.iterrows():
            city_name = city['Urban Agglomeration']
            pop_2024 = city['2024']
            
            # Different marker for target city
            if city_name == current_city:
                folium.Marker(
                    location=[city.geometry.y, city.geometry.x],
                    popup=f'<b>{city_name}</b><br>Population 2024: {pop_2024}k<br>(Target City)',
                    icon=folium.Icon(color='red', icon='star')
                ).add_to(m)
            else:
                folium.Marker(
                    location=[city.geometry.y, city.geometry.x],
                    popup=f'<b>{city_name}</b><br>Population 2024: {pop_2024}k',
                    icon=folium.Icon(color='green', icon='info-sign')
                ).add_to(m)
    
    # Add layer control
    folium.LayerControl().add_to(m)
    
    return m


def create_population_trends_plot(aoi_results: Dict[str, Any], current_city: str,
                                save_path: Optional[str] = None,
                                figsize: Tuple[float, float] = (6, 4)) -> Optional[plt.Figure]:
    """
    Create population trends analysis plot matching original notebook style.
    
    Args:
        aoi_results: Results from process_city_aoi function
        current_city: Name of the current city
        save_path: Optional path to save the figure
        figsize: Figure size (width, height)
        
    Returns:
        Matplotlib figure object or None if no data
    """
    cities_in_aoi_df = aoi_results['cities_in_aoi_df']
    
    if cities_in_aoi_df.empty:
        print("No population data available for plotting.")
        return None
    
    # Prepare year series — detect available range from data
    all_year_cols = sorted([c for c in cities_in_aoi_df.columns if c.isdigit()])
    pop_years = [y for y in all_year_cols if int(y) % 5 == 0]
    years_int = list(map(int, pop_years))
    
    # Create figure
    fig, ax = plt.subplots(figsize=figsize)
    
    # Total AOI population trend (single line per AOI)
    total_pop = [cities_in_aoi_df[yr].sum() for yr in pop_years if yr in cities_in_aoi_df.columns]
    ax.plot(years_int[:len(total_pop)], total_pop,
            label="Total AOI Population",
            color="navy", marker="s",
            linewidth=1, markersize=4, alpha=0.75)
    
    # 2024 marker and vertical line
    y_2024 = cities_in_aoi_df["2024"].sum()
    ax.axvline(2024, color="crimson", linestyle="--", linewidth=1)
    ax.scatter(2024, y_2024, marker="D", s=70,
               color="crimson", edgecolors="black", linewidth=1, zorder=5)
    
    # 2050 marker and vertical line
    y_2050 = cities_in_aoi_df["2050"].sum()
    ax.axvline(2050, color="darkgreen", linestyle="--", linewidth=1)
    ax.scatter(2050, y_2050, marker="D", s=70,
               color="darkgreen", edgecolors="black", linewidth=1, zorder=5)
    
    # Vertical 2024 label (bottom of line)
    y_max = max(total_pop) * 1.1
    ax.text(2024, y_max * 0.05,
            "2024", rotation=90,
            ha="right", va="bottom", fontsize=8, color="crimson")
    
    # Vertical 2050 label (middle of line)
    ax.text(2050, y_max * 0.5,
            "2050", rotation=90,
            ha="right", va="center", fontsize=8, color="darkgreen")
    
    # 2024 population annotation
    ax.annotate(f"Total Pop 2024:\n{y_2024:,.0f},000",
                xy=(2024, y_2024),
                xycoords="data",
                xytext=(0.45, 0.50),
                textcoords="axes fraction",
                fontsize=8, fontweight="bold", color="crimson",
                ha="left", va="center",
                arrowprops=dict(arrowstyle="->", color="black", lw=1))
    
    # 2050 population annotation
    ax.annotate(f"Total Pop 2050:\n{y_2050:,.0f},000",
                xy=(2050, y_2050),
                xycoords="data",
                xytext=(0.45, 0.65),
                textcoords="axes fraction",
                fontsize=8, fontweight="bold", color="darkgreen",
                ha="left", va="center",
                arrowprops=dict(arrowstyle="->", color="black", lw=1))
    
    # Population breakdown box (per-city contributions within AOI)
    if len(cities_in_aoi_df) > 1 and '2024' in cities_in_aoi_df.columns:
        breakdown_lines = ["Population Breakdown (2024):"]
        sorted_cities = cities_in_aoi_df.sort_values('2024', ascending=False, na_position='last')
        max_show = 8
        for i, (_, row) in enumerate(sorted_cities.iterrows()):
            if i >= max_show:
                remaining = len(sorted_cities) - max_show
                breakdown_lines.append(f"  ...+{remaining} more")
                break
            name = row['Urban Agglomeration']
            pop = row['2024']
            suffix = " \u2605" if name == current_city else ""
            pop_str = f"{pop:,.0f}k" if pd.notna(pop) else "n/a"
            breakdown_lines.append(f"  {name}: {pop_str}{suffix}")
        breakdown_lines.append(f"  Total: {y_2024:,.0f}k")

        ax.text(0.98, 0.02,
                "\n".join(breakdown_lines),
                transform=ax.transAxes, va="bottom", ha="right",
                fontsize=6.5,
                bbox=dict(boxstyle="round,pad=0.4",
                          facecolor="#fff9db", edgecolor="#8b6914", alpha=0.9))

    # Linear trend & regression equation
    slope, intercept = np.polyfit(years_int[:len(total_pop)], total_pop, 1)
    ax.plot(years_int[:len(total_pop)], np.poly1d([slope, intercept])(years_int[:len(total_pop)]),
            linestyle="--", color="grey", linewidth=1.2,
            label=f"Linear Trend (slope  {slope:,.0f}k/yr)")
    
    # Equation text
    eqn = f"y = {slope:,.0f}·x + {intercept:,.0f}"
    ax.text(0.2, 0.2, eqn, transform=ax.transAxes,
            fontsize=8, color="grey", ha="left", va="bottom",
            bbox=dict(boxstyle="round,pad=0.25",
                      facecolor="white", edgecolor="grey", alpha=0.7))
    
    # Growth rate box
    growth_rates = []
    for i in range(0, len(years_int[:len(total_pop)])-2, 2):
        if i+2 < len(total_pop):
            if total_pop[i] > 0:
                r = ((total_pop[i+2] / total_pop[i]) ** 0.1 - 1) * 100
                growth_rates.append(f"{years_int[i]}-{years_int[i+2]}: {r:5.2f}%/yr")
    # Overall growth rate — start from first non-zero population year
    if len(total_pop) >= 2:
        first_nz = next((j for j, p in enumerate(total_pop) if p > 0), None)
        if first_nz is not None and first_nz < len(total_pop) - 1:
            overall_span = years_int[len(total_pop)-1] - years_int[first_nz]
            overall_r = ((total_pop[-1] / total_pop[first_nz]) ** (1/overall_span) - 1) * 100
            growth_rates.append(f"Overall ({years_int[first_nz]}-{years_int[len(total_pop)-1]}): {overall_r:5.2f}%/yr")
    
    growth_text = "Growth Rates (10-yr):\n" + "\n".join(growth_rates)
    gr_box = ax.text(0.02, 0.98,
            growth_text,
            transform=ax.transAxes, va="top",
            fontsize=7.5,
            bbox=dict(boxstyle="round,pad=0.4",
                      facecolor="#d9ecff", edgecolor="#003d7a", alpha=0.9))
    
    # Formatting
    _yr0, _yr1 = years_int[0], years_int[-1]
    ax.set_title(f"Population Trends in {current_city} AOI ({_yr0}\u2013{_yr1})",
                 fontsize=12, fontweight="bold", pad=10)
    ax.set_xlabel("Year", fontsize=8)
    ax.set_ylabel("Population (thousands)", fontsize=8)
    ax.grid(True, alpha=0.25)
    ax.set_ylim(0, max(total_pop) * 1.1)
    
    # Legend — placed below the growth rate box with ~1cm gap
    # Estimate box height: (n_lines * ~line_height) in axes fraction
    n_gr_lines = len(growth_rates) + 1  # +1 for header
    gr_box_bottom = 0.98 - n_gr_lines * 0.055  # ~0.055 per line in axes frac
    legend_top = gr_box_bottom - 0.04  # ~1cm gap
    ax.legend(title="Legend",
              fontsize=7.5, title_fontsize=8.5,
              loc="upper left", bbox_to_anchor=(0.02, legend_top),
              frameon=True)
    
    plt.tight_layout()
    
    # Save if path provided
    if save_path:
        save_path = Path(save_path)
        # Save PNG
        fig.savefig(save_path, dpi=config.FIGURE_DPI, bbox_inches='tight')
        # Save PDF
        pdf_path = save_path.with_suffix('.pdf')
        fig.savefig(pdf_path, format='pdf', bbox_inches='tight')
        print(f"Population trends plot saved: {save_path.name} + {pdf_path.name}")
    
    return fig


def save_figures(aoi_results: Dict[str, Any], current_city: str, 
                figures_dir: str) -> Dict[str, str]:
    """
    Create and save all figures for a city.
    
    Args:
        aoi_results: Results from process_city_aoi function
        current_city: Name of the current city
        figures_dir: Directory to save figures
        
    Returns:
        Dictionary with paths of saved figures
    """
    figures_dir = Path(figures_dir)
    figures_dir.mkdir(parents=True, exist_ok=True)
    
    saved_figures = {}
    
    # Create and save AOI map
    aoi_map_png = figures_dir / f"{current_city}_AOI_Map.png"
    aoi_map_pdf = figures_dir / f"{current_city}_AOI_Map.pdf"
    
    aoi_fig = create_aoi_map(aoi_results, current_city)
    aoi_fig.savefig(aoi_map_png, dpi=config.FIGURE_DPI, bbox_inches='tight')
    aoi_fig.savefig(aoi_map_pdf, bbox_inches='tight')
    plt.close(aoi_fig)
    
    saved_figures['aoi_map_png'] = str(aoi_map_png)
    saved_figures['aoi_map_pdf'] = str(aoi_map_pdf)
    
    # Create and save population trends plot
    pop_plot_png = figures_dir / f"{current_city}_Population_Trends.png"
    pop_plot_pdf = figures_dir / f"{current_city}_Population_Trends.pdf"
    
    pop_fig = create_population_trends_plot(aoi_results, current_city)
    if pop_fig:
        pop_fig.savefig(pop_plot_png, dpi=config.FIGURE_DPI, bbox_inches='tight')
        pop_fig.savefig(pop_plot_pdf, bbox_inches='tight')
        plt.close(pop_fig)
        
        saved_figures['population_plot_png'] = str(pop_plot_png)
        saved_figures['population_plot_pdf'] = str(pop_plot_pdf)
    
    print(f"Figures saved to: {figures_dir}")
    print(f"Total figures: {len(saved_figures)} files")
    
    return saved_figures


def create_composite_population_trend(all_cities_results: Dict[str, Any],
                                      save_dir: Optional[str] = None,
                                      figsize: Tuple[float, float] = (10, 6),
                                      dpi: int = 300,
                                      mode: str = 'aoi',
                                      target_cities: Optional[List[str]] = None,
                                      all_cities_df: Optional[Any] = None) -> Tuple[plt.Figure, Dict[str, Any]]:
    """
    Create composite population trend plot for all selected cities.

    Dynamically detects the available year range from the data (works
    with both the legacy 1950–2035 CSV and the new 1975–2050 WUP 2025 CSV).

    Aggregates population across all cities and plots:
    - Total population curve with study-year and projection markers
    - Top-5 city individual lines (with 2024 population in legend)
    - Linear regression with R² annotation
    - 10-year growth rates
    - Projection shading for 2025–last year

    Args:
        all_cities_results: Dictionary of AOI results keyed by city name.
        save_dir: Directory to save SVG. If None, files are not saved.
        figsize: Figure size (width, height).
        dpi: Resolution for saved PNG.
        mode: 'aoi' for total AOI population (all cities in buffer),
              'individual' for target city population only.
        target_cities: Optional list of city names to include in
              mode='individual'. If None, all unique cities are included.
        all_cities_df: Optional DataFrame with ALL cities data. If provided in
              mode='individual', cities not in all_cities_results will be pulled
              from this DataFrame, ensuring complete population coverage.

    Returns:
        Tuple of (matplotlib Figure, summary statistics dict).
    """
    # Aggregate population
    aoi_pop_records = []
    target_set = set(target_cities) if target_cities else None
    if mode == 'individual':
        # Collect ALL unique individual cities across all AOIs
        seen_cities = set()
        for city_name, aoi_results in all_cities_results.items():
            aoi_df = aoi_results['cities_in_aoi_df']
            year_cols_all = sorted([c for c in aoi_df.columns if c.isdigit()])
            for _, row in aoi_df.iterrows():
                indiv_city = row['Urban Agglomeration']
                if indiv_city in seen_cities:
                    continue
                if target_set and indiv_city not in target_set:
                    continue
                seen_cities.add(indiv_city)
                record = {'AOI': indiv_city}
                for y in year_cols_all:
                    record[y] = row[y]
                aoi_pop_records.append(record)
        
        # ─ If all_cities_df provided, supplement missing cities for complete coverage ─
        # This ensures absorbed cities are included in population trend
        if all_cities_df is not None:
            year_cols_df = sorted([c for c in all_cities_df.columns if c.isdigit()])
            for _, city_row in all_cities_df.iterrows():
                city_name = city_row.get('Urban Agglomeration', '')
                if city_name and city_name not in seen_cities:
                    if target_set and city_name not in target_set:
                        continue
                    seen_cities.add(city_name)
                    record = {'AOI': city_name}
                    for y in year_cols_df:
                        record[y] = city_row[y]
                    aoi_pop_records.append(record)
    else:
        # Default: sum all cities within each AOI
        for city_name, aoi_results in all_cities_results.items():
            aoi_df = aoi_results['cities_in_aoi_df']
            year_cols_all = sorted([c for c in aoi_df.columns if c.isdigit()])
            record = {'AOI': city_name}
            for y in year_cols_all:
                record[y] = aoi_df[y].sum()
            aoi_pop_records.append(record)

    composite_df = pd.DataFrame(aoi_pop_records)

    # Year columns — detect from data
    all_year_cols = sorted([c for c in composite_df.columns if c.isdigit()])
    year_cols = [y for y in all_year_cols if y in composite_df.columns]
    years_int = list(map(int, year_cols))
    first_year = years_int[0]
    last_year = years_int[-1]

    # Sort by 2024 population
    composite_df_sorted = composite_df.sort_values('2024', ascending=False)

    # Total population per year (millions)
    total_pop = [composite_df[y].sum() / 1000 for y in year_cols]

    # Top-5 AOIs
    top5 = composite_df_sorted.head(5)

    #  Create figure 
    fig, ax = plt.subplots(figsize=figsize)

    # Projection shading
    ax.axvspan(2025, last_year, alpha=0.08, color='grey', zorder=0)
    proj_mid = (2025 + last_year) / 2
    ax.text(proj_mid, max(total_pop) * 1.03, 'Projected', ha='center',
            fontsize=10.4, fontstyle='italic', color='#666')

    # Top-5 AOI lines
    palette = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
    for i, (_, aoi_row) in enumerate(top5.iterrows()):
        name = aoi_row['AOI']
        pop_2024_aoi = aoi_row['2024'] / 1000
        aoi_pop = [aoi_row[y] / 1000 for y in year_cols]
        ax.plot(years_int, aoi_pop, label=f'{name} ({pop_2024_aoi:.1f} M)',
                color=palette[i], linewidth=1.0, alpha=0.65, markersize=0)

    # Total population line
    total_label = 'Total (all cities)' if mode == 'individual' else 'Total (all AOIs)'
    ax.plot(years_int, total_pop, label=total_label,
            color='navy', marker='s', linewidth=2.2, markersize=3, alpha=0.9, zorder=4)

    # 2024 marker
    idx_2024 = years_int.index(2024)
    y_2024 = total_pop[idx_2024]
    ax.axvline(2024, color='crimson', linestyle='--', linewidth=1, zorder=3)
    ax.scatter(2024, y_2024, marker='D', s=80,
               color='crimson', edgecolors='black', linewidth=1, zorder=6)
    ax.text(2024, ax.get_ylim()[1] * 0.92 if ax.get_ylim()[1] > 0 else y_2024 * 1.1,
            '2024', rotation=90, ha='right', va='bottom',
            fontsize=10.4, color='crimson')

    # Last-year marker
    idx_last = years_int.index(last_year)
    y_last = total_pop[idx_last]
    ax.scatter(last_year, y_last, marker='D', s=80,
               color='darkgreen', edgecolors='black', linewidth=1, zorder=6)

    # Population annotations
    ax.annotate(f"Total Pop 2024:\n{y_2024:.1f} M",
                xy=(2024, y_2024), xycoords='data',
                xytext=(0.50, 0.45), textcoords='axes fraction',
                fontsize=11.7, fontweight='bold', color='crimson',
                ha='left', va='center',
                arrowprops=dict(arrowstyle='->', color='black', lw=1))
    ax.annotate(f"Total Pop {last_year}:\n{y_last:.1f} M",
                xy=(last_year, y_last), xycoords='data',
                xytext=(0.50, 0.60), textcoords='axes fraction',
                fontsize=11.7, fontweight='bold', color='darkgreen',
                ha='left', va='center',
                arrowprops=dict(arrowstyle='->', color='black', lw=1))

    # Linear regression with R²
    slope, intercept = np.polyfit(years_int, total_pop, 1)
    y_pred = np.poly1d([slope, intercept])(years_int)
    ss_res = np.sum((np.array(total_pop) - y_pred) ** 2)
    ss_tot = np.sum((np.array(total_pop) - np.mean(total_pop)) ** 2)
    r_squared = 1 - ss_res / ss_tot

    ax.plot(years_int, y_pred, linestyle='--', color='grey', linewidth=1.2,
            label=f'Linear Trend \n(slope  {slope:,.2f} M/yr)')

    eqn = f'y = {slope:,.2f}·x + {intercept:,.1f}\n(R² = {r_squared:.4f})'
    ax.text(0.22, 0.15, eqn, transform=ax.transAxes,
            fontsize=10.4, color='grey', ha='left', va='bottom',
            bbox=dict(boxstyle='round,pad=0.25',
                      facecolor='white', edgecolor='grey', alpha=0.7))

    # 10-year growth rates
    milestone_years = list(range(first_year, last_year + 1, 10))
    if last_year not in milestone_years:
        milestone_years.append(last_year)
    growth_rates = []
    for i in range(len(milestone_years) - 1):
        y0, y1 = milestone_years[i], milestone_years[i + 1]
        if str(y0) in year_cols and str(y1) in year_cols:
            p0 = composite_df[str(y0)].sum()
            p1 = composite_df[str(y1)].sum()
            if p0 > 0:
                r = ((p1 / p0) ** (1 / (y1 - y0)) - 1) * 100
                growth_rates.append(f'{y0}–{y1}: {r:5.2f}%/yr')

    ax.text(0.02, 0.98,
            '10-yr Growth Rate:\n' + '\n'.join(growth_rates),
            transform=ax.transAxes, va='top', fontsize=9.75,
            bbox=dict(boxstyle='round,pad=0.4',
                      facecolor='#d9ecff', edgecolor='#003d7a', alpha=0.9))

    # Formatting
    n_aois = len(composite_df)
    if mode == 'individual':
        title_label = f'Composite Population Trend — {n_aois} Nigerian Cities (Individual, {first_year}–{last_year})'
    else:
        title_label = f'Composite Population Trend — {n_aois} Nigerian AOIs ({first_year}–{last_year})'
    ax.set_title(title_label, fontsize=16.9, fontweight='bold', pad=12)
    ax.set_xlabel('Year', fontsize=13)
    ax.set_ylabel('Population (Millions)', fontsize=13)
    ax.grid(True, alpha=0.25)
    ax.set_xlim(first_year - 2, last_year + 2)
    ax.set_ylim(0, max(total_pop) * 1.12)
    ax.legend(title='Legend', fontsize=10.4, title_fontsize=11.7,
              loc='upper left', bbox_to_anchor=(0.22, 1.0),
              frameon=True, framealpha=0.9)
    plt.tight_layout()

    # Save
    if save_dir is not None:
        save_path = Path(save_dir)
        save_path.mkdir(parents=True, exist_ok=True)
        suffix = '_Individual' if mode == 'individual' else ''
        base = save_path / f'Composite_Population_Trend{suffix}'
        fig.savefig(base.with_suffix('.png'), dpi=dpi, bbox_inches='tight', facecolor='white')
        fig.savefig(base.with_suffix('.pdf'), format='pdf', bbox_inches='tight', facecolor='white')
        fig.savefig(base.with_suffix('.svg'), format='svg', bbox_inches='tight', facecolor='white')
        print(f" Saved: {base.with_suffix('.png').name}")
        print(f" Saved: {base.with_suffix('.pdf').name}")
        print(f" Saved: {base.with_suffix('.svg').name}")

    # Summary statistics
    pop_first_k = composite_df[str(first_year)].sum()
    pop_2024_k = composite_df['2024'].sum() if '2024' in composite_df.columns else 0
    pop_last_k = composite_df[str(last_year)].sum()
    stats = {
        'n_aois': n_aois,
        'n_cities': n_aois,  # backward compat
        'first_year': first_year,
        'last_year': last_year,
        'pop_first_k': pop_first_k,
        'pop_2024_k': pop_2024_k,
        'pop_last_k': pop_last_k,
        # Legacy keys for backward compatibility
        'pop_1950_k': pop_first_k,
        'pop_2035_k': pop_last_k,
        'slope_M_per_yr': slope,
        'r_squared': r_squared,
    }

    return fig, stats


# ==============================================================================
# LST TEMPORAL ANALYSIS VISUALIZATIONS
# ==============================================================================

def create_combined_lst_heatmap(day_data, night_data, time_dim='year', output_path=None,
                                figsize=(16, 10), dpi=300):
    """
    Create side-by-side heatmaps for day and night LST.
    
    Parameters:
    -----------
    day_data : pd.DataFrame
        Day-time heatmap data
    night_data : pd.DataFrame
        Night-time heatmap data
    time_dim : str
        'year' or 'month'
    output_path : str, optional
        Path to save the figure
    figsize : tuple
        Figure size
    dpi : int
        DPI for saved figure
        
    Returns:
    --------
    matplotlib.figure.Figure
        The combined heatmap figure
    """
    import seaborn as sns
    from matplotlib.gridspec import GridSpec
    
    fig = plt.figure(figsize=figsize, dpi=dpi)
    gs = GridSpec(1, 2, figure=fig, wspace=0.3)
    
    # Day-time heatmap
    ax1 = fig.add_subplot(gs[0, 0])
    sns.heatmap(
        day_data,
        annot=True,
        fmt='.1f',
        cmap='YlOrRd',
        cbar_kws={'label': 'LST (°C)'},
        linewidths=0.5,
        linecolor='gray',
        ax=ax1
    )
    ax1.set_title('Day-time LST', fontsize=16, fontweight='bold', pad=15)
    ax1.set_xlabel('Year' if time_dim == 'year' else 'Month', fontsize=12)
    ax1.set_ylabel('City', fontsize=12)
    ax1.tick_params(axis='x', rotation=45)
    
    # Night-time heatmap (use warm LST palette)
    ax2 = fig.add_subplot(gs[0, 1])
    sns.heatmap(
        night_data,
        annot=True,
        fmt='.1f',
        cmap='YlOrRd',
        cbar_kws={'label': 'LST (°C)'},
        linewidths=0.5,
        linecolor='gray',
        ax=ax2
    )
    ax2.set_title('Night-time LST', fontsize=16, fontweight='bold', pad=15)
    ax2.set_xlabel('Year' if time_dim == 'year' else 'Month', fontsize=12)
    ax2.set_ylabel('')
    ax2.tick_params(axis='x', rotation=45)
    
    # Overall title
    time_label = 'Yearly' if time_dim == 'year' else 'Monthly Climatology'
    fig.suptitle(
        f'LST Median Across Nigerian Cities - {time_label}',
        fontsize=18,
        fontweight='bold',
        y=0.98
    )
    
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    
    if output_path:
        output_path = Path(output_path)
        # Save PNG
        plt.savefig(output_path, dpi=dpi, bbox_inches='tight')
        # Save PDF
        pdf_path = output_path.with_suffix('.pdf')
        plt.savefig(pdf_path, format='pdf', bbox_inches='tight')
        print(f' Saved combined heatmap to {output_path.name} + {pdf_path.name}')
    
    return fig


def create_lst_heatmap(data, lst_time, time_dim='year', output_path=None, dpi=300, 
                       cities_per_page=10, max_cities=None):
    """
    Create LST heatmap(s) with pagination for many cities, sorted warmest to coolest.
    
    Parameters:
    -----------
    data : pd.DataFrame
        Heatmap data (cities as rows, time as columns)
    lst_time : str
        'day' or 'night'
    time_dim : str
        'year' or 'month'
    output_path : str, optional
        Path to save the figure (page number appended when paginated)
    dpi : int
        DPI for saved figure (default 300, use higher for publication quality)
    cities_per_page : int
        Maximum cities per page when >5 cities (default: 10)
    max_cities : int, optional
        Maximum total cities to include (default: all cities)
        
    Returns:
    --------
    matplotlib.figure.Figure or list
        Single figure (≤5 cities) or list of figures (>5 cities)
    """
    import seaborn as sns
    import math
    
    if data.empty:
        print(f" No data to plot for {lst_time}-time {time_dim}")
        return None
    
    # Sort ALL cities by mean temperature (warmest first)
    data = data.copy()
    data['mean_temp'] = data.mean(axis=1)
    data = data.sort_values('mean_temp', ascending=False)  # Warmest first
    
    # Optionally limit total cities
    n_cities_total = len(data)
    if max_cities is not None and n_cities_total > max_cities:
        data = data.head(max_cities)
        n_cities_total = max_cities
        print(f"📊 Limited to top {max_cities} hottest cities")
    
    # Drop mean_temp column before plotting
    data = data.drop('mean_temp', axis=1)
    
    # For monthly data, convert month numbers to names
    if time_dim == 'month':
        month_names = {1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun',
                      7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'}
        data.columns = [month_names.get(int(col), col) for col in data.columns]
    
    # Determine pagination: ≤5 cities = single page (original format), >5 = paginate
    if n_cities_total <= 5:
        # Original compact format for small datasets
        return _create_single_heatmap(data, lst_time, time_dim, output_path, dpi, 
                                      compact=True)
    else:
        # Paginated format for many cities
        n_pages = math.ceil(n_cities_total / cities_per_page)
        figures = []
        
        print(f"📄 Creating {n_pages} page(s) with up to {cities_per_page} cities each")
        
        for page in range(n_pages):
            start_idx = page * cities_per_page
            end_idx = min(start_idx + cities_per_page, n_cities_total)
            page_data = data.iloc[start_idx:end_idx]
            
            # Generate page-specific output path
            if output_path:
                base_path = output_path.replace('.png', '')
                page_output = f"{base_path}_Page{page + 1}of{n_pages}.png"
            else:
                page_output = None
            
            # Create page title suffix
            page_info = f"Page {page + 1} of {n_pages} (Cities {start_idx + 1}-{end_idx})"
            
            fig = _create_single_heatmap(page_data, lst_time, time_dim, page_output, dpi,
                                         compact=False, page_info=page_info)
            figures.append(fig)
        
        return figures


def _create_single_heatmap(data, lst_time, time_dim, output_path, dpi, 
                           compact=False, page_info=None):
    """
    Internal function to create a single heatmap page.
    
    Parameters:
    -----------
    data : pd.DataFrame
        Pre-sorted heatmap data for this page
    lst_time : str
        'day' or 'night'
    time_dim : str
        'year' or 'month'
    output_path : str, optional
        Path to save figure
    dpi : int
        DPI for saving
    compact : bool
        Use compact sizing for ≤5 cities
    page_info : str, optional
        Page information to include in title
    """
    import seaborn as sns
    
    n_cities = len(data)
    n_periods = len(data.columns)
    
    if compact:
        # Original compact format for ≤5 cities
        if time_dim == 'month':
            fig_height = max(2.5, min(8, n_cities * 0.28))
            fig_width = max(7, min(16, n_periods * 0.45))
        else:
            fig_height = max(2.5, min(8, n_cities * 0.25))
            fig_width = max(8, min(18, n_periods * 0.32))
    else:
        # Half A4 vertical format (~8.27" x 5.85") for paginated heatmaps
        fig_width = 8.27  # A4 width in inches
        fig_height = 5.85  # Half A4 height
    
    # Font sizes
    if compact:
        title_fontsize = max(9, min(13, fig_height * 1.3))
        label_fontsize = max(8, min(11, fig_height * 1.1))
        tick_fontsize = max(7, min(9, fig_height * 0.85))
        annot_fontsize = max(5, min(7, fig_height * 0.7))
        cbar_labelsize = max(7, min(9, fig_height * 0.85))
    else:
        # Fixed sizes for paginated format
        title_fontsize = 12
        label_fontsize = 10
        tick_fontsize = 9
        annot_fontsize = 7
        cbar_labelsize = 9
    
    # Create figure
    fig, ax = plt.subplots(figsize=(fig_width, fig_height), dpi=dpi)
    
    # Use the same warm LST palette for day/night and data-driven thresholds.
    cmap = 'YlOrRd'
    cbar_label = 'LST (\u00b0C)'
    vals = data.values.flatten()
    vals = vals[~np.isnan(vals)]
    vmin, vmax = (np.nanmin(vals), np.nanmax(vals)) if len(vals) else (None, None)
    
    # Create heatmap with colorbar on right
    heatmap = sns.heatmap(
        data,
        annot=True,
        fmt='.1f',
        cmap=cmap,
        vmin=vmin,
        vmax=vmax,
        cbar_kws={
            'label': cbar_label,
            'shrink': 0.7 if not compact else 0.55,
            'aspect': 30 if not compact else 35,
            'pad': 0.02
        },
        linewidths=0.3 if not compact else 0.2,
        linecolor='gray',
        ax=ax,
        annot_kws={'fontsize': annot_fontsize}
    )
    
    # Adjust colorbar
    cbar = heatmap.collections[0].colorbar
    cbar.ax.tick_params(labelsize=tick_fontsize)
    cbar.set_label(cbar_label, size=cbar_labelsize)
    
    # Format title
    time_label = 'Year' if time_dim == 'year' else 'Month'
    title_time = 'Yearly' if time_dim == 'year' else 'Monthly Climatology'
    
    title = f'{lst_time.title()}-time LST - {title_time} (Warmest to Coolest)'
    if page_info:
        title = f'{title}\n{page_info}'
    
    ax.set_title(title, fontsize=title_fontsize, fontweight='bold', pad=10)
    ax.set_xlabel(time_label, fontsize=label_fontsize, fontweight='bold')
    ax.set_ylabel('City', fontsize=label_fontsize, fontweight='bold')
    
    # X-axis labels
    if time_dim == 'month':
        ax.tick_params(axis='x', rotation=0, labelsize=tick_fontsize)
    else:
        ax.tick_params(axis='x', rotation=45, labelsize=tick_fontsize)
    ax.tick_params(axis='y', rotation=0, labelsize=tick_fontsize)
    
    plt.tight_layout(pad=0.5)
    
    if output_path:
        fig.savefig(output_path, dpi=dpi, bbox_inches='tight')
        pdf_path = output_path.replace('.png', '.pdf')
        fig.savefig(pdf_path, format='pdf', bbox_inches='tight')
        print(f' Saved: {output_path.split("/")[-1].split(chr(92))[-1]}')
        plt.close(fig)
        return None
    
    return fig


def create_lst_heatmap_with_validation(data, lst_time, time_dim, validation_df, 
                                       output_path=None, dpi=300):
    """
    Create LST heatmap with stakeholder validation table on the right.
    
    Parameters:
    -----------
    data : pd.DataFrame
        Heatmap data (cities as rows, time as columns)
    lst_time : str
        'day' or 'night'
    time_dim : str
        'year' or 'month'
    validation_df : pd.DataFrame
        Validation data with columns: city, n_stakeholders, pct_perceived_warming, overall_agreement
    output_path : str, optional
        Path to save the figure
    dpi : int
        DPI for saved figure
    """
    import seaborn as sns
    from matplotlib.gridspec import GridSpec
    
    if data.empty:
        print(f" No data to plot for {lst_time}-time {time_dim}")
        return None
    
    # Sort cities by mean temperature
    data = data.copy()
    data['mean_temp'] = data.mean(axis=1)
    data = data.sort_values('mean_temp', ascending=True)
    city_order = data.index.tolist()
    data = data.drop('mean_temp', axis=1)
    
    # For monthly data, convert month numbers to names
    if time_dim == 'month':
        month_names = {1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun',
                      7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'}
        data.columns = [month_names.get(int(col), col) for col in data.columns]
    
    # Sort validation_df to match heatmap city order
    validation_df = validation_df.set_index('city').loc[city_order].reset_index()
    
    # Dynamic sizing
    n_cities = len(data)
    n_periods = len(data.columns)
    
    # More compact vertical spacing
    if time_dim == 'month':
        fig_height = max(2.5, min(8, n_cities * 0.18))
        heatmap_width = max(7, min(14, n_periods * 0.45))
    else:
        fig_height = max(2.5, min(8, n_cities * 0.16))
        heatmap_width = max(8, min(16, n_periods * 0.32))
    
    # Table width proportional to heatmap
    table_width = heatmap_width * 0.35
    total_width = heatmap_width + table_width + 0.5
    
    # Font sizes
    title_fontsize = max(9, min(13, fig_height * 1.3))
    label_fontsize = max(8, min(11, fig_height * 1.1))
    tick_fontsize = max(7, min(9, fig_height * 0.85))
    annot_fontsize = max(5, min(7, fig_height * 0.7))
    table_fontsize = max(6, min(8, fig_height * 0.75))
    
    # Create figure with GridSpec
    fig = plt.figure(figsize=(total_width, fig_height), dpi=dpi)
    gs = GridSpec(1, 2, figure=fig, width_ratios=[heatmap_width, table_width], 
                  wspace=0.02, left=0.05, right=0.98, top=0.92, bottom=0.12)
    
    # Heatmap subplot
    ax_heatmap = fig.add_subplot(gs[0, 0])
    
    # Use warm LST palette for consistency with LST/QA figures.
    cmap = 'YlOrRd'
    cbar_label = 'LST (\u00b0C)'
    vals = data.values.flatten()
    vals = vals[~np.isnan(vals)]
    vmin, vmax = (np.nanmin(vals), np.nanmax(vals)) if len(vals) else (None, None)
    
    # Create heatmap
    heatmap = sns.heatmap(
        data,
        annot=True,
        fmt='.1f',
        cmap=cmap,
        vmin=vmin,
        vmax=vmax,
        cbar_kws={'label': cbar_label, 'shrink': 0.5, 'aspect': 30, 'pad': 0.01},
        linewidths=0.15,
        linecolor='gray',
        ax=ax_heatmap,
        annot_kws={'fontsize': annot_fontsize}
    )
    
    # Adjust colorbar
    cbar = heatmap.collections[0].colorbar
    cbar.ax.tick_params(labelsize=tick_fontsize)
    cbar.set_label(cbar_label, size=label_fontsize)
    
    # Heatmap labels
    time_label = 'Year' if time_dim == 'year' else 'Month'
    ax_heatmap.set_xlabel(time_label, fontsize=label_fontsize, fontweight='bold')
    ax_heatmap.set_ylabel('City', fontsize=label_fontsize, fontweight='bold')
    
    if time_dim == 'month':
        ax_heatmap.tick_params(axis='x', rotation=0, labelsize=tick_fontsize)
    else:
        ax_heatmap.tick_params(axis='x', rotation=45, labelsize=tick_fontsize)
    ax_heatmap.tick_params(axis='y', rotation=0, labelsize=tick_fontsize)
    
    # Validation table subplot
    ax_table = fig.add_subplot(gs[0, 1])
    ax_table.axis('off')
    
    # Create table data
    table_data = []
    for _, row in validation_df.iterrows():
        if row['n_stakeholders'] == 0:
            table_data.append(['*', '*', '*'])
        else:
            table_data.append([
                f"{int(row['n_stakeholders'])}",
                f"{int(row['pct_perceived_warming'])}",
                f"{int(row['overall_agreement'])}" if row['overall_agreement'] >= 0 else '-'
            ])
    
    # Table column headers
    col_labels = ['No.\nstakeholders', 'Perceived\nwarming (%)', 'Overall\nagreement (%)']
    
    # Create table
    table = ax_table.table(
        cellText=table_data,
        rowLabels=validation_df['city'].tolist(),
        colLabels=col_labels,
        cellLoc='center',
        rowLoc='right',
        loc='center',
        bbox=[0, 0, 1, 1]
    )
    
    # Style table
    table.auto_set_font_size(False)
    table.set_fontsize(table_fontsize)
    table.scale(1, fig_height / (n_cities + 2))
    
    # Header styling
    for i in range(len(col_labels)):
        cell = table[(0, i)]
        cell.set_facecolor('#E8E8E8')
        cell.set_text_props(weight='bold', fontsize=table_fontsize)
        cell.set_edgecolor('black')
        cell.set_linewidth(1.5)
    
    # Row label styling (cities)
    for i in range(len(validation_df)):
        cell = table[(i+1, -1)]
        cell.set_facecolor('#F5F5F5')
        cell.set_text_props(weight='bold', fontsize=table_fontsize)
        cell.set_edgecolor('black')
        cell.set_linewidth(1.5)
    
    # Data cell styling
    for i in range(1, len(validation_df) + 1):
        for j in range(len(col_labels)):
            cell = table[(i, j)]
            cell.set_edgecolor('black')
            cell.set_linewidth(0.8)
    
    # Red neatline border
    ax_table.add_patch(plt.Rectangle((0, 0), 1, 1, fill=False, edgecolor='red', 
                                     linewidth=2, transform=ax_table.transAxes, zorder=10))
    
    # Table title
    ax_table.text(0.5, 1.05, 'STAKEHOLDER INPUT EVALUATION', 
                  ha='center', va='bottom', fontsize=title_fontsize,
                  fontweight='bold', transform=ax_table.transAxes)
    
    # Overall title
    time_label_title = 'Yearly' if time_dim == 'year' else 'Monthly Climatology'
    fig.suptitle(f'{lst_time.title()}-time LST - {time_label_title} (Warmest to Coolest)',
                 fontsize=title_fontsize + 1, fontweight='bold', y=0.98)
    
    if output_path:
        fig.savefig(output_path, dpi=dpi, bbox_inches='tight')
        pdf_path = output_path.replace('.png', '.pdf')
        fig.savefig(pdf_path, format='pdf', bbox_inches='tight')
        print(f' Saved {lst_time}-time {time_dim} heatmap with validation (SVG)')
        plt.close(fig)
        return None
    
    return fig


# =============================================================================
# DAILY LST VISUALIZATION FUNCTIONS (Notebook 04)
# =============================================================================

def plot_daily_lst_timeseries(
    df,
    city_name,
    dataset_name,
    day_night,
    output_dir=None,
    figsize=(14, 6),
    dpi=300
):
    """
    Plot daily LST time series with hot event highlighting.
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with 'date', 'lst_mean', and 'is_hot' columns
    city_name : str
        Name of city
    dataset_name : str
        Dataset name ('MODIS', 'ERA5', 'SEVIRI')
    day_night : str
        'day' or 'night'
    output_dir : str or Path, optional
        Directory to save figure
    figsize : tuple
        Figure size
    dpi : int
        Figure DPI
        
    Returns
    -------
    fig : matplotlib.figure.Figure
        Figure object
    """
    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    
    # Plot time series
    ax.plot(df['date'], df['lst_mean'], color='#2E86AB', linewidth=1.5, alpha=0.8, label='LST')
    
    # Highlight hot events
    if 'is_hot' in df.columns:
        hot_days = df[df['is_hot']]
        ax.scatter(hot_days['date'], hot_days['lst_mean'], color='#E63946', s=50, 
                   alpha=0.6, zorder=5, label='Hot Events')
    
    # Add mean line
    mean_lst = df['lst_mean'].mean()
    ax.axhline(mean_lst, color='#666', linestyle='--', linewidth=1, alpha=0.5, label=f'Mean: {mean_lst:.1f}°C')
    
    # Formatting
    ax.set_xlabel('Date', fontsize=12, fontweight='bold')
    ax.set_ylabel('LST (°C)', fontsize=12, fontweight='bold')
    ax.set_title(f'{city_name} - {dataset_name} {day_night.title()}-time LST (2024)', 
                 fontsize=14, fontweight='bold', pad=15)
    ax.legend(loc='best', frameon=True, fontsize=10)
    ax.grid(True, alpha=0.3, linestyle=':', linewidth=0.5)
    
    plt.tight_layout()
    
    # Save if output directory specified
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        png_path = output_dir / f'{dataset_name.lower()}_{day_night}_timeseries.png'
        pdf_path = output_dir / f'{dataset_name.lower()}_{day_night}_timeseries.pdf'
        
        fig.savefig(png_path, dpi=dpi, bbox_inches='tight')
        fig.savefig(pdf_path, format='pdf', bbox_inches='tight')
        
        plt.close(fig)
        return None
    
    return fig


def plot_persistent_events(
    df,
    city_name,
    dataset_name,
    day_night,
    output_dir=None,
    figsize=(14, 6),
    dpi=300
):
    """
    Plot persistent hot events with event duration annotation.
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with 'event_id', 'event_duration' columns
    city_name : str
        Name of city
    dataset_name : str
        Dataset name
    day_night : str
        'day' or 'night'
    output_dir : str or Path, optional
        Directory to save figure
    figsize : tuple
        Figure size
    dpi : int
        Figure DPI
        
    Returns
    -------
    fig : matplotlib.figure.Figure or None
    """
    # Filter persistent events
    persistent_df = df[df['event_id'] > 0].copy()
    
    if persistent_df.empty:
        print(f"No persistent events to plot for {dataset_name} {day_night}")
        return None
    
    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    
    # Plot full time series
    ax.plot(df['date'], df['lst_mean'], color='#A8DADC', linewidth=1, alpha=0.6, label='LST')
    
    # Highlight persistent events with different colors
    unique_events = persistent_df['event_id'].unique()
    colors = plt.cm.Reds(np.linspace(0.4, 0.9, len(unique_events)))
    
    for event_id, color in zip(unique_events, colors):
        event_df = persistent_df[persistent_df['event_id'] == event_id]
        duration = event_df['event_duration'].iloc[0]
        
        ax.plot(event_df['date'], event_df['lst_mean'], color=color, linewidth=2.5, 
                label=f'Event {event_id} ({duration}d)')
        
        # Annotate event duration
        mid_idx = len(event_df) // 2
        mid_date = event_df.iloc[mid_idx]['date']
        mid_lst = event_df.iloc[mid_idx]['lst_mean']
        
        ax.annotate(f'{duration}d', xy=(mid_date, mid_lst), 
                    xytext=(0, 10), textcoords='offset points',
                    ha='center', fontsize=9, fontweight='bold',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor=color, alpha=0.7))
    
    # Formatting
    ax.set_xlabel('Date', fontsize=12, fontweight='bold')
    ax.set_ylabel('LST (°C)', fontsize=12, fontweight='bold')
    ax.set_title(f'{city_name} - {dataset_name} Persistent Hot Events ({day_night.title()}-time)', 
                 fontsize=14, fontweight='bold', pad=15)
    ax.legend(loc='best', frameon=True, fontsize=9, ncol=2)
    ax.grid(True, alpha=0.3, linestyle=':', linewidth=0.5)
    
    plt.tight_layout()
    
    # Save
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        png_path = output_dir / f'{dataset_name.lower()}_{day_night}_persistent_events.png'
        pdf_path = output_dir / f'{dataset_name.lower()}_{day_night}_persistent_events.pdf'
        
        fig.savefig(png_path, dpi=dpi, bbox_inches='tight')
        fig.savefig(pdf_path, format='pdf', bbox_inches='tight')
        
        plt.close(fig)
        return None
    
    return fig


def plot_multi_city_dataset_comparison(
    comparison_results_list,
    dataset1_name='MODIS',
    dataset2_name='ERA5-Land',
    output_dir=None,
    figsize=None,
    dpi=300,
    cities_per_page=5
):
    """
    Create paginated multi-panel hex-bin plots comparing two datasets across
    multiple cities.

    When more than *cities_per_page* cities are supplied the results are split
    into pages of that size.  Each page is saved separately (``_Page1of3``,
    etc.) so that every figure remains a manageable height.

    Parameters
    ----------
    comparison_results_list : list of dict
        Each dict contains: 'city', 'day_comparison', 'night_comparison'.
    dataset1_name, dataset2_name : str
        Human-readable dataset labels (axes / title).
    output_dir : str or Path, optional
        Directory to save figures (SVG per page).
    figsize : tuple, optional
        Per-page size (auto-calculated if *None*).
    dpi : int
        Figure resolution.
    cities_per_page : int
        Maximum number of city rows per figure (default 5).

    Returns
    -------
    list[matplotlib.figure.Figure]
        One figure per page.  When only one page is needed a single-element
        list is returned for backward compatibility.
    """
    import math

    n_cities = len(comparison_results_list)
    n_pages = max(1, math.ceil(n_cities / cities_per_page))

    line_color = '#E63946'  # Red for 1:1 line
    day_cmap = 'Oranges'    # Warm colour-map for daytime hexbins
    night_cmap = 'Greys'    # Neutral colour-map for nighttime hexbins

    figures = []

    for page_idx in range(n_pages):
        start = page_idx * cities_per_page
        end = min(start + cities_per_page, n_cities)
        page_items = comparison_results_list[start:end]
        nrows = len(page_items)

        # Auto-calculate figure size per page
        if figsize is None:
            width = 14
            height = 4 * nrows
            page_figsize = (width, height)
        else:
            page_figsize = figsize

        fig, axes = plt.subplots(nrows, 2, figsize=page_figsize, dpi=dpi,
                                 squeeze=False)

        for i, result in enumerate(page_items):
            city = result['city']
            day_comp = result['day_comparison']
            night_comp = result['night_comparison']

            for col_idx, (comp, cmap, period_label) in enumerate([
                (day_comp, day_cmap, 'Daytime'),
                (night_comp, night_cmap, 'Nighttime'),
            ]):
                ax = axes[i, col_idx]
                merged = comp['merged_data']

                if merged.empty:
                    ax.text(0.5, 0.5, 'No data', transform=ax.transAxes,
                            ha='center', va='center', fontsize=10, color='gray')
                    ax.set_title(f'{city} - {period_label}', fontsize=11,
                                 fontweight='bold', pad=10)
                    continue

                # Resolve column names
                col1_cands = [c for c in merged.columns if dataset1_name in c]
                col2_cands = [c for c in merged.columns if dataset2_name in c]
                if not col1_cands or not col2_cands:
                    non_date = [c for c in merged.columns if c != 'date']
                    col1_cands = non_date[:1]
                    col2_cands = non_date[1:2]
                if not col1_cands or not col2_cands:
                    ax.text(0.5, 0.5, 'No matching columns',
                            transform=ax.transAxes, ha='center', va='center',
                            fontsize=10, color='gray')
                    ax.set_title(f'{city} - {period_label}', fontsize=11,
                                 fontweight='bold', pad=10)
                    continue

                x = merged[col1_cands[0]].dropna()
                y = merged[col2_cands[0]].reindex(x.index).dropna()
                x = x.reindex(y.index)

                # Choose between hexbin (many points) and scatter (few points)
                if len(x) >= 30:
                    hb = ax.hexbin(x, y, gridsize=25, cmap=cmap, mincnt=1,
                                   linewidths=0.2, edgecolors='grey')
                    cb = fig.colorbar(hb, ax=ax, shrink=0.7, pad=0.02)
                    cb.set_label('Count', fontsize=8)
                    cb.ax.tick_params(labelsize=7)
                else:
                    scatter_color = '#FF8C42' if col_idx == 0 else '#7D7D7D'
                    ax.scatter(x, y, alpha=0.7, s=30, color=scatter_color,
                               edgecolors='black', linewidth=0.4)

                # 1:1 reference line
                min_val = min(x.min(), y.min())
                max_val = max(x.max(), y.max())
                ax.plot([min_val, max_val], [min_val, max_val],
                        color=line_color, linestyle='--', linewidth=2,
                        alpha=0.8, label='1:1 Line')

                # Statistics box
                r = comp['correlation']
                bias = comp['bias']
                rmse = comp['rmse']
                mae = comp['mae']
                n = comp['n_samples']

                stats_text = (f'r = {r:.3f}\n'
                              f'Bias = {bias:+.2f}\u00b0C\n'
                              f'RMSE = {rmse:.2f}\u00b0C\n'
                              f'MAE = {mae:.2f}\u00b0C\n'
                              f'n = {n}')
                ax.text(0.97, 0.03, stats_text, transform=ax.transAxes,
                        verticalalignment='bottom',
                        horizontalalignment='right', fontsize=9,
                        family='monospace',
                        bbox=dict(boxstyle='round,pad=0.5',
                                  facecolor='white', edgecolor='gray',
                                  alpha=0.95, linewidth=1))

                ax.set_xlabel(f'{dataset1_name} LST (\u00b0C)', fontsize=10,
                              fontweight='bold')
                ax.set_ylabel(f'{dataset2_name} LST (\u00b0C)', fontsize=10,
                              fontweight='bold')
                ax.set_title(f'{city} - {period_label}', fontsize=11,
                             fontweight='bold', pad=10)
                ax.grid(True, alpha=0.25, linestyle=':', linewidth=0.5)
                ax.set_aspect('equal', adjustable='box')

        # Page title
        page_label = (f' (Page {page_idx + 1} of {n_pages})'
                      if n_pages > 1 else '')
        fig.suptitle(
            f'Inter-Dataset Validation: {dataset1_name} vs '
            f'{dataset2_name}{page_label}',
            fontsize=14, fontweight='bold', y=0.995)
        plt.tight_layout(rect=[0, 0, 1, 0.99])

        # Save
        if output_dir:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

            suffix = (f'_Page{page_idx + 1}of{n_pages}'
                      if n_pages > 1 else '')
            stem = f'multi_city_comparison_{dataset1_name}_vs_{dataset2_name}'
            png_path = output_dir / f'{stem}{suffix}.png'
            pdf_path = output_dir / f'{stem}{suffix}.pdf'

            fig.savefig(png_path, dpi=dpi, bbox_inches='tight',
                        facecolor='white')
            fig.savefig(pdf_path, format='pdf', bbox_inches='tight',
                        facecolor='white')
            print(f"   \u2713 Saved: {png_path.name}")
            print(f"   \u2713 Saved: {pdf_path.name}")

        figures.append(fig)

    return figures[0] if len(figures) == 1 else figures


def plot_target_diagram(
    comparison_results,
    dataset1_name='MODIS',
    dataset2_name='ERA5-Land',
    output_dir=None,
    figsize=(8.27, 5.85),
    dpi=300,
    show_labels=True,
    cluster_lookup=None,
):
    """
    Create a Target Diagram (Jolliff et al. 2009) combining Day (triangle) and
    Night (circle) on one half-A4 panel, with points coloured by Cluster25 class.

    Background
    ----------
    The **Target Diagram** was introduced by Jolliff et al. (2009) as a compact
    way to display three complementary validation metrics — bias, unbiased RMSE,
    and total RMSE — in a single Cartesian plot.  Taylor (2001) earlier proposed
    a similar diagram in polar coordinates (Taylor Diagram); the Target Diagram
    uses Cartesian coordinates, making the bias sign (ERA5 > MODIS or ERA5 <
    MODIS) immediately visible.

    Mathematical formulation
    ------------------------
    Given N paired observations (x_i = reference, y_i = model):

        Bias  =  mean(y) − mean(x)                    [y-axis; °C]
        RMSE  =  √[ mean( (y_i − x_i)² ) ]            [radius; °C]
        uRMSE =  √( RMSE² − Bias² )                   [x-axis; °C]

    The sign of uRMSE is set to match the sign of the Pearson correlation between
    model and reference anomalies (Jolliff et al. 2009, eq. 3):

        sign(uRMSE) = sign( r )

    Points near the origin perform best (low bias AND low random error).
    Concentric dashed circles are iso-RMSE contours.

    References
    ----------
    Jolliff, J. K., Kindle, J. C., Shulman, I., Penta, B., Friedrichs, M. A. M.,
        Helber, R., & Arnone, R. A. (2009). Summary diagrams for coupled
        hydrodynamic-ecosystem model skill assessment. *Journal of Marine Systems*,
        76(1–2), 64–82. https://doi.org/10.1016/j.jmarsys.2008.05.014

    Taylor, K. E. (2001). Summarizing model performance in a single diagram.
        *Journal of Geophysical Research: Atmospheres*, 106(D7), 7183–7192.
        https://doi.org/10.1029/2000JD900719

    Parameters
    ----------
    comparison_results : list of dict
        One dict per city with keys:
        'city', 'day_bias', 'day_rmse', 'day_correlation',
                'night_bias', 'night_rmse', 'night_correlation'
    dataset1_name : str
        Reference dataset label (default 'MODIS')
    dataset2_name : str
        Comparison dataset label (default 'ERA5-Land')
    output_dir : str or Path, optional
        Directory to save SVG + PDF outputs
    figsize : tuple
        (width, height) in inches — default (8.27, 6.0) = half A4 landscape
    dpi : int
        Figure resolution (default 300)
    show_labels : bool
        Annotate each point with city name using callout arrows (default True)
    cluster_lookup : dict, optional
        city_name -> Cluster25 integer, used to assign point colours

    Returns
    -------
    fig : matplotlib.figure.Figure
    summary : dict
        Day / night best/worst city and mean metrics
    """
    import numpy as np
    from pathlib import Path
    import matplotlib.patches as mpatches
    import matplotlib.lines   as mlines

    try:
        from adjustText import adjust_text as _adjust_text
        _has_adj = True
    except ImportError:
        _has_adj = False
        print("  WARN: adjustText not installed — labels may overlap.")

    try:
        import sys, os
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from config import CLUSTER25_COLORS as _CL_COL
    except Exception:
        _CL_COL = {}

    _FALLBACK_COLOR = '#888888'

    def _city_color(city):
        if cluster_lookup and city in cluster_lookup:
            return _CL_COL.get(int(cluster_lookup[city]), _FALLBACK_COLOR)
        return _FALLBACK_COLOR

    # ── Extract & compute metrics ─────────────────────────────────────────────
    cities = [r['city'] for r in comparison_results]
    b_d  = np.array([r['day_bias']              for r in comparison_results], float)
    R_d  = np.array([r['day_rmse']              for r in comparison_results], float)
    r_d  = np.array([r.get('day_correlation', 0)   for r in comparison_results], float)
    b_n  = np.array([r['night_bias']            for r in comparison_results], float)
    R_n  = np.array([r['night_rmse']            for r in comparison_results], float)
    r_n  = np.array([r.get('night_correlation', 0) for r in comparison_results], float)

    # uRMSE with Jolliff sign convention
    uR_d = np.sign(r_d) * np.sqrt(np.clip(R_d**2 - b_d**2, 0, None))
    uR_n = np.sign(r_n) * np.sqrt(np.clip(R_n**2 - b_n**2, 0, None))

    colors = [_city_color(c) for c in cities]

    # ── Figure ────────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)

    MS = 29  # marker size (fixed; ~43/1.5)

    # Plot Day (triangle) and Night (circle) per city, same cluster colour
    for i, (city, col) in enumerate(zip(cities, colors)):
        ax.scatter(uR_d[i], b_d[i], s=MS, marker='^',
                   color=col, edgecolors='black', linewidth=0.6,
                   alpha=0.88, zorder=3)
        ax.scatter(uR_n[i], b_n[i], s=MS, marker='o',
                   color=col, edgecolors='black', linewidth=0.6,
                   alpha=0.88, zorder=3)

    # ── City labels — isolation-only strategy ────────────────────────────────
    # Build a (2N × 2) coordinate array of every plotted point (day then night).
    # A point is labelled only when its nearest neighbour exceeds the threshold,
    # i.e. the point sits in open space where text cannot overlap other markers.
    texts = []
    if show_labels:
        _n = len(cities)
        _px = np.concatenate([uR_d, uR_n])          # all x-coords
        _py = np.concatenate([b_d,  b_n])            # all y-coords
        _pl = cities + cities                        # city name for each point
        _pp = ['day'] * _n + ['night'] * _n          # period tag

        # Pairwise Euclidean distances (pure numpy, no scipy dependency)
        _diff  = np.stack([_px, _py], axis=1)
        _dmat  = np.sqrt(((_diff[:, None, :] - _diff[None, :, :]) ** 2).sum(axis=2))
        np.fill_diagonal(_dmat, np.inf)
        _nn_dist = _dmat.min(axis=1)                 # nearest-neighbour distance

        # Tune: minimum clear space (°C) before we attempt to label
        _ISO = 0.85

        FS = 6.5
        for idx in range(len(_px)):
            if _nn_dist[idx] < _ISO:
                continue                             # too crowded — skip
            x, y, city = _px[idx], _py[idx], _pl[idx]
            # Only label if the point is actually within the current axis window
            texts.append(
                ax.text(x, y, city, fontsize=FS, color='#111111',
                        alpha=0.92, va='center', ha='left', zorder=5,
                        clip_on=True)
            )

    # ── RMSE iso-circles ─────────────────────────────────────────────────────
    max_R = float(np.nanmax(np.concatenate([R_d, R_n])))
    step  = 2 if max_R <= 12 else 4
    for r_val in np.arange(step, max_R + step * 1.5, step):
        circ = plt.Circle((0, 0), r_val, fill=False,
                           edgecolor='#666666', linestyle='--',
                           linewidth=0.5, alpha=0.45, zorder=1)
        ax.add_patch(circ)
        ax.text(r_val * 0.707, r_val * 0.707, f'{r_val:.0f}\u00b0C',
                fontsize=6.0, color='#444444', alpha=0.75,
                ha='center', va='center',
                bbox=dict(boxstyle='round,pad=0.2', facecolor='white',
                          edgecolor='none', alpha=0.65))

    # ── Crosshairs ───────────────────────────────────────────────────────────
    ax.axhline(0, color='black', linewidth=0.7, linestyle='-', alpha=0.45, zorder=2)
    ax.axvline(0, color='black', linewidth=0.7, linestyle='-', alpha=0.45, zorder=2)

    # ── Bullseye (perfect agreement) ─────────────────────────────────────────
    ax.scatter([0], [0], s=160, color='none', edgecolors='red',
               linewidths=1.6, zorder=4)
    ax.scatter([0], [0], s=45,  color='none', edgecolors='red',
               linewidths=1.1, zorder=4)
    ax.scatter([0], [0], s=12,  color='red',  zorder=4)

    # ── Axis limits — equal x/y range so RMSE circles are round and the figure
    # is always square in data-space regardless of data distribution.
    # Strategy: fit each axis to its data, then expand the narrower one to match.
    all_uR = np.concatenate([uR_d, uR_n])
    all_b  = np.concatenate([b_d,  b_n])
    _pad = 0.12
    _xlo = min(float(np.nanmin(all_uR)) - _pad, -0.4)
    _xhi = max(float(np.nanmax(all_uR)) + _pad,  0.4)
    _ylo = min(float(np.nanmin(all_b))  - _pad, -0.4)
    _yhi = max(float(np.nanmax(all_b))  + _pad,  0.4)
    # Expand the narrower axis to match the wider one so equal-aspect
    # produces a square data-space (not a tall-and-narrow axes box).
    _xrng, _yrng = _xhi - _xlo, _yhi - _ylo
    if _xrng < _yrng:
        _d = (_yrng - _xrng) / 2
        _xlo -= _d;  _xhi += _d
    elif _yrng < _xrng:
        _d = (_xrng - _yrng) / 2
        _ylo -= _d;  _yhi += _d
    ax.set_xlim(_xlo, _xhi)
    ax.set_ylim(_ylo, _yhi)
    ax.set_aspect('equal', adjustable='box')  # keeps RMSE circles round

    # ── Axes decoration ──────────────────────────────────────────────────────
    ax.set_xlabel('Unbiased RMSE (\u00b0C)', fontsize=6, fontweight='bold')
    ax.set_ylabel(
        f'Bias (\u00b0C)\n[{dataset1_name} \u2212 {dataset2_name}]',
        fontsize=6, fontweight='bold',
    )
    ax.set_title(
        f'Target Diagram: {dataset1_name} vs {dataset2_name}\n'
        f'Day (\u25b2) and Night (\u25cf), coloured by Cluster25 class',
        fontsize=6.5, fontweight='bold', pad=6,
    )
    ax.tick_params(axis='both', labelsize=5.5)
    ax.grid(True, alpha=0.18, linestyle=':', linewidth=0.5, zorder=0)

    # ── Legend ────────────────────────────────────────────────────────────────
    # Section 1: marker style
    h_day   = mlines.Line2D([], [], marker='^', linestyle='none',
                             color='dimgrey', markeredgecolor='black',
                             markersize=5, label='Day (\u25b2)')
    h_night = mlines.Line2D([], [], marker='o', linestyle='none',
                             color='dimgrey', markeredgecolor='black',
                             markersize=5, label='Night (\u25cf)')
    h_perf  = mlines.Line2D([], [], marker='o', linestyle='none',
                             color='red', markeredgecolor='red',
                             markersize=5, label='Perfect agreement')
    handles = [h_day, h_night, h_perf]
    labels  = ['Day (\u25b2)', 'Night (\u25cf)', 'Perfect agreement']

    ax.legend(handles=handles, labels=labels,
              loc='lower right', fontsize=6.5,
              framealpha=0.93, edgecolor='#aaaaaa',
              fancybox=False, frameon=True,
              handlelength=1.4, handleheight=1.2,
              borderpad=0.6)

    # ── adjustText callouts ───────────────────────────────────────────────────
    if texts and _has_adj:
        _adjust_text(
            texts, ax=ax,
            expand_points=(1.4, 1.4),
            expand_text=(1.1, 1.1),
            force_points=(0.35, 0.35),
            force_text=(0.35, 0.35),
            arrowprops=dict(arrowstyle='->', color='grey', lw=0.55),
        )

    plt.tight_layout()

    # ── Save ─────────────────────────────────────────────────────────────────
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        stem = f'target_diagram_{dataset1_name}_vs_{dataset2_name}'
        for ext in ('svg', 'pdf'):
            p = output_dir / f'{stem}.{ext}'
            fig.savefig(str(p), format=ext, bbox_inches='tight', facecolor='white')
            print(f'    Saved: {p.name}')

    # ── Summary dict ─────────────────────────────────────────────────────────
    summary = {
        'n_cities': len(cities),
        'day': {
            'best_city':        cities[int(np.nanargmin(R_d))],
            'best_rmse':        float(np.nanmin(R_d)),
            'worst_city':       cities[int(np.nanargmax(R_d))],
            'worst_rmse':       float(np.nanmax(R_d)),
            'mean_bias':        float(np.nanmean(b_d)),
            'mean_rmse':        float(np.nanmean(R_d)),
            'mean_correlation': float(np.nanmean(r_d)),
        },
        'night': {
            'best_city':        cities[int(np.nanargmin(R_n))],
            'best_rmse':        float(np.nanmin(R_n)),
            'worst_city':       cities[int(np.nanargmax(R_n))],
            'worst_rmse':       float(np.nanmax(R_n)),
            'mean_bias':        float(np.nanmean(b_n)),
            'mean_rmse':        float(np.nanmean(R_n)),
            'mean_correlation': float(np.nanmean(r_n)),
        },
    }

    return fig, summary


def plot_dataset_comparison(
    comparison_results,
    city_name,
    comparison_name,
    output_dir=None,
    figsize=(12, 5),
    dpi=300
):
    """
    Plot scatter comparison between two LST datasets.
    
    Parameters
    ----------
    comparison_results : dict
        Results from compare_datasets()
    city_name : str
        Name of city
    comparison_name : str
        Comparison identifier (e.g., 'MODIS vs ERA5')
    output_dir : str or Path, optional
        Directory to save figure
    figsize : tuple
        Figure size
    dpi : int
        Figure DPI
        
    Returns
    -------
    fig : matplotlib.figure.Figure or None
    """
    merged = comparison_results['merged_data']
    
    if merged.empty:
        print(f"No overlapping data for {comparison_name}")
        return None
    
    # Extract dataset names
    dataset1 = comparison_results['dataset1_name']
    dataset2 = comparison_results['dataset2_name']
    
    col1 = [c for c in merged.columns if dataset1 in c and 'lst' in c.lower()][0]
    col2 = [c for c in merged.columns if dataset2 in c and 'lst' in c.lower()][0]
    
    # Create figure with two subplots
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=figsize, dpi=dpi)
    
    # Scatter plot
    ax1.scatter(merged[col1], merged[col2], alpha=0.5, s=30, color='#457B9D')
    
    # 1:1 line
    min_val = min(merged[col1].min(), merged[col2].min())
    max_val = max(merged[col1].max(), merged[col2].max())
    ax1.plot([min_val, max_val], [min_val, max_val], 'r--', linewidth=2, label='1:1 Line')
    
    # Add statistics text
    r = comparison_results['correlation']
    bias = comparison_results['bias']
    rmse = comparison_results['rmse']
    mae = comparison_results['mae']
    n = comparison_results['n_samples']
    
    stats_text = f'r = {r:.3f}\nBias = {bias:.2f}°C\nRMSE = {rmse:.2f}°C\nMAE = {mae:.2f}°C\nn = {n}'
    ax1.text(0.05, 0.95, stats_text, transform=ax1.transAxes, 
             verticalalignment='top', fontsize=10, 
             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
    
    ax1.set_xlabel(f'{dataset1} LST (°C)', fontsize=11, fontweight='bold')
    ax1.set_ylabel(f'{dataset2} LST (°C)', fontsize=11, fontweight='bold')
    ax1.set_title(f'{city_name} - {comparison_name}', fontsize=12, fontweight='bold')
    ax1.legend(loc='lower right')
    ax1.grid(True, alpha=0.3, linestyle=':', linewidth=0.5)
    
    # Time series comparison
    ax2.plot(merged['date'], merged[col1], label=dataset1, color='#E63946', linewidth=1.5, alpha=0.8)
    ax2.plot(merged['date'], merged[col2], label=dataset2, color='#2A9D8F', linewidth=1.5, alpha=0.8)
    
    ax2.set_xlabel('Date', fontsize=11, fontweight='bold')
    ax2.set_ylabel('LST (°C)', fontsize=11, fontweight='bold')
    ax2.set_title('Time Series Comparison', fontsize=12, fontweight='bold')
    ax2.legend(loc='best')
    ax2.grid(True, alpha=0.3, linestyle=':', linewidth=0.5)
    
    plt.tight_layout()
    
    # Save
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        png_path = output_dir / f'comparison_{comparison_name.lower().replace(" ", "_")}.png'
        pdf_path = output_dir / f'comparison_{comparison_name.lower().replace(" ", "_")}.pdf'
        
        fig.savefig(png_path, dpi=dpi, bbox_inches='tight')
        fig.savefig(pdf_path, format='pdf', bbox_inches='tight')
        
        plt.close(fig)
        return None
    
    return fig


def plot_diurnal_range(
    df_day,
    df_night,
    city_name,
    dataset_name,
    output_dir=None,
    figsize=(14, 6),
    dpi=300
):
    """
    Plot diurnal temperature range (day - night).
    
    Parameters
    ----------
    df_day : pd.DataFrame
        Daytime LST data
    df_night : pd.DataFrame
        Nighttime LST data
    city_name : str
        Name of city
    dataset_name : str
        Dataset name
    output_dir : str or Path, optional
        Directory to save figure
    figsize : tuple
        Figure size
    dpi : int
        Figure DPI
        
    Returns
    -------
    fig : matplotlib.figure.Figure or None
    """
    # Merge day and night data
    merged = pd.merge(
        df_day[['date', 'lst_mean']],
        df_night[['date', 'lst_mean']],
        on='date',
        suffixes=('_day', '_night')
    ).dropna()
    
    if merged.empty:
        print(f"No overlapping day/night data for {dataset_name}")
        return None
    
    # Calculate diurnal range
    merged['diurnal_range'] = merged['lst_mean_day'] - merged['lst_mean_night']
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=figsize, dpi=dpi, sharex=True)
    
    # Day and night time series
    ax1.plot(merged['date'], merged['lst_mean_day'], label='Day', color='#E63946', linewidth=1.5)
    ax1.plot(merged['date'], merged['lst_mean_night'], label='Night', color='#1D3557', linewidth=1.5)
    ax1.fill_between(merged['date'], merged['lst_mean_night'], merged['lst_mean_day'], 
                      alpha=0.2, color='#F4A261')
    
    ax1.set_ylabel('LST (°C)', fontsize=11, fontweight='bold')
    ax1.set_title(f'{city_name} - {dataset_name} Day/Night LST', fontsize=12, fontweight='bold')
    ax1.legend(loc='best')
    ax1.grid(True, alpha=0.3, linestyle=':', linewidth=0.5)
    
    # Diurnal range
    mean_range = merged['diurnal_range'].mean()
    ax2.plot(merged['date'], merged['diurnal_range'], color='#F4A261', linewidth=1.5)
    ax2.axhline(mean_range, color='#666', linestyle='--', linewidth=1, alpha=0.5,
                label=f'Mean: {mean_range:.1f}°C')
    ax2.fill_between(merged['date'], 0, merged['diurnal_range'], alpha=0.3, color='#F4A261')
    
    ax2.set_xlabel('Date', fontsize=11, fontweight='bold')
    ax2.set_ylabel('Diurnal Range (°C)', fontsize=11, fontweight='bold')
    ax2.set_title('Day-Night Temperature Difference', fontsize=12, fontweight='bold')
    ax2.legend(loc='best')
    ax2.grid(True, alpha=0.3, linestyle=':', linewidth=0.5)
    
    plt.tight_layout()
    
    # Save
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        png_path = output_dir / f'{dataset_name.lower()}_diurnal_range.png'
        pdf_path = output_dir / f'{dataset_name.lower()}_diurnal_range.pdf'
        
        fig.savefig(png_path, dpi=dpi, bbox_inches='tight')
        fig.savefig(pdf_path, format='pdf', bbox_inches='tight')
        
        plt.close(fig)
        return None
    
    return fig


def create_comprehensive_daily_dashboard(
    city_name,
    df_modis_day,
    df_modis_night,
    df_era5_day,
    df_era5_night,
    df_seviri_day=None,
    df_seviri_night=None,
    output_dir=None,
    dpi=300
):
    """
    Create comprehensive multi-panel dashboard for daily LST analysis.
    
    Parameters
    ----------
    city_name : str
        Name of city
    df_modis_day, df_modis_night : pd.DataFrame
        MODIS day/night data
    df_era5_day, df_era5_night : pd.DataFrame
        ERA5 day/night data
    df_seviri_day, df_seviri_night : pd.DataFrame, optional
        SEVIRI day/night data
    output_dir : str or Path, optional
        Directory to save figure
    dpi : int
        Figure DPI
        
    Returns
    -------
    fig : matplotlib.figure.Figure or None
    """
    fig = plt.figure(figsize=(18, 12), dpi=dpi)
    gs = GridSpec(3, 2, figure=fig, hspace=0.3, wspace=0.25)
    
    # Panel 1: MODIS Day Time Series
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.plot(df_modis_day['date'], df_modis_day['lst_mean'], color='#E63946', linewidth=1.5)
    if 'is_hot' in df_modis_day.columns:
        hot_days = df_modis_day[df_modis_day['is_hot']]
        ax1.scatter(hot_days['date'], hot_days['lst_mean'], color='#A4133C', s=40, alpha=0.7, zorder=5)
    ax1.set_title('MODIS Day LST', fontsize=11, fontweight='bold')
    ax1.set_ylabel('LST (°C)', fontsize=10)
    ax1.grid(True, alpha=0.3, linestyle=':', linewidth=0.5)
    
    # Panel 2: MODIS Night Time Series
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.plot(df_modis_night['date'], df_modis_night['lst_mean'], color='#1D3557', linewidth=1.5)
    if 'is_hot' in df_modis_night.columns:
        hot_nights = df_modis_night[df_modis_night['is_hot']]
        ax2.scatter(hot_nights['date'], hot_nights['lst_mean'], color='#0B1F3F', s=40, alpha=0.7, zorder=5)
    ax2.set_title('MODIS Night LST', fontsize=11, fontweight='bold')
    ax2.set_ylabel('LST (°C)', fontsize=10)
    ax2.grid(True, alpha=0.3, linestyle=':', linewidth=0.5)
    
    # Panel 3: ERA5 Day Time Series
    ax3 = fig.add_subplot(gs[1, 0])
    ax3.plot(df_era5_day['date'], df_era5_day['lst_mean'], color='#2A9D8F', linewidth=1.5)
    ax3.set_title('ERA5-Land Day LST', fontsize=11, fontweight='bold')
    ax3.set_ylabel('LST (°C)', fontsize=10)
    ax3.grid(True, alpha=0.3, linestyle=':', linewidth=0.5)
    
    # Panel 4: ERA5 Night Time Series
    ax4 = fig.add_subplot(gs[1, 1])
    ax4.plot(df_era5_night['date'], df_era5_night['lst_mean'], color='#1B6B5F', linewidth=1.5)
    ax4.set_title('ERA5-Land Night LST', fontsize=11, fontweight='bold')
    ax4.set_ylabel('LST (°C)', fontsize=10)
    ax4.grid(True, alpha=0.3, linestyle=':', linewidth=0.5)
    
    # Panel 5: Dataset Comparison (Day)
    ax5 = fig.add_subplot(gs[2, 0])
    merged_day = pd.merge(
        df_modis_day[['date', 'lst_mean']],
        df_era5_day[['date', 'lst_mean']],
        on='date',
        suffixes=('_modis', '_era5')
    ).dropna()
    
    if not merged_day.empty:
        ax5.scatter(merged_day['lst_mean_modis'], merged_day['lst_mean_era5'], 
                   alpha=0.5, s=30, color='#E76F51')
        min_val = min(merged_day['lst_mean_modis'].min(), merged_day['lst_mean_era5'].min())
        max_val = max(merged_day['lst_mean_modis'].max(), merged_day['lst_mean_era5'].max())
        ax5.plot([min_val, max_val], [min_val, max_val], 'r--', linewidth=2)
        
        r = merged_day['lst_mean_modis'].corr(merged_day['lst_mean_era5'])
        ax5.text(0.05, 0.95, f'r = {r:.3f}', transform=ax5.transAxes,
                verticalalignment='top', fontsize=9,
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
    
    ax5.set_xlabel('MODIS LST (°C)', fontsize=10)
    ax5.set_ylabel('ERA5 LST (°C)', fontsize=10)
    ax5.set_title('Day: MODIS vs ERA5', fontsize=11, fontweight='bold')
    ax5.grid(True, alpha=0.3, linestyle=':', linewidth=0.5)
    
    # Panel 6: Dataset Comparison (Night)
    ax6 = fig.add_subplot(gs[2, 1])
    merged_night = pd.merge(
        df_modis_night[['date', 'lst_mean']],
        df_era5_night[['date', 'lst_mean']],
        on='date',
        suffixes=('_modis', '_era5')
    ).dropna()
    
    if not merged_night.empty:
        ax6.scatter(merged_night['lst_mean_modis'], merged_night['lst_mean_era5'], 
                   alpha=0.5, s=30, color='#264653')
        min_val = min(merged_night['lst_mean_modis'].min(), merged_night['lst_mean_era5'].min())
        max_val = max(merged_night['lst_mean_modis'].max(), merged_night['lst_mean_era5'].max())
        ax6.plot([min_val, max_val], [min_val, max_val], 'r--', linewidth=2)
        
        r = merged_night['lst_mean_modis'].corr(merged_night['lst_mean_era5'])
        ax6.text(0.05, 0.95, f'r = {r:.3f}', transform=ax6.transAxes,
                verticalalignment='top', fontsize=9,
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
    
    ax6.set_xlabel('MODIS LST (°C)', fontsize=10)
    ax6.set_ylabel('ERA5 LST (°C)', fontsize=10)
    ax6.set_title('Night: MODIS vs ERA5', fontsize=11, fontweight='bold')
    ax6.grid(True, alpha=0.3, linestyle=':', linewidth=0.5)
    
    # Overall title
    fig.suptitle(f'{city_name} - Daily LST Analysis Dashboard (2024)', 
                 fontsize=16, fontweight='bold', y=0.995)
    
    # Save
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        png_path = output_dir / 'comprehensive_daily_dashboard.png'
        pdf_path = output_dir / 'comprehensive_daily_dashboard.pdf'
        
        fig.savefig(png_path, dpi=dpi, bbox_inches='tight')
        fig.savefig(pdf_path, format='pdf', bbox_inches='tight')
        
        plt.close(fig)
        return None
    
    return fig


def create_dual_dataset_comparison_plot(modis_df, era5_df, city_name, study_year, output_dir, hot_percentile=90, stats=None):
    """
    Create comparative visualization showing both MODIS and ERA5-Land data with hot event annotations.
    Follows EXACT format from original notebook 04_temporal_analysis_daily.ipynb
    
    Parameters:
    -----------
    modis_df : pandas.DataFrame or None
        MODIS daily LST data with columns: date, day_lst_*, night_lst_*
    era5_df : pandas.DataFrame or None
        ERA5-Land daily LST data with same column structure
    city_name : str
        Name of the city
    study_year : int
        Study year
    output_dir : Path or str
        Directory to save the plot
    hot_percentile : int
        Hot event threshold percentile (default: 90)
    stats : dict or None
        Statistics dictionary containing hot event and persistent event information
    
    Returns:
    --------
    Path or None
        Path to saved comparison plot, or None if no data available
    """
    import matplotlib.dates as mdates
    
    if modis_df is None and era5_df is None:
        return None
    
    # Create figure with standard format (18x12 inches)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(18, 12), sharex=True)
    
    # Plot MODIS data (if available)
    if modis_df is not None:
        # Calculate MODIS thresholds
        modis_day_threshold = modis_df['day_lst_median'].quantile(hot_percentile / 100)
        modis_night_threshold = modis_df['night_lst_median'].quantile(hot_percentile / 100)
        
        # Identify hot days and nights
        modis_hot_days = modis_df['day_lst_median'] >= modis_day_threshold
        modis_hot_nights = modis_df['night_lst_median'] >= modis_night_threshold
        
        # Plot MODIS ranges
        ax1.fill_between(modis_df['date'], modis_df['day_lst_min'], modis_df['day_lst_max'],
                        alpha=0.3, color='red', label='MODIS Day Range')
        ax1.fill_between(modis_df['date'], modis_df['night_lst_min'], modis_df['night_lst_max'],
                        alpha=0.3, color='blue', label='MODIS Night Range')
        
        # Plot MODIS medians
        ax1.plot(modis_df['date'], modis_df['day_lst_median'], 
                color='red', linewidth=1.5, label='MODIS Day LST', alpha=0.9)
        ax1.plot(modis_df['date'], modis_df['night_lst_median'], 
                color='blue', linewidth=1.5, label='MODIS Night LST', alpha=0.9)
        
        # Mark hot days/nights (filled black dots)
        hot_day_dates = modis_df.loc[modis_hot_days, 'date']
        hot_day_temps = modis_df.loc[modis_hot_days, 'day_lst_median']
        ax1.scatter(hot_day_dates, hot_day_temps, color='black', s=30, zorder=5, 
                   label='Hot Days/Nights', alpha=0.6)
        
        hot_night_dates = modis_df.loc[modis_hot_nights, 'date']
        hot_night_temps = modis_df.loc[modis_hot_nights, 'night_lst_median']
        ax1.scatter(hot_night_dates, hot_night_temps, color='black', s=30, zorder=5, alpha=0.6)
        
        # Add persistent event counts as text annotation (bottom-left)
        if stats and 'modis' in stats:
            persistent_events = stats['modis'].get('heat_events', {}).get('persistent_events', {})
            persist_days_list = persistent_events.get('persistent_hot_days', [])
            persist_nights_list = persistent_events.get('persistent_hot_nights', [])
            
            n_persist_days = len(persist_days_list)
            n_persist_nights = len(persist_nights_list)
            
            # Get maximum duration for days and nights
            max_duration_days = max([event['duration'] for event in persist_days_list], default=0)
            max_duration_nights = max([event['duration'] for event in persist_nights_list], default=0)
            
            persist_text = f"Persistent Events:\nDays: {n_persist_days} events (max {max_duration_days} days)\nNights: {n_persist_nights} events (max {max_duration_nights} days)"
            ax1.text(0.02, 0.02, persist_text, transform=ax1.transAxes, 
                    fontsize=10, verticalalignment='bottom', horizontalalignment='left',
                    bbox=dict(boxstyle='round', facecolor='white', alpha=0.85, edgecolor='gray'))
        
        # Plot MODIS thresholds
        ax1.axhline(y=modis_day_threshold, color='red', linestyle='--', alpha=0.7,
                   label=f'Day Threshold ({modis_day_threshold:.1f}°C)')
        ax1.axhline(y=modis_night_threshold, color='blue', linestyle='--', alpha=0.7,
                   label=f'Night Threshold ({modis_night_threshold:.1f}°C)')
        
        ax1.set_title(f'MODIS LST Analysis - {city_name} ({study_year})', fontsize=14, fontweight='bold')
        ax1.set_ylabel('Temperature (°C)', fontsize=12, fontweight='bold')
        ax1.grid(True, alpha=0.3)
        ax1.legend(loc='upper right', fontsize=9, ncol=2)
    
    # Plot ERA5-Land data (if available)
    if era5_df is not None:
        # Calculate ERA5-Land thresholds
        era5_day_threshold = era5_df['day_lst_median'].quantile(hot_percentile / 100)
        era5_night_threshold = era5_df['night_lst_median'].quantile(hot_percentile / 100)
        
        # Identify hot days and nights
        era5_hot_days = era5_df['day_lst_median'] >= era5_day_threshold
        era5_hot_nights = era5_df['night_lst_median'] >= era5_night_threshold
        
        # Plot ERA5-Land ranges
        ax2.fill_between(era5_df['date'], era5_df['day_lst_min'], era5_df['day_lst_max'],
                        alpha=0.3, color='orange', label='ERA5-Land Day Range')
        ax2.fill_between(era5_df['date'], era5_df['night_lst_min'], era5_df['night_lst_max'],
                        alpha=0.3, color='purple', label='ERA5-Land Night Range')
        
        # Plot ERA5-Land medians
        ax2.plot(era5_df['date'], era5_df['day_lst_median'], 
                color='orange', linewidth=1.5, label='ERA5-Land Day LST', alpha=0.9)
        ax2.plot(era5_df['date'], era5_df['night_lst_median'], 
                color='purple', linewidth=1.5, label='ERA5-Land Night LST', alpha=0.9)
        
        # Mark hot days/nights (filled black dots)
        hot_day_dates = era5_df.loc[era5_hot_days, 'date']
        hot_day_temps = era5_df.loc[era5_hot_days, 'day_lst_median']
        ax2.scatter(hot_day_dates, hot_day_temps, color='black', s=30, zorder=5, 
                   label='Hot Days/Nights', alpha=0.6)
        
        hot_night_dates = era5_df.loc[era5_hot_nights, 'date']
        hot_night_temps = era5_df.loc[era5_hot_nights, 'night_lst_median']
        ax2.scatter(hot_night_dates, hot_night_temps, color='black', s=30, zorder=5, alpha=0.6)
        
        # Add persistent event counts as text annotation (bottom-left)
        if stats and 'era5_land' in stats:
            persistent_events = stats['era5_land'].get('heat_events', {}).get('persistent_events', {})
            persist_days_list = persistent_events.get('persistent_hot_days', [])
            persist_nights_list = persistent_events.get('persistent_hot_nights', [])
            
            n_persist_days = len(persist_days_list)
            n_persist_nights = len(persist_nights_list)
            
            # Get maximum duration for days and nights
            max_duration_days = max([event['duration'] for event in persist_days_list], default=0)
            max_duration_nights = max([event['duration'] for event in persist_nights_list], default=0)
            
            persist_text = f"Persistent Events:\nDays: {n_persist_days} events (max {max_duration_days} days)\nNights: {n_persist_nights} events (max {max_duration_nights} nights)"
            ax2.text(0.02, 0.02, persist_text, transform=ax2.transAxes, 
                    fontsize=10, verticalalignment='bottom', horizontalalignment='left',
                    bbox=dict(boxstyle='round', facecolor='white', alpha=0.85, edgecolor='gray'))
        
        # Plot ERA5-Land thresholds
        ax2.axhline(y=era5_day_threshold, color='orange', linestyle='--', alpha=0.7,
                   label=f'Day Threshold ({era5_day_threshold:.1f}°C)')
        ax2.axhline(y=era5_night_threshold, color='purple', linestyle='--', alpha=0.7,
                   label=f'Night Threshold ({era5_night_threshold:.1f}°C)')
        
        ax2.set_title(f'ERA5-Land LST Analysis - {city_name} ({study_year})', fontsize=14, fontweight='bold')
        ax2.set_ylabel('Temperature (°C)', fontsize=12, fontweight='bold')
        ax2.grid(True, alpha=0.3)
        ax2.legend(loc='upper right', fontsize=9, ncol=2)
    
    # Format x-axis (bottom plot only)
    ax2.set_xlabel('Date', fontsize=12, fontweight='bold')
    ax2.xaxis.set_major_locator(mdates.MonthLocator())
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%b'))
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45)
    
    # Adjust layout
    plt.tight_layout()
    
    # Save comparison plot
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    png_path = output_dir / f'{city_name}_MODIS_vs_ERA5Land_comparison_{study_year}.png'
    pdf_path = output_dir / f'{city_name}_MODIS_vs_ERA5Land_comparison_{study_year}.pdf'
    
    # Save both PNG and PDF
    plt.savefig(png_path, dpi=300, bbox_inches='tight')
    plt.savefig(pdf_path, format='pdf', bbox_inches='tight')
    plt.close()
    
    print(f"        📊 Saved comparison plot: {png_path.name} + {pdf_path.name}")
    return png_path


def create_enhanced_persistent_event_plot(modis_df, era5_df, city_name, study_year, output_dir, hot_percentile=90, stats=None):
    """
    Create enhanced visualization highlighting persistent heat events with connecting line markers.
    Similar to create_dual_dataset_comparison_plot but adds horizontal lines with 'o' markers
    to show persistent heat events positioned above threshold lines.
    
    Parameters:
    -----------
    modis_df : pandas.DataFrame or None
        MODIS daily LST data with columns: date, day_lst_*, night_lst_*
    era5_df : pandas.DataFrame or None
        ERA5-Land daily LST data with same column structure
    city_name : str
        Name of the city
    study_year : int
        Study year
    output_dir : Path or str
        Directory to save the plot
    hot_percentile : int
        Hot event threshold percentile (default: 90)
    stats : dict or None
        Statistics dictionary containing persistent event information
    
    Returns:
    --------
    Path or None
        Path to saved enhanced plot, or None if no data available
    """
    import matplotlib.dates as mdates
    from matplotlib.lines import Line2D
    
    if modis_df is None and era5_df is None:
        return None
    
    # Create figure
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(18, 12), sharex=True)
    
    # ====================================================================
    # MODIS PANEL
    # ====================================================================
    if modis_df is not None:
        modis_day_threshold = modis_df['day_lst_median'].quantile(hot_percentile / 100)
        modis_night_threshold = modis_df['night_lst_median'].quantile(hot_percentile / 100)
        
        modis_hot_days = modis_df['day_lst_median'] >= modis_day_threshold
        modis_hot_nights = modis_df['night_lst_median'] >= modis_night_threshold
        
        # Plot ranges
        ax1.fill_between(modis_df['date'], modis_df['day_lst_min'], modis_df['day_lst_max'],
                        alpha=0.3, color='red', label='MODIS Day Range')
        ax1.fill_between(modis_df['date'], modis_df['night_lst_min'], modis_df['night_lst_max'],
                        alpha=0.3, color='blue', label='MODIS Night Range')
        
        # Plot medians
        ax1.plot(modis_df['date'], modis_df['day_lst_median'], 
                color='red', linewidth=1.5, label='MODIS Day LST', alpha=0.9)
        ax1.plot(modis_df['date'], modis_df['night_lst_median'], 
                color='blue', linewidth=1.5, label='MODIS Night LST', alpha=0.9)
        
        # Mark all hot days/nights (black dots)
        hot_day_dates = modis_df.loc[modis_hot_days, 'date']
        hot_day_temps = modis_df.loc[modis_hot_days, 'day_lst_median']
        ax1.scatter(hot_day_dates, hot_day_temps, color='black', s=30, zorder=5, 
                   label='Hot Days/Nights', alpha=0.6)
        
        hot_night_dates = modis_df.loc[modis_hot_nights, 'date']
        hot_night_temps = modis_df.loc[modis_hot_nights, 'night_lst_median']
        ax1.scatter(hot_night_dates, hot_night_temps, color='black', s=30, zorder=5, alpha=0.6)
        
        # Plot threshold lines
        ax1.axhline(y=modis_day_threshold, color='red', linestyle='--', alpha=0.7,
                   label=f'Day Threshold ({modis_day_threshold:.1f}°C)')
        ax1.axhline(y=modis_night_threshold, color='blue', linestyle='--', alpha=0.7,
                   label=f'Night Threshold ({modis_night_threshold:.1f}°C)')
        
        # ====================================================================
        # ADD LONGEST PERSISTENT EVENT MARKERS FOR MODIS (Pi/Pii)
        # ====================================================================
        if stats and 'modis' in stats:
            persistent_events = stats['modis'].get('heat_events', {}).get('persistent_events', {})
            persist_days_list = persistent_events.get('persistent_hot_days', [])
            persist_nights_list = persistent_events.get('persistent_hot_nights', [])
            
            # Get y-limits for positioning markers BELOW thresholds
            y_min, y_max = ax1.get_ylim()
            marker_offset = (y_max - y_min) * 0.12  # ~5cm below threshold
            
            custom_lines = []
            
            # Find and draw LONGEST persistent DAY event (Pi)
            if persist_days_list:
                longest_day_event = max(persist_days_list, key=lambda x: x['duration'])
                start_date = longest_day_event['start_date']
                end_date = longest_day_event['end_date']
                duration = longest_day_event['duration']
                
                event_mask = (modis_df['date'] >= start_date) & (modis_df['date'] <= end_date)
                event_dates = modis_df.loc[event_mask, 'date']
                
                if len(event_dates) > 0:
                    marker_y = modis_day_threshold - marker_offset
                    
                    # Draw straight horizontal black line
                    ax1.plot(event_dates, [marker_y] * len(event_dates), 
                            color='black', linewidth=3, solid_capstyle='butt',
                            alpha=0.9, zorder=10)
                    
                    # Add vertical bar '|' at start and end
                    bar_height = (y_max - y_min) * 0.015
                    ax1.plot([event_dates.iloc[0], event_dates.iloc[0]], 
                            [marker_y - bar_height, marker_y + bar_height], 
                            color='black', linewidth=3, solid_capstyle='butt', zorder=11)
                    ax1.plot([event_dates.iloc[-1], event_dates.iloc[-1]], 
                            [marker_y - bar_height, marker_y + bar_height], 
                            color='black', linewidth=3, solid_capstyle='butt', zorder=11)
                    
                    # Add label "P_i" with RED background (matching day range)
                    mid_date = event_dates.iloc[len(event_dates)//2]
                    ax1.text(mid_date, marker_y + bar_height*2, 'P$_i$', 
                            fontsize=11, fontweight='bold', ha='center', va='bottom',
                            bbox=dict(boxstyle='round,pad=0.3', facecolor='red', alpha=0.6, edgecolor='black'))
                    
                    custom_lines.append(
                        Line2D([0], [0], color='black', linewidth=3, marker='|', markersize=10,
                               label=f'Pi: Longest Day Event ({duration} days)')
                    )
            
            # Find and draw LONGEST persistent NIGHT event (Pii)
            if persist_nights_list:
                longest_night_event = max(persist_nights_list, key=lambda x: x['duration'])
                start_date = longest_night_event['start_date']
                end_date = longest_night_event['end_date']
                duration = longest_night_event['duration']
                
                event_mask = (modis_df['date'] >= start_date) & (modis_df['date'] <= end_date)
                event_dates = modis_df.loc[event_mask, 'date']
                
                if len(event_dates) > 0:
                    marker_y = modis_night_threshold - marker_offset
                    
                    # Draw straight horizontal black line
                    ax1.plot(event_dates, [marker_y] * len(event_dates), 
                            color='black', linewidth=3, solid_capstyle='butt',
                            alpha=0.9, zorder=10)
                    
                    # Add vertical bar '|' at start and end
                    bar_height = (y_max - y_min) * 0.015
                    ax1.plot([event_dates.iloc[0], event_dates.iloc[0]], 
                            [marker_y - bar_height, marker_y + bar_height], 
                            color='black', linewidth=3, solid_capstyle='butt', zorder=11)
                    ax1.plot([event_dates.iloc[-1], event_dates.iloc[-1]], 
                            [marker_y - bar_height, marker_y + bar_height], 
                            color='black', linewidth=3, solid_capstyle='butt', zorder=11)
                    
                    # Add label "P_ii" with BLUE background (matching night range)
                    mid_date = event_dates.iloc[len(event_dates)//2]
                    ax1.text(mid_date, marker_y + bar_height*2, 'P$_{ii}$', 
                            fontsize=11, fontweight='bold', ha='center', va='bottom',
                            bbox=dict(boxstyle='round,pad=0.3', facecolor='blue', alpha=0.6, edgecolor='black'))
                    
                    custom_lines.append(
                        Line2D([0], [0], color='black', linewidth=3, marker='|', markersize=10,
                               label=f'P$_{{ii}}$: Longest Night Event ({duration} nights)')
                    )
            
            # Combine Pi and Pii into single legend entry if both exist
            if len(custom_lines) == 2:
                # Replace with single combined entry
                day_duration = persist_days_list[0]['duration'] if persist_days_list else 0
                night_duration = persist_nights_list[0]['duration'] if persist_nights_list else 0
                custom_lines = [
                    Line2D([0], [0], color='black', linewidth=3, marker='|', markersize=10,
                           label=f'Longest Events: P$_i$ ({day_duration}d), P$_{{ii}}$ ({night_duration}n)')
                ]
            
            # Add persistent event stats text with lighter background
            n_persist_days = len(persist_days_list)
            n_persist_nights = len(persist_nights_list)
            longest_duration_days = max([event['duration'] for event in persist_days_list], default=0)
            longest_duration_nights = max([event['duration'] for event in persist_nights_list], default=0)
            
            persist_text = f"Persistent Events (MODIS):\nDays: {n_persist_days} total (longest: {longest_duration_days} days)\nNights: {n_persist_nights} total (longest: {longest_duration_nights} nights)"
            ax1.text(0.02, 0.02, persist_text, transform=ax1.transAxes, 
                    fontsize=10, verticalalignment='bottom', horizontalalignment='left',
                    bbox=dict(boxstyle='round', facecolor='white', alpha=0.9, edgecolor='gray', linewidth=1))
        
        ax1.set_title(f'MODIS LST Analysis - {city_name} ({study_year})', 
                     fontsize=14, fontweight='bold')
        ax1.set_ylabel('Temperature (°C)', fontsize=12, fontweight='bold')
        ax1.grid(True, alpha=0.3)
        
        # Combine legends
        handles1, labels1 = ax1.get_legend_handles_labels()
        if custom_lines:
            handles1.extend(custom_lines)
        ax1.legend(handles=handles1, loc='upper right', fontsize=9, ncol=2)
    
    # ====================================================================
    # ERA5-LAND PANEL
    # ====================================================================
    if era5_df is not None:
        era5_day_threshold = era5_df['day_lst_median'].quantile(hot_percentile / 100)
        era5_night_threshold = era5_df['night_lst_median'].quantile(hot_percentile / 100)
        
        era5_hot_days = era5_df['day_lst_median'] >= era5_day_threshold
        era5_hot_nights = era5_df['night_lst_median'] >= era5_night_threshold
        
        # Plot ranges
        ax2.fill_between(era5_df['date'], era5_df['day_lst_min'], era5_df['day_lst_max'],
                        alpha=0.3, color='orange', label='ERA5-Land Day Range')
        ax2.fill_between(era5_df['date'], era5_df['night_lst_min'], era5_df['night_lst_max'],
                        alpha=0.3, color='purple', label='ERA5-Land Night Range')
        
        # Plot medians
        ax2.plot(era5_df['date'], era5_df['day_lst_median'], 
                color='orange', linewidth=1.5, label='ERA5-Land Day LST', alpha=0.9)
        ax2.plot(era5_df['date'], era5_df['night_lst_median'], 
                color='purple', linewidth=1.5, label='ERA5-Land Night LST', alpha=0.9)
        
        # Mark all hot days/nights (black dots)
        hot_day_dates = era5_df.loc[era5_hot_days, 'date']
        hot_day_temps = era5_df.loc[era5_hot_days, 'day_lst_median']
        ax2.scatter(hot_day_dates, hot_day_temps, color='black', s=30, zorder=5, 
                   label='Hot Days/Nights', alpha=0.6)
        
        hot_night_dates = era5_df.loc[era5_hot_nights, 'date']
        hot_night_temps = era5_df.loc[era5_hot_nights, 'night_lst_median']
        ax2.scatter(hot_night_dates, hot_night_temps, color='black', s=30, zorder=5, alpha=0.6)
        
        # Plot threshold lines
        ax2.axhline(y=era5_day_threshold, color='orange', linestyle='--', alpha=0.7,
                   label=f'Day Threshold ({era5_day_threshold:.1f}°C)')
        ax2.axhline(y=era5_night_threshold, color='purple', linestyle='--', alpha=0.7,
                   label=f'Night Threshold ({era5_night_threshold:.1f}°C)')
        
        # ====================================================================
        # ADD LONGEST PERSISTENT EVENT MARKERS (STRAIGHT BLACK LINES BELOW THRESHOLD)
        # ====================================================================
        if stats and 'era5_land' in stats:
            persistent_events = stats['era5_land'].get('heat_events', {}).get('persistent_events', {})
            persist_days_list = persistent_events.get('persistent_hot_days', [])
            persist_nights_list = persistent_events.get('persistent_hot_nights', [])
            
            # Get y-limits for positioning markers BELOW thresholds (~5cm in figure space)
            y_min, y_max = ax2.get_ylim()
            marker_offset = (y_max - y_min) * 0.12  # ~5cm below threshold
            
            custom_lines = []
            
            # Find and draw LONGEST persistent DAY event (Pi)
            if persist_days_list:
                longest_day_event = max(persist_days_list, key=lambda x: x['duration'])
                start_date = longest_day_event['start_date']
                end_date = longest_day_event['end_date']
                duration = longest_day_event['duration']
                
                event_mask = (era5_df['date'] >= start_date) & (era5_df['date'] <= end_date)
                event_dates = era5_df.loc[event_mask, 'date']
                
                if len(event_dates) > 0:
                    marker_y = era5_day_threshold - marker_offset
                    
                    # Draw straight horizontal black line
                    ax2.plot(event_dates, [marker_y] * len(event_dates), 
                            color='black', linewidth=3, solid_capstyle='butt',
                            alpha=0.9, zorder=10)
                    
                    # Add vertical bar '|' at start and end
                    bar_height = (y_max - y_min) * 0.015
                    ax2.plot([event_dates.iloc[0], event_dates.iloc[0]], 
                            [marker_y - bar_height, marker_y + bar_height], 
                            color='black', linewidth=3, solid_capstyle='butt', zorder=11)
                    ax2.plot([event_dates.iloc[-1], event_dates.iloc[-1]], 
                            [marker_y - bar_height, marker_y + bar_height], 
                            color='black', linewidth=3, solid_capstyle='butt', zorder=11)
                    
                    # Add label "P_i" with ORANGE background (matching day range)
                    mid_date = event_dates.iloc[len(event_dates)//2]
                    ax2.text(mid_date, marker_y + bar_height*2, 'P$_i$', 
                            fontsize=11, fontweight='bold', ha='center', va='bottom',
                            bbox=dict(boxstyle='round,pad=0.3', facecolor='orange', alpha=0.6, edgecolor='black'))
                    
                    custom_lines.append(
                        Line2D([0], [0], color='black', linewidth=3, marker='|', markersize=10,
                               label=f'Pi: Longest Day Event ({duration} days)')
                    )
            
            # Find and draw LONGEST persistent NIGHT event (Pii)
            if persist_nights_list:
                longest_night_event = max(persist_nights_list, key=lambda x: x['duration'])
                start_date = longest_night_event['start_date']
                end_date = longest_night_event['end_date']
                duration = longest_night_event['duration']
                
                event_mask = (era5_df['date'] >= start_date) & (era5_df['date'] <= end_date)
                event_dates = era5_df.loc[event_mask, 'date']
                
                if len(event_dates) > 0:
                    marker_y = era5_night_threshold - marker_offset
                    
                    # Draw straight horizontal black line
                    ax2.plot(event_dates, [marker_y] * len(event_dates), 
                            color='black', linewidth=3, solid_capstyle='butt',
                            alpha=0.9, zorder=10)
                    
                    # Add vertical bar '|' at start and end
                    bar_height = (y_max - y_min) * 0.015
                    ax2.plot([event_dates.iloc[0], event_dates.iloc[0]], 
                            [marker_y - bar_height, marker_y + bar_height], 
                            color='black', linewidth=3, solid_capstyle='butt', zorder=11)
                    ax2.plot([event_dates.iloc[-1], event_dates.iloc[-1]], 
                            [marker_y - bar_height, marker_y + bar_height], 
                            color='black', linewidth=3, solid_capstyle='butt', zorder=11)
                    
                    # Add label "P_ii" with PURPLE background (matching night range)
                    mid_date = event_dates.iloc[len(event_dates)//2]
                    ax2.text(mid_date, marker_y + bar_height*2, 'P$_{ii}$', 
                            fontsize=11, fontweight='bold', ha='center', va='bottom',
                            bbox=dict(boxstyle='round,pad=0.3', facecolor='purple', alpha=0.6, edgecolor='black'))
                    
                    custom_lines.append(
                        Line2D([0], [0], color='black', linewidth=3, marker='|', markersize=10,
                               label=f'P$_{{ii}}$: Longest Night Event ({duration} nights)')
                    )
            
            # Combine Pi and Pii into single legend entry if both exist
            if len(custom_lines) == 2:
                # Replace with single combined entry
                day_duration = persist_days_list[0]['duration'] if persist_days_list else 0
                night_duration = persist_nights_list[0]['duration'] if persist_nights_list else 0
                custom_lines = [
                    Line2D([0], [0], color='black', linewidth=3, marker='|', markersize=10,
                           label=f'Longest Events: P$_i$ ({day_duration}d), P$_{{ii}}$ ({night_duration}n)')
                ]
            
            # Add summary text with lighter background
            n_persist_days = len(persist_days_list)
            n_persist_nights = len(persist_nights_list)
            longest_duration_days = max([event['duration'] for event in persist_days_list], default=0)
            longest_duration_nights = max([event['duration'] for event in persist_nights_list], default=0)
            
            persist_text = f"Persistent Events (ERA5-Land):\nDays: {n_persist_days} total (longest: {longest_duration_days} days)\nNights: {n_persist_nights} total (longest: {longest_duration_nights} nights)"
            ax2.text(0.02, 0.02, persist_text, transform=ax2.transAxes, 
                    fontsize=10, verticalalignment='bottom', horizontalalignment='left',
                    bbox=dict(boxstyle='round', facecolor='white', alpha=0.9, edgecolor='gray', linewidth=1))
        
        ax2.set_title(f'ERA5-Land LST Analysis - Longest Persistent Events Highlighted - {city_name} ({study_year})', 
                     fontsize=14, fontweight='bold')
        ax2.set_ylabel('Temperature (°C)', fontsize=12, fontweight='bold')
        ax2.grid(True, alpha=0.3)
        
        # Combine legends
        handles2, labels2 = ax2.get_legend_handles_labels()
        if custom_lines:
            handles2.extend(custom_lines)
        ax2.legend(handles=handles2, loc='upper right', fontsize=9, ncol=2)
    
    # Format x-axis
    ax2.set_xlabel('Date', fontsize=12, fontweight='bold')
    ax2.xaxis.set_major_locator(mdates.MonthLocator())
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%b'))
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45)
    
    plt.tight_layout()
    
    # Save plot
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    png_path = output_dir / f'{city_name}_MODIS_ERA5_persistent_markers_{study_year}.png'
    pdf_path = output_dir / f'{city_name}_MODIS_ERA5_persistent_markers_{study_year}.pdf'
    
    plt.savefig(png_path, dpi=300, bbox_inches='tight')
    plt.savefig(pdf_path, format='pdf', bbox_inches='tight')
    plt.close()
    
    print(f"        📊 Saved enhanced plot: {png_path.name} + {pdf_path.name}")
    return png_path


# ====================================================================
# SEVIRI LST VISUALIZATION
# ====================================================================

def create_persistent_heat_event_maps(
    cities_data: dict,
    period: str = 'day',
    base_dir: str = None,
    study_year: int = 2024,
    aoi_dir: str = None,
    dpi: int = 300,
    figsize: tuple = None,
    max_combined_cities: int = 5,
    save_individual: bool = True
) -> plt.Figure:
    """
    Create publication-ready multi-panel Persistent Heat Event Maps showing SEVIRI LST
    with all geospatial layers (water, roads, places, boundaries).
    
    Similar to create_publication_study_area_map() but showing LST as background
    with overlaid geospatial features.
    
    Parameters
    ----------
    cities_data : dict
        Dictionary of city data from load_seviri_cities_lst()
    period : str
        'day' or 'night'
    base_dir : str or Path
        Base output directory for saving figures
    study_year : int
        Study year
    aoi_dir : str or Path
        Base AOI directory for loading boundaries and features
    dpi : int, optional
        Figure DPI (default: 300)
    figsize : tuple, optional
        Figure size (width, height). If None, calculated from number of cities.
    max_combined_cities : int, optional
        Maximum number of cities to include on the combined multi-panel figure
        (default 5).  When more cities are available, only the first
        *max_combined_cities* (alphabetically) appear on the combined figure.
        Individual per-city maps are always saved for every city.
    save_individual : bool, optional
        If True (default), save a standalone single-panel map for every city
        into ``<base_dir>/../City_<name>/Figures/``.
    
    Returns
    -------
    plt.Figure
        The matplotlib figure object
    
    Notes
    -----
    - LST displayed with YlOrRd colormap (20-55°C day, 18-30°C night)
    - Water bodies shown as blue-filled polygons (>3 sq km)
    - Roads displayed as thin grey lines
    - Places labeled (~1 per 5 sq km using buffer zones)
    - Main/Adjacent boundaries shown as hollow (unfilled) polygons
    - Dynamic layout works for any number of cities
    - Scale bars inside map frames
    - Unified legend and north arrow
    """
    import rasterio
    from pathlib import Path
    from matplotlib.gridspec import GridSpec
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D
    from matplotlib import cm
    from matplotlib.colors import Normalize
    import math
    import string
    
    # Import adjustText for intelligent text placement
    try:
        from adjustText import adjust_text
        ADJUSTTEXT_AVAILABLE = True
    except ImportError:
        ADJUSTTEXT_AVAILABLE = False
        print("  adjustText not available - text overlap may occur")
        print("    Install with: pip install adjustText")
    
    # Filter cities with data for this period
    available_cities = {name: data for name, data in cities_data.items() 
                       if period in data}
    
    n_cities = len(available_cities)
    if n_cities == 0:
        print(f"  No {period} data available")
        return None
    
    # Decide which cities go on the combined figure
    sorted_city_names = sorted(available_cities.keys())
    if n_cities > max_combined_cities:
        combined_city_names = sorted_city_names[:max_combined_cities]
        print(f"\n  {n_cities} cities available — combined figure limited "
              f"to first {max_combined_cities}.")
        print(f"    Individual maps will be saved for ALL {n_cities} cities.")
    else:
        combined_city_names = sorted_city_names
    
    # Build the subset dict used for the combined figure
    combined_cities = {name: available_cities[name]
                       for name in combined_city_names}
    
    print(f"\n{'='*80}")
    print(f"CREATING PERSISTENT HEAT EVENT MAPS - {period.upper()}")
    print(f"{'='*80}")
    print(f"Cities (combined figure): {len(combined_cities)} / {n_cities} total")
    
    # Temperature scales and colormap
    if period == 'day':
        vmin, vmax = 20, 55
    else:  # night
        vmin, vmax = 18, 30
    
    cmap = cm.get_cmap('YlOrRd')
    norm = Normalize(vmin=vmin, vmax=vmax)
    
    # Dynamic grid layout (max 3 columns) - uses combined_cities count
    n_combined = len(combined_cities)
    max_cols = 3
    n_cols = min(n_combined, max_cols)
    n_rows = math.ceil(n_combined / n_cols)
    
    # Calculate figure size if not provided - enhanced for 30+ cities
    if figsize is None:
        fig_width = 5 * n_cols
        fig_height = 5 * n_rows + 2.5  # Extra space for external scale bars
        figsize = (fig_width, fig_height)
    
    print(f"Layout: {n_rows} rows x {n_cols} cols")
    print(f"Figure size: {figsize[0]}\" x {figsize[1]}\"")
    
    # Create figure
    fig = plt.figure(figsize=figsize, dpi=dpi)
    # Fix #2: Better spacing - reduced title overlap and gaps
    gs = GridSpec(n_rows, n_cols, figure=fig, 
                  left=0.08, right=0.95, top=0.95, bottom=0.10,
                  hspace=0.25, wspace=0.25)
    
    panel_labels = list(string.ascii_uppercase)
    
    # Helper function to load geospatial features
    def load_city_features(city_name, aoi_base_dir):
        """Load all geospatial features for a city"""
        if aoi_base_dir is None:
            return None, None, None, None
        
        city_dir = Path(aoi_base_dir) / f'City_{city_name}'
        features_dir = city_dir / 'Features'
        osm_dir = features_dir / 'OSM'
        
        features = {}
        
        # Load Main polygon
        main_file = features_dir / f'{city_name}_Main_Polygon.geojson'
        if main_file.exists():
            features['main'] = gpd.read_file(str(main_file))
        
        # Load Adjacent polygons
        adj_file = features_dir / f'{city_name}_Adjacent_Polygons.geojson'
        if adj_file.exists():
            features['adjacent'] = gpd.read_file(str(adj_file))
        
        # Load water bodies
        water_file = osm_dir / f'{city_name}_water_bodies.geojson'
        if water_file.exists():
            water_gdf = gpd.read_file(str(water_file))
            # Filter water bodies >= 3 sq km
            if not water_gdf.empty and 'area_km2' in water_gdf.columns:
                features['water'] = water_gdf[water_gdf['area_km2'] >= 3.0]
            elif not water_gdf.empty:
                # Calculate area if not present
                water_metric = water_gdf.to_crs('EPSG:32632')
                water_gdf['area_km2'] = water_metric.geometry.area / 1e6
                features['water'] = water_gdf[water_gdf['area_km2'] >= 3.0]
        
        # Load roads
        roads_file = osm_dir / f'{city_name}_roads.geojson'
        if roads_file.exists():
            features['roads'] = gpd.read_file(str(roads_file))
        
        # Load places
        places_file = osm_dir / f'{city_name}_places.geojson'
        if places_file.exists():
            places_gdf = gpd.read_file(str(places_file))
            # Filter to cities (capitals), towns and suburbs
            if 'place' in places_gdf.columns:
                features['places'] = places_gdf[
                    places_gdf['place'].isin(['city', 'town', 'suburb'])
                ]
        
        return features
    
    # Helper function to filter places by buffer with better spatial distribution
    def filter_places_by_buffer(places_gdf, buffer_km=4.87, max_labels=10):
        """Filter places to ~1 per 75 sq km (pi * 4.87^2  75) with max label limit
        Uses improved spatial distribution to cover map area better
        
        Args:
            places_gdf: GeoDataFrame of places
            buffer_km: Buffer distance in km (4.87 km = ~75 sq km coverage)
            max_labels: Maximum number of labels to show per map
        """
        if places_gdf is None or places_gdf.empty:
            return None
        
        if 'name' not in places_gdf.columns:
            return None
        
        # Only keep places with names
        named_places = places_gdf[places_gdf['name'].notna()].copy()
        
        if named_places.empty:
            return None
        
        # Convert to metric CRS for buffer calculation
        metric_crs = 'EPSG:32632'
        places_metric = named_places.to_crs(metric_crs)
        
        # Sort by importance: city > town > suburb (capitals first)
        if 'place' in places_metric.columns:
            place_order = {'city': 0, 'town': 1, 'suburb': 2}
            places_metric['priority'] = places_metric['place'].map(
                lambda x: place_order.get(x, 3)
            )
            places_metric = places_metric.sort_values('priority')
        
        # Apply spatial filtering with max limit
        selected_indices = []
        used_geometries = []
        
        for idx, place in places_metric.iterrows():
            # Stop if we've reached max labels
            if len(selected_indices) >= max_labels:
                break
                
            point = place.geometry
            buffer_m = buffer_km * 1000
            
            # Check if too close to already selected places
            too_close = False
            for used_geom in used_geometries:
                if point.distance(used_geom) < buffer_m:
                    too_close = True
                    break
            
            if not too_close:
                selected_indices.append(idx)
                used_geometries.append(point)
        
        return named_places.loc[selected_indices]
    
    # Plot each city (combined figure only — limited to combined_cities)
    legend_collected = False
    legend_handles = []
    legend_labels = []
    
    for idx, (city_name, city_data) in enumerate(sorted(combined_cities.items())):
        row = idx // n_cols
        col = idx % n_cols
        ax = fig.add_subplot(gs[row, col])
        
        panel_letter = panel_labels[idx]
        
        print(f"\n{panel_letter}: {city_name}")
        
        lst_file = city_data.get(f'{period}_file')
        event_period = city_data.get(f'{period}_event', 'N/A')
        
        if not lst_file or not Path(lst_file).exists():
            print(f"    LST file not found")
            continue
        
        try:
            # Open LST raster
            with rasterio.open(lst_file) as src:
                data_raw = src.read(1)
                
                # Mask nodata
                if src.nodata is not None:
                    data_raw = np.where(data_raw == src.nodata, np.nan, data_raw)
                data_masked = np.ma.masked_invalid(data_raw)
                
                extent = [src.bounds.left, src.bounds.right, 
                         src.bounds.bottom, src.bounds.top]
                lst_crs = src.crs
                
                # Create LST extent polygon for clipping features to raster bounds
                from shapely.geometry import box
                lst_extent = box(src.bounds.left, src.bounds.bottom, 
                                src.bounds.right, src.bounds.top)
                
                # Plot LST as background
                im = ax.imshow(data_masked, cmap=cmap, norm=norm,
                             extent=extent, interpolation='nearest', 
                             aspect='equal', zorder=1)
                
                # Load geospatial features
                features = load_city_features(city_name, aoi_dir)
                
                if features:
                    # Plot water bodies (blue-filled polygons) - clipped to LST extent
                    if 'water' in features and not features['water'].empty:
                        water_proj = features['water'].to_crs(lst_crs)
                        # Clip to LST bounds
                        water_clipped = water_proj.clip(lst_extent)
                        if not water_clipped.empty:
                            water_clipped.plot(ax=ax, facecolor='steelblue', 
                                           edgecolor='darkblue', linewidth=0.5, 
                                           alpha=0.7, zorder=3)
                            print(f"   Water: {len(water_clipped)} bodies (clipped)")
                    
                    # Roads removed from visualization
                    # if 'roads' in features and not features['roads'].empty:
                    #     roads_proj = features['roads'].to_crs(lst_crs)
                    #     roads_proj.plot(ax=ax, color='grey', linewidth=0.15, 
                    #                    alpha=0.3, zorder=0.5)
                    #     print(f"   Roads: {len(roads_proj)} segments")
                    
                    # Plot Main boundary (hollow, thick black line) - clipped to LST extent
                    if 'main' in features and not features['main'].empty:
                        main_proj = features['main'].to_crs(lst_crs)
                        main_clipped = main_proj.clip(lst_extent)
                        if not main_clipped.empty:
                            main_clipped.boundary.plot(ax=ax, color='black', 
                                                   linewidth=2.5, zorder=5)
                            print(f"   Main boundary (clipped)")
                    
                    # Plot Adjacent boundaries (hollow, dashed black line) - clipped to LST extent
                    if 'adjacent' in features and not features['adjacent'].empty:
                        adj_proj = features['adjacent'].to_crs(lst_crs)
                        adj_clipped = adj_proj.clip(lst_extent)
                        if not adj_clipped.empty:
                            adj_clipped.boundary.plot(ax=ax, color='black', 
                                                  linewidth=1.5, linestyle='--', zorder=5)
                            print(f"   Adjacent boundaries: {len(adj_clipped)} (clipped)")
                    
                    # Plot place labels (max 10 labels, ~1 per 75 sq km) - only within LST bounds
                    if 'places' in features and not features['places'].empty:
                        places_filtered = filter_places_by_buffer(features['places'], 
                                                                 buffer_km=4.87, max_labels=10)
                        if places_filtered is not None and not places_filtered.empty:
                            places_proj = places_filtered.to_crs(lst_crs)
                            # Clip to LST extent - only keep places inside raster bounds
                            places_proj = places_proj.clip(lst_extent)
                            
                            if places_proj.empty:
                                print(f"  ⚠ No places within LST bounds")
                                continue
                            
                            # Plot markers
                            places_proj.plot(ax=ax, color='darkred', markersize=22,
                                           marker='o', edgecolor='white', 
                                           linewidth=0.8, zorder=6, alpha=0.95)
                            
                            # Add labels with adjustText for smart positioning
                            texts = []
                            for _, place in places_proj.iterrows():
                                name = place['name']
                                x, y = place.geometry.x, place.geometry.y
                                t = ax.text(x, y, name,
                                          fontsize=9, color='darkred',
                                          fontweight='bold',
                                          bbox=dict(boxstyle='round,pad=0.15',
                                                   facecolor='white',
                                                   alpha=0.9, edgecolor='none'),
                                          zorder=7)
                                texts.append(t)
                            
                            # Use adjustText to prevent overlap WITHOUT arrows
                            if ADJUSTTEXT_AVAILABLE and len(texts) > 0:
                                adjust_text(texts, ax=ax,
                                          arrowprops=None,  # Remove arrows
                                          expand_points=(2.0, 2.0),
                                          expand_text=(1.5, 1.5),
                                          force_points=(0.3, 0.3),
                                          force_text=(0.5, 0.5),
                                          lim=500)  # Limit iterations
                            
                            print(f"   Places: {len(places_proj)} labels (max 10)")
                
                # Set axis limits
                ax.set_xlim(src.bounds.left, src.bounds.right)
                ax.set_ylim(src.bounds.bottom, src.bounds.top)
                ax.set_aspect('equal', adjustable='box')
                
                # Calculate statistics
                valid_data = data_masked.compressed()
                if len(valid_data) > 0:
                    mean_temp = np.mean(valid_data)
                    min_temp = np.min(valid_data)
                    max_temp = np.max(valid_data)
                    
                    # Panel letter
                    title = f"{panel_letter}"
                    
                    map_width = src.bounds.right - src.bounds.left
                    map_height = src.bounds.top - src.bounds.bottom
                    center_x = (src.bounds.left + src.bounds.right) / 2
                    
                    # City name centered at top of map
                    ax.text(center_x, 
                           src.bounds.top - map_height * 0.02,
                           city_name, fontsize=10, fontweight='bold',
                           ha='center', va='top', color='black',
                           bbox=dict(boxstyle='round,pad=0.15',
                                   facecolor='white', alpha=0.9,
                                   edgecolor='none'),
                           zorder=20)
                    
                    # Store stats for display below scale bar
                    stats_text = f"{event_period}: {mean_temp:.1f}°C ({min_temp:.1f}–{max_temp:.1f}°C)"
                else:
                    title = f"{panel_letter}"
                    center_x = (src.bounds.left + src.bounds.right) / 2
                    center_y = (src.bounds.top + src.bounds.bottom) / 2
                    ax.text(center_x, center_y, f"{city_name}\nNo valid data",
                           fontsize=10, fontweight='bold', ha='center',
                           va='center', color='red',
                           bbox=dict(boxstyle='round,pad=0.5',
                                   facecolor='white', alpha=0.9,
                                   edgecolor='red'),
                           zorder=20)
                    stats_text = "No valid data"
                
                ax.set_title(title, fontsize=12, fontweight='bold', pad=8, loc='center')
                # ax.set_xlabel('Longitude', fontsize=8)  # Commented out
                # ax.set_ylabel('Latitude', fontsize=8)   # Commented out
                ax.set_xticks([])
                ax.set_yticks([])
                
                # Fix: Uniform 3cm scale bar with integer km only
                map_width = src.bounds.right - src.bounds.left
                map_height = src.bounds.top - src.bounds.bottom
                
                # Estimate scale (depends on latitude)
                center_lat = (src.bounds.top + src.bounds.bottom) / 2
                km_per_deg = 111 * np.cos(np.radians(center_lat))
                
                # Calculate 3cm in figure coordinates (assuming ~2.54cm per inch)
                fig_width_inches = figsize[0] / n_cols
                scale_bar_inches = 3.0 / 2.54  # 3 cm in inches
                scale_bar_frac = scale_bar_inches / fig_width_inches
                
                # Convert to data coordinates
                scale_deg = map_width * scale_bar_frac * 0.7  # 0.7 to keep it reasonable
                scale_km = scale_deg * km_per_deg
                
                # Position below map in axis coordinates
                scale_x_center = (src.bounds.left + src.bounds.right) / 2
                scale_x_start = scale_x_center - scale_deg / 2
                scale_x_end = scale_x_center + scale_deg / 2
                
                # Use axis transform to place below plot
                from matplotlib.transforms import blended_transform_factory
                trans = blended_transform_factory(ax.transData, ax.transAxes)
                
                # Draw scale bar below x-axis
                ax.plot([scale_x_start, scale_x_end], [-0.08, -0.08],
                       'k-', linewidth=2, transform=trans, clip_on=False, zorder=25)
                ax.plot([scale_x_start, scale_x_start], [-0.09, -0.07],
                       'k-', linewidth=2, transform=trans, clip_on=False, zorder=25)
                ax.plot([scale_x_end, scale_x_end], [-0.09, -0.07],
                       'k-', linewidth=2, transform=trans, clip_on=False, zorder=25)
                
                # Show integer km only (no decimals, no symbols)
                ax.text(scale_x_center, -0.11, f'{int(round(scale_km))} km',
                       fontsize=8, ha='center', va='top',
                       transform=trans, clip_on=False, zorder=25)
                
                # Add LST stats below scale bar with increased font size
                ax.text(scale_x_center, -0.16, stats_text,
                       fontsize=9, ha='center', va='top', style='italic',
                       transform=trans, clip_on=False, zorder=25)
                
                # Collect legend elements (only once)
                if not legend_collected:
                    legend_handles = [
                        Patch(facecolor='steelblue', edgecolor='darkblue',
                             linewidth=0.5, alpha=0.7, label='Water Bodies (≥3 km²)'),
                        Line2D([0], [0], marker='o', color='darkred',
                              markersize=6, linestyle='', markeredgecolor='white',
                              markeredgewidth=0.5, label='Places'),
                        Patch(facecolor='none', edgecolor='black',
                             linewidth=2.5, label='Main Urban Block'),
                        Patch(facecolor='none', edgecolor='black',
                             linewidth=1.5, linestyle='--',
                             label='Adjacent Urban Block(s)')
                    ]
                    legend_collected = True
                
        except Exception as e:
            print(f"   Error: {e}")
            continue
    
    # Hide empty subplots
    for idx in range(n_combined, n_rows * n_cols):
        row = idx // n_cols
        col = idx % n_cols
        fig.add_subplot(gs[row, col]).set_visible(False)
    
    # Add shared colorbar on left side
    cbar_ax = fig.add_axes([0.08, 0.02, 0.30, 0.015])
    cbar = fig.colorbar(cm.ScalarMappable(norm=norm, cmap=cmap),
                       cax=cbar_ax, orientation='horizontal')
    cbar.set_label('Land Surface Temperature (°C)', 
                  fontsize=11, fontweight='bold')
    cbar.ax.tick_params(labelsize=9)
    
    # Add compact legend in middle (same row as colorbar)
    if legend_handles:
        fig.legend(handles=legend_handles, loc='lower center',
                  bbox_to_anchor=(0.55, 0.01), ncol=2,
                  fontsize=8.5, frameon=True, fancybox=True,
                  edgecolor='gray', framealpha=0.95, columnspacing=0.8)
    
    # Add north arrow on far right (same row as colorbar and legend)
    from matplotlib.patches import FancyArrowPatch
    ax_north = fig.add_axes([0.88, 0.015, 0.035, 0.045])
    ax_north.set_xlim(0, 1)
    ax_north.set_ylim(0, 1)
    ax_north.axis('off')
    arrow = FancyArrowPatch((0.5, 0.15), (0.5, 0.75),
                           arrowstyle='-|>', mutation_scale=14,
                           color='black', linewidth=2)
    ax_north.add_patch(arrow)
    ax_north.text(0.5, 0.85, 'N', fontsize=12, fontweight='bold',
                 ha='center', va='bottom')
    ax_north.plot([0.3, 0.7], [0.15, 0.15], 'k-', linewidth=2)
    
    # Figure title - Fix #5: Adjusted y-position to prevent overlap with panel B
    period_label = 'Daytime' if period == 'day' else 'Nighttime'
    fig.suptitle(f'Persistent Heat Event Maps: {period_label} LST - {study_year}',
                fontsize=13, fontweight='bold', y=0.99)
    
    # Save figure
    if base_dir:
        output_dir = Path(base_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        png_path = output_dir / f'Persistent_Heat_Event_Map_{period}_{study_year}.png'
        pdf_path = output_dir / f'Persistent_Heat_Event_Map_{period}_{study_year}.pdf'
        
        fig.savefig(png_path, dpi=dpi, bbox_inches='tight', 
                   facecolor='white', pad_inches=0.1)
        fig.savefig(pdf_path, format='pdf', bbox_inches='tight',
                   facecolor='white', pad_inches=0.1)
        
        print(f"\n{'='*80}")
        print(f" Saved combined: {png_path.name}")
        print(f" Saved combined: {pdf_path.name}")
        print(f"{'='*80}")
    
    # -----------------------------------------------------------------
    # Individual per-city maps (saved into each city's Figures folder)
    # -----------------------------------------------------------------
    if save_individual and base_dir:
        analysis_root = Path(base_dir).parent  # e.g. .../04_trend_analysis_daily
        period_label_ind = 'Daytime' if period == 'day' else 'Nighttime'
        
        print(f"\n{'='*80}")
        print(f"SAVING INDIVIDUAL CITY MAPS ({period.upper()}) — {n_cities} cities")
        print(f"{'='*80}")
        
        for city_name in sorted_city_names:
            city_data_ind = available_cities[city_name]
            city_fig_dir = analysis_root / f'City_{city_name}' / 'Figures'
            city_fig_dir.mkdir(parents=True, exist_ok=True)
            
            lst_file = city_data_ind.get(f'{period}_file')
            event_period = city_data_ind.get(f'{period}_event', 'N/A')
            
            if not lst_file or not Path(lst_file).exists():
                print(f"    {city_name}: LST file not found — skipping")
                continue
            
            try:
                with rasterio.open(lst_file) as src:
                    data_raw = src.read(1)
                    if src.nodata is not None:
                        data_raw = np.where(data_raw == src.nodata, np.nan, data_raw)
                    data_masked = np.ma.masked_invalid(data_raw)
                    
                    extent = [src.bounds.left, src.bounds.right,
                             src.bounds.bottom, src.bounds.top]
                    lst_crs = src.crs
                    
                    from shapely.geometry import box as shapely_box
                    lst_extent = shapely_box(src.bounds.left, src.bounds.bottom,
                                            src.bounds.right, src.bounds.top)
                    
                    # Single-panel figure
                    ind_fig, ind_ax = plt.subplots(1, 1, figsize=(6, 6), dpi=dpi)
                    
                    im = ind_ax.imshow(data_masked, cmap=cmap, norm=norm,
                                       extent=extent, interpolation='nearest',
                                       aspect='equal', zorder=1)
                    
                    # Overlay geospatial features
                    features = load_city_features(city_name, aoi_dir)
                    if features:
                        if 'water' in features and not features['water'].empty:
                            water_proj = features['water'].to_crs(lst_crs)
                            water_clipped = water_proj.clip(lst_extent)
                            if not water_clipped.empty:
                                water_clipped.plot(ax=ind_ax, facecolor='steelblue',
                                                   edgecolor='darkblue', linewidth=0.5,
                                                   alpha=0.7, zorder=3)
                        if 'main' in features and not features['main'].empty:
                            main_proj = features['main'].to_crs(lst_crs)
                            main_clipped = main_proj.clip(lst_extent)
                            if not main_clipped.empty:
                                main_clipped.boundary.plot(ax=ind_ax, color='black',
                                                           linewidth=2.5, zorder=5)
                        if 'adjacent' in features and not features['adjacent'].empty:
                            adj_proj = features['adjacent'].to_crs(lst_crs)
                            adj_clipped = adj_proj.clip(lst_extent)
                            if not adj_clipped.empty:
                                adj_clipped.boundary.plot(ax=ind_ax, color='black',
                                                          linewidth=1.5,
                                                          linestyle='--', zorder=5)
                        if 'places' in features and not features['places'].empty:
                            places_filtered = filter_places_by_buffer(
                                features['places'], buffer_km=4.87, max_labels=10)
                            if places_filtered is not None and not places_filtered.empty:
                                places_proj = places_filtered.to_crs(lst_crs)
                                places_proj = places_proj.clip(lst_extent)
                                if not places_proj.empty:
                                    places_proj.plot(ax=ind_ax, color='darkred',
                                                     markersize=22, marker='o',
                                                     edgecolor='white',
                                                     linewidth=0.8, zorder=6,
                                                     alpha=0.95)
                                    texts_ind = []
                                    for _, place in places_proj.iterrows():
                                        t = ind_ax.text(
                                            place.geometry.x, place.geometry.y,
                                            place['name'], fontsize=9,
                                            color='darkred', fontweight='bold',
                                            bbox=dict(boxstyle='round,pad=0.15',
                                                      facecolor='white',
                                                      alpha=0.9,
                                                      edgecolor='none'),
                                            zorder=7)
                                        texts_ind.append(t)
                                    if ADJUSTTEXT_AVAILABLE and texts_ind:
                                        adjust_text(texts_ind, ax=ind_ax,
                                                    arrowprops=None,
                                                    expand_points=(2.0, 2.0),
                                                    expand_text=(1.5, 1.5),
                                                    force_points=(0.3, 0.3),
                                                    force_text=(0.5, 0.5),
                                                    lim=500)
                    
                    ind_ax.set_xlim(src.bounds.left, src.bounds.right)
                    ind_ax.set_ylim(src.bounds.bottom, src.bounds.top)
                    ind_ax.set_aspect('equal', adjustable='box')
                    ind_ax.set_xticks([])
                    ind_ax.set_yticks([])
                    
                    # Statistics text
                    valid_data = data_masked.compressed()
                    if len(valid_data) > 0:
                        mean_t = np.mean(valid_data)
                        min_t = np.min(valid_data)
                        max_t = np.max(valid_data)
                        stats_txt = (f"{event_period}: {mean_t:.1f}°C "
                                     f"({min_t:.1f}–{max_t:.1f}°C)")
                    else:
                        stats_txt = "No valid data"
                    
                    ind_ax.set_title(
                        f'{city_name} — {period_label_ind} Persistent Heat Event '
                        f'({study_year})\n{stats_txt}',
                        fontsize=11, fontweight='bold', pad=10)
                    
                    # Colorbar
                    cb = ind_fig.colorbar(
                        cm.ScalarMappable(norm=norm, cmap=cmap), ax=ind_ax,
                        orientation='horizontal', shrink=0.7, pad=0.04)
                    cb.set_label('Land Surface Temperature (°C)', fontsize=9)
                    cb.ax.tick_params(labelsize=8)
                    
                    ind_fig.tight_layout()
                    
                    # Save
                    stem = f'Persistent_Heat_Event_Map_{period}_{study_year}_{city_name}'
                    ind_png = city_fig_dir / f'{stem}.png'
                    ind_pdf = city_fig_dir / f'{stem}.pdf'
                    ind_fig.savefig(ind_png, dpi=dpi, bbox_inches='tight',
                                    facecolor='white', pad_inches=0.1)
                    ind_fig.savefig(ind_pdf, format='pdf', bbox_inches='tight',
                                    facecolor='white', pad_inches=0.1)
                    plt.close(ind_fig)
                    
                    print(f"   {city_name}: {ind_png.name}")
                    
            except Exception as e:
                print(f"   {city_name}: {e}")
                continue
        
        print(f"\n{'='*80}")
        print(f" Individual maps complete — {n_cities} cities")
        print(f"{'='*80}")
    
    return fig


def visualize_seviri_all_cities(cities_data, period='day', base_dir=None, study_year=2024, aoi_dir=None, dpi=300):
    """
    Create multi-city SEVIRI LST visualization grid with cartographic elements.
    
    DEPRECATED: Use create_persistent_heat_event_maps() for publication-ready maps
    with all geospatial layers (water, roads, places, boundaries).
    
    Parameters:
    -----------
    cities_data : dict
        Dictionary of city data from load_seviri_cities_lst()
    period : str
        'day' or 'night'
    base_dir : str or Path
        Base output directory
    study_year : int
        Study year
    aoi_dir : str or Path
        Base AOI directory for loading boundaries
    dpi : int
        Figure DPI
    
    Returns:
    --------
    matplotlib.figure.Figure or None
    """
    print("\n  Note: visualize_seviri_all_cities() is deprecated.")
    print("    Use create_persistent_heat_event_maps() for publication maps.\n")
    
    # Call the new function
    return create_persistent_heat_event_maps(
        cities_data=cities_data,
        period=period,
        base_dir=base_dir,
        study_year=study_year,
        aoi_dir=aoi_dir,
        dpi=dpi
    )
    import rasterio
    from pathlib import Path
    from matplotlib.gridspec import GridSpec
    from matplotlib.patches import Patch
    from matplotlib import cm
    from matplotlib.colors import Normalize
    
    # Filter cities with data for this period
    available_cities = {name: data for name, data in cities_data.items() 
                       if period in data}
    
    n_cities = len(available_cities)
    if n_cities == 0:
        print(f"  No {period} data available")
        return None
    
    # Fixed temperature scales and colormap
    if period == 'day':
        vmin, vmax = 20, 55
    else:  # night
        vmin, vmax = 18, 30
    
    # Use Yellow-Orange-Red colormap (same for both periods)
    cmap = cm.get_cmap('YlOrRd')
    norm = Normalize(vmin=vmin, vmax=vmax)
    
    # Determine grid layout (max 3 columns, dynamic)
    max_cols = 3
    n_cols = min(n_cities, max_cols)
    n_rows = int(np.ceil(n_cities / n_cols))
    
    # Create figure
    fig_width = 4 * n_cols
    fig_height = 4 * n_rows + 1.5
    fig = plt.figure(figsize=(fig_width, fig_height), dpi=dpi)
    gs = GridSpec(n_rows, n_cols, figure=fig, 
                  left=0.08, right=0.95, top=0.93, bottom=0.12,
                  hspace=0.35, wspace=0.25)
    
    # Helper function to load city boundaries
    def load_city_boundaries(city_name):
        """Load main and adjacent city boundary files"""
        if aoi_dir is None:
            print(f"      AOI directory not provided for {city_name}")
            return None, None
            
        city_aoi_dir = Path(aoi_dir) / f'City_{city_name}'
        main_file = city_aoi_dir / 'Features' / f'{city_name}_Main_Polygon.geojson'
        adjacent_file = city_aoi_dir / 'Features' / f'{city_name}_Adjacent_Polygons.geojson'
        
        main_gdf = None
        adjacent_gdf = None
        
        if main_file.exists():
            try:
                main_gdf = gpd.read_file(str(main_file))
                print(f"     Loaded main boundary for {city_name}")
            except Exception as e:
                print(f"      Error loading main boundary for {city_name}: {e}")
        else:
            print(f"      Main boundary file not found: {main_file}")
        
        if adjacent_file.exists():
            try:
                adjacent_gdf = gpd.read_file(str(adjacent_file))
                print(f"     Loaded adjacent boundaries for {city_name}")
            except Exception as e:
                print(f"      Error loading adjacent boundaries for {city_name}: {e}")
        
        return main_gdf, adjacent_gdf
    
    # Plot each city
    for idx, (city_name, city_data) in enumerate(sorted(available_cities.items())):
        row = idx // n_cols
        col = idx % n_cols
        ax = fig.add_subplot(gs[row, col])
        
        lst_data = city_data[period]
        event_period = city_data.get(f'{period}_event', 'N/A')
        duration = city_data.get(f'{period}_duration', 'N/A')
        
        # Load the GeoTIFF to get extent and CRS
        lst_file = city_data.get(f'{period}_file')
        if lst_file and Path(lst_file).exists():
            try:
                with rasterio.open(lst_file) as src:
                    extent = [src.bounds.left, src.bounds.right, 
                             src.bounds.bottom, src.bounds.top]
                    
                    # Re-read data with proper nodata handling
                    data_raw = src.read(1)
                    # Mask nodata values (handle both NaN and nodata value)
                    if src.nodata is not None:
                        data_raw = np.where(data_raw == src.nodata, np.nan, data_raw)
                    data_masked = np.ma.masked_invalid(data_raw)
                    
                    # Plot LST
                    im = ax.imshow(data_masked, cmap=cmap, norm=norm,
                                 extent=extent, interpolation='nearest', aspect='equal')
                    
                    # Set exact axis limits
                    ax.set_xlim(src.bounds.left, src.bounds.right)
                    ax.set_ylim(src.bounds.bottom, src.bounds.top)
                    ax.set_aspect('equal', adjustable='box')
                    
                    # Overlay city boundaries
                    main_gdf, adjacent_gdf = load_city_boundaries(city_name)
                    
                    if main_gdf is not None and not main_gdf.empty:
                        main_gdf_proj = main_gdf.to_crs(src.crs)
                        main_gdf_proj.boundary.plot(ax=ax, color='black', 
                                                   linewidth=2.5, zorder=5)
                    
                    if adjacent_gdf is not None and not adjacent_gdf.empty:
                        adjacent_gdf_proj = adjacent_gdf.to_crs(src.crs)
                        adjacent_gdf_proj.boundary.plot(ax=ax, color='black',
                                                       linewidth=1.5, linestyle='--', zorder=5)
                    
                    # Title with event period AND statistics
                    valid_data = data_masked.compressed()
                    if len(valid_data) > 0:
                        mean_temp = np.mean(valid_data)
                        min_temp = np.min(valid_data)
                        max_temp = np.max(valid_data)
                        # Include event period in title
                        title = f"{city_name}\n{event_period}\n{mean_temp:.1f}°C ({min_temp:.1f}–{max_temp:.1f}°C)"
                    else:
                        title = f"{city_name}\n{event_period}\nNo valid data"
            
            except Exception as e:
                # Fallback to simple plot
                im = ax.imshow(lst_data, cmap=cmap, norm=norm)
                title = f"{city_name}\n{event_period}\nDuration: {duration} days"
        else:
            # Fallback to simple plot
            im = ax.imshow(lst_data, cmap=cmap, norm=norm)
            title = f"{city_name}\n{event_period}\nDuration: {duration} days"
        
        # Title
        ax.set_title(title, fontsize=10, fontweight='bold', pad=8)
        ax.set_xlabel('Longitude', fontsize=8)
        ax.set_ylabel('Latitude', fontsize=8)
        # Remove tick labels but keep axis labels
        ax.set_xticks([])
        ax.set_yticks([])
        
        # Clean spines
        for spine in ax.spines.values():
            spine.set_visible(False)
    
    # Add shared colorbar (centered, half width)
    cbar_ax = fig.add_axes([0.3, 0.05, 0.4, 0.015])
    cbar = fig.colorbar(cm.ScalarMappable(norm=norm, cmap=cmap),
                       cax=cbar_ax, orientation='horizontal')
    cbar.set_label('Land Surface Temperature (°C)', fontsize=11, fontweight='bold')
    cbar.ax.tick_params(labelsize=9)
    
    # Add legend for boundaries
    legend_elements = [
        Patch(facecolor='none', edgecolor='black', linewidth=2.5, label='Main Urban Block'),
        Patch(facecolor='none', edgecolor='black', linewidth=1.5, linestyle='--', 
              label='Adjacent Urban Block(s)')
    ]
    legend_ax = fig.add_axes([0.72, 0.04, 0.15, 0.04])
    legend_ax.axis('off')
    legend_ax.legend(handles=legend_elements, loc='center left',
                    frameon=True, fontsize=9, title='Boundaries', title_fontsize=10)
    
    # Add North arrow
    def create_north_arrow(ax, x=0.5, y=0.3, arrow_length=0.5, fontsize=12):
        ax.annotate('N', xy=(x, y), xytext=(x, y - arrow_length),
                   xycoords='axes fraction',
                   fontsize=fontsize, fontweight='bold',
                   ha='center', va='bottom',
                   arrowprops=dict(arrowstyle='->', lw=2, color='black'))
    
    north_ax = fig.add_axes([0.12, 0.04, 0.08, 0.04])
    north_ax.axis('off')
    create_north_arrow(north_ax)
    
    # Save figure (both PNG and PDF)
    if base_dir:
        output_dir = Path(base_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        png_path = output_dir / f'SEVIRI_LST_{period}_all_cities_{study_year}.png'
        pdf_path = output_dir / f'SEVIRI_LST_{period}_all_cities_{study_year}.pdf'
        
        fig.savefig(png_path, dpi=dpi, bbox_inches='tight', pad_inches=0.1)
        fig.savefig(pdf_path, format='pdf', bbox_inches='tight', pad_inches=0.1)
        
        print(f" Saved: {png_path.name} + {pdf_path.name}")
    
    plt.show()
    plt.close()
    
    return fig


def plot_lst_with_osm_overlay(lst_raster_path: str, city_name: str, period: str,
                               osm_dir: Path, output_path: str = None,
                               figsize=(12, 10), dpi=300):
    """
    Plot LST raster with OSM features overlaid (roads and prominent places).
    
    Parameters
    ----------
    lst_raster_path : str
        Path to clipped LST GeoTIFF file
    city_name : str
        Name of the city (e.g., 'Lagos', 'Abuja')
    period : str
        'day' or 'night'
    osm_dir : Path
        Path to OSM features directory (City_[Name]/OSM/)
    output_path : str, optional
        Path to save the figure
    figsize : tuple
        Figure size (width, height)
    dpi : int
        Figure resolution
        
    Returns
    -------
    fig : matplotlib.figure.Figure
        The created figure
        
    Example
    -------
    >>> from pathlib import Path
    >>> osm_dir = Path('data/outputs/01_aoi_delineation/City_Lagos/OSM')
    >>> fig = plot_lst_with_osm_overlay(
    ...     'Lagos_SEVIRI_day_20240101_20240131_median_WGS84_1km_clipped.tif',
    ...     'Lagos', 'day', osm_dir, 'Lagos_LST_day_with_osm.png'
    ... )
    """
    import rasterio
    from rasterio.plot import show
    import geopandas as gpd
    
    # Read LST raster
    with rasterio.open(lst_raster_path) as src:
        lst_data = src.read(1)
        lst_crs = src.crs
        extent = [src.bounds.left, src.bounds.right, src.bounds.bottom, src.bounds.top]
    
    # Mask nodata values
    lst_data = np.where(lst_data == 0, np.nan, lst_data)
    
    # Create figure
    fig, ax = plt.subplots(figsize=figsize)
    
    # Plot LST
    im = ax.imshow(lst_data, extent=extent, cmap='RdYlBu_r', alpha=0.9,
                   vmin=np.nanpercentile(lst_data, 2),
                   vmax=np.nanpercentile(lst_data, 98))
    
    # Add colorbar
    cbar = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label('LST (°C)', rotation=270, labelpad=20, fontsize=12, weight='bold')
    
    # Load and plot OSM features
    # 1. Water bodies (show outline only, already masked)
    water_file = osm_dir / f'{city_name}_water_bodies.geojson'
    if water_file.exists():
        water_gdf = gpd.read_file(water_file).to_crs(lst_crs)
        if not water_gdf.empty:
            water_gdf.boundary.plot(ax=ax, color='cyan', linewidth=1.5, alpha=0.8,
                                   label='Water Bodies (masked)', linestyle='--')
    
    # 2. Major roads
    roads_file = osm_dir / f'{city_name}_major_roads.geojson'
    if roads_file.exists():
        roads_gdf = gpd.read_file(roads_file).to_crs(lst_crs)
        if not roads_gdf.empty:
            roads_gdf.plot(ax=ax, color='white', linewidth=1.2, alpha=0.9,
                          label='Major Roads', linestyle='-')
    
    # 3. Prominent places
    places_file = osm_dir / f'{city_name}_prominent_places.geojson'
    if places_file.exists():
        places_gdf = gpd.read_file(places_file).to_crs(lst_crs)
        if not places_gdf.empty:
            places_gdf.plot(ax=ax, color='black', markersize=80, alpha=0.9,
                           label='Cities/Towns', marker='o', edgecolor='white', linewidth=0.5)
            
            # Annotate place names
            if 'name' in places_gdf.columns:
                for idx, row in places_gdf.iterrows():
                    if pd.notna(row.get('name')):
                        point = row.geometry.centroid if row.geometry.type != 'Point' else row.geometry
                        ax.annotate(row['name'], xy=(point.x, point.y),
                                   xytext=(5, 5), textcoords='offset points',
                                   fontsize=8, color='black', weight='bold',
                                   bbox=dict(boxstyle='round,pad=0.4', fc='white', alpha=0.85, edgecolor='black'),
                                   path_effects=[pe.withStroke(linewidth=2, foreground='white')])
    
    # Formatting
    period_label = 'Day' if period.lower() == 'day' else 'Night'
    ax.set_title(f'{city_name} - SEVIRI LST ({period_label})\nwith OSM Features Overlay',
                fontsize=14, weight='bold', pad=15)
    ax.set_xlabel('Longitude', fontsize=11, weight='bold')
    ax.set_ylabel('Latitude', fontsize=11, weight='bold')
    ax.legend(loc='upper right', fontsize=9, framealpha=0.9)
    ax.grid(True, alpha=0.3, linestyle='--', color='gray')
    
    plt.tight_layout()
    
    # Save figure
    if output_path:
        plt.savefig(output_path, dpi=dpi, bbox_inches='tight')
        print(f" Saved: {Path(output_path).name}")
    
    plt.show()
    
    return fig

# ====================================================================
# GEOSPATIAL FEATURES MAP (OSM + JRC Water + City Polygons)
# ====================================================================

def add_scale_bar(ax, length_km: float = None, location: str = 'lower left'):
    """
    Add a scale bar to a map axis.
    
    Parameters
    ----------
    ax : matplotlib.axes.Axes
        The axes to add the scale bar to
    length_km : float, optional
        Length of scale bar in km. If None, auto-calculated from extent.
    location : str
        Location of scale bar ('lower left', 'lower right', 'upper left', 'upper right')
    """
    from matplotlib.patches import FancyBboxPatch
    from matplotlib.lines import Line2D
    
    # Get axis extent
    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    
    # Calculate appropriate scale bar length if not specified
    extent_km = (xlim[1] - xlim[0]) * 111  # Approximate km per degree at equator
    if length_km is None:
        # Choose a nice round number for scale bar
        if extent_km > 50:
            length_km = 20
        elif extent_km > 20:
            length_km = 10
        elif extent_km > 10:
            length_km = 5
        else:
            length_km = 2
    
    # Convert km to degrees (approximate)
    length_deg = length_km / 111
    
    # Position based on location
    x_offset = 0.05
    y_offset = 0.08
    
    if 'right' in location:
        x_pos = xlim[1] - (xlim[1] - xlim[0]) * (x_offset + length_deg / (xlim[1] - xlim[0]))
    else:
        x_pos = xlim[0] + (xlim[1] - xlim[0]) * x_offset
    
    if 'upper' in location:
        y_pos = ylim[1] - (ylim[1] - ylim[0]) * y_offset
    else:
        y_pos = ylim[0] + (ylim[1] - ylim[0]) * y_offset
    
    # Draw scale bar
    ax.plot([x_pos, x_pos + length_deg], [y_pos, y_pos], 
            color='black', linewidth=3, solid_capstyle='butt', zorder=10)
    
    # Add end ticks
    tick_height = (ylim[1] - ylim[0]) * 0.01
    ax.plot([x_pos, x_pos], [y_pos - tick_height, y_pos + tick_height], 
            color='black', linewidth=2, zorder=10)
    ax.plot([x_pos + length_deg, x_pos + length_deg], [y_pos - tick_height, y_pos + tick_height], 
            color='black', linewidth=2, zorder=10)
    
    # Add label
    ax.text(x_pos + length_deg/2, y_pos + (ylim[1] - ylim[0]) * 0.02, 
            f'{length_km} km', ha='center', va='bottom', fontsize=9, 
            fontweight='bold', zorder=10,
            bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.8, edgecolor='none'))


def add_north_arrow(ax, location: str = 'upper right', size: float = 0.08):
    """
    Add a north arrow to a map axis.
    
    Parameters
    ----------
    ax : matplotlib.axes.Axes
        The axes to add the north arrow to
    location : str
        Location of north arrow ('upper left', 'upper right', 'lower left', 'lower right')
    size : float
        Size as fraction of axis height
    """
    from matplotlib.patches import FancyArrow
    
    # Get axis extent
    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    
    # Arrow dimensions
    arrow_height = (ylim[1] - ylim[0]) * size
    arrow_width = arrow_height * 0.25
    
    # Position
    x_offset = 0.05
    y_offset = 0.12
    
    if 'right' in location:
        x_pos = xlim[1] - (xlim[1] - xlim[0]) * x_offset
    else:
        x_pos = xlim[0] + (xlim[1] - xlim[0]) * x_offset
    
    if 'upper' in location:
        y_pos = ylim[1] - (ylim[1] - ylim[0]) * y_offset
    else:
        y_pos = ylim[0] + (ylim[1] - ylim[0]) * (y_offset + size)
    
    # Draw arrow
    ax.annotate('N', xy=(x_pos, y_pos), xytext=(x_pos, y_pos - arrow_height),
                arrowprops=dict(arrowstyle='-|>', color='black', lw=2),
                fontsize=12, fontweight='bold', ha='center', va='top', zorder=10)


def create_geospatial_features_map(
    city_name: str,
    aoi_gdf: gpd.GeoDataFrame,
    cr_gdf: gpd.GeoDataFrame = None,
    main_polygon_gdf: gpd.GeoDataFrame = None,
    adjacent_polygons_gdf: gpd.GeoDataFrame = None,
    landscape_gdf: gpd.GeoDataFrame = None,
    cluster25_colors: dict = None,
    water_gdf: gpd.GeoDataFrame = None,
    roads_gdf: gpd.GeoDataFrame = None,
    places_gdf: gpd.GeoDataFrame = None,
    place_types_filter: list = None,
    label_buffer_km: float = 2.0,
    figsize: tuple = (12, 12),
    save_path: str = None,
    dpi: int = 300,
) -> plt.Figure:
    """
    Three-zone study area map for a single city (NB01_v4_SMOD).

    Layer order (bottom → top)
    --------------------------
    1  City-Region (CR) fill  — very light fill
    2  Cluster25 polygons     — canonical colours, clipped to CR extent
    3  BRA fill               — gold / amber
    4  Water bodies           — steelblue
    5  UC fill                — darkorange, primary focus zone
    6  BRA outline            — dashed brown
    7  UC outline             — solid dark brown
    8  CR outline             — solid dark grey
    9  Cluster25 C{N} labels  — deferred above outlines
    10 Roads                  — thin grey, above all zone elements
    11 Place dots             — suburb/town markers
    12 Place labels           — name annotations
    Legend (zorder 50)        — pinned inside CR bounds, above all

    Legend shows only zones + water + roads + suburbs.
    Cluster25 regions are labelled on the map ('C{N}') but kept out of the legend.

    Parameters
    ----------
    city_name : str
    aoi_gdf   : GeoDataFrame — map extent / neatline (convex hull of CR)
    cr_gdf    : GeoDataFrame — City-Region polygon (water-free); plotted as light bg
    main_polygon_gdf      : GeoDataFrame — Urban Core (UC)
    adjacent_polygons_gdf : GeoDataFrame — Background Reference Area (BRA)
    landscape_gdf   : GeoDataFrame — Cluster25 landscape polygons ('Cluster25' column)
    cluster25_colors: dict — {int: hex} canonical colour palette
    water_gdf, roads_gdf, places_gdf : optional feature layers
    place_types_filter : list of OSM place types to display
    label_buffer_km : minimum spacing between place labels (km)
    figsize, save_path, dpi : standard figure params
    """
    from matplotlib.patches import Patch
    from matplotlib.lines   import Line2D

    fig, ax = plt.subplots(figsize=figsize)

    # ── Map extent ────────────────────────────────────────────────────────────
    aoi_plot  = aoi_gdf.to_crs("EPSG:4326")
    bounds    = aoi_plot.total_bounds          # [minx, miny, maxx, maxy]
    w = bounds[2] - bounds[0]
    h = bounds[3] - bounds[1]
    ax.set_xlim(bounds[0] - w * 0.02, bounds[2] + w * 0.02)
    ax.set_ylim(bounds[1] - h * 0.02, bounds[3] + h * 0.02)

    legend_handles = []
    legend_labels  = []

    # Pre-compute reprojected zone GDFs (reused for both fill and outline passes)
    cr_plot  = None
    bra_plot = None
    uc_plot  = None
    if cr_gdf is not None and not cr_gdf.empty:
        cr_plot = cr_gdf.copy()
        cr_plot["geometry"] = cr_plot.geometry.buffer(0)
        cr_plot = cr_plot.to_crs("EPSG:4326")
    if adjacent_polygons_gdf is not None and not adjacent_polygons_gdf.empty:
        bra_plot = adjacent_polygons_gdf.copy()
        bra_plot["geometry"] = bra_plot.geometry.buffer(0)
        bra_plot = bra_plot.to_crs("EPSG:4326")
    if main_polygon_gdf is not None and not main_polygon_gdf.empty:
        uc_plot = main_polygon_gdf.copy()
        uc_plot["geometry"] = uc_plot.geometry.buffer(0)
        uc_plot = uc_plot.to_crs("EPSG:4326")

    # ═══════════════════════════════════════════════════════════════════════════
    # LAYER PASS 1 — ZONE FILLS (bottom, semi-transparent background)
    # Geographic features (water, roads) are rendered ABOVE these fills so they
    # remain clearly visible.  Zone outlines are rendered in Pass 3 (top).
    # ═══════════════════════════════════════════════════════════════════════════

    # Layer 1: CR fill only (no outline — outline comes in Pass 3)
    if cr_plot is not None:
        cr_plot.plot(ax=ax, facecolor="#f0f0eb", edgecolor="none",
                     alpha=0.30, zorder=1)
        legend_handles.append(Patch(facecolor="#f0f0eb", edgecolor="#333333",
                                    linewidth=1.6, alpha=0.85))
        legend_labels.append("City-Region (CR)")

    # Layer 2: Cluster25 landscape classification (clipped to map extent)
    _cluster_labels_pending = []   # defer text until Pass 3 so labels sit on top
    if landscape_gdf is not None and cluster25_colors is not None:
        try:
            land = landscape_gdf.to_crs("EPSG:4326").copy()
            land["geometry"] = land.geometry.buffer(0)
            clip_geom = aoi_plot.geometry.unary_union
            land_clip = gpd.clip(land, clip_geom)

            if not land_clip.empty:
                land_clip["_color"] = land_clip["Cluster25"].map(cluster25_colors)
                land_clip = land_clip[land_clip["_color"].notna()]

                if not land_clip.empty:
                    land_clip.plot(ax=ax, color=land_clip["_color"],
                                   edgecolor="white", linewidth=0.15,
                                   alpha=0.50, zorder=2)

                    # Collect C{N} label positions — rendered in Pass 3
                    MIN_LABEL_AREA_DEG2 = 0.003
                    labeled_clusters = set()
                    land_clip = land_clip.copy()
                    land_clip["_area"] = land_clip.geometry.area
                    for _, row in land_clip.sort_values("_area", ascending=False).iterrows():
                        cid = int(row["Cluster25"])
                        if cid in labeled_clusters or row.geometry.area < MIN_LABEL_AREA_DEG2:
                            continue
                        centroid = row.geometry.centroid
                        if not (bounds[0] <= centroid.x <= bounds[2] and
                                bounds[1] <= centroid.y <= bounds[3]):
                            continue
                        _cluster_labels_pending.append((centroid.x, centroid.y, f"C{cid}"))
                        labeled_clusters.add(cid)
        except Exception as _e:
            print(f"  Cluster25 layer skipped: {_e}")

    # Layer 3: BRA fill only (no outline — outline comes in Pass 3)
    if bra_plot is not None:
        bra_plot.plot(ax=ax, facecolor="#f5c842", edgecolor="none",
                      alpha=0.28, zorder=3)
        legend_handles.append(Patch(facecolor="#f5c842", edgecolor="#7a5c00",
                                    linewidth=2.0, linestyle="--", alpha=0.75))
        legend_labels.append("Background Reference Area (BRA)")

    # ═══════════════════════════════════════════════════════════════════════════
    # LAYER PASS 2 — GEOGRAPHIC FEATURES (middle: water, roads, UC fill)
    # Rendered above zone fills so context features are clearly visible.
    # ═══════════════════════════════════════════════════════════════════════════

    # Layer 4: Water bodies (above BRA fill — water areas show clearly as blue)
    if water_gdf is not None and not water_gdf.empty:
        water_gdf.to_crs("EPSG:4326").plot(
            ax=ax, facecolor="#4a9eca", edgecolor="#2b6fa0",
            linewidth=0.5, alpha=0.80, zorder=4)
        legend_handles.append(Patch(facecolor="#4a9eca", edgecolor="#2b6fa0",
                                    linewidth=0.5, alpha=0.80))
        legend_labels.append(f"Water bodies ({len(water_gdf):,})")

    # Roads deferred to zorder=10 — rendered above zone fills, outlines, and cluster labels

    # Layer 6: UC fill only (above water — roads will overlay this in Pass 3)
    if uc_plot is not None:
        uc_plot.plot(ax=ax, facecolor="#e07b00", edgecolor="none",
                     alpha=0.72, zorder=6)
        legend_handles.append(Patch(facecolor="#e07b00", edgecolor="#5c3100",
                                    linewidth=2.0, alpha=0.90))
        legend_labels.append("Urban Core (UC)")

    # ═══════════════════════════════════════════════════════════════════════════
    # LAYER PASS 3 — ZONE OUTLINES + LABELS (top: always crisp, never buried)
    # ═══════════════════════════════════════════════════════════════════════════

    # Layer 7: BRA outline only (dashed, drawn above water/roads)
    if bra_plot is not None:
        bra_plot.plot(ax=ax, facecolor="none", edgecolor="#7a5c00",
                      linewidth=2.0, linestyle="--", alpha=0.92, zorder=7)

    # Layer 8: UC outline only (solid, drawn above BRA outline)
    if uc_plot is not None:
        uc_plot.plot(ax=ax, facecolor="none", edgecolor="#5c3100",
                     linewidth=2.0, linestyle="-", alpha=0.95, zorder=8)

    # Layer 9: CR outline only (solid frame, drawn last among zones)
    if cr_plot is not None:
        cr_plot.plot(ax=ax, facecolor="none", edgecolor="#333333",
                     linewidth=1.8, linestyle="-", alpha=0.88, zorder=9)

    # Layer 10: Cluster25 C{N} text labels (deferred to sit above outlines)
    for _cx, _cy, _clbl in _cluster_labels_pending:
        ax.text(_cx, _cy, _clbl,
                fontsize=6.5, ha="center", va="center",
                color="#111111", fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.15", facecolor="white",
                          alpha=0.60, edgecolor="none"),
                zorder=10)

    # Layer 10.5: Roads — above all zone fills, outlines, and cluster labels
    if roads_gdf is not None and not roads_gdf.empty:
        roads_gdf.to_crs("EPSG:4326").plot(
            ax=ax, color="#888888", linewidth=0.45, alpha=0.75, zorder=10.5)
        legend_handles.append(Line2D([0], [0], color="#888888", linewidth=1.4, alpha=0.85))
        legend_labels.append(f"Roads ({len(roads_gdf):,})")

    # Layer 11: Places / suburbs
    if places_gdf is not None and not places_gdf.empty:
        places_plot = places_gdf.to_crs("EPSG:4326")
        if place_types_filter is None:
            place_types_filter = ["suburb", "town"]
        if "place" in places_plot.columns:
            places_plot = places_plot[places_plot["place"].isin(place_types_filter)].copy()

        if not places_plot.empty:
            places_plot.plot(ax=ax, color="darkred", markersize=40, alpha=0.90,
                             marker="o", edgecolor="white", linewidth=0.8, zorder=11)
            legend_handles.append(
                Line2D([0], [0], marker="o", color="w", markerfacecolor="darkred",
                       markersize=9, markeredgecolor="white", markeredgewidth=0.8))
            legend_labels.append(f"Suburbs/Towns ({len(places_plot)})")

            name_col = "name" if "name" in places_plot.columns else None
            if name_col:
                buf_deg = (label_buffer_km / 111.0) * 0.8
                placed  = []
                for _, row in places_plot.sort_values(name_col).iterrows():
                    if pd.isna(row.get(name_col)):
                        continue
                    pt = row.geometry if row.geometry.type == "Point" else row.geometry.centroid
                    pb = pt.buffer(buf_deg)
                    if any(pb.intersects(e) for e in placed):
                        continue
                    ax.annotate(row[name_col], xy=(pt.x, pt.y),
                                xytext=(3, 3), textcoords="offset points",
                                fontsize=7.5, color="black", fontweight="bold",
                                bbox=dict(boxstyle="round,pad=0.2",
                                          facecolor="white", alpha=0.80,
                                          edgecolor="none"),
                                zorder=12)
                    placed.append(pb)

    # ── Cartographic elements ─────────────────────────────────────────────────
    add_scale_bar(ax, length_km=1, location="lower left")
    add_north_arrow(ax, location="upper right")

    # ── Title ─────────────────────────────────────────────────────────────────
    # Build area strings for subtitle
    def _area_km2(gdf):
        if gdf is None or gdf.empty:
            return "n/a"
        try:
            return f"{gdf.to_crs('ESRI:102022').geometry.buffer(0).area.sum()/1e6:.0f} km²"
        except Exception:
            return "n/a"

    uc_area  = _area_km2(main_polygon_gdf)
    bra_area = _area_km2(adjacent_polygons_gdf)
    cr_area  = _area_km2(cr_gdf if cr_gdf is not None else aoi_gdf)

    ax.set_title(
        f"{city_name} — Three-Zone Study Area\n"
        f"UC: {uc_area}  |  BRA: {bra_area}  |  CR: {cr_area}",
        fontsize=13, fontweight="bold", pad=12,
    )
    ax.set_xlabel("Longitude (°E)", fontsize=10)
    ax.set_ylabel("Latitude (°N)", fontsize=10)

    # ── Legend ────────────────────────────────────────────────────────────────
    # Pinned to the lower-right corner of the CR polygon so it never overflows
    # the CR boundary.  zorder=50 ensures it renders above all axes elements.
    if legend_handles:
        if cr_plot is not None:
            cr_b  = cr_plot.total_bounds   # [minx, miny, maxx, maxy] in degrees
            _pad  = min(w, h) * 0.015
            _lx   = cr_b[2] - _pad         # CR right edge minus small inset
            _ly   = cr_b[1] + _pad         # CR bottom edge plus small inset
            # Clamp to axes data range so the anchor point stays on-screen
            _xlim = ax.get_xlim()
            _ylim = ax.get_ylim()
            _lx   = max(_xlim[0], min(_lx, _xlim[1]))
            _ly   = max(_ylim[0], min(_ly, _ylim[1]))
            leg   = ax.legend(legend_handles, legend_labels,
                              loc="lower right",
                              bbox_to_anchor=(_lx, _ly),
                              bbox_transform=ax.transData,
                              fontsize=8.5,
                              framealpha=0.95, edgecolor="#555",
                              title="Legend", title_fontsize=9.5,
                              borderpad=0.8, labelspacing=0.55)
        else:
            leg = ax.legend(legend_handles, legend_labels,
                            loc="lower right", fontsize=8.5,
                            framealpha=0.95, edgecolor="#555",
                            title="Legend", title_fontsize=9.5,
                            borderpad=0.8, labelspacing=0.55)
        leg.set_zorder(50)

    ax.grid(True, alpha=0.2, linestyle=":", color="gray", zorder=0)
    ax.set_aspect("equal")
    ax.tick_params(axis="both", which="major", labelsize=8.5)
    plt.tight_layout()

    # ── Save ──────────────────────────────────────────────────────────────────
    if save_path:
        save_path = Path(save_path)
        fig.savefig(save_path,                    dpi=dpi, bbox_inches="tight", facecolor="white")
        fig.savefig(save_path.with_suffix(".pdf"), format="pdf", bbox_inches="tight", facecolor="white")
        print(f"   Saved: {save_path.name}  +  {save_path.stem}.pdf")

    return fig


# =============================================================================
# PUBLICATION-READY STUDY AREA MAP FUNCTIONS
# =============================================================================

def calculate_city_extents(
    aoi_dict: Dict[str, gpd.GeoDataFrame],
    buffer_fraction: float = 0.05
) -> Dict[str, Dict[str, float]]:
    """
    Calculate map extents and areas for each city AOI.
    
    Parameters
    ----------
    aoi_dict : Dict[str, gpd.GeoDataFrame]
        Dictionary mapping city names to AOI GeoDataFrames
    buffer_fraction : float, optional
        Fraction of extent to add as buffer (default: 0.05 = 5%)
    
    Returns
    -------
    Dict[str, Dict[str, float]]
        Dictionary with city extents containing:
        - xmin, xmax, ymin, ymax: Buffered bounds in degrees
        - cx, cy: Center coordinates
        - width_km, height_km: Approximate dimensions in km
        - area_sqkm: Area in square kilometers
    """
    city_extents = {}
    
    for city, gdf in aoi_dict.items():
        bounds = gdf.to_crs('EPSG:4326').total_bounds
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]
        buffer_x = width * buffer_fraction
        buffer_y = height * buffer_fraction
        
        # Calculate area using UTM projection
        aoi_utm = gdf.to_crs(gdf.estimate_utm_crs())
        area_sqkm = aoi_utm.geometry.area.sum() / 1e6
        
        city_extents[city] = {
            'xmin': bounds[0] - buffer_x,
            'xmax': bounds[2] + buffer_x,
            'ymin': bounds[1] - buffer_y,
            'ymax': bounds[3] + buffer_y,
            'cx': (bounds[0] + bounds[2]) / 2,
            'cy': (bounds[1] + bounds[3]) / 2,
            'width_km': width * 111,
            'height_km': height * 111,
            'area_sqkm': area_sqkm
        }
    
    return city_extents


def _add_publication_scale_bar(
    ax: plt.Axes,
    extent: Dict[str, float],
    fontsize: int = 5
) -> None:
    """
    Add a scale bar to a publication map panel (inside the map frame).
    
    Parameters
    ----------
    ax : plt.Axes
        Matplotlib axes to add scale bar to
    extent : Dict[str, float]
        Dictionary with xmin, xmax, ymin, ymax, cx, cy, width_km keys
    fontsize : int, optional
        Font size for scale bar label (default: 5)
    """
    map_width_km = extent['width_km']
    
    # Choose appropriate scale bar length (roughly 1/4 of map width)
    if map_width_km > 50:
        scale_km = 20
    elif map_width_km > 30:
        scale_km = 10
    else:
        scale_km = 5
    
    # Calculate scale bar length in degrees
    center_lat = extent['cy']
    km_per_deg_lon = 111 * np.cos(np.radians(center_lat))
    scale_deg = scale_km / km_per_deg_lon
    
    # Position scale bar INSIDE the map at bottom-left
    # Use data coordinates for proper positioning within map extent
    map_width = extent['xmax'] - extent['xmin']
    map_height = extent['ymax'] - extent['ymin']
    
    # Position: 5% from left edge, 8% from bottom
    scale_x = extent['xmin'] + map_width * 0.05
    scale_y = extent['ymin'] + map_height * 0.08
    bar_height = map_height * 0.015  # Height of end caps
    
    # Draw white background box for visibility
    from matplotlib.patches import FancyBboxPatch
    box_padding = map_width * 0.015
    box_x = scale_x - box_padding
    box_y = scale_y - bar_height - map_height * 0.02
    box_width = scale_deg + 2 * box_padding
    box_height = bar_height * 2 + map_height * 0.06
    
    bg_box = FancyBboxPatch(
        (box_x, box_y), box_width, box_height,
        boxstyle='round,pad=0.01', facecolor='white', edgecolor='none',
        alpha=0.85, zorder=14, transform=ax.transData
    )
    ax.add_patch(bg_box)
    
    # Draw horizontal bar
    ax.plot([scale_x, scale_x + scale_deg], [scale_y, scale_y], 
            'k-', linewidth=1.5, zorder=15)
    # End caps
    ax.plot([scale_x, scale_x], [scale_y - bar_height, scale_y + bar_height], 
            'k-', linewidth=1.5, zorder=15)
    ax.plot([scale_x + scale_deg, scale_x + scale_deg], 
            [scale_y - bar_height, scale_y + bar_height], 
            'k-', linewidth=1.5, zorder=15)
    # Label (above the bar)
    ax.text(scale_x + scale_deg/2, scale_y + bar_height * 1.8, f'{scale_km} km', 
            fontsize=fontsize, ha='center', va='bottom', zorder=15)


def _add_publication_scale_bar_nigeria(
    ax: plt.Axes,
    nigeria_bounds: tuple,
    scale_km: int = 200,
    fontsize: int = 5
) -> None:
    """
    Add a scale bar to the Nigeria overview panel (inside the map frame).
    
    Parameters
    ----------
    ax : plt.Axes
        Matplotlib axes for Nigeria map
    nigeria_bounds : tuple
        Bounds of Nigeria (xmin, ymin, xmax, ymax)
    scale_km : int, optional
        Scale bar length in km (default: 200)
    fontsize : int, optional
        Font size for label (default: 5)
    """
    nb = nigeria_bounds
    map_width = nb[2] - nb[0]
    map_height = nb[3] - nb[1]
    
    # Calculate scale bar length in degrees
    center_lat = (nb[1] + nb[3]) / 2
    km_per_deg_lon = 111 * np.cos(np.radians(center_lat))
    scale_deg = scale_km / km_per_deg_lon
    
    # Position inside map at bottom-left (5% from edges)
    scale_x = nb[0] + map_width * 0.05
    scale_y = nb[1] + map_height * 0.08
    bar_height = map_height * 0.015
    
    # Draw white background box for visibility
    from matplotlib.patches import FancyBboxPatch
    box_padding = map_width * 0.01
    box_x = scale_x - box_padding
    box_y = scale_y - bar_height - map_height * 0.015
    box_width = scale_deg + 2 * box_padding
    box_height = bar_height * 2 + map_height * 0.05
    
    bg_box = FancyBboxPatch(
        (box_x, box_y), box_width, box_height,
        boxstyle='round,pad=0.01', facecolor='white', edgecolor='none',
        alpha=0.85, zorder=14, transform=ax.transData
    )
    ax.add_patch(bg_box)
    
    # Draw horizontal bar
    ax.plot([scale_x, scale_x + scale_deg], [scale_y, scale_y], 'k-', linewidth=2, zorder=15)
    # End caps
    ax.plot([scale_x, scale_x], [scale_y - bar_height, scale_y + bar_height], 'k-', linewidth=2, zorder=15)
    ax.plot([scale_x + scale_deg, scale_x + scale_deg], [scale_y - bar_height, scale_y + bar_height], 'k-', linewidth=2, zorder=15)
    # Label
    ax.text(scale_x + scale_deg/2, scale_y + bar_height * 1.8, f'{scale_km} km', 
            fontsize=fontsize, ha='center', va='bottom', zorder=15)


def _add_publication_north_arrow(
    fig: plt.Figure,
    position: tuple = (0.90, 0.025, 0.04, 0.055)
) -> plt.Axes:
    """
    Add a compact north arrow to a publication figure.
    
    Parameters
    ----------
    fig : plt.Figure
        Matplotlib figure to add north arrow to
    position : tuple, optional
        Position as (left, bottom, width, height) in figure coordinates
    
    Returns
    -------
    plt.Axes
        The axes containing the north arrow
    """
    from matplotlib.patches import FancyArrowPatch
    
    ax_north = fig.add_axes(position)
    ax_north.set_xlim(0, 1)
    ax_north.set_ylim(0, 1)
    ax_north.axis('off')
    
    # Draw north arrow
    arrow = FancyArrowPatch((0.5, 0.1), (0.5, 0.7),
                            arrowstyle='-|>', mutation_scale=12,
                            color='black', linewidth=1.5)
    ax_north.add_patch(arrow)
    
    # Add "N" label
    ax_north.text(0.5, 0.82, 'N', fontsize=10, fontweight='bold', ha='center', va='bottom')
    
    # Base line
    ax_north.plot([0.3, 0.7], [0.1, 0.1], 'k-', linewidth=1.5)
    
    return ax_north


def create_nigeria_overview_panel(
    ax: plt.Axes,
    nigeria_gdf: gpd.GeoDataFrame,
    city_extents: Dict[str, Dict[str, float]],
    cities: list,
    panel_label: str = 'A'
) -> None:
    """
    Create the Nigeria overview panel with city markers.
    
    Parameters
    ----------
    ax : plt.Axes
        Matplotlib axes for the panel
    nigeria_gdf : gpd.GeoDataFrame
        Nigeria boundary GeoDataFrame
    city_extents : Dict[str, Dict[str, float]]
        Dictionary of city extents from calculate_city_extents()
    cities : list
        List of city names to plot
    panel_label : str, optional
        Panel label (default: 'A')
    """
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D
    import matplotlib.cm as cm
    
    nigeria = nigeria_gdf.to_crs('EPSG:4326')
    
    # Plot Nigeria boundary
    nigeria.plot(ax=ax, facecolor='#e8e8e8', edgecolor='black', linewidth=0.8)
    
    # Plot city points
    n_cities = len(cities)
    colors = cm.get_cmap('tab10')(np.linspace(0, 1, n_cities))
    
    for i, city in enumerate(cities):
        cx, cy = city_extents[city]['cx'], city_extents[city]['cy']
        ax.plot(cx, cy, 'o', color=colors[i], markersize=8, 
               markeredgecolor='black', markeredgewidth=0.7, zorder=5)
        ax.annotate(city, (cx, cy), xytext=(5, 5), textcoords='offset points',
                   fontsize=7, fontweight='bold',
                   bbox=dict(boxstyle='round,pad=0.15', fc='white', alpha=0.9, ec='none'))
    
    # Format axes
    nb = nigeria.total_bounds
    ax.set_xlim(nb[0], nb[2])
    ax.set_ylim(nb[1], nb[3])
    ax.set_title(panel_label, fontsize=11, fontweight='bold', pad=4, loc='left')
    ax.tick_params(labelsize=6)
    ax.set_xlabel('Longitude (°E)', fontsize=6)
    ax.set_ylabel('Latitude (°N)', fontsize=6)
    ax.set_aspect('equal')
    
    # Legend with hollow circle for cities
    legend_handles = [
        Patch(facecolor='#e8e8e8', edgecolor='black', linewidth=1, label='Boundary'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='none', 
               markersize=7, markeredgecolor='black', markeredgewidth=1.5, label='Cities')
    ]
    ax.legend(handles=legend_handles, loc='lower right', fontsize=6,
             frameon=True, fancybox=True, framealpha=0.9, edgecolor='gray')
    
    # Scale bar (inside map frame at bottom-left)
    _add_publication_scale_bar_nigeria(ax, nb)


def create_city_feature_panel(
    ax: plt.Axes,
    city: str,
    extent: Dict[str, float],
    geo_features: Dict[str, gpd.GeoDataFrame],
    polygon_features: Dict[str, gpd.GeoDataFrame],
    panel_label: str,
    collect_legend: bool = False
) -> tuple:
    """
    Create an individual city map panel with geospatial features.
    
    Parameters
    ----------
    ax : plt.Axes
        Matplotlib axes for the panel
    city : str
        City name
    extent : Dict[str, float]
        City extent from calculate_city_extents()
    geo_features : Dict[str, gpd.GeoDataFrame]
        Dictionary with 'water', 'roads', 'places' GeoDataFrames
    polygon_features : Dict[str, gpd.GeoDataFrame]
        Dictionary with 'main_polygon', 'adjacent_polygons' GeoDataFrames
    panel_label : str
        Panel label (e.g., 'B', 'C', 'D')
    collect_legend : bool, optional
        Whether to collect legend handles (default: False)
    
    Returns
    -------
    tuple
        (legend_handles, legend_labels) if collect_legend=True, else ([], [])
    """
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D
    
    legend_handles, legend_labels = [], []
    
    # Set extent
    ax.set_xlim(extent['xmin'], extent['xmax'])
    ax.set_ylim(extent['ymin'], extent['ymax'])
    
    # Plot roads
    if geo_features.get('roads') is not None and not geo_features['roads'].empty:
        geo_features['roads'].to_crs('EPSG:4326').plot(
            ax=ax, color='grey', linewidth=0.25, alpha=0.5, zorder=1)
        if collect_legend:
            legend_handles.append(Line2D([0], [0], color='grey', linewidth=1.5))
            legend_labels.append('Roads')
    
    # Plot water
    if geo_features.get('water') is not None and not geo_features['water'].empty:
        geo_features['water'].to_crs('EPSG:4326').plot(
            ax=ax, facecolor='steelblue', alpha=0.7, 
            edgecolor='darkblue', linewidth=0.4, zorder=2)
        if collect_legend:
            legend_handles.append(Patch(facecolor='steelblue', edgecolor='darkblue', alpha=0.7))
            legend_labels.append('Water Bodies')
    
    # Plot adjacent polygons
    if polygon_features.get('adjacent_polygons') is not None and not polygon_features['adjacent_polygons'].empty:
        polygon_features['adjacent_polygons'].to_crs('EPSG:4326').plot(
            ax=ax, facecolor='gold', alpha=0.4,
            edgecolor='black', linewidth=0.7, linestyle='--', zorder=3)
        if collect_legend:
            legend_handles.append(Patch(facecolor='gold', edgecolor='black', alpha=0.5))
            legend_labels.append('Adjacent Urban Landscape')
    
    # Plot main polygon
    if polygon_features.get('main_polygon') is not None and not polygon_features['main_polygon'].empty:
        polygon_features['main_polygon'].to_crs('EPSG:4326').plot(
            ax=ax, facecolor='darkorange', alpha=0.5,
            edgecolor='black', linewidth=0.9, zorder=4)
        if collect_legend:
            legend_handles.append(Patch(facecolor='darkorange', edgecolor='black', alpha=0.6))
            legend_labels.append('Core Urban Landscape')
    
    # City name label at center
    ax.annotate(city, (extent['cx'], extent['cy']), fontsize=10, fontweight='bold',
               ha='center', va='center', color='black', alpha=0.7,
               bbox=dict(boxstyle='round,pad=0.2', fc='white', alpha=0.6, ec='none'),
               zorder=10)
    
    # Panel formatting
    ax.set_title(panel_label, fontsize=11, fontweight='bold', pad=3, loc='left')
    ax.tick_params(labelsize=6)
    ax.set_xlabel('Lon (°E)', fontsize=6)
    ax.set_ylabel('Lat (°N)', fontsize=6)
    ax.xaxis.set_major_formatter(plt.FormatStrFormatter('%.2f'))
    ax.yaxis.set_major_formatter(plt.FormatStrFormatter('%.2f'))
    ax.set_aspect('equal', adjustable='datalim')
    
    # Scale bar (inside map frame at bottom-left)
    _add_publication_scale_bar(ax, extent)
    
    return legend_handles, legend_labels


def create_publication_study_area_map(
    aoi_dict: Dict[str, gpd.GeoDataFrame],
    geo_features: Dict[str, Dict[str, gpd.GeoDataFrame]],
    polygon_features: Dict[str, Dict[str, gpd.GeoDataFrame]],
    nigeria_path: Path,
    save_path: Path = None,
    title: str = 'Study Area Maps: Nigerian Cities with Geospatial Features',
    figsize: tuple = (11.69, 7.5),
    dpi: int = 300,
    city_order: list = None,
    grid_layout: tuple = None
) -> plt.Figure:
    """
    Create a publication-ready multi-panel study area map.
    
    Creates a figure with:
    - Panel A: Nigeria overview with city locations
    - Panels B-F+: Individual city maps with geospatial features
    - Unified legend and north arrow
    - Scale bars inside each map frame (bottom-left)
    
    Parameters
    ----------
    aoi_dict : Dict[str, gpd.GeoDataFrame]
        Dictionary mapping city names to AOI GeoDataFrames
    geo_features : Dict[str, Dict[str, gpd.GeoDataFrame]]
        Nested dict: {city: {'water': gdf, 'roads': gdf, 'places': gdf}}
    polygon_features : Dict[str, Dict[str, gpd.GeoDataFrame]]
        Nested dict: {city: {'main_polygon': gdf, 'adjacent_polygons': gdf}}
    nigeria_path : Path
        Path to Nigeria boundary GeoJSON file
    save_path : Path, optional
        Base path to save figure (will save .svg)
    title : str, optional
        Figure title
    figsize : tuple, optional
        Figure size in inches (default: A4 landscape 11.69" x 7.5")
    dpi : int, optional
        DPI for PNG output (default: 300)
    city_order : list, optional
        Custom order for cities (e.g., ['Jos', 'Kano', 'Lagos', 'Port Harcourt', 'Abuja']).
        If None, cities are sorted alphabetically.
    grid_layout : tuple, optional
        Custom grid layout as (n_rows, n_cols). If None, calculated automatically.
    
    Returns
    -------
    plt.Figure
        The matplotlib figure object
    
    Examples
    --------
    >>> fig = create_publication_study_area_map(
    ...     aoi_dict=aoi_dict,
    ...     geo_features=geo_features,
    ...     polygon_features=polygon_features,
    ...     nigeria_path=project_root / 'data/inputs/geospatial_features/boundary_Nigeria.geojson',
    ...     save_path=output_dir / 'Study_Area_Map_Publication',
    ...     city_order=['Jos', 'Kano', 'Lagos', 'Port Harcourt', 'Abuja'],
    ...     grid_layout=(2, 3)
    ... )
    """
    import math
    import string
    
    # Use custom city order or default to sorted
    if city_order is not None:
        cities = [c for c in city_order if c in aoi_dict]
    else:
        cities = sorted(aoi_dict.keys())
    n_cities = len(cities)
    n_total = n_cities + 1  # +1 for Nigeria
    
    # Use custom grid layout or calculate automatically
    if grid_layout is not None:
        n_rows, n_cols = grid_layout
    else:
        n_cols = math.ceil(math.sqrt(n_total))
        n_rows = math.ceil(n_total / n_cols)
    
    print(f"Layout: 1 Nigeria + {n_cities} cities = {n_total} panels in {n_rows}x{n_cols} grid")
    print(f"City order: {', '.join(cities)}")
    print(f"Figure: {figsize[0]}\" x {figsize[1]}\"")
    
    # Calculate city extents
    print("\nCalculating city extents...")
    city_extents = calculate_city_extents(aoi_dict)
    for city, ext in city_extents.items():
        print(f"  {city}: {ext['area_sqkm']:.1f} km²")
    
    # Create figure
    fig = plt.figure(figsize=figsize)
    gs = fig.add_gridspec(n_rows, n_cols, 
                          left=0.05, right=0.95, top=0.90, bottom=0.12,
                          hspace=0.30, wspace=0.15)  # Increased hspace for external scale bars
    
    # Generate enough panel labels: A-Z, then AA, AB, ...
    panel_labels = list(string.ascii_uppercase)
    if n_total > 26:
        for first in string.ascii_uppercase:
            for second in string.ascii_uppercase:
                panel_labels.append(first + second)
                if len(panel_labels) >= n_total:
                    break
            if len(panel_labels) >= n_total:
                break
    
    # Panel A: Nigeria overview
    print("\nCreating Nigeria panel (A)...")
    ax_nigeria = fig.add_subplot(gs[0, 0])
    nigeria_gdf = gpd.read_file(nigeria_path)
    create_nigeria_overview_panel(ax_nigeria, nigeria_gdf, city_extents, cities, 'A')
    
    # City panels
    print("Creating city maps...")
    legend_handles, legend_labels = [], []
    
    for idx, city in enumerate(cities):
        panel_idx = idx + 1
        row = panel_idx // n_cols
        col = panel_idx % n_cols
        
        ax = fig.add_subplot(gs[row, col])
        panel_letter = panel_labels[panel_idx]
        
        # Collect legend only from first city
        collect_legend = (idx == 0)
        
        handles, labels = create_city_feature_panel(
            ax=ax,
            city=city,
            extent=city_extents[city],
            geo_features=geo_features[city],
            polygon_features=polygon_features[city],
            panel_label=panel_letter,
            collect_legend=collect_legend
        )
        
        if collect_legend:
            legend_handles = handles
            legend_labels = labels
        
        print(f"  {panel_letter}: {city} ({city_extents[city]['area_sqkm']:.1f} km²)")
    
    # Hide empty subplots
    for idx in range(n_total, n_rows * n_cols):
        row = idx // n_cols
        col = idx % n_cols
        fig.add_subplot(gs[row, col]).set_visible(False)
    
    # Title
    fig.suptitle(title, fontsize=12, fontweight='bold', y=0.96)
    
    # Legend (centered at bottom)
    if legend_handles:
        fig.legend(legend_handles, legend_labels, loc='lower center', 
                  bbox_to_anchor=(0.42, 0.02),
                  ncol=len(legend_handles), fontsize=8, frameon=True, fancybox=True,
                  edgecolor='gray', framealpha=0.95, 
                  title='City Map Features', title_fontsize=8)
    
    # North arrow
    _add_publication_north_arrow(fig)
    print("\n Added compact North Arrow")
    
    # Save
    if save_path:
        save_path = Path(save_path)
        png_path = save_path.with_suffix('.png')
        pdf_path = save_path.with_suffix('.pdf')
        
        fig.savefig(png_path, dpi=dpi, bbox_inches='tight', facecolor='white')
        fig.savefig(pdf_path, format='pdf', bbox_inches='tight', facecolor='white')
        
        print(f"\n Panel labels: A (Nigeria), B-{panel_labels[n_cities]} (Cities)")
        print(" Scale bars inside all map frames (bottom-left)")
        print(" Hollow circle in Nigeria legend")
        print(" Compact North Arrow")
        print(f" Saved: {png_path.name}, {pdf_path.name}")
    
    return fig


# 
# Nigeria Cities + Landscape Map (Cluster25 background + proportional pop)
# 


def create_nigeria_cities_landscape_map(
    aoi_dict: Dict[str, gpd.GeoDataFrame],
    cities_csv_path: Path,
    landscape_path: Path,
    nigeria_path: Path,
    cluster25_colors: Dict[int, str],
    study_year: int = 2024,
    save_path: Path = None,
    title: str = 'Study Cities on Landscape Classification — Nigeria',
    figsize: tuple = (10, 10),
    dpi: int = 300,
    pop_scale: float = 0.6,
    show_plot: bool = True,
    pop_override: Dict[str, float] = None,
) -> plt.Figure:
    """
    Create a Nigeria map displaying:
      1. National boundary
      2. Cluster25 landscape classification (filled polygons)
      3. Proportional circles sized by city population at the study year
      4. Black point markers at city locations
      5. City name labels

    Parameters
    ----------
    aoi_dict : dict
        City name → AOI GeoDataFrame (used for centroid positions).
    cities_csv_path : Path
        Path to the UN population CSV ('Urban Agglomeration', 'Latitude',
        'Longitude', and year columns with population in thousands).
    landscape_path : Path
        Path to landscape GeoJSON with a 'Cluster25' column.
    nigeria_path : Path
        Path to Nigeria boundary GeoJSON.
    cluster25_colors : dict
        Mapping of Cluster25 integer class → hex colour string.
    study_year : int
        Year column to use for population (default 2024).
    save_path : Path, optional
        Base path (without extension). .svg will be saved.
    title : str
        Figure title.
    figsize : tuple
        Figure size in inches.
    dpi : int
        DPI for PNG output.
    pop_scale : float
        Visual scaling factor for proportional circles (degrees).
    show_plot : bool
        Whether to call plt.show().

    Returns
    -------
    matplotlib.figure.Figure
    """
    import matplotlib.patches as mpatches

    # ------------------------------------------------------------------
    # Load data
    # ------------------------------------------------------------------
    nigeria_gdf = gpd.read_file(nigeria_path).to_crs('EPSG:4326')
    landscape_gdf = gpd.read_file(landscape_path).to_crs('EPSG:4326')

    # Support both CSV and XLSX formats
    cities_csv_path_p = Path(cities_csv_path)
    if cities_csv_path_p.suffix.lower() in ('.xlsx', '.xls'):
        cities_df = pd.read_excel(cities_csv_path, sheet_name='Data')
    else:
        cities_df = pd.read_csv(cities_csv_path, thousands=',')

    # Rename WUP 2025 columns to legacy schema if present
    if 'City_Name' in cities_df.columns:
        cities_df = cities_df.rename(columns={
            'City_Name': 'Urban Agglomeration',
            'PWCent_Latitude': 'Latitude',
            'PWCent_Longitude': 'Longitude',
        })
        cities_df['Urban Agglomeration'] = cities_df['Urban Agglomeration'].str.strip()

    # Build population lookup (values in thousands → actual)
    year_col = str(study_year)
    pop_lookup = {}
    coord_lookup = {}
    for _, row in cities_df.iterrows():
        name = row['Urban Agglomeration']
        if pd.notna(name) and year_col in cities_df.columns:
            pop_val = row[year_col]
            pop_lookup[name] = float(pop_val) * 1_000 if pd.notna(pop_val) else 0
            coord_lookup[name] = (float(row['Longitude']), float(row['Latitude']))

    # Apply rolled-up population override (e.g. absorbed city pop added to parent)
    if pop_override:
        for city, pop_val in pop_override.items():
            pop_lookup[city] = pop_val

    # Restrict to cities in aoi_dict
    cities = sorted(aoi_dict.keys())

    # ------------------------------------------------------------------
    # Prepare landscape base layer
    # ------------------------------------------------------------------
    landscape_merged = landscape_gdf.dissolve(by='Cluster25', as_index=False)
    landscape_merged['color'] = landscape_merged['Cluster25'].map(cluster25_colors)

    # ------------------------------------------------------------------
    # Create figure
    # ------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=figsize)

    # Layer 1 — Cluster25 landscape
    landscape_merged.plot(
        ax=ax, color=landscape_merged['color'],
        edgecolor='white', linewidth=0.2, alpha=0.6, zorder=1,
    )

    # Layer 2 — Nigeria boundary
    nigeria_gdf.plot(
        ax=ax, facecolor='none', edgecolor='#333333',
        linewidth=1.5, zorder=2,
    )

    # ------------------------------------------------------------------
    # Proportional circles + city points + labels
    # ------------------------------------------------------------------
    max_pop = max((pop_lookup.get(c, 0) for c in cities), default=1) or 1

    label_texts, label_x, label_y = [], [], []

    def _fmt_pop(p):
        if p >= 1_000_000:
            return f'{p / 1_000_000:.1f} M'
        if p >= 1_000:
            return f'{p / 1_000:.0f}k'
        return f'{p:.0f}'

    for city in cities:
        lon, lat = coord_lookup.get(city, (None, None))
        if lon is None:
            continue

        pop = pop_lookup.get(city, 0)
        radius = pop_scale * np.sqrt(pop / max_pop) if pop > 0 else 0

        # Layer 3 — proportional population circle
        if radius > 0:
            circle = plt.Circle(
                (lon, lat), radius,
                facecolor='#555555', edgecolor='white',
                linewidth=0.8, alpha=0.75, zorder=4,
            )
            ax.add_patch(circle)

        # Layer 4 — black city point
        ax.plot(lon, lat, 'ko', markersize=3, zorder=6)

        # Layer 5 — city name label
        label = f'{city}\n({_fmt_pop(pop)})'
        txt = ax.text(
            lon, lat - radius - 0.12, label,
            ha='center', va='top', fontsize=6.5,
            fontweight='bold', color='#000',
            zorder=7, linespacing=0.85,
        )
        label_texts.append(txt)
        label_x.append(lon)
        label_y.append(lat - radius - 0.12)

    # De-clutter labels
    try:
        from adjustText import adjust_text
        adjust_text(
            label_texts, x=label_x, y=label_y, ax=ax,
            force_text=(0.4, 0.6), force_points=(0.3, 0.5),
            expand_text=(1.1, 1.2), expand_points=(1.1, 1.2),
            arrowprops=dict(arrowstyle='-', color='#888', lw=0.5,
                            shrinkA=10, shrinkB=5),
            ensure_inside_axes=True, max_move=2.0,
        )
    except ImportError:
        pass

    # ------------------------------------------------------------------
    # Title, legend, axes
    # ------------------------------------------------------------------
    ax.set_title(title, fontsize=13, fontweight='bold', pad=14)

    legend_elements = [
        plt.Line2D([0], [0], marker='o', color='w',
                   markerfacecolor='#555555', markeredgecolor='white',
                   markersize=12, alpha=0.75, label='Population (proportional)'),
        plt.Line2D([0], [0], marker='o', color='w',
                   markerfacecolor='black', markersize=5, label='City location'),
        mpatches.Patch(facecolor='none', edgecolor='#333',
                       linewidth=1.5, label='National boundary'),
    ]
    ax.legend(
        handles=legend_elements, loc='lower right', fontsize=8,
        framealpha=0.95, edgecolor='#999',
        title='Legend', title_fontsize=9,
    )

    ax.set_xlabel('Longitude', fontsize=10)
    ax.set_ylabel('Latitude', fontsize=10)
    ax.grid(True, alpha=0.15, linestyle='--', linewidth=0.5, zorder=0)
    ax.set_aspect('equal')

    bounds = nigeria_gdf.total_bounds
    ax.set_xlim(bounds[0] - 0.5, bounds[2] + 0.5)
    ax.set_ylim(bounds[1] - 1.0, bounds[3] + 0.5)

    # Scale bar (100 km  0.9° at ~9°N)
    sc_cx = (bounds[0] + bounds[2]) / 2
    sc_lat = bounds[1] - 0.7
    ax.plot([sc_cx - 0.45, sc_cx + 0.45], [sc_lat, sc_lat],
            'k-', linewidth=3, zorder=8)
    ax.plot([sc_cx - 0.45, sc_cx - 0.45],
            [sc_lat - 0.1, sc_lat + 0.1], 'k-', linewidth=2, zorder=8)
    ax.plot([sc_cx + 0.45, sc_cx + 0.45],
            [sc_lat - 0.1, sc_lat + 0.1], 'k-', linewidth=2, zorder=8)
    ax.text(sc_cx, sc_lat + 0.15, '100 km',
            ha='center', va='bottom', fontsize=8, fontweight='bold', zorder=8)

    # North arrow
    arrow_props = dict(arrowstyle='->', lw=2, color='black')
    ax.annotate('N', xy=(0.96, 0.96), xytext=(0.96, 0.91),
                xycoords='axes fraction', fontsize=12, ha='center',
                fontweight='bold', arrowprops=arrow_props, zorder=10)

    fig.tight_layout()

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------
    if save_path:
        save_path = Path(save_path)
        png_p = save_path.with_suffix('.png')
        pdf_p = save_path.with_suffix('.pdf')
        fig.savefig(png_p, dpi=dpi, bbox_inches='tight', facecolor='white')
        fig.savefig(pdf_p, format='pdf', bbox_inches='tight', facecolor='white')
        print(f"   Saved: {png_p.name}, {pdf_p.name}")

    if show_plot:
        plt.show()
    else:
        plt.close(fig)

    return fig


def create_cluster25_classification_table(
    landscape_path: Path,
    cluster25_colors: Dict[int, str],
    save_path: Path = None,
    title: str = 'Cluster25 Landscape Classification',
    figsize: tuple = (14, 8),
    dpi: int = 300,
    show_plot: bool = True,
) -> plt.Figure:
    """
    Plot a publication-ready table of the 25 landscape clusters with
    colour swatches, climate, geology, and elevation class columns.

    Parameters
    ----------
    landscape_path : Path
        Path to landscape GeoJSON with Cluster25, Climate_Class,
        Geology_Class, and Elevation_Class columns.
    cluster25_colors : dict
        Mapping of Cluster25 integer class → hex colour string.
    save_path : Path, optional
        Base path (without extension). .svg will be saved.
    title : str
        Table title.
    figsize : tuple
        Figure size in inches.
    dpi : int
        DPI for PNG output.
    show_plot : bool
        Whether to call plt.show().

    Returns
    -------
    matplotlib.figure.Figure
    """
    import matplotlib.patches as mpatches

    landscape_gdf = gpd.read_file(landscape_path)

    # Build unique cluster table, sorted by Cluster25
    cluster_table = (
        landscape_gdf
        .groupby('Cluster25')
        .agg(
            Climate_Class=('Climate_Class', 'first'),
            Geology_Class=('Geology_Class', 'first'),
            Elevation_Class=('Elevation_Class', 'first'),
        )
        .reset_index()
        .sort_values('Cluster25')
    )

    n_rows = len(cluster_table)

    #  Build cell text (S/No, Colour swatch, Cluster, Climate, Geology, Elevation) 
    col_labels = ['S/No', ' ', 'Cluster', 'Climate Class', 'Geology Class',
                  'Elevation Class']
    cell_text = []
    row_colors_hex = []
    for sno, (_, r) in enumerate(cluster_table.iterrows(), 1):
        c25 = int(r['Cluster25'])
        hex_c = cluster25_colors.get(c25, '#CCCCCC')
        cell_text.append([
            str(sno),
            '',           # colour swatch — filled via cell facecolor
            f'CL-{c25}',
            r['Climate_Class'],
            r['Geology_Class'],
            r['Elevation_Class'],
        ])
        row_colors_hex.append(hex_c)

    #  Create figure 
    fig, ax = plt.subplots(figsize=figsize)
    ax.axis('off')
    ax.set_title(title, fontsize=14, fontweight='bold', pad=18)

    table = ax.table(
        cellText=cell_text,
        colLabels=col_labels,
        loc='center',
        cellLoc='center',
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1.0, 1.45)  # row height expansion

    #  Style header row 
    for j in range(len(col_labels)):
        cell = table[0, j]
        cell.set_facecolor('#2c3e50')
        cell.set_text_props(color='white', fontweight='bold', fontsize=10)
        cell.set_edgecolor('white')
        cell.set_linewidth(1.5)

    #  Style data rows 
    # Columns that should be left-aligned (Climate, Geology, Elevation)
    left_align_cols = {3, 4, 5}
    colour_swatch_col = 1  # column index for colour swatch
    for i in range(1, n_rows + 1):
        hex_c = row_colors_hex[i - 1]
        for j in range(len(col_labels)):
            cell = table[i, j]
            cell.set_edgecolor('#ddd')
            cell.set_linewidth(0.8)
            # Alternate row background for readability
            if j == colour_swatch_col:
                # Fill swatch cell with cluster colour
                cell.set_facecolor(hex_c)
                cell.set_edgecolor('#999')
            elif i % 2 == 0:
                cell.set_facecolor('#f9f9f9')
            else:
                cell.set_facecolor('white')
            # Left-align text columns
            if j in left_align_cols:
                cell.get_text().set_ha('left')
                cell.PAD = 0.05

    # Left-align header cells for text columns too
    for j in left_align_cols:
        table[0, j].get_text().set_ha('left')
        table[0, j].PAD = 0.05

    #  Adjust column widths 
    col_widths = [0.06, 0.04, 0.08, 0.30, 0.28, 0.24]
    for j, w in enumerate(col_widths):
        for i in range(n_rows + 1):
            table[i, j].set_width(w)

    fig.tight_layout()

    #  Save 
    if save_path:
        save_path = Path(save_path)
        png_p = save_path.with_suffix('.png')
        pdf_p = save_path.with_suffix('.pdf')
        fig.savefig(png_p, dpi=dpi, bbox_inches='tight', facecolor='white')
        fig.savefig(pdf_p, format='pdf', bbox_inches='tight', facecolor='white')
        print(f"   Saved: {png_p.name}, {pdf_p.name}")

    if show_plot:
        plt.show()
    else:
        plt.close(fig)

    return fig


def create_nigeria_overview_map(
    aoi_dict: Dict[str, gpd.GeoDataFrame],
    nigeria_path: Path,
    save_path: Path = None,
    title: str = 'Study Cities: Nigeria',
    figsize: tuple = (11.69, 7.5),
    dpi: int = 300
) -> plt.Figure:
    """
    Create a standalone Nigeria overview map showing all selected city locations.
    
    Used in non-TEST modes where cities are visualized individually.
    The same figure dimensions as the publication map are used.
    
    Parameters
    ----------
    aoi_dict : Dict[str, gpd.GeoDataFrame]
        Dictionary mapping city names to AOI GeoDataFrames
    nigeria_path : Path
        Path to Nigeria boundary GeoJSON file
    save_path : Path, optional
        Base path to save figure (will save .svg)
    title : str, optional
        Figure title
    figsize : tuple, optional
        Figure size in inches
    dpi : int, optional
        DPI for PNG output
    
    Returns
    -------
    plt.Figure
    """
    city_extents = calculate_city_extents(aoi_dict)
    cities = sorted(aoi_dict.keys())
    
    fig, ax = plt.subplots(1, 1, figsize=figsize)
    
    nigeria_gdf = gpd.read_file(nigeria_path)
    create_nigeria_overview_panel(ax, nigeria_gdf, city_extents, cities, panel_label='')
    ax.set_title(title, fontsize=12, fontweight='bold', pad=10)
    
    _add_publication_north_arrow(fig)
    
    fig.tight_layout(rect=[0, 0, 0.95, 0.95])
    
    if save_path:
        save_path = Path(save_path)
        png_path = save_path.with_suffix('.png')
        pdf_path = save_path.with_suffix('.pdf')
        fig.savefig(png_path, dpi=dpi, bbox_inches='tight', facecolor='white')
        fig.savefig(pdf_path, format='pdf', bbox_inches='tight', facecolor='white')
        print(f"   Saved: {png_path.name}, {pdf_path.name}")
    
    return fig


def create_individual_city_study_area_map(
    city: str,
    aoi_dict: Dict[str, gpd.GeoDataFrame],
    geo_features: Dict[str, Dict[str, gpd.GeoDataFrame]],
    polygon_features: Dict[str, Dict[str, gpd.GeoDataFrame]],
    nigeria_path: Path,
    save_path: Path = None,
    figsize: tuple = (11.69, 7.5),
    dpi: int = 300
) -> plt.Figure:
    """
    Create a study area map for a single city with Nigeria inset.
    
    Layout: Left panel = Nigeria overview (showing this city highlighted),
    Right panel = City detail with all geospatial features.
    Uses the same figure dimensions and styling as the combined publication map.
    
    Parameters
    ----------
    city : str
        City name
    aoi_dict : Dict[str, gpd.GeoDataFrame]
        Full dictionary of all city AOIs (for Nigeria overview context)
    geo_features : Dict[str, Dict[str, gpd.GeoDataFrame]]
        Nested dict with features for all cities
    polygon_features : Dict[str, Dict[str, gpd.GeoDataFrame]]
        Nested dict with polygon features for all cities
    nigeria_path : Path
        Path to Nigeria boundary GeoJSON
    save_path : Path, optional
        Base path to save (will save .svg)
    figsize : tuple, optional
        Figure size in inches (default: A4 landscape)
    dpi : int, optional
        DPI for PNG output
    
    Returns
    -------
    plt.Figure
    """
    import matplotlib.cm as cm
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D
    
    # Calculate extents for all cities (for Nigeria overview)
    city_extents = calculate_city_extents(aoi_dict)
    all_cities = sorted(aoi_dict.keys())
    
    fig = plt.figure(figsize=figsize)
    gs = fig.add_gridspec(1, 2, left=0.05, right=0.95, top=0.90, bottom=0.12,
                          wspace=0.15, width_ratios=[0.4, 0.6])
    
    # Left panel: Nigeria overview with this city highlighted
    ax_nigeria = fig.add_subplot(gs[0])
    nigeria_gdf = gpd.read_file(nigeria_path).to_crs('EPSG:4326')
    
    # Plot Nigeria boundary
    nigeria_gdf.plot(ax=ax_nigeria, facecolor='#e8e8e8', edgecolor='black', linewidth=0.8)
    
    # Plot all cities as grey, highlight current city in red
    n_cities = len(all_cities)
    for i, c in enumerate(all_cities):
        cx, cy = city_extents[c]['cx'], city_extents[c]['cy']
        if c == city:
            ax_nigeria.plot(cx, cy, 'o', color='red', markersize=10,
                           markeredgecolor='black', markeredgewidth=0.8, zorder=6)
            ax_nigeria.annotate(c, (cx, cy), xytext=(5, 5), textcoords='offset points',
                               fontsize=8, fontweight='bold', color='red',
                               bbox=dict(boxstyle='round,pad=0.15', fc='white', alpha=0.9, ec='none'))
        else:
            ax_nigeria.plot(cx, cy, 'o', color='grey', markersize=5,
                           markeredgecolor='black', markeredgewidth=0.5, zorder=4, alpha=0.6)
            ax_nigeria.annotate(c, (cx, cy), xytext=(3, 3), textcoords='offset points',
                               fontsize=6, color='grey',
                               bbox=dict(boxstyle='round,pad=0.1', fc='white', alpha=0.7, ec='none'))
    
    nb = nigeria_gdf.total_bounds
    ax_nigeria.set_xlim(nb[0], nb[2])
    ax_nigeria.set_ylim(nb[1], nb[3])
    ax_nigeria.set_title('A', fontsize=11, fontweight='bold', pad=4, loc='left')
    ax_nigeria.tick_params(labelsize=6)
    ax_nigeria.set_xlabel('Longitude (°E)', fontsize=6)
    ax_nigeria.set_ylabel('Latitude (°N)', fontsize=6)
    ax_nigeria.set_aspect('equal')
    
    legend_handles_ng = [
        Patch(facecolor='#e8e8e8', edgecolor='black', linewidth=1, label='Boundary'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='red',
               markersize=7, markeredgecolor='black', markeredgewidth=1, label=f'{city} (current)'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='grey',
               markersize=5, markeredgecolor='black', markeredgewidth=0.5, label='Other cities')
    ]
    ax_nigeria.legend(handles=legend_handles_ng, loc='lower right', fontsize=6,
                     frameon=True, fancybox=True, framealpha=0.9, edgecolor='gray')
    _add_publication_scale_bar_nigeria(ax_nigeria, nb)
    
    # Right panel: City detail
    ax_city = fig.add_subplot(gs[1])
    handles, labels = create_city_feature_panel(
        ax=ax_city,
        city=city,
        extent=city_extents[city],
        geo_features=geo_features[city],
        polygon_features=polygon_features[city],
        panel_label='B',
        collect_legend=True
    )
    
    # Title
    fig.suptitle(f'Study Area Map: {city}', fontsize=12, fontweight='bold', y=0.96)
    
    # Legend
    if handles:
        fig.legend(handles, labels, loc='lower center',
                  bbox_to_anchor=(0.55, 0.02),
                  ncol=len(handles), fontsize=8, frameon=True, fancybox=True,
                  edgecolor='gray', framealpha=0.95,
                  title='City Map Features', title_fontsize=8)
    
    # North arrow
    _add_publication_north_arrow(fig)
    
    # Save
    if save_path:
        save_path = Path(save_path)
        png_path = save_path.with_suffix('.png')
        pdf_path = save_path.with_suffix('.pdf')
        fig.savefig(png_path, dpi=dpi, bbox_inches='tight', facecolor='white')
        fig.savefig(pdf_path, format='pdf', bbox_inches='tight', facecolor='white')
        print(f"   Saved: {png_path.name}, {pdf_path.name}")
    
    return fig


# =============================================================================
# STAKEHOLDER ANALYSIS VISUALIZATIONS (Notebook 02)
# =============================================================================

def create_stakeholder_map_with_bar_chart(cities_gdf, boundary_gdf, workshop_prof,
                                          profession_colors, survey_df, workshop_total,
                                          global_registered=None, global_attendees=None,
                                          cluster_workshop_prof=None,
                                          figsize=(11.7, 5.85),
                                          registered_by=None, bar_labels=None,
                                          panel_letters=('A', 'B'), bar_legend_title=None):
    """
    Create stakeholder distribution map with component bar chart and nested donut.
    Designed to fit upper half of A4 page (11.7" x 5.85")
    
    Parameters:
    -----------
    cities_gdf : GeoDataFrame
        Cities with population and stakeholder data
    boundary_gdf : GeoDataFrame
        Nigeria boundary
    workshop_prof : DataFrame
        Workshop attendance by city and profession
    profession_colors : dict
        Color mapping for professions
    survey_df : DataFrame
        Complete survey data (for donut chart calculations)
    workshop_total : DataFrame
        Workshop totals by city (for donut chart calculations)
    global_registered : int, optional
        Total unique registered stakeholders (if None, sum from cities_gdf)
    global_attendees : int, optional
        Total unique workshop attendees (if None, sum from cities_gdf)
    figsize : tuple
        Figure size (width, height) in inches
    registered_by : dict, optional
        Registrations per bar (city name, or Cluster25 id in the cluster panel); when
        given, each bar ends "attended/registered" instead of "attended"
    bar_labels : dict, optional
        Axis label per bar (city name, or Cluster25 id in the cluster panel); default
        'Cluster {id}' for clusters and the city name for cities
    panel_letters : tuple
        Letters of the map and bar panels
    bar_legend_title : str, optional
        Title of the profession legend (default: 'Profession' for clusters,
        'Profession/Discipline (Mix)' for cities)

    Returns:
    --------
    fig : matplotlib.figure.Figure

    Example:
    --------
    >>> fig = create_stakeholder_map_with_bar_chart(
    ...     cities_gdf, boundary_gdf, workshop_prof, 
    ...     profession_colors, survey_df, workshop_total,
    ...     global_registered=332, global_attendees=115
    ... )
    >>> fig.savefig('stakeholder_map.png', dpi=300)
    """
    from matplotlib.patches import Wedge
    from matplotlib.lines import Line2D as Line2D_patch
    import matplotlib.patches as mpatches
    
    # Create figure with two subplots: map (60%) and bar chart (40%)
    fig = plt.figure(figsize=figsize)
    gs = GridSpec(1, 2, figure=fig, width_ratios=[0.6, 0.4], wspace=0.25)
    
    ax_map = fig.add_subplot(gs[0])
    ax_bar = fig.add_subplot(gs[1])
    
    # =========================================================================
    # LEFT PANEL: MAP
    # =========================================================================
    
    # 1. Plot Nigeria boundary
    boundary_gdf.plot(ax=ax_map, facecolor='white', edgecolor='black', linewidth=1.2)
    
    # Calculate scaling factors
    max_pop = cities_gdf['population_2024'].max()
    max_registered = cities_gdf['registered_count'].max()
    
    # Scale factors for proportional circles
    pop_scale = 4000
    reg_scale = 2000
    
    # 2. Plot population circles (light grey, semi-transparent)
    for idx, row in cities_gdf.iterrows():
        if row['population_2024'] > 0:
            size = (row['population_2024'] / max_pop) * pop_scale
            ax_map.scatter(row.geometry.x, row.geometry.y, 
                          s=size, color='lightgrey', alpha=0.4, 
                          edgecolors='grey', linewidth=0.5, zorder=2)
    
    # 3. Plot registered stakeholders as pie charts (Workshop Status)
    color_attended = 'black'
    color_absent = '#999999'
    
    for idx, row in cities_gdf.iterrows():
        if row['registered_count'] > 0:
            radius = np.sqrt((row['registered_count'] / max_registered) * reg_scale) / 111.32 / 0.9
            
            attended = row['total_attendees']
            not_attended = row['registered_count'] - attended
            
            x, y = row.geometry.x, row.geometry.y
            
            if attended > 0 and not_attended > 0:
                angle_attended = (attended / row['registered_count']) * 360
                
                wedge1 = Wedge((x, y), radius, 0, angle_attended, 
                             facecolor=color_attended, edgecolor='black', linewidth=1, zorder=3)
                ax_map.add_patch(wedge1)
                
                wedge2 = Wedge((x, y), radius, angle_attended, 360, 
                             facecolor=color_absent, edgecolor='black', linewidth=1, zorder=3)
                ax_map.add_patch(wedge2)
            elif attended > 0:
                circle = plt.Circle((x, y), radius, color=color_attended, 
                                   edgecolor='black', linewidth=1, zorder=3)
                ax_map.add_patch(circle)
            else:
                circle = plt.Circle((x, y), radius, color=color_absent, 
                                   edgecolor='black', linewidth=1, zorder=3)
                ax_map.add_patch(circle)
    
    # 4. Add city labels with red dots and smart positioning
    try:
        from adjustText import adjust_text
        texts = []
        dot_size = 4
        
        for idx, row in cities_gdf.iterrows():
            ax_map.scatter(row.geometry.x, row.geometry.y, 
                          s=dot_size, color='red', marker='o', 
                          edgecolors='white', linewidth=0.3, zorder=6)
            
            txt = ax_map.text(row.geometry.x, row.geometry.y, row['city'],
                             fontsize=6, ha='left', va='bottom',
                             color='black', zorder=7,
                             bbox=dict(boxstyle='round,pad=0.05',
                                      facecolor='white', edgecolor='none', 
                                      alpha=0.85))
            texts.append(txt)
        
        adjust_text(texts, ax=ax_map, 
                   arrowprops=dict(arrowstyle='-', color='gray', lw=0.3, alpha=0.5),
                   expand_text=(1.05, 1.2), expand_points=(1.1, 1.2),
                   force_text=(0.2, 0.3), force_points=(0.1, 0.2))
    except:
        pass
    
    # 5. Add map elements (North arrow, scale bar)
    ax_map.annotate('N', xy=(0.95, 0.95), xycoords='axes fraction',
                   fontsize=12, fontweight='bold', ha='center', va='center',
                   bbox=dict(boxstyle='circle', facecolor='white', 
                            edgecolor='black', linewidth=1))
    ax_map.annotate('', xy=(0.95, 0.93), xytext=(0.95, 0.89), xycoords='axes fraction',
                   arrowprops=dict(arrowstyle='->', lw=1.5, color='black'))
    
    # Scale bar
    scale_x_start = 0.05
    scale_y = 0.05
    scale_width = 0.15
    
    line = Line2D_patch([scale_x_start, scale_x_start + scale_width], 
                       [scale_y, scale_y],
                       transform=ax_map.transAxes, color='black', linewidth=2)
    ax_map.add_line(line)
    
    tick_height = 0.01
    for x_pos in [scale_x_start, scale_x_start + scale_width]:
        tick = Line2D_patch([x_pos, x_pos], [scale_y - tick_height, scale_y + tick_height],
                          transform=ax_map.transAxes, color='black', linewidth=1.5)
        ax_map.add_line(tick)
    
    ax_map.text(scale_x_start, scale_y - 0.02, '0', 
               transform=ax_map.transAxes, fontsize=6, ha='center', va='top')
    ax_map.text(scale_x_start + scale_width/2, scale_y - 0.02, '250', 
               transform=ax_map.transAxes, fontsize=6, ha='center', va='top')
    ax_map.text(scale_x_start + scale_width, scale_y - 0.02, '500 km', 
               transform=ax_map.transAxes, fontsize=6, ha='center', va='top')
    
    # Calculate totals for legend
    if global_registered is not None and global_attendees is not None:
        total_registered = int(global_registered)
        total_attendees = int(global_attendees)
    else:
        cities_with_data = cities_gdf[cities_gdf['registered_count'] > 0]
        total_registered = int(cities_with_data['registered_count'].sum())
        total_attendees = int(cities_with_data['total_attendees'].sum())
    
    only_registered = total_registered - total_attendees
    
    pop_min = int(cities_gdf['population_2024'].min())
    pop_max = int(cities_gdf['population_2024'].max())
    
    cities_with_reg = cities_gdf[cities_gdf['registered_count'] > 0]
    reg_min = int(cities_with_reg['registered_count'].min()) if len(cities_with_reg) > 0 else 0
    reg_max = int(cities_with_reg['registered_count'].max()) if len(cities_with_reg) > 0 else 0
    
    # Legend for map
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker='o', color='w', label='City',
              markerfacecolor='red', markersize=4,
              markeredgecolor='white', markeredgewidth=0.3),
        Line2D([0], [0], marker='o', color='w', label=f'City Population (2024 | {pop_min:,}K - {pop_max:,}K)',
              markerfacecolor='lightgrey', markersize=8, alpha=0.4,
              markeredgecolor='grey', markeredgewidth=0.5),
        Line2D([0], [0], marker='o', color='w', label=f'Total Registrants ({total_registered} | {reg_min} - {reg_max})',
              markerfacecolor='none', markersize=8,
              markeredgecolor='black', markeredgewidth=1),
        mpatches.Patch(facecolor='black', edgecolor='black', 
                      label=f'Workshop - Attended ({total_attendees})', linewidth=1),
        mpatches.Patch(facecolor='#999999', edgecolor='black', 
                      label=f'Workshop - Absent, only registered ({only_registered})', linewidth=1),
    ]
    
    legend = ax_map.legend(handles=legend_elements, loc='lower right', 
                          fontsize=6, frameon=True, facecolor='white', 
                          edgecolor='black', title='Legend', title_fontsize=7,
                          framealpha=0.9)
    
    ax_map.set_title(panel_letters[0], fontsize=10, fontweight='bold', pad=10)
    ax_map.set_xlabel('Longitude (°E)', fontsize=8)
    ax_map.set_ylabel('Latitude (°N)', fontsize=8)
    ax_map.tick_params(labelsize=7)
    ax_map.grid(True, alpha=0.2, linestyle='--', linewidth=0.5)
    ax_map.set_aspect('equal')
    
    # =========================================================================
    # RIGHT PANEL: BAR CHART
    # When cluster_workshop_prof is provided → cluster-level bars (§5B)
    # Otherwise → city-level bars (§5A default)
    # =========================================================================

    def _bar_end(n, key):
        """The label at a bar's end: attended, or attended/registered."""
        if registered_by is None:
            return f'{int(n)}'
        return f'{int(n)}/{int(registered_by.get(key, 0))}'

    if cluster_workshop_prof is not None:
        # ── Cluster-level stacked bars ────────────────────────────────────────
        cluster_totals = (cluster_workshop_prof
                          .groupby('Cluster25')['count'].sum()
                          .sort_values(ascending=True))
        cluster_list_b = cluster_totals.index.tolist()
        professions_b  = sorted(cluster_workshop_prof['profession'].unique())

        dm_b = pd.DataFrame(0, index=cluster_list_b, columns=professions_b)
        for _, row in cluster_workshop_prof.iterrows():
            if row['Cluster25'] in dm_b.index:
                dm_b.loc[row['Cluster25'], row['profession']] = row['count']

        left_b = np.zeros(len(cluster_list_b))
        for prof in professions_b:
            vals = dm_b[prof].values
            if vals.sum() > 0:
                color = profession_colors.get(prof, '#888888')
                ax_bar.barh([(bar_labels or {}).get(c, f'Cluster {c}') for c in cluster_list_b],
                            vals, left=left_b,
                            color=color, edgecolor='white', linewidth=0.5, label=prof)
                left_b += vals

        for i, cl in enumerate(cluster_list_b):
            total = cluster_totals[cl]
            if total > 0:
                ax_bar.text(total + 0.2, i, _bar_end(total, cl),
                            va='center', ha='left', fontsize=6.5, fontweight='bold')
        if registered_by is not None:              # room for the longer labels
            ax_bar.set_xlim(right=ax_bar.get_xlim()[1] * 1.12)

        ax_bar.set_xlabel('Workshop Attendees', fontsize=8)
        ax_bar.set_title(panel_letters[1], fontsize=10, fontweight='bold', pad=10)
        ax_bar.tick_params(axis='both', labelsize=7)
        ax_bar.grid(axis='x', alpha=0.3, linestyle='--', linewidth=0.5)
        handles_b, labels_b = ax_bar.get_legend_handles_labels()
        if handles_b:
            ax_bar.legend(handles_b, labels_b, loc='lower right', fontsize=5,
                          title=bar_legend_title or 'Profession', title_fontsize=6,
                          framealpha=0.95, edgecolor='black', ncol=1)

        fig.suptitle(
            f'Stakeholder Distribution by Cluster ({config.PROJECT_STUDY_YEAR})',
            fontsize=11, fontweight='bold', y=0.98)

    else:
        # ── City-level stacked bars (default §5A behaviour) ───────────────────
        workshop_cities = (workshop_prof.groupby('city')['count'].sum()
                           .sort_values(ascending=True))
        workshop_cities = workshop_cities[workshop_cities > 0]

        professions_in_data = sorted(workshop_prof['profession'].unique())
        city_list = workshop_cities.index.tolist()
        data_matrix = pd.DataFrame(0, index=city_list, columns=professions_in_data)

        for _, row in workshop_prof.iterrows():
            if row['city'] in city_list:
                data_matrix.loc[row['city'], row['profession']] = row['count']

        left = np.zeros(len(city_list))
        for prof in professions_in_data:
            if prof in profession_colors:
                color = profession_colors[prof]
                values = data_matrix[prof].values
                if values.sum() > 0:
                    ax_bar.barh([(bar_labels or {}).get(c, c) for c in city_list], values, left=left,
                               color=color, edgecolor='white', linewidth=0.5, label=prof)
                    left += values

        ax_bar.set_xlabel('Number of Workshop Attendees', fontsize=8)
        ax_bar.set_title(panel_letters[1], fontsize=10, fontweight='bold', pad=10)
        ax_bar.tick_params(axis='both', labelsize=6)
        ax_bar.grid(axis='x', alpha=0.3, linestyle='--', linewidth=0.5)

        handles, labels = ax_bar.get_legend_handles_labels()
        ax_bar.legend(handles, labels, loc='lower right',
                     fontsize=5.5, frameon=True, facecolor='white', edgecolor='black',
                     title=bar_legend_title or 'Profession/Discipline (Mix)', title_fontsize=6,
                     framealpha=0.95, ncol=1)

        for i, city in enumerate(city_list):
            total = workshop_cities[city]
            ax_bar.text(total + 0.5, i, _bar_end(total, city),
                       va='center', ha='left', fontsize=5.5, fontweight='bold')
        if registered_by is not None:              # room for the longer labels
            ax_bar.set_xlim(right=ax_bar.get_xlim()[1] * 1.12)

        fig.suptitle(f'Stakeholder Distribution & Composition ({config.PROJECT_STUDY_YEAR})',
                    fontsize=11, fontweight='bold', y=0.98)

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    return fig


def create_city_classification_donut(cities_gdf, survey_df, workshop_total, 
                                     figsize=(8, 8), title=None):
    """
    Create a standalone 3-ring donut chart showing city classification:
    - Ring 1: Target vs Off-Target cities
    - Ring 2: Registration status
    - Ring 3: Workshop attendance status
    
    Parameters:
    -----------
    cities_gdf : GeoDataFrame
        Cities with population data (target cities)
    survey_df : DataFrame
        Survey data with matched_city_x (registered cities)
    workshop_total : DataFrame
        Workshop attendance totals
    figsize : tuple, optional
        Figure size (width, height) in inches, default (8, 8)
    title : str, optional
        Figure title, default "City Classification"
    
    Returns:
    --------
    fig : matplotlib.figure.Figure
        The figure object
    """
    import matplotlib.patches as mpatches
    
    # Calculate city sets
    target_cities = set(cities_gdf['city'].unique())  # Target cities from population CSV
    attended_cities = set(workshop_total['city'].dropna().unique())  # Cities with workshop attendance

    # Some workshop cities can appear only in matched_city_y (attendance location)
    # and not in matched_city_x (city association/registration linkage). Include
    # them here so Ring 3 attendance totals reconcile with workshop city counts.
    registered_cities = (
        set(survey_df['matched_city_x'].dropna().unique()) |
        attended_cities
    )
    
    # Center: Total unique cities (union of target and registered)
    total_unique_cities = len(target_cities | registered_cities)
    
    # Ring 1 segments: Target status
    cities_in_target = target_cities
    cities_off_target = registered_cities - target_cities
    
    n_target = len(cities_in_target)
    n_offtarget = len(cities_off_target)
    
    # Ring 2 segments: Registration status (subdivides Ring 1)
    target_registered = target_cities & registered_cities
    target_not_registered = target_cities - registered_cities
    offtarget_registered = cities_off_target  # All off-target are registered by definition
    
    n_target_reg = len(target_registered)
    n_target_notreg = len(target_not_registered)
    n_offtarget_reg = len(offtarget_registered)
    
    # Ring 3 segments: Attendance status (subdivides Ring 2 where applicable)
    target_reg_attended = target_registered & attended_cities
    target_reg_not_attended = target_registered - attended_cities
    target_not_reg_na = target_not_registered  # N/A - can't attend if not registered
    offtarget_reg_attended = offtarget_registered & attended_cities
    offtarget_reg_not_attended = offtarget_registered - attended_cities
    
    n_target_reg_att = len(target_reg_attended)
    n_target_reg_notatt = len(target_reg_not_attended)
    n_target_notreg_na = len(target_not_reg_na)
    n_offtarget_reg_att = len(offtarget_reg_attended)
    n_offtarget_reg_notatt = len(offtarget_reg_not_attended)
    
    # Create figure and axis
    fig, ax = plt.subplots(figsize=figsize, subplot_kw=dict(aspect="equal"))
    
    # Improved color scheme with better distinction
    # Ring 1: Target Status
    ring1_colors = ['#3498db', '#ff8c42']  # Blue for Target, Distinct Orange for Off-Target
    
    # Ring 2: Registration Status
    ring2_colors = [
        '#1e5a8e',  # Darker Blue (Target+Registered)
        '#95a5a6',  # Grey (Target+Not Registered)
        '#c55504'   # Darker Orange (Off-Target+Registered)
    ]
    
    # Ring 3: Attendance Status
    ring3_colors = [
        '#0d7f3c',  # Dark Green (Target+Reg+Attended)
        '#e74c3c',  # Red (Target+Reg+Not Attended)
        '#d5d8dc',  # Light Grey (Target+NotReg+N/A)
        '#52be80',  # Lighter Green (Off-Target+Reg+Attended)
        '#f39c12'   # Gold/Yellow (Off-Target+Reg+Not Attended)
    ]
    
    # Ring 1: Target Status (360° complete)
    ring1_sizes = [n_target, n_offtarget]
    ring1_labels = ['Target', 'Off-Target']
    
    wedges_r1, _ = ax.pie(ring1_sizes, 
                          radius=0.50,
                          colors=ring1_colors,
                          labels=None,
                          startangle=90,
                          wedgeprops=dict(width=0.15, edgecolor='white', linewidth=2.5))
    
    # Add Ring 1 labels
    for i, (wedge, label, count) in enumerate(zip(wedges_r1, ring1_labels, ring1_sizes)):
        ang = (wedge.theta2 + wedge.theta1) / 2
        x = 0.425 * np.cos(np.deg2rad(ang))
        y = 0.425 * np.sin(np.deg2rad(ang))
        ax.text(x, y, f'{label}\n({count})', ha='center', va='center', 
               fontsize=10, fontweight='bold', color='black')
    
    # Ring 2: Registration Status (360° complete, aligned with Ring 1)
    ring2_sizes = [n_target_reg, n_target_notreg, n_offtarget_reg]
    ring2_labels = ['Registered', 'Not Reg.', 'Registered']
    
    wedges_r2, _ = ax.pie(ring2_sizes,
                          radius=0.65,
                          colors=ring2_colors,
                          labels=None,
                          startangle=90,
                          wedgeprops=dict(width=0.15, edgecolor='white', linewidth=2))
    
    # Add Ring 2 labels
    for i, (wedge, label, count) in enumerate(zip(wedges_r2, ring2_labels, ring2_sizes)):
        if count > 0:
            ang = (wedge.theta2 + wedge.theta1) / 2
            x = 0.575 * np.cos(np.deg2rad(ang))
            y = 0.575 * np.sin(np.deg2rad(ang))
            ax.text(x, y, f'{label}\n({count})', ha='center', va='center', 
                   fontsize=9, fontweight='normal', color='black')
    
    # Ring 3: Attendance Status (360° complete, with N/A for not registered)
    ring3_sizes = [n_target_reg_att, n_target_reg_notatt, n_target_notreg_na, 
                   n_offtarget_reg_att, n_offtarget_reg_notatt]
    ring3_labels = ['Attended', 'Not Attended', 'N/A', 'Attended', 'Not Attended']
    
    wedges_r3, _ = ax.pie(ring3_sizes,
                          radius=0.80,
                          colors=ring3_colors,
                          labels=None,
                          startangle=90,
                          wedgeprops=dict(width=0.15, edgecolor='white', linewidth=1.5))
    
    # Add Ring 3 labels (positioned outside the ring)
    for i, (wedge, label, count) in enumerate(zip(wedges_r3, ring3_labels, ring3_sizes)):
        if count > 0:
            ang = (wedge.theta2 + wedge.theta1) / 2
            x = 0.90 * np.cos(np.deg2rad(ang))
            y = 0.90 * np.sin(np.deg2rad(ang))
            
            # Special handling for N/A
            if label == 'N/A':
                wedge.set_hatch('///')
                wedge.set_edgecolor('grey')
                ax.text(x, y, f'{label}\n({count})', ha='center', va='center', 
                       fontsize=8, fontweight='normal', color='black',
                       bbox=dict(boxstyle='round,pad=0.3', facecolor='white', 
                                edgecolor='grey', alpha=0.8))
            else:
                ax.text(x, y, f'{label}\n({count})', ha='center', va='center', 
                       fontsize=8, fontweight='normal', color='black')
    
    # Center circle and text
    centre_circle = plt.Circle((0, 0), 0.35, fc='white', linewidth=0)
    ax.add_artist(centre_circle)
    
    # Multi-line text with different font sizes
    ax.text(0, 0.08, f'{total_unique_cities}', 
           ha='center', va='center', fontsize=32, fontweight='bold', color='black')
    ax.text(0, -0.05, 'Cities', 
           ha='center', va='center', fontsize=14, fontweight='normal', color='black')
    ax.text(0, -0.14, '(Target and Others)', 
           ha='center', va='center', fontsize=10, fontweight='normal', color='grey')
    
    ax.axis('equal')
    
    # Add title
    if title is None:
        title = f'City Classification: Target, Registration & Workshop Attendance ({config.PROJECT_STUDY_YEAR})'
    fig.suptitle(title, fontsize=13, fontweight='bold', y=0.98)
    
    # Add legend explaining the rings
    legend_elements = [
        mpatches.Patch(facecolor='white', edgecolor='black', linewidth=1, 
                      label='Ring 1: Target Status - >300K Population: 2024'),
        mpatches.Patch(facecolor='white', edgecolor='black', linewidth=1, 
                      label='Ring 2: Stakeholder Registration Status'),
        mpatches.Patch(facecolor='white', edgecolor='black', linewidth=1, 
                      label='Ring 3: Workshop Attendance Status'),
        mpatches.Patch(facecolor='#d5d8dc', edgecolor='grey', hatch='///', 
                      label='N/A: Not Applicable')
    ]
    
    ax.legend(handles=legend_elements, loc='upper center', fontsize=8, 
             frameon=True, facecolor='white', edgecolor='black', 
             framealpha=0.9, bbox_to_anchor=(0.5, -0.08), ncol=2)
    
    plt.tight_layout()

    return fig


def create_city_stakeholder_donut(cluster_summary, study_gdf=None,
                                  cluster25_colors=None,
                                  total_pids=None, attended_pids=None,
                                  figsize=(14, 8), show_title=True,
                                  legend_count_label='att.'):
    """
    Single top-semicircle half-donut chart (horizontal cut, upper half active).

    Arc spans 0° (right) counterclockwise through 90° (top) to 180° (left).

    Hierarchy (inner → outer):
      Ring 1 : 16 Cluster25 classes — clusters with ANY workshop-attended cities
               appear first (right side of arc), then clusters with none.
               Arc size = N cities per cluster.  Colour = cluster colour.
      Ring 2 : Workshop attendance split within each Ring 1 cluster arc.
               [attended sub-arc (cluster colour)] then
               [not-attended sub-arc (cluster colour lightened 45%)].
               Inherits cluster colour → colour continuity Ring 1 → Ring 2.
      Ring 3 : Individual cities within each Ring 2 sub-arc.
               Attended cities: arc ∝ total_attendees (or registered_count),
               normalised to sum = n_attended_cl; colour graded vivid→lighter.
               Not-attended cities: equal arcs; strongly lightened cluster colour.
      Labels : Attended cities only — "City (N attendees)" with radial leader
               lines.  Right-quarter segments labelled to the right; left-quarter
               segments labelled to the left.  Not-attended cities: no label.
    Center   : n_cities (from NB01, dynamic) top; survey-attended stakeholders
               (incl. absorbed cities) bottom — both fully dynamic.

    Parameters
    ----------
    cluster_summary : DataFrame
        ``cluster_stake_df`` from NB02 §4B.  Required columns:
        ``Cluster``, ``N Cities``, ``Registered``, ``Attended Workshop``.
    study_gdf : GeoDataFrame, optional
        Per-city GDF with ``Cluster25``, ``city``, ``total_attendees``
        (preferred) or ``registered_count`` (fallback).
    cluster25_colors : dict, optional
        ``{int: hex_str}`` mapping from ``config.CLUSTER25_COLORS``.
    total_pids : int, optional
        Reserved for API compatibility; not displayed.
    attended_pids : int, optional
        Unique PIDs with survey status "Yes" (incl. absorbed cities).
        Falls back to sum of 'Attended Workshop' column when None.
    figsize : tuple
        Figure size in inches.  Default (12, 11) suits portrait half-donut.
    show_title : bool
        False leaves the figure without its title.
    legend_count_label : str
        The word after each cluster's attendance count in the legend.

    Returns
    -------
    fig : matplotlib.figure.Figure
    """
    import matplotlib.colors as mcolors
    import matplotlib.patches as mpatches
    from matplotlib.gridspec import GridSpec
    from matplotlib.patches import Rectangle

    if cluster25_colors is None:
        cluster25_colors = {}

    # ── helpers ──────────────────────────────────────────────────────────────
    def _cl_num(lbl):
        try:
            return int(str(lbl).lstrip('C'))
        except ValueError:
            return 999

    def _cl_color(lbl):
        return cluster25_colors.get(_cl_num(lbl), '#888888')

    def _lighten(hx, amount):
        rgb = np.array(mcolors.to_rgb(hx))
        return mcolors.to_hex(rgb + (1.0 - rgb) * float(np.clip(amount, 0, 1)))

    def _half_ring(ax, data, radius, width):
        """Top-facing half-donut ring (startangle=0, data spans top 180°)."""
        sizes  = [d[0] for d in data if d[0] > 0]
        colors = [d[1] for d in data if d[0] > 0]
        if not sizes:
            return
        total = sum(sizes)
        ax.pie(sizes + [total], radius=radius, colors=colors + ['white'],
               labels=None, startangle=0,
               wedgeprops=dict(width=width, edgecolor='white', linewidth=0.6))

    # ── base cluster table (numerically sorted) ───────────────────────────────
    cs = (cluster_summary.copy()
          .assign(_n=lambda df: df['Cluster'].map(_cl_num))
          .sort_values('_n').drop(columns='_n').reset_index(drop=True))

    n_cities   = int(cs['N Cities'].sum())
    center_att = (attended_pids if attended_pids is not None
                  else int(cs['Attended Workshop'].sum()))

    # ── per-cluster attendance breakdown ──────────────────────────────────────
    # Use total_attendees (workshop presence) if present in study_gdf,
    # otherwise fall back to registered_count as proxy.
    _MIN_FRAC = 0.02

    if study_gdf is not None and 'total_attendees' in study_gdf.columns:
        _att_col = 'total_attendees'
    else:
        _att_col = 'registered_count'

    cluster_data = {}   # cl → dict with n_att, n_not, att_sub, not_sub, n_cities

    for _, row in cs.iterrows():
        cl = row['Cluster']
        if study_gdf is not None and 'Cluster25' in study_gdf.columns:
            sub_cl = study_gdf[study_gdf['Cluster25'] == _cl_num(cl)]
            att_sub = (sub_cl[sub_cl[_att_col] > 0]
                       .sort_values(_att_col, ascending=False)
                       .reset_index(drop=True))
            not_sub = sub_cl[sub_cl[_att_col] == 0].reset_index(drop=True)
            n_att = len(att_sub)
            n_not = len(not_sub)
        else:
            n_att = int(row.get('Cities w/ Stakeholders', 0))
            n_not = int(row['N Cities']) - n_att
            att_sub = None
            not_sub = None

        cluster_data[cl] = dict(
            n_att=n_att, n_not=n_not,
            att_sub=att_sub, not_sub=not_sub,
            n_cities=int(row['N Cities']),
        )

    n_att_total = sum(d['n_att'] for d in cluster_data.values())
    n_not_total = sum(d['n_not'] for d in cluster_data.values())

    # ── sort Ring 1: clusters with ANY attendance first, then without ─────────
    cs_att   = cs[cs['Cluster'].map(lambda c: cluster_data[c]['n_att'] > 0)]
    cs_noatt = cs[cs['Cluster'].map(lambda c: cluster_data[c]['n_att'] == 0)]
    cs_sorted = pd.concat([cs_att, cs_noatt]).reset_index(drop=True)

    # ── Ring 1: cluster arcs ──────────────────────────────────────────────────
    r1_data = [
        (cluster_data[row['Cluster']]['n_cities'], _cl_color(row['Cluster']))
        for _, row in cs_sorted.iterrows()
    ]

    # ── Ring 2: within each cluster arc → [attended | not-attended] ──────────
    # attended sub-arc  : cluster colour (full)
    # not-attended arc  : cluster colour lightened 45%
    r2_data = []
    for _, row in cs_sorted.iterrows():
        cl     = row['Cluster']
        d      = cluster_data[cl]
        cl_col = _cl_color(cl)
        if d['n_att'] > 0:
            r2_data.append((d['n_att'], cl_col))
        if d['n_not'] > 0:
            r2_data.append((d['n_not'], _lighten(cl_col, 0.45)))

    # ── Ring 3 + per-city label metadata ─────────────────────────────────────
    # city_ring3 tuples: (city_name, att_count, draw_color, draw_size, is_attended)
    city_ring3 = []

    for _, row in cs_sorted.iterrows():
        cl     = row['Cluster']
        d      = cluster_data[cl]
        cl_col = _cl_color(cl)

        # — attended cities (arc ∝ att_col, normalised to n_att) —
        if d['n_att'] > 0 and d['att_sub'] is not None:
            sub   = d['att_sub']
            n_sub = len(sub)
            total = float(sub[_att_col].sum())
            if total > 0:
                raw = [max(float(sub.at[i, _att_col]) / total,
                           _MIN_FRAC / n_sub) for i in range(n_sub)]
            else:
                raw = [1.0 / n_sub] * n_sub
            raw_sum   = sum(raw)
            arc_sizes = [d['n_att'] * r / raw_sum for r in raw]
            for i, sr in sub.iterrows():
                cnt     = int(sr[_att_col])
                lighten = 0.0 if n_sub <= 1 else 0.55 * i / (n_sub - 1)
                city_ring3.append((sr['city'], cnt,
                                   _lighten(cl_col, lighten), arc_sizes[i], True))

        # — not-attended cities (equal arcs, lightened) —
        if d['n_not'] > 0:
            not_col = _lighten(cl_col, 0.55)
            if d['not_sub'] is not None:
                for _, sr in d['not_sub'].iterrows():
                    city_ring3.append((sr['city'], 0, not_col, 1.0, False))
            else:
                for _ in range(d['n_not']):
                    city_ring3.append((cl, 0, not_col, 1.0, False))

    r3_draw = [(e[3], e[2]) for e in city_ring3]

    # ── label positions + leader-line coordinates (top-half donut) ───────────
    # Arc angles: mid_a = 0° + cumul×180°  (0° = right, 90° = top, 180° = left).
    # Right quarter (0°–90°): ha='left',  rot = mid_a        → labels point right.
    # Left quarter  (90°–180°): ha='right', rot = mid_a−180  → labels point left.
    # Only attended cities receive a label.
    # Leader line: thin radial tick from Ring 3 outer edge to label anchor.
    _R          = 0.80
    _ring3_edge = _R + 0.14 + 0.015   # just outside Ring 3 outer rim
    _label_r    = _R + 0.30           # label anchor radius
    r3_total    = sum(e[0] for e in r3_draw) if r3_draw else 1
    cumul       = 0.0
    # (x_tick, y_tick, x_lbl, y_lbl, text, rot, ha)
    city_labels = []

    for (cname, cnt, _, arc_sz, is_att) in city_ring3:
        frac    = arc_sz / r3_total
        mid_a   = 0.0 + (cumul + frac / 2.0) * 180.0
        mid_rad = np.radians(mid_a)

        if is_att:   # labels only for cities with workshop attendance
            x_tick = _ring3_edge * np.cos(mid_rad)
            y_tick = _ring3_edge * np.sin(mid_rad)
            x_lbl  = _label_r   * np.cos(mid_rad)
            y_lbl  = _label_r   * np.sin(mid_rad)

            is_right = mid_a <= 90
            rot = mid_a if is_right else mid_a - 180
            ha  = 'left' if is_right else 'right'
            city_labels.append((x_tick, y_tick, x_lbl, y_lbl,
                                f"{cname} ({cnt})", rot, ha))
        cumul += frac

    # ── figure layout ─────────────────────────────────────────────────────────
    fig = plt.figure(figsize=figsize)
    gs  = GridSpec(1, 2, figure=fig, width_ratios=[0.72, 0.38], wspace=0.04)
    ax     = fig.add_subplot(gs[0])
    ax_leg = fig.add_subplot(gs[1])
    ax_leg.axis('off')

    # ── draw rings ────────────────────────────────────────────────────────────
    _half_ring(ax, r1_data, 0.46, 0.14)   # Ring 1 — clusters (16)
    _half_ring(ax, r2_data, 0.62, 0.14)   # Ring 2 — attendance split
    _half_ring(ax, r3_draw, 0.78, 0.14)   # Ring 3 — cities (56)

    # White center disc
    ax.add_artist(plt.Circle((0, 0), 0.32, fc='white', linewidth=0, zorder=4))

    # White rectangle masks bottom-half filler wedges cleanly
    _ext = _label_r + 0.28
    ax.add_patch(Rectangle((-_ext - 0.05, -_ext - 0.05),
                            2 * (_ext + 0.05), _ext + 0.06,
                            facecolor='white', edgecolor='none', zorder=5))

    # ── leader lines + city labels (attended cities only) ─────────────────────
    # Improved: subtle background + better sizing for readability
    for (xt, yt, xl, yl, text, rot, ha) in city_labels:
        ax.plot([xt, xl * 0.987], [yt, yl * 0.987],
                color='#999999', lw=0.5, zorder=6, solid_capstyle='round', alpha=0.6)
        # Add subtle label background for better contrast
        ax.text(xl, yl, text, ha=ha, va='center',
                fontsize=7.2, rotation=rot, color='#000000', zorder=7,
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white', 
                         edgecolor='none', alpha=0.75, linewidth=0))

    # ── center text (dynamic: NB01 city count + workshop-attended PIDs) ───────
    # Positioned inside the inner white disc (upper portion visible above flat edge)
    # Enhanced hierarchy and spacing
    ax.text(0,  0.19, str(n_cities), ha='center', va='center',
            fontsize=20, fontweight='bold', color='#222222', zorder=6)
    ax.text(0,  0.09, 'Target Cities', ha='center', va='center',
            fontsize=8, color='#666666', zorder=6)
    ax.text(0, -0.04, str(center_att), ha='center', va='center',
            fontsize=18, fontweight='bold', color='#222222', zorder=6)
    ax.text(0, -0.14, 'Workshop Participants', ha='center', va='center',
            fontsize=8, fontweight='bold', color='#444444', zorder=6)

    # ── axis bounds (top half: full width, y ≥ −0.15) ────────────────────────
    ax.set_xlim(-_ext, _ext)
    ax.set_ylim(-0.18, _ext)
    ax.set_aspect('equal', adjustable='datalim')
    ax.axis('off')

    # ── legend ────────────────────────────────────────────────────────────────
    # One entry per cluster (attended clusters first). A filled coloured circle
    # marks clusters with workshop attendance; an open coloured circle marks those
    # without. Label format: "CX (N cities | M att.)".
    from matplotlib.lines import Line2D

    def _circ(color, filled):
        return Line2D([0], [0], marker='o', linestyle='none', markersize=9,
                      markerfacecolor=(color if filled else 'none'),
                      markeredgecolor=color, markeredgewidth=1.4)

    leg_handles, leg_labels = [], []
    for _, row in cs_sorted.iterrows():
        cl   = row['Cluster']
        d    = cluster_data[cl]
        n_aw = int(row['Attended Workshop'])
        leg_handles.append(_circ(_cl_color(cl), d['n_att'] > 0))
        leg_labels.append(f"{cl}  ({d['n_cities']} cities | {n_aw} {legend_count_label})")

    ax_leg.legend(leg_handles, leg_labels, loc='center left',
                  fontsize=8.5, title='LEGEND', title_fontsize=11,
                  frameon=False, handlelength=1.0, handletextpad=0.6,
                  labelspacing=0.75, borderpad=0.5, bbox_to_anchor=(-0.02, 0.5))

    if show_title:
        fig.suptitle(
            f'City & Stakeholder Classification by Physiographic Cluster (56 Cities, 16 Clusters) — {config.PROJECT_STUDY_YEAR}',
            fontsize=12, fontweight='bold', y=0.98)
    plt.tight_layout()
    return fig


# Keep plural alias for backward compatibility
create_city_stakeholder_donuts = create_city_stakeholder_donut


def create_collab_type_chart(
    city_pivot,
    cluster_pivot,
    collab_types,
    collab_colors,
    figsize=(15, 10),
    top_n_cities=None,
    bar_height=0.68,
):
    """
    Two-panel horizontal stacked bar chart: collaboration type mix of registered
    stakeholders, shown per city (left) and per cluster (right).

    Each bar represents one city or cluster.  Bar segments are broken into the
    six collaboration types from ``9_reg_collab_type`` (multi-select: a single
    respondent may appear in more than one segment).

    Parameters
    ----------
    city_pivot : DataFrame
        Wide-format table.  Index = city name.
        Columns = collaboration type labels (must match ``collab_types``).
        Values  = count of unique PIDs mentioning that type in that city.
        Must also contain a ``'_total'`` column (row-sum of type counts).
    cluster_pivot : DataFrame
        Same structure but index = cluster label (e.g. 'C13').
    collab_types : list[str]
        Ordered list of collaboration type labels (controls stacking order).
    collab_colors : dict[str, str]
        ``{type_label: hex_colour}``.
    figsize : tuple
        Figure size in inches.  Default (15, 10).
    top_n_cities : int or None
        If set, display only the top N cities by total count.
        None (default) displays all cities.
    bar_height : float
        Fractional height of each horizontal bar (0–1).  Default 0.68.

    Returns
    -------
    fig : matplotlib.figure.Figure
    """
    import matplotlib.patches as mpatches
    import matplotlib.ticker as mticker

    # ── Sort both pivots: descending total → largest at top of chart ──────────
    city_s  = city_pivot.sort_values('_total', ascending=True)
    if top_n_cities is not None:
        city_s = city_s.tail(int(top_n_cities))
    clust_s = cluster_pivot.sort_values('_total', ascending=True)

    # ── Figure and axes ───────────────────────────────────────────────────────
    n_city  = len(city_s)
    n_clust = len(clust_s)

    fig, axes = plt.subplots(
        1, 2,
        figsize=figsize,
        gridspec_kw={'width_ratios': [max(0.55, n_city / (n_city + n_clust)),
                                      min(0.45, n_clust / (n_city + n_clust))]},
    )
    fig.subplots_adjust(wspace=0.38, bottom=0.14)

    ax_c, ax_k = axes

    # ── Shared drawing helper ─────────────────────────────────────────────────
    def _stacked_barh(ax, pivot, ylabel_fontsize=8, annot_min=2):
        ys     = np.arange(len(pivot))
        lefts  = np.zeros(len(pivot))

        for ctype in collab_types:
            if ctype not in pivot.columns:
                continue
            vals = pivot[ctype].values.astype(float)
            color = collab_colors.get(ctype, '#888888')

            bars = ax.barh(
                ys, vals, left=lefts,
                height=bar_height,
                color=color,
                edgecolor='white', linewidth=0.5,
            )

            # White value label inside segment when wide enough
            for i, (v, l) in enumerate(zip(vals, lefts)):
                if v >= annot_min:
                    ax.text(
                        l + v / 2, ys[i], str(int(v)),
                        ha='center', va='center',
                        fontsize=6.2, color='white', fontweight='bold',
                        clip_on=True,
                    )
            lefts += vals

        # 'n=…' total annotation at the right end of each bar
        for i, tot in enumerate(pivot['_total']):
            ax.text(
                lefts[i] + 0.4, ys[i],
                f'n={int(tot)}',
                ha='left', va='center',
                fontsize=6.8, color='#333333',
            )

        # Axis styling
        ax.set_yticks(ys)
        ax.set_yticklabels(pivot.index, fontsize=ylabel_fontsize)
        ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True, nbins=6))
        ax.set_xlabel('No. of registered stakeholders (multi-select mentions)',
                      fontsize=8)
        ax.spines[['top', 'right']].set_visible(False)
        ax.xaxis.grid(True, alpha=0.25, linestyle='--', linewidth=0.5)
        ax.set_axisbelow(True)
        # Extend x-axis slightly to the right so 'n=…' labels fit
        ax.set_xlim(0, lefts.max() * 1.18)

    # ── Draw panels ───────────────────────────────────────────────────────────
    _stacked_barh(ax_c, city_s,  ylabel_fontsize=7.5)
    ax_c.set_title(
        f'Per City  ({n_city} cities with registered stakeholders)',
        fontsize=9.5, fontweight='bold', pad=7,
    )

    _stacked_barh(ax_k, clust_s, ylabel_fontsize=8.5)
    ax_k.set_title(
        f'Per Cluster  ({n_clust} clusters represented)',
        fontsize=9.5, fontweight='bold', pad=7,
    )

    # ── Shared legend (bottom-centre) ─────────────────────────────────────────
    legend_handles = [
        mpatches.Patch(facecolor=collab_colors.get(ct, '#888'), edgecolor='#555',
                       linewidth=0.5, label=ct)
        for ct in collab_types
    ]
    fig.legend(
        handles=legend_handles,
        loc='lower center',
        ncol=3,
        fontsize=8,
        frameon=True,
        facecolor='white',
        edgecolor='#bbbbbb',
        bbox_to_anchor=(0.5, 0.01),
        handlelength=1.4,
        handleheight=1.0,
        columnspacing=1.2,
    )

    fig.suptitle(
        'Collaboration Type Mix — Registered Stakeholders  '
        f'(n = 321 unique PIDs; 568 city-registration mentions)\n'
        'Multi-select: one respondent may appear in more than one category per bar',
        fontsize=10, fontweight='bold', y=1.01,
    )

    return fig


def create_perception_chart_with_donuts(
    unique_resp: pd.DataFrame,
    warming_total: pd.Series,
    diurnal_total: pd.Series,
    min_participants: int = 2,
    figsize: tuple = (14, 5.5),
    legend_scale: float = 1.2,
    peak_total: pd.Series = None,
    panel_letters: tuple = ('A)', 'B)', 'C)'),
) -> tuple:
    """
    Create combined bar charts with embedded donut charts for stakeholder perception.
    
    Shows city-level breakdown with overall summary donuts embedded in each panel.
    
    Parameters:
    -----------
    unique_resp : DataFrame
        Unique responses per participant with 'matched_city_y', 
        '61_temp_increase_10yrs', '60_diurnal_severity_heat' columns
    warming_total : Series
        Overall warming perception counts
    diurnal_total : Series
        Overall diurnal heating pattern counts
    min_participants : int
        Minimum participants per city to include (default: 2)
    figsize : tuple
        Figure size (width, height)
    legend_scale : float
        Scale factor for legend font sizes (default: 1.2)
        
    Returns:
    --------
    tuple : (main_fig, separate_donuts_fig)
        Main figure with embedded donuts and separate standalone donuts figure
    """
    from matplotlib.gridspec import GridSpec
    
    # Define color schemes
    warming_colors = {
        'Yes': '#d62728',           # Red - city has warmed
        'No': '#2ca02c',            # Green - city has not warmed
        "I'm not sure": '#7f7f7f',  # Gray - uncertain
        "I'd rather not say": '#c7c7c7'    # Light gray - no response
    }
    
    diurnal_colors = {
        'During the day': '#ff7f0e',  # Orange - daytime heat
        'At night': '#1f77b4',        # Blue - nighttime heat
        'Both': '#9467bd',            # Purple - both periods
        "I'd rather not say": '#c7c7c7'      # Light gray - no response
    }

    # Peak-season (Q58) — seasonal order, cool→hot palette; grey handling matches
    # the warming/diurnal "not sure" / "rather not say" convention.
    peak_colors = {
        'December – February': '#4e79a7',  # Blue  - cool/harmattan
        'March – May':         '#d62728',  # Red   - dry-season heat peak
        'June – August':       '#2ca02c',  # Green - rainy season
        'September – November': '#ff7f0e', # Orange- transition
        'I am not sure':            '#7f7f7f',  # Gray  - uncertain
        "I'd rather not say":       '#c7c7c7',  # Light gray - no response
    }
    peak_order = ['December – February', 'March – May',
                  'June – August', 'September – November',
                  'I am not sure', "I'd rather not say"]

    _three = peak_total is not None   # 3-panel mode when peak data supplied

    # Sort cities by total participants
    city_order = unique_resp['matched_city_y'].value_counts().index.tolist()
    
    # Cross-tabulations
    warming_by_city = pd.crosstab(
        unique_resp['matched_city_y'], 
        unique_resp['61_temp_increase_10yrs']
    ).reindex(city_order)
    
    diurnal_by_city = pd.crosstab(
        unique_resp['matched_city_y'], 
        unique_resp['60_diurnal_severity_heat']
    ).reindex(city_order)
    
    # Filter cities
    cities_filtered = [c for c in city_order 
                       if unique_resp['matched_city_y'].value_counts()[c] >= min_participants]
    
    warming_filtered = warming_by_city.loc[cities_filtered]
    diurnal_filtered = diurnal_by_city.loc[cities_filtered]
    
    # Prepare data
    warming_order = ['Yes', 'No', "I'm not sure", "I'd rather not say"]
    warming_cols = [c for c in warming_order if c in warming_filtered.columns]
    warming_data = warming_filtered[warming_cols].fillna(0)
    
    diurnal_order = ['During the day', 'At night', 'Both', "I'd rather not say"]
    diurnal_cols = [c for c in diurnal_order if c in diurnal_filtered.columns]
    diurnal_data = diurnal_filtered[diurnal_cols].fillna(0)

    # Peak-season crosstab (Panel C) — only when 3-panel mode is requested
    if _three and '58_temp_peak_city' in unique_resp.columns:
        peak_by_city = pd.crosstab(
            unique_resp['matched_city_y'],
            unique_resp['58_temp_peak_city']
        ).reindex(city_order)
        peak_filtered = peak_by_city.loc[cities_filtered]
        peak_cols = [c for c in peak_order if c in peak_filtered.columns]
        peak_data = peak_filtered[peak_cols].fillna(0)
    else:
        _three = False   # missing column → fall back to 2-panel

    # =========================================================================
    # MAIN FIGURE: Bar charts with embedded donuts
    # =========================================================================
    fig = plt.figure(figsize=figsize)
    _ncol = 3 if _three else 2
    gs = GridSpec(1, _ncol, figure=fig,
                  width_ratios=[1] * _ncol, wspace=0.08)

    # Create subplots for bars
    ax1 = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[0, 1])
    ax3 = fig.add_subplot(gs[0, 2]) if _three else None
    
    # --- LEFT PANEL: City Warming Over 10 Years ---
    left = np.zeros(len(warming_data))
    bar_handles = []
    for col in warming_cols:
        if col in warming_data.columns:
            values = warming_data[col].values
            bars = ax1.barh(range(len(warming_data)), values, left=left, 
                     color=warming_colors.get(col, '#c7c7c7'), label=col, height=0.7)
            bar_handles.append(bars)
            left += values
    
    ax1.set_yticks(range(len(warming_data)))
    ax1.set_yticklabels(warming_data.index, fontsize=10)
    ax1.set_xlabel('Number of Participants', fontsize=10)
    ax1.set_title(f'{panel_letters[0]} City Warming Over 10 Years', fontsize=11, fontweight='bold', loc='left')
    ax1.invert_yaxis()
    ax1.set_xlim(0, 35)  # Fixed limit for consistent panel width
    
    # Add count labels
    for i, city in enumerate(warming_data.index):
        total = warming_data.loc[city].sum()
        ax1.text(total + 0.3, i, f'n={int(total)}', va='center', fontsize=8, color='gray')
    
    # Prepare warming donut data
    warming_vals = [warming_total.get(cat, 0) for cat in warming_order 
                    if cat in warming_total.index or warming_total.get(cat, 0) > 0]
    warming_labels = [cat for cat in warming_order 
                      if cat in warming_total.index or warming_total.get(cat, 0) > 0]
    warming_colors_list = [warming_colors[cat] for cat in warming_labels]
    total_warming = sum(warming_vals)
    
    # Embedded donut for warming (positioned ABOVE the legend, moved up 1.5cm)
    ax1_inset = ax1.inset_axes([0.58, 0.33, 0.40, 0.45])  # [x, y, width, height]
    
    wedges, _, autotexts = ax1_inset.pie(
        warming_vals, labels=None, colors=warming_colors_list,
        autopct=lambda p: f'{p:.0f}%' if p > 5 else '',
        pctdistance=0.75, startangle=90,
        wedgeprops=dict(width=0.45, edgecolor='white', linewidth=0.5)
    )
    for autotext in autotexts:
        autotext.set_fontsize(7)
        autotext.set_color('white')
        autotext.set_fontweight('bold')
    
    # Center text: Number bigger/bolder, "Participants" smaller and gray
    ax1_inset.text(0, 0.05, f'{total_warming}', ha='center', va='center', 
                   fontsize=12, fontweight='bold', color='black')
    ax1_inset.text(0, -0.18, 'Participants', ha='center', va='center', 
                   fontsize=6, fontweight='normal', color='#666666')
    ax1_inset.set_title('Overall', fontsize=8, fontweight='bold', pad=2)
    
    # Legend at bottom-right (BELOW the donut)
    ax1.legend(loc='lower right', fontsize=8*legend_scale, title='Response', 
               title_fontsize=9*legend_scale, framealpha=0.95, 
               bbox_to_anchor=(0.99, 0.01))
    
    # --- RIGHT PANEL: Timing of Most Severe Heat ---
    left = np.zeros(len(diurnal_data))
    for col in diurnal_cols:
        if col in diurnal_data.columns:
            values = diurnal_data[col].values
            ax2.barh(range(len(diurnal_data)), values, left=left,
                     color=diurnal_colors.get(col, '#c7c7c7'), label=col, height=0.7)
            left += values
    
    ax2.set_yticks(range(len(diurnal_data)))
    ax2.set_yticklabels([])  # Shared with left panel
    ax2.invert_yaxis()
    ax2.set_xlabel('Number of Participants', fontsize=10)
    ax2.set_title(f'{panel_letters[1]} Timing of Most Severe Heat', fontsize=11, fontweight='bold', loc='left')
    ax2.set_xlim(0, 35)  # Fixed limit for consistent panel width
    
    # Add count labels
    for i, city in enumerate(diurnal_data.index):
        total = diurnal_data.loc[city].sum()
        ax2.text(total + 0.3, i, f'n={int(total)}', va='center', fontsize=8, color='gray')
    
    # Prepare diurnal donut data
    diurnal_vals = [diurnal_total.get(cat, 0) for cat in diurnal_order 
                    if cat in diurnal_total.index or diurnal_total.get(cat, 0) > 0]
    diurnal_labels = [cat for cat in diurnal_order 
                      if cat in diurnal_total.index or diurnal_total.get(cat, 0) > 0]
    diurnal_colors_list = [diurnal_colors[cat] for cat in diurnal_labels]
    total_diurnal = sum(diurnal_vals)
    
    # Embedded donut for diurnal (positioned ABOVE the legend, moved up 1.5cm)
    ax2_inset = ax2.inset_axes([0.58, 0.33, 0.40, 0.45])
    
    wedges2, _, autotexts2 = ax2_inset.pie(
        diurnal_vals, labels=None, colors=diurnal_colors_list,
        autopct=lambda p: f'{p:.0f}%' if p > 5 else '',
        pctdistance=0.75, startangle=90,
        wedgeprops=dict(width=0.45, edgecolor='white', linewidth=0.5)
    )
    for autotext in autotexts2:
        autotext.set_fontsize(7)
        autotext.set_color('white')
        autotext.set_fontweight('bold')
    
    # Center text: Number bigger/bolder, "Participants" smaller and gray
    ax2_inset.text(0, 0.05, f'{total_diurnal}', ha='center', va='center', 
                   fontsize=12, fontweight='bold', color='black')
    ax2_inset.text(0, -0.18, 'Participants', ha='center', va='center', 
                   fontsize=6, fontweight='normal', color='#666666')
    ax2_inset.set_title('Overall', fontsize=8, fontweight='bold', pad=2)
    
    # Legend at bottom-right (BELOW the donut)
    ax2.legend(loc='lower right', fontsize=8*legend_scale, title='Response', 
               title_fontsize=9*legend_scale, framealpha=0.95,
               bbox_to_anchor=(0.99, 0.01))
    
    # --- PANEL C: Peak Season / Month (Q58) ---
    if _three:
        left = np.zeros(len(peak_data))
        for col in peak_cols:
            if col in peak_data.columns:
                values = peak_data[col].values
                ax3.barh(range(len(peak_data)), values, left=left,
                         color=peak_colors.get(col, '#c7c7c7'), label=col, height=0.7)
                left += values

        ax3.set_yticks(range(len(peak_data)))
        ax3.set_yticklabels([])  # shared with left panel
        ax3.invert_yaxis()
        ax3.set_xlabel('Number of Participants', fontsize=10)
        ax3.set_title(f'{panel_letters[2]} Peak Heat Season', fontsize=11, fontweight='bold', loc='left')
        ax3.set_xlim(0, 35)

        for i, city in enumerate(peak_data.index):
            total = peak_data.loc[city].sum()
            ax3.text(total + 0.3, i, f'n={int(total)}', va='center', fontsize=8, color='gray')

        peak_vals   = [peak_total.get(cat, 0) for cat in peak_order
                       if peak_total.get(cat, 0) > 0]
        peak_labels = [cat for cat in peak_order if peak_total.get(cat, 0) > 0]
        peak_colors_list = [peak_colors.get(cat, '#c7c7c7') for cat in peak_labels]
        total_peak = sum(peak_vals)

        ax3_inset = ax3.inset_axes([0.58, 0.33, 0.40, 0.45])
        _, _, autotexts3i = ax3_inset.pie(
            peak_vals, labels=None, colors=peak_colors_list,
            autopct=lambda p: f'{p:.0f}%' if p > 5 else '',
            pctdistance=0.75, startangle=90,
            wedgeprops=dict(width=0.45, edgecolor='white', linewidth=0.5)
        )
        for autotext in autotexts3i:
            autotext.set_fontsize(7); autotext.set_color('white'); autotext.set_fontweight('bold')
        ax3_inset.text(0, 0.05, f'{total_peak}', ha='center', va='center',
                       fontsize=12, fontweight='bold', color='black')
        ax3_inset.text(0, -0.18, 'Participants', ha='center', va='center',
                       fontsize=6, fontweight='normal', color='#666666')
        ax3_inset.set_title('Overall', fontsize=8, fontweight='bold', pad=2)

        ax3.legend(loc='lower right', fontsize=8 * legend_scale, title='Response',
                   title_fontsize=9 * legend_scale, framealpha=0.95,
                   bbox_to_anchor=(0.99, 0.01))

    # Main title
    _suptitle = ('Stakeholder Perception by City: Warming, Diurnal Heating & Peak Season'
                 if _three else
                 'Stakeholder Perception by City: Warming & Diurnal Heating')
    fig.suptitle(_suptitle, fontsize=13, fontweight='bold', y=0.98)

    plt.tight_layout(rect=[0, 0, 1, 0.94])
    
    # =========================================================================
    # SEPARATE DONUTS FIGURE (for standalone use)
    # =========================================================================
    # Assemble one donut spec per response question (2 or 3 depending on mode)
    _donut_specs = [
        (warming_vals, warming_colors_list, warming_labels, total_warming,
         'A) Overall Warming Perception\n(Has city warmed in 10 years)'),
        (diurnal_vals, diurnal_colors_list, diurnal_labels, total_diurnal,
         'B) Overall Diurnal Heating Pattern\n(When is heat most severe)'),
    ]
    if _three:
        _donut_specs.append(
            (peak_vals, peak_colors_list, peak_labels, total_peak,
             'C) Overall Peak Heat Season\n(Hottest time of year)')
        )

    _nd = len(_donut_specs)
    fig2, _axd = plt.subplots(1, _nd, figsize=(6 * _nd, 5))
    if _nd == 1:
        _axd = [_axd]

    for _axi, (_vals, _cols, _lbls, _tot, _title) in zip(_axd, _donut_specs):
        _wedges, _, _autot = _axi.pie(
            _vals, labels=None, colors=_cols,
            autopct=lambda p: f'{p:.1f}%' if p > 3 else '',
            pctdistance=0.75, startangle=90,
            wedgeprops=dict(width=0.5, edgecolor='white')
        )
        for _at in _autot:
            _at.set_fontsize(10); _at.set_color('white'); _at.set_fontweight('bold')
        _axi.text(0, 0.06, f'{_tot}', ha='center', va='center',
                  fontsize=18, fontweight='bold', color='black')
        _axi.text(0, -0.15, 'Participants', ha='center', va='center',
                  fontsize=9, fontweight='normal', color='#666666')
        _axi.set_title(_title, fontsize=11, fontweight='bold')
        _axi.legend(_wedges, _lbls, loc='center left', bbox_to_anchor=(1.0, 0.5),
                    fontsize=9 * legend_scale, title='Response',
                    title_fontsize=10 * legend_scale)

    fig2.suptitle('Stakeholder Perception: Overall Summaries\n(Workshop Participants, Unique Responses)',
                  fontsize=13, fontweight='bold', y=1.02)
    plt.tight_layout()
    
    print(" Perception charts created successfully!")
    print(f"   - Main chart with embedded donuts")
    print(f"   - Separate standalone donut chart")

    return fig, fig2


# =============================================================================
# CLUSTER-LEVEL STAKEHOLDER FUNCTIONS
# (aggregate city-level results to climate-cluster level)
# =============================================================================

def create_cluster_stakeholder_map(
    cluster_summary,
    cluster_workshop_prof,
    boundary_gdf,
    cities_gdf,
    cluster25_colors=None,
    profession_colors=None,
    show_map_panel=True,
    figsize=(11.7, 5.85)
):
    """
    Cluster-level stakeholder distribution: optional Nigeria map (cities coloured by
    cluster) + stacked horizontal bar chart of workshop attendees by profession per cluster.

    Parameters
    ----------
    cluster_summary : DataFrame
        Columns: Cluster25, n_cities, cities_with_reg, cities_with_att,
                 registered_count, attended_count
    cluster_workshop_prof : DataFrame
        Columns: Cluster25, profession, count
    boundary_gdf : GeoDataFrame
        Nigeria national boundary polygon
    cities_gdf : GeoDataFrame
        Target city points; must have 'Cluster25' column for colour coding
    cluster25_colors : dict, optional
        {cluster_id: hex_color}; falls back to tab10 if None
    profession_colors : dict, optional
        {profession_name: hex_color}; falls back to tab20 if None.
        Pass the same dict used in §5A for consistent colours across figures.
    show_map_panel : bool, optional
        When True (default), shows the Nigeria cluster map in the left panel.
        When False, shows only the bar chart (single-panel figure).
    figsize : tuple

    Returns
    -------
    fig : matplotlib.figure.Figure
    """
    import matplotlib.patches as mpatches
    from matplotlib.lines import Line2D as _SLn

    all_clusters = sorted(cluster_summary['Cluster25'].unique())
    if cluster25_colors is None:
        cmap = plt.get_cmap('tab10')
        cluster25_colors = {c: cmap(i / max(len(all_clusters) - 1, 1))
                            for i, c in enumerate(all_clusters)}

    fig = plt.figure(figsize=figsize)
    if show_map_panel:
        gs = GridSpec(1, 2, figure=fig, width_ratios=[0.55, 0.45], wspace=0.28)
        ax_map = fig.add_subplot(gs[0])
        ax_bar = fig.add_subplot(gs[1])
    else:
        ax_bar = fig.add_subplot(1, 1, 1)
        ax_map = None

    # =========================================================================
    # MAP PANEL (optional)
    # =========================================================================
    if show_map_panel and ax_map is not None:
        boundary_gdf.plot(ax=ax_map, facecolor='#f5f5f5', edgecolor='#555555',
                          linewidth=0.8)

        if 'Cluster25' in cities_gdf.columns:
            for cluster, grp in cities_gdf.groupby('Cluster25'):
                color = cluster25_colors.get(cluster, '#aaaaaa')
                ax_map.scatter(grp.geometry.x, grp.geometry.y,
                               s=28, color=color, alpha=0.9,
                               edgecolors='white', linewidths=0.4, zorder=3)
        else:
            ax_map.scatter(cities_gdf.geometry.x, cities_gdf.geometry.y,
                           s=20, color='#888888', alpha=0.8, zorder=3)

        ax_map.annotate('', xy=(0.955, 0.920), xytext=(0.955, 0.875),
                        xycoords='axes fraction',
                        arrowprops=dict(arrowstyle='->', lw=1.5, color='black'))
        ax_map.text(0.955, 0.933, 'N', transform=ax_map.transAxes,
                    fontsize=9, fontweight='bold', ha='center', va='bottom')

        sb_x0, sb_x1, sb_y = 0.05, 0.20, 0.05
        ax_map.add_line(_SLn([sb_x0, sb_x1], [sb_y, sb_y],
                             transform=ax_map.transAxes, color='black', lw=1.5))
        for xp in [sb_x0, sb_x1]:
            ax_map.add_line(_SLn([xp, xp], [sb_y - 0.01, sb_y + 0.01],
                                  transform=ax_map.transAxes, color='black', lw=1.0))
        ax_map.text((sb_x0 + sb_x1) / 2, sb_y - 0.025, '~500 km',
                    transform=ax_map.transAxes, fontsize=5.5, ha='center', va='top')

        ax_map.set_xlabel('Longitude (°E)', fontsize=8)
        ax_map.set_ylabel('Latitude (°N)', fontsize=8)
        ax_map.tick_params(labelsize=7)
        ax_map.grid(True, alpha=0.2, linestyle='--', linewidth=0.5)
        ax_map.set_aspect('equal')
        ax_map.set_title('A', fontsize=10, fontweight='bold', pad=8)

        legend_handles = [
            mpatches.Patch(facecolor=cluster25_colors.get(c, '#aaaaaa'),
                           label=f'Cluster {c}', linewidth=0)
            for c in all_clusters
            if c in cluster_summary['Cluster25'].values
        ]
        ax_map.legend(handles=legend_handles, loc='lower right', fontsize=5.5,
                      title='Cluster', title_fontsize=6.5, framealpha=0.92,
                      edgecolor='black', ncol=2)

    # =========================================================================
    # BAR CHART PANEL
    # =========================================================================
    cluster_totals = (cluster_workshop_prof
                      .groupby('Cluster25')['count'].sum()
                      .sort_values(ascending=True))
    cluster_list = cluster_totals.index.tolist()
    professions = sorted(cluster_workshop_prof['profession'].unique())

    data_matrix = pd.DataFrame(0, index=cluster_list, columns=professions)
    for _, row in cluster_workshop_prof.iterrows():
        if row['Cluster25'] in data_matrix.index:
            data_matrix.loc[row['Cluster25'], row['profession']] = row['count']

    # Use profession_colors when provided, otherwise fall back to tab20
    _bar_fallback = plt.get_cmap('tab20').colors
    left = np.zeros(len(cluster_list))
    for pi, prof in enumerate(professions):
        vals = data_matrix[prof].values
        if vals.sum() > 0:
            if profession_colors is not None and prof in profession_colors:
                bar_color = profession_colors[prof]
            else:
                bar_color = _bar_fallback[pi % len(_bar_fallback)]
            ax_bar.barh([f'Cluster {c}' for c in cluster_list], vals, left=left,
                        color=bar_color, edgecolor='white', linewidth=0.5, label=prof)
            left += vals

    for i, cl in enumerate(cluster_list):
        total = cluster_totals[cl]
        if total > 0:
            ax_bar.text(total + 0.2, i, f'{int(total)}',
                        va='center', ha='left', fontsize=6.5, fontweight='bold')

    ax_bar.set_xlabel('Workshop Attendees', fontsize=8)
    bar_title = 'B' if show_map_panel else 'Workshop Attendees by Profession per Cluster'
    ax_bar.set_title(bar_title, fontsize=10, fontweight='bold', pad=8)
    ax_bar.tick_params(axis='both', labelsize=7)
    ax_bar.grid(axis='x', alpha=0.3, linestyle='--', linewidth=0.5)
    handles, labels = ax_bar.get_legend_handles_labels()
    if handles:
        ax_bar.legend(handles, labels, loc='lower right', fontsize=5,
                      title='Profession', title_fontsize=6,
                      framealpha=0.95, edgecolor='black', ncol=1)

    fig.suptitle(
        f'Stakeholder Distribution by Climate Cluster ({config.PROJECT_STUDY_YEAR})',
        fontsize=11, fontweight='bold', y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.96])

    print("✅ Cluster stakeholder map created!")
    return fig


def create_cluster_classification_donut(
    cluster_summary,
    cluster25_colors=None,
    figsize=(8, 8),
    title=None
):
    """
    3-ring donut showing cluster-level city engagement funnel.

    Ring 1 (inner):  N target cities per cluster (coloured by cluster)
    Ring 2 (middle): Cities with ≥1 registered stakeholder vs. none
    Ring 3 (outer):  Cities with ≥1 workshop attendee vs. not attended
                     (N/A segment where no registration exists)

    Parameters
    ----------
    cluster_summary : DataFrame
        Columns: Cluster25, n_cities, cities_with_reg, cities_with_att
    cluster25_colors : dict, optional
    figsize : tuple
    title : str, optional

    Returns
    -------
    fig : matplotlib.figure.Figure
    """
    import matplotlib.patches as mpatches

    clusters = cluster_summary['Cluster25'].tolist()
    if cluster25_colors is None:
        cmap = plt.get_cmap('tab10')
        cluster25_colors = {c: cmap(i / max(len(clusters) - 1, 1))
                            for i, c in enumerate(clusters)}

    total_cities = int(cluster_summary['n_cities'].sum())

    ring1_sizes, ring1_colors, ring1_labels = [], [], []
    ring2_sizes, ring2_colors, ring2_labels = [], [], []
    ring3_sizes, ring3_colors, ring3_labels = [], [], []

    for _, row in cluster_summary.iterrows():
        cl = row['Cluster25']
        n = int(row['n_cities'])
        with_reg = int(row['cities_with_reg'])
        no_reg = n - with_reg
        with_att = int(row['cities_with_att'])
        reg_no_att = with_reg - with_att

        base = cluster25_colors.get(cl, '#aaaaaa')

        ring1_sizes.append(n)
        ring1_colors.append(base)
        ring1_labels.append(str(cl))

        ring2_sizes += [with_reg, no_reg]
        ring2_colors += [base, '#d5d8dc']
        ring2_labels += ['Reg.', 'No Reg.']

        ring3_sizes += [with_att, reg_no_att, no_reg]
        ring3_colors += [base, '#aaaaaa', '#e8e8e8']
        ring3_labels += ['Attended', 'Not Att.', 'N/A']

    fig, ax = plt.subplots(figsize=figsize, subplot_kw=dict(aspect='equal'))

    wedges_r1, _ = ax.pie(
        ring1_sizes, radius=0.50, colors=ring1_colors,
        labels=None, startangle=90,
        wedgeprops=dict(width=0.15, edgecolor='white', linewidth=2.0))
    for wedge, label, count in zip(wedges_r1, ring1_labels, ring1_sizes):
        ang = (wedge.theta2 + wedge.theta1) / 2
        x = 0.425 * np.cos(np.deg2rad(ang))
        y = 0.425 * np.sin(np.deg2rad(ang))
        ax.text(x, y, f'{label}\n({count})', ha='center', va='center',
                fontsize=7, fontweight='bold', color='black')

    wedges_r2, _ = ax.pie(
        ring2_sizes, radius=0.65, colors=ring2_colors,
        labels=None, startangle=90,
        wedgeprops=dict(width=0.15, edgecolor='white', linewidth=1.5))
    for wedge, label, count in zip(wedges_r2, ring2_labels, ring2_sizes):
        if count > 0:
            ang = (wedge.theta2 + wedge.theta1) / 2
            x = 0.575 * np.cos(np.deg2rad(ang))
            y = 0.575 * np.sin(np.deg2rad(ang))
            ax.text(x, y, f'{label}\n({count})', ha='center', va='center',
                    fontsize=7, fontweight='normal', color='black')

    wedges_r3, _ = ax.pie(
        ring3_sizes, radius=0.80, colors=ring3_colors,
        labels=None, startangle=90,
        wedgeprops=dict(width=0.15, edgecolor='white', linewidth=1.0))
    for wedge, label, count in zip(wedges_r3, ring3_labels, ring3_sizes):
        if count > 0:
            ang = (wedge.theta2 + wedge.theta1) / 2
            x = 0.90 * np.cos(np.deg2rad(ang))
            y = 0.90 * np.sin(np.deg2rad(ang))
            if label == 'N/A':
                wedge.set_hatch('///')
                wedge.set_edgecolor('grey')
                ax.text(x, y, f'{label}\n({count})', ha='center', va='center',
                        fontsize=7, fontweight='normal', color='black',
                        bbox=dict(boxstyle='round,pad=0.2', facecolor='white',
                                  edgecolor='grey', alpha=0.8))
            else:
                ax.text(x, y, f'{label}\n({count})', ha='center', va='center',
                        fontsize=7, fontweight='normal', color='black')

    centre_circle = plt.Circle((0, 0), 0.35, fc='white', linewidth=0)
    ax.add_artist(centre_circle)
    ax.text(0, 0.08, f'{total_cities}', ha='center', va='center',
            fontsize=28, fontweight='bold', color='black')
    ax.text(0, -0.06, 'Target Cities', ha='center', va='center',
            fontsize=12, fontweight='normal', color='black')
    ax.text(0, -0.16, 'across clusters', ha='center', va='center',
            fontsize=9, fontweight='normal', color='#666666')
    ax.axis('equal')

    if title is None:
        title = (f'Cluster Engagement Funnel: Registration & Attendance '
                 f'({config.PROJECT_STUDY_YEAR})')
    fig.suptitle(title, fontsize=13, fontweight='bold', y=0.98)

    legend_elements = [
        mpatches.Patch(facecolor='white', edgecolor='black', linewidth=1,
                       label='Ring 1: Target cities per climate cluster'),
        mpatches.Patch(facecolor='white', edgecolor='black', linewidth=1,
                       label='Ring 2: Cities with registered stakeholders'),
        mpatches.Patch(facecolor='white', edgecolor='black', linewidth=1,
                       label='Ring 3: Cities with workshop attendees'),
        mpatches.Patch(facecolor='#e8e8e8', edgecolor='grey', hatch='///',
                       label='N/A: no registered stakeholders'),
    ]
    ax.legend(handles=legend_elements, loc='upper center', fontsize=7.5,
              frameon=True, facecolor='white', edgecolor='black',
              framealpha=0.9, bbox_to_anchor=(0.5, -0.08), ncol=2)

    plt.tight_layout()
    print("✅ Cluster classification donut created!")
    return fig


def create_cluster_perception_chart(
    warming_by_cluster,
    diurnal_by_cluster,
    warming_total,
    diurnal_total,
    cluster25_colors=None,
    figsize=(14, 5.5),
    legend_scale=1.0,
    peak_by_cluster=None,
    peak_total=None,
    suptitle=True,
    stacked=False,
    row_label='Cluster {}',
    panel_letters=('A)', 'B)', 'C)'),
):
    """
    Cluster-level perception analysis: warming (Q61) + diurnal heat (Q60) stacked bars
    with embedded overall donut insets.

    Mirrors create_perception_chart_with_donuts but rows = climate clusters.

    Parameters
    ----------
    warming_by_cluster : DataFrame
        crosstab(Cluster25, '61_temp_increase_10yrs')
    diurnal_by_cluster : DataFrame
        crosstab(Cluster25, '60_diurnal_severity_heat')
    warming_total : Series
        Overall warming response counts
    diurnal_total : Series
        Overall diurnal response counts
    cluster25_colors : dict, optional
        {cluster_id: hex_color}; used for y-tick label colouring
    figsize : tuple
    legend_scale : float
    row_label : str
        Row label for a cluster index, e.g. 'C{}' for "C13".
    panel_letters : tuple of str
        The letters before the three panel titles, e.g. ('(a)', '(b)', '(c)').

    Returns
    -------
    fig : matplotlib.figure.Figure
    fig2 : matplotlib.figure.Figure  (standalone donut summary)
    """
    warming_colors = {
        'Yes': '#d62728',
        'No': '#2ca02c',
        "I'm not sure": '#7f7f7f',
        "I'd rather not say": '#c7c7c7',
    }
    diurnal_colors = {
        'During the day': '#ff7f0e',
        'At night': '#1f77b4',
        'Both': '#9467bd',
        "I'd rather not say": '#c7c7c7',
    }
    peak_colors = {
        'December – February': '#4e79a7',
        'March – May':         '#d62728',
        'June – August':       '#2ca02c',
        'September – November': '#ff7f0e',
        'I am not sure':            '#7f7f7f',
        "I'd rather not say":       '#c7c7c7',
    }

    warming_order  = ['Yes', 'No', "I'm not sure", "I'd rather not say"]
    diurnal_order  = ['During the day', 'At night', 'Both', "I'd rather not say"]
    peak_order     = ['December – February', 'March – May',
                      'June – August', 'September – November',
                      'I am not sure', "I'd rather not say"]

    warming_cols = [c for c in warming_order if c in warming_by_cluster.columns]
    diurnal_cols = [c for c in diurnal_order if c in diurnal_by_cluster.columns]

    warming_data = warming_by_cluster[warming_cols].fillna(0)
    diurnal_data = diurnal_by_cluster[diurnal_cols].fillna(0)

    _three = peak_by_cluster is not None and peak_total is not None
    if _three:
        peak_cols = [c for c in peak_order if c in peak_by_cluster.columns]
        peak_data = peak_by_cluster[peak_cols].fillna(0)

    cluster_labels = [row_label.format(c) for c in warming_data.index]

    # =========================================================================
    # MAIN FIGURE
    # =========================================================================
    fig = plt.figure(figsize=figsize)
    _ncol = 3 if _three else 2
    # stacked=True puts the panels in rows instead of columns, so the figure can be
    # built at a single-page print width without squeezing three panels across it.
    # Added for the SCS rebuild; default False is the original side-by-side layout.
    if stacked:
        gs = GridSpec(_ncol, 1, figure=fig, height_ratios=[1] * _ncol, hspace=0.42)
        _slots = [gs[i, 0] for i in range(_ncol)]
    else:
        gs = GridSpec(1, _ncol, figure=fig, width_ratios=[1] * _ncol, wspace=0.08)
        _slots = [gs[0, i] for i in range(_ncol)]
    ax1 = fig.add_subplot(_slots[0])
    ax2 = fig.add_subplot(_slots[1])
    ax3 = fig.add_subplot(_slots[2]) if _three else None

    # --- LEFT: Warming ---
    left = np.zeros(len(warming_data))
    for col in warming_cols:
        values = warming_data[col].values
        ax1.barh(range(len(warming_data)), values, left=left,
                 color=warming_colors.get(col, '#c7c7c7'), label=col, height=0.65)
        left += values

    ax1.set_yticks(range(len(warming_data)))
    ax1.set_yticklabels(cluster_labels, fontsize=9)
    ax1.set_xlabel('Number of Participants', fontsize=10)
    ax1.set_title(f'{panel_letters[0]} City Warming Over 10 Years (by Cluster)',
                  fontsize=11, fontweight='bold', loc='left')
    ax1.invert_yaxis()
    max_w = int(warming_data.sum(axis=1).max()) + 5
    ax1.set_xlim(0, max_w)

    for i, cl in enumerate(warming_data.index):
        total = warming_data.loc[cl].sum()
        ax1.text(total + 0.3, i, f'n={int(total)}', va='center', fontsize=8, color='gray')

    # Donut inset (warming overall)
    warming_vals   = [warming_total.get(cat, 0) for cat in warming_order
                      if warming_total.get(cat, 0) > 0]
    warming_lbls_d = [cat for cat in warming_order if warming_total.get(cat, 0) > 0]
    warming_cols_d = [warming_colors[c] for c in warming_lbls_d]
    total_warming  = sum(warming_vals)

    ax1_ins = ax1.inset_axes([0.58, 0.33, 0.40, 0.45])
    wedges, _, autotexts = ax1_ins.pie(
        warming_vals, labels=None, colors=warming_cols_d,
        autopct=lambda p: f'{p:.0f}%' if p > 5 else '',
        pctdistance=0.75, startangle=90,
        wedgeprops=dict(width=0.45, edgecolor='white', linewidth=0.5))
    for at in autotexts:
        at.set_fontsize(7); at.set_color('white'); at.set_fontweight('bold')
    ax1_ins.text(0, 0.05, f'{total_warming}', ha='center', va='center',
                 fontsize=12, fontweight='bold', color='black')
    ax1_ins.text(0, -0.18, 'Participants', ha='center', va='center',
                 fontsize=6, color='#666666')
    ax1_ins.set_title('Overall', fontsize=8, fontweight='bold', pad=2)

    ax1.legend(loc='lower right', fontsize=8 * legend_scale, title='Response',
               title_fontsize=9 * legend_scale, framealpha=0.95,
               bbox_to_anchor=(0.99, 0.01))

    # --- RIGHT: Diurnal ---
    left = np.zeros(len(diurnal_data))
    for col in diurnal_cols:
        values = diurnal_data[col].values
        ax2.barh(range(len(diurnal_data)), values, left=left,
                 color=diurnal_colors.get(col, '#c7c7c7'), label=col, height=0.65)
        left += values

    ax2.set_yticks(range(len(diurnal_data)))
    ax2.set_yticklabels([])
    ax2.set_xlabel('Number of Participants', fontsize=10)
    ax2.set_title(f'{panel_letters[1]} Timing of Most Severe Heat (by Cluster)',
                  fontsize=11, fontweight='bold', loc='left')
    ax2.invert_yaxis()
    max_d = int(diurnal_data.sum(axis=1).max()) + 5
    ax2.set_xlim(0, max_d)

    for i, cl in enumerate(diurnal_data.index):
        total = diurnal_data.loc[cl].sum()
        ax2.text(total + 0.3, i, f'n={int(total)}', va='center', fontsize=8, color='gray')

    # Donut inset (diurnal overall)
    diurnal_vals   = [diurnal_total.get(cat, 0) for cat in diurnal_order
                      if diurnal_total.get(cat, 0) > 0]
    diurnal_lbls_d = [cat for cat in diurnal_order if diurnal_total.get(cat, 0) > 0]
    diurnal_cols_d = [diurnal_colors[c] for c in diurnal_lbls_d]
    total_diurnal  = sum(diurnal_vals)

    ax2_ins = ax2.inset_axes([0.58, 0.33, 0.40, 0.45])
    wedges2, _, autotexts2 = ax2_ins.pie(
        diurnal_vals, labels=None, colors=diurnal_cols_d,
        autopct=lambda p: f'{p:.0f}%' if p > 5 else '',
        pctdistance=0.75, startangle=90,
        wedgeprops=dict(width=0.45, edgecolor='white', linewidth=0.5))
    for at in autotexts2:
        at.set_fontsize(7); at.set_color('white'); at.set_fontweight('bold')
    ax2_ins.text(0, 0.05, f'{total_diurnal}', ha='center', va='center',
                 fontsize=12, fontweight='bold', color='black')
    ax2_ins.text(0, -0.18, 'Participants', ha='center', va='center',
                 fontsize=6, color='#666666')
    ax2_ins.set_title('Overall', fontsize=8, fontweight='bold', pad=2)

    ax2.legend(loc='lower right', fontsize=8 * legend_scale, title='Response',
               title_fontsize=9 * legend_scale, framealpha=0.95,
               bbox_to_anchor=(0.99, 0.01))

    # --- PANEL C: Peak Season / Month (Q58) ---
    if _three:
        left = np.zeros(len(peak_data))
        for col in peak_cols:
            values = peak_data[col].values
            ax3.barh(range(len(peak_data)), values, left=left,
                     color=peak_colors.get(col, '#c7c7c7'), label=col, height=0.65)
            left += values

        ax3.set_yticks(range(len(peak_data)))
        ax3.set_yticklabels([])
        ax3.set_xlabel('Number of Participants', fontsize=10)
        ax3.set_title(f'{panel_letters[2]} Peak Heat Season (by Cluster)',
                      fontsize=11, fontweight='bold', loc='left')
        ax3.invert_yaxis()
        max_p = int(peak_data.sum(axis=1).max()) + 5
        ax3.set_xlim(0, max_p)

        for i, cl in enumerate(peak_data.index):
            total = peak_data.loc[cl].sum()
            ax3.text(total + 0.3, i, f'n={int(total)}', va='center', fontsize=8, color='gray')

        peak_vals   = [peak_total.get(cat, 0) for cat in peak_order
                       if peak_total.get(cat, 0) > 0]
        peak_lbls_d = [cat for cat in peak_order if peak_total.get(cat, 0) > 0]
        peak_cols_d = [peak_colors.get(c, '#c7c7c7') for c in peak_lbls_d]
        total_peak  = sum(peak_vals)

        ax3_ins = ax3.inset_axes([0.58, 0.33, 0.40, 0.45])
        _, _, autotexts3i = ax3_ins.pie(
            peak_vals, labels=None, colors=peak_cols_d,
            autopct=lambda p: f'{p:.0f}%' if p > 5 else '',
            pctdistance=0.75, startangle=90,
            wedgeprops=dict(width=0.45, edgecolor='white', linewidth=0.5))
        for at in autotexts3i:
            at.set_fontsize(7); at.set_color('white'); at.set_fontweight('bold')
        ax3_ins.text(0, 0.05, f'{total_peak}', ha='center', va='center',
                     fontsize=12, fontweight='bold', color='black')
        ax3_ins.text(0, -0.18, 'Participants', ha='center', va='center',
                     fontsize=6, color='#666666')
        ax3_ins.set_title('Overall', fontsize=8, fontweight='bold', pad=2)

        ax3.legend(loc='lower right', fontsize=8 * legend_scale, title='Response',
                   title_fontsize=9 * legend_scale, framealpha=0.95,
                   bbox_to_anchor=(0.99, 0.01))

    # suptitle=False added for the SCS rebuild, where captions carry the title.
    if suptitle:
        _suptitle = ('Stakeholder Perception by Climate Cluster: '
                     'Warming, Diurnal Heating & Peak Season' if _three else
                     'Stakeholder Perception by Climate Cluster: Warming & Diurnal Heating')
        fig.suptitle(_suptitle, fontsize=13, fontweight='bold', y=0.98)
        plt.tight_layout(rect=[0, 0, 1, 0.94])
    else:
        plt.tight_layout()

    # =========================================================================
    # SEPARATE DONUTS FIGURE (standalone)
    # =========================================================================
    _donut_specs = [
        (warming_vals, warming_cols_d, warming_lbls_d, total_warming,
         'A) Overall Warming Perception\n(Has city warmed in 10 years)'),
        (diurnal_vals, diurnal_cols_d, diurnal_lbls_d, total_diurnal,
         'B) Overall Diurnal Heating Pattern\n(When is heat most severe)'),
    ]
    if _three:
        _donut_specs.append(
            (peak_vals, peak_cols_d, peak_lbls_d, total_peak,
             'C) Overall Peak Heat Season\n(Hottest time of year)')
        )

    _nd = len(_donut_specs)
    fig2, _axd = plt.subplots(1, _nd, figsize=(6 * _nd, 5))
    if _nd == 1:
        _axd = [_axd]

    for _axi, (_vals, _cols, _lbls, _tot, _title) in zip(_axd, _donut_specs):
        _wedges, _, _autot = _axi.pie(
            _vals, labels=None, colors=_cols,
            autopct=lambda p: f'{p:.1f}%' if p > 3 else '',
            pctdistance=0.75, startangle=90,
            wedgeprops=dict(width=0.5, edgecolor='white'))
        for _at in _autot:
            _at.set_fontsize(10); _at.set_color('white'); _at.set_fontweight('bold')
        _axi.text(0, 0.06, f'{_tot}', ha='center', va='center',
                  fontsize=18, fontweight='bold', color='black')
        _axi.text(0, -0.15, 'Participants', ha='center', va='center',
                  fontsize=9, color='#666666')
        _axi.set_title(_title, fontsize=11, fontweight='bold')
        _axi.legend(_wedges, _lbls, loc='center left', bbox_to_anchor=(1.0, 0.5),
                    fontsize=9 * legend_scale, title='Response',
                    title_fontsize=10 * legend_scale)

    fig2.suptitle(
        'Stakeholder Perception: Overall Summaries (Cluster Aggregation)',
        fontsize=13, fontweight='bold', y=1.02)
    plt.tight_layout()

    print("✅ Cluster perception charts created!")
    print("   - Main chart with embedded donuts (by cluster)")
    print("   - Separate standalone donut chart")

    return fig, fig2


def create_national_perception_donuts(
    warming_total,
    diurnal_total,
    peak_total,
    legend_scale: float = 1.2,
    figsize: tuple = None,
    title: str = 'National Stakeholder Perception: Overall Summaries',
):
    """
    National-level perception summary: three large donuts (Warming · Diurnal ·
    Peak Season) side-by-side, pooling every participant.

    Uses the identical colour logic, seasonal ordering and "not sure / rather
    not say" handling as create_perception_chart_with_donuts (city) and
    create_cluster_perception_chart (cluster), so all three levels match.

    Parameters
    ----------
    warming_total, diurnal_total, peak_total : pd.Series
        Overall response counts (index = response category) for Q61 / Q60 / Q58.
    legend_scale : float
    figsize : tuple, optional
        Defaults to (18, 5) — three donuts.
    title : str

    Returns
    -------
    fig : matplotlib.figure.Figure
    """
    warming_colors = {
        'Yes': '#d62728', 'No': '#2ca02c',
        "I'm not sure": '#7f7f7f', "I'd rather not say": '#c7c7c7',
    }
    diurnal_colors = {
        'During the day': '#ff7f0e', 'At night': '#1f77b4',
        'Both': '#9467bd', "I'd rather not say": '#c7c7c7',
    }
    peak_colors = {
        'December – February': '#4e79a7', 'March – May': '#d62728',
        'June – August': '#2ca02c', 'September – November': '#ff7f0e',
        'I am not sure': '#7f7f7f', "I'd rather not say": '#c7c7c7',
    }
    warming_order = ['Yes', 'No', "I'm not sure", "I'd rather not say"]
    diurnal_order = ['During the day', 'At night', 'Both', "I'd rather not say"]
    peak_order    = ['December – February', 'March – May', 'June – August',
                     'September – November', 'I am not sure', "I'd rather not say"]

    specs = [
        (warming_total, warming_order, warming_colors,
         'A) Overall Warming Perception\n(Has city warmed in 10 years)'),
        (diurnal_total, diurnal_order, diurnal_colors,
         'B) Overall Diurnal Heating Pattern\n(When is heat most severe)'),
        (peak_total, peak_order, peak_colors,
         'C) Overall Peak Heat Season\n(Hottest time of year)'),
    ]

    if figsize is None:
        figsize = (18, 5)
    fig, axes = plt.subplots(1, 3, figsize=figsize)

    for ax, (total, order, cmap, panel_title) in zip(axes, specs):
        vals   = [total.get(cat, 0) for cat in order if total.get(cat, 0) > 0]
        labels = [cat for cat in order if total.get(cat, 0) > 0]
        colors = [cmap.get(c, '#c7c7c7') for c in labels]
        grand  = sum(vals)

        wedges, _, autot = ax.pie(
            vals, labels=None, colors=colors,
            autopct=lambda p: f'{p:.1f}%' if p > 3 else '',
            pctdistance=0.75, startangle=90,
            wedgeprops=dict(width=0.5, edgecolor='white'))
        for at in autot:
            at.set_fontsize(10); at.set_color('white'); at.set_fontweight('bold')
        ax.text(0, 0.06, f'{grand}', ha='center', va='center',
                fontsize=18, fontweight='bold', color='black')
        ax.text(0, -0.15, 'Participants', ha='center', va='center',
                fontsize=9, color='#666666')
        ax.set_title(panel_title, fontsize=11, fontweight='bold')
        ax.legend(wedges, labels, loc='center left', bbox_to_anchor=(1.0, 0.5),
                  fontsize=9 * legend_scale, title='Response',
                  title_fontsize=10 * legend_scale)

    fig.suptitle(title, fontsize=13, fontweight='bold', y=1.02)
    plt.tight_layout()

    print("✅ National perception donuts created (warming · diurnal · peak season)")
    return fig


def create_persistent_heat_event_summary_chart(cities_data, base_dir=None, study_year=2024, dpi=300):
    """
    Create summary chart of mean LST during persistent heat events across cities.
    
    Shows grouped bars for day (left) and night (right) with:
    - Base colors: Orange (day), Grey (night)
    - Red tips for values exceeding overall mean (danger zone)
    - Black range indicators showing min-max variability
    - Cities sorted from hottest to coolest
    
    Parameters
    ----------
    cities_data : dict
        Dictionary of city data from load_seviri_cities_lst()
        Format: {city_name: {'day': {...}, 'night': {...}, 'day_file': ..., 'night_file': ...}}
    base_dir : str or Path, optional
        Output directory for saving figures
    study_year : int, optional
        Study year for labeling (default: 2024)
    dpi : int, optional
        Figure DPI (default: 300)
    
    Returns
    -------
    matplotlib.figure.Figure
        The created figure
    
    Examples
    --------
    >>> fig = create_persistent_heat_event_summary_chart(cities_data, 
    ...                                                   base_dir='outputs', 
    ...                                                   study_year=2024)
    """
    import matplotlib.pyplot as plt
    import numpy as np
    from pathlib import Path
    import rasterio
    
    # Extract mean LST for each city from their persistent heat event files
    summary_data = []
    
    for city_name, city_data in sorted(cities_data.items()):
        row = {'city': city_name}
        
        for period in ['day', 'night']:
            if period in city_data and f'{period}_file' in city_data:
                lst_file = city_data[f'{period}_file']
                
                if lst_file and Path(lst_file).exists():
                    try:
                        # Read LST and calculate mean, min, max
                        with rasterio.open(lst_file) as src:
                            data = src.read(1)
                            data_valid = data[~np.isnan(data)]
                            
                            if len(data_valid) > 0:
                                row[f'{period}_mean'] = np.mean(data_valid)
                                row[f'{period}_min'] = np.min(data_valid)
                                row[f'{period}_max'] = np.max(data_valid)
                                row[f'{period}_event'] = city_data.get(f'{period}_event', 'N/A')
                                row[f'{period}_duration'] = city_data.get(f'{period}_duration', 0)
                            else:
                                row[f'{period}_mean'] = np.nan
                                row[f'{period}_min'] = np.nan
                                row[f'{period}_max'] = np.nan
                    except Exception as e:
                        print(f"Warning: Could not read {period} LST for {city_name}: {e}")
                        row[f'{period}_mean'] = np.nan
                        row[f'{period}_min'] = np.nan
                        row[f'{period}_max'] = np.nan
                else:
                    row[f'{period}_mean'] = np.nan
                    row[f'{period}_min'] = np.nan
                    row[f'{period}_max'] = np.nan
            else:
                row[f'{period}_mean'] = np.nan
                row[f'{period}_min'] = np.nan
                row[f'{period}_max'] = np.nan
        
        summary_data.append(row)
    
    # Sort cities by combined day+night mean (hottest first)
    summary_data_sorted = sorted(summary_data, 
                                 key=lambda x: (x.get('day_mean', 0) if not np.isnan(x.get('day_mean', np.nan)) else 0) + 
                                              (x.get('night_mean', 0) if not np.isnan(x.get('night_mean', np.nan)) else 0),
                                 reverse=True)
    
    # Convert to arrays for plotting
    cities = [row['city'] for row in summary_data_sorted]
    day_means = np.array([row.get('day_mean', np.nan) for row in summary_data_sorted])
    day_mins = np.array([row.get('day_min', np.nan) for row in summary_data_sorted])
    day_maxs = np.array([row.get('day_max', np.nan) for row in summary_data_sorted])
    night_means = np.array([row.get('night_mean', np.nan) for row in summary_data_sorted])
    night_mins = np.array([row.get('night_min', np.nan) for row in summary_data_sorted])
    night_maxs = np.array([row.get('night_max', np.nan) for row in summary_data_sorted])
    
    # Calculate overall statistics (excluding NaN)
    day_valid = day_means[~np.isnan(day_means)]
    night_valid = night_means[~np.isnan(night_means)]
    
    if len(day_valid) == 0 and len(night_valid) == 0:
        print("  No valid data for summary chart")
        return None
    
    day_overall_mean = np.mean(day_valid) if len(day_valid) > 0 else np.nan
    day_overall_std = np.std(day_valid) if len(day_valid) > 0 else np.nan
    
    night_overall_mean = np.mean(night_valid) if len(night_valid) > 0 else np.nan
    night_overall_std = np.std(night_valid) if len(night_valid) > 0 else np.nan
    
    print(f"\n{'='*80}")
    print(f"PERSISTENT HEAT EVENT SUMMARY STATISTICS - {study_year}")
    print(f"{'='*80}")
    print(f"Daytime LST:  Mean = {day_overall_mean:.1f}°C, Std = {day_overall_std:.1f}°C")
    print(f"Nighttime LST: Mean = {night_overall_mean:.1f}°C, Std = {night_overall_std:.1f}°C")
    
    # Count cities exceeding mean
    day_above_mean = np.sum((day_means > day_overall_mean) & ~np.isnan(day_means))
    night_above_mean = np.sum((night_means > night_overall_mean) & ~np.isnan(night_means))
    
    print(f"\nCities Above Mean (Danger Zone):")
    print(f"  Day:   {day_above_mean}/{len(day_valid)} cities ({day_above_mean/len(day_valid)*100:.1f}%)")
    print(f"  Night: {night_above_mean}/{len(night_valid)} cities ({night_above_mean/len(night_valid)*100:.1f}%)")
    print(f"\nCities sorted from hottest to coolest (by combined day+night mean)")
    print(f"{'='*80}\n")
    
    # Create figure with single subplot for horizontal grouped bars
    n_cities = len(cities)
    
    # Get dynamic layout parameters
    layout = _get_chart_layout_params(n_cities)
    figsize = layout['figsize']
    width = layout['width']
    fontsize_labels = layout['fontsize_labels']
    
    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    
    y = np.arange(n_cities)
    
    # Colors
    day_base_color = '#FFB366'  # Light orange for day base
    night_base_color = '#696969'  # Dark grey for night base
    danger_color = '#FF0000'  # Red for exceeding portion (tip)
    range_color = '#000000'  # Black for all range indicators
    
    # Process day and night data — horizontal bars
    for i, city in enumerate(cities):
        day_val = day_means[i]
        day_min = day_mins[i]
        day_max = day_maxs[i]
        night_val = night_means[i]
        night_min = night_mins[i]
        night_max = night_maxs[i]
        
        # --- DAY BAR (top of pair) ---
        if not np.isnan(day_val):
            if day_val > day_overall_mean:
                base_width_val = day_overall_mean
                exceed_width_val = day_val - day_overall_mean
            else:
                base_width_val = day_val
                exceed_width_val = 0
            
            ax.barh(y[i] - width/2, base_width_val, width,
                    color=day_base_color, edgecolor='black', linewidth=1)
            
            if exceed_width_val > 0:
                ax.barh(y[i] - width/2, exceed_width_val, width,
                        left=base_width_val, color=danger_color,
                        edgecolor='black', linewidth=1)
            
            # Range indicator (min to max) — horizontal
            if not np.isnan(day_min) and not np.isnan(day_max):
                ax.plot([day_min, day_max], [y[i] - width/2, y[i] - width/2],
                        color=range_color, linewidth=3, alpha=0.6, zorder=2)
                cap_h = width * 0.3
                ax.plot([day_min, day_min],
                        [y[i] - width/2 - cap_h/2, y[i] - width/2 + cap_h/2],
                        color=range_color, linewidth=2, alpha=0.6)
                ax.plot([day_max, day_max],
                        [y[i] - width/2 - cap_h/2, y[i] - width/2 + cap_h/2],
                        color=range_color, linewidth=2, alpha=0.6)
            
            # Value label inside bar
            ax.text(day_val / 2, y[i] - width/2, f'{day_val:.1f}',
                    ha='center', va='center', fontsize=fontsize_labels,
                    fontweight='bold', color='white',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='black',
                              alpha=0.7))
        
        # --- NIGHT BAR (bottom of pair) ---
        if not np.isnan(night_val):
            if night_val > night_overall_mean:
                base_width_val = night_overall_mean
                exceed_width_val = night_val - night_overall_mean
            else:
                base_width_val = night_val
                exceed_width_val = 0
            
            ax.barh(y[i] + width/2, base_width_val, width,
                    color=night_base_color, edgecolor='black', linewidth=1)
            
            if exceed_width_val > 0:
                ax.barh(y[i] + width/2, exceed_width_val, width,
                        left=base_width_val, color=danger_color,
                        edgecolor='black', linewidth=1)
            
            if not np.isnan(night_min) and not np.isnan(night_max):
                ax.plot([night_min, night_max], [y[i] + width/2, y[i] + width/2],
                        color=range_color, linewidth=3, alpha=0.6, zorder=2)
                cap_h = width * 0.3
                ax.plot([night_min, night_min],
                        [y[i] + width/2 - cap_h/2, y[i] + width/2 + cap_h/2],
                        color=range_color, linewidth=2, alpha=0.6)
                ax.plot([night_max, night_max],
                        [y[i] + width/2 - cap_h/2, y[i] + width/2 + cap_h/2],
                        color=range_color, linewidth=2, alpha=0.6)
            
            ax.text(night_val / 2, y[i] + width/2, f'{night_val:.1f}',
                    ha='center', va='center', fontsize=fontsize_labels,
                    fontweight='bold', color='white',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='black',
                              alpha=0.7))
    
    # Add mean lines (now vertical) with labels
    if not np.isnan(day_overall_mean):
        ax.axvline(day_overall_mean, color='darkorange', linestyle='--',
                   linewidth=2.5, alpha=0.8, zorder=3)
        ax.text(day_overall_mean + 0.3, n_cities - 0.3,
                f'Day Mean: {day_overall_mean:.1f}°C',
                fontsize=9, fontweight='bold', color='darkorange',
                bbox=dict(boxstyle='round,pad=0.4', facecolor='white',
                          edgecolor='darkorange', alpha=0.9),
                ha='left', va='top')
    
    if not np.isnan(night_overall_mean):
        ax.axvline(night_overall_mean, color='dimgray', linestyle='--',
                   linewidth=2.5, alpha=0.8, zorder=3)
        ax.text(night_overall_mean + 0.3, 0.3,
                f'Night Mean: {night_overall_mean:.1f}°C',
                fontsize=9, fontweight='bold', color='dimgray',
                bbox=dict(boxstyle='round,pad=0.4', facecolor='white',
                          edgecolor='dimgray', alpha=0.9),
                ha='left', va='bottom')
    
    # Horizontal separator lines between cities
    for i in range(1, n_cities):
        ax.axhline(y[i] - 0.5, color='lightgrey', linestyle='-',
                   linewidth=1, alpha=0.3, zorder=0)
    
    # Formatting — axes swapped for horizontal layout
    ax.set_ylabel('Cities (sorted hottest → coolest)', fontsize=13,
                  fontweight='bold')
    ax.set_xlabel('Mean LST (°C)', fontsize=13, fontweight='bold')
    ax.set_title(
        f'Persistent Heat Event Comparison: Day vs Night - {study_year}\n'
        f'Red tips indicate temperatures exceeding overall mean (Danger Zone)',
        fontsize=14, fontweight='bold', pad=20)
    ax.set_yticks(y)
    ax.set_yticklabels(cities, fontsize=10)
    ax.invert_yaxis()  # hottest at top
    ax.grid(axis='x', alpha=0.3, linestyle='--', zorder=0)
    
    # Create custom legend
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D
    
    legend_elements = [
        Patch(facecolor=day_base_color, edgecolor='black', label='Day Base'),
        Patch(facecolor=night_base_color, edgecolor='black', label='Night Base'),
        Patch(facecolor=danger_color, edgecolor='black',
              label='Excess Above Mean (Red Tip)'),
        Line2D([0], [0], color=range_color, linewidth=4, alpha=0.6,
               label='Range (Min-Max)'),
    ]
    
    ax.legend(handles=legend_elements, loc='lower right', fontsize=9,
              framealpha=0.95, edgecolor='black', fancybox=True, ncol=2)
    
    plt.tight_layout()
    
    # Save figure
    if base_dir:
        output_dir = Path(base_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        png_path = output_dir / f'Persistent_Heat_Event_Summary_{study_year}.png'
        pdf_path = output_dir / f'Persistent_Heat_Event_Summary_{study_year}.pdf'
        
        fig.savefig(png_path, dpi=dpi, bbox_inches='tight',
                   facecolor='white', pad_inches=0.1)
        fig.savefig(pdf_path, format='pdf', bbox_inches='tight',
                   facecolor='white', pad_inches=0.1)
        
        print(f" Saved: {png_path.name}")
        print(f" Saved: {pdf_path.name}")
        print(f"{'='*80}\n")
    
    return fig


def _get_chart_layout_params(n_cities):
    """
    Get dynamic layout parameters based on number of cities.
    
    Helper function to maintain consistent sizing across heat event charts.
    Charts use **horizontal bars** (cities on the y-axis) so the figure grows
    vertically with more cities.
    
    Parameters
    ----------
    n_cities : int
        Number of cities to plot
    
    Returns
    -------
    dict
        Dictionary with 'figsize', 'width', and 'fontsize_labels' keys
    """
    if n_cities <= 10:
        return {'figsize': (14, 8), 'width': 0.38, 'fontsize_labels': 8}
    elif n_cities <= 20:
        return {'figsize': (14, 14), 'width': 0.35, 'fontsize_labels': 7}
    elif n_cities <= 30:
        return {'figsize': (14, 20), 'width': 0.32, 'fontsize_labels': 7}
    else:  # Up to 50+ cities
        return {'figsize': (14, 28), 'width': 0.28, 'fontsize_labels': 6}


def create_persistent_heat_event_variability_chart(cities_data, base_dir=None, study_year=2024, dpi=300):
    """
    Create variability chart showing standard deviation of LST during persistent heat events.
    
    Shows grouped bars for day (left) and night (right) with:
    - Base colors: Orange (day), Grey (night) for normal variability
    - Red tips for SD values exceeding overall mean SD (high variability zones)
    - Cities sorted from highest to lowest variability
    
    Parameters
    ----------
    cities_data : dict
        Dictionary of city data from load_seviri_cities_lst()
        Format: {city_name: {'day': {...}, 'night': {...}, 'day_file': ..., 'night_file': ...}}
    base_dir : str or Path, optional
        Output directory for saving figures
    study_year : int, optional
        Study year for labeling (default: 2024)
    dpi : int, optional
        Figure DPI (default: 300)
    
    Returns
    -------
    matplotlib.figure.Figure
        The created figure
    
    Examples
    --------
    >>> fig = create_persistent_heat_event_variability_chart(cities_data, 
    ...                                                       base_dir='outputs', 
    ...                                                       study_year=2024)
    """
    import matplotlib.pyplot as plt
    import numpy as np
    from pathlib import Path
    import rasterio
    from matplotlib.patches import Patch
    
    # Extract SD for each city from their persistent heat event files
    sd_data = []
    
    for city_name, city_data in sorted(cities_data.items()):
        row = {'city': city_name}
        
        for period in ['day', 'night']:
            if period in city_data and f'{period}_file' in city_data:
                lst_file = city_data[f'{period}_file']
                
                if lst_file and Path(lst_file).exists():
                    try:
                        # Read LST and calculate standard deviation
                        with rasterio.open(lst_file) as src:
                            data = src.read(1)
                            data_valid = data[~np.isnan(data)]
                            
                            if len(data_valid) > 0:
                                row[f'{period}_std'] = np.std(data_valid)
                            else:
                                row[f'{period}_std'] = np.nan
                    except Exception as e:
                        print(f"Warning: Could not read {period} LST for {city_name}: {e}")
                        row[f'{period}_std'] = np.nan
                else:
                    row[f'{period}_std'] = np.nan
            else:
                row[f'{period}_std'] = np.nan
        
        sd_data.append(row)
    
    # Sort cities by highest combined variability (day + night SD)
    sd_data_sorted = sorted(sd_data, 
                            key=lambda x: x.get('day_std', 0) if not np.isnan(x.get('day_std', np.nan)) else 0,
                            reverse=True)
    
    # Convert to arrays for plotting
    cities = [row['city'] for row in sd_data_sorted]
    day_stds = np.array([row.get('day_std', np.nan) for row in sd_data_sorted])
    night_stds = np.array([row.get('night_std', np.nan) for row in sd_data_sorted])
    
    # Calculate overall statistics (excluding NaN)
    day_valid_std = day_stds[~np.isnan(day_stds)]
    night_valid_std = night_stds[~np.isnan(night_stds)]
    
    if len(day_valid_std) == 0 and len(night_valid_std) == 0:
        print("  No valid data for SD variability chart")
        return None
    
    day_mean_std = np.mean(day_valid_std) if len(day_valid_std) > 0 else np.nan
    night_mean_std = np.mean(night_valid_std) if len(night_valid_std) > 0 else np.nan
    
    print(f"\n{'='*80}")
    print(f"TEMPERATURE VARIABILITY STATISTICS - {study_year}")
    print(f"{'='*80}")
    print(f"Daytime Variability:  Mean SD = {day_mean_std:.2f}°C")
    print(f"Nighttime Variability: Mean SD = {night_mean_std:.2f}°C")
    
    # Count cities with high variability (SD exceeds mean SD)
    day_high_var = np.sum((day_stds > day_mean_std) & ~np.isnan(day_stds))
    night_high_var = np.sum((night_stds > night_mean_std) & ~np.isnan(night_stds))
    
    print(f"\nCities with High Variability (SD > Mean SD):")
    print(f"  Day:   {day_high_var}/{len(day_valid_std)} cities ({day_high_var/len(day_valid_std)*100:.1f}%)")
    print(f"  Night: {night_high_var}/{len(night_valid_std)} cities ({night_high_var/len(night_valid_std)*100:.1f}%)")
    print(f"\nCities sorted by highest to lowest variability")
    print(f"{'='*80}\n")
    
    # Get dynamic layout parameters
    n_cities = len(cities)
    layout = _get_chart_layout_params(n_cities)
    figsize = layout['figsize']
    width = layout['width']
    fontsize_labels = layout['fontsize_labels']
    
    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    
    y = np.arange(n_cities)
    
    # Colors (consistent with summary chart)
    day_base_color = '#FFB366'  # Light orange for day
    night_base_color = '#696969'  # Dark grey for night
    high_var_color = '#FF0000'  # Red for high variability
    
    # Plot horizontal bars
    for i, city in enumerate(cities):
        day_sd = day_stds[i]
        night_sd = night_stds[i]
        
        # --- DAY BAR (top of pair) ---
        if not np.isnan(day_sd):
            base_w = min(day_sd, day_mean_std)
            ax.barh(y[i] - width/2, base_w, width,
                    color=day_base_color, edgecolor='black', linewidth=1)
            
            if day_sd > day_mean_std:
                tip_w = day_sd - day_mean_std
                ax.barh(y[i] - width/2, tip_w, width,
                        left=day_mean_std, color=high_var_color,
                        edgecolor='black', linewidth=1)
            
            ax.text(day_sd / 2, y[i] - width/2, f'{day_sd:.2f}',
                    ha='center', va='center', fontsize=fontsize_labels,
                    fontweight='bold', color='white',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='black',
                              alpha=0.7))
        
        # --- NIGHT BAR (bottom of pair) ---
        if not np.isnan(night_sd):
            base_w = min(night_sd, night_mean_std)
            ax.barh(y[i] + width/2, base_w, width,
                    color=night_base_color, edgecolor='black', linewidth=1)
            
            if night_sd > night_mean_std:
                tip_w = night_sd - night_mean_std
                ax.barh(y[i] + width/2, tip_w, width,
                        left=night_mean_std, color=high_var_color,
                        edgecolor='black', linewidth=1)
            
            ax.text(night_sd / 2, y[i] + width/2, f'{night_sd:.2f}',
                    ha='center', va='center', fontsize=fontsize_labels,
                    fontweight='bold', color='white',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='black',
                              alpha=0.7))
    
    # Mean SD lines (vertical now)
    if not np.isnan(day_mean_std):
        ax.axvline(day_mean_std, color='darkorange', linestyle='--',
                   linewidth=2.5, alpha=0.8, zorder=3)
        ax.text(day_mean_std + 0.05, n_cities - 0.3,
                f'Day Mean SD: {day_mean_std:.2f}°C',
                fontsize=9, fontweight='bold', color='darkorange',
                bbox=dict(boxstyle='round,pad=0.4', facecolor='white',
                          edgecolor='darkorange', alpha=0.9),
                ha='left', va='top')
    
    if not np.isnan(night_mean_std):
        ax.axvline(night_mean_std, color='dimgray', linestyle='--',
                   linewidth=2.5, alpha=0.8, zorder=3)
        ax.text(night_mean_std + 0.05, 0.3,
                f'Night Mean SD: {night_mean_std:.2f}°C',
                fontsize=9, fontweight='bold', color='dimgray',
                bbox=dict(boxstyle='round,pad=0.4', facecolor='white',
                          edgecolor='dimgray', alpha=0.9),
                ha='left', va='bottom')
    
    # Horizontal separators between cities
    for i in range(1, n_cities):
        ax.axhline(y[i] - 0.5, color='lightgrey', linestyle='-',
                   linewidth=1, alpha=0.3, zorder=0)
    
    # Formatting — axes swapped for horizontal layout
    ax.set_ylabel('Cities (sorted highest → lowest variability)', fontsize=13,
                  fontweight='bold')
    ax.set_xlabel('Standard Deviation (°C)', fontsize=13, fontweight='bold')
    ax.set_title(
        f'Temperature Variability During Persistent Heat Events - {study_year}\n'
        f'Red tips indicate cities with high temperature variability (SD > Mean SD)',
        fontsize=14, fontweight='bold', pad=20)
    ax.set_yticks(y)
    ax.set_yticklabels(cities, fontsize=10)
    ax.invert_yaxis()  # highest variability at top
    ax.grid(axis='x', alpha=0.3, linestyle='--', zorder=0)
    
    # Legend
    legend_elements = [
        Patch(facecolor=day_base_color, edgecolor='black',
              label='Day Normal Variability'),
        Patch(facecolor=night_base_color, edgecolor='black',
              label='Night Normal Variability'),
        Patch(facecolor=high_var_color, edgecolor='black',
              label='High Variability Tip (SD > Mean SD)'),
    ]
    
    ax.legend(handles=legend_elements, loc='lower right', fontsize=9,
              framealpha=0.95, edgecolor='black', fancybox=True)
    
    plt.tight_layout()
    
    # Save figure
    if base_dir:
        output_dir = Path(base_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        png_path = output_dir / f'Persistent_Heat_Event_Variability_{study_year}.png'
        pdf_path = output_dir / f'Persistent_Heat_Event_Variability_{study_year}.pdf'
        
        fig.savefig(png_path, dpi=dpi, bbox_inches='tight',
                   facecolor='white', pad_inches=0.1)
        fig.savefig(pdf_path, format='pdf', bbox_inches='tight',
                   facecolor='white', pad_inches=0.1)
        
        print(f" Saved: {png_path.name}")
        print(f" Saved: {pdf_path.name}")
        print(f"{'='*80}\n")
    
    return fig
    
    legend_elements = [
        Patch(facecolor=day_base_color, edgecolor='black', label='Day Base (0 → Mean)'),
        Patch(facecolor=day_exceed_color, edgecolor='black', label='Day SD Portion (Mean → Value)'),
        Patch(facecolor=night_base_color, edgecolor='black', label='Night Base (0 → Mean)'),
        Patch(facecolor=night_exceed_color, edgecolor='black', label='Night SD Portion (Mean → Value)'),
    ]
    
    # Add mean lines to legend
    if not np.isnan(day_overall_mean):
        legend_elements.append(Line2D([0], [0], color='darkorange', linestyle='-', 
                                     linewidth=2.5, label=f'Day Mean: {day_overall_mean:.1f}°C'))
    if not np.isnan(night_overall_mean):
        legend_elements.append(Line2D([0], [0], color='darkblue', linestyle='-',
                                     linewidth=2.5, label=f'Night Mean: {night_overall_mean:.1f}°C'))
    
    # Add threshold lines to legend
    if not np.isnan(day_threshold):
        legend_elements.append(Line2D([0], [0], color='red', linestyle='--',
                                     linewidth=2, label=f'Day Threshold (M+SD): {day_threshold:.1f}°C'))
    if not np.isnan(night_threshold):
        legend_elements.append(Line2D([0], [0], color='dimgrey', linestyle='--',
                                     linewidth=2, label=f'Night Threshold (M+SD): {night_threshold:.1f}°C'))
    
    # Position legend at bottom right
    ax.legend(handles=legend_elements, loc='lower right', fontsize=8.5, 
             framealpha=0.95, edgecolor='black', fancybox=True, ncol=2)
    
    # Add text box with summary - positioned lower left
    day_above_mean = np.sum((day_means > day_overall_mean) & ~np.isnan(day_means))
    night_above_mean = np.sum((night_means > night_overall_mean) & ~np.isnan(night_means))
    day_above_threshold = np.sum((day_means > day_threshold) & ~np.isnan(day_means))
    night_above_threshold = np.sum((night_means > night_threshold) & ~np.isnan(night_means))
    
    summary_text = (
        f'Cities Above Mean:\n'
        f'  Day: {day_above_mean}/{len(day_valid)}\n'
        f'  Night: {night_above_mean}/{len(night_valid)}\n'
        f'\n'
        f'Cities Exceeding Threshold (M+SD):\n'
        f'  Day: {day_above_threshold}/{len(day_valid)}\n'
        f'  Night: {night_above_threshold}/{len(night_valid)}\n'
        f'\n'
        f'Each city: Day (left) | Night (right)'
    )
    
    ax.text(0.02, 0.02, summary_text, transform=ax.transAxes,
           fontsize=9, va='bottom', ha='left',
           bbox=dict(boxstyle='round,pad=0.6', facecolor='white',
                    alpha=0.95, edgecolor='black', linewidth=1.5))
    
    plt.tight_layout()
    
    # Save figure
    if base_dir:
        output_dir = Path(base_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        png_path = output_dir / f'Persistent_Heat_Event_Summary_{study_year}.png'
        pdf_path = output_dir / f'Persistent_Heat_Event_Summary_{study_year}.pdf'
        
        fig.savefig(png_path, dpi=dpi, bbox_inches='tight',
                   facecolor='white', pad_inches=0.1)
        fig.savefig(pdf_path, format='pdf', bbox_inches='tight',
                   facecolor='white', pad_inches=0.1)
        
        print(f" Saved: {png_path.name}")
        print(f" Saved: {pdf_path.name}")
        print(f"{'='*80}\n")
    
    return fig


# =============================================================================
# HOTSPOT GRID MAP VISUALIZATION (Notebook 05 - Section 6.1)
# =============================================================================

def create_city_hotspot_grid_maps(city_name, hotspot_polygons, survey_points, landscape_data, 
                                  output_dir, show_plot=False, skip_if_exists=True):
    """
    Create 1×3 grid of hotspot maps for a city showing P90 and Gi* overlayed.
    
    Includes skip logic to avoid re-generating maps if they already exist with matching parameters.
    
    Parameters
    ----------
    city_name : str
        Name of the city
    hotspot_polygons : GeoDataFrame
        Hotspot polygons with method, period, contour_level columns
    survey_points : GeoDataFrame
        Survey points with spot_type column
    landscape_data : GeoDataFrame
        Landscape data with Cluster25 classification
    output_dir : Path
        Directory to save output maps
    show_plot : bool, optional
        Whether to display the plot (default: False)
    skip_if_exists : bool, optional
        If True, skip generation if files already exist (default: True)
        
    Returns
    -------
    dict or None
        Processing results with status and file paths, or None if error
        
    Examples
    --------
    >>> from pathlib import Path
    >>> result = create_city_hotspot_grid_maps(
    ...     city_name='Lagos',
    ...     hotspot_polygons=hotspots_gdf,
    ...     survey_points=survey_gdf,
    ...     landscape_data=landscape_gdf,
    ...     output_dir=Path('data/outputs/05_hotspot_analysis/maps'),
    ...     skip_if_exists=True
    ... )
    >>> if result and not result['skipped']:
    ...     print(f"Maps generated: {result['pdf'].name}")
    """
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.lines import Line2D
    import geopandas as gpd
    import numpy as np
    from pathlib import Path
    import json
    
    try:
        import config
        OUTPUT_DIR = config.OUTPUT_DIR
    except:
        OUTPUT_DIR = Path('data/outputs')
    
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Define expected output files (vector only)
    pdf_path = output_dir / f'{city_name}_hotspot_grid_1x3.pdf'
    svg_path = output_dir / f'{city_name}_hotspot_grid_1x3.svg'
    legend_pdf = output_dir / f'{city_name}_legend.pdf'
    legend_svg = output_dir / f'{city_name}_legend.svg'
    tracking_file = output_dir / f'{city_name}_map_params.json'
    
    # =============================================================================
    # SKIP LOGIC: Check if maps exist and parameters match
    # =============================================================================
    
    if skip_if_exists and pdf_path.exists() and svg_path.exists() and legend_pdf.exists() and legend_svg.exists():
        # Check if tracking file exists
        if tracking_file.exists():
            with open(tracking_file, 'r') as f:
                saved_params = json.load(f)
            
            # Get current AOI area to detect changes
            try:
                city_dir = OUTPUT_DIR / '01_aoi_delineation' / f'City_{city_name}'
                features_dir = city_dir / 'Features'
                main_polygon_file = features_dir / f'{city_name}_Main_Polygon.geojson'
                
                if main_polygon_file.exists():
                    main_poly_gdf = gpd.read_file(main_polygon_file)
                    current_area_km2 = main_poly_gdf.to_crs('EPSG:32632').area.sum() / 1e6
                else:
                    current_area_km2 = 0.0
                    
                saved_area_km2 = saved_params.get('aoi_area_km2', 0.0)
                area_change_pct = abs(current_area_km2 - saved_area_km2) / saved_area_km2 * 100 if saved_area_km2 > 0 else 0
                
                # Skip if area hasn't changed significantly (tolerance: 1%)
                if area_change_pct < 1.0:
                    return {
                        'city': city_name,
                        'pdf': pdf_path,
                        'svg': svg_path,
                        'legend_pdf': legend_pdf,
                        'legend_svg': legend_svg,
                        'PDF': pdf_path,
                        'SVG': svg_path,
                        'skipped': True,
                        'reason': f'Maps exist and AOI unchanged (area change: {area_change_pct:.2f}%)',
                        'success': True
                    }
            except Exception as e:
                # If we can't check parameters, regenerate to be safe
                pass
        else:
            # Backward-compatible fast skip when outputs exist but tracking file is absent.
            return {
                'city': city_name,
                'pdf': pdf_path,
                'svg': svg_path,
                'legend_pdf': legend_pdf,
                'legend_svg': legend_svg,
                'PDF': pdf_path,
                'SVG': svg_path,
                'skipped': True,
                'reason': 'Maps exist (tracking metadata not found)',
                'success': True
            }
    
    # =============================================================================
    # CONFIGURATION: Colors, Styles, Periods
    # =============================================================================
    
    METHODS = ['P90', 'GI_STAR']
    PERIODS = ['Day', 'Night', 'Persistent']
    
    # Color configuration - Orange shades for P90, Red shades for Gi*
    HOTSPOT_COLORS = {
        'P90': {
            0.9: '#FF8C00',   # Dark orange (90% - most critical)
            0.75: '#FFA500',  # Orange (75%)
            0.5: '#FFD700'    # Gold/Light orange (50% - least critical)
        },
        'GI_STAR': {
            0.9: '#8B0000',   # Dark red (90% - most critical)
            0.75: '#DC143C',  # Crimson (75%)
            0.5: '#FF6347'    # Tomato/Light red (50% - least critical)
        }
    }
    
    CONTOUR_STYLES = {
        0.9: {'alpha': 0.8, 'linewidth': 1.5, 'linestyle': '-'},
        0.75: {'alpha': 0.7, 'linewidth': 1.2, 'linestyle': '--'},
        0.5: {'alpha': 0.6, 'linewidth': 0.8, 'linestyle': ':'}
    }
    
    SURVEY_STYLES = {
        'hotspot': {'marker': '*', 'color': 'red', 'size': 100, 'edgecolor': 'darkred', 'linewidth': 0.5},
        'coolspot': {'marker': 'o', 'color': 'blue', 'size': 50, 'edgecolor': 'darkblue', 'linewidth': 0.5}
    }
    
    OSM_STYLES = {
        'water': {'facecolor': '#4A90E2', 'edgecolor': '#2E5C8A', 'linewidth': 0.5, 'alpha': 0.7},
        'roads': {'color': '#666666', 'linewidth': 0.3, 'alpha': 0.6}
    }
    
    BOUNDARY_STYLES = {
        'main': {'edgecolor': 'black', 'facecolor': 'none', 'linewidth': 2.0, 'linestyle': '-'},
        'adjacent': {'edgecolor': 'black', 'facecolor': 'none', 'linewidth': 2.0, 'linestyle': '--'}
    }
    
    # =============================================================================
    # DATA PREPARATION: Filter data for this city and load spatial files
    # =============================================================================
    
    city_hotspots = hotspot_polygons[hotspot_polygons['city'] == city_name].copy()
    city_survey = survey_points[survey_points['city'] == city_name].copy() if 'city' in survey_points.columns else survey_points.copy()
    
    # Load city-specific data
    city_dir = OUTPUT_DIR / '01_aoi_delineation' / f'City_{city_name}'
    features_dir = city_dir / 'Features'
    osm_dir = features_dir / 'OSM'
    
    # Load AOI boundaries
    try:
        aoi_boundary = gpd.read_file(features_dir / f'{city_name}_AOI_Boundary.geojson')
        main_polygon = gpd.read_file(features_dir / f'{city_name}_Main_Polygon.geojson')
        adj_file = features_dir / f'{city_name}_Adjacent_Polygons.geojson'
        if adj_file.exists():
            adjacent_polygons = gpd.read_file(adj_file)
        else:
            adjacent_polygons = gpd.GeoDataFrame()
    except Exception as e:
        print(f" Error loading boundaries for {city_name}: {e}")
        return None
    
    # Load OSM features (separate try/except so roads still display when
    # water_bodies file is absent — 12 cities lack a water_bodies GeoJSON)
    try:
        osm_roads = gpd.read_file(osm_dir / f'{city_name}_roads.geojson')
    except Exception:
        osm_roads = gpd.GeoDataFrame()
    try:
        osm_water = gpd.read_file(osm_dir / f'{city_name}_water_bodies.geojson')
    except Exception:
        osm_water = gpd.GeoDataFrame()
    
    # Clip and merge landscape data
    if landscape_data is not None:
        try:
            landscape_clipped = gpd.overlay(landscape_data, aoi_boundary, how='intersection')
            landscape_merged = landscape_clipped.dissolve(by='Cluster25', as_index=False)
        except Exception:
            landscape_merged = None
    else:
        landscape_merged = None
    
    # Separate survey points by type
    survey_hotspots = city_survey[city_survey['spot_type'].str.contains('hotspot', case=False, na=False)]
    survey_coolspots = city_survey[city_survey['spot_type'].str.contains('coolspot', case=False, na=False)]
    
    # =============================================================================
    # FIGURE CREATION: 1×3 Grid (Day/Night/Persistent)
    # =============================================================================
    
    bounds = aoi_boundary.total_bounds  # [minx, miny, maxx, maxy]
    width_deg = bounds[2] - bounds[0]
    height_deg = bounds[3] - bounds[1]
    aspect_ratio = height_deg / width_deg
    
    fig_width = 18
    fig_height = max(6, min(12, fig_width * aspect_ratio / 3))
    
    fig, axes = plt.subplots(1, 3, figsize=(fig_width, fig_height))
    fig.suptitle(f'{city_name}: Hotspot Detection Results (P90 & Gi* Overlayed)', 
                 fontsize=18, fontweight='bold', y=0.98)
    
    # =============================================================================
    # PLOT EACH PERIOD
    # =============================================================================
    
    for col_idx, period in enumerate(PERIODS):
        ax = axes[col_idx]
        ax.set_title(period, fontsize=16, fontweight='bold', pad=10)
        ax.set_xlim(bounds[0], bounds[2])
        ax.set_ylim(bounds[1], bounds[3])
        ax.set_aspect('equal')
        
        # Layer 1: Landscape (Cluster25 merged) - filled with canonical cluster colours
        if landscape_merged is not None and len(landscape_merged) > 0:
            import importlib as _il
            try:
                import config as _cfg_mod
                _il.reload(_cfg_mod)
                _cl25 = getattr(_cfg_mod, 'CLUSTER25_COLORS', {})
            except Exception:
                _cl25 = {}
            # Map each polygon to its cluster colour (fallback: light grey)
            _fill_colors = landscape_merged['Cluster25'].map(
                lambda c: _cl25.get(int(c), '#d9d9d9')
            )
            landscape_merged.plot(ax=ax, color=_fill_colors,
                                 edgecolor='none', alpha=0.45, legend=False)
            landscape_merged.plot(ax=ax, facecolor='none', edgecolor='#8B4513', 
                                 linewidth=1.0, linestyle='--', alpha=0.7)
            
            # Add Cluster25 labels
            from matplotlib import patheffects
            for idx, row in landscape_merged.iterrows():
                try:
                    centroid = row.geometry.centroid
                    cluster_num = int(row['Cluster25'])
                    text = ax.text(centroid.x, centroid.y, f'CL-{cluster_num}',
                                 ha='center', va='center', fontsize=18, fontweight='bold',
                                 color='black', zorder=10)
                    text.set_path_effects([
                        patheffects.withStroke(linewidth=2, foreground='white')
                    ])
                except Exception:
                    continue
        
        # Layer 2: Water bodies
        if not osm_water.empty:
            osm_water.plot(ax=ax, **OSM_STYLES['water'])
        
        # Layer 3: Roads
        if not osm_roads.empty:
            osm_roads.plot(ax=ax, **OSM_STYLES['roads'])
        
        # Layer 4: Adjacent boundaries
        if not adjacent_polygons.empty:
            adjacent_polygons.plot(ax=ax, **BOUNDARY_STYLES['adjacent'])
        
        # Layer 5: Main boundary
        main_polygon.plot(ax=ax, **BOUNDARY_STYLES['main'])
        
        # Layer 6: Hotspot polygons (P90 first, then Gi* overlaid)
        method_areas = {}
        
        for method in METHODS:
            method_period_hotspots = city_hotspots[
                (city_hotspots['method'] == method) & 
                (city_hotspots['period'] == period)
            ]
            
            total_area = 0
            for contour_level in [0.9, 0.75, 0.5]:
                contour_hotspots = method_period_hotspots[
                    method_period_hotspots['contour_level'] == contour_level
                ]
                if not contour_hotspots.empty:
                    style = CONTOUR_STYLES[contour_level]
                    color = HOTSPOT_COLORS[method][contour_level]
                    contour_hotspots.plot(
                        ax=ax, 
                        facecolor=color, 
                        edgecolor='darkred' if method == 'GI_STAR' else 'darkorange',
                        alpha=style['alpha'],
                        linewidth=style['linewidth'],
                        linestyle=style['linestyle']
                    )
                    total_area += contour_hotspots['area_km2'].sum()
            
            method_areas[method] = total_area
        
        # Layer 7: Survey points
        if not survey_hotspots.empty:
            survey_hotspots.plot(ax=ax, marker=SURVEY_STYLES['hotspot']['marker'],
                                color=SURVEY_STYLES['hotspot']['color'],
                                markersize=SURVEY_STYLES['hotspot']['size'],
                                edgecolor=SURVEY_STYLES['hotspot']['edgecolor'],
                                linewidth=SURVEY_STYLES['hotspot']['linewidth'],
                                zorder=10)
        
        if not survey_coolspots.empty:
            survey_coolspots.plot(ax=ax, marker=SURVEY_STYLES['coolspot']['marker'],
                                 color=SURVEY_STYLES['coolspot']['color'],
                                 markersize=SURVEY_STYLES['coolspot']['size'],
                                 edgecolor=SURVEY_STYLES['coolspot']['edgecolor'],
                                 linewidth=SURVEY_STYLES['coolspot']['linewidth'],
                                 zorder=10)
        
        # Add north arrow (top right)
        from matplotlib.patches import FancyArrowPatch
        x_range = bounds[2] - bounds[0]
        y_range = bounds[3] - bounds[1]
        arrow_x = bounds[2] - 0.05 * x_range
        arrow_y_start = bounds[3] - 0.08 * y_range
        arrow_y_end = bounds[3] - 0.03 * y_range
        
        arrow = FancyArrowPatch((arrow_x, arrow_y_start), (arrow_x, arrow_y_end),
                               arrowstyle='->', mutation_scale=25, linewidth=2.5,
                               color='black', zorder=1000)
        ax.add_patch(arrow)
        ax.text(arrow_x, arrow_y_start - 0.01 * y_range, 'N', 
               ha='center', va='top', fontsize=12, fontweight='bold')
        
        # Remove axis ticks
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_xlabel('')
        ax.set_ylabel('')
        
        # Add method-specific area totals under each map
        if method_areas:
            text_lines = []
            for method in METHODS:
                area = method_areas.get(method, 0)
                method_name = 'P90' if method == 'P90' else 'Gi*'
                if area > 0:
                    text_lines.append(f'{method_name} = {area:.1f} km²')
            
            if text_lines:
                text_content = '\n'.join(text_lines)
                ax.text(0.5, -0.08, text_content, 
                       transform=ax.transAxes, fontsize=10, fontweight='bold',
                       ha='center', va='top',
                       bbox=dict(boxstyle='round,pad=0.4', facecolor='white', alpha=0.9, edgecolor='gray'))
    
    plt.tight_layout(rect=[0, 0.02, 1, 0.96])
    
    # =============================================================================
    # SAVE MAIN MAP
    # =============================================================================
    
    plt.savefig(svg_path, dpi=300, format='svg', bbox_inches='tight')
    plt.savefig(pdf_path, dpi=300, format='pdf', bbox_inches='tight')
    plt.close()
    
    # =============================================================================
    # CREATE SEPARATE LEGEND
    # =============================================================================
    
    legend_fig = plt.figure(figsize=(14, 3))
    ax_legend = legend_fig.add_subplot(111)
    ax_legend.axis('off')
    
    legend_elements = [
        # P90 Hotspots
        mpatches.Patch(facecolor=HOTSPOT_COLORS['P90'][0.9], edgecolor='darkorange', 
                      label='P90 90% Contour', alpha=0.8, linewidth=1.5),
        mpatches.Patch(facecolor=HOTSPOT_COLORS['P90'][0.75], edgecolor='darkorange', 
                      label='P90 75% Contour', alpha=0.7, linewidth=1.2),
        mpatches.Patch(facecolor=HOTSPOT_COLORS['P90'][0.5], edgecolor='darkorange', 
                      label='P90 50% Contour', alpha=0.6, linewidth=0.8),
        # Gi* Hotspots
        mpatches.Patch(facecolor=HOTSPOT_COLORS['GI_STAR'][0.9], edgecolor='darkred', 
                      label='Gi* 90% Contour', alpha=0.8, linewidth=1.5),
        mpatches.Patch(facecolor=HOTSPOT_COLORS['GI_STAR'][0.75], edgecolor='darkred', 
                      label='Gi* 75% Contour', alpha=0.7, linewidth=1.2),
        mpatches.Patch(facecolor=HOTSPOT_COLORS['GI_STAR'][0.5], edgecolor='darkred', 
                      label='Gi* 50% Contour', alpha=0.6, linewidth=0.8),
        # Survey points
        Line2D([0], [0], marker='*', color='w', markerfacecolor='red', 
               markersize=12, label='Hotspots (Stakeholders)', markeredgecolor='darkred'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='blue', 
               markersize=8, label='Coolspots (Stakeholders)', markeredgecolor='darkblue'),
        # Boundaries
        Line2D([0], [0], color='black', linewidth=2.0, label='Main City Boundary'),
        Line2D([0], [0], color='black', linewidth=2.0, linestyle='--', 
               label='Adjacent City Boundaries'),
        # Other features
        mpatches.Patch(facecolor=OSM_STYLES['water']['facecolor'], 
                      edgecolor=OSM_STYLES['water']['edgecolor'], 
                      label='Water Bodies', alpha=0.7),
        Line2D([0], [0], color=OSM_STYLES['roads']['color'], 
               linewidth=1.0, label='Roads'),
        Line2D([0], [0], color='#8B4513', linewidth=1.0, linestyle='--', 
               label='Cluster25 Boundaries'),
    ]
    
    legend = ax_legend.legend(handles=legend_elements, loc='center', ncol=4, 
              title='Legend', title_fontsize=14,
              fontsize=12, frameon=True, fancybox=True, shadow=True)
    legend.get_title().set_fontweight('bold')
    
    legend_fig.savefig(legend_svg, dpi=300, format='svg', bbox_inches='tight')
    legend_fig.savefig(legend_pdf, dpi=300, format='pdf', bbox_inches='tight')
    plt.close(legend_fig)
    
    # =============================================================================
    # SAVE TRACKING PARAMETERS
    # =============================================================================
    
    # Get current AOI area for tracking
    current_area_km2 = main_polygon.to_crs('EPSG:32632').area.sum() / 1e6
    
    tracking_params = {
        'city': city_name,
        'aoi_area_km2': round(current_area_km2, 4),
        'generated_date': pd.Timestamp.now().isoformat(),
        'periods': PERIODS,
        'methods': METHODS
    }
    
    with open(tracking_file, 'w') as f:
        json.dump(tracking_params, f, indent=2)
    
    if show_plot:
        pass  # Already closed
    
    return {
        'city': city_name, 
        'pdf': pdf_path, 
        'svg': svg_path, 
        'legend_pdf': legend_pdf, 
        'legend_svg': legend_svg, 
        'PDF': pdf_path,
        'SVG': svg_path,
        'skipped': False,
        'success': True
    }


def create_gi_star_distribution_plots(city_name, output_dir, skip_if_exists=True):
    """
    Create Gi* Z-score distribution plots for a city showing Day and Night only.
    
    Visualizes statistical distributions of Gi* Z-scores to validate hotspot 
    detection thresholds. Persistent period is excluded since it has no LST data.
    
    Parameters
    ----------
    city_name : str
        Name of the city
    output_dir : Path
        Directory to save output plots (should be figures directory, not maps)
    skip_if_exists : bool, optional
        If True, skip generation if files already exist (default: True)
        
    Returns
    -------
    dict or None
        Processing results with status and file paths, or None if error
        
    Examples
    --------
    >>> from pathlib import Path
    >>> result = create_gi_star_distribution_plots(
    ...     city_name='Lagos',
    ...     output_dir=Path('data/outputs/05_hotspot_analysis/figures'),
    ...     skip_if_exists=True
    ... )
    >>> if result and not result['skipped']:
    ...     print(f"Plots generated: {result['pdf'].name}")
    """
    import matplotlib.pyplot as plt
    import numpy as np
    from pathlib import Path
    from scipy import stats
    
    try:
        import config
        OUTPUT_DIR = config.OUTPUT_DIR
    except:
        OUTPUT_DIR = Path('data/outputs')
    
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Define expected output files (vector only)
    pdf_path = output_dir / f'{city_name}_gi_star_distributions.pdf'
    svg_path = output_dir / f'{city_name}_gi_star_distributions.svg'
    
    # =============================================================================
    # SKIP LOGIC: Check if plots exist
    # =============================================================================
    
    if skip_if_exists and pdf_path.exists() and svg_path.exists():
        return {
            'city': city_name,
            'pdf': pdf_path,
            'svg': svg_path,
            'PDF': pdf_path,
            'SVG': svg_path,
            'skipped': True,
            'reason': 'Plots already exist',
            'success': True
        }
    
    # =============================================================================
    # LOAD DATA: Get Gi* Z-scores from hotspot_results
    # =============================================================================
    
    # Need access to hotspot_results variable (should be in global scope)
    # This function is designed to be called from notebook context where
    # hotspot_results exists
    import sys
    frame = sys._getframe(1)
    hotspot_results = frame.f_globals.get('hotspot_results')
    
    if hotspot_results is None or city_name not in hotspot_results:
        print(f" Hotspot results not found for {city_name}")
        return None
    
    # Only Day and Night (Persistent has no LST data)
    periods = ['day', 'night']
    period_labels = ['Day', 'Night']
    
    # Check if required periods have data
    city_data = hotspot_results[city_name]
    if not all(period in city_data for period in periods):
        print(f" Missing period data for {city_name}")
        return None
    
    # =============================================================================
    # CREATE FIGURE: 1×2 subplots (Day/Night only), shared y-axis
    # =============================================================================
    
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=True)
    fig.suptitle(f'{city_name}: Gi* Z-Score Distributions', 
                 fontsize=16, fontweight='bold', y=0.98)
    
    for idx, (ax, period, period_label) in enumerate(zip(axes, periods, period_labels)):
        # Get Gi* Z-scores for this period
        gi_star_z = city_data[period].get('gi_star_z')
        
        if gi_star_z is None:
            ax.text(0.5, 0.5, 'No Data', ha='center', va='center', 
                   fontsize=14, transform=ax.transAxes)
            ax.set_title(period_label, fontsize=14, fontweight='bold')
            continue
        
        # Filter out NaN values
        z_scores = gi_star_z[~np.isnan(gi_star_z)]
        
        if len(z_scores) == 0:
            ax.text(0.5, 0.5, 'No Valid Data', ha='center', va='center', 
                   fontsize=14, transform=ax.transAxes)
            ax.set_title(period_label, fontsize=14, fontweight='bold')
            continue
        
        # Calculate statistics
        mean_z = np.mean(z_scores)
        std_z = np.std(z_scores)
        skewness = stats.skew(z_scores)
        kurtosis = stats.kurtosis(z_scores)
        
        # Threshold counts
        hot_95 = np.sum(z_scores > 1.96)
        hot_99 = np.sum(z_scores > 2.58)
        cold_95 = np.sum(z_scores < -1.96)
        cold_99 = np.sum(z_scores < -2.58)
        
        pct_hot_95 = 100 * hot_95 / len(z_scores)
        pct_hot_99 = 100 * hot_99 / len(z_scores)
        
        # Plot histogram
        n, bins, patches = ax.hist(z_scores, bins=50, density=True, 
                                   alpha=0.7, color='gray', edgecolor='black',
                                   linewidth=0.5, label='Observed Distribution')
        
        # Overlay theoretical normal distribution N(0,1)
        x_norm = np.linspace(z_scores.min(), z_scores.max(), 200)
        norm_pdf = stats.norm.pdf(x_norm, 0, 1)
        ax.plot(x_norm, norm_pdf, 'k--', linewidth=2, label='N(0,1) Theoretical')
        
        # Add threshold lines
        ax.axvline(1.96, color='orange', linestyle='--', linewidth=1.5, 
                  label='±1.96 (95% CI)', alpha=0.8)
        ax.axvline(-1.96, color='orange', linestyle='--', linewidth=1.5, alpha=0.8)
        ax.axvline(2.58, color='red', linestyle='--', linewidth=1.5, 
                  label='±2.58 (99% CI)', alpha=0.8)
        ax.axvline(-2.58, color='red', linestyle='--', linewidth=1.5, alpha=0.8)
        
        # Shade hotspot/coldspot regions
        ax.axvspan(1.96, z_scores.max(), alpha=0.2, color='red', label='Hotspots (Z>1.96)')
        ax.axvspan(z_scores.min(), -1.96, alpha=0.2, color='blue', label='Coldspots (Z<-1.96)')
        
        # Labels and title
        ax.set_xlabel('Gi* Z-Score', fontsize=12)
        # Only label y-axis on first (leftmost) subplot
        if idx == 0:
            ax.set_ylabel('Probability Density', fontsize=12)
        ax.set_title(period_label, fontsize=14, fontweight='bold', pad=10)
        ax.grid(True, alpha=0.3, linestyle='--')
        ax.legend(loc='upper right', fontsize=8)
        
        # Add statistics annotation
        stats_text = (
            f'Mean: {mean_z:.3f}\n'
            f'Std: {std_z:.3f}\n'
            f'Skewness: {skewness:.3f}\n'
            f'Kurtosis: {kurtosis:.3f}\n'
            f'\n'
            f'Hotspots:\n'
            f'  Z>1.96: {pct_hot_95:.1f}% ({hot_95:,})\n'
            f'  Z>2.58: {pct_hot_99:.1f}% ({hot_99:,})\n'
            f'\n'
            f'Coldspots:\n'
            f'  Z<-1.96: {100*cold_95/len(z_scores):.1f}% ({cold_95:,})\n'
            f'  Z<-2.58: {100*cold_99/len(z_scores):.1f}% ({cold_99:,})'
        )
        
        ax.text(0.02, 0.98, stats_text, transform=ax.transAxes,
               fontsize=8, va='top', ha='left',
               bbox=dict(boxstyle='round,pad=0.5', facecolor='white',
                        alpha=0.9, edgecolor='gray'))
    
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    
    # =============================================================================
    # SAVE PLOTS
    # =============================================================================
    
    plt.savefig(svg_path, dpi=300, format='svg', bbox_inches='tight')
    plt.savefig(pdf_path, dpi=300, format='pdf', bbox_inches='tight')
    plt.close()
    
    return {
        'city': city_name,
        'pdf': pdf_path,
        'svg': svg_path,
        'PDF': pdf_path,
        'SVG': svg_path,
        'skipped': False,
        'success': True
    }


def create_gistar_distribution(city, z_grids, periods=('day', 'night')):
    """
    Gi★ Z-score distribution of one city, day and night side by side (NB05 §11b).

    Each panel: density histogram of the city's Gi★ z-scores against N(0,1), the
    ±1.96 and ±2.58 thresholds, the shaded hot and cold tails, and a statistics
    box (mean, std, skew, kurtosis, hot / cold pixels at 95 % and 99 %).

    Parameters
    ----------
    city : str
        City name, for the title.
    z_grids : dict
        ``{period: z_grid}``, each a 2-D array of Gi★ z-scores (NaN outside the
        grid), or None when the period has no data.
    periods : tuple
        Panel order.

    Returns
    -------
    matplotlib.figure.Figure
        Not saved and not shown: the caller does both.
    """
    from scipy import stats as _sp_stats

    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=True)
    fig.suptitle(f'{city}: Gi★ Z-Score Distributions',
                 fontsize=13, fontweight='bold', y=0.98)

    for idx, (ax, period) in enumerate(zip(axes, periods)):
        z_grid = z_grids.get(period)
        if z_grid is None:
            ax.text(0.5, 0.5, 'No Data', ha='center', va='center',
                    fontsize=13, transform=ax.transAxes)
            ax.set_title(period.capitalize(), fontsize=12, fontweight='bold')
            continue
        z_scores = z_grid[np.isfinite(z_grid)].ravel()
        if not len(z_scores): ax.axis('off'); continue

        n        = len(z_scores)
        mean_z   = float(np.mean(z_scores))
        std_z    = float(np.std(z_scores))
        skewness = float(_sp_stats.skew(z_scores))
        kurtosis = float(_sp_stats.kurtosis(z_scores))
        hot_95   = int(np.sum(z_scores >  1.96)); hot_99  = int(np.sum(z_scores >  2.58))
        cold_95  = int(np.sum(z_scores < -1.96)); cold_99 = int(np.sum(z_scores < -2.58))

        # Density histogram
        ax.hist(z_scores, bins=50, density=True,
                alpha=0.65, color='#C8D8E8', edgecolor='#4a4a4a',
                linewidth=0.5, label='Observed distribution')

        # Theoretical N(0,1) curve
        x_norm = np.linspace(z_scores.min(), z_scores.max(), 300)
        ax.plot(x_norm, _sp_stats.norm.pdf(x_norm, 0, 1),
                'k--', lw=2, label='N(0,1) Theoretical')

        # Threshold lines ±1.96 and ±2.58
        ax.axvline( 1.96, color='#FF8C00', ls='--', lw=2.0, alpha=0.95, label='±1.96 (95% CI)')
        ax.axvline(-1.96, color='#FF8C00', ls='--', lw=2.0, alpha=0.95)
        ax.axvline( 2.58, color='#CC0000', ls=':',  lw=2.0, alpha=0.95, label='±2.58 (99% CI)')
        ax.axvline(-2.58, color='#0000CC', ls=':',  lw=2.0, alpha=0.95)

        # Shaded tails
        ax.axvspan( 1.96, float(z_scores.max()), alpha=0.22, color='#FF4500', label='Hot spots (Z > 1.96)')
        ax.axvspan(float(z_scores.min()), -1.96, alpha=0.22, color='#1565C0', label='Cold spots (Z < −1.96)')

        ax.set_xlabel('Gi★ Z-Score', fontsize=11)
        if idx == 0:
            ax.set_ylabel('Probability Density', fontsize=11)
        ax.set_title(period.capitalize(), fontsize=12, fontweight='bold', pad=8)
        ax.grid(True, alpha=0.25, ls='--')
        ax.legend(loc='upper right', fontsize=7.5)

        stats_txt = (
            f'Mean:  {mean_z:.3f}\n'
            f'Std:   {std_z:.3f}\n'
            f'Skew:  {skewness:.3f}\n'
            f'Kurt:  {kurtosis:.3f}\n\n'
            f'Hot spots:\n'
            f'  Z > 1.96 : {100*hot_95/n:.1f}% ({hot_95:,})\n'
            f'  Z > 2.58 : {100*hot_99/n:.1f}% ({hot_99:,})\n\n'
            f'Cold spots:\n'
            f'  Z < −1.96 : {100*cold_95/n:.1f}% ({cold_95:,})\n'
            f'  Z < −2.58 : {100*cold_99/n:.1f}% ({cold_99:,})'
        )
        ax.text(0.02, 0.98, stats_txt, transform=ax.transAxes,
                fontsize=7.5, va='top', ha='left',
                bbox=dict(boxstyle='round,pad=0.4', facecolor='white',
                          alpha=0.88, edgecolor='gray'))

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    return fig


def create_city_spot_area_ranked(spots, cities, city_to_cluster, cluster_colors, spot_type_filter,
                                 chart_title, legend_clusters, periods=('day', 'night'),
                                 panel_title_fmt='{period} — {spot}spot Area\n'
                                                 '(* = BH-FDR  |  colour = Cluster25  |  hatch = contour zone)',
                                 legend_title='Cluster25  |  Contour zone'):
    """
    Ranked horizontal bars of each city's spot area, day and night side by side (NB05 §11c, chart D/E).

    One bar per city with spots in the period, sorted by L50 area: the L90 / L75-L90 / L50-L75
    segments in the cluster colour with hatches; a star marks a BH-FDR-significant city.

    Parameters
    ----------
    spots : DataFrame
        One row per spot: city, period, spot_type, area_km2_50, area_km2_75, area_km2_90,
        bh_significant.
    cities : list
        The cities to consider (NB05: the cities with SEVIRI data).
    city_to_cluster : dict
        ``{city: cluster}``.
    cluster_colors : dict
        ``{cluster: colour}``.
    spot_type_filter : str
        'hot' or 'cold'.
    chart_title : str
        Figure title.
    legend_clusters : list
        The clusters listed in the legend.
    periods : tuple
        Panel order.
    panel_title_fmt : str
        Panel title, formatted with ``period`` and ``spot`` ('Hot' / 'Cold').
    legend_title : str
        Title of the bottom legend.

    Returns
    -------
    matplotlib.figure.Figure
        Not saved and not shown: the caller does both.
    """
    import matplotlib.patches as mpatches

    _bh_h = max(0.28, 5.5 / max(len(cities), 1))
    fig_d, axes_d = plt.subplots(1, 2,
        figsize=(17, max(7, len(cities)*_bh_h + 2.5)),
        sharey=False)

    for ax_d, period in zip(axes_d, periods):
        _rows_d = []
        for city in cities:
            sub = spots[(spots.city==city) & (spots.period==period) &
                        (spots.spot_type==spot_type_filter)]
            a50 = float(sub['area_km2_50'].sum()) if len(sub) else 0.
            a75 = float(sub['area_km2_75'].fillna(0).sum()) if len(sub) else 0.
            a90 = float(sub['area_km2_90'].fillna(0).sum()) if len(sub) else 0.
            bh  = bool(sub['bh_significant'].any()) if len(sub) else False
            cl  = int(city_to_cluster.get(city, -1))
            _rows_d.append({'city': city, 'a50': a50, 'a75': a75, 'a90': a90,
                            'bh': bh, 'cluster': cl})

        # Exclude cities with no spots for this period
        _dat_d = (pd.DataFrame(_rows_d)
                  .query('a50 > 0')
                  .sort_values('a50', ascending=True))

        if _dat_d.empty:
            ax_d.set_title(f'{period.capitalize()} — no {spot_type_filter} spots')
            ax_d.axis('off')
            continue

        left = np.zeros(len(_dat_d))
        for seg_vals, htch, alpha_v, seg_lbl in [
            (_dat_d['a90'].values,                          'oo', 0.85, 'L90 dense core'),
            ((_dat_d['a75']-_dat_d['a90']).clip(0).values, 'xx', 0.70, 'L75 inner zone'),
            ((_dat_d['a50']-_dat_d['a75']).clip(0).values, '//', 0.55, 'L50 outer extent'),
        ]:
            bar_clrs = [cluster_colors.get(int(_dat_d.iloc[i]['cluster']), '#BAB0AC')
                        for i in range(len(_dat_d))]
            ax_d.barh(range(len(_dat_d)), seg_vals, left=left,
                      color=bar_clrs, hatch=htch, alpha=alpha_v,
                      edgecolor='black', lw=0.4, label=seg_lbl)
            left += seg_vals

        ylabels = [f'{r.city}{"*" if r.bh else ""}' for _, r in _dat_d.iterrows()]
        ax_d.set_yticks(range(len(_dat_d)))
        ax_d.set_yticklabels(ylabels, fontsize=9)
        ax_d.set_xlabel('Area (km²)', fontsize=9)
        ax_d.set_title(panel_title_fmt.format(period=period.capitalize(),
                                              spot=spot_type_filter.capitalize()),
                       fontsize=9, fontweight='bold')

    # Legend
    cl_handles = [mpatches.Patch(color=cluster_colors.get(cl, '#BAB0AC'),
                                 label=f'C{cl}', edgecolor='black', lw=0.5)
                  for cl in sorted(legend_clusters)]
    hatch_handles = [
        mpatches.Patch(facecolor='#AAAAAA', hatch='oo', edgecolor='black', label='L90 dense core'),
        mpatches.Patch(facecolor='#AAAAAA', hatch='xx', edgecolor='black', label='L75 inner zone'),
        mpatches.Patch(facecolor='#AAAAAA', hatch='//', edgecolor='black', label='L50 outer extent'),
    ]
    fig_d.legend(handles=cl_handles + [mpatches.Patch(visible=False)] + hatch_handles,
                 title=legend_title, fontsize=7.0, title_fontsize=8,
                 loc='lower center', ncol=min(len(cl_handles)+4, 10),
                 bbox_to_anchor=(0.5, -0.02), framealpha=0.9)
    fig_d.suptitle(chart_title, fontsize=11, fontweight='bold')
    plt.tight_layout(rect=[0, 0.07, 1, 1])
    return fig_d


_HD_HOT_BASE, _HD_COLD_BASE, _HD_MIN_ARC = '#E07B00', '#2B6CB0', 8.0


def _hd_fmt(v):
    if v >= 1e6: return f'{v/1e6:.1f}M'
    if v >= 1e3: return f'{v/1e3:.1f}k'
    return f'{int(v)}'


def _hd_blend(hex_c, fade):
    import matplotlib.colors as _mc
    rgb = np.array(_mc.to_rgb(hex_c))
    return tuple(rgb + fade * (1 - rgb))


def create_population_halfdonut(sub_gdf, title):
    """
    Population within hot and cold spots as a half-donut (NB05 §11d, ``_draw_halfdonut``).

    Flat edge down, arc up; left half = hot spots, right half = cold spots. Ring 1 (inner) =
    spot type, proportional to its population; ring 2 = day / night within each type; ring 3
    (outer) = contour zone (L90 / L75 excl. / L50 excl.). Labels only for arcs >= 8 degrees,
    spaced per side.

    Parameters
    ----------
    sub_gdf : DataFrame
        Rows of one city, cluster or the nation, with spot_type, period, population (L50),
        pop_75, pop_90 and area_km2_50 / _75 / _90 (used only where pop_75 / pop_90 are absent).
    title : str
        Axes title.

    Returns
    -------
    matplotlib.figure.Figure or None
        None when ``sub_gdf`` is empty. Not saved and not shown: the caller does both.
    """
    from matplotlib.patches import Wedge as _W11d, Patch as _P11d
    HOT_BASE, COLD_BASE, MIN_ARC = _HD_HOT_BASE, _HD_COLD_BASE, _HD_MIN_ARC
    _fmt11d, _blend11d = _hd_fmt, _hd_blend

    if not len(sub_gdf):
        return None

    fig, ax = plt.subplots(figsize=(10, 6.5), subplot_kw=dict(aspect='equal'))

    r_i = [0.32, 0.60, 0.92]
    r_w = [0.25, 0.28, 0.28]

    def _pop(st, per):
        s = sub_gdf[(sub_gdf.spot_type == st) & (sub_gdf.period == per)]
        return float(s['population'].sum()) if len(s) else 0.

    def _pop75(st, per):
        s = sub_gdf[(sub_gdf.spot_type == st) & (sub_gdf.period == per)]
        if 'pop_75' in s.columns and s['pop_75'].notna().any():
            return float(s['pop_75'].sum()) if len(s) else 0.
        a50 = float(s['area_km2_50'].sum()) or 1
        a75 = float(s['area_km2_75'].fillna(0).sum())
        return _pop(st, per) * (a75 / a50)

    def _pop90(st, per):
        s = sub_gdf[(sub_gdf.spot_type == st) & (sub_gdf.period == per)]
        if 'pop_90' in s.columns and s['pop_90'].notna().any():
            return float(s['pop_90'].sum()) if len(s) else 0.
        a50 = float(s['area_km2_50'].sum()) or 1
        a90 = float(s['area_km2_90'].fillna(0).sum())
        return _pop(st, per) * (a90 / a50)

    total_hot_pop  = _pop('hot', 'day')  + _pop('hot', 'night')
    total_cold_pop = _pop('cold', 'day') + _pop('cold', 'night')
    total_pop      = total_hot_pop + total_cold_pop

    total_all  = (total_hot_pop + total_cold_pop) or 1
    hot_sweep  = min(180., 180. * total_hot_pop  / total_all)
    cold_sweep = min(180., 180. * total_cold_pop / total_all)

    raw_labels = []   # collect before drawing (to apply spacing first)

    for st, base_ang, ang_span, base_clr in (
        ('hot',  180 - hot_sweep,  hot_sweep,  HOT_BASE),
        ('cold', 0,                cold_sweep, COLD_BASE),
    ):
        side = 'left' if st == 'hot' else 'right'
        if ang_span < 0.5:
            continue

        # Ring 1: spot-type band
        ax.add_patch(_W11d((0, 0), r_i[0] + r_w[0], base_ang, base_ang + ang_span,
                           width=r_w[0], facecolor=_blend11d(base_clr, 0.0),
                           edgecolor='white', lw=2.0))
        if ang_span >= MIN_ARC:
            mid_ang = base_ang + ang_span / 2
            mid_r   = r_i[0] + r_w[0] / 2
            raw_labels.append({'ang': mid_ang, 'r': mid_r, 'side': side,
                               'text': f'{"Hot" if st=="hot" else "Cold"}: '
                                       f'{_fmt11d(total_hot_pop if st=="hot" else total_cold_pop)}',
                               'fs': 9, 'fw': 'bold'})

        # Ring 2: Day / Night
        ang2    = base_ang
        tot_st  = (total_hot_pop if st == 'hot' else total_cold_pop) or 1
        for per, fade, ico in (('day', 0.0, '☀'), ('night', 0.30, '☾')):
            pp  = _pop(st, per)
            sw2 = ang_span * (pp / tot_st)
            if pp > 0 and sw2 > 0.5:
                ax.add_patch(_W11d((0, 0), r_i[1] + r_w[1], ang2, ang2 + sw2,
                                   width=r_w[1], facecolor=_blend11d(base_clr, fade),
                                   edgecolor='white', lw=1.4))
                if sw2 >= MIN_ARC:
                    raw_labels.append({'ang': ang2 + sw2 / 2, 'r': r_i[1] + r_w[1] / 2,
                                       'side': side,
                                       'text': f'{ico} {per.capitalize()}: {_fmt11d(pp)}',
                                       'fs': 7.5, 'fw': 'normal'})

                # Ring 3: contour zones
                p90    = min(_pop90(st, per), pp)
                p75    = min(_pop75(st, per), pp)
                p75_ex = max(0, p75 - p90)
                p50_ex = max(0, pp  - p75)
                ang3   = ang2
                for pop_seg, fade3, htch, zone_lbl in (
                    (p90,    0.0,  'oo', 'L90'),
                    (p75_ex, 0.15, 'xx', 'L75'),
                    (p50_ex, 0.30, '//', 'L50'),
                ):
                    sw3 = sw2 * (pop_seg / pp) if pp > 0 else 0
                    if pop_seg > 0 and sw3 > 0.3:
                        ax.add_patch(_W11d((0, 0), r_i[2] + r_w[2], ang3, ang3 + sw3,
                                          width=r_w[2],
                                          facecolor=_blend11d(base_clr, 0.55 + fade3),
                                          hatch=htch, edgecolor='white', lw=0.8))
                        if sw3 >= MIN_ARC:
                            raw_labels.append({
                                'ang':  ang3 + sw3 / 2,
                                'r':    r_i[2] + r_w[2] / 2,
                                'side': side,
                                'text': f'{zone_lbl}: {_fmt11d(pop_seg)}',
                                'fs':   6.5, 'fw': 'normal'})
                    ang3 += sw3
            ang2 += sw2

    # Centre label
    ax.text(0,  0.10, _fmt11d(total_pop),   ha='center', va='center',
            fontsize=13, fontweight='bold', color='#333')
    ax.text(0, -0.08, 'Total\npop',          ha='center', va='center',
            fontsize=7, color='#666')
    ax.text(-0.7, -0.08, '← Hot spots',  ha='center', va='top',
            fontsize=9, fontweight='bold', color=HOT_BASE)
    ax.text( 0.7, -0.08, 'Cold spots →', ha='center', va='top',
            fontsize=9, fontweight='bold', color=COLD_BASE)

    ax.set_xlim(-2.2, 2.2)
    ax.set_ylim(-0.6, 1.80)

    # Build annotate positions; enforce minimum y-spacing per side
    MIN_DY = 0.14
    annots = []
    for sp in raw_labels:
        ang_r = np.radians(sp['ang'])
        rx = sp['r'] * np.cos(ang_r)
        ry = sp['r'] * np.sin(ang_r)
        lx = -1.90 if sp['side'] == 'left' else 1.90
        annots.append({**sp, 'rx': rx, 'ry': ry, 'lx': lx, 'y_text': max(0.04, ry)})

    for side in ('left', 'right'):
        side_a = sorted([a for a in annots if a['side'] == side],
                        key=lambda a: a['y_text'])
        for i in range(1, len(side_a)):
            if side_a[i]['y_text'] - side_a[i - 1]['y_text'] < MIN_DY:
                side_a[i]['y_text'] = side_a[i - 1]['y_text'] + MIN_DY

    for sp in annots:
        ax.annotate(
            sp['text'],
            xy=(sp['rx'], sp['ry']),
            xytext=(sp['lx'], sp['y_text']),
            ha='right' if sp['side'] == 'left' else 'left',
            va='center', fontsize=sp['fs'], fontweight=sp['fw'],
            color='#222',
            bbox=dict(boxstyle='round,pad=0.18', fc='white', ec='none', alpha=0.88),
            arrowprops=dict(arrowstyle='-', color='#bbb', lw=0.5))

    ax.axis('off')
    ax.set_title(title, fontsize=9, fontweight='bold', pad=10)

    leg_h = [
        _P11d(facecolor=HOT_BASE,  label='Hot spots'),
        _P11d(facecolor=COLD_BASE, label='Cold spots'),
        _P11d(facecolor='#AAAAAA', hatch='oo', edgecolor='white', label='L90 dense core'),
        _P11d(facecolor='#AAAAAA', hatch='xx', edgecolor='white', label='L75 inner zone'),
        _P11d(facecolor='#AAAAAA', hatch='//', edgecolor='white', label='L50 outer extent'),
    ]
    ax.legend(handles=leg_h, loc='lower center', ncol=5, fontsize=7.5,
              bbox_to_anchor=(0.5, -0.04), framealpha=0.9)
    plt.tight_layout()
    return fig


def create_national_population_map(spots, centroids, cities, landscape_gdf, nigeria_gdf,
                                   cluster25_colors, spot_type_filter='hot', title=None,
                                   spot_label=None, pop_word='pop exp',
                                   scale_title='Population\nExposure'):
    """
    National map of each city's spot area and the population within it (NB05 §11e,
    ``plot_national_map_v2``).

    Background: the Cluster25 landscape (alpha 0.30) and the national boundary. Per city: a
    circle sized by the population within its L50 spots (day + night), split into a day and a
    night wedge by spot area, labelled with the city and its area; grey dot where the city has
    none. Legend, north arrow, ~100 km scale bar, national statistics box and a population key.

    Parameters
    ----------
    spots : DataFrame
        city, period, spot_type, area_km2_50, population (L50), bh_significant.
    centroids : dict
        ``{city: (lon, lat)}``, the urban-core centroids (EPSG:4326).
    cities : list
        The cities analysed (NB05: the cities with SEVIRI data).
    landscape_gdf : GeoDataFrame
        Landscape polygons with a ``Cluster25`` column.
    nigeria_gdf : GeoDataFrame
        National boundary.
    cluster25_colors : dict
        ``{cluster: colour}``.
    spot_type_filter : str
        'hot' or 'cold'.
    title : str or None
        Axes title; None gives NB05's.
    spot_label : str or None
        'Hotspot' / 'Coldspot' (NB05's) when None; used in the title, legend and box.
    pop_word : str
        The statistics box's population label (NB05: 'pop exp').
    scale_title : str
        Title of the population key (NB05: 'Population\\nExposure').

    Returns
    -------
    matplotlib.figure.Figure
        Not saved and not shown: the caller does both.
    """
    from matplotlib.patches import Wedge as _Wedge5e
    import matplotlib.patches as _mp5e
    import matplotlib.lines as _ml5e_leg
    _fmt_pop5e = _hd_fmt

    DAY_CLR   = '#FF9500' if spot_type_filter == 'hot' else '#00CED1'
    NIGHT_CLR = '#4A4A4A' if spot_type_filter == 'hot' else '#1565C0'
    if spot_label is None:
        spot_label = 'Hotspot' if spot_type_filter == 'hot' else 'Coldspot'

    land = landscape_gdf.to_crs('EPSG:4326').copy()
    land['_clr'] = land['Cluster25'].apply(lambda c: cluster25_colors.get(int(c), '#DDDDDD'))

    fig, ax = plt.subplots(figsize=(10, 10))

    # ── Background: Cluster25 landscape (single vectorised call) ─────────────
    land.plot(ax=ax, color=land['_clr'], alpha=0.30, edgecolor='none', zorder=1)

    # National boundary outline (on top of landscape)
    nigeria_gdf.boundary.plot(ax=ax, edgecolor='#1A1A1A', lw=1.8, zorder=6)

    # ── Per-city wedge circles ────────────────────────────────────────────────
    city_stats = {}
    for city in cities:
        if city not in centroids: continue
        lon, lat = centroids[city]
        stats = {'lon': lon, 'lat': lat}
        for period in ('day', 'night'):
            sub = spots[(spots.city==city) & (spots.period==period) &
                        (spots.spot_type==spot_type_filter)]
            stats[f'{period}_area'] = float(sub['area_km2_50'].sum()) if len(sub) else 0.
            stats[f'{period}_pop']  = float(sub['population'].sum())  if len(sub) else 0.
        stats['total_area'] = stats['day_area'] + stats['night_area']
        stats['total_pop']  = stats['day_pop']  + stats['night_pop']
        stats['bh'] = bool(spots[(spots.city==city)&(spots.spot_type==spot_type_filter)]['bh_significant'].any())
        city_stats[city] = stats

    max_area = max((s['total_area'] for s in city_stats.values() if s['total_area'] > 0), default=1)
    max_pop  = max((s['total_pop']  for s in city_stats.values() if s['total_pop']  > 0), default=1)
    SCALE = 0.55

    total_day_pop   = sum(s['day_pop']   for s in city_stats.values())
    total_night_pop = sum(s['night_pop'] for s in city_stats.values())
    n_with_spots    = sum(1 for s in city_stats.values() if s['total_area'] > 0)
    total_area_km2  = sum(s['total_area'] for s in city_stats.values())

    for city, s in city_stats.items():
        lon, lat = s['lon'], s['lat']
        total = s['total_area'] or 0
        total_pop_city = s['total_pop'] or 0
        if total <= 0 or total_pop_city <= 0:
            ax.plot(lon, lat, 'o', color='#CCCCCC', ms=4, zorder=5, alpha=0.6)
            continue
        radius  = SCALE * (max(total_pop_city, 1) / max_pop) ** 0.5
        day_f   = s['day_area']   / total
        night_f = s['night_area'] / total
        day_start = 90; day_end = 90 + day_f * 360
        if s['day_area'] > 0:
            ax.add_patch(_Wedge5e((lon, lat), radius, day_start, day_end,
                                  facecolor=DAY_CLR, edgecolor='white', lw=0.8,
                                  alpha=0.92, zorder=6))
        night_start = day_end; night_end = 450
        if s['night_area'] > 0:
            ax.add_patch(_Wedge5e((lon, lat), radius, night_start, night_end,
                                  facecolor=NIGHT_CLR, edgecolor='white', lw=0.8,
                                  alpha=0.92, zorder=6))
        ax.plot(lon, lat, 'ko', ms=2.5, zorder=7)
        ax.text(lon, lat - radius - 0.08,
                f"{city}\n({s['total_area']:.0f} km²)",
                ha='center', va='top', fontsize=5.5, color='#222', zorder=7,
                linespacing=0.9,
                bbox=dict(boxstyle='round,pad=0.1', fc='white', ec='none', alpha=0.65))

    bounds = nigeria_gdf.total_bounds
    ax.set_xlim(bounds[0]-0.5, bounds[2]+0.5)
    ax.set_ylim(bounds[1]-1.0, bounds[3]+0.8)
    ax.grid(True, alpha=0.12, ls='--', lw=0.4, zorder=0)
    ax.set_xlabel('Longitude', fontsize=10)
    ax.set_ylabel('Latitude',  fontsize=10)
    ax.set_aspect('equal')
    ax.set_title(title if title is not None else
                 f'Nigeria UHI {spot_label} Summary — Area & Population Exposure',
                 fontsize=13, fontweight='bold', pad=12)

    # Legend — Day / Night / No spots only (no Cluster25 entries)
    legend_els = [
        _mp5e.Patch(facecolor=DAY_CLR,   edgecolor='white',
                    label=f'Day {spot_label.lower()} area',   alpha=0.92),
        _mp5e.Patch(facecolor=NIGHT_CLR, edgecolor='white',
                    label=f'Night {spot_label.lower()} area', alpha=0.92),
        _mp5e.Patch(facecolor='#CCCCCC', edgecolor='none',
                    label='No spots detected'),
        _ml5e_leg.Line2D([0], [0], color='#1A1A1A', lw=1.8,
                         label='Nigeria boundary'),
    ]
    ax.legend(handles=legend_els, loc='lower left', fontsize=8.5, framealpha=0.95,
              edgecolor='#999', title='Legend', title_fontsize=10, ncol=1)

    # North arrow
    ax.annotate('N', xy=(0.97, 0.96), xytext=(0.97, 0.91),
                xycoords='axes fraction', fontsize=12, ha='center', fontweight='bold',
                arrowprops=dict(arrowstyle='->', lw=2, color='black'), zorder=10)

    # Scale bar — bottom centre
    _deg_100km = 100 / 111.0   # degrees ≈ 100km at equator
    sc_lon = (bounds[0] + bounds[2]) / 2 - _deg_100km / 2
    sc_lat = bounds[1] - 0.55
    ax.plot([sc_lon, sc_lon+0.9], [sc_lat, sc_lat], 'k-', lw=3, zorder=8)
    ax.plot([sc_lon, sc_lon], [sc_lat-0.1, sc_lat+0.1], 'k-', lw=2, zorder=8)
    ax.plot([sc_lon+0.9, sc_lon+0.9], [sc_lat-0.1, sc_lat+0.1], 'k-', lw=2, zorder=8)
    ax.text(sc_lon+0.45, sc_lat+0.15, '~100 km',
            ha='center', va='bottom', fontsize=8, fontweight='bold', zorder=8)

    # Stats box
    stats_box = (
        f'National Summary\n'
        f'─────────────\n'
        f'Cities analysed : {len(cities)}\n'
        f'Cities w/ {spot_label.lower()}s: {n_with_spots}\n'
        f'Total area (km²): {total_area_km2:.0f}\n'
        f'Day   {pop_word}  : {_fmt_pop5e(total_day_pop)}\n'
        f'Night {pop_word}  : {_fmt_pop5e(total_night_pop)}'
    )
    ax.text(0.98, 0.01, stats_box, transform=ax.transAxes,
            fontsize=8, va='bottom', ha='right',
            bbox=dict(boxstyle='round,pad=0.5', fc='white', ec='#AAA', alpha=0.9),
            fontfamily='monospace', zorder=10)

    # Proportional circle legend (population scale) — bottom right, above stats box
    _prop_ins = ax.inset_axes([0.77, 0.14, 0.20, 0.20])
    _prop_ins.set_xlim(0, 10); _prop_ins.set_ylim(0, 10)
    _prop_ins.set_facecolor('white'); _prop_ins.patch.set_alpha(0.92)
    _prop_ins.patch.set_edgecolor('#AAAAAA'); _prop_ins.patch.set_linewidth(0.8)
    _prop_ins.axis('off')
    _prop_ins.text(5, 9.3, scale_title, ha='center', va='top',
                   fontsize=6, fontweight='bold')
    _ref_pops5e = [max_pop, max_pop * 0.35, max_pop * 0.08]
    _ref_lbl5e  = [_fmt_pop5e(p) for p in _ref_pops5e]
    for _ri, (_rp, _rl) in enumerate(zip(_ref_pops5e, _ref_lbl5e)):
        _rr = 2.0 * (_rp / max_pop) ** 0.5
        _yc = 7.0 - _ri * 3.0
        _prop_ins.add_patch(_Wedge5e((3, _yc), _rr, 0, 360,
                                     facecolor=DAY_CLR, edgecolor='white',
                                     lw=0.6, alpha=0.88))
        _prop_ins.text(3 + _rr + 0.4, _yc, _rl, va='center', ha='left', fontsize=6)

    plt.tight_layout()
    return fig


def create_hotspot_area_by_contour_plots(hotspot_polygons_enriched, landscape_gdf_4326,
                                         output_dir: Path, skip_if_exists: bool = True,
                                         cities_per_page: int = 10):
    """
    Create grouped stacked bar charts showing hotspot area distribution by contour level,
    stacked by Cluster25 landscape classes. Only P90 and GI_STAR methods (excl. VALIDATED).
    
    Paginated: *cities_per_page* cities per figure page (default 10).
    Multi-page PDF via ``PdfPages``; individual SVGs per page.
    
    Visualization (per page):
    - 3 vertically stacked facets (Day, Night, Persistent)
    - Per city: 6 bars (2 methods × 3 contours)
    - Each bar stacked by Cluster25 landscape colours
    - Patch count annotated above each bar
    
    Args:
        hotspot_polygons_enriched: GeoDataFrame with city, method, period, contour_level, Cluster25, area_km2
        landscape_gdf_4326: GeoDataFrame with Cluster25 classification details
        output_dir: Directory to save plots (figures/)
        skip_if_exists: Skip if outputs already exist
        cities_per_page: Number of cities per figure page (default: 10)
    
    Returns:
        dict with paths to saved files
    """
    from matplotlib.patches import Patch
    from matplotlib.backends.backend_pdf import PdfPages
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
    
    # Define output paths
    pdf_path = output_dir / 'hotspot_area_by_contour_cluster25.pdf'
    svg_path = output_dir / 'hotspot_area_by_contour_cluster25.svg'
    table1_path = output_dir / 'table1_hotspot_characterization.csv'
    table2_path = output_dir / 'table2_cluster25_colors.csv'
    
    # Check if outputs exist
    if skip_if_exists and all(p.exists() for p in [pdf_path, svg_path, table1_path, table2_path]):
        print(f" Plots already exist, skipping")
        return {
            'pdf': pdf_path,
            'svg': svg_path,
            'PDF': pdf_path,
            'SVG': svg_path,
            'table1': table1_path,
            'table2': table2_path,
            'skipped': True,
            'success': True
        }
    
    # =============================================================================
    # PREPARE DATA
    # =============================================================================
    
    # Filter to only P90 and GI_STAR (NO CONFIRMED), exclude contour_level 1.0
    df = hotspot_polygons_enriched[
        (hotspot_polygons_enriched['method'].isin(['P90', 'GI_STAR'])) &
        (hotspot_polygons_enriched['contour_level'] < 1.0)
    ].copy()
    
    if df.empty:
        print(f" No data for P90 or GI_STAR methods")
        return None
    
    # Get unique values
    cities = sorted(df['city'].unique())
    methods = ['P90', 'GI_STAR']  # Only 2 methods
    # Use actual period values from data (capitalized: Day, Night, Persistent)
    periods = sorted(df['period'].unique(), key=lambda x: {'Day': 1, 'Night': 2, 'Persistent': 3}.get(x, 99))
    contour_levels = sorted([c for c in df['contour_level'].unique() if c < 1.0], reverse=True)  # Descending, exclude 1.0
    
    # Get unique Cluster25 classes and use canonical colour palette from config
    cluster25_classes = sorted(df['Cluster25_mode'].dropna().unique())
    n_clusters = len(cluster25_classes)
    
    import importlib as _il
    try:
        import config as _cfg_mod
        _il.reload(_cfg_mod)
        _canonical_colors = getattr(_cfg_mod, 'CLUSTER25_COLORS', {})
    except Exception:
        _canonical_colors = {}
    
    # Build cluster_colors dict – canonical first, fallback grey for unknowns
    cluster_colors = {}
    for cluster in cluster25_classes:
        cluster_colors[cluster] = _canonical_colors.get(int(cluster), '#d9d9d9')
    
    # Calculate area by city-method-period-contour-Cluster25_mode
    area_by_contour_cluster = df.groupby(
        ['city', 'method', 'period', 'contour_level', 'Cluster25_mode']
    ).agg({
        'area_km2': 'sum',
        'hotspot_id': 'count'
    }).reset_index()
    area_by_contour_cluster.rename(columns={'hotspot_id': 'n_polygons'}, inplace=True)
    
    # Calculate total patches per city-method-period-contour (for annotation)
    patch_counts = df.groupby(
        ['city', 'method', 'period', 'contour_level']
    )['hotspot_id'].count().reset_index(name='total_patches')
    
    # Pivot for stacked bar structure
    pivot_area = area_by_contour_cluster.pivot_table(
        index=['city', 'method', 'period', 'contour_level'],
        columns='Cluster25_mode',
        values='area_km2',
        fill_value=0
    )
    
    # =============================================================================
    # CREATE PAGINATED FIGURES - cities_per_page cities per page
    # Each page: 3 row panels (Day, Night, Persistent)
    # Multi-page PDF via PdfPages; individual SVGs numbered by page
    # =============================================================================
    
    n_cities = len(cities)
    n_methods = len(methods)
    n_contours = len(contour_levels)
    bars_per_method = n_contours                   # 3
    bars_per_city = n_methods * n_contours          # 6
    
    # Display order: Day (top), Night (middle), Persistent (bottom)
    display_order = [p for p in ['Day', 'Night', 'Persistent'] if p in periods]
    for p in periods:
        if p not in display_order:
            display_order.append(p)
    n_panels = len(display_order)
    
    # Chunk cities into pages
    city_chunks = [cities[i:i + cities_per_page] for i in range(0, n_cities, cities_per_page)]
    n_pages = len(city_chunks)
    
    # Collect per-page SVG paths
    svg_paths = []
    
    pdf_pages = None
    pdf_export_ok = True
    try:
        pdf_pages = PdfPages(str(pdf_path))
    except Exception as e:
        pdf_export_ok = False
        print(f"Warning: PDF export disabled for this run ({e}). Continuing with SVG exports.")

    for page_idx, page_cities in enumerate(city_chunks):
        n_page_cities = len(page_cities)

        # --- x-position geometry (compact) ---------------------------------
        bar_w = 0.38
        intra_gap = 0.04
        inter_gap = bar_w * 0.45
        city_gap = bar_w * 1.4

        x_positions = []
        contour_labels_x = []
        method_labels_x = []
        city_labels_x = []
        city_dividers = []
        method_dividers = []

        cursor = 0.0
        for ci, city in enumerate(page_cities):
            city_start = cursor
            for mi, method in enumerate(methods):
                method_start = cursor
                for coi, contour in enumerate(contour_levels):
                    x_positions.append(cursor)
                    pct = int(contour * 100)
                    contour_labels_x.append((cursor, f'{pct}%'))
                    cursor += bar_w + intra_gap
                cursor -= intra_gap
                method_center = (method_start + cursor) / 2
                method_label = 'P90' if method == 'P90' else 'Gi*'
                method_labels_x.append((method_center, method_label))
                if mi < n_methods - 1:
                    method_dividers.append(cursor + inter_gap / 2)
                cursor += inter_gap
            cursor -= inter_gap
            city_center = (city_start + cursor) / 2
            city_labels_x.append((city_center, city))
            cursor += city_gap
            if ci < n_page_cities - 1:
                city_dividers.append(cursor - city_gap / 2)

        total_width = cursor - city_gap

        # --- Compact figure sizing -----------------------------------------
        fig_w = max(10, total_width * 0.85 + 1.5)
        panel_h = max(2.5, fig_w * 0.14)
        fig_h = panel_h * n_panels + 1.8

        fig, axes = plt.subplots(n_panels, 1, figsize=(fig_w, fig_h),
                                 sharex=True, sharey=True)
        if n_panels == 1:
            axes = [axes]

        fig.subplots_adjust(hspace=0)

        page_label = f' (Page {page_idx + 1}/{n_pages})' if n_pages > 1 else ''
        fig.suptitle(
            f'Hotspot Area Distribution by Contour Level & Landscape Character (Cluster25){page_label}',
            fontsize=13, fontweight='bold', y=0.97)

        # --- Draw each panel -----------------------------------------------
        for ax_idx, ax in enumerate(axes):
            if ax_idx >= len(display_order):
                ax.set_visible(False)
                continue

            period = display_order[ax_idx]

            try:
                period_area = pivot_area.xs(period, level='period')
            except KeyError:
                ax.text(0.5, 0.5, f'No Data for {period}',
                       ha='center', va='center', fontsize=11, transform=ax.transAxes)
                ax.set_ylabel(f'{period}\n\nArea (km²)',
                             fontsize=10, fontweight='bold', labelpad=6)
                continue

            period_patches = patch_counts[patch_counts['period'] == period]

            bar_idx = 0
            for ci, city in enumerate(page_cities):
                for mi, method in enumerate(methods):
                    for coi, contour in enumerate(contour_levels):
                        x = x_positions[bar_idx]
                        bar_idx += 1

                        bottom = 0
                        for cluster in cluster25_classes:
                            if (city, method, contour) in period_area.index:
                                area = period_area.loc[(city, method, contour), cluster]
                                if area > 0:
                                    ax.bar(x, area, bar_w, bottom=bottom,
                                           color=cluster_colors[cluster],
                                           edgecolor='white', linewidth=0.2)
                                    bottom += area

            ax.autoscale(axis='y')
            y_lo, y_hi = ax.get_ylim()
            nudge = y_hi * 0.018 if y_hi > 0 else 0.3

            # Patch-count annotations
            bar_idx = 0
            for ci, city in enumerate(page_cities):
                for mi, method in enumerate(methods):
                    for coi, contour in enumerate(contour_levels):
                        x = x_positions[bar_idx]
                        bar_idx += 1

                        bar_top = 0
                        if (city, method, contour) in period_area.index:
                            bar_top = period_area.loc[(city, method, contour)].sum()

                        patch_row = period_patches[
                            (period_patches['city'] == city) &
                            (period_patches['method'] == method) &
                            (period_patches['contour_level'] == contour)
                        ]
                        if not patch_row.empty and bar_top > 0:
                            n_patches = patch_row.iloc[0]['total_patches']
                            ax.text(x, bar_top + nudge, str(n_patches),
                                   ha='center', va='bottom', fontsize=8,
                                   fontweight='bold', color='#333333')

            # --- Styling ---
            ax.set_ylabel(f'{period}\n\nArea (km²)',
                         fontsize=10, fontweight='bold', labelpad=6)
            ax.grid(axis='y', alpha=0.25, linestyle='--', zorder=0)
            ax.set_xlim(-bar_w * 0.8, total_width + bar_w * 0.8)
            ax.tick_params(axis='y', labelsize=9)
            ax.axhline(0, color='black', linewidth=0.8, zorder=2)

            for xd in city_dividers:
                ax.axvline(xd, color='#666666', linewidth=0.9, linestyle='-', alpha=0.6, zorder=0)
            for xd in method_dividers:
                ax.axvline(xd, color='#aaaaaa', linewidth=0.6, linestyle='--', alpha=0.5, zorder=0)

            if ax_idx < n_panels - 1:
                ax.tick_params(axis='x', labelbottom=False, length=0)
            if ax_idx > 0:
                ax.spines['top'].set_visible(False)
            if ax_idx < n_panels - 1:
                ax.spines['bottom'].set_visible(False)

        # --- X-axis label hierarchy (bottom panel only) --------------------
        bottom_ax = axes[-1]

        bottom_ax.set_xticks([pos for pos, _ in contour_labels_x])
        bottom_ax.set_xticklabels([lbl for _, lbl in contour_labels_x],
                                   fontsize=9, rotation=0)
        bottom_ax.tick_params(axis='x', which='major', pad=2, length=3)

        for mx, mlbl in method_labels_x:
            bottom_ax.text(mx, -0.10, mlbl,
                          ha='center', va='top', fontsize=10, fontweight='bold',
                          transform=bottom_ax.get_xaxis_transform())

        for cx, clbl in city_labels_x:
            bottom_ax.text(cx, -0.20, clbl,
                          ha='center', va='top', fontsize=11, fontweight='bold',
                          transform=bottom_ax.get_xaxis_transform())

        plt.tight_layout(rect=[0, 0.07, 1, 0.95])
        fig.subplots_adjust(hspace=0)

        # Save page to multi-page PDF (best-effort; continue if backend is incompatible)
        if pdf_pages is not None:
            try:
                pdf_pages.savefig(fig, dpi=300, bbox_inches='tight')
            except Exception as e:
                pdf_export_ok = False
                print(f"Warning: PDF page export skipped due to backend incompatibility ({e}).")
                try:
                    pdf_pages.close()
                except Exception:
                    pass
                pdf_pages = None

        # Save individual SVG per page
        if n_pages == 1:
            page_svg = svg_path
        else:
            page_svg = output_dir / f'hotspot_area_by_contour_cluster25_page{page_idx + 1}.svg'
        plt.savefig(page_svg, dpi=300, format='svg', bbox_inches='tight')
        svg_paths.append(page_svg)
        plt.close(fig)

    if pdf_pages is not None:
        try:
            pdf_pages.close()
        except Exception:
            pass

    if pdf_export_ok and pdf_path.exists():
        print(f" Saved hotspot area plots: {pdf_path.name} ({n_pages} page{'s' if n_pages > 1 else ''})")
    else:
        print(" Saved hotspot area plots without PDF (SVG exports completed).")
    
    # =============================================================================
    # GENERATE TABLE 1: Hotspot Characterization
    # =============================================================================
    
    # Calculate dominant Cluster25 and top 3 for each city-method-period-contour
    characterization_rows = []
    
    for (city, method, period, contour), group in area_by_contour_cluster.groupby(
        ['city', 'method', 'period', 'contour_level']
    ):
        # Sort by area descending
        group_sorted = group.sort_values('area_km2', ascending=False)
        
        # Dominant Cluster25
        dominant_cluster = group_sorted.iloc[0]['Cluster25_mode']
        total_area = group_sorted['area_km2'].sum()
        dominant_area = group_sorted.iloc[0]['area_km2']
        dominant_pct = 100 * dominant_area / total_area
        
        # Top 3 Cluster25 classes
        top3 = group_sorted.head(3)
        top3_str = ', '.join([
            f"{row['Cluster25_mode']} ({100*row['area_km2']/total_area:.0f}%)"
            for _, row in top3.iterrows()
        ])
        
        # Total patches
        n_polygons = group['n_polygons'].sum()
        mean_area = total_area / n_polygons if n_polygons > 0 else 0
        
        characterization_rows.append({
            'City': city,
            'Period': period,
            'Method': method,
            'Contour': contour,
            'N_Polygons': n_polygons,
            'Total_Area_km²': round(total_area, 2),
            'Mean_Area_km²': round(mean_area, 2),
            'Dominant_Cluster25': dominant_cluster,
            'Dominant_%': round(dominant_pct, 1),
            'Top_3_Cluster25_Classes': top3_str
        })
    
    table1_df = pd.DataFrame(characterization_rows)
    table1_df = table1_df.sort_values(['City', 'Period', 'Method', 'Contour'])
    table1_df.to_csv(table1_path, index=False)
    print(f" Saved Table 1: {table1_path.name}")
    
    # =============================================================================
    # GENERATE TABLE 2: Cluster25 with Colors
    # =============================================================================
    
    # Extract Cluster25 classification from landscape_gdf_4326
    # Assuming columns: Cluster25, Climate_Class, Geology_Class, Elevation_Class
    
    cluster25_info = []
    
    for cluster in cluster25_classes:
        # Get landscape info for this cluster
        cluster_rows = landscape_gdf_4326[landscape_gdf_4326['Cluster25'] == cluster]
        
        if not cluster_rows.empty:
            # Take first row (all should have same classification)
            row = cluster_rows.iloc[0]
            
            # Get color hex (already stored as hex string)
            color_hex = cluster_colors[cluster]
            
            # Build description from climate, geology, elevation
            climate = row.get('Climate_Class', 'Unknown')
            geology = row.get('Geology_Class', 'Unknown')
            elevation_raw = str(row.get('Elevation_Class', 'Unknown'))
            
            # Parse elevation to extract clean range
            if 'Very Low' in elevation_raw or '0-100m' in elevation_raw:
                elev_range = '0-100m'
                elev_label = 'Very Low'
            elif 'Low' in elevation_raw or '101-500m' in elevation_raw:
                elev_range = '101-500m'
                elev_label = 'Low'
            elif 'Moderate' in elevation_raw or '501-1000m' in elevation_raw:
                elev_range = '501-1000m'
                elev_label = 'Moderate'
            elif 'High' in elevation_raw or '1001-1500m' in elevation_raw:
                elev_range = '1001-1500m'
                elev_label = 'High'
            elif 'Very High' in elevation_raw or '>1500m' in elevation_raw:
                elev_range = '>1500m'
                elev_label = 'Very High'
            else:
                elev_range = elevation_raw
                elev_label = elevation_raw
            
            description = f"{geology} terrain at {elev_range} with {climate} climate"
            
            cluster25_info.append({
                'Cluster25': cluster,
                'Color': color_hex,
                'Climate_Class': climate,
                'Geology_Class': geology,
                'Elevation_Class': f"{elev_label} ({elev_range})",
                'Description': description
            })
        else:
            # Fallback if no landscape data found
            color_hex = cluster_colors[cluster]
            
            cluster25_info.append({
                'Cluster25': cluster,
                'Color': color_hex,
                'Climate_Class': 'Unknown',
                'Geology_Class': 'Unknown',
                'Elevation_Class': 'Unknown',
                'Description': f'Cluster {cluster} (no classification data)'
            })
    
    table2_df = pd.DataFrame(cluster25_info)
    table2_df = table2_df.sort_values('Cluster25')
    table2_df.to_csv(table2_path, index=False)
    print(f" Saved Table 2: {table2_path.name}")
    
    primary_svg = svg_path if svg_path.exists() else (svg_paths[0] if svg_paths else svg_path)
    pdf_result = pdf_path if (pdf_export_ok and pdf_path.exists()) else None

    return {
        'pdf': pdf_result,
        'svg': primary_svg,
        'PDF': pdf_result,
        'SVG': primary_svg,
        'table1': table1_path,
        'table2': table2_path,
        'skipped': False,
        'success': True
    }


# ---------------------------------------------------------------------------
# Section 6.4 — Population Exposure Nested Donut Charts
# ---------------------------------------------------------------------------

def _blend_with_white(hex_color: str, factor: float) -> str:
    """Blend a hex colour toward white. factor=0 → original, factor=1 → white."""
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    r = int(r + (255 - r) * factor)
    g = int(g + (255 - g) * factor)
    b = int(b + (255 - b) * factor)
    return f'#{r:02x}{g:02x}{b:02x}'


def create_population_exposure_donuts(
    hotspot_polygons_enriched,
    output_dir: Path,
    skip_if_exists: bool = True,
):
    """
    Create **separate half-donut cross-section** charts per city
    showing population exposed to UHI hotspots.

    Each city gets its own figure (PDF + SVG).  The semicircle faces
    upward; the flat cut edge faces down.  Day occupies the left
    half-ring, Night the right half-ring.

    Rings (inside → outside):
        Ring 1 (inner)  : Period  — Day (left) / Night (right)
        Ring 2 (middle) : Method  — P90 / Gi*
        Ring 3 (outer)  : Contour — 90 % / 75 % / 50 %

    Design:
     Day ☀ / Night ☾ headers placed at the base (below the flat edge)
       Labels on each side connected by leader lines FROM the segment
        midpoint TO the label position
       Leader lines are coloured to match their segment, with small
        filled circles at both endpoints
       Robust overlap resolution keeps labels well-separated
       Zero-population segments are omitted

    Args:
        hotspot_polygons_enriched: GeoDataFrame with city, method, period,
            contour_level, pop_total columns.
        output_dir: Directory to save figures.
        skip_if_exists: If True, skip when all files exist.

    Returns:
        dict with per-city paths and status.
    """
    import importlib
    importlib.reload(config)

    import matplotlib.pyplot as plt
    from matplotlib.patches import Wedge, FancyBboxPatch
    import numpy as np
    import pandas as pd

    #  data prep 
    df = (
        hotspot_polygons_enriched
        .loc[
            hotspot_polygons_enriched['method'].isin(['P90', 'GI_STAR'])
            & hotspot_polygons_enriched['period'].isin(['Day', 'Night'])
        ]
        .copy()
    )

    if df.empty:
        print(" No data matching filter (P90/GI_STAR × Day/Night)")
        return {'skipped': False, 'success': False}

    cities = sorted(df['city'].unique())

    # Check skip
    all_exist = True
    for city in cities:
        slug = city.lower().replace(' ', '_')
        pdf_p = output_dir / f'population_exposure_donut_{slug}.pdf'
        svg_p = output_dir / f'population_exposure_donut_{slug}.svg'
        if not (pdf_p.exists() and svg_p.exists()):
            all_exist = False
            break

    if skip_if_exists and all_exist:
        print(" All per-city donut charts already exist, skipping")
        return {'skipped': True, 'success': True, 'cities': cities}

    #  colour palette 
    period_colors = {
        'Day':   '#E8651A',
        'Night': '#2B6CB0',
    }
    method_offsets = {'P90': 0.0, 'GI_STAR': 0.15}
    ring_fade   = {1: 0.00, 2: 0.30, 3: 0.55}
    contour_extra = {0.9: 0.00, 0.75: 0.12, 0.5: 0.24}

    periods  = ['Day', 'Night']
    methods  = ['P90', 'GI_STAR']
    contours = [0.9, 0.75, 0.5]

    #  ring geometry 
    r_inner = {1: 0.42, 2: 0.72, 3: 1.02}
    r_width = {1: 0.27, 2: 0.27, 3: 0.24}
    outer_max = r_inner[3] + r_width[3]  # 1.26

    #  helpers 
    def _fmt_pop(val):
        """Format population: ≥1000 → '12.3 k', else integer."""
        if val >= 1_000_000:
            return f'{val / 1_000_000:.1f} M'
        elif val >= 1_000:
            return f'{val / 1_000:.1f} k'
        return f'{int(val):,}'

    saved_paths = {}

    for city in cities:
        city_df = df[df['city'] == city]
        agg = (
            city_df
            .groupby(['period', 'method', 'contour_level'], as_index=False)
            ['pop_total'].sum()
        )

        #  figure 
        fig, ax = plt.subplots(
            figsize=(10.0, 6.0),
            subplot_kw=dict(aspect='equal'),
        )

        # Collect label specs per side
        label_specs = []

        #  compute proportional angular spans for Day vs Night 
        # Ring 1 sweep is proportional to actual population, not 50/50.
        period_pops = {}
        for period in periods:
            period_pops[period] = agg.loc[
                agg['period'] == period, 'pop_total'
            ].sum()
        total_pop_all = sum(period_pops.values()) or 1

        # Day occupies the left half (angles measured CCW from 3 o'clock):
        #   Day spans from 90° upward, Night spans from 90° downward (toward 0°).
        day_sweep   = 90 * (period_pops.get('Day', 0)   / total_pop_all) * 2
        night_sweep = 90 * (period_pops.get('Night', 0) / total_pop_all) * 2
        # Clamp so neither exceeds 180° total semicircle
        day_sweep   = min(day_sweep, 180)
        night_sweep = min(night_sweep, 180)

        period_angles = {
            'Day':   (180 - day_sweep, 180),     # left side, ending at 180°
            'Night': (0, night_sweep),            # right side, starting at 0°
        }

        for period in periods:
            semi_start, semi_end = period_angles[period]
            semi_span  = semi_end - semi_start
            if semi_span <= 0:
                continue
            base_color = period_colors[period]
            side       = 'left' if period == 'Day' else 'right'

            #  Ring 1: Period band 
            pop_period = agg.loc[agg['period'] == period, 'pop_total'].sum()
            if pop_period <= 0:
                continue

            color_r1 = _blend_with_white(base_color, ring_fade[1])
            inner1, outer1 = r_inner[1], r_inner[1] + r_width[1]
            ax.add_patch(Wedge(
                (0, 0), outer1, semi_start, semi_end,
                width=r_width[1],
                facecolor=color_r1, edgecolor='white', linewidth=1.8,
            ))

            mid_ang1_deg = (semi_start + semi_end) / 2
            mid_r1   = (inner1 + outer1) / 2
            label_specs.append({
                'mid_ang_deg': mid_ang1_deg,
                'mid_r': mid_r1,
                'side': side, 'ring': 1,
                'text': f'{period}: {_fmt_pop(pop_period)}',
                'color': color_r1, 'fs': 9, 'fw': 'bold',
            })

            #  Ring 2: Method bands 
            method_pops = []
            for m in methods:
                mp = agg.loc[
                    (agg['period'] == period) & (agg['method'] == m),
                    'pop_total',
                ].sum()
                method_pops.append(mp)

            total_period = sum(method_pops) or 1

            ang_cursor2 = semi_start
            for m, mp in zip(methods, method_pops):
                sweep2 = semi_span * (mp / total_period)

                if mp > 0:
                    inner2, outer2 = r_inner[2], r_inner[2] + r_width[2]
                    fade2  = ring_fade[2] + method_offsets[m]
                    color_r2 = _blend_with_white(base_color, fade2)

                    ax.add_patch(Wedge(
                        (0, 0), outer2, ang_cursor2, ang_cursor2 + sweep2,
                        width=r_width[2],
                        facecolor=color_r2, edgecolor='white', linewidth=1.4,
                    ))

                    mid_ang2_deg = ang_cursor2 + sweep2 / 2
                    mid_r2   = (inner2 + outer2) / 2
                    m_label  = m.replace('GI_STAR', 'Gi*')
                    label_specs.append({
                        'mid_ang_deg': mid_ang2_deg,
                        'mid_r': mid_r2,
                        'side': side, 'ring': 2,
                        'text': f'{m_label}: {_fmt_pop(mp)}',
                        'color': color_r2, 'fs': 8, 'fw': 'bold',
                    })

                #  Ring 3: Contour bands 
                contour_pops = []
                for c in contours:
                    cp = agg.loc[
                        (agg['period'] == period)
                        & (agg['method'] == m)
                        & (agg['contour_level'] == c),
                        'pop_total',
                    ].sum()
                    contour_pops.append(cp)

                total_method = sum(contour_pops) or 1

                ang_cursor3 = ang_cursor2
                for c, cp in zip(contours, contour_pops):
                    sweep3 = sweep2 * (cp / total_method)

                    if cp > 0:
                        inner3, outer3 = r_inner[3], r_inner[3] + r_width[3]
                        fade3  = ring_fade[3] + method_offsets[m] + contour_extra[c]
                        color_r3 = _blend_with_white(base_color, fade3)

                        ax.add_patch(Wedge(
                            (0, 0), outer3, ang_cursor3, ang_cursor3 + sweep3,
                            width=r_width[3],
                            facecolor=color_r3, edgecolor='white', linewidth=1.0,
                        ))

                        mid_ang3_deg = ang_cursor3 + sweep3 / 2
                        mid_r3   = (inner3 + outer3) / 2
                        label_specs.append({
                            'mid_ang_deg': mid_ang3_deg,
                            'mid_r': mid_r3,
                            'side': side, 'ring': 3,
                            'text': f'{int(c * 100)}%: {_fmt_pop(cp)}',
                            'color': color_r3, 'fs': 7.5, 'fw': 'normal',
                        })

                    ang_cursor3 += sweep3
                ang_cursor2 += sweep2

        #  label segments directly at their midpoints 
        # Filled circle at segment midpoint; horizontal text beside it.
        # Day (left) labels sit LEFT of dot, Night (right) sit RIGHT.
        # Overlap prevention: spread labels vertically per side so
        # no two are closer than min_gap.

        day_dark   = period_colors['Day']
        night_dark = period_colors['Night']
        dot_size   = 4

        # Pre-compute dot positions
        for spec in label_specs:
            ang_rad = np.deg2rad(spec['mid_ang_deg'])
            mid_r   = spec['mid_r']
            spec['dot_x'] = mid_r * np.cos(ang_rad)
            spec['dot_y'] = mid_r * np.sin(ang_rad)
            spec['label_y'] = spec['dot_y']   # initial

        #  vertical overlap prevention per side 
        min_gap = 0.085
        for side_name in ('left', 'right'):
            group = [s for s in label_specs if s['side'] == side_name]
            if len(group) <= 1:
                continue
            # Sort top-to-bottom by dot_y
            group.sort(key=lambda s: -s['dot_y'])
            # Push apart (top-to-bottom)
            for i in range(1, len(group)):
                if group[i - 1]['label_y'] - group[i]['label_y'] < min_gap:
                    group[i]['label_y'] = group[i - 1]['label_y'] - min_gap

        #  draw dots + labels 
        for spec in label_specs:
            side = spec['side']
            dark = day_dark if side == 'left' else night_dark

            dx, dy = spec['dot_x'], spec['dot_y']
            ly     = spec['label_y']

            # Filled circle at the segment midpoint
            ax.plot(dx, dy, 'o',
                    color=dark, markersize=dot_size,
                    markeredgecolor='white', markeredgewidth=0.5,
                    zorder=7)

            # Horizontal text at (possibly shifted) label_y
            if side == 'left':
                ha = 'right'
                label_txt = f'{spec["text"]}  '
                tx = dx
            else:
                ha = 'left'
                label_txt = f'  {spec["text"]}'
                tx = dx

            ax.text(
                tx, ly, label_txt,
                ha=ha, va='center',
                fontsize=spec['fs'], fontweight=spec['fw'],
                color=dark,
                zorder=8,
                bbox=dict(boxstyle='round,pad=0.02', fc='white',
                          ec='none', alpha=0.7),
            )

        #  centre annotation 
        city_total = int(city_df['pop_total'].sum())
        ax.text(0, 0.22, city, ha='center', va='center',
                fontsize=16, fontweight='bold', color='#1a1a1a')
        ax.text(0, 0.04, _fmt_pop(city_total), ha='center', va='center',
                fontsize=18, color='#222222', fontweight='bold')
        ax.text(0, -0.09, 'persons exposed', ha='center', va='center',
                fontsize=8.5, color='#888888', style='italic')

        #  "Day" / "Night" at the BASE (below flat edge) 
        base_y = -0.22
        ax.text(-0.55, base_y, 'Day', ha='center', va='top',
                fontsize=12, fontweight='bold', color=day_dark)
        ax.text(0.55, base_y, 'Night', ha='center', va='top',
                fontsize=12, fontweight='bold', color=night_dark)
        # Thin separator line on the flat edge
        ax.plot([-outer_max, outer_max], [0, 0],
                color='#cccccc', lw=0.6, zorder=1)

        #  ring-name labels on the flat edge (at y=0) 
        # Place ring names along the bottom baseline so they don't
        # overlap segment labels at the top of the arc.
        for ring_id, ring_name in [(1, 'Period'), (2, 'Method'), (3, 'Contour')]:
            mid_r = r_inner[ring_id] + r_width[ring_id] / 2
            ax.text(mid_r, -0.04, ring_name, ha='center', va='top',
                    fontsize=6.5, color='#777777', style='italic')

        #  title 
        ax.set_title(
            f'Population Exposed to UHI Hotspots — {city}',
            fontsize=13, fontweight='bold', pad=18, color='#1a1a1a',
        )

        #  axis limits 
        margin = 0.65
        ax.set_xlim(-(outer_max + margin), outer_max + margin)
        ax.set_ylim(-0.55, outer_max + 0.55)
        ax.set_axis_off()

        fig.tight_layout()

        #  save per-city 
        slug = city.lower().replace(' ', '_')
        pdf_path = output_dir / f'population_exposure_donut_{slug}.pdf'
        svg_path = output_dir / f'population_exposure_donut_{slug}.svg'
        fig.savefig(svg_path, format='svg', dpi=300, bbox_inches='tight')
        fig.savefig(pdf_path, format='pdf', dpi=300, bbox_inches='tight')
        plt.close(fig)
        print(f"   {city}: {svg_path.name} / {pdf_path.name}")
        saved_paths[city] = {'pdf': pdf_path, 'svg': svg_path, 'PDF': pdf_path, 'SVG': svg_path}

    return {
        'cities': saved_paths,
        'skipped': False,
        'success': True,
    }


def create_nigeria_population_exposure_summary(
    hotspot_polygons_enriched,
    output_dir: Path,
    skip_if_exists: bool = True,
    country_label: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build AOI-level Section 6.4 summary table and create one composite
    half-donut for the whole country.

    Table columns:
        AOI | Level | Diurnality | Sub-total Population |
        Total Population (across the sub-totals)

    The national donut is created from aggregated P90/GI_STAR x Day/Night x
    contour-level totals so it is directly comparable with city-level donuts.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not country_label:
        boundary_name = Path(config.AOI_DATA_PATHS.get('boundary_geojson', '')).stem
        if boundary_name.lower().startswith('boundary_'):
            country_label = boundary_name.split('_', 1)[1].replace('_', ' ').strip().title()
        else:
            country_label = 'National'

    required_cols = {'city', 'method', 'period', 'contour_level', 'pop_total'}
    missing = required_cols.difference(set(hotspot_polygons_enriched.columns))
    if missing:
        raise ValueError(
            f"Missing required columns for Section 6.4 summary: {sorted(missing)}"
        )

    df = hotspot_polygons_enriched.loc[
        hotspot_polygons_enriched['method'].isin(['P90', 'GI_STAR'])
        & hotspot_polygons_enriched['period'].isin(['Day', 'Night']),
        ['city', 'method', 'period', 'contour_level', 'pop_total'],
    ].copy()

    if df.empty:
        return {'success': False, 'skipped': False, 'reason': 'No matching rows after filter'}

    # AOI-level table requested by user.
    aoi_level = (
        df.groupby(['city', 'contour_level', 'period'], as_index=False)['pop_total']
          .sum()
          .rename(
              columns={
                  'city': 'AOI',
                  'contour_level': 'Level',
                  'period': 'Diurnality (day/night)',
                  'pop_total': 'Sub-total Population',
              }
          )
    )
    aoi_level['Level'] = (aoi_level['Level'] * 100).round(0).astype(int).astype(str) + '%'
    aoi_level['Total Population (across the sub-totals)'] = (
        aoi_level.groupby('AOI')['Sub-total Population'].transform('sum')
    )

    # National roll-up rows (same schema as AOI rows).
    national_rows = (
        aoi_level.groupby(['Level', 'Diurnality (day/night)'], as_index=False)['Sub-total Population']
                 .sum()
    )
    national_rows.insert(0, 'AOI', country_label)
    national_total = national_rows['Sub-total Population'].sum()
    national_rows['Total Population (across the sub-totals)'] = national_total

    summary_table = pd.concat([aoi_level, national_rows], ignore_index=True)
    summary_table = summary_table.sort_values(
        by=['AOI', 'Diurnality (day/night)', 'Level'],
        key=lambda s: s.map({'Day': 0, 'Night': 1}) if s.name == 'Diurnality (day/night)' else s,
    )

    summary_csv = output_dir / 'population_exposure_summary_aoi_level.csv'
    summary_table.to_csv(summary_csv, index=False)

    # Build country-level donut input and reuse the existing renderer.
    national_donut_df = (
        df.groupby(['period', 'method', 'contour_level'], as_index=False)['pop_total']
          .sum()
    )
    national_donut_df['city'] = country_label

    donut_result = create_population_exposure_donuts(
        hotspot_polygons_enriched=national_donut_df,
        output_dir=output_dir,
        skip_if_exists=skip_if_exists,
    )

    donut_paths = None
    if isinstance(donut_result.get('cities'), dict):
        donut_paths = donut_result['cities'].get(country_label)

    if donut_paths is None:
        slug = country_label.lower().replace(' ', '_')
        donut_paths = {
            'svg': output_dir / f'population_exposure_donut_{slug}.svg',
            'pdf': output_dir / f'population_exposure_donut_{slug}.pdf',
            'SVG': output_dir / f'population_exposure_donut_{slug}.svg',
            'PDF': output_dir / f'population_exposure_donut_{slug}.pdf',
        }

    return {
        'success': bool(donut_result.get('success', False)),
        'skipped': bool(donut_result.get('skipped', False)),
        'table_csv': summary_csv,
        'donut': donut_paths,
        'country': country_label,
        'n_aoi_rows': int(len(aoi_level)),
        'n_national_rows': int(len(national_rows)),
    }


def create_national_summary_map(
    hotspots_gdf: gpd.GeoDataFrame,
    landscape_gdf: gpd.GeoDataFrame,
    nigeria_gdf: gpd.GeoDataFrame,
    cluster25_colors: Dict[str, str],
    output_dir: Path,
    figsize: Tuple[float, float] = (10, 10),
    day_color: str = '#FF9500',
    night_color: str = '#4A4A4A',
    scale_factor: float = 1.0,
    show_plot: bool = True,
) -> Dict[str, Any]:
    """
    Create a national summary map with proportional symbols showing
    UHI hotspot population exposure by city on a Cluster25 base layer.
    
    Args:
        hotspots_gdf: GeoDataFrame with hotspot polygons containing 'city', 
                      'period', 'pop_total', 'method', and 'area_km2' columns
        landscape_gdf: GeoDataFrame with landscape/Cluster25 data
        nigeria_gdf: GeoDataFrame with Nigeria national boundary
        cluster25_colors: Dict mapping Cluster25 classes to hex colors
        output_dir: Base output directory (maps subdir will be used)
        figsize: Figure size (width, height in inches)
        day_color: Hex color for day exposure wedges
        night_color: Hex color for night exposure wedges
        scale_factor: Scale factor for proportional circles
        show_plot: Whether to display the plot
        
    Returns:
        Dict with paths to saved files and summary statistics
    """
    from matplotlib.patches import Wedge
    import matplotlib.patches as mpatches
    
    # Ensure output directory exists
    maps_dir = Path(output_dir) / 'maps'
    maps_dir.mkdir(parents=True, exist_ok=True)
    
    # -------------------------------------------------------------------------
    # Compute population exposure statistics
    # -------------------------------------------------------------------------
    
    def format_population(pop):
        """Format population: use 'k' for thousands, plain number for hundreds."""
        if pop >= 1000:
            return f'{pop/1000:.1f}k'
        else:
            return f'{pop:.0f}'
    
    # Aggregate by city and period
    city_period_pop = hotspots_gdf.groupby(['city', 'period'])['pop_total'].sum().reset_index()
    city_stats = city_period_pop.pivot(index='city', columns='period', values='pop_total').fillna(0)
    
    # Ensure Day and Night columns exist
    for col in ['Day', 'Night']:
        if col not in city_stats.columns:
            city_stats[col] = 0
    
    city_stats['Total'] = city_stats['Day'] + city_stats['Night']
    
    # Compute city centroids dynamically from hotspot polygons
    city_dissolved = hotspots_gdf.dissolve(by='city')
    city_centroids = city_dissolved.geometry.centroid
    
    # Add coordinates (lon = x, lat = y)
    city_stats['lon'] = city_stats.index.map(lambda c: city_centroids[c].x)
    city_stats['lat'] = city_stats.index.map(lambda c: city_centroids[c].y)
    
    # Overall totals
    total_day = city_stats['Day'].sum()
    total_night = city_stats['Night'].sum()
    total_all = city_stats['Total'].sum()
    n_cities = len(city_stats)
    
    # -------------------------------------------------------------------------
    # Prepare base layer
    # -------------------------------------------------------------------------
    
    # Dissolve landscape by Cluster25 + map colors
    landscape_merged = landscape_gdf.dissolve(by='Cluster25', as_index=False)
    landscape_merged['color'] = landscape_merged['Cluster25'].map(cluster25_colors)
    
    # -------------------------------------------------------------------------
    # Create map
    # -------------------------------------------------------------------------
    
    fig, ax = plt.subplots(figsize=figsize)
    
    # Plot Cluster25 base layer
    landscape_merged.plot(
        ax=ax, color=landscape_merged['color'],
        edgecolor='white', linewidth=0.3, alpha=0.6, zorder=1
    )
    
    # Plot Nigeria boundary
    nigeria_gdf.plot(ax=ax, facecolor='none', edgecolor='#333333', linewidth=1.5, zorder=2)
    
    # Scale factor for circles
    max_pop = city_stats['Total'].max()
    
    # Draw proportional symbols
    label_texts = []  # collect for adjustText de-cluttering
    label_x = []
    label_y = []
    
    for city in city_stats.index:
        row = city_stats.loc[city]
        lat, lon = row['lat'], row['lon']
        day_pop, night_pop, total_pop = row['Day'], row['Night'], row['Total']
        
        if total_pop == 0:
            continue
        
        radius_deg = scale_factor * np.sqrt(total_pop / max_pop)
        
        # Calculate proportional angles for Day and Night
        day_fraction = day_pop / total_pop
        night_fraction = night_pop / total_pop
        
        # Wedge angles: start at top (90°), going counterclockwise
        day_start = 90
        day_end = 90 + day_fraction * 360
        night_start = day_end
        night_end = 450  # 90 + 360 (full circle back to start)
        
        # Adaptive edge linewidth (thinner for smaller circles)
        edge_lw = max(0.5, min(2.0, radius_deg * 3))
        
        # Day wedge (proportional)
        if day_pop > 0:
            ax.add_patch(Wedge((lon, lat), radius_deg, day_start, day_end,
                               facecolor=day_color, edgecolor='white',
                               linewidth=edge_lw, alpha=0.9, zorder=5))
        
        # Night wedge (proportional)
        if night_pop > 0:
            ax.add_patch(Wedge((lon, lat), radius_deg, night_start, night_end,
                               facecolor=night_color, edgecolor='white',
                               linewidth=edge_lw, alpha=0.9, zorder=5))
        
        # City centroid as black dot
        ax.plot(lon, lat, 'ko', markersize=3, zorder=7)
        
        # City name with population — collect for adjustText
        label_text = f"{city}\n({format_population(total_pop)})"
        txt = ax.text(lon, lat - radius_deg - 0.12, label_text,
                     ha='center', va='top',
                     fontsize=7.5, fontweight='bold', color='#000',
                     zorder=6, linespacing=0.9)
        label_texts.append(txt)
        label_x.append(lon)
        label_y.append(lat - radius_deg - 0.12)
    
    # De-clutter overlapping labels using adjustText
    try:
        from adjustText import adjust_text
        adjust_text(label_texts, x=label_x, y=label_y, ax=ax,
                    force_text=(0.4, 0.6), force_points=(0.3, 0.5),
                    expand_text=(1.1, 1.2), expand_points=(1.1, 1.2),
                    arrowprops=dict(arrowstyle='-', color='#888888', lw=0.5),
                    ensure_inside_axes=True, max_move=2.0)
    except ImportError:
        pass  # adjustText not installed — labels stay at default positions
    
    # Title
    ax.set_title('Urban Heat Island Hotspots — Population Exposure by City',
                 fontsize=14, fontweight='bold', pad=15)
    
    # Create legend with title, placed at bottom left
    legend_elements = [
        mpatches.Patch(facecolor=day_color, edgecolor='white', label='Day Exposure', alpha=0.9),
        mpatches.Patch(facecolor=night_color, edgecolor='white', label='Night Exposure', alpha=0.9),
        mpatches.Patch(facecolor='none', edgecolor='#333333', linewidth=1.5, label='National Boundary'),
        plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='black', markersize=6, label='City'),
    ]
    ax.legend(handles=legend_elements, loc='lower left', fontsize=9, framealpha=0.95,
              edgecolor='#999', title='Legend', title_fontsize=10)
    
    # -------------------------------------------------------------------------
    # Calculate statistics for summary box
    # -------------------------------------------------------------------------
    
    # Calculate total hotspot area
    if 'area_km2' in hotspots_gdf.columns:
        total_hotspot_area_km2 = hotspots_gdf['area_km2'].sum()
    else:
        hotspots_projected = hotspots_gdf.to_crs(epsg=32632)
        total_hotspot_area_km2 = hotspots_projected.geometry.area.sum() / 1e6
    
    # Calculate significant hotspots (Gi* method)
    gi_star_hotspots = hotspots_gdf[hotspots_gdf['method'] == 'GI_STAR']
    n_gi_star = len(gi_star_hotspots)
    if 'area_km2' in gi_star_hotspots.columns:
        gi_star_area_km2 = gi_star_hotspots['area_km2'].sum()
    else:
        gi_star_projected = gi_star_hotspots.to_crs(epsg=32632)
        gi_star_area_km2 = gi_star_projected.geometry.area.sum() / 1e6
    
    # Calculate Gi* population at risk
    gi_star_pop = gi_star_hotspots['pop_total'].sum() if 'pop_total' in gi_star_hotspots.columns else 0
    
    stats_text = f'''National Summary

Cities Analyzed: {n_cities}
Hotspots Detected: {len(hotspots_gdf)} ({total_hotspot_area_km2:.1f} km²)
Population at Risk - Day/Night: {format_population(total_day)} | {format_population(total_night)}

Significant Hotspots (Gi*): {n_gi_star} ({gi_star_area_km2:.1f} km²)
Total Population at Risk (Gi*): {format_population(gi_star_pop)}

*Circle size ∝ population exposure'''
    
    ax.text(0.98, 0.14, stats_text, transform=ax.transAxes, fontsize=7.5,
            ha='right', va='bottom', family='monospace', zorder=10)
    
    # -------------------------------------------------------------------------
    # Formatting
    # -------------------------------------------------------------------------
    
    ax.set_xlabel('Longitude', fontsize=10)
    ax.set_ylabel('Latitude', fontsize=10)
    ax.grid(True, alpha=0.15, linestyle='--', linewidth=0.5, zorder=0)
    ax.set_aspect('equal')
    
    # Expand bounds to include Lagos and labels
    bounds = nigeria_gdf.total_bounds
    ax.set_xlim(bounds[0] - 0.5, bounds[2] + 0.5)
    ax.set_ylim(bounds[1] - 1.0, bounds[3] + 0.5)
    
    # -------------------------------------------------------------------------
    # Scale bar at bottom center (100 km  0.9 degrees at equator)
    # -------------------------------------------------------------------------
    
    scale_center_lon = (bounds[0] + bounds[2]) / 2
    scale_half_deg = 0.45  # 0.9 degrees total  100 km
    scale_lon_start = scale_center_lon - scale_half_deg
    scale_lon_end = scale_center_lon + scale_half_deg
    scale_lat = bounds[1] - 0.7
    
    ax.plot([scale_lon_start, scale_lon_end], [scale_lat, scale_lat], 'k-', linewidth=3, zorder=8)
    ax.plot([scale_lon_start, scale_lon_start], [scale_lat - 0.1, scale_lat + 0.1], 'k-', linewidth=2, zorder=8)
    ax.plot([scale_lon_end, scale_lon_end], [scale_lat - 0.1, scale_lat + 0.1], 'k-', linewidth=2, zorder=8)
    ax.text(scale_center_lon, scale_lat + 0.15, '100 km',
            ha='center', va='bottom', fontsize=8, fontweight='bold', zorder=8)
    
    # -------------------------------------------------------------------------
    # North arrow - upper right corner
    # -------------------------------------------------------------------------
    
    arrow_props = dict(arrowstyle='->', lw=2, color='black')
    ax.annotate('N', xy=(0.96, 0.96), xytext=(0.96, 0.91), xycoords='axes fraction',
                fontsize=12, ha='center', fontweight='bold',
                arrowprops=arrow_props, zorder=10)
    
    # -------------------------------------------------------------------------
    # Save outputs
    # -------------------------------------------------------------------------
    
    output_path_svg = maps_dir / 'national_summary_map_cluster25.svg'
    output_path_pdf = maps_dir / 'national_summary_map_cluster25.pdf'
    
    fig.savefig(output_path_svg, dpi=300, format='svg', bbox_inches='tight')
    fig.savefig(output_path_pdf, format='pdf', bbox_inches='tight')
    
    print(f" Saved: {output_path_svg.name} | {output_path_pdf.name}")
    
    if show_plot:
        plt.show()
    else:
        plt.close(fig)
    
    return {
        'svg_path': output_path_svg,
        'png_path': output_path_svg,
        'pdf_path': output_path_pdf,
        'n_cities': n_cities,
        'n_hotspots': len(hotspots_gdf),
        'total_area_km2': total_hotspot_area_km2,
        'total_day_pop': total_day,
        'total_night_pop': total_night,
        'n_gi_star': n_gi_star,
        'gi_star_area_km2': gi_star_area_km2,
        'gi_star_pop': gi_star_pop,
        'success': True,
    }


# 
# Cluster25 helpers — city-based assignment (captures ALL workshop stakeholders)
# 


def _build_city_cluster25_map(survey_df, landscape_gdf):
    """
    Map each workshop city to its dominant Cluster25 class by spatially
    joining the stakeholder spot coordinates that DO have lat/long to the
    landscape polygons, then picking the most-frequent Cluster25 per city.

    Returns
    -------
    city_cluster : dict   {city_name: int(Cluster25)}
    cluster_meta : dict   {int(Cluster25): {'Climate_Class': ..., 'Landcover_Class': ...}}
    """
    from shapely.geometry import Point

    workshop = survey_df[survey_df['survey status'] == 'Yes'].copy()
    spots = workshop[
        workshop['lat_spot'].notna() & workshop['long_spot'].notna()
    ].copy()

    geometry = [Point(xy) for xy in zip(spots['long_spot'], spots['lat_spot'])]
    spots_gdf = gpd.GeoDataFrame(spots, geometry=geometry, crs='EPSG:4326')

    landscape_4326 = landscape_gdf.to_crs('EPSG:4326')
    join_cols = ['Cluster25', 'Climate_Class', 'Landcover_Class', 'geometry']
    joined = gpd.sjoin(
        spots_gdf, landscape_4326[join_cols],
        how='left', predicate='within',
    )
    joined = joined[joined['Cluster25'].notna()].copy()
    joined['Cluster25'] = joined['Cluster25'].astype(int)

    # Dominant cluster per city
    city_cluster = (
        joined.groupby('matched_city_y')['Cluster25']
        .agg(lambda x: x.value_counts().index[0])
        .to_dict()
    )

    # Manual fallback for cities where no stakeholder had spot coordinates.
    # Assignments are based on each city's geographic / climatic zone.
    _FALLBACK_CITY_CLUSTER = {
        'Abraka':     13,   # Delta State  – Wet & Dry / Tree Cover
        'Benin City': 13,   # Edo State    – Wet & Dry / Tree Cover
        'Dutse':      25,   # Jigawa State – Sudan Sav. / Grassland
        'Jalingo':     4,   # Taraba State – Guinea Sav. / Built-up
        'Kaduna':      4,   # Kaduna State – Guinea Sav. / Built-up
        'Owerri':     13,   # Imo State    – Wet & Dry / Tree Cover
        'Umuahia':    13,   # Abia State   – Wet & Dry / Tree Cover
        'Yola':       25,   # Adamawa State – Sudan Sav. / Grassland
    }
    for city, cid in _FALLBACK_CITY_CLUSTER.items():
        if city not in city_cluster:
            city_cluster[city] = cid

    # Metadata per cluster (for labelling)
    cluster_meta = {}
    for cid in joined['Cluster25'].unique():
        row = joined[joined['Cluster25'] == cid].iloc[0]
        cluster_meta[int(cid)] = {
            'Climate_Class': row['Climate_Class'],
            'Landcover_Class': row['Landcover_Class'],
        }

    return city_cluster, cluster_meta


def _assign_cluster25_via_city(survey_df, landscape_gdf):
    """
    Assign a Cluster25 class to EVERY workshop stakeholder via their city.

    This avoids losing stakeholders who have no spot coordinates.

    Returns
    -------
    df : pd.DataFrame   Workshop attendees with a 'Cluster25' column added.
    cluster_meta : dict  {Cluster25_id: {Climate_Class, Landcover_Class}}
    """
    city_cluster, cluster_meta = _build_city_cluster25_map(
        survey_df, landscape_gdf
    )
    workshop = survey_df[survey_df['survey status'] == 'Yes'].copy()

    # Primary: use matched_city_y; fallback: matched_city_x (for PIDs
    # whose city_y is NaN but city_x is populated, e.g. Lagos registrants)
    workshop['_city_key'] = workshop['matched_city_y'].fillna(
        workshop['matched_city_x']
    )
    workshop['Cluster25'] = workshop['_city_key'].map(city_cluster)
    workshop = workshop[workshop['Cluster25'].notna()].copy()
    workshop['Cluster25'] = workshop['Cluster25'].astype(int)
    # Ensure matched_city_y is populated for downstream grouping
    workshop['matched_city_y'] = workshop['matched_city_y'].fillna(
        workshop['matched_city_x']
    )
    workshop.drop(columns=['_city_key'], inplace=True)
    return workshop, cluster_meta


# 
# Chart 1: Reasons for Heating vs. Mitigation by Cluster25
# 

def create_reasons_mitigation_chart(
    survey_df: pd.DataFrame,
    landscape_gdf: gpd.GeoDataFrame,
    output_dir: Path,
    cluster25_colors: Optional[Dict[int, str]] = None,
    figsize: Tuple[float, float] = (18, 9),
    show_plot: bool = True,
) -> Dict[str, Any]:
    """
    Side-by-side horizontal stacked-bar chart of stakeholder-reported reasons
    for urban heating (left) and suggested mitigation solutions (right),
    broken down by Cluster25 landscape type.

    Cluster25 is assigned to every workshop stakeholder via their city's
    dominant landscape class, so that **all** stakeholders with responses
    are included — not only those with spot coordinates.

    Args:
        survey_df:  Raw DataFrame from master_composite.csv.
        landscape_gdf:  Landscape GeoDataFrame with Cluster25 attribute.
        output_dir:  Base output directory; files go into ``output_dir/maps/``.
        cluster25_colors:  Optional dict {cluster_id: hex_color}.
        figsize:  Figure size (width, height) in inches.
        show_plot:  Whether to call ``plt.show()``.

    Returns:
        Dict with saved file paths and summary statistics.
    """
    maps_dir = Path(output_dir) / 'maps'
    maps_dir.mkdir(parents=True, exist_ok=True)

    #  assign Cluster25 via city (all stakeholders) 
    workshop, cluster_meta = _assign_cluster25_via_city(survey_df, landscape_gdf)

    #  city → Cluster25 reverse map (for textbox) 
    _city_cl = (
        workshop.drop_duplicates('matched_city_y')
        .set_index('matched_city_y')['Cluster25']
        .to_dict()
    )
    cl_to_cities: Dict[int, list] = {}
    for _city, _cid in _city_cl.items():
        cl_to_cities.setdefault(int(_cid), []).append(_city)

    #  deduplicate: one response per PID per Cluster25 
    reason_col = '74_reason_hotspots'
    mitig_col = '94_temp_mitigation_solution'

    reason_data = workshop[workshop[reason_col].notna()].drop_duplicates(
        subset=['pid', 'Cluster25']
    )
    mitig_data = workshop[workshop[mitig_col].notna()].drop_duplicates(
        subset=['pid', 'Cluster25']
    )

    #  cross-tabulate 
    reason_ct = pd.crosstab(reason_data['Cluster25'], reason_data[reason_col])
    mitig_ct = pd.crosstab(mitig_data['Cluster25'], mitig_data[mitig_col])

    # Stakeholders per Cluster25
    n_reason = reason_data.groupby('Cluster25')['pid'].nunique()
    n_mitig = mitig_data.groupby('Cluster25')['pid'].nunique()

    #  short column names for display 
    reason_short = {
        'Concentration of automobile emissions': 'Auto. emissions',
        'Dense urban building':                  'Dense buildings',
        'Felling of trees (or devegetation) in the city': 'Devegetation',
        'Population density':                    'Population density',
        'Industrial/refining/manufacturing activities': 'Industrial activity',
        'Others':                                'Others',
        'None of the above':                     'None',
    }
    mitig_short = {
        'Tree planting':             'Tree planting',
        'Urban layout design':       'Urban layout',
        'Adoption of green walls':   'Green walls',
        'Development of waterfronts': 'Waterfronts',
        'Others':                    'Others',
    }

    #  colour palettes 
    reason_colors = {
        'Auto. emissions':    '#e74c3c',
        'Dense buildings':    '#e67e22',
        'Devegetation':       '#27ae60',
        'Population density': '#3498db',
        'Industrial activity': '#9b59b6',
        'Others':             '#95a5a6',
        'None':               '#d5d8dc',
    }
    mitig_colors = {
        'Tree planting':  '#27ae60',
        'Urban layout':   '#2980b9',
        'Green walls':    '#16a085',
        'Waterfronts':    '#5dade2',
        'Others':         '#95a5a6',
    }

    # Rename columns; use CL-{id} labels on y-axis
    reason_ct.columns = [reason_short.get(c, c) for c in reason_ct.columns]
    mitig_ct.columns = [mitig_short.get(c, c) for c in mitig_ct.columns]
    reason_ct.index = [f'CL-{int(i)}' for i in reason_ct.index]
    mitig_ct.index = [f'CL-{int(i)}' for i in mitig_ct.index]

    # Sort by total responses (ascending so busiest on top)
    reason_ct = reason_ct.loc[reason_ct.sum(axis=1).sort_values(ascending=True).index]
    mitig_ct = mitig_ct.reindex(reason_ct.index).fillna(0).astype(int)

    # Column order for consistent stacking
    r_cols = [c for c in reason_short.values() if c in reason_ct.columns]
    m_cols = [c for c in mitig_short.values() if c in mitig_ct.columns]
    reason_ct = reason_ct[r_cols]
    mitig_ct = mitig_ct[[c for c in m_cols if c in mitig_ct.columns]]

    #  totals for subtitle 
    total_reason_stk = reason_data['pid'].nunique()
    total_mitig_stk = mitig_data['pid'].nunique()
    total_stakeholders = workshop.drop_duplicates('pid')['pid'].nunique()
    n_cities_workshop = workshop['matched_city_y'].nunique()

    #  PLOT 
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=figsize, sharey=True,
                                    gridspec_kw={'wspace': 0.05})

    # Left panel — Reasons for heating
    left_acc = np.zeros(len(reason_ct))
    for col in r_cols:
        vals = reason_ct[col].values
        ax1.barh(range(len(reason_ct)), vals, left=left_acc,
                 color=reason_colors.get(col, '#95a5a6'),
                 label=col, height=0.65, edgecolor='white', linewidth=0.5)
        left_acc += vals

    # count annotations (bold, no 'n=' prefix)
    sorted_clusters = list(reason_ct.index)
    for i, lbl in enumerate(sorted_clusters):
        total = reason_ct.loc[lbl].sum()
        cid = int(lbl.split('-')[1])
        n_stk = n_reason.get(cid, 0)
        ax1.text(total + 0.5, i, f'{n_stk}', va='center', fontsize=11,
                 fontweight='bold', color='#333333')

    ax1.set_yticks(range(len(reason_ct)))
    ax1.set_yticklabels(sorted_clusters, fontsize=10, fontweight='bold')
    ax1.set_xlabel('No. of Stakeholders', fontsize=11, fontweight='bold')
    ax1.set_title(f'A)  Reasons for Urban Heating  ({total_reason_stk} stk.)',
                  fontsize=13, fontweight='bold', loc='left')
    ax1.legend(loc='lower right', fontsize=10, framealpha=0.95,
               title='Reason', title_fontsize=11)

    # Right panel — Mitigation solutions
    left_acc = np.zeros(len(mitig_ct))
    for col in mitig_ct.columns:
        vals = mitig_ct[col].values
        ax2.barh(range(len(mitig_ct)), vals, left=left_acc,
                 color=mitig_colors.get(col, '#95a5a6'),
                 label=col, height=0.65, edgecolor='white', linewidth=0.5)
        left_acc += vals

    for i, lbl in enumerate(sorted_clusters):
        total = mitig_ct.loc[lbl].sum()
        cid = int(lbl.split('-')[1])
        n_stk = n_mitig.get(cid, 0)
        ax2.text(total + 0.5, i, f'{n_stk}', va='center', fontsize=11,
                 fontweight='bold', color='#333333')

    ax2.set_xlabel('No. of Stakeholders', fontsize=11, fontweight='bold')
    ax2.set_title(f'B)  Suggested Mitigation Solutions  ({total_mitig_stk} stk.)',
                  fontsize=13, fontweight='bold', loc='left')
    ax2.legend(loc='lower right', fontsize=10, framealpha=0.95,
               title='Solution', title_fontsize=11)

    fig.suptitle(
        'Stakeholder Perceptions: Causes of Urban Heating vs. Mitigation Strategies\n'
        f'by Landscape Character (Cluster25)  —  {total_stakeholders} stakeholders, '
        f'{n_cities_workshop} cities',
        fontsize=14, fontweight='bold', y=1.01,
    )

    fig.tight_layout()

    #  textbox: cities per cluster 
    tb_lines = []
    for _cid in sorted(cl_to_cities.keys()):
        _cities_str = ', '.join(sorted(cl_to_cities[_cid]))
        tb_lines.append(f'CL-{_cid}: {_cities_str}')
    tb_text = '\n'.join(tb_lines)
    fig.text(
        0.5, -0.02, tb_text,
        ha='center', va='top', fontsize=7.5, family='sans-serif',
        bbox=dict(boxstyle='round,pad=0.5', facecolor='#f7f9fc',
                  edgecolor='#cccccc', alpha=0.9),
    )

    #  save 
    svg_path = maps_dir / 'reasons_mitigation_by_cluster25.svg'
    pdf_path = maps_dir / 'reasons_mitigation_by_cluster25.pdf'
    fig.savefig(svg_path, dpi=300, format='svg', bbox_inches='tight')
    fig.savefig(pdf_path, format='pdf', bbox_inches='tight')
    print(f" Saved: {svg_path.name} | {pdf_path.name}")

    if show_plot:
        plt.show()
    else:
        plt.close(fig)

    return {
        'svg_path': svg_path,
        'png_path': svg_path,
        'pdf_path': pdf_path,
        'n_stakeholders': total_stakeholders,
        'n_reason_stakeholders': total_reason_stk,
        'n_mitig_stakeholders': total_mitig_stk,
        'n_cities': n_cities_workshop,
        'n_cluster25_classes': len(reason_ct),
        'reason_responses': int(reason_ct.values.sum()),
        'mitig_responses': int(mitig_ct.values.sum()),
        'success': True,
    }


# 
# Chart 2: Tree Species Heatmap (Cluster25 or City)
# 

def create_tree_species_heatmap(
    survey_df: pd.DataFrame,
    landscape_gdf: gpd.GeoDataFrame,
    output_dir: Path,
    top_n_species: Optional[int] = 15,
    group_by: str = 'cluster25',
    figsize: Optional[Tuple[float, float]] = None,
    show_plot: bool = True,
) -> Dict[str, Any]:
    """
    Heatmap of tree species suggested by stakeholders.

    Two grouping modes controlled by *group_by*:

    * ``'cluster25'`` — species (y-axis) × Landscape Cluster25 (x-axis)
    * ``'city'``      — species (y-axis) × City (x-axis)

    Set *top_n_species* to ``None`` to display **all** species.

    Cell intensity encodes the **number of stakeholders** who mentioned that
    species.  Colour gradient: light green → dark green.

    Args:
        survey_df:  Raw DataFrame from master_composite.csv.
        landscape_gdf:  Landscape GeoDataFrame with Cluster25 attribute.
        output_dir:  Base output directory; files go into ``output_dir/maps/``.
        top_n_species:  Number of top species to show, or ``None`` for all.
        group_by:  ``'cluster25'`` (default) or ``'city'``.
        figsize:  Figure size; auto-calculated if ``None``.
        show_plot:  Whether to call ``plt.show()``.

    Returns:
        Dict with output paths and summary statistics.
    """
    from matplotlib.colors import LinearSegmentedColormap
    import seaborn as sns

    maps_dir = Path(output_dir) / 'maps'
    maps_dir.mkdir(parents=True, exist_ok=True)

    #  assign Cluster25 via city 
    workshop, cluster_meta = _assign_cluster25_via_city(survey_df, landscape_gdf)

    #  filter to tree-species rows 
    tree_col = 'canonical_common_name'
    tree_data = workshop[workshop[tree_col].notna()].copy()
    if tree_data.empty:
        print("⚠ No tree-species data found.")
        return {'success': False}

    # Species ranking (full list)
    species_ranking = tree_data[tree_col].value_counts()
    n_total_species = len(species_ranking)

    if top_n_species is not None:
        selected_species = species_ranking.head(top_n_species).index.tolist()
    else:
        selected_species = species_ranking.index.tolist()

    tree_data = tree_data[tree_data[tree_col].isin(selected_species)]

    #  deduplicate: one entry per PID × species × group 
    # Without this, a stakeholder's tree suggestion is counted once per
    # survey spot, inflating the cross-tab.  We want unique stakeholders.
    if group_by == 'city':
        tree_data = tree_data.drop_duplicates(
            subset=['pid', tree_col, 'matched_city_y']
        )
    else:
        tree_data = tree_data.drop_duplicates(
            subset=['pid', tree_col, 'Cluster25']
        )

    #  cross-tabulate 
    if group_by == 'city':
        ct = pd.crosstab(tree_data[tree_col], tree_data['matched_city_y'])
        ct = ct.reindex(index=selected_species).fillna(0).astype(int)
        ct = ct[sorted(ct.columns)]

        # n= stakeholders per city (unique PIDs with tree data)
        n_per_group = tree_data.groupby('matched_city_y')['pid'].nunique()
        col_labels = [f'{city}\n(n={n_per_group.get(city, 0)})'
                      for city in ct.columns]

        x_label = 'City'
        species_tag = f'top{top_n_species}' if top_n_species else 'all'
        fname_stem = f'tree_species_heatmap_cities_{species_tag}'
        title_group = 'City'
    else:
        ct = pd.crosstab(tree_data[tree_col], tree_data['Cluster25'])
        ct = ct.reindex(index=selected_species).fillna(0).astype(int)
        ct.columns = [f'CL-{int(c)}' for c in sorted(ct.columns)]
        ct = ct[sorted(ct.columns, key=lambda x: int(x.split('-')[1]))]

        # n= stakeholders per Cluster25 (unique PIDs with tree data)
        n_per_group = (
            tree_data.groupby('Cluster25')['pid'].nunique()
            .reindex(sorted(tree_data['Cluster25'].unique()), fill_value=0)
        )
        col_labels = []
        for c in ct.columns:
            cid = int(c.split('-')[1])
            col_labels.append(f'{c}\n(n={n_per_group.get(cid, 0)})')

        x_label = 'Landscape Character (Cluster25)'
        species_tag = f'top{top_n_species}' if top_n_species else 'all'
        fname_stem = f'tree_species_heatmap_cluster25_{species_tag}'
        title_group = 'Landscape Character'

    #  dynamic figsize (tight: cell height  0.35 in) 
    if figsize is None:
        n_rows = len(selected_species)
        n_cols = ct.shape[1]
        if group_by == 'city':
            figsize = (max(16, n_cols * 0.60 + 3), max(6, n_rows * 0.35 + 2.5))
        else:
            figsize = (max(10, n_cols * 1.1 + 3), max(6, n_rows * 0.35 + 2.5))

    #  totals 
    total_stakeholders = tree_data['pid'].nunique()
    n_cities = tree_data['matched_city_y'].nunique()
    n_display = len(selected_species)

    #  light-green → dark-green colour map 
    green_cmap = LinearSegmentedColormap.from_list(
        'light_dark_green',
        ['#f0f9e8', '#bae4bc', '#7bccc4', '#43a2ca', '#0b6623'],
        N=256,
    )

    #  PLOT 
    fig, ax = plt.subplots(figsize=figsize)

    sns.heatmap(
        ct,
        annot=True,
        fmt='d',
        annot_kws={'fontsize': 10, 'fontweight': 'bold'},
        cmap=green_cmap,
        linewidths=0.5,
        linecolor='white',
        cbar_kws={'label': 'No. of Stakeholders', 'shrink': 0.7},
        xticklabels=col_labels,
        yticklabels=ct.index.tolist(),
        ax=ax,
        vmin=0,
        mask=(ct == 0),
        square=False,
    )

    # Zero cells: light grey background
    for yi in range(ct.shape[0]):
        for xi in range(ct.shape[1]):
            if ct.iloc[yi, xi] == 0:
                ax.add_patch(plt.Rectangle(
                    (xi, yi), 1, 1, fill=True,
                    facecolor='#f5f5f5', edgecolor='white', linewidth=0.8,
                ))

    ax.set_xlabel(x_label, fontsize=11, fontweight='bold', labelpad=10)
    ax.set_ylabel('Tree Species', fontsize=11, fontweight='bold', labelpad=10)

    if group_by == 'city':
        ax.tick_params(axis='x', labelsize=7.5, rotation=45)
        plt.setp(ax.get_xticklabels(), ha='right', rotation_mode='anchor')
    else:
        ax.tick_params(axis='x', labelsize=9, rotation=0)
    ax.tick_params(axis='y', labelsize=9, rotation=0)

    # Title
    species_subtitle = (
        f'Top {n_display} of {n_total_species} species shown'
        if top_n_species else f'All {n_total_species} species shown'
    )
    ax.set_title(
        f'Tree Species Suggested by Stakeholders per {title_group}\n'
        f'{total_stakeholders} stakeholders across {n_cities} cities  |  '
        f'{species_subtitle}',
        fontsize=13, fontweight='bold', pad=15,
    )

    fig.tight_layout()

    #  save 
    svg_path = maps_dir / f'{fname_stem}.svg'
    pdf_path = maps_dir / f'{fname_stem}.pdf'
    fig.savefig(svg_path, dpi=300, format='svg', bbox_inches='tight')
    fig.savefig(pdf_path, format='pdf', bbox_inches='tight')
    print(f" Saved: {svg_path.name} | {pdf_path.name}")

    if show_plot:
        plt.show()
    else:
        plt.close(fig)

    return {
        'svg_path': svg_path,
        'png_path': svg_path,
        'pdf_path': pdf_path,
        'n_stakeholders': total_stakeholders,
        'n_cities': n_cities,
        'n_species': n_display,
        'n_groups': ct.shape[1],
        'total_mentions': int(ct.values.sum()),
        'success': True,
    }


# =============================================================================
# NOTEBOOK 03 — DASK-BASED MAP VISUALIZATIONS
# =============================================================================

def _load_geotiff_nb03(file_path):
    """Load a GeoTIFF, mask nodata and extreme values, return (data, bounds, transform, crs)."""
    try:
        import rasterio
        import numpy as np
        with rasterio.open(file_path) as src:
            data = src.read(1).astype(float)
            if src.nodata is not None:
                data[data == src.nodata] = np.nan
            data[(data < -50) | (data > 70)] = np.nan
            return data, src.bounds, src.transform, src.crs
    except Exception as e:
        print(f" Error loading {file_path}: {e}")
        return None, None, None, None


def _calc_qa_stats_nb03(qa_file_path):
    """Return a short QA stats string from a QA GeoTIFF (e.g. 'QA: S-72.4%')."""
    try:
        import rasterio
        import numpy as np
        with rasterio.open(qa_file_path) as src:
            qa_data = src.read(1)
            valid = np.count_nonzero(~np.isnan(qa_data.astype(float)))
            if valid == 0:
                return "No QA data"
            strict_pct = np.count_nonzero(qa_data == 1) / valid * 100
            return f"QA: S-{strict_pct:.1f}%"
    except Exception:
        return "QA data unavailable"


def create_monthly_climatology_map(city_name, city_dir, lst_time,
                                   lst_config, vis_config,
                                   temporal_config, project_config):
    """
    Create a 4×3 A5 grid of monthly LST climatology maps for one city & time.

    This is the ``@delayed`` function from Notebook 03 Cell 16, extracted so
    it can be submitted to a Dask cluster from either the notebook or a script.

    Parameters
    ----------
    city_name : str
    city_dir  : str  (relative path under lst_output_dir, e.g. 'City_Lagos')
    lst_time  : str  ('day' or 'night')
    lst_config   : dict  (config.LST_CONFIG)
    vis_config   : dict  (config.VISUALIZATION_CONFIG[lst_time])
    temporal_config : dict  (config.TEMPORAL_CONFIG)
    project_config  : dict  (config.PROJECT_CONFIG)

    Returns
    -------
    dict with keys: status, city, lst_time, type, output_pdf, output_png
    """
    import glob
    import re
    import os
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as _plt
    from matplotlib.gridspec import GridSpec
    from matplotlib.colors import LinearSegmentedColormap

    A5_SIZE_INCHES = (5.83, 8.27)

    try:
        subdir       = 'Day' if lst_time == 'day' else 'Night'
        geotiff_dir  = os.path.join(project_config['lst_output_dir'], city_dir,
                                    'LST_Temporal_Analysis', subdir, 'geotiff')
        if not os.path.exists(geotiff_dir):
            return {'status': 'error',
                    'message': f'Directory not found: {geotiff_dir}'}

        monthly_files = sorted(glob.glob(
            os.path.join(geotiff_dir,
                         f"{city_name}_LST_{lst_time.title()}_MonthlyClimatology_*.tif")))
        if not monthly_files:
            return {'status': 'no_data',
                    'message': f'No monthly files found for {city_name} {lst_time}'}

        figures_dir = os.path.join(os.path.dirname(geotiff_dir), 'Figures')
        os.makedirs(figures_dir, exist_ok=True)

        MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June',
                       'July', 'August', 'September', 'October', 'November', 'December']
        min_val    = vis_config['min_temp']
        max_val    = vis_config['max_temp']
        hi_temp    = vis_config['highlight_temp']
        lst_cmap   = LinearSegmentedColormap.from_list(
            vis_config['colormap_name'], vis_config['colors'])

        fig = _plt.figure(figsize=A5_SIZE_INCHES, dpi=300)
        _plt.tight_layout()
        gs  = GridSpec(4, 3, figure=fig, hspace=0.15, wspace=0.1)

        im = None
        for fp in monthly_files:
            m = re.search(r'MonthlyClimatology_(\d+)', os.path.basename(fp))
            if not m:
                continue
            mnum = int(m.group(1))
            ax   = fig.add_subplot(gs[(mnum - 1) // 3, (mnum - 1) % 3])
            data, bounds, transform, crs = _load_geotiff_nb03(fp)
            if data is not None:
                im = ax.imshow(data, cmap=lst_cmap, vmin=min_val, vmax=max_val)
                ax.set_title(MONTH_NAMES[mnum - 1], fontsize=8)
                ax.set_xticks([]); ax.set_yticks([])
                qa_fp = fp.replace('_LST_', '_QA_Source_')
                if os.path.exists(qa_fp):
                    ax.text(0.98, 0.02, _calc_qa_stats_nb03(qa_fp),
                            ha='right', va='bottom', transform=ax.transAxes,
                            fontsize=6.5,
                            bbox=dict(facecolor='white', alpha=0.7,
                                      pad=1, edgecolor='none'))
            else:
                ax.text(0.5, 0.5, 'No Data', ha='center', va='center',
                        transform=ax.transAxes)
                ax.set_title(MONTH_NAMES[mnum - 1], fontsize=8)

        fig.canvas.draw()
        if im is not None:
            cbar_ax = fig.add_axes([0.15, 0.05, 0.7, 0.02])
            ticks   = sorted(set(list(range(int(min_val), int(max_val) + 1, 5)) + [hi_temp]))
            cbar    = fig.colorbar(im, cax=cbar_ax, orientation='horizontal', ticks=ticks)
            cbar.ax.set_xticklabels([str(t) for t in ticks], fontsize=6)
            hi_idx  = ticks.index(hi_temp)
            cbar.ax.get_xticklabels()[hi_idx].set_weight('bold')
            cbar.set_label('Temperature (°C)', fontsize=8)

        yr_range = f"{temporal_config['years'][0]}-{temporal_config['years'][-1]}"
        fig.suptitle(f"{city_name} — {lst_time.title()}-time Monthly LST Climatology",
                     fontsize=10, y=0.95)
        fig.text(0.5, 0.01,
                 f"Median {lst_time.title()}-time LST values across years {yr_range}",
                 ha='center', fontsize=6)
        fig.canvas.draw()

        out_pdf = os.path.join(figures_dir,
                               f"{city_name}_{lst_time.title()}_Monthly_LST_Climatology.pdf")
        out_png = os.path.join(figures_dir,
                               f"{city_name}_{lst_time.title()}_Monthly_LST_Climatology.png")
        fig.savefig(out_pdf, bbox_inches='tight', format='pdf')
        fig.savefig(out_png, bbox_inches='tight', dpi=300, format='png')
        _plt.close(fig)

        return {'status': 'success', 'city': city_name, 'lst_time': lst_time,
                'type': 'monthly', 'output_pdf': out_pdf, 'output_png': out_png}

    except Exception as e:
        import traceback
        return {'status': 'error', 'city': city_name, 'lst_time': lst_time,
                'type': 'monthly',
                'message': f"{e}\n{traceback.format_exc()}"}


def create_yearly_lst_map(city_name, city_dir, lst_time,
                          lst_config, vis_config,
                          temporal_config, project_config):
    """
    Create a 5×4 A5 grid of yearly LST median maps for one city & time.

    Parameters
    ----------
    (same as create_monthly_climatology_map)

    Returns
    -------
    dict with keys: status, city, lst_time, type, output_pdf, output_png
    """
    import glob
    import re
    import os
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as _plt
    from matplotlib.gridspec import GridSpec
    from matplotlib.colors import LinearSegmentedColormap

    A5_SIZE_INCHES = (5.83, 8.27)
    N_ROWS, N_COLS = 5, 4

    try:
        subdir      = 'Day' if lst_time == 'day' else 'Night'
        geotiff_dir = os.path.join(project_config['lst_output_dir'], city_dir,
                                   'LST_Temporal_Analysis', subdir, 'geotiff')
        if not os.path.exists(geotiff_dir):
            return {'status': 'error',
                    'message': f'Directory not found: {geotiff_dir}'}

        yearly_files = sorted(glob.glob(
            os.path.join(geotiff_dir,
                         f"{city_name}_LST_{lst_time.title()}_Yearly_*.tif")))
        if not yearly_files:
            return {'status': 'no_data',
                    'message': f'No yearly files found for {city_name} {lst_time}'}

        figures_dir = os.path.join(os.path.dirname(geotiff_dir), 'Figures')
        os.makedirs(figures_dir, exist_ok=True)

        min_val  = vis_config['min_temp']
        max_val  = vis_config['max_temp']
        hi_temp  = vis_config['highlight_temp']
        lst_cmap = LinearSegmentedColormap.from_list(
            vis_config['colormap_name'], vis_config['colors'])

        fig = _plt.figure(figsize=A5_SIZE_INCHES, dpi=300)
        _plt.tight_layout()
        gs  = GridSpec(N_ROWS, N_COLS, figure=fig, hspace=0.15, wspace=0.1)

        im = None
        for i, fp in enumerate(yearly_files[:N_ROWS * N_COLS]):
            m = re.search(r'Yearly_(\d{4})', os.path.basename(fp))
            if not m:
                continue
            year_str = m.group(1)
            ax = fig.add_subplot(gs[i // N_COLS, i % N_COLS])
            data, bounds, transform, crs = _load_geotiff_nb03(fp)
            if data is not None:
                im = ax.imshow(data, cmap=lst_cmap, vmin=min_val, vmax=max_val)
                ax.set_title(year_str, fontsize=8)
                ax.set_xticks([]); ax.set_yticks([])
                qa_fp = fp.replace('_LST_', '_QA_Source_')
                if os.path.exists(qa_fp):
                    ax.text(0.98, 0.02, _calc_qa_stats_nb03(qa_fp),
                            ha='right', va='bottom', transform=ax.transAxes,
                            fontsize=6.5,
                            bbox=dict(facecolor='white', alpha=0.7,
                                      pad=1, edgecolor='none'))
            else:
                ax.text(0.5, 0.5, 'No Data', ha='center', va='center',
                        transform=ax.transAxes)
                ax.set_title(year_str, fontsize=8)

        fig.canvas.draw()
        if im is not None:
            cbar_ax = fig.add_axes([0.15, 0.05, 0.7, 0.02])
            ticks   = sorted(set(list(range(int(min_val), int(max_val) + 1, 5)) + [hi_temp]))
            cbar    = fig.colorbar(im, cax=cbar_ax, orientation='horizontal', ticks=ticks)
            cbar.ax.set_xticklabels([str(t) for t in ticks], fontsize=6)
            hi_idx  = ticks.index(hi_temp)
            cbar.ax.get_xticklabels()[hi_idx].set_weight('bold')
            cbar.set_label('Temperature (°C)', fontsize=8)

        fig.suptitle(f"{city_name} — {lst_time.title()}-time Yearly LST Medians",
                     fontsize=10, y=0.95)
        fig.canvas.draw()

        out_pdf = os.path.join(figures_dir,
                               f"{city_name}_{lst_time.title()}_Yearly_LST.pdf")
        out_png = os.path.join(figures_dir,
                               f"{city_name}_{lst_time.title()}_Yearly_LST.png")
        fig.savefig(out_pdf, bbox_inches='tight', format='pdf')
        fig.savefig(out_png, bbox_inches='tight', dpi=300, format='png')
        _plt.close(fig)

        return {'status': 'success', 'city': city_name, 'lst_time': lst_time,
                'type': 'yearly', 'output_pdf': out_pdf, 'output_png': out_png}

    except Exception as e:
        import traceback
        return {'status': 'error', 'city': city_name, 'lst_time': lst_time,
                'type': 'yearly',
                'message': f"{e}\n{traceback.format_exc()}"}


def create_qa_maps(aoi_data, lst_config, temporal_config, project_config):
    """
    Create monthly QA climatology and yearly QA maps for all cities.

    Equivalent to Notebook 03 Cell 17.  Saves PNGs/PDFs into
    ``Figures/QA_Maps/`` inside each city's LST_Temporal_Analysis directory.

    Parameters
    ----------
    aoi_data : dict  {city_name: {'city_dir': ...}}
    lst_config      : dict  (config.LST_CONFIG)
    temporal_config : dict  (config.TEMPORAL_CONFIG)
    project_config  : dict  (config.PROJECT_CONFIG)
    """
    import glob
    import re
    import os
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as _plt
    import matplotlib.gridspec as gridspec
    from matplotlib.colors import ListedColormap, BoundaryNorm

    A5_SIZE_INCHES = (8.27, 11.69)

    lst_time_options = (['day', 'night'] if lst_config['lst_time'] == 'both'
                        else [lst_config['lst_time']])

    # Build QA colourmap
    qa_colors  = []
    qa_labels  = []
    qa_values  = []
    for tier in sorted(lst_config.get('qa_levels_to_use', []),
                       key=lambda t: lst_config['quality_hierarchy'][t]['priority']):
        tc = lst_config['quality_hierarchy'][tier]
        qa_colors.append(tc['color'])
        qa_labels.append(
            f"{tier.capitalize()} (≤{tc['description'].split('≤')[1].strip()})"
            if '≤' in tc['description'] else tier.capitalize()
        )
        qa_values.append(tc['priority'])

    qa_cmap = ListedColormap(qa_colors) if qa_colors else None
    qa_norm = (BoundaryNorm([qa_values[0] - 0.5] + [v + 0.5 for v in qa_values],
                            len(qa_colors))
               if qa_colors else None)

    def _load_qa(fp):
        try:
            import rasterio
            with rasterio.open(fp) as src:
                data = src.read(1).astype(float)
                if src.nodata is not None:
                    data[data == src.nodata] = np.nan
                return data, src.bounds, src.transform, src.crs
        except Exception as exc:
            print(f" Error loading QA file {fp}: {exc}")
            return None, None, None, None

    def _qa_stats_str(qa_data):
        try:
            valid = np.count_nonzero(~np.isnan(qa_data))
            if valid == 0:
                return "No QA data"
            parts = []
            for tier, tc in lst_config['quality_hierarchy'].items():
                if tier in lst_config.get('qa_levels_to_use', []):
                    pct = np.count_nonzero(qa_data == tc['priority']) / valid * 100
                    parts.append(f"{tier[0].upper()}:{pct:.1f}%")
            return " | ".join(parts)
        except Exception:
            return "QA data unavailable"

    MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June',
                   'July', 'August', 'September', 'October', 'November', 'December']

    for city_name, aoi_info in aoi_data.items():
        print(f"\n🏙️  Processing QA maps for {city_name}")
        city_dir = aoi_info['city_dir']

        for lst_time in lst_time_options:
            subdir      = 'Day' if lst_time == 'day' else 'Night'
            geotiff_dir = os.path.join(project_config['lst_output_dir'], city_dir,
                                       'LST_Temporal_Analysis', subdir, 'geotiff')
            if not os.path.exists(geotiff_dir):
                print(f"   Not found: {geotiff_dir}")
                continue

            qa_maps_dir = os.path.join(os.path.dirname(geotiff_dir),
                                       'Figures', 'QA_Maps')
            os.makedirs(qa_maps_dir, exist_ok=True)

            #  Monthly QA 
            monthly_qa = sorted(glob.glob(
                os.path.join(geotiff_dir,
                             f"{city_name}_QA_Source_{subdir.lower()}_MonthlyClimatology_*.tif")))
            if monthly_qa:
                try:
                    fig = _plt.figure(figsize=A5_SIZE_INCHES, dpi=300)
                    gs  = gridspec.GridSpec(4, 3, figure=fig, hspace=0.15, wspace=0.1)
                    for fp in monthly_qa:
                        m = (re.search(r'MonthlyClimatology_(\d+)', os.path.basename(fp)) or
                             re.search(r'month_(\d+)', os.path.basename(fp)))
                        if not m:
                            continue
                        mnum = int(m.group(1))
                        ax   = fig.add_subplot(gs[(mnum - 1) // 3, (mnum - 1) % 3])
                        qa_data, *_ = _load_qa(fp)
                        if qa_data is not None:
                            ax.imshow(qa_data, cmap=qa_cmap, norm=qa_norm)
                            ax.set_title(MONTH_NAMES[mnum - 1], fontsize=8)
                            ax.set_xticks([]); ax.set_yticks([])
                            ax.text(0.98, 0.02, _qa_stats_str(qa_data),
                                    ha='right', va='bottom',
                                    transform=ax.transAxes, fontsize=7.5,
                                    bbox=dict(facecolor='white', alpha=0.7,
                                              pad=1, edgecolor='none'))
                        else:
                            ax.text(0.5, 0.5, 'No QA Data',
                                    ha='center', va='center', transform=ax.transAxes)
                            ax.set_title(MONTH_NAMES[mnum - 1], fontsize=8)
                    cbar_ax = fig.add_axes([0.15, 0.05, 0.7, 0.02])
                    _plt.colorbar(
                        _plt.cm.ScalarMappable(cmap=qa_cmap, norm=qa_norm),
                        cax=cbar_ax, orientation='horizontal', ticks=qa_values
                    ).ax.set_xticklabels(qa_labels, fontsize=6)
                    fig.suptitle(
                        f"{city_name} — {lst_time.title()}-time Monthly QA Climatology",
                        fontsize=10, y=0.95)
                    yr_range = f"{temporal_config['years'][0]}-{temporal_config['years'][-1]}"
                    _plt.figtext(0.5, 0.01, f"Data period: {yr_range}",
                                 ha='center', fontsize=6)
                    out_pdf = os.path.join(qa_maps_dir,
                        f"{city_name}_{lst_time.title()}_Monthly_QA_Climatology.pdf")
                    out_png = os.path.join(qa_maps_dir,
                        f"{city_name}_{lst_time.title()}_Monthly_QA_Climatology.png")
                    _plt.savefig(out_pdf, bbox_inches='tight')
                    _plt.savefig(out_png, bbox_inches='tight', dpi=300)
                    _plt.close()
                    print(f"   Monthly QA → {os.path.basename(out_png)}")
                except Exception as exc:
                    import traceback
                    print(f"   Monthly QA error for {city_name}: {exc}")
                    print(traceback.format_exc())

            #  Yearly QA 
            yearly_qa = sorted(glob.glob(
                os.path.join(geotiff_dir,
                             f"{city_name}_QA_Source_{subdir.lower()}_Yearly_*.tif")))
            if not yearly_qa:
                continue
            try:
                n = len(yearly_qa)
                if n <= 12: nr, nc = 3, 4
                elif n <= 16: nr, nc = 4, 4
                elif n <= 20: nr, nc = 5, 4
                else: nr, nc = 5, 5

                fig = _plt.figure(figsize=A5_SIZE_INCHES, dpi=300)
                gs  = gridspec.GridSpec(nr, nc, figure=fig, hspace=0.15, wspace=0.1)
                for i, fp in enumerate(yearly_qa):
                    m = (re.search(r'Yearly_(\d{4})', os.path.basename(fp)) or
                         re.search(r'_(\d{4})_', os.path.basename(fp)))
                    if not m or i >= nr * nc:
                        continue
                    ax = fig.add_subplot(gs[i // nc, i % nc])
                    qa_data, *_ = _load_qa(fp)
                    if qa_data is not None:
                        ax.imshow(qa_data, cmap=qa_cmap, norm=qa_norm)
                        ax.set_title(m.group(1), fontsize=8)
                        ax.set_xticks([]); ax.set_yticks([])
                        ax.text(0.98, 0.02, _qa_stats_str(qa_data),
                                ha='right', va='bottom',
                                transform=ax.transAxes, fontsize=7.5,
                                bbox=dict(facecolor='white', alpha=0.7,
                                          pad=1, edgecolor='none'))
                    else:
                        ax.text(0.5, 0.5, 'No QA Data',
                                ha='center', va='center', transform=ax.transAxes)
                        ax.set_title(m.group(1), fontsize=8)
                cbar_ax = fig.add_axes([0.15, 0.05, 0.7, 0.02])
                _plt.colorbar(
                    _plt.cm.ScalarMappable(cmap=qa_cmap, norm=qa_norm),
                    cax=cbar_ax, orientation='horizontal', ticks=qa_values
                ).ax.set_xticklabels(qa_labels, fontsize=6)
                fig.suptitle(
                    f"{city_name} — {lst_time.title()}-time Yearly QA Maps",
                    fontsize=10, y=0.95)
                out_pdf = os.path.join(qa_maps_dir,
                    f"{city_name}_{lst_time.title()}_Yearly_QA.pdf")
                out_png = os.path.join(qa_maps_dir,
                    f"{city_name}_{lst_time.title()}_Yearly_QA.png")
                _plt.savefig(out_pdf, bbox_inches='tight')
                _plt.savefig(out_png, bbox_inches='tight', dpi=300)
                _plt.close()
                print(f"   Yearly QA  → {os.path.basename(out_png)}")
            except Exception as exc:
                import traceback
                print(f"   Yearly QA error for {city_name}: {exc}")
                print(traceback.format_exc())


def create_lst_trend_plots(aoi_data, all_stats_df,
                           temporal_config, project_config, lst_config):
    """
    Create per-city dual-panel LST trend plots (left: yearly trends,
    right: monthly climatology) and a standalone legend.

    Equivalent to Notebook 03 Cell 21 (Block 7).

    Parameters
    ----------
    aoi_data : dict  {city_name: {'city_dir': ...}}
    all_stats_df    : pd.DataFrame  (from All_Cities_LST_Statistics.csv)
    temporal_config : dict  (config.TEMPORAL_CONFIG)
    project_config  : dict  (config.PROJECT_CONFIG)
    lst_config      : dict  (config.LST_CONFIG)
    """
    import os
    import shutil
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as _plt
    import matplotlib.ticker as ticker
    import matplotlib.patches as mpatches
    from matplotlib.lines import Line2D
    from scipy import stats

    FIGURE_SIZE  = (18, 9)
    DPI          = 300
    DAY_COLOR    = '#FF7F0E'
    DAY_FILL     = (1.0, 0.5, 0.055, 0.3)
    NIGHT_COLOR  = '#000000'
    NIGHT_FILL   = (0.5, 0.5, 0.5, 0.3)
    MONTH_ABBRS  = {1:'Jan',2:'Feb',3:'Mar',4:'Apr',5:'May',6:'Jun',
                    7:'Jul',8:'Aug',9:'Sep',10:'Oct',11:'Nov',12:'Dec'}

    lst_time_options = (['day', 'night'] if lst_config['lst_time'] == 'both'
                        else [lst_config['lst_time']])

    def _safe_y(ax, x, y, offset, frac=0.1):
        ylim = ax.get_ylim()
        yr   = ylim[1] - ylim[0]
        ny   = y + offset
        if ny + yr * frac > ylim[1]:
            ny = y - abs(offset) - yr * frac
        elif ny - yr * frac < ylim[0]:
            ny = y + abs(offset) + yr * frac
        return max(ylim[0] + yr * frac * 0.5,
                   min(ny, ylim[1] - yr * frac * 0.5))

    for city_name, aoi_info in aoi_data.items():
        city_df = all_stats_df[all_stats_df['city'] == city_name]
        if city_df.empty:
            print(f"  No data for {city_name}")
            continue

        city_dir        = aoi_info['city_dir']
        city_temporal   = os.path.join(project_config['lst_output_dir'],
                                       f'City_{city_name}', 'LST_Temporal_Analysis')
        os.makedirs(city_temporal, exist_ok=True)
        figures_dir     = os.path.join(city_temporal, 'Figures')
        os.makedirs(figures_dir, exist_ok=True)

        fig, (ax1, ax2) = _plt.subplots(1, 2, figsize=FIGURE_SIZE, sharey=True)
        _plt.subplots_adjust(wspace=0.05)

        yr_range  = (f"({temporal_config['years'][0]}-{temporal_config['years'][-1]})"
                     if temporal_config.get('years') else "")
        fig.suptitle(f"{city_name} Land Surface Temperature {yr_range}",
                     fontweight='bold', fontsize=27, y=0.95)

        all_temps  = []
        day_data   = {}
        night_data = {}

        #  Left panel: yearly trends 
        ax1.set_title("Yearly LST Trends", fontsize=21, pad=20)
        for lst_time in lst_time_options:
            time_df  = city_df[city_df['day_night'] == lst_time]
            yearly   = time_df[time_df['time_period_type'] == 'yearly'].sort_values('time_period')
            if yearly.empty:
                continue
            years    = yearly['time_period'].values.astype(int)
            meds     = yearly['lst_median'].values
            lo, hi   = yearly['lst_min'].values, yearly['lst_max'].values
            all_temps.extend(lo); all_temps.extend(hi)
            col, fill, _d = ((DAY_COLOR, DAY_FILL, day_data)
                             if lst_time == 'day'
                             else (NIGHT_COLOR, NIGHT_FILL, night_data))
            _d.update({'years': years, 'temps': meds,
                       'min_temps': lo, 'max_temps': hi})
            ax1.fill_between(years, lo, hi, color=fill, zorder=1)
            ax1.plot(years, meds, color=col, alpha=0.8, linestyle='-',
                     linewidth=3.75, zorder=2)
            ax1.scatter(years, meds, color=col, s=60, zorder=3)
            try:
                sl, ic, rv, pv, _ = stats.linregress(years, meds)
                r2 = rv ** 2
                ax1.plot(years, ic + sl * years, color=col,
                         linestyle=':', linewidth=3, zorder=1)
                eq   = f"{lst_time.capitalize()}: y = {sl:.4f}x + {ic:.2f}"
                st   = (f"R² = {r2:.3f}, p<{pv:.2f}*" if pv < 0.05
                        else f"R² = {r2:.3f}, p={pv:.3f}")
                wm   = sl * 10
                tc   = sl * (years[-1] - years[0])
                txt  = f"{eq}\n{st}\nWarming: {wm:.2f}°C/decade ({tc:.2f}°C total)"
                _d.update({'trend_text': txt, 'color': col})
            except Exception:
                pass

        _BOX_POS = {'day': (0.02, 0.95, 'top'), 'night': (0.01, 0.03, 'bottom')}
        for lst_time in ['day', 'night']:
            d = day_data if lst_time == 'day' else night_data
            if d and 'trend_text' in d:
                xp, yp, va = _BOX_POS[lst_time]
                ax1.text(xp, yp, d['trend_text'], transform=ax1.transAxes,
                         fontsize=15, va=va,
                         bbox=dict(boxstyle='round,pad=0.5', facecolor='white',
                                   alpha=0.6, edgecolor=d['color'], linewidth=2),
                         color=d['color'], fontweight='bold')
        for lst_time in ['day', 'night']:
            d = day_data if lst_time == 'day' else night_data
            if not d:
                continue
            years, meds, col = d['years'], d['temps'], DAY_COLOR if lst_time == 'day' else NIGHT_COLOR
            yr   = ax1.get_ylim()[1] - ax1.get_ylim()[0] if ax1.get_ylim()[1] != ax1.get_ylim()[0] else 10
            off  = yr * 0.03
            ax1.annotate(f"{years[-1]}: {meds[-1]:.1f}°C",
                         xy=(years[-1], meds[-1]),
                         xytext=(years[-1], _safe_y(ax1, years[-1], meds[-1], off)),
                         ha='center', va='top', fontsize=12, fontweight='bold',
                         color=col,
                         bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                                   edgecolor=col, alpha=0.9),
                         arrowprops=dict(arrowstyle='->', color=col, lw=1))
            mi   = int(np.argmin(meds))
            ax1.annotate(f"{years[mi]}: {meds[mi]:.1f}°C",
                         xy=(years[mi], meds[mi]),
                         xytext=(years[mi], _safe_y(ax1, years[mi], meds[mi], -off)),
                         ha='center', va='top', fontsize=12, fontweight='bold',
                         color=col,
                         bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                                   edgecolor=col, alpha=0.9),
                         arrowprops=dict(arrowstyle='->', color=col, lw=1))

        ax1.set_xlabel("Year", fontsize=18)
        ax1.set_ylabel("LST (°C)", fontsize=18)
        ax1.grid(True, linestyle='--', alpha=0.6)
        ax1.tick_params(axis='both', labelsize=15)
        ax1.xaxis.set_major_locator(ticker.MaxNLocator(integer=True))
        ax1.xaxis.set_major_formatter(ticker.FormatStrFormatter('%d'))

        #  Right panel: monthly climatology 
        ax2.set_title("Monthly LST Climatology", fontsize=21, pad=20)
        day_data   = {}
        night_data = {}
        for lst_time in lst_time_options:
            time_df  = city_df[city_df['day_night'] == lst_time]
            monthly  = time_df[
                (time_df['time_period_type'] == 'monthly') &
                (time_df['is_climatology'] == True)
            ].sort_values('time_period')
            if monthly.empty:
                monthly = time_df[
                    time_df['time_period_type'] == 'monthly'
                ].sort_values('time_period')
            if monthly.empty:
                continue
            months = monthly['time_period'].values.astype(int)
            meds   = monthly['lst_median'].values
            lo, hi = monthly['lst_min'].values, monthly['lst_max'].values
            all_temps.extend(lo); all_temps.extend(hi)
            col, fill, _d = ((DAY_COLOR, DAY_FILL, day_data)
                             if lst_time == 'day'
                             else (NIGHT_COLOR, NIGHT_FILL, night_data))
            _d.update({'months': months, 'temps': meds})
            ax2.fill_between(months, lo, hi, color=fill, zorder=1)
            ax2.plot(months, meds, color=col, alpha=0.8, linestyle='-',
                     linewidth=3.75, zorder=2)
            ax2.scatter(months, meds, color=col, s=60, zorder=3)
            yr2 = max(all_temps) - min(all_temps) if all_temps else 10
            off2 = yr2 * 0.05
            maxi = int(np.argmax(meds)); mini = int(np.argmin(meds))
            for mi, sym in [(maxi, (months[maxi], meds[maxi])),
                             (mini, (months[mini], meds[mini]))]:
                off_dir = off2 if mi == maxi else -off2
                ax2.annotate(
                    f"{MONTH_ABBRS[sym[0]]}: {sym[1]:.1f}°C",
                    xy=sym,
                    xytext=(sym[0], _safe_y(ax2, sym[0], sym[1], off_dir)),
                    ha='center', va='top', fontsize=15, fontweight='bold',
                    color=col,
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                              edgecolor=col, alpha=0.9),
                    arrowprops=dict(arrowstyle='->', color=col, lw=1.5))
            amp = float(meds.max() - meds.min())
            stats_txt = f"Monthly amplitude: {amp:.1f}°C\nStd Dev: {float(np.std(meds)):.1f}°C"
            _d.update({'monthly_stats_text': stats_txt, 'color': col})

        _BOX_POS2 = {'day': (0.98, 0.95, 'top', 'right'),
                     'night': (0.99, 0.03, 'bottom', 'right')}
        for lst_time in ['day', 'night']:
            d = day_data if lst_time == 'day' else night_data
            if d and 'monthly_stats_text' in d:
                xp, yp, va, ha = _BOX_POS2[lst_time]
                ax2.text(xp, yp, d['monthly_stats_text'], transform=ax2.transAxes,
                         fontsize=12, va=va, ha=ha,
                         bbox=dict(boxstyle='round,pad=0.5', facecolor='white',
                                   alpha=0.6, edgecolor=d['color'], linewidth=1),
                         color=d['color'], fontweight='bold')

        ax2.set_xlabel("Month", fontsize=18)
        ax2.set_xticks(range(1, 13))
        ax2.set_xticklabels([MONTH_ABBRS[i] for i in range(1, 13)])
        ax2.grid(True, linestyle='--', alpha=0.6)
        ax2.tick_params(axis='both', labelsize=15)

        if all_temps:
            ym, yM  = min(all_temps), max(all_temps)
            margin  = (yM - ym) * 0.1
            ax1.set_ylim(ym - margin, yM + margin)
            ax2.set_ylim(ym - margin, yM + margin)

        _plt.tight_layout(rect=[0, 0.03, 1, 0.92])
        out_png = os.path.join(figures_dir, f"{city_name}_LST_Trends_Combined2.png")
        out_pdf = os.path.join(figures_dir, f"{city_name}_LST_Trends_Combined2.pdf")
        _plt.savefig(out_png, dpi=DPI, bbox_inches='tight')
        _plt.savefig(out_pdf, bbox_inches='tight')
        _plt.close(fig)
        print(f" Saved trend plots for {city_name}")

    #  Standalone legend 
    legend_dir = os.path.join(project_config['lst_output_dir'], 'Stats')
    os.makedirs(legend_dir, exist_ok=True)
    leg_fig, leg_ax = _plt.subplots(figsize=(12, 3), dpi=300)
    leg_ax.axis('off')
    leg_handles = [
        Line2D([0], [0], color=DAY_COLOR,   linewidth=3.75, label='Day-time Median'),
        Line2D([0], [0], color=DAY_COLOR,   linewidth=3, linestyle=':',
               label='Day Trend Line'),
        mpatches.Patch(color=DAY_FILL,    label='Day Min-Max Range'),
        Line2D([0], [0], color=NIGHT_COLOR, linewidth=3.75, label='Night-time Median'),
        Line2D([0], [0], color=NIGHT_COLOR, linewidth=3, linestyle=':',
               label='Night Trend Line'),
        mpatches.Patch(color=NIGHT_FILL,  label='Night Min-Max Range'),
    ]
    leg = leg_ax.legend(handles=leg_handles, loc='center', ncol=3, fontsize=14,
                        frameon=True, fancybox=True, shadow=True,
                        framealpha=0.9, edgecolor='black')
    leg.get_frame().set_linewidth(1.5)
    leg_fig.tight_layout()
    leg_png = os.path.join(legend_dir, "LST_Trend_Plot_Legend.png")
    leg_pdf = os.path.join(legend_dir, "LST_Trend_Plot_Legend.pdf")
    leg_fig.savefig(leg_png, dpi=300, bbox_inches='tight',
                    facecolor='white', edgecolor='none')
    leg_fig.savefig(leg_pdf, bbox_inches='tight',
                    facecolor='white', edgecolor='none')
    _plt.close(leg_fig)
    print(f" Legend saved: {leg_png}")

    for city_name, aoi_info in aoi_data.items():
        cf = os.path.join(project_config['lst_output_dir'], f'City_{city_name}',
                          'LST_Temporal_Analysis', 'Figures')
        if os.path.exists(cf):
            shutil.copy2(leg_png, os.path.join(cf, f"{city_name}_LST_Trend_Legend.png"))
            shutil.copy2(leg_pdf, os.path.join(cf, f"{city_name}_LST_Trend_Legend.pdf"))


def create_trend_category_chart(summary_csv_path, output_dir):
    """
    Create the Block 9a grouped bar chart: cities vs. LST trend categories.

    Reads ``City_LST_Enhanced_Summary.csv`` and saves
    ``Trend_Category_Summary_Chart.png/.pdf`` into *output_dir*.

    Parameters
    ----------
    summary_csv_path : str  Path to City_LST_Enhanced_Summary.csv
    output_dir       : str  Directory where output files are saved
    """
    import os
    import re
    import numpy as np
    import pandas as pd
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as _plt
    import matplotlib.ticker as mticker

    if not os.path.exists(summary_csv_path):
        print(f" Summary file not found: {summary_csv_path}")
        return

    df = pd.read_csv(summary_csv_path)
    os.makedirs(output_dir, exist_ok=True)

    def _slope(val):
        m = re.search(r'([-+]\d+\.\d*)\s*°C/year', str(val))
        return float(m.group(1)) if m else 0.0

    def _is_sig(val):
        s = str(val).lower()
        if 'not significant' in s:
            return False
        m = re.search(r'p\s*=\s*([\d.]+)', s)
        if m:
            return float(m.group(1)) < 0.05
        return ('increasing trend' in s or 'decreasing trend' in s)

    CATS       = ['Significant Warming', 'Significant Cooling',
                  'Insignificant Warming', 'No Trend / Insig. Cooling']
    CAT_COLORS = ['#d73027', '#4575b4', '#fdae61', '#abd9e9']

    def _cat(row):
        sl, sg = _slope(row.get('Warming Rate', '')), _is_sig(row.get('Trend Significance', ''))
        if sg   and sl > 0: return 'Significant Warming'
        elif sg and sl < 0: return 'Significant Cooling'
        elif sl > 0:        return 'Insignificant Warming'
        else:               return 'No Trend / Insig. Cooling'

    df['_cat'] = df.apply(_cat, axis=1)

    tc = next((c for c in df.columns
               if c.strip().lower() in ('time', 'day_night', 'lst_time')), None)
    if tc is None:
        print(" Could not find time column in CSV"); return

    df['_tnorm'] = df[tc].str.strip().str.capitalize()
    counts = {}
    for t in ['Day', 'Night']:
        sub = df[df['_tnorm'] == t]
        if not sub.empty:
            counts[t] = {c: int((sub['_cat'] == c).sum()) for c in CATS}

    if not counts:
        print(" No data to plot"); return

    x     = np.arange(len(CATS))
    bw    = 0.35
    n_t   = len(counts)
    TS    = {'Day': {'hatch': '', 'alpha': 0.88},
             'Night': {'hatch': '//', 'alpha': 0.75}}

    fig, ax = _plt.subplots(figsize=(13, 6))
    for i, (t, cnt) in enumerate(counts.items()):
        vals   = [cnt.get(c, 0) for c in CATS]
        offset = (i - (n_t - 1) / 2) * bw
        st     = TS.get(t, {'hatch': '', 'alpha': 0.88})
        bars   = ax.bar(x + offset, vals, bw, label=f'{t}-time',
                        color=[CAT_COLORS[j] for j in range(len(CATS))],
                        edgecolor='white', linewidth=0.8,
                        alpha=st['alpha'], hatch=st['hatch'])
        for bar, v in zip(bars, vals):
            if v > 0:
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_height() + 0.15, str(v),
                        ha='center', va='bottom', fontsize=11, fontweight='bold')

    ax.set_xticks(x)
    ax.set_xticklabels(CATS, fontsize=12)
    ax.set_ylabel('Number of Cities', fontsize=13)
    ax.set_title('LST Trend Category Summary — All Cities',
                 fontsize=15, fontweight='bold', pad=14)
    ax.legend(fontsize=12)
    ax.set_ylim(0, max(max(v for d in counts.values() for v in d.values()), 1) + 2)
    ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    ax.grid(axis='y', linestyle='--', alpha=0.5)
    ax.spines[['top', 'right']].set_visible(False)
    _plt.tight_layout()

    chart_png = os.path.join(output_dir, 'Trend_Category_Summary_Chart.png')
    chart_pdf = os.path.join(output_dir, 'Trend_Category_Summary_Chart.pdf')
    fig.savefig(chart_png, dpi=400, bbox_inches='tight')
    fig.savefig(chart_pdf, bbox_inches='tight')
    _plt.close(fig)
    print(f" Trend Category Chart → {chart_png}")


def create_annual_lst_violin_chart(all_stats_csv_path, output_dir, lst_config):
    """
    Create the Block 9b butterfly half-violin chart.

    One figure, one shared LST x-axis (10–46°C).
    Cities on the y-axis (warmest → top).
    Night-time half-violins grow leftward; Day-time grow rightward.

    Parameters
    ----------
    all_stats_csv_path : str   Path to All_Cities_LST_Statistics.csv
    output_dir         : str   Directory where output files are saved
    lst_config         : dict  (config.LST_CONFIG)
    """
    import os
    import numpy as np
    import pandas as pd
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot       as _plt
    import matplotlib.ticker       as _ticker
    import matplotlib.lines        as _mlines
    import matplotlib.patches      as _mpatch
    from scipy.stats import gaussian_kde as _kde

    if not os.path.exists(all_stats_csv_path):
        print(f" Not found: {all_stats_csv_path}"); return

    os.makedirs(output_dir, exist_ok=True)

    all_df = pd.read_csv(all_stats_csv_path)
    yr_df  = all_df[
        (all_df['time_period_type'] == 'yearly') &
        (all_df['is_climatology'] == False)
    ].copy()
    yr_df['year'] = yr_df['time_period'].astype(int)

    available = yr_df['day_night'].unique().tolist()
    lst_times = [t for t in ['day', 'night'] if t in available]
    if lst_config['lst_time'] != 'both':
        lst_times = [t for t in lst_times if t == lst_config['lst_time']]

    if not lst_times:
        print(" No yearly data found"); return

    ref_time     = 'day' if 'day' in lst_times else lst_times[0]
    city_means   = (yr_df[yr_df['day_night'] == ref_time]
                    .groupby('city')['lst_median'].mean()
                    .sort_values(ascending=False))
    sorted_cities = city_means.index.tolist()
    n             = len(sorted_cities)
    city_ypos     = {c: i + 1 for i, c in enumerate(sorted_cities)}

    X_MIN, X_MAX = 10, 46
    VLINE_X      = 27.0
    DAY_COLOR    = '#FF7F0E'
    NIGHT_COLOR  = '#555555'
    HALF_W       = 0.38
    KDE_PTS      = 300

    fig, ax = _plt.subplots(figsize=(13.0, max(5.0, n * 0.42)))

    def _draw_hv(data, y0, side, color):
        if len(data) < 2:
            return
        xlo = max(data.min() - 0.5, X_MIN)
        xhi = min(data.max() + 0.5, X_MAX)
        xg  = np.linspace(xlo, xhi, KDE_PTS)
        try:
            sigma = np.std(data)
            bw    = max(0.3, sigma * 0.35)
            kde   = _kde(data, bw_method=bw / (sigma if sigma > 0 else 1))
            dens  = kde(xg)
        except Exception:
            return
        dn = dens / dens.max() * HALF_W if dens.max() > 0 else dens

        if side == 'right':
            yl, yh = np.full_like(xg, y0), y0 + dn
        else:
            yl, yh = y0 - dn, np.full_like(xg, y0)

        ax.fill_between(xg, yl, yh, color=color, alpha=0.48, linewidth=0)
        ax.plot(xg, yh, color=color, linewidth=0.9, alpha=0.85)
        ax.plot(xg, yl, color=color, linewidth=0.9, alpha=0.85)
        med  = float(np.median(data))
        medn = float(np.interp(med, xg, dn))
        if side == 'right':
            ax.plot([med, med], [y0, y0 + medn],
                    color=color, linewidth=2.5, solid_capstyle='round', zorder=5)
        else:
            ax.plot([med, med], [y0 - medn, y0],
                    color=color, linewidth=2.5, solid_capstyle='round', zorder=5)

    has_hot = has_cool = False
    for city in sorted_cities:
        y0 = city_ypos[city]
        for lst_time in lst_times:
            col  = DAY_COLOR  if lst_time == 'day' else NIGHT_COLOR
            side = 'right'    if lst_time == 'day' else 'left'
            vals = yr_df[(yr_df['day_night'] == lst_time) &
                         (yr_df['city'] == city)]['lst_median'].dropna().values
            _draw_hv(vals, y0, side, col)
            if len(vals) > 0:
                dy = 0.10 if lst_time == 'day' else -0.10
                ax.scatter(vals.max(), y0 + dy, color='#d73027', s=48, zorder=7,
                           linewidths=0,
                           label='Hottest year' if not has_hot else '')
                ax.scatter(vals.min(), y0 + dy, color='#4575b4', s=48, zorder=7,
                           linewidths=0,
                           label='Coolest year' if not has_cool else '')
                has_hot = has_cool = True

    ax.set_xlim(X_MIN, X_MAX)
    ax.set_ylim(n + 0.7, 0.3)
    ax.set_xlabel('Annual Median LST (°C)', fontsize=12)
    ax.xaxis.set_major_locator(_ticker.MultipleLocator(4))
    ax.xaxis.set_minor_locator(_ticker.MultipleLocator(2))
    ax.grid(axis='x', which='major', linestyle='--', alpha=0.45)
    ax.grid(axis='x', which='minor', linestyle=':', alpha=0.25)
    ax.set_yticks(list(range(1, n + 1)))
    ax.set_yticklabels(sorted_cities, fontsize=max(6, 10 - n // 12))
    ax.tick_params(axis='y', length=0)
    ax.spines[['top', 'right']].set_visible(False)

    ax.axvline(VLINE_X, color='#444444', linewidth=1.2,
               linestyle='--', alpha=0.7, zorder=3)
    ax.text(VLINE_X - 0.35, 0.25, '◀ Night-time',
            fontsize=9, color=NIGHT_COLOR, fontweight='bold',
            ha='right', va='center', transform=ax.get_xaxis_transform())
    ax.text(VLINE_X + 0.35, 0.25, 'Day-time ▶',
            fontsize=9, color=DAY_COLOR, fontweight='bold',
            ha='left', va='center', transform=ax.get_xaxis_transform())

    leg_handles = [
        _mpatch.Patch(facecolor=NIGHT_COLOR, alpha=0.55, label='Night-time LST'),
        _mpatch.Patch(facecolor=DAY_COLOR,   alpha=0.55, label='Day-time LST'),
        _mlines.Line2D([], [], marker='o', color='w', markerfacecolor='#d73027',
                       markersize=7, label='Hottest year'),
        _mlines.Line2D([], [], marker='o', color='w', markerfacecolor='#4575b4',
                       markersize=7, label='Coolest year'),
    ]
    ax.legend(handles=leg_handles, fontsize=9, loc='lower right', framealpha=0.85)
    ax.set_title(
        'Annual LST Distribution per City  '
        '—  Night-time (left) vs Day-time (right)\n'
        'Cities sorted warmest → coolest  ·  '
        'Red = hottest year  ·  Blue = coolest year',
        fontsize=11, fontweight='bold', pad=10)

    _plt.tight_layout()
    out_png = os.path.join(output_dir, 'Annual_LST_Violin_Chart.png')
    out_pdf = os.path.join(output_dir, 'Annual_LST_Violin_Chart.pdf')
    fig.savefig(out_png, dpi=400, bbox_inches='tight')
    fig.savefig(out_pdf, bbox_inches='tight')
    _plt.close(fig)
    print(f" Annual LST Violin Chart → {out_png}")


def create_stakeholder_validation_chart(validation_df, output_dir,
                                        chart_type='annual'):
    """
    Create multi-layer donut / sunburst chart comparing stakeholder
    warming perceptions with actual LST trends.

    Equivalent to Notebook 03 Cells 29 (annual) & 30 (monthly).

    Parameters
    ----------
    validation_df : pd.DataFrame
        For annual chart columns: city, n_stakeholders, pct_of_total,
        pct_perceived_warming, overall_agreement, duration_counts,
        day_significance, night_significance.
        For monthly chart cols additionally: lst_day_hottest,
        lst_night_hottest.
    output_dir : str
        Directory where SVG are saved.
    chart_type : str
        'annual' (default) or 'monthly'.
    """
    import os
    import math
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as _plt

    os.makedirs(output_dir, exist_ok=True)

    AGREE_COLOR    = '#0000FF'
    DISAGREE_COLOR = '#FF0000'
    DUR_COLORS     = {
        'Within the last 5 years': '#FFD700',
        'Between 5 - 10 years':    '#4169E1',
        'Between 11 - 15 years':   '#32CD32',
        'Over 15 years':           '#8B008B',
    }
    DUR_CATS = list(DUR_COLORS.keys())

    valid_df    = validation_df[validation_df['n_stakeholders'] > 0].copy()
    n_cities    = len(valid_df)
    total_stake = valid_df['n_stakeholders'].sum()
    max_cols    = min(5, n_cities)
    n_rows      = math.ceil(n_cities / max_cols)
    fig_w       = 8 * max_cols
    fig_h       = 8 * n_rows + 3

    fig  = _plt.figure(figsize=(fig_w, fig_h))
    hr   = [5] * n_rows + [1]
    gs   = fig.add_gridspec(n_rows + 1, max_cols, height_ratios=hr, hspace=0.3)

    for i, (_, row) in enumerate(valid_df.iterrows()):
        ax        = fig.add_subplot(gs[i // max_cols, i % max_cols])
        city      = row['city']
        n_s       = row['n_stakeholders']
        pct_tot   = row['pct_of_total']
        agree     = row['overall_agreement']
        dur       = row.get('duration_counts', {})
        if not isinstance(dur, dict):
            dur = {}

        # Layer 1 (inner): city proportion
        ax.pie([n_s, total_stake - n_s], radius=0.5,
               colors=['#FFA500', '#E0E0E0'],
               wedgeprops=dict(width=0.2, edgecolor='white', linewidth=2),
               startangle=90)

        # Layer 2 (middle): agreement
        if not np.isnan(agree):
            ax.pie([agree, 100 - agree], radius=0.7,
                   colors=[AGREE_COLOR, DISAGREE_COLOR],
                   wedgeprops=dict(width=0.2, edgecolor='white', linewidth=2),
                   startangle=90)

        # Layer 3 (outer): duration
        d3s = [(float(dur.get(dc, 0)), DUR_COLORS[dc])
               for dc in DUR_CATS if dur.get(dc, 0) > 0]
        if d3s:
            ax.pie([s for s, _ in d3s], radius=0.9,
                   colors=[c for _, c in d3s],
                   wedgeprops=dict(width=0.2, edgecolor='white', linewidth=2),
                   startangle=90)

        ax.text(0, 0.15, city, ha='center', va='center',
                fontsize=18, fontweight='bold')
        ax.text(0, -0.05, str(n_s), ha='center', va='center',
                fontsize=32, fontweight='bold')
        ax.text(0, -0.25, f"({pct_tot:.1f}%)", ha='center', va='center',
                fontsize=14)

        if chart_type == 'annual':
            title_txt = (f"Day: {row.get('day_significance','N/A')}, "
                         f"Night: {row.get('night_significance','N/A')}")
        else:
            title_txt = (f"Day: {row.get('lst_day_hottest','N/A')}, "
                         f"Night: {row.get('lst_night_hottest','N/A')}")
        ax.text(0.5, 0.92, title_txt, transform=ax.transAxes,
                fontsize=12, ha='center', va='top',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightyellow',
                          edgecolor='gray', linewidth=1))
        ax.set_aspect('equal')

    # Legend
    leg_ax = fig.add_subplot(gs[n_rows, :])
    leg_ax.axis('off')
    leg_els = [
        _plt.Line2D([0], [0], marker='s', color='w',
                    markerfacecolor=AGREE_COLOR, markersize=20,
                    label='  Agrees with LST trend'),
        _plt.Line2D([0], [0], marker='s', color='w',
                    markerfacecolor=DISAGREE_COLOR, markersize=20,
                    label='  Disagrees with LST trend'),
    ]
    for dc in DUR_CATS:
        leg_els.append(_plt.Line2D(
            [0], [0], marker='s', color='w',
            markerfacecolor=DUR_COLORS[dc], markersize=20,
            label=f'  {dc}'))
    leg_ax.legend(handles=leg_els, loc='center', ncol=3,
                  frameon=False, fontsize=14, handletextpad=0.5, columnspacing=2)

    if chart_type == 'annual':
        title  = (f"Annual Validation: Multi-Layer Donuts "
                  f"(Total: {total_stake} stakeholders)\n"
                  f"Inner: City Proportion | Middle: Annual Trend Agreement "
                  f"| Outer: Duration")
        fstem  = 'Stakeholder_Validation_Sunburst_Chart'
    else:
        title  = (f"Monthly Peak Validation: Multi-Layer Split Donuts "
                  f"(Total: {total_stake} stakeholders)\n"
                  f"Inner: City Proportion | Middle: Monthly Peak Agreement "
                  f"(Day OR Night) | Outer: Duration")
        fstem  = 'Stakeholder_Validation_Monthly_Sunburst_Chart'

    fig.suptitle(title, fontsize=16, fontweight='bold', y=0.98)
    _plt.tight_layout()

    out_png = os.path.join(output_dir, f'{fstem}.png')
    out_pdf = os.path.join(output_dir, f'{fstem}.pdf')
    fig.savefig(out_png, dpi=300, bbox_inches='tight', facecolor='white')
    fig.savefig(out_pdf, bbox_inches='tight', facecolor='white')
    _plt.close(fig)
    print(f" Stakeholder validation chart ({chart_type}) → {out_png}")


# ====================================================================
# OPTION A: PAIRED DOT PLOT
# ====================================================================

def create_paired_dot_plot(cities_data, base_dir=None, study_year=2024, dpi=200):
    """
    Create a paired dot plot showing mean LST ± 1 SD for day and night
    persistent heat events, with a 2-layer donut inset summarising
    danger-zone counts.

    Each city gets two markers (Day = diamond, Night = circle) connected
    by a thin line.  Filled markers denote cities exceeding the overall
    mean (danger zone); hollow markers sit below the mean.  Whiskers
    span ± 1 standard deviation.  A 2-layer donut inset (inner = Day/Night
    totals as dotted outlines; outer = Danger/Normal filled wedges)
    provides a compact summary.

    Parameters
    ----------
    cities_data : dict
        ``{city_name: {'day_file': str, 'night_file': str, ...}}``.
        Each value must contain ``'day_file'`` and ``'night_file'``
        pointing to single-band GeoTIFF rasters of persistent-heat
        mean LST.
    base_dir : str or Path, optional
        Directory for saving SVG.  If *None* the figure is
        returned without saving.
    study_year : int, optional
        Year label used in the title and filename (default 2024).
    dpi : int, optional
        Screen DPI for the figure (default 200); saved at 300 DPI.

    Returns
    -------
    matplotlib.figure.Figure
        The finished figure (caller should ``display()`` / ``plt.close()``).

    Examples
    --------
    >>> fig = create_paired_dot_plot(cities_data, base_dir='outputs',
    ...                              study_year=2024)
    >>> display(fig); plt.close(fig)
    """
    import matplotlib.pyplot as plt
    import matplotlib.patheffects as pe
    import numpy as np
    import rasterio
    from pathlib import Path
    from matplotlib.lines import Line2D

    # -- Colour palette (matches project-wide constants) ----------------
    DAY_FILL     = '#FF8C00'
    DAY_HOLLOW   = '#FFB366'
    NIGHT_FILL   = '#444444'
    NIGHT_HOLLOW = '#999999'
    EXCEED_EDGE  = '#CC0000'

    # -- 1  Gather stats from raster files ------------------------------
    dot_data = []
    for city_name, city_data in cities_data.items():
        row = {'city': city_name}
        for period in ['day', 'night']:
            if period in city_data and f'{period}_file' in city_data:
                lst_file = city_data[f'{period}_file']
                if lst_file and Path(lst_file).exists():
                    try:
                        with rasterio.open(lst_file) as src:
                            d = src.read(1)
                            v = d[~np.isnan(d)]
                            if len(v) > 0:
                                row[f'{period}_mean'] = float(np.mean(v))
                                row[f'{period}_std']  = float(np.std(v))
                                row[f'{period}_min']  = float(np.min(v))
                                row[f'{period}_max']  = float(np.max(v))
                            else:
                                row[f'{period}_mean'] = np.nan
                    except Exception:
                        row[f'{period}_mean'] = np.nan
        dot_data.append(row)

    # -- 2  Sort hottest → coolest (combined day+night mean) -----------
    def _sort_key(r):
        dm = r.get('day_mean', np.nan)
        nm = r.get('night_mean', np.nan)
        dm = dm if not np.isnan(dm) else 0
        nm = nm if not np.isnan(nm) else 0
        return dm + nm

    dot_data.sort(key=_sort_key, reverse=True)

    cities_list  = [r['city'] for r in dot_data]
    day_means    = np.array([r.get('day_mean', np.nan) for r in dot_data])
    day_stds     = np.array([r.get('day_std', np.nan)  for r in dot_data])
    night_means  = np.array([r.get('night_mean', np.nan) for r in dot_data])
    night_stds   = np.array([r.get('night_std', np.nan)  for r in dot_data])

    day_overall   = np.nanmean(day_means)
    night_overall = np.nanmean(night_means)

    n = len(cities_list)
    y = np.arange(n)

    # -- 3  Build figure (A4-portrait: ~190 mm × 260 mm usable) --------
    fig, ax = plt.subplots(figsize=(7.5, 10.2), dpi=dpi)

    for i in range(n):
        dm, ds = day_means[i], day_stds[i]
        nm, ns = night_means[i], night_stds[i]
        has_day   = not np.isnan(dm)
        has_night = not np.isnan(nm)

        # Connecting line
        if has_day and has_night:
            ax.plot([nm, dm], [i, i], color='#BBBBBB', lw=1.2, zorder=1)

        # Night dot + whisker
        if has_night:
            ns_val = ns if not np.isnan(ns) else 0
            exceeds_night = nm > night_overall
            fc = NIGHT_FILL if exceeds_night else 'white'
            ec = EXCEED_EDGE if exceeds_night else NIGHT_HOLLOW
            ax.plot([nm - ns_val, nm + ns_val], [i, i],
                    color=NIGHT_HOLLOW, lw=2.5, solid_capstyle='round', zorder=2)
            ax.scatter(nm, i, s=55, c=fc, edgecolors=ec, linewidths=1.3,
                       zorder=3, marker='o')
            if exceeds_night:
                ax.annotate(f'{nm:.1f}', xy=(nm, i), xytext=(4, -6),
                            textcoords='offset points', fontsize=5.5,
                            fontweight='bold', color='#444444',
                            ha='left', va='top', zorder=5)

        # Day dot + whisker
        if has_day:
            ds_val = ds if not np.isnan(ds) else 0
            exceeds_day = dm > day_overall
            fc = DAY_FILL if exceeds_day else 'white'
            ec = EXCEED_EDGE if exceeds_day else DAY_HOLLOW
            ax.plot([dm - ds_val, dm + ds_val], [i, i],
                    color=DAY_HOLLOW, lw=2.5, solid_capstyle='round', zorder=2)
            ax.scatter(dm, i, s=55, c=fc, edgecolors=ec, linewidths=1.3,
                       zorder=3, marker='D')
            if exceeds_day:
                ax.annotate(f'{dm:.1f}', xy=(dm, i), xytext=(4, -6),
                            textcoords='offset points', fontsize=5.5,
                            fontweight='bold', color='#CC5500',
                            ha='left', va='top', zorder=5)

    # Reference lines
    ax.axvline(day_overall, color='#FF8C00', ls='--', lw=1.2, alpha=0.7,
               zorder=0, label=f'Day Mean: {day_overall:.1f} C')
    ax.axvline(night_overall, color='#666666', ls='--', lw=1.2, alpha=0.7,
               zorder=0, label=f'Night Mean: {night_overall:.1f} C')

    ax.set_yticks(y)
    ax.set_yticklabels(cities_list, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel('Mean LST (\u00b0C)', fontsize=10)
    ax.set_ylabel('Cities (sorted hottest \u2192 coolest)', fontsize=10)
    ax.set_title(
        f'Persistent Heat Event: Day vs Night Mean LST \u00b1 1 SD \u2013 {study_year}\n'
        f'Filled markers = exceeding overall mean  |  Whiskers = \u00b11 SD',
        fontsize=10, fontweight='bold')
    ax.grid(axis='x', alpha=0.25)

    # Legend
    legend_elements = [
        Line2D([0], [0], marker='D', color='w', markerfacecolor=DAY_FILL,
               markeredgecolor=EXCEED_EDGE, markersize=8,
               label='Day > Mean (danger)'),
        Line2D([0], [0], marker='D', color='w', markerfacecolor='white',
               markeredgecolor=DAY_HOLLOW, markersize=8,
               label='Day \u2264 Mean'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor=NIGHT_FILL,
               markeredgecolor=EXCEED_EDGE, markersize=8,
               label='Night > Mean (danger)'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='white',
               markeredgecolor=NIGHT_HOLLOW, markersize=8,
               label='Night \u2264 Mean'),
        Line2D([0], [0], color=DAY_HOLLOW, lw=2.5, label='\u00b11 SD (Day)'),
        Line2D([0], [0], color=NIGHT_HOLLOW, lw=2.5, label='\u00b11 SD (Night)'),
        Line2D([0], [0], color='#BBBBBB', lw=1.2, label='Day\u2013Night gap'),
    ]
    ax.legend(handles=legend_elements, loc='lower right', fontsize=7,
              framealpha=0.9)

    # -- 4  Inset 2-layer donut summary --------------------------------
    _halo = [pe.withStroke(linewidth=2.5, foreground='white')]

    day_valid   = ~np.isnan(day_means)
    night_valid = ~np.isnan(night_means)
    n_day       = int(np.sum(day_valid))
    n_night     = int(np.sum(night_valid))
    day_danger   = int(np.sum(day_means[day_valid] > day_overall))
    day_normal   = n_day - day_danger
    night_danger = int(np.sum(night_means[night_valid] > night_overall))
    night_normal = n_night - night_danger

    ax_donut = fig.add_axes([0.64, 0.23, 0.44, 0.22])
    ax_donut.set_aspect('equal')

    # Outer ring: Danger | Normal
    outer_sizes   = [day_danger, day_normal, night_danger, night_normal]
    outer_colors  = [DAY_FILL, DAY_HOLLOW, NIGHT_FILL, NIGHT_HOLLOW]
    outer_edges   = [EXCEED_EDGE, DAY_HOLLOW, EXCEED_EDGE, NIGHT_HOLLOW]
    outer_texts   = [f'Danger\n{day_danger}', f'Normal\n{day_normal}',
                     f'Danger\n{night_danger}', f'Normal\n{night_normal}']
    outer_tcolors = ['#8B0000', '#7A4800', 'black', '#333333']

    wedges_o, _ = ax_donut.pie(
        outer_sizes, colors=outer_colors, radius=1.0,
        wedgeprops=dict(width=0.30, linewidth=1.5),
        startangle=90, counterclock=False)
    for w, ec in zip(wedges_o, outer_edges):
        w.set_edgecolor(ec)

    for w, lbl, tc in zip(wedges_o, outer_texts, outer_tcolors):
        ang = (w.theta1 + w.theta2) / 2
        x_pos = 0.85 * np.cos(np.radians(ang))
        y_pos = 0.85 * np.sin(np.radians(ang))
        ax_donut.text(x_pos, y_pos, lbl, ha='center', va='center',
                      fontsize=6, fontweight='bold', color=tc,
                      path_effects=_halo)

    # Inner ring: Day | Night (dotted outlines, no fill)
    inner_sizes   = [n_day, n_night]
    inner_colors  = ['none', 'none']
    inner_edges   = [DAY_FILL, NIGHT_FILL]
    inner_texts   = [f'Day\n{n_day}', f'Night\n{n_night}']
    inner_tcolors = [DAY_FILL, NIGHT_FILL]

    wedges_i, _ = ax_donut.pie(
        inner_sizes, colors=inner_colors, radius=0.70,
        wedgeprops=dict(width=0.28, linewidth=2.0, linestyle=(0, (3, 2))),
        startangle=90, counterclock=False)
    for w, ec in zip(wedges_i, inner_edges):
        w.set_edgecolor(ec)

    for w, lbl, tc in zip(wedges_i, inner_texts, inner_tcolors):
        ang = (w.theta1 + w.theta2) / 2
        x_pos = 0.56 * np.cos(np.radians(ang))
        y_pos = 0.56 * np.sin(np.radians(ang))
        ax_donut.text(x_pos, y_pos, lbl, ha='center', va='center',
                      fontsize=7, fontweight='bold', color=tc,
                      path_effects=_halo)

    ax_donut.text(0, 0, f'{n}\nCities', ha='center', va='center',
                  fontsize=9, fontweight='bold', color='#333333')
    ax_donut.text(0, 1.18, 'Inner: Day | Night', ha='center', va='bottom',
                  fontsize=5.5, color='#555555', fontstyle='italic',
                  path_effects=_halo)
    ax_donut.text(0, -1.18, 'Outer: Danger | Normal', ha='center', va='top',
                  fontsize=5.5, color='#555555', fontstyle='italic',
                  path_effects=_halo)

    plt.tight_layout()

    # -- 5  Save --------------------------------------------------------
    if base_dir is not None:
        save_dir = Path(base_dir)
        save_dir.mkdir(parents=True, exist_ok=True)
        for ext in ['png', 'pdf']:
            out = save_dir / f'Paired_Dot_Plot_MeanSD_{study_year}.{ext}'
            fig.savefig(out, dpi=300, bbox_inches='tight')
        print(f"Saved: Paired_Dot_Plot_MeanSD_{study_year}.SVG")

    return fig


# ====================================================================
# OPTION C: DAY-NIGHT SCATTER WITH HEAT DURATION PIE CHARTS
# ====================================================================

def create_daynight_scatter_pie(cities_data, base_dir=None, study_year=2024, dpi=200):
    """
    Create a day-vs-night scatter plot where each city is represented by
    a pie chart whose size encodes total persistent heat duration and
    whose slices show the day/night split.

    Quadrant shading highlights danger-zone cities (hot day + hot night).
    City labels are placed on a transparent overlay axis at high zorder
    so they render above all pie charts, with ``adjustText`` resolving
    overlaps and thin leader lines connecting displaced labels to their
    pie centres.

    Parameters
    ----------
    cities_data : dict
        ``{city_name: {'day_file': str, 'night_file': str,
        'day_duration': int, 'night_duration': int, ...}}``.
    base_dir : str or Path, optional
        Directory for saving SVG.  ``None`` → no save.
    study_year : int, optional
        Year label (default 2024).
    dpi : int, optional
        Screen DPI (default 200); saved at 300 DPI.

    Returns
    -------
    matplotlib.figure.Figure
        The finished figure.

    Examples
    --------
    >>> fig = create_daynight_scatter_pie(cities_data,
    ...                                   base_dir='outputs',
    ...                                   study_year=2024)
    >>> display(fig); plt.close(fig)
    """
    import matplotlib.pyplot as plt
    import matplotlib.patheffects as pe
    import numpy as np
    import rasterio
    from pathlib import Path
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D

    try:
        from adjustText import adjust_text
        HAS_ADJUSTTEXT = True
    except ImportError:
        HAS_ADJUSTTEXT = False

    # -- 1  Gather data -------------------------------------------------
    pie_data = []
    for city_name, city_data in cities_data.items():
        row = {'city': city_name}
        for period in ['day', 'night']:
            if f'{period}_file' in city_data:
                lst_file = city_data[f'{period}_file']
                if lst_file and Path(lst_file).exists():
                    try:
                        with rasterio.open(lst_file) as src:
                            arr = src.read(1)
                            valid = arr[~np.isnan(arr)]
                            if len(valid) > 0:
                                row[f'{period}_mean'] = float(np.mean(valid))
                                row[f'{period}_std']  = float(np.std(valid))
                    except Exception:
                        pass
            dur = city_data.get(f'{period}_duration', 0)
            row[f'{period}_dur'] = int(dur) if dur else 0

        if 'day_mean' in row and 'night_mean' in row:
            pie_data.append(row)

    if not pie_data:
        print("No cities with both day and night data — skipping.")
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.text(0.5, 0.5, 'No data', transform=ax.transAxes,
                ha='center', va='center')
        return fig

    n_cities = len(pie_data)
    names     = [r['city'] for r in pie_data]
    x_day     = np.array([r['day_mean'] for r in pie_data])
    y_night   = np.array([r['night_mean'] for r in pie_data])
    d_dur     = np.array([r.get('day_dur', 0) for r in pie_data])
    n_dur     = np.array([r.get('night_dur', 0) for r in pie_data])
    total_dur = d_dur + n_dur

    day_overall   = np.nanmean(x_day)
    night_overall = np.nanmean(y_night)

    # -- 2  Pie sizing (figure fraction) --------------------------------
    MIN_PIE = 0.018
    MAX_PIE = 0.048
    valid_totals = total_dur[total_dur > 0]
    min_total = int(valid_totals.min()) if len(valid_totals) > 0 else 1
    max_total = int(total_dur.max()) if total_dur.max() > 0 else 2

    DAY_COLOR   = '#FF8C00'
    NIGHT_COLOR = '#444444'

    # -- 3  Figure and main axes ----------------------------------------
    fig, ax = plt.subplots(figsize=(18, 13), dpi=dpi)

    x_range = x_day.max() - x_day.min()
    y_range = y_night.max() - y_night.min()
    x_pad = max(x_range * 0.20, 4.0)
    y_pad = max(y_range * 0.20, 1.5)
    ax.set_xlim(x_day.min() - x_pad, x_day.max() + x_pad)
    ax.set_ylim(y_night.min() - y_pad, y_night.max() + y_pad)

    # Quadrant reference lines
    ax.axvline(day_overall, color='#FF8C00', ls='--', lw=1.2, alpha=0.6, zorder=1)
    ax.axhline(night_overall, color='#666666', ls='--', lw=1.2, alpha=0.6, zorder=1)

    # Shade quadrants
    xlims = ax.get_xlim()
    ylims = ax.get_ylim()
    n_frac = (night_overall - ylims[0]) / (ylims[1] - ylims[0])
    ax.axvspan(day_overall, xlims[1], ymin=n_frac, ymax=1,
               color='#FF0000', alpha=0.04, zorder=0)
    ax.axvspan(xlims[0], day_overall, ymin=0, ymax=n_frac,
               color='#0066CC', alpha=0.04, zorder=0)

    # Quadrant labels
    ax.text(0.98, 0.98, 'HOT DAY + HOT NIGHT\n(Danger Zone)',
            transform=ax.transAxes, ha='right', va='top', fontsize=7,
            color='#CC0000', fontstyle='italic', alpha=0.7)
    ax.text(0.02, 0.02, 'COOL DAY + COOL NIGHT\n(Below Average)',
            transform=ax.transAxes, ha='left', va='bottom', fontsize=7,
            color='#0055AA', fontstyle='italic', alpha=0.7)
    ax.text(0.98, 0.02, 'HOT DAY + COOL NIGHT\n(Night Relief)',
            transform=ax.transAxes, ha='right', va='bottom', fontsize=7,
            color='#886600', fontstyle='italic', alpha=0.5)
    ax.text(0.02, 0.98, 'COOL DAY + HOT NIGHT\n(Possible UHI)',
            transform=ax.transAxes, ha='left', va='top', fontsize=7,
            color='#555555', fontstyle='italic', alpha=0.5)

    ax.set_xlabel(
        f'Day Mean LST (\u00b0C)  |  dashed = overall mean {day_overall:.1f}\u00b0C',
        fontsize=10)
    ax.set_ylabel(
        f'Night Mean LST (\u00b0C)  |  dashed = overall mean {night_overall:.1f}\u00b0C',
        fontsize=10)
    ax.set_title(
        f'Day vs Night Mean LST During Persistent Heat Events \u2013 {study_year}\n'
        f'Pie size = Total Heat Duration  |  Orange = Day Duration  '
        f'|  Grey = Night Duration',
        fontsize=12, fontweight='bold')
    ax.grid(alpha=0.2)

    # -- 4  Lock data→display transforms --------------------------------
    fig.canvas.draw()

    # -- 5  Draw pie charts at each city position -----------------------
    for i in range(n_cities):
        t = total_dur[i]
        if t == 0:
            ax.plot(x_day[i], y_night[i], 'x', color='grey', ms=4,
                    mew=0.8, zorder=5)
            continue

        if max_total > min_total:
            frac = (t - min_total) / (max_total - min_total)
        else:
            frac = 0.5
        pie_sz = MIN_PIE + frac * (MAX_PIE - MIN_PIE)

        disp_xy = ax.transData.transform((x_day[i], y_night[i]))
        fig_xy  = fig.transFigure.inverted().transform(disp_xy)

        pie_ax = fig.add_axes(
            [fig_xy[0] - pie_sz / 2, fig_xy[1] - pie_sz / 2,
             pie_sz, pie_sz],
            zorder=5)

        if d_dur[i] == 0:
            slices, colors = [n_dur[i]], [NIGHT_COLOR]
        elif n_dur[i] == 0:
            slices, colors = [d_dur[i]], [DAY_COLOR]
        else:
            slices, colors = [d_dur[i], n_dur[i]], [DAY_COLOR, NIGHT_COLOR]

        pie_ax.pie(slices, colors=colors, startangle=90,
                   wedgeprops={'edgecolor': 'white', 'linewidth': 0.8})
        pie_ax.set_aspect('equal')
        pie_ax.patch.set_alpha(0)

    # -- 6  Labels on transparent overlay axes (above pies) -------------
    ax_pos = ax.get_position()
    ax_overlay = fig.add_axes(ax_pos, frameon=False, zorder=100)
    ax_overlay.set_xlim(ax.get_xlim())
    ax_overlay.set_ylim(ax.get_ylim())
    ax_overlay.set_xticks([])
    ax_overlay.set_yticks([])
    ax_overlay.patch.set_alpha(0)

    halo = [pe.withStroke(linewidth=3, foreground='white')]

    xlims_d = ax.get_xlim()
    dx_data = xlims_d[1] - xlims_d[0]

    texts = []
    for i, name in enumerate(names):
        texts.append(ax_overlay.text(x_day[i], y_night[i], name,
                                    fontsize=8, ha='center', va='center',
                                    color='black',  path_effects=halo,
                                    bbox=dict(boxstyle='round,pad=0.3',
                                              facecolor='yellow', alpha=0.7,
                                              edgecolor='black', linewidth=0.5),
                                    zorder=101))

    # Resolve overlaps with adjustText
    if HAS_ADJUSTTEXT and len(texts) > 0:
        adjust_text(texts, ax=ax_overlay,
                   arrowprops=dict(arrowstyle='-', lw=0.5, color='black', alpha=0.3),
                   expand_points=(1.5, 1.5))

    # -- 7  Save --------------------------------------------------------
    if base_dir is not None:
        save_dir = Path(base_dir)
        save_dir.mkdir(parents=True, exist_ok=True)
        for ext in ['png', 'pdf']:
            out = save_dir / f'DayNight_Scatter_Pie_{study_year}.{ext}'
            fig.savefig(out, dpi=300, bbox_inches='tight')
        print(f"Saved: DayNight_Scatter_Pie_{study_year}")

    return fig


# ====================================================================
# HOTSPOT ANALYSIS: SUMMARY TABLE GENERATION
# ====================================================================

def build_gistar_p90_summary_table(table1_csv_path):
    """
    Build a side-by-side Gi* and P90 summary table from hotspot characterization data.
    
    This function processes hotspot detection results (from 05_hotspot_analysis.ipynb
    Section 6.3) and creates a comprehensive summary table with per-cluster statistics
    across both Gi* and P90 methods, Day/Night periods, and confidence thresholds
    (50%, 75%, 90%).
    
    Parameters
    ----------
    table1_csv_path : str or Path
        Path to 'table1_hotspot_characterization.csv' from hotspot analysis output
        
    Returns
    -------
    pandas.DataFrame
        Summary table with columns:
        - Dominant Cluster: Cluster identifier (CL-1 to CL-25)
        - City.AOIs: Comma-separated list of cities in cluster
        - (Method, Period, Threshold): Area in km² for each combination
        
        Rows include:
        - Cluster rows (CL-1 to CL-25)
        - Sub-total (Gi*): Sum of all Gi* method cells
        - Sub-total (P90): Sum of all P90 method cells
        - Total: Grand total across all methods and thresholds
        
    Example
    -------
    >>> from src.visualization import build_gistar_p90_summary_table
    >>> from pathlib import Path
    >>> 
    >>> project_root = Path('.')
    >>> table1_path = project_root / 'data' / 'outputs' / '05_hotspot_analysis' / 'figures' / 'table1_hotspot_characterization.csv'
    >>> 
    >>> summary_table = build_gistar_p90_summary_table(table1_path)
    >>> summary_table.to_csv('manuscript_table.csv', index=False)
    """
    from pathlib import Path
    import pandas as pd
    import numpy as np
    
    table1_path = Path(table1_csv_path)
    
    # Load data
    df = pd.read_csv(table1_path)
    
    # Filter for Gi* and P90 methods, Day/Night periods
    data = df[(df["Method"].isin(["GI_STAR", "P90"])) & (df["Period"].isin(["Day", "Night"]))].copy()
    
    # Normalize contour values
    data["Contour"] = pd.to_numeric(data["Contour"], errors="coerce").round(2)
    contour_map = {0.50: "50%", 0.75: "75%", 0.90: "90%"}
    data = data[data["Contour"].isin(contour_map.keys())].copy()
    data["Threshold"] = data["Contour"].map(contour_map)
    
    # Clean cluster IDs
    data["Dominant_Cluster25"] = pd.to_numeric(data["Dominant_Cluster25"], errors="coerce")
    data = data.dropna(subset=["Dominant_Cluster25"]).copy()
    data["Dominant_Cluster25"] = data["Dominant_Cluster25"].astype(int)
    
    selected_clusters = list(range(1, 26))
    
    # Process each method to extract data
    method_data_dict = {}
    city_maps = {}
    
    for method in ["GI_STAR", "P90"]:
        method_df = data[data["Method"] == method].copy()
        
        # Build city list per cluster
        city_maps[method] = (
            method_df.groupby("Dominant_Cluster25")["City"]
              .apply(lambda s: ", ".join(sorted(set(s.dropna()))))
              .to_dict()
        )
        
        # Aggregate by cluster, period, threshold
        agg = method_df.groupby(["Dominant_Cluster25", "Period", "Threshold"], as_index=False)["Total_Area_km²"].sum()
        
        pivot = (
            agg.pivot_table(
                index="Dominant_Cluster25",
                columns=["Period", "Threshold"],
                values="Total_Area_km²",
                aggfunc="sum",
                fill_value=0.0,
            )
            .reindex(selected_clusters, fill_value=0.0)
        )
        
        # Ensure consistent column order
        ordered_cols = [
            ("Day", "50%"), ("Day", "75%"), ("Day", "90%"),
            ("Night", "50%"), ("Night", "75%"), ("Night", "90%"),
        ]
        for col in ordered_cols:
            if col not in pivot.columns:
                pivot[col] = 0.0
        pivot = pivot[ordered_cols]
        method_data_dict[method] = pivot
    
    # Build side-by-side table with one row per cluster
    result_data = []
    
    for cluster_id in selected_clusters:
        row = {"Dominant Cluster": f"CL-{cluster_id}"}
        
        # Combine cities from both methods
        cities_gi = city_maps["GI_STAR"].get(cluster_id, "")
        cities_p90 = city_maps["P90"].get(cluster_id, "")
        all_cities = ", ".join(sorted(set((cities_gi + ", " + cities_p90).split(", "))))
        all_cities = ", ".join([c for c in all_cities.split(", ") if c])
        row["City.AOIs"] = all_cities
        
        # Add method-specific AOI counts
        gi_aois = [c.strip() for c in cities_gi.split(",") if c.strip()]
        p90_aois = [c.strip() for c in cities_p90.split(",") if c.strip()]
        row["Gi*.AOI_Count"] = len(gi_aois)
        row["P90.AOI_Count"] = len(p90_aois)
        
        # Add Gi* columns
        for period in ["Day", "Night"]:
            for threshold in ["50%", "75%", "90%"]:
                gi_val = method_data_dict["GI_STAR"].loc[cluster_id, (period, threshold)]
                row[("Gi*", period, threshold)] = round(gi_val, 2)
        
        # Add P90 columns
        for period in ["Day", "Night"]:
            for threshold in ["50%", "75%", "90%"]:
                p90_val = method_data_dict["P90"].loc[cluster_id, (period, threshold)]
                row[("P90", period, threshold)] = round(p90_val, 2)
        
        result_data.append(row)
    
    # Create DataFrame
    result = pd.DataFrame(result_data)
    
    # Reorder columns: Dominant Cluster, City.AOIs, AOI counts, then Gi* Day/Night, P90 Day/Night
    col_order = ["Dominant Cluster", "City.AOIs", "Gi*.AOI_Count", "P90.AOI_Count",
                 ("Gi*", "Day", "50%"), ("Gi*", "Day", "75%"), ("Gi*", "Day", "90%"),
                 ("Gi*", "Night", "50%"), ("Gi*", "Night", "75%"), ("Gi*", "Night", "90%"),
                 ("P90", "Day", "50%"), ("P90", "Day", "75%"), ("P90", "Day", "90%"),
                 ("P90", "Night", "50%"), ("P90", "Night", "75%"), ("P90", "Night", "90%")]
    result = result[col_order]
    
    # Filter out clusters with 0 for both Gi* and P90
    gi_cols = [col for col in result.columns if col[0] == "Gi*"]
    p90_cols = [col for col in result.columns if col[0] == "P90"]
    
    result_filtered = result[
        (result[gi_cols].sum(axis=1) > 0) |  # Keep if Gi* has any non-zero
        (result[p90_cols].sum(axis=1) > 0)   # Keep if P90 has any non-zero
    ].copy()
    
    # Compute subtotals for each method (based on filtered clusters)
    gi_subtotals = {}
    p90_subtotals = {}
    
    for period in ["Day", "Night"]:
        for threshold in ["50%", "75%", "90%"]:
            gi_subtotals[(period, threshold)] = round(result_filtered[("Gi*", period, threshold)].sum(), 2)
            p90_subtotals[(period, threshold)] = round(result_filtered[("P90", period, threshold)].sum(), 2)
    
    # Build summary rows with proper column filling
    summary_rows = []
    
    # Sub-total (Gi*) row
    gi_subtotal = {"Dominant Cluster": "Sub-total (Gi*)", "City.AOIs": "", "Gi*.AOI_Count": 0, "P90.AOI_Count": 0}
    for period in ["Day", "Night"]:
        for threshold in ["50%", "75%", "90%"]:
            gi_subtotal[("Gi*", period, threshold)] = gi_subtotals[(period, threshold)]
            gi_subtotal[("P90", period, threshold)] = 0.0
    summary_rows.append(gi_subtotal)
    
    # Sub-total (P90) row
    p90_subtotal = {"Dominant Cluster": "Sub-total (P90)", "City.AOIs": "", "Gi*.AOI_Count": 0, "P90.AOI_Count": 0}
    for period in ["Day", "Night"]:
        for threshold in ["50%", "75%", "90%"]:
            p90_subtotal[("Gi*", period, threshold)] = 0.0
            p90_subtotal[("P90", period, threshold)] = p90_subtotals[(period, threshold)]
    summary_rows.append(p90_subtotal)
    
    # Grand Total row (sum of all methods and thresholds)
    grand_total = {"Dominant Cluster": "Total", "City.AOIs": "", "Gi*.AOI_Count": 0, "P90.AOI_Count": 0}
    for period in ["Day", "Night"]:
        for threshold in ["50%", "75%", "90%"]:
            grand_total[("Gi*", period, threshold)] = gi_subtotals[(period, threshold)]
            grand_total[("P90", period, threshold)] = p90_subtotals[(period, threshold)]
    summary_rows.append(grand_total)
    
    # Concatenate all rows
    final_table = pd.concat([
        result_filtered.reset_index(drop=True),
        pd.DataFrame(summary_rows)
    ], ignore_index=True)
    
    # Ensure all columns exist in the final table
    for col in col_order:
        if col not in final_table.columns:
            final_table[col] = 0.0
    final_table = final_table[col_order]
    
    return final_table


def plot_hotspot_multicomponent_chart(final_table, output_path, figsize=(18, 7), dpi=300):
    """
    Create a multi-component bar chart showing hotspot areas by thermal cluster.
    
    Visualizes hotspot detection results across different methods (P90 and Gi*) and
    confidence thresholds (50%, 75%, 90%), with grouped bars for each cluster.
    
    Parameters
    ----------
    final_table : pandas.DataFrame
        Summary table from build_gistar_p90_summary_table(), containing cluster data
        with (Method, Period, Threshold) multi-index columns
    output_path : str or Path
        Base path for output chart. The function saves SVG and PDF.
    figsize : tuple
        Figure size (width, height) in inches. Default: (18, 7)
    dpi : int
        Resolution for saved figure. Default: 300
        
    Returns
    -------
    matplotlib.figure.Figure
        The created figure object
        
    Notes
    -----
    - Uses Day period only (hotspot areas are consistent across periods)
    - Each cluster has 6 bars: P90-50%, P90-75%, P90-90%, Gi*-50%, Gi*-75%, Gi*-90%
    - A thin dotted grey divider separates P90 bars from Gi* bars within each cluster
    - Color coding: P90 uses orange tones, Gi* uses red tones (lighter → darker with increasing confidence)
    - Adds the total number of City AOIs per cluster above each cluster bar group
    - Removes extra horizontal padding before CL-1 and after CL-25
    - Chart is publication-ready with proper formatting and legend
    
    Example
    -------
    >>> from src.visualization import build_gistar_p90_summary_table, plot_hotspot_multicomponent_chart
    >>> from pathlib import Path
    >>> 
    >>> table1_path = Path('data/outputs/05_hotspot_analysis/figures/table1_hotspot_characterization.csv')
    >>> summary_table = build_gistar_p90_summary_table(table1_path)
    >>> fig = plot_hotspot_multicomponent_chart(
    ...     summary_table,
    ...     output_path=table1_path.parent / 'hotspot_chart'
    ... )
    """
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
    from pathlib import Path
    
    # Color mapping for both methods and thresholds
    HOTSPOT_COLORS = {
        'P90': {
            0.9: '#FF8C00',   # Dark orange (90%)
            0.75: '#FFA500',  # Orange (75%)
            0.5: '#FFD700'    # Gold (50%)
        },
        'GI_STAR': {
            0.9: '#8B0000',   # Dark red (90%)
            0.75: '#DC143C',  # Crimson (75%)
            0.5: '#FF6347'    # Tomato (50%)
        }
    }
    
    # Define the 6 components per cluster (P90: 3 thresholds + Gi*: 3 thresholds)
    components = [
        ('P90', 0.9, 'P90-90%'),
        ('P90', 0.75, 'P90-75%'),
        ('P90', 0.5, 'P90-50%'),
        ('Gi*', 0.9, 'Gi*-90%'),
        ('Gi*', 0.75, 'Gi*-75%'),
        ('Gi*', 0.5, 'Gi*-50%'),
    ]
    
    # Filter to data rows only (exclude summary rows)
    data_rows = final_table[final_table['Dominant Cluster'].str.startswith('CL-')].copy()
    clusters = data_rows['Dominant Cluster'].values
    n_clusters = len(clusters)
    bar_width = 0.12  # Width of each bar
    method_gap = bar_width * 0.35  # Extra spacing between P90 and Gi* triplets
    x_positions = np.arange(n_clusters)
    
    # Create figure
    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    
    # Plot bars for each component
    max_vals = np.zeros(n_clusters)
    for i, (method_col, contour, label) in enumerate(components):
        offset = (i - 2.5) * bar_width
        if i < 3:
            offset -= method_gap / 2
        else:
            offset += method_gap / 2
        
        # Map contour value to threshold string for column lookup
        threshold_map = {0.9: "90%", 0.75: "75%", 0.5: "50%"}
        threshold_str = threshold_map[contour]
        
        # Use Day period for all components
        period = "Day"
        
        # Get values for this component
        col = (method_col, period, threshold_str)
        values = data_rows[col].values
        
        # Get color (map method_col back to visualization method name)
        viz_method = 'GI_STAR' if method_col == 'Gi*' else method_col
        color = HOTSPOT_COLORS[viz_method][contour]
        
        # Plot bars
        ax.bar(x_positions + offset, values, bar_width, label=label, color=color, 
               edgecolor='black', linewidth=0.5)
        max_vals = np.maximum(max_vals, values)

    # Add a subtle divider between P90 (left triplet) and Gi* (right triplet).
    # The split is exactly at the cluster center x-position (between bars 3 and 4).
    if n_clusters > 0:
        for x in x_positions:
            ax.axvline(
                x=x,
                ymin=0,
                ymax=1,
                color='grey',
                linestyle=':',
                linewidth=1.0,
                alpha=0.85,
                zorder=2,
            )

    # Add method-specific AOI counts at top of each cluster group
    # Extract method-specific counts from data_rows
    p90_counts = data_rows['P90.AOI_Count'].values if 'P90.AOI_Count' in data_rows.columns else np.zeros(n_clusters)
    gi_counts = data_rows['Gi*.AOI_Count'].values if 'Gi*.AOI_Count' in data_rows.columns else np.zeros(n_clusters)
    
    # Colors: orange for P90 (75% shade), crimson for Gi* (75% shade)
    p90_color = HOTSPOT_COLORS['P90'][0.75]  # #FFA500
    gi_color = HOTSPOT_COLORS['GI_STAR'][0.75]  # #DC143C
    
    y_offset = max(max_vals) * 0.03 if len(max_vals) and max(max_vals) > 0 else 0.3
    
    for i in range(n_clusters):
        # P90 count on the left
        if p90_counts[i] > 0:
            ax.text(
                x_positions[i] - 0.15,
                max_vals[i] + y_offset,
                f'{int(p90_counts[i])}',
                ha='center',
                va='bottom',
                fontsize=9,
                fontweight='bold',
                color=p90_color
            )
        
        # Gi* count on the right
        if gi_counts[i] > 0:
            ax.text(
                x_positions[i] + 0.15,
                max_vals[i] + y_offset,
                f'{int(gi_counts[i])}',
                ha='center',
                va='bottom',
                fontsize=9,
                fontweight='bold',
                color=gi_color
            )
    
    # Customize chart
    ax.set_xlabel('Physiographic Clusters', fontsize=12, fontweight='bold')
    ax.set_ylabel('Area (km²)', fontsize=12, fontweight='bold')
    ax.set_title('Hotspot Areas by Physiographic Cluster and Method Components',
                 fontsize=14, fontweight='bold')
    ax.set_xticks(x_positions)
    ax.set_xticklabels(clusters, rotation=45, ha='right')
    ax.legend(loc='upper right', ncol=3, fontsize=10)
    ax.grid(axis='y', alpha=0.3, linestyle='--')
    ax.set_ylim(bottom=0)

    # Remove horizontal padding so bars begin at CL-1 and end at CL-25
    left_edge = x_positions[0] - 3 * bar_width - (method_gap / 2)
    right_edge = x_positions[-1] + 3 * bar_width + (method_gap / 2)
    ax.set_xlim(left_edge, right_edge)
    ax.margins(x=0)
    
    plt.tight_layout()
    
    # Save figure as SVG and PDF only.
    # Some notebook sessions force a PDF canvas backend, which can raise:
    # "The 'pdf' backend does not support svg output".
    # Explicitly switch canvas per export type to avoid backend mismatch.
    output_path = Path(output_path)
    svg_path = output_path.with_suffix('.svg')
    pdf_path = output_path.with_suffix('.pdf')

    from matplotlib.backends.backend_svg import FigureCanvasSVG
    from matplotlib.backends.backend_pdf import FigureCanvasPdf

    FigureCanvasSVG(fig)
    fig.savefig(svg_path, bbox_inches='tight')

    FigureCanvasPdf(fig)
    fig.savefig(pdf_path, bbox_inches='tight')

    print(f"Chart saved: {svg_path}")
    print(f"Chart saved: {pdf_path}")
    print(f"Chart shows {n_clusters} physiographic clusters with 6 component bars each "
          f"(P90-50%, P90-75%, P90-90%, Gi*-50%, Gi*-75%, Gi*-90%)")
    
    return fig


# ====================================================================
# PUBLISH-READY: HEAT WAVE RESILIENCE & VULNERABILITY SUMMARY MAP
# ====================================================================

def create_resilience_vulnerability_map(
    cities_summary_data,
    city_name,
    output_dir=None,
    figsize=(16, 12),
    dpi=300
):
    """
    Create a publication-ready summary map showing Heat Wave resilience and
    vulnerability indicators for a single city or all cities simultaneously.
    
    This visualization synthesizes all key indicators from the temperature
    analysis to provide a comprehensive view of heat exposure, susceptibility,
    and adaptive capacity across urban/peri-urban areas.
    
    Parameters
    ----------
    cities_summary_data : dict
        Summary statistics from all temporal analysis phases:
        {'city_name': {
            'aoi_area_km2': float,
            'core_area_km2': float,
            'population_2024': int,
            'mean_day_lst': float,
            'mean_night_lst': float,
            'day_hotspot_pixels': int,
            'night_hotspot_pixels': int,
            'persistent_heat_days': int,
            'persistent_heat_nights': int,
            'trend_slope_celsius_per_decade': float,
            'stakeholder_awareness': float (0-100),
            'perceived_warming_agreement': float (0-100),
        }}
    city_name : str
        City for which to create the map (or 'All' for multi-city comparison)
    output_dir : str or Path, optional
        Directory to save figure (both PNG and PDF)
    figsize : tuple
        Figure size (width, height) in inches
    dpi : int
        Resolution for saved figure (default 300 for publication)
        
    Returns
    -------
    matplotlib.figure.Figure
        The completed figure
        
    Notes
    -----
    - Indicators are standardized to 0-100 scale for direct comparison
    - Color coding: Green = low risk, Yellow = moderate, Red = high risk
    - Includes trend analysis and stakeholder perception alignment
    - Suitable for peer-reviewed publications and policy briefs
    
    Example
    -------
    >>> summary = {
    ...     'Lagos': {
    ...         'aoi_area_km2': 5400,
    ...         'population_2024': 15000,
    ...         'mean_day_lst': 38.5,
    ...         'persistent_heat_days': 120,
    ...         ...
    ...     }
    ... }
    >>> fig = create_resilience_vulnerability_map(summary, 'Lagos',
    ...                                            output_dir='outputs')
    """
    from pathlib import Path
    import numpy as np
    import pandas as pd
    from matplotlib.patches import Rectangle, FancyBboxPatch
    from matplotlib.gridspec import GridSpec
    
    # Prepare data
    if city_name == 'All' or city_name not in cities_summary_data:
        cities_to_plot = list(cities_summary_data.keys())
    else:
        cities_to_plot = [city_name]
    
    # Create figure
    if len(cities_to_plot) == 1:
        fig = plt.figure(figsize=figsize)
        gs = GridSpec(2, 2, figure=fig, hspace=0.3, wspace=0.3,
                      left=0.08, right=0.95, top=0.93, bottom=0.08)
    else:
        # Multi-city layout
        n_rows = int(np.ceil(len(cities_to_plot) / 2))
        fig = plt.figure(figsize=(figsize[0], figsize[1] * n_rows / 2))
        gs = GridSpec(n_rows * 2, 2, figure=fig, hspace=0.4, wspace=0.3,
                      left=0.08, right=0.95, top=0.93, bottom=0.08)
    
    # Color mapping function
    def get_risk_color(value, reverse=False):
        """Get color based on risk level (0-100 scale)"""
        value = np.clip(value, 0, 100)
        if reverse:
            value = 100 - value
        
        if value < 33:
            return '#2ecc71'  # Green (low risk)
        elif value < 66:
            return '#f39c12'  # Yellow (moderate)
        else:
            return '#e74c3c'  # Red (high risk)
    
    # Create subplots for each city
    for idx, plot_city in enumerate(cities_to_plot):
        if plot_city not in cities_summary_data:
            continue
        
        data = cities_summary_data[plot_city]
        
        # Select subplot
        if len(cities_to_plot) == 1:
            ax = fig.add_subplot(gs[0, :])  # Top half for single city
        else:
            row = (idx // 2) * 2
            col = idx % 2
            ax = fig.add_subplot(gs[row:row+2, col])
        
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 10)
        ax.axis('off')
        
        # Title
        ax.text(5, 9.5, f'{plot_city} - Heat Resilience Profile',
                fontsize=14, fontweight='bold', ha='center', va='top')
        
        # Prepare indicators
        indicators = {
            'Heat Exposure': {
                'value': np.clip(data.get('mean_day_lst', 25) / 50 * 100, 0, 100),
                'label': f"{data.get('mean_day_lst', 0):.1f}°C",
                'y': 8.5
            },
            'Hotspot Coverage': {
                'value': data.get('hotspot_coverage_percent', 0),
                'label': f"{data.get('hotspot_coverage_percent', 0):.1f}%",
                'y': 7.5
            },
            'Trend (2000-2024)': {
                'value': np.clip(data.get('trend_slope_celsius_per_decade', 0) / 0.15 * 100, 0, 100),
                'label': f"{data.get('trend_slope_celsius_per_decade', 0):.2f}°C/decade",
                'y': 6.5
            },
            'Persistent Heat Days': {
                'value': np.clip(data.get('persistent_heat_days', 0) / 365 * 100, 0, 100),
                'label': f"{data.get('persistent_heat_days', 0)} days",
                'y': 5.5
            },
            'Population Exposure': {
                'value': np.clip(np.log10(data.get('population_2024', 1)) / 8 * 100, 0, 100),
                'label': f"{data.get('population_2024', 0):,.0f}",
                'y': 4.5
            },
            'Stakeholder Awareness': {
                'value': data.get('stakeholder_awareness', 0),
                'label': f"{data.get('stakeholder_awareness', 0):.0f}%",
                'y': 3.5,
                'reverse': True
            },
        }
        
        # Draw indicator bars
        for indicator_name, props in indicators.items():
            value = props['value']
            y_pos = props['y']
            
            # Background bar
            rect_bg = FancyBboxPatch((0.5, y_pos - 0.3), 6, 0.6,
                                     boxstyle='round,pad=0.05',
                                     facecolor='lightgray', edgecolor='black',
                                     linewidth=0.5)
            ax.add_patch(rect_bg)
            
            # Value bar
            color = get_risk_color(value, reverse=props.get('reverse', False))
            rect_val = FancyBboxPatch((0.5, y_pos - 0.3), 6 * value / 100, 0.6,
                                      boxstyle='round,pad=0.05',
                                      facecolor=color, edgecolor='black',
                                      linewidth=0.5, alpha=0.85)
            ax.add_patch(rect_val)
            
            # Label
            ax.text(0.2, y_pos, indicator_name, fontsize=9,
                   fontweight='bold', va='center', ha='right')
            
            # Value
            ax.text(6.8, y_pos, props['label'], fontsize=8,
                   va='center', ha='left')
        
        # Risk classification box
        risk_score = np.mean([props['value'] for props in indicators.values()])
        if risk_score < 33:
            risk_class = 'LOW RISK'
            risk_color = '#2ecc71'
        elif risk_score < 66:
            risk_class = 'MODERATE RISK'
            risk_color = '#f39c12'
        else:
            risk_class = 'HIGH RISK'
            risk_color = '#e74c3c'
        
        risk_box = FancyBboxPatch((0.5, 1.5), 6, 0.8,
                                   boxstyle='round,pad=0.1',
                                   facecolor=risk_color, edgecolor='black',
                                   linewidth=1.5, alpha=0.9)
        ax.add_patch(risk_box)
        ax.text(3.5, 1.9, risk_class,
               fontsize=11, fontweight='bold',
               ha='center', va='center', color='white')
    
    # Figure title
    if city_name == 'All':
        fig.suptitle('Heat Resilience & Vulnerability Assessment - All Cities',
                    fontsize=16, fontweight='bold', y=0.98)
    else:
        fig.suptitle(f'Heat Resilience & Vulnerability Assessment - {city_name}',
                    fontsize=16, fontweight='bold', y=0.98)
    
    # Save figure
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        png_path = output_dir / f'Resilience_Vulnerability_Map_{city_name}.png'
        pdf_path = output_dir / f'Resilience_Vulnerability_Map_{city_name}.pdf'
        
        fig.savefig(png_path, dpi=dpi, bbox_inches='tight', facecolor='white')
        fig.savefig(pdf_path, format='pdf', bbox_inches='tight', facecolor='white')
        
        print(f" Saved: {png_path.name}")
        print(f" Saved: {pdf_path.name}")
    
    return fig
    pie_radii = []
    for i in range(n_cities):
        td = total_dur[i]
        if td == 0 or max_total <= min_total:
            fr = 0.5
        else:
            fr = (td - min_total) / (max_total - min_total)
        ps = MIN_PIE + fr * (MAX_PIE - MIN_PIE)
        pie_radii.append(ps / 2 * dx_data * 1.6)

    texts = []
    for i in range(n_cities):
        lx = x_day[i] + pie_radii[i] + dx_data * 0.004
        ly = y_night[i]
        txt = ax_overlay.text(
            lx, ly, names[i], fontsize=8, fontweight='bold',
            color='#222222', ha='left', va='center',
            path_effects=halo)
        texts.append(txt)

    if HAS_ADJUSTTEXT:
        ax_overlay.scatter(x_day, y_night, s=1500, alpha=0)
        adjust_text(
            texts, x=x_day.tolist(), y=y_night.tolist(),
            ax=ax_overlay,
            expand_points=(4.0, 4.0), expand_text=(2.0, 2.0),
            force_points=(5.0, 5.0), force_text=(2.0, 2.0),
            ensure_inside_axes=True, max_move=None)

    # Manual leader lines from pie centre to displaced labels
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for i in range(n_cities):
        bbox = texts[i].get_window_extent(renderer)
        inv = ax_overlay.transData.inverted()
        cx, cy = x_day[i], y_night[i]
        lx0, lcy = inv.transform((bbox.x0, (bbox.y0 + bbox.y1) / 2))
        lx1, _   = inv.transform((bbox.x1, bbox.y0))
        if abs(lx0 - cx) < abs(lx1 - cx):
            conn_x, conn_y = lx0, lcy
        else:
            conn_x, conn_y = lx1, lcy
        dist = np.sqrt((conn_x - cx)**2 + (conn_y - cy)**2)
        if dist > pie_radii[i] * 1.5:
            ax_overlay.plot([cx, conn_x], [cy, conn_y],
                            '-', color='#555555', lw=0.7, alpha=0.6)

    # -- 7  Legend at bottom centre ------------------------------------
    legend_elements = [
        Patch(facecolor=DAY_COLOR, edgecolor='white', lw=0.8,
              label='Day Persistent Heat Duration'),
        Patch(facecolor=NIGHT_COLOR, edgecolor='white', lw=0.8,
              label='Night Persistent Heat Duration'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='#AAAAAA',
               alpha=0.5, markersize=6,
               label=f'Smallest pie = {min_total} days total'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='#AAAAAA',
               alpha=0.5, markersize=14,
               label=f'Largest pie = {max_total} days total'),
    ]
    ax.legend(handles=legend_elements, loc='lower center', ncol=2,
              fontsize=8, framealpha=0.9,
              title='Pie Chart Legend', title_fontsize=8)

    # -- 8  Save --------------------------------------------------------
    if base_dir is not None:
        save_dir = Path(base_dir)
        save_dir.mkdir(parents=True, exist_ok=True)
        for ext in ['png', 'pdf']:
            out = save_dir / f'DayNight_Scatter_PieDuration_{study_year}.{ext}'
            fig.savefig(out, dpi=300, bbox_inches='tight')
        print(f"Saved: DayNight_Scatter_PieDuration_{study_year}.SVG")

    return fig


# ======================================================================
# NB05 — Quick-look KDE polygon diagnostic grid
# ======================================================================

def plot_kde_quicklook(
    hotspot_polygons_gdf,
    persistent_heat_rasters: dict,
    cities: list,
    all_cities: list | None = None,
    output_dir=None,
    method: str = 'P90',
    period: str = 'Day',
    dpi: int = 200,
):
    """Create a quick-look grid of KDE contour polygons over LST rasters.

    Parameters
    ----------
    hotspot_polygons_gdf : GeoDataFrame
        Full hotspot polygon GeoDataFrame with 'method', 'period', 'city',
        'contour_level' columns.
    persistent_heat_rasters : dict
        ``{city: {'day': {'data': np.ndarray, 'transform': Affine}, ...}}``
    cities : list[str]
        Cities to display **inline** (typically TEST_CITIES subset).
    all_cities : list[str] | None
        All cities for the saved file version.  If *None*, defaults to *cities*.
    output_dir : Path | str | None
        If provided, saves the full-city grid (SVG) here.
    method, period : str
        Filter values for the polygon GeoDataFrame.
    dpi : int
        Figure resolution.

    Returns
    -------
    matplotlib.figure.Figure or None
    """
    import math
    from pathlib import Path
    from rasterio.transform import array_bounds

    if all_cities is None:
        all_cities = cities

    sample_gdf = hotspot_polygons_gdf[
        (hotspot_polygons_gdf['method'] == method) &
        (hotspot_polygons_gdf['period'] == period)
    ].copy()

    if len(sample_gdf) == 0:
        print(f"⚠  No {method} {period} polygons to visualize")
        return None

    # --- Helper: draw one grid ------------------------------------------
    def _draw_grid(city_list, tag=''):
        n = len(city_list)
        if n == 0:
            return None
        max_cols = min(5, n)
        n_rows = math.ceil(n / max_cols)
        fig, axes = plt.subplots(n_rows, max_cols,
                                 figsize=(4 * max_cols, 4 * n_rows))
        if n == 1:
            axes = np.array([axes])
        axes = np.array(axes).flatten()

        for i in range(n, len(axes)):
            axes[i].set_visible(False)

        colors = {0.50: 'yellow', 0.75: 'orange', 0.90: 'red'}

        for idx, city in enumerate(city_list):
            ax = axes[idx]
            city_polys = sample_gdf[sample_gdf['city'] == city]

            if len(city_polys) == 0:
                ax.text(0.5, 0.5, f'{city}\nNo {method} {period}\npolygons',
                        ha='center', va='center', transform=ax.transAxes,
                        fontsize=9)
                ax.set_title(city, fontsize=10)
                ax.axis('off')
                continue

            # LST background
            if city in persistent_heat_rasters:
                per = period.lower()
                rdata = persistent_heat_rasters[city][per]['data']
                rtx = persistent_heat_rasters[city][per]['transform']
                display = rdata.copy().astype(float)
                display[rdata <= 0] = np.nan
                bounds = array_bounds(rdata.shape[0], rdata.shape[1], rtx)
                extent = [bounds[0], bounds[2], bounds[1], bounds[3]]
                ax.imshow(display, cmap='RdYlBu_r', alpha=0.5,
                          extent=extent, aspect='auto', origin='upper')

            for level in [0.50, 0.75, 0.90]:
                lp = city_polys[city_polys['contour_level'] == level]
                if len(lp) > 0:
                    lp.plot(ax=ax, facecolor='none', edgecolor=colors[level],
                            linewidth=2, label=f'{level:.0%}')

            ax.set_title(f'{city} – {method} {period}\n{len(city_polys)} polys',
                         fontsize=10)
            ax.set_xlabel('Longitude', fontsize=8)
            ax.set_ylabel('Latitude', fontsize=8)
            if idx == 0:
                ax.legend(loc='upper left', fontsize=8, title='Contour')

        fig.suptitle(f'KDE Quick-Look: {method} {period} ({len(city_list)} cities){tag}',
                     fontsize=13, y=1.01)
        fig.tight_layout()
        return fig

    # --- Save full-city grid to disk ------------------------------------
    if output_dir is not None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        fig_all = _draw_grid(all_cities, tag=' [all]')
        if fig_all is not None:
            for ext in ('png', 'pdf'):
                fig_all.savefig(out / f'kde_quicklook_{method}_{period}.{ext}',
                                dpi=dpi, bbox_inches='tight')
            plt.close(fig_all)
            print(f"💾 Saved kde_quicklook_{method}_{period}.SVG → {out.name}/")

    # --- Return inline figure (display subset only) ---------------------
    fig_inline = _draw_grid(cities)
    return fig_inline


# =====================================================================
# Notebook-03 helpers  – LST temporal analysis visualisation utilities
# =====================================================================

def load_geotiff(file_path):
    """Load a single-band GeoTIFF, masking NoData and extreme values.

    Returns (data, bounds, transform, crs) or (None, …) on error.
    """
    import rasterio as _rio
    import numpy as _np

    try:
        with _rio.open(file_path) as src:
            data = src.read(1).astype(float)
            if src.nodata is not None:
                data[data == src.nodata] = _np.nan
            data[(_np.abs(data) > 70) | (data < -50)] = _np.nan
            return data, src.bounds, src.transform, src.crs
    except Exception as e:
        print(f" Error loading {file_path}: {e}")
        return None, None, None, None


def calculate_qa_stats(qa_file_path):
    """Return a short string summarising QA tier proportions.

    E.g. ``"QA: S-85.3%"``
    """
    import rasterio as _rio
    import numpy as _np

    try:
        with _rio.open(qa_file_path) as src:
            qa_data = src.read(1).astype(float)
            if src.nodata is not None:
                qa_data[qa_data == src.nodata] = _np.nan
            valid = _np.count_nonzero(~_np.isnan(qa_data))
            if valid == 0:
                return "No QA data"
            strict_pct = (_np.count_nonzero(qa_data == 1) / valid) * 100
            return f"QA: S-{strict_pct:.1f}%"
    except Exception:
        return "QA data unavailable"


def load_qa_geotiff(file_path):
    """Load a QA-source GeoTIFF (single band), masking NoData as NaN.

    Returns (data, bounds, transform, crs) or (None, …) on error.
    """
    import rasterio as _rio
    import numpy as _np

    try:
        with _rio.open(file_path) as src:
            data = src.read(1).astype(float)
            if src.nodata is not None:
                data[data == src.nodata] = _np.nan
            return data, src.bounds, src.transform, src.crs
    except Exception as e:
        print(f" Error loading QA file {file_path}: {e}")
        return None, None, None, None


def calculate_detailed_qa_stats(qa_data, lst_config):
    """Detailed per-tier QA percentages, e.g. ``"S:85.3% | M:14.7%"``.

    Parameters
    ----------
    qa_data : np.ndarray
    lst_config : dict   (must contain 'quality_hierarchy' and 'qa_levels_to_use')
    """
    import numpy as _np

    try:
        valid = _np.count_nonzero(~_np.isnan(qa_data))
        if valid == 0:
            return "No QA data"
        parts = []
        for tier in sorted(lst_config['qa_levels_to_use'],
                           key=lambda t: lst_config['quality_hierarchy'][t]['priority']):
            pv = lst_config['quality_hierarchy'][tier]['priority']
            pct = (_np.count_nonzero(qa_data == pv) / valid) * 100
            parts.append(f"{tier[0].upper()}:{pct:.1f}%")
        return " | ".join(parts)
    except Exception:
        return "QA data unavailable"


# -- LST map creation (used with Dask delayed in notebook) ---------------

def create_monthly_climatology_map(city_name, city_dir, lst_time,
                                   lst_config, vis_config, temporal_config,
                                   project_config):
    """Create a 4×3 monthly-climatology LST map for one city / time.

    .. note:: Apply ``@dask.delayed`` in the notebook, **not** here.

    Returns dict with *status*, *output_pdf*, *output_png*, etc.
    """
    import os as _os, glob as _glob, re as _re, traceback as _tb
    import numpy as _np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as _plt
    from matplotlib.gridspec import GridSpec as _GS
    from matplotlib.colors import LinearSegmentedColormap as _LSCM

    A5 = (5.83, 8.27)

    try:
        base = _os.path.join(project_config['lst_output_dir'],
                             f"City_{city_name}", 'LST_Temporal_Analysis')
        sub = 'Day' if lst_time == 'day' else 'Night'
        gdir = _os.path.join(base, sub, 'geotiff')
        if not _os.path.isdir(gdir):
            return {'status': 'error', 'message': f'Dir missing: {gdir}'}

        files = sorted(_glob.glob(
            _os.path.join(gdir,
                          f"{city_name}_LST_{lst_time.title()}_MonthlyClimatology_*.tif")))
        if not files:
            return {'status': 'no_data', 'message': f'No monthly files for {city_name} {lst_time}'}

        figs_dir = _os.path.join(base, sub, 'Figures')
        _os.makedirs(figs_dir, exist_ok=True)

        fig = _plt.figure(figsize=A5, dpi=300)
        _plt.tight_layout()
        gs = _GS(4, 3, figure=fig, hspace=0.15, wspace=0.1)

        months = ['January', 'February', 'March', 'April', 'May', 'June',
                  'July', 'August', 'September', 'October', 'November', 'December']
        cmap = _LSCM.from_list(vis_config['colormap_name'], vis_config['colors'])
        mn, mx, hl = vis_config['min_temp'], vis_config['max_temp'], vis_config['highlight_temp']

        im = None
        for fp in files:
            m = _re.search(r'MonthlyClimatology_(\d+)', _os.path.basename(fp))
            if not m:
                continue
            mnum = int(m.group(1))
            ax = fig.add_subplot(gs[(mnum - 1) // 3, (mnum - 1) % 3])
            data, *_ = load_geotiff(fp)
            if data is not None:
                im = ax.imshow(data, cmap=cmap, vmin=mn, vmax=mx)
                ax.set_title(months[mnum - 1], fontsize=8)
                ax.set_xticks([]); ax.set_yticks([])
                qf = fp.replace('_LST_', '_QA_Source_')
                if _os.path.exists(qf):
                    ax.text(0.98, 0.02, calculate_qa_stats(qf),
                            ha='right', va='bottom', transform=ax.transAxes,
                            fontsize=6.5,
                            bbox=dict(facecolor='white', alpha=0.7, pad=1, edgecolor='none'))
            else:
                ax.text(0.5, 0.5, 'No Data', ha='center', va='center',
                        transform=ax.transAxes)
                ax.set_title(months[mnum - 1], fontsize=8)

        fig.canvas.draw()
        if im is not None:
            cax = fig.add_axes([0.15, 0.05, 0.7, 0.02])
            ticks = list(range(int(mn), int(mx) + 1, 5))
            if hl not in ticks:
                ticks.append(hl); ticks.sort()
            cb = fig.colorbar(im, cax=cax, orientation='horizontal', ticks=ticks)
            cb.ax.set_xticklabels([str(t) for t in ticks], fontsize=6)
            cb.ax.get_xticklabels()[ticks.index(hl)].set_weight('bold')
            cb.set_label('Temperature (°C)', fontsize=8)

        yr = f"{temporal_config['years'][0]}-{temporal_config['years'][-1]}"
        fig.suptitle(f"{city_name} - {lst_time.title()}-time Monthly LST Climatology",
                     fontsize=10, y=0.95)
        fig.text(0.5, 0.01,
                 f"Median {lst_time.title()}-time LST values across years {yr}",
                 ha='center', fontsize=6)
        fig.canvas.draw()

        pdf = _os.path.join(figs_dir, f"{city_name}_{lst_time.title()}_Monthly_LST_Climatology.pdf")
        png = _os.path.join(figs_dir, f"{city_name}_{lst_time.title()}_Monthly_LST_Climatology.png")
        fig.savefig(pdf, bbox_inches='tight', format='pdf')
        fig.savefig(png, bbox_inches='tight', dpi=300, format='png')
        _plt.close(fig)

        return {'status': 'success', 'city': city_name, 'lst_time': lst_time,
                'type': 'monthly', 'output_pdf': pdf, 'output_png': png}
    except Exception as e:
        return {'status': 'error', 'city': city_name, 'lst_time': lst_time,
                'type': 'monthly', 'message': f"{e}\n{_tb.format_exc()}"}


def create_yearly_lst_map(city_name, city_dir, lst_time,
                          lst_config, vis_config, temporal_config,
                          project_config):
    """Create a 5×4 yearly-composite LST map for one city / time.

    .. note:: Apply ``@dask.delayed`` in the notebook, **not** here.

    Returns dict with *status*, *output_pdf*, *output_png*, etc.
    """
    import os as _os, glob as _glob, re as _re, traceback as _tb
    import numpy as _np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as _plt
    from matplotlib.gridspec import GridSpec as _GS
    from matplotlib.colors import LinearSegmentedColormap as _LSCM

    A5 = (5.83, 8.27)

    try:
        base = _os.path.join(project_config['lst_output_dir'],
                             f"City_{city_name}", 'LST_Temporal_Analysis')
        sub = 'Day' if lst_time == 'day' else 'Night'
        gdir = _os.path.join(base, sub, 'geotiff')
        if not _os.path.isdir(gdir):
            return {'status': 'error', 'message': f'Dir missing: {gdir}'}

        files = sorted(_glob.glob(
            _os.path.join(gdir,
                          f"{city_name}_LST_{lst_time.title()}_Yearly_*.tif")))
        if not files:
            return {'status': 'no_data', 'message': f'No yearly files for {city_name} {lst_time}'}

        figs_dir = _os.path.join(base, sub, 'Figures')
        _os.makedirs(figs_dir, exist_ok=True)

        n_r, n_c = 5, 4
        fig = _plt.figure(figsize=A5, dpi=300)
        _plt.tight_layout()
        gs = _GS(n_r, n_c, figure=fig, hspace=0.15, wspace=0.1)

        cmap = _LSCM.from_list(vis_config['colormap_name'], vis_config['colors'])
        mn, mx, hl = vis_config['min_temp'], vis_config['max_temp'], vis_config['highlight_temp']

        im = None
        for i, fp in enumerate(files[:n_r * n_c]):
            m = _re.search(r'Yearly_(\d{4})', _os.path.basename(fp))
            if not m:
                continue
            yr = m.group(1)
            ax = fig.add_subplot(gs[i // n_c, i % n_c])
            data, *_ = load_geotiff(fp)
            if data is not None:
                im = ax.imshow(data, cmap=cmap, vmin=mn, vmax=mx)
                ax.set_title(yr, fontsize=8)
                ax.set_xticks([]); ax.set_yticks([])
                qf = fp.replace('_LST_', '_QA_Source_')
                if _os.path.exists(qf):
                    ax.text(0.98, 0.02, calculate_qa_stats(qf),
                            ha='right', va='bottom', transform=ax.transAxes,
                            fontsize=6.5,
                            bbox=dict(facecolor='white', alpha=0.7, pad=1, edgecolor='none'))
            else:
                ax.text(0.5, 0.5, 'No Data', ha='center', va='center',
                        transform=ax.transAxes)
                ax.set_title(yr, fontsize=8)

        fig.canvas.draw()
        if im is not None:
            cax = fig.add_axes([0.15, 0.05, 0.7, 0.02])
            ticks = list(range(int(mn), int(mx) + 1, 5))
            if hl not in ticks:
                ticks.append(hl); ticks.sort()
            cb = fig.colorbar(im, cax=cax, orientation='horizontal', ticks=ticks)
            cb.ax.set_xticklabels([str(t) for t in ticks], fontsize=6)
            cb.ax.get_xticklabels()[ticks.index(hl)].set_weight('bold')
            cb.set_label('Temperature (°C)', fontsize=8)

        fig.suptitle(f"{city_name} - {lst_time.title()}-time Yearly LST Medians",
                     fontsize=10, y=0.95)
        fig.canvas.draw()

        pdf = _os.path.join(figs_dir, f"{city_name}_{lst_time.title()}_Yearly_LST.pdf")
        png = _os.path.join(figs_dir, f"{city_name}_{lst_time.title()}_Yearly_LST.png")
        fig.savefig(pdf, bbox_inches='tight', format='pdf')
        fig.savefig(png, bbox_inches='tight', dpi=300, format='png')
        _plt.close(fig)

        return {'status': 'success', 'city': city_name, 'lst_time': lst_time,
                'type': 'yearly', 'output_pdf': pdf, 'output_png': png}
    except Exception as e:
        return {'status': 'error', 'city': city_name, 'lst_time': lst_time,
                'type': 'yearly', 'message': f"{e}\n{_tb.format_exc()}"}


# -- Trend-line annotation helpers (Notebook 03, Cell 20) ----------------

def find_safe_text_position(ax, x, y, default_offset,
                            text_height_fraction=0.1):
    """Return a y-coordinate for an annotation that stays within
    the axes limits."""
    ylim = ax.get_ylim()
    y_range = ylim[1] - ylim[0]
    th = y_range * text_height_fraction

    new_y = y + default_offset
    if new_y + th > ylim[1]:
        new_y = y - abs(default_offset) - th
    elif new_y - th < ylim[0]:
        new_y = y + abs(default_offset) + th
    return max(ylim[0] + th * 0.5, min(new_y, ylim[1] - th * 0.5))


def place_trend_box_safely(ax, day_data=None, night_data=None):
    """Fixed box positions: Day → top-left, Night → bottom-left."""
    pos = {}
    if day_data is not None:
        pos['day'] = (0.02, 0.95)
    if night_data is not None:
        pos['night'] = (0.01, 0.03)
    return pos


def place_monthly_stats_box_safely(ax, day_data=None, night_data=None):
    """Fixed box positions: Day → top-right, Night → bottom-right."""
    pos = {}
    if day_data is not None:
        pos['day'] = (0.98, 0.95)
    if night_data is not None:
        pos['night'] = (0.99, 0.03)
    return pos


# -- Heatmap helpers (Notebook 03, Cell 21) ------------------------------

def compute_mk_significance(heatmap_df, alpha=0.05):
    """Mann-Kendall trend test per city (row).

    Returns ``{city_name: True/False}`` — *True* when the test finds a
    significant *increasing* trend at the given *alpha*.
    """
    import pymannkendall as _mk

    sig = {}
    for city in heatmap_df.index:
        row = heatmap_df.loc[city].dropna()
        if len(row) >= 4:
            try:
                res = _mk.original_test(row.values)
                sig[city] = (res.p < alpha and res.trend == 'increasing')
            except Exception:
                sig[city] = False
        else:
            sig[city] = False
    return sig


_MONTH_NAMES_SHORT = {1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr',
                      5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Aug',
                      9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'}


def create_single_page_heatmap(data, mk_sig, lst_time, time_dim,
                               fig_w, fig_h, output_path, dpi=300,
                               pre_sorted=False, separator_after_rows=None,
                               cluster_lookup=None):
    """Single-page LST heatmap with Mann-Kendall trend markers.

    Parameters
    ----------
    data : pd.DataFrame        (cities × time-periods)
    mk_sig : dict              {city: (trend_str, p_val)} — trend_str is
                               'increasing', 'decreasing', or ''; also
                               accepts legacy bool or bare string values.
    lst_time : str             'day' | 'night'
    time_dim : str             'year' | 'month'
    fig_w, fig_h : float       figure size in inches
    output_path : str          SVG output path (PDF saved alongside)
    pre_sorted : bool          if True, skip internal mean-LST sort
    separator_after_rows : list[int] | None
                               0-based row indices after which a thick
                               horizontal separator line is drawn
                               (e.g. [9, 10] draws lines after rows 9 and 10)
    cluster_lookup : dict | None
                               {city_name: cluster_int} — when provided, appends
                               '[C{N}]' to each city row label (yearly heatmaps only)
    """
    import os as _os
    from pathlib import Path as _Path
    import numpy as _np
    import matplotlib.pyplot as _plt
    import seaborn as _sns

    if data.empty:
        print(f"   No data for {lst_time} {time_dim}")
        return

    df = data.copy()
    if not pre_sorted:
        df['_mean'] = df.mean(axis=1)
        df = df.sort_values('_mean', ascending=False).drop('_mean', axis=1)

    if time_dim == 'month':
        df.columns = [_MONTH_NAMES_SHORT.get(int(c), c) for c in df.columns]

    # Build city label: "↑ CityName *** [C7]" / "↓ CityName *" / "CityName [C4]"
    # mk_sig values may be (trend, p_val) tuples, bare strings, or legacy bools
    def _mk_label(city):
        v = mk_sig.get(city, '')
        if isinstance(v, tuple):
            trend, p_val = v[0], float(v[1]) if len(v) > 1 else 1.0
        elif v is True:
            trend, p_val = 'increasing', 0.001   # legacy bool — assume sig
        elif v is False or v == '':
            trend, p_val = '', 1.0
        else:
            trend, p_val = str(v), 1.0  # bare string with unknown p

        if trend == 'increasing':
            arrow = '\u2191'
        elif trend == 'decreasing':
            arrow = '\u2193'
        else:
            arrow = ''

        stars = ('***' if p_val < 0.001 else
                 '**'  if p_val < 0.01  else
                 '*'   if p_val < 0.05  else '')

        # Build base label
        if arrow:
            base = f'{arrow} {city} {stars}' if stars else f'{arrow} {city}'
        else:
            base = city

        # Append cluster label if lookup provided
        if cluster_lookup:
            cid = cluster_lookup.get(city)
            if cid is not None:
                base = f'{base} [C{int(cid)}]'
        return base

    # Yearly: full label with MK arrow + stars + cluster
    # Monthly: cluster label only (no MK significance — monthly stats not computed)
    def _monthly_label(city):
        base = city
        if cluster_lookup:
            cid = cluster_lookup.get(city)
            if cid is not None:
                base = f'{city} [C{int(cid)}]'
        return base

    # Apply MK labels when yearly, OR when mk_sig is explicitly provided (e.g. cluster monthly)
    # Fall back to cluster-suffix-only label when no significance data supplied (city monthly)
    if time_dim == 'year' or mk_sig:
        df.index = [_mk_label(c) for c in df.index]
    elif cluster_lookup:
        df.index = [_monthly_label(c) for c in df.index]

    n_cities = len(df)
    n_cols = len(df.columns)

    # Scale figure height so every city row is tall enough to show its label
    row_height = 0.22  # inches per city row
    min_h = max(fig_h, n_cities * row_height + 1.5)

    # Consistent small font sizes for both axes
    tick_fs = max(4, min(6, 350 / n_cities))
    annot_fs = max(3.5, min(5.5, 250 / (n_cities * n_cols) + 3.5))

    cmap = 'YlOrRd'
    vals = df.values.flatten()
    vals = vals[~_np.isnan(vals)]
    vmin, vmax = (_np.nanmin(vals), _np.nanmax(vals)) if len(vals) else (None, None)

    label = 'Yearly' if time_dim == 'year' else 'Monthly Climatology'

    fig, ax = _plt.subplots(figsize=(fig_w, min_h), dpi=dpi)
    _sns.heatmap(df, annot=True, fmt='.1f', cmap=cmap,
                 vmin=vmin, vmax=vmax, linewidths=0.3, linecolor='gray',
                 ax=ax, annot_kws={'fontsize': annot_fs},
                 cbar_kws={'label': 'LST (°C)', 'shrink': 0.4, 'pad': 0.015,
                           'aspect': 25})

    # Smaller colorbar label
    cbar = ax.collections[0].colorbar
    cbar.ax.tick_params(labelsize=tick_fs)
    cbar.set_label('LST (°C)', fontsize=tick_fs + 1)

    if time_dim == 'year':
        ax.set_title(f'{lst_time.title()}-time LST — {label}\n'
                     f'\u2191\u2193 MK trend  * p<0.05  ** p<0.01  *** p<0.001',
                     fontsize=8, fontweight='bold', pad=8)
    else:
        ax.set_title(f'{lst_time.title()}-time LST — {label}',
                     fontsize=8, fontweight='bold', pad=8)
    ax.set_xlabel('Year' if time_dim == 'year' else 'Month',
                  fontsize=tick_fs + 1, fontweight='bold')
    ax.set_ylabel('City', fontsize=tick_fs + 1, fontweight='bold')
    # Same label size on both axes
    ax.tick_params(axis='y', rotation=0, labelsize=tick_fs)
    ax.tick_params(axis='x', rotation=45 if time_dim == 'year' else 0,
                   labelsize=tick_fs)
    # Force ALL city labels to be shown — prevent matplotlib auto-pruning
    from matplotlib.ticker import FixedLocator as _FixedLocator
    ax.yaxis.set_major_locator(_FixedLocator(_np.arange(n_cities) + 0.5))
    ax.set_yticklabels(df.index, fontsize=tick_fs)
    ax.set_ylim(n_cities, 0)  # ensure full range visible

    # Draw thick separator lines between row groups (publication heatmaps)
    if separator_after_rows:
        for row_idx in separator_after_rows:
            y = row_idx + 1   # seaborn y-axis: row 0 top → n_cities bottom
            ax.axhline(y=y, color='black', linewidth=2.0, zorder=10)

    _plt.tight_layout(pad=0.5)

    out_path = _Path(output_path)
    fig.savefig(out_path, dpi=dpi, bbox_inches='tight')

    # Always save a separate PDF companion without overwriting the primary file.
    pdf_path = out_path.with_suffix('.pdf')
    if pdf_path != out_path:
        fig.savefig(pdf_path, format='pdf', bbox_inches='tight')

    _plt.close(fig)
    print(f'   Saved: {_os.path.basename(str(out_path))}')


# ─── NB03 temporal trend chart ───────────────────────────────────────────────

_NB03_COLOURS = {
    # Day-time: warm orange/gold tones
    'uc_day':    '#E07B00',
    'bra_day':   '#B8860B',
    'delta_day': '#B22222',       # RED day SUHI
    'cr_day_fill':   '#FFDAB9',
    # Night-time: near-black to grey tones (not blue)
    'uc_night':  '#1C1C1C',
    'bra_night': '#6B6B6B',
    'delta_night':  '#9932CC',    # PURPLE night SUHI
    'cr_night_fill': '#A8A8A8',
}
_NB03_MARKERS   = {'uc': 'o', 'bra': 's', 'delta': '^'}
_NB03_MON_ABBR  = ['Jan','Feb','Mar','Apr','May','Jun',
                    'Jul','Aug','Sep','Oct','Nov','Dec']


def create_temporal_chart(city, df_ann, df_mon,
                           df_del_ann, df_del_mon,
                           ann_stats, mon_stats,
                           del_ann_stats, del_mon_stats,
                           save_path=None, dpi=150,
                           ylim_lst=(10, 50),
                           ylim_suhii=(-3, 3)):
    """
    Combined annual (left) + monthly (right) LST trend chart.

    Both panels show day and night on the same axes.
    Delta (UC-BRA) on right y-axis of BOTH panels.
    Sen slope as thin dashed overlay per zone.
    CR P5-P95 as shaded envelope.
    Peak/trough annotated with hollow circle + label.
    Cloud flag: grey x at panel bottom for low-coverage years/months.

    Parameters
    ----------
    city : str
    df_ann, df_mon : pd.DataFrame
        Annual / monthly aggregated data (zone, period, year/month, median_lst,
        p05_lst, p95_lst, low_coverage).
    df_del_ann, df_del_mon : pd.DataFrame
        Delta (UC-BRA) annual / monthly data (period, year/month, delta_lst).
    ann_stats, mon_stats : pd.DataFrame
        Pre-computed MK + Sen stats keyed by (city, zone, period).
    del_ann_stats, del_mon_stats : pd.DataFrame
        Delta trend stats keyed by (city, period).
    save_path : Path | str | None
    dpi : int

    Returns
    -------
    matplotlib.figure.Figure
    """
    import numpy as _np
    import matplotlib.pyplot as _plt
    import matplotlib.patches as _mp
    from matplotlib.lines import Line2D as _L2D
    from matplotlib.gridspec import GridSpec as _GS

    C = _NB03_COLOURS
    MK = _NB03_MARKERS
    MA = _NB03_MON_ABBR
    _ZONE_LABEL = {'urban_core': 'UC', 'bra': 'BRA', 'city_region': 'CR'}

    def _trend_line(idx, slope, intercept):
        x = _np.array(idx, dtype=float)
        return intercept + slope * (x - x[0])

    def _stats_row(stats_df, zone, period):
        if stats_df is None or stats_df.empty:
            return None
        if 'zone' in stats_df.columns:
            sub = stats_df[(stats_df['zone'] == zone) & (stats_df['period'] == period)]
        else:
            sub = stats_df[stats_df['period'] == period]
        return sub.iloc[0] if not sub.empty else None

    def _stats_box(ax, rows, header, x=0.02, y=0.98, va='top'):
        """Compact MK/Sen stats box.  va='top' → top-left; va='bottom' → bottom-left."""
        lines = [f'\u2500 {header} \u2500']
        any_data = False
        for label, row in rows:
            if row is None:
                continue
            any_data = True
            sym = {'increasing': '\u2191', 'decreasing': '\u2193'}.get(
                str(row.get('mk_trend', '')), '\u2014')
            p = row.get('mk_p', _np.nan)
            try:
                pf = float(p)
                sig = '***' if pf < 0.001 else ('**' if pf < 0.01 else ('*' if pf < 0.05 else 'ns'))
            except (TypeError, ValueError):
                sig = ''
            hr = '[H&R]' if row.get('autocorr_corrected', False) else ''
            bd = row.get('sen_slope_per_decade', _np.nan)
            try:
                dec_str = f'{float(bd):+.2f}\u00b0C/dec'
            except (TypeError, ValueError):
                dec_str = ''
            parts = [sym, sig]
            if dec_str: parts.append(dec_str)
            if hr:      parts.append(hr)
            lines.append(f'  {label}: {" ".join(pt for pt in parts if pt)}')
        if any_data:
            ax.text(x, y, '\n'.join(lines),
                    transform=ax.transAxes, fontsize=7.0,
                    va=va, ha='left', family='monospace',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                              alpha=0.50, edgecolor='none'),
                    zorder=10, clip_on=False)

    def _annotate_peak_trough(ax, x_vals, y_vals, color, side='left', is_monthly=False):
        if len(y_vals) == 0:
            return
        hi_i = _np.nanargmax(y_vals)
        lo_i = _np.nanargmin(y_vals)
        # Skip trough annotation if it coincides with peak (flat series)
        pairs = [(hi_i, 'peak'), (lo_i, 'trough')]
        if hi_i == lo_i:
            pairs = [(hi_i, 'peak')]

        x_min, x_max = ax.get_xlim()
        y_min, y_max = ax.get_ylim()
        x_span = x_max - x_min if x_max != x_min else 1.0
        y_span = y_max - y_min if y_max != y_min else 1.0

        for i, lab in pairs:
            ax.plot(x_vals[i], y_vals[i], 'o', ms=8, mfc='none',
                    mec=color, mew=1.3, zorder=9, clip_on=True)
            x_label = MA[int(x_vals[i]) - 1] if is_monthly else str(x_vals[i])

            # Adaptive horizontal offset: push label away from nearest x-edge
            x_frac = (x_vals[i] - x_min) / x_span
            if x_frac > 0.65:       # point is in right third → label goes left
                xoff, ha = -5, 'right'
            else:                   # otherwise label goes right
                xoff, ha = +5, 'left'

            # Adaptive vertical offset: peak label goes up unless near top edge
            y_frac = (y_vals[i] - y_min) / y_span
            if lab == 'peak':
                yoff = -14 if y_frac > 0.80 else +14
            else:
                yoff = +14 if y_frac < 0.20 else -14

            ax.annotate(f'{x_label}: {y_vals[i]:.1f}\u00b0C',
                        xy=(x_vals[i], y_vals[i]),
                        xytext=(xoff, yoff),
                        textcoords='offset points',
                        fontsize=5.5, color=color, ha=ha,
                        annotation_clip=True,
                        bbox=dict(boxstyle='round,pad=0.15', facecolor='white',
                                  edgecolor=color, alpha=0.85, lw=0.5),
                        arrowprops=dict(arrowstyle='-', color=color,
                                        lw=0.5, ls='solid'))

    # ── Smoothing helper ─────────────────────────────────────────────────────
    def _smooth(x, y, kind='annual'):
        """Return smoothed y values. Gaussian filter for annual; spline for monthly."""
        try:
            from scipy.ndimage import gaussian_filter1d as _gf
            from scipy.interpolate import make_interp_spline as _mis
        except ImportError:
            return y   # scipy not available — return raw
        if len(y) < 4:
            return y
        if kind == 'monthly':
            # Cubic spline on 1-12, evaluated on fine grid then sampled back at integers
            xs = _np.array(x, dtype=float)
            ys = _np.array(y, dtype=float)
            try:
                spl = _mis(xs, ys, k=3)
                xf  = _np.linspace(xs[0], xs[-1], 300)
                yf  = spl(xf)
                # Sample back at original integer months
                return _np.array([float(spl(_np.array([xi])))[0] for xi in xs])
            except Exception:
                return y
        else:
            # Gaussian blur — sigma=0.8 gives gentle smoothing on 20-pt series
            return _gf(_np.array(y, dtype=float), sigma=0.8)

    # ── A4 landscape figure (11.0 × 7.0 in) — two panels side by side ───────
    # Font size constants for A4 publication legibility
    _FS_TITLE  = 10    # figure suptitle
    _FS_AX     = 8.5   # axis labels
    _FS_TICK   = 7.5   # tick labels
    _FS_ANNOT  = 5.5   # peak/trough annotations
    _FS_SEAS   = 6.5   # wet-season text
    _FS_LEG    = 7.5   # legend

    fig = _plt.figure(figsize=(11.0, 7.0))
    fig.suptitle(f'{city} \u2014 MODIS LST Temporal Analysis (Day & Night)',
                 fontsize=_FS_TITLE, fontweight='bold', y=1.01)
    gs    = _GS(1, 2, figure=fig, wspace=0.25)
    ax_a  = fig.add_subplot(gs[0])
    ax_m  = fig.add_subplot(gs[1])
    ax_a2 = ax_a.twinx()
    ax_m2 = ax_m.twinx()

    # Uniform LST y-axis for cross-city/cluster comparability
    if ylim_lst is not None:
        ax_a.set_ylim(ylim_lst)
        ax_m.set_ylim(ylim_lst)

    for period in ['day', 'night']:
        suf = f'_{period}'
        uc_col  = C[f'uc{suf}'];  bra_col = C[f'bra{suf}']
        del_col = C[f'delta{suf}']; cr_fill = C[f'cr{suf}_fill']

        # ── Annual panel ──────────────────────────────────────────────────────
        for zone, col, mk in [('urban_core', uc_col, 'uc'),
                               ('bra',        bra_col, 'bra')]:
            sub = df_ann[(df_ann['zone'] == zone) & (df_ann['period'] == period)]
            if sub.empty:
                continue
            sub = sub.sort_values('year')
            x, y_raw = sub['year'].values, sub['median_lst'].values
            y = _smooth(x, y_raw, kind='annual')
            mask = sub['low_coverage'].values if 'low_coverage' in sub.columns else _np.zeros(len(sub), dtype=bool)
            ax_a.plot(x, y, color=col, lw=1.6, zorder=4)
            # Sen slope overlay
            sr = _stats_row(ann_stats, zone, period)
            if sr is not None and not _np.isnan(sr.get('sen_slope_per_year', _np.nan)):
                yhat = _trend_line(x, sr['sen_slope_per_year'], sr['intercept'])
                ax_a.plot(x, yhat, color=col, lw=0.9, ls='--', zorder=3)
            # Cloud flag
            for xi in x[mask]:
                ax_a.text(xi, y.min() - 0.5, '\u2715', ha='center', va='bottom',
                          fontsize=5, color='#999', zorder=5)
            # Peak/trough — UC only to avoid clutter
            if zone == 'urban_core':
                _annotate_peak_trough(ax_a, list(x), list(y_raw), col)

        # CR P5-P95 band (only if percentile columns exist)
        cr_a = df_ann[(df_ann['zone'] == 'city_region') & (df_ann['period'] == period)]
        if not cr_a.empty and 'p05_lst' in cr_a.columns and 'p95_lst' in cr_a.columns:
            cr_s = cr_a.sort_values('year')
            ax_a.fill_between(cr_s['year'], cr_s['p05_lst'], cr_s['p95_lst'],
                               color=cr_fill, alpha=0.45, zorder=1,
                               label=f'City Region (range) {period}')

        # ── SUHII on right y-axis — thin prominent line with uniform cosmetic glow ──
        # set_ylim is called AFTER the loop (across both periods) to avoid clipping
        da = df_del_ann[df_del_ann['period'] == period] if not df_del_ann.empty else _np.empty(0)
        if hasattr(da, 'empty') and not da.empty:
            da = da.sort_values('year')
            xd, yd_raw = da['year'].values, da['delta_lst'].values
            yd = _smooth(xd, yd_raw, kind='annual')
            # Cosmetic glow: wide transparent line behind the actual line
            ax_a2.plot(xd, yd, color=del_col, lw=7, alpha=0.15, zorder=6, solid_capstyle='round')
            ax_a2.plot(xd, yd, color=del_col, lw=2.0, ls='-', zorder=8)
            # SUHII Sen slope dashed overlay
            dr = _stats_row(del_ann_stats, 'delta_uc_bra', period)
            if dr is not None and not _np.isnan(dr.get('sen_slope_per_year', _np.nan)):
                ax_a2.plot(xd, _trend_line(xd, dr['sen_slope_per_year'], dr['intercept']),
                           color=del_col, lw=1.2, ls='--', zorder=7)

        # ── Monthly panel ─────────────────────────────────────────────────────
        for zone, col, mk in [('urban_core', uc_col, 'uc'),
                               ('bra',        bra_col, 'bra')]:
            sub = df_mon[(df_mon['zone'] == zone) & (df_mon['period'] == period)]
            if sub.empty:
                continue
            clim = sub.groupby('month')['median_lst'].mean().reset_index()
            x, y_raw = clim['month'].values, clim['median_lst'].values
            y = _smooth(x, y_raw, kind='monthly')
            ax_m.plot(x, y, color=col, lw=1.6, zorder=4)
            sr = _stats_row(mon_stats, zone, period)
            if sr is not None and not _np.isnan(sr.get('sen_slope_per_year', _np.nan)):
                yhat = _trend_line(x, sr['sen_slope_per_year'], sr['intercept'])
                ax_m.plot(x, yhat, color=col, lw=0.9, ls='--', zorder=3)
            _annotate_peak_trough(ax_m, list(x), list(y_raw), col, is_monthly=True)

        # CR P5-P95 monthly (only if percentile columns exist)
        cr_m = df_mon[(df_mon['zone'] == 'city_region') & (df_mon['period'] == period)]
        if not cr_m.empty and 'p05_lst' in cr_m.columns and 'p95_lst' in cr_m.columns:
            cr_c = cr_m.groupby('month').agg(
                p05=('p05_lst', 'mean'), p95=('p95_lst', 'mean')).reset_index()
            ax_m.fill_between(cr_c['month'], cr_c['p05'], cr_c['p95'],
                               color=cr_fill, alpha=0.45, zorder=1,
                               label=f'City Region (range) {period}')

        # SUHII monthly — thin prominent line with uniform cosmetic glow
        # set_ylim is called AFTER the loop (across both periods) to avoid clipping
        dm = df_del_mon[df_del_mon['period'] == period] if not df_del_mon.empty else _np.empty(0)
        if hasattr(dm, 'empty') and not dm.empty:
            dc = dm.groupby('month')['delta_lst'].mean().reset_index()
            xm, ym_raw = dc['month'].values, dc['delta_lst'].values
            ym = _smooth(xm, ym_raw, kind='monthly')
            ax_m2.plot(xm, ym, color=del_col, lw=7, alpha=0.15, zorder=6, solid_capstyle='round')
            ax_m2.plot(xm, ym, color=del_col, lw=2.0, ls='-', zorder=8)
            rev_months = xm[ym_raw < 0]
            if len(rev_months) > 0 and period == 'night':
                ax_m2.annotate('SUHI\nreversal',
                                xy=(rev_months[len(rev_months)//2], 0),
                                xytext=(0, -20), textcoords='offset points',
                                fontsize=_FS_SEAS, color=del_col, ha='center',
                                arrowprops=dict(arrowstyle='->', color=del_col, lw=0.7))

    # ── SUHII axis limits — set once across BOTH periods to prevent clipping ──
    def _suhii_ylim(df_del, val_col='delta_lst'):
        if not hasattr(df_del, 'empty') or df_del.empty:
            return None
        vals = df_del[val_col].dropna().values
        if len(vals) == 0:
            return None
        c    = (vals.max() + vals.min()) / 2
        half = max(vals.max() - vals.min(), 0.3) / 2
        return (c - half * 3.5, c + half * 3.5)

    _lim_a = ylim_suhii if ylim_suhii is not None else _suhii_ylim(df_del_ann)
    _lim_m = ylim_suhii if ylim_suhii is not None else _suhii_ylim(df_del_mon)
    if _lim_a:
        ax_a2.set_ylim(*_lim_a)
    ax_a2.axhline(0, color='#888', lw=0.7, ls=':', alpha=0.7, zorder=2)
    if _lim_m:
        ax_m2.set_ylim(*_lim_m)
    ax_m2.axhline(0, color='#888', lw=0.7, ls=':', alpha=0.7, zorder=2)

    # Wet-season shading in monthly panel
    ax_m.axvspan(5.5, 10.5, color='#AADDFF', alpha=0.12, zorder=0)
    ax_m.text(8, 0.97, 'Wet season', fontsize=_FS_SEAS, color='#5588AA',
              ha='center', va='top', style='italic',
              transform=ax_m.get_xaxis_transform())

    # ── Axis labels & ticks ───────────────────────────────────────────────────
    ax_a.set_xlabel('Year',  fontsize=_FS_AX)
    ax_a.set_ylabel('Annual median LST (\u00b0C)', fontsize=_FS_AX)
    ax_a2.set_ylabel('SUHII — UC\u2212BRA (\u00b0C)', fontsize=_FS_AX - 0.5,
                     color='#555')
    ax_m.set_xlabel('Month', fontsize=_FS_AX)
    ax_m.set_ylabel('Monthly mean LST (\u00b0C)', fontsize=_FS_AX)
    ax_m2.set_ylabel('SUHII — UC\u2212BRA (\u00b0C)', fontsize=_FS_AX - 0.5,
                     color='#555')
    ax_m.set_xticks(range(1, 13))
    ax_m.set_xticklabels(MA, fontsize=_FS_TICK)
    for _ax in [ax_a, ax_a2, ax_m, ax_m2]:
        _ax.tick_params(labelsize=_FS_TICK)
    # Integer year ticks derived from data
    _all_yrs = sorted({int(y) for y in df_ann['year'].dropna().unique()
                        if 2000 < float(y) < 2100})
    if _all_yrs:
        _tick_step = 2 if len(_all_yrs) > 10 else 1
        _tick_yrs  = [y for y in _all_yrs if (y - _all_yrs[0]) % _tick_step == 0]
        ax_a.set_xticks(_tick_yrs)
        ax_a.set_xticklabels([str(y) for y in _tick_yrs],
                              fontsize=_FS_TICK, rotation=45, ha='right')

    # ── Stats boxes — day at top-left, night at bottom-left of each panel ───
    _day_hdr   = 'Day-time trend (- - = Sen slope)'
    _night_hdr = 'Night-time trend (- - = Sen slope)'
    # Annual panel
    _stats_box(ax_a, [
        ('UC',    _stats_row(ann_stats,     'urban_core',   'day')),
        ('BRA',   _stats_row(ann_stats,     'bra',          'day')),
        ('SUHII', _stats_row(del_ann_stats, 'delta_uc_bra', 'day')),
    ], header=_day_hdr, x=0.02, y=0.98, va='top')
    _stats_box(ax_a, [
        ('UC',    _stats_row(ann_stats,     'urban_core',   'night')),
        ('BRA',   _stats_row(ann_stats,     'bra',          'night')),
        ('SUHII', _stats_row(del_ann_stats, 'delta_uc_bra', 'night')),
    ], header=_night_hdr, x=0.02, y=0.02, va='bottom')
    # Monthly panel
    _stats_box(ax_m, [
        ('UC',    _stats_row(mon_stats,     'urban_core',   'day')),
        ('BRA',   _stats_row(mon_stats,     'bra',          'day')),
        ('SUHII', _stats_row(del_mon_stats, 'delta_uc_bra', 'day')),
    ], header=_day_hdr, x=0.02, y=0.98, va='top')
    _stats_box(ax_m, [
        ('UC',    _stats_row(mon_stats,     'urban_core',   'night')),
        ('BRA',   _stats_row(mon_stats,     'bra',          'night')),
        ('SUHII', _stats_row(del_mon_stats, 'delta_uc_bra', 'night')),
    ], header=_night_hdr, x=0.02, y=0.02, va='bottom')

    # ── Legend — single row at bottom centre, pure proxies, no markers ────────
    _sl = dict(lw=1.6, ls='-')
    _leg_handles = [
        _L2D([0],[0], color=C['uc_day'],       **_sl,           label='UC — day'),
        _L2D([0],[0], color=C['uc_night'],     **_sl,           label='UC — night'),
        _L2D([0],[0], color=C['bra_day'],       **_sl,          label='BRA — day'),
        _L2D([0],[0], color=C['bra_night'],     **_sl,          label='BRA — night'),
        _L2D([0],[0], color=C['delta_day'],   lw=2.0, ls='-',   label='SUHII — day'),
        _L2D([0],[0], color=C['delta_night'], lw=2.0, ls='-',   label='SUHII — night'),
        _mp.Patch(facecolor=C['cr_day_fill'],   alpha=0.55,     label='City Region range — day'),
        _mp.Patch(facecolor=C['cr_night_fill'], alpha=0.55,     label='City Region range — night'),
        _L2D([0],[0], color='#777', lw=0.9, ls='--',            label="Sen\u2019s slope (- -)"),
    ]
    fig.legend(handles=_leg_handles, loc='lower center', ncol=5,
               fontsize=_FS_LEG, framealpha=0.92, bbox_to_anchor=(0.5, -0.12))

    _plt.tight_layout()
    if save_path:
        from pathlib import Path as _P
        sp = _P(save_path)
        sp.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(sp,                dpi=dpi, bbox_inches='tight', facecolor='white')
        fig.savefig(sp.with_suffix('.pdf'), format='pdf',
                    bbox_inches='tight', facecolor='white')
        print(f'   Saved: {sp.name}')
    return fig


# ─── NB03 stakeholder validation sunburst charts ─────────────────────────────

def create_validation_sunburst_charts(validation_df, monthly_validation_df,
                                       results_dir, dpi=150):
    """
    Multi-layer sunburst donut charts for stakeholder validation.

    Two figures produced:
    - Annual: Q61 (perceived warming) vs UC MK trend
    - Monthly: Q58 (peak season) vs UC hottest month

    Each city gets one donut with three rings:
      Inner  (r=0.50): city share of total stakeholders
      Middle (r=0.70): agreement (blue) vs disagreement (red)
      Outer  (r=0.90): duration of stay in city (colour-coded)

    Parameters
    ----------
    validation_df : pd.DataFrame
        Annual validation rows. Must have columns: city, n_stakeholders,
        pct_of_total, overall_agreement, duration_counts (dict),
        day_significance, night_significance.
    monthly_validation_df : pd.DataFrame
        Monthly validation rows. Must have: city, n_stakeholders,
        pct_of_total, overall_agreement, duration_counts (dict),
        lst_day_hottest, lst_night_hottest.
    results_dir : Path | str
    dpi : int

    Returns
    -------
    tuple[Figure, Figure]  (fig_annual, fig_monthly)
    """
    import math as _math
    import numpy as _np
    import matplotlib.pyplot as _plt
    from pathlib import Path as _P

    _DUR_CATS = ['Within the last 5 years', 'Between 5 - 10 years',
                 'Between 11 - 15 years', 'Over 15 years']
    _DUR_COL  = {
        'Within the last 5 years': '#FFD700',
        'Between 5 - 10 years':    '#1AC9F5',
        'Between 11 - 15 years':   '#32CD32',
        'Over 15 years':           '#8B008B',
    }
    _AGREE_COL    = '#0000FF'
    _DISAGREE_COL = '#FF0000'

    def _draw_panel(ax, row, total_stake, mode):
        n     = row['n_stakeholders']
        pct_t = row['pct_of_total']
        agr   = row['overall_agreement']
        dur   = row.get('duration_counts', {})

        # ── Helper: place count labels inside ring wedges ─────────────────────
        # Skips wedges narrower than min_deg° (unreadable) and zero-count wedges.
        # Font size is intentionally smaller than the central total-n label (18pt).
        def _label_ring(patches, counts, min_deg=18, fs=6, col='white'):
            for w, v in zip(patches, counts):
                span = abs(w.theta2 - w.theta1)
                if span < min_deg or v == 0:
                    continue
                mid_rad = _np.radians((w.theta1 + w.theta2) / 2)
                r_c = w.r - w.width / 2   # radial centre of the ring band
                ax.text(r_c * _np.cos(mid_rad), r_c * _np.sin(mid_rad),
                        str(int(round(v))), ha='center', va='center',
                        fontsize=fs, fontweight='bold', color=col)

        # ── Inner ring: city/cluster share of total stakeholders ──────────────
        inner_p, _ = ax.pie([n, total_stake - n], radius=0.50,
               colors=['#FFA500', '#E0E0E0'],
               wedgeprops=dict(width=0.20, edgecolor='white', linewidth=2),
               startangle=90)
        # Label the orange wedge only (the grey = all other cities, not labelled)
        _label_ring(inner_p[:1], [n], min_deg=10, fs=5, col='white')

        # ── Middle ring: agreed vs disagreed ──────────────────────────────────
        if not (isinstance(agr, float) and _np.isnan(agr)):
            agr_n = int(round(n * agr / 100))
            dis_n = n - agr_n
            mid_p, _ = ax.pie([agr, 100 - agr], radius=0.70,
                   colors=[_AGREE_COL, _DISAGREE_COL],
                   wedgeprops=dict(width=0.20, edgecolor='white', linewidth=2),
                   startangle=90)
            _label_ring(mid_p, [agr_n, dis_n], min_deg=18, fs=6, col='white')

        # ── Outer ring: duration of stay ──────────────────────────────────────
        dur_s = [float(dur.get(d, 0) or 0) for d in _DUR_CATS]
        if sum(dur_s) > 0:
            out_p, _ = ax.pie(dur_s, radius=0.90,
                   colors=[_DUR_COL[d] for d in _DUR_CATS],
                   wedgeprops=dict(width=0.20, edgecolor='white', linewidth=2),
                   startangle=90)
            _label_ring(out_p, dur_s, min_deg=20, fs=5.5, col='white')

        ax.text(0,  0.15, row['city'],  ha='center', va='center',
                fontsize=10, fontweight='bold')
        ax.text(0, -0.05, str(n),       ha='center', va='center',
                fontsize=18, fontweight='bold')
        ax.text(0, -0.25, f'({pct_t:.1f}%)', ha='center', va='center', fontsize=9)

        if mode == 'annual':
            lbl = (f"Day: {row['day_significance']}\n"
                   f"Night: {row['night_significance']}")
        else:
            # Show what stakeholders said + what MODIS says (day and night peak)
            stk_resp = str(row.get('stakeholder_peak_response', 'N/A') or 'N/A')
            # Shorten long quarter strings for readability
            _short = {
                'March \u2013 May': 'Mar–May', 'March - May': 'Mar–May',
                'June \u2013 August': 'Jun–Aug', 'June - August': 'Jun–Aug',
                'September \u2013 November': 'Sep–Nov', 'September - November': 'Sep–Nov',
                'December \u2013 February': 'Dec–Feb', 'December - February': 'Dec–Feb',
            }
            stk_short = _short.get(stk_resp, stk_resp)
            lbl = (f"Stakeholders: {stk_short}\n"
                   f"LST day peak:   {row['lst_day_hottest']}\n"
                   f"LST night peak: {row['lst_night_hottest']}")
        ax.text(0.5, 0.94, lbl, transform=ax.transAxes,
                fontsize=7.5, ha='center', va='top',
                bbox=dict(boxstyle='round,pad=0.4', facecolor='lightyellow',
                          edgecolor='gray', linewidth=0.8))
        ax.set_aspect('equal')

    def _build_fig(df_plot, total_stake, mode, title):
        rows = df_plot[df_plot['n_stakeholders'] > 0]
        n_c = len(rows)
        if n_c == 0:
            return None
        mc  = min(5, n_c)
        nr  = _math.ceil(n_c / mc)
        fig = _plt.figure(figsize=(8 * mc, 8 * nr + 3))
        gs  = fig.add_gridspec(nr + 1, mc,
                                height_ratios=[5] * nr + [1], hspace=0.30)
        for idx, (_, row) in enumerate(rows.iterrows()):
            r, c = divmod(idx, mc)
            _draw_panel(fig.add_subplot(gs[r, c]), row, total_stake, mode)

        leg = fig.add_subplot(gs[nr, :])
        leg.axis('off')
        handles = [
            _plt.Line2D([0],[0], marker='s', color='w',
                        markerfacecolor=_AGREE_COL,    markersize=14,
                        label='Agrees with LST'),
            _plt.Line2D([0],[0], marker='s', color='w',
                        markerfacecolor=_DISAGREE_COL, markersize=14,
                        label='Disagrees with LST'),
        ]
        for d in _DUR_CATS:
            handles.append(_plt.Line2D([0],[0], marker='s', color='w',
                                        markerfacecolor=_DUR_COL[d],
                                        markersize=14, label=d))
        leg.legend(handles=handles, loc='center', ncol=3,
                   frameon=False, fontsize=12)
        fig.suptitle(title, fontsize=14, fontweight='bold', y=0.99)
        _plt.tight_layout()
        return fig

    out = _P(results_dir)
    tot_ann = validation_df['n_stakeholders'].sum()
    tot_mon = monthly_validation_df['n_stakeholders'].sum()

    fig_a = _build_fig(
        validation_df, tot_ann, 'annual',
        ('Annual Validation: Perceived Warming vs UC LST Trend\n'
         'Inner: City share  |  Middle: Agreement/Disagreement  |  Outer: Duration'),
    )
    fig_m = _build_fig(
        monthly_validation_df, tot_mon, 'monthly',
        ('Monthly Validation: Peak Season vs UC Hottest Month (Day OR Night)\n'
         'Inner: City share  |  Middle: Agreement/Disagreement  |  Outer: Duration'),
    )

    for fig, stem in [(fig_a, 'Stakeholder_Validation_Annual_Sunburst'),
                      (fig_m, 'Stakeholder_Validation_Monthly_Sunburst')]:
        if fig is None:
            continue
        fp = out / stem
        fig.savefig(fp.with_suffix('.svg'), bbox_inches='tight', facecolor='white')
        fig.savefig(fp.with_suffix('.pdf'), format='pdf',
                    bbox_inches='tight', facecolor='white')
        _plt.close(fig)
        print(f'  Saved: {stem}.svg/.pdf')


# =============================================================================
# NB04 — Daily LST Visualization Functions
# =============================================================================

def create_nb04_event_plot(
    modis_df,
    era5_df,
    city_name: str,
    study_year: int,
    audit_day: dict,
    audit_night: dict,
    output_path=None,
    figsize=(11.69, 8.27),
    dpi: int = 300,
    show_inline: bool = False,
):
    """
    Two-panel daily LST time-series chart for NB04 (A4 landscape).

    Layout
    ------
    Top panel    : MODIS UC LST — day (orange/red) + night (blue/navy)
    Bottom panel : ERA5-Land UC LST — day (orange/red) + night (blue/navy)

    Annotations per panel
    ~~~~~~~~~~~~~~~~~~~~~
    * Shaded fill: LST min-max range (light, per period)
    * Solid line : median LST
    * Dashed lines: P90 threshold (day = red dashed, night = blue dashed)
    * Black dots : individual MODIS / ERA5 hot days/nights above P90
    * Grey shading: every persistent event window (≥ 2 consecutive)
    * Coloured bracket: selected SEVIRI event — bold, labelled with tier
    * Pi/Pii style horizontal bracket with vertical end-bars

    Parameters
    ----------
    modis_df, era5_df : pd.DataFrame or None
        Full daily LST DataFrames (columns: date, day_lst_min/median/max,
        night_lst_min/median/max).
    city_name : str
    study_year : int
    audit_day, audit_night : dict
        Output of ``daily_analysis_utils.run_city_event_pipeline`` for 'day'
        and 'night' respectively.
    output_path : str or Path or None
        If given, figure is saved here (SVG).
    figsize : tuple
        Figure size in inches (default A4 landscape 11.69 × 8.27).
    dpi : int
    show_inline : bool
        If True the figure is shown interactively (plt.show()), else closed
        after saving.

    Returns
    -------
    fig : matplotlib.figure.Figure or None
    """
    import matplotlib.pyplot as _plt
    import matplotlib.dates as mdates
    import matplotlib.patches as mpatches
    import numpy as _np

    if modis_df is None and era5_df is None:
        return None

    # ── colour scheme ─────────────────────────────────────────────────────────
    DAY_COL      = '#d73027'    # red-orange — day
    DAY_FILL     = '#fdae61'    # light orange fill
    NIGHT_COL    = '#4575b4'    # blue — night
    NIGHT_FILL   = '#abd9e9'    # light blue fill
    SEL_DAY_COL  = '#a50026'    # dark red — selected day event bracket
    SEL_NGT_COL  = '#313695'    # dark blue — selected night event bracket
    PERSIST_ALPHA = 0.12        # background shading for any persistent event

    _TIER_COLORS = {'EXCELLENT': '#1a9850', 'GOOD': '#f77f00', 'FAIR': '#999999'}

    fig, axes = _plt.subplots(2, 1, figsize=figsize, sharex=True,
                               gridspec_kw={'hspace': 0.12})

    def _draw_panel(ax, df, dataset_label, audit_d, audit_n, ds_type):
        """Render one panel (MODIS or ERA5)."""
        if df is None:
            ax.text(0.5, 0.5, f'No {dataset_label} data', transform=ax.transAxes,
                    ha='center', va='center', fontsize=12, color='grey')
            ax.set_ylabel(f'{dataset_label}\nLST (°C)')
            return

        df = df.copy()
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')

        # ── day range + line ──────────────────────────────────────────────────
        if 'day_lst_min' in df.columns and 'day_lst_max' in df.columns:
            ax.fill_between(df['date'], df['day_lst_min'], df['day_lst_max'],
                            color=DAY_FILL, alpha=0.35, linewidth=0, label='Day range')
        if 'day_lst_median' in df.columns:
            ax.plot(df['date'], df['day_lst_median'],
                    color=DAY_COL, linewidth=1.2, label='Day LST (median)', zorder=3)

        # ── night range + line ────────────────────────────────────────────────
        if 'night_lst_min' in df.columns and 'night_lst_max' in df.columns:
            ax.fill_between(df['date'], df['night_lst_min'], df['night_lst_max'],
                            color=NIGHT_FILL, alpha=0.35, linewidth=0, label='Night range')
        if 'night_lst_median' in df.columns:
            ax.plot(df['date'], df['night_lst_median'],
                    color=NIGHT_COL, linewidth=1.2, label='Night LST (median)', zorder=3)

        # ── P90 thresholds ────────────────────────────────────────────────────
        thresholds = {**audit_d.get('thresholds', {}), **audit_n.get('thresholds', {})}
        key_day   = f'{ds_type}_p90_celsius'   # same key used in build_event_json
        key_night = f'{ds_type}_p90_celsius'   # both audits use the same key name
        t_day   = audit_d.get('thresholds', {}).get(key_day)
        t_night = audit_n.get('thresholds', {}).get(key_night)

        if t_day is not None:
            ax.axhline(t_day, color=DAY_COL, linestyle='--', linewidth=1.0,
                       alpha=0.7, label=f'Day P90 = {t_day:.1f}°C', zorder=4)
        if t_night is not None:
            ax.axhline(t_night, color=NIGHT_COL, linestyle='--', linewidth=1.0,
                       alpha=0.7, label=f'Night P90 = {t_night:.1f}°C', zorder=4)

        # ── mark individual hot days (dots) ───────────────────────────────────
        if 'day_lst_median' in df.columns and t_day is not None:
            hot_d = df[df['day_lst_median'] >= t_day]
            ax.scatter(hot_d['date'], hot_d['day_lst_median'],
                       color=DAY_COL, s=18, zorder=5, alpha=0.6)
        if 'night_lst_median' in df.columns and t_night is not None:
            hot_n = df[df['night_lst_median'] >= t_night]
            ax.scatter(hot_n['date'], hot_n['night_lst_median'],
                       color=NIGHT_COL, s=18, zorder=5, alpha=0.6)

        # ── grey shading for every persistent event ───────────────────────────
        all_events = (
            audit_d.get('era5_persistent_events' if ds_type == 'era5' else 'modis_persistent_events', []) +
            audit_n.get('era5_persistent_events' if ds_type == 'era5' else 'modis_persistent_events', [])
        )
        shaded_windows = set()
        for evt in all_events:
            key = (evt.get('start_date'), evt.get('end_date'))
            if key in shaded_windows:
                continue
            shaded_windows.add(key)
            try:
                s = pd.to_datetime(evt['start_date'])
                e = pd.to_datetime(evt['end_date']) + pd.Timedelta(days=1)
                ax.axvspan(s, e, color='grey', alpha=PERSIST_ALPHA, linewidth=0, zorder=1)
            except Exception:
                pass

        # ── bracket helper ────────────────────────────────────────────────────
        y_min, y_max = ax.get_ylim()
        _bracket_gap = (y_max - y_min) * 0.08   # space below threshold line

        def _draw_bracket(start_str, end_str, label, color, above_y, bar_frac=0.02):
            try:
                s = pd.to_datetime(start_str)
                e = pd.to_datetime(end_str)
            except Exception:
                return
            bh   = (y_max - y_min) * bar_frac
            brak = above_y - _bracket_gap
            # horizontal bar
            ax.plot([s, e], [brak, brak], color=color, linewidth=2.5,
                    solid_capstyle='butt', zorder=8)
            # end ticks
            ax.plot([s, s], [brak - bh, brak + bh], color=color, linewidth=2.5, zorder=9)
            ax.plot([e, e], [brak - bh, brak + bh], color=color, linewidth=2.5, zorder=9)
            mid = s + (e - s) / 2
            ax.text(mid, brak + bh * 1.5, label,
                    ha='center', va='bottom', fontsize=7.5, fontweight='bold',
                    color=color, zorder=10)

        # ── selected event brackets (day and night) ───────────────────────────
        sel_d = audit_d.get('selected_event')
        sel_n = audit_n.get('selected_event')

        if sel_d and t_day is not None:
            tier_d = sel_d.get('tier', 'FAIR')
            _draw_bracket(sel_d['start_date'], sel_d['end_date'],
                          f"SEL-Day [{tier_d}]", SEL_DAY_COL, t_day)

        if sel_n and t_night is not None:
            tier_n = sel_n.get('tier', 'FAIR')
            _draw_bracket(sel_n['start_date'], sel_n['end_date'],
                          f"SEL-Night [{tier_n}]", SEL_NGT_COL, t_night)

        # ── axes formatting ───────────────────────────────────────────────────
        ax.set_ylabel(f'{dataset_label}\nLST (°C)', fontsize=9)
        ax.tick_params(axis='y', labelsize=8)
        ax.grid(axis='y', linestyle=':', linewidth=0.5, alpha=0.5)
        ax.legend(loc='upper right', fontsize=7, ncol=2, framealpha=0.88,
                  handlelength=1.2, columnspacing=0.8,
                  bbox_to_anchor=(0.99, 0.99), borderaxespad=0)

    # ── draw both panels ─────────────────────────────────────────────────────
    _draw_panel(axes[0], modis_df, 'MODIS', audit_day, audit_night, 'modis')
    _draw_panel(axes[1], era5_df,  'ERA5-Land', audit_day, audit_night, 'era5')

    # ── x-axis (shared) ───────────────────────────────────────────────────────
    axes[1].xaxis.set_major_locator(mdates.MonthLocator())
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter('%b'))
    axes[1].tick_params(axis='x', labelsize=8)

    # ── title ─────────────────────────────────────────────────────────────────
    fig.suptitle(
        f'{city_name}  —  Daily Urban-Core LST  ({study_year})\n'
        'Dashed = P90 threshold  |  Grey shade = persistent hot event  |  '
        'Bracket = selected event for SEVIRI',
        fontsize=9, y=0.99,
    )

    fig.tight_layout(rect=[0, 0, 1, 0.97])

    if output_path is not None:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(output_path), bbox_inches='tight',
                    facecolor='white', dpi=dpi)

    if show_inline:
        _plt.show()
    else:
        if output_path is not None:
            _plt.close(fig)

    return fig


def create_cluster_event_frequency_chart(
    cluster_event_summary,
    city_event_records: dict,
    cluster_lookup: dict,
    period: str = 'day',
    output_path=None,
    figsize=None,
    dpi: int = 300,
    cluster_fmt: str = 'C{:02d}',
    ax=None,
    show_legend: bool = True,
    title=None,
):
    """
    Grouped barplot: number of ERA5 persistent events per city, grouped by
    cluster, colour-coded by tier of the selected event.

    Parameters
    ----------
    cluster_event_summary : pd.DataFrame
        Output of ``daily_analysis_utils.aggregate_cluster_events``.
    city_event_records : dict
        ``{city: audit_dict}`` — one audit per city for the given period.
    cluster_lookup : dict
        ``{city: cluster_int}``.
    period : str
        'day' or 'night' (for the axis title).
    output_path : str or Path or None
    figsize : tuple or None
        Auto-scaled from number of cities if None.
    dpi : int
    cluster_fmt : str
        Cluster code under each city name, formatted with the cluster number.
    ax : matplotlib.axes.Axes or None
        Draw into this panel of an existing figure (its layout is the caller's).
    show_legend : bool
        False leaves out the tier legend (e.g. when the caller draws one for several panels).
    title : str or None
        The panel title; None gives the default two-line title.

    Returns
    -------
    fig : matplotlib.figure.Figure
    """
    import matplotlib.pyplot as _plt
    import matplotlib.patches as mpatches

    _TIER_COLORS = {'EXCELLENT': '#1a9850', 'GOOD': '#f77f00',
                    'FAIR': '#999999', None: '#cccccc'}
    _TIER_ORDER  = ['EXCELLENT', 'GOOD', 'FAIR']

    # Build per-city rows: city, cluster, n_events, n_days, tier_of_selected
    rows = []
    for city, cnum in sorted(cluster_lookup.items()):
        rec = city_event_records.get(city)
        if rec is None:
            continue
        n_events = len(rec.get('era5_persistent_events', []))
        sel      = rec.get('selected_event')
        tier     = sel.get('tier') if sel else None
        dur      = sel.get('duration', 0) if sel else 0
        rows.append({'city': city, 'cluster': int(cnum),
                     'n_events': n_events, 'duration': dur, 'tier': tier})

    if not rows:
        return None

    import pandas as _pd
    df_plot = _pd.DataFrame(rows).sort_values(['cluster', 'city'])
    cities  = df_plot['city'].tolist()
    n       = len(cities)

    if figsize is None:
        figsize = (max(8, n * 0.45), 5)

    own = ax is None
    if own:
        fig, ax = _plt.subplots(figsize=figsize)
    else:
        fig = ax.figure

    bar_colors = [_TIER_COLORS.get(t, '#cccccc') for t in df_plot['tier']]
    bars = ax.bar(range(n), df_plot['n_events'], color=bar_colors,
                  edgecolor='white', linewidth=0.5)

    # Label each bar with duration of selected event
    for i, (bar, row) in enumerate(zip(bars, df_plot.itertuples())):
        if row.duration > 0:
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 0.1,
                    f'{row.duration}d', ha='center', va='bottom',
                    fontsize=6.5, color='#333333')

    # ── x-axis city labels with cluster numbers ───────────────────────────────
    x_labels = [f"{r['city']}\n[{cluster_fmt.format(r['cluster'])}]" for _, r in df_plot.iterrows()]
    ax.set_xticks(range(n))
    ax.set_xticklabels(x_labels, fontsize=7, rotation=45, ha='right')

    # ── cluster boundary lines ────────────────────────────────────────────────
    prev_cl = None
    for i, cl in enumerate(df_plot['cluster']):
        if prev_cl is not None and cl != prev_cl:
            ax.axvline(i - 0.5, color='#444444', linewidth=0.8, linestyle=':')
        prev_cl = cl

    # ── legend ───────────────────────────────────────────────────────────────
    patches = [mpatches.Patch(color=_TIER_COLORS[t], label=t) for t in _TIER_ORDER]
    if show_legend:
        ax.legend(handles=patches, title='Selected event tier',
                  loc='upper right', fontsize=8, title_fontsize=8)

    ax.set_ylabel('ERA5 persistent hot events (count)', fontsize=9)
    ax.set_xlabel('City [Cluster]', fontsize=9)
    ax.set_title(
        title if title is not None else
        f'ERA5 Persistent Hot-Event Count per City — {period.capitalize()}\n'
        'Bar colour = tier of selected SEVIRI event  |  Label = selected duration (days)',
        fontsize=9,
    )
    ax.yaxis.set_major_locator(_plt.MaxNLocator(integer=True))
    ax.grid(axis='y', linestyle=':', linewidth=0.5, alpha=0.5)

    if own:
        fig.tight_layout()

    if output_path is not None:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(output_path), bbox_inches='tight',
                    facecolor='white', dpi=dpi)
        _plt.close(fig)

    return fig


def create_seviri_era5_scatter(
    day_rows: list,
    night_rows: list,
    zone: str = 'urban_core',
    output_dir=None,
    output_stem: str = 'SEVIRI_vs_ERA5_scatter_combined',
    figsize=(11.69, 5.85),
    dpi: int = 300,
    tier_title: str = 'MODIS tier',
):
    """
    Combined day + night scatter: SEVIRI LST vs ERA5-Land LST (event window).

    Two panels side-by-side (left = Day, right = Night).  Each point = one city.
    Colour = MODIS-tier of the selected event.  1:1 line + OLS regression.
    Saves PDF + SVG.

    Parameters
    ----------
    day_rows, night_rows : list of dict
        Each dict: 'city', 'era5_mean', 'seviri_mean', 'tier' (optional).
    zone : str
        Zone label for axis titles ('urban_core', 'bra', etc.).
    output_dir : str or Path or None
    output_stem : str
    figsize : tuple  — half-A4 landscape by default
    dpi : int
    tier_title : str
        Title of the tier legend.

    Returns
    -------
    fig : matplotlib.figure.Figure or None
    """
    import matplotlib.pyplot as _plt
    import matplotlib.patches as _mpatches
    import numpy as _np

    _TIER_COLORS = {
        'EXCELLENT': '#1a9850',
        'GOOD':      '#f77f00',
        'FAIR':      '#999999',
        None:        '#cccccc',
    }

    all_rows = {'day': day_rows or [], 'night': night_rows or []}
    panels = [
        (p, [r for r in all_rows[p]
             if r.get('era5_mean') is not None and r.get('seviri_mean') is not None])
        for p in ('day', 'night')
    ]
    panels = [(p, rows) for p, rows in panels if rows]

    if not panels:
        return None

    n_panels = len(panels)
    fig, axes = _plt.subplots(1, n_panels, figsize=figsize, squeeze=False)

    zone_label = zone.replace('_', ' ').title()
    all_tiers_seen: set = set()

    for col, (period, rows) in enumerate(panels):
        ax = axes[0, col]
        era5_vals   = _np.array([r['era5_mean']   for r in rows])
        seviri_vals = _np.array([r['seviri_mean'] for r in rows])
        tiers       = [r.get('tier') for r in rows]
        cities      = [r['city'] for r in rows]
        colors      = [_TIER_COLORS.get(t, '#cccccc') for t in tiers]
        all_tiers_seen.update(tiers)

        ax.scatter(era5_vals, seviri_vals, c=colors, s=55,
                   edgecolors='white', linewidths=0.5, zorder=3)

        lims = [min(era5_vals.min(), seviri_vals.min()) - 1,
                max(era5_vals.max(), seviri_vals.max()) + 1]
        ax.plot(lims, lims, 'k--', linewidth=0.8, label='1:1', zorder=2)

        if len(era5_vals) >= 2:
            m, b = _np.polyfit(era5_vals, seviri_vals, 1)
            x_fit = _np.linspace(lims[0], lims[1], 100)
            ax.plot(x_fit, m * x_fit + b, color='#d73027', linewidth=1.2,
                    label=f'Fit: y={m:.2f}x+{b:.1f}', zorder=2)
            resid  = seviri_vals - (m * era5_vals + b)
            ss_res = (resid ** 2).sum()
            ss_tot = ((seviri_vals - seviri_vals.mean()) ** 2).sum()
            r2     = 1 - ss_res / ss_tot if ss_tot > 0 else float('nan')
            ax.text(0.04, 0.96, f'r² = {r2:.3f}   n = {len(rows)}',
                    transform=ax.transAxes, fontsize=7.5, va='top',
                    bbox=dict(boxstyle='round,pad=0.25', fc='white', alpha=0.8))

        for vx, vy, city in zip(era5_vals, seviri_vals, cities):
            ax.annotate(city, (vx, vy), fontsize=5,
                        xytext=(3, 3), textcoords='offset points', color='#444444')

        ax.set_xlim(lims)
        ax.set_ylim(lims)
        ax.set_aspect('equal')
        ax.grid(linestyle=':', linewidth=0.4, alpha=0.45)
        ax.set_xlabel('ERA5-Land LST (°C)', fontsize=9)
        ax.set_ylabel('SEVIRI LST (°C)', fontsize=9)
        ax.set_title(
            f'{"Daytime" if period == "day" else "Nighttime"} | {zone_label}',
            fontsize=10, fontweight='bold',
        )
        ax.legend(fontsize=7, loc='lower right')

    tier_order = [t for t in ('EXCELLENT', 'GOOD', 'FAIR', None) if t in all_tiers_seen]
    tier_handles = [
        _mpatches.Patch(color=_TIER_COLORS.get(t, '#cccccc'), label=t or 'No event')
        for t in tier_order
    ]
    if tier_handles:
        fig.legend(handles=tier_handles, title=tier_title,
                   fontsize=7, title_fontsize=7.5,
                   loc='lower center', ncol=len(tier_handles),
                   bbox_to_anchor=(0.5, -0.01))

    fig.suptitle(
        'SEVIRI vs ERA5-Land LST — Event-Window Comparison\n'
        '(one point per city; event-window mean)',
        fontsize=10, y=1.01,
    )
    fig.tight_layout()

    if output_dir is not None:
        from pathlib import Path as _Path
        _Path(output_dir).mkdir(parents=True, exist_ok=True)
        for ext in ('svg', 'pdf'):
            fig.savefig(
                str(_Path(output_dir) / f'{output_stem}.{ext}'),
                format=ext, bbox_inches='tight', facecolor='white', dpi=dpi,
            )
        _plt.close(fig)

    return fig


def create_era5_modis_hexbin(
    paired_data: dict,
    title: str = 'ERA5-Land vs MODIS Daily LST',
    output_path=None,
    figsize=(11, 5),
    dpi: int = 300,
    gridsize: int = 35,
    show_inline: bool = False,
    bias_label: str = 'Bias',
):
    """
    Two-panel hexbin scatter plot comparing ERA5-Land vs MODIS daily LST.

    Left panel = Day, Right panel = Night.  Each hexbin cell is coloured by
    the number of co-located (ERA5, MODIS) observation pairs it contains.
    A 1:1 reference line and an OLS regression line are drawn on both panels.
    Metric annotations (r², bias, RMSE, n) appear in the top-left corner.

    This function works for both city-level (one city's paired observations)
    and cluster-level (pooled observations from all cities in the cluster).

    Parameters
    ----------
    paired_data : dict
        Keys ``'day'`` and/or ``'night'``, each containing a dict with:
        - ``'era5'``  : array-like of ERA5 LST values (°C)
        - ``'modis'`` : array-like of MODIS LST values (°C)
        - ``'metrics'``: dict with keys r, r2, bias, rmse, mae, n
          (output of ``daily_analysis_utils.compute_correlation_metrics``)
    title : str
        Figure suptitle.
    output_path : str or Path or None
        Save path for the SVG figure.
    figsize : tuple
        Figure size in inches (default half-A4 landscape).
    dpi : int
    gridsize : int
        Number of hexagons along each axis (higher = finer grid).
    show_inline : bool
        If True, call plt.show(); else close after saving.
    bias_label : str
        Label of the bias line in the metric box, e.g. 'Bias (ERA5-Land − MODIS)'.

    Returns
    -------
    fig : matplotlib.figure.Figure or None
    """
    import matplotlib.pyplot as _plt
    import matplotlib.colors as mcolors
    import numpy as _np

    periods_present = [p for p in ('day', 'night') if p in paired_data
                       and len(paired_data[p].get('era5', [])) > 1]
    if not periods_present:
        return None

    n_panels = len(periods_present)
    fig, axes = _plt.subplots(1, n_panels, figsize=figsize, squeeze=False)

    # Truncated colormaps: skip the near-white bottom 22 % of the stock maps
    # so that even a single-observation hexbin shows a visible dark golden colour.
    import numpy as _np_hb
    import matplotlib.cm as _mcm_hb
    from matplotlib.colors import LinearSegmentedColormap as _LSC_hb
    _day_cmap_hb   = _LSC_hb.from_list(
        'YlOrRd_dark', _mcm_hb.get_cmap('YlOrRd')(_np_hb.linspace(0.22, 1.0, 256)))
    _night_cmap_hb = _LSC_hb.from_list(
        'YlGnBu_dark', _mcm_hb.get_cmap('YlGnBu')(_np_hb.linspace(0.22, 1.0, 256)))
    _PERIOD_COLORS = {'day': _day_cmap_hb, 'night': _night_cmap_hb}
    _PERIOD_LABELS = {'day': 'Daytime', 'night': 'Nighttime'}

    for col, period in enumerate(periods_present):
        ax   = axes[0, col]
        data = paired_data[period]
        era5  = _np.array(data['era5'],  dtype=float)
        modis = _np.array(data['modis'], dtype=float)
        mask  = _np.isfinite(era5) & _np.isfinite(modis)
        era5, modis = era5[mask], modis[mask]

        if len(era5) < 2:
            ax.text(0.5, 0.5, 'Insufficient data', transform=ax.transAxes,
                    ha='center', va='center', color='grey')
            continue

        cmap  = _PERIOD_COLORS.get(period, 'viridis')
        hb    = ax.hexbin(era5, modis, gridsize=gridsize, cmap=cmap,
                          mincnt=1, linewidths=0.2)
        cb    = fig.colorbar(hb, ax=ax, shrink=0.85, pad=0.02)
        cb.set_label('Observation count', fontsize=7)
        cb.ax.tick_params(labelsize=6)

        # 1:1 line
        lims = [min(era5.min(), modis.min()) - 1,
                max(era5.max(), modis.max()) + 1]
        ax.plot(lims, lims, 'k--', linewidth=1.0, label='1:1', zorder=3)

        # OLS regression
        m, b = _np.polyfit(era5, modis, 1)
        x_fit = _np.linspace(lims[0], lims[1], 200)
        ax.plot(x_fit, m * x_fit + b, color='#e31a1c', linewidth=1.2,
                label=f'Fit (slope={m:.2f})', zorder=3)

        ax.set_xlim(lims); ax.set_ylim(lims)
        ax.set_aspect('equal')

        # Metrics annotation
        mets = data.get('metrics', {})
        r    = mets.get('r',    float('nan'))
        r2   = mets.get('r2',   float('nan'))
        bias = mets.get('bias', float('nan'))
        rmse = mets.get('rmse', float('nan'))
        n    = mets.get('n',    len(era5))
        _fmt = lambda v: f'{v:.3f}' if _np.isfinite(v) else 'N/A'
        ann  = (f"r = {_fmt(r)}\n"
                f"r² = {_fmt(r2)}\n"
                f"{bias_label} = {bias:+.2f}°C\n"
                f"RMSE = {_fmt(rmse)}°C\n"
                f"n = {n:,}")
        ax.text(0.03, 0.97, ann, transform=ax.transAxes,
                fontsize=7.5, va='top', family='monospace',
                bbox=dict(boxstyle='round,pad=0.3', fc='white', alpha=0.75))

        ax.set_xlabel('ERA5-Land LST (°C)', fontsize=9)
        ax.set_ylabel('MODIS LST (°C)',      fontsize=9)
        ax.set_title(_PERIOD_LABELS[period], fontsize=10, fontweight='bold')
        ax.tick_params(labelsize=8)
        ax.grid(linestyle=':', linewidth=0.4, alpha=0.4)
        ax.legend(fontsize=7, loc='lower right')

    fig.suptitle(title, fontsize=10, y=1.01)
    fig.tight_layout()

    if output_path is not None:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(output_path), bbox_inches='tight',
                    facecolor='white', dpi=dpi)

    if show_inline:
        _plt.show()
    elif output_path is not None:
        _plt.close(fig)

    return fig

    return fig_a, fig_m


def create_suhii_city_chart(
    df_seviri,
    cluster_lookup: dict,
    output_dir=None,
    output_stem: str = 'SEVIRI_SUHII_cities',
    figsize=(8.27, 11.69),
    dpi: int = 300,
    cl_legend_ncol: int = 3,
    axes=None,
    title: str = ('City-Level SEVIRI SUHII\n'
                  '(fill = cluster colour  |  sorted by daytime \u2193)'),
    show_national_box: bool = True,
    cl_label: str = 'Cl {}',
):
    """
    Publication-quality city-level SUHII chart (portrait A4).

    Two panels (Daytime left, Nighttime right).  Cities on Y-axis sorted by
    daytime SUHII descending.  Bar fill = Cluster25 colour.

    Parameters
    ----------
    df_seviri : pd.DataFrame
        Columns needed: 'city', 'period', 'suhii', 'note'.
        Only rows where note == 'ok' are plotted.
    cluster_lookup : dict
        city → Cluster25 integer.
    output_dir : str or Path or None
    output_stem : str
    figsize : tuple  — default portrait A4
    dpi : int
    axes : (ax_day, ax_night) or None
        Draw into axes the caller already made, instead of creating a figure. Nothing
        is saved and the figure is not laid out or closed, so the panel can be one part
        of a larger figure. Added for the SCS rebuild; default None is the old
        behaviour.
    title : str or None
        None removes the in-figure title.
    show_national_box : bool
        The national mean/range box in the lower left.
    cl_label : str
        Legend label for a cluster number, e.g. 'C{}' for "C13".

    Returns
    -------
    fig : matplotlib.figure.Figure or None
    """
    import matplotlib.pyplot as _plt
    import matplotlib.patches as _mpatches
    import numpy as _np

    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from config import CLUSTER25_COLORS as _CL_COL
    except Exception:
        _CL_COL = {}

    _FALLBACK_CLR = '#888888'

    _ok = df_seviri[df_seviri['note'] == 'ok'].copy()
    _ok = _ok.dropna(subset=['suhii'])
    if _ok.empty:
        print('  No valid SEVIRI SUHII data — download cities first.')
        return None

    _day_df   = _ok[_ok['period'] == 'day'].set_index('city')['suhii']
    _night_df = _ok[_ok['period'] == 'night'].set_index('city')['suhii']

    _all_cities = sorted(set(_day_df.index) | set(_night_df.index))
    _all_cities.sort(
        key=lambda c: (
            -float(_day_df[c])
            if (c in _day_df.index and _np.isfinite(float(_day_df[c])))
            else float('inf')
        )
    )

    n = len(_all_cities)
    if n == 0:
        return None

    y_pos = _np.arange(n)
    bar_h = 0.55

    # sharex=True enforces a uniform x-axis (SUHII) scale across both panels
    _embedded = axes is not None
    if _embedded:
        axes = list(axes)
        fig = axes[0].figure
    else:
        fig, axes = _plt.subplots(1, 2, figsize=figsize, sharey=True, sharex=True,
                                  gridspec_kw={'wspace': 0.06})

    for period, ax in [('day', axes[0]), ('night', axes[1])]:
        _pdata = _day_df if period == 'day' else _night_df
        for i, city in enumerate(_all_cities):
            if city not in _pdata.index:
                continue
            val = float(_pdata[city])
            if not _np.isfinite(val):
                continue
            cl_num = cluster_lookup.get(city)
            fill   = (_CL_COL.get(cl_num, _FALLBACK_CLR)
                      if cl_num is not None else _FALLBACK_CLR)
            ax.barh(y_pos[i], val, bar_h,
                    color=fill, edgecolor='#333333', linewidth=0.3, zorder=3)

        ax.axvline(0, color='#555555', linewidth=0.8, zorder=2)
        ax.grid(axis='x', linestyle=':', linewidth=0.35, alpha=0.45, zorder=0)
        ax.set_xlabel('SUHII (°C)', fontsize=9)
        ax.set_title(f'{"Daytime" if period == "day" else "Nighttime"}',
                     fontsize=10, fontweight='bold')
        ax.tick_params(labelsize=7)

    axes[0].set_yticks(y_pos)
    axes[0].set_yticklabels(_all_cities, fontsize=6)
    axes[0].invert_yaxis()
    axes[1].tick_params(left=False, labelleft=False)

    _used_cl = sorted({cluster_lookup.get(c) for c in _all_cities
                       if cluster_lookup.get(c) is not None})
    _cl_handles = [
        _mpatches.Patch(facecolor=_CL_COL.get(n, _FALLBACK_CLR), label=cl_label.format(n))
        for n in _used_cl
    ]

    if _embedded:
        axes[1].legend(handles=_cl_handles, title='Cluster (fill)', title_fontsize=6.5,
                       fontsize=6, loc='lower right', ncol=cl_legend_ncol,
                       framealpha=0.9)
    else:
        fig.legend(handles=_cl_handles,
                   title='Cluster (fill)', title_fontsize=7, fontsize=6.5,
                   loc='lower right', bbox_to_anchor=(0.98, 0.01),
                   ncol=cl_legend_ncol, framealpha=0.9)

    _d_vals = _day_df.dropna()
    _n_vals = _night_df.dropna()
    if show_national_box and (len(_d_vals) > 0 or len(_n_vals) > 0):
        _nat_txt = (
            f"National  Day: μ={_d_vals.mean():.2f}°C  "
            f"[{_d_vals.min():.2f}–{_d_vals.max():.2f}]\n"
            f"          Night: μ={_n_vals.mean():.2f}°C  "
            f"[{_n_vals.min():.2f}–{_n_vals.max():.2f}]"
        )
        if _embedded:
            axes[0].text(0.02, 0.012, _nat_txt, transform=axes[0].transAxes,
                         ha='left', va='bottom', fontsize=6.2,
                         bbox=dict(boxstyle='round,pad=0.35', fc='#f7f7f7', alpha=0.9))
        else:
            fig.text(0.02, 0.01, _nat_txt, ha='left', va='bottom', fontsize=7,
                     bbox=dict(boxstyle='round,pad=0.4', fc='#f7f7f7', alpha=0.9))

    if _embedded:
        return fig

    if title:
        fig.suptitle(title, fontsize=10, y=0.998)
    fig.tight_layout(rect=[0, 0.08, 1, 0.975])

    if output_dir is not None:
        from pathlib import Path as _Path
        _Path(output_dir).mkdir(parents=True, exist_ok=True)
        for ext in ('svg', 'pdf'):
            fig.savefig(
                str(_Path(output_dir) / f'{output_stem}.{ext}'),
                format=ext, bbox_inches='tight', facecolor='white', dpi=dpi,
            )
        _plt.close(fig)

    return fig


def create_heat_event_stacked_bar(
    stats_df,
    level: str = 'city',
    output_dir=None,
    output_stem: str = None,
    figsize=None,
    dpi: int = 300,
):
    """
    Combined ERA5-Land + MODIS hot-day count chart (horizontal bars).

    Two panels side-by-side: left = ERA5-Land, right = MODIS.
    Day (red shades) and Night (blue shades) bars sit above/below each entity.
    'cluster' level → A4 landscape (11.69" × 8.27").
    'city'    level → A4 portrait  (8.27" × 11.69").
    Saved as PDF + SVG.

    Parameters
    ----------
    stats_df : pd.DataFrame
        Columns: entity-id col, 'dataset', 'period',
        'n_hot_days', 'total_persistent_days'.
    level : str
        'city' or 'cluster'.
    output_dir : str or Path or None
    output_stem : str or None  — defaults to 'hot_day_counts_{level}'
    figsize : tuple or None
    dpi : int

    Returns
    -------
    fig : matplotlib.figure.Figure or None
    """
    import matplotlib.pyplot as _plt
    import numpy as _np
    import matplotlib.patches as _mpat

    id_col = 'city' if level == 'city' else 'cluster_num'
    if figsize is None:
        figsize = (11.69, 8.27) if level == 'cluster' else (8.27, 11.69)
    if output_stem is None:
        output_stem = f'hot_day_counts_{level}'

    DAY_PERSIST = '#a50026'
    DAY_ISOL    = '#f4a582'
    NGT_PERSIST = '#313695'
    NGT_ISOL    = '#92c5de'
    bar_h = 0.28

    _df = stats_df.copy()
    _df['isolated_days'] = _np.maximum(
        _df['n_hot_days'].fillna(0) - _df['total_persistent_days'].fillna(0), 0
    ).astype(int)
    _df['persist_days'] = _df['total_persistent_days'].fillna(0).astype(int)

    all_entities = sorted(
        _df[id_col].dropna().unique(),
        key=lambda x: (int(x) if str(x).isdigit() else 0, str(x)),
    )
    n = len(all_entities)
    if n == 0:
        return None

    y     = _np.arange(n)
    y_day = y - bar_h * 0.6
    y_ngt = y + bar_h * 0.6

    fig, axes = _plt.subplots(1, 2, figsize=figsize, sharey=True,
                               gridspec_kw={'wspace': 0.06})

    def _get(sub, entity, period, col):
        r = sub[(sub[id_col] == entity) & (sub['period'] == period)]
        return int(r[col].iloc[0]) if not r.empty else 0

    for col_i, (ds, ds_label) in enumerate([('ERA5-Land', 'ERA5-Land'), ('MODIS', 'MODIS')]):
        ax  = axes[col_i]
        sub = _df[_df['dataset'] == ds]

        for i, ent in enumerate(all_entities):
            dp  = _get(sub, ent, 'day',   'persist_days')
            di  = _get(sub, ent, 'day',   'isolated_days')
            np_ = _get(sub, ent, 'night', 'persist_days')
            ni  = _get(sub, ent, 'night', 'isolated_days')

            ax.barh(y_day[i], dp,  bar_h, color=DAY_PERSIST, zorder=3)
            ax.barh(y_day[i], di,  bar_h, left=dp,  color=DAY_ISOL,    zorder=3)
            ax.barh(y_ngt[i], np_, bar_h, color=NGT_PERSIST, zorder=3)
            ax.barh(y_ngt[i], ni,  bar_h, left=np_, color=NGT_ISOL,    zorder=3)

        ax.set_title(ds_label, fontsize=10, fontweight='bold')
        ax.set_xlabel('Hot-day count (days)', fontsize=8.5)
        ax.grid(axis='x', linestyle=':', linewidth=0.4, alpha=0.5, zorder=0)
        ax.axvline(0, color='#888888', linewidth=0.5)
        ax.tick_params(labelsize=7.5)

    axes[0].set_yticks(y)
    axes[0].set_yticklabels(
        [str(e) for e in all_entities],
        fontsize=6.5 if level == 'city' else 8,
    )
    axes[0].invert_yaxis()
    axes[0].set_ylabel(id_col.replace('_', ' ').title(), fontsize=9)
    axes[1].tick_params(left=False, labelleft=False)

    _handles = [
        _mpat.Patch(facecolor=DAY_PERSIST, label='Day — persistent'),
        _mpat.Patch(facecolor=DAY_ISOL,    label='Day — isolated'),
        _mpat.Patch(facecolor=NGT_PERSIST, label='Night — persistent'),
        _mpat.Patch(facecolor=NGT_ISOL,    label='Night — isolated'),
    ]
    fig.legend(handles=_handles, loc='lower center', ncol=4, fontsize=7.5,
               framealpha=0.9, bbox_to_anchor=(0.5, 0.0))

    fig.suptitle(
        f'Hot-Day Counts — {level.title()} Level  '
        '|  Dark = persistent event days  |  Light = isolated hot days',
        fontsize=10, y=0.995,
    )
    fig.tight_layout(rect=[0, 0.06, 1, 0.97])

    if output_dir is not None:
        from pathlib import Path as _Path
        _Path(output_dir).mkdir(parents=True, exist_ok=True)
        for ext in ('svg', 'pdf'):
            fig.savefig(
                str(_Path(output_dir) / f'{output_stem}.{ext}'),
                format=ext, bbox_inches='tight', facecolor='white', dpi=dpi,
            )
        _plt.close(fig)

    return fig

    return fig





# === PUBLICATION FIGURES ===

_A4_W  = 8.27
_A4_H  = 11.69
_HALF_H = _A4_H / 2


def create_publication_nigeria_overview(
    aoi_dict: Dict,
    cities_csv_path,
    landscape_path,
    nigeria_path,
    cluster25_colors: Dict,
    active_cluster_ids: list = None,
    study_year: int = 2024,
    pop_override: Dict = None,
    save_path=None,
    dpi: int = 300,
    figsize: tuple = (8.27, 11.69),
    pop_scale: float = 0.6,
    cluster_labels: Dict = None,
    legend_cluster_ids: list = None,
    highlight_cluster_ids: set = None,
    absorbed_points: list = None,
    pop_legend_values: list = None,
    title: str = 'Study Cities \u2014 Nigeria Cluster25 Landscape Classification',
    legend_title: str = 'Legend',
    cluster_legend_heading: str = 'Landscape Clusters (Cl25):',
    legend_ncol: int = 2,
    legend_fontsize: float = 7,
    legend_outside: bool = False,
    legend_below: bool = False,
    label_min_pop: float = None,
    label_min_pop_bbox: tuple = None,
    unlabelled_cities: list = None,
    city_legend_label: str = 'Study city',
) -> plt.Figure:
    """A4 publication Nigeria overview: Cluster25 fills + proportional circles + cluster legend.

    The optional arguments were added for the SCS rebuild and all default to the original
    behaviour, so existing callers (NB01) render exactly as before:

    cluster_labels         {cluster_id: text} for the legend, instead of 'Cluster {id}'
    legend_cluster_ids     which clusters the legend lists (default: the active ones)
    highlight_cluster_ids  those drawn with a dark outline and a marker in the legend
    absorbed_points        [(lon, lat, name), ...] drawn as a cross on a white halo
    pop_legend_values      [(persons, label), ...] for the graduated key, instead of
                           fractions of the largest city
    title                  None removes the in-figure title
    legend_outside         places the legend beside the map instead of inside it, for a
                           legend too long to sit over the country without covering it
    legend_below           places it under the map instead, which keeps the map width
    label_min_pop          inside label_min_pop_bbox, name only cities at or above
                           this population; used where names would overlap
    label_min_pop_bbox     (lon_min, lat_min, lon_max, lat_max) the rule applies in
    unlabelled_cities      further cities drawn with the same symbol, sized from the
                           cities table, but not named
    city_legend_label      the legend entry for the city symbol
    """
    import matplotlib.patches as mpatches

    nigeria_gdf   = gpd.read_file(nigeria_path).to_crs('EPSG:4326')
    landscape_gdf = gpd.read_file(landscape_path).to_crs('EPSG:4326')
    landscape_gdf['geometry'] = landscape_gdf.geometry.buffer(0)

    _p = Path(cities_csv_path)
    if _p.suffix.lower() in ('.xlsx', '.xls'):
        _df = pd.read_excel(cities_csv_path, sheet_name='Data')
    else:
        _df = pd.read_csv(cities_csv_path, thousands=',')
    if 'City_Name' in _df.columns:
        _df = _df.rename(columns={'City_Name': 'Urban Agglomeration',
                                   'PWCent_Latitude': 'Latitude',
                                   'PWCent_Longitude': 'Longitude'})
        _df['Urban Agglomeration'] = _df['Urban Agglomeration'].str.strip()

    yr = str(study_year)
    pop_lookup, coord_lookup = {}, {}
    for _, row in _df.iterrows():
        name = row['Urban Agglomeration']
        if pd.notna(name) and yr in _df.columns:
            pv = row[yr]
            pop_lookup[name]   = float(pv) * 1_000 if pd.notna(pv) else 0
            coord_lookup[name] = (float(row['Longitude']), float(row['Latitude']))
    if pop_override:
        for c, pv in pop_override.items():
            pop_lookup[c] = pv

    cities = sorted(aoi_dict.keys())
    land_merged = landscape_gdf.dissolve(by='Cluster25', as_index=False)
    land_merged['color'] = land_merged['Cluster25'].map(cluster25_colors)

    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_facecolor('white')
    land_merged.plot(ax=ax, color=land_merged['color'],
                     edgecolor='white', linewidth=0.2, alpha=0.6, zorder=1)
    nigeria_gdf.plot(ax=ax, facecolor='none', edgecolor='#333333',
                     linewidth=1.5, zorder=2)

    _unl = sorted(set(unlabelled_cities or []) - set(cities))
    max_pop = max((pop_lookup.get(c, 0) for c in cities + _unl), default=1) or 1
    label_texts, label_x, label_y = [], [], []

    def _fmt(p):
        if p >= 1_000_000: return f'{p/1_000_000:.1f}M'
        if p >= 1_000:     return f'{p/1_000:.0f}k'
        return f'{p:.0f}'

    for city in cities + _unl:
        lon, lat = coord_lookup.get(city, (None, None))
        if lon is None:
            continue
        pop    = pop_lookup.get(city, 0)
        radius = pop_scale * np.sqrt(pop / max_pop) if pop > 0 else 0
        if radius > 0:
            ax.add_patch(plt.Circle((lon, lat), radius, facecolor='#555555',
                                    edgecolor='white', linewidth=0.8, alpha=0.75, zorder=4))
        ax.plot(lon, lat, 'ko', markersize=3, zorder=6)
        if city in _unl:
            continue
        # Where names collide, name only the larger cities inside the given box. The
        # city itself is still drawn; only its label is dropped, and every name is in
        # Supp. Fig. S2.
        if label_min_pop and label_min_pop_bbox:
            _x0, _y0, _x1, _y1 = label_min_pop_bbox
            if _x0 <= lon <= _x1 and _y0 <= lat <= _y1 and pop < label_min_pop:
                continue
        txt = ax.text(lon, lat - radius - 0.12, f'{city}\n({_fmt(pop)})',
                      ha='center', va='top', fontsize=6.5, fontweight='bold',
                      color='#111', zorder=7, linespacing=0.85)
        label_texts.append(txt); label_x.append(lon); label_y.append(lat - radius - 0.12)

    try:
        from adjustText import adjust_text
        # Keep labels close to their circles: small forces, tight expansion and a
        # short maximum displacement so a label never drifts far from its city.
        adjust_text(label_texts, x=label_x, y=label_y, ax=ax,
                    force_text=(0.12, 0.25), force_points=(0.10, 0.18),
                    expand_text=(1.02, 1.05), expand_points=(1.02, 1.05),
                    arrowprops=dict(arrowstyle='-', color='#999', lw=0.4,
                                    shrinkA=3, shrinkB=2),
                    ensure_inside_axes=True, max_move=0.4)
    except ImportError:
        pass

    # Candidate cities absorbed into a neighbour: a heavy cross on a white halo, so the
    # mark stays legible over any landscape-class colour.
    if absorbed_points:
        for _lon, _lat, _nm in absorbed_points:
            ax.plot(_lon, _lat, 'o', markersize=9, markerfacecolor='white',
                    markeredgecolor='none', alpha=0.95, zorder=7)
            ax.plot(_lon, _lat, 'x', markersize=6, markeredgewidth=2.0,
                    color='#B2182B', zorder=8)

    bounds = nigeria_gdf.total_bounds
    ax.set_xlim(bounds[0] - 0.5, bounds[2] + 0.5)
    ax.set_ylim(bounds[1] - 1.0, bounds[3] + 0.5)
    ax.set_aspect('equal')
    ax.grid(True, alpha=0.15, linestyle='--', linewidth=0.5, zorder=0)
    ax.set_xlabel('Longitude', fontsize=10); ax.set_ylabel('Latitude', fontsize=10)
    if title:
        ax.set_title(title, fontsize=13, fontweight='bold', pad=14)

    sc_cx = (bounds[0] + bounds[2]) / 2; sc_lat = bounds[1] - 0.7
    ax.plot([sc_cx - 0.45, sc_cx + 0.45], [sc_lat, sc_lat], 'k-', linewidth=3, zorder=8)
    for _xx in [sc_cx - 0.45, sc_cx + 0.45]:
        ax.plot([_xx, _xx], [sc_lat - 0.1, sc_lat + 0.1], 'k-', linewidth=2, zorder=8)
    ax.text(sc_cx, sc_lat + 0.15, '100 km', ha='center', va='bottom',
            fontsize=8, fontweight='bold', zorder=8)
    ax.annotate('N', xy=(0.96, 0.96), xytext=(0.96, 0.91), xycoords='axes fraction',
                fontsize=12, ha='center', fontweight='bold',
                arrowprops=dict(arrowstyle='->', lw=2, color='black'), zorder=10)

    _items = [
        plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='black',
                   markersize=5, label=city_legend_label),
        mpatches.Patch(facecolor='none', edgecolor='#333', linewidth=1.5,
                       label='National boundary'),
    ]
    if absorbed_points:
        _items.append(plt.Line2D([0], [0], marker='x', color='#B2182B', linestyle='none',
                                 markersize=6, markeredgewidth=2.0,
                                 label=f'Absorbed candidate ({len(absorbed_points)})'))
    _items += [
        mpatches.Patch(facecolor='none', edgecolor='none', label=''),
        mpatches.Patch(facecolor='none', edgecolor='none', label=cluster_legend_heading),
    ]
    if legend_cluster_ids is not None:
        _cids = list(legend_cluster_ids)
    elif active_cluster_ids:
        _cids = sorted(active_cluster_ids)
    else:
        _cids = sorted(int(x) for x in land_merged['Cluster25'].unique())
    _hi = set(int(x) for x in (highlight_cluster_ids or []))
    for cid in _cids:
        col = cluster25_colors.get(int(cid))
        if not col:
            continue
        _lbl = (cluster_labels or {}).get(int(cid), f'Cluster {cid}')
        _on = int(cid) in _hi
        _items.append(mpatches.Patch(facecolor=col,
                                     edgecolor='#333333' if _on else 'white',
                                     linewidth=1.1 if _on else 0.5,
                                     alpha=0.85 if _on else 0.6,
                                     label=_lbl))
    if legend_below:
        # The map is laid out before the legend exists, so a legend wider than the map
        # hangs below it rather than shrinking it: the map body keeps its size.
        fig.tight_layout()
        leg = ax.legend(handles=_items, loc='upper center', bbox_to_anchor=(0.5, -0.085),
                        fontsize=legend_fontsize, framealpha=1.0, edgecolor='#555',
                        title=legend_title, title_fontsize=9, ncol=legend_ncol,
                        borderpad=0.7, labelspacing=0.28, handlelength=1.3,
                        handletextpad=0.45, columnspacing=1.1)
    elif legend_outside:
        leg = ax.legend(handles=_items, loc='upper left', bbox_to_anchor=(1.015, 1.0),
                        fontsize=legend_fontsize, framealpha=1.0, edgecolor='#555',
                        title=legend_title, title_fontsize=9, ncol=legend_ncol,
                        borderpad=0.8, labelspacing=0.3, handlelength=1.3,
                        handletextpad=0.45)
    else:
        leg = ax.legend(handles=_items, loc='lower right', fontsize=legend_fontsize,
                        framealpha=0.93, edgecolor='#555', title=legend_title,
                        title_fontsize=9, ncol=legend_ncol,
                        borderpad=0.8, labelspacing=0.35, handlelength=1.2,
                        handletextpad=0.4)
    if not legend_below:
        fig.tight_layout()

    # ── Graduated proportional-circle key, drawn just above the legend (no frame) ──
    # Circles are in data coordinates (true circles under aspect='equal'); the anchor is
    # read back from the rendered legend box so the key always sits above the legend.
    from matplotlib.patches import Circle as _RefCircle
    fig.canvas.draw()
    if legend_outside or legend_below:
        # The legend is no longer over the map, so the key sits in the lower-right
        # corner of the map itself rather than being stacked above the legend.
        _cx, _by = ax.transData.inverted().transform(
            ax.transAxes.transform((0.88, 0.05)))
    else:
        _bb = leg.get_window_extent().transformed(ax.transAxes.inverted())
        _cx, _by = ax.transData.inverted().transform(
            ax.transAxes.transform(((_bb.x0 + _bb.x1) / 2, _bb.y1 + 0.012)))
    _r_big = pop_scale * np.sqrt(1.0)
    # Explicit bands let the key start at the 300,000 selection threshold rather than at
    # a fraction of the largest city.
    _bands = ([(float(_v), _lb) for _v, _lb in pop_legend_values] if pop_legend_values
              else [(max_pop * _fr, None) for _fr in (1.0, 0.4, 0.12)])
    for _v, _lb in sorted(_bands, key=lambda t: -t[0]):
        _fr = min(max(_v / max_pop, 1e-9), 1.0)
        _r = pop_scale * np.sqrt(_fr)
        ax.add_patch(_RefCircle((_cx, _by + _r), _r, fill=False, edgecolor='#555',
                                linewidth=0.9, zorder=9, clip_on=False))
        _top = _by + 2 * _r
        ax.plot([_cx - _r, _cx - _r_big - 0.12], [_top, _top], '-',
                color='#888', lw=0.5, zorder=9, clip_on=False)
        ax.text(_cx - _r_big - 0.16, _top, _lb if _lb else _fmt(_v), ha='right',
                va='center', fontsize=6.5, zorder=10, clip_on=False)
    ax.text(_cx, _by + 2 * _r_big + 0.06, 'Population', ha='center', va='bottom',
            fontsize=7.5, fontweight='bold', zorder=10, clip_on=False)

    if save_path:
        _sp = Path(save_path)
        fig.savefig(_sp.with_suffix('.svg'), format='svg', dpi=dpi,
                    bbox_inches='tight', facecolor='white')
        fig.savefig(_sp.with_suffix('.pdf'), format='pdf',
                    bbox_inches='tight', facecolor='white')
        print(f"   Saved: {_sp.stem}.svg + .pdf")
    return fig


def _draw_zone_panel(
    ax,
    aoi_gdf,
    cr_gdf=None,
    uc_gdf=None,
    bra_gdf=None,
    landscape_gdf=None,
    cluster25_colors=None,
    water_gdf=None,
    roads_gdf=None,
    places_gdf=None,
    label_buffer_km: float = 1.4,
) -> tuple:
    """
    Render three-zone layers on an existing axes.

    Layer style rules:
    - CR outline: thick (#333333, lw=2.0)
    - UC outline: red (#cc0000, lw=1.8)
    - BRA outline: very thin (#7a5c00, lw=0.4)
    - Water: fill only — edgecolor set equal to facecolor so any rendered edge
      is invisible regardless of backend antialiasing behaviour.
    - Roads: thin grey lines

    Returns (legend_handles, legend_labels).
    """
    from matplotlib.patches import Patch
    from matplotlib.lines   import Line2D

    _WATER_FC = '#4a9eca'   # water fill colour — reused for edge to suppress outlines

    def _prep(gdf):
        if gdf is None or gdf.empty:
            return None
        out = gdf.copy(); out['geometry'] = out.geometry.buffer(0)
        return out.to_crs('EPSG:4326')

    aoi_plot = _prep(aoi_gdf)
    cr_plot  = _prep(cr_gdf)
    bra_plot = _prep(bra_gdf)
    uc_plot  = _prep(uc_gdf)

    if aoi_plot is None:
        return [], []

    bounds = aoi_plot.total_bounds
    w = bounds[2] - bounds[0]; h = bounds[3] - bounds[1]
    ax.set_xlim(bounds[0] - w * 0.02, bounds[2] + w * 0.02)
    ax.set_ylim(bounds[1] - h * 0.02, bounds[3] + h * 0.02)

    leg_h, leg_l = [], []

    # ── CR fill ─────────────────────────────────────────────────────────────────
    if cr_plot is not None:
        cr_plot.plot(ax=ax, facecolor='#f0f0eb', edgecolor='none', linewidth=0,
                     alpha=0.30, zorder=1)
        leg_h.append(Patch(facecolor='#f0f0eb', edgecolor='#333333', linewidth=0.2, alpha=0.85))
        leg_l.append('City-Region (CR)')

    # ── Landscape cluster fills ─────────────────────────────────────────────────
    _cluster_labels = []
    if landscape_gdf is not None and cluster25_colors is not None:
        try:
            land = landscape_gdf.to_crs('EPSG:4326').copy()
            land['geometry'] = land.geometry.buffer(0)
            clip_geom = (aoi_plot.geometry.union_all()
                         if hasattr(aoi_plot.geometry, 'union_all')
                         else aoi_plot.geometry.unary_union)
            land_clip = gpd.clip(land, clip_geom)
            if not land_clip.empty:
                land_clip['_color'] = land_clip['Cluster25'].map(cluster25_colors)
                land_clip = land_clip[land_clip['_color'].notna()]
                if not land_clip.empty:
                    land_clip.plot(ax=ax, color=land_clip['_color'],
                                   edgecolor='none', linewidth=0, alpha=0.50, zorder=2)
                    land_clip = land_clip.copy()
                    land_clip['_area'] = land_clip.geometry.area
                    labeled = set()
                    for _, row in land_clip.sort_values('_area', ascending=False).iterrows():
                        cid = int(row['Cluster25'])
                        if cid in labeled or row.geometry.area < 0.003:
                            continue
                        c = row.geometry.centroid
                        if bounds[0] <= c.x <= bounds[2] and bounds[1] <= c.y <= bounds[3]:
                            _cluster_labels.append((c.x, c.y, f'C{cid}'))
                            labeled.add(cid)
        except Exception:
            pass

    # ── BRA fill ────────────────────────────────────────────────────────────────
    if bra_plot is not None:
        bra_plot.plot(ax=ax, facecolor='#f5c842', edgecolor='none', linewidth=0,
                      alpha=0.28, zorder=3)
        leg_h.append(Patch(facecolor='#f5c842', edgecolor='#7a5c00', linewidth=0.4,
                           linestyle='--', alpha=0.75))
        leg_l.append('BRA')

    # ── Water fill — edge set equal to fill colour to suppress any visible outline
    if water_gdf is not None and not water_gdf.empty:
        _wtr = water_gdf.to_crs('EPSG:4326').copy()
        _wtr['geometry'] = _wtr.geometry.buffer(0)
        _wtr.plot(ax=ax, facecolor=_WATER_FC, edgecolor=_WATER_FC, linewidth=0.5,
                  alpha=0.80, zorder=4)
        leg_h.append(Patch(facecolor=_WATER_FC, edgecolor='none', linewidth=0, alpha=0.80))
        leg_l.append('Water')

    # ── UC fill ─────────────────────────────────────────────────────────────────
    if uc_plot is not None:
        uc_plot.plot(ax=ax, facecolor='#e07b00', edgecolor='none', linewidth=0,
                     alpha=0.72, zorder=5)
        leg_h.append(Patch(facecolor='#e07b00', edgecolor='#cc0000', linewidth=1.8, alpha=0.90))
        leg_l.append('Urban Core (UC)')

    # ── Outlines drawn on top of fills ─────────────────────────────────────────
    if bra_plot is not None:
        bra_plot.plot(ax=ax, facecolor='none', edgecolor='#7a5c00',
                      linewidth=0.4, linestyle='--', alpha=0.92, zorder=6)
    if uc_plot is not None:
        uc_plot.plot(ax=ax, facecolor='none', edgecolor='#cc0000',
                     linewidth=1.8, linestyle='-', alpha=0.95, zorder=7)
    if cr_plot is not None:
        cr_plot.plot(ax=ax, facecolor='none', edgecolor='#333333',
                     linewidth=0.2, linestyle='-', alpha=0.88, zorder=8)

    # ── Cluster ID labels ────────────────────────────────────────────────────────
    for cx, cy, lbl in _cluster_labels:
        ax.text(cx, cy, lbl, fontsize=5.5, ha='center', va='center', color='#111',
                fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.12', facecolor='white',
                          alpha=0.55, edgecolor='none'), zorder=9)

    # ── Roads ────────────────────────────────────────────────────────────────────
    if roads_gdf is not None and not roads_gdf.empty:
        roads_gdf.to_crs('EPSG:4326').plot(ax=ax, color='#888888', linewidth=0.35,
                                            alpha=0.70, zorder=10)
        leg_h.append(Line2D([0], [0], color='#888888', linewidth=1.2, alpha=0.85))
        leg_l.append('Roads')

    ax.set_aspect('equal')
    ax.grid(True, alpha=0.15, linestyle=':', color='gray', zorder=0)
    ax.tick_params(axis='both', which='major', labelsize=5.5)

    return leg_h, leg_l


def create_publication_city_grid(
    city_names: list,
    zone_results: Dict,
    results_aoi_path,
    landscape_gdf,
    cluster25_colors: Dict,
    storage_crs: str = 'EPSG:4326',
    save_path=None,
    dpi: int = 300,
    figsize: tuple = (8.27, 5.845),
    single_north_arrow: bool = False,
) -> plt.Figure:
    """
    2x3 publication grid (half-A4 landscape).

    Parameters
    ----------
    single_north_arrow : bool, default False
        If False (NB01 default) a small north arrow is drawn on every city panel.
        If True, the per-panel arrows are suppressed and a single north arrow is
        drawn just above the shared legend (used for the manuscript Figure 4).

    Layout uses a 4-column GridSpec with a ~2 cm spacer between column 0
    (Kano / Lagos) and columns 2-3 (Abuja+Jos / Port Harcourt+Legend):

      Row 0:  city[0]  |  [~2 cm gap]  |  city[1]  |  city[2]
      Row 1:  city[3]  |  [~2 cm gap]  |  city[4]  |  legend

    No suburb labels. Compact scale bar (5pt text). North arrow at CR top-right.
    """
    from matplotlib.gridspec import GridSpec

    SPACER = 0.175         # spacer column as fraction of a data-column unit (~1 cm on A4)
    NROWS  = 2
    fig = plt.figure(figsize=figsize, facecolor='white')
    gs  = GridSpec(NROWS, 4, figure=fig,
                   width_ratios=[1, SPACER, 1, 1],
                   hspace=0.08, wspace=0.04)

    # (gs_row, gs_col) for each city in city_names[:5]
    GS_POS = [(0, 0), (0, 2), (0, 3), (1, 0), (1, 2)]

    shared_h, shared_l = None, None

    for idx, city in enumerate(city_names[:5]):
        gs_row, gs_col = GS_POS[idx]
        ax = fig.add_subplot(gs[gs_row, gs_col])

        if city not in zone_results:
            ax.set_visible(False)
            continue

        res       = zone_results[city]
        city_slug = res.get('city_slug', city.replace(' ', '_').lower())
        city_dir  = Path(res.get('city_dir', Path(results_aoi_path) / city_slug))

        def _load_or_none(p):
            p = Path(p)
            if p.exists():
                try:
                    g = gpd.read_file(p)
                    return g if not g.empty else None
                except Exception:
                    return None
            return None

        water_gdf = _load_or_none(city_dir / f'{city_slug}_water_bodies_4326.geojson')
        osm_dir   = city_dir / 'osm'
        roads_gdf = _load_or_none(osm_dir / f'{city_slug}_roads_4326.geojson')

        def _prep_zone(gdf):
            if gdf is None or gdf.empty:
                return None
            out = gdf.to_crs(storage_crs).copy()
            out['geometry'] = out.geometry.buffer(0)
            return out

        cr_4326  = _prep_zone(res.get('cr_gdf'))
        uc_4326  = _prep_zone(res.get('uc_gdf'))
        bra_4326 = _prep_zone(res.get('bra_gdf'))

        if cr_4326 is None:
            ax.set_visible(False)
            continue

        _union = (cr_4326.geometry.union_all()
                  if hasattr(cr_4326.geometry, 'union_all')
                  else cr_4326.geometry.unary_union)
        extent = gpd.GeoDataFrame(geometry=[_union.convex_hull], crs=storage_crs)

        leg_h, leg_l = _draw_zone_panel(
            ax=ax, aoi_gdf=extent,
            cr_gdf=cr_4326, uc_gdf=uc_4326, bra_gdf=bra_4326,
            landscape_gdf=landscape_gdf, cluster25_colors=cluster25_colors,
            water_gdf=water_gdf, roads_gdf=roads_gdf,
            places_gdf=None,
        )
        if shared_h is None:
            shared_h, shared_l = leg_h, leg_l

        # Compact scale bar
        _xlim = ax.get_xlim(); _ylim = ax.get_ylim()
        _ext_km = (_xlim[1] - _xlim[0]) * 111.0
        _scale_km = next((s for s in [50, 20, 10, 5, 2, 1] if s < _ext_km * 0.35), 1)
        _sdeg = _scale_km / 111.0
        _x0   = _xlim[0] + (_xlim[1] - _xlim[0]) * 0.05
        _y0   = _ylim[0] + (_ylim[1] - _ylim[0]) * 0.07
        _dh   = (_ylim[1] - _ylim[0]) * 0.012
        ax.plot([_x0, _x0 + _sdeg], [_y0, _y0], 'k-', linewidth=2.0, zorder=15,
                solid_capstyle='butt')
        for _xx in [_x0, _x0 + _sdeg]:
            ax.plot([_xx, _xx], [_y0 - _dh, _y0 + _dh], 'k-', linewidth=1.3, zorder=15)
        ax.text(_x0 + _sdeg / 2, _y0 + _dh * 1.5, f'{_scale_km} km',
                ha='center', va='bottom', fontsize=6.5, fontweight='bold', zorder=15,
                bbox=dict(boxstyle='round,pad=0.12', facecolor='white',
                          alpha=0.75, edgecolor='none'))

        # North arrow at CR top-right corner — arrowhead points UP (north).
        # Suppressed when a single shared arrow is requested (manuscript Figure 4).
        if not single_north_arrow:
            _cr_b  = cr_4326.to_crs('EPSG:4326').total_bounds
            _ax_w  = _xlim[1] - _xlim[0]; _ax_h = _ylim[1] - _ylim[0]
            _na_xf  = max(0.08, min((_cr_b[2] - _xlim[0]) / _ax_w - 0.10, 0.90))
            _na_tip = max(0.22, min((_cr_b[3] - _ylim[0]) / _ax_h - 0.04, 0.88))
            _na_base = max(0.06, _na_tip - 0.11)
            ax.annotate('',
                        xy=(_na_xf, _na_tip),       # arrowhead at top (pointing north)
                        xytext=(_na_xf, _na_base),  # tail at bottom
                        xycoords='axes fraction',
                        arrowprops=dict(arrowstyle='->', lw=1.2, color='black',
                                       mutation_scale=8),
                        zorder=16)
            ax.text(_na_xf, _na_tip + 0.025, 'N',
                    transform=ax.transAxes, ha='center', va='bottom',
                    fontsize=6.5, fontweight='bold', color='black', zorder=16)

        ax.set_title(city, fontsize=8.5, fontweight='bold', pad=3)
        ax.set_xlabel(''); ax.set_ylabel('')

    # Shared legend in gs[1, 3]
    ax_leg = fig.add_subplot(gs[1, 3])
    ax_leg.set_axis_off()
    # When a single shared arrow is requested, seat the legend lower so the arrow
    # has clear space above it; otherwise centre it as before.
    _leg_loc = 'lower center' if single_north_arrow else 'center'
    if shared_h:
        ax_leg.legend(handles=shared_h, labels=shared_l,
                      loc=_leg_loc, ncol=1, fontsize=7.5, framealpha=0.95,
                      edgecolor='#555', title='Legend', title_fontsize=8.5,
                      borderpad=0.7, labelspacing=0.40,
                      handlelength=1.3, handletextpad=0.45)

    # Single north arrow, centred just above the shared legend
    if single_north_arrow:
        ax_leg.annotate('',
                        xy=(0.5, 0.90), xytext=(0.5, 0.72),
                        xycoords='axes fraction',
                        arrowprops=dict(arrowstyle='->', lw=1.5, color='black',
                                        mutation_scale=13),
                        zorder=16)
        ax_leg.text(0.5, 0.92, 'N', transform=ax_leg.transAxes,
                    ha='center', va='bottom', fontsize=10, fontweight='bold',
                    color='black', zorder=16)

    fig.tight_layout()

    if save_path:
        _sp = Path(save_path)
        fig.savefig(_sp.with_suffix('.svg'), format='svg', dpi=dpi,
                    bbox_inches='tight', facecolor='white')
        fig.savefig(_sp.with_suffix('.pdf'), format='pdf',
                    bbox_inches='tight', facecolor='white')
        print(f"   Saved: {_sp.stem}.svg + .pdf")
    return fig


def create_cluster_zone_population_chart(
    cluster_zone_summary,
    save_path=None,
    dpi: int = 300,
    figsize: tuple = (11.69, 5.845),
) -> plt.Figure:
    """
    Dual-axis half-A4-landscape cluster chart.
    Left y-axis:  grouped bars UC/BRA/CR (km2), sorted by CR area descending.
    Right y-axis: WUP 2024 population — circle scatter (no connecting line).
    """
    import matplotlib.ticker as mticker

    df = cluster_zone_summary.sort_values('total_cr_area_km2', ascending=False).reset_index(drop=True)
    x_lbls = [f"Cl-{int(r.Cluster25):02d}\n({int(r.n_cities)})" for _, r in df.iterrows()]
    x  = np.arange(len(df)); bw = 0.22

    fig, ax1 = plt.subplots(figsize=figsize, facecolor='white')
    ax2 = ax1.twinx()

    _zone_cfg = [
        ('total_uc_area_km2',  '#e07b00', 'UC area (km²)'),
        ('total_bra_area_km2', '#f5c842', 'BRA area (km²)'),
        ('total_cr_area_km2',  '#d0d0c8', 'CR area (km²)'),
    ]
    for (col_name, colour, lbl), off in zip(_zone_cfg, [-bw, 0, bw]):
        vals = pd.to_numeric(df[col_name], errors='coerce').fillna(0).values
        ax1.bar(x + off, vals, width=bw * 0.92, color=colour,
                edgecolor='white', linewidth=0.5, alpha=0.90, label=lbl, zorder=3)

    ax1.set_ylabel('Zone Area (km²)', fontsize=12)
    ax1.set_xlabel('Cluster  (ID, N cities)', fontsize=12)
    ax1.set_xticks(x)
    ax1.set_xticklabels(x_lbls, fontsize=9)
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f'{v:,.0f}'))
    ax1.tick_params(axis='y', labelsize=9)
    ax1.grid(axis='y', alpha=0.20, linestyle='--', zorder=0)
    ax1.set_axisbelow(True)

    pop_m = pd.to_numeric(df['total_population_wup_k'], errors='coerce').fillna(0).values / 1_000
    ax2.scatter(x, pop_m, color='#1a237e', s=70, marker='o',
                edgecolors='white', linewidths=0.8, alpha=0.92,
                label='WUP 2024 pop (M)', zorder=5)
    ax2.set_ylabel('WUP 2024 Population (M)', fontsize=12, color='#1a237e')
    ax2.tick_params(axis='y', labelcolor='#1a237e', labelsize=9)
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f'{v:.1f}M'))

    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc='upper right', fontsize=10,
               framealpha=0.92, edgecolor='#555', ncol=2, borderpad=0.8, labelspacing=0.45)
    ax1.set_title('Cluster Zone Areas & WUP 2024 Population', fontsize=13,
                  fontweight='bold', pad=10)
    fig.tight_layout()

    if save_path:
        _sp = Path(save_path)
        fig.savefig(_sp.with_suffix('.svg'), format='svg', dpi=dpi,
                    bbox_inches='tight', facecolor='white')
        fig.savefig(_sp.with_suffix('.pdf'), format='pdf',
                    bbox_inches='tight', facecolor='white')
        print(f"   Saved: {_sp.stem}.svg + .pdf")
    return fig


def create_cluster_multiline_trend(
    cluster_zone_summary,
    cities_df,
    absorbed_map: Dict,
    cluster25_colors: Dict = None,
    save_path=None,
    dpi: int = 300,
    figsize: tuple = (11.69, 5.845),
) -> plt.Figure:
    """
    Multi-line half-A4-landscape cluster population trend, styled after the
    composite city population trend.

    Each cluster uses its defined CLUSTER25_COLORS colour.
    Growth rates expressed in M/yr (people per year, in millions) — consistent
    with the total linear trend label.
    2024 and 2050 diamond markers on the total line, with population annotations.
    """
    import matplotlib.lines   as mlines
    import matplotlib.patches as mpatch
    import matplotlib.ticker  as mticker

    yr_cols = sorted([c for c in cities_df.columns if c.isdigit()])
    # Use 5-year intervals plus 2024 so the study-year marker is exact
    _base_yrs = [y for y in yr_cols if int(y) % 5 == 0]
    pop_yrs   = sorted(set(_base_yrs + (['2024'] if '2024' in yr_cols else [])))
    yr_ints   = list(map(int, pop_yrs))
    last_year = yr_ints[-1]

    # Fallback palette if cluster25_colors not provided
    try:
        _cm = plt.colormaps['tab20']
    except AttributeError:
        _cm = plt.cm.get_cmap('tab20')
    _FALLBACK = [_cm(i / 20) for i in range(20)]

    def _build_agg_df(city_list):
        rows = []
        for city in city_list:
            members = [city] + [a for a, p in absorbed_map.items() if p == city]
            src = cities_df[cities_df['Urban Agglomeration'].isin(members)]
            if src.empty:
                continue
            agg = {c: src[c].sum() for c in yr_cols if c in src.columns}
            agg['Urban Agglomeration'] = city
            rows.append(agg)
        return pd.DataFrame(rows) if rows else pd.DataFrame()

    df_cl = cluster_zone_summary.sort_values('Cluster25').reset_index(drop=True)

    cluster_series = {}
    for _, row in df_cl.iterrows():
        cid    = int(row['Cluster25'])
        cities = [c.strip() for c in str(row['cities']).split(',') if c.strip()]
        agg_df = _build_agg_df(cities)
        if agg_df.empty:
            continue
        ts = [agg_df[y].sum() if y in agg_df.columns else 0.0 for y in pop_yrs]
        if len(ts) < 2 or all(v == 0 for v in ts):
            continue
        ts_m = [v / 1_000 for v in ts]   # millions
        # Linear slope in M/yr
        _nz = [i for i, v in enumerate(ts_m) if v > 0]
        if len(_nz) >= 2:
            _s, _ = np.polyfit(yr_ints[:len(ts_m)], ts_m, 1)
            rate_m_yr = float(_s)
        else:
            rate_m_yr = 0.0
        pop2024 = float(agg_df['2024'].sum()) / 1_000 if '2024' in agg_df.columns else 0.0
        cluster_series[cid] = {'ts_m': ts_m, 'pop2024': pop2024, 'rate': rate_m_yr}

    if not cluster_series:
        print("WARNING: no cluster time-series data."); return None

    # Total across all clusters
    n_pts     = min(len(cs['ts_m']) for cs in cluster_series.values())
    total_m   = [sum(cluster_series[cid]['ts_m'][i] for cid in cluster_series)
                 for i in range(n_pts)]
    yrs_total = yr_ints[:n_pts]

    # split_i: index of first year >= 2025 (solid includes 2025 as last point)
    SPLIT_YR = 2025
    split_i  = next((i for i, y in enumerate(yrs_total) if y >= SPLIT_YR), len(yrs_total))

    fig, ax = plt.subplots(figsize=figsize, facecolor='white')

    # Grey projection shade
    ax.axvspan(SPLIT_YR, last_year + 5, alpha=0.08, color='grey', zorder=0)

    # Per-cluster lines — use CLUSTER25_COLORS, fall back to tab20 by index
    sorted_cids = sorted(cluster_series.keys())
    for fi, cid in enumerate(sorted_cids):
        col = (cluster25_colors.get(int(cid)) if cluster25_colors else None) \
              or _FALLBACK[fi % len(_FALLBACK)]
        info = cluster_series[cid]
        ts_m = info['ts_m']
        yrs  = yr_ints[:len(ts_m)]
        si   = next((i for i, y in enumerate(yrs) if y >= SPLIT_YR), len(yrs))
        end_s = min(si + 1, len(yrs))
        ax.plot(yrs[:end_s], ts_m[:end_s],
                color=col, linewidth=1.2, alpha=0.80, zorder=3)
        if si < len(yrs):
            ax.plot(yrs[si:], ts_m[si:],
                    color=col, linewidth=1.0, alpha=0.45, linestyle='--', zorder=3)

    # Total line (navy, thick)
    end_s_tot = min(split_i + 1, len(total_m))
    ax.plot(yrs_total[:end_s_tot], total_m[:end_s_tot],
            color='navy', linewidth=2.4, alpha=0.92, zorder=5,
            label='Total (all clusters)')
    if split_i < len(total_m):
        ax.plot(yrs_total[split_i:], total_m[split_i:],
                color='navy', linewidth=2.0, alpha=0.55, linestyle='--', zorder=5)

    # Vertical reference lines with rotated year labels
    _y_max = max(total_m) * 1.10
    for yr_ref, lc, lw in [(2024, '#444444', 1.4), (last_year, '#777777', 1.0)]:
        ax.axvline(yr_ref, color=lc, linestyle='--', linewidth=lw, alpha=0.90, zorder=6)
        ax.text(yr_ref - 0.5, _y_max * 0.97, str(yr_ref),
                rotation=90, ha='right', va='top',
                fontsize=9, color=lc, fontweight='bold', zorder=7)

    # Diamond markers on total line at 2024 and last_year, with population labels
    for yr_ref in [2024, last_year]:
        if yr_ref in yrs_total:
            _idx = yrs_total.index(yr_ref)
            _val = total_m[_idx]
            ax.scatter(yr_ref, _val, marker='D', s=65,
                       color='navy', edgecolors='white', linewidths=0.8, zorder=8)
            # Annotation with population value
            _xoff = 0.42 if yr_ref == 2024 else 0.55
            _yoff = 0.38 if yr_ref == 2024 else 0.56
            ax.annotate(f"Total {yr_ref}:\n{_val:.1f} M",
                        xy=(yr_ref, _val), xycoords='data',
                        xytext=(_xoff, _yoff), textcoords='axes fraction',
                        fontsize=9.5, fontweight='bold', color='navy',
                        ha='left', va='center',
                        arrowprops=dict(arrowstyle='->', color='#444', lw=0.9))

    # "Projected" label in shaded area
    _proj_mid = (SPLIT_YR + last_year) / 2
    ax.text(_proj_mid, max(total_m) * 1.04, 'Projected',
            ha='center', va='bottom', fontsize=9.5,
            fontstyle='italic', color='#555555', zorder=9)

    # Linear regression on total
    _slope, _intercept = np.polyfit(yrs_total, total_m, 1)
    _ypred  = np.poly1d([_slope, _intercept])(yrs_total)
    _ss_res = np.sum((np.array(total_m) - _ypred) ** 2)
    _ss_tot = np.sum((np.array(total_m) - np.mean(total_m)) ** 2)
    _r2 = 1 - _ss_res / _ss_tot if _ss_tot > 0 else 0.0
    ax.plot(yrs_total, _ypred, linestyle=':', color='grey', linewidth=1.2, alpha=0.70,
            label=f'Linear trend ({_slope:+.2f} M/yr)', zorder=2)
    ax.text(0.22, 0.12,
            f'y = {_slope:.2f}·x + {_intercept:.0f}\n(R² = {_r2:.4f})',
            transform=ax.transAxes, fontsize=8.5, color='grey',
            ha='left', va='bottom',
            bbox=dict(boxstyle='round,pad=0.25', facecolor='white',
                      edgecolor='grey', alpha=0.70))

    # 10-year growth rates box — in M/yr (consistent with linear trend)
    _milestone_yrs = list(range(yr_ints[0], last_year + 1, 10))
    if last_year not in _milestone_yrs:
        _milestone_yrs.append(last_year)
    _gr_lines = []
    for _ia in range(len(_milestone_yrs) - 1):
        _y0, _y1 = _milestone_yrs[_ia], _milestone_yrs[_ia + 1]
        if _y0 in yrs_total and _y1 in yrs_total:
            _p0 = total_m[yrs_total.index(_y0)]
            _p1 = total_m[yrs_total.index(_y1)]
            _gr = (_p1 - _p0) / (_y1 - _y0)  # M/yr
            _gr_lines.append(f'{_y0}–{_y1}: {_gr:+.2f} M/yr')
    if _gr_lines:
        ax.text(0.02, 0.97, '10-yr Growth Rate:\n' + '\n'.join(_gr_lines),
                transform=ax.transAxes, va='top', fontsize=7.5,
                bbox=dict(boxstyle='round,pad=0.35',
                          facecolor='#d9ecff', edgecolor='#003d7a', alpha=0.88))

    # Axis formatting
    ax.set_xlabel('Year', fontsize=11)
    ax.set_ylabel('Aggregated Population (M)', fontsize=11)
    ax.set_title('Cluster25 Population Trends — WUP Reference', fontsize=13,
                 fontweight='bold', pad=10)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f'{int(round(v))}M'))
    ax.tick_params(axis='both', labelsize=9)
    ax.grid(True, alpha=0.15, linestyle=':', zorder=0)
    ax.set_axisbelow(True)
    ax.set_xlim(yr_ints[0] - 2, last_year + 4)
    ax.set_ylim(0, max(total_m) * 1.12)

    # Legend: Total + linear trend + per-cluster (no projection/year reference entries)
    _leg_h = [
        mlines.Line2D([0], [0], color='navy', linewidth=2.4),
        mlines.Line2D([0], [0], color='grey', linestyle=':', linewidth=1.2, alpha=0.70),
    ]
    _leg_l = [
        'Total — all clusters',
        f'Linear trend ({_slope:+.2f} M/yr)',
    ]
    for cid in sorted_cids:
        info = cluster_series[cid]
        col  = (cluster25_colors.get(int(cid)) if cluster25_colors else None) \
               or _FALLBACK[sorted_cids.index(cid) % len(_FALLBACK)]
        lbl  = f"C{cid:02d}  {info['pop2024']:.1f}M  ({info['rate']:+.2f}M/yr)"
        _leg_h.append(mlines.Line2D([0], [0], color=col, linewidth=1.8))
        _leg_l.append(lbl)

    ax.legend(_leg_h, _leg_l,
              loc='upper left',
              fontsize=8.5, framealpha=0.92, edgecolor='#aaa',
              title='Cluster | Pop 2024 | Growth (M/yr)',
              title_fontsize=9.5, ncol=2,
              borderpad=0.8, labelspacing=0.35,
              handlelength=1.6, handletextpad=0.5, columnspacing=1.0)

    fig.tight_layout()

    if save_path:
        _sp = Path(save_path)
        fig.savefig(_sp.with_suffix('.svg'), format='svg', dpi=dpi,
                    bbox_inches='tight', facecolor='white')
        fig.savefig(_sp.with_suffix('.pdf'), format='pdf',
                    bbox_inches='tight', facecolor='white')
        print(f"   Saved: {_sp.stem}.svg + .pdf")
    return fig
