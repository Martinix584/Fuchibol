{# Qué variables pesan más para explicar el valor de mercado. #}
select *
from ml.global_explain(model {{ market_value_model() }})
