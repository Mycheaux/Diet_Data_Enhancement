"""Export diet-enhancement features for PhenoBench participant-embedding tasks.

This module is intentionally an adapter, not a PhenoBench runner. Its narrow
job is to turn project-specific Diet Data Enhancement tables into artifacts that
the separate `phenobench-tre` repo can execute against.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


DEFAULT_TASK_MAP_PATH = Path(__file__).with_name("phenobench_task_map.json")
DEFAULT_ALPHAS = (0.01, 0.1, 1.0, 10.0, 100.0)
ID_COLUMNS = ("participant_id", "ParticipantId", "participant", "person_id")
NON_FEATURE_COLUMNS = {
    "participant_id",
    "ParticipantId",
    "participant",
    "person_id",
    "cohort",
    "research_stage",
    "time_window",
    "window_id",
    "array_index",
    "timestamp",
    "collection_timestamp",
    "collection_date",
    "sample_name",
    "run_name",
    "wgs_dna_code",
    "split",
}


@dataclass(frozen=True)
class EmbeddingExport:
    artifact_path: Path
    metadata_path: Path
    feature_columns: list[str]
    participant_count: int
    embedding_dim: int


def read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix in {".csv", ".txt"}:
        return pd.read_csv(path)
    if suffix == ".tsv":
        return pd.read_csv(path, sep="\t")
    raise ValueError(f"Unsupported table format for {path}. Use CSV, TSV, or Parquet.")


def resolve_id_column(frame: pd.DataFrame, requested: str | None) -> str:
    if requested:
        if requested not in frame.columns:
            raise ValueError(f"Requested id column {requested!r} is not in the table.")
        return requested
    for col in ID_COLUMNS:
        if col in frame.columns:
            return col
    raise ValueError(
        "Could not find a participant id column. Pass --id-col explicitly."
    )


def select_feature_columns(
    frame: pd.DataFrame,
    *,
    id_col: str,
    exclude_columns: Iterable[str] = (),
) -> list[str]:
    exclude = set(NON_FEATURE_COLUMNS)
    exclude.add(id_col)
    exclude.update(exclude_columns)
    numeric_cols = [
        col
        for col in frame.columns
        if col not in exclude and pd.api.types.is_numeric_dtype(frame[col])
    ]
    if not numeric_cols:
        raise ValueError("No numeric feature columns were found for the embedding.")
    return numeric_cols


def prepare_participant_matrix(
    frame: pd.DataFrame,
    *,
    id_col: str,
    feature_columns: list[str],
    participant_policy: str,
) -> pd.DataFrame:
    work = frame[[id_col, *feature_columns]].copy()
    work[id_col] = work[id_col].map(_coerce_participant_id)
    work[feature_columns] = (
        work[feature_columns]
        .replace([np.inf, -np.inf], np.nan)
        .fillna(0.0)
        .astype(float)
    )

    duplicate_mask = work[id_col].duplicated(keep=False)
    if duplicate_mask.any():
        if participant_policy == "error":
            sample = sorted(work.loc[duplicate_mask, id_col].unique().tolist())[:10]
            raise ValueError(
                "The table has repeated participant ids. Phenobench participant_embedding "
                f"expects one row per participant. Examples: {sample}. Use "
                "--participant-policy mean or first if appropriate."
            )
        if participant_policy == "mean":
            work = work.groupby(id_col, as_index=False)[feature_columns].mean()
        elif participant_policy == "first":
            work = work.drop_duplicates(subset=[id_col], keep="first")
        else:
            raise ValueError(f"Unknown participant policy: {participant_policy}")
    return work


def export_participant_embedding(
    *,
    x_path: Path,
    output_path: Path,
    id_col: str | None = None,
    feature_columns: list[str] | None = None,
    participant_policy: str = "error",
    feature_set_name: str = "diet_enhancement",
) -> EmbeddingExport:
    frame = read_table(x_path)
    resolved_id_col = resolve_id_column(frame, id_col)
    resolved_features = feature_columns or select_feature_columns(
        frame, id_col=resolved_id_col
    )
    matrix = prepare_participant_matrix(
        frame,
        id_col=resolved_id_col,
        feature_columns=resolved_features,
        participant_policy=participant_policy,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    artifact = pd.DataFrame(
        {
            "participant_id": matrix[resolved_id_col].astype(str),
            "embedding": matrix[resolved_features].to_numpy(dtype=float).tolist(),
        }
    )
    if "split" in frame.columns and participant_policy in {"error", "first"}:
        split_frame = frame[[resolved_id_col, "split"]].drop_duplicates(
            subset=[resolved_id_col], keep="first"
        )
        split_frame[resolved_id_col] = split_frame[resolved_id_col].map(
            _coerce_participant_id
        )
        artifact = artifact.merge(
            split_frame.rename(columns={resolved_id_col: "participant_id"}),
            on="participant_id",
            how="left",
        )
    artifact.to_parquet(output_path, index=False)

    metadata_path = output_path.with_suffix(".metadata.json")
    metadata = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_x_path": str(x_path),
        "feature_set_name": feature_set_name,
        "id_column": resolved_id_col,
        "participant_policy": participant_policy,
        "participant_count": int(len(artifact)),
        "embedding_dim": int(len(resolved_features)),
        "feature_columns": resolved_features,
        "phenobench_predictor": "participant_embedding",
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return EmbeddingExport(
        artifact_path=output_path,
        metadata_path=metadata_path,
        feature_columns=resolved_features,
        participant_count=int(len(artifact)),
        embedding_dim=int(len(resolved_features)),
    )


def generate_phenobench_configs(
    *,
    embedding_artifact: Path,
    embedding_dim: int,
    output_dir: Path,
    feature_set_name: str,
    tasks: dict[str, dict],
    task_loader_mode: str = "real",
    tracking_uri: str = "databricks://ds",
    output_root: str = "experiments",
    leaderboard_root: str = "phenobench/leaderboards",
) -> list[Path]:
    config_dir = output_dir / "phenobench_configs"
    config_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for task_id, meta in tasks.items():
        phenobench_task = meta.get("phenobench_task")
        if not phenobench_task or not meta.get("config_ready", True):
            continue
        config_path = config_dir / f"{phenobench_task}_{feature_set_name}_ridge_cv.yaml"
        config_path.write_text(
            _render_yaml_config(
                task_name=phenobench_task,
                embedding_artifact=embedding_artifact,
                embedding_dim=embedding_dim,
                task_loader_mode=task_loader_mode,
                tracking_uri=tracking_uri,
                output_root=output_root,
                leaderboard_root=leaderboard_root,
            ),
            encoding="utf-8",
        )
        written.append(config_path)
    return written


def generate_task_cards(
    *,
    output_dir: Path,
    feature_set_name: str,
    tasks: dict[str, dict],
) -> list[Path]:
    card_dir = output_dir / "phenobench_task_cards"
    card_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for task_id, meta in tasks.items():
        phenobench_task = meta.get("phenobench_task") or task_id
        card_path = card_dir / f"{phenobench_task}.md"
        card_path.write_text(
            _render_task_card(task_id=task_id, feature_set_name=feature_set_name, meta=meta),
            encoding="utf-8",
        )
        written.append(card_path)
    return written


def build_adapter_export(
    *,
    x_path: Path,
    output_dir: Path,
    feature_set_name: str,
    task_map_path: Path = DEFAULT_TASK_MAP_PATH,
    id_col: str | None = None,
    participant_policy: str = "error",
    task_loader_mode: str = "real",
    tracking_uri: str = "databricks://ds",
    adapter_mode: str = "full",
) -> dict:
    tasks = json.loads(task_map_path.read_text(encoding="utf-8"))
    embedding_path = (
        output_dir
        / "participant_embedding"
        / f"{feature_set_name}.participant_embedding.parquet"
    )
    export = export_participant_embedding(
        x_path=x_path,
        output_path=embedding_path,
        id_col=id_col,
        participant_policy=participant_policy,
        feature_set_name=feature_set_name,
    )
    configs = []
    cards = []
    if adapter_mode in {"full", "tre_minimal"}:
        configs = generate_phenobench_configs(
            embedding_artifact=export.artifact_path,
            embedding_dim=export.embedding_dim,
            output_dir=output_dir,
            feature_set_name=feature_set_name,
            tasks=tasks,
            task_loader_mode=task_loader_mode,
            tracking_uri=tracking_uri,
        )
    if adapter_mode in {"full", "outside_llm"}:
        cards = generate_task_cards(
            output_dir=output_dir,
            feature_set_name=feature_set_name,
            tasks=tasks,
        )
        write_llm_task_card_brief(
            output_dir=output_dir,
            feature_set_name=feature_set_name,
            tasks=tasks,
        )
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "feature_set_name": feature_set_name,
        "source_x_path": str(x_path),
        "embedding_artifact": str(export.artifact_path),
        "embedding_metadata": str(export.metadata_path),
        "participant_count": export.participant_count,
        "embedding_dim": export.embedding_dim,
        "phenobench_configs": [str(path) for path in configs],
        "phenobench_task_cards": [str(path) for path in cards],
        "task_map_path": str(task_map_path),
        "adapter_mode": adapter_mode,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "phenobench_adapter_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return manifest


def write_llm_task_card_brief(
    *,
    output_dir: Path,
    feature_set_name: str,
    tasks: dict[str, dict],
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = output_dir / "llm_task_card_brief.md"
    planning_tasks = [
        (task_id, meta)
        for task_id, meta in tasks.items()
        if not meta.get("config_ready", True)
    ]
    executable_tasks = [
        (task_id, meta)
        for task_id, meta in tasks.items()
        if meta.get("config_ready", True)
    ]
    prompt_path.write_text(
        _render_llm_task_card_brief(
            feature_set_name=feature_set_name,
            executable_tasks=executable_tasks,
            planning_tasks=planning_tasks,
        ),
        encoding="utf-8",
    )
    return prompt_path


def _render_yaml_config(
    *,
    task_name: str,
    embedding_artifact: Path,
    embedding_dim: int,
    task_loader_mode: str,
    tracking_uri: str,
    output_root: str,
    leaderboard_root: str,
) -> str:
    alphas = ", ".join(str(value) for value in DEFAULT_ALPHAS)
    return f"""schema_version: 1

