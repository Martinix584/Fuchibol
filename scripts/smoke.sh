#!/usr/bin/env bash
# Compila dbt sin credenciales reales y corre el smoke test en DuckDB.
# dbt-bigquery necesita una service account para arrancar aunque no se conecte:
# se genera una descartable que nunca toca GCP (--no-populate-cache + --no-introspect).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

openssl genrsa -out "$TMP/key.pem" 2048 2>/dev/null
python - "$TMP" <<'PY'
import json, sys
tmp = sys.argv[1]
json.dump({
    "type": "service_account", "project_id": "fuchibol-smoke", "private_key_id": "smoke",
    "private_key": open(f"{tmp}/key.pem").read(),
    "client_email": "smoke@fuchibol-smoke.iam.gserviceaccount.com", "client_id": "0",
    "token_uri": "https://oauth2.googleapis.com/token",
}, open(f"{tmp}/sa.json", "w"))
PY

cd "$ROOT/dbt"
GOOGLE_APPLICATION_CREDENTIALS="$TMP/sa.json" GCP_PROJECT_ID=fuchibol-smoke DBT_SEND_ANONYMOUS_USAGE_STATS=false \
  dbt --no-populate-cache compile --no-introspect --target prod --profiles-dir . --quiet
cd "$ROOT"
python tests/smoke/run_smoke.py --dbt-dir dbt "$@"
