# Oral Microbiome Preprocessing Notes For Nitrate Analysis

This note documents the HPP oral microbiome data structure observed in TRE and how the nitrate oral microbiome notebook preprocesses it.

## Data Source

The oral microbiome data are loaded with:

```python
from pheno_utils import PhenoLoader
pl = PhenoLoader("oral_microbiome", errors="warn")
oral_primary = pl.dfs["oral_microbiome"]
```

In TRE, `PhenoLoader("oral_microbiome")` exposes two tables: `oral_microbiome` and `age_sex`. The primary `oral_microbiome` table contains participant-level metadata and path columns pointing to aggregated MetaPhlAn and HUMAnN bulk files.

Observed primary table:

- `oral_primary` shape: approximately `8816 x 41`
- dataset directory: `/home/ec2-user/studies/hpp_datasets/oral_microbiome`
- path columns include MetaPhlAn abundance parquet files and HUMAnN aggregated pathway arrow files

## Confirmed Bulk Tables

The following local aggregate files were confirmed to load successfully in TRE:

| Prefix | Path Column | File Type | Observed Shape | Use |
|---|---|---:|---:|---|
| `oral_metaphlan_genus` | `metaphlan_abundance_genus_parquet` | parquet | `8834 x 282` raw, `8834 x 279` normalized | genus abundances, alpha diversity, nitrate-reducer genera |
| `oral_metaphlan_species` | `metaphlan_abundance_species_parquet` | parquet | `8834 x 742` raw, `8834 x 728` normalized | species abundances, alpha diversity, nitrate-reducer species |
| `oral_metaphlan_family` | `metaphlan_abundance_family_parquet` | parquet | `8834 x 130` raw, `8834 x 128` normalized | family abundances and family-level nitrate-reducer proxies |
| `oral_humann_pathway_abundance_pathway_level` | `humann_aggregated_pathway_abundance_pathway_level_arrow` | arrow | `8838 x 492` raw, `8838 x 490` normalized | HUMAnN pathway abundance, nitrogen pathway totals |
| `oral_humann_pathway_coverage_pathway_level` | `humann_aggregated_pathway_coverage_pathway_level_arrow` | arrow | `8838 x 492` raw, `8838 x 490` normalized | HUMAnN pathway coverage, nitrogen pathway totals |

Some HUMAnN microbe-level path columns were present, but the observed values pointed to `s3://...` per-sample paths rather than local aggregate files. Those are skipped by default in the notebook to avoid slow or failing reads.

## Metadata Exclusion

The bulk tables include metadata columns such as:

- `participant_id`
- `cohort`
- `research_stage`
- `array_index`
- `collection_date`

These must be excluded before computing alpha diversity or top-variable features. Including `collection_date` as a numeric value can create nonsensical total abundance and Shannon diversity values. The updated notebook excludes these metadata columns before numeric feature construction.

## Derived Features

For MetaPhlAn genus/species/family tables, the notebook derives:

- Shannon diversity
- Simpson diversity
- richness, defined as number of non-zero features
- total abundance
- nitrate-reducer taxon abundance and presence for:
  - `Actinomyces`
  - `Haemophilus`
  - `Kingella`
  - `Neisseria`
  - `Prevotella`
  - `Rothia`
  - `Veillonella`
- total nitrate-reducer abundance
- any nitrate-reducer presence
- top variable taxa, prioritizing nitrate-reducer taxa when present

For HUMAnN pathway-level abundance and coverage tables, the notebook derives:

- pathway columns matching nitrate, nitrite, nitric oxide, denitrification, nitrogen, and common nitrogen metabolism gene/pathway tokens
- nitrogen pathway total abundance or coverage
- any nitrogen pathway presence
- count of matched nitrogen pathway columns
- top variable pathway features

## Relevance To Nitrate Hypothesis

Dietary nitrate is biologically interesting because the enterosalivary nitrate cycle depends strongly on oral bacteria. Nitrate is concentrated in saliva, then oral nitrate-reducing microbes convert nitrate to nitrite, which can contribute to nitric oxide biology and vascular/metabolic phenotypes.

The most relevant oral microbiome features for the nitrate story are therefore:

- nitrate-reducer genera and species, especially `Neisseria`, `Rothia`, `Veillonella`, `Actinomyces`, `Haemophilus`, `Prevotella`, and `Kingella`
- alpha diversity metrics, as broad ecological markers
- HUMAnN nitrogen/nitrate/nitrite pathway abundance and coverage
- top variable taxa/pathways as discovery features

The notebook uses these features as outcomes against KG-derived dietary nitrate/nitrite exposure groups and continuous exposure values.
