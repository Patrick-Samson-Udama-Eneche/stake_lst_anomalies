"""
Master Runner Script for LST Modeling Project
==============================================

Executes all project notebooks in the correct dependency order:
  01 → 01a → 02 → 03 → 04 → 05 → 061 → 062 → 063

Usage:
------
  # Run all notebooks for all cities (from CSV):
  python run_all.py

  # Run for specific cities only, see readme for valid names:
  python run_all.py --cities "Lagos" "Abuja" "Kano"

  # Run only specific notebooks:
  python run_all.py --notebooks 01 05

  # Dry-run (check dependencies without executing):
  python run_all.py --dry-run

  # Skip notebooks that require external API credentials:
  python run_all.py --skip-gee --skip-eumetsat

  # Continue from a specific notebook (skip earlier ones):
  python run_all.py --start-from 05

Notes:
------
  - Notebook 01 requires city selection. When run via this script, cities
    are injected automatically (bypassing the interactive widget).
  - Notebooks 01a, 03, 04 require Google Earth Engine credentials.
  - Notebook 04 (SEVIRI section) requires EUMETSAT credentials.
  - Notebook 02 is independent and can run in parallel with 01a/03.
  - Notebook 05 requires outputs from Notebook 04 (SEVIRI rasters).
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Path setup — make sure config.py and src/ are importable
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    import nbformat
    from nbclient import NotebookClient
except ImportError:
    print("ERROR: nbformat and nbclient are required.")
    print("  Install with: pip install nbformat nbclient")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

NOTEBOOKS_DIR = PROJECT_ROOT / "notebooks"

# Ordered list of notebooks with metadata
NOTEBOOK_REGISTRY = [
    {
        "id": "01",
        "file": "01_AOI_delineation.ipynb",
        "name": "AOI Delineation",
        "description": "Define Areas of Interest for selected Nigerian cities",
        "requires_gee": False,
        "requires_eumetsat": False,
        "accepts_cities": True,        # Can receive city selection
        "depends_on": [],
    },
    {
        "id": "01a",
        "file": "01a_AOI_OSM_JRC_features.ipynb",
        "name": "OSM/JRC Feature Extraction",
        "description": "Extract OpenStreetMap and JRC geospatial features for AOIs",
        "requires_gee": True,
        "requires_eumetsat": False,
        "accepts_cities": False,       # Auto-discovers from 01 outputs
        "depends_on": ["01"],
    },
    {
        "id": "02",
        "file": "02_stakeholder_analysis.ipynb",
        "name": "Stakeholder Analysis",
        "description": "Analyze stakeholder survey data and create visualizations",
        "requires_gee": False,
        "requires_eumetsat": False,
        "accepts_cities": False,       # Uses survey data directly
        "depends_on": [],              # Independent
    },
    {
        "id": "03",
        "file": "03_temporal_analysis_months_annual.ipynb",
        "name": "Monthly/Annual LST Analysis",
        "description": "Extract and analyze monthly/annual LST trends via GEE",
        "requires_gee": True,
        "requires_eumetsat": False,
        "accepts_cities": False,       # Auto-discovers from 01 outputs
        "depends_on": ["01"],
    },
    {
        "id": "04",
        "file": "04_temporal_analysis_daily.ipynb",
        "name": "Daily LST Analysis",
        "description": "Daily LST extraction (MODIS, ERA5, SEVIRI) and heat event analysis",
        "requires_gee": True,
        "requires_eumetsat": True,
        "accepts_cities": False,       # Auto-discovers from 01 outputs
        "depends_on": ["01"],
    },
    {
        "id": "05",
        "file": "05_hotspot_analysis.ipynb",
        "name": "Hotspot Analysis",
        "description": "UHI hotspot detection, KDE delineation, enrichment, and visualization",
        "requires_gee": True,          # For GHSL population download
        "requires_eumetsat": False,
        "accepts_cities": False,       # Auto-discovers from 04 SEVIRI outputs
        "depends_on": ["04"],
    },
    {
        "id": "06",
        "file": "06_hotspot_modelling.ipynb",
        "name": "Hotspot Modelling",
        "description": "Landscape-oriented modelling of hotspot occurrence (logistic) and extent (OLS clustered)",
        "requires_gee": False,
        "requires_eumetsat": False,
        "accepts_cities": False,
        "depends_on": ["05"],
    },
]


def get_notebook_by_id(nb_id: str) -> Optional[dict]:
    """Get notebook registry entry by ID."""
    for nb in NOTEBOOK_REGISTRY:
        if nb["id"] == nb_id:
            return nb
    return None


# ---------------------------------------------------------------------------
# Credential checks
# ---------------------------------------------------------------------------

def check_gee_credentials() -> bool:
    """Check if Google Earth Engine credentials are available."""
    try:
        import config
        gee_json = Path(config.GEE_CONFIG.get("service_json", ""))
        if gee_json.exists():
            print(f"  [OK] GEE service account: {gee_json.name}")
            return True
        # Fallback check
        fallback = PROJECT_ROOT / "secrets" / "gee_service_account.json"
        if fallback.exists():
            print(f"  [OK] GEE service account (fallback): {fallback.name}")
            return True
        print("  [MISSING] GEE service account JSON not found")
        return False
    except Exception as e:
        print(f"  [ERROR] GEE credential check failed: {e}")
        return False


def check_eumetsat_credentials() -> bool:
    """Check if EUMETSAT credentials are available."""
    try:
        creds_path = PROJECT_ROOT / "secrets" / "eumetsat_credentials.json"
        if creds_path.exists():
            with open(creds_path, encoding='utf-8') as f:
                creds = json.load(f)
            if creds.get("consumer_key") and creds.get("consumer_secret"):
                print(f"  [OK] EUMETSAT credentials: {creds_path.name}")
                return True
            print("  [INCOMPLETE] EUMETSAT credentials file exists but keys are empty")
            return False
        print("  [MISSING] EUMETSAT credentials not found")
        return False
    except Exception as e:
        print(f"  [ERROR] EUMETSAT credential check failed: {e}")
        return False


def load_available_cities() -> list:
    """Load all available cities from the project CSV."""
    try:
        import pandas as pd
        import config
        cities_path = config.get_aoi_data_path("cities_csv")
        df = pd.read_csv(cities_path)
        return sorted(df["Urban Agglomeration"].dropna().tolist())
    except Exception as e:
        print(f"  [WARNING] Could not load city list: {e}")
        return []


# ---------------------------------------------------------------------------
# Notebook execution
# ---------------------------------------------------------------------------

def inject_city_selection(nb: nbformat.NotebookNode, cities: list) -> nbformat.NotebookNode:
    """
    Inject city selection into Notebook 01 by modifying the parameter cell.

    Strategy: Find the cell with `selected_city = "Lagos"` and replace it
    with direct city list assignment, bypassing the interactive widget.
    """
    cities_str = json.dumps(cities)

    injection_code = f"""# === INJECTED BY run_all.py (automated execution) ===
