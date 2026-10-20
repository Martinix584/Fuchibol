select
    {{ to_int("game_id") }} as game_id,
    cast(competition_id as string) as competition_id,
    cast(competition_type as string) as competition_type,
    {{ to_int("season") }} as season,
    safe_cast(`date` as date) as game_date,
    {{ to_int("home_club_id") }} as home_club_id,
    {{ to_int("away_club_id") }} as away_club_id,
    cast(home_club_name as string) as home_club_name,
    cast(away_club_name as string) as away_club_name,
    {{ to_int("home_club_goals") }} as home_club_goals,
    {{ to_int("away_club_goals") }} as away_club_goals,
    {{ to_int("attendance") }} as attendance

from {{ source('transfermarkt', 'games') }}
