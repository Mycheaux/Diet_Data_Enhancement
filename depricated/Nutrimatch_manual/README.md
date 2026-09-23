# Diet Data Enhancement Notebooks

These notebooks are designed as a two-step workflow for TRE/SageMaker:

1. Run the long model training from a console/background process.
2. Open the notebook afterward to load saved CSV artifacts, print paper-ready tables, and generate plots.

Do not rely on the notebook browser session for long training runs. If SageMaker disconnects, a console-launched `nohup` job should keep running on the server.

## Project Location In TRE

The expected TRE project root is:

```bash
/home/ec2-user/studies/Diet_Data_Enhancement_Project/Diet_Data_Enhancement_TRE
```

Run all commands below from that project root.

```bash
cd /home/ec2-user/studies/Diet_Data_Enhancement_Project/Diet_Data_Enhancement_TRE
```

## All Paper-Aligned Predictions: Linear + Tree Explainability

Use this notebook when you want a broad archived run over the NutriMatch/paper-aligned targets with both linear and tree models.

Notebook:

```text
depricated/Nutrimatch_manual/nutrimatch_all_predictions_linear_hgb_explainability.ipynb
```

Background runner:

```text
depricated/Nutrimatch_manual/run_nutrimatch_all_predictions_linear_hgb_explainability_background.py
```

It compares age/sex, basic nutrients, full NutriMatch nutrients, and the enhancement arms. It runs regression tasks with R2/RMSE/Pearson r, binary or categorical tasks with AUROC/AUPRC/F1 macro, and also creates quartile-classification tasks from continuous targets when sample counts allow it. Linear models save coefficient tables; tree models try LightGBM GPU first when usable, otherwise use histogram-based gradient boosting, and save SHAP tables when SHAP supports the fitted backend.

Start a background run from a Python/IPython/SageMaker console:

```python
from pathlib import Path
import os
import sys
import subprocess
import time

PROJECT_ROOT = Path("/home/ec2-user/studies/Diet_Data_Enhancement_Project/Diet_Data_Enhancement_TRE")
RUNNER = PROJECT_ROOT / "depricated/Nutrimatch_manual/run_nutrimatch_all_predictions_linear_hgb_explainability_background.py"
LOG_DIR = PROJECT_ROOT / "depricated/Nutrimatch_manual/outputs/nutrimatch_all_predictions_linear_hgb_explainability/outputs/logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

stamp = time.strftime("%Y%m%d_%H%M%S")
TMP_LOG = Path(f"/tmp/nutrimatch_all_predictions_linear_hgb_explainability_{stamp}.log")
PID = LOG_DIR / f"background_training_{stamp}.pid"
LATEST_PID = LOG_DIR / "background_training_latest.pid"

env = os.environ.copy()
env["DDE_RUN_TRAINING"] = "1"
env["PYTHONUNBUFFERED"] = "1"
env["DDE_USE_GPU"] = "1"
env["DDE_MODEL_FILTER"] = "linear,tree"
env["DDE_X_BATCH_SIZE"] = "20"
env["DDE_MAX_TARGETS"] = "0"
env["DDE_EXPLAIN_TOP_N"] = "40"
env["DDE_SHAP_SAMPLE_N"] = "500"
env["PYTHONPATH"] = f"{PROJECT_ROOT}:{env.get('PYTHONPATH', '')}"

log_file = open(TMP_LOG, "wb")
proc = subprocess.Popen(
    [sys.executable, "-u", str(RUNNER)],
    cwd=str(PROJECT_ROOT),
    stdout=log_file,
    stderr=subprocess.STDOUT,
    env=env,
    start_new_session=True,
    close_fds=True,
)

PID.write_text(str(proc.pid) + "\n")
LATEST_PID.write_text(str(proc.pid) + "\n")

print("Started all-prediction linear/tree explainability run.")
print("PID:", proc.pid)
print("Live log:", TMP_LOG)
print("PID file:", PID)
```

One-time log check:

```python
from pathlib import Path

logs = sorted(
    Path("/tmp").glob("nutrimatch_all_predictions_linear_hgb_explainability_*.log"),
    key=lambda p: p.stat().st_mtime,
    reverse=True,
)
if not logs:
    raise FileNotFoundError("No /tmp logs found for this run.")

LOG = logs[0]
print("Newest log:", LOG)
print(LOG.read_text(errors="replace")[-12000:])
```

Main saved outputs:

```text
depricated/Nutrimatch_manual/outputs/nutrimatch_all_predictions_linear_hgb_explainability/outputs/all_prediction_model_results.csv
depricated/Nutrimatch_manual/outputs/nutrimatch_all_predictions_linear_hgb_explainability/outputs/all_prediction_fold_metrics.csv
depricated/Nutrimatch_manual/outputs/nutrimatch_all_predictions_linear_hgb_explainability/outputs/all_prediction_oof_predictions.csv
depricated/Nutrimatch_manual/outputs/nutrimatch_all_predictions_linear_hgb_explainability/outputs/linear_coefficients.csv
depricated/Nutrimatch_manual/outputs/nutrimatch_all_predictions_linear_hgb_explainability/outputs/tree_shap_feature_importance.csv
depricated/Nutrimatch_manual/outputs/nutrimatch_all_predictions_linear_hgb_explainability/outputs/tree_shap_dependence_long.csv
depricated/Nutrimatch_manual/outputs/nutrimatch_all_predictions_linear_hgb_explainability/outputs/figures/
```

## NutriMatch Paper Figures With Enhancement Arms

Use this notebook when you want the paper-style NutriMatch Figure 3 analyses, but with Diet Data Enhancement feature sets added to the comparison.

Notebook:

```text
depricated/Nutrimatch_manual/nutrimatch_paper_figures_with_enhancements.ipynb
```

Background runner:

```text
depricated/Nutrimatch_manual/run_nutrimatch_paper_figures_with_enhancements_background.py
```

It compares:

- Age + sex
- Age + sex + paper-basic nutrients
- Age + sex + NutriMatch all nutrients
- Age + sex + De novo microbiome-oriented
- Age + sex + De novo cardiometabolic
- Age + sex + NutriMatch microbiome-oriented
- Age + sex + NutriMatch cardiometabolic
- Age + sex + NutriMatch broad diet-health
- Age + sex + NutriMatch mental-health
- Age + sex + De novo broad diet-health
- Age + sex + De novo mental-health

It creates paper-style outputs:

- Figure 3a-like phenotype prediction R2 plots, stratified by sex when sex is available.
- Figure 3b-like Nightingale biomarker correlation heatmaps.
- Figure 3c-like 2-year overweight/obesity ROC curves with AUROC.
- CSV tables showing which data source gives which accuracy metric for each target/task.

Main saved outputs:

```text
downstream_analysis/tasks/nutrimatch_paper_figures_with_enhancements/outputs/paper_figure_model_results.csv
downstream_analysis/tasks/nutrimatch_paper_figures_with_enhancements/outputs/paper_figure_oof_predictions.csv
downstream_analysis/tasks/nutrimatch_paper_figures_with_enhancements/outputs/paper_figure_metric_table.csv
downstream_analysis/tasks/nutrimatch_paper_figures_with_enhancements/outputs/paper_figure_arm_summary.csv
downstream_analysis/tasks/nutrimatch_paper_figures_with_enhancements/outputs/paper_figure_best_by_target.csv
downstream_analysis/tasks/nutrimatch_paper_figures_with_enhancements/outputs/paper_ready_metric_table.csv
downstream_analysis/tasks/nutrimatch_paper_figures_with_enhancements/outputs/figures/
```

If you are in a Python/IPython/SageMaker console, paste this to start a clean background run:

```python
from pathlib import Path
import os
import sys
import subprocess
import time

PROJECT_ROOT = Path("/home/ec2-user/studies/Diet_Data_Enhancement_Project/Diet_Data_Enhancement_TRE")
RUNNER = PROJECT_ROOT / "depricated/Nutrimatch_manual/run_nutrimatch_paper_figures_with_enhancements_background.py"
LOG_DIR = PROJECT_ROOT / "downstream_analysis/tasks/nutrimatch_paper_figures_with_enhancements/outputs/logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

stamp = time.strftime("%Y%m%d_%H%M%S")
TMP_LOG = Path(f"/tmp/nutrimatch_paper_figures_with_enhancements_{stamp}.log")
PID = LOG_DIR / f"background_training_{stamp}.pid"
LATEST_PID = LOG_DIR / "background_training_latest.pid"

env = os.environ.copy()
env["DDE_RUN_TRAINING"] = "1"
env["PYTHONUNBUFFERED"] = "1"
env["PYTHONPATH"] = f"{PROJECT_ROOT}:{env.get('PYTHONPATH', '')}"

log_file = open(TMP_LOG, "wb")
proc = subprocess.Popen(
    [sys.executable, "-u", str(RUNNER)],
    cwd=str(PROJECT_ROOT),
    stdout=log_file,
    stderr=subprocess.STDOUT,
    env=env,
    start_new_session=True,
    close_fds=True,
)

PID.write_text(str(proc.pid) + "\n")
LATEST_PID.write_text(str(proc.pid) + "\n")

print("Started NutriMatch paper figures with enhancement arms.")
print("PID:", proc.pid)
print("Live log:", TMP_LOG)
print("PID file:", PID)
```

To watch the latest log from the Python/IPython/SageMaker console:

```python
from pathlib import Path
import time

logs = sorted(
    Path("/tmp").glob("nutrimatch_paper_figures_with_enhancements_*.log"),
    key=lambda p: p.stat().st_mtime,
    reverse=True,
)
if not logs:
    raise FileNotFoundError("No /tmp NutriMatch paper-figures logs found.")

LOG = logs[0]
print("Watching:", LOG)

last_size = 0
for tick in range(10_000):
    text = LOG.read_text(errors="replace")
    if len(text) != last_size:
        print("\n" + "=" * 80)
        print("tick", tick, "| size", len(text), "|", time.ctime(LOG.stat().st_mtime))
        print(text[-12000:])
        last_size = len(text)
    time.sleep(30)
```

After it prints `STATUS: COMPLETE`, open and run:

```text
depricated/Nutrimatch_manual/nutrimatch_paper_figures_with_enhancements.ipynb
```

The notebook should load saved results, print tables, and recreate the plots without rerunning training.

## NutriMatch 2-Year Overweight/Obesity Prediction With Enhancement Arms

Use this focused notebook when you only want the paper's Figure 3c-style analysis: predicting overweight/obesity status at about 2-year follow-up.

Notebook:

```text
depricated/Nutrimatch_manual/nutrimatch_two_year_obesity_with_enhancements.ipynb
```

Background runner:

```text
depricated/Nutrimatch_manual/run_nutrimatch_two_year_obesity_with_enhancements_background.py
```

What it does:

- Derives a 2-year follow-up target from anthropometrics BMI.
- Uses follow-up BMI closest to 730 days, within the default 540-900 day window.
- Labels overweight/obesity as follow-up BMI >= 25.
- Builds its own cached diet feature matrices after filtering diet days to >=800 kcal when calorie data are available.
- Compares age + sex, paper-basic nutrients, full NutriMatch, and the enhanced feature sets.
- Uses LightGBM as the primary paper-aligned model when it is installed. If LightGBM is unavailable, the runner records and uses the configured fallback unless `DDE_ALLOW_MODEL_FALLBACK=0`.
- Reports AUROC, AUPRC, accuracy, balanced accuracy, and F1.
- Creates paper-style ROC plots for the paper three arms and for paper arms plus enhancement arms.
- Adds a supplementary Random Forest classification section comparing NutriMatch all nutrients with the best-performing enhanced alternative, including feature-importance plots.

If you are in a Python/IPython/SageMaker console, paste this to start a clean background run:

