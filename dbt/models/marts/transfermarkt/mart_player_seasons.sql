{{ config(cluster_by=['player_id', 'season']) }}

{# Stats de cada jugador por temporada: partidos, minutos, goles, asistencias, por 90 y valor. #}
select
    player_id,
    player_name,
    season,
    age,
    position,
    sub_position,
    country_of_citizenship,
    main_club_id,
    main_club_name,
    main_league_id,
    main_league_name,
    main_league_country,
    clubs_count,
    games,
    games_60_plus,
    minutes,
    minutes_per_game,
    goals,
    assists,
    goals_per_90,
    assists_per_90,
    goal_contributions_per_90,
    yellow_cards,
    red_cards,
    league_minutes,
    international_cup_minutes,
    market_value_eur as market_value_end_of_season_eur

from {{ ref('int_player_value_features') }}
