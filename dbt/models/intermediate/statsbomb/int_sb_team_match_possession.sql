{#
  Posesión de cada equipo por partido: parte de la duración de los eventos (sin la tanda de
  penales) en la que el equipo tenía la pelota. Base del ajuste PAdj.
#}
with team_seconds as (

    select match_id, possession_team_id as team_id, sum(coalesce(duration, 0)) as seconds
    from {{ ref('stg_sb_events') }}
    where period <= 4 and possession_team_id is not null
    group by match_id, possession_team_id

)

select
    match_id,
    team_id,
    round(100 * seconds / sum(seconds) over (partition by match_id), 2) as possession_pct
from team_seconds
