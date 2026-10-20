{#
  Cada transferencia con lo que pasó antes y después:
  - valor de mercado al fichar, ~1 año después y pico posterior
  - minutos, goles y asistencias en el club de origen (año previo) y en el nuevo (año siguiente)
  - qué porcentaje de los minutos posibles jugó en el club nuevo
#}
{% set window = var('transfer_window_days') %}

with transfers as (

    select * from {{ ref('stg_transfers') }}

),

valuations as (

    select * from {{ ref('stg_player_valuations') }}

),

appearances as (

    select * from {{ ref('stg_appearances') }}

),

data_cutoff as (

    select max(game_date) as last_game_date from appearances

),

value_after as (

    select
        transfers.transfer_id,
        valuations.market_value_eur as value_1y_after_eur
    from transfers
    inner join valuations
        on valuations.player_id = transfers.player_id
        and valuations.valuation_date between date_add(transfers.transfer_date, interval 270 day)
            and date_add(transfers.transfer_date, interval 450 day)
    qualify row_number() over (
        partition by transfers.transfer_id
        order by abs(date_diff(valuations.valuation_date, date_add(transfers.transfer_date, interval 365 day), day))
    ) = 1

),

peak_after as (

    select
        transfers.transfer_id,
        max(valuations.market_value_eur) as peak_value_after_eur
    from transfers
    inner join valuations
        on valuations.player_id = transfers.player_id
        and valuations.valuation_date > transfers.transfer_date
    group by transfers.transfer_id

),

stats_after as (

    select
        transfers.transfer_id,
        count(*) as games_after,
        sum(appearances.minutes_played) as minutes_after,
        sum(appearances.goals) as goals_after,
        sum(appearances.assists) as assists_after
    from transfers
    inner join appearances
        on appearances.player_id = transfers.player_id
        and appearances.club_id = transfers.to_club_id
        and appearances.game_date between transfers.transfer_date
            and date_add(transfers.transfer_date, interval {{ window }} day)
    group by transfers.transfer_id

),

stats_before as (

    select
        transfers.transfer_id,
        count(*) as games_before,
        sum(appearances.minutes_played) as minutes_before,
        sum(appearances.goals) as goals_before,
        sum(appearances.assists) as assists_before
    from transfers
    inner join appearances
        on appearances.player_id = transfers.player_id
        and appearances.club_id = transfers.from_club_id
        and appearances.game_date between date_sub(transfers.transfer_date, interval {{ window }} day)
            and transfers.transfer_date
    group by transfers.transfer_id

),

club_games_after as (

    {# Partidos que jugó el club nuevo en la ventana: el máximo de minutos posibles #}
    select
        transfers.transfer_id,
        count(*) as club_games_after
    from transfers
    inner join {{ ref('stg_games') }} as games
        on transfers.to_club_id in (games.home_club_id, games.away_club_id)
        and games.game_date between transfers.transfer_date
            and date_add(transfers.transfer_date, interval {{ window }} day)
    group by transfers.transfer_id

)

select
    transfers.*,
    players.player_name,
    players.position,
    players.sub_position,
    players.country_of_citizenship,
    round(date_diff(transfers.transfer_date, players.date_of_birth, day) / 365.25, 1) as age_at_transfer,

    from_clubs.domestic_competition_id as from_league_id,
    from_clubs.league_name as from_league_name,
    from_clubs.league_country as from_country,
    to_clubs.domestic_competition_id as to_league_id,
    to_clubs.league_name as to_league_name,
    to_clubs.league_country as to_country,

    value_after.value_1y_after_eur,
    peak_after.peak_value_after_eur,

    coalesce(stats_before.games_before, 0) as games_before,
    coalesce(stats_before.minutes_before, 0) as minutes_before,
    coalesce(stats_before.goals_before, 0) as goals_before,
    coalesce(stats_before.assists_before, 0) as assists_before,
    {{ per_90('stats_before.goals_before + stats_before.assists_before', 'stats_before.minutes_before') }}
        as goal_contributions_per_90_before,

    coalesce(stats_after.games_after, 0) as games_after,
    coalesce(stats_after.minutes_after, 0) as minutes_after,
    coalesce(stats_after.goals_after, 0) as goals_after,
    coalesce(stats_after.assists_after, 0) as assists_after,
    {{ per_90('stats_after.goals_after + stats_after.assists_after', 'stats_after.minutes_after') }}
        as goal_contributions_per_90_after,

    club_games_after.club_games_after,
    round(safe_divide(stats_after.minutes_after, club_games_after.club_games_after * 90), 3)
        as minutes_share_after,

    {# Fichajes de hace menos de un año todavía no tienen la ventana completa #}
    date_add(transfers.transfer_date, interval {{ window }} day) <= data_cutoff.last_game_date
        as has_full_window

from transfers
cross join data_cutoff
left join {{ ref('stg_players') }} as players using (player_id)
left join {{ ref('int_clubs_with_league') }} as from_clubs
    on transfers.from_club_id = from_clubs.club_id
left join {{ ref('int_clubs_with_league') }} as to_clubs
    on transfers.to_club_id = to_clubs.club_id
left join value_after using (transfer_id)
left join peak_after using (transfer_id)
left join stats_after using (transfer_id)
left join stats_before using (transfer_id)
left join club_games_after using (transfer_id)
