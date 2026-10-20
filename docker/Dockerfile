FROM apache/airflow:3.1.8-python3.12

# dbt va en su propio virtualenv para no pelear con las dependencias de Airflow
USER root
RUN python -m venv /opt/dbt-venv \
    && /opt/dbt-venv/bin/pip install --no-cache-dir "dbt-core~=1.12.0" "dbt-bigquery~=1.12.0" \
    && chown -R airflow: /opt/dbt-venv
USER airflow

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
