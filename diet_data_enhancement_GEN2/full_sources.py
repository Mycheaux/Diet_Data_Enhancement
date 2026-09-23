"""Prepare independent all-food identities and raw public composition sources."""

import json
import re
import unicodedata
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from .independent_pilot import ROOT, HPP, USDA, read_identity, digest, write_json


OUT = ROOT / "outputs_GEN2/step1d_all_foods"
REF = OUT / "reference"
FNDDS = ROOT / "data/USDA_FNDDS/FoodData_Central_survey_food_csv_2024-10-31.zip"
TZAMERET = ROOT / "data/Tzameret_Israel/moh_mitzrachim.csv"


def normalize(text):
    if pd.isna(text):
        return ""
    return re.sub(r"[^\w%]+", " ", unicodedata.normalize("NFKC", str(text)).casefold()).strip()


def read_zip_member(archive, name):
    members = [n for n in archive.namelist() if n.endswith(f"/{name}.csv")]
    if len(members) != 1:
        raise ValueError(f"Ambiguous source table {name}")
    with archive.open(members[0]) as handle:
        return pd.read_csv(handle)


def load_usda(path, source):
    with zipfile.ZipFile(path) as archive:
        food = read_zip_member(archive, "food")
        nutrients = read_zip_member(archive, "nutrient")
        values = read_zip_member(archive, "food_nutrient")
        if source == "SR":
            category = read_zip_member(archive, "food_category")
            categories = category.set_index("id").description
        else:
            category = read_zip_member(archive, "wweia_food_category")
            categories = category.set_index("wweia_food_category_code").wweia_food_category_description
    if values.duplicated(["fdc_id", "nutrient_id"]).any():
        raise ValueError("Source nutrient duplicates require review, not averaging.")
    food["source_food_key"] = source + ":" + food.fdc_id.astype(str)
    food["source"] = source
    food["source_food_id"] = food.fdc_id.astype(str)
    food["food_name"] = food.description
    food["hebrew_name"] = ""
    food["category"] = food.food_category_id.map(categories).fillna("")
    food["source_url"] = "https://fdc.nal.usda.gov/food-details/" + food.fdc_id.astype(str) + "/nutrients"
    values["source_food_key"] = source + ":" + values.fdc_id.astype(str)
    values["source"] = source
    values = values.rename(columns={"id": "source_row_id"})
    values = values.merge(nutrients[["id", "name", "unit_name"]], left_on="nutrient_id", right_on="id", validate="many_to_one")
    values = values.drop(columns="id")
    if values.name.isna().any() or (~np.isfinite(values.amount)).any() or values.amount.lt(0).any():
        raise ValueError("Invalid public source values or definitions.")
    return food, nutrients, values


def main():
    REF.mkdir(parents=True, exist_ok=True)
    identities = read_identity(HPP)
    identities.to_csv(OUT / "identities.csv", index=False)
    foods, catalogs, amounts = [], [], []
    for source, path in [("SR", USDA), ("FNDDS", FNDDS)]:
        food, catalog, values = load_usda(path, source)
        foods.append(food)
        catalogs.append(catalog)
        amounts.append(values)
    # Public-source composition is permitted here; HPP nutrients are not read.
    tz = pd.read_csv(TZAMERET, dtype={"Code": str})
    tz_food = pd.DataFrame({"source_food_key": "TZ:" + tz.Code,
                           "source": "TZ", "source_food_id": tz.Code,
                           "food_name": tz.english_name.fillna(""), "hebrew_name": tz.shmmitzrach.fillna(""),
                           "category": "", "source_url": "https://www.gov.il/he/departments/topics/nutrition"})
    foods.append(tz_food)
    columns = ["source_food_key", "source", "source_food_id", "food_name", "hebrew_name", "category", "source_url"]
    food = pd.concat([f[columns] for f in foods], ignore_index=True)
    if food.source_food_key.duplicated().any() or (food.food_name.eq("") & food.hebrew_name.eq("")).any():
        raise ValueError("Invalid reference identity table.")
    food.to_csv(REF / "foods.csv", index=False)
    all_amounts = pd.concat(amounts, ignore_index=True)
    all_amounts.to_csv(REF / "usda_nutrients.csv.gz", index=False, compression="gzip")
    catalog = pd.concat(catalogs, ignore_index=True).drop_duplicates(["id", "name", "unit_name"])
    if catalog.id.duplicated().any():
        raise ValueError("Conflicting nutrient definitions across public sources.")
    used_ids = set(all_amounts.nutrient_id)
    catalog.loc[catalog.id.isin(used_ids)].to_csv(REF / "usda_nutrient_dictionary.csv", index=False)
    tz.to_csv(REF / "tzameret_public_source.csv", index=False)
    by_name = {}
    for row in food.itertuples():
        for text in [row.food_name, row.hebrew_name]:
            name = normalize(text)
            if name:
                by_name.setdefault(name, set()).add(row.source_food_key)
    exact = []
    for row in identities.itertuples():
        matches = set()
        for text in [row.product_name, row.hebrew_name, row.short_name]:
            matches.update(by_name.get(normalize(text), []))
        for source_key in sorted(matches):
            exact.append({"hpp_food_id": row.hpp_food_id, "source_food_key": source_key,
                          "method": "normalized_original_identity_exact_not_nutrient_match"})
    pd.DataFrame(exact).to_csv(REF / "exact_identity_links.csv", index=False)
    summary = {"hpp_foods": len(identities), "public_foods": len(food),
               "public_foods_by_source": food.source.value_counts().to_dict(),
               "used_usda_nutrient_ids": len(used_ids),
               "foods_with_exact_identity_candidate": len({r["hpp_food_id"] for r in exact}),
               "hpp_allowed_columns": ["food_id", "product_name", "hebrew_name", "short_name"],
               "hpp_nutrient_columns_read": 0, "gen1_outputs_read": 0}
    write_json("source_summary.json", summary, REF)
    write_json("source_manifest.json", {
        "code_sha256": digest(Path(__file__)),
        "identity_values_sha256": digest(OUT / "identities.csv"),
        "public_source_hashes": {str(p.relative_to(ROOT)): digest(p) for p in [USDA, FNDDS, TZAMERET]},
        "outputs": {p.name: digest(p) for p in sorted(REF.glob("*.csv*"))},
    }, REF)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
