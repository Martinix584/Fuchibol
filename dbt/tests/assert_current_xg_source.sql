{{ config(tags=['current']) }}
{% set big5_source = var('xg_source_big5', 'understat') %}
-- Argentina siempre SofaScore; las 5 grandes, la fuente elegida. Nunca se mezclan.
select player_id, league_code, season, xg_source
from {{ ref('mart_current_player_season') }}
where (league_code = 'ARG' and xg_source != 'sofascore')
    or (league_code != 'ARG' and xg_source != '{{ big5_source }}')
