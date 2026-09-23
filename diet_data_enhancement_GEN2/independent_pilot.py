"""Build a source-backed five-food prototype without any Gen1 nutrient inputs.

This replays explicitly reviewed source choices. It is not embedding retrieval.
"""

import hashlib
import json
import platform
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs_GEN2/step1b_independent_pilot"
CONFIG = Path(__file__).with_name("independent_pilot.json")
HPP = ROOT / "data/HPP/hpp_food_items_with_nutrients.csv"
USDA = ROOT / "data/USDA_SR_Legacy/FoodData_Central_sr_legacy_food_csv_2018-04.zip"
IDENTITY_COLUMNS = ["food_id", "product_name", "hebrew_name", "short_name"]
AA_IDS = set(range(1210, 1228))
SUM_RECIPES = {
    "essential_amino_acids_g_per_100g": [1210, 1211, 1212, 1213, 1214, 1215, 1217, 1219, 1221],
    "branched_chain_amino_acids_g_per_100g": [1212, 1213, 1219],
    "aromatic_amino_acids_g_per_100g": [1210, 1217, 1218],
    "sulfur_amino_acids_g_per_100g": [1215, 1216],
    "epa_dha_dpa_g_per_100g": [1272, 1278, 1280],
    "unsaturated_fatty_acids_g_per_100g": [1292, 1293],
}


