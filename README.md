# Dynamics of Urban Surface Warming in Nigerian Cities: A Multi-source, Landscape-oriented, Stakeholder-informed Analysis

## Overview

Reproducible Land Surface Temperature (LST) modeling and Urban Heat Island (UHI) hotspot analysis for Nigerian cities. The project integrates multi-source satellite data (MODIS, ERA5-Land, MSG SEVIRI), stakeholder survey data from workshops organized, and landscape assessment to identify, quantify, and validate persistent heat events across multiple study cities.

**Study cities:** 67 Nigerian cities ≥300k population (UN WUP 2025) → 58 unique AOIs after spatial deduplication (configurable in `config.py`)  
**Test cities:** Lagos, Abuja, Kano, Jos, Port Harcourt  
**Workshop cities:** Individuals from 28 cities across Nigeria were in attendance (stakeholder survey)  
**Study year:** 2024/2025  

---

## Valid City Names (67 cities ≥300k → 58 AOIs)

The pipeline uses **67 cities** from the UN WUP 2025 dataset with population ≥300k (2024 estimates). After spatial deduplication in Notebook 01 (merging overlapping AOIs), this produces **58 unique AOIs**. Spelling and capitalisation must match — the runner will flag typos and suggest corrections.

<details>
<summary>Click to expand full list (67 cities, sorted alphabetically)</summary>

| # | City | # | City | # | City | # | City |
|---|------|---|------|---|------|---|------|
| 1 | Aba | 18 | Enugu | 35 | Kaduna | 52 | Oron |
| 2 | Abakaliki | 19 | Erin-osun | 36 | Kano | 53 | Oshogbo |
| 3 | Abeokuta | 20 | Gamboru | 37 | Katsina | 54 | Otite |
| 4 | Aboh | 21 | Gboko | 38 | KUNDULUN | 55 | Owerri |
| 5 | Abonnema | 22 | Gusau | 39 | Lagos | 56 | Oyigbo |
| 6 | Abuja | 23 | Gwagwalada | 40 | Lokoja | 57 | Oyo |
| 7 | Ado Ekiti | 24 | Ibadan | 41 | Madalla | 58 | Port Harcourt |
| 8 | Akure | 25 | Ife | 42 | Maiduguri | 59 | Potiskum |
| 9 | Asaba | 26 | Ijebu-Ode | 43 | Makurdi | 60 | Saki |
| 10 | Bauchi | 27 | Ikare | 44 | Minna | 61 | Sapele |
| 11 | Benin City | 28 | Ikere-Ekiti | 45 | Nsukka | 62 | Sokoto |
| 12 | Bida | 29 | Ikorodu | 46 | Ogale | 63 | Titi |
| 13 | Bonny | 30 | Ikot Ekpene | 47 | Ogbomosho | 64 | Ughelli |
| 14 | Calabar | 31 | Ilesa | 48 | Ondo | 65 | Umuahia |
| 15 | Daura | 32 | Ilorin | 49 | Onitsha | 66 | Uyo |
| 16 | Dere | 33 | Iseyin | 50 | Warri | 67 | Yenagoa |
| 17 | | 34 | Jos | 51 | Yola | | Zaria |

> **Note:** 9 cities are absorbed into parent AOIs during spatial deduplication (e.g., Ikorodu → Lagos), resulting in 58 unique AOIs.

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

**Prerequisites:** Python **3.11 or 3.12**, Git, and (for the GEE/EUMETSAT notebooks) internet access.

Create and activate a virtual environment named **`geovenv`** (this exact name is what the tooling
expects), then install the pinned dependencies:

