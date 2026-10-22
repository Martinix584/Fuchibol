{# "41:20" -> 2480 segundos. Los relojes de StatsBomb son acumulados (el 2.º tiempo arranca en 45:00). #}
{% macro mmss_to_seconds(column) -%}
    (safe_cast(split({{ column }}, ':')[safe_offset(0)] as int64) * 60
        + safe_cast(split({{ column }}, ':')[safe_offset(1)] as int64))
{%- endmacro %}

{# Distancia al centro del arco rival. StatsBomb orienta siempre el ataque hacia x = 120 (cancha de 120 x 80). #}
{% macro distance_to_goal(x, y) -%}
    sqrt(pow(120 - {{ x }}, 2) + pow(40 - {{ y }}, 2))
{%- endmacro %}

{# Dentro del área rival: x >= 102 y 18 <= y <= 62. #}
{% macro in_box(x, y) -%}
    ({{ x }} >= 102 and {{ y }} between 18 and 62)
{%- endmacro %}

{# Nombre comparable entre fuentes: minúsculas, sin acentos ni signos. #}
{% macro normalize_name(column) -%}
    trim(regexp_replace(regexp_replace(lower(normalize({{ column }}, NFD)), r'\p{M}', ''), r'[^a-z]+', ' '))
{%- endmacro %}

{# Zona de la grilla de xT (12 x 8 sobre 120 x 80): celdas de 10 x 10, los bordes caen en la última. #}
{% macro xt_zone(coordinate, cells) -%}
    least(greatest(cast(floor({{ coordinate }} / 10) as int64), 0), {{ cells - 1 }})
{%- endmacro %}
