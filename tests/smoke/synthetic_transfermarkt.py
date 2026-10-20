"""Datos sintéticos con las columnas de transfermarkt-datasets.

Los jugadores llevan nombres y nacionalidades reales de StatsBomb (los de más minutos),
más algunos casos trampa, para probar el cruce de identidades de int_player_id_map.
"""

from __future__ import annotations

import random
from datetime import date, timedelta


def build(con, sb_players: list[dict], seed: int = 7) -> dict:
    """sb_players: [{name, display_name, country}] de StatsBomb. Devuelve los casos esperados del cruce."""
    rnd = random.Random(seed)
    raw = "raw_transfermarkt"

    competitions = [
        (
            "ARG1",
            "primera-division",
            "primera-division",
            "first_tier",
            "domestic_league",
            "Argentina",
            "amerika",
        ),
        ("GB1", "premier-league", "premier-league", "first_tier", "domestic_league", "England", "europa"),
        (
            "CL",
            "uefa-champions-league",
            "uefa-champions-league",
            "uefa_champions_league",
            "international_cup",
            None,
            "europa",
        ),
    ]
    con.execute(f"""create table {raw}.competitions(competition_id varchar, competition_code varchar,
        name varchar, sub_type varchar, type varchar, country_name varchar, confederation varchar)""")
    con.executemany(f"insert into {raw}.competitions values (?,?,?,?,?,?,?)", competitions)

    clubs = [
        (1, "River Plate", "ARG1"),
        (2, "Boca Juniors", "ARG1"),
        (3, "Racing Club", "ARG1"),
        (10, "Arsenal", "GB1"),
        (11, "Chelsea", "GB1"),
        (12, "Brighton", "GB1"),
    ]
    con.execute(f"""create table {raw}.clubs(club_id bigint, name varchar, domestic_competition_id varchar,
        squad_size bigint, average_age double, foreigners_percentage double, national_team_players bigint,
        stadium_name varchar, last_season bigint)""")
    con.executemany(f"insert into {raw}.clubs values (?,?,?,25,26.1,40.0,5,'x',2023)", clubs)

    # --- jugadores: 60 genéricos + los reales de StatsBomb + casos trampa
    players, expected = [], {}
    pid = 0

    def add(name, country, club):
        nonlocal pid
        pid += 1
        pos = rnd.choice(["Attack", "Midfield", "Defender", "Goalkeeper"])
        players.append(
            (
                pid,
                name,
                club,
                country,
                country,
                date(1995 + pid % 8, 1 + pid % 12, 1).isoformat(),
                pos,
                pos + "-sub",
                rnd.choice(["right", "left"]),
                170 + pid % 25,
                "2027-06-30",
                "Agente",
                pid % 30,
                pid % 7,
                float(rnd.randint(1, 80) * 1e6),
                90e6,
                2023,
                f"Club {club}",
            )
        )
        return pid

    for i in range(60):
        add(f"Jugador {i + 1}", "Argentina" if i % 2 else "England", clubs[i % 6][0])
    for p in sb_players:
        expected[p["display_name"]] = add(p["display_name"], p["country"], clubs[pid % 6][0])
    # Las trampas usan jugadores con nacionalidad (en datos viejos StatsBomb no la trae, y sin
    # nacionalidad un homónimo es ambiguo de verdad)
    with_country = [p for p in sb_players if p["country"]]
    # trampa 1: homónimo con otra nacionalidad (no debe romper el cruce por nacionalidad)
    if with_country:
        add(with_country[0]["display_name"], "Narnia", 1)
    # trampa 2: dos jugadores iguales de la misma nacionalidad -> ambiguo, no se cruza
    if len(with_country) > 1:
        dup = with_country[1]
        add(dup["display_name"], dup["country"], 2)
        expected[dup["display_name"]] = None

    con.execute(f"""create table {raw}.players(player_id bigint, name varchar, current_club_id double,
        country_of_citizenship varchar, country_of_birth varchar, date_of_birth varchar, position varchar,
        sub_position varchar, foot varchar, height_in_cm double, contract_expiration_date varchar,
        agent_name varchar, international_caps bigint, international_goals bigint, market_value_in_eur double,
        highest_market_value_in_eur double, last_season bigint, current_club_name varchar,
        image_url varchar default 'u')""")
    con.executemany(
        f"""insert into {raw}.players (player_id, name, current_club_id, country_of_citizenship,
        country_of_birth, date_of_birth, position, sub_position, foot, height_in_cm, contract_expiration_date,
        agent_name, international_caps, international_goals, market_value_in_eur, highest_market_value_in_eur,
        last_season, current_club_name) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        players,
    )
    n_players = pid

    def home_club(p):
        return clubs[(p - 1) % 6][0]

    # --- transferencias: argentinos de clubes argentinos que se van a Inglaterra en 2021
    transfers, moves = [], {}
    for p in range(1, n_players + 1):
        from_club = home_club(p)
        if from_club < 10 and p % 2 == 0:
            to = rnd.choice([10, 11, 12])
            moves[p] = (date(2021, 7, 15), to)
            transfers.append(
                (
                    p,
                    "2021-07-15",
                    "21/22",
                    from_club,
                    to,
                    f"C{from_club}",
                    f"C{to}",
                    float(rnd.randint(1, 40) * 1e6),
                    float(rnd.randint(1, 30) * 1e6),
                )
            )
        if p % 11 == 0:
            transfers.append(
                (p, "2022-01-10", "21/22", from_club, -1, f"C{from_club}", "Without Club", 0.0, None)
            )
    transfers.append((3, "2099-01-01", "98/99", 1, 2, "a", "b", 1e6, 1e6))  # futuro: se filtra
    con.execute(f"""create table {raw}.transfers(player_id bigint, transfer_date varchar,
        transfer_season varchar, from_club_id bigint, to_club_id bigint, from_club_name varchar,
        to_club_name varchar,
        transfer_fee double, market_value_in_eur double)""")
    con.executemany(f"insert into {raw}.transfers values (?,?,?,?,?,?,?,?,?)", transfers)

    def club_of(p, d):
        return moves[p][1] if p in moves and d >= moves[p][0] else home_club(p)

    # --- partidos semanales 2020-2023 y apariciones
    games, apps, gid, d = [], [], 0, date(2020, 8, 1)
    while d < date(2023, 6, 1):
        season = d.year if d.month >= 7 else d.year - 1
        for league, ids in [("ARG1", [1, 2, 3]), ("GB1", [10, 11, 12])]:
            h, a = rnd.sample(ids, 2)
            gid += 1
            games.append(
                (
                    gid,
                    league,
                    season,
                    d,
                    h,
                    a,
                    rnd.randint(0, 3),
                    rnd.randint(0, 3),
                    30000,
                    "domestic_league",
                    f"C{h}",
                    f"C{a}",
                )
            )
            for p in range(1, n_players + 1):
                c = club_of(p, d)
                if c in (h, a) and rnd.random() < 0.8:
                    apps.append(
                        (
                            f"{gid}_{p}",
                            gid,
                            p,
                            c,
                            d,
                            league,
                            rnd.choice([90, 90, 60, 20]),
                            int(rnd.random() < 0.2),
                            int(rnd.random() < 0.15),
                            int(rnd.random() < 0.1),
                            0,
                        )
                    )
        d += timedelta(days=7)
    con.execute(f"""create table {raw}.games(game_id bigint, competition_id varchar, season bigint, date date,
        home_club_id bigint, away_club_id bigint, home_club_goals bigint, away_club_goals bigint,
        attendance bigint, competition_type varchar, home_club_name varchar, away_club_name varchar)""")
    con.executemany(f"insert into {raw}.games values (?,?,?,?,?,?,?,?,?,?,?,?)", games)
    con.execute(f"""create table {raw}.appearances(appearance_id varchar, game_id bigint, player_id bigint,
        player_club_id bigint, date date, competition_id varchar, minutes_played bigint, goals bigint,
        assists bigint, yellow_cards bigint, red_cards bigint)""")
    con.executemany(f"insert into {raw}.appearances values (?,?,?,?,?,?,?,?,?,?,?)", apps)

    # --- valuaciones semestrales 2019-2023
    vals = []
    for p in range(1, n_players + 1):
        v = rnd.randint(1, 20) * 1e6
        for y in range(2019, 2024):
            for m in (1, 6, 12):
                v = max(1e5, v * rnd.uniform(0.8, 1.4))
                vals.append((p, date(y, m, 15), float(round(v)), club_of(p, date(y, m, 15)), None))
    con.execute(f"""create table {raw}.player_valuations(player_id bigint, date date,
        market_value_in_eur double, current_club_id bigint, player_club_domestic_competition_id varchar)""")
    con.executemany(f"insert into {raw}.player_valuations values (?,?,?,?,?)", vals)
    return expected
