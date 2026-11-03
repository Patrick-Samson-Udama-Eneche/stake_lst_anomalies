# Urban surface thermal anomalies in Nigeria: A multi-source, landscape-oriented and stakeholder-informed analysis

## Overview

We model land surface temperature (LST) and map surface hot and cold spots in Nigerian cities. We combine satellite data (MODIS, ERA5-Land, MSG SEVIRI), a stakeholder survey from the workshops we organised, and the physiographic landscape typology of Nigeria to identify, quantify and corroborate persistent heat events and surface thermal anomalies.

**Study cities:** the 67 Nigerian cities of at least 300,000 inhabitants in the UN World Urbanization Prospects. Eleven of them lie within the urban core of a larger neighbour and merge into it, which leaves 56 study cities (the selection is set in `config.py`).  
**Test cities:** Lagos, Abuja, Kano, Jos, Port Harcourt  
**Stakeholders:** 105 participants from 21 cities in 10 typology clusters  
**Period:** long-term LST trends over 2006–2025, and persistent heat events and surface spots in 2024  

---

## Valid City Names (67 cities of at least 300,000, giving 56 study cities)

The pipeline uses **67 cities** from the UN WUP dataset with population ≥300k (2024 estimates). Notebook 01 merges the 11 that lie within a larger neighbour's urban core, leaving **56 study cities**. Spelling and capitalisation must match exactly, and the runner flags typing errors and suggests corrections.

<details>
<summary>Click to expand full list (67 cities, sorted alphabetically)</summary>

| # | City | # | City | # | City | # | City |
|---|------|---|------|---|------|---|------|
| 1 | Aba | 18 | Erin-osun | 35 | Kano | 52 | Owerri |
| 2 | Abakaliki | 19 | Gamboru | 36 | Katsina | 53 | Oyigbo |
| 3 | Abeokuta | 20 | Gboko | 37 | KUNDULUN | 54 | Oyo |
| 4 | Aboh | 21 | Gusau | 38 | Lagos | 55 | Port Harcourt |
| 5 | Abonnema | 22 | Gwagwalada | 39 | Lokoja | 56 | Potiskum |
| 6 | Abuja | 23 | Ibadan | 40 | Madalla | 57 | Saki |
| 7 | Ado Ekiti | 24 | Ife | 41 | Maiduguri | 58 | Sapele |
| 8 | Akure | 25 | Ijebu-Ode | 42 | Makurdi | 59 | Sokoto |
| 9 | Asaba | 26 | Ikare | 43 | Minna | 60 | Titi |
| 10 | Bauchi | 27 | Ikere-Ekiti | 44 | Nsukka | 61 | Ughelli |
| 11 | Benin City | 28 | Ikorodu | 45 | Ogale | 62 | Umuahia |
| 12 | Bida | 29 | Ikot Ekpene | 46 | Ogbomosho | 63 | Uyo |
| 13 | Bonny | 30 | Ilesa | 47 | Ondo | 64 | Warri |
| 14 | Calabar | 31 | Ilorin | 48 | Onitsha | 65 | Yenagoa |
| 15 | Daura | 32 | Iseyin | 49 | Oron | 66 | Yola |
| 16 | Dere | 33 | Jos | 50 | Oshogbo | 67 | Zaria |
| 17 | Enugu | 34 | Kaduna | 51 | Otite |  |  |

> **Note:** 11 cities merge into a neighbouring study city (Ikorodu, for example, merges into Lagos), which leaves 56 study cities.

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

**Prerequisites:** Python **3.12.10**, Git, and (for the GEE/EUMETSAT notebooks) internet access.

We produced the results in an environment named **`geovenv`** with Python 3.12.10. `requirements.lock`
holds its exact package versions for Windows, Linux and macOS, while `requirements.txt` lists the packages
without fixed versions for new scenarios. Any one of the four routes below installs the same versions.

```powershell
git clone <repo-url>
cd stake_lst_anomalies

# Route 1: uv (fastest)
uv venv --python 3.12.10 geovenv
uv pip sync requirements.lock --python geovenv

# Route 2: pip
py -3.12 -m venv geovenv                 # Linux / macOS: python3.12 -m venv geovenv
.\geovenv\Scripts\python.exe -m pip install -r requirements.lock

# Route 3: conda-forge (if the pip GDAL wheels fail on your machine)
conda env create -f environment.yml      # then: conda activate stake_lst_anomalies

# Route 4: Docker (no local install, see "5. Docker")
docker build -t stake_lst_anomalies .
```

Then activate the environment (`.\geovenv\Scripts\Activate.ps1` on Windows, `source geovenv/bin/activate`
on Linux and macOS) and register it as the Jupyter kernel `python3`, which `run_all.py` and the notebooks
use:

```powershell
python -m ipykernel install --user --name python3 --display-name "Python (geovenv)"
```

> **Always activate the environment first**, and then launch `jupyter lab` or run `python run_all.py`
> from it. Every run of `run_all.py` records the environment in `Results/_provenance/`.
>
> **Windows with Smart App Control:** Windows may refuse a package's DLL with "An Application Control
> policy has blocked this file". Importing again often clears it (we saw this with `statsmodels` and
> `geemap`). conda-forge's numpy stays blocked, so after `conda env create` we run
> `python -m pip install --force-reinstall --no-deps numpy==2.4.4`, the PyPI build of the same version.
>
> **To check an install at any time:** `python scripts/check_project.py`. It reports PASS, FAIL or NOTE for
> the environment, code, dataset, outputs and repository. It makes no remote call and runs no notebook.
>
> **Before committing from a clone:** run `python scripts/strip_outputs.py install` once. Git then stores
> every notebook without its outputs (your copy keeps them) and refuses a commit that would add figures,
> results or secrets. The repository holds code and text only, and the figures and tables are published
> in the article.

### 2. Configure Credentials
See [secrets/README.md](secrets/README.md) for the file formats and set-up.

| Credential | Required By | Location |
|-----------|------------|----------|
| GEE Service Account | Notebooks 01, 03, 04 and the population step (`scripts/extract_population_100m.py`, run with Notebook 05) | `secrets/gee_service_account.json` |
| EUMETSAT API Keys | Notebook 04 (SEVIRI) | `secrets/eumetsat_credentials.json` |

### 3. Run the Analysis

**Option A: interactive, in Jupyter Lab**
```powershell
jupyter lab
# Run the notebooks in order: 01, 02, 03, 04, 05, 06 and then 07_publication_outputs
```

**Option B: automated, with the runner script**
```powershell
# Run the pipeline (it asks what to generate, as described below)
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
| **1. Manuscript outputs only** | `manuscript` | `Notebook/07_publication_outputs.ipynb`, which assembles all manuscript figures and tables **from cached `Results/`** in minutes, without GEE or OSM |
| **2. All project outputs** | `all` | The analysis notebooks 01 to 05 (the last section of NB05 builds and checks the published dataset), then 06 and the manuscript assembly |
| **3. Analytic outputs only** | `analytic` | The analysis notebooks 01–06 (no manuscript assembly) |
| **4. Published dataset only** | `dataset` | `build_dataset()` from `scripts/build_master_summary.py`, called directly **from cached `Results/`** without running a notebook. The QA checks run if the deposit changed. It needs no credentials and takes about a minute. |

```powershell
# Skip the prompt by passing the scope explicitly:
python run_all.py --scope manuscript   # rebuild manuscript artwork from cache (fast)
python run_all.py --scope dataset      # rebuild the published dataset from cache (fast)
python run_all.py --scope all          # full reproduction, end to end
python run_all.py --scope analytic     # analysis only
```
> In a non-interactive shell (CI, Docker) there is no prompt and `all` is assumed. Pass `--scope` to
> choose another scope.

### 4. Running Tests
```powershell
# Run all tests
pytest tests/ -v

