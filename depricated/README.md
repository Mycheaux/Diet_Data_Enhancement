# Depricated Files

This folder records notebook-style entry points that were moved out of the
active downstream-analysis package when the project switched to task-specific
runners plus a dashboard app.

The spelling `depricated` is retained because that was the requested folder
name.

## Move Record

| Previous path | New path | Reason |
|---|---|---|
| `downstream_analysis/preprocess.ipynb` | `depricated/downstream_analysis/preprocess.ipynb` | Replaced by task configs and `downstream_analysis/app.py`; shared preprocessing code now lives in `downstream_analysis/utils/preprocess.py`. |
| `downstream_analysis/supervised_prediction.ipynb` | `depricated/downstream_analysis/supervised_prediction.ipynb` | Replaced by task-specific runners in `downstream_analysis/tasks/`; shared modeling code now lives in `downstream_analysis/utils/modeling.py`. |

## Active Replacements

Use these instead:

```bash
python -m downstream_analysis.app --project-root .
python -m downstream_analysis.tasks.microbiome_prediction.microbiome_prediction --config downstream_analysis/tasks/microbiome_prediction/example_config.json --project-root .
python -m downstream_analysis.tasks.cvd.cvd_prediction --config downstream_analysis/tasks/cvd/example_config.json --project-root .
```
