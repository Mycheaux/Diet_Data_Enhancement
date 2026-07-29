import json
from collections import Counter
from pathlib import Path

import pandas as pd

from .sources import ROOT


OUT = ROOT / "outputs/visualizations"
DENOVO_KG = ROOT / "outputs/enhanced_hpp/1.denovo/kg"

NODE_COLORS = {
    "hpp_food": "#2563eb",
    "canonical_food": "#0f766e",
    "nutrient": "#f59e0b",
    "openfoodfacts_product": "#16a34a",
    "nova_group": "#db2777",
    "nutriscore_grade": "#65a30d",
    "chemical_class": "#ca8a04",
    "chemical_superclass": "#a16207",
    "hmdb_biospecimen": "#0891b2",
    "disease": "#dc2626",
    "pathway": "#7c3aed",
}

EDGE_COLORS = {
    "has_canonical_helper": "#64748b",
    "has_nutrient_amount_per_100g": "#f59e0b",
    "inherits_product_processing_match": "#16a34a",
    "has_nova_group": "#db2777",
    "has_nutriscore_grade": "#65a30d",
    "linked_to_foodb_chemical_class": "#ca8a04",
    "linked_to_foodb_chemical_superclass": "#a16207",
    "linked_to_hmdb_biospecimen": "#0891b2",
    "linked_to_hmdb_disease_annotation": "#dc2626",
    "linked_to_hmdb_pathway_annotation": "#7c3aed",
}

PRIORITY_NUTRIENTS = [
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


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))


def _load_denovo_kg():
    nodes_path = DENOVO_KG / "hpp_scenario_kg_nodes.csv"
    edges_path = DENOVO_KG / "hpp_scenario_kg_edges.csv"
    if not nodes_path.exists() or not edges_path.exists():
        raise FileNotFoundError("Missing de novo HPP scenario KG. Run build-hpp-comparison-layers first.")
    nodes = pd.read_csv(nodes_path, dtype=str).fillna("")
    edges = pd.read_csv(edges_path, dtype=str).fillna("")
    return nodes, edges


def _node_lookup(nodes):
    return {row["key"]: row.to_dict() for _, row in nodes.iterrows()}


def _format_node(row):
    kind = row.get("kind", "node")
    label = row.get("label", row.get("key", ""))
    return {
        "id": row["key"],
        "label": label,
        "group": kind,
        "title": f"{kind}: {label}",
        "color": NODE_COLORS.get(kind, "#94a3b8"),
        "shape": "dot" if kind != "hpp_food" else "box",
    }


def _format_edge(row):
    relation = row.get("relation", "")
    label = relation
    title = relation
    if relation == "has_nutrient_amount_per_100g" and row.get("value", ""):
        label = row.get("value", "")
        title = f"{relation}: {row.get('value')} per 100 g"
    return {
        "from": row["source"],
        "to": row["target"],
        "label": label,
        "title": title,
        "arrows": "to",
        "color": {"color": EDGE_COLORS.get(relation, "#94a3b8")},
        "font": {"size": 8, "align": "middle"},
    }


