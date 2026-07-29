import argparse
import getpass
import hashlib
import json
import os
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from .sources import ROOT


OUT = ROOT / "outputs"
REFERENCE = OUT / "reference"
EMBEDDINGS = OUT / "embeddings"
DEFAULT_SENTENCE_EMBEDDING_MODEL = os.getenv("OPENAI_FOOD_CONCEPT_EMBEDDING_MODEL", "text-embedding-3-large")


IDENTITY_COLS = {
    "canonical_food_id",
    "canonical_name",
    "canonical_category",
    "hpp_food_count",
}

CHEMICAL_COUNT_COLS = {
    "foodatlas_compound_count",
    "foodatlas_food_count",
    "foodb_compound_count",
}

DISEASE_PATHWAY_COUNT_COLS = {
    "foodatlas_disease_edge_count",
    "foodatlas_positive_disease_edge_count",
    "foodatlas_negative_disease_edge_count",
    "hmdb_metabolite_count",
    "hmdb_biospecimen_count",
    "hmdb_disease_count",
    "hmdb_pathway_count",
}

PROCESSING_NUMERIC_COLS = {
    "ingredient_count",
    "additives_n",
    "nova_group",
    "completeness",
    "energy_kcal_100g",
    "fat_100g",
    "saturated_fat_100g",
    "carbohydrates_100g",
    "sugars_100g",
    "fiber_100g",
    "proteins_100g",
    "salt_100g",
    "sodium_100g",
    "openfoodfacts_match_score",
}

TEXT_EVIDENCE_COLS = [
    "canonical_category",
    "openfoodfacts_product_name",
    "openfoodfacts_category",
    "brands",
    "countries_en",
    "ingredients_text",
    "additives_tags",
    "allergens",
    "labels_en",
    "nutriscore_grade",
    "pnns_groups_1",
    "pnns_groups_2",
    "food_groups_en",
    "foodb_top_chemical_classes",
    "foodb_top_chemical_superclasses",
    "foodb_annotation_quality_counts",
    "hmdb_biospecimens",
    "hmdb_top_diseases",
    "hmdb_top_pathways",
]

CLUSTER_COLORS = [
    "#2563eb",
    "#dc2626",
    "#16a34a",
    "#9333ea",
    "#ea580c",
    "#0891b2",
    "#be123c",
    "#4d7c0f",
    "#7c3aed",
    "#ca8a04",
]

CATEGORY_SYMBOLS = [
    "circle",
    "diamond",
    "square",
    "cross",
    "x",
    "triangle-up",
    "triangle-down",
    "star",
    "hexagon",
    "pentagon",
    "hourglass",
    "bowtie",
    "asterisk",
    "circle-open",
    "diamond-open",
    "square-open",
]


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))


def _read_csv(path, **kwargs):
    path = Path(path)
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, **kwargs)


def _feature_matrix():
    path = REFERENCE / "canonical_food_feature_matrix.csv"
    if not path.exists():
        raise FileNotFoundError(
            "Missing canonical feature matrix. Run `pipeline build-reference` first."
        )
    return pd.read_csv(path)


def _nutrient_columns(feature):
    provenance = _read_csv(OUT / "nutrients/canonical_nutrient_provenance.csv")
    if provenance.empty or "nutrient_name" not in provenance:
        return []
    names = set(provenance["nutrient_name"].dropna().astype(str))
    return [col for col in feature.columns if col in names]


def _numeric_block(feature, columns):
    cols = [col for col in columns if col in feature.columns]
    if not cols:
        return np.zeros((len(feature), 0), dtype=float), []
    values = feature[cols].apply(pd.to_numeric, errors="coerce")
    values = values.fillna(values.median(numeric_only=True)).fillna(0)
    values = np.log1p(values.clip(lower=0))
    mean = values.mean(axis=0)
    std = values.std(axis=0).replace(0, 1)
    scaled = ((values - mean) / std).to_numpy(dtype=float)
    return scaled, cols


def _tokenize_evidence(value):
    if value is None or pd.isna(value):
        return []
    text = str(value).replace("|", " ").replace(",", " ").replace(":", " ")
    clean = []
    for token in text.lower().split():
        token = "".join(ch for ch in token if ch.isalnum() or ch in {"-", "_"})
        if len(token) >= 3:
            clean.append(token)
    return clean


