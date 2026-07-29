import argparse
import json
import os
import zipfile
from collections import Counter
from pathlib import Path

import pandas as pd

from .canonical import build_canonical_tables, canonical_as_foods, load_canonical_foods, run_canonical_pipeline
from .foodatlas import extract_food_entities_from_parquet, map_hpp_to_foodatlas
from .mapping import map_hpp_to_public
from .nutrients import impute_canonical_nutrients
from .sources import ROOT, load_public_foods
from .text import tokens


OUT = ROOT / "outputs"
LAYERED = OUT / "layered"
REFERENCE = OUT / "reference"

OPENFOODFACTS_PATH = ROOT / "data/OpenFoodFacts/en.openfoodfacts.org.products.csv"
FOODATLAS_ZIP = ROOT / "data/FoodAtlas/foodatlas-v4.5.zip"

OFF_ID_COLS = [
    "code",
    "product_name",
    "generic_name",
    "brands",
    "categories",
    "categories_en",
    "countries_en",
    "ingredients_text",
    "additives_n",
    "additives_tags",
    "allergens",
    "labels_en",
    "nutriscore_grade",
    "nova_group",
    "pnns_groups_1",
    "pnns_groups_2",
    "food_groups_en",
    "main_category_en",
    "completeness",
    "energy-kcal_100g",
    "fat_100g",
    "saturated-fat_100g",
    "carbohydrates_100g",
    "sugars_100g",
    "fiber_100g",
    "proteins_100g",
    "salt_100g",
    "sodium_100g",
]


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))


def _ensure_canonical():
    if not (OUT / "canonical/canonical_foods.csv").exists():
        run_canonical_pipeline()
    canonical = load_canonical_foods()
    return canonical, canonical_as_foods(canonical)


def build_layer1_candidates(top_k=5):
    """Map canonical foods to curated nutrient/FCDB identity sources."""
    LAYERED.mkdir(parents=True, exist_ok=True)
    _, canonical_foods = _ensure_canonical()
    public = load_public_foods()
    candidates = map_hpp_to_public(canonical_foods, public, top_k=top_k).rename(
        columns={
            "hpp_food_id": "canonical_food_id",
            "hpp_food_name": "canonical_name",
            "hpp_short_description": "representative_original_name",
            "hpp_category": "canonical_category",
        }
    )
    candidates["source_layer"] = "layer_1_nutrients"
    candidates["mapping_role"] = "nutrient_reference"
    candidates["stage"] = "layered_canonical_nutrient_candidate"
    out_path = LAYERED / "layer1_nutrient_candidates.csv"
    candidates.to_csv(out_path, index=False)
    summary = {
        "layer": "Layer 1: nutrients",
        "candidate_rows": int(candidates.shape[0]),
        "canonical_food_count": int(candidates["canonical_food_id"].nunique()),
        "source_counts": candidates["source"].value_counts().to_dict(),
        "top_match_confidence_counts": (
            candidates[candidates["candidate_rank"] == 1]["confidence"].value_counts().to_dict()
        ),
        "output": str(out_path),
    }
    _write_json(LAYERED / "layer1_nutrient_candidates_summary.json", summary)
    return candidates, summary


def _canonical_token_set(canonical):
    keep = set()
    for value in canonical["canonical_name"].dropna().astype(str):
        for token in tokens(value):
            if len(token) >= 3:
                keep.add(token)
    return keep


