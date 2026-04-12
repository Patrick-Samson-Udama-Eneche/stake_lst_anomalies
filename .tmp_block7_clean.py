print("="*70)
print("BLOCK 7: LST TREND ANALYSIS - IMPROVED VISUALIZATION")
print("="*70)

# Define the figure size for 1x2 plots (side by side layout with shared y-axis)
FIGURE_SIZE = (18, 9)  # Larger figure for better readability
DPI = 300

# Define colors using proper matplotlib RGBA format
DAY_COLOR = '#FF7F0E'  # Orange for day
DAY_FILL = (1.0, 0.5, 0.055, 0.3)  # Lighter orange with alpha=0.3
NIGHT_COLOR = '#000000'  # Black for night line and markers
NIGHT_FILL = (0.5, 0.5, 0.5, 0.3)  # Grey with alpha=0.3 for night shaded area

# Month abbreviations
MONTH_ABBRS = {
    1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun',
    7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'
}

# Import helper functions from src (previously defined inline)
from src.visualization import find_safe_text_position, place_trend_box_safely, place_monthly_stats_box_safely

# --- Skip logic: check if all expected trend plot outputs already exist ---
_skip_trends = config.SKIP_EXISTING.get('trend_plots', False)
_trends_all_exist = False

if _skip_trends:
    _trends_all_exist = True
    _legend_svg = os.path.join(PROJECT_CONFIG['lst_output_dir'], 'Stats', 'LST_Trend_Plot_Legend.svg')
    _legend_pdf = os.path.join(PROJECT_CONFIG['lst_output_dir'], 'Stats', 'LST_Trend_Plot_Legend.pdf')
    if not (os.path.exists(_legend_svg) and os.path.exists(_legend_pdf)):
        _trends_all_exist = False
    else:
        for _cn in aoi_data:
            _fdir = os.path.join(PROJECT_CONFIG['lst_output_dir'], f'City_{_cn}',
                                 'LST_Temporal_Analysis', 'Figures')
            _exp_svg = os.path.join(_fdir, f"{_cn}_LST_Trends_Combined2.svg")
            _exp_pdf = os.path.join(_fdir, f"{_cn}_LST_Trends_Combined2.pdf")
            if not (os.path.exists(_exp_svg) and os.path.exists(_exp_pdf)):
                _trends_all_exist = False
                break

if _skip_trends and _trends_all_exist:
    print("⏭️  SKIPPED — all LST trend plot outputs already exist.")
    print("   Set config.SKIP_EXISTING['trend_plots'] = False to regenerate.")
