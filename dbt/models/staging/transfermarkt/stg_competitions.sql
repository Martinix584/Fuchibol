select
    cast(competition_id as string) as competition_id,
    cast(competition_code as string) as competition_code,
    initcap(replace(cast(name as string), '-', ' ')) as competition_name,
    cast(type as string) as competition_type,
    cast(sub_type as string) as competition_sub_type,
    nullif(cast(country_name as string), '') as country_name,
    cast(confederation as string) as confederation,
    type = 'domestic_league' as is_domestic_league

from {{ source('transfermarkt', 'competitions') }}
