{# Para cada fila, P(gana) + P(empata) + P(pierde) tiene que dar ~1 (el corte en 15 goles deja un error ínfimo). #}
{% test outcome_probabilities_sum_to_one(model) %}
select match_id, team_id, win_probability + draw_probability + loss_probability as total
from {{ model }}
where abs(win_probability + draw_probability + loss_probability - 1) > 0.001
{% endtest %}
