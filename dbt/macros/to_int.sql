{#
  El autodetect de BigQuery puede leer una columna entera como INT64, FLOAT64
  (si tiene vacíos, p. ej. "123.0") o STRING. Pasar por FLOAT64 cubre los tres casos.
#}
{% macro to_int(column) -%}
    safe_cast(safe_cast({{ column }} as float64) as int64)
{%- endmacro %}