# Diet-enhancement bridge generated by downstream_analysis.phenobench_adapter.
# The predictor reads a participant-level diet embedding artifact.

task:
  name: {task_name}
  kwargs:
    loader_mode: {task_loader_mode}

predictor:
  name: participant_embedding
  kwargs:
    artifact_path: "{embedding_artifact}"
    embedding_dim: {embedding_dim}
    view_slice: concat

strategy:
  name: ridge_cv
  kwargs:
    alphas: [{alphas}]
    fit_intercept: true
    cv: 5
    seed: 42
    scaler: standard

persistence:
  output_root: {output_root}
  leaderboard_root: {leaderboard_root}
  predictions: true
  leaderboard: false
  tracking_uri: "{tracking_uri}"
"""


def _render_task_card(*, task_id: str, feature_set_name: str, meta: dict) -> str:
    clinical_name = meta.get("clinical_name", task_id)
    phenobench_task = meta.get("phenobench_task") or task_id
    return f"""# {clinical_name} Diet-Enhancement Task Card

Status: draft

Task id: `{phenobench_task}`

## Target

Predict {clinical_name} from participant-level diet representations exported by
the Diet Data Enhancement project.

- target field: `{meta.get("diet_target_field", "not specified")}`
- target dataset: {meta.get("target_dataset", "not specified")}
- target source: {meta.get("target_source", "not specified")}
- default research stage: TRE evaluation with participant-level train/test splits
- valid range: {meta.get("valid_range", "use source-specific quality-control range")}
- primary metric: {meta.get("primary_metric", "R2")}

