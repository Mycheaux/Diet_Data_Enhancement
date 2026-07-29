import json
import math
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
KG_ENHANCE = ROOT / "outputs" / "KG_enhance"
OUT = KG_ENHANCE / "visualizations"

SCENARIOS = ["denovo", "nutrimatch_based"]
METRICS = ["idf", "idf_entropy", "idf_entropy_cross_entropy"]
SIGNATURE_TYPES = ["chemical", "metabolomics", "disease", "pathway"]
FOOD_QUERIES = [
    "coffee",
    "milk",
    "chicken",
    "bread",
    "apple",
    "salad",
    "cucumber",
    "hummus",
    "egg",
    "rice",
]

NODE_COLORS = {
    "hpp_food": "#2563eb",
    "canonical_food": "#0f766e",
    "source_food": "#64748b",
    "foodatlas_food": "#2aa198",
    "foodb_food": "#16a34a",
    "openfoodfacts_product": "#16a34a",
    "nutrient": "#f59e0b",
    "foodatlas_chemical": "#d69e2e",
    "foodb_compound": "#ca8a04",
    "chemical_class": "#ca8a04",
    "chemical_superclass": "#a16207",
    "hmdb_metabolite": "#7c3aed",
    "hmdb_biospecimen": "#0891b2",
    "disease": "#ef4444",
    "pathway": "#8b5cf6",
    "human_correction": "#64748b",
    "nova_group": "#db2777",
    "nutriscore_grade": "#65a30d",
}

EDGE_COLORS = {
    "has_canonical_helper": "#64748b",
    "inherits_product_processing_match": "#16a34a",
    "has_nutrient_amount_per_100g": "#f59e0b",
    "has_nova_group": "#db2777",
    "has_nutriscore_grade": "#65a30d",
    "linked_to_foodb_chemical_class": "#ca8a04",
    "linked_to_foodb_chemical_superclass": "#a16207",
    "linked_to_hmdb_biospecimen": "#0891b2",
    "linked_to_hmdb_disease_annotation": "#ef4444",
    "linked_to_hmdb_pathway_annotation": "#8b5cf6",
}

CENTERS = {
    "hpp_food": (-2200, -240, 18),
    "canonical_food": (-1380, 260, 22),
    "source_food": (-1780, 1120, 28),
    "foodatlas_food": (-560, -1120, 16),
    "foodb_food": (-260, 1040, 24),
    "openfoodfacts_product": (-560, -1120, 18),
    "nutrient": (-820, 440, 22),
    "nova_group": (-220, -1240, 25),
    "nutriscore_grade": (-40, -940, 25),
    "foodatlas_chemical": (620, -800, 5.8),
    "foodb_compound": (740, 1000, 9.0),
    "chemical_class": (620, -800, 18),
    "chemical_superclass": (740, -420, 24),
    "hmdb_metabolite": (1880, 280, 8.2),
    "hmdb_biospecimen": (1880, 280, 36),
    "disease": (3100, -540, 11),
    "pathway": (3260, 1120, 7),
    "human_correction": (-980, -300, 28),
}

STAGE = {
    "hpp_food": 0,
    "canonical_food": 1,
    "source_food": 1,
    "foodatlas_food": 1,
    "foodb_food": 1,
    "openfoodfacts_product": 1,
    "nutrient": 1,
    "nova_group": 1,
    "nutriscore_grade": 1,
    "foodatlas_chemical": 2,
    "foodb_compound": 2,
    "chemical_class": 2,
    "chemical_superclass": 2,
    "hmdb_metabolite": 3,
    "hmdb_biospecimen": 3,
    "disease": 4,
    "pathway": 4,
    "human_correction": 1,
}


def _read_feature_matrix(scenario):
    folder = "1.denovo" if scenario == "denovo" else "2.nutrimatch_based"
    return pd.read_csv(
        ROOT / "outputs" / "enhanced_hpp" / folder / "hpp_feature_matrix_per_100g.csv",
        usecols=[
            "hpp_food_id",
            "hpp_food_name",
            "hpp_product_name",
            "hpp_short_description",
            "hpp_category",
            "number_loggings",
            "canonical_name",
        ],
        low_memory=False,
        dtype={"hpp_food_id": str},
    )


def _select_foods():
    foods = _read_feature_matrix("denovo")
    selected = []
    seen = set()
    text = (
        foods["hpp_food_name"].fillna("")
        + " "
        + foods["hpp_product_name"].fillna("")
        + " "
        + foods["hpp_short_description"].fillna("")
        + " "
        + foods["canonical_name"].fillna("")
    ).str.lower()
    for query in FOOD_QUERIES:
        match = foods.loc[text.str.contains(query, regex=False, na=False)].copy()
        if match.empty:
            continue
        match["number_loggings"] = pd.to_numeric(match["number_loggings"], errors="coerce").fillna(0)
        row = match.sort_values("number_loggings", ascending=False).iloc[0]
        hpp_id = str(row["hpp_food_id"])
        if hpp_id in seen:
            continue
        seen.add(hpp_id)
        selected.append(
            {
                "query": query,
                "hpp_food_id": hpp_id,
                "label": str(row["hpp_food_name"]),
                "product": str(row["hpp_product_name"]),
                "category": str(row["hpp_category"]),
                "number_loggings": float(row["number_loggings"]),
                "canonical_name": str(row["canonical_name"]),
            }
        )
    return selected


def _signature_path(scenario, metric, signature_type):
    return (
        KG_ENHANCE
        / scenario
        / metric
        / f"kg_food_top_weighted_{signature_type}_{metric}.csv"
    )


def _load_signature_rows(selected_foods, top_n=12):
    food_ids = {food["hpp_food_id"] for food in selected_foods}
    rows = []
    for scenario in SCENARIOS:
        for metric in METRICS:
            for signature_type in SIGNATURE_TYPES:
                path = _signature_path(scenario, metric, signature_type)
                if not path.exists():
                    continue
                df = pd.read_csv(path, dtype={"hpp_food_id": str}, low_memory=False)
                df = df[df["hpp_food_id"].isin(food_ids)].copy()
                if df.empty:
                    continue
                df = df.sort_values(["hpp_food_id", "weighted_value"], ascending=[True, False])
                df = df.groupby("hpp_food_id").head(top_n)
                for _, row in df.iterrows():
                    rows.append(
                        {
                            "scenario": scenario,
                            "metric": metric,
                            "signature_type": signature_type,
                            "hpp_food_id": str(row["hpp_food_id"]),
                            "label": str(row["feature_label"]),
                            "relation": str(row["relation"]),
                            "target_kind": str(row["target_kind"]),
                            "weighted_value": float(row["weighted_value"]),
                            "node_weight": float(row["node_information_weight"]),
                            "prevalence": int(row["node_prevalence_foods"]),
                            "entropy": float(row["normalized_entropy"]),
                            "specificity": float(row["category_specificity"]),
                            "kl": float(row["kl_divergence_vs_background"]),
                        }
                    )
    return rows


def _load_threshold_rows():
    rows = []
    for scenario in SCENARIOS:
        for metric in METRICS:
            path = KG_ENHANCE / scenario / metric / f"kg_threshold_suggestions_{metric}.csv"
            if not path.exists():
                continue
            df = pd.read_csv(path)
            for _, row in df.iterrows():
                rows.append(
                    {
                        "scenario": scenario,
                        "metric": metric,
                        "quantile": float(row["quantile"]),
                        "threshold": float(row["threshold"]),
                        "retained_fraction": float(row["retained_fraction"]),
                        "median_edges_per_food": float(row["median_edges_per_food"]),
                        "recommended": bool(row["recommended"]),
                    }
                )
    return rows


