"""Imprime en Markdown las métricas de la última corrida, listas para pegar en el README."""

from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from ingestion import config

QUERIES = {
    "Volumen (última ingesta por tabla)": """
        select table_name as tabla, `rows` as filas, round(bytes / 1e6, 1) as mb,
               extract_seconds as seg_extract, load_seconds as seg_load
        from `{p}.{ops}.pipeline_runs`
        where true
        qualify row_number() over (partition by table_name order by recorded_at desc) = 1
        order by filas desc
    """,
    "Tests de dbt (última corrida)": """
        select status as estado, count(*) as tests
        from `{p}.{ops}.dbt_results`
        where resource_type = 'test'
          and invocation_id = (
              select invocation_id from `{p}.{ops}.dbt_results`
              where resource_type = 'test' order by generated_at desc limit 1)
        group by status
    """,
    "Tiempos de dbt (los 10 modelos más lentos, última corrida)": """
        select split(unique_id, '.')[safe_offset(2)] as modelo,
               execution_seconds as segundos,
               round(bytes_processed / 1e6, 1) as mb_procesados
        from `{p}.{ops}.dbt_results`
        where resource_type in ('model', 'snapshot')
        qualify row_number() over (partition by unique_id order by generated_at desc) = 1
        order by segundos desc
        limit 10
    """,
    "Cruce de jugadores StatsBomb -> Transfermarkt": """
        select match_method as regla, count(*) as jugadores
        from `{p}.intermediate.int_player_id_map`
        group by match_method
        order by jugadores desc
    """,
    "Modelo de valor de mercado (scikit-learn)": """
        select round(r2_score, 3) as r2, round(mean_absolute_error, 3) as mae_log,
               round(median_absolute_error, 3) as mediana_error_log
        from `{p}.ml.ml_model_evaluation`
    """,
}


def to_markdown(rows) -> str:
    rows = list(rows)
    if not rows:
        return "_sin datos_"
    headers = list(rows[0].keys())
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(str(r[h]) for h in headers) + " |" for r in rows]
    return "\n".join(lines)


def main() -> None:
    client = bigquery.Client(project=config.GCP_PROJECT_ID, location=config.BQ_LOCATION)
    for title, sql in QUERIES.items():
        try:
            rows = client.query(sql.format(p=config.GCP_PROJECT_ID, ops=config.BQ_OPS_DATASET)).result()
            body = to_markdown(rows)
        except NotFound:  # tabla que todavía no se construyó (por ejemplo, sin dbt-train)
            body = "_sin datos_"
        print(f"### {title}\n\n{body}\n")


if __name__ == "__main__":
    main()
