{# Predicción del modelo para la última temporada (que no vio al entrenar). #}
select
    player_id,
    season,
    market_value_eur as actual_value_eur,
    round(exp(predicted_log_market_value)) as predicted_value_eur

from ml.predict(
    model {{ market_value_model() }},
    (
        select player_id, market_value_eur, {{ market_value_features() }}
        from {{ ref('int_player_value_features') }}
        where market_value_eur > 0
            and minutes >= {{ var('ml_min_minutes') }}
            and season = {{ prediction_season_sql() }}
    )
)
