#!/usr/bin/env bash
# Corre dbt sin credenciales reales (para compilar o generar los docs, nunca para build/run).
# dbt-bigquery necesita una service account para arrancar aunque no se conecte:
# se genera una descartable que nunca toca GCP.
#   scripts/dbt_offline.sh compile --no-introspect
#   scripts/dbt_offline.sh docs generate --empty-catalog --static
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

openssl genrsa -out "$TMP/key.pem" 2048 2>/dev/null
python - "$TMP" <<'PY'
import json, sys
tmp = sys.argv[1]
json.dump({
    "type": "service_account", "project_id": "fuchibol-offline", "private_key_id": "offline",
    "private_key": open(f"{tmp}/key.pem").read(),
    "client_email": "offline@fuchibol-offline.iam.gserviceaccount.com", "client_id": "0",
    "token_uri": "https://oauth2.googleapis.com/token",
}, open(f"{tmp}/sa.json", "w"))
PY

cd "$ROOT/dbt"
GOOGLE_APPLICATION_CREDENTIALS="$TMP/sa.json" GCP_PROJECT_ID="${GCP_PROJECT_ID:-fuchibol-offline}" DBT_SEND_ANONYMOUS_USAGE_STATS=false \
  dbt --no-populate-cache "$@" --target prod --profiles-dir . --quiet
