import datetime as dt

import pytest

from app import agente


def test_cupo_diario(monkeypatch):
    monkeypatch.setattr(agente, "MAX_PREGUNTAS_DIA", 2)
    monkeypatch.setattr(agente, "_cupo", {"dia": None, "usadas": 0})
    hoy, manana = dt.date(2026, 11, 3), dt.date(2026, 11, 4)
    assert agente.tomar_cupo(hoy) == 1
    assert agente.tomar_cupo(hoy) == 0
    with pytest.raises(agente.SinCupo):
        agente.tomar_cupo(hoy)
    assert agente.tomar_cupo(manana) == 1  # al otro día arranca de nuevo


def test_demasiados_pasos_no_rompe(monkeypatch):
    class Falla:
        def invoke(self, *a, **k):
            raise agente.GraphRecursionError("límite")

    monkeypatch.setattr(agente, "agente", lambda: Falla())
    monkeypatch.setattr(agente, "_cupo", {"dia": None, "usadas": 0})
    assert "demasiados pasos" in agente.preguntar([{"role": "user", "content": "x"}])[-1].text


def test_mem0_caido_no_rompe(monkeypatch):
    class Caido:
        def search(self, *a, **k):
            raise ConnectionError("mem0 caído")

        def add(self, *a, **k):
            raise ConnectionError("mem0 caído")

    monkeypatch.setattr(agente, "_mem0", lambda: Caido())
    assert agente.recordar("u", "x") == []
    agente.guardar("u", "x", "y")  # no levanta
