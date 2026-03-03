# Dynamics of Urban Surface Warming in Nigerian Cities: A Multi-source, Landscape-oriented, Stakeholder-informed Analysis

## Overview

Reproducible Land Surface Temperature (LST) modeling and Urban Heat Island (UHI) hotspot analysis for Nigerian cities. The project integrates multi-source satellite data (MODIS, ERA5-Land, MSG SEVIRI), stakeholder survey data from workshops organized, and landscape assessment to identify, quantify, and validate persistent heat events across multiple study cities.

**Study cities:** 16 Nigerian cities with population ≥ 1 million (configurable in `config.py`)  
**Test cities:** Lagos, Abuja, Kano, Jos, Port Harcourt  
**Workshop cities:** Individuals from 28 cities across Nigeria were in attendance (stakeholder survey)  
**Study year:** 2024/2025  

---

## Valid City Names (50)

The pipeline recognises **exactly** these 50 city names from the population CSV. Spelling and capitalisation must match — the runner will flag typos and suggest corrections.

<details>
<summary>Click to expand full list</summary>

| # | City | # | City | # | City | # | City | # | City |
|---|------|---|------|---|------|---|------|---|------|
| 1 | Aba | 11 | Effon Alaiye | 21 | Ikot Ekpene | 31 | Maiduguri | 41 | Owerri |
| 2 | Abakaliki | 12 | Enugu | 22 | Ilesha | 32 | Makurdi | 42 | Oyo |
| 3 | Abeokuta | 13 | Gboko | 23 | Ilorin | 33 | Minna | 43 | Port Harcourt |
| 4 | Abuja | 14 | Gombe | 24 | Jos | 34 | Nnewi | 44 | Potiskum |
| 5 | Ado-Ekiti | 15 | Gwagwalada | 25 | Kaduna | 35 | Ogbomosho | 45 | Saki |
| 6 | Akure | 16 | Ibadan | 26 | Kano | 36 | Okene | 46 | Sokoto |
| 7 | Bauchi | 17 | Ife | 27 | Katsina | 37 | Okpogho | 47 | Umuahia |
| 8 | Benin City | 18 | Igbidu | 28 | Lafia | 38 | Ondo | 48 | Uyo |
| 9 | Birnin Kebbi | 19 | Ijebu-Ode | 29 | Lagos | 39 | Onitsha | 49 | Warri |
| 10 | Calabar | 20 | Ikorodu | 30 | Lokoja | 40 | Oshogbo | 50 | Zaria |

</details>

```powershell
# List all valid city names from the terminal
python run_all.py --list-cities

# Example: if you mistype a city name the runner will flag it
python run_all.py --cities "Lag0s" "Abuja"
# [ERROR] 'Lag0s' is not a valid city name.  Did you mean: Lagos
```

---

## Quick Start

### 1. Initial Setup
```powershell
# Clone and create virtual environment
git clone <repo-url>
cd stake_lst_modelling
python -m venv geovenv

# Activate environment
.\geovenv\Scripts\Activate.ps1    # Windows PowerShell
# source geovenv/bin/activate     # Linux/Mac

# Install dependencies (includes osmnx for OpenStreetMap queries)
pip install -r requirements.txt
```

> **Note:** The `osmnx` package (added to `requirements.txt`) is required for Notebook 01a to extract OSM roads and places via the Overpass API.

### 2. Configure Credentials
See [docs/SECURITY_SETUP.md](docs/SECURITY_SETUP.md) for detailed instructions.

| Credential | Required By | Location |
|-----------|------------|----------|
| GEE Service Account | Notebooks 01a, 03, 04, 05 | `secrets/gee_service_account.json` |
| EUMETSAT API Keys | Notebook 04 (SEVIRI) | `secrets/eumetsat_credentials.json` |

### 3. Run the Analysis

**Option A — Interactive (Jupyter Lab):**
```powershell
jupyter lab
# Run notebooks in order: 01 → 01a → 02 → 03 → 04 → 05 → 06
```

**Option B — Automated (Master Runner Script):**
```powershell
# Run all notebooks for all cities
python run_all.py

# Run for specific cities
python run_all.py --cities "Lagos" "Abuja" "Kano"

# Run specific notebooks only
python run_all.py --notebooks 01 05

# Preview execution plan without running
python run_all.py --dry-run

# Skip notebooks requiring external APIs
python run_all.py --skip-gee --skip-eumetsat
```

