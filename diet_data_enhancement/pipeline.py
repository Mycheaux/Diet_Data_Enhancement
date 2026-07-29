import argparse
import json
from pathlib import Path

import pandas as pd

from .canonical import (
    build_canonical_graph,
    build_canonical_tables,
    map_canonical_to_public,
    run_canonical_pipeline,
)
from .chem_bio_layers import (
    build_foodb_compound_reference,
    build_hmdb_food_compound_links,
    build_hmdb_metabolite_index,
    build_layer3_chemical_features,
    build_layer3_foodb_candidates,
    build_layer5_disease_pathway_features,
    run_chem_bio_layers,
)
from .downstream_features import build_all_downstream_feature_tables
from .foodatlas import (
    extract_food_entities_from_parquet,
    map_hpp_to_foodatlas,
    map_reviewed_items_to_foodatlas,
)
from .food_card import (
    build_food_card_embeddings,
    build_food_cards,
    build_global_categorization_candidates,
    build_seed_categorizations,
)
from .final_kg import build_final_kg
from .graph_store import graph_from_mappings, save_graph
from .hpp_scenarios import (
    build_hpp_comparison_layers,
    build_hpp_enhancement_scenarios,
    build_hpp_llm_sentence_embeddings,
)
from .hpp_kg_visualization import build_denovo_hpp_kg_visualizations
from .hpp_kg_advanced_visualization import build_denovo_advanced_kg_visualizations
from .hpp_kg_mega_visualization import build_denovo_hpp_kg_mega_flexible
from .kg_visualization import (
    build_full_floating_visualization,
    build_full_visualization,
    build_schema_overview_plot,
    build_visualizations,
)
from .kg_enhance import build_kg_enhancement, build_kg_enhancement_interactive
from .kg_enhance_visualization import build_kg_enhance_visualizations
from .layered import (
    build_hitl_queue,
    build_layer1_candidates,
    build_layer2_candidates,
    build_layered_validation,
    build_reference_tables,
    run_layered_all,
)
from .mapping import make_review_queue, map_hpp_to_public
from .multimodal import build_all as build_multimodal_food_concept_space
from .multimodal import (
    build_embedding_visualization,
    build_food_concept_sentences,
    build_llm_sentence_embeddings,
    build_multimodal_vectors,
    build_pattern_discovery,
)
from .nutrients import harmonize_nutrients, impute_canonical_nutrients
from .nutrimatch_comparison import (
    compare_inferred_nutrimatch_mapping_to_layer1,
    compare_nutrimatch_to_layer1,
)
from .sources import load_hpp_foods, load_public_foods


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"


