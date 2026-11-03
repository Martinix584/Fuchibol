import numpy as np
import pandas as pd

from app import rag


def _fake(monkeypatch):
    df = pd.DataFrame(
        {
            "title": ["Lionel Messi", "Lionel Messi", "Real Madrid", "Boca Juniors"],
            "section": ["Barcelona", "Selección", "Historia", "Historia"],
            "url": ["u1", "u2", "u3", "u4"],
            "text": [
                "Debutó en el Barcelona",
                "Campeón del mundo en Catar",
                "Club de Madrid",
                "La Bombonera",
            ],
            "entity_type": ["player", "player", "club", "club"],
            "player_id": pd.array([28003, 28003, None, None], dtype="Int64"),
            "club_id": pd.array([None, None, 418, 189], dtype="Int64"),
        }
    )
    emb = np.eye(4, dtype=np.float32)
    filas = zip(df.title, df.section, df.text, strict=True)
    bm25 = rag.BM25.construir([rag._tokens(f"{t} {s} {x}") for t, s, x in filas])
    monkeypatch.setattr(rag, "indice", lambda: (df, emb, bm25))
    # la pregunta "cae" cerca del fragmento 1 en el espacio denso
    monkeypatch.setattr(rag, "embeber", lambda _: np.array([[0, 1, 0, 0]], dtype=np.float32))


def test_hibrido_y_filtro(monkeypatch):
    _fake(monkeypatch)
    top = rag.buscar("campeón del mundo catar", k=2)
    assert top[0]["url"] == "u2"  # denso y BM25 coinciden
    solo_club = rag.buscar("historia", k=5, club_id=189)
    assert [r["url"] for r in solo_club] == ["u4"]
    assert solo_club[0]["player_id"] is None  # sin NA de pandas en la salida (va a JSON)
    sin_articulo = rag.buscar("historia", k=5, club_id=999)  # sin artículos: busca en todo
    assert len(sin_articulo) == 4


def test_tokens_sin_tildes():
    assert rag._tokens("Campeón, Catar!") == ["campeon", "catar"]


def test_solo_bm25_sin_embeddings(monkeypatch):
    _fake(monkeypatch)
    df, _, bm25 = rag.indice()
    monkeypatch.setattr(rag, "indice", lambda: (df, None, bm25))
    monkeypatch.setattr(rag, "embeber", lambda _: (_ for _ in ()).throw(AssertionError("no debe llamarse")))
    assert rag.buscar("bombonera", k=1)[0]["url"] == "u4"


def test_bm25_guardar_y_cargar(tmp_path):
    corpus = [["messi", "barcelona"], ["boca", "bombonera", "boca"], ["river", "monumental"]]
    bm = rag.BM25.construir(corpus)
    bm.guardar(tmp_path / "b.npz")
    otro = rag.BM25.cargar(tmp_path / "b.npz")
    q = ["boca", "messi"]
    assert abs(bm.get_scores(q) - otro.get_scores(q)).max() < 1e-2  # pesos guardados en float16
    assert otro.get_scores(["boca"]).argmax() == 1