# Bypasses interactive widget for batch processing
import sys, os
sys.path.insert(0, os.path.dirname(os.getcwd()))

# Cities selected for this run
_INJECTED_CITIES = {cities_str}
selected_city = _INJECTED_CITIES[0]  # Primary city (for backwards compatibility)
print(f"[run_all.py] Processing {{len(_INJECTED_CITIES)}} cities: {{', '.join(_INJECTED_CITIES)}}")
"""

    for i, cell in enumerate(nb.cells):
        if cell.cell_type == "code" and 'selected_city = "Lagos"' in cell.source:
            nb.cells[i].source = injection_code
            break

    # Also patch get_selected_cities() to return injected list
    for i, cell in enumerate(nb.cells):
        if cell.cell_type == "code" and "def get_selected_cities():" in cell.source:
            patched = cell.source.replace(
                "def get_selected_cities():",
                "def get_selected_cities():\n"
                "    # Patched by run_all.py for automated execution\n"
                f"    if '_INJECTED_CITIES' in dir():\n"
                f"        return _INJECTED_CITIES\n"
                f"    if '_INJECTED_CITIES' in globals():\n"
                f"        return globals()['_INJECTED_CITIES']"
            )
            nb.cells[i].source = patched
            break

    return nb


def execute_notebook(
    nb_info: dict,
    cities: Optional[list] = None,
    timeout: int = 7200,
    output_dir: Optional[Path] = None,
) -> dict:
    """
    Execute a single notebook and return status.

    Parameters
    ----------
    nb_info : dict
        Notebook registry entry
    cities : list, optional
        Cities to process (only used for Notebook 01)
    timeout : int
        Maximum execution time in seconds (default: 2 hours)
    output_dir : Path, optional
        Directory for executed notebook output (default: notebooks/)

    Returns
    -------
    dict with keys: success, duration, error, output_path
    """
    nb_path = NOTEBOOKS_DIR / nb_info["file"]
    if output_dir is None:
        output_dir = NOTEBOOKS_DIR

    output_path = output_dir / f"executed_{nb_info['file']}"

    print(f"\n{'='*70}")
    print(f"  Notebook {nb_info['id']}: {nb_info['name']}")
    print(f"  File: {nb_info['file']}")
    print(f"{'='*70}")

    if not nb_path.exists():
        return {
            "success": False,
            "duration": 0,
            "error": f"Notebook file not found: {nb_path}",
            "output_path": None,
        }

    start_time = time.time()

    try:
        # Read notebook
        with open(nb_path, "r", encoding="utf-8") as f:
            nb = nbformat.read(f, as_version=4)

        # Inject city selection for Notebook 01
        if nb_info["accepts_cities"] and cities:
            print(f"  Injecting cities: {', '.join(cities)}")
            nb = inject_city_selection(nb, cities)

        # Execute
        client = NotebookClient(
            nb,
            timeout=timeout,
            kernel_name="python3",
            resources={"metadata": {"path": str(NOTEBOOKS_DIR)}},
        )

        print(f"  Executing... (timeout: {timeout}s)")
        client.execute()

        # Save executed notebook
        with open(output_path, "w", encoding="utf-8") as f:
            nbformat.write(nb, f)

        duration = time.time() - start_time
        print(f"  SUCCESS ({duration:.1f}s)")

        return {
            "success": True,
            "duration": duration,
            "error": None,
            "output_path": str(output_path),
        }

    except Exception as e:
        duration = time.time() - start_time
        error_msg = str(e)

        # Try to save partial output
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                nbformat.write(nb, f)
        except Exception:
            pass

        print(f"  FAILED after {duration:.1f}s")
        print(f"  Error: {error_msg[:200]}")

        return {
            "success": False,
            "duration": duration,
            "error": error_msg,
            "output_path": str(output_path) if output_path.exists() else None,
        }


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def resolve_notebook_order(requested_ids: Optional[list] = None, start_from: Optional[str] = None) -> list:
    """
    Resolve which notebooks to run and in what order.
    Respects dependencies.
    """
    all_ids = [nb["id"] for nb in NOTEBOOK_REGISTRY]

    if requested_ids:
        # Validate
        for rid in requested_ids:
            if rid not in all_ids:
                print(f"ERROR: Unknown notebook ID '{rid}'. Available: {all_ids}")
                sys.exit(1)
        run_ids = requested_ids
    else:
        run_ids = all_ids

    if start_from:
        if start_from not in all_ids:
            print(f"ERROR: Unknown notebook ID '{start_from}'. Available: {all_ids}")
            sys.exit(1)
        idx = all_ids.index(start_from)
        run_ids = [rid for rid in run_ids if all_ids.index(rid) >= idx]

    # Return in registry order
    return [nb for nb in NOTEBOOK_REGISTRY if nb["id"] in run_ids]


def main():
    parser = argparse.ArgumentParser(
        description="Run all LST Modeling Project notebooks in sequence",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--cities",
        nargs="+",
        help="Cities to process (default: all available from CSV)",
    )
    parser.add_argument(
        "--notebooks",
        nargs="+",
        help="Specific notebook IDs to run (e.g., 01 03 05)",
    )
    parser.add_argument(
        "--start-from",
        help="Start execution from this notebook ID (skip earlier ones)",
    )
    parser.add_argument(
        "--skip-gee",
        action="store_true",
        help="Skip notebooks requiring Google Earth Engine",
    )
    parser.add_argument(
        "--skip-eumetsat",
        action="store_true",
        help="Skip notebooks requiring EUMETSAT credentials",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=7200,
        help="Per-notebook timeout in seconds (default: 7200 = 2h)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Directory for executed notebook outputs (default: notebooks/)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show execution plan without running notebooks",
    )
    parser.add_argument(
        "--list-cities",
        action="store_true",
        help="Print the 50 valid city names and exit",
    )

    args = parser.parse_args()

    # ---- Handle --list-cities early exit ----
    if args.list_cities:
        from config import VALID_CITIES
        print(f"\n  Valid city names ({len(VALID_CITIES)} total):")
        print("  " + "-" * 40)
        for i, city in enumerate(VALID_CITIES, 1):
            print(f"  {i:>3}. {city}")
        return

    print("=" * 70)
    print("  LST Modeling Project — Master Runner")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # ---- Step 1: Resolve city selection ----
    if args.cities:
        from config import validate_city_names
        cities = validate_city_names(args.cities)
        if not cities:
            print("\n[ABORT] No valid cities provided. Use --list-cities to see valid names.")
            return
        if len(cities) < len(args.cities):
            invalid = set(args.cities) - set(cities)
            print(f"\n[WARNING] Skipped invalid: {', '.join(invalid)}")
        print(f"\nCities (from CLI): {', '.join(cities)}")
    else:
        cities = load_available_cities()
        if cities:
            print(f"\nCities (from CSV): {len(cities)} available")
            for c in cities[:10]:
                print(f"  - {c}")
            if len(cities) > 10:
                print(f"  ... and {len(cities) - 10} more")
        else:
            print("\n[WARNING] No cities found. Notebook 01 will use default (Lagos).")
            cities = ["Lagos"]

    # ---- Step 2: Check credentials ----
    print("\nCredential checks:")
    has_gee = check_gee_credentials()
    has_eumetsat = check_eumetsat_credentials()

    # ---- Step 3: Resolve notebook order ----
    notebooks_to_run = resolve_notebook_order(args.notebooks, args.start_from)

    # Apply skip filters
    if args.skip_gee:
        skipped = [nb for nb in notebooks_to_run if nb["requires_gee"]]
        notebooks_to_run = [nb for nb in notebooks_to_run if not nb["requires_gee"]]
        if skipped:
            print(f"\nSkipping (--skip-gee): {', '.join(nb['id'] for nb in skipped)}")

    if args.skip_eumetsat:
        skipped = [nb for nb in notebooks_to_run if nb["requires_eumetsat"]]
        notebooks_to_run = [nb for nb in notebooks_to_run if not nb["requires_eumetsat"]]
        if skipped:
            print(f"\nSkipping (--skip-eumetsat): {', '.join(nb['id'] for nb in skipped)}")

    # Warn about missing credentials
    gee_notebooks = [nb for nb in notebooks_to_run if nb["requires_gee"]]
    eumetsat_notebooks = [nb for nb in notebooks_to_run if nb["requires_eumetsat"]]

    if gee_notebooks and not has_gee:
        print(f"\n[WARNING] GEE credentials missing. These may fail: "
              f"{', '.join(nb['id'] for nb in gee_notebooks)}")

    if eumetsat_notebooks and not has_eumetsat:
        print(f"\n[WARNING] EUMETSAT credentials missing. These may fail: "
              f"{', '.join(nb['id'] for nb in eumetsat_notebooks)}")

    # ---- Step 4: Show execution plan ----
    print(f"\nExecution plan ({len(notebooks_to_run)} notebooks):")
    print("-" * 70)
    for i, nb in enumerate(notebooks_to_run, 1):
        deps = f" (after: {', '.join(nb['depends_on'])})" if nb["depends_on"] else ""
        flags = []
        if nb["requires_gee"]:
            flags.append("GEE")
        if nb["requires_eumetsat"]:
            flags.append("EUMETSAT")
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        print(f"  {i}. [{nb['id']}] {nb['name']}{flag_str}{deps}")
    print("-" * 70)

    if args.dry_run:
        print("\n[DRY RUN] No notebooks were executed.")
        return

    # ---- Step 5: Execute notebooks ----
    output_dir = Path(args.output_dir) if args.output_dir else None
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)

    results = {}
    overall_start = time.time()

    for nb_info in notebooks_to_run:
        # Check dependencies
        for dep_id in nb_info["depends_on"]:
            if dep_id in results and not results[dep_id]["success"]:
                print(f"\n  SKIPPING {nb_info['id']}: dependency {dep_id} failed")
                results[nb_info["id"]] = {
                    "success": False,
                    "duration": 0,
                    "error": f"Skipped — dependency {dep_id} failed",
                    "output_path": None,
                }
                continue

        result = execute_notebook(
            nb_info,
            cities=cities if nb_info["accepts_cities"] else None,
            timeout=args.timeout,
            output_dir=output_dir,
        )
        results[nb_info["id"]] = result

    # ---- Step 6: Summary ----
    overall_duration = time.time() - overall_start
    print(f"\n{'='*70}")
    print("  EXECUTION SUMMARY")
    print(f"{'='*70}")
    print(f"  Total time: {overall_duration:.1f}s ({overall_duration/60:.1f} min)")
    print(f"  Cities: {', '.join(cities[:5])}{'...' if len(cities) > 5 else ''}")
    print()

    success_count = sum(1 for r in results.values() if r["success"])
    fail_count = len(results) - success_count

    for nb_id, result in results.items():
        nb = get_notebook_by_id(nb_id)
        status = "PASS" if result["success"] else "FAIL"
        duration = f"{result['duration']:.1f}s"
        error_hint = ""
        if result["error"]:
            error_hint = f" — {result['error'][:60]}"
        print(f"  [{status}] {nb_id} {nb['name']} ({duration}){error_hint}")

    print(f"\n  Result: {success_count} passed, {fail_count} failed")
    print(f"{'='*70}")

    # Save run log
    log_path = PROJECT_ROOT / "data" / "outputs" / "run_all_log.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = {
        "timestamp": datetime.now().isoformat(),
        "cities": cities,
        "duration_seconds": overall_duration,
        "results": {
            k: {
                "success": v["success"],
                "duration": v["duration"],
                "error": v["error"],
            }
            for k, v in results.items()
        },
    }
    with open(log_path, "w", encoding='utf-8') as f:
        json.dump(log, f, indent=2)
    print(f"\n  Run log saved: {log_path.relative_to(PROJECT_ROOT)}")

    sys.exit(0 if fail_count == 0 else 1)


if __name__ == "__main__":
    main()