def _hashed_text_block(feature, columns, dims=64):
    block = np.zeros((len(feature), dims), dtype=float)
    used_cols = [col for col in columns if col in feature.columns]
    for row_idx, (_, row) in enumerate(feature.iterrows()):
        counts = Counter()
        for col in used_cols:
            counts.update(_tokenize_evidence(row.get(col, "")))
        for token, count in counts.items():
            token_hash = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
            sign_hash = int(hashlib.md5(("salt:" + token).encode("utf-8")).hexdigest(), 16)
            idx = token_hash % dims
            sign = 1 if sign_hash % 2 == 0 else -1
            block[row_idx, idx] += sign * np.log1p(count)
    if dims:
        mean = block.mean(axis=0)
        std = block.std(axis=0)
        std[std == 0] = 1
        block = (block - mean) / std
    return block, [f"text_hash_{idx:02d}" for idx in range(dims)]


def _scale_block(block):
    if block.shape[1] == 0:
        return block
    return block / np.sqrt(block.shape[1])


def _pca_projection(matrix, dims=2):
    if matrix.size == 0:
        return np.zeros((matrix.shape[0], dims))
    centered = matrix - matrix.mean(axis=0)
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    components = vt[:dims].T
    projection = centered @ components
    if projection.shape[1] < dims:
        projection = np.pad(projection, ((0, 0), (0, dims - projection.shape[1])))
    return projection


def _kmeans(matrix, k=8, iterations=80):
    n = matrix.shape[0]
    if n == 0:
        return np.array([], dtype=int)
    k = max(1, min(k, n))
    norms = np.linalg.norm(matrix, axis=1)
    seeds = np.linspace(0, n - 1, k).astype(int)
    order = np.argsort(norms)
    centroids = matrix[order[seeds]].copy()
    labels = np.zeros(n, dtype=int)
    for _ in range(iterations):
        distances = ((matrix[:, None, :] - centroids[None, :, :]) ** 2).sum(axis=2)
        new_labels = distances.argmin(axis=1)
        if np.array_equal(new_labels, labels):
            break
        labels = new_labels
        for cluster in range(k):
            members = matrix[labels == cluster]
            if len(members):
                centroids[cluster] = members.mean(axis=0)
    return labels


def _top_available_nutrients(feature, row, nutrient_cols, limit=8):
    values = []
    for col in nutrient_cols:
        value = pd.to_numeric(row.get(col), errors="coerce")
        if pd.notna(value) and float(value) != 0:
            values.append(col)
    return values[:limit]


