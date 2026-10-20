#!/usr/bin/env bash
# Prueba el DAG con dag.test() en una base de Airflow descartable (SQLite).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export AIRFLOW_HOME="$(mktemp -d)"
trap 'rm -rf "$AIRFLOW_HOME"' EXIT
export AIRFLOW__CORE__LOAD_EXAMPLES=false
export AIRFLOW__CORE__DAGS_FOLDER="$ROOT/dags"
export PYTHONPATH="$ROOT"
cd "$ROOT"

airflow db migrate > /dev/null
airflow dags reserialize > /dev/null
python -c "
from airflow.models.dagbag import DagBag
bag = DagBag('dags', include_examples=False)
assert not bag.import_errors, bag.import_errors
print('DAG importado sin errores:', list(bag.dags))
"
status=0
for scenario in both tm_only sb_only none; do
  if ! output="$(python tests/dags/dag_scenarios.py "$scenario" 2>&1)"; then status=1; fi
  echo "$output" | grep -E '^(OK|FAIL)' || { echo "$output" | tail -20; status=1; }
done
exit $status
