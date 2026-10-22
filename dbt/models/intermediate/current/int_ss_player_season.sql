{{ config(tags=['current']) }}
{# Jugador x temporada de SofaScore con métricas cada 90 (null en modo top). #}
with players as (

    select * from {{ ref('stg_ss_player_season') }}

)

select
    players.*,
    {{ per_90('goals', 'minutes') }} as goals_per_90,
    {{ per_90('assists', 'minutes') }} as assists_per_90,
    {{ per_90('shots', 'minutes') }} as shots_per_90,
    {{ per_90('key_passes', 'minutes') }} as key_passes_per_90,
    {{ per_90('xg', 'minutes') }} as xg_per_90,
    {{ per_90('xa', 'minutes') }} as xa_per_90,
    round(goals - xg, 2) as goals_minus_xg
from players
