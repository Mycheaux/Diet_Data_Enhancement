# Generation 2

Code lives here. Generated artifacts live in `outputs_GEN2/`. Checkpoint reviews
live in `docs/GEN2_details.md`; the design is in `docs/GEN2_PLAN_NOTES.md`.

Step 1 produces two primary food tables: NutriMatch-based and independent de
novo, with supporting provenance and review artifacts. Downstream task goals
can guide feature coverage, but task-specific datasets and prediction remain
later work (Layer 5: feature QC; Layer 7: downstream datasets). Step 1 is still
in progress. The approved pilot is preserved; the expanded checkpoint below
also exports the unchanged full NutriMatch-based comparator.

## Independent De Novo Requirement

De novo is rebuilt from original food identities and public evidence. It does
not inherit Gen1 feature columns, old generated food names, old donor choices,
HPP nutrient values, or NutriMatch values. The feature schema can expand freely
with distinct, defined quantities and explicit compound recipes. Gen1 comparison
is optional and happens after generation; identical values are possible when
independent procedures select the same public evidence.

The baseline audit below reads old outputs for diagnosis only. Do not use it as
a feature generator or import its matrices into a de novo builder.

## Step 1: Independent Prototype

```sh
python -m diet_data_enhancement_GEN2.independent_pilot
python -m diet_data_enhancement_GEN2.plot_independent_pilot
python -m unittest diet_data_enhancement_GEN2.test_independent_pilot
```

This produces `outputs_GEN2/step1b_independent_pilot/`: 7,405 identity-only input
rows and a five-food, 79-feature prototype with a new public-source dictionary,
cell provenance, donor decisions and figures. It uses 71 independently chosen
USDA nutrient IDs and eight algebraic compound features. All 395 feature cells
are populated. Eighteen espresso amino-acid cells use a protein-scaled brewed
coffee proxy; four derived cells inherit that uncertainty. These proxy estimates
have not been empirically validated.

The folder retains its historical `step1b` name. The eight compound features
are exploratory food-level recipes within the de novo pilot, not separate
task-specific exports. The comparator export was completed in the next checkpoint.

Donor choices were reviewed in the current conversation and are pinned in
`independent_pilot.json`. No external adjudication model or embeddings were run.
This is a transparent worked prototype, not the requested production vector
mapping pipeline or a completed 7,405-food dataset. The 78 other nutrient types
in the public source remain visible as uncompleted candidates; pilot coverage
must not be reported as completeness of that wider catalog.

`read_identity` uses a four-column allowlist at read time. Tests confirm changing
HPP nutrient values and old generated names cannot affect that input. The formal
blind evaluation must use a fresh model context, since the interactive discussion
has already displayed Gen1 values.

## Step 1: Expanded Checkpoint

```sh
python -m diet_data_enhancement_GEN2.expand_step1
python -m diet_data_enhancement_GEN2.export_nutrimatch_base
python -m diet_data_enhancement_GEN2.review_expanded_step1
python -m diet_data_enhancement_GEN2.plot_expanded_step1
python -m unittest diet_data_enhancement_GEN2.test_independent_pilot diet_data_enhancement_GEN2.test_schema_expansion
```

Outputs: `outputs_GEN2/step1c_expanded_schema/`. The two primary tables are
`denovo/food_features.csv` (five foods, 98 features plus two identifiers) and
`nutrimatch_based/food_features.csv` (7,405 foods, 153 supplied nutrients plus
two identifiers). The original 79-feature pilot and Gen1 outputs are unchanged.

The de novo builder reads the same original HPP identity allowlist, the raw
USDA SR Legacy archive, the reviewed donor configuration `independent_pilot.json`,
and identity interpretations in `schema_expansion.json`. It does not read the
comparator, Gen1 schemas, or older generated names. The comparator exporter is
a separate module; comparison runs only after both branch tables are frozen.
No external embeddings, adjudication calls or learned rubric are claimed.