# Run a specific test module
pytest tests/test_config.py -v
```

### 5. Docker (Optional)

The image holds Python 3.12.10 and the packages of `requirements.lock`. The data, `Results/` and the
secrets are mounted when the image runs.

```powershell
docker build -t stake_lst_anomalies .                    # build
docker run --rm stake_lst_anomalies pytest tests -q      # run the tests in the image
docker compose up lab                                    # Jupyter Lab on http://localhost:8888
docker compose run --rm reproduce                        # rebuild the manuscript outputs from Results/
```

The rebuild reads only `data/inputs/` and `Results/01_…` to `Results/06_…`. It writes the executed
notebook to `Results/_provenance/`, where its last output gives the number of checks passed.

Docker cannot read files that a cloud service keeps online only, so we run it from a local copy of the
project rather than a synced folder. The image has no Arial, so figures drawn in it use DejaVu Sans,
while the values stay the same.

---

## Notebook Pipeline

All notebooks live in `Notebook/` and must be run in order, because each one builds on the outputs of the
earlier ones. They depend on one another as follows:

1. `01_AOI_delineation` comes first, and Notebooks 02, 03 and 04 each build on its outputs.
2. `02_stakeholder_analysis` analyses the stakeholder survey.
3. `03_temporal_analysis_months_annual` also reads the attendee list of Notebook 02.
4. `04_temporal_analysis_daily` produces the SEVIRI composites and the SUHII that Notebook 05 reads.
5. `05_hotspot_analysis` builds on Notebook 04. It includes the population step and builds the dataset.
6. `06_hotspot_modelling` builds on Notebook 05.
7. `07_publication_outputs` assembles the manuscript items from the results of the six notebooks before it.

| # | Notebook | Purpose | External APIs | Inputs |
|---|---------|---------|--------------|--------|
| 01 | `01_AOI_delineation.ipynb` | Delineates three zones per city from GHS-SMOD (urban core, background reference area and city region) and removes JRC surface water from them. It also downloads OpenStreetMap roads and places, attaches each city's 2024 UN WUP population and landscape cluster, draws the overview, zone and population-trend figures, and exports the zones as Earth Engine assets | GEE, OSM | UN WUP 2025 cities, Nigeria boundary, landscape typology |
| 02 | `02_stakeholder_analysis.ipynb` | Stakeholder survey: who took part, from which cities and clusters, and how they perceive warming | none | `master_composite.csv`, NB01's `city_cluster25_lookup.csv` |
| 03 | `03_temporal_analysis_months_annual.ipynb` | Monthly and annual MODIS LST for the three zones, 2006–2025, and their long-term trends per city, cluster and nation | GEE (MODIS) | NB01's zones and assets, NB02's attendee list |
| 04 | `04_temporal_analysis_daily.ipynb` | Daily MODIS and ERA5-Land LST in 2024, persistent heat events, one selected event per city and period, and its MSG-SEVIRI composites | GEE, EUMETSAT | NB01's zones and assets |
| 05 | `05_hotspot_analysis.ipynb` | Surface hot and cold spot detection (Gi\*), KDE contours, landscape enrichment, population within spots and stakeholder corroboration. Its last section (§14) builds the published dataset | none (the population step uses GEE) | NB01's zones, NB04's SEVIRI composites and SUHII, the survey |
| 06 | `06_hotspot_modelling.ipynb` | Association of the landscape typology (Cluster25) and of its elements (climate zone, geology, elevation) with spot occurrence (Monte Carlo χ², Cramér's V), SUHII and spot area (Kruskal–Wallis, η², Dunn post-hoc), Holm-corrected across elements | none | NB05's spot layer, NB04's SUHII |
| pub | `07_publication_outputs.ipynb` | **Manuscript assembly**: re-renders every manuscript figure, supplementary figure, table and appendix from cached `Results/`, in manuscript order, without GEE or OSM | none | Cached `Results/` from 01–06 |
| data | `scripts/build_master_summary.py` | **Published dataset assembly**: builds the composite GeoPackage and its data dictionary from cached `Results/` and then runs the QA suite, without GEE or OSM | none | Cached `Results/` from 01–05 |

> `run_all.py` runs the analysis notebooks 01–06 and then the manuscript-assembly notebook
> `07_publication_outputs.ipynb`. The dataset build runs within Notebook 05 (§14), and
> `--scope dataset` runs it on its own, as `--scope manuscript` does for Notebook 07. Both read only
> cached `Results/` and need no credentials. Registry entries may point at a notebook (`file`) or a
> Python script (`script`).

### Run times

Measured on a laptop with an Intel Core i7-8650U, 16 GB of RAM and Windows 11 (3 November 2026):

| Notebook | Time | Notes |
|----------|------|-------|
| **01** AOI delineation | about 5 min for two cities | downloads OpenStreetMap, GHS-SMOD and JRC water, and exports the Earth Engine assets |
| **02** Stakeholder analysis | under 1 min | no download |
| **03** Monthly and annual LST | 3 to about 40 min per city | MODIS 2006–2025 through Earth Engine, taking longer for cities with complex outlines |
| **04** Daily LST | 28 min for two cities | ERA5-Land and MODIS through Earth Engine, MSG-SEVIRI from EUMETSAT |
| **05** Hotspot analysis | 18–20 min for all 56 cities | with the downloads in place |
| **06** Typology association | 2 min | |
| **07** Publication outputs | 6–15 min | |

A full run for all 56 cities takes many hours, most of them in Notebooks 03 and 04. Our test run with two
cities (`--cities`) took about an hour. [REPRODUCIBILITY.md](REPRODUCIBILITY.md) gives the details.

### City Selection Configuration

City selection is controlled in **`config.py`** via `CITY_SELECTION_MODE`. Edit this setting to choose which cities to process:

| Mode | Description | Cities |
|------|-------------|--------|
| `"ALL"` | All cities in the UN WUP table | 67 cities |
| `"ABOVE_1M"` | Cities with population ≥ 1 million | 17 cities |
| `"ABOVE_500K"` | Cities with population ≥ 500k | 37 cities |
| `"ABOVE_300K"` | Cities with population ≥ 300k (default) | 67 cities, merged into 56 study cities |
| `"TEST"` | Quick development/debugging runs | Lagos, Abuja, Kano, Jos, Port Harcourt |
| `"SPECIFIC"` | User-specified custom selection | Any of the 67 cities |

```python
# In config.py, choose one of these lines:
CITY_SELECTION_MODE = "ALL"        # All 67 cities in the UN WUP table
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

