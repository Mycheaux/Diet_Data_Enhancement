import csv
import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd

from ..graph_store import load_graph, save_graph, upsert_edge, upsert_node
from ..mapping import find_candidates, build_index
from ..sources import load_foodatlas_entities_if_available, load_public_foods


ROOT = Path(__file__).resolve().parents[2]
MAPPING_DIR = ROOT / "outputs/mapping"
GRAPH_PATH = ROOT / "outputs/graph/food_mapping_graph.json"
REVIEW_PATH = MAPPING_DIR / "review_queue.csv"
HUMAN_PATH = MAPPING_DIR / "human_corrections.csv"
HUMAN_FOODATLAS_PATH = ROOT / "outputs/foodatlas/human_foodatlas_remap.csv"


def ensure_outputs():
    if not REVIEW_PATH.exists():
        from ..pipeline import run

        run()
    MAPPING_DIR.mkdir(parents=True, exist_ok=True)
    if not HUMAN_PATH.exists():
        with HUMAN_PATH.open("w", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "hpp_food_id",
                    "hpp_food_name",
                    "human_food_name",
                    "human_category",
                    "human_notes",
                    "remap_source",
                    "remap_source_food_id",
                    "remap_food_name",
                    "remap_score",
                    "remap_confidence",
                ],
            )
            writer.writeheader()
    HUMAN_FOODATLAS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not HUMAN_FOODATLAS_PATH.exists():
        with HUMAN_FOODATLAS_PATH.open("w", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "hpp_food_id",
                    "human_food_name",
                    "foodatlas_id",
                    "foodatlas_name",
                    "match_score",
                    "confidence",
                    "status",
                ],
            )
            writer.writeheader()


def load_queue():
    ensure_outputs()
    corrections = pd.read_csv(HUMAN_PATH) if HUMAN_PATH.exists() else pd.DataFrame()
    reviewed_ids = set(corrections["hpp_food_id"].astype(str)) if not corrections.empty else set()
    queue = pd.read_csv(REVIEW_PATH)
    queue["hpp_food_id"] = queue["hpp_food_id"].astype(str)
    return queue[~queue["hpp_food_id"].isin(reviewed_ids)]


def category_options():
    ensure_outputs()
    values = []
    if REVIEW_PATH.exists():
        queue = pd.read_csv(REVIEW_PATH)
        if "hpp_category" in queue.columns:
            values.extend(queue["hpp_category"].dropna().astype(str).tolist())
    if HUMAN_PATH.exists():
        corrections = pd.read_csv(HUMAN_PATH)
        if "human_category" in corrections.columns:
            values.extend(corrections["human_category"].dropna().astype(str).tolist())
    cleaned = sorted({value.strip() for value in values if value and value.strip()})
    return cleaned


def page_shell(body):
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Diet Mapping Review</title>
  <link rel="stylesheet" href="/style.css">
</head>
<body>{body}
<script>
function filterCategories(query) {{
  const select = document.querySelector('.category-select');
  if (!select) return;
  const needle = query.trim().toLowerCase();
  for (const option of select.options) {{
    if (!option.value) {{
      option.hidden = false;
      continue;
    }}
    option.hidden = needle && !option.textContent.toLowerCase().includes(needle);
  }}
}}
</script>
</body>
</html>"""


def render_home(message="", min_score=0.0, max_score=1.0):
    queue = load_queue()
    queue["match_score"] = pd.to_numeric(queue["match_score"], errors="coerce").fillna(0)
    total = len(pd.read_csv(REVIEW_PATH)) if REVIEW_PATH.exists() else 0
    done = total - len(queue)
    filtered = queue[(queue["match_score"] >= min_score) & (queue["match_score"] <= max_score)].copy()
    items = []
    for _, row in filtered.head(120).iterrows():
        original = str(row.get("hpp_short_description", "") or "").strip()
        original_line = (
            f'<small>Original: {html.escape(original)}</small>'
            if original and original != str(row["hpp_food_name"])
            else ""
        )
        items.append(
            f"""<a class="queue-item" href="/item?id={html.escape(str(row['hpp_food_id']))}">
              <strong>{html.escape(str(row['hpp_food_name']))}</strong>
              {original_line}
              <span>{html.escape(str(row.get('confidence', '')))} · score {float(row.get('match_score', 0)):.4f}</span>
            </a>"""
        )
    body = f"""
