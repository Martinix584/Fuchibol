from ingestion.wiki_corpus import MAX_CHARS, fragmentos

EXTRACTO = """Lionel Messi es un futbolista argentino que juega como delantero en el Inter Miami de la MLS.

== Trayectoria ==
=== Barcelona ===
""" + ("Debutó en el primer equipo del Barcelona en 2004 y ganó todo lo que había para ganar. " * 40) + """
=== Paris Saint-Germain ===
Llegó al PSG en 2021 tras la salida del Barcelona por problemas económicos del club catalán.

== Referencias ==
Esto no tiene que aparecer en ningún fragmento porque son solo referencias bibliográficas.
"""


def test_fragmentos():
    fr = fragmentos(EXTRACTO)
    secciones = [s for s, _ in fr]
    assert secciones[0] == "Introducción"
    assert "Trayectoria > Barcelona" in secciones and "Trayectoria > Paris Saint-Germain" in secciones
    assert not any("Referencias" in s or "bibliográficas" in t for s, t in fr)
    assert all(len(t) <= MAX_CHARS + 200 for _, t in fr)
