"""Compara el xG de Understat con el de StatsBomb en las 5 grandes 2015/16 (plan 7.1).

Todo en local, sin GCP: StatsBomb sale del repo abierto y Understat de su endpoint JSON, así
la temporada 2015 no entra a raw_understat (se colaría en los marts de la temporada actual).

    PYTHONPATH=. .venv/bin/python scripts/compare_xg.py                # las 5 ligas
    PYTHONPATH=. .venv/bin/python scripts/compare_xg.py --leagues EPL  # una sola

Cruce de jugadores, por liga: primero el equipo (nombre parecido, difflib) y dentro del
equipo el jugador, por apodo de StatsBomb igual al nombre de Understat o, si no, porque
todas las palabras del nombre de Understat están en el nombre completo de StatsBomb.
Si hay dos candidatos, se descarta (igual que int_player_id_map).
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import statistics
import unicodedata
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ingestion import statsbomb, understat

SEASON_SB = 27  # 2015/16 en StatsBomb
SEASON_US = 2015
# Understat -> competition_id de StatsBomb. La Bundesliga 2015/16 de StatsBomb trae solo 34
# partidos contra la temporada entera de Understat: no es comparable y queda fuera del default.
LEAGUES = {"EPL": 2, "La_liga": 11, "Bundesliga": 9, "Serie_A": 12, "Ligue_1": 7}


def norm(text: str | None) -> str:
    """Minúsculas, sin tildes ni signos (como el macro normalize_name de dbt)."""
    text = unicodedata.normalize("NFD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return " ".join(re.sub(r"[^a-z]+", " ", text).split())


def sb_players(events_by_match: dict, lineups_by_match: dict) -> dict[int, dict]:
    """Jugador de StatsBomb con su xG, npxG, tiros, equipo y apodo."""
    players: dict[int, dict] = {}
    for match_id, events in events_by_match.items():
        for lineup in lineups_by_match.get(match_id, []):
            for p in lineup["lineup"]:
                players.setdefault(
                    p["player_id"],
                    {
                        "name": p["player_name"],
                        "nickname": p.get("player_nickname"),
                        "team": lineup["team_name"],
                        "team_id": lineup["team_id"],
                        "xg": 0.0,
                        "npxg": 0.0,
                        "shots": 0,
                    },
                )
        for e in events:
            if e["type"]["name"] != "Shot" or e.get("period", 1) > 4:
                continue
            p = players.get(e["player"]["id"])
            if p is None:
                continue
            xg = e["shot"].get("statsbomb_xg") or 0.0
            p["xg"] += xg
            p["shots"] += 1
            if e["shot"]["type"]["name"] != "Penalty":
                p["npxg"] += xg
    return players


def map_teams(sb_teams: dict[str, int], us_teams: set[str]) -> dict[str, int]:
    """Equipo de Understat -> team_id de StatsBomb.

    sb_teams es nombre -> team_id: StatsBomb a veces nombra distinto al mismo equipo
    ("Marseille" y "Olympique de Marseille"). Primero, un único equipo que contenga todas las
    palabras ("Caen" en "Stade Malherbe Caen"); si no, el nombre más parecido (difflib).
    """
    by_norm = {norm(t): team_id for t, team_id in sb_teams.items()}
    mapping = {}
    for team in us_teams:
        tokens = set(norm(team).split())
        contains = {team_id for name, team_id in by_norm.items() if tokens <= set(name.split())}
        best = difflib.get_close_matches(norm(team), by_norm, n=1, cutoff=0.6)
        if len(contains) == 1:
            mapping[team] = contains.pop()
        elif best:
            mapping[team] = by_norm[best[0]]
    return mapping


def match_players(sb: dict[int, dict], us: list[dict], team_map: dict[str, int]) -> list[tuple[dict, dict]]:
    """Pares (StatsBomb, Understat) únicos por equipo; los ambiguos quedan afuera."""
    by_team: dict[int, list[dict]] = defaultdict(list)
    for p in sb.values():
        by_team[p["team_id"]].append(p)
    pairs, used = [], set()
    for u in us:
        teams = [team_map[t.strip()] for t in u["team_title"].split(",") if t.strip() in team_map]
        candidates = [p for t in teams for p in by_team[t]]
        name = norm(u["player_name"])
        exact = [p for p in candidates if norm(p["nickname"]) == name or norm(p["name"]) == name]
        tokens = set(name.split())
        subset = [p for p in candidates if tokens and tokens <= set(norm(p["name"]).split())]
        found = exact if len(exact) == 1 else subset if not exact and len(subset) == 1 else []
        if found and id(found[0]) not in used:
            used.add(id(found[0]))
            pairs.append((found[0], u))
    return pairs


def compare(pairs: list[tuple[dict, dict]], sb_total_xg: float) -> dict:
    """Métricas del plan: totales, diferencia, correlación, error medio y cobertura."""
    sb_xg = [p["xg"] for p, _ in pairs]
    us_xg = [float(u["xG"]) for _, u in pairs]
    diffs = [a - b for a, b in zip(sb_xg, us_xg, strict=True)]
    return {
        "jugadores": len(pairs),
        "xg_statsbomb": round(sum(sb_xg), 1),
        "xg_understat": round(sum(us_xg), 1),
        "dif_pct": round(100 * (sum(us_xg) - sum(sb_xg)) / sum(sb_xg), 1) if sum(sb_xg) else None,
        "pearson": round(statistics.correlation(sb_xg, us_xg), 3) if len(pairs) > 2 else None,
        "dif_media_abs": round(statistics.fmean(abs(d) for d in diffs), 3) if diffs else None,
        "pct_mas_de_0_5": round(100 * sum(abs(d) > 0.5 for d in diffs) / len(diffs), 1) if diffs else None,
        "cobertura_xg_sb": round(100 * sum(sb_xg) / sb_total_xg, 1) if sb_total_xg else None,
    }


def load_statsbomb(competition_id: int, cache: Path) -> tuple[dict, dict, int]:
    """Eventos (solo tiros) y alineaciones de una competición; cachea los tiros por partido."""
    matches = statsbomb.fetch_json(f"matches/{competition_id}/{SEASON_SB}.json")
    cache.mkdir(parents=True, exist_ok=True)

    def fetch(match_id: int):
        path = cache / f"{match_id}.json"
        if path.exists():
            data = json.loads(path.read_text())
        else:
            events = statsbomb.fetch_json(f"events/{match_id}.json")
            data = {
                "shots": [e for e in events if e["type"]["name"] == "Shot"],
                "lineups": statsbomb.fetch_json(f"lineups/{match_id}.json"),
            }
            path.write_text(json.dumps(data))
        return match_id, data

    with ThreadPoolExecutor(8) as pool:
        results = dict(pool.map(fetch, [m["match_id"] for m in matches]))
    events = {k: v["shots"] for k, v in results.items()}
    lineups = {k: v["lineups"] for k, v in results.items()}
    return events, lineups, len(matches)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--leagues", default="EPL,La_liga,Serie_A,Ligue_1", help="Códigos de Understat separados por coma"
    )
    parser.add_argument(
        "--cache",
        default=str(Path.home() / ".cache/fuchibol/compare_xg"),
        help="Carpeta para cachear los tiros",
    )
    args = parser.parse_args()

    rows = []
    for league in [c.strip() for c in args.leagues.split(",")]:
        events, lineups, n_matches = load_statsbomb(LEAGUES[league], Path(args.cache) / league)
        sb = sb_players(events, lineups)
        payload = understat.fetch_league_data(league, SEASON_US)
        us = payload["players"]
        team_map = map_teams(
            {p["team"]: p["team_id"] for p in sb.values()},
            {t.strip() for u in us for t in u["team_title"].split(",")},
        )
        pairs = match_players(sb, us, team_map)
        rows.append(
            {"liga": league, "partidos_sb": n_matches, **compare(pairs, sum(p["xg"] for p in sb.values()))}
        )

    headers = list(rows[0])
    print("| " + " | ".join(headers) + " |\n|" + "---|" * len(headers))
    for r in rows:
        print("| " + " | ".join(str(r[h]) for h in headers) + " |")


if __name__ == "__main__":
    main()
