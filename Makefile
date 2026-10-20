.PHONY: setup test lint smoke test-dag extract dbt-build dbt-train dbt-docs airflow-up airflow-down metrics charts

DBT = cd dbt && dbt
DBT_FLAGS = --profiles-dir .
SMOKE_DB ?= /tmp/fuchibol-smoke.duckdb

setup:            ## Entorno local (Python 3.12)
	python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt

test:             ## Tests unitarios de Python + parseo de dbt
	pytest -q
	$(DBT) parse $(DBT_FLAGS)

lint:
	ruff check ingestion dags tests scripts
	ruff format --check ingestion dags tests scripts

smoke:            ## dbt de punta a punta en DuckDB con el Mundial 2022 real (sin GCP)
	scripts/smoke.sh --database $(SMOKE_DB)

test-dag:         ## dag.test() del DAG en 4 escenarios (requiere Airflow instalado)
	scripts/test_dag.sh

charts: smoke     ## Regenera los gráficos del README con datos reales
	PYTHONPATH=. python scripts/readme_charts.py $(SMOKE_DB)

extract:          ## Ingesta de las dos fuentes a GCS + BigQuery (sin Airflow)
	PYTHONPATH=. python scripts/run_ingestion.py

dbt-build:        ## Seeds, modelos, snapshot, data tests y unit tests (sin ML)
	$(DBT) build $(DBT_FLAGS) --exclude tag:ml

dbt-train:        ## Entrena el modelo de BigQuery ML y construye sus tablas
	$(DBT) run-operation train_market_value_model $(DBT_FLAGS)
	$(DBT) build $(DBT_FLAGS) --select tag:ml

dbt-docs:         ## Documentación y linaje de dbt en http://localhost:8081
	$(DBT) docs generate $(DBT_FLAGS) && $(DBT) docs serve $(DBT_FLAGS) --port 8081

airflow-up:
	docker compose up -d --build

airflow-down:
	docker compose down

metrics:          ## Imprime la tabla de métricas para el README
	PYTHONPATH=. python scripts/metrics_report.py
