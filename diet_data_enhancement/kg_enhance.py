import json
import math
import re
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
ENHANCED = ROOT / "outputs" / "enhanced_hpp"
OUT = ROOT / "outputs" / "KG_enhance"

SCENARIOS = {
    "denovo": ENHANCED / "1.denovo",
    "nutrimatch_based": ENHANCED / "2.nutrimatch_based",
}

METRICS = {
    "idf": "IDF only: global inverse-food-frequency specificity.",
    "idf_entropy": "IDF multiplied by category specificity from normalized entropy.",
    "idf_entropy_cross_entropy": "IDF multiplied by category specificity and KL divergence against the background category distribution.",
}

SIGNATURE_RELATIONS = {
    "chemical": ["linked_to_foodb_chemical_class", "linked_to_foodb_chemical_superclass"],
    "metabolomics": ["linked_to_hmdb_biospecimen"],
    "disease": ["linked_to_hmdb_disease_annotation"],
    "pathway": ["linked_to_hmdb_pathway_annotation"],
}


def _read_scenario_kg(scenario_name):
    scenario_dir = SCENARIOS[scenario_name]
    nodes = pd.read_csv(scenario_dir / "kg" / "hpp_scenario_kg_nodes.csv", low_memory=False)
    edges = pd.read_csv(scenario_dir / "kg" / "hpp_scenario_kg_edges.csv", low_memory=False)
    nodes["key"] = nodes["key"].astype(str)
    edges["source"] = edges["source"].astype(str)
    edges["target"] = edges["target"].astype(str)
    return nodes, edges


def _safe_token(value, limit=140):
    value = re.sub(r"[^A-Za-z0-9]+", "_", str(value).strip().lower())
    value = re.sub(r"_+", "_", value).strip("_")
    return (value or "unknown")[:limit]


def _food_category_table(nodes):
    foods = nodes.loc[nodes["kind"].eq("hpp_food"), ["key", "id", "label", "category"]].copy()
    foods = foods.rename(columns={"key": "source", "id": "hpp_food_id", "label": "hpp_food_name"})
    foods["category"] = foods["category"].fillna("unknown").astype(str)
    foods["hpp_food_id"] = foods["hpp_food_id"].astype(str)
    return foods


def _target_table(nodes):
    return nodes[["key", "kind", "label"]].rename(
        columns={"key": "target", "kind": "target_kind", "label": "target_label"}
    )


def _background_distribution(foods):
    counts = foods["category"].value_counts()
    total = counts.sum()
    return (counts / total).to_dict()


def _compute_node_information(nodes, edges):
    foods = _food_category_table(nodes)
    targets = _target_table(nodes)
    background = _background_distribution(foods)
    categories = sorted(background)
    n_foods = foods["source"].nunique()
    max_entropy = math.log(max(len(categories), 1))

    hpp_edges = edges.loc[edges["source"].isin(set(foods["source"]))].copy()
    hpp_edges = hpp_edges[["source", "target", "relation"]].drop_duplicates()
    hpp_edges = hpp_edges.merge(foods[["source", "category"]], on="source", how="left")
    hpp_edges["category"] = hpp_edges["category"].fillna("unknown")

    rows = []
    grouped = hpp_edges.groupby(["relation", "target"], dropna=False)
    for (relation, target), group in grouped:
        node_prevalence = int(group["source"].nunique())
        idf = math.log((n_foods + 1) / (node_prevalence + 1)) + 1

        category_counts = group.groupby("category")["source"].nunique()
        total_for_node = float(category_counts.sum())
        entropy = 0.0
        cross_entropy = 0.0
        kl_divergence = 0.0
        for category in categories:
            p_node = float(category_counts.get(category, 0.0)) / total_for_node if total_for_node else 0.0
            p_bg = float(background.get(category, 0.0))
            if p_node > 0:
                entropy -= p_node * math.log(p_node)
                cross_entropy -= p_node * math.log(max(p_bg, 1e-12))
                kl_divergence += p_node * math.log(p_node / max(p_bg, 1e-12))

        normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0.0
        category_specificity = max(0.0, 1.0 - normalized_entropy)
        idf_entropy = idf * category_specificity
        idf_entropy_cross_entropy = idf * category_specificity * math.log1p(kl_divergence)

        rows.append(
            {
                "relation": relation,
                "target": target,
                "node_prevalence_foods": node_prevalence,
                "total_hpp_foods": n_foods,
                "idf": idf,
                "entropy": entropy,
                "normalized_entropy": normalized_entropy,
                "category_specificity": category_specificity,
                "cross_entropy_vs_background": cross_entropy,
                "kl_divergence_vs_background": kl_divergence,
                "idf_entropy": idf_entropy,
                "idf_entropy_cross_entropy": idf_entropy_cross_entropy,
            }
        )

    info = pd.DataFrame(rows).merge(targets, on="target", how="left")
    info["target_kind"] = info["target_kind"].fillna("unknown")
    info["target_label"] = info["target_label"].fillna(info["target"].astype(str))
    return info


