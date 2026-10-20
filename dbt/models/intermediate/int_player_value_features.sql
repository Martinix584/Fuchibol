{#
  Grano: jugador x temporada. Junta rendimiento + perfil + el valor de mercado
  al cierre de la temporada (la etiqueta que aprende el modelo de BigQuery ML).
#}
with stats as (

    select *, {{ season_end_date('season') }} as season_end_date
    from {{ ref('int_player_season_stats') }}

),

season_value as (

    select
        stats.player_id,
        stats.season,
        valuations.market_value_eur,
        valuations.valuation_date
    from stats
    inner join {{ ref('stg_player_valuations') }} as valuations
        on valuations.player_id = stats.player_id
        and valuations.valuation_date
            between date_sub(stats.season_end_date, interval 200 day) and stats.season_end_date
    qualify row_number() over (
        partition by stats.player_id, stats.season order by valuations.valuation_date desc
    ) = 1

)

select
    stats.*,
    players.player_name,
    players.position,
    players.sub_position,
    players.foot,
    players.height_in_cm,
    players.country_of_citizenship,
    round(date_diff(stats.season_end_date, players.date_of_birth, day) / 365.25, 1) as age,
    leagues.competition_name as main_league_name,
    leagues.country_name as main_league_country,
    clubs.club_name as main_club_name,
    season_value.market_value_eur,
    season_value.valuation_date

from stats
inner join {{ ref('stg_players') }} as players using (player_id)
left join season_value using (player_id, season)
left join {{ ref('stg_competitions') }} as leagues
    on stats.main_league_id = leagues.competition_id
left join {{ ref('stg_clubs') }} as clubs
    on stats.main_club_id = clubs.club_id
