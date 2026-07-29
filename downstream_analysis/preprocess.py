"""Preprocess TRE diet logs into participant-level feature tables.

This module is designed to run inside TRE. It expects a participant diet-event
table and joins it to food-level reference tables created outside TRE.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


ID_COL_DEFAULT = "participant_id"
FOOD_COL_DEFAULT = "hpp_food_id"
GRAMS_COL_DEFAULT = "grams_consumed"
TIME_COL_DEFAULT = "timestamp"


def read_table(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    if path.suffix.lower() in {".csv", ".gz"}:
        return pd.read_csv(path)
    if path.suffix.lower() in {".tsv", ".txt"}:
        return pd.read_csv(path, sep="\t")
    raise ValueError(f"Unsupported table format: {path}")


def write_table(df: pd.DataFrame, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".parquet":
        df.to_parquet(path, index=False)
    else:
        df.to_csv(path, index=False)
    return path


def infer_feature_columns(df: pd.DataFrame, exclude: Iterable[str]) -> list[str]:
    exclude = set(exclude)
    numeric = df.select_dtypes(include=[np.number]).columns
    return [col for col in numeric if col not in exclude]


def add_time_window(
    diet: pd.DataFrame,
    time_col: str | None = TIME_COL_DEFAULT,
    window: str = "participant",
) -> pd.DataFrame:
    """Add a `time_window` column for participant-level or calendar windows."""
    out = diet.copy()
    if window == "participant" or not time_col or time_col not in out.columns:
        out["time_window"] = "all"
        return out
    ts = pd.to_datetime(out[time_col], errors="coerce")
    if window == "day":
        out["time_window"] = ts.dt.to_period("D").astype(str)
    elif window == "week":
        out["time_window"] = ts.dt.to_period("W").astype(str)
    elif window == "month":
        out["time_window"] = ts.dt.to_period("M").astype(str)
    elif window == "year":
        out["time_window"] = ts.dt.to_period("Y").astype(str)
    else:
        raise ValueError("window must be one of participant, day, week, month, year")
    out["time_window"] = out["time_window"].fillna("missing_time")
    return out


def aggregate_food_features(
    diet_events: pd.DataFrame,
    food_features: pd.DataFrame,
    feature_cols: list[str] | None = None,
    id_col: str = ID_COL_DEFAULT,
    food_col: str = FOOD_COL_DEFAULT,
    grams_col: str = GRAMS_COL_DEFAULT,
    time_col: str | None = TIME_COL_DEFAULT,
    window: str = "participant",
    amount_scaling: str = "per_100g",
    output_prefix: str = "",
) -> pd.DataFrame:
    """Aggregate food-level numeric features to participant/time-window features.

    `amount_scaling='per_100g'` uses event exposure = food_feature * grams / 100.
    `amount_scaling='weighted_mean'` uses grams-weighted mean feature values.
    """
    if id_col not in diet_events.columns:
        raise ValueError(f"Missing participant id column: {id_col}")
    if food_col not in diet_events.columns or food_col not in food_features.columns:
        raise ValueError(f"Food id column {food_col!r} must exist in both tables.")
    if grams_col not in diet_events.columns:
        raise ValueError(f"Missing grams column: {grams_col}")
    diet = add_time_window(diet_events, time_col=time_col, window=window)
    diet = diet[[id_col, "time_window", food_col, grams_col]].copy()
    diet[grams_col] = pd.to_numeric(diet[grams_col], errors="coerce").fillna(0)
    food_features = food_features.copy()
    food_features[food_col] = food_features[food_col].astype(diet[food_col].dtype, copy=False)
    if feature_cols is None:
        feature_cols = infer_feature_columns(food_features, exclude=[food_col])
    merged = diet.merge(food_features[[food_col] + feature_cols], on=food_col, how="left")
    values = merged[feature_cols].apply(pd.to_numeric, errors="coerce").fillna(0)
    grams = merged[grams_col].to_numpy()[:, None]
    if amount_scaling == "per_100g":
        scaled = values.to_numpy(dtype=float) * grams / 100.0
        tmp = pd.DataFrame(scaled, columns=[f"{output_prefix}{c}" for c in feature_cols])
        tmp[id_col] = merged[id_col].values
        tmp["time_window"] = merged["time_window"].values
        out = tmp.groupby([id_col, "time_window"], as_index=False).sum()
    elif amount_scaling == "weighted_mean":
        scaled = values.to_numpy(dtype=float) * grams
        tmp = pd.DataFrame(scaled, columns=[f"{output_prefix}{c}" for c in feature_cols])
        tmp[id_col] = merged[id_col].values
        tmp["time_window"] = merged["time_window"].values
        tmp["_grams"] = merged[grams_col].values
        grouped = tmp.groupby([id_col, "time_window"], as_index=False).sum()
        feature_out = [f"{output_prefix}{c}" for c in feature_cols]
        denom = grouped["_grams"].replace(0, np.nan)
        grouped[feature_out] = grouped[feature_out].div(denom, axis=0).fillna(0)
        out = grouped.drop(columns=["_grams"])
    else:
        raise ValueError("amount_scaling must be 'per_100g' or 'weighted_mean'")
    return out


def aggregate_embeddings(
    diet_events: pd.DataFrame,
    food_embeddings: pd.DataFrame,
    id_col: str = ID_COL_DEFAULT,
    food_col: str = FOOD_COL_DEFAULT,
    grams_col: str = GRAMS_COL_DEFAULT,
    time_col: str | None = TIME_COL_DEFAULT,
    window: str = "participant",
    embedding_prefix: str = "embedding_",
    output_prefix: str = "food_card_",
) -> pd.DataFrame:
    """Create amount-weighted participant embeddings from food embeddings."""
    embedding_cols = [col for col in food_embeddings.columns if col.startswith(embedding_prefix)]
    if not embedding_cols:
        raise ValueError(f"No embedding columns found with prefix {embedding_prefix!r}")
    out = aggregate_food_features(
        diet_events=diet_events,
        food_features=food_embeddings[[food_col] + embedding_cols],
        feature_cols=embedding_cols,
        id_col=id_col,
        food_col=food_col,
        grams_col=grams_col,
        time_col=time_col,
        window=window,
        amount_scaling="weighted_mean",
        output_prefix=output_prefix,
    )
    return out


def build_design_matrix(
    diet_events_path: str | Path,
    food_reference_path: str | Path,
    output_path: str | Path,
    feature_mode: str = "enriched",
    id_col: str = ID_COL_DEFAULT,
    food_col: str = FOOD_COL_DEFAULT,
    grams_col: str = GRAMS_COL_DEFAULT,
    time_col: str | None = TIME_COL_DEFAULT,
    window: str = "participant",
    feature_cols: list[str] | None = None,
) -> dict:
    """Build participant-level X table from diet events and food-level features."""
    diet = read_table(diet_events_path)
    ref = read_table(food_reference_path)
    if feature_mode == "embedding":
        x = aggregate_embeddings(
            diet,
            ref,
            id_col=id_col,
            food_col=food_col,
            grams_col=grams_col,
            time_col=time_col,
            window=window,
        )
    elif feature_mode in {"enriched", "kg"}:
        x = aggregate_food_features(
            diet,
            ref,
            feature_cols=feature_cols,
            id_col=id_col,
            food_col=food_col,
            grams_col=grams_col,
            time_col=time_col,
            window=window,
            amount_scaling="per_100g" if feature_mode == "enriched" else "weighted_mean",
            output_prefix=f"{feature_mode}_",
        )
    else:
        raise ValueError("feature_mode must be one of: enriched, embedding, kg")
    output_path = write_table(x, output_path)
    summary = {
        "feature_mode": feature_mode,
        "diet_events_path": str(diet_events_path),
        "food_reference_path": str(food_reference_path),
        "output_path": str(output_path),
        "rows": int(len(x)),
        "columns": int(x.shape[1]),
        "participants": int(x[id_col].nunique()) if id_col in x else None,
        "window": window,
    }
    summary_path = Path(output_path).with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary

