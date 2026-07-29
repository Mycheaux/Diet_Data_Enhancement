import json
import math
from collections import defaultdict
from pathlib import Path

import pandas as pd

from .sources import ROOT


OUT = ROOT / "outputs/visualizations"
FINAL_KG = ROOT / "outputs/kg"
HMDB_INDEX = ROOT / "outputs/layered/layer4_hmdb_metabolite_index.csv"

NODE_COLORS = {
    "hpp_food": "#2563eb",
    "canonical_food": "#0f766e",
    "source_food": "#64748b",
    "foodatlas_food": "#2aa198",
    "foodb_food": "#16a34a",
    "nutrient": "#f59e0b",
    "foodatlas_chemical": "#d69e2e",
    "foodb_compound": "#ca8a04",
    "hmdb_metabolite": "#7c3aed",
    "hmdb_biospecimen": "#0891b2",
    "disease": "#ef4444",
    "pathway": "#8b5cf6",
    "human_correction": "#64748b",
}

EDGE_COLORS = {
    "belongs_to_canonical": "#64748b",
    "mapped_to_foodatlas": "#20a4a9",
    "mapped_to_public_fcdb": "#64748b",
    "mapped_to_foodb": "#16a34a",
    "has_nutrient_value": "#f59e0b",
    "foodatlas_contains": "#d69e2e",
    "foodb_contains_compound": "#ca8a04",
    "linked_to_hmdb_metabolite": "#7c3aed",
    "hmdb_observed_in_biospecimen": "#0891b2",
    "foodatlas_positively_correlates_with": "#dc2626",
    "foodatlas_negatively_correlates_with": "#4f46e5",
    "hmdb_metabolite_disease_annotation": "#ef4444",
    "hmdb_metabolite_pathway_annotation": "#8b5cf6",
    "foodatlas_is_a": "#94a3b8",
}

CENTERS = {
    "hpp_food": (-2200, -240, 18),
    "canonical_food": (-1380, 260, 22),
    "source_food": (-1780, 1120, 28),
    "foodatlas_food": (-560, -1120, 16),
    "foodb_food": (-260, 1040, 24),
    "nutrient": (-820, 440, 22),
    "foodatlas_chemical": (620, -800, 5.8),
    "foodb_compound": (740, 1000, 9.0),
    "hmdb_metabolite": (1880, 280, 8.2),
    "hmdb_biospecimen": (2520, 880, 36),
    "disease": (3100, -540, 10.5),
    "pathway": (3260, 1120, 7.0),
    "human_correction": (-980, -300, 28),
}


def _split_pipe(value):
    return [item.strip() for item in str(value or "").split("|") if item.strip()]


def _norm_kind(kind):
    return "disease" if kind == "foodatlas_disease" else kind


def _disease_key(label):
    return "disease:" + str(label).strip().lower().replace(" ", "_")


def _pathway_key(label):
    return "pathway:" + str(label).strip().lower().replace(" ", "_")


def _layout_node(kind, offset):
    cx, cy, spacing = CENTERS.get(kind, (0, 0, 24))
    golden = math.pi * (3 - math.sqrt(5))
    radius = spacing * math.sqrt(offset + 1)
    angle = offset * golden
    return round(cx + math.cos(angle) * radius, 2), round(cy + math.sin(angle) * radius, 2)


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


