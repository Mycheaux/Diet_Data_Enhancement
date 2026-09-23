#!/usr/bin/env python
"""Run the archived all-target NutriMatch prediction notebook from a console."""

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
    os.environ.setdefault("PYTHONUNBUFFERED", "1")

    notebook_path = Path(__file__).with_name(
        "nutrimatch_all_predictions_linear_hgb_explainability.ipynb"
    )
    if not notebook_path.exists():
        print(f"Notebook not found: {notebook_path}", flush=True)
        return 2

    project_root = notebook_path.resolve().parents[2]
    os.chdir(project_root)
    for path in [project_root, Path.cwd()]:
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))

    output_dir = (
        project_root
        / "depricated/Nutrimatch_manual/outputs"
        / "nutrimatch_all_predictions_linear_hgb_explainability"
        / "outputs"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    namespace = {
        "__name__": "__main__",
        "__file__": str(notebook_path),
        "display": display,
    }
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    code_cells = [cell for cell in notebook["cells"] if cell.get("cell_type") == "code"]

    print(f"Executing {len(code_cells)} code cells from {notebook_path}", flush=True)
    print(f"Project root: {project_root}", flush=True)
    print(f"Output directory: {output_dir}", flush=True)
    print(f"DDE_RUN_TRAINING={os.environ.get('DDE_RUN_TRAINING')}", flush=True)
    print(f"DDE_USE_GPU={os.environ.get('DDE_USE_GPU', '1')}", flush=True)
    print(f"DDE_MODEL_FILTER={os.environ.get('DDE_MODEL_FILTER', '') or 'linear,tree'}", flush=True)

    try:
        for cell_number, cell in enumerate(code_cells, start=1):
            source = "".join(cell.get("source", []))
            if not source.strip():
                continue
            print(f"\n--- code cell {cell_number}/{len(code_cells)} ---", flush=True)
            exec(compile(source, f"{notebook_path}:cell-{cell_number}", "exec"), namespace)
    except Exception:
        print(f"Failed in code cell {cell_number}", flush=True)
        traceback.print_exc()
        print("\nSTATUS: FAILED - see traceback above", flush=True)
        return 1

    expected = [
        "all_prediction_model_results.csv",
        "all_prediction_fold_metrics.csv",
        "all_prediction_oof_predictions.csv",
        "linear_coefficients.csv",
        "tree_shap_feature_importance.csv",
        "tree_shap_dependence_long.csv",
        "paper_ready_all_prediction_results.csv",
        "arm_summary.csv",
    ]
    print("\nExpected output files:", flush=True)
    for name in expected:
        path = output_dir / name
        print(f"{name} exists= {path.exists()} size= {path.stat().st_size if path.exists() else None}", flush=True)

    print("\nSTATUS: COMPLETE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
