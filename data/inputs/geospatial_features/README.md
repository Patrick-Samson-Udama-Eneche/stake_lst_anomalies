# Geospatial Features

This directory contains geospatial data for Nigerian cities used in the LST modeling project.

## Files

### Base Geographic Data
- `boundary_Nigeria.geojson` - Nigeria national boundary
- `5km_grid_Nigeria.geojson` - 5km grid overlay for Nigeria
- `Major_cities_Nigeria.geojson` - Major cities locations (points)
- `Major_cities_population_Nigeria.csv` - Population data for cities
- `urban_landscape_typology_Nigeria.geojson` - Urban landscape classifications

### City-Specific OSM Features
Downloaded using `OSM_features.ipynb` for each city:

#### Abuja, Jos, Kano, Lagos, Port Harcourt
Each city has:
- `{City}_major_roads.geojson` - Major roads and expressways
- `{City}_built_up_areas.geojson` - Built-up/developed areas
- `{City}_places_villages.geojson` - Named places and villages

## Data Generation

### OSM_features.ipynb
**Purpose:** Downloads OpenStreetMap (OSM) features for city areas of interest

**What it does:**
1. Loads AOI boundaries from `data/outputs/01_aoi_delineation/`
2. Downloads OSM data for each city:
   - Major roads (motorways, trunks, primary/secondary/tertiary roads)
   - Built-up areas (residential, commercial, industrial landuse)
   - Places and villages (named settlements)
3. Saves results to city-specific folders

**Status:** 
- ✅ Data already downloaded and saved
- 🔄 Can be re-run if data needs to be updated
- ⚠️ Requires internet connection and OSMnx library

**Note:** This notebook is a **data generation script**, not part of the main analysis workflow. It only needs to be run when:
- Setting up the project for the first time
- Updating OSM data with newer features
- Adding new cities to the analysis

## Usage in Analysis

Currently, these OSM features are **not actively used** in the main analysis notebooks (01, 02). They are available for future analysis that may require:
- Road network analysis
- Built-up area calculations
- Spatial overlay operations
- Urban morphology studies
