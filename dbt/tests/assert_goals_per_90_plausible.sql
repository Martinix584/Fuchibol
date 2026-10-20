{{ config(severity='warn') }}
-- Con al menos 900 minutos, nadie promedia más de 2 goles cada 90 (Haaland anda cerca de 1).
select player_id, season, minutes, goals_per_90
from {{ ref('int_player_season_stats') }}
where minutes >= 900
    and goals_per_90 > 2
