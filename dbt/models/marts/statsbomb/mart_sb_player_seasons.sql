{#
  Un jugador por competición-temporada: totales, cada 90 y eficiencia.
  Las métricas cada 90 solo son confiables con muchos minutos: filtrar por minutes_played
  (en Power BI hay un slicer de minutos mínimos).
#}
{% set totals = [
    'shots', 'shots_on_target', 'goals', 'penalty_goals', 'headed_goals', 'xg', 'npxg', 'xa',
    'passes', 'passes_completed', 'progressive_passes', 'passes_into_final_third', 'passes_into_box',
    'key_passes', 'assists', 'crosses', 'through_balls', 'carries', 'progressive_carries', 'carries_into_box',
    'dribbles_attempted', 'dribbles_completed', 'pressures', 'counterpressures', 'tackles', 'tackles_won',
    'interceptions', 'ball_recoveries', 'clearances', 'blocks', 'dispossessed', 'fouls_committed',
    'fouls_won', 'yellow_cards', 'red_cards', 'saves'
] %}
{% set per_90_columns = [
    'goals', 'npxg', 'xa', 'shots', 'key_passes', 'progressive_passes', 'progressive_carries',
    'passes_into_box', 'dribbles_completed', 'pressures', 'tackles_won', 'interceptions', 'ball_recoveries'
] %}

with player_seasons as (

    select
        player_id,
        competition_id,
        season_id,
        any_value(competition_name) as competition_name,
        any_value(season_name) as season_name,
        any_value(player_name) as player_name,
        any_value(player_display_name) as player_display_name,
        any_value(country_name) as country_name,
        string_agg(distinct team_name, ', ') as teams,
        count(*) as matches_played,
        countif(is_starter) as starts,
        sum(minutes_played) as minutes_played,
        {% for column in totals %}
        sum({{ column }}) as {{ column }},
        {% endfor %}
        sum(goals) - sum(penalty_goals) as non_penalty_goals
    from {{ ref('fct_sb_player_matches') }}
    group by player_id, competition_id, season_id

)

select
    player_seasons.*,
    {% for column in per_90_columns %}
    {{ per_90('player_seasons.' ~ column, 'player_seasons.minutes_played') }} as {{ column }}_per_90,
    {% endfor %}
    {{ per_90('player_seasons.non_penalty_goals', 'player_seasons.minutes_played') }} as non_penalty_goals_per_90,
    {{ per_90('player_seasons.npxg + player_seasons.xa', 'player_seasons.minutes_played') }} as npxg_plus_xa_per_90,
    round(player_seasons.non_penalty_goals - player_seasons.npxg, 2) as goals_minus_npxg,
    round(safe_divide(player_seasons.npxg, player_seasons.shots - player_seasons.penalty_goals), 3)
        as npxg_per_shot,
    round(safe_divide(player_seasons.passes_completed, player_seasons.passes), 3) as pass_completion,
    round(safe_divide(player_seasons.dribbles_completed, player_seasons.dribbles_attempted), 3)
        as dribble_success,
    round(safe_divide(player_seasons.shots_on_target, player_seasons.shots), 3) as shot_accuracy,
    id_map.tm_player_id

from player_seasons
left join {{ ref('int_player_id_map') }} as id_map
    on id_map.sb_player_id = player_seasons.player_id
