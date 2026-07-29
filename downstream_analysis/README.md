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

## Expected TRE Diet Log Shape

At minimum:

```text
participant_id | hpp_food_id | grams_consumed
```

Optional:

```text
timestamp
```

If `timestamp` is available, outputs can be made per day, week, month, year, or
overall participant.

## Feature Inputs

Examples generated outside TRE:

```text
outputs/enhanced_hpp/1.denovo/hpp_feature_matrix_per_100g.csv
outputs/downstream_features/denovo/broad_diet_health/hpp_downstream_feature_table.csv
outputs/food_card/denovo/embeddings/hpp_food_card_embeddings_full_biology_text_text_embedding_3_large.parquet
```

