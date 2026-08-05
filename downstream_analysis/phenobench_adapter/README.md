# PhenoBench Adapter

This folder contains the Diet Data Enhancement adapter for `phenobench-tre`.
The adapter code stays in this repo. The reusable PhenoBench execution code
lives in the separate `phenobench-tre` repo/folder.

The matching PhenoBench-side handoff docs live in:

```text
phenobench-tre/outside_tre/
phenobench-tre/inside_tre/
phenobench-tre/adapter_builder/
```

The root-level `outside_tre/`, `inside_tre/`, and `adapter_builder/` folders are
the generic PhenoBench-TRE workflow. This folder is this project's exported
adapter.

The design separates work into two zones:

1. **Outside TRE:** LLM-assisted PhenoBench config drafting using public docs
   and placeholder artifact paths only.
2. **Inside TRE:** deterministic Diet Data Enhancement feature export into a
   PhenoBench artifact contract.

No LLM call or API key is required inside TRE.

## What The Adapter Exports

From a participant-level diet feature table, the adapter can export:

```text
participant_embedding/<feature_set>.participant_embedding.parquet
participant_embedding/<feature_set>.participant_embedding.metadata.json
phenobench_task_cards/*.md
llm_task_card_brief.md
phenobench_adapter_manifest.json
```

The Parquet artifact follows the Phenobench `participant_embedding` contract:

```text
participant_id | embedding
```

where `embedding` is a numeric vector made from the selected diet features.

## Recommended Two-Phase Workflow

### Phase A: Outside TRE

Use this project plus the `phenobench-tre` repo docs to draft or refine task cards.
This can involve an LLM because it uses no private participant-level data.

```bash
python -m downstream_analysis.phenobench_adapter.phenobench_adapter write-llm-brief \
  --output-dir outputs/phenobench_adapter/planning \
  --feature-set-name denovo_full_data
```

Draft task cards can also be exported without any participant-level table:

```bash
python -m downstream_analysis.phenobench_adapter.phenobench_adapter write-task-cards \
  --output-dir outputs/phenobench_adapter/planning \
  --feature-set-name denovo_full_data
```

The generated `llm_task_card_brief.md` tells an agent to read:

```text
AGENTS.md
docs/onboarding.md
docs/architecture.md
configs/README.md
docs/task_cards/README.md
the closest task card and config for the selected task
```

Then the agent should explain what must change for the diet-enhancement data
before editing Phenobench files.

Canonical PhenoBench config/task-card edits should happen in `phenobench-tre`
after reviewing the generated drafts against the generic `outside_tre/` flow.

### Phase B: Inside TRE

Run only deterministic code on private data. For example:

```bash
python -m downstream_analysis.phenobench_adapter.phenobench_adapter build \
  --x-path downstream_analysis/test_outputs/cvd/full_data/X_full_data_30d.parquet \
  --output-dir outputs/phenobench_adapter/denovo_full_data \
  --feature-set-name denovo_full_data \
  --participant-policy mean \
  --adapter-mode artifact_only
```

`artifact_only` writes only:

```text
participant_embedding/
phenobench_adapter_manifest.json
```

Then run a reviewed config from `phenobench-tre/inside_tre` that points to the
artifact path written above:

```bash
python -m phenobench run /path/to/phenobench_configs/hba1c_denovo_full_data_ridge_cv.yaml
```

Inside TRE, `phenobench-tre` should be available as an offline checkout or
package alongside this Diet Data Enhancement repo. This adapter should be run
from the Diet Data Enhancement code, while reviewed configs are executed by
`phenobench-tre`. No LLM briefs, task-card drafting, API keys, or web access are
required.

## Adapter Modes

```text
artifact_only embedding artifact + manifest only; preferred modular TRE mode
tre_minimal   embedding artifact + executable configs, legacy convenience mode
outside_llm   embedding artifact + task cards + LLM brief
full          embedding artifact + configs + task cards + LLM brief
```

## What I Think Of The Suggested Phenobench Tasks

The colleague's list is exactly the right direction, but the tasks fall into
two technical shapes.

Participant-level tasks can use the current adapter immediately:

```text
hba1c
tg
ldl
fpg
glyca
vat
waist
waist_hip_ratio
```

These are compatible with one diet vector per participant, usually built from a
diet-history window before the phenotype measurement.

Meal-event or causal/time-series tasks need a second adapter:

```text
meal_ppgr
meal_cgm_trajectory
diet_sleep_causal_effect
post_meal_movement_priority
```

For those, one row should probably be one meal or one exposure window, not one
participant. They are high-value tasks, especially `meal_ppgr`, but they need
the Phenobench task contract inspected before generating configs.

Microbiome diversity/richness tasks are scientifically central for this
project, but the adapter should first confirm the exact Phenobench loader and
target columns:

```text
gut_shannon_diversity
gut_species_richness
```

## Current Config-Ready Target Bridge

The current hard-coded config export includes Phenobench-compatible
participant-level outcomes:

```text
hba1c -> bt__hba1c_float_value
tg    -> bt__triglycerides_float_value
ldl   -> bt__ldl_cholesterol_float_value
fpg   -> bt__glucose_float_value, only fasting-equivalent when metadata supports fasting
glyca -> Phenobench GlycA task loader when available
vat   -> Phenobench VAT task loader when available
waist -> Phenobench waist task loader when available
waist_hip_ratio -> Phenobench waist-hip-ratio task loader when available
```

Tasks marked as planning-only in `phenobench_task_map.json` produce task-card
context but no executable config until their task-specific adapter is added.

## Minimal Files To Upload To TRE For This Bridge

For the hard-coded TRE part, upload:

```text
downstream_analysis/phenobench_adapter/
requirements.txt
the participant-level feature table generated inside TRE or mounted there
```

If configs were generated outside TRE and paths are valid inside TRE, upload
only:

```text
phenobench_configs/*.yaml
participant_embedding/*.parquet
participant_embedding/*.metadata.json
phenobench_adapter_manifest.json
```

For safety, generate the embedding artifact inside TRE whenever the source table
contains private participant-level rows.

## Outside-TRE Web Sanity Check

Use this local test app to check the adapter UI flow with mock participant data:

```bash
python -m downstream_analysis.phenobench_adapter.test_web_app --project-root .
```

Then open:

```text
http://127.0.0.1:8771
```

The app writes disposable mock outputs to:

```text
outputs/phenobench_adapter/test_web/
```
