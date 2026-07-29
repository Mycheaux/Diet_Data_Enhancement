# Diet Data Enhancement Project — Two-Part Plan (Outside TRE / Inside TRE)

## Part 1 — Outside the TRE (build here, with OpenAI)

Everything in this part uses only public data (already downloaded: USDA SR Legacy/FNDDS, Tzameret, MEXT, AUSNUT, FoodAtlas, Bahrain FCT) and produces artifacts + code that get carried into the TRE as a finished, pre-tested package.

### Two distinct translation stages — why the split works this way

NutriMatch (and this project) does "raw data → nutrients" in two separate stages, and only one of them needs to happen outside:

- **Stage 1 — food-level harmonization (this is Part 1).** Operates on food composition *databases*, not on any individual's diet log. It matches food item descriptions across FCDBs — including HPP's own internal food code list (7,765 items, not participant records) — and imputes missing nutrients, producing an enriched per-food nutrient lookup table (21 → 151 nutrients). This is the only part that needs OpenAI LLM calls + embeddings, and the only part that needs anything from HPP at all (its bare food list, not individual data).
- **Stage 2 — person-level translation (this is Part 2, inside the TRE).** Once Stage 1's enriched lookup table exists, turning a participant's raw log (food code + grams) into their personal nutrient intake is just a lookup-and-scale operation — no LLM or embedding calls needed. This is what actually touches individual-level data, and it never needs to leave the TRE.

### 1. Harmonized nutrient reference (the NutriMatch-style pipeline)
- Standardization of food descriptions across all public FCDBs using an OpenAI GPT model.
- Embedding + cross-database matching using OpenAI embeddings, with `text-embedding-3-large` as the preferred higher-quality default and `text-embedding-3-small` as a lower-cost fallback.
- LLM-judged equivalence validation using an OpenAI GPT model and ranked nutrient imputation.
- Output: one merged reference table covering every public food item, enriched from ~21 baseline nutrients toward the ~151 NutriMatch achieved.

### 2. FoodAtlas knowledge-graph mapping
- Match the harmonized food list against FoodAtlas's food nodes.
- Attach chemical, bioactivity, disease-association, and flavor-descriptor fields where matched (partial coverage expected, ~1,430 FoodAtlas foods vs thousands in the harmonized list — report match rate, don't assume full coverage).

### 3. All downstream code, written and pre-tested end-to-end
- Feature-assembly code: turns a person's raw diet log + the harmonized/enriched reference into the full per-person nutrient+FoodAtlas feature table.
- **Fork the published pipeline rather than build from scratch.** The diet-microbiome paper's own code is public: [github.com/TmrSegev/diet-microbiome](https://github.com/TmrSegev/diet-microbiome) (Zenodo-archived, DOI 10.5281/zenodo.18959226). `diet_processing.ipynb` is the raw-log → ~700-feature pipeline; `diet_processing_nutrients_only.ipynb` is the nutrients-only variant (a ready-made stand-in for the "basic nutrients" arm of the ablation); `create_diet_mb.ipynb` merges diet features with microbiome data; `train_models.py`/`predict.py`/`SHAP.py` are the LightGBM/Ridge training, prediction, and SHAP interpretation harness; the repo also already has an external-validation pipeline (Australian/PNP3 cohorts) to mirror for cross-cohort transfer testing.
- Part 1 work = fork this repo and modify `diet_processing.ipynb` at the point where it pulls the baseline nutrient table, swapping in the harmonized/enriched (NutriMatch+FoodAtlas) lookup instead — producing an enriched sibling of the same feature-assembly + modeling code, tested against the repo's own `demo.ipynb` mock data (~30 min run, reproduces one of the paper's figures) so there's a working reference output to match before anything touches real data.
- This also means the microbiome-prediction targets from the original paper (alpha-diversity, species/pathway relative abundance, the diet→microbiome→phenotype simulation) are available as an additional outcome category for the ablation, not just the phenotype/biomarker targets — since the forked code already predicts them.
- **Running any of this against real data — the actual baseline-vs-enriched comparison — is Part 2 work, done inside the TRE.** Part 1 only produces the adapted code + its mock-data test pass; no real prediction numbers exist until Part 2.

