# Downstream Analysis TRE Scaffold

This folder contains code and notebooks intended to be copied or run inside TRE.
It does not require participant data outside TRE.

## Files

- `preprocess.py`: joins participant diet logs to HPP food-level feature tables,
  food-card embeddings, or KG-derived feature tables, then aggregates to
  participant/time-window design matrices.
- `modeling.py`: aligns `X` and `Y`, runs five repeated 80/20 train-test splits,
  trains simple scikit-learn models, and reports classification or regression
  metrics.
- `preprocess.ipynb`: notebook wrapper for preprocessing.
- `supervised_prediction.ipynb`: notebook wrapper for prediction.
- `tasks/microbiome_prediction/`: task-specific workflow comparing full
  KG/downstream features, de novo enriched features, NutriMatch-only nutrient
  features, and food-card embedding features for microbiome targets.

## Expected TRE Diet Log Shape

The legacy HPP/TRE diet logging dictionary uses:

```text
participant_id | food_id | weight_g
```

Optional:

```text
collection_timestamp | local_timestamp | collection_date
```

The preprocessing code also accepts the older local aliases
`hpp_food_id`, `grams_consumed`, and `timestamp`. This lets the same notebooks
run against TRE diet logs while still joining to exported food-reference tables
whose food identifier is usually `hpp_food_id`.

## Feature Inputs

Examples generated outside TRE:

```text
outputs/enhanced_hpp/1.denovo/hpp_feature_matrix_per_100g.csv
outputs/downstream_features/denovo/broad_diet_health/hpp_downstream_feature_table.csv
outputs/food_card/denovo/embeddings/hpp_food_card_embeddings_full_biology_text_text_embedding_3_large.parquet
```

## Task Workflows

Microbiome prediction:

```bash
python -m downstream_analysis.tasks.microbiome_prediction.microbiome_prediction \
  --config downstream_analysis/tasks/microbiome_prediction/example_config.json \
  --project-root .
```
