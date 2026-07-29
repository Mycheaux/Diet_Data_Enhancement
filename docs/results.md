# Results

This document summarizes the current outside-TRE Diet Data Enhancement results
for manuscript drafting. It emphasizes reproducible quantitative results and
clearly separates direct evidence from interpretation.

## NutriMatch-Derived Nutrient Panel Comparator

We evaluated the current Layer 1 nutrient output against a locally provided
NutriMatch-derived nutrient panel:

```text
data/Nutrimatch/imputed_nutrients_table.parquet
```

The bundle README describes this file as a static NutriMatch-derived
food-composition panel, not participant-level diet data and not a row-level
mapping/provenance table. The parquet contains four dataset strata:
`SR_Legacy`, `FNDDS`, `Zameret`, and `HPP`. The HPP subset contains `7,405` food
rows and `153` nutrient columns, with values expressed per 100 g.

Because the comparator does not include donor-food identifiers, match confidence
scores, or value-level provenance, we did not claim a direct mapping-accuracy
comparison against NutriMatch. Instead, we compared the resulting nutrient
panels after harmonizing them to the same canonical-food level.

## Canonicalization And Join Integrity

The NutriMatch HPP subset joined exactly to the local HPP food catalog using the
Hebrew food name described in the comparator README:

| Metric | Value |
|---|---:|
| HPP food rows in raw HPP table | `7,405` |
| NutriMatch HPP rows | `7,405` |
| NutriMatch HPP rows joined to HPP `food_id` | `7,405` |
| Canonical foods after HPP collapse | `842` |

The one-to-one join establishes that the comparator covers the same local HPP
food universe used by this project. We then collapsed the NutriMatch HPP panel
to the same `842` canonical foods using the existing
`outputs/canonical/hpp_to_canonical.csv` crosswalk and the same
`number_loggings` weighting rule used by the current Layer 1 nutrient profile
builder.

## Nutrient-Panel Agreement

The canonicalized NutriMatch HPP panel and this project's Layer 1 canonical
nutrient panel shared all `153` NutriMatch nutrient columns. On these shared
columns, the two panels were numerically identical after canonical aggregation,
up to floating-point precision:

| Metric | Value |
|---|---:|
| Shared nutrient columns | `153` |
| Compared canonical foods | `842` |
| Weighted exact match on shared canonical nutrient values | `100.0%` |
| NutriMatch-only nutrient columns | `0` |

This result indicates that, for the 153 NutriMatch/HPP nutrient fields, the
current Layer 1 canonical nutrient table preserves the same HPP nutrient
information as the NutriMatch-derived operational panel after applying the same
canonical-food collapse.

The key difference is therefore not that the current pipeline gives different
values for the shared 153 HPP nutrients. The key differences are breadth,
traceability, modularity, and downstream enrichment.

## Inferred Mapping-Level Comparison Against NutriMatch

The provided NutriMatch parquet does not include the original food-to-food
mapping decisions. Therefore, a literal comparison such as "our HPP food X maps
to donor food A, NutriMatch maps the same HPP food X to donor food B" is not
directly possible from this file alone.

To approximate this comparison, we inferred a likely NutriMatch donor row for
each HPP food by finding the nearest non-HPP row in the NutriMatch nutrient
matrix. Candidate donor rows came from the three non-HPP strata present in the
parquet: `SR_Legacy`, `FNDDS`, and `Zameret`. Similarity was computed over all
153 nutrient columns after `log1p` transformation, z-score standardization, and
L2 normalization; the nearest donor was selected by cosine similarity. HPP-level
inferred donors were then collapsed to the same 842 canonical foods using
`number_loggings` as the primary weighting signal.

This inferred NutriMatch donor map was then compared against our Layer 1 top
candidate. Source labels were normalized as follows: `USDA_SR_Legacy` to
`SR_Legacy`, `USDA_FNDDS` to `FNDDS`, and `Tzameret_Israel` to `Zameret`.
Our Layer 1 candidates from AUSNUT, Bahrain, and MEXT were labelled as not
directly comparable because those sources are not present in the provided
NutriMatch matrix.

| Mapping comparison status | Canonical foods |
|---|---:|
| Same source and similar food name | `35` |
| Same source but different inferred donor food | `280` |
| Different source | `324` |
| Our top source not present in NutriMatch source set | `203` |
| Total canonical foods compared | `842` |

