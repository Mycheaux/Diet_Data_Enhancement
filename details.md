# Diet Data Enhancement: Details

This document is the detailed technical guide for the HPP diet data enhancement
project. The short overview and main reproduction commands are in
[README.md](README.md). The paper-facing methods draft is in
[docs/methods.md](docs/methods.md).

## Project Scope

The project develops outside-TRE food-reference tooling. It uses HPP food-item
reference data and public food, product, chemical, metabolite, disease, and
pathway databases. It does not require participant-level diet logs outside the
TRE.

The final exported unit is the original HPP `food_id`. Canonical food concepts
remain as helper nodes for reducing repeated mapping and sharing evidence across
near-duplicate foods.

## Active Paper Branches

The current active comparison is:

```text
1.denovo
2.nutrimatch_based
```

The hybrid folder `3.nutrimatch_enhanced` is retained for design completeness,
but it is currently identical to de novo for available values because the HPP
table already contains all 153 NutriMatch nutrient fields.

## Implemented Components

Implemented pipeline components include:

1. Source loaders for HPP and public food-composition databases.
2. Deterministic food-name normalization and similarity scoring.
3. Canonical helper food concept generation.
4. Layer 1 nutrient candidates from public FCDB sources.
5. Layer 2 OpenFoodFacts product/processing candidates.
6. HITL review queue and layered review UI.
7. FoodAtlas extraction and graph feature construction.
8. FooDB food-to-compound mapping and compact chemical features.
9. HMDB biofluid metabolite index and FooDB/HMDB bridge.
10. Disease/pathway summaries from FoodAtlas and HMDB.
11. Canonical and HPP-level reference matrices.
12. HPP-level de novo and NutriMatch-based enhancement branches.
13. Scenario-specific HPP-level KGs.
14. Structured multimodal embeddings.
15. Deterministic HPP food concept sentences.
16. Optional OpenAI sentence embeddings with terminal API-key prompt.

## Repository Layout

```text
Diet_Data_enhancement/
  data/                         Local source datasets
  diet_data_enhancement/        Python package
    sources.py                  Dataset loaders
    text.py                     Text normalization and similarity scoring
    mapping.py                  Legacy HPP-level public FCDB matching
    nutrients.py                Nutrient harmonization and imputation
    canonical.py                Canonical helper food concepts
    layered.py                  Layer 1/2 canonical mapping and HITL queue
    chem_bio_layers.py          FooDB, HMDB, FoodAtlas disease/pathway layers
    hpp_scenarios.py            HPP-level scenario outputs, KGs, embeddings
    final_kg.py                 Canonical/full KG builder
    kg_visualization.py         KG visualizations
    multimodal.py               Canonical-level embeddings/sentences
    nutrimatch_comparison.py    NutriMatch comparator and inferred mapping
    pipeline.py                 Command dispatcher
    ui/                         HITL web UI
  docs/
    methods.md                  Current paper methods draft
    HPP_ENHANCEMENT_SCENARIOS.md
    METHODS_REPRODUCIBILITY.md
    results.md
  outputs/                      Generated outputs
  README.md                     Short overview
  details.md                    This detailed guide
```

## Input Data

Expected local files include:

```text
data/HPP/hpp_food_items_with_nutrients.csv
data/Nutrimatch/imputed_nutrients_table.parquet
data/USDA_SR_Legacy/FoodData_Central_sr_legacy_food_csv_2018-04.zip
data/USDA_FNDDS/FoodData_Central_survey_food_csv_2024-10-31.zip
data/Tzameret_Israel/moh_mitzrachim.csv
data/AUSNUT_Australia/AUSNUT-2023-Food-details-4.xlsx
data/Bahrain FCT/Bahrain_Food_Composition_Table_pdf_extracted.xlsx
data/MEXT_Japan/1385123_Table18.xlsx
data/OpenFoodFacts/en.openfoodfacts.org.products.csv
data/FoodAtlas/foodatlas-v4.5.zip
data/FooDB/foodb_2020_04_07_json/
data/HMDB/
```

## Source Roles

| Source | Role |
|---|---|
| HPP food-item table | Target HPP food universe and observed nutrients |
| NutriMatch parquet | Basic comparator and NutriMatch-based nutrient branch |
| USDA SR Legacy | Generic nutrient reference |
| USDA FNDDS | Survey/as-consumed nutrient reference |
| Tzameret | Israeli/Hebrew/local food and nutrient reference |
| AUSNUT | Australian survey food reference |
| Bahrain FCT | Gulf/Middle Eastern food-composition reference |
| MEXT Japan | Japanese food names, composition, and preparation metadata |
| OpenFoodFacts | Product, processing, ingredient, additive, label evidence |
| FoodAtlas | Food-chemical-disease graph evidence |
| FooDB | Food constituents and chemical identifiers |
| HMDB | Human metabolites, biospecimens, diseases, pathways |

## Main Commands

Run the current full enhancement workflow:

```bash
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline layered-all
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline chem-bio-all
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline build-reference
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline build-hpp-enhancement-scenarios
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline build-hpp-comparison-layers
```

Run optional comparator commands:

```bash
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline compare-nutrimatch
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline compare-nutrimatch-mapping
```

Run optional OpenAI sentence embeddings:

```bash
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline build-hpp-llm-sentence-embeddings
```

The OpenAI command prompts for the API key and does not save it.

## HPP-Level Scenario Outputs

Active branch folders:

```text
outputs/enhanced_hpp/1.denovo/
outputs/enhanced_hpp/2.nutrimatch_based/
```

Each branch contains:

```text
hpp_nutrient_reference_per_100g.csv
hpp_feature_matrix_per_100g.csv
hpp_nutrient_provenance_long.csv.gz
feature_schema.csv
scenario_summary.json
hpp_layers_2_to_7_summary.json
layer_tables/
layer6_multimodal_embeddings/
layer7_sentences_patterns/
kg/
```

Layer table outputs:

```text
layer_tables/layer2_product_processing_reference.csv
layer_tables/layer3_food_chemical_reference.csv
layer_tables/layer4_human_metabolomics_reference.csv
layer_tables/layer5_disease_pathway_reference.csv
```

Embedding outputs:

```text
layer6_multimodal_embeddings/hpp_multimodal_vectors.parquet
layer6_multimodal_embeddings/hpp_embedding_projection.csv
layer6_multimodal_embeddings/hpp_multimodal_vector_dimensions.csv
```

Sentence and pattern outputs:

```text
layer7_sentences_patterns/hpp_food_concept_sentences.csv
layer7_sentences_patterns/hpp_food_disease_pattern_discovery.csv
```

KG outputs:

```text
kg/hpp_scenario_kg_nodes.csv
kg/hpp_scenario_kg_edges.csv
kg/hpp_scenario_kg_summary.json
```

Optional OpenAI sentence embedding outputs:

```text
layer7_llm_sentence_embeddings/hpp_food_sentence_embeddings.parquet
layer7_llm_sentence_embeddings/hpp_food_sentence_embedding_projection.csv
layer7_llm_sentence_embeddings/hpp_food_sentence_embedding_summary.json
```

## Downstream Task Feature Exports

The scenario knowledge graphs can be flattened into task-specific HPP food
feature tables. This is useful when a downstream analysis does not need the
entire multimodal feature space, or when a paper analysis needs an explicit
feature inclusion list for a particular outcome family.

Run:

```bash
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline build-downstream-feature-tables
```

The command builds exports for both active branches:

```text
outputs/downstream_features/denovo/
outputs/downstream_features/nutrimatch_based/
```

Available recipe folders:

```text
broad_diet_health/
microbiome/
mental_health/
cardiometabolic/
chemical_metabolomics/
```

Each recipe folder contains:

```text
hpp_downstream_feature_table.csv
hpp_downstream_feature_list.csv
hpp_downstream_feature_summary.json
```

The feature table is indexed at HPP `food_id` level. It combines selected
columns from `hpp_feature_matrix_per_100g.csv` with KG-derived neighborhood
features. KG features are named with the pattern:

```text
kg__<edge_relation>__<target_node_type>__<target_label>
```

For nutrient amount edges, the KG-derived value is the per-100 g nutrient
amount. For product, NOVA, NutriScore, chemical class, HMDB biospecimen,
disease, and pathway edges, the value is a binary/count neighborhood feature.

The feature-list file records whether each column came from HPP identifiers,
the scenario feature matrix, or the scenario knowledge graph. This lets a
downstream task report exactly which feature families were used without
manually inspecting the table.

## Current Branch Sizes

| Branch | HPP rows | Nutrients | Full matrix | Structured embedding | KG nodes | KG edges |
|---|---:|---:|---:|---:|---:|---:|
| De novo | 7,405 | 192 | 7,405 x 246 | 7,405 x 300 | 9,246 | 1,511,243 |
| NutriMatch based | 7,405 | 153 | 7,405 x 207 | 7,405 x 261 | 9,207 | 1,480,390 |

## Feature Interpretation

Nutrient features are per-100 g food-reference values. Inside the TRE:

```text
event_amount = reference_per_100g * weight_g / 100
```

Product, chemical, metabolite, disease, and pathway features are currently
annotation features. They can be represented as event-level indicators,
patient-level aggregate counts, graph-neighborhood summaries, or embedding
features. They should not be interpreted as measured post-ingestion metabolite
amounts or causal diet-disease estimates.

## Knowledge Graph Interpretation

The HPP scenario KG stores nutrient amount edges directly from HPP foods:

```text
HPP food_id -> nutrient -> value per 100 g
```

Layer 2-5 evidence is inherited through canonical helper nodes:

```text
HPP food_id -> canonical_food_id -> product, chemical, HMDB, disease, pathway
```

The `mapping_mode` field records whether an edge is scenario-specific,
canonical-helper inherited, or another evidence type.

## NutriMatch Comparator

The provided NutriMatch parquet is a wide nutrient table indexed by
`(dataset, food_name)` with four strata:

```text
SR_Legacy
FNDDS
Zameret
HPP
```

It contains `25,446` rows and `153` nutrient columns. The HPP stratum contains
`7,405` rows. The provided file does not include the original NutriMatch
food-to-food mapping table, donor-food IDs, confidence scores, or imputation
provenance.

Current comparison findings:

- The NutriMatch HPP panel and the local HPP nutrient table match exactly for
  all `153` shared nutrient fields.
- De novo has `39` additional nutrient-like fields not present in NutriMatch.
- Inferred donor mapping comparison is possible, but it is not equivalent to
  comparing against the original NutriMatch mapping table.

## HITL UI

The layered HITL UI is available for Layer 1/2 review:

```bash
tools/run_layered_hitl.sh
```

or:

```bash
conda run --no-capture-output -n ds python -m diet_data_enhancement.ui.layered_server
```

Open:

```text
http://127.0.0.1:8766
```

The UI supports role-specific decisions such as accepting Layer 1, accepting
Layer 2, accepting both, saving notes, remapping a layer with extra text, and
assigning weak items to an existing canonical food.

## Related Documents

```text
README.md
docs/methods.md
docs/HPP_ENHANCEMENT_SCENARIOS.md
docs/METHODS_REPRODUCIBILITY.md
docs/results.md
```
