import csv
import html
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import pandas as pd

from ..layered import load_openfoodfacts_products
from ..mapping import map_hpp_to_public
from ..sources import load_public_foods


ROOT = Path(__file__).resolve().parents[2]
LAYERED = ROOT / "outputs/layered"
QUEUE_PATH = LAYERED / "hitl_review_queue.csv"
DECISIONS_PATH = LAYERED / "hitl_human_decisions.csv"
REMAP_PATH = LAYERED / "hitl_remap_candidates.csv"
CANONICAL_PATH = ROOT / "outputs/canonical/canonical_foods.csv"

DECISION_FIELDS = [
    "canonical_food_id",
    "canonical_name",
    "reviewer_decision",
    "identity_type",
    "accepted_nutrient_source_id",
    "accepted_product_source_id",
    "assign_existing_canonical_food_id",
    "reviewer_notes",
]

REMAP_FIELDS = [
    "canonical_food_id",
    "attempt",
    "created_at",
    "remap_scope",
    "reviewer_context",
    "source_layer",
    "mapping_role",
    "candidate_rank",
    "match_score",
    "confidence",
    "source",
    "source_food_id",
    "matched_food_name",
    "matched_category",
    "brands",
    "category_off",
    "ingredients_text",
    "nova_group",
    "nutriscore_grade",
]


def safe_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_filters(params):
    tier = params.get("tier", ["all"])[0]
    if tier not in {"all", "review", "low"}:
        tier = "all"
    min_score = max(0.0, min(1.0, safe_float(params.get("min_score", ["0"])[0], 0.0)))
    max_score = max(0.0, min(1.0, safe_float(params.get("max_score", ["1"])[0], 1.0)))
    if min_score > max_score:
        min_score, max_score = max_score, min_score
    return tier, min_score, max_score


def home_url(tier="all", min_score=0.0, max_score=1.0):
    query = urlencode(
        {
            "tier": tier,
            "min_score": f"{min_score:.2f}",
            "max_score": f"{max_score:.2f}",
        }
    )
    return f"/?{query}"


def ensure_outputs():
    if not QUEUE_PATH.exists():
        from ..layered import build_hitl_queue

        build_hitl_queue()
    LAYERED.mkdir(parents=True, exist_ok=True)
    if not DECISIONS_PATH.exists():
        with DECISIONS_PATH.open("w", newline="") as handle:
            csv.DictWriter(handle, fieldnames=DECISION_FIELDS).writeheader()
    if not REMAP_PATH.exists():
        with REMAP_PATH.open("w", newline="") as handle:
            csv.DictWriter(handle, fieldnames=REMAP_FIELDS).writeheader()
    else:
        with REMAP_PATH.open(newline="") as handle:
            current_fields = next(csv.reader(handle), [])
        if current_fields != REMAP_FIELDS:
            existing = pd.read_csv(REMAP_PATH, dtype=str).fillna("") if REMAP_PATH.stat().st_size else pd.DataFrame()
            for field in REMAP_FIELDS:
                if field not in existing:
                    existing[field] = ""
            existing[REMAP_FIELDS].to_csv(REMAP_PATH, index=False)


def load_remaining_queue():
    ensure_outputs()
    queue = load_pending_queue()
    if DECISIONS_PATH.exists():
        decisions = pd.read_csv(DECISIONS_PATH, dtype=str).fillna("")
        reviewed = set(decisions["canonical_food_id"].astype(str))
        queue = queue[~queue["canonical_food_id"].astype(str).isin(reviewed)]
    for col in ["total_loggings", "hpp_item_count", "hpp_food_count"]:
        queue[col] = pd.to_numeric(queue[col], errors="coerce").fillna(0).astype(int)
    queue["nutrient_match_score_number"] = pd.to_numeric(
        queue["nutrient_match_score"], errors="coerce"
    ).fillna(0.0)
    return queue


def load_pending_queue():
    ensure_outputs()
    queue = pd.read_csv(QUEUE_PATH, dtype=str).fillna("")
    queue = queue[queue["review_status"].eq("pending")].copy()
    for col in ["total_loggings", "hpp_item_count", "hpp_food_count"]:
        queue[col] = pd.to_numeric(queue[col], errors="coerce").fillna(0).astype(int)
    queue["nutrient_match_score_number"] = pd.to_numeric(
        queue["nutrient_match_score"], errors="coerce"
    ).fillna(0.0)
    return queue


def load_human_decision_ids():
    ensure_outputs()
    if not DECISIONS_PATH.exists():
        return set()
    decisions = pd.read_csv(DECISIONS_PATH, dtype=str).fillna("")
    return set(decisions["canonical_food_id"].astype(str))


