# Diet Data Enhancement: Reproducible Methods And Paper Methods Draft

This document describes the current outside-TRE food data enhancement workflow in
a form suitable for reproducibility and for drafting the Methods section of a
paper. The workflow operates only on food/reference data. It does not use
participant-level diet records and is therefore designed to be developed,
audited, and validated outside the TRE before any TRE-side deployment.

## Step List

1. Assemble HPP food-item input data.
2. Assemble public food-composition database reference sources.
3. Normalize food names and source metadata.
4. Create low-effort deterministic mappings from HPP foods to public FCDBs.
5. Create a review queue for weak or ambiguous mappings.
6. Capture human-in-the-loop corrections through the local UI.
7. Re-map human-corrected foods against public FCDBs and FoodAtlas.
8. Collapse repeated HPP food IDs into canonical food concepts.
9. Map canonical food concepts to public FCDBs.
10. Optionally run OpenAI embedding retrieval and GPT validation.
11. Harmonize and impute nutrient profiles at the canonical food level.
12. Extract OpenFoodFacts product/processing features.
13. Extract FoodAtlas and FooDB food-chemical features.
14. Parse HMDB biospecimen-specific metabolite files.
15. Create FoodAtlas/HMDB disease and pathway graph features.
16. Build the final modular food knowledge graph.
17. Create visualization and internal-validation outputs.
18. Create multimodal food embeddings and food concept sentences.
19. Package reviewed outputs for later TRE-side feature construction.

## Method Overview

We developed a staged food data enhancement pipeline to convert a heterogeneous
food-item list into a canonical, traceable, nutrient-enriched knowledge graph.
The pipeline begins with HPP food items and maps them to external food
composition databases using deterministic text matching. Low-confidence or
ambiguous matches are flagged for human review. Human corrections are saved as
auditable records and are re-used for remapping. Repeated HPP food IDs with the
same short food concept are collapsed into canonical food concepts to reduce
duplicated mapping and review work while preserving original HPP IDs for
traceability. Nutrient data are harmonized across HPP and public food-composition
sources, and canonical food nutrient profiles are imputed using a transparent
provenance rule. Finally, FoodAtlas entities and relationships are integrated to
add food, chemical, and disease/medical-condition nodes and edges to a modular
knowledge graph.

## Reproducible Implementation Details

This section records the operational choices used in the current local run so
that the analysis can be reproduced exactly and described transparently in an
academic Methods section.

### Identifiers And Node Keys

Original HPP foods were never collapsed destructively. The original HPP
identifier was retained as `hpp_food_id` and used to create KG nodes with the
key format:

```text
hpp_food:<hpp_food_id>
```

Canonical food concepts were created from the normalized HPP short food name plus
the normalized HPP category. The canonical identifier format was:

```text
canonical:<normalized_food_name>:<normalized_category>
```

For example, repeated coffee entries in the HPP table map to the same canonical
concept:

```text
canonical:coffee:drinks
```

External database nodes used source-specific identifiers rather than labels, so
that duplicate names from different sources did not merge incorrectly:

| Node class | ID used | KG key format |
|---|---|---|
| HPP food | HPP `food_id` | `hpp_food:<hpp_food_id>` |
| Canonical food | normalized name + category | `canonical_food:<canonical_food_id>` |
| Public FCDB food | source name + source food ID | `source_food:<source>:<source_food_id>` |
| FoodAtlas entity | FoodAtlas `foodatlas_id` | `foodatlas_<entity_type>:<foodatlas_id>` |
| FooDB food | FooDB numeric food ID | `foodb_food:<foodb_food_id>` |
| FooDB compound | FooDB public ID when present, otherwise numeric compound ID | `foodb_compound:<foodb_compound_id>` |
| HMDB metabolite | HMDB accession | `hmdb_metabolite:<hmdb_id>` |
| HMDB biospecimen | biospecimen label | `hmdb_biospecimen:<biospecimen>` |
| Nutrient | nutrient name | `nutrient:<nutrient_name>` |
| Human correction | reviewed HPP food ID | `human_correction:<hpp_food_id>` |

The final KG builder de-duplicated nodes by these keys and de-duplicated edges by
the tuple `(source, target, relation)`. If the same node or edge was observed
again, attributes were updated rather than creating a duplicate graph element.

### Text Normalization And Matching Score

