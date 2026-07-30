# CVD And Cardiometabolic Prediction

This task compares four diet-derived feature sets for predicting
cardiovascular and cardiometabolic blood biomarkers inside TRE:

1. `full_data`: full KG/downstream cardiometabolic feature export.
2. `enriched_data`: de novo enriched HPP per-100 g food features.
3. `nutrimatch_only`: NutriMatch-based per-100 g nutrient features.
4. `food_card_embedding`: amount-weighted food-card text embedding vectors.

## Approved Targets

The first version uses these numeric blood-test targets:

```text
bt__triglycerides_float_value
bt__total_cholesterol_float_value
bt__hdl_cholesterol_float_value
bt__ldl_cholesterol_float_value
bt__non_hdl_cholesterol_float_value
bt__glucose_float_value
bt__hba1c_float_value
bt__creatinine_float_value
bt__urate_float_value
bt__alt_float_value
bt__ast_float_value
bt__ggt_float_value
```

If a target is missing from the TRE table, the default behavior is to skip it
and report it in `missing_targets`. Set `strict_targets` to `true` in the config
if missing targets should stop the run.

## Run

Edit `example_config.json` or copy it to a TRE-local config file, then run:

```bash
python -m downstream_analysis.tasks.cvd.cvd_prediction \
  --config downstream_analysis/tasks/cvd/example_config.json \
  --project-root .
```

## Inputs

Diet events should follow the TRE diet logging shape:

```text
participant_id | food_id | weight_g | collection_timestamp
```

The CVD target table should be wide, with `participant_id`, optionally a date
or `time_window`, and the approved blood-test target columns.

Default feature references are:

```text
outputs/downstream_features/denovo/cardiometabolic/hpp_downstream_feature_table.csv
outputs/enhanced_hpp/1.denovo/hpp_feature_matrix_per_100g.csv
outputs/enhanced_hpp/2.nutrimatch_based/hpp_feature_matrix_per_100g.csv
outputs/food_card/denovo/embeddings/hpp_food_card_embeddings_full_biology_text_text_embedding_3_large.parquet
```

## Outputs

The task writes:

```text
cvd_targets_selected.parquet
feature_set_build_summaries.csv
cvd_feature_set_comparison.csv
cvd_prediction_run_summary.json
<feature_set>/X_<feature_set>_<window>.parquet
<feature_set>/predictions/<target>/*metrics.csv
```
