{{ config(tags=['current'], severity='warn') }}
-- Jugadores de SofaScore que patearon y no tienen xG: el dato falta en el origen.
-- Es un aviso, no un error: sirve para ver si baja en las cargas siguientes.
select player_id, player_name, team_name, shots
from {{ ref('stg_ss_player_season') }}
where xg is null and shots > 0
