#!/usr/bin/env python
"""Keep notebook outputs, figures, results and secrets out of git.

    python scripts/strip_outputs.py install   # once per clone: sets up the filter and the pre-commit check
    python scripts/strip_outputs.py clean     # the git filter: a notebook on stdin, the same notebook without outputs on stdout
    python scripts/strip_outputs.py check     # the pre-commit check: refuses a commit that would add any of the above

The filter clears every code cell's outputs and execution count, drops the run timings from the cell
metadata and gives the notebook the generic kernel `python3`. It works on what git stores, not on the
file on disk: notebooks keep their figures and tables in the editor, and the repository holds code and
text only. `git restore` or `git checkout` of a notebook brings back the stored version,
without outputs.

The check runs before every commit. It refuses notebooks that still carry outputs (the filter is not
installed in that clone), figure, office, archive and binary data files, anything under `Results/`
except `cluster_labels.csv`, and anything under `secrets/`, `private/` or `docs/` except the templates.

Standard library only, so any Python 3 runs it.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILTER = "strip-outputs"
KERNEL = {"display_name": "Python 3 (ipykernel)", "language": "python", "name": "python3"}
RUN_METADATA = ("execution", "ExecuteTime")

BLOCKED_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".pdf", ".eps", ".tif", ".tiff", ".webp",
    ".xlsx", ".xls", ".docx", ".doc", ".pptx", ".odt", ".ods",
    ".zip", ".7z", ".gz", ".tar", ".rar",
    ".gpkg", ".shp", ".shx", ".dbf", ".prj", ".cpg", ".parquet", ".feather", ".pkl", ".pickle",
    ".nc", ".h5", ".hdf5", ".npy", ".npz", ".joblib",
}
ALLOWED = {
    "Results/manuscript_outputs/cluster_labels.csv",
    "secrets/.gitignore",
    "secrets/README.md",
    "secrets/eumetsat_credentials.json.example",
    "secrets/gee_service_account.json.example",
}
BLOCKED_FOLDERS = ("Results/", "secrets/", "private/", "docs/")


def strip(nb: dict) -> dict:
    """Return the notebook without outputs, execution counts or run timings."""
    for cell in nb.get("cells", []):
        if cell.get("cell_type") == "code":
            cell["outputs"] = []
            cell["execution_count"] = None
        meta = cell.get("metadata")
        if isinstance(meta, dict):
            for key in RUN_METADATA:
                meta.pop(key, None)
    meta = nb.setdefault("metadata", {})
    if "kernelspec" in meta:
        meta["kernelspec"] = dict(KERNEL)
    return nb


def dumps(nb: dict) -> bytes:
    """Write a notebook the way Jupyter and VS Code do: sorted keys, one-space indent, UTF-8."""
    return (json.dumps(nb, sort_keys=True, indent=1, ensure_ascii=False) + "\n").encode("utf-8")


def clean_bytes(raw: bytes) -> bytes:
    """Strip a notebook given as bytes; anything that is not a notebook passes through unchanged."""
    try:
        nb = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return raw
    if not isinstance(nb, dict) or "cells" not in nb:
        return raw
    return dumps(strip(nb))


def has_outputs(nb: dict) -> bool:
    return any(cell.get("outputs") or cell.get("execution_count") is not None
               for cell in nb.get("cells", []) if cell.get("cell_type") == "code")


def git(*args: str, binary: bool = False):
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout
    return out if binary else out.decode("utf-8")


def check() -> int:
    staged = [p for p in git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z").split("\0") if p]
    problems = []
    for path in staged:
        suffix = Path(path).suffix.lower()
        if path in ALLOWED:
            continue
        if path.startswith(BLOCKED_FOLDERS):
            problems.append(f"{path}: results, secrets and working notes stay out of git")
        elif suffix in BLOCKED_SUFFIXES:
            problems.append(f"{path}: figures, documents and binary data stay out of git")
        elif suffix == ".ipynb":
            try:
                nb = json.loads(git("show", f":{path}", binary=True).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                problems.append(f"{path}: not a valid notebook")
                continue
            if has_outputs(nb):
                problems.append(f"{path}: still has outputs; run `python scripts/strip_outputs.py install`, "
                                f"then `git add {path}` again")
    if problems:
        print("Commit refused:")
        for p in problems:
            print(f"  {p}")
        return 1
    return 0


def install() -> int:
    python = Path(sys.executable).as_posix()
    script = "scripts/strip_outputs.py"
    git("config", f"filter.{FILTER}.clean", f'"{python}" {script} clean')
    hooks = Path(git("rev-parse", "--git-path", "hooks").strip())
    hooks = hooks if hooks.is_absolute() else ROOT / hooks
    hook = hooks / "pre-commit"
    body = f'#!/bin/sh\nexec "{python}" {script} check\n'
    if hook.exists() and script not in hook.read_text(encoding="utf-8", errors="replace"):
        print(f"{hook} exists and is not mine; add this line to it by hand:\n  {body.splitlines()[1]}")
        return 1
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(body, encoding="utf-8", newline="\n")
    hook.chmod(0o755)
    print(f"Filter '{FILTER}' and pre-commit check installed, using {python}.")
    print("Notebooks already in git are stripped the next time they are staged "
          "(`git add --renormalize .` does all of them at once).")
    return 0


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "clean":
        sys.stdout.buffer.write(clean_bytes(sys.stdin.buffer.read()))
        return 0
    if command == "check":
        return check()
    if command == "install":
        return install()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
