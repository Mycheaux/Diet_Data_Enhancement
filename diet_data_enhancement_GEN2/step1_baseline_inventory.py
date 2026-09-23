"""Audit Gen1 snapshots without changing values or importing the Gen1 pipeline.

Run from the repository root:
    python -m diet_data_enhancement_GEN2.step1_baseline_inventory
"""

import hashlib
import json
import platform
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs_GEN2/step1_baseline_inventory"
PACKAGE = ROOT / "diet_data_enhancement_GEN2"
SCENARIOS = {"denovo": "1.denovo", "nutrimatch_based": "2.nutrimatch_based"}
RECIPES = ["broad_diet_health", "cardiometabolic", "chemical_metabolomics", "mental_health", "microbiome"]
HPP_METADATA = {
    "hpp_food_id", "short_description", "category_hint", "product_name",
    "short_name", "hebrew_name", "gpt_short_food_name", "number_loggings",
}


def file_record(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return {"path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size,
            "sha256": digest.hexdigest()}


def save_csv(frame, name):
    frame.to_csv(OUT / name, index=False)


def save_json(payload, name):
    (OUT / name).write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")


def profile(table_id, frame, metadata, source_path):
    rows = []
    for column in frame:
        series = frame[column]
        numeric = pd.api.types.is_numeric_dtype(series)
        present = int(series.notna().sum())
        zero = int(series.eq(0).sum()) if numeric else None
        values = series.dropna()
        info = metadata.get(column, {})
        rows.append({
            "table_id": table_id, "source_path": source_path,
            "column_name": column, "feature_family": info.get("feature_group", "unclassified"),
            "model_role": info.get("model_role", "not_declared"),
            "mapping_origin": info.get("mapping_origin", "not_declared"),
            "per_100g_scalable_declared": info.get("per_100g_scalable", "not_declared"),
            "unit_status": "not_validated_in_this_audit",
            "dtype": str(series.dtype), "row_count": len(frame),
            "present_count": present, "missing_count": len(frame) - present,
            "missing_fraction": 1 - present / len(frame),
            "zero_count": zero,
            "zero_fraction_of_present": zero / present if numeric and present else None,
            "nonzero_count": present - zero if numeric else None,
            "distinct_present_values": int(series.nunique()),
            "numeric_min": float(values.min()) if numeric and present else None,
            "numeric_median": float(values.median()) if numeric and present else None,
            "numeric_max": float(values.max()) if numeric and present else None,
        })
    return pd.DataFrame(rows)


def compare_columns(left, right):
    if set(left.index) != set(right.index):
        raise ValueError("Baseline food-ID sets differ; compare only after resolving this mismatch.")
    right = right.reindex(left.index)
    rows = []
    for column in left.columns.intersection(right.columns):
        a, b = left[column], right[column]
        paired = a.notna() & b.notna()
        equal = a.eq(b) | (a.isna() & b.isna())
        numeric = pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b)
        rows.append({
            "column_name": column, "compared_rows": len(left),
            "exact_equal_including_missing": bool(equal.all()),
            "different_cell_count": int((~equal).sum()),
            "paired_present_count": int(paired.sum()),
            "both_missing_count": int((a.isna() & b.isna()).sum()),
            "max_abs_difference": float((a[paired] - b[paired]).abs().max()) if numeric and paired.any() else None,
        })
    return pd.DataFrame(rows)