```powershell
# 1. Clone the repository
git clone <repo-url>
cd stake_lst_modelling

# 2. Create the virtual environment (uses your Python 3.11/3.12 interpreter)
python -m venv geovenv

# 3. Activate it
.\geovenv\Scripts\Activate.ps1     # Windows PowerShell
# .\geovenv\Scripts\activate.bat   # Windows cmd
# source geovenv/bin/activate      # Linux / macOS

# 4. Upgrade pip and install all dependencies (incl. geopandas, osmnx, xlsxwriter, earthengine-api)
python -m pip install --upgrade pip
pip install -r requirements.txt

# 5. Register the environment as a Jupyter kernel named "python3"
#    (run_all.py and the notebooks execute against this kernel)
python -m ipykernel install --user --name python3 --display-name "Python (geovenv)"
```

> **Always activate `geovenv` first** — launch `jupyter lab` and run `python run_all.py` from the
> activated environment so the notebooks resolve the correct packages.
>
> **Note:** `osmnx` (in `requirements.txt`) is required for Notebook 01 to extract OSM roads and
> places via the Overpass API.

### 2. Configure Credentials
See [docs/SECURITY_SETUP.md](docs/SECURITY_SETUP.md) for detailed instructions.

| Credential | Required By | Location |
|-----------|------------|----------|
| GEE Service Account | Notebooks 01, 03, 04, 05 | `secrets/gee_service_account.json` |
| EUMETSAT API Keys | Notebook 04 (SEVIRI) | `secrets/eumetsat_credentials.json` |

### 3. Run the Analysis

**Option A — Interactive (Jupyter Lab):**
```powershell
jupyter lab
# Run notebooks in order: 01 → 02 → 03 → 04 → 05 → 06 → 07_publication_outputs
```

**Option B — Automated (Master Runner Script):**
```powershell
# Run the pipeline (you will be prompted for what to generate — see below)
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

**Choosing what to generate (output scope).**
When you run `python run_all.py` without `--notebooks`, it asks which outputs to build:

| Choice | `--scope` value | What runs |
|--------|-----------------|-----------|
| **1. Manuscript outputs only** | `manuscript` | `Notebook/07_publication_outputs.ipynb` — assembles all manuscript figures, tables and appendices **from cached `Results/`** (no GEE/OSM, minutes) |
| **2. All project outputs** | `all` | The analysis pipeline 01 → 05 (NB05's last section builds and checks the published dataset) → 06, then the manuscript assembly |
| **3. Analytic outputs only** | `analytic` | The analysis notebooks 01–06 (no manuscript assembly) |
| **4. Published dataset only** | `dataset` | `build_dataset()` from `scripts/build_master_summary.py`, called directly **from cached `Results/`** with no notebook run; QA runs if the deposit changed (no credentials, ~1 minute) |

```powershell
# Skip the prompt by passing the scope explicitly:
python run_all.py --scope manuscript   # rebuild manuscript artwork from cache (fast)
python run_all.py --scope dataset      # rebuild the published dataset from cache (fast)
python run_all.py --scope all          # full reproduction, end to end
python run_all.py --scope analytic     # analysis only
```
> In a non-interactive shell (CI, Docker) the prompt is skipped and `all` is assumed; pass
> `--scope` to override.

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

All notebooks live in `Notebook/` and must be run in order — each builds on outputs from previous
stages.

```
01_AOI_delineation ──► 02_stakeholder_analysis (independent)
│                            │
├──► 03_temporal_months_annual│
│                             │
└──► 04_temporal_daily        │
        │                     │
        └──► 05_hotspot_analysis
                │             │
                └──► 06_hotspot_modelling
                              │
                              └──► 07_publication_outputs (manuscript assembly)
