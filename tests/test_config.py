import os

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
    assert cfg.location == "US"
    assert cfg.data_dir == "./data"
    assert cfg.taxi_month == "2023-01"


def test_load_config_missing_required_raises(monkeypatch):
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    monkeypatch.setenv("GCS_BUCKET", "proj-x-lake")
    with pytest.raises(ValueError, match="GCP_PROJECT_ID"):
        load_config()


def test_load_config_missing_bucket_raises(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "proj-x")
    monkeypatch.delenv("GCS_BUCKET", raising=False)
    with pytest.raises(ValueError, match="GCS_BUCKET"):
        load_config()


def test_load_config_uses_defaults(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "proj-x")
    monkeypatch.setenv("GCS_BUCKET", "proj-x-lake")
    monkeypatch.delenv("BQ_DATASET_RAW", raising=False)
    monkeypatch.delenv("BQ_LOCATION", raising=False)
    monkeypatch.delenv("TAXI_DATA_DIR", raising=False)
    monkeypatch.delenv("TAXI_MONTH", raising=False)

    cfg = load_config()

    assert cfg.dataset_raw == "raw"
    assert cfg.location == "US"
    assert cfg.data_dir == "./data"
    assert cfg.taxi_month == "2023-01"


def test_system_env_takes_precedence_over_dotenv(monkeypatch, tmp_path):
    from dotenv import load_dotenv

    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "GCP_PROJECT_ID=from-dotenv\nGCS_BUCKET=from-dotenv\n"
    )

    monkeypatch.setenv("GCP_PROJECT_ID", "from-system")
    monkeypatch.setenv("GCS_BUCKET", "from-system")

    # load_dotenv() does not override already-set environment variables by
    # default, so system env values must remain in place after this call.
    load_dotenv(dotenv_path=dotenv_path)

    assert os.environ["GCP_PROJECT_ID"] == "from-system"
    assert os.environ["GCS_BUCKET"] == "from-system"

    cfg = load_config()

    assert cfg.project_id == "from-system"
    assert cfg.bucket == "from-system"
