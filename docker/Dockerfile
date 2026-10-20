FROM apache/airflow:3.1.8-python3.12

ARG AIRFLOW_VERSION=3.1.8
ARG CONSTRAINTS=https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-3.12.txt

# dbt va en su propio virtualenv para no pelear con las dependencias de Airflow
USER root
RUN python -m venv /opt/dbt-venv \
    && /opt/dbt-venv/bin/pip install --no-cache-dir "dbt-core~=1.12.0" "dbt-bigquery~=1.12.0" \
    && chown -R airflow: /opt/dbt-venv
USER airflow

# Las librerías de la ingesta se instalan con las constraints oficiales de Airflow,
# así pip no actualiza nada que rompa a los providers de Google que ya trae la imagen
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir "apache-airflow==${AIRFLOW_VERSION}" -r /tmp/requirements.txt \
    --constraint "${CONSTRAINTS}"
