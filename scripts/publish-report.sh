#!/usr/bin/env bash
# Safely publish generated reports when multiple independent Actions share main.
set -euo pipefail

if [[ "$#" -lt 1 || "$#" -gt 2 ]]; then
  echo "Usage: bash scripts/publish-report.sh REPORT_PATH [STATE_PATH]" >&2
  exit 2
fi
report="$1"
state="${2:-}"
for path in "$report" ${state:+"$state"}; do
  if [[ ! -f "$path" ]]; then
    echo "Missing generated file: $path" >&2
    exit 2
  fi
done

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
cp "$report" "$tmpdir/report.md"
if [[ -n "$state" ]]; then cp "$state" "$tmpdir/seen.json"; fi

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

for attempt in 1 2 3 4 5; do
  echo "Publishing report, attempt $attempt"
  # Rebuild a fresh report commit from the current remote head each time.
  # This avoids cherry-pick/rebase text conflicts between concurrent scanners.
  git fetch origin main
  git reset --hard origin/main
  mkdir -p "$(dirname "$report")"
  if [[ -n "$state" ]]; then mkdir -p "$(dirname "$state")"; fi
  cp "$tmpdir/report.md" "$report"

  # Combine remote and this run's seen IDs instead of losing entries.
  if [[ -n "$state" ]]; then
  python3 - "$state" "$tmpdir/seen.json" <<'PY'
import json
import sys
from pathlib import Path

destination, generated = Path(sys.argv[1]), Path(sys.argv[2])
def load(path):
    try:
        values = json.loads(path.read_text(encoding="utf-8"))
        return [v for v in values if isinstance(v, str)] if isinstance(values, list) else []
    except (OSError, ValueError):
        return []
items = list(dict.fromkeys(load(destination) + load(generated)))[-4000:]
destination.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Persisting {len(items)} seen IDs")
PY
  fi

  git add -- "$report"
  if [[ -n "$state" ]]; then git add -- "$state"; fi
  if git diff --cached --quiet; then
    echo "No report changes to save"
    exit 0
  fi
  git commit -m "chore: update wool reports [skip ci]"
  if git push origin HEAD:main; then
    echo "Published successfully"
    exit 0
  fi
  sleep "$((attempt * 3))"
done
echo "Publishing failed after 5 retries" >&2
exit 1