### 4. Running Tests
```powershell
# Run all tests
pytest tests/ -v

# Run a specific test module
pytest tests/test_config.py -v
```

### 5. Docker (Optional)
```powershell
# Build
docker build -t lst-modelling .

# Run interactively
docker run -it -v ${PWD}/data:/app/data -v ${PWD}/secrets:/app/secrets lst-modelling bash

# Run the pipeline
docker run -v ${PWD}/data:/app/data -v ${PWD}/secrets:/app/secrets lst-modelling python run_all.py
```

---

## Notebook Pipeline

Notebooks must be run in order — each builds on outputs from previous stages.

```
01_AOI_delineation ──► 01a_OSM_JRC_features
│                            │
├──► 02_stakeholder_analysis │ (independent)
│                            │
├──► 03_temporal_months_annual ◄─┘
│
└──► 04_temporal_daily
        │
        └──► 05_hotspot_analysis
                │
                └──► 06_hotspot_modelling
```

| # | Notebook | Purpose | External APIs | Inputs |
|---|---------|---------|--------------|--------|
| 01 | `01_AOI_delineation.ipynb` | Define city AOIs (buffer zones, boundaries, population stats) | — | Cities CSV, urban/boundary GeoJSON |
| 01a | `01a_AOI_OSM_JRC_features.ipynb` | Extract OSM water/roads/places and create study area maps | GEE | Notebook 01 AOI outputs |
| 02 | `02_stakeholder_analysis.ipynb` | Stakeholder survey mapping and perception analysis | — | `master_composite.csv`, cities CSV |
| 03 | `03_temporal_analysis_months_annual.ipynb` | Monthly/annual LST extraction and trend analysis (2006–2024) | GEE (MODIS) | Notebook 01 AOI outputs |
| 04 | `04_temporal_analysis_daily.ipynb` | Daily LST analysis: MODIS + ERA5 hot events, SEVIRI persistent heat rasters | GEE, EUMETSAT | Notebook 01 AOI outputs |
| 05 | `05_hotspot_analysis.ipynb` | UHI hotspot detection (Gi\*), KDE delineation, landscape enrichment, population exposure, stakeholder validation | GEE (GHSL) | Notebooks 03 + 04 outputs, landscape/survey data |
| 06 | `06_hotspot_modelling.ipynb` | Landscape-oriented modelling: hotspot occurrence (logistic), extent (OLS), intensity (OLS) with hierarchical block entry and city-clustered SEs | — | Notebook 05 hotspot outputs, landscape data |

### Execution Times (Benchmark)

Timings below were measured on a modest development workstation:

| Component | Specification |
|-----------|---------------|
| **CPU** | Intel Core i7-4600U @ 2.10 GHz (2 cores, 4 threads) |
| **RAM** | 8 GB DDR3 |
| **OS** | Windows 11 |
| **Python** | 3.11 |
| **Internet** | ~50 Mbps (required for GEE/OSM/EUMETSAT APIs) |

| Notebook | ~Time (5 cities) | ~Time per city | Notes |
|----------|------------------|----------------|-------|
| **01** AOI Delineation | 2–3 min | 30 sec | Local processing only |
| **01a** OSM/JRC Features | 15–25 min | 3–5 min | GEE water + OSM roads/places + map generation |
| **02** Stakeholder Analysis | 3–5 min | — | Survey data (no per-city loop) |
| **03** Monthly/Annual LST | 30–45 min | 6–9 min | GEE MODIS extraction (2006–2024) |
| **04** Daily LST + SEVIRI | 45–90 min | 10–18 min | GEE + EUMETSAT download (network-bound) |
| **05** Hotspot Analysis | 20–30 min | 4–6 min | Gi\* statistics, KDE, population exposure |

> **Tip:** For 50 cities (`CITY_SELECTION_MODE = "ALL"`), expect 8–12 hours total.  
> Use `"TEST"` mode (5 cities) for development/debugging (~2–3 hours total).

### Visualization and Output Logic

When processing many cities (`ALL` or `ABOVE_1M` mode), the pipeline uses **smart output strategies** to keep publication figures readable while still generating per-city outputs:

| Output Type | ALL/ABOVE_1M Mode | TEST/SPECIFIC Mode |
|-------------|-------------------|-------------------|
| **Publication study area map** | Nigeria + 5 TEST cities only | All selected cities |
| **Per-city study area maps** | ✓ Saved to `City_[Name]/Figures/` | ✓ Saved to `City_[Name]/Figures/` |
| **Per-city feature maps** | ✓ AOI-bounded extent | ✓ AOI-bounded extent |
| **Summary charts** | ✓ All cities included | ✓ All cities included |

All per-city maps use the **AOI boundary from Notebook 01** as the definitive map extent, ensuring consistent framing across the pipeline.

### City Selection Configuration

City selection is controlled in **`config.py`** via `CITY_SELECTION_MODE`. Edit this setting to choose which cities to process:

| Mode | Description | Cities |
|------|-------------|--------|
| `"ALL"` | All cities in the CSV file | 50 cities |
| `"ABOVE_1M"` | Cities with population ≥ 1 million (default) | 16 cities |
| `"TEST"` | Quick development/debugging runs | Lagos, Abuja, Kano, Jos, Port Harcourt |
| `"SPECIFIC"` | User-specified custom selection | Any from 50 valid cities |

```python
# In config.py — change this line:
CITY_SELECTION_MODE = "ALL"       # All 50 cities in CSV
CITY_SELECTION_MODE = "ABOVE_1M"  # 16 cities >= 1M population (default)
CITY_SELECTION_MODE = "TEST"      # 5 test cities for quick runs
CITY_SELECTION_MODE = "SPECIFIC"  # Custom selection (edit SELECTED_CITIES below)

# For SPECIFIC mode, populate this list:
SELECTED_CITIES = ["Lagos", "Enugu", "Maiduguri"]  # Any valid cities
```

**Cities with population ≥ 1 million (2024):**
Lagos, Kano, Abuja, Ibadan, Port Harcourt, Benin City, Onitsha, Uyo, Nnewi, Aba, Kaduna, Ikorodu, Ilorin, Warri, Owerri, Jos

### City Selection Flow

Cities selected in **config.py** automatically flow to all downstream notebooks. Each downstream notebook auto-discovers cities by scanning the output directories of its predecessors — no manual configuration needed.

---

## Project Structure

```
stake_lst_modelling/
├── run_all.py                 # Master runner script (automated execution)
├── config.py                  # Centralized configuration (paths, parameters, CRS)
├── requirements.txt           # Python dependencies
├── .gitignore                 # Git ignore rules
│
├── notebooks/                 # Analysis notebooks (01–05)
│   ├── 01_AOI_delineation.ipynb
│   ├── 01a_AOI_OSM_JRC_features.ipynb
│   ├── 02_stakeholder_analysis.ipynb
│   ├── 03_temporal_analysis_months_annual.ipynb
│   ├── 04_temporal_analysis_daily.ipynb
│   ├── 05_hotspot_analysis.ipynb
│   └── 06_hotspot_modelling.ipynb
│
├── src/                       # Reusable Python modules
│   ├── aoi_utils.py           # AOI processing (buffers, boundaries, statistics)
│   ├── data_io.py             # Data loading, export, spatial operations
│   ├── gee_utils.py           # Google Earth Engine extraction (MODIS, ERA5)
│   ├── temporal_analysis.py   # LST trend analysis and statistics
│   ├── temporal_analysis_utils.py  # Daily LST helper functions
│   ├── decision_tree_utils.py # Heat event decision tree logic
│   ├── seviri_processing_utils.py  # EUMETSAT SEVIRI download and processing
│   ├── modelling_utils.py     # Hierarchical regression, panel charts (NB06)
│   └── visualization.py       # All plotting functions (~8,000 lines)
│
├── data/
│   ├── inputs/
│   │   ├── geospatial_features/    # Cities CSV, urban/boundary GeoJSON, landscape polygons
│   │   ├── stakeholder_survey/     # master_composite.csv (1,194 rows × 96 cols)
│   │   └── osm_nigeria/            # Pre-downloaded OSM data
│   └── outputs/
│       ├── 01_aoi_delineation/     # City AOI boundaries and features
│       ├── 02_stakeholder_analysis/ # Survey maps and charts
│       ├── 03_trend_analysis_monthly_annual/  # LST rasters and trend figures
│       ├── 04_trend_analysis_daily/  # Daily time series, SEVIRI heat rasters
│       ├── 05_hotspot_analysis/     # Hotspot polygons, KDE maps, charts
│       └── 06_hotspot_modelling/    # Model tables (CSV) and figures (PNG/PDF)
│
├── secrets/                   # API credentials (git-ignored)
│   ├── gee_service_account.json
│   └── eumetsat_credentials.json
│
└── docs/                      # Documentation
    ├── PROJECT_AUDIT_REPORT.md      # Full project audit and dependency analysis
    ├── PROGRESS_TRACKER.md          # Current status
    ├── execution_strategy.md        # Setup reference
    └── ...
```