def load_remap_candidates(canonical_food_id):
    ensure_outputs()
    remaps = pd.read_csv(REMAP_PATH, dtype=str).fillna("")
    remaps = remaps[remaps["canonical_food_id"].eq(canonical_food_id)].copy()
    if remaps.empty:
        return remaps
    remaps["attempt_number"] = pd.to_numeric(remaps["attempt"], errors="coerce").fillna(0).astype(int)
    current = []
    for _, group in remaps.groupby("mapping_role", sort=False):
        latest = int(group["attempt_number"].max())
        current.append(group[group["attempt_number"].eq(latest)])
    return pd.concat(current, ignore_index=True, sort=False) if current else remaps.iloc[0:0].copy()


def next_remap_attempt(canonical_food_id):
    ensure_outputs()
    remaps = pd.read_csv(REMAP_PATH, dtype=str).fillna("")
    remaps = remaps[remaps["canonical_food_id"].eq(canonical_food_id)].copy()
    if remaps.empty:
        return 1
    attempts = pd.to_numeric(remaps["attempt"], errors="coerce").fillna(0).astype(int)
    return int(attempts.max()) + 1


def remap_source_for_item(row, reviewer_context, source_df, layer, role, top_k=5):
    query = " ".join(
        part
        for part in [
            row.get("canonical_name", ""),
            row.get("representative_original_name", ""),
            row.get("canonical_category", ""),
            reviewer_context,
        ]
        if str(part).strip()
    )
    food = pd.DataFrame(
        [
            {
                "hpp_food_id": row["canonical_food_id"],
                "food_name": query,
                "short_description": row.get("representative_original_name", ""),
                "category": row.get("canonical_category", ""),
                "hebrew_name": "",
            }
        ]
    )
    mapped = map_hpp_to_public(food, source_df, top_k=top_k)
    mapped["source_layer"] = layer
    mapped["mapping_role"] = role
    return mapped


def run_remap(row, reviewer_context, remap_scope="both"):
    if remap_scope not in {"layer1", "layer2", "both"}:
        remap_scope = "both"
    attempt = next_remap_attempt(row["canonical_food_id"])
    created_at = time.strftime("%Y-%m-%d %H:%M:%S")
    rows = []

    if remap_scope in {"layer1", "both"}:
        layer1 = remap_source_for_item(
            row,
            reviewer_context,
            load_public_foods(),
            "layer_1_nutrients",
            "nutrient_reference",
        )
        for candidate in layer1.to_dict("records"):
            rows.append(
                {
                    "canonical_food_id": row["canonical_food_id"],
                    "attempt": attempt,
                    "created_at": created_at,
                    "remap_scope": remap_scope,
                    "reviewer_context": reviewer_context,
                    "source_layer": candidate.get("source_layer", ""),
                    "mapping_role": candidate.get("mapping_role", ""),
                    "candidate_rank": candidate.get("candidate_rank", ""),
                    "match_score": candidate.get("match_score", ""),
                    "confidence": candidate.get("confidence", ""),
                    "source": candidate.get("source", ""),
                    "source_food_id": candidate.get("source_food_id", ""),
                    "matched_food_name": candidate.get("matched_food_name", ""),
                    "matched_category": candidate.get("matched_category", ""),
                    "brands": "",
                    "category_off": "",
                    "ingredients_text": "",
                    "nova_group": "",
                    "nutriscore_grade": "",
                }
            )

    if remap_scope in {"layer2", "both"}:
        off_path = LAYERED / "openfoodfacts_candidate_source.csv"
        off = pd.read_csv(off_path, dtype=str).fillna("") if off_path.exists() else load_openfoodfacts_products()
        if not off.empty:
            layer2 = remap_source_for_item(
                row,
                reviewer_context,
                off,
                "layer_2_product_processing",
                "product_processing",
            )
            extra = off.drop_duplicates(["source", "source_food_id"])
            layer2 = layer2.merge(extra, on=["source", "source_food_id"], how="left", suffixes=("", "_off"))
            for candidate in layer2.to_dict("records"):
                rows.append(
                    {
                        "canonical_food_id": row["canonical_food_id"],
                        "attempt": attempt,
                        "created_at": created_at,
                        "remap_scope": remap_scope,
                        "reviewer_context": reviewer_context,
                        "source_layer": candidate.get("source_layer", ""),
                        "mapping_role": candidate.get("mapping_role", ""),
                        "candidate_rank": candidate.get("candidate_rank", ""),
                        "match_score": candidate.get("match_score", ""),
                        "confidence": candidate.get("confidence", ""),
                        "source": candidate.get("source", ""),
                        "source_food_id": candidate.get("source_food_id", ""),
                        "matched_food_name": candidate.get("matched_food_name", ""),
                        "matched_category": candidate.get("matched_category", ""),
                        "brands": candidate.get("brands", ""),
                        "category_off": candidate.get("category", candidate.get("category_off", "")),
                        "ingredients_text": candidate.get("ingredients_text", ""),
                        "nova_group": candidate.get("nova_group", ""),
                        "nutriscore_grade": candidate.get("nutriscore_grade", ""),
                    }
                )

    with REMAP_PATH.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REMAP_FIELDS)
        for item in rows:
            writer.writerow({field: item.get(field, "") for field in REMAP_FIELDS})
    return attempt


