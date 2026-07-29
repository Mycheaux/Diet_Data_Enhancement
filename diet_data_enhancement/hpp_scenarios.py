import hashlib
import getpass
import json
import os
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from .nutrimatch_comparison import NUTRIMATCH_PARQUET, nutrimatch_hpp_with_ids
from .sources import ROOT


OUT = ROOT / "outputs"
SCENARIO_ROOT = OUT / "enhanced_hpp"
DEFAULT_SENTENCE_EMBEDDING_MODEL = os.getenv("OPENAI_FOOD_CONCEPT_EMBEDDING_MODEL", "text-embedding-3-large")

SCENARIOS = {
    "1.denovo": {
        "label": "de_novo",
        "description": (
            "HPP-level nutrient table built from the local de novo pipeline. "
            "For each HPP food and nutrient, observed HPP values are used first; "
            "mapped public-source values are used only where HPP is missing."
        ),
    },
    "2.nutrimatch_based": {
        "label": "nutrimatch_based",
        "description": (
            "HPP-level nutrient table read directly from the NutriMatch-derived "
            "HPP stratum. Values are interpreted as per 100 g food-reference values."
        ),
    },
    "3.nutrimatch_enhanced": {
        "label": "nutrimatch_enhanced",
        "description": (
            "Hybrid HPP-level nutrient table. De novo values are used first; "
            "NutriMatch HPP values fill missing de novo values when available."
        ),
    },
}

ACTIVE_COMPARISON_SCENARIOS = ["1.denovo", "2.nutrimatch_based"]

IDENTITY_COLS = [
    "hpp_food_id",
    "hpp_food_name",
    "hpp_product_name",
    "hpp_short_description",
    "hpp_hebrew_name",
    "hpp_category",
    "number_loggings",
    "canonical_food_id",
    "canonical_name",
    "canonical_category",
    "canonical_assignment_method",
]


def _write_json(path, payload):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload, indent=2))


def _load_identity():
    hpp = pd.read_csv(
        ROOT / "data/HPP/hpp_food_items_with_nutrients.csv",
        dtype={"food_id": str},
        usecols=[
            "food_id",
            "gpt_short_food_name",
            "product_name",
            "short_description",
            "hebrew_name",
            "category_hint",
            "number_loggings",
        ],
    ).rename(
        columns={
            "food_id": "hpp_food_id",
            "gpt_short_food_name": "hpp_food_name",
            "product_name": "hpp_product_name",
            "short_description": "hpp_short_description",
            "hebrew_name": "hpp_hebrew_name",
            "category_hint": "hpp_category",
        }
    )
    crosswalk = pd.read_csv(OUT / "canonical/hpp_to_canonical.csv", dtype={"hpp_food_id": str})
    crosswalk = crosswalk[
        [
            "hpp_food_id",
            "canonical_food_id",
            "canonical_name",
            "canonical_category",
            "canonical_assignment_method",
        ]
    ]
    return hpp.merge(crosswalk, on="hpp_food_id", how="left")


def _load_denovo_nutrients():
    harmonized = pd.read_csv(OUT / "nutrients/hpp_nutrient_harmonized.csv", dtype={"hpp_food_id": str})
    hpp_cols = [col for col in harmonized.columns if col.startswith("hpp__")]
    mapped_cols = [col for col in harmonized.columns if col.startswith("mapped__")]
    nutrient_names = sorted(
        {col.removeprefix("hpp__") for col in hpp_cols}
        | {col.removeprefix("mapped__") for col in mapped_cols}
    )
    value_cols = {"hpp_food_id": harmonized["hpp_food_id"]}
    source_rows = []
    for nutrient in nutrient_names:
        hpp_col = f"hpp__{nutrient}"
        mapped_col = f"mapped__{nutrient}"
        hpp_value = pd.to_numeric(harmonized[hpp_col], errors="coerce") if hpp_col in harmonized else pd.Series(pd.NA, index=harmonized.index)
        mapped_value = (
            pd.to_numeric(harmonized[mapped_col], errors="coerce")
            if mapped_col in harmonized
            else pd.Series(pd.NA, index=harmonized.index)
        )
        value_cols[nutrient] = hpp_value.where(hpp_value.notna(), mapped_value)
        source = pd.Series("missing", index=harmonized.index)
        source = source.where(hpp_value.isna(), "hpp_observed")
        source = source.where(~(hpp_value.isna() & mapped_value.notna()), "de_novo_public_mapping")
        source_rows.append(pd.DataFrame({"hpp_food_id": harmonized["hpp_food_id"], "nutrient_name": nutrient, "nutrient_source": source}))
    out = pd.DataFrame(value_cols)
    provenance = pd.concat(source_rows, ignore_index=True)
    return out, provenance


def _load_nutrimatch_hpp_nutrients():
    if not NUTRIMATCH_PARQUET.exists():
        raise FileNotFoundError(NUTRIMATCH_PARQUET)
    nm = nutrimatch_hpp_with_ids()
    meta_cols = {"hebrew_name", "hpp_food_id", "number_loggings"}
    nutrient_cols = [col for col in nm.columns if col not in meta_cols]
    out = nm[["hpp_food_id"] + nutrient_cols].copy()
    out["hpp_food_id"] = out["hpp_food_id"].astype(str)
    provenance = out[["hpp_food_id"]].copy()
    provenance_rows = []
    for nutrient in nutrient_cols:
        values = pd.to_numeric(out[nutrient], errors="coerce")
        source = pd.Series("missing", index=out.index)
        source = source.where(values.isna(), "nutrimatch_hpp_panel")
        provenance_rows.append(pd.DataFrame({"hpp_food_id": out["hpp_food_id"], "nutrient_name": nutrient, "nutrient_source": source}))
    return out, pd.concat(provenance_rows, ignore_index=True)


