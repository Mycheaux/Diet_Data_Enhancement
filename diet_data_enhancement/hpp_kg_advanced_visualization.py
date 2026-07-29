import json
import math
from collections import defaultdict
from pathlib import Path

import pandas as pd

from .sources import ROOT


OUT = ROOT / "outputs/visualizations"
DENOVO = ROOT / "outputs/enhanced_hpp/1.denovo"
KG = DENOVO / "kg"
LAYER_TABLES = DENOVO / "layer_tables"

NODE_COLORS = {
    "hpp_food": "#2563eb",
    "canonical_food": "#0f766e",
    "openfoodfacts_product": "#16a34a",
    "nutrient": "#f59e0b",
    "foodatlas_chemical": "#d69e2e",
    "chemical_class": "#ca8a04",
    "chemical_superclass": "#a16207",
    "hmdb_metabolite": "#7c3aed",
    "hmdb_biospecimen": "#0891b2",
    "disease": "#ef4444",
    "pathway": "#8b5cf6",
    "nova_group": "#db2777",
    "nutriscore_grade": "#65a30d",
}

EDGE_COLORS = {
    "has_canonical_helper": "#64748b",
    "inherits_product_processing_match": "#16a34a",
    "has_nutrient_amount_per_100g": "#f59e0b",
    "has_nova_group": "#db2777",
    "has_nutriscore_grade": "#65a30d",
    "foodatlas_contains": "#d69e2e",
    "biological_display_to_chemical": "#ca8a04",
    "nutrient_chemical_name_match": "#06b6d4",
    "biological_display_to_metabolite": "#7c3aed",
    "biological_display_to_biospecimen": "#0891b2",
    "foodatlas_positively_correlates_with": "#dc2626",
    "foodatlas_negatively_correlates_with": "#4f46e5",
    "hmdb_disease_annotation": "#ef4444",
    "hmdb_pathway_annotation": "#8b5cf6",
}

STAGE = {
    "hpp_food": 0,
    "canonical_food": 1,
    "openfoodfacts_product": 1,
    "nutrient": 1,
    "nova_group": 1,
    "nutriscore_grade": 1,
    "foodatlas_chemical": 2,
    "chemical_class": 2,
    "chemical_superclass": 2,
    "hmdb_metabolite": 3,
    "hmdb_biospecimen": 3,
    "disease": 4,
    "pathway": 4,
}

PRIORITY_NUTRIENTS = [
    "Energy",
    "Protein",
    "Total lipid (fat)",
    "Carbohydrate, by difference",
    "Water",
    "Fiber, total dietary",
    "Sugars, Total",
    "Sodium, Na",
    "Calcium, Ca",
    "Iron, Fe",
    "Potassium, K",
    "Caffeine",
    "Theobromine",
]


def _read_csv(path, **kwargs):
    return pd.read_csv(path, dtype=str, **kwargs).fillna("")


def _load_inputs():
    nodes = _read_csv(KG / "hpp_scenario_kg_nodes.csv")
    edges = _read_csv(KG / "hpp_scenario_kg_edges.csv")
    disease = _read_csv(LAYER_TABLES / "layer5_disease_pathway_reference.csv")
    compound_reference_path = ROOT / "outputs/reference/canonical_food_compound_reference.csv"
    hmdb_edges_path = ROOT / "outputs/reference/canonical_food_hmdb_metabolite_edges.csv"
    hmdb_index_path = ROOT / "outputs/layered/layer4_hmdb_metabolite_index.csv"
    final_edges_path = ROOT / "outputs/kg/final_food_kg_edges.csv"
    final_nodes_path = ROOT / "outputs/kg/final_food_kg_nodes.csv"
    compound_reference = _read_csv(compound_reference_path) if compound_reference_path.exists() else pd.DataFrame()
    hmdb_edges = _read_csv(hmdb_edges_path) if hmdb_edges_path.exists() else pd.DataFrame()
    hmdb_index = _read_csv(hmdb_index_path) if hmdb_index_path.exists() else pd.DataFrame()
    if final_edges_path.exists():
        final_edges = pd.read_csv(final_edges_path, dtype=str, usecols=["source", "target", "relation"]).fillna("")
    else:
        final_edges = pd.DataFrame(columns=["source", "target", "relation"])
    if final_nodes_path.exists():
        final_nodes = pd.read_csv(final_nodes_path, dtype=str, usecols=["key", "kind", "label"]).fillna("")
    else:
        final_nodes = pd.DataFrame(columns=["key", "kind", "label"])
    return nodes, edges, disease, compound_reference, hmdb_edges, hmdb_index, final_edges, final_nodes


def _split_pipe(value, limit=None):
    values = [item.strip() for item in str(value or "").split("|") if item.strip()]
    return values[:limit] if limit else values


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _disease_key(name):
    return f"disease:{str(name).strip()}"


def _pathway_key(name):
    return f"pathway:{str(name).strip()}"


def _priority_nutrient_edges(nutrient_edges, per_food):
    priority = {f"nutrient:{name}": i for i, name in enumerate(PRIORITY_NUTRIENTS)}
    rows = []
    for source, group in nutrient_edges.groupby("source", sort=False):
        chosen = group.copy()
        chosen["_rank"] = chosen["target"].map(priority).fillna(999).astype(int)
        rows.append(chosen.sort_values(["_rank", "target"]).head(per_food).drop(columns=["_rank"]))
    if not rows:
        return nutrient_edges.head(0)
    return pd.concat(rows, ignore_index=True)


def _node_record(key, row=None, kind=None, label=None):
    if row is not None:
        kind = kind or row.get("kind", "")
        label = label or row.get("label", key)
    kind = kind or key.split(":", 1)[0]
    label = label or key
    return {
        "key": key,
        "kind": kind,
        "label": str(label),
        "color": NODE_COLORS.get(kind, "#94a3b8"),
        "stage": STAGE.get(kind, 2),
    }


def _add_node(nodes, key, row=None, kind=None, label=None):
    if key not in nodes:
        nodes[key] = _node_record(key, row=row, kind=kind, label=label)
    return nodes[key]


def _add_edge(edges, source, target, relation, title="", value="", sign=""):
    if not source or not target or source == target:
        return
    item = {
        "source": source,
        "target": target,
        "relation": relation,
        "color": EDGE_COLORS.get(relation, "#94a3b8"),
        "title": title or relation,
        "value": str(value or ""),
        "sign": sign,
    }
    edge_key = (item["source"], item["target"], item["relation"], item["value"])
    if edge_key not in edges["_seen"]:
        edges["_seen"].add(edge_key)
        edges["rows"].append(item)


