"""Small local dashboard for TRE downstream prediction task runs.

The app is intentionally dependency-free: it uses the Python standard library
to show task cards, existing comparison tables, and run buttons for configured
prediction tasks.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import subprocess
import sys
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


@dataclass(frozen=True)
class TaskSpec:
    key: str
    title: str
    module: str
    config_path: Path
    output_dir: Path
    comparison_file: str
    summary_file: str
    description: str


def default_tasks(project_root: Path) -> list[TaskSpec]:
    return [
        TaskSpec(
            key="microbiome",
            title="Microbiome Prediction",
            module="downstream_analysis.tasks.microbiome_prediction.microbiome_prediction",
            config_path=project_root / "downstream_analysis" / "tasks" / "microbiome_prediction" / "example_config.json",
            output_dir=project_root / "downstream_analysis" / "tasks" / "microbiome_prediction" / "outputs",
            comparison_file="microbiome_feature_set_comparison.csv",
            summary_file="microbiome_prediction_run_summary.json",
            description="Predict URS or MetaPhlAn abundance targets from four diet representations.",
        ),
        TaskSpec(
            key="cvd",
            title="CVD Biomarker Prediction",
            module="downstream_analysis.tasks.cvd.cvd_prediction",
            config_path=project_root / "downstream_analysis" / "tasks" / "cvd" / "example_config.json",
            output_dir=project_root / "downstream_analysis" / "tasks" / "cvd" / "outputs",
            comparison_file="cvd_feature_set_comparison.csv",
            summary_file="cvd_prediction_run_summary.json",
            description="Predict cardiometabolic blood biomarkers from four diet representations.",
        ),
    ]


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": str(exc)}


def read_csv_preview(path: Path, max_rows: int = 60) -> tuple[list[str], list[list[str]]]:
    if not path.exists():
        return [], []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        rows = list(reader)
    if not rows:
        return [], []
    return rows[0], rows[1 : max_rows + 1]


def short_path(path: Path, project_root: Path) -> str:
    try:
        return str(path.relative_to(project_root))
    except ValueError:
        return str(path)


def run_task(task: TaskSpec, project_root: Path) -> dict:
    cmd = [
        sys.executable,
        "-m",
        task.module,
        "--config",
        str(task.config_path),
        "--project-root",
        str(project_root),
    ]
    completed = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True)
    return {
        "task": task.key,
        "returncode": completed.returncode,
        "command": " ".join(cmd),
        "stdout": completed.stdout[-8000:],
        "stderr": completed.stderr[-8000:],
    }


def render_table(headers: list[str], rows: list[list[str]]) -> str:
    if not headers:
        return "<p class='muted'>No comparison table found yet.</p>"
    head = "".join(f"<th>{html.escape(str(h))}</th>" for h in headers)
    body_rows = []
    for row in rows:
        body_rows.append("<tr>" + "".join(f"<td>{html.escape(str(cell))}</td>" for cell in row) + "</tr>")
    body = "".join(body_rows)
    return f"<div class='table-wrap'><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"


def render_task_card(task: TaskSpec, project_root: Path) -> str:
    summary_path = task.output_dir / task.summary_file
    comparison_path = task.output_dir / task.comparison_file
    summary = read_json(summary_path)
    headers, rows = read_csv_preview(comparison_path)
    status = "Complete" if comparison_path.exists() else "Not run"
    status_class = "ok" if comparison_path.exists() else "wait"
    targets = summary.get("targets", [])
    feature_sets = summary.get("feature_sets", [])
    missing_targets = summary.get("missing_targets", [])
    target_text = ", ".join(map(str, targets[:8])) if targets else "No targets recorded yet"
    if len(targets) > 8:
        target_text += f" ... +{len(targets) - 8}"
    feature_text = ", ".join(map(str, feature_sets)) if feature_sets else "No feature sets recorded yet"
    missing_text = ""
    if missing_targets:
        missing_text = f"<p><strong>Missing targets:</strong> {html.escape(', '.join(map(str, missing_targets)))}</p>"
    return f"""
    <section class="card">
      <div class="card-head">
        <div>
          <h2>{html.escape(task.title)}</h2>
          <p>{html.escape(task.description)}</p>
        </div>
        <span class="pill {status_class}">{status}</span>
      </div>
      <div class="meta">
        <p><strong>Config:</strong> {html.escape(short_path(task.config_path, project_root))}</p>
        <p><strong>Output:</strong> {html.escape(short_path(task.output_dir, project_root))}</p>
        <p><strong>Feature sets:</strong> {html.escape(feature_text)}</p>
        <p><strong>Targets:</strong> {html.escape(target_text)}</p>
        {missing_text}
      </div>
      <form method="post" action="/run">
        <input type="hidden" name="task" value="{html.escape(task.key)}">
        <button type="submit">Run Task</button>
      </form>
      <h3>Comparison Preview</h3>
      {render_table(headers, rows)}
    </section>
    """


def render_page(project_root: Path, tasks: list[TaskSpec], message: dict | None = None) -> bytes:
    cards = "\n".join(render_task_card(task, project_root) for task in tasks)
    message_html = ""
    if message:
        stdout = html.escape(message.get("stdout", ""))
        stderr = html.escape(message.get("stderr", ""))
        code = html.escape(str(message.get("returncode", "")))
        task = html.escape(str(message.get("task", "")))
        message_html = f"""
        <section class="run-log">
          <h2>Last Run: {task} (exit {code})</h2>
          <h3>Output</h3><pre>{stdout or "No stdout."}</pre>
          <h3>Errors / Warnings</h3><pre>{stderr or "No stderr."}</pre>
        </section>
        """
    page = f"""<!doctype html>
    <html>
    <head>
      <meta charset="utf-8">
      <title>Diet Data Enhancement Downstream Dashboard</title>
      <style>
        body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #17202a; background: #f5f7fa; }}
        header {{ background: #17324d; color: white; padding: 24px 32px; }}
        header h1 {{ margin: 0 0 8px; font-size: 28px; }}
        header p {{ margin: 0; color: #dbe7f3; }}
        main {{ max-width: 1280px; margin: 0 auto; padding: 24px; }}
        .toolbar {{ display: flex; gap: 12px; margin-bottom: 20px; align-items: center; }}
        button, .button {{ border: 0; background: #1769aa; color: white; padding: 9px 13px; border-radius: 6px; cursor: pointer; font-weight: 650; text-decoration: none; display: inline-block; }}
        button:hover, .button:hover {{ background: #0f548a; }}
        .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 18px; }}
        .card, .run-log {{ background: white; border: 1px solid #d9e0e7; border-radius: 8px; padding: 18px; box-shadow: 0 1px 2px rgba(20, 36, 56, 0.06); }}
        .card-head {{ display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }}
        h2 {{ margin: 0 0 6px; font-size: 20px; }}
        h3 {{ margin: 18px 0 8px; font-size: 15px; }}
        p {{ line-height: 1.45; }}
        .meta p {{ margin: 5px 0; font-size: 13px; }}
        .pill {{ white-space: nowrap; border-radius: 999px; padding: 5px 9px; font-size: 12px; font-weight: 750; }}
        .pill.ok {{ background: #dff4e8; color: #17633a; }}
        .pill.wait {{ background: #fff1cc; color: #7a5400; }}
        .muted {{ color: #667085; }}
        .table-wrap {{ overflow: auto; max-height: 420px; border: 1px solid #edf0f3; border-radius: 6px; }}
        table {{ border-collapse: collapse; width: 100%; font-size: 12px; }}
        th, td {{ padding: 7px 8px; border-bottom: 1px solid #edf0f3; text-align: left; vertical-align: top; }}
        th {{ position: sticky; top: 0; background: #eef3f8; z-index: 1; }}
        pre {{ white-space: pre-wrap; background: #101828; color: #f2f4f7; padding: 12px; border-radius: 6px; max-height: 280px; overflow: auto; }}
      </style>
    </head>
    <body>
      <header>
        <h1>Downstream Analysis Dashboard</h1>
        <p>Run TRE prediction tasks and compare feature-set performance.</p>
      </header>
      <main>
        <div class="toolbar">
          <a class="button" href="/">Refresh</a>
          <form method="post" action="/run-all"><button type="submit">Run All Tasks</button></form>
        </div>
        {message_html}
        <div class="cards">{cards}</div>
      </main>
    </body>
    </html>"""
    return page.encode("utf-8")


class DashboardHandler(BaseHTTPRequestHandler):
    project_root: Path
    tasks: list[TaskSpec]
    last_message: dict | None = None

    def do_GET(self) -> None:
        self._send_page()

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(length).decode("utf-8")
        form = parse_qs(data)
        parsed = urlparse(self.path)
        if parsed.path == "/run":
            task_key = form.get("task", [""])[0]
            task = next((item for item in self.tasks if item.key == task_key), None)
            self.last_message = run_task(task, self.project_root) if task else {"task": task_key, "returncode": "missing", "stderr": "Unknown task."}
        elif parsed.path == "/run-all":
            messages = [run_task(task, self.project_root) for task in self.tasks]
            self.last_message = {
                "task": "all",
                "returncode": ",".join(str(item["returncode"]) for item in messages),
                "stdout": "\n\n".join(f"[{item['task']}]\n{item['stdout']}" for item in messages),
                "stderr": "\n\n".join(f"[{item['task']}]\n{item['stderr']}" for item in messages if item.get("stderr")),
            }
        self._send_page()

    def _send_page(self) -> None:
        body = render_page(self.project_root, self.tasks, self.last_message)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch downstream-analysis task dashboard.")
    parser.add_argument("--project-root", default=".", help="Project root containing downstream_analysis and outputs.")
    parser.add_argument("--host", default="127.0.0.1", help="Host/IP to bind.")
    parser.add_argument("--port", type=int, default=8765, help="Port to serve.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_root = Path(args.project_root).resolve()
    handler = DashboardHandler
    handler.project_root = project_root
    handler.tasks = default_tasks(project_root)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    url = f"http://{args.host}:{args.port}"
    print(f"Downstream dashboard running at {url}")
    print("Press Ctrl+C to stop.")
    server.serve_forever()
