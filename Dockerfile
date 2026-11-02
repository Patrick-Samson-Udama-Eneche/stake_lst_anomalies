# =============================================================================
# Dockerfile — stake_lst_modelling
# =============================================================================
# The same environment as the published results: Python 3.12.10 and the exact package
# versions in requirements.lock (the geospatial wheels bring their own GDAL and PROJ).
#
# Build:            docker build -t stake-lst-modelling .
# Tests:            docker run --rm stake-lst-modelling pytest tests -q
# Jupyter Lab:      docker compose up lab            (see docker-compose.yml)
# Reproduce (R1):   docker compose run --rm reproduce
#
# Data, Results and secrets are mounted at run time, never baked into the image.
# =============================================================================

FROM python:3.12.10-slim

# git lets scripts/env_report.py record the commit of a run
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first, for layer caching
COPY requirements.lock .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.lock \
    && python -m ipykernel install --sys-prefix --name python3

# Project code
COPY config.py run_all.py requirements.txt ./
COPY src/ src/
COPY scripts/ scripts/
COPY Notebook/ Notebook/
COPY tests/ tests/
COPY docs/ docs/

RUN mkdir -p data Results secrets

CMD ["python", "run_all.py", "--help"]
