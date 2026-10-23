.PHONY: setup setup-sofascore test lint smoke test-dag extract dbt-build dbt-train dbt-docs dbt-current understat sofascore airflow-up airflow-down metrics charts export-parquet app

PY ?= .venv/bin/python
DBT = cd dbt && $(CURDIR)/.venv/bin/dbt
DBT_FLAGS = --profiles-dir .
DBT_TARGET ?= dev
DBT_DEV_DATASET ?= dev
# El modelo escribe y lee el mismo dataset que usa dbt: ml en prod, <dev>_ml en dev.
ML_DATASET = $(if $(filter prod,$(DBT_TARGET)),ml,$(DBT_DEV_DATASET)_ml)
ML_FEATURES_DATASET = $(if $(filter prod,$(DBT_TARGET)),intermediate,$(DBT_DEV_DATASET)_intermediate)
SMOKE_DB ?= /tmp/fuchibol-smoke.duckdb

setup:            ## Entorno local (Python 3.12+)
	python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt

setup-sofascore:  ## Playwright para la ingesta local/manual de SofaScore
	.venv/bin/pip install -r requirements-sofascore.txt
	.venv/bin/python -m playwright install chromium

test:             ## Tests unitarios de Python + parseo de dbt
	$(PY) -m pytest -q
	$(DBT) parse $(DBT_FLAGS)

lint:
	$(PY) -m ruff check ingestion dags tests scripts app
	$(PY) -m ruff format --check ingestion dags tests scripts app

smoke:            ## dbt de punta a punta en DuckDB con el Mundial 2022 real (sin GCP)
	PATH=$(CURDIR)/.venv/bin:$$PATH scripts/smoke.sh --database $(SMOKE_DB)

test-dag:         ## dag.test() del DAG en 4 escenarios (requiere Airflow instalado)
	PATH=$(CURDIR)/.venv/bin:$$PATH scripts/test_dag.sh

charts: smoke     ## Regenera los gráficos del README con datos reales
	PYTHONPATH=. $(PY) scripts/readme_charts.py $(SMOKE_DB)

extract:          ## Ingesta de las fuentes automáticas a GCS + BigQuery (sin Airflow)
	PYTHONPATH=. $(PY) scripts/run_ingestion.py

dbt-build:        ## Seeds, modelos, snapshot, data tests y unit tests (sin ML ni temporada actual)
	$(DBT) build $(DBT_FLAGS) --exclude tag:ml --exclude tag:current

dbt-current:      ## Modelos de la temporada actual (Understat + SofaScore Argentina)
	$(DBT) build $(DBT_FLAGS) --select tag:current+

understat:        ## Ingesta de Understat (temporada actual de las 5 grandes)
	PYTHONPATH=. $(PY) -m ingestion.understat

sofascore:        ## Ingesta local/manual de SofaScore (Argentina; requiere setup-sofascore)
	PYTHONPATH=. $(PY) -m ingestion.sofascore --scope ARG --mode full --headful

dbt-train:        ## Entrena el modelo de valor de mercado (scikit-learn, en local) y construye sus tablas
	BQ_ML_DATASET=$(ML_DATASET) PYTHONPATH=. $(PY) -m ingestion.ml --dataset $(ML_FEATURES_DATASET) && \
	$(DBT) build $(DBT_FLAGS) --target $(DBT_TARGET) --select tag:ml

dbt-docs:         ## Documentación y linaje de dbt en http://localhost:8081
	$(DBT) docs generate $(DBT_FLAGS) && $(DBT) docs serve $(DBT_FLAGS) --port 8081

airflow-up:
	docker compose up -d --build

airflow-down:
	docker compose down

metrics:          ## Imprime la tabla de métricas para el README
	PYTHONPATH=. $(PY) scripts/metrics_report.py

export-parquet:   ## Exporta marts y ml a data/parquet para la app
	PYTHONPATH=. $(PY) scripts/export_parquet.py

app: export-parquet  ## Corre la app pública en http://localhost:8501
	$(PY) -m streamlit run app/streamlit_app.py
