{# Métricas del modelo (sobre el 20% de evaluación). Van al README y a Power BI. #}
select * from {{ source('ml', 'model_evaluation') }}
