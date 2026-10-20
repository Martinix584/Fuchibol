{#
  Minutos jugados por jugador y partido, a partir de sus tramos en la alineación.
  Un tramo puede cruzar tiempos (ej. de 41:20 del 1.º a 64:09 del 2.º): se reparte entre
  cada tiempo usando el inicio y el fin reales de cada uno, así el descuento cuenta.
  Un partido con alargue completo da ~120 minutos más los descuentos.
#}
with positions as (

    select
        lineups.match_id,
        lineups.team_id,
        lineups.player_id,
        lineups.is_starter,
        {{ mmss_to_seconds('position.`from`') }} as from_seconds,
        {{ mmss_to_seconds('position.`to`') }} as to_seconds,
        position.from_period,
        position.to_period
    from {{ ref('stg_sb_lineups') }} as lineups
    cross join unnest(lineups.positions) as position

),

periods as (

    select * from {{ ref('int_sb_match_periods') }}

),

last_period as (

    select match_id, max(period) as last_period
    from periods
    group by match_id

),

segments as (

    {# Cada tramo, recortado a cada tiempo que cruza (en segundos de reloj) #}
    select
        positions.match_id,
        positions.team_id,
        positions.player_id,
        positions.is_starter,
        periods.period,
        if(periods.period = positions.from_period, positions.from_seconds, periods.start_seconds) as segment_start,
        if(
            periods.period = coalesce(positions.to_period, last_period.last_period)
            and positions.to_seconds is not null,
            positions.to_seconds,
            periods.end_seconds
        ) as segment_end
    from positions
    inner join last_period using (match_id)
    inner join periods
        on periods.match_id = positions.match_id
        and periods.period between positions.from_period
            and coalesce(positions.to_period, last_period.last_period)

),

{#
  El origen a veces trae tramos superpuestos (p. ej. cuando un jugador sale a atenderse
  y vuelve). Se unen los intervalos de cada jugador en cada tiempo antes de sumar
  (gaps and islands), así un mismo minuto nunca cuenta dos veces.
#}
flagged as (

    select
        *,
        if(
            segment_start <= max(segment_end) over (
                partition by match_id, player_id, period
                order by segment_start, segment_end
                rows between unbounded preceding and 1 preceding
            ),
            0,
            1
        ) as starts_island
    from segments
    where segment_end > segment_start

),

islands as (

    select
        *,
        sum(starts_island) over (
            partition by match_id, player_id, period
            order by segment_start, segment_end
            rows between unbounded preceding and current row
        ) as island_id
    from flagged

),

merged as (

    select
        match_id,
        team_id,
        player_id,
        logical_or(is_starter) as is_starter,
        max(segment_end) - min(segment_start) as seconds
    from islands
    group by match_id, team_id, player_id, period, island_id

)

select
    match_id,
    team_id,
    player_id,
    logical_or(is_starter) as is_starter,
    round(sum(seconds) / 60, 1) as minutes_played

from merged
group by match_id, team_id, player_id