## Why This Matters

{meta.get("why_this_matters", "This task evaluates whether enriched diet representations improve prediction for the target phenotype.")}

## Baselines And Ceilings

Recommended comparison arms:

- no-feature or demographic Phenobench floor, when available;
- NutriMatch-only nutrient diet representation;
- de novo diet-enhancement representation;
- full KG/downstream representation;
- food-card text-embedding representation.

The ceiling is limited by diet-log completeness, target measurement noise,
participant overlap, time-window alignment, and non-diet covariates that are not
included in the embedding.

## Caveats

{meta.get("caveats", "Interpret results with attention to target measurement timing, missingness, and confounding.")}

## Metrics

Use Phenobench regression metrics for continuous biomarkers. Report mean and
fold-level R2, RMSE, MAE when available, and Pearson correlation for comparison
with the local downstream-analysis notebooks.

## References

- Diet Data Enhancement project methods and downstream-analysis documentation.
- Phenobench task documentation and task-specific source material.

## Open Questions

- What diet-history window best matches this biomarker?
- Should non-diet covariates be added as a separate comparison arm?
- Should task-specific food-card summaries be generated for this phenotype?
"""


def _render_llm_task_card_brief(
    *,
    feature_set_name: str,
    executable_tasks: list[tuple[str, dict]],
    planning_tasks: list[tuple[str, dict]],
) -> str:
    executable_lines = "\n".join(
        f"- `{task_id}` / Phenobench `{meta.get('phenobench_task')}`: "
        f"{meta.get('clinical_name', task_id)}"
        for task_id, meta in executable_tasks
    )
    planning_lines = "\n".join(
        f"- `{task_id}` / Phenobench `{meta.get('phenobench_task', 'not confirmed')}`: "
        f"{meta.get('clinical_name', task_id)}; adapter note: "
        f"{meta.get('adapter_note', 'needs task-specific adapter review')}"
        for task_id, meta in planning_tasks
    )
    return f"""# LLM Brief For Phenobench Task-Card Drafting

