"""Búsqueda híbrida sobre data/rag/: BM25 + embeddings (Vertex), fusionados con RRF.

    python -m app.rag indexar     # calcula data/rag/embeddings.npy (requiere credenciales de GCP)

Las preguntas se embeben con el MISMO modelo que el índice: si cambia EMBED_MODEL, reindexar.
"""

from __future__ import annotations

import os
import re
import sys
import time
import unicodedata
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from google import genai
from google.genai import types
from rank_bm25 import BM25Okapi

RAG = Path(__file__).resolve().parents[1] / "data" / "rag"
EMBED_MODEL = "gemini-embedding-001"
EMBED_DIM = 768
PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "fuchibol-512404")
RRF_K = 60


def _tokens(t: str) -> list[str]:
    t = unicodedata.normalize("NFKD", t.lower())
    return re.findall(r"\w+", "".join(c for c in t if not unicodedata.combining(c)))


@lru_cache(maxsize=1)
def _cliente() -> genai.Client:
    return genai.Client(vertexai=True, project=PROJECT, location="global")


def embeber(textos: list[str], tarea: str = "RETRIEVAL_QUERY") -> np.ndarray:
    r = _cliente().models.embed_content(
        model=EMBED_MODEL,
        contents=textos,
        config=types.EmbedContentConfig(task_type=tarea, output_dimensionality=EMBED_DIM),
    )
    v = np.array([e.values for e in r.embeddings], dtype=np.float32)
    # con menos de 3072 dimensiones Gemini no devuelve vectores normalizados
    return v / np.linalg.norm(v, axis=1, keepdims=True)


@lru_cache(maxsize=1)
def indice() -> tuple[pd.DataFrame, np.ndarray | None, BM25Okapi]:
    """Sin embeddings.npy (todavía no se indexó) la búsqueda queda solo con BM25."""
    df = pd.read_parquet(RAG / "chunks.parquet")
    emb = None
    if (RAG / "embeddings.npy").exists():
        emb = np.load(RAG / "embeddings.npy").astype(np.float32)
        assert len(df) == len(emb), "chunks y embeddings desalineados: reindexar"
    bm25 = BM25Okapi([_tokens(f"{t} {s} {x}") for t, s, x in zip(df.title, df.section, df.text, strict=True)])
    return df, emb, bm25


def buscar(pregunta: str, k: int = 6, player_id: int | None = None, club_id: int | None = None) -> list[dict]:
    """Top-k fragmentos. Si se pasa una entidad, busca solo en sus artículos (si tiene)."""
    df, emb, bm25 = indice()
    mascara = np.ones(len(df), dtype=bool)
    if player_id is not None:
        mascara = (df.player_id == player_id).fillna(False).to_numpy()
    elif club_id is not None:
        mascara = (df.club_id == club_id).fillna(False).to_numpy()
    if not mascara.any():
        mascara[:] = True
    idx = np.flatnonzero(mascara)

    rankings = [bm25.get_scores(_tokens(pregunta))[idx]]
    if emb is not None:
        rankings.append(emb[idx] @ embeber([pregunta])[0])
    rrf = np.zeros(len(idx))
    for scores in rankings:
        rrf[np.argsort(-scores)] += 1 / (RRF_K + np.arange(1, len(idx) + 1))
    top = idx[np.argsort(-rrf)[:k]]
    cols = ["title", "section", "url", "text", "entity_type", "player_id", "club_id"]
    return df.iloc[top][cols].astype(object).where(df.iloc[top][cols].notna(), None).to_dict("records")


def indexar(lote: int = 64) -> None:
    df = pd.read_parquet(RAG / "chunks.parquet")
    textos = [f"{t} — {s}\n{x}" for t, s, x in zip(df.title, df.section, df.text, strict=True)]
    partes = []
    for i in range(0, len(textos), lote):
        for intento in range(6):
            try:
                partes.append(embeber(textos[i : i + lote], "RETRIEVAL_DOCUMENT"))
                break
            except genai.errors.APIError as e:  # 429 de cuota por minuto: esperar y reintentar
                if e.code != 429 or intento == 5:
                    raise
                time.sleep(10 * (intento + 1))
        print(f"{min(i + lote, len(textos))}/{len(textos)}", flush=True)
    # float16: la mitad de peso en el repo, sin diferencia práctica para coseno
    np.save(RAG / "embeddings.npy", np.vstack(partes).astype(np.float16))


if __name__ == "__main__" and sys.argv[1:] == ["indexar"]:
    indexar()
