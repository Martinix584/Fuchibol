{# Métricas del modelo (sobre el 20% de evaluación). Van al README y a Power BI. #}
select
    current_timestamp() as evaluated_at,
    *
from ml.evaluate(model {{ market_value_model() }})
