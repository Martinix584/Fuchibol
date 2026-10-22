{# Predicción del modelo para la última temporada (que no vio al entrenar). La escribe ingestion/ml.py. #}
select
    player_id,
    season,
    actual_value_eur,
    predicted_value_eur
from {{ source('ml', 'model_predictions') }}
