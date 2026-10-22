{#
  Grupo de posición de cada jugador por competición-temporada: el de más minutos.
  Duración de cada tramo de la alineación con el reloj acumulado de StatsBomb (el que no
  tiene fin dura hasta el final del partido). No recorta descuentos ni une tramos
  superpuestos como int_sb_player_match_minutes: para elegir el grupo alcanza.
#}
with segments as (

    select
        lineups.match_id,
        lineups.player_id,
        position.position_id,
        {{ mmss_to_seconds('position.`from`') }} as from_seconds,
        {{ mmss_to_seconds('position.`to`') }} as to_seconds
    from {{ ref('stg_sb_lineups') }} as lineups
    cross join unnest(lineups.positions) as position

),

match_end as (

    select match_id, max(end_seconds) as end_seconds
    from {{ ref('int_sb_match_periods') }}
    group by match_id

),

group_seconds as (

    select
        segments.player_id,
        matches.competition_id,
        matches.season_id,
        position_map.position_group,
        sum(coalesce(segments.to_seconds, match_end.end_seconds) - segments.from_seconds) as seconds
    from segments
    inner join match_end using (match_id)
    inner join {{ ref('stg_sb_matches') }} as matches using (match_id)
    inner join {{ ref('position_groups') }} as position_map using (position_id)
    group by 1, 2, 3, 4

)

select player_id, competition_id, season_id, position_group
from group_seconds
where seconds > 0
qualify row_number() over (
    partition by player_id, competition_id, season_id order by seconds desc, position_group
) = 1
