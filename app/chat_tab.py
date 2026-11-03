"""Pestaña Chat: el agente (app/agente.py) con código de acceso y memoria por nombre.

Secrets (Streamlit Cloud → Settings → Secrets, o .streamlit/secrets.toml en local):
    CHAT_CODIGO = "..."          # sin esto el chat queda cerrado
    MEM0_API_KEY = "..."         # opcional: memoria entre visitas
    [gcp_service_account]        # JSON de la cuenta de servicio fuchibol-app (en local alcanza con ADC)
    type = "service_account"
    ...
"""

from __future__ import annotations

import hmac
import json
import os
import re
import tempfile

import streamlit as st

EJEMPLOS = [
    "¿Quién es el jugador más subvaluado de la Liga Argentina?",
    "¿Argentina ganó la final del Mundial 2022 por suerte o por juego?",
    "¿Cuánto vale Julián Álvarez y por qué se fue del City?",
]


def _secreto(clave: str):
    try:
        return st.secrets.get(clave)
    except FileNotFoundError:  # sin secrets.toml en local
        return None


def _credenciales() -> None:
    """En Streamlit Cloud no hay ADC: escribe la cuenta de servicio de secrets a un archivo temporal."""
    sa = _secreto("gcp_service_account")
    if sa and not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(dict(sa), f)
        f.close()
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = f.name
    if mem0 := _secreto("MEM0_API_KEY"):
        os.environ.setdefault("MEM0_API_KEY", mem0)


def _mostrar_pasos(pasos: list[dict]) -> None:
    if not pasos:
        return
    with st.expander(f"Cómo lo respondió ({len(pasos)} pasos)"):
        for p in pasos:
            if p["tool"] == "consultar_stats":
                st.code(p["args"].get("sql", ""), language="sql")
            else:
                st.markdown(f"🔎 Wikipedia: *{p['args'].get('pregunta', '')}*")


def render() -> None:
    codigo = _secreto("CHAT_CODIGO")
    if not codigo:
        st.info("El chat está cerrado: falta configurar `CHAT_CODIGO` en los secrets.")
        return
    if not st.session_state.get("chat_ok"):
        ingresado = st.text_input("Código de acceso", type="password")
        if ingresado and hmac.compare_digest(ingresado, str(codigo)):
            st.session_state.chat_ok = True
            st.rerun()
        elif ingresado:
            st.error("Código incorrecto.")
        st.caption("El chat usa un LLM pago, por eso tiene código. Pedíselo a Martín.")
        return

    _credenciales()
    from app.agente import SinCupo, preguntar  # import tardío: las otras pestañas no cargan LangChain

    nombre = st.text_input("Tu nombre (opcional, para que el agente te recuerde la próxima vez)")
    usuario = re.sub(r"[^a-z0-9]+", "-", nombre.strip().lower()).strip("-") or None

    hist = st.session_state.setdefault("chat", [])
    if not hist:
        st.caption("Probá con: " + " · ".join(f"*{e}*" for e in EJEMPLOS))
    for m in hist:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
            _mostrar_pasos(m.get("pasos", []))

    pregunta = st.chat_input("Preguntale a los datos…")
    if not pregunta:
        return
    hist.append({"role": "user", "content": pregunta})
    with st.chat_message("user"):
        st.markdown(pregunta)
    with st.chat_message("assistant"):
        with st.spinner("Consultando datos y Wikipedia…"):
            try:
                msgs = preguntar([{"role": m["role"], "content": m["content"]} for m in hist], usuario)
                texto = msgs[-1].text
                pasos = [
                    {"tool": tc["name"], "args": tc["args"]}
                    for m in msgs
                    for tc in (getattr(m, "tool_calls", None) or [])
                ]
            except SinCupo as e:
                texto, pasos = str(e), []
            except Exception as e:  # Vertex caído, cuota, etc.: no romper la app
                texto, pasos = f"No pude responder ahora ({type(e).__name__}). Probá en un rato.", []
        st.markdown(texto)
        _mostrar_pasos(pasos)
    hist.append({"role": "assistant", "content": texto, "pasos": pasos})
