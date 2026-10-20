{% docs __overview__ %}
# Fuchibol

Pipeline de datos de fútbol con dos fuentes públicas:

- **Transfermarkt** (via transfermarkt-datasets, CC0): jugadores, valores de mercado,
  transferencias y apariciones. Responde *¿valió lo que se pagó?*, *Argentina fábrica de
  jugadores* y alimenta el modelo de valor de mercado de BigQuery ML.
- **StatsBomb Open Data**: datos de eventos del mismo tipo que Opta (cada pase, tiro y
  presión, con xG). Da xG, xA, acciones progresivas, mapas de tiros y tablas por xPts.

Las dos se unen en `int_player_id_map` (resolución de identidades por nombre y
nacionalidad) y en `mart_player_scouting`.

Capas: `staging` (tipos y limpieza) → `intermediate` (lógica de negocio) → `marts`
(lo que consume Power BI) → `ml` (BigQuery ML).
{% enddocs %}
