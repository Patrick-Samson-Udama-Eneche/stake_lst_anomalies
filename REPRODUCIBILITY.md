# Reproducing the results

This guide shows how to reproduce the results of *Urban surface thermal anomalies in Nigeria*: how to install
the environment, which accounts you need, how to run each case and how to check that it worked.

The repository holds the code and a few small inputs (see *Data in this repository* in the [README](README.md)).
It holds no satellite data: the notebooks download it with your own Google Earth Engine and EUMETSAT credentials.
The figures and tables are published with the article, and Notebook 07 rebuilds them. The dataset is on Zenodo.

| To … | You need | Where | Time |
|---|---|---|---|
| **A.** re-run the study from the sources | Earth Engine and EUMETSAT credentials | [section 3](#a-re-run-the-study-from-the-sources) | hours |
| **B.** rebuild the article's figures and tables | the results of A | [section 4](#b-rebuild-the-articles-figures-and-tables) | 6–15 min |
| **C.** run a new scenario (other cities, year or thresholds) | credentials, an edited `config.py` | [section 5](#c-run-a-new-scenario) | hours |
| **D.** use only the published dataset | the dataset | [section 6](#d-use-only-the-published-dataset) | — |

## What is where

| Item | Where |
|---|---|
| Code | this repository; every release is archived on Zenodo (DOI _to be added_) |
| Small inputs (boundary, typology, UN city populations, survey responses) | `data/`, with their sources and terms in the README |
| Satellite and settlement data | downloaded by the notebooks (table below) |
| Dataset (v1.0.1) | Zenodo, [10.5281/zenodo.23777933](https://doi.org/10.5281/zenodo.23777933) (all versions: [10.5281/zenodo.23050559](https://doi.org/10.5281/zenodo.23050559)) |
| Figures and tables | the article (DOI _to be added_), their version of record |

The notebooks download:

| Data | Notebook | Access | Reference |
|---|---|---|---|
| GHS-SMOD R2023A, settlement model | 01 | Earth Engine | Schiavina, Melchiorri, Pesaresi (2023), [doi:10.2905/A0DF7A6F-49DE-46EA-9BDE-563437A6E2BA](https://doi.org/10.2905/A0DF7A6F-49DE-46EA-9BDE-563437A6E2BA) |
| Global Surface Water v1.4 | 01 | Earth Engine | Pekel et al. (2016), Nature 540, 418–422, [doi:10.1038/nature20584](https://doi.org/10.1038/nature20584) |
| OpenStreetMap features | 01 | Overpass API, no account | © OpenStreetMap contributors, [ODbL](https://www.openstreetmap.org/copyright) |
| MODIS Aqua MYD11A1 v061 | 03, 04 | Earth Engine | Wan, Hook, Hulley (2021), [doi:10.5067/MODIS/MYD11A1.061](https://doi.org/10.5067/MODIS/MYD11A1.061) |
| ERA5-Land hourly | 04 | Earth Engine | Muñoz-Sabater et al. (2021), Earth Syst. Sci. Data 13, 4349–4383, [doi:10.5194/essd-13-4349-2021](https://doi.org/10.5194/essd-13-4349-2021) |
| MSG LST with Directional Effects, MLST_DIR [LSA-004] | 04 | EUMETSAT Data Store | EUMETSAT LSA SAF (Trigo et al., 2011, [doi:10.1080/01431161003743199](https://doi.org/10.1080/01431161003743199)); method: Ermida et al. (2018), [doi:10.3390/rs10071114](https://doi.org/10.3390/rs10071114) |
| GHS-POP R2023A, population grid | `scripts/extract_population_100m.py` | Earth Engine | Schiavina, Freire, MacManus (2023), [doi:10.2905/2FF68A52-5B5B-4A22-8F40-C41DA8332CFE](https://doi.org/10.2905/2FF68A52-5B5B-4A22-8F40-C41DA8332CFE) |

## 1. Install

We produced the results with **Python 3.12.10** in an environment named `geovenv`. `requirements.lock` holds
its exact package versions for Windows, Linux and macOS. Any one of four routes gives the same versions:

```powershell
git clone https://github.com/Patrick-Samson-Udama-Eneche/stake_lst_anomalies.git
cd stake_lst_anomalies

# Route 1: uv (fastest)
uv venv --python 3.12.10 geovenv
uv pip sync requirements.lock --python geovenv

# Route 2: pip
py -3.12 -m venv geovenv                 # Linux / macOS: python3.12 -m venv geovenv
.\geovenv\Scripts\python.exe -m pip install -r requirements.lock

# Route 3: conda-forge (if the pip GDAL wheels fail on your machine)
conda env create -f environment.yml
conda activate stake_lst_anomalies

# Route 4: Docker (no local Python needed)
docker build -t stake_lst_anomalies .
```

For routes 1 and 2, activate the environment (`.\geovenv\Scripts\Activate.ps1`; Linux / macOS:
`source geovenv/bin/activate`) before running anything. Then run `python scripts/check_project.py`: it reports
PASS, FAIL or NOTE for the environment, code, dataset, outputs and repository, without any remote call.

We tested every route from a fresh start on Windows 11, with the results of a full run in place:

| Route | Project check | Notebook 07 | Notes |
|---|---|---|---|
| uv | 17 passed, 0 failed | 79 of 79 | the same GEOS 3.13.1, PROJ 9.5.1 and GDAL 3.11.4 as our build |
| pip | 17 passed, 0 failed | 79 of 79 | the same libraries as uv |
| conda | 17 passed, 0 failed | 79 of 79 | newer GEOS 3.14.1, PROJ 9.8.1 and GDAL 3.13.3: the same values, not the same bytes |
| Docker (Linux) | 59 tests pass in the image | 79 of 79 | the same values; text files with Linux line endings; figures in DejaVu Sans |

- **conda reproduces values, not bytes.** Its newer geometry libraries move spot and contour outlines by at
  most 4.5 × 10⁻⁸ m. Every attribute is identical, but Notebook 05's dataset rebuild reports "values changed".
  To reproduce the dataset exactly, use uv or pip.
- **Docker.** The image holds the code and the environment; `data/` and `Results/` are mounted when it runs.
  It has no Arial, so its figures use DejaVu Sans, and it writes text files with Linux line endings. Run it from
  a local folder: Docker cannot read files that a cloud service keeps online only.
- **Windows with Smart App Control.** Windows may refuse a package's DLL with "An Application Control policy has
  blocked this file". Importing again often clears it. conda-forge's numpy stays blocked, so after
  `conda env create` we run `python -m pip install --force-reinstall --no-deps numpy==2.4.4`, the PyPI build of
  the same version.

## 2. Accounts and credentials

[secrets/README.md](secrets/README.md) gives the file formats. The files stay in `secrets/`, which git ignores.

1. **Google Earth Engine.** A Google Cloud project registered for Earth Engine (free for non-commercial use) and a
   service account with access to it. Save the account's JSON key as `secrets/gee_service_account.json`. The
   code takes the project from the key (or from the environment variable `GEE_PROJECT_ID`).
   Notebook 01 stores each city's zones as an Earth Engine asset in your project, in the folder named by
   `GEE_COLLECTION` (default `AOI_Nigeria_Cities`). It creates the folder when it is missing and waits for its
   exports to finish, because Notebooks 03 and 04 read these assets.
2. **EUMETSAT.** An account on the EUMETSAT Data Store and its API key pair. Save them as
   `secrets/eumetsat_credentials.json`.
3. **OpenStreetMap** needs no account.

Earth Engine requests time out after six minutes and are retried when the failure looks temporary (a dropped
connection, a computer going to sleep, a busy server), so an interrupted run does not hang.

## 3. A. Re-run the study from the sources

With the credentials of section 2 in place:

```powershell
python run_all.py --scope all --output-dir Results/_provenance
```

This runs Notebooks 01 to 06 for the 56 study cities, then Notebook 07. On a first run it also does two things by
itself:

1. **Earth Engine assets.** Notebook 01 creates the asset folder in your project, exports each city's zones to it
   and waits until the exports are complete, because Notebooks 03 and 04 read them.
2. **Population.** `scripts/extract_population_100m.py` sums GHS-POP inside the spots and zones that Notebook 05
   writes, and Notebook 05 needs those sums. So on a first run Notebook 05 stops once its spots and zones are
   written, `run_all.py` runs the script, and Notebook 05 runs again. Without `run_all.py`: run Notebook 05, then
   the script, then Notebook 05 again.

Each notebook keeps what it has downloaded, so a run that stops can be started again and continues with what is
missing. Earth Engine requests that hang (a computer going to sleep, a dropped connection) time out and are
retried.

**Time.** We tested this from an empty folder with two cities, Jos and Bida, on the laptop of section 1:

| Step | Time for two cities |
|---|---|
| Notebook 01 (OpenStreetMap, GHS-SMOD, Global Surface Water, asset exports) | 5 min |
| Notebook 02 | under 1 min |
| Notebook 03 (MODIS, 2006–2025) | 3–21 min per city; up to 40 min for a city with a long coastline |
| Notebook 04 (ERA5-Land, MODIS daily, MSG-SEVIRI) | 28 min |
| Population (GHS-POP) | under 1 min |
| Notebook 05 | 2 min |

For all 56 cities the run takes the better part of a day; with the downloads in place, Notebook 05 takes about
18 minutes, Notebook 06 two minutes and Notebook 07 6–15 minutes.

**It worked if** `run_all.py` ends with "0 failed" and Notebook 07 reports "Assertions: 79 of 79 passed". With the
same downloads as ours, Notebook 05's rebuild of the dataset matches the published one except for the one value
described in section 6. If a provider has reprocessed its archive since, values can differ; Notebook 05's quality
checks and Notebook 07's assertions then name what changed.

**A quick check with a few cities.** `python run_all.py --scope all --cities "Jos" "Bida"` runs every notebook for
those cities only: about an hour, and enough to show that your credentials and every download work (Notebooks 01
to 04 and the population step). Notebook 05's checks of the published counts, Notebook 06 and Notebook 07 are
written for all 56 cities, so with a few cities Notebook 05 stops at its first published check (§9). Notebooks 04
and 05 take their cities from what the earlier notebooks wrote, so start from an empty `Results/` when you change
the set of cities.

Notebook 01's assets stay in your Earth Engine project; delete the folder in the Assets tab of the Earth Engine
Code Editor when you no longer need it.

## 4. B. Rebuild the article's figures and tables

No credentials and no internet are needed once the results of case A are in `Results/`, and the dataset is in
`Results/05_hotspot_analysis/surface_thermal_anomaly_stakeholder_composite/` (Notebook 05 builds it; or download
v1.0.1 from Zenodo and put its files there).

```powershell
python run_all.py --scope manuscript --output-dir Results/_provenance
```

Notebook 07 draws every figure and table of the article and its supplementary material and writes them to
`Results/manuscript_outputs/`. It asserts every value it shows against the dataset in place and logs every file it
reads. It takes 6–10 minutes, and up to 15 minutes when it draws every figure set, as on a first run.

**It worked if** the last output of `Results/_provenance/executed_07_publication_outputs.ipynb` reads
**"Assertions: 79 of 79 passed"** and `python scripts/check_project.py` reads **0 failed**. With results that
match the published ones, every table holds the same values; the Excel workbooks embed their creation time,
`_data_sources.csv` records the dates of the input files, and the labels of Fig. 1, S3.1 and S3.2 move slightly
between runs (the label placement is random).

## 5. C. Run a new scenario

1. In `config.py`, change the settings you want: the cities (`CITY_SELECTION_MODE`, or `SELECTED_CITIES` with
   `"SPECIFIC"`), the study year (`PROJECT_STUDY_YEAR` and `PROJECT_SETTINGS['study_year']`), or the hot and cold
   spot thresholds (`HOTSPOT_*`). For a few cities, `python run_all.py --cities "Jos" "Bida" …` does the same
   as `"SPECIFIC"` for every notebook it runs.
2. Run the steps of case A, starting from an empty `Results/`.

Notebooks 01 to 05 run for any set of cities and settings, as far as the spots and the population within them.
Notebook 05's checks, the dataset build's quality checks, Notebook 06 and Notebook 07 are written for the published
56-city scenario: they compare the results with its counts, so for a new scenario they stop or report the
differences rather than build a new version of the dataset. The dataset build labels every row with a
`scenario_id`, an eight-character digest of the settings (listed in the `scenario_config` layer), so that runs
under different settings can be told apart.

`requirements.txt` lists the packages without exact versions, for anyone who wants to run a new scenario with
newer releases.

## 6. D. Use only the published dataset

The dataset needs no code from this repository. It is one GeoPackage (projection ESRI:102022) with a data
dictionary and its own README, which describes every layer, field, source and the anonymisation. Open it in QGIS,
or in Python:

```python
import geopandas as gpd
import pyogrio

path = "surface_thermal_anomaly_stakeholder_composite.gpkg"
print(pyogrio.list_layers(path))          # the layers and their geometry types
layer = gpd.read_file(path, layer="...")  # one layer, by name
```

### The published dataset and this code

The code rebuilds the dataset as we last built it, on 29 October 2026. The published v1.0.1 is the build of
28 October. The two differ in one data value: one participant left "recency of contact with the city" blank,
which v1.0.1 stores as empty and the rebuild stores as "I'd rather not say". No figure or table reads this field,
and Notebook 07 passes all 79 checks with v1.0.1. The wording of the data dictionary and a few entries of the
`dataset_info` layer (the DOI fields and the layer counts) differ as well. With the results of case A in place,
`python scripts/build_master_summary.py --compare-only` rebuilds the dataset and compares it with the copy in
`Results/05_hotspot_analysis/surface_thermal_anomaly_stakeholder_composite/` without changing anything; against
v1.0.1 it reports "Values changed" and lists this one field among the data layers
(`Results/05_hotspot_analysis/_build_staging/CHANGES_REPORT.md`).

## 7. Checks at a glance

| Check | Command | Expected |
|---|---|---|
| Project | `python scripts/check_project.py` | 0 failed |
| Tests | `pytest tests -q` | 59 passed |
| Figures and tables | the last output of `Results/_provenance/executed_07_publication_outputs.ipynb` | Assertions: 79 of 79 passed |
| Dataset | `python scripts/build_master_summary.py --compare-only` | against v1.0.1: "Values changed", one data field (see above) |

Every run of `run_all.py` also records the environment (Python, packages and libraries) in `Results/_provenance/`.

## Releasing a new version

1. `python scripts/check_project.py` reads 0 failed, and `pytest tests -q` passes.
2. We publish a release on GitHub (tag `v<version>`). Zenodo archives it at once under the code's concept DOI, with
   the metadata in `.zenodo.json`.

## How to cite

Please cite the article and the dataset; [CITATION.cff](CITATION.cff) holds the metadata for this code.