```python
from pathlib import Path
import os
import sys
import subprocess
import time

PROJECT_ROOT = Path("/home/ec2-user/studies/Diet_Data_Enhancement_Project/Diet_Data_Enhancement_TRE")
RUNNER = PROJECT_ROOT / "depricated/Nutrimatch_manual/run_nutrimatch_two_year_obesity_with_enhancements_background.py"
LOG_DIR = PROJECT_ROOT / "downstream_analysis/tasks/nutrimatch_two_year_obesity_with_enhancements/outputs/logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

stamp = time.strftime("%Y%m%d_%H%M%S")
TMP_LOG = Path(f"/tmp/nutrimatch_two_year_obesity_with_enhancements_{stamp}.log")
PID = LOG_DIR / f"background_training_{stamp}.pid"
LATEST_PID = LOG_DIR / "background_training_latest.pid"

env = os.environ.copy()
env["DDE_RUN_TRAINING"] = "1"
env["PYTHONUNBUFFERED"] = "1"
env["DDE_MODEL"] = "lightgbm"
env["DDE_ALLOW_MODEL_FALLBACK"] = "1"
env["DDE_RUN_RF_SUPPLEMENT"] = "1"
env["DDE_X_BATCH_SIZE"] = "20"
env["PYTHONPATH"] = f"{PROJECT_ROOT}:{env.get('PYTHONPATH', '')}"

log_file = open(TMP_LOG, "wb")
proc = subprocess.Popen(
    [sys.executable, "-u", str(RUNNER)],
    cwd=str(PROJECT_ROOT),
    stdout=log_file,
    stderr=subprocess.STDOUT,
    env=env,
    start_new_session=True,
    close_fds=True,
)

PID.write_text(str(proc.pid) + "\n")
LATEST_PID.write_text(str(proc.pid) + "\n")

print("Started NutriMatch 2-year overweight/obesity prediction.")
print("PID:", proc.pid)
print("Live log:", TMP_LOG)
print("PID file:", PID)
```

To watch the latest log from the Python/IPython/SageMaker console:

```python
from pathlib import Path
import time

logs = sorted(
    Path("/tmp").glob("nutrimatch_two_year_obesity_with_enhancements_*.log"),
    key=lambda p: p.stat().st_mtime,
    reverse=True,
)
if not logs:
    raise FileNotFoundError("No /tmp two-year obesity logs found.")

LOG = logs[0]
print("Watching:", LOG)

last_size = -1
for tick in range(10_000):
    text = LOG.read_text(errors="replace")
    size = len(text)
    if size != last_size:
        print("\n" + "=" * 80)
        print("tick:", tick, "| size:", size, "| modified:", time.ctime(LOG.stat().st_mtime))
        print(text[-12000:])
        last_size = size
    if "STATUS: COMPLETE" in text or "STATUS: FAILED" in text:
        print("\nRun finished.")
        break
    time.sleep(30)
```

Main saved outputs:

```text
downstream_analysis/tasks/nutrimatch_two_year_obesity_with_enhancements/outputs/two_year_obesity_model_results.csv
downstream_analysis/tasks/nutrimatch_two_year_obesity_with_enhancements/outputs/two_year_obesity_fold_metrics.csv
downstream_analysis/tasks/nutrimatch_two_year_obesity_with_enhancements/outputs/two_year_obesity_oof_predictions.csv
downstream_analysis/tasks/nutrimatch_two_year_obesity_with_enhancements/outputs/paper_ready_two_year_obesity_table.csv
downstream_analysis/tasks/nutrimatch_two_year_obesity_with_enhancements/outputs/supplementary_random_forest_two_year_obesity_results.csv
downstream_analysis/tasks/nutrimatch_two_year_obesity_with_enhancements/outputs/supplementary_random_forest_feature_importance.csv
downstream_analysis/tasks/nutrimatch_two_year_obesity_with_enhancements/outputs/figures/
```

After it prints `STATUS: COMPLETE`, open and run:

```text
depricated/Nutrimatch_manual/nutrimatch_two_year_obesity_with_enhancements.ipynb
```

The notebook should load the saved results and recreate the ROC plots without rerunning training.

## 1. NutriMatch Paper-Target Prediction

This notebook predicts the paper-aligned target set from:

- age + sex
- age + sex + paper-basic nutrients
- age + sex + all NutriMatch nutrients
- age + sex + each enhanced diet feature set