<main class="layout">
  <section class="topbar">
    <div>
      <h1>Diet Mapping Review</h1>
      <p>{done} reviewed · {len(queue)} pending · {total} total flagged</p>
    </div>
    <a class="button" href="/graph">Graph JSON</a>
  </section>
  {f'<p class="notice">{html.escape(message)}</p>' if message else ''}
  <section class="panel filter-panel">
    <div>
      <h2>Score filter</h2>
      <p class="muted">Show entries with automated match scores between the selected lower and upper limits.</p>
    </div>
    <form class="filter-form" method="get" action="/">
      <label>Lower than / from
        <div class="range-row">
          <input type="range" name="min_score" min="0" max="1" step="0.01" value="{min_score:.2f}" oninput="minScoreValue.value = Number(this.value).toFixed(2)">
          <output id="minScoreValue">{min_score:.2f}</output>
        </div>
      </label>
      <label>Higher than / to
        <div class="range-row">
          <input type="range" name="max_score" min="0" max="1" step="0.01" value="{max_score:.2f}" oninput="maxScoreValue.value = Number(this.value).toFixed(2)">
          <output id="maxScoreValue">{max_score:.2f}</output>
        </div>
      </label>
      <button class="button" type="submit">Apply filter</button>
      <a class="button ghost" href="/">Reset</a>
    </form>
    <div class="count-card">
      <strong>{len(filtered)}</strong>
      <span>entries remaining after filter</span>
    </div>
  </section>
  <section class="panel">
    <h2>Pending review queue</h2>
    <div class="queue">{''.join(items) if items else '<p class="empty">No pending review items.</p>'}</div>
  </section>
</main>"""
    return page_shell(body)


def render_item(food_id):
    queue = load_queue()
    item = queue[queue["hpp_food_id"].astype(str) == str(food_id)]
    if item.empty:
        return render_home("That item is already reviewed or not in the queue.")
    row = item.iloc[0].to_dict()
    candidates = pd.read_csv(MAPPING_DIR / "hpp_public_food_mappings.csv")
    candidates = candidates[candidates["hpp_food_id"].astype(str) == str(food_id)].head(5)
    candidate_rows = []
    for _, cand in candidates.iterrows():
        candidate_rows.append(
            f"""<tr>
              <td>{html.escape(str(cand['candidate_rank']))}</td>
              <td>{html.escape(str(cand['source']))}</td>
              <td>{html.escape(str(cand['matched_food_name']))}</td>
              <td>{html.escape(str(cand['match_score']))}</td>
              <td>{html.escape(str(cand['confidence']))}</td>
            </tr>"""
        )
    categories = category_options()
    current_category = str(row.get("hpp_category", "") or "")
    original_name = str(row.get("hpp_short_description", "") or "").strip()
    original_detail = (
        f'<p class="original-name">Original/product entry: <strong>{html.escape(original_name)}</strong></p>'
        if original_name
        else ""
    )
    category_options_html = "\n".join(
        f'<option value="{html.escape(category)}" {"selected" if category == current_category else ""}>{html.escape(category)}</option>'
        for category in categories
    )
    body = f"""
