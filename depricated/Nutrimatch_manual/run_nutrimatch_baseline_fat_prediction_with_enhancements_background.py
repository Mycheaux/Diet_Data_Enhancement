"""Run the baseline body-fat NutriMatch benchmark notebook.

This executes nutrimatch_baseline_fat_prediction_with_enhancements.ipynb with
DDE_RUN_TRAINING=1 so the long run can continue after SageMaker disconnects.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path


NOTEBOOK_NAME = "nutrimatch_baseline_fat_prediction_with_enhancements.ipynb"


def find_project_root() -> Path:
    cwd = Path.cwd().resolve()
    if (cwd / "downstream_analysis").exists():
        return cwd
    tre_root = Path("/home/ec2-user/studies/Diet_Data_Enhancement_Project/Diet_Data_Enhancement_TRE")
    if (tre_root / "downstream_analysis").exists():
        return tre_root
    for parent in [cwd, *cwd.parents]:
        if (parent / "downstream_analysis").exists():
            return parent
    raise RuntimeError("Could not find Diet_Data_Enhancement_TRE project root.")


def fallback_display(value) -> None:
    try:
        import pandas as pd

        if isinstance(value, pd.DataFrame):
            print(value.head(80).to_string())
            return
        if isinstance(value, pd.Series):
            print(value.head(80).to_string())
            return
    except Exception:
        pass
    print(value)


def main() -> int:
    project_root = find_project_root()
    os.chdir(project_root)
    sys.path.insert(0, str(project_root))
    os.environ["DDE_RUN_TRAINING"] = "1"
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    os.environ.setdefault("DDE_MODEL", "lightgbm")
    os.environ.setdefault("DDE_ALLOW_MODEL_FALLBACK", "1")
    os.environ.setdefault("DDE_RUN_RF_SUPPLEMENT", "1")
    os.environ.setdefault("DDE_X_BATCH_SIZE", "20")

    notebook_path = project_root / "depricated/Nutrimatch_manual" / NOTEBOOK_NAME
    output_dir = project_root / "downstream_analysis/tasks/nutrimatch_baseline_fat_prediction_with_enhancements/outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Project:", project_root, flush=True)
    print("Notebook:", notebook_path, flush=True)
    print("Output directory:", output_dir, flush=True)
    print("DDE_RUN_TRAINING=1", flush=True)
    print("DDE_MODEL:", os.environ.get("DDE_MODEL"), flush=True)
    print("DDE_ALLOW_MODEL_FALLBACK:", os.environ.get("DDE_ALLOW_MODEL_FALLBACK"), flush=True)
    print("DDE_RUN_RF_SUPPLEMENT:", os.environ.get("DDE_RUN_RF_SUPPLEMENT"), flush=True)
    print("DDE_X_BATCH_SIZE:", os.environ.get("DDE_X_BATCH_SIZE"), flush=True)

    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    namespace = {
        "__name__": "__main__",
        "__file__": str(notebook_path),
        "display": fallback_display,
    }

    code_cells = [cell for cell in notebook.get("cells", []) if cell.get("cell_type") == "code"]
    print(f"Executing {len(code_cells)} code cells from {notebook_path}", flush=True)

    for number, cell in enumerate(code_cells, start=1):
        source = "".join(cell.get("source", []))
        if not source.strip():
            continue
        print(f"\n--- code cell {number}/{len(code_cells)} ---", flush=True)
        try:
            exec(compile(source, f"{notebook_path}:cell-{number}", "exec"), namespace)
        except Exception:
            print(f"Failed in code cell {number}", flush=True)
            traceback.print_exc()
            print("\nSTATUS: FAILED - see traceback above", flush=True)
            return 1

    print("\nSTATUS: COMPLETE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
