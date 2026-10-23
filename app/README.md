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

Opción simple: [Streamlit Community Cloud](https://share.streamlit.io) apuntando a este
repo, con `app/streamlit_app.py` como entrypoint y `app/requirements.txt` como dependencias.
Los Parquet tienen que estar en el repo (o en un bucket público) en `data/parquet/`.

Antes de publicar, revisar licencias: StatsBomb pide atribución, Transfermarkt es CC0 y
Understat/SofaScore no tienen licencia explícita de redistribución. Si no querés
redistribuir esas dos fuentes, limitá la app a Transfermarkt + StatsBomb o pedí permiso.