def _load_canonical_non_nutrient_features(nutrient_names):
    feature_path = OUT / "reference/canonical_food_feature_matrix.csv"
    if not feature_path.exists():
        return pd.DataFrame(columns=["canonical_food_id"])
    feature = pd.read_csv(feature_path)
    helper_cols = {"canonical_name", "canonical_category", "hpp_food_count"}
    drop_cols = set(nutrient_names) | helper_cols
    keep_cols = ["canonical_food_id"] + [col for col in feature.columns if col not in drop_cols and col != "canonical_food_id"]
    non_nutrient = feature[keep_cols].copy()
    rename = {col: f"canonical_inherited__{col}" for col in non_nutrient.columns if col != "canonical_food_id"}
    return non_nutrient.rename(columns=rename)


def _build_feature_schema(feature, nutrient_cols, scenario_label):
    rows = []
    identity = set(IDENTITY_COLS)
    for col in feature.columns:
        if col in identity:
            group = "identity"
            scalable = False
            transform = "join key or descriptor"
            origin = "hpp_food_id_or_canonical_helper"
        elif col in nutrient_cols:
            group = "nutrient_per_100g"
            scalable = True
            transform = "diet_event_value = reference_per_100g * grams_consumed / 100"
            origin = scenario_label
        elif col.startswith("canonical_inherited__openfoodfacts") or col.startswith("canonical_inherited__nova") or col.startswith("canonical_inherited__nutriscore"):
            group = "product_processing"
            scalable = False
            transform = "categorical or per-product descriptor; use as event indicator unless converted separately"
            origin = "canonical_helper_inherited"
        elif "compound" in col or "chemical" in col:
            group = "food_chemical_annotation"
            scalable = False
            transform = "annotation/count feature; dose scaling requires compound amount data not yet available"
            origin = "canonical_helper_inherited"
        elif "hmdb" in col or "disease" in col or "pathway" in col:
            group = "metabolomics_disease_pathway_annotation"
            scalable = False
            transform = "graph annotation/count feature; use as event exposure flag or graph neighborhood feature"
            origin = "canonical_helper_inherited"
        else:
            group = "other_reference_feature"
            scalable = False
            transform = "scenario-specific descriptor"
            origin = "canonical_helper_inherited"
        rows.append(
            {
                "feature_name": col,
                "feature_group": group,
                "mapping_origin": origin,
                "per_100g_scalable": scalable,
                "recommended_diet_event_transform": transform,
            }
        )
    return pd.DataFrame(rows)


def _summarize_matrix(feature, nutrient_cols, scenario_name, scenario_label):
    nutrient = feature[nutrient_cols] if nutrient_cols else pd.DataFrame(index=feature.index)
    non_null = nutrient.notna().sum().sum() if not nutrient.empty else 0
    return {
        "scenario_folder": scenario_name,
        "scenario_label": scenario_label,
        "hpp_food_rows": int(feature["hpp_food_id"].nunique()),
        "canonical_helper_foods": int(feature["canonical_food_id"].nunique()),
        "feature_matrix_shape": [int(feature.shape[0]), int(feature.shape[1])],
        "nutrient_columns": int(len(nutrient_cols)),
        "nutrient_non_null_cells": int(non_null),
        "nutrient_non_null_percent": round(float(100 * nutrient.notna().to_numpy().mean()), 3) if nutrient_cols else 0.0,
        "median_non_null_nutrients_per_hpp_food": float(nutrient.notna().sum(axis=1).median()) if nutrient_cols else 0.0,
        "per_100g_note": "Nutrient values are reference amounts per 100 g food unless a source-specific unit exception is documented.",
        "diet_event_scaling": "For TRE diet events: nutrient_amount = reference_per_100g * consumed_grams / 100.",
    }


def _scenario_dir(scenario_name):
    return SCENARIO_ROOT / scenario_name


def _scenario_feature_path(scenario_name):
    return _scenario_dir(scenario_name) / "hpp_feature_matrix_per_100g.csv"


def _identity_columns_in(df):
    return [col for col in IDENTITY_COLS if col in df.columns]


def _read_feature_schema(scenario_name):
    return pd.read_csv(_scenario_dir(scenario_name) / "feature_schema.csv")


def _scenario_nutrient_cols(scenario_name, feature):
    schema_path = _scenario_dir(scenario_name) / "feature_schema.csv"
    if schema_path.exists():
        schema = pd.read_csv(schema_path)
        names = set(schema.loc[schema["feature_group"].eq("nutrient_per_100g"), "feature_name"].astype(str))
        return [col for col in feature.columns if col in names]
    meta = set(IDENTITY_COLS)
    return [col for col in feature.columns if col not in meta and not col.startswith("canonical_inherited__")]


def _select_columns(feature, tokens):
    selected = []
    for col in feature.columns:
        low = col.lower()
        if any(token in low for token in tokens):
            selected.append(col)
    return selected


def _write_layer_table(feature, scenario_dir, filename, cols):
    cols = [col for col in cols if col in feature.columns]
    out = feature[_identity_columns_in(feature) + cols].copy()
    out.to_csv(scenario_dir / filename, index=False)
    return scenario_dir / filename, out.shape


def _tokenize(value):
    if value is None or pd.isna(value):
        return []
    tokens = []
    for raw in str(value).replace("|", " ").replace(",", " ").replace(":", " ").split():
        token = "".join(ch for ch in raw.lower() if ch.isalnum() or ch in {"-", "_"})
        if len(token) >= 3:
            tokens.append(token)
    return tokens


def _compact_list(value, limit=6):
    if value is None or pd.isna(value) or not str(value).strip():
        return []
    seen = []
    for chunk in str(value).replace(",", "|").split("|"):
        chunk = chunk.strip()
        if ":" in chunk:
            chunk = chunk.split(":", 1)[0].strip()
        if chunk and chunk not in seen:
            seen.append(chunk)
        if len(seen) >= limit:
            break
    return seen


