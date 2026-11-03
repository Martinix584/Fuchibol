"""Búsqueda híbrida sobre data/rag/: BM25 + embeddings (Vertex), fusionados con RRF.

    python -m app.rag indexar     # embeddings.npy (requiere credenciales de GCP) + bm25.npz
    python -m app.rag bm25        # solo bm25.npz (sin red)

Las preguntas se embeben con el MISMO modelo que el índice: si cambia EMBED_MODEL, reindexar.
"""

from __future__ import annotations

import os
import re
import sys
import time
import unicodedata
from collections import Counter
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from google import genai
from google.genai import types

RAG = Path(__file__).resolve().parents[1] / "data" / "rag"
EMBED_MODEL = "gemini-embedding-001"
EMBED_DIM = 768
PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "fuchibol-512404")
RRF_K = 60


def _tokens(t: str) -> list[str]:
    t = unicodedata.normalize("NFKD", t.lower())
    return re.findall(r"\w+", "".join(c for c in t if not unicodedata.combining(c)))


class BM25:
    """BM25 Okapi (mismas fórmulas que rank_bm25) precalculado como listas invertidas en numpy.

    Construirlo en Python tarda segundos acá y minutos en la CPU de Streamlit Cloud (y traba la app
    entera por el GIL), así que se arma offline y en runtime solo se carga el .npz."""

    def __init__(self, vocab: dict[str, int], indptr, docs, pesos, n_docs: int):
        self.vocab, self.indptr, self.docs, self.pesos, self.n_docs = vocab, indptr, docs, pesos, n_docs

    @classmethod
    def construir(cls, corpus: list[list[str]], k1: float = 1.5, b: float = 0.75, eps: float = 0.25) -> BM25:
        n_docs = len(corpus)
        dl = np.array([len(d) for d in corpus], dtype=np.float64)
        postings: dict[str, list[tuple[int, int]]] = {}
        for i, d in enumerate(corpus):
            for t, f in Counter(d).items():
                postings.setdefault(t, []).append((i, f))
        n = np.array([len(p) for p in postings.values()], dtype=np.float64)
        idf = np.log((n_docs - n + 0.5) / (n + 0.5))
        idf = np.where(idf < 0, eps * idf.mean(), idf)
        indptr = np.concatenate([[0], np.cumsum(n)]).astype(np.int64)
        docs = np.empty(indptr[-1], dtype=np.int32)
        pesos = np.empty(indptr[-1], dtype=np.float32)
        for k, p in enumerate(postings.values()):
            ids, tf = np.array(p, dtype=np.int64).T
            docs[indptr[k] : indptr[k + 1]] = ids
            pesos[indptr[k] : indptr[k + 1]] = (
                idf[k] * tf * (k1 + 1) / (tf + k1 * (1 - b + b * dl[ids] / dl.mean()))
            )
        return cls({t: k for k, t in enumerate(postings)}, indptr, docs, pesos, n_docs)

    def get_scores(self, tokens: list[str]) -> np.ndarray:
        s = np.zeros(self.n_docs, dtype=np.float32)
        for t in tokens:
            if (k := self.vocab.get(t)) is not None:
                a, z = self.indptr[k], self.indptr[k + 1]
                s[self.docs[a:z]] += self.pesos[a:z]
        return s

    def guardar(self, path: Path) -> None:
        np.savez_compressed(
            path,
            vocab=np.array(list(self.vocab)),
            indptr=self.indptr,
            docs=self.docs,
            pesos=self.pesos.astype(np.float16),
            n_docs=self.n_docs,
        )

    @classmethod
    def cargar(cls, path: Path) -> BM25:
        z = np.load(path)
        vocab = {t: k for k, t in enumerate(z["vocab"].tolist())}
        return cls(vocab, z["indptr"], z["docs"], z["pesos"].astype(np.float32), int(z["n_docs"]))


def _corpus(df: pd.DataFrame) -> list[list[str]]:
    return [_tokens(f"{t} {s} {x}") for t, s, x in zip(df.title, df.section, df.text, strict=True)]


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
def indice() -> tuple[pd.DataFrame, np.ndarray | None, BM25]:
    """Sin embeddings.npy (todavía no se indexó) la búsqueda queda solo con BM25."""
    df = pd.read_parquet(RAG / "chunks.parquet")
    emb = None
    if (RAG / "embeddings.npy").exists():
        emb = np.load(RAG / "embeddings.npy").astype(np.float32)
        assert len(df) == len(emb), "chunks y embeddings desalineados: reindexar"
    if (RAG / "bm25.npz").exists():
        bm25 = BM25.cargar(RAG / "bm25.npz")
        assert bm25.n_docs == len(df), "chunks y bm25 desalineados: python -m app.rag bm25"
    else:
        bm25 = BM25.construir(_corpus(df))
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
    indexar_bm25()


def indexar_bm25() -> None:
    BM25.construir(_corpus(pd.read_parquet(RAG / "chunks.parquet"))).guardar(RAG / "bm25.npz")


if __name__ == "__main__":
    {"indexar": indexar, "bm25": indexar_bm25}[sys.argv[1]]()
