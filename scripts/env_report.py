#!/usr/bin/env python
"""Record the computing environment of a run.

Writes Results/_provenance/environment_<date>.json with the Python and OS versions, every
installed package and its version, the git commit and whether the working tree is dirty, the
GDAL and PROJ versions, and the CPU count. run_all.py and the dataset build call it.

    python scripts/env_report.py
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import platform
import subprocess
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "Results" / "_provenance"


def _git(*args):
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                              timeout=20).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def _gdal_proj():
    out = {}
    try:
        import rasterio
        out["gdal"] = rasterio.__gdal_version__
    except Exception:                      # not installed or no GDAL: record the absence
        out["gdal"] = None
    try:
        import pyproj
        out["proj"] = pyproj.proj_version_str
    except Exception:
        out["proj"] = None
    return out


def environment() -> dict:
    status = _git("status", "--porcelain")
    return {
        "recorded": _dt.datetime.now().isoformat(timespec="seconds"),
        "python": sys.version.split()[0],
        "python_executable": sys.executable,
        "os": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "git_commit": _git("rev-parse", "HEAD"),
        "git_dirty": bool(status) if status is not None else None,
        **_gdal_proj(),
        "packages": dict(sorted((d.metadata["Name"], d.version) for d in metadata.distributions()
                                if d.metadata["Name"])),
    }


def write(out_dir: Path = OUT_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"environment_{_dt.date.today().isoformat()}.json"
    p.write_text(json.dumps(environment(), indent=2), encoding="utf-8")
    return p


if __name__ == "__main__":
    print("Environment recorded:", write().relative_to(ROOT))
