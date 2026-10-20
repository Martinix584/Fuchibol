select
    {{ to_int("player_id") }} as player_id,
    cast(name as string) as player_name,
    {{ to_int("current_club_id") }} as current_club_id,
    cast(current_club_name as string) as current_club_name,
    {{ to_int("last_season") }} as last_season,
    cast(country_of_citizenship as string) as country_of_citizenship,
    cast(country_of_birth as string) as country_of_birth,
    safe_cast(date_of_birth as date) as date_of_birth,
    cast(position as string) as position,
    cast(sub_position as string) as sub_position,
    cast(foot as string) as foot,
    {{ to_int("height_in_cm") }} as height_in_cm,
    safe_cast(contract_expiration_date as date) as contract_expiration_date,
    cast(agent_name as string) as agent_name,
    {{ to_int("international_caps") }} as international_caps,
    {{ to_int("international_goals") }} as international_goals,
    {{ to_int("market_value_in_eur") }} as market_value_eur,
    {{ to_int("highest_market_value_in_eur") }} as highest_market_value_eur,
    cast(image_url as string) as image_url

from {{ source('transfermarkt', 'players') }}
