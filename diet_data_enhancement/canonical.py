import json
import re
from pathlib import Path

import pandas as pd

from .graph_store import empty_graph, save_graph, upsert_edge, upsert_node
from .mapping import make_review_queue, map_hpp_to_public
from .sources import ROOT, load_hpp_foods, load_public_foods
from .text import normalize_text


OUT = ROOT / "outputs/canonical"


def slug(value):
    text = normalize_text(value)
    text = re.sub(r"\s+", "_", text).strip("_")
    return text or "unknown"


def canonical_id(name, category):
    return f"canonical:{slug(name)}:{slug(category)}"


def build_canonical_tables():
    OUT.mkdir(parents=True, exist_ok=True)
    hpp = load_hpp_foods().copy()
    raw_hpp = pd.read_csv(ROOT / "data/HPP/hpp_food_items_with_nutrients.csv")
    raw_hpp = raw_hpp[["food_id", "product_name", "short_name"]].rename(
        columns={"food_id": "hpp_food_id"}
    )
    hpp = hpp.merge(raw_hpp, on="hpp_food_id", how="left")
    hpp["original_product_name"] = (
        hpp["product_name"]
        .fillna(hpp["short_description"])
        .fillna(hpp["short_name"])
        .fillna(hpp["hebrew_name"])
        .fillna("")
    )
    hpp["canonical_name"] = hpp["food_name"].fillna("").astype(str).str.strip()
    hpp["canonical_category"] = hpp["category"].fillna("").astype(str).str.strip()
    hpp["canonical_food_id"] = [
        canonical_id(name, category)
        for name, category in zip(hpp["canonical_name"], hpp["canonical_category"])
    ]

    agg_rows = []
    for cid, group in hpp.groupby("canonical_food_id", sort=True):
        group = group.copy()
        group["number_loggings"] = pd.to_numeric(group.get("number_loggings"), errors="coerce") if "number_loggings" in group else 0
        # load_hpp_foods currently excludes number_loggings, so this remains forward-compatible.
        representative = group.iloc[0]
        original_examples = (
            group["original_product_name"]
            .dropna()
            .astype(str)
            .drop_duplicates()
            .head(12)
            .tolist()
        )
        hebrew_examples = (
            group["hebrew_name"]
            .dropna()
            .astype(str)
            .drop_duplicates()
            .head(12)
            .tolist()
        )
        agg_rows.append(
            {
                "canonical_food_id": cid,
                "canonical_name": representative["canonical_name"],
                "canonical_category": representative["canonical_category"],
                "hpp_food_count": int(group["hpp_food_id"].nunique()),
                "representative_hpp_food_id": representative["hpp_food_id"],
                "representative_original_name": representative["original_product_name"],
                "representative_hebrew_name": representative.get("hebrew_name", ""),
                "original_examples": " | ".join(original_examples),
                "hebrew_examples": " | ".join(hebrew_examples),
                "needs_review": bool(group["hpp_food_id"].nunique() > 1),
                "canonical_assignment_method": "normalized_name_plus_category",
            }
        )

    canonical = pd.DataFrame(agg_rows).sort_values(["canonical_name", "canonical_category"])
    crosswalk = hpp[
        [
            "hpp_food_id",
            "food_name",
            "original_product_name",
            "hebrew_name",
            "category",
            "canonical_food_id",
            "canonical_name",
            "canonical_category",
        ]
    ].rename(
        columns={
            "food_name": "hpp_food_name",
            "category": "hpp_category",
        }
    )
    crosswalk["canonical_assignment_method"] = "normalized_name_plus_category"

    canonical.to_csv(OUT / "canonical_foods.csv", index=False)
    crosswalk.to_csv(OUT / "hpp_to_canonical.csv", index=False)

    summary = {
        "hpp_food_count": int(crosswalk["hpp_food_id"].nunique()),
        "canonical_food_count": int(canonical["canonical_food_id"].nunique()),
        "collapsed_hpp_food_count": int(canonical["hpp_food_count"].sum() - canonical.shape[0]),
        "multi_hpp_canonical_count": int((canonical["hpp_food_count"] > 1).sum()),
        "outputs": {
            "canonical_foods": str(OUT / "canonical_foods.csv"),
            "hpp_to_canonical": str(OUT / "hpp_to_canonical.csv"),
        },
    }
    (OUT / "canonical_summary.json").write_text(json.dumps(summary, indent=2))
    return canonical, crosswalk, summary


def load_canonical_foods():
    path = OUT / "canonical_foods.csv"
    if not path.exists():
        canonical, _, _ = build_canonical_tables()
        return canonical
    return pd.read_csv(path)


