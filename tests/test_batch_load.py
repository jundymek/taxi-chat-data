import pytest

from ingestion.batch_load import blob_name_for


def test_blob_name_for_strips_directory():
    assert blob_name_for("./data/yellow_tripdata_2023-01.parquet") == (
        "raw/yellow_tripdata_2023-01.parquet"
    )


@pytest.mark.integration
def test_run_batch_loads_rows():
    # MANUAL smoke-test: requires configured GCP + a downloaded file.
    # Run: pytest tests/test_batch_load.py -m integration -v
    from ingestion.batch_load import run_batch
    from ingestion.config import load_config
    from ingestion.download import download_taxi_parquet

    cfg = load_config()
    path = download_taxi_parquet(cfg)
    rows = run_batch(cfg, path)
    assert rows > 0
