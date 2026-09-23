# Downstream Analysis TRE Scaffold

This folder contains task runners, a dashboard app, and shared utilities
intended to be copied or run inside TRE.
It does not require participant data outside TRE.

## Files

- `app.py`: launches a small local dashboard for running tasks and viewing
  comparison outputs.
- `utils/preprocess.py`: joins participant diet logs to HPP food-level feature tables,
  food-card embeddings, or KG-derived feature tables, then aggregates to
  participant/time-window design matrices.
- `utils/modeling.py`: aligns `X` and `Y`, runs five repeated 80/20 train-test splits,
  trains simple scikit-learn models, and reports classification or regression
  metrics.
- `phenobench_adapter/`: exports participant-level diet feature matrices as
  PhenoBench `participant_embedding` artifacts. This is the only folder here
  that depends on the PhenoBench-TRE handoff contract.
- `tasks/microbiome_prediction/`: task-specific workflow comparing full
  KG/downstream features, de novo enriched features, NutriMatch-only nutrient
  features, and food-card embedding features for microbiome targets.
- `tasks/cvd/`: task-specific workflow comparing the same four diet
  representations for cardiovascular and cardiometabolic blood biomarkers.

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
`hpp_food_id`, `grams_consumed`, and `timestamp`. This lets the same task
runners work against TRE diet logs while still joining to exported food-reference tables
whose food identifier is usually `hpp_food_id`.

## Feature Inputs

Examples generated outside TRE:

```text
outputs/enhanced_hpp/1.denovo/hpp_feature_matrix_per_100g.csv
outputs/downstream_features/denovo/broad_diet_health/hpp_downstream_feature_table.csv
outputs/food_card/denovo/embeddings/hpp_food_card_embeddings_full_biology_text_text_embedding_3_large.parquet
```

## Task Workflows

Dashboard:

```bash
python -m downstream_analysis.app --project-root .
```

Microbiome prediction:

```bash
python -m downstream_analysis.tasks.microbiome_prediction.microbiome_prediction \
  --config downstream_analysis/tasks/microbiome_prediction/example_config.json \
  --project-root .
```

CVD and cardiometabolic biomarker prediction:

```bash
python -m downstream_analysis.tasks.cvd.cvd_prediction \
  --config downstream_analysis/tasks/cvd/example_config.json \
  --project-root .
```

Phenobench adapter export:

```bash
python -m downstream_analysis.phenobench_adapter.phenobench_adapter build \
  --x-path downstream_analysis/test_outputs/cvd/full_data/X_full_data_30d.parquet \
  --output-dir outputs/phenobench_adapter/denovo_full_data \
  --feature-set-name denovo_full_data \
  --participant-policy mean \
  --adapter-mode artifact_only
```
