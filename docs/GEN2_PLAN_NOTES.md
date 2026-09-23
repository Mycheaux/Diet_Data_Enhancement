# Generation 2 Diet Data Enhancement Plan Notes

------------------------------

## SUMMARY

Layer 1: create two base food tables, NutriMatch-based and independent de novo.
For de novo, use public FCDBs, the newest available Astra-class model, vector
embeddings, multilingual matching, donor selection and top-1 versus top-N tests,
with no NutriMatch/HPP nutrient leakage. Rebuild every de novo value and design its schema independently;
complete modeling features through documented transfer, estimation and recipes.
Keywords: original food identity, new schema, embeddings, donor food, per 100 g,
completion hierarchy, provenance.

Layer 2: product and processing enrichment from OpenFoodFacts and related
product databases, keeping only source-backed per 100 g values where available.
Keywords: ingredients, NOVA, Nutri-Score, additives, brands, product nutrients,
processing.

Layer 3: chemical and metabolite dose enrichment from FooDB, FoodAtlas,
FoodData Central, HMDB bridges, and specialized databases where available.
Keywords: compound concentration, mg per 100 g, chemical class, metabolite,
biofluid, source quality.

Layer 4: pathway and disease scoring from weighted upstream evidence rather
than flat graph links. Keywords: chemical dose, pathway weight, disease edge,
directionality, citation count, confidence, exposure index.

Layer 5: feature novelty, sparsity, and quality control before promoting
columns into modeling tables, using rubric learning to make decisions
consistent and auditable. Keywords: duplicate column detection, unit conversion,
missingness, alias table, imputation, sparsity reduction, provenance, LRRL.

Layer 6: mega KG plus reference tables with stable identifiers connecting every
food, source, nutrient, chemical, pathway, disease, evidence weight, and
downstream feature. Keywords: node table, edge table, HPP join table, audit
trail, TRE-ready exports.

Layer 7: broad and task-specific downstream feature datasets built from the KG,
reference tables, and literature-guided Astra feature design. Keywords:
cardiovascular, microbiome, glycemic, pathway-specific, compound features,
NutriMatch baseline, plus versions.

Workflow rule: move slowly and review one dataset/layer step at a time. Every
step must add a checkpoint entry to `docs/GEN2_details.md` with five example
foods, newly added columns, column counts, example rows, and visualizations
before the next step starts.

------------------------------

## DETAILS

These notes capture the main design direction for the next generation of diet
data enhancement using the same broad database universe: HPP, NutriMatch,
public food-composition databases, OpenFoodFacts, FoodAtlas, FooDB, HMDB, and
scenario-specific knowledge graph outputs.

## De Novo Requirement: Rebuild Every Column

User clarification, 2026-09-22: the de novo branch must be constructed from
scratch. This applies to all nutrients and all later feature layers, not only
columns absent from Gen1. Gen1's column names, number of columns, values,
generated names, canonical assignments and donor choices are not the starting
template. The LLM may propose additional nutrients, chemical groups, pathway
features and compound recipes from public evidence and literature. There is no
requirement to reproduce the old 153- or 192-nutrient schema.

Keep only the HPP food IDs and original descriptions needed to identify the
logged foods. Independently interpret original Hebrew/English names and product
descriptions using the new model. Read identity fields through an explicit
allowlist; do not load HPP numeric nutrient columns into mapping or imputation.
Do not reuse old `gpt_short_food_name` or inherited graph features as truth.
Any source category used later must also be checked against original identity.

The implementation should build a new feature registry with stable quantity
identifiers, units, derivation rules, provenance and uncertainty. Check novelty
against this new registry, including semantic aliases; comparison with Gen1 is
optional after generation. A newly generated value may legitimately equal a
Gen1 value if both select the same public source. Independence is established
by inputs and value lineage, not by forcing numerical disagreement.

Aim for complete model-ready values for the declared feature set. A populated
value can be a donor transfer, supported estimate or computed recipe; each must
identify which. Keep the underlying evidence table separately, preserving actual
source gaps. Broader candidate columns that remain unresolved must remain visible
in the coverage report. Completing a small selected subset does not complete the
whole catalog or all 7,405 foods.

