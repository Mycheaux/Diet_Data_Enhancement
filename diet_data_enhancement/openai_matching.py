import argparse
import getpass
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
from openai import OpenAI

from .mapping import confidence_tier
from .sources import ROOT, load_hpp_foods, load_public_foods


OUT = ROOT / "outputs/openai"
EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")
VALIDATION_MODEL = os.getenv("OPENAI_VALIDATION_MODEL", "gpt-5.5")


def _client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        api_key = getpass.getpass(
            "Enter OpenAI API key for this run only. It will not be saved: "
        ).strip()
    if not api_key:
        raise RuntimeError("No OpenAI API key provided; OpenAI matching was not run.")
    return OpenAI(api_key=api_key)


def embedding_text(row, name_col="food_name", category_col="category"):
    parts = [str(row.get(name_col, "") or "")]
    category = str(row.get(category_col, "") or "")
    if category:
        parts.append(f"category: {category}")
    return " | ".join(parts)


def embed_texts(texts, model=EMBEDDING_MODEL, batch_size=128):
    client = _client()
    vectors = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        response = client.embeddings.create(model=model, input=batch)
        vectors.extend([item.embedding for item in response.data])
    return np.array(vectors, dtype=np.float32)


def cosine_matrix(left, right):
    left_norm = left / np.clip(np.linalg.norm(left, axis=1, keepdims=True), 1e-12, None)
    right_norm = right / np.clip(np.linalg.norm(right, axis=1, keepdims=True), 1e-12, None)
    return left_norm @ right_norm.T


def run_embedding_match(limit_hpp=None, limit_public=None, top_k=5):
    OUT.mkdir(parents=True, exist_ok=True)
    hpp = load_hpp_foods()
    public = load_public_foods()
    if limit_hpp:
        hpp = hpp.head(limit_hpp)
    if limit_public:
        public = public.head(limit_public)

    hpp_texts = [embedding_text(row) for row in hpp.to_dict("records")]
    public_texts = [embedding_text(row) for row in public.to_dict("records")]
    hpp_vectors = embed_texts(hpp_texts)
    public_vectors = embed_texts(public_texts)
    scores = cosine_matrix(hpp_vectors, public_vectors)

    rows = []
    public_records = public.to_dict("records")
    for hpp_idx, hpp_row in enumerate(hpp.to_dict("records")):
        top_indices = np.argsort(scores[hpp_idx])[-top_k:][::-1]
        for rank, source_idx in enumerate(top_indices, start=1):
            score = float(scores[hpp_idx, source_idx])
            candidate = public_records[source_idx]
            rows.append(
                {
                    "hpp_food_id": hpp_row["hpp_food_id"],
                    "hpp_food_name": hpp_row["food_name"],
                    "hpp_short_description": hpp_row["short_description"],
                    "hpp_category": hpp_row["category"],
                    "candidate_rank": rank,
                    "embedding_score": round(score, 6),
                    "confidence": confidence_tier(score),
                    "source": candidate["source"],
                    "source_food_id": candidate["source_food_id"],
                    "matched_food_name": candidate["food_name"],
                    "matched_category": candidate.get("category", ""),
                    "stage": "openai_embedding_retrieval",
                }
            )
    out_path = OUT / "openai_embedding_candidates.csv"
    pd.DataFrame(rows).to_csv(out_path, index=False)
    return out_path


def validate_candidates(candidates_path=None, limit=50):
    candidates_path = Path(candidates_path or OUT / "openai_embedding_candidates.csv")
    candidates = pd.read_csv(candidates_path)
    best = candidates[candidates["candidate_rank"] == 1].head(limit)
    client = _client()
    rows = []
    for _, row in best.iterrows():
        prompt = {
            "task": "Judge whether two food descriptions refer to the same food for nutrient mapping.",
            "hpp_food": {
                "name": row["hpp_food_name"],
                "original_entry": row.get("hpp_short_description", ""),
                "category": row.get("hpp_category", ""),
            },
            "candidate_food": {
                "name": row["matched_food_name"],
                "source": row["source"],
                "category": row.get("matched_category", ""),
            },
            "output_json_schema": {
                "equivalent": "yes | no | uncertain",
                "confidence": "high | medium | low",
                "reason": "short reason",
            },
        }
        response = client.responses.create(
            model=VALIDATION_MODEL,
            input=[
                {
                    "role": "user",
                    "content": (
                        "Return only JSON. Be strict: foods must be close enough "
                        "that nutrient values could be transferred.\n\n"
                        + json.dumps(prompt, ensure_ascii=False)
                    ),
                }
            ],
        )
        text = response.output_text.strip()
        try:
            verdict = json.loads(text)
        except json.JSONDecodeError:
            verdict = {"equivalent": "uncertain", "confidence": "low", "reason": text[:500]}
        rows.append({**row.to_dict(), **{f"gpt_{k}": v for k, v in verdict.items()}})
    out_path = OUT / "gpt_validated_candidates.csv"
    pd.DataFrame(rows).to_csv(out_path, index=False)
    return out_path


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    match = sub.add_parser("embed-match")
    match.add_argument("--limit-hpp", type=int)
    match.add_argument("--limit-public", type=int)
    match.add_argument("--top-k", type=int, default=5)
    validate = sub.add_parser("validate")
    validate.add_argument("--candidates")
    validate.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    try:
        if args.command == "embed-match":
            print(run_embedding_match(args.limit_hpp, args.limit_public, args.top_k))
        elif args.command == "validate":
            print(validate_candidates(args.candidates, args.limit))
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    main()