Thus, under this inferred donor comparison, only `35 / 842` canonical foods had
clear same-source and similar-name agreement. This low direct agreement should
not be interpreted as proof that either method is globally better, because the
NutriMatch donor map is reconstructed from the completed nutrient matrix rather
than read from the original NutriMatch mapping/provenance table. It is best
interpreted as a discrepancy-finding and review-prioritization analysis.

The inferred comparison produced the following review-priority categories:

| Review priority | Canonical foods | Interpretation |
|---|---:|---|
| Agreement | `35` | Our Layer 1 candidate and inferred NutriMatch donor are aligned. |
| NutriMatch inferred may be better | `11` | Our candidate is low/review tier and the inferred NutriMatch donor has stronger name evidence. |
| Our mapping may be better | `341` | Our candidate is high/medium confidence despite donor disagreement. |
| Both plausible, review | `92` | Both systems have strong evidence but point to different donors. |
| Ambiguous review | `363` | Neither comparison gives enough evidence for an automatic winner. |

Examples where the inferred NutriMatch donor appears useful for review include
foods such as Kashkaval, Buffalo milk yogurt, Majadra, Kif Kef, Salt, Pear, and
Zaatar. These are high-value HITL targets because the inferred donor is often a
local Zameret entry with plausible Hebrew-name or nutrient-profile support,
whereas our current Layer 1 candidate can be low-confidence or semantically
wrong.

Examples where our mapping is likely at least as good include cases such as
Agave syrup, Alfalfa sprouts, Artichoke, Bagel, and Brazil nuts, where our
candidate has high or medium lexical/role confidence and the inferred donor
either differs only by source or reflects a nutrient-nearest neighbor rather
than a clearly superior food-identity match.

The strongest defensible conclusion is therefore:

1. The two approaches reproduce the same canonical HPP nutrient panel on the 153
   shared nutrients.
2. Their inferred donor choices do not generally match.
3. The provided NutriMatch file is insufficient to declare a definitive mapping
   accuracy winner.
4. The inferred donor comparison is still valuable because it identifies a small
   set of likely NutriMatch-better cases, a larger set of likely our-better
   cases, and a substantial ambiguous set that should enter HITL review.

## Nutrient Breadth And Sparsity

This project's Layer 1 canonical nutrient panel contains `192` nutrient-like
columns, compared with `153` in the NutriMatch-derived HPP panel. The additional
`39` fields arise from the project's broader source ingestion and source-native
nutrient naming, especially non-HPP public-source fields that have not yet been
fully unit/name-standardized.

| Panel | Food rows | Nutrient columns | Non-null cells | Nonzero cells | Median nonzero nutrients per food |
|---|---:|---:|---:|---:|---:|
| NutriMatch-derived HPP panel, HPP-food level | `7,405` | `153` | `100.000%` | `62.535%` | `99` |
| NutriMatch-derived HPP panel, canonical level | `842` | `153` | `100.000%` | `70.962%` | `113` |
| This project Layer 1 canonical nutrient panel | `842` | `192` | `82.196%` | `58.170%` | `115` |
| This project Layer 1 canonical panel, shared nutrients only | `842` | `153` | `100.000%` | `70.962%` | `113` |

The lower non-null percentage in the full 192-column project matrix is expected:
the extra source-native columns are not populated for every canonical food. When
restricted to the 153 shared NutriMatch nutrients, the current project exactly
matches the canonicalized NutriMatch coverage profile.

## Provenance And Auditability

The NutriMatch-derived parquet is a complete nutrient matrix but does not retain
value-level provenance in the provided snapshot. In contrast, the current
pipeline writes a long provenance table:

```text
outputs/nutrients/canonical_nutrient_provenance.csv
```

This table records the selected value, source, source food ID when relevant,
confidence, method, HPP observation count, mapped-source observation count, and
whether the value came from observed HPP data or public-source transfer.

Current provenance summary:

| Chosen source | Method | Nutrient values | Canonical foods |
|---|---|---:|---:|
| HPP | weighted HPP observed mean | `128,826` | `842` |
| Tzameret Israel | weighted mapped public-source mean | `3,961` | `134` |
| Bahrain FCT | weighted mapped public-source mean | `95` | `72` |

Overall, the canonical nutrient table currently contains `132,882` value-level
provenance records. Of these, `128,826` were selected from observed HPP values
and `4,056` were selected from mapped public sources.

This is a major methodological distinction: the comparator provides a complete
operational nutrient panel, whereas the current project provides a complete
canonical panel plus an auditable value-level explanation for how each retained
nutrient value was selected.

