from __future__ import annotations

import csv
import html
import io
import textwrap
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
EXPORT_DIR = ROOT / "Nitrate_results_1" / "00002759"
OUT_DIR = ROOT / "nature_microbiology_draft"
FIG_DIR = OUT_DIR / "figures"
TABLE_DIR = OUT_DIR / "tables"


def parse_bundle(path: Path) -> dict[str, pd.DataFrame]:
    text = path.read_text(errors="replace").splitlines()
    tables: dict[str, pd.DataFrame] = {}
    i = 0
    while i < len(text):
        line = text[i]
        if line.startswith("__TABLE_START__"):
            name = next(csv.reader([line]))[1]
            i += 1
            rows: list[str] = []
            while i < len(text) and not text[i].startswith("__TABLE_END__"):
                rows.append(text[i])
                i += 1
            content = "\n".join(rows).strip()
            if content:
                tables[name] = pd.read_csv(io.StringIO(content))
        i += 1
    return tables


def label_outcome(value: str) -> str:
    value = str(value)
    replacements = {
        "oral_metaphlan_": "",
        "oral_nitrate_": "nitrate_",
        "supp_species_": "",
        "_": " ",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    value = value.replace("rothia dentocariosa", "Rothia dentocariosa")
    value = value.replace("genus neisseria", "Neisseria")
    value = value.replace("species neisseria", "Neisseria species")
    value = value.replace("family neisseria", "Neisseriaceae")
    value = value.replace("genus prevotella", "Prevotella")
    value = value.replace("species prevotella", "Prevotella species")
    value = value.replace("family prevotella", "Prevotellaceae")
    value = value.replace("genus veillonella", "Veillonella")
    value = value.replace("species veillonella", "Veillonella species")
    value = value.replace("family veillonella", "Veillonellaceae")
    value = value.replace("genus megasphaera", "Megasphaera")
    value = value.replace("species megasphaera", "Megasphaera species")
    value = value.replace("genus burkholderiaceae", "Burkholderiaceae")
    value = value.replace("family burkholderiaceae", "Burkholderiaceae family")
    value = value.replace("nitrate balance log ratio", "Nitrate-balance score")
    value = value.replace("nitrate positive score", "Nitrate-positive score")
    value = value.replace("nitrate anaerobe score", "Anaerobe score")
    value = value.replace("genus shannon", "Genus Shannon")
    value = value.replace("species shannon", "Species Shannon")
    return value


def label_exposure(value: str) -> str:
    mapping = {
        "overall_nitrate": "overall nitrate",
        "vegetable_nitrate": "vegetable nitrate",
        "overall_nitrite": "overall nitrite",
        "processed_nitrite": "processed nitrite",
        "nitroso_axis": "nitroso axis",
        "arginine_no_axis": "arginine/NO axis",
    }
    return mapping.get(str(value), str(value).replace("_", " "))


def q_text(q: float) -> str:
    if pd.isna(q):
        return ""
    if q < 0.001:
        return "q<0.001"
    return f"q={q:.3f}".rstrip("0").rstrip(".")


def p_text(p: float) -> str:
    if pd.isna(p):
        return ""
    if p < 0.001:
        return "p<0.001"
    return f"p={p:.3f}".rstrip("0").rstrip(".")


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def wrap_svg_text(text: str, max_chars: int) -> list[str]:
    return textwrap.wrap(str(text), width=max_chars, break_long_words=False) or [str(text)]


def rd_bu(value: float, vmin: float, vmax: float) -> str:
    if pd.isna(value):
        return "#f7f7f7"
    value = max(vmin, min(vmax, float(value)))
    mid = 0.0
    if value < mid:
        t = (value - vmin) / (mid - vmin)
        c1 = np.array([33, 102, 172])
        c2 = np.array([247, 247, 247])
    else:
        t = (value - mid) / (vmax - mid)
        c1 = np.array([247, 247, 247])
        c2 = np.array([178, 24, 43])
    rgb = (c1 * (1 - t) + c2 * t).astype(int)
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def svg_text(x, y, text, size=12, anchor="start", weight="400", fill="#111", rotate=None):
    transform = f' transform="rotate({rotate} {x} {y})"' if rotate is not None else ""
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="Arial, sans-serif" '
        f'font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" '
        f'fill="{fill}"{transform}>{esc(text)}</text>'
    )


def write_svg(path: Path, width: int, height: int, body: list[str]) -> None:
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        *body,
        "</svg>",
    ]
    path.write_text("\n".join(svg), encoding="utf-8")


def save_selected_tables(tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    main = tables["main_ecology_results"].copy()
    main["label"] = main["outcome"].map(label_outcome)
    main["exposure_label"] = main["exposure"].map(label_exposure)

    exposure_summary = tables["exposure_summary"].copy()
    exposure_summary["exposure_label"] = exposure_summary["exposure"].map(label_exposure)
    exposure_cols = [
        "exposure_label",
        "terms",
        "connected_foods_after_filter",
        "excluded_sparse_or_irregular",
        "primary_logging_quality",
        "primary_exposure_metric",
        "target_node_count",
    ]
    exposure_summary = exposure_summary[[c for c in exposure_cols if c in exposure_summary.columns]]
    exposure_summary.to_csv(TABLE_DIR / "table_1_exposure_reconstruction.csv", index=False)

    table2_outcomes = [
        "oral_nitrate_balance_log_ratio",
        "oral_nitrate_anaerobe_score",
        "oral_nitrate_positive_score",
        "oral_metaphlan_genus_neisseria",
        "oral_metaphlan_genus_prevotella",
        "oral_metaphlan_genus_veillonella",
        "oral_metaphlan_genus_megasphaera",
        "oral_metaphlan_genus_burkholderiaceae",
    ]
    table2 = main[
        main["outcome"].isin(table2_outcomes)
        & main["exposure"].isin(
            [
                "overall_nitrate",
                "vegetable_nitrate",
                "overall_nitrite",
                "processed_nitrite",
                "arginine_no_axis",
            ]
        )
    ].copy()
    table2 = table2.sort_values(["outcome", "exposure"])
    table2 = table2[
        [
            "exposure_label",
            "label",
            "n",
            "exposure_standardized_beta",
            "exposure_p",
            "exposure_q_value",
            "high_minus_low_d",
            "high_vs_low_q_value",
            "r2",
        ]
    ]
    table2.to_csv(TABLE_DIR / "table_2_selected_axis_ecology_results.csv", index=False)

    opp = tables["opposite_axis_candidates"].copy()
    opp.to_csv(TABLE_DIR / "table_3_opposite_axis_candidates.csv", index=False)

    demo = tables["diet_demographic_results"].copy()
    demo["exposure_label"] = demo["exposure"].map(label_exposure)
    demo = demo.sort_values("q_value")[
        ["demographic", "exposure_label", "n", "standardized_beta", "p_value", "q_value", "r2"]
    ]
    demo.to_csv(TABLE_DIR / "table_4_demographic_diet_results.csv", index=False)

    return {
        "main": main,
        "exposure_summary": exposure_summary,
        "table2": table2,
        "opp": opp,
        "demo": demo,
        "group": tables["plot_group_distribution_summary"].copy(),
    }


def figure_heatmap(main: pd.DataFrame) -> None:
    selected = [
        "oral_nitrate_balance_log_ratio",
        "oral_nitrate_positive_score",
        "oral_nitrate_anaerobe_score",
        "oral_metaphlan_genus_neisseria",
        "oral_metaphlan_genus_prevotella",
        "oral_metaphlan_genus_veillonella",
        "oral_metaphlan_genus_megasphaera",
        "oral_metaphlan_genus_burkholderiaceae",
        "oral_metaphlan_species_rothia_dentocariosa",
        "oral_metaphlan_species_shannon",
    ]
    exposures = [
        "overall_nitrate",
        "vegetable_nitrate",
        "overall_nitrite",
        "processed_nitrite",
        "nitroso_axis",
        "arginine_no_axis",
    ]
    sub = main[main["outcome"].isin(selected) & main["exposure"].isin(exposures)].copy()
    beta = sub.pivot(index="outcome", columns="exposure", values="exposure_standardized_beta").reindex(selected)[exposures]
    q = sub.pivot(index="outcome", columns="exposure", values="exposure_q_value").reindex(selected)[exposures]

    width, height = 1080, 700
    left, top = 280, 80
    cell_w, cell_h = 120, 46
    lim = max(float(np.nanmax(np.abs(beta.to_numpy()))), 0.07)
    body = [
        svg_text(width / 2, 34, "Nitrogen diet axes show distinct oral ecology associations", 20, "middle", "700"),
        svg_text(left, height - 28, "* exposure FDR q<0.05 within prespecified oral ecology outcomes", 12),
    ]
    for j, exposure in enumerate(exposures):
        x = left + j * cell_w + cell_w / 2
        body.append(svg_text(x, top - 14, label_exposure(exposure), 12, "end", rotate=-35))
    for i, outcome in enumerate(selected):
        y = top + i * cell_h
        body.append(svg_text(left - 12, y + cell_h / 2 + 5, label_outcome(outcome), 12, "end"))
        for j, exposure in enumerate(exposures):
            x = left + j * cell_w
            b = beta.iloc[i, j]
            qq = q.iloc[i, j]
            body.append(f'<rect x="{x}" y="{y}" width="{cell_w}" height="{cell_h}" fill="{rd_bu(b, -lim, lim)}" stroke="#d9d9d9"/>')
            if pd.notna(b):
                marker = "*" if pd.notna(qq) and qq < 0.05 else ""
                body.append(svg_text(x + cell_w / 2, y + cell_h / 2 + 5, f"{b:+.2f}{marker}", 11, "middle"))
    legend_x, legend_y = left + len(exposures) * cell_w + 32, top + 30
    for k in range(90):
        val = lim - (2 * lim) * k / 89
        body.append(f'<rect x="{legend_x}" y="{legend_y+k*3}" width="18" height="3" fill="{rd_bu(val, -lim, lim)}"/>')
    body.append(svg_text(legend_x + 28, legend_y + 6, f"+{lim:.2f}", 10))
    body.append(svg_text(legend_x + 28, legend_y + 136, "0", 10))
    body.append(svg_text(legend_x + 28, legend_y + 270, f"-{lim:.2f}", 10))
    body.append(svg_text(legend_x + 18, legend_y + 310, "Adjusted standardized beta", 11, "middle", rotate=-90))
    write_svg(FIG_DIR / "figure_1_axis_heatmap.svg", width, height, body)


def figure_opposite_axes(opp: pd.DataFrame) -> None:
    plot = opp.copy().head(8)
    plot["label_clean"] = plot["label"].map(label_outcome)
    width, height = 1060, 560
    left, right, top, row_h = 300, 960, 82, 52
    vals = pd.concat([plot["strongest_positive_beta"], plot["strongest_negative_beta"]]).abs()
    lim = max(float(vals.max()) * 1.22, 0.08)
    mid = (left + right) / 2
    scale = (right - left) / 2 / lim
    body = [
        svg_text(width / 2, 34, "Same oral features increase under one nitrogen axis and decrease under another", 20, "middle", "700"),
        f'<line x1="{mid}" y1="{top-24}" x2="{mid}" y2="{top+row_h*len(plot)}" stroke="black" stroke-width="1"/>',
        svg_text(left, height - 22, "negative association", 12),
        svg_text(right, height - 22, "positive association", 12, "end"),
        f'<rect x="{left+20}" y="{height-47}" width="16" height="10" fill="#2166ac"/>',
        svg_text(left+42, height-38, "strongest negative axis", 11),
        f'<rect x="{left+210}" y="{height-47}" width="16" height="10" fill="#b2182b"/>',
        svg_text(left+232, height-38, "strongest positive axis", 11),
    ]
    for tick in np.linspace(-lim, lim, 5):
        x = mid + tick * scale
        body.append(f'<line x1="{x:.1f}" y1="{top-18}" x2="{x:.1f}" y2="{top+row_h*len(plot)}" stroke="#000" stroke-opacity="0.12"/>')
        body.append(svg_text(x, height - 58, f"{tick:+.2f}", 10, "middle"))
    for k, (_, row) in enumerate(plot.iterrows()):
        y = top + k * row_h
        body.append(svg_text(left - 14, y + 18, row["label_clean"], 12, "end"))
        nval = float(row["strongest_negative_beta"])
        pval = float(row["strongest_positive_beta"])
        nx = mid + nval * scale
        px = mid + pval * scale
        body.append(f'<rect x="{min(nx, mid):.1f}" y="{y+7}" width="{abs(nx-mid):.1f}" height="14" fill="#2166ac"/>')
        body.append(f'<rect x="{mid:.1f}" y="{y+27}" width="{abs(px-mid):.1f}" height="14" fill="#b2182b"/>')
        body.append(svg_text(nx - 5, y + 18, label_exposure(row["strongest_negative_axis"]), 10, "end"))
        body.append(svg_text(px + 5, y + 38, label_exposure(row["strongest_positive_axis"]), 10))
    body.append(svg_text((left+right)/2, height - 22, "Adjusted standardized beta", 12, "middle"))
    write_svg(FIG_DIR / "figure_2_opposite_axis_features.svg", width, height, body)


def figure_same_features_across_axes(main: pd.DataFrame) -> None:
    outcomes = [
        "oral_metaphlan_genus_neisseria",
        "oral_metaphlan_genus_prevotella",
        "oral_nitrate_balance_log_ratio",
        "oral_nitrate_anaerobe_score",
    ]
    exposures = [
        "overall_nitrate",
        "vegetable_nitrate",
        "overall_nitrite",
        "processed_nitrite",
        "nitroso_axis",
        "arginine_no_axis",
    ]
    width, height = 1320, 980
    panel_w, panel_h = 560, 370
    origins = [(86, 92), (730, 92), (86, 540), (730, 540)]
    body = [
        svg_text(width / 2, 34, "Same oral feature across dietary nitrogen axes", 22, "middle", "700"),
        svg_text(
            width / 2,
            58,
            "Bars show adjusted standardized beta; labels show model p, FDR q and high-minus-low Cohen's d",
            12,
            "middle",
            "400",
            "#333",
        ),
        f'<rect x="{width-260}" y="28" width="14" height="14" fill="#b2182b" stroke="#111"/>',
        svg_text(width - 238, 40, "positive beta", 11),
        f'<rect x="{width-150}" y="28" width="14" height="14" fill="#2166ac" stroke="#111"/>',
        svg_text(width - 128, 40, "negative beta", 11),
    ]
    plot = main[main["outcome"].isin(outcomes) & main["exposure"].isin(exposures)].copy()
    lim = max(float(plot["exposure_standardized_beta"].abs().max()) * 1.45, 0.075)

    for (x0, y0), outcome in zip(origins, outcomes):
        sub = plot[plot["outcome"] == outcome].set_index("exposure").reindex(exposures).reset_index()
        plot_l, plot_t, plot_w, plot_h = x0 + 58, y0 + 56, panel_w - 88, panel_h - 138
        zero_y = plot_t + plot_h / 2
        scale = (plot_h / 2) / lim
        body.append(svg_text(x0 + panel_w / 2, y0 + 20, label_outcome(outcome), 16, "middle", "700"))
        body.append(f'<rect x="{plot_l}" y="{plot_t}" width="{plot_w}" height="{plot_h}" fill="none" stroke="#222"/>')
        body.append(f'<line x1="{plot_l}" y1="{zero_y:.1f}" x2="{plot_l+plot_w}" y2="{zero_y:.1f}" stroke="#111" stroke-width="1"/>')
        for tick in np.linspace(-lim, lim, 5):
            yy = zero_y - tick * scale
            body.append(f'<line x1="{plot_l}" y1="{yy:.1f}" x2="{plot_l+plot_w}" y2="{yy:.1f}" stroke="#000" stroke-opacity="0.16"/>')
            body.append(svg_text(plot_l - 8, yy + 4, f"{tick:+.2f}", 9, "end"))
        bar_w = 46
        step = plot_w / len(exposures)
        for j, row in sub.iterrows():
            exposure = row["exposure"]
            beta = row["exposure_standardized_beta"]
            if pd.isna(beta):
                continue
            cx = plot_l + step * (j + 0.5)
            bar_y = zero_y - max(beta, 0) * scale
            bar_h = abs(beta * scale)
            color = "#b2182b" if beta >= 0 else "#2166ac"
            body.append(f'<rect x="{cx-bar_w/2:.1f}" y="{bar_y:.1f}" width="{bar_w}" height="{bar_h:.1f}" fill="{color}" fill-opacity="0.82" stroke="#111"/>')
            label_lines = [
                p_text(row["exposure_p"]),
                q_text(row["exposure_q_value"]),
                f"d={float(row['high_minus_low_d']):+.3f}" if pd.notna(row["high_minus_low_d"]) else "",
            ]
            label_lines = [line for line in label_lines if line]
            label_y = bar_y - 31 if beta >= 0 else bar_y + bar_h + 12
            for k, line in enumerate(label_lines):
                body.append(svg_text(cx, label_y + 10 * k, line, 8, "middle"))
            body.append(svg_text(cx, plot_t + plot_h + 22, label_exposure(exposure), 10, "end", rotate=-35))
        body.append(svg_text(plot_l + plot_w / 2, plot_t + plot_h + 90, "Dietary nitrogen axis", 11, "middle"))
        body.append(svg_text(x0 + 14, plot_t + plot_h / 2, "Adjusted standardized beta", 11, "middle", rotate=-90))
    write_svg(FIG_DIR / "figure_3_same_feature_axis_bars.svg", width, height, body)


def figure_group_means(group: pd.DataFrame) -> None:
    group = group.copy()
    panels = [
        ("vegetable_nitrate", "oral_metaphlan_genus_neisseria"),
        ("vegetable_nitrate", "oral_nitrate_anaerobe_score"),
        ("vegetable_nitrate", "oral_nitrate_balance_log_ratio"),
        ("processed_nitrite", "oral_metaphlan_species_prevotella"),
    ]
    colors = {"low": "#2166ac", "mid": "#f4a582", "high": "#b2182b"}
    width, height = 1040, 760
    body = [svg_text(width / 2, 34, "Representative low/mid/high exposure-group summaries", 20, "middle", "700")]
    panel_w, panel_h = 455, 300
    origins = [(90, 88), (570, 88), (90, 430), (570, 430)]
    for (x0, y0), (exposure, outcome) in zip(origins, panels):
        sub = group[(group["exposure"] == exposure) & (group["outcome"] == outcome)].copy()
        sub = sub[sub["exposure_group"].isin(["low", "mid", "high"])]
        order = ["low", "mid", "high"]
        sub = sub.set_index("exposure_group").reindex(order).reset_index()
        y = pd.to_numeric(sub["mean"], errors="coerce").to_numpy()
        sd = pd.to_numeric(sub["sd"], errors="coerce").to_numpy()
        n = pd.to_numeric(sub["n"], errors="coerce").to_numpy()
        ci = 1.96 * sd / np.sqrt(n)
        ymax = max(float(np.nanmax(y + ci)) * 1.2, 1.0)
        plot_l, plot_t, plot_w, plot_h = x0 + 55, y0 + 52, 350, 190
        body.append(svg_text(x0 + panel_w / 2, y0 + 16, f"{label_exposure(exposure)} -> {label_outcome(outcome)}", 13, "middle", "700"))
        body.append(f'<rect x="{plot_l}" y="{plot_t}" width="{plot_w}" height="{plot_h}" fill="none" stroke="#222"/>')
        for gline in np.linspace(0, ymax, 4):
            yy = plot_t + plot_h - (gline / ymax) * plot_h
            body.append(f'<line x1="{plot_l}" y1="{yy:.1f}" x2="{plot_l+plot_w}" y2="{yy:.1f}" stroke="#000" stroke-opacity="0.14"/>')
            body.append(svg_text(plot_l - 8, yy + 4, f"{gline:.1f}", 9, "end"))
        for j, g in enumerate(order):
            cx = plot_l + 62 + j * 112
            bar_h = (y[j] / ymax) * plot_h if pd.notna(y[j]) else 0
            by = plot_t + plot_h - bar_h
            ci_h = (ci[j] / ymax) * plot_h if pd.notna(ci[j]) else 0
            body.append(f'<rect x="{cx-26}" y="{by:.1f}" width="52" height="{bar_h:.1f}" fill="{colors[g]}" stroke="#111" stroke-width="0.8"/>')
            body.append(f'<line x1="{cx}" y1="{by-ci_h:.1f}" x2="{cx}" y2="{by+ci_h:.1f}" stroke="#111"/>')
            body.append(f'<line x1="{cx-9}" y1="{by-ci_h:.1f}" x2="{cx+9}" y2="{by-ci_h:.1f}" stroke="#111"/>')
            body.append(f'<line x1="{cx-9}" y1="{by+ci_h:.1f}" x2="{cx+9}" y2="{by+ci_h:.1f}" stroke="#111"/>')
            body.append(svg_text(cx, plot_t + plot_h + 20, g, 11, "middle"))
            body.append(svg_text(cx, plot_t + plot_h + 35, f"n={int(n[j]) if pd.notna(n[j]) else 0}", 9, "middle"))
        body.append(svg_text(plot_l + plot_w / 2, plot_t + plot_h + 56, "Exposure tertile", 11, "middle"))
        body.append(svg_text(x0 + 12, plot_t + plot_h / 2, "Mean relative abundance / score", 10, "middle", rotate=-90))
    write_svg(FIG_DIR / "figure_3_representative_group_means.svg", width, height, body)


def figure_demographics(tables: dict[str, pd.DataFrame]) -> None:
    demo_oral = tables["demographic_oral_results"].copy()
    demo_oral["label"] = demo_oral["outcome"].map(label_outcome)
    plot = demo_oral.sort_values("q_value").head(14).copy()
    width, height = 980, 600
    left, right, top, row_h = 390, 890, 82, 34
    lim = max(float(plot["standardized_beta"].abs().max()) * 1.35, 0.08)
    mid = (left + right) / 2
    scale = (right - left) / 2 / lim
    body = [
        svg_text(width / 2, 34, "Age and sex associations with oral ecology", 20, "middle", "700"),
        f'<line x1="{mid}" y1="{top-22}" x2="{mid}" y2="{top+row_h*len(plot)}" stroke="black" stroke-width="1"/>',
        svg_text(left, height - 30, "Adjusted standardized beta", 12),
        f'<circle cx="{right-160}" cy="{height-33}" r="5" fill="#4d4d4d"/>',
        svg_text(right-148, height-29, "age", 11),
        f'<circle cx="{right-110}" cy="{height-33}" r="5" fill="#b2182b"/>',
        svg_text(right-98, height-29, "sex", 11),
    ]
    for tick in np.linspace(-lim, lim, 5):
        x = mid + tick * scale
        body.append(f'<line x1="{x:.1f}" y1="{top-16}" x2="{x:.1f}" y2="{top+row_h*len(plot)}" stroke="#000" stroke-opacity="0.14"/>')
        body.append(svg_text(x, height - 52, f"{tick:+.2f}", 10, "middle"))
    for k, (_, row) in enumerate(plot.iterrows()):
        y = top + k * row_h
        color = "#4d4d4d" if row["demographic"] == "age" else "#b2182b"
        label = f"{row['demographic']}: {row['label']}"
        body.append(svg_text(left - 12, y + 5, label, 11, "end"))
        x = mid + float(row["standardized_beta"]) * scale
        body.append(f'<circle cx="{x:.1f}" cy="{y}" r="5" fill="{color}" stroke="#111"/>')
        body.append(svg_text(x, y - 10, q_text(row["q_value"]), 8, "middle"))
    write_svg(FIG_DIR / "figure_4_demographic_oral_ecology.svg", width, height, body)


def build() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    tables = parse_bundle(EXPORT_DIR / "A_main_result_export_bundle.csv")
    selected = save_selected_tables(tables)
    figure_heatmap(selected["main"])
    figure_opposite_axes(selected["opp"])
    figure_same_features_across_axes(selected["main"])
    figure_group_means(selected["group"])
    figure_demographics(tables)
    print(f"Wrote manuscript tables and figures to {OUT_DIR}")


if __name__ == "__main__":
    build()
