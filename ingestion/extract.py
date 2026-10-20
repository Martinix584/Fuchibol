"""Extract de Transfermarkt: baja los CSV de transfermarkt-datasets y los deja en GCS (capa raw).

Es incremental a nivel archivo: guarda en GCS un manifest con la huella (ETag /
Last-Modified / tamaño) de cada archivo y solo vuelve a bajar los que cambiaron.

Uso local:
    python -m ingestion.extract                # solo lo que cambió
    python -m ingestion.extract --force        # todo
    python -m ingestion.extract --tables players transfers
"""

from __future__ import annotations

import argparse
import json
import logging
import tempfile
import time
from datetime import date

import requests

from ingestion import config, storage

log = logging.getLogger(__name__)


def source_url(table: str) -> str:
    return f"{config.BASE_URL}/{table}.csv.gz"


def gcs_object_name(table: str, ingest_date: str) -> str:
    """Ruta particionada por fecha de ingesta: permite reprocesar cualquier día."""
    return f"{config.GCS_RAW_PREFIX}/{table}/ingest_date={ingest_date}/{table}.csv.gz"


def fingerprint_from_headers(headers: dict) -> str:
    """Huella del archivo remoto. Prioriza ETag; si no hay, usa fecha + tamaño."""
    headers = {k.lower(): v for k, v in headers.items()}
    if headers.get("etag"):
        return headers["etag"].strip('"')
    return f"{headers.get('last-modified', '')}|{headers.get('content-length', '')}"


def remote_fingerprint(table: str) -> str:
    resp = requests.head(source_url(table), timeout=config.HTTP_TIMEOUT_S, allow_redirects=True)
    resp.raise_for_status()
    return fingerprint_from_headers(dict(resp.headers))


def changed_tables(remote: dict[str, str], manifest: dict[str, str]) -> list[str]:
    return [t for t, fp in remote.items() if manifest.get(t) != fp]


def load_manifest() -> dict[str, str]:
    return storage.read_manifest(config.MANIFEST_BLOB)


def save_manifest(updates: dict[str, str]) -> None:
    storage.update_manifest(config.MANIFEST_BLOB, updates)


def detect_changes(tables: list[str] | None = None, force: bool = False) -> list[str]:
    tables = tables or config.TABLES
    if force:
        return list(tables)
    remote = {t: remote_fingerprint(t) for t in tables}
    changed = changed_tables(remote, load_manifest())
    log.info("Tablas con cambios: %s", changed or "ninguna")
    return changed


def extract_table(table: str, ingest_date: str | None = None) -> dict:
    """Baja un archivo y lo sube a GCS. Devuelve métricas para la tabla ops.pipeline_runs."""
    ingest_date = ingest_date or date.today().isoformat()
    started = time.monotonic()

    with tempfile.NamedTemporaryFile(suffix=".csv.gz") as tmp:
        with requests.get(source_url(table), stream=True, timeout=config.HTTP_TIMEOUT_S) as resp:
            resp.raise_for_status()
            fingerprint = fingerprint_from_headers(dict(resp.headers))
            for chunk in resp.iter_content(chunk_size=1 << 20):
                tmp.write(chunk)
        tmp.flush()
        size_bytes = tmp.tell()

        uri = storage.upload_file(tmp.name, gcs_object_name(table, ingest_date), "application/gzip")

    result = {
        "table": table,
        "gcs_uri": uri,
        "bytes": size_bytes,
        "fingerprint": fingerprint,
        "extract_seconds": round(time.monotonic() - started, 2),
    }
    log.info("Extraído %s", result)
    return result


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tables", nargs="*", default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    for table in detect_changes(args.tables, args.force):
        result = extract_table(table)
        save_manifest({table: result["fingerprint"]})
        print(json.dumps(result))


if __name__ == "__main__":
    main()
