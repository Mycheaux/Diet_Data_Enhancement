import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .sources import ROOT
from .text import name_similarity, unicode_name_similarity


OUT = ROOT / "outputs"
VALIDATION = OUT / "validation"
NUTRIMATCH_DIR = ROOT / "data/Nutrimatch"
NUTRIMATCH_PARQUET = NUTRIMATCH_DIR / "imputed_nutrients_table.parquet"


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))


def _numeric(df):
    return df.apply(pd.to_numeric, errors="coerce")


def _weighted_mean(values, weights):
    values = pd.to_numeric(values, errors="coerce")
    weights = pd.to_numeric(weights, errors="coerce").fillna(1).clip(lower=0)
    mask = values.notna()
    if not mask.any():
        return np.nan
    if weights[mask].sum() == 0:
        weights = pd.Series(1, index=weights.index)
    return float((values[mask] * weights[mask]).sum() / weights[mask].sum())


def load_nutrimatch_hpp():
    if not NUTRIMATCH_PARQUET.exists():
        raise FileNotFoundError(NUTRIMATCH_PARQUET)
    raw = pd.read_parquet(NUTRIMATCH_PARQUET)
    if isinstance(raw.index, pd.MultiIndex) and "dataset" in raw.index.names:
        hpp = raw.xs("HPP", level="dataset").copy()
    else:
        hpp = raw.copy()
    hpp.index.name = "hebrew_name"
    hpp = hpp.reset_index()
    return hpp


def nutrimatch_hpp_with_ids():
    hpp_nm = load_nutrimatch_hpp()
    catalog = pd.read_csv(
        ROOT / "data/HPP/hpp_food_items_with_nutrients.csv",
        dtype={"food_id": str},
        usecols=["food_id", "hebrew_name", "number_loggings"],
    ).rename(columns={"food_id": "hpp_food_id"})
    joined = hpp_nm.merge(catalog, on="hebrew_name", how="left", validate="one_to_one")
    return joined


def canonicalize_nutrimatch():
    nm = nutrimatch_hpp_with_ids()
    crosswalk = pd.read_csv(OUT / "canonical/hpp_to_canonical.csv", dtype=str)
    crosswalk = crosswalk[["hpp_food_id", "canonical_food_id", "canonical_name", "canonical_category"]]
    nm = nm.merge(crosswalk, on="hpp_food_id", how="left")
    nutrient_cols = [
        col
        for col in nm.columns
        if col
        not in {
            "hebrew_name",
            "hpp_food_id",
            "number_loggings",
            "canonical_food_id",
            "canonical_name",
            "canonical_category",
        }
    ]
    rows = []
    for cid, group in nm.groupby("canonical_food_id", dropna=False, sort=True):
        if pd.isna(cid):
            continue
        row = {
            "canonical_food_id": cid,
            "canonical_name": group["canonical_name"].iloc[0],
            "canonical_category": group["canonical_category"].iloc[0],
            "hpp_food_count": int(group["hpp_food_id"].nunique()),
        }
        for nutrient in nutrient_cols:
            row[nutrient] = _weighted_mean(group[nutrient], group["number_loggings"])
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["canonical_name", "canonical_category"])