def canonical_options(current_id=""):
    if not CANONICAL_PATH.exists():
        return ""
    canonical = pd.read_csv(CANONICAL_PATH, dtype=str).fillna("")
    parts = ['<option value="">Do not merge / keep this canonical food</option>']
    for _, row in canonical.sort_values(["canonical_name", "canonical_category"]).iterrows():
        cid = row["canonical_food_id"]
        if cid == current_id:
            continue
        label = f"{row['canonical_name']} | {row.get('canonical_category', '')} | {cid}"
        parts.append(f'<option value="{html.escape(cid)}">{html.escape(label)}</option>')
    return "\n".join(parts)


def summary_cards(queue):
    all_pending = load_pending_queue()
    handled_ids = load_human_decision_ids()
    pending_ids = set(all_pending["canonical_food_id"].astype(str))
    handled_count = len(handled_ids & pending_ids)
    total_hpp = int(queue["hpp_item_count"].sum()) if not queue.empty else 0
    conf = queue["nutrient_confidence"].value_counts().to_dict() if not queue.empty else {}
    handled_conf = (
        all_pending[all_pending["canonical_food_id"].astype(str).isin(handled_ids)]["nutrient_confidence"].value_counts().to_dict()
        if not all_pending.empty
        else {}
    )
    by_tier = (
        queue.groupby("usage_tier")
        .agg(
            canonical_foods=("canonical_food_id", "nunique"),
            hpp_items=("hpp_item_count", "sum"),
        )
        .reset_index()
        if not queue.empty
        else pd.DataFrame(columns=["usage_tier", "canonical_foods", "hpp_items"])
    )
    tier_rows = []
    for _, row in by_tier.iterrows():
        tier_rows.append(
            f"""<tr>
              <td>{html.escape(str(row['usage_tier']))}</td>
              <td>{int(row['canonical_foods'])}</td>
              <td>{int(row['hpp_items'])}</td>
            </tr>"""
        )
    return f"""
<section class="stats">
  <article><strong>{len(queue)}</strong><span>canonical foods remaining</span></article>
  <article><strong>{handled_count}</strong><span>handled in this HITL pass</span></article>
  <article><strong>{total_hpp}</strong><span>underlying HPP food IDs</span></article>
  <article><strong>{conf.get('review', 0)}</strong><span>review-tier remaining</span><em>{handled_conf.get('review', 0)} handled</em></article>
  <article><strong>{conf.get('low', 0)}</strong><span>low-tier remaining</span><em>{handled_conf.get('low', 0)} handled</em></article>
</section>
<section class="panel">
  <h2>Remaining By Usage Tier</h2>
  <table>
    <thead><tr><th>Tier</th><th>Canonical foods</th><th>HPP food IDs</th></tr></thead>
    <tbody>{''.join(tier_rows)}</tbody>
  </table>
</section>"""


def filter_queue(queue, tier, min_score, max_score):
    filtered = queue.copy()
    if tier != "all":
        filtered = filtered[filtered["nutrient_confidence"].eq(tier)]
    return filtered[
        filtered["nutrient_match_score_number"].between(min_score, max_score, inclusive="both")
    ].copy()


