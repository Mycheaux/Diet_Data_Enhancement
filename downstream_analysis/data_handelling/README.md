# TRE Data Handling

This folder prepares local input tables for downstream prediction tasks using
`pheno_utils.PhenoLoader`.

Run these commands inside TRE, where `pheno_utils` and the HPP datasets are
available.

## CVD Inputs

```bash
python -m downstream_analysis.data_handelling.pheno_loader_export prepare-task-inputs \
  --tasks cvd \
  --output-dir tre_inputs
```

Creates:

```text
tre_inputs/diet_logging_events.parquet
tre_inputs/blood_tests.parquet
tre_inputs/tre_inputs_manifest.json
```

Then run:

```bash
python -m downstream_analysis.tasks.cvd.cvd_prediction \
  --config downstream_analysis/tasks/cvd/example_config.json \
  --project-root .
```

## Microbiome Inputs

```bash
python -m downstream_analysis.data_handelling.pheno_loader_export prepare-task-inputs \
  --tasks microbiome \
  --output-dir tre_inputs \
  --max-microbiome-targets 500
```

Creates:

```text
tre_inputs/diet_logging_events.parquet
tre_inputs/microbiome_targets.parquet
tre_inputs/tre_inputs_manifest.json
```

The loader tries common gut microbiome abundance tables first. To force one:

```bash
python -m downstream_analysis.data_handelling.pheno_loader_export prepare-task-inputs \
  --tasks microbiome \
  --output-dir tre_inputs \
  --microbiome-table metaphlan_abundance_species_parquet
```

## Oral Microbiome Inputs For Nitrate Analyses

For the dietary nitrate/nitrite side-paper analysis, prepare oral microbiome
features separately:

```bash
python -m downstream_analysis.data_handelling.oral_microbiome_preprocess \
  --output-dir tre_inputs/oral_microbiome
```

This creates, when the corresponding HPP bulk tables are available:

```text
tre_inputs/oral_microbiome/oral_metaphlan_genus_abundance.parquet
tre_inputs/oral_microbiome/oral_metaphlan_species_abundance.parquet
tre_inputs/oral_microbiome/oral_genus_alpha_diversity.parquet
tre_inputs/oral_microbiome/oral_species_alpha_diversity.parquet
tre_inputs/oral_microbiome/oral_genus_nitrate_reducer_features.parquet
tre_inputs/oral_microbiome/oral_species_nitrate_reducer_features.parquet
tre_inputs/oral_microbiome/oral_humann_pathway_abundance.parquet
tre_inputs/oral_microbiome/oral_humann_pathway_coverage.parquet
tre_inputs/oral_microbiome/oral_humann_pathway_abundance_nitrogen_pathway_candidates.parquet
tre_inputs/oral_microbiome/oral_humann_pathway_coverage_nitrogen_pathway_candidates.parquet
tre_inputs/oral_microbiome/oral_microbiome_nitrate_summary_features.parquet
tre_inputs/oral_microbiome/oral_microbiome_preprocess_manifest.json
```

The nitrate-reducer feature files aggregate candidate oral nitrate-reducing
genera such as `Actinomyces`, `Haemophilus`, `Kingella`, `Neisseria`,
`Prevotella`, `Rothia`, and `Veillonella`. These are intended as screening
features; inspect the exact MetaPhlAn labels and matched feature counts inside
TRE before treating them as final biology.

## Dataset Inspection

Use this before adding a new task or modality:

```bash
python -m downstream_analysis.data_handelling.pheno_loader_export inspect-dataset diet_logging
python -m downstream_analysis.data_handelling.pheno_loader_export inspect-dataset blood_tests
python -m downstream_analysis.data_handelling.pheno_loader_export inspect-dataset gut_microbiome
python -m downstream_analysis.data_handelling.pheno_loader_export inspect-dataset oral_microbiome
```

The inspection output lists tables already loaded in `pl.dfs` and bulk/time
series fields found in `pl.dict`.

## Design

The downstream prediction code still reads local parquet files. This folder is
the thin TRE-specific bridge from HPP `PhenoLoader` datasets to those files, so
the modeling code does not need to know how each HPP modality is physically
stored.
