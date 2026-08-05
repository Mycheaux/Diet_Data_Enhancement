"""Outside-TRE web sanity check for the Phenobench adapter.

The app uses deterministic mock participant features. It never reads private
TRE data and never calls an LLM.
"""

from __future__ import annotations

import argparse
import html
import json
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np
import pandas as pd

from downstream_analysis.phenobench_adapter.phenobench_adapter import (
    build_adapter_export,
    generate_task_cards,
    write_llm_task_card_brief,
)


FEATURE_SET_NAME = "outside_tre_mock_diet"


def create_mock_participant_features(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "mock_participant_diet_features.csv"
    rng = np.random.default_rng(42)
    rows = []
    for idx in range(1, 41):
        base = rng.normal(0.0, 1.0)
        rows.append(
            {
                "participant_id": f"mock_{idx:03d}",
                "window_id": "mock_30d",
                "split": "train" if idx <= 28 else "test",
                "nutrient_energy_kcal": 1800 + 250 * base + rng.normal(0, 60),
                "nutrient_fiber_g": 18 + 4 * rng.random(),
                "nutrient_saturated_fat_g": 14 + 5 * rng.random(),
                "processing_nova_high_share": float(rng.random()),
                "chemical_polyphenol_signal": 0.4 + 0.25 * rng.random(),
                "metabolite_caffeine_related_signal": 0.2 + 0.3 * rng.random(),
                "pathway_inflammation_neighborhood": 0.1 + 0.2 * rng.random(),
                "disease_cardiometabolic_neighborhood": 0.15 + 0.25 * rng.random(),
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def run_adapter_export(project_root: Path) -> dict:
    output_dir = project_root / "outputs" / "phenobench_adapter" / "test_web"
    mock_path = create_mock_participant_features(output_dir)
    return build_adapter_export(
        x_path=mock_path,
        output_dir=output_dir,
        feature_set_name=FEATURE_SET_NAME,
        id_col="participant_id",
        participant_policy="error",
        task_loader_mode="synthetic",
        tracking_uri="sqlite:///mlruns.db",
        adapter_mode="full",
    )


def run_planning_export(project_root: Path) -> dict:
    output_dir = project_root / "outputs" / "phenobench_adapter" / "test_web"
    tasks = json.loads(
        (
            project_root
            / "downstream_analysis"
            / "phenobench_adapter"
            / "phenobench_task_map.json"
        ).read_text(encoding="utf-8")
    )
    cards = generate_task_cards(
        output_dir=output_dir,
        feature_set_name=FEATURE_SET_NAME,
        tasks=tasks,
    )
    brief = write_llm_task_card_brief(
        output_dir=output_dir,
        feature_set_name=FEATURE_SET_NAME,
        tasks=tasks,
    )
    return {
        "llm_task_card_brief": str(brief),
        "phenobench_task_cards": [str(path) for path in cards],
    }


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": str(exc)}


def list_files(base: Path) -> list[Path]:
    if not base.exists():
        return []
    return sorted(path for path in base.rglob("*") if path.is_file())


def preview_table(path: Path, max_rows: int = 8) -> str:
    if not path.exists():
        return "<p class='muted'>Mock participant table has not been created yet.</p>"
    frame = pd.read_csv(path).head(max_rows)
    headers = "".join(f"<th>{html.escape(str(col))}</th>" for col in frame.columns)
    rows = []
    for _, row in frame.iterrows():
        rows.append(
            "<tr>"
            + "".join(f"<td>{html.escape(str(value))}</td>" for value in row.tolist())
            + "</tr>"
        )
    return (
        "<div class='table-wrap'><table><thead><tr>"
        + headers
        + "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )


def render_file_list(paths: list[Path], project_root: Path) -> str:
    if not paths:
        return "<p class='muted'>No files generated yet.</p>"
    items = []
    for path in paths:
        try:
            label = path.relative_to(project_root)
        except ValueError:
            label = path
        items.append(f"<li><code>{html.escape(str(label))}</code></li>")
    return "<ul>" + "".join(items) + "</ul>"


def render_page(project_root: Path, message: dict | None = None) -> bytes:
    output_dir = project_root / "outputs" / "phenobench_adapter" / "test_web"
    mock_path = output_dir / "mock_participant_diet_features.csv"
    manifest = read_json(output_dir / "phenobench_adapter_manifest.json")
    files = list_files(output_dir)
    message_html = ""
    if message:
        message_html = (
            "<section class='notice'>"
            f"<h2>{html.escape(str(message.get('title', 'Last Action')))}</h2>"
            f"<pre>{html.escape(json.dumps(message.get('payload', message), indent=2))}</pre>"
            "</section>"
        )
    manifest_html = (
        f"<pre>{html.escape(json.dumps(manifest, indent=2))}</pre>"
        if manifest
        else "<p class='muted'>Adapter manifest has not been generated yet.</p>"
    )
    page = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Phenobench Adapter Outside-TRE Test</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f6f8fb; color: #152232; }}
    header {{ background: #19324a; color: white; padding: 24px 32px; }}
    header h1 {{ margin: 0 0 8px; font-size: 26px; }}
    header p {{ margin: 0; color: #d9e6f2; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 24px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 16px; }}
    section {{ background: white; border: 1px solid #dbe3ec; border-radius: 8px; padding: 18px; box-shadow: 0 1px 2px rgba(20, 36, 56, 0.06); }}
    h2 {{ margin: 0 0 10px; font-size: 18px; }}
    p {{ line-height: 1.45; }}
    form {{ display: inline-block; margin: 4px 8px 8px 0; }}
    button, a.button {{ border: 0; background: #1769aa; color: white; padding: 9px 13px; border-radius: 6px; cursor: pointer; font-weight: 650; text-decoration: none; display: inline-block; }}
    button:hover, a.button:hover {{ background: #0f548a; }}
    .muted {{ color: #667085; }}
    .notice {{ border-left: 5px solid #1769aa; margin-bottom: 16px; }}
    .table-wrap {{ overflow: auto; max-height: 360px; border: 1px solid #edf0f3; border-radius: 6px; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 12px; }}
    th, td {{ padding: 7px 8px; border-bottom: 1px solid #edf0f3; text-align: left; white-space: nowrap; }}
    th {{ position: sticky; top: 0; background: #eef3f8; }}
    pre {{ white-space: pre-wrap; background: #101828; color: #f2f4f7; padding: 12px; border-radius: 6px; max-height: 360px; overflow: auto; font-size: 12px; }}
    code {{ background: #eef3f8; padding: 1px 4px; border-radius: 4px; }}
    ul {{ padding-left: 20px; }}
    li {{ margin: 4px 0; }}
  </style>
</head>
<body>
  <header>
    <h1>Phenobench Adapter Outside-TRE Test</h1>
    <p>Sanity-check the adapter using mock participant diet features only.</p>
  </header>
  <main>
    {message_html}
    <section>
      <h2>Actions</h2>
      <form method="post" action="/action"><input type="hidden" name="action" value="planning"><button type="submit">Generate Planning Files</button></form>
      <form method="post" action="/action"><input type="hidden" name="action" value="adapter"><button type="submit">Generate Mock Adapter Export</button></form>
      <a class="button" href="/">Refresh</a>
      <p class="muted">Outputs are written to <code>outputs/phenobench_adapter/test_web</code>.</p>
    </section>
    <div class="grid">
      <section>
        <h2>Mock Participant Feature Table</h2>
        {preview_table(mock_path)}
      </section>
      <section>
        <h2>Adapter Manifest</h2>
        {manifest_html}
      </section>
    </div>
    <section>
      <h2>Generated Files</h2>
      {render_file_list(files, project_root)}
    </section>
    <section>
      <h2>Phenobench Smoke Command</h2>
      <p>After generating the mock adapter export, a generated config can be inspected or copied into the Phenobench repo. This test uses mock data only; real execution still belongs inside TRE.</p>
      <pre>python -m phenobench run outputs/phenobench_adapter/test_web/phenobench_configs/hba1c_{FEATURE_SET_NAME}_ridge_cv.yaml</pre>
    </section>
  </main>
</body>
</html>"""
    return page.encode("utf-8")


class TestWebHandler(BaseHTTPRequestHandler):
    project_root: Path
    last_message: dict | None = None

    def do_GET(self) -> None:
        self._send_page()

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(length).decode("utf-8")
        form = parse_qs(data)
        parsed = urlparse(self.path)
        if parsed.path == "/action":
            action = form.get("action", [""])[0]
            try:
                if action == "planning":
                    payload = run_planning_export(self.project_root)
                    type(self).last_message = {
                        "title": "Planning files generated",
                        "payload": payload,
                    }
                elif action == "adapter":
                    payload = run_adapter_export(self.project_root)
                    type(self).last_message = {
                        "title": "Mock adapter export generated",
                        "payload": payload,
                    }
                else:
                    type(self).last_message = {
                        "title": "Unknown action",
                        "payload": {"action": action},
                    }
            except Exception as exc:
                type(self).last_message = {
                    "title": f"Action failed: {type(exc).__name__}",
                    "payload": {"error": str(exc), "traceback": traceback.format_exc()},
                }
        self._send_page()

    def _send_page(self) -> None:
        body = render_page(self.project_root, self.last_message)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Launch the outside-TRE Phenobench adapter test web app."
    )
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8771)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_root = Path(args.project_root).resolve()
    handler = TestWebHandler
    handler.project_root = project_root
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Phenobench adapter test web app running at http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    main()