Food names were normalized using Unicode NFKD decomposition, ASCII conversion,
lowercasing, punctuation removal, and whitespace compaction. The deterministic
name score combined three components:

```text
match_score =
  0.55 * character_trigram_cosine
+ 0.35 * token_jaccard
+ 0.10 * containment_score
```

Exact normalized string equality was assigned a score of `1.0`. The containment
score was nonzero only when one normalized food name was contained in the other,
and was calculated as the ratio of shorter to longer normalized string length.

The English/token matching used ASCII-normalized text. For the Tzameret/Hebrew
case, the bilingual mapper also computed a Unicode-preserving Hebrew score when
both HPP and source Hebrew names were available. The final score was the maximum
of the English and Hebrew scores, and `match_language` records whether the
selected score came from English, Hebrew, or neither.

Candidate search used an inverted token index. For each query food, only source
records sharing query tokens were scored, up to a maximum candidate pool of
`500` records. If no token overlap existed, the first `500` source records were
used as a fallback candidate pool. The top `5` candidates were retained per food
by default.

Confidence tiers were assigned using fixed thresholds:

| Tier | Match-score rule | Interpretation |
|---|---:|---|
| `high` | `score >= 0.86` | strong lexical match |
| `medium` | `0.72 <= score < 0.86` | acceptable automated candidate |
| `low` | `0.58 <= score < 0.72` | weak candidate requiring review unless rescued by another layer |
| `review` | `score < 0.58` | ambiguous/no candidate requiring review |

Rows with no nonzero candidate were retained as explicit review rows with
`match_score = 0.0`, `confidence = review`, `match_language = none`, and empty
source identifiers.

### Human-In-The-Loop Routing Rules

The layered HITL queue was constructed after both Layer 1 nutrient/reference
candidates and Layer 2 OpenFoodFacts product/processing candidates existed. For
each canonical food, the top-ranked Layer 1 candidate and top-ranked Layer 2
candidate were selected.

Review routing used the following rules:

| Condition | Queue action |
|---|---|
| Layer 1 confidence is `high` or `medium` | auto-accept Layer 1 candidate |
| Layer 2 confidence is `high` or `medium` | treat Layer 2 product evidence as strong |
| Layer 1 confidence is `low` or `review` and Layer 2 is not strong | send canonical food to HITL |
| Layer 1 confidence is `low` or `review` but Layer 2 is `high` or `medium` | auto-accept because product/processing evidence is strong |

Thus, the final HITL queue contains weak or ambiguous Layer 1 cases only when
Layer 2 does not provide a strong product/processing candidate. The queue is
tracked at the canonical-food level, while also reporting how many original HPP
food IDs and diet-logging observations each canonical review row represents.

Usage tiers were calculated from `number_loggings` summed across HPP foods within
each canonical concept. Canonical foods were sorted by total logging frequency,
and cumulative logging share was used to assign:

| Usage tier | Rule |
|---|---|
| `tier_1_high_usage_top_80pct` | cumulative logging share `<= 0.80` |
| `tier_2_medium_usage_next_15pct` | cumulative logging share `> 0.80` and `<= 0.95` |
| `tier_3_low_usage_last_5pct` | cumulative logging share `> 0.95` |

The HITL UI writes role-specific decisions rather than one universal mapping.
Reviewers can accept Layer 1, accept Layer 2, accept both, save context and remap
Layer 1, save context and remap Layer 2, save context and remap both, or assign
the item to an existing canonical food concept. Remapping uses only the
reviewer-supplied text for the selected layer(s); all other food items and
previously accepted mappings remain unchanged.

### Layer-Specific Inclusion And Dropping Rules

The current pipeline intentionally keeps source-specific evidence modular. It
does not require every database to map every food, and it does not drop a
canonical food simply because a later layer is missing. Missing Layer 2-5
features are represented as zero counts or blank annotations in the final
feature matrix.

Layer 1 nutrient/reference mapping:

- Input candidates: USDA SR Legacy, FNDDS, AUSNUT, Tzameret, Bahrain, and MEXT
  identity/cooking-name support.
- Retained candidates: top `5` per canonical food.
- Downstream nutrient harmonization currently accepts mappings with confidence
  in `high`, `medium`, or `review`; `low` confidence mappings are excluded unless
  replaced by human-reviewed remaps. This choice preserves exact/no-candidate
  review rows while excluding weak lexical candidates from nutrient transfer.