def _nutrient_unit(nutrient):
    lowered = nutrient.lower()
    if nutrient == "Energy":
        return "kcal"
    if lowered in {
        "protein",
        "total lipid (fat)",
        "carbohydrate, by difference",
        "water",
        "fiber, total dietary",
        "sugars, total",
        "sugars, total including nlea",
        "starch",
        "fructose",
        "glucose",
        "sucrose",
        "lactose",
        "maltose",
        "galactose",
        "alcohol, ethyl",
        "ash",
    }:
        return "g"
    if lowered in {"caffeine", "theobromine"}:
        return "mg"
    if "vitamin a, iu" in lowered or "international units" in lowered:
        return "IU"
    if any(token in lowered for token in ["calcium", "iron", "magnesium", "phosphorus", "potassium", "sodium", "zinc", "copper", "selenium", "manganese", "fluoride"]):
        return "mg or source-native mineral unit"
    if any(token in lowered for token in ["vitamin", "folate", "carotene", "retinol", "tocopherol", "biotin", "iodine"]):
        return "source-native vitamin unit"
    return "g or source-native unit"


def _format_amount(value):
    value = float(value)
    if abs(value) >= 100:
        return f"{value:.0f}"
    if abs(value) >= 10:
        return f"{value:.1f}"
    if abs(value) >= 1:
        return f"{value:.2f}"
    return f"{value:.3g}"


def _priority_nutrient_phrases(row, nutrient_cols, limit=10):
    priority = [
        "Energy",
        "Protein",
        "Total lipid (fat)",
        "Carbohydrate, by difference",
        "Water",
        "Fiber, total dietary",
        "Sugars, Total",
        "Sugars, total including NLEA",
        "Sodium, Na",
        "Calcium, Ca",
        "Iron, Fe",
        "Potassium, K",
        "Caffeine",
    ]
    selected = []
    seen = set()
    for nutrient in priority + list(nutrient_cols):
        if nutrient in seen or nutrient not in nutrient_cols:
            continue
        seen.add(nutrient)
        value = pd.to_numeric(row.get(nutrient), errors="coerce")
        if pd.notna(value) and float(value) != 0:
            selected.append(f"{nutrient} {_format_amount(value)} {_nutrient_unit(nutrient)}")
        if len(selected) >= limit:
            break
    return selected


def _scenario_food_sentence(row, scenario_name, nutrient_cols):
    scenario_label = SCENARIOS[scenario_name]["label"]
    food_name = row.get("hpp_food_name", "")
    product_name = row.get("hpp_product_name", "")
    hebrew_name = row.get("hpp_hebrew_name", "")
    canonical_name = row.get("canonical_name", "")
    category = row.get("hpp_category", "")
    nutrients = _priority_nutrient_phrases(row, nutrient_cols, limit=10)
    product = row.get("canonical_inherited__openfoodfacts_product_name", "")
    nova = row.get("canonical_inherited__nova_group", "")
    nutriscore = row.get("canonical_inherited__nutriscore_grade", "")
    ingredients = row.get("canonical_inherited__ingredients_text", "")
    additives = row.get("canonical_inherited__additives_tags", "")
    classes = _compact_list(row.get("canonical_inherited__foodb_top_chemical_classes", ""), limit=8)
    superclasses = _compact_list(row.get("canonical_inherited__foodb_top_chemical_superclasses", ""), limit=6)
    biospecimens = _compact_list(row.get("canonical_inherited__hmdb_biospecimens", ""), limit=6)
    diseases = _compact_list(row.get("canonical_inherited__hmdb_top_diseases", ""), limit=8)
    pathways = _compact_list(row.get("canonical_inherited__hmdb_top_pathways", ""), limit=8)
    foodb_count = int(pd.to_numeric(row.get("canonical_inherited__foodb_compound_count", 0), errors="coerce") or 0)
    fa_compound_count = int(pd.to_numeric(row.get("canonical_inherited__foodatlas_compound_count", 0), errors="coerce") or 0)
    hmdb_count = int(pd.to_numeric(row.get("canonical_inherited__hmdb_metabolite_count", 0), errors="coerce") or 0)
    disease_count = int(pd.to_numeric(row.get("canonical_inherited__hmdb_disease_count", 0), errors="coerce") or 0)
    pathway_count = int(pd.to_numeric(row.get("canonical_inherited__hmdb_pathway_count", 0), errors="coerce") or 0)

    sentence = (
        f"Per 100 g reference for HPP food {row['hpp_food_id']} ({food_name}; Hebrew: {hebrew_name}) "
        f"in category {category}, using the {scenario_label} nutrient scenario. "
        f"The food is linked to canonical helper {row.get('canonical_food_id', '')} ({canonical_name}). "
    )
    if product_name and pd.notna(product_name):
        sentence += f"The original HPP product description is {product_name}. "
    if nutrients:
        sentence += "Per 100 g, it contains " + "; ".join(nutrients) + ". "
    else:
        sentence += "No numeric nutrient amounts are available in this scenario. "
    if product and pd.notna(product):
        sentence += f"Product/processing evidence maps to OpenFoodFacts product {product}. "
    if pd.notna(nova) and str(nova).strip() and str(nova).lower() not in {"nan", "unknown"}:
        sentence += f"The inherited NOVA processing group is {nova}. "
    if pd.notna(nutriscore) and str(nutriscore).strip() and str(nutriscore).lower() not in {"nan", "unknown"}:
        sentence += f"The inherited Nutri-Score grade is {nutriscore}. "
    if ingredients and pd.notna(ingredients):
        ingredient_text = str(ingredients).strip()
        if len(ingredient_text) > 260:
            ingredient_text = ingredient_text[:257].rstrip() + "..."
        sentence += f"Ingredient evidence includes {ingredient_text}. "
    if additives and pd.notna(additives):
        sentence += "Additive evidence includes " + ", ".join(_compact_list(additives, limit=8)) + ". "
    sentence += (
        f"Food chemical evidence links the helper food to {foodb_count} FooDB compounds "
        f"and {fa_compound_count} FoodAtlas compound nodes. "
    )
    if classes or superclasses:
        sentence += "Prominent chemical classes include " + ", ".join(classes + superclasses) + ". "
    sentence += f"HMDB bridging links this food concept to {hmdb_count} human metabolites"
    if biospecimens:
        sentence += " observed in " + ", ".join(biospecimens)
    sentence += ". "
    sentence += (
        f"The disease/pathway graph includes {disease_count} disease annotations and "
        f"{pathway_count} pathway annotations"
    )
    if diseases:
        sentence += ", including diseases such as " + ", ".join(diseases)
    if pathways:
        sentence += ", and pathways such as " + ", ".join(pathways)
    sentence += (
        ". Chemical, metabolite, disease, and pathway links are reference graph annotations "
        "for hypothesis generation, not causal estimates or measured post-ingestion amounts."
    )
    return sentence


