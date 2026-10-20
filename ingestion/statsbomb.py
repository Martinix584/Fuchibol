"""Ingesta de StatsBomb Open Data: partidos, eventos y alineaciones.

Flujo:
  1. sync_matches(): baja competitions.json y los partidos del alcance elegido, los
     carga a BigQuery (WRITE_TRUNCATE, son chicos) y arma el plan de partidos nuevos o
     actualizados comparando su `last_updated` contra un manifest en GCS.
  2. ingest_batch(): por cada competición-temporada del plan, baja eventos y alineaciones
     en paralelo, los escribe como NDJSON.gz en GCS y los agrega (WRITE_APPEND) a BigQuery.
     El staging de dbt se queda con la última ingesta de cada partido, así que reintentar
     o reprocesar nunca duplica datos.
  3. save_manifest(): recién al final se marca cada partido como procesado.

El NDJSON en GCS guarda el JSON completo del origen. En BigQuery se carga con un esquema
explícito (ingestion/schemas/) e ignore_unknown_values, así que solo entra lo que se usa.

Uso local:
    python -m ingestion.statsbomb                       # alcance de STATSBOMB_SCOPE
    python -m ingestion.statsbomb --scope core,big5_2015
    python -m ingestion.statsbomb --force               # reprocesa todo el alcance
"""

from __future__ import annotations

import argparse
import gzip
import json
import logging
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from pathlib import Path

import requests

from ingestion import config, storage

log = logging.getLogger(__name__)

SCHEMAS_DIR = Path(__file__).parent / "schemas"
_session = requests.Session()


# ---------------------------------------------------------------- utilidades puras


def resolve_scope(scope: str, competitions: list[dict]) -> list[tuple[int, int]]:
    """Traduce "core,big5_2015" o "all" a una lista de (competition_id, season_id)."""
    pairs: list[tuple[int, int]] = []
    for name in (s.strip() for s in scope.split(",") if s.strip()):
        if name == "all":
            pairs += [
                (c["competition_id"], c["season_id"])
                for c in competitions
                if c.get("competition_gender") == "male"
            ]
        elif name in config.STATSBOMB_SCOPES:
            pairs += config.STATSBOMB_SCOPES[name]
        else:
            raise ValueError(
                f"Alcance desconocido: {name}. Opciones: all, {', '.join(config.STATSBOMB_SCOPES)}"
            )
    available = {(c["competition_id"], c["season_id"]) for c in competitions}
    missing = [p for p in pairs if p not in available]
    if missing:
        log.warning("No están en el open data y se ignoran: %s", missing)
    return sorted({p for p in pairs if p in available})


def changed_matches(matches: list[dict], manifest: dict[str, str]) -> list[dict]:
    """Partidos nuevos o con `last_updated` distinto al ya procesado."""
    return [m for m in matches if manifest.get(str(m["match_id"])) != m.get("last_updated")]


def build_plan(matches_by_pair: dict[tuple[int, int], list[dict]], manifest: dict[str, str]) -> list[dict]:
    plan = []
    for (competition_id, season_id), matches in sorted(matches_by_pair.items()):
        todo = changed_matches(matches, manifest)
        if todo:
            plan.append(
                {
                    "competition_id": competition_id,
                    "season_id": season_id,
                    "matches": {str(m["match_id"]): m.get("last_updated") for m in todo},
                }
            )
    return plan


def with_metadata(rows: list[dict], ingested_at: str, **extra) -> list[dict]:
    return [{**extra, **row, "_ingested_at": ingested_at} for row in rows]


def lineup_rows(match_id: int, lineups: list[dict], ingested_at: str) -> list[dict]:
    return [
        {
            "match_id": match_id,
            "team_id": team["team_id"],
            "team_name": team["team_name"],
            "lineup": team["lineup"],
            "_ingested_at": ingested_at,
        }
        for team in lineups
    ]


def batch_prefix(kind: str, competition_id: int, season_id: int, ingest_date: str) -> str:
    return (
        f"{config.GCS_STATSBOMB_PREFIX}/{kind}/competition_id={competition_id}/"
        f"season_id={season_id}/ingest_date={ingest_date}/{kind}.ndjson.gz"
    )


# ---------------------------------------------------------------- red y GCP


def fetch_json(path: str):
    for attempt in range(4):
        try:
            resp = _session.get(f"{config.STATSBOMB_BASE_URL}/{path}", timeout=config.HTTP_TIMEOUT_S)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException:
            if attempt == 3:
                raise
            time.sleep(2**attempt)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _write_ndjson_gz(rows, path: str) -> int:
    count = 0
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False))
            f.write("\n")
            count += 1
    return count


def load_ndjson(gcs_uri: str, table: str, schema_name: str, append: bool) -> int:
    from google.cloud import bigquery

    client = bigquery.Client(project=config.GCP_PROJECT_ID, location=config.BQ_LOCATION)
    client.create_dataset(config.BQ_STATSBOMB_DATASET, exists_ok=True)
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        schema=client.schema_from_json(str(SCHEMAS_DIR / f"{schema_name}.json")),
        ignore_unknown_values=True,
        write_disposition=(
            bigquery.WriteDisposition.WRITE_APPEND if append else bigquery.WriteDisposition.WRITE_TRUNCATE
        ),
        time_partitioning=bigquery.TimePartitioning(field="_ingested_at") if append else None,
        clustering_fields=["match_id"] if append else None,
    )
    table_id = f"{config.GCP_PROJECT_ID}.{config.BQ_STATSBOMB_DATASET}.{table}"
    job = client.load_table_from_uri(gcs_uri, table_id, job_config=job_config)
    job.result()
    return job.output_rows