def compare_nutrimatch_to_layer1():
    VALIDATION.mkdir(parents=True, exist_ok=True)
    nm_hpp = nutrimatch_hpp_with_ids()
    nm_canonical = canonicalize_nutrimatch()
    ours = pd.read_csv(OUT / "nutrients/canonical_nutrient_profiles.csv")
    provenance = pd.read_csv(OUT / "nutrients/canonical_nutrient_provenance.csv")
    hpp_raw = pd.read_csv(ROOT / "data/HPP/hpp_food_items_with_nutrients.csv", dtype={"food_id": str})
    crosswalk = pd.read_csv(OUT / "canonical/hpp_to_canonical.csv", dtype=str)
    layer1 = pd.read_csv(OUT / "layered/layer1_nutrient_candidates.csv", dtype=str)
    hitl = pd.read_csv(OUT / "layered/hitl_review_queue.csv", dtype=str)

    identity_cols = {"canonical_food_id", "canonical_name", "canonical_category", "hpp_food_count"}
    ours_nutrients = [col for col in ours.columns if col not in identity_cols]
    nm_nutrients = [col for col in nm_canonical.columns if col not in identity_cols]
    shared = sorted(set(ours_nutrients).intersection(nm_nutrients))
    ours_only = sorted(set(ours_nutrients) - set(nm_nutrients))
    nm_only = sorted(set(nm_nutrients) - set(ours_nutrients))

    joined = ours[["canonical_food_id", "canonical_name", "canonical_category"] + shared].merge(
        nm_canonical[["canonical_food_id"] + shared],
        on="canonical_food_id",
        how="inner",
        suffixes=("_ours", "_nutrimatch"),
    )

    diff_rows = []
    for nutrient in shared:
        left = pd.to_numeric(joined[f"{nutrient}_ours"], errors="coerce")
        right = pd.to_numeric(joined[f"{nutrient}_nutrimatch"], errors="coerce")
        mask = left.notna() & right.notna()
        if not mask.any():
            continue
        abs_diff = (left[mask] - right[mask]).abs()
        denom = right[mask].abs().replace(0, np.nan)
        rel_diff = abs_diff / denom
        diff_rows.append(
            {
                "nutrient_name": nutrient,
                "compared_canonical_foods": int(mask.sum()),
                "mean_abs_difference": float(abs_diff.mean()),
                "median_abs_difference": float(abs_diff.median()),
                "p95_abs_difference": float(abs_diff.quantile(0.95)),
                "max_abs_difference": float(abs_diff.max()),
                "mean_relative_difference_nonzero_nutrimatch": float(rel_diff.dropna().mean())
                if rel_diff.notna().any()
                else np.nan,
                "exact_match_percent": float(100 * np.isclose(left[mask], right[mask], rtol=1e-9, atol=1e-9).mean()),
            }
        )
    nutrient_agreement = pd.DataFrame(diff_rows).sort_values(
        ["mean_abs_difference", "nutrient_name"], ascending=[False, True]
    )

    top_l1 = (
        layer1.sort_values(["canonical_food_id", "candidate_rank"])
        .groupby("canonical_food_id", as_index=False)
        .head(1)
    )
    top_conf = top_l1["confidence"].value_counts().to_dict()
    accepted_conf = (
        hitl[hitl["review_status"].eq("auto_accept")]["nutrient_confidence"].value_counts().to_dict()
        if "review_status" in hitl
        else {}
    )
    pending_conf = (
        hitl[hitl["review_status"].eq("pending")]["nutrient_confidence"].value_counts().to_dict()
        if "review_status" in hitl
        else {}
    )

    coverage_rows = []
    for label, df, nutrient_cols in [
        ("NutriMatch-derived HPP panel, HPP-food level", nm_hpp, nm_nutrients),
        ("NutriMatch-derived HPP panel, canonical level", nm_canonical, nm_nutrients),
        ("This project Layer 1 canonical nutrient panel", ours, ours_nutrients),
        ("This project Layer 1 canonical panel, shared nutrients only", ours, shared),
    ]:
        numeric = _numeric(df[nutrient_cols])
        nonnull = numeric.notna()
        nonzero = numeric.fillna(0).ne(0)
        coverage_rows.append(
            {
                "panel": label,
                "food_rows": int(df.shape[0]),
                "nutrient_columns": int(len(nutrient_cols)),
                "non_null_cell_percent": round(100 * nonnull.to_numpy().mean(), 3) if len(nutrient_cols) else 0,
                "nonzero_cell_percent": round(100 * nonzero.to_numpy().mean(), 3) if len(nutrient_cols) else 0,
                "median_nonzero_nutrients_per_food": float(nonzero.sum(axis=1).median()) if len(nutrient_cols) else 0,
                "p05_nonzero_nutrients_per_food": float(nonzero.sum(axis=1).quantile(0.05)) if len(nutrient_cols) else 0,
                "p95_nonzero_nutrients_per_food": float(nonzero.sum(axis=1).quantile(0.95)) if len(nutrient_cols) else 0,
            }
        )
    coverage = pd.DataFrame(coverage_rows)

    provenance_summary = (
        provenance.groupby(["chosen_source", "method"], dropna=False)
        .agg(nutrient_values=("nutrient_name", "count"), canonical_foods=("canonical_food_id", "nunique"))
        .reset_index()
        .sort_values("nutrient_values", ascending=False)
    )

    food_level_summary = pd.DataFrame(
        [
            {"metric": "HPP food rows in raw HPP table", "value": int(hpp_raw["food_id"].nunique())},
            {"metric": "NutriMatch HPP rows", "value": int(nm_hpp.shape[0])},
            {"metric": "NutriMatch HPP rows joined to HPP food_id", "value": int(nm_hpp["hpp_food_id"].notna().sum())},
            {"metric": "Canonical foods after HPP collapse", "value": int(crosswalk["canonical_food_id"].nunique())},
            {"metric": "Layer 1 canonical foods with top candidate", "value": int(top_l1["canonical_food_id"].nunique())},
            {"metric": "Layer 1 high/medium top candidates", "value": int(top_l1["confidence"].isin(["high", "medium"]).sum())},
            {"metric": "Layer 1 low/review top candidates", "value": int(top_l1["confidence"].isin(["low", "review"]).sum())},
            {"metric": "Layered HITL pending canonical foods", "value": int((hitl["review_status"] == "pending").sum())},
            {"metric": "Layered HITL auto-accepted canonical foods", "value": int((hitl["review_status"] == "auto_accept").sum())},
            {"metric": "Shared nutrient columns", "value": int(len(shared))},
            {"metric": "This project nutrient columns", "value": int(len(ours_nutrients))},
            {"metric": "NutriMatch nutrient columns", "value": int(len(nm_nutrients))},
            {"metric": "This project extra nutrient-like columns", "value": int(len(ours_only))},
            {"metric": "NutriMatch-only nutrient columns", "value": int(len(nm_only))},
        ]
    )

    if not nutrient_agreement.empty:
        exact_all = float(
            nutrient_agreement["exact_match_percent"].mul(nutrient_agreement["compared_canonical_foods"]).sum()
            / nutrient_agreement["compared_canonical_foods"].sum()
        )
    else:
        exact_all = np.nan

    summary = {
        "comparison_scope": (
            "NutriMatch file is an imputed nutrient panel, not a row-level mapping/provenance table. "
            "Evaluation therefore compares resulting nutrient panels and auditability, not direct donor-food choices."
        ),
        "nutrimatch_rows_total": int(pd.read_parquet(NUTRIMATCH_PARQUET).shape[0]),
        "nutrimatch_hpp_rows": int(nm_hpp.shape[0]),
        "nutrimatch_hpp_joined_to_food_id": int(nm_hpp["hpp_food_id"].notna().sum()),
        "canonical_food_count": int(crosswalk["canonical_food_id"].nunique()),
        "shared_nutrient_columns": int(len(shared)),
        "our_nutrient_columns": int(len(ours_nutrients)),
        "nutrimatch_nutrient_columns": int(len(nm_nutrients)),
        "our_extra_columns": ours_only,
        "nutrimatch_only_columns": nm_only,
        "weighted_exact_match_percent_on_shared_canonical_values": exact_all,
        "layer1_top_candidate_confidence_counts": top_conf,
        "hitl_auto_accept_nutrient_confidence_counts": accepted_conf,
        "hitl_pending_nutrient_confidence_counts": pending_conf,
        "outputs": {
            "summary_metrics": str(VALIDATION / "nutrimatch_comparison_summary_metrics.csv"),
            "coverage": str(VALIDATION / "nutrimatch_comparison_coverage.csv"),
            "nutrient_agreement": str(VALIDATION / "nutrimatch_comparison_nutrient_agreement.csv"),
            "provenance_summary": str(VALIDATION / "nutrimatch_comparison_provenance_summary.csv"),
            "canonicalized_nutrimatch": str(VALIDATION / "nutrimatch_canonical_nutrient_profiles.csv"),
            "summary_json": str(VALIDATION / "nutrimatch_comparison_summary.json"),
        },
    }

    nm_canonical.to_csv(VALIDATION / "nutrimatch_canonical_nutrient_profiles.csv", index=False)
    food_level_summary.to_csv(VALIDATION / "nutrimatch_comparison_summary_metrics.csv", index=False)
    coverage.to_csv(VALIDATION / "nutrimatch_comparison_coverage.csv", index=False)
    nutrient_agreement.to_csv(VALIDATION / "nutrimatch_comparison_nutrient_agreement.csv", index=False)
    provenance_summary.to_csv(VALIDATION / "nutrimatch_comparison_provenance_summary.csv", index=False)
    _write_json(VALIDATION / "nutrimatch_comparison_summary.json", summary)
    return summary