def _numeric_block(feature, cols):
    cols = [col for col in cols if col in feature.columns]
    if not cols:
        return np.zeros((len(feature), 0)), []
    values = feature[cols].apply(pd.to_numeric, errors="coerce")
    values = values.fillna(values.median(numeric_only=True)).fillna(0)
    values = np.log1p(values.clip(lower=0))
    std = values.std(axis=0).replace(0, 1)
    values = ((values - values.mean(axis=0)) / std).to_numpy(dtype=float)
    return values / np.sqrt(max(values.shape[1], 1)), cols


def _hashed_text_block(feature, cols, dims=64):
    block = np.zeros((len(feature), dims), dtype=float)
    cols = [col for col in cols if col in feature.columns]
    for row_idx, (_, row) in enumerate(feature.iterrows()):
        counts = Counter()
        for col in cols:
            counts.update(_tokenize(row.get(col, "")))
        for token, count in counts.items():
            token_hash = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
            sign_hash = int(hashlib.md5(("salt:" + token).encode("utf-8")).hexdigest(), 16)
            block[row_idx, token_hash % dims] += (1 if sign_hash % 2 == 0 else -1) * np.log1p(count)
    if dims:
        std = block.std(axis=0)
        std[std == 0] = 1
        block = (block - block.mean(axis=0)) / std
        block = block / np.sqrt(dims)
    return block, [f"text_hash_{idx:02d}" for idx in range(dims)]


def _pca_projection(matrix, dims=2):
    if matrix.size == 0:
        return np.zeros((matrix.shape[0], dims))
    centered = matrix - matrix.mean(axis=0)
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    projection = centered @ vt[:dims].T
    if projection.shape[1] < dims:
        projection = np.pad(projection, ((0, 0), (0, dims - projection.shape[1])))
    return projection


def _kmeans(matrix, k=8, iterations=80):
    n = matrix.shape[0]
    if n == 0:
        return np.array([], dtype=int)
    k = max(1, min(k, n))
    order = np.argsort(np.linalg.norm(matrix, axis=1))
    centroids = matrix[order[np.linspace(0, n - 1, k).astype(int)]].copy()
    labels = np.zeros(n, dtype=int)
    for _ in range(iterations):
        distances = ((matrix[:, None, :] - centroids[None, :, :]) ** 2).sum(axis=2)
        new_labels = distances.argmin(axis=1)
        if np.array_equal(new_labels, labels):
            break
        labels = new_labels
        for cluster in range(k):
            members = matrix[labels == cluster]
            if len(members):
                centroids[cluster] = members.mean(axis=0)
    return labels


