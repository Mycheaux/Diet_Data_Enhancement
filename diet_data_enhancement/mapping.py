from dataclasses import dataclass

import pandas as pd

from .text import confidence_tier, name_similarity, normalize_text, tokens, unicode_name_similarity


@dataclass
class CandidateIndex:
    records: list
    token_to_indices: dict


def build_index(candidates):
    records = candidates.to_dict("records")
    token_to_indices = {}
    for idx, record in enumerate(records):
        record["_norm"] = normalize_text(record["food_name"])
        record["_tokens"] = set(tokens(record["food_name"]))
        for token in record["_tokens"]:
            token_to_indices.setdefault(token, set()).add(idx)
    return CandidateIndex(records=records, token_to_indices=token_to_indices)


def candidate_indices_for(query, index, max_pool=500):
    query_tokens = set(tokens(query))
    if not query_tokens:
        return range(min(len(index.records), max_pool))
    counts = {}
    for token in query_tokens:
        for idx in index.token_to_indices.get(token, ()):
            counts[idx] = counts.get(idx, 0) + 1
    ranked = sorted(counts, key=lambda idx: counts[idx], reverse=True)
    if not ranked:
        return range(min(len(index.records), max_pool))
    return ranked[:max_pool]


def find_candidates(query, index, top_k=5):
    scored = []
    for idx in candidate_indices_for(query, index):
        record = index.records[idx]
        score = name_similarity(query, record["food_name"])
        if score > 0:
            scored.append((score, record))
    scored.sort(key=lambda item: item[0], reverse=True)
    rows = []
    for rank, (score, record) in enumerate(scored[:top_k], start=1):
        rows.append(
            {
                "candidate_rank": rank,
                "match_score": score,
                "confidence": confidence_tier(score),
                "source": record["source"],
                "source_food_id": record["source_food_id"],
                "matched_food_name": record["food_name"],
                "matched_category": record.get("category", ""),
            }
        )
    return rows


def _best_language_score(food, record):
    english_score = name_similarity(food.get("food_name", ""), record.get("food_name", ""))
    hebrew_score = 0.0
    hpp_hebrew = food.get("hebrew_name", "")
    source_hebrew = record.get("hebrew_name", "")
    if hpp_hebrew and source_hebrew:
        hebrew_score = unicode_name_similarity(hpp_hebrew, source_hebrew)
    if hebrew_score > english_score:
        return hebrew_score, english_score, hebrew_score, "hebrew"
    return english_score, english_score, hebrew_score, "english"


def find_candidates_for_food(food, index, top_k=5):
    query = food.get("food_name", "")
    scored = []
    for idx in candidate_indices_for(query, index):
        record = index.records[idx]
        score, english_score, hebrew_score, match_language = _best_language_score(food, record)
        if score > 0:
            scored.append((score, english_score, hebrew_score, match_language, record))
    scored.sort(key=lambda item: item[0], reverse=True)
    rows = []
    for rank, (score, english_score, hebrew_score, match_language, record) in enumerate(scored[:top_k], start=1):
        rows.append(
            {
                "candidate_rank": rank,
                "match_score": score,
                "english_match_score": english_score,
                "hebrew_match_score": hebrew_score,
                "match_language": match_language,
                "confidence": confidence_tier(score),
                "source": record["source"],
                "source_food_id": record["source_food_id"],
                "matched_food_name": record["food_name"],
                "matched_category": record.get("category", ""),
                "matched_hebrew_name": record.get("hebrew_name", ""),
            }
        )
    return rows


def map_hpp_to_public(hpp_foods, public_foods, top_k=5):
    index = build_index(public_foods)
    rows = []
    for _, food in hpp_foods.iterrows():
        food_record = food.to_dict()
        candidates = find_candidates_for_food(food_record, index, top_k=top_k)
        if not candidates:
            candidates = [
                {
                    "candidate_rank": 1,
                    "match_score": 0.0,
                    "english_match_score": 0.0,
                    "hebrew_match_score": 0.0,
                    "match_language": "none",
                    "confidence": "review",
                    "source": "",
                    "source_food_id": "",
                    "matched_food_name": "",
                    "matched_category": "",
                    "matched_hebrew_name": "",
                }
            ]
        for candidate in candidates:
            rows.append(
                {
                    "hpp_food_id": food["hpp_food_id"],
                    "hpp_food_name": food["food_name"],
                    "hpp_short_description": food["short_description"],
                    "hpp_category": food["category"],
                    **candidate,
                    "stage": "public_fcdb_low_effort",
                    "needs_human_review": candidate["confidence"] in {"low", "review"},
                }
            )
    return pd.DataFrame(rows)


def make_review_queue(mapping_df):
    best = mapping_df.sort_values(["hpp_food_id", "candidate_rank"]).groupby("hpp_food_id").head(1)
    queue = best[best["confidence"].isin(["low", "review"])].copy()
    queue["review_status"] = "pending"
    queue["human_food_name"] = ""
    queue["human_category"] = ""
    queue["human_notes"] = ""
    return queue