def _weighted_edges(edges, info, metric):
    cols = [
        "relation",
        "target",
        "target_kind",
        "target_label",
        "node_prevalence_foods",
        "total_hpp_foods",
        "idf",
        "normalized_entropy",
        "category_specificity",
        "cross_entropy_vs_background",
        "kl_divergence_vs_background",
        metric,
    ]
    cols = list(dict.fromkeys(cols))
    weighted = edges.merge(info[cols], on=["relation", "target"], how="left")
    base = pd.to_numeric(weighted["value"], errors="coerce")
    weighted["edge_base_value"] = base.where(base.notna(), 1.0)
    weighted["node_information_weight"] = pd.to_numeric(weighted[metric], errors="coerce").fillna(0.0)
    weighted["weighted_value"] = weighted["edge_base_value"] * weighted["node_information_weight"]
    weighted["metric"] = metric
    weighted["target_kind"] = weighted["target_kind"].fillna("unknown")
    weighted["target_label"] = weighted["target_label"].fillna(weighted["target"].astype(str))
    return weighted


def _threshold_summary(weighted):
    quantiles = [0.50, 0.75, 0.90, 0.95, 0.975, 0.99]
    source_is_food = weighted["source"].astype(str).str.startswith("hpp_food:")
    rows = []
    for q in quantiles:
        threshold = float(weighted["weighted_value"].quantile(q))
        kept = weighted.loc[weighted["weighted_value"].ge(threshold)]
        kept_food = kept.loc[source_is_food.loc[kept.index]]
        per_food = kept_food.groupby("source").size()
        rows.append(
            {
                "quantile": q,
                "threshold": threshold,
                "edges_retained": int(len(kept)),
                "retained_fraction": float(len(kept) / len(weighted)) if len(weighted) else 0.0,
                "foods_with_retained_edges": int(per_food.shape[0]),
                "median_edges_per_food": float(per_food.median()) if not per_food.empty else 0.0,
                "p10_edges_per_food": float(per_food.quantile(0.10)) if not per_food.empty else 0.0,
            }
        )
    summary = pd.DataFrame(rows)
    viable = summary.loc[
        summary["foods_with_retained_edges"].ge(0.95 * weighted.loc[source_is_food, "source"].nunique())
        & summary["median_edges_per_food"].ge(20)
    ]
    if viable.empty:
        summary["recommended"] = summary["quantile"].eq(0.90)
    else:
        chosen = viable.sort_values("quantile", ascending=False).iloc[0]["quantile"]
        summary["recommended"] = summary["quantile"].eq(chosen)
    return summary


