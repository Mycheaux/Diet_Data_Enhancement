# Gen2 Details

Updated: 2026-09-23. Review each checkpoint before continuing.

## Step 1: Two Base Food Tables

**In progress.** The original five-food pilot was approved. This checkpoint
expands it using the same USDA source; its original values are unchanged.
No later data-source layer, task-specific dataset or prediction has run.

| Branch | Current output | Still needed |
|---|---|---|
| NutriMatch-based | 7,405 foods x 153 supplied nutrients; separate Gen2 export, values unchanged | No new nutrient construction in this comparator |
| Independent de novo | 5 foods x 98 features: 86 nutrients + 8 existing formulas + 4 identity descriptors | Remaining nutrient completion, broader feature discovery and all 7,405 foods |

Tables also contain food ID and name. De novo grew from **5 x 81 to 5 x 100 total
columns**, adding **19 features**, dropping/renaming none. It reads no
HPP/NutriMatch nutrient values or old generated names.

## What Was Added

- **15 nutrients:** SFA 4:0, 6:0, 8:0, 10:0, 12:0, 14:0, 16:0, 18:0;
  MUFA 16:1, 20:1, 22:1; PUFA 20:4, 18:4; added vitamin E and added B12.
- **4 categorical descriptors:** food family, preparation evidence,
  fermentation evidence and grain-refinement evidence from original descriptions.
- **Selection:** assess all 149 source nutrient IDs; include every eligible
  quantity complete across these five donors or the previously reviewed proxy.
  This is a coverage rule, not learned rubric selection or predictive validation.
- **Representation check:** do not add energy kJ, vitamin D IU or vitamin A IU.
  The last is an alternate activity convention, not a universal unit conversion.

All **470 numeric feature cells** are populated: 412 donor transfers, 18 existing
espresso amino-acid proxy estimates and 40 existing derived values. No new
numeric imputation was introduced. Of 20 descriptor cells, **13 are informative
and 7 say `not_stated`**, which means unknown, not absent.

**60 distinct nutrient candidates remain pending:** 59 need completion and one
has an ambiguous source label (`PUFA 2:4 n-6`). Their 273 unresolved cells remain
visible in the evidence table, not zero-filled. This is not full-catalogue coverage.
All 86 nutrient names overlap NutriMatch's 153; **260/430** matched values differ.
The descriptors are new feature types here, not newly measured chemicals.

## Five-Food Preview

Each food gained 15 nutrient fields and four descriptors, absent from the
approved pilot. SFA 16:0 below is in g per 100 g, transferred from reference foods.

| Food | HPP ID | New SFA 16:0 | Preparation evidence | Fermentation evidence |
|---|---|---:|---|---|
| Espresso | 1007294 | 0.046 | Espresso extraction | Not stated |
| Cooked spinach | 1009997 | 0.033 | Cooked; method unknown | Not stated |
| Turkey pastrami | 1013314 | 1.110 | Pastrami | Not stated |
| Whole-wheat sourdough | 1011816 | 0.600 | Sourdough bread | Sourdough |
| Yogurt, 3% fat | 1009118 | 0.886 | Yogurt | Yogurt |

![Five-food expansion](../outputs_GEN2/step1c_expanded_schema/five_food_expansion.png)

[Coverage figure](../outputs_GEN2/step1c_expanded_schema/catalogue_coverage.png) |
[De novo table](../outputs_GEN2/step1c_expanded_schema/denovo/food_features.csv) |
[NutriMatch-based table](../outputs_GEN2/step1c_expanded_schema/nutrimatch_based/food_features.csv) |
[Exact new columns](../outputs_GEN2/step1c_expanded_schema/denovo/new_columns.csv) |
[Nutrient registry](../outputs_GEN2/step1c_expanded_schema/denovo/nutrient_registry.csv) |
[Candidate evidence](../outputs_GEN2/step1c_expanded_schema/denovo/candidate_evidence_long.csv) |
[Cell provenance](../outputs_GEN2/step1c_expanded_schema/denovo/cell_provenance.csv).

**Checks:** 18 tests passed, including lineage, unknown/zero separation, input
isolation, unchanged pilot values and unchanged comparator values. Mapping/proxy
accuracy remains unvalidated; generic-food and preparation assumptions remain.
Differences do not prove improvement. Embedding/external model calls: **0**.

**Next, after review:** independent completion strategies for pending nutrients,
broader evidence-backed features and production mapping before full de novo export.
No Layer 2 or downstream work yet. [Inputs, sources and reproduction](../diet_data_enhancement_GEN2/README.md)
| [Plan](GEN2_PLAN_NOTES.md) | [Earlier detailed record](GEN2_details_archive_2026-09-22.md).
