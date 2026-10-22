{{ config(tags=['current']) }}
{#
  Percentiles (0-100) de la temporada actual contra los jugadores de la misma posición, liga
  y fuente de xG (Understat y SofaScore nunca se comparan entre sí). Solo con 600 minutos o más.
  Posición en 4 grupos: SofaScore ya trae G/D/M/F; Understat trae una lista ("D M S") y se
  toma la primera, con GK -> G. "S" sola (solo entró de suplente) queda afuera.
#}
{% set metrics = ['xg', 'xa', 'npxg', 'shots', 'key_passes'] %}

with players as (

    select
        *,
        case
            when xg_source = 'sofascore' then position
            when split(position, ' ')[safe_offset(0)] = 'GK' then 'G'
            when split(position, ' ')[safe_offset(0)] in ('D', 'M', 'F') then split(position, ' ')[safe_offset(0)]
        end as position_group
    from {{ ref('mart_current_player_season') }}
    where minutes >= 600

)

select
    player_key,
    player_name,
    team_name,
    league_code,
    season,
    xg_source,
    position_group,
    minutes,
    {% for metric in metrics %}
    {{ metric }}_per_90,
    {# null si la fuente no trae la métrica (npxG en SofaScore), en vez de percentil 0 #}
    if({{ metric }}_per_90 is null, null, round(percent_rank() over (
        partition by league_code, season, xg_source, position_group, {{ metric }}_per_90 is null
        order by {{ metric }}_per_90
    ) * 100)) as {{ metric }}_pct{{ ',' if not loop.last }}
    {% endfor %}
from players
where position_group in ('G', 'D', 'M', 'F')
