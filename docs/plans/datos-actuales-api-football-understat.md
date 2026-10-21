# Plan: datos de la temporada actual (API-Football + Understat)

> Plan de trabajo para un agente que retome el proyecto. Está escrito para leerse de punta a punta
> antes de tocar código. Todo lo marcado **VERIFICAR** se dio por cierto sin poder comprobarlo
> (la red del entorno donde se escribió bloqueaba esas APIs): comprobalo contra la API real antes
> de construir encima.

## 1. Contexto

Fuchibol es un pipeline de punta a punta: **Python → GCS → BigQuery → dbt → BigQuery ML → Airflow → Power BI**.
Hoy tiene dos fuentes, y ninguna trae la temporada en curso:

| Fuente | Qué trae | Problema |
|---|---|---|
| Transfermarkt ([transfermarkt-datasets](https://github.com/dcaribou/transfermarkt-datasets), CC0) | Jugadores, valores de mercado, transferencias, apariciones | Las actualizaciones están **pausadas desde el 6 de julio de 2026** |
| StatsBomb Open Data | Eventos con xG, xA, progresivos y presiones | Casi todo es **histórico** (torneos y temporadas puntuales) |

El usuario quiere **datos actuales** de **las 5 grandes ligas + la Liga Profesional Argentina**. Se suman dos
fuentes:

| Fuente nueva | Para qué | Cobertura |
|---|---|---|
| **API-Football v3** | Estadísticas actuales por jugador (minutos, goles, asistencias, pases clave, duelos, gambetas, rating…) y por partido | Las 6 ligas |
| **Understat** | xG, xA, npxG, xGChain, xGBuildup por jugador y xPts por equipo, temporada actual | Solo las 5 grandes ligas (**no** Argentina) |

### Decisiones ya tomadas con el usuario (no rediscutir)

- Ligas: Premier League, La Liga, Serie A, Bundesliga, Ligue 1 y Liga Profesional Argentina.
- Plan **gratis** de API-Football mientras alcance: unas 100 requests por día y 10 por minuto. Si el plan
  gratis no deja pedir la temporada actual, se avisa al usuario: la alternativa es el plan Pro (unos USD 19 por
  mes, 7.500 requests por día). **No contratar nada sin su confirmación.**
- **Bajar una vez y guardar para siempre:** lo histórico se baja una vez, y la temporada en curso se actualiza
  de forma incremental (solo los partidos nuevos). La "base serverless" es **BigQuery**, que ya usa el proyecto:
  no hay que sumar otra base.
- Los datos crudos de API-Football y Understat **no se suben al repo** (licencias). En el reporte solo van
  agregados y métricas derivadas.

### Fuentes descartadas (y por qué; no volver a proponerlas)

- **FBref:** desde enero de 2026 ya no tiene xG, xA ni acciones progresivas (Opta le cortó el acceso), y
  Sports Reference no permite el scraping masivo. Fuente: <https://www.sports-reference.com/blog/2026/01/fbref-stathead-data-update/>
- **Scraping de Transfermarkt:** va contra sus términos. Se sigue usando el dataset CC0.
- **"SoccerData trae Transfermarkt y Capology":** es falso; la librería no incluye esas fuentes.
- **Opta o StatsBomb pagos:** fuera de presupuesto.

## 2. Prerrequisitos (del usuario; pedirlos si faltan)

1. **API key de API-Football** (cuenta gratis en <https://dashboard.api-football.com>), cargada como **secreto del
   entorno** con el nombre `API_FOOTBALL_KEY`. Nunca en el chat, en el repo ni en logs.
2. **Red:** agregar `v3.football.api-sports.io` y `understat.com` en *Network access → Allowed domains* del
   entorno. Pasos: <https://code.claude.com/docs/en/cloud-environments#network-access>
3. En producción (Airflow), la key va como variable de entorno del contenedor (`.env`, que está en
   `.gitignore`) o como Airflow Variable o Connection. Documentarlo en `.env.example` **sin el valor**.

Si faltan la key o la red, **no inventes respuestas de la API.** Se puede avanzar con el código y con tests
sobre fixtures armadas a mano según la documentación, pero dejá claro en el PR que falta la validación real.

## 3. Paso 0: verificaciones antes de escribir código

Hacelas con `curl` y anotá los resultados en el PR. Cada llamada consume cuota: usá las justas.

```bash
H="x-apisports-key: $API_FOOTBALL_KEY"
B=https://v3.football.api-sports.io

curl -s -H "$H" $B/status                       # plan, requests usadas hoy y límite diario
curl -s -H "$H" "$B/leagues?id=128"             # Argentina: temporadas, cuál es current y coverage
curl -s -H "$H" "$B/players?league=39&season=2026&page=1"   # ¿el plan gratis deja la temporada actual?
```

**VERIFICAR** y decidir:

- [ ] **Acceso a la temporada actual con el plan gratis.** Si `errors` viene no vacío (por ejemplo
  `{"plan": "Free plans do not have access to this season, try from 2021 to 2023."}`), **frená y avisale al
  usuario** con el texto exacto. No sigas con temporadas viejas como si fueran actuales.
- [ ] **Los errores vienen con HTTP 200:** API-Football devuelve 200 y pone el problema en el campo `errors`
  (puede ser lista vacía `[]` u objeto `{}`). El cliente tiene que tratar `errors` no vacío como fallo.
- [ ] **Encabezados de cuota:** `x-ratelimit-requests-limit` y `x-ratelimit-requests-remaining` (diarios) y
  `X-RateLimit-Limit` / `X-RateLimit-Remaining` (por minuto). Confirmá los nombres exactos.
- [ ] **Qué `season` usar:** el año de inicio (Europa 2026/27 → `2026`; Argentina 2026 → `2026`). Mirá
  `seasons[].current` en `/leagues`.
- [ ] **Formato de Argentina:** si Apertura y Clausura están dentro de la misma liga 128 (distintos `round`) o
  en ids separados.
- [ ] **`coverage`** de cada liga y temporada: `fixtures.statistics_players` y `players` tienen que ser `true`.
- [ ] **Understat:** cómo expone hoy los datos. Históricamente venían embebidos en el HTML de
  `https://understat.com/league/<LIGA>/<AÑO>` como `var playersData = JSON.parse('...')` (con escapes `\xNN`),
  igual que `teamsData` y `datesData`. Puede haber cambiado a endpoints JSON. Inspeccioná la página y elegí el
  camino más estable. Nombres de liga: `EPL`, `La_liga`, `Bundesliga`, `Serie_A`, `Ligue_1`.
- [ ] **Términos de Understat:** no se encontraron. Scraping liviano (pocas requests, con caché y espera entre
  llamadas), sin redistribuir datos crudos. Si sus términos lo prohíben, avisá y dejá Understat afuera.

## 4. Datos de referencia

### API-Football v3 (**VERIFICAR** contra la documentación: <https://www.api-football.com/documentation-v3>)

- Base: `https://v3.football.api-sports.io`, encabezado `x-apisports-key`.
- Ligas: Premier **39**, La Liga **140**, Serie A **135**, Bundesliga **78**, Ligue 1 **61**, Liga Profesional
  Argentina **128**.
- Endpoints que se usan:

| Endpoint | Para qué | Costo |
|---|---|---|
| `/status` | Cuota restante (no consume) **VERIFICAR** | 0-1 |
| `/leagues?id=` | Temporada actual y coverage | 1 por liga |
| `/fixtures?league=&season=` | Lista de partidos con estado (`fixture.status.short`: `FT`, `AET`, `PEN`…) | 1 por liga |
| `/players?league=&season=&page=` | Totales por jugador en la temporada (20 por página, `paging.total`) | ~30-40 por liga |
| `/fixtures/players?fixture=` | Stats de cada jugador en un partido | 1 por partido |
| `/fixtures/statistics?fixture=` | Stats de equipo (a veces con `expected_goals`) | opcional, 1 por partido |

- Estructura de `/players` (`response[]`): `player{id, name, firstname, lastname, age, birth{date, place, country},
  nationality, height, weight, photo}` + `statistics[]` (una por equipo y liga) con `team`, `league`,
  `games{appearences, lineups, minutes, number, position, rating, captain}`, `substitutes{in, out, bench}`,
  `shots{total, on}`, `goals{total, conceded, assists, saves}`, `passes{total, key, accuracy}`,
  `tackles{total, blocks, interceptions}`, `duels{total, won}`, `dribbles{attempts, success, past}`,
  `fouls{drawn, committed}`, `cards{yellow, yellowred, red}`, `penalty{won, commited, scored, missed, saved}`.
  Ojo con las faltas de ortografía de la API (`appearences`, `commited`): respetalas en el esquema.
- Muchos valores numéricos llegan como **string** o **null** (por ejemplo `rating: "7.2"` o `passes.accuracy`).
  En raw, guardalos como STRING y castealos en staging con `safe_cast` (macro `to_int` y similares).
- **No trae xG ni xA por jugador.** Para eso están StatsBomb (histórico) y Understat (actual).

### Understat (**VERIFICAR**)

- Jugadores por liga y temporada: `id, player_name, games, time, goals, xG, assists, xA, shots, key_passes,
  yellow_cards, red_cards, position, team_title, npg, npxG, xGChain, xGBuildup`, todos como string.
- Equipos (`teamsData`): `history[]` por partido con `xG, xGA, npxG, npxGA, deep, ppda, xpts, result, date,
  scored, missed, pts`.
- La temporada es el año de inicio (2026 → 2026/27).

### Presupuesto de requests (plan gratis, 100 por día)

| Etapa | Requests | Días |
|---|---|---|
| Totales de la temporada (`/players`, 6 ligas × ~35 páginas) | ~210 | 2-3 |
| Detalle por partido de lo que va de la temporada (~800 partidos) | ~800 | ~9 |
| Mantenimiento: partidos nuevos por semana entre las 6 ligas | ~60-80 por semana | 10-15 por día |

Orden: primero los **totales de temporada** (en 2 o 3 días ya hay datos actuales de las 6 ligas) y después el
backfill por partido en segundo plano. Dejá **siempre un margen** (tope de unas 90 por día, configurable).

## 5. Arquitectura propuesta

```
API-Football ──► ingestion/api_football.py ──► GCS raw/api_football/<endpoint>/... ──► BigQuery raw_api_football
Understat    ──► ingestion/understat.py    ──► GCS raw/understat/...               ──► BigQuery raw_understat
                                                                   │
                                     dbt staging → intermediate → marts (temporada actual)
```

Seguí **los mismos patrones** que `ingestion/statsbomb.py`:

- **NDJSON.gz en GCS** con el JSON completo de la respuesta, y carga a BigQuery con **esquema explícito**
  (`ingestion/schemas/*.json`) + `ignore_unknown_values=True`, siempre `WRITE_APPEND`, partición por
  `_ingested_at` y cluster por la clave natural. El staging se queda con la última ingesta de cada clave
  (`qualify row_number() over (partition by <clave> order by _ingested_at desc) = 1`).
- **Load jobs** (gratis), nunca streaming inserts.
- **Manifest en GCS** (`manifests/api_football.json`) con el estado: qué páginas de `/players` se bajaron por
  liga y temporada (y cuándo), y qué `fixture_id` ya tienen `/fixtures/players`. Se guarda **después** de cargar,
  como en StatsBomb.
- **Funciones puras separadas de la red** (planificar, armar filas, parsear), para testearlas con pytest sin
  credenciales.

### 5.1 `ingestion/api_football.py`

- `Client`: sesión `requests` con el encabezado de la key, timeout, reintentos con espera exponencial ante 429,
  5xx y cortes de red, y **tope de 10 por minuto** (dormir lo necesario). Lee y loguea los encabezados de cuota.
  Lanza un error claro si `errors` no está vacío. **Nunca loguear la key.**
- `Budget`: cuenta las requests de la corrida y corta cuando llega a `API_FOOTBALL_DAILY_BUDGET` (default 90) o
  cuando `x-ratelimit-requests-remaining` baja de un mínimo. Sin cuota, la corrida termina bien (no es un
  error): el resto sigue mañana.
- `plan_work(manifest, leagues, season, budget)`: función pura que arma la lista priorizada.
  1. `/leagues` y `/fixtures` de cada liga, una vez por día (para saber qué partidos terminaron).
  2. Páginas de `/players` que faltan o tienen más de N días (los totales cambian con cada fecha: refrescarlos
     una vez por semana).
  3. `/fixtures/players` de partidos terminados que todavía no se bajaron, del más nuevo al más viejo.
- Tablas raw: `leagues`, `fixtures`, `players_season` (una fila por jugador y página, con `statistics` anidado),
  `fixture_players` (una fila por equipo y partido, con jugadores anidados).
- Configuración en `ingestion/config.py`: `API_FOOTBALL_BASE_URL`, `API_FOOTBALL_KEY` (solo env),
  `API_FOOTBALL_LEAGUES = {39: ..., 140: ..., 135: ..., 78: ..., 61: ..., 128: ...}`, `API_FOOTBALL_SEASON`
  (default: la `current` de `/leagues`), `API_FOOTBALL_DAILY_BUDGET=90`, `BQ_API_FOOTBALL_DATASET`.

### 5.2 `ingestion/understat.py`

- Una request por liga y temporada para jugadores y equipos (según lo que se encuentre en el paso 0), con 2 a 5
  segundos entre requests y un User-Agent que identifique el proyecto.
- Solo la temporada actual por defecto (y opcionalmente las anteriores, una sola vez).
- Raw: `players_season` y `team_matches` (de `teamsData.history`).
- Si el formato es el `JSON.parse('...')` embebido: extraerlo con regex y decodificar los `\xNN` con
  `codecs.decode(s, "unicode_escape")`, con un test que cubra justamente esa decodificación. Si se evalúa
  `soccerdata` como dependencia, fijá la versión y aislalo detrás de una función, porque se rompe cuando el
  sitio cambia.

### 5.3 Airflow

- **DAG nuevo, diario:** `dags/fuchibol_current_season.py` (por ejemplo 07:00 UTC). Tareas: `af_plan` →
  `af_fetch` (una sola tarea secuencial: la cuota es global y no conviene paralelizar) → `af_finish`
  (métricas + manifest) ‖ `understat_fetch` → `understat_finish` → gate de cambios → `dbt build` de los modelos
  de temporada actual (`--select tag:current+`).
- El DAG semanal existente (`fuchibol_pipeline`) **no cambia**, salvo que conviene excluir `tag:current` de su
  `dbt_build_core` para no reconstruirlos dos veces (o dejarlos y documentarlo).
- Mismas reglas que el DAG actual: `dbt_command()`, `env -u PYTHONPATH` para dbt, manifest al final y
  `trigger_rule="none_failed"` donde una rama pueda quedar en *skipped*.
- La key llega como variable de entorno del contenedor. Sumala a `docker-compose.yml` vía `env_file` (ya existe)
  y a `.env.example` sin valor.

### 5.4 dbt

Carpetas nuevas: `models/staging/api_football`, `models/staging/understat`, `models/intermediate/current`,
`models/marts/current`. Ponele `+tags: ["current"]` a lo nuevo en `dbt_project.yml`.

| Modelo | Grano | Contenido |
|---|---|---|
| `stg_af_fixtures` | partido | ids, liga, temporada, ronda, fecha, equipos, goles, estado |
| `stg_af_players` | jugador | perfil: nombre, nombre y apellido, **fecha de nacimiento**, nacionalidad, altura |
| `stg_af_player_season_stats` | jugador × equipo × liga × temporada | totales (`unnest(statistics)`) |
| `stg_af_fixture_player_stats` | jugador × partido | stats del partido (`unnest` de equipos y jugadores) |
| `stg_us_players_season` | jugador Understat × liga × temporada | xG, xA, npxG, xGChain, xGBuildup… |
| `stg_us_team_matches` | equipo × partido | xG, xGA, xpts, pts, ppda |
| `int_af_player_season` | jugador × liga × temporada | suma de equipos + métricas cada 90 (macro `per_90`, ya tiene paréntesis) |
| `int_player_id_map_af` | jugador AF → Transfermarkt | cruce (ver abajo) |
| `int_player_id_map_us` | jugador Understat → AF | por nombre normalizado + equipo + liga y temporada |
| `mart_current_player_season` | jugador × liga × temporada actual | stats AF + xG y xA de Understat (si hay) + valor de mercado TM |
| `mart_current_team_table` | equipo × liga actual | puntos, xPts (Understat en las 5 grandes; en Argentina sin xPts), diferencia |
| `mart_transfer_roi_current` | o extender `mart_transfer_roi` | rendimiento post-fichaje con AF para fichajes recientes |

**Cruce con Transfermarkt:** API-Football trae la **fecha de nacimiento**, así que el cruce es mucho más preciso
que con StatsBomb.

1. Fecha de nacimiento igual + nombre normalizado igual (macro `normalize_name`).
2. Fecha de nacimiento igual + misma nacionalidad + todas las palabras de un nombre dentro del otro.
3. Nombre normalizado + nacionalidad (sin fecha), solo si es único.

Reusá la lógica de `int_player_id_map.sql`: mejor regla primero, descartar empates y seed de overrides
(podés crear `seeds/af_player_id_overrides.csv`). Agregá a `ops` o a un modelo la **tasa de cruce por liga**, que
es una métrica del README.

**Tests mínimos:** `unique` / `not_null` en claves; `unique_combination` en granos compuestos; `non_negative` en
conteos; `in_range` en minutos por partido (0-150), en `rating` (0-10) y en `pass_accuracy` (0-100); relaciones
entre jugador y partido; **unit tests** para la suma por equipos, para `per_90` y para el cruce por fecha de
nacimiento. Seguí la sintaxis del repo (`data_tests` con `arguments:`, `config: severity: warn` donde aplique).

**Convenciones SQL del repo** (respetalas): BigQuery; `{{ to_int(...) }}` para enteros que pueden llegar como
string o float; `where true` antes de un `qualify` que no tenga `WHERE` ni `GROUP BY`; nada de `select *` en marts
salvo que esté justificado; comentarios en español dentro de `{# #}`; nombres en inglés y `snake_case`.

### 5.5 Power BI y README

- `powerbi/README.md`: sumar la página **"Temporada actual"** (tabla de jugadores con slicer de liga y minutos
  mínimos, xG/90 y xA/90 en las 5 grandes, rating y pases clave/90 en Argentina) y actualizar "¿Quién tuvo
  suerte?" con `mart_current_team_table`.
- `README.md`: fuentes (con atribución a API-Football y Understat), diagrama, métricas (requests usadas por día,
  filas, tasa de cruce) y la aclaración de que Argentina no tiene xG.
- Exposure de Power BI (`dbt/models/exposures.yml`): sumar los marts nuevos.

## 6. Tests y validación (antes de cada push)

```bash
ruff check ingestion dags tests scripts && ruff format --check ingestion dags tests scripts
pytest -q
(cd dbt && dbt parse --profiles-dir .)
scripts/smoke.sh --matches 8          # smoke actual: no debe romperse
scripts/test_dag.sh                   # sumar los escenarios del DAG nuevo
```

- **pytest** para todo lo puro: `plan_work` (presupuesto, prioridades, reanudar al otro día), parseo de
  `errors`, encabezados de cuota, armado de filas, decodificación de Understat. Usá **fixtures chicas armadas a
  mano** con la estructura real (pocas filas, nombres inventados). **No subas respuestas reales completas.**
- **Smoke test:** extender `tests/smoke/` con un generador sintético para las tablas raw nuevas, siguiendo el
  ejemplo de `synthetic_transfermarkt.py`, para que los modelos nuevos corran en DuckDB en CI.
- **DAG:** escenarios con `dag.test()` en `tests/dags/` (sin cuota, con partidos nuevos, error de plan).
- **Validación real** (con key y red): corré una ingesta con `API_FOOTBALL_DAILY_BUDGET=10`, revisá en el PR las
  filas reales por tabla y contrastá 2 o 3 números conocidos (goleador de una liga, minutos de un titular).

## 7. Orden de trabajo sugerido (un PR por paso)

1. **Paso 0 + cliente API-Football**: verificaciones, `Client`, `Budget`, `plan_work`, esquemas, `/leagues`,
   `/fixtures` y `/players` con sus tests.
2. **`/fixtures/players`** + backfill incremental + DAG diario.
3. **dbt de API-Football** + cruce con Transfermarkt + smoke y tests.
4. **Understat** (ingesta + dbt + cruce con AF).
5. **Marts de temporada actual**, README, Power BI y exposure.

Cada PR: CI en verde, descripción con lo verificado y lo que falta, y sin datos crudos ni secretos.

## 8. Criterios de aceptación

- [ ] Con el plan gratis, en ≤ 3 días hay **totales de la temporada actual** de las 6 ligas en BigQuery.
- [ ] El backfill por partido avanza solo cada día **sin pasarse del presupuesto** y retoma donde quedó.
- [ ] Una corrida sin cuota termina en verde y no pierde estado.
- [ ] Reprocesar no duplica nada (staging con la última ingesta).
- [ ] Tasa de cruce AF → Transfermarkt reportada por liga (objetivo orientativo: > 85 % en las 5 grandes).
- [ ] xG y xA actuales de Understat para las 5 grandes; Argentina documentada sin xG.
- [ ] CI en verde (lint, pytest, dbt parse, smoke y DAG) y README y Power BI actualizados.
- [ ] Ningún secreto ni dato crudo en el repo.

## 9. Riesgos y qué hacer

| Riesgo | Qué hacer |
|---|---|
| El plan gratis no da la temporada actual | Frenar y avisar al usuario (opción: plan Pro). No usar temporadas viejas como si fueran actuales. |
| Cambia el formato de Understat | Parser aislado y tests; si se rompe, el DAG marca la rama como fallida sin tocar a API-Football. |
| Cuota agotada por un bug (loop de reintentos) | `Budget` obligatorio en el cliente; test que lo cubra. |
| Nombres distintos entre fuentes | Fecha de nacimiento como clave principal y seed de overrides. |
| Licencias | Solo agregados en el reporte; raw privado en GCS y BigQuery; atribución en el README. |
| Ligas de Argentina con formato raro (Apertura/Clausura, zonas) | Verificar en el paso 0; modelar `round` y fase en `stg_af_fixtures`. |
