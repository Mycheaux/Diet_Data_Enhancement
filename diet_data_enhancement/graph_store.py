import json
from datetime import datetime, timezone
from pathlib import Path


def empty_graph():
    return {"nodes": [], "edges": [], "metadata": {"created_at": now(), "updated_at": now()}}


def now():
    return datetime.now(timezone.utc).isoformat()


def load_graph(path):
    path = Path(path)
    if not path.exists():
        return empty_graph()
    return json.loads(path.read_text())


def save_graph(graph, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    graph["metadata"]["updated_at"] = now()
    path.write_text(json.dumps(graph, indent=2, ensure_ascii=False))


def _node_key(kind, node_id):
    return f"{kind}:{node_id}"


def upsert_node(graph, kind, node_id, label, **attrs):
    key = _node_key(kind, node_id)
    for node in graph["nodes"]:
        if node["key"] == key:
            node.update({"label": label, **attrs})
            return key
    graph["nodes"].append({"key": key, "kind": kind, "id": str(node_id), "label": label, **attrs})
    return key


def upsert_edge(graph, source_key, target_key, relation, **attrs):
    for edge in graph["edges"]:
        if edge["source"] == source_key and edge["target"] == target_key and edge["relation"] == relation:
            edge.update(attrs)
            return
    graph["edges"].append({"source": source_key, "target": target_key, "relation": relation, **attrs})


def add_mapping(graph, hpp_row, mapping_row, relation="mapped_to"):
    hpp_key = upsert_node(
        graph,
        "hpp_food",
        hpp_row["hpp_food_id"],
        hpp_row["hpp_food_name"],
        category=hpp_row.get("hpp_category", ""),
    )
    source_key = upsert_node(
        graph,
        "source_food",
        f"{mapping_row.get('source', '')}:{mapping_row.get('source_food_id', '')}",
        mapping_row.get("matched_food_name", ""),
        source=mapping_row.get("source", ""),
        category=mapping_row.get("matched_category", ""),
    )
    upsert_edge(
        graph,
        hpp_key,
        source_key,
        relation,
        score=float(mapping_row.get("match_score", 0) or 0),
        confidence=mapping_row.get("confidence", ""),
        stage=mapping_row.get("stage", ""),
    )


def graph_from_mappings(mapping_df):
    graph = empty_graph()
    best = mapping_df.sort_values(["hpp_food_id", "candidate_rank"]).groupby("hpp_food_id").head(1)
    for _, row in best.iterrows():
        if not row.get("matched_food_name"):
            continue
        add_mapping(graph, row, row)
    return graph
