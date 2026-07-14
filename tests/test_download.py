import os
import pytest
from ingestion.config import Config
from ingestion.download import build_taxi_url, download_taxi_parquet


def test_build_taxi_url():
    url = build_taxi_url("2023-01")
    assert url == (
        "https://d37ci6vzurychx.cloudfront.net/trip-data/"
        "yellow_tripdata_2023-01.parquet"
    )


def test_download_skips_if_exists(tmp_path, monkeypatch):
    # file already exists -> download does not attempt network, returns the path
    existing = tmp_path / "yellow_tripdata_2023-01.parquet"
    existing.write_bytes(b"fake")
    cfg = Config(
        project_id="p", bucket="b", dataset_raw="raw", location="US",
        data_dir=str(tmp_path), taxi_month="2023-01",
    )

    def _fail(*a, **k):
        raise AssertionError("should not download, file already exists")

    monkeypatch.setattr("ingestion.download.requests.get", _fail)

    path = download_taxi_parquet(cfg)
    assert path == str(existing)
    assert os.path.exists(path)
