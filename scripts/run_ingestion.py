"""Corre la ingesta completa sin Airflow (útil para la primera carga o para desarrollar).

PYTHONPATH=. python scripts/run_ingestion.py                  # las tres fuentes
PYTHONPATH=. python scripts/run_ingestion.py --only statsbomb --scope core,big5_2015
PYTHONPATH=. python scripts/run_ingestion.py --only understat --understat-scope big5
"""

import argparse
import logging
import uuid

from ingestion import extract, load, metrics, statsbomb, understat


def run_transfermarkt(force: bool) -> list[dict]:
    extracts, loads = [], []
    for table in extract.detect_changes(force=force):
        extracted = extract.extract_table(table)
        extracts.append(extracted)
        loads.append(load.load_table(extracted["gcs_uri"], table))
    extract.save_manifest({e["table"]: e["fingerprint"] for e in extracts})
    return metrics.merge_extract_load(extracts, loads)


def run_statsbomb(scope: str | None, force: bool) -> list[dict]:
    synced = statsbomb.sync_matches(scope, force)
    batches = [statsbomb.ingest_batch(item) for item in synced["plan"]]
    statsbomb.save_manifest(batches)
    return synced["metrics"] + [m for b in batches for m in b["metrics"]]


def run_understat(scope: str | None, force: bool) -> list[dict]:
    from ingestion import current_season

    current_season.ensure_tables()
    return understat.ingest_all(understat.resolve_leagues(scope), force=force)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--only", choices=["transfermarkt", "statsbomb", "understat"], default=None)
    parser.add_argument("--scope", default=None, help="Alcance de StatsBomb (core, big5_2015, messi, all)")
    parser.add_argument(
        "--understat-scope", default=None, help="Alcance de Understat (big5, all o ligas separadas por coma)"
    )
    parser.add_argument("--force", action="store_true", help="Reprocesar todo")
    args = parser.parse_args()

    items = []
    if args.only in (None, "transfermarkt"):
        items += run_transfermarkt(args.force)
    if args.only in (None, "statsbomb"):
        items += run_statsbomb(args.scope, args.force)
    if args.only in (None, "understat"):
        items += run_understat(args.understat_scope, args.force)

    metrics.record_ingestion(f"manual__{uuid.uuid4().hex[:8]}", items)
    logging.info("Listo: %d cargas, %s filas", len(items), sum(i["rows"] or 0 for i in items))


if __name__ == "__main__":
    main()
