# Reproducing the results

This guide shows how to reproduce the results of *Urban surface thermal anomalies in Nigeria*: how to
install the environment, where to get the data, how to run each case and how to check that it worked.

| I want to … | I need | Command | Time |
|---|---|---|---|
| **A.** rebuild the article's figures and tables | the caches and the dataset | `python run_all.py --scope manuscript --output-dir Results/_provenance` | 6–15 min |
| **B.** re-run the whole pipeline from the sources | Earth Engine and EUMETSAT credentials | `python run_all.py --scope all --output-dir Results/_provenance` | hours |
| **C.** run a new scenario (other cities, year or thresholds) | credentials, an edited `config.py` | `python run_all.py --scope analytic` | hours |
| **D.** use only the published dataset | the dataset | none | — |

## What is where

| Item | Where | Licence |
|---|---|---|
| Code | this repository, and its archived release on Zenodo (DOI _to be added_) | CC BY 4.0 |
| Caches: the results of Notebooks 01–06 | the same Zenodo record, `stake_lst_anomalies_caches_v1.0.0.zip` | CC BY 4.0 |
| OpenStreetMap extracts | the same Zenodo record, `stake_lst_anomalies_osm_v1.0.0.zip` | ODbL 1.0 |
| Dataset (v1.0.1) | Zenodo, [10.5281/zenodo.23777933](https://doi.org/10.5281/zenodo.23777933) (all versions: [10.5281/zenodo.23050559](https://doi.org/10.5281/zenodo.23050559)) | CC BY 4.0 |
| Figures and tables | the article (DOI _to be added_), their version of record | — |

The figures and tables are not in this repository. The article publishes them, and Notebook 07 rebuilds
them from the caches and the dataset (case A).

## 1. Install

I produced the results with **Python 3.12.10** in an environment named `geovenv`. `requirements.lock` holds
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
`source geovenv/bin/activate`) before running anything. Then run `python scripts/check_project.py`: it
reports PASS, FAIL or NOTE for the environment, code, dataset, outputs and repository, without any remote
call.

I tested every route from a fresh start on Windows 11, with the caches and the dataset in place. With the
published v1.0.1 downloaded from Zenodo, Notebook 07 also passes 79 of 79.

| Route | Project check | Notebook 07 | Notes |
|---|---|---|---|
| uv | 17 passed, 0 failed | 79 of 79 | the same GEOS 3.13.1, PROJ 9.5.1 and GDAL 3.11.4 as my build |
| pip | 17 passed, 0 failed | 79 of 79 | the same libraries as uv |
| conda | 17 passed, 0 failed | 79 of 79 | newer GEOS 3.14.1, PROJ 9.8.1 and GDAL 3.13.3: the same values, not the same bytes |
| Docker (Linux) | 59 tests pass in the image | 79 of 79 | the same values; text files with Linux line endings; figures in DejaVu Sans |

- **conda reproduces values, not bytes.** Its newer geometry libraries move spot and contour outlines by at
  most 4.5 × 10⁻⁸ m. Every attribute is identical, but Notebook 05's dataset rebuild reports "values changed"
  against the published dataset. To reproduce the dataset exactly, use uv or pip.
- **Docker.** The image holds the code and the environment; `data/` and `Results/` are mounted when it runs.
  It has no Arial, so its figures use DejaVu Sans, and it writes text files with Linux line endings. The
  tables hold the same values as on Windows. Run it from a local folder: Docker cannot read files that a
  cloud service keeps online only.
  ```powershell
  docker run --rm stake_lst_anomalies pytest tests -q      # 59 passed
  docker compose run --rm reproduce                        # case A under Linux
  ```
- **Windows with Smart App Control.** Windows may refuse a package's DLL with "An Application Control policy
  has blocked this file". Importing again often clears it. conda-forge's numpy stays blocked, so after
  `conda env create` I run `python -m pip install --force-reinstall --no-deps numpy==2.4.4`, the PyPI build
  of the same version.

## 2. Get the data

1. Download `stake_lst_anomalies_caches_v1.0.0.zip` from the code record and unzip it in the repository's
   root folder. It creates `Results/01_aoi_delineation/` to `Results/06_hotspot_modelling/`.
2. Download the dataset, v1.0.1, and put its files in
   `Results/05_hotspot_analysis/surface_thermal_anomaly_stakeholder_composite/`.
3. Only to re-run Notebook 01 without downloading OpenStreetMap again: unzip
   `stake_lst_anomalies_osm_v1.0.0.zip` in the root folder. It adds the `osm/` folder of each city under
   `Results/01_aoi_delineation/` and the download cache `Notebook/cache/`.
4. Run `python scripts/check_project.py`. Before case A, it reports the figures and tables as missing: a
   note, not a failure.

## 3. The four cases

### A. Rebuild the article's figures and tables

No credentials and no internet are needed.

```powershell
python run_all.py --scope manuscript --output-dir Results/_provenance
```

Notebook 07 reads the caches and the dataset, draws every figure and table of the article and its
supplementary material, and writes them to `Results/manuscript_outputs/`. It asserts every value it shows
against the published dataset and logs every file it reads. It takes 6–10 minutes, and up to 15 minutes
when it draws every figure set, as on a first run.

**It worked if** the last output of `Results/_provenance/executed_07_publication_outputs.ipynb` reads
**"Assertions: 79 of 79 passed"** and `python scripts/check_project.py` reads **17 passed, 0 failed**.

