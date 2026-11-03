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
- **Chat**: agente (Gemini 3.8 Flash en Vertex, LangChain) con dos tools: SQL de solo lectura sobre estos
  Parquet y RAG híbrido (BM25 + embeddings) sobre Wikipedia en español, más memoria con Mem0. Pide código de
  acceso y tiene cupo diario. Secrets: ver el docstring de `app/chat_tab.py`.

## Publicarla

Está en **Cloud Run** (https://fuchibol-861967550352.us-central1.run.app): `python deploy/publicar.py` arma la
imagen con Docker local, la sube a Artifact Registry y despliega con la cuenta de servicio `fuchibol-app` (sin
clave JSON) y el código del chat de `.streamlit/secrets.toml`. Escala a cero (gratis, con arranque en frío) y a
lo sumo una instancia (tope de costo).

Streamlit Community Cloud quedó chico: con su CPU mínima, cargar LangChain al abrir el chat trababa el servidor
y el navegador no llegaba a bajar los JS de la página.

`make export-parquet` lee `dev_marts` y `dev_ml` (o los datasets que le pases con
`--datasets`) y escribe en `data/parquet/marts` y `data/parquet/ml`, que es lo que espera
la app.

Antes de publicar, revisar licencias: StatsBomb pide atribución, Transfermarkt es CC0 y
Understat/SofaScore no tienen licencia explícita de redistribución. Si no querés
redistribuir esas dos fuentes, limitá la app a Transfermarkt + StatsBomb o pedí permiso.
