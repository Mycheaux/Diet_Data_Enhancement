# HPP-Level Enhancement Scenarios

This document defines the HPP-level enrichment scenarios for the paper.
The final analysis unit is the original HPP `food_id`; `canonical_food_id` is
retained as a helper layer for sharing evidence and reducing repeated mapping
work.

The active comparison is now:

```text
1.denovo vs 2.nutrimatch_based
```

The hybrid scenario is retained as an optional design branch, but because it is
currently identical to de novo for all available values, it is not the main
comparison branch.

For next-generation design notes on true dose-valued chemical features,
pathway exposure scores, independent de novo nutrient testing, and a stronger
LLM adjudication layer, see [GEN2_PLAN_NOTES.md](GEN2_PLAN_NOTES.md).

## Scientific Goal

The goal is to enrich HPP diet records so that each logged food can be expanded
into a per-100 g multimodal reference profile. Inside the TRE, these HPP-level
food-reference profiles can be joined to participant diet events and multiplied
by consumed amount:

```text
event_amount = reference_per_100g * weight_g / 100
```

The resulting person-level diet matrices can support prediction of microbiome
profiles, mental health factors, disease risk, metabolic markers, and other HPP
phenotypes. The same enriched food references also support food knowledge graph
construction, hypothesis discovery, and patient-level diet embeddings.

## Scenario 1: De Novo

Folder:

```text
outputs/enhanced_hpp/1.denovo/
```

This scenario uses the local de novo HPP enhancement pipeline. For every HPP
`food_id` and nutrient, observed HPP values are used first. If an observed HPP
nutrient is missing, the de novo public-database mapping layer can fill the
value from mapped FCDB sources.

Current result:

| Metric | Value |
|---|---:|
| HPP food rows | `7,405` |
| Canonical helper foods | `842` |
| Nutrient columns | `192` |
| Feature matrix shape | `7,405 x 246` |
| Nutrient non-null cells | `1,163,818` |
| Nutrient non-null percentage | `81.858%` |
| Median non-null nutrients per HPP food | `153` |
| HPP observed nutrient values | `1,132,965` |
| De novo public-mapped nutrient values | `30,853` |

## Scenario 2: NutriMatch Based

Folder:

```text
outputs/enhanced_hpp/2.nutrimatch_based/
```

This scenario uses the NutriMatch-derived HPP nutrient stratum as the nutrient
layer. The provided NutriMatch parquet is a wide nutrient table indexed by
`(dataset, food_name)` and contains an `HPP` stratum with `7,405` rows and
`153` nutrient columns. The file does not expose the original donor-food mapping
table, confidence scores, or row-level imputation provenance.

Current result:

| Metric | Value |
|---|---:|
| HPP food rows | `7,405` |
| Canonical helper foods | `842` |
| Nutrient columns | `153` |
| Feature matrix shape | `7,405 x 207` |
| Nutrient non-null cells | `1,132,965` |
| Nutrient non-null percentage | `100.000%` |
| Median non-null nutrients per HPP food | `153` |
| NutriMatch HPP panel nutrient values | `1,132,965` |

## Scenario 3: NutriMatch Enhanced Hybrid

Folder:

```text
outputs/enhanced_hpp/3.nutrimatch_enhanced/
```

This scenario uses de novo nutrient values first and fills remaining missing
values from the NutriMatch HPP panel when a matching nutrient exists. This is
the practical hybrid track for later versions where de novo coverage may be
restricted by confidence, HITL status, or source availability.

Current result:

| Metric | Value |
|---|---:|
| HPP food rows | `7,405` |
| Canonical helper foods | `842` |
| Nutrient columns | `192` |
| Feature matrix shape | `7,405 x 246` |
| Nutrient non-null cells | `1,163,818` |
| Nutrient non-null percentage | `81.858%` |
| Median non-null nutrients per HPP food | `153` |
| De novo primary nutrient values | `1,163,818` |
| NutriMatch fill values | `0` |