def load_openfoodfacts_products(max_scan_rows=None, max_candidates=150000, chunksize=100000):
    """Load a bounded, token-filtered OpenFoodFacts candidate table.

    The full local OpenFoodFacts TSV is very large. This loader scans a
    configurable prefix and keeps rows that share informative tokens with the
    canonical HPP food names. Set OFF_MAX_SCAN_ROWS=0 to scan the whole file.
    """
    if not OPENFOODFACTS_PATH.exists():
        return pd.DataFrame(columns=["source", "source_food_id", "food_name", "category"])
    canonical = load_canonical_foods()
    canonical_tokens = _canonical_token_set(canonical)
    max_scan_rows = int(os.getenv("OFF_MAX_SCAN_ROWS", max_scan_rows or 300000))
    if max_scan_rows <= 0:
        max_scan_rows = None
    max_candidates = int(os.getenv("OFF_MAX_CANDIDATES", max_candidates))

    rows = []
    scanned = 0
    for chunk in pd.read_csv(
        OPENFOODFACTS_PATH,
        sep="\t",
        dtype=str,
        usecols=lambda col: col in OFF_ID_COLS,
        chunksize=chunksize,
        low_memory=False,
    ):
        scanned += len(chunk)
        text = (
            chunk.get("product_name", "").fillna("")
            + " "
            + chunk.get("generic_name", "").fillna("")
            + " "
            + chunk.get("categories_en", "").fillna("")
            + " "
            + chunk.get("brands", "").fillna("")
        )
        for idx, row_text in text.items():
            row_tokens = set(tokens(row_text))
            if not row_tokens.intersection(canonical_tokens):
                continue
            row = chunk.loc[idx].to_dict()
            food_name = row.get("product_name") or row.get("generic_name") or row.get("categories_en") or ""
            if not str(food_name).strip():
                continue
            ingredient_text = str(row.get("ingredients_text") or "")
            rows.append(
                {
                    "source": "OpenFoodFacts",
                    "source_food_id": str(row.get("code") or "").strip(),
                    "food_name": str(food_name).strip(),
                    "category": str(row.get("categories_en") or row.get("main_category_en") or "").strip(),
                    "generic_name": row.get("generic_name", ""),
                    "brands": row.get("brands", ""),
                    "countries_en": row.get("countries_en", ""),
                    "ingredients_text": ingredient_text,
                    "ingredient_count": len([part for part in ingredient_text.split(",") if part.strip()]),
                    "additives_n": row.get("additives_n", ""),
                    "additives_tags": row.get("additives_tags", ""),
                    "allergens": row.get("allergens", ""),
                    "labels_en": row.get("labels_en", ""),
                    "nutriscore_grade": row.get("nutriscore_grade", ""),
                    "nova_group": row.get("nova_group", ""),
                    "pnns_groups_1": row.get("pnns_groups_1", ""),
                    "pnns_groups_2": row.get("pnns_groups_2", ""),
                    "food_groups_en": row.get("food_groups_en", ""),
                    "completeness": row.get("completeness", ""),
                    "energy_kcal_100g": row.get("energy-kcal_100g", ""),
                    "fat_100g": row.get("fat_100g", ""),
                    "saturated_fat_100g": row.get("saturated-fat_100g", ""),
                    "carbohydrates_100g": row.get("carbohydrates_100g", ""),
                    "sugars_100g": row.get("sugars_100g", ""),
                    "fiber_100g": row.get("fiber_100g", ""),
                    "proteins_100g": row.get("proteins_100g", ""),
                    "salt_100g": row.get("salt_100g", ""),
                    "sodium_100g": row.get("sodium_100g", ""),
                }
            )
            if len(rows) >= max_candidates:
                return pd.DataFrame(rows)
        if max_scan_rows is not None and scanned >= max_scan_rows:
            break
    return pd.DataFrame(rows)


def build_layer2_candidates(top_k=5):
    """Map canonical foods to OpenFoodFacts product/processing candidates."""
    LAYERED.mkdir(parents=True, exist_ok=True)
    _, canonical_foods = _ensure_canonical()
    off = load_openfoodfacts_products()
    candidate_source_path = LAYERED / "openfoodfacts_candidate_source.csv"
    off.to_csv(candidate_source_path, index=False)
    if off.empty:
        candidates = pd.DataFrame()
    else:
        candidates = map_hpp_to_public(canonical_foods, off, top_k=top_k).rename(
            columns={
                "hpp_food_id": "canonical_food_id",
                "hpp_food_name": "canonical_name",
                "hpp_short_description": "representative_original_name",
                "hpp_category": "canonical_category",
            }
        )
        extra = off.drop_duplicates(["source", "source_food_id"])
        candidates = candidates.merge(
            extra,
            left_on=["source", "source_food_id"],
            right_on=["source", "source_food_id"],
            how="left",
            suffixes=("", "_off"),
        )
    if not candidates.empty:
        candidates["source_layer"] = "layer_2_product_processing"
        candidates["mapping_role"] = "product_processing"
        candidates["stage"] = "layered_openfoodfacts_product_candidate"
    out_path = LAYERED / "layer2_openfoodfacts_candidates.csv"
    candidates.to_csv(out_path, index=False)
    summary = {
        "layer": "Layer 2: product/processing",
        "openfoodfacts_candidate_source_rows": int(off.shape[0]),
        "candidate_rows": int(candidates.shape[0]),
        "canonical_food_count": int(candidates["canonical_food_id"].nunique()) if not candidates.empty else 0,
        "top_match_confidence_counts": (
            candidates[candidates["candidate_rank"] == 1]["confidence"].value_counts().to_dict()
            if not candidates.empty
            else {}
        ),
        "outputs": {
            "candidate_source": str(candidate_source_path),
            "candidates": str(out_path),
        },
        "note": (
            "OpenFoodFacts loading is bounded by OFF_MAX_SCAN_ROWS and OFF_MAX_CANDIDATES. "
            "Set OFF_MAX_SCAN_ROWS=0 for a full scan."
        ),
    }
    _write_json(LAYERED / "layer2_openfoodfacts_candidates_summary.json", summary)
    return candidates, summary