def render_filters(queue, tier, min_score, max_score):
    group = queue if tier == "all" else queue[queue["nutrient_confidence"].eq(tier)]
    filtered = filter_queue(queue, tier, min_score, max_score)
    counts = queue["nutrient_confidence"].value_counts().to_dict()
    links = [
        ("all", "All", len(queue)),
        ("review", "Review", counts.get("review", 0)),
        ("low", "Low", counts.get("low", 0)),
    ]
    buttons = []
    for value, label, count in links:
        active = " active" if value == tier else ""
        buttons.append(
            f'<a class="filter-button{active}" href="{home_url(value, min_score, max_score)}">{label}<span>{count}</span></a>'
        )
    return f"""
<section class="panel filter-panel">
  <div class="filter-row">
    <div class="filter-buttons">{''.join(buttons)}</div>
    <div class="filter-count"><strong>{len(filtered)}</strong><span>shown from {len(group)} in selected group</span></div>
  </div>
  <form method="get" action="/" class="score-filter">
    <input type="hidden" name="tier" value="{html.escape(tier)}">
    <label>Minimum score
      <input type="range" name="min_score" min="0" max="1" step="0.01" value="{min_score:.2f}" oninput="document.getElementById('minScoreValue').textContent = Number(this.value).toFixed(2)">
      <output id="minScoreValue">{min_score:.2f}</output>
    </label>
    <label>Maximum score
      <input type="range" name="max_score" min="0" max="1" step="0.01" value="{max_score:.2f}" oninput="document.getElementById('maxScoreValue').textContent = Number(this.value).toFixed(2)">
      <output id="maxScoreValue">{max_score:.2f}</output>
    </label>
    <button class="button" type="submit">Apply score filter</button>
  </form>
</section>"""


def quick_decision_form(row, decision, label, notes, return_url="/"):
    nutrient_source_id = row.get("nutrient_source_food_id", "") if decision in {"accept_layer1", "accept_both"} else ""
    product_source_id = row.get("product_source_food_id", "") if decision in {"accept_layer2", "accept_both"} else ""
    return f"""
<form method="post" action="/save" class="inline-form">
  <input type="hidden" name="return_url" value="{html.escape(return_url)}">
  <input type="hidden" name="canonical_food_id" value="{html.escape(row['canonical_food_id'])}">
  <input type="hidden" name="canonical_name" value="{html.escape(row['canonical_name'])}">
  <input type="hidden" name="reviewer_decision" value="{html.escape(decision)}">
  <input type="hidden" name="identity_type" value="{html.escape(row.get('suggested_identity_type', 'generic_or_recipe'))}">
  <input type="hidden" name="accepted_nutrient_source_id" value="{html.escape(nutrient_source_id)}">
  <input type="hidden" name="accepted_product_source_id" value="{html.escape(product_source_id)}">
  <input type="hidden" name="assign_existing_canonical_food_id" value="">
  <input type="hidden" name="reviewer_notes" value="{html.escape(notes)}">
  <button class="button small" type="submit">{html.escape(label)}</button>
</form>"""


def quick_decision_buttons(row, return_url="/"):
    return f"""
<div class="quick-actions">
  {quick_decision_form(row, "accept_layer1", "Accept layer 1", "Accepted Layer 1 nutrient map from queue.", return_url)}
  {quick_decision_form(row, "accept_layer2", "Accept layer 2", "Accepted Layer 2 product/processing map from queue.", return_url)}
  {quick_decision_form(row, "accept_both", "Accept both", "Accepted current Layer 1 and Layer 2 maps from queue.", return_url)}
</div>"""


def remap_candidate_rows(candidates):
    rows = []
    for _, row in candidates.iterrows():
        detail = row.get("matched_category", "") or row.get("category_off", "")
        brand = row.get("brands", "")
        if brand:
            detail = f"{brand} | {detail}" if detail else brand
        rows.append(
            f"""<tr>
              <td>{html.escape(str(row.get('candidate_rank', '')))}</td>
              <td>{html.escape(str(row.get('matched_food_name', '')))}</td>
              <td>{html.escape(str(row.get('source', '')))}</td>
              <td>{html.escape(str(row.get('source_food_id', '')))}</td>
              <td>{html.escape(str(row.get('match_score', '')))}</td>
              <td>{html.escape(str(row.get('confidence', '')))}</td>
              <td>{html.escape(str(detail))}</td>
            </tr>"""
        )
    return "".join(rows) if rows else '<tr><td colspan="7">No candidates.</td></tr>'


def fixed_layer_candidate(row, mapping_role):
    if mapping_role == "nutrient_reference":
        return pd.DataFrame(
            [
                {
                    "candidate_rank": "fixed",
                    "matched_food_name": row.get("nutrient_matched_food_name", ""),
                    "source": row.get("nutrient_source", ""),
                    "source_food_id": row.get("nutrient_source_food_id", ""),
                    "match_score": row.get("nutrient_match_score", ""),
                    "confidence": row.get("nutrient_confidence", ""),
                    "matched_category": "unchanged current layer 1",
                    "mapping_role": "nutrient_reference",
                }
            ]
        )
    return pd.DataFrame(
        [
            {
                "candidate_rank": "fixed",
                "matched_food_name": row.get("product_matched_food_name", ""),
                "source": row.get("product_source", ""),
                "source_food_id": row.get("product_source_food_id", ""),
                "match_score": row.get("product_match_score", ""),
                "confidence": row.get("product_confidence", ""),
                "matched_category": "unchanged current layer 2",
                "brands": row.get("product_brand", ""),
                "category_off": row.get("product_category", ""),
                "mapping_role": "product_processing",
            }
        ]
    )