def read_identity(path):
    # Column selection occurs at read time; HPP nutrient values never enter the frame.
    frame = pd.read_csv(path, usecols=IDENTITY_COLUMNS, dtype={"food_id": str})
    if frame.food_id.isna().any() or frame.food_id.duplicated().any():
        raise ValueError("Food IDs must be present and unique.")
    return frame.rename(columns={"food_id": "hpp_food_id"})


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def write_json(name, value, out=OUT):
    (out / name).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def main(config_path=CONFIG, out=OUT, matrix_filename="independent_pilot_features.csv"):
    config = json.loads(config_path.read_text())
    out.mkdir(parents=True, exist_ok=True)
    identities = read_identity(HPP)
    identities.to_csv(out / "all_foods_identity_only.csv", index=False)
    with zipfile.ZipFile(USDA) as archive:
        def read_member(name):
            matches = [p for p in archive.namelist() if p.endswith(f"/{name}.csv")]
            if len(matches) != 1:
                raise ValueError(f"Ambiguous source member {name}")
            with archive.open(matches[0]) as handle:
                return pd.read_csv(handle)
        food = read_member("food").set_index("fdc_id")
        nutrient = read_member("nutrient").set_index("id")
        amounts = read_member("food_nutrient")
        derivations = read_member("food_nutrient_derivation")

    if amounts.duplicated(["fdc_id", "nutrient_id"]).any():
        raise ValueError("Duplicate source nutrient rows require explicit adjudication.")
    records = amounts.set_index(["fdc_id", "nutrient_id"])
    selected_ids = config["nutrient_ids"]
    if len(selected_ids) != len(set(selected_ids)):
        raise ValueError("Duplicate nutrient identities in schema.")
    used_ids = sorted(amounts.nutrient_id.unique())
    catalog = nutrient.loc[used_ids].reset_index().rename(columns={"id": "usda_nutrient_id"})
    units = {"G": "g", "MG": "mg", "UG": "ug", "KCAL": "kcal", "kJ": "kj", "IU": "iu"}
    names = {i: f"usda_{i}_{units[nutrient.loc[i, 'unit_name']]}_per_100g" for i in used_ids}
    catalog["feature_name"] = catalog.usda_nutrient_id.map(names)
    catalog["selected_for_pilot"] = catalog.usda_nutrient_id.isin(selected_ids)
    catalog["status"] = np.where(catalog.selected_for_pilot, "pilot_nutrient", "candidate_not_completed_in_this_pilot")
    catalog["source_foods_with_value"] = catalog.usda_nutrient_id.map(amounts.groupby("nutrient_id").amount.count())
    catalog.to_csv(out / "public_nutrient_catalog.csv", index=False)
    derivations.to_csv(out / "source_derivation_dictionary.csv", index=False)

    features, provenance, evidence, mapping, dictionary = [], [], [], [], []
    for nutrient_id in selected_ids:
        dictionary.append({
            "feature_name": names[nutrient_id], "feature_type": "nutrient_dose_estimate",
            "display_name": nutrient.loc[nutrient_id, "name"],
            "unit": units[nutrient.loc[nutrient_id, "unit_name"]], "basis": "per_100g_edible_food",
            "usda_nutrient_id": nutrient_id, "formula": "source amount or documented proxy estimate",
            "recipe_dependencies": "", "interpretation": "Estimated target-food composition, not a target-food laboratory measurement.",
        })

    for spec in config["foods"]:
        target = identities.set_index("hpp_food_id").loc[spec["hpp_food_id"]]
        if target.product_name != spec["expected_product_name"]:
            raise ValueError("Pinned food identity changed.")
        primary = spec["primary_fdc_id"]
        if food.loc[primary, "description"] != spec["expected_donor_name"]:
            raise ValueError("Pinned donor identity changed.")
        values, evidence_keys = {}, {}
        feature_row = {"hpp_food_id": spec["hpp_food_id"], "food_name": target.product_name}
        for nutrient_id in used_ids:
            if (primary, nutrient_id) in records.index:
                source_row = records.loc[(primary, nutrient_id)]
                evidence.append({"hpp_food_id": spec["hpp_food_id"], "donor_fdc_id": primary,
                                 "usda_nutrient_id": nutrient_id, "value": source_row.amount,
                                 "unit": nutrient.loc[nutrient_id, "unit_name"],
                                 "source_food_nutrient_row_id": source_row.id})
        for nutrient_id in selected_ids:
            donor, method, factor = primary, "primary_donor_transfer", 1.0
            extra_dependencies = []
            key = (donor, nutrient_id)
            if key not in records.index or pd.isna(records.loc[key, "amount"]):
                proxy = spec.get("amino_acid_proxy_fdc_id")
                if nutrient_id not in AA_IDS or proxy is None:
                    raise ValueError(f"Unresolved value: {spec['hpp_food_id']}/{nutrient_id}; do not silently zero-fill.")
                donor = proxy
                target_protein = records.loc[(primary, 1003), "amount"]
                donor_protein = records.loc[(donor, 1003), "amount"]
                if not np.isfinite(donor_protein) or donor_protein <= 0:
                    raise ValueError("Amino-acid proxy needs a positive protein denominator.")
                factor = float(target_protein / donor_protein)
                method = "protein_scaled_brewed_coffee_proxy"
                extra_dependencies = [int(records.loc[(primary, 1003), "id"]), int(records.loc[(donor, 1003), "id"])]
                key = (donor, nutrient_id)
            record = records.loc[key]
            value = float(record.amount * factor)
            if not np.isfinite(value) or value < 0:
                raise ValueError("Invalid nutrient value.")
            values[nutrient_id] = value
            feature_row[names[nutrient_id]] = value
            evidence_keys[nutrient_id] = [int(record.id)] + extra_dependencies
            provenance.append({
                "hpp_food_id": spec["hpp_food_id"], "feature_name": names[nutrient_id], "value": value,
                "unit": units[nutrient.loc[nutrient_id, "unit_name"]], "basis": "per_100g_edible_food",
                "method": method, "donor_fdc_id": donor, "donor_description": food.loc[donor, "description"],
                "source_url": f"https://fdc.nal.usda.gov/food-details/{donor}/nutrients",
                "source_food_nutrient_row_ids": json.dumps(evidence_keys[nutrient_id]),
                "source_derivation_id": None if pd.isna(record.derivation_id) else int(record.derivation_id),
                "source_data_points": None if pd.isna(record.data_points) else int(record.data_points),
                "source_value": float(record.amount), "scale_factor": factor,
                "recipe_dependencies": "", "upstream_proxy_used": method != "primary_donor_transfer",
                "uncertainty": spec.get("amino_acid_proxy_reason") if method != "primary_donor_transfer" else spec["uncertainty"],
                "recorded_source_zero": bool(record.amount == 0),
                "mapping_status": config["status"],
            })

        recipes = dict(SUM_RECIPES)
        recipes["sodium_to_potassium_mass_ratio"] = [1093, 1092]
        recipes["unsaturated_to_saturated_fat_ratio"] = [1292, 1293, 1258]
        for name, deps in recipes.items():
            if name in SUM_RECIPES:
                value = sum(values[i] for i in deps)
                formula, unit = " + ".join(names[i] for i in deps), "g"
            else:
                numerator = sum(values[i] for i in deps[:-1])
                denominator = values[deps[-1]]
                if denominator <= 0:
                    raise ValueError(f"Undefined ratio {name}; a full-dataset recipe needs an explicit zero-denominator policy.")
                value = numerator / denominator
                formula = "(" + " + ".join(names[i] for i in deps[:-1]) + ") / " + names[deps[-1]]
                unit = "dimensionless"
            feature_row[name] = value
            uses_proxy = bool(spec.get("amino_acid_proxy_fdc_id")) and bool(set(deps) & AA_IDS)
            provenance.append({
                "hpp_food_id": spec["hpp_food_id"], "feature_name": name, "value": value,
                "unit": unit, "basis": "per_100g_edible_food" if unit == "g" else "ratio",
                "method": "derived_recipe", "recipe_dependencies": json.dumps([names[i] for i in deps]),
                "source_food_nutrient_row_ids": json.dumps(sorted({k for i in deps for k in evidence_keys[i]})),
                "upstream_proxy_used": uses_proxy, "mapping_status": config["status"],
                "uncertainty": "Inherits donor and proxy uncertainty; algebraic feature, not a validated disease effect.",
            })
            if not any(row["feature_name"] == name for row in dictionary):
                dictionary.append({"feature_name": name, "feature_type": "derived_compound_feature",
                                   "display_name": name.replace("_", " "), "unit": unit,
                                   "basis": "per_100g_edible_food" if unit == "g" else "ratio",
                                   "formula": formula, "recipe_dependencies": json.dumps([names[i] for i in deps]),
                                   "interpretation": "Candidate predictor; no clinical or mechanistic effect is asserted."})
        mapping.append({**spec, "status": config["status"], "nutrient_columns": len(selected_ids),
                        "derived_columns": len(recipes), "nutrient_proxy_cells": sum(
                            p["hpp_food_id"] == spec["hpp_food_id"] and p["method"] == "protein_scaled_brewed_coffee_proxy"
                            for p in provenance)})
        features.append(feature_row)

    matrix = pd.DataFrame(features)
    feature_cols = [d["feature_name"] for d in dictionary]
    if len(set(feature_cols)) != len(feature_cols) or matrix[feature_cols].isna().any().any():
        raise ValueError("Duplicate or incomplete pilot feature columns.")
    prov = pd.DataFrame(provenance)
    if len(prov) != len(matrix) * len(feature_cols) or prov.duplicated(["hpp_food_id", "feature_name"]).any():
        raise ValueError("Incomplete or duplicated cell provenance.")
    matrix.to_csv(out / matrix_filename, index=False)
    prov.to_csv(out / "cell_provenance.csv", index=False)
    pd.DataFrame(dictionary).to_csv(out / "feature_dictionary.csv", index=False)
    pd.DataFrame(evidence).to_csv(out / "primary_donor_evidence_long.csv", index=False)
    pd.DataFrame(mapping).to_csv(out / "reviewed_donor_decisions.csv", index=False)
    summary = {
        "status": config["status"], "food_rows": len(matrix), "identity_rows_prepared": len(identities),
        "nutrient_columns": len(selected_ids), "derived_columns": len(SUM_RECIPES) + 2,
        "feature_columns": len(feature_cols), "identity_columns": 2,
        "filled_feature_cells": int(matrix[feature_cols].notna().sum().sum()),
        "missing_feature_cells": int(matrix[feature_cols].isna().sum().sum()),
        "cell_methods": prov.method.value_counts().to_dict(),
        "derived_cells_with_proxy_dependency": int((prov.method.eq("derived_recipe") & prov.upstream_proxy_used).sum()),
        "public_source_nutrient_candidates": len(used_ids),
        "public_candidates_outside_pilot": len(used_ids) - len(selected_ids),
        "hpp_nutrient_columns_read": 0, "old_generated_names_read": 0,
        "nutrimatch_or_gen1_output_files_read": 0, "embedding_calls": 0, "adjudication_api_calls": 0,
        "completeness_scope": "Only the declared five-food prototype schema. This is not completion of all 7405 foods or the full candidate nutrient catalog.",
        "validation_note": "Source traceability and numeric completeness checked; mapping and proxy accuracy not empirically validated.",
    }
    write_json("summary.json", summary, out)
    write_json("run_manifest.json", {
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "python": platform.python_version(),
        "pandas": pd.__version__, "numpy": np.__version__,
        "code_sha256": digest(Path(__file__)), "config_sha256": digest(config_path),
        "identity_input": {"path": str(HPP.relative_to(ROOT)), "allowed_columns": IDENTITY_COLUMNS,
                           "identity_values_sha256": hashlib.sha256(identities.to_csv(index=False).encode()).hexdigest()},
        "nutrient_input": {"path": str(USDA.relative_to(ROOT)), "sha256": digest(USDA),
                           "publication_dates": sorted(food.publication_date.dropna().unique().tolist())},
        "output_hashes": {p.name: digest(p) for p in sorted(out.glob("*.csv"))},
        "external_api_model": None, "embedding_model": None,
    }, out)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