def _top_by_id(df, id_col):
    if df.empty:
        return df
    return df.sort_values([id_col, "candidate_rank"]).groupby(id_col, as_index=False).head(1)


def canonical_usage_table(canonical):
    crosswalk_path = OUT / "canonical/hpp_to_canonical.csv"
    if not crosswalk_path.exists():
        build_canonical_tables()
    crosswalk = pd.read_csv(crosswalk_path, dtype=str)
    hpp_usage = pd.read_csv(
        ROOT / "data/HPP/hpp_food_items_with_nutrients.csv",
        usecols=["food_id", "number_loggings"],
        dtype={"food_id": str},
    ).rename(columns={"food_id": "hpp_food_id"})
    hpp_usage["number_loggings"] = pd.to_numeric(hpp_usage["number_loggings"], errors="coerce").fillna(0)
    usage = (
        crosswalk[["hpp_food_id", "canonical_food_id"]]
        .merge(hpp_usage, on="hpp_food_id", how="left")
        .groupby("canonical_food_id", as_index=False)
        .agg(
            total_loggings=("number_loggings", "sum"),
            hpp_item_count=("hpp_food_id", "nunique"),
        )
    )
    usage = usage.sort_values("total_loggings", ascending=False).reset_index(drop=True)
    total = usage["total_loggings"].sum()
    usage["cumulative_logging_share"] = usage["total_loggings"].cumsum() / total if total else 0

    def tier(share):
        if share <= 0.80:
            return "tier_1_high_usage_top_80pct"
        if share <= 0.95:
            return "tier_2_medium_usage_next_15pct"
        return "tier_3_low_usage_last_5pct"

    usage["usage_tier"] = usage["cumulative_logging_share"].map(tier)
    return canonical.merge(usage, on="canonical_food_id", how="left")