The previous hard-coded 71-nutrient panel is replaced here by a catalogue-wide
coverage rule: assess every source nutrient ID, distinguish alternate
representations, and include every remaining eligible quantity available for
all five foods through primary transfers or the already reviewed amino-acid
proxy. This includes 86 nutrients, not a scientifically optimal or final schema.
Fifty-nine quantities need more completion work and one (`PUFA 2:4 n-6`) requires
source identity review. No missing value is treated as zero. Partial evidence
for excluded candidates remains in `denovo/candidate_evidence_long.csv`.

Two fixed unit aliases are excluded: energy kJ versus kcal, and total vitamin D
IU versus micrograms. Vitamin A IU is separately excluded as an alternate
activity convention; a universal IU-to-RAE conversion is **not** applied.
Definitions and sources are recorded in `denovo/alternate_representations.csv`:
[NIST energy units](https://www.nist.gov/glossary-term/26261),
[NIH vitamin D](https://ods.od.nih.gov/factsheets/VitaminD-HealthProfessional/),
[NIH vitamin A](https://ods.od.nih.gov/factsheets/VitaminA-HealthProfessional/).
The [USDA SR Legacy guide](https://www.ars.usda.gov/ARSUserFiles/80400525/Data/SR-Legacy/SR-Legacy_Doc.pdf)
explains the source structure and that missing entries do not mean zero.

The four identity descriptors preserve food family, preparation, fermentation
and grain-refinement information from original descriptions. `not_stated` is
an explicit unknown category, not a negative biological assertion. They do not
assert complete ingredients, NOVA scores, live cultures or pathway effects.
Downstream encoding must preserve unknown status. There are 13 informative
descriptor cells and seven unknown cells, separate from 470 complete numeric
cells. These descriptors are not new measured nutrients or evidence of more
predictive signal. Their ontology must be expanded before all-food application.

Exact new fields, coverage, pending reasons and lineage are in `new_columns.csv`,
`feature_coverage.csv`, `nutrient_registry.csv`, `pending_nutrients.csv` and
`cell_provenance.csv` under `denovo/`. The comparison confirms all 86 nutrient
names overlap the baseline; 260/430 matched values differ. All previously
approved values are preserved. Neither disagreement nor completeness validates
accuracy. The existing 18 espresso proxies remain unvalidated, and no new
numeric imputation is introduced here.

Eighteen tests check the coverage policy, unit/identity distinctions, explicit
unknowns, source lineage, original pilot reproducibility and exact comparator
preservation. Integration tests require both checkpoint branches to exist.
Each branch has a run manifest; comparison and plots have separate input hashes.
The plotting module uses matplotlib; the other modules need pandas and numpy.
Review `docs/GEN2_details.md` before starting another source or layer.

## Preparatory Gen1 Audit

This is the preparatory inventory before Layer 1 mapping. It reads the HPP input,
both Gen1 reference matrices, their schemas and nutrient provenance, all ten
existing downstream exports, and the selected-donor snapshot. It does not import
or run the Gen1 pipeline. No LLM call, nutrient change, alias merge, or imputation
is part of this audit. Inspecting these old downstream tables did not create any
Gen2 downstream outputs or advance the later layers.

From the repository root, using a Python environment with pandas and numpy:

```sh
python -m diet_data_enhancement_GEN2.step1_baseline_inventory
```

For figures, also install matplotlib in the plotting environment:

```sh
python -m diet_data_enhancement_GEN2.plot_step1
```

The repository's existing requirements cover these packages. Actual package
versions, source hashes and generated-table hashes are saved in the run manifest;
figure inputs and hashes have a separate manifest. Rerunning replaces only the
named Step 1 artifacts. Preserve the current outputs if comparing later runs.

`five_food_panel.json` pins the five examples and explains their selection.
Coverage is unweighted by logging frequency. Missing cells, recorded zeros and
nonzero values are separate categories. A zero is not assumed to be biological
absence. Aliases are name-based candidates only, requiring later unit and
chemical-identity checks. Gen1 feature-family and per-100g labels are retained
as source declarations, not newly validated classifications.

Validation checks food-ID uniqueness, matching food-ID sets, complete feature
schemas, panel identity, nutrient-value/provenance agreement and unchanged input
hashes. The next checkpoint begins after user review.
