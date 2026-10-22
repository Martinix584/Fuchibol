"""Ingesta de Understat: xG, xA, npxG, xGChain y xGBuildup de la temporada actual.

Understat no tiene API documentada, pero la página de liga pide un JSON a
`/getLeagueData/{league}/{season}`. Ese endpoint devuelve, en una sola request:

  - players: una fila por jugador con xG, xA, npxG, xGChain y xGBuildup.
  - teams: una fila por equipo con `history` (un partido por fecha) y xPts.
  - dates: los partidos con goles y xG de cada lado.

La respuesta trae los números como strings; se guardan así en raw y el staging de
dbt los castea con SAFE_CAST. Es la fuente automática de xG para las 5 grandes ligas
(no cubre Argentina). Se corre a diario desde Airflow.

Uso local:
    python -m ingestion.understat                       # big5, temporada en curso
    python -m ingestion.understat --leagues EPL,La_liga
    python -m ingestion.understat --season 2025 --force
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import UTC, date, datetime, timedelta

import requests

from ingestion import bq, config, storage

log = logging.getLogger(__name__)

TABLE_SPECS = [
    {
        "dataset": config.BQ_UNDERSTAT_DATASET,
        "table": "players_season",
        "schema": "understat_players_season",
        "cluster_fields": ["league", "season"],
    },
    {
        "dataset": config.BQ_UNDERSTAT_DATASET,
        "table": "team_matches",
        "schema": "understat_team_matches",
        "cluster_fields": ["league", "season", "team_id"],
    },
    {
        "dataset": config.BQ_UNDERSTAT_DATASET,
        "table": "matches",
        "schema": "understat_matches",
        "cluster_fields": ["league", "season"],
    },
]

_session = requests.Session()


# ---------------------------------------------------------------- utilidades puras


def default_season(today: date | None = None) -> int:
    """Temporada europea en curso: julio a junio (octubre de 2026 -> 2026)."""
    today = today or datetime.now(UTC).date()
    return today.year if today.month >= 7 else today.year - 1


def season_name(season: int) -> str:
    return f"{season}/{str(season + 1)[-2:]}"


def resolve_leagues(scope: str | None = None) -> list[str]:
    """Traduce "big5", "all" o "EPL,La_liga" a códigos de liga válidos."""
    scope = scope or config.UNDERSTAT_SCOPE
    codes: list[str] = []
    for name in (s.strip() for s in scope.split(",") if s.strip()):
        if name == "all":
            codes += list(config.UNDERSTAT_LEAGUES)
        elif name == "big5":
            codes += list(config.UNDERSTAT_LEAGUES)
        elif name in config.UNDERSTAT_LEAGUES:
            codes.append(name)
        else:
            raise ValueError(
                f"Liga desconocida: {name}. Opciones: big5, all, {', '.join(config.UNDERSTAT_LEAGUES)}"
            )
    # Mantiene el orden de config y evita repetidos.
    return [code for code in config.UNDERSTAT_LEAGUES if code in set(codes)]


def _num(value, cast=float):
    if value is None or value == "":
        return None
    try:
        return cast(value)
    except (TypeError, ValueError):
        return None


def parse_league_data(payload: dict, league: str, season: int, ingested_at: str) -> dict[str, list[dict]]:
    """Convierte la respuesta de Understat en filas listas para las 3 tablas raw."""
    league_name = config.UNDERSTAT_LEAGUES[league]
    sname = season_name(season)
    base = {"league": league, "league_name": league_name, "season": season, "season_name": sname}

    players = []
    for player in payload.get("players") or []:
        if player.get("id") is None:
            continue
        players.append(
            {
                **base,
                "player_id": str(player["id"]),
                "player_name": player.get("player_name"),
                "team_title": player.get("team_title"),
                "position": player.get("position"),
                "games": player.get("games"),
                "minutes": player.get("time"),
                "goals": player.get("goals"),
                "assists": player.get("assists"),
                "shots": player.get("shots"),
                "key_passes": player.get("key_passes"),
                "yellow_cards": player.get("yellow_cards"),
                "red_cards": player.get("red_cards"),
                "non_penalty_goals": player.get("npg"),
                "xg": player.get("xG"),
                "xa": player.get("xA"),
                "npxg": player.get("npxG"),
                "xg_chain": player.get("xGChain"),
                "xg_buildup": player.get("xGBuildup"),
                "_ingested_at": ingested_at,
            }
        )

    team_matches = []
    for team_key, team in (payload.get("teams") or {}).items():
        team_id = _num(team.get("id") or team_key, int)
        if team_id is None:
            continue
        for match in team.get("history") or []:
            ppda = match.get("ppda") or {}
            ppda_allowed = match.get("ppda_allowed") or {}
            team_matches.append(
                {
                    **base,
                    "team_id": team_id,
                    "team_title": team.get("title"),
                    "match_date": match.get("date"),
                    "h_a": match.get("h_a"),
                    "xg": _num(match.get("xG")),
                    "xga": _num(match.get("xGA")),
                    "npxg": _num(match.get("npxG")),
                    "npxga": _num(match.get("npxGA")),
                    "ppda_att": _num(ppda.get("att"), int),
                    "ppda_def": _num(ppda.get("def"), int),
                    "ppda_allowed_att": _num(ppda_allowed.get("att"), int),
                    "ppda_allowed_def": _num(ppda_allowed.get("def"), int),
                    "deep": _num(match.get("deep"), int),
                    "deep_allowed": _num(match.get("deep_allowed"), int),
                    "scored": _num(match.get("scored"), int),
                    "missed": _num(match.get("missed"), int),
                    "xpts": _num(match.get("xpts")),
                    "result": match.get("result"),
                    "wins": _num(match.get("wins"), int),
                    "draws": _num(match.get("draws"), int),
                    "loses": _num(match.get("loses"), int),
                    "pts": _num(match.get("pts"), int),
                    "npxgd": _num(match.get("npxGD")),
                    "_ingested_at": ingested_at,
                }
            )

    matches = []
    for match in payload.get("dates") or []:
        if match.get("id") is None:
            continue
        home = match.get("h") or {}
        away = match.get("a") or {}
        goals = match.get("goals") or {}
        xg = match.get("xG") or {}
        forecast = match.get("forecast") or {}
        matches.append(
            {
                **base,
                "match_id": str(match["id"]),
                "is_result": match.get("isResult"),
                "match_date": match.get("datetime"),
                "home_team_id": _num(home.get("id"), int),
                "home_team_title": home.get("title"),
                "home_team_short_title": home.get("short_title"),
                "away_team_id": _num(away.get("id"), int),
                "away_team_title": away.get("title"),
                "away_team_short_title": away.get("short_title"),
                "home_goals": _num(goals.get("h"), int),
                "away_goals": _num(goals.get("a"), int),
                "home_xg": _num(xg.get("h")),
                "away_xg": _num(xg.get("a")),
                "forecast_win": _num(forecast.get("w")),
                "forecast_draw": _num(forecast.get("d")),
                "forecast_loss": _num(forecast.get("l")),
                "_ingested_at": ingested_at,
            }
        )

    return {"players_season": players, "team_matches": team_matches, "matches": matches}


def gcs_object_name(table: str, league: str, season: int, ingest_date: str) -> str:
    return (
        f"{config.GCS_UNDERSTAT_PREFIX}/{table}/league={league}/season={season}/"
        f"ingest_date={ingest_date}/{table}.ndjson.gz"
    )


# ---------------------------------------------------------------- red y GCP


def fetch_league_data(league: str, season: int) -> dict:
    """Baja el JSON de una liga-temporada con reintentos y headers de la web."""
    url = f"{config.UNDERSTAT_BASE_URL}/getLeagueData/{league}/{season}"
    headers = {
        "User-Agent": config.UNDERSTAT_USER_AGENT,
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{config.UNDERSTAT_BASE_URL}/league/{league}/{season}",
        "Accept": "application/json, text/javascript, */*; q=0.01",
    }
    for attempt in range(4):
        try:
            resp = _session.get(url, headers=headers, timeout=config.HTTP_TIMEOUT_S)
            resp.raise_for_status()
            payload = resp.json()
            if not isinstance(payload, dict):
                raise ValueError(f"Understat devolvió un JSON inesperado para {league}/{season}")
            return payload
        except (requests.RequestException, ValueError):
            if attempt == 3:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("inalcanzable")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def is_fresh(manifest: dict, league: str, season: int) -> bool:
    """Evita pedir la misma liga dos veces en pocas horas (el DAG corre a diario)."""
    entry = manifest.get(f"{league}:{season}") or {}
    fetched_at = entry.get("fetched_at")
    if not fetched_at:
        return False
    try:
        fetched = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    return datetime.now(UTC) - fetched < timedelta(hours=config.UNDERSTAT_MIN_INTERVAL_HOURS)


def ingest_league(
    league: str,
    season: int,
    force: bool = False,
    ingest_date: str | None = None,
) -> list[dict]:
    """Baja una liga y agrega sus 3 tablas a BigQuery. Devuelve métricas de carga."""
    ingest_date = ingest_date or date.today().isoformat()
    ingested_at = _now()

    if not force:
        manifest = storage.read_manifest(config.UNDERSTAT_MANIFEST_BLOB)
        if is_fresh(manifest, league, season):
            log.info(
                "Understat %s/%s: ya se actualizó hace menos de %sh",
                league,
                season,
                config.UNDERSTAT_MIN_INTERVAL_HOURS,
            )
            return []

    payload = fetch_league_data(league, season)
    tables = parse_league_data(payload, league, season, ingested_at)

    results = []
    for table, rows in tables.items():
        spec = next(s for s in TABLE_SPECS if s["table"] == table)
        results.append(
            bq.upload_and_load(
                rows,
                gcs_object_name(table, league, season, ingest_date),
                config.BQ_UNDERSTAT_DATASET,
                table,
                spec["schema"],
                spec["cluster_fields"],
            )
        )

    storage.update_manifest(
        config.UNDERSTAT_MANIFEST_BLOB,
        {
            f"{league}:{season}": {
                "fetched_at": ingested_at,
                "season_name": season_name(season),
                "rows": {table: len(rows) for table, rows in tables.items()},
            }
        },
    )
    log.info(
        "Understat %s/%s: %d jugadores, %d equipos-partido, %d partidos",
        league,
        season,
        len(tables["players_season"]),
        len(tables["team_matches"]),
        len(tables["matches"]),
    )
    return results


def ingest_all(
    leagues: list[str] | None = None,
    season: int | None = None,
    force: bool = False,
    ingest_date: str | None = None,
) -> list[dict]:
    season = season or config.UNDERSTAT_SEASON or default_season()
    leagues = leagues or resolve_leagues()
    results: list[dict] = []
    for index, league in enumerate(leagues):
        results += ingest_league(league, season, force=force, ingest_date=ingest_date)
        if index < len(leagues) - 1:
            time.sleep(config.UNDERSTAT_DELAY_S)
    return results


def ensure_tables() -> None:
    bq.ensure_tables(TABLE_SPECS)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--leagues", default=None, help="big5, all o códigos separados por coma")
    parser.add_argument("--season", type=int, default=None, help="Año de inicio (2026 = 2026/27)")
    parser.add_argument("--force", action="store_true", help="Ignora el manifest y vuelve a bajar")
    args = parser.parse_args()

    # Crea también las tablas vacías de SofaScore para que dbt pueda correr siempre.
    from ingestion import current_season

    current_season.ensure_tables()
    results = ingest_all(resolve_leagues(args.leagues), args.season, args.force)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
