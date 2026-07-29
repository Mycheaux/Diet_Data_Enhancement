# Diet Data Enhancement

This project builds HPP `food_id`-level diet data enhancement outputs outside
the TRE using food/reference data only. The goal is to create per-100 g food
reference tables, knowledge graphs, and embedding-ready representations that can
later be joined to participant diet logs inside the TRE.

The current paper comparison has two active enhancement branches:

1. **De novo diet data enhancement**: HPP foods are enhanced using the local
   pipeline and public/reference databases.
2. **NutriMatch-based diet data enhancement**: HPP nutrient values come from
   the provided NutriMatch HPP nutrient panel, then the same non-nutrient
   enhancement layers are applied.

A third file-level comparator, **basic NutriMatch**, is retained for comparison
of the provided NutriMatch nutrient panel alone. It is not the main enriched
multimodal branch because the provided parquet does not include product,
chemical, metabolite, disease, pathway, or mapping-provenance layers.

For full implementation details, see [details.md](details.md). For the current
paper methods draft, see [docs/methods.md](docs/methods.md).

## Enhancement Layers

The first five layers are used for diet data enhancement:

1. **Layer 1: nutrients**: HPP/de novo or NutriMatch-based per-100 g nutrient
   values.
2. **Layer 2: product/processing**: OpenFoodFacts product, ingredient,
   additive, NOVA, label, brand, and product-nutrition evidence.
3. **Layer 3: food chemicals**: FoodAtlas graph chemistry plus FooDB
   compound/constituent summaries.
4. **Layer 4: human metabolomics biology**: HMDB biofluid metabolite index and
   FooDB/HMDB identifier bridge.
5. **Layer 5: disease/pathway graph features**: FoodAtlas disease edges plus
   compact HMDB disease/pathway summaries.

The result of these layers is:

- an HPP-level **diet data enhancement table**;
- HPP-level and canonical-helper **reference tables**;
- a scenario-specific **knowledge graph**.

Layers 6 and 7 then produce derived representations:

- **Layer 6**: structured multimodal food embeddings.
- **Layer 7**: deterministic food concept sentences, optional OpenAI sentence
  embeddings, and pattern-discovery summaries.
- **Food cards**: deterministic LLM-readable HPP food descriptions built from
  nutrients, product/processing evidence, KG chemistry, metabolomics,
  disease/pathway themes, and global concept categorization tables.

## Main Outputs

Active branch outputs are written to:

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
layer_tables/
layer6_multimodal_embeddings/
layer7_sentences_patterns/
kg/
```

The basic NutriMatch comparator outputs are written under:

```text
outputs/validation/nutrimatch_*
```

## Setup

Use the existing conda environment:

```bash
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline --help
```

If setting up a fresh environment:

```bash
conda create -n ds python=3.11 pandas openpyxl pyarrow plotly nbformat jupyter -y
conda run -n ds python -m pip install openai
```

## Reproduce Current Results

Run from the project root:

```bash
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline layered-all
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline chem-bio-all
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline build-reference
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline build-hpp-enhancement-scenarios
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline build-hpp-comparison-layers
```

Optional NutriMatch comparison:

```bash
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline compare-nutrimatch
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline compare-nutrimatch-mapping
```

Optional OpenAI sentence embeddings for both active branches:

```bash
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline build-hpp-llm-sentence-embeddings
```

This prompts for an OpenAI API key in the terminal and does not save it.

Optional food-card text exports for downstream embedding and prediction:

```bash
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline build-food-card-categorization
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline build-food-cards
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline build-food-card-embeddings
```

To embed only the de novo branch:

```bash
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline --scenario denovo build-food-card-embeddings
```

The first command builds global metabolite, chemical, pathway, and disease
categorization candidates plus deterministic seed groupings. The second command
uses those categorization tables, the HPP scenario tables, and the KG/reference
tables to write deterministic text cards for every HPP food. Outputs are:

```text
outputs/food_card/denovo/hpp_food_cards.csv
outputs/food_card/denovo/hpp_food_cards.jsonl
outputs/food_card/denovo/hpp_food_card_embedding_input.jsonl
outputs/food_card/nutrimatch_based/hpp_food_cards.csv
outputs/food_card/nutrimatch_based/hpp_food_cards.jsonl
outputs/food_card/nutrimatch_based/hpp_food_card_embedding_input.jsonl
outputs/food_card/hpp_food_cards_all_scenarios.csv
outputs/food_card/food_card_build_summary.json
```

The `full_biology_text` column is the main embedding-ready food-card sentence.
The shorter `nutrition_core_text` and `chemistry_metabolomics_text` columns are
included for ablation studies.

The embedding command prompts for an OpenAI API key in the terminal and does
not save it. It writes one embedding vector per HPP food to:

```text
outputs/food_card/denovo/embeddings/
outputs/food_card/nutrimatch_based/embeddings/
outputs/food_card/food_card_embedding_summary.json
```

Optional task-specific downstream feature exports:

```bash
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline build-downstream-feature-tables
```

This reads the scenario KGs and writes recipe-specific CSV feature tables under
`outputs/downstream_features/` for broad diet-health, microbiome,
mental-health, cardiometabolic, and chemical/metabolomics analyses.

## TRE Downstream Analysis Scaffold

TRE-side preprocessing and prediction notebooks are in:

```text
downstream_analysis/
```

The expected raw diet-event table has at least:

```text
participant_id | hpp_food_id | grams_consumed
```

and can optionally include a timestamp column. The notebooks support:

- enriched per-100 g food features;
- food-card embedding vectors;
- KG/downstream feature exports.

Use:

```text
downstream_analysis/preprocess.ipynb
downstream_analysis/supervised_prediction.ipynb
```

Most logic is kept in `downstream_analysis/preprocess.py` and
`downstream_analysis/modeling.py` so future TRE notebooks can reuse the same
alignment, aggregation, cross-validation, and metric code.

## Current Branch Sizes

| Branch | HPP rows | Nutrients | Feature matrix | Structured embedding | KG edges |
|---|---:|---:|---:|---:|---:|
| De novo | 7,405 | 192 | 7,405 x 246 | 7,405 x 300 | 1,511,243 |
| NutriMatch based | 7,405 | 153 | 7,405 x 207 | 7,405 x 261 | 1,480,390 |

Nutrient values are treated as per-100 g food-reference values. Inside the TRE,
diet-event features should be assembled as:

```text
event_amount = reference_per_100g * grams_consumed / 100
```
