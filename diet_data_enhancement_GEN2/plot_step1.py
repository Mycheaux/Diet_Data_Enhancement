"""Render static checkpoint figures from the Step 1 audit tables."""

import os
import tempfile
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", tempfile.mkdtemp(prefix="gen2-matplotlib-"))

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch
import numpy as np
import pandas as pd

from .step1_baseline_inventory import OUT, file_record, save_json


COLORS = {"Nonzero": "#247C70", "Recorded zero": "#DDAF47", "Missing": "#E0E3E5"}


def finish(fig, filename):
    fig.savefig(OUT / filename, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main():
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.spines.top": False, "axes.spines.right": False})
    coverage = pd.read_csv(OUT / "five_food_coverage.csv")
    preview = pd.read_csv(OUT / "five_food_values.csv")
    profiles = pd.read_csv(OUT / "column_profiles.csv")
    extra = pd.read_csv(OUT / "denovo_extra_columns.csv")
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), gridspec_kw={"width_ratios": [1.25, 1]})
    for ax, group, title in zip(axes, ["shared_nutrients", "denovo_extra_nutrients"], ["Shared nutrients", "De novo extras"]):
        rows = coverage[coverage.table_id.eq("denovo") & coverage.feature_group.eq(group)]
        positions = np.arange(len(rows))
        offset = np.zeros(len(rows))
        for label, col in [("Nonzero", "nonzero_count"), ("Recorded zero", "zero_count"), ("Missing", "missing_count")]:
            vals = rows[col].to_numpy()
            ax.barh(positions, vals, left=offset, color=COLORS[label], height=0.6)
            for i, value in enumerate(vals):
                if value >= 3:
                    ax.text(offset[i] + value / 2, i, str(value), ha="center", va="center", color="white" if label == "Nonzero" else "#222222", fontsize=10)
            offset += vals
        ax.set_yticks(positions, rows.panel_label if ax is axes[0] else [])
        ax.invert_yaxis()
        ax.set_xlim(0, rows.column_count.max())
        ax.set_title(f"{title} ({int(rows.column_count.max())} columns)", loc="left", fontsize=12)
        ax.set_xlabel("Nutrient columns")
    fig.suptitle("Five-food baseline: recorded values and gaps", x=0.03, ha="left", fontsize=15)
    fig.legend(handles=[Patch(color=c, label=l) for l, c in COLORS.items()], loc="lower center", ncol=3, frameon=False, bbox_to_anchor=(0.56, -0.01))
    fig.text(0.03, -0.055, "Shared nutrient values are identical in Gen1 de novo and NutriMatch-based. Recorded zero is not a verified absence.", fontsize=10)
    fig.tight_layout(rect=(0, 0.065, 1, 0.95))
    finish(fig, "five_food_coverage.png")

    columns = ["Energy", "Protein", "Fiber, total dietary", "Caffeine", "Leucine", "leucine", "palmitic", "iodine",
               "canonical_inherited__foodb_compound_count", "canonical_inherited__hmdb_pathway_count"]
    labels = ["Energy", "Protein", "Fiber", "Caffeine", "Leucine", "leucine\n(extra)", "palmitic\n(extra)", "iodine\n(extra)", "FooDB\ncompound\ncount", "HMDB\npathway\ncount"]
    values = preview[columns].to_numpy(dtype=float)
    state = np.where(np.isnan(values), 0, np.where(values == 0, 1, 2))
    fig, ax = plt.subplots(figsize=(13, 4.8))
    ax.imshow(state, cmap=ListedColormap([COLORS["Missing"], COLORS["Recorded zero"], COLORS["Nonzero"]]), vmin=0, vmax=2, aspect="auto")
    for i in range(values.shape[0]):
        for j in range(values.shape[1]):
            label = "missing" if np.isnan(values[i, j]) else f"{values[i, j]:.4g}"
            ax.text(j, i, label, ha="center", va="center", fontsize=10, color="white" if state[i, j] == 2 else "#222222")
    ax.set_xticks(range(len(columns)), labels, fontsize=10)
    ax.set_yticks(range(len(preview)), preview.panel_label)
    ax.set_title("Five foods: selected Gen1 values", loc="left", fontsize=15, pad=16)
    fig.text(0.03, 0.005, "Nutrients retain source-native units and a declared per-100g basis. Graph counts are annotations, not doses or disease effects.", fontsize=10)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    finish(fig, "five_food_values.png")

    rows, labels = [], []
    for table_id, label in [("hpp_input", "HPP input nutrients"), ("nutrimatch_based", "NutriMatch-based nutrients"), ("denovo", "De novo nutrients")]:
        sub = profiles[profiles.table_id.eq(table_id) & profiles.feature_family.eq("nutrient_per_100g")]
        rows.append(sub)
        labels.append(f"{label} ({len(sub)})")
    rows.append(extra)
    labels.append(f"De novo-only extras ({len(extra)})")
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8), gridspec_kw={"width_ratios": [1.25, 1]})
    offset = np.zeros(len(rows))
    for label, col in [("Nonzero", "nonzero_count"), ("Recorded zero", "zero_count"), ("Missing", "missing_count")]:
        vals = np.array([100 * row[col].sum() / row.row_count.sum() for row in rows])
        axes[0].barh(range(len(rows)), vals, left=offset, color=COLORS[label], height=0.6)
        for i, value in enumerate(vals):
            if value >= 5:
                axes[0].text(offset[i] + value / 2, i, f"{value:.1f}%", ha="center", va="center", color="white" if label == "Nonzero" else "#222222", fontsize=10)
        offset += vals
    axes[0].set_yticks(range(len(rows)), labels)
    axes[0].invert_yaxis()
    axes[0].set_xlim(0, 100)
    axes[0].set_xlabel("Percent of nutrient cells across 7,405 foods")
    axes[0].set_title("Overall nutrient coverage", loc="left", fontsize=12)
    axes[1].hist(extra.missing_fraction * 100, bins=[80, 85, 90, 95, 100], color="#738AC0", edgecolor="white")
    axes[1].set_xlim(80, 100)
    axes[1].set_xticks([80, 85, 90, 95, 100])
    axes[1].set_xlabel("Missing values per extra column (%)")
    axes[1].set_ylabel("Number of columns")
    axes[1].set_title("Sparsity of 39 de novo-only columns", loc="left", fontsize=12)
    fig.suptitle("Gen1 baseline: coverage across all foods", x=0.03, ha="left", fontsize=15)
    fig.legend(handles=[Patch(color=c, label=l) for l, c in COLORS.items()], loc="lower center", ncol=3, frameon=False, bbox_to_anchor=(0.56, -0.01))
    fig.text(0.03, -0.055, "Unweighted food rows. Non-null values and graph links do not establish biological validity or predictive benefit.", fontsize=10)
    fig.tight_layout(rect=(0, 0.07, 1, 0.95))
    finish(fig, "baseline_sparsity.png")
    save_json({"matplotlib": matplotlib.__version__, "code": file_record(Path(__file__)),
               "inputs": [file_record(OUT / name) for name in ["five_food_coverage.csv", "five_food_values.csv", "column_profiles.csv", "denovo_extra_columns.csv"]],
               "figures": [file_record(OUT / name) for name in ["five_food_coverage.png", "five_food_values.png", "baseline_sparsity.png"]]}, "figure_manifest.json")


if __name__ == "__main__":
    main()
