"""Evals del agente, sin framework: ruteo de tools, valor correcto y artículo recuperado.

python -m evals.correr            # todas las preguntas -> evals/resultados.json
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

import yaml

from app.agente import preguntar
from app.sql_tool import conectar

DIR = Path(__file__).parent
TOOLS = {
    "sql": {"consultar_stats"},
    "rag": {"buscar_contexto"},
    "mixto": {"consultar_stats", "buscar_contexto"},
}


def norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", str(t).lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def numeros(texto: str) -> list[float]:
    """Números de una respuesta en castellano: 1.234.567, 1,98, 1.98, €8.000.000."""
    out = []
    for n in re.findall(r"\d[\d.,]*\d|\d", texto):
        if "," in n and "." in n:
            n = n.replace(".", "").replace(",", ".")
        elif "," in n:
            n = n.replace(",", ".")
        elif re.fullmatch(r"\d{1,3}(\.\d{3})+", n):
            n = n.replace(".", "")
        try:
            out.append(float(n))
        except ValueError:
            pass
    return out


def valor_ok(esperado, respuesta: str, acepta: list[str]) -> bool:
    if isinstance(esperado, int | float):
        # "100 millones" / "100 M€" también vale para 100.000.000
        cands = [y for x in numeros(respuesta) for y in (x, x * 1e6)]
        return any(abs(y - esperado) <= max(0.02, abs(esperado) * 0.01) for y in cands)
    return any(norm(e) in norm(respuesta) for e in [esperado, *acepta])


def correr_una(q: dict, con) -> dict:
    msgs = preguntar([{"role": "user", "content": q["pregunta"]}])
    usadas = {tc["name"] for m in msgs for tc in (getattr(m, "tool_calls", None) or [])}
    articulos = set()
    for m in msgs:
        if getattr(m, "name", None) == "buscar_contexto":
            try:
                articulos |= {f["articulo"] for f in json.loads(m.content)}
            except (json.JSONDecodeError, TypeError):
                pass
    respuesta = msgs[-1].text
    r = {
        "pregunta": q["pregunta"],
        "tipo": q["tipo"],
        "tools": sorted(usadas),
        "respuesta": respuesta,
        "tool_ok": TOOLS[q["tipo"]] <= usadas,
    }
    if "verdad" in q:
        esperado = con.execute(q["verdad"]).fetchone()[0]
        r["esperado"] = esperado
        r["valor_ok"] = valor_ok(esperado, respuesta, q.get("acepta", []))
    if "articulo" in q:
        r["articulo_ok"] = q["articulo"] in articulos
    return r


def main() -> None:
    preguntas = yaml.safe_load((DIR / "preguntas.yaml").read_text())
    if sys.argv[1:]:
        preguntas = [q for q in preguntas if any(a.lower() in q["pregunta"].lower() for a in sys.argv[1:])]
    con = conectar()
    res = []
    for i, q in enumerate(preguntas, 1):
        r = correr_una(q, con)
        res.append(r)
        marcas = " ".join(f"{k[:-3]}={'✓' if v else '✗'}" for k, v in r.items() if k.endswith("_ok"))
        print(f"{i:2}/{len(preguntas)} {marcas}  {q['pregunta'][:70]}", flush=True)
    (DIR / "resultados.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    for k in ("tool_ok", "valor_ok", "articulo_ok"):
        vals = [r[k] for r in res if k in r]
        if vals:
            print(f"{k}: {sum(vals)}/{len(vals)} ({100 * sum(vals) / len(vals):.0f} %)")


if __name__ == "__main__":
    main()
