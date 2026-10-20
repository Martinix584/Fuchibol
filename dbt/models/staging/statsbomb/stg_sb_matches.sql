{# matches es append-only (una foto por ingesta): se queda con la última versión de cada partido #}
with source as (

    select *
    from {{ source('statsbomb', 'matches') }}
    where match_status = 'available'
    qualify row_number() over (partition by match_id order by _ingested_at desc) = 1

)

select
    match_id,
    match_date,
    competition.competition_id,
    competition.competition_name,
    season.season_id,
    season.season_name,
    competition_stage.name as competition_stage,
    match_week,
    home_team.home_team_id as home_team_id,
    home_team.home_team_name as home_team_name,
    away_team.away_team_id as away_team_id,
    away_team.away_team_name as away_team_name,
    home_team.managers[safe_offset(0)].name as home_manager_name,
    away_team.managers[safe_offset(0)].name as away_manager_name,
    home_score,
    away_score,
    stadium.name as stadium_name,
    referee.name as referee_name,
    last_updated

from source
