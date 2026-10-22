{# Todas las métricas de un jugador en un partido. Base de los marts de jugadores. #}
with events as (

    select * from {{ ref('stg_sb_events') }}
    where player_id is not null
        and period <= 4

),

shot_stats as (

    select
        match_id,
        player_id,
        count(*) as shots,
        countif(is_on_target) as shots_on_target,
        countif(is_goal) as goals,
        countif(is_goal and is_penalty) as penalty_goals,
        countif(is_penalty) as penalties_taken,
        sum(xg) as xg,
        sum(if(is_penalty, 0, xg)) as npxg,
        countif(is_goal and body_part = 'Head') as headed_goals
    from {{ ref('int_sb_shots') }}
    group by match_id, player_id

),

pass_stats as (

    select
        match_id,
        player_id,
        count(*) as passes,
        countif(is_complete) as passes_completed,
        countif(is_progressive) as progressive_passes,
        countif(is_into_final_third) as passes_into_final_third,
        countif(is_into_box) as passes_into_box,
        countif(is_key_pass) as key_passes,
        countif(is_assist) as assists,
        countif(is_cross) as crosses,
        countif(is_through_ball) as through_balls,
        sum(xa) as xa
    from {{ ref('int_sb_passes') }}
    group by match_id, player_id

),

carry_stats as (

    select
        match_id,
        player_id,
        count(*) as carries,
        countif(
            carry_detail.end_location[safe_offset(0)] >= 60
            and {{ distance_to_goal('carry_detail.end_location[safe_offset(0)]', 'carry_detail.end_location[safe_offset(1)]') }}
                <= 0.75 * {{ distance_to_goal('x', 'y') }}
            and {{ distance_to_goal('x', 'y') }}
                - {{ distance_to_goal('carry_detail.end_location[safe_offset(0)]', 'carry_detail.end_location[safe_offset(1)]') }}
                >= 5
        ) as progressive_carries,
        countif(
            {{ in_box('carry_detail.end_location[safe_offset(0)]', 'carry_detail.end_location[safe_offset(1)]') }}
            and not {{ in_box('x', 'y') }}
        ) as carries_into_box
    from events
    where event_type = 'Carry'
    group by match_id, player_id

),

xt_stats as (

    select match_id, player_id, sum(xt_added) as xt_added
    from {{ ref('int_sb_xt_actions') }}
    group by match_id, player_id

),

other_stats as (

    select
        match_id,
        player_id,
        countif(event_type = 'Dribble') as dribbles_attempted,
        countif(event_type = 'Dribble' and dribble_detail.outcome.name = 'Complete') as dribbles_completed,
        countif(event_type = 'Pressure') as pressures,
        countif(event_type = 'Pressure' and counterpress) as counterpressures,
        countif(event_type = 'Duel' and duel_detail.type.name = 'Tackle') as tackles,
        countif(
            event_type = 'Duel'
            and duel_detail.type.name = 'Tackle'
            and duel_detail.outcome.name in ('Won', 'Success', 'Success In Play', 'Success Out')
        ) as tackles_won,
        countif(event_type = 'Interception') as interceptions,
        countif(event_type = 'Ball Recovery' and not coalesce(ball_recovery_detail.recovery_failure, false))
            as ball_recoveries,
        countif(event_type = 'Clearance') as clearances,
        countif(event_type = 'Block') as blocks,
        countif(event_type = 'Dispossessed') as dispossessed,
        countif(event_type = 'Miscontrol') as miscontrols,
        countif(event_type = 'Foul Committed') as fouls_committed,
        countif(event_type = 'Foul Won') as fouls_won,
        countif(
            coalesce(foul_committed_detail.card.name, bad_behaviour_detail.card.name) = 'Yellow Card'
        ) as yellow_cards,
        countif(
            coalesce(foul_committed_detail.card.name, bad_behaviour_detail.card.name) in ('Red Card', 'Second Yellow')
        ) as red_cards,
        countif(event_type = 'Goal Keeper' and goalkeeper_detail.type.name in ('Shot Saved', 'Penalty Saved'))
            as saves
    from events
    group by match_id, player_id

),

stat_columns as (

    select
        minutes.match_id,
        minutes.team_id,
        minutes.player_id,
        minutes.is_starter,
        minutes.minutes_played,
        {% for column in [
            'shots', 'shots_on_target', 'goals', 'penalty_goals', 'penalties_taken', 'headed_goals',
            'passes', 'passes_completed', 'progressive_passes', 'passes_into_final_third', 'passes_into_box',
            'key_passes', 'assists', 'crosses', 'through_balls',
            'carries', 'progressive_carries', 'carries_into_box',
            'dribbles_attempted', 'dribbles_completed', 'pressures', 'counterpressures', 'tackles',
            'tackles_won', 'interceptions', 'ball_recoveries', 'clearances', 'blocks', 'dispossessed',
            'miscontrols', 'fouls_committed', 'fouls_won', 'yellow_cards', 'red_cards', 'saves'
        ] %}
        coalesce({{ column }}, 0) as {{ column }},
        {% endfor %}
        round(coalesce(shot_stats.xg, 0), 4) as xg,
        round(coalesce(shot_stats.npxg, 0), 4) as npxg,
        round(coalesce(pass_stats.xa, 0), 4) as xa,
        round(coalesce(xt_stats.xt_added, 0), 4) as xt_added,
        {#
          PAdj de StatsBomb: acciones * 2 / (1 + e^(-0.1 * (posesión - 50))). Un equipo con poca
          pelota defiende más y suma más quites solo por eso; el ajuste lo lleva a una base de 50 %.
          https://blogarchive.statsbomb.com/articles/soccer/introducing-possession-adjusted-player-stats/
          (el artículo la da para quites; acá va sobre quites + intercepciones, como en sus radares).
        #}
        round(
            (coalesce(other_stats.tackles, 0) + coalesce(other_stats.interceptions, 0))
            * 2 / (1 + exp(-0.1 * (possession.possession_pct - 50))),
            3
        ) as padj_tackles_interceptions
    from {{ ref('int_sb_player_match_minutes') }} as minutes
    left join shot_stats using (match_id, player_id)
    left join pass_stats using (match_id, player_id)
    left join carry_stats using (match_id, player_id)
    left join xt_stats using (match_id, player_id)
    left join other_stats using (match_id, player_id)
    left join {{ ref('int_sb_team_match_possession') }} as possession using (match_id, team_id)
    where minutes.minutes_played > 0

)

select * from stat_columns
