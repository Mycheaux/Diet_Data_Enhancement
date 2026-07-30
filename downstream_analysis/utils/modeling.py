"""Simple supervised ML evaluation for TRE-side diet prediction tasks."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import pearsonr
from sklearn.base import clone
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Lasso, LinearRegression, LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    f1_score,
    mean_squared_error,
    precision_recall_curve,
    r2_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedShuffleSplit, ShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .preprocess import read_table, write_table


def align_x_y(
    x: pd.DataFrame,
    y: pd.DataFrame,
    target_col: str,
    id_col: str = "participant_id",
    time_col: str | None = "time_window",
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    keys = [id_col]
    if time_col and time_col in x.columns and time_col in y.columns:
        keys.append(time_col)
    merged = x.merge(y[keys + [target_col]], on=keys, how="inner")
    y_out = merged[target_col]
    drop = set(keys + [target_col])
    x_out = merged[[col for col in merged.columns if col not in drop]]
    feature_cols = [col for col in x_out.columns if pd.api.types.is_numeric_dtype(x_out[col])]
    x_out = x_out[feature_cols]
    meta = merged[keys].copy()
    return x_out, y_out, meta


def infer_task_type(y: pd.Series) -> str:
    y_nonnull = y.dropna()
    if y_nonnull.empty:
        raise ValueError("Target has no non-missing values.")
    unique = y_nonnull.nunique()
    if unique <= 2:
        return "binary"
    if pd.api.types.is_numeric_dtype(y_nonnull) and unique > 10:
        return "continuous"
    return "multiclass"


def available_models(task_type: str) -> dict:
    if task_type == "continuous":
        return {
            "linear_regression": Pipeline([("impute", SimpleImputer()), ("scale", StandardScaler()), ("model", LinearRegression())]),
            "ridge": Pipeline([("impute", SimpleImputer()), ("scale", StandardScaler()), ("model", Ridge(alpha=1.0))]),
            "lasso": Pipeline([("impute", SimpleImputer()), ("scale", StandardScaler()), ("model", Lasso(alpha=0.01, max_iter=10000))]),
            "rf_regression": Pipeline([("impute", SimpleImputer()), ("model", RandomForestRegressor(n_estimators=300, random_state=0, n_jobs=-1))]),
        }
    return {
        "logistic_regression": Pipeline(
            [
                ("impute", SimpleImputer()),
                ("scale", StandardScaler()),
                ("model", LogisticRegression(max_iter=5000, class_weight="balanced")),
            ]
        ),
        "rf_classification": Pipeline(
            [
                ("impute", SimpleImputer()),
                ("model", RandomForestClassifier(n_estimators=300, random_state=0, n_jobs=-1, class_weight="balanced")),
            ]
        ),
    }


def _classification_metrics(y_true, y_pred, y_score, task_type: str) -> dict:
    metrics = {
        "accuracy": accuracy_score(y_true, y_pred),
        "f1_macro": f1_score(y_true, y_pred, average="macro", zero_division=0),
    }
    if task_type == "binary":
        try:
            metrics["auroc"] = roc_auc_score(y_true, y_score)
        except Exception:
            metrics["auroc"] = np.nan
        try:
            metrics["auprc"] = average_precision_score(y_true, y_score)
        except Exception:
            metrics["auprc"] = np.nan
    else:
        metrics["auroc"] = np.nan
        metrics["auprc"] = np.nan
    return metrics


def _regression_metrics(y_true, y_pred) -> dict:
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    try:
        pearson = pearsonr(y_true, y_pred).statistic
    except Exception:
        pearson = np.nan
    return {
        "r2": r2_score(y_true, y_pred),
        "rmse": rmse,
        "pearson_r": pearson,
    }


def evaluate_models(
    x: pd.DataFrame,
    y: pd.Series,
    task_type: str | None = None,
    models: list[str] | None = None,
    n_splits: int = 5,
    test_size: float = 0.2,
    random_state: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run repeated 80/20 train-test splits and average metrics."""
    valid = y.notna()
    x = x.loc[valid].copy()
    y = y.loc[valid].copy()
    task_type = task_type or infer_task_type(y)
    model_bank = available_models(task_type)
    selected = models or list(model_bank)
    missing = [m for m in selected if m not in model_bank]
    if missing:
        raise ValueError(f"Unsupported model(s) for {task_type}: {missing}")
    splitter = (
        StratifiedShuffleSplit(n_splits=n_splits, test_size=test_size, random_state=random_state)
        if task_type in {"binary", "multiclass"}
        else ShuffleSplit(n_splits=n_splits, test_size=test_size, random_state=random_state)
    )
    split_iter = splitter.split(x, y) if task_type in {"binary", "multiclass"} else splitter.split(x)
    rows = []
    for fold, (train_idx, test_idx) in enumerate(split_iter, start=1):
        x_train, x_test = x.iloc[train_idx], x.iloc[test_idx]
        y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]
        for model_name in selected:
            estimator = clone(model_bank[model_name])
            estimator.fit(x_train, y_train)
            pred = estimator.predict(x_test)
            if task_type == "continuous":
                metrics = _regression_metrics(y_test, pred)
            else:
                if hasattr(estimator, "predict_proba"):
                    proba = estimator.predict_proba(x_test)
                    score = proba[:, 1] if proba.shape[1] == 2 else proba.max(axis=1)
                elif hasattr(estimator, "decision_function"):
                    score = estimator.decision_function(x_test)
                else:
                    score = pred
                metrics = _classification_metrics(y_test, pred, score, task_type)
            rows.append({"fold": fold, "model": model_name, "task_type": task_type, **metrics})
    fold_metrics = pd.DataFrame(rows)
    metric_cols = [c for c in fold_metrics.columns if c not in {"fold", "model", "task_type"}]
    summary = (
        fold_metrics.groupby(["model", "task_type"])[metric_cols]
        .agg(["mean", "std"])
        .reset_index()
    )
    summary.columns = ["_".join([str(x) for x in col if x]) for col in summary.columns]
    return fold_metrics, summary


def run_prediction_from_files(
    x_path: str | Path,
    y_path: str | Path,
    target_col: str,
    output_dir: str | Path,
    id_col: str = "participant_id",
    time_col: str | None = "time_window",
    task_type: str | None = None,
    models: list[str] | None = None,
    n_splits: int = 5,
    test_size: float = 0.2,
) -> dict:
    x_table = read_table(x_path)
    y_table = read_table(y_path)
    x, y, meta = align_x_y(x_table, y_table, target_col=target_col, id_col=id_col, time_col=time_col)
    fold_metrics, summary = evaluate_models(
        x,
        y,
        task_type=task_type,
        models=models,
        n_splits=n_splits,
        test_size=test_size,
    )
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    fold_path = output_dir / f"{target_col}_fold_metrics.csv"
    summary_path = output_dir / f"{target_col}_summary_metrics.csv"
    write_table(fold_metrics, fold_path)
    write_table(summary, summary_path)
    run_summary = {
        "x_path": str(x_path),
        "y_path": str(y_path),
        "target_col": target_col,
        "aligned_rows": int(len(x)),
        "feature_count": int(x.shape[1]),
        "task_type": task_type or infer_task_type(y),
        "fold_metrics": str(fold_path),
        "summary_metrics": str(summary_path),
    }
    (output_dir / f"{target_col}_run_summary.json").write_text(json.dumps(run_summary, indent=2), encoding="utf-8")
    return run_summary