def _build_display_graph(food_query=None, full=False):
    raw_nodes, raw_edges, disease_table, compound_reference, hmdb_edges, hmdb_index, final_edges, final_nodes = _load_inputs()
    lookup = {row["key"]: row.to_dict() for _, row in raw_nodes.iterrows()}
    final_lookup = {row["key"]: row.to_dict() for _, row in final_nodes.iterrows()}
    disease_lookup = {f"hpp_food:{row['hpp_food_id']}": row.to_dict() for _, row in disease_table.iterrows()}
    hpp_nodes = raw_nodes[raw_nodes["kind"].eq("hpp_food")].copy()
    if food_query:
        mask = hpp_nodes["label"].str.contains(food_query, case=False, na=False)
        hpp_keys = hpp_nodes[mask]["key"].head(1).tolist()
    else:
        hpp_keys = []
    if not hpp_keys:
        hpp_keys = hpp_nodes[hpp_nodes["label"].str.contains("coffee", case=False, na=False)]["key"].head(1).tolist()
    if not hpp_keys:
        hpp_keys = hpp_nodes["key"].head(1).tolist()

    relation_groups = {name: group.copy() for name, group in raw_edges.groupby("relation", sort=False)}
    if full:
        hpp_keys = hpp_nodes["key"].tolist()

    hpp_set = set(hpp_keys)
    visual_nodes = {}
    visual_edges = {"rows": [], "_seen": set()}
    for key in hpp_keys:
        _add_node(visual_nodes, key, row=lookup.get(key))

    canonical_edges = relation_groups.get("has_canonical_helper", raw_edges.head(0))
    product_edges = relation_groups.get("inherits_product_processing_match", raw_edges.head(0))
    nutrient_edges = relation_groups.get("has_nutrient_amount_per_100g", raw_edges.head(0))
    nova_edges = relation_groups.get("has_nova_group", raw_edges.head(0))
    nutriscore_edges = relation_groups.get("has_nutriscore_grade", raw_edges.head(0))
    chem_edges = pd.concat(
        [
            relation_groups.get("linked_to_foodb_chemical_class", raw_edges.head(0)),
            relation_groups.get("linked_to_foodb_chemical_superclass", raw_edges.head(0)),
        ],
        ignore_index=True,
    )
    biospecimen_edges = relation_groups.get("linked_to_hmdb_biospecimen", raw_edges.head(0))
    hmdb_disease_edges = relation_groups.get("linked_to_hmdb_disease_annotation", raw_edges.head(0))
    pathway_edges = relation_groups.get("linked_to_hmdb_pathway_annotation", raw_edges.head(0))
    signed_foodatlas_edges = final_edges[
        final_edges["relation"].isin(
            ["foodatlas_positively_correlates_with", "foodatlas_negatively_correlates_with"]
        )
    ].copy()
    signed_by_chemical = {
        source: group
        for source, group in signed_foodatlas_edges.groupby("source", sort=False)
    }
    compound_by_canonical = {}
    if not compound_reference.empty:
        compound_by_canonical = {
            canonical_id: group.drop_duplicates(["foodatlas_chemical_id", "compound_name"])
            for canonical_id, group in compound_reference.groupby("canonical_food_id", sort=False)
        }
    hmdb_by_canonical = {}
    if not hmdb_edges.empty:
        hmdb_by_canonical = {
            canonical_id: group.drop_duplicates(["hmdb_id", "hmdb_name", "biospecimen"])
            for canonical_id, group in hmdb_edges.groupby("canonical_food_id", sort=False)
        }
    hmdb_by_name = {}
    if not hmdb_index.empty:
        hmdb_index["_name_norm"] = hmdb_index["hmdb_name"].str.lower().str.strip()
        hmdb_by_name = {
            name: group
            for name, group in hmdb_index.groupby("_name_norm", sort=False)
        }

    nutrient_keep = _priority_nutrient_edges(nutrient_edges[nutrient_edges["source"].isin(hpp_set)], 8 if full else 14)
    nutrient_by_source = {source: group.copy() for source, group in nutrient_keep.groupby("source", sort=False)}
    chem_by_source = {source: group["target"].drop_duplicates().tolist() for source, group in chem_edges[chem_edges["source"].isin(hpp_set)].groupby("source", sort=False)}
    biospecimen_by_source = {source: group["target"].drop_duplicates().tolist() for source, group in biospecimen_edges[biospecimen_edges["source"].isin(hpp_set)].groupby("source", sort=False)}
    hmdb_disease_by_source = {source: group["target"].drop_duplicates().tolist() for source, group in hmdb_disease_edges[hmdb_disease_edges["source"].isin(hpp_set)].groupby("source", sort=False)}
    pathway_by_source = {source: group["target"].drop_duplicates().tolist() for source, group in pathway_edges[pathway_edges["source"].isin(hpp_set)].groupby("source", sort=False)}
    simple_sources = [
        canonical_edges,
        product_edges,
        nutrient_keep,
        nova_edges,
        nutriscore_edges,
    ]
    for frame in simple_sources:
        for _, row in frame[frame["source"].isin(hpp_set)].iterrows():
            source = row["source"]
            target = row["target"]
            _add_node(visual_nodes, source, row=lookup.get(source))
            _add_node(visual_nodes, target, row=lookup.get(target))
            _add_edge(
                visual_edges,
                source,
                target,
                row["relation"],
                value=row.get("value", ""),
                title=f"{row['relation']} {row.get('value', '')}".strip(),
            )

    anchors = {}
    for hpp_key in hpp_keys:
        product = product_edges[product_edges["source"].eq(hpp_key)]["target"].head(1).tolist()
        canonical = canonical_edges[canonical_edges["source"].eq(hpp_key)]["target"].head(1).tolist()
        anchors[hpp_key] = product[0] if product else canonical[0] if canonical else hpp_key
        if anchors[hpp_key] not in visual_nodes:
            _add_node(visual_nodes, anchors[hpp_key], row=lookup.get(anchors[hpp_key]))

    def top_targets(source_map, source, limit):
        return source_map.get(source, [])[:limit]

    for hpp_key in hpp_keys:
        anchor = anchors[hpp_key]
        disease_info = disease_lookup.get(hpp_key, {})
        canonical_id = disease_info.get("canonical_food_id", "")
        hpp_nutrients = nutrient_by_source.get(hpp_key, nutrient_keep.head(0))
        nutrient_keys = hpp_nutrients["target"].drop_duplicates().tolist()
        chemicals = top_targets(chem_by_source, hpp_key, 8 if full else 16)
        for chem_key in chemicals:
            _add_node(visual_nodes, chem_key, row=lookup.get(chem_key))
            _add_edge(visual_edges, hpp_key, chem_key, "biological_display_to_chemical", title="food to food chemical class")

        foodatlas_chemical_nodes = []
        if canonical_id and canonical_id in compound_by_canonical:
            fa_compounds = compound_by_canonical[canonical_id].head(3 if full else 10)
            for _, compound_row in fa_compounds.iterrows():
                chemical_id = compound_row.get("foodatlas_chemical_id", "")
                if not chemical_id:
                    continue
                chemical_key = f"foodatlas_chemical:{chemical_id}"
                chemical_label = compound_row.get("compound_name", chemical_id)
                _add_node(visual_nodes, chemical_key, kind="foodatlas_chemical", label=chemical_label)
                _add_edge(visual_edges, hpp_key, chemical_key, "foodatlas_contains", title="food to FoodAtlas chemical")
                foodatlas_chemical_nodes.append(chemical_key)
                chemical_norm = str(chemical_label).lower().strip()
                for nutrient_key in nutrient_keys:
                    nutrient_label = lookup.get(nutrient_key, {}).get("label", nutrient_key.split(":", 1)[-1])
                    if chemical_norm and chemical_norm == str(nutrient_label).lower().strip():
                        _add_edge(
                            visual_edges,
                            nutrient_key,
                            chemical_key,
                            "nutrient_chemical_name_match",
                            title="ancillary nutrient-to-chemical name match",
                        )
                signed_rows = signed_by_chemical.get(chemical_key, pd.DataFrame()).head(3 if full else 8)
                for _, signed_row in signed_rows.iterrows():
                    disease_key = signed_row["target"]
                    disease_node = final_lookup.get(disease_key, {})
                    disease_label = disease_node.get("label", disease_key.split(":", 1)[-1])
                    unified_disease_key = _disease_key(disease_label)
                    _add_node(visual_nodes, unified_disease_key, kind="disease", label=disease_label)
                    relation = signed_row["relation"]
                    sign = "positive" if "positively" in relation else "negative"
                    _add_edge(
                        visual_edges,
                        chemical_key,
                        unified_disease_key,
                        relation,
                        sign=sign,
                        title=relation.replace("_", " "),
                    )

        metabolite_keys = []
        if canonical_id and canonical_id in hmdb_by_canonical:
            hmdb_rows = hmdb_by_canonical[canonical_id].head(3 if full else 10)
            for _, hmdb_row in hmdb_rows.iterrows():
                hmdb_id = hmdb_row.get("hmdb_id", "")
                if not hmdb_id:
                    continue
                metabolite_key = f"hmdb_metabolite:{hmdb_id}"
                metabolite_label = hmdb_row.get("hmdb_name", hmdb_id)
                _add_node(visual_nodes, metabolite_key, kind="hmdb_metabolite", label=metabolite_label)
                _add_edge(visual_edges, hpp_key, metabolite_key, "biological_display_to_metabolite", title="food to HMDB metabolite")
                metabolite_keys.append(metabolite_key)
                for chem_key in (foodatlas_chemical_nodes[:3] or chemicals[:3]):
                    _add_edge(visual_edges, chem_key, metabolite_key, "biological_display_to_metabolite", title="ancillary chemical-to-HMDB metabolite bridge")

                hmdb_node = final_lookup.get(metabolite_key, {})
                disease_names = _split_pipe(hmdb_node.get("disease_names", ""), 3 if full else 8)
                pathway_names = _split_pipe(hmdb_node.get("pathway_names", ""), 2 if full else 6)
                if not disease_names:
                    index_rows = hmdb_by_name.get(str(metabolite_label).lower().strip(), pd.DataFrame())
                    if not index_rows.empty:
                        disease_names = _split_pipe(index_rows.iloc[0].get("disease_names", ""), 3 if full else 8)
                        pathway_names = pathway_names or _split_pipe(index_rows.iloc[0].get("pathway_names", ""), 2 if full else 6)
                for disease_name in disease_names:
                    disease_key = _disease_key(disease_name)
                    _add_node(visual_nodes, disease_key, kind="disease", label=disease_name)
                    _add_edge(visual_edges, metabolite_key, disease_key, "hmdb_disease_annotation", title="HMDB metabolite disease annotation")
                for pathway_name in pathway_names:
                    pathway_key = _pathway_key(pathway_name)
                    _add_node(visual_nodes, pathway_key, kind="pathway", label=pathway_name)
                    _add_edge(visual_edges, metabolite_key, pathway_key, "hmdb_pathway_annotation", title="HMDB metabolite pathway annotation")

        for nutrient_key in nutrient_keys:
            nutrient_label = lookup.get(nutrient_key, {}).get("label", nutrient_key.split(":", 1)[-1])
            index_rows = hmdb_by_name.get(str(nutrient_label).lower().strip(), pd.DataFrame())
            if index_rows.empty:
                continue
            for disease_name in _split_pipe(index_rows.iloc[0].get("disease_names", ""), 2 if full else 5):
                disease_key = _disease_key(disease_name)
                _add_node(visual_nodes, disease_key, kind="disease", label=disease_name)
                _add_edge(visual_edges, nutrient_key, disease_key, "hmdb_disease_annotation", title="nutrient name matched to HMDB metabolite disease annotation")

        for biospecimen_key in top_targets(biospecimen_by_source, hpp_key, 3 if full else 6):
            _add_node(visual_nodes, biospecimen_key, row=lookup.get(biospecimen_key))
            for metabolite_key in metabolite_keys[:2 if full else 5]:
                _add_edge(visual_edges, metabolite_key, biospecimen_key, "biological_display_to_biospecimen", title="HMDB metabolite observed in biofluid")

        disease_targets = top_targets(hmdb_disease_by_source, hpp_key, 4 if full else 12)
        pathway_targets = top_targets(pathway_by_source, hpp_key, 3 if full else 10)
        for target in disease_targets:
            _add_node(visual_nodes, target, row=lookup.get(target))
            for metabolite_key in metabolite_keys[:2 if full else 5]:
                _add_edge(visual_edges, metabolite_key, target, "hmdb_disease_annotation")
        for target in pathway_targets:
            _add_node(visual_nodes, target, row=lookup.get(target))
            for metabolite_key in metabolite_keys[:2 if full else 5]:
                _add_edge(visual_edges, metabolite_key, target, "hmdb_pathway_annotation")

    return {
        "nodes": list(visual_nodes.values()),
        "edges": visual_edges["rows"],
        "source": "outputs/enhanced_hpp/1.denovo/kg",
        "full_source_node_count": int(raw_nodes.shape[0]),
        "full_source_edge_count": int(raw_edges.shape[0]),
    }