## Layer 1 Mapping And Review Burden

The Layer 1 mapping system generated a top candidate for all `842` canonical
foods. Top-candidate confidence distribution was:

| Confidence tier | Canonical foods |
|---|---:|
| High | `355` |
| Medium | `98` |
| Low | `146` |
| Review | `243` |

Thus, `453 / 842` canonical foods had high- or medium-confidence Layer 1
candidate mappings, while `389 / 842` had low or review-tier Layer 1 candidates.
After incorporating Layer 2 product/processing evidence into the HITL routing
rule, `637` canonical foods were auto-accepted and `205` remained pending for
human review.

This does not measure NutriMatch's mapping accuracy because the comparator file
does not include NutriMatch match decisions. However, it does quantify an
important practical advantage of the current pipeline: low-confidence food
identity decisions are explicitly surfaced for review rather than hidden inside
a completed imputed nutrient matrix.

## Beyond Layer 1: Product, Chemistry, Metabolomics, And Disease/Pathway Layers

The NutriMatch-derived panel is limited to nutrient composition. The current
project extends the same HPP food universe into a multi-layer food knowledge
representation:

| Feature layer | Current result |
|---|---:|
| Canonical foods | `842` |
| FoodAtlas compound-linked foods | `340` |
| FooDB compound-linked foods | `822` |
| HMDB metabolite-linked foods | `822` |
| Foods with HMDB disease labels | `816` |
| Foods with HMDB pathway labels | `811` |
| Final KG nodes | `297,299` |
| Final KG edges | `2,325,237` |

These additional layers support analyses that a nutrient-only table cannot
directly support: food-product processing features, food chemical exposure
features, food-to-human-metabolite bridges, disease/pathway graph neighborhoods,
and multimodal food embeddings.

## Interpretation For Manuscript Results

The current comparison supports the following conservative interpretation:

1. The provided NutriMatch-derived HPP nutrient panel and this project's Layer 1
   canonical nutrient panel agree exactly on the 153 shared HPP nutrient fields
   after aggregation to canonical foods.
2. The current pipeline expands the nutrient schema from `153` to `192`
   nutrient-like fields, although these additional fields require unit/name
   standardization before final epidemiologic use.
3. The current pipeline provides value-level provenance for all canonical
   nutrient values, whereas the provided NutriMatch-derived snapshot does not
   contain match/provenance metadata.
4. The current pipeline explicitly exposes weak and ambiguous mappings through a
   canonical-food HITL workflow.
5. The current pipeline extends beyond nutrients into OpenFoodFacts,
   FoodAtlas, FooDB, HMDB, disease/pathway features, knowledge graphs, and
   multimodal embeddings.

Therefore, the strongest defensible claim is not that the Layer 1 nutrient
values are numerically superior to NutriMatch for shared HPP nutrients. Rather,
the current project reproduces the shared HPP nutrient panel at canonical-food
level while adding traceability, reviewability, modular extensibility, and
biologically enriched feature layers required for downstream diet-health
prediction.

## Reproducibility

Run the comparison with:

```bash
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline compare-nutrimatch
```

Run the inferred mapping-level comparison with:

```bash
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline compare-nutrimatch-mapping
```

Generated outputs:

```text
outputs/validation/nutrimatch_comparison_summary.json
outputs/validation/nutrimatch_comparison_summary_metrics.csv
outputs/validation/nutrimatch_comparison_coverage.csv
outputs/validation/nutrimatch_comparison_nutrient_agreement.csv
outputs/validation/nutrimatch_comparison_provenance_summary.csv
outputs/validation/nutrimatch_canonical_nutrient_profiles.csv
outputs/validation/nutrimatch_inferred_hpp_donor_mapping.csv
outputs/validation/nutrimatch_inferred_canonical_donor_mapping.csv
outputs/validation/nutrimatch_inferred_vs_our_layer1_mapping_comparison.csv
outputs/validation/nutrimatch_inferred_mapping_comparison_summary.csv
outputs/validation/nutrimatch_inferred_mapping_comparison_summary.json
```

Important limitation: a definitive direct mapping-level comparison will require
the actual NutriMatch match/provenance table containing target source food IDs,
donor database labels, match confidence, and imputation provenance. The current
provided parquet supports exact nutrient-panel comparison and inferred
donor-match comparison, but not direct adjudication of NutriMatch's original
mapping decisions.
