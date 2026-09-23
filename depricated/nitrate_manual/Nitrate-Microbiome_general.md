# Nitrate-Microbiome General Paper Concept

## Working Title

Knowledge-Graph Enhanced Dietary Nitrate Phenotyping Reveals Distinct Oral Microbiome Ecologies In A Population Cohort

## Abstract

Dietary nitrate has been proposed as an oral microbiome prebiotic because oral bacteria are required for the conversion of nitrate to nitrite, a key step in the enterosalivary nitrate-nitrite-nitric oxide pathway. However, most existing evidence comes from short-term nitrate or beetroot supplementation studies, and less is known about whether habitual nitrate-related dietary patterns in free-living populations are associated with oral microbiome structure and function. We used a knowledge-graph-enhanced diet exposure framework to distinguish vegetable nitrate, processed nitrite, nitroso-related, and arginine/nitric-oxide-related dietary axes in HPP participants with diet logging and oral microbiome data. Oral metagenomic features were derived from MetaPhlAn genus, species, and family abundance tables and HUMAnN pathway abundance and coverage tables, including alpha diversity, nitrate-reducer taxa, nitrogen pathway features, and top variable taxa/pathways.

Preliminary analyses suggest that higher vegetable nitrate exposure is associated with a lower-diversity oral microbiome characterized by increased Neisseria-related features and depletion of Prevotella/Prevotellaceae, Veillonella, Megasphaera, Moraxellaceae, and other anaerobic/dysbiosis-associated taxa. In contrast, processed nitrite-related exposure appears to show a distinct pattern, including increased Prevotella and Shannon diversity and decreased Rothia dentocariosa. Nitroso and arginine/nitric-oxide axes partially overlap with vegetable nitrate patterns but show distinct feature-level signatures. These results suggest that nitrogen-related dietary exposures do not act uniformly on the oral microbiome; instead, food source and dietary context may determine whether nitrate/nitrite-related chemistry aligns with a potentially beneficial nitrate-cycle oral ecology or with a different, processed-food-associated microbial state.

This work extends nitrate supplementation literature by showing that a similar nitrate-responsive oral ecology may be detectable in habitual diet patterns at population scale. The central hypothesis is that vegetable nitrate is associated with a more specialized oral nitrate-cycle ecology, while processed nitrite and nitroso-related exposures define distinct oral microbial signatures. This distinction may help explain why nitrate-rich vegetables and processed nitrite-containing foods have different health implications despite sharing nitrogen-related chemistry.

## Main Findings So Far

- Vegetable nitrate appears associated with:
  - lower Shannon diversity
  - higher Neisseria-related features
  - lower Prevotella / Prevotellaceae
  - lower Veillonella
  - lower Megasphaera
  - lower Moraxellaceae

- Processed nitrite appears associated with:
  - higher Prevotella
  - higher Shannon diversity
  - lower Rothia dentocariosa

- Nitroso axis appears associated with:
  - higher Rothia dentocariosa
  - lower Veillonella
  - lower Prevotellaceae

- Arginine / nitric oxide axis appears associated with:
  - higher Neisseriaceae / GGB6675
  - lower Prevotella

- Age appears to modify the association between nitrate/NO-axis exposures and Prevotella:
  - older participants show stronger Prevotella depletion with higher vegetable nitrate, nitroso axis, and arginine/NO-axis exposure.

## Why This Is Nature-Like

- It is not simply another nitrate supplementation study.
- It uses real-world habitual diet rather than short-term beetroot intervention.
- It separates vegetable nitrate from processed nitrite and nitroso-related food axes.
- It combines:
  - diet knowledge graph
  - oral metagenomics
  - taxonomic features
  - functional HUMAnN pathways
  - effect modification by age/sex
- It suggests a broader principle:
  - the food matrix determines whether nitrogen-related diet chemistry maps to a beneficial oral nitrate-cycle ecology.

## Core Biological Interpretation

Vegetable nitrate may not increase all nitrate-reducing bacteria. Instead, it may select for a more specific nitrate-cycle-compatible ecology:

- more Neisseria / Rothia-like taxa
- less Prevotella / Veillonella-like anaerobic taxa
- lower overall diversity due to ecological specialization

This aligns with intervention literature showing nitrate supplementation often increases Neisseria and Rothia while decreasing Prevotella and Veillonella.

## Next Analyses

- Build and test an oral nitrate-balance score:
  - `log1p(Neisseria + Rothia) - log1p(Prevotella + Veillonella + Megasphaera)`

- Compare this balance across:
  - vegetable nitrate
  - processed nitrite
  - nitroso axis
  - arginine/NO axis

- Test robustness after adjustment for:
  - age
  - sex
  - BMI
  - smoking
  - alcohol
  - diet quality / processed-food proxies if available

- Add systemic phenotype follow-up:
  - blood pressure
  - glucose / HbA1c
  - lipids
  - inflammation markers
  - oral/dental health proxies

## Key Caveats

- This is observational and should not be framed causally without stronger design.
- Processed nitrite may capture processed-food dietary pattern rather than nitrite chemistry alone.
- GGB taxa are less interpretable than named genera/species.
- Oral microbiome table timing relative to diet and clinical phenotypes needs careful alignment.

