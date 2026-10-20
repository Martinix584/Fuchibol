import json
from pathlib import Path

import pytest

from ingestion import config
from ingestion.statsbomb import (
    batch_prefix,
    build_plan,
    changed_matches,
    lineup_rows,
    resolve_scope,
    with_metadata,
)

COMPETITIONS = [
    {"competition_id": 43, "season_id": 106, "competition_gender": "male"},
    {"competition_id": 43, "season_id": 3, "competition_gender": "male"},
    {"competition_id": 72, "season_id": 107, "competition_gender": "female"},
]


def test_resolve_scope_named_scope_keeps_only_available_pairs(monkeypatch):
    monkeypatch.setitem(config.STATSBOMB_SCOPES, "test", [(43, 106), (999, 1)])
    assert resolve_scope("test", COMPETITIONS) == [(43, 106)]


def test_resolve_scope_all_is_men_only_and_deduplicated(monkeypatch):
    monkeypatch.setitem(config.STATSBOMB_SCOPES, "test", [(43, 106)])
    assert resolve_scope("all,test", COMPETITIONS) == [(43, 3), (43, 106)]


def test_resolve_scope_rejects_unknown_scope():
    with pytest.raises(ValueError, match="Alcance desconocido"):
        resolve_scope("nope", COMPETITIONS)


def test_default_scopes_are_valid_pairs():
    for pairs in config.STATSBOMB_SCOPES.values():
        assert pairs and all(isinstance(c, int) and isinstance(s, int) for c, s in pairs)


def test_changed_matches_new_and_updated_only():
    matches = [
        {"match_id": 1, "last_updated": "2024-01-01"},
        {"match_id": 2, "last_updated": "2024-02-01"},
        {"match_id": 3, "last_updated": "2024-03-01"},
    ]
    manifest = {"1": "2024-01-01", "2": "2023-12-31"}
    assert [m["match_id"] for m in changed_matches(matches, manifest)] == [2, 3]


def test_build_plan_skips_pairs_without_changes():
    by_pair = {
        (43, 106): [{"match_id": 1, "last_updated": "a"}],
        (43, 3): [{"match_id": 2, "last_updated": "b"}],
    }
    plan = build_plan(by_pair, {"1": "a"})
    assert plan == [{"competition_id": 43, "season_id": 3, "matches": {"2": "b"}}]


def test_with_metadata_adds_match_id_and_timestamp():
    rows = with_metadata([{"id": "e1"}], "2026-10-20T00:00:00Z", match_id=7)
    assert rows == [{"match_id": 7, "id": "e1", "_ingested_at": "2026-10-20T00:00:00Z"}]


def test_lineup_rows_one_row_per_team():
    lineups = [
        {"team_id": 1, "team_name": "A", "lineup": [{"player_id": 10}]},
        {"team_id": 2, "team_name": "B", "lineup": []},
    ]
    rows = lineup_rows(5, lineups, "ts")
    assert [(r["match_id"], r["team_id"], len(r["lineup"])) for r in rows] == [(5, 1, 1), (5, 2, 0)]


def test_batch_prefix_is_partitioned():
    assert batch_prefix("events", 43, 106, "2026-10-20") == (
        "raw/statsbomb/events/competition_id=43/season_id=106/ingest_date=2026-10-20/events.ndjson.gz"
    )


@pytest.mark.parametrize("name", ["events", "lineups", "matches", "competitions"])
def test_bigquery_schemas_are_valid_json_with_ingestion_timestamp(name):
    fields = json.loads((Path(config.__file__).parent / "schemas" / f"statsbomb_{name}.json").read_text())
    assert any(f["name"] == "_ingested_at" and f["type"] == "TIMESTAMP" for f in fields)
    names = [f["name"] for f in fields]
    assert len(names) == len(set(names))
