select
    {{ to_int("player_id") }} as player_id,
    safe_cast(`date` as date) as valuation_date,
    {{ to_int("market_value_in_eur") }} as market_value_eur,
    {{ to_int("current_club_id") }} as club_id,
    cast(player_club_domestic_competition_id as string) as club_domestic_competition_id

from {{ source('transfermarkt', 'player_valuations') }}