def remap_accept_form(row, decision, label, nutrient_id="", product_id="", attempt=""):
    return f"""
<form method="post" action="/save" class="inline-form">
  <input type="hidden" name="return_url" value="/">
  <input type="hidden" name="canonical_food_id" value="{html.escape(row['canonical_food_id'])}">
  <input type="hidden" name="canonical_name" value="{html.escape(row['canonical_name'])}">
  <input type="hidden" name="reviewer_decision" value="{html.escape(decision)}">
  <input type="hidden" name="identity_type" value="{html.escape(row.get('suggested_identity_type', 'generic_or_recipe'))}">
  <input type="hidden" name="accepted_nutrient_source_id" value="{html.escape(str(nutrient_id))}">
  <input type="hidden" name="accepted_product_source_id" value="{html.escape(str(product_id))}">
  <input type="hidden" name="assign_existing_canonical_food_id" value="">
  <input type="hidden" name="reviewer_notes" value="Accepted remapped candidate from attempt {html.escape(str(attempt))}.">
  <button class="button" type="submit">{html.escape(label)}</button>
</form>"""


def remap_accept_buttons(row, remaps):
    l1 = remaps[remaps["mapping_role"].eq("nutrient_reference")].sort_values("candidate_rank").head(1)
    l2 = remaps[remaps["mapping_role"].eq("product_processing")].sort_values("candidate_rank").head(1)
    remapped_l1 = not l1.empty
    remapped_l2 = not l2.empty
    if l1.empty:
        l1 = fixed_layer_candidate(row, "nutrient_reference")
    if l2.empty:
        l2 = fixed_layer_candidate(row, "product_processing")
    if l1.empty and l2.empty:
        return ""
    nutrient_id = l1.iloc[0].get("source_food_id", "") if not l1.empty else ""
    product_id = l2.iloc[0].get("source_food_id", "") if not l2.empty else ""
    attempt = remaps["attempt"].iloc[0] if "attempt" in remaps else ""
    buttons = []
    if nutrient_id and remapped_l1:
        buttons.append(remap_accept_form(row, "accept_layer1_remapped", "Accept layer 1", nutrient_id, "", attempt))
    if product_id and remapped_l2:
        buttons.append(remap_accept_form(row, "accept_layer2_remapped", "Accept layer 2", "", product_id, attempt))
    if nutrient_id and product_id:
        buttons.append(remap_accept_form(row, "accept_both_remapped", "Accept both", nutrient_id, product_id, attempt))
    return f'<div class="quick-actions">{"".join(buttons)}</div>'


def render_remap_panel(row):
    remaps = load_remap_candidates(row["canonical_food_id"])
    latest = ""
    if not remaps.empty:
        l1 = remaps[remaps["mapping_role"].eq("nutrient_reference")]
        l2 = remaps[remaps["mapping_role"].eq("product_processing")]
        l1_display = l1 if not l1.empty else fixed_layer_candidate(row, "nutrient_reference")
        l2_display = l2 if not l2.empty else fixed_layer_candidate(row, "product_processing")
        latest = f"""
    <div class="remap-results">
      <div class="section-head compact">
        <div>
          <h3>Current Remap State</h3>
          <p>latest saved candidate set for each remapped layer</p>
        </div>
        {remap_accept_buttons(row, remaps)}
      </div>
      <h3>Layer 1 Nutrient Candidates</h3>
      <table>
        <thead><tr><th>Rank</th><th>Food</th><th>Source</th><th>ID</th><th>Score</th><th>Tier</th><th>Detail</th></tr></thead>
        <tbody>{remap_candidate_rows(l1_display)}</tbody>
      </table>
      <h3>Layer 2 Product Candidates</h3>
      <table>
        <thead><tr><th>Rank</th><th>Product</th><th>Source</th><th>ID</th><th>Score</th><th>Tier</th><th>Detail</th></tr></thead>
        <tbody>{remap_candidate_rows(l2_display)}</tbody>
      </table>
    </div>"""
    return f"""
    <article class="panel full-width">
      <h2>Save and Remap</h2>
      <form method="post" action="/remap" class="remap-form">
        <input type="hidden" name="canonical_food_id" value="{html.escape(row['canonical_food_id'])}">
        <label>Add food identity details
          <textarea name="reviewer_context" rows="4" placeholder="Example: plain yellow cheese, cow milk, hard cheese, not tofu, 9% fat"></textarea>
        </label>
        <div class="quick-actions">
          <button class="button" type="submit" name="remap_scope" value="layer1">Save and remap layer 1</button>
          <button class="button" type="submit" name="remap_scope" value="layer2">Save and remap layer 2</button>
          <button class="button" type="submit" name="remap_scope" value="both">Save and remap both</button>
        </div>
      </form>
      {latest}
    </article>"""


