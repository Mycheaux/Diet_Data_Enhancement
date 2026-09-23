"""Compare frozen branch outputs only after independent generation."""

import json

import numpy as np
import pandas as pd

from .expand_step1 import OUT as DENOVO
from .export_nutrimatch_base import OUT as BASELINE
from .independent_pilot import OUT as APPROVED, digest, write_json


def main():
    out = DENOVO.parent
    matrix = pd.read_csv(DENOVO / "food_features.csv", dtype={"hpp_food_id": str}).set_index("hpp_food_id", verify_integrity=True)
    baseline = pd.read_csv(BASELINE / "food_features.csv", dtype={"hpp_food_id": str}).set_index("hpp_food_id", verify_integrity=True)
    old = pd.read_csv(APPROVED / "independent_pilot_features.csv", dtype={"hpp_food_id": str}).set_index("hpp_food_id", verify_integrity=True)
    old = old.loc[matrix.index]
    pd.testing.assert_frame_equal(matrix[old.columns], old)
    dictionary = pd.read_csv(DENOVO / "feature_dictionary.csv")
    baseline = baseline.loc[matrix.index]
    shared = dictionary.loc[dictionary.feature_type.eq("nutrient_dose_estimate") & dictionary.display_name.isin(baseline.columns)]
    cells = []
    for row in shared.itertuples():
        for food_id in matrix.index:
            new, previous = float(matrix.loc[food_id, row.feature_name]), float(baseline.loc[food_id, row.display_name])
            cells.append({"hpp_food_id": food_id, "food_name": matrix.loc[food_id, "food_name"],
                          "feature_name": row.feature_name, "nutrient_name": row.display_name, "unit": row.unit,
                          "basis": "per_100g_as_declared_by_each_input", "pilot_value": new, "nutrimatch_value": previous,
                          "different": not np.isclose(new, previous, rtol=1e-9, atol=1e-12),
                          "both_recorded_zero": new == 0 and previous == 0})
    cells = pd.DataFrame(cells)
    cells.to_csv(out / "shared_nutrient_comparison.csv", index=False)
    per_food = cells.groupby(["hpp_food_id", "food_name"], sort=False).agg(
        compared_cells=("different", "size"), different_cells=("different", "sum"), both_recorded_zero=("both_recorded_zero", "sum"))
    per_food["same_cells"] = per_food.compared_cells - per_food.different_cells
    per_food.reset_index().to_csv(out / "five_food_comparison.csv", index=False)
    overlap = dictionary[["feature_name", "display_name", "feature_type", "change_from_approved_pilot"]].copy()
    overlap["comparison_with_153"] = np.where(overlap.feature_name.isin(shared.feature_name), "shared_nutrient_quantity",
        np.where(overlap.feature_type.eq("derived_compound_feature"), "algebraic_summary_not_new_measurement", "identity_information_not_new_nutrient"))
    overlap.to_csv(out / "feature_overlap.csv", index=False)
    summary = {"compared_foods": len(matrix), "shared_nutrient_columns": len(shared),
               "compared_cells": len(cells), "different_cells": int(cells.different.sum()),
               "same_cells": int((~cells.different).sum()), "both_recorded_zero": int(cells.both_recorded_zero.sum()),
               "approved_pilot_values_preserved": True,
               "comparison_note": "Post-build comparison only. Matching names and declared per-100g bases, not an independent unit or accuracy audit. Differences do not establish improvement.",
               "frozen_input_hashes": {"denovo": digest(DENOVO / "food_features.csv"),
                                       "nutrimatch_based": digest(BASELINE / "food_features.csv"),
                                       "approved_pilot": digest(APPROVED / "independent_pilot_features.csv")}}
    write_json("comparison_summary.json", summary, out)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