def _top_signatures(weighted, signature_type, relations, top_n=25):
    food_edges = weighted.loc[
        weighted["source"].astype(str).str.startswith("hpp_food:")
        & weighted["relation"].isin(relations)
    ].copy()
    if food_edges.empty:
        return pd.DataFrame()
    food_edges["hpp_food_id"] = food_edges["source"].str.replace("hpp_food:", "", regex=False)
    food_edges["feature_label"] = food_edges["target_label"].astype(str)
    food_edges = food_edges.sort_values(["hpp_food_id", "weighted_value"], ascending=[True, False])
    top = food_edges.groupby("hpp_food_id").head(top_n)
    return top[
        [
            "hpp_food_id",
            "relation",
            "target",
            "target_kind",
            "feature_label",
            "edge_base_value",
            "node_information_weight",
            "weighted_value",
            "node_prevalence_foods",
            "normalized_entropy",
            "category_specificity",
            "kl_divergence_vs_background",
        ]
    ].assign(signature_type=signature_type)


def _food_signature_matrix(weighted, max_features=300):
    food_edges = weighted.loc[weighted["source"].astype(str).str.startswith("hpp_food:")].copy()
    food_edges["hpp_food_id"] = food_edges["source"].str.replace("hpp_food:", "", regex=False)
    food_edges["feature"] = (
        "kgw__"
        + food_edges["relation"].astype(str).map(_safe_token)
        + "__"
        + food_edges["target_kind"].astype(str).map(_safe_token)
        + "__"
        + food_edges["target_label"].astype(str).map(_safe_token)
    )
    top_features = (
        food_edges.groupby("feature")["weighted_value"]
        .sum()
        .sort_values(ascending=False)
        .head(max_features)
        .index
    )
    use = food_edges.loc[food_edges["feature"].isin(set(top_features))]
    matrix = use.pivot_table(
        index="hpp_food_id",
        columns="feature",
        values="weighted_value",
        aggfunc="sum",
        fill_value=0,
    ).reset_index()
    matrix.columns.name = None
    return matrix


