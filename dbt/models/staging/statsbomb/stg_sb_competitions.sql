select
    competition_id,
    season_id,
    competition_name,
    country_name,
    season_name,
    competition_gender,
    coalesce(competition_international, false) as is_international

from {{ source('statsbomb', 'competitions') }}
