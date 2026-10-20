select player_id, valuation_date
from {{ ref('stg_player_valuations') }}
where valuation_date > current_date()