def _compact_list(value, limit=6):
    if value is None or pd.isna(value) or not str(value).strip():
        return []
    parts = []
    for chunk in str(value).replace(",", "|").split("|"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ":" in chunk:
            chunk = chunk.split(":", 1)[0].strip()
        if chunk and chunk not in parts:
            parts.append(chunk)
        if len(parts) >= limit:
            break
    return parts


def build_food_concept_sentences(feature=None):
    EMBEDDINGS.mkdir(parents=True, exist_ok=True)
    feature = _feature_matrix() if feature is None else feature
    nutrient_cols = _nutrient_columns(feature)
    rows = []
    for _, row in feature.iterrows():
        cid = row["canonical_food_id"]
        name = row.get("canonical_name", cid)
        category = row.get("canonical_category", "")
        nutrients = _top_available_nutrients(feature, row, nutrient_cols)
        classes = _compact_list(row.get("foodb_top_chemical_classes", ""))
        superclasses = _compact_list(row.get("foodb_top_chemical_superclasses", ""))
        biospecimens = _compact_list(row.get("hmdb_biospecimens", ""))
        diseases = _compact_list(row.get("hmdb_top_diseases", ""))
        pathways = _compact_list(row.get("hmdb_top_pathways", ""))
        compound_count = int(pd.to_numeric(row.get("foodb_compound_count", 0), errors="coerce") or 0)
        fa_compound_count = int(pd.to_numeric(row.get("foodatlas_compound_count", 0), errors="coerce") or 0)
        hmdb_count = int(pd.to_numeric(row.get("hmdb_metabolite_count", 0), errors="coerce") or 0)
        disease_count = int(pd.to_numeric(row.get("hmdb_disease_count", 0), errors="coerce") or 0)
        pathway_count = int(pd.to_numeric(row.get("hmdb_pathway_count", 0), errors="coerce") or 0)

        sentence = (
            f"{name} maps to canonical food concept {cid}"
            + (f" in category {category}" if category else "")
            + ". "
        )
        if nutrients:
            sentence += (
                "The harmonized nutrient layer has available values for "
                + ", ".join(nutrients)
                + ". "
            )
        else:
            sentence += "The harmonized nutrient layer has no available numeric nutrient values. "
        sentence += (
            f"The chemistry layer links this food to {compound_count} FooDB compounds "
            f"and {fa_compound_count} FoodAtlas compounds. "
        )
        if classes or superclasses:
            sentence += (
                "Prominent mapped chemical classes include "
                + ", ".join(classes + superclasses)
                + ". "
            )
        sentence += f"The HMDB bridge links this food to {hmdb_count} human metabolites"
        if biospecimens:
            sentence += " observed in " + ", ".join(biospecimens)
        sentence += ". "
        sentence += (
            f"The disease/pathway graph summarizes {disease_count} HMDB disease labels "
            f"and {pathway_count} HMDB pathway labels"
        )
        if diseases:
            sentence += ", with example disease annotations including " + ", ".join(diseases)
        if pathways:
            sentence += ", and example pathways including " + ", ".join(pathways)
        sentence += ". These graph-derived links are annotation features, not causal estimates."

        rows.append(
            {
                "canonical_food_id": cid,
                "canonical_name": name,
                "canonical_category": category,
                "concept_sentence": sentence,
                "nutrient_evidence_count": len(nutrients),
                "foodb_compound_count": compound_count,
                "foodatlas_compound_count": fa_compound_count,
                "hmdb_metabolite_count": hmdb_count,
                "hmdb_disease_count": disease_count,
                "hmdb_pathway_count": pathway_count,
            }
        )
    out = pd.DataFrame(rows)
    out_path = EMBEDDINGS / "canonical_food_concept_sentences.csv"
    out.to_csv(out_path, index=False)
    return out, out_path


def build_multimodal_vectors(k=8, text_dims=64):
    EMBEDDINGS.mkdir(parents=True, exist_ok=True)
    feature = _feature_matrix()
    nutrient_cols = _nutrient_columns(feature)
    processing_cols = [col for col in PROCESSING_NUMERIC_COLS if col in feature.columns]
    chemical_cols = [col for col in CHEMICAL_COUNT_COLS if col in feature.columns]
    disease_cols = [col for col in DISEASE_PATHWAY_COUNT_COLS if col in feature.columns]

    nutrient_block, nutrient_names = _numeric_block(feature, nutrient_cols)
    processing_block, processing_names = _numeric_block(feature, processing_cols)
    chemical_block, chemical_names = _numeric_block(feature, chemical_cols)
    disease_block, disease_names = _numeric_block(feature, disease_cols)
    text_block, text_names = _hashed_text_block(feature, TEXT_EVIDENCE_COLS, dims=text_dims)

    blocks = [
        ("nutrient", _scale_block(nutrient_block), nutrient_names),
        ("processing", _scale_block(processing_block), processing_names),
        ("chemical", _scale_block(chemical_block), chemical_names),
        ("metabolite_disease_pathway", _scale_block(disease_block), disease_names),
        ("text_evidence", _scale_block(text_block), text_names),
    ]
    combined = np.concatenate([block for _, block, _ in blocks if block.shape[1] > 0], axis=1)
    dim_names = []
    for block_name, _, names in blocks:
        dim_names.extend([f"{block_name}__{name}" for name in names])

    projection = _pca_projection(combined, dims=2)
    labels = _kmeans(combined, k=k)

    vector_cols = [f"v_{idx:04d}" for idx in range(combined.shape[1])]
    vectors = pd.DataFrame(combined, columns=vector_cols)
    vectors.insert(0, "cluster_id", labels)
    vectors.insert(0, "embedding_version", "multimodal_structured_v1")
    vectors.insert(0, "canonical_category", feature["canonical_category"])
    vectors.insert(0, "canonical_name", feature["canonical_name"])
    vectors.insert(0, "canonical_food_id", feature["canonical_food_id"])

    projection_df = feature[["canonical_food_id", "canonical_name", "canonical_category"]].copy()
    projection_df["x"] = projection[:, 0]
    projection_df["y"] = projection[:, 1]
    projection_df["cluster_id"] = labels

    dimension_map = pd.DataFrame(
        {
            "dimension": vector_cols,
            "feature_name": dim_names,
        }
    )
    sentence_df, sentence_path = build_food_concept_sentences(feature)

    vectors_path = EMBEDDINGS / "canonical_food_multimodal_vectors.parquet"
    projection_path = EMBEDDINGS / "embedding_space_projection.csv"
    dimension_path = EMBEDDINGS / "canonical_food_multimodal_vector_dimensions.csv"
    vectors.to_parquet(vectors_path, index=False)
    projection_df.to_csv(projection_path, index=False)
    dimension_map.to_csv(dimension_path, index=False)

    summary = {
        "embedding_version": "multimodal_structured_v1",
        "canonical_food_count": int(len(feature)),
        "combined_dimension_count": int(combined.shape[1]),
        "cluster_count": int(len(set(labels.tolist()))),
        "block_dimensions": {
            block_name: int(block.shape[1]) for block_name, block, _ in blocks
        },
        "outputs": {
            "vectors": str(vectors_path),
            "projection": str(projection_path),
            "dimensions": str(dimension_path),
            "sentences": str(sentence_path),
        },
    }
    _write_json(EMBEDDINGS / "multimodal_embedding_summary.json", summary)
    return summary


def build_pattern_discovery(top_n=12):
    EMBEDDINGS.mkdir(parents=True, exist_ok=True)
    projection_path = EMBEDDINGS / "embedding_space_projection.csv"
    if not projection_path.exists():
        build_multimodal_vectors()
    projection = pd.read_csv(projection_path)
    disease = _read_csv(REFERENCE / "canonical_food_disease_pathway_features.csv").fillna("")
    merged = projection.merge(disease, on=["canonical_food_id", "canonical_name", "canonical_category"], how="left")
    rows = []
    for cluster_id, group in merged.groupby("cluster_id"):
        disease_counts = Counter()
        pathway_counts = Counter()
        for _, row in group.iterrows():
            disease_counts.update(_compact_list(row.get("hmdb_top_diseases", ""), limit=20))
            pathway_counts.update(_compact_list(row.get("hmdb_top_pathways", ""), limit=20))
        examples = group.sort_values("canonical_name")["canonical_name"].head(8).tolist()
        for label, count in disease_counts.most_common(top_n):
            rows.append(
                {
                    "cluster_id": cluster_id,
                    "association_type": "hmdb_disease",
                    "label": label,
                    "food_count_in_cluster": int(len(group)),
                    "label_count_in_cluster": int(count),
                    "example_foods": " | ".join(examples),
                }
            )
        for label, count in pathway_counts.most_common(top_n):
            rows.append(
                {
                    "cluster_id": cluster_id,
                    "association_type": "hmdb_pathway",
                    "label": label,
                    "food_count_in_cluster": int(len(group)),
                    "label_count_in_cluster": int(count),
                    "example_foods": " | ".join(examples),
                }
            )
    out = pd.DataFrame(rows)
    out_path = EMBEDDINGS / "food_disease_pattern_discovery.csv"
    out.to_csv(out_path, index=False)
    summary = {
        "clusters": int(projection["cluster_id"].nunique()) if not projection.empty else 0,
        "pattern_rows": int(out.shape[0]),
        "output": str(out_path),
    }
    _write_json(EMBEDDINGS / "food_disease_pattern_discovery_summary.json", summary)
    return summary


def _categorical_embedding_figure(data, title, xaxis_title, yaxis_title):
    import plotly.graph_objects as go

    plot = data.copy()
    plot["cluster_label"] = "Cluster " + plot["cluster_id"].astype(str)
    cluster_values = sorted(plot["cluster_id"].dropna().unique().tolist())
    cluster_color = {
        value: CLUSTER_COLORS[idx % len(CLUSTER_COLORS)]
        for idx, value in enumerate(cluster_values)
    }
    categories = sorted(plot["canonical_category"].fillna("Uncategorized").astype(str).unique())
    category_symbol = {
        category: CATEGORY_SYMBOLS[idx % len(CATEGORY_SYMBOLS)]
        for idx, category in enumerate(categories)
    }
    plot["marker_color"] = plot["cluster_id"].map(cluster_color)
    plot["marker_symbol"] = (
        plot["canonical_category"].fillna("Uncategorized").astype(str).map(category_symbol)
    )

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=plot["x"],
            y=plot["y"],
            mode="markers",
            marker={
                "size": 9,
                "opacity": 0.82,
                "color": plot["marker_color"],
                "symbol": plot["marker_symbol"],
                "line": {"width": 0.4, "color": "rgba(20, 20, 20, 0.35)"},
            },
            customdata=plot[["canonical_name", "canonical_category"]].to_numpy(),
            hovertemplate="<b>%{customdata[0]}</b><br>Category: %{customdata[1]}<extra></extra>",
            showlegend=False,
            name="foods",
        )
    )
    for cluster_id in cluster_values:
        fig.add_trace(
            go.Scatter(
                x=[None],
                y=[None],
                mode="markers",
                marker={"size": 10, "color": cluster_color[cluster_id], "symbol": "circle"},
                name=f"Cluster {cluster_id}",
                legendgroup="cluster",
                legendgrouptitle_text="Cluster colors",
                showlegend=True,
            )
        )
    for category in categories:
        fig.add_trace(
            go.Scatter(
                x=[None],
                y=[None],
                mode="markers",
                marker={
                    "size": 10,
                    "color": "#6b7280",
                    "symbol": category_symbol[category],
                    "line": {"width": 0.5, "color": "#374151"},
                },
                name=category,
                legendgroup="category",
                legendgrouptitle_text="Category shapes",
                showlegend=True,
            )
        )
    fig.update_layout(
        template="plotly_white",
        title=title,
        xaxis_title=xaxis_title,
        yaxis_title=yaxis_title,
        legend_title_text="Categorical legends",
        margin={"l": 40, "r": 30, "t": 70, "b": 40},
    )
    return fig