def _pack_graph(graph, layout):
    nodes = [dict(node) for node in graph["nodes"]]
    if layout == "radial":
        _layout_radial(nodes)
    elif layout == "flexible":
        _layout_flexible(nodes)
    else:
        _layout_staged(nodes)
    index = {node["key"]: i for i, node in enumerate(nodes)}
    packed_edges = []
    for edge in graph["edges"]:
        if edge["source"] in index and edge["target"] in index:
            packed_edges.append(
                {
                    "s": index[edge["source"]],
                    "t": index[edge["target"]],
                    "r": edge["relation"],
                    "c": edge["color"],
                    "g": edge.get("sign", ""),
                    "v": edge.get("value", ""),
                }
            )
    packed_nodes = [
        {
            "k": node["key"],
            "l": node["label"],
            "t": node["kind"],
            "c": node["color"],
            "st": node.get("stage", STAGE.get(node["kind"], 2)),
            "x": round(node["x"], 2),
            "y": round(node["y"], 2),
        }
        for node in nodes
    ]
    return {
        "nodes": packed_nodes,
        "edges": packed_edges,
        "nodeColors": NODE_COLORS,
        "edgeColors": EDGE_COLORS,
        "layout": layout,
    }


def _layout_staged(nodes):
    grouped = defaultdict(list)
    for node in nodes:
        grouped[node["stage"]].append(node)
    x_by_stage = {0: 130, 1: 420, 2: 760, 3: 1080, 4: 1410}
    for stage, group in grouped.items():
        count = len(group)
        for i, node in enumerate(group):
            node["x"] = x_by_stage.get(stage, 760)
            node["y"] = 90 + (i + 1) * (720 / (count + 1))


