"""Expand the approved five-food schema using only identity and public evidence.

No NutriMatch values or schemas enter the de novo build. Coverage gates are a
checkpoint policy, not scientific feature selection or learned rubric scores.
"""

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import independent_pilot as pilot


OUT = pilot.ROOT / "outputs_GEN2/step1c_expanded_schema/denovo"
DESCRIPTORS = Path(__file__).with_name("schema_expansion.json")
USDA_DOC = "https://www.ars.usda.gov/ARSUserFiles/80400525/Data/SR-Legacy/SR-Legacy_Doc.pdf"
ALIASES = {
    1062: {"canonical_id": 1008, "factor": 1 / 4.184,
           "reason": "Energy in kJ is the kcal quantity in different units, not a new predictor.",
           "source_url": "https://www.nist.gov/glossary-term/26261"},
    1110: {"canonical_id": 1114, "factor": 1 / 40,
           "reason": "Total vitamin D in IU is the same quantity as total D in micrograms.",
           "source_url": "https://ods.od.nih.gov/factsheets/VitaminD-HealthProfessional/"},
}
REPRESENTATIONS = {**ALIASES, 1104: {
    "canonical_id": 1106, "factor": None,
    "reason": "Vitamin A IU is an alternate activity convention. Keep source evidence but use RAE and constituent carotenoids in the panel; do not use a universal IU-to-RAE factor.",
    "source_url": "https://ods.od.nih.gov/factsheets/VitaminA-HealthProfessional/",
}}
EXCLUDED_STATUSES = {"unit_alias", "alternate_activity_convention"}


def read_source():
    with zipfile.ZipFile(pilot.USDA) as archive:
        def read(name):
            members = [n for n in archive.namelist() if n.endswith(f"/{name}.csv")]
            if len(members) != 1:
                raise ValueError(f"Ambiguous source member: {name}")
            return pd.read_csv(archive.open(members[0]))
        return read("nutrient").set_index("id"), read("food_nutrient")


def select_catalog(nutrients, amounts, foods):
    if amounts.duplicated(["fdc_id", "nutrient_id"]).any():
        raise ValueError("Duplicate source nutrient rows.")
    records = amounts.set_index(["fdc_id", "nutrient_id"])

    def present(donor, nutrient_id):
        key = (donor, nutrient_id)
        return (key in records.index and np.isfinite(records.loc[key, "amount"])
                and records.loc[key, "amount"] >= 0)

    rows, cells = [], []
    for nutrient_id in sorted(amounts.nutrient_id.unique()):
        direct = available = 0
        for food in foods:
            primary = food["primary_fdc_id"]
            donor = primary
            primary_value = present(primary, nutrient_id)
            method = "primary_donor_transfer" if primary_value else "unresolved"
            factor = 1.0
            if not primary_value and nutrient_id in pilot.AA_IDS:
                proxy = food.get("amino_acid_proxy_fdc_id")
                if (proxy is not None and present(proxy, nutrient_id)
                        and present(primary, 1003) and present(proxy, 1003)
                        and records.loc[(proxy, 1003), "amount"] > 0):
                    donor = proxy
                    factor = records.loc[(primary, 1003), "amount"] / records.loc[(proxy, 1003), "amount"]
                    method = "protein_scaled_brewed_coffee_proxy"
            resolved = method != "unresolved"
            direct += int(primary_value)
            available += int(resolved)
            record = records.loc[(donor, nutrient_id)] if resolved else None
            cells.append({
                "hpp_food_id": food["hpp_food_id"], "usda_nutrient_id": int(nutrient_id),
                "name": nutrients.loc[nutrient_id, "name"], "unit": nutrients.loc[nutrient_id, "unit_name"],
                "basis": "per_100g_edible_food", "value": float(record.amount * factor) if resolved else None,
                "method": method, "donor_fdc_id": donor if resolved else None,
                "source_food_nutrient_row_id": int(record.id) if resolved else None,
                "source_value": float(record.amount) if resolved else None, "scale_factor": factor if resolved else None,
                "source_url": f"https://fdc.nal.usda.gov/food-details/{donor}/nutrients" if resolved else "",
                "recorded_source_zero": bool(record.amount == 0) if resolved else None,
                "next_action": "" if resolved else "Review independent secondary donors or an explicit validated imputation method; do not zero-fill.",
            })
        if nutrient_id in ALIASES:
            status, reason = "unit_alias", ALIASES[nutrient_id]["reason"]
        elif nutrient_id in REPRESENTATIONS:
            status, reason = "alternate_activity_convention", REPRESENTATIONS[nutrient_id]["reason"]
        elif nutrient_id == 1408:
            status, reason = "source_label_review", "Source label PUFA 2:4 n-6 is ambiguous; verify identity before using or renaming."
        elif available == len(foods):
            status = "included"
            reason = "All five have primary-source values." if direct == len(foods) else "Complete using the previously reviewed amino-acid proxy; proxy remains unvalidated."
        else:
            status, reason = "completion_pending", "Some panel foods need independent donor review or supported imputation."
        source = amounts.loc[amounts.nutrient_id.eq(nutrient_id), "amount"]
        rows.append({
            "usda_nutrient_id": int(nutrient_id), "name": nutrients.loc[nutrient_id, "name"],
            "unit": nutrients.loc[nutrient_id, "unit_name"], "basis": "per_100g_edible_food",
            "source_foods_with_value": int((np.isfinite(source) & source.ge(0)).sum()),
            "panel_primary_values": direct, "panel_values_with_reviewed_proxy": available,
            "panel_foods": len(foods), "status": status, "reason": reason,
            "canonical_nutrient_id": REPRESENTATIONS.get(nutrient_id, {}).get("canonical_id", int(nutrient_id)),
            "alias_to_canonical_factor": REPRESENTATIONS.get(nutrient_id, {}).get("factor", 1.0),
            "definition_source_url": REPRESENTATIONS.get(nutrient_id, {}).get("source_url", USDA_DOC),
        })
    return pd.DataFrame(rows), pd.DataFrame(cells)


