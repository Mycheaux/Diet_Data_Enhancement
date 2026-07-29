import zipfile
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def _clean_records(df, source, id_col, name_col, category_col=None, extra_cols=None):
    extra_cols = extra_cols or []
    records = []
    for _, row in df.iterrows():
        name = row.get(name_col)
        if pd.isna(name) or not str(name).strip():
            continue
        records.append(
            {
                "source": source,
                "source_food_id": str(row.get(id_col, "")).strip(),
                "food_name": str(name).strip(),
                "category": "" if category_col is None or pd.isna(row.get(category_col)) else str(row.get(category_col)).strip(),
                **{
                    col: "" if pd.isna(row.get(col)) else str(row.get(col)).strip()
                    for col in extra_cols
                    if col in row
                },
            }
        )
    return pd.DataFrame(records)


def load_hpp_foods(path=ROOT / "data/HPP/hpp_food_items_with_nutrients.csv"):
    df = pd.read_csv(path)
    out = df[["food_id", "short_description", "category_hint", "gpt_short_food_name", "hebrew_name"]].copy()
    out["food_name"] = out["gpt_short_food_name"].fillna(out["short_description"])
    out["category"] = out["category_hint"].fillna("")
    return out.rename(columns={"food_id": "hpp_food_id"})[
        ["hpp_food_id", "food_name", "short_description", "category", "hebrew_name"]
    ]


def load_usda_sr(path=ROOT / "data/USDA_SR_Legacy/FoodData_Central_sr_legacy_food_csv_2018-04.zip"):
    with zipfile.ZipFile(path) as archive:
        with archive.open("FoodData_Central_sr_legacy_food_csv_2018-04/food.csv") as handle:
            food = pd.read_csv(handle)
    return _clean_records(food, "USDA_SR_Legacy", "fdc_id", "description", "food_category_id")


def load_usda_fndds(path=ROOT / "data/USDA_FNDDS/FoodData_Central_survey_food_csv_2024-10-31.zip"):
    with zipfile.ZipFile(path) as archive:
        with archive.open("FoodData_Central_survey_food_csv_2024-10-31/food.csv") as handle:
            food = pd.read_csv(handle)
    return _clean_records(food, "USDA_FNDDS", "fdc_id", "description", "food_category_id")


def load_tzameret(path=ROOT / "data/Tzameret_Israel/moh_mitzrachim.csv"):
    df = pd.read_csv(path)
    return _clean_records(df, "Tzameret_Israel", "Code", "english_name", extra_cols=["shmmitzrach"]).rename(
        columns={"shmmitzrach": "hebrew_name"}
    )


def load_ausnut(path=ROOT / "data/AUSNUT_Australia/AUSNUT-2023-Food-details-4.xlsx"):
    df = pd.read_excel(path, sheet_name="Food details", header=[2, 3])
    df.columns = [
        "_".join(str(part) for part in col if str(part) != "nan").strip("_")
        for col in df.columns
    ]
    survey_id = next(col for col in df.columns if col.startswith("Survey ID"))
    food_name = next(col for col in df.columns if col.startswith("Food name"))
    food_description = next(col for col in df.columns if col.startswith("Food description"))
    food_group = next(
        col
        for col in df.columns
        if col.startswith("2023 Food and dietary supplement classification")
        and "Food group name" in col
    )
    return _clean_records(
        df,
        "AUSNUT_Australia",
        survey_id,
        food_name,
        food_group,
        [food_description],
    )


def load_bahrain(path=ROOT / "data/Bahrain FCT/Bahrain_Food_Composition_Table_pdf_extracted.xlsx"):
    df = pd.read_excel(path)
    return _clean_records(df, "Bahrain_FCT", "Item No.", "Food Name (English)", "Food Category")


def load_mext_names(path=ROOT / "data/MEXT_Japan/1385123_Table18.xlsx"):
    """Load Japanese MEXT English/scientific names as a lightweight name source.

    The local Table 18 workbook is a supplementary English/scientific-name table,
    not the full nutrient table. We include it in Layer 1 candidate generation as
    a food identity/cooking-context source, while keeping nutrient extraction for
    a later adapter.
    """
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=["source", "source_food_id", "food_name", "category"])
    raw = pd.read_excel(path, header=None)
    header_idx = None
    for idx, row in raw.iterrows():
        values = [str(value).strip().lower() for value in row.tolist()]
        if "item no." in values and "english name" in values:
            header_idx = idx
            break
    if header_idx is None:
        return pd.DataFrame(columns=["source", "source_food_id", "food_name", "category"])
    df = raw.iloc[header_idx + 1 :, :3].copy()
    df.columns = ["item_no", "english_name", "scientific_name"]
    df = df[df["english_name"].notna()]
    df["english_name"] = df["english_name"].astype(str).str.replace("\n", " ", regex=False)
    df = df[~df["english_name"].str.match(r"^\s*\d+\s+[A-Z ]+\s*$", na=False)]
    return _clean_records(df, "MEXT_Japan", "item_no", "english_name", extra_cols=["scientific_name"])


def load_public_foods():
    frames = [
        load_usda_sr(),
        load_usda_fndds(),
        load_tzameret(),
        load_ausnut(),
        load_bahrain(),
        load_mext_names(),
    ]
    return pd.concat(frames, ignore_index=True)


def load_foodatlas_entities_if_available(path=ROOT / "outputs/foodatlas/entities_foods.csv"):
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=["source", "source_food_id", "food_name", "category"])
    df = pd.read_csv(path)
    id_col = "foodatlas_id" if "foodatlas_id" in df.columns else ("id" if "id" in df.columns else df.columns[0])
    name_col = "common_name" if "common_name" in df.columns else ("name" if "name" in df.columns else df.columns[1])
    category_col = "food_groups" if "food_groups" in df.columns else ("category" if "category" in df.columns else None)
    return _clean_records(df, "FoodAtlas", id_col, name_col, category_col)
