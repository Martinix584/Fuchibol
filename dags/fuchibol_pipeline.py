"""DAG semanal de Fuchibol: dos fuentes en paralelo y después dbt + el modelo de valor de mercado.

Transfermarkt:  tm_check ─► tm_extract[tabla] ─► tm_load[tabla] ─► tm_finish
StatsBomb:      sb_sync_matches ─► sb_ingest[competición-temporada] ─► sb_finish
                                                     │
            any_changes (short-circuit) ─► dbt_build_core ─► train_market_value_model ─► dbt_build_ml

- Cada rama solo procesa lo que cambió (huella de archivo en Transfermarkt, last_updated
  de cada partido en StatsBomb). Los manifests se guardan recién cuando la carga terminó.
- Si ninguna fuente cambió, any_changes corta el DAG y no se gasta nada en BigQuery.
- Con el parámetro force=True se reprocesa todo.
- train_market_value_model entrena con scikit-learn (ingestion/ml.py). La idea era BigQuery ML,
  pero para este proyecto no valía la pena: facturaba más de 20 GB por una tabla de 27 MB.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import Param, dag, task

# dbt corre en su propio virtualenv. Se le saca PYTHONPATH porque el entrypoint de la imagen
# de Airflow le agrega sus librerías (cuando el contenedor corre con otro uid) y dbt terminaría
# importando un protobuf incompatible.
DBT_BIN = "env -u PYTHONPATH /opt/dbt-venv/bin/dbt"
DBT_DIR = "/opt/airflow/dbt"


def dbt_command(args: str) -> str:
    """Corre dbt y sube su run_results.json a ops.dbt_results aunque falle, sin perder el exit code.

    Se borra el run_results.json anterior: si dbt falla antes de escribir uno nuevo, no se
    suben otra vez los resultados de la corrida previa.
    """
    results = f"{DBT_DIR}/target/run_results.json"
    return (
        f"rm -f {results}; cd {DBT_DIR} && {DBT_BIN} {args} --target prod; status=$?; "
        f"if [ -f {results} ]; then cd /opt/airflow && python -m ingestion.metrics dbt "
        f"{results} --run-id '{{{{ run_id }}}}'; fi; "
        "exit $status"
    )


@dag(
    dag_id="fuchibol_pipeline",
    schedule="0 6 * * 1",  # lunes 06:00 UTC
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5)},
    params={
        "force": Param(False, type="boolean", description="Reprocesar todo"),
        "statsbomb_scope": Param(
            None,
            type=["null", "string"],
            description="Alcance de StatsBomb (core, big5_2015, messi, all). Vacío = STATSBOMB_SCOPE",
        ),
    },
    tags=["fuchibol", "transfermarkt", "statsbomb", "bigquery", "dbt"],
    doc_md=__doc__,
)
def fuchibol_pipeline():
    # ------------------------------------------------------------------ Transfermarkt
    @task
    def tm_check(params=None) -> list[str]:
        from ingestion.extract import detect_changes

        return detect_changes(force=params["force"])

    @task(max_active_tis_per_dag=3)
    def tm_extract(table: str, ds=None) -> dict:
        from ingestion.extract import extract_table

        return extract_table(table, ingest_date=ds)

    @task(max_active_tis_per_dag=3)
    def tm_load(extracted: dict) -> dict:
        from ingestion.load import load_table

        return load_table(extracted["gcs_uri"], extracted["table"])

    @task
    def tm_finish(extracts: list[dict], loads: list[dict], run_id=None) -> None:
        from ingestion import extract, metrics

        extracts, loads = list(extracts), list(loads)
        metrics.record_ingestion(run_id, metrics.merge_extract_load(extracts, loads))
        extract.save_manifest({e["table"]: e["fingerprint"] for e in extracts})

    # ------------------------------------------------------------------ StatsBomb
    @task
    def sb_sync_matches(params=None, ds=None, run_id=None) -> list[dict]:
        from ingestion import metrics, statsbomb

        synced = statsbomb.sync_matches(params["statsbomb_scope"], params["force"], ingest_date=ds)
        metrics.record_ingestion(run_id, synced["metrics"])
        return synced["plan"]

    @task(max_active_tis_per_dag=2, execution_timeout=timedelta(hours=2))
    def sb_ingest(item: dict, ds=None) -> dict:
        from ingestion.statsbomb import ingest_batch

        return ingest_batch(item, ingest_date=ds)

    @task
    def sb_finish(batches: list[dict], run_id=None) -> None:
        from ingestion import metrics, statsbomb

        batches = list(batches)
        metrics.record_ingestion(run_id, [m for b in batches for m in b["metrics"]])
        statsbomb.save_manifest(batches)

    # ------------------------------------------------------------------ Gate + dbt
    @task.short_circuit
    def any_changes(tm_tables: list[str], sb_plan: list[dict]) -> bool:
        return bool(tm_tables) or bool(sb_plan)

    dbt_build_core = BashOperator(
        task_id="dbt_build_core",
        bash_command=dbt_command("build --exclude tag:ml --exclude tag:current"),
        trigger_rule="none_failed",  # una rama sin cambios queda "skipped", no frena a dbt
    )
    train_model = BashOperator(
        task_id="train_market_value_model",
        bash_command="cd /opt/airflow && python -m ingestion.ml",
    )
    dbt_build_ml = BashOperator(
        task_id="dbt_build_ml",
        bash_command=dbt_command("build --select tag:ml"),
    )

    tm_tables = tm_check()
    tm_extracts = tm_extract.expand(table=tm_tables)
    tm_loads = tm_load.expand(extracted=tm_extracts)
    tm_done = tm_finish(tm_extracts, tm_loads)

    sb_plan = sb_sync_matches()
    sb_batches = sb_ingest.expand(item=sb_plan)
    sb_done = sb_finish(sb_batches)

    gate = any_changes(tm_tables, sb_plan)
    [gate, tm_done, sb_done] >> dbt_build_core >> train_model >> dbt_build_ml


fuchibol_pipeline()