def descriptor_frames(identities, config):
    features = config["features"]
    names = [f["feature_name"] for f in features]
    if len(set(names)) != len(names):
        raise ValueError("Duplicate descriptor feature names.")
    source = identities.set_index("hpp_food_id", verify_integrity=True)
    data, provenance = [], []
    seen = set()
    for food in config["foods"]:
        food_id = food["hpp_food_id"]
        if food_id in seen or source.loc[food_id, "product_name"] != food["expected_product_name"]:
            raise ValueError("Duplicate or changed descriptor food identity.")
        seen.add(food_id)
        row = {"hpp_food_id": food_id}
        for spec in features:
            name = spec["feature_name"]
            value = food[name]
            if value not in spec["allowed_values"]:
                raise ValueError(f"Undeclared descriptor category: {name}/{value}")
            known = value != config["unknown_category"]
            row[name] = value
            provenance.append({
                "hpp_food_id": food_id, "feature_name": name, "value": value,
                "unit": "category", "basis": "food_identity_not_dose",
                "method": "original_identity_interpretation" if known else "identity_not_stated",
                "known_value": known, "source_field": "product_name",
                "source_text": source.loc[food_id, "product_name"],
                "source_file": str(pilot.HPP.relative_to(pilot.ROOT)),
                "upstream_proxy_used": False, "uncertainty": spec["definition"],
                "mapping_status": "assistant_reviewed_identity_not_externally_validated",
            })
        data.append(row)
    dictionary = pd.DataFrame([{
        "feature_name": spec["feature_name"], "display_name": spec["display_name"],
        "feature_type": "identity_descriptor", "unit": "category", "basis": "food_identity_not_dose",
        "formula": "Assistant interpretation of the original food description.",
        "interpretation": spec["definition"], "allowed_values": json.dumps(spec["allowed_values"]),
        "unknown_value": config["unknown_category"], "inclusion_reason": "Preserve food-identity detail without treating a donor assumption as observed target information.",
    } for spec in features])
    return pd.DataFrame(data), pd.DataFrame(provenance), dictionary


