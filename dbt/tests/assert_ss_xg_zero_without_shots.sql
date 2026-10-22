{{ config(tags=['current']) }}
-- Sin tiros, el xG es 0, no null (y lo mismo para xA sin pases clave).
select player_id, shots, xg, key_passes, xa
from {{ ref('stg_ss_player_season') }}
where (shots = 0 and xg is null) or (key_passes = 0 and xa is null)
