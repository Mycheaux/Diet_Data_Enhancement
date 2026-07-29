import json
import re
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
ENHANCED = ROOT / "outputs" / "enhanced_hpp"
OUT = ROOT / "outputs" / "downstream_features"

SCENARIOS = {
    "denovo": ENHANCED / "1.denovo",
    "nutrimatch_based": ENHANCED / "2.nutrimatch_based",
}

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

KG_RELATIONS = [
    "has_nutrient_amount_per_100g",
    "inherits_product_processing_match",
    "has_nova_group",
    "has_nutriscore_grade",
    "linked_to_foodb_chemical_class",
    "linked_to_foodb_chemical_superclass",
    "linked_to_hmdb_biospecimen",
    "linked_to_hmdb_disease_annotation",
    "linked_to_hmdb_pathway_annotation",
]

TEXT_EVIDENCE_COLS = [
    "canonical_inherited__openfoodfacts_product_name",
    "canonical_inherited__brands",
    "canonical_inherited__countries_en",
    "canonical_inherited__ingredients_text",
    "canonical_inherited__additives_tags",
    "canonical_inherited__allergens",
    "canonical_inherited__labels_en",
    "canonical_inherited__foodb_top_chemical_classes",
    "canonical_inherited__foodb_top_chemical_superclasses",
    "canonical_inherited__hmdb_biospecimens",
    "canonical_inherited__hmdb_top_diseases",
    "canonical_inherited__hmdb_top_pathways",
]

RECIPES = {
    "broad_diet_health": {
        "description": "Broad diet-health feature export: nutrients, product/processing, chemical, metabolomics, disease, pathway, and text-evidence fields.",
        "feature_groups": [
            "nutrient_per_100g",
            "product_processing",
            "food_chemical_annotation",
            "metabolomics_disease_pathway_annotation",
        ],
        "kg_relations": KG_RELATIONS,
        "feature_tokens": [],
        "target_keywords": [],
        "include_text": True,
    },
    "microbiome": {
        "description": "Microbiome-oriented export emphasizing fiber, carbohydrate, fat, fermentation-relevant nutrients, chemicals, biospecimens, gastrointestinal diseases, and pathways.",
        "feature_groups": [
            "nutrient_per_100g",
            "product_processing",
            "food_chemical_annotation",
            "metabolomics_disease_pathway_annotation",
        ],
        "kg_relations": KG_RELATIONS,
        "feature_tokens": [
            "fiber",
            "carbohydrate",
            "sugar",
            "starch",
            "fat",
            "fatty",
            "protein",
            "alcohol",
            "sodium",
            "potassium",
            "magnesium",
            "zinc",
            "iron",
            "vitamin",
            "folate",
            "choline",
            "betaine",
        ],
        "target_keywords": [
            "feces",
            "gut",
            "bowel",
            "colon",
            "colorectal",
            "crohn",
            "ulcerative",
            "inflammatory",
            "bile",
            "short chain",
            "fatty acid",
            "amino acid",
            "carbohydrate",
            "lipid",
            "tryptophan",
        ],
        "include_text": True,
    },
    "mental_health": {
        "description": "Mental-health-oriented export emphasizing stimulant, alcohol, amino-acid, B-vitamin, omega-fat, neurotransmitter, stress, depression, anxiety, and related pathway evidence.",
        "feature_groups": [
            "nutrient_per_100g",
            "product_processing",
            "food_chemical_annotation",
            "metabolomics_disease_pathway_annotation",
        ],
        "kg_relations": KG_RELATIONS,
        "feature_tokens": [
            "caffeine",
            "theobromine",
            "alcohol",
            "tryptophan",
            "tyrosine",
            "phenylalanine",
            "glutamic",
            "glycine",
            "serine",
            "folate",
            "vitamin b",
            "b-12",
            "b-6",
            "choline",
            "magnesium",
            "zinc",
            "iron",
            "omega",
            "dha",
            "epa",
            "fatty",
            "sugar",
        ],
        "target_keywords": [
            "anxiety",
            "depression",
            "stress",
            "mood",
            "cognitive",
            "brain",
            "neuro",
            "serotonin",
            "dopamine",
            "gaba",
            "glutamate",
            "tryptophan",
            "caffeine",
            "sleep",
        ],
        "include_text": True,
    },
    "cardiometabolic": {
        "description": "Cardiometabolic export emphasizing energy, fat, sodium, sugar, fiber, lipid, diabetes, obesity, cardiovascular, and inflammation evidence.",
        "feature_groups": [
            "nutrient_per_100g",
            "product_processing",
            "food_chemical_annotation",
            "metabolomics_disease_pathway_annotation",
        ],
        "kg_relations": KG_RELATIONS,
        "feature_tokens": [
            "energy",
            "fat",
            "saturated",
            "trans",
            "cholesterol",
            "sodium",
            "salt",
            "sugar",
            "carbohydrate",
            "fiber",
            "protein",
            "potassium",
            "magnesium",
            "calcium",
            "folate",
        ],
        "target_keywords": [
            "cardio",
            "heart",
            "vascular",
            "diabetes",
            "insulin",
            "glucose",
            "obesity",
            "lipid",
            "cholesterol",
            "inflammation",
            "hypertension",
            "atherosclerosis",
            "fatty acid",
        ],
        "include_text": True,
    },
    "chemical_metabolomics": {
        "description": "Chemistry and metabolomics export emphasizing FoodAtlas, FooDB, HMDB, disease, pathway, and biospecimen graph neighborhoods.",
        "feature_groups": [
            "food_chemical_annotation",
            "metabolomics_disease_pathway_annotation",
        ],
        "kg_relations": [
            "linked_to_foodb_chemical_class",
            "linked_to_foodb_chemical_superclass",
            "linked_to_hmdb_biospecimen",
            "linked_to_hmdb_disease_annotation",
            "linked_to_hmdb_pathway_annotation",
        ],
        "feature_tokens": [],
        "target_keywords": [],
        "include_text": True,
    },
}