def _build_nodes():
    nodes_path = FINAL_KG / "final_food_kg_nodes.csv"
    final_nodes = pd.read_csv(nodes_path, dtype=str, usecols=["key", "kind", "label"]).fillna("")
    final_nodes["display_kind"] = final_nodes["kind"].map(_norm_kind)
    final_nodes["display_key"] = final_nodes.apply(
        lambda row: _disease_key(row["label"]) if row["kind"] == "foodatlas_disease" else row["key"],
        axis=1,
    )

    rows = {}
    old_to_new = {}
    offsets = defaultdict(int)
    for _, row in final_nodes.iterrows():
        key = row["display_key"]
        old_to_new[row["key"]] = key
        if key in rows:
            continue
        kind = row["display_kind"]
        x, y = _layout_node(kind, offsets[kind])
        offsets[kind] += 1
        rows[key] = {
            "key": key,
            "label": row["label"] or key,
            "kind": kind,
            "x": x,
            "y": y,
        }

    if HMDB_INDEX.exists():
        hmdb = pd.read_csv(
            HMDB_INDEX,
            dtype=str,
            usecols=["hmdb_id", "hmdb_name", "disease_names", "pathway_names"],
        ).fillna("")
        for _, row in hmdb.drop_duplicates("hmdb_id").iterrows():
            key = f"hmdb_metabolite:{row['hmdb_id']}"
            if key not in rows:
                x, y = _layout_node("hmdb_metabolite", offsets["hmdb_metabolite"])
                offsets["hmdb_metabolite"] += 1
                rows[key] = {
                    "key": key,
                    "label": row["hmdb_name"] or row["hmdb_id"],
                    "kind": "hmdb_metabolite",
                    "x": x,
                    "y": y,
                }
            for disease in _split_pipe(row["disease_names"]):
                disease_key = _disease_key(disease)
                if disease_key not in rows:
                    x, y = _layout_node("disease", offsets["disease"])
                    offsets["disease"] += 1
                    rows[disease_key] = {
                        "key": disease_key,
                        "label": disease,
                        "kind": "disease",
                        "x": x,
                        "y": y,
                    }
            for pathway in _split_pipe(row["pathway_names"]):
                pathway_key = _pathway_key(pathway)
                if pathway_key not in rows:
                    x, y = _layout_node("pathway", offsets["pathway"])
                    offsets["pathway"] += 1
                    rows[pathway_key] = {
                        "key": pathway_key,
                        "label": pathway,
                        "kind": "pathway",
                        "x": x,
                        "y": y,
                    }

    ordered = list(rows.values())
    key_to_index = {row["key"]: idx for idx, row in enumerate(ordered)}
    return ordered, key_to_index, old_to_new


def _build_edges(key_to_index, old_to_new):
    edges_path = FINAL_KG / "final_food_kg_edges.csv"
    edge_rows = []
    relations_seen = set()
    usecols = ["source", "target", "relation"]
    for chunk in pd.read_csv(edges_path, dtype=str, usecols=usecols, chunksize=250000):
        chunk = chunk.fillna("")
        for _, row in chunk.iterrows():
            source = old_to_new.get(row["source"], row["source"])
            target = old_to_new.get(row["target"], row["target"])
            if source not in key_to_index or target not in key_to_index:
                continue
            relation = row["relation"]
            relations_seen.add(relation)
            edge_rows.append([key_to_index[source], key_to_index[target], relation])

    if HMDB_INDEX.exists():
        hmdb = pd.read_csv(
            HMDB_INDEX,
            dtype=str,
            usecols=["hmdb_id", "disease_names", "pathway_names"],
        ).fillna("")
        for _, row in hmdb.drop_duplicates("hmdb_id").iterrows():
            source = f"hmdb_metabolite:{row['hmdb_id']}"
            if source not in key_to_index:
                continue
            for disease in _split_pipe(row["disease_names"]):
                target = _disease_key(disease)
                if target in key_to_index:
                    relation = "hmdb_metabolite_disease_annotation"
                    relations_seen.add(relation)
                    edge_rows.append([key_to_index[source], key_to_index[target], relation])
            for pathway in _split_pipe(row["pathway_names"]):
                target = _pathway_key(pathway)
                if target in key_to_index:
                    relation = "hmdb_metabolite_pathway_annotation"
                    relations_seen.add(relation)
                    edge_rows.append([key_to_index[source], key_to_index[target], relation])

    return edge_rows, sorted(relations_seen)


def _write_data_js(path, nodes, edges, relations):
    kinds = sorted({node["kind"] for node in nodes})
    kind_index = {kind: idx for idx, kind in enumerate(kinds)}
    rel_index = {rel: idx for idx, rel in enumerate(relations)}
    compact_nodes = (
        [node["key"], node["label"], kind_index[node["kind"]], node["x"], node["y"]]
        for node in nodes
    )
    compact_edges = ([source, target, rel_index[relation]] for source, target, relation in edges)
    node_tmp = path.with_suffix(".nodes.tmp")
    edge_tmp = path.with_suffix(".edges.tmp")
    _write_json_array(node_tmp, compact_nodes)
    _write_json_array(edge_tmp, compact_edges)
    with path.open("w") as handle:
        handle.write("window.MEGA_KG_DATA={")
        handle.write("kinds:")
        handle.write(json.dumps(kinds, separators=(",", ":")))
        handle.write(",relations:")
        handle.write(json.dumps(relations, separators=(",", ":")))
        handle.write(",nodeColors:")
        handle.write(json.dumps(NODE_COLORS, separators=(",", ":")))
        handle.write(",edgeColors:")
        handle.write(json.dumps(EDGE_COLORS, separators=(",", ":")))
        handle.write(",nodes:")
        handle.write(node_tmp.read_text())
        handle.write(",edges:")
        handle.write(edge_tmp.read_text())
        handle.write("};\n")
    node_tmp.unlink(missing_ok=True)
    edge_tmp.unlink(missing_ok=True)


