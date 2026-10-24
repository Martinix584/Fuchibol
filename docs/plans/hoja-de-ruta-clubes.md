# Hoja de ruta: Fuchibol como sistema de datos de un club

> **Avance (23/10/2026):** etapas 1 y 2 implementadas, 7.1 y 7.2 medidas (ver criterios al final). Modelo de valor
> entrenado en local con scikit-learn (R² 0,83; la idea era BigQuery ML, pero no valía la pena acá). Pendiente:
> etapa 3 (Power BI, SkillCorner; la app ya está publicada) y etapa 4.
>
> Plan a futuro. Está pensado para leerse de punta a punta antes de tocar
> código. Las decisiones de la sección 2 ya se discutieron con el usuario: no rediscutirlas.
>
> **Estado (octubre 2026):** el pipeline histórico (Transfermarkt + StatsBomb) y la temporada actual
> (Understat + SofaScore) andan y están cargados en GCP: Transfermarkt (2,87 M filas crudas) y
> StatsBomb `core` (1,25 M) desde el 22/10/2026, con marts y modelo de valor en `prod` y `dev`.
>
> **SofaScore Argentina cargado (22/10/2026)** con `make sofascore` (modo `full`): Primera LPF 2026,
> 30 equipos, 839 jugadores (62 G, 276 D, 317 M, 184 F), 554 xG en total. `make dbt-current` pasa 48/48 y
> `mart_current_player_season` ya tiene filas `ARG` con `xg_source = 'sofascore'`.
>
> **SofaScore 5 grandes cargado (23/10/2026)** con `--mode full`, una liga por proceso: EPL 444, La Liga 461,
> Serie A 457, Bundesliga 386 y Ligue 1 393 jugadores (2.141 en total). La comparación 7.2 da correlación
> 0,97-0,98 con Understat y 2-10 % menos xG; está en el README.

## 1. Objetivo

Llevar Fuchibol de "buen proyecto de Data Engineering" a "el sistema que un Director de Datos querría tener
andando mañana", pensando en departamentos de datos de clubes (River, Talleres, Racing, Estudiantes, MLS,
Brasil, Europa) y consultoras de scouting (Driblab, StatsBomb, Zelus, SRC).

Lo que ya diferencia al proyecto: ingesta automática de varios proveedores, cruce de IDs sin romper nada,
esquemas versionados y tablas listas para que el analista o el director deportivo las consuman a primera hora.
Lo que falta: **métricas en el idioma del scouting**, **números reales en el README** y **algo que se pueda
tocar sin instalar nada**.

## 2. Decisiones ya tomadas (no rediscutir)

- **Cruce de jugadores sin club.** El escalón nuevo de `int_player_id_map` **no** exige "mismo club": gran
  parte del alcance `core` son selecciones (en StatsBomb el equipo es "Argentina", no el club) y no existe un
  `int_club_id_map`. Se usa nacionalidad + año de actividad solapado + Levenshtein ≤ 2.
- **No hay fecha de nacimiento en StatsBomb.** Las alineaciones de StatsBomb Open Data no la traen, así que
  no se puede usar como clave del cruce StatsBomb → Transfermarkt.
- **Grupo de posición por minutos, desde las alineaciones.** `stg_sb_lineups` ya guarda el array
  `positions` completo y `int_sb_player_match_minutes` ya lo despliega en tramos. Se suman segundos por
  puesto; no se usa la moda de los eventos (cuenta toques, no tiempo, y BigQuery no tiene `MODE()`).
- **Nada de métricas sacadas del smoke.** El smoke usa un Transfermarkt **sintético**: el cruce por regla,
  el R²/MAE y cualquier cosa de fichajes tienen que salir de la carga real en GCP.
- **La app pública lee datos reales**, exportados de BigQuery, nunca el `.duckdb` del smoke.
- **Club Elo cubre solo Europa** (no Argentina, Brasil ni MLS): sirve para ponderar dentro de Europa, no las
  ventas de la liga argentina.
- **Capturas y Parquet al final.** Power BI, capturas y exportación se hacen recién cuando estén xT, PAdj y
  percentiles, para no hacerlos dos veces.
- **SofaScore es la fuente de Argentina**, cargada a mano con `make sofascore` (navegador visible).
  API-Football queda como fuente opcional para estadísticas no-xG.

