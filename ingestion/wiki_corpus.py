"""Corpus de Wikipedia (es) para el RAG del agente. Corrida offline, una vez:

    python -m ingestion.wiki_corpus      # -> data/rag/chunks.parquet

Une por Wikidata (ID de Transfermarkt: P2446 jugador, P7223 club), no por nombre, así cada
fragmento lleva el player_id/club_id de Transfermarkt. Texto CC BY-SA 4.0: se cita la URL.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path

import duckdb
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
MARTS = ROOT / "data" / "parquet" / "marts"
OUT = ROOT / "data" / "rag" / "chunks.parquet"
UA = "FuchibolBot/0.1 (https://github.com/Martinix584/Fuchibol; corpus para RAG)"
WIKI = "https://es.wikipedia.org/w/api.php"
SPARQL = "https://query.wikidata.org/sparql"

LIGAS = ("ES1", "GB1", "IT1", "L1", "FR1", "ARG1")
TORNEOS = [
    "Copa Mundial de Fútbol de 2018",
    "Copa Mundial de Fútbol de 2022",
    "Eurocopa 2020",
    "Eurocopa 2024",
    "Copa América 2024",
    "Copa Africana de Naciones 2023",
    "1. Bundesliga 2023-24",
    "Final de la Copa Mundial de Fútbol de 2022",
]
SECCIONES_FUERA = {
    "referencias", "enlaces externos", "bibliografía", "véase también", "notas", "notas y referencias",
    "fuentes", "galería", "galería de imágenes", "lectura adicional", "estadísticas",
}
MAX_CHARS = 1500
MAX_POR_ARTICULO = 40_000

log = logging.getLogger("wiki_corpus")
s = requests.Session()
s.headers["User-Agent"] = UA


def _get(url: str, params: dict) -> dict:
    for intento in range(5):
        r = s.get(url, params=params, timeout=60)
        if r.status_code in (429, 503):
            time.sleep(5 * (intento + 1))
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()
    return {}


def candidatos() -> tuple[list[int], list[int]]:
    con = duckdb.connect()
    tablas = ("dim_players", "dim_clubs", "mart_player_scouting")
    p, c, sc = (f"'{(MARTS / t).as_posix()}.parquet'" for t in tablas)
    jugadores = con.sql(f"""
        (select player_id from {p} where last_season_played >= 2015
         order by highest_market_value_eur desc nulls last limit 1200)
        union
        (select p.player_id from {p} p join {c} c on c.club_id = p.current_club_id
         where c.domestic_competition_id = 'ARG1' order by p.market_value_eur desc nulls last limit 300)
        union
        (select s.tm_player_id from {sc} s join {p} p on p.player_id = s.tm_player_id
         where p.highest_market_value_eur >= 5000000)
    """).fetchall()
    clubes = con.sql(f"select club_id from {c} where domestic_competition_id in {LIGAS}").fetchall()
    return [r[0] for r in jugadores], [r[0] for r in clubes]


def titulos_por_tm(ids: list[int], prop: str) -> dict[int, str]:
    """ID de Transfermarkt -> título en es.wikipedia, por Wikidata."""
    out: dict[int, str] = {}
    for i in range(0, len(ids), 250):
        values = " ".join(f'"{x}"' for x in ids[i : i + 250])
        q = f"""SELECT ?tm ?art WHERE {{ VALUES ?tm {{ {values} }} ?it wdt:{prop} ?tm .
                ?art schema:about ?it ; schema:isPartOf <https://es.wikipedia.org/> . }}"""
        for b in _get(SPARQL, {"query": q, "format": "json"})["results"]["bindings"]:
            titulo = requests.utils.unquote(b["art"]["value"].rsplit("/wiki/", 1)[1]).replace("_", " ")
            out.setdefault(int(b["tm"]["value"]), titulo)
        time.sleep(1)
    return out


def texto(titulo: str) -> tuple[str, str] | None:
    d = _get(WIKI, {
        "action": "query", "prop": "extracts", "explaintext": 1, "redirects": 1,
        "titles": titulo, "format": "json", "formatversion": 2,
    })
    pag = d["query"]["pages"][0]
    if pag.get("missing") or not pag.get("extract"):
        return None
    return pag["title"], pag["extract"][:MAX_POR_ARTICULO]


def fragmentos(extracto: str) -> list[tuple[str, str]]:
    """(sección, texto) de hasta MAX_CHARS, cortando por párrafo y salteando secciones sin contenido útil."""
    out: list[tuple[str, str]] = []
    seccion, saltear = "Introducción", False
    buf = ""
    for linea in extracto.splitlines():
        m = re.match(r"^(=+)\s*(.*?)\s*=+$", linea)
        if m:
            if buf.strip() and not saltear:
                out.append((seccion, buf.strip()))
            buf = ""
            nivel, nombre = len(m.group(1)), m.group(2)
            if nivel == 2:
                seccion, saltear = nombre, nombre.lower() in SECCIONES_FUERA
            elif not saltear:
                seccion = f"{seccion.split(' > ')[0]} > {nombre}"
            continue
        if not linea.strip() or saltear:
            continue
        # los párrafos de Wikipedia suelen ser una sola línea larga: se parten por oración
        for oracion in re.split(r"(?<=[.!?])\s+", linea):
            if len(buf) + len(oracion) > MAX_CHARS and buf:
                out.append((seccion, buf.strip()))
                buf = ""
            buf += oracion + " "
        buf += "\n"
    if buf.strip() and not saltear:
        out.append((seccion, buf.strip()))
    return [(sec, t) for sec, t in out if len(t) >= 80]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    jugadores, clubes = candidatos()
    log.info("candidatos: %d jugadores, %d clubes", len(jugadores), len(clubes))
    articulos = (
        [("player", i, t) for i, t in titulos_por_tm(jugadores, "P2446").items()]
        + [("club", i, t) for i, t in titulos_por_tm(clubes, "P7223").items()]
        + [("tournament", None, t) for t in TORNEOS]
    )
    log.info("con artículo en es.wikipedia: %d", len(articulos))
    filas = []
    for n, (tipo, tm_id, titulo) in enumerate(articulos, 1):
        r = texto(titulo)
        if r is None:
            log.warning("sin texto: %s", titulo)
            continue
        titulo, ext = r
        url = "https://es.wikipedia.org/wiki/" + titulo.replace(" ", "_")
        for k, (sec, t) in enumerate(fragmentos(ext)):
            filas.append({
                "chunk_id": f"{titulo}#{k}", "title": titulo, "section": sec, "url": url, "text": t,
                "entity_type": tipo,
                "player_id": tm_id if tipo == "player" else None,
                "club_id": tm_id if tipo == "club" else None,
            })
        if n % 100 == 0:
            log.info("%d/%d artículos, %d fragmentos", n, len(articulos), len(filas))
        time.sleep(0.2)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(filas).astype({"player_id": "Int64", "club_id": "Int64"})
    df.to_parquet(OUT, index=False)
    log.info("listo: %d fragmentos de %d artículos -> %s", len(df), df["title"].nunique(), OUT)


if __name__ == "__main__":
    main()
