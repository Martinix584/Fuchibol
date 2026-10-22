# Runbook: xG de la temporada actual y respaldo manual de SofaScore

## Qué corre solo y qué no

| Liga | Fuente automática | Dónde corre |
|---|---|---|
| Premier League, La Liga, Serie A, Bundesliga, Ligue 1 | **Understat** | DAG diario `fuchibol_current_season` (07:00 UTC) |
| Liga Profesional Argentina | **SofaScore** | Local/manual, con Playwright |
| Respaldo de las 5 grandes | **SofaScore** | Local/manual, solo si Understat falla |

Understat es la fuente principal de xG de las 5 grandes. SofaScore **no** corre en Airflow: no tiene API
pública y su sesión puede pedir un captcha. La ingesta es opcional, de bajo volumen y queda fuera del
repo (no se versiona el raw).

## Preparación (una sola vez)

```bash
make setup-sofascore          # instala Playwright y Chromium en .venv
source .venv/bin/activate    # opcional: el Makefile ya usa .venv/bin/python y .venv/bin/dbt
cp .env.example .env          # completá GCP_PROJECT_ID, GCS_BUCKET, etc.
set -a && source .env && set +a
```

Los comandos de Python cargan solos el `.env` de la raíz (vía `python-dotenv`) sin pisar variables ya
exportadas. Las tareas de dbt no pasan por `ingestion`, así que ahí sí necesitás el `source .env`.

Si preferís usar el Chrome del sistema, no hace falta `playwright install chromium`: el cliente intenta
`channel="chrome"` primero y, si no está, usa el Chromium de Playwright.

## Verificar la sesión

```bash
make sofascore                # equivale a python -m ingestion.sofascore --scope ARG --mode full --headful
# o solo verificar la sesión y la temporada:
PYTHONPATH=. .venv/bin/python -m ingestion.sofascore --scope ARG --check --headful
```

Debe imprimir el `season_id` y el nombre de la temporada actual (por ejemplo, `Primera LPF 2026`). Si ves
`403/challenge` o un captcha de Cloudflare:

1. Volvé a correr con `--headful`: la ventana queda abierta en el captcha y el proceso espera a que lo
   resuelvas (300 segundos por defecto; se cambia con `SOFASCORE_CAPTCHA_TIMEOUT_S`).
2. No recargues ni cierres esa ventana mientras espera.
3. No reduzcas la espera entre requests: por defecto son 3 segundos (con jitter) y 1000 requests por corrida.

## Argentina (flujo normal)

```bash
# Baja la temporada actual completa: top-players + plantillas + una request por jugador.
make sofascore

# Reconstruye los marts de la temporada actual (requiere el .env exportado).
make dbt-current
```

El resultado queda en `raw_sofascore.player_season` y se ve en `marts.mart_current_player_season` con
`xg_source = 'sofascore'`. El staging prefiere las filas `full` sobre las `top`, así que podés empezar con
`--mode top` y completar después sin duplicar.

### Si se corta a mitad de camino

El manifest `manifests/sofascore.json` guarda cada jugador ya bajado. Volvé a correr el mismo comando:
saltea los que están frescos (6 horas por defecto) y sigue donde quedó. Para forzar todo:

```bash
python -m ingestion.sofascore --scope ARG --mode full --force --headful
```

## Respaldo manual de las 5 grandes

Solo si Understat no está disponible y aceptás el riesgo de SofaScore. **No hay cambio automático de
fuente**: los modelos de xG de Understat y SofaScore no son comparables, así que la serie se corta.

```bash
# 1. Bajar xG/xA de las 5 grandes (modo top: no pide minutos, menos requests).
python -m ingestion.sofascore --scope big5 --mode top --force --headful

# 2. Construir los marts eligiendo SofaScore para las 5 grandes.
cd dbt
dbt build --profiles-dir . \
  --vars '{xg_source_big5: sofascore}' \
  --select tag:current+
```

Para volver a Understat, simplemente corré el DAG diario o:

```bash
cd dbt
dbt build --profiles-dir . --select tag:current+
```

El default de `xg_source_big5` es `understat`. El test `assert_current_xg_source` verifica que Argentina
sea siempre SofaScore y que las 5 grandes usen la fuente elegida.

## Limitaciones y advertencias

- **Argentina no tiene xPts** en esta versión: SofaScore se usa para xG/xA por jugador, no para una tabla
  de equipos. `mart_current_team_table` sigue siendo Understat. Calcular xPts para Argentina requiere un
  modelo Poisson propio (o eventos de SofaScore), que es un paso separado.
- En modo `top`, `minutes` y las métricas cada 90 quedan null; los totales de xG/xA sí están.
- SofaScore puede cambiar sus endpoints o su challenge sin aviso. Si la ingesta falla, el pipeline
  histórico y Understat siguen funcionando.
- Este runbook es para uso local, manual y de bajo volumen; no publiques el raw ni lo pongas en un servicio.
- Understat tampoco es una API oficial: si cambia el endpoint, `ingestion/understat.py` falla de forma
  ruidosa y el DAG diario queda en rojo (los marts conservan la última carga).
