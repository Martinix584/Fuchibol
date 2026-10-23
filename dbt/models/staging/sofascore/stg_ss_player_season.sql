{{ config(tags=['current']) }}
{#
  Una fila por jugador y temporada. Si el mismo jugador se bajó en modo top y full,
  gana la fila full (tiene minutos y estadísticas completas), sin importar el orden
  de ingesta; dentro de cada modo gana la última ingesta.

  SofaScore no manda expectedGoals/expectedAssists a quien no pateó o no dio pases clave:
  ahí el valor real es 0. Si pateó y no vino xG, el dato falta de verdad y queda null
  (lo cuenta el test assert_ss_xg_missing_with_shots).
#}
with source as (

    select * from {{ source('sofascore', 'player_season') }}
    where true
    qualify row_number() over (
        partition by league_code, season_id, player_id
        order by case when source_mode = 'full' then 1 else 0 end desc, _ingested_at desc
    ) = 1

)

select
    cast(league_code as string) as league_code,
    cast(league_name as string) as league_name,
    safe_cast(season_id as int64) as season_id,
    cast(season_name as string) as season_name,
    -- SofaScore manda `year` como "26/27" en las ligas europeas y "2026" en Argentina.
    -- El cast directo dejaba null las europeas; para el raw ya cargado se deduce del
    -- nombre ("Premier League 26/27").
    case
        when safe_cast(season_year as int64) is not null then safe_cast(season_year as int64)
        when regexp_contains(season_name, r'(?:19|20)\d{2}') then
            safe_cast(regexp_extract(season_name, r'((?:19|20)\d{2})') as int64)
        when regexp_contains(season_name, r'\d{2}\s*/\s*\d{2}') then
            safe_cast(regexp_extract(season_name, r'(\d{2})\s*/') as int64)
            + if(
                safe_cast(regexp_extract(season_name, r'(\d{2})\s*/') as int64) >= 50,
                1900,
                2000
            )
    end as season_year,
    safe_cast(player_id as int64) as player_id,
    cast(player_name as string) as player_name,
    safe_cast(team_id as int64) as team_id,
    cast(team_name as string) as team_name,
    cast(position as string) as position,
    cast(source_mode as string) as source_mode,
    safe_cast(appearances as int64) as appearances,
    safe_cast(minutes as float64) as minutes,
    safe_cast(goals as int64) as goals,
    safe_cast(assists as int64) as assists,
    safe_cast(shots as int64) as shots,
    safe_cast(shots_on_target as int64) as shots_on_target,
    safe_cast(key_passes as int64) as key_passes,
    safe_cast(penalty_goals as int64) as penalty_goals,
    safe_cast(yellow_cards as int64) as yellow_cards,
    safe_cast(red_cards as int64) as red_cards,
    safe_cast(rating as float64) as rating,
    case
        when expected_goals is null and safe_cast(shots as int64) = 0 then 0.0
        else safe_cast(expected_goals as float64)
    end as xg,
    case
        when expected_assists is null and safe_cast(key_passes as int64) = 0 then 0.0
        else safe_cast(expected_assists as float64)
    end as xa,
    safe_cast(expected_goals_on_target as float64) as xg_on_target,
    cast(raw as string) as raw_json,
    _ingested_at
from source
