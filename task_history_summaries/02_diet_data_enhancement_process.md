# Diet Data Enhancement Process For Reusable HPP Chemical-Exposure Analyses

## Purpose Of This Summary

This document explains how diet data enhancement and exposure reconstruction were done in the nitrate/oral microbiome project. It is written for a future LLM agent that needs to recreate this work from scratch or streamline the same process for another chemical, metabolite, food component, disease node, or KG-derived hypothesis.

The key idea is:

> Use the full enhanced food knowledge graph to connect biological concepts to HPP food nodes, convert those connected foods into participant-level dietary exposure axes from TRE diet logs, apply reliable-logger quality control, then test exposure associations with HPP outcomes using transparent, reproducible statistics.

## Inputs And Data Sources

### Repository Location

Project root:

`/Users/elchananmycheaux/Library/CloudStorage/OneDrive-Personal/Agens_Intelligens/Agent_Codex/Diet_Data_enhancement`

Manual analysis folder:

`downstream_analysis/manual`

Nitrate task folder:

`downstream_analysis/manual/nitrate`

### TRE Data Loading Rule

Inside TRE, HPP participant data must be loaded using `PhenoLoader`, not by hard-coded local CSV/parquet paths.

Correct pattern:

```python
from pheno_utils import PhenoLoader

pl = PhenoLoader("oral_microbiome", errors="warn")
oral_primary = pl.dfs["oral_microbiome"]
```

For diet events:

```python
pl = PhenoLoader("diet_logging", age_sex_dataset=None, errors="warn")
```

The notebook should then inspect `pl.dfs` and use either already-loaded diet event tables or path columns supplied by `PhenoLoader`.

Do not assume that `pyarrow`, `fastparquet`, `plotly`, or Excel writers are installed in TRE. Use pandas/matplotlib where available. For exports, prefer CSV bundles that can be parsed outside TRE.

## High-Level Workflow

1. Define a biological question in terms of chemicals, metabolites, pathways, food sources, or KG nodes.
2. Use the full enhanced KG to find foods connected to those concepts.
3. Apply source filters only when biologically justified.
4. Load diet logs through `PhenoLoader`.
5. Convert diet event rows into participant-level exposure summaries.
6. Identify and exclude sparse/irregular diet loggers.
7. Load HPP outcome data through `PhenoLoader`.
8. Preprocess outcomes into participant-level variables.
9. Merge exposure, outcome and covariates.
10. Run prespecified adjusted models and high/mid/low contrasts.
11. Apply FDR correction within clearly defined hypothesis families.
12. Export only de-identified summary tables from TRE.
13. Recreate final manuscript figures outside TRE.

## Exposure Reconstruction Principles

### Use The Full KG

The user explicitly wanted the full enhanced KG used, not a small hand-built dictionary. The workflow should traverse KG connections between:

- chemical terms
- metabolite names
- compound classes
- pathway nodes
- food nodes
- HPP canonical food identifiers

For nitrate, the final axes used:

| Exposure axis | Terms/source rule | Connected foods after filtering | Target node count |
|---|---:|---:|---:|
| `overall_nitrate` | nitrate, non-metal nitrates, sodium nitrate, potassium nitrate | 3,848 | 72 |
| `vegetable_nitrate` | nitrate, non-metal nitrates plus vegetable-source filter | 209 | 72 |
| `overall_nitrite` | nitrite, non-metal nitrites, sodium nitrite, potassium nitrite | 3,262 | 21 |
| `processed_nitrite` | nitrite, sodium nitrite, sodium nitrate, non-metal nitrites plus processed/cured-source filter | 57 | 23 |
| `nitroso_axis` | nitroso, nitrosamine, N-nitroso, nitroso compound | 2,780 | 61 |
| `arginine_no_axis` | arginine, citrulline, ornithine, arginine/proline metabolism, nitric oxide | 7,405 | 268 |

### Do Not Overclaim Chemical Precision

KG-derived food axes are not measured chemical doses. A future agent should describe them as:

- reconstructed dietary axes
- KG-connected foods
- food-source nitrogen axes
- source-aware dietary exposures

Avoid saying:

- exact nitrate dose
- exact nitrite dose
- causal nitrate effect
- pure nitrate/nitrite chemistry

### Source Filters

Source filters can be powerful but risky.

For vegetable nitrate, include foods whose names or categories suggest vegetable sources, such as:

- vegetable
- leafy
- spinach
- lettuce
- beet/beetroot
- arugula/rocket
- celery
- cabbage
- chard
- radish

For processed nitrite, include processed/cured food context, such as:

- smoked
- cured
- sausage
- bacon
- ham
- salami
- hot dog
- processed

Important: final production code should use word-boundary matching. Avoid substring artifacts such as matching `ham` inside unrelated food names.

## Diet Log Exposure Scoring

The core event-level fields needed are:

- participant identifier
- food identifier
- food name/canonical food id if available
- grams consumed
- date/time of logging

The nitrate paper used several exposure metrics but the primary one was:

```text
exposure_per_1000g_logged = absolute_exposure_g / total_logged_g * 1000
```

Why this was chosen:

- it reduces bias from people who simply log more total food
- it preserves true differences in food composition and amount consumed
- it avoids normalizing by number of eating episodes alone

Other useful metrics:

```text
absolute_exposure_g
exposure_g_per_logging_day
log1p_exposure_per_1000g_logged
log1p_exposure_g_per_logging_day
logged_g_per_day
food_events
logging_days
total_logged_g
```

Use `log1p` for continuous regression plots/models when exposure is zero-inflated:

```python
log1p_exposure_value = np.log1p(exposure_value.fillna(0))
```

Interpretation:

- `log1p` handles zero values safely
- many zeros are expected when a participant did not consume connected foods for a specific axis during logged days
- do not automatically drop zeros; zeros are meaningful non-consumption unless the participant has unreliable logging

## Diet Logging Quality Control

The user specifically did not want to normalize away real multiple-meal intake. Instead, the workflow should identify unreliable logging patterns and drop or flag them.

The final approach:

- build daily logging summaries per participant
- assess sparse or irregular logging
- retain reliable loggers in the main analysis
- keep logging metrics for transparency and optional sensitivity models

Useful daily logging features:

- number of logged days
- total logged grams
- median grams per logging day
- number of food events
- median events per day
- first and last log date
- observed span days
- maximum gap between logged days
- logging coverage
- coefficient of variation of daily grams

Flags used in the notebook:

- too few logged days
- low total grams
- low median daily grams
- high daily-gram variability
- large gap between logged days

Observed decision from this project:

- 7,630 participants were reliable
- 2,567 were sparse or irregular
- 2,551 were flagged for large gaps
- 17 were flagged for low daily grams
- sparse/irregular loggers were dropped from the primary analysis

The exact threshold values are printed in the notebook transparency section and cached under the TRE-side cache directory.

## Caching And Progress

The diet exposure construction cell can be slow because it:

- loads large diet event tables through `PhenoLoader`
- normalizes identifiers
- builds daily logging quality summaries
- traverses/extracts KG-connected food IDs for multiple exposure axes
- aggregates participant-level exposure tables

The notebook was modified to:

- print progress messages such as `[diet 1/7]`, `[diet 2/7]`, etc.
- cache diet events, logging quality tables, daily logging tables, exposure tables and build summaries
- avoid rerunning expensive steps unnecessarily

Recommended principle:

> Every long TRE cell should print progress and cache intermediate outputs, because users cannot easily inspect stalled operations.

## Oral Microbiome Outcome Preprocessing

For the nitrate project, oral microbiome was loaded with:

```python
from pheno_utils import PhenoLoader
pl = PhenoLoader("oral_microbiome", errors="warn")
oral_primary = pl.dfs["oral_microbiome"]
```

Confirmed available tables:

- primary `oral_microbiome`
- `age_sex`

The primary table has participant-level metadata and path columns to bulk files.

Confirmed bulk files loaded successfully in TRE:

- MetaPhlAn genus abundance parquet
- MetaPhlAn species abundance parquet
- MetaPhlAn family abundance parquet
- HUMAnN pathway abundance pathway-level arrow
- HUMAnN pathway coverage pathway-level arrow

Microbe-level HUMAnN paths often pointed to `s3://...` per-sample files and were skipped by default.

Metadata columns must be excluded before computing diversity:

- `participant_id`
- `cohort`
- `research_stage`
- `array_index`
- `collection_date`

Derived oral features included:

- Shannon diversity
- Simpson diversity
- richness
- total abundance
- nitrate-reducer taxon abundance
- nitrate-reducer presence
- nitrate-positive score
- anaerobe score
- nitrate-balance log ratio
- top variable taxa
- nitrogen pathway totals from HUMAnN pathway tables

Main taxa:

- `Neisseria`
- `Rothia`
- `Rothia dentocariosa`
- `Prevotella`
- `Veillonella`
- `Megasphaera`
- `Moraxellaceae`
- `Burkholderiaceae`
- `Actinomyces`
- `Haemophilus`
- `Kingella`

## Covariates And Confounders

The final main model used:

- age
- sex
- BMI
- current smoking status
- alcohol current frequency

The earlier/secondary model also included diet logging covariates:

- food events
- logging days
- total logged grams

The user later preferred not to include logging covariates in the main model because reliable-logger filtering already handled logging quality. Therefore:

- A main analysis: lean covariates, logging used for QC/transparency
- B secondary analysis: additional diet-logging covariates as sensitivity

When age is the tested variable, exclude age from covariates. When sex is the tested variable, exclude sex from covariates. This avoids adjusting away the variable being tested.

## Statistical Analysis Pattern

Use three complementary analysis styles.

### Continuous Exposure Models

Model:

```text
oral_outcome ~ log1p(exposure_per_1000g_logged) + covariates
```

Report:

- adjusted beta
- standardized beta
- standard error
- p value
- FDR q value
- n
- R2

### Low/Mid/High Exposure Groups

Create tertiles:

- low
- mid
- high

Use these for:

- reader-friendly summaries
- violin/box plots
- group means with 95% CI
- high-minus-low Cohen's d