This brief is meant for work outside TRE. Do not put private participant data in
the prompt. Use only public docs, Phenobench docs, task cards, configs, and the
Diet Data Enhancement methods/readme files.

## First Instruction For The Agent

Read Phenobench `AGENTS.md`, then `docs/onboarding.md`,
`docs/architecture.md`, `configs/README.md`, `docs/task_cards/README.md`, and
the closest task card/config for the task being adapted. Explain what needs to
change for the diet-enhancement dataset before editing anything.

## Diet Feature Set

Feature-set name: `{feature_set_name}`

The Diet Data Enhancement project can provide participant-level diet embeddings
from enriched nutrient, food-chemical, metabolomic, disease/pathway, and
food-card text representations. Inside TRE these are exported as a Phenobench
`participant_embedding` artifact with one row per `participant_id`.

## Config-Ready Participant-Level Tasks

These can start with the hard-coded adapter output using
`participant_embedding` plus `ridge_cv`:

{executable_lines or "- None yet."}

## Planning-Only Or Task-Specific Adapter Tasks

These are scientifically relevant, but should not be treated as the same
participant-level embedding problem without inspecting the task contract:

{planning_lines or "- None."}

## Suggested Comparison Arms

- Phenobench floor or no-feature baseline.
- NutriMatch-only nutrient features.
- De novo diet-enhancement features.
- Full KG/downstream features.
- Food-card text embeddings.

## TRE Boundary

Outside TRE: task-card drafting, phenotype interpretation, prompt-based
summaries, literature wording, and any LLM use.

