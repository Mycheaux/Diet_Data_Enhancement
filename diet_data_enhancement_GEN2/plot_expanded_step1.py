"""Plot the next five-food checkpoint and the full source-catalogue disposition."""

import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", tempfile.mkdtemp(prefix="gen2-expansion-plot-"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .expand_step1 import OUT as DENOVO
from .independent_pilot import OUT as APPROVED, digest, write_json


def main():
    out = DENOVO.parent
    matrix = pd.read_csv(DENOVO / "food_features.csv", dtype={"hpp_food_id": str})
    registry = pd.read_csv(DENOVO / "nutrient_registry.csv")
    summary = json.loads((DENOVO / "summary.json").read_text())
    previous = json.loads((APPROVED / "summary.json").read_text())
    mapping = pd.read_csv(DENOVO / "reviewed_donor_decisions.csv", dtype={"hpp_food_id": str}).set_index("hpp_food_id")
    labels = mapping.loc[matrix.hpp_food_id, "panel_label"].tolist()
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(2, 1, figsize=(12.5, 6.5), gridspec_kw={"height_ratios": [1.05, 1]})
    cols = ["usda_1259_g_per_100g", "usda_1263_g_per_100g", "usda_1265_g_per_100g", "usda_1266_g_per_100g", "usda_1275_g_per_100g"]
    labels_col = ["SFA 4:0\ng/100 g", "SFA 12:0\ng/100 g", "SFA 16:0\ng/100 g", "SFA 18:0\ng/100 g", "MUFA 16:1\ng/100 g"]
    for ax in axes:
        ax.axis("off")
    numeric = [[f"{v:.4g}" for v in row] for row in matrix[cols].to_numpy()]
    table = axes[0].table(cellText=[[label] + vals for label, vals in zip(labels, numeric)],
                          colLabels=["Food"] + labels_col, cellLoc="center", colWidths=[.24] + [.152] * 5,
                          bbox=[0, 0, 1, .92])
    attr_cols = ["identity_preparation_evidence", "identity_fermentation_evidence", "identity_grain_refinement_evidence"]
    readable = {"espresso_extraction_named": "Espresso extraction", "cooked_method_unspecified": "Cooked, method unknown",
                "pastrami_named": "Pastrami", "sourdough_bread_named": "Sourdough bread", "yogurt_named": "Yogurt",
                "sourdough_named": "Sourdough", "whole_wheat_named": "Whole wheat", "not_stated": "Not stated"}
    attrs = [[readable[v] for v in row] for row in matrix[attr_cols].to_numpy()]
    table2 = axes[1].table(cellText=[[label] + vals for label, vals in zip(labels, attrs)],
                           colLabels=["Food", "Preparation evidence", "Fermentation evidence", "Grain refinement evidence"],
                           colWidths=[.24, .27, .245, .245], cellLoc="center", bbox=[0, 0, 1, .92])
    for table_item in (table, table2):
        table_item.auto_set_font_size(False)
        table_item.set_fontsize(10)
        for (row, col), cell in table_item.get_celld().items():
            cell.set_edgecolor("#D5DCDA")
            cell.set_facecolor("#DCEAE6" if row == 0 else "#FFFFFF" if row % 2 else "#F2F5F4")
            if row == 0:
                cell.set_text_props(weight="bold")
            if cell.get_text().get_text() == "Not stated":
                cell.set_facecolor("#FAEDD0")
    axes[0].set_title(f"Examples from {summary['added_nutrient_columns']} additional nutrients", loc="left", fontsize=12, pad=3)
    axes[1].set_title("Original food descriptions: no donor assumptions added", loc="left", fontsize=12, pad=3)
    fig.suptitle("Step 1 checkpoint: what the five foods gained", x=.04, ha="left", fontsize=15)
    fig.text(.04, .025, "Nutrient values are reference-food transfers, not target-food measurements. 'Not stated' is unknown, not absence.", fontsize=10)
    fig.tight_layout(rect=(.025, .06, .985, .95), h_pad=1.9)
    fig.savefig(out / "five_food_expansion.png", dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(12, 5.5), gridspec_kw={"width_ratios": [1.05, 1.4]})
    left = np.zeros(2)
    for values, label, color in [([previous["nutrient_columns"], summary["nutrient_columns"]], "Nutrients", "#287E71"),
                                  ([previous["derived_columns"], summary["derived_columns"]], "Existing formulas", "#6078B2"),
                                  ([0, summary["identity_descriptor_columns"]], "Identity fields", "#D5A238")]:
        axes[0].barh([0, 1], values, left=left, label=label, color=color, height=.5)
        for i, v in enumerate(values):
            if v:
                axes[0].text(left[i] + v / 2, i, str(v), ha="center", va="center", fontsize=10, color="white" if label != "Identity fields" else "black")
        left += np.array(values)
    axes[0].set_yticks([0, 1], ["Approved pilot", "Expanded pilot"])
    axes[0].invert_yaxis()
    axes[0].set_xlim(0, 106)
    axes[0].set_xlabel("Feature columns (food IDs and names excluded)")
    axes[0].set_title(f"{previous['feature_columns']} to {summary['feature_columns']} columns", loc="left")
    handles, legend_labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, legend_labels, loc="lower left", bbox_to_anchor=(.025, .08), ncol=3, frameon=False, fontsize=9)
    counts = registry.status.value_counts()
    counts["excluded_representations"] = counts.get("unit_alias", 0) + counts.get("alternate_activity_convention", 0)
    statuses = ["included", "completion_pending", "source_label_review", "excluded_representations"]
    colors = ["#287E71", "#D5A238", "#AC5660", "#8D969E"]
    axes[1].barh(range(4), [counts.get(s, 0) for s in statuses], color=colors, height=.55)
    axes[1].set_yticks(range(4), ["Included", "Needs completion", "Needs identity review", "Alternate representations"])
    axes[1].invert_yaxis()
    axes[1].set_xlim(0, 101)
    for i, s in enumerate(statuses):
        axes[1].text(counts.get(s, 0) + 1.5, i, str(counts.get(s, 0)), va="center")
    axes[1].set_xlabel("Source nutrient IDs")
    axes[1].set_title("All 149 source nutrient IDs accounted for", loc="left")
    fig.suptitle("Coverage is a checkpoint, not final completeness", x=.025, ha="left", fontsize=14)
    fig.text(.025, .025, f"{summary['filled_numeric_cells']}/{summary['filled_numeric_cells']} included numeric cells populated; 7/20 identity cells explicitly unknown. 60 nutrient candidates remain pending.", fontsize=10)
    fig.tight_layout(rect=(0, .19, 1, .94), w_pad=2.5)
    fig.savefig(out / "catalogue_coverage.png", dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    write_json("figure_manifest.json", {"code_sha256": digest(Path(__file__)), "matplotlib": matplotlib.__version__,
               "inputs": {name: digest(DENOVO / name) for name in ["food_features.csv", "nutrient_registry.csv", "reviewed_donor_decisions.csv", "summary.json"]},
               "approved_pilot_summary_sha256": digest(APPROVED / "summary.json"),
               "figures": {name: digest(out / name) for name in ["five_food_expansion.png", "catalogue_coverage.png"]}}, out)


if __name__ == "__main__":
    main()
