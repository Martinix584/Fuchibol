"""Datos sintéticos de Understat y SofaScore para el smoke test en DuckDB.

No pretende reproducir una temporada completa: alcanza para que los modelos de
temporada actual tengan filas, se ejerciten los joins/uniones y pasen los data tests.
Los nombres y equipos son reales; los números son inventados.
"""

from __future__ import annotations

INGESTED = "2026-10-22T06:00:00+00:00"
OLDER = "2026-10-21T06:00:00+00:00"


def build(con, create_table, tmp) -> None:
    understat_players = [
        {
            "league": "EPL",
            "league_name": "Premier League",
            "season": 2026,
            "season_name": "2026/27",
            "player_id": "8260",
            "player_name": "Erling Haaland",
            "team_title": "Manchester City",
            "position": "F",
            "games": "7",
            "minutes": "621",
            "goals": "8",
            "assists": "0",
            "shots": "27",
            "key_passes": "4",
            "yellow_cards": "0",
            "red_cards": "0",
            "non_penalty_goals": "8",
            "xg": "6.426070660352707",
            "xa": "1.740727722644806",
            "npxg": "6.426070660352707",
            "xg_chain": "9.303837895393372",
            "xg_buildup": "1.8586600590497255",
            "_ingested_at": INGESTED,
        },
        {
            "league": "EPL",
            "league_name": "Premier League",
            "season": 2026,
            "season_name": "2026/27",
            "player_id": "42030",
            "player_name": "Bukayo Saka",
            "team_title": "Arsenal",
            "position": "F M",
            "games": "7",
            "minutes": "540",
            "goals": "3",
            "assists": "4",
            "shots": "18",
            "key_passes": "21",
            "yellow_cards": "1",
            "red_cards": "0",
            "non_penalty_goals": "2",
            "xg": "2.8",
            "xa": "3.4",
            "npxg": "2.1",
            "xg_chain": "6.2",
            "xg_buildup": "1.1",
            "_ingested_at": INGESTED,
        },
        {
            "league": "La_liga",
            "league_name": "La Liga",
            "season": 2026,
            "season_name": "2026/27",
            "player_id": "74214",
            "player_name": "Lamine Yamal",
            "team_title": "Barcelona",
            "position": "F M",
            "games": "6",
            "minutes": "480",
            "goals": "2",
            "assists": "5",
            "shots": "14",
            "key_passes": "24",
            "yellow_cards": "0",
            "red_cards": "0",
            "non_penalty_goals": "2",
            "xg": "2.3",
            "xa": "4.1",
            "npxg": "2.3",
            "xg_chain": "7.1",
            "xg_buildup": "1.9",
            "_ingested_at": INGESTED,
        },
    ]

    def team_match(team_id, team_name, date_, xg, xga, scored, missed, xpts, pts, result):
        return {
            "league": "EPL",
            "league_name": "Premier League",
            "season": 2026,
            "season_name": "2026/27",
            "team_id": team_id,
            "team_title": team_name,
            "match_date": date_,
            "h_a": "h",
            "xg": xg,
            "xga": xga,
            "npxg": xg,
            "npxga": xga,
            "ppda_att": 350,
            "ppda_def": 11,
            "ppda_allowed_att": 120,
            "ppda_allowed_def": 30,
            "deep": 12,
            "deep_allowed": 4,
            "scored": scored,
            "missed": missed,
            "xpts": xpts,
            "result": result,
            "wins": 1 if pts == 3 else 0,
            "draws": 1 if pts == 1 else 0,
            "loses": 1 if pts == 0 else 0,
            "pts": pts,
            "npxgd": round(xg - xga, 3),
            "_ingested_at": INGESTED,
        }

    understat_team_matches = [
        team_match(167, "Manchester City", "2026-08-23 13:00:00", 2.1, 0.8, 2, 1, 2.2, 3, "w"),
        team_match(167, "Manchester City", "2026-08-30 13:00:00", 1.4, 1.1, 1, 1, 1.1, 1, "d"),
        team_match(11, "Arsenal", "2026-08-24 13:00:00", 1.8, 0.9, 2, 0, 2.0, 3, "w"),
        team_match(11, "Arsenal", "2026-08-31 13:00:00", 0.9, 1.2, 0, 1, 0.4, 0, "l"),
    ]

    understat_matches = [
        {
            "league": "EPL",
            "league_name": "Premier League",
            "season": 2026,
            "season_name": "2026/27",
            "match_id": "31180",
            "is_result": True,
            "match_date": "2026-08-23 13:00:00",
            "home_team_id": 167,
            "home_team_title": "Manchester City",
            "home_team_short_title": "MCI",
            "away_team_id": 89,
            "away_team_title": "Manchester United",
            "away_team_short_title": "MUN",
            "home_goals": 2,
            "away_goals": 1,
            "home_xg": 2.1,
            "away_xg": 0.8,
            "forecast_win": 0.7,
            "forecast_draw": 0.2,
            "forecast_loss": 0.1,
            "_ingested_at": INGESTED,
        },
        {
            "league": "EPL",
            "league_name": "Premier League",
            "season": 2026,
            "season_name": "2026/27",
            "match_id": "31181",
            "is_result": True,
            "match_date": "2026-08-24 13:00:00",
            "home_team_id": 11,
            "home_team_title": "Arsenal",
            "home_team_short_title": "ARS",
            "away_team_id": 12,
            "away_team_title": "Brighton",
            "away_team_short_title": "BHA",
            "home_goals": 2,
            "away_goals": 0,
            "home_xg": 1.8,
            "away_xg": 0.9,
            "forecast_win": 0.6,
            "forecast_draw": 0.25,
            "forecast_loss": 0.15,
            "_ingested_at": INGESTED,
        },
    ]

    sofascore_seasons = [
        {
            "league_code": "ARG",
            "league_name": "Liga Profesional Argentina",
            "season_id": 87913,
            "season_name": "Primera LPF 2026",
            "year": "2026",
            "is_selected": True,
            "_ingested_at": INGESTED,
        }
    ]

    def sofa_row(player_id, player_name, team_id, team_name, mode, minutes, xg, xa, ingested):
        return {
            "league_code": "ARG",
            "league_name": "Liga Profesional Argentina",
            "season_id": 87913,
            "season_name": "Primera LPF 2026",
            "season_year": 2026,
            "player_id": player_id,
            "player_name": player_name,
            "team_id": team_id,
            "team_name": team_name,
            "position": "M",
            "source_mode": mode,
            "appearances": 23,
            "minutes": minutes,
            "goals": 3,
            "assists": 4,
            "shots": 30,
            "shots_on_target": 11,
            "key_passes": 40,
            "penalty_goals": 1,
            "yellow_cards": 5,
            "red_cards": 0,
            "rating": 7.2,
            "expected_goals": xg,
            "expected_assists": xa,
            "expected_goals_on_target": 0.5,
            "raw": "{}",
            "_ingested_at": ingested,
        }

    sofascore_players = [
        # fila top vieja: el staging tiene que preferir la full
        sofa_row(255389, "Leandro Paredes", 3202, "Boca Juniors", "top", None, 0.30, 1.0, OLDER),
        sofa_row(255389, "Leandro Paredes", 3202, "Boca Juniors", "full", 1628, 0.3837, 1.1193, INGESTED),
        sofa_row(123456, "Equipo rival", 3203, "River Plate", "full", 1400, 0.9, 0.7, INGESTED),
    ]

    for table, schema, rows in [
        ("players_season", "understat_players_season", understat_players),
        ("team_matches", "understat_team_matches", understat_team_matches),
        ("matches", "understat_matches", understat_matches),
    ]:
        create_table(con, f"raw_understat.{table}", schema, rows, tmp)
    for table, schema, rows in [
        ("seasons", "sofascore_seasons", sofascore_seasons),
        ("player_season", "sofascore_player_season", sofascore_players),
    ]:
        create_table(con, f"raw_sofascore.{table}", schema, rows, tmp)