def _build_threshold_visualization(outputs):
    rows = []
    samples = []
    for item in outputs:
        threshold = pd.read_csv(item["thresholds"])
        weighted_sample = pd.read_csv(item["weighted_edges"], compression="gzip", nrows=50000)
        for _, row in threshold.iterrows():
            rows.append(
                {
                    "scenario": item["scenario"],
                    "metric": item["metric"],
                    "quantile": row["quantile"],
                    "threshold": row["threshold"],
                    "edges_retained": row["edges_retained"],
                    "retained_fraction": row["retained_fraction"],
                    "median_edges_per_food": row["median_edges_per_food"],
                    "recommended": bool(row["recommended"]),
                }
            )
        sample_edges = weighted_sample.nlargest(1200, "weighted_value")[
            ["source", "target", "relation", "target_kind", "target_label", "weighted_value"]
        ].to_dict(orient="records")
        samples.append({"scenario": item["scenario"], "metric": item["metric"], "edges": sample_edges})
    payload = {
        "thresholds": rows,
        "samples": samples,
    }
    out = OUT / "kg_weighting_threshold_explorer.html"
    html = """<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<title>KG Weighting Threshold Explorer</title>
<style>
body{font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:0;background:#f7f7f4;color:#1f2933}
header{padding:14px 18px;border-bottom:1px solid #ddd;background:#fff}
.controls{display:flex;gap:12px;align-items:center;flex-wrap:wrap;padding:12px 18px;background:#fff;border-bottom:1px solid #ddd}
select,input{font:inherit;padding:6px 8px}
#wrap{display:grid;grid-template-columns:1fr 360px;gap:0;height:calc(100vh - 118px)}
canvas{width:100%;height:100%;background:#fbfbf8}
aside{border-left:1px solid #ddd;background:#fff;padding:14px;overflow:auto}
.stat{margin:8px 0;padding:8px;border:1px solid #e2e2dc;background:#fafafa}
.muted{color:#667085;font-size:13px}
</style>
</head>
<body>
<header><b>KG weighting threshold explorer</b><div class="muted">Shows top weighted edges for each metric. Use threshold quantile to see how aggressive edge filtering behaves.</div></header>
<div class="controls">
<label>Scenario <select id="scenario"></select></label>
<label>Metric <select id="metric"></select></label>
<label>Threshold quantile <input id="q" type="range" min="0" max="5" value="3" step="1"></label>
<span id="qLabel"></span>
</div>
<div id="wrap"><canvas id="canvas"></canvas><aside><h3>Threshold summary</h3><div id="stats"></div><h3>Edge types</h3><div id="relations"></div></aside></div>
<script>
const DATA = __PAYLOAD__;
const qs=[0.5,0.75,0.9,0.95,0.975,0.99];
const scenarioSel=document.getElementById('scenario'), metricSel=document.getElementById('metric'), q=document.getElementById('q');
const canvas=document.getElementById('canvas'), ctx=canvas.getContext('2d');
const colors={has_nutrient_amount_per_100g:'#3974b7',linked_to_foodb_chemical_class:'#7a52aa',linked_to_foodb_chemical_superclass:'#9b6ec8',linked_to_hmdb_biospecimen:'#148f77',linked_to_hmdb_disease_annotation:'#c44949',linked_to_hmdb_pathway_annotation:'#d18420',has_nova_group:'#607d3b',has_nutriscore_grade:'#8a8f38',inherits_product_processing_match:'#5f6f86',has_canonical_helper:'#999'};
function uniq(a){return [...new Set(a)]}
uniq(DATA.thresholds.map(d=>d.scenario)).forEach(v=>scenarioSel.add(new Option(v,v)));
uniq(DATA.thresholds.map(d=>d.metric)).forEach(v=>metricSel.add(new Option(v,v)));
metricSel.value='idf_entropy_cross_entropy';
function current(){
  const s=scenarioSel.value,m=metricSel.value,quant=qs[+q.value];
  const t=DATA.thresholds.find(d=>d.scenario===s&&d.metric===m&&Math.abs(d.quantile-quant)<1e-9);
  const sample=DATA.samples.find(d=>d.scenario===s&&d.metric===m);
  return {s,m,quant,t,edges:(sample?sample.edges:[]).filter(e=>e.weighted_value>=t.threshold)};
}
function draw(){
  const d=current(); document.getElementById('qLabel').textContent=d.quant;
  const rect=canvas.getBoundingClientRect(); canvas.width=rect.width*devicePixelRatio; canvas.height=rect.height*devicePixelRatio; ctx.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);
  ctx.clearRect(0,0,rect.width,rect.height);
  const nodes=new Map(); d.edges.forEach(e=>{if(!nodes.has(e.source))nodes.set(e.source,{id:e.source,type:'food'}); if(!nodes.has(e.target))nodes.set(e.target,{id:e.target,type:e.target_kind,label:e.target_label});});
  const arr=[...nodes.values()], foods=arr.filter(n=>n.type==='food'), other=arr.filter(n=>n.type!=='food');
  foods.forEach((n,i)=>{n.x=120+(i%20)*18;n.y=80+Math.floor(i/20)*18});
  other.forEach((n,i)=>{const a=i/Math.max(1,other.length)*Math.PI*2; const r=150+80*((i%5)/5); n.x=rect.width/2+Math.cos(a)*r; n.y=rect.height/2+Math.sin(a)*r});
  d.edges.forEach(e=>{const a=nodes.get(e.source),b=nodes.get(e.target); if(!a||!b)return; ctx.strokeStyle=colors[e.relation]||'#999'; ctx.globalAlpha=.18; ctx.lineWidth=Math.max(.4,Math.min(4,Math.log1p(e.weighted_value))); ctx.beginPath(); ctx.moveTo(a.x,a.y); ctx.lineTo(b.x,b.y); ctx.stroke();});
  ctx.globalAlpha=1; arr.forEach(n=>{ctx.fillStyle=n.type==='food'?'#222':(n.type==='disease'?'#c44949':n.type==='pathway'?'#d18420':n.type.includes('chemical')?'#7a52aa':'#148f77'); ctx.beginPath(); ctx.arc(n.x,n.y,n.type==='food'?2.2:3.2,0,Math.PI*2); ctx.fill();});
  document.getElementById('stats').innerHTML=`<div class="stat">threshold: <b>${d.t.threshold.toFixed(4)}</b></div><div class="stat">edges retained: <b>${d.t.edges_retained.toLocaleString()}</b> (${(100*d.t.retained_fraction).toFixed(1)}%)</div><div class="stat">median edges/food: <b>${d.t.median_edges_per_food.toFixed(1)}</b></div><div class="stat">recommended: <b>${d.t.recommended?'yes':'no'}</b></div>`;
  const rel=Object.entries(d.edges.reduce((o,e)=>(o[e.relation]=(o[e.relation]||0)+1,o),{})).sort((a,b)=>b[1]-a[1]);
  document.getElementById('relations').innerHTML=rel.map(([k,v])=>`<div class="stat"><span style="color:${colors[k]||'#555'}">■</span> ${k}<br><b>${v}</b> sample edges</div>`).join('');
}
[scenarioSel,metricSel,q].forEach(el=>el.addEventListener('input',draw));
addEventListener('resize',draw); draw();
</script>
</body>
</html>"""
    out.write_text(html.replace("__PAYLOAD__", json.dumps(payload)))
    return out


