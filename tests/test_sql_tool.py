import duckdb
import pytest

from app.sql_tool import MAX_ROWS, SQLRechazado, conectar, consultar, esquema


@pytest.fixture(scope="module")
def con():
    return conectar()


def test_select_normal(con):
    filas = consultar(con, "select player_name from dim_players order by player_id")
    assert len(filas) == MAX_ROWS and "player_name" in filas[0]


def test_respeta_order_by(con):
    q = "select player_name from dim_players order by market_value_eur desc nulls last limit 5"
    assert [r["player_name"] for r in consultar(con, q)] == [r[0] for r in con.execute(q).fetchall()]


def test_cte_y_union(con):
    assert consultar(con, "with a as (select 1 as x) select x from a union all select 2")


@pytest.mark.parametrize(
    "sql",
    [
        "select * from read_csv('/etc/passwd')",
        "select * from '/etc/passwd'",
        "select * from read_parquet('https://example.com/x.parquet')",
        "drop table dim_players",
        "insert into dim_clubs select * from dim_clubs",
        "copy dim_players to '/tmp/x.csv'",
        "attach '/tmp/x.db'",
        "set enable_external_access = true",
        "select 1; drop table dim_players",
        "select * from no_existe",
        "select * from main.dim_players",
        "select getenv('HOME')",
        "select current_setting('home_directory')",
    ],
)
def test_rechaza(con, sql):
    with pytest.raises(SQLRechazado):
        consultar(con, sql)
    assert consultar(con, "select count(*) as n from dim_players")[0]["n"] > 0


def test_acceso_externo_cerrado(con):
    # aunque algo pasara sqlglot, DuckDB no puede leer archivos
    with pytest.raises(duckdb.PermissionException):
        con.execute("select * from read_csv('/etc/passwd')")


def test_timeout(con):
    lenta = "select sum(a.player_id * b.player_id) as s from dim_players a, dim_players b"
    with pytest.raises(SQLRechazado, match="tardó"):
        consultar(con, lenta, timeout=0.5)


def test_esquema_usa_dbt(con):
    e = esquema(con)
    assert "mart_player_scouting:" in e and "million_eur_per_npxg_xa_per_90" in e
