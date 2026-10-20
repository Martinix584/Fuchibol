{#
  Jugadores subvaluados: el modelo dice que, por su rendimiento y perfil,
  deberían valer bastante más de lo que marca Transfermarkt.
#}
select
    seasons.player_id,
    seasons.player_name,
    seasons.season,
    seasons.age,
    seasons.position,
    seasons.country_of_citizenship,
    seasons.main_club_name,
    seasons.main_league_name,
    seasons.games,
    seasons.minutes,
    seasons.goals,
    seasons.assists,
    seasons.goal_contributions_per_90,
    predictions.actual_value_eur,
    predictions.predicted_value_eur,
    predictions.predicted_value_eur - predictions.actual_value_eur as value_gap_eur,
    round(safe_divide(predictions.predicted_value_eur, predictions.actual_value_eur), 2) as predicted_to_actual_ratio,
    case
        when safe_divide(predictions.predicted_value_eur, predictions.actual_value_eur) >= 1.5 then 'Subvaluado'
        when safe_divide(predictions.predicted_value_eur, predictions.actual_value_eur) <= 0.67 then 'Sobrevaluado'
        else 'Precio justo'
    end as valuation_label,
    rank() over (order by safe_divide(predictions.predicted_value_eur, predictions.actual_value_eur) desc)
        as undervalued_rank

from {{ ref('ml_market_value_predictions') }} as predictions
inner join {{ ref('mart_player_seasons') }} as seasons using (player_id, season)
