"""DAG diario de la temporada actual: Understat -> dbt current.

Understat es la fuente automática de xG/xA de las 5 grandes ligas. SofaScore queda
afuera a propósito: no tiene API pública, sus términos prohíben el scraping y se corre
local/manual (ver docs/runbooks/xg-manual-fallback.md). La rama de Argentina se
construye con las tablas vacías si SofaScore todavía no se corrió.

Understat también crea (si no existen) las tablas raw de SofaScore, así dbt puede
referenciar ambos sources sin fallar. Después corre `dbt build --select tag:current+`.

El DAG semanal `fuchibol_pipeline` excluye `tag:current` para no pisar estos marts.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import Param, dag, task

# Igual que en fuchibol_pipeline: dbt vive en su propio virtualenv y hay que sacarle
# PYTHONPATH para que no importe el protobuf de Airflow.
DBT_BIN = "env -u PYTHONPATH /opt/dbt-venv/bin/dbt"
DBT_DIR = "/opt/airflow/dbt"


def dbt_command(args: str) -> str:
    """Corre dbt y sube run_results.json a ops.dbt_results aunque falle."""
    results = f"{DBT_DIR}/target/run_results.json"
    return (
        f"rm -f {results}; cd {DBT_DIR} && {DBT_BIN} {args} --target prod; status=$?; "
        f"if [ -f {results} ]; then cd /opt/airflow && python -m ingestion.metrics dbt "
        f"{results} --run-id '{{{{ run_id }}}}'; fi; exit $status"
    )


@dag(
    dag_id="fuchibol_current_season",
    description="Temporada actual: Understat (5 grandes) + dbt current (incluye SofaScore Argentina)",
    schedule="0 7 * * *",  # todos los días a las 07:00 UTC
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=10)},
    params={
        "force": Param(False, type="boolean", description="Ignorar el manifest de Understat"),
        "season": Param(
            None,
            type=["null", "integer"],
            description="Año de inicio de la temporada (2026 = 2026/27). Vacío = automático",
        ),
    },
    tags=["fuchibol", "current", "understat", "bigquery", "dbt"],
    doc_md=__doc__,
)
def fuchibol_current_season():
    @task
    def current_ensure_tables() -> None:
        from ingestion.current_season import ensure_tables

        ensure_tables()

    @task(execution_timeout=timedelta(minutes=20))
    def understat_fetch(params=None, ds=None, run_id=None) -> list[dict]:
        from ingestion import metrics, understat

        params = params or {}
        results = understat.ingest_all(
            season=params.get("season"),
            force=bool(params.get("force")),
            ingest_date=ds,
        )
        metrics.record_ingestion(run_id, results)
        return results

    dbt_build_current = BashOperator(
        task_id="dbt_build_current",
        bash_command=dbt_command("build --select tag:current+"),
        execution_timeout=timedelta(minutes=60),
    )

    current_ensure_tables() >> understat_fetch() >> dbt_build_current


fuchibol_current_season()
