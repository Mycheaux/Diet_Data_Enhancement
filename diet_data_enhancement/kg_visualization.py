import argparse
import json
import math
import random
import zipfile
from pathlib import Path

import pandas as pd

from .sources import ROOT


OUT = ROOT / "outputs/visualizations"
FOODATLAS_ZIP = ROOT / "data/FoodAtlas/foodatlas-v4.5.zip"

NODE_COLORS = {
    "canonical_food": "#0f766e",
    "hpp_food": "#073b8e",
    "foodatlas_food": "#2aa198",
    "foodatlas_chemical": "#d69e2e",
    "foodatlas_disease": "#f4a6a6",
    "foodb_food": "#16a34a",
    "foodb_compound": "#ca8a04",
    "hmdb_metabolite": "#7c3aed",
    "hmdb_biospecimen": "#0891b2",
}


def _hpp_display_label(short_name, original_name):
    short_name = str(short_name or "").strip()
    original_name = str(original_name or "").strip()
    if not original_name or original_name.lower() == "nan":
        return short_name
    if not short_name or short_name.lower() == original_name.lower():
        return original_name
    return f"{short_name} ({original_name})"


def _node_id(value):
    if pd.isna(value):
        return ""
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


EDGE_COLORS = {
    "belongs_to_canonical": "#8aa0b8",
    "mapped_to_foodatlas": "#20a4a9",
    "foodatlas_contains": "#d69e2e",
    "foodatlas_positively_correlates_with": "#d94b5d",
    "foodatlas_negatively_correlates_with": "#4f8fd9",
    "foodatlas_is_a": "#b7bec8",
    "mapped_to_foodb": "#16a34a",
    "foodb_contains_compound": "#ca8a04",
    "linked_to_hmdb_metabolite": "#7c3aed",
    "hmdb_observed_in_biospecimen": "#0891b2",
}


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


def _choose_food(food_query=None):
    canonical = pd.read_csv(ROOT / "outputs/canonical/canonical_foods.csv")
    crosswalk = pd.read_csv(ROOT / "outputs/canonical/hpp_to_canonical.csv")
    foodatlas = pd.read_csv(ROOT / "outputs/foodatlas/hpp_foodatlas_candidates.csv")
    best_foodatlas = foodatlas.sort_values(["hpp_food_id", "candidate_rank"]).groupby("hpp_food_id").head(1)
    merged = (
        crosswalk.merge(canonical, on=["canonical_food_id", "canonical_name", "canonical_category"], how="left")
        .merge(best_foodatlas[["hpp_food_id", "source_food_id", "matched_food_name", "match_score", "confidence"]], on="hpp_food_id", how="left")
    )
    merged = merged[merged["source_food_id"].notna()].copy()

    if food_query:
        mask = (
            merged["canonical_name"].astype(str).str.contains(food_query, case=False, na=False)
            | merged["hpp_food_name"].astype(str).str.contains(food_query, case=False, na=False)
            | merged["matched_food_name"].astype(str).str.contains(food_query, case=False, na=False)
        )
        if mask.any():
            return merged[mask].iloc[0], merged

    preferred = ["coffee", "milk", "apple", "tomato", "bread", "chocolate"]
    for term in preferred:
        mask = merged["canonical_name"].astype(str).str.contains(term, case=False, na=False)
        if mask.any():
            return merged[mask].iloc[0], merged
    return merged.iloc[0], merged