def render_queue_section(title, rows, description, return_url="/"):
    items = []
    for _, row in rows.head(160).iterrows():
        items.append(
            f"""<article class="queue-item">
              <a class="queue-link" href="/item?id={html.escape(row['canonical_food_id'])}">
                <strong>{html.escape(row['canonical_name'])}</strong>
                <small>{html.escape(row.get('canonical_category', ''))}</small>
                <span>{html.escape(row['usage_tier'])} · {int(row['hpp_item_count'])} HPP IDs</span>
                <span>Layer 1: {html.escape(row['nutrient_confidence'])} · {html.escape(row['nutrient_matched_food_name'])}</span>
              </a>
              {quick_decision_buttons(row, return_url=return_url)}
            </article>"""
        )
    return f"""
  <section class="panel">
    <div class="section-head">
      <div>
        <h2>{html.escape(title)}</h2>
        <p>{html.escape(description)}</p>
      </div>
      <strong>{len(rows)}</strong>
    </div>
    <div class="queue">{''.join(items) if items else '<p class="empty">No pending items in this tier.</p>'}</div>
  </section>"""


def page(body):
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Layered HITL Review</title>
  <link rel="stylesheet" href="/style.css">
</head>
<body>{body}</body>
</html>"""


def render_home(params=None):
    params = params or {}
    tier, min_score, max_score = parse_filters(params)
    queue = load_remaining_queue()
    filtered = filter_queue(queue, tier, min_score, max_score)
    return_url = home_url(tier, min_score, max_score)
    sections = []
    if tier in {"all", "review"}:
        review_queue = filtered[filtered["nutrient_confidence"].eq("review")]
        sections.append(
            render_queue_section(
                "Review Tier",
                review_queue,
                "Ambiguous matches. These are often plausible enough to accept after a quick check.",
                return_url,
            )
        )
    if tier in {"all", "low"}:
        low_queue = filtered[filtered["nutrient_confidence"].eq("low")]
        sections.append(
            render_queue_section(
                "Low Tier",
                low_queue,
                "Weak matches. These are more likely to need reassignment, manual research, or rejection.",
                return_url,
            )
        )
    body = f"""
<main class="layout">
  <header class="topbar">
    <div>
      <h1>Layered HITL Review</h1>
      <p>Only weak or ambiguous Layer 1 mappings remain here. Strong Layer 2 OpenFoodFacts mappings are auto-accepted.</p>
    </div>
  </header>
  {summary_cards(queue)}
  {render_filters(queue, tier, min_score, max_score)}
  {''.join(sections)}
</main>"""
    return page(body)


def render_item(canonical_food_id):
    queue = load_remaining_queue()
    item = queue[queue["canonical_food_id"].eq(canonical_food_id)]
    if item.empty:
        return render_home()
    row = item.iloc[0].to_dict()
    body = f"""