def build_embedding_visualization():
    EMBEDDINGS.mkdir(parents=True, exist_ok=True)
    projection_path = EMBEDDINGS / "embedding_space_projection.csv"
    sentence_path = EMBEDDINGS / "canonical_food_concept_sentences.csv"
    if not projection_path.exists() or not sentence_path.exists():
        build_multimodal_vectors()
    projection = pd.read_csv(projection_path)
    sentences = pd.read_csv(sentence_path)
    data = projection.merge(
        sentences[["canonical_food_id", "concept_sentence"]],
        on="canonical_food_id",
        how="left",
    )
    fig = _categorical_embedding_figure(
        data,
        "Multimodal Canonical Food Concept Space",
        "PC1 of structured multimodal vector",
        "PC2 of structured multimodal vector",
    )
    out_path = EMBEDDINGS / "embedding_space_interactive.html"
    fig.write_html(out_path, include_plotlyjs="cdn", full_html=True)
    summary = {
        "food_count": int(data["canonical_food_id"].nunique()),
        "cluster_count": int(data["cluster_id"].nunique()),
        "output": str(out_path),
    }
    _write_json(EMBEDDINGS / "embedding_space_visualization_summary.json", summary)
    return summary


def _openai_client(force_prompt=False):
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ImportError("Install the openai package in the active environment first.") from exc
    api_key = "" if force_prompt else os.getenv("OPENAI_API_KEY")
    if not api_key:
        api_key = getpass.getpass(
            "Paste OpenAI API key for this run only. It will not be saved: "
        ).strip()
    if not api_key:
        raise RuntimeError("No OpenAI API key provided; sentence embeddings were not run.")
    return OpenAI(api_key=api_key)


