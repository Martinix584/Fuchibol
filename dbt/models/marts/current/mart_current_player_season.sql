{{ config(tags=['current']) }}
{#
  Jugador x liga-temporada de la temporada actual. Las 5 grandes salen de Understat
  por defecto; Argentina sale siempre de SofaScore. Con
  `--vars '{xg_source_big5: sofascore}'` se reemplazan las 5 grandes por el respaldo
  manual de SofaScore. Nunca se mezclan fuentes en la misma fila: `xg_source` lo dice.
#}
{% set big5_source = var('xg_source_big5', 'understat') %}
{% if big5_source not in ['understat', 'sofascore'] %}
    {{ exceptions.raise_compiler_error("xg_source_big5 debe ser 'understat' o 'sofascore'") }}
{% endif %}

with understat as (

    select
        cast(player_id as string) as player_id,
        player_name,
        team_name,
        league_code,
        league_name,
        season,
        season_name,
        position,
        games,
        safe_cast(minutes as float64) as minutes,
        goals,
        assists,
        shots,
        key_passes,
        xg,
        xa,
        npxg,
        xg_chain,
        xg_buildup,
        xg_per_90,
        xa_per_90,
        npxg_per_90,
        shots_per_90,
        key_passes_per_90,
        goals_minus_xg,
        cast(null as int64) as team_id,
        'understat' as xg_source
    from {{ ref('int_us_player_season') }}
    where '{{ big5_source }}' = 'understat'

),

sofascore as (

    select
        cast(player_id as string) as player_id,
        player_name,
        team_name,
        league_code,
        league_name,
        season_year as season,
        season_name,
        position,
        appearances as games,
        minutes,
        goals,
        assists,
        shots,
        key_passes,
        xg,
        xa,
        cast(null as float64) as npxg,
        cast(null as float64) as xg_chain,
        cast(null as float64) as xg_buildup,
        xg_per_90,
        xa_per_90,
        cast(null as float64) as npxg_per_90,
        shots_per_90,
        key_passes_per_90,
        goals_minus_xg,
        team_id,
        'sofascore' as xg_source
    from {{ ref('int_ss_player_season') }}
    where league_code = 'ARG' or '{{ big5_source }}' = 'sofascore'

),

selected as (

    select * from understat
    union all
    select * from sofascore

)

select
    selected.*,
    concat(xg_source, ':', player_id) as player_key
from selected