def build_visualization_subgraph(
    food_query=None,
    max_hpp=8,
    max_chemicals=18,
    max_diseases=24,
    max_foodb_compounds=8,
    max_hmdb_metabolites=10,
):
    selected, all_mapped = _choose_food(food_query)
    entities, triplets = _read_foodatlas()
    entity_lookup = entities.set_index("foodatlas_id").to_dict("index")

    canonical_id = selected["canonical_food_id"]
    canonical_name = selected["canonical_name"]
    same_canonical = all_mapped[all_mapped["canonical_food_id"].eq(canonical_id)].head(max_hpp).copy()
    foodatlas_ids = same_canonical["source_food_id"].dropna().astype(str).unique().tolist()
    foodb_candidates_path = ROOT / "outputs/layered/layer3_foodb_food_candidates.csv"
    hmdb_examples_path = ROOT / "outputs/reference/canonical_food_hmdb_metabolite_link_examples.csv"

    contains = triplets[
        triplets["head_id"].isin(foodatlas_ids) & triplets["relationship_name"].eq("contains")
    ].head(max_chemicals * max(1, len(foodatlas_ids)))
    chemical_ids = contains["tail_id"].dropna().astype(str).drop_duplicates().head(max_chemicals).tolist()

    positive = triplets[
        triplets["head_id"].isin(chemical_ids)
        & triplets["relationship_name"].eq("positively_correlates_with")
    ].head(max_diseases * max(1, len(chemical_ids)))
    negative = triplets[
        triplets["head_id"].isin(chemical_ids)
        & triplets["relationship_name"].eq("negatively_correlates_with")
    ].head(max_diseases * max(1, len(chemical_ids)))
    disease_ids = (
        pd.concat([positive["tail_id"], negative["tail_id"]])
        .dropna()
        .astype(str)
        .drop_duplicates()
        .head(max_diseases)
        .tolist()
    )
    positive = positive[positive["tail_id"].isin(disease_ids)]
    negative = negative[negative["tail_id"].isin(disease_ids)]

    nodes = []
    edges = []

    def add_node(key, kind, label, ring, **attrs):
        if key in {node["key"] for node in nodes}:
            return
        nodes.append(
            {
                "key": key,
                "kind": kind,
                "label": str(label),
                "ring": ring,
                "color": NODE_COLORS.get(kind, "#9aa5b1"),
                **attrs,
            }
        )

    def add_edge(source, target, relation, positive_path=False, **attrs):
        if any(edge["source"] == source and edge["target"] == target and edge["relation"] == relation for edge in edges):
            return
        edges.append(
            {
                "source": source,
                "target": target,
                "relation": relation,
                "color": EDGE_COLORS.get(relation, "#9aa5b1"),
                "positive_path": positive_path,
                **attrs,
            }
        )

    canonical_key = f"canonical_food:{canonical_id}"
    add_node(canonical_key, "canonical_food", canonical_name, 0, category=selected.get("canonical_category", ""))

    for _, row in same_canonical.iterrows():
        hpp_key = f"hpp_food:{row['hpp_food_id']}"
        fa_key = f"foodatlas_food:{row['source_food_id']}"
        hpp_label = _hpp_display_label(row["hpp_food_name"], row.get("original_product_name", ""))
        add_node(hpp_key, "hpp_food", hpp_label, 4, short_name=row["hpp_food_name"], original=row.get("original_product_name", ""))
        add_node(fa_key, "foodatlas_food", row["matched_food_name"], 2, foodatlas_id=row["source_food_id"])
        add_edge(hpp_key, canonical_key, "belongs_to_canonical")
        add_edge(hpp_key, fa_key, "mapped_to_foodatlas", positive_path=True, score=row.get("match_score", ""))

    if foodb_candidates_path.exists():
        foodb_candidates = pd.read_csv(foodb_candidates_path)
        foodb_matches = foodb_candidates[foodb_candidates["canonical_food_id"].eq(canonical_id)].copy()
        if not foodb_matches.empty:
            top_foodb = foodb_matches.sort_values("candidate_rank").iloc[0]
            foodb_food_id = _node_id(top_foodb["source_food_id"])
            foodb_food_key = f"foodb_food:{foodb_food_id}"
            add_node(
                foodb_food_key,
                "foodb_food",
                top_foodb.get("matched_food_name", foodb_food_id),
                3,
                confidence=top_foodb.get("confidence", ""),
            )
            add_edge(
                canonical_key,
                foodb_food_key,
                "mapped_to_foodb",
                positive_path=True,
                score=top_foodb.get("match_score", ""),
            )

    if hmdb_examples_path.exists():
        hmdb_examples = pd.read_csv(hmdb_examples_path)
        hmdb_rows = hmdb_examples[hmdb_examples["canonical_food_id"].eq(canonical_id)].copy()
        if not hmdb_rows.empty:
            hmdb_rows = (
                hmdb_rows.dropna(subset=["foodb_compound_public_id", "hmdb_id"])
                .drop_duplicates(["foodb_compound_public_id", "hmdb_id", "biospecimen"])
            )
            compound_ids = hmdb_rows["foodb_compound_public_id"].dropna().astype(str).drop_duplicates().head(max_foodb_compounds)
            hmdb_rows = hmdb_rows[hmdb_rows["foodb_compound_public_id"].astype(str).isin(compound_ids)]
            metabolite_ids = hmdb_rows["hmdb_id"].dropna().astype(str).drop_duplicates().head(max_hmdb_metabolites)
            hmdb_rows = hmdb_rows[hmdb_rows["hmdb_id"].astype(str).isin(metabolite_ids)]
            for _, row in hmdb_rows.iterrows():
                foodb_food_id = _node_id(row["foodb_food_id"])
                foodb_compound_id = _node_id(row["foodb_compound_public_id"])
                hmdb_id = _node_id(row["hmdb_id"])
                biospecimen_id = _node_id(row["biospecimen"])
                foodb_food_key = f"foodb_food:{foodb_food_id}"
                foodb_compound_key = f"foodb_compound:{foodb_compound_id}"
                hmdb_key = f"hmdb_metabolite:{hmdb_id}"
                biospecimen_key = f"hmdb_biospecimen:{biospecimen_id}"
                add_node(foodb_food_key, "foodb_food", row.get("foodb_food_name", foodb_food_id), 3)
                add_node(foodb_compound_key, "foodb_compound", row.get("compound_name", foodb_compound_id), 6)
                add_node(hmdb_key, "hmdb_metabolite", row.get("hmdb_name", hmdb_id), 7)
                add_node(biospecimen_key, "hmdb_biospecimen", row.get("biospecimen", ""), 8)
                add_edge(canonical_key, foodb_food_key, "mapped_to_foodb", positive_path=True)
                add_edge(foodb_food_key, foodb_compound_key, "foodb_contains_compound", positive_path=True)
                add_edge(
                    foodb_compound_key,
                    hmdb_key,
                    "linked_to_hmdb_metabolite",
                    positive_path=True,
                    method=row.get("hmdb_link_method", ""),
                )
                add_edge(hmdb_key, biospecimen_key, "hmdb_observed_in_biospecimen", positive_path=True)

    for _, row in contains[contains["tail_id"].isin(chemical_ids)].iterrows():
        food_key = f"foodatlas_food:{row['head_id']}"
        chemical = entity_lookup.get(row["tail_id"], {})
        chemical_key = f"foodatlas_chemical:{row['tail_id']}"
        add_node(chemical_key, "foodatlas_chemical", chemical.get("common_name", row["tail_id"]), 1)
        add_edge(food_key, chemical_key, "foodatlas_contains", positive_path=True)

    for _, row in positive.iterrows():
        chemical_key = f"foodatlas_chemical:{row['head_id']}"
        disease = entity_lookup.get(row["tail_id"], {})
        disease_key = f"foodatlas_disease:{row['tail_id']}"
        add_node(disease_key, "foodatlas_disease", disease.get("common_name", row["tail_id"]), 5)
        add_edge(chemical_key, disease_key, "foodatlas_positively_correlates_with", positive_path=True)

    for _, row in negative.iterrows():
        chemical_key = f"foodatlas_chemical:{row['head_id']}"
        disease = entity_lookup.get(row["tail_id"], {})
        disease_key = f"foodatlas_disease:{row['tail_id']}"
        add_node(disease_key, "foodatlas_disease", disease.get("common_name", row["tail_id"]), 5)
        add_edge(chemical_key, disease_key, "foodatlas_negatively_correlates_with", positive_path=True)

    return {
        "selected_food": {
            "canonical_food_id": canonical_id,
            "canonical_name": canonical_name,
            "food_query": food_query or "",
        },
        "nodes": nodes,
        "edges": edges,
    }


def _spread(group, x1, y1, x2, y2, cols=None):
    if not group:
        return
    cols = cols or max(1, math.ceil(math.sqrt(len(group))))
    rows = max(1, math.ceil(len(group) / cols))
    dx = 0 if cols == 1 else (x2 - x1) / (cols - 1)
    dy = 0 if rows == 1 else (y2 - y1) / (rows - 1)
    for idx, node in enumerate(group):
        col = idx % cols
        row = idx // cols
        node["x"] = x1 + col * dx
        node["y"] = y1 + row * dy


def _layout(nodes, width=2000, height=1250):
    grouped = {}
    for node in nodes:
        grouped.setdefault(node["kind"], []).append(node)

    for node in grouped.get("canonical_food", []):
        node["x"] = 860
        node["y"] = 600

    _spread(grouped.get("hpp_food", []), 60, 300, 300, 980, cols=2)
    _spread(grouped.get("foodatlas_food", []), 760, 260, 1020, 330, cols=2)
    _spread(grouped.get("foodatlas_chemical", []), 430, 90, 1050, 470, cols=3)
    _spread(grouped.get("foodatlas_disease", []), 1350, 60, 1830, 780, cols=2)
    _spread(grouped.get("foodb_food", []), 730, 775, 990, 845, cols=2)
    _spread(grouped.get("foodb_compound", []), 400, 875, 730, 1160, cols=3)
    _spread(grouped.get("hmdb_metabolite", []), 900, 910, 1170, 1160, cols=3)
    _spread(grouped.get("hmdb_biospecimen", []), 1430, 930, 1840, 1170, cols=3)

    placed = {node["key"] for node in nodes if "x" in node and "y" in node}
    leftovers = [node for node in nodes if node["key"] not in placed]
    _spread(leftovers, 760, 520, 1140, 740, cols=4)
    return nodes


