{{ config(cluster_by=['competition_id', 'player_id']) }}

{# Un jugador por partido, con todas sus métricas avanzadas y el contexto del partido. #}
select
    stats.*,
    matches.match_date,
    matches.competition_id,
    matches.competition_name,
    matches.season_id,
    matches.season_name,
    matches.competition_stage,
    lineups.player_name,
    lineups.player_display_name,
    lineups.country_name,
    lineups.team_name,
    if(stats.team_id = matches.home_team_id, matches.away_team_name, matches.home_team_name) as opponent_name,
    if(stats.team_id = matches.home_team_id, 'Local', 'Visitante') as venue

from {{ ref('int_sb_player_match_stats') }} as stats
inner join {{ ref('stg_sb_matches') }} as matches using (match_id)
inner join {{ ref('stg_sb_lineups') }} as lineups using (match_id, player_id)
