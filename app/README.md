# App pública

Streamlit sobre Parquet + DuckDB. No necesita GCP: los datos se exportan una vez
desde BigQuery con `make export-parquet` a `data/parquet/`.

```bash
make export-parquet   # marts + ml -> data/parquet/ (requiere ADC)
make app              # http://localhost:8501
```

## Páginas

- **Jugadores**: radar de percentiles por posición de la temporada actual
  (Understat/SofaScore, cada fuente por separado) y de StatsBomb (xT, PAdj, etc.).
- **Subvaluados**: ranking del modelo, real vs. predicho, R²/MAE e importancia de variables.
- **Fichajes**: costo vs. valor un año después, veredicto y balance por club.
- **Mapa de tiros**: tiros de StatsBomb sobre la cancha, tamaño = xG.

## Publicarla

Streamlit necesita un servidor Python, así que **no corre en Vercel** tal cual. Dos caminos:

1. **Streamlit Community Cloud (recomendado, gratis):**
   - `make export-parquet` y commitear `data/parquet/` (7,7 MB; está versionado a propósito
     porque Streamlit lee los datos del repo).
   - En <https://share.streamlit.io>: New app → repo → branch `main` → main file
     `app/streamlit_app.py`; en Advanced settings, Python 3.12 o 3.13.
   - Streamlit usa `app/requirements.txt`, que tiene prioridad sobre el `requirements.txt`
     de la raíz (ese es de la ingesta).
   - Para usar tu dominio de Vercel, dejá un proyecto chico que redirija a la URL de
     Streamlit (`vercel.json` con un redirect); el DNS de Vercel no puede apuntar directo
     a Streamlit.
2. **Todo en Vercel:** requiere reescribir la app como sitio estático (Evidence.dev o
   Next.js + DuckDB-WASM). Es otro proyecto, no un deploy.

`make export-parquet` lee `dev_marts` y `dev_ml` (o los datasets que le pases con
`--datasets`) y escribe en `data/parquet/marts` y `data/parquet/ml`, que es lo que espera
la app.

Antes de publicar, revisar licencias: StatsBomb pide atribución, Transfermarkt es CC0 y
Understat/SofaScore no tienen licencia explícita de redistribución. Si no querés
redistribuir esas dos fuentes, limitá la app a Transfermarkt + StatsBomb o pedí permiso.
