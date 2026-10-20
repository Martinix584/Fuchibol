# Reporte de Power BI

Guardá el reporte acá como `fuchibol.pbix` (o en formato proyecto `.pbip`, que es texto y se versiona mejor) y
las capturas en `powerbi/img/`. Tema: **Vista → Temas → Buscar temas → `fuchibol-theme.json`** (es la misma
paleta, validada para daltonismo, que los gráficos del README).

## Conexión

1. Power BI Desktop → **Obtener datos** → **Google BigQuery** → iniciar sesión con tu cuenta de GCP.
2. Datasets: `marts`, `ml` y `ops`.
3. Modo **Importar**: el volumen es chico y así no se pagan consultas cada vez que alguien abre el reporte.

## Modelo

| Tabla | Grano | Relación |
|---|---|---|
| `marts.dim_players` | jugador (Transfermarkt) | `player_id` 1 → * en las tablas de Transfermarkt; 1 → * `mart_player_scouting[tm_player_id]` |
| `marts.dim_clubs` | club | `club_id` 1 → * `mart_transfer_roi[to_club_id]` |
| `marts.mart_player_seasons` | jugador × temporada | |
| `marts.mart_transfer_roi` | fichaje pago | |
| `marts.mart_argentina_exports` | venta de la liga argentina al exterior | |
| `marts.mart_club_transfer_balance` | club | |
| `ml.mart_undervalued_players` | jugador (última temporada) | |
| `marts.mart_sb_player_seasons` | jugador × competición StatsBomb | |
| `marts.fct_sb_shots` | tiro | `player_id` → `mart_sb_player_seasons` (con competición) |
| `marts.fct_sb_team_matches`, `marts.mart_sb_team_seasons` | equipo × partido / torneo | |
| `marts.mart_player_scouting` | jugador × competición (cruzado) | `tm_player_id` → `dim_players` |
| `ops.pipeline_runs`, `ops.dbt_results` | corrida | |

Para la competición, armá una tabla `Competicion` con `competition_id`, `season_id` y una clave
`competition_id & "-" & season_id` en cada tabla de StatsBomb, y usala como slicer común.

## Páginas

1. **Ficha del jugador** (Transfermarkt): buscador; tarjetas de partidos, goles, asistencias, goles por partido y
   cada 90; línea de valor de mercado por temporada; tabla de temporadas.
2. **¿Valió lo que se pagó?**: dispersión monto (x) vs. valor un año después (y) por `verdict`; ranking de clubes
   por `hit_rate`; filtros de liga, temporada y posición.
3. **Argentina, fábrica de jugadores**: Sankey club de origen → liga de destino; ingresos por club y año;
   `peak_value_to_fee_ratio`.
4. **Subvaluados (BigQuery ML)**: top 20 por `predicted_to_actual_ratio`; real vs. predicho; importancia de
   variables; R² y MAE del modelo.
5. **Scouting con datos de eventos** (StatsBomb + Transfermarkt): dispersión npxG/90 vs. xA/90 con tamaño = valor de
   mercado; slicer de minutos mínimos (≥ 270 en torneos, ≥ 900 en ligas); tabla con pases y conducciones
   progresivas cada 90; `million_eur_per_npxg_xa_per_90`.
6. **Mapa de tiros y tabla por xG**: tiros sobre una imagen de medio campo (dispersión con ejes fijos 0-80 y
   60-120, tamaño = xG, color = gol); tabla real vs. xPts como en `docs/img/points_vs_xpts_2022.png`.
7. **Salud del pipeline**: filas por tabla y corrida, duración, tests que pasan o fallan, modelos más lentos.

## Medidas DAX sugeridas

```DAX
Goles por partido = DIVIDE ( SUM ( mart_player_seasons[goals] ), SUM ( mart_player_seasons[games] ) )

Goles cada 90 = DIVIDE ( SUM ( mart_player_seasons[goals] ) * 90, SUM ( mart_player_seasons[minutes] ) )

npxG + xA cada 90 =
DIVIDE (
    ( SUM ( mart_sb_player_seasons[npxg] ) + SUM ( mart_sb_player_seasons[xa] ) ) * 90,
    SUM ( mart_sb_player_seasons[minutes_played] )
)

Definición vs xG = SUM ( mart_sb_player_seasons[non_penalty_goals] ) - SUM ( mart_sb_player_seasons[npxg] )

Gasto (M€) = DIVIDE ( SUM ( mart_transfer_roi[transfer_fee_eur] ), 1e6 )

Tasa de aciertos =
DIVIDE (
    CALCULATE ( COUNTROWS ( mart_transfer_roi ), mart_transfer_roi[verdict] = "Acierto" ),
    CALCULATE ( COUNTROWS ( mart_transfer_roi ), mart_transfer_roi[verdict] IN { "Acierto", "Cumplió", "Fracaso" } )
)

Tests OK % =
DIVIDE (
    CALCULATE ( COUNTROWS ( dbt_results ), dbt_results[resource_type] = "test", dbt_results[status] = "pass" ),
    CALCULATE ( COUNTROWS ( dbt_results ), dbt_results[resource_type] = "test" )
)
```

## Publicar

"Publicar en la web" necesita una cuenta laboral o educativa de Power BI. Si no tenés, alcanza con el archivo en el
repo, una captura por página y un GIF corto en el README principal. Mencioná a StatsBomb como fuente con su logo
(lo piden sus términos de uso).
