#!/usr/bin/env python
"""Check the state of this project: environment, code, dataset and outputs.

    python scripts/check_project.py

Prints PASS, FAIL or NOTE for each check, and exits with 1 if anything failed. It makes no remote
call and runs no pipeline notebook. So it shows that the notebooks are intact and that everything
they import loads; it cannot show that NB01, NB03, NB04 and NB05 still reach Earth Engine or EUMETSAT.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.metadata as metadata
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "Results/05_hotspot_analysis/surface_thermal_anomaly_stakeholder_composite"
OUTPUTS = ROOT / "Results/manuscript_outputs"
CACHES = ["01_aoi_delineation", "02_stakeholder_analysis", "03_temporal_analysis", "04_temporal_analysis_daily",
          "05_hotspot_analysis", "06_hotspot_modelling"]
COUNT = {"PASS": 0, "FAIL": 0, "NOTE": 0}


def report(status, what, detail=""):
    COUNT[status] += 1
    print(f"  [{status}] {what}" + (f": {detail}" if detail else ""), flush=True)


def check(ok, what, detail=""):
    report("PASS" if ok else "FAIL", what, detail)


def git(*args):
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True).stdout.strip()


def check_environment():
    print("Environment")
    version = sys.version.split()[0]
    check(version == "3.12.10", "Python 3.12.10", version)
    wrong, n = [], 0
    for line in (ROOT / "requirements.lock").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        req = Requirement(line)
        if req.marker and not req.marker.evaluate():
            continue
        n += 1
        try:
            found = metadata.version(req.name)
            if found not in req.specifier:
                wrong.append(f"{req.name} {found} (lock {req.specifier})")
        except metadata.PackageNotFoundError:
            wrong.append(f"{req.name} missing")
    check(not wrong, f"{n} packages at the versions in requirements.lock", "; ".join(wrong[:12]))


def notebook_cells(path):
    """The code cells of a notebook, as plain Python: IPython turns its magics into calls."""
    from IPython.core.inputtransformer2 import TransformerManager
    nb = json.loads(path.read_text(encoding="utf-8"))
    for i, cell in enumerate(nb["cells"]):
        if cell["cell_type"] == "code":
            yield i, TransformerManager().transform_cell("".join(cell["source"]))


def top_level_imports(tree):
    """Module names imported outside any try block; a try block marks an optional package."""
    optional = {id(n) for t in ast.walk(tree) if isinstance(t, ast.Try) for b in t.body for n in ast.walk(b)}
    names = set()
    for node in ast.walk(tree):
        if id(node) in optional:
            continue
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def check_code():
    print("Code")
    used, bad = defaultdict(set), []
    notebooks = sorted((ROOT / "Notebook").glob("0*.ipynb"))
    for nb in notebooks:
        for i, code in notebook_cells(nb):
            try:
                for name in top_level_imports(ast.parse(code)):
                    used[name].add(nb.name[:2])
            except SyntaxError as e:
                bad.append(f"{nb.name} cell {i} line {e.lineno}")
    check(len(notebooks) == 7 and not bad, f"{len(notebooks)} notebooks open, and every code cell parses", "; ".join(bad[:8]))

    files = [*ROOT.glob("src/*.py"), *ROOT.glob("scripts/*.py"), ROOT / "config.py", ROOT / "run_all.py"]
    bad = []
    for f in files:
        try:
            for name in top_level_imports(ast.parse(f.read_text(encoding="utf-8"))):
                used[name].add(f.stem)
        except SyntaxError as e:
            bad.append(f"{f.name} line {e.lineno}")
    check(not bad, f"{len(files)} Python files parse", "; ".join(bad))

    local = {f.stem for f in files}
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")])}
    packages = sorted(set(used) - set(sys.stdlib_module_names) - local) + sorted(f.stem for f in ROOT.glob("src/*.py"))
    failed = []
    for name in packages:
        for attempt in range(3):                   # a Windows security block can clear on a retry
            run = subprocess.run([sys.executable, "-B", "-c", f"import {name}"], capture_output=True, text=True, cwd=ROOT, env=env)
            if run.returncode == 0:
                break
        else:
            last = (run.stderr.strip().splitlines() or ["no message"])[-1]
            who = ", ".join(sorted(used.get(name, {name})))[:50]
            failed.append(f"{name} (used by {who}): {last[:110]}")
    check(not failed, f"{len(packages)} packages and project modules load", "")
    for f in failed:
        print(f"         {f}")

    run = subprocess.run([sys.executable, "-B", "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider"], capture_output=True, text=True, cwd=ROOT)
    check(run.returncode == 0, "the test suite", (run.stdout.strip().splitlines() or [""])[-1])


def check_dataset():
    print("Dataset")
    sums = DATASET / "checksums_md5.txt"
    if not sums.exists():
        report("NOTE", "the dataset is not in this folder", "it is not in git; download it from Zenodo (10.5281/zenodo.23050559)")
        return
    bad, n = [], 0
    for line in sums.read_text(encoding="utf-8").splitlines():
        if line.strip():
            md5, name = line.split(maxsplit=1)
            name = name.lstrip("*")
            n += 1
            if not (DATASET / name).exists() or hashlib.md5((DATASET / name).read_bytes()).hexdigest() != md5:
                bad.append(name)
    check(not bad, f"{n} files match their checksums", ", ".join(bad))
    import pyogrio
    layers = len(pyogrio.list_layers(DATASET / "surface_thermal_anomaly_stakeholder_composite.gpkg"))
    check(layers == 18, "the GeoPackage has 18 layers", str(layers))


def check_results():
    print("Results")
    missing = [c for c in CACHES if not any((ROOT / "Results" / c).glob("*"))]
    if missing:
        report("NOTE", "caches missing, so Notebook 07 cannot rebuild yet", ", ".join(missing))
    else:
        report("PASS", "the caches of NB01-NB06 are here")
    if not (OUTPUTS / "main_figures").exists():
        report("NOTE", "no manuscript outputs here", "they are published with the article; Notebook 07 rebuilds them")
        return
    expected = (("main_figures", "Fig_*.pdf", 14), ("main_tables", "Table_*.csv", 5), ("supplementary_tables", "Supp_Table_*.csv", 8),
                ("supplementary_figures", "S*/", 11))
    for folder, pattern, n in expected:
        found = len(list((OUTPUTS / folder).glob(pattern)))
        check(found == n, f"{folder} holds {n} items", str(found))
    pdfs = list(OUTPUTS.rglob("*.pdf"))
    bad = [p.name for p in pdfs if p.read_bytes()[:5] != b"%PDF-"]
    check(pdfs and not bad, f"{len(pdfs)} PDFs are real PDFs", ", ".join(bad[:5]))

    run = ROOT / "Results/_provenance/executed_07_publication_outputs.ipynb"
    if not run.exists():
        report("NOTE", "Notebook 07 has no recorded run here", "python run_all.py --scope manuscript --output-dir Results/_provenance")
        return
    nb = json.loads(run.read_text(encoding="utf-8"))
    outputs = [o for c in nb["cells"] for o in c.get("outputs", [])]
    errors = sum(o["output_type"] == "error" for o in outputs)
    text = "".join("".join(o.get("text", "")) for o in outputs)
    found = re.findall(r"Assertions: (\d+) of (\d+) passed", text)
    good = bool(found) and found[-1][0] == found[-1][1] and not errors
    check(good, "the last run of Notebook 07", f"{found[-1][0]} of {found[-1][1]} checks, {errors} cell errors" if found else "no check summary")


def check_repository():
    print("Repository")
    print(f"  branch {git('branch', '--show-current')}, {git('rev-list', '--count', 'HEAD')} commits, remote {git('remote', 'get-url', 'origin')}")
    changed = git("status", "--porcelain").splitlines()
    if changed:
        report("NOTE", f"{len(changed)} files changed or new", "; ".join(c[3:] for c in changed[:5]))
    else:
        report("PASS", "nothing uncommitted")
    secret = re.compile(r"(service_account|credentials)\.json$|\.pem$|\.key$|^\.env$")
    tracked = [f for f in git("ls-files").splitlines() if secret.search(f)]
    check(not tracked, "no credential file is tracked", ", ".join(tracked))
    have = [f for f in ("gee_service_account.json", "eumetsat_credentials.json") if (ROOT / "secrets" / f).exists()]
    report("NOTE", "credentials here (needed only for NB01, NB03, NB04, NB05)", ", ".join(have) or "none")


def main():
    print(f"Project check: {ROOT}\n")
    for step in (check_environment, check_code, check_dataset, check_results, check_repository):
        step()
        print()
    print(f"{COUNT['PASS']} passed, {COUNT['FAIL']} failed, {COUNT['NOTE']} notes")
    return 1 if COUNT["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