def build_denovo(out=OUT):
    out.mkdir(parents=True, exist_ok=True)
    config = json.loads(pilot.CONFIG.read_text())
    descriptors = json.loads(DESCRIPTORS.read_text())
    nutrients, amounts = read_source()
    registry, evidence = select_catalog(nutrients, amounts, config["foods"])
    selected = registry.loc[registry.status.eq("included"), "usda_nutrient_id"].tolist()
    previous_ids = set(config["nutrient_ids"])
    if not previous_ids.issubset(selected):
        raise ValueError("The new coverage policy unexpectedly removes approved nutrients.")
    config["nutrient_ids"] = selected
    config["schema_note"] = "All source IDs assessed. Include every distinct nutrient complete across the five reviewed foods using primary evidence or the previously approved amino-acid proxy. No fixed nutrient count; uncompleted candidates remain explicit."
    pilot.write_json("resolved_pilot_config.json", config, out)
    pilot.main(out / "resolved_pilot_config.json", out, "food_features.csv")
    matrix = pd.read_csv(out / "food_features.csv", dtype={"hpp_food_id": str})
    dictionary = pd.read_csv(out / "feature_dictionary.csv")
    prov = pd.read_csv(out / "cell_provenance.csv", dtype={"hpp_food_id": str})
    prov["known_value"] = True
    identity = pilot.read_identity(pilot.HPP)
    attrs, attr_prov, attr_dict = descriptor_frames(identity, descriptors)
    if set(attrs.hpp_food_id) != set(matrix.hpp_food_id):
        raise ValueError("Descriptor panel differs from the nutrient panel.")
    matrix = matrix.merge(attrs, on="hpp_food_id", validate="one_to_one")
    reason = registry.set_index("usda_nutrient_id").reason
    dictionary["inclusion_reason"] = dictionary.usda_nutrient_id.map(reason).fillna("Previously reviewed exploratory formula; not a validated outcome predictor.")
    dictionary = pd.concat([dictionary, attr_dict], ignore_index=True)
    prov = pd.concat([prov, attr_prov], ignore_index=True)
    dictionary["change_from_approved_pilot"] = [
        "added_identity_descriptor" if row.feature_type == "identity_descriptor" else
        "retained" if pd.isna(row.usda_nutrient_id) or int(row.usda_nutrient_id) in previous_ids else
        "added_nutrient" for row in dictionary.itertuples()
    ]
    numeric_names = dictionary.loc[dictionary.feature_type.ne("identity_descriptor"), "feature_name"].tolist()
    if not np.isfinite(matrix[numeric_names].to_numpy(dtype=float)).all():
        raise ValueError("Incomplete numeric panel.")
    if dictionary.feature_name.duplicated().any() or prov.duplicated(["hpp_food_id", "feature_name"]).any():
        raise ValueError("Duplicate features or cell provenance.")
    if len(prov) != len(matrix) * len(dictionary):
        raise ValueError("Incomplete cell provenance.")
    matrix.to_csv(out / "food_features.csv", index=False)
    dictionary.to_csv(out / "feature_dictionary.csv", index=False)
    prov.to_csv(out / "cell_provenance.csv", index=False)
    registry.to_csv(out / "nutrient_registry.csv", index=False)
    evidence.to_csv(out / "candidate_evidence_long.csv", index=False)
    dictionary.loc[dictionary.change_from_approved_pilot.ne("retained")].to_csv(out / "new_columns.csv", index=False)
    registry.loc[~registry.status.isin(EXCLUDED_STATUSES | {"included"})].to_csv(out / "pending_nutrients.csv", index=False)
    registry.loc[registry.status.eq("unit_alias")].to_csv(out / "unit_aliases.csv", index=False)
    registry.loc[registry.status.isin(EXCLUDED_STATUSES)].to_csv(out / "alternate_representations.csv", index=False)
    coverage = prov.groupby("feature_name").agg(populated_cells=("value", "count"), known_cells=("known_value", "sum"))
    coverage = dictionary[["feature_name", "display_name", "feature_type", "change_from_approved_pilot"]].merge(coverage, on="feature_name", validate="one_to_one")
    coverage["panel_foods"] = len(matrix)
    coverage["recorded_zero_cells"] = coverage.feature_name.map(prov.loc[prov.value.eq(0)].groupby("feature_name").size()).fillna(0).astype(int)
    coverage.to_csv(out / "feature_coverage.csv", index=False)
    summary = json.loads((out / "summary.json").read_text())
    summary.update({
        "status": "expanded_five_food_checkpoint_not_full_denovo_table",
        "feature_columns": len(dictionary), "identity_descriptor_columns": len(attr_dict),
        "numeric_feature_columns": len(numeric_names), "filled_numeric_cells": len(matrix) * len(numeric_names),
        "filled_feature_cells": int(matrix[dictionary.feature_name].notna().sum().sum()),
        "known_descriptor_cells": int(attr_prov.known_value.sum()),
        "unknown_descriptor_cells": int((~attr_prov.known_value).sum()),
        "cell_methods": prov.method.value_counts().to_dict(),
        "added_nutrient_columns": len(set(selected) - previous_ids),
        "added_identity_columns": len(attr_dict), "dropped_feature_columns": 0, "renamed_feature_columns": 0,
        "newly_imputed_numeric_cells": 0, "unit_alias_columns_not_double_counted": len(ALIASES),
        "alternate_activity_conventions_not_added": len(REPRESENTATIONS) - len(ALIASES),
        "nutrient_registry_status_counts": registry.status.value_counts().to_dict(),
        "canonical_nutrient_candidates": int((~registry.status.isin(EXCLUDED_STATUSES)).sum()),
        "pending_distinct_nutrients": int((~registry.status.isin(EXCLUDED_STATUSES | {"included"})).sum()),
        "pending_nutrient_cells_without_value": int(evidence.loc[~evidence.usda_nutrient_id.isin(REPRESENTATIONS), "value"].isna().sum()),
        "completeness_scope": "Numeric completeness applies only to the included five-food panel. Unknown descriptor categories and unresolved nutrient candidates are reported separately. Not the full food population or final feature schema.",
        "selection_policy": config["schema_note"],
    })
    pilot.write_json("summary.json", summary, out)
    manifest = json.loads((out / "run_manifest.json").read_text())
    manifest.update({
        "expanded_at_utc": datetime.now(timezone.utc).isoformat(),
        "expansion_code_sha256": pilot.digest(Path(__file__)), "descriptor_config_sha256": pilot.digest(DESCRIPTORS),
        "approved_mapping_config_sha256": pilot.digest(pilot.CONFIG),
        "output_hashes": {p.name: pilot.digest(p) for p in sorted(out.glob("*.csv"))},
        "nutrimatch_values_or_schema_used": False,
    })
    pilot.write_json("run_manifest.json", manifest, out)
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    build_denovo()
