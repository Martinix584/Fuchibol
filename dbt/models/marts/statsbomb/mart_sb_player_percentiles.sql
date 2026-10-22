{#
  Percentiles (0-100) de las métricas de scouting cada 90, contra los jugadores del mismo
  grupo de posición en la misma competición-temporada. Solo jugadores con 600 minutos o más:
  con menos, los per-90 no son confiables. Alimenta los radares.
#}
{% set metrics = [
    'npxg', 'xa', 'xt_added', 'shots', 'key_passes', 'progressive_passes', 'progressive_carries',
    'dribbles_completed', 'pressures', 'padj_tackles_interceptions'
] %}

select
    player_id,
    player_name,
    teams,
    competition_id,
    competition_name,
    season_id,
    season_name,
    position_group,
    minutes_played,
    {% for metric in metrics %}
    {{ metric }}_per_90,
    round(percent_rank() over (
        partition by competition_id, season_id, position_group order by {{ metric }}_per_90
    ) * 100) as {{ metric }}_pct,
    {% endfor %}
    tm_player_id
from {{ ref('mart_sb_player_seasons') }}
where minutes_played >= 600 and position_group is not null
