# Microbiome Prediction

This task compares three diet-derived feature sets for predicting microbiome
targets inside TRE:

1. `full_data`: full KG/downstream microbiome feature export.
2. `enriched_data`: de novo enriched HPP per-100 g food features.
3. `nutrimatch_only`: NutriMatch-based per-100 g nutrient features.
4. `food_card_embedding`: amount-weighted food-card text embedding vectors.

The microbiome legacy dictionary indicates that the main target families are
wide abundance tables from URS and MetaPhlAn. The runner therefore expects a
wide target table with `participant_id`, optionally `time_window`, and one or
more numeric abundance columns.

## Run

Edit `example_config.json` or copy it to a TRE-local config file, then run:

```bash
python -m downstream_analysis.tasks.microbiome_prediction.microbiome_prediction \
  --config downstream_analysis/tasks/microbiome_prediction/example_config.json \
  --project-root .
```

## Inputs

Diet events should follow the TRE diet logging shape:

```text
participant_id | food_id | weight_g | collection_timestamp
```

The code also accepts aliases such as `hpp_food_id`, `grams_consumed`, and
`timestamp`.

Default feature references are:

```text
outputs/downstream_features/denovo/microbiome/hpp_downstream_feature_table.csv
outputs/enhanced_hpp/1.denovo/hpp_feature_matrix_per_100g.csv
outputs/enhanced_hpp/2.nutrimatch_based/hpp_feature_matrix_per_100g.csv
outputs/food_card/denovo/embeddings/hpp_food_card_embeddings_full_biology_text_text_embedding_3_large.parquet
```

## Outputs

The task writes:

```text
microbiome_targets_selected.parquet
feature_set_build_summaries.csv
microbiome_feature_set_comparison.csv
microbiome_prediction_run_summary.json
<feature_set>/X_<feature_set>_<window>.parquet
<feature_set>/predictions/<target>/*metrics.csv
```
