select
    clubs.*,
    leagues.competition_name as league_name,
    leagues.country_name as league_country,
    leagues.confederation

from {{ ref('stg_clubs') }} as clubs
left join {{ ref('stg_competitions') }} as leagues
    on clubs.domestic_competition_id = leagues.competition_id
