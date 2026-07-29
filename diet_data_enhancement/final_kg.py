import json
import zipfile
from collections import Counter
from pathlib import Path

import pandas as pd

from .graph_store import empty_graph, now, save_graph
from .sources import ROOT


OUT = ROOT / "outputs/kg"
FOODATLAS_ZIP = ROOT / "data/FoodAtlas/foodatlas-v4.5.zip"


def _read_csv(path, required=False):
    path = Path(path)
    if not path.exists():
        if required:
            raise FileNotFoundError(path)
        return pd.DataFrame()
    return pd.read_csv(path)


def _clean(value):
    if pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _attrs(**kwargs):
    clean = {}
    for key, value in kwargs.items():
        if pd.isna(value):
            continue
        if hasattr(value, "item"):
            value = value.item()
        clean[key] = value
    return clean


def _best_rows(df, id_col):
    if df.empty:
        return df
    return df.sort_values([id_col, "candidate_rank"]).groupby(id_col, as_index=False).head(1)


def _add_source_food(graph, row, name_col="matched_food_name", category_col="matched_category"):
    source = _clean(row.get("source", ""))
    source_food_id = _clean(row.get("source_food_id", ""))
    return graph.add_node(
        "source_food",
        f"{source}:{source_food_id}",
        _clean(row.get(name_col, "")),
        **_attrs(
            source=source,
            source_food_id=source_food_id,
            category=row.get(category_col, ""),
        ),
    )


def _add_foodatlas_food(graph, foodatlas_id, label, **extra):
    return graph.add_node(
        "foodatlas_food",
        _clean(foodatlas_id),
        _clean(label),
        **_attrs(**extra),
    )


def _add_foodb_food(graph, foodb_food_id, label, **extra):
    return graph.add_node(
        "foodb_food",
        _clean(foodb_food_id),
        _clean(label),
        **_attrs(source="FooDB", foodb_food_id=_clean(foodb_food_id), **extra),
    )


def _add_foodb_compound(graph, foodb_compound_id, label, **extra):
    return graph.add_node(
        "foodb_compound",
        _clean(foodb_compound_id),
        _clean(label),
        **_attrs(source="FooDB", foodb_compound_id=_clean(foodb_compound_id), **extra),
    )


def _add_hmdb_metabolite(graph, hmdb_id, label, **extra):
    return graph.add_node(
        "hmdb_metabolite",
        _clean(hmdb_id),
        _clean(label),
        **_attrs(source="HMDB", hmdb_id=_clean(hmdb_id), **extra),
    )


def _foodatlas_kind(entity_type):
    entity_type = _clean(entity_type).lower() or "entity"
    return f"foodatlas_{entity_type}"


def _load_foodatlas_native_tables():
    with zipfile.ZipFile(FOODATLAS_ZIP) as archive:
        with archive.open("foodatlas-v4.5/entities.parquet") as handle:
            entities = pd.read_parquet(handle)
        with archive.open("foodatlas-v4.5/relationships.parquet") as handle:
            relationships = pd.read_parquet(handle)
        with archive.open("foodatlas-v4.5/triplets.parquet") as handle:
            triplets = pd.read_parquet(handle)
    relationship_names = dict(zip(relationships["foodatlas_id"], relationships["name"]))
    return entities, relationship_names, triplets


class IndexedGraph:
    def __init__(self):
        self.graph = empty_graph()
        self._nodes = {}
        self._edges = {}

    def add_node(self, kind, node_id, label, **attrs):
        key = f"{kind}:{node_id}"
        payload = {"key": key, "kind": kind, "id": str(node_id), "label": label, **attrs}
        if key in self._nodes:
            self._nodes[key].update(payload)
        else:
            self._nodes[key] = payload
        return key

    def add_edge(self, source_key, target_key, relation, **attrs):
        key = (source_key, target_key, relation)
        payload = {"source": source_key, "target": target_key, "relation": relation, **attrs}
        if key in self._edges:
            self._edges[key].update(payload)
        else:
            self._edges[key] = payload

    def to_graph(self):
        self.graph["nodes"] = list(self._nodes.values())
        self.graph["edges"] = list(self._edges.values())
        return self.graph