def build_hitl_queue():
    """Build a combined Layer 1 + Layer 2 review queue for role-specific HITL."""
    LAYERED.mkdir(parents=True, exist_ok=True)
    canonical = canonical_usage_table(load_canonical_foods())
    l1_path = LAYERED / "layer1_nutrient_candidates.csv"
    l2_path = LAYERED / "layer2_openfoodfacts_candidates.csv"
    if not l1_path.exists():
        build_layer1_candidates()
    if not l2_path.exists():
        build_layer2_candidates()
    l1 = pd.read_csv(l1_path, dtype=str)
    l2 = pd.read_csv(l2_path, dtype=str) if l2_path.exists() else pd.DataFrame()
    top_l1 = _top_by_id(l1, "canonical_food_id")
    top_l2 = _top_by_id(l2, "canonical_food_id") if not l2.empty else pd.DataFrame()

    rows = []
    for _, food in canonical.iterrows():
        cid = food["canonical_food_id"]
        nutrient = top_l1[top_l1["canonical_food_id"].eq(cid)]
        product = top_l2[top_l2["canonical_food_id"].eq(cid)] if not top_l2.empty else pd.DataFrame()
        n = nutrient.iloc[0].to_dict() if not nutrient.empty else {}
        p = product.iloc[0].to_dict() if not product.empty else {}
        n_conf = n.get("confidence", "review")
        p_conf = p.get("confidence", "")
        product_strong = bool(p) and p_conf in {"medium", "high"}
        nutrient_weak = n_conf in {"low", "review"}
        needs_review = nutrient_weak and not product_strong
        if product_strong and nutrient_weak:
            reason = "Auto-accepted because Layer 2 has a strong product/processing candidate."
        elif product_strong:
            reason = "Auto-accepted because Layer 1 is acceptable and Layer 2 is strong."
        elif nutrient_weak:
            reason = "Nutrient-layer candidate is weak or ambiguous."
        else:
            reason = "Auto-accepted because Layer 1 candidate is acceptable."
        rows.append(
            {
                "canonical_food_id": cid,
                "canonical_name": food.get("canonical_name", ""),
                "canonical_category": food.get("canonical_category", ""),
                "hpp_food_count": food.get("hpp_food_count", ""),
                "hpp_item_count": food.get("hpp_item_count", food.get("hpp_food_count", "")),
                "total_loggings": int(food.get("total_loggings", 0) or 0),
                "cumulative_logging_share": round(float(food.get("cumulative_logging_share", 0) or 0), 6),
                "usage_tier": food.get("usage_tier", "tier_unknown"),
                "representative_hpp_food_id": food.get("representative_hpp_food_id", ""),
                "representative_original_name": food.get("representative_original_name", ""),
                "nutrient_source": n.get("source", ""),
                "nutrient_source_food_id": n.get("source_food_id", ""),
                "nutrient_matched_food_name": n.get("matched_food_name", ""),
                "nutrient_match_score": n.get("match_score", ""),
                "nutrient_confidence": n_conf,
                "product_source": p.get("source", ""),
                "product_source_food_id": p.get("source_food_id", ""),
                "product_matched_food_name": p.get("matched_food_name", ""),
                "product_match_score": p.get("match_score", ""),
                "product_confidence": p_conf,
                "product_brand": p.get("brands", ""),
                "product_category": p.get("category_off", p.get("matched_category", "")),
                "product_nova_group": p.get("nova_group", ""),
                "product_nutriscore_grade": p.get("nutriscore_grade", ""),
                "review_status": "pending" if needs_review else "auto_accept",
                "suggested_identity_type": "branded_or_packaged" if product_strong else "generic_or_recipe",
                "review_reason": reason,
                "reviewer_decision": "",
                "accepted_nutrient_source_id": "",
                "accepted_product_source_id": "",
                "assign_existing_canonical_food_id": "",
                "reviewer_notes": "",
            }
        )
    queue = pd.DataFrame(rows).sort_values(
        ["review_status", "usage_tier", "total_loggings", "canonical_name"],
        ascending=[False, True, False, True],
    )
    out_path = LAYERED / "hitl_review_queue.csv"
    queue.to_csv(out_path, index=False)
    accepted = queue[queue["review_status"].eq("auto_accept")].copy()
    accepted["accepted_nutrient_source_id"] = accepted["nutrient_source_food_id"]
    accepted["accepted_product_source_id"] = accepted["product_source_food_id"]
    accepted_path = LAYERED / "role_mapping_decisions.csv"
    accepted.to_csv(accepted_path, index=False)
    summary = {
        "queue_rows": int(queue.shape[0]),
        "pending_review_rows": int((queue["review_status"] == "pending").sum()),
        "auto_accept_rows": int((queue["review_status"] == "auto_accept").sum()),
        "pending_hpp_item_rows": int(
            pd.to_numeric(
                queue.loc[queue["review_status"].eq("pending"), "hpp_item_count"],
                errors="coerce",
            ).fillna(0).sum()
        ),
        "pending_total_loggings": int(
            pd.to_numeric(
                queue.loc[queue["review_status"].eq("pending"), "total_loggings"],
                errors="coerce",
            ).fillna(0).sum()
        ),
        "pending_by_usage_tier": (
            queue[queue["review_status"].eq("pending")]
            .groupby("usage_tier")
            .agg(
                canonical_food_count=("canonical_food_id", "nunique"),
                hpp_item_count=("hpp_item_count", lambda value: int(pd.to_numeric(value, errors="coerce").fillna(0).sum())),
                total_loggings=("total_loggings", lambda value: int(pd.to_numeric(value, errors="coerce").fillna(0).sum())),
            )
            .reset_index()
            .to_dict("records")
        ),
        "pending_by_nutrient_confidence": (
            queue[queue["review_status"].eq("pending")]["nutrient_confidence"].value_counts().to_dict()
        ),
        "outputs": {
            "hitl_review_queue": str(out_path),
            "role_mapping_decisions": str(accepted_path),
        },
    }
    _write_json(LAYERED / "hitl_review_queue_summary.json", summary)
    return queue, summary