def _write_html(payload):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "kg_weighted_signature_explorer.html"
    html = """<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<title>KG Weighted Signature Explorer</title>
<style>
:root{font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#1f2933;background:#f6f6f1}
body{margin:0;background:#f6f6f1}
header{padding:14px 18px;background:#fff;border-bottom:1px solid #ddd}
h1{font-size:18px;margin:0 0 4px 0;font-weight:650}
.muted{color:#667085;font-size:13px}
.controls{display:flex;gap:12px;align-items:end;flex-wrap:wrap;padding:12px 18px;background:#fff;border-bottom:1px solid #ddd}
label{display:flex;flex-direction:column;gap:4px;font-size:12px;color:#475467}
select,input{font:inherit;padding:7px 9px;border:1px solid #cfd4dc;border-radius:6px;background:#fff}
main{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:0;min-height:calc(100vh - 118px)}
#chart{padding:14px 18px}
aside{background:#fff;border-left:1px solid #ddd;padding:14px;overflow:auto}
.panel{border:1px solid #e0e3e7;background:#fff;border-radius:8px;margin-bottom:10px;padding:10px}
.bar-row{display:grid;grid-template-columns:240px minmax(120px,1fr) 78px;align-items:center;gap:10px;margin:6px 0}
.name{font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bar-track{height:14px;background:#edf0f3;border-radius:999px;overflow:hidden}
.bar{height:100%;border-radius:999px;background:#5179b8}
.value{font-size:12px;text-align:right;color:#475467}
.food-title{font-size:15px;font-weight:650;margin-bottom:2px}
.badge{display:inline-block;padding:3px 7px;border:1px solid #d7dbe2;border-radius:999px;font-size:12px;margin:3px 4px 3px 0;background:#fafafa}
.metric-grid{display:grid;grid-template-columns:repeat(3,minmax(160px,1fr));gap:10px}
.metric-card{border:1px solid #e0e3e7;background:#fff;border-radius:8px;padding:10px}
.metric-card h3{font-size:13px;margin:0 0 8px 0}
.tiny{font-size:12px;color:#667085}
@media(max-width:900px){main{grid-template-columns:1fr}.metric-grid{grid-template-columns:1fr}.bar-row{grid-template-columns:150px 1fr 64px}aside{border-left:0;border-top:1px solid #ddd}}
</style>
</head>
<body>
<header>
<h1>KG weighted signature explorer</h1>
<div class="muted">Compare IDF, IDF+entropy, and IDF+entropy+cross-entropy/KL signatures for selected HPP foods.</div>
</header>
<div class="controls">
<label>Scenario<select id="scenario"></select></label>
<label>Food<select id="food"></select></label>
<label>Signature<select id="sig"></select></label>
<label>Minimum rank shown<input id="topn" type="range" min="4" max="12" value="8" step="1"></label>
<span class="muted" id="topLabel"></span>
</div>
<main>
<section id="chart"></section>
<aside>
<div class="panel" id="foodInfo"></div>
<div class="panel"><b>Threshold suggestions</b><div id="thresholds"></div></div>
<div class="panel"><b>How to read</b><p class="tiny">Higher bars mean the target node is more informative under that metric. Prevalence is the number of HPP foods connected to that node; lower prevalence and lower entropy usually mean more food-specific evidence.</p></div>
</aside>
</main>
<script>
const DATA=__PAYLOAD__;
const metrics=['idf','idf_entropy','idf_entropy_cross_entropy'];
const metricLabel={idf:'IDF',idf_entropy:'IDF + entropy',idf_entropy_cross_entropy:'IDF + entropy + KL'};
const scenario=document.getElementById('scenario'), food=document.getElementById('food'), sig=document.getElementById('sig'), topn=document.getElementById('topn');
function addOptions(el, vals, labels){vals.forEach(v=>el.add(new Option(labels&&labels[v]?labels[v]:v,v)))}
addOptions(scenario,[...new Set(DATA.rows.map(d=>d.scenario))]);
addOptions(sig,[...new Set(DATA.rows.map(d=>d.signature_type))]);
DATA.foods.forEach(f=>food.add(new Option(`${f.label} (${f.category})`,f.hpp_food_id)));
scenario.value='denovo'; sig.value='chemical';
function fmt(x){return Number(x).toLocaleString(undefined,{maximumFractionDigits:3})}
function render(){
  const sc=scenario.value, fid=food.value, st=sig.value, n=+topn.value;
  document.getElementById('topLabel').textContent=`top ${n}`;
  const f=DATA.foods.find(x=>x.hpp_food_id===fid);
  document.getElementById('foodInfo').innerHTML=`<div class="food-title">${f.label}</div><div class="muted">${f.product} · ${f.category}</div><div><span class="badge">HPP ${f.hpp_food_id}</span><span class="badge">${fmt(f.number_loggings)} loggings</span><span class="badge">${f.canonical_name}</span></div>`;
  const maxVal=Math.max(...DATA.rows.filter(d=>d.scenario===sc&&d.hpp_food_id===fid&&d.signature_type===st).map(d=>d.weighted_value),1e-9);
  document.getElementById('chart').innerHTML=`<div class="metric-grid">${metrics.map(m=>{
    const rows=DATA.rows.filter(d=>d.scenario===sc&&d.metric===m&&d.hpp_food_id===fid&&d.signature_type===st).sort((a,b)=>b.weighted_value-a.weighted_value).slice(0,n);
    return `<div class="metric-card"><h3>${metricLabel[m]}</h3>${rows.map(r=>`<div class="bar-row" title="prevalence ${r.prevalence}; entropy ${fmt(r.entropy)}; KL ${fmt(r.kl)}"><div class="name">${r.label}</div><div class="bar-track"><div class="bar" style="width:${Math.max(1,100*r.weighted_value/maxVal)}%"></div></div><div class="value">${fmt(r.weighted_value)}</div></div>`).join('')}</div>`;
  }).join('')}</div>`;
  const th=DATA.thresholds.filter(d=>d.scenario===sc);
  document.getElementById('thresholds').innerHTML=metrics.map(m=>{
    const rec=th.find(d=>d.metric===m&&d.recommended) || th.find(d=>d.metric===m);
    return `<div class="tiny" style="margin-top:8px"><b>${metricLabel[m]}</b><br>q=${rec.quantile}; threshold=${fmt(rec.threshold)}; retained=${fmt(100*rec.retained_fraction)}%; median edges/food=${fmt(rec.median_edges_per_food)}</div>`;
  }).join('');
}
[scenario,food,sig,topn].forEach(el=>el.addEventListener('input',render));
render();
</script>
</body>
</html>"""
    path.write_text(html.replace("__PAYLOAD__", json.dumps(payload)))
    return path


def _layout_node(kind, offset):
    cx, cy, spacing = CENTERS.get(kind, (0, 0, 24))
    golden = math.pi * (3 - math.sqrt(5))
    radius = spacing * math.sqrt(offset + 1)
    angle = offset * golden
    return round(cx + math.cos(angle) * radius, 2), round(cy + math.sin(angle) * radius, 2)


def _read_existing_mega_nodes():
    path = ROOT / "outputs" / "visualizations" / "denovo_hpp_kg_mega_flexible_data.js"
    if not path.exists():
        return []
    text = path.read_text()
    body = text.removeprefix("window.MEGA_KG_DATA=").rstrip(";" + chr(10))
    for key in ["kinds", "relations", "nodeColors", "edgeColors", "nodes", "edges"]:
        prefix = "{" if key == "kinds" else ","
        body = body.replace(prefix + key + ":", prefix + json.dumps(key) + ":")
    data = json.loads(body)
    nodes = []
    for row in data["nodes"]:
        nodes.append(
            {
                "key": row[0],
                "label": row[1],
                "kind": data["kinds"][row[2]],
                "x": row[3],
                "y": row[4],
            }
        )
    return nodes


def _scenario_nodes(scenario):
    scenario_folder = "1.denovo" if scenario == "denovo" else "2.nutrimatch_based"
    nodes_path = ROOT / "outputs" / "enhanced_hpp" / scenario_folder / "kg" / "hpp_scenario_kg_nodes.csv"
    raw_nodes = pd.read_csv(nodes_path, dtype=str).fillna("")
    offsets = defaultdict(int)
    nodes = []
    for _, row in raw_nodes.iterrows():
        kind = row["kind"]
        x, y = _layout_node(kind, offsets[kind])
        offsets[kind] += 1
        nodes.append({"key": row["key"], "label": row["label"] or row["key"], "kind": kind, "x": x, "y": y})
    return nodes


def _full_mega_plus_scenario_nodes(scenario):
    nodes = _read_existing_mega_nodes()
    seen = {node["key"] for node in nodes}
    scenario_extra = []
    offsets = defaultdict(int)
    for node in nodes:
        offsets[node["kind"]] += 1
    for node in _scenario_nodes(scenario):
        if node["key"] in seen:
            continue
        x, y = _layout_node(node["kind"], offsets[node["kind"]])
        offsets[node["kind"]] += 1
        added = dict(node)
        added["x"] = x
        added["y"] = y
        scenario_extra.append(added)
        seen.add(added["key"])
    return nodes + scenario_extra


def _write_json_array(path, rows):
    first = True
    with path.open("w") as handle:
        handle.write("[")
        for row in rows:
            if first:
                first = False
            else:
                handle.write(",")
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
        handle.write("]")


def _recommended_threshold(scenario, metric):
    path = KG_ENHANCE / scenario / metric / f"kg_threshold_suggestions_{metric}.csv"
    thresholds = pd.read_csv(path)
    recommended = thresholds.loc[thresholds["recommended"]]
    if recommended.empty:
        recommended = thresholds.loc[thresholds["quantile"].eq(0.90)]
    row = recommended.iloc[0] if not recommended.empty else thresholds.iloc[-1]
    return float(row["threshold"]), float(row["quantile"])


def _build_weighted_mega_data(scenario="denovo", metric="idf_entropy_cross_entropy"):
    scenario_folder = "1.denovo" if scenario == "denovo" else "2.nutrimatch_based"
    nodes_path = ROOT / "outputs" / "enhanced_hpp" / scenario_folder / "kg" / "hpp_scenario_kg_nodes.csv"
    weighted_edges_path = KG_ENHANCE / scenario / metric / f"kg_weighted_edges_{metric}.csv.gz"
    threshold, quantile = _recommended_threshold(scenario, metric)

    raw_nodes = pd.read_csv(nodes_path, dtype=str).fillna("")
    offsets = defaultdict(int)
    nodes = []
    for _, row in raw_nodes.iterrows():
        kind = row["kind"]
        x, y = _layout_node(kind, offsets[kind])
        offsets[kind] += 1
        nodes.append(
            {
                "key": row["key"],
                "label": row["label"] or row["key"],
                "kind": kind,
                "x": x,
                "y": y,
            }
        )
    key_to_index = {node["key"]: idx for idx, node in enumerate(nodes)}

    usecols = [
        "source",
        "target",
        "relation",
        "weighted_value",
        "node_information_weight",
        "edge_base_value",
    ]
    edge_rows = []
    relations_seen = set()
    for chunk in pd.read_csv(weighted_edges_path, usecols=usecols, chunksize=250000):
        chunk = chunk.loc[pd.to_numeric(chunk["weighted_value"], errors="coerce").ge(threshold)]
        for _, row in chunk.iterrows():
            source = str(row["source"])
            target = str(row["target"])
            if source not in key_to_index or target not in key_to_index:
                continue
            relation = str(row["relation"])
            relations_seen.add(relation)
            edge_rows.append(
                [
                    key_to_index[source],
                    key_to_index[target],
                    relation,
                    round(float(row["weighted_value"]), 6),
                    round(float(row["node_information_weight"]), 6)
                    if pd.notna(row["node_information_weight"])
                    else 0,
                ]
            )
    return nodes, edge_rows, sorted(relations_seen), threshold, quantile