else:
    try:
        # Set non-interactive matplotlib backend to avoid parallel execution errors
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.ticker as ticker  # For integer years formatting
        
        print("\n📊 Generating improved LST trend line plots for each city...")
        
        # Load the statistics file from Stats folder
        stats_file = os.path.join(PROJECT_CONFIG['lst_output_dir'], 'Stats', 'All_Cities_LST_Statistics.csv')
        
        if os.path.exists(stats_file):
            all_stats_df = pd.read_csv(stats_file)
            print(f"✅ Loaded statistics from: {stats_file}")
        else:
            # Try alternative locations
            alt_stats_files = [
                os.path.join(PROJECT_CONFIG['lst_output_dir'], 'Stats', 'City_LST_Enhanced_Summary.csv'),
                os.path.join(PROJECT_CONFIG['lst_output_dir'], 'LST_Temporal_Analysis_Dask', 'Statistics', 'All_Cities_LST_Statistics.csv')
            ]
            
            stats_found = False
            for file in alt_stats_files:
                if os.path.exists(file):
                    all_stats_df = pd.read_csv(file)
                    print(f"✅ Loaded statistics from alternative location: {file}")
                    stats_found = True
                    break
                    
            if not stats_found:
                raise FileNotFoundError(f"Could not find statistics file in any known location.")
        
        # Determine which LST time periods to process
        lst_time_options = ['day', 'night'] if LST_CONFIG['lst_time'] == 'both' else [LST_CONFIG['lst_time']]
        
        # Process each city
        for city_name, aoi_info in aoi_data.items():
            print(f"\n📊 Processing trend plots for {city_name}...")
            
            # Filter for this city's data
            city_df = all_stats_df[all_stats_df['city'] == city_name]
            
            if city_df.empty:
                print(f"⚠️ No data found for {city_name} in the statistics file")
                continue
                
            # Create directory for trend plots in the city's LST_Temporal_Analysis folder
            city_dir = aoi_info['city_dir']
            city_temporal_dir = os.path.join(PROJECT_CONFIG['lst_output_dir'], f'City_{city_name}', 'LST_Temporal_Analysis')
            os.makedirs(city_temporal_dir, exist_ok=True)
            
            # Create the figure with 1x2 subplots sharing y-axis
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=FIGURE_SIZE, sharey=True)
            
            # Reduce space between subplots
            plt.subplots_adjust(wspace=0.05)
            
            # Get study period for title
            try:
                years_range = f"({TEMPORAL_CONFIG['years'][0]}-{TEMPORAL_CONFIG['years'][-1]})"
            except:
                years_range = ""
                
            # Add overall title with increased font size
            fig.suptitle(f"{city_name} Land Surface Temperature {years_range}", 
                        fontweight='bold', fontsize=27, y=0.95)
            
            # Store data for both plots to determine y-axis limits and safe positioning
            all_temps = []
            day_data = {}
            night_data = {}
            
            # LEFT PLOT: Yearly Trends (both day and night)
            ax1.set_title("Yearly LST Trends", fontsize=21, pad=20)
            
            # Process yearly data for both day and night
            for lst_time in lst_time_options:
                # Filter for day/night data
                time_df = city_df[city_df['day_night'] == lst_time]
                
                if time_df.empty:
                    print(f"⚠️ No {lst_time}-time data found for {city_name}")
                    continue
                    
                # Get yearly data
                yearly_df = time_df[time_df['time_period_type'] == 'yearly']
                
                if yearly_df.empty:
                    print(f"⚠️ No yearly data found for {city_name} {lst_time}")
                    continue
                    
                # Sort yearly data chronologically
                yearly_df = yearly_df.sort_values('time_period')
                
                # Convert years to integers and get median LST values
                years = yearly_df['time_period'].values.astype(int)
                temps = yearly_df['lst_median'].values
                
                # Get min-max values for shaded area
                min_temps = yearly_df['lst_min'].values
                max_temps = yearly_df['lst_max'].values
                
                # Store all temperatures for y-axis limits
                all_temps.extend(min_temps)
                all_temps.extend(max_temps)
                
                # Get color and fill based on day/night
                if lst_time == 'day':
                    color = DAY_COLOR
                    fill_color = DAY_FILL
                    linestyle = ':'  # Dotted line for day trend
                    day_data = {
                        'years': years, 'temps': temps, 'min_temps': min_temps, 'max_temps': max_temps
                    }
                else:
                    color = NIGHT_COLOR
                    fill_color = NIGHT_FILL
                    linestyle = ':'  # Dotted line for night trend
                    night_data = {
                        'years': years, 'temps': temps, 'min_temps': min_temps, 'max_temps': max_temps
                    }
                
                time_label = lst_time.capitalize()
                
                # Plot shaded min-max range
                ax1.fill_between(years, min_temps, max_temps, color=fill_color, zorder=1)
                
                # Plot median line and points
                ax1.plot(years, temps, color=color, alpha=0.8, linestyle='-', linewidth=3.75, zorder=2)
                ax1.scatter(years, temps, color=color, s=60, zorder=3)
                
                # Calculate and plot trendline
                try:
                    from scipy import stats
                    slope, intercept, r_value, p_value, std_err = stats.linregress(years, temps)
                    r_squared = r_value**2
                    
                    # Generate trend line
                    trend_line = intercept + slope * years
                    
                    # Plot trendline with appropriate style
                    ax1.plot(years, trend_line, color=color, linestyle=linestyle, linewidth=3, zorder=1)
                    
                    # Calculate total warming/cooling over the period
                    total_change = slope * (years[-1] - years[0])
                    warming_per_decade = slope * 10
                    
                    # Create trend text box with increased font size
                    equation_text = f"{time_label}: y = {slope:.4f}x + {intercept:.2f}"
                    stats_text = f"R² = {r_squared:.3f}, p<{p_value:.2f}*" if p_value < 0.05 else f"R² = {r_squared:.3f}, p={p_value:.3f}"
                    warming_text = f"Warming: {warming_per_decade:.2f}°C/decade ({total_change:.2f}°C total)"
                    
                    full_text = f"{equation_text}\n{stats_text}\n{warming_text}"
                    
                    # Store trend info for safe positioning later
                    if lst_time == 'day':
                        day_data['trend_text'] = full_text
                        day_data['color'] = color
                    else:
                        night_data['trend_text'] = full_text
                        night_data['color'] = color
                    
                except Exception as e:
                    print(f"⚠️ Error calculating trend for {city_name} {lst_time}: {e}")
            
            # Place trend boxes safely with night always at bottom left
            box_positions = place_trend_box_safely(ax1, day_data if day_data else None, night_data if night_data else None)
            
            # Add the text boxes with fixed positions
            for lst_time in ['day', 'night']:
                data = day_data if lst_time == 'day' else night_data
                if data and 'trend_text' in data and lst_time in box_positions:
                    x_pos, y_pos = box_positions[lst_time]
                    
                    # Set vertical alignment based on position (top for day, bottom for night)
                    v_align = 'top' if lst_time == 'day' else 'bottom'
                    
                    ax1.text(x_pos, y_pos, data['trend_text'], transform=ax1.transAxes,
                            fontsize=15, verticalalignment=v_align, 
                            bbox=dict(boxstyle='round,pad=0.5', facecolor='white', alpha=0.6, edgecolor=data['color'], linewidth=2),
                            color=data['color'], fontweight='bold')
            
            # Add annotations for min/max values with safe positioning
            for lst_time in ['day', 'night']:
                data = day_data if lst_time == 'day' else night_data
                if not data:
                    continue
                    
                years = data['years']
                temps = data['temps']
                color = DAY_COLOR if lst_time == 'day' else NIGHT_COLOR
                
                # Find hottest and coolest year values from yearly median LST
                max_year_idx = np.argmax(temps)
                max_year = years[max_year_idx]
                max_temp = temps[max_year_idx]
                min_year_idx = np.argmin(temps)
                min_year = years[min_year_idx]
                min_temp = temps[min_year_idx]
                
                # Calculate safe positions for annotations
                y_range = ax1.get_ylim()[1] - ax1.get_ylim()[0]
                offset = y_range * 0.03  # 3% of y-range
                
                # Annotate hottest year value with safe positioning
                safe_y_max = find_safe_text_position(ax1, max_year, max_temp, offset)
                ax1.annotate(f"{max_year}: {max_temp:.1f}°C", 
                           xy=(max_year, max_temp),
                           xytext=(max_year, safe_y_max), 
                           ha='center', va='top',
                           fontsize=12, fontweight='bold', color=color,
                           bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor=color, alpha=0.9),
                           arrowprops=dict(arrowstyle='->', color=color, lw=1))
                
                # Annotate minimum year value with safe positioning
                safe_y_min = find_safe_text_position(ax1, min_year, min_temp, -offset)
                ax1.annotate(f"{min_year}: {min_temp:.1f}°C", 
                           xy=(min_year, min_temp),
                           xytext=(min_year, safe_y_min), 
                           ha='center', va='top',
                           fontsize=12, fontweight='bold', color=color,
                           bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor=color, alpha=0.9),
                           arrowprops=dict(arrowstyle='->', color=color, lw=1))
            
            # Format left plot - Ensure years are displayed as integers
            ax1.set_xlabel("Year", fontsize=18)
            ax1.set_ylabel("LST (°C)", fontsize=18)
            ax1.grid(True, linestyle='--', alpha=0.6)
            ax1.tick_params(axis='both', which='major', labelsize=15)
            
            # Set integer years on x-axis
            ax1.xaxis.set_major_locator(ticker.MaxNLocator(integer=True))
            ax1.xaxis.set_major_formatter(ticker.FormatStrFormatter('%d'))
            
            # RIGHT PLOT: Monthly Climatology (both day and night)
            ax2.set_title("Monthly LST Climatology", fontsize=21, pad=20)
            
            # Reset data storage for monthly plot
            day_data = {}
            night_data = {}
            
            # Process monthly climatology data for both day and night
            for lst_time in lst_time_options:
                # Filter for day/night data
                time_df = city_df[city_df['day_night'] == lst_time]
                
                if time_df.empty:
                    continue
                    
                # Get monthly climatology data
                monthly_df = time_df[(time_df['time_period_type'] == 'monthly') & (time_df['is_climatology'] == True)]
                
                if monthly_df.empty:
                    monthly_df = time_df[time_df['time_period_type'] == 'monthly']
                    print(f"⚠️ No climatology data found for {city_name} {lst_time}, using regular monthly data")
                    
                if monthly_df.empty:
                    continue
                    
                # Sort by month number
                monthly_df = monthly_df.sort_values('time_period')
                months = monthly_df['time_period'].values.astype(int)
                temps = monthly_df['lst_median'].values
                
                # Get min-max values for shaded area
                min_temps = monthly_df['lst_min'].values
                max_temps = monthly_df['lst_max'].values
                
                # Store all temperatures for consistent y-axis
                all_temps.extend(min_temps)
                all_temps.extend(max_temps)
                
                # Get color based on day/night
                if lst_time == 'day':
                    color = DAY_COLOR
                    fill_color = DAY_FILL
                    day_data = {'months': months, 'temps': temps, 'min_temps': min_temps, 'max_temps': max_temps}
                else:
                    color = NIGHT_COLOR
                    fill_color = NIGHT_FILL
                    night_data = {'months': months, 'temps': temps, 'min_temps': min_temps, 'max_temps': max_temps}
                
                # Plot shaded min-max range
                ax2.fill_between(months, min_temps, max_temps, color=fill_color, zorder=1)
                
                # Plot median line and points
                ax2.plot(months, temps, color=color, alpha=0.8, linestyle='-', linewidth=3.75, zorder=2)
                ax2.scatter(months, temps, color=color, s=60, zorder=3)
                
                # Find and annotate extreme months with safe positioning
                min_idx = np.argmin(temps)
                max_idx = np.argmax(temps)
                
                min_month = MONTH_ABBRS[months[min_idx]]
                max_month = MONTH_ABBRS[months[max_idx]]
                
                # Calculate safe positions
                y_range = np.max(all_temps) - np.min(all_temps) if all_temps else 10
                offset = y_range * 0.05  # 5% of y-range
                
                # Annotate maximum month with safe positioning
                safe_y_max = find_safe_text_position(ax2, months[max_idx], temps[max_idx], offset)
                ax2.annotate(f"{max_month}: {temps[max_idx]:.1f}°C", 
                           xy=(months[max_idx], temps[max_idx]),
                           xytext=(months[max_idx], safe_y_max),
                           ha='center', va='top',
                           fontsize=15, fontweight='bold', color=color,
                           bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor=color, alpha=0.9),
                           arrowprops=dict(arrowstyle='->', color=color, lw=1.5))
                
                # Annotate minimum month with safe positioning
                safe_y_min = find_safe_text_position(ax2, months[min_idx], temps[min_idx], -offset)
                ax2.annotate(f"{min_month}: {temps[min_idx]:.1f}°C", 
                           xy=(months[min_idx], temps[min_idx]),
                           xytext=(months[min_idx], safe_y_min), 
                           ha='center', va='top',
                           fontsize=15, fontweight='bold', color=color,
                           bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor=color, alpha=0.9),
                           arrowprops=dict(arrowstyle='->', color=color, lw=1.5))
                
                # Calculate additional monthly statistics
                time_label = lst_time.capitalize()
                
                # Monthly amplitude (min-max range)
                monthly_amplitude = np.max(temps) - np.min(temps)
                
                # Standard deviation
                monthly_std = np.std(temps)
                
                # Create simplified statistics text box with only MA and Std Dev
                monthly_stats_text = f"Monthly amplitude: {monthly_amplitude:.1f}°C\nStd Dev: {monthly_std:.1f}°C"
                
                # Store monthly stats info for positioning later
                if lst_time == 'day':
                    day_data['monthly_stats_text'] = monthly_stats_text
                    day_data['color'] = color
                else:
                    night_data['monthly_stats_text'] = monthly_stats_text
                    night_data['color'] = color
            
            # Place monthly statistics boxes safely with night always at bottom right
            monthly_box_positions = place_monthly_stats_box_safely(ax2, day_data if day_data else None, night_data if night_data else None)
            
            # Add monthly statistics boxes to the plot with fixed positions
            for lst_time in ['day', 'night']:
                data = day_data if lst_time == 'day' else night_data
                if data and 'monthly_stats_text' in data and lst_time in monthly_box_positions:
                    x_pos, y_pos = monthly_box_positions[lst_time]
                    
                    # Set vertical alignment based on position (top for day, bottom for night)
                    v_align = 'top' if lst_time == 'day' else 'bottom'
                    
                    ax2.text(x_pos, y_pos, data['monthly_stats_text'], transform=ax2.transAxes,
                            fontsize=12, verticalalignment=v_align, horizontalalignment='right',
                            bbox=dict(boxstyle='round,pad=0.5', facecolor='white', alpha=0.6, edgecolor=data['color'], linewidth=1),
                            color=data['color'], fontweight='bold')
            
            # Format right plot (no y-label since it's shared)
            ax2.set_xlabel("Month", fontsize=18)
            ax2.set_xticks(range(1, 13))
            ax2.set_xticklabels([MONTH_ABBRS[i] for i in range(1, 13)])
            ax2.grid(True, linestyle='--', alpha=0.6)
            ax2.tick_params(axis='both', which='major', labelsize=15)
            
            # Set consistent y-axis limits for both plots
            if all_temps:
                y_min, y_max = min(all_temps), max(all_temps)
                y_margin = (y_max - y_min) * 0.1
                ax1.set_ylim(y_min - y_margin, y_max + y_margin)
                ax2.set_ylim(y_min - y_margin, y_max + y_margin)
            
            # Adjust layout
            plt.tight_layout(rect=[0, 0.03, 1, 0.92])
            
            # Create directory for saving the output
            figures_dir = os.path.join(city_temporal_dir, 'Figures')
            os.makedirs(figures_dir, exist_ok=True)
            
            # Save the combined plot (SVG+PDF) through centralized data_io helper
            output_file_base = os.path.join(figures_dir, f"{city_name}_LST_Trends_Combined2")
            data_io.export_figure_set(
                fig,
                output_file_base,
                save_png=False,
                save_svg=True,
                save_pdf=True,
                dpi=DPI,
                bbox_inches='tight'
            )
            
            print(f"✅ Saved trend plots for {city_name} to {figures_dir}")
            
            plt.close(fig)  # Close to free memory
        
        print("\n" + "="*70)
        print("🎯 LST TREND PLOTS COMPLETED")
        print("="*70)
        print("Trend line plots have been generated for all cities")
        print("="*70)
        
    except Exception as e:
        print(f"ÃƒÂ¢Ã‚ÂÃ…â€™ Error creating trend line plots: {e}")
        traceback_str = traceback.format_exc()
        print(f"ÃƒÂ°Ã…Â¸“Ã¢â‚¬Â¹ Traceback: {traceback_str}")
        
    print("="*70)
    print("LEGEND GENERATION FOR LST TREND PLOTS")
    print("="*70)

    import matplotlib.patches as mpatches
    from matplotlib.lines import Line2D

    try:
        # Create a standalone legend figure
        legend_fig, legend_ax = plt.subplots(figsize=(12, 3), dpi=300)
        
        # Hide the axes
        legend_ax.axis('off')
        
        # Define the legend elements matching your plot styling
        legend_elements = [
            # Day-time elements (orange)
            Line2D([0], [0], color=DAY_COLOR, linewidth=3.75, label='Day-time Median'),
            Line2D([0], [0], color=DAY_COLOR, linewidth=3, linestyle=':', label='Day Trend Line'),
            mpatches.Patch(color=DAY_FILL, label='Day Min-Max Range'),
            
            # Night-time elements (black/grey)
            Line2D([0], [0], color=NIGHT_COLOR, linewidth=3.75, label='Night-time Median'),
            Line2D([0], [0], color=NIGHT_COLOR, linewidth=3, linestyle=':', label='Night Trend Line'),
            mpatches.Patch(color=NIGHT_FILL, label='Night Min-Max Range'),
        ]
        
        # Create the legend with horizontal layout
        legend = legend_ax.legend(
            handles=legend_elements,
            loc='center',
            ncol=3,
            fontsize=14,
            frameon=True,
            fancybox=True,
            shadow=True,
            framealpha=0.9,
            edgecolor='black',
            facecolor='white'
        )
        
        # Adjust legend spacing
        legend.get_frame().set_linewidth(1.5)
        
        # Adjust the layout to center the legend
        legend_fig.tight_layout()
        
        # Create directory for legend output in the main stats directory
        legend_dir = os.path.join(PROJECT_CONFIG['lst_output_dir'], 'Stats')
        os.makedirs(legend_dir, exist_ok=True)
        
        # Save the legend (SVG+PDF) through centralized data_io helper
        legend_output_base = os.path.join(legend_dir, "LST_Trend_Plot_Legend")
        data_io.export_figure_set(
            legend_fig,
            legend_output_base,
            save_png=False,
            save_svg=True,
            save_pdf=True,
            dpi=300,
            bbox_inches='tight',
            facecolor='white',
            edgecolor='none'
        )
        legend_output_svg = f"{legend_output_base}.svg"
        legend_output_pdf = f"{legend_output_base}.pdf"
        
        plt.close(legend_fig)
        
        print(f" Legend saved successfully:")
        print(f"   SVG: {legend_output_svg}")
        print(f"   PDF: {legend_output_pdf}")
        
        # Also create a version for each city's figures directory
        for city_name, aoi_info in aoi_data.items():
            city_figures_dir = os.path.join(PROJECT_CONFIG['lst_output_dir'], f'City_{city_name}', 
                                           'LST_Temporal_Analysis', 'Figures')
            if os.path.exists(city_figures_dir):
                city_legend_svg = os.path.join(city_figures_dir, f"{city_name}_LST_Trend_Legend.svg")
                city_legend_pdf = os.path.join(city_figures_dir, f"{city_name}_LST_Trend_Legend.pdf")
                
                # Copy the legend to each city's directory
                import shutil
                shutil.copy2(legend_output_svg, city_legend_svg)
                shutil.copy2(legend_output_pdf, city_legend_pdf)
                
                print(f"   ÃƒÂ¢Ã…â€œ“ Legend copied to {city_name} figures directory")
        
        print("\n" + "="*70)
        print("🎯 LEGEND GENERATION COMPLETED")
        print("="*70)
        print("="*70)
        
    except Exception as e:
        print(f"ÃƒÂ¢Ã‚ÂÃ…â€™ Error creating legend: {e}")
        traceback_str = traceback.format_exc()
        print(f"ÃƒÂ°Ã…Â¸“Ã¢â‚¬Â¹ Traceback: {traceback_str}")