The current hybrid has zero NutriMatch-filled cells because the de novo HPP
source already contains complete values for the 153 NutriMatch nutrient fields,
and the extra 39 de novo nutrient-like columns are not present in the
NutriMatch file. This is an important paper caveat: the hybrid design is useful
and reproducible, but in the current local snapshot it does not add new cells
over de novo unless we later apply confidence-based masking or obtain a richer
NutriMatch provenance/mapping table.

## Active Layer 2-7 Branches

Layer 2 onward is now generated for the two active paper branches:

```text
outputs/enhanced_hpp/1.denovo/
outputs/enhanced_hpp/2.nutrimatch_based/
```

Both branches keep HPP `food_id` as the row unit. Nutrient values are
scenario-specific and per 100 g; Layer 2-5 annotations are currently inherited
from canonical-helper mappings unless future HPP-specific overrides are added.

### Layer 2: Product/Processing

Files:

```text
layer_tables/layer2_product_processing_reference.csv
```

Current shape in both branches: `7,405 x 37`.

This table contains OpenFoodFacts-derived product, ingredient, additive, NOVA,
Nutri-Score, brand, country, label, product-group, and product-nutrition
features inherited from the canonical helper match.

### Layer 3: Food Chemicals

Files:

```text
layer_tables/layer3_food_chemical_reference.csv
```

Current shape in both branches: `7,405 x 17`.

This table contains FoodAtlas/FooDB chemical annotation summaries, including
food/compound counts, top chemical classes and superclasses, and annotation
quality summaries inherited through the canonical helper.

### Layer 4: Human Metabolomics Biology

Files:

```text
layer_tables/layer4_human_metabolomics_reference.csv
```

Current shape in both branches: `7,405 x 14`.

This table contains HMDB-linked metabolite counts, biospecimen counts,
biospecimen labels, and related metabolite-link summaries inherited through the
FooDB/HMDB bridge.

### Layer 5: Disease/Pathway Graph Features

Files:

```text
layer_tables/layer5_disease_pathway_reference.csv
```

Current shape in both branches: `7,405 x 18`.

This table contains compact HMDB disease/pathway counts and top labels plus
FoodAtlas disease-edge summaries. These are graph annotation features and should
not be interpreted as causal diet-disease estimates.

### Layer 6: HPP-Level Multimodal Embeddings

Files:

```text
layer6_multimodal_embeddings/hpp_multimodal_vectors.parquet
layer6_multimodal_embeddings/hpp_embedding_projection.csv
layer6_multimodal_embeddings/hpp_multimodal_vector_dimensions.csv
```

Current de novo vector output: `7,405 x 300`.

Current NutriMatch-based vector output: `7,405 x 261`.

The difference comes from the nutrient block: de novo has 192 nutrient
dimensions, while NutriMatch-based has 153. Product/processing, chemical,
metabolomics/disease/pathway, and hashed text-evidence blocks are otherwise
constructed with the same logic.

### Layer 7: HPP-Level Food Concept Sentences And Pattern Discovery

Files:

```text
layer7_sentences_patterns/hpp_food_concept_sentences.csv
layer7_sentences_patterns/hpp_food_disease_pattern_discovery.csv
```

Each HPP food receives an interpretable sentence describing its scenario,
canonical helper, per-100 g nutrient evidence, product/processing evidence,
food-chemical links, HMDB metabolite evidence, and disease/pathway annotation
neighborhood. Cluster-level disease/pathway summaries are produced from the
HPP-level embedding projection.

The sentence template is deterministic. In simplified form:

```text
Per 100 g reference for HPP food <food_id> (<food name>; Hebrew: <Hebrew name>)
in category <category>, using the <scenario> nutrient scenario. The food is
linked to canonical helper <canonical_food_id> (<canonical_name>). Per 100 g, it
contains <nutrient amount examples>. Product/processing evidence maps to
OpenFoodFacts product <product>. Food chemical evidence links the helper food to
<FooDB compound count> FooDB compounds and <FoodAtlas compound count> FoodAtlas
compound nodes. Prominent chemical classes include <classes>. HMDB bridging
links this food concept to <metabolite count> human metabolites observed in
<biospecimens>. The disease/pathway graph includes <disease count> disease
annotations and <pathway count> pathway annotations, including diseases such as
<disease examples> and pathways such as <pathway examples>. Chemical,
metabolite, disease, and pathway links are reference graph annotations for
hypothesis generation, not causal estimates or measured post-ingestion amounts.
```

