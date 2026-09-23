"""Prepare local TRE input tables from HPP datasets loaded by PhenoLoader.

This module runs inside TRE where ``pheno_utils`` is available.  It writes the
small set of local parquet files expected by the downstream prediction tasks,
while also supporting generic dataset inspection/export for future modalities.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


DEFAULT_CVD_TARGETS = [
    "bt__triglycerides_float_value",
    "bt__total_cholesterol_float_value",
    "bt__hdl_cholesterol_float_value",
    "bt__ldl_cholesterol_float_value",
    "bt__non_hdl_cholesterol_float_value",
    "bt__glucose_float_value",
    "bt__hba1c_float_value",
    "bt__creatinine_float_value",
    "bt__urate_float_value",
    "bt__alt_float_value",
    "bt__ast_float_value",
    "bt__ggt_float_value",
]

DIET_EVENT_COLUMNS = [
    "participant_id",
    "cohort",
    "research_stage",
    "logging_day",
    "collection_timestamp",
    "collection_date",
    "food_id",
    "short_food_name",
    "product_name",
    "food_category",
    "weight_g",
    "calories_kcal",
    "carbohydrate_g",
    "lipid_g",
    "protein_g",
    "sodium_mg",
    "alcohol_g",
    "dietary_fiber_g",
    "eaten_in_restaurant",
    "local_timestamp",
    "timezone",
]

MICROBIOME_TABLE_CANDIDATES = [
    "urs",
    "urs_abundances",
    "urs_abundances_aggregated",
    "metaphlan_abundance_species",
    "metaphlan_abundance_species_parquet",
    "metaphlan_abundance_genus",
    "metaphlan_abundance_genus_parquet",
    "metaphlan_abundance_strain",
    "metaphlan_abundance_strain_parquet",
]


def require_pheno_utils():
    try:
        from pheno_utils import PhenoLoader  # type: ignore
        from pheno_utils.config import DATASETS_PATH  # type: ignore
    except Exception as exc:  # pragma: no cover - only happens outside TRE
        raise RuntimeError(
            "pheno_utils is required for this command. Run it inside TRE or in "
            "an environment where `from pheno_utils import PhenoLoader` works."
        ) from exc
    return PhenoLoader, Path(DATASETS_PATH)


def make_loader(dataset: str, *, age_sex_dataset: str | None = None, errors: str = "warn"):
    PhenoLoader, _ = require_pheno_utils()
    return PhenoLoader(dataset, age_sex_dataset=age_sex_dataset, errors=errors)


def dataframe_with_index_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Return a flat dataframe, preserving useful MultiIndex levels as columns."""
    out = df.copy()
    if isinstance(out.index, pd.MultiIndex):
        out = out.reset_index()
    elif out.index.name is not None:
        out = out.reset_index()
    return out.loc[:, ~out.columns.duplicated()].copy()