SOURCE_NORMALIZATION = {
    "USDA_SR_Legacy": "SR_Legacy",
    "USDA_FNDDS": "FNDDS",
    "Tzameret_Israel": "Zameret",
}


def _standardized_log_matrix(df, mean=None, std=None):
    values = np.log1p(df.apply(pd.to_numeric, errors="coerce").fillna(0).clip(lower=0).to_numpy(dtype=float))
    if mean is None:
        mean = values.mean(axis=0)
    if std is None:
        std = values.std(axis=0)
        std[std == 0] = 1
    values = (values - mean) / std
    norms = np.linalg.norm(values, axis=1, keepdims=True)
    values = values / np.clip(norms, 1e-12, None)
    return values, mean, std


def infer_nutrimatch_donor_mapping(chunk_size=256):
    """Infer likely NutriMatch donor rows by nutrient-vector nearest neighbors.

    The NutriMatch bundle does not include the actual donor-food mapping table.
    This function therefore reverse-infers the closest non-HPP row for each HPP
    row using cosine similarity over the 153 shared nutrient columns.
    """
    VALIDATION.mkdir(parents=True, exist_ok=True)
    raw = pd.read_parquet(NUTRIMATCH_PARQUET)
    source = raw[raw.index.get_level_values("dataset") != "HPP"].copy()
    hpp = raw.xs("HPP", level="dataset").copy()
    nutrient_cols = list(raw.columns)

    combined_numeric = pd.concat([hpp[nutrient_cols], source[nutrient_cols]], axis=0)
    _, mean, std = _standardized_log_matrix(combined_numeric)
    source_x, _, _ = _standardized_log_matrix(source[nutrient_cols], mean=mean, std=std)
    hpp_x, _, _ = _standardized_log_matrix(hpp[nutrient_cols], mean=mean, std=std)
    source_index = source.index.to_frame(index=False).reset_index(drop=True)

    best_rows = []
    for start in range(0, hpp_x.shape[0], chunk_size):
        end = min(start + chunk_size, hpp_x.shape[0])
        scores = hpp_x[start:end] @ source_x.T
        best_idx = scores.argmax(axis=1)
        best_score = scores[np.arange(end - start), best_idx]
        hpp_names = hpp.index[start:end]
        for local_idx, source_idx in enumerate(best_idx):
            source_row = source_index.iloc[int(source_idx)]
            best_rows.append(
                {
                    "hebrew_name": hpp_names[local_idx],
                    "nutrimatch_inferred_dataset": source_row["dataset"],
                    "nutrimatch_inferred_food_name": source_row["food_name"],
                    "nutrimatch_inferred_vector_similarity": round(float(best_score[local_idx]), 6),
                    "inference_method": "nearest_non_hpp_nutrient_vector_cosine_log1p_zscore",
                }
            )
    inferred = pd.DataFrame(best_rows)
    catalog = pd.read_csv(
        ROOT / "data/HPP/hpp_food_items_with_nutrients.csv",
        dtype={"food_id": str},
        usecols=["food_id", "hebrew_name", "number_loggings"],
    ).rename(columns={"food_id": "hpp_food_id"})
    inferred = inferred.merge(catalog, on="hebrew_name", how="left")
    crosswalk = pd.read_csv(OUT / "canonical/hpp_to_canonical.csv", dtype=str)
    inferred = inferred.merge(
        crosswalk[
            [
                "hpp_food_id",
                "hpp_food_name",
                "canonical_food_id",
                "canonical_name",
                "canonical_category",
            ]
        ],
        on="hpp_food_id",
        how="left",
    )
    inferred["number_loggings"] = pd.to_numeric(inferred["number_loggings"], errors="coerce").fillna(0)
    inferred_path = VALIDATION / "nutrimatch_inferred_hpp_donor_mapping.csv"
    inferred.to_csv(inferred_path, index=False)

    canonical_rows = []
    for cid, group in inferred.groupby("canonical_food_id", sort=True):
        if pd.isna(cid):
            continue
        weighted = (
            group.groupby(["nutrimatch_inferred_dataset", "nutrimatch_inferred_food_name"], dropna=False)
            .agg(
                hpp_food_count=("hpp_food_id", "nunique"),
                total_loggings=("number_loggings", "sum"),
                mean_vector_similarity=("nutrimatch_inferred_vector_similarity", "mean"),
                max_vector_similarity=("nutrimatch_inferred_vector_similarity", "max"),
            )
            .reset_index()
            .sort_values(["total_loggings", "hpp_food_count", "mean_vector_similarity"], ascending=False)
        )
        top = weighted.iloc[0]
        canonical_rows.append(
            {
                "canonical_food_id": cid,
                "canonical_name": group["canonical_name"].iloc[0],
                "canonical_category": group["canonical_category"].iloc[0],
                "hpp_food_count": int(group["hpp_food_id"].nunique()),
                "nutrimatch_inferred_dataset": top["nutrimatch_inferred_dataset"],
                "nutrimatch_inferred_food_name": top["nutrimatch_inferred_food_name"],
                "nutrimatch_inferred_hpp_food_count": int(top["hpp_food_count"]),
                "nutrimatch_inferred_total_loggings": float(top["total_loggings"]),
                "nutrimatch_inferred_mean_vector_similarity": float(top["mean_vector_similarity"]),
                "nutrimatch_inferred_max_vector_similarity": float(top["max_vector_similarity"]),
            }
        )
    canonical_inferred = pd.DataFrame(canonical_rows)
    canonical_path = VALIDATION / "nutrimatch_inferred_canonical_donor_mapping.csv"
    canonical_inferred.to_csv(canonical_path, index=False)
    return inferred, canonical_inferred


