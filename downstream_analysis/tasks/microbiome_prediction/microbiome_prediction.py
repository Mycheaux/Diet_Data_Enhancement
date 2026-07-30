"""Microbiome prediction comparison for TRE-side analyses.

This task builds participant/time-window diet design matrices for three feature
sets and evaluates the same microbiome targets against each one:

1. full_data: KG/downstream feature export, intended to include nutrient,
   product, chemical, metabolite, disease, and pathway features.
2. enriched_data: de novo enriched HPP per-100 g food features.
3. nutrimatch_only: NutriMatch-based per-100 g nutrient features.
4. food_card_embedding: food-card text embedding vectors aggregated by intake.

The microbiome target table is expected to be wide: one row per participant or
participant/time window and one or more numeric microbiome targets, such as URS
or MetaPhlAn abundance columns.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from downstream_analysis.modeling import run_prediction_from_files
from downstream_analysis.preprocess import add_time_window, build_design_matrix, read_table, write_table


@dataclass(frozen=True)
class FeatureSet:
    name: str
    path: Path
    feature_mode: str
    description: str


def default_feature_sets(project_root: Path) -> list[FeatureSet]:
    """Return the three planned microbiome comparison inputs."""
    return [
        FeatureSet(
            name="full_data",
            path=project_root / "outputs" / "downstream_features" / "denovo" / "microbiome" / "hpp_downstream_feature_table.csv",
            feature_mode="kg",
            description="Full KG/downstream microbiome feature export.",
        ),
        FeatureSet(
            name="enriched_data",
            path=project_root / "outputs" / "enhanced_hpp" / "1.denovo" / "hpp_feature_matrix_per_100g.csv",
            feature_mode="enriched",
            description="De novo enriched HPP per-100 g food features.",
        ),
        FeatureSet(
            name="nutrimatch_only",
            path=project_root / "outputs" / "enhanced_hpp" / "2.nutrimatch_based" / "hpp_feature_matrix_per_100g.csv",
            feature_mode="enriched",
            description="NutriMatch-based per-100 g nutrient features.",
        ),
        FeatureSet(
            name="food_card_embedding",
            path=project_root
            / "outputs"
            / "food_card"
            / "denovo"
            / "embeddings"
            / "hpp_food_card_embeddings_full_biology_text_text_embedding_3_large.parquet",
            feature_mode="embedding",
            description="Amount-weighted de novo food-card text embedding features.",
        ),
    ]


def load_feature_sets(config: dict[str, Any], project_root: Path) -> list[FeatureSet]:
    """Load feature-set definitions from config or use defaults."""
    custom = config.get("feature_sets")
    if not custom:
        return default_feature_sets(project_root)
    out: list[FeatureSet] = []
    for item in custom:
        out.append(
            FeatureSet(
                name=item["name"],
                path=(project_root / item["path"]).resolve() if not Path(item["path"]).is_absolute() else Path(item["path"]),
                feature_mode=item.get("feature_mode", "enriched"),
                description=item.get("description", ""),
            )
        )
    return out


def infer_microbiome_targets(
    microbiome_table: pd.DataFrame,
    id_col: str = "participant_id",
    time_col: str | None = "time_window",
    requested_targets: list[str] | None = None,
    max_targets: int | None = None,
) -> list[str]:
    """Select numeric microbiome target columns from a wide target table."""
    if requested_targets:
        missing = [target for target in requested_targets if target not in microbiome_table.columns]
        if missing:
            raise ValueError(f"Requested target columns are missing from microbiome table: {missing}")
        return requested_targets
    exclude = {id_col}
    if time_col:
        exclude.add(time_col)
    metadata_like = {
        "collection_timestamp",
        "collection_date",
        "timezone",
        "sample_name",
        "run_name",
        "wgs_dna_code",
    }
    exclude.update(metadata_like)
    targets = [
        col
        for col in microbiome_table.select_dtypes(include="number").columns
        if col not in exclude
    ]
    if max_targets is not None:
        targets = targets[:max_targets]
    if not targets:
        raise ValueError("No numeric microbiome targets found. Pass explicit target columns in the config.")
    return targets


def normalize_microbiome_targets(
    microbiome_targets_path: str | Path,
    output_path: str | Path,
    id_col: str = "participant_id",
    time_col: str | None = "time_window",
    target_time_col: str | None = "collection_timestamp",
    window: str = "participant",
    targets: list[str] | None = None,
    max_targets: int | None = None,
) -> tuple[Path, list[str]]:
    """Copy selected target columns to a modeling-ready target table."""
    y = read_table(microbiome_targets_path)
    if time_col and time_col not in y.columns:
        y = add_time_window(y, time_col=target_time_col, window=window)
    selected = infer_microbiome_targets(
        y,
        id_col=id_col,
        time_col=time_col,
        requested_targets=targets,
        max_targets=max_targets,
    )
    keep = [id_col]
    if time_col and time_col in y.columns:
        keep.append(time_col)
    keep.extend(selected)
    output_path = write_table(y[keep], output_path)
    return output_path, selected


def run_microbiome_comparison(
    config: dict[str, Any],
    project_root: Path,
) -> dict[str, Any]:
    """Build X tables and run all configured microbiome prediction comparisons."""
    output_dir = Path(config.get("output_dir", project_root / "downstream_analysis" / "tasks" / "microbiome_prediction" / "outputs"))
    if not output_dir.is_absolute():
        output_dir = project_root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    id_col = config.get("id_col", "participant_id")
    food_col = config.get("food_col", "food_id")
    ref_food_col = config.get("ref_food_col", "hpp_food_id")
    grams_col = config.get("grams_col", "weight_g")
    time_col = config.get("time_col", "collection_timestamp")
    y_time_col = config.get("y_time_col", "time_window")
    target_time_col = config.get("target_time_col", "collection_timestamp")
    window = config.get("window", "participant")

    diet_events_path = Path(config["diet_events_path"])
    microbiome_targets_path = Path(config["microbiome_targets_path"])
    if not diet_events_path.is_absolute():
        diet_events_path = project_root / diet_events_path
    if not microbiome_targets_path.is_absolute():
        microbiome_targets_path = project_root / microbiome_targets_path

    target_table_path, targets = normalize_microbiome_targets(
        microbiome_targets_path=microbiome_targets_path,
        output_path=output_dir / "microbiome_targets_selected.parquet",
        id_col=id_col,
        time_col=y_time_col,
        target_time_col=target_time_col,
        window=window,
        targets=config.get("targets"),
        max_targets=config.get("max_targets"),
    )

    task_type = config.get("task_type", "continuous")
    models = config.get("models", ["ridge", "lasso", "rf_regression"])
    n_splits = int(config.get("n_splits", 5))
    test_size = float(config.get("test_size", 0.2))

    comparison_rows: list[dict[str, Any]] = []
    feature_summaries: list[dict[str, Any]] = []
    for feature_set in load_feature_sets(config, project_root):
        feature_output_dir = output_dir / feature_set.name
        feature_output_dir.mkdir(parents=True, exist_ok=True)
        x_path = feature_output_dir / f"X_{feature_set.name}_{window}.parquet"
        feature_summary = build_design_matrix(
            diet_events_path=diet_events_path,
            food_reference_path=feature_set.path,
            output_path=x_path,
            feature_mode=feature_set.feature_mode,
            id_col=id_col,
            food_col=food_col,
            ref_food_col=ref_food_col,
            grams_col=grams_col,
            time_col=time_col,
            window=window,
        )
        feature_summaries.append(
            {
                "feature_set": feature_set.name,
                "description": feature_set.description,
                **feature_summary,
            }
        )
        for target in targets:
            target_dir = feature_output_dir / "predictions" / target
            run_summary = run_prediction_from_files(
                x_path=x_path,
                y_path=target_table_path,
                target_col=target,
                output_dir=target_dir,
                id_col=id_col,
                time_col=y_time_col,
                task_type=task_type,
                models=models,
                n_splits=n_splits,
                test_size=test_size,
            )
            summary_metrics = read_table(run_summary["summary_metrics"])
            for _, row in summary_metrics.iterrows():
                row_dict = row.to_dict()
                row_dict.update(
                    {
                        "feature_set": feature_set.name,
                        "target": target,
                        "x_path": str(x_path),
                        "aligned_rows": run_summary["aligned_rows"],
                        "feature_count": run_summary["feature_count"],
                    }
                )
                comparison_rows.append(row_dict)

    comparison = pd.DataFrame(comparison_rows)
    comparison_path = output_dir / "microbiome_feature_set_comparison.csv"
    write_table(comparison, comparison_path)
    feature_summary_path = output_dir / "feature_set_build_summaries.csv"
    write_table(pd.DataFrame(feature_summaries), feature_summary_path)
    run_summary = {
        "diet_events_path": str(diet_events_path),
        "microbiome_targets_path": str(microbiome_targets_path),
        "selected_target_table": str(target_table_path),
        "targets": targets,
        "feature_sets": [fs.name for fs in load_feature_sets(config, project_root)],
        "comparison_path": str(comparison_path),
        "feature_summary_path": str(feature_summary_path),
        "output_dir": str(output_dir),
    }
    (output_dir / "microbiome_prediction_run_summary.json").write_text(json.dumps(run_summary, indent=2), encoding="utf-8")
    return run_summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run microbiome prediction feature-set comparison.")
    parser.add_argument("--config", required=True, help="Path to microbiome prediction JSON config.")
    parser.add_argument("--project-root", default=".", help="Project root containing downstream_analysis and outputs.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_root = Path(args.project_root).resolve()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = project_root / config_path
    config = json.loads(config_path.read_text(encoding="utf-8"))
    summary = run_microbiome_comparison(config=config, project_root=project_root)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
