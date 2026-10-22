# Runbook: xG de la temporada actual y respaldo manual de SofaScore

## Qué corre solo y qué no

| Liga | Fuente automática | Dónde corre |
|---|---|---|
| Premier League, La Liga, Serie A, Bundesliga, Ligue 1 | **Understat** | DAG diario `fuchibol_current_season` (07:00 UTC) |
| Liga Profesional Argentina | **SofaScore** | Local/manual, con Playwright |
| Respaldo de las 5 grandes | **SofaScore** | Local/manual, solo si Understat falla |

Understat es la fuente principal de xG de las 5 grandes. SofaScore **no** corre en Airflow: no tiene API
pública, sus términos prohíben el scraping/agregación sin consentimiento y su sesión puede pedir un
captcha. La ingesta es opcional, de bajo volumen y queda fuera del repo (no se versiona el raw).

## Preparación (una sola vez)

```bash
make setup-sofascore          # instala Playwright y Chromium en .venv
source .venv/bin/activate
cp .env.example .env          # completá GCP_PROJECT_ID, GCS_BUCKET, etc.
set -a && source .env && set +a
```

Si preferís usar el Chrome del sistema, no hace falta `playwright install chromium`: el cliente intenta
`channel="chrome"` primero y, si no está, usa el Chromium de Playwright.

## Verificar la sesión

```bash
python -m ingestion.sofascore --scope ARG --check --headful
```

Debe imprimir el `season_id` y el nombre de la temporada actual (por ejemplo, `Primera LPF 2026`). Si ves
`403/challenge`:

1. Volvé a correr con `--headful` y esperá unos segundos.
2. Si aparece un captcha, resolvelo en la ventana del navegador.
3. No reduzcas la espera entre requests: por defecto son 3 segundos (con jitter) y 1000 requests por corrida.

## Argentina (flujo normal)

```bash
# Baja la temporada actual completa: top-players + plantillas + una request por jugador.
python -m ingestion.sofascore --scope ARG --mode full --headful

# Reconstruye los marts de la temporada actual.
cd dbt
dbt build --profiles-dir . --select tag:current+
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
- Los términos de SofaScore prohíben el scraping/agregación sin consentimiento. Este runbook es para uso
  local, manual y de bajo volumen; no publiques el raw ni lo pongas en un servicio.
- Understat tampoco es una API oficial: si cambia el endpoint, `ingestion/understat.py` falla de forma
  ruidosa y el DAG diario queda en rojo (los marts conservan la última carga).