def build_kg_enhancement():
    OUT.mkdir(parents=True, exist_ok=True)
    all_outputs = []
    for scenario_name in SCENARIOS:
        scenario_out = OUT / scenario_name
        scenario_out.mkdir(parents=True, exist_ok=True)
        nodes, edges = _read_scenario_kg(scenario_name)
        info = _compute_node_information(nodes, edges)
        info_path = scenario_out / "kg_node_information_scores.csv"
        info.to_csv(info_path, index=False)

        for metric in METRICS:
            metric_out = scenario_out / metric
            metric_out.mkdir(parents=True, exist_ok=True)
            weighted = _weighted_edges(edges, info, metric)
            weighted_path = metric_out / f"kg_weighted_edges_{metric}.csv.gz"
            threshold_path = metric_out / f"kg_threshold_suggestions_{metric}.csv"
            matrix_path = metric_out / f"kg_food_weighted_signature_matrix_{metric}.csv"
            summary_path = metric_out / f"kg_weighting_summary_{metric}.json"
            weighted.to_csv(weighted_path, index=False, compression="gzip")
            thresholds = _threshold_summary(weighted)
            thresholds.to_csv(threshold_path, index=False)
            matrix = _food_signature_matrix(weighted)
            matrix.to_csv(matrix_path, index=False)

            signature_paths = {}
            for signature_type, relations in SIGNATURE_RELATIONS.items():
                sig = _top_signatures(weighted, signature_type, relations)
                path = metric_out / f"kg_food_top_weighted_{signature_type}_{metric}.csv"
                sig.to_csv(path, index=False)
                signature_paths[signature_type] = str(path)

            summary = {
                "scenario": scenario_name,
                "metric": metric,
                "metric_description": METRICS[metric],
                "node_information_scores": str(info_path),
                "weighted_edges": str(weighted_path),
                "threshold_suggestions": str(threshold_path),
                "weighted_signature_matrix": str(matrix_path),
                "top_signature_files": signature_paths,
                "edges": int(weighted.shape[0]),
                "nodes_scored": int(info.shape[0]),
                "recommended_threshold": thresholds.loc[thresholds["recommended"]].to_dict(orient="records"),
            }
            summary_path.write_text(json.dumps(summary, indent=2))
            all_outputs.append(
                {
                    "scenario": scenario_name,
                    "metric": metric,
                    "weighted_edges": str(weighted_path),
                    "thresholds": str(threshold_path),
                    "summary": str(summary_path),
                    "signature_matrix": str(matrix_path),
                }
            )

    viz = _build_threshold_visualization(all_outputs)
    project_summary = {
        "metrics": METRICS,
        "scenarios": list(SCENARIOS),
        "outputs": all_outputs,
        "threshold_explorer": str(viz),
    }
    (OUT / "kg_enhancement_summary.json").write_text(json.dumps(project_summary, indent=2))
    pd.DataFrame(all_outputs).to_csv(OUT / "kg_enhancement_outputs.csv", index=False)
    return project_summary


