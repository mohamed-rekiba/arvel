#!/usr/bin/env bash
# Run the suite under coverage and enforce >=95% BRANCH-INCLUSIVE coverage.
#
# `branch = true` is enabled in pyproject, so the gate is on the combined line+branch metric
# (the stricter measure) — not line coverage alone. Both figures are printed for visibility.
# Run from the repo root (inside the venv or via `uv run`).
set -euo pipefail

coverage run -m pytest -q
coverage report --precision=2        # combined line+branch view (visibility)
coverage json -q -o .coverage.json
python - <<'PY'
import json

totals = json.load(open(".coverage.json"))["totals"]
line = 100 * totals["covered_lines"] / totals["num_statements"]
combined = totals["percent_covered"]  # branch-inclusive (branch=true)
print(f"line: {line:.2f}%  ·  branch-inclusive: {combined:.2f}%  (gate: combined >= 95%)")
raise SystemExit(0 if combined >= 95 else 1)
PY