Important convention:

```text
positive Cohen's d = higher outcome in high exposure than low exposure
negative Cohen's d = lower outcome in high exposure than low exposure
```

### Top/Bottom 10%

Use top 10% versus bottom 10% as a stronger-contrast sensitivity analysis. This is useful for plots but should not replace the continuous model as the primary statistic.

## Multiple Testing

Use FDR correction, but define the hypothesis family explicitly.

Main FDR family:

```text
main exposures x prespecified oral ecology outcomes
```

Demographic oral FDR family:

```text
age/sex x prespecified oral ecology outcomes
```

Processed nitrite/nitroso pathway FDR family:

```text
processed_nitrite -> nitroso_axis -> prespecified oral ecology outcomes
```

Supplementary species FDR family:

```text
main exposures x all species-level MetaPhlAn features
```

Do not mix small prespecified and large exploratory FDR families.

## TRE Export Strategy

Because TRE has package limitations and export limits:

- do not rely on `plotly`
- do not rely on `openpyxl`
- do not rely on zip writing if TRE filesystem does not support it
- export de-identified CSV summary tables
- when many CSVs are needed, bundle them into a single text/CSV bundle with table boundary markers

Final export bundle pattern:

```text
__TABLE_START__,table_name
csv header
csv rows
__TABLE_END__,table_name
```

This made it possible to export:

- `A_main_result_export_bundle.csv`
- `B_secondary_result_export_bundle.csv`

Outside TRE, parse the bundle into separate dataframes and regenerate publication figures.

Do not export participant IDs or participant-level rows. Export aggregate statistics, model summaries, and plotting summaries only.

## Visualization Principles

In TRE:

- use matplotlib only
- white background
- black axes/grid
- consistent colors:
  - low: blue
  - mid: orange
  - high: red
- show p and q values on plots
- use 95% CI when plotting group means
- include commented `fig.savefig(...)` lines for later use

Outside TRE:

- regenerate clean figures from exported summary tables
- prefer SVG for manuscript figures
- ensure labels do not overlap
- do not include participant IDs

Most important figure type for the nitrate paper:

```text
same oral feature across dietary nitrogen axes
```

Examples:

- `Neisseria`
- `Prevotella`
- nitrate-balance score
- anaerobe score

Each panel should show:

- adjusted standardized beta
- p value
- FDR q value
- high-minus-low Cohen's d

## Generalizable Agentic Pipeline

For future projects, the agent should follow this pipeline:

1. **Hypothesis scan**
   - inspect HPP dataset catalog
   - inspect KG for possible biological axes
   - propose hypotheses that are biologically plausible and editorially interesting

2. **Choose exposure**
   - define chemical/metabolite/pathway nodes
   - decide whether source filters are needed
   - distinguish broad axes from source-specific axes

3. **Choose outcome layer**
   - select HPP data modality closest to the mechanism
   - oral microbiome was chosen here because nitrate reduction happens in the mouth

4. **Build exposure table**
   - load diet through `PhenoLoader`
   - map KG-connected foods to diet events
   - calculate participant-level metrics
   - apply reliable logging filter
   - cache outputs

5. **Preprocess outcome**
   - load with `PhenoLoader`
   - inspect table paths and data dictionary
   - exclude metadata columns
   - construct biologically interpretable features

6. **Model**
   - define prespecified hypothesis family
   - run continuous adjusted models
   - run group contrasts
   - calculate effect sizes and FDR

7. **Iterate with human**
   - inspect surprising findings
   - check if story is known
   - refine axes, covariates and plots
   - explicitly handle reviewer objections

8. **Export**
   - export de-identified summary bundles
   - create external visualizer/manuscript figures

9. **Write**
   - choose journal-specific article shape
   - keep causal language out unless causal design exists
   - include limitations and next sensitivity analyses

## Reusable User Preferences Captured From This Task

- The user values ideas that can become interesting papers, not only valid analyses.
- The user wants LLM agents to be creative but scientifically careful.
- The user wants the agent to use the full KG, not a small hand list.
- The user wants modular notebooks with clear sections.
- The user wants confounders controlled but not overcorrected.
- The user prefers transparent p/q/effect-size reporting.
- The user wants publication-ready plots, but can export summary tables and polish plots outside TRE.
- The user wants agentic discovery and human-in-the-loop hypothesis refinement to be part of the eventual pipeline/story.
- The user strongly prefers not to export participant-level identifiers from TRE.

## Common Mistakes To Avoid

- Do not load HPP participant data by hard-coded file paths inside TRE when `PhenoLoader` is required.
- Do not use `plotly` inside TRE.
- Do not assume Excel export packages are available.
- Do not calculate diversity on metadata columns.
- Do not insert many dataframe columns one by one if it creates fragmentation warnings; concatenate columns at once.
- Do not drop zero exposures automatically; zero can mean true non-consumption.
- Do not include age as a covariate when testing age difference, or sex when testing sex difference.
- Do not call mediation causal unless temporal/causal assumptions are justified.
- Do not present source-specific axes as pure chemical dose.
- Do not ignore the vegetable-versus-processed-food reviewer critique.