def _numeric(series):
    return pd.to_numeric(series, errors="coerce")


def build_processing_reference():
    REFERENCE.mkdir(parents=True, exist_ok=True)
    l2_path = LAYERED / "layer2_openfoodfacts_candidates.csv"
    if not l2_path.exists():
        build_layer2_candidates()
    candidates = pd.read_csv(l2_path, dtype=str) if l2_path.exists() else pd.DataFrame()
    if candidates.empty:
        out = pd.DataFrame(columns=["canonical_food_id"])
    else:
        best = _top_by_id(candidates, "canonical_food_id").copy()
        for col in [
            "ingredient_count",
            "additives_n",
            "nova_group",
            "completeness",
            "energy_kcal_100g",
            "fat_100g",
            "saturated_fat_100g",
            "carbohydrates_100g",
            "sugars_100g",
            "fiber_100g",
            "proteins_100g",
            "salt_100g",
            "sodium_100g",
        ]:
            if col in best:
                best[col] = _numeric(best[col])
        out = best[
            [
                col
                for col in [
                    "canonical_food_id",
                    "canonical_name",
                    "source_food_id",
                    "matched_food_name",
                    "match_score",
                    "confidence",
                    "brands",
                    "countries_en",
                    "category_off",
                    "ingredients_text",
                    "ingredient_count",
                    "additives_n",
                    "additives_tags",
                    "allergens",
                    "labels_en",
                    "nutriscore_grade",
                    "nova_group",
                    "pnns_groups_1",
                    "pnns_groups_2",
                    "food_groups_en",
                    "completeness",
                    "energy_kcal_100g",
                    "fat_100g",
                    "saturated_fat_100g",
                    "carbohydrates_100g",
                    "sugars_100g",
                    "fiber_100g",
                    "proteins_100g",
                    "salt_100g",
                    "sodium_100g",
                ]
                if col in best.columns
            ]
        ].rename(
            columns={
                "source_food_id": "openfoodfacts_code",
                "matched_food_name": "openfoodfacts_product_name",
                "match_score": "openfoodfacts_match_score",
                "confidence": "openfoodfacts_confidence",
                "category_off": "openfoodfacts_category",
            }
        )
    out_path = REFERENCE / "canonical_food_processing_reference.csv"
    out.to_csv(out_path, index=False)
    return out_path


def _read_foodatlas():
    with zipfile.ZipFile(FOODATLAS_ZIP) as archive:
        with archive.open("foodatlas-v4.5/entities.parquet") as handle:
            entities = pd.read_parquet(handle)
        with archive.open("foodatlas-v4.5/relationships.parquet") as handle:
            relationships = pd.read_parquet(handle)
        with archive.open("foodatlas-v4.5/triplets.parquet") as handle:
            triplets = pd.read_parquet(handle)
    rel_names = dict(zip(relationships["foodatlas_id"], relationships["name"]))
    triplets["relationship_name"] = triplets["relationship_id"].map(rel_names)
    return entities, triplets


