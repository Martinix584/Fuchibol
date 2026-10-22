{{ config(tags=['current']) }}
{# Tabla de equipos por liga-temporada: puntos reales vs. xPts de Understat. #}
select
    league_code,
    league_name,
    season,
    season_name,
    team_id,
    any_value(team_name) as team_name,
    count(*) as matches,
    sum(wins) as wins,
    sum(draws) as draws,
    sum(losses) as losses,
    sum(goals_for) as goals_for,
    sum(goals_against) as goals_against,
    sum(points) as points,
    round(sum(xg), 2) as xg_for,
    round(sum(xga), 2) as xg_against,
    round(sum(xg) - sum(xga), 2) as xg_diff,
    round(sum(xpts), 2) as xpts,
    round(sum(points) - sum(xpts), 2) as points_minus_xpts,
    round(avg(xg), 3) as xg_per_match,
    round(avg(xga), 3) as xg_against_per_match,
    round(avg(ppda_att), 2) as ppda_att,
    round(avg(ppda_def), 2) as ppda_def,
    sum(deep) as deep_completions,
    sum(deep_allowed) as deep_allowed
from {{ ref('stg_us_team_matches') }}
group by league_code, league_name, season, season_name, team_id
