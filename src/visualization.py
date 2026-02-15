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
from typing import Dict, Any, Optional, Tuple
import warnings

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
    
    # Add north arrow
    ax.annotate('N', xy=(0.9, 0.9), xycoords='axes fraction', fontsize=16, fontweight='bold',
               ha='center', va='center',
               bbox=dict(boxstyle='circle', facecolor='white', edgecolor='black'))
    ax.annotate('↑', xy=(0.9, 0.84), xycoords='axes fraction', fontsize=18, fontweight='bold',
               ha='center', va='center')
    
    plt.tight_layout()
    
    # Save if path provided
    if save_path:
        save_path = Path(save_path)
        # Save PNG
        fig.savefig(save_path, dpi=config.FIGURE_DPI, bbox_inches='tight')
        # Save PDF
        pdf_path = save_path.with_suffix('.pdf')
        fig.savefig(pdf_path, format='pdf', bbox_inches='tight')
        print(f"AOI map saved: {save_path.name} + {pdf_path.name}")
    
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
    
    # Prepare year series
    pop_years = [str(y) for y in range(1950, 2036, 5)]
    years_int = list(map(int, pop_years))
    
    # Create figure
    fig, ax = plt.subplots(figsize=figsize)
    
    # Plot city series
    palette = plt.cm.Set3(np.linspace(0, 1, len(cities_in_aoi_df)))
    
    for i, (_, city) in enumerate(cities_in_aoi_df.iterrows()):
        name = city["Urban Agglomeration"]
        populations = [city[yr] for yr in pop_years if yr in city.index]
        
        if name == current_city:  # target city
            ax.plot(years_int[:len(populations)], populations,
                    label=f"{name} (Target)",
                    color="red", marker="o",
                    linewidth=1, markersize=4, alpha=0.75)
        else:  # other cities
            ax.plot(years_int[:len(populations)], populations,
                    label=name,
                    color=palette[i], marker="o",
                    linewidth=1.2, markersize=4, alpha=0.75)
    
    # Total AOI population trend
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
    
    # Vertical 2024 label
    ax.text(2024, ax.get_ylim()[1] * 0.9,
            "2024", rotation=90,
            ha="right", va="bottom", fontsize=8, color="crimson")
    
    # Population annotation
    ax.annotate(f"Total Pop 2024:\n{y_2024:,.0f},000",
                xy=(2024, y_2024),
                xycoords="data",
                xytext=(0.5, 0.50),
                textcoords="axes fraction",
                fontsize=8, fontweight="bold", color="crimson",
                ha="left", va="center",
                arrowprops=dict(arrowstyle="->", color="black", lw=1))
    
    # Linear trend & regression equation
    slope, intercept = np.polyfit(years_int[:len(total_pop)], total_pop, 1)
    ax.plot(years_int[:len(total_pop)], np.poly1d([slope, intercept])(years_int[:len(total_pop)]),
            linestyle="--", color="grey", linewidth=1.2,
            label=f"Linear Trend (slope ≈ {slope:,.0f}k/yr)")
    
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
            r = ((total_pop[i+2] / total_pop[i]) ** 0.1 - 1) * 100
            growth_rates.append(f"{years_int[i]}-{years_int[i+2]}: {r:5.2f}%/yr")
    
    ax.text(0.02, 0.98,
            "Growth Rates (10-yr):\n" + "\n".join(growth_rates),
            transform=ax.transAxes, va="top",
            fontsize=7.5,
            bbox=dict(boxstyle="round,pad=0.4",
                      facecolor="#d9ecff", edgecolor="#003d7a", alpha=0.9))
    
    # Formatting
    ax.set_title(f"Population Trends in {current_city} AOI (1950-2035)",
                 fontsize=12, fontweight="bold", pad=10)
    ax.set_xlabel("Year", fontsize=8)
    ax.set_ylabel("Population (thousands)", fontsize=8)
    ax.grid(True, alpha=0.25)
    ax.set_ylim(0, max(total_pop) * 1.1)
    
    # Legend
    ax.legend(title="Legend",
              fontsize=7.5, title_fontsize=8.5,
              loc="upper left", bbox_to_anchor=(0.25, 1),
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
        cbar_kws={'label': 'LST (�C)'},
        linewidths=0.5,
        linecolor='gray',
        ax=ax1
    )
    ax1.set_title('Day-time LST', fontsize=16, fontweight='bold', pad=15)
    ax1.set_xlabel('Year' if time_dim == 'year' else 'Month', fontsize=12)
    ax1.set_ylabel('City', fontsize=12)
    ax1.tick_params(axis='x', rotation=45)
    
    # Night-time heatmap
    ax2 = fig.add_subplot(gs[0, 1])
    sns.heatmap(
        night_data,
        annot=True,
        fmt='.1f',
        cmap='PuBu',
        cbar_kws={'label': 'LST (�C)'},
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
        print(f'✅ Saved combined heatmap to {output_path.name} + {pdf_path.name}')
    
    return fig


def create_lst_heatmap(data, lst_time, time_dim='year', output_path=None, dpi=300):
    """
    Create a single LST heatmap with dynamic sizing and sorted by temperature.
    
    Parameters:
    -----------
    data : pd.DataFrame
        Heatmap data (cities as rows, time as columns)
    lst_time : str
        'day' or 'night'
    time_dim : str
        'year' or 'month'
    output_path : str, optional
        Path to save the figure
    dpi : int
        DPI for saved figure
        
    Returns:
    --------
    matplotlib.figure.Figure
        The heatmap figure
    """
    import seaborn as sns
    
    if data.empty:
        print(f"⚠️ No data to plot for {lst_time}-time {time_dim}")
        return None
    
    # Sort cities by mean temperature (warmest to coolest)
    # Note: ascending=True because heatmap displays bottom-to-top (last row at bottom)
    data = data.copy()
    data['mean_temp'] = data.mean(axis=1)
    data = data.sort_values('mean_temp', ascending=True)  # Changed to True for correct display
    data = data.drop('mean_temp', axis=1)
    
    # For monthly data, convert month numbers to names
    if time_dim == 'month':
        month_names = {1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun',
                      7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'}
        data.columns = [month_names.get(int(col), col) for col in data.columns]
    
    # Dynamic figure sizing based on number of cities
    n_cities = len(data)
    n_periods = len(data.columns)
    
    # Calculate figure dimensions (more aggressive compactness)
    if time_dim == 'month':
        # Monthly: slightly wider cells, more compact vertically
        fig_height = max(2.5, min(8, n_cities * 0.28))  # Reduced from 0.35
        fig_width = max(7, min(16, n_periods * 0.45))   # Slightly wider for month names
    else:
        # Yearly: keep horizontal, reduce vertical significantly
        fig_height = max(2.5, min(8, n_cities * 0.25))  # Further reduced from 0.35
        fig_width = max(8, min(18, n_periods * 0.32))   # Reduced from 0.35
    
    # Font sizes scale with figure size (reduced)
    title_fontsize = max(9, min(13, fig_height * 1.3))
    label_fontsize = max(8, min(11, fig_height * 1.1))
    tick_fontsize = max(7, min(9, fig_height * 0.85))
    annot_fontsize = max(5, min(7, fig_height * 0.7))
    cbar_labelsize = max(7, min(9, fig_height * 0.85))  # Same as tick labels
    
    # Create figure
    fig, ax = plt.subplots(figsize=(fig_width, fig_height), dpi=dpi)
    
    # Choose colormap based on day/night
    cmap = 'YlOrRd' if lst_time == 'day' else 'PuBu'
    cbar_label = 'LST (\u00b0C)'  # Fixed degree symbol using unicode
    
    # Create heatmap with thinner colorbar
    heatmap = sns.heatmap(
        data,
        annot=True,
        fmt='.1f',
        cmap=cmap,
        cbar_kws={
            'label': cbar_label,
            'shrink': 0.55,  # Further reduced from 0.6
            'aspect': 35,    # Increased from 30 for even thinner bar
            'pad': 0.01      # Minimal padding
        },
        linewidths=0.2,  # Even thinner gridlines (from 0.3)
        linecolor='gray',
        ax=ax,
        annot_kws={'fontsize': annot_fontsize}
    )
    
    # Adjust colorbar label size to match axis labels
    cbar = heatmap.collections[0].colorbar
    cbar.ax.tick_params(labelsize=tick_fontsize)
    cbar.set_label(cbar_label, size=cbar_labelsize)
    
    # Format labels
    time_label = 'Year' if time_dim == 'year' else 'Month'
    title_time = 'Yearly' if time_dim == 'year' else 'Monthly Climatology'
    
    ax.set_title(
        f'{lst_time.title()}-time LST - {title_time} (Warmest to Coolest)',
        fontsize=title_fontsize,
        fontweight='bold',
        pad=8  # Further reduced from 10
    )
    ax.set_xlabel(time_label, fontsize=label_fontsize, fontweight='bold')
    ax.set_ylabel('City', fontsize=label_fontsize, fontweight='bold')
    
    # Rotate x-axis labels for better readability
    if time_dim == 'month':
        ax.tick_params(axis='x', rotation=0, labelsize=tick_fontsize)  # Horizontal for month names
    else:
        ax.tick_params(axis='x', rotation=45, labelsize=tick_fontsize)
    ax.tick_params(axis='y', rotation=0, labelsize=tick_fontsize)
    
    plt.tight_layout(pad=0.3)  # Even more minimal padding (from 0.5)
    
    if output_path:
        # Save both PNG and PDF
        fig.savefig(output_path, dpi=dpi, bbox_inches='tight')
        
        # Generate PDF path from PNG path
        pdf_path = output_path.replace('.png', '.pdf')
        fig.savefig(pdf_path, format='pdf', bbox_inches='tight')
        
        print(f'✅ Saved {lst_time}-time {time_dim} heatmap (PNG + PDF)')
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
        print(f"⚠️ No data to plot for {lst_time}-time {time_dim}")
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
    
    # Choose colormap
    cmap = 'YlOrRd' if lst_time == 'day' else 'PuBu'
    cbar_label = 'LST (\u00b0C)'
    
    # Create heatmap
    heatmap = sns.heatmap(
        data,
        annot=True,
        fmt='.1f',
        cmap=cmap,
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
        print(f'✅ Saved {lst_time}-time {time_dim} heatmap with validation (PNG + PDF)')
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
    dpi=300
):
    """
    Create multi-panel scatter plots comparing two datasets across multiple cities.
    
    Creates a grid of scatter plots (one per city) showing MODIS vs ERA5-Land comparison
    for both day and night periods, with statistics displayed in each panel.
    
    Parameters
    ----------
    comparison_results_list : list of dict
        List of dictionaries, each containing:
        - 'city': str, city name
        - 'day_comparison': dict from compare_datasets()
        - 'night_comparison': dict from compare_datasets()
    dataset1_name : str
        Name of first dataset (e.g., 'MODIS')
    dataset2_name : str
        Name of second dataset (e.g., 'ERA5-Land')
    output_dir : str or Path, optional
        Directory to save figure
    figsize : tuple, optional
        Figure size (auto-calculated if None)
    dpi : int
        Figure resolution
        
    Returns
    -------
    fig : matplotlib.figure.Figure
        The created figure
        
    Example
    -------
    >>> comparison_results = [
    ...     {'city': 'Abuja', 'day_comparison': day_comp, 'night_comparison': night_comp},
    ...     {'city': 'Lagos', 'day_comparison': day_comp, 'night_comparison': night_comp}
    ... ]
    >>> fig = plot_multi_city_dataset_comparison(comparison_results)
    """
    n_cities = len(comparison_results_list)
    
    # Calculate grid layout (2 columns: day and night)
    ncols = 2  # Day and Night
    nrows = n_cities
    
    # Auto-calculate figure size if not provided
    if figsize is None:
        width = 14
        height = 4 * nrows
        figsize = (width, height)
    
    # Create figure and subplots
    fig, axes = plt.subplots(nrows, ncols, figsize=figsize, dpi=dpi, squeeze=False)
    
    # Color scheme - orange for day, grey for night
    day_color = '#FF8C42'  # Orange for daytime
    night_color = '#7D7D7D'  # Grey for nighttime
    line_color = '#E63946'  # Red for 1:1 line
    
    for i, result in enumerate(comparison_results_list):
        city = result['city']
        day_comp = result['day_comparison']
        night_comp = result['night_comparison']
        
        # ===== DAY PANEL =====
        ax_day = axes[i, 0]
        
        # Extract merged data
        day_merged = day_comp['merged_data']
        
        if not day_merged.empty:
            # Find column names
            col1_day = [c for c in day_merged.columns if dataset1_name in c][0]
            col2_day = [c for c in day_merged.columns if dataset2_name in c][0]
            
            # Scatter plot - ORANGE for day with thin black outline
            ax_day.scatter(day_merged[col1_day], day_merged[col2_day], 
                          alpha=0.7, s=30, color=day_color, 
                          edgecolors='black', linewidth=0.4)
            
            # 1:1 reference line
            min_val = min(day_merged[col1_day].min(), day_merged[col2_day].min())
            max_val = max(day_merged[col1_day].max(), day_merged[col2_day].max())
            ax_day.plot([min_val, max_val], [min_val, max_val], 
                       color=line_color, linestyle='--', linewidth=2, alpha=0.8, label='1:1 Line')
            
            # Add statistics box at bottom right
            r = day_comp['correlation']
            bias = day_comp['bias']
            rmse = day_comp['rmse']
            mae = day_comp['mae']
            n = day_comp['n_samples']
            
            stats_text = (f'r = {r:.3f}\n'
                         f'Bias = {bias:+.2f}°C\n'
                         f'RMSE = {rmse:.2f}°C\n'
                         f'MAE = {mae:.2f}°C\n'
                         f'n = {n}')
            
            # Position at bottom right (fixed alignment)
            ax_day.text(0.97, 0.03, stats_text, transform=ax_day.transAxes, 
                       verticalalignment='bottom', horizontalalignment='right',
                       fontsize=9, family='monospace',
                       bbox=dict(boxstyle='round,pad=0.5', facecolor='white', 
                                edgecolor='gray', alpha=0.95, linewidth=1))
            
            # Axis labels
            ax_day.set_xlabel(f'{dataset1_name} LST (°C)', fontsize=10, fontweight='bold')
            ax_day.set_ylabel(f'{dataset2_name} LST (°C)', fontsize=10, fontweight='bold')
            
            # Title (city name and period)
            if i == 0:
                ax_day.set_title(f'{city} - Daytime', fontsize=11, fontweight='bold', pad=10)
            else:
                ax_day.set_title(f'{city} - Daytime', fontsize=11, fontweight='bold', pad=10)
            
            # Grid
            ax_day.grid(True, alpha=0.25, linestyle=':', linewidth=0.5)
            
            # Equal aspect for better comparison
            ax_day.set_aspect('equal', adjustable='box')
        
        # ===== NIGHT PANEL =====
        ax_night = axes[i, 1]
        
        # Extract merged data
        night_merged = night_comp['merged_data']
        
        if not night_merged.empty:
            # Find column names
            col1_night = [c for c in night_merged.columns if dataset1_name in c][0]
            col2_night = [c for c in night_merged.columns if dataset2_name in c][0]
            
            # Scatter plot - GREY for night with thin black outline
            ax_night.scatter(night_merged[col1_night], night_merged[col2_night], 
                           alpha=0.7, s=30, color=night_color, 
                           edgecolors='black', linewidth=0.4)
            
            # 1:1 reference line
            min_val = min(night_merged[col1_night].min(), night_merged[col2_night].min())
            max_val = max(night_merged[col1_night].max(), night_merged[col2_night].max())
            ax_night.plot([min_val, max_val], [min_val, max_val], 
                         color=line_color, linestyle='--', linewidth=2, alpha=0.8, label='1:1 Line')
            
            # Add statistics box at bottom right
            r = night_comp['correlation']
            bias = night_comp['bias']
            rmse = night_comp['rmse']
            mae = night_comp['mae']
            n = night_comp['n_samples']
            
            stats_text = (f'r = {r:.3f}\n'
                         f'Bias = {bias:+.2f}°C\n'
                         f'RMSE = {rmse:.2f}°C\n'
                         f'MAE = {mae:.2f}°C\n'
                         f'n = {n}')
            
            # Position at bottom right (fixed alignment)
            ax_night.text(0.97, 0.03, stats_text, transform=ax_night.transAxes, 
                         verticalalignment='bottom', horizontalalignment='right',
                         fontsize=9, family='monospace',
                         bbox=dict(boxstyle='round,pad=0.5', facecolor='white', 
                                  edgecolor='gray', alpha=0.95, linewidth=1))
            
            # Axis labels
            ax_night.set_xlabel(f'{dataset1_name} LST (°C)', fontsize=10, fontweight='bold')
            ax_night.set_ylabel(f'{dataset2_name} LST (°C)', fontsize=10, fontweight='bold')
            
            # Title
            if i == 0:
                ax_night.set_title(f'{city} - Nighttime', fontsize=11, fontweight='bold', pad=10)
            else:
                ax_night.set_title(f'{city} - Nighttime', fontsize=11, fontweight='bold', pad=10)
            
            # Grid
            ax_night.grid(True, alpha=0.25, linestyle=':', linewidth=0.5)
            
            # Equal aspect
            ax_night.set_aspect('equal', adjustable='box')
    
    # Overall title
    fig.suptitle(f'Inter-Dataset Validation: {dataset1_name} vs {dataset2_name}', 
                 fontsize=14, fontweight='bold', y=0.995)
    
    # Adjust layout
    plt.tight_layout(rect=[0, 0, 1, 0.99])
    
    # Save if output directory specified
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        png_path = output_dir / f'multi_city_comparison_{dataset1_name}_vs_{dataset2_name}.png'
        pdf_path = output_dir / f'multi_city_comparison_{dataset1_name}_vs_{dataset2_name}.pdf'
        
        fig.savefig(png_path, dpi=dpi, bbox_inches='tight', facecolor='white')
        fig.savefig(pdf_path, format='pdf', bbox_inches='tight', facecolor='white')
        print(f"   ✓ Saved: {png_path.name}")
        print(f"   ✓ Saved: {pdf_path.name}")
    
    return fig


def plot_target_diagram(
    comparison_results,
    dataset1_name='MODIS',
    dataset2_name='ERA5-Land',
    output_dir=None,
    figsize=None,
    dpi=300,
    show_labels=True
):
    """
    Create a Target Diagram showing validation metrics for multiple cities.
    
    A Target Diagram is a standardized plot used in atmospheric science to visualize
    model performance metrics (bias, RMSE, correlation) in a single coordinate system.
    
    Mathematical Formulation:
    -------------------------
    X-axis: Unbiased RMSE = √(RMSE² - Bias²)
        - Represents random error component
        - Distance from y-axis
        
    Y-axis: Bias = Mean(Dataset1 - Dataset2)
        - Represents systematic error
        - Positive = Dataset1 > Dataset2
        - Negative = Dataset1 < Dataset2
        
    Distance from origin = Total RMSE
        - Points near center = Better agreement
        - RMSE circles show performance contours
    
    Parameters
    ----------
    comparison_results : list of dict
        List of dictionaries containing comparison metrics for each city:
        - 'city': str, city name
        - 'day_bias': float, daytime bias
        - 'day_rmse': float, daytime RMSE
        - 'day_correlation': float, daytime Pearson r
        - 'night_bias': float, nighttime bias
        - 'night_rmse': float, nighttime RMSE
        - 'night_correlation': float, nighttime Pearson r
    dataset1_name : str
        Name of reference dataset (e.g., 'MODIS')
    dataset2_name : str
        Name of comparison dataset (e.g., 'ERA5-Land')
    output_dir : str or Path, optional
        Directory to save figure
    figsize : tuple, optional
        Figure size (width, height) in inches
        If None, automatically calculated based on number of cities:
        - 5 cities: (8.27, 5.85) = half A4 landscape
        - Scales up for larger datasets
    dpi : int
        Figure resolution (300 recommended for publication)
    show_labels : bool
        Whether to show city name labels on points
        Automatically disabled if > 20 cities to avoid clutter
        
    Returns
    -------
    fig : matplotlib.figure.Figure
        The created figure
        
    dict : Summary statistics
        Contains best/worst performers and overall statistics
        
    Notes
    -----
    - Orange markers = Daytime
    - Grey markers = Nighttime
    - Red target at origin = Perfect agreement
    - Concentric circles = RMSE contours
    - Equal aspect ratio ensures proper circle geometry
    - Uses adjustText to prevent label overlaps
    
    Example
    -------
    >>> comparison_results = [
    ...     {'city': 'Abuja', 'day_bias': -4.64, 'day_rmse': 5.74, ...},
    ...     {'city': 'Lagos', 'day_bias': -3.72, 'day_rmse': 4.92, ...}
    ... ]
    >>> fig, stats = plot_target_diagram(comparison_results)
    """
    import numpy as np
    from pathlib import Path
    from adjustText import adjust_text
    
    n_cities = len(comparison_results)
    
    # Extract metrics
    cities = []
    biases_day = []
    rmses_day = []
    correlations_day = []
    biases_night = []
    rmses_night = []
    correlations_night = []
    
    for result in comparison_results:
        cities.append(result['city'])
        biases_day.append(result['day_bias'])
        rmses_day.append(result['day_rmse'])
        correlations_day.append(result['day_correlation'])
        biases_night.append(result['night_bias'])
        rmses_night.append(result['night_rmse'])
        correlations_night.append(result['night_correlation'])
    
    # Calculate unbiased RMSE (random error component)
    # RMSE' = sqrt(RMSE² - Bias²)
    unbiased_rmse_day = np.sqrt(np.array(rmses_day)**2 - np.array(biases_day)**2)
    unbiased_rmse_night = np.sqrt(np.array(rmses_night)**2 - np.array(biases_night)**2)
    
    # Dynamic figure sizing
    if figsize is None:
        # Half A4 landscape (8.27" x 5.85") for 5-10 cities
        # Scale up gradually for more cities
        if n_cities <= 10:
            figsize = (8.27, 5.85)
        elif n_cities <= 20:
            figsize = (10, 7)
        elif n_cities <= 50:
            figsize = (12, 9)
        else:
            figsize = (14, 11)
    
    # Automatic label control for large datasets
    if show_labels and n_cities > 20:
        show_labels = False
        print(f"ℹ️  City labels disabled (n={n_cities} > 20). Use legend instead.")
    
    # Create figure
    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    
    # Color scheme
    day_color = '#FF8C42'    # Orange
    night_color = '#7D7D7D'  # Grey
    
    # Dynamic marker size based on number of cities
    if n_cities <= 10:
        marker_size = 120
        label_fontsize = 8
    elif n_cities <= 20:
        marker_size = 80
        label_fontsize = 7
    elif n_cities <= 50:
        marker_size = 50
        label_fontsize = 6
    else:
        marker_size = 30
        label_fontsize = 5
    
    # Plot observations
    ax.scatter(unbiased_rmse_day, biases_day, 
               s=marker_size, alpha=0.75, color=day_color, 
               edgecolors='black', linewidth=1.0,
               label='Daytime', marker='o', zorder=3)
    
    ax.scatter(unbiased_rmse_night, biases_night, 
               s=marker_size, alpha=0.75, color=night_color, 
               edgecolors='black', linewidth=1.0,
               label='Nighttime', marker='o', zorder=3)
    
    # Add city labels if enabled
    texts = []
    if show_labels:
        for i, city in enumerate(cities):
            # Day labels - black text for legibility
            text_day = ax.text(unbiased_rmse_day[i], biases_day[i], city,
                              fontsize=label_fontsize, fontweight='normal',
                              color='black', alpha=0.85)
            texts.append(text_day)
            
            # Night labels - black text for legibility
            text_night = ax.text(unbiased_rmse_night[i], biases_night[i], city,
                                fontsize=label_fontsize, fontweight='normal',
                                color='black', alpha=0.85)
            texts.append(text_night)
    
    # Add RMSE reference circles - visible with good spacing
    max_rmse = max(max(rmses_day), max(rmses_night))
    
    # Dynamic circle levels - 2°C intervals
    if max_rmse <= 6:
        rmse_levels = [2, 4, 6]
    elif max_rmse <= 10:
        rmse_levels = [2, 4, 6, 8, 10]
    else:
        rmse_levels = list(range(2, int(max_rmse) + 4, 2))
    
    for rmse in rmse_levels:
        circle = plt.Circle((0, 0), rmse, fill=False, 
                           edgecolor='#555555', linestyle='--', 
                           linewidth=0.5, alpha=0.6, zorder=1)
        ax.add_patch(circle)
        # Label circles - darker and more visible
        ax.text(rmse * 0.707, rmse * 0.707, f'{rmse}°C', 
               fontsize=8, color='#333333', alpha=0.8,
               ha='center', va='center',
               bbox=dict(boxstyle='round,pad=0.3', facecolor='white', 
                        edgecolor='none', alpha=0.85))
    
    # Crosshairs at origin
    ax.axhline(y=0, color='black', linewidth=1.2, linestyle='-', alpha=0.6, zorder=2)
    ax.axvline(x=0, color='black', linewidth=1.2, linestyle='-', alpha=0.6, zorder=2)
    
    # Bullseye target (perfect agreement) - sniper target style
    ax.scatter([0], [0], s=200, color='none', edgecolors='red', 
              linewidths=2.0, marker='o', zorder=4)
    ax.scatter([0], [0], s=100, color='none', edgecolors='red', 
              linewidths=1.5, marker='o', zorder=4)
    ax.scatter([0], [0], s=30, color='red', marker='o', 
              linewidths=0, zorder=4, label='Perfect Agreement')
    
    # Set axis limits - increase x-axis width for more space
    max_unbiased_rmse = max(max(unbiased_rmse_day), max(unbiased_rmse_night))
    max_bias = max(max(abs(np.array(biases_day))), max(abs(np.array(biases_night))))
    axis_limit = max(max_unbiased_rmse, max_bias) * 1.15
    
    # Wider x-axis (1.4x multiplier) for more horizontal space
    ax.set_xlim(-axis_limit * 0.1, axis_limit * 1.4)
    ax.set_ylim(-axis_limit, axis_limit)
    
    # Labels and title
    ax.set_xlabel('Unbiased RMSE (°C)', fontsize=10, fontweight='bold')
    ax.set_ylabel(f'Bias (°C)\n[{dataset1_name} − {dataset2_name}]', 
                 fontsize=10, fontweight='bold')
    ax.set_title(f'Target Diagram: {dataset1_name} vs {dataset2_name}', 
                fontsize=11, fontweight='bold', pad=12)
    
    # Grid
    ax.grid(True, alpha=0.2, linestyle=':', linewidth=0.5, zorder=0)
    
    # Legend - position based on data distribution
    legend_loc = 'upper right' if np.mean(biases_day) < 0 else 'lower right'
    ax.legend(loc=legend_loc, fontsize=8, framealpha=0.95, 
             edgecolor='gray', fancybox=False, frameon=True)
    
    # Equal aspect ratio
    ax.set_aspect('equal', adjustable='box')
    
    # Apply adjustText to prevent label overlaps
    if show_labels and texts:
        adjust_text(texts, ax=ax, 
                   expand_points=(1.5, 1.5),
                   arrowprops=dict(arrowstyle='-', color='gray', lw=0.3, alpha=0.5),
                   force_points=(0.5, 0.5),
                   force_text=(0.5, 0.5))
    
    plt.tight_layout()
    
    # Save if requested
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        png_path = output_dir / f'target_diagram_{dataset1_name}_vs_{dataset2_name}.png'
        pdf_path = output_dir / f'target_diagram_{dataset1_name}_vs_{dataset2_name}.pdf'
        
        fig.savefig(png_path, dpi=dpi, bbox_inches='tight', facecolor='white')
        fig.savefig(pdf_path, format='pdf', bbox_inches='tight', facecolor='white')
        print(f"   ✓ Saved: {png_path.name}")
        print(f"   ✓ Saved: {pdf_path.name}")
    
    # Generate summary statistics
    summary = {
        'n_cities': n_cities,
        'day': {
            'best_city': cities[np.argmin(rmses_day)],
            'best_rmse': np.min(rmses_day),
            'worst_city': cities[np.argmax(rmses_day)],
            'worst_rmse': np.max(rmses_day),
            'mean_bias': np.mean(biases_day),
            'mean_rmse': np.mean(rmses_day),
            'mean_correlation': np.mean(correlations_day)
        },
        'night': {
            'best_city': cities[np.argmin(rmses_night)],
            'best_rmse': np.min(rmses_night),
            'worst_city': cities[np.argmax(rmses_night)],
            'worst_rmse': np.max(rmses_night),
            'mean_bias': np.mean(biases_night),
            'mean_rmse': np.mean(rmses_night),
            'mean_correlation': np.mean(correlations_night)
        }
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
    figsize: tuple = None
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
        print("⚠️  adjustText not available - text overlap may occur")
        print("    Install with: pip install adjustText")
    
    # Filter cities with data for this period
    available_cities = {name: data for name, data in cities_data.items() 
                       if period in data}
    
    n_cities = len(available_cities)
    if n_cities == 0:
        print(f"⚠️  No {period} data available")
        return None
    
    print(f"\n{'='*80}")
    print(f"CREATING PERSISTENT HEAT EVENT MAPS - {period.upper()}")
    print(f"{'='*80}")
    print(f"Cities: {n_cities}")
    
    # Temperature scales and colormap
    if period == 'day':
        vmin, vmax = 20, 55
    else:  # night
        vmin, vmax = 18, 30
    
    cmap = cm.get_cmap('YlOrRd')
    norm = Normalize(vmin=vmin, vmax=vmax)
    
    # Dynamic grid layout (max 3 columns) - Scalability Fix #1
    max_cols = 3
    n_cols = min(n_cities, max_cols)
    n_rows = math.ceil(n_cities / n_cols)
    
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
        """Filter places to ~1 per 75 sq km (pi * 4.87^2 ≈ 75) with max label limit
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
    
    # Plot each city
    legend_collected = False
    legend_handles = []
    legend_labels = []
    
    for idx, (city_name, city_data) in enumerate(sorted(available_cities.items())):
        row = idx // n_cols
        col = idx % n_cols
        ax = fig.add_subplot(gs[row, col])
        
        panel_letter = panel_labels[idx]
        
        print(f"\n{panel_letter}: {city_name}")
        
        lst_file = city_data.get(f'{period}_file')
        event_period = city_data.get(f'{period}_event', 'N/A')
        
        if not lst_file or not Path(lst_file).exists():
            print(f"  ⚠️  LST file not found")
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
                            print(f"  ✓ Water: {len(water_clipped)} bodies (clipped)")
                    
                    # Roads removed from visualization
                    # if 'roads' in features and not features['roads'].empty:
                    #     roads_proj = features['roads'].to_crs(lst_crs)
                    #     roads_proj.plot(ax=ax, color='grey', linewidth=0.15, 
                    #                    alpha=0.3, zorder=0.5)
                    #     print(f"  ✓ Roads: {len(roads_proj)} segments")
                    
                    # Plot Main boundary (hollow, thick black line) - clipped to LST extent
                    if 'main' in features and not features['main'].empty:
                        main_proj = features['main'].to_crs(lst_crs)
                        main_clipped = main_proj.clip(lst_extent)
                        if not main_clipped.empty:
                            main_clipped.boundary.plot(ax=ax, color='black', 
                                                   linewidth=2.5, zorder=5)
                            print(f"  ✓ Main boundary (clipped)")
                    
                    # Plot Adjacent boundaries (hollow, dashed black line) - clipped to LST extent
                    if 'adjacent' in features and not features['adjacent'].empty:
                        adj_proj = features['adjacent'].to_crs(lst_crs)
                        adj_clipped = adj_proj.clip(lst_extent)
                        if not adj_clipped.empty:
                            adj_clipped.boundary.plot(ax=ax, color='black', 
                                                  linewidth=1.5, linestyle='--', zorder=5)
                            print(f"  ✓ Adjacent boundaries: {len(adj_clipped)} (clipped)")
                    
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
                            
                            print(f"  ✓ Places: {len(places_proj)} labels (max 10)")
                
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
            print(f"  ✗ Error: {e}")
            continue
    
    # Hide empty subplots
    for idx in range(n_cities, n_rows * n_cols):
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
        print(f"✅ Saved: {png_path.name}")
        print(f"✅ Saved: {pdf_path.name}")
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
    print("\n⚠️  Note: visualize_seviri_all_cities() is deprecated.")
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
        print(f"⚠️  No {period} data available")
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
            print(f"    ⚠️  AOI directory not provided for {city_name}")
            return None, None
            
        city_aoi_dir = Path(aoi_dir) / f'City_{city_name}'
        main_file = city_aoi_dir / 'Features' / f'{city_name}_Main_Polygon.geojson'
        adjacent_file = city_aoi_dir / 'Features' / f'{city_name}_Adjacent_Polygons.geojson'
        
        main_gdf = None
        adjacent_gdf = None
        
        if main_file.exists():
            try:
                main_gdf = gpd.read_file(str(main_file))
                print(f"    ✅ Loaded main boundary for {city_name}")
            except Exception as e:
                print(f"    ⚠️  Error loading main boundary for {city_name}: {e}")
        else:
            print(f"    ⚠️  Main boundary file not found: {main_file}")
        
        if adjacent_file.exists():
            try:
                adjacent_gdf = gpd.read_file(str(adjacent_file))
                print(f"    ✅ Loaded adjacent boundaries for {city_name}")
            except Exception as e:
                print(f"    ⚠️  Error loading adjacent boundaries for {city_name}: {e}")
        
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
        
        print(f"✅ Saved: {png_path.name} + {pdf_path.name}")
    
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
        print(f"✅ Saved: {Path(output_path).name}")
    
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
    main_polygon_gdf: gpd.GeoDataFrame = None,
    adjacent_polygons_gdf: gpd.GeoDataFrame = None,
    water_gdf: gpd.GeoDataFrame = None,
    roads_gdf: gpd.GeoDataFrame = None,
    places_gdf: gpd.GeoDataFrame = None,
    place_types_filter: list = None,
    label_buffer_km: float = 2.0,
    figsize: tuple = (12, 12),
    save_path: str = None,
    dpi: int = 300
) -> plt.Figure:
    """
    Create geospatial features map for a city with all urban polygons, 
    JRC water bodies, OSM roads, and suburb places.
    
    Parameters
    ----------
    city_name : str
        Name of the city
    aoi_gdf : gpd.GeoDataFrame
        AOI boundary GeoDataFrame (used as map extent/neatline)
    main_polygon_gdf : gpd.GeoDataFrame, optional
        Main urban polygon (orange fill)
    adjacent_polygons_gdf : gpd.GeoDataFrame, optional
        Adjacent urban polygons (yellow fill)
    water_gdf : gpd.GeoDataFrame, optional
        JRC water bodies (blue fill)
    roads_gdf : gpd.GeoDataFrame, optional
        OSM roads (thin grey lines for all types)
    places_gdf : gpd.GeoDataFrame, optional
        OSM places (filtered to suburbs only, with labels)
    place_types_filter : list, optional
        Place types to display. Default: ['suburb']
    label_buffer_km : float, optional
        Minimum distance between labels in kilometers. Default: 2.0
    figsize : tuple
        Figure size (width, height)
    save_path : str, optional
        Path to save figure (will save both PNG and PDF)
    dpi : int
        Figure DPI for saving
    
    Returns
    -------
    plt.Figure
        Matplotlib figure object
    
    Notes
    -----
    - Map extent is set by AOI boundary
    - Legend includes all visible features
    - Scale bar and north arrow are added automatically
    - Saves both PNG and PDF formats
    """
    fig, ax = plt.subplots(figsize=figsize)
    
    # Ensure all data is in WGS84 for consistent plotting
    aoi_plot = aoi_gdf.to_crs('EPSG:4326')
    
    # Calculate map extent from all features instead of AOI bounds
    all_bounds = []
    
    # Collect bounds from all available features
    if main_polygon_gdf is not None and not main_polygon_gdf.empty:
        all_bounds.append(main_polygon_gdf.to_crs('EPSG:4326').total_bounds)
    if adjacent_polygons_gdf is not None and not adjacent_polygons_gdf.empty:
        all_bounds.append(adjacent_polygons_gdf.to_crs('EPSG:4326').total_bounds)
    if water_gdf is not None and not water_gdf.empty:
        all_bounds.append(water_gdf.to_crs('EPSG:4326').total_bounds)
    if roads_gdf is not None and not roads_gdf.empty:
        all_bounds.append(roads_gdf.to_crs('EPSG:4326').total_bounds)
    if places_gdf is not None and not places_gdf.empty:
        all_bounds.append(places_gdf.to_crs('EPSG:4326').total_bounds)
    
    # If no features available, fall back to AOI bounds
    if not all_bounds:
        all_bounds.append(aoi_plot.total_bounds)
    
    # Calculate combined extent from all features
    import numpy as np
    combined_bounds = np.array(all_bounds)
    extent_bounds = [
        combined_bounds[:, 0].min(),  # min x
        combined_bounds[:, 1].min(),  # min y
        combined_bounds[:, 2].max(),  # max x
        combined_bounds[:, 3].max()   # max y
    ]
    
    # Set extent exactly to feature bounds without padding
    ax.set_xlim(extent_bounds[0], extent_bounds[2])
    ax.set_ylim(extent_bounds[1], extent_bounds[3])
    
    legend_handles = []
    legend_labels = []
    
    # 1. Plot roads FIRST (thin grey lines, all road types) - lowest z-order
    if roads_gdf is not None and not roads_gdf.empty:
        roads_plot = roads_gdf.to_crs('EPSG:4326')
        roads_plot.plot(ax=ax, color='grey', linewidth=0.4, alpha=0.5, zorder=1)
        from matplotlib.lines import Line2D
        legend_handles.append(Line2D([0], [0], color='grey', linewidth=1.5, alpha=0.7))
        legend_labels.append(f' Roads ({len(roads_plot):,})')
    
    # 2. Plot adjacent polygons (yellow fill with black dashed lines)
    if adjacent_polygons_gdf is not None and not adjacent_polygons_gdf.empty:
        adj_plot = adjacent_polygons_gdf.to_crs('EPSG:4326')
        adj_plot.plot(ax=ax, facecolor='gold', alpha=0.4, edgecolor='black',
                     linewidth=2, linestyle='--', zorder=5)  # Above water, dashed black lines
        from matplotlib.patches import Patch
        legend_handles.append(Patch(facecolor='gold', edgecolor='black', 
                                   alpha=0.5, linewidth=2, linestyle='--'))
        legend_labels.append(f'Adjacent urban landscape ({len(adj_plot)})')
    
    # 3. Plot main polygon (orange fill with black solid lines)
    if main_polygon_gdf is not None and not main_polygon_gdf.empty:
        main_plot = main_polygon_gdf.to_crs('EPSG:4326')
        main_plot.plot(ax=ax, facecolor='darkorange', alpha=0.5, edgecolor='black',
                      linewidth=2, zorder=6)  # Highest z-order, solid black lines
        from matplotlib.patches import Patch
        legend_handles.append(Patch(facecolor='darkorange', edgecolor='black', 
                                   alpha=0.6, linewidth=2))
        legend_labels.append('Core urban landscape')
    
    # 4. Plot water bodies (steelblue fill with darker edge)
    if water_gdf is not None and not water_gdf.empty:
        water_plot = water_gdf.to_crs('EPSG:4326')
        water_plot.plot(ax=ax, facecolor='steelblue', alpha=0.7, edgecolor='darkblue',
                       linewidth=0.8, zorder=4)
        from matplotlib.patches import Patch
        legend_handles.append(Patch(facecolor='steelblue', edgecolor='darkblue', 
                                   alpha=0.7, linewidth=0.8))
        legend_labels.append(f'Water Bodies ({len(water_plot)})')
    
    # 5. Plot places (suburbs only, with labels)  # AOI boundary removed
    # Removed AOI boundary plotting
    from matplotlib.lines import Line2D
    # AOI legend entry removed
    # AOI legend label removed
    
    # 6. Plot places (suburbs only, with labels)
    if places_gdf is not None and not places_gdf.empty:
        places_plot = places_gdf.to_crs('EPSG:4326')
        
        # Filter to suburbs only by default
        if place_types_filter is None:
            place_types_filter = ['suburb']
        
        if 'place' in places_plot.columns:
            filtered_places = places_plot[places_plot['place'].isin(place_types_filter)].copy()
        else:
            filtered_places = places_plot.copy()
        
        if not filtered_places.empty:
            # Plot place markers
            filtered_places.plot(ax=ax, color='darkred', markersize=50, alpha=0.9,
                                marker='o', edgecolor='white', linewidth=1, zorder=7)
            
            legend_handles.append(Line2D([0], [0], marker='o', color='w', markerfacecolor='darkred',
                                        markersize=10, markeredgecolor='white', markeredgewidth=1))
            legend_labels.append(f'Suburbs ({len(filtered_places)})')
            
            # Add labels for places with names using proper spatial buffering
            name_col = 'name' if 'name' in filtered_places.columns else None
            if name_col:
                from shapely.geometry import Point
                from shapely import buffer
                import geopandas as gpd
                
                # Create proper spatial buffers for collision detection
                placed_buffer_zones = []  # Store actual geometric buffers
                successful_labels = []
                skipped_labels = []
                
                # For 1 suburb per 2 sq km, calculate buffer radius
                # Area = π * r² = 2 km²
                # r = sqrt(2/π) ≈ 0.8 km radius for 2 sq km coverage
                buffer_degrees = (label_buffer_km / 111.0) * 0.8  # Convert km to degrees (~111 km per degree)
                
                # Priority-based sorting: prioritize larger place types and longer names
                place_priority = {'city': 5, 'town': 4, 'suburb': 3, 'village': 2, 'neighbourhood': 1}
                filtered_places['priority'] = filtered_places.get('place', 'suburb').map(place_priority).fillna(3)
                filtered_places['name_length'] = filtered_places[name_col].fillna('').str.len()
                
                # Sort by priority (desc) then by name length (desc) for better label placement
                filtered_places = filtered_places.sort_values(['priority', 'name_length'], ascending=[False, False])
                
                for idx, row in filtered_places.iterrows():
                    if pd.notna(row.get(name_col)):
                        # Get centroid for labeling
                        if row.geometry.type == 'Point':
                            point = row.geometry
                        else:
                            point = row.geometry.centroid
                        
                        # Create buffer zone around potential label position
                        potential_buffer = point.buffer(buffer_degrees)
                        
                        # Check for collision with existing label buffers
                        collision = False
                        for existing_buffer in placed_buffer_zones:
                            if potential_buffer.intersects(existing_buffer):
                                collision = True
                                break
                        
                        # If no collision, place the label close to the point
                        if not collision:
                            ax.annotate(
                                row[name_col],
                                xy=(point.x, point.y),
                                xytext=(3, 3),  # Smaller offset to keep labels close to points
                                textcoords='offset points',
                                fontsize=8,  # Slightly larger for better readability
                                color='black',
                                fontweight='bold',
                                bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.8, edgecolor='none'),
                                zorder=8
                            )
                            placed_buffer_zones.append(potential_buffer)
                            successful_labels.append(row[name_col])
                        else:
                            # Skip overlapping labels - cleaner than complex repositioning
                            skipped_labels.append(row[name_col])
                
                # Report results
                total_named_places = len(filtered_places[filtered_places[name_col].notna()])
                print(f"  ✓ Placed {len(successful_labels)}/{total_named_places} labels (~1 per 2 km²)")
                if skipped_labels:
                    print(f"  ⏭️ Skipped {len(skipped_labels)} overlapping labels")
    
    # Add scale bar with standardized 1km length
    add_scale_bar(ax, length_km=1, location='lower left')
    
    # Add north arrow
    add_north_arrow(ax, location='upper right')
    
    # Calculate AOI area for title
    aoi_area_km2 = aoi_gdf.to_crs('EPSG:32632').area.sum() / 1e6
    
    # Formatting
    ax.set_title(f'{city_name} - Geospatial Features Map\nAOI Area: {aoi_area_km2:.1f} km²',
                fontsize=14, fontweight='bold', pad=15)
    ax.set_xlabel('Longitude (°E)', fontsize=11, fontweight='bold')
    ax.set_ylabel('Latitude (°N)', fontsize=11, fontweight='bold')
    
    # Create legend
    ax.legend(legend_handles, legend_labels, loc='lower right', fontsize=9, 
             framealpha=0.95, edgecolor='black', fancybox=True,
             title='Legend', title_fontsize=10)
    
    # Grid and aspect
    ax.grid(True, alpha=0.3, linestyle=':', color='gray', zorder=0)
    ax.set_aspect('equal')
    
    # Tick formatting
    ax.tick_params(axis='both', which='major', labelsize=9)
    
    plt.tight_layout()
    
    # Save figure (PNG and PDF)
    if save_path:
        save_path = Path(save_path)
        
        # Save PNG
        fig.savefig(save_path, dpi=dpi, bbox_inches='tight', facecolor='white')
        print(f"  ✓ Saved: {save_path.name}")
        
        # Save PDF
        pdf_path = save_path.with_suffix('.pdf')
        fig.savefig(pdf_path, format='pdf', bbox_inches='tight', facecolor='white')
        print(f"  ✓ Saved: {pdf_path.name}")
    
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
        Base path to save figure (will save .png and .pdf)
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
    
    panel_labels = list(string.ascii_uppercase)
    
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
    print("\n✓ Added compact North Arrow")
    
    # Save
    if save_path:
        save_path = Path(save_path)
        png_path = save_path.with_suffix('.png')
        pdf_path = save_path.with_suffix('.pdf')
        
        fig.savefig(png_path, dpi=dpi, bbox_inches='tight', facecolor='white')
        fig.savefig(pdf_path, format='pdf', bbox_inches='tight', facecolor='white')
        
        print(f"\n✓ Panel labels: A (Nigeria), B-{panel_labels[n_cities]} (Cities)")
        print("✓ Scale bars inside all map frames (bottom-left)")
        print("✓ Hollow circle in Nigeria legend")
        print("✓ Compact North Arrow")
        print(f"✓ Saved: {png_path.name}, {pdf_path.name}")
    
    return fig


# =============================================================================
# STAKEHOLDER ANALYSIS VISUALIZATIONS (Notebook 02)
# =============================================================================

def create_stakeholder_map_with_bar_chart(cities_gdf, boundary_gdf, workshop_prof, 
                                          profession_colors, survey_df, workshop_total,
                                          global_registered=None, global_attendees=None,
                                          figsize=(11.7, 5.85)):
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
    ax_map.annotate('↑', xy=(0.95, 0.91), xycoords='axes fraction',
                   fontsize=14, fontweight='bold', ha='center', va='center')
    
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
    
    ax_map.set_title('A', fontsize=10, fontweight='bold', pad=10)
    ax_map.set_xlabel('Longitude (°E)', fontsize=8)
    ax_map.set_ylabel('Latitude (°N)', fontsize=8)
    ax_map.tick_params(labelsize=7)
    ax_map.grid(True, alpha=0.2, linestyle='--', linewidth=0.5)
    ax_map.set_aspect('equal')
    
    # =========================================================================
    # RIGHT PANEL: BAR CHART + DONUT
    # =========================================================================
    
    # Prepare data for stacked horizontal bar chart
    workshop_cities = workshop_prof.groupby('city')['count'].sum().sort_values(ascending=True)
    workshop_cities = workshop_cities[workshop_cities > 0]
    
    professions_in_data = sorted(workshop_prof['profession'].unique())
    
    city_list = workshop_cities.index.tolist()
    data_matrix = pd.DataFrame(0, index=city_list, columns=professions_in_data)
    
    for _, row in workshop_prof.iterrows():
        if row['city'] in city_list:
            data_matrix.loc[row['city'], row['profession']] = row['count']
    
    # Plot stacked horizontal bars
    left = np.zeros(len(city_list))
    
    for prof in professions_in_data:
        if prof in profession_colors:
            color = profession_colors[prof]
            values = data_matrix[prof].values
            
            if values.sum() > 0:
                ax_bar.barh(city_list, values, left=left, 
                           color=color, edgecolor='white', linewidth=0.5,
                           label=prof)
                left += values
    
    ax_bar.set_xlabel('Number of Workshop Attendees', fontsize=8)
    ax_bar.set_title('B', fontsize=10, fontweight='bold', pad=10)
    ax_bar.tick_params(axis='both', labelsize=6)
    ax_bar.grid(axis='x', alpha=0.3, linestyle='--', linewidth=0.5)
    
    handles, labels = ax_bar.get_legend_handles_labels()
    ax_bar.legend(handles, labels, loc='lower right',
                 fontsize=5.5, frameon=True, facecolor='white', edgecolor='black',
                 title='Profession/Discipline (Mix)', title_fontsize=6,
                 framealpha=0.95, ncol=1)
    
    # Add value labels on bars
    for i, city in enumerate(city_list):
        total = workshop_cities[city]
        ax_bar.text(total + 0.5, i, f'{total}', 
                   va='center', ha='left', fontsize=5.5, fontweight='bold')
    
    # Overall figure title
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
    registered_cities = set(survey_df['matched_city_x'].dropna().unique())  # Cities with stakeholders
    attended_cities = set(workshop_total['city'].unique())  # Cities with workshop attendance
    
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
                      label='Ring 1: Target Status - >1 Million: 2024'),
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


def create_perception_chart_with_donuts(
    unique_resp: pd.DataFrame,
    warming_total: pd.Series,
    diurnal_total: pd.Series,
    min_participants: int = 2,
    figsize: tuple = (14, 5.5),
    legend_scale: float = 1.2
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
        'No response': '#c7c7c7'    # Light gray - no response
    }
    
    diurnal_colors = {
        'During the day': '#ff7f0e',  # Orange - daytime heat
        'At night': '#1f77b4',        # Blue - nighttime heat
        'Both': '#9467bd',            # Purple - both periods
        'No response': '#c7c7c7'      # Light gray - no response
    }
    
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
    warming_order = ['Yes', 'No', "I'm not sure", 'No response']
    warming_cols = [c for c in warming_order if c in warming_filtered.columns]
    warming_data = warming_filtered[warming_cols].fillna(0)
    
    diurnal_order = ['During the day', 'At night', 'Both', 'No response']
    diurnal_cols = [c for c in diurnal_order if c in diurnal_filtered.columns]
    diurnal_data = diurnal_filtered[diurnal_cols].fillna(0)
    
    # =========================================================================
    # MAIN FIGURE: Bar charts with embedded donuts
    # =========================================================================
    fig = plt.figure(figsize=figsize)
    gs = GridSpec(1, 2, figure=fig, width_ratios=[1, 1], wspace=0.08)
    
    # Create subplots for bars
    ax1 = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[0, 1])
    
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
    ax1.set_title('A) City Warming Over 10 Years', fontsize=11, fontweight='bold', loc='left')
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
    ax2.set_title('B) Timing of Most Severe Heat', fontsize=11, fontweight='bold', loc='left')
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
    
    # Main title
    fig.suptitle('Stakeholder Perception by City: Warming & Diurnal Heating\n(Workshop Participants, Unique Responses)',
                 fontsize=13, fontweight='bold', y=0.98)
    
    plt.tight_layout(rect=[0, 0, 1, 0.94])
    
    # =========================================================================
    # SEPARATE DONUTS FIGURE (for standalone use)
    # =========================================================================
    fig2, (ax3, ax4) = plt.subplots(1, 2, figsize=(12, 5))
    
    # Left donut: Warming
    wedges3, _, autotexts3 = ax3.pie(
        warming_vals, labels=None, colors=warming_colors_list,
        autopct=lambda p: f'{p:.1f}%' if p > 3 else '',
        pctdistance=0.75, startangle=90,
        wedgeprops=dict(width=0.5, edgecolor='white')
    )
    for autotext in autotexts3:
        autotext.set_fontsize(10)
        autotext.set_color('white')
        autotext.set_fontweight('bold')
    
    # Center text: Number bigger/bolder, "Participants" smaller and gray
    ax3.text(0, 0.06, f'{total_warming}', ha='center', va='center', 
             fontsize=18, fontweight='bold', color='black')
    ax3.text(0, -0.15, 'Participants', ha='center', va='center', 
             fontsize=9, fontweight='normal', color='#666666')
    ax3.set_title('A) Overall Warming Perception\n(Has city warmed in 10 years?)', 
                  fontsize=11, fontweight='bold')
    # Legend with response title
    ax3.legend(wedges3, warming_labels, 
               loc='center left', bbox_to_anchor=(1.0, 0.5), fontsize=9*legend_scale,
               title='Response', title_fontsize=10*legend_scale)
    
    # Right donut: Diurnal
    wedges4, _, autotexts4 = ax4.pie(
        diurnal_vals, labels=None, colors=diurnal_colors_list,
        autopct=lambda p: f'{p:.1f}%' if p > 3 else '',
        pctdistance=0.75, startangle=90,
        wedgeprops=dict(width=0.5, edgecolor='white')
    )
    for autotext in autotexts4:
        autotext.set_fontsize(10)
        autotext.set_color('white')
        autotext.set_fontweight('bold')
    
    # Center text: Number bigger/bolder, "Participants" smaller and gray
    ax4.text(0, 0.06, f'{total_diurnal}', ha='center', va='center', 
             fontsize=18, fontweight='bold', color='black')
    ax4.text(0, -0.15, 'Participants', ha='center', va='center', 
             fontsize=9, fontweight='normal', color='#666666')
    ax4.set_title('B) Overall Diurnal Heating Pattern\n(When is heat most severe?)', 
                  fontsize=11, fontweight='bold')
    # Legend with response title
    ax4.legend(wedges4, diurnal_labels,
               loc='center left', bbox_to_anchor=(1.0, 0.5), fontsize=9*legend_scale,
               title='Response', title_fontsize=10*legend_scale)
    
    fig2.suptitle('Stakeholder Perception: Overall Summaries\n(Workshop Participants, Unique Responses)',
                  fontsize=13, fontweight='bold', y=1.02)
    plt.tight_layout()
    
    print("✅ Perception charts created successfully!")
    print(f"   - Main chart with embedded donuts")
    print(f"   - Separate standalone donut chart")
    
    return fig, fig2


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
        print("⚠️  No valid data for summary chart")
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
    
    # Create figure with single subplot for grouped bars
    n_cities = len(cities)
    
    # Get dynamic layout parameters
    layout = _get_chart_layout_params(n_cities)
    figsize = layout['figsize']
    width = layout['width']
    fontsize_labels = layout['fontsize_labels']
    
    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    
    x = np.arange(n_cities)
    
    # Colors
    day_base_color = '#FFB366'  # Light orange for day base
    night_base_color = '#696969'  # Dark grey for night base
    danger_color = '#FF0000'  # Red for exceeding portion (tip)
    range_color = '#000000'  # Black for all range indicators
    
    # Process day and night data
    for i, city in enumerate(cities):
        day_val = day_means[i]
        day_min = day_mins[i]
        day_max = day_maxs[i]
        night_val = night_means[i]
        night_min = night_mins[i]
        night_max = night_maxs[i]
        
        # --- DAY BAR (left) ---
        if not np.isnan(day_val):
            # Base portion (0 to mean or full bar if below mean)
            if day_val > day_overall_mean:
                base_height = day_overall_mean
                exceed_height = day_val - day_overall_mean
            else:
                base_height = day_val
                exceed_height = 0
            
            # Plot base (orange)
            ax.bar(x[i] - width/2, base_height, width, 
                   color=day_base_color, edgecolor='black', linewidth=1,
                   label='_nolegend_')
            
            # Plot exceeding portion (red tip) if above mean
            if exceed_height > 0:
                ax.bar(x[i] - width/2, exceed_height, width, 
                       bottom=base_height, color=danger_color, 
                       edgecolor='black', linewidth=1, label='_nolegend_')
            
            # Add range indicator (min to max)
            if not np.isnan(day_min) and not np.isnan(day_max):
                ax.plot([x[i] - width/2, x[i] - width/2], [day_min, day_max],
                       color=range_color, linewidth=3, alpha=0.6, zorder=2,
                       label='_nolegend_')
                # Add caps to range
                cap_width = width * 0.3
                ax.plot([x[i] - width/2 - cap_width/2, x[i] - width/2 + cap_width/2], 
                       [day_min, day_min], color=range_color, linewidth=2, alpha=0.6,
                       label='_nolegend_')
                ax.plot([x[i] - width/2 - cap_width/2, x[i] - width/2 + cap_width/2], 
                       [day_max, day_max], color=range_color, linewidth=2, alpha=0.6,
                       label='_nolegend_')
            
            # Add value label at center of bar
            ax.text(x[i] - width/2, day_val / 2, f'{day_val:.1f}',
                   ha='center', va='center', fontsize=fontsize_labels, fontweight='bold',
                   color='white', bbox=dict(boxstyle='round,pad=0.3', facecolor='black', alpha=0.7))
        
        # --- NIGHT BAR (right) ---
        if not np.isnan(night_val):
            # Base portion (0 to mean or full bar if below mean)
            if night_val > night_overall_mean:
                base_height = night_overall_mean
                exceed_height = night_val - night_overall_mean
            else:
                base_height = night_val
                exceed_height = 0
            
            # Plot base (dark grey)
            ax.bar(x[i] + width/2, base_height, width,
                   color=night_base_color, edgecolor='black', linewidth=1,
                   label='_nolegend_')
            
            # Plot exceeding portion (red tip) if above mean
            if exceed_height > 0:
                ax.bar(x[i] + width/2, exceed_height, width,
                       bottom=base_height, color=danger_color,
                       edgecolor='black', linewidth=1, label='_nolegend_')
            
            # Add range indicator (min to max)
            if not np.isnan(night_min) and not np.isnan(night_max):
                ax.plot([x[i] + width/2, x[i] + width/2], [night_min, night_max],
                       color=range_color, linewidth=3, alpha=0.6, zorder=2,
                       label='_nolegend_')
                # Add caps to range
                cap_width = width * 0.3
                ax.plot([x[i] + width/2 - cap_width/2, x[i] + width/2 + cap_width/2], 
                       [night_min, night_min], color=range_color, linewidth=2, alpha=0.6,
                       label='_nolegend_')
                ax.plot([x[i] + width/2 - cap_width/2, x[i] + width/2 + cap_width/2], 
                       [night_max, night_max], color=range_color, linewidth=2, alpha=0.6,
                       label='_nolegend_')
            
            # Add value label at center of bar
            ax.text(x[i] + width/2, night_val / 2, f'{night_val:.1f}',
                   ha='center', va='center', fontsize=fontsize_labels, fontweight='bold',
                   color='white', bbox=dict(boxstyle='round,pad=0.3', facecolor='black', alpha=0.7))
    
    # Add mean lines with labels on the lines
    if not np.isnan(day_overall_mean):
        ax.axhline(day_overall_mean, color='darkorange', linestyle='--', 
                   linewidth=2.5, alpha=0.8, zorder=3)
        # Add label on the line (positioned at right edge, avoiding overlap)
        ax.text(n_cities - 0.3, day_overall_mean + 0.3, f'Day Mean: {day_overall_mean:.1f}°C',
               fontsize=9, fontweight='bold', color='darkorange', 
               bbox=dict(boxstyle='round,pad=0.4', facecolor='white', edgecolor='darkorange', alpha=0.9),
               ha='right', va='bottom')
    
    if not np.isnan(night_overall_mean):
        ax.axhline(night_overall_mean, color='dimgray', linestyle='--',
                   linewidth=2.5, alpha=0.8, zorder=3)
        # Add label on the line (positioned at left edge, avoiding overlap)
        ax.text(0.3, night_overall_mean + 0.3, f'Night Mean: {night_overall_mean:.1f}°C',
               fontsize=9, fontweight='bold', color='dimgray',
               bbox=dict(boxstyle='round,pad=0.4', facecolor='white', edgecolor='dimgray', alpha=0.9),
               ha='left', va='bottom')
    
    # Add vertical separator lines between cities
    for i in range(1, n_cities):
        ax.axvline(x[i] - 0.5, color='lightgrey', linestyle='-', linewidth=1, alpha=0.3, zorder=0)
    
    # Formatting
    ax.set_xlabel('Cities', fontsize=13, fontweight='bold')
    ax.set_ylabel('Mean LST (°C)', fontsize=13, fontweight='bold')
    ax.set_title(f'Persistent Heat Event Comparison: Day vs Night - {study_year}\n' +
                 f'Red tips indicate temperatures exceeding overall mean (Danger Zone)',
                 fontsize=14, fontweight='bold', pad=20)
    ax.set_xticks(x)
    ax.set_xticklabels(cities, rotation=45, ha='right', fontsize=10)
    ax.grid(axis='y', alpha=0.3, linestyle='--', zorder=0)
    
    # Create custom legend (simplified - no mean values)
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D
    
    legend_elements = [
        Patch(facecolor=day_base_color, edgecolor='black', label='Day Base'),
        Patch(facecolor=night_base_color, edgecolor='black', label='Night Base'),
        Patch(facecolor=danger_color, edgecolor='black', label='Excess Above Mean (Red Tip)'),
        Line2D([0], [0], color=range_color, linewidth=4, alpha=0.6, label='Range (Min-Max)'),
    ]
    
    # Position legend at bottom right
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
        
        print(f"✅ Saved: {png_path.name}")
        print(f"✅ Saved: {pdf_path.name}")
        print(f"{'='*80}\n")
    
    return fig


def _get_chart_layout_params(n_cities):
    """
    Get dynamic layout parameters based on number of cities.
    
    Helper function to maintain consistent sizing across heat event charts.
    
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
        return {'figsize': (14, 7), 'width': 0.38, 'fontsize_labels': 8}
    elif n_cities <= 20:
        return {'figsize': (18, 7), 'width': 0.35, 'fontsize_labels': 7}
    elif n_cities <= 30:
        return {'figsize': (24, 7), 'width': 0.32, 'fontsize_labels': 6}
    else:  # Up to 50+ cities
        return {'figsize': (32, 7), 'width': 0.28, 'fontsize_labels': 5}


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
        print("⚠️  No valid data for SD variability chart")
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
    
    x = np.arange(n_cities)
    
    # Colors (consistent with summary chart)
    day_base_color = '#FFB366'  # Light orange for day
    night_base_color = '#696969'  # Dark grey for night
    high_var_color = '#FF0000'  # Red for high variability
    
    # Plot bars
    for i, city in enumerate(cities):
        day_sd = day_stds[i]
        night_sd = night_stds[i]
        
        # --- DAY BAR (left) ---
        if not np.isnan(day_sd):
            # Base bar (from 0 to mean_std or full height if below mean)
            base_height = min(day_sd, day_mean_std)
            ax.bar(x[i] - width/2, base_height, width, 
                   color=day_base_color, edgecolor='black', linewidth=1)
            
            # Red tip only if SD exceeds mean SD
            if day_sd > day_mean_std:
                tip_height = day_sd - day_mean_std
                ax.bar(x[i] - width/2, tip_height, width, 
                       bottom=day_mean_std, color=high_var_color, 
                       edgecolor='black', linewidth=1)
            
            # Add value label
            ax.text(x[i] - width/2, day_sd / 2, f'{day_sd:.2f}',
                   ha='center', va='center', fontsize=fontsize_labels, fontweight='bold',
                   color='white', bbox=dict(boxstyle='round,pad=0.3', facecolor='black', alpha=0.7))
        
        # --- NIGHT BAR (right) ---
        if not np.isnan(night_sd):
            # Base bar (from 0 to mean_std or full height if below mean)
            base_height = min(night_sd, night_mean_std)
            ax.bar(x[i] + width/2, base_height, width,
                   color=night_base_color, edgecolor='black', linewidth=1)
            
            # Red tip only if SD exceeds mean SD
            if night_sd > night_mean_std:
                tip_height = night_sd - night_mean_std
                ax.bar(x[i] + width/2, tip_height, width,
                       bottom=night_mean_std, color=high_var_color,
                       edgecolor='black', linewidth=1)
            
            # Add value label
            ax.text(x[i] + width/2, night_sd / 2, f'{night_sd:.2f}',
                   ha='center', va='center', fontsize=fontsize_labels, fontweight='bold',
                   color='white', bbox=dict(boxstyle='round,pad=0.3', facecolor='black', alpha=0.7))
    
    # Add mean SD lines with labels
    if not np.isnan(day_mean_std):
        ax.axhline(day_mean_std, color='darkorange', linestyle='--', 
                   linewidth=2.5, alpha=0.8, zorder=3)
        ax.text(n_cities - 0.3, day_mean_std + 0.05, f'Day Mean SD: {day_mean_std:.2f}°C',
               fontsize=9, fontweight='bold', color='darkorange', 
               bbox=dict(boxstyle='round,pad=0.4', facecolor='white', edgecolor='darkorange', alpha=0.9),
               ha='right', va='bottom')
    
    if not np.isnan(night_mean_std):
        ax.axhline(night_mean_std, color='dimgray', linestyle='--',
                   linewidth=2.5, alpha=0.8, zorder=3)
        ax.text(0.3, night_mean_std + 0.05, f'Night Mean SD: {night_mean_std:.2f}°C',
               fontsize=9, fontweight='bold', color='dimgray',
               bbox=dict(boxstyle='round,pad=0.4', facecolor='white', edgecolor='dimgray', alpha=0.9),
               ha='left', va='bottom')
    
    # Add vertical separators
    for i in range(1, n_cities):
        ax.axvline(x[i] - 0.5, color='lightgrey', linestyle='-', linewidth=1, alpha=0.3, zorder=0)
    
    # Formatting
    ax.set_xlabel('Cities', fontsize=13, fontweight='bold')
    ax.set_ylabel('Standard Deviation (°C)', fontsize=13, fontweight='bold')
    ax.set_title(f'Temperature Variability During Persistent Heat Events - {study_year}\n' +
                 f'Red tips indicate cities with high temperature variability (SD > Mean SD)',
                 fontsize=14, fontweight='bold', pad=20)
    ax.set_xticks(x)
    ax.set_xticklabels(cities, rotation=45, ha='right', fontsize=10)
    ax.grid(axis='y', alpha=0.3, linestyle='--', zorder=0)
    
    # Legend
    legend_elements = [
        Patch(facecolor=day_base_color, edgecolor='black', label='Day Normal Variability'),
        Patch(facecolor=night_base_color, edgecolor='black', label='Night Normal Variability'),
        Patch(facecolor=high_var_color, edgecolor='black', label='High Variability Tip (SD > Mean SD)'),
    ]
    
    ax.legend(handles=legend_elements, loc='upper right', fontsize=9, 
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
        
        print(f"✅ Saved: {png_path.name}")
        print(f"✅ Saved: {pdf_path.name}")
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
        
        print(f"✅ Saved: {png_path.name}")
        print(f"✅ Saved: {pdf_path.name}")
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
    
    # Define expected output files
    pdf_path = output_dir / f'{city_name}_hotspot_grid_1x3.pdf'
    png_path = output_dir / f'{city_name}_hotspot_grid_1x3.png'
    legend_pdf = output_dir / f'{city_name}_legend.pdf'
    legend_png = output_dir / f'{city_name}_legend.png'
    tracking_file = output_dir / f'{city_name}_map_params.json'
    
    # =============================================================================
    # SKIP LOGIC: Check if maps exist and parameters match
    # =============================================================================
    
    if skip_if_exists and pdf_path.exists() and png_path.exists():
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
                        'png': png_path,
                        'legend_pdf': legend_pdf,
                        'legend_png': legend_png,
                        'skipped': True,
                        'reason': f'Maps exist and AOI unchanged (area change: {area_change_pct:.2f}%)',
                        'success': True
                    }
            except Exception as e:
                # If we can't check parameters, regenerate to be safe
                pass
    
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
        print(f"✗ Error loading boundaries for {city_name}: {e}")
        return None
    
    # Load OSM features
    try:
        osm_roads = gpd.read_file(osm_dir / f'{city_name}_roads.geojson')
        osm_water = gpd.read_file(osm_dir / f'{city_name}_water_bodies.geojson')
    except Exception:
        osm_roads = gpd.GeoDataFrame()
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
    
    plt.savefig(pdf_path, dpi=300, bbox_inches='tight')
    plt.savefig(png_path, dpi=300, bbox_inches='tight')
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
    
    legend_fig.savefig(legend_pdf, dpi=300, bbox_inches='tight')
    legend_fig.savefig(legend_png, dpi=300, bbox_inches='tight')
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
        'png': png_path, 
        'legend_pdf': legend_pdf, 
        'legend_png': legend_png, 
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
    
    # Define expected output files
    pdf_path = output_dir / f'{city_name}_gi_star_distributions.pdf'
    png_path = output_dir / f'{city_name}_gi_star_distributions.png'
    
    # =============================================================================
    # SKIP LOGIC: Check if plots exist
    # =============================================================================
    
    if skip_if_exists and pdf_path.exists() and png_path.exists():
        return {
            'city': city_name,
            'pdf': pdf_path,
            'png': png_path,
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
        print(f"✗ Hotspot results not found for {city_name}")
        return None
    
    # Only Day and Night (Persistent has no LST data)
    periods = ['day', 'night']
    period_labels = ['Day', 'Night']
    
    # Check if required periods have data
    city_data = hotspot_results[city_name]
    if not all(period in city_data for period in periods):
        print(f"✗ Missing period data for {city_name}")
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
    
    plt.savefig(pdf_path, dpi=300, bbox_inches='tight')
    plt.savefig(png_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    return {
        'city': city_name,
        'pdf': pdf_path,
        'png': png_path,
        'skipped': False,
        'success': True
    }


def create_hotspot_area_by_contour_plots(hotspot_polygons_enriched, landscape_gdf_4326,
                                         output_dir: Path, skip_if_exists: bool = True):
    """
    Create grouped stacked bar charts showing hotspot area distribution by contour level,
    stacked by Cluster25 landscape classes. NO CONFIRMED method (only P90 and GI_STAR).
    
    Visualization:
    - 3 facets (Day, Night, Persistent)
    - Per city: 6 bars (2 methods × 3 contours)
      - P90: [90%] [75%] [50%]
      - Gi*: [90%] [75%] [50%]
    - Each bar stacked by 25 unique Cluster25 colors
    - Patch count annotated at top of each bar
    - NO LEGEND - colors shown in Table 2
    
    Args:
        hotspot_polygons_enriched: GeoDataFrame with city, method, period, contour_level, Cluster25, area_km2
        landscape_gdf_4326: GeoDataFrame with Cluster25 classification details
        output_dir: Directory to save plots (figures/)
        skip_if_exists: Skip if outputs already exist
    
    Returns:
        dict with paths to saved files
    """
    from matplotlib.patches import Patch
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
    
    # Define output paths
    pdf_path = output_dir / 'hotspot_area_by_contour_cluster25.pdf'
    png_path = output_dir / 'hotspot_area_by_contour_cluster25.png'
    table1_path = output_dir / 'table1_hotspot_characterization.csv'
    table2_path = output_dir / 'table2_cluster25_colors.csv'
    
    # Check if outputs exist
    if skip_if_exists and all(p.exists() for p in [pdf_path, png_path, table1_path, table2_path]):
        print(f"✓ Plots already exist, skipping")
        return {
            'pdf': pdf_path,
            'png': png_path,
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
        print(f"✗ No data for P90 or GI_STAR methods")
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
    # CREATE FIGURE - Single chart, 3 row panels (Day, Night, Persistent)
    # X-axis hierarchy: City (top) > Method > Contour (bar base)
    # Y-axis: Period label + shared Total Area scale
    # Vertical dividers between cities; dashed dividers between methods
    # Compact sizing, no vertical gaps between panels
    # =============================================================================
    
    n_cities = len(cities)
    n_methods = len(methods)
    n_contours = len(contour_levels)
    bars_per_method = n_contours                   # 3
    bars_per_city = n_methods * n_contours          # 6
    
    # --- x-position geometry (compact) -----------------------------------------
    bar_w = 0.38                     # narrower bars
    intra_gap = 0.04                 # minimal gap between contour bars
    inter_gap = bar_w * 0.45         # visible gap between P90 and Gi* groups
    city_gap = bar_w * 1.4           # gap between cities
    
    # Build x-positions and collect label / divider metadata
    x_positions = []
    contour_labels_x = []
    method_labels_x = []
    city_labels_x = []
    city_dividers = []     # solid lines between cities
    method_dividers = []   # dashed lines between methods within a city
    
    cursor = 0.0
    for ci, city in enumerate(cities):
        city_start = cursor
        for mi, method in enumerate(methods):
            method_start = cursor
            for coi, contour in enumerate(contour_levels):
                x_positions.append(cursor)
                pct = int(contour * 100)
                contour_labels_x.append((cursor, f'{pct}%'))
                cursor += bar_w + intra_gap
            cursor -= intra_gap  # remove trailing intra-gap
            method_center = (method_start + cursor) / 2
            method_label = 'P90' if method == 'P90' else 'Gi*'
            method_labels_x.append((method_center, method_label))
            if mi < n_methods - 1:
                # dashed divider between methods (placed in the inter_gap)
                method_dividers.append(cursor + inter_gap / 2)
            cursor += inter_gap
        cursor -= inter_gap  # remove trailing inter-gap
        city_center = (city_start + cursor) / 2
        city_labels_x.append((city_center, city))
        cursor += city_gap
        if ci < n_cities - 1:
            city_dividers.append(cursor - city_gap / 2)
    
    total_width = cursor - city_gap
    
    # Display order: Day (top), Night (middle), Persistent (bottom)
    display_order = [p for p in ['Day', 'Night', 'Persistent'] if p in periods]
    for p in periods:
        if p not in display_order:
            display_order.append(p)
    n_panels = len(display_order)
    
    # --- Compact figure sizing -------------------------------------------------
    fig_w = max(10, total_width * 0.85 + 1.5)
    panel_h = max(2.5, fig_w * 0.14)
    fig_h = panel_h * n_panels + 1.8  # tight: panels + title + x-labels
    
    fig, axes = plt.subplots(n_panels, 1, figsize=(fig_w, fig_h),
                             sharex=True, sharey=True)
    if n_panels == 1:
        axes = [axes]
    
    # Eliminate vertical space between panels
    fig.subplots_adjust(hspace=0)
    
    fig.suptitle('Hotspot Area Distribution by Contour Level & Landscape Character (Cluster25)',
                 fontsize=13, fontweight='bold', y=0.97)
    
    # --- Draw each panel -------------------------------------------------------
    for ax_idx, ax in enumerate(axes):
        if ax_idx >= len(display_order):
            ax.set_visible(False)
            continue
        
        period = display_order[ax_idx]
        
        # Get data for this period
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
        for ci, city in enumerate(cities):
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
        
        # y-limits before annotating
        ax.autoscale(axis='y')
        y_lo, y_hi = ax.get_ylim()
        nudge = y_hi * 0.018 if y_hi > 0 else 0.3
        
        # Patch-count annotations
        bar_idx = 0
        for ci, city in enumerate(cities):
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
        
        # Black baseline at y = 0
        ax.axhline(0, color='black', linewidth=0.8, zorder=2)
        
        # City dividers (solid)
        for xd in city_dividers:
            ax.axvline(xd, color='#666666', linewidth=0.9, linestyle='-', alpha=0.6, zorder=0)
        
        # Method dividers (dashed, lighter)
        for xd in method_dividers:
            ax.axvline(xd, color='#aaaaaa', linewidth=0.6, linestyle='--', alpha=0.5, zorder=0)
        
        # Remove x-tick labels on non-bottom panels; keep shared spine
        if ax_idx < n_panels - 1:
            ax.tick_params(axis='x', labelbottom=False, length=0)
        
        # Remove inner spines so panels look seamless
        if ax_idx > 0:
            ax.spines['top'].set_visible(False)
        if ax_idx < n_panels - 1:
            ax.spines['bottom'].set_visible(False)
    
    # --- X-axis label hierarchy (bottom panel only) ----------------------------
    bottom_ax = axes[-1]
    
    # Level 1 (closest to bars): Contour % labels
    bottom_ax.set_xticks([pos for pos, _ in contour_labels_x])
    bottom_ax.set_xticklabels([lbl for _, lbl in contour_labels_x],
                               fontsize=9, rotation=0)
    bottom_ax.tick_params(axis='x', which='major', pad=2, length=3)
    
    # Level 2: Method labels
    for mx, mlbl in method_labels_x:
        bottom_ax.text(mx, -0.10, mlbl,
                      ha='center', va='top', fontsize=10, fontweight='bold',
                      transform=bottom_ax.get_xaxis_transform())
    
    # Level 3: City labels
    for cx, clbl in city_labels_x:
        bottom_ax.text(cx, -0.20, clbl,
                      ha='center', va='top', fontsize=11, fontweight='bold',
                      transform=bottom_ax.get_xaxis_transform())
    
    plt.tight_layout(rect=[0, 0.07, 1, 0.95])
    fig.subplots_adjust(hspace=0)  # re-enforce after tight_layout
    
    # =============================================================================
    # SAVE PLOT
    # =============================================================================
    
    plt.savefig(pdf_path, dpi=300, bbox_inches='tight')
    plt.savefig(png_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"✓ Saved hotspot area plots: {pdf_path.name}")
    
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
    print(f"✓ Saved Table 1: {table1_path.name}")
    
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
    print(f"✓ Saved Table 2: {table2_path.name}")
    
    return {
        'pdf': pdf_path,
        'png': png_path,
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

    Each city gets its own figure (PDF + PNG).  The semicircle faces
    upward; the flat cut edge faces down.  Day occupies the left
    half-ring, Night the right half-ring.

    Rings (inside → outside):
        Ring 1 (inner)  : Period  — Day (left) / Night (right)
        Ring 2 (middle) : Method  — P90 / Gi*
        Ring 3 (outer)  : Contour — 90 % / 75 % / 50 %

    Design:
      • Day ☀ / Night ☾ headers placed at the base (below the flat edge)
      • Labels on each side connected by leader lines FROM the segment
        midpoint TO the label position
      • Leader lines are coloured to match their segment, with small
        filled circles at both endpoints
      • Robust overlap resolution keeps labels well-separated
      • Zero-population segments are omitted

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

    # ── data prep ─────────────────────────────────────────────────────────
    df = (
        hotspot_polygons_enriched
        .loc[
            hotspot_polygons_enriched['method'].isin(['P90', 'GI_STAR'])
            & hotspot_polygons_enriched['period'].isin(['Day', 'Night'])
        ]
        .copy()
    )

    if df.empty:
        print("✗ No data matching filter (P90/GI_STAR × Day/Night)")
        return {'skipped': False, 'success': False}

    cities = sorted(df['city'].unique())

    # Check skip
    all_exist = True
    for city in cities:
        slug = city.lower().replace(' ', '_')
        pdf_p = output_dir / f'population_exposure_donut_{slug}.pdf'
        png_p = output_dir / f'population_exposure_donut_{slug}.png'
        if not (pdf_p.exists() and png_p.exists()):
            all_exist = False
            break

    if skip_if_exists and all_exist:
        print("✓ All per-city donut charts already exist, skipping")
        return {'skipped': True, 'success': True, 'cities': cities}

    # ── colour palette ────────────────────────────────────────────────────
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

    # ── ring geometry ─────────────────────────────────────────────────────
    r_inner = {1: 0.42, 2: 0.72, 3: 1.02}
    r_width = {1: 0.27, 2: 0.27, 3: 0.24}
    outer_max = r_inner[3] + r_width[3]  # 1.26

    # ── helpers ───────────────────────────────────────────────────────────
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

        # ── figure ────────────────────────────────────────────────────
        fig, ax = plt.subplots(
            figsize=(10.0, 6.0),
            subplot_kw=dict(aspect='equal'),
        )

        # Collect label specs per side
        label_specs = []

        # ── compute proportional angular spans for Day vs Night ───────
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

            # ── Ring 1: Period band ───────────────────────────────────
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

            # ── Ring 2: Method bands ──────────────────────────────────
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

                # ── Ring 3: Contour bands ─────────────────────────────
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

        # ── label segments directly at their midpoints ──────────────
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

        # ── vertical overlap prevention per side ──────────────────────
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

        # ── draw dots + labels ────────────────────────────────────────
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

        # ── centre annotation ─────────────────────────────────────────
        city_total = int(city_df['pop_total'].sum())
        ax.text(0, 0.22, city, ha='center', va='center',
                fontsize=16, fontweight='bold', color='#1a1a1a')
        ax.text(0, 0.04, _fmt_pop(city_total), ha='center', va='center',
                fontsize=18, color='#222222', fontweight='bold')
        ax.text(0, -0.09, 'persons exposed', ha='center', va='center',
                fontsize=8.5, color='#888888', style='italic')

        # ── "Day" / "Night" at the BASE (below flat edge) ────────────
        base_y = -0.22
        ax.text(-0.55, base_y, 'Day', ha='center', va='top',
                fontsize=12, fontweight='bold', color=day_dark)
        ax.text(0.55, base_y, 'Night', ha='center', va='top',
                fontsize=12, fontweight='bold', color=night_dark)
        # Thin separator line on the flat edge
        ax.plot([-outer_max, outer_max], [0, 0],
                color='#cccccc', lw=0.6, zorder=1)

        # ── ring-name labels on the flat edge (at y=0) ────────────────
        # Place ring names along the bottom baseline so they don't
        # overlap segment labels at the top of the arc.
        for ring_id, ring_name in [(1, 'Period'), (2, 'Method'), (3, 'Contour')]:
            mid_r = r_inner[ring_id] + r_width[ring_id] / 2
            ax.text(mid_r, -0.04, ring_name, ha='center', va='top',
                    fontsize=6.5, color='#777777', style='italic')

        # ── title ─────────────────────────────────────────────────────
        ax.set_title(
            f'Population Exposed to UHI Hotspots — {city}',
            fontsize=13, fontweight='bold', pad=18, color='#1a1a1a',
        )

        # ── axis limits ───────────────────────────────────────────────
        margin = 0.65
        ax.set_xlim(-(outer_max + margin), outer_max + margin)
        ax.set_ylim(-0.55, outer_max + 0.55)
        ax.set_axis_off()

        fig.tight_layout()

        # ── save per-city ─────────────────────────────────────────────
        slug = city.lower().replace(' ', '_')
        pdf_path = output_dir / f'population_exposure_donut_{slug}.pdf'
        png_path = output_dir / f'population_exposure_donut_{slug}.png'
        fig.savefig(pdf_path, format='pdf', dpi=300, bbox_inches='tight')
        fig.savefig(png_path, format='png', dpi=300, bbox_inches='tight')
        plt.close(fig)
        print(f"  ✓ {city}: {pdf_path.name} / {png_path.name}")
        saved_paths[city] = {'pdf': pdf_path, 'png': png_path}

    return {
        'cities': saved_paths,
        'skipped': False,
        'success': True,
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
        
        # Day wedge (proportional)
        if day_pop > 0:
            ax.add_patch(Wedge((lon, lat), radius_deg, day_start, day_end,
                               facecolor=day_color, edgecolor='white',
                               linewidth=2, alpha=0.9, zorder=5))
        
        # Night wedge (proportional)
        if night_pop > 0:
            ax.add_patch(Wedge((lon, lat), radius_deg, night_start, night_end,
                               facecolor=night_color, edgecolor='white',
                               linewidth=2, alpha=0.9, zorder=5))
        
        # City centroid as black dot
        ax.plot(lon, lat, 'ko', markersize=4, zorder=7)
        
        # City name with population in parentheses below
        label_text = f"{city}\n({format_population(total_pop)})"
        ax.text(lon, lat - radius_deg - 0.15, label_text, ha='center', va='top',
                fontsize=9, fontweight='bold', color='#000', zorder=6, linespacing=0.9)
    
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
─────────────────
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
    # Scale bar at bottom center (100 km ≈ 0.9 degrees at equator)
    # -------------------------------------------------------------------------
    
    scale_center_lon = (bounds[0] + bounds[2]) / 2
    scale_half_deg = 0.45  # 0.9 degrees total ≈ 100 km
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
    
    output_path_png = maps_dir / 'national_summary_map_cluster25.png'
    output_path_pdf = maps_dir / 'national_summary_map_cluster25.pdf'
    
    fig.savefig(output_path_png, dpi=300, bbox_inches='tight')
    fig.savefig(output_path_pdf, format='pdf', bbox_inches='tight')
    
    print(f"✓ Saved: {output_path_png.name} | {output_path_pdf.name}")
    
    if show_plot:
        plt.show()
    else:
        plt.close(fig)
    
    return {
        'png_path': output_path_png,
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


# ─────────────────────────────────────────────────────────────────────────────
# Cluster25 helpers — city-based assignment (captures ALL workshop stakeholders)
# ─────────────────────────────────────────────────────────────────────────────


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


# ─────────────────────────────────────────────────────────────────────────────
# Chart 1: Reasons for Heating vs. Mitigation by Cluster25
# ─────────────────────────────────────────────────────────────────────────────

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

    # ── assign Cluster25 via city (all stakeholders) ─────────────────────
    workshop, cluster_meta = _assign_cluster25_via_city(survey_df, landscape_gdf)

    # ── city → Cluster25 reverse map (for textbox) ───────────────────────
    _city_cl = (
        workshop.drop_duplicates('matched_city_y')
        .set_index('matched_city_y')['Cluster25']
        .to_dict()
    )
    cl_to_cities: Dict[int, list] = {}
    for _city, _cid in _city_cl.items():
        cl_to_cities.setdefault(int(_cid), []).append(_city)

    # ── deduplicate: one response per PID per Cluster25 ──────────────────
    reason_col = '74_reason_hotspots'
    mitig_col = '94_temp_mitigation_solution'

    reason_data = workshop[workshop[reason_col].notna()].drop_duplicates(
        subset=['pid', 'Cluster25']
    )
    mitig_data = workshop[workshop[mitig_col].notna()].drop_duplicates(
        subset=['pid', 'Cluster25']
    )

    # ── cross-tabulate ───────────────────────────────────────────────────
    reason_ct = pd.crosstab(reason_data['Cluster25'], reason_data[reason_col])
    mitig_ct = pd.crosstab(mitig_data['Cluster25'], mitig_data[mitig_col])

    # Stakeholders per Cluster25
    n_reason = reason_data.groupby('Cluster25')['pid'].nunique()
    n_mitig = mitig_data.groupby('Cluster25')['pid'].nunique()

    # ── short column names for display ───────────────────────────────────
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

    # ── colour palettes ──────────────────────────────────────────────────
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

    # ── totals for subtitle ──────────────────────────────────────────────
    total_reason_stk = reason_data['pid'].nunique()
    total_mitig_stk = mitig_data['pid'].nunique()
    total_stakeholders = workshop.drop_duplicates('pid')['pid'].nunique()
    n_cities_workshop = workshop['matched_city_y'].nunique()

    # ── PLOT ─────────────────────────────────────────────────────────────
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

    # ── textbox: cities per cluster ──────────────────────────────────────
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

    # ── save ─────────────────────────────────────────────────────────────
    png_path = maps_dir / 'reasons_mitigation_by_cluster25.png'
    pdf_path = maps_dir / 'reasons_mitigation_by_cluster25.pdf'
    fig.savefig(png_path, dpi=300, bbox_inches='tight')
    fig.savefig(pdf_path, format='pdf', bbox_inches='tight')
    print(f"✓ Saved: {png_path.name} | {pdf_path.name}")

    if show_plot:
        plt.show()
    else:
        plt.close(fig)

    return {
        'png_path': png_path,
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


# ─────────────────────────────────────────────────────────────────────────────
# Chart 2: Tree Species Heatmap (Cluster25 or City)
# ─────────────────────────────────────────────────────────────────────────────

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

    # ── assign Cluster25 via city ────────────────────────────────────────
    workshop, cluster_meta = _assign_cluster25_via_city(survey_df, landscape_gdf)

    # ── filter to tree-species rows ──────────────────────────────────────
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

    # ── deduplicate: one entry per PID × species × group ─────────────────
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

    # ── cross-tabulate ───────────────────────────────────────────────────
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

    # ── dynamic figsize (tight: cell height ≈ 0.35 in) ─────────────────
    if figsize is None:
        n_rows = len(selected_species)
        n_cols = ct.shape[1]
        if group_by == 'city':
            figsize = (max(16, n_cols * 0.60 + 3), max(6, n_rows * 0.35 + 2.5))
        else:
            figsize = (max(10, n_cols * 1.1 + 3), max(6, n_rows * 0.35 + 2.5))

    # ── totals ───────────────────────────────────────────────────────────
    total_stakeholders = tree_data['pid'].nunique()
    n_cities = tree_data['matched_city_y'].nunique()
    n_display = len(selected_species)

    # ── light-green → dark-green colour map ──────────────────────────────
    green_cmap = LinearSegmentedColormap.from_list(
        'light_dark_green',
        ['#f0f9e8', '#bae4bc', '#7bccc4', '#43a2ca', '#0b6623'],
        N=256,
    )

    # ── PLOT ─────────────────────────────────────────────────────────────
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

    # ── save ─────────────────────────────────────────────────────────────
    png_path = maps_dir / f'{fname_stem}.png'
    pdf_path = maps_dir / f'{fname_stem}.pdf'
    fig.savefig(png_path, dpi=300, bbox_inches='tight')
    fig.savefig(pdf_path, format='pdf', bbox_inches='tight')
    print(f"✓ Saved: {png_path.name} | {pdf_path.name}")

    if show_plot:
        plt.show()
    else:
        plt.close(fig)

    return {
        'png_path': png_path,
        'pdf_path': pdf_path,
        'n_stakeholders': total_stakeholders,
        'n_cities': n_cities,
        'n_species': n_display,
        'n_groups': ct.shape[1],
        'total_mentions': int(ct.values.sum()),
        'success': True,
    }