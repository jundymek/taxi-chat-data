import os
import re

import requests

from ingestion.config import Config

BASE_URL = "https://d37ci6vzurychx.cloudfront.net/trip-data"

# Expected format: YYYY-MM (e.g. 2023-01). Enforced to keep the value safe
# for use in both the remote URL and the local filesystem path.
_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def _validate_month(month: str) -> str:
    if not _MONTH_RE.match(month):
        raise ValueError(
            f"Invalid taxi_month {month!r}; expected YYYY-MM (e.g. '2023-01')"
        )
    return month


def build_taxi_url(month: str) -> str:
    month = _validate_month(month)
    return f"{BASE_URL}/yellow_tripdata_{month}.parquet"


def download_taxi_parquet(cfg: Config) -> str:
    os.makedirs(cfg.data_dir, exist_ok=True)
    month = _validate_month(cfg.taxi_month)
    filename = f"yellow_tripdata_{month}.parquet"
    dest = os.path.join(cfg.data_dir, filename)
    if os.path.exists(dest):
        print(f"[download] file already exists, skipping: {dest}")
        return dest
    url = build_taxi_url(month)
    print(f"[download] downloading {url}")
    tmp_dest = f"{dest}.part"
    try:
        with requests.get(url, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(tmp_dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 20):
                    f.write(chunk)
        os.replace(tmp_dest, dest)
    except BaseException:
        # Don't leave a partial/corrupt file behind that a later run's
        # existence check would mistake for a completed download.
        if os.path.exists(tmp_dest):
            os.remove(tmp_dest)
        raise
    print(f"[download] saved {dest}")
    return dest


if __name__ == "__main__":
    from ingestion.config import load_config

    download_taxi_parquet(load_config())
