# Urban Heat Island & LST Modeling Project

## Overview

Reproducible Land Surface Temperature (LST) modeling and Urban Heat Island (UHI) hotspot analysis for Nigerian cities. The project integrates multi-source satellite data (MODIS, ERA5-Land, MSG SEVIRI), stakeholder survey data from 28 workshop cities, and landscape characterization to identify, quantify, and validate persistent urban heat islands across 5 study cities.

**Study cities:** Abuja, Jos, Kano, Lagos, Port Harcourt  
**Workshop cities:** 28 cities across Nigeria (stakeholder survey)  
**Study year:** 2024  

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

# Install dependencies
pip install -r requirements.txt
```

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
# Run notebooks in order: 01 → 01a → 02 → 03 → 04 → 05 → 061 → 062 → 063
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
                └──► 061_lst_model_variables
                        │
                        └──► 062_lst_modelling
                                │
                                └──► 063_lst_model_validation
```

| # | Notebook | Purpose | External APIs | Inputs |
|---|---------|---------|--------------|--------|
| 01 | `01_AOI_delineation.ipynb` | Define city AOIs (buffer zones, boundaries, population stats) | — | Cities CSV, urban/boundary GeoJSON |
| 01a | `01a_AOI_OSM_JRC_features.ipynb` | Extract OSM water/roads/places and create study area maps | GEE | Notebook 01 AOI outputs |
| 02 | `02_stakeholder_analysis.ipynb` | Stakeholder survey mapping and perception analysis | — | `master_composite.csv`, cities CSV |
| 03 | `03_temporal_analysis_months_annual.ipynb` | Monthly/annual LST extraction and trend analysis (2006–2024) | GEE (MODIS) | Notebook 01 AOI outputs |
| 04 | `04_temporal_analysis_daily.ipynb` | Daily LST analysis: MODIS + ERA5 hot events, SEVIRI persistent heat rasters | GEE, EUMETSAT | Notebook 01 AOI outputs |
| 05 | `05_hotspot_analysis.ipynb` | UHI hotspot detection (Gi\*), KDE delineation, landscape enrichment, population exposure, stakeholder validation | GEE (GHSL) | Notebooks 03 + 04 outputs, landscape/survey data |
| 061 | `061_lst_model_variables.ipynb` | Feature engineering — extract predictor variables (NDVI, NDBI, elevation, distance to water/roads, population density) per pixel | GEE | Notebook 05 hotspot outputs |
| 062 | `062_lst_modelling.ipynb` | Train Random Forest and Gradient Boosting regression models for LST prediction | — | Notebook 061 feature dataset |
| 063 | `063_lst_model_validation.ipynb` | Model evaluation: hold-out test set, spatial cross-validation, stakeholder comparison | — | Notebook 062 trained models |

### City Selection Flow

Cities selected in **Notebook 01** (via interactive widget or CLI) automatically flow to all downstream notebooks. Each downstream notebook auto-discovers cities by scanning the output directories of its predecessors — no manual configuration needed.

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
│   ├── 061_lst_model_variables.ipynb
│   ├── 062_lst_modelling.ipynb
│   └── 063_lst_model_validation.ipynb
│
├── src/                       # Reusable Python modules
│   ├── aoi_utils.py           # AOI processing (buffers, boundaries, statistics)
│   ├── data_io.py             # Data loading, export, spatial operations
│   ├── gee_utils.py           # Google Earth Engine extraction (MODIS, ERA5)
│   ├── temporal_analysis.py   # LST trend analysis and statistics
│   ├── temporal_analysis_utils.py  # Daily LST helper functions
│   ├── decision_tree_utils.py # Heat event decision tree logic
│   ├── seviri_processing_utils.py  # EUMETSAT SEVIRI download and processing
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
│       ├── 061_lst_model_variables/ # Feature engineering outputs
│       ├── 062_lst_modelling/       # Trained models & LST predictions
│       └── 063_lst_model_validation/ # Validation reports & figures
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
| `MODEL_TRAINING_CONFIG.models` | RF, GBR | Regression models for LST prediction |
| `MODEL_VALIDATION_CONFIG.spatial_cv` | leave-one-city-out | Spatial cross-validation strategy |

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
| **Phase 5** | In Progress | LST feature engineering and predictive modeling (Notebooks 061–063) |

---

## License

This project is licensed under [CC-BY-4.0](LICENSE). You are free to share and adapt the material with appropriate credit.

## How to Cite

If you use this project in your research, please cite it using the metadata in [CITATION.cff](CITATION.cff):

> Eneche, P. (2026). *Urban Heat Island & LST Modeling Project*. University of Twente. Licensed under CC-BY-4.0.
