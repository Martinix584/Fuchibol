{{ config(tags=['current']) }}
{# Una fila por jugador y liga-temporada de Understat. El raw guarda strings: casteamos. #}
with source as (

    select * from {{ source('understat', 'players_season') }}
    where true
    qualify row_number() over (
        partition by league, season, player_id order by _ingested_at desc
    ) = 1

)

select
    safe_cast(player_id as int64) as player_id,
    cast(player_name as string) as player_name,
    cast(league as string) as league_code,
    cast(league_name as string) as league_name,
    safe_cast(season as int64) as season,
    cast(season_name as string) as season_name,
    cast(team_title as string) as team_name,
    cast(position as string) as position,
    {{ to_int('games') }} as games,
    {{ to_int('minutes') }} as minutes,
    {{ to_int('goals') }} as goals,
    {{ to_int('assists') }} as assists,
    {{ to_int('shots') }} as shots,
    {{ to_int('key_passes') }} as key_passes,
    {{ to_int('yellow_cards') }} as yellow_cards,
    {{ to_int('red_cards') }} as red_cards,
    {{ to_int('non_penalty_goals') }} as non_penalty_goals,
    safe_cast(xg as float64) as xg,
    safe_cast(xa as float64) as xa,
    safe_cast(npxg as float64) as npxg,
    safe_cast(xg_chain as float64) as xg_chain,
    safe_cast(xg_buildup as float64) as xg_buildup,
    _ingested_at
from source
