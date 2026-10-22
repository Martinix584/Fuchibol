{{ config(tags=['current']) }}
{# Temporadas de cada torneo de SofaScore (Argentina puede tener Apertura/Clausura). #}
with source as (

    select * from {{ source('sofascore', 'seasons') }}
    where true
    qualify row_number() over (
        partition by league_code, season_id order by _ingested_at desc
    ) = 1

)

select
    cast(league_code as string) as league_code,
    cast(league_name as string) as league_name,
    safe_cast(season_id as int64) as season_id,
    cast(season_name as string) as season_name,
    cast(year as string) as season_year,
    coalesce(safe_cast(is_selected as bool), false) as is_selected,
    _ingested_at
from source
