{# Perfil del jugador + totales de carrera (en las competiciones cubiertas por el dataset). #}
with career as (

    select
        player_id,
        min(season) as first_season,
        max(season) as last_season_played,
        sum(games) as career_games,
        sum(minutes) as career_minutes,
        sum(goals) as career_goals,
        sum(assists) as career_assists,
        sum(yellow_cards) as career_yellow_cards,
        sum(red_cards) as career_red_cards
    from {{ ref('int_player_season_stats') }}
    group by player_id

)

select
    players.player_id,
    players.player_name,
    players.position,
    players.sub_position,
    players.foot,
    players.height_in_cm,
    players.date_of_birth,
    players.country_of_citizenship,
    players.country_of_birth,
    players.current_club_id,
    players.current_club_name,
    players.contract_expiration_date,
    players.agent_name,
    players.international_caps,
    players.international_goals,
    players.market_value_eur,
    players.highest_market_value_eur,
    players.image_url,
    career.first_season,
    career.last_season_played,
    coalesce(career.career_games, 0) as career_games,
    coalesce(career.career_minutes, 0) as career_minutes,
    coalesce(career.career_goals, 0) as career_goals,
    coalesce(career.career_assists, 0) as career_assists,
    career.career_yellow_cards,
    career.career_red_cards,
    round(safe_divide(career.career_goals, career.career_games), 3) as goals_per_game,
    {{ per_90('career.career_goals', 'career.career_minutes') }} as goals_per_90,
    {{ per_90('career.career_assists', 'career.career_minutes') }} as assists_per_90,
    {{ per_90('career.career_goals + career.career_assists', 'career.career_minutes') }}
        as goal_contributions_per_90

from {{ ref('stg_players') }} as players
left join career using (player_id)
