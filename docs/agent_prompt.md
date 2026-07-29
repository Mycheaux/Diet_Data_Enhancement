# Agent Prompt For Recreating The Diet Data Enhancement Project

Use this prompt with Codex, Claude Code, or another coding agent when the data
files and paper/method text documents are already available. The goal is to
recreate the code, data-integration layers, outputs, notebooks, downstream
feature exports, and interactive visualizations in the same final design as the
current project.

```text
You are a senior scientific Python coding agent. Build a reproducible project
for HPP diet data enhancement using only the local files in this project folder.

Project objective
=================

Create an HPP food_id-level diet data enhancement pipeline that integrates:

1. HPP foods and HPP nutrient data.
2. Public nutrient databases: USDA/FNDDS, USDA SR Legacy, AUSNUT, Tzameret,
   Bahrain FCT, and MEXT Japan.
3. NutriMatch HPP nutrient panel, provided as a parquet file.
4. OpenFoodFacts product/processing data.
5. FooDB food-compound/constituent chemistry.
6. FoodAtlas food-chemical-disease graph evidence.
7. HMDB human metabolomics, disease, pathway, and biospecimen evidence.

The final analysis unit must remain the original HPP food identifier. Canonical
food concepts are allowed only as helper entities for mapping and evidence
sharing, not as the final downstream analysis key. Every final table intended
for downstream prediction must include HPP food_id-level rows so it can be
joined inside the TRE to participant diet logs.

The output should support NutriMatch-paper-style prediction tasks inside TRE:
join HPP food_id diet logs to an external food reference table, scale per-100 g
features by consumed grams, aggregate across diet events to participant-level
predictors, and compare prediction performance between feature-generation
strategies.

Important constraints
=====================

- Work only inside the project folder.
- Do not require participant-level TRE data.
- Use modular Python code so databases can be added, removed, or replaced.
- Keep all generated outputs under `outputs/`.
- Keep notebooks under `notebooks/`.
- Keep paper-style text docs under `docs/`; assume method/result text docs may
  already be provided and should not be overwritten unless explicitly asked.
- Use deterministic local matching as the default. Optional OpenAI/LLM sentence
  embeddings may be supported, but the API key must be requested interactively
  in the terminal and must never be saved to disk.
- All reproducible outputs must be regenerable from command-line pipeline
  commands.

Expected folder structure
=========================

Create or maintain:

data/
  HPP/
  Nutrimatch/
  USDA_FNDDS/
  USDA_SR_Legacy/
  AUSNUT_Australia/
  Tzameret_Israel/
  Bahrain FCT/
  MEXT_Japan/
  OpenFoodFacts/
  FooDB/
  FoodAtlas/
  HMDB/

diet_data_enhancement/
  __init__.py
  sources.py
  mapping.py
  canonical.py
  nutrients.py
  layered.py
  chem_bio_layers.py
  hpp_scenarios.py
  downstream_features.py
  nutrimatch_comparison.py
  multimodal.py
  final_kg.py
  graph_store.py
  pipeline.py
  hpp_kg_visualization.py
  hpp_kg_advanced_visualization.py
  hpp_kg_mega_visualization.py
  ui/
    __init__.py
    layered_server.py

notebooks/
  enriched_hpp_data_explorer.ipynb
  internal_validation_metrics.ipynb
  kg_visualization_and_checks.ipynb
  multimodal_food_concept_embedding_space.ipynb

outputs/
  layered/
  reference/
  canonical/
  nutrients/
  enhanced_hpp/
  downstream_features/
  visualizations/
  validation/

Pipeline design
===============

Implement a command dispatcher:

python -m diet_data_enhancement.pipeline <command>

At minimum support these commands:

layered-all
chem-bio-all
build-reference
build-hpp-enhancement-scenarios
build-hpp-comparison-layers
compare-nutrimatch
compare-nutrimatch-mapping
build-hpp-llm-sentence-embeddings
build-denovo-advanced-kg-viz
build-denovo-mega-flexible-kg-viz
build-downstream-feature-tables

The main reproduction sequence should be:

conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline layered-all
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline chem-bio-all
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline build-reference
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline build-hpp-enhancement-scenarios
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline build-hpp-comparison-layers
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline build-denovo-advanced-kg-viz
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline build-denovo-mega-flexible-kg-viz
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline build-downstream-feature-tables

Data enhancement layers
=======================

Layer 1: nutrients
------------------

Build two active HPP food_id-level nutrient strategies:

1. De novo:
   - Use HPP food list and available HPP nutrient data.
   - Harmonize public food composition database nutrient fields.
   - Map HPP foods to public-source food records.
   - Use deterministic text normalization, token similarity, category
     evidence, and source-specific match metadata.
   - Retain per-100 g values and nutrient provenance.

2. NutriMatch-based:
   - Read the NutriMatch HPP nutrient parquet.
   - Treat values as per-100 g HPP food nutrient values.
   - Preserve the NutriMatch nutrient schema as its own branch.

Retain a basic NutriMatch comparator for validation but do not treat it as the
complete multimodal branch because it lacks product, chemical, metabolite,
disease, pathway, and mapping-provenance layers.

Layer 2: product/processing
---------------------------

Map HPP/canonical helper foods to OpenFoodFacts. Extract compact evidence:

- OpenFoodFacts code.
- product name.
- match score and confidence.
- brand.
- country.
- ingredients text.
- ingredient count.
- additives count and tags.
- allergens.
- labels.
- Nutri-Score grade.
- NOVA group.
- PNNS groups.
- food groups.
- completeness.
- product-level nutrients such as energy, fat, saturated fat, carbohydrates,
  sugars, fiber, protein, salt, and sodium per 100 g.

Layer 3: food chemicals
-----------------------

Use FoodAtlas and FooDB:

- FoodAtlas: food-compound evidence and graph-derived food-chemical counts.
- FooDB: food-to-compound evidence, compound counts, chemical classes,
  chemical superclasses, and annotation quality summaries.

Generate HPP-level compact features by inheriting evidence through canonical
helper foods when needed.

Layer 4: human metabolomics biology
-----------------------------------

Use HMDB:

- Build an HMDB metabolite index.
- Link food-derived compounds to HMDB metabolites where identifiers allow.
- Extract metabolite count, biospecimen count, biospecimen labels, and related
  compact metabolomics evidence.

Layer 5: disease/pathway graph features
---------------------------------------

Use FoodAtlas and HMDB:

- FoodAtlas disease edge counts.
- FoodAtlas positive disease edge counts.
- FoodAtlas negative disease edge counts.
- HMDB disease count.
- HMDB pathway count.
- top HMDB diseases.
- top HMDB pathways.

Treat these as annotation and hypothesis-generation features, not causal
diet-disease estimates.

Layer 6: multimodal structured embeddings
-----------------------------------------

For each active branch, build HPP food-level structured embeddings from:

- numeric nutrient values;
- product/processing numeric fields;
- food chemical counts;
- HMDB/disease/pathway count features;
- deterministic hashed text-evidence features.

Use deterministic preprocessing:

- numeric blocks: convert to numeric, median-impute, log/standardize where
  appropriate, and concatenate by block;
- text block: stable hashed text features from ingredient text, chemical class
  labels, disease labels, pathway labels, product labels, and biospecimens.

Layer 7: deterministic food concept sentences and optional LLM embeddings
-------------------------------------------------------------------------

Create one deterministic sentence per HPP food. Sentence structure should be
stable and interpretable, for example:

Per 100 g reference for HPP food <food_id> (<food name>; Hebrew: <Hebrew name>)
in category <category>. It is represented by canonical helper <canonical name>.
Top nutrient evidence includes <nutrient amounts>. Product-processing evidence
includes <OpenFoodFacts product, NOVA, NutriScore, ingredients/additives>.
Food-chemical evidence includes <FoodAtlas/FooDB counts and top classes>. HMDB
links include <metabolite count>, biospecimens <biospecimens>, disease labels
<top diseases>, and pathway labels <top pathways>. These graph-derived links
are annotation features, not causal estimates.

Optional LLM sentence embeddings:

- prompt for OpenAI API key in terminal;
- do not save API key;
- write embeddings and projections only.

Output branches
===============

Write active branch outputs to:

outputs/enhanced_hpp/1.denovo/
outputs/enhanced_hpp/2.nutrimatch_based/

Each branch must contain:

hpp_nutrient_reference_per_100g.csv
hpp_feature_matrix_per_100g.csv
hpp_nutrient_provenance_long.csv.gz
feature_schema.csv
scenario_summary.json
hpp_layers_2_to_7_summary.json
layer_tables/
  layer2_product_processing_reference.csv
  layer3_food_chemical_reference.csv
  layer4_human_metabolomics_reference.csv
  layer5_disease_pathway_reference.csv
layer6_multimodal_embeddings/
  hpp_multimodal_vectors.parquet
  hpp_embedding_projection.csv
  hpp_multimodal_vector_dimensions.csv
layer7_sentences_patterns/
  hpp_food_concept_sentences.csv
  hpp_food_disease_pattern_discovery.csv
kg/
  hpp_scenario_kg_nodes.csv
  hpp_scenario_kg_edges.csv
  hpp_scenario_kg_summary.json

Expected approximate final sizes in the current snapshot:

- De novo: 7,405 HPP rows, 192 nutrient fields, feature matrix around
  7,405 x 246, structured embedding around 7,405 x 300, KG around 1.5M edges.
- NutriMatch-based: 7,405 HPP rows, 153 nutrient fields, feature matrix around
  7,405 x 207, structured embedding around 7,405 x 261, KG around 1.48M edges.

Exact dimensions may differ if source data versions differ, but row counts and
output schemas should be explainable.

Knowledge graph
===============

Build scenario-specific HPP KGs with nodes and edges as CSV.

Minimum node fields:

key
kind
id
label
unit_basis
hebrew_name
category
scenario

Minimum edge fields:

source
target
relation
scenario
mapping_mode
value
unit_basis
score
confidence

Required KG semantics:

- HPP food -> canonical helper food.
- HPP food -> nutrient with relation `has_nutrient_amount_per_100g` and numeric
  edge value.
- HPP/canonical helper -> OpenFoodFacts product evidence.
- HPP/canonical helper -> NOVA group.
- HPP/canonical helper -> NutriScore grade.
- HPP/canonical helper -> FooDB chemical class and superclass.
- HPP/canonical helper -> HMDB biospecimen.
- HPP/canonical helper -> HMDB disease annotation.
- HPP/canonical helper -> HMDB pathway annotation.

Use HPP food_id as final downstream key. Canonical helper IDs are internal
mapping/evidence-sharing aids.

KG visualization algorithm
==========================

Create these interactive HTML visualizations under `outputs/visualizations/`:

1. `denovo_hpp_kg_path_explorer.html`
2. `denovo_hpp_kg_full_flexible.html`
3. `denovo_hpp_kg_full_radial.html`
4. `denovo_hpp_kg_mega_flexible.html`

For shareable visualizations that use external data JavaScript, write the
matching `_data.js` file next to the HTML. The HTML should work by opening it
locally in a browser when the HTML and its `_data.js` file are in the same
folder.

Visual design:

- Canvas-based or SVG/HTML interactive visualization is acceptable.
- Use smaller nodes so the full KG is readable.
- Color nodes by type.
- Color edges by relation.
- Positive and negative disease correlations are edge types, not node types:
  use distinct edge colors/dashes for positive and negative FoodAtlas disease
  evidence.
- Provide a legend.
- Clicking a legend category hides/shows that node category.
- Hovering a node shows only concise information: node label/name and node type.

Path explorer behavior:

- Default view should show all edges for the selected/example subgraph.
- Clicking a node highlights the biologically relevant outgoing neighborhood
  and makes unrelated nodes/edges transparent/light.
- Include a degree selector from 1 to 4.
- Direction should follow:
  food -> nutrients
  food -> chemicals
  food -> metabolites
  nutrients/chemicals/metabolites -> diseases/pathways
- If nutrient-to-chemical or chemical-to-metabolite ancillary evidence exists,
  include those as ancillary edges with a distinct color.

Full flexible behavior:

- Show the full de novo HPP KG, with a force/floating layout.
- Same node types should tend to cluster near each other.
- Nodes keep type-specific colors.
- Edges may be hidden or light by default if needed for performance, but
  clicking/searching a node must show its local neighborhood.

Full radial behavior:

- Show a radial biological layout:
  HPP foods and canonical foods near the inside;
  product/processing and nutrients in intermediate rings;
  chemicals/metabolites outward;
  diseases/pathways near the outside.

Mega flexible behavior:

- Create `denovo_hpp_kg_mega_flexible.html`.
- Include all KG nodes plus available wider native chemical, pathway,
  metabolite, and disease nodes.
- Use the same click-neighborhood algorithm as the full flexible visualization.
- Local neighborhood highlighting must include disease/pathway edges when they
  are reachable through the same biological direction rules.
- Use an external data file:
  `denovo_hpp_kg_mega_flexible_data.js`.

Downstream task feature exports
===============================

Create a module that flattens the KG into task-specific HPP food-level feature
tables. The output is for TRE-side prediction tasks.

Command:

python -m diet_data_enhancement.pipeline build-downstream-feature-tables

Write:

outputs/downstream_features/denovo/<recipe>/
outputs/downstream_features/nutrimatch_based/<recipe>/

Recipes:

1. broad_diet_health
2. microbiome
3. mental_health
4. cardiometabolic
5. chemical_metabolomics

Each recipe folder must contain:

hpp_downstream_feature_table.csv
hpp_downstream_feature_list.csv
hpp_downstream_feature_summary.json

The table is one row per HPP food. Combine selected flat features from
`hpp_feature_matrix_per_100g.csv` with KG-derived neighborhood features.

KG feature naming convention:

kg__<edge_relation>__<target_node_type>__<target_label>

For nutrient amount edges, use the per-100 g edge value. For product,
processing, chemical class, HMDB biospecimen, disease, and pathway edges, use
binary/count neighborhood features unless a better numeric edge value exists.

The feature-list file must record:

scenario
recipe
feature_name
feature_source
model_role

Notebook requirements
=====================

Create a concise downstream-feature explorer notebook:

notebooks/enriched_hpp_data_explorer.ipynb

It should focus only on what is needed for paper understanding and TRE-side
NutriMatch-style prediction tasks:

- Load downstream recipe metadata.
- Compare de novo vs NutriMatch-based feature table sizes.
- Show feature provenance and feature families.
- Show branch-specific and shared features.
- Load one selected scenario/recipe table.
- Report missingness and numeric sparsity by feature family.
- Search and inspect one HPP food, such as coffee.
- Show top non-zero numeric features and text evidence fields for that food.
- Demonstrate TRE-side join/aggregation using a tiny fake diet log:
  join by food_id, scale per-100 g nutrient values by grams consumed, aggregate
  to participant-level predictors.
- Save a compact paper overview CSV:
  outputs/enhanced_hpp/downstream_recipe_overview_for_paper.csv

The notebook must not load real participant-level TRE data.

Human-in-the-loop mapping UI
============================

Create a local HITL review UI for weak/ambiguous mappings. It should:

- Review only weak or ambiguous matches.
- Auto-accept strong Layer 2 product matches.
- Show counts by review tier.
- Distinguish high-use diet-logging items from low-use items.
- Provide filters by tier and mapping score range.
- Allow assignment to an existing canonical food item.
- Include uniform buttons:
  accept layer 1
  accept layer 2
  accept both
  save and remap layer 1
  save and remap layer 2
  save and remap both
- Remap only the selected/changed item, not unrelated foods.
- Keep other food items unchanged.
- Support bilingual mapping for HPP to Tzameret: compare English-English and
  Hebrew-Hebrew/available Hebrew evidence, then retain whichever is more
  confident.

Validation and comparison
=========================

Implement NutriMatch comparison:

- Read NutriMatch parquet and README.
- Inspect and report its head/columns.
- Compare the current Layer 1 nutrient mapping against NutriMatch-based
  nutrient values where features overlap.
- Report shared nutrient value agreement, de novo-only nutrient fields, and
  NutriMatch-only nutrient fields.
- Keep the conclusion clear: current de novo Layer 1 and NutriMatch-based Layer
  1 are both nutrient mappings, but the de novo branch may include additional
  nutrient-like fields and full mapping/provenance logic.

TRE-side interpretation
=======================

In docs and notebooks, explain:

- Nutrients are per-100 g food-reference values.
- Diet event amount:
  event_amount = reference_per_100g * grams_consumed / 100
- Product, chemical, metabolite, disease, pathway, and KG features are
  annotation/exposure features unless explicitly measured as quantities.
- Participant-level features inside TRE should be created by joining the HPP
  food_id reference table to diet logs and aggregating over the intended time
  window.
- For paper comparison, run the same prediction task twice:
  once with de novo features and once with NutriMatch-based features, holding
  outcome definition, cross-validation, model family, and feature recipe fixed.

Implementation style
====================

- Use Python with pandas/numpy/sklearn where useful.
- Prefer CSV/parquet outputs that can be inspected without special software.
- Keep mapping and extraction functions modular.
- Write summaries as JSON and compact CSVs.
- Avoid destructive operations.
- Validate notebooks as JSON and ensure code cells parse.
- Keep output filenames stable.
- Do not hide scientific assumptions in code; write them into summary files or
  method comments.

Final acceptance checks
=======================

After implementation, confirm:

1. `python -m diet_data_enhancement.pipeline build-hpp-enhancement-scenarios`
   creates `outputs/enhanced_hpp/1.denovo` and
   `outputs/enhanced_hpp/2.nutrimatch_based`.
2. Each active branch has `hpp_feature_matrix_per_100g.csv`,
   `feature_schema.csv`, `layer_tables/`, `layer6_multimodal_embeddings/`,
   `layer7_sentences_patterns/`, and `kg/`.
3. De novo and NutriMatch-based branches have the same HPP food_id row universe.
4. KG node and edge CSVs exist for both active branches.
5. Interactive de novo KG visualizations exist and open locally.
6. Mega KG visualization includes its companion `_data.js` file.
7. Downstream feature recipe CSVs exist for both active scenarios and all five
   recipes.
8. The downstream explorer notebook loads the recipe tables and demonstrates
   the TRE-side join/aggregation pattern without real participant data.
9. Optional OpenAI embedding command prompts for an API key and does not save it.
10. The project can be reproduced from command-line pipeline commands.
```

