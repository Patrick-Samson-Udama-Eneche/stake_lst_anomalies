# =============================================================================
# Dockerfile for LST Modelling Project
# =============================================================================
# Provides a fully reproducible environment with all geospatial dependencies.
#
# Build:
#   docker build -t lst-modelling .
#
# Run interactively (Jupyter Lab):
#   docker run -it --rm \
#     -p 8888:8888 \
#     -v ./data:/app/data \
#     -v ./secrets:/app/secrets \
#     lst-modelling jupyter lab --ip=0.0.0.0 --no-browser --allow-root
#
# Run the full pipeline:
#   docker run -it --rm \
#     -v ./data:/app/data \
#     -v ./secrets:/app/secrets \
#     lst-modelling python run_all.py
#
# Run for specific cities:
#   docker run -it --rm \
#     -v ./data:/app/data \
#     -v ./secrets:/app/secrets \
#     lst-modelling python run_all.py --cities "Lagos" "Abuja"
#
# Run tests:
#   docker run --rm lst-modelling pytest tests/ -v
# =============================================================================

FROM python:3.11-slim

# System dependencies required by GDAL, rasterio, fiona, and shapely
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    libspatialindex-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set GDAL environment variables (required for rasterio/fiona compilation)
ENV GDAL_CONFIG=/usr/bin/gdal-config
ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal

WORKDIR /app

# Install Python dependencies first (Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy project source code
COPY config.py run_all.py ./
COPY src/ src/
COPY notebooks/ notebooks/
COPY tests/ tests/

# Create necessary directories
RUN mkdir -p data/inputs data/outputs secrets

# Default: show help
CMD ["python", "run_all.py", "--help"]