<main class="layout">
  <section class="topbar">
    <div>
      <a href="/" class="back">Back to queue</a>
      <h1>{html.escape(str(row['hpp_food_name']))}</h1>
      <p>{html.escape(str(row.get('hpp_category', '')))}</p>
      {original_detail}
    </div>
  </section>
  <section class="grid">
    <article class="panel">
      <h2>Automated candidates</h2>
      <table>
        <thead><tr><th>Rank</th><th>Source</th><th>Match</th><th>Score</th><th>Tier</th></tr></thead>
        <tbody>{''.join(candidate_rows)}</tbody>
      </table>
    </article>
    <article class="panel">
      <h2>Human correction</h2>
      <p class="muted form-note">When you click Save and remap, the corrected name and category are saved, immediately remapped against public FCDBs and FoodAtlas, and added to the graph.</p>
      <form method="post" action="/save">
        <input type="hidden" name="hpp_food_id" value="{html.escape(str(row['hpp_food_id']))}">
        <input type="hidden" name="hpp_food_name" value="{html.escape(str(row['hpp_food_name']))}">
        <label>Corrected food name
          <input name="human_food_name" value="{html.escape(str(row['hpp_food_name']))}" required>
        </label>
        <fieldset class="category-box">
          <legend>Category</legend>
          <p class="muted">Choose an existing category from the searchable list. If no existing category fits, use Add new category and write a short, reusable category name.</p>
          <label>Find a category
            <input class="category-search" type="search" placeholder="Type to filter the dropdown" oninput="filterCategories(this.value)">
          </label>
          <label>Existing category
            <select name="human_category" class="category-select">
              <option value="">Choose an existing category</option>
              {category_options_html}
            </select>
          </label>
          <button class="button ghost small" type="button" onclick="document.querySelector('.new-category').hidden = false; document.querySelector('[name=new_category]').focus()">Add new category</button>
          <label class="new-category" hidden>New category
            <input name="new_category" placeholder="Example: mixed dish, sweet baked good, dairy beverage">
          </label>
        </fieldset>
        <label>Notes
          <textarea name="human_notes" rows="5" placeholder="Preparation, brand, ingredients, why the candidate is wrong..."></textarea>
        </label>
        <button class="button" type="submit">Save and remap</button>
      </form>
    </article>
  </section>