def _embed_texts_openai(texts, model=DEFAULT_SENTENCE_EMBEDDING_MODEL, batch_size=64, force_prompt=False):
    client = _openai_client(force_prompt=force_prompt)
    vectors = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        response = client.embeddings.create(model=model, input=batch)
        vectors.extend([item.embedding for item in response.data])
    return np.array(vectors, dtype=np.float32)


def build_llm_sentence_embeddings(model=DEFAULT_SENTENCE_EMBEDDING_MODEL, batch_size=64, force_prompt=False):
    EMBEDDINGS.mkdir(parents=True, exist_ok=True)
    sentence_path = EMBEDDINGS / "canonical_food_concept_sentences.csv"
    if not sentence_path.exists():
        build_food_concept_sentences()
    sentences = pd.read_csv(sentence_path)
    texts = sentences["concept_sentence"].fillna("").astype(str).tolist()
    vectors = _embed_texts_openai(texts, model=model, batch_size=batch_size, force_prompt=force_prompt)
    projection = _pca_projection(vectors, dims=2)
    labels = _kmeans(vectors, k=8)

    vector_cols = [f"e_{idx:04d}" for idx in range(vectors.shape[1])]
    out = pd.DataFrame(vectors, columns=vector_cols)
    out.insert(0, "cluster_id", labels)
    out.insert(0, "embedding_model", model)
    out.insert(0, "canonical_category", sentences["canonical_category"])
    out.insert(0, "canonical_name", sentences["canonical_name"])
    out.insert(0, "canonical_food_id", sentences["canonical_food_id"])

    projection_df = sentences[["canonical_food_id", "canonical_name", "canonical_category"]].copy()
    projection_df["x"] = projection[:, 0]
    projection_df["y"] = projection[:, 1]
    projection_df["cluster_id"] = labels
    projection_df["embedding_model"] = model

    vectors_path = EMBEDDINGS / "canonical_food_sentence_embeddings.parquet"
    projection_path = EMBEDDINGS / "llm_embedding_space_projection.csv"
    html_path = EMBEDDINGS / "llm_embedding_space_interactive.html"
    out.to_parquet(vectors_path, index=False)
    projection_df.to_csv(projection_path, index=False)

    fig = _categorical_embedding_figure(
        projection_df,
        f"LLM Sentence Embedding Food Concept Space ({model})",
        "PC1 of sentence embedding",
        "PC2 of sentence embedding",
    )
    fig.write_html(html_path, include_plotlyjs="cdn", full_html=True)

    summary = {
        "embedding_model": model,
        "canonical_food_count": int(len(sentences)),
        "embedding_dimension_count": int(vectors.shape[1]),
        "cluster_count": int(len(set(labels.tolist()))),
        "outputs": {
            "vectors": str(vectors_path),
            "projection": str(projection_path),
            "visualization": str(html_path),
        },
    }
    _write_json(EMBEDDINGS / "llm_sentence_embedding_summary.json", summary)
    return summary