- Nutrient values are retained in source-native units and are marked
  `source_native_units_not_yet_standardized`.

Layer 2 OpenFoodFacts mapping:

- Input file: `data/OpenFoodFacts/en.openfoodfacts.org.products.csv`.
- Default scan: first `300,000` rows, controlled by `OFF_MAX_SCAN_ROWS`.
- Full scan: set `OFF_MAX_SCAN_ROWS=0`.
- Candidate retention: rows sharing at least one informative token with the
  canonical HPP food vocabulary, up to `OFF_MAX_CANDIDATES=150000` by default.
- Retained columns include product code/name, generic name, brands, categories,
  countries, ingredients, additive count/tags, allergens, labels, Nutri-Score,
  NOVA group, PNNS groups, food groups, completeness, and selected per-100 g
  nutrients.
- Downstream processing reference uses only the top-ranked OpenFoodFacts
  candidate per canonical food.

Layer 3 FoodAtlas/FooDB chemistry:

- FoodAtlas direct food mapping uses top-ranked HPP-to-FoodAtlas food candidates.
- FoodAtlas compound features are generated from native `contains` edges where
  a mapped FoodAtlas food points to a chemical entity.
- FoodAtlas disease features are counted from chemical-to-disease edges with
  `positively_correlates_with` and `negatively_correlates_with` relations.
- FooDB mapping uses top `5` canonical-food to FooDB-food candidates, and the
  compound reference uses the top-ranked FooDB food per canonical food.
- FooDB compound extraction reads `Content.json` and retains only rows where
  `source_type == "Compound"` and the FooDB `food_id` belongs to a top-matched
  canonical FooDB food.
- The full run uses `FOODB_MAX_CONTENT_ROWS=0`, meaning no row cap. A positive
  value can be used for smoke tests.
- FooDB compound nodes in the KG are de-duplicated by FooDB public compound ID
  when present, otherwise by numeric FooDB compound ID.

Layer 4 HMDB metabolomics:

- HMDB XML files are parsed for six biospecimen-specific metabolite sets:
  serum, urine, feces, saliva, sweat, and CSF.
- The full run uses `HMDB_MAX_METABOLITES_PER_FILE=0`, meaning no per-file cap.
  A positive value can be used for development smoke tests.
- The parser stores HMDB accession, name, biospecimen, formula, molecular
  weight, InChIKey, InChI, SMILES, FooDB ID, PubChem, ChEBI, KEGG, taxonomy
  fields, disease names, and pathway names.
- Disease and pathway name lists are suppressed for a metabolite when they exceed
  `HMDB_MAX_DISEASES_PER_METABOLITE=200` or
  `HMDB_MAX_PATHWAYS_PER_METABOLITE=200`. In these cases the raw counts and an
  overflow flag are retained, but the long text list is blanked to avoid
  uninformative expansion by ubiquitous metabolites.
- Food-to-HMDB links are created through direct FooDB public compound ID matches
  where available, otherwise through InChIKey matches.
- The exhaustive KG bridge is
  `outputs/reference/canonical_food_hmdb_metabolite_edges.csv`. The separate
  `canonical_food_hmdb_metabolite_link_examples.csv` is capped by
  `HMDB_LINK_EXAMPLE_LIMIT=50000` by default and is used for inspection only.

Layer 5 disease/pathway features:

- FoodAtlas disease edge counts are summarized as total, positive, and negative
  disease-correlation edge counts per canonical food.
- HMDB disease and pathway counts are summarized from the food-compound-metabolite
  links.
- Disease/pathway features are treated as graph annotations and hypothesis
  generation features, not causal diet-health effects.

Final KG construction:

- The KG includes all canonical foods and all HPP-to-canonical crosswalk edges.
- For canonical-to-public-FCDB, HPP-to-FoodAtlas, and canonical-to-FooDB mapping,
  only the top-ranked candidate per food is represented as a mapping edge.
- The full native FoodAtlas graph is included by default: all FoodAtlas entities
  plus all native triplets.
- The all-mapped FooDB compound bridge is included, after de-duplicating
  `(foodb_food_id, foodb_compound_public_id, foodb_compound_id)` rows.