<main class="layout">
  <header class="topbar">
    <div>
      <a class="back" href="/">Back to queue</a>
      <h1>{html.escape(row['canonical_name'])}</h1>
      <p>{html.escape(row.get('canonical_category', ''))}</p>
    </div>
  </header>
  <section class="grid">
    <article class="panel">
      <h2>Canonical Food</h2>
      <dl>
        <dt>Canonical ID</dt><dd>{html.escape(row['canonical_food_id'])}</dd>
        <dt>Representative HPP entry</dt><dd>{html.escape(row.get('representative_original_name', ''))}</dd>
        <dt>Underlying HPP food IDs</dt><dd>{int(row.get('hpp_item_count', 0))}</dd>
        <dt>Usage tier</dt><dd>{html.escape(row.get('usage_tier', ''))}</dd>
        <dt>Review tier</dt><dd>{html.escape(row.get('nutrient_confidence', ''))}</dd>
      </dl>
    </article>
    <article class="panel">
      <h2>Original Layer 1 Candidate</h2>
      <dl>
        <dt>Source</dt><dd>{html.escape(row.get('nutrient_source', ''))}</dd>
        <dt>Source food ID</dt><dd>{html.escape(row.get('nutrient_source_food_id', ''))}</dd>
        <dt>Matched food</dt><dd>{html.escape(row.get('nutrient_matched_food_name', ''))}</dd>
        <dt>Score</dt><dd>{html.escape(row.get('nutrient_match_score', ''))}</dd>
        <dt>Tier</dt><dd>{html.escape(row.get('nutrient_confidence', ''))}</dd>
      </dl>
    </article>
    <article class="panel">
      <h2>Original Layer 2 Candidate</h2>
      <dl>
        <dt>Product</dt><dd>{html.escape(row.get('product_matched_food_name', ''))}</dd>
        <dt>Barcode</dt><dd>{html.escape(row.get('product_source_food_id', ''))}</dd>
        <dt>Brand</dt><dd>{html.escape(row.get('product_brand', ''))}</dd>
        <dt>Category</dt><dd>{html.escape(row.get('product_category', ''))}</dd>
        <dt>Score / tier</dt><dd>{html.escape(row.get('product_match_score', ''))} / {html.escape(row.get('product_confidence', ''))}</dd>
      </dl>
    </article>
    <article class="panel">
      <h2>Reviewer Decision</h2>
      {quick_decision_buttons(row)}
      <form method="post" action="/save">
        <input type="hidden" name="return_url" value="/">
        <input type="hidden" name="canonical_food_id" value="{html.escape(row['canonical_food_id'])}">
        <input type="hidden" name="canonical_name" value="{html.escape(row['canonical_name'])}">
        <label>Decision
          <select name="reviewer_decision">
            <option value="accept_layer1">Accept layer 1</option>
            <option value="accept_layer2">Accept layer 2</option>
            <option value="accept_both">Accept both</option>
            <option value="assign_existing_canonical">Assign/merge to existing canonical food</option>
            <option value="needs_manual_research">Needs manual research</option>
            <option value="reject_all">Reject current candidates</option>
          </select>
        </label>
        <label>Identity type
          <select name="identity_type">
            <option value="generic_or_recipe">Generic / recipe</option>
            <option value="branded_or_packaged">Branded / packaged</option>
            <option value="ambiguous">Ambiguous</option>
          </select>
        </label>
        <label>Accepted nutrient source ID
          <input name="accepted_nutrient_source_id" value="{html.escape(row.get('nutrient_source_food_id', ''))}">
        </label>
        <label>Accepted product source ID
          <input name="accepted_product_source_id" value="{html.escape(row.get('product_source_food_id', ''))}">
        </label>
        <label>Assign to existing canonical food
          <select name="assign_existing_canonical_food_id">
            {canonical_options(row['canonical_food_id'])}
          </select>
        </label>
        <label>Notes
          <textarea name="reviewer_notes" rows="5"></textarea>
        </label>
        <button class="button" type="submit">Save decision</button>
      </form>
    </article>
    {render_remap_panel(row)}
  </section>
