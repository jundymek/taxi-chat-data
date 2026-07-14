import os

from google.api_core.exceptions import Conflict
from google.cloud import bigquery, storage

from ingestion.config import Config


def blob_name_for(local_path: str) -> str:
    """Object path in the bucket: raw/ layer + file name."""
    return f"raw/{os.path.basename(local_path)}"


def ensure_bucket(cfg: Config) -> None:
    client = storage.Client(project=cfg.project_id)
    if client.lookup_bucket(cfg.bucket) is not None:
        print(f"[gcs] bucket {cfg.bucket} already exists")
        return
    try:
        client.create_bucket(cfg.bucket, location=cfg.location)
        print(f"[gcs] created bucket {cfg.bucket}")
    except Conflict:
        # Another run (or a race between lookup and create) already made it;
        # treat that as success so the step stays idempotent, mirroring
        # ensure_dataset's exists_ok=True.
        print(f"[gcs] bucket {cfg.bucket} already exists")


def upload_to_gcs(cfg: Config, local_path: str) -> str:
    client = storage.Client(project=cfg.project_id)
    bucket = client.bucket(cfg.bucket)
    blob_name = blob_name_for(local_path)
    blob = bucket.blob(blob_name)
    # Default per-request timeout (60s) is too tight for slow/uneven upload
    # links; raise it so a large file doesn't fail on transient slowness.
    blob.upload_from_filename(local_path, timeout=600)
    uri = f"gs://{cfg.bucket}/{blob_name}"
    print(f"[gcs] uploaded {uri}")
    return uri


def ensure_dataset(cfg: Config) -> None:
    client = bigquery.Client(project=cfg.project_id)
    dataset_id = f"{cfg.project_id}.{cfg.dataset_raw}"
    dataset = bigquery.Dataset(dataset_id)
    dataset.location = cfg.location
    client.create_dataset(dataset, exists_ok=True)
    print(f"[bq] dataset {dataset_id} ready")


def load_gcs_to_bq(cfg: Config, gcs_uri: str) -> int:
    client = bigquery.Client(project=cfg.project_id)
    table_id = f"{cfg.project_id}.{cfg.dataset_raw}.trips"
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.PARQUET,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        autodetect=True,
    )
    load_job = client.load_table_from_uri(gcs_uri, table_id, job_config=job_config)
    load_job.result()  # wait for completion
    table = client.get_table(table_id)
    print(f"[bq] loaded {table.num_rows} rows into {table_id}")
    return table.num_rows


def run_batch(cfg: Config, local_path: str) -> int:
    ensure_bucket(cfg)
    gcs_uri = upload_to_gcs(cfg, local_path)
    ensure_dataset(cfg)
    return load_gcs_to_bq(cfg, gcs_uri)


if __name__ == "__main__":
    from ingestion.config import load_config
    from ingestion.download import download_taxi_parquet

    cfg = load_config()
    path = download_taxi_parquet(cfg)
    run_batch(cfg, path)
