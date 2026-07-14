import os

import requests

from ingestion.config import Config

BASE_URL = "https://d37ci6vzurychx.cloudfront.net/trip-data"


def build_taxi_url(month: str) -> str:
    return f"{BASE_URL}/yellow_tripdata_{month}.parquet"


def download_taxi_parquet(cfg: Config) -> str:
    os.makedirs(cfg.data_dir, exist_ok=True)
    filename = f"yellow_tripdata_{cfg.taxi_month}.parquet"
    dest = os.path.join(cfg.data_dir, filename)
    if os.path.exists(dest):
        print(f"[download] file already exists, skipping: {dest}")
        return dest
    url = build_taxi_url(cfg.taxi_month)
    print(f"[download] downloading {url}")
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    print(f"[download] saved {dest}")
    return dest


if __name__ == "__main__":
    from ingestion.config import load_config

    download_taxi_parquet(load_config())
