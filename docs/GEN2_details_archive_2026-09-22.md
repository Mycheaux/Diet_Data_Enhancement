# Archived Gen2 Audit And Prototype Notes

Historical record, archived on 2026-09-22. Checkpoint names and scope below
reflect the earlier discussion; use [GEN2_details.md](GEN2_details.md) for
current status. Downstream tables listed here were inspected Gen1 artifacts,
not newly created Gen2 outputs.

# Generation 2 Details And Step Checkpoints

This document is the slow review log for Generation 2 Diet Data Enhancement.
Each dataset, source, mapping layer, imputation layer, KG layer, or downstream
feature export should add one checkpoint here before the next step begins.

The purpose is to make every step inspectable: five foods, new columns, column
counts, example rows, sparsity, provenance, and a simple visualization.

Latest checkpoint: [Step 1b: Independent Five-Food Prototype](#step-1b-independent-five-food-prototype),
created 2026-09-22 following the user's correction. Step 1 below is a Gen1
diagnostic audit, not a newly generated de novo table.

## Review Rule

Do not move to the next Gen2 step until the current checkpoint has been added
and reviewed.

Gen2 implementation and outputs must stay separate from Gen1:

```text
diet_data_enhancement_GEN2/
outputs_GEN2/
```

Use existing `diet_data_enhancement/` and `outputs/` only as reference inputs
or comparison baselines unless a checkpoint explicitly documents copied or
adapted logic.

Each checkpoint should answer:

- What did this step add?
- Which five foods show the change clearly?
- What new columns appeared?
- How many rows and columns existed before and after?
- Which values are observed, transferred, imputed, or missing?
- Does the result look biologically plausible?
- What should be fixed or reviewed before continuing?

## Default Five-Food Panel

Reuse these foods where possible so changes can be tracked across layers:

```text
coffee
boiled spinach or leafy vegetable
processed meat example
whole grain or bread example
yogurt or fermented dairy example
```

If a source only affects a narrow food class, replace one or more foods with
source-relevant examples and explain why.

## Checkpoint Template

### Step N: <step name>

Date:

Status:

Input files:

Output files:

Command, notebook, or script:

Purpose:

#### Five-Food Preview

| Food | HPP food ID | Before this step | After this step | Main change | Concern or review note |
|---|---|---|---|---|---|
|  |  |  |  |  |  |
|  |  |  |  |  |  |
|  |  |  |  |  |  |
|  |  |  |  |  |  |
|  |  |  |  |  |  |

#### Shape Change

| Table | Rows before | Columns before | Rows after | Columns after | Columns added | Columns dropped | Columns renamed |
|---|---:|---:|---:|---:|---:|---:|---:|
|  |  |  |  |  |  |  |  |

#### New Columns

| Column | Feature family | Unit | Per 100 g? | Observed / mapped / imputed | Missingness | Provenance available? | Keep / merge / alias / review |
|---|---|---|---|---|---:|---|---|
|  |  |  |  |  |  |  |  |

#### Example Rows For Five Foods

Add a compact table or link to a generated CSV showing the five selected foods
and the new columns introduced in this step.

#### Missingness And Sparsity

Summarize missingness for the new columns:

```text
new_column_count:
median_missingness:
high_missingness_columns:
columns_with_zero_inflation:
columns_recommended_for_reference_only:
columns_recommended_for_imputation_review:
```

#### Provenance

Record source and transformation evidence:

```text
source_database:
source_table:
source_version_or_date:
mapping_method:
donor_food_strategy:
unit_conversion_rule:
imputation_rule:
confidence_fields:
```

#### Visualizations

Include at least:

- one five-food visualization, such as a food-by-feature heatmap, presence
  matrix, before/after feature-count bar chart, or mini KG neighborhood;
- one aggregate visualization, such as missingness distribution, new-column
  family counts, source coverage, or provenance/confidence distribution.

Generated visualization paths:

```text
five_food_visualization:
aggregate_visualization:
```

#### Interpretation

What looks useful:

What looks suspicious:

What needs human review:

Decision before next step:

```text
continue / revise / hold
```

---

## Step 1: Baseline Inventory And Five-Food Panel

Date: 2026-09-22.

Status: audit completed; awaiting user review. Decision before next step: **hold**
until this checkpoint is reviewed, as requested. This preparatory inventory was
previously called Step 0 in discussion. It precedes Layer 1; checkpoint numbers
and layer numbers are different.

Purpose: establish the exact starting tables, pin five inspectable foods, measure
missingness, compare de novo with NutriMatch-based values, and expose identity or
donor problems before new mapping starts.

This step added audit tables and three figures. It added **0 modeling features**,
changed **0 nutrient values**, and performed **0 imputations**. No new source,
LLM mapping, embedding retrieval, rubric learning, or downstream prediction was
run. The five foods are illustrative examples, not a representative sample for
estimating population-wide rates; all aggregate rates below use all 7,405 foods.

### Inputs And Reproduction

Inputs:

- `data/HPP/hpp_food_items_with_nutrients.csv`.
- `outputs/enhanced_hpp/1.denovo/` and `outputs/enhanced_hpp/2.nutrimatch_based/`:
  feature matrices, feature schemas, and nutrient provenance tables.
- All ten `outputs/downstream_features/{scenario}/{recipe}/hpp_downstream_feature_table.csv`
  files and their feature lists, across two scenarios and five recipes.
- `outputs/nutrients/hpp_nutrient_harmonized.csv` for the recorded selected donor.
- `diet_data_enhancement/hpp_scenarios.py` and `diet_data_enhancement/nutrients.py`
  as evidence for how the Gen1 values were chosen. These modules were not run.

Reproducible code and pinned food selection:
[Gen2 workflow](../diet_data_enhancement_GEN2/README.md) and
[five-food configuration](../diet_data_enhancement_GEN2/five_food_panel.json).

Commands, from the project root in environments with the required packages:

```sh
python -m diet_data_enhancement_GEN2.step1_baseline_inventory
python -m diet_data_enhancement_GEN2.plot_step1
```

The audit used Python from the bundled workspace runtime; plotting used the
installed Anaconda runtime because the bundled runtime lacked matplotlib.
The [run manifest](../outputs_GEN2/step1_baseline_inventory/run_manifest.json)
records the audit runtime, package versions, code hash, input hashes and output
hashes. The [figure manifest](../outputs_GEN2/step1_baseline_inventory/figure_manifest.json)
records the plotting code, inputs and generated figures.

All new outputs are under `outputs_GEN2/step1_baseline_inventory/`. The Gen1
inputs retained their original hashes. Generated Gen2 data follows the existing
Git ignore policy for generated Gen1 artifacts.

### Shape Change

All 13 tables contain **7,405 unique HPP food IDs**, with matching ID sets.
All retain 7,405 rows after this audit. Columns added, dropped, renamed or imputed
in each source table: **0**. The audit uses `hpp_food_id` as its common join-key
name; it does not rename the `food_id` column in the HPP source file.

| Table | Columns before | Columns after | Identity / descriptor columns | Other columns |
|---|---:|---:|---:|---:|
| HPP input | 161 | 161 | 8 | 153 |
| Gen1 de novo reference | 246 | 246 | 11 | 235 |
| Gen1 NutriMatch-based reference | 207 | 207 | 11 | 196 |
| De novo: broad diet health | 1,209 | 1,209 | 11 | 1,198 |
| NutriMatch-based: broad diet health | 1,148 | 1,148 | 11 | 1,137 |
| De novo: cardiometabolic | 906 | 906 | 11 | 895 |
| NutriMatch-based: cardiometabolic | 883 | 883 | 11 | 872 |
| De novo: chemical/metabolomics | 226 | 226 | 11 | 215 |
| NutriMatch-based: chemical/metabolomics | 226 | 226 | 11 | 215 |
| De novo: mental health | 914 | 914 | 11 | 903 |
| NutriMatch-based: mental health | 887 | 887 | 11 | 876 |
| De novo: microbiome | 930 | 930 | 11 | 919 |
| NutriMatch-based: microbiome | 905 | 905 | 11 | 894 |

"Other columns" includes annotations, categories and text evidence as declared
by the existing schema; it is not the number of independent numeric predictors.
The reference tables contain 192 de novo nutrient columns versus 153
NutriMatch-based nutrient columns. Both also contain 43 inherited reference
fields and 11 identity/descriptor fields.

Full [table inventory](../outputs_GEN2/step1_baseline_inventory/table_inventory.csv)
and [per-column profiles](../outputs_GEN2/step1_baseline_inventory/column_profiles.csv)
include exact counts, missingness, numeric zeros, value ranges, feature families
and source paths. Gen1 family labels are retained as declarations, not validated
Gen2 classifications.

### Five-Food Preview

Selection used food descriptions, preparation specificity and logging frequency.
The IDs are pinned for later checkpoints. The bread example explicitly specifies
whole wheat and sourdough; the more common "Brown bread" description is ambiguous.

| Food | HPP food ID | Product description | Simplified / canonical name | Before and after this step |
|---|---|---|---|---|
| Espresso | 1007294 | Espresso | Coffee | 153 shared nutrients present; 0/39 extras present; unchanged |
| Cooked spinach | 1009997 | Fresh cooked spinach | Chard | 153 shared nutrients present; 0/39 extras present; unchanged |
| Turkey pastrami | 1013314 | Turkey pastrami sausage | Pastrami | 153 shared nutrients present; 0/39 extras present; unchanged |
| Whole-wheat sourdough | 1011816 | Whole wheat sourdough bread and cereals | Wholemeal Bread | 153 shared nutrients present; 0/39 extras present; unchanged |
| Yogurt, 3% fat | 1009118 | Bio yogurt 3% fat | Natural Yogurt | 153 shared nutrients present; 0/39 extras present; unchanged |

For these five foods, every present exported nutrient is labeled `hpp_observed`
in Gen1. This means supplied by the HPP input, not verified laboratory measurement.
None of their 39 extra fields contains a donor-transferred value.

### Example Values

These are the recorded Gen1 values, identical across the two scenarios for shared
nutrients. Gen1 declares nutrients to be per 100 g, but physical units were not
validated here. Read these as source values, not newly harmonized Gen2 doses.

| Food | Energy | Protein | Total lipid (fat) | Fiber | Caffeine | Leucine | Extra `leucine` |
|---|---:|---:|---:|---:|---:|---:|---|
| Espresso | 9 | 0.12 | 0.18 | 0 | 212 | 0.081 | missing |
| Cooked spinach | 33 | 3.41 | 0.70 | 1.9 | 0 | 0.223 | missing |
| Turkey pastrami | 110 | 13.00 | 4.00 | 0 | 0 | 1.133 | missing |
| Whole-wheat sourdough | 228 | 10.50 | 6.00 | 8.2 | 0 | 0.718 | missing |
| Yogurt, 3% fat | 63 | 5.25 | 1.55 | 0 | 0 | 0.454 | missing |

Recorded zeros remain distinct from missing values. Their biological meaning has
not been verified. The yogurt name/value mismatch is a review flag, not a numeric
correction made in this checkpoint.

Inspect the [compact five-row preview](../outputs_GEN2/step1_baseline_inventory/five_food_values.csv),
[all de novo columns for these five foods](../outputs_GEN2/step1_baseline_inventory/five_food_denovo_all_columns.csv),
[all NutriMatch-based columns](../outputs_GEN2/step1_baseline_inventory/five_food_nutrimatch_based_all_columns.csv),
and [five-food coverage counts](../outputs_GEN2/step1_baseline_inventory/five_food_coverage.csv).

### Shared And Extra Columns

**All 207 shared columns are exactly equal after alignment by HPP food ID**,
including matching missing values. This comprises 11 identity/descriptor fields,
153 nutrients and 43 inherited reference fields. There are no NutriMatch-only
columns in this comparison. The [column comparison](../outputs_GEN2/step1_baseline_inventory/shared_column_comparison.csv)
records equality, differing-cell counts and paired-value counts for every field.

The **39 de novo-only nutrient columns already existed in Gen1**; they were not
added in this step. Their exact names and individual profiles are in
[de novo extra columns](../outputs_GEN2/step1_baseline_inventory/denovo_extra_columns.csv).

Seventeen extra names match existing names after case, underscore and whitespace
normalization: `arginine`, `biotin`, `cystine`, `histidine`, `iodine`, `isoleucine`,
`leucine`, `lysine`, `methionine`, `pantothenic_acid`, `phenylalanine`, `serine`,
`sugar_alcohols`, `threonine`, `tryptophan`, `tyrosine`, and `valine`.
For example, `leucine` matches the name `Leucine`, and `pantothenic_acid` matches
`Pantothenic acid`. These are **candidate aliases only**. Units, analyte identity
and source definitions must be checked before merging.

The other 22 extras were not assessed beyond that simple name check. Lack of a
name match does not establish novelty; fatty-acid names and vitamin-A forms may
also overlap existing columns. No feature was approved, merged or dropped here.

### Missingness And Sparsity

- All 153 HPP/NutriMatch shared nutrients are non-null for all 7,405 foods, but
  37.46% of these cells contain recorded zeros. Complete tables do not prove that
  every zero is a measured absence.
- Each of the 39 extra columns is **86.60% to 97.47% missing**.
- Median missingness across those columns is **88.62%**. Across all extra-column
  cells, **89.32% are missing**, leaving 10.68% present.
- All 39 extras exceed 80% missingness; none is entirely missing across all foods.
- Five extras have at least 80% recorded zeros among their present values:
  `biotin`, `erucic`, `iodine`, `parinaric`, and `sugar_alcohols`. All present
  values of the extra `iodine` column are zero. This is a descriptive flag, not
  a statistical test or evidence of true absence.
- All 39 extra columns require alias, unit and missingness review before any
  imputation decision. Reference-only versus modeling eligibility is deferred
  to the planned rubric; sparse fields are not automatically discarded.

The downstream inventory also separates zero rates from missingness. A table with
many encoded graph indicators can have low missingness while containing mostly
zeros; its width and completeness do not establish added predictive signal.

### Donors And Provenance

A donor food is a food record in an external composition database whose values
can be transferred after a food match. The selected donor is separate from the
OpenFoodFacts product match and from the source of each exported nutrient value.

| HPP example | Recorded nutrient donor | Source | Confidence label | Review concern |
|---|---|---|---|---|
| Espresso | No donor recorded in harmonized snapshot | Missing | Missing | Does not establish that no candidate existed elsewhere |
| Cooked spinach | Chard, raw | USDA_FNDDS | medium | Species/name conflict and cooked-versus-raw mismatch |
| Turkey pastrami | Pastrami | AUSNUT_Australia | high | Generic donor name does not establish turkey-specific composition |
| Whole-wheat sourdough | No donor recorded in harmonized snapshot | Missing | Missing | Grain mixture and sourdough specificity need later retrieval |
| Yogurt, 3% fat | Tofu yogurt | USDA_SR_Legacy | review | Dairy-versus-soy mismatch; existing needs-human-review flag is true |

These are Gen1 labels, not newly calibrated confidence scores. The three recorded
donors have candidate rank 1. The Gen1 code takes the top-ranked candidate unless
a human correction replaces it; it does not average the top three. It prefers
available HPP values, then transfers donor values into gaps. For this panel, the
HPP preference explains why the bad donor examples did not replace shared values.

Across all de novo nutrient cells:

| Recorded source | Cells | Share of present nutrient cells |
|---|---:|---:|
| HPP input (`hpp_observed`) | 1,132,965 | 97.35% |
| Public donor mapping (`de_novo_public_mapping`) | 30,853 | 2.65% |
| Missing | 257,942 | Not applicable |

This supports treating the old de novo output as HPP-first enrichment, not the
independent nutrient reconstruction planned for Gen2. The original
`outputs/mapping/hpp_public_food_mappings.csv` candidate list is unavailable in
this workspace. The harmonized snapshot preserves selected donors, but it cannot
support a retrospective top-N averaging experiment by itself.

The five-food extracts include the inherited OpenFoodFacts product and confidence
fields. Cooked spinach inherits "Organic Red Chard". FooDB compound counts and
HMDB pathway counts are annotation counts, not measured concentrations, pathway
activation, or disease effects. Large counts need evidence review before use as
dose-dependent predictors.

Source versions, exact nutrient units and conversion provenance are not fully
specified in these Gen1 snapshots. File hashes identify the audited local
artifacts; they do not substitute for upstream database release metadata.

Evidence: [selected donors](../outputs_GEN2/step1_baseline_inventory/five_food_selected_donors.csv),
[five-food nutrient provenance](../outputs_GEN2/step1_baseline_inventory/five_food_nutrient_provenance.csv),
and [whole-table provenance counts](../outputs_GEN2/step1_baseline_inventory/nutrient_provenance_summary.csv).

### Visualizations

The five-food coverage view separates nonzero values, recorded zeros and missing
cells. All five foods lack all 39 extra nutrient values.

![Five-food nutrient coverage](../outputs_GEN2/step1_baseline_inventory/five_food_coverage.png)

The selected-value view shows the `Leucine`/`leucine` example and inherited graph
counts alongside nutrient values. Color represents presence status, not magnitude.

![Five-food values and annotation counts](../outputs_GEN2/step1_baseline_inventory/five_food_values.png)

The aggregate view shows coverage across all 7,405 foods and the missingness
distribution of the 39 extras.

![Whole-baseline sparsity](../outputs_GEN2/step1_baseline_inventory/baseline_sparsity.png)

### Verification And Decision

All 17 recorded integrity checks passed: unique food IDs and complete schemas
for 13 tables, full nutrient-cell/provenance agreement for both reference tables,
matching panel identities, and unchanged input hashes. Food-ID sets were also
checked across all 13 tables. A focused comparison check verified that shuffled
rows align by ID and that missing-versus-zero differences are detected. The
three figures were visually inspected.

See [validation results](../outputs_GEN2/step1_baseline_inventory/validation.json)
and the [machine-readable summary](../outputs_GEN2/step1_baseline_inventory/summary.json).

What looks useful: stable food IDs, a reproducible baseline and five pinned
examples make later changes directly comparable.

What needs review: spinach/chard identity; raw/cooked compatibility; dairy/tofu
compatibility; the yogurt fat discrepancy; aliases and unvalidated units; the
meaning of zeros; and graph-count evidence quality.

Actual Astra/API token use in this step: **0 tokens, 0 model calls**.

Next proposed checkpoint after review: a five-food Layer 1 mapping pilot, starting
with food identity and preparation checks, an explicit nutrient/unit dictionary,
and source-backed donor candidates retrieved using embeddings and structured
filters. Keep HPP/NutriMatch nutrient values hidden from de novo mapping and use
them only for later comparison. Pin the model and embedding versions, show the
top candidates and donor strategy, and add the next checkpoint here before any
full-data run.

---

## Step 1b: Independent Five-Food Prototype

Date: 2026-09-22.

Status: independent value-generation prototype completed for five foods;
automated embedding mapping and the full 7,405-food rebuild are still pending.
The user clarified that all de novo columns must be independently created and
filled, with freedom to design a new schema. The preceding audit did not do that
and must not be presented as the Gen2 result.

### Corrected Scope

Every de novo feature is rebuilt from original food identity and public evidence.
There is no required Gen1 column match, preserved nutrient block or old generated
name. The model can add features and recipes beyond the old panel. Equal values
can still arise naturally from the same public evidence; lineage, not forced
disagreement, determines whether the result was independently generated.

The [updated plan](GEN2_PLAN_NOTES.md#de-novo-requirement-rebuild-every-column)
now removes the conflicting HPP/NutriMatch-first imputation rule, sets a modeling
completion target, and defines fallbacks with uncertainty. The NutriMatch methods
reading and citation are recorded there. The immediate lesson for our pipeline
is that completion requires an explicit imputation policy beyond initial matches.

### Inputs And Output Shape

The builder reads only `food_id`, `product_name`, `hebrew_name` and `short_name`
from the HPP input. It reads **zero nutrient columns**, **zero old generated
names**, and **zero NutriMatch or Gen1 output files**. Numeric source data comes
directly from the local USDA SR Legacy archive, including nutrient IDs, units,
food IDs and source derivation metadata.

USDA describes SR Legacy as including analytical, calculated and literature
values. A donor transfer therefore does not imply a new laboratory measurement
of the target food. See [USDA data documentation](https://fdc.nal.usda.gov/data-documentation/).

| Artifact | Rows | Columns / contents | Change |
|---|---:|---|---|
| Independent identity input | 7,405 | 4 identity fields | Newly exported allowlisted inputs |
| Public nutrient candidate catalog | 149 | Nutrient IDs, names, units, source support and status | New source-derived registry |
| Independent five-food matrix | 5 | 2 identity + 71 nutrient + 8 derived = 81 columns | 79 newly generated feature columns |
| Cell provenance | 395 | One record per food/feature value | 337 primary transfers, 18 proxy estimates, 40 derived values |
| Remaining public nutrient candidates | 78 | Candidate catalog entries outside the current pilot | Not completed; not counted in the 79-feature matrix |

All **395 cells in the declared 79-feature pilot are filled**. This does not mean
all source nutrients or all foods are complete. The first module covers major
nutrient families; additional sugars, starch, minor lipid species, other bioactives
and source-specific nutrients need further work. Their candidate entries and
available primary-donor evidence remain visible rather than being discarded.
No downstream predictive improvement has yet been measured.

### Fresh Donor Decisions

These decisions were made by reviewing original descriptions and the public
source catalog in this conversation, then saved for reproducible replay. They
were not selected by an embedding run or a separately pinned Astra/API call.

| Food / HPP ID | New public donor / FDC ID | Decision and remaining assumption |
|---|---|---|
| Espresso / 1007294 | Brewed restaurant espresso / 171891 | Caffeinated espresso; dilution/extraction remains uncertain |
| Cooked spinach / 1009997 | Spinach, boiled, drained, without salt / 168463 | Preserves spinach and cooked state; salt and cooking method are assumptions |
| Turkey pastrami / 1013314 | Pastrami, turkey / 172927 | Preserves species and processing; generic recipe and brand remain uncertain |
| Whole-wheat sourdough / 1011816 | Whole-wheat bread, prepared from recipe / 172690 | Approximate bread proxy; sourdough and cereal mixture are not established |
| Yogurt, 3% fat / 1009118 | Plain whole-milk yogurt / 171284 | Dairy donor; its 3.25 g/100 g fat approximates the 3% label |

The espresso donor lacks 18 amino-acid fields in this schema. Their estimates use
the amino-acid profile of brewed caffeinated coffee (FDC 171890), multiplied by
the ratio of espresso-donor protein to brewed-coffee-donor protein. That ratio is
1 for these records, but the formula is retained. This is an **unvalidated proxy
assumption**, not evidence that espresso and ordinary coffee have identical
amino-acid profiles. Four derived amino-acid sums inherit this uncertainty.

The original Hebrew labels were inspected for identity. No chard, raw vegetable,
tofu yogurt or beef-pastrami value is used as a substitute in these five choices.

### Five Fresh Example Rows

Values below are estimates per 100 g food, with units taken from the public
nutrient dictionary. They were regenerated from public source records, not
subtracted from or copied out of the baseline audit.

| Food | Energy, kcal | Protein, g | Fat, g | Fiber, g | Sodium, mg | Caffeine, mg | Leucine, g |
|---|---:|---:|---:|---:|---:|---:|---:|
| Espresso | 9 | 0.12 | 0.18 | 0 | 14 | 212 | 0.005 (proxy) |
| Cooked spinach | 23 | 2.97 | 0.26 | 2.4 | 70 | 0 | 0.231 |
| Turkey pastrami | 139 | 16.30 | 6.21 | 0.1 | 1,123 | 0 | 1.421 |
| Whole-wheat sourdough | 278 | 8.40 | 5.40 | 6.0 | 346 | 0 | 0.574 |
| Yogurt, 3% fat | 61 | 3.47 | 3.25 | 0 | 46 | 0 | 0.350 |

Before this independent build, these Gen2 records had only four original identity
fields and no generated feature values. After it, each has 79 feature values.
Source zeros are preserved with a source-row reference; missing values are not
silently converted to zero.

### New Feature Definitions

The 71 nutrient features use USDA nutrient IDs and explicit unit/basis suffixes,
for example `usda_1003_g_per_100g` for protein. This avoids treating source-name
variants as different nutrients. The source registry is independent of Gen1.

The eight compound features are new recipes in this Gen2 prototype, not claims
that these mathematical quantities are novel to nutritional science:

| Feature | Recipe | Unit |
|---|---|---|
| Essential amino-acid total | Sum of the nine specified essential amino acids | g/100 g |
| Branched-chain amino-acid total | Isoleucine + leucine + valine | g/100 g |
| Aromatic amino-acid total | Tryptophan + phenylalanine + tyrosine | g/100 g |
| Sulfur amino-acid total | Methionine + cystine | g/100 g |
| EPA + DHA + DPA | Sum of those three specified fatty-acid quantities | g/100 g |
| Unsaturated fatty-acid total | Monounsaturated + polyunsaturated fatty acids | g/100 g |
| Sodium-to-potassium mass ratio | Sodium in mg divided by potassium in mg | Dimensionless |
| Unsaturated-to-saturated fat ratio | (Monounsaturated + polyunsaturated) / saturated fatty acids | Dimensionless |

These recipes are candidates for prediction, not validated disease/pathway effect
scores. No claim of independent information gain is made merely because a sum or
ratio adds a column. All pilot denominators are positive; a full-data recipe must
explicitly handle zero denominators before deployment. The ratios are computed
features, not consumed amounts to multiply directly by portion grams.

### Files And Reproduction

- [Five-food feature matrix](../outputs_GEN2/step1b_independent_pilot/independent_pilot_features.csv).
- [Exact column dictionary and formulas](../outputs_GEN2/step1b_independent_pilot/feature_dictionary.csv).
- [Cell-level provenance and uncertainty](../outputs_GEN2/step1b_independent_pilot/cell_provenance.csv).
- [Reviewed donor decisions](../outputs_GEN2/step1b_independent_pilot/reviewed_donor_decisions.csv).
- [Full public nutrient candidate catalog](../outputs_GEN2/step1b_independent_pilot/public_nutrient_catalog.csv).
- [Available primary-donor evidence, including non-pilot nutrients](../outputs_GEN2/step1b_independent_pilot/primary_donor_evidence_long.csv).
- [Summary](../outputs_GEN2/step1b_independent_pilot/summary.json) and [run manifest](../outputs_GEN2/step1b_independent_pilot/run_manifest.json).

The new implementation is under `diet_data_enhancement_GEN2/`. Reproduce from
the repository root:

```sh
python -m diet_data_enhancement_GEN2.independent_pilot
python -m diet_data_enhancement_GEN2.plot_independent_pilot
python -m unittest diet_data_enhancement_GEN2.test_independent_pilot
```

The manifest hashes only the allowlisted identity representation for the HPP
input, so excluded nutrient values are not part of the generator's input
signature. It separately hashes the public archive, code, configuration and
outputs. Public source derivation IDs and their dictionary are retained.

### Visualizations

![Independent five-food values](../outputs_GEN2/step1b_independent_pilot/independent_values.png)

![Five-food and aggregate feature origins](../outputs_GEN2/step1b_independent_pilot/independent_coverage.png)

### Verification And Remaining Work

The input-boundary tests pass: changing an HPP nutrient or old LLM-generated name
does not change the identity input, and duplicate food IDs are rejected. The
builder checks source identities, nutrient uniqueness, numeric validity,
non-missing pilot values and a unique provenance row for every feature cell.

The model-generated decisions here are preserved in configuration for replay,
but their accuracy and the espresso proxy still need validation. This is not a
formal blinded experiment: this conversation has already displayed old baseline
values. The production run must use fresh contexts without those values.

The current runtime has no configured API key for automated embedding calls.
External embedding calls and external adjudication API calls in this prototype:
**0**. No external model version or vector score is claimed. This does not count
the assistant's reasoning in the conversation as zero token usage.

Remaining scope: source expansion, completion of additional nutrient candidates,
fresh embedding retrieval, pinned current-model adjudication and rubric learning,
top-N comparison, validated imputation, then extension to all 7,405 foods and the
broader chemical/pathway feature families. The fully populated 79-feature pilot
is a concrete start, not a claim that these remaining tasks are finished.
