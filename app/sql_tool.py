"""Tool SQL del agente: un SELECT de solo lectura sobre los Parquet de data/parquet/.

Tres capas, por si una falla:
1. sqlglot: una sola sentencia, de tipo consulta, y solo contra tablas conocidas
   (nada de read_csv, ATTACH, etc.).
2. DuckDB sin acceso externo y con la configuración bloqueada: aunque algo pase el filtro,
   no lee archivos ni URLs.
3. Tope de filas y timeout (con interrupt, porque DuckDB no tiene timeout por consulta).
"""

from __future__ import annotations

import threading
from pathlib import Path

import duckdb
import sqlglot
import yaml
from sqlglot import exp

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "parquet"
MAX_ROWS = 200
TIMEOUT_S = 10.0
# Funciones escalares que leen el entorno o la configuración
# (las de tabla ya caen por no ser tablas conocidas).
FUNCIONES_PROHIBIDAS = {"getenv", "current_setting", "current_setting_value"}

IDS = """IDs: `player_id` NO es el mismo en todas las tablas.
- dim_players, mart_player_seasons, mart_transfer_roi, mart_argentina_exports, mart_undervalued_players,
  ml_*: ID de Transfermarkt.
- fct_sb_*, mart_sb_*, mart_player_scouting: ID de StatsBomb. El puente es mart_player_scouting.tm_player_id.
- mart_current_*: ID de Understat o SofaScore según xg_source; player_key = xg_source:player_id.
  No se une con las otras fuentes por ID: solo por nombre, y avisando que puede fallar.
"""


class SQLRechazado(ValueError):
    pass


def _parquets() -> list[Path]:
    # ml/ tiene copias viejas sin prefijo (model_*, feature_importance): solo las ml_* y mart_*.
    return [
        p
        for p in sorted(DATA.glob("*/*.parquet"))
        if p.parent.name == "marts" or p.stem.startswith(("ml_", "mart_"))
    ]


def conectar() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    for p in _parquets():
        con.execute(f"create table {p.stem} as select * from read_parquet('{p.as_posix()}')")
    con.execute("set enable_external_access = false")
    con.execute("set lock_configuration = true")
    return con


def validar(sql: str, tablas: set[str]) -> str:
    try:
        sentencias = [s for s in sqlglot.parse(sql, read="duckdb") if s is not None]
    except sqlglot.errors.ParseError as e:
        raise SQLRechazado(f"SQL inválido: {e}") from e
    if len(sentencias) != 1:
        raise SQLRechazado("Tiene que ser una sola sentencia.")
    q = sentencias[0]
    if not isinstance(q, exp.Query):
        raise SQLRechazado("Solo se permiten consultas SELECT.")
    ctes = {c.alias_or_name for c in q.find_all(exp.CTE)}
    for t in q.find_all(exp.Table):
        if not isinstance(t.this, exp.Identifier) or t.db or t.catalog:
            raise SQLRechazado(f"Fuente no permitida: {t.sql()}")
        if t.name not in tablas and t.name not in ctes:
            raise SQLRechazado(f"Tabla desconocida: {t.name}")
    for f in q.find_all(exp.Func):
        nombre = (f.name if isinstance(f, exp.Anonymous) else f.sql_name()).lower()
        if nombre in FUNCIONES_PROHIBIDAS or nombre.startswith("duckdb_"):
            raise SQLRechazado(f"Función no permitida: {nombre}")
    return f"select * from ({q.sql(dialect='duckdb')}) limit {MAX_ROWS}"


def consultar(con: duckdb.DuckDBPyConnection, sql: str, timeout: float = TIMEOUT_S) -> list[dict]:
    cur = con.cursor()  # un cursor por llamada: la conexión se comparte entre sesiones de Streamlit
    tablas = {r[0] for r in cur.execute("select table_name from information_schema.tables").fetchall()}
    try:
        seguro = validar(sql, tablas)
    except SQLRechazado:
        cur.close()
        raise
    timer = threading.Timer(timeout, cur.interrupt)
    timer.start()
    try:
        rel = cur.execute(seguro)
        cols = [d[0] for d in rel.description]
        return [dict(zip(cols, fila, strict=True)) for fila in rel.fetchall()]
    except duckdb.InterruptException as e:
        raise SQLRechazado(f"La consulta tardó más de {timeout:g} s.") from e
    finally:
        timer.cancel()
        cur.close()


def esquema(con: duckdb.DuckDBPyConnection) -> str:
    """Esquema para el prompt: tipos reales de DuckDB + descripciones de los .yml de dbt."""
    desc: dict[str, dict[str, str]] = {}
    for yml in (ROOT / "dbt" / "models").rglob("_*.yml"):
        for m in (yaml.safe_load(yml.read_text()) or {}).get("models", []):
            cols = {c["name"]: c.get("description", "").strip() for c in m.get("columns", [])}
            desc[m["name"]] = {"": (m.get("description") or "").strip(), **cols}
    filas = con.execute(
        "select table_name, column_name, data_type from information_schema.columns"
        " order by table_name, ordinal_position"
    ).fetchall()
    out: list[str] = [IDS]
    actual = None
    for tabla, col, tipo in filas:
        d = desc.get(tabla, {})
        if tabla != actual:
            actual = tabla
            out.append(f"\n{tabla}" + (f": {' '.join(d[''].split())}" if d.get("") else ""))
        nota = d.get(col, "")
        out.append(f"  {col} {tipo}" + (f" -- {' '.join(nota.split())}" if nota else ""))
    return "\n".join(out).strip()
