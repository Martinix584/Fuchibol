"""Helpers de BigQuery para las fuentes de la temporada actual.

Understat y SofaScore comparten el mismo patrón: NDJSON.gz en GCS + un load job
append-only a BigQuery con un esquema explícito. El staging de dbt se queda con la
última ingesta de cada fila, así que reintentar nunca duplica datos.
"""

from __future__ import annotations

import gzip
import json
import tempfile
import time
from pathlib import Path

from ingestion import config, storage

SCHEMAS_DIR = Path(__file__).parent / "schemas"


def write_ndjson_gz(rows: list[dict], path: str) -> int:
    count = 0
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, default=str))
            f.write("\n")
            count += 1
    return count


def ensure_tables(specs: list[dict]) -> None:
    """Crea (si no existen) el dataset y las tablas raw de una fuente.

    Es importante crearlas aunque todavía no haya datos: dbt referencia los sources
    siempre y así el build no falla cuando SofaScore todavía no se corrió.
    """
    from google.cloud import bigquery

    client = bigquery.Client(project=config.GCP_PROJECT_ID, location=config.BQ_LOCATION)
    for dataset in {spec["dataset"] for spec in specs}:
        client.create_dataset(dataset, exists_ok=True)

    for spec in specs:
        schema = client.schema_from_json(str(SCHEMAS_DIR / f"{spec['schema']}.json"))
        table_id = f"{config.GCP_PROJECT_ID}.{spec['dataset']}.{spec['table']}"
        table = bigquery.Table(table_id, schema=schema)
        table.time_partitioning = bigquery.TimePartitioning(field="_ingested_at")
        if spec.get("cluster_fields"):
            table.clustering_fields = spec["cluster_fields"]
        client.create_table(table, exists_ok=True)


def load_ndjson(
    gcs_uri: str,
    dataset: str,
    table: str,
    schema_name: str,
    cluster_fields: list[str] | None = None,
) -> int:
    from google.cloud import bigquery

    client = bigquery.Client(project=config.GCP_PROJECT_ID, location=config.BQ_LOCATION)
    client.create_dataset(dataset, exists_ok=True)
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        schema=client.schema_from_json(str(SCHEMAS_DIR / f"{schema_name}.json")),
        ignore_unknown_values=True,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        time_partitioning=bigquery.TimePartitioning(field="_ingested_at"),
        clustering_fields=cluster_fields,
    )
    table_id = f"{config.GCP_PROJECT_ID}.{dataset}.{table}"
    job = client.load_table_from_uri(gcs_uri, table_id, job_config=job_config)
    job.result()
    return job.output_rows


def upload_and_load(
    rows: list[dict],
    object_name: str,
    dataset: str,
    table: str,
    schema_name: str,
    cluster_fields: list[str] | None = None,
) -> dict:
    """Sube las filas a GCS y las carga en BigQuery. Devuelve métricas para ops."""
    started = time.monotonic()
    if not rows:
        return {
            "table": f"{dataset}.{table}",
            "rows": 0,
            "bytes": 0,
            "extract_seconds": None,
            "load_seconds": 0.0,
        }

    with tempfile.NamedTemporaryFile(suffix=".ndjson.gz") as tmp:
        count = write_ndjson_gz(rows, tmp.name)
        size = Path(tmp.name).stat().st_size
        uri = storage.upload_file(tmp.name, object_name, "application/gzip")

    loaded = load_ndjson(uri, dataset, table, schema_name, cluster_fields) if count else 0
    return {
        "table": f"{dataset}.{table}",
        "rows": loaded,
        "bytes": size,
        "extract_seconds": None,
        "load_seconds": round(time.monotonic() - started, 2),
    }
