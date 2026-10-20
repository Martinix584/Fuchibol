from ingestion import config
from ingestion.extract import changed_tables, fingerprint_from_headers, gcs_object_name, source_url


def test_source_url():
    assert source_url("players") == f"{config.BASE_URL}/players.csv.gz"


def test_gcs_object_name_is_partitioned_by_ingest_date():
    assert (
        gcs_object_name("transfers", "2026-10-20")
        == "raw/transfermarkt/transfers/ingest_date=2026-10-20/transfers.csv.gz"
    )


def test_fingerprint_prefers_etag():
    assert fingerprint_from_headers({"ETag": '"abc"', "Content-Length": "10"}) == "abc"


def test_fingerprint_falls_back_to_last_modified_and_size():
    headers = {"Last-Modified": "Mon, 06 Jul 2026 10:00:00 GMT", "Content-Length": "10"}
    assert fingerprint_from_headers(headers) == "Mon, 06 Jul 2026 10:00:00 GMT|10"


def test_changed_tables_detects_new_and_modified():
    remote = {"players": "v2", "clubs": "v1", "games": "v1"}
    manifest = {"players": "v1", "clubs": "v1"}
    assert changed_tables(remote, manifest) == ["players", "games"]


def test_changed_tables_empty_when_nothing_changed():
    assert changed_tables({"players": "v1"}, {"players": "v1"}) == []