- The all-mapped HMDB bridge is included from
  `canonical_food_hmdb_metabolite_edges.csv` when present; the capped example
  table is used only as fallback.
- HMDB edges with missing `canonical_food_id`, `foodb_compound_id`, or `hmdb_id`
  are dropped from KG construction.
- Long HMDB disease/pathway text fields are intentionally omitted from the
  exhaustive HMDB edge table to keep the full KG tractable; compact disease and
  pathway counts remain in the reference feature tables.
- Nutrient nodes and `has_nutrient_value` edges are included for all canonical
  nutrient provenance rows by default.

The following records were intentionally not represented as full KG nodes in the
current build:

- non-top-ranked candidate mappings, which remain in candidate CSV files for
  audit but are not promoted to accepted mapping edges;
- all OpenFoodFacts products, because Layer 2 keeps a bounded token-relevant
  source table and promotes only top-ranked product candidates;
- all FooDB foods, because the KG includes FooDB foods reached by canonical-food
  top matches and their compounds, not the complete FooDB food dictionary;
- all HMDB metabolites, because the KG includes HMDB metabolites reached through
  mapped FooDB compounds, not the complete parsed HMDB metabolite index;
- long exploded HMDB disease/pathway text annotations in the exhaustive edge
  table, because they can make ubiquitous metabolites dominate the graph without
  adding interpretable food-specific structure.

### Reference Feature Matrix Rule

The final canonical-food feature matrix starts with every canonical food and left
joins the nutrient, product/processing, FoodAtlas/FooDB chemical, HMDB
metabolite, and disease/pathway summary tables. Count columns are filled with
zero when a later layer is missing. This means an unmapped Layer 2, FooDB, HMDB,
or disease/pathway layer does not remove the food from the analytic matrix; it
only records absence of evidence from that layer.

## Step-By-Step Methods

### 1. HPP Food-Item Data Assembly

The primary input is the HPP food-item table:

```text
data/HPP/hpp_food_items_with_nutrients.csv
```

This file contains HPP food identifiers, food descriptions, category hints,
product/original names, and nutrient columns. The pipeline treats `food_id` as
the original HPP food identity. These IDs are never discarded; even after
canonicalization, each HPP food ID remains traceable through a crosswalk.

Relevant code:

```text
diet_data_enhancement/sources.py
diet_data_enhancement/nutrients.py
```

### 2. Public Food-Composition Database Assembly

The HPP list is mapped against multiple public or reference food-composition
sources:

```text
data/USDA_SR_Legacy/FoodData_Central_sr_legacy_food_csv_2018-04.zip
data/USDA_FNDDS/FoodData_Central_survey_food_csv_2024-10-31.zip
data/Tzameret_Israel/moh_mitzrachim.csv
data/AUSNUT_Australia/AUSNUT-2023-Food-details-4.xlsx
data/Bahrain FCT/Bahrain_Food_Composition_Table_pdf_extracted.xlsx
data/MEXT_Japan/1385123_Table18.xlsx
data/OpenFoodFacts/en.openfoodfacts.org.products.csv
data/FoodAtlas/foodatlas-v4.5.zip
data/FooDB/foodb_2020_04_07_json/
data/HMDB/
```

Each source contributes food names, categories where available, source food IDs,
and source-specific metadata. USDA, FNDDS, AUSNUT, Tzameret, Bahrain, and MEXT
primarily support nutrient/reference identity mapping. OpenFoodFacts contributes
product, processing, ingredient, and packaging context. FoodAtlas contributes a
native food-chemical-disease graph. FooDB contributes food-compound chemistry and
external compound identifiers. HMDB contributes human metabolite, biospecimen,
disease, and pathway context. A source inventory is written to:

```text
outputs/inventory/source_inventory.csv
```

Relevant command:

```bash
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline inventory
```

### 3. Name Normalization And Deterministic Candidate Matching

Food names are normalized before matching. Normalization includes lowercasing,
punctuation cleanup, tokenization, and simple similarity scoring. For each HPP
food item, the deterministic mapper returns up to five candidate public FCDB
matches. Each candidate row contains:

- HPP food ID and HPP food name
- source database name
- source food ID
- matched food name
- candidate rank
- match score
- confidence tier
- human-review flag

Relevant code:

```text
diet_data_enhancement/text.py
diet_data_enhancement/mapping.py
```

Relevant command:

```bash
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline run
```

Key outputs:

```text
outputs/mapping/hpp_public_food_mappings.csv
outputs/mapping/review_queue.csv
outputs/mapping/mapping_summary.json
```

### 4. Initial Review Queue

The top-ranked candidate for each HPP food is assigned a confidence tier. Weak
or ambiguous mappings are placed in the review queue. The review queue is not a
final error list; it is a prioritization device that identifies entries for
human-in-the-loop review.

Key output:

```text
outputs/mapping/review_queue.csv
```

### 5. Human-In-The-Loop Correction

A local web UI allows reviewers to inspect uncertain mappings, search/select
food categories, enter corrected food names, add notes, and save corrections.
The UI uses the existing review queue and writes corrections to an audit log.
When a reviewer saves a correction, the corrected food name is remapped against
public FCDBs and FoodAtlas.

Relevant code:

```text
diet_data_enhancement/ui/server.py
```

Relevant command:

```bash
conda run --no-capture-output -n ds python -m diet_data_enhancement.ui.server
```

Key outputs:

```text
outputs/mapping/human_corrections.csv
outputs/foodatlas/human_foodatlas_remap.csv
outputs/graph/food_mapping_graph.json
```

### 6. Canonical Food Concept Layer

Many HPP food IDs represent the same short food concept but differ in original
or product names. For example, the canonical concept `Coffee` may include HPP
entries such as `Espresso`, `Instant Coffee`, `ground coffee`, and other
preparations. To reduce duplicated review work, HPP food IDs are collapsed into
canonical food concepts using normalized short food name plus category.

This step preserves both levels:

- Original HPP food IDs remain as `hpp_food` nodes.
- Canonical food concepts become `canonical_food` nodes.
- A crosswalk links each HPP food ID to one canonical concept.

Relevant code:

```text
diet_data_enhancement/canonical.py
```

Relevant command:

```bash
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline canonical-all
```

Key outputs:

```text
outputs/canonical/canonical_foods.csv
outputs/canonical/hpp_to_canonical.csv
outputs/canonical/canonical_public_food_mappings.csv
outputs/canonical/canonical_review_queue.csv
outputs/canonical/canonical_food_graph.json
outputs/canonical/canonical_pipeline_summary.json
```

### 7. Canonical-Level Public FCDB Mapping

After canonicalization, the mapping procedure is repeated at the canonical food
concept level. This allows repeated HPP items to inherit one canonical mapping
while retaining original ID-level traceability. Canonical mapping provides a
smaller and more reviewable table than HPP-ID-level matching.

Key output:

```text
outputs/canonical/canonical_public_food_mappings.csv
```

### 8. Optional OpenAI Embedding Retrieval And GPT Validation

The pipeline includes an optional OpenAI-based mapping module. It performs
embedding-based candidate retrieval and then uses GPT validation to judge whether
candidate matches are close enough for nutrient transfer.

This step is optional and is designed to be reproducible without saving the API
key. If `OPENAI_API_KEY` is not already set, the command prompts for a key for
that run only.

Relevant code:

```text
diet_data_enhancement/openai_matching.py
```

Relevant commands:

```bash
conda run --no-capture-output -n ds python -m diet_data_enhancement.openai_matching embed-match --limit-hpp 100 --top-k 5
conda run --no-capture-output -n ds python -m diet_data_enhancement.openai_matching validate --limit 50
```

Key outputs:

```text
outputs/openai/openai_embedding_candidates.csv
outputs/openai/gpt_validated_candidates.csv
outputs/openai/openai_run_summary.json
```

In the current pilot run, OpenAI/GPT validation is used as an internal
validation signal rather than as a formal gold-standard accuracy estimate.

### 9. Nutrient Harmonization

Nutrient data from HPP and mapped public sources are joined into an HPP-level
harmonized nutrient table. HPP nutrient columns are kept with an `hpp__` prefix,
while mapped source nutrient columns are kept with a `mapped__` prefix. Human
review remaps are preferred when present.

Relevant code:

```text
diet_data_enhancement/nutrients.py
```

Relevant command:

```bash
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline harmonize-nutrients
```

Key outputs:

```text
outputs/nutrients/hpp_nutrient_harmonized.csv
outputs/nutrients/nutrient_harmonization_summary.json
```

### 10. Canonical Nutrient Imputation With Provenance

