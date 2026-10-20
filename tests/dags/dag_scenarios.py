"""Corre el DAG de punta a punta con dag.test(), simulando la ingesta, en cuatro escenarios.

Verifica las reglas de disparo: si cambió cualquiera de las dos fuentes, dbt corre; si no
cambió nada, se saltea todo. Lo llama scripts/test_dag.sh (necesita Airflow instalado).

    python tests/dags/dag_scenarios.py both|tm_only|sb_only|none
"""

from __future__ import annotations

import logging
import sys

import ingestion.extract as tm_extract
import ingestion.load as tm_load
import ingestion.metrics as metrics
import ingestion.statsbomb as statsbomb

EXPECTED = {
    #           tm_finish   sb_finish   dbt (core, train, ml)
    "both": ("success", "success", "success"),
    "tm_only": ("success", "skipped", "success"),
    "sb_only": ("skipped", "success", "success"),
    "none": ("skipped", "skipped", "skipped"),
}


def main(scenario: str) -> int:
    logging.disable(logging.WARNING)
    tm_tables = ["players", "clubs"] if scenario in ("both", "tm_only") else []
    sb_plan = (
        [{"competition_id": 43, "season_id": 106, "matches": {"1": "2024-01-01"}}]
        if scenario in ("both", "sb_only")
        else []
    )
    saved = {}

    tm_extract.detect_changes = lambda force=False: tm_tables
    tm_extract.extract_table = lambda table, ingest_date=None: {
        "table": table,
        "gcs_uri": "gs://x",
        "bytes": 1,
        "fingerprint": "f",
        "extract_seconds": 0.1,
    }
    tm_extract.save_manifest = lambda updates: saved.setdefault("tm", sorted(updates))
    tm_load.load_table = lambda uri, table: {"table": table, "rows": 10, "load_seconds": 0.1}
    metrics.record_ingestion = lambda run_id, items: None
    statsbomb.sync_matches = lambda scope, force, ingest_date=None: {"plan": sb_plan, "metrics": []}
    statsbomb.ingest_batch = lambda item, ingest_date=None: {"matches": item["matches"], "metrics": []}
    statsbomb.save_manifest = lambda batches: saved.setdefault("sb", len(list(batches)))

    from airflow.models.dagbag import DagBag

    dag = DagBag("dags", include_examples=False).dags["fuchibol_pipeline"]
    for task_id in ("dbt_build_core", "train_market_value_model", "dbt_build_ml"):
        dag.get_task(task_id).bash_command = f"echo {task_id}"
    run = dag.test(use_executor=False)
    states = {ti.task_id: str(ti.state) for ti in run.get_task_instances()}

    tm_state, sb_state, dbt_state = EXPECTED[scenario]
    got = (
        states["tm_finish"],
        states["sb_finish"],
        {states["dbt_build_core"], states["train_market_value_model"], states["dbt_build_ml"]},
    )
    ok = got == (tm_state, sb_state, {dbt_state})
    label = "OK  " if ok else "FAIL"
    print(f"{label} {scenario:<8} tm_finish={got[0]} sb_finish={got[1]} dbt={got[2]} saved={saved}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