What stays the same between runs, and what does not:

- every table holds the same values; on Windows the CSV files are byte-identical to mine;
- the Excel workbooks embed their creation time, and `_data_sources.csv` records the dates of the input files;
- the labels of Fig. 1, S3.1 and S3.2 move slightly between runs (the label placement is random); no value
  changes.

### B. Re-run the pipeline from the sources

Notebooks 01, 03, 04 and 05 download from Google Earth Engine (MODIS, ERA5-Land, GHSL, JRC Global Surface
Water) and EUMETSAT (LSA SAF SEVIRI land surface temperature). Put your credentials in `secrets/`, as
[secrets/README.md](secrets/README.md) describes, then run:

```powershell
python run_all.py --scope all --output-dir Results/_provenance
```

This runs Notebooks 01 to 06 in order, then Notebook 07. It overwrites the caches in `Results/`, so keep a
copy of them if you want to compare. The notebooks can also be run one by one in Jupyter, in the order
01 → 06, then 07.

| Notebook | Time | Needs |
|---|---|---|
| 01 AOI delineation | network-bound | Earth Engine, OpenStreetMap |
| 02 Stakeholder analysis | 30 s | — |
| 03 Monthly and annual LST | network-bound | Earth Engine |
| 04 Daily LST | network-bound | Earth Engine, EUMETSAT |
| 05 Surface hot and cold spots, and the dataset | 18 min | Earth Engine |
| 06 Typology association | 1.5 min | — |
| 07 Figures and tables | 6–15 min | — |

I measured these times on a laptop with an Intel Core i7-8650U, 16 GB of RAM and Windows 11. The download
notebooks take several hours for all cities. Their results depend on the providers' archives: if a
provider reprocesses a product, the values can change.

Notebook 05 ends by rebuilding the dataset and comparing it with the copy in place, by a content
fingerprint: a SHA-256 over every layer's content, which ignores differences that are only in the file
bytes. Against the published v1.0.1 it reports **"Values changed"**, for the reason given under
[The published dataset and this code](#the-published-dataset-and-this-code). If its quality checks then
pass, it replaces your copy and keeps the old one in `Results/05_hotspot_analysis/_superseded_build_<date>/`.
Then check Notebook 07 as in case A.

### C. Run a new scenario

1. In `config.py`, change the settings you want: the cities (`CITY_SELECTION_MODE`, or `SELECTED_CITIES`
   with `"SPECIFIC"`), the study year (`PROJECT_STUDY_YEAR` and `PROJECT_SETTINGS['study_year']`), or the
   hot and cold spot thresholds (`HOTSPOT_*`).
2. Run the analysis: `python run_all.py --scope analytic`, or `python run_all.py --cities "Lagos" "Kano"` for a
   few cities.
3. Build the dataset: `python run_all.py --scope dataset`.

The dataset build labels every row with a `scenario_id`, an eight-character digest of the settings (listed
in the `scenario_config` layer). A new scenario is added to your local copy of the dataset next to the
published one, rather than replacing it; the published version stays on Zenodo. Notebook 07 rebuilds the
article for the published scenario and checks every value against it, so it is not meant for a new one.

`requirements.txt` lists the packages without exact versions, for anyone who wants to run a new scenario
with newer releases.

### D. Use only the published dataset

The dataset needs no code from this repository. It is one GeoPackage (projection ESRI:102022) with a data
dictionary and its own README, which describes every layer, field, source and the anonymisation. Open it in
QGIS, or in Python:

```python
import geopandas as gpd
import pyogrio

path = "surface_thermal_anomaly_stakeholder_composite.gpkg"
print(pyogrio.list_layers(path))          # the layers and their geometry types
layer = gpd.read_file(path, layer="...")  # one layer, by name
```

With the caches in place, `python scripts/build_master_summary.py --compare-only` rebuilds the dataset in
about two minutes, without credentials, and compares it with your copy without changing anything. It
writes the differences to `Results/05_hotspot_analysis/_build_staging/CHANGES_REPORT.md`.
(`python run_all.py --scope dataset` does the same, but replaces your copy when the content differs.)

### The published dataset and this code

The code rebuilds the dataset as I last built it, on 29 October 2026. The published v1.0.1 is the build of
28 October. The two differ in one data value: one participant left "recency of contact with the city"
blank, which v1.0.1 stores as empty and the rebuild stores as "I'd rather not say". No figure or table
reads this field, and Notebook 07 passes all 79 checks with v1.0.1. The wording of the data dictionary and a
few entries of the `dataset_info` layer (the DOI fields and the layer counts) differ as well. A comparison against v1.0.1 therefore reports
"Values changed", and its changes report lists this one field among the data layers.

## 4. Checks at a glance

| Check | Command | Expected |
|---|---|---|
| Project | `python scripts/check_project.py` | 17 passed, 0 failed |
| Tests | `pytest tests -q` | 59 passed |
| Figures and tables | the last output of `Results/_provenance/executed_07_publication_outputs.ipynb` | Assertions: 79 of 79 passed |
| Dataset | `python scripts/build_master_summary.py --compare-only` | against v1.0.1: "Values changed", one data field (see above) |

Every run of `run_all.py` also records the environment (Python, packages and libraries) in
`Results/_provenance/`.

## How to cite

Please cite the article and the dataset; [CITATION.cff](CITATION.cff) holds the metadata for this code.
