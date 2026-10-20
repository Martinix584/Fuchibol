"""Helpers de GCS compartidos por las dos fuentes."""

from __future__ import annotations

import json

from ingestion import config


def bucket():
    from google.cloud import storage

    return storage.Client(project=config.GCP_PROJECT_ID).bucket(config.GCS_BUCKET)


def gcs_uri(object_name: str) -> str:
    return f"gs://{config.GCS_BUCKET}/{object_name}"


def upload_file(local_path: str, object_name: str, content_type: str) -> str:
    bucket().blob(object_name).upload_from_filename(local_path, content_type=content_type)
    return gcs_uri(object_name)


def read_manifest(object_name: str) -> dict:
    blob = bucket().blob(object_name)
    if not blob.exists():
        return {}
    return json.loads(blob.download_as_text())


def update_manifest(object_name: str, updates: dict) -> None:
    """Lee, mezcla y vuelve a escribir. Lo usa una sola tarea por corrida, así que no hay carreras."""
    manifest = read_manifest(object_name)
    manifest.update(updates)
    bucket().blob(object_name).upload_from_string(
        json.dumps(manifest, indent=2, sort_keys=True), content_type="application/json"
    )