It evaluates the primary `hist_gradient_boosting` model first, using the old fold-by-fold scoring strategy. Outputs include target/task/model/data-source metric tables with `R2`, `RMSE`, `Accuracy`, `AUROC`, and `AUPRC` where applicable.

Model-status note:

- The current default run uses sklearn `HistGradientBoostingRegressor` / `HistGradientBoostingClassifier`.
- Regression R2 is reported as the mean of per-fold R2 values, matching the older standalone notebook behavior.
- The previous `ridge` + `random_forest` run is useful as a transparent supplementary analysis, but it is not the current default.
- A separate primary section should also reproduce the NutriMatch paper model as exactly as the TRE data/code allow.
- A later model-expansion section can compare other candidates such as Elastic Net, Extra Trees, XGBoost/LightGBM/CatBoost where available, and calibrated classifiers.
- Do not run those extra model sections automatically until their exact specification is confirmed.

An old/manual copy is also available:

```text
depricated/Nutrimatch_manual/nutrimatch_paper_targets_prediction_old.ipynb
```

Use this notebook to rerun the earlier single boosting-style model manually. It trains by default and writes to:

```text
downstream_analysis/tasks/nutrimatch_paper_targets_prediction_old/outputs/
```

Start the background run from a shell/terminal:

```bash
mkdir -p downstream_analysis/tasks/nutrimatch_paper_targets_prediction/outputs/logs
PYTHONPATH="$PWD:${PYTHONPATH:-}" DDE_RUN_TRAINING=1 PYTHONUNBUFFERED=1 \
nohup python -u depricated/Nutrimatch_manual/run_nutrimatch_paper_targets_prediction_background.py \
  > /tmp/nutrimatch_paper_targets_prediction_background_training.log 2>&1 &
echo $! > downstream_analysis/tasks/nutrimatch_paper_targets_prediction/outputs/logs/background_training.pid
```

If you are in a Python/IPython/SageMaker console instead of a shell, paste this Python code:

```python
from pathlib import Path
import os
import sys
import subprocess

PROJECT_ROOT = Path("/home/ec2-user/studies/Diet_Data_Enhancement_Project/Diet_Data_Enhancement_TRE")
RUNNER = PROJECT_ROOT / "depricated/Nutrimatch_manual/run_nutrimatch_paper_targets_prediction_background.py"

LOG_DIR = PROJECT_ROOT / "downstream_analysis/tasks/nutrimatch_paper_targets_prediction/outputs/logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

PROJECT_LOG = LOG_DIR / "background_training.log"
TMP_LOG = Path("/tmp/nutrimatch_paper_targets_prediction_background_training.log")
PID = LOG_DIR / "background_training.pid"

env = os.environ.copy()
env["DDE_RUN_TRAINING"] = "1"
env["PYTHONUNBUFFERED"] = "1"
env["PYTHONPATH"] = f"{PROJECT_ROOT}:{env.get('PYTHONPATH', '')}"

log_file = open(TMP_LOG, "wb")

proc = subprocess.Popen(
    [sys.executable, "-u", str(RUNNER)],
    cwd=str(PROJECT_ROOT),
    stdout=log_file,
    stderr=subprocess.STDOUT,
    env=env,
    start_new_session=True,
    close_fds=True,
)

PID.write_text(str(proc.pid) + "\n")

print("Started NutriMatch paper target prediction.")
print("PID:", proc.pid)
print("Live log:", TMP_LOG)
print("Project log copy:", PROJECT_LOG)
print("PID file:", PID)
```

Check progress:

```bash
tail -f /tmp/nutrimatch_paper_targets_prediction_background_training.log
```

From a Python/IPython/SageMaker console, check progress with:

```python
from pathlib import Path

LOG = Path("/tmp/nutrimatch_paper_targets_prediction_background_training.log")

print(LOG.read_text(errors="replace")[-8000:])
```

If you want to copy the live log back into the project output folder:

```python
from pathlib import Path
import shutil

TMP_LOG = Path("/tmp/nutrimatch_paper_targets_prediction_background_training.log")
PROJECT_LOG = Path("/home/ec2-user/studies/Diet_Data_Enhancement_Project/Diet_Data_Enhancement_TRE/downstream_analysis/tasks/nutrimatch_paper_targets_prediction/outputs/logs/background_training.log")

if TMP_LOG.exists():
    shutil.copyfile(TMP_LOG, PROJECT_LOG)
    print("Copied log to:", PROJECT_LOG)
```

