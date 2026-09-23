"""Resumable local multilingual embeddings and source-balanced candidate retrieval."""

import argparse
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from .full_sources import OUT, REF
from .independent_pilot import digest, write_json


MODEL = "Qwen/Qwen3-Embedding-0.6B"
EMB = OUT / "embeddings"
MODEL_CACHE = Path("/private/tmp/diet-gen2-model-cache")
PROMPT = "Instruct: Retrieve a food composition reference matching the food identity, main ingredients, species, cooking state, preparation, and stated fat or sugar level.\nQuery: "


def download_model():
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    from huggingface_hub import HfApi, snapshot_download
    EMB.mkdir(parents=True, exist_ok=True)
    pin = EMB / "model_pin.json"
    revision = json.loads(pin.read_text())["revision"] if pin.exists() else HfApi().model_info(MODEL).sha
    path = snapshot_download(MODEL, revision=revision, cache_dir=MODEL_CACHE,
                             allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model", "1_Pooling/*"])
    write_json("model_pin.json", {"model": MODEL, "revision": revision, "local_path": path,
                                 "source_url": f"https://huggingface.co/{MODEL}/tree/{revision}"}, EMB)
    print(f"Downloaded and pinned {MODEL} at {revision}", flush=True)


def text_inputs():
    food = pd.read_csv(REF / "foods.csv").fillna("")
    identity = pd.read_csv(OUT / "identities.csv", dtype={"hpp_food_id": str}).fillna("")
    source_text = [f"{r.food_name}; {r.hebrew_name}".strip("; ") for r in food.itertuples()]
    query_text = [f"{r.product_name}; {r.hebrew_name}" for r in identity.itertuples()]
    return food, identity, source_text, query_text


def encode_resumable(model, texts, name, batch_size, prompt=""):
    stamp = hashlib.sha256(json.dumps({"texts": texts, "prompt": prompt}, ensure_ascii=False).encode()).hexdigest()
    path, state_path = EMB / f"{name}.npy", EMB / f"{name}_progress.json"
    if state_path.exists():
        state = json.loads(state_path.read_text())
        if state["input_hash"] != stamp:
            raise ValueError("Embedding inputs changed; use a new cache directory rather than mixing runs.")
        start = state["completed"]
        values = np.lib.format.open_memmap(path, mode="r+")
    else:
        start = 0
        values = np.lib.format.open_memmap(path, mode="w+", dtype=np.float32, shape=(len(texts), 1024))
    for offset in range(start, len(texts), batch_size):
        batch = model.encode(texts[offset:offset + batch_size], prompt=prompt,
                             batch_size=batch_size, normalize_embeddings=True,
                             convert_to_numpy=True, show_progress_bar=False)
        if not np.isfinite(batch).all() or batch.shape[1] != 1024:
            raise ValueError("Invalid model embeddings.")
        end = offset + len(batch)
        values[offset:end] = batch
        values.flush()
        write_json(state_path.name, {"input_hash": stamp, "completed": end, "total": len(texts)}, EMB)
        if offset == start or end % (batch_size * 8) == 0 or end == len(texts):
            print(f"{name}: {end}/{len(texts)}", flush=True)
    return values


def encode(batch_size=24, device=None):
    import torch
    import transformers
    from sentence_transformers import SentenceTransformer
    pin = json.loads((EMB / "model_pin.json").read_text())
    device = device or ("mps" if torch.backends.mps.is_available() else "cpu")
    kwargs = {"torch_dtype": torch.float16} if device == "mps" else {}
    torch.set_num_threads(4)
    model = SentenceTransformer(pin["local_path"], device=device,
                                model_kwargs=kwargs, tokenizer_kwargs={"padding_side": "left"})
    model.max_seq_length = 192
    food, identity, source_text, query_text = text_inputs()
    print(f"Embedding device={device}; {len(food)} references and {len(identity)} foods", flush=True)
    encode_resumable(model, source_text, "public", batch_size)
    encode_resumable(model, query_text, "hpp", batch_size, PROMPT)
    write_json("run_manifest.json", {"model": MODEL, "revision": pin["revision"], "device": device,
               "torch": torch.__version__, "transformers": transformers.__version__, "dimensions": 1024,
               "query_prompt": PROMPT, "max_sequence_length": model.max_seq_length,
               "source_id_order_sha256": hashlib.sha256("\n".join(food.source_food_key).encode()).hexdigest(),
               "hpp_id_order_sha256": hashlib.sha256("\n".join(identity.hpp_food_id).encode()).hexdigest(),
               "code_sha256": digest(Path(__file__)), "external_embedding_api_calls": 0,
               "input_hashes": {"foods.csv": digest(REF / "foods.csv"), "identities.csv": digest(OUT / "identities.csv")},
               "output_hashes": {name: digest(EMB / name) for name in ["public.npy", "hpp.npy"]}}, EMB)


def retrieve(top_k=8):
    food, identity, _, _ = text_inputs()
    for name in ["public", "hpp"]:
        state = json.loads((EMB / f"{name}_progress.json").read_text())
        if state["completed"] != state["total"]:
            raise ValueError("Embedding pass is incomplete.")
    public = np.load(EMB / "public.npy", mmap_mode="r")
    hpp = np.load(EMB / "hpp.npy", mmap_mode="r")
    if public.shape[0] != len(food) or hpp.shape[0] != len(identity):
        raise ValueError("Embedding table alignment mismatch.")
    exact = pd.read_csv(REF / "exact_identity_links.csv", dtype={"hpp_food_id": str})
    exact_groups = exact.groupby("hpp_food_id").source_food_key.apply(list).to_dict()
    lookup = {key: i for i, key in enumerate(food.source_food_key)}
    source_groups = {s: np.flatnonzero(food.source.eq(s).to_numpy()) for s in food.source.unique()}
    rows = []
    for start in range(0, len(identity), 128):
        scores = np.asarray(hpp[start:start + 128]) @ public.T
        for local, similarities in enumerate(scores):
            row = identity.iloc[start + local]
            chosen = set(np.argpartition(similarities, -top_k)[-top_k:].tolist())
            # Keep alternatives from each source even when a single source dominates.
            for indices in source_groups.values():
                chosen.update(indices[np.argpartition(similarities[indices], -3)[-3:]].tolist())
            exact_keys = set(exact_groups.get(row.hpp_food_id, []))
            chosen.update(lookup[key] for key in exact_keys)
            ranked = sorted(chosen, key=lambda i: (-float(similarities[i]), food.iloc[i].source_food_key))
            for rank, idx in enumerate(ranked, 1):
                donor = food.iloc[idx]
                rows.append({"hpp_food_id": row.hpp_food_id, "product_name": row.product_name,
                             "hebrew_name": row.hebrew_name, "candidate_rank": rank,
                             "source_food_key": donor.source_food_key, "candidate_name": donor.food_name,
                             "candidate_hebrew": donor.hebrew_name, "source_category": donor.category,
                             "embedding_cosine": float(similarities[idx]),
                             "exact_identity": donor.source_food_key in exact_keys,
                             "source": donor.source})
    candidates = pd.DataFrame(rows)
    candidates.to_csv(OUT / "mapping_candidates.csv", index=False)
    write_json("retrieval_summary.json", {"foods": len(identity), "candidates": len(candidates),
               "model": MODEL, "revision": json.loads((EMB / "model_pin.json").read_text())["revision"],
               "top_k_global": top_k, "per_source_minimum": 3, "all_exact_candidates_retained": True,
               "status": "candidates_not_accepted_matches", "code_sha256": digest(Path(__file__))}, OUT)
    print(f"Saved {len(candidates)} candidates for {len(identity)} foods", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["download", "encode", "retrieve"])
    parser.add_argument("--batch-size", type=int, default=24)
    parser.add_argument("--device", choices=["cpu", "mps"])
    args = parser.parse_args()
    if args.command == "download":
        download_model()
    elif args.command == "encode":
        encode(args.batch_size, args.device)
    else:
        retrieve()
