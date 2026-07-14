import pytest

from ingestion.config import load_config, Config


def test_load_config_reads_env(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "proj-x")
    monkeypatch.setenv("GCS_BUCKET", "proj-x-lake")
    monkeypatch.setenv("BQ_DATASET_RAW", "raw")
    monkeypatch.setenv("BQ_LOCATION", "US")
    monkeypatch.setenv("TAXI_DATA_DIR", "./data")
    monkeypatch.setenv("TAXI_MONTH", "2023-01")

    cfg = load_config()

    assert isinstance(cfg, Config)
    assert cfg.project_id == "proj-x"
    assert cfg.bucket == "proj-x-lake"
    assert cfg.dataset_raw == "raw"
    assert cfg.taxi_month == "2023-01"


def test_load_config_missing_required_raises(monkeypatch):
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    monkeypatch.setenv("GCS_BUCKET", "proj-x-lake")
    with pytest.raises(ValueError, match="GCP_PROJECT_ID"):
        load_config()
