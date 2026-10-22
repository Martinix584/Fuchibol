import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from ingestion import config
from ingestion.understat import (
    default_season,
    gcs_object_name,
    is_fresh,
    parse_league_data,
    resolve_leagues,
    season_name,
)

SCHEMAS = Path(__file__).parents[1] / "ingestion" / "schemas"


@pytest.fixture
def payload():
    return {
        "players": [
            {
                "id": "8260",
                "player_name": "Erling Haaland",
                "games": "7",
                "time": "621",
                "goals": "8",
                "assists": "0",
                "shots": "27",
                "key_passes": "4",
                "yellow_cards": "0",
                "red_cards": "0",
                "position": "F",
                "team_title": "Manchester City",
                "npg": "8",
                "npxG": "6.426070660352707",
                "xG": "6.426070660352707",
                "xA": "1.740727722644806",
                "xGChain": "9.303837895393372",
                "xGBuildup": "1.8586600590497255",
            }
        ],
        "teams": {
            "167": {
                "id": "167",
                "title": "Manchester City",
                "history": [
                    {
                        "h_a": "h",
                        "xG": 2.1,
                        "xGA": 0.8,
                        "npxG": 1.9,
                        "npxGA": 0.8,
                        "ppda": {"att": 350, "def": 11},
                        "ppda_allowed": {"att": 120, "def": 30},
                        "deep": 12,
                        "deep_allowed": 4,
                        "scored": 2,
                        "missed": 1,
                        "xpts": 2.2,
                        "result": "w",
                        "date": "2026-08-23 13:00:00",
                        "wins": 1,
                        "draws": 0,
                        "loses": 0,
                        "pts": 3,
                        "npxGD": 1.1,
                    }
                ],
            }
        },
        "dates": [
            {
                "id": "31180",
                "isResult": True,
                "h": {"id": "167", "title": "Manchester City", "short_title": "MCI"},
                "a": {"id": "89", "title": "Manchester United", "short_title": "MUN"},
                "goals": {"h": "2", "a": "1"},
                "xG": {"h": "2.1", "a": "0.8"},
                "datetime": "2026-08-23 13:00:00",
                "forecast": {"w": "0.7", "d": "0.2", "l": "0.1"},
            }
        ],
    }


def test_default_season_uses_european_calendar():
    assert default_season(date(2026, 10, 22)) == 2026
    assert default_season(date(2026, 6, 1)) == 2025


def test_season_name():
    assert season_name(2026) == "2026/27"


def test_resolve_leagues():
    assert resolve_leagues("EPL,La_liga") == ["EPL", "La_liga"]
    assert resolve_leagues("big5") == list(config.UNDERSTAT_LEAGUES)
    with pytest.raises(ValueError, match="Liga desconocida"):
        resolve_leagues("NOPE")


def test_parse_league_data_players(payload):
    tables = parse_league_data(payload, "EPL", 2026, "2026-10-22T06:00:00+00:00")
    (player,) = tables["players_season"]
    assert player["league"] == "EPL"
    assert player["league_name"] == "Premier League"
    assert player["season"] == 2026
    assert player["season_name"] == "2026/27"
    assert player["player_id"] == "8260"
    assert player["minutes"] == "621"
    assert player["xg"] == "6.426070660352707"
    assert player["xa"] == "1.740727722644806"
    assert player["npxg"] == "6.426070660352707"
    assert player["xg_chain"] == "9.303837895393372"
    assert player["_ingested_at"] == "2026-10-22T06:00:00+00:00"


def test_parse_league_data_team_matches_flattens_ppda(payload):
    tables = parse_league_data(payload, "EPL", 2026, "2026-10-22T06:00:00+00:00")
    (match,) = tables["team_matches"]
    assert match["team_id"] == 167
    assert match["team_title"] == "Manchester City"
    assert match["match_date"] == "2026-08-23 13:00:00"
    assert match["xg"] == 2.1
    assert match["xga"] == 0.8
    assert match["ppda_att"] == 350
    assert match["ppda_def"] == 11
    assert match["ppda_allowed_att"] == 120
    assert match["ppda_allowed_def"] == 30
    assert match["scored"] == 2
    assert match["pts"] == 3
    assert match["npxgd"] == 1.1


def test_parse_league_data_matches(payload):
    tables = parse_league_data(payload, "EPL", 2026, "2026-10-22T06:00:00+00:00")
    (match,) = tables["matches"]
    assert match["match_id"] == "31180"
    assert match["is_result"] is True
    assert match["home_team_id"] == 167
    assert match["away_team_id"] == 89
    assert match["home_goals"] == 2
    assert match["away_goals"] == 1
    assert match["home_xg"] == 2.1
    assert match["forecast_win"] == 0.7


def test_parse_league_data_tolerates_missing_sections():
    tables = parse_league_data({}, "EPL", 2026, "2026-10-22T06:00:00+00:00")
    assert tables == {"players_season": [], "team_matches": [], "matches": []}


def test_gcs_object_name_is_partitioned_by_league_and_season():
    assert gcs_object_name("players_season", "EPL", 2026, "2026-10-22") == (
        "raw/understat/players_season/league=EPL/season=2026/ingest_date=2026-10-22/players_season.ndjson.gz"
    )


def test_is_fresh():
    now = datetime.now(UTC).isoformat()
    old = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
    assert is_fresh({"EPL:2026": {"fetched_at": now}}, "EPL", 2026)
    assert not is_fresh({"EPL:2026": {"fetched_at": old}}, "EPL", 2026)
    assert not is_fresh({}, "EPL", 2026)


def test_schemas_are_valid_and_have_ingested_at():
    for name in ("understat_players_season", "understat_team_matches", "understat_matches"):
        fields = json.loads((SCHEMAS / f"{name}.json").read_text())
        assert {field["name"] for field in fields} >= {"_ingested_at"}
        assert all(
            field["type"] in {"STRING", "INTEGER", "FLOAT", "BOOLEAN", "TIMESTAMP"} for field in fields
        )


def test_main_records_ingestion_metrics(monkeypatch):
    from ingestion import current_season, metrics, understat

    loaded = [{"table": "raw_understat.matches", "rows": 3}]
    recorded = []
    monkeypatch.setattr("sys.argv", ["understat", "--leagues", "EPL"])
    monkeypatch.setattr(current_season, "ensure_tables", lambda: None)
    monkeypatch.setattr(understat, "ingest_all", lambda *a, **k: loaded)
    monkeypatch.setattr(metrics, "record_ingestion", lambda run_id, items: recorded.append((run_id, items)))
    understat.main()
    assert recorded and recorded[0][0].startswith("manual__") and recorded[0][1] == loaded
