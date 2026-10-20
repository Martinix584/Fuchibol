{#
  Argentina como fábrica de jugadores: jugadores argentinos vendidos por clubes
  de la liga argentina a clubes del exterior, y qué pasó con su valor después.
#}
select
    transfer_id,
    transfer_date,
    extract(year from transfer_date) as transfer_year,
    player_id,
    player_name,
    position,
    age_at_transfer,
    from_club_id,
    from_club_name,
    to_club_id,
    to_club_name,
    coalesce(to_league_name, 'Liga no cubierta') as to_league_name,
    coalesce(to_country, 'Otro') as to_country,
    transfer_fee_eur,
    is_paid_transfer,
    market_value_at_transfer_eur,
    value_1y_after_eur,
    peak_value_after_eur,
    round(safe_divide(peak_value_after_eur, nullif(transfer_fee_eur, 0)), 2) as peak_value_to_fee_ratio,
    minutes_after,
    goal_contributions_per_90_before,
    goal_contributions_per_90_after,
    minutes_share_after,
    has_full_window

from {{ ref('int_transfers_enriched') }}
where country_of_citizenship = 'Argentina'
    and from_country = 'Argentina'
    and coalesce(to_country, 'Otro') != 'Argentina'
    and to_club_name not in ('Without Club', 'Retired', 'Career break', 'Unknown')