</main>"""
    return page_shell(body)


def save_review(params):
    food_name = params.get("human_food_name", [""])[0].strip()
    selected_category = params.get("human_category", [""])[0].strip()
    new_category = params.get("new_category", [""])[0].strip()
    human_category = new_category or selected_category
    public = load_public_foods()
    index = build_index(public)
    remap = find_candidates(food_name, index, top_k=1)
    best = remap[0] if remap else {}
    foodatlas = load_foodatlas_entities_if_available()
    foodatlas_best = {}
    if not foodatlas.empty:
        foodatlas_best = find_candidates(food_name, build_index(foodatlas), top_k=1)
        foodatlas_best = foodatlas_best[0] if foodatlas_best else {}
    row = {
        "hpp_food_id": params.get("hpp_food_id", [""])[0],
        "hpp_food_name": params.get("hpp_food_name", [""])[0],
        "human_food_name": food_name,
        "human_category": human_category,
        "human_notes": params.get("human_notes", [""])[0],
        "remap_source": best.get("source", ""),
        "remap_source_food_id": best.get("source_food_id", ""),
        "remap_food_name": best.get("matched_food_name", ""),
        "remap_score": best.get("match_score", 0),
        "remap_confidence": best.get("confidence", "review"),
    }
    with HUMAN_PATH.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row.keys()))
        writer.writerow(row)
    if foodatlas_best:
        fa_row = {
            "hpp_food_id": row["hpp_food_id"],
            "human_food_name": row["human_food_name"],
            "foodatlas_id": foodatlas_best.get("source_food_id", ""),
            "foodatlas_name": foodatlas_best.get("matched_food_name", ""),
            "match_score": foodatlas_best.get("match_score", 0),
            "confidence": foodatlas_best.get("confidence", "review"),
            "status": "ui_human_correction_candidate",
        }
        with HUMAN_FOODATLAS_PATH.open("a", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(fa_row.keys()))
            writer.writerow(fa_row)

    graph = load_graph(GRAPH_PATH)
    hpp_key = upsert_node(graph, "hpp_food", row["hpp_food_id"], row["hpp_food_name"], reviewed=True)
    human_key = upsert_node(
        graph,
        "human_assertion",
        f"{row['hpp_food_id']}:{row['human_food_name']}",
        row["human_food_name"],
        category=row["human_category"],
        notes=row["human_notes"],
    )
    upsert_edge(graph, hpp_key, human_key, "human_corrected_to", confidence="human_reviewed")
    if row["remap_food_name"]:
        source_key = upsert_node(
            graph,
            "source_food",
            f"{row['remap_source']}:{row['remap_source_food_id']}",
            row["remap_food_name"],
            source=row["remap_source"],
        )
        upsert_edge(
            graph,
            human_key,
            source_key,
            "remapped_to",
            score=float(row["remap_score"]),
            confidence=row["remap_confidence"],
            stage="human_review_remap",
        )
    if foodatlas_best:
        foodatlas_key = upsert_node(
            graph,
            "foodatlas_food",
            foodatlas_best.get("source_food_id", ""),
            foodatlas_best.get("matched_food_name", ""),
            source="FoodAtlas",
        )
        upsert_edge(
            graph,
            human_key,
            foodatlas_key,
            "foodatlas_candidate",
            score=float(foodatlas_best.get("match_score", 0) or 0),
            confidence=foodatlas_best.get("confidence", ""),
            stage="human_review_foodatlas_remap",
        )
    save_graph(graph, GRAPH_PATH)


CSS = """
:root { color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #eef8fb; color: #073044; }
body { margin: 0; min-height: 100vh; background: radial-gradient(circle at top left, #b8edf6 0, transparent 34%), linear-gradient(180deg, #e9f8fc 0%, #f7fbfc 46%, #eef7fb 100%); }
.layout { max-width: 1180px; margin: 0 auto; padding: 34px; }
.topbar { display: flex; justify-content: space-between; gap: 24px; align-items: flex-start; margin-bottom: 20px; padding: 22px; color: white; background: linear-gradient(135deg, #075985 0%, #0284c7 52%, #06b6d4 100%); border-radius: 8px; box-shadow: 0 16px 35px rgba(7,89,133,.22); }
h1 { font-size: 34px; line-height: 1.1; margin: 0 0 8px; letter-spacing: 0; }
h2 { font-size: 18px; margin: 0 0 14px; color: #083449; }
p { margin: 0; color: #4c7180; }
.topbar p { color: #d9f7ff; }
.panel { background: rgba(255,255,255,.92); border: 1px solid #b9e3ee; border-radius: 8px; padding: 20px; box-shadow: 0 10px 26px rgba(8,47,73,.08); backdrop-filter: blur(8px); margin-bottom: 18px; }
.filter-panel { display: grid; grid-template-columns: 1fr minmax(420px, 1.6fr) 190px; gap: 18px; align-items: center; }
.filter-form { display: grid; grid-template-columns: 1fr 1fr auto auto; gap: 12px; align-items: end; }
.range-row { display: grid; grid-template-columns: 1fr 48px; gap: 10px; align-items: center; }
input[type=range] { accent-color: #0284c7; padding: 0; border: 0; }
output { color: #075985; font-weight: 800; font-variant-numeric: tabular-nums; }
.count-card { display: grid; gap: 2px; justify-items: center; padding: 16px; border-radius: 8px; background: #e0f7ff; border: 1px solid #98d9eb; }
.count-card strong { color: #075985; font-size: 30px; line-height: 1; }
.count-card span { text-align: center; color: #416a78; font-size: 13px; }
.queue { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 10px; }
.queue-item { display: flex; flex-direction: column; gap: 7px; padding: 15px; border: 1px solid #b9e3ee; border-radius: 8px; color: inherit; text-decoration: none; background: linear-gradient(180deg, #ffffff, #f1fbfe); min-height: 78px; transition: transform .12s ease, border-color .12s ease, box-shadow .12s ease; }
.queue-item:hover { border-color: #0284c7; transform: translateY(-1px); box-shadow: 0 10px 22px rgba(2,132,199,.14); }
.queue-item small { color: #6d8b98; font-size: 12px; line-height: 1.3; }
.queue-item span { color: #527685; font-size: 13px; }
.grid { display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(340px, .75fr); gap: 18px; align-items: start; }
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th, td { border-bottom: 1px solid #d4edf4; text-align: left; padding: 10px 8px; vertical-align: top; }
th { color: #0f5f83; font-size: 12px; text-transform: uppercase; }
label { display: grid; gap: 8px; margin-bottom: 16px; color: #16475c; font-weight: 700; }
input, textarea { font: inherit; border: 1px solid #9ed8e8; border-radius: 6px; padding: 10px 12px; background: #fbfeff; color: #073044; }
input:focus, textarea:focus { outline: 3px solid rgba(14,165,233,.22); border-color: #0284c7; }
fieldset { border: 1px solid #b9e3ee; border-radius: 8px; padding: 14px; margin: 0 0 16px; background: #f3fbfe; }
legend { color: #075985; font-weight: 800; padding: 0 6px; }
.button { border: 0; border-radius: 6px; background: #0277bd; color: white; padding: 10px 14px; font-weight: 800; text-decoration: none; cursor: pointer; box-shadow: 0 8px 16px rgba(2,119,189,.18); white-space: nowrap; }
.button:hover { background: #0369a1; }
.button.ghost { background: #e0f2fe; color: #075985; box-shadow: none; border: 1px solid #9ed8e8; }
.button.small { width: fit-content; padding: 8px 11px; font-size: 13px; margin-bottom: 12px; }
.back { color: white; font-weight: 800; text-decoration: none; display: inline-block; margin-bottom: 12px; }
.notice { background: #dcfce7; color: #166534; padding: 12px 14px; border-radius: 6px; margin-bottom: 14px; border: 1px solid #86efac; }
.empty { padding: 18px; }
.muted { color: #5d7d89; font-size: 14px; line-height: 1.45; }
.form-note { margin-bottom: 16px; }
.original-name { color: #d9f7ff; font-size: 14px; margin-top: 8px; }
.original-name strong { color: #ffffff; }
@media (max-width: 980px) { .filter-panel, .filter-form { grid-template-columns: 1fr; } .grid { grid-template-columns: 1fr; } }
@media (max-width: 820px) { .layout { padding: 18px; } .topbar { display: block; } .panel { margin-bottom: 14px; } }
"""


class Handler(BaseHTTPRequestHandler):
    def send_html(self, content, status=200, content_type="text/html; charset=utf-8"):
        data = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/style.css":
            return self.send_html(CSS, content_type="text/css; charset=utf-8")
        if self.path.startswith("/item?"):
            params = parse_qs(urlparse(self.path).query)
            return self.send_html(render_item(params.get("id", [""])[0]))
        if self.path == "/graph":
            graph = load_graph(GRAPH_PATH)
            return self.send_html(json.dumps(graph, indent=2), content_type="application/json")
        params = parse_qs(urlparse(self.path).query)
        try:
            min_score = float(params.get("min_score", ["0"])[0])
            max_score = float(params.get("max_score", ["1"])[0])
        except ValueError:
            min_score, max_score = 0.0, 1.0
        min_score = max(0.0, min(1.0, min_score))
        max_score = max(0.0, min(1.0, max_score))
        if min_score > max_score:
            min_score, max_score = max_score, min_score
        return self.send_html(render_home(min_score=min_score, max_score=max_score))

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        params = parse_qs(body)
        if self.path == "/save":
            save_review(params)
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()
            return
        self.send_html("Not found", status=404)


def main():
    ensure_outputs()
    server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    print("Review UI running at http://127.0.0.1:8765")
    server.serve_forever()


if __name__ == "__main__":
    main()