Canonical food nutrient profiles are constructed by aggregating nutrient values
across all HPP food IDs belonging to the same canonical food concept. The
current imputation rule is:

1. Prefer observed HPP nutrient values when available.
2. Aggregate repeated HPP values using `number_loggings` as weights where
   available.
3. If HPP is missing for a nutrient, use mapped public-source nutrient values.
4. Record the chosen value and provenance for every canonical nutrient value.

This produces both a wide nutrient-profile table and a long provenance table.
Nutrient names are harmonized, but units are currently marked as source-native
and should be unit-standardized before final analytic use.

Relevant command:

```bash
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline impute-nutrients
```

Key outputs:

```text
outputs/nutrients/canonical_nutrient_profiles.csv
outputs/nutrients/canonical_nutrient_provenance.csv
outputs/nutrients/canonical_nutrient_imputation_summary.json
```

### 11. FoodAtlas Extraction And Mapping

FoodAtlas is used to add biological and disease-related structure to the food
data. The source archive contains FoodAtlas food, chemical, and disease entities
as well as native FoodAtlas relationships:

- `contains`
- `is_a`
- `positively_correlates_with`
- `negatively_correlates_with`

The pipeline extracts FoodAtlas food entities for direct food-name mapping and
also imports the full FoodAtlas native graph into the final KG.

Relevant code:

```text
diet_data_enhancement/foodatlas.py
diet_data_enhancement/final_kg.py
```

Relevant commands:

```bash
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline extract-foodatlas
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline map-foodatlas
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline map-reviewed-foodatlas
```

Key outputs:

```text
outputs/foodatlas/entities_foods.csv
outputs/foodatlas/hpp_foodatlas_candidates.csv
outputs/foodatlas/human_foodatlas_remap.csv
```

### 12. Final Modular Knowledge Graph

The final knowledge graph combines:

- HPP food nodes
- canonical food nodes
- public FCDB source food nodes
- FoodAtlas food nodes
- FoodAtlas chemical nodes
- FoodAtlas disease/medical-condition nodes
- nutrient nodes
- human correction nodes
- mapping edges
- canonical assignment edges
- nutrient-value edges
- OpenAI/GPT validation edges where available
- FoodAtlas native relationship edges

Relevant code:

```text
diet_data_enhancement/final_kg.py
diet_data_enhancement/graph_store.py
```

Relevant command:

```bash
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline build-kg
```

Key outputs:

```text
outputs/kg/final_food_kg.json
outputs/kg/final_food_kg_nodes.csv
outputs/kg/final_food_kg_edges.csv
outputs/kg/final_food_kg_summary.json
```

The current full KG contains:

- 297,299 nodes
- 2,325,237 edges
- 193,236 FoodAtlas chemical nodes
- 13,298 FoodAtlas disease/medical-condition nodes
- 63,449 FooDB compound nodes in the all-mapped KG bridge
- 7,612 HMDB metabolite nodes in the all-mapped KG bridge
- 84,099 positive FoodAtlas disease-correlation edges
- 46,757 negative FoodAtlas disease-correlation edges
- 1,613,988 FooDB contains-compound bridge edges
- 7,859 FooDB-to-HMDB metabolite bridge edges

### 13. Visualization And Paper Figures

The repository creates both full interactive and publication-oriented
visualizations. The full visualization is a canvas-based browser explorer that
contains all nodes and edges and supports search, pan/zoom, node dragging, and
1st- to 4th-degree neighborhood expansion. Static paper figures use aggregate or
focused representations because the full node-level KG is too large to plot as a
readable static network.

Relevant code:

```text
diet_data_enhancement/kg_visualization.py
notebooks/kg_visualization_and_checks.ipynb
```

Relevant commands:

```bash
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline build-full-kg-viz
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline build-kg-viz
```

Key outputs:

```text
outputs/visualizations/kg_full_interactive.html
outputs/visualizations/kg_full_visualization_data.js
outputs/visualizations/kg_paper_schema_overview_plotly.html
outputs/visualizations/kg_focused_interactive.html
outputs/visualizations/kg_focused_publication_subgraph.svg
outputs/visualizations/kg_focused_subgraph.json
```

### 14. Multimodal Food Concepts And Pattern Discovery