def _write_weighted_mega_data_js(path, nodes, edges, relations, metric, threshold, quantile):
    kinds = sorted({node["kind"] for node in nodes})
    kind_index = {kind: idx for idx, kind in enumerate(kinds)}
    rel_index = {rel: idx for idx, rel in enumerate(relations)}
    compact_nodes = (
        [node["key"], node["label"], kind_index[node["kind"]], node["x"], node["y"]]
        for node in nodes
    )
    compact_edges = (
        [source, target, rel_index[relation], weighted_value, node_weight]
        for source, target, relation, weighted_value, node_weight in edges
    )
    node_tmp = path.with_suffix(".nodes.tmp")
    edge_tmp = path.with_suffix(".edges.tmp")
    _write_json_array(node_tmp, compact_nodes)
    _write_json_array(edge_tmp, compact_edges)
    with path.open("w") as handle:
        handle.write("window.WEIGHTED_MEGA_KG_DATA={")
        handle.write("metric:")
        handle.write(json.dumps(metric))
        handle.write(",threshold:")
        handle.write(json.dumps(threshold))
        handle.write(",quantile:")
        handle.write(json.dumps(quantile))
        handle.write(",kinds:")
        handle.write(json.dumps(kinds, separators=(",", ":")))
        handle.write(",relations:")
        handle.write(json.dumps(relations, separators=(",", ":")))
        handle.write(",nodeColors:")
        handle.write(json.dumps(NODE_COLORS, separators=(",", ":")))
        handle.write(",edgeColors:")
        handle.write(json.dumps(EDGE_COLORS, separators=(",", ":")))
        handle.write(",stage:")
        handle.write(json.dumps(STAGE, separators=(",", ":")))
        handle.write(",nodes:")
        handle.write(node_tmp.read_text())
        handle.write(",edges:")
        handle.write(edge_tmp.read_text())
        handle.write("};\n")
    node_tmp.unlink(missing_ok=True)
    edge_tmp.unlink(missing_ok=True)


def _build_weighted_edges_for_metric(scenario, metric, key_to_index):
    weighted_edges_path = KG_ENHANCE / scenario / metric / f"kg_weighted_edges_{metric}.csv.gz"
    threshold, quantile = _recommended_threshold(scenario, metric)
    usecols = [
        "source",
        "target",
        "relation",
        "weighted_value",
        "node_information_weight",
    ]
    edge_rows = []
    relations_seen = set()
    for chunk in pd.read_csv(weighted_edges_path, usecols=usecols, chunksize=250000):
        chunk = chunk.loc[pd.to_numeric(chunk["weighted_value"], errors="coerce").ge(threshold)]
        for _, row in chunk.iterrows():
            source = str(row["source"])
            target = str(row["target"])
            if source not in key_to_index or target not in key_to_index:
                continue
            relation = str(row["relation"])
            relations_seen.add(relation)
            edge_rows.append(
                [
                    key_to_index[source],
                    key_to_index[target],
                    relation,
                    round(float(row["weighted_value"]), 6),
                    round(float(row["node_information_weight"]), 6)
                    if pd.notna(row["node_information_weight"])
                    else 0,
                ]
            )
    return edge_rows, sorted(relations_seen), threshold, quantile


def _write_metric_select_mega_data_js(path, nodes, metric_payloads):
    kinds = sorted({node["kind"] for node in nodes})
    kind_index = {kind: idx for idx, kind in enumerate(kinds)}
    all_relations = sorted(
        {
            relation
            for payload in metric_payloads.values()
            for relation in payload["relations"]
        }
    )
    rel_index = {rel: idx for idx, rel in enumerate(all_relations)}
    compact_nodes = (
        [node["key"], node["label"], kind_index[node["kind"]], node["x"], node["y"]]
        for node in nodes
    )
    node_tmp = path.with_suffix(".nodes.tmp")
    _write_json_array(node_tmp, compact_nodes)

    edge_text_by_metric = {}
    tmp_paths = []
    for metric, payload in metric_payloads.items():
        compact_edges = (
            [source, target, rel_index[relation], weighted_value, node_weight]
            for source, target, relation, weighted_value, node_weight in payload["edges"]
        )
        tmp = path.with_suffix(f".{metric}.edges.tmp")
        _write_json_array(tmp, compact_edges)
        tmp_paths.append(tmp)
        edge_text_by_metric[metric] = tmp.read_text()

    with path.open("w") as handle:
        handle.write("window.WEIGHTED_MEGA_KG_DATA={")
        handle.write("metrics:")
        handle.write(json.dumps(list(metric_payloads), separators=(",", ":")))
        handle.write(",metricLabels:")
        handle.write(
            json.dumps(
                {
                    "idf": "IDF",
                    "idf_entropy": "IDF + entropy",
                    "idf_entropy_cross_entropy": "IDF + entropy + KL",
                },
                separators=(",", ":"),
            )
        )
        handle.write(",thresholds:")
        handle.write(
            json.dumps(
                {
                    metric: {
                        "threshold": payload["threshold"],
                        "quantile": payload["quantile"],
                    }
                    for metric, payload in metric_payloads.items()
                },
                separators=(",", ":"),
            )
        )
        handle.write(",kinds:")
        handle.write(json.dumps(kinds, separators=(",", ":")))
        handle.write(",relations:")
        handle.write(json.dumps(all_relations, separators=(",", ":")))
        handle.write(",nodeColors:")
        handle.write(json.dumps(NODE_COLORS, separators=(",", ":")))
        handle.write(",edgeColors:")
        handle.write(json.dumps(EDGE_COLORS, separators=(",", ":")))
        handle.write(",stage:")
        handle.write(json.dumps(STAGE, separators=(",", ":")))
        handle.write(",nodes:")
        handle.write(node_tmp.read_text())
        handle.write(",edgeSets:{")
        first = True
        for metric, text in edge_text_by_metric.items():
            if first:
                first = False
            else:
                handle.write(",")
            handle.write(json.dumps(metric))
            handle.write(":")
            handle.write(text)
        handle.write("}};\n")

    node_tmp.unlink(missing_ok=True)
    for tmp in tmp_paths:
        tmp.unlink(missing_ok=True)


