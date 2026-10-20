{#
  Modelo de valor de mercado con BigQuery ML.

  Aprende el valor (en log) a partir del rendimiento y el perfil del jugador en
  temporadas pasadas, y predice la última temporada completa. Si el modelo dice
  que un jugador "debería" valer bastante más de lo que vale -> subvaluado.

  Se entrena con:  dbt run-operation train_market_value_model
#}

{% macro ml_dataset() -%}
    {{ generate_schema_name('ml', none) | trim }}
{%- endmacro %}

{% macro market_value_model() -%}
    `{{ target.project }}.{{ ml_dataset() }}.market_value_model`
{%- endmacro %}

{# Features que usa el modelo: se comparten entre el entrenamiento y la predicción. #}
{% macro market_value_features() -%}
    season,
    age,
    position,
    sub_position,
    foot,
    height_in_cm,
    main_league_id,
    games,
    games_60_plus,
    minutes,
    minutes_per_game,
    goals_per_90,
    assists_per_90,
    goal_contributions_per_90,
    yellow_cards,
    red_cards,
    league_minutes,
    international_cup_minutes,
    clubs_count
{%- endmacro %}

{# Última temporada con valores de mercado: es la que se predice (y no se usa para entrenar). #}
{% macro prediction_season_sql() -%}
    (
        select max(season)
        from {{ ref('int_player_value_features') }}
        where market_value_eur is not null
    )
{%- endmacro %}

{% macro train_market_value_model() %}
    {% set ml_schema = api.Relation.create(database=target.project, schema=ml_dataset()) %}
    {% do adapter.create_schema(ml_schema) %}

    {% set sql %}
        create or replace model {{ market_value_model() }}
        options (
            model_type = 'BOOSTED_TREE_REGRESSOR',
            input_label_cols = ['log_market_value'],
            data_split_method = 'RANDOM',
            data_split_eval_fraction = 0.2,
            max_iterations = 100,
            early_stop = true,
            enable_global_explain = true
        ) as
        select
            {{ market_value_features() }},
            ln(market_value_eur) as log_market_value
        from {{ ref('int_player_value_features') }}
        where market_value_eur > 0
            and minutes >= {{ var('ml_min_minutes') }}
            and season < {{ prediction_season_sql() }}
    {% endset %}

    {{ log("Entrenando " ~ market_value_model() ~ " ...", info=true) }}
    {% do run_query(sql) %}
    {{ log("Modelo entrenado.", info=true) }}
{% endmacro %}
