# Methods

## Study Overview

We developed a modular framework to enrich food items from the Human Phenotype
Project (HPP) dietary database with nutrient, product-processing,
food-chemical, human-metabolomic, disease/pathway, knowledge-graph, and
embedding-derived features. The primary unit of enhancement was the original HPP
food identifier, so that the resulting reference data can be joined directly to
participant-level diet records inside the trusted research environment. All
development described here used food-reference data only and did not require
participant-level dietary or phenotype records.

The goal of the framework was to transform each HPP food into a per-100 g
multimodal reference profile. During downstream analysis, diet-event features
can be scaled by reported consumed amount, so that a food eaten in different
quantities contributes proportionally to nutrient exposure and other
dose-scalable features.

## Enhancement Strategies

We evaluated two active HPP-level diet data enhancement strategies. In the
first, referred to as the **de novo enhancement strategy**, HPP foods were
processed through the local mapping and enrichment pipeline. The nutrient layer
used observed HPP nutrient values when available and added mapped public-source
values where the local pipeline provided additional nutrient evidence.

In the second, referred to as the **NutriMatch-based enhancement strategy**, the
nutrient layer was derived from the HPP stratum of a NutriMatch-derived nutrient
panel. The same downstream non-nutrient enrichment layers were then applied.
This created a direct comparison between a locally generated nutrient-enhanced
branch and a NutriMatch-based nutrient branch while holding the product,
chemical, metabolomic, disease/pathway, and graph-enrichment logic constant.

We also retained the provided NutriMatch nutrient panel as a basic comparator.
This comparator was used to assess nutrient-panel agreement and to explore
inferred donor-food discrepancies, but it was not considered a complete
multimodal enhancement strategy because the provided file did not include
product-processing, food-chemical, HMDB, disease/pathway, or original
mapping-provenance layers.

## Food Identity And Canonical Helper Concepts

The final analysis unit was the HPP food identifier. However, repeated or
near-duplicate HPP food entries were also grouped into canonical helper food
concepts using normalized food names and food-category information. These helper
concepts were used to reduce repeated mapping work and to share non-nutrient
evidence across closely related HPP foods.

This design preserved HPP-level outputs while allowing product, chemical,
metabolomic, and disease/pathway annotations to be inherited through a stable
helper layer when HPP-specific evidence was not available. Thus, downstream
participant-level analyses can remain anchored to the original HPP food
identifier, while the enrichment process can still exploit shared food-concept
evidence.

## Layered Food Enhancement

The enhancement framework was organized into five primary data-enrichment
layers.

**Layer 1: Nutrients.** The nutrient layer represented per-100 g food-reference
composition. The de novo strategy used HPP nutrient values and additional
mapped public-source values, whereas the NutriMatch-based strategy used the HPP
stratum of the NutriMatch-derived nutrient panel. In the current data snapshot,
the two strategies agreed exactly for the shared NutriMatch nutrient fields,
while the de novo branch retained additional nutrient-like fields not present in
the NutriMatch panel.

**Layer 2: Product and processing evidence.** Product-level enrichment was
obtained from OpenFoodFacts. This layer added evidence related to branded food
identity, product names, ingredient text, additive annotations, allergens,
labels, Nutri-Score, NOVA processing group, product categories, and available
product-level nutrient fields. This layer was intended to distinguish generic
foods from packaged or processed products and to support later analyses of food
processing and ingredient exposure.

**Layer 3: Food chemicals.** Food-chemical enrichment was derived from FoodAtlas
and FooDB. This layer linked foods to food constituents, chemical classes,
chemical superclasses, and graph-derived food-chemical evidence. Compact summary
features were generated for predictive modelling, while the knowledge graph
retained higher-dimensional food-chemical connectivity for hypothesis
generation.

**Layer 4: Human metabolomics biology.** Food-chemical evidence was bridged to
human metabolomics using HMDB and shared chemical identifiers. This layer added
human-metabolite annotations, biofluid context, and metabolite-link evidence,
allowing food-derived chemical features to be connected to metabolites observed
in human biological matrices.

**Layer 5: Disease and pathway graph features.** Disease and pathway
annotations were derived from FoodAtlas and HMDB. These annotations summarized
disease labels, pathway labels, and graph neighborhoods linked to food
chemicals and human metabolites. These features were treated as
hypothesis-generating graph annotations rather than causal estimates of
diet-disease effects.

## Enhanced Reference Outputs

The first five layers produced three main classes of reference outputs. First,
we generated HPP-level diet data enhancement tables containing per-100 g
nutrients and compact product, chemical, metabolomic, disease, and pathway
features. Second, we generated reference tables separating nutrient,
product-processing, food-chemical, human-metabolomic, and disease/pathway
feature groups. Third, we generated scenario-specific knowledge graphs linking
HPP foods to nutrients, canonical helper foods, product-processing evidence,
chemical annotations, HMDB metabolites, disease labels, and pathway labels.

Nutrient amount edges in the knowledge graph were scenario-specific, reflecting
the difference between the de novo and NutriMatch-based nutrient branches.
Non-nutrient graph evidence was inherited through the canonical helper layer
unless a future HPP-specific override is supplied.

## Multimodal Food Embeddings

After constructing the enhanced reference profiles, we generated structured
multimodal embeddings for each HPP food. These embeddings combined numeric
nutrient values, product-processing features, food-chemical summaries,
metabolomics and disease/pathway summaries, and hashed text-evidence features.
Numeric features were transformed and standardized before block-wise
concatenation so that no single feature family dominated only because it
contained more columns. Textual evidence, including ingredient strings,
chemical-class labels, disease labels, and pathway labels, was represented using
a deterministic hashed text block.

The resulting embeddings provide a dense representation of each food's
nutritional, product, chemical, biological, and graph context. These food-level
embeddings can later be aggregated across all foods consumed by a participant to
create patient-level diet embeddings for predictive modelling.

## Food Concept Sentences And Sentence Embeddings

For each HPP food, we also generated a deterministic food concept sentence. The
sentence described the food identity, nutrient amounts per 100 g, product and
processing evidence, food-chemical annotations, HMDB-linked metabolites,
biofluid context, and disease/pathway graph annotations. This provided an
interpretable textual representation of the same multimodal evidence encoded in
the structured tables and knowledge graph.

Optional large-language-model sentence embeddings can be generated from these
deterministic sentences. These embeddings provide an alternative semantic
representation of enriched foods and can be compared with structured embeddings
for clustering, retrieval, and downstream prediction.

## Downstream TRE Analysis

The enhanced HPP-level food references are intended for use inside the TRE by
joining participant diet records to HPP food identifiers. Nutrient and other
dose-scalable values can be multiplied by consumed grams divided by 100.
Product, chemical, metabolite, disease, and pathway annotations can be encoded
as event-level indicators, graph-neighborhood features, or participant-level
aggregated exposure summaries.

These enriched diet representations are designed to support prediction of
microbiome composition, microbiome diversity, mental health factors, disease
risk, metabolic markers, and other HPP phenotypes. In parallel, the knowledge
graph can be used for hypothesis discovery by tracing food-to-chemical,
chemical-to-metabolite, and metabolite-to-disease/pathway neighborhoods.
