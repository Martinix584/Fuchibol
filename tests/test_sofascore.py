import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ingestion import config
from ingestion.sofascore import (
    SofaScoreBlocked,
    SofaScoreClient,
    SofaScoreNotFound,
    gcs_object_name,
    is_fresh,
    manifest_key,
    mode_for,
    parse_number,
    parse_season_year,
    player_stats_row,
    resolve_scope,
    roster_players,
    season_rows,
    season_teams,
    select_season,
    top_players_rows,
)

SCHEMAS = Path(__file__).parents[1] / "ingestion" / "schemas"


@pytest.fixture
def season():
    return {"id": 87913, "name": "Primera LPF 2026", "year": "2026"}


@pytest.fixture
def top_payload():
    player = {"id": 255389, "name": "Leandro Paredes", "position": "M"}
    team = {"id": 3202, "name": "Boca Juniors"}
    stats = {"appearances": 23}
    payload = {"topPlayers": {}}
    for category, value in {
        "rating": 7.2,
        "goals": 3,
        "expectedGoals": 0.3837,
        "assists": 4,
        "expectedAssists": 1.1193,
        "totalShots": 30,
        "shotsOnTarget": 11,
        "keyPasses": 40,
        "penaltyGoals": 1,
        "yellowCards": 5,
        "redCards": 0,
    }.items():
        payload["topPlayers"][category] = [
            {
                "player": player,
                "team": team,
                "statistics": {**stats, category: value},
            }
        ]
    return payload


def test_resolve_scope():
    assert resolve_scope("ARG") == ["ARG"]
    assert resolve_scope("big5") == ["EPL", "La_liga", "Serie_A", "Bundesliga", "Ligue_1"]
    assert resolve_scope("all") == list(config.SOFASCORE_TOURNAMENTS)
    with pytest.raises(ValueError, match="Torneo desconocido"):
        resolve_scope("NOPE")


def test_mode_for_defaults():
    assert mode_for("ARG") == "full"
    assert mode_for("EPL") == "full"
    assert mode_for("EPL", "top") == "top"
    with pytest.raises(ValueError, match="Modo desconocido"):
        mode_for("ARG", "nope")


def test_select_season_latest_by_year_and_id():
    payload = {
        "seasons": [
            {"id": 1, "name": "2025", "year": "2025"},
            {"id": 3, "name": "2026 Clausura", "year": "2026"},
            {"id": 2, "name": "2026 Apertura", "year": "2026"},
        ]
    }
    assert select_season(payload)["id"] == 3
    assert select_season(payload, "2025")["id"] == 1
    assert select_season(payload, "2")["id"] == 2


def test_select_season_rejects_unknown():
    with pytest.raises(ValueError, match="No encontré"):
        select_season({"seasons": [{"id": 1, "year": "2025"}]}, "2026")


def test_season_rows_marks_selected(season):
    payload = {"seasons": [season, {"id": 1, "name": "2025", "year": "2025"}]}
    rows = season_rows(payload, "ARG", "Liga Profesional Argentina", 87913, "2026-10-22T06:00:00+00:00")
    assert rows[0]["league_code"] == "ARG"
    assert rows[0]["season_id"] == 87913
    assert rows[0]["season_name"] == "Primera LPF 2026"
    assert rows[0]["year"] == "2026"
    assert rows[0]["is_selected"] is True
    assert rows[1]["is_selected"] is False


def test_season_teams_supports_flat_and_grouped_payloads():
    flat = {
        "teams": [
            {"id": 3202, "name": "Boca Juniors"},
            {"team": {"id": 3203, "name": "River Plate"}},
        ]
    }
    grouped = {"groups": [{"teams": [{"id": 3202, "name": "Boca Juniors"}]}]}
    assert season_teams(flat) == [
        {"team_id": 3202, "team_name": "Boca Juniors"},
        {"team_id": 3203, "team_name": "River Plate"},
    ]
    assert season_teams(grouped) == [{"team_id": 3202, "team_name": "Boca Juniors"}]
    assert season_teams({}) == []


def test_roster_players_returns_base_rows():
    payload = {
        "players": [
            {
                "player": {"id": 255389, "name": "Leandro Paredes", "position": "M"},
                "team": {"id": 3202, "name": "Boca Juniors"},
                "statistics": {"appearances": 23},
            },
            {"player": {"id": 123456, "name": "Otro Jugador", "position": "F"}},
        ]
    }
    rows = roster_players(payload, 3202, "Boca Juniors")
    assert rows == [
        {
            "player_id": 255389,
            "player_name": "Leandro Paredes",
            "team_id": 3202,
            "team_name": "Boca Juniors",
            "position": "M",
            "appearances": 23,
        },
        {
            "player_id": 123456,
            "player_name": "Otro Jugador",
            "team_id": 3202,
            "team_name": "Boca Juniors",
            "position": "F",
            "appearances": None,
        },
    ]