def build_final_kg(include_all_nutrients=True, include_foodatlas_native=True):
    """Build the modular food knowledge graph from current pipeline outputs."""
    OUT.mkdir(parents=True, exist_ok=True)
    builder = IndexedGraph()
    builder.graph["metadata"].update(
        {
            "graph_name": "diet_data_enhancement_final_food_kg",
            "created_by": "diet_data_enhancement.final_kg",
            "module_policy": {
                "public_fcdb": "best canonical candidate per canonical food",
                "foodatlas": "best direct candidate per HPP food plus human remap candidates",
                "openai_validation": "validated candidate edges where available",
                "nutrients": "canonical nutrient values with provenance",
                "foodatlas_native": (
                    "all FoodAtlas food, chemical, and disease entities plus native triplets"
                    if include_foodatlas_native
                    else "only FoodAtlas nodes touched by HPP mappings"
                ),
            },
        }
    )

    canonical = _read_csv(ROOT / "outputs/canonical/canonical_foods.csv", required=True)
    crosswalk = _read_csv(ROOT / "outputs/canonical/hpp_to_canonical.csv", required=True)
    canonical_mappings = _read_csv(ROOT / "outputs/canonical/canonical_public_food_mappings.csv")
    foodatlas_direct = _read_csv(ROOT / "outputs/foodatlas/hpp_foodatlas_candidates.csv")
    foodatlas_human = _read_csv(ROOT / "outputs/foodatlas/human_foodatlas_remap.csv")
    human_corrections = _read_csv(ROOT / "outputs/mapping/human_corrections.csv")
    openai_validated = _read_csv(ROOT / "outputs/openai/gpt_validated_candidates.csv")
    nutrients = _read_csv(ROOT / "outputs/nutrients/canonical_nutrient_provenance.csv")
    foodb_candidates = _read_csv(ROOT / "outputs/layered/layer3_foodb_food_candidates.csv")
    foodb_compounds_path = ROOT / "outputs/reference/canonical_food_foodb_compound_reference.csv"
    hmdb_edges_path = ROOT / "outputs/reference/canonical_food_hmdb_metabolite_edges.csv"
    hmdb_examples_path = ROOT / "outputs/reference/canonical_food_hmdb_metabolite_link_examples.csv"
    hmdb_edges = _read_csv(hmdb_edges_path if hmdb_edges_path.exists() else hmdb_examples_path)

    if include_foodatlas_native:
        entities, relationship_names, triplets = _load_foodatlas_native_tables()
        foodatlas_entity_types = {}
        for _, row in entities.iterrows():
            foodatlas_entity_types[row["foodatlas_id"]] = row["entity_type"]
            builder.add_node(
                _foodatlas_kind(row["entity_type"]),
                row["foodatlas_id"],
                row.get("common_name", ""),
                **_attrs(
                    foodatlas_id=row.get("foodatlas_id", ""),
                    entity_type=row.get("entity_type", ""),
                    scientific_name=row.get("scientific_name", ""),
                    synonyms=row.get("synonyms", ""),
                    external_ids=row.get("external_ids", ""),
                    attributes=row.get("attributes", ""),
                ),
            )

        for _, row in triplets.iterrows():
            head_id = row["head_id"]
            tail_id = row["tail_id"]
            relation = relationship_names.get(row["relationship_id"], row["relationship_id"])
            head_kind = _foodatlas_kind(foodatlas_entity_types.get(head_id, "entity"))
            tail_kind = _foodatlas_kind(foodatlas_entity_types.get(tail_id, "entity"))
            builder.add_edge(
                f"{head_kind}:{head_id}",
                f"{tail_kind}:{tail_id}",
                f"foodatlas_{relation}",
                **_attrs(
                    relationship_id=row.get("relationship_id", ""),
                    relationship_name=relation,
                    foodatlas_evidence_source=row.get("source", ""),
                    attestation_ids=row.get("attestation_ids", ""),
                ),
            )

    for _, row in canonical.iterrows():
        builder.add_node(
            "canonical_food",
            row["canonical_food_id"],
            row["canonical_name"],
            **_attrs(
                category=row.get("canonical_category", ""),
                hpp_food_count=int(row.get("hpp_food_count", 0)),
                representative_hpp_food_id=row.get("representative_hpp_food_id", ""),
                representative_original_name=row.get("representative_original_name", ""),
                original_examples=row.get("original_examples", ""),
                needs_review=bool(row.get("needs_review", False)),
                assignment_method=row.get("canonical_assignment_method", ""),
            ),
        )

    for _, row in crosswalk.iterrows():
        hpp_key = builder.add_node(
            "hpp_food",
            row["hpp_food_id"],
            row["hpp_food_name"],
            **_attrs(
                category=row.get("hpp_category", ""),
                original_product_name=row.get("original_product_name", ""),
            ),
        )
        canonical_key = f"canonical_food:{row['canonical_food_id']}"
        builder.add_edge(
            hpp_key,
            canonical_key,
            "belongs_to_canonical",
            **_attrs(method=row.get("canonical_assignment_method", "")),
        )

    for _, row in _best_rows(canonical_mappings, "canonical_food_id").iterrows():
        canonical_key = f"canonical_food:{row['canonical_food_id']}"
        source_key = _add_source_food(builder, row)
        builder.add_edge(
            canonical_key,
            source_key,
            "mapped_to_public_fcdb",
            **_attrs(
                candidate_rank=row.get("candidate_rank", ""),
                score=float(row.get("match_score", 0) or 0),
                confidence=row.get("confidence", ""),
                stage=row.get("stage", ""),
                needs_human_review=bool(row.get("needs_human_review", False)),
            ),
        )

    for _, row in _best_rows(foodatlas_direct, "hpp_food_id").iterrows():
        hpp_key = f"hpp_food:{row['hpp_food_id']}"
        foodatlas_key = _add_foodatlas_food(
            builder,
            row.get("source_food_id", ""),
            row.get("matched_food_name", ""),
            category=row.get("matched_category", ""),
        )
        builder.add_edge(
            hpp_key,
            foodatlas_key,
            "mapped_to_foodatlas",
            **_attrs(
                candidate_rank=row.get("candidate_rank", ""),
                score=float(row.get("match_score", 0) or 0),
                confidence=row.get("confidence", ""),
                stage=row.get("stage", ""),
                needs_human_review=bool(row.get("needs_human_review", False)),
            ),
        )

    if not foodb_candidates.empty:
        for _, row in _best_rows(foodb_candidates, "canonical_food_id").iterrows():
            canonical_key = f"canonical_food:{row['canonical_food_id']}"
            foodb_key = _add_foodb_food(
                builder,
                row.get("source_food_id", ""),
                row.get("matched_food_name", ""),
                category=row.get("matched_category", ""),
            )
            builder.add_edge(
                canonical_key,
                foodb_key,
                "mapped_to_foodb",
                **_attrs(
                    candidate_rank=row.get("candidate_rank", ""),
                    score=float(row.get("match_score", 0) or 0),
                    confidence=row.get("confidence", ""),
                    stage=row.get("stage", ""),
                    needs_human_review=bool(row.get("needs_human_review", False)),
                ),
            )

    if foodb_compounds_path.exists():
        usecols = [
            "foodb_food_id",
            "foodb_food_name",
            "foodb_compound_public_id",
            "foodb_compound_id",
            "compound_name",
            "inchikey",
            "chemical_class",
            "chemical_subclass",
            "chemical_superclass",
            "kingdom",
        ]
        seen_foodb_compounds = set()
        for chunk in pd.read_csv(
            foodb_compounds_path,
            dtype=str,
            usecols=lambda col: col in usecols,
            chunksize=300000,
        ):
            chunk = chunk.fillna("")
            chunk = chunk[chunk["foodb_compound_public_id"].ne("") | chunk["foodb_compound_id"].ne("")]
            for _, row in chunk.drop_duplicates(["foodb_food_id", "foodb_compound_public_id", "foodb_compound_id"]).iterrows():
                foodb_compound_id = row.get("foodb_compound_public_id", "") or row.get("foodb_compound_id", "")
                key = (row.get("foodb_food_id", ""), foodb_compound_id)
                if key in seen_foodb_compounds:
                    continue
                seen_foodb_compounds.add(key)
                foodb_food_key = _add_foodb_food(
                    builder,
                    row.get("foodb_food_id", ""),
                    row.get("foodb_food_name", ""),
                )
                foodb_compound_key = _add_foodb_compound(
                    builder,
                    foodb_compound_id,
                    row.get("compound_name", ""),
                    numeric_foodb_compound_id=row.get("foodb_compound_id", ""),
                    inchikey=row.get("inchikey", ""),
                    kingdom=row.get("kingdom", ""),
                    chemical_class=row.get("chemical_class", ""),
                    chemical_subclass=row.get("chemical_subclass", ""),
                    chemical_superclass=row.get("chemical_superclass", ""),
                )
                builder.add_edge(
                    foodb_food_key,
                    foodb_compound_key,
                    "foodb_contains_compound",
                    **_attrs(foodb_compound_id=row.get("foodb_compound_id", "")),
                )

    if not hmdb_edges.empty:
        edge_subset = hmdb_edges.dropna(subset=["canonical_food_id", "foodb_compound_id", "hmdb_id"]).copy()
        for _, row in edge_subset.iterrows():
            canonical_key = f"canonical_food:{row['canonical_food_id']}"
            foodb_food_key = _add_foodb_food(
                builder,
                row.get("foodb_food_id", ""),
                row.get("foodb_food_name", ""),
            )
            foodb_compound_key = _add_foodb_compound(
                builder,
                row.get("foodb_compound_public_id", row.get("foodb_compound_id", "")),
                row.get("compound_name", ""),
                numeric_foodb_compound_id=row.get("foodb_compound_id", ""),
                inchikey=row.get("inchikey", ""),
                pubchem_compound_id=row.get("pubchem_compound_id", ""),
                chebi_id=row.get("chebi_id", ""),
                kegg_id=row.get("kegg_id", ""),
                kingdom=row.get("kingdom", ""),
                super_class=row.get("super_class", ""),
                chemical_class=row.get("class", ""),
                sub_class=row.get("sub_class", ""),
                direct_parent=row.get("direct_parent", ""),
            )
            hmdb_key = _add_hmdb_metabolite(
                builder,
                row.get("hmdb_id", ""),
                row.get("hmdb_name", ""),
                biospecimen=row.get("biospecimen", ""),
                disease_names=row.get("disease_names", ""),
                pathway_names=row.get("pathway_names", ""),
            )
            builder.add_edge(canonical_key, foodb_food_key, "mapped_to_foodb")
            builder.add_edge(foodb_food_key, foodb_compound_key, "foodb_contains_compound")
            builder.add_edge(
                foodb_compound_key,
                hmdb_key,
                "linked_to_hmdb_metabolite",
                **_attrs(
                    method=row.get("hmdb_link_method", ""),
                    inchikey=row.get("inchikey", ""),
                    foodb_id=row.get("foodb_id", ""),
                ),
            )
            biospecimen = _clean(row.get("biospecimen", ""))
            if biospecimen:
                biospecimen_key = builder.add_node("hmdb_biospecimen", biospecimen, biospecimen, source="HMDB")
                builder.add_edge(hmdb_key, biospecimen_key, "hmdb_observed_in_biospecimen")

    for _, row in foodatlas_human.iterrows():
        hpp_key = f"hpp_food:{row['hpp_food_id']}"
        foodatlas_key = _add_foodatlas_food(builder, row.get("foodatlas_id", ""), row.get("foodatlas_name", ""))
        builder.add_edge(
            hpp_key,
            foodatlas_key,
            "human_corrected_foodatlas_candidate",
            **_attrs(
                human_food_name=row.get("human_food_name", ""),
                score=float(row.get("match_score", 0) or 0),
                confidence=row.get("confidence", ""),
                status=row.get("status", ""),
            ),
        )

    for _, row in human_corrections.iterrows():
        hpp_key = f"hpp_food:{row['hpp_food_id']}"
        correction_key = builder.add_node(
            "human_correction",
            row["hpp_food_id"],
            row.get("human_food_name", ""),
            **_attrs(
                human_category=row.get("human_category", ""),
                human_notes=row.get("human_notes", ""),
                remap_source=row.get("remap_source", ""),
                remap_source_food_id=row.get("remap_source_food_id", ""),
                remap_food_name=row.get("remap_food_name", ""),
                remap_score=row.get("remap_score", ""),
                remap_confidence=row.get("remap_confidence", ""),
            ),
        )
        builder.add_edge(hpp_key, correction_key, "has_human_correction")

    for _, row in openai_validated.iterrows():
        hpp_key = f"hpp_food:{row['hpp_food_id']}"
        source_key = _add_source_food(builder, row)
        builder.add_edge(
            hpp_key,
            source_key,
            "openai_validated_candidate",
            **_attrs(
                embedding_score=float(row.get("embedding_score", 0) or 0),
                retrieval_confidence=row.get("confidence", ""),
                gpt_equivalent=row.get("gpt_equivalent", ""),
                gpt_confidence=row.get("gpt_confidence", ""),
                gpt_reason=row.get("gpt_reason", ""),
                stage=row.get("stage", ""),
            ),
        )

    if not nutrients.empty:
        nutrient_rows = nutrients if include_all_nutrients else nutrients.head(0)
        for _, row in nutrient_rows.iterrows():
            canonical_key = f"canonical_food:{row['canonical_food_id']}"
            nutrient_key = builder.add_node(
                "nutrient",
                row["nutrient_name"],
                row["nutrient_name"],
                **_attrs(unit_status=row.get("unit_status", "")),
            )
            builder.add_edge(
                canonical_key,
                nutrient_key,
                "has_nutrient_value",
                **_attrs(
                    value=float(row.get("final_value", 0) or 0),
                    unit_status=row.get("unit_status", ""),
                    chosen_source=row.get("chosen_source", ""),
                    source_food_id=row.get("source_food_id", ""),
                    confidence=row.get("confidence", ""),
                    method=row.get("method", ""),
                    hpp_value=row.get("hpp_value", ""),
                    mapped_value=row.get("mapped_value", ""),
                    hpp_observation_count=row.get("hpp_observation_count", ""),
                    mapped_observation_count=row.get("mapped_observation_count", ""),
                ),
            )

    graph = builder.to_graph()
    node_counts = Counter(node["kind"] for node in graph["nodes"])
    edge_counts = Counter(edge["relation"] for edge in graph["edges"])
    graph["metadata"].update(
        {
            "updated_at": now(),
            "node_count": len(graph["nodes"]),
            "edge_count": len(graph["edges"]),
            "node_counts_by_kind": dict(sorted(node_counts.items())),
            "edge_counts_by_relation": dict(sorted(edge_counts.items())),
        }
    )

    graph_path = OUT / "final_food_kg.json"
    nodes_path = OUT / "final_food_kg_nodes.csv"
    edges_path = OUT / "final_food_kg_edges.csv"
    summary_path = OUT / "final_food_kg_summary.json"
    save_graph(graph, graph_path)
    pd.DataFrame(graph["nodes"]).to_csv(nodes_path, index=False)
    pd.DataFrame(graph["edges"]).to_csv(edges_path, index=False)

    summary = {
        "graph": str(graph_path),
        "nodes": str(nodes_path),
        "edges": str(edges_path),
        "node_count": len(graph["nodes"]),
        "edge_count": len(graph["edges"]),
        "node_counts_by_kind": dict(sorted(node_counts.items())),
        "edge_counts_by_relation": dict(sorted(edge_counts.items())),
        "include_all_nutrients": include_all_nutrients,
        "include_foodatlas_native": include_foodatlas_native,
    }
    summary_path.write_text(json.dumps(summary, indent=2))
    return summary


def main():
    print(json.dumps(build_final_kg(), indent=2))


if __name__ == "__main__":
    main()
