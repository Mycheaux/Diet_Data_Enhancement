import json
import zipfile
from pathlib import Path

import pandas as pd

from .sources import ROOT


OUT = ROOT / "outputs/nutrients"
HPP_PATH = ROOT / "data/HPP/hpp_food_items_with_nutrients.csv"

HPP_META = {
    "food_id",
    "short_description",
    "category_hint",
    "product_name",
    "short_name",
    "hebrew_name",
    "gpt_short_food_name",
    "number_loggings",
}

TZAMERET_META = {
    "Code",
    "smlmitzrach",
    "shmmitzrach",
    "makor",
    "edible",
    "psolet",
    "ahuz_ibud_nozlim",
    "tarich_ptiha",
    "tarich_idkun",
    "english_name",
}

BAHRAIN_RENAME = {
    "Water (g)": "Water",
    "Protein (g)": "Protein",
    "Fat (g)": "Total lipid (fat)",
    "Dietary Fibre (g)": "Fiber, total dietary",
    "Total Available Carbohydrate (g)": "Carbohydrate, by difference",
    "Energy (kcal)": "Energy",
    "Calcium (mg)": "Calcium, Ca",
    "Phosphorus (mg)": "Phosphorus, P",
    "Iron (mg)": "Iron, Fe",
    "Thiamin / Vitamin B1 (mg)": "Thiamin",
    "Riboflavin / Vitamin B2 (mg)": "Riboflavin",
    "Niacin (mg)": "Niacin",
    "Vitamin C (mg)": "Vitamin C, total ascorbic acid",
}

TZAMERET_RENAME = {
    "protein": "Protein",
    "total_fat": "Total lipid (fat)",
    "carbohydrates": "Carbohydrate, by difference",
    "food_energy": "Energy",
    "alcohol": "Alcohol, ethyl",
    "moisture": "Water",
    "total_dietary_fiber": "Fiber, total dietary",
    "calcium": "Calcium, Ca",
    "iron": "Iron, Fe",
    "magnesium": "Magnesium, Mg",
    "phosphorus": "Phosphorus, P",
    "potassium": "Potassium, K",
    "sodium": "Sodium, Na",
    "zinc": "Zinc, Zn",
    "copper": "Copper, Cu",
    "vitamin_a_iu": "Vitamin A, IU",
    "carotene": "Carotene, beta",
    "vitamin_e": "Vitamin E (alpha-tocopherol)",
    "vitamin_c": "Vitamin C, total ascorbic acid",
    "thiamin": "Thiamin",
    "riboflavin": "Riboflavin",
    "niacin": "Niacin",
    "vitamin_b6": "Vitamin B-6",
    "folate": "Folate, total",
    "folate_dfe": "Folate, DFE",
    "vitamin_b12": "Vitamin B-12",
    "cholesterol": "Cholesterol",
    "saturated_fat": "Fatty acids, total saturated",
    "mono_unsaturated_fat": "Fatty acids, total monounsaturated",
    "poly_unsaturated_fat": "Fatty acids, total polyunsaturated",
    "vitamin_d": "Vitamin D (D2 + D3)",
    "total_sugars": "Sugars, Total",
    "trans_fatty_acids": "Fatty acids, total trans",
    "vitamin_k": "Vitamin K",
    "selenium": "Selenium, Se",
    "choline": "Choline, total",
    "manganese": "Manganese, Mn",
    "fructose": "Fructose",
}


def _numeric_frame(df, id_col, source, rename=None, drop_cols=None):
    rename = rename or {}
    drop_cols = set(drop_cols or [])
    rows = df.copy()
    rows[id_col] = rows[id_col].astype(str)
    nutrient_cols = [col for col in rows.columns if col not in drop_cols and col != id_col]
    out = rows[[id_col] + nutrient_cols].rename(columns={id_col: "source_food_id", **rename})
    out["source"] = source
    for col in out.columns:
        if col not in {"source", "source_food_id"}:
            out[col] = pd.to_numeric(out[col].replace("-", pd.NA), errors="coerce")
    return out


def load_hpp_nutrients():
    df = pd.read_csv(HPP_PATH)
    nutrient_cols = [col for col in df.columns if col not in HPP_META]
    out = df[["food_id"] + nutrient_cols].rename(columns={"food_id": "hpp_food_id"})
    return out