Check whether it is still running:

```bash
PID=$(cat downstream_analysis/tasks/nutrimatch_paper_targets_prediction/outputs/logs/background_training.pid)
ps -p "$PID" -o pid,ppid,stat,etime,cmd
```

From a Python/IPython/SageMaker console:

```python
from pathlib import Path
import subprocess

PID = Path("/home/ec2-user/studies/Diet_Data_Enhancement_Project/Diet_Data_Enhancement_TRE/downstream_analysis/tasks/nutrimatch_paper_targets_prediction/outputs/logs/background_training.pid")
pid = PID.read_text().strip()

subprocess.run(["ps", "-p", pid, "-o", "pid,ppid,stat,etime,cmd"])
```

Main saved outputs:

```text
downstream_analysis/tasks/nutrimatch_paper_targets_prediction/outputs/nutrimatch_paper_target_model_results.csv
downstream_analysis/tasks/nutrimatch_paper_targets_prediction/outputs/paper_target_metric_table.csv
downstream_analysis/tasks/nutrimatch_paper_targets_prediction/outputs/paper_target_best_by_target.csv
downstream_analysis/tasks/nutrimatch_paper_targets_prediction/outputs/paper_target_arm_summary.csv
downstream_analysis/tasks/nutrimatch_paper_targets_prediction/outputs/regression_deltas_vs_paper_baselines.csv
downstream_analysis/tasks/nutrimatch_paper_targets_prediction/outputs/classification_deltas_vs_paper_baselines.csv
```

After the console job finishes, open:

```text
depricated/Nutrimatch_manual/nutrimatch_paper_targets_prediction.ipynb
```

Run the notebook normally. It should load the saved results, print tables, and recreate figures without rerunning model training.

## 2. Diet Data Enhancement Benchmark I

This broader benchmark has sections for:

- NutriMatch paper-aligned prediction
- gut microbiome from diet
- Nightingale metabolomics from diet
- oral microbiome from diet
- CGM/post-meal glucose proxy traits from diet
- peripheral vascular health from diet

For each section, it compares:

- age + sex
- age + sex + base nutrients
- age + sex + NutriMatch
- age + sex + each enhanced feature set

It evaluates both `ridge` and `random_forest` models. It writes per-section metrics and combined tables showing which data source gives which accuracy metric for each target/task.

Start the background run:

```bash
mkdir -p downstream_analysis/tasks/diet_data_enhancement_benchmark_I/outputs/logs
PYTHONPATH="$PWD:${PYTHONPATH:-}" DDE_RUN_TRAINING=1 PYTHONUNBUFFERED=1 \
nohup python -u depricated/Nutrimatch_manual/run_diet_data_enhancement_benchmark_I_background.py \
  > downstream_analysis/tasks/diet_data_enhancement_benchmark_I/outputs/logs/background_training.log 2>&1 &
echo $! > downstream_analysis/tasks/diet_data_enhancement_benchmark_I/outputs/logs/background_training.pid
```

Check progress:

```bash
tail -f downstream_analysis/tasks/diet_data_enhancement_benchmark_I/outputs/logs/background_training.log
```

Check whether it is still running:

```bash
PID=$(cat downstream_analysis/tasks/diet_data_enhancement_benchmark_I/outputs/logs/background_training.pid)
ps -p "$PID" -o pid,ppid,stat,etime,cmd
```

Main combined outputs:

```text
downstream_analysis/tasks/diet_data_enhancement_benchmark_I/outputs/diet_data_enhancement_benchmark_I_all_metrics.csv
downstream_analysis/tasks/diet_data_enhancement_benchmark_I/outputs/diet_data_enhancement_benchmark_I_metric_table.csv
downstream_analysis/tasks/diet_data_enhancement_benchmark_I/outputs/diet_data_enhancement_benchmark_I_summary.csv
downstream_analysis/tasks/diet_data_enhancement_benchmark_I/outputs/diet_data_enhancement_benchmark_I_best_by_target.csv
downstream_analysis/tasks/diet_data_enhancement_benchmark_I/outputs/diet_data_enhancement_benchmark_I_best_overall.csv
```