### 4. A written "data contract" (critical deliverable)
A precise schema spec for every table the TRE-side code expects, e.g.:
- HPP diet log table: participant ID, food code, food name, weight (g), energy, date/timestamp.
- HPP internal food code list: food code, food name, category — this is what part 1's harmonized reference needs to be matched against once real codes are available.
- Phenotype/biomarker tables: participant ID, visit date, and each target field (BMI, body-fat %, waist circumference, VAT mass, triglycerides, WBC, Nightingale panel fields, CGM metrics, serum folate, etc.), with expected units.
Whoever preps real data inside the TRE follows this spec exactly, so the pre-tested code runs without modification.

### 5. Resolve the "no internet inside the TRE" problem now, not later
TREs are almost universally air-gapped or network-restricted — the harmonization pipeline's OpenAI GPT and embedding API calls cannot run inside the TRE. Before finishing Part 1, decide one of:
- **(a)** Bring HPP's food code list (just the list of unique foods/codes/categories — not individual-level records) out to Part 1 for matching, then carry only the resulting crosswalk table (HPP food code → harmonized nutrient/FoodAtlas profile) back into the TRE. Requires TRE administrator sign-off that a bare food-name list isn't itself protected data.
- **(b)** Bundle a fully offline embedding model (e.g., a local sentence-transformers model with no API dependency) into the code package, so the final HPP-food-to-reference matching step can run inside the TRE without internet. Lower expected match quality than the OpenAI GPT + OpenAI embeddings workflow, but self-contained.
This decision determines what exactly ships into the TRE, so it should be settled before Part 2 starts.

## Part 2 — Inside the TRE (you run this, OpenAI/Codex has no visibility)

### What gets carried in
- The harmonized + FoodAtlas-enriched reference table(s) from Part 1.
- The forked `diet-microbiome` codebase (feature assembly, modeling, SHAP, cross-cohort validation), modified for the enriched nutrient lookup and already passing on the repo's own mock demo data.
- Whichever offline matching solution was decided in Part 1, item 5.
- The data contract spec, so real data can be checked against it before running anything.

### What already exists inside the TRE
- Real HPP diet logs, HPP's internal food code list, demographics, and the phenotype/biomarker/CGM/microbiome tables needed for validation — none of this ever needs to leave. (Note: since the forked pipeline includes microbiome-prediction targets, requesting access should explicitly include the gut microbiome dataset alongside diet logs and phenotype/biomarker data — not just the latter two.)

### Steps to run inside
1. Match HPP's real food code list against the harmonized reference (via whichever method was chosen in Part 1.5).
2. Run the forked `diet_processing.ipynb`/`create_diet_mb.ipynb` to build the enriched per-person diet feature table (and merge with real microbiome data) from real diet logs — this is the first point where the pipeline sees real individual-level data.
3. Run `train_models.py`/`predict.py` against real phenotype/biomarker and microbiome targets, for the full nested comparison (raw HPP → +NutriMatch → +FoodAtlas → +HITL) — this is the step that actually tests whether enrichment improves prediction accuracy.
4. Run validation (cross-validation, `SHAP.py`, any cross-cohort checks via the repo's existing Australian/PNP3 validation pipeline).
5. Export only aggregate, non-identifying outputs (performance metrics, SHAP summary plots, result tables) through the TRE's disclosure/export review process — raw data and per-person values stay inside.

### Practical notes for running independently
- Since OpenAI/Codex can't see this environment, expect to debug real-data quirks yourself (schema mismatches, missing values, unexpected encodings) — the data contract from Part 1 is there to minimize this, but it won't catch everything.
- Confirm with TRE administrators what packages/versions are pre-approved inside the environment, since there's likely no live `pip install` — Part 1's code should be packaged with an explicit, pinned dependency list so it can be installed offline.
- Once aggregate results are exported, bring them back for interpretation/write-up help.
