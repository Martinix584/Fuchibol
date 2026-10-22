import math
import random

from ingestion.ml import CATEGORICAL, FEATURES, NUMERIC, encode, split, train


def row(player_id, season, minutes, value, position="Attack"):
    r = {c: 0 for c in NUMERIC}
    r.update({c: None for c in CATEGORICAL})
    r.update(
        player_id=player_id,
        season=season,
        minutes=minutes,
        position=position,
        market_value_eur=value,
    )
    return r


def test_encode_numeric_nan_and_categorical_codes():
    rows = [
        row(1, 2024, 900, 1e6, "Attack"),
        row(2, 2024, 900, 1e6, "Defender"),
        row(3, 2024, 900, 1e6, None),
    ]
    rows[2]["age"] = None
    matrix, codes = encode(rows)
    position = FEATURES.index("position")
    assert [m[position] for m in matrix[:2]] == [0, 1]
    assert math.isnan(matrix[2][position]) and math.isnan(matrix[2][FEATURES.index("age")])
    assert codes["position"] == {"Attack": 0, "Defender": 1}


def test_split_is_reproducible_and_disjoint():
    train_idx, eval_idx = split(100)
    assert (train_idx, eval_idx) == split(100)
    assert len(train_idx) == 80 and len(eval_idx) == 20 and not set(train_idx) & set(eval_idx)


def test_train_learns_value_and_predicts_only_last_season():
    rng = random.Random(0)
    rows = [
        row(i, season, minutes, math.exp(10 + minutes / 1000 + rng.gauss(0, 0.05)))
        for i, (season, minutes) in enumerate(
            (s, rng.randint(900, 3400)) for s in (2022, 2023, 2024, 2025) for _ in range(150)
        )
    ]
    result = train(rows, prediction_season=2025)
    assert result["evaluation"]["r2_score"] > 0.8
    assert {p["season"] for p in result["predictions"]} == {2025}
    assert len(result["predictions"]) == 150
    assert result["features"][0]["feature"] == "minutes"
