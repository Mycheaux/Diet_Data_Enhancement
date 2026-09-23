"""Export the supplied comparator separately; never called by de novo builders."""

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .independent_pilot import HPP, ROOT, digest, write_json


OUT = ROOT / "outputs_GEN2/step1c_expanded_schema/nutrimatch_based"
METADATA = {"food_id", "short_description", "category_hint", "product_name", "short_name",
            "hebrew_name", "gpt_short_food_name", "number_loggings"}


def export_baseline(path=HPP, out=OUT):
    source = pd.read_csv(path, dtype={"food_id": str})
    if not METADATA.issubset(source.columns):
        raise ValueError("Unexpected NutriMatch input metadata schema.")
    if source.food_id.isna().any() or source.food_id.duplicated().any():
        raise ValueError("Missing or duplicate food IDs.")
    nutrients = [name for name in source.columns if name not in METADATA]
    if not nutrients or not np.isfinite(source[nutrients].to_numpy(dtype=float)).all():
        raise ValueError("Nonfinite or absent comparator nutrients.")
    if (source[nutrients] < 0).any().any():
        raise ValueError("Negative comparator nutrients.")
    out.mkdir(parents=True, exist_ok=True)
    matrix = source[["food_id", "product_name"] + nutrients].rename(columns={"food_id": "hpp_food_id", "product_name": "food_name"})
    matrix.to_csv(out / "food_features.csv", index=False)
    # This branch preserves the input, without certifying its measurements or units.
    pd.DataFrame([{"feature_name": name, "feature_type": "supplied_nutrient",
                   "basis": "per_100g_as_supplied", "unit_status": "inherited_not_revalidated",
                   "provenance_method": "supplied_nutrimatch_value_unchanged",
                   "source_column": name, "source_file": str(path)} for name in nutrients]).to_csv(out / "feature_dictionary.csv", index=False)
    pd.DataFrame({"hpp_food_id": matrix.hpp_food_id, "source_food_id": source.food_id,
                  "method": "supplied_nutrimatch_value_unchanged"}).to_csv(out / "row_provenance.csv", index=False)
    summary = {"food_rows": len(matrix), "nutrient_columns": len(nutrients), "identity_columns": 2,
               "filled_nutrient_cells": int(matrix[nutrients].notna().sum().sum()),
               "recorded_zero_cells": int(matrix[nutrients].eq(0).sum().sum()),
               "values_changed": 0, "downstream_features_added": 0,
               "status": "supplied_comparator_exported_not_newly_validated"}
    write_json("summary.json", summary, out)
    write_json("run_manifest.json", {"created_at_utc": datetime.now(timezone.utc).isoformat(),
               "source_sha256": digest(path), "code_sha256": digest(Path(__file__)),
               "output_hashes": {p.name: digest(p) for p in sorted(out.glob("*.csv"))}}, out)
    print(summary)
    return summary


if __name__ == "__main__":
    export_baseline()
