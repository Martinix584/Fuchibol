{# Un jugador convocado por partido. positions trae cada tramo que jugó (puesto, desde, hasta). #}
with source as (

    select *
    from {{ source('statsbomb', 'lineups') }}
    where true
    qualify _ingested_at = max(_ingested_at) over (partition by match_id)

)

select
    source.match_id,
    source.team_id,
    source.team_name,
    player.player_id,
    player.player_name,
    player.player_nickname,
    coalesce(player.player_nickname, player.player_name) as player_display_name,
    player.jersey_number,
    player.country.name as country_name,
    player.positions,
    player.cards,
    array_length(player.positions) > 0 as played,
    player.positions[safe_offset(0)].start_reason = 'Starting XI' as is_starter

from source
cross join unnest(source.lineup) as player