def _html_doc(data):
    data = {**data, "nodes": _layout(data["nodes"])}
    payload = json.dumps(data, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Diet Data Enhancement KG</title>
<style>
body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f5fbff; color: #123; }}
header {{ padding: 18px 24px; background: #063b5f; color: white; }}
h1 {{ margin: 0; font-size: 22px; }}
.wrap {{ display: grid; grid-template-columns: 1fr 340px; min-height: calc(100vh - 64px); }}
#graph {{ width: 100%; height: calc(100vh - 64px); background: radial-gradient(circle at 50% 48%, #ffffff 0, #eef8fb 58%, #d9edf7 100%); }}
aside {{ padding: 18px; border-left: 1px solid #c8dce8; background: #ffffff; overflow: auto; }}
.legend {{ display: grid; gap: 8px; margin: 14px 0 24px; }}
.swatch {{ display: inline-block; width: 12px; height: 12px; border-radius: 50%; margin-right: 8px; vertical-align: -1px; }}
.edge-swatch {{ height: 3px; border-radius: 2px; width: 22px; display: inline-block; margin-right: 8px; vertical-align: 3px; }}
button {{ border: 0; background: #0b6fa4; color: white; padding: 8px 10px; border-radius: 6px; cursor: pointer; }}
svg text {{ paint-order: stroke; stroke: white; stroke-width: 4px; stroke-linejoin: round; font-size: 11px; fill: #102a43; }}
.node {{ cursor: pointer; }}
.dim {{ opacity: 0.08; }}
.active-node {{ stroke: #111827; stroke-width: 3px; }}
.active-edge {{ stroke-width: 4px; opacity: 1; }}
.edge {{ opacity: .58; }}
.positive {{ stroke-width: 2.8px; }}
.negative {{ stroke-width: 2.8px; stroke-dasharray: 6 4; }}
</style>
</head>
<body>
<header><h1>Diet Data Enhancement Knowledge Graph</h1></header>
<div class="wrap">
<svg id="graph" viewBox="0 0 2000 1250" role="img" aria-label="Food knowledge graph visualization"></svg>
<aside>
<h2 id="title">Food KG View</h2>
<p id="details">Click a node to highlight the local FoodAtlas, FooDB, and HMDB paths.</p>
<button id="reset">Reset</button>
<h3>Node Types</h3>
<div class="legend">
<div><span class="swatch" style="background:#073b8e"></span>HPP food</div>
<div><span class="swatch" style="background:#0f766e"></span>Canonical food</div>
<div><span class="swatch" style="background:#2aa198"></span>FoodAtlas food</div>
<div><span class="swatch" style="background:#16a34a"></span>FooDB food</div>
<div><span class="swatch" style="background:#d69e2e"></span>Chemical</div>
<div><span class="swatch" style="background:#ca8a04"></span>FooDB compound</div>
<div><span class="swatch" style="background:#7c3aed"></span>HMDB metabolite</div>
<div><span class="swatch" style="background:#0891b2"></span>HMDB biofluid</div>
<div><span class="swatch" style="background:#f4a6a6"></span>Medical condition</div>
</div>
<h3>Edge Types</h3>
<div class="legend">
<div><span class="edge-swatch" style="background:#8aa0b8"></span>HPP belongs to canonical</div>
<div><span class="edge-swatch" style="background:#20a4a9"></span>HPP mapped to FoodAtlas</div>
<div><span class="edge-swatch" style="background:#d69e2e"></span>Food contains chemical</div>
<div><span class="edge-swatch" style="background:#d94b5d"></span>Positive disease correlation</div>
<div><span class="edge-swatch" style="background:#4f8fd9"></span>Negative disease correlation</div>
<div><span class="edge-swatch" style="background:#16a34a"></span>Canonical to FooDB</div>
<div><span class="edge-swatch" style="background:#ca8a04"></span>FooDB contains compound</div>
<div><span class="edge-swatch" style="background:#7c3aed"></span>Compound to HMDB metabolite</div>
<div><span class="edge-swatch" style="background:#0891b2"></span>HMDB metabolite in biofluid</div>
</div>
</aside>
</div>
<script>
const data = {payload};
const svg = document.getElementById('graph');
const nodeByKey = new Map(data.nodes.map(n => [n.key, n]));
const pathEdges = data.edges.filter(e => e.positive_path);
function el(name, attrs) {{
  const out = document.createElementNS('http://www.w3.org/2000/svg', name);
  Object.entries(attrs || {{}}).forEach(([k,v]) => out.setAttribute(k, v));
  return out;
}}
const defs = el('defs');
defs.innerHTML = `
<marker id="arrow-default" markerWidth="9" markerHeight="9" refX="8" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,6 L8,3 z" fill="#8aa0b8"></path></marker>
<marker id="arrow-positive" markerWidth="9" markerHeight="9" refX="8" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,6 L8,3 z" fill="#d94b5d"></path></marker>
<marker id="arrow-negative" markerWidth="9" markerHeight="9" refX="8" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,6 L8,3 z" fill="#4f8fd9"></path></marker>
`;
svg.appendChild(defs);
[
  ['HPP foods', 30, 250, 310, 800, '#073b8e'],
  ['FoodAtlas chemicals', 395, 50, 720, 470, '#d69e2e'],
  ['FoodAtlas diseases', 1315, 25, 610, 820, '#f4a6a6'],
  ['FooDB compounds', 365, 835, 430, 370, '#ca8a04'],
  ['HMDB metabolites', 865, 865, 370, 340, '#7c3aed'],
  ['HMDB biofluids', 1395, 890, 500, 330, '#0891b2'],
].forEach(([label, x, y, w, h, color]) => {{
  const rect = el('rect', {{x, y, width:w, height:h, rx:14, fill:'none', stroke:color, 'stroke-dasharray':'7 8', opacity:.32}});
  svg.appendChild(rect);
  const text = el('text', {{x:Number(x)+12, y:Number(y)+24, fill:color, 'font-weight':700}});
  text.textContent = label;
  svg.appendChild(text);
}});
const edgeEls = data.edges.map(e => {{
  const s = nodeByKey.get(e.source), t = nodeByKey.get(e.target);
  const marker = e.relation.includes('positively') ? 'url(#arrow-positive)' : e.relation.includes('negatively') ? 'url(#arrow-negative)' : 'url(#arrow-default)';
  const klass = e.relation.includes('positively') ? 'edge positive' : e.relation.includes('negatively') ? 'edge negative' : 'edge';
  const line = el('line', {{x1:s.x, y1:s.y, x2:t.x, y2:t.y, stroke:e.color, 'stroke-width': e.relation.includes('correlates') ? 2.4 : 1.4, class:klass, 'marker-end':marker}});
  line.dataset.source = e.source; line.dataset.target = e.target; line.dataset.positive = e.positive_path ? '1' : '0';
  svg.appendChild(line); return line;
}});
const nodeEls = data.nodes.map(n => {{
  const g = el('g', {{class:'node'}});
  g.dataset.key = n.key;
  const title = el('title');
  title.textContent = `${{n.label}} · ${{n.kind}}`;
  g.appendChild(title);
  const r = n.kind === 'canonical_food' ? 18 : n.kind === 'foodatlas_disease' ? 9 : n.kind === 'foodatlas_chemical' ? 7 : n.kind === 'hmdb_metabolite' ? 8 : n.kind === 'foodb_compound' ? 7 : 10;
  g.appendChild(el('circle', {{cx:n.x, cy:n.y, r, fill:n.color, stroke:'white', 'stroke-width':2}}));
  const text = el('text', {{x:n.x + r + 4, y:n.y + 4}});
  text.textContent = n.label.length > 36 ? n.label.slice(0, 34) + '…' : n.label;
  g.appendChild(text);
  g.addEventListener('click', () => highlight(n.key));
  svg.appendChild(g); return g;
}});
function connectedPositive(start) {{
  const seen = new Set([start]); let changed = true;
  while (changed) {{
    changed = false;
    for (const e of pathEdges) {{
      if (seen.has(e.source) && !seen.has(e.target)) {{ seen.add(e.target); changed = true; }}
      if (seen.has(e.target) && !seen.has(e.source)) {{ seen.add(e.source); changed = true; }}
    }}
  }}
  return seen;
}}
function highlight(key) {{
  const keep = connectedPositive(key);
  nodeEls.forEach(g => {{
    const active = keep.has(g.dataset.key);
    g.classList.toggle('dim', !active);
    g.querySelector('circle').classList.toggle('active-node', g.dataset.key === key);
  }});
  edgeEls.forEach(line => {{
    const active = keep.has(line.dataset.source) && keep.has(line.dataset.target) && line.dataset.positive === '1';
    line.classList.toggle('dim', !active);
    line.classList.toggle('active-edge', active);
  }});
  const node = nodeByKey.get(key);
  document.getElementById('title').textContent = node.label;
  document.getElementById('details').textContent = `${{node.kind}} · highlighted ${{keep.size}} nodes on local FoodAtlas/FooDB/HMDB paths`;
}}
document.getElementById('reset').addEventListener('click', () => {{
  nodeEls.forEach(g => g.classList.remove('dim'));
  edgeEls.forEach(e => e.classList.remove('dim', 'active-edge'));
  document.getElementById('title').textContent = 'Food KG View';
  document.getElementById('details').textContent = 'Click a node to highlight the local FoodAtlas, FooDB, and HMDB paths.';
}});
</script>
</body>
</html>"""


def _full_layout(nodes):
    ring_radius = {
        "nutrient": 900,
        "hmdb_biospecimen": 1200,
        "hmdb_metabolite": 1350,
        "foodb_compound": 1450,
        "foodatlas_chemical": 1550,
        "canonical_food": 2200,
        "foodb_food": 2550,
        "foodatlas_food": 2850,
        "source_food": 3400,
        "hpp_food": 4000,
        "foodatlas_disease": 4750,
        "human_correction": 5200,
    }
    grouped = {}
    for idx, node in enumerate(nodes):
        grouped.setdefault(node["kd"], []).append((idx, node))

    random.seed(42)
    for kind, group in grouped.items():
        radius = ring_radius.get(kind, 3600)
        count = len(group)
        for offset, (idx, node) in enumerate(group):
            angle = (2 * math.pi * offset / max(1, count)) + random.uniform(-0.002, 0.002)
            node["x"] = round(math.cos(angle) * radius, 2)
            node["y"] = round(math.sin(angle) * radius, 2)
            node["i"] = idx
            node["color"] = NODE_COLORS.get(kind, "#94a3b8")
    return nodes


def _floating_full_layout(nodes):
    centers = {
        "canonical_food": (0, 0, 18),
        "hpp_food": (-1700, -260, 24),
        "source_food": (-1420, 1020, 30),
        "nutrient": (-980, -1420, 20),
        "foodatlas_food": (260, -1080, 30),
        "foodatlas_chemical": (1420, -620, 8),
        "foodatlas_disease": (2350, 620, 24),
        "foodb_food": (-30, 1080, 26),
        "foodb_compound": (1180, 1180, 14),
        "hmdb_metabolite": (2240, 1450, 24),
        "hmdb_biospecimen": (2860, 1280, 38),
        "human_correction": (-450, 420, 35),
    }
    grouped = {}
    for idx, node in enumerate(nodes):
        grouped.setdefault(node["kd"], []).append((idx, node))

    golden_angle = math.pi * (3 - math.sqrt(5))
    random.seed(73)
    for kind, group in grouped.items():
        cx, cy, spacing = centers.get(kind, (0, 0, 32))
        for offset, (idx, node) in enumerate(group):
            if kind == "canonical_food":
                local_radius = spacing * math.sqrt(offset)
            else:
                local_radius = spacing * math.sqrt(offset + 1)
            angle = offset * golden_angle + random.uniform(-0.08, 0.08)
            wobble = random.uniform(-0.45, 0.45) * spacing
            node["x"] = round(cx + math.cos(angle) * (local_radius + wobble), 2)
            node["y"] = round(cy + math.sin(angle) * (local_radius + wobble), 2)
            node["i"] = idx
            node["color"] = NODE_COLORS.get(kind, "#94a3b8")
    return nodes


def _full_html(title="Full Diet Knowledge Graph", data_filename="kg_full_visualization_data.js", description=None):
    description = description or "All nodes are present. Edges are hidden by default for speed; search or click a node to show its local connections. Use mouse wheel to zoom, drag background to pan, drag a node to move it."
    html = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Full Diet KG Explorer</title>
<style>
body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:#071827; color:#e8f6ff; overflow:hidden; }
header { height:58px; display:flex; align-items:center; gap:14px; padding:0 18px; background:#082f49; border-bottom:1px solid #164e63; }
h1 { font-size:18px; margin:0; white-space:nowrap; }
input, button, select { border:1px solid #2d6f8f; background:#0b2538; color:#e8f6ff; border-radius:6px; padding:7px 9px; }
button { cursor:pointer; }
#canvas { display:block; width:100vw; height:calc(100vh - 58px); background:#f5fbff; }
#panel { position:fixed; right:14px; top:72px; width:330px; max-height:calc(100vh - 96px); overflow:auto; background:rgba(255,255,255,.94); color:#102a43; border:1px solid #b7d2df; border-radius:8px; padding:14px; box-shadow:0 10px 32px rgba(7,24,39,.22); }
#tooltip { position:fixed; display:none; pointer-events:none; max-width:280px; background:rgba(15,23,42,.94); color:white; border:1px solid rgba(255,255,255,.2); border-radius:6px; padding:7px 9px; font-size:12px; line-height:1.35; box-shadow:0 8px 24px rgba(15,23,42,.25); z-index:20; }
.muted { color:#486581; font-size:12px; }
.legend { display:grid; grid-template-columns:1fr 1fr; gap:6px; font-size:12px; }
.legend-item { cursor:pointer; user-select:none; padding:3px 4px; border-radius:5px; }
.legend-item:hover { background:#e2edf5; }
.legend-item.off { opacity:.34; text-decoration:line-through; }
.dot { display:inline-block; width:11px; height:11px; border-radius:50%; margin-right:6px; }
.row { margin:8px 0; }
</style>
</head>
<body>
<header>
<h1>Full Diet Knowledge Graph</h1>
<input id="search" placeholder="Search node label or key" size="34">
<button id="searchBtn">Find</button>
<button id="resetBtn">Reset View</button>
<label>depth
<select id="depthSelect">
<option value="1">1st</option>
<option value="2" selected>2nd</option>
<option value="3">3rd</option>
<option value="4">4th</option>
</select>
</label>
<label><input type="checkbox" id="edgesToggle"> show all edges</label>
<span id="status" class="muted">Loading full KG...</span>
</header>
<canvas id="canvas"></canvas>
<div id="tooltip"></div>
<aside id="panel">
<h2 style="margin-top:0">Full KG Explorer</h2>
<p class="muted">All nodes are present. Edges are hidden by default for speed; search or click a node to show its local connections. Use mouse wheel to zoom, drag background to pan, drag a node to move it.</p>
<div class="legend">
<div class="legend-item" data-kind="hpp_food"><span class="dot" style="background:#073b8e"></span>HPP food</div>
<div class="legend-item" data-kind="canonical_food"><span class="dot" style="background:#0f766e"></span>Canonical food</div>
<div class="legend-item" data-kind="foodatlas_food"><span class="dot" style="background:#2aa198"></span>FoodAtlas food</div>
<div class="legend-item" data-kind="foodb_food"><span class="dot" style="background:#16a34a"></span>FooDB food</div>
<div class="legend-item" data-kind="foodatlas_chemical,foodb_compound"><span class="dot" style="background:#d69e2e"></span>Chemical</div>
<div class="legend-item" data-kind="hmdb_metabolite"><span class="dot" style="background:#7c3aed"></span>HMDB metabolite</div>
<div class="legend-item" data-kind="foodatlas_disease"><span class="dot" style="background:#f4a6a6"></span>Disease</div>
<div class="legend-item" data-kind="source_food,nutrient,human_correction,hmdb_biospecimen"><span class="dot" style="background:#94a3b8"></span>Other</div>
</div>
<div id="details" class="row">Click or search for a node.</div>
</aside>
<script src="kg_full_visualization_data.js"></script>
<script>
const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');
const tooltip = document.getElementById('tooltip');
const data = window.FULL_KG_DATA;
const nodes = data.nodes, edges = data.edges;
const nodeByKey = new Map(nodes.map((n, i) => [n.k, i]));
const incident = new Map();
for (const e of edges) {
  if (!incident.has(e.s)) incident.set(e.s, []);
  if (!incident.has(e.t)) incident.set(e.t, []);
  incident.get(e.s).push(e); incident.get(e.t).push(e);
}
let scale = 0.075, tx = innerWidth / 2, ty = (innerHeight + 58) / 2;
let selected = -1, hover = -1, draggingNode = -1, draggingPan = false, last = null;
let showAllEdges = false;
const hiddenKinds = new Set();
let neighborhoodCache = {selected:-1, depth:-1, nodes:new Set(), edges:[]};
function resize(){ canvas.width = innerWidth * devicePixelRatio; canvas.height = (innerHeight-58) * devicePixelRatio; canvas.style.height = (innerHeight-58)+'px'; draw(); }
function sx(x){ return x * scale + tx; } function sy(y){ return y * scale + ty - 58; }
function wx(x){ return (x - tx) / scale; } function wy(y){ return (y - ty + 58) / scale; }
function edgeColor(r){ return data.edgeColors[r] || '#9aa5b1'; }
function radius(n){ if(n.kd === 'canonical_food') return 3.8; if(n.kd === 'foodatlas_disease') return 2.5; if(n.kd === 'foodatlas_chemical') return 1.8; return 2.1; }
function nodeVisible(i){ return !hiddenKinds.has(nodes[i].kd); }
function currentDepth(){ return Number(document.getElementById('depthSelect').value || 2); }
function computeNeighborhood(){
  const depth = currentDepth();
  if (selected < 0) return {nodes:new Set(), edges:[]};
  if (neighborhoodCache.selected === selected && neighborhoodCache.depth === depth) return neighborhoodCache;
  const keep = new Set([selected]);
  const edgeKeys = new Set();
  let frontier = new Set([selected]);
  for (let step=0; step<depth; step++) {
    const next = new Set();
    for (const nodeIndex of frontier) {
      for (const e of incident.get(nodeIndex) || []) {
        edgeKeys.add(`${e.s}|${e.t}|${e.r}`);
        const other = e.s === nodeIndex ? e.t : e.s;
        if (!nodeVisible(other)) continue;
        if (!keep.has(other)) {
          keep.add(other);
          next.add(other);
        }
      }
    }
    frontier = next;
    if (frontier.size === 0) break;
  }
  const localEdges = [];
  for (const e of edges) {
    if (edgeKeys.has(`${e.s}|${e.t}|${e.r}`)) localEdges.push(e);
  }
  neighborhoodCache = {selected, depth, nodes:keep, edges:localEdges};
  return neighborhoodCache;
}
function draw(){
  ctx.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);
  ctx.clearRect(0,0,innerWidth,innerHeight-58);
  ctx.fillStyle = '#f5fbff'; ctx.fillRect(0,0,innerWidth,innerHeight-58);
  const neighborhood = computeNeighborhood();
  const drawEdges = showAllEdges ? edges : (selected >= 0 ? neighborhood.edges : []);
  ctx.globalAlpha = showAllEdges ? 0.07 : 0.55;
  for (const e of drawEdges) {
    if (!nodeVisible(e.s) || !nodeVisible(e.t)) continue;
    const a=nodes[e.s], b=nodes[e.t]; const ax=sx(a.x), ay=sy(a.y), bx=sx(b.x), by=sy(b.y);
    if ((ax < -100 && bx < -100) || (ay < -100 && by < -100) || (ax > innerWidth+100 && bx > innerWidth+100) || (ay > innerHeight+100 && by > innerHeight+100)) continue;
    ctx.strokeStyle = edgeColor(e.r); ctx.lineWidth = e.r === 'foodatlas_positively_correlates_with' ? 1.3 : .7;
    ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke();
  }
  ctx.globalAlpha = 1;
  for (let i=0; i<nodes.length; i++) {
    if (!nodeVisible(i)) continue;
    const n=nodes[i], x=sx(n.x), y=sy(n.y);
    if (x < -20 || y < -20 || x > innerWidth+20 || y > innerHeight+20) continue;
    const dim = selected >= 0 && !neighborhood.nodes.has(i);
    ctx.globalAlpha = dim ? 0.08 : 0.88;
    ctx.fillStyle = n.c; ctx.beginPath(); ctx.arc(x,y,Math.max(1.1, radius(n)*Math.sqrt(scale*10)),0,Math.PI*2); ctx.fill();
  }
  if (selected >= 0) {
    const n = nodes[selected]; ctx.globalAlpha=1; ctx.strokeStyle='#111827'; ctx.lineWidth=3; ctx.beginPath(); ctx.arc(sx(n.x),sy(n.y),9,0,Math.PI*2); ctx.stroke();
    ctx.fillStyle='#102a43'; ctx.font='13px system-ui'; ctx.fillText(n.l, sx(n.x)+12, sy(n.y)+4);
  }
  if (hover >= 0 && hover !== selected) {
    const n = nodes[hover]; ctx.globalAlpha=1; ctx.strokeStyle='#111827'; ctx.lineWidth=2; ctx.beginPath(); ctx.arc(sx(n.x),sy(n.y),7,0,Math.PI*2); ctx.stroke();
  }
  ctx.globalAlpha = 1;
}
function nearest(clientX, clientY) {
  const x = clientX, y = clientY - 58; let best=-1, bestD=16*16;
  const neighborhood = computeNeighborhood();
  for (let i=0; i<nodes.length; i++) {
    if (!nodeVisible(i)) continue;
    if (selected >= 0 && !neighborhood.nodes.has(i)) continue;
    const dx=sx(nodes[i].x)-x, dy=sy(nodes[i].y)-y, d=dx*dx+dy*dy;
    if (d < bestD) { best=i; bestD=d; }
  }
  return best;
}
function showTooltip(i, event) {
  if (i < 0) {
    tooltip.style.display = 'none';
    return;
  }
  const n = nodes[i];
  tooltip.innerHTML = `<b>${n.l}</b><br><span>${n.kd}</span>`;
  const left = Math.min(event.clientX + 14, innerWidth - 300);
  const top = Math.min(event.clientY + 14, innerHeight - 80);
  tooltip.style.left = left + 'px';
  tooltip.style.top = top + 'px';
  tooltip.style.display = 'block';
}
function selectNode(i){
  if (!nodeVisible(i)) return;
  selected = i; const n = nodes[i];
  const inc = incident.get(i) || [];
  neighborhoodCache = {selected:-1, depth:-1, nodes:new Set(), edges:[]};
  const nb = computeNeighborhood();
  document.getElementById('details').innerHTML = `<b>${n.l}</b><br><span class="muted">${n.kd} · ${n.k}</span><br>${inc.length} direct edges<br>${nb.nodes.size.toLocaleString()} nodes and ${nb.edges.length.toLocaleString()} edges within ${currentDepth()} degree(s)`;
  draw();
}
canvas.addEventListener('mousedown', e => { last={x:e.clientX,y:e.clientY}; const n=nearest(e.clientX,e.clientY); if(n>=0){ draggingNode=n; selectNode(n); } else draggingPan=true; });
canvas.addEventListener('mousemove', e => {
  if(!last) {
    const n = nearest(e.clientX,e.clientY);
    if (n !== hover) { hover = n; draw(); }
    showTooltip(n, e);
    return;
  }
  if(draggingNode>=0){
    nodes[draggingNode].x = wx(e.clientX); nodes[draggingNode].y = wy(e.clientY);
    hover = draggingNode;
    showTooltip(draggingNode, e);
  } else if(draggingPan){
    tx += e.clientX-last.x; ty += e.clientY-last.y;
    hover = -1;
    showTooltip(-1, e);
  }
  last={x:e.clientX,y:e.clientY}; draw();
});
canvas.addEventListener('mouseleave', e => { hover=-1; showTooltip(-1, e); draw(); });
addEventListener('mouseup', () => { draggingNode=-1; draggingPan=false; last=null; });
canvas.addEventListener('wheel', e => { e.preventDefault(); const old=scale; scale *= e.deltaY < 0 ? 1.14 : 0.88; scale = Math.max(0.012, Math.min(2.2, scale)); const mx=e.clientX, my=e.clientY; tx = mx - (mx-tx)*(scale/old); ty = my - (my-ty)*(scale/old); draw(); }, {passive:false});
document.getElementById('edgesToggle').addEventListener('change', e => { showAllEdges=e.target.checked; draw(); });
document.getElementById('depthSelect').addEventListener('change', () => { neighborhoodCache = {selected:-1, depth:-1, nodes:new Set(), edges:[]}; if(selected >= 0) selectNode(selected); else draw(); });
document.getElementById('resetBtn').addEventListener('click', () => { scale=.075; tx=innerWidth/2; ty=(innerHeight+58)/2; selected=-1; hover=-1; tooltip.style.display='none'; draw(); });
document.querySelectorAll('.legend-item').forEach(item => {
  item.addEventListener('click', () => {
    const kinds = item.dataset.kind.split(',');
    const hiding = !item.classList.contains('off');
    for (const kind of kinds) {
      if (hiding) hiddenKinds.add(kind); else hiddenKinds.delete(kind);
    }
    item.classList.toggle('off', hiding);
    if (selected >= 0 && !nodeVisible(selected)) selected = -1;
    if (hover >= 0 && !nodeVisible(hover)) hover = -1;
    neighborhoodCache = {selected:-1, depth:-1, nodes:new Set(), edges:[]};
    tooltip.style.display='none';
    draw();
  });
});
document.getElementById('searchBtn').addEventListener('click', () => {
  const q=document.getElementById('search').value.toLowerCase(); if(!q) return;
  const i=nodes.findIndex((n, idx) => nodeVisible(idx) && (n.l.toLowerCase().includes(q) || n.k.toLowerCase().includes(q)));
  if(i>=0){ tx = innerWidth/2 - nodes[i].x*scale; ty = (innerHeight+58)/2 - nodes[i].y*scale; selectNode(i); }
});
document.getElementById('status').textContent = `${nodes.length.toLocaleString()} nodes · ${edges.length.toLocaleString()} edges`;
addEventListener('resize', resize); resize();
</script>
</body>
</html>"""
    return (
        html.replace("<title>Full Diet KG Explorer</title>", f"<title>{title}</title>")
        .replace("<h1>Full Diet Knowledge Graph</h1>", f"<h1>{title}</h1>")
        .replace(
            "<p class=\"muted\">All nodes are present. Edges are hidden by default for speed; search or click a node to show its local connections. Use mouse wheel to zoom, drag background to pan, drag a node to move it.</p>",
            f"<p class=\"muted\">{description}</p>",
        )
        .replace("<script src=\"kg_full_visualization_data.js\"></script>", f"<script src=\"{data_filename}\"></script>")
    )


def _publication_svg(data):
    nodes = _layout(data["nodes"], width=2000, height=1250)
    node_lookup = {node["key"]: node for node in nodes}
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="2000" height="1250" viewBox="0 0 2000 1250">',
        '<defs>',
        '<marker id="arrow-positive" markerWidth="9" markerHeight="9" refX="8" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,6 L8,3 z" fill="#d94b5d"/></marker>',
        '<marker id="arrow-negative" markerWidth="9" markerHeight="9" refX="8" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,6 L8,3 z" fill="#4f8fd9"/></marker>',
        '<marker id="arrow-default" markerWidth="9" markerHeight="9" refX="8" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,6 L8,3 z" fill="#8aa0b8"/></marker>',
        '</defs>',
        '<rect width="2000" height="1250" fill="#f7fbff"/>',
        '<text x="36" y="48" font-family="Arial" font-size="26" font-weight="700" fill="#063b5f">Diet Data Enhancement KG: FoodAtlas Disease-Correlation View</text>',
    ]
    for edge in data["edges"]:
        source = node_lookup[edge["source"]]
        target = node_lookup[edge["target"]]
        color = edge["color"]
        is_correlation = "correlates" in edge["relation"]
        width = 2.6 if is_correlation else 1.3
        marker = "arrow-positive" if "positively" in edge["relation"] else "arrow-negative" if "negatively" in edge["relation"] else "arrow-default"
        dash = ' stroke-dasharray="6 4"' if "negatively" in edge["relation"] else ""
        lines.append(f'<line x1="{source["x"]:.1f}" y1="{source["y"]:.1f}" x2="{target["x"]:.1f}" y2="{target["y"]:.1f}" stroke="{color}" stroke-width="{width}" opacity="0.62" marker-end="url(#{marker})"{dash}/>')
    for node in nodes:
        radius = 18 if node["kind"] == "canonical_food" else 9
        lines.append(f'<circle cx="{node["x"]:.1f}" cy="{node["y"]:.1f}" r="{radius}" fill="{node["color"]}" stroke="white" stroke-width="2"/>')
        label = node["label"][:34]
        lines.append(f'<text x="{node["x"] + radius + 4:.1f}" y="{node["y"] + 4:.1f}" font-family="Arial" font-size="11" fill="#102a43">{label}</text>')
    lines.append("</svg>")
    return "\n".join(lines)


def build_visualizations(food_query=None):
    OUT.mkdir(parents=True, exist_ok=True)
    data = build_visualization_subgraph(food_query=food_query)
    data_path = OUT / "kg_focused_subgraph.json"
    html_path = OUT / "kg_focused_interactive.html"
    svg_path = OUT / "kg_focused_publication_subgraph.svg"
    data_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    html_path.write_text(_html_doc(data))
    svg_path.write_text(_publication_svg(data))
    summary = {
        "selected_food": data["selected_food"],
        "node_count": len(data["nodes"]),
        "edge_count": len(data["edges"]),
        "outputs": {
            "subgraph_json": str(data_path),
            "interactive_html": str(html_path),
            "publication_svg": str(svg_path),
        },
    }
    (OUT / "kg_visualization_summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def build_full_visualization(layout="radial"):
    OUT.mkdir(parents=True, exist_ok=True)
    nodes_df = pd.read_csv(
        ROOT / "outputs/kg/final_food_kg_nodes.csv",
        usecols=["key", "kind", "label", "original_product_name"],
        dtype=str,
    )
    edges_df = pd.read_csv(ROOT / "outputs/kg/final_food_kg_edges.csv", usecols=["source", "target", "relation"], dtype=str)

    nodes = []
    key_to_index = {}
    for idx, row in nodes_df.iterrows():
        key = str(row["key"])
        kind = str(row["kind"])
        label = str(row["label"]) if not pd.isna(row["label"]) else key
        if kind == "hpp_food":
            label = _hpp_display_label(label, row.get("original_product_name", ""))
        key_to_index[key] = idx
        nodes.append(
            {
                "k": key,
                "kd": kind,
                "l": label[:90],
                "c": NODE_COLORS.get(kind, "#94a3b8"),
            }
        )
    if layout == "floating":
        nodes = _floating_full_layout(nodes)
        data_path = OUT / "kg_full_floating_visualization_data.js"
        html_path = OUT / "kg_full_floating_interactive.html"
        summary_path = OUT / "kg_full_floating_visualization_summary.json"
        title = "Full Diet Knowledge Graph: Floating Layout"
        data_filename = "kg_full_floating_visualization_data.js"
        description = (
            "All nodes and edges are present in an organic floating-cluster layout. "
            "Edges are hidden by default for speed; search or click a node to show its local connections. "
            "Use mouse wheel to zoom, drag background to pan, drag a node to move it."
        )
        note = "This is the full-KG floating-cluster canvas explorer. It includes all nodes and all edges; edges are hidden by default for responsiveness."
    else:
        nodes = _full_layout(nodes)
        data_path = OUT / "kg_full_visualization_data.js"
        html_path = OUT / "kg_full_interactive.html"
        summary_path = OUT / "kg_full_visualization_summary.json"
        title = "Full Diet Knowledge Graph"
        data_filename = "kg_full_visualization_data.js"
        description = None
        note = "This is a full-KG canvas explorer. It renders all nodes and includes all edges; edges are hidden by default for responsiveness."

    edges = []
    for _, row in edges_df.iterrows():
        source = key_to_index.get(str(row["source"]))
        target = key_to_index.get(str(row["target"]))
        if source is None or target is None:
            continue
        edges.append({"s": source, "t": target, "r": str(row["relation"])})

    data = {
        "nodes": nodes,
        "edges": edges,
        "edgeColors": EDGE_COLORS,
    }
    data_path.write_text("window.FULL_KG_DATA = " + json.dumps(data, separators=(",", ":"), ensure_ascii=False) + ";\n")
    html_path.write_text(_full_html(title=title, data_filename=data_filename, description=description))
    summary = {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "layout": layout,
        "outputs": {
            "interactive_html": str(html_path),
            "data_js": str(data_path),
        },
        "note": note,
    }
    summary_path.write_text(json.dumps(summary, indent=2))
    return summary


def build_full_floating_visualization():
    return build_full_visualization(layout="floating")


def build_schema_overview_plot():
    OUT.mkdir(parents=True, exist_ok=True)
    import plotly.graph_objects as go

    nodes_df = pd.read_csv(ROOT / "outputs/kg/final_food_kg_nodes.csv", usecols=["key", "kind"], dtype=str)
    edges_df = pd.read_csv(ROOT / "outputs/kg/final_food_kg_edges.csv", usecols=["source", "target", "relation"], dtype=str)
    kind_by_key = dict(zip(nodes_df["key"], nodes_df["kind"]))
    node_counts = nodes_df["kind"].value_counts().to_dict()
    edge_summary = edges_df.assign(
        source_kind=edges_df["source"].map(kind_by_key),
        target_kind=edges_df["target"].map(kind_by_key),
    )
    edge_summary = (
        edge_summary.dropna(subset=["source_kind", "target_kind"])
        .groupby(["source_kind", "target_kind", "relation"], as_index=False)
        .size()
        .rename(columns={"size": "edge_count"})
    )

    positions = {
        "hpp_food": (0.0, 0.56),
        "canonical_food": (1.0, 0.56),
        "source_food": (2.0, 0.72),
        "foodatlas_food": (2.0, 0.42),
        "foodatlas_chemical": (3.15, 0.42),
        "foodatlas_disease": (4.35, 0.42),
        "foodb_food": (2.0, 0.14),
        "foodb_compound": (3.15, 0.14),
        "hmdb_metabolite": (4.35, 0.14),
        "hmdb_biospecimen": (5.25, 0.14),
        "nutrient": (2.0, 0.96),
        "human_correction": (1.0, 0.22),
    }
    labels = {
        "hpp_food": "HPP foods",
        "canonical_food": "Canonical foods",
        "source_food": "Public FCDB foods",
        "foodatlas_food": "FoodAtlas foods",
        "foodatlas_chemical": "FoodAtlas chemicals",
        "foodatlas_disease": "FoodAtlas diseases",
        "foodb_food": "FooDB foods",
        "foodb_compound": "FooDB compounds",
        "hmdb_metabolite": "HMDB metabolites",
        "hmdb_biospecimen": "HMDB biofluids",
        "nutrient": "Nutrients",
        "human_correction": "Human corrections",
    }

    relation_labels = {
        "belongs_to_canonical": "belongs to canonical",
        "mapped_to_public_fcdb": "mapped to public FCDB",
        "mapped_to_foodatlas": "mapped to FoodAtlas",
        "foodatlas_contains": "contains",
        "foodatlas_is_a": "is a",
        "foodatlas_positively_correlates_with": "positive correlation",
        "foodatlas_negatively_correlates_with": "negative correlation",
        "mapped_to_foodb": "mapped to FooDB",
        "foodb_contains_compound": "contains compound",
        "linked_to_hmdb_metabolite": "linked to HMDB",
        "hmdb_observed_in_biospecimen": "observed in biofluid",
        "has_nutrient_value": "has nutrient value",
        "has_human_correction": "has human correction",
        "human_corrected_foodatlas_candidate": "human FoodAtlas candidate",
        "openai_validated_candidate": "OpenAI validated",
    }

    fig = go.Figure()
    for _, row in edge_summary.iterrows():
        if row["source_kind"] not in positions or row["target_kind"] not in positions:
            continue
        x0, y0 = positions[row["source_kind"]]
        x1, y1 = positions[row["target_kind"]]
        relation = row["relation"]
        color = EDGE_COLORS.get(relation, "#94a3b8")
        width = max(1.0, min(12.0, math.log10(row["edge_count"] + 1) * 2.2))
        fig.add_trace(
            go.Scatter(
                x=[x0, (x0 + x1) / 2, x1],
                y=[y0, (y0 + y1) / 2 + 0.04, y1],
                mode="lines",
                line=dict(color=color, width=width, shape="spline"),
                opacity=0.42,
                hoverinfo="text",
                text=f"{labels.get(row['source_kind'], row['source_kind'])} -> {labels.get(row['target_kind'], row['target_kind'])}<br>{relation_labels.get(relation, relation)}<br>{row['edge_count']:,} edges",
                showlegend=False,
            )
        )

    for kind, (x, y) in positions.items():
        count = int(node_counts.get(kind, 0))
        if count == 0:
            continue
        size = max(18, min(92, 16 + math.log10(count + 1) * 15))
        fig.add_trace(
            go.Scatter(
                x=[x],
                y=[y],
                mode="markers+text",
                marker=dict(
                    size=size,
                    color=NODE_COLORS.get(kind, "#94a3b8"),
                    line=dict(width=2, color="white"),
                ),
                text=[f"{labels.get(kind, kind)}<br>{count:,}"],
                textposition="bottom center",
                hoverinfo="text",
                hovertext=[f"{labels.get(kind, kind)}<br>{count:,} nodes"],
                showlegend=False,
            )
        )

    edge_table = edge_summary.sort_values("edge_count", ascending=False).head(18)
    fig.add_trace(
        go.Table(
            domain=dict(x=[0.56, 1.0], y=[0.0, 0.36]),
            header=dict(values=["Relation", "From", "To", "Edges"], fill_color="#e2e8f0", align="left"),
            cells=dict(
                values=[
                    [relation_labels.get(v, v) for v in edge_table["relation"]],
                    [labels.get(v, v) for v in edge_table["source_kind"]],
                    [labels.get(v, v) for v in edge_table["target_kind"]],
                    [f"{int(v):,}" for v in edge_table["edge_count"]],
                ],
                fill_color="#ffffff",
                align="left",
                height=24,
            ),
        )
    )

    fig.update_layout(
        title="Diet Data Enhancement Whole Knowledge Graph Schema",
        width=1500,
        height=950,
        margin=dict(l=40, r=40, t=80, b=40),
        paper_bgcolor="#f8fafc",
        plot_bgcolor="#f8fafc",
        xaxis=dict(visible=False, range=[-0.25, 5.55]),
        yaxis=dict(visible=False, range=[-0.05, 1.08]),
        annotations=[
            dict(
                x=0,
                y=1.05,
                xref="paper",
                yref="paper",
                showarrow=False,
                align="left",
                text=(
                    f"{len(nodes_df):,} nodes and {len(edges_df):,} edges. "
                    "Bubble area uses a log scale; line width uses a log scale. "
                    "Red/blue lines are FoodAtlas positive/negative disease correlations."
                ),
            )
        ],
    )

    html_path = OUT / "kg_paper_schema_overview_plotly.html"
    csv_path = OUT / "kg_schema_edge_summary.csv"
    summary_path = OUT / "kg_schema_overview_summary.json"
    fig.write_html(html_path, include_plotlyjs="cdn")
    edge_summary.to_csv(csv_path, index=False)
    summary = {
        "node_count": int(len(nodes_df)),
        "edge_count": int(len(edges_df)),
        "node_counts_by_kind": {k: int(v) for k, v in sorted(node_counts.items())},
        "edge_schema_rows": int(len(edge_summary)),
        "outputs": {
            "schema_plotly": str(html_path),
            "edge_summary_csv": str(csv_path),
        },
    }
    summary_path.write_text(json.dumps(summary, indent=2))
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--food", default=None, help="Optional food name to focus the graph, e.g. coffee")
    parser.add_argument("--full", action="store_true", help="Build the full-KG canvas explorer")
    parser.add_argument("--floating", action="store_true", help="Build the full-KG floating-cluster explorer")
    parser.add_argument("--schema", action="store_true", help="Build the aggregate whole-KG schema plot")
    args = parser.parse_args()
    if args.schema:
        print(json.dumps(build_schema_overview_plot(), indent=2))
    elif args.floating:
        print(json.dumps(build_full_floating_visualization(), indent=2))
    elif args.full:
        print(json.dumps(build_full_visualization(), indent=2))
    else:
        print(json.dumps(build_visualizations(food_query=args.food), indent=2))


if __name__ == "__main__":
    main()
