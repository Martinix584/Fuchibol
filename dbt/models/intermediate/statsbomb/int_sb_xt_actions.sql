{#
  Expected Threat (xT): cuánto aumenta la chance de gol mover la pelota de una zona a otra.
  Grilla pública 12 x 8 de Karun Singh (seed xt_grid; https://karun.in/blog/expected-threat.html).
  Cuentan los pases completados en juego y las conducciones; xt_added = xT(fin) - xT(inicio),
  así que mover la pelota hacia atrás resta.
#}
with actions as (

    select event_id, match_id, team_id, player_id, 'Pass' as action_type, x, y, end_x, end_y
    from {{ ref('int_sb_passes') }}
    where is_complete and not is_set_piece

    union all

    select event_id, match_id, team_id, player_id, 'Carry' as action_type, x, y, end_x, end_y
    from {{ ref('int_sb_carries') }}

),

zoned as (

    select
        actions.*,
        {{ xt_zone('x', 12) }} as start_zone_x,
        {{ xt_zone('y', 8) }} as start_zone_y,
        {{ xt_zone('end_x', 12) }} as end_zone_x,
        {{ xt_zone('end_y', 8) }} as end_zone_y
    from actions
    where x is not null and y is not null and end_x is not null and end_y is not null

)

select
    zoned.*,
    start_grid.xt as start_xt,
    end_grid.xt as end_xt,
    round(end_grid.xt - start_grid.xt, 6) as xt_added
from zoned
inner join {{ ref('xt_grid') }} as start_grid
    on start_grid.zone_x = zoned.start_zone_x and start_grid.zone_y = zoned.start_zone_y
inner join {{ ref('xt_grid') }} as end_grid
    on end_grid.zone_x = zoned.end_zone_x and end_grid.zone_y = zoned.end_zone_y
