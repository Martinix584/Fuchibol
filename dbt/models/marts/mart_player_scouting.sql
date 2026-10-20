{#
  Scouting: une el rendimiento avanzado de StatsBomb (xG, xA, acciones progresivas) con
  el perfil y el valor de mercado de Transfermarkt, para los jugadores cruzados en
  int_player_id_map. Responde, por ejemplo, "¿cuánto vale cada xG+xA cada 90?".
#}
with sb as (

    select * from {{ ref('mart_sb_player_seasons') }}
    where tm_player_id is not null

),

seasons as (

    select competition_id, season_id, max(match_date) as last_match_date
    from {{ ref('stg_sb_matches') }}
    group by competition_id, season_id

),

value_at_season as (

    {# Valor de mercado más cercano (hasta 1 año antes) al último partido de esa competición #}
    select
        sb.player_id,
        sb.competition_id,
        sb.season_id,
        valuations.market_value_eur,
        valuations.valuation_date
    from sb
    inner join seasons using (competition_id, season_id)
    inner join {{ ref('stg_player_valuations') }} as valuations
        on valuations.player_id = sb.tm_player_id
        and valuations.valuation_date between date_sub(seasons.last_match_date, interval 365 day)
            and seasons.last_match_date
    where true
    qualify row_number() over (
        partition by sb.player_id, sb.competition_id, sb.season_id order by valuations.valuation_date desc
    ) = 1

)

select
    sb.*,
    tm.player_name as tm_player_name,
    tm.position as tm_position,
    tm.sub_position as tm_sub_position,
    tm.date_of_birth,
    round(date_diff(seasons.last_match_date, tm.date_of_birth, day) / 365.25, 1) as age_at_competition,
    tm.current_club_name,
    tm.market_value_eur as current_market_value_eur,
    value_at_season.market_value_eur as market_value_at_competition_eur,
    round(safe_divide(value_at_season.market_value_eur / 1e6, sb.npxg_plus_xa_per_90), 2)
        as million_eur_per_npxg_xa_per_90

from sb
inner join seasons
    on seasons.competition_id = sb.competition_id
    and seasons.season_id = sb.season_id
inner join {{ ref('dim_players') }} as tm
    on tm.player_id = sb.tm_player_id
left join value_at_season
    on value_at_season.player_id = sb.player_id
    and value_at_season.competition_id = sb.competition_id
    and value_at_season.season_id = sb.season_id
