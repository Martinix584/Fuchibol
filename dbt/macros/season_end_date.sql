{#
  Fin de temporada "europea": la temporada 2023 (2023/24) termina el 30/06/2024.
  Simplificación: las ligas de calendario anual (p. ej. Argentina) quedan corridas medio año.
#}
{% macro season_end_date(season) -%}
    date({{ season }} + 1, 6, 30)
{%- endmacro %}
