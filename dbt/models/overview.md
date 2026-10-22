{% docs __overview__ %}
# Fuchibol

Pipeline de datos de fútbol con cuatro fuentes:

- **Transfermarkt** (via transfermarkt-datasets, CC0): jugadores, valores de mercado,
  transferencias y apariciones. Responde *¿valió lo que se pagó?*, *Argentina fábrica de
  jugadores* y alimenta el modelo de valor de mercado de BigQuery ML.
- **StatsBomb Open Data**: datos de eventos del mismo tipo que Opta (cada pase, tiro y
  presión, con xG). Da xG, xA, acciones progresivas, mapas de tiros y tablas por xPts.
- **Understat**: xG, xA, npxG, xGChain y xGBuildup de la temporada actual de las 5
  grandes ligas. Corre a diario en Airflow.
- **SofaScore**: xG/xA de la Liga Profesional Argentina y respaldo manual de las 5
  grandes. Es opcional, local y no corre en Airflow.

StatsBomb y Transfermarkt se unen en `int_player_id_map` (resolución de identidades por
nombre y nacionalidad) y en `mart_player_scouting`. Understat y SofaScore conviven en
`mart_current_player_season`, sin mezclar fuentes: cada fila lleva `xg_source`.

Capas: `staging` (tipos y limpieza) → `intermediate` (lógica de negocio) → `marts`
(lo que consume Power BI) → `ml` (BigQuery ML). Los modelos de la temporada actual
llevan el tag `current` y los construye el DAG diario `fuchibol_current_season`.
{% enddocs %}
