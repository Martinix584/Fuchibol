{#
  Un equipo por partido: goles, xG a favor y en contra, y puntos esperados (xPts).

  xPts: se asume que los goles de cada equipo siguen una Poisson con media = su xG, se
  calcula la probabilidad de cada resultado (0-0 a 15-15) y xPts = 3·P(gana) + P(empata).
  Es una aproximación conocida; la alternativa es simular tiro por tiro.
#}
with matches as (

    {# Solo partidos con eventos cargados: uno listado pero todavía sin ingerir daría xG 0 #}
    select *
    from {{ ref('stg_sb_matches') }}
    where match_id in (select match_id from {{ ref('int_sb_match_periods') }})

),

team_xg as (

    select
        match_id,
        team_id,
        count(*) as shots,
        countif(is_on_target) as shots_on_target,
        sum(xg) as xg,
        sum(if(is_penalty, 0, xg)) as npxg
    from {{ ref('int_sb_shots') }}
    group by match_id, team_id

),

sides as (

    select
        match_id, competition_id, competition_name, season_id, season_name, match_date, competition_stage,
        home_team_id as team_id, home_team_name as team_name,
        away_team_id as opponent_id, away_team_name as opponent_name,
        'Local' as venue, home_score as goals_for, away_score as goals_against
    from matches

    union all

    select
        match_id, competition_id, competition_name, season_id, season_name, match_date, competition_stage,
        away_team_id, away_team_name, home_team_id, home_team_name,
        'Visitante', away_score, home_score
    from matches

),

with_xg as (

    select
        sides.*,
        coalesce(own.shots, 0) as shots,
        coalesce(own.shots_on_target, 0) as shots_on_target,
        round(coalesce(own.xg, 0), 3) as xg_for,
        round(coalesce(own.npxg, 0), 3) as npxg_for,
        coalesce(rival.shots, 0) as shots_against,
        round(coalesce(rival.xg, 0), 3) as xg_against,
        round(coalesce(rival.npxg, 0), 3) as npxg_against
    from sides
    left join team_xg as own
        on own.match_id = sides.match_id and own.team_id = sides.team_id
    left join team_xg as rival
        on rival.match_id = sides.match_id and rival.team_id = sides.opponent_id

),

{# Probabilidad de cada marcador posible según Poisson(xG) #}
scorelines as (

    select
        with_xg.match_id,
        with_xg.team_id,
        g_for,
        g_against,
        exp(-with_xg.xg_for) * pow(with_xg.xg_for, g_for) / factorials[offset(g_for)]
            * exp(-with_xg.xg_against) * pow(with_xg.xg_against, g_against) / factorials[offset(g_against)]
            as probability
    from with_xg
    cross join unnest(generate_array(0, 15)) as g_for
    cross join unnest(generate_array(0, 15)) as g_against
    cross join (select [1, 1, 2, 6, 24, 120, 720, 5040, 40320, 362880, 3628800, 39916800, 479001600, 6227020800, 87178291200, 1307674368000] as factorials)

),

outcome_probabilities as (

    select
        match_id,
        team_id,
        sum(if(g_for > g_against, probability, 0)) as win_probability,
        sum(if(g_for = g_against, probability, 0)) as draw_probability,
        sum(if(g_for < g_against, probability, 0)) as loss_probability
    from scorelines
    group by match_id, team_id

)

select
    with_xg.*,
    case
        when with_xg.goals_for > with_xg.goals_against then 'Ganó'
        when with_xg.goals_for = with_xg.goals_against then 'Empató'
        else 'Perdió'
    end as result,
    case
        when with_xg.goals_for > with_xg.goals_against then 3
        when with_xg.goals_for = with_xg.goals_against then 1
        else 0
    end as points,
    round(outcome_probabilities.win_probability, 4) as win_probability,
    round(outcome_probabilities.draw_probability, 4) as draw_probability,
    round(outcome_probabilities.loss_probability, 4) as loss_probability,
    round(3 * outcome_probabilities.win_probability + outcome_probabilities.draw_probability, 3) as xpts

from with_xg
inner join outcome_probabilities using (match_id, team_id)