## 3. Etapa 1: números reales (1-2 días)

1. **`make understat` y `make sofascore` registran métricas.** Ni `ingestion/understat.py:main()` ni
   `ingestion/sofascore.py` llaman a `metrics.record_ingestion`, así que `ops.pipeline_runs` queda vacía
   (la carga de Argentina del 22/10 tampoco quedó registrada). Sumarlo en los dos (con un `run_id` tipo
   `manual__xxxx`, como `scripts/run_ingestion.py`). Test: que cada `main` llame a `record_ingestion`.
2. **xG nulo en SofaScore Argentina** (200 de 839 jugadores). SofaScore directamente no manda
   `expectedGoals` para esos jugadores (verificado en el JSON crudo: el scraper no pierde nada). Hay dos
   casos distintos:
   - **114 sin ningún tiro** (arqueros, defensores): xG real = 0. En `stg_ss_player_season`, poner
     `xg = 0` cuando `shots = 0` y no venga el dato, así entran a los per-90 y percentiles.
   - **86 con tiros pero sin xG** (ej. Federico Gino, Aldosivi: 16 tiros, 2 goles): el dato falta de
     verdad. Dejarlo `null` (no inventar) y agregar un test de dbt con `severity: warn` que cuente cuántos
     hay, para ver si baja en cargas futuras.
   - Mismo criterio para `xa` (`expectedAssists`).
3. **El respaldo de las 5 grandes en modo `top` casi no trae xG.** `top` une los rankings de
   `top-players/overall`, y el de xG lista unos 50 jugadores por liga: en Argentina, 410 de 460 filas `top`
   vinieron sin xG. Con `xg_source_big5: sofascore` + `--mode top`, el mart quedaría con xG solo para los
   líderes. Cambiar el runbook (`docs/runbooks/xg-manual-fallback.md`), el docstring de
   `ingestion/sofascore.py` y el default de `SOFASCORE_MODE` para las 5 grandes a `full`, partido por liga
   en varios días por el presupuesto (ver 7.2). Otra opción es dejar `top` documentado como "solo
   líderes", pero entonces no sirve como reemplazo de Understat.
4. **Carga real en GCP:** `make extract` (Transfermarkt + StatsBomb `core` + Understat), `make dbt-build`,
   `make dbt-train`. El alcance `core` entra en el nivel gratuito; configurar alerta de presupuesto antes.
5. **Completar la tabla de métricas del README** con `make metrics`: filas por fuente, volumen, duración,
   tests, **cruce por regla** y **R²/MAE** del modelo (el MAE está en log del valor: aclararlo o
   convertirlo a euros con cuidado).

## 4. Etapa 2: métricas de fútbol (1 fin de semana)

### 4.1 xT (Expected Threat)

- Seed `dbt/seeds/xt_grid.csv` con la grilla pública de Karun Singh (12 × 8 zonas sobre la cancha
  120 × 80 de StatsBomb). Citar la fuente en el seed y en el README.
- Macro `xt_zone(x, y)` → índice de zona; `xt_added = xt(end) - xt(start)`.
- Pases: `int_sb_passes` ya tiene `x, y, end_x, end_y`; solo pases completados.
- Conducciones: **no existe `int_sb_carries`**; crearlo desde `stg_sb_events` (`carry_detail.end_location`).
- Mart: `xt_added`, `xt_added_per_90` por jugador-temporada en `mart_sb_player_seasons`.
- Unit test de dbt: un pase de una zona conocida a otra da el delta esperado.

### 4.2 Grupo de posición

- Agregar el nombre del puesto al CTE de tramos de `int_sb_player_match_minutes` y sumar segundos por puesto
  **antes** de unir intervalos superpuestos.
- Mapear a 6 grupos: GK, CB, FB, CM, W/AM, ST (seed `position_groups.csv` desde los nombres de StatsBomb).
- `position_group` = el grupo con más minutos del jugador en la temporada.

### 4.3 PAdj (ajuste por posesión) para acciones defensivas

- Posesión por partido desde `stg_sb_events` (`possession`, `possession_team_id` y duración de cada
  posesión).
