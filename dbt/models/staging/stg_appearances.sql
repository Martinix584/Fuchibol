select
    cast(appearance_id as string) as appearance_id,
    {{ to_int("game_id") }} as game_id,
    {{ to_int("player_id") }} as player_id,
    {{ to_int("player_club_id") }} as club_id,
    safe_cast(`date` as date) as game_date,
    cast(competition_id as string) as competition_id,
    coalesce({{ to_int("minutes_played") }}, 0) as minutes_played,
    coalesce({{ to_int("goals") }}, 0) as goals,
    coalesce({{ to_int("assists") }}, 0) as assists,
    coalesce({{ to_int("yellow_cards") }}, 0) as yellow_cards,
    coalesce({{ to_int("red_cards") }}, 0) as red_cards

from {{ source('transfermarkt', 'appearances') }}