def _spiral_positions(group, cx, cy, spacing):
    golden = math.pi * (3 - math.sqrt(5))
    for i, node in enumerate(group):
        radius = spacing * math.sqrt(i + 1)
        angle = i * golden
        node["x"] = cx + math.cos(angle) * radius
        node["y"] = cy + math.sin(angle) * radius


def _layout_flexible(nodes):
    centers = {
        "hpp_food": (-1750, -260, 22),
        "canonical_food": (-1020, 330, 18),
        "openfoodfacts_product": (-620, -930, 24),
        "nutrient": (-620, 1120, 19),
        "chemical_class": (420, -560, 17),
        "chemical_superclass": (620, 80, 17),
        "hmdb_metabolite": (1300, -320, 20),
        "hmdb_biospecimen": (1660, 300, 24),
        "disease": (2520, -230, 20),
        "pathway": (2850, 620, 20),
        "nova_group": (-220, -1240, 25),
        "nutriscore_grade": (-180, -1040, 25),
    }
    grouped = defaultdict(list)
    for node in nodes:
        grouped[node["kind"]].append(node)
    for kind, group in grouped.items():
        cx, cy, spacing = centers.get(kind, (0, 0, 24))
        _spiral_positions(group, cx, cy, spacing)


def _layout_radial(nodes):
    rings = {
        "hpp_food": 180,
        "canonical_food": 520,
        "openfoodfacts_product": 760,
        "nutrient": 980,
        "nova_group": 1140,
        "nutriscore_grade": 1220,
        "chemical_class": 1450,
        "chemical_superclass": 1680,
        "hmdb_metabolite": 1950,
        "hmdb_biospecimen": 2200,
        "pathway": 3020,
        "disease": 3380,
    }
    grouped = defaultdict(list)
    for node in nodes:
        grouped[node["kind"]].append(node)
    for kind, group in grouped.items():
        radius = rings.get(kind, 2400)
        for i, node in enumerate(group):
            angle = (2 * math.pi * i) / max(1, len(group))
            node["x"] = math.cos(angle) * radius
            node["y"] = math.sin(angle) * radius


def _write_js(path, packed):
    path.write_text("window.DENOVO_KG_DATA = " + json.dumps(packed, ensure_ascii=False) + ";\n")


def _html(title, data_file, start_scale, details, default_show_edges=False):
    checked = " checked" if default_show_edges else ""
    show_edges_js = "true" if default_show_edges else "false"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:#f8fafc; color:#0f172a; overflow:hidden; }}
