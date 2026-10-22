"""Modelo de valor de mercado: se entrena en local (o en Airflow) con scikit-learn.

La idea original era BigQuery ML, pero para este proyecto no valía la pena: BigQuery ML
factura cada vuelta del entrenamiento sobre la tabla, y una tabla de ~27 MB terminaba
contando como más de 20 GB. Con scikit-learn se entrena en segundos y gratis.

Aprende el valor (en log) a partir del rendimiento y el perfil del jugador en temporadas
pasadas, y predice la última temporada completa, que no ve al entrenar. Si el modelo dice
que un jugador "debería" valer bastante más de lo que vale -> subvaluado.

    PYTHONPATH=. python -m ingestion.ml            # lee intermediate.int_player_value_features
    PYTHONPATH=. python -m ingestion.ml --dataset dev_intermediate

Escribe tres tablas en el dataset `ml` (las leen los modelos dbt con tag ml):
    ml.model_predictions   player_id, season, valor real y predicho
    ml.model_evaluation    R², MAE y error mediano sobre el 20 % de evaluación
    ml.feature_importance  importancia de cada variable (permutación sobre la evaluación)
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import random
from datetime import UTC, datetime

from ingestion import config

log = logging.getLogger(__name__)

NUMERIC = [
    "season",
    "age",
    "height_in_cm",
    "games",
    "games_60_plus",
    "minutes",
    "minutes_per_game",
    "goals_per_90",
    "assists_per_90",
    "goal_contributions_per_90",
    "yellow_cards",
    "red_cards",
    "league_minutes",
    "international_cup_minutes",
    "clubs_count",
]
CATEGORICAL = ["position", "sub_position", "foot", "main_league_id"]
FEATURES = NUMERIC + CATEGORICAL
SEED = 42


def encode(rows: list[dict]) -> tuple[list[list[float]], dict[str, dict[str, int]]]:
    """Matriz de features: numéricas tal cual (None -> NaN) y categóricas como enteros.

    HistGradientBoostingRegressor maneja NaN y categorías codificadas como enteros.
    """
    codes: dict[str, dict[str, int]] = {c: {} for c in CATEGORICAL}
    matrix = []
    for row in rows:
        values = [math.nan if row[c] is None else float(row[c]) for c in NUMERIC]
        for c in CATEGORICAL:
            value = row[c]
            values.append(math.nan if value is None else codes[c].setdefault(str(value), len(codes[c])))
        matrix.append(values)
    return matrix, codes


def split(n: int, eval_fraction: float = 0.2) -> tuple[list[int], list[int]]:
    """Índices de entrenamiento y evaluación, al azar pero reproducible (como data_split RANDOM)."""
    indices = list(range(n))
    random.Random(SEED).shuffle(indices)
    cut = int(n * (1 - eval_fraction))
    return indices[:cut], indices[cut:]


def train(rows: list[dict], prediction_season: int) -> dict:
    """Entrena con las temporadas anteriores a `prediction_season` y predice esa temporada."""
    import numpy as np
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.inspection import permutation_importance
    from sklearn.metrics import mean_absolute_error, median_absolute_error, r2_score

    matrix, _ = encode(rows)
    X = np.array(matrix)
    y = np.array([math.log(r["market_value_eur"]) for r in rows])
    seasons = np.array([r["season"] for r in rows])

    history = np.flatnonzero(seasons < prediction_season)
    target = np.flatnonzero(seasons == prediction_season)
    train_idx, eval_idx = split(len(history))
    train_idx, eval_idx = history[train_idx], history[eval_idx]

    model = HistGradientBoostingRegressor(
        max_iter=300,
        early_stopping=True,
        random_state=SEED,
        categorical_features=[FEATURES.index(c) for c in CATEGORICAL],
    )
    model.fit(X[train_idx], y[train_idx])

    predicted_eval = model.predict(X[eval_idx])
    evaluation = {
        "r2_score": float(r2_score(y[eval_idx], predicted_eval)),
        "mean_absolute_error": float(mean_absolute_error(y[eval_idx], predicted_eval)),
        "median_absolute_error": float(median_absolute_error(y[eval_idx], predicted_eval)),
        "train_rows": len(train_idx),
        "eval_rows": len(eval_idx),
        "prediction_season": prediction_season,
    }
    importance = permutation_importance(
        model, X[eval_idx], y[eval_idx], n_repeats=5, random_state=SEED, scoring="r2"
    )
    features = [
        {"feature": name, "attribution": round(float(score), 6)}
        for name, score in sorted(
            zip(FEATURES, importance.importances_mean, strict=True), key=lambda pair: -pair[1]
        )
    ]
    predictions = [
        {
            "player_id": rows[i]["player_id"],
            "season": int(seasons[i]),
            "actual_value_eur": rows[i]["market_value_eur"],
            "predicted_value_eur": round(math.exp(value)),
        }
        for i, value in zip(target, model.predict(X[target]), strict=True)
    ]
    return {"evaluation": evaluation, "features": features, "predictions": predictions}


def read_features(dataset: str) -> tuple[list[dict], int]:
    """Filas para el modelo (con valor y minutos mínimos) y la temporada a predecir."""
    from google.cloud import bigquery

    client = bigquery.Client(project=config.GCP_PROJECT_ID, location=config.BQ_LOCATION)
    table = f"`{config.GCP_PROJECT_ID}.{dataset}.int_player_value_features`"
    sql = f"""
        select player_id, market_value_eur, {", ".join(FEATURES)}
        from {table}
        where market_value_eur > 0 and minutes >= {config.ML_MIN_MINUTES}
    """
    rows = [dict(r) for r in client.query(sql).result()]
    prediction_season = max(r["season"] for r in rows)
    return rows, prediction_season


def write_table(table: str, rows: list[dict]) -> None:
    """Reemplaza la tabla con un load job (gratis)."""
    from google.cloud import bigquery

    client = bigquery.Client(project=config.GCP_PROJECT_ID, location=config.BQ_LOCATION)
    client.create_dataset(config.BQ_ML_DATASET, exists_ok=True)
    job_config = bigquery.LoadJobConfig(
        autodetect=True, write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE
    )
    table_id = f"{config.GCP_PROJECT_ID}.{config.BQ_ML_DATASET}.{table}"
    client.load_table_from_json(rows, table_id, job_config=job_config).result()
    log.info("Escritas %d filas en %s", len(rows), table_id)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dataset", default="intermediate", help="Dataset de int_player_value_features")
    args = parser.parse_args()

    rows, prediction_season = read_features(args.dataset)
    log.info("Entrenando con %d filas; temporada a predecir: %s", len(rows), prediction_season)
    result = train(rows, prediction_season)
    trained_at = datetime.now(UTC).isoformat()
    write_table("model_predictions", result["predictions"])
    write_table("model_evaluation", [{"evaluated_at": trained_at, **result["evaluation"]}])
    write_table("feature_importance", result["features"])
    print(json.dumps(result["evaluation"], indent=2))


if __name__ == "__main__":
    main()
