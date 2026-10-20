{#
  Pases con las banderas que se usan en scouting:
  - progresivo: completado, en juego, termina en campo rival y deja la pelota al menos
    25% más cerca del arco (criterio simple y explícito; hay varias definiciones)
  - al último tercio / al área, pase clave (termina en tiro) y xA (xG del tiro que generó)
#}
with passes as (

    select
        event_id,
        match_id,
        period,
        team_id,
        player_id,
        player_name,
        play_pattern,
        x,
        y,
        pass_detail.end_location[safe_offset(0)] as end_x,
        pass_detail.end_location[safe_offset(1)] as end_y,
        pass_detail.length as length,
        pass_detail.height.name as height,
        pass_detail.type.name as pass_type,
        pass_detail.body_part.name as body_part,
        pass_detail.outcome.name as outcome,
        pass_detail.outcome is null as is_complete,
        coalesce(pass_detail.type.name in ('Corner', 'Free Kick', 'Throw-in', 'Kick Off', 'Goal Kick'), false)
            as is_set_piece,
        coalesce(pass_detail.`cross`, false) as is_cross,
        coalesce(pass_detail.switch, false) as is_switch,
        coalesce(pass_detail.through_ball, false) as is_through_ball,
        coalesce(pass_detail.cut_back, false) as is_cut_back,
        coalesce(pass_detail.shot_assist, false) or coalesce(pass_detail.goal_assist, false) as is_key_pass,
        coalesce(pass_detail.goal_assist, false) as is_assist,
        pass_detail.assisted_shot_id,
        pass_detail.recipient.id as recipient_id,
        under_pressure
    from {{ ref('stg_sb_events') }}
    where event_type = 'Pass'
        and period <= 4

)

select
    passes.*,
    passes.is_complete
        and not passes.is_set_piece
        and passes.end_x >= 60
        and {{ distance_to_goal('passes.end_x', 'passes.end_y') }}
            <= 0.75 * {{ distance_to_goal('passes.x', 'passes.y') }}
        as is_progressive,
    passes.is_complete and passes.x < 80 and passes.end_x >= 80 as is_into_final_third,
    passes.is_complete
        and {{ in_box('passes.end_x', 'passes.end_y') }}
        and not {{ in_box('passes.x', 'passes.y') }}
        as is_into_box,
    coalesce(shots.xg, 0) as xa

from passes
left join {{ ref('int_sb_shots') }} as shots
    on shots.shot_id = passes.assisted_shot_id
