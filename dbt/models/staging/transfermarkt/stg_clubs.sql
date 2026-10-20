select
    {{ to_int("club_id") }} as club_id,
    cast(name as string) as club_name,
    cast(domestic_competition_id as string) as domestic_competition_id,
    {{ to_int("squad_size") }} as squad_size,
    safe_cast(average_age as float64) as average_age,
    safe_cast(foreigners_percentage as float64) as foreigners_percentage,
    {{ to_int("national_team_players") }} as national_team_players,
    cast(stadium_name as string) as stadium_name,
    {{ to_int("last_season") }} as last_season

from {{ source('transfermarkt', 'clubs') }}