def build_foodatlas_reference():
    """Build FoodAtlas-derived compound/disease summary references."""
    REFERENCE.mkdir(parents=True, exist_ok=True)
    if not (OUT / "foodatlas/entities_foods.csv").exists():
        extract_food_entities_from_parquet()
    if not (OUT / "foodatlas/hpp_foodatlas_candidates.csv").exists():
        map_hpp_to_foodatlas()
    if not (OUT / "canonical/hpp_to_canonical.csv").exists():
        build_canonical_tables()
    crosswalk = pd.read_csv(OUT / "canonical/hpp_to_canonical.csv", dtype=str)
    candidates = pd.read_csv(OUT / "foodatlas/hpp_foodatlas_candidates.csv", dtype=str)
    if candidates.empty:
        return None, None
    candidates["candidate_rank"] = pd.to_numeric(candidates["candidate_rank"], errors="coerce")
    best = candidates.sort_values(["hpp_food_id", "candidate_rank"]).groupby("hpp_food_id").head(1)
    mapped = best.merge(crosswalk[["hpp_food_id", "canonical_food_id", "canonical_name"]], on="hpp_food_id", how="left")
    food_ids = mapped["source_food_id"].dropna().astype(str).unique().tolist()
    entities, triplets = _read_foodatlas()
    entity_lookup = entities.set_index("foodatlas_id").to_dict("index")
    contains = triplets[
        triplets["head_id"].astype(str).isin(food_ids)
        & triplets["relationship_name"].eq("contains")
    ].copy()
    fa_to_canonical = mapped[["source_food_id", "canonical_food_id", "canonical_name"]].dropna().drop_duplicates()
    compounds = contains.merge(fa_to_canonical, left_on="head_id", right_on="source_food_id", how="left")
    compound_rows = []
    for _, row in compounds.iterrows():
        chem = entity_lookup.get(row["tail_id"], {})
        compound_rows.append(
            {
                "canonical_food_id": row["canonical_food_id"],
                "canonical_name": row["canonical_name"],
                "foodatlas_food_id": row["head_id"],
                "foodatlas_chemical_id": row["tail_id"],
                "compound_name": chem.get("common_name", ""),
                "compound_entity_type": chem.get("entity_type", ""),
                "relationship": "contains",
                "source_database": "FoodAtlas",
            }
        )
    compound_ref = pd.DataFrame(compound_rows).drop_duplicates()
    compound_path = REFERENCE / "canonical_food_compound_reference.csv"
    compound_ref.to_csv(compound_path, index=False)

    disease_edges = triplets[
        triplets["head_id"].astype(str).isin(compound_ref.get("foodatlas_chemical_id", pd.Series(dtype=str)).astype(str))
        & triplets["relationship_name"].isin(["positively_correlates_with", "negatively_correlates_with"])
    ].copy()
    disease_counts = Counter()
    positive_counts = Counter()
    negative_counts = Counter()
    if not disease_edges.empty and not compound_ref.empty:
        chemical_to_foods = compound_ref.groupby("foodatlas_chemical_id")["canonical_food_id"].apply(set).to_dict()
        for _, edge in disease_edges.iterrows():
            for cid in chemical_to_foods.get(str(edge["head_id"]), set()):
                disease_counts[cid] += 1
                if edge["relationship_name"] == "positively_correlates_with":
                    positive_counts[cid] += 1
                else:
                    negative_counts[cid] += 1
    summary = (
        compound_ref.groupby("canonical_food_id")
        .agg(
            foodatlas_compound_count=("foodatlas_chemical_id", "nunique"),
            foodatlas_food_count=("foodatlas_food_id", "nunique"),
        )
        .reset_index()
        if not compound_ref.empty
        else pd.DataFrame(columns=["canonical_food_id", "foodatlas_compound_count", "foodatlas_food_count"])
    )
    summary["foodatlas_disease_edge_count"] = summary["canonical_food_id"].map(disease_counts).fillna(0).astype(int)
    summary["foodatlas_positive_disease_edge_count"] = summary["canonical_food_id"].map(positive_counts).fillna(0).astype(int)
    summary["foodatlas_negative_disease_edge_count"] = summary["canonical_food_id"].map(negative_counts).fillna(0).astype(int)
    summary_path = REFERENCE / "canonical_food_graph_features.csv"
    summary.to_csv(summary_path, index=False)
    return compound_path, summary_path


