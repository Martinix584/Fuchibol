{# Estadística cada 90 minutos. Devuelve null si no jugó. #}
{% macro per_90(stat, minutes) -%}
    round(safe_divide({{ stat }} * 90, nullif({{ minutes }}, 0)), 3)
{%- endmacro %}
