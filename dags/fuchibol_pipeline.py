"""DAG semanal de Fuchibol.

check_updates ─► extract (mapeado por tabla) ─► load (mapeado) ─► record_ingestion ─► save_manifest
                                                                                         │
                       dbt_build_core ─► train_market_value_model ─► dbt_build_ml ◄──────┘

Si ningún archivo cambió desde la última corrida, check_updates corta el DAG
(short-circuit) y no se gasta nada en BigQuery. Con el parámetro force=True se
reprocesa todo igual.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import Param, dag, task

DBT_BIN = "/opt/dbt-venv/bin/dbt"
DBT_DIR = "/opt/airflow/dbt"


def dbt_command(args: str) -> str:
    """Corre dbt y sube su run_results.json a ops.dbt_results aunque falle, sin perder el exit code."""
    return (
        f"cd {DBT_DIR} && {DBT_BIN} {args} --target prod; status=$?; "
        "cd /opt/airflow && python -m ingestion.metrics dbt "
        f"{DBT_DIR}/target/run_results.json --run-id '{{{{ run_id }}}}'; "
        "exit $status"
    )


@dag(
    dag_id="fuchibol_pipeline",
    schedule="0 6 * * 1",  # lunes 06:00 UTC
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5)},
    params={"force": Param(False, type="boolean", description="Reprocesar todas las tablas")},
    tags=["fuchibol", "transfermarkt", "bigquery", "dbt"],
    doc_md=__doc__,
)
def fuchibol_pipeline():
    @task.short_circuit
    def check_updates(params=None) -> list[str]:
        from ingestion.extract import detect_changes

        return detect_changes(force=params["force"])

    @task(max_active_tis_per_dag=3)
    def extract(table: str, ds=None) -> dict:
        from ingestion.extract import extract_table

        return extract_table(table, ingest_date=ds)

    @task(max_active_tis_per_dag=3)
    def load(extracted: dict) -> dict:
        from ingestion.load import load_table

        return load_table(extracted["gcs_uri"], extracted["table"])

    @task
    def record_ingestion(extracts: list[dict], loads: list[dict], run_id=None) -> None:
        from ingestion.metrics import record_ingestion as record

        record(run_id, list(extracts), list(loads))

    @task
    def save_manifest(extracts: list[dict]) -> None:
        """Se guarda al final: si un load falla, la próxima corrida vuelve a intentar esa tabla."""
        from ingestion.extract import save_manifest as save

        save({e["table"]: e["fingerprint"] for e in extracts})

    dbt_build_core = BashOperator(
        task_id="dbt_build_core",
        bash_command=dbt_command("build --exclude tag:ml"),
    )
    train_model = BashOperator(
        task_id="train_market_value_model",
        bash_command=f"cd {DBT_DIR} && {DBT_BIN} run-operation train_market_value_model --target prod",
    )
    dbt_build_ml = BashOperator(
        task_id="dbt_build_ml",
        bash_command=dbt_command("build --select tag:ml"),
    )

    tables = check_updates()
    extracts = extract.expand(table=tables)
    loads = load.expand(extracted=extracts)
    recorded = record_ingestion(extracts, loads)
    saved = save_manifest(extracts)

    loads >> recorded >> saved >> dbt_build_core >> train_model >> dbt_build_ml


fuchibol_pipeline()