def _html():
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>De Novo HPP Mega Flexible KG</title>
<style>
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f8fafc;color:#0f172a;overflow:hidden}
header{height:66px;display:flex;align-items:center;gap:10px;padding:0 14px;background:#fff;border-bottom:1px solid #dbe4ee;box-sizing:border-box}
h1{margin:0;font-size:16px;font-weight:700;white-space:nowrap}
input,select,button{border:1px solid #cbd5e1;background:#fff;color:#0f172a;border-radius:6px;padding:7px 9px;font:inherit}
button{cursor:pointer}
#canvas{display:block;width:100vw;height:calc(100vh - 66px);background:#f8fafc}
#panel{position:fixed;right:14px;top:80px;width:350px;max-height:calc(100vh - 100px);overflow:auto;background:rgba(255,255,255,.96);border:1px solid #cbd5e1;border-radius:8px;padding:14px;box-shadow:0 14px 36px rgba(15,23,42,.16);box-sizing:border-box}
#tooltip{position:fixed;display:none;pointer-events:none;max-width:330px;background:rgba(15,23,42,.95);color:#fff;border-radius:6px;padding:7px 9px;font-size:12px;line-height:1.35;z-index:20}
.muted{color:#64748b;font-size:12px}.legend{display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:12px;margin-top:8px}.legend-item{cursor:pointer;user-select:none;padding:4px 5px;border-radius:5px}.legend-item:hover{background:#edf2f7}.legend-item.off{opacity:.35;text-decoration:line-through}.dot{display:inline-block;width:11px;height:11px;border-radius:50%;margin-right:6px;vertical-align:-1px}.row{margin-top:10px}
</style>
</head>
<body>
<header>
<h1>De Novo HPP Mega Flexible KG</h1>
<input id="search" placeholder="Search node label or key" size="30">
<button id="find">Find</button>
<label>degree <select id="degree"><option>1</option><option>2</option><option>3</option><option selected>4</option></select></label>
<label><input type="checkbox" id="allEdges"> all edges</label>
<button id="reset">Reset</button>
<span id="status" class="muted">Loading...</span>
</header>
<canvas id="canvas"></canvas>
<div id="tooltip"></div>
<aside id="panel">
<div class="muted">Mega graph: all full-KG nodes plus HMDB-index disease/pathway nodes. Edges are hidden by default for speed; click/search a node to show its local neighborhood.</div>
<div class="legend" id="legend"></div>
<div id="details" class="row">Search or click a node.</div>
</aside>
<script src="denovo_hpp_kg_mega_flexible_data.js"></script>
<script>
const raw=window.MEGA_KG_DATA;
const kinds=raw.kinds, rels=raw.relations;
const nodes=raw.nodes.map((n,i)=>({i,k:n[0],l:n[1],t:kinds[n[2]],x:n[3],y:n[4],c:raw.nodeColors[kinds[n[2]]]||'#94a3b8'}));
const edges=raw.edges.map(e=>({s:e[0],t:e[1],r:rels[e[2]],c:raw.edgeColors[rels[e[2]]]||'#94a3b8'}));
const canvas=document.getElementById('canvas'),ctx=canvas.getContext('2d'),tooltip=document.getElementById('tooltip');
const out=new Map(),any=new Map();
const stageByKind={hpp_food:0,canonical_food:1,source_food:1,foodatlas_food:1,foodb_food:1,nutrient:1,foodatlas_chemical:2,foodb_compound:2,hmdb_metabolite:3,hmdb_biospecimen:3,disease:4,pathway:4,human_correction:1};
for(const e of edges){if(!out.has(e.s))out.set(e.s,[]);if(!any.has(e.s))any.set(e.s,[]);if(!any.has(e.t))any.set(e.t,[]);out.get(e.s).push(e);any.get(e.s).push(e);any.get(e.t).push(e)}
let scale=.07,tx=innerWidth/2,ty=(innerHeight-66)/2,selected=-1,hover=-1,hidden=new Set(),showAll=false,drag=false,last=null,nb={nodes:new Set(),edges:[]};
function resize(){canvas.width=innerWidth*devicePixelRatio;canvas.height=(innerHeight-66)*devicePixelRatio;canvas.style.height=(innerHeight-66)+'px';draw()}
function sx(x){return x*scale+tx} function sy(y){return y*scale+ty}
function visible(i){return !hidden.has(nodes[i].t)}
function radius(n){if(n.t==='hpp_food')return 3.2;if(n.t==='canonical_food')return 2.9;if(n.t==='disease'||n.t==='pathway')return 1.7;if(n.t.includes('chemical')||n.t==='foodb_compound')return 1.15;return 1.5}
function degree(){return Number(document.getElementById('degree').value||4)}
function edgeForwardFrom(e,idx){if(e.s===idx)return e.t;if(e.t===idx){const a=stageByKind[nodes[e.t].t]??0,b=stageByKind[nodes[e.s].t]??0;if(b>=a)return e.s}return -1}
function local(start){if(start<0)return{nodes:new Set(),edges:[]};const keep=new Set([start]),localEdges=[];let frontier=new Set([start]);for(let d=0;d<degree();d++){const next=new Set();for(const idx of frontier){for(const e of any.get(idx)||[]){const target=edgeForwardFrom(e,idx);if(target<0||!visible(target))continue;localEdges.push(e);if(!keep.has(target)){keep.add(target);next.add(target)}}}frontier=next;if(!frontier.size)break}return{nodes:keep,edges:localEdges}}
function draw(){ctx.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);ctx.clearRect(0,0,innerWidth,innerHeight-66);ctx.fillStyle='#f8fafc';ctx.fillRect(0,0,innerWidth,innerHeight-66);const drawEdges=showAll?edges:nb.edges;for(const e of drawEdges){if(!visible(e.s)||!visible(e.t))continue;const a=nodes[e.s],b=nodes[e.t],ax=sx(a.x),ay=sy(a.y),bx=sx(b.x),by=sy(b.y);if((ax<-60&&bx<-60)||(ay<-60&&by<-60)||(ax>innerWidth+60&&bx>innerWidth+60)||(ay>innerHeight+60&&by>innerHeight+60))continue;const hi=selected>=0&&nb.nodes.has(e.s)&&nb.nodes.has(e.t);ctx.globalAlpha=hi?1:(showAll?.035:.55);ctx.strokeStyle=e.c;ctx.lineWidth=hi?2.2:.55;if(e.r.includes('negatively'))ctx.setLineDash([5,4]);else ctx.setLineDash([]);ctx.beginPath();ctx.moveTo(ax,ay);ctx.lineTo(bx,by);ctx.stroke()}ctx.setLineDash([]);for(let i=0;i<nodes.length;i++){if(!visible(i))continue;const n=nodes[i],x=sx(n.x),y=sy(n.y);if(x<-20||y<-20||x>innerWidth+20||y>innerHeight+20)continue;const dim=selected>=0&&!nb.nodes.has(i);ctx.globalAlpha=dim?.06:.88;ctx.fillStyle=n.c;ctx.beginPath();ctx.arc(x,y,Math.max(.7,radius(n)*Math.sqrt(scale*14)),0,Math.PI*2);ctx.fill()}ctx.globalAlpha=1;if(selected>=0){const n=nodes[selected];ctx.strokeStyle='#020617';ctx.lineWidth=2.4;ctx.beginPath();ctx.arc(sx(n.x),sy(n.y),6.5,0,Math.PI*2);ctx.stroke();ctx.fillStyle='#0f172a';ctx.font='13px system-ui';ctx.fillText(n.l.length>48?n.l.slice(0,45)+'...':n.l,sx(n.x)+10,sy(n.y)+4)}if(hover>=0&&hover!==selected){const n=nodes[hover];ctx.strokeStyle='#334155';ctx.lineWidth=1.8;ctx.beginPath();ctx.arc(sx(n.x),sy(n.y),5,0,Math.PI*2);ctx.stroke()}document.getElementById('status').textContent=nodes.length.toLocaleString()+' nodes, '+edges.length.toLocaleString()+' edges'}
function nearest(cx,cy){const x=cx,y=cy-66;let best=-1,bestD=18*18,cands=selected>=0?nb.nodes:null;for(let i=0;i<nodes.length;i++){if(!visible(i))continue;if(cands&&!cands.has(i))continue;const dx=sx(nodes[i].x)-x,dy=sy(nodes[i].y)-y,d=dx*dx+dy*dy;if(d<bestD){best=i;bestD=d}}return best}
function select(i){selected=i;nb=local(i);const n=nodes[i],direct=(any.get(i)||[]).length;document.getElementById('details').innerHTML='<b>'+n.l+'</b><br><span class="muted">'+n.t+' · '+n.k+'</span><br>'+direct.toLocaleString()+' direct edges<br>'+nb.nodes.size.toLocaleString()+' outgoing-neighborhood nodes, '+nb.edges.length.toLocaleString()+' edges';draw()}
function tip(i,e){if(i<0){tooltip.style.display='none';return}const n=nodes[i];tooltip.innerHTML='<b>'+n.l+'</b><br>'+n.t;tooltip.style.left=Math.min(e.clientX+12,innerWidth-340)+'px';tooltip.style.top=Math.min(e.clientY+12,innerHeight-80)+'px';tooltip.style.display='block'}
canvas.addEventListener('mousedown',e=>{last={x:e.clientX,y:e.clientY};const n=nearest(e.clientX,e.clientY);if(n>=0)select(n);else drag=true});
canvas.addEventListener('mousemove',e=>{if(drag&&last){tx+=e.clientX-last.x;ty+=e.clientY-last.y;last={x:e.clientX,y:e.clientY};draw();return}const n=nearest(e.clientX,e.clientY);if(n!==hover){hover=n;draw()}tip(n,e)});
addEventListener('mouseup',()=>{drag=false;last=null});canvas.addEventListener('mouseleave',()=>{hover=-1;tip(-1,{});draw()});
canvas.addEventListener('wheel',e=>{e.preventDefault();const old=scale;scale*=e.deltaY<0?1.14:.88;scale=Math.max(.004,Math.min(3,scale));const mx=e.clientX,my=e.clientY-66;tx=mx-(mx-tx)*(scale/old);ty=my-(my-ty)*(scale/old);draw()},{passive:false});
document.getElementById('allEdges').addEventListener('change',e=>{showAll=e.target.checked;draw()});document.getElementById('degree').addEventListener('change',()=>{if(selected>=0)select(selected);else draw()});
document.getElementById('reset').addEventListener('click',()=>{selected=-1;hover=-1;nb={nodes:new Set(),edges:[]};scale=.07;tx=innerWidth/2;ty=(innerHeight-66)/2;document.getElementById('details').textContent='Search or click a node.';draw()});
function findNode(){const q=document.getElementById('search').value.trim().toLowerCase();if(!q)return;const i=nodes.findIndex((n,idx)=>visible(idx)&&(n.l.toLowerCase().includes(q)||n.k.toLowerCase().includes(q)));if(i>=0){tx=innerWidth/2-nodes[i].x*scale;ty=(innerHeight-66)/2-nodes[i].y*scale;select(i)}}
document.getElementById('find').addEventListener('click',findNode);document.getElementById('search').addEventListener('keydown',e=>{if(e.key==='Enter')findNode()});
const legend=document.getElementById('legend');Object.entries(raw.nodeColors).forEach(([kind,color])=>{const item=document.createElement('div');item.className='legend-item';item.innerHTML='<span class="dot" style="background:'+color+'"></span>'+kind;item.onclick=()=>{if(hidden.has(kind)){hidden.delete(kind);item.classList.remove('off')}else{hidden.add(kind);item.classList.add('off')}if(selected>=0&&!visible(selected))selected=-1;nb=selected>=0?local(selected):{nodes:new Set(),edges:[]};draw()};legend.appendChild(item)});
resize();addEventListener('resize',resize);
</script>
</body>
</html>
"""


def build_denovo_hpp_kg_mega_flexible():
    OUT.mkdir(parents=True, exist_ok=True)
    nodes, key_to_index, old_to_new = _build_nodes()
    edges, relations = _build_edges(key_to_index, old_to_new)
    data_path = OUT / "denovo_hpp_kg_mega_flexible_data.js"
    html_path = OUT / "denovo_hpp_kg_mega_flexible.html"
    _write_data_js(data_path, nodes, edges, relations)
    html_path.write_text(_html())
    summary = {
        "html": str(html_path),
        "data": str(data_path),
        "nodes": len(nodes),
        "edges": len(edges),
        "node_kind_counts": pd.Series([node["kind"] for node in nodes]).value_counts().to_dict(),
        "relation_count": len(relations),
        "relations": relations,
    }
    (OUT / "denovo_hpp_kg_mega_flexible_summary.json").write_text(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    print(json.dumps(build_denovo_hpp_kg_mega_flexible(), indent=2))
