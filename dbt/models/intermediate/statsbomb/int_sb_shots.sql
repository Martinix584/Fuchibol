{# Tiros (sin la tanda de penales) con su xG, quién dio el pase previo y la distancia al arco. #}
with events as (

    select * from {{ ref('stg_sb_events') }}

),

key_passes as (

    select event_id, player_id, player_name
    from events
    where event_type = 'Pass'

)

select
    shots.event_id as shot_id,
    shots.match_id,
    shots.period,
    shots.minute,
    shots.second,
    shots.team_id,
    shots.team_name,
    shots.player_id,
    shots.player_name,
    shots.position_name,
    shots.play_pattern,
    shots.x,
    shots.y,
    shots.shot_detail.end_location[safe_offset(0)] as end_x,
    shots.shot_detail.end_location[safe_offset(1)] as end_y,
    shots.shot_detail.end_location[safe_offset(2)] as end_z,
    round({{ distance_to_goal('shots.x', 'shots.y') }}, 1) as distance_to_goal,
    shots.shot_detail.statsbomb_xg as xg,
    shots.shot_detail.outcome.name as outcome,
    shots.shot_detail.outcome.name = 'Goal' as is_goal,
    shots.shot_detail.outcome.name in ('Goal', 'Saved', 'Saved To Post') as is_on_target,
    shots.shot_detail.type.name as shot_type,
    shots.shot_detail.type.name = 'Penalty' as is_penalty,
    shots.shot_detail.body_part.name as body_part,
    shots.shot_detail.technique.name as technique,
    coalesce(shots.shot_detail.first_time, false) as is_first_time,
    coalesce(shots.shot_detail.one_on_one, false) as is_one_on_one,
    shots.under_pressure,
    shots.shot_detail.key_pass_id,
    key_passes.player_id as assister_id,
    key_passes.player_name as assister_name

from events as shots
left join key_passes
    on key_passes.event_id = shots.shot_detail.key_pass_id
where shots.event_type = 'Shot'
    and shots.period <= 4
