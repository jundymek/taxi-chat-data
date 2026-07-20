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


def test_build_taxi_url_rejects_invalid_month():
    with pytest.raises(ValueError):
        build_taxi_url("2023-01/../../etc")


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


def test_download_rejects_invalid_month(tmp_path):
    cfg = Config(
        project_id="p", bucket="b", dataset_raw="raw", location="US",
        data_dir=str(tmp_path), taxi_month="../escape",
    )
    with pytest.raises(ValueError):
        download_taxi_parquet(cfg)


def test_download_interrupted_stream_leaves_no_partial_and_is_retried(
    tmp_path, monkeypatch
):
    cfg = Config(
        project_id="p", bucket="b", dataset_raw="raw", location="US",
        data_dir=str(tmp_path), taxi_month="2023-01",
    )
    dest = tmp_path / "yellow_tripdata_2023-01.parquet"
    tmp_dest = tmp_path / "yellow_tripdata_2023-01.parquet.part"

    call_count = {"n": 0}

    class _FailingResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size):
            yield b"partial-bytes"
            raise ConnectionError("connection dropped mid-stream")

    class _OkResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size):
            yield b"complete-bytes"

    def _get(*a, **k):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return _FailingResponse()
        return _OkResponse()

    monkeypatch.setattr("ingestion.download.requests.get", _get)

    # First attempt fails mid-stream: no corrupt/partial file left behind.
    with pytest.raises(ConnectionError):
        download_taxi_parquet(cfg)
    assert not dest.exists()
    assert not tmp_dest.exists()

    # Second attempt succeeds, and the previous failure did not create a
    # file that would have been wrongly treated as already downloaded.
    path = download_taxi_parquet(cfg)
    assert path == str(dest)
    assert dest.exists()
    assert dest.read_bytes() == b"complete-bytes"
    assert call_count["n"] == 2
