from ingestion.metrics import ingestion_rows, parse_run_results

RUN_RESULTS = {
    "metadata": {"invocation_id": "inv-1", "generated_at": "2026-10-20T06:10:00Z"},
    "args": {"which": "build"},
    "results": [
        {
            "unique_id": "model.fuchibol.mart_transfer_roi",
            "status": "success",
            "execution_time": 4.21234,
            "adapter_response": {"rows_affected": 52000, "bytes_processed": 120000000},
            "failures": None,
        },
        {
            "unique_id": "test.fuchibol.unique_dim_players_player_id.abc123",
            "status": "pass",
            "execution_time": 1.5,
            "adapter_response": {},
            "failures": 0,
        },
    ],
}


def test_parse_run_results_flattens_each_node():
    rows = parse_run_results(RUN_RESULTS, run_id="scheduled__2026-10-20")
    assert len(rows) == 2
    model, test = rows
    assert model["resource_type"] == "model"
    assert model["rows_affected"] == 52000
    assert model["execution_seconds"] == 4.212
    assert model["command"] == "build"
    assert test["resource_type"] == "test"
    assert test["failures"] == 0
    assert test["bytes_processed"] is None


def test_ingestion_rows_joins_extract_and_load_by_table():
    extracts = [{"table": "players", "bytes": 2048, "extract_seconds": 1.2}]
    loads = [{"table": "players", "rows": 50000, "load_seconds": 3.4}]
    (row,) = ingestion_rows("run-1", extracts, loads)
    assert row["table_name"] == "players"
    assert row["rows"] == 50000
    assert row["bytes"] == 2048
    assert row["load_seconds"] == 3.4