def build_all():
    embedding_summary = build_multimodal_vectors()
    pattern_summary = build_pattern_discovery()
    visualization_summary = build_embedding_visualization()
    summary = {
        "multimodal_embeddings": embedding_summary,
        "pattern_discovery": pattern_summary,
        "visualization": visualization_summary,
    }
    _write_json(EMBEDDINGS / "multimodal_food_concept_space_summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        nargs="?",
        default="all",
        choices=["sentences", "vectors", "patterns", "visualize", "llm-sentences", "all"],
    )
    parser.add_argument("--model", default=DEFAULT_SENTENCE_EMBEDDING_MODEL)
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()
    if args.command == "sentences":
        _, path = build_food_concept_sentences()
        print(path)
    elif args.command == "vectors":
        print(json.dumps(build_multimodal_vectors(), indent=2))
    elif args.command == "patterns":
        print(json.dumps(build_pattern_discovery(), indent=2))
    elif args.command == "visualize":
        print(json.dumps(build_embedding_visualization(), indent=2))
    elif args.command == "llm-sentences":
        print(json.dumps(build_llm_sentence_embeddings(args.model, args.batch_size, force_prompt=True), indent=2))
    else:
        print(json.dumps(build_all(), indent=2))


if __name__ == "__main__":
    main()
