"""Exporta los marts y las tablas del modelo a Parquet para la app pública.

Lee de BigQuery con la sesión de ADC y escribe un archivo por tabla:

    PYTHONPATH=. .venv/bin/python scripts/export_parquet.py
    PYTHONPATH=. .venv/bin/python scripts/export_parquet.py --out data/parquet

La app (app/streamlit_app.py) consulta esos Parquet con DuckDB, así no necesita
credenciales de GCP ni hace consultas cada vez que alguien abre una página.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import pyarrow.parquet as pq
from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from ingestion import config


def export_table(
    client: bigquery.Client, project: str, dataset: str, table: str, folder: str, out: Path
) -> int:
    sql = f"select * from `{project}.{dataset}.{table}`"
    arrow = client.query(sql).to_arrow()
    path = out / folder / f"{table}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(arrow, path, compression="zstd")
    return arrow.num_rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    base = os.getenv("DBT_DEV_DATASET", "dev")
    parser.add_argument("--out", default="data/parquet", help="Carpeta de salida")
    parser.add_argument(
        "--datasets",
        default=f"{base}_marts,{base}_ml",
        help="Datasets de BigQuery separados por coma (por defecto, los del target dev)",
    )
    parser.add_argument("--project", default=config.GCP_PROJECT_ID)
    args = parser.parse_args()

    client = bigquery.Client(project=args.project, location=config.BQ_LOCATION)
    out = Path(args.out)
    total = 0
    for dataset in [d.strip() for d in args.datasets.split(",") if d.strip()]:
        folder = dataset.removeprefix(f"{base}_")
        try:
            available = list(client.list_tables(f"{args.project}.{dataset}"))
        except NotFound:
            hint = " (corré `make dbt-train`)" if dataset.endswith("ml") else ""
            print(f"{dataset}: no existe{hint}; se saltea")
            continue
        tables = sorted(
            (table for table in available if "__dbt_tmp" not in table.table_id),
            key=lambda table: table.table_id,
        )
        if not tables:
            print(f"{dataset}: sin tablas")
            continue
        for table in tables:
            rows = export_table(client, args.project, dataset, table.table_id, folder, out)
            total += rows
            print(f"{dataset}.{table.table_id}: {rows:,} filas")
        expected = {f"{table.table_id}.parquet" for table in tables}
        for stale in (out / folder).glob("*.parquet"):
            if stale.name not in expected:
                stale.unlink()
                print(f"  borrado {stale.name} (ya no está en {dataset})")
    print(f"\n{total:,} filas en {out}/")


if __name__ == "__main__":
    main()
