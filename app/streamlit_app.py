"""App pública de Fuchibol: explora los marts exportados a Parquet.

    make export-parquet   # baja marts y ml de BigQuery a data/parquet/
    make app              # http://localhost:8501

No usa credenciales: lee los Parquet con DuckDB. Para publicarla, subí el repo
(con data/parquet) a Streamlit Community Cloud o montá los Parquet en un bucket.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

DATA = Path(__file__).resolve().parents[1] / "data" / "parquet"

st.set_page_config(page_title="Fuchibol", page_icon="⚽", layout="wide")


@st.cache_data(show_spinner=False)
def load(dataset: str, table: str) -> pd.DataFrame:
    path = DATA / dataset / f"{table}.parquet"
    if not path.exists():
        return pd.DataFrame()
    return duckdb.sql(f"select * from read_parquet('{path.as_posix()}')").df()


def radar(labels: list[str], values: list[float], title: str) -> go.Figure:
    pairs = [(label, value) for label, value in zip(labels, values, strict=True) if pd.notna(value)]
    labels = [p[0] for p in pairs]
    values = [float(p[1]) for p in pairs]
    fig = go.Figure(
        go.Scatterpolar(
            r=values + values[:1],
            theta=labels + labels[:1],
            fill="toself",
            line_color="#1f77b4",
        )
    )
    fig.update_layout(
        title=title,
        polar={"radialaxis": {"range": [0, 100], "ticksuffix": "º"}},
        showlegend=False,
        height=420,
        margin={"l": 40, "r": 40, "t": 50, "b": 20},
    )
    return fig


def pitch_layout(fig: go.Figure) -> None:
    line = {"color": "white", "width": 2}
    shapes = [
        {"type": "rect", "x0": 0, "y0": 0, "x1": 120, "y1": 80, "line": line},
        {"type": "line", "x0": 60, "y0": 0, "x1": 60, "y1": 80, "line": line},
        {"type": "circle", "x0": 50, "y0": 30, "x1": 70, "y1": 50, "line": line},
        {"type": "rect", "x0": 0, "y0": 18, "x1": 18, "y1": 62, "line": line},
        {"type": "rect", "x0": 102, "y0": 18, "x1": 120, "y1": 62, "line": line},
        {"type": "rect", "x0": 0, "y0": 30, "x1": 6, "y1": 50, "line": line},
        {"type": "rect", "x0": 114, "y0": 30, "x1": 120, "y1": 50, "line": line},
    ]
    fig.update_layout(
        shapes=shapes,
        plot_bgcolor="#2e7d32",
        paper_bgcolor="#2e7d32",
        xaxis={"range": [-2, 122], "visible": False},
        yaxis={"range": [-2, 82], "visible": False, "scaleanchor": "x"},
        height=520,
        margin={"l": 10, "r": 10, "t": 30, "b": 10},
    )


def main() -> None:
    st.title("⚽ Fuchibol")
    st.caption(
        "Datos: [Transfermarkt](https://github.com/dcaribou/transfermarkt-datasets) (CC0), "
        "[StatsBomb Open Data](https://github.com/statsbomb/open-data), "
        "[Understat](https://understat.com) y [SofaScore](https://www.sofascore.com)."
    )

    if not (DATA / "marts").exists():
        st.error("Falta `data/parquet/`. Corré `make export-parquet` y volvé a abrir la app.")
        st.stop()

    tab_players, tab_value, tab_transfers, tab_shots = st.tabs(
        ["Jugadores", "Subvaluados", "Fichajes", "Mapa de tiros"]
    )

    with tab_players:
        source = st.radio("Fuente", ["Temporada actual", "StatsBomb"], horizontal=True)
        if source == "Temporada actual":
            df = load("marts", "mart_current_player_percentiles")
            if df.empty:
                st.info("No hay percentiles de la temporada actual.")
            else:
                league = st.selectbox("Liga", sorted(df["league_code"].unique()))
                part = df[df["league_code"] == league].copy()
                part["label"] = (
                    part["player_name"]
                    + " · "
                    + part["team_name"]
                    + " · "
                    + part["minutes"].round().astype(int).astype(str)
                    + "'"
                )
                choice = st.selectbox("Jugador", sorted(part["label"]))
                row = part[part["label"] == choice].iloc[0]
                left, right = st.columns([3, 2])
                with left:
                    fig = radar(
                        ["xG", "xA", "npxG", "Tiros", "Pases clave"],
                        [
                            row["xg_pct"],
                            row["xa_pct"],
                            row["npxg_pct"],
                            row["shots_pct"],
                            row["key_passes_pct"],
                        ],
                        f"{row['player_name']} · {row['position_group']} · {row['xg_source']}",
                    )
                    st.plotly_chart(fig, width="stretch")
                with right:
                    st.metric("Minutos", int(row["minutes"]))
                    st.dataframe(
                        part[part["label"] == choice][
                            ["xg_per_90", "xa_per_90", "npxg_per_90", "shots_per_90", "key_passes_per_90"]
                        ].T.rename(columns={row.name: "cada 90"}),
                        width="stretch",
                    )
        else:
            df = load("marts", "mart_sb_player_percentiles")
            if df.empty:
                st.info("No hay percentiles de StatsBomb.")
            else:
                df["comp"] = df["competition_name"] + " " + df["season_name"]
                comp = st.selectbox("Competición", sorted(df["comp"].drop_duplicates()))
                part = df[df["comp"] == comp].copy()
                part["label"] = (
                    part["player_name"]
                    + " · "
                    + part["teams"]
                    + " · "
                    + part["minutes_played"].round().astype(int).astype(str)
                    + "'"
                )
                choice = st.selectbox("Jugador", sorted(part["label"]))
                row = part[part["label"] == choice].iloc[0]
                metrics = [
                    ("npxG", "npxg_pct"),
                    ("xA", "xa_pct"),
                    ("xT", "xt_added_pct"),
                    ("Tiros", "shots_pct"),
                    ("Pases clave", "key_passes_pct"),
                    ("Pases progresivos", "progressive_passes_pct"),
                    ("Conducciones", "progressive_carries_pct"),
                    ("Regates", "dribbles_completed_pct"),
                    ("Presiones", "pressures_pct"),
                    ("PAdj T+I", "padj_tackles_interceptions_pct"),
                ]
                fig = radar(
                    [label for label, _ in metrics],
                    [row[col] for _, col in metrics],
                    f"{row['player_name']} · {row['position_group']} · {row['teams']}",
                )
                st.plotly_chart(fig, width="stretch")

    with tab_value:
        df = load("ml", "mart_undervalued_players")
        if df.empty:
            st.info("Corré `make dbt-train` para generar las predicciones.")
        else:
            eval_df = load("ml", "ml_model_evaluation")
            if not eval_df.empty:
                ev = eval_df.iloc[0]
                c1, c2, c3 = st.columns(3)
                c1.metric("R²", f"{ev['r2_score']:.3f}")
                c2.metric("MAE (log)", f"{ev['mean_absolute_error']:.3f}")
                c3.metric("Error mediano", f"{ev['median_absolute_error']:.3f}")

            c1, c2, c3 = st.columns(3)
            leagues = c1.multiselect("Liga", sorted(df["main_league_name"].dropna().unique()))
            labels = c2.multiselect(
                "Etiqueta", sorted(df["valuation_label"].unique()), default=["Subvaluado"]
            )
            top_n = c3.slider("Top", 10, 200, 50, step=10)

            view = df.copy()
            if leagues:
                view = view[view["main_league_name"].isin(leagues)]
            if labels:
                view = view[view["valuation_label"].isin(labels)]
            view = view.nsmallest(top_n, "undervalued_rank")

            view["real_m"] = view["actual_value_eur"] / 1e6
            view["predicho_m"] = view["predicted_value_eur"] / 1e6
            fig = px.scatter(
                view,
                x="real_m",
                y="predicho_m",
                color="valuation_label",
                hover_name="player_name",
                hover_data=["main_club_name", "age", "predicted_to_actual_ratio"],
                log_x=True,
                log_y=True,
                labels={"real_m": "Valor real (M€)", "predicho_m": "Valor predicho (M€)"},
            )
            fig.add_shape(
                type="line",
                x0=0.1,
                y0=0.1,
                x1=1000,
                y1=1000,
                line={"dash": "dash", "color": "gray"},
            )
            fig.update_layout(height=480)
            st.plotly_chart(fig, width="stretch")
            st.dataframe(
                view[
                    [
                        "undervalued_rank",
                        "player_name",
                        "main_club_name",
                        "age",
                        "actual_value_eur",
                        "predicted_value_eur",
                        "predicted_to_actual_ratio",
                        "valuation_label",
                    ]
                ],
                width="stretch",
                hide_index=True,
            )

    with tab_transfers:
        df = load("marts", "mart_transfer_roi")
        if df.empty:
            st.info("No hay datos de fichajes.")
        else:
            view = df[
                (df["is_paid_transfer"]) & (df["value_1y_after_eur"] > 0) & (df["transfer_fee_eur"] > 0)
            ].copy()
            view["costo_m"] = view["transfer_fee_eur"] / 1e6
            view["valor_m"] = view["value_1y_after_eur"] / 1e6
            fig = px.scatter(
                view,
                x="costo_m",
                y="valor_m",
                color="verdict",
                hover_name="player_name",
                hover_data=["from_club_name", "to_club_name", "transfer_season"],
                log_x=True,
                log_y=True,
                labels={"costo_m": "Costo (M€)", "valor_m": "Valor un año después (M€)"},
            )
            fig.add_shape(
                type="line", x0=0.1, y0=0.1, x1=1000, y1=1000, line={"dash": "dash", "color": "gray"}
            )
            fig.update_layout(height=480)
            st.plotly_chart(fig, width="stretch")

            balance = load("marts", "mart_club_transfer_balance")
            if not balance.empty:
                top = balance.reindex(balance["net_balance_eur"].abs().nlargest(15).index)
                fig2 = px.bar(
                    top,
                    x="club_name",
                    y="net_balance_eur",
                    color="net_balance_eur",
                    color_continuous_scale="RdYlGn",
                    labels={"club_name": "", "net_balance_eur": "Balance neto (€)"},
                )
                fig2.update_layout(height=380, coloraxis_showscale=False)
                st.plotly_chart(fig2, width="stretch")

    with tab_shots:
        df = load("marts", "fct_sb_shots")
        if df.empty:
            st.info("No hay tiros de StatsBomb.")
        else:
            c1, c2, c3 = st.columns(3)
            comps = c1.multiselect("Competición", sorted(df["competition_name"].unique()))
            view = df[df["competition_name"].isin(comps)] if comps else df
            teams = c2.multiselect("Equipo", sorted(view["team_name"].unique()))
            if teams:
                view = view[view["team_name"].isin(teams)]
            players = c3.multiselect("Jugador", sorted(view["player_name"].unique()))
            if players:
                view = view[view["player_name"].isin(players)]

            fig = px.scatter(
                view,
                x="x",
                y="y",
                size="xg",
                color="is_goal",
                color_discrete_map={True: "#d62728", False: "#90a4ae"},
                hover_name="player_name",
                hover_data=["team_name", "xg", "outcome", "shot_type", "minute"],
                labels={"x": "", "y": "", "is_goal": "Gol"},
            )
            pitch_layout(fig)
            st.plotly_chart(fig, width="stretch")
            st.caption(f"{len(view):,} tiros · tamaño = xG · rojo = gol")


if __name__ == "__main__":
    main()
