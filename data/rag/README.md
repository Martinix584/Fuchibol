# Corpus del RAG

- `chunks.parquet`: fragmentos de texto de 2.486 artículos de **Wikipedia en español** (jugadores, clubes y
  torneos), bajados el 03/11/2026 con `python -m ingestion.wiki_corpus`. Cada fila guarda la URL de su
  artículo. Licencia del texto: [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/deed.es); los
  autores son los editores de cada artículo (ver el historial en su URL).
- `bm25.npz`: índice BM25 precalculado (`python -m app.rag bm25`), así la app no lo arma en runtime.
- `embeddings.npy`: un vector por fila de `chunks.parquet` (`gemini-embedding-001`, 768 dims, float16), con
  `python -m app.rag indexar`. Si se rehace el corpus, hay que reindexar.