def _build_hpp_multimodal_outputs(feature, scenario_name, scenario_dir, nutrient_cols):
    layer6 = scenario_dir / "layer6_multimodal_embeddings"
    layer7 = scenario_dir / "layer7_sentences_patterns"
    layer6.mkdir(exist_ok=True)
    layer7.mkdir(exist_ok=True)

    processing_cols = _select_columns(
        feature,
        [
            "openfoodfacts",
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
        ],
    )
    chemical_cols = _select_columns(feature, ["compound_count", "chemical", "foodb_top"])
    disease_cols = _select_columns(feature, ["hmdb_", "disease", "pathway", "biospecimen", "foodatlas_positive", "foodatlas_negative"])
    numeric_cols = []
    for cols in [nutrient_cols, processing_cols, chemical_cols, disease_cols]:
        for col in cols:
            converted = pd.to_numeric(feature[col], errors="coerce")
            if col not in numeric_cols and converted.notna().any():
                numeric_cols.append(col)
    text_cols = [
        col
        for col in feature.columns
        if col not in set(IDENTITY_COLS) | set(numeric_cols)
        and (feature[col].dtype == "object" or str(feature[col].dtype).startswith("string"))
    ]

    nutrient_block, nutrient_names = _numeric_block(feature, nutrient_cols)
    processing_block, processing_names = _numeric_block(feature, processing_cols)
    chemical_block, chemical_names = _numeric_block(feature, chemical_cols)
    disease_block, disease_names = _numeric_block(feature, disease_cols)
    text_block, text_names = _hashed_text_block(feature, text_cols)
    blocks = [
        ("nutrient", nutrient_block, nutrient_names),
        ("processing", processing_block, processing_names),
        ("chemical", chemical_block, chemical_names),
        ("metabolomics_disease_pathway", disease_block, disease_names),
        ("text_evidence", text_block, text_names),
    ]
    matrix = np.concatenate([block for _, block, _ in blocks if block.shape[1] > 0], axis=1)
    projection = _pca_projection(matrix, dims=2)
    labels = _kmeans(matrix, k=8)
    vector_cols = [f"v_{idx:04d}" for idx in range(matrix.shape[1])]
    vectors = pd.DataFrame(matrix, columns=vector_cols)
    vectors.insert(0, "cluster_id", labels)
    vectors.insert(0, "embedding_version", f"hpp_{SCENARIOS[scenario_name]['label']}_structured_v1")
    for col in reversed(_identity_columns_in(feature)):
        vectors.insert(0, col, feature[col].values)
    projection_df = feature[_identity_columns_in(feature)].copy()
    projection_df["x"] = projection[:, 0]
    projection_df["y"] = projection[:, 1]
    projection_df["cluster_id"] = labels
    dim_rows = []
    idx = 0
    for block_name, _, names in blocks:
        for name in names:
            dim_rows.append({"dimension": f"v_{idx:04d}", "feature_block": block_name, "feature_name": name})
            idx += 1

    vectors_path = layer6 / "hpp_multimodal_vectors.parquet"
    projection_path = layer6 / "hpp_embedding_projection.csv"
    dimensions_path = layer6 / "hpp_multimodal_vector_dimensions.csv"
    vectors.to_parquet(vectors_path, index=False)
    projection_df.to_csv(projection_path, index=False)
    pd.DataFrame(dim_rows).to_csv(dimensions_path, index=False)

    sentence_rows = []
    for _, row in feature.iterrows():
        nutrients = _priority_nutrient_phrases(row, nutrient_cols, limit=10)
        foodb_count = int(pd.to_numeric(row.get("canonical_inherited__foodb_compound_count", 0), errors="coerce") or 0)
        hmdb_count = int(pd.to_numeric(row.get("canonical_inherited__hmdb_metabolite_count", 0), errors="coerce") or 0)
        disease_count = int(pd.to_numeric(row.get("canonical_inherited__hmdb_disease_count", 0), errors="coerce") or 0)
        pathway_count = int(pd.to_numeric(row.get("canonical_inherited__hmdb_pathway_count", 0), errors="coerce") or 0)
        sentence = _scenario_food_sentence(row, scenario_name, nutrient_cols)
        sentence_rows.append(
            {
                "hpp_food_id": row["hpp_food_id"],
                "hpp_food_name": row.get("hpp_food_name", ""),
                "canonical_food_id": row.get("canonical_food_id", ""),
                "canonical_name": row.get("canonical_name", ""),
                "scenario": SCENARIOS[scenario_name]["label"],
                "concept_sentence": sentence,
                "nutrient_evidence_count": len(nutrients),
                "foodb_compound_count": foodb_count,
                "hmdb_metabolite_count": hmdb_count,
                "hmdb_disease_count": disease_count,
                "hmdb_pathway_count": pathway_count,
            }
        )
    sentences = pd.DataFrame(sentence_rows)
    sentences_path = layer7 / "hpp_food_concept_sentences.csv"
    sentences.to_csv(sentences_path, index=False)

    patterns = []
    joined = projection_df.merge(sentences[["hpp_food_id", "concept_sentence"]], on="hpp_food_id", how="left")
    text_lookup = feature.set_index("hpp_food_id", drop=False)
    for cluster_id, group in joined.groupby("cluster_id"):
        disease_counts = Counter()
        pathway_counts = Counter()
        for hpp_id in group["hpp_food_id"]:
            row = text_lookup.loc[hpp_id]
            disease_counts.update(_compact_list(row.get("canonical_inherited__hmdb_top_diseases", ""), limit=20))
            pathway_counts.update(_compact_list(row.get("canonical_inherited__hmdb_top_pathways", ""), limit=20))
        examples = group.sort_values("hpp_food_name")["hpp_food_name"].head(8).tolist()
        for label, count in disease_counts.most_common(12):
            patterns.append({"cluster_id": cluster_id, "association_type": "hmdb_disease", "label": label, "hpp_food_count_in_cluster": int(len(group)), "label_count_in_cluster": int(count), "example_hpp_foods": " | ".join(examples)})
        for label, count in pathway_counts.most_common(12):
            patterns.append({"cluster_id": cluster_id, "association_type": "hmdb_pathway", "label": label, "hpp_food_count_in_cluster": int(len(group)), "label_count_in_cluster": int(count), "example_hpp_foods": " | ".join(examples)})
    patterns_path = layer7 / "hpp_food_disease_pattern_discovery.csv"
    pd.DataFrame(patterns).to_csv(patterns_path, index=False)

    return {
        "vectors": str(vectors_path),
        "projection": str(projection_path),
        "dimensions": str(dimensions_path),
        "sentences": str(sentences_path),
        "patterns": str(patterns_path),
        "vector_shape": [int(vectors.shape[0]), int(vectors.shape[1])],
        "cluster_count": int(pd.Series(labels).nunique()),
        "block_dimensions": {
            "nutrient": int(nutrient_block.shape[1]),
            "processing": int(processing_block.shape[1]),
            "chemical": int(chemical_block.shape[1]),
            "metabolomics_disease_pathway": int(disease_block.shape[1]),
            "text_evidence": int(text_block.shape[1]),
        },
    }


def _add_node(nodes, kind, node_id, label, **attrs):
    key = f"{kind}:{node_id}"
    if key not in nodes:
        nodes[key] = {"key": key, "kind": kind, "id": str(node_id), "label": str(label), **attrs}
    return key