Each section also writes its own folder:

```text
downstream_analysis/tasks/diet_data_enhancement_benchmark_I/outputs/01_nutrimatch_paper_aligned/
downstream_analysis/tasks/diet_data_enhancement_benchmark_I/outputs/02_gut_microbiome/
downstream_analysis/tasks/diet_data_enhancement_benchmark_I/outputs/03_nightingale_metabolomics/
downstream_analysis/tasks/diet_data_enhancement_benchmark_I/outputs/04_oral_microbiome/
downstream_analysis/tasks/diet_data_enhancement_benchmark_I/outputs/05_cgm_post_meal_glucose_proxies/
downstream_analysis/tasks/diet_data_enhancement_benchmark_I/outputs/06_peripheral_vascular_health/
```

After the console job finishes, open:

```text
depricated/Nutrimatch_manual/diet_data_enhancement_benchmark_I.ipynb
```

Run the notebook normally. It should load saved per-section metrics, print summary tables, and recreate figures.

## 3. Baseline Body-Fat Prediction With Enhancement Arms

Use this focused notebook when you want to test whether baseline diet features predict baseline body-composition traits. This replaces the earlier two-year body-fat framing, because the TRE `body_composition` table may not contain repeated measurements needed for a true two-year body-composition follow-up target.

Notebook:

```text
depricated/Nutrimatch_manual/nutrimatch_baseline_fat_prediction_with_enhancements.ipynb
```

Background runner:

```text
depricated/Nutrimatch_manual/run_nutrimatch_baseline_fat_prediction_with_enhancements_background.py
```

Targets:

- `body_comp_total_region_percent_fat`
- `body_comp_android_fat_free_mass`

Task versions:

- continuous regression for the baseline value
- tertile classification
- moving binary threshold selected by best `denovo_cardiometabolic` AUROC, then applied to all feature arms
- clinical/exploratory binary version: sex-specific high body-fat cutoff for total percent fat, and bottom-tertile low android fat-free mass where no universal clinical cutoff is available

If you are in a Python/IPython/SageMaker console, paste this to start a background run:

```python
from pathlib import Path
import os
import sys
import subprocess
import time

PROJECT_ROOT = Path("/home/ec2-user/studies/Diet_Data_Enhancement_Project/Diet_Data_Enhancement_TRE")
RUNNER = PROJECT_ROOT / "depricated/Nutrimatch_manual/run_nutrimatch_baseline_fat_prediction_with_enhancements_background.py"
LOG_DIR = PROJECT_ROOT / "downstream_analysis/tasks/nutrimatch_baseline_fat_prediction_with_enhancements/outputs/logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

stamp = time.strftime("%Y%m%d_%H%M%S")
TMP_LOG = Path(f"/tmp/nutrimatch_baseline_fat_prediction_with_enhancements_{stamp}.log")
PID = LOG_DIR / f"background_training_{stamp}.pid"
LATEST_PID = LOG_DIR / "background_training_latest.pid"

env = os.environ.copy()
env["DDE_RUN_TRAINING"] = "1"
env["PYTHONUNBUFFERED"] = "1"
env["DDE_MODEL"] = "lightgbm"
env["DDE_ALLOW_MODEL_FALLBACK"] = "1"
env["DDE_RUN_RF_SUPPLEMENT"] = "1"
env["DDE_X_BATCH_SIZE"] = "20"
env["PYTHONPATH"] = f"{PROJECT_ROOT}:{env.get('PYTHONPATH', '')}"

log_file = open(TMP_LOG, "wb")
proc = subprocess.Popen(
    [sys.executable, "-u", str(RUNNER)],
    cwd=str(PROJECT_ROOT),
    stdout=log_file,
    stderr=subprocess.STDOUT,
    env=env,
    start_new_session=True,
    close_fds=True,
)

PID.write_text(str(proc.pid) + "\n")
LATEST_PID.write_text(str(proc.pid) + "\n")

print("Started NutriMatch baseline body-fat prediction.")
print("PID:", proc.pid)
print("Live log:", TMP_LOG)
print("PID file:", PID)
```