def build_reference_tables():
    REFERENCE.mkdir(parents=True, exist_ok=True)
    canonical = load_canonical_foods()
    master_path = REFERENCE / "canonical_food_master.csv"
    canonical.to_csv(master_path, index=False)
    nutrient_summary = impute_canonical_nutrients()
    nutrient_profile_path = Path(nutrient_summary["outputs"]["canonical_nutrient_profiles"])
    nutrient_reference = pd.read_csv(nutrient_profile_path)
    nutrient_out = REFERENCE / "canonical_food_nutrient_reference.csv"
    nutrient_reference.to_csv(nutrient_out, index=False)
    processing_path = build_processing_reference()
    compound_path, graph_features_path = build_foodatlas_reference()

    feature = canonical[["canonical_food_id", "canonical_name", "canonical_category", "hpp_food_count"]].copy()
    feature = feature.merge(nutrient_reference, on=["canonical_food_id", "canonical_name", "canonical_category", "hpp_food_count"], how="left")
    processing = pd.read_csv(processing_path) if Path(processing_path).exists() else pd.DataFrame()
    if not processing.empty:
        feature = feature.merge(processing.drop(columns=["canonical_name"], errors="ignore"), on="canonical_food_id", how="left")
    graph_features = pd.read_csv(graph_features_path) if graph_features_path and Path(graph_features_path).exists() else pd.DataFrame()
    if not graph_features.empty:
        feature = feature.merge(graph_features, on="canonical_food_id", how="left")
    chemical_features_path = REFERENCE / "canonical_food_chemical_features.csv"
    disease_pathway_path = REFERENCE / "canonical_food_disease_pathway_features.csv"
    if chemical_features_path.exists():
        chemical_features = pd.read_csv(chemical_features_path)
        chemical_features = chemical_features[
            ["canonical_food_id"]
            + [col for col in chemical_features.columns if col not in set(feature.columns) and col != "canonical_food_id"]
        ]
        feature = feature.merge(
            chemical_features.drop(columns=["canonical_name"], errors="ignore"),
            on="canonical_food_id",
            how="left",
        )
    if disease_pathway_path.exists():
        disease_pathway = pd.read_csv(disease_pathway_path)
        disease_pathway = disease_pathway[
            ["canonical_food_id"]
            + [col for col in disease_pathway.columns if col not in set(feature.columns) and col != "canonical_food_id"]
        ]
        feature = feature.merge(
            disease_pathway.drop(columns=["canonical_name", "canonical_category"], errors="ignore"),
            on="canonical_food_id",
            how="left",
        )
    for col in [
        "foodatlas_compound_count",
        "foodatlas_food_count",
        "foodatlas_disease_edge_count",
        "foodatlas_positive_disease_edge_count",
        "foodatlas_negative_disease_edge_count",
        "foodb_compound_count",
        "hmdb_metabolite_count",
        "hmdb_biospecimen_count",
        "hmdb_disease_count",
        "hmdb_pathway_count",
    ]:
        if col in feature:
            feature[col] = feature[col].fillna(0).astype(int)
    feature_path = REFERENCE / "canonical_food_feature_matrix.csv"
    feature.to_csv(feature_path, index=False)
    summary = {
        "outputs": {
            "canonical_food_master": str(master_path),
            "canonical_food_nutrient_reference": str(nutrient_out),
            "canonical_food_processing_reference": str(processing_path),
            "canonical_food_compound_reference": str(compound_path) if compound_path else "",
            "canonical_food_graph_features": str(graph_features_path) if graph_features_path else "",
            "canonical_food_chemical_features": str(chemical_features_path) if chemical_features_path.exists() else "",
            "canonical_food_disease_pathway_features": str(disease_pathway_path) if disease_pathway_path.exists() else "",
            "canonical_food_feature_matrix": str(feature_path),
        },
        "canonical_food_count": int(canonical["canonical_food_id"].nunique()),
        "feature_matrix_shape": [int(feature.shape[0]), int(feature.shape[1])],
    }
    _write_json(REFERENCE / "reference_build_summary.json", summary)
    return summary