---

## Key Configuration (`config.py`)

| Parameter | Value | Description |
|-----------|-------|-------------|
| `PROJECT_STUDY_YEAR` | 2024 | Reference year for all analyses |
| `HOTSPOT_CONFIG.percentile_hot` | 90 | Top 10% = hot pixels |
| `KDE_CONFIG.contour_levels` | [50, 75, 90] | Nested hotspot polygons |
| `RESAMPLE_CONFIG.resolution_m` | 250 | Resampled binary mask resolution |
| `AOI_BUFFER_DISTANCE` | 5000m | Buffer around urban polygons |
| `FIGURE_DPI` | 300 | Publication-quality output |
| `HIERARCHY_BLOCKS` | Climate → Geology → Elevation | Hierarchical regression block order |
| `OLS_CLUSTERED_CONFIG.cluster_variable` | city | City-level clustered standard errors |

The `CITIES` list is populated dynamically by scanning Notebook 04 SEVIRI outputs (via `load_cities_from_daily_analysis()`). For Notebook 01, cities are selected interactively or via CLI.

---

## Outputs Summary

### Notebook 05 — Hotspot Analysis Outputs
- **Hotspot polygons** (GeoJSON, EPSG:4326 + EPSG:3857) with landscape, LST, and population attributes
- **City grid maps** — multi-panel hotspot maps with survey overlay per city
- **Gi\* distribution plots** — statistical significance of hotspot detection
- **Contour area charts** — hotspot area by landscape class and contour level
- **Population exposure half-donuts** — people exposed to UHI per city
- **National summary map** — proportional symbol map across all study cities
- **Stakeholder perception charts** — reasons/mitigation by Cluster25 landscape type
- **Tree species heatmaps** — 4 variants (by cluster/city × top-15/all species)

### Notebook 06 — Hotspot Modelling Outputs
- **Skewness diagnostics** — 2×2 Day|Night panels with normal distribution overlay
- **Model comparison tables** (CSV) — hierarchical block R², ΔR², AIC, BIC per analysis
- **Coefficient tables** (CSV) — OLS coefficients with clustered SEs and % change
- **Variance partitioning panels** — Day|Night stacked bar charts (logistic pseudo-R², OLS R²)
- **Coefficient forest plots** — Day|Night horizontal panel with significance colouring
- **Model metadata** (JSON) — reproducibility records per analysis/period

---

## Documentation

- [docs/PROJECT_CONCEPT_NOTE.md](docs/PROJECT_CONCEPT_NOTE.md) — Unified project concept note (research context, methodology, architecture, outputs)
- [docs/SECURITY_SETUP.md](docs/SECURITY_SETUP.md) — Credential management and setup instructions
- [docs/Idea_mapping_formatted.md](docs/Idea_mapping_formatted.md) — Original research strategy document
- [secrets/README.md](secrets/README.md) — API credential file formats and setup guide
- [secrets/gee_service_account.json.example](secrets/gee_service_account.json.example) — GEE service account template
- [secrets/eumetsat_credentials.json.example](secrets/eumetsat_credentials.json.example) — EUMETSAT API key template

---

## Current Status

| Phase | Status | Description |
|-------|--------|-------------|
| **Phase 1** | Complete | AOI delineation and stakeholder analysis |
| **Phase 2** | Complete | Monthly/annual LST temporal analysis |
| **Phase 3** | Complete | Daily LST analysis (MODIS, ERA5, SEVIRI) |
| **Phase 4** | Complete | UHI hotspot detection and stakeholder validation |
| **Phase 5** | Complete | Landscape-oriented hotspot modelling — occurrence, extent, and intensity (Notebook 06) |

---

## License

This project is licensed under [CC-BY-4.0](LICENSE). You are free to share and adapt the material with appropriate credit.

## How to Cite

If you use this project in your research, please cite it using the metadata in [CITATION.cff](CITATION.cff):

> Eneche, P. (2026). *Urban Heat Island & LST Modeling Project*. University of Twente. Licensed under CC-BY-4.0.