def _read_csv(path):
    return pd.read_csv(path, low_memory=False, dtype={"hpp_food_id": str})


def _clean_feature_token(value):
    value = re.sub(r"[^A-Za-z0-9]+", "_", str(value).strip().lower())
    value = re.sub(r"_+", "_", value).strip("_")
    return value[:120] or "unknown"


def _contains_any(value, tokens):
    if not tokens:
        return True
    value = str(value).lower()
    return any(token.lower() in value for token in tokens)


def _selected_matrix_columns(feature, schema, recipe):
    groups = set(recipe["feature_groups"])
    selected = schema.loc[schema["feature_group"].isin(groups), "feature_name"].astype(str).tolist()
    selected = [col for col in selected if col in feature.columns]
    tokens = recipe.get("feature_tokens") or []
    if tokens:
        selected = [col for col in selected if _contains_any(col, tokens) or col.startswith("canonical_inherited__")]
    if recipe.get("include_text"):
        selected += [col for col in TEXT_EVIDENCE_COLS if col in feature.columns]
    seen = set()
    cols = []
    for col in selected:
        if col not in seen:
            seen.add(col)
            cols.append(col)
    return cols


def _load_kg_edges(scenario_dir):
    nodes = pd.read_csv(scenario_dir / "kg" / "hpp_scenario_kg_nodes.csv", low_memory=False)
    edges = pd.read_csv(scenario_dir / "kg" / "hpp_scenario_kg_edges.csv", low_memory=False)
    nodes = nodes[["key", "kind", "label"]].rename(
        columns={"key": "target", "kind": "target_kind", "label": "target_label"}
    )
    edges = edges[edges["source"].astype(str).str.startswith("hpp_food:", na=False)].copy()
    edges["hpp_food_id"] = edges["source"].astype(str).str.replace("hpp_food:", "", regex=False)
    edges = edges.merge(nodes, on="target", how="left")
    edges["target_kind"] = edges["target_kind"].fillna("unknown")
    edges["target_label"] = edges["target_label"].fillna(edges["target"].astype(str))
    return edges


def _kg_feature_matrix(edges, recipe):
    edges = edges[edges["relation"].isin(recipe["kg_relations"])].copy()
    keywords = recipe.get("target_keywords") or []
    if keywords:
        relation_keep_all = edges["relation"].isin(
            [
                "has_nutrient_amount_per_100g",
                "inherits_product_processing_match",
                "has_nova_group",
                "has_nutriscore_grade",
                "linked_to_foodb_chemical_class",
                "linked_to_foodb_chemical_superclass",
                "linked_to_hmdb_biospecimen",
            ]
        )
        label_keep = edges["target_label"].astype(str).map(lambda value: _contains_any(value, keywords))
        edges = edges[relation_keep_all | label_keep].copy()
    if edges.empty:
        return pd.DataFrame(columns=["hpp_food_id"])
    numeric_value = pd.to_numeric(edges.get("value"), errors="coerce")
    edges["feature_value"] = numeric_value.where(numeric_value.notna(), 1.0)
    edges["kg_feature"] = (
        "kg__"
        + edges["relation"].astype(str).map(_clean_feature_token)
        + "__"
        + edges["target_kind"].astype(str).map(_clean_feature_token)
        + "__"
        + edges["target_label"].astype(str).map(_clean_feature_token)
    )
    matrix = edges.pivot_table(
        index="hpp_food_id",
        columns="kg_feature",
        values="feature_value",
        aggfunc="sum",
        fill_value=0,
    ).reset_index()
    matrix.columns.name = None
    return matrix