def _build_hpp_scenario_kg(feature, scenario_name, scenario_dir, nutrient_cols):
    kg_dir = scenario_dir / "kg"
    kg_dir.mkdir(exist_ok=True)
    nodes = {}
    edge_rows = []
    scenario_label = SCENARIOS[scenario_name]["label"]
    nutrient_node = {}
    for nutrient in nutrient_cols:
        nutrient_node[nutrient] = _add_node(nodes, "nutrient", nutrient, nutrient, unit_basis="per_100g_food_reference")

    for _, row in feature.iterrows():
        hpp_key = _add_node(
            nodes,
            "hpp_food",
            row["hpp_food_id"],
            row.get("hpp_food_name", row["hpp_food_id"]),
            hebrew_name=row.get("hpp_hebrew_name", ""),
            category=row.get("hpp_category", ""),
            scenario=scenario_label,
        )
        canonical_key = _add_node(
            nodes,
            "canonical_food",
            row.get("canonical_food_id", ""),
            row.get("canonical_name", row.get("canonical_food_id", "")),
            category=row.get("canonical_category", ""),
        )
        edge_rows.append({"source": hpp_key, "target": canonical_key, "relation": "has_canonical_helper", "scenario": scenario_label, "mapping_mode": "canonical_helper"})
        for nutrient in nutrient_cols:
            value = pd.to_numeric(row.get(nutrient), errors="coerce")
            if pd.notna(value):
                edge_rows.append(
                    {
                        "source": hpp_key,
                        "target": nutrient_node[nutrient],
                        "relation": "has_nutrient_amount_per_100g",
                        "scenario": scenario_label,
                        "value": float(value),
                        "unit_basis": "per_100g_food_reference",
                    }
                )

        code = row.get("canonical_inherited__openfoodfacts_code", "")
        product_name = row.get("canonical_inherited__openfoodfacts_product_name", "")
        if pd.notna(code) and str(code).strip() and str(code).lower() != "nan":
            product_key = _add_node(nodes, "openfoodfacts_product", code, product_name if pd.notna(product_name) else code)
            edge_rows.append(
                {
                    "source": hpp_key,
                    "target": product_key,
                    "relation": "inherits_product_processing_match",
                    "scenario": scenario_label,
                    "mapping_mode": "canonical_inherited",
                    "score": row.get("canonical_inherited__openfoodfacts_match_score", ""),
                    "confidence": row.get("canonical_inherited__openfoodfacts_confidence", ""),
                }
            )
        for value, kind, relation in [
            (row.get("canonical_inherited__nutriscore_grade", ""), "nutriscore_grade", "has_nutriscore_grade"),
            (row.get("canonical_inherited__nova_group", ""), "nova_group", "has_nova_group"),
        ]:
            if pd.notna(value) and str(value).strip() and str(value).lower() not in {"nan", "unknown"}:
                target = _add_node(nodes, kind, value, value)
                edge_rows.append({"source": hpp_key, "target": target, "relation": relation, "scenario": scenario_label, "mapping_mode": "canonical_inherited"})

        for col, kind, relation in [
            ("canonical_inherited__foodb_top_chemical_classes", "chemical_class", "linked_to_foodb_chemical_class"),
            ("canonical_inherited__foodb_top_chemical_superclasses", "chemical_superclass", "linked_to_foodb_chemical_superclass"),
            ("canonical_inherited__hmdb_biospecimens", "hmdb_biospecimen", "linked_to_hmdb_biospecimen"),
            ("canonical_inherited__hmdb_top_diseases", "disease", "linked_to_hmdb_disease_annotation"),
            ("canonical_inherited__hmdb_top_pathways", "pathway", "linked_to_hmdb_pathway_annotation"),
        ]:
            for item in _compact_list(row.get(col, ""), limit=10):
                target = _add_node(nodes, kind, item, item)
                edge_rows.append({"source": hpp_key, "target": target, "relation": relation, "scenario": scenario_label, "mapping_mode": "canonical_inherited"})

    nodes_df = pd.DataFrame(nodes.values())
    edges_df = pd.DataFrame(edge_rows)
    nodes_path = kg_dir / "hpp_scenario_kg_nodes.csv"
    edges_path = kg_dir / "hpp_scenario_kg_edges.csv"
    nodes_df.to_csv(nodes_path, index=False)
    edges_df.to_csv(edges_path, index=False)
    summary = {
        "scenario": scenario_label,
        "nodes": int(nodes_df.shape[0]),
        "edges": int(edges_df.shape[0]),
        "hpp_food_nodes": int((nodes_df["kind"] == "hpp_food").sum()),
        "nutrient_amount_edges": int((edges_df["relation"] == "has_nutrient_amount_per_100g").sum()),
        "outputs": {"nodes": str(nodes_path), "edges": str(edges_path)},
        "design_note": "Nutrient amount edges are scenario-specific; Layer 2-5 annotations are inherited through canonical helper evidence unless HPP-specific overrides are later added.",
    }
    _write_json(kg_dir / "hpp_scenario_kg_summary.json", summary)
    return summary


def _openai_client(force_prompt=True):
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ImportError("Install the openai package in the active environment first.") from exc
    api_key = "" if force_prompt else os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        api_key = getpass.getpass("Paste OpenAI API key for this run only. It will not be saved: ").strip()
    if not api_key:
        raise RuntimeError("No OpenAI API key provided; LLM sentence embeddings were not run.")
    return OpenAI(api_key=api_key)


def _embed_texts_openai(texts, model, batch_size, force_prompt=True):
    client = _openai_client(force_prompt=force_prompt)
    vectors = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        response = client.embeddings.create(model=model, input=batch)
        vectors.extend([item.embedding for item in response.data])
    return np.array(vectors, dtype=np.float32)


def build_hpp_llm_sentence_embeddings(
    model=DEFAULT_SENTENCE_EMBEDDING_MODEL,
    batch_size=64,
    force_prompt=True,
):
    """Embed deterministic HPP food concept sentences for active scenarios."""
    if not (SCENARIO_ROOT / "denovo_vs_nutrimatch_layer2_to_7_summary.json").exists():
        build_hpp_comparison_layers()
    client_vectors = {}
    payload = {
        "embedding_model": model,
        "active_scenarios": ACTIVE_COMPARISON_SCENARIOS,
        "scenarios": {},
        "api_key_policy": "Prompted in terminal for this run only; not saved.",
    }
    client = None
    for scenario_name in ACTIVE_COMPARISON_SCENARIOS:
        scenario_dir = _scenario_dir(scenario_name)
        layer7 = scenario_dir / "layer7_sentences_patterns"
        sentence_path = layer7 / "hpp_food_concept_sentences.csv"
        if not sentence_path.exists():
            build_hpp_comparison_layers()
        sentences = pd.read_csv(sentence_path, dtype={"hpp_food_id": str})
        texts = sentences["concept_sentence"].fillna("").astype(str).tolist()
        if client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise ImportError("Install the openai package in the active environment first.") from exc
            api_key = "" if force_prompt else os.getenv("OPENAI_API_KEY", "")
            if not api_key:
                api_key = getpass.getpass("Paste OpenAI API key for this run only. It will not be saved: ").strip()
            if not api_key:
                raise RuntimeError("No OpenAI API key provided; LLM sentence embeddings were not run.")
            client = OpenAI(api_key=api_key)
        vectors = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            response = client.embeddings.create(model=model, input=batch)
            vectors.extend([item.embedding for item in response.data])
        matrix = np.array(vectors, dtype=np.float32)
        projection = _pca_projection(matrix, dims=2)
        labels = _kmeans(matrix, k=8)
        vector_cols = [f"e_{idx:04d}" for idx in range(matrix.shape[1])]
        out = pd.DataFrame(matrix, columns=vector_cols)
        out.insert(0, "cluster_id", labels)
        out.insert(0, "embedding_model", model)
        for col in reversed(["scenario", "canonical_name", "canonical_food_id", "hpp_food_name", "hpp_food_id"]):
            if col in sentences:
                out.insert(0, col, sentences[col].values)
        projection_df = sentences[["hpp_food_id", "hpp_food_name", "canonical_food_id", "canonical_name", "scenario"]].copy()
        projection_df["x"] = projection[:, 0]
        projection_df["y"] = projection[:, 1]
        projection_df["cluster_id"] = labels
        projection_df["embedding_model"] = model
        llm_dir = scenario_dir / "layer7_llm_sentence_embeddings"
        llm_dir.mkdir(exist_ok=True)
        vectors_path = llm_dir / "hpp_food_sentence_embeddings.parquet"
        projection_path = llm_dir / "hpp_food_sentence_embedding_projection.csv"
        out.to_parquet(vectors_path, index=False)
        projection_df.to_csv(projection_path, index=False)
        summary = {
            "scenario": SCENARIOS[scenario_name]["label"],
            "hpp_food_count": int(sentences["hpp_food_id"].nunique()),
            "embedding_model": model,
            "embedding_dimension_count": int(matrix.shape[1]),
            "cluster_count": int(pd.Series(labels).nunique()),
            "outputs": {
                "vectors": str(vectors_path),
                "projection": str(projection_path),
                "sentences": str(sentence_path),
            },
        }
        _write_json(llm_dir / "hpp_food_sentence_embedding_summary.json", summary)
        payload["scenarios"][scenario_name] = summary
        client_vectors[scenario_name] = str(vectors_path)
    _write_json(SCENARIO_ROOT / "denovo_vs_nutrimatch_llm_sentence_embedding_summary.json", payload)
    return payload


