{{ config(materialized='table', cluster_by=['match_id', 'event_type']) }}

{#
  Un evento por fila. Se materializa como tabla (es la base de todo lo demás) y se queda
  solo con la última ingesta de cada partido: reprocesar un partido nunca duplica eventos.
  Los detalles por tipo (pass, shot, carry...) quedan como STRUCT para los modelos de abajo.
#}
with source as (

    select *
    from {{ source('statsbomb', 'events') }}
    where true
    qualify _ingested_at = max(_ingested_at) over (partition by match_id)

)

select
    id as event_id,
    match_id,
    `index` as event_index,
    period,
    minute,
    second,
    minute * 60 + second as clock_seconds,
    type.name as event_type,
    possession,
    possession_team.id as possession_team_id,
    play_pattern.name as play_pattern,
    team.id as team_id,
    team.name as team_name,
    player.id as player_id,
    player.name as player_name,
    position.name as position_name,
    location[safe_offset(0)] as x,
    location[safe_offset(1)] as y,
    duration,
    coalesce(under_pressure, false) as under_pressure,
    coalesce(counterpress, false) as counterpress,
    `pass` as pass_detail,
    shot as shot_detail,
    carry as carry_detail,
    dribble as dribble_detail,
    duel as duel_detail,
    interception as interception_detail,
    ball_recovery as ball_recovery_detail,
    goalkeeper as goalkeeper_detail,
    foul_committed as foul_committed_detail,
    bad_behaviour as bad_behaviour_detail,
    substitution as substitution_detail

from source