def write_table(df: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".parquet":
        df.to_parquet(path, index=False)
    elif path.suffix.lower() == ".csv":
        df.to_csv(path, index=False)
    else:
        raise ValueError(f"Unsupported output extension for {path}; use .parquet or .csv")
    return path


def clean_path_value(value: object) -> str | None:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    return text


def dataset_folder(loader, dataset_name: str) -> Path:
    _, datasets_path = require_pheno_utils()
    folder = getattr(loader, "dataset", None) or dataset_name
    return datasets_path / str(folder)


def candidate_bulk_paths(loader, dataset_name: str, table_name: str) -> list[Path]:
    """Return plausible parquet paths for a table that is not loaded in ``pl.dfs``."""
    folder = dataset_folder(loader, dataset_name)
    names = [table_name]
    if table_name.endswith("_parquet"):
        names.append(table_name[: -len("_parquet")])
    candidates: list[Path] = []
    for name in names:
        if name.endswith(".parquet"):
            candidates.append(folder / name)
        else:
            candidates.append(folder / f"{name}.parquet")

    for frame in getattr(loader, "dfs", {}).values():
        flat = dataframe_with_index_columns(frame)
        for col in flat.columns:
            if col == table_name or col == table_name.replace("_parquet", ""):
                for raw in flat[col].dropna().unique()[:20]:
                    rel = clean_path_value(raw)
                    if rel:
                        candidates.append(folder / rel)

    dictionary = getattr(loader, "dict", None)
    if isinstance(dictionary, pd.DataFrame):
        dflat = dataframe_with_index_columns(dictionary)
        mask = pd.Series(False, index=dflat.index)
        for col in ("field_string", "tabular_field_name", "parent_dataframe"):
            if col in dflat:
                mask = mask | dflat[col].astype(str).eq(table_name)
        for col in ("relative_location", "bulk_dictionary"):
            if col in dflat:
                for raw in dflat.loc[mask, col].dropna().unique()[:20]:
                    rel = clean_path_value(raw)
                    if rel:
                        candidates.append(folder.parent / rel)
                        candidates.append(folder / rel)
    seen: set[str] = set()
    out = []
    for path in candidates:
        key = str(path)
        if key not in seen:
            seen.add(key)
            out.append(path)
    return out


def table_from_loader_getitem(loader, table_name: str) -> pd.DataFrame | None:
    """Try PhenoLoader's bracket access pattern, used by datasets like oral_microbiome."""
    candidates = [table_name]
    if table_name.endswith("_parquet"):
        candidates.append(table_name[: -len("_parquet")])
    for key in candidates:
        try:
            table = loader[key]
        except Exception:
            continue
        if isinstance(table, pd.Series):
            table = table.to_frame()
        if isinstance(table, pd.DataFrame):
            return dataframe_with_index_columns(table)
    return None


def load_table_from_loader(
    loader,
    dataset_name: str,
    table_name: str,
    *,
    required: bool = True,
) -> pd.DataFrame | None:
    dfs = getattr(loader, "dfs", {})
    if table_name in dfs:
        return dataframe_with_index_columns(dfs[table_name])
    if table_name.endswith("_parquet") and table_name[: -len("_parquet")] in dfs:
        return dataframe_with_index_columns(dfs[table_name[: -len("_parquet")]])

    getitem_table = table_from_loader_getitem(loader, table_name)
    if getitem_table is not None:
        return getitem_table

    for path in candidate_bulk_paths(loader, dataset_name, table_name):
        if path.exists():
            return dataframe_with_index_columns(pd.read_parquet(path))

    if required:
        tried = [str(p) for p in candidate_bulk_paths(loader, dataset_name, table_name)]
        raise FileNotFoundError(
            f"Could not load table {table_name!r} from dataset {dataset_name!r}. "
            f"Available pl.dfs tables: {sorted(dfs.keys())}. Tried paths: {tried[:8]}"
        )
    return None


def keep_existing_columns(df: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    keep = [col for col in columns if col in df.columns]
    remainder = [col for col in df.columns if col not in keep]
    return df[keep + remainder]


def prepare_diet_events(output_dir: Path, *, errors: str = "warn") -> dict:
    loader = make_loader("diet_logging", age_sex_dataset=None, errors=errors)
    events = load_table_from_loader(loader, "diet_logging", "diet_logging_events")
    events = keep_existing_columns(events, DIET_EVENT_COLUMNS)
    output_path = write_table(events, output_dir / "diet_logging_events.parquet")
    return {
        "dataset": "diet_logging",
        "table": "diet_logging_events",
        "output_path": str(output_path),
        "rows": int(len(events)),
        "columns": list(events.columns),
    }


def prepare_blood_tests(output_dir: Path, *, errors: str = "warn") -> dict:
    loader = make_loader("blood_tests", age_sex_dataset=None, errors=errors)
    blood = load_table_from_loader(loader, "blood_tests", "blood_tests")
    preferred = ["participant_id", "cohort", "research_stage", "collection_date", "hmo"]
    blood = keep_existing_columns(blood, preferred + DEFAULT_CVD_TARGETS)
    output_path = write_table(blood, output_dir / "blood_tests.parquet")
    present_targets = [target for target in DEFAULT_CVD_TARGETS if target in blood.columns]
    return {
        "dataset": "blood_tests",
        "table": "blood_tests",
        "output_path": str(output_path),
        "rows": int(len(blood)),
        "columns": list(blood.columns),
        "present_cvd_targets": present_targets,
        "missing_cvd_targets": [target for target in DEFAULT_CVD_TARGETS if target not in blood.columns],
    }


def choose_microbiome_table(loader, dataset_name: str, requested_table: str | None) -> tuple[str, pd.DataFrame]:
    if requested_table:
        table = load_table_from_loader(loader, dataset_name, requested_table)
        return requested_table, table

    candidates: list[tuple[str, pd.DataFrame, int]] = []
    for table_name in MICROBIOME_TABLE_CANDIDATES:
        table = load_table_from_loader(loader, dataset_name, table_name, required=False)
        if table is None:
            continue
        numeric_count = len(table.select_dtypes(include="number").columns)
        if numeric_count:
            candidates.append((table_name, table, numeric_count))
    if not candidates:
        fallback = load_table_from_loader(loader, dataset_name, "gut_microbiome")
        return "gut_microbiome", fallback
    candidates.sort(key=lambda item: item[2], reverse=True)
    return candidates[0][0], candidates[0][1]


def prepare_microbiome_targets(
    output_dir: Path,
    *,
    table_name: str | None = None,
    max_numeric_targets: int | None = 500,
    errors: str = "warn",
) -> dict:
    loader = make_loader("gut_microbiome", age_sex_dataset=None, errors=errors)
    selected_name, table = choose_microbiome_table(loader, "gut_microbiome", table_name)
    preferred = [
        "participant_id",
        "cohort",
        "research_stage",
        "collection_timestamp",
        "collection_date",
        "sample_name",
        "run_name",
        "wgs_dna_code",
    ]
    numeric_cols = [
        col
        for col in table.select_dtypes(include="number").columns
        if col not in set(preferred)
    ]
    if max_numeric_targets is not None and len(numeric_cols) > max_numeric_targets:
        numeric_cols = numeric_cols[:max_numeric_targets]
    keep = [col for col in preferred if col in table.columns] + numeric_cols
    if keep:
        table = table[keep]
    output_path = write_table(table, output_dir / "microbiome_targets.parquet")
    return {
        "dataset": "gut_microbiome",
        "table": selected_name,
        "output_path": str(output_path),
        "rows": int(len(table)),
        "columns": list(table.columns),
        "numeric_target_count": int(len(numeric_cols)),
    }


def inspect_dataset(dataset: str, *, errors: str = "warn") -> dict:
    loader = make_loader(dataset, age_sex_dataset=None, errors=errors)
    dfs = getattr(loader, "dfs", {})
    dictionary = getattr(loader, "dict", None)
    tables = {
        name: {"rows": int(len(dataframe_with_index_columns(frame))), "columns": list(dataframe_with_index_columns(frame).columns)}
        for name, frame in dfs.items()
    }
    bulk_fields: list[dict] = []
    if isinstance(dictionary, pd.DataFrame):
        dflat = dataframe_with_index_columns(dictionary)
        for _, row in dflat.iterrows():
            field_type = str(row.get("field_type", ""))
            extension = str(row.get("bulk_file_extension", ""))
            if "file" in field_type.lower() or extension not in {"", "nan", "NaN"}:
                bulk_fields.append(
                    {
                        "field_string": clean_path_value(row.get("field_string")),
                        "parent_dataframe": clean_path_value(row.get("parent_dataframe")),
                        "relative_location": clean_path_value(row.get("relative_location")),
                        "bulk_file_extension": clean_path_value(row.get("bulk_file_extension")),
                    }
                )
    return {
        "dataset": dataset,
        "pheno_dataset_folder": str(getattr(loader, "dataset", dataset)),
        "dfs_tables": tables,
        "bulk_fields": bulk_fields,
    }


def export_dataset_tables(dataset: str, output_dir: Path, *, errors: str = "warn") -> dict:
    loader = make_loader(dataset, age_sex_dataset=None, errors=errors)
    out_dir = output_dir / dataset
    exported = []
    for table_name, frame in getattr(loader, "dfs", {}).items():
        flat = dataframe_with_index_columns(frame)
        path = write_table(flat, out_dir / f"{table_name}.parquet")
        exported.append({"table": table_name, "output_path": str(path), "rows": int(len(flat)), "columns": list(flat.columns)})
    manifest = {"dataset": dataset, "exported_tables": exported}
    write_manifest(manifest, out_dir / "export_manifest.json")
    return manifest


def write_manifest(summary: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    return path


def prepare_task_inputs(
    output_dir: Path,
    *,
    tasks: Iterable[str],
    microbiome_table: str | None = None,
    max_microbiome_targets: int | None = 500,
    errors: str = "warn",
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    task_set = set(tasks)
    summaries: dict[str, dict] = {}
    if task_set & {"all", "cvd", "microbiome", "diet"}:
        summaries["diet_logging_events"] = prepare_diet_events(output_dir, errors=errors)
    if task_set & {"all", "cvd", "blood_tests"}:
        summaries["blood_tests"] = prepare_blood_tests(output_dir, errors=errors)
    if task_set & {"all", "microbiome"}:
        summaries["microbiome_targets"] = prepare_microbiome_targets(
            output_dir,
            table_name=microbiome_table,
            max_numeric_targets=max_microbiome_targets,
            errors=errors,
        )
    manifest = {"output_dir": str(output_dir), "tasks": sorted(task_set), "tables": summaries}
    write_manifest(manifest, output_dir / "tre_inputs_manifest.json")
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare downstream_analysis TRE inputs from pheno_utils.PhenoLoader."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare-task-inputs")
    prepare.add_argument("--output-dir", default="tre_inputs", type=Path)
    prepare.add_argument(
        "--tasks",
        nargs="+",
        default=["cvd"],
        choices=["all", "cvd", "microbiome", "diet", "blood_tests"],
    )
    prepare.add_argument("--microbiome-table")
    prepare.add_argument("--max-microbiome-targets", type=int, default=500)
    prepare.add_argument("--errors", default="warn")

    inspect = sub.add_parser("inspect-dataset")
    inspect.add_argument("dataset")
    inspect.add_argument("--output-json", type=Path)
    inspect.add_argument("--errors", default="warn")

    export = sub.add_parser("export-dataset")
    export.add_argument("dataset")
    export.add_argument("--output-dir", default="tre_inputs/raw_exports", type=Path)
    export.add_argument("--errors", default="warn")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        if args.command == "prepare-task-inputs":
            summary = prepare_task_inputs(
                output_dir=args.output_dir,
                tasks=args.tasks,
                microbiome_table=args.microbiome_table,
                max_microbiome_targets=args.max_microbiome_targets,
                errors=args.errors,
            )
        elif args.command == "inspect-dataset":
            summary = inspect_dataset(args.dataset, errors=args.errors)
            if args.output_json:
                write_manifest(summary, args.output_json)
        elif args.command == "export-dataset":
            summary = export_dataset_tables(args.dataset, args.output_dir, errors=args.errors)
        else:
            raise ValueError(args.command)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
