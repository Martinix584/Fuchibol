#!/usr/bin/env bash
# Compila dbt sin credenciales reales y corre el smoke test en DuckDB.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
"$ROOT/scripts/dbt_offline.sh" compile --no-introspect
cd "$ROOT"
python tests/smoke/run_smoke.py --dbt-dir dbt "$@"
