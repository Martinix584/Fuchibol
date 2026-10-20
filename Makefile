.PHONY: setup test lint extract dbt-build dbt-train dbt-docs airflow-up airflow-down metrics

DBT = cd dbt && dbt
DBT_FLAGS = --profiles-dir .

setup:            ## Entorno local (Python 3.12)
	python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt

test:             ## Tests unitarios de la ingesta + parseo de dbt
	pytest -q
	$(DBT) parse $(DBT_FLAGS)

lint:
	ruff check ingestion dags tests scripts
	ruff format --check ingestion dags tests scripts

extract:          ## Baja lo que cambió a GCS y lo carga a BigQuery (sin Airflow)
	PYTHONPATH=. python scripts/run_ingestion.py

dbt-build:        ## Modelos + tests + snapshots (sin ML)
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
