import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def build_report():
    summary = json.loads((ROOT / "outputs/mapping/mapping_summary.json").read_text())
    inventory = pd.read_csv(ROOT / "outputs/inventory/source_inventory.csv")
    foodatlas = pd.read_csv(ROOT / "outputs/foodatlas/entities_foods.csv")
    foodatlas_candidates = pd.read_csv(ROOT / "outputs/foodatlas/hpp_foodatlas_candidates.csv")
    best_foodatlas = foodatlas_candidates[foodatlas_candidates["candidate_rank"] == 1]
    canonical_summary_path = ROOT / "outputs/canonical/canonical_pipeline_summary.json"
    canonical_summary = json.loads(canonical_summary_path.read_text()) if canonical_summary_path.exists() else {}
    nutrient_imputation_path = ROOT / "outputs/nutrients/canonical_nutrient_imputation_summary.json"
    nutrient_imputation = (
        json.loads(nutrient_imputation_path.read_text()) if nutrient_imputation_path.exists() else {}
    )
    kg_summary_path = ROOT / "outputs/kg/final_food_kg_summary.json"
    kg_summary = json.loads(kg_summary_path.read_text()) if kg_summary_path.exists() else {}

    report = {
        "public_mapping": {
            "hpp_food_count": summary["hpp_food_count"],
            "public_candidate_count": summary["public_candidate_count"],
            "top_match_confidence_counts": summary["top_match_confidence_counts"],
            "review_queue_count": summary["review_queue_count"],
        },
        "source_inventory": inventory.to_dict("records"),
        "foodatlas": {
            "food_entity_count": int(foodatlas.shape[0]),
            "top_match_confidence_counts": best_foodatlas["confidence"].value_counts().to_dict(),
        },
        "canonical": canonical_summary,
        "canonical_nutrient_imputation": nutrient_imputation,
        "final_knowledge_graph": kg_summary,
        "recommended_next_step": (
            "Standardize nutrient units and inspect canonical-level imputed values "
            "before carrying the package toward TRE-side feature assembly."
        ),
    }
    out_path = ROOT / "outputs/run_report.json"
    out_path.write_text(json.dumps(report, indent=2))
    return out_path


def main():
    print(build_report())


if __name__ == "__main__":
    main()
