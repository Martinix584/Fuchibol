"""Smoke test de punta a punta sin GCP.

1. Carga a DuckDB partidos REALES de StatsBomb (bajados de GitHub o de una carpeta local
   con la misma estructura que el repo open-data) con el mismo esquema que en BigQuery.
2. Genera datos sintéticos de Transfermarkt (con jugadores reales de esos partidos).
3. Corre en orden todos los modelos dbt compilados (salvo los de BigQuery ML) traduciendo
   el SQL de BigQuery a DuckDB, y después todos los data tests.
4. Imprime un resumen (filas, tiempos, tests) y sale con error si falla algo.

Requiere el proyecto compilado: lo más fácil es correrlo con scripts/smoke.sh.

    python tests/smoke/run_smoke.py --dbt-dir dbt --matches 6
    python tests/smoke/run_smoke.py --dbt-dir dbt --statsbomb-dir ~/open-data/data \\
        --competition 43 --season 106
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))

from bq_to_duckdb import TYPE_MAP, duck_type, prune, to_duckdb  # noqa: E402
from synthetic_transfermarkt import build as build_transfermarkt  # noqa: E402

from ingestion import statsbomb  # noqa: E402

SCHEMAS = ROOT / "ingestion" / "schemas"


def reader(local_dir: str | None):
    """Lee de una carpeta local o de GitHub (con los mismos reintentos que la ingesta)."""

    def read(path: str):
        if local_dir:
            return json.loads((Path(local_dir) / path).read_text())
        return statsbomb.fetch_json(path)

    return read


def create_table(con, table: str, schema_name: str, rows: list[dict], tmp: Path) -> None:
    fields = json.loads((SCHEMAS / f"{schema_name}.json").read_text())
    path = tmp / f"{table.replace('.', '_')}.ndjson"
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(prune(row, fields), default=str) + "\n")
    columns = ", ".join(f"'{fl['name']}': '{duck_type(fl)}'" for fl in fields)
    con.execute(
        f"create table {table} as select * from read_json('{path}', format='newline_delimited', "
        f"columns={{{columns}}})"
    )


def load_statsbomb(con, read, competition: int, season: int, n_matches: int | None, tmp: Path) -> list[dict]:
    ingested_at = "2026-10-20T06:00:00+00:00"
    competitions = read("competitions.json")
    matches = read(f"matches/{competition}/{season}.json")
    matches = (
        sorted(matches, key=lambda m: m["match_date"], reverse=True)[:n_matches] if n_matches else matches
    )
    ids = [m["match_id"] for m in matches]
    with ThreadPoolExecutor(8) as pool:
        payloads = list(pool.map(lambda i: (i, read(f"events/{i}.json"), read(f"lineups/{i}.json")), ids))

    events, lineups = [], []
    for match_id, ev, lu in payloads:
        events += statsbomb.with_metadata(ev, ingested_at, match_id=match_id)
        lineups += statsbomb.lineup_rows(match_id, lu, ingested_at)
        # una "reingesta" vieja del primer partido: el staging tiene que ignorarla
        if match_id == ids[0]:
            events += statsbomb.with_metadata(ev[:50], "2026-01-01T00:00:00+00:00", match_id=match_id)

    create_table(
        con,
        "raw_statsbomb.competitions",
        "statsbomb_competitions",
        statsbomb.with_metadata(competitions, ingested_at),
        tmp,
    )
    create_table(
        con, "raw_statsbomb.matches", "statsbomb_matches", statsbomb.with_metadata(matches, ingested_at), tmp
    )
    create_table(con, "raw_statsbomb.events", "statsbomb_events", events, tmp)
    create_table(con, "raw_statsbomb.lineups", "statsbomb_lineups", lineups, tmp)
    print(f"StatsBomb: {len(matches)} partidos, {len(events):,} eventos")

    # jugadores con más partidos, para armar el Transfermarkt sintético
    seen = {}
    for row in lineups:
        for p in row["lineup"]:
            if p["positions"]:
                key = p["player_id"]
                player = seen.setdefault(
                    key,
                    {
                        "sb_player_id": key,
                        "display_name": p["player_name"],
                        "country": (p.get("country") or {}).get("name"),
                        "n": 0,
                    },
                )
                player["n"] += 1
                # misma regla que int_player_id_map: el apodo, si aparece en algún partido
                if p["player_nickname"]:
                    player["display_name"] = p["player_nickname"]
    return sorted(seen.values(), key=lambda p: -p["n"])[:40]


def topological_order(nodes: dict) -> list[str]:
    order, seen = [], set()

    def visit(uid):
        if uid in seen or uid not in nodes:
            return
        seen.add(uid)
        for dep in nodes[uid].get("depends_on", {}).get("nodes", []):
            visit(dep)
        order.append(uid)

    for uid in sorted(nodes):
        visit(uid)
    return order


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dbt-dir", default=str(ROOT / "dbt"))
    parser.add_argument(
        "--statsbomb-dir", default=None, help="Carpeta data/ del repo open-data (si no, GitHub)"
    )
    parser.add_argument("--competition", type=int, default=43)
    parser.add_argument("--season", type=int, default=106)
    parser.add_argument("--matches", type=int, default=None, help="Cantidad de partidos (por defecto, todos)")
    parser.add_argument("--report", default=None, help="Guardar el resumen en este JSON")
    parser.add_argument(
        "--database", default=":memory:", help="Archivo DuckDB para inspeccionar el resultado"
    )
    args = parser.parse_args()

    dbt_dir = Path(args.dbt_dir)
    manifest = json.loads((dbt_dir / "target" / "manifest.json").read_text())
    nodes = manifest["nodes"]
    project = next(n["database"] for n in nodes.values() if n["resource_type"] == "model")

    Path(args.database).unlink(missing_ok=True) if args.database != ":memory:" else None
    con = duckdb.connect(args.database)
    for schema in {n["schema"] for n in nodes.values()} | {"raw_transfermarkt", "raw_statsbomb"}:
        con.execute(f'create schema if not exists "{schema}"')
    tmp = Path(dbt_dir / "target" / "smoke")
    tmp.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    sb_players = load_statsbomb(
        con, reader(args.statsbomb_dir), args.competition, args.season, args.matches, tmp
    )
    expected_map = build_transfermarkt(con, sb_players)

    summary = {"models": {}, "tests": {"pass": 0, "warn": 0, "fail": 0, "error": 0}, "failures": []}
    order = topological_order(nodes)

    # seeds
    for uid in order:
        node = nodes[uid]
        if node["resource_type"] == "seed":
            path = dbt_dir / node["original_file_path"]
            types = {c: TYPE_MAP.get(t.upper(), "VARCHAR") for c, t in node["config"]["column_types"].items()}
            con.execute(
                f"create table {node['schema']}.{node['alias']} as "
                f"select * from read_csv('{path}', header=true, types={types})"
            )

    # modelos (sin los de BigQuery ML, que necesitan el modelo entrenado)
    for uid in order:
        node = nodes[uid]
        if node["resource_type"] != "model" or "ml" in node["tags"]:
            continue
        sql = (dbt_dir / "target" / "compiled" / "fuchibol" / node["original_file_path"]).read_text()
        t0 = time.monotonic()
        try:
            con.execute(f"create table {node['schema']}.{node['alias']} as {to_duckdb(sql, project)}")
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR en {node['name']}: {exc}")
            return 1
        rows = con.execute(f"select count(*) from {node['schema']}.{node['alias']}").fetchone()[0]
        summary["models"][node["name"]] = {"rows": rows, "seconds": round(time.monotonic() - t0, 2)}
        print(f"  {node['name']:<34} {rows:>9,} filas  {summary['models'][node['name']]['seconds']:>6.2f}s")

    # data tests (salvo los que dependen de ML o del snapshot)
    skipped = {
        uid for uid, n in nodes.items() if n["resource_type"] == "snapshot" or "ml" in n.get("tags", [])
    }
    for uid in order:
        node = nodes[uid]
        if node["resource_type"] != "test" or set(node["depends_on"].get("nodes", [])) & skipped:
            continue
        compiled = dbt_dir / "target" / "compiled" / "fuchibol" / node["original_file_path"]
        if compiled.suffix == ".yml":
            compiled = compiled / f"{node['alias']}.sql"
        severity = node["config"]["severity"].lower()
        try:
            failures = con.execute(
                f"select count(*) from ({to_duckdb(compiled.read_text(), project)})"
            ).fetchone()[0]
        except Exception as exc:  # noqa: BLE001
            summary["tests"]["error"] += 1
            summary["failures"].append(f"{node['name']}: ERROR {exc}")
            continue
        if not failures:
            summary["tests"]["pass"] += 1
        else:
            summary["tests"]["warn" if severity == "warn" else "fail"] += 1
            summary["failures"].append(f"{node['name']} ({severity}): {failures} filas")

    # el cruce de identidades tiene que dar lo esperado
    # (por id: un mismo jugador puede traer apodos distintos según el partido)
    mapped = dict(
        con.execute("select sb_player_id, tm_player_id from intermediate.int_player_id_map").fetchall()
    )
    overrides = {
        int(r["sb_player_id"]) for r in csv.DictReader(open(dbt_dir / "seeds" / "player_id_overrides.csv"))
    }
    wrong = [
        (p["display_name"], expected_map.get(p["display_name"]), mapped.get(p["sb_player_id"]))
        for p in sb_players
        if p["sb_player_id"] not in overrides
        and mapped.get(p["sb_player_id"]) != expected_map.get(p["display_name"])
    ]
    summary["id_map"] = {"sb_players": len(sb_players), "mapped": len(mapped), "wrong": wrong}
    summary["seconds"] = round(time.monotonic() - started, 1)

    print(f"\nTests: {summary['tests']}")
    for f in summary["failures"]:
        print(f"  - {f}")
    print(f"Cruce de jugadores: {len(mapped)} cruzados, {len(wrong)} distintos de lo esperado {wrong[:5]}")
    print(f"Total: {summary['seconds']}s")
    if args.report:
        Path(args.report).write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    ok = summary["tests"]["fail"] == 0 and summary["tests"]["error"] == 0 and not wrong
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
