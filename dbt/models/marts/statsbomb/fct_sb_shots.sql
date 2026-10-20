{{ config(cluster_by=['competition_id', 'team_id']) }}

{# Un tiro por fila con coordenadas: alimenta el mapa de tiros de Power BI. #}
select
    shots.*,
    matches.match_date,
    matches.competition_id,
    matches.competition_name,
    matches.season_id,
    matches.season_name,
    if(shots.team_id = matches.home_team_id, matches.away_team_name, matches.home_team_name) as opponent_name,
    case
        when shots.xg >= 0.3 then 'Muy clara'
        when shots.xg >= 0.1 then 'Clara'
        else 'Baja'
    end as chance_quality

from {{ ref('int_sb_shots') }} as shots
inner join {{ ref('stg_sb_matches') }} as matches using (match_id)
