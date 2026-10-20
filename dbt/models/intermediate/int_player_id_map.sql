{#
  Cruce de jugadores StatsBomb -> Transfermarkt (no comparten ids).

  Se prueban reglas de más a menos estricta y cada jugador se queda con la mejor que
  le dé UN solo candidato. Si una regla da dos o más candidatos, se descarta (preferimos
  no cruzar a cruzar mal). Los casos difíciles se resuelven a mano en el seed
  player_id_overrides.

    1. override      seed manual
    2. name_country  apodo/nombre normalizado igual + misma nacionalidad
    3. full_country  nombre completo de StatsBomb igual + misma nacionalidad
    4. tokens        todas las palabras del nombre de Transfermarkt están en el nombre completo
                     de StatsBomb (ej. "Rodrigo De Paul" ⊂ "Rodrigo Javier De Paul") + nacionalidad
    5. name_only     apodo/nombre igual, sin mirar nacionalidad (solo si es único en todo el dataset)
#}
with aliases as (

    select alias, country from {{ ref('country_aliases') }}

),

sb_country as (

    select player_id, country_name
    from {{ ref('stg_sb_lineups') }}
    group by player_id, country_name
    qualify row_number() over (partition by player_id order by count(*) desc, country_name) = 1

),

sb_players as (

    select
        lineups.player_id as sb_player_id,
        any_value(lineups.player_name) as sb_full_name,
        any_value(lineups.player_display_name) as sb_display_name,
        {{ normalize_name('any_value(lineups.player_name)') }} as full_key,
        {{ normalize_name('any_value(lineups.player_display_name)') }} as display_key,
        {{ normalize_name('coalesce(any_value(aliases.country), any_value(sb_country.country_name))') }}
            as country_key
    from {{ ref('stg_sb_lineups') }} as lineups
    inner join sb_country on sb_country.player_id = lineups.player_id
    left join aliases on aliases.alias = sb_country.country_name
    group by lineups.player_id

),

tm_players as (

    select
        players.player_id as tm_player_id,
        players.player_name as tm_name,
        {{ normalize_name('players.player_name') }} as name_key,
        {{ normalize_name('coalesce(aliases.country, players.country_of_citizenship)') }} as country_key
    from {{ ref('stg_players') }} as players
    left join aliases on aliases.alias = players.country_of_citizenship

),

candidates as (

    select sb.sb_player_id, tm.tm_player_id, 2 as rule_rank, 'name_country' as match_method
    from sb_players as sb
    inner join tm_players as tm on tm.name_key = sb.display_key and tm.country_key = sb.country_key

    union all

    select sb.sb_player_id, tm.tm_player_id, 3, 'full_country'
    from sb_players as sb
    inner join tm_players as tm on tm.name_key = sb.full_key and tm.country_key = sb.country_key

    union all

    select sb.sb_player_id, tm.tm_player_id, 4, 'tokens'
    from sb_players as sb
    inner join tm_players as tm
        on tm.country_key = sb.country_key
        and split(tm.name_key, ' ')[safe_offset(0)] = split(sb.full_key, ' ')[safe_offset(0)]
    where array_length(split(tm.name_key, ' ')) >= 2
        and not exists (
            select 1
            from unnest(split(tm.name_key, ' ')) as token
            where token not in unnest(split(sb.full_key, ' '))
        )

    union all

    select sb.sb_player_id, tm.tm_player_id, 5, 'name_only'
    from sb_players as sb
    inner join tm_players as tm on tm.name_key = sb.display_key

),

{# Mejor regla de cada jugador, y cuántos candidatos distintos da esa regla #}
best_rule as (

    select
        sb_player_id,
        tm_player_id,
        match_method,
        rule_rank,
        count(distinct tm_player_id) over (partition by sb_player_id, rule_rank) as candidates_at_rule
    from candidates
    where true
    qualify rule_rank = min(rule_rank) over (partition by sb_player_id)

),

algorithmic as (

    select distinct sb_player_id, tm_player_id, match_method, rule_rank
    from best_rule
    where candidates_at_rule = 1

),

overrides as (

    {# Solo los que apuntan a un jugador que existe: si no, se usa el algoritmo #}
    select overrides.sb_player_id, overrides.tm_player_id, 'override' as match_method, 1 as rule_rank
    from {{ ref('player_id_overrides') }} as overrides
    inner join tm_players using (tm_player_id)

),

combined as (

    select * from overrides
    union all
    select * from algorithmic
    where sb_player_id not in (select sb_player_id from overrides)

)

{# Un jugador de Transfermarkt tampoco puede quedar cruzado con dos de StatsBomb #}
select
    combined.sb_player_id,
    combined.tm_player_id,
    combined.match_method,
    sb.sb_full_name,
    sb.sb_display_name,
    tm.tm_name

from combined
inner join sb_players as sb using (sb_player_id)
inner join tm_players as tm using (tm_player_id)
where true
qualify count(*) over (partition by combined.tm_player_id, combined.rule_rank) = 1
    and combined.rule_rank = min(combined.rule_rank) over (partition by combined.tm_player_id)
