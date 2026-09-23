"""Create review figures for the independent five-food prototype."""

import os
import tempfile
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", tempfile.mkdtemp(prefix="gen2-pilot-plot-"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch
import numpy as np
import pandas as pd

from .independent_pilot import OUT, digest, write_json


def main():
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False})
    matrix = pd.read_csv(OUT / "independent_pilot_features.csv", dtype={"hpp_food_id": str})
    prov = pd.read_csv(OUT / "cell_provenance.csv", dtype={"hpp_food_id": str})
    mapping = pd.read_csv(OUT / "reviewed_donor_decisions.csv", dtype={"hpp_food_id": str})
    labels = mapping.panel_label.tolist()
    colors = {"primary_donor_transfer": "#247C70", "protein_scaled_brewed_coffee_proxy": "#D9A435", "derived_recipe": "#738AC0"}
    titles = {"primary_donor_transfer": "Public donor transfer", "protein_scaled_brewed_coffee_proxy": "Proxy estimate", "derived_recipe": "Derived feature"}
    counts = pd.crosstab(prov.hpp_food_id, prov.method).reindex(matrix.hpp_food_id)
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.5), gridspec_kw={"width_ratios": [1.5, 1]})
    offset = np.zeros(len(matrix))
    for method, color in colors.items():
        values = counts[method].to_numpy()
        axes[0].barh(range(len(matrix)), values, left=offset, color=color, height=0.6)
        for i, value in enumerate(values):
            if value:
                axes[0].text(offset[i] + value / 2, i, str(value), ha="center", va="center", color="white" if method != "protein_scaled_brewed_coffee_proxy" else "#222222")
        offset += values
    axes[0].set_yticks(range(len(matrix)), labels)
    axes[0].invert_yaxis()
    axes[0].set_xlim(0, len(matrix.columns) - 2)
    axes[0].set_xlabel("Filled feature columns per food")
    axes[0].set_title("Five-food feature origins", loc="left")
    totals = [int(prov.method.eq(method).sum()) for method in colors]
    axes[1].bar(range(3), totals, color=list(colors.values()), width=0.65)
    axes[1].set_xticks(range(3), ["Public\ndonor", "Proxy\nestimate", "Derived\nfeature"])
    axes[1].set_ylim(0, max(totals) * 1.2)
    axes[1].set_ylabel("Feature cells across five foods")
    axes[1].set_title(f"{sum(totals)} filled cells, zero missing", loc="left")
    for i, value in enumerate(totals):
        axes[1].text(i, value + 6, str(value), ha="center")
    fig.suptitle("Independent prototype: 71 nutrients + 8 compound features", x=0.02, ha="left", fontsize=14)
    fig.legend(handles=[Patch(color=c, label=titles[m]) for m, c in colors.items()], loc="lower center", bbox_to_anchor=(0.56, -0.025), ncol=3, frameon=False)
    fig.text(0.02, -0.085, "Prototype only: source choices reviewed in-session; no embedding run. A further 78 public nutrient types remain candidates.", fontsize=9)
    fig.tight_layout(rect=(0, 0.07, 1, 0.94))
    fig.savefig(OUT / "independent_coverage.png", dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    cols = ["usda_1003_g_per_100g", "usda_1004_g_per_100g", "usda_1079_g_per_100g",
            "usda_1093_mg_per_100g", "usda_1057_mg_per_100g", "usda_1213_g_per_100g",
            "branched_chain_amino_acids_g_per_100g", "sodium_to_potassium_mass_ratio"]
    col_labels = ["Protein\ng/100 g", "Fat\ng/100 g", "Fiber\ng/100 g", "Sodium\nmg/100 g",
                  "Caffeine\nmg/100 g", "Leucine\ng/100 g", "BCAA sum\ng/100 g", "Sodium :\npotassium\nmass ratio"]
    values = matrix[cols].to_numpy()
    lookup = prov.set_index(["hpp_food_id", "feature_name"])
    states = np.array([[int(lookup.loc[(food_id, col), "upstream_proxy_used"]) for col in cols] for food_id in matrix.hpp_food_id])
    fig, ax = plt.subplots(figsize=(13, 4.8))
    ax.imshow(states, cmap=ListedColormap(["#E8F0EC", "#F5E4B8"]), vmin=0, vmax=1, aspect="auto")
    for i in range(len(matrix)):
        for j in range(len(cols)):
            ax.text(j, i, f"{values[i, j]:.4g}", ha="center", va="center", fontsize=11)
    ax.set_yticks(range(len(matrix)), labels)
    ax.set_xticks(range(len(cols)), col_labels)
    ax.set_title("Fresh source values and new compound features", loc="left", fontsize=14, pad=14)
    fig.text(0.02, 0.015, "Amber: proxy estimate or a formula using it. Other cells use public donor values. All are estimates for the target foods.", fontsize=10)
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(OUT / "independent_values.png", dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    write_json("figure_manifest.json", {"matplotlib": matplotlib.__version__, "code_sha256": digest(Path(__file__)),
        "inputs": {name: digest(OUT / name) for name in ["independent_pilot_features.csv", "cell_provenance.csv", "reviewed_donor_decisions.csv"]},
        "figures": {name: digest(OUT / name) for name in ["independent_coverage.png", "independent_values.png"]}})


if __name__ == "__main__":
    main()
