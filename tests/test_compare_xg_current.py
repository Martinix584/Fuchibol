from scripts.compare_xg_current import compare, map_teams, match_players, norm


def row(name, team, xg, key="x"):
    return {"player_name": name, "team_name": team, "xg": xg, "player_key": key}


def test_norm_strips_accents_and_symbols():
    assert norm("Ángel Di María") == "angel di maria"
    assert norm("  Núñez, Darwin ") == "nunez darwin"


def test_map_teams_exact_contains_and_fuzzy():
    mapping = map_teams(
        {"Manchester City", "Paris Saint Germain", "Bayern Munich"},
        {"Man City", "Paris Saint-Germain", "Bayern München"},
    )
    assert mapping["Manchester City"] == "Man City"
    assert mapping["Paris Saint Germain"] == "Paris Saint-Germain"
    assert mapping["Bayern Munich"] == "Bayern München"


def test_match_players_discards_ambiguous_names():
    us = [row("Lionel Messi", "Inter Miami", 10.0, "u1")]
    ss = [
        row("Lionel Messi", "Inter Miami", 9.5, "s1"),
        row("Lionel Messi", "Inter Miami", 9.0, "s2"),
    ]
    assert match_players(us, ss, {"Inter Miami": "Inter Miami"}) == []


def test_match_players_exact_and_subset():
    us = [row("Lionel Messi", "Inter Miami", 10.0, "u1"), row("Rodrigo De Paul", "Inter Miami", 3.0, "u2")]
    ss = [
        row("Lionel Messi", "Inter Miami", 9.5, "s1"),
        row("Rodrigo Javier De Paul", "Inter Miami", 2.8, "s2"),
    ]
    pairs = match_players(us, ss, {"Inter Miami": "Inter Miami"})
    assert len(pairs) == 2
    assert {u["player_key"] for u, _ in pairs} == {"u1", "u2"}


def test_compare_metrics():
    pairs = [
        (row("A", "X", 10.0), row("A", "X", 9.0)),
        (row("B", "X", 2.0), row("B", "X", 2.5)),
    ]
    result = compare(pairs, us_total=12.0, ss_total=11.5)
    assert result["jugadores"] == 2
    assert result["dif_pct"] == -4.2
    assert result["dif_media_abs"] == 0.75
    assert result["pct_mas_de_0_5"] == 50.0
    assert result["cobertura_xg_us"] == 100.0
