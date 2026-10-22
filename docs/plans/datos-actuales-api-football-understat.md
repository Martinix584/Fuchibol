# Plan: datos de la temporada actual (Understat + SofaScore; API-Football pendiente)

> Plan de trabajo para un agente que retome el proyecto. Está escrito para leerse de punta a punta
> antes de tocar código. Las secciones de **API-Football** siguen marcadas **VERIFICAR** porque
> requieren una API key y no se validaron contra el servicio real; la parte de **Understat y
> SofaScore ya está verificada e implementada**.
>
> **Estado (octubre 2026):** la parte de xG ya está implementada. Understat usa el endpoint JSON
> `GET /getLeagueData/{league}/{season}` (no el HTML embebido que suponía el plan original) y corre
> en el DAG diario `fuchibol_current_season`. Para Argentina se eligió **SofaScore**, opcional y
> local/manual, no API-Football. API-Football sigue pendiente: necesita una API key y no es
> necesario para xG. Ver `docs/runbooks/xg-manual-fallback.md` y `ingestion/understat.py`.
>
> **Actualización:** el modelo de valor de mercado ya no usa BigQuery ML; se entrena con
> scikit-learn (`ingestion/ml.py`). El resto del documento se deja como plan histórico.

## 1. Contexto

Fuchibol es un pipeline de punta a punta: **Python → GCS → BigQuery → dbt → BigQuery ML → Airflow → Power BI**.
Hoy tiene cuatro fuentes; las dos nuevas cubren la temporada en curso:

| Fuente | Qué trae | Problema |
|---|---|---|
| Transfermarkt ([transfermarkt-datasets](https://github.com/dcaribou/transfermarkt-datasets), CC0) | Jugadores, valores de mercado, transferencias, apariciones | Las actualizaciones están **pausadas desde el 6 de julio de 2026** |
| StatsBomb Open Data | Eventos con xG, xA, progresivos y presiones | Casi todo es **histórico** (torneos y temporadas puntuales) |
| Understat | xG, xA, npxG, xGChain, xGBuildup y xPts | Solo las 5 grandes ligas (**no** Argentina) |
| SofaScore | xG/xA por jugador | Argentina y respaldo manual; sin API pública |

El usuario quiere **datos actuales** de **las 5 grandes ligas + la Liga Profesional Argentina**. Se suman dos
fuentes:

| Fuente nueva | Para qué | Cobertura |
|---|---|---|
| **Understat** | xG, xA, npxG, xGChain, xGBuildup por jugador y xPts por equipo, temporada actual | Solo las 5 grandes ligas (**no** Argentina) |
| **SofaScore** | xG/xA por jugador de la temporada actual | Argentina; respaldo manual de las 5 grandes |

API-Football (estadísticas actuales no-xG) sigue en el plan como fase posterior; no es requisito para xG.

### Decisiones ya tomadas con el usuario (no rediscutir)

- Ligas: Premier League, La Liga, Serie A, Bundesliga, Ligue 1 y Liga Profesional Argentina.
- **Understat** es la fuente automática de xG de las 5 grandes; corre en Airflow a diario.
- **SofaScore** es la fuente de Argentina y el respaldo manual de las 5 grandes. Es local, opcional y **no**
  corre en Airflow: no tiene API pública.
- **No se mezclan fuentes de xG en una misma fila:** `mart_current_player_season` expone `xg_source` y el
  respaldo se activa a mano con `--vars '{xg_source_big5: sofascore}'`. No hay fallback automático.
- Plan **gratis** de API-Football mientras alcance: unas 100 requests por día y 10 por minuto. Si el plan
  gratis no deja pedir la temporada actual, se avisa al usuario: la alternativa es el plan Pro (unos USD 19 por
  mes, 7.500 requests por día). **No contratar nada sin su confirmación.**
- **Bajar una vez y guardar para siempre:** lo histórico se baja una vez, y la temporada en curso se actualiza
  de forma incremental (solo los partidos nuevos). La "base serverless" es **BigQuery**, que ya usa el proyecto:
  no hay que sumar otra base.
- Los datos crudos de API-Football, Understat y SofaScore **no se suben al repo** (licencias/ToS). En el reporte
  solo van agregados y métricas derivadas.

### Fuentes descartadas (y por qué; no volver a proponerlas)

- **FBref:** desde enero de 2026 ya no tiene xG, xA ni acciones progresivas (Opta le cortó el acceso), y
  Sports Reference no permite el scraping masivo. Fuente: <https://www.sports-reference.com/blog/2026/01/fbref-stathead-data-update/>
- **Scraping de Transfermarkt:** va contra sus términos. Se sigue usando el dataset CC0.
- **"SoccerData trae Transfermarkt y Capology":** es falso; la librería no incluye esas fuentes.
- **Opta o StatsBomb pagos:** fuera de presupuesto.

## 2. Prerrequisitos (del usuario; pedirlos si faltan)

La parte de xG ya implementada **no necesita API key**: Understat es público y SofaScore se corre
local con Playwright. Lo siguiente aplica a la fase pendiente de API-Football.

1. **API key de API-Football** (cuenta gratis en <https://dashboard.api-football.com>), cargada como **secreto del
   entorno** con el nombre `API_FOOTBALL_KEY`. Nunca en el chat, en el repo ni en logs.
2. **Red:** `understat.com` (ya verificado) y `www.sofascore.com` para la ingesta local. Para API-Football,
   agregar `v3.football.api-sports.io` en *Network access → Allowed domains* del entorno. Pasos:
   <https://code.claude.com/docs/en/cloud-environments#network-access>
3. En producción (Airflow), la key va como variable de entorno del contenedor (`.env`, que está en
   `.gitignore`) o como Airflow Variable o Connection. Documentarlo en `.env.example` **sin el valor**.

Si faltan la key o la red, **no inventes respuestas de la API.** Se puede avanzar con el código y con tests
sobre fixtures armadas a mano según la documentación, pero dejá claro en el PR que falta la validación real.

## 3. Paso 0: verificaciones (API-Football pendiente)

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
- [x] **Understat:** verificado. El endpoint es `GET /getLeagueData/{league}/{season}` con
  `X-Requested-With: XMLHttpRequest`; devuelve `{players, teams, dates}` y no hace falta parsear
  HTML. Nombres de liga: `EPL`, `La_liga`, `Bundesliga`, `Serie_A`, `Ligue_1`.
- [x] **Términos de Understat:** no se encontraron términos que prohíban el uso; se hacen 5 requests
  por día, con caché y espera entre ligas, y no se redistribuyen datos crudos. Implementado.

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
- **No trae xG ni xA por jugador.** Para eso están StatsBomb (histórico), Understat (5 grandes) y SofaScore
  (Argentina).

### Understat (**verificado e implementado**)

- Endpoint: `GET /getLeagueData/{league}/{season}` con `X-Requested-With: XMLHttpRequest`. Devuelve
  `{players, teams, dates}`.
- Jugadores: `id, player_name, games, time, goals, xG, assists, xA, shots, key_passes, yellow_cards,
  red_cards, position, team_title, npg, npxG, xGChain, xGBuildup`, casi todos como string.
- Equipos: `teams[id].history[]` por partido con `xG, xGA, npxG, npxGA, deep, ppda, xpts, result, date,
  scored, missed, pts`.
- `dates[]`: partidos con `goals` y `xG` de local/visitante.
- La temporada es el año de inicio (2026 → 2026/27).
- Verificado en octubre de 2026: EPL/2026 devolvió 449 jugadores.

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
Understat ──► ingestion/understat.py ──► GCS raw/understat/...   ──► BigQuery raw_understat
SofaScore ──► ingestion/sofascore.py  ──► GCS raw/sofascore/...  ──► BigQuery raw_sofascore
API-Football ──► ingestion/api_football.py ──► GCS raw/api_football/... ──► BigQuery raw_api_football
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

### 5.2 `ingestion/understat.py` (**implementado**)

- Endpoint real: `GET https://understat.com/getLeagueData/{league}/{season}` con `X-Requested-With:
  XMLHttpRequest` y User-Agent propio. Devuelve `{players, teams, dates}`; **no** hace falta parsear HTML.
- Una request por liga y temporada, con 2,5 segundos entre ligas y un manifest que evita repetir la misma
  liga dentro de las 6 horas. La temporada es el año de inicio (2026 → 2026/27).
- Raw: `players_season`, `team_matches` (flatten de `teams[].history`) y `matches`.
- Si Understat cambia el endpoint o el formato, la ingesta falla de forma ruidosa; no hay fallback automático.

### 5.3 SofaScore (`ingestion/sofascore.py`, **implementado**)

- No tiene API pública: es **local/manual**,
  nunca en Airflow.
- Playwright (import perezoso) abre la web, hace `fetch` same-origin y baja temporada, `top-players`,
  equipos/plantillas y, en modo `full`, una request por jugador con minutos. Rate limit 3 s + jitter,
  presupuesto de 1000 requests y manifest reanudable.
- Argentina usa `full` por defecto; el respaldo de las 5 grandes usa `top` (sin minutos).
- Raw: `seasons` y `player_season`. El staging prefiere `full` sobre `top`.

### 5.4 Airflow (**implementado**)

- DAG diario `dags/fuchibol_current_season.py` (07:00 UTC): `current_ensure_tables` → `understat_fetch` →
  `dbt build --select tag:current+`.
- `current_ensure_tables` crea también las tablas vacías de SofaScore para que dbt pueda referenciar ambos
  sources antes de la primera corrida manual.
- El DAG semanal `fuchibol_pipeline` ahora excluye `tag:current` (`--exclude tag:current`).
- API-Football no se implementó: requiere API key y no es necesario para xG. Queda como fase posterior.

### 5.4 dbt (**implementado para xG**)

Carpetas nuevas: `models/staging/understat`, `models/staging/sofascore`,
`models/intermediate/current`, `models/marts/current`. Los modelos llevan `tags=['current']`
en su `config()` y el DAG semanal los excluye.

| Modelo | Grano | Contenido |
|---|---|---|
| `stg_us_players_season` | jugador Understat × liga × temporada | xG, xA, npxG, xGChain, xGBuildup… |
| `stg_us_team_matches` | equipo × partido | xG, xGA, xpts, pts, ppda |
| `stg_us_matches` | partido | goles y xG de cada lado |
| `stg_ss_seasons` | liga × temporada SofaScore | temporada elegida (Apertura/Clausura) |
| `stg_ss_player_season` | jugador × temporada SofaScore | xG/xA, minutos (full) o totales (top) |
| `int_us_player_season` | jugador × liga × temporada | métricas cada 90 y goles - xG |
| `int_us_team_season` | equipo × liga × temporada | puntos reales vs. xPts |
| `int_ss_player_season` | jugador × temporada SofaScore | métricas cada 90 (null en modo top) |
| `mart_current_player_season` | jugador × liga × temporada actual | Understat o SofaScore, con `xg_source` |
| `mart_current_team_table` | equipo × liga actual | puntos, xG, xPts (solo Understat) |

**Regla de fuentes:** las 5 grandes usan Understat por defecto; Argentina usa SofaScore. El var
`xg_source_big5` (default `understat`) permite el respaldo manual `sofascore`. El test
`assert_current_xg_source` verifica que no se mezclen fuentes. No hay fallback automático.

**API-Football (pendiente):** cuando se implemente, sus modelos van en `models/staging/api_football`
y se cruzan con Transfermarkt por fecha de nacimiento + nombre normalizado. No es necesario para
xG y requiere API key.

**Convenciones SQL del repo** (respetalas): BigQuery; `{{ to_int(...) }}` para enteros que pueden llegar como
string o float; `where true` antes de un `qualify` que no tenga `WHERE` ni `GROUP BY`; nada de `select *` en marts
salvo que esté justificado; comentarios en español dentro de `{# #}`; nombres en inglés y `snake_case`.

### 5.5 Power BI y README (**implementado**)

- `powerbi/README.md`: página **"Temporada actual"** con `mart_current_player_season` (xG, xA, npxG,
  goles - xG, `xg_source` como leyenda) y `mart_current_team_table` (puntos vs. xPts). Argentina usa
  SofaScore y no tiene xPts de equipo en esta versión.
- `README.md`: fuentes, diagrama, DAG diario, comandos de Understat/SofaScore y
  métricas de tests actualizadas.
- Exposure de Power BI (`dbt/models/exposures.yml`): incluye los dos marts nuevos.

## 6. Tests y validación (antes de cada push)

```bash
ruff check ingestion dags tests scripts && ruff format --check ingestion dags tests scripts
pytest -q
(cd dbt && dbt parse --profiles-dir .)
scripts/smoke.sh --matches 8          # smoke actual: no debe romperse
scripts/test_dag.sh                   # sumar los escenarios del DAG nuevo
```

- **pytest** para todo lo puro: De Understat se testea `default_season`, `resolve_leagues`, el parser de
  `players/teams/dates` y la frescura del manifest. De SofaScore, `resolve_scope`, `select_season`, el merge de
  `top-players`, `player_stats_row`, `season_teams`/`roster_players`, el manifest y que el módulo importe sin
  Playwright. Usá **fixtures chicas armadas a mano** con la estructura real. **No subas respuestas reales completas.**
- **Smoke test:** `tests/smoke/synthetic_current_season.py` genera filas de Understat y SofaScore (incluida una
  fila `top` vieja y una `full` nueva del mismo jugador) para que todos los modelos corran en DuckDB.
- **DAG:** el test del DAG sigue cubriendo la rama histórica; el DAG nuevo es una cadena lineal y se valida con
  `dbt parse`/smoke. Si se agregan escenarios, usar `dag.test()` en `tests/dags/`.
- **Validación real:** Understat se verificó contra la temporada 2026/27 (por ejemplo, EPL devolvió 449
  jugadores). SofaScore se verificó contra Argentina (`season_id=87913`); con red y key, API-Football se validará
  con `API_FOOTBALL_DAILY_BUDGET=10` cuando se implemente.

## 7. Orden de trabajo (estado)

1. **Hecho:** Understat (endpoint JSON, ingesta, esquemas, dbt staging/intermediate/marts, DAG diario).
2. **Hecho:** SofaScore local/manual para Argentina (Playwright, modo full, manifest, runbook).
3. **Hecho:** marts de temporada actual con `xg_source`, respaldo manual `xg_source_big5`, smoke, tests,
   README, Power BI y exposure.
4. **Pendiente:** API-Football (`/leagues`, `/fixtures`, `/players`, `/fixtures/players`), cruce con
   Transfermarkt por fecha de nacimiento y métricas no-xG. Requiere API key y validación real.
5. **Opcional:** xPts de Argentina con un modelo Poisson propio; hoy `mart_current_team_table` es solo Understat.

Cada PR: CI en verde, descripción con lo verificado y lo que falta, y sin datos crudos ni secretos.

## 8. Criterios de aceptación

- [x] xG y xA actuales de Understat para las 5 grandes, con `xg_source`.
- [x] Argentina con xG/xA de SofaScore, sin mezclar fuentes; xPts de equipo queda pendiente.
- [x] Reprocesar no duplica nada (staging con la última ingesta; `full` gana sobre `top`).
- [x] CI en verde (lint, pytest, dbt parse, smoke) y README/Power BI actualizados.
- [x] Ningún secreto ni dato crudo en el repo.
- [ ] API-Football: totales y backfill por partido con el plan gratis, sin pasarse del presupuesto.
- [ ] Tasa de cruce AF → Transfermarkt reportada por liga (objetivo orientativo: > 85 % en las 5 grandes).

## 9. Riesgos y qué hacer

| Riesgo | Qué hacer |
|---|---|
| El plan gratis no da la temporada actual | Frenar y avisar al usuario (opción: plan Pro). No usar temporadas viejas como si fueran actuales. |
| Cambia el formato de Understat | Parser aislado y tests; si se rompe, el DAG marca la rama como fallida sin tocar a API-Football. |
| Cuota agotada por un bug (loop de reintentos) | `Budget` obligatorio en el cliente; test que lo cubra. |
| Nombres distintos entre fuentes | Fecha de nacimiento como clave principal y seed de overrides. |
| Licencias | Solo agregados en el reporte; raw privado en GCS y BigQuery; atribución en el README. |
| Ligas de Argentina con formato raro (Apertura/Clausura, zonas) | Verificar en el paso 0; modelar `round` y fase en `stg_af_fixtures`. |