The multimodal analysis layer converts the structured reference tables and final
KG into food concept representations. This stage produces both machine-readable
vectors and interpretable text descriptions for each canonical food. The same
logic can later be applied to person-level diet events inside the TRE.

The vector representation combines modular feature blocks:

- nutrient amounts from the canonical nutrient feature matrix;
- OpenFoodFacts product, ingredient, additive, label, and processing features;
- FoodAtlas/FooDB chemical features and food-compound edges;
- HMDB metabolite, biofluid, disease, and pathway features;
- graph-neighborhood features derived from the final KG;
- stable hashed text-evidence dimensions created from food concept evidence
  fields.

Numeric features are log-transformed, median-imputed, standardized, and scaled by
block size before concatenation. The current vector version,
`multimodal_structured_v1`, is fully offline and does not call an embedding API.
It creates 280-dimensional vectors: 192 nutrient dimensions, 14
product/processing dimensions, 3 chemical-count dimensions, 7
metabolite/disease/pathway dimensions, and 64 stable hashed text-evidence
dimensions. A two-dimensional PCA projection and deterministic eight-cluster
K-means assignment are also written for inspection.

The text representation summarizes the same evidence in auditable natural
language. For example, a portion-scaled coffee event could be represented as a
sentence describing the canonical food mapping, available nutrient amounts,
coffee-associated chemicals, HMDB metabolite and biofluid links, and
disease/pathway graph neighborhoods. Exact nutrient amounts can be dose-scaled
when units are standardized; chemical, metabolite, disease, and pathway graph
features should be interpreted as mapped exposure/annotation features unless
source concentrations and biological conversion assumptions support true dose
estimation.

Relevant code:

```text
diet_data_enhancement/multimodal.py
```

Relevant command:

```bash
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline build-multimodal-space
```

Optional API-based sentence embeddings can be generated from the same food
concept sentences:

```bash
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline build-llm-sentence-embeddings
```

This optional step uses `OPENAI_FOOD_CONCEPT_EMBEDDING_MODEL`, defaulting to
`text-embedding-3-large`, and writes a separate LLM sentence-embedding space.
The pipeline command prompts for the API key in the terminal for that run,
keeps it only in memory, and does not write it to project outputs or local
configuration files.

Key outputs:

```text
outputs/embeddings/canonical_food_multimodal_vectors.parquet
outputs/embeddings/canonical_food_multimodal_vector_dimensions.csv
outputs/embeddings/canonical_food_concept_sentences.csv
outputs/embeddings/embedding_space_projection.csv
outputs/embeddings/embedding_space_interactive.html
outputs/embeddings/food_disease_pattern_discovery.csv
outputs/embeddings/multimodal_food_concept_space_summary.json
outputs/embeddings/canonical_food_sentence_embeddings.parquet
outputs/embeddings/llm_embedding_space_projection.csv
outputs/embeddings/llm_embedding_space_interactive.html
```

The first pattern-discovery output summarizes disease and pathway labels that
occur frequently within each multimodal food cluster. These summaries are
exploratory and hypothesis-generating; future versions should add formal
background-corrected enrichment tests and compare structured vectors with API
sentence embeddings.

### 15. Internal Validation

Internal validation metrics are generated for manuscript reporting and
comparison with food-mapping papers. The current validation notebook reports:

- mapping coverage
- high/medium-confidence mapping percentage
- low/review-confidence percentage
- best-match score distributions
- score-threshold coverage
- canonical review-burden reduction
- OpenAI/GPT pilot validation results
- nutrient-profile coverage
- KG node and edge counts

Relevant notebook:

```text
notebooks/internal_validation_metrics.ipynb
```

Key outputs:

```text
outputs/validation/mapping_validation_summary.csv
outputs/validation/score_threshold_coverage.csv
outputs/validation/canonical_review_burden_reduction.csv
outputs/validation/nutrient_coverage_metrics.csv
outputs/validation/manuscript_validation_summary.csv
```

Current headline internal validation metrics include:

- 7,405 HPP food IDs
- 842 canonical food concepts
- 88.63% of HPP food rows collapsed into canonical concepts
- 27.10% high/medium-confidence HPP-to-public-FCDB mapping
- 31.83% high/medium-confidence canonical-to-public-FCDB mapping
- 27.21% high/medium-confidence HPP-to-FoodAtlas mapping
- 89.37% reduction in low/review mapping burden after canonicalization
- 62.00% GPT-equivalent `yes` in the OpenAI pilot validation sample
- 100.00% of canonical foods with at least one nutrient value

