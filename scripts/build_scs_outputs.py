#!/usr/bin/env python
"""Run Notebook/07_publication_outputs.ipynb to build the SCS figures and tables.

There is one definition of every figure, and it lives in that notebook. This script only
executes it, so nothing here can drift from what the notebook draws.

    python scripts/build_scs_outputs.py            # run the whole notebook in place
    python scripts/build_scs_outputs.py --cells 3 5 7
    python scripts/build_scs_outputs.py --no-inplace   # leave the notebook unexecuted

Writing back only happens when every cell succeeds.
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NB = ROOT / "Notebook" / "07_publication_outputs.ipynb"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cells", nargs="*", type=int, default=None,
                    help="run only these cell indices (for iterating on one figure)")
    ap.add_argument("--no-inplace", action="store_true",
                    help="execute without writing the notebook back")
    ap.add_argument("--timeout", type=int, default=1800)
    a = ap.parse_args(argv)

    import nbformat
    from nbclient import NotebookClient

    nb = nbformat.read(NB, as_version=4)
    if a.cells is not None:
        keep = set(a.cells)
        nb.cells = [c for i, c in enumerate(nb.cells) if i in keep]
        print("running %d of the notebook's cells: %s" % (len(nb.cells), sorted(keep)))
    client = NotebookClient(nb, timeout=a.timeout, kernel_name="python3",
                            resources={"metadata": {"path": str(NB.parent)}},
                            allow_errors=False)
    client.execute()

    failed = [i for i, c in enumerate(nb.cells)
              for o in c.get("outputs", []) if o.get("output_type") == "error"]
    for i, c in enumerate(nb.cells):
        for o in c.get("outputs", []):
            if o.get("output_type") == "stream":
                sys.stdout.write(o.get("text", ""))
            elif o.get("output_type") == "error":
                print("ERROR in cell %d: %s: %s" % (i, o.get("ename"), o.get("evalue")))
    if failed:
        return 1
    if a.cells is None and not a.no_inplace:
        nbformat.write(nb, NB)
        print("notebook written back with outputs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