def build_hpp_comparison_layers():
    """Build Layer 2-7 and KG outputs for de novo vs NutriMatch-based scenarios."""
    if not _scenario_feature_path("1.denovo").exists() or not _scenario_feature_path("2.nutrimatch_based").exists():
        build_hpp_enhancement_scenarios()
    payload = {"scenarios": {}, "active_scenarios": ACTIVE_COMPARISON_SCENARIOS}
    for scenario_name in ACTIVE_COMPARISON_SCENARIOS:
        scenario_dir = _scenario_dir(scenario_name)
        feature = pd.read_csv(_scenario_feature_path(scenario_name), dtype={"hpp_food_id": str})
        nutrient_cols = _scenario_nutrient_cols(scenario_name, feature)
        layer_dir = scenario_dir / "layer_tables"
        layer_dir.mkdir(exist_ok=True)
        layer_outputs = {}
        layer2_cols = _select_columns(
            feature,
            [
                "openfoodfacts",
                "brands",
                "countries_en",
                "ingredients",
                "additives",
                "allergens",
                "labels",
                "nutriscore",
                "nova",
                "pnns",
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
            ],
        )
        layer3_cols = _select_columns(feature, ["foodatlas_compound", "foodatlas_food_count", "foodb_compound", "foodb_top_chemical", "annotation_quality"])
        layer4_cols = _select_columns(feature, ["hmdb_metabolite", "hmdb_biospecimen", "hmdb_biospecimens"])
        layer5_cols = _select_columns(feature, ["disease", "pathway", "foodatlas_positive", "foodatlas_negative"])
        for filename, cols in [
            ("layer2_product_processing_reference.csv", layer2_cols),
            ("layer3_food_chemical_reference.csv", layer3_cols),
            ("layer4_human_metabolomics_reference.csv", layer4_cols),
            ("layer5_disease_pathway_reference.csv", layer5_cols),
        ]:
            path, shape = _write_layer_table(feature, layer_dir, filename, cols)
            layer_outputs[filename] = {"path": str(path), "shape": [int(shape[0]), int(shape[1])]}
        embedding_summary = _build_hpp_multimodal_outputs(feature, scenario_name, scenario_dir, nutrient_cols)
        kg_summary = _build_hpp_scenario_kg(feature, scenario_name, scenario_dir, nutrient_cols)
        summary = {
            "scenario_label": SCENARIOS[scenario_name]["label"],
            "hpp_food_rows": int(feature["hpp_food_id"].nunique()),
            "nutrient_columns": int(len(nutrient_cols)),
            "layer_tables": layer_outputs,
            "layer6": embedding_summary,
            "kg": kg_summary,
        }
        _write_json(scenario_dir / "hpp_layers_2_to_7_summary.json", summary)
        payload["scenarios"][scenario_name] = summary
    _write_json(SCENARIO_ROOT / "denovo_vs_nutrimatch_layer2_to_7_summary.json", payload)
    return payload


def _write_scenario_readme(path, scenario_name, summary):
    text = f"""# {scenario_name}

{SCENARIOS[scenario_name]["description"]}

## Unit Of Analysis

Each row is one original HPP `food_id`. The `canonical_food_id` is retained as a
helper identifier so that repeated or near-duplicate HPP foods can inherit
shared product, chemical, HMDB, disease, pathway, KG, and embedding evidence
when an HPP-specific override is not yet available.

## Per 100 g Reference

Nutrient columns are interpreted as food-reference values per 100 g. Inside the
TRE, participant diet events should be assembled as:

```text
event_amount = reference_per_100g * grams_consumed / 100
```

For liquids, a density rule must be chosen inside the TRE or in a later
preprocessing step. A water-like default of 1 ml approximately equal to 1 g can
be used only with explicit provenance.

## Outputs

- `hpp_nutrient_reference_per_100g.csv`: HPP-level nutrient matrix only.
- `hpp_feature_matrix_per_100g.csv`: HPP-level nutrient matrix plus inherited
  product, chemical, HMDB, disease, pathway, and KG features.
- `hpp_nutrient_provenance_long.csv.gz`: long nutrient-source provenance.
- `feature_schema.csv`: feature groups and recommended diet-event transform.
- `scenario_summary.json`: compact coverage summary.

## Summary

```json
{json.dumps(summary, indent=2)}
```
"""
    path.write_text(text)


