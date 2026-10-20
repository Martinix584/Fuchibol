"""Load: carga los CSV de GCS a BigQuery (dataset raw), una tabla por archivo.

Usa load jobs (gratis en BigQuery) en vez de streaming inserts. Cada archivo es
una foto completa de la tabla, así que se reemplaza con WRITE_TRUNCATE; el
historial de cambios lo guardan los snapshots de dbt.

Uso local:
    python -m ingestion.load <gcs_uri> <tabla>
    (gcs_uri = gs://<bucket>/raw/transfermarkt/<tabla>/ingest_date=<fecha>/<tabla>.csv.gz)
"""

from __future__ import annotations

import argparse
import json
import logging
import time

from ingestion import config

log = logging.getLogger(__name__)


def raw_table_id(table: str) -> str:
    return f"{config.GCP_PROJECT_ID}.{config.BQ_RAW_DATASET}.{table}"


def load_table(gcs_uri: str, table: str) -> dict:
    from google.cloud import bigquery

    client = bigquery.Client(project=config.GCP_PROJECT_ID, location=config.BQ_LOCATION)
    client.create_dataset(config.BQ_RAW_DATASET, exists_ok=True)

    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        autodetect=True,
        allow_quoted_newlines=True,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )

    started = time.monotonic()
    job = client.load_table_from_uri(gcs_uri, raw_table_id(table), job_config=job_config)
    job.result()

    result = {
        "table": table,
        "rows": job.output_rows,
        "load_seconds": round(time.monotonic() - started, 2),
        "bq_job_id": job.job_id,
    }
    log.info("Cargado %s", result)
    return result


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gcs_uri")
    parser.add_argument("table")
    args = parser.parse_args()
    print(json.dumps(load_table(args.gcs_uri, args.table)))


if __name__ == "__main__":
    main()
