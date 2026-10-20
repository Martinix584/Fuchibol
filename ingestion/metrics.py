"""Métricas del pipeline: volumen, tiempos y resultados de tests.

Se guardan en BigQuery (dataset ops) para mostrarlas en el README y en la
página "Salud del pipeline" de Power BI.

    ops.pipeline_runs  -> una fila por tabla ingerida (filas, bytes, segundos)
    ops.dbt_results    -> una fila por modelo/test/snapshot de cada corrida de dbt

Uso desde la línea de comandos (lo llama el DAG después de cada comando dbt):
    python -m ingestion.metrics dbt dbt/target/run_results.json --run-id manual
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import UTC, datetime

from ingestion import config

log = logging.getLogger(__name__)

PIPELINE_RUNS_SCHEMA = [
    ("run_id", "STRING"),
    ("recorded_at", "TIMESTAMP"),
    ("table_name", "STRING"),
    ("rows", "INT64"),
    ("bytes", "INT64"),
    ("extract_seconds", "FLOAT64"),
    ("load_seconds", "FLOAT64"),
]

DBT_RESULTS_SCHEMA = [
    ("run_id", "STRING"),
    ("invocation_id", "STRING"),
    ("command", "STRING"),
    ("generated_at", "TIMESTAMP"),
    ("unique_id", "STRING"),
    ("resource_type", "STRING"),
    ("status", "STRING"),
    ("execution_seconds", "FLOAT64"),
    ("rows_affected", "INT64"),
    ("bytes_processed", "INT64"),
    ("failures", "INT64"),
]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def ingestion_rows(run_id: str, extracts: list[dict], loads: list[dict]) -> list[dict]:
    """Une las métricas de extract y load por tabla."""
    loads_by_table = {r["table"]: r for r in loads}
    rows = []
    for e in extracts:
        load = loads_by_table.get(e["table"], {})
        rows.append(
            {
                "run_id": run_id,
                "recorded_at": _now(),
                "table_name": e["table"],
                "rows": load.get("rows"),
                "bytes": e.get("bytes"),
                "extract_seconds": e.get("extract_seconds"),
                "load_seconds": load.get("load_seconds"),
            }
        )
    return rows


def parse_run_results(run_results: dict, run_id: str) -> list[dict]:
    """Aplana el run_results.json de dbt a filas para ops.dbt_results."""
    meta = run_results.get("metadata", {})
    command = run_results.get("args", {}).get("which")
    rows = []
    for r in run_results.get("results", []):
        adapter = r.get("adapter_response") or {}
        rows.append(
            {
                "run_id": run_id,
                "invocation_id": meta.get("invocation_id"),
                "command": command,
                "generated_at": meta.get("generated_at"),
                "unique_id": r["unique_id"],
                "resource_type": r["unique_id"].split(".")[0],
                "status": r.get("status"),
                "execution_seconds": round(r.get("execution_time") or 0.0, 3),
                "rows_affected": adapter.get("rows_affected"),
                "bytes_processed": adapter.get("bytes_processed"),
                "failures": r.get("failures"),
            }
        )
    return rows


def write_rows(table: str, rows: list[dict], schema: list[tuple[str, str]]) -> None:
    """Append con un load job (gratis), no con streaming inserts."""
    if not rows:
        return
    from google.cloud import bigquery

    client = bigquery.Client(project=config.GCP_PROJECT_ID, location=config.BQ_LOCATION)
    client.create_dataset(config.BQ_OPS_DATASET, exists_ok=True)
    job_config = bigquery.LoadJobConfig(
        schema=[bigquery.SchemaField(name, type_) for name, type_ in schema],
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
    )
    table_id = f"{config.GCP_PROJECT_ID}.{config.BQ_OPS_DATASET}.{table}"
    client.load_table_from_json(rows, table_id, job_config=job_config).result()
    log.info("Escritas %d filas en %s", len(rows), table_id)


def record_ingestion(run_id: str, extracts: list[dict], loads: list[dict]) -> None:
    write_rows("pipeline_runs", ingestion_rows(run_id, extracts, loads), PIPELINE_RUNS_SCHEMA)


def record_dbt(run_results_path: str, run_id: str) -> None:
    with open(run_results_path) as f:
        rows = parse_run_results(json.load(f), run_id)
    write_rows("dbt_results", rows, DBT_RESULTS_SCHEMA)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="kind", required=True)
    dbt = sub.add_parser("dbt", help="Sube un run_results.json de dbt a ops.dbt_results")
    dbt.add_argument("run_results_path")
    dbt.add_argument("--run-id", default="manual")
    args = parser.parse_args()

    if args.kind == "dbt":
        record_dbt(args.run_results_path, args.run_id)


if __name__ == "__main__":
    main()
