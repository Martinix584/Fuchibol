# Plan: agente con RAG híbrido (SQL + Wikipedia) en la app

> Estado (03/11/2026): E1 hecha (`app/sql_tool.py`). E2 corpus (`ingestion/wiki_corpus.py`), E3 índice
> (`app/rag.py`) y E4 agente (`app/agente.py`) escritos. Decididos: todo en Vertex (agente `gemini-3.8-flash`,
> embeddings `gemini-embedding-001` a 768 dims); Mem0 alojado (free tier); código de acceso +
> presupuesto de GCP. Falta: Mem0, evals (E5) y pestaña Chat (E6).

## 1. Qué es

Una pestaña **Chat** nueva en `app/streamlit_app.py`. El agente tiene dos tools:

- `consultar_stats(sql)`: SQL de solo lectura en DuckDB sobre `data/parquet/` (los mismos 7,7 MB que ya usa la
  app). **En runtime no se toca BigQuery ni GCP para los datos.**
- `buscar_contexto(pregunta, entidad?)`: búsqueda híbrida (BM25 + embeddings) sobre artículos de Wikipedia en
  español, con cita al artículo y la sección.

Preguntas de ejemplo:

- Solo SQL: "¿quién está más subvaluado en la Liga Argentina?"
- Solo RAG: "¿por qué se fue Di María del Real Madrid?"
- Las dos: "¿Argentina ganó la final de 2022 por suerte o por juego?" (xG de StatsBomb + relato).

**El enlace:** cada fragmento de texto lleva el `player_id`/`club_id` de `dim_players`/`dim_clubs`. Eso deja
que el agente cruce SQL y texto sobre la misma entidad, y es lo que lo separa de un RAG de tutorial.

## 2. Decisiones

1. **Proveedor: todo en Vertex.** Agente `gemini-3.8-flash`, embeddings `gemini-embedding-001` a 768 dims.
   Para el deploy hace falta una cuenta de servicio con rol Vertex AI User y su JSON en `st.secrets`.
2. **Mem0.** Streamlit Cloud no tiene disco persistente.
   - Mem0 alojado (free tier): la memoria sobrevive entre visitas. Es la única opción en la que Mem0 se puede
     mostrar.
   - Si la memoria es solo de sesión, Mem0 no aporta nada sobre el historial que ya está en `session_state`:
     en ese caso conviene no usarlo.
   - "Te recuerdo" necesita una identidad: un campo de nombre o `st.login`.
3. **Costo de la URL pública.** Un tope en `session_state` no frena a nadie, porque se resetea al recargar.
   - Por defecto: código de acceso para el chat (el resto de la app sigue público).
   - Siempre: un límite de gasto del lado del proveedor (presupuesto de GCP: ya existe "Fuchibol - alerta 1", 1 USD/mes, avisa al 50 % y 100 %).

## 3. Etapas

### E1. Tool SQL segura (½ día)
- Cargar los Parquet como tablas en una conexión DuckDB en memoria.
- Después ejecutar `SET enable_external_access=false; SET lock_configuration=true;` para que no pueda hacer
  `read_csv('/etc/passwd')` ni bajar URLs.
- Validar con **sqlglot** (ya está en `requirements-dev.txt`; sumarlo a `app/requirements.txt` fijado en la misma `30.23.0`): una
  sola sentencia `SELECT`, con `LIMIT` forzado a 200 filas.
- Timeout: DuckDB no tiene un timeout por consulta, así que un `threading.Timer` llama a `con.interrupt()` a los
  10 s.
- El prompt con el esquema se genera de los `.yml` de dbt (`dbt/models/**/_*.yml`), que ya describen las
  columnas. No se escribe a mano.
- `tests/test_sql_tool.py` tiene que rechazar: lectura de archivos, `DROP`/`INSERT`/`COPY`/`ATTACH`, varias
  sentencias encadenadas y una consulta lenta (que el timeout la corte).

### E2. Corpus de Wikipedia (1 día)
- Elegir los artículos con los propios datos: top-N jugadores por valor de mercado o minutos, clubes de las
  5 grandes y de la LPF, Mundiales, Copas América, Euros y finales que estén en StatsBomb.
- Para unir con nuestros IDs, usar Wikidata y no los nombres (50.000 jugadores, muchos se llaman igual).
  Verificar la propiedad "ID de Transfermarkt" de jugador y de club (P2446 y la de club). Con una consulta
  SPARQL sale ID de Transfermarkt → sitelink de es.wikipedia, y de ahí directo el `player_id`/`club_id`.
- Ojo: Wikidata da el ID de Transfermarkt. A las tablas de StatsBomb se llega por `mart_player_scouting.tm_player_id`,
  y a las de temporada actual (Understat/SofaScore) no hay puente por ID.
- Bajar el texto de la API de MediaWiki de es.wikipedia con un User-Agent propio.
- Licencia CC BY-SA: sumar la atribución a los créditos de fuentes de la app y del README.
- Script: `ingestion/wiki_corpus.py`, una sola corrida offline.

### E3. Índice (½ día)
- Dividir por sección y fragmento (unos 500 tokens), con metadatos `{titulo, seccion, url, player_id, club_id}`.
- Calcular los embeddings offline y guardarlos en `data/rag/chunks.parquet`, versionado como el resto.
- En runtime: coseno con numpy (alcanza para unos miles de fragmentos), BM25 (`rank_bm25`) y fusión RRF.
  Sumar un reranker solo si las evals muestran que falta.
- La pregunta se embebe con **el mismo modelo** que el índice, así que ese proveedor tiene que responder desde
  Streamlit Cloud.

### E4. Agente (1 día)
- LangChain v1. Antes de escribir código, verificar la API actual (`create_agent` / LangGraph) contra la
  versión instalada.
- Las dos tools de arriba, más Mem0 según la decisión 2.2.
- System prompt: siempre citar el artículo, o la tabla y la consulta usada. Si no está en los datos, decirlo.
- Streaming en la UI, y mostrar qué tool usó y qué SQL corrió (vende mucho en la demo).

### E5. Evals (½ a 1 día)
- `evals/preguntas.yaml`: entre 30 y 50 preguntas con la tool esperada y, si son numéricas, el SQL de verdad.
- `evals/correr.py`, sin framework. Mide:
  - acierto de tool
  - al menos una pregunta que cruce fuentes (StatsBomb ↔ Transfermarkt), porque `player_id` cambia de significado
    según la tabla
  - respuesta numérica igual a la de la consulta de verdad
  - que la cita de RAG contenga lo afirmado (juez LLM)
- Publicar los números en el README, igual que las métricas del pipeline.

### E6. UI y deploy (½ día)
- Pestaña Chat, código de acceso, secrets en Streamlit Cloud y dependencias nuevas en `app/requirements.txt`.
- Un GIF o video corto para el README.

## 4. Criterios de terminado
- `pytest` pasa, incluido el test de la tool SQL.
- Las evals dan ≥ 85 % de acierto de tool y ≥ 90 % de respuestas numéricas correctas (ajustar después de la
  primera corrida).
- La pestaña anda en la URL pública, con código de acceso, límite de gasto y atribución de Wikipedia.

Total estimado: 3 a 5 días.
