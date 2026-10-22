{# Qué variables pesan más para explicar el valor de mercado (importancia por permutación). #}
select feature, attribution from {{ source('ml', 'feature_importance') }}
