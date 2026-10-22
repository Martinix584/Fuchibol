"""SofaScore: xG/xA de la Liga Profesional Argentina y respaldo manual de las 5 grandes.

SofaScore no tiene API pública. Sus endpoints internos devuelven `403 challenge` si se
los llama con HTTP directo, así que este módulo abre un navegador real con Playwright y
hace `fetch` desde la misma página. Es una herramienta **local/manual**: no se ejecuta en
Airflow ni agrega Playwright a la imagen de producción.

La fuente recomendada para las 5 grandes sigue siendo Understat. SofaScore se usa:
  - siempre para Argentina (`--scope ARG`);
  - como respaldo manual de las 5 grandes (`--scope big5 --mode top`).

Flujo:
  1. Abre el navegador y resuelve la sesión (si hay challenge, reintenta o pide headful).
  2. Baja la temporada actual, los equipos/jugadores de `top-players`, las plantillas y,
     en modo full, una request por jugador para obtener minutos y estadísticas completas.
  3. Guarda NDJSON.gz en GCS y lo agrega a BigQuery (raw_sofascore). El staging de dbt
     se queda con la última ingesta y prefiere las filas `full` sobre las `top`.

Requisitos (solo local):
    pip install -r requirements-sofascore.txt
    python -m playwright install chromium     # o usar Chrome del sistema
    python -m ingestion.sofascore --scope ARG --check
    python -m ingestion.sofascore --scope ARG --mode full
    python -m ingestion.sofascore --scope big5 --mode top --force

Este módulo es opcional, manual y de bajo volumen; no se publica el raw.
Ver docs/runbooks/xg-manual-fallback.md.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from ingestion import bq, config, storage

log = logging.getLogger(__name__)

TABLE_SPECS = [
    {
        "dataset": config.BQ_SOFASCORE_DATASET,
        "table": "seasons",
        "schema": "sofascore_seasons",
        "cluster_fields": ["league_code", "season_id"],
    },
    {
        "dataset": config.BQ_SOFASCORE_DATASET,
        "table": "player_season",
        "schema": "sofascore_player_season",
        "cluster_fields": ["league_code", "season_id"],
    },
]

# category de top-players -> columna del schema
CATEGORY_FIELDS = {
    "rating": "rating",
    "goals": "goals",
    "expectedGoals": "expected_goals",
    "assists": "assists",
    "expectedAssists": "expected_assists",
    "totalShots": "shots",
    "shotsOnTarget": "shots_on_target",
    "keyPasses": "key_passes",
    "penaltyGoals": "penalty_goals",
    "yellowCards": "yellow_cards",
    "redCards": "red_cards",
}

STATS_FIELDS = {
    "minutesPlayed": "minutes",
    "goals": "goals",
    "assists": "assists",
    "totalShots": "shots",
    "shotsOnTarget": "shots_on_target",
    "keyPasses": "key_passes",
    "penaltyGoals": "penalty_goals",
    "yellowCards": "yellow_cards",
    "redCards": "red_cards",
    "rating": "rating",
    "expectedGoals": "expected_goals",
    "expectedAssists": "expected_assists",
    "expectedGoalsOnTarget": "expected_goals_on_target",
}

INT_FIELDS = {
    "goals",
    "assists",
    "shots",
    "shots_on_target",
    "key_passes",
    "penalty_goals",
    "yellow_cards",
    "red_cards",
    "appearances",
}


class SofaScoreError(RuntimeError):
    """Error genérico de SofaScore."""


class SofaScoreBlocked(SofaScoreError):
    """SofaScore devolvió 403/challenge: hay que abrir el navegador en modo headful."""


class SofaScoreNotFound(SofaScoreError):
    """El recurso no existe (por ejemplo, un jugador sin estadísticas)."""


class BudgetExhausted(SofaScoreError):
    """Se alcanzó el presupuesto de requests de la corrida."""


# ---------------------------------------------------------------- utilidades puras


def parse_number(value, cast=float):
    if value is None or value == "":
        return None
    try:
        return cast(value)
    except (TypeError, ValueError):
        return None


def resolve_scope(scope: str | None = None) -> list[str]:
    """Traduce "ARG", "big5", "all" o una lista separada por comas a códigos."""
    scope = scope or config.SOFASCORE_SCOPE
    codes: list[str] = []
    for name in (s.strip() for s in scope.split(",") if s.strip()):
        if name == "all":
            codes += list(config.SOFASCORE_TOURNAMENTS)
        elif name == "big5":
            codes += [code for code in config.SOFASCORE_TOURNAMENTS if code != "ARG"]
        elif name in config.SOFASCORE_TOURNAMENTS:
            codes.append(name)
        else:
            raise ValueError(
                f"Torneo desconocido: {name}. Opciones: ARG, big5, all, "
                f"{', '.join(config.SOFASCORE_TOURNAMENTS)}"
            )
    return [code for code in config.SOFASCORE_TOURNAMENTS if code in set(codes)]


def mode_for(code: str, mode: str | None = None) -> str:
    """ARG usa full por defecto; el respaldo de las 5 grandes usa top (menos requests)."""
    mode = mode or config.SOFASCORE_MODE or ("full" if code == "ARG" else "top")
    if mode not in ("top", "full"):
        raise ValueError(f"Modo desconocido: {mode}. Usá top o full.")
    return mode


def select_season(payload: dict, wanted: str | int | None = None) -> dict:
    """Elige la temporada pedida (año o id) o la más reciente."""
    seasons = payload.get("seasons") or []
    if not seasons:
        raise ValueError("SofaScore no devolvió temporadas")
    if wanted is not None and str(wanted) != "":
        matches = [s for s in seasons if str(s.get("year")) == str(wanted) or str(s.get("id")) == str(wanted)]
        if not matches:
            raise ValueError(f"No encontré la temporada {wanted}")
        seasons = matches
    return max(seasons, key=lambda s: (parse_number(s.get("year"), int) or 0, int(s.get("id") or 0)))


def season_rows(
    payload: dict, league_code: str, league_name: str, selected_id: int, ingested_at: str
) -> list[dict]:
    rows = []
    for season in payload.get("seasons") or []:
        rows.append(
            {
                "league_code": league_code,
                "league_name": league_name,
                "season_id": parse_number(season.get("id"), int),
                "season_name": season.get("name"),
                "year": str(season.get("year")) if season.get("year") is not None else None,
                "is_selected": parse_number(season.get("id"), int) == selected_id,
                "_ingested_at": ingested_at,
            }
        )
    return rows


def _category_value(stats: dict, category: str):
    value = stats.get(category)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        return parse_number(value)
    if isinstance(value, dict):
        for key in ("value", "total", "statistic"):
            if key in value:
                return parse_number(value[key])
    return None


def top_players_rows(
    payload: dict, league_code: str, league_name: str, season: dict, ingested_at: str
) -> list[dict]:
    """Une las categorías de `top-players/overall` en una fila por jugador.

    En modo top no hay minutos: se guardan xG/xA y el resto de las categorías. El
    `appearances` viene en la categoría de rating y se conserva.
    """
    season_id = parse_number(season.get("id"), int)
    season_name = season.get("name")
    season_year = parse_number(season.get("year"), int)
    merged: dict[int, dict] = {}

    for category, entries in (payload.get("topPlayers") or {}).items():
        for entry in entries or []:
            player = entry.get("player") or {}
            player_id = parse_number(player.get("id"), int)
            if player_id is None:
                continue
            row = merged.setdefault(
                player_id,
                {
                    "league_code": league_code,
                    "league_name": league_name,
                    "season_id": season_id,
                    "season_name": season_name,
                    "season_year": season_year,
                    "player_id": player_id,
                    "player_name": player.get("name"),
                    "team_id": parse_number((entry.get("team") or {}).get("id"), int),
                    "team_name": (entry.get("team") or {}).get("name"),
                    "position": player.get("position"),
                    "source_mode": "top",
                    "appearances": None,
                    "minutes": None,
                    "goals": None,
                    "assists": None,
                    "shots": None,
                    "shots_on_target": None,
                    "key_passes": None,
                    "penalty_goals": None,
                    "yellow_cards": None,
                    "red_cards": None,
                    "rating": None,
                    "expected_goals": None,
                    "expected_assists": None,
                    "expected_goals_on_target": None,
                    "_raw": {},
                },
            )
            stats = entry.get("statistics") or {}
            appearances = parse_number(stats.get("appearances"), int)
            if appearances is not None:
                row["appearances"] = appearances
            if category in CATEGORY_FIELDS:
                field = CATEGORY_FIELDS[category]
                value = _category_value(stats, category)
                if value is not None:
                    row[field] = int(value) if field in INT_FIELDS else value
                row["_raw"][category] = value
            # completa datos de equipo/nombre si la primera categoría no los traía
            row["team_id"] = row["team_id"] or parse_number((entry.get("team") or {}).get("id"), int)
            row["team_name"] = row["team_name"] or (entry.get("team") or {}).get("name")

    rows = []
    for player_id in sorted(merged):
        row = merged[player_id]
        raw = row.pop("_raw")
        row["raw"] = json.dumps(raw, ensure_ascii=False, sort_keys=True)
        row["_ingested_at"] = ingested_at
        rows.append(row)
    return rows


def player_stats_row(
    payload: dict,
    league_code: str,
    league_name: str,
    season: dict,
    top_row: dict,
    ingested_at: str,
) -> dict:
    """Convierte `/player/{id}/.../statistics/overall` en una fila full."""
    stats = payload.get("statistics") or payload
    row = {
        "league_code": league_code,
        "league_name": league_name,
        "season_id": parse_number(season.get("id"), int),
        "season_name": season.get("name"),
        "season_year": parse_number(season.get("year"), int),
        "player_id": top_row["player_id"],
        "player_name": top_row.get("player_name"),
        "team_id": top_row.get("team_id"),
        "team_name": top_row.get("team_name"),
        "position": top_row.get("position"),
        "source_mode": "full",
        "appearances": top_row.get("appearances"),
        "minutes": top_row.get("minutes"),
        "goals": top_row.get("goals"),
        "assists": top_row.get("assists"),
        "shots": top_row.get("shots"),
        "shots_on_target": top_row.get("shots_on_target"),
        "key_passes": top_row.get("key_passes"),
        "penalty_goals": top_row.get("penalty_goals"),
        "yellow_cards": top_row.get("yellow_cards"),
        "red_cards": top_row.get("red_cards"),
        "rating": top_row.get("rating"),
        "expected_goals": top_row.get("expected_goals"),
        "expected_assists": top_row.get("expected_assists"),
        "expected_goals_on_target": top_row.get("expected_goals_on_target"),
        "raw": json.dumps(stats, ensure_ascii=False, sort_keys=True),
        "_ingested_at": ingested_at,
    }
    for source, field in STATS_FIELDS.items():
        value = parse_number(stats.get(source))
        if value is not None:
            row[field] = int(value) if field in INT_FIELDS else value
    appearances = parse_number(stats.get("appearances"), int)
    if appearances is not None:
        row["appearances"] = appearances
    return row


def season_teams(payload: dict) -> list[dict]:
    """Extrae los equipos de `/unique-tournament/{id}/season/{id}/teams`.

    La respuesta puede venir como `teams[]`, como `groups[].teams[]` o con el equipo
    anidado en `team`. Devolvemos una lista sin duplicados.
    """
    entries = list(payload.get("teams") or [])
    for group in payload.get("groups") or []:
        entries += list(group.get("teams") or [])

    teams: dict[int, dict] = {}
    for entry in entries:
        team = entry.get("team") or entry
        team_id = parse_number(team.get("id"), int)
        if team_id is None:
            continue
        teams[team_id] = {"team_id": team_id, "team_name": team.get("name")}
    return list(teams.values())


def roster_players(payload: dict, team_id: int, team_name: str | None) -> list[dict]:
    """Extrae la plantilla de `/team/{teamId}/players` como filas base.

    No se cargan como filas `top`: solo sirven para saber qué jugadores pedir en modo
    full. La fila final la arma `player_stats_row` con las estadísticas reales.
    """
    rows = []
    for entry in payload.get("players") or []:
        player = entry.get("player") or entry
        player_id = parse_number(player.get("id"), int)
        if player_id is None:
            continue
        team = entry.get("team") or {}
        resolved_team_id = parse_number(team.get("id"), int)
        if resolved_team_id is None:
            resolved_team_id = team_id
        stats = entry.get("statistics") or {}
        rows.append(
            {
                "player_id": player_id,
                "player_name": player.get("name"),
                "team_id": resolved_team_id,
                "team_name": team.get("name") or team_name,
                "position": player.get("position"),
                "appearances": parse_number(stats.get("appearances"), int),
            }
        )
    return rows


def manifest_key(code: str, season_id: int, player_id: int) -> str:
    return f"{code}:{season_id}:{player_id}"


def is_fresh(manifest: dict, key: str) -> bool:
    entry = (manifest.get("players") or {}).get(key) or {}
    fetched_at = entry.get("fetched_at")
    if not fetched_at:
        return False
    try:
        fetched = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    return datetime.now(UTC) - fetched < timedelta(hours=config.SOFASCORE_REFRESH_HOURS)


def gcs_object_name(table: str, league_code: str, season_id: int, ingest_date: str, part: str) -> str:
    return (
        f"{config.GCS_SOFASCORE_PREFIX}/{table}/league={league_code}/season_id={season_id}/"
        f"ingest_date={ingest_date}/part={part}/{table}.ndjson.gz"
    )


# ---------------------------------------------------------------- navegador


class SofaScoreClient:
    """Navegador Playwright con fetch same-origin a los endpoints internos de SofaScore."""

    def __init__(self, headless: bool = True, profile_dir: str | None = None):
        self.headless = headless
        self.profile_dir = Path(profile_dir or config.SOFASCORE_PROFILE_DIR)
        self.requests = 0
        self._last_request = 0.0
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None

    def __enter__(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - depende del entorno local
            raise RuntimeError(
                "Falta Playwright. Instalá requirements-sofascore.txt y ejecutá "
                "`python -m playwright install chromium`."
            ) from exc

        self.profile_dir.mkdir(parents=True, exist_ok=True)
        state_file = self.profile_dir / "state.json"
        try:
            self._pw = sync_playwright().start()
        except Exception as exc:  # noqa: BLE001 - Playwright puede fallar por binarios faltantes
            raise RuntimeError(
                "No se pudo iniciar Playwright. Revisá la instalación de requirements-sofascore.txt "
                "y ejecutá `python -m playwright install chromium`."
            ) from exc
        try:
            launch_args = {"headless": self.headless, "args": ["--no-sandbox"]}
            try:
                self._browser = self._pw.chromium.launch(channel="chrome", **launch_args)
            except Exception:  # noqa: BLE001 - si no hay Chrome, usa el Chromium de Playwright
                self._browser = self._pw.chromium.launch(**launch_args)

            self._context = self._browser.new_context(
                user_agent=config.UNDERSTAT_USER_AGENT + " SofaScore",
                locale="es-AR",
                timezone_id="America/Argentina/Buenos_Aires",
                viewport={"width": 1366, "height": 900},
                storage_state=str(state_file) if state_file.exists() else None,
            )
            self._page = self._context.new_page()
            self._page.goto(config.SOFASCORE_HOME_URL, wait_until="domcontentloaded", timeout=60_000)
            self._page.wait_for_timeout(3_000)
            self.ensure_session()
        except Exception:
            self.close()
            raise
        return self

    def ensure_session(self) -> None:
        """Verifica que la sesión no esté en challenge; recarga hasta 3 veces."""
        last_error = None
        for attempt in range(3):
            try:
                self._fetch_raw(f"/unique-tournament/{config.SOFASCORE_TOURNAMENTS['ARG']['id']}/seasons")
                return
            except SofaScoreBlocked as exc:
                last_error = exc
                self._page.reload(wait_until="domcontentloaded", timeout=60_000)
                self._page.wait_for_timeout(4_000 + attempt * 3_000)
        raise SofaScoreBlocked(
            "SofaScore sigue devolviendo challenge. Probá con --headful, esperá unos minutos "
            "o resolvé el captcha en la ventana del navegador."
        ) from last_error

    def _fetch_raw(self, path: str) -> dict:
        result = self._page.evaluate(
            """
            async (url) => {
              const controller = new AbortController();
              const timer = setTimeout(() => controller.abort(), 30000);
              try {
                const response = await fetch(url, {
                  headers: {
                    "Accept": "application/json",
                    "X-Requested-With": "XMLHttpRequest"
                  },
                  credentials: "include",
                  signal: controller.signal
                });
                return { status: response.status, body: await response.text() };
              } finally {
                clearTimeout(timer);
              }
            }
            """,
            path,
        )
        status, body = result["status"], result["body"]
        if status == 403 or '"challenge"' in body or body.lstrip().startswith("<"):
            raise SofaScoreBlocked(f"SofaScore 403/challenge en {path}")
        if status == 404:
            raise SofaScoreNotFound(f"SofaScore 404 en {path}")
        if status != 200:
            raise SofaScoreError(f"SofaScore {status} en {path}: {body[:200]}")
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise SofaScoreError(f"SofaScore devolvió HTML/JSON inválido en {path}") from exc

    def get(self, path: str) -> dict:
        if self.requests >= config.SOFASCORE_DAILY_BUDGET:
            raise BudgetExhausted(
                f"Se alcanzó SOFASCORE_DAILY_BUDGET={config.SOFASCORE_DAILY_BUDGET}. "
                "El progreso quedó en el manifest; volvé a correr mañana o subí el límite."
            )
        wait = self._last_request + config.SOFASCORE_RATE_LIMIT_S * random.uniform(0.85, 1.15)
        delay = wait - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        self._last_request = time.monotonic()
        self.requests += 1
        try:
            return self._fetch_raw(path)
        except SofaScoreBlocked:
            self.ensure_session()
            return self._fetch_raw(path)

    def close(self) -> None:
        try:
            if self._context is not None:
                try:
                    self._context.storage_state(path=str(self.profile_dir / "state.json"))
                except Exception:  # noqa: BLE001 - guardar la sesión es best-effort
                    pass
        finally:
            for obj in (self._context, self._browser):
                if obj is not None:
                    try:
                        obj.close()
                    except Exception:  # noqa: BLE001
                        pass
            if self._pw is not None:
                try:
                    self._pw.stop()
                except Exception:  # noqa: BLE001
                    pass

    def __exit__(self, *exc):
        self.close()


# ---------------------------------------------------------------- ingesta


def _now() -> str:
    return datetime.now(UTC).isoformat()


def save_manifest(manifest: dict) -> None:
    storage.update_manifest(config.SOFASCORE_MANIFEST_BLOB, manifest)


def _flush_player_rows(rows: list[dict], code: str, season_id: int, ingest_date: str, part: str) -> dict:
    if not rows:
        return {
            "table": f"{config.BQ_SOFASCORE_DATASET}.player_season[{code}/{season_id}]",
            "rows": 0,
            "bytes": 0,
            "extract_seconds": None,
            "load_seconds": 0.0,
        }
    return bq.upload_and_load(
        rows,
        gcs_object_name("player_season", code, season_id, ingest_date, part),
        config.BQ_SOFASCORE_DATASET,
        "player_season",
        "sofascore_player_season",
        TABLE_SPECS[1]["cluster_fields"],
    )


def ingest_tournament(
    client: SofaScoreClient,
    code: str,
    season_arg: str | int | None,
    mode: str,
    force: bool,
    limit: int | None,
    manifest: dict,
    ingest_date: str,
) -> list[dict]:
    tournament = config.SOFASCORE_TOURNAMENTS[code]
    tournament_id = tournament["id"]
    seasons_payload = client.get(f"/unique-tournament/{tournament_id}/seasons")
    season = select_season(seasons_payload, season_arg)
    season_id = int(season["id"])
    sname = season.get("name")
    ingested_at = _now()

    results = [
        bq.upload_and_load(
            season_rows(seasons_payload, code, tournament["name"], season_id, ingested_at),
            gcs_object_name("seasons", code, season_id, ingest_date, "all"),
            config.BQ_SOFASCORE_DATASET,
            "seasons",
            "sofascore_seasons",
            TABLE_SPECS[0]["cluster_fields"],
        )
    ]

    top_payload = client.get(f"/unique-tournament/{tournament_id}/season/{season_id}/top-players/overall")
    all_top_rows = top_players_rows(top_payload, code, tournament["name"], season, ingested_at)
    top_rows = all_top_rows[:limit] if limit is not None else all_top_rows
    results.append(_flush_player_rows(top_rows, code, season_id, ingest_date, "top"))
    log.info("SofaScore %s/%s (%s): %d jugadores en top-players", code, sname, season_id, len(top_rows))

    if mode == "full":
        # Para tener minutos de toda la liga (no solo del top), armamos la lista de
        # jugadores con las plantillas. Si falla, seguimos con el top: es un fallback
        # parcial, no un cambio de fuente.
        candidates = {row["player_id"]: row for row in all_top_rows}
        try:
            teams_payload = client.get(f"/unique-tournament/{tournament_id}/season/{season_id}/teams")
            teams = season_teams(teams_payload)
        except SofaScoreNotFound:
            teams = []
            log.warning("SofaScore %s/%s: no encontré equipos; uso solo top-players", code, season_id)
        for team in teams:
            try:
                roster_payload = client.get(f"/team/{team['team_id']}/players")
            except SofaScoreNotFound:
                continue
            for row in roster_players(roster_payload, team["team_id"], team["team_name"]):
                candidates.setdefault(row["player_id"], row)

        full_candidates = list(candidates.values())
        if limit is not None:
            full_candidates = full_candidates[:limit]

        pending: list[dict] = []
        batch = 0
        processed = 0
        try:
            for top_row in full_candidates:
                player_id = top_row["player_id"]
                key = manifest_key(code, season_id, player_id)
                if not force and is_fresh(manifest, key):
                    continue
                path = (
                    f"/player/{player_id}/unique-tournament/{tournament_id}/season/{season_id}"
                    f"/statistics/overall"
                )
                try:
                    stats_payload = client.get(path)
                except SofaScoreNotFound:
                    log.info("SofaScore: %s no tiene estadísticas en %s/%s", player_id, code, season_id)
                    continue
                pending.append(
                    player_stats_row(stats_payload, code, tournament["name"], season, top_row, _now())
                )
                manifest.setdefault("players", {})[key] = {
                    "fetched_at": _now(),
                    "mode": "full",
                }
                processed += 1
                if len(pending) >= 25:
                    batch += 1
                    results.append(
                        _flush_player_rows(pending, code, season_id, ingest_date, f"full-{batch:03d}")
                    )
                    save_manifest(manifest)
                    pending = []
                if limit is not None and processed >= limit:
                    break
        finally:
            if pending:
                batch += 1
                results.append(_flush_player_rows(pending, code, season_id, ingest_date, f"full-{batch:03d}"))
            save_manifest(manifest)
        log.info("SofaScore %s/%s: %d jugadores con estadísticas completas", code, season_id, processed)

    manifest.setdefault("tournaments", {})[code] = {
        "season_id": season_id,
        "season_name": sname,
        "mode": mode,
        "fetched_at": ingested_at,
    }
    save_manifest(manifest)
    return results


def ingest_all(
    scope: str | None = None,
    season: str | int | None = None,
    mode: str | None = None,
    force: bool = False,
    limit: int | None = None,
    headless: bool = True,
    ingest_date: str | None = None,
) -> list[dict]:
    codes = resolve_scope(scope)
    season = season or config.SOFASCORE_SEASON or None
    ingest_date = ingest_date or date.today().isoformat()
    manifest = storage.read_manifest(config.SOFASCORE_MANIFEST_BLOB)
    results: list[dict] = []

    with SofaScoreClient(headless=headless) as client:
        for code in codes:
            results += ingest_tournament(
                client,
                code,
                season,
                mode_for(code, mode),
                force,
                limit,
                manifest,
                ingest_date,
            )
    return results


def ensure_tables() -> None:
    bq.ensure_tables(TABLE_SPECS)


def check(scope: str | None = None, season: str | int | None = None, headless: bool = True) -> list[dict]:
    """Abre el navegador y muestra la temporada elegida, sin cargar datos."""
    checks = []
    with SofaScoreClient(headless=headless) as client:
        for code in resolve_scope(scope):
            tournament = config.SOFASCORE_TOURNAMENTS[code]
            payload = client.get(f"/unique-tournament/{tournament['id']}/seasons")
            chosen = select_season(payload, season or config.SOFASCORE_SEASON or None)
            checks.append(
                {
                    "league_code": code,
                    "tournament_id": tournament["id"],
                    "season_id": chosen.get("id"),
                    "season_name": chosen.get("name"),
                    "year": chosen.get("year"),
                }
            )
            print(json.dumps(checks[-1], ensure_ascii=False))
    return checks


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--scope", default=None, help="ARG, big5, all o códigos separados por coma")
    parser.add_argument("--season", default=None, help="Año (2026) o id de temporada de SofaScore")
    parser.add_argument("--mode", choices=["top", "full"], default=None)
    parser.add_argument("--force", action="store_true", help="Ignora el manifest y vuelve a pedir")
    parser.add_argument("--limit", type=int, default=None, help="Máximo de jugadores (para probar)")
    parser.add_argument("--headful", action="store_true", help="Muestra el navegador (recomendado)")
    parser.add_argument("--check", action="store_true", help="Solo verifica la sesión y la temporada")
    args = parser.parse_args()

    try:
        headless = config.SOFASCORE_HEADLESS and not args.headful
        if args.check:
            check(args.scope, args.season, headless=headless)
            return
        ensure_tables()
        results = ingest_all(
            args.scope,
            args.season,
            args.mode,
            args.force,
            args.limit,
            headless=headless,
        )
        print(json.dumps(results, indent=2))
    except (SofaScoreBlocked, BudgetExhausted, SofaScoreError, RuntimeError, ValueError) as exc:
        log.error("%s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