header {{ height:64px; display:flex; align-items:center; gap:12px; padding:0 16px; background:#ffffff; border-bottom:1px solid #dbe4ee; box-sizing:border-box; }}
h1 {{ margin:0; font-size:17px; font-weight:700; white-space:nowrap; }}
input, select, button {{ border:1px solid #cbd5e1; background:#ffffff; color:#0f172a; border-radius:6px; padding:7px 9px; font:inherit; }}
button {{ cursor:pointer; }}
#canvas {{ display:block; width:100vw; height:calc(100vh - 64px); background:#f8fafc; }}
#panel {{ position:fixed; right:14px; top:78px; width:340px; max-height:calc(100vh - 98px); overflow:auto; background:rgba(255,255,255,.95); border:1px solid #cbd5e1; border-radius:8px; padding:14px; box-shadow:0 14px 36px rgba(15,23,42,.16); box-sizing:border-box; }}
#tooltip {{ position:fixed; display:none; pointer-events:none; max-width:300px; background:rgba(15,23,42,.95); color:#fff; border-radius:6px; padding:7px 9px; font-size:12px; line-height:1.35; z-index:20; }}
.muted {{ color:#64748b; font-size:12px; }}
.legend {{ display:grid; grid-template-columns:1fr 1fr; gap:6px; font-size:12px; margin-top:8px; }}
.legend-item {{ cursor:pointer; user-select:none; padding:4px 5px; border-radius:5px; }}
.legend-item:hover {{ background:#edf2f7; }}
.legend-item.off {{ opacity:.35; text-decoration:line-through; }}
.dot {{ display:inline-block; width:11px; height:11px; border-radius:50%; margin-right:6px; vertical-align:-1px; }}
.row {{ margin-top:10px; }}
</style>
</head>
<body>
<header>
<h1>{title}</h1>
<input id="search" placeholder="Search node" size="26">
<button id="find">Find</button>
<label>degree <select id="degree"><option value="1">1</option><option value="2">2</option><option value="3">3</option><option value="4" selected>4</option></select></label>
<label><input type="checkbox" id="allEdges"{checked}> all edges</label>
<button id="reset">Reset</button>
<span id="status" class="muted"></span>
</header>
<canvas id="canvas"></canvas>
<div id="tooltip"></div>
<aside id="panel">
<div class="muted">{details}</div>
<div class="legend" id="legend"></div>
<div id="details" class="row">Click a node to highlight outgoing biological paths up to the selected degree.</div>
</aside>
<script src="{data_file}"></script>
<script>
const data = window.DENOVO_KG_DATA;
const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');
const tooltip = document.getElementById('tooltip');
const nodes = data.nodes;
const edges = data.edges;
const incidentOut = new Map();
const incidentAny = new Map();
for (const e of edges) {{
  if (!incidentOut.has(e.s)) incidentOut.set(e.s, []);
  if (!incidentAny.has(e.s)) incidentAny.set(e.s, []);
  if (!incidentAny.has(e.t)) incidentAny.set(e.t, []);
  incidentOut.get(e.s).push(e);
  incidentAny.get(e.s).push(e);
  incidentAny.get(e.t).push(e);
}}
let scale = {start_scale};
let tx = innerWidth / 2;
let ty = (innerHeight - 64) / 2;
let selected = -1;
let hover = -1;
let showAllEdges = {show_edges_js};
let hiddenKinds = new Set();
let dragging = false;
let last = null;
let neighborhood = {{nodes:new Set(), edges:[]}};

function resize() {{
  canvas.width = innerWidth * devicePixelRatio;
  canvas.height = (innerHeight - 64) * devicePixelRatio;
  canvas.style.height = (innerHeight - 64) + 'px';
  draw();
}}
function sx(x) {{ return x * scale + tx; }}
function sy(y) {{ return y * scale + ty; }}
function wx(x) {{ return (x - tx) / scale; }}
function wy(y) {{ return (y - ty) / scale; }}
function radius(n) {{
  if (n.t === 'hpp_food') return 3.7;
  if (n.t === 'canonical_food') return 3.1;
  if (n.t === 'disease' || n.t === 'pathway') return 2.6;
  return 2.2;
}}
function visibleNode(i) {{ return !hiddenKinds.has(nodes[i].t); }}
function degree() {{ return Number(document.getElementById('degree').value || 4); }}
function computeNeighborhood(start) {{
  if (start < 0) return {{nodes:new Set(), edges:[]}};
  const keep = new Set([start]);
  const localEdges = [];
  let frontier = new Set([start]);
  for (let d = 0; d < degree(); d++) {{
    const next = new Set();
    for (const idx of frontier) {{
      const fromStage = nodes[idx].st ?? 0;
      for (const e of incidentOut.get(idx) || []) {{
        if (!visibleNode(e.t)) continue;
        const toStage = nodes[e.t].st ?? fromStage;
        if (toStage < fromStage) continue;
        localEdges.push(e);
        if (!keep.has(e.t)) {{
          keep.add(e.t);
          next.add(e.t);
        }}
      }}
    }}
    frontier = next;
    if (!frontier.size) break;
  }}
  return {{nodes:keep, edges:localEdges}};
}}
function edgeIsHighlighted(e) {{
  return selected >= 0 && neighborhood.nodes.has(e.s) && neighborhood.nodes.has(e.t);
}}
function draw() {{
  ctx.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);
  ctx.clearRect(0,0,innerWidth,innerHeight-64);
  ctx.fillStyle = '#f8fafc';
  ctx.fillRect(0,0,innerWidth,innerHeight-64);
  const drawEdges = showAllEdges ? edges : neighborhood.edges;
  ctx.globalAlpha = showAllEdges ? 0.08 : 0.72;
  for (const e of drawEdges) {{
    if (!visibleNode(e.s) || !visibleNode(e.t)) continue;
    const a = nodes[e.s], b = nodes[e.t];
    const ax = sx(a.x), ay = sy(a.y), bx = sx(b.x), by = sy(b.y);
    if ((ax < -80 && bx < -80) || (ay < -80 && by < -80) || (ax > innerWidth + 80 && bx > innerWidth + 80) || (ay > innerHeight + 80 && by > innerHeight + 80)) continue;
    const hi = edgeIsHighlighted(e);
    ctx.globalAlpha = hi ? 1 : (showAllEdges ? 0.08 : 0.55);
    ctx.strokeStyle = e.c;
    ctx.lineWidth = hi ? 2.8 : (e.g ? 1.6 : 0.9);
    if (e.g === 'negative') ctx.setLineDash([6,4]); else ctx.setLineDash([]);
    ctx.beginPath();
    ctx.moveTo(ax, ay);
    ctx.lineTo(bx, by);
    ctx.stroke();
  }}
  ctx.setLineDash([]);
  for (let i = 0; i < nodes.length; i++) {{
    if (!visibleNode(i)) continue;
    const n = nodes[i], x = sx(n.x), y = sy(n.y);
    if (x < -30 || y < -30 || x > innerWidth + 30 || y > innerHeight + 30) continue;
    const dim = selected >= 0 && !neighborhood.nodes.has(i);
    ctx.globalAlpha = dim ? 0.08 : 0.92;
    ctx.fillStyle = n.c;
    ctx.beginPath();
    ctx.arc(x, y, Math.max(0.9, radius(n) * Math.sqrt(scale * 12)), 0, Math.PI * 2);
    ctx.fill();
  }}
  ctx.globalAlpha = 1;
  if (selected >= 0) {{
    const n = nodes[selected];
    ctx.strokeStyle = '#020617';
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.arc(sx(n.x), sy(n.y), 7, 0, Math.PI * 2);
    ctx.stroke();
    ctx.fillStyle = '#0f172a';
    ctx.font = '13px system-ui';
    ctx.fillText(n.l.length > 46 ? n.l.slice(0, 43) + '...' : n.l, sx(n.x) + 13, sy(n.y) + 4);
  }}
  if (hover >= 0 && hover !== selected) {{
    const n = nodes[hover];
    ctx.strokeStyle = '#334155';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(sx(n.x), sy(n.y), 5.5, 0, Math.PI * 2);
    ctx.stroke();
  }}
  document.getElementById('status').textContent = nodes.length.toLocaleString() + ' nodes, ' + edges.length.toLocaleString() + ' display edges';
}}
function nearest(clientX, clientY) {{
  const x = clientX, y = clientY - 64;
  let best = -1, bestD = 18 * 18;
  const candidates = selected >= 0 ? neighborhood.nodes : null;
  for (let i = 0; i < nodes.length; i++) {{
    if (!visibleNode(i)) continue;
    if (candidates && !candidates.has(i)) continue;
    const dx = sx(nodes[i].x) - x, dy = sy(nodes[i].y) - y;
    const d = dx * dx + dy * dy;
    if (d < bestD) {{ best = i; bestD = d; }}
  }}
  return best;
}}
function selectNode(i) {{
  selected = i;
  neighborhood = computeNeighborhood(selected);
  const n = nodes[i];
  const direct = (incidentAny.get(i) || []).length;
  document.getElementById('details').innerHTML = '<b>' + n.l + '</b><br><span class="muted">' + n.t + ' · ' + n.k + '</span><br>' + direct.toLocaleString() + ' direct display edges<br>' + neighborhood.nodes.size.toLocaleString() + ' nodes and ' + neighborhood.edges.length.toLocaleString() + ' outgoing biological-path edges within degree ' + degree();
  draw();
}}
function showTip(i, event) {{
  if (i < 0) {{ tooltip.style.display = 'none'; return; }}
  const n = nodes[i];
  tooltip.innerHTML = '<b>' + n.l + '</b><br>' + n.t;
  tooltip.style.left = Math.min(event.clientX + 12, innerWidth - 310) + 'px';
  tooltip.style.top = Math.min(event.clientY + 12, innerHeight - 80) + 'px';
  tooltip.style.display = 'block';
}}
canvas.addEventListener('mousedown', e => {{ last = {{x:e.clientX, y:e.clientY}}; const n = nearest(e.clientX, e.clientY); if (n >= 0) selectNode(n); dragging = n < 0; }});
canvas.addEventListener('mousemove', e => {{
  if (dragging && last) {{
    tx += e.clientX - last.x;
    ty += e.clientY - last.y;
    last = {{x:e.clientX, y:e.clientY}};
    draw();
    return;
  }}
  const n = nearest(e.clientX, e.clientY);
  if (n !== hover) {{ hover = n; draw(); }}
  showTip(n, e);
}});
addEventListener('mouseup', () => {{ dragging = false; last = null; }});
canvas.addEventListener('mouseleave', () => {{ hover = -1; tooltip.style.display = 'none'; draw(); }});
canvas.addEventListener('wheel', e => {{
  e.preventDefault();
  const old = scale;
  scale *= e.deltaY < 0 ? 1.14 : 0.88;
  scale = Math.max(0.01, Math.min(3, scale));
  const mx = e.clientX, my = e.clientY - 64;
  tx = mx - (mx - tx) * (scale / old);
  ty = my - (my - ty) * (scale / old);
  draw();
}}, {{passive:false}});
document.getElementById('allEdges').addEventListener('change', e => {{ showAllEdges = e.target.checked; draw(); }});
document.getElementById('degree').addEventListener('change', () => {{ if (selected >= 0) selectNode(selected); else draw(); }});
document.getElementById('reset').addEventListener('click', () => {{ selected = -1; hover = -1; neighborhood = {{nodes:new Set(), edges:[]}}; scale = {start_scale}; tx = innerWidth / 2; ty = (innerHeight - 64) / 2; tooltip.style.display = 'none'; document.getElementById('details').textContent = 'Click a node to highlight outgoing biological paths up to the selected degree.'; draw(); }});
document.getElementById('find').addEventListener('click', () => {{
  const q = document.getElementById('search').value.trim().toLowerCase();
  if (!q) return;
  const i = nodes.findIndex(n => visibleNode(nodes.indexOf(n)) && (n.l.toLowerCase().includes(q) || n.k.toLowerCase().includes(q)));
  if (i >= 0) {{ tx = innerWidth / 2 - nodes[i].x * scale; ty = (innerHeight - 64) / 2 - nodes[i].y * scale; selectNode(i); }}
}});
document.getElementById('search').addEventListener('keydown', e => {{ if (e.key === 'Enter') document.getElementById('find').click(); }});
const legend = document.getElementById('legend');
Object.entries(data.nodeColors).forEach(([kind, color]) => {{
  const item = document.createElement('div');
  item.className = 'legend-item';
  item.dataset.kind = kind;
  item.innerHTML = '<span class="dot" style="background:' + color + '"></span>' + kind;
  item.addEventListener('click', () => {{
    if (hiddenKinds.has(kind)) {{ hiddenKinds.delete(kind); item.classList.remove('off'); }}
    else {{ hiddenKinds.add(kind); item.classList.add('off'); }}
    if (selected >= 0 && !visibleNode(selected)) selected = -1;
    neighborhood = selected >= 0 ? computeNeighborhood(selected) : {{nodes:new Set(), edges:[]}};
    draw();
  }});
  legend.appendChild(item);
}});
resize();
addEventListener('resize', resize);
</script>
</body>
</html>
"""


def build_denovo_advanced_kg_visualizations(food_query="coffee"):
    OUT.mkdir(parents=True, exist_ok=True)
    focused = _build_display_graph(food_query=food_query, full=False)
    full = _build_display_graph(full=True)

    outputs = {}
    for name, graph, layout, scale, details, default_show_edges in [
        (
            "denovo_hpp_kg_path_explorer",
            focused,
            "staged",
            0.72,
            "Focused de novo HPP biological-path view. Food points to nutrients, chemicals, and metabolites; those evidence nodes point to diseases/pathways when supported.",
            True,
        ),
        (
            "denovo_hpp_kg_full_flexible",
            full,
            "flexible",
            0.085,
            "Full de novo display graph with signed FoodAtlas chemical-to-disease correlation edges; same node types are clustered together.",
            False,
        ),
        (
            "denovo_hpp_kg_full_radial",
            full,
            "radial",
            0.075,
            "Full de novo display graph in radial biological order: foods inside, disease/pathway nodes outside.",
            False,
        ),
    ]:
        packed = _pack_graph(graph, layout)
        js_path = OUT / f"{name}_data.js"
        html_path = OUT / f"{name}.html"
        _write_js(js_path, packed)
        html_path.write_text(_html(name.replace("_", " ").title(), js_path.name, scale, details, default_show_edges=default_show_edges))
        outputs[name] = {
            "html": str(html_path),
            "data": str(js_path),
            "nodes": len(packed["nodes"]),
            "display_edges": len(packed["edges"]),
        }

    summary = {
        "source": "outputs/enhanced_hpp/1.denovo/kg",
        "source_nodes": full["full_source_node_count"],
        "source_edges": full["full_source_edge_count"],
        "outputs": outputs,
        "notes": [
            "FoodAtlas and HMDB disease labels are unified into one disease node category in the visualization.",
            "Positive and negative FoodAtlas correlations are edge types from chemical nodes to disease nodes.",
            "Display edges are biologically ordered for interaction and are intentionally reduced from the 1.5M raw KG edges for browser performance.",
            "Node click highlighting follows outgoing food -> nutrient/chemical/metabolite -> disease/pathway direction up to degree 4.",
        ],
    }
    (OUT / "denovo_hpp_kg_advanced_visualization_summary.json").write_text(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    print(json.dumps(build_denovo_advanced_kg_visualizations(), indent=2))