def load_tzameret_nutrients():
    df = pd.read_csv(ROOT / "data/Tzameret_Israel/moh_mitzrachim.csv")
    nutrient_cols = [col for col in df.columns if col not in TZAMERET_META]
    return _numeric_frame(
        df[["Code"] + nutrient_cols],
        "Code",
        "Tzameret_Israel",
        rename=TZAMERET_RENAME,
        drop_cols=TZAMERET_META,
    )


def load_bahrain_nutrients():
    df = pd.read_excel(ROOT / "data/Bahrain FCT/Bahrain_Food_Composition_Table_pdf_extracted.xlsx")
    nutrient_cols = [col for col in df.columns if col not in {"Item No.", "Food Category", "Food Name (English)"}]
    return _numeric_frame(
        df[["Item No."] + nutrient_cols],
        "Item No.",
        "Bahrain_FCT",
        rename=BAHRAIN_RENAME,
        drop_cols={"Food Category", "Food Name (English)"},
    )


def load_usda_nutrients(zip_path, folder, source):
    with zipfile.ZipFile(zip_path) as archive:
        with archive.open(f"{folder}/food_nutrient.csv") as handle:
            food_nutrient = pd.read_csv(handle)
        with archive.open(f"{folder}/nutrient.csv") as handle:
            nutrient = pd.read_csv(handle)
    merged = food_nutrient.merge(nutrient[["id", "name", "unit_name"]], left_on="nutrient_id", right_on="id")
    merged["nutrient_name"] = merged["name"]
    pivot = merged.pivot_table(
        index="fdc_id",
        columns="nutrient_name",
        values="amount",
        aggfunc="mean",
    ).reset_index()
    return _numeric_frame(pivot, "fdc_id", source)


def load_source_nutrients():
    frames = [
        load_tzameret_nutrients(),
        load_bahrain_nutrients(),
        load_usda_nutrients(
            ROOT / "data/USDA_SR_Legacy/FoodData_Central_sr_legacy_food_csv_2018-04.zip",
            "FoodData_Central_sr_legacy_food_csv_2018-04",
            "USDA_SR_Legacy",
        ),
        load_usda_nutrients(
            ROOT / "data/USDA_FNDDS/FoodData_Central_survey_food_csv_2024-10-31.zip",
            "FoodData_Central_survey_food_csv_2024-10-31",
            "USDA_FNDDS",
        ),
    ]
    combined = pd.concat(frames, ignore_index=True, sort=False)
    nutrient_cols = [col for col in combined.columns if col not in {"source", "source_food_id"}]
    return (
        combined.groupby(["source", "source_food_id"], as_index=False)[nutrient_cols]
        .mean(numeric_only=True)
    )


def best_available_mapping():
    mappings = pd.read_csv(ROOT / "outputs/mapping/hpp_public_food_mappings.csv")
    best = mappings.sort_values(["hpp_food_id", "candidate_rank"]).groupby("hpp_food_id").head(1).copy()
    corrections_path = ROOT / "outputs/mapping/human_corrections.csv"
    if corrections_path.exists():
        corrections = pd.read_csv(corrections_path)
        if not corrections.empty:
            correction_rows = corrections.rename(
                columns={
                    "remap_source": "source",
                    "remap_source_food_id": "source_food_id",
                    "remap_food_name": "matched_food_name",
                    "remap_score": "match_score",
                    "remap_confidence": "confidence",
                }
            )
            correction_rows["candidate_rank"] = 0
            correction_rows["stage"] = "human_review_remap"
            correction_rows["needs_human_review"] = False
            keep = [
                "hpp_food_id",
                "source",
                "source_food_id",
                "matched_food_name",
                "match_score",
                "confidence",
                "candidate_rank",
                "stage",
                "needs_human_review",
            ]
            best = best[~best["hpp_food_id"].isin(correction_rows["hpp_food_id"])]
            best = pd.concat([best, correction_rows[keep]], ignore_index=True, sort=False)
    best["source_food_id"] = best["source_food_id"].astype(str).str.replace(r"\.0$", "", regex=True)
    return best


