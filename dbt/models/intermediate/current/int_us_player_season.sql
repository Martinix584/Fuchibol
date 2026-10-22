{{ config(tags=['current']) }}
{# Jugador x liga-temporada de Understat con métricas cada 90 y eficiencia. #}
with players as (

    select * from {{ ref('stg_us_players_season') }}

)

select
    players.*,
    {{ per_90('goals', 'minutes') }} as goals_per_90,
    {{ per_90('assists', 'minutes') }} as assists_per_90,
    {{ per_90('shots', 'minutes') }} as shots_per_90,
    {{ per_90('key_passes', 'minutes') }} as key_passes_per_90,
    {{ per_90('xg', 'minutes') }} as xg_per_90,
    {{ per_90('xa', 'minutes') }} as xa_per_90,
    {{ per_90('npxg', 'minutes') }} as npxg_per_90,
    {{ per_90('npxg + xa', 'minutes') }} as npxg_plus_xa_per_90,
    round(goals - xg, 2) as goals_minus_xg,
    round(safe_divide(npxg, shots), 3) as npxg_per_shot
from players