### Optional LLM Sentence Embeddings

Files after running the API step:

```text
layer7_llm_sentence_embeddings/hpp_food_sentence_embeddings.parquet
layer7_llm_sentence_embeddings/hpp_food_sentence_embedding_projection.csv
layer7_llm_sentence_embeddings/hpp_food_sentence_embedding_summary.json
```

These are OpenAI embedding vectors of the deterministic concept sentences. The
API key is requested interactively in the terminal and is not saved.

## HPP-Level Scenario Knowledge Graphs

Files:

```text
kg/hpp_scenario_kg_nodes.csv
kg/hpp_scenario_kg_edges.csv
kg/hpp_scenario_kg_summary.json
```

Current KG sizes:

| Scenario | Nodes | Edges | Nutrient amount edges |
|---|---:|---:|---:|
| De novo | `9,246` | `1,511,243` | `1,163,818` |
| NutriMatch based | `9,207` | `1,480,390` | `1,132,965` |

Nutrient edges are scenario-specific:

```text
HPP food_id -> nutrient -> value per 100 g
```

Layer 2-5 evidence is attached to each HPP food through inherited canonical
helper annotations:

```text
HPP food_id -> canonical_food_id -> product, chemical, HMDB, disease, pathway
```

The edge field `mapping_mode` records whether an edge is scenario-specific or
canonical-inherited.

## Shared Non-Nutrient Enrichment

All three scenarios keep HPP `food_id` as the exported row identifier. Current
non-nutrient features are inherited through the canonical helper layer:

```text
HPP food_id -> canonical_food_id -> product/processing, FoodAtlas, FooDB, HMDB,
disease/pathway, KG, and embedding evidence
```

This design keeps the downstream analysis unit HPP-specific while still
allowing repeated HPP foods to share curated evidence. Future HPP-specific HITL
overrides can replace inherited evidence without changing the exported table
contract.

## Output Files In Each Scenario

Each scenario folder contains:

```text
hpp_nutrient_reference_per_100g.csv
hpp_feature_matrix_per_100g.csv
hpp_nutrient_provenance_long.csv.gz
feature_schema.csv
scenario_summary.json
README.md
```

The nutrient-only table is intended for direct nutrient-intake assembly. The
full feature matrix adds inherited product, chemical, metabolomics,
disease/pathway, and KG features. The schema table marks which features are
per-100 g scalable and how they should be transformed for diet events.

## Reproducibility

Run:

```bash
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline build-hpp-enhancement-scenarios
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline build-hpp-comparison-layers
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline build-hpp-llm-sentence-embeddings
```

The combined summary is written to:

```text
outputs/enhanced_hpp/hpp_enhancement_scenarios_summary.json
outputs/enhanced_hpp/scenario_comparison_summary.csv
outputs/enhanced_hpp/denovo_vs_nutrimatch_layer2_to_7_summary.json
outputs/enhanced_hpp/denovo_vs_nutrimatch_llm_sentence_embedding_summary.json
```

## Evaluation Plan

Outside the TRE, evaluation should focus on food-reference coverage,
traceability, mapping agreement, and graph/feature completeness. Inside the TRE,
the same three scenarios can be joined to participant diet logs and compared by
downstream predictive performance:

1. Nutrient-only patient features.
2. Nutrient plus product/processing features.
3. Nutrient plus chemical/metabolite/pathway graph features.
4. Patient-level diet embeddings aggregated from all consumed HPP foods.

The NutriMatch paper evaluates enrichment by expanding nutrient coverage and
testing downstream prediction. We will use the same broad logic, while extending
the enriched representation beyond nutrients into KG and multimodal food
features.
