# Project Concept Note

## Physiographic Controls on Urban Heat Intensity in Nigerian Cities: A Hierarchical Analysis with Stakeholder Validation

---

## 1. Research Context

Urban Heat Islands (UHIs) amplify health risks, energy demand, and environmental stress in rapidly urbanising African cities. This project investigates **how physiographic factors — climate zone, geological substrate, and elevation — control the spatial intensity of persistent urban heat** across Nigerian cities, validated against stakeholder perceptions from workshop-based participatory mapping.

### Research Questions

| # | Question |
|---|---------|
| **RQ1** | What are the physiographic controls on extreme urban heat intensity across Nigerian cities? |
| RQ1a | What is the unique contribution of each physiographic factor (climate, geology, elevation)? |
| RQ1b | How much variance do these factors explain collectively? |
| RQ1c | How do controls differ between daytime and night-time heat? |
| **RQ2** | How do urban heat hotspots cluster spatially within and across cities? |
| **RQ3** | To what extent do stakeholder perceptions validate satellite-derived hotspot locations? |
| **RQ4** | Which cities exhibit persistent heat events (consecutive hot days/nights)? |

### Study Area

- **Country:** Nigeria — spans 4 Köppen climate zones
- **Hotspot analysis cities:** Abuja, Jos, Kano, Lagos, Port Harcourt (5 cities across distinct physiographic settings)
- **Stakeholder workshop cities:** 28 cities across Nigeria (115 survey participants)
- **Study year:** 2024

---

## 2. Methodological Framework

### 2.1 Data Sources

| Source | Resolution | Variables | Used In |
|--------|-----------|----------|---------|
| MSG SEVIRI | 15 min / ~3 km → 1 km | Land Surface Temperature (day/night) | Persistent heat rasters |
| MODIS Aqua (MYD11A1) | Daily / 1 km | LST with QA filtering | Hot event detection, trend analysis |
| ERA5-Land | Hourly / ~11 km | 2m air temperature | Hot event cross-validation |
| GHSL (JRC) | 100 m → 1 km via GEE | Population grid (2020 epoch) | Population exposure |
| Landscape Character | Vector polygons | Climate, geology, elevation, land cover (Cluster25 classification) | Attribute enrichment |
| OpenStreetMap | Vector | Water bodies, roads, places | Water masking, context maps |
| Stakeholder Survey | Point (GPS ±10 m) | Hot/cold spot locations, reasons, mitigation preferences, tree species | Validation |

### 2.2 Analysis Pipeline

```
Notebook 01: AOI Delineation
│   Select cities → buffer urban polygons → generate AOI boundaries
│   Output: City AOI GeoJSON files (boundary, buffer, statistics)
│
├── Notebook 01a: Geospatial Feature Extraction
│     Extract OSM water/roads/places + JRC features per AOI
│
├── Notebook 02: Stakeholder Analysis (independent)
│     Map 115 stakeholders across 28 cities, perception analysis
│
├── Notebook 03: Monthly/Annual LST Trends (2006–2024)
│     MODIS extraction via GEE → yearly/monthly GeoTIFFs + trend analysis
│
└── Notebook 04: Daily LST & Persistent Heat Events
      MODIS + ERA5 hot event detection → Decision tree → SEVIRI persistent heat rasters
      │
      └── Notebook 05: Hotspot Analysis
            P90 → Gi* → KDE polygons → landscape/population enrichment → validation
            │
            └── Notebook 06: LST Modelling (061 → 062 → 063)
                  061: Feature engineering (NDVI, NDBI, elevation, distance, population)
                  062: Model training (Random Forest, Gradient Boosting regression)
                  063: Model validation (hold-out, spatial CV, stakeholder comparison)
```

### 2.3 Hotspot Identification

