from ingestion.metrics import ingestion_rows, merge_extract_load, parse_run_results

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


def test_merge_extract_load_joins_by_table():
    extracts = [{"table": "players", "bytes": 2048, "extract_seconds": 1.2}]
    loads = [{"table": "players", "rows": 50000, "load_seconds": 3.4}]
    (item,) = merge_extract_load(extracts, loads)
    assert item == {
        "table": "players",
        "rows": 50000,
        "bytes": 2048,
        "extract_seconds": 1.2,
        "load_seconds": 3.4,
    }


def test_ingestion_rows_share_run_id_and_timestamp():
    items = [
        {"table": "players", "rows": 1, "bytes": 2, "extract_seconds": 3.0, "load_seconds": 4.0},
        {
            "table": "statsbomb.events[43/106]",
            "rows": 5,
            "bytes": 6,
            "extract_seconds": None,
            "load_seconds": 7.0,
        },
    ]
    rows = ingestion_rows("run-1", items)
    assert [r["table_name"] for r in rows] == ["players", "statsbomb.events[43/106]"]
    assert {r["run_id"] for r in rows} == {"run-1"}
    assert len({r["recorded_at"] for r in rows}) == 1
