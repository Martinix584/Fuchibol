{{ config(tags=['current']) }}
{#
  Tabla de equipos de la temporada actual. Por ahora solo Understat: SofaScore cubre
  xG/xA por jugador, no una tabla de equipos. Si se usa el respaldo de SofaScore para
  las 5 grandes, esta tabla sigue mostrando el último Understat (xg_source lo aclara).
#}
select
    team_id,
    team_name,
    league_code,
    league_name,
    season,
    season_name,
    matches,
    wins,
    draws,
    losses,
    goals_for,
    goals_against,
    points,
    xg_for,
    xg_against,
    xg_diff,
    xpts,
    points_minus_xpts,
    xg_per_match,
    xg_against_per_match,
    ppda_att,
    ppda_def,
    deep_completions,
    deep_allowed,
    'understat' as xg_source
from {{ ref('int_us_team_season') }}
