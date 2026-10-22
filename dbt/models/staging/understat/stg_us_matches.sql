{{ config(tags=['current']) }}
{# Partidos de Understat: goles y xG de cada lado. Base para la tabla de partidos. #}
with source as (

    select * from {{ source('understat', 'matches') }}
    where true
    qualify row_number() over (
        partition by match_id order by _ingested_at desc
    ) = 1

)

select
    cast(match_id as string) as match_id,
    cast(league as string) as league_code,
    cast(league_name as string) as league_name,
    safe_cast(season as int64) as season,
    cast(season_name as string) as season_name,
    coalesce(safe_cast(is_result as bool), false) as is_result,
    safe_cast(match_date as timestamp) as match_date,
    safe_cast(home_team_id as int64) as home_team_id,
    cast(home_team_title as string) as home_team_name,
    cast(home_team_short_title as string) as home_team_short_name,
    safe_cast(away_team_id as int64) as away_team_id,
    cast(away_team_title as string) as away_team_name,
    cast(away_team_short_title as string) as away_team_short_name,
    safe_cast(home_goals as int64) as home_goals,
    safe_cast(away_goals as int64) as away_goals,
    safe_cast(home_xg as float64) as home_xg,
    safe_cast(away_xg as float64) as away_xg,
    safe_cast(forecast_win as float64) as forecast_win,
    safe_cast(forecast_draw as float64) as forecast_draw,
    safe_cast(forecast_loss as float64) as forecast_loss,
    _ingested_at
from source
