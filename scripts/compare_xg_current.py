"""Compara el xG de Understat y SofaScore en la temporada actual (plan 7.2).

Lee ``marts.mart_current_player_season`` de BigQuery (las dos fuentes ya cargadas) y
cruza jugadores por liga + equipo + nombre. No mezcla fuentes: solo mide cuánto se
separan. Pensado para correr después de cargar las 5 grandes con SofaScore en modo full.

    PYTHONPATH=. .venv/bin/python scripts/compare_xg_current.py
    PYTHONPATH=. .venv/bin/python scripts/compare_xg_current.py --leagues EPL --season 2026
    PYTHONPATH=. .venv/bin/python scripts/compare_xg_current.py --json /tmp/compare.json
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import statistics
import unicodedata
from collections import defaultdict

from google.cloud import bigquery

from ingestion import config

BIG5 = ["EPL", "La_liga", "Serie_A", "Bundesliga", "Ligue_1"]


def norm(text: str | None) -> str:
    text = unicodedata.normalize("NFD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return " ".join(re.sub(r"[^a-z]+", " ", text).split())


def map_teams(us_teams: set[str], ss_teams: set[str]) -> dict[str, str]:
    """Equipo de Understat -> equipo de SofaScore (exacto, contiene o fuzzy)."""
    by_norm = {norm(t): t for t in ss_teams}
    mapping: dict[str, str] = {}
    for team in us_teams:
        name = norm(team)
        if name in by_norm:
            mapping[team] = by_norm[name]
            continue
        tokens = set(name.split())
        contains = [key for key in by_norm if tokens and tokens <= set(key.split())]
        best = difflib.get_close_matches(name, by_norm, n=1, cutoff=0.6)
        if len(contains) == 1:
            mapping[team] = by_norm[contains[0]]
        elif best:
            mapping[team] = by_norm[best[0]]
    return mapping


def match_players(us: list[dict], ss: list[dict], team_map: dict[str, str]) -> list[tuple[dict, dict]]:
    """Pares (Understat, SofaScore) únicos; los ambiguos quedan afuera."""
    by_team: dict[str, list[dict]] = defaultdict(list)
    for row in ss:
        by_team[row["team_name"]].append(row)

    pairs: list[tuple[dict, dict]] = []
    used: set[str] = set()
    for u in us:
        team = team_map.get(u["team_name"])
        candidates = by_team.get(team, []) if team else []
        name = norm(u["player_name"])
        exact = [s for s in candidates if norm(s["player_name"]) == name]
        tokens = set(name.split())
        subset = [s for s in candidates if tokens and tokens <= set(norm(s["player_name"]).split())]
        found = exact if len(exact) == 1 else subset if not exact and len(subset) == 1 else []
        if not found and candidates:
            scored = sorted(
                (
                    (difflib.SequenceMatcher(None, name, norm(s["player_name"])).ratio(), s)
                    for s in candidates
                ),
                key=lambda item: item[0],
                reverse=True,
            )
            if scored and scored[0][0] >= 0.85 and (len(scored) == 1 or scored[1][0] < scored[0][0] - 0.05):
                found = [scored[0][1]]
        if found and found[0]["player_key"] not in used:
            used.add(found[0]["player_key"])
            pairs.append((u, found[0]))
    return pairs


def compare(pairs: list[tuple[dict, dict]], us_total: float, ss_total: float) -> dict:
    us_xg = [float(u["xg"]) for u, _ in pairs]
    ss_xg = [float(s["xg"]) for _, s in pairs]
    diffs = [a - b for a, b in zip(us_xg, ss_xg, strict=True)]
    us_sum, ss_sum = sum(us_xg), sum(ss_xg)
    return {
        "jugadores": len(pairs),
        "xg_understat": round(us_sum, 1),
        "xg_sofascore": round(ss_sum, 1),
        "dif_pct": round(100 * (ss_sum - us_sum) / us_sum, 1) if us_sum else None,
        "pearson": round(statistics.correlation(us_xg, ss_xg), 3) if len(pairs) > 2 else None,
        "dif_media_abs": round(statistics.fmean(abs(d) for d in diffs), 3) if diffs else None,
        "pct_mas_de_0_5": round(100 * sum(abs(d) > 0.5 for d in diffs) / len(diffs), 1) if diffs else None,
        "cobertura_xg_us": round(100 * us_sum / us_total, 1) if us_total else None,
        "cobertura_xg_ss": round(100 * ss_sum / ss_total, 1) if ss_total else None,
    }


def load_rows(
    client: bigquery.Client, dataset: str, season: int, source: str, leagues: list[str]
) -> list[dict]:
    sql = f"""
        select player_name, team_name, league_code, xg, xa, shots, key_passes, minutes, player_key
        from `{client.project}.{dataset}.mart_current_player_season`
        where season = @season
          and xg_source = @source
          and league_code in unnest(@leagues)
          and xg is not null
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("season", "INT64", season),
            bigquery.ScalarQueryParameter("source", "STRING", source),
            bigquery.ArrayQueryParameter("leagues", "STRING", leagues),
        ]
    )
    return [dict(row) for row in client.query(sql, job_config=job_config).result()]


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--leagues", default=",".join(BIG5))
    parser.add_argument("--season", type=int, default=None, help="Por defecto, la última con Understat")
    parser.add_argument("--dataset", default="marts")
    parser.add_argument("--json", default=None, help="Guardar los resultados en JSON")
    args = parser.parse_args()

    client = bigquery.Client(project=config.GCP_PROJECT_ID, location=config.BQ_LOCATION)
    season = args.season
    if season is None:
        row = next(
            iter(
                client.query(
                    f"select max(season) season from "
                    f"`{client.project}.{args.dataset}.mart_current_player_season` "
                    "where xg_source = 'understat'"
                ).result()
            )
        )
        season = row.season
    leagues = [league.strip() for league in args.leagues.split(",") if league.strip()]

    results = []
    for league in leagues:
        us = load_rows(client, args.dataset, season, "understat", [league])
        ss = load_rows(client, args.dataset, season, "sofascore", [league])
        if not us or not ss:
            print(f"{league}: falta {'Understat' if not us else 'SofaScore'} para {season}; se saltea.")
            continue
        team_map = map_teams({r["team_name"] for r in us}, {r["team_name"] for r in ss})
        pairs = match_players(us, ss, team_map)
        results.append(
            {
                "liga": league,
                **compare(pairs, sum(float(r["xg"]) for r in us), sum(float(r["xg"]) for r in ss)),
            }
        )

    if not results:
        print("No hay ligas con las dos fuentes cargadas.")
        return

    headers = list(results[0])
    print("| " + " | ".join(headers) + " |")
    print("|" + "---|" * len(headers))
    for row in results:
        print("| " + " | ".join(str(row[h]) for h in headers) + " |")

    if args.json:
        with open(args.json, "w") as fh:
            json.dump({"season": season, "results": results}, fh, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