def canonical_as_foods(canonical):
    return pd.DataFrame(
        {
            "hpp_food_id": canonical["canonical_food_id"],
            "food_name": canonical["canonical_name"],
            "short_description": canonical["representative_original_name"],
            "category": canonical["canonical_category"],
            "hebrew_name": canonical.get("representative_hebrew_name", ""),
        }
    )


def map_canonical_to_public(top_k=5):
    OUT.mkdir(parents=True, exist_ok=True)
    canonical = load_canonical_foods()
    canonical_foods = canonical_as_foods(canonical)
    public = load_public_foods()
    mappings = map_hpp_to_public(canonical_foods, public, top_k=top_k)
    mappings = mappings.rename(
        columns={
            "hpp_food_id": "canonical_food_id",
            "hpp_food_name": "canonical_name",
            "hpp_short_description": "representative_original_name",
            "hpp_category": "canonical_category",
        }
    )
    mappings["stage"] = "canonical_public_fcdb_low_effort"
    mappings.to_csv(OUT / "canonical_public_food_mappings.csv", index=False)

    review = make_review_queue(
        mappings.rename(
            columns={
                "canonical_food_id": "hpp_food_id",
                "canonical_name": "hpp_food_name",
                "representative_original_name": "hpp_short_description",
                "canonical_category": "hpp_category",
            }
        )
    ).rename(
        columns={
            "hpp_food_id": "canonical_food_id",
            "hpp_food_name": "canonical_name",
            "hpp_short_description": "representative_original_name",
            "hpp_category": "canonical_category",
        }
    )
    review.to_csv(OUT / "canonical_review_queue.csv", index=False)

    best = mappings[mappings["candidate_rank"] == 1]
    summary = {
        "canonical_food_count": int(canonical.shape[0]),
        "mapping_rows": int(mappings.shape[0]),
        "review_queue_count": int(review.shape[0]),
        "top_match_confidence_counts": best["confidence"].value_counts().to_dict(),
        "outputs": {
            "canonical_public_food_mappings": str(OUT / "canonical_public_food_mappings.csv"),
            "canonical_review_queue": str(OUT / "canonical_review_queue.csv"),
        },
    }
    (OUT / "canonical_mapping_summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def build_canonical_graph():
    OUT.mkdir(parents=True, exist_ok=True)
    canonical = load_canonical_foods()
    crosswalk_path = OUT / "hpp_to_canonical.csv"
    if not crosswalk_path.exists():
        _, crosswalk, _ = build_canonical_tables()
    else:
        crosswalk = pd.read_csv(crosswalk_path)

    graph = empty_graph()
    for _, row in canonical.iterrows():
        upsert_node(
            graph,
            "canonical_food",
            row["canonical_food_id"],
            row["canonical_name"],
            category=row.get("canonical_category", ""),
            hpp_food_count=int(row.get("hpp_food_count", 0)),
            representative_original_name=row.get("representative_original_name", ""),
        )

    for _, row in crosswalk.iterrows():
        hpp_key = upsert_node(
            graph,
            "hpp_food",
            row["hpp_food_id"],
            row["hpp_food_name"],
            category=row.get("hpp_category", ""),
            original_product_name=row.get("original_product_name", ""),
        )
        canonical_key = f"canonical_food:{row['canonical_food_id']}"
        upsert_edge(
            graph,
            hpp_key,
            canonical_key,
            "belongs_to_canonical",
            method=row.get("canonical_assignment_method", ""),
        )

    mapping_path = OUT / "canonical_public_food_mappings.csv"
    if mapping_path.exists():
        mappings = pd.read_csv(mapping_path)
        best = mappings.sort_values(["canonical_food_id", "candidate_rank"]).groupby("canonical_food_id").head(1)
        for _, row in best.iterrows():
            canonical_key = f"canonical_food:{row['canonical_food_id']}"
            source_key = upsert_node(
                graph,
                "source_food",
                f"{row.get('source', '')}:{row.get('source_food_id', '')}",
                row.get("matched_food_name", ""),
                source=row.get("source", ""),
                category=row.get("matched_category", ""),
            )
            upsert_edge(
                graph,
                canonical_key,
                source_key,
                "mapped_to",
                score=float(row.get("match_score", 0) or 0),
                confidence=row.get("confidence", ""),
                stage=row.get("stage", ""),
            )

    graph_path = OUT / "canonical_food_graph.json"
    save_graph(graph, graph_path)
    return graph_path


def run_canonical_pipeline():
    _, _, canonical_summary = build_canonical_tables()
    mapping_summary = map_canonical_to_public()
    graph_path = build_canonical_graph()
    summary = {
        "canonical": canonical_summary,
        "mapping": mapping_summary,
        "graph": str(graph_path),
    }
    (OUT / "canonical_pipeline_summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def main():
    print(json.dumps(run_canonical_pipeline(), indent=2))


if __name__ == "__main__":
    main()