To watch the latest log from the Python/IPython/SageMaker console:

```python
from pathlib import Path
import time

logs = sorted(
    Path("/tmp").glob("nutrimatch_baseline_fat_prediction_with_enhancements_*.log"),
    key=lambda p: p.stat().st_mtime,
    reverse=True,
)
if not logs:
    raise FileNotFoundError("No /tmp baseline body-fat logs found.")

LOG = logs[0]
print("Watching:", LOG)

last_size = -1
for tick in range(10_000):
    text = LOG.read_text(errors="replace")
    size = len(text)
    if size != last_size:
        print("\n" + "=" * 80)
        print("tick:", tick, "| size:", size, "| modified:", time.ctime(LOG.stat().st_mtime))
        print(text[-12000:])
        last_size = size
    if "STATUS: COMPLETE" in text or "STATUS: FAILED" in text:
        print("\nRun finished.")
        break
    time.sleep(30)
```

Main saved outputs:

```text
downstream_analysis/tasks/nutrimatch_baseline_fat_prediction_with_enhancements/outputs/baseline_fat_model_results.csv
downstream_analysis/tasks/nutrimatch_baseline_fat_prediction_with_enhancements/outputs/baseline_fat_oof_predictions.csv
downstream_analysis/tasks/nutrimatch_baseline_fat_prediction_with_enhancements/outputs/baseline_fat_task_catalog.csv
downstream_analysis/tasks/nutrimatch_baseline_fat_prediction_with_enhancements/outputs/baseline_fat_threshold_candidates.csv
downstream_analysis/tasks/nutrimatch_baseline_fat_prediction_with_enhancements/outputs/baseline_fat_denovo_cardiometabolic_threshold_scan.csv
downstream_analysis/tasks/nutrimatch_baseline_fat_prediction_with_enhancements/outputs/baseline_fat_best_moving_thresholds.csv
downstream_analysis/tasks/nutrimatch_baseline_fat_prediction_with_enhancements/outputs/baseline_fat_metric_table.csv
downstream_analysis/tasks/nutrimatch_baseline_fat_prediction_with_enhancements/outputs/baseline_fat_arm_summary.csv
downstream_analysis/tasks/nutrimatch_baseline_fat_prediction_with_enhancements/outputs/paper_ready_baseline_fat_table.csv
downstream_analysis/tasks/nutrimatch_baseline_fat_prediction_with_enhancements/outputs/baseline_fat_best_by_task.csv
downstream_analysis/tasks/nutrimatch_baseline_fat_prediction_with_enhancements/outputs/supplementary_random_forest_baseline_fat_results.csv
downstream_analysis/tasks/nutrimatch_baseline_fat_prediction_with_enhancements/outputs/supplementary_random_forest_baseline_fat_feature_importance.csv
downstream_analysis/tasks/nutrimatch_baseline_fat_prediction_with_enhancements/outputs/figures/
```

After it prints `STATUS: COMPLETE`, open and run:

```text
depricated/Nutrimatch_manual/nutrimatch_baseline_fat_prediction_with_enhancements.ipynb
```

The notebook should load saved results, print tables, and recreate plots without rerunning model training.

## Useful Optional Settings

For a quicker smoke test:

```bash
export DDE_RF_N_ESTIMATORS=50
export DDE_N_SPLITS=3
```

For the fuller run, leave those unset. The default random forest uses 300 trees and 5-fold cross-validation.

## Interpreting The Tables

The most useful files for the paper/supplement are:

- `*_metric_table.csv`: one row per target, task, model, and data source.
- `*_summary.csv`: average performance per model/data source.
- `*_best_by_target.csv`: best-performing data source for each target/model.
- `*_best_overall.csv`: strongest examples where enhanced data beats the NutriMatch baseline.

For regression tasks, use `R2`, `RMSE`, and `pearson_r`.
For classification tasks, use `Accuracy`, `balanced_accuracy`, `f1_macro`, `AUROC`, and `AUPRC`.
