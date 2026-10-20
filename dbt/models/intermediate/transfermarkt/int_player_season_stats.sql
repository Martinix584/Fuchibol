{# Una fila por jugador y temporada, sumando todos sus clubes y competiciones. #}
with appearances as (

    select
        appearances.*,
        games.season,
        games.competition_type
    from {{ ref('stg_appearances') }} as appearances
    inner join {{ ref('stg_games') }} as games using (game_id)

),

main_club as (

    select player_id, season, club_id as main_club_id
    from appearances
    group by player_id, season, club_id
    qualify row_number() over (
        partition by player_id, season order by sum(minutes_played) desc, club_id
    ) = 1

),

main_league as (

    select player_id, season, competition_id as main_league_id
    from appearances
    where competition_type = 'domestic_league'
    group by player_id, season, competition_id
    qualify row_number() over (
        partition by player_id, season order by sum(minutes_played) desc, competition_id
    ) = 1

),

totals as (

    select
        player_id,
        season,
        count(*) as games,
        countif(minutes_played >= 60) as games_60_plus,
        sum(minutes_played) as minutes,
        sum(goals) as goals,
        sum(assists) as assists,
        sum(yellow_cards) as yellow_cards,
        sum(red_cards) as red_cards,
        sum(if(competition_type = 'domestic_league', minutes_played, 0)) as league_minutes,
        sum(if(competition_type = 'international_cup', minutes_played, 0)) as international_cup_minutes,
        count(distinct club_id) as clubs_count
    from appearances
    group by player_id, season

)

select
    totals.*,
    {{ per_90('goals', 'minutes') }} as goals_per_90,
    {{ per_90('assists', 'minutes') }} as assists_per_90,
    {{ per_90('goals + assists', 'minutes') }} as goal_contributions_per_90,
    round(safe_divide(minutes, games), 1) as minutes_per_game,
    main_club.main_club_id,
    main_league.main_league_id

from totals
left join main_club using (player_id, season)
left join main_league using (player_id, season)
