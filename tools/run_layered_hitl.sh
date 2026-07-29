#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:8766 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Layered HITL UI is already running at http://127.0.0.1:8766"
  exit 0
fi

if command -v conda >/dev/null 2>&1 && conda env list | awk '{print $1}' | grep -qx ds; then
  conda run --no-capture-output -n ds python -m diet_data_enhancement.ui.layered_server
else
  python3 -m diet_data_enhancement.ui.layered_server
fi