def run():
    mapping_dir = OUT / "mapping"
    graph_dir = OUT / "graph"
    mapping_dir.mkdir(parents=True, exist_ok=True)
    graph_dir.mkdir(parents=True, exist_ok=True)

    hpp = load_hpp_foods()
    public = load_public_foods()
    mappings = map_hpp_to_public(hpp, public, top_k=5)
    review = make_review_queue(mappings)
    graph = graph_from_mappings(mappings)

    mappings.to_csv(mapping_dir / "hpp_public_food_mappings.csv", index=False)
    review.to_csv(mapping_dir / "review_queue.csv", index=False)
    save_graph(graph, graph_dir / "food_mapping_graph.json")

    best = mappings[mappings["candidate_rank"] == 1]
    summary = {
        "hpp_food_count": int(hpp.shape[0]),
        "public_candidate_count": int(public.shape[0]),
        "top_match_confidence_counts": best["confidence"].value_counts().to_dict(),
        "review_queue_count": int(review.shape[0]),
        "outputs": {
            "mappings": str(mapping_dir / "hpp_public_food_mappings.csv"),
            "review_queue": str(mapping_dir / "review_queue.csv"),
            "graph": str(graph_dir / "food_mapping_graph.json"),
        },
    }
    (mapping_dir / "mapping_summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def write_source_inventory():
    inventory_dir = OUT / "inventory"
    inventory_dir.mkdir(parents=True, exist_ok=True)
    hpp = load_hpp_foods()
    public = load_public_foods()
    rows = [
        {
            "source": "HPP_food_list",
            "record_count": int(hpp.shape[0]),
            "role": "target food list to be mapped",
        }
    ]
    for source, group in public.groupby("source"):
        rows.append(
            {
                "source": source,
                "record_count": int(group.shape[0]),
                "role": "public FCDB candidate source",
            }
        )
    inventory = pd.DataFrame(rows).sort_values("source")
    inventory.to_csv(inventory_dir / "source_inventory.csv", index=False)
    return inventory_dir / "source_inventory.csv"


def run_all():
    summary = run()
    foodatlas_entities = extract_food_entities_from_parquet()
    foodatlas_candidates = map_hpp_to_foodatlas()
    reviewed_foodatlas = map_reviewed_items_to_foodatlas()
    source_inventory = write_source_inventory()
    nutrient_summary = harmonize_nutrients()
    canonical_summary = run_canonical_pipeline()
    canonical_nutrient_summary = impute_canonical_nutrients()
    kg_summary = build_final_kg()
    summary["outputs"].update(
        {
            "foodatlas_entities": str(foodatlas_entities),
            "foodatlas_candidates": str(foodatlas_candidates),
            "reviewed_foodatlas_candidates": str(reviewed_foodatlas),
            "source_inventory": str(source_inventory),
            "nutrient_harmonized": nutrient_summary["output"],
            "canonical_pipeline": str(OUT / "canonical/canonical_pipeline_summary.json"),
            "canonical_nutrient_profiles": canonical_nutrient_summary["outputs"]["canonical_nutrient_profiles"],
            "final_food_kg": kg_summary["graph"],
        }
    )
    (OUT / "mapping/mapping_summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenario",
        action="append",
        choices=["denovo", "nutrimatch_based"],
        help="Optional scenario filter for commands that support it. May be repeated.",
    )
    parser.add_argument(
        "--text-column",
        default="full_biology_text",
        help="Food-card text column to embed for build-food-card-embeddings.",
    )
    parser.add_argument(
        "--embedding-model",
        default=None,
        help="Embedding model override for build-food-card-embeddings.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=64,
        help="Batch size for build-food-card-embeddings.",
    )
    parser.add_argument(
        "command",
        choices=[
            "run",
            "run-all",
            "extract-foodatlas",
            "map-foodatlas",
            "map-reviewed-foodatlas",
            "inventory",
            "harmonize-nutrients",
            "impute-nutrients",
            "canonicalize",
            "map-canonical",
            "canonical-graph",
            "canonical-all",
            "build-kg",
            "build-kg-viz",
            "build-full-kg-viz",
            "build-full-floating-kg-viz",
            "build-kg-schema-viz",
            "layer1-map",
            "layer2-map",
            "layered-hitl-queue",
            "build-reference",
            "layered-validation",
            "layered-all",
            "layer3-foodb-map",
            "layer3-foodb-compounds",
            "layer3-chemical-features",
            "layer4-hmdb-index",
            "layer4-hmdb-links",
            "layer5-disease-pathway",
            "chem-bio-all",
            "build-food-concept-sentences",
            "build-multimodal-vectors",
            "build-food-disease-patterns",
            "build-embedding-space-viz",
            "build-llm-sentence-embeddings",
            "build-multimodal-space",
            "compare-nutrimatch",
            "compare-nutrimatch-mapping",
            "build-hpp-enhancement-scenarios",
            "build-hpp-comparison-layers",
            "build-hpp-llm-sentence-embeddings",
            "build-denovo-hpp-kg-viz",
            "build-denovo-advanced-kg-viz",
            "build-denovo-mega-flexible-kg-viz",
            "build-downstream-feature-tables",
            "build-kg-enhance",
            "build-kg-enhance-interactive",
            "build-kg-enhance-viz",
            "build-food-card-categorization",
            "build-food-cards",
            "build-food-card-embeddings",
        ],
    )
    args = parser.parse_args()
    if args.command == "run":
        summary = run()
        print(json.dumps(summary, indent=2))
    elif args.command == "run-all":
        summary = run_all()
        print(json.dumps(summary, indent=2))
    elif args.command == "extract-foodatlas":
        print(extract_food_entities_from_parquet())
    elif args.command == "map-foodatlas":
        print(map_hpp_to_foodatlas())
    elif args.command == "map-reviewed-foodatlas":
        print(map_reviewed_items_to_foodatlas())
    elif args.command == "inventory":
        print(write_source_inventory())
    elif args.command == "harmonize-nutrients":
        print(json.dumps(harmonize_nutrients(), indent=2))
    elif args.command == "impute-nutrients":
        print(json.dumps(impute_canonical_nutrients(), indent=2))
    elif args.command == "canonicalize":
        _, _, summary = build_canonical_tables()
        print(json.dumps(summary, indent=2))
    elif args.command == "map-canonical":
        print(json.dumps(map_canonical_to_public(), indent=2))
    elif args.command == "canonical-graph":
        print(build_canonical_graph())
    elif args.command == "canonical-all":
        print(json.dumps(run_canonical_pipeline(), indent=2))
    elif args.command == "build-kg":
        print(json.dumps(build_final_kg(), indent=2))
    elif args.command == "build-kg-viz":
        print(json.dumps(build_visualizations(), indent=2))
    elif args.command == "build-full-kg-viz":
        print(json.dumps(build_full_visualization(), indent=2))
    elif args.command == "build-full-floating-kg-viz":
        print(json.dumps(build_full_floating_visualization(), indent=2))
    elif args.command == "build-kg-schema-viz":
        print(json.dumps(build_schema_overview_plot(), indent=2))
    elif args.command == "layer1-map":
        print(json.dumps(build_layer1_candidates()[1], indent=2))
    elif args.command == "layer2-map":
        print(json.dumps(build_layer2_candidates()[1], indent=2))
    elif args.command == "layered-hitl-queue":
        print(json.dumps(build_hitl_queue()[1], indent=2))
    elif args.command == "build-reference":
        print(json.dumps(build_reference_tables(), indent=2))
    elif args.command == "layered-validation":
        print(build_layered_validation())
    elif args.command == "layered-all":
        print(json.dumps(run_layered_all(), indent=2))
    elif args.command == "layer3-foodb-map":
        print(json.dumps(build_layer3_foodb_candidates()[1], indent=2))
    elif args.command == "layer3-foodb-compounds":
        print(json.dumps(build_foodb_compound_reference()[1], indent=2))
    elif args.command == "layer3-chemical-features":
        print(json.dumps(build_layer3_chemical_features()[1], indent=2))
    elif args.command == "layer4-hmdb-index":
        print(json.dumps(build_hmdb_metabolite_index()[1], indent=2))
    elif args.command == "layer4-hmdb-links":
        print(json.dumps(build_hmdb_food_compound_links()[1], indent=2))
    elif args.command == "layer5-disease-pathway":
        print(json.dumps(build_layer5_disease_pathway_features()[1], indent=2))
    elif args.command == "chem-bio-all":
        print(json.dumps(run_chem_bio_layers(), indent=2))
    elif args.command == "build-food-concept-sentences":
        _, path = build_food_concept_sentences()
        print(path)
    elif args.command == "build-multimodal-vectors":
        print(json.dumps(build_multimodal_vectors(), indent=2))
    elif args.command == "build-food-disease-patterns":
        print(json.dumps(build_pattern_discovery(), indent=2))
    elif args.command == "build-embedding-space-viz":
        print(json.dumps(build_embedding_visualization(), indent=2))
    elif args.command == "build-llm-sentence-embeddings":
        print(json.dumps(build_llm_sentence_embeddings(force_prompt=True), indent=2))
    elif args.command == "build-multimodal-space":
        print(json.dumps(build_multimodal_food_concept_space(), indent=2))
    elif args.command == "compare-nutrimatch":
        print(json.dumps(compare_nutrimatch_to_layer1(), indent=2))
    elif args.command == "compare-nutrimatch-mapping":
        print(json.dumps(compare_inferred_nutrimatch_mapping_to_layer1(), indent=2))
    elif args.command == "build-hpp-enhancement-scenarios":
        print(json.dumps(build_hpp_enhancement_scenarios(), indent=2))
    elif args.command == "build-hpp-comparison-layers":
        print(json.dumps(build_hpp_comparison_layers(), indent=2))
    elif args.command == "build-hpp-llm-sentence-embeddings":
        print(json.dumps(build_hpp_llm_sentence_embeddings(force_prompt=True), indent=2))
    elif args.command == "build-denovo-hpp-kg-viz":
        print(json.dumps(build_denovo_hpp_kg_visualizations(), indent=2))
    elif args.command == "build-denovo-advanced-kg-viz":
        print(json.dumps(build_denovo_advanced_kg_visualizations(), indent=2))
    elif args.command == "build-denovo-mega-flexible-kg-viz":
        print(json.dumps(build_denovo_hpp_kg_mega_flexible(), indent=2))
    elif args.command == "build-downstream-feature-tables":
        print(json.dumps(build_all_downstream_feature_tables(), indent=2))
    elif args.command == "build-kg-enhance":
        print(json.dumps(build_kg_enhancement(), indent=2))
    elif args.command == "build-kg-enhance-interactive":
        print(json.dumps(build_kg_enhancement_interactive(), indent=2))
    elif args.command == "build-kg-enhance-viz":
        print(json.dumps(build_kg_enhance_visualizations(), indent=2))
    elif args.command == "build-food-card-categorization":
        summary = {
            "global_candidates": build_global_categorization_candidates(),
            "seed_categorizations": build_seed_categorizations(),
        }
        print(json.dumps(summary, indent=2))
    elif args.command == "build-food-cards":
        print(json.dumps(build_food_cards(), indent=2))
    elif args.command == "build-food-card-embeddings":
        kwargs = {
            "scenarios": tuple(args.scenario or ["denovo", "nutrimatch_based"]),
            "text_column": args.text_column,
            "batch_size": args.batch_size,
            "force_prompt": True,
        }
        if args.embedding_model:
            kwargs["model"] = args.embedding_model
        print(json.dumps(build_food_card_embeddings(**kwargs), indent=2))


if __name__ == "__main__":
    main()
