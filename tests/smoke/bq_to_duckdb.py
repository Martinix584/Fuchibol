"""Traducción BigQuery -> DuckDB para el smoke test.

No pretende ser un emulador de BigQuery: alcanza para correr el SQL compilado de este
proyecto y detectar errores de lógica (joins, granos, filtros) sin una cuenta de GCP.
"""

from __future__ import annotations

import re

import sqlglot

TYPE_MAP = {
    "STRING": "VARCHAR",
    "INTEGER": "BIGINT",
    "INT64": "BIGINT",
    "FLOAT": "DOUBLE",
    "FLOAT64": "DOUBLE",
    "BOOLEAN": "BOOLEAN",
    "BOOL": "BOOLEAN",
    "TIMESTAMP": "TIMESTAMP",
    "DATE": "DATE",
}


def duck_type(field: dict) -> str:
    if field["type"] == "RECORD":
        inner = ", ".join(f'"{f["name"]}" {duck_type(f)}' for f in field["fields"])
        base = f"STRUCT({inner})"
    else:
        base = TYPE_MAP[field["type"]]
    return f"{base}[]" if field.get("mode") == "REPEATED" else base


def prune(value, fields: list[dict]):
    """Deja solo los campos del esquema, como hace BigQuery con ignore_unknown_values."""
    if value is None:
        return None
    out = {}
    for f in fields:
        v = value.get(f["name"])
        if f["type"] == "RECORD" and v is not None:
            v = [prune(x, f["fields"]) for x in v] if f.get("mode") == "REPEATED" else prune(v, f["fields"])
        if f.get("mode") == "REPEATED" and v is None:
            v = []
        out[f["name"]] = v
    return out


def to_duckdb(sql: str, project: str) -> str:
    # `proyecto`.`dataset`.`tabla` -> dataset.tabla
    sql = re.sub(rf"`{re.escape(project)}`\.`(\w+)`\.`(\w+)`", r"\1.\2", sql)
    # NORMALIZE(x, NFD) no existe en DuckDB: strip_accents ya saca los acentos
    sql = re.sub(r"normalize\((.+?), NFD\)", r"strip_accents(\1)", sql)
    # sqlglot traduce bien arr[offset(0)] pero no arr[offset(variable)] (DuckDB indexa desde 1)
    sql = re.sub(r"\[(?:safe_)?offset\(([A-Za-z_][\w.]*)\)\]", r"[ordinal(\1 + 1)]", sql)
    statements = sqlglot.transpile(sql, read="bigquery", write="duckdb")
    return ";\n".join(statements)
