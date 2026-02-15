# OpenStreetMap Data for Nigeria

This directory contains large OpenStreetMap (OSM) extracts for Nigeria. Due to GitHub's file size limits, these files are **not included in the repository** and must be downloaded separately.

## Required Files

| File | Size | Purpose | Status |
|------|------|---------|--------|
| `nigeria-latest.osm.pbf` | ~635 MB | Full Nigeria OSM data | ⚠️ Download required |
| `regional/Abuja_regional.osm.pbf` | ~194 MB | Abuja regional extract | ⚠️ Download required |
| `regional/Jos_regional.osm.pbf` | ~108 MB | Jos regional extract | ⚠️ Download required |

## Download Instructions

### Option 1: Geofabrik (Recommended)

Download the full Nigeria extract from [Geofabrik](https://download.geofabrik.de/africa/nigeria.html):

```powershell
# Create directory if needed
New-Item -ItemType Directory -Force -Path "data/inputs/osm_nigeria"

# Download Nigeria extract
Invoke-WebRequest -Uri "https://download.geofabrik.de/africa/nigeria-latest.osm.pbf" -OutFile "data/inputs/osm_nigeria/nigeria-latest.osm.pbf"
```

### Option 2: Generate Regional Extracts with Osmium

If you need the regional extracts for Abuja and Jos, use [Osmium Tool](https://osmcode.org/osmium-tool/) to extract from the full Nigeria file:

```powershell
# Install Osmium (via conda or system package manager)
# conda install -c conda-forge osmium-tool

# Extract Abuja region (example coordinates - adjust as needed)
osmium extract -b 6.5,8.5,7.5,9.5 data/inputs/osm_nigeria/nigeria-latest.osm.pbf -o data/inputs/osm_nigeria/regional/Abuja_regional.osm.pbf

# Extract Jos region
osmium extract -b 8.5,9.5,9.5,10.5 data/inputs/osm_nigeria/nigeria-latest.osm.pbf -o data/inputs/osm_nigeria/regional/Jos_regional.osm.pbf
```

### Option 3: Use Pre-downloaded Files

If you already have these files from a previous run, simply place them in this directory. The `.gitignore` is configured to exclude `*.osm.pbf` files automatically.

## Verification

After downloading, verify the files exist:

```powershell
Get-ChildItem -Path "data/inputs/osm_nigeria" -Recurse -Filter "*.osm.pbf" | Select-Object Name, @{Name="Size(MB)";Expression={[math]::Round($_.Length/1MB,2)}}
```

Expected output:
```
Name                       Size(MB)
----                       --------
nigeria-latest.osm.pbf     ~635
Abuja_regional.osm.pbf     ~194
Jos_regional.osm.pbf       ~108
```

## Notes

- OSM data is updated daily on Geofabrik — your downloads may differ slightly in size
- These files are excluded from git via `.gitignore` (too large for GitHub)
- The notebooks will automatically use these files if present in the expected locations
- If files are missing, Notebook 01a will use the Overpass API as a fallback (slower, rate-limited)
