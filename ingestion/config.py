"""Configuración central de la ingesta. Todo sale de variables de entorno (ver .env.example)."""

import os

# Mirror público de transfermarkt-datasets (CC0): https://github.com/dcaribou/transfermarkt-datasets
BASE_URL = os.getenv("TM_BASE_URL", "https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data")

# Tablas que usa el proyecto. Cada una se publica como <tabla>.csv.gz
TABLES = [
    "competitions",
    "clubs",
    "players",
    "player_valuations",
    "transfers",
    "games",
    "appearances",
]

GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "")
GCS_BUCKET = os.getenv("GCS_BUCKET", "")
BQ_LOCATION = os.getenv("BQ_LOCATION", "US")
BQ_RAW_DATASET = os.getenv("BQ_RAW_DATASET", "raw_transfermarkt")
BQ_OPS_DATASET = os.getenv("BQ_OPS_DATASET", "ops")

GCS_RAW_PREFIX = "raw/transfermarkt"
MANIFEST_BLOB = "manifests/transfermarkt.json"

HTTP_TIMEOUT_S = 120