def build_hpp_enhancement_scenarios():
    SCENARIO_ROOT.mkdir(parents=True, exist_ok=True)
    identity = _load_identity()
    denovo, denovo_prov = _load_denovo_nutrients()
    nutrimatch, nutrimatch_prov = _load_nutrimatch_hpp_nutrients()

    denovo_nutrients = [col for col in denovo.columns if col != "hpp_food_id"]
    nm_nutrients = [col for col in nutrimatch.columns if col != "hpp_food_id"]
    hybrid_nutrients = sorted(set(denovo_nutrients) | set(nm_nutrients))

    denovo_aligned = denovo[["hpp_food_id"] + denovo_nutrients].copy()
    nm_aligned = nutrimatch[["hpp_food_id"] + nm_nutrients].copy()
    denovo_idx = denovo.set_index("hpp_food_id", drop=False)
    nm_idx = nutrimatch.set_index("hpp_food_id", drop=False)
    hybrid = denovo[["hpp_food_id"]].copy()
    hybrid_cols = {"hpp_food_id": hybrid["hpp_food_id"]}
    hybrid_prov_rows = []
    for nutrient in hybrid_nutrients:
        denovo_value = (
            pd.to_numeric(denovo_idx.reindex(hybrid["hpp_food_id"])[nutrient].reset_index(drop=True), errors="coerce")
            if nutrient in denovo_nutrients
            else pd.Series(pd.NA, index=hybrid.index)
        )
        nm_value = (
            pd.to_numeric(nm_idx.reindex(hybrid["hpp_food_id"])[nutrient].reset_index(drop=True), errors="coerce")
            if nutrient in nm_nutrients
            else pd.Series(pd.NA, index=hybrid.index)
        )
        hybrid_cols[nutrient] = denovo_value.where(denovo_value.notna(), nm_value)
        source = pd.Series("missing", index=hybrid.index)
        source = source.where(nm_value.isna(), "nutrimatch_fill")
        source = source.where(denovo_value.isna(), "de_novo_primary")
        hybrid_prov_rows.append(pd.DataFrame({"hpp_food_id": hybrid["hpp_food_id"], "nutrient_name": nutrient, "nutrient_source": source}))
    hybrid_out = pd.DataFrame(hybrid_cols)
    hybrid_prov = pd.concat(hybrid_prov_rows, ignore_index=True)

    scenario_data = {
        "1.denovo": (denovo_aligned, denovo_prov),
        "2.nutrimatch_based": (nm_aligned, nutrimatch_prov),
        "3.nutrimatch_enhanced": (hybrid_out, hybrid_prov),
    }

    all_nutrient_names = sorted(set(denovo_nutrients) | set(nm_nutrients))
    non_nutrient = _load_canonical_non_nutrient_features(all_nutrient_names)
    summaries = {}
    for scenario_name, (nutrients, provenance) in scenario_data.items():
        scenario_dir = SCENARIO_ROOT / scenario_name
        scenario_dir.mkdir(parents=True, exist_ok=True)
        nutrient_cols = [col for col in nutrients.columns if col != "hpp_food_id"]
        nutrient_ref = identity.merge(nutrients, on="hpp_food_id", how="left")
        feature = nutrient_ref.merge(non_nutrient, on="canonical_food_id", how="left")

        scenario_label = SCENARIOS[scenario_name]["label"]
        provenance = provenance.copy()
        provenance["scenario"] = scenario_label
        provenance["unit_basis"] = "per_100g_food_reference"
        provenance["diet_event_scaling"] = "reference_per_100g_times_grams_consumed_divided_by_100"

        schema = _build_feature_schema(feature, nutrient_cols, scenario_label)
        summary = _summarize_matrix(feature, nutrient_cols, scenario_name, scenario_label)
        summary["description"] = SCENARIOS[scenario_name]["description"]
        summary["outputs"] = {
            "hpp_nutrient_reference_per_100g": str(scenario_dir / "hpp_nutrient_reference_per_100g.csv"),
            "hpp_feature_matrix_per_100g": str(scenario_dir / "hpp_feature_matrix_per_100g.csv"),
            "hpp_nutrient_provenance_long": str(scenario_dir / "hpp_nutrient_provenance_long.csv.gz"),
            "feature_schema": str(scenario_dir / "feature_schema.csv"),
            "scenario_summary": str(scenario_dir / "scenario_summary.json"),
            "readme": str(scenario_dir / "README.md"),
        }

        nutrient_ref.to_csv(scenario_dir / "hpp_nutrient_reference_per_100g.csv", index=False)
        feature.to_csv(scenario_dir / "hpp_feature_matrix_per_100g.csv", index=False)
        provenance.to_csv(scenario_dir / "hpp_nutrient_provenance_long.csv.gz", index=False, compression="gzip")
        schema.to_csv(scenario_dir / "feature_schema.csv", index=False)
        _write_json(scenario_dir / "scenario_summary.json", summary)
        _write_scenario_readme(scenario_dir / "README.md", scenario_name, summary)
        summaries[scenario_name] = summary

    comparison = pd.DataFrame(
        [
            {
                "scenario": name,
                "hpp_food_rows": summary["hpp_food_rows"],
                "feature_columns": summary["feature_matrix_shape"][1],
                "nutrient_columns": summary["nutrient_columns"],
                "nutrient_non_null_percent": summary["nutrient_non_null_percent"],
                "median_non_null_nutrients_per_hpp_food": summary["median_non_null_nutrients_per_hpp_food"],
            }
            for name, summary in summaries.items()
        ]
    )
    comparison.to_csv(SCENARIO_ROOT / "scenario_comparison_summary.csv", index=False)
    payload = {
        "scenario_root": str(SCENARIO_ROOT),
        "scenarios": summaries,
        "comparison": str(SCENARIO_ROOT / "scenario_comparison_summary.csv"),
        "important_design_note": (
            "Final analysis unit is HPP food_id. canonical_food_id is retained as a helper "
            "for shared mappings and inherited non-nutrient evidence."
        ),
    }
    _write_json(SCENARIO_ROOT / "hpp_enhancement_scenarios_summary.json", payload)
    return payload


if __name__ == "__main__":
    print(json.dumps(build_hpp_enhancement_scenarios(), indent=2))
