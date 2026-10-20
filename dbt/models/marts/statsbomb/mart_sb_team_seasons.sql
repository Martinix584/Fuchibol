{# Tabla de posiciones real vs. "merecida" por xG: quién tuvo suerte y quién no. #}
select
    team_id,
    competition_id,
    season_id,
    any_value(team_name) as team_name,
    any_value(competition_name) as competition_name,
    any_value(season_name) as season_name,
    count(*) as matches,
    countif(result = 'Ganó') as wins,
    countif(result = 'Empató') as draws,
    countif(result = 'Perdió') as losses,
    sum(goals_for) as goals_for,
    sum(goals_against) as goals_against,
    sum(goals_for) - sum(goals_against) as goal_difference,
    round(sum(xg_for), 2) as xg_for,
    round(sum(xg_against), 2) as xg_against,
    round(sum(xg_for) - sum(xg_against), 2) as xg_difference,
    sum(points) as points,
    round(sum(xpts), 1) as xpts,
    round(sum(points) - sum(xpts), 1) as points_minus_xpts,
    round(sum(goals_for) - sum(xg_for), 2) as finishing_over_xg,
    round(sum(xg_against) - sum(goals_against), 2) as goalkeeping_over_xg

from {{ ref('fct_sb_team_matches') }}
group by team_id, competition_id, season_id