def compare_inferred_nutrimatch_mapping_to_layer1():
    VALIDATION.mkdir(parents=True, exist_ok=True)
    inferred_hpp_path = VALIDATION / "nutrimatch_inferred_hpp_donor_mapping.csv"
    inferred_canonical_path = VALIDATION / "nutrimatch_inferred_canonical_donor_mapping.csv"
    if inferred_hpp_path.exists() and inferred_canonical_path.exists():
        inferred_hpp = pd.read_csv(inferred_hpp_path, dtype=str)
        inferred = pd.read_csv(inferred_canonical_path, dtype=str)
    else:
        inferred_hpp, inferred = infer_nutrimatch_donor_mapping()

    layer1 = pd.read_csv(OUT / "layered/layer1_nutrient_candidates.csv", dtype=str)
    top_l1 = (
        layer1.sort_values(["canonical_food_id", "candidate_rank"])
        .groupby("canonical_food_id", as_index=False)
        .head(1)
        .copy()
    )
    top_l1["our_nutrimatch_comparable_dataset"] = top_l1["source"].map(SOURCE_NORMALIZATION).fillna("")
    merged = inferred.merge(
        top_l1[
            [
                "canonical_food_id",
                "source",
                "source_food_id",
                "matched_food_name",
                "match_score",
                "confidence",
                "our_nutrimatch_comparable_dataset",
            ]
        ],
        on="canonical_food_id",
        how="left",
    )

    def comparable_name_score(row):
        nm_dataset = row.get("nutrimatch_inferred_dataset", "")
        nm_name = row.get("nutrimatch_inferred_food_name", "")
        if nm_dataset == "Zameret":
            hpp_rows = inferred_hpp[inferred_hpp["canonical_food_id"].eq(row["canonical_food_id"])]
            hebrew = hpp_rows["hebrew_name"].dropna().astype(str)
            query = hebrew.mode().iloc[0] if not hebrew.empty else row.get("canonical_name", "")
            return unicode_name_similarity(query, nm_name)
        return name_similarity(row.get("canonical_name", ""), nm_name)

    merged["nutrimatch_inferred_name_score_to_canonical"] = merged.apply(comparable_name_score, axis=1)
    merged["our_match_score"] = pd.to_numeric(merged["match_score"], errors="coerce")
    merged["nutrimatch_inferred_mean_vector_similarity"] = pd.to_numeric(
        merged["nutrimatch_inferred_mean_vector_similarity"], errors="coerce"
    )
    merged["same_comparable_source"] = (
        merged["nutrimatch_inferred_dataset"].astype(str).eq(merged["our_nutrimatch_comparable_dataset"].astype(str))
    )
    merged["our_source_in_nutrimatch_sources"] = merged["our_nutrimatch_comparable_dataset"].ne("")
    merged["same_name_when_source_matches"] = (
        merged["same_comparable_source"]
        & merged.apply(
            lambda row: name_similarity(row.get("matched_food_name", ""), row.get("nutrimatch_inferred_food_name", "")) >= 0.86
            if row.get("nutrimatch_inferred_dataset", "") != "Zameret"
            else unicode_name_similarity(row.get("matched_food_name", ""), row.get("nutrimatch_inferred_food_name", "")) >= 0.86,
            axis=1,
        )
    )

    def label(row):
        if not row["our_source_in_nutrimatch_sources"]:
            return "not_directly_comparable_our_source_not_in_nutrimatch"
        if row["same_name_when_source_matches"]:
            return "same_source_and_similar_name"
        if row["same_comparable_source"]:
            return "same_source_different_inferred_food"
        return "different_source"

    merged["mapping_agreement_status"] = merged.apply(label, axis=1)

    def priority(row):
        if row["mapping_agreement_status"] == "same_source_and_similar_name":
            return "agreement"
        if row["confidence"] in {"high", "medium"} and row["nutrimatch_inferred_mean_vector_similarity"] >= 0.98:
            return "discordant_both_plausible_review"
        if row["confidence"] in {"low", "review"} and row["nutrimatch_inferred_name_score_to_canonical"] >= 0.72:
            return "nutrimatch_inferred_may_be_better_review"
        if row["confidence"] in {"high", "medium"}:
            return "our_mapping_may_be_better_review"
        return "ambiguous_review"

    merged["review_priority"] = merged.apply(priority, axis=1)

    comparison_path = VALIDATION / "nutrimatch_inferred_vs_our_layer1_mapping_comparison.csv"
    merged.to_csv(comparison_path, index=False)

    summary_rows = []
    summary_rows.append({"metric": "canonical_foods_compared", "value": int(merged.shape[0])})
    summary_rows.append(
        {"metric": "our_layer1_source_in_nutrimatch_source_set", "value": int(merged["our_source_in_nutrimatch_sources"].sum())}
    )
    summary_rows.append({"metric": "same_comparable_source", "value": int(merged["same_comparable_source"].sum())})
    summary_rows.append(
        {"metric": "same_source_and_similar_name", "value": int(merged["same_name_when_source_matches"].sum())}
    )
    for status, count in merged["mapping_agreement_status"].value_counts().items():
        summary_rows.append({"metric": f"agreement_status__{status}", "value": int(count)})
    for status, count in merged["review_priority"].value_counts().items():
        summary_rows.append({"metric": f"review_priority__{status}", "value": int(count)})

    summary = pd.DataFrame(summary_rows)
    summary_path = VALIDATION / "nutrimatch_inferred_mapping_comparison_summary.csv"
    summary.to_csv(summary_path, index=False)
    payload = {
        "important_limitation": (
            "The NutriMatch bundle does not contain the true mapping table. "
            "These are inferred donor rows from nearest non-HPP nutrient-vector similarity."
        ),
        "canonical_foods_compared": int(merged.shape[0]),
        "agreement_status_counts": merged["mapping_agreement_status"].value_counts().to_dict(),
        "review_priority_counts": merged["review_priority"].value_counts().to_dict(),
        "outputs": {
            "hpp_inferred": str(inferred_hpp_path),
            "canonical_inferred": str(inferred_canonical_path),
            "comparison": str(comparison_path),
            "summary": str(summary_path),
            "summary_json": str(VALIDATION / "nutrimatch_inferred_mapping_comparison_summary.json"),
        },
    }
    _write_json(VALIDATION / "nutrimatch_inferred_mapping_comparison_summary.json", payload)
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        nargs="?",
        default="compare",
        choices=["compare", "infer-mapping", "compare-mapping"],
    )
    args = parser.parse_args()
    if args.command == "compare":
        print(json.dumps(compare_nutrimatch_to_layer1(), indent=2))
    elif args.command == "infer-mapping":
        _, canonical = infer_nutrimatch_donor_mapping()
        print(canonical.head(20).to_json(orient="records", indent=2))
    elif args.command == "compare-mapping":
        print(json.dumps(compare_inferred_nutrimatch_mapping_to_layer1(), indent=2))


if __name__ == "__main__":
    main()
