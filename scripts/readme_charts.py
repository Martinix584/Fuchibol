"""Genera los gráficos del README a partir de la base DuckDB del smoke test (datos reales).

scripts/smoke.sh --database /tmp/fuchibol.duckdb      # Mundial 2022 completo
python scripts/readme_charts.py /tmp/fuchibol.duckdb
"""

import sys
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Arc, Rectangle  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "docs" / "img"
SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
XG, GOAL = "#2a78d6", "#eb6834"  # paleta categórica validada (slots 1 y 2)

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "text.color": INK,
        "axes.labelcolor": INK_2,
        "xtick.color": INK_2,
        "ytick.color": INK_2,
        "axes.edgecolor": GRID,
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
    }
)


def half_pitch(ax):
    """Medio campo de StatsBomb (120 x 80), arco arriba."""
    line = {"color": "#bdbcb6", "lw": 1.2, "fill": False}
    ax.add_patch(Rectangle((0, 60), 80, 60, **line))
    ax.add_patch(Rectangle((18, 102), 44, 18, **line))
    ax.add_patch(Rectangle((30, 114), 20, 6, **line))
    ax.add_patch(Arc((40, 108), 20, 20, theta1=217, theta2=323, color="#bdbcb6", lw=1.2))
    ax.add_patch(Arc((40, 60), 20, 20, theta1=0, theta2=180, color="#bdbcb6", lw=1.2))
    ax.plot([36, 44], [120, 120], color=INK_2, lw=3, solid_capstyle="round")
    ax.set_xlim(-1, 81)
    ax.set_ylim(66, 121.5)
    ax.set_aspect("equal")
    ax.axis("off")


def shot_map(con, player: str, path: Path):
    shots = con.execute(
        """select x, y, xg, is_goal, is_penalty from marts.fct_sb_shots s
           join staging.stg_sb_lineups l using (match_id, player_id)
           where l.player_display_name = ?""",
        [player],
    ).fetchall()
    totals = con.execute(
        """select goals, penalty_goals, round(xg, 1), round(npxg, 1), shots, round(minutes_played)
           from marts.mart_sb_player_seasons where player_display_name = ?""",
        [player],
    ).fetchone()
    fig, ax = plt.subplots(figsize=(6.4, 5.6))
    half_pitch(ax)
    for x, y, xg, is_goal, _ in shots:
        size = 40 + xg * 900
        # en el plano, x de StatsBomb (hacia el arco) es el eje vertical
        if is_goal:
            ax.scatter(y, x, s=size, color=GOAL, edgecolor=SURFACE, linewidth=2, zorder=3)
        else:
            ax.scatter(y, x, s=size, facecolor="none", edgecolor=XG, linewidth=2, zorder=2)
    goals, pens, xg, npxg, n_shots, minutes = totals
    fig.suptitle(f"{player}: tiros en el Mundial 2022", x=0.06, ha="left", fontsize=13, fontweight="bold")
    fig.text(
        0.06,
        0.885,
        f"{goals} goles ({pens} de penal) · {xg} xG ({npxg} sin penales) · {n_shots} tiros · "
        f"{minutes:.0f} minutos",
        color=INK_2,
        fontsize=9.5,
    )
    legend = [
        Line2D(
            [], [], marker="o", ls="", markersize=10, markerfacecolor=GOAL, markeredgecolor=GOAL, label="Gol"
        ),
        Line2D(
            [],
            [],
            marker="o",
            ls="",
            markersize=10,
            markerfacecolor="none",
            markeredgecolor=XG,
            lw=2,
            label="Sin gol",
        ),
        Line2D(
            [],
            [],
            marker="o",
            ls="",
            markersize=5,
            markerfacecolor="none",
            markeredgecolor=INK_2,
            label="Tamaño = xG",
        ),
    ]
    ax.legend(handles=legend, loc="upper center", ncol=3, frameon=False, bbox_to_anchor=(0.5, 0.0))
    fig.text(0.06, -0.02, "Datos: StatsBomb Open Data · Fuchibol", color=INK_2, fontsize=8)
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def points_vs_xpts(con, path: Path):
    rows = con.execute(
        """select team_name, points, xpts, matches from marts.mart_sb_team_seasons
           where matches >= 5 order by xpts"""
    ).fetchall()
    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    for i, (_team, pts, xpts, _) in enumerate(rows):
        ax.plot([xpts, pts], [i, i], color=GRID, lw=2, zorder=1, solid_capstyle="round")
        ax.scatter(xpts, i, s=70, color=XG, edgecolor=SURFACE, linewidth=2, zorder=3)
        ax.scatter(pts, i, s=70, color=GOAL, edgecolor=SURFACE, linewidth=2, zorder=3)
        diff = pts - xpts
        ax.text(max(pts, xpts) + 0.4, i, f"{diff:+.1f}", va="center", fontsize=9, color=INK_2)
    ax.set_yticks(range(len(rows)), [r[0] for r in rows])
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.set_xlabel("Puntos en el torneo (victoria = 3, empate = 1; alargue incluido, sin penales)")
    ax.set_xlim(left=0)
    fig.suptitle(
        "Mundial 2022: puntos reales vs. puntos esperados por xG",
        x=0.02,
        ha="left",
        fontsize=13,
        fontweight="bold",
    )
    fig.text(
        0.02,
        0.905,
        "Equipos con 5 o más partidos. El número es puntos menos xPts: positivo = sacó más de lo que generó.",
        color=INK_2,
        fontsize=9,
    )
    legend = [
        Line2D([], [], marker="o", ls="", markersize=8, color=GOAL, label="Puntos"),
        Line2D([], [], marker="o", ls="", markersize=8, color=XG, label="xPts"),
    ]
    ax.legend(handles=legend, loc="upper left", frameon=False)
    fig.text(
        0.02,
        -0.04,
        "Datos: StatsBomb Open Data · xPts con Poisson sobre el xG de cada partido",
        color=INK_2,
        fontsize=8,
    )
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def main():
    con = duckdb.connect(sys.argv[1], read_only=True)
    OUT.mkdir(parents=True, exist_ok=True)
    shot_map(con, "Lionel Messi", OUT / "shotmap_messi_2022.png")
    points_vs_xpts(con, OUT / "points_vs_xpts_2022.png")
    print(f"Gráficos en {OUT}")


if __name__ == "__main__":
    main()