```

| # | Notebook | Purpose | External APIs | Inputs |
|---|---------|---------|--------------|--------|
| 01 | `01_AOI_delineation.ipynb` | Define city AOIs (zones, boundaries, population, Cluster25) **and** extract OSM water/roads/places + create study-area maps (former `01a`, now merged) | GEE, OSM | Cities CSV, urban/boundary GeoJSON |
| 02 | `02_stakeholder_analysis.ipynb` | Stakeholder survey mapping and perception analysis | — | `master_composite.csv`, cities CSV |
| 03 | `03_temporal_analysis_months_annual.ipynb` | Monthly/annual LST extraction and trend analysis (2006–2024) | GEE (MODIS) | Notebook 01 AOI outputs |
| 04 | `04_temporal_analysis_daily.ipynb` | Daily LST analysis: MODIS + ERA5 hot events, SEVIRI persistent heat rasters | GEE, EUMETSAT | Notebook 01 AOI outputs |
| 05 | `05_hotspot_analysis.ipynb` | UHI hotspot detection (Gi\*), KDE delineation, landscape enrichment, population exposure, stakeholder validation | GEE (GHSL) | Notebooks 03 + 04 outputs, landscape/survey data |
| 06 | `06_hotspot_modelling.ipynb` | Landscape-oriented modelling: extent (OLS) and intensity (OLS) with hierarchical block entry, city-clustered SEs, and Wild Cluster Bootstrap inference (B = 999) | — | Notebook 05 hotspot outputs, landscape data |
| pub | `07_publication_outputs.ipynb` | **Manuscript assembly** — re-renders every manuscript figure, supplementary figure, table and appendix from cached `Results/`, in manuscript order. No GEE/OSM. | — | Cached `Results/` from 01–06 |

| data | `scripts/build_master_summary.py` | **Published dataset assembly** — builds the composite GeoPackage and its data dictionary from cached `Results/`, then runs the QA suite. No GEE/OSM. | — | Cached `Results/` from 01–05 |

> The analysis notebooks 01–06 are run by `run_all.py`; the manuscript-assembly notebook
> `07_publication_outputs.ipynb` and the dataset build are run last (or on their own via
> `--scope manuscript` / `--scope dataset`). Both read only cached `Results/` and need no
> credentials. Registry entries may point at a notebook (`file`) or a Python script (`script`).

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
| **01** AOI Delineation (incl. OSM/JRC) | 18–28 min | 4–6 min | Local zones + GEE water + OSM roads/places + maps |
| **02** Stakeholder Analysis | 3–5 min | — | Survey data (no per-city loop) |
| **03** Monthly/Annual LST | 30–45 min | 6–9 min | GEE MODIS extraction (2006–2024) |
| **04** Daily LST + SEVIRI | 45–90 min | 10–18 min | GEE + EUMETSAT download (network-bound) |
| **05** Hotspot Analysis | 20–30 min | 4–6 min | Gi\* statistics, KDE, population exposure |

> **Tip:** For 67 cities (`CITY_SELECTION_MODE = "ABOVE_300K"`), expect 8–12 hours total.  
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
| `"ALL"` | All cities in the CSV file | 791 cities |
| `"ABOVE_1M"` | Cities with population ≥ 1 million | 17 cities |
| `"ABOVE_500K"` | Cities with population ≥ 500k | 37 cities |
| `"ABOVE_300K"` | Cities with population ≥ 300k (default) | 67 cities → 58 AOIs |
| `"TEST"` | Quick development/debugging runs | Lagos, Abuja, Kano, Jos, Port Harcourt |
| `"SPECIFIC"` | User-specified custom selection | Any from 791 valid cities |

```python
# In config.py — change this line:
CITY_SELECTION_MODE = "ALL"        # All 791 cities in CSV
CITY_SELECTION_MODE = "ABOVE_1M"   # 17 cities >= 1M population
CITY_SELECTION_MODE = "ABOVE_500K" # 37 cities >= 500k population
CITY_SELECTION_MODE = "ABOVE_300K" # 67 cities >= 300k population (default)
CITY_SELECTION_MODE = "TEST"       # 5 test cities for quick runs
CITY_SELECTION_MODE = "SPECIFIC"   # Custom selection (edit SELECTED_CITIES below)

