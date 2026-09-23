# Hypothesis Discovery To Nature Communications Paper

## Purpose Of This Summary

This document captures the task-specific history, decisions, principles, analysis choices, and paper-story development for the HPP nitrate/oral microbiome work. It is written so that a future LLM agent can recreate the project from scratch, understand the user intent, avoid earlier mistakes, and generalize the process into a pipeline for future hypothesis-to-paper workflows.

The central project became:

**Agentic diet reconstruction reveals divergent oral nitrate-cycle ecologies linked to vegetable nitrate and processed nitrite in the Human Phenotype Project.**

The paper is intended as a Nature Communications-style observational cohort paper, with an agentic/human-in-the-loop discovery process as part of the scientific contribution.

## Initial User Goal

The user created a manual analysis folder under:

`downstream_analysis/manual`

The first instruction was to learn the process of creating data groups and preprocessing data with respect to a chemical or KG node, then use HPP and the full enhanced KG to think of interesting data-discovery stories. The user wanted examples of the form:

- people who consume more of food/chemical/metabolite X have more disease Y
- the effect may differ by sex or age
- the association may show up in oral microbiome, metabolomics, cholesterol, disease phenotype, or other HPP layers
- the finding should be interesting to an editor, not merely statistically significant

The first promising hypothesis chosen was **dietary nitrate and oral microbiome**.

## Why Dietary Nitrate And Oral Microbiome Were Chosen

The biological rationale was strong:

- Dietary nitrate enters the enterosalivary nitrate-nitrite-nitric oxide pathway.
- Nitrate is concentrated in saliva.
- Oral bacteria reduce nitrate to nitrite.
- This makes oral microbiome more mechanistically proximal than gut microbiome for nitrate biology.
- Intervention literature already shows nitrate-sensitive oral taxa, especially `Neisseria`, `Rothia`, `Prevotella`, and `Veillonella`.
- HPP contains oral microbiome data, diet logs, lifestyle/demographic covariates, and potentially downstream clinical phenotypes.

The original intended outcome was not "nitrate causes microbiome change" but rather:

> Can KG-enhanced diet reconstruction detect nitrate-cycle oral ecology signatures in a large free-living cohort, and can it separate vegetable nitrate from processed nitrite/nitroso/arginine-NO axes?

## Key Hypothesis Evolution

### Stage 1: Simple Nitrate Exposure

The first hypothesis was:

- high dietary nitrate versus low dietary nitrate
- outcome: oral microbiome diversity and nitrate-reducing taxa

Proposed oral microbiome outcomes:

- nitrate-reducing taxa if identifiable
- oral microbiome alpha diversity
- MetaPhlAn species/genus/family abundances
- HUMAnN pathway abundance/coverage

### Stage 2: Source-Specific Nitrate/Nitrite Axes

The story improved when nitrate was separated into chemically and source-aware axes:

- `overall_nitrate`
- `vegetable_nitrate`
- `overall_nitrite`
- `processed_nitrite`
- `nitroso_axis`
- `arginine_no_axis`

The scientific reason:

- vegetable nitrate is usually delivered through vegetables and the enterosalivary route
- processed nitrite is often direct nitrite in processed/cured food matrices
- nitroso-associated foods may represent nitrosation-related chemistry but should not be assumed to mediate processed nitrite
- arginine/citrulline/ornithine relate to NO metabolism by a different route

This shifted the paper from a simple nitrate story to:

> Chemically related dietary nitrogen axes map to divergent, sometimes opposite, oral microbial ecology states.

### Stage 3: Age/Sex Effect Modification

The user explored whether age or sex changed the diet-to-oral microbiome association.

Questions tested:

- Does the diet-microbiome association become stronger/weaker with age?
- Does it differ by sex?
- Are age/sex differences in diet aligned with age/sex differences in oral ecology?
- Could age or sex mediate a diet-microbiome signal?

The outcome:

- age and sex clearly structure diet and oral ecology
- interaction/moderation results were not strong enough to be the main paper story
- mediation-style results had to be treated cautiously and not as causal mediation
- age/sex should be kept as secondary context and covariate justification

### Stage 4: Processed Nitrite To Nitroso Mediation Check

The user asked whether processed nitrite might mediate through the nitroso axis.

The notebook added a processed nitrite -> nitroso axis -> oral ecology analysis.

Result:

- no FDR-supported indirect processed nitrite -> nitroso -> oral ecology signal
- main summary: zero indirect tests passed q < 0.05 or q < 0.10
- main-analysis minimum indirect q was approximately 0.728

Interpretation:

- do not claim nitroso mediates processed nitrite
- safer claim: processed nitrite and nitroso-associated diet are separable reconstructed dietary axes

### Stage 5: Reviewer Challenge And Overall Axes

The main reviewer challenge emerged:

> Is this really nitrate/nitrite biology, or just vegetable versus processed-meat diet quality?

To address this, the manuscript added `overall_nitrate` and `overall_nitrite` as broad axes. These help show that the signal is not only a vegetable-versus-meat contrast.

Interpretation:

- broad nitrate/nitrite axes contain weaker but directionally relevant oral ecology signal
- source-specific axes sharpen the ecology
- this supports "food-source nitrogen ecology" rather than pure chemical dose

## Main Results To Preserve

The final manuscript should emphasize these results.

### Vegetable Nitrate

Higher vegetable nitrate was associated with:

- higher nitrate-balance score
- higher `Neisseria`
- higher nitrate-positive score
- lower anaerobe score
- lower `Veillonella`
- lower `Prevotella`

Selected values from the exported main analysis:

| Axis | Feature | n | Standardized beta | FDR q | High-minus-low Cohen's d |
|---|---:|---:|---:|---:|---:|
| Vegetable nitrate | Nitrate-balance score | 5,691 | +0.068 | 5.4e-5 | +0.119 |
| Vegetable nitrate | Neisseria | 5,689 | +0.059 | 3.1e-4 | +0.152 |
| Vegetable nitrate | Nitrate-positive score | 5,691 | +0.046 | 0.0088 | +0.083 |
| Vegetable nitrate | Anaerobe score | 5,691 | -0.052 | 0.0024 | -0.080 |
| Vegetable nitrate | Veillonella | 5,689 | -0.044 | 0.0095 | -0.084 |
| Vegetable nitrate | Prevotella | 5,689 | -0.040 | 0.0188 | -0.042 |

### Processed Nitrite

Higher processed nitrite was associated with:

- higher anaerobe score
- higher `Prevotella`
- higher `Megasphaera`
- lower nitrate-balance score

Selected values:

| Axis | Feature | n | Standardized beta | FDR q | High-minus-low Cohen's d |
|---|---:|---:|---:|---:|---:|
| Processed nitrite | Anaerobe score | 5,691 | +0.049 | 0.0052 | +0.082 |
| Processed nitrite | Prevotella | 5,689 | +0.046 | 0.0088 | +0.106 |
| Processed nitrite | Megasphaera | 5,689 | +0.043 | 0.0117 | +0.091 |
| Processed nitrite | Nitrate-balance score | 5,691 | -0.041 | 0.0169 | -0.071 |

### Overall Nitrate And Overall Nitrite

These broad axes are important for reviewer defense.

Overall nitrate showed:

- higher `Burkholderiaceae`
- directionally higher `Neisseria`
- directionally higher nitrate-balance score
- directionally lower anaerobe score

Overall nitrite showed:

- higher `Burkholderiaceae`
- higher `Neisseria`
- directionally higher nitrate-balance score
- directionally lower anaerobe score

The broad axes are weaker and more heterogeneous than source-specific axes, but they help show that the KG chemical annotations have signal beyond a crude vegetable/meat split.

### Opposite-Axis Features

Most important paper plot:

- the same oral feature increases under one dietary nitrogen axis and decreases under another

Examples:

- nitrate-balance score: positive under vegetable nitrate, negative under processed nitrite
- `Neisseria`: positive under vegetable nitrate/overall nitrite, negative under arginine/NO axis
- anaerobe score: negative under vegetable nitrate, positive under processed nitrite
- `Prevotella`: negative under vegetable nitrate, positive under processed nitrite

This is the cleanest story:

> The result is not "more nitrogen equals more/less microbiome feature." Different reconstructed nitrogen axes map to different oral ecologies.

## Manuscript And Output Files

Primary manuscript draft:

`downstream_analysis/manual/nitrate/nature_microbiology_draft/NatureCommunications_NitrateOralEcology_manuscript.md`

Earlier Nature Microbiology-style draft:

`downstream_analysis/manual/nitrate/nature_microbiology_draft/NatureMicrobiology_NitrateOralEcology_manuscript.md`

Figure/table builder:

`downstream_analysis/manual/nitrate/build_nature_microbiology_package.py`

Generated figures:

- `figure_1_axis_heatmap.svg`
- `figure_2_opposite_axis_features.svg`
- `figure_3_same_feature_axis_bars.svg`
- `figure_3_representative_group_means.svg`
- `figure_4_demographic_oral_ecology.svg`

Generated manuscript tables:

- `table_1_exposure_reconstruction.csv`
- `table_2_selected_axis_ecology_results.csv`
- `table_3_opposite_axis_candidates.csv`
- `table_4_demographic_diet_results.csv`

Final TRE-side paper notebook:

`downstream_analysis/manual/nitrate/DietNitrateOralEcologyPaper.ipynb`

Downloaded TRE export:

`downstream_analysis/manual/nitrate/00002759.zip`

Unzipped de-identified export:

`downstream_analysis/manual/nitrate/00002759_unzipped/00002759/A_main_result_export_bundle.csv`

Secondary sensitivity export:

`downstream_analysis/manual/nitrate/00002759_unzipped/00002759/B_secondary_result_export_bundle.csv`

## Journal Storyline Decisions

Several possible papers were discussed:

1. Agentic AI/diet-data enhancement tool paper for Nature Methods or Nature Machine Intelligence.
2. Nitrate/nitrite/nitroso/arginine-NO oral ecology paper for Nature Communications or Nature Microbiology.
3. Dietary nitrate, age/sex and cardiovascular health paper for NEJM-style clinical framing.

Final focus for the current manuscript:

- Nature Communications-style article
- broad enough to include methods/background
- not only microbiology novelty, but cohort-scale agentic reconstruction and source-aware ecology

The user wanted the paper to retain a clinical/biological side rather than become only methodological. Therefore the manuscript should balance:

- agentic diet reconstruction
- HPP scale
- oral nitrate-cycle biology
- food-source nitrogen axes
- divergent oral ecology results

## Recommended Nat Com Article Pattern

Use this structure:

1. Title
2. Abstract, about 150-200 words
3. Introduction
   - oral nitrate cycle
   - prior nitrate intervention evidence
   - limitation of isolated exposure thinking
   - need for KG-enhanced diet reconstruction
   - HPP and agentic/human-in-loop setup
4. Results
   - agentic KG reconstruction defined nitrogen axes
   - broad nitrate/nitrite axes bridge chemistry and food source
   - vegetable nitrate aligned with nitrate-positive ecology
   - processed nitrite showed divergent ecology
   - same features moved in opposite directions across axes
   - nitroso axis did not mediate processed nitrite
   - age/sex are secondary cohort structure
5. Discussion
   - summarize core finding
   - explain why known nitrate biology still matters
   - explain what is new: scale, reconstruction, source disambiguation
   - address vegetable/meat diet-quality critique
   - limitations and next sensitivity analyses
6. Methods
   - cohort/TRE
   - agentic reconstruction
   - exposure scoring
   - oral microbiome preprocessing
   - statistical models
   - FDR
   - reporting conventions

## Writing Principles For Future Agents

Use observational wording:

- "associated with"
- "linked to"
- "aligned with"
- "mapped to"
- "separable dietary axes"
- "source-aware reconstruction"

Avoid causal wording unless intervention data are added:

- avoid "causes"
- avoid "drives"
- avoid "mediates" as a proven mechanism
- avoid "protective" or "harmful" unless using external clinical outcome validation

Best framing:

> Agentic KG-enhanced diet reconstruction separated chemically related, food-source-specific nitrogen axes. In a large HPP cohort, these axes were associated with divergent oral nitrate-cycle ecologies, with vegetable nitrate and processed nitrite showing opposite patterns for nitrate-balance, anaerobe score, Neisseria and Prevotella.

## Key Reviewer Risks

### Risk 1: This Is Just Vegetables Versus Processed Meat

Response:

- call the variables "food-source nitrogen axes"
- include overall nitrate and overall nitrite results
- show same features moving across multiple axes, not only vegetable and processed nitrite
- add source-matched sensitivity models before submission if possible:
  - vegetable nitrate adjusted for total vegetables/fibre
  - processed nitrite adjusted for processed meat, sodium, protein, saturated fat

### Risk 2: Exposure Variables Are Not Chemical Dose

Response:

- explicitly state that KG-derived exposure is not measured nitrate/nitrite dose
- use "reconstructed exposure" or "dietary axis"
- do not claim direct chemical measurement

### Risk 3: Observational And Cross-Sectional

Response:

- avoid causal language
- present as discovery and ecological association
- propose validation through intervention/source-matched designs

### Risk 4: Processed Nitrite Food Matching Could Have Token Artifacts

Response:

- use exact word-boundary matching in final TRE notebook
- export full food-list audit tables
- manually inspect processed/cured food list
- avoid substring matches such as `ham` inside unrelated food names

### Risk 5: Microbiome Is Compositional And Sparse

Response:

- keep main outcomes prespecified and interpretable
- use FDR within prespecified family
- add compositional sensitivity analysis if possible
- avoid overinterpreting single weak taxa

## What A Future Agent Should Do Next

1. Audit food lists in TRE for each exposure axis.
2. Patch source-token filters to use word boundaries.
3. Add diet-quality/source-matched sensitivity models.
4. Add a concise supplementary table for all foods contributing to each exposure axis.
5. Consider clinical phenotype extension:
   - blood pressure
   - vascular age
   - oral/dental health
   - inflammatory biomarkers
   - salivary nitrate/nitrite if available
6. Convert manuscript to a polished article draft or DOCX only after sensitivity analyses are finalized.