Notebook 01 takes its cities from `CITY_SELECTION_MODE` (`python run_all.py --cities …` sets `"SPECIFIC"` for every
notebook it runs). The later notebooks find the cities in the outputs of the earlier ones, so start from an empty
`Results/` when you change the set of cities.

---

## Project Structure

```
stake_lst_anomalies/
├── run_all.py                 # Runs the notebooks in order (and the population step)
├── config.py                  # Paths, parameters, CRS, city selection
├── requirements.lock          # Exact package versions (Python 3.12.10), with requirements.txt as the loose list
├── environment.yml            # conda route
├── Dockerfile, docker-compose.yml
├── REPRODUCIBILITY.md         # How to install, run and check
├── CITATION.cff, .zenodo.json, LICENSE
│
├── Notebook/                  # All notebooks (analysis 01–06 + manuscript assembly)
│   ├── 01_AOI_delineation.ipynb
│   ├── 02_stakeholder_analysis.ipynb
│   ├── 03_temporal_analysis_months_annual.ipynb
│   ├── 04_temporal_analysis_daily.ipynb
│   ├── 05_hotspot_analysis.ipynb
│   ├── 06_hotspot_modelling.ipynb
│   └── 07_publication_outputs.ipynb         # Assembles manuscript artwork from cached Results/
│
├── scripts/
│   ├── build_master_summary.py   # Builds the published dataset from cached Results/ (also run by NB05 §14)
│   ├── qa_master_summary.py      # QA suite over the built dataset
│   ├── extract_population_100m.py  # Sums GHS-POP inside each spot and zone (Earth Engine)
│   ├── compute_hitrate.py        # Stakeholder hit rates (NB05 and the dataset build)
│   ├── env_report.py             # Records the environment of every run in Results/_provenance/
│   ├── build_scs_outputs.py      # Runs Notebook 07
│   ├── make_cluster_labels.py    # Writes the cluster label lookup
│   ├── compare_to_archive.py     # Compares a dataset build with the published v1.0.0
│   ├── check_project.py          # Reports the state of the environment, code, dataset and outputs
│   └── strip_outputs.py          # Keeps notebook outputs, figures, results and secrets out of git
│
├── src/                       # Python modules used by the notebooks
│   ├── aoi_utils.py, dual_zone_aoi_utils.py, water_download_utils.py   # zones and water (NB01, and aoi_utils also in NB03)
│   ├── gee_utils.py           # Earth Engine: start-up, MODIS and ERA5-Land extraction (NB01, NB03, NB04)
│   ├── temporal_analysis.py   # LST trend statistics (NB03)
│   ├── daily_analysis_utils.py  # Daily series and persistent heat events (NB04)
│   ├── seviri_processing_utils.py  # EUMETSAT MSG-SEVIRI download and processing (NB04)
│   ├── data_io.py             # Data loading, export, spatial operations
│   ├── visualization.py       # Plotting functions (about 16,700 lines, used by NB01–NB04 and NB07)
│   ├── pub_figures.py, pub_hotspot_tables.py, temporal_panels.py, scs_style.py   # NB07
│   ├── decision_tree_utils.py, temporal_analysis_utils.py   # covered by the tests, not called by the notebooks
│   └── modelling_utils.py     # the earlier regression approach to NB06, no longer used
│
├── tests/                     # pytest suite (59 tests)
│
├── data/
│   ├── inputs/
│   │   ├── geospatial_features/    # Boundary, typology, UN WUP table, OSM extracts (see "Data in this repository")
│   │   └── stakeholder_survey/     # master_composite.csv (1,194 rows × 96 cols)
│   ├── reference/                  # abbreviations.csv
│   └── outputs/                    # The run log of run_all.py (not in git)
│
├── Results/                   # Pipeline outputs and caches (git-ignored)
│   ├── 01_aoi_delineation/         # Zones, population and cluster tables, with <City>/figures/ and <City>/osm/
│   ├── 02_stakeholder_analysis/    # Survey maps, perception charts, stakeholder figures
│   ├── 03_… / 04_… / 06_…          # Temporal, daily and association outputs
│   ├── 05_hotspot_analysis/        # Spots, contours, population, and the dataset:
│   │   ├── surface_thermal_anomaly_stakeholder_composite/
│   │   │   ├── surface_thermal_anomaly_stakeholder_composite.gpkg   # 18 layers, the dataset
│   │   │   ├── data_dictionary.csv / .md                            # one table per layer
│   │   │   └── README.md, CHANGELOG.md, LICENSE.txt, checksums_md5.txt
│   │   └── dataset_build/          # build record: reports and checks (not published)
│   └── manuscript_outputs/         # Manuscript figures/tables/appendices (see Outputs Summary)
│
└── secrets/                   # API credentials (git-ignored)
    ├── gee_service_account.json
    └── eumetsat_credentials.json
```