def test_top_players_rows_merges_categories(top_payload, season):
    (row,) = top_players_rows(
        top_payload, "ARG", "Liga Profesional Argentina", season, "2026-10-22T06:00:00+00:00"
    )
    assert row["player_id"] == 255389
    assert row["player_name"] == "Leandro Paredes"
    assert row["team_id"] == 3202
    assert row["team_name"] == "Boca Juniors"
    assert row["season_id"] == 87913
    assert row["season_year"] == 2026
    assert row["source_mode"] == "top"
    assert row["appearances"] == 23
    assert row["minutes"] is None
    assert row["goals"] == 3
    assert row["assists"] == 4
    assert row["shots"] == 30
    assert row["shots_on_target"] == 11
    assert row["key_passes"] == 40
    assert row["penalty_goals"] == 1
    assert row["yellow_cards"] == 5
    assert row["red_cards"] == 0
    assert row["rating"] == 7.2
    assert row["expected_goals"] == 0.3837
    assert row["expected_assists"] == 1.1193
    assert json.loads(row["raw"])["expectedGoals"] == 0.3837


def test_top_players_rows_tolerates_empty_payload(season):
    assert top_players_rows({}, "ARG", "Liga", season, "2026-10-22T06:00:00+00:00") == []


def test_player_stats_row_overrides_top_with_full(top_payload, season):
    (top_row,) = top_players_rows(
        top_payload, "ARG", "Liga Profesional Argentina", season, "2026-10-22T06:00:00+00:00"
    )
    payload = {
        "statistics": {
            "minutesPlayed": 1628,
            "goals": 3,
            "assists": 4,
            "totalShots": 31,
            "shotsOnTarget": 12,
            "keyPasses": 41,
            "penaltyGoals": 1,
            "yellowCards": 5,
            "redCards": 0,
            "rating": 7.31,
            "expectedGoals": 0.41,
            "expectedAssists": 1.2,
            "expectedGoalsOnTarget": 0.5,
        }
    }
    row = player_stats_row(
        payload, "ARG", "Liga Profesional Argentina", season, top_row, "2026-10-22T06:05:00+00:00"
    )
    assert row["source_mode"] == "full"
    assert row["minutes"] == 1628
    assert row["appearances"] == 23  # se conserva del top
    assert row["expected_goals"] == 0.41
    assert row["expected_assists"] == 1.2
    assert row["shots"] == 31
    assert row["key_passes"] == 41
    assert row["expected_goals_on_target"] == 0.5


def test_player_stats_row_keeps_top_values_when_full_omits_them(top_payload, season):
    (top_row,) = top_players_rows(
        top_payload, "ARG", "Liga Profesional Argentina", season, "2026-10-22T06:00:00+00:00"
    )
    row = player_stats_row(
        {"statistics": {"minutesPlayed": 1628}},
        "ARG",
        "Liga Profesional Argentina",
        season,
        top_row,
        "2026-10-22T06:05:00+00:00",
    )
    assert row["minutes"] == 1628
    assert row["expected_goals"] == 0.3837
    assert row["expected_assists"] == 1.1193
    assert row["goals"] == 3
    assert row["appearances"] == 23


def test_parse_number():
    assert parse_number("3") == 3.0
    assert parse_number("3", int) == 3
    assert parse_number(None) is None
    assert parse_number("x") is None


def test_gcs_object_name_is_partitioned():
    assert gcs_object_name("player_season", "ARG", 87913, "2026-10-22", "top") == (
        "raw/sofascore/player_season/league=ARG/season_id=87913/ingest_date=2026-10-22/"
        "part=top/player_season.ndjson.gz"
    )


def test_manifest_key_and_freshness():
    assert manifest_key("ARG", 87913, 255389) == "ARG:87913:255389"
    now = datetime.now(UTC).isoformat()
    old = (datetime.now(UTC) - timedelta(hours=48)).isoformat()
    assert is_fresh({"players": {"ARG:87913:1": {"fetched_at": now}}}, "ARG:87913:1")
    assert not is_fresh({"players": {"ARG:87913:1": {"fetched_at": old}}}, "ARG:87913:1")
    assert not is_fresh({}, "ARG:87913:1")


def test_schemas_are_valid_and_have_ingested_at():
    for name in ("sofascore_seasons", "sofascore_player_season"):
        fields = json.loads((SCHEMAS / f"{name}.json").read_text())
        assert {field["name"] for field in fields} >= {"_ingested_at"}
        assert all(
            field["type"] in {"STRING", "INTEGER", "FLOAT", "BOOLEAN", "TIMESTAMP"} for field in fields
        )