def _weighted_mega_html(data_js_name):
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Weighted De Novo HPP Mega Flexible KG</title>
<style>
body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f8fafc;color:#0f172a;overflow:hidden}}
header{{height:66px;display:flex;align-items:center;gap:10px;padding:0 14px;background:#fff;border-bottom:1px solid #dbe4ee;box-sizing:border-box}}
h1{{margin:0;font-size:16px;font-weight:700;white-space:nowrap}}
input,select,button{{border:1px solid #cbd5e1;background:#fff;color:#0f172a;border-radius:6px;padding:7px 9px;font:inherit}}
button{{cursor:pointer}}#canvas{{display:block;width:100vw;height:calc(100vh - 66px);background:#f8fafc}}
#panel{{position:fixed;right:14px;top:80px;width:350px;max-height:calc(100vh - 100px);overflow:auto;background:rgba(255,255,255,.96);border:1px solid #cbd5e1;border-radius:8px;padding:14px;box-shadow:0 14px 36px rgba(15,23,42,.16);box-sizing:border-box}}
#tooltip{{position:fixed;display:none;pointer-events:none;max-width:330px;background:rgba(15,23,42,.95);color:#fff;border-radius:6px;padding:7px 9px;font-size:12px;line-height:1.35;z-index:20}}
.muted{{color:#64748b;font-size:12px}}.legend{{display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:12px;margin-top:8px}}.legend-item{{cursor:pointer;user-select:none;padding:4px 5px;border-radius:5px}}.legend-item:hover{{background:#edf2f7}}.legend-item.off{{opacity:.35;text-decoration:line-through}}.dot{{display:inline-block;width:11px;height:11px;border-radius:50%;margin-right:6px;vertical-align:-1px}}.row{{margin-top:10px}}
</style>
</head>
<body>
<header>
<h1>Weighted De Novo HPP Mega Flexible KG</h1>
<input id="search" placeholder="Search node label or key" size="30">
<button id="find">Find</button>
<label>degree <select id="degree"><option>1</option><option>2</option><option>3</option><option selected>4</option></select></label>
<label><input type="checkbox" id="allEdges"> all retained edges</label>
<button id="reset">Reset</button>
<span id="status" class="muted">Loading...</span>
</header>
<canvas id="canvas"></canvas>
<div id="tooltip"></div>
<aside id="panel">
<div class="muted" id="intro">Weighted mega graph. Edges are filtered by metric threshold and hidden by default for speed; click/search a node to show its local weighted neighborhood.</div>
<div class="legend" id="legend"></div>
<div id="details" class="row">Search or click a node.</div>
</aside>
<script src="{data_js_name}"></script>
<script>
const raw=window.WEIGHTED_MEGA_KG_DATA;
const kinds=raw.kinds, rels=raw.relations;
const nodes=raw.nodes.map((n,i)=>({{i,k:n[0],l:n[1],t:kinds[n[2]],x:n[3],y:n[4],c:raw.nodeColors[kinds[n[2]]]||'#94a3b8'}}));
const edges=raw.edges.map(e=>({{s:e[0],t:e[1],r:rels[e[2]],w:e[3],nw:e[4],c:raw.edgeColors[rels[e[2]]]||'#94a3b8'}}));
const canvas=document.getElementById('canvas'),ctx=canvas.getContext('2d'),tooltip=document.getElementById('tooltip');
document.getElementById('intro').textContent='Weighted mega graph: metric '+raw.metric+', threshold '+raw.threshold.toFixed(5)+' at q='+raw.quantile+'. All nodes are present; edges below threshold are dropped.';
const any=new Map();for(const e of edges){{if(!any.has(e.s))any.set(e.s,[]);if(!any.has(e.t))any.set(e.t,[]);any.get(e.s).push(e);any.get(e.t).push(e)}}
let scale=.07,tx=innerWidth/2,ty=(innerHeight-66)/2,selected=-1,hover=-1,hidden=new Set(),showAll=false,drag=false,last=null,nb={{nodes:new Set(),edges:[]}};
function resize(){{canvas.width=innerWidth*devicePixelRatio;canvas.height=(innerHeight-66)*devicePixelRatio;canvas.style.height=(innerHeight-66)+'px';draw()}}
function sx(x){{return x*scale+tx}} function sy(y){{return y*scale+ty}}
function visible(i){{return !hidden.has(nodes[i].t)}}
function radius(n){{if(n.t==='hpp_food')return 3.2;if(n.t==='canonical_food')return 2.9;if(n.t==='disease'||n.t==='pathway')return 1.7;if(n.t.includes('chemical'))return 1.15;return 1.5}}
function degree(){{return Number(document.getElementById('degree').value||4)}}
function stage(kind){{return raw.stage[kind]??0}}
function connectedTarget(e,idx){{return e.s===idx?e.t:e.s}}
function local(start){{if(start<0)return{{nodes:new Set(),edges:[]}};const keep=new Set([start]),localEdges=[],edgeSeen=new Set();let frontier=new Set([start]);for(let d=0;d<degree();d++){{const next=new Set();for(const idx of frontier){{for(const e of any.get(idx)||[]){{const target=connectedTarget(e,idx);if(target<0||!visible(target))continue;const edgeKey=e.s+'|'+e.t+'|'+e.r;if(!edgeSeen.has(edgeKey)){{edgeSeen.add(edgeKey);localEdges.push(e)}}if(!keep.has(target)){{keep.add(target);next.add(target)}}}}}}frontier=next;if(!frontier.size)break}}return{{nodes:keep,edges:localEdges}}}}
function draw(){{ctx.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);ctx.clearRect(0,0,innerWidth,innerHeight-66);ctx.fillStyle='#f8fafc';ctx.fillRect(0,0,innerWidth,innerHeight-66);const drawEdges=showAll?edges:nb.edges;for(const e of drawEdges){{if(!visible(e.s)||!visible(e.t))continue;const a=nodes[e.s],b=nodes[e.t],ax=sx(a.x),ay=sy(a.y),bx=sx(b.x),by=sy(b.y);if((ax<-60&&bx<-60)||(ay<-60&&by<-60)||(ax>innerWidth+60&&bx>innerWidth+60)||(ay>innerHeight+60&&by>innerHeight+60))continue;const hi=selected>=0&&nb.nodes.has(e.s)&&nb.nodes.has(e.t);ctx.globalAlpha=hi?1:(showAll?.04:.62);ctx.strokeStyle=e.c;ctx.lineWidth=hi?Math.min(4,1+Math.log1p(e.w)):Math.min(1.4,.35+Math.log1p(e.w)/8);ctx.setLineDash(e.r.includes('negative')?[5,4]:[]);ctx.beginPath();ctx.moveTo(ax,ay);ctx.lineTo(bx,by);ctx.stroke()}}ctx.setLineDash([]);for(let i=0;i<nodes.length;i++){{if(!visible(i))continue;const n=nodes[i],x=sx(n.x),y=sy(n.y);if(x<-20||y<-20||x>innerWidth+20||y>innerHeight+20)continue;const dim=selected>=0&&!nb.nodes.has(i);ctx.globalAlpha=dim?.06:.88;ctx.fillStyle=n.c;ctx.beginPath();ctx.arc(x,y,Math.max(.7,radius(n)*Math.sqrt(scale*14)),0,Math.PI*2);ctx.fill()}}ctx.globalAlpha=1;if(selected>=0){{const n=nodes[selected];ctx.strokeStyle='#020617';ctx.lineWidth=2.4;ctx.beginPath();ctx.arc(sx(n.x),sy(n.y),6.5,0,Math.PI*2);ctx.stroke();ctx.fillStyle='#0f172a';ctx.font='13px system-ui';ctx.fillText(n.l.length>48?n.l.slice(0,45)+'...':n.l,sx(n.x)+10,sy(n.y)+4)}}if(hover>=0&&hover!==selected){{const n=nodes[hover];ctx.strokeStyle='#334155';ctx.lineWidth=1.8;ctx.beginPath();ctx.arc(sx(n.x),sy(n.y),5,0,Math.PI*2);ctx.stroke()}}document.getElementById('status').textContent=nodes.length.toLocaleString()+' nodes, '+edges.length.toLocaleString()+' retained weighted edges'}}
function nearest(cx,cy){{const x=cx,y=cy-66;let best=-1,bestD=18*18,cands=selected>=0?nb.nodes:null;for(let i=0;i<nodes.length;i++){{if(!visible(i))continue;if(cands&&!cands.has(i))continue;const dx=sx(nodes[i].x)-x,dy=sy(nodes[i].y)-y,d=dx*dx+dy*dy;if(d<bestD){{best=i;bestD=d}}}}return best}}
function select(i){{selected=i;nb=local(i);const n=nodes[i],direct=(any.get(i)||[]).length;const top=nb.edges.slice().sort((a,b)=>b.w-a.w).slice(0,8).map(e=>'<br>'+e.r+': '+e.w.toFixed(4)).join('');document.getElementById('details').innerHTML='<b>'+n.l+'</b><br><span class="muted">'+n.t+' · '+n.k+'</span><br>'+direct.toLocaleString()+' retained direct edges<br>'+nb.nodes.size.toLocaleString()+' outgoing-neighborhood nodes, '+nb.edges.length.toLocaleString()+' edges'+top;draw()}}
function tip(i,e){{if(i<0){{tooltip.style.display='none';return}}const n=nodes[i];tooltip.innerHTML='<b>'+n.l+'</b><br>'+n.t;tooltip.style.left=Math.min(e.clientX+12,innerWidth-340)+'px';tooltip.style.top=Math.min(e.clientY+12,innerHeight-80)+'px';tooltip.style.display='block'}}
canvas.addEventListener('mousedown',e=>{{last={{x:e.clientX,y:e.clientY}};const n=nearest(e.clientX,e.clientY);if(n>=0)select(n);else drag=true}});
canvas.addEventListener('mousemove',e=>{{if(drag&&last){{tx+=e.clientX-last.x;ty+=e.clientY-last.y;last={{x:e.clientX,y:e.clientY}};draw();return}}const n=nearest(e.clientX,e.clientY);if(n!==hover){{hover=n;draw()}}tip(n,e)}});
addEventListener('mouseup',()=>{{drag=false;last=null}});canvas.addEventListener('mouseleave',()=>{{hover=-1;tip(-1,{{}});draw()}});
canvas.addEventListener('wheel',e=>{{e.preventDefault();const old=scale;scale*=e.deltaY<0?1.14:.88;scale=Math.max(.004,Math.min(3,scale));const mx=e.clientX,my=e.clientY-66;tx=mx-(mx-tx)*(scale/old);ty=my-(my-ty)*(scale/old);draw()}},{{passive:false}});
document.getElementById('allEdges').addEventListener('change',e=>{{showAll=e.target.checked;draw()}});document.getElementById('degree').addEventListener('change',()=>{{if(selected>=0)select(selected);else draw()}});
document.getElementById('reset').addEventListener('click',()=>{{selected=-1;hover=-1;nb={{nodes:new Set(),edges:[]}};scale=.07;tx=innerWidth/2;ty=(innerHeight-66)/2;document.getElementById('details').textContent='Search or click a node.';draw()}});
function findNode(){{const q=document.getElementById('search').value.trim().toLowerCase();if(!q)return;const i=nodes.findIndex((n,idx)=>visible(idx)&&(n.l.toLowerCase().includes(q)||n.k.toLowerCase().includes(q)));if(i>=0){{tx=innerWidth/2-nodes[i].x*scale;ty=(innerHeight-66)/2-nodes[i].y*scale;select(i)}}}}
document.getElementById('find').addEventListener('click',findNode);document.getElementById('search').addEventListener('keydown',e=>{{if(e.key==='Enter')findNode()}});
const legend=document.getElementById('legend');Object.entries(raw.nodeColors).forEach(([kind,color])=>{{const item=document.createElement('div');item.className='legend-item';item.innerHTML='<span class="dot" style="background:'+color+'"></span>'+kind;item.onclick=()=>{{if(hidden.has(kind)){{hidden.delete(kind);item.classList.remove('off')}}else{{hidden.add(kind);item.classList.add('off')}}if(selected>=0&&!visible(selected))selected=-1;nb=selected>=0?local(selected):{{nodes:new Set(),edges:[]}};draw()}};legend.appendChild(item)}});
resize();addEventListener('resize',resize);
</script>
</body>
</html>
"""


def _metric_select_mega_html(data_js_name):
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Weighted De Novo HPP Mega Flexible KG</title>
<style>
body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f8fafc;color:#0f172a;overflow:hidden}}
header{{height:66px;display:flex;align-items:center;gap:10px;padding:0 14px;background:#fff;border-bottom:1px solid #dbe4ee;box-sizing:border-box}}
h1{{margin:0;font-size:16px;font-weight:700;white-space:nowrap}}
input,select,button{{border:1px solid #cbd5e1;background:#fff;color:#0f172a;border-radius:6px;padding:7px 9px;font:inherit}}
button{{cursor:pointer}}#canvas{{display:block;width:100vw;height:calc(100vh - 66px);background:#f8fafc}}
#panel{{position:fixed;right:14px;top:80px;width:350px;max-height:calc(100vh - 100px);overflow:auto;background:rgba(255,255,255,.96);border:1px solid #cbd5e1;border-radius:8px;padding:14px;box-shadow:0 14px 36px rgba(15,23,42,.16);box-sizing:border-box}}
#tooltip{{position:fixed;display:none;pointer-events:none;max-width:330px;background:rgba(15,23,42,.95);color:#fff;border-radius:6px;padding:7px 9px;font-size:12px;line-height:1.35;z-index:20}}
.muted{{color:#64748b;font-size:12px}}.legend{{display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:12px;margin-top:8px}}.legend-item{{cursor:pointer;user-select:none;padding:4px 5px;border-radius:5px}}.legend-item:hover{{background:#edf2f7}}.legend-item.off{{opacity:.35;text-decoration:line-through}}.dot{{display:inline-block;width:11px;height:11px;border-radius:50%;margin-right:6px;vertical-align:-1px}}.row{{margin-top:10px}}
</style>
</head>
<body>
<header>
<h1>Weighted De Novo HPP Mega Flexible KG</h1>
<input id="search" placeholder="Search node label or key" size="27">
<button id="find">Find</button>
<label>metric <select id="metric"></select></label>
<label>degree <select id="degree"><option>1</option><option>2</option><option>3</option><option selected>4</option></select></label>
<label><input type="checkbox" id="allEdges"> all retained edges</label>
<button id="reset">Reset</button>
<span id="status" class="muted">Loading...</span>
</header>
<canvas id="canvas"></canvas>
<div id="tooltip"></div>
<aside id="panel">
<div class="muted" id="intro">Weighted mega graph. Select a metric, then click/search a node to show its local weighted neighborhood.</div>
<div class="legend" id="legend"></div>
<div id="details" class="row">Search or click a node.</div>
</aside>
<script src="{data_js_name}"></script>
<script>
const raw=window.WEIGHTED_MEGA_KG_DATA;
const kinds=raw.kinds, rels=raw.relations;
const nodes=raw.nodes.map((n,i)=>({{i,k:n[0],l:n[1],t:kinds[n[2]],x:n[3],y:n[4],c:raw.nodeColors[kinds[n[2]]]||'#94a3b8'}}));
const metricSelect=document.getElementById('metric');
raw.metrics.forEach(m=>metricSelect.add(new Option(raw.metricLabels[m]||m,m)));
metricSelect.value='idf_entropy_cross_entropy';
let edges=[], any=new Map();
const canvas=document.getElementById('canvas'),ctx=canvas.getContext('2d'),tooltip=document.getElementById('tooltip');
let scale=.07,tx=innerWidth/2,ty=(innerHeight-66)/2,selected=-1,hover=-1,hidden=new Set(),showAll=false,drag=false,last=null,nb={{nodes:new Set(),edges:[]}};
function loadMetric(){{const m=metricSelect.value;edges=raw.edgeSets[m].map(e=>({{s:e[0],t:e[1],r:rels[e[2]],w:e[3],nw:e[4],c:raw.edgeColors[rels[e[2]]]||'#94a3b8'}}));any=new Map();for(const e of edges){{if(!any.has(e.s))any.set(e.s,[]);if(!any.has(e.t))any.set(e.t,[]);any.get(e.s).push(e);any.get(e.t).push(e)}}const th=raw.thresholds[m];document.getElementById('intro').textContent='Weighted mega graph: metric '+(raw.metricLabels[m]||m)+', threshold '+th.threshold.toFixed(5)+' at q='+th.quantile+'. All nodes are present; retained edges switch with metric.';selected=-1;hover=-1;nb={{nodes:new Set(),edges:[]}};document.getElementById('details').textContent='Search or click a node.';draw()}}
function resize(){{canvas.width=innerWidth*devicePixelRatio;canvas.height=(innerHeight-66)*devicePixelRatio;canvas.style.height=(innerHeight-66)+'px';draw()}}
function sx(x){{return x*scale+tx}} function sy(y){{return y*scale+ty}}
function visible(i){{return !hidden.has(nodes[i].t)}}
function radius(n){{if(n.t==='hpp_food')return 3.2;if(n.t==='canonical_food')return 2.9;if(n.t==='disease'||n.t==='pathway')return 1.7;if(n.t.includes('chemical'))return 1.15;return 1.5}}
function degree(){{return Number(document.getElementById('degree').value||4)}}
function stage(kind){{return raw.stage[kind]??0}}
function edgeForwardFrom(e,idx){{if(e.s===idx)return e.t;if(e.t===idx){{const a=stage(nodes[e.t].t),b=stage(nodes[e.s].t);if(b>=a)return e.s}}return -1}}
function local(start){{if(start<0)return{{nodes:new Set(),edges:[]}};const keep=new Set([start]),localEdges=[];let frontier=new Set([start]);for(let d=0;d<degree();d++){{const next=new Set();for(const idx of frontier){{for(const e of any.get(idx)||[]){{const target=edgeForwardFrom(e,idx);if(target<0||!visible(target))continue;localEdges.push(e);if(!keep.has(target)){{keep.add(target);next.add(target)}}}}}}frontier=next;if(!frontier.size)break}}return{{nodes:keep,edges:localEdges}}}}
function draw(){{ctx.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);ctx.clearRect(0,0,innerWidth,innerHeight-66);ctx.fillStyle='#f8fafc';ctx.fillRect(0,0,innerWidth,innerHeight-66);const drawEdges=showAll?edges:nb.edges;for(const e of drawEdges){{if(!visible(e.s)||!visible(e.t))continue;const a=nodes[e.s],b=nodes[e.t],ax=sx(a.x),ay=sy(a.y),bx=sx(b.x),by=sy(b.y);if((ax<-60&&bx<-60)||(ay<-60&&by<-60)||(ax>innerWidth+60&&bx>innerWidth+60)||(ay>innerHeight+60&&by>innerHeight+60))continue;const hi=selected>=0&&nb.nodes.has(e.s)&&nb.nodes.has(e.t);ctx.globalAlpha=hi?1:(showAll?.04:.62);ctx.strokeStyle=e.c;ctx.lineWidth=hi?Math.min(4,1+Math.log1p(e.w)):Math.min(1.4,.35+Math.log1p(e.w)/8);ctx.setLineDash(e.r.includes('negative')?[5,4]:[]);ctx.beginPath();ctx.moveTo(ax,ay);ctx.lineTo(bx,by);ctx.stroke()}}ctx.setLineDash([]);for(let i=0;i<nodes.length;i++){{if(!visible(i))continue;const n=nodes[i],x=sx(n.x),y=sy(n.y);if(x<-20||y<-20||x>innerWidth+20||y>innerHeight+20)continue;const dim=selected>=0&&!nb.nodes.has(i);ctx.globalAlpha=dim?.06:.88;ctx.fillStyle=n.c;ctx.beginPath();ctx.arc(x,y,Math.max(.7,radius(n)*Math.sqrt(scale*14)),0,Math.PI*2);ctx.fill()}}ctx.globalAlpha=1;if(selected>=0){{const n=nodes[selected];ctx.strokeStyle='#020617';ctx.lineWidth=2.4;ctx.beginPath();ctx.arc(sx(n.x),sy(n.y),6.5,0,Math.PI*2);ctx.stroke();ctx.fillStyle='#0f172a';ctx.font='13px system-ui';ctx.fillText(n.l.length>48?n.l.slice(0,45)+'...':n.l,sx(n.x)+10,sy(n.y)+4)}}if(hover>=0&&hover!==selected){{const n=nodes[hover];ctx.strokeStyle='#334155';ctx.lineWidth=1.8;ctx.beginPath();ctx.arc(sx(n.x),sy(n.y),5,0,Math.PI*2);ctx.stroke()}}document.getElementById('status').textContent=nodes.length.toLocaleString()+' nodes, '+edges.length.toLocaleString()+' retained weighted edges'}}
function nearest(cx,cy){{const x=cx,y=cy-66;let best=-1,bestD=18*18,cands=selected>=0?nb.nodes:null;for(let i=0;i<nodes.length;i++){{if(!visible(i))continue;if(cands&&!cands.has(i))continue;const dx=sx(nodes[i].x)-x,dy=sy(nodes[i].y)-y,d=dx*dx+dy*dy;if(d<bestD){{best=i;bestD=d}}}}return best}}
function select(i){{selected=i;nb=local(i);const n=nodes[i],direct=(any.get(i)||[]).length;const top=nb.edges.slice().sort((a,b)=>b.w-a.w).slice(0,8).map(e=>'<br>'+e.r+': '+e.w.toFixed(4)).join('');document.getElementById('details').innerHTML='<b>'+n.l+'</b><br><span class="muted">'+n.t+' · '+n.k+'</span><br>'+direct.toLocaleString()+' retained direct edges<br>'+nb.nodes.size.toLocaleString()+' outgoing-neighborhood nodes, '+nb.edges.length.toLocaleString()+' edges'+top;draw()}}
function tip(i,e){{if(i<0){{tooltip.style.display='none';return}}const n=nodes[i];tooltip.innerHTML='<b>'+n.l+'</b><br>'+n.t;tooltip.style.left=Math.min(e.clientX+12,innerWidth-340)+'px';tooltip.style.top=Math.min(e.clientY+12,innerHeight-80)+'px';tooltip.style.display='block'}}
canvas.addEventListener('mousedown',e=>{{last={{x:e.clientX,y:e.clientY}};const n=nearest(e.clientX,e.clientY);if(n>=0)select(n);else drag=true}});
canvas.addEventListener('mousemove',e=>{{if(drag&&last){{tx+=e.clientX-last.x;ty+=e.clientY-last.y;last={{x:e.clientX,y:e.clientY}};draw();return}}const n=nearest(e.clientX,e.clientY);if(n!==hover){{hover=n;draw()}}tip(n,e)}});
addEventListener('mouseup',()=>{{drag=false;last=null}});canvas.addEventListener('mouseleave',()=>{{hover=-1;tip(-1,{{}});draw()}});
canvas.addEventListener('wheel',e=>{{e.preventDefault();const old=scale;scale*=e.deltaY<0?1.14:.88;scale=Math.max(.004,Math.min(3,scale));const mx=e.clientX,my=e.clientY-66;tx=mx-(mx-tx)*(scale/old);ty=my-(my-ty)*(scale/old);draw()}},{{passive:false}});
document.getElementById('allEdges').addEventListener('change',e=>{{showAll=e.target.checked;draw()}});document.getElementById('degree').addEventListener('change',()=>{{if(selected>=0)select(selected);else draw()}});metricSelect.addEventListener('change',loadMetric);
document.getElementById('reset').addEventListener('click',()=>{{selected=-1;hover=-1;nb={{nodes:new Set(),edges:[]}};scale=.07;tx=innerWidth/2;ty=(innerHeight-66)/2;document.getElementById('details').textContent='Search or click a node.';draw()}});
function findNode(){{const q=document.getElementById('search').value.trim().toLowerCase();if(!q)return;const i=nodes.findIndex((n,idx)=>visible(idx)&&(n.l.toLowerCase().includes(q)||n.k.toLowerCase().includes(q)));if(i>=0){{tx=innerWidth/2-nodes[i].x*scale;ty=(innerHeight-66)/2-nodes[i].y*scale;select(i)}}}}
document.getElementById('find').addEventListener('click',findNode);document.getElementById('search').addEventListener('keydown',e=>{{if(e.key==='Enter')findNode()}});
const legend=document.getElementById('legend');Object.entries(raw.nodeColors).forEach(([kind,color])=>{{const item=document.createElement('div');item.className='legend-item';item.innerHTML='<span class="dot" style="background:'+color+'"></span>'+kind;item.onclick=()=>{{if(hidden.has(kind)){{hidden.delete(kind);item.classList.remove('off')}}else{{hidden.add(kind);item.classList.add('off')}}if(selected>=0&&!visible(selected))selected=-1;nb=selected>=0?local(selected):{{nodes:new Set(),edges:[]}};draw()}};legend.appendChild(item)}});
loadMetric();resize();addEventListener('resize',resize);
</script>
</body>
</html>
"""


def build_metric_select_weighted_mega_visualization(scenario="denovo"):
    OUT.mkdir(parents=True, exist_ok=True)
    scenario_folder = "1.denovo" if scenario == "denovo" else "2.nutrimatch_based"
    nodes_path = ROOT / "outputs" / "enhanced_hpp" / scenario_folder / "kg" / "hpp_scenario_kg_nodes.csv"
    raw_nodes = pd.read_csv(nodes_path, dtype=str).fillna("")
    offsets = defaultdict(int)
    nodes = []
    for _, row in raw_nodes.iterrows():
        kind = row["kind"]
        x, y = _layout_node(kind, offsets[kind])
        offsets[kind] += 1
        nodes.append({"key": row["key"], "label": row["label"] or row["key"], "kind": kind, "x": x, "y": y})
    key_to_index = {node["key"]: idx for idx, node in enumerate(nodes)}

    metric_payloads = {}
    for metric in METRICS:
        edge_rows, relations, threshold, quantile = _build_weighted_edges_for_metric(
            scenario, metric, key_to_index
        )
        metric_payloads[metric] = {
            "edges": edge_rows,
            "relations": relations,
            "threshold": threshold,
            "quantile": quantile,
        }

    stem = f"{scenario}_hpp_kg_weighted_metric_select_mega_flexible"
    data_path = OUT / f"{stem}_data.js"
    html_path = OUT / f"{stem}.html"
    _write_metric_select_mega_data_js(data_path, nodes, metric_payloads)
    html_path.write_text(_metric_select_mega_html(data_path.name))
    summary = {
        "html": str(html_path),
        "data": str(data_path),
        "scenario": scenario,
        "metrics": list(metric_payloads),
        "nodes": len(nodes),
        "retained_edges_by_metric": {
            metric: len(payload["edges"]) for metric, payload in metric_payloads.items()
        },
        "thresholds": {
            metric: {"threshold": payload["threshold"], "quantile": payload["quantile"]}
            for metric, payload in metric_payloads.items()
        },
        "node_kind_counts": pd.Series([node["kind"] for node in nodes]).value_counts().to_dict(),
    }
    (OUT / f"{stem}_summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def _build_threshold_app_edges(scenario, key_to_index):
    metric_frames = []
    for metric in METRICS:
        path = KG_ENHANCE / scenario / metric / f"kg_weighted_edges_{metric}.csv.gz"
        frame = pd.read_csv(
            path,
            usecols=["source", "target", "relation", "weighted_value"],
            low_memory=False,
        )
        frame = frame.rename(columns={"weighted_value": metric})
        metric_frames.append(frame)
    merged = metric_frames[0]
    for frame in metric_frames[1:]:
        merged = merged.merge(frame, on=["source", "target", "relation"], how="left")
    merged[METRICS] = merged[METRICS].fillna(0)

    relations = sorted(merged["relation"].astype(str).unique())
    rel_index = {rel: idx for idx, rel in enumerate(relations)}
    edge_rows = []
    for _, row in merged.iterrows():
        source = str(row["source"])
        target = str(row["target"])
        if source not in key_to_index or target not in key_to_index:
            continue
        edge_rows.append(
            [
                key_to_index[source],
                key_to_index[target],
                rel_index[str(row["relation"])],
                round(float(row["idf"]), 6),
                round(float(row["idf_entropy"]), 6),
                round(float(row["idf_entropy_cross_entropy"]), 6),
            ]
        )
    return edge_rows, relations


def _write_threshold_app_data_js(path, nodes, edges, relations, threshold_options):
    kinds = sorted({node["kind"] for node in nodes})
    kind_index = {kind: idx for idx, kind in enumerate(kinds)}
    compact_nodes = (
        [node["key"], node["label"], kind_index[node["kind"]], node["x"], node["y"]]
        for node in nodes
    )
    node_tmp = path.with_suffix(".nodes.tmp")
    edge_tmp = path.with_suffix(".edges.tmp")
    _write_json_array(node_tmp, compact_nodes)
    _write_json_array(edge_tmp, edges)
    with path.open("w") as handle:
        handle.write("window.THRESHOLD_MEGA_KG_DATA={")
        handle.write("metrics:")
        handle.write(json.dumps(METRICS, separators=(",", ":")))
        handle.write(",metricLabels:")
        handle.write(
            json.dumps(
                {
                    "idf": "IDF",
                    "idf_entropy": "IDF + entropy",
                    "idf_entropy_cross_entropy": "IDF + entropy + KL",
                },
                separators=(",", ":"),
            )
        )
        handle.write(",thresholdOptions:")
        handle.write(json.dumps(threshold_options, separators=(",", ":")))
        handle.write(",kinds:")
        handle.write(json.dumps(kinds, separators=(",", ":")))
        handle.write(",relations:")
        handle.write(json.dumps(relations, separators=(",", ":")))
        handle.write(",nodeColors:")
        handle.write(json.dumps(NODE_COLORS, separators=(",", ":")))
        handle.write(",edgeColors:")
        handle.write(json.dumps(EDGE_COLORS, separators=(",", ":")))
        handle.write(",stage:")
        handle.write(json.dumps(STAGE, separators=(",", ":")))
        handle.write(",nodes:")
        handle.write(node_tmp.read_text())
        handle.write(",edges:")
        handle.write(edge_tmp.read_text())
        handle.write("};\n")
    node_tmp.unlink(missing_ok=True)
    edge_tmp.unlink(missing_ok=True)


def _threshold_mega_app_html(data_js_name):
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Threshold Weighted HPP Mega KG</title>
<style>
body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f8fafc;color:#0f172a;overflow:hidden}}
header{{height:72px;display:flex;align-items:center;gap:10px;padding:0 14px;background:#fff;border-bottom:1px solid #dbe4ee;box-sizing:border-box;flex-wrap:wrap}}
h1{{margin:0;font-size:16px;font-weight:700;white-space:nowrap}}
input,select,button{{border:1px solid #cbd5e1;background:#fff;color:#0f172a;border-radius:6px;padding:7px 9px;font:inherit}}
input[type=range]{{padding:0;width:170px}}button{{cursor:pointer}}#canvas{{display:block;width:100vw;height:calc(100vh - 72px);background:#f8fafc}}
#panel{{position:fixed;right:14px;top:86px;width:370px;max-height:calc(100vh - 106px);overflow:auto;background:rgba(255,255,255,.96);border:1px solid #cbd5e1;border-radius:8px;padding:14px;box-shadow:0 14px 36px rgba(15,23,42,.16);box-sizing:border-box}}
#tooltip{{position:fixed;display:none;pointer-events:none;max-width:330px;background:rgba(15,23,42,.95);color:#fff;border-radius:6px;padding:7px 9px;font-size:12px;line-height:1.35;z-index:20}}
.muted{{color:#64748b;font-size:12px}}.legend{{display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:12px;margin-top:8px}}.legend-item{{cursor:pointer;user-select:none;padding:4px 5px;border-radius:5px}}.legend-item:hover{{background:#edf2f7}}.legend-item.off{{opacity:.35;text-decoration:line-through}}.dot{{display:inline-block;width:11px;height:11px;border-radius:50%;margin-right:6px;vertical-align:-1px}}.row{{margin-top:10px}}label{{font-size:12px;color:#475569}}#thresholdReadout{{min-width:210px}}
</style>
</head>
<body>
<header>
<h1>Threshold Weighted HPP Mega KG</h1>
<input id="search" placeholder="Search node label or key" size="24">
<button id="find">Find</button>
<label>metric <select id="metric"></select></label>
<label>threshold <input id="threshold" type="range" min="0" max="5" step="1" value="2"></label>
<span id="thresholdReadout" class="muted"></span>
<label>degree <select id="degree"><option>1</option><option>2</option><option>3</option><option selected>4</option></select></label>
<label><input type="checkbox" id="allEdges"> all retained edges</label>
<button id="reset">Reset</button>
<span id="status" class="muted">Loading...</span>
</header>
<canvas id="canvas"></canvas>
<div id="tooltip"></div>
<aside id="panel">
<div class="muted" id="intro">All nodes are retained. Raising the threshold drops edges only; nodes outside the selected retained neighborhood are faded.</div>
<div class="legend" id="legend"></div>
<div id="details" class="row">Search or click a node.</div>
</aside>
<script src="{data_js_name}"></script>
<script>
const raw=window.THRESHOLD_MEGA_KG_DATA;
const kinds=raw.kinds, rels=raw.relations, metrics=raw.metrics;
const metricIndex={{idf:3,idf_entropy:4,idf_entropy_cross_entropy:5}};
const nodes=raw.nodes.map((n,i)=>({{i,k:n[0],l:n[1],t:kinds[n[2]],x:n[3],y:n[4],c:raw.nodeColors[kinds[n[2]]]||'#94a3b8'}}));
const edges=raw.edges.map(e=>({{s:e[0],t:e[1],r:rels[e[2]],v:e}}));
const metricSelect=document.getElementById('metric'),thresholdSlider=document.getElementById('threshold');
metrics.forEach(m=>metricSelect.add(new Option(raw.metricLabels[m]||m,m)));metricSelect.value='idf_entropy_cross_entropy';
const canvas=document.getElementById('canvas'),ctx=canvas.getContext('2d'),tooltip=document.getElementById('tooltip');
let scale=.07,tx=innerWidth/2,ty=(innerHeight-72)/2,selected=-1,hover=-1,hidden=new Set(),showAll=false,drag=false,last=null,nb={{nodes:new Set(),edges:[]}},any=new Map();
function metric(){{return metricSelect.value}} function thresholdObj(){{return raw.thresholdOptions[metric()][Number(thresholdSlider.value)]}} function threshold(){{return thresholdObj().threshold}}
function w(e){{return e.v[metricIndex[metric()]]||0}} function edgePass(e){{return w(e)>=threshold()}}
function rebuildAdj(){{any=new Map();for(const e of edges){{if(!edgePass(e))continue;if(!any.has(e.s))any.set(e.s,[]);if(!any.has(e.t))any.set(e.t,[]);any.get(e.s).push(e);any.get(e.t).push(e)}}}}
function resize(){{canvas.width=innerWidth*devicePixelRatio;canvas.height=(innerHeight-72)*devicePixelRatio;canvas.style.height=(innerHeight-72)+'px';draw()}}
function sx(x){{return x*scale+tx}} function sy(y){{return y*scale+ty}}
function visible(i){{return !hidden.has(nodes[i].t)}} function radius(n){{if(n.t==='hpp_food')return 3.2;if(n.t==='canonical_food')return 2.9;if(n.t==='disease'||n.t==='pathway')return 1.7;if(n.t.includes('chemical'))return 1.15;return 1.5}}
function degree(){{return Number(document.getElementById('degree').value||4)}} function stage(kind){{return raw.stage[kind]??0}}
function connectedTarget(e,idx){{return e.s===idx?e.t:e.s}}
function isFoodKind(k){{return k==='hpp_food'||k==='canonical_food'||k==='openfoodfacts_product'||k==='foodatlas_food'||k==='foodb_food'||k==='source_food'}}
function isPrimaryBioKind(k){{return k==='nutrient'||k==='chemical_class'||k==='chemical_superclass'||k==='foodatlas_chemical'||k==='foodb_compound'||k==='hmdb_metabolite'||k==='hmdb_biospecimen'}}
function isDownstreamKind(k){{return k==='disease'||k==='pathway'}}
function isProcessingKind(k){{return k==='nova_group'||k==='nutriscore_grade'}}
function cloneVirtualEdge(anchor,e,target){{return {{s:anchor,t:target,r:e.r,w:w(e),v:e.v,virtual:true}}}}
function rootDownstreamEdges(root){{return (any.get(root)||[]).filter(e=>{{const t=connectedTarget(e,root);return visible(t)&&isDownstreamKind(nodes[t].t)}})}}
function biologicalNeighbors(idx,root){{const out=[];const idxKind=nodes[idx].t;for(const e of any.get(idx)||[]){{const target=connectedTarget(e,idx);if(target<0||!visible(target))continue;const targetKind=nodes[target].t;if(idx===root&&isFoodKind(idxKind)){{if(isPrimaryBioKind(targetKind)||isProcessingKind(targetKind)||targetKind==='canonical_food'||targetKind==='openfoodfacts_product')out.push([target,e]);}}else if(isPrimaryBioKind(idxKind)){{if(isDownstreamKind(targetKind)||isPrimaryBioKind(targetKind))out.push([target,e]);}}else if(isFoodKind(idxKind)){{if(isPrimaryBioKind(targetKind)||isProcessingKind(targetKind))out.push([target,e]);}}else if(!isDownstreamKind(idxKind)){{if((stage(targetKind)>=stage(idxKind))&&!isFoodKind(targetKind))out.push([target,e]);}}}}if(idx!==root&&isPrimaryBioKind(idxKind)){{for(const e of rootDownstreamEdges(root)){{const target=connectedTarget(e,root);out.push([target,cloneVirtualEdge(idx,e,target)]);}}}}return out}}
function local(start){{if(start<0)return{{nodes:new Set(),edges:[]}};const keep=new Set([start]),localEdges=[],edgeSeen=new Set();let frontier=new Set([start]);for(let d=0;d<degree();d++){{const next=new Set();for(const idx of frontier){{for(const pair of biologicalNeighbors(idx,start)){{const target=pair[0],e=pair[1];const edgeKey=e.s+'|'+e.t+'|'+e.r+'|'+(e.virtual?'v':'r');if(!edgeSeen.has(edgeKey)){{edgeSeen.add(edgeKey);localEdges.push(e)}}if(!keep.has(target)){{keep.add(target);next.add(target)}}}}}}frontier=next;if(!frontier.size)break}}return{{nodes:keep,edges:localEdges}}}}
function activeEdges(){{return showAll?edges.filter(edgePass):nb.edges}}
function draw(){{ctx.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);ctx.clearRect(0,0,innerWidth,innerHeight-72);ctx.fillStyle='#f8fafc';ctx.fillRect(0,0,innerWidth,innerHeight-72);const drawEdges=activeEdges();for(const e of drawEdges){{if(!visible(e.s)||!visible(e.t))continue;const a=nodes[e.s],b=nodes[e.t],ax=sx(a.x),ay=sy(a.y),bx=sx(b.x),by=sy(b.y);if((ax<-60&&bx<-60)||(ay<-60&&by<-60)||(ax>innerWidth+60&&bx>innerWidth+60)||(ay>innerHeight+60&&by>innerHeight+60))continue;const hi=selected>=0&&nb.nodes.has(e.s)&&nb.nodes.has(e.t);const ew=w(e);ctx.globalAlpha=hi?1:(showAll?.035:.62);ctx.strokeStyle=raw.edgeColors[e.r]||'#94a3b8';ctx.lineWidth=hi?Math.min(4,1+Math.log1p(ew)):Math.min(1.4,.35+Math.log1p(ew)/8);ctx.setLineDash(e.r.includes('negative')?[5,4]:[]);ctx.beginPath();ctx.moveTo(ax,ay);ctx.lineTo(bx,by);ctx.stroke()}}ctx.setLineDash([]);for(let i=0;i<nodes.length;i++){{if(!visible(i))continue;const n=nodes[i],x=sx(n.x),y=sy(n.y);if(x<-20||y<-20||x>innerWidth+20||y>innerHeight+20)continue;let dim=false;if(selected>=0)dim=!nb.nodes.has(i);else if(thresholdSlider.value>0)dim=!any.has(i);ctx.globalAlpha=dim?.055:.88;ctx.fillStyle=n.c;ctx.beginPath();ctx.arc(x,y,Math.max(.7,radius(n)*Math.sqrt(scale*14)),0,Math.PI*2);ctx.fill()}}ctx.globalAlpha=1;if(selected>=0){{const n=nodes[selected];ctx.strokeStyle='#020617';ctx.lineWidth=2.4;ctx.beginPath();ctx.arc(sx(n.x),sy(n.y),6.5,0,Math.PI*2);ctx.stroke();ctx.fillStyle='#0f172a';ctx.font='13px system-ui';ctx.fillText(n.l.length>48?n.l.slice(0,45)+'...':n.l,sx(n.x)+10,sy(n.y)+4)}}if(hover>=0&&hover!==selected){{const n=nodes[hover];ctx.strokeStyle='#334155';ctx.lineWidth=1.8;ctx.beginPath();ctx.arc(sx(n.x),sy(n.y),5,0,Math.PI*2);ctx.stroke()}}document.getElementById('status').textContent=nodes.length.toLocaleString()+' nodes, '+activeEdges().length.toLocaleString()+' visible retained edges'}}
function nearest(cx,cy){{const x=cx,y=cy-72;let best=-1,bestD=18*18,cands=selected>=0?nb.nodes:null;for(let i=0;i<nodes.length;i++){{if(!visible(i))continue;if(cands&&!cands.has(i))continue;const dx=sx(nodes[i].x)-x,dy=sy(nodes[i].y)-y,d=dx*dx+dy*dy;if(d<bestD){{best=i;bestD=d}}}}return best}}
function select(i){{selected=i;nb=local(i);const n=nodes[i],direct=(any.get(i)||[]).length;const top=nb.edges.slice().sort((a,b)=>w(b)-w(a)).slice(0,8).map(e=>'<br>'+e.r+': '+w(e).toFixed(4)).join('');document.getElementById('details').innerHTML='<b>'+n.l+'</b><br><span class="muted">'+n.t+' · '+n.k+'</span><br>'+direct.toLocaleString()+' retained direct edges<br>'+nb.nodes.size.toLocaleString()+' retained-neighborhood nodes, '+nb.edges.length.toLocaleString()+' edges'+top;draw()}}
function refreshThreshold(){{const t=thresholdObj();document.getElementById('thresholdReadout').textContent='q='+t.quantile+' · threshold='+t.threshold.toFixed(5);rebuildAdj();if(selected>=0)nb=local(selected);draw()}}
function tip(i,e){{if(i<0){{tooltip.style.display='none';return}}const n=nodes[i];tooltip.innerHTML='<b>'+n.l+'</b><br>'+n.t;tooltip.style.left=Math.min(e.clientX+12,innerWidth-340)+'px';tooltip.style.top=Math.min(e.clientY+12,innerHeight-80)+'px';tooltip.style.display='block'}}
canvas.addEventListener('mousedown',e=>{{last={{x:e.clientX,y:e.clientY}};const n=nearest(e.clientX,e.clientY);if(n>=0)select(n);else drag=true}});
canvas.addEventListener('mousemove',e=>{{if(drag&&last){{tx+=e.clientX-last.x;ty+=e.clientY-last.y;last={{x:e.clientX,y:e.clientY}};draw();return}}const n=nearest(e.clientX,e.clientY);if(n!==hover){{hover=n;draw()}}tip(n,e)}});
addEventListener('mouseup',()=>{{drag=false;last=null}});canvas.addEventListener('mouseleave',()=>{{hover=-1;tip(-1,{{}});draw()}});
canvas.addEventListener('wheel',e=>{{e.preventDefault();const old=scale;scale*=e.deltaY<0?1.14:.88;scale=Math.max(.004,Math.min(3,scale));const mx=e.clientX,my=e.clientY-72;tx=mx-(mx-tx)*(scale/old);ty=my-(my-ty)*(scale/old);draw()}},{{passive:false}});
document.getElementById('allEdges').addEventListener('change',e=>{{showAll=e.target.checked;draw()}});document.getElementById('degree').addEventListener('change',()=>{{if(selected>=0)select(selected);else draw()}});metricSelect.addEventListener('change',refreshThreshold);thresholdSlider.addEventListener('input',refreshThreshold);
document.getElementById('reset').addEventListener('click',()=>{{selected=-1;hover=-1;nb={{nodes:new Set(),edges:[]}};scale=.07;tx=innerWidth/2;ty=(innerHeight-72)/2;document.getElementById('details').textContent='Search or click a node.';draw()}});
function findNode(){{const q=document.getElementById('search').value.trim().toLowerCase();if(!q)return;const i=nodes.findIndex((n,idx)=>visible(idx)&&(n.l.toLowerCase().includes(q)||n.k.toLowerCase().includes(q)));if(i>=0){{tx=innerWidth/2-nodes[i].x*scale;ty=(innerHeight-72)/2-nodes[i].y*scale;select(i)}}}}
document.getElementById('find').addEventListener('click',findNode);document.getElementById('search').addEventListener('keydown',e=>{{if(e.key==='Enter')findNode()}});
const legend=document.getElementById('legend');Object.entries(raw.nodeColors).forEach(([kind,color])=>{{const item=document.createElement('div');item.className='legend-item';item.innerHTML='<span class="dot" style="background:'+color+'"></span>'+kind;item.onclick=()=>{{if(hidden.has(kind)){{hidden.delete(kind);item.classList.remove('off')}}else{{hidden.add(kind);item.classList.add('off')}}if(selected>=0&&!visible(selected))selected=-1;nb=selected>=0?local(selected):{{nodes:new Set(),edges:[]}};draw()}};legend.appendChild(item)}});
refreshThreshold();resize();addEventListener('resize',resize);
</script>
</body>
</html>
"""


def build_threshold_weighted_mega_app(scenario="denovo"):
    OUT.mkdir(parents=True, exist_ok=True)
    nodes = _full_mega_plus_scenario_nodes(scenario)
    key_to_index = {node["key"]: idx for idx, node in enumerate(nodes)}

    edges, relations = _build_threshold_app_edges(scenario, key_to_index)
    threshold_options = {}
    for metric in METRICS:
        options = pd.read_csv(KG_ENHANCE / scenario / metric / f"kg_threshold_suggestions_{metric}.csv")
        threshold_options[metric] = [
            {"quantile": float(row["quantile"]), "threshold": float(row["threshold"])}
            for _, row in options.iterrows()
        ]
    stem = f"{scenario}_hpp_kg_weighted_threshold_app"
    data_path = OUT / f"{stem}_data.js"
    html_path = OUT / f"{stem}.html"
    _write_threshold_app_data_js(data_path, nodes, edges, relations, threshold_options)
    html_path.write_text(_threshold_mega_app_html(data_path.name))
    summary = {
        "html": str(html_path),
        "data": str(data_path),
        "scenario": scenario,
        "nodes": len(nodes),
        "edges": len(edges),
        "metrics": METRICS,
        "threshold_options": threshold_options,
        "node_kind_counts": pd.Series([node["kind"] for node in nodes]).value_counts().to_dict(),
    }
    (OUT / f"{stem}_summary.json").write_text(json.dumps(summary, indent=2))
    return summary

def build_weighted_mega_flexible_visualization(
    scenario="denovo", metric="idf_entropy_cross_entropy"
):
    OUT.mkdir(parents=True, exist_ok=True)
    nodes, edges, relations, threshold, quantile = _build_weighted_mega_data(scenario, metric)
    stem = f"{scenario}_hpp_kg_weighted_{metric}_mega_flexible"
    data_path = OUT / f"{stem}_data.js"
    html_path = OUT / f"{stem}.html"
    _write_weighted_mega_data_js(data_path, nodes, edges, relations, metric, threshold, quantile)
    html_path.write_text(_weighted_mega_html(data_path.name))
    summary = {
        "html": str(html_path),
        "data": str(data_path),
        "scenario": scenario,
        "metric": metric,
        "threshold": threshold,
        "threshold_quantile": quantile,
        "nodes": len(nodes),
        "retained_edges": len(edges),
        "node_kind_counts": pd.Series([node["kind"] for node in nodes]).value_counts().to_dict(),
        "relation_count": len(relations),
        "relations": relations,
    }
    (OUT / f"{stem}_summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def build_kg_enhance_visualizations():
    selected_foods = _select_foods()
    payload = {
        "foods": selected_foods,
        "rows": _load_signature_rows(selected_foods),
        "thresholds": _load_threshold_rows(),
    }
    signature_explorer = _write_html(payload)
    summary = {
        "signature_explorer": str(signature_explorer),
        "threshold_explorer": str(KG_ENHANCE / "kg_weighting_threshold_explorer.html"),
        "threshold_weighted_mega_app": str(build_threshold_weighted_mega_app()["html"]),
        "metric_select_weighted_mega_flexible": str(
            build_metric_select_weighted_mega_visualization()["html"]
        ),
        "weighted_mega_flexible": str(
            build_weighted_mega_flexible_visualization()["html"]
        ),
        "selected_foods": selected_foods,
        "rows_embedded": len(payload["rows"]),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "kg_enhance_visualization_summary.json").write_text(json.dumps(summary, indent=2))
    return summary