1. **Percentile threshold:** Pixels ≥ P90 classified as hot (top 10%)
2. **Spatial clustering:** Getis-Ord Gi\* statistic (p < 0.05, Queen contiguity weights)
3. **Validated hotspots:** Intersection of P90 and Gi\* significant pixels
4. **KDE delineation:** Gaussian kernel (Scott's rule bandwidth), contour extraction at 50%, 75%, 90% density levels
5. **Polygon post-processing:** Douglas-Peucker simplification (0.0001°), minimum area filter

### 2.4 Decision Tree for Persistent Heat Events

The project uses a **duration-priority** decision tree (Option 1) for selecting SEVIRI observation periods:

- **ERA5-Land's longest persistent event always selected** — heat stress is cumulative; duration matters most
- **MODIS cross-validation** provides quality flags (Excellent/Good/Fair) — neutral language, does not override duration selection
- **Night SEVIRI window:** Expanded from 3 hours (00:00–03:00) to 12 hours (18:00–06:00) for better coverage in cloud-prone tropical cities

### 2.5 Attribute Enrichment

Each hotspot polygon is enriched with:
- **Landscape character:** Climate zone, geology, elevation class, land cover (via Cluster25 classification from 25 landscape types)
- **LST statistics:** Day/night mean, max, min from SEVIRI persistent heat rasters
- **Population exposure:** GHSL 2020 population count within polygon boundaries
- **Stakeholder validation:** Hit-rate analysis with configurable buffer zone

### 2.6 LST Predictive Modelling

Notebook 06 builds regression models to predict LST from physiographic and urban variables:

1. **Feature engineering (061):** Extract per-pixel predictor variables (NDVI, NDBI, NDWI, impervious fraction, elevation, slope, distance to water/roads, population density, air temperature) from GEE and local rasters
2. **Model training (062):** Fit Random Forest and Gradient Boosting regressors; evaluate feature importance; hyperparameter tuning via cross-validation
3. **Model validation (063):** Hold-out test set metrics (R², RMSE, MAE), leave-one-city-out spatial CV, comparison of model-predicted hotspots with stakeholder survey locations

### 2.7 Stakeholder Validation

- Workshop-based participatory mapping (28 cities, 115 participants)
- Stakeholders identify perceived hot/cold spots, reasons, mitigation preferences, and preferred tree species
- Spatial overlay of survey points with satellite-derived hotspot polygons
- Agreement metrics: hit-rate, spatial concordance

---

## 3. Technical Architecture

### Configuration

All parameters are centralised in `config.py`:
- **CRS:** WGS84 (EPSG:4326) for storage, Web Mercator (EPSG:3857) for processing
- **Hotspot thresholds:** P90 hot, P95 extreme, Gi\* p < 0.05
- **KDE:** Scott's rule bandwidth, contour levels [0.50, 0.75, 0.90]
- **Resampling:** 250 m binary mask resolution for KDE performance
- **Study year:** 2024 (configurable via `PROJECT_STUDY_YEAR`)

### Modular Source Code (`src/`)

| Module | Purpose |
|--------|---------|
| `aoi_utils.py` | AOI buffer zone creation, boundary statistics |
| `data_io.py` | Data loading, export, spatial operations, GHSL download |
| `gee_utils.py` | GEE authentication, MODIS/ERA5 extraction |
| `temporal_analysis.py` | Trend analysis, hot event detection, persistence statistics |
| `temporal_analysis_utils.py` | Daily LST helper functions, JSON serialization |
| `decision_tree_utils.py` | Duration-priority event selection logic |
| `seviri_processing_utils.py` | EUMETSAT download, MSG native processing, reprojection |
| `visualization.py` | All plotting functions (maps, charts, heatmaps, ~8,000 lines) |

### City Selection Flow

Cities selected in Notebook 01 automatically propagate to all downstream notebooks. Each notebook auto-discovers cities by scanning output directories of its predecessors — no manual reconfiguration needed. The Cluster25 landscape classification system maps all 28 workshop cities to 8 landscape clusters.

### External Service Dependencies

| Service | Notebooks | Purpose |
|---------|-----------|---------|
| Google Earth Engine | 01a, 03, 04, 05 | MODIS LST extraction, ERA5 extraction, GHSL population |
| EUMETSAT Data Store | 04 | MSG SEVIRI persistent heat raster download |

### OSM Feature Extraction

Per-city features extracted and cached from OpenStreetMap:
- **Water bodies** (polygon): `natural=water`, various `water=*` tags — used for SEVIRI LST masking
- **Roads** (line): motorway through tertiary + link variants
- **Places** (point): city, town, village, neighbourhood hierarchy

---

## 4. Key Outputs

### Data Products
- **City AOI boundaries** — GeoJSON per city (boundary, buffer, main polygon, adjacent polygons)
- **Monthly/annual LST rasters** — GeoTIFF per city/period (2006–2024)
- **Daily LST time series** — CSV + JSON statistics per city
- **SEVIRI persistent heat rasters** — GeoTIFF (1 km, WGS84) per city for day and night
- **Hotspot polygons** — GeoJSON (EPSG:4326 + EPSG:3857) with landscape, LST, and population attributes

### Visualisations
- City AOI maps with population trends
- Stakeholder distribution maps and perception charts
- LST temporal heatmaps (yearly/monthly × day/night)
- Persistent heat event timeline plots
- Multi-panel hotspot grid maps per city
- Gi\* distribution histograms
- Hotspot area by contour level and landscape class
- Population exposure half-donut charts
- National summary map (proportional symbols)
- Stakeholder perception by Cluster25 landscape type (stacked bar + tree species heatmaps)

---

## 5. Landscape Classification

The project uses a **Cluster25** system derived from hierarchical landscape character analysis:

| Cluster | Dominant Cities |
|---------|----------------|
| CL-4 | Abuja, Calabar, Jalingo, Kaduna, Lafia, Minna |
| CL-7 | Anyigba |
| CL-8 | Katsina |
| CL-9 | Ado Ekiti, Ibadan, Ife |
| CL-12 | Lokoja, Makurdi |
| CL-13 | Abraka, Akure, Benin City, Lagos, Osogbo, Owerri, Port Harcourt, Umuahia, Uyo |
| CL-19 | Jos |
| CL-25 | Dutse, Ilesa, Kano, Maiduguri, Yola |

Each cluster represents a distinct combination of climate zone, geological substrate, elevation range, and land cover type. Eight cities without coordinate data in the landscape GeoJSON use manually verified fallback assignments.

---

## 6. Project Status

| Phase | Status | Description |
|-------|--------|-------------|
| 1 — AOI Delineation | **Complete** | City boundaries defined, OSM features extracted |
| 2 — Stakeholder Analysis | **Complete** | 115 stakeholders mapped, perception analysis done |
| 3 — Monthly/Annual LST | **Complete** | MODIS trends for 5 cities (2006–2024) |
| 4 — Daily LST & SEVIRI | **Complete** | Hot events detected, persistent heat rasters generated |
| 5 — Hotspot Analysis | **Complete** | P90/Gi\*/KDE hotspots delineated, enriched, validated |
| 6 — LST Modelling | **In Progress** | Feature engineering + predictive models (RF, GBR) |
| 7 — Model Validation | **Planned** | Spatial cross-validation and stakeholder comparison |

---

## 7. References

This project builds on established UHI methodologies:

- **Peng et al. (2012)** — Hierarchical regression across 419 cities for UHI drivers
- **Clinton & Gong (2013)** — Climate zone effects on SUHI intensity
- **Zhou et al. (2014)** — P90 methodology for UHI hotspot identification
- **Rasul et al. (2017)** — Elevation effects on LST patterns
- **Kuang et al. (2015)** — Geological substrate influence on thermal properties
- **Schwarz et al. (2011)** — Gi\* spatial clustering for UHI delineation
- **Dousset et al. (2011)** — Persistent heat events and mortality linkage

---

*This document consolidates all project planning, implementation, and audit documentation into a single reference. For credential setup, see [SECURITY_SETUP.md](SECURITY_SETUP.md). For the original research strategy, see [Idea_mapping_formatted.md](Idea_mapping_formatted.md).*
