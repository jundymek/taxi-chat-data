import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()  # load .env if present; system env vars take precedence


@dataclass
class Config:
    project_id: str
    bucket: str
    dataset_raw: str
    location: str
    data_dir: str
    taxi_month: str


def load_config() -> Config:
    project_id = os.getenv("GCP_PROJECT_ID")
    if not project_id:
        raise ValueError("Missing required environment variable GCP_PROJECT_ID (set it in .env)")
    bucket = os.getenv("GCS_BUCKET")
    if not bucket:
        raise ValueError("Missing required environment variable GCS_BUCKET (set it in .env)")
    return Config(
        project_id=project_id,
        bucket=bucket,
        dataset_raw=os.getenv("BQ_DATASET_RAW", "raw"),
        location=os.getenv("BQ_LOCATION", "US"),
        data_dir=os.getenv("TAXI_DATA_DIR", "./data"),
        taxi_month=os.getenv("TAXI_MONTH", "2023-01"),
    )
