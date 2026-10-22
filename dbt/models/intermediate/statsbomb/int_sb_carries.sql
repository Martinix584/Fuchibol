{# Conducciones (Carry) con inicio y fin, sin la tanda de penales. #}
select
    event_id,
    match_id,
    period,
    team_id,
    player_id,
    player_name,
    x,
    y,
    carry_detail.end_location[safe_offset(0)] as end_x,
    carry_detail.end_location[safe_offset(1)] as end_y
from {{ ref('stg_sb_events') }}
where event_type = 'Carry'
    and period <= 4
