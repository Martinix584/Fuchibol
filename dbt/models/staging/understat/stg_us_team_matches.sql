{{ config(tags=['current']) }}
{# Una fila por equipo y partido. `history` de Understat trae xG, xGA y xPts. #}
with source as (

    select * from {{ source('understat', 'team_matches') }}
    where true
    qualify row_number() over (
        partition by league, season, team_id, match_date order by _ingested_at desc
    ) = 1

)

select
    cast(league as string) as league_code,
    cast(league_name as string) as league_name,
    safe_cast(season as int64) as season,
    cast(season_name as string) as season_name,
    safe_cast(team_id as int64) as team_id,
    cast(team_title as string) as team_name,
    safe_cast(match_date as timestamp) as match_date,
    cast(h_a as string) as home_away,
    safe_cast(xg as float64) as xg,
    safe_cast(xga as float64) as xga,
    safe_cast(npxg as float64) as npxg,
    safe_cast(npxga as float64) as npxga,
    safe_cast(ppda_att as int64) as ppda_att,
    safe_cast(ppda_def as int64) as ppda_def,
    safe_cast(ppda_allowed_att as int64) as ppda_allowed_att,
    safe_cast(ppda_allowed_def as int64) as ppda_allowed_def,
    safe_cast(deep as int64) as deep,
    safe_cast(deep_allowed as int64) as deep_allowed,
    safe_cast(scored as int64) as goals_for,
    safe_cast(missed as int64) as goals_against,
    safe_cast(xpts as float64) as xpts,
    cast(result as string) as result,
    safe_cast(wins as int64) as wins,
    safe_cast(draws as int64) as draws,
    safe_cast(loses as int64) as losses,
    safe_cast(pts as int64) as points,
    safe_cast(npxgd as float64) as npxgd,
    _ingested_at
from source