class FakePage:
    """Reemplaza el navegador: devuelve una respuesta fija y anota la URL pedida."""

    def __init__(self, result):
        self.result = result
        self.paths = []

    def evaluate(self, script, path):
        self.paths.append(path)
        return self.result


def test_fetch_raw_prefixes_api_v1():
    client = SofaScoreClient()
    client._page = FakePage({"status": 200, "body": '{"seasons": []}'})
    assert client._fetch_raw("/unique-tournament/155/seasons") == {"seasons": []}
    assert client._page.paths == ["/api/v1/unique-tournament/155/seasons"]


def test_fetch_raw_does_not_double_prefix_api_v1():
    client = SofaScoreClient()
    client._page = FakePage({"status": 200, "body": "{}"})
    client._fetch_raw("/api/v1/unique-tournament/155/seasons")
    assert client._page.paths == ["/api/v1/unique-tournament/155/seasons"]


def test_fetch_raw_404_is_not_found_not_challenge():
    client = SofaScoreClient()
    client._page = FakePage({"status": 404, "body": '{"error": {"code": 404}}'})
    with pytest.raises(SofaScoreNotFound):
        client._fetch_raw("/player/1/unique-tournament/155/season/87913/statistics/overall")


def test_fetch_raw_html_is_still_a_challenge():
    client = SofaScoreClient()
    client._page = FakePage({"status": 200, "body": "<!DOCTYPE html><html>challenge</html>"})
    with pytest.raises(SofaScoreBlocked):
        client._fetch_raw("/unique-tournament/155/seasons")


@pytest.mark.parametrize(
    ("value", "name", "expected"),
    [
        ("2026", None, 2026),
        (2026, None, 2026),
        ("26/27", "Premier League 26/27", 2026),
        (None, "LaLiga 26/27", 2026),
        ("2026/27", None, 2026),
        ("99/00", None, 1999),
        (None, "Torneo sin año", None),
    ],
)
def test_parse_season_year(value, name, expected):
    assert parse_season_year(value, name) == expected


def test_fetch_raw_timeout_is_a_challenge():
    class TimeoutPage:
        def evaluate(self, script, path):
            raise RuntimeError("Page.evaluate: AbortError: signal is aborted without reason")

    client = SofaScoreClient()
    client._page = TimeoutPage()
    with pytest.raises(SofaScoreBlocked):
        client._fetch_raw("/unique-tournament/155/seasons")


def test_fetch_raw_context_destroyed_is_a_challenge():
    class NavigatedPage:
        def evaluate(self, script, path):
            raise RuntimeError(
                "Page.evaluate: Execution context was destroyed, most likely because of a navigation"
            )

    client = SofaScoreClient()
    client._page = NavigatedPage()
    with pytest.raises(SofaScoreBlocked):
        client._fetch_raw("/unique-tournament/155/seasons")


def test_main_records_ingestion_metrics(monkeypatch):
    from ingestion import metrics, sofascore

    loaded = [{"table": "raw_sofascore.player_season[ARG/1]", "rows": 25}]
    recorded = []
    monkeypatch.setattr("sys.argv", ["sofascore", "--scope", "ARG"])
    monkeypatch.setattr(sofascore, "ensure_tables", lambda: None)
    monkeypatch.setattr(sofascore, "ingest_all", lambda *a, **k: loaded)
    monkeypatch.setattr(metrics, "record_ingestion", lambda run_id, items: recorded.append((run_id, items)))
    sofascore.main()
    assert recorded and recorded[0][0].startswith("manual__") and recorded[0][1] == loaded


def test_fetch_events_reuses_one_session_and_skips_missing(monkeypatch):
    from ingestion import sofascore

    opened = []

    class FakeClient:
        def __init__(self, headless=True):
            opened.append(self)
            self.paths = []

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.closed = True

        def get(self, path):
            self.paths.append(path)
            if path == "/event/2":
                raise SofaScoreNotFound(path)
            return {"path": path}

    monkeypatch.setattr(sofascore, "SofaScoreClient", FakeClient)
    out = list(sofascore.fetch_events([1, 2, 1, 3]))
    assert [e for e, _ in out] == [1, 3]
    assert len(opened) == 1 and opened[0].closed
    assert opened[0].paths == ["/event/1", "/event/2", "/event/3"]

    shared = FakeClient()
    list(sofascore.fetch_events([4], client=shared))
    assert len(opened) == 2 and not hasattr(shared, "closed")