</main>"""
    return page(body)


def save_decision(params):
    row = {field: params.get(field, [""])[0].strip() for field in DECISION_FIELDS}
    with DECISIONS_PATH.open("a", newline="") as handle:
        csv.DictWriter(handle, fieldnames=DECISION_FIELDS).writerow(row)


def safe_return_url(params):
    return_url = params.get("return_url", ["/"])[0].strip() or "/"
    if not return_url.startswith("/") or return_url.startswith("//"):
        return "/"
    return return_url


CSS = """
:root { font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #102a43; background: #f5fbff; }
body { margin: 0; background: #f5fbff; }
.layout { max-width: 1240px; margin: 0 auto; padding: 28px; }
.topbar { display: flex; justify-content: space-between; gap: 20px; padding: 22px; color: white; background: #075985; border-radius: 8px; margin-bottom: 18px; }
h1 { margin: 0 0 6px; font-size: 30px; }
h2 { margin: 0 0 14px; font-size: 18px; color: #075985; }
p { margin: 0; color: #496a7a; }
.topbar p { color: #dff8ff; }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin-bottom: 16px; }
.stats article, .panel { background: white; border: 1px solid #c8e7f2; border-radius: 8px; box-shadow: 0 8px 24px rgba(15, 76, 117, .08); }
.stats article { padding: 16px; display: grid; gap: 4px; }
.stats strong { font-size: 28px; color: #0369a1; }
.stats span { color: #527084; font-size: 13px; }
.stats em { color: #78909c; font-size: 12px; font-style: normal; }
.panel { padding: 18px; margin-bottom: 16px; }
.filter-panel { display: grid; gap: 16px; }
.filter-row { display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; }
.filter-buttons { display: flex; flex-wrap: wrap; gap: 8px; }
.filter-button { display: inline-flex; align-items: center; gap: 8px; padding: 9px 12px; border: 1px solid #a9d7e5; border-radius: 6px; color: #075985; text-decoration: none; font-weight: 800; background: #fbfeff; }
.filter-button.active { background: #075985; color: white; border-color: #075985; }
.filter-button span { min-width: 24px; padding: 2px 7px; border-radius: 999px; color: #075985; background: #e0f2fe; text-align: center; }
.filter-button.active span { color: #075985; background: white; }
.filter-count { display: grid; justify-items: end; gap: 2px; }
.filter-count strong { color: #0369a1; font-size: 28px; }
.filter-count span { color: #607d8b; font-size: 13px; }
.score-filter { display: grid; grid-template-columns: repeat(2, minmax(220px, 1fr)) auto; align-items: end; gap: 12px; }
.score-filter label { margin-bottom: 0; }
input[type="range"] { padding: 0; accent-color: #0277bd; }
output { color: #0369a1; font-weight: 800; }
.section-head { display: flex; align-items: end; justify-content: space-between; gap: 16px; margin-bottom: 14px; }
.section-head strong { color: #0369a1; font-size: 28px; }
.queue { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 10px; }
.queue-item { display: grid; gap: 10px; padding: 14px; border: 1px solid #c8e7f2; border-radius: 8px; color: inherit; background: #fbfeff; }
.queue-item:hover { border-color: #0284c7; box-shadow: 0 8px 18px rgba(2,132,199,.14); }
.queue-item small, .queue-item span { color: #607d8b; font-size: 13px; }
.queue-link { display: grid; gap: 6px; color: inherit; text-decoration: none; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 9px 8px; border-bottom: 1px solid #e0f2f8; text-align: left; }
.grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; align-items: start; }
.full-width { grid-column: 1 / -1; }
.compact { align-items: center; }
h3 { margin: 16px 0 10px; font-size: 15px; color: #264b5d; }
.remap-form { display: grid; gap: 12px; margin-bottom: 16px; }
.remap-results { display: grid; gap: 10px; }
dt { color: #607d8b; font-size: 12px; text-transform: uppercase; margin-top: 10px; }
dd { margin: 3px 0 0; }
label { display: grid; gap: 7px; margin-bottom: 13px; font-weight: 700; color: #264b5d; }
input, textarea, select { font: inherit; border: 1px solid #a9d7e5; border-radius: 6px; padding: 9px 10px; background: #fbfeff; }
.button { border: 0; border-radius: 6px; background: #0277bd; color: white; padding: 10px 14px; font-weight: 800; cursor: pointer; }
.button.small { padding: 8px 10px; font-size: 13px; }
.inline-form { margin: 0; }
.quick-actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.back { color: white; font-weight: 800; text-decoration: none; display: inline-block; margin-bottom: 10px; }
.empty { color: #607d8b; }
@media (max-width: 900px) { .grid, .score-filter { grid-template-columns: 1fr; } .layout { padding: 16px; } .filter-count { justify-items: start; } }
"""


class Handler(BaseHTTPRequestHandler):
    def send_text(self, content, status=200, content_type="text/html; charset=utf-8"):
        data = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/style.css":
            return self.send_text(CSS, content_type="text/css; charset=utf-8")
        if self.path.startswith("/item?"):
            params = parse_qs(urlparse(self.path).query)
            return self.send_text(render_item(params.get("id", [""])[0]))
        return self.send_text(render_home(parse_qs(urlparse(self.path).query)))

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        params = parse_qs(self.rfile.read(length).decode("utf-8"))
        if self.path == "/save":
            save_decision(params)
            self.send_response(303)
            self.send_header("Location", safe_return_url(params))
            self.end_headers()
            return
        if self.path == "/remap":
            canonical_food_id = params.get("canonical_food_id", [""])[0]
            reviewer_context = params.get("reviewer_context", [""])[0].strip()
            remap_scope = params.get("remap_scope", ["both"])[0]
            queue = load_remaining_queue()
            item = queue[queue["canonical_food_id"].eq(canonical_food_id)]
            if not item.empty:
                run_remap(item.iloc[0].to_dict(), reviewer_context, remap_scope)
            self.send_response(303)
            self.send_header("Location", f"/item?id={canonical_food_id}")
            self.end_headers()
            return
        return self.send_text("Not found", status=404)


def main():
    ensure_outputs()
    server = ThreadingHTTPServer(("127.0.0.1", 8766), Handler)
    print("Layered HITL UI running at http://127.0.0.1:8766")
    server.serve_forever()


if __name__ == "__main__":
    main()
