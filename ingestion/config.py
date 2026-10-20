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

# ---------------------------------------------------------------------------
# StatsBomb Open Data: datos de eventos (cada pase, tiro, presión...) con xG.
# Es lo más parecido a Opta que se puede usar gratis. Requiere atribución:
# https://github.com/statsbomb/open-data
# ---------------------------------------------------------------------------
STATSBOMB_BASE_URL = os.getenv(
    "STATSBOMB_BASE_URL", "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
)
BQ_STATSBOMB_DATASET = os.getenv("BQ_STATSBOMB_DATASET", "raw_statsbomb")
GCS_STATSBOMB_PREFIX = "raw/statsbomb"
STATSBOMB_MANIFEST_BLOB = "manifests/statsbomb.json"
STATSBOMB_WORKERS = int(os.getenv("STATSBOMB_WORKERS", "8"))

# Alcances predefinidos: (competition_id, season_id). Se elige con STATSBOMB_SCOPE
# (varios separados por coma). "all" = todas las competiciones masculinas.
STATSBOMB_SCOPES = {
    # ~350 partidos: torneos recientes que también cubre Transfermarkt
    "core": [
        (43, 106),  # Mundial 2022
        (43, 3),  # Mundial 2018
        (55, 282),  # Euro 2024
        (55, 43),  # Euro 2020
        (223, 282),  # Copa América 2024
        (1267, 107),  # Copa Africana 2023
        (9, 281),  # Bundesliga 2023/24 (Leverkusen invicto)
    ],
    # ~1.800 partidos: temporadas completas de las 5 grandes ligas
    "big5_2015": [(2, 27), (11, 27), (9, 27), (12, 27), (7, 27)],
    # La Liga de Messi (solo partidos del Barcelona), 2004/05 a 2020/21
    "messi": [(11, s) for s in (37, 38, 39, 40, 41, 21, 22, 23, 24, 25, 26, 27, 2, 1, 4, 42, 90)],
}
STATSBOMB_SCOPE = os.getenv("STATSBOMB_SCOPE", "core")