def _upload_and_load(rows, object_name: str, table: str, schema_name: str, append: bool) -> dict:
    started = time.monotonic()
    with tempfile.NamedTemporaryFile(suffix=".ndjson.gz") as tmp:
        count = _write_ndjson_gz(rows, tmp.name)
        size = Path(tmp.name).stat().st_size
        uri = storage.upload_file(tmp.name, object_name, "application/gzip")
    loaded = load_ndjson(uri, table, schema_name, append) if count else 0
    return {
        "table": f"statsbomb.{table}",
        "rows": loaded,
        "bytes": size,
        "extract_seconds": None,
        "load_seconds": round(time.monotonic() - started, 2),
    }


# ---------------------------------------------------------------- pasos del pipeline


def sync_matches(scope: str | None = None, force: bool = False, ingest_date: str | None = None) -> dict:
    """Carga competiciones y partidos del alcance y devuelve el plan de partidos a ingerir."""
    scope = scope or config.STATSBOMB_SCOPE
    ingest_date = ingest_date or date.today().isoformat()
    ingested_at = _now()

    competitions = fetch_json("competitions.json")
    pairs = resolve_scope(scope, competitions)
    matches_by_pair = {pair: fetch_json(f"matches/{pair[0]}/{pair[1]}.json") for pair in pairs}
    all_matches = [m for ms in matches_by_pair.values() for m in ms]

    metrics = [
        _upload_and_load(
            with_metadata(competitions, ingested_at),
            f"{config.GCS_STATSBOMB_PREFIX}/competitions/ingest_date={ingest_date}/competitions.ndjson.gz",
            "competitions",
            "statsbomb_competitions",
            append=False,
        ),
        _upload_and_load(
            with_metadata(all_matches, ingested_at),
            f"{config.GCS_STATSBOMB_PREFIX}/matches/ingest_date={ingest_date}/matches.ndjson.gz",
            "matches",
            "statsbomb_matches",
            append=False,
        ),
    ]
    manifest = {} if force else storage.read_manifest(config.STATSBOMB_MANIFEST_BLOB)
    plan = build_plan(matches_by_pair, manifest)
    log.info(
        "StatsBomb: %d competiciones-temporada, %d partidos, %d para ingerir",
        len(pairs),
        len(all_matches),
        sum(len(p["matches"]) for p in plan),
    )
    return {"plan": plan, "metrics": metrics}


def _fetch_match(match_id: int) -> tuple[int, list[dict], list[dict]]:
    return match_id, fetch_json(f"events/{match_id}.json"), fetch_json(f"lineups/{match_id}.json")


def ingest_batch(item: dict, ingest_date: str | None = None) -> dict:
    """Baja eventos y alineaciones de una competición-temporada y los agrega a BigQuery."""
    ingest_date = ingest_date or date.today().isoformat()
    ingested_at = _now()
    competition_id, season_id = item["competition_id"], item["season_id"]
    match_ids = [int(m) for m in item["matches"]]
    started = time.monotonic()

    tmp_dir = tempfile.TemporaryDirectory()
    paths = {kind: Path(tmp_dir.name) / f"{kind}.ndjson.gz" for kind in ("events", "lineups")}
    n_events = n_lineups = 0
    with (
        tmp_dir,
        gzip.open(paths["events"], "wt", encoding="utf-8") as ev_out,
        gzip.open(paths["lineups"], "wt", encoding="utf-8") as lu_out,
        ThreadPoolExecutor(max_workers=config.STATSBOMB_WORKERS) as pool,
    ):
        for match_id, events, lineups in pool.map(_fetch_match, match_ids):
            for row in with_metadata(events, ingested_at, match_id=match_id):
                ev_out.write(json.dumps(row, ensure_ascii=False) + "\n")
                n_events += 1
            for row in lineup_rows(match_id, lineups, ingested_at):
                lu_out.write(json.dumps(row, ensure_ascii=False) + "\n")
                n_lineups += 1
        ev_out.close()
        lu_out.close()
        extract_seconds = round(time.monotonic() - started, 2)

        results = []
        for kind, schema_name in [("events", "statsbomb_events"), ("lineups", "statsbomb_lineups")]:
            load_started = time.monotonic()
            uri = storage.upload_file(
                str(paths[kind]),
                batch_prefix(kind, competition_id, season_id, ingest_date),
                "application/gzip",
            )
            results.append(
                {
                    "table": f"statsbomb.{kind}[{competition_id}/{season_id}]",
                    "rows": load_ndjson(uri, kind, schema_name, append=True),
                    "bytes": paths[kind].stat().st_size,
                    "extract_seconds": extract_seconds,
                    "load_seconds": round(time.monotonic() - load_started, 2),
                }
            )

    log.info(
        "StatsBomb %s/%s: %d partidos, %d eventos, %d alineaciones",
        competition_id,
        season_id,
        len(match_ids),
        n_events,
        n_lineups,
    )
    return {"matches": item["matches"], "metrics": results}


def save_manifest(batches: list[dict]) -> None:
    updates = {mid: updated for b in batches for mid, updated in b["matches"].items()}
    storage.update_manifest(config.STATSBOMB_MANIFEST_BLOB, updates)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--scope", default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    synced = sync_matches(args.scope, args.force)
    batches = [ingest_batch(item) for item in synced["plan"]]
    save_manifest(batches)
    print(json.dumps([m for b in batches for m in b["metrics"]], indent=2))


if __name__ == "__main__":
    main()
