# Reporte de Power BI

El `.pbix` va en esta carpeta (`fuchibol.pbix`) junto con capturas en `powerbi/img/`.

## Conexión

1. Power BI Desktop → **Obtener datos** → **Google BigQuery** → iniciar sesión con tu cuenta de GCP.
2. Proyecto → dataset `marts` y `ml` (y `ops` para la página de salud del pipeline).
3. Modo **Importar** (el volumen es chico y así no pagás queries cada vez que alguien abre el reporte).

## Modelo (estrella)

| Tabla | Tipo | Relación |
|---|---|---|
| `marts.dim_players` | dimensión | `player_id` 1 → * hechos |
| `marts.dim_clubs` | dimensión | `club_id` 1 → * `mart_transfer_roi[to_club_id]` |
| `marts.mart_player_seasons` | hecho | jugador × temporada |
| `marts.mart_transfer_roi` | hecho | un fichaje pago por fila |
| `marts.mart_argentina_exports` | hecho | ventas de la liga argentina al exterior |
| `marts.mart_club_transfer_balance` | agregado | un club por fila |
| `ml.mart_undervalued_players` | hecho | jugador (última temporada) |
| `ml.ml_feature_importance`, `ml.ml_model_evaluation` | apoyo | — |
| `ops.pipeline_runs`, `ops.dbt_results` | apoyo | — |

## Páginas

1. **Ficha del jugador**: buscador por nombre; tarjetas con partidos, goles, asistencias, goles por partido y cada 90; línea de valor de mercado por temporada; tabla de temporadas.
2. **¿Valió lo que se pagó?**: dispersión monto pagado (x) vs. valor 1 año después (y) coloreada por `verdict`; ranking de clubes por `hit_rate`; filtros por liga, temporada y posición.
3. **Argentina, fábrica de jugadores**: Sankey o mapa club de origen → liga de destino; ingresos por club argentino y por año; revalorización (`peak_value_to_fee_ratio`).
4. **Subvaluados (BigQuery ML)**: top 20 por `predicted_to_actual_ratio`; real vs. predicho; importancia de variables; métricas del modelo (R², MAE).
5. **Salud del pipeline**: filas por tabla, duración de cada corrida, tests que pasan / fallan, modelos más lentos.

## Medidas DAX sugeridas

```DAX
Goles por partido = DIVIDE ( SUM ( mart_player_seasons[goals] ), SUM ( mart_player_seasons[games] ) )

Goles cada 90 = DIVIDE ( SUM ( mart_player_seasons[goals] ) * 90, SUM ( mart_player_seasons[minutes] ) )

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

"Publicar en la web" necesita una cuenta laboral o educativa de Power BI. Si no tenés, alcanza con
el `.pbix` en el repo, capturas de cada página y un GIF corto en el README principal.