# For SPECIFIC mode, populate this list:
SELECTED_CITIES = ["Lagos", "Enugu", "Maiduguri"]  # Any valid cities
```

**Cities with population ≥ 1 million (2024, WUP 2025):**
Lagos, Onitsha, Kano, Owerri, Ibadan, Port Harcourt, Kaduna, Benin City, Warri, Uyo, Aba, Aboh, Abuja, Ilorin, Maiduguri, Enugu, Otite

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
├── Notebook/                  # All notebooks (analysis 01–06 + manuscript assembly)
│   ├── 01_AOI_delineation.ipynb          # AOI zones + OSM/JRC features (former 01a merged in)
│   ├── 02_stakeholder_analysis.ipynb
│   ├── 03_temporal_analysis_months_annual.ipynb
│   ├── 04_temporal_analysis_daily.ipynb
│   ├── 05_hotspot_analysis.ipynb
│   ├── 06_hotspot_modelling.ipynb
│   └── 07_publication_outputs.ipynb         # Assembles manuscript artwork from cached Results/
│
├── scripts/                   # Re-runnable pipeline scripts (ship with the repository)
│   ├── build_master_summary.py   # Assembles the published composite dataset from cached Results/
│   └── qa_master_summary.py      # 60-check QA suite over the built dataset
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
│   ├── pub_hotspot_tables.py  # Manuscript §3.3–§3.4 table builders (csv + styled xlsx)
│   ├── temporal_panels.py     # Annual/monthly trend panel renderer (NB03 split)
│   └── visualization.py       # All plotting functions (~8,000 lines)
│
├── data/
│   ├── inputs/
│   │   ├── geospatial_features/    # Cities CSV, urban/boundary GeoJSON, landscape polygons
│   │   ├── stakeholder_survey/     # master_composite.csv (1,194 rows × 96 cols)
│   │   └── osm_nigeria/            # Pre-downloaded OSM data
│   └── outputs/                    # Legacy outputs (kept for reference)
│
├── Results/                   # Current pipeline outputs (git-ignored; published via Zenodo)
│   ├── 01_aoi_delineation/         # City AOI boundaries, zones, population, cluster tables
│   ├── 02_stakeholder_analysis/    # Survey maps, perception charts, stakeholder figures
│   ├── 03_… / 04_… / 06_…          # Temporal, daily and modelling outputs
│   ├── 05_hotspot_analysis/        # Hotspot outputs, and the published dataset:
│   │   └── surface_thermal_anomaly_stakeholder_composite/
│   │       ├── surface_thermal_anomaly_stakeholder_composite.gpkg   # 17 layers, the dataset
│   │       ├── data_dictionary.csv / .md                            # one table per layer
│   │       └── _build/             # reports, README, CHANGELOG, checksums (not archived)
│   └── manuscript_outputs/         # Assembled manuscript figures/tables/appendices (see above)
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
| `WILD_BOOTSTRAP_CONFIG.n_bootstrap` | 999 | Wild Cluster Bootstrap replications (Rademacher weights) |

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
- **Data composition charts** — donut and Sankey diagrams showing sample composition by landscape class
- **Skewness diagnostics** — 2×2 Day|Night panels with normal distribution overlay
- **Model comparison tables** (CSV) — hierarchical block R², ΔR², AIC, BIC per analysis
- **Coefficient tables** (CSV) — OLS coefficients with clustered SEs, Wild Cluster Bootstrap *p*-values, and % change
- **Variance partitioning panels** — Day|Night stacked bar charts showing block-level R² contributions
- **Coefficient forest plots** — Day|Night horizontal panel with significance colouring (OLS and bootstrap)
- **Model metadata** (JSON) — reproducibility records per analysis/period

### Manuscript Outputs (`Notebook/07_publication_outputs.ipynb`)

Notebook 07 builds every figure and table of the SCS article and of its supplementary material, in
manuscript order. Its values come from the published dataset (v1.0.1,
`Results/05_hotspot_analysis/surface_thermal_anomaly_stakeholder_composite/`); where the dataset
holds no equivalent, from the cached results of NB01–NB06, each such read permitted per item in the
work plan, logged, and asserted against the dataset wherever the two overlap. It draws with the same
functions the analysis notebooks use (`src/visualization.py`, `src/temporal_panels.py`,
`src/pub_hotspot_tables.py`) and makes no GEE, EUMETSAT or OSM call.

Run it after NB01–NB06 (or on their cached `Results/`):

```powershell
python run_all.py --scope manuscript          # or: python scripts/build_scs_outputs.py
# or open Notebook/07_publication_outputs.ipynb and Run All
```

- **Cell order.** Setup, then the shared-inputs cell; after that any item cell runs on its own
  (Fig. 6 after Fig. 5). The notebook opens with a table of contents linking every item.
- **Checks.** Every value shown is asserted against the dataset (`check()`); every read passes a
  source guard (`read_source()`), and a forbidden source stops the run.
- **Supplementary sets** show one example per level (national, one cluster, one city); their second
  cell writes the whole set.
- **Skip logic.** A figure set already written by the current drawing code from the current inputs
  (a stamp in its folder) is not redrawn, nor is a preview newer than its files; the checks always
  run. Set `REBUILD = True` in Setup to redraw everything, e.g. after re-running NB01–NB06.

Outputs, under `Results/manuscript_outputs/`:

```
Results/manuscript_outputs/
├── main_figures/            Fig_01_study_area … Fig_15_association_effect_sizes        [.pdf/.svg]
├── supplementary_figures/   S1_population_trajectories/, S2_city_delineation_maps/, … one folder per item
├── tables/                  Table_01 … Table_05, Supp_Table_S1 … S8                    [.csv/.xlsx]
├── appendices/              Appendix_1_PLT_reference                                   [.csv/.xlsx]
├── captions.md · number_map.csv · figure_print_sizes.csv · _data_sources.csv
└── _preview/INDEX.md        monitoring: v3.0 against new previews, data sources, checks, sizes
```

Fig. 2 (the workflow) and the graphical abstract are drawn by the author outside the notebook. The
work plan is `docs/scs_rebuild/SCS_Figures_Tables_WorkPlan.md` and the running log
`docs/scs_rebuild/WORKLOG.md`.

---

## Documentation

- [docs/PROJECT_CONCEPT_NOTE.md](docs/PROJECT_CONCEPT_NOTE.md) — Unified project concept note (research context, methodology, architecture, outputs)
- [docs/MANUSCRIPT_DRAFT.md](docs/MANUSCRIPT_DRAFT.md) — Nature Cities manuscript draft (complete with all numerical results)
- [docs/manuscript_draft_elsevier.md](docs/manuscript_draft_elsevier.md) — Urban Climate / Elsevier manuscript draft (complete with all numerical results)
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

## Reproducibility & Data Availability

This repository is designed so that the public can **reproduce or replicate** the study either
end-to-end or at the manuscript-assembly stage alone.

- **Full reproduction** — run the analysis pipeline and then rebuild the manuscript artwork:
  ```powershell
  python run_all.py --scope all
  ```
  This requires GEE and EUMETSAT credentials (see *Configure Credentials*) and populates `Results/`.

- **Manuscript artwork only** — if the cached `Results/` are already present (e.g. downloaded from
  the Zenodo data archive), rebuild every figure/table/appendix in minutes, no credentials needed:
  ```powershell
  python run_all.py --scope manuscript
  # or open Notebook/07_publication_outputs.ipynb and Run All
  ```

- **Published dataset only** — rebuild the composite dataset from cached `Results/` and check
  it against the deposit, no credentials (see *Reproduce the dataset* below):
  ```powershell
  python run_all.py --scope dataset
  ```

- **Step-by-step (incremental) reproduction** — open the notebooks in order (01 → 06, then
  `Notebook/07_publication_outputs.ipynb`) in Jupyter and run them cell by cell.

### The published dataset

`scripts/build_master_summary.py` assembles a single, self-describing dataset from cached
`Results/` — every pipeline stage except the association analysis, which belongs to the research
article. It is one GeoPackage plus its data dictionary, and it carries **its own README**:

```
Results/05_hotspot_analysis/surface_thermal_anomaly_stakeholder_composite/
├── surface_thermal_anomaly_stakeholder_composite.gpkg   # all layers, ESRI:102022
├── data_dictionary.csv / .md    # one row per field: units, ranges, nulls, sensor, provenance
├── README.md                    # ← the authoritative description of the dataset
├── CHANGELOG.md, LICENSE.txt, checksums_md5.txt
Results/05_hotspot_analysis/dataset_build/   # build record, beside the deposit, not archived
Results/05_hotspot_analysis/_build_staging/  # every build lands here first (see below)
```

That README is the single place where the dataset is documented — layers and row counts, keys and
joins, CRS and coverage, input sources, what is deliberately excluded, the participant cohort rule,
anonymisation, licence and citation. It is regenerated by the build, so it cannot drift from the
data. **Read it there rather than duplicating it here.** `dataset_build/build_report.md` carries the
build record: sources per layer, decisions taken, deviations and the validation run.

Every layer carries a `scenario_id`, an eight-character digest of the configuration behind the run,
recorded in full in the `scenario_config` layer. Re-running under different settings, or for another
study year, **adds** to the package rather than overwriting it; re-running the same scenario and
year is idempotent.

### Reproduce the dataset

The build logic lives in one place, `scripts/build_master_summary.py`, and has two entry points
that call the same `build_dataset()`:

```powershell
python scripts/build_master_summary.py        # command line (also: python run_all.py --scope dataset)
# or run Notebook/05_hotspot_analysis.ipynb to its end: §14 "Build the dataset" calls it
```

A pre-flight check first confirms that every input exists (the NB01–NB05 outputs, the
population cache from `scripts/extract_population_100m.py`, the UN WUP table and
`data/reference/abbreviations.csv`) and names whatever produces a missing one; no partial
dataset is built. Every build is then written to `Results/05_hotspot_analysis/_build_staging/`
and compared with the deposit by its **content fingerprint**: a SHA-256 over every layer
(rows sorted, floats to 12 significant digits, geometry as WKB), the scenario configuration and
the data dictionary, excluding build date, commit and checksums. MD5s verify a download; the
fingerprint decides whether two builds hold the same data, because a GeoPackage can differ
byte-wise while its content is identical.

| Outcome | Meaning | What happens |
|---|---|---|
| Same fingerprint | Nothing changed | "Dataset reproduced (fingerprint identical)". Nothing is touched; staging is cleared. |
| Different content (values, or a new `scenario_id`) | An input, the code or a setting changed | QA runs on the staging build. **If it passes**, the deposit is kept whole in `Results/05_hotspot_analysis/_superseded_build_<date>/` and replaced by the staging build with all its files (GeoPackage, data dictionary, README, CHANGELOG, LICENSE, checksums written last). **If QA fails**, the deposit is not touched and staging is kept for inspection. `dataset_build/CHANGES_REPORT_<date>.md` lists every layer and field that differs, data layers first. |

**No version is named in the code.** Versions are named on Zenodo only. A deposit is identified by
its content fingerprint (`dataset_info.content_fingerprint`; `previous_fingerprint` names the
deposit it is compared with), and each CHANGELOG entry is headed by its date and fingerprint, for
example `## 2026-10-29 · fingerprint sha256:…`, followed by the deposit it is compared with.
`python scripts/build_master_summary.py --compare-only` builds and compares without running QA or
updating anything. `--normalise-line-endings` rewrites the text files of a deposit with LF and
regenerates its checksums without touching the data.

**Archived artefacts (Zenodo).** Two separate deposits, each with its own DOI:

| Deposit | Contents | DOI |
|---------|----------|-----|
| **Dataset** | `surface_thermal_anomaly_stakeholder_composite` (GeoPackage + data dictionary) | _to be added_ |
| **Software** | Citable snapshot of this repository, minted from a GitHub release | _to be added_ |

---

## License

This project is licensed under [CC-BY-4.0](LICENSE). You are free to share and adapt the material with appropriate credit.

## How to Cite

If you use this project in your research, please cite it using the metadata in [CITATION.cff](CITATION.cff):