def build_selected_kg_enhancement(scenario_name, metric):
    if scenario_name not in SCENARIOS:
        raise ValueError(f"Unknown scenario {scenario_name!r}. Available: {sorted(SCENARIOS)}")
    if metric not in METRICS:
        raise ValueError(f"Unknown metric {metric!r}. Available: {sorted(METRICS)}")
    OUT.mkdir(parents=True, exist_ok=True)
    scenario_out = OUT / scenario_name
    scenario_out.mkdir(parents=True, exist_ok=True)
    nodes, edges = _read_scenario_kg(scenario_name)
    info = _compute_node_information(nodes, edges)
    info_path = scenario_out / "kg_node_information_scores.csv"
    info.to_csv(info_path, index=False)

    metric_out = scenario_out / metric
    metric_out.mkdir(parents=True, exist_ok=True)
    weighted = _weighted_edges(edges, info, metric)
    weighted_path = metric_out / f"kg_weighted_edges_{metric}.csv.gz"
    threshold_path = metric_out / f"kg_threshold_suggestions_{metric}.csv"
    matrix_path = metric_out / f"kg_food_weighted_signature_matrix_{metric}.csv"
    summary_path = metric_out / f"kg_weighting_summary_{metric}.json"

    weighted.to_csv(weighted_path, index=False, compression="gzip")
    thresholds = _threshold_summary(weighted)
    thresholds.to_csv(threshold_path, index=False)
    matrix = _food_signature_matrix(weighted)
    matrix.to_csv(matrix_path, index=False)

    signature_paths = {}
    for signature_type, relations in SIGNATURE_RELATIONS.items():
        sig = _top_signatures(weighted, signature_type, relations)
        path = metric_out / f"kg_food_top_weighted_{signature_type}_{metric}.csv"
        sig.to_csv(path, index=False)
        signature_paths[signature_type] = str(path)

    summary = {
        "scenario": scenario_name,
        "metric": metric,
        "metric_description": METRICS[metric],
        "node_information_scores": str(info_path),
        "weighted_edges": str(weighted_path),
        "threshold_suggestions": str(threshold_path),
        "weighted_signature_matrix": str(matrix_path),
        "top_signature_files": signature_paths,
        "edges": int(weighted.shape[0]),
        "nodes_scored": int(info.shape[0]),
        "recommended_threshold": thresholds.loc[thresholds["recommended"]].to_dict(orient="records"),
    }
    summary_path.write_text(json.dumps(summary, indent=2))
    return summary


def build_kg_enhancement_interactive():
    print("Available scenarios:")
    for idx, scenario_name in enumerate(SCENARIOS, start=1):
        print(f"{idx}. {scenario_name}")
    scenario_choice = input("Choose scenario number: ").strip()
    scenario_names = list(SCENARIOS)
    scenario_name = scenario_names[int(scenario_choice) - 1]

    print("Available KG weighting metrics:")
    for idx, (metric, description) in enumerate(METRICS.items(), start=1):
        print(f"{idx}. {metric}: {description}")
    metric_choice = input("Choose metric number: ").strip()
    metric = list(METRICS)[int(metric_choice) - 1]
    return build_selected_kg_enhancement(scenario_name, metric)
