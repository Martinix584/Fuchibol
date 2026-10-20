{# Inicio y fin (en segundos de reloj) de cada tiempo jugado. El 5 (penales) no cuenta como minutos. #}
select
    match_id,
    period,
    min(if(event_type = 'Half Start', clock_seconds, null)) as start_seconds,
    max(if(event_type = 'Half End', clock_seconds, null)) as end_seconds

from {{ ref('stg_sb_events') }}
where event_type in ('Half Start', 'Half End')
    and period <= 4
group by match_id, period
