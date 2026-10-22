"""Utilidades compartidas por las fuentes de la temporada actual."""

from __future__ import annotations

from ingestion import bq, sofascore, understat


def ensure_tables() -> None:
    """Crea las tablas raw de Understat y SofaScore (aunque todavía estén vacías).

    dbt referencia ambos sources siempre. Si SofaScore nunca se corrió, sus tablas
    existen vacías y los marts de Argentina no tienen filas (no hay xG inventado).
    """
    bq.ensure_tables(understat.TABLE_SPECS)
    bq.ensure_tables(sofascore.TABLE_SPECS)
