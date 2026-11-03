from evals.correr import numeros, valor_ok


def test_numeros_castellano():
    assert numeros("vale €100.000.000 y tuvo 1,98 npxG (o 1.98), 20 tiros") == [100000000, 1.98, 1.98, 20]


def test_valor_ok():
    assert valor_ok(1.97, "Argentina generó 1,98 npxG", [])
    assert not valor_ok(1.97, "Argentina generó 2,30 npxG", [])
    assert valor_ok("Spain", "Fue España, con 13 de xG", ["España"])
    assert valor_ok(100000000, "vale 100 millones de euros", [])
    assert valor_ok("Julián Alvarez", "JULIAN ALVAREZ vale", [])