The NutriMatch-based comparator can retain its original nutrients. The independent
de novo output cannot use them as fallbacks. Any later `denovo_plus_nutrimatch`
comparison must be a separately named export after the de novo table is frozen.

### NutriMatch Methods Reading

The paper describes top-five embedding retrieval, LLM equivalence checks,
database prioritization and nutrient transfer. Unresolved foods receive a
nearest-food fallback, explaining its completeness strategy. Its reported panel
has 151 nutrients; our local snapshot has 153, so those schemas are not assumed
identical. Completeness alone does not establish measurement or accuracy.
Source: [NutriMatch, Methods: Alignment and Imputation](https://www.nature.com/articles/s44482-025-00001-7.pdf).

Gen2 should implement its own explicit completion hierarchy, then test the
accuracy and predictive value of each tier. The old local pipeline's combination
of HPP-first values, incomplete donor coverage and unresolved aliases explains
why its extras remained sparse. That is an implementation limitation to fix,
not a reason to constrain the new schema to Gen1.

## Main Motivation

The current system is strong as a food-reference enrichment framework, but the
next generation should make a sharper distinction between:

- measured or transferable quantitative dose values;
- semi-quantitative evidence scores;
- annotation-only biological context.

This matters because not every food-to-chemical or food-to-pathway link should
be treated like a measured amount. Two foods can connect to the same chemical
while containing very different concentrations. The same food eaten in different
amounts should also contribute proportionally different exposure. Generation 2
should therefore separate true dose scaling from graph evidence and biological
annotation.

## Slow Checkpoint Workflow

Step 1 has exactly two primary food-table outputs: **NutriMatch-based** and
**independent de novo**, plus their supporting dictionaries, provenance and
review figures. Each row represents a food. Planned downstream tasks may guide
which food attributes and candidate columns are useful now, but Step 1 does not
create task-specific tables, select features against outcomes, or run prediction.
Layer 5 provides feature quality control; Layer 7 creates broad and task-specific
downstream datasets. The seven-layer design otherwise remains unchanged.

Initial status (2026-09-22): Step 1 began with a preparatory audit and an
independent five-food pilot: 71 nutrient columns and eight exploratory compound
features, all 395 cells populated. This approved pilot is preserved unchanged.

Current status (2026-09-23): **Step 1 remains in progress.** A second checkpoint
assesses all 149 public-source nutrient IDs and expands the five-food table to
86 nutrients, eight existing formulas and four identity descriptors (98 features).
It adds 15 direct-source nutrients and four description-derived fields, not new
task-specific outcomes. All 470 numeric cells are populated; seven of 20
descriptor cells explicitly report unknown information. Sixty distinct nutrient
candidates remain pending, with missing evidence retained. Two unit aliases and
the alternate vitamin A IU activity convention are not added as new predictors.
This is a transparent coverage rule, not learned rubric selection. No new
numeric imputation, automated embedding or external model calls have run.
The separate NutriMatch-based Gen2 table is now exported for all 7,405 foods and
153 original nutrient columns, with values unchanged. The full de novo table,
broader feature discovery and production embedding/model validation remain pending.

The short checkpoint is in `docs/GEN2_details.md`; the earlier long record is
archived in `docs/GEN2_details_archive_2026-09-22.md`. The existing pilot folder
`outputs_GEN2/step1b_independent_pilot/` keeps its historical name. References to
downstream exports in the archived audit describe inspected Gen1 files, not
completed Gen2 work. The expanded checkpoint is in
`outputs_GEN2/step1c_expanded_schema/`, with separate `denovo/` and
`nutrimatch_based/` branches. No later Gen2 layer has run.

Generation 2 should be run as a slow, review-gated pipeline. After each dataset,
database, mapping layer, imputation layer, KG layer, or downstream feature
export is added, the agent must write a checkpoint to:

```text
docs/GEN2_details.md
```

The next step should not begin until the user reviews that checkpoint and asks
to continue.

Generation 2 implementation should be kept separate from the existing Gen1 code
and outputs. New reproducible code should live under:

```text
diet_data_enhancement_GEN2/
```

New generated outputs should live under:

```text
outputs_GEN2/
```

The existing `diet_data_enhancement/` package and `outputs/` folder should be
treated as Gen1/reference artifacts unless a specific migration step explicitly
copies or adapts logic into the Gen2 package. This separation should make it
clear which results came from the old pipeline and which came from the new
rubric-guided, checkpointed Gen2 pipeline.

Each checkpoint should include:

- a short current-stage summary; keep long audits and reproducibility details
  in linked artifacts so `GEN2_details.md` remains easy to review;
- step name, date, input files, output files, and command or notebook used;
- five representative HPP foods shown before and after the step;
- what each of the five foods gained from the new data source or layer;
- the exact new columns added, grouped by feature family;
- number of rows and columns before the step;
- number of rows and columns after the step;
- number of added columns, dropped columns, renamed columns, and imputed columns;
- missingness and sparsity summary for the new columns;
- provenance fields added or changed;
- five-row preview table for the selected foods;
- at least one compact visualization of the five foods;
- at least one aggregate visualization of the new columns or missingness;
- interpretation: what looks useful, what looks suspicious, and what needs
  human review before the next step.

Useful five-food visualizations include a small heatmap of new feature values, a
food-by-feature presence matrix, a before/after feature-count bar chart, a
donor/source provenance diagram, or a mini KG neighborhood plot for those five
foods. The visualization should be simple enough to inspect quickly and should
make it obvious what changed in the current step.

The five example foods should be reused where possible so changes can be tracked
across layers, but the checkpoint can swap in source-specific examples when a
dataset only affects a narrow food class. A good default panel is:

```text
coffee
boiled spinach or leafy vegetable
processed meat example
whole grain or bread example
yogurt or fermented dairy example
```

This checkpoint workflow is part of quality control, not presentation polish.
The purpose is to make every data-source addition inspectable before it becomes
buried inside a large feature table or KG.

## Feature Classes

Generation 2 should explicitly tag every feature as one of the following
classes.

1. Dose-valued features

These are true or estimated amounts per 100 g food. Examples include nutrients,
caffeine, nitrate, sodium, selected polyphenols, or any FooDB/FoodAtlas compound
where concentration can be parsed and normalized to a common unit.

Diet-event scaling:

```text
event_amount = reference_per_100g * consumed_g / 100
```

2. Semi-quantitative evidence features

These include source quality, mapping confidence, number of supporting database
links, concentration range quality, preparation specificity, annotation quality,
and evidence count. These features can weight a dose or rank confidence, but
they are not themselves consumed amounts.

3. Annotation-only biological features

These include many disease, pathway, biospecimen, and metabolite graph labels.
They are useful for hypothesis generation and model features, but should not be
described as direct per-100 g pathway amounts unless a defensible quantitative
chemical-to-pathway model is built.

## Layer 5: Rubric-Learned Feature Quality Control

Generation 1 used mostly fixed rules and after-the-fact summaries for feature
quality control. Nutrient names were harmonized with manually written rename
maps, source-food matches were ranked by deterministic text similarity, the
top-ranked candidate was usually selected unless human correction existed, HPP
values were preferred before public-source values, and provenance was recorded
after the selected value was chosen. This was useful and transparent, but it did
not provide one unified decision system for detecting duplicate columns,
resolving aliases, judging sparsity, deciding when imputation is safe, or
deciding whether a feature belongs in the broad modeling matrix versus only in a
reference table.

Generation 2 should turn Layer 5 into a feature-governance layer inspired by
LLM rubric learning methods such as LRRL. The goal is not to let the LLM make
uncontrolled feature decisions, but to use Astra to learn a clear rubric from a
diverse set of examples, convert that rubric into structured rules, and then
apply those rules reproducibly across all candidate columns.

Each candidate feature should first be serialized into a column card:

```text
column_name
source_database
source_table
feature_family
unit
unit_status
per_100g_status
non_null_rate
zero_rate
value_min
value_median
value_max
example_values
closest_existing_columns
semantic_similarity_to_existing_columns
correlation_with_existing_columns
known_aliases
missingness_pattern
provenance_fields_available
unit_conversion_possible
candidate_downstream_role
```

Astra should then inspect a stratified sample of column cards and synthesize a
global feature-QC rubric. The sample should include known duplicates, unit
variants, aliases, sparse-but-important columns, sparse-and-weak columns,
columns eligible for imputation, columns not eligible for imputation, and
columns with strong versus weak provenance.

The learned rubric should score each candidate column on:

- semantic identity: same feature, synonym, subtype, superclass, related but
  distinct biology, or truly new feature;
- unit and scale: explicit unit, convertible unit, ambiguous unit, per 100 g
  valid, or not dose-valued;
- missingness: true absence, unknown value, source-coverage failure, not
  applicable, or measurement below detection;
- sparsity: broad-model ready, task-specific only, reference-table only, or
  too sparse/weak to use;
- alias handling: keep new, merge with existing, store as alias, or drop;
- imputation eligibility: safe to impute, conditionally impute, do not impute,
  or send to HITL;
- provenance quality: complete, acceptable, weak, missing key evidence, or
  unusable;
- final action: keep_new, merge, convert_unit, alias_only, impute,
  reference_only, drop, or HITL.

After the rubric is learned, most decisions should be made by deterministic code
using the rubric fields. Astra should be reserved for ambiguous or high-impact
columns. This makes the process cheaper and more reproducible than asking the
model to judge every column independently.

This is an improvement over Generation 1 because it changes feature QC from
manual checks plus provenance logs into an auditable decision layer. For
example, Gen 1 might keep `caffeine`, `caffeine_mg`, and a source-specific
caffeine field as separate columns unless manually caught. Gen 2 should classify
them as the same biological quantity, standardize units, merge or alias them,
and record that decision. Likewise, a sparse FooDB compound column should not be
promoted automatically; the rubric should decide whether it is a meaningful
task-specific exposure, a source-coverage artifact, or reference-only evidence.

Generation 2 should include a dedicated completion task to populate the declared
modeling features and test whether this increases downstream signal. Distinguish
true absence from missing coverage and record every estimate as an estimate.
Completeness is a target for the modeling export, while the evidence export
preserves unknowns. Do not report success by silently removing hard columns or
turning all unknowns into zeros. Report candidate, accepted, completed and
unresolved feature counts separately.

Imputation should be considered separately for each feature family:

- de novo nutrients: rebuild every value from independent public donor foods,
  compatible donor ensembles, recipe calculations or explicit learned estimates;
  HPP/NutriMatch nutrient values are never inputs or fallbacks;
- NutriMatch-based comparator nutrients: original values may be retained only
  in this separately named branch;
- chemicals/metabolites: impute only within comparable food groups,
  preparation states, or source-database neighborhoods; do not treat unknown
  compound content as zero unless the source explicitly supports absence;
- processing/product features: impute from product/category evidence only when
  food identity and preparation are sufficiently specific;
- pathway/disease scores: impute from upstream dose-capable chemicals or
  metabolite evidence, not from disease labels alone;
- embeddings/food-card features: allow model-derived embeddings to fill broad
  representation gaps, but keep them separate from measured dose features.

The completion hierarchy for the independent branch is:

1. Use a validated, preparation-compatible source value with a known unit.
2. Retrieve further candidates per missing nutrient, across independently
   parsed public FCDBs; one donor need not supply the entire profile.
3. Use top-N compatible donors or an explicit recipe/mass-balance calculation
   when it provides a better estimate than a single approximate donor.
4. Use a compatible food-family or multivariate estimate trained on public
   composition data, with held-out-source validation and uncertainty. Train any
   participant-dependent transformation inside training folds only.
5. Use an explicitly labeled LLM prior only when its supporting assumptions,
   plausible range and uncertainty can be recorded. It must not be described as
   measured or database-backed when the numerical value is model-generated.
6. Where no defensible estimate exists, retain the unresolved candidate and
   explain the gap. Do not pretend a zero or arbitrary number is a chemical dose.

Every completed column needs a definition and every populated cell needs a
method and source/recipe. For derived features, propagate the uncertainty of
estimated inputs. A confidence-weighted sum or ratio is a new feature recipe,
not automatically an established biological mechanism or improved predictor.

Every imputed value should carry provenance columns:

```text
imputation_method
imputation_source_scope
imputation_confidence
imputation_uncertainty
observed_or_imputed
donor_food_count
nearest_neighbor_distance
category_support_count
rubric_imputation_decision
```

Recommended imputation branches:

```text
no_imputation
conservative_imputation
task_family_imputation
exploratory_imputation
```

`conservative_imputation` should use only high-confidence donor foods, compatible
units, and close food/category matches. `task_family_imputation` can impute
features that are sparse globally but important for a specific downstream family,
such as microbiome substrates, glycemic carbohydrates, lipid-related compounds,
or sleep-relevant dietary exposures. `exploratory_imputation` can be broader,
but must remain labeled and evaluated separately.

Imputation should be evaluated as an ablation. For each downstream task family,
compare no-imputation, conservative imputation, and task-family imputation using
the same model family and cross-validation split. Report whether imputation
improves prediction, calibration, feature stability, and interpretability, and
whether the gain comes from real signal or leakage/proxy artifacts.

## Source Enrichment Step

Generation 2 should add a dedicated food-chemical composition enrichment step
before pathway or disease scoring. The priority is full FooDB enrichment because
FooDB is already part of the project and contains food-compound content fields
that are currently underused.

Priority source order:

```text
1. Full FooDB compound-content enrichment
2. Nitr-Navigator for nitrate, nitrite, and nitrosamine-focused analyses
3. Phenol-Explorer for polyphenols
4. EuroFIR eBASIS for plant bioactives where access permits
5. PhytoHub for phytochemicals, metabolites, and food-source links
6. USDA FoodData Central for nutrient-like food components
```

The full FooDB step should parse all available food-compound content records,
not only compact compound counts or top chemical classes. For each FooDB
food-compound row, retain:

- FooDB food identifier and food name;
- FooDB compound identifier, public identifier, and compound name;
- original content, original minimum, original maximum, and original unit;
- normalized concentration where possible, preferably mg per 100 g;
- preparation type and citation;
- compound taxonomy, annotation quality, InChIKey, PubChem, ChEBI, KEGG, and
  HMDB bridge fields where available;
- parsing status, unit-normalization status, and confidence.

After parsing FooDB content, map it through the existing canonical/HPP food
crosswalk so each HPP `food_id` can inherit a chemical concentration profile
from the best available canonical helper or source-food match. The output should
support both continuous exposure reconstruction and high/medium/low ranking for
each chemical.

Recommended FooDB-derived table:

```text
hpp_food_id
canonical_food_id
source_food_id
source_food_name
chemical_id
chemical_name
chemical_class
chemical_superclass
concentration_mg_per_100g
concentration_min_mg_per_100g
concentration_max_mg_per_100g
low_mid_high_rank
percentile_within_chemical
source_database
source_quality_weight
mapping_confidence_weight
preparation_type
citation
provenance_status
```

## Chemical Dose Model

Where compound concentration is available, Generation 2 should build explicit
chemical exposure values:

```text
chemical_exposure =
  chemical_concentration_per_100g
  * consumed_g / 100
  * mapping_confidence_weight
  * source_quality_weight
  * preparation_or_bioavailability_weight
```

The per-100 g chemical table should retain original value, parsed numeric value,
unit, normalized unit, min/max/range where available, source database, source
food, mapped HPP food, mapping method, confidence tier, and any preparation
context.

Important design rule:

```text
food -> chemical edges with numeric concentration are dose-capable;
food -> chemical-class edges are annotation or semi-quantitative summaries.
```

## Pathway And Disease Exposure Model

Pathway and disease features should be derived from weighted upstream evidence,
not treated as measured food amounts.

A defensible pathway exposure score could be:

```text
pathway_exposure_score =
  sum over linked chemicals/metabolites:
    chemical_dose
    * chemical_to_pathway_weight
    * evidence_confidence
```

This makes the pathway score an exposure index, not a causal claim. Disease
features should be even more conservative: useful as graph neighborhoods,
hypothesis labels, and downstream predictors, but not interpreted as direct
diet-disease effects.

Generation 2 should support both global edge weights and task-family-specific
edge weights. The global edge weight captures general evidence quality and
biological plausibility. The task-family-specific weight captures whether that
same edge is likely to help a planned downstream prediction family. This keeps
the model broad enough for discovery while still letting prediction tasks use
the most relevant disease, pathway, nutrient, chemical, metabolite, and
processing signals.

Recent downstream work suggests the first task families should include:

- cardiometabolic and cardiovascular biomarkers: triglycerides, total
  cholesterol, HDL, LDL, non-HDL cholesterol, blood pressure where available,
  creatinine, urate, ALT, AST, and GGT;
- glycemic and insulin-resistance tasks: glucose, HbA1c, postprandial glucose
  response, CGM trajectory, prediabetes/type 2 diabetes status, and TyG;
- body composition and obesity tasks: two-year obesity, waist circumference,
  waist-to-hip ratio, visceral adipose tissue, BMI/fat prediction, and related
  anthropometry;
- microbiome tasks: oral microbiome ecology, gut microbiome abundance,
  Shannon diversity, species richness, IBS-related phenotypes, and
  microbiome-linked substrate features;
- sleep and behavior tasks: diet effect on later sleep and post-meal movement
  priority;
- mental-health tasks: diet-linked mental-health prediction where target
  definitions are available;
- liver and inflammation tasks: fatty liver/liver attenuation, GlycA,
  inflammatory pathways, and liver enzyme signals.

The edge-weight table should therefore include columns such as:

```text
global_edge_weight
cardiometabolic_edge_weight
glycemic_edge_weight
body_composition_edge_weight
microbiome_edge_weight
sleep_behavior_edge_weight
mental_health_edge_weight
liver_inflammation_edge_weight
```

These weights should be learned or assigned with a rubric-learning pattern.
Astra can read task cards, prior notebooks, database evidence, and relevant
papers to build a rubric for each task family. The rubric should score whether
an edge is mechanistically relevant, dose-dependent, directionally interpretable,
specific enough, and likely useful for prediction. For example, a
food-to-polyphenol-to-inflammation pathway edge may receive a moderate global
weight, a high cardiometabolic or liver/inflammation weight, and a lower sleep
weight unless sleep-specific evidence is present.

The task-family weights should remain broad buckets, not one custom ontology per
single target. For example, LDL, triglycerides, and total cholesterol can share a
cardiometabolic/lipid rubric, while HbA1c, glucose, CGM, and TyG can share a
glycemic rubric. Target-specific models can still learn final coefficients, but
the KG export should provide stable task-family priors rather than manually
tuned target-by-target weights.

## Independent De Novo Nutrient Build

The current de novo and NutriMatch-based branches are identical for the shared
153 HPP nutrient columns because both preserve the same HPP nutrient information
after harmonization. That is useful for validation, but it is not a fully
independent de novo accuracy test.

In these notes, a donor food means the external database food whose values are
used to fill or estimate values for an HPP food. For example, if an HPP row is
`boiled spinach` and the best public food-composition database match is
`spinach, cooked, boiled, drained`, then the public database row is the donor
food. Its per 100 g nutrient or chemical values can be transferred to the HPP
food, while retaining source, confidence, mapping method, and provenance.
Donor-food adjudication means choosing which external source food should donate
values when several candidates are plausible.

Generation 2's primary de novo build must follow this sequence:

```text
1. Exclude HPP/NutriMatch nutrient values and old generated food names.
2. Reinterpret original food identity and preparation from original descriptions.
3. Design a new source- and literature-driven feature schema.
4. Retrieve public-source candidates using fresh embeddings and structured filters.
5. Validate candidates using a pinned current model and record the decisions.
6. Populate all accepted columns through the explicit completion hierarchy.
7. Compute new compound features with recorded formulas and uncertainty.
8. Freeze outputs before any optional Gen1/NutriMatch comparison.
9. Evaluate prediction, calibration, coverage and proxy sensitivity downstream.
```

Evaluation can show whether the independent representation is useful across
prediction tasks. NutriMatch is a comparator, not the schema template or a source
of ground-truth nutrient measurements. Use fresh model contexts for a formal
blind run; this exploratory conversation has already displayed baseline values.

Generation 2 should also test an alternate donor strategy. Gen 1 mostly used a
single top-ranked donor food for nutrient transfer. Gen 2 should keep that as a
baseline, but add explicit top-`n` donor averaging branches:

```text
top1_donor
top3_confidence_weighted_average
top5_confidence_weighted_average
topN_agreement_filtered_average
```

The top-`n` branches should average only biologically comparable candidates:
same food type, compatible preparation, compatible units, no obvious
raw-versus-cooked mismatch, and no category contradiction. The averaging weight
can combine match confidence, embedding similarity, source quality, preparation
match, and nutrient-value agreement. If candidate values disagree strongly, the
pipeline should down-weight the outlier, send the food to HITL, or fall back to
top-1 selection.

This should be evaluated as a change test: compare top-1 donor transfer against
top-3/top-5 weighted averaging using held-out HPP or NutriMatch values, and
report which strategy performs better by nutrient, source database, confidence
tier, food category, and preparation type.

## Stronger LLM Role

Improved LLMs should help, but only if they are used for the high-value parts of
the pipeline. The current LLM usage is mostly optional embeddings and candidate
validation, not full evidence adjudication.

Generation 2 should use the LLM as a controlled adjudication layer for:

- Hebrew-English food identity matching;
- ambiguous food-category and preparation interpretation;
- candidate donor-food ranking across public FCDBs;
- concentration text parsing where source tables contain ranges or native units;
- conflict resolution among independent public-source candidates during de novo
  construction; HPP/NutriMatch disagreement is examined only after freezing outputs;
- explanation of why a value should be accepted, rejected, or sent to HITL.

The LLM may create new feature definitions and propose estimates, but their
status must be explicit. Database-derived values must be source-backed,
unit-normalized and reproducible. LLM-generated priors must be tagged separately
with their prompt/model, assumptions and uncertainty; they are not measurements.

## Recommended Generation 2 Outputs

Generation 2 should produce four parallel output families:

```text
1. nutrient_dose_per_100g
2. chemical_dose_per_100g
3. pathway_exposure_score_per_100g
4. evidence_provenance_uncertainty
```

The `chemical_dose_per_100g` family should start with the full FooDB enrichment
table, then add specialized source modules such as Nitr-Navigator and
Phenol-Explorer for chemicals where those databases are stronger than FooDB.

Inside the TRE:

- dose-valued nutrient and chemical features scale by consumed grams;
- pathway scores aggregate as weighted exposure indices;
- disease and graph labels remain hypothesis and annotation features;
- all models can include provenance and uncertainty as explicit covariates or
  filtering criteria.

## Evaluation Plan

Generation 2 should be evaluated with ablations:

- NutriMatch only;
- current de novo;
- true de novo without HPP nutrient leakage;
- chemical-dose enhanced;
- pathway-score enhanced;
- conservative imputation;
- task-family imputation;
- LLM-adjudicated mapping;
- HITL-reviewed high-uncertainty subset.

Hold the downstream task, cohort, outcome, cross-validation and model family
fixed, then compare accuracy, calibration, stability and interpretability.
Record each branch's schema and recipe explicitly; the independent branch is
allowed to create a different feature set. Also run matched-feature ablations
where they answer a specific question, without constraining the broad new schema.

------------------------------

## TOKEN NEED

These are planning estimates for using Astra as the reasoning/adjudication model
in Generation 2. Exact token use depends on batching, number of candidate donor
foods per HPP food, number of papers read, and how much source evidence is
included in each prompt. The pipeline should cache every Astra decision so the
same food, source row, paper, or feature recipe is not paid for twice.

| Step | Astra role | Estimated tokens |
|---|---|---:|
| Layer 1 candidate adjudication | For each HPP food, compare embedding-retrieved and deterministic FCDB donor candidates, choose donor food, explain uncertainty, and flag HITL cases. | 1,500-4,000 tokens per food batch of 5-10 foods; about 1.5M-5M tokens for a full 7,000-8,000 food pass if aggressively batched. |
| Layer 1 top-N donor averaging test | Review top-3/top-5 donor groups, identify comparable candidates, choose weights, detect outliers, and decide when to average versus fall back to top-1. | 300K-1.5M tokens if limited to foods with multiple plausible high-quality donors. |
| Layer 1 nutrient conflict review | Review conflicts between public-source donor nutrients and held-out HPP/NutriMatch validation values after the independent de novo pass. | 300K-1M tokens for sampled review; 1M-3M tokens for full high-conflict review. |
| Layer 5 rubric learning | Read stratified column-card examples, synthesize the global feature-QC rubric, define scoring fields, and draft deterministic implementation rules. | 150K-500K tokens for initial rubric learning and revision. |
| Feature novelty and duplicate-column audit | Decide whether new columns are genuine, aliases, unit conversions, higher-level classes, or duplicates. | 200K-800K tokens, depending on number of candidate columns and source descriptions. |
| Imputation rubric and review | Decide which sparse features are eligible for conservative, task-family, or exploratory imputation, define provenance fields, and review ambiguous imputation candidates. | 250K-1M tokens depending on feature-family count and ambiguity. |
| Source quantitative audit | Classify OpenFoodFacts, FooDB, FoodAtlas, HMDB, FoodData Central, and specialized sources by per-100 g value availability and evidence type. | 100K-400K tokens for source schema review and rule writing. |
| Chemical/metabolite parsing support | Help interpret difficult units, ranges, preparation notes, and compound-content text when deterministic parsing is uncertain. | 500K-2M tokens if limited to uncertain rows; much higher if all rows are sent. |
| Pathway and disease weighting design | Design edge-weight rules for food-to-chemical-to-pathway-to-disease scoring, including directionality and source quality. | 100K-300K tokens for rule design and examples. |
| Task-family edge rubric learning | Read task cards, recent notebook summaries, database evidence, and papers to create broad cardiometabolic, glycemic, body-composition, microbiome, sleep/behavior, mental-health, and liver/inflammation edge-weight rubrics. | 300K-1.5M tokens, depending on number of task families and papers. |
| Literature-guided broad feature design | Read papers and propose general diet-derived feature families for the broad downstream dataset. | 500K-2M tokens for 20-80 papers, depending on abstract-only versus full-text use. |
| Task-specific feature recipes | For cardiovascular, microbiome, glycemic, liver, mental-health, and inflammation tasks, read papers and select/compose features from the broad dataset. | 300K-1.5M tokens per task family; 2M-8M tokens for six task families. |
| Final recipe validation and documentation | Check each feature recipe for leakage, duplicates, sparse columns, provenance, and NutriMatch baseline coverage. | 300K-1M tokens. |

Recommended practical budget:

```text
Minimal Gen2 design and sampled validation: 3M-8M tokens
Full mapping plus literature-guided task recipes: 10M-25M tokens
Very broad full-evidence run with many papers and row-level review: 25M-60M+ tokens
```

Token-saving rules:

- use embeddings and deterministic filters before Astra adjudication;
- send Astra only the top candidates and the evidence fields needed for the
  decision;
- batch similar foods together when context remains clear;
- cache model decisions by normalized food, source candidates, prompt version,
  and model version;
- use cheaper deterministic checks for exact duplicates, unit conversions, and
  sparse-column statistics;
- reserve Astra for ambiguous mapping, biological interpretation, literature
  synthesis, and feature-recipe design.