- Ajustar quites, intercepciones y presiones por la posesión del rival (fórmula sigmoide de StatsBomb para
  PAdj Tackles & Interceptions). Documentar en el README por qué: un defensor de un equipo con 35 % de
  posesión suma el doble de acciones solo porque defiende más.

### 4.4 Percentiles por posición

- Para Argentina (temporada actual) se puede hacer **ya**, sin esperar a StatsBomb: SofaScore trae
  `position` (G, D, M, F) y minutos. Percentiles de xG, xA, tiros y pases clave cada 90 por posición, con
  ≥ 600 minutos, en un mart `mart_current_player_percentiles` (Argentina con SofaScore y las 5 grandes con
  Understat, **cada fuente por separado**).
- Para StatsBomb: vista con `round(percent_rank() over (partition by competition_id, season_id, position_group order by
  metric_per_90) * 100)` para 8-10 métricas clave (npxG, xA, xT, pases y conducciones progresivas, PAdj
  defensivas, presiones), solo jugadores con ≥ 600 minutos.
- Alimenta los radares de Power BI y de la app.

## 5. Etapa 3: producto (1-2 semanas)

1. **Power BI:** actualizar el reporte con xT, percentiles y PAdj; capturas definitivas + GIF corto, y una
   captura del grafo de linaje de dbt docs (<https://martinix584.github.io/Fuchibol/>). Power BI Desktop no
   corre en Linux: hace falta una VM de Windows (o usar Looker Studio como alternativa para el dashboard web).
2. **Exportar los marts a Parquet** desde BigQuery (datos reales) para la app.
3. **App pública** (Evidence.dev o Streamlit Community Cloud) sobre esos Parquet con DuckDB: radar de
   comparación de jugadores, buscador de subvaluados, ROI de fichajes y mapa de tiros. Link arriba de todo
   en el README.
   - Liga Argentina actual: ya hay xG/xA de SofaScore en `mart_current_player_season` (`league_code =
     'ARG'`). Para filtrar "Sub-23" falta la edad: SofaScore no la guarda hoy; o se agrega `dateOfBirth`
     al scraper (si viene en el payload del jugador; verificar) o se cruza con Transfermarkt.
   - StatsBomb Open Data no tiene liga argentina: las métricas de eventos (xT, PAdj) no van a existir
     para Argentina, solo xG/xA y las estadísticas de SofaScore.
   - Revisar licencias antes de publicar: StatsBomb pide atribución; Transfermarkt es CC0.
4. **SkillCorner Open Data** (`skillcorner/opendata`, ~10 partidos de tracking a 10 fps) como módulo aparte,
   en DuckDB/Parquet por volumen: sprints (> 25 km/h), HSR y aceleraciones por jugador y partido.

## 6. Etapa 4: refinamientos

- **Escalón 6 del cruce de jugadores** (después de `name_only`): nombre normalizado sin tildes
  (`normalize(..., NFD)` + quitar marcas) + misma nacionalidad + algún año en común (`match_date` de
  StatsBomb vs. `game_date` de `stg_appearances`) + `edit_distance <= 2`, y **único** en ese año (si hay dos
  candidatos, se descarta como en las demás reglas). Medir cuánto sube el cruce; no prometer un porcentaje.
- **Club Elo** (clubelo.com, CSV público) como tabla liviana en el DAG para ponderar `mart_transfer_roi` y el
  modelo de valor **solo para fichajes entre clubes europeos** (ΔElo).
- **Modelos incrementales en dbt:** `stg_sb_events` hoy es `table` clusterizada por `match_id, event_type`.
  Pasarla a `incremental` con `insert_overwrite` recién cuando se cargue el alcance `all`; con `core` la
  ganancia es chica.

## 7. Validar los modelos de xG con datos propios

Understat y SofaScore **no usan el mismo modelo de xG**:
- **Understat** usa un modelo propio, entrenado con más de 100.000 tiros.
- **SofaScore** no publica su metodología. Se infiere que muestra el xG de Opta porque coincide con el de
  FotMob, pero es una inferencia, no algo que ellos confirmen.

Los números difieren por varias razones: el modelo, qué cuenta cada uno como tiro (bloqueos, desvíos, goles
en contra), las coordenadas de cada remate (hay diferencias de metros entre proveedores) y el tratamiento de
los penales. Por eso `mart_current_player_season` tiene `xg_source` y nunca mezcla fuentes en una fila:
`goals - xg` se puede comparar dentro de una fuente, no entre fuentes. Esta sección **mide** esa
diferencia en vez de suponerla.

### 7.1 Understat vs. StatsBomb (se puede hacer ya)

- Las dos fuentes cubren las 5 grandes en **2015/16**: StatsBomb Open Data tiene esa temporada (cuatro ligas
  completas) y Understat cubre desde 2014/15.
- Backfill de Understat para esa temporada: `UNDERSTAT_SEASON=2015` o `--season 2015` (5 requests).
- Script `scripts/compare_xg.py` (o un análisis dbt con tag `validation`, fuera de `tag:current`) que cruce
  jugador × liga-temporada y reporte, por liga:
  - suma de xG de cada fuente y diferencia porcentual;
  - correlación (Pearson) entre fuentes por jugador;
  - diferencia media absoluta;
  - % de jugadores donde difieren más de 0,5 xG;
  - cobertura: tiros y jugadores que hay en una fuente y faltan en la otra.
- El cruce de jugadores entre StatsBomb y Understat es otro problema de identidad: reusar la normalización
  de nombres de `int_player_id_map` (nombre sin tildes + equipo + temporada) y descartar los ambiguos.
  Equipo sí sirve acá, porque las dos fuentes son de clubes y de la misma liga.
- Resultado al README, en "Sobre los datos": cuánto se separan los dos modelos de xG.

### 7.2 Understat vs. SofaScore

- Ingerir las 5 grandes con `python -m ingestion.sofascore --scope big5 --mode full` y aplicar las mismas
  métricas de 7.1 contra Understat, mismos jugadores y misma temporada (2026/27, ya cargada de Understat).
- **Tiene que ser `full`, no `top`:** en la carga de Argentina, el modo `top` trajo xG solo para 50 de 460
  jugadores; el resto vino en `null` porque `top` solo lista a los que aparecen en el ranking de xG.
- **Volumen:** Argentina en `full` fueron ~840 requests en ~50 minutos. Las 5 grandes son ~2.200 jugadores,
  así que `SOFASCORE_DAILY_BUDGET=1000` corta la corrida. Partir por liga (`--scope EPL`, después
  `La_liga`, etc.) en días distintos; el manifest saltea lo ya bajado.
- Cruce de jugadores Understat ↔ SofaScore: nombre normalizado + equipo + temporada, descartando ambiguos
  (las dos son de clubes y de la misma liga).
- Sirve para decidir con números si el respaldo manual (`xg_source_big5: sofascore`) es intercambiable con
  Understat o si cambia las conclusiones.

## 8. Criterios de aceptación

- [x] `ops.pipeline_runs` tiene filas después de `make understat`, `make sofascore` y de cada corrida del DAG con datos nuevos.
- [x] La tabla de métricas del README no tiene ningún *pendiente* y todos sus números salen de GCP (costo: US$0 dentro del free tier, con alerta a US$1/mes).
- [x] `xt_added_per_90`, `position_group`, métricas PAdj y percentiles en los marts, con tests de dbt.
- [x] Smoke en verde después de cada etapa (CI corre al pushear).
- [ ] Capturas de Power BI y del linaje en el README, tomadas después de la etapa 2.
- [x] App pública con datos reales y link en el README (Streamlit Community Cloud, 23/10/2026). Falta mejorarle el diseño.
- [x] SofaScore Argentina cargado y en `mart_current_player_season` (22/10/2026).
- [x] xG = 0 para jugadores de SofaScore sin tiros; test de aviso para los que tienen tiros y no xG.
- [x] Percentiles por posición de la temporada actual (Argentina y 5 grandes, por fuente).
- [x] Comparación Understat vs. StatsBomb (2015/16) con correlación, diferencia media y cobertura por liga,
      resumida en el README (`scripts/compare_xg.py`, en local; la Bundesliga queda afuera porque StatsBomb trae
      solo 34 partidos).
- [x] Comparación Understat vs. SofaScore (2026/27, 5 grandes) con las mismas métricas: correlación 0,97-0,98,
       SofaScore da 2-10 % menos xG y la cobertura es 96-99 % (`scripts/compare_xg_current.py`, 23/10/2026).