def normalized_name(value):
    return re.sub(r"\s+", " ", value.casefold().replace("_", " ")).strip()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    inputs, checks, profiles, inventory = {}, {}, [], []

    def track(path):
        record = file_record(path)
        inputs[record["path"]] = record
        return path

    def read(relative, **kwargs):
        return pd.read_csv(track(ROOT / relative), **kwargs)

    panel_config = PACKAGE / "five_food_panel.json"
    panel = pd.DataFrame(json.loads(track(panel_config).read_text()))
    ids = panel.hpp_food_id.tolist()
    if len(ids) != 5 or len(set(ids)) != 5:
        raise ValueError("The checkpoint requires five distinct, pinned HPP IDs.")

    def inventory_table(table_id, path, metadata, raw_hpp=False):
        key = "food_id" if raw_hpp else "hpp_food_id"
        frame = read(path, dtype={key: str}, low_memory=False).rename(columns={key: "hpp_food_id"})
        if frame.empty or frame.hpp_food_id.isna().any() or frame.hpp_food_id.duplicated().any():
            raise ValueError(f"Empty table or invalid food IDs: {path}")
        if not set(ids).issubset(frame.hpp_food_id):
            raise ValueError(f"Missing panel food in {path}")
        if set(metadata) != set(frame.columns):
            raise ValueError(f"Schema columns differ from table columns: {path}")
        column_profile = profile(table_id, frame, metadata, path)
        profiles.append(column_profile)
        feature_columns = [c for c in frame if metadata[c].get("feature_group") != "identity"]
        features = frame[feature_columns]
        numeric = features.select_dtypes(include="number")
        present_numeric = int(numeric.notna().sum().sum())
        inventory.append({
            "table_id": table_id, "source_path": path,
            "rows_before": len(frame), "columns_before": len(frame.columns),
            "rows_after": len(frame), "columns_after": len(frame.columns),
            "columns_added": 0, "columns_dropped": 0, "columns_renamed": 0,
            "columns_imputed": 0, "unique_food_ids": frame.hpp_food_id.nunique(),
            "identity_columns": len(frame.columns) - len(feature_columns),
            "feature_columns": len(feature_columns), "numeric_feature_columns": len(numeric.columns),
            "feature_missing_fraction": float(features.isna().to_numpy().mean()),
            "numeric_zero_fraction_of_present": float(numeric.eq(0).sum().sum() / present_numeric) if present_numeric else None,
            "columns_over_80pct_missing": int(column_profile.missing_fraction.gt(0.8).sum()),
            "columns_all_missing": int(column_profile.present_count.eq(0).sum()),
        })
        checks[f"{table_id}_unique_ids_and_complete_schema"] = True
        return frame.set_index("hpp_food_id", drop=False)

    hpp_path = "data/HPP/hpp_food_items_with_nutrients.csv"
    hpp_columns = read(hpp_path, nrows=0).rename(columns={"food_id": "hpp_food_id"}).columns
    hpp_meta = {c: {"feature_group": "identity" if c in HPP_METADATA else "nutrient_per_100g"} for c in hpp_columns}
    hpp = inventory_table("hpp_input", hpp_path, hpp_meta, raw_hpp=True)
    panel = panel.merge(hpp.reset_index(drop=True)[[
        "hpp_food_id", "product_name", "short_description", "hebrew_name",
        "gpt_short_food_name", "category_hint", "number_loggings",
    ]], on="hpp_food_id", validate="one_to_one")
    if not panel.product_name.eq(panel.expected_product_name).all():
        raise ValueError("A pinned food name changed. Review the panel configuration.")
    save_csv(panel, "five_food_panel.csv")

    matrices, schemas, provenance_counts, selected_provenance = {}, {}, [], []
    for scenario, folder in SCENARIOS.items():
        base = f"outputs/enhanced_hpp/{folder}"
        schema = read(f"{base}/feature_schema.csv")
        schemas[scenario] = schema.set_index("feature_name").to_dict("index")
        matrix = inventory_table(scenario, f"{base}/hpp_feature_matrix_per_100g.csv", schemas[scenario])
        if set(matrix.index) != set(hpp.index):
            raise ValueError(f"Food-ID mismatch for {scenario}")
        matrices[scenario] = matrix
        prov_path = f"{base}/hpp_nutrient_provenance_long.csv.gz"
        prov = read(prov_path, dtype={"hpp_food_id": str})
        nutrient_cols = schema.loc[schema.feature_group.eq("nutrient_per_100g"), "feature_name"].tolist()
        if prov.duplicated(["hpp_food_id", "nutrient_name"]).any():
            raise ValueError(f"Duplicate provenance cells: {scenario}")
        if (len(prov) != len(matrix) * len(nutrient_cols)
                or set(prov.nutrient_name) != set(nutrient_cols)
                or set(prov.hpp_food_id) != set(matrix.index)):
            raise ValueError(f"Incomplete nutrient provenance: {scenario}")
        for column, group in prov.groupby("nutrient_name", sort=False):
            actual_missing = matrix.loc[group.hpp_food_id, column].isna().to_numpy()
            if not np.array_equal(actual_missing, group.nutrient_source.eq("missing").to_numpy()):
                raise ValueError(f"Value/provenance disagreement: {scenario}/{column}")
        checks[f"{scenario}_provenance_matches_all_nutrient_cells"] = True
        count = prov.groupby("nutrient_source").size().rename("cell_count").reset_index()
        count.insert(0, "table_id", scenario)
        count["fraction_of_all_nutrient_cells"] = count.cell_count / len(prov)
        count["fraction_of_present_nutrient_cells"] = np.where(
            count.nutrient_source.ne("missing"),
            count.cell_count / prov.nutrient_source.ne("missing").sum(), np.nan,
        )
        provenance_counts.append(count)
        selected = prov[prov.hpp_food_id.isin(ids)].copy()
        selected.insert(0, "table_id", scenario)
        selected["provenance_file"] = prov_path
        selected_provenance.append(selected)
        del prov
        for recipe in RECIPES:
            downstream = f"outputs/downstream_features/{scenario}/{recipe}"
            feature_list = read(f"{downstream}/hpp_downstream_feature_list.csv")
            meta = {r.feature_name: {
                "feature_group": "identity" if r.model_role == "identifier_or_descriptor" else r.feature_source,
                "model_role": r.model_role, "mapping_origin": r.feature_source,
            } for r in feature_list.itertuples()}
            table = inventory_table(f"{scenario}/{recipe}", f"{downstream}/hpp_downstream_feature_table.csv", meta)
            if set(table.index) != set(hpp.index):
                raise ValueError(f"Food-ID mismatch for {scenario}/{recipe}")
            del table

    denovo, nutrimatch = matrices["denovo"], matrices["nutrimatch_based"]
    comparison = compare_columns(denovo, nutrimatch)
    extra_names = denovo.columns.difference(nutrimatch.columns).tolist()
    all_profiles = pd.concat(profiles, ignore_index=True)
    extra = all_profiles[all_profiles.table_id.eq("denovo") & all_profiles.column_name.isin(extra_names)].copy()
    aliases = {normalized_name(c): c for c in nutrimatch.columns}
    extra["candidate_existing_alias"] = extra.column_name.map(lambda c: aliases.get(normalized_name(c), ""))
    extra["alias_status"] = np.where(extra.candidate_existing_alias.ne(""), "name_only_candidate_review_units_and_identity", "not_assessed_beyond_name_normalization")
    extra["added_in_this_step"] = False
    save_csv(extra, "denovo_extra_columns.csv")
    save_csv(comparison, "shared_column_comparison.csv")
    save_csv(all_profiles, "column_profiles.csv")
    save_csv(pd.DataFrame(inventory), "table_inventory.csv")
    save_csv(pd.concat(provenance_counts, ignore_index=True), "nutrient_provenance_summary.csv")
    five_prov = pd.concat(selected_provenance, ignore_index=True)
    save_csv(five_prov, "five_food_nutrient_provenance.csv")

    coverage_rows = []
    shared_nutrients = [c for c, m in schemas["nutrimatch_based"].items() if m["feature_group"] == "nutrient_per_100g"]
    for item in panel.itertuples():
        for scenario, matrix in matrices.items():
            for group, columns in [("shared_nutrients", shared_nutrients), ("denovo_extra_nutrients", extra_names if scenario == "denovo" else [])]:
                row = matrix.loc[item.hpp_food_id, columns]
                present, zeros = int(row.notna().sum()), int(row.eq(0).sum())
                coverage_rows.append({
                    "hpp_food_id": item.hpp_food_id, "panel_label": item.panel_label,
                    "table_id": scenario, "feature_group": group, "column_count": len(columns),
                    "present_count": present, "nonzero_count": present - zeros,
                    "zero_count": zeros, "missing_count": len(columns) - present,
                })
    save_csv(pd.DataFrame(coverage_rows), "five_food_coverage.csv")
    sample_cols = [
        "canonical_name", "Energy", "Protein", "Total lipid (fat)",
        "Carbohydrate, by difference", "Fiber, total dietary", "Sodium, Na",
        "Caffeine", "Leucine", "leucine", "palmitic", "iodine",
        "canonical_inherited__openfoodfacts_product_name",
        "canonical_inherited__openfoodfacts_confidence",
        "canonical_inherited__foodb_compound_count",
        "canonical_inherited__hmdb_pathway_count",
    ]
    preview = panel[["hpp_food_id", "panel_label", "product_name"]].merge(
        denovo.reset_index(drop=True)[["hpp_food_id"] + sample_cols], on="hpp_food_id", validate="one_to_one")
    save_csv(preview, "five_food_values.csv")
    for scenario, matrix in matrices.items():
        save_csv(matrix.loc[ids], f"five_food_{scenario}_all_columns.csv")

    # The harmonized snapshot retains the selected donor even if candidate files are absent.
    donor_path = "outputs/nutrients/hpp_nutrient_harmonized.csv"
    donor_cols = ["hpp_food_id", "source", "source_food_id", "matched_food_name",
                  "candidate_rank", "match_score", "confidence", "stage", "needs_human_review"]
    donors = read(donor_path, usecols=donor_cols, dtype={"hpp_food_id": str, "source_food_id": str})
    save_csv(panel[["hpp_food_id", "panel_label"]].merge(
        donors, on="hpp_food_id", how="left", validate="one_to_one"), "five_food_selected_donors.csv")
    for relative in ["diet_data_enhancement/hpp_scenarios.py", "diet_data_enhancement/nutrients.py"]:
        track(ROOT / relative)

    nutrient_counts = {s: sum(m["feature_group"] == "nutrient_per_100g" for m in schemas[s].values()) for s in SCENARIOS}
    summary = {
        "step": 1, "scope": "baseline_inventory_before_layer_1",
        "review_status": "awaiting_user_review", "food_count": len(hpp),
        "tables_audited": len(inventory),
        "new_modeling_columns": 0, "imputed_cells": 0, "llm_calls": 0, "llm_tokens": 0,
        "shared_columns_including_id": len(comparison),
        "identical_shared_columns_including_id": int(comparison.exact_equal_including_missing.sum()),
        "shared_nutrient_columns": len(shared_nutrients), "nutrient_columns": nutrient_counts,
        "denovo_extra_columns": len(extra), "nutrimatch_only_columns": nutrimatch.columns.difference(denovo.columns).tolist(),
        "extra_missing_fraction_min": float(extra.missing_fraction.min()),
        "extra_missing_fraction_median": float(extra.missing_fraction.median()),
        "extra_missing_fraction_max": float(extra.missing_fraction.max()),
        "extra_cell_missing_fraction": float(denovo[extra_names].isna().to_numpy().mean()),
        "extra_name_alias_candidates": int(extra.candidate_existing_alias.ne("").sum()),
        "original_candidate_file_available": (ROOT / "outputs/mapping/hpp_public_food_mappings.csv").exists(),
        "unit_note": "Per-100g basis is a Gen1 declaration; physical units are source-native and not revalidated here.",
        "zero_note": "Recorded zeros are counted separately from missing cells; they are not verified biological absences.",
        "alias_note": "Name-only candidates are not validated aliases; no merge, conversion or imputation was performed.",
        "provenance_note": "hpp_observed means present in the HPP input, not a verified laboratory observation.",
    }
    checks["five_panel_product_names_match_pinned_config"] = True
    checks["all_input_hashes_unchanged_after_audit"] = all(file_record(ROOT / p)["sha256"] == r["sha256"] for p, r in inputs.items())
    if not all(checks.values()):
        raise ValueError("An audit integrity check failed.")
    save_json(summary, "summary.json")
    save_json(checks, "validation.json")
    save_json({
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(), "python_executable": sys.executable,
        "pandas": pd.__version__, "numpy": np.__version__,
        "reproduction_command": "python -m diet_data_enhancement_GEN2.step1_baseline_inventory",
        "code": file_record(Path(__file__)), "inputs": list(inputs.values()),
        "definitions": {
            "missing": "pandas CSV missing-value parsing; recorded zero remains present",
            "comparison": "exact parsed values aligned by HPP food ID; missing equals missing; no numeric tolerance",
            "fractions": "unweighted across HPP food rows; logging frequency is not used",
            "schema": "Gen1 feature families retained as declarations, not reclassified or validated",
        },
        "outputs": [file_record(p) for p in sorted(OUT.glob("*.csv"))]
            + [file_record(OUT / n) for n in ["summary.json", "validation.json"]],
    }, "run_manifest.json")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
