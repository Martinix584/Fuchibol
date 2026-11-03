"""Publica la app en Cloud Run (proyecto fuchibol-512404) con la cuenta de servicio fuchibol-app.

    python deploy/publicar.py

Arma un contexto mínimo (sin .env, keys/ ni secrets.toml), construye con Docker local, sube y despliega.
En Cloud Run no hace falta la clave JSON: Vertex usa la cuenta de servicio adjunta al servicio.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROYECTO = "fuchibol-512404"
REGION = "us-central1"
SERVICIO = "fuchibol"
CUENTA = f"fuchibol-app@{PROYECTO}.iam.gserviceaccount.com"
IMAGEN = f"{REGION}-docker.pkg.dev/{PROYECTO}/cloud-run-source-deploy/{SERVICIO}"
INCLUIR = [
    "app/*.py",
    "app/requirements.txt",
    "data/parquet/**/*.parquet",
    "data/rag/*",
    "dbt/models/**/_*.yml",
    ".streamlit/config.toml",
]


def main() -> None:
    s = tomllib.loads((ROOT / ".streamlit" / "secrets.toml").read_text())
    with tempfile.TemporaryDirectory() as tmp:
        for patron in INCLUIR:
            for p in ROOT.glob(patron):
                destino = Path(tmp) / p.relative_to(ROOT)
                destino.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, destino)
        shutil.copy2(ROOT / "deploy" / "Dockerfile", Path(tmp) / "Dockerfile")
        assert not list(Path(tmp).rglob("secrets.toml")) and not list(Path(tmp).rglob("*.json"))
        # Se construye acá con Docker y se sube: Cloud Build usa una cuenta sin permisos en esta organización.
        subprocess.run(
            ["gcloud", "auth", "configure-docker", REGION + "-docker.pkg.dev", "--quiet"], check=True
        )
        subprocess.run(["docker", "build", "--platform", "linux/amd64", "-t", IMAGEN, tmp], check=True)
        subprocess.run(["docker", "push", IMAGEN], check=True)
        subprocess.run(
            [
                "gcloud",
                "run",
                "deploy",
                SERVICIO,
                "--image",
                IMAGEN,
                "--project",
                PROYECTO,
                "--region",
                REGION,
                "--service-account",
                CUENTA,
                "--port",
                "7860",
                "--cpu",
                "1",
                "--memory",
                "2Gi",
                # ponytail: 0 instancias mínimas = gratis con arranque en frío; 1 si hace falta al instante
                "--min-instances",
                "0",
                "--max-instances",
                "1",  # 1 como máximo: tope de costo
                "--session-affinity",
                "--timeout",
                "3600",  # el websocket de Streamlit dura toda la visita
                "--allow-unauthenticated",
                "--set-env-vars",
                f"CHAT_CODIGO={s['CHAT_CODIGO']},MEM0_API_KEY={s['MEM0_API_KEY']}",
                "--quiet",
            ],
            check=True,
        )


if __name__ == "__main__":
    main()
