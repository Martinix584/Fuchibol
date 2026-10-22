import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from compare_xg import compare, map_teams, match_players, norm  # noqa: E402


def sb(name, nickname, team, xg, team_id=1):
    return {
        "name": name,
        "nickname": nickname,
        "team": team,
        "team_id": team_id,
        "xg": xg,
        "npxg": xg,
        "shots": 1,
    }


def test_norm_strips_accents_and_signs():
    assert norm("Kylian Mbappé-Lottin") == "kylian mbappe lottin"


def test_map_teams_contained_words_then_closest_name():
    sb_teams = {
        "Paris Saint-Germain": 1,
        "Stade Malherbe Caen": 2,
        "Marseille": 3,
        "Olympique de Marseille": 3,
    }
    mapping = map_teams(sb_teams, {"Paris Saint Germain", "Caen", "Marseille", "Nowhere FC"})
    assert mapping == {"Paris Saint Germain": 1, "Caen": 2, "Marseille": 3}


def test_match_players_by_nickname_tokens_and_skips_ambiguous():
    players = {
        1: sb("Lionel Andrés Messi Cuccittini", "Lionel Messi", "Barcelona", 20.0),
        2: sb("Sergio Busquets i Burgos", None, "Barcelona", 1.0),
        3: sb("Luis Alberto Suárez Díaz", None, "Barcelona", 25.0),
        4: sb("Luis Alberto Romero Alconchel", None, "Barcelona", 2.0),
    }
    understat = [
        {"player_name": "Lionel Messi", "team_title": "Barcelona", "xG": "21"},  # apodo
        {"player_name": "Sergio Busquets", "team_title": "Barcelona", "xG": "1"},  # palabras
        {"player_name": "Luis Alberto", "team_title": "Barcelona", "xG": "2"},  # dos candidatos
    ]
    pairs = match_players(players, understat, {"Barcelona": 1})
    assert [(p["name"], u["player_name"]) for p, u in pairs] == [
        ("Lionel Andrés Messi Cuccittini", "Lionel Messi"),
        ("Sergio Busquets i Burgos", "Sergio Busquets"),
    ]


def test_compare_metrics():
    pairs = [
        (sb("A", None, "T", 10.0), {"xG": "11"}),
        (sb("B", None, "T", 2.0), {"xG": "2.2"}),
        (sb("C", None, "T", 0.0), {"xG": "0.1"}),
    ]
    result = compare(pairs, sb_total_xg=16.0)
    assert result["jugadores"] == 3
    assert result["dif_pct"] == 10.8  # (13.3 - 12) / 12
    assert result["pct_mas_de_0_5"] == 33.3
    assert result["cobertura_xg_sb"] == 75.0
