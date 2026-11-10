#!/usr/bin/env bash
# Build a self-contained agent-redteam.pyz zipapp.
# The mock target and all 5 defense layers run fully offline inside the pyz.
# Note: --config and data/attack_vectors.json resolve from the CWD, so for
# custom configs run from a checkout (or pass --config explicitly).
set -euo pipefail
cd "$(dirname "$0")/.."
OUT="${1:-agent-redteam.pyz}"
STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT
for d in attacks defenses aggregators memory metrics orchestrator targets configs data scripts demo storage; do
  cp -r "$d" "$STAGING/"
done
cp requirements.txt requirements.lock "$STAGING/" 2>/dev/null || true
cat > "$STAGING/__main__.py" <<'PY'
from scripts.run_redteam import main

raise SystemExit(main())
PY
python3 -m zipapp "$STAGING" -p "/usr/bin/env python3" -o "$OUT"
echo "built: $OUT ($(wc -c < "$OUT") bytes)"