def _html_document(title, nodes_payload, edges_payload, summary_text):
    legend = "".join(
        f"<button class='legend-item active' data-kind='{kind}'><span class='swatch' style='background:{color}'></span>{kind}</button>"
        for kind, color in NODE_COLORS.items()
    )
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>{title}</title>
  <style>
    html, body {{ margin:0; width:100%; height:100%; overflow:hidden; font-family:-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    #app {{ display:grid; grid-template-rows:auto 1fr; width:100%; height:100%; }}
    header {{ padding:14px 18px; border-bottom:1px solid #e5e7eb; background:#ffffff; }}
    h1 {{ margin:0 0 6px; font-size:18px; font-weight:700; }}
    p {{ margin:0; color:#475569; font-size:13px; }}
    #network {{ position:relative; width:100%; height:100%; background:#f8fafc; }}
    svg {{ width:100%; height:100%; display:block; cursor:grab; }}
    svg:active {{ cursor:grabbing; }}
    .edge {{ stroke-width:1.2; stroke-opacity:.38; fill:none; }}
    .edge-label {{ font-size:9px; fill:#475569; pointer-events:none; paint-order:stroke; stroke:#f8fafc; stroke-width:3px; }}
    .node circle, .node rect {{ stroke:#ffffff; stroke-width:1.5px; filter:drop-shadow(0 1px 2px rgba(15,23,42,.20)); }}
    .node text {{ font-size:11px; fill:#0f172a; pointer-events:none; paint-order:stroke; stroke:#f8fafc; stroke-width:3px; }}
    .legend {{ margin-top:10px; display:flex; flex-wrap:wrap; gap:8px 14px; font-size:12px; color:#334155; }}
    .legend-item {{ display:inline-flex; align-items:center; gap:5px; border:1px solid #cbd5e1; background:#fff; color:#334155; padding:4px 7px; border-radius:6px; cursor:pointer; font:inherit; }}
    .legend-item:not(.active) {{ opacity:.35; }}
    .swatch {{ width:10px; height:10px; border-radius:50%; display:inline-block; }}
    #tooltip {{ position:absolute; display:none; max-width:320px; padding:7px 9px; border:1px solid #cbd5e1; border-radius:6px; background:#ffffff; box-shadow:0 8px 24px rgba(15,23,42,.16); color:#0f172a; font-size:12px; line-height:1.35; pointer-events:none; z-index:3; }}
  </style>
</head>
<body>
<div id="app">
  <header>
    <h1>{title}</h1>
    <p>{summary_text}</p>
    <div class="legend">{legend}</div>
  </header>
  <div id="network"></div>
</div>
<script>
const rawNodes = {json.dumps(nodes_payload)};
const rawEdges = {json.dumps(edges_payload)};
const container = document.getElementById('network');
const tooltip = document.createElement('div');
tooltip.id = 'tooltip';
container.appendChild(tooltip);

const svgNS = 'http://www.w3.org/2000/svg';
const svg = document.createElementNS(svgNS, 'svg');
container.appendChild(svg);
const defs = document.createElementNS(svgNS, 'defs');
svg.appendChild(defs);
const marker = document.createElementNS(svgNS, 'marker');
marker.setAttribute('id', 'arrow');
marker.setAttribute('viewBox', '0 0 10 10');
marker.setAttribute('refX', '9');
marker.setAttribute('refY', '5');
marker.setAttribute('markerWidth', '6');
marker.setAttribute('markerHeight', '6');
marker.setAttribute('orient', 'auto-start-reverse');
const arrowPath = document.createElementNS(svgNS, 'path');
arrowPath.setAttribute('d', 'M 0 0 L 10 5 L 0 10 z');
arrowPath.setAttribute('fill', '#64748b');
marker.appendChild(arrowPath);
defs.appendChild(marker);
const viewport = document.createElementNS(svgNS, 'g');
svg.appendChild(viewport);
const edgeLayer = document.createElementNS(svgNS, 'g');
const nodeLayer = document.createElementNS(svgNS, 'g');
viewport.appendChild(edgeLayer);
viewport.appendChild(nodeLayer);

const nodes = rawNodes.map((node, index) => ({{...node, index}}));
const nodeById = new Map(nodes.map(node => [node.id, node]));
const edges = rawEdges
  .map((edge, index) => ({{...edge, index, source: nodeById.get(edge.from), target: nodeById.get(edge.to)}}))
  .filter(edge => edge.source && edge.target);
const activeKinds = new Set(nodes.map(node => node.group));
const groupOrder = [...new Set(nodes.map(node => node.group))].sort();
const width = () => Math.max(container.clientWidth, 800);
const height = () => Math.max(container.clientHeight, 500);
const radius = () => Math.min(width(), height()) * 0.38;

function hashValue(text) {{
  let hash = 0;
  for (let i = 0; i < text.length; i += 1) hash = ((hash << 5) - hash + text.charCodeAt(i)) | 0;
  return Math.abs(hash);
}}

function seedPositions() {{
  const cx = width() / 2;
  const cy = height() / 2;
  const slots = new Map(groupOrder.map((kind, i) => [kind, (Math.PI * 2 * i) / Math.max(groupOrder.length, 1)]));
  nodes.forEach((node) => {{
    const angle = (slots.get(node.group) || 0) + ((hashValue(node.id) % 100) / 100 - 0.5) * 0.55;
    const ring = radius() * (0.42 + (hashValue(node.label || node.id) % 100) / 190);
    node.x = cx + Math.cos(angle) * ring;
    node.y = cy + Math.sin(angle) * ring;
    node.vx = 0;
    node.vy = 0;
  }});
}}

function simulate(iterations = 220) {{
  const cx = width() / 2;
  const cy = height() / 2;
  for (let tick = 0; tick < iterations; tick += 1) {{
    for (let i = 0; i < nodes.length; i += 1) {{
      const a = nodes[i];
      for (let j = i + 1; j < nodes.length; j += 1) {{
        const b = nodes[j];
        let dx = a.x - b.x;
        let dy = a.y - b.y;
        let dist2 = dx * dx + dy * dy + 0.01;
        if (dist2 > 240000) continue;
        const force = 150 / dist2;
        a.vx += dx * force;
        a.vy += dy * force;
        b.vx -= dx * force;
        b.vy -= dy * force;
      }}
    }}
    edges.forEach(edge => {{
      const dx = edge.target.x - edge.source.x;
      const dy = edge.target.y - edge.source.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const desired = edge.source.group === edge.target.group ? 110 : 185;
      const force = (dist - desired) * 0.0025;
      const fx = dx / dist * force;
      const fy = dy / dist * force;
      edge.source.vx += fx;
      edge.source.vy += fy;
      edge.target.vx -= fx;
      edge.target.vy -= fy;
    }});
    nodes.forEach(node => {{
      node.vx += (cx - node.x) * 0.0009;
      node.vy += (cy - node.y) * 0.0009;
      node.x += node.vx;
      node.y += node.vy;
      node.vx *= 0.82;
      node.vy *= 0.82;
    }});
  }}
}}

function shortLabel(label) {{
  const value = String(label || '');
  return value.length > 28 ? value.slice(0, 25) + '...' : value;
}}

function draw() {{
  edgeLayer.replaceChildren();
  nodeLayer.replaceChildren();
  const visible = node => activeKinds.has(node.group);
  edges.forEach(edge => {{
    if (!visible(edge.source) || !visible(edge.target)) return;
    const line = document.createElementNS(svgNS, 'line');
    line.setAttribute('class', 'edge');
    line.setAttribute('x1', edge.source.x);
    line.setAttribute('y1', edge.source.y);
    line.setAttribute('x2', edge.target.x);
    line.setAttribute('y2', edge.target.y);
    line.setAttribute('stroke', edge.color?.color || '#94a3b8');
    line.setAttribute('marker-end', 'url(#arrow)');
    edgeLayer.appendChild(line);
    if (edges.length <= 120) {{
      const text = document.createElementNS(svgNS, 'text');
      text.setAttribute('class', 'edge-label');
      text.setAttribute('x', (edge.source.x + edge.target.x) / 2);
      text.setAttribute('y', (edge.source.y + edge.target.y) / 2);
      text.textContent = shortLabel(edge.label || edge.title || '');
      edgeLayer.appendChild(text);
    }}
  }});
  nodes.forEach(node => {{
    if (!visible(node)) return;
    const group = document.createElementNS(svgNS, 'g');
    group.setAttribute('class', 'node');
    group.setAttribute('transform', `translate(${{node.x}},${{node.y}})`);
    const shape = document.createElementNS(svgNS, node.shape === 'box' ? 'rect' : 'circle');
    if (node.shape === 'box') {{
      shape.setAttribute('x', -42);
      shape.setAttribute('y', -15);
      shape.setAttribute('width', 84);
      shape.setAttribute('height', 30);
      shape.setAttribute('rx', 6);
    }} else {{
      shape.setAttribute('r', node.group === 'hpp_food' ? 6 : 4.5);
    }}
    shape.setAttribute('fill', node.color || '#94a3b8');
    group.appendChild(shape);
    const text = document.createElementNS(svgNS, 'text');
    text.setAttribute('y', node.shape === 'box' ? 4 : -11);
    text.setAttribute('text-anchor', 'middle');
    text.textContent = shortLabel(node.label);
    group.appendChild(text);
    group.addEventListener('mousemove', (event) => {{
      tooltip.style.display = 'block';
      tooltip.style.left = `${{event.offsetX + 12}}px`;
      tooltip.style.top = `${{event.offsetY + 12}}px`;
      tooltip.innerHTML = `<strong>${{node.label || node.id}}</strong><br>${{node.group}}`;
    }});
    group.addEventListener('mouseleave', () => {{ tooltip.style.display = 'none'; }});
    nodeLayer.appendChild(group);
  }});
}}

let view = {{ x: 0, y: 0, scale: 1 }};
function applyView() {{
  viewport.setAttribute('transform', `translate(${{view.x}},${{view.y}}) scale(${{view.scale}})`);
}}
svg.addEventListener('wheel', (event) => {{
  event.preventDefault();
  const factor = event.deltaY < 0 ? 1.08 : 0.92;
  view.scale = Math.max(0.18, Math.min(4, view.scale * factor));
  applyView();
}}, {{ passive: false }});
let dragging = false;
let lastPoint = null;
svg.addEventListener('pointerdown', (event) => {{ dragging = true; lastPoint = [event.clientX, event.clientY]; }});
svg.addEventListener('pointermove', (event) => {{
  if (!dragging || !lastPoint) return;
  view.x += event.clientX - lastPoint[0];
  view.y += event.clientY - lastPoint[1];
  lastPoint = [event.clientX, event.clientY];
  applyView();
}});
svg.addEventListener('pointerup', () => {{ dragging = false; lastPoint = null; }});
svg.addEventListener('pointerleave', () => {{ dragging = false; lastPoint = null; }});

document.querySelectorAll('.legend-item').forEach(button => {{
  button.addEventListener('click', () => {{
    const kind = button.dataset.kind;
    if (activeKinds.has(kind)) {{
      activeKinds.delete(kind);
      button.classList.remove('active');
    }} else {{
      activeKinds.add(kind);
      button.classList.add('active');
    }}
    draw();
  }});
}});

seedPositions();
simulate();
draw();
applyView();
window.addEventListener('resize', () => {{ seedPositions(); simulate(80); draw(); }});
</script>
</body>
</html>
"""


def _write_html(path, title, sub_nodes, sub_edges, summary_text):
    node_map = _node_lookup(sub_nodes)
    nodes_payload = [_format_node(row) for _, row in sub_nodes.iterrows()]
    valid = set(node_map)
    edge_rows = sub_edges[sub_edges["source"].isin(valid) & sub_edges["target"].isin(valid)]
    edges_payload = [_format_edge(row) for _, row in edge_rows.iterrows()]
    path.write_text(_html_document(title, nodes_payload, edges_payload, summary_text))
    return {
        "path": str(path),
        "nodes": int(len(nodes_payload)),
        "edges": int(len(edges_payload)),
    }


def _focused_subgraph(nodes, edges, query="coffee"):
    hpp = nodes[nodes["kind"].eq("hpp_food")].copy()
    mask = hpp["label"].str.contains(query, case=False, na=False)
    focus = hpp[mask].head(1)
    if focus.empty:
        focus = hpp.head(1)
    hpp_key = focus.iloc[0]["key"]
    selected_edges = []
    outgoing = edges[edges["source"].eq(hpp_key)].copy()
    selected_edges.append(outgoing[outgoing["relation"].eq("has_canonical_helper")])
    for relation in [
        "inherits_product_processing_match",
        "has_nova_group",
        "has_nutriscore_grade",
        "linked_to_foodb_chemical_class",
        "linked_to_foodb_chemical_superclass",
        "linked_to_hmdb_biospecimen",
        "linked_to_hmdb_disease_annotation",
        "linked_to_hmdb_pathway_annotation",
    ]:
        selected_edges.append(outgoing[outgoing["relation"].eq(relation)].head(10))

    nutrient_edges = outgoing[outgoing["relation"].eq("has_nutrient_amount_per_100g")].copy()
    priority_targets = [f"nutrient:{name}" for name in PRIORITY_NUTRIENTS]
    nutrient_edges["priority"] = nutrient_edges["target"].apply(lambda x: priority_targets.index(x) if x in priority_targets else 999)
    selected_edges.append(nutrient_edges.sort_values("priority").head(14))
    sub_edges = pd.concat(selected_edges, ignore_index=True).drop_duplicates(["source", "target", "relation"])
    keys = set([hpp_key]) | set(sub_edges["source"]) | set(sub_edges["target"])
    sub_nodes = nodes[nodes["key"].isin(keys)].copy()
    return sub_nodes, sub_edges


def _sample_full_subgraph(nodes, edges, max_hpp=180):
    hpp = nodes[nodes["kind"].eq("hpp_food")].copy().head(max_hpp)
    hpp_keys = set(hpp["key"])
    selected = []
    outgoing = edges[edges["source"].isin(hpp_keys)].copy()
    selected.append(outgoing[outgoing["relation"].eq("has_canonical_helper")])
    selected.append(outgoing[outgoing["relation"].eq("inherits_product_processing_match")])
    for relation in [
        "has_nova_group",
        "has_nutriscore_grade",
        "linked_to_foodb_chemical_class",
        "linked_to_foodb_chemical_superclass",
        "linked_to_hmdb_biospecimen",
        "linked_to_hmdb_disease_annotation",
        "linked_to_hmdb_pathway_annotation",
    ]:
        selected.append(outgoing[outgoing["relation"].eq(relation)].groupby("source", as_index=False).head(5))
    nutrient_edges = outgoing[outgoing["relation"].eq("has_nutrient_amount_per_100g")].copy()
    priority_targets = {f"nutrient:{name}" for name in PRIORITY_NUTRIENTS}
    selected.append(nutrient_edges[nutrient_edges["target"].isin(priority_targets)])
    sub_edges = pd.concat(selected, ignore_index=True).drop_duplicates(["source", "target", "relation"])
    keys = set(sub_edges["source"]) | set(sub_edges["target"])
    sub_nodes = nodes[nodes["key"].isin(keys)].copy()
    return sub_nodes, sub_edges


def _schema_summary(nodes, edges):
    node_counts = nodes["kind"].value_counts().rename_axis("node_kind").reset_index(name="count")
    edge_counts = edges["relation"].value_counts().rename_axis("relation").reset_index(name="count")
    node_counts.to_csv(OUT / "denovo_hpp_kg_schema_node_summary.csv", index=False)
    edge_counts.to_csv(OUT / "denovo_hpp_kg_schema_edge_summary.csv", index=False)

    schema_edges = []
    for _, row in edges.iterrows():
        source_kind = row["source"].split(":", 1)[0]
        target_kind = row["target"].split(":", 1)[0]
        schema_edges.append((source_kind, target_kind, row["relation"]))
    schema = (
        pd.DataFrame(schema_edges, columns=["source_kind", "target_kind", "relation"])
        .value_counts()
        .reset_index(name="count")
    )
    schema.to_csv(OUT / "denovo_hpp_kg_schema_edges.csv", index=False)

    schema_nodes = []
    schema_vis_edges = []
    for kind, count in nodes["kind"].value_counts().items():
        schema_nodes.append({
            "id": kind,
            "label": f"{kind}\\n{count:,}",
            "group": kind,
            "title": f"{kind}: {count:,} nodes",
            "color": NODE_COLORS.get(kind, "#94a3b8"),
            "shape": "box",
        })
    for _, row in schema.iterrows():
        schema_vis_edges.append({
            "from": row["source_kind"],
            "to": row["target_kind"],
            "label": f"{row['relation']}\\n{row['count']:,}",
            "title": f"{row['relation']}: {row['count']:,}",
            "arrows": "to",
            "color": {"color": EDGE_COLORS.get(row["relation"], "#94a3b8")},
        })
    path = OUT / "denovo_hpp_kg_schema_interactive.html"
    path.write_text(_html_document(
        "De Novo HPP KG Schema Overview",
        schema_nodes,
        schema_vis_edges,
        "Schema-level view of the de novo HPP scenario KG. Edge labels show relation counts.",
    ))
    return {
        "path": str(path),
        "node_summary": str(OUT / "denovo_hpp_kg_schema_node_summary.csv"),
        "edge_summary": str(OUT / "denovo_hpp_kg_schema_edge_summary.csv"),
        "schema_edges": str(OUT / "denovo_hpp_kg_schema_edges.csv"),
        "schema_node_kinds": int(len(schema_nodes)),
        "schema_edge_types": int(len(schema_vis_edges)),
    }


def build_denovo_hpp_kg_visualizations(food_query="coffee"):
    OUT.mkdir(parents=True, exist_ok=True)
    nodes, edges = _load_denovo_kg()

    focused_nodes, focused_edges = _focused_subgraph(nodes, edges, query=food_query)
    full_nodes, full_edges = _sample_full_subgraph(nodes, edges)

    focused = _write_html(
        OUT / "denovo_hpp_kg_focused_interactive.html",
        "De Novo HPP KG Focused View",
        focused_nodes,
        focused_edges,
        "Focused de novo HPP scenario KG around one food, showing per-100 g nutrients and inherited Layer 2-5 annotations.",
    )
    full = _write_html(
        OUT / "denovo_hpp_kg_full_sample_interactive.html",
        "De Novo HPP KG Full Sample View",
        full_nodes,
        full_edges,
        "Sampled browser-friendly view of the de novo HPP scenario KG. The complete KG is stored in the scenario KG CSV files.",
    )
    schema = _schema_summary(nodes, edges)

    focused_nodes.to_json(OUT / "denovo_hpp_kg_focused_nodes.json", orient="records", indent=2)
    focused_edges.to_json(OUT / "denovo_hpp_kg_focused_edges.json", orient="records", indent=2)
    full_nodes.to_json(OUT / "denovo_hpp_kg_full_sample_nodes.json", orient="records", indent=2)
    full_edges.to_json(OUT / "denovo_hpp_kg_full_sample_edges.json", orient="records", indent=2)

    relation_counts = edges["relation"].value_counts().to_dict()
    node_counts = nodes["kind"].value_counts().to_dict()
    summary = {
        "source": "outputs/enhanced_hpp/1.denovo/kg",
        "source_nodes": int(nodes.shape[0]),
        "source_edges": int(edges.shape[0]),
        "node_kind_counts": node_counts,
        "relation_counts": relation_counts,
        "outputs": {
            "focused": focused,
            "full_sample": full,
            "schema": schema,
            "focused_nodes": str(OUT / "denovo_hpp_kg_focused_nodes.json"),
            "focused_edges": str(OUT / "denovo_hpp_kg_focused_edges.json"),
            "full_sample_nodes": str(OUT / "denovo_hpp_kg_full_sample_nodes.json"),
            "full_sample_edges": str(OUT / "denovo_hpp_kg_full_sample_edges.json"),
        },
    }
    _write_json(OUT / "denovo_hpp_kg_visualization_summary.json", summary)
    return summary


if __name__ == "__main__":
    print(json.dumps(build_denovo_hpp_kg_visualizations(), indent=2))