---

## Key Configuration (`config.py`)

| Parameter | Value | Description |
|-----------|-------|-------------|
| `PROJECT_STUDY_YEAR` | 2024 | Study year of the daily analysis, the events and the spots |
| `TEMPORAL_CONFIG['years']` | 2006–2025 | Years of the long-term MODIS series (NB03) |
| `CITY_SELECTION_MODE` | `"ABOVE_300K"` | Cities to process (see City Selection Configuration) |
| `BRA_BUFFER_M` | 10,000 m | The background reference area: the envelope of the urban core buffered by this distance |
| `HOTSPOT_PERCENTILE_HOT` / `HOTSPOT_PERCENTILE_COLD` | 90 / 10 | LST percentiles of the hot and cold candidate pixels (NB05) |
| `HOTSPOT_FDR_ALPHA` | 0.05 | Benjamini–Hochberg false discovery rate for Gi\* (NB05) |
| `KDE_CONTOUR_LEVELS` | 0.50, 0.75, 0.90 | Nested contour levels L50 ⊃ L75 ⊃ L90 of each spot (NB05) |
| `FIGURE_DPI` | 300 | Resolution of saved raster figures |

`config.py` also holds settings from the earlier regression approach to Notebook 06 (`HIERARCHY_BLOCKS`,
`OLS_CLUSTERED_CONFIG`, `WILD_BOOTSTRAP_CONFIG`), which no notebook uses.

---

## Outputs Summary

### Notebook 05: Hotspot Analysis Outputs
- **Spot layer** `all_cities_spots.geojson` and `.csv` (EPSG:4326, computed in ESRI:102022): the L50 footprint
  of every surface hot and cold spot, with its landscape, LST, SUHII and population attributes.
- **`master_thermal_spots.gpkg`**: the L50/L75/L90 contours, the city zones and the stakeholder hot and cold points.
- **Summary tables**: per spot, per cluster and national, with the population half-donut tables for cities and
  clusters.
- **Per-city maps** (§11a): the LST raster with the L50/L75/L90 contours, the urban core and the stakeholder points.
- **A4 grids** (§11a2): all 56 cities, by day and by night.
- **Gi\* distribution plots** (§11b): the Z-score distributions of the hot and the cold spots.
- **Contour area charts** (§11c): spot area by landscape cluster.
- **Population half-donuts** (§11d): residents within surface hot and cold spots, per city, cluster and nation.
- **National summary maps** (§11e): proportional population circles over the Cluster25 map, for hot and for cold
  spots.
- **Stakeholder perception chart** (§11f): Q60 (diurnal severity) and Q61 (ten-year warming) by Cluster25.
- **Descriptive charts** (§12b, §12c): spot area, population within spots and core compactness by cluster, and
  the ranked spot area per city and per cluster.
- **The published dataset** (§14), in `surface_thermal_anomaly_stakeholder_composite/`.

### Notebook 06: Typology Association Outputs

Units: 56 cities and 185 spots (95 hot, 90 cold). With a median of 3–5 cities per cluster, regression inference
is unreliable, so the notebook uses non-parametric association tests.