Inside TRE: raw participant data joins, participant embedding artifact creation,
Phenobench config execution, model fitting, and metric export.
"""


def _coerce_participant_id(value: object) -> str:
    if pd.isna(value):
        raise ValueError("participant_id contains missing values")
    if isinstance(value, bool):
        raise ValueError(f"participant_id is not valid: {value!r}")
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)):
        fvalue = float(value)
        if not fvalue.is_integer():
            raise ValueError(f"participant_id is a non-integer float: {value!r}")
        return str(int(fvalue))
    text = str(value)
    if not text:
        raise ValueError("participant_id contains empty strings")
    return text


def _parse_feature_columns(value: str | None) -> list[str] | None:
    if value is None:
        return None
    return [part.strip() for part in value.split(",") if part.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export diet-enhancement features as Phenobench artifacts."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    export_parser = sub.add_parser("export-embedding")
    export_parser.add_argument("--x-path", required=True, type=Path)
    export_parser.add_argument("--output-path", required=True, type=Path)
    export_parser.add_argument("--id-col")
    export_parser.add_argument("--feature-columns")
    export_parser.add_argument(
        "--participant-policy",
        choices=("error", "mean", "first"),
        default="error",
    )
    export_parser.add_argument("--feature-set-name", default="diet_enhancement")

    config_parser = sub.add_parser("generate-configs")
    config_parser.add_argument("--embedding-artifact", required=True, type=Path)
    config_parser.add_argument("--embedding-dim", required=True, type=int)
    config_parser.add_argument("--output-dir", required=True, type=Path)
    config_parser.add_argument("--feature-set-name", default="diet_enhancement")
    config_parser.add_argument("--task-map-path", default=DEFAULT_TASK_MAP_PATH, type=Path)
    config_parser.add_argument("--task-loader-mode", default="real")
    config_parser.add_argument("--tracking-uri", default="databricks://ds")

    brief_parser = sub.add_parser("write-llm-brief")
    brief_parser.add_argument("--output-dir", required=True, type=Path)
    brief_parser.add_argument("--feature-set-name", default="diet_enhancement")
    brief_parser.add_argument("--task-map-path", default=DEFAULT_TASK_MAP_PATH, type=Path)

    card_parser = sub.add_parser("write-task-cards")
    card_parser.add_argument("--output-dir", required=True, type=Path)
    card_parser.add_argument("--feature-set-name", default="diet_enhancement")
    card_parser.add_argument("--task-map-path", default=DEFAULT_TASK_MAP_PATH, type=Path)

    build_parser = sub.add_parser("build")
    build_parser.add_argument("--x-path", required=True, type=Path)
    build_parser.add_argument("--output-dir", required=True, type=Path)
    build_parser.add_argument("--feature-set-name", default="diet_enhancement")
    build_parser.add_argument("--task-map-path", default=DEFAULT_TASK_MAP_PATH, type=Path)
    build_parser.add_argument("--id-col")
    build_parser.add_argument(
        "--participant-policy",
        choices=("error", "mean", "first"),
        default="error",
    )
    build_parser.add_argument("--task-loader-mode", default="real")
    build_parser.add_argument("--tracking-uri", default="databricks://ds")
    build_parser.add_argument(
        "--adapter-mode",
        choices=("artifact_only", "full", "outside_llm", "tre_minimal"),
        default="full",
        help=(
            "artifact_only writes only the participant embedding artifact and manifest; "
            "full writes embedding, configs, cards, and LLM brief; "
            "outside_llm writes embedding plus card/brief material; "
            "tre_minimal writes embedding plus executable configs only."
        ),
    )

    args = parser.parse_args(argv)
    if args.command == "export-embedding":
        export = export_participant_embedding(
            x_path=args.x_path,
            output_path=args.output_path,
            id_col=args.id_col,
            feature_columns=_parse_feature_columns(args.feature_columns),
            participant_policy=args.participant_policy,
            feature_set_name=args.feature_set_name,
        )
        print(json.dumps(export.__dict__ | {
            "artifact_path": str(export.artifact_path),
            "metadata_path": str(export.metadata_path),
        }, indent=2))
        return 0
    if args.command == "generate-configs":
        tasks = json.loads(args.task_map_path.read_text(encoding="utf-8"))
        configs = generate_phenobench_configs(
            embedding_artifact=args.embedding_artifact,
            embedding_dim=args.embedding_dim,
            output_dir=args.output_dir,
            feature_set_name=args.feature_set_name,
            tasks=tasks,
            task_loader_mode=args.task_loader_mode,
            tracking_uri=args.tracking_uri,
        )
        cards = generate_task_cards(
            output_dir=args.output_dir,
            feature_set_name=args.feature_set_name,
            tasks=tasks,
        )
        print(json.dumps({
            "phenobench_configs": [str(path) for path in configs],
            "phenobench_task_cards": [str(path) for path in cards],
        }, indent=2))
        return 0
    if args.command == "write-llm-brief":
        tasks = json.loads(args.task_map_path.read_text(encoding="utf-8"))
        prompt_path = write_llm_task_card_brief(
            output_dir=args.output_dir,
            feature_set_name=args.feature_set_name,
            tasks=tasks,
        )
        print(json.dumps({"llm_task_card_brief": str(prompt_path)}, indent=2))
        return 0
    if args.command == "write-task-cards":
        tasks = json.loads(args.task_map_path.read_text(encoding="utf-8"))
        cards = generate_task_cards(
            output_dir=args.output_dir,
            feature_set_name=args.feature_set_name,
            tasks=tasks,
        )
        print(json.dumps({
            "phenobench_task_cards": [str(path) for path in cards],
        }, indent=2))
        return 0
    if args.command == "build":
        manifest = build_adapter_export(
            x_path=args.x_path,
            output_dir=args.output_dir,
            feature_set_name=args.feature_set_name,
            task_map_path=args.task_map_path,
            id_col=args.id_col,
            participant_policy=args.participant_policy,
            task_loader_mode=args.task_loader_mode,
            tracking_uri=args.tracking_uri,
            adapter_mode=args.adapter_mode,
        )
        print(json.dumps(manifest, indent=2))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
