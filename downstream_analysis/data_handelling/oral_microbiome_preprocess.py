"""Prepare oral microbiome targets for nitrate/nitrite discovery analyses.

Run this inside TRE where ``pheno_utils`` and the HPP oral microbiome bulk
tables are available.  The script exports:

- MetaPhlAn genus/species abundance tables;
- alpha-diversity summaries computed from genus and species abundances;
- candidate nitrate-reducing oral taxa aggregates;
- HUMAnN pathway abundance and coverage tables, with nitrate/nitrite-relevant
  pathway candidates when labels are identifiable.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from downstream_analysis.data_handelling.pheno_loader_export import (
    clean_path_value,
    dataframe_with_index_columns,
    dataset_folder,
    load_table_from_loader,
    table_from_loader_getitem,
    make_loader,
    write_manifest,
    write_table,
)


ID_COL = "participant_id"

METAPHLAN_FIELDS = {
    "genus": [
        "metaphlan_abundance_genus_parquet",
        "metaphlan_abundance_genus",
        "metaphlan_aggregated_genus",
        "metaphlan_genus",
    ],
    "species": [
        "metaphlan_abundance_species_parquet",
        "metaphlan_abundance_species",
        "metaphlan_aggregated_species",
        "metaphlan_species",
    ],
}

HUMANN_FIELDS = {
    "pathway_abundance": [
        "humann_aggregated_pathway_abundance_pathway_level_arrow",
        "humann_aggregated_pathway_abundance_microbiome_level_arrow",
        "humann_pathway_abundance_pathway_level_parquet",
        "humann_pathway_abundance_microbe_level_parquet",
        "humann_pathway_abundance_tsv",
    ],
    "pathway_coverage": [
        "humann_aggregated_pathway_coverage_pathway_level_arrow",
        "humann_aggregated_pathway_coverage_microbiome_level_arrow",
        "humann_pathway_coverage_pathway_level_parquet",
        "humann_pathway_coverage_microbe_level_parquet",
        "humann_pathway_coverage_tsv",
    ],
}

NITRATE_REDUCER_TAXA = {
    "actinomyces": r"(^|[|_;\s])actinomyces([|_;\s]|$)",
    "haemophilus": r"(^|[|_;\s])haemophilus([|_;\s]|$)",
    "kingella": r"(^|[|_;\s])kingella([|_;\s]|$)",
    "neisseria": r"(^|[|_;\s])neisseria([|_;\s]|$)",
    "prevotella": r"(^|[|_;\s])prevotella([|_;\s]|$)",
    "rothia": r"(^|[|_;\s])rothia([|_;\s]|$)",
    "veillonella": r"(^|[|_;\s])veillonella([|_;\s]|$)",
}

NITRATE_PATHWAY_PATTERN = re.compile(
    r"nitrate|nitrite|nitric|nitros|denitrification|nitrogen|"
    r"\bnar[A-Z]?\b|\bnir[A-Z]?\b|\bnor[A-Z]?\b|\bnos[Z]?\b",
    flags=re.IGNORECASE,
)


def _clean_feature_name(value: object) -> str:
    text = str(value).strip()
    text = re.sub(r"^[a-z]__+", "", text)
    text = re.sub(r"[^A-Za-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_").lower()
    return text[:160] or "unknown"


def _participant_columns(df: pd.DataFrame) -> list[str]:
    aliases = [
        ID_COL,
        "participant",
        "participantid",
        "research_id",
        "sample",
        "sample_id",
        "sample_name",
        "wgs_dna_code",
    ]
    lower = {str(col).lower(): col for col in df.columns}
    return [lower[name] for name in aliases if name in lower]


def _metadata_columns(df: pd.DataFrame) -> list[str]:
    patterns = re.compile(
        r"participant|cohort|research_stage|collection|date|time|timezone|"
        r"sample|run|wgs|dna|fastq|read_count|qc|path|parquet|arrow|tsv",
        flags=re.IGNORECASE,
    )
    return [col for col in df.columns if patterns.search(str(col))]


def _feature_columns(df: pd.DataFrame) -> list[str]:
    metadata = set(_metadata_columns(df))
    return [
        col
        for col in df.select_dtypes(include="number").columns
        if col not in metadata
    ]


def _resolve_relative_path(base: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return base / path


def _candidate_paths_from_dictionary(loader, dataset_name: str, field_names: Iterable[str]) -> list[Path]:
    folder = dataset_folder(loader, dataset_name)
    fields = {name.lower() for name in field_names}
    candidates: list[Path] = []

    dictionary = getattr(loader, "dict", None)
    if isinstance(dictionary, pd.DataFrame):
        dflat = dataframe_with_index_columns(dictionary)
        mask = pd.Series(False, index=dflat.index)
        for col in ["tabular_field_name", "field_string", "relative_location"]:
            if col in dflat:
                values = dflat[col].astype(str).str.lower()
                for field in fields:
                    mask = mask | values.eq(field) | values.str.contains(re.escape(field), na=False)
        for col in ["relative_location", "bulk_dictionary"]:
            if col in dflat:
                for raw in dflat.loc[mask, col].dropna().unique():
                    text = clean_path_value(raw)
                    if text:
                        candidates.append(_resolve_relative_path(folder.parent, text))
                        candidates.append(_resolve_relative_path(folder, text))

    primary = load_oral_primary_table(loader) if dataset_name == "oral_microbiome" else load_table_from_loader(loader, dataset_name, dataset_name, required=False)
    if primary is not None:
        for field in field_names:
            if field in primary.columns:
                for raw in primary[field].dropna().unique()[:50]:
                    text = clean_path_value(raw)
                    if text:
                        candidates.append(_resolve_relative_path(folder, text))
                        candidates.append(_resolve_relative_path(folder.parent, text))

    for field in field_names:
        candidates.extend(
            [
                folder / f"{field}.parquet",
                folder / f"{field}.arrow",
                folder / f"{field}.feather",
                folder / f"{field}.tsv",
            ]
        )
        if field.endswith("_parquet"):
            stem = field[: -len("_parquet")]
            candidates.extend([folder / f"{stem}.parquet", folder / f"{stem}.arrow"])
        if field.endswith("_arrow"):
            stem = field[: -len("_arrow")]
            candidates.extend([folder / f"{stem}.arrow", folder / f"{stem}.feather"])

    seen: set[str] = set()
    out: list[Path] = []
    for path in candidates:
        key = str(path)
        if key not in seen:
            seen.add(key)
            out.append(path)
    return out


def _read_any_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".parquet", ".pq"}:
        return dataframe_with_index_columns(pd.read_parquet(path))
    if suffix in {".arrow", ".feather"}:
        return dataframe_with_index_columns(pd.read_feather(path))
    if suffix in {".tsv", ".txt"}:
        return dataframe_with_index_columns(pd.read_csv(path, sep="\t"))
    if suffix == ".csv":
        return dataframe_with_index_columns(pd.read_csv(path))
    raise ValueError(f"Unsupported oral microbiome table format: {path}")



def load_oral_primary_table(loader) -> pd.DataFrame | None:
    """Load the main oral_microbiome table using the documented PhenoLoader pattern."""
    primary = table_from_loader_getitem(loader, "oral_microbiome")
    if primary is not None:
        return primary
    primary = load_table_from_loader(loader, "oral_microbiome", "oral_microbiome", required=False)
    if primary is not None:
        return primary
    try:
        table = loader[["oral_microbiome"]]
    except Exception:
        return None
    if isinstance(table, pd.Series):
        table = table.to_frame()
    if isinstance(table, pd.DataFrame):
        return dataframe_with_index_columns(table)
    return None


def load_oral_bulk_table(loader, field_names: Iterable[str], *, required: bool = False) -> tuple[str | None, pd.DataFrame | None]:
    dataset_name = "oral_microbiome"
    for field in field_names:
        table = load_table_from_loader(loader, dataset_name, field, required=False)
        if table is not None:
            return field, table
    for path in _candidate_paths_from_dictionary(loader, dataset_name, field_names):
        if path.exists():
            return str(path), _read_any_table(path)
    if required:
        raise FileNotFoundError(f"Could not find any oral microbiome table for: {list(field_names)}")
    return None, None


def normalize_abundance_table(df: pd.DataFrame, *, prefix: str) -> pd.DataFrame:
    """Return a wide participant-by-feature numeric matrix."""
    out = dataframe_with_index_columns(df)
    participant_cols = _participant_columns(out)
    if ID_COL not in out.columns and participant_cols:
        out = out.rename(columns={participant_cols[0]: ID_COL})

    long_name_cols = [
        col
        for col in out.columns
        if re.search(r"taxon|clade|species|genus|pathway|feature|name", str(col), flags=re.IGNORECASE)
    ]
    value_cols = [
        col
        for col in out.select_dtypes(include="number").columns
        if re.search(r"abundance|coverage|relative|value|count|rpm|cpm", str(col), flags=re.IGNORECASE)
    ]

    if ID_COL in out.columns and long_name_cols and value_cols and len(value_cols) <= 3:
        name_col = long_name_cols[0]
        value_col = value_cols[0]
        wide = out.pivot_table(index=ID_COL, columns=name_col, values=value_col, aggfunc="mean", fill_value=0)
        wide.columns = [f"{prefix}__{_clean_feature_name(col)}" for col in wide.columns]
        return wide.reset_index()

    features = _feature_columns(out)
    if ID_COL in out.columns and features:
        keep = [ID_COL] + features
        wide = out[keep].copy()
        rename = {col: f"{prefix}__{_clean_feature_name(col)}" for col in features}
        wide = wide.rename(columns=rename)
        return wide.groupby(ID_COL, as_index=False).mean(numeric_only=True)

    # Some bulk mapping tables are feature x sample. Transpose when columns look
    # like sample/participant identifiers and rows carry feature labels.
    if long_name_cols:
        feature_col = long_name_cols[0]
        numeric = out.set_index(feature_col).select_dtypes(include="number")
        if numeric.shape[1] > 1:
            wide = numeric.T.reset_index().rename(columns={"index": ID_COL})
            wide.columns = [
                ID_COL if col == ID_COL else f"{prefix}__{_clean_feature_name(col)}"
                for col in wide.columns
            ]
            return wide

    raise ValueError(
        "Could not normalize oral microbiome table. Expected either a participant "
        "column plus numeric feature columns, a long participant-feature-value table, "
        "or a feature-by-sample numeric matrix."
    )


def participant_lookup_from_primary(loader) -> dict[str, str]:
    primary = load_oral_primary_table(loader)
    if primary is None or ID_COL not in primary.columns:
        return {}
    key_cols = [
        col
        for col in [
            ID_COL,
            "sample_name",
            "sample_id",
            "wgs_dna_code",
            "run_name",
            "raw_fastq",
            "trimmed_fastq",
            "metaphlan4_results_tsv",
        ]
        if col in primary.columns
    ]
    lookup: dict[str, str] = {}
    for _, row in primary[[ID_COL] + [col for col in key_cols if col != ID_COL]].dropna(subset=[ID_COL]).iterrows():
        participant = str(row[ID_COL])
        for col in key_cols:
            raw = row.get(col)
            text = clean_path_value(raw)
            if not text:
                continue
            lookup[text] = participant
            lookup[Path(text).name] = participant
            lookup[Path(text).stem] = participant
    return lookup


def apply_participant_lookup(matrix: pd.DataFrame, lookup: dict[str, str]) -> pd.DataFrame:
    if not lookup or ID_COL not in matrix.columns:
        return matrix
    out = matrix.copy()
    ids = out[ID_COL].astype(str)
    mapped = ids.map(lookup)
    if mapped.notna().mean() >= 0.5:
        out[ID_COL] = mapped.fillna(ids)
        numeric_cols = [col for col in out.select_dtypes(include="number").columns if col != ID_COL]
        if numeric_cols:
            out = out.groupby(ID_COL, as_index=False)[numeric_cols].mean()
    return out


def alpha_diversity_from_abundance(abundance: pd.DataFrame, *, prefix: str) -> pd.DataFrame:
    features = [col for col in abundance.select_dtypes(include="number").columns if col != ID_COL]
    x = abundance[features].clip(lower=0).fillna(0).to_numpy(dtype=float)
    row_sums = x.sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        p = np.divide(x, row_sums[:, None], out=np.zeros_like(x), where=row_sums[:, None] > 0)
        logp = np.where(p > 0, np.log(p), 0.0)
    shannon = -(p * logp).sum(axis=1)
    simpson = 1.0 - (p**2).sum(axis=1)
    richness = (x > 0).sum(axis=1)
    return pd.DataFrame(
        {
            ID_COL: abundance[ID_COL].astype(str).to_numpy(),
            f"{prefix}_shannon": shannon,
            f"{prefix}_simpson": simpson,
            f"{prefix}_richness": richness,
            f"{prefix}_total_abundance": row_sums,
        }
    )


def nitrate_reducer_features(abundance: pd.DataFrame, *, taxonomic_level: str) -> pd.DataFrame:
    numeric_cols = [col for col in abundance.select_dtypes(include="number").columns if col != ID_COL]
    out = pd.DataFrame({ID_COL: abundance[ID_COL].astype(str)})
    matched_any: list[str] = []
    for taxon, pattern in NITRATE_REDUCER_TAXA.items():
        regex = re.compile(pattern, flags=re.IGNORECASE)
        matches = [col for col in numeric_cols if regex.search(col.replace("__", "_"))]
        out[f"oral_{taxonomic_level}_nitrate_reducer__{taxon}"] = (
            abundance[matches].sum(axis=1) if matches else 0.0
        )
        matched_any.extend(matches)
    out[f"oral_{taxonomic_level}_nitrate_reducer__total"] = (
        abundance[sorted(set(matched_any))].sum(axis=1) if matched_any else 0.0
    )
    out[f"oral_{taxonomic_level}_nitrate_reducer__matched_feature_count"] = len(set(matched_any))
    return out


def nitrate_pathway_candidates(pathway_table: pd.DataFrame) -> pd.DataFrame:
    numeric_cols = [col for col in pathway_table.select_dtypes(include="number").columns if col != ID_COL]
    matches = [col for col in numeric_cols if NITRATE_PATHWAY_PATTERN.search(col)]
    keep = [ID_COL] + matches
    out = pathway_table[keep].copy() if matches else pathway_table[[ID_COL]].copy()
    if matches:
        out["oral_humann_nitrogen_pathway__total"] = out[matches].sum(axis=1)
    out["oral_humann_nitrogen_pathway__matched_feature_count"] = len(matches)
    return out


def merge_on_participant(tables: list[pd.DataFrame]) -> pd.DataFrame:
    merged: pd.DataFrame | None = None
    for table in tables:
        if table is None or table.empty:
            continue
        table = table.copy()
        table[ID_COL] = table[ID_COL].astype(str)
        merged = table if merged is None else merged.merge(table, on=ID_COL, how="outer")
    return merged if merged is not None else pd.DataFrame(columns=[ID_COL])


def prepare_oral_microbiome_outputs(output_dir: Path, *, errors: str = "warn") -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    loader = make_loader("oral_microbiome", age_sex_dataset=None, errors=errors)
    participant_lookup = participant_lookup_from_primary(loader)

    exports: dict[str, dict] = {}
    derived_for_summary: list[pd.DataFrame] = []

    for level, fields in METAPHLAN_FIELDS.items():
        source, raw = load_oral_bulk_table(loader, fields, required=False)
        if raw is None:
            exports[f"metaphlan_{level}"] = {"status": "missing", "tried_fields": fields}
            continue
        matrix = normalize_abundance_table(raw, prefix=f"oral_metaphlan_{level}")
        matrix = apply_participant_lookup(matrix, participant_lookup)
        matrix_path = write_table(matrix, output_dir / f"oral_metaphlan_{level}_abundance.parquet")
        alpha = alpha_diversity_from_abundance(matrix, prefix=f"oral_{level}")
        alpha_path = write_table(alpha, output_dir / f"oral_{level}_alpha_diversity.parquet")
        reducer = nitrate_reducer_features(matrix, taxonomic_level=level)
        reducer_path = write_table(reducer, output_dir / f"oral_{level}_nitrate_reducer_features.parquet")
        derived_for_summary.extend([alpha, reducer])
        exports[f"metaphlan_{level}"] = {
            "status": "exported",
            "source": source,
            "abundance_path": str(matrix_path),
            "alpha_diversity_path": str(alpha_path),
            "nitrate_reducer_features_path": str(reducer_path),
            "rows": int(len(matrix)),
            "features": int(len(matrix.columns) - 1),
        }

    for kind, fields in HUMANN_FIELDS.items():
        source, raw = load_oral_bulk_table(loader, fields, required=False)
        if raw is None:
            exports[f"humann_{kind}"] = {"status": "missing", "tried_fields": fields}
            continue
        matrix = normalize_abundance_table(raw, prefix=f"oral_humann_{kind}")
        matrix = apply_participant_lookup(matrix, participant_lookup)
        matrix_path = write_table(matrix, output_dir / f"oral_humann_{kind}.parquet")
        candidates = nitrate_pathway_candidates(matrix)
        candidates_path = write_table(candidates, output_dir / f"oral_humann_{kind}_nitrogen_pathway_candidates.parquet")
        derived_for_summary.append(candidates)
        exports[f"humann_{kind}"] = {
            "status": "exported",
            "source": source,
            "path": str(matrix_path),
            "nitrogen_pathway_candidates_path": str(candidates_path),
            "rows": int(len(matrix)),
            "features": int(len(matrix.columns) - 1),
            "nitrogen_pathway_candidate_features": int(len(candidates.columns) - 2)
            if "oral_humann_nitrogen_pathway__matched_feature_count" in candidates.columns
            else 0,
        }

    summary_table = merge_on_participant(derived_for_summary)
    summary_path = write_table(summary_table, output_dir / "oral_microbiome_nitrate_summary_features.parquet")
    manifest = {
        "dataset": "oral_microbiome",
        "output_dir": str(output_dir),
        "exports": exports,
        "summary_features_path": str(summary_path),
        "summary_feature_rows": int(len(summary_table)),
        "summary_feature_columns": list(summary_table.columns),
        "participant_lookup_keys": int(len(participant_lookup)),
        "nitrate_reducer_taxa_regex": NITRATE_REDUCER_TAXA,
        "nitrate_pathway_pattern": NITRATE_PATHWAY_PATTERN.pattern,
        "notes": (
            "Candidate nitrate-reducing taxa are genus-level literature-guided "
            "screening features. Confirm exact taxa/pathway labels inside TRE "
            "before interpreting biology."
        ),
    }
    write_manifest(manifest, output_dir / "oral_microbiome_preprocess_manifest.json")
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare oral microbiome features for nitrate/nitrite discovery analyses."
    )
    parser.add_argument("--output-dir", type=Path, default=Path("tre_inputs/oral_microbiome"))
    parser.add_argument("--errors", default="warn")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = prepare_oral_microbiome_outputs(args.output_dir, errors=args.errors)
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