- **Normality diagnostics** (CSV): Shapiro–Wilk and D'Agostino–Pearson tests of SUHII and spot area.
- **Part A tables** (CSV): the typology against spot occurrence (Monte Carlo χ², Cramér's V), SUHII and area (Kruskal–Wallis, η²).
- **Part B tables** (CSV): the same tests for each typology element (climate, geology, elevation), Holm-corrected.
- **Synthesis tables** (CSV): Cramér's V between the typology and each element, the typology against its best
  single element for every outcome, and the master synthesis table of all results.
- **Figures**: effect-size heatmaps, the cluster thermal profile heatmap, distribution boxplots by cluster and by
  element, Dunn post-hoc heatmaps, and the forest plot of all effect sizes.

### Manuscript Outputs (`Notebook/07_publication_outputs.ipynb`)

Notebook 07 builds every figure and table of the SCS article and its supplementary material, in
manuscript order. We take the values from the published dataset (v1.0.1,
`Results/05_hotspot_analysis/surface_thermal_anomaly_stakeholder_composite/`), and from the cached
results of NB01–NB06 only where the dataset holds no equivalent, checking them against the dataset
wherever the two overlap. The notebook draws with the functions the analysis notebooks use
(`src/visualization.py`, `src/temporal_panels.py`, `src/pub_figures.py`,
`src/pub_hotspot_tables.py`) and makes no GEE,
EUMETSAT or OSM call.

The figures and tables are published with the article, which is their version of record, so they are not
in this repository, and Notebook 07 rebuilds them. It needs the results of NB01–NB06 under `Results/`, which
are not in git either. Running NB01–NB06 with your own Earth Engine and EUMETSAT credentials produces them (see
[REPRODUCIBILITY.md](REPRODUCIBILITY.md)).

Run it after NB01–NB06 (or on their cached `Results/`):

```powershell
python run_all.py --scope manuscript
# or open Notebook/07_publication_outputs.ipynb and Run All
```

- **Cell order.** Run Setup first and the shared-inputs cell next. After that, any item cell runs on its
  own, except that Fig. 6 runs after Fig. 5 and Supp. Table S6 after Table 3. The notebook opens with a
  table of contents.
- **Checks.** Every value shown that the dataset also holds is asserted against it with `check()`. Every
  file read is logged by `read_source()`, and a forbidden source stops the run.
- **Supplementary sets** show one example per level (national, one cluster, one city), and their
  second cell writes the whole set.
- **Skip logic.** A figure set already written by the current drawing code from the current inputs
  is not redrawn. Set `REBUILD = True` in Setup to redraw everything, e.g. after re-running NB01–NB06.

Outputs, under `Results/manuscript_outputs/`:

```
Results/manuscript_outputs/
├── main_figures/            Fig_01_study_area … Fig_15_association_effect_sizes        [.pdf/.svg]
├── main_tables/             Table_01 … Table_05                                        [.csv/.xlsx]
├── supplementary_figures/   S1_population_trajectories/ … S11_city_perception/, one folder per item
├── supplementary_tables/    Supp_Table_S1 … S8                         [.csv, plus .xlsx except S3, S4, S6]
└── captions.md · figure_print_sizes.csv · _data_sources.csv
```

We draw Fig. 2 (the workflow) and the graphical abstract outside the notebook.

---

## Documentation

- [secrets/README.md](secrets/README.md) describes the credential files and how to set them up.
- [secrets/gee_service_account.json.example](secrets/gee_service_account.json.example) is the template of the
  Earth Engine service-account key.
- [secrets/eumetsat_credentials.json.example](secrets/eumetsat_credentials.json.example) is the template of the
  EUMETSAT API key.

---

## Current Status

| Phase | Status | Description |
|-------|--------|-------------|
| **Phase 1** | Complete | AOI delineation and stakeholder analysis |
| **Phase 2** | Complete | Monthly/annual LST temporal analysis |
| **Phase 3** | Complete | Daily LST analysis (MODIS, ERA5, SEVIRI) |
| **Phase 4** | Complete | Surface hot and cold spot detection and stakeholder corroboration |
| **Phase 5** | Complete | Association of the landscape typology with spot occurrence, SUHII and area (Notebook 06) |
| **Phase 6** | Complete | Manuscript figures and tables (Notebook 07) |

---

## Reproducibility & Data Availability

**[REPRODUCIBILITY.md](REPRODUCIBILITY.md) is the full guide:** the four install routes and how we tested
them, the credentials and downloads, the ways to reproduce, run times, and how to check that a run worked.

This repository is designed so that the public can **reproduce or replicate** the study either
end-to-end or at the manuscript-assembly stage alone.

- **Full reproduction.** Run the analysis pipeline and then rebuild the manuscript artwork:
  ```powershell
  python run_all.py --scope all
  ```
  This requires GEE and EUMETSAT credentials (see *Configure Credentials*) and populates `Results/`.

- **Manuscript artwork only.** Once your own run of NB01–NB06 has filled `Results/`, this command rebuilds
  every figure, table and appendix in minutes and needs no credentials:
  ```powershell
  python run_all.py --scope manuscript
  # or open Notebook/07_publication_outputs.ipynb and Run All
  ```

- **Published dataset only.** This command rebuilds the composite dataset from cached `Results/` and
  checks it against the deposit, without credentials (see *Reproduce the dataset* below):
  ```powershell
  python run_all.py --scope dataset
  ```

- **Step-by-step reproduction.** Open the notebooks in Jupyter in order, from 01 to 06 and then
  `Notebook/07_publication_outputs.ipynb`, and run them cell by cell. On a first run, Notebook 05 stops after
  writing its spots and zones. Run `python scripts/extract_population_100m.py` at that point, and then run
  Notebook 05 again.

### The published dataset

`scripts/build_master_summary.py` assembles a single, self-describing dataset from cached
`Results/`. It covers every pipeline stage except the association analysis, which belongs to the
research article. It is one GeoPackage plus its data dictionary, and it carries **its own README**:

```
Results/05_hotspot_analysis/surface_thermal_anomaly_stakeholder_composite/
├── surface_thermal_anomaly_stakeholder_composite.gpkg   # all layers, ESRI:102022
├── data_dictionary.csv / .md    # one row per field: units, ranges, nulls, sensor, provenance
├── README.md                    # the authoritative description of the dataset
├── CHANGELOG.md, LICENSE.txt, checksums_md5.txt
Results/05_hotspot_analysis/dataset_build/   # build record, beside the deposit, not archived
Results/05_hotspot_analysis/_build_staging/  # every build lands here first (see below)
```

That README is the single place where the dataset is documented. It covers the layers and row counts,
keys and joins, CRS and coverage, input sources, what is deliberately excluded, the participant cohort
rule, anonymisation, licence and citation. The build regenerates it, so it cannot drift from the
data. **Read it there rather than duplicating it here.** `dataset_build/build_report.md` carries the
build record: sources per layer, decisions taken, deviations and the validation run.

Every layer carries a `scenario_id`, an eight-character digest of the configuration behind the run,
recorded in full in the `scenario_config` layer. Re-running under different settings, or for another
study year, **adds** to the package rather than overwriting it, while re-running the same scenario
and year leaves the package as it is.

### Reproduce the dataset

The build logic lives in one place, `scripts/build_master_summary.py`, and has two entry points
that call the same `build_dataset()`:

```powershell
python scripts/build_master_summary.py        # command line (also: python run_all.py --scope dataset)
# or run Notebook/05_hotspot_analysis.ipynb to its end: §14 "Build the dataset" calls it
```

A pre-flight check first confirms that every input exists (the NB01–NB05 outputs, the
population cache from `scripts/extract_population_100m.py`, the UN WUP table and
`data/reference/abbreviations.csv`). If one is missing, the check names what produces it and no
partial dataset is built. Every build is then written to `Results/05_hotspot_analysis/_build_staging/`
and compared with the deposit by its **content fingerprint**: a SHA-256 over every layer
(rows sorted, floats to 12 significant digits, geometry as WKB), the scenario configuration and
the data dictionary, excluding build date, commit and checksums. MD5s verify a download, whereas the
fingerprint decides whether two builds hold the same data, because a GeoPackage can differ
byte-wise while its content is identical.

| Outcome | Meaning | What happens |
|---|---|---|
| Same fingerprint | Nothing changed | "Dataset reproduced (fingerprint identical)". Nothing is touched, and staging is cleared. |
| Different content (values, or a new `scenario_id`) | An input, the code or a setting changed | QA runs on the staging build. **If it passes**, the deposit is kept whole in `Results/05_hotspot_analysis/_superseded_build_<date>/` and replaced by the staging build with all its files (GeoPackage, data dictionary, README, CHANGELOG, LICENSE, checksums written last). **If QA fails**, the deposit is not touched and staging is kept for inspection. `dataset_build/CHANGES_REPORT_<date>.md` lists every layer and field that differs, data layers first. |

**No version is named in the code.** Versions are named on Zenodo only. A deposit is identified by
its content fingerprint, stored in `dataset_info.content_fingerprint`, and `previous_fingerprint`
names the deposit it is compared with. Each CHANGELOG entry is headed by its date and fingerprint,
for example `## 2026-10-29 · fingerprint sha256:…`, followed by the deposit it is compared with.
`python scripts/build_master_summary.py --compare-only` builds and compares without running QA or
updating anything. `--normalise-line-endings` rewrites the text files of a deposit with LF and
regenerates its checksums without touching the data.

**Archived artefacts (Zenodo).** Two separate deposits, each with its own DOI:

| Deposit | Contents | DOI |
|---------|----------|-----|
| **Dataset** | `surface_thermal_anomaly_stakeholder_composite` (GeoPackage + data dictionary) | [10.5281/zenodo.23777933](https://doi.org/10.5281/zenodo.23777933) for v1.0.1, and [10.5281/zenodo.23050559](https://doi.org/10.5281/zenodo.23050559) for all versions |
| **Software** | Citable snapshot of this repository, archived automatically from each GitHub release | [10.5281/zenodo.23924335](https://doi.org/10.5281/zenodo.23924335) for v1.0.0, and [10.5281/zenodo.23924334](https://doi.org/10.5281/zenodo.23924334) for all versions |

---

## Data in this repository

The repository holds no satellite data, which the notebooks download with your own credentials. It does hold
these inputs, each with its own source and terms:

| File (under `data/`) | What it is | Source and terms | Read by |
|---|---|---|---|
| `inputs/geospatial_features/boundary_Nigeria.geojson` | National boundary of Nigeria | Common Operational Dataset of administrative boundaries for Nigeria (COD-AB): Office of the Surveyor General of the Federation of Nigeria, via UN OCHA and the Humanitarian Data Exchange ([download](https://data.humdata.org/dataset/81ac1d38-f603-4a98-804d-325c658599a3/resource/7e30ec96-7f29-4ee8-9f4c-77633b353cbb/download/nga_admin_boundaries.geojson.zip)). Licence: Creative Commons Attribution for Intergovernmental Organisations (CC BY-IGO). | NB01, NB02, NB05, NB07 |
| `inputs/geospatial_features/landscape_ch_polygons_with_class_metrics.geojson`, `inputs/geospatial_features/urban_landscape_typology_Nigeria.geojson` | Physiographic landscape typology of Nigeria | P.S.U. Eneche, F. Atun, Y. Zeng, K. Pfeffer (2025). *Dataset Associated with the Landscape Character Assessment of Nigeria: A Machine-assisted Learning Approach.* 4TU.ResearchData. [doi:10.4121/f7e4e2f9-a97c-4259-86bc-4840bc95be2f](https://doi.org/10.4121/f7e4e2f9-a97c-4259-86bc-4840bc95be2f). Terms as published there. | NB07, `config.py`, scripts |
| `inputs/geospatial_features/Major_cities_population_Nigeria_WUP_2025.csv` | City populations, 1975–2050 | United Nations (2025). *World Urbanization Prospects: Summary of Results – Dataset*, [WUP2025-F21-DEGURBA-Cities_Pop.xlsx](https://population.un.org/wup/assets/Download/Cities/WUP2025-F21-DEGURBA-Cities_Pop.xlsx) (accessed 3 September 2026). © United Nations. | NB01, NB03, the dataset build |
| `inputs/geospatial_features/City_*/` (14 files) | OpenStreetMap built-up areas, roads and places for Abuja, Jos, Kano, Lagos and Port Harcourt, made by `OSM_features.ipynb` before 15 February 2026 | © OpenStreetMap contributors, available under the [Open Database License 1.0](https://www.openstreetmap.org/copyright). | not read (Notebook 01 downloads the OpenStreetMap features it needs) |
| `inputs/stakeholder_survey/master_composite.csv` | The responses to the stakeholder survey of this study, anonymised (KoboToolbox, twelve virtual workshops, 16 May 2024 – 22 January 2025) | CC BY 4.0, as this repository. The questionnaire: P.S.U. Eneche, F. Atun, Y. Zeng, K. Pfeffer (2025). *Survey Questionnaire: Urban Heating and Strategic Greening of Nigerian Cities.* [doi:10.5281/zenodo.14989792](https://doi.org/10.5281/zenodo.14989792) | NB02, NB05, NB07, the dataset build |
| `reference/abbreviations.csv` | The abbreviations used in the dataset | CC BY 4.0, as this repository | the dataset build and its QA |

---

## License

The code and this project's own data are licensed under [CC-BY-4.0](LICENSE). You are free to share and adapt
the material with appropriate credit. The third-party inputs listed under *Data in this repository* keep their own
terms.

## How to Cite

If you use this project in your research, please cite the version of the code you used and the dataset. The
metadata of the code is in [CITATION.cff](CITATION.cff), and GitHub's *Cite this repository* button formats it.

- **Code, v1.0.0:** Eneche, P. S. U., Zeng, Y., Atun, F., & Pfeffer, K. (2026). *Urban surface thermal anomalies in Nigeria: A multi-source, landscape-oriented and stakeholder-informed analysis* (Version v1.0.0)
  [Software]. Zenodo. [https://doi.org/10.5281/zenodo.23924335](https://doi.org/10.5281/zenodo.23924335). The DOI [10.5281/zenodo.23924334](https://doi.org/10.5281/zenodo.23924334)
  stands for all versions and always resolves to the latest one.
- **Dataset, v1.0.1:** Eneche, P. S. U., Zeng, Y., Atun, F., & Pfeffer, K. (2026). *Dataset associated with the
  analysis of surface thermal anomalies, population exposure and stakeholder insights across major Nigerian cities*
  (Version 1.0.1) [Data set]. Zenodo. [https://doi.org/10.5281/zenodo.23777933](https://doi.org/10.5281/zenodo.23777933)


