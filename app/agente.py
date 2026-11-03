"""Agente de Fuchibol: Gemini 3.8 Flash (Vertex) + SQL sobre los marts + RAG sobre Wikipedia.

    python -m app.agente "¿quién está más subvaluado en la Liga Argentina?"
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import sys
import threading
from functools import lru_cache

from langchain.agents import create_agent
from langchain.tools import tool
from langchain_core.messages import AIMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.errors import GraphRecursionError
from mem0 import MemoryClient
from mem0.client.types import SearchMemoryOptions

from app import rag
from app.sql_tool import SQLRechazado, conectar, consultar, esquema

MODEL = "gemini-3.8-flash"
PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "fuchibol-512404")
# Tope de gasto del lado de la app: preguntas por día para todo el proceso (todas las sesiones de Streamlit)
# y pasos por pregunta. El presupuesto de GCP solo avisa; esto corta.
# ponytail: contador en memoria, se resetea si Streamlit reinicia; persistirlo si eso pasa seguido.
MAX_PREGUNTAS_DIA = 30  # ~0,036 USD por pregunta mixta (40k tokens in, 1,5k out) -> ~1 USD/día como máximo
MAX_CHARS_TOOL = 6000
MAX_PASOS = 25  # cada turno del modelo y cada tool cuenta; una pregunta mixta usa ~10

_cupo = {"dia": None, "usadas": 0}
_cupo_lock = threading.Lock()


class SinCupo(RuntimeError):
    pass


def tomar_cupo(hoy: dt.date | None = None) -> int:
    """Descuenta una pregunta del cupo diario y devuelve cuántas quedan. SinCupo si no hay."""
    hoy = hoy or dt.date.today()
    with _cupo_lock:
        if _cupo["dia"] != hoy:
            _cupo.update(dia=hoy, usadas=0)
        if _cupo["usadas"] >= MAX_PREGUNTAS_DIA:
            raise SinCupo("Se terminó el cupo de preguntas de hoy. Volvé mañana.")
        _cupo["usadas"] += 1
        return MAX_PREGUNTAS_DIA - _cupo["usadas"]

PROMPT = """Sos el analista de datos de Fuchibol. Respondés en castellano rioplatense, corto y concreto.

Tenés dos herramientas:
- consultar_stats: SQL (DuckDB) de solo lectura sobre los datos de abajo. Para números, rankings y
  comparaciones.
- buscar_contexto: fragmentos de Wikipedia en español. Para historia, contexto, polémicas, por qué pasó algo.
Si la pregunta mezcla números y relato, usá las dos. Para buscar sobre un jugador o club que ya identificaste
por SQL, pasale a buscar_contexto su player_id o club_id de Transfermarkt.

Reglas:
- Nunca inventes números: todo número sale de una consulta. Si un SQL falla, leé el error y corregilo.
- Citá siempre: para datos, la tabla; para texto, el título del artículo de Wikipedia.
- Si no está en los datos, decilo. No completes con lo que sabés de memoria.
- Valores de mercado en euros (Transfermarkt). xG y demás según la fuente indicada en cada tabla.

Esquema:
{esquema}
"""


@lru_cache(maxsize=1)
def _con():
    return conectar()


@tool
def consultar_stats(sql: str) -> str:
    """Corre un SELECT de DuckDB sobre las tablas del esquema. Devuelve hasta 200 filas en JSON."""
    try:
        out = json.dumps(consultar(_con(), sql), default=str, ensure_ascii=False)
        if len(out) > MAX_CHARS_TOOL:  # cada paso reenvía todo: un resultado gigante multiplica el costo
            out = out[:MAX_CHARS_TOOL] + " …[resultado truncado: pedí solo las columnas necesarias o agregá]"
        return out
    except SQLRechazado as e:
        return f"ERROR: {e}"
    except Exception as e:  # error de DuckDB (columna mal escrita, etc.): que el modelo lo corrija
        return f"ERROR de SQL: {e}"


@tool
def buscar_contexto(pregunta: str, player_id: int | None = None, club_id: int | None = None) -> str:
    """Busca en Wikipedia (es). player_id/club_id (de Transfermarkt) restringen a los artículos de esa
    entidad."""
    frs = rag.buscar(pregunta, k=6, player_id=player_id, club_id=club_id)
    return json.dumps(
        [{"articulo": f["title"], "seccion": f["section"], "url": f["url"], "texto": f["text"]} for f in frs],
        ensure_ascii=False,
    )


MEMORIA = """Guardá solo preferencias futboleras del usuario: equipo que sigue, jugadores, ligas o
posiciones que le interesan, y el tipo de análisis que pide. Nada de datos personales ni de los resultados
de las consultas. Escribí cada memoria en español."""
log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _mem0() -> MemoryClient | None:
    key = os.environ.get("MEM0_API_KEY")
    return MemoryClient(api_key=key) if key else None


def recordar(usuario: str, pregunta: str) -> list[str]:
    """Memorias de Mem0 relevantes a la pregunta. Si Mem0 falla, el chat sigue sin memoria."""
    if not (m := _mem0()):
        return []
    try:
        r = m.search(pregunta, SearchMemoryOptions(filters={"user_id": usuario}, top_k=5))
        return [x["memory"] for x in r.get("results", r if isinstance(r, list) else [])]
    except Exception:
        log.exception("Mem0 search")
        return []


def guardar(usuario: str, pregunta: str, respuesta: str) -> None:
    if not (m := _mem0()):
        return
    try:
        msgs = [{"role": "user", "content": pregunta}, {"role": "assistant", "content": respuesta}]
        # add quiere user_id suelto (con filters= el API responde 400); search sí lo quiere en filters
        m.add(msgs, user_id=usuario, custom_instructions=MEMORIA)
    except Exception:
        log.exception("Mem0 add")


@lru_cache(maxsize=1)
def agente():
    llm = ChatGoogleGenerativeAI(
        model=MODEL, vertexai=True, project=PROJECT, location="global", temperature=0
    )
    prompt = PROMPT.format(esquema=esquema(_con()))
    return create_agent(llm, [consultar_stats, buscar_contexto], system_prompt=prompt)


def preguntar(mensajes: list[dict], usuario: str | None = None) -> list:
    """mensajes: [{"role": "user"|"assistant", "content": str}, ...]. Devuelve los mensajes del turno.
    Con usuario, usa Mem0: trae lo que se sabe de él y guarda lo nuevo."""
    tomar_cupo()
    pregunta = mensajes[-1]["content"]
    if usuario and (mems := recordar(usuario, pregunta)):
        contexto = "\n".join(f"- {x}" for x in mems)
        con_memoria = f"[Lo que sabés del usuario]\n{contexto}\n\n{pregunta}"
        mensajes = [*mensajes[:-1], {"role": "user", "content": con_memoria}]
    try:
        out = agente().invoke({"messages": mensajes}, config={"recursion_limit": MAX_PASOS})["messages"]
    except GraphRecursionError:
        return [AIMessage("La pregunta necesitó demasiados pasos. Probá reformularla más concreta.")]
    if usuario:
        guardar(usuario, pregunta, out[-1].text)
    return out


if __name__ == "__main__":
    usuario = os.environ.get("FUCHIBOL_USUARIO")  # para probar la memoria desde la terminal
    for m in preguntar([{"role": "user", "content": " ".join(sys.argv[1:])}], usuario):
        for tc in getattr(m, "tool_calls", None) or []:
            print(f"[{tc['name']}] {tc['args']}")
    print(m.text)
