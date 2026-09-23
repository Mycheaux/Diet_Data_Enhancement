#!/usr/bin/env python
"""Run NutriMatch paper-target prediction outside the notebook browser session."""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path


def display(*objects, **_kwargs):
    """Small Jupyter display fallback for console execution."""
    for obj in objects:
        print(obj, flush=True)


def main() -> int:
    os.environ.setdefault("DDE_RUN_TRAINING", "1")
    os.environ.setdefault("DDE_BACKGROUND_WORKER", "1")
    notebook_path = Path(__file__).with_name("nutrimatch_paper_targets_prediction.ipynb")
    if not notebook_path.exists():
        print(f"Notebook not found: {notebook_path}", flush=True)
        return 2
    project_root = notebook_path.resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    if str(Path.cwd()) not in sys.path:
        sys.path.insert(0, str(Path.cwd()))
    os.chdir(project_root)

    namespace = {
        "__name__": "__main__",
        "__file__": str(notebook_path),
        "display": display,
    }
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    code_cells = [cell for cell in notebook["cells"] if cell.get("cell_type") == "code"]
    print(f"Executing {len(code_cells)} code cells from {notebook_path}", flush=True)
    print(f"DDE_RUN_TRAINING={os.environ.get('DDE_RUN_TRAINING')}", flush=True)

    for cell_number, cell in enumerate(code_cells, start=1):
        source = "".join(cell.get("source", []))
        if not source.strip():
            continue
        if (
            ("subprocess.Popen(" in source and "background_training.pid" in source)
            or ("nohup python" in source and "background_training.pid" in source)
        ):
            print(f"\n--- skipping launcher cell {cell_number}/{len(code_cells)} ---", flush=True)
            continue
        print(f"\n--- code cell {cell_number}/{len(code_cells)} ---", flush=True)
        try:
            exec(compile(source, f"{notebook_path}:cell-{cell_number}", "exec"), namespace)
        except Exception:
            print(f"Failed in code cell {cell_number}", flush=True)
            traceback.print_exc()
            return 1

    print("\nBackground run finished successfully.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