def _feature_list(table, identity_cols, matrix_cols, kg_cols, recipe_name, scenario_name):
    rows = []
    for col in table.columns:
        if col in identity_cols:
            source = "hpp_identity"
            model_role = "identifier_or_descriptor"
        elif col in matrix_cols:
            source = "scenario_feature_matrix"
            model_role = "numeric_or_text_evidence"
        elif col in kg_cols:
            source = "scenario_knowledge_graph"
            model_role = "numeric_edge_value_or_binary_neighborhood"
        else:
            source = "derived"
            model_role = "unknown"
        rows.append(
            {
                "scenario": scenario_name,
                "recipe": recipe_name,
                "feature_name": col,
                "feature_source": source,
                "model_role": model_role,
            }
        )
    return pd.DataFrame(rows)


def build_downstream_feature_table(recipe_name="broad_diet_health", scenario_name="denovo"):
    if recipe_name not in RECIPES:
        raise ValueError(f"Unknown recipe {recipe_name!r}. Available: {sorted(RECIPES)}")
    if scenario_name not in SCENARIOS:
        raise ValueError(f"Unknown scenario {scenario_name!r}. Available: {sorted(SCENARIOS)}")

    recipe = RECIPES[recipe_name]
    scenario_dir = SCENARIOS[scenario_name]
    feature = _read_csv(scenario_dir / "hpp_feature_matrix_per_100g.csv")
    schema = pd.read_csv(scenario_dir / "feature_schema.csv", low_memory=False)
    identity_cols = [col for col in IDENTITY_COLS if col in feature.columns]
    matrix_cols = _selected_matrix_columns(feature, schema, recipe)
    table = feature[identity_cols + matrix_cols].copy()
    table["hpp_food_id"] = table["hpp_food_id"].astype(str)

    edges = _load_kg_edges(scenario_dir)
    kg_matrix = _kg_feature_matrix(edges, recipe)
    kg_cols = [col for col in kg_matrix.columns if col != "hpp_food_id"]
    if kg_cols:
        table = table.merge(kg_matrix, on="hpp_food_id", how="left")
        table[kg_cols] = table[kg_cols].fillna(0)

    out_dir = OUT / scenario_name / recipe_name
    out_dir.mkdir(parents=True, exist_ok=True)
    table_path = out_dir / "hpp_downstream_feature_table.csv"
    feature_list_path = out_dir / "hpp_downstream_feature_list.csv"
    summary_path = out_dir / "hpp_downstream_feature_summary.json"

    feature_list = _feature_list(table, identity_cols, matrix_cols, kg_cols, recipe_name, scenario_name)
    table.to_csv(table_path, index=False)
    feature_list.to_csv(feature_list_path, index=False)

    summary = {
        "scenario": scenario_name,
        "recipe": recipe_name,
        "description": recipe["description"],
        "hpp_food_rows": int(table["hpp_food_id"].nunique()),
        "table_shape": [int(table.shape[0]), int(table.shape[1])],
        "identity_columns": len(identity_cols),
        "matrix_feature_columns": len(matrix_cols),
        "kg_feature_columns": len(kg_cols),
        "outputs": {
            "feature_table": str(table_path),
            "feature_list": str(feature_list_path),
            "summary": str(summary_path),
        },
    }
    summary_path.write_text(json.dumps(summary, indent=2))
    return summary


def build_all_downstream_feature_tables():
    summaries = []
    for scenario_name in SCENARIOS:
        for recipe_name in RECIPES:
            summaries.append(build_downstream_feature_table(recipe_name, scenario_name))
    OUT.mkdir(parents=True, exist_ok=True)
    summary = {
        "recipes": {name: spec["description"] for name, spec in RECIPES.items()},
        "scenario_count": len(SCENARIOS),
        "recipe_count": len(RECIPES),
        "exports": summaries,
    }
    (OUT / "downstream_feature_exports_summary.json").write_text(json.dumps(summary, indent=2))
    pd.DataFrame(summaries).to_csv(OUT / "downstream_feature_exports_summary.csv", index=False)
    return summary