These are internal validation metrics. Deterministic scores, confidence tiers,
and GPT judgments should not be described as formal accuracy unless a blinded
expert-adjudicated gold-standard set is created.

## Reproducible Command Sequence

From a fresh project checkout or folder:

```bash
conda create -n ds python=3.11 pandas openpyxl pyarrow plotly nbformat jupyter -y
conda run -n ds python -m pip install openai
```

Run the full non-OpenAI pipeline:

```bash
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline run-all
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline layered-all
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline chem-bio-all
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline build-reference
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline build-kg
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline build-full-kg-viz
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline build-kg-viz
conda run --no-capture-output -n ds python -m diet_data_enhancement.report
```

The layered chemical/biology portion can also be rerun independently:

```bash
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline layer3-foodb-map
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline layer3-foodb-compounds
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline layer3-chemical-features
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline layer4-hmdb-index
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline layer4-hmdb-links
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline layer5-disease-pathway
conda run --no-capture-output -n ds python -m diet_data_enhancement.pipeline build-reference
```

For fast smoke tests, set `FOODB_MAX_CONTENT_ROWS` and
`HMDB_MAX_METABOLITES_PER_FILE` to positive values. The full local run uses `0`
for both. `HMDB_LINK_EXAMPLE_LIMIT` controls the capped example edge output, and
`HMDB_MAX_PATHWAYS_PER_METABOLITE` / `HMDB_MAX_DISEASES_PER_METABOLITE` suppress
ubiquitous metabolites from dominating the compact disease/pathway summaries.

The full KG uses `outputs/reference/canonical_food_hmdb_metabolite_edges.csv`
as the complete minimal all-mapped FooDB-to-HMDB bridge. The separate
`canonical_food_hmdb_metabolite_link_examples.csv` remains capped for inspection
only.

Optional OpenAI pilot:

```bash
conda run --no-capture-output -n ds python -m diet_data_enhancement.openai_matching embed-match --limit-hpp 100 --top-k 5
conda run --no-capture-output -n ds python -m diet_data_enhancement.openai_matching validate --limit 50
```

Open notebooks for examples, visualization, and validation:

```text
notebooks/staged_mapping_examples.ipynb
notebooks/openai_matching_output_review.ipynb
notebooks/kg_visualization_and_checks.ipynb
notebooks/internal_validation_metrics.ipynb
```

## Suggested Paper Methods Wording

We developed a staged food data enhancement workflow outside the TRE using HPP
food-item reference data and multiple public food-composition databases. HPP
food names and public database food names were normalized and compared using a
deterministic candidate-matching procedure that generated ranked candidate
matches and confidence tiers. Low-confidence and ambiguous matches were routed
to a human-in-the-loop review interface, where corrected food names, categories,
and notes were captured in an auditable correction log and re-used for
remapping.

To reduce duplicate review and mapping work, HPP food IDs were collapsed into
canonical food concepts using normalized short food name and category while
preserving the original HPP ID to canonical concept crosswalk. Public FCDB
mapping was repeated at the canonical concept level. An optional OpenAI module
performed embedding-based retrieval and GPT-based validation of candidate
matches; API keys were entered only at runtime and were not stored.

Nutrient data were harmonized by joining HPP nutrient values with mapped public
source nutrient values. Canonical nutrient profiles were constructed by
aggregating repeated HPP values and imputing missing nutrients from mapped public
sources, with provenance recorded for every selected nutrient value. FoodAtlas
entities and relationships were then integrated to connect foods to FoodAtlas
foods, chemicals, and disease/medical-condition entities through native
FoodAtlas relationship types. The final output was a modular property graph
containing HPP foods, canonical food concepts, public FCDB source foods,
FoodAtlas food/chemical/disease entities, nutrient nodes, human correction
nodes, and provenance-bearing relationship edges.

Internal validation summarized mapping coverage, confidence-tier distributions,
score-threshold coverage, review-burden reduction after canonicalization,
OpenAI/GPT pilot validation, nutrient coverage, and graph component counts.
Because the current evaluation does not yet include a blinded expert-adjudicated
gold standard, these metrics are reported as internal validation rather than
formal mapping accuracy.
