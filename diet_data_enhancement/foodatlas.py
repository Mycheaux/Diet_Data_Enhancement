from pathlib import Path

import pandas as pd

from .mapping import build_index, find_candidates, map_hpp_to_public
from .sources import ROOT, load_foodatlas_entities_if_available, load_hpp_foods


FOODATLAS_ZIP = ROOT / "data/FoodAtlas/foodatlas-v4.5.zip"
FOODATLAS_ENTITY_CSV = ROOT / "outputs/foodatlas/entities_foods.csv"


def extract_food_entities_from_parquet(zip_path=FOODATLAS_ZIP, out_path=FOODATLAS_ENTITY_CSV):
    """Extract FoodAtlas food-like entities when parquet support is installed.

    The current workspace runtime does not include a parquet engine. Keeping this
    as an explicit function makes the dependency boundary clear: once pyarrow or
    fastparquet is available, this will create the CSV used by the deep mapper.
    """
    import zipfile

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        with archive.open("foodatlas-v4.5/entities.parquet") as handle:
            entities = pd.read_parquet(handle)

    required = ["foodatlas_id", "entity_type", "common_name", "synonyms", "attributes"]
    missing = [col for col in required if col not in entities.columns]
    if missing:
        raise ValueError(f"FoodAtlas entities file is missing expected columns: {missing}")

    foods = entities[entities["entity_type"].astype(str).str.lower().eq("food")].copy()
    foods["food_groups"] = foods["attributes"].astype(str)
    foods[["foodatlas_id", "common_name", "synonyms", "food_groups"]].to_csv(out_path, index=False)
    return out_path


def map_reviewed_items_to_foodatlas(human_corrections_path=None, out_path=None, top_k=5):
    human_corrections_path = Path(human_corrections_path or ROOT / "outputs/mapping/human_corrections.csv")
    out_path = Path(out_path or ROOT / "outputs/foodatlas/human_foodatlas_remap.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    foodatlas = load_foodatlas_entities_if_available()
    if foodatlas.empty:
        pd.DataFrame(
            columns=[
                "hpp_food_id",
                "human_food_name",
                "foodatlas_id",
                "foodatlas_name",
                "match_score",
                "confidence",
                "status",
            ]
        ).to_csv(out_path, index=False)
        return out_path

    corrections = pd.read_csv(human_corrections_path)
    index = build_index(foodatlas)
    rows = []
    for _, correction in corrections.iterrows():
        for candidate in find_candidates(correction["human_food_name"], index, top_k=top_k):
            rows.append(
                {
                    "hpp_food_id": correction["hpp_food_id"],
                    "human_food_name": correction["human_food_name"],
                    "foodatlas_id": candidate["source_food_id"],
                    "foodatlas_name": candidate["matched_food_name"],
                    "match_score": candidate["match_score"],
                    "confidence": candidate["confidence"],
                    "status": "candidate",
                }
            )
    pd.DataFrame(rows).to_csv(out_path, index=False)
    return out_path


def map_hpp_to_foodatlas(out_path=None, top_k=5):
    out_path = Path(out_path or ROOT / "outputs/foodatlas/hpp_foodatlas_candidates.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    foodatlas = load_foodatlas_entities_if_available()
    hpp = load_hpp_foods()
    if foodatlas.empty:
        pd.DataFrame().to_csv(out_path, index=False)
        return out_path
    mapped = map_hpp_to_public(hpp, foodatlas, top_k=top_k)
    mapped["stage"] = "foodatlas_direct_deep_remap"
    mapped.to_csv(out_path, index=False)
    return out_path