def harmonize_nutrients(min_confidence=("high", "medium", "review")):
    OUT.mkdir(parents=True, exist_ok=True)
    hpp = load_hpp_nutrients()
    source_nutrients = load_source_nutrients()
    mapping = best_available_mapping()
    mapping = mapping[mapping["confidence"].isin(min_confidence)].copy()
    source_nutrients["source_food_id"] = source_nutrients["source_food_id"].astype(str).str.replace(r"\.0$", "", regex=True)

    joined = mapping.merge(source_nutrients, on=["source", "source_food_id"], how="left", suffixes=("", "_source"))
    hpp = hpp.rename(columns={col: f"hpp__{col}" for col in hpp.columns if col != "hpp_food_id"})
    nutrient_cols = [
        col
        for col in joined.columns
        if col
        not in {
            "hpp_food_id",
            "hpp_food_name",
            "hpp_short_description",
            "hpp_category",
            "candidate_rank",
            "match_score",
            "confidence",
            "source",
            "source_food_id",
            "matched_food_name",
            "matched_category",
            "stage",
            "needs_human_review",
        }
    ]
    joined = joined.rename(columns={col: f"mapped__{col}" for col in nutrient_cols})
    enriched = hpp.merge(joined, on="hpp_food_id", how="left")
    enriched.to_csv(OUT / "hpp_nutrient_harmonized.csv", index=False)

    summary = {
        "hpp_food_rows": int(enriched.shape[0]),
        "mapped_rows_with_any_source_nutrient": int(
            enriched[[col for col in enriched.columns if col.startswith("mapped__")]].notna().any(axis=1).sum()
        ),
        "hpp_nutrient_columns": len([col for col in enriched.columns if col.startswith("hpp__")]),
        "mapped_nutrient_columns": len([col for col in enriched.columns if col.startswith("mapped__")]),
        "output": str(OUT / "hpp_nutrient_harmonized.csv"),
    }
    (OUT / "nutrient_harmonization_summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def _weighted_mean(values, weights):
    numeric_values = pd.to_numeric(values, errors="coerce")
    numeric_weights = pd.to_numeric(weights, errors="coerce").fillna(1)
    mask = numeric_values.notna()
    if not mask.any():
        return pd.NA, 0
    valid_values = numeric_values[mask]
    valid_weights = numeric_weights[mask].clip(lower=0)
    if valid_weights.sum() == 0:
        valid_weights = pd.Series(1, index=valid_values.index)
    return float((valid_values * valid_weights).sum() / valid_weights.sum()), int(mask.sum())


def _best_confidence(values):
    order = {"high": 4, "medium": 3, "review": 2, "low": 1}
    clean = [str(value) for value in values.dropna().tolist()]
    if not clean:
        return "unknown"
    return max(clean, key=lambda value: order.get(value, 0))


def _mode_text(values):
    clean = values.dropna().astype(str)
    clean = clean[clean.str.len() > 0]
    if clean.empty:
        return ""
    return clean.mode().iloc[0]


def _ensure_canonical_outputs():
    canonical_path = ROOT / "outputs/canonical/canonical_foods.csv"
    crosswalk_path = ROOT / "outputs/canonical/hpp_to_canonical.csv"
    if not canonical_path.exists() or not crosswalk_path.exists():
        from .canonical import build_canonical_tables

        build_canonical_tables()
    return pd.read_csv(canonical_path), pd.read_csv(crosswalk_path)


def _ensure_hpp_harmonized():
    harmonized_path = OUT / "hpp_nutrient_harmonized.csv"
    if not harmonized_path.exists():
        harmonize_nutrients()
    return pd.read_csv(harmonized_path)


def impute_canonical_nutrients():
    """Build canonical-food nutrient profiles with row-level provenance.

    Rule for each canonical food and nutrient:
    1. Prefer observed HPP nutrient values, aggregated across repeated HPP IDs.
    2. If HPP is missing, use mapped public-source nutrient values.
    3. Leave missing if neither layer has usable numeric data.
    """
    OUT.mkdir(parents=True, exist_ok=True)
    canonical, crosswalk = _ensure_canonical_outputs()
    harmonized = _ensure_hpp_harmonized()

    weights = pd.read_csv(HPP_PATH, usecols=["food_id", "number_loggings"]).rename(
        columns={"food_id": "hpp_food_id"}
    )
    crosswalk["hpp_food_id"] = crosswalk["hpp_food_id"].astype(str)
    harmonized["hpp_food_id"] = harmonized["hpp_food_id"].astype(str)
    weights["hpp_food_id"] = weights["hpp_food_id"].astype(str)

    merged = (
        crosswalk[
            [
                "hpp_food_id",
                "canonical_food_id",
                "canonical_name",
                "canonical_category",
            ]
        ]
        .merge(harmonized, on="hpp_food_id", how="left")
        .merge(weights, on="hpp_food_id", how="left")
    )
    merged["number_loggings"] = pd.to_numeric(merged["number_loggings"], errors="coerce").fillna(1)

    hpp_cols = [col for col in merged.columns if col.startswith("hpp__")]
    mapped_cols = [col for col in merged.columns if col.startswith("mapped__")]
    nutrient_names = sorted(
        {col.removeprefix("hpp__") for col in hpp_cols}
        | {col.removeprefix("mapped__") for col in mapped_cols}
    )

    provenance_rows = []
    wide_rows = []

    canonical_lookup = canonical.set_index("canonical_food_id", drop=False)
    for canonical_food_id, group in merged.groupby("canonical_food_id", sort=True):
        meta = canonical_lookup.loc[canonical_food_id]
        wide_row = {
            "canonical_food_id": canonical_food_id,
            "canonical_name": meta.get("canonical_name", group["canonical_name"].iloc[0]),
            "canonical_category": meta.get("canonical_category", group["canonical_category"].iloc[0]),
            "hpp_food_count": int(group["hpp_food_id"].nunique()),
        }

        for nutrient_name in nutrient_names:
            hpp_col = f"hpp__{nutrient_name}"
            mapped_col = f"mapped__{nutrient_name}"
            hpp_value, hpp_count = (
                _weighted_mean(group[hpp_col], group["number_loggings"])
                if hpp_col in group
                else (pd.NA, 0)
            )
            mapped_value, mapped_count = (
                _weighted_mean(group[mapped_col], group["number_loggings"])
                if mapped_col in group
                else (pd.NA, 0)
            )

            if pd.notna(hpp_value):
                final_value = hpp_value
                chosen_source = "HPP"
                source_food_id = ""
                confidence = "high"
                method = "weighted_hpp_observed_mean"
            elif pd.notna(mapped_value):
                final_value = mapped_value
                source_rows = group[group[mapped_col].notna()] if mapped_col in group else group.iloc[0:0]
                chosen_source = _mode_text(source_rows.get("source", pd.Series(dtype=str)))
                source_food_id = _mode_text(source_rows.get("source_food_id", pd.Series(dtype=str)))
                confidence = _best_confidence(source_rows.get("confidence", pd.Series(dtype=str)))
                method = "weighted_mapped_public_source_mean"
            else:
                continue

            wide_row[nutrient_name] = final_value
            provenance_rows.append(
                {
                    "canonical_food_id": canonical_food_id,
                    "canonical_name": wide_row["canonical_name"],
                    "canonical_category": wide_row["canonical_category"],
                    "nutrient_name": nutrient_name,
                    "final_value": final_value,
                    "unit_status": "source_native_units_not_yet_standardized",
                    "chosen_source": chosen_source,
                    "source_food_id": source_food_id,
                    "confidence": confidence,
                    "method": method,
                    "hpp_value": hpp_value,
                    "mapped_value": mapped_value,
                    "hpp_observation_count": hpp_count,
                    "mapped_observation_count": mapped_count,
                }
            )

        wide_rows.append(wide_row)

    profiles = pd.DataFrame(wide_rows).sort_values(["canonical_name", "canonical_category"])
    provenance = pd.DataFrame(provenance_rows).sort_values(
        ["canonical_name", "canonical_category", "nutrient_name"]
    )

    profiles_path = OUT / "canonical_nutrient_profiles.csv"
    provenance_path = OUT / "canonical_nutrient_provenance.csv"
    profiles.to_csv(profiles_path, index=False)
    provenance.to_csv(provenance_path, index=False)

    summary = {
        "canonical_food_count": int(profiles["canonical_food_id"].nunique()),
        "nutrient_profile_rows": int(profiles.shape[0]),
        "nutrient_value_count": int(provenance.shape[0]),
        "nutrients_with_any_value": int(provenance["nutrient_name"].nunique()),
        "values_chosen_from_hpp": int((provenance["chosen_source"] == "HPP").sum()),
        "values_imputed_from_public_sources": int((provenance["chosen_source"] != "HPP").sum()),
        "outputs": {
            "canonical_nutrient_profiles": str(profiles_path),
            "canonical_nutrient_provenance": str(provenance_path),
        },
        "important_note": (
            "Nutrient names are harmonized, but units are still source-native. "
            "Use the provenance table before treating values as analytically final."
        ),
    }
    (OUT / "canonical_nutrient_imputation_summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def main():
    summary = harmonize_nutrients()
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
