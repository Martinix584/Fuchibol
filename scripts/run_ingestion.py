"""Corre extract + load + métricas sin Airflow (útil para la primera carga)."""

import argparse
import logging
import uuid

from ingestion.extract import detect_changes, extract_table, save_manifest
from ingestion.load import load_table
from ingestion.metrics import record_ingestion


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Reprocesar todas las tablas")
    args = parser.parse_args()

    run_id = f"manual__{uuid.uuid4().hex[:8]}"
    extracts, loads = [], []
    for table in detect_changes(force=args.force):
        extracted = extract_table(table)
        extracts.append(extracted)
        loads.append(load_table(extracted["gcs_uri"], table))

    record_ingestion(run_id, extracts, loads)
    save_manifest({e["table"]: e["fingerprint"] for e in extracts})
    logging.info("Listo: %d tablas, %s filas", len(loads), sum(r["rows"] for r in loads))


if __name__ == "__main__":
    main()