def build_layered_validation():
    validation_dir = OUT / "validation"
    validation_dir.mkdir(parents=True, exist_ok=True)
    summaries = []
    for path in [
        LAYERED / "layer1_nutrient_candidates.csv",
        LAYERED / "layer2_openfoodfacts_candidates.csv",
    ]:
        if not path.exists():
            continue
        df = pd.read_csv(path)
        if df.empty:
            continue
        top = _top_by_id(df, "canonical_food_id")
        summaries.append(
            {
                "mapping_layer": df["source_layer"].iloc[0],
                "mapping_role": df["mapping_role"].iloc[0],
                "canonical_food_count": int(top["canonical_food_id"].nunique()),
                "candidate_rows": int(df.shape[0]),
                "high_confidence_percent": round(100 * (top["confidence"] == "high").mean(), 3),
                "high_or_medium_percent": round(100 * top["confidence"].isin(["high", "medium"]).mean(), 3),
                "review_or_low_percent": round(100 * top["confidence"].isin(["review", "low"]).mean(), 3),
                "mean_best_score": round(pd.to_numeric(top["match_score"], errors="coerce").mean(), 4),
            }
        )
    queue = pd.read_csv(LAYERED / "hitl_review_queue.csv") if (LAYERED / "hitl_review_queue.csv").exists() else pd.DataFrame()
    pd.DataFrame(summaries).to_csv(validation_dir / "layered_mapping_validation_summary.csv", index=False)
    if not queue.empty:
        queue_summary = pd.DataFrame(
            [
                {"metric": "canonical_foods", "value": int(queue.shape[0])},
                {"metric": "pending_hitl_review", "value": int((queue["review_status"] == "pending").sum())},
                {"metric": "auto_accept_role_mappings", "value": int((queue["review_status"] == "auto_accept").sum())},
                {
                    "metric": "pending_underlying_hpp_food_ids",
                    "value": int(
                        pd.to_numeric(
                            queue.loc[queue["review_status"].eq("pending"), "hpp_item_count"],
                            errors="coerce",
                        ).fillna(0).sum()
                    ),
                },
                {
                    "metric": "pending_total_loggings",
                    "value": int(
                        pd.to_numeric(
                            queue.loc[queue["review_status"].eq("pending"), "total_loggings"],
                            errors="coerce",
                        ).fillna(0).sum()
                    ),
                },
                {
                    "metric": "potential_branded_or_packaged",
                    "value": int((queue["suggested_identity_type"] == "branded_or_packaged").sum()),
                },
            ]
        )
        queue_summary.to_csv(validation_dir / "layered_hitl_validation_summary.csv", index=False)
        tier_summary = (
            queue[queue["review_status"].eq("pending")]
            .groupby(["usage_tier", "nutrient_confidence"], as_index=False)
            .agg(
                canonical_food_count=("canonical_food_id", "nunique"),
                hpp_item_count=("hpp_item_count", lambda value: int(pd.to_numeric(value, errors="coerce").fillna(0).sum())),
                total_loggings=("total_loggings", lambda value: int(pd.to_numeric(value, errors="coerce").fillna(0).sum())),
            )
        )
        tier_summary.to_csv(validation_dir / "layered_hitl_tier_summary.csv", index=False)
    return validation_dir / "layered_mapping_validation_summary.csv"


def run_layered_all():
    canonical_summary = run_canonical_pipeline()
    layer1_candidates, layer1_summary = build_layer1_candidates()
    layer2_candidates, layer2_summary = build_layer2_candidates()
    queue, queue_summary = build_hitl_queue()
    reference_summary = build_reference_tables()
    validation_path = build_layered_validation()
    summary = {
        "canonical": canonical_summary,
        "layer1": layer1_summary,
        "layer2": layer2_summary,
        "hitl": queue_summary,
        "reference": reference_summary,
        "validation": str(validation_path),
        "important_note": (
            "Layer 1 and Layer 2 candidates are generated before HITL. HITL decisions "
            "should accept role-specific mappings rather than one universal best match."
        ),
    }
    _write_json(LAYERED / "layered_pipeline_summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=[
            "layer1",
            "layer2",
            "hitl-queue",
            "reference",
            "validation",
            "all",
        ],
    )
    args = parser.parse_args()
    if args.command == "layer1":
        print(json.dumps(build_layer1_candidates()[1], indent=2))
    elif args.command == "layer2":
        print(json.dumps(build_layer2_candidates()[1], indent=2))
    elif args.command == "hitl-queue":
        print(json.dumps(build_hitl_queue()[1], indent=2))
    elif args.command == "reference":
        print(json.dumps(build_reference_tables(), indent=2))
    elif args.command == "validation":
        print(build_layered_validation())
    elif args.command == "all":
        print(json.dumps(run_layered_all(), indent=2))


if __name__ == "__main__":
    main()